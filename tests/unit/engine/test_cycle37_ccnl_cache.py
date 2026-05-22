"""사이클 37 (2026-05-21) — KIS 실제 last_cntg_hour 캐시 + UI 노출.

배경:
- 사이클 35 세션별 구독 UI 가 `last_tick` (WebSocket 수신 시각) 만 표시.
- 두 시각이 다 필요:
  - `last_tick`: 우리 WS 가 받은 마지막 tick (stale 판정 기준)
  - `last_cntg_hour`: KIS 실제 마지막 체결시각 (시장 거래 발생)
- 차이가 크면 WS 구독 문제 진단 가능 (KIS 정상 송출 중인데 우리만 못 받음).

본 사이클 (37) 변경:
- `scheduler._last_ccnl_cache: dict[str, dict]` 신규 필드
  - 구조: `{ticker: {fetched_at: datetime, last_cntg_hour: str, today_volume: int}}`
  - TTL 5분 (KIS Rate Limit 보호)
- `_refresh_stale_ccnl_cache(stale_tickers)` 헬퍼 — stale (r≥2) 종목 inquire_ccnl 호출 + 캐시 갱신
- `_evaluate_universe_guard` 호출과 중복 차단 (같은 사이클 동일 ticker 재호출 0)
- `_reset_daily_state` 동행 clear

사양 (C-1 ~ C-7):
- C-1: `_last_ccnl_cache` 필드 초기화
- C-2: `_refresh_stale_ccnl_cache` 가 stale 종목 (r≥2) 대상 inquire_ccnl 호출 + 캐시 저장
- C-3: TTL 5분 — 5분 이내 hit (재호출 0), 5분 초과 재호출
- C-4: cap 20 (단일 사이클 최대 20 종목 호출)
- C-5: 보유 종목 우선순위 — cap 도달 전 보유 종목 먼저 처리
- C-6: KIS None 응답 graceful (캐시 미스 — 다음 사이클 자연 재시도)
- C-7: `_reset_daily_state` 동행 clear
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _make_sched(*, held_tickers: list[str] | None = None):
    """__new__ minimal scheduler with required fields."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True
    sched._stale_retry_count = {}
    sched._stale_last_resubscribe_at = {}
    sched._stale_force_retry_history = {}
    sched._pending_next_day_clear = set()
    sched._universe_excluded_today = set()
    sched._last_ccnl_cache = {}  # 사이클 37 — 새 필드

    fake_strategy = MagicMock()
    fake_state = MagicMock()
    fake_state.positions = {t: MagicMock() for t in (held_tickers or [])}
    fake_strategy.state = fake_state
    fake_registry = MagicMock()
    fake_registry.all = MagicMock(return_value=[fake_strategy])
    fake_registry.is_ticker_held_by_any = MagicMock(
        side_effect=lambda t: t in (held_tickers or [])
    )
    sched.registry = fake_registry
    return sched


# ===========================================================================
# C-1: _last_ccnl_cache 필드 초기화 + _reset_daily_state 동행 clear
# ===========================================================================
def test_last_ccnl_cache_field_initialized_in_init():
    """`TradingScheduler.__init__` 에 `_last_ccnl_cache: dict[str, dict]` 초기화.

    사이클 48 (2026-05-22) 의미 갱신: `_stale_state` 통합 (`StaleTrackerState.last_ccnl_cache`)
    + 호환 layer property — 동일 인터페이스 보존.
    """
    import inspect
    from src.engine.scheduler import TradingScheduler

    src = inspect.getsource(TradingScheduler.__init__)
    # 사이클 48: `_stale_state` 가 7 필드 통합 (last_ccnl_cache 포함)
    assert "_stale_state" in src or "_last_ccnl_cache" in src, (
        "TradingScheduler.__init__ 에 _last_ccnl_cache (또는 통합 _stale_state) 필드 누락"
    )


