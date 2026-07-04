"""사이클 191 AST Red — 재진입 쿨다운 배선 구조 정적 가드.

작업 지시서 `_workspace/red/cycle191_reentry_cooldown_wiring.md` §Red AST.

source 텍스트 grep 금지 — AST 노드 검사 (사이클 167/179/185 교훈: 주석/별칭/공백 false-positive 차단).

- A-1 (HIGH, G-191-NO-DAILY-RESET, 불변식): BFB/VCP `_reset_daily_state`·`prepare` 본체에
  `_cooldown_until` clear/재대입 0건 (multi-day 상태 영구 보호). 현행 PASS (미래 재발 차단).
- A-2 (Red): BFB/VCP `on_position_closed` 내 `register_cooldown_after_exit` Call ≥ 1
  (고아 재발 영구 차단). 현재 FAIL = BFB 미호출 + VCP override 부재.
- A-3 (불변식): order_engine `on_position_closed` 호출 site 정확히 2곳 (사이클 185 G2 답습, 참조).
"""

from __future__ import annotations

import ast

import pytest

import src.engine.order_engine as _oe_mod
import src.engine.strategies.bull_flag_breakout as _bfb_mod
import src.engine.strategies.vcp_breakout as _vcp_mod

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# AST 헬퍼
# ---------------------------------------------------------------------------
def _parse(module) -> ast.Module:
    with open(module.__file__, encoding="utf-8") as f:
        return ast.parse(f.read())


def _find_func(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _is_cooldown_attr(node: ast.AST) -> bool:
    """`*._cooldown_until` Attribute 노드 판별."""
    return isinstance(node, ast.Attribute) and node.attr == "_cooldown_until"


def _cooldown_mutations(func_node: ast.AST) -> list:
    """함수 내 `_cooldown_until` 대입/clear/pop/재대입 노드 목록.

    - `self._cooldown_until = ...` (Attribute 대입)
    - `self._cooldown_until[...] = ...` (Subscript 대입)
    - `self._cooldown_until.clear()` / `.pop(...)` / `.popitem()`
    """
    hits: list = []
    for node in ast.walk(func_node):
        # Assign / AnnAssign 타깃
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for tgt in targets:
            if _is_cooldown_attr(tgt):
                hits.append(node)
            if isinstance(tgt, ast.Subscript) and _is_cooldown_attr(tgt.value):
                hits.append(node)
        # clear/pop 계열 Call
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("clear", "pop", "popitem") and _is_cooldown_attr(
                node.func.value
            ):
                hits.append(node)
    return hits


def _register_calls(func_node: ast.AST) -> list:
    return [
        n
        for n in ast.walk(func_node)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Attribute) and n.func.attr == "register_cooldown_after_exit")
            or (isinstance(n.func, ast.Name) and n.func.id == "register_cooldown_after_exit")
        )
    ]


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
# A-1 (HIGH, 불변식 PASS) — 일일/prepare 리셋 절대 금지
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mod", [_bfb_mod, _vcp_mod], ids=["bfb", "vcp"])
def test_A1_no_cooldown_reset_in_daily_or_prepare(mod) -> None:
    """G-191-NO-DAILY-RESET: `_reset_daily_state`/`prepare` 에 `_cooldown_until` mutation 0건.

    multi-day 상태 → 일일/prepare 리셋 시 3/7일 쿨다운 매일 소멸 = 무의미 → 영구 차단.
    (VCP `_reset_daily_state` override 부재 = 자동 미접촉 PASS)
    """
    tree = _parse(mod)
    for fname in ("_reset_daily_state", "prepare"):
        fn = _find_func(tree, fname)
        if fn is None:
            continue  # override 부재 = 미접촉 (PASS)
        muts = _cooldown_mutations(fn)
        assert not muts, (
            f"{mod.__name__}.{fname} 에 _cooldown_until mutation {len(muts)}건 — "
            "multi-day 쿨다운 일일 소멸 영구 차단 위반"
        )


# ---------------------------------------------------------------------------
# A-2 (Red) — on_position_closed 내 register 호출 존재 의무
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mod", [_bfb_mod, _vcp_mod], ids=["bfb", "vcp"])
def test_A2_on_position_closed_calls_register(mod) -> None:
    """BFB/VCP `on_position_closed` FunctionDef 존재 + `register_cooldown_after_exit` Call ≥ 1.

    현재 FAIL = BFB on_position_closed 미호출 / VCP override 부재 (고아 재발).
    """
    tree = _parse(mod)
    fn = _find_func(tree, "on_position_closed")
    assert fn is not None, (
        f"{mod.__name__}.on_position_closed override 신설 의무 (고아 쿨다운 배선)"
    )
    calls = _register_calls(fn)
    assert len(calls) >= 1, (
        f"{mod.__name__}.on_position_closed 에 register_cooldown_after_exit Call ≥ 1 의무"
    )


# ---------------------------------------------------------------------------
# A-3 (불변식 PASS) — order_engine on_position_closed 호출 site 정확히 2곳
# ---------------------------------------------------------------------------
def test_A3_order_engine_on_position_closed_two_sites() -> None:
    """order_engine `_handle_sell_fill` + `execute_sell` 양쪽 on_position_closed Call ≥ 1 (사이클 185 계약).

    사이클 191 은 훅 계약 불변 재사용 → order_engine 변경 0. 참조 가드.
    """
    tree = _parse(_oe_mod)
    for fname in ("_handle_sell_fill", "execute_sell"):
        fn = _find_func(tree, fname)
        assert fn is not None, f"{fname} FunctionDef 존재 의무"
        calls = _on_position_closed_calls(fn)
        assert len(calls) >= 1, (
            f"{fname} 영역 on_position_closed Call ≥ 1 (사이클 185 계약 불변)"
        )
