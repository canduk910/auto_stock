"""사이클 62 (2026-06-05) Red — B 카테고리: `risk.on_tick` 가격 필터 분기 (4 케이스).

> **선행 명세**: `_workspace/red/cycle62_price_filter.md` (§B)
> **설계 카드**: §2.3 risk.on_tick 필터 적용 코드 sketch
> **선례**: `tests/unit/engine/test_buy_block_low_funds.py` 등 risk.on_tick 분기 패턴 답습

요구 행위 (Red 단계 모두 AttributeError 정답 — `_get_price_filter_cached` 미구현):

B-1: mode=OFF 시 필터 미적용 → 매수 진행 (execute_buy 호출됨)
B-2: mode=HARD + 범위 외 → 매수 차단 (execute_buy 미호출 + `_emit_price_filter_skip` 호출)
B-3: mode=HARD + 범위 내 → 매수 진행
B-4: `check_exit_signal` 분기 *전* 진입 (매도 차단 0 — 사이클 38 명문화)

**사이클 38 명문화 (CLAUDE.md)**:
- `tradable_boards` 매수 진입 전용 → 매도/익일청산/손절/Trailing/15:20 강제청산은 영향 0
- `check_exit_signal` 분기는 `on_tick` line 103 의 `if state.has_position(ticker):` 안쪽
- 가격 필터는 line 192 `signal = strategy.check_buy_signal` *전* 진입 (line 165 이후)

회귀 가드: B-4 가 사이클 38 명문화 영속 검증.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 공용 헬퍼
# ---------------------------------------------------------------------------
def _make_risk_manager():
    """RiskManager 인스턴스 + 단일 strategy + OrderEngine mock."""
    from src.engine.order_engine import OrderEngine
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    order_engine = MagicMock(spec=OrderEngine)
    order_engine.execute_buy = AsyncMock()
    order_engine.execute_sell = AsyncMock()
    order_engine._selling = set()

    rm = RiskManager(registry=registry, order_engine=order_engine)
    return rm, registry, order_engine


def _make_strategy(strategy_id="momentum"):
    """단일 전략 mock — has_position=False, check_buy_signal=BUY."""
    from src.engine.strategy_base import Signal

    strat = MagicMock()
    strat.strategy_id = strategy_id
    strat.config = MagicMock(params={})
    state = MagicMock()
    state.has_position = MagicMock(return_value=False)
    state.positions = {}
    state.buy_disabled = False
    state.is_low_funds_blocked = MagicMock(return_value=False)
    state.is_buy_blocked = MagicMock(return_value=False)
    state.total_investment = 100_000_000  # 1억 — current_price > total 가드 우회
    state.signal_count_today = 0
    strat.state = state
    strat.is_daily_loss_exceeded = MagicMock(return_value=False)
    strat.check_buy_signal = MagicMock(return_value=Signal.BUY)
    strat.check_exit_signal = MagicMock(return_value=Signal.NONE)
    return strat


def _patch_common_guards(monkeypatch):
    """공통 가드 mock — session_tracker / market_regime / registry guard."""
    from src.engine.market_regime import BuyBlockState

    monkeypatch.setattr(
        "src.engine.risk.session_tracker.is_tradable",
        MagicMock(return_value=True),
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
# B-1: mode=OFF — 필터 미적용 매수 진행
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B1_mode_off_allows_buy(monkeypatch):
    """B-1: 가격 필터 mode=OFF 시 필터 미적용 + 매수 진행 (execute_buy 호출).

    `is_active=False` 분기 → `_get_price_filter_cached` 호출 후 즉시 skip.
    """
    from src.db.system_config import PriceFilter  # Red: ImportError
    from src.engine import risk as risk_mod

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy("momentum")
    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    monkeypatch.setattr(registry, "is_ticker_blocked_for_buy", MagicMock(return_value=False))

    _patch_common_guards(monkeypatch)

    # 가격 필터 OFF (비활성)
    pf_off = PriceFilter(min_price=0, max_price=0, mode="OFF")
    monkeypatch.setattr(
        rm, "_get_price_filter_cached", AsyncMock(return_value=pf_off),
        raising=False,  # Red 단계 미존재 호환
    )

    # 가격 = 3,000원 (저가주 영역)
    await rm.on_tick("005930", current_price=3000, open_price=2900, change_rate=3.0)

    order_engine.execute_buy.assert_called_once()
    args, _kwargs = order_engine.execute_buy.call_args
    assert args[0] == "005930"


# ---------------------------------------------------------------------------
# B-2: mode=HARD + 범위 외 → 매수 차단
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B2_mode_hard_below_min_blocks_buy(monkeypatch):
    """B-2: HARD + min=5000 + ref_price=3000 (저가주) → 매수 차단.

    `execute_buy` 호출 0건 + `_emit_price_filter_skip` 호출 1건 검증.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy("momentum")
    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    monkeypatch.setattr(registry, "is_ticker_blocked_for_buy", MagicMock(return_value=False))
    _patch_common_guards(monkeypatch)

    # 가격 필터 HARD + min=5000
    pf_hard = PriceFilter(min_price=5000, max_price=0, mode="HARD")
    monkeypatch.setattr(
        rm, "_get_price_filter_cached", AsyncMock(return_value=pf_hard), raising=False,
    )
    emit_skip_mock = AsyncMock()
    monkeypatch.setattr(rm, "_emit_price_filter_skip", emit_skip_mock, raising=False)

    # prev_close=3000 (저가주, min=5000 미달)
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 3000})

    await rm.on_tick("005930", current_price=3000, open_price=2900, change_rate=3.0)

    # 매수 차단 검증
    order_engine.execute_buy.assert_not_called()
    # skip emit 호출 1건
    emit_skip_mock.assert_called_once()