def test_reset_daily_state_clears_ccnl_cache():
    """`_reset_daily_state` 가 `_last_ccnl_cache.clear()` 호출.

    사이클 48 의미 갱신: `_stale_state.reset_daily()` 위임 (7 필드 일괄 clear).
    """
    import inspect
    from src.engine.scheduler import TradingScheduler

    src = inspect.getsource(TradingScheduler._reset_daily_state)
    # 사이클 48: 통합 reset 위임 또는 기존 .clear() 패턴 호환
    assert (
        "_stale_state.reset_daily()" in src
        or ("_last_ccnl_cache" in src and ".clear()" in src)
    ), (
        "_reset_daily_state 에 _last_ccnl_cache.clear() 누락"
    )


# ===========================================================================
# C-2: _refresh_stale_ccnl_cache 가 stale (r≥2) 종목 inquire_ccnl 호출
# ===========================================================================
@pytest.mark.asyncio
async def test_refresh_calls_inquire_ccnl_for_stale_tickers(monkeypatch):
    """r≥2 stale 종목 대상 inquire_ccnl 호출 + 캐시 저장."""
    sched = _make_sched()
    sched._stale_retry_count = {"036930": 3, "086980": 2, "005930": 1}  # r<2 제외

    captured: list[str] = []

    async def _fake_ccnl(ticker, market="J"):
        captured.append(ticker)
        return {
            "last_cntg_hour": "142045",
            "last_price": 50000,
            "last_volume": 100,
            "last_relative_strength": 80.0,
            "today_volume": 5000,
            "raw_count": 5,
        }

    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_ccnl, raising=False)

    await sched._refresh_stale_ccnl_cache(["036930", "086980", "005930"])

    # r≥2 만 호출
    assert "036930" in captured
    assert "086980" in captured
    assert "005930" not in captured
    assert len(captured) == 2

    # 캐시 저장
    assert "036930" in sched._last_ccnl_cache
    assert sched._last_ccnl_cache["036930"]["last_cntg_hour"] == "142045"
    assert sched._last_ccnl_cache["036930"]["today_volume"] == 5000
    assert "fetched_at" in sched._last_ccnl_cache["036930"]


# ===========================================================================
# C-3: TTL 5분 — 5분 이내 hit, 초과 재호출
# ===========================================================================
@pytest.mark.asyncio
async def test_ttl_5min_caches_within_window(monkeypatch):
    """5분 이내 캐시 hit — inquire_ccnl 재호출 0."""
    sched = _make_sched()
    sched._stale_retry_count = {"036930": 3}

    # 이미 4분 전에 캐시됨
    sched._last_ccnl_cache["036930"] = {
        "fetched_at": datetime.now(KST) - timedelta(seconds=240),
        "last_cntg_hour": "141000",
        "today_volume": 4000,
    }

    spy = AsyncMock()
    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", spy, raising=False)

    await sched._refresh_stale_ccnl_cache(["036930"])

    spy.assert_not_called()
    # 캐시 그대로
    assert sched._last_ccnl_cache["036930"]["last_cntg_hour"] == "141000"


@pytest.mark.asyncio
async def test_ttl_5min_refreshes_after_expiry(monkeypatch):
    """5분 초과 시 재호출 + 캐시 갱신."""
    sched = _make_sched()
    sched._stale_retry_count = {"036930": 3}

    # 6분 전 (5분 초과)
    sched._last_ccnl_cache["036930"] = {
        "fetched_at": datetime.now(KST) - timedelta(seconds=360),
        "last_cntg_hour": "140000",
        "today_volume": 3000,
    }

    async def _fake_ccnl(ticker, market="J"):
        return {
            "last_cntg_hour": "142045",
            "last_price": 50000,
            "last_volume": 100,
            "last_relative_strength": 80.0,
            "today_volume": 5500,
            "raw_count": 6,
        }

    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_ccnl, raising=False)

    await sched._refresh_stale_ccnl_cache(["036930"])

    # 캐시 갱신
    assert sched._last_ccnl_cache["036930"]["last_cntg_hour"] == "142045"
    assert sched._last_ccnl_cache["036930"]["today_volume"] == 5500


