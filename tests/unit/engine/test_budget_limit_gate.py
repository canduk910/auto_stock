"""전략 예산 이중제한 ② 명목 축 — `StrategyBase._apply_budget_limit` 회귀 가드.

결함 (Part A, D1):
7 전략 `calc_buy_quantity` 의 주 분기가 `int(total_investment × position_ratio) // price`
를 **잔여 검증 없이 반환**했다. 잔여 클램프는 `_fallback_one_share`(비중 기준 0주일 때의
1주 폴백)와 turtle opt-in 분기에만 존재 → `position_ratio × max_positions > 1.0` 인
전략은 전략 예산을 초과 매수할 수 있었다 (라이브 실측: kojiro 2.00 / LTV 2.00,
계좌 전체 122.5% 초과 청약).

시정 후 규약:
    잔여 = total_investment − _calc_used_funds()   (보유 원금 + pending 예정액)
    qty <= 0 → `_fallback_one_share` 위임          (기존 계약 보존)
    qty  > 0 → min(qty, 잔여 // price)             (부분 매수 허용, 잔여<price → 0)

이중제한 = ① 개수 `max_positions`(기존) + ② 명목 `Σ매수금액 ≤ total_investment`(본 관문).

원자성: `order_engine.execute_buy` 는 `calc_buy_quantity` ~ `pending_buys.add` 사이
`await` 0건이라 관문의 read 가 pending 등록까지 원자적이다 (AST 가드가 영구 고정).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, StrategyBase, StrategyConfig

pytestmark = pytest.mark.unit


ALL_STRATEGIES = [
    ("momentum", MomentumStrategy),
    ("volatility_breakout", VolatilityBreakoutStrategy),
    ("long_tail_volatility", LongTailVolatilityStrategy),
    ("donchian_swing", DonchianSwingStrategy),
    ("bull_flag_breakout", BullFlagBreakoutStrategy),
    ("vcp_breakout", VcpBreakoutStrategy),
    ("kojiro", KojiroStrategy),
]

TOTAL = 1_000_000
PRICE = 10_000


def _build(strategy_id: str, cls, total: int = TOTAL):
    cfg = StrategyConfig(strategy_id=strategy_id, name=strategy_id, weight=0.25)
    s = cls(cfg)
    s.state.total_investment = total
    return s


def _consume(s, amount: int) -> None:
    """보유 포지션으로 전략 예산 `amount` 원 사용 처리."""
    s.state.positions["000001"] = Position(
        ticker="000001", buy_price=amount, quantity=1,
        order_no="ORD1", strategy_id=s.strategy_id,
    )


def _ratio_qty(s, price: int = PRICE) -> int:
    """클램프 없을 때의 기존 비중 수량."""
    return int(s.state.total_investment * s.config.params["position_ratio"]) // price


# ---------------------------------------------------------------------------
# A-CLAMP-1 — 잔여 > 요구 → 기존 비중 수량 그대로 (회귀 0)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", ALL_STRATEGIES)
def test_no_clamp_when_budget_available(strategy_id, cls):
    s = _build(strategy_id, cls)
    expected = _ratio_qty(s)
    assert expected > 0, "테스트 전제: 비중 수량 > 0"
    assert s.calc_buy_quantity(PRICE, "005930") == expected


# ---------------------------------------------------------------------------
# A-CLAMP-2 — 잔여 < 요구 → 잔여//price 로 축소 (부분 매수)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", ALL_STRATEGIES)
def test_clamped_to_remaining_budget(strategy_id, cls):
    s = _build(strategy_id, cls)
    _consume(s, 950_000)          # 잔여 50,000 → 5주
    assert _ratio_qty(s) > 5, "테스트 전제: 비중 수량이 잔여 수량보다 커야 클램프가 관측됨"
    assert s.calc_buy_quantity(PRICE, "005930") == 5


# ---------------------------------------------------------------------------
# A-CLAMP-3 — 잔여 < 1주 가격 → 0 (진입 스킵)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", ALL_STRATEGIES)
def test_zero_when_remaining_below_one_share(strategy_id, cls):
    s = _build(strategy_id, cls)
    _consume(s, 995_000)          # 잔여 5,000 < 10,000
    assert s.calc_buy_quantity(PRICE, "005930") == 0


# ---------------------------------------------------------------------------
# A-CLAMP-4 — 잔여 음수(예산 초과 보유) → 0 (음수 나눗셈 사고 차단)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", ALL_STRATEGIES)
def test_zero_when_remaining_negative(strategy_id, cls):
    s = _build(strategy_id, cls)
    _consume(s, 1_500_000)        # 잔여 −500,000
    assert s.calc_buy_quantity(PRICE, "005930") == 0


# ---------------------------------------------------------------------------
# A-CLAMP-5 — pending_buy_amounts 도 사용액에 포함 (체결 전 race 가드)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", ALL_STRATEGIES)
def test_pending_amounts_count_as_used(strategy_id, cls):
    s = _build(strategy_id, cls)
    s.state.pending_buys.add("000002")
    s.state.pending_buy_amounts["000002"] = 950_000
    assert s.calc_buy_quantity(PRICE, "005930") == 5


# ---------------------------------------------------------------------------
# A-INV — 불변식: 연속 매수 시퀀스에서 Σ(price×qty) ≤ total_investment
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", ALL_STRATEGIES)
@pytest.mark.parametrize("price", [1_000, 7_700, 33_333, 250_000])
def test_invariant_never_exceeds_strategy_budget(strategy_id, cls, price):
    """max_positions 를 무시하고 20회 연속 체결시켜도 예산을 넘지 않는다."""
    s = _build(strategy_id, cls)
    spent = 0
    for i in range(20):
        qty = s.calc_buy_quantity(price, f"{i:06d}")
        if qty <= 0:
            break
        spent += price * qty
        s.state.positions[f"{i:06d}"] = Position(
            ticker=f"{i:06d}", buy_price=price, quantity=qty,
            order_no=f"O{i}", strategy_id=strategy_id,
        )
    assert spent <= s.state.total_investment, (
        f"{strategy_id} 예산 초과: spent={spent} > budget={s.state.total_investment}"
    )


# ---------------------------------------------------------------------------
# A-ISOLATE — 전략 간 격리 (A 의 사용액이 B 의 관문에 영향 0)
# ---------------------------------------------------------------------------
def test_budget_gate_is_strategy_isolated():
    a = _build("kojiro", KojiroStrategy)
    b = _build("vcp_breakout", VcpBreakoutStrategy)
    _consume(a, 999_999)
    assert a.calc_buy_quantity(PRICE, "005930") == 0
    assert b.calc_buy_quantity(PRICE, "005930") == _ratio_qty(b)


# ---------------------------------------------------------------------------
# A-FALLBACK — qty<=0 경로는 여전히 `_fallback_one_share` 위임 (분기 순서 계약)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", ALL_STRATEGIES)
def test_fallback_helper_still_invoked_for_zero_ratio_qty(strategy_id, cls):
    s = _build(strategy_id, cls, total=10_000)   # 비중 수량 0 강제
    sentinel = 42
    with patch.object(
        StrategyBase, "_fallback_one_share", return_value=sentinel,
    ) as mock_helper:
        result = s.calc_buy_quantity(100_000_000, "005930")
    # cycle245 — 위임은 그대로이나 반환값은 ρ캡을 통과한다. 모킹된 42주 × 1억원 =
    # ρ상한의 천문학적 배수라 캡이 0 으로 자른다(§3-7 "모든 랏" 계약의 직접 증거).
    # 헬퍼 반환값이 그대로 유통되는 계약은 `test_cycle245_ratio_notional_cap.py`
    # F-14 가 캡 비바인딩 조건에서 강하게 검증한다. 이 테스트의 진짜 계약은
    # **분기 순서/위임**(아래 assert_called_once_with)이므로 그것은 무변경.
    assert sentinel == 42
    assert result == 0
    mock_helper.assert_called_once_with(100_000_000)


# ---------------------------------------------------------------------------
# A-PRICE0 — current_price <= 0 → 0 (기존 계약 보존)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strategy_id,cls", ALL_STRATEGIES)
def test_zero_price_returns_zero(strategy_id, cls):
    s = _build(strategy_id, cls)
    assert s.calc_buy_quantity(0, "005930") == 0
    assert s.calc_buy_quantity(-100, "005930") == 0


# ---------------------------------------------------------------------------
# A-KOJIRO-0 — D2 회귀: turtle + 예산 완전 소진 → 0
#   (기존 결함: `min(unit_qty, budget_qty) if budget_qty > 0 else unit_qty`
#    → 잔여 0 일 때 클램프가 해제되고 풀 유닛이 통과했다 = fail-open 반전)
# ---------------------------------------------------------------------------
def test_kojiro_turtle_returns_zero_when_budget_exhausted():
    s = _build("kojiro", KojiroStrategy)
    s.config.params["sizing_mode"] = "turtle"
    s.config.params["risk_pct"] = 0.005
    s._candidates["005930"] = {"atr": 500.0}     # atr/price = 5% (변동성 floor 통과)
    _consume(s, 1_000_000)                       # 잔여 0
    assert s.calc_buy_quantity(PRICE, "005930") == 0


def test_kojiro_turtle_clamped_to_remaining():
    """잔여가 유닛보다 작으면 잔여 수량으로 축소 (부분 매수)."""
    s = _build("kojiro", KojiroStrategy)
    s.config.params["sizing_mode"] = "turtle"
    s.config.params["risk_pct"] = 0.005
    s._candidates["005930"] = {"atr": 500.0}     # unit = 1,000,000×0.005/500 = 10주
    _consume(s, 970_000)                         # 잔여 30,000 → 3주
    assert s.calc_buy_quantity(PRICE, "005930") == 3


# ---------------------------------------------------------------------------
# A-DON-TURTLE — donchian turtle 경로도 동일 관문 통과 (기존 guarded 와 이중 no-op)
# ---------------------------------------------------------------------------
def test_donchian_turtle_respects_budget_gate():
    s = _build("donchian_swing", DonchianSwingStrategy)
    s.config.params["sizing_mode"] = "turtle"
    s.config.params["risk_pct"] = 0.005
    s._candidates["005930"] = {"atr": 500.0}
    _consume(s, 1_000_000)
    assert s.calc_buy_quantity(PRICE, "005930") == 0
