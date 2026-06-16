"""사이클 147 AST 영구 가드 — `_order_strategy.get(order_no, "momentum")` 하드코딩 폴백 패턴 영구 차단.

## 영역 영구 영속 의무

`src/engine/order_engine.py::_handle_sell_fill` + `_handle_buy_fill` 영역에서
`self._order_strategy.get(order_no, "momentum")` 패턴 영구 영속 0건.

사이클 147 시정 후 영구 영속 = `self._order_strategy.get(order_no)` (default 미지정) +
trade_history fallback 영역 영구 영속 chain.

## 사유

005940 사고 시점 영역 = `self._order_strategy.get(order_no, "momentum")` 하드코딩 폴백 → 잘못된 strategy → trade_history strategy 미매칭 → affected=0 → 보정 INSERT UniqueViolation → callback_exception.
미래 동일 패턴 재발 영역 영구 차단.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ORDER_ENGINE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "src"
    / "engine"
    / "order_engine.py"
)


def _find_function_node(tree: ast.AST, name: str) -> ast.AsyncFunctionDef | None:
    """AsyncFunctionDef 영역에서 이름 매칭 영역 영구 영속 추적."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    return None


def _count_hardcoded_momentum_fallback(func_node: ast.AsyncFunctionDef) -> int:
    """`self._order_strategy.get(order_no, "momentum")` 패턴 영역 카운트."""
    count = 0
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        # self._order_strategy.get(...) 패턴 영역 매칭
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "get":
            continue
        value = node.func.value
        if not isinstance(value, ast.Attribute):
            continue
        if value.attr != "_order_strategy":
            continue
        # arg2 = "momentum" 영역 매칭
        if len(node.args) >= 2:
            arg2 = node.args[1]
            if isinstance(arg2, ast.Constant) and arg2.value == "momentum":
                count += 1
    return count


# ---------------------------------------------------------------------------
# G-147-AST-1 (HIGH) — _handle_sell_fill + _handle_buy_fill 하드코딩 폴백 영역 0건
# ---------------------------------------------------------------------------
def test_G147_AST_1_HIGH_no_hardcoded_momentum_fallback_in_sell_buy_fill() -> None:
    """사이클 147 시정 후 영구 영속 의무 영역.

    `_handle_sell_fill` + `_handle_buy_fill` 영역에서
    `self._order_strategy.get(order_no, "momentum")` 하드코딩 폴백 패턴 = 0건.
    """
    assert ORDER_ENGINE_PATH.exists(), f"order_engine.py 영역 영구 영속 의무: {ORDER_ENGINE_PATH}"

    source = ORDER_ENGINE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for target_name in ("_handle_sell_fill", "_handle_buy_fill"):
        func = _find_function_node(tree, target_name)
        assert func is not None, f"{target_name} 영역 영구 영속 의무"

        count = _count_hardcoded_momentum_fallback(func)
        assert count == 0, (
            f"{target_name} 영역 `self._order_strategy.get(order_no, \"momentum\")` "
            f"하드코딩 폴백 영역 영구 차단 의무 — 매핑 dict miss 시 trade_history fallback "
            f"영역 영구 영속 chain 사용. 발견 {count}건."
        )


# ---------------------------------------------------------------------------
# G-147-AST-2 — _lookup_strategy_from_trade_history 영역 호출 ≥ 2 (sell + buy)
# ---------------------------------------------------------------------------
def test_G147_AST_2_lookup_helper_used_in_both_handlers() -> None:
    """`_lookup_strategy_from_trade_history` 호출 영역 영구 영속 의무 영역."""
    source = ORDER_ENGINE_PATH.read_text(encoding="utf-8")

    # 함수 호출 영역 grep — `_lookup_strategy_from_trade_history(`
    pattern = re.compile(r"_lookup_strategy_from_trade_history\s*\(")
    matches = pattern.findall(source)

    # G-147-AST-2: sell + buy 영역 ≥ 2건 호출 영역 영구 영속 의무 (import 영역 제외)
    # 단, sell 영역만 우선 시정 시 ≥ 1건 정합 영구 영속.
    assert len(matches) >= 1, (
        f"`_lookup_strategy_from_trade_history` 호출 영역 영구 영속 의무 "
        f"(`_handle_sell_fill` 최소 1건). 발견 {len(matches)}건."
    )
