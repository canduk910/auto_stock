"""B-1 — kojiro 터틀 사이징 guarded 전환 회귀 가드.

kojiro 는 청산이 이미 ATR 기반(`hard_stop_pct −8%` → `2×ATR tighten-only floor`
→ stage3 → `2.5ATR 트레일`)인데 사이징만 `position_ratio` 인 "반쪽" 상태였다.
이를 해소하되, unguarded `compute_unit_qty` 를 쓰면 **저변동 종목에서 단일종목
집중이 폭증**한다 — 유닛 명목 비중은 대수적으로 `risk_pct ÷ (ATR/price)` 라
`atr_ratio = 1%` 면 예산의 **50%** 가 한 종목에 들어간다.

따라서 donchian `_turtle_buy_quantity` 와 동일하게 `compute_unit_qty_guarded`
3중 가드(변동성 floor / 잔여 예산 / notional 상한)를 통과시킨다.

핵심 불변식 (B-NARROW): notional 상한이 `position_ratio × 예산` 이므로
**터틀 수량 ≤ position_ratio 수량**이 항상 성립 → 터틀 전환은 순수 축소 방향이고
저ATR 수량 폭증(함정 #1)은 구조적으로 불가능하다. 임계는
`atr_ratio = risk_pct ÷ position_ratio` (기본값 0.005/0.20 = 2.5%) —
그 아래는 상한이 바인딩해 현행과 동일, 그 위에서만 실제로 수량이 줄어든다.

청산 로직은 변경 0 (`_entry_atr` 스냅샷 미도입 — kojiro 는 `_candidates` live ATR +
`_stop_floor` tighten-only 로 loosen 을 이미 차단하며, 스냅샷을 얹으면 tighten
메커니즘이 2원화된다. sizing ATR 과 stop ATR 이 **같은 dict 를 읽는 구조적 동일성**이
커플링 보증).
"""

from __future__ import annotations

import ast
import inspect

import pytest

from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategy_base import Position, StrategyConfig

pytestmark = pytest.mark.unit

BUDGET = 100_000_000
RATIO = 0.20
RISK_PCT = 0.005


def _kojiro(*, turtle: bool = True, budget: int = BUDGET, **extra):
    params = {"risk_pct": RISK_PCT, **extra}
    if turtle:
        params["sizing_mode"] = "turtle"
    s = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.3, params=params),
    )
    s.state.total_investment = budget
    return s


def _pr_qty(budget: int, price: int, ratio: float = RATIO) -> int:
    return int(budget * ratio) // price


# ---------------------------------------------------------------------------
# B1-DEFAULT — min_vol_floor_pct 기본값 존재 (donchian 과 동일 규약)
# ---------------------------------------------------------------------------
def test_min_vol_floor_pct_default_present():
    assert KojiroStrategy.DEFAULT_PARAMS.get("min_vol_floor_pct") == 1.0


# ---------------------------------------------------------------------------
# B1-VOLFLOOR — atr/price < min_vol_floor_pct% → 터틀 0 → position_ratio 낙하
#   (unguarded 였다면 저변동일수록 수량이 폭증했다)
# ---------------------------------------------------------------------------
def test_low_volatility_falls_back_to_position_ratio():
    s = _kojiro()
    price = 50_000
    s._candidates["005930"] = {"atr": 100.0}       # atr/price = 0.2% < 1%
    assert s.calc_buy_quantity(price, "005930") == _pr_qty(BUDGET, price)


def test_volatility_floor_boundary_is_inclusive_above():
    """정확히 1.0% 는 통과 (`<` 비교)."""
    s = _kojiro()
    price = 50_000
    s._candidates["005930"] = {"atr": 500.0}       # 정확히 1.0%
    qty = s.calc_buy_quantity(price, "005930")
    assert qty == _pr_qty(BUDGET, price), "1.0% 는 floor 통과 후 notional 상한이 바인딩"


# ---------------------------------------------------------------------------
# B1-NOTIONAL — 저변동 종목 유닛 명목이 position_ratio × 예산 을 넘지 못한다
#   (unguarded 회귀: atr_ratio 1% → 예산의 50% 단일종목 집중)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("atr_ratio", [0.010, 0.015, 0.020, 0.025])
def test_notional_never_exceeds_position_ratio_budget(atr_ratio):
    s = _kojiro()
    price = 20_000
    s._candidates["005930"] = {"atr": price * atr_ratio}
    qty = s.calc_buy_quantity(price, "005930")
    assert qty * price <= int(BUDGET * RATIO), (
        f"atr_ratio={atr_ratio:.1%} 에서 단일종목 명목 {qty * price:,} 가 "
        f"notional 상한 {int(BUDGET * RATIO):,} 초과"
    )


