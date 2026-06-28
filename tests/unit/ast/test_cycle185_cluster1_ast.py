"""사이클 185 클러스터 ① AST Red — 배선 구조 정적 가드.

Red 설계 `_workspace/red/cycle185_cluster1_reset.md` §AST.

source 텍스트 grep 금지 — AST 노드 검사 (사이클 167/179 교훈: 주석/별칭/공백 false-positive 차단).

- G1-WIRING-AST (Red): scheduler `_reset_daily_state` FunctionDef 에
  `<name>._reset_daily_state()` Call 노드 (receiver=Name != self) 존재.
- G2-OE-AST (Red): order_engine `_handle_sell_fill` + `execute_sell` 양쪽 FunctionDef 에
  `on_position_closed` Call ≥ 1.
- G2-STRUCT-INVARIANT (HIGH):
  (1) site 집합 (양쪽 PASS, 불변식): order_engine 의 `state.positions` 제거
      (`del ...positions[...]` / `...positions.pop(...)`) 직접 포함 함수 집합
      == `{_handle_sell_fill, execute_sell}` (3번째 site 추가 영구 차단).
  (2) companion (Red): 위 각 함수에 `on_position_closed` Call 동반 의무.
"""

from __future__ import annotations

import ast

import pytest

import src.engine.order_engine as _oe_mod
import src.engine.scheduler as _sched_mod

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# AST 헬퍼
# ---------------------------------------------------------------------------
def _parse(module) -> ast.Module:
    with open(module.__file__, encoding="utf-8") as f:
        return ast.parse(f.read())


def _find_func(tree: ast.AST, name: str):
    """이름이 일치하는 (Async)FunctionDef 노드 반환 (전역 유일 가정)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _func_of_map(tree: ast.AST) -> dict:
    """각 노드 → 직속 enclosing (Async)FunctionDef 이름 매핑 (중첩 함수 정확 귀속)."""
    func_of: dict = {}

    def visit(node, fname):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_of[child] = fname
                visit(child, child.name)
            else:
                func_of[child] = fname
                visit(child, fname)

    visit(tree, None)
    return func_of


def _is_state_positions(node: ast.AST) -> bool:
    """`state.positions` 또는 `*.state.positions` Attribute 노드인지 판별."""
    if not (isinstance(node, ast.Attribute) and node.attr == "positions"):
        return False
    base = node.value
    if isinstance(base, ast.Name) and base.id == "state":
        return True
    if isinstance(base, ast.Attribute) and base.attr == "state":
        return True
    return False


def _positions_removal_funcs(tree: ast.AST, func_of: dict) -> set:
    """`state.positions` 제거 (`del [...]` / `.pop`/`.clear`/`.popitem`) 직접 포함 함수명 집합."""
    funcs: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Delete):
            for tgt in node.targets:
                if isinstance(tgt, ast.Subscript) and _is_state_positions(tgt.value):
                    funcs.add(func_of.get(node))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("pop", "clear", "popitem") and _is_state_positions(
                node.func.value
            ):
                funcs.add(func_of.get(node))
    funcs.discard(None)
    return funcs


def _on_position_closed_calls(func_node: ast.AST) -> list:
    return [
        n
        for n in ast.walk(func_node)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Attribute) and n.func.attr == "on_position_closed")
            or (isinstance(n.func, ast.Name) and n.func.id == "on_position_closed")
        )
    ]


# ---------------------------------------------------------------------------
# G1-WIRING-AST (Red)
# ---------------------------------------------------------------------------
def test_G1_WIRING_AST_scheduler_reset_calls_strategy_reset_daily_state() -> None:
    """scheduler `_reset_daily_state` 내 `strategy._reset_daily_state()` Call 노드 (배선) 의무.

    receiver=Name (예: strategy) AND != self (자기 재귀 배제).
    현재 FAIL = Call 노드 0건 (배선 부재).
    """
    tree = _parse(_sched_mod)
    target = _find_func(tree, "_reset_daily_state")
    assert target is not None, "scheduler._reset_daily_state FunctionDef 존재 의무"

    hits = [
        n
        for n in ast.walk(target)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "_reset_daily_state"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id != "self"
    ]
    assert len(hits) >= 1, (
        "scheduler _reset_daily_state 등록 순회에 strategy._reset_daily_state() Call 노드 (배선) 의무"
    )


# ---------------------------------------------------------------------------
# G2-OE-AST (Red)
# ---------------------------------------------------------------------------
def test_G2_OE_AST_both_sell_sites_call_on_position_closed() -> None:
    """order_engine `_handle_sell_fill` + `execute_sell` 양쪽에 on_position_closed Call ≥ 1.

    현재 FAIL = 양쪽 모두 0건.
    """
    tree = _parse(_oe_mod)
    for fname in ("_handle_sell_fill", "execute_sell"):
        fn = _find_func(tree, fname)
        assert fn is not None, f"{fname} FunctionDef 존재 의무"
        calls = _on_position_closed_calls(fn)
        assert len(calls) >= 1, f"{fname} 영역 on_position_closed Call 노드 ≥ 1 의무"


# ---------------------------------------------------------------------------
# G2-STRUCT-INVARIANT (HIGH) — site 집합 불변식 (양쪽 PASS) + companion (Red)
# ---------------------------------------------------------------------------
def test_G2_STRUCT_INVARIANT_site_set_exactly_two() -> None:
    """order_engine state.positions 제거 site 집합 == {_handle_sell_fill, execute_sell} (양쪽 PASS).

    3번째 제거 site 추가 시 가드 FAIL → on_position_closed 동반 의무 강제 (누설 silent 재발 영구 차단).
    """
    tree = _parse(_oe_mod)
    func_of = _func_of_map(tree)
    funcs = _positions_removal_funcs(tree, func_of)
    assert funcs == {"_handle_sell_fill", "execute_sell"}, (
        f"order_engine 메모리 positions 제거 site 불변식 위반: {funcs}. "
        "3번째 site 추가 시 on_position_closed 동반 의무 (도메인 권고 B)."
    )


def test_G2_STRUCT_INVARIANT_each_site_companions_on_position_closed() -> None:
    """positions 제거 site 함수마다 on_position_closed Call 동반 의무 (Red).

    현재 FAIL = 두 site 모두 on_position_closed 미동반.
    """
    tree = _parse(_oe_mod)
    func_of = _func_of_map(tree)
    funcs = _positions_removal_funcs(tree, func_of)
    assert funcs, "positions 제거 site 함수 집합 비어있음 (detector 결함)"
    for fname in funcs:
        fn = _find_func(tree, fname)
        assert fn is not None
        calls = _on_position_closed_calls(fn)
        assert len(calls) >= 1, (
            f"{fname} positions 제거 site 에 on_position_closed 동반 의무 (누설 차단)"
        )
