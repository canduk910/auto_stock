"""사이클 62 (2026-06-05) Red — G 카테고리: WARN 모드 (2 케이스, 자문 +2).

> **선행 명세**: `_workspace/red/cycle62_price_filter.md` (§G)
> **자문 응답 Q4**: 3 모드 (HARD/WARN/OFF) + 디폴트 OFF
> **선례**: 사이클 8 `buy_block_mode` WARN 패턴 (`[buy_block_warn]` WARNING 로그 emit) 답습

요구 행위 (Red 단계 AttributeError 정답 — `_price_filter_warn_logged_today` 미존재):

G-1: mode=WARN + 범위 외 → 매수 진행 + `[price_filter_warn]` WARNING 로그
G-2: WARN 모드 emit cap 적용 (skip cap 과 별도) — 같은 (ticker, strategy) 1회/일

자문 근거: 신규 가드 *시장 신뢰 형성* 패턴 (WARN 1주 → HARD 전환 단계적 도입).
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_risk_manager():
    from src.engine.order_engine import OrderEngine
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    order_engine = MagicMock(spec=OrderEngine)
    order_engine.execute_buy = AsyncMock()
    order_engine._selling = set()
    rm = RiskManager(registry=registry, order_engine=order_engine)
    return rm, registry, order_engine


def _make_strategy(strategy_id="momentum"):
    from src.engine.strategy_base import Signal

    strat = MagicMock()
    strat.strategy_id = strategy_id
    strat.config = MagicMock(params={})
    state = MagicMock()
    state.has_position = MagicMock(return_value=False)
    state.positions = {}
    state.buy_disabled = False
    state.is_low_funds_blocked = MagicMock(return_value=False)
    state.total_investment = 100_000_000
    state.signal_count_today = 0
    strat.state = state
    strat.is_daily_loss_exceeded = MagicMock(return_value=False)
    strat.check_buy_signal = MagicMock(return_value=Signal.BUY)
    return strat


def _patch_common(monkeypatch, registry):
    from src.engine.market_regime import BuyBlockState

    monkeypatch.setattr(registry, "is_ticker_blocked_for_buy", MagicMock(return_value=False))
    monkeypatch.setattr(
        "src.engine.risk.session_tracker.is_tradable", MagicMock(return_value=True),
    )
    monkeypatch.setattr(
        "src.engine.risk.get_current_regime",
        lambda: MagicMock(
            get_buy_block_state=AsyncMock(
                return_value=BuyBlockState(
                    mode="OFF", blocked=False, soft_multiplier=1.0, reasons=[],
                ),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# G-1: WARN 모드 + 범위 외 → 매수 허용 + WARNING 로그
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G1_warn_mode_allows_buy_with_warning_log(
    monkeypatch, caplog: pytest.LogCaptureFixture,
):
    """G-1: WARN + min=10_000 + ref_price=3000 (범위 외) → 매수 진행 + `[price_filter_warn]`
    WARNING 로그 emit.

    사이클 31 buy_block_mode WARN 답습 (매수 허용 + 사후 가시화).
    logger 명시 binding: `src.engine.risk` (사이클 60/61 패턴 답습).
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy("momentum")
    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    _patch_common(monkeypatch, registry)

    pf_warn = PriceFilter(min_price=10_000, max_price=0, mode="WARN")
    monkeypatch.setattr(
        rm, "_get_price_filter_cached", AsyncMock(return_value=pf_warn), raising=False,
    )
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 3000})

    caplog.set_level(logging.WARNING, logger="src.engine.risk")

    with patch("src.db.system_logs.write_log", AsyncMock()):
        await rm.on_tick("005930", current_price=3000, open_price=2900, change_rate=3.0)

    # 매수 정상 진행 (WARN 모드 = 허용)
    order_engine.execute_buy.assert_called_once()
    # WARNING 로그 emit (`[price_filter_warn]` prefix)
    warn_logs = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and "[price_filter_warn]" in r.message
    ]
    assert len(warn_logs) == 1, (
        f"WARN 모드 [price_filter_warn] WARNING 로그 누락 (실제 {len(warn_logs)}건)"
    )


# ---------------------------------------------------------------------------
# G-2: WARN cap 적용 — 같은 (ticker, strategy) 1회/일
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_G2_warn_mode_cap_per_pair_per_day(monkeypatch):
    """G-2: 같은 (ticker, strategy) 쌍 100회 호출 시 WARN emit 1회만.

    `_price_filter_warn_logged_today: DailyEmitCap[tuple[str, str]]` 필드 cap.
    skip cap (`_price_filter_skip_logged_today`) 과 별도 추적.
    """
    rm, _, _ = _make_risk_manager()

    # Red: 두 필드 모두 미존재 — AttributeError 정답
    _ = rm._price_filter_warn_logged_today  # noqa: F841

    with patch("src.engine.risk.logger") as mock_logger, \
         patch("src.db.system_logs.write_log", AsyncMock()):
        from src.db.system_config import PriceFilter
        pf = PriceFilter(min_price=10_000, max_price=0, mode="WARN")

        for _ in range(100):
            await rm._emit_price_filter_warn(
                ticker="005930",
                strategy_id="momentum",
                reason="below_min",
                ref_price=3000,
                price_filter=pf,
            )

    warn_calls = [c for c in mock_logger.warning.call_args_list
                  if "[price_filter_warn]" in str(c)]
    assert len(warn_calls) == 1, (
        f"WARN emit cap 위반 — 100회 호출 시 1회만 emit (실제 {len(warn_calls)}회)"
    )
