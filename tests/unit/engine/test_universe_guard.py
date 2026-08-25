"""사이클 32 (R4, 2026-05-21) — universe stale 가드 + KIS 최근체결시각 기록.

배경:
- 사이클 28~29 누적 효과로 메인 편중 73% → 30% 해소됐으나 stale 종목 자체는 분산만 됨.
- 거래량 빈약한 중소형주가 영구 stale 로 41 슬롯 점유 + R1 force_retry 매 5분 KIS Rate Limit 부담.

본 사이클 (32) 변경:
- `_evaluate_universe_guard()` 신규 헬퍼 — stale > MAX_STALE_RETRIES + 거래량 빈약 종목 제외 평가
- 신규 필드 `_universe_excluded_today: set[str]` (RiskManager 또는 scheduler)
- 제외 종목은 `_collect_breakout_tickers` / `_scan_loop` 통합 구독에서 필터링
- WebSocket unsubscribe + INFO 로그 영구 보존
- `_reset_daily_state` 동행 clear (영구 블랙리스트 금지)

안전 가드:
- 보유 종목 (`registry.is_ticker_held_by_any`) 절대 제외 금지
- 익일 청산 (`_pending_next_day_clear`) 절대 제외 금지
- KIS `inquire_ccnl` 응답 graceful (실패 시 제외 보류)
- 동일 ticker 1회/일 KIS 호출 (제외 판단 시점만)

사양 (U-1 ~ U-9):
- U-1: stale > 5 + 빈약 거래량 → universe 제외 + WebSocket unsubscribe
- U-2: stale > 5 + 빈 ccnl 응답 → universe 제외 (no_ccnl reason)
- U-3: stale > 5 + KIS 호출 실패 (None) → 제외 보류 (graceful)
- U-4: stale ≤ 5 → 제외 안 함 (가드 미발화)
- U-5: 보유 종목은 stale 무관 제외 차단
- U-6: 익일청산 종목은 stale 무관 제외 차단
- U-7: `_universe_excluded_today` set 신규 필드 초기화
- U-8: `_reset_daily_state` 동행 clear
- U-9: 제외 INFO 로그 포맷
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — TradingScheduler minimal instance
# ---------------------------------------------------------------------------
def _make_sched(
    *,
    held_tickers: list[str] = None,
    next_day_clear: set[tuple[str, str]] = None,
    stale_counts: dict[str, int] = None,
):
    """__new__ 기반 minimal scheduler."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True
    sched._stale_retry_count = stale_counts or {}
    sched._stale_last_resubscribe_at = {}
    sched._stale_force_retry_history = {}
    sched._pending_next_day_clear = next_day_clear or set()
    sched._universe_excluded_today = set()

    # registry 더블
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
# U-1: stale > 5 + 빈약 거래량 → universe 제외 + WebSocket unsubscribe
# ===========================================================================
@pytest.mark.asyncio
async def test_stale_with_low_volume_excludes_from_universe(monkeypatch):
    """주성엔지니어링 시나리오 — stale 9회 + 진짜 당일 누적 8500 (< 10000) → 제외.

    cycle227 (P0-2) — 판정 소스가 `today_volume`(최근 ~30체결 합)에서 실측 누적
    (tick 관측 우선 → REST 폴백)으로 바뀌었다. 이 테스트는 tick 관측이 없는
    경우이므로 REST 폴백(`inquire_acml_vol`)이 판정을 낸다.
    """
    from src.engine import tick_volume
    tick_volume.reset_for_test()
    sched = _make_sched(stale_counts={"036930": 9})

    # KIS inquire_ccnl mock — 빈약 거래량 응답 (레거시 로그 필드로만 소비됨)
    async def _fake_ccnl(ticker, market="J"):
        return {
            "last_cntg_hour": "091342",
            "last_price": 1500,
            "last_volume": 120,
            "last_relative_strength": 82.5,
            "today_volume": 8500,  # < 10000 임계 (로그 필드 — 판정 소스 아님)
            "raw_count": 5,
        }
    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_ccnl, raising=False)
    # cycle227 — REST 폴백(tick 미관측 시). 진짜 당일 누적도 빈약.
    monkeypatch.setattr(
        quot_mod, "inquire_acml_vol", AsyncMock(return_value=8500), raising=False,
    )

    # WebSocket pool unsubscribe spy
    from src.realtime import websocket_pool as wp_mod
    unsub_spy = AsyncMock()
    monkeypatch.setattr(wp_mod.kis_ws_pool, "unsubscribe", unsub_spy, raising=False)

    # write_log mock
    from src.engine import scheduler as sch_mod
    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    await sched._evaluate_universe_guard(["036930"])
    tick_volume.reset_for_test()

    assert "036930" in sched._universe_excluded_today, (
        f"stale 9회 + today_volume 8500 → 제외 누락. "
        f"excluded={sched._universe_excluded_today}"
    )
    unsub_spy.assert_awaited_once()


