"""비중 단위 계약 — AST 영구 가드 (2026-08-18).

행위 테스트로는 되살아나는 것을 못 막는 **구조적 계약**을 정적으로 봉인한다.

- **G-1**: `routes/strategies.update_weights` 안에 값 크기 기반 단위 추론
  (`v / 100 if v > 1 else v`)이 **다시 생기지 않는다**. `IfExp` 0건 +
  `/ 100` BinOp 0건.
- **G-2**: Σ 불변식 가드가 `registry.update_weights` / `save_weights` 호출보다
  **먼저** 나오고 그 사이에 early return 이 있다 (메모리/DB split-brain 차단).
- **G-3**: `db/strategy_config.save_weights` 에는 Σ 검증이 **없다**.
  `routes/recommendations.py:110` 이 단일 전략 partial dict 로 호출하므로
  거기에 Σ 불변식을 넣으면 AI 자문 단건 적용이 전부 깨진다 — 라우트 계층 전용.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_ROUTES_STRATEGIES = _ROOT / "src" / "routes" / "strategies.py"
_DB_STRATEGY_CONFIG = _ROOT / "src" / "db" / "strategy_config.py"


def _func_node(path: Path, name: str) -> tuple[ast.AST, str]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node, src
    raise AssertionError(f"{path.name} 에서 {name} 함수를 찾지 못했습니다")


def _is_sum_of_weight_values(node: ast.AST) -> bool:
    """`sum(weights.values())` 형태인가."""
    if not isinstance(node, ast.Call):
        return False
    if not (isinstance(node.func, ast.Name) and node.func.id == "sum"):
        return False
    if len(node.args) != 1:
        return False
    arg = node.args[0]
    return (
        isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "values"
        and isinstance(arg.func.value, ast.Name)
        and arg.func.value.id == "weights"
    )


def _call_lines(func: ast.AST, *, attr: str | None = None, name: str | None = None) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if attr is not None and isinstance(f, ast.Attribute) and f.attr == attr:
            lines.append(node.lineno)
        elif name is not None and isinstance(f, ast.Name) and f.id == name:
            lines.append(node.lineno)
    return lines


# ---------------------------------------------------------------------------
# G-1 — 값 크기 기반 단위 추론 부활 금지
# ---------------------------------------------------------------------------


def test_g1_no_conditional_expression_in_update_weights():
    """`v / 100 if v > 1 else v` 형태의 삼항 추론 변환 0건."""
    func, _ = _func_node(_ROUTES_STRATEGIES, "update_weights")
    ifexps = [n for n in ast.walk(func) if isinstance(n, ast.IfExp)]
    assert not ifexps, (
        "update_weights 에 조건식(IfExp)이 있다 — 값 크기로 단위를 추론하면 "
        f"1%(=1)가 100%로 저장된다 (lineno={[n.lineno for n in ifexps]})"
    )


def test_g1_no_divide_by_hundred_in_update_weights():
    """`/ 100` 퍼센트→비율 변환 0건 (요청 바디는 이미 비율이다)."""
    func, _ = _func_node(_ROUTES_STRATEGIES, "update_weights")
    offenders = [
        n.lineno
        for n in ast.walk(func)
        if isinstance(n, ast.BinOp)
        and isinstance(n.op, ast.Div)
        and isinstance(n.right, ast.Constant)
        and n.right.value == 100
    ]
    assert not offenders, f"update_weights 에 / 100 변환이 있다 (lineno={offenders})"


# ---------------------------------------------------------------------------
# G-2 — Σ 가드가 저장보다 먼저 + early return
# ---------------------------------------------------------------------------


def test_g2_sum_tolerance_constant_exists():
    """Σ 허용오차는 매직넘버가 아니라 모듈 상수다."""
    src = _ROUTES_STRATEGIES.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {
        t.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for t in node.targets
        if isinstance(t, ast.Name)
    }
    assert "_WEIGHT_SUM_TOLERANCE" in names, (
        "모듈 상수 _WEIGHT_SUM_TOLERANCE 가 없다"
    )


def test_g2_sum_guard_precedes_persistence_with_early_return():
    """Σ 가드 → early return → registry.update_weights / save_weights 순서."""
    func, _ = _func_node(_ROUTES_STRATEGIES, "update_weights")

    guard_lines = [n.lineno for n in ast.walk(func) if _is_sum_of_weight_values(n)]
    assert guard_lines, "sum(weights.values()) Σ 불변식 가드가 없다"
    guard_line = min(guard_lines)

    registry_lines = _call_lines(func, attr="update_weights")
    assert registry_lines, "registry.update_weights 호출을 찾지 못했다"
    save_lines = _call_lines(func, name="save_weights") + _call_lines(
        func, attr="save_weights"
    )
    assert save_lines, "save_weights 호출을 찾지 못했다"

    assert guard_line < min(registry_lines), (
        f"Σ 가드(L{guard_line})가 registry.update_weights(L{min(registry_lines)}) 뒤에 있다 "
        "— 오염 payload 가 메모리에 먼저 반영된다"
    )
    assert guard_line < min(save_lines), (
        f"Σ 가드(L{guard_line})가 save_weights(L{min(save_lines)}) 뒤에 있다"
    )

    returns_between = [
        n.lineno
        for n in ast.walk(func)
        if isinstance(n, ast.Return) and guard_line <= n.lineno < min(registry_lines)
    ]
    assert returns_between, (
        "Σ 가드와 저장 사이에 early return 이 없다 — 거부해도 저장이 이어져 "
        "메모리/DB split-brain 이 발생한다"
    )


# ---------------------------------------------------------------------------
# G-3 — save_weights 에는 Σ 검증 금지 (partial dict 호출자 보호)
# ---------------------------------------------------------------------------


def test_g3_save_weights_has_no_sum_validation():
    """`db.strategy_config.save_weights` 는 Σ 를 검증하지 않는다.

    `routes/recommendations.py:110` / `recommendation_engine.py:601` 이
    `{sid: w}` 단건 dict 로 호출하므로 Σ 불변식이 성립하지 않는다.
    """
    func, _ = _func_node(_DB_STRATEGY_CONFIG, "save_weights")
    sum_calls = [n.lineno for n in _call_lines_all_sum(func)]
    assert not sum_calls, (
        "save_weights 에 sum() 검증이 있다 — 단일 전략 partial dict 호출자"
        f"(AI 자문 적용)가 깨진다 (lineno={sum_calls})"
    )


def _call_lines_all_sum(func: ast.AST) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(func)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "sum"
    ]
