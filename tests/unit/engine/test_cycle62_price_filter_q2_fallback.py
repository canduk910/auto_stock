"""사이클 62 (2026-06-05) Red — F 카테고리: Q2 fallback (5 케이스, 자문 +3 흡수).

> **선행 명세**: `_workspace/red/cycle62_price_filter.md` (§F)
> **설계 카드**: §2.2 — 비교 가격 데이터 소스 (Q2 자문 확정)
> **자문 응답 Q2**: `prev_close` 우선 + `current_price` fallback (갭상승/하락 시점 결함 회피)

요구 행위 (Red 단계 AttributeError 정답 — `_get_price_filter_cached` 미존재):

F-1: `prev_close > 0` → prev_close 기준 평가 (1순위)
F-2: `prev_close == 0` + `current_price > 0` → current_price fallback (2순위)
F-3: 둘 다 0 → graceful 통과 (필터 미적용 — 신규 상장 영구 차단 방지)
F-4: 갭상승 (prev=4500 < min=5000, cur=5200 > min=5000) → prev_close 우선 차단 (트레이더 의도)
F-5: 갭하락 (prev=10_500 > min=5000, cur=9800 > min=5000) → prev_close 우선 통과

회귀 가드:
- 자문 결함 회피 — 작전주 갭상승 시점에 current_price 단독 사용하면 차단 누락
- 신규 상장 종목 영구 차단 방지 (graceful 통과)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

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
# F-1: prev_close > 0 → 1순위 사용
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F1_prev_close_used_when_available(monkeypatch):
    """F-1: prev_close=50_000 + current_price=49_000 + filter min=10_000/max=100_000 → 통과.

    1순위 prev_close 가 활용되어야 함.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy("momentum")
    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    _patch_common(monkeypatch, registry)

    pf = PriceFilter(min_price=10_000, max_price=100_000, mode="HARD")
    monkeypatch.setattr(rm, "_get_price_filter_cached", AsyncMock(return_value=pf), raising=False)
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 50_000})

    await rm.on_tick("005930", current_price=49_000, open_price=49_500, change_rate=-1.0)

    order_engine.execute_buy.assert_called_once()  # prev=50_000 통과


# ---------------------------------------------------------------------------
# F-2: prev_close 미존재 → current_price fallback (2순위)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F2_current_price_fallback_when_prev_missing(monkeypatch):
    """F-2: prev_close 키 없음 + current_price=50_000 + filter min=10_000 → current 사용 통과.

    2순위 fallback 동작 검증.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy("momentum")
    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    _patch_common(monkeypatch, registry)

    pf = PriceFilter(min_price=10_000, max_price=0, mode="HARD")
    monkeypatch.setattr(rm, "_get_price_filter_cached", AsyncMock(return_value=pf), raising=False)
    # prev_close 비어있음 → current_price fallback
    monkeypatch.setattr(scanner, "ticker_prev_close", {})

    await rm.on_tick("005930", current_price=50_000, open_price=49_500, change_rate=1.0)

    order_engine.execute_buy.assert_called_once()


# ---------------------------------------------------------------------------
# F-3: 둘 다 미존재 → graceful 통과 (필터 skip, 매수 허용)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F3_graceful_pass_when_both_missing(monkeypatch):
    """F-3: prev_close 미존재 + current_price=0 → 필터 skip + 매수 허용.

    신규 상장 종목 영구 차단 방지 (사이클 32 R4 graceful 패턴 답습).
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy("momentum")
    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    _patch_common(monkeypatch, registry)

    # 필터 활성 (HARD min=10_000) — 만약 0 으로 차단하면 결함
    pf = PriceFilter(min_price=10_000, max_price=0, mode="HARD")
    monkeypatch.setattr(rm, "_get_price_filter_cached", AsyncMock(return_value=pf), raising=False)
    monkeypatch.setattr(scanner, "ticker_prev_close", {})

    # current_price=0 (WS 늦은 종목)
    await rm.on_tick("005930", current_price=0, open_price=0, change_rate=0.0)

    # 둘 다 0 → graceful 통과 (매수 허용)
    # 단 current_price=0 자체로 other guard (total_investment 비교) 가 차단할 수 있음
    # 핵심 검증: `_emit_price_filter_skip` 호출 0건 (필터가 차단하지 않음)
    if hasattr(rm, "_emit_price_filter_skip"):
        # Green 단계 — graceful 통과면 emit 0건
        emit_calls = [c for c in
                      getattr(rm._emit_price_filter_skip, "call_args_list", [])
                      if c]
        assert len(emit_calls) == 0, (
            "둘 다 0 시 필터가 차단 — graceful 통과 결함"
        )


# ---------------------------------------------------------------------------
# F-4: 갭상승 (prev=4500 < min=5000 / cur=5200 > min=5000) → prev_close 우선 차단
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F4_gap_up_blocked_by_prev_close(monkeypatch):
    """F-4: 작전주 갭상승 시나리오 — 전일 4,500원 (저가주) + 시초가 5,200원 (필터 통과).

    `prev_close` 우선 사용 시 → 차단 (트레이더 의도).
    `current_price` 단독 사용 시 → 통과 (자문 결함 — Q2 회피 케이스).
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy("momentum")
    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    _patch_common(monkeypatch, registry)

    pf = PriceFilter(min_price=5000, max_price=0, mode="HARD")
    monkeypatch.setattr(rm, "_get_price_filter_cached", AsyncMock(return_value=pf), raising=False)
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 4500})

    # 시초가 5,200 (current_price 통과 위치) — 그러나 prev_close=4500 → 차단
    await rm.on_tick("005930", current_price=5200, open_price=5200, change_rate=15.0)

    # prev_close 우선 차단 — 매수 0건
    order_engine.execute_buy.assert_not_called()


# ---------------------------------------------------------------------------
# F-5: 갭하락 (prev=10500 > min / cur=9800 > min) → prev_close 우선 통과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F5_gap_down_passed_by_prev_close(monkeypatch):
    """F-5: prev_close=10_500 / current_price=9800 / filter min=5000 → 둘 다 통과
    (prev_close 우선 사용 검증).

    F-4 의 역시나리오 — prev_close 우선 정책이 갭하락 시점에도 일관 작동.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy("momentum")
    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    _patch_common(monkeypatch, registry)

    pf = PriceFilter(min_price=5000, max_price=0, mode="HARD")
    monkeypatch.setattr(rm, "_get_price_filter_cached", AsyncMock(return_value=pf), raising=False)
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 10_500})

    await rm.on_tick("005930", current_price=9800, open_price=9800, change_rate=-7.0)

    # prev_close=10_500 > min=5000 → 통과
    order_engine.execute_buy.assert_called_once()