# ===========================================================================
# C-4: cap 20 (단일 사이클 최대 호출 수)
# ===========================================================================
@pytest.mark.asyncio
async def test_cap_20_calls_per_cycle(monkeypatch):
    """단일 사이클에 inquire_ccnl 호출 최대 20건 — KIS Rate Limit 보호."""
    sched = _make_sched()
    # 30 종목 stale
    many_tickers = [f"{i+10000:06d}" for i in range(30)]
    sched._stale_retry_count = {t: 3 for t in many_tickers}

    call_count = {"n": 0}

    async def _fake_ccnl(ticker, market="J"):
        call_count["n"] += 1
        return {
            "last_cntg_hour": "142045",
            "last_price": 50000,
            "last_volume": 100,
            "last_relative_strength": 80.0,
            "today_volume": 5000,
            "raw_count": 5,
        }

    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_ccnl, raising=False)

    await sched._refresh_stale_ccnl_cache(many_tickers)

    assert call_count["n"] == 20, (
        f"단일 사이클 cap 20 초과 — 실제={call_count['n']}건 호출"
    )


# ===========================================================================
# C-5: 보유 종목 우선순위 — cap 도달 전 보유 종목 먼저 처리
# ===========================================================================
@pytest.mark.asyncio
async def test_held_tickers_processed_first(monkeypatch):
    """30종목 stale 중 보유 5종목은 cap 20 내에 반드시 포함."""
    held = [f"H{i:05d}" for i in range(5)]
    other = [f"O{i:05d}" for i in range(25)]
    all_tickers = other + held  # held 가 뒤에 있어도 우선순위로 앞으로 와야

    sched = _make_sched(held_tickers=held)
    sched._stale_retry_count = {t: 3 for t in all_tickers}

    captured: list[str] = []

    async def _fake_ccnl(ticker, market="J"):
        captured.append(ticker)
        return {"last_cntg_hour": "142045", "last_price": 50000, "last_volume": 100,
                "last_relative_strength": 80.0, "today_volume": 5000, "raw_count": 5}

    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_ccnl, raising=False)

    await sched._refresh_stale_ccnl_cache(all_tickers)

    # cap 20 — 보유 5 + 후보 15
    assert len(captured) == 20
    # 보유 5종목은 모두 처리됨
    for h in held:
        assert h in captured, f"보유 종목 {h} 가 cap 내 우선 처리 누락"


# ===========================================================================
# C-6: KIS None 응답 graceful (캐시 미스)
# ===========================================================================
@pytest.mark.asyncio
async def test_kis_none_response_graceful(monkeypatch):
    """KIS None 응답 (오프장 / 거래 없음) → 캐시 저장 안 함, 다음 사이클 재시도."""
    sched = _make_sched()
    sched._stale_retry_count = {"036930": 3}

    async def _fake_none(ticker, market="J"):
        return None

    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_none, raising=False)

    await sched._refresh_stale_ccnl_cache(["036930"])

    # 캐시 저장 안 함 (다음 사이클 재시도 가능)
    assert "036930" not in sched._last_ccnl_cache


@pytest.mark.asyncio
async def test_kis_exception_graceful(monkeypatch):
    """KIS 예외 → 한 종목 격리 + 다른 종목 처리 계속."""
    sched = _make_sched()
    sched._stale_retry_count = {"036930": 3, "086980": 3}

    async def _fake_ccnl(ticker, market="J"):
        if ticker == "036930":
            raise RuntimeError("KIS timeout")
        return {"last_cntg_hour": "142045", "last_price": 50000, "last_volume": 100,
                "last_relative_strength": 80.0, "today_volume": 5000, "raw_count": 5}

    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_ccnl, raising=False)

    # 예외 전파 없이 완료
    await sched._refresh_stale_ccnl_cache(["036930", "086980"])

    # 036930 격리 (캐시 저장 안 됨)
    assert "036930" not in sched._last_ccnl_cache
    # 086980 정상
    assert "086980" in sched._last_ccnl_cache
