"""Phase 2A-1 — kojiro 터틀 유닛 sizing opt-in 회귀 가드.

- INV: sizing_mode='turtle' → qty×ATR ≈ budget×risk_pct (클램프 미발동, ±1주).
- FALLBACK: turtle + {risk_pct 0·None / atr 0·_candidates 부재 / ticker None / mode≠turtle} → position_ratio.
- SIG: 7전략 calc_buy_quantity(price, ticker) 2-positional 호출 정상 + AST ticker 파라미터.
- REGRESS: 미전환 6전략에 sizing_mode='turtle' 주입해도 position_ratio 바이트 동일(분기 부재).
"""

from __future__ import annotations

import ast
import inspect
import math

import pytest

from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategy_base import Position, StrategyConfig

pytestmark = pytest.mark.unit

_ALL_STRATEGY_CLASSES = [
    KojiroStrategy, DonchianSwingStrategy, BullFlagBreakoutStrategy, VcpBreakoutStrategy,
    VolatilityBreakoutStrategy, LongTailVolatilityStrategy, MomentumStrategy,
]


_OMIT = object()


def _kojiro(*, turtle=False, risk_pct=_OMIT, budget=100_000_000):
    params = {}
    if turtle:
        params["sizing_mode"] = "turtle"
    if risk_pct is not _OMIT:
        params["risk_pct"] = risk_pct  # None 도 명시 주입 (fallback 경로 검증용)
    s = KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2, params=params))
    s.state.total_investment = budget
    return s


# ── INV: 터틀 유닛 불변식 ──

def test_turtle_sizing_invariant():
    s = _kojiro(turtle=True, risk_pct=0.005, budget=100_000_000)
    s._candidates["005930"] = {"atr": 3000.0}
    # unit = floor(100M*0.005/3000)=166. price 10000 → budget_qty 10000 → 클램프 미발동
    qty = s.calc_buy_quantity(10000, "005930")
    assert qty == math.floor(100_000_000 * 0.005 / 3000)  # 166
    # 불변식: qty×ATR ≈ budget×risk_pct (절삭오차 < ATR)
    assert abs(qty * 3000.0 - 100_000_000 * 0.005) < 3000.0


def test_turtle_sizing_atr_inverse():
    s = _kojiro(turtle=True)
    s._candidates["A"] = {"atr": 1000.0}
    s._candidates["B"] = {"atr": 5000.0}
    assert s.calc_buy_quantity(10000, "A") > s.calc_buy_quantity(10000, "B")


def test_turtle_budget_clamp_binding():
    """잔여 예산 클램프 바인딩.

    의미 전환 (2026-08-03 B-1 guarded 전환): 기존 입력 `atr=100 / price=50,000` 은
    `atr/price = 0.2%` 라 `compute_unit_qty_guarded` 의 변동성 floor(1%)에 걸려
    터틀이 0 을 반환하고 position_ratio 로 낙하한다 — 예산 클램프를 관측할 수 없다.
    입력을 floor 통과값으로 조정해 **본래 의도(잔여 예산 클램프 바인딩)를 보존**한다.
    저변동 낙하 자체는 `test_kojiro_turtle_guarded.py` 가 별도로 고정한다.
    """
    s = _kojiro(turtle=True, budget=1_000_000)  # 예산 100만
    s._candidates["005930"] = {"atr": 200.0}    # atr/price = 2% ≥ floor. unit = 5000/200 = 25
    # notional 상한 = int(1M×0.20)//10,000 = 20 / 잔여 상한 = 1M//10,000 = 100 → unit 25 중
    # notional 20 이 먼저 바인딩하지 않도록 잔여를 더 좁혀 예산 클램프를 관측한다.
    s.state.positions["000001"] = Position(
        ticker="000001", buy_price=900_000, quantity=1, order_no="O", strategy_id="kojiro",
    )
    # 잔여 100,000 → 100,000//10,000 = 10주 (unit 25 / notional 20 보다 좁음)
    assert s.calc_buy_quantity(10_000, "005930") == 10


# ── FALLBACK: 모든 실패 경로 → position_ratio ──