# ===========================================================================
# U-2: stale > 5 + 빈 ccnl 응답 (None) → universe 제외 보류 (graceful)
# ===========================================================================
@pytest.mark.asyncio
async def test_stale_with_none_ccnl_response_defers_exclusion(monkeypatch):
    """KIS 응답 None (오프장 / 거래 없음) → 제외 보류, 다음 사이클 재시도."""
    sched = _make_sched(stale_counts={"036930": 9})

    async def _fake_ccnl(ticker, market="J"):
        return None  # 빈 응답 / KIS 오류 (graceful)
    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_ccnl, raising=False)

    from src.realtime import websocket_pool as wp_mod
    unsub_spy = AsyncMock()
    monkeypatch.setattr(wp_mod.kis_ws_pool, "unsubscribe", unsub_spy, raising=False)

    from src.engine import scheduler as sch_mod
    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    await sched._evaluate_universe_guard(["036930"])

    # 정책 결정: KIS None 응답 (오프장 등) 은 제외 보류 — 다음 사이클 재시도
    assert "036930" not in sched._universe_excluded_today, (
        "KIS 응답 None 시 제외 보류 — 다음 사이클 자연 재시도 (graceful)"
    )
    unsub_spy.assert_not_awaited()


# ===========================================================================
# U-3: KIS 호출 예외 → 제외 보류 (graceful)
# ===========================================================================
@pytest.mark.asyncio
async def test_kis_exception_does_not_break_evaluation(monkeypatch):
    """`inquire_ccnl` 호출 예외 → 다른 ticker 평가 계속 (격리).

    cycle227 (P0-2) — 035420 은 tick 미관측이라 REST 폴백(`inquire_acml_vol`)이
    판정을 낸다.
    """
    from src.engine import tick_volume
    tick_volume.reset_for_test()
    sched = _make_sched(stale_counts={"036930": 9, "035420": 8})

    async def _fake_ccnl(ticker, market="J"):
        if ticker == "036930":
            raise RuntimeError("KIS API timeout")
        # 035420 은 정상 응답 (제외 대상)
        return {
            "last_cntg_hour": "091000",
            "last_price": 50000,
            "last_volume": 100,
            "last_relative_strength": 75.0,
            "today_volume": 5000,  # < 10000 (로그 필드 — 판정 소스 아님)
            "raw_count": 3,
        }
    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_ccnl, raising=False)
    # cycle227 — REST 폴백. 035420 의 진짜 당일 누적도 빈약.
    monkeypatch.setattr(
        quot_mod, "inquire_acml_vol", AsyncMock(return_value=5000), raising=False,
    )

    from src.realtime import websocket_pool as wp_mod
    unsub_spy = AsyncMock()
    monkeypatch.setattr(wp_mod.kis_ws_pool, "unsubscribe", unsub_spy, raising=False)

    from src.engine import scheduler as sch_mod
    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    # 예외 전파 없이 완료되어야 함
    await sched._evaluate_universe_guard(["036930", "035420"])
    tick_volume.reset_for_test()

    # 036930 — KIS 예외 → 제외 보류
    assert "036930" not in sched._universe_excluded_today
    # 035420 — 정상 응답 + 거래량 빈약 → 제외
    assert "035420" in sched._universe_excluded_today


# ===========================================================================
# U-4: stale ≤ MAX_STALE_RETRIES (5) → 가드 미발화
# ===========================================================================
@pytest.mark.asyncio
async def test_stale_below_threshold_not_evaluated(monkeypatch):
    """stale 4회 (≤ MAX_STALE_RETRIES=5) → KIS 호출 0건, 제외 0건."""
    sched = _make_sched(stale_counts={"036930": 4})

    spy = AsyncMock()
    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", spy, raising=False)

    await sched._evaluate_universe_guard(["036930"])

    # 임계 미달 → KIS 호출 자체 안 함
    spy.assert_not_called()
    assert "036930" not in sched._universe_excluded_today


# ===========================================================================
# U-5: 보유 종목은 stale 무관 제외 차단
# ===========================================================================
@pytest.mark.asyncio
async def test_held_ticker_never_excluded(monkeypatch):
    """보유 005935 + stale 9회 + 빈약 거래량 → 절대 제외 금지 (손절 평가 우선)."""
    sched = _make_sched(
        held_tickers=["005935"],
        stale_counts={"005935": 9},
    )

    spy = AsyncMock(return_value={
        "last_cntg_hour": "091000", "last_price": 60000, "last_volume": 0,
        "last_relative_strength": 0.0, "today_volume": 0, "raw_count": 0,
    })
    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", spy, raising=False)

    await sched._evaluate_universe_guard(["005935"])

    # 보유 종목은 KIS 호출 자체 사전 차단 (Rate Limit 절약)
    spy.assert_not_called()
    assert "005935" not in sched._universe_excluded_today, (
        "보유 종목 절대 제외 금지 — 손절·트레일링 평가 우선"
    )


# ===========================================================================
# U-6: 익일청산 종목은 stale 무관 제외 차단
# ===========================================================================
@pytest.mark.asyncio
async def test_next_day_clear_ticker_never_excluded(monkeypatch):
    """`_pending_next_day_clear` 보류 종목 + stale 9회 → 절대 제외 금지."""
    sched = _make_sched(
        next_day_clear={("232680", "momentum")},
        stale_counts={"232680": 9},
    )

    spy = AsyncMock()
    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", spy, raising=False)

    await sched._evaluate_universe_guard(["232680"])

    spy.assert_not_called()
    assert "232680" not in sched._universe_excluded_today


