"""cycle439 — B4-4: `execute_sell` 의 수량 초과(APBK0400) #1.5 재대조 분기를
`OrderEngine._handle_sell_qty_exceeded` 로 추출한다(행위 보존, B4-3·B4-5 와
같은 설계 — `_workspace/refactor/2026-10-09_review.md` B4-4행).

관문 3 중 「호출부 단일」 — 그 메서드를 부르는 자리는 `execute_sell` 1건뿐이다.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ORDER_ENGINE_PATH = _REPO_ROOT / "src" / "engine" / "order_engine.py"
_HELPER = "_handle_sell_qty_exceeded"
_GATE = "is_sell_qty_exceeded"


def _module_tree() -> ast.Module:
    return ast.parse(_ORDER_ENGINE_PATH.read_text(encoding="utf-8"))


def _class_body(tree: ast.Module, class_name: str) -> list[ast.stmt]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node.body
    raise AssertionError(f"클래스 {class_name} 를 찾지 못했다")


def _func(name: str) -> ast.AsyncFunctionDef:
    tree = _module_tree()
    for node in _class_body(tree, "OrderEngine"):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"OrderEngine.{name} 를 찾지 못했다")


def _call_names(fn: ast.AST, name: str) -> list[int]:
    """`fn` 바디 안에서 `self.<name>(...)` 또는 `<name>(...)` 호출의 줄번호."""
    out: list[int] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute) and target.attr == name:
                out.append(node.lineno)
            elif isinstance(target, ast.Name) and target.id == name:
                out.append(node.lineno)
    return out


def test_helper_exists_and_is_async():
    fn = _func(_HELPER)
    assert isinstance(fn, ast.AsyncFunctionDef), f"{_HELPER} 는 async def 여야 한다"


def test_helper_is_called_exactly_once_from_execute_sell():
    """🔴 호출부는 `execute_sell` **1곳**뿐이다."""
    calls_in_execute_sell = _call_names(_func("execute_sell"), _HELPER)
    assert len(calls_in_execute_sell) == 1, (
        f"execute_sell 안 호출 {len(calls_in_execute_sell)}곳 (기대 1곳): "
        f"{calls_in_execute_sell}"
    )


def test_helper_is_not_called_from_anywhere_else_in_order_engine():
    """OrderEngine 의 다른 메서드가 이 헬퍼를 부르면 안 된다(단일 진입점)."""
    tree = _module_tree()
    other_call_sites: list[tuple[str, int]] = []
    for node in _class_body(tree, "OrderEngine"):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in (_HELPER, "execute_sell"):
            continue
        for ln in _call_names(node, _HELPER):
            other_call_sites.append((node.name, ln))
    assert other_call_sites == [], (
        f"execute_sell 밖에서 {_HELPER} 를 부르는 자리가 있다: {other_call_sites}"
    )


def test_gate_still_lives_in_execute_sell():
    """관문 판정(`is_sell_qty_exceeded`)은 호출부에 남아 있다 — 헬퍼가 그 판정을
    다시 하지 않는다(B4-3·B4-5 와 같은 설계)."""
    fn = _func("execute_sell")
    gate_calls = _call_names(fn, _GATE)
    assert len(gate_calls) == 1, (
        f"execute_sell 안 {_GATE} 호출 {len(gate_calls)}곳 (기대 1곳)"
    )

    helper_fn = _func(_HELPER)
    helper_gate_calls = _call_names(helper_fn, _GATE)
    assert helper_gate_calls == [], (
        f"{_HELPER} 안에서 {_GATE} 를 다시 판정한다 — 관문은 호출부에만 있어야 한다"
    )


def test_helper_returns_outcome_and_sell_cap_tuple():
    """반환형이 `(SellQtyExceededOutcome, sell_cap)` 튜플임을 소스에서 확인한다."""
    import src.engine.order_engine as oe

    sig = inspect.signature(oe.OrderEngine._handle_sell_qty_exceeded)
    assert "sell_cap" in sig.parameters, "sell_cap 을 입력으로 받지 않는다"
    src = inspect.getsource(oe.OrderEngine._handle_sell_qty_exceeded)
    for outcome in ("RETRY", "STOP", "FALL_THROUGH"):
        assert f"SellQtyExceededOutcome.{outcome}" in src, (
            f"{outcome} 출구가 소스에서 사라졌다"
        )


def test_callsite_handles_all_three_outcomes():
    src = inspect.getsource(
        __import__("src.engine.order_engine", fromlist=["OrderEngine"]).OrderEngine.execute_sell
    )
    assert "SellQtyExceededOutcome.RETRY" in src
    assert "SellQtyExceededOutcome.STOP" in src
