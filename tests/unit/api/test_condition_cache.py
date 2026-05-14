"""PR-C (2026-05-14) — condition.py TTL 캐시 검증.

`fetch_stock_detail` 5초 TTL / `fetch_daily_candles` 300초 TTL 캐시. 동일 ticker
반복 조회 시 KIS 호출 1회로 수렴 (5xx 노출 면적 축소 + 외부 부하 감소).

회귀 가드:
- TTL 만료 후 재호출 시 KIS 호출 발생
- days 별 캐시 키 분리 (60일 vs 21일 등)
- `_reset_daily_state` 호출 후 캐시 비어있음 (clear_caches API)
- 동시 다회 호출 시 race condition 없음 (asyncio.Lock)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_caches_around_test():
    """매 테스트마다 캐시 초기화 — 격리."""
    from src.api import condition

    condition.clear_caches()
    yield
    condition.clear_caches()


# ---------------------------------------------------------------------------
# fetch_stock_detail — TTL hit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_stock_detail_hits_cache_within_ttl(monkeypatch):
    """첫 호출 후 TTL 내 재호출은 KIS 호출 발생 안 함."""
    from src.api import condition

    mock_get = AsyncMock(return_value={"output": {"stck_prpr": "65000"}})
    monkeypatch.setattr(condition, "kis_get", mock_get)

    r1 = await condition.fetch_stock_detail("005930")
    r2 = await condition.fetch_stock_detail("005930")
    r3 = await condition.fetch_stock_detail("005930")

    assert r1 == r2 == r3 == {"stck_prpr": "65000"}
    assert mock_get.await_count == 1, "TTL 내 KIS 호출 1회만"


# ---------------------------------------------------------------------------
# fetch_stock_detail — TTL 만료 후 재호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_stock_detail_miss_after_ttl(monkeypatch):
    """TTL 경과 후 재호출 시 KIS 호출 발생."""
    from src.api import condition

    mock_get = AsyncMock(return_value={"output": {"stck_prpr": "65000"}})
    monkeypatch.setattr(condition, "kis_get", mock_get)

    # monotonic 을 monkeypatch — 시간 흐름 시뮬
    current_time = [1000.0]

    def fake_monotonic():
        return current_time[0]

    monkeypatch.setattr(condition.time, "monotonic", fake_monotonic)

    await condition.fetch_stock_detail("005930")  # t=1000
    assert mock_get.await_count == 1

    # TTL(5s) 내 → 캐시 hit
    current_time[0] = 1004.0
    await condition.fetch_stock_detail("005930")
    assert mock_get.await_count == 1

    # TTL 경과 → miss
    current_time[0] = 1006.0
    await condition.fetch_stock_detail("005930")
    assert mock_get.await_count == 2


# ---------------------------------------------------------------------------
# fetch_stock_detail — ticker 별 캐시 키 분리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_stock_detail_separate_cache_per_ticker(monkeypatch):
    from src.api import condition

    responses = {
        "005930": {"output": {"stck_prpr": "65000"}},
        "000660": {"output": {"stck_prpr": "180000"}},
    }

    async def _fake_get(_path, _tr, params):
        return responses[params["fid_input_iscd"]]

    mock = AsyncMock(side_effect=_fake_get)
    monkeypatch.setattr(condition, "kis_get", mock)

    r1 = await condition.fetch_stock_detail("005930")
    r2 = await condition.fetch_stock_detail("000660")
    r3 = await condition.fetch_stock_detail("005930")  # 캐시 hit
    r4 = await condition.fetch_stock_detail("000660")  # 캐시 hit

    assert r1["stck_prpr"] == "65000"
    assert r2["stck_prpr"] == "180000"
    assert r1 == r3
    assert r2 == r4
    # ticker 당 1회씩만 KIS 호출
    assert mock.await_count == 2


# ---------------------------------------------------------------------------
# fetch_daily_candles — days 별 캐시 키 분리
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_daily_candles_caches_per_days_key(monkeypatch):
    """동일 ticker + 다른 days → 별도 캐시. 같은 (ticker, days) 만 재사용."""
    from src.api import condition

    call_count = [0]

    async def _fake_get(_path, _tr, params):
        call_count[0] += 1
        # output2에 days 일치 응답
        return {
            "output2": [
                {"stck_bsop_date": f"2026050{i}", "stck_clpr": str(60000 + i)}
                for i in range(1, 10)
            ]
        }

    monkeypatch.setattr(condition, "kis_get", _fake_get)

    await condition.fetch_daily_candles("005930", days=21)
    await condition.fetch_daily_candles("005930", days=21)  # 캐시 hit
    assert call_count[0] == 1

    await condition.fetch_daily_candles("005930", days=60)  # 다른 days → miss
    assert call_count[0] == 2

    await condition.fetch_daily_candles("005930", days=60)  # 캐시 hit
    assert call_count[0] == 2


# ---------------------------------------------------------------------------
# clear_caches / _reset_daily_state 통합
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_stock_detail_cache_cleared_on_clear_caches(monkeypatch):
    """`clear_caches()` 직접 호출 시 캐시 무효화 → 다음 호출은 KIS 발생."""
    from src.api import condition

    mock_get = AsyncMock(return_value={"output": {"stck_prpr": "65000"}})
    monkeypatch.setattr(condition, "kis_get", mock_get)

    await condition.fetch_stock_detail("005930")
    await condition.fetch_stock_detail("005930")
    assert mock_get.await_count == 1

    condition.clear_caches()

    await condition.fetch_stock_detail("005930")
    assert mock_get.await_count == 2, "clear_caches 후 캐시 miss → 재조회"


@pytest.mark.asyncio
async def test_reset_daily_state_clears_condition_caches(monkeypatch):
    """`scheduler._reset_daily_state()` 가 condition 캐시도 일괄 무효화한다.

    안전 규칙(CLAUDE.md): `_reset_daily_state` 에 새 상태(캐시) 추가 시 정리 누락 금지.
    """
    from src.api import condition
    from src.engine.scheduler import TradingScheduler

    mock_get = AsyncMock(return_value={"output": {"stck_prpr": "65000"}})
    monkeypatch.setattr(condition, "kis_get", mock_get)

    # 캐시 시드
    await condition.fetch_stock_detail("005930")
    assert "005930" in condition._price_cache

    # scheduler instance 의 reset 호출 (sync)
    sched = TradingScheduler()
    sched._reset_daily_state()

    assert "005930" not in condition._price_cache, "reset 후 price cache 비어있음"
    assert condition._candle_cache == {}, "reset 후 candle cache 비어있음"


# ---------------------------------------------------------------------------
# 동시 호출 — KIS 호출 1회 보장 (lock + 캐시 협조)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_stock_detail_concurrent_calls_share_first_fetch(monkeypatch):
    """asyncio.gather 로 10회 동시 호출해도 KIS 호출 1회만 (single-flight).

    명세(02_bundle_abc): 동시 호출 시 첫 호출만 fetch, 나머지는 같은 결과 합류.
    """
    import asyncio

    from src.api import condition

    call_count = [0]

    async def _slow_get(*_args, **_kwargs):
        call_count[0] += 1
        await asyncio.sleep(0.01)
        return {"output": {"stck_prpr": "65000"}}

    monkeypatch.setattr(condition, "kis_get", _slow_get)

    results = await asyncio.gather(*(
        condition.fetch_stock_detail("005930") for _ in range(10)
    ))

    assert all(r == {"stck_prpr": "65000"} for r in results)
    # single-flight — 10개 동시 호출이어도 KIS 1회만
    assert call_count[0] == 1, f"single-flight 위반: KIS {call_count[0]}회 호출"


@pytest.mark.asyncio
async def test_fetch_daily_candles_concurrent_calls_share_first_fetch(monkeypatch):
    """daily candle 동시 호출도 single-flight."""
    import asyncio

    from src.api import condition

    call_count = [0]

    async def _slow_get(*_args, **_kwargs):
        call_count[0] += 1
        await asyncio.sleep(0.01)
        return {
            "output2": [
                {"stck_bsop_date": "20260512", "stck_clpr": "65000"},
            ]
        }

    monkeypatch.setattr(condition, "kis_get", _slow_get)

    results = await asyncio.gather(*(
        condition.fetch_daily_candles("005930", days=21) for _ in range(8)
    ))

    assert all(len(r) == 1 for r in results)
    assert call_count[0] == 1, f"daily single-flight 위반: KIS {call_count[0]}회"