# ===========================================================================
# U-7: `_universe_excluded_today` 신규 필드 초기화 (__init__)
# ===========================================================================
def test_universe_excluded_today_field_initialized_in_init():
    """`TradingScheduler.__init__` 가 `_universe_excluded_today: set` 초기화.

    사이클 48 (2026-05-22) 의미 갱신: `_stale_state` 통합 (universe_excluded_today 포함).
    """
    import inspect
    from src.engine.scheduler import TradingScheduler

    src = inspect.getsource(TradingScheduler.__init__)
    # 사이클 48: 통합 _stale_state 또는 기존 직접 필드
    assert "_stale_state" in src or "_universe_excluded_today" in src, (
        "TradingScheduler.__init__ 에 _universe_excluded_today (또는 통합 _stale_state) 초기화 누락"
    )


# ===========================================================================
# U-8: `_reset_daily_state` 동행 clear (영구 블랙리스트 금지)
# ===========================================================================
def test_reset_daily_state_clears_universe_excluded():
    """`_reset_daily_state` 가 `_universe_excluded_today` 도 clear.

    사이클 48 의미 갱신: `_stale_state.reset_daily()` 위임 (7 필드 일괄 clear).
    """
    import inspect
    from src.engine.scheduler import TradingScheduler

    src = inspect.getsource(TradingScheduler._reset_daily_state)
    # 사이클 48: 통합 reset 위임 또는 기존 .clear() 패턴
    assert (
        "_stale_state.reset_daily()" in src
        or ("_universe_excluded_today" in src and ".clear()" in src)
    ), (
        f"_reset_daily_state 가 _universe_excluded_today (또는 통합 _stale_state.reset_daily()) 미 clear "
        f"(영구 블랙리스트 금지 위반)"
    )


# ===========================================================================
# U-9: 제외 INFO 로그 포맷 검증
# ===========================================================================
@pytest.mark.asyncio
async def test_universe_excluded_log_format(monkeypatch, caplog):
    """`[universe_excluded] ticker={t} reason=... retries={n} ...` 포맷.

    cycle227 (P0-2) — tick 미관측이라 REST 폴백(`inquire_acml_vol`)이 판정을 낸다.
    `today_volume` 은 여전히 로그 필드로 남는다(운영 grep 연속성).
    """
    import logging
    from src.engine import tick_volume
    tick_volume.reset_for_test()
    sched = _make_sched(stale_counts={"036930": 9})

    async def _fake_ccnl(ticker, market="J"):
        return {
            "last_cntg_hour": "091342",
            "last_price": 1500,
            "last_volume": 120,
            "last_relative_strength": 82.5,
            "today_volume": 8500,
            "raw_count": 5,
        }
    from src.api import quotation as quot_mod
    monkeypatch.setattr(quot_mod, "inquire_ccnl", _fake_ccnl, raising=False)
    monkeypatch.setattr(
        quot_mod, "inquire_acml_vol", AsyncMock(return_value=8500), raising=False,
    )

    from src.realtime import websocket_pool as wp_mod
    monkeypatch.setattr(wp_mod.kis_ws_pool, "unsubscribe", AsyncMock(), raising=False)

    from src.engine import scheduler as sch_mod
    async def _wl(*a, **kw):
        return None
    monkeypatch.setattr(sch_mod, "write_log", _wl)

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    await sched._evaluate_universe_guard(["036930"])
    tick_volume.reset_for_test()

    log_lines = [r.message for r in caplog.records if "[universe_excluded]" in r.message]
    assert len(log_lines) == 1, f"INFO 로그 누락. records={[r.message for r in caplog.records]}"
    line = log_lines[0]
    assert "ticker=036930" in line
    assert "reason=stale_6plus_low_volume" in line
    assert "retries=9" in line
    assert "last_cntg_hour=091342" in line
    assert "today_volume=8500" in line


# ===========================================================================
# U-10: `_collect_breakout_tickers` 가 제외된 종목 필터링
# ===========================================================================
def test_collect_breakout_tickers_filters_excluded():
    """제외 set 에 있는 ticker 는 후속 구독 후보에서 빠진다."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._universe_excluded_today = {"036930"}

    fake_strategy = MagicMock()
    fake_strategy.config.enabled = True
    fake_strategy.get_scanned_tickers = MagicMock(return_value=["005930", "036930", "035420"])

    fake_registry = MagicMock()
    fake_registry.get = MagicMock(side_effect=lambda sid: (
        fake_strategy if sid in ("volatility_breakout", "long_tail_volatility") else None
    ))
    sched.registry = fake_registry

    result = sched._collect_breakout_tickers()

    # 036930 은 제외 set 에 있으므로 빠짐
    assert "036930" not in result, (
        f"_universe_excluded_today 종목 필터링 누락. result={result}"
    )
    # 다른 종목은 보존
    assert "005930" in result
    assert "035420" in result