# ---------------------------------------------------------------------------
# B-3: mode=HARD + 범위 내 → 매수 진행
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B3_mode_hard_within_range_allows_buy(monkeypatch):
    """B-3: HARD + min=5000 + max=1_000_000 + ref_price=50_000 → 매수 진행.

    필터 통과 = `execute_buy` 호출됨.
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy("momentum")
    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    monkeypatch.setattr(registry, "is_ticker_blocked_for_buy", MagicMock(return_value=False))
    _patch_common_guards(monkeypatch)

    pf_hard = PriceFilter(min_price=5000, max_price=1_000_000, mode="HARD")
    monkeypatch.setattr(
        rm, "_get_price_filter_cached", AsyncMock(return_value=pf_hard), raising=False,
    )
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 50_000})

    await rm.on_tick("005930", current_price=50_000, open_price=49_000, change_rate=2.0)

    order_engine.execute_buy.assert_called_once()


# ---------------------------------------------------------------------------
# B-4: check_exit_signal 분기 *전* 진입 (매도 차단 0 — 사이클 38 명문화)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B4_exit_signal_evaluated_before_price_filter(monkeypatch):
    """B-4: 보유 종목 + check_exit_signal=STOP_LOSS + 가격 필터 HARD 활성 시
    매도 정상 발화 (필터 무관) — 사이클 38 명문화 영속 검증.

    구현 위치 의무: 가격 필터 가드는 `check_exit_signal` 분기 *후*,
    즉 `for strategy:` 루프 안쪽의 `if state.has_position(...)` 분기를 거친 *다음에*
    진입해야 한다 (사이클 38 — `tradable_boards` 매수 진입 전용).
    """
    from src.db.system_config import PriceFilter
    from src.engine import scanner
    from src.engine.strategy_base import Position, Signal

    rm, registry, order_engine = _make_risk_manager()
    strat = _make_strategy("momentum")

    # 보유 종목 시뮬레이션
    pos = Position(
        ticker="005930", buy_price=50_000, quantity=10,
        order_no="A001", strategy_id="momentum", buy_date="2026-06-05",
    )
    strat.state.has_position = MagicMock(return_value=True)
    strat.state.positions = {"005930": pos}
    strat.check_exit_signal = MagicMock(return_value=Signal.STOP_LOSS)

    monkeypatch.setattr(registry, "enabled", MagicMock(return_value=[strat]))
    monkeypatch.setattr(registry, "is_ticker_blocked_for_buy", MagicMock(return_value=False))
    _patch_common_guards(monkeypatch)

    # 필터 HARD min=10_000 — 만약 매도 분기 *전* 평가되면 차단 → 사이클 38 위반
    pf_hard = PriceFilter(min_price=10_000, max_price=0, mode="HARD")
    monkeypatch.setattr(
        rm, "_get_price_filter_cached", AsyncMock(return_value=pf_hard), raising=False,
    )
    # ref_price=3000 (필터 범위 외 — 만약 필터가 매도 분기 *전* 진입하면 매도 차단됨)
    monkeypatch.setattr(scanner, "ticker_prev_close", {"005930": 3000})

    await rm.on_tick("005930", current_price=3000, open_price=2900, change_rate=-40.0)

    # 매도 정상 발화 검증 — 가격 필터에 무관
    order_engine.execute_sell.assert_called_once()
    args, _kwargs = order_engine.execute_sell.call_args
    assert args[0] == "005930"
    assert args[1] == Signal.STOP_LOSS
