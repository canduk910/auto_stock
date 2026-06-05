"""사이클 62 (2026-06-05) Red — C 카테고리: emit cap (2 케이스).

> **선행 명세**: `_workspace/red/cycle62_price_filter.md` (§C)
> **설계 카드**: §2.4 emit cap 정책
> **선례**: 사이클 31 R6 `_risk_silent_skip_logged_today` (`DailyEmitCap[tuple[str, str]]`)
> 사이클 56-D `RiskManager.reset_daily_state` 위임 패턴

요구 행위 (Red 단계 AttributeError 정답 — emit cap 2 종 필드 미존재):

C-1: 같은 (ticker, strategy) 쌍은 1회/일만 emit (cap 동작 검증)
C-2: `reset_daily_state()` 호출 후 cap 2 종 동행 reset (다음 영업일 emit 재개)

회귀 가드:
- CLAUDE.md 절대 규칙: `_reset_daily_state` 동행 reset 의무
- 사이클 56-D 패턴 답습 — `_risk_silent_skip_logged_today.clear()` 옆에 신규 2 종 추가
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_risk_manager():
    from src.engine.order_engine import OrderEngine
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    order_engine = MagicMock(spec=OrderEngine)
    rm = RiskManager(registry=registry, order_engine=order_engine)
    return rm


# ---------------------------------------------------------------------------
# C-1: 같은 (ticker, strategy) 1회/일만 emit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_C1_emit_skip_capped_once_per_day():
    """C-1: 같은 (ticker, strategy) 쌍 100회 호출 시 emit 1회만 (cap 동작).

    `_price_filter_skip_logged_today: DailyEmitCap[tuple[str, str]]` 필드가
    매 틱 폭주 차단. 사이클 31 R6 `_risk_silent_skip_logged_today` 답습.
    """
    rm = _make_risk_manager()

    # Red 단계 — 필드 자체가 없음 → AttributeError 정답
    cap = rm._price_filter_skip_logged_today  # noqa: F841

    with patch("src.engine.risk.logger") as mock_logger, \
         patch("src.db.system_logs.write_log", AsyncMock()):
        # 같은 (005930, momentum) 100회 호출
        from src.db.system_config import PriceFilter
        pf = PriceFilter(min_price=5000, max_price=0, mode="HARD")

        for _ in range(100):
            await rm._emit_price_filter_skip(
                ticker="005930",
                strategy_id="momentum",
                reason="below_min",
                ref_price=3000,
                price_filter=pf,
            )

    # logger.info 호출 1회만 (cap 동작)
    info_calls = [c for c in mock_logger.info.call_args_list
                  if "[price_filter_skip]" in str(c)]
    assert len(info_calls) == 1, (
        f"emit cap 위반 — 100회 호출 시 1회만 emit 해야 함 (실제 {len(info_calls)}회)"
    )


# ---------------------------------------------------------------------------
# C-2: reset_daily_state 동행 reset (cap 2 종)
# ---------------------------------------------------------------------------
def test_C2_reset_daily_state_clears_cap_two_kinds():
    """C-2: `reset_daily_state()` 호출 후 `_price_filter_skip_logged_today` +
    `_price_filter_warn_logged_today` 모두 초기화.

    회귀 가드: CLAUDE.md 절대 규칙 — `_reset_daily_state` 동행 reset.
    사이클 56-D 패턴 답습 (기존 `_risk_silent_skip_logged_today.clear()` 옆 2 줄 추가).
    """
    rm = _make_risk_manager()

    # Red 단계 — 두 필드 자체 미존재 → AttributeError 정답
    # 더미 데이터 주입
    rm._price_filter_skip_logged_today.add(("005930", "momentum"))
    rm._price_filter_skip_logged_today.add(("000660", "volatility_breakout"))
    rm._price_filter_warn_logged_today.add(("005930", "momentum"))
    rm._price_filter_warn_logged_today.add(("035720", "long_tail_volatility"))

    # 사전 검증 — 데이터 주입 확인
    assert ("005930", "momentum") in rm._price_filter_skip_logged_today
    assert ("005930", "momentum") in rm._price_filter_warn_logged_today

    # 호출
    rm.reset_daily_state()

    # 사후 검증 — 두 cap 모두 빈 상태
    assert ("005930", "momentum") not in rm._price_filter_skip_logged_today, (
        "_price_filter_skip_logged_today reset 누락 — 다음 영업일까지 잔류 위험"
    )
    assert ("005930", "momentum") not in rm._price_filter_warn_logged_today, (
        "_price_filter_warn_logged_today reset 누락 — 다음 영업일까지 잔류 위험"
    )
    # 기존 사이클 31 R6 동행 reset 보존 확인 (회귀 가드)
    assert len(rm._risk_silent_skip_logged_today) == 0
