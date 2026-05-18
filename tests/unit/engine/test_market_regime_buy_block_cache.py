"""사이클 11 Red (2026-05-18) — `MarketRegime.get_buy_block_state()` 60s TTL 캐시.

배경 (결함 D, 운영 사고 2026-05-18 09:00 진입 이후):
- `risk.on_tick()` 가 매수 신호 평가 직전마다 `get_buy_block_state()` 호출.
- 매 호출이 supabase `system_config` 5 키(mode + 4 임계)를 fetch.
- 30 종목 × 10s tick → 분당 ~180 호출 × 5 키 = **900~1800 DB 쿼리/분**.
- supabase-py HTTP/2 stale connection 으로 매번 `[buy_block_thresholds] get ... 실패` ERROR.
- graceful fallback 동작이라 매매 안전성 영향 0 이지만 ERROR 로그 누적 + DB 부하 과다.

본 사이클은 `MarketRegime` 인스턴스에 60s TTL 캐시를 추가해 매수 평가당 DB 호출
180배 감소. 운영자 Settings UI 토글 시 `invalidate_buy_block_cache()` 로 즉시 무효화.

6 케이스:
1. TTL fresh — 60s 이내 재호출 시 DB fetch 0 회 (캐시 hit)
2. TTL 만료 — 60s 경과 후 DB fetch 1 회 (캐시 갱신)
3. invalidate_buy_block_cache — 명시 무효화 후 다음 호출 시 DB fetch
4. 첫 호출 시 DB fetch — 캐시 없을 때 정상 동작
5. 동시 호출 — 캐시 hit 인 두 번째 호출은 동일 객체 반환 (consistency)
6. DB 예외 시 캐시 미저장 — 안전 폴백 분기는 캐시 영구 오염 안 함

`time.monotonic()` 을 monkeypatch 해 임의 시각 조작.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def fake_clock(monkeypatch):
    """`market_regime.time.monotonic` 을 가짜 시계로 교체. fixture 반환 list[float] 제어."""
    from src.engine import market_regime as mr

    state = {"now": 1000.0}

    def _fake_monotonic():
        return state["now"]

    monkeypatch.setattr(mr.time, "monotonic", _fake_monotonic, raising=False)
    return state


@pytest.fixture
def patched_db(monkeypatch):
    """`_db_get_buy_block_mode` / `_db_get_buy_block_thresholds` 를 호출 카운터 mock 으로 교체."""
    from src.db.system_config import BuyBlockThresholds
    from src.engine import market_regime as mr

    mode_calls = {"count": 0}
    thresholds_calls = {"count": 0}

    async def _mode():
        mode_calls["count"] += 1
        return "HARD"

    async def _thresholds():
        thresholds_calls["count"] += 1
        return BuyBlockThresholds(
            vix_threshold=25.0,
            fg_high_threshold=85.0,
            fg_low_threshold=15.0,
            defensive_enabled=True,
        )

    monkeypatch.setattr(mr, "_db_get_buy_block_mode", _mode, raising=False)
    monkeypatch.setattr(mr, "_db_get_buy_block_thresholds", _thresholds, raising=False)
    return {"mode": mode_calls, "thresholds": thresholds_calls}


# ---------------------------------------------------------------------------
# Case 1: TTL fresh — 60s 이내 재호출 캐시 hit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_buy_block_cache_fresh_hits_skip_db_fetch(fake_clock, patched_db):
    """첫 호출 후 1초 뒤 재호출 → DB fetch 1 회만 (캐시 hit)."""
    from src.engine.market_regime import MarketRegime

    r = MarketRegime(regime="neutral", vix=20.0, fear_greed_score=50.0)

    # 1차 호출 — DB fetch 1
    state1 = await r.get_buy_block_state()
    assert state1.mode == "HARD"
    assert patched_db["mode"]["count"] == 1
    assert patched_db["thresholds"]["count"] == 1

    # 시간 1s 경과 — TTL 내
    fake_clock["now"] = 1001.0

    # 2차 호출 — 캐시 hit, DB fetch 0 추가
    state2 = await r.get_buy_block_state()
    assert state2.mode == "HARD"
    assert patched_db["mode"]["count"] == 1  # 증가 없음
    assert patched_db["thresholds"]["count"] == 1


# ---------------------------------------------------------------------------
# Case 2: TTL 만료 — 60s 경과 후 DB fetch 갱신
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_buy_block_cache_expires_after_ttl(fake_clock, patched_db):
    """TTL 60s 경과 후 호출 → DB fetch 추가 1 회 (캐시 갱신)."""
    from src.engine.market_regime import MarketRegime

    r = MarketRegime(regime="neutral", vix=20.0)

    await r.get_buy_block_state()
    assert patched_db["mode"]["count"] == 1

    # 61s 경과 — TTL 만료
    fake_clock["now"] = 1061.0

    await r.get_buy_block_state()
    assert patched_db["mode"]["count"] == 2  # 캐시 갱신 1 회 추가
    assert patched_db["thresholds"]["count"] == 2


# ---------------------------------------------------------------------------
# Case 3: invalidate_buy_block_cache — 명시 무효화 후 다음 호출 시 fetch
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invalidate_cache_forces_next_fetch(fake_clock, patched_db):
    """`invalidate_buy_block_cache()` 호출 → 다음 호출 시 즉시 DB fetch.

    운영 UI Settings 토글 (`PUT /api/integrations/buy-block`) 시 호출.
    TTL 미만 경과여도 무효화돼야 즉시 반영.
    """
    from src.engine.market_regime import MarketRegime

    r = MarketRegime(regime="neutral", vix=20.0)

    await r.get_buy_block_state()
    assert patched_db["mode"]["count"] == 1

    # 명시 무효화
    r.invalidate_buy_block_cache()

    # 시간 변화 없이 다시 호출 → DB fetch 추가
    await r.get_buy_block_state()
    assert patched_db["mode"]["count"] == 2


# ---------------------------------------------------------------------------
# Case 4: 첫 호출 — 캐시 없을 때 DB fetch 정상 동작
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_first_call_fetches_from_db(fake_clock, patched_db):
    """캐시 미존재 상태에서 첫 호출 → DB fetch 1 회."""
    from src.engine.market_regime import MarketRegime

    r = MarketRegime()
    assert patched_db["mode"]["count"] == 0

    state = await r.get_buy_block_state()
    assert state.mode == "HARD"
    assert patched_db["mode"]["count"] == 1


# ---------------------------------------------------------------------------
# Case 5: 동시 호출 — 캐시 hit 시 동일 결과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_consecutive_calls_return_consistent_state(fake_clock, patched_db):
    """캐시 hit 인 두 번째 호출 결과 동일성 — mode/blocked/reasons 모두 일치."""
    from src.engine.market_regime import MarketRegime

    r = MarketRegime(regime="defensive", vix=30.0)

    s1 = await r.get_buy_block_state()
    fake_clock["now"] = 1010.0  # TTL 내
    s2 = await r.get_buy_block_state()

    assert s1.mode == s2.mode
    assert s1.blocked == s2.blocked
    assert s1.soft_multiplier == s2.soft_multiplier
    assert s1.reasons == s2.reasons


# ---------------------------------------------------------------------------
# Case 6: DB 예외 시 캐시 미저장 — 폴백 분기는 캐시 영구 오염 안 함
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_db_exception_does_not_poison_cache(fake_clock, monkeypatch):
    """DB fetch 실패(폴백 분기) 시 결과를 캐시에 저장하지 않아야 함.

    운영 UI 가 임계값을 정상 갱신 후 폴백 결과가 영구 캐시되면 새 임계가 반영 안 됨.
    안전 폴백은 즉시(매 호출) 반환 — 다음 호출에서 정상 fetch 재시도.
    """
    from src.engine import market_regime as mr
    from src.engine.market_regime import MarketRegime

    fetch_count = {"count": 0}

    async def _failing_mode():
        fetch_count["count"] += 1
        raise RuntimeError("DB connection error")

    async def _failing_thresholds():
        raise RuntimeError("DB connection error")

    monkeypatch.setattr(mr, "_db_get_buy_block_mode", _failing_mode, raising=False)
    monkeypatch.setattr(mr, "_db_get_buy_block_thresholds", _failing_thresholds, raising=False)

    r = MarketRegime(regime="neutral", vix=20.0)

    # 1차: 폴백 분기 (HARD + 기본 임계)
    s1 = await r.get_buy_block_state()
    assert s1.mode == "HARD"
    assert fetch_count["count"] == 1

    # 1초 후 재호출 — 캐시에 저장됐다면 fetch 안 함, 폴백 분기는 매 호출 fetch 시도해야 함
    fake_clock["now"] = 1001.0
    s2 = await r.get_buy_block_state()
    assert fetch_count["count"] == 2, "폴백 분기는 캐시 오염 안 함 — 매번 재시도"
    assert s2.mode == "HARD"