def _position_ratio_qty(budget, price, ratio=0.20):
    return int(budget * ratio) // price


def test_fallback_when_risk_pct_zero():
    s = _kojiro(turtle=True, risk_pct=0.0, budget=100_000_000)
    s._candidates["005930"] = {"atr": 3000.0}
    assert s.calc_buy_quantity(10000, "005930") == _position_ratio_qty(100_000_000, 10000)


def test_fallback_when_risk_pct_none():
    s = _kojiro(turtle=True, risk_pct=None, budget=100_000_000)
    s._candidates["005930"] = {"atr": 3000.0}
    assert s.calc_buy_quantity(10000, "005930") == _position_ratio_qty(100_000_000, 10000)


def test_fallback_when_atr_missing():
    s = _kojiro(turtle=True, budget=100_000_000)
    # _candidates 에 ticker 없음 → atr 0 → compute 0 → fallback
    assert s.calc_buy_quantity(10000, "005930") == _position_ratio_qty(100_000_000, 10000)


def test_fallback_when_atr_zero():
    s = _kojiro(turtle=True, budget=100_000_000)
    s._candidates["005930"] = {"atr": 0.0}
    assert s.calc_buy_quantity(10000, "005930") == _position_ratio_qty(100_000_000, 10000)


def test_fallback_when_ticker_none():
    s = _kojiro(turtle=True, budget=100_000_000)
    s._candidates["005930"] = {"atr": 3000.0}
    # ticker=None → turtle 분기 skip → position_ratio
    assert s.calc_buy_quantity(10000) == _position_ratio_qty(100_000_000, 10000)


def test_position_ratio_mode_ignores_turtle():
    s = _kojiro(turtle=False, budget=100_000_000)  # sizing_mode 기본 position_ratio
    s._candidates["005930"] = {"atr": 3000.0}
    assert s.calc_buy_quantity(10000, "005930") == _position_ratio_qty(100_000_000, 10000)


# ── SIG: 7전략 시그니처 ──

@pytest.mark.parametrize("cls", _ALL_STRATEGY_CLASSES)
def test_calc_buy_quantity_accepts_ticker_arg(cls):
    s = cls(StrategyConfig(strategy_id=cls.__name__, name="x", weight=0.1))
    s.state.total_investment = 100_000_000
    # 2-positional 호출 크래시 없음 (hot path TypeError 방지)
    q = s.calc_buy_quantity(10000, "005930")
    assert isinstance(q, int) and q >= 0


@pytest.mark.parametrize("cls", _ALL_STRATEGY_CLASSES)
def test_calc_buy_quantity_signature_has_ticker_param(cls):
    src = inspect.getsource(cls.calc_buy_quantity)
    tree = ast.parse(src.strip() if not src.startswith(" ") else __import__("textwrap").dedent(src))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    arg_names = [a.arg for a in fn.args.args]
    assert "ticker" in arg_names, f"{cls.__name__}.calc_buy_quantity 에 ticker 파라미터 없음"


# ── REGRESS: 미전환 6전략 turtle 주입해도 position_ratio 동일 ──

@pytest.mark.parametrize("cls", [
    DonchianSwingStrategy, BullFlagBreakoutStrategy, VcpBreakoutStrategy,
    VolatilityBreakoutStrategy, LongTailVolatilityStrategy, MomentumStrategy,
])
def test_non_kojiro_ignores_turtle_mode(cls):
    # sizing_mode='turtle' + risk_pct 주입해도 6전략은 turtle 분기 부재 → 기존 수량 동일
    s_plain = cls(StrategyConfig(strategy_id=cls.__name__, name="x", weight=0.1))
    s_turtle = cls(StrategyConfig(strategy_id=cls.__name__, name="x", weight=0.1,
                                  params={"sizing_mode": "turtle", "risk_pct": 0.005}))
    s_plain.state.total_investment = 100_000_000
    s_turtle.state.total_investment = 100_000_000
    # ticker 유무·turtle 주입 무관 동일
    assert s_turtle.calc_buy_quantity(10000, "005930") == s_plain.calc_buy_quantity(10000)
