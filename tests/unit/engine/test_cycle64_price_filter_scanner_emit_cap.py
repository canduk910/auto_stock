"""사이클 64 (2026-06-06) Red — E 카테고리: DailyEmitCap + reset 동행 (2 케이스).

> **선행 명세**: `_workspace/red/cycle64_price_filter_scanner.md` (§E)
> **선례**: 사이클 31 R6 `_risk_silent_skip_logged_today` + 사이클 62 C 패턴 답습
> **CLAUDE.md 절대 규칙**: `_reset_daily_state` 동행 reset 의무

요구 행위 (Red 단계 AttributeError 정답):

- E-1: 같은 ticker 100회 호출 시 emit 1회만 (`_price_filter_scanner_skip_logged_today` cap)
- E-2: `scanner.reset_price_filter_daily_state()` 호출 후 cap clear (다음 영업일 재 emit)
      + scheduler `_reset_daily_state` 동행 호출 검증 (정적 inspect)

위험 등급 LOW.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_pf(min_price=5000, max_price=0):
    from src.db.system_config import PriceFilter
    return PriceFilter(min_price=min_price, max_price=max_price)


def _make_basics(ticker: str, prdy_clpr: int):
    """사이클 81 시정 — bfdy_clpr 정본 키 사용 (파라미터명 호환 보존)."""
    from src.models.stock import StockBasics
    return StockBasics(
        ticker=ticker, name="", excg_dvsn_cd="",
        nxt_tradable=True, krx_halted=False, admin_item=False,
        raw={"bfdy_clpr": str(prdy_clpr)},  # 사이클 81 시정 — CTPF1002R 정본 키
    )


# ---------------------------------------------------------------------------
# E-1: cap 1회/ticker/일 (100회 호출 시 emit 1회)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_E1_emit_skip_capped_once_per_day():
    """E-1: 같은 ticker 100회 호출 시 `[price_filter_scanner_skip]` INFO 1회만 emit.

    `_price_filter_scanner_skip_logged_today: DailyEmitCap[str]` cap. 매 sa사이클 폭주 차단.
    """
    from src.engine import scanner

    pf = _make_pf(min_price=5000, max_price=0)
    candidates = ["005930"]

    # 사전 reset — 테스트 격리
    if hasattr(scanner, "reset_price_filter_daily_state"):
        scanner.reset_price_filter_daily_state()

    with patch("src.engine.scanner.logger") as mock_logger, \
         patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get",
               AsyncMock(return_value=_make_basics("005930", prdy_clpr=3000))), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        # 같은 ticker 100회 호출 (매번 차단 + cap 적용)
        for _ in range(100):
            await scanner._apply_price_filter(candidates, protected_tickers=set())

    # logger.info 호출 중 `[price_filter_scanner_skip]` 포함 1회만
    info_calls = [c for c in mock_logger.info.call_args_list
                  if "[price_filter_scanner_skip]" in str(c)]
    assert len(info_calls) == 1, (
        f"emit cap 위반 — 100회 호출 시 1회만 emit 해야 함 (실제 {len(info_calls)}회)"
    )


# ---------------------------------------------------------------------------
# E-2: reset_price_filter_daily_state() + scheduler _reset_daily_state 동행
# ---------------------------------------------------------------------------
def test_E2_reset_clears_cap_and_scheduler_reset_calls_it():
    """E-2: (a) `reset_price_filter_daily_state()` 호출 → cap dict clear /
    (b) `scheduler._reset_daily_state()` 가 `scanner.reset_price_filter_daily_state()` 동행 호출.

    CLAUDE.md 절대 규칙 — `_reset_daily_state` 동행 reset 의무.
    """
    from src.engine import scanner

    # === (a) cap clear 동작 ===
    # 사전 데이터 주입 — `_price_filter_scanner_skip_logged_today` cap 에 ticker add
    cap = scanner._price_filter_scanner_skip_logged_today  # Red: 필드 미존재 → AttributeError
    cap.add("005930")
    cap.add("000660")
    assert "005930" in cap

    # Red: `reset_price_filter_daily_state` 미존재 → AttributeError 정답
    scanner.reset_price_filter_daily_state()

    # 사후 — cap 빈 상태
    cap_after = scanner._price_filter_scanner_skip_logged_today
    assert "005930" not in cap_after, "cap clear 결함 — 다음 영업일까지 잔류 위험"
    assert "000660" not in cap_after

    # === (b) scheduler._reset_daily_state 가 동행 호출 ===
    from src.engine import scheduler
    src_reset = inspect.getsource(scheduler.TradingScheduler._reset_daily_state)
    # 정적 검증 — `reset_price_filter_daily_state` 또는 `scanner.reset_price_filter` 호출 존재
    assert (
        "reset_price_filter_daily_state" in src_reset
        or "scanner.reset_price_filter" in src_reset
    ), (
        "scheduler._reset_daily_state() 가 scanner.reset_price_filter_daily_state() "
        "동행 호출 누락 — CLAUDE.md 절대 규칙 위반 (다음 영업일 cap 잔류 위험)"
    )
