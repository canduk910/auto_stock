"""전략 1주 폴백의 잔여 자금 가드 — 회귀 테스트.

결함:
4개 전략의 calc_buy_quantity() 1주 폴백이 state.total_investment(고정 총액)와
current_price를 직접 비교 → 동일 전략이 이미 다른 종목에 자금을 거의 다 쓴 뒤에도
"총 할당 >= 1주 가격"이면 1주 추가 매수 → 전략 한도 초과.

수정 후 동작:
폴백 = StrategyBase._fallback_one_share(current_price) 공통 헬퍼
  used = sum(buy_price*qty for pos in positions) + sum(pending_buy_amounts.values())
  remaining = state.total_investment - used
  return 1 if remaining >= current_price else 0

4개 전략(momentum / volatility_breakout / long_tail_volatility / donchian_swing)
모두 동일 헬퍼 호출 — 정책 통합 + 중복 제거.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, StrategyBase, StrategyConfig

pytestmark = pytest.mark.unit


STRATEGY_CLASSES = [
    ("momentum", MomentumStrategy),
    ("volatility_breakout", VolatilityBreakoutStrategy),
    ("long_tail_volatility", LongTailVolatilityStrategy),
    ("donchian_swing", DonchianSwingStrategy),
]


def _build(strategy_id: str, cls):
    """할당 자금 비중 25% 균일 가정한 전략 인스턴스."""
    cfg = StrategyConfig(strategy_id=strategy_id, name=strategy_id, weight=0.25)
    return cls(cfg)


# ---------------------------------------------------------------------------
# Case A — 신규 전략, 사용액 0 → 1주 매수 (기존 동작 유지)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", STRATEGY_CLASSES)
def test_fallback_when_no_usage_then_returns_one(strategy_id, cls):
    """사용액 0 + 비중계산 0주 + 잔여(=total) >= 가격 → 1주 폴백."""
    s = _build(strategy_id, cls)
    # total=1M, ratio≈0.1~0.25 → amount=100k~250k. 가격 1주에 800k → 비중 기준 0주.
    s.state.total_investment = 1_000_000
    assert s.calc_buy_quantity(current_price=800_000) == 1


# ---------------------------------------------------------------------------
# Case B — 보유 포지션으로 사용액 90% → 잔여 < 가격 → 0주 (수정 후 동작)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", STRATEGY_CLASSES)
def test_fallback_when_positions_consume_most_funds_then_returns_zero(
    strategy_id, cls,
):
    """동일 전략이 이미 다른 종목에 자금 90% 점유 → 1주 가격 > 잔여 → 0주.

    `current_price=600_000` 으로 모든 전략 비중계산이 0주가 되도록 강제
    (momentum 25%×1M=250k / VB·LTV 10%×1M=100k / donchian 20%×1M=200k 모두 < 600k).
    """
    s = _build(strategy_id, cls)
    s.state.total_investment = 1_000_000
    # 보유 포지션 사용액 = 900,000
    s.state.positions["000001"] = Position(
        ticker="000001",
        buy_price=90_000,
        quantity=10,
        order_no="ORD1",
        strategy_id=strategy_id,
    )
    # 잔여 = 100,000 < 600,000 → 폴백도 0주 반환해야 함 (기존 결함: 1주 반환했었음)
    assert s.calc_buy_quantity(current_price=600_000) == 0


# ---------------------------------------------------------------------------
# Case C — pending_buys 로 사용액 90% → 잔여 < 가격 → 0주 (race 가드)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", STRATEGY_CLASSES)
def test_fallback_when_pending_buys_consume_most_funds_then_returns_zero(
    strategy_id, cls,
):
    """매수 주문중 종목으로 자금 90% 점유 → 잔여 < 가격 → 0주 (race 가드)."""
    s = _build(strategy_id, cls)
    s.state.total_investment = 1_000_000
    # 매수 주문중 (체결 전) — pending_buys set + pending_buy_amounts dict 동기 등록
    s.state.pending_buys.add("000002")
    s.state.pending_buy_amounts["000002"] = 900_000
    # 잔여 = 100,000 < 600,000 → 폴백 0주
    assert s.calc_buy_quantity(current_price=600_000) == 0


# ---------------------------------------------------------------------------
# Case D — 4개 전략 모두 _fallback_one_share 공통 헬퍼 호출
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", STRATEGY_CLASSES)
def test_fallback_uses_common_helper(strategy_id, cls):
    """비중계산 0주 시 StrategyBase._fallback_one_share 가 호출됨을 검증."""
    s = _build(strategy_id, cls)
    s.state.total_investment = 10_000  # 비중계산 0주 강제 (어떤 ratio든 < 가격)
    sentinel = 42

    with patch.object(
        StrategyBase, "_fallback_one_share", return_value=sentinel,
    ) as mock_helper:
        result = s.calc_buy_quantity(current_price=100_000_000)

    assert result == sentinel
    mock_helper.assert_called_once_with(100_000_000)


# ---------------------------------------------------------------------------
# Case E — 다른 전략 사용액은 자기 전략 폴백에 영향 없음 (격리)
# ---------------------------------------------------------------------------
def test_fallback_isolated_per_strategy_state():
    """A 전략에 사용액 90% 등록해도 B 전략 폴백은 자기 잔여만 본다."""
    momentum = _build("momentum", MomentumStrategy)
    vb = _build("volatility_breakout", VolatilityBreakoutStrategy)

    # momentum 90% 사용 (다른 전략 노이즈)
    momentum.state.total_investment = 1_000_000
    momentum.state.positions["000001"] = Position(
        ticker="000001",
        buy_price=90_000,
        quantity=10,
        order_no="MOM1",
        strategy_id="momentum",
    )

    # VB 는 깨끗한 상태 — total 1M, 사용액 0. ratio=10% → amount=100k, qty=0
    vb.state.total_investment = 1_000_000

    # VB 입장에서 잔여 = 1M >= 600k → 1주 폴백 가능해야 함 (momentum 사용액 영향 없음)
    assert vb.calc_buy_quantity(current_price=600_000) == 1


# ---------------------------------------------------------------------------
# StrategyBase 헬퍼 직접 검증 — used_funds 계산 정확성
# ---------------------------------------------------------------------------
def test_calc_used_funds_combines_positions_and_pending_amounts():
    """_calc_used_funds = positions buy_price*qty 합 + pending_buy_amounts 합."""
    s = _build("momentum", MomentumStrategy)
    s.state.total_investment = 5_000_000

    # 포지션 2개: 50k×4 + 30k×10 = 200k + 300k = 500k
    s.state.positions["000001"] = Position(
        ticker="000001", buy_price=50_000, quantity=4,
        order_no="O1", strategy_id="momentum",
    )
    s.state.positions["000002"] = Position(
        ticker="000002", buy_price=30_000, quantity=10,
        order_no="O2", strategy_id="momentum",
    )

    # pending 2개: 150k + 250k = 400k
    s.state.pending_buys.add("000003")
    s.state.pending_buy_amounts["000003"] = 150_000
    s.state.pending_buys.add("000004")
    s.state.pending_buy_amounts["000004"] = 250_000

    assert s._calc_used_funds() == 900_000


def test_fallback_one_share_returns_one_when_remaining_equals_price():
    """잔여 == 가격 경계: >= 비교 (1주 매수 가능)."""
    s = _build("momentum", MomentumStrategy)
    s.state.total_investment = 100_000
    # 사용액 0, 잔여 100k == 가격 100k → 1주
    assert s._fallback_one_share(current_price=100_000) == 1


def test_fallback_one_share_returns_zero_when_remaining_below_price():
    """잔여 < 가격 → 0주."""
    s = _build("momentum", MomentumStrategy)
    s.state.total_investment = 100_000
    s.state.positions["X"] = Position(
        ticker="X", buy_price=50_000, quantity=1,
        order_no="O", strategy_id="momentum",
    )
    # 잔여 = 50k < 60k 가격 → 0주
    assert s._fallback_one_share(current_price=60_000) == 0
