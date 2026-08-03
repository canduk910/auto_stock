"""전략 예산 이중제한 — AST 영구 가드.

행위 테스트로는 잡히지 않는 **구조적 계약**을 정적으로 봉인한다.

- **A-ATOMIC (최우선)**: `order_engine.execute_buy` 의 `calc_buy_quantity` 호출 ~
  `pending_buys.add` 사이 `await` 0건. 이 구간이 동기이기 때문에 `_apply_budget_limit`
  이 읽는 잔여 예산이 pending 등록까지 원자적이다. 누가 `await` 를 하나만 끼워도
  두 코루틴이 같은 잔여를 보고 각자 매수해 예산 클램프가 조용히 무력화된다.
  **8영역(order_engine)을 건드리지 않으면서 8영역을 보호하는 가드.**
- **A-PURE**: 관문 자체가 `await`/DB/HTTP 를 쓰지 않는다 (원자성 유지 조건).
- **A-GATE**: 7 전략 `calc_buy_quantity` 의 모든 `return` 이 관문을 경유한다
  (상수 0 반환 및 관문에 위임하는 내부 헬퍼 호출만 예외).
- **C-MAXPOS**: `max_positions` 는 AI 자동튜닝 대상이 아니다 (리스크 정체성 상수).
- **C-DEFAULT**: 코드 기본값의 `position_ratio × max_positions ≤ 1.0` 불변식.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from src.engine import order_engine as order_engine_mod
from src.engine import recommendation_engine as rec_mod
from src.engine.strategy_base import StrategyBase

pytestmark = pytest.mark.unit

_STRATEGY_DIR = Path(__file__).resolve().parents[3] / "src" / "engine" / "strategies"

STRATEGY_FILES = [
    "momentum.py",
    "volatility_breakout.py",
    "long_tail_volatility.py",
    "donchian_swing.py",
    "bull_flag_breakout.py",
    "vcp_breakout.py",
    "kojiro.py",
]

GATE = "_apply_budget_limit"


def _func_node(source: str, name: str) -> ast.AST:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 함수를 찾지 못했습니다")


def _strategy_tree(filename: str) -> tuple[ast.AST, str]:
    src = (_STRATEGY_DIR / filename).read_text(encoding="utf-8")
    return ast.parse(src), src


# ---------------------------------------------------------------------------
# A-ATOMIC — execute_buy 의 사이징↔pending 등록 구간에 await 0건
# ---------------------------------------------------------------------------
def test_execute_buy_sizing_to_pending_is_await_free():
    src = inspect.getsource(order_engine_mod)
    fn = _func_node(src, "execute_buy")

    calc_lines = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "calc_buy_quantity"
    ]
    add_lines = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "add"
        and isinstance(n.func.value, ast.Attribute)
        and n.func.value.attr == "pending_buys"
    ]
    assert calc_lines, "execute_buy 에 calc_buy_quantity 호출이 없습니다"
    assert add_lines, "execute_buy 에 pending_buys.add 호출이 없습니다"

    start, end = min(calc_lines), min(add_lines)
    assert start < end, "calc_buy_quantity 가 pending_buys.add 보다 뒤에 있습니다"

    offenders = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Await) and start <= n.lineno <= end
    ]
    assert not offenders, (
        "execute_buy 의 사이징~pending 등록 구간에 await 가 있습니다 "
        f"(라인 {offenders}). 전략 예산 클램프의 원자성이 깨집니다 — "
        "잔여 예산 read 와 pending_buy_amounts 등록 사이에 다른 코루틴이 끼어들면 "
        "두 매수가 같은 잔여를 보고 각자 통과합니다."
    )


# ---------------------------------------------------------------------------
# A-PURE — 관문은 await / DB / HTTP 미접촉
# ---------------------------------------------------------------------------
def test_budget_gate_is_pure_sync():
    src = inspect.getsource(StrategyBase)
    fn = _func_node(src, GATE)

    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)], (
        f"{GATE} 안에 await 가 있습니다 — execute_buy 원자성 파괴"
    )
    forbidden = ("src.db", "httpx", "requests", "asyncio", "aiohttp")
    for node in ast.walk(fn):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith(forbidden), f"{GATE} 금지 import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(forbidden), (
                f"{GATE} 금지 import: {node.module}"
            )


# ---------------------------------------------------------------------------
# A-GATE — 7 전략 calc_buy_quantity 의 모든 return 이 관문 경유
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", STRATEGY_FILES)
def test_calc_buy_quantity_returns_pass_through_gate(filename):
    tree, _ = _strategy_tree(filename)
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "calc_buy_quantity":
            fn = node
            break
    assert fn is not None, f"{filename} 에 calc_buy_quantity 가 없습니다"

    gated = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        # 상수 0 (가격 <= 0 조기 반환) 은 허용
        if isinstance(node.value, ast.Constant) and node.value.value == 0:
            continue
        assert isinstance(node.value, ast.Call), (
            f"{filename}:{node.lineno} calc_buy_quantity 가 관문을 거치지 않고 "
            "수량을 직접 반환합니다 — 전략 예산 초과 매수 경로"
        )
        assert getattr(node.value.func, "attr", None) == GATE, (
            f"{filename}:{node.lineno} return 이 {GATE} 를 경유하지 않습니다"
        )
        gated += 1
    assert gated >= 1, f"{filename} calc_buy_quantity 에 {GATE} 경유 return 이 없습니다"


# ---------------------------------------------------------------------------
# C-MAXPOS — max_positions 는 AI 자동튜닝 화이트리스트에서 영구 제외
# ---------------------------------------------------------------------------
def test_max_positions_excluded_from_param_ranges():
    assert "max_positions" not in rec_mod.PARAM_RANGES, (
        "max_positions 는 PARAM_RANGES 편입 금지 — 동시보유 슬롯 수는 리스크 정체성 상수. "
        "position_ratio 와의 곱 교차검증이 없어 조합 사고(예산 200%)가 재발한다."
    )
    assert "max_positions" not in rec_mod.INT_PARAMS


# ---------------------------------------------------------------------------
# C-DEFAULT — 코드 기본값 불변식: position_ratio × max_positions ≤ 1.0
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("filename", STRATEGY_FILES)
def test_default_params_respect_budget_invariant(filename):
    tree, _ = _strategy_tree(filename)
    params: dict = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if not (
                isinstance(stmt, ast.Assign)
                and any(getattr(t, "id", "") == "DEFAULT_PARAMS" for t in stmt.targets)
                and isinstance(stmt.value, ast.Dict)
            ):
                continue
            for k, v in zip(stmt.value.keys, stmt.value.values):
                key = getattr(k, "value", None)
                if key in ("position_ratio", "max_positions"):
                    params[key] = ast.literal_eval(v)
    ratio = params.get("position_ratio")
    max_pos = params.get("max_positions")
    assert ratio is not None and max_pos is not None, (
        f"{filename} DEFAULT_PARAMS 에 position_ratio / max_positions 가 필요합니다"
    )
    assert ratio * max_pos <= 1.0 + 1e-9, (
        f"{filename}: position_ratio({ratio}) × max_positions({max_pos}) = "
        f"{ratio * max_pos:.2f} > 1.0 — 전략 예산 초과 조합. "
        "런타임 관문이 흡수하지만 기본값은 불변식을 지켜야 한다."
    )


# ---------------------------------------------------------------------------
# C-CROSS — position_ratio × max_positions > 1.0 추천은 거부된다
# ---------------------------------------------------------------------------
def test_validate_rejects_budget_overcommit_ratio():
    """max_positions=10 인 전략에 position_ratio 0.20(=200%) 추천 → 거부."""
    current = {"position_ratio": 0.10, "max_positions": 10, "stop_loss_rate": -7.0}
    params, *_ = rec_mod._validate_recommendations(
        {"recommended_params": {"position_ratio": 0.20}}, current,
    )
    assert "position_ratio" not in params, "예산 200% 조합이 통과했습니다"


def test_validate_accepts_within_budget_ratio():
    """동일 전략에 position_ratio 0.10(=100%) 은 통과."""
    current = {"position_ratio": 0.05, "max_positions": 10, "stop_loss_rate": -7.0}
    params, *_ = rec_mod._validate_recommendations(
        {"recommended_params": {"position_ratio": 0.10}}, current,
    )
    assert params.get("position_ratio") == pytest.approx(0.10)