# ---------------------------------------------------------------------------
# B1-NARROW — 터틀 수량 ≤ position_ratio 수량 (순수 축소 방향, 구조적 안전판)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("atr_ratio", [0.011, 0.02, 0.025, 0.03, 0.04, 0.06])
@pytest.mark.parametrize("price", [5_000, 20_000, 137_000])
def test_turtle_qty_never_exceeds_position_ratio_qty(atr_ratio, price):
    s = _kojiro()
    s._candidates["005930"] = {"atr": price * atr_ratio}
    turtle_qty = s.calc_buy_quantity(price, "005930")
    assert turtle_qty <= max(_pr_qty(BUDGET, price), 1), (
        "터틀 전환이 position_ratio 대비 수량을 늘렸습니다 — 함정 #1 재발"
    )


def test_turtle_reduces_qty_above_threshold():
    """`atr_ratio > risk_pct/position_ratio`(=2.5%) 에서는 실제로 수량이 줄어든다."""
    s = _kojiro()
    price = 20_000
    s._candidates["005930"] = {"atr": price * 0.05}   # 5% > 2.5%
    assert s.calc_buy_quantity(price, "005930") < _pr_qty(BUDGET, price)


# ---------------------------------------------------------------------------
# B1-BUDGET — 잔여 예산 클램프 (예산 소진 시 0, 부분 잔여 시 축소)
# ---------------------------------------------------------------------------
def test_budget_clamp_binds():
    s = _kojiro(budget=1_000_000)
    price = 10_000
    s._candidates["005930"] = {"atr": 200.0}      # 2% ≥ floor, unit = 5000/200 = 25
    s.state.positions["000001"] = Position(
        ticker="000001", buy_price=900_000, quantity=1,
        order_no="O", strategy_id="kojiro",
    )                                              # 잔여 100,000 → 10주
    assert s.calc_buy_quantity(price, "005930") == 10


def test_budget_exhausted_returns_zero():
    s = _kojiro(budget=1_000_000)
    s._candidates["005930"] = {"atr": 200.0}
    s.state.positions["000001"] = Position(
        ticker="000001", buy_price=1_000_000, quantity=1,
        order_no="O", strategy_id="kojiro",
    )
    assert s.calc_buy_quantity(10_000, "005930") == 0


# ---------------------------------------------------------------------------
# B1-INV — 유닛 리스크 정규화: qty × ATR ≈ 예산 × risk_pct (클램프 미발동 구간)
# ---------------------------------------------------------------------------
def test_unit_risk_invariant_when_no_clamp():
    s = _kojiro()
    price = 10_000
    atr = 3_000.0                                   # 30% — floor·상한 모두 미발동
    s._candidates["005930"] = {"atr": atr}
    qty = s.calc_buy_quantity(price, "005930")
    assert abs(qty * atr - BUDGET * RISK_PCT) < atr


# ---------------------------------------------------------------------------
# B1-FALLBACK — 실패 경로는 전부 position_ratio 낙하 (fail-open 보존)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("setup", ["no_candidate", "atr_zero", "ticker_none", "mode_off"])
def test_fail_open_paths(setup):
    price = 10_000
    if setup == "mode_off":
        s = _kojiro(turtle=False)
        s._candidates["005930"] = {"atr": 3_000.0}
        assert s.calc_buy_quantity(price, "005930") == _pr_qty(BUDGET, price)
        return
    s = _kojiro()
    if setup == "atr_zero":
        s._candidates["005930"] = {"atr": 0}
    if setup == "ticker_none":
        s._candidates["005930"] = {"atr": 3_000.0}
        assert s.calc_buy_quantity(price, None) == _pr_qty(BUDGET, price)
        return
    assert s.calc_buy_quantity(price, "005930") == _pr_qty(BUDGET, price)


# ---------------------------------------------------------------------------
# B1-EXIT-UNCHANGED — 청산 경로는 사이징 방식을 참조하지 않는다
# ---------------------------------------------------------------------------
def test_check_exit_signal_does_not_reference_sizing_mode():
    src = inspect.getsource(KojiroStrategy.check_exit_signal)
    fn = ast.parse(src.lstrip()).body[0]
    tokens = {
        n.value for n in ast.walk(fn)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    assert "sizing_mode" not in tokens, (
        "청산이 사이징 방식을 참조하면 안 된다 — 기보유 포지션의 손절 규약이 "
        "DB 토글 하나로 바뀌는 사고 경로"
    )
    assert "_entry_atr" not in src, (
        "kojiro 는 `_entry_atr` 스냅샷을 도입하지 않는다 — "
        "`_candidates` live ATR + `_stop_floor` tighten-only 단일 메커니즘 유지"
    )


def test_exit_signal_uses_candidates_atr_same_source_as_sizing():
    """sizing 과 손절이 같은 `_candidates[t]['atr']` 를 읽는다 (커플링 보증)."""
    exit_src = inspect.getsource(KojiroStrategy.check_exit_signal)
    calc_src = inspect.getsource(KojiroStrategy.calc_buy_quantity)
    assert '_candidates' in exit_src and '"atr"' in exit_src
    assert '_candidates' in calc_src and '"atr"' in calc_src
