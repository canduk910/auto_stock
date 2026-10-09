"""사이클 185 클러스터 ① AST Red — 배선 구조 정적 가드.

Red 설계 `_workspace/red/cycle185_cluster1_reset.md` §AST.

source 텍스트 grep 금지 — AST 노드 검사 (사이클 167/179 교훈: 주석/별칭/공백 false-positive 차단).

- G1-WIRING-AST (Red): scheduler `_reset_daily_state` FunctionDef 에
  `<name>._reset_daily_state()` Call 노드 (receiver=Name != self) 존재.
- G2-OE-AST (Red): order_engine `_handle_sell_fill` FunctionDef 에
  `on_position_closed` Call ≥ 1.
  🔁 cycle429(D1 안A, 사용자 승인 2026-10-10) — 수량 부족(APBK1234·APBK0400
  실보유 0) 자동 삭제 경로가 없어지면서 `_handle_sell_final_failure` 의
  포지션 제거·`on_position_closed` 분기가 사라졌다(`_handle_sell_insufficient_quantity`
  로 흡수된 로직은 포지션을 **보존**하므로 on_position_closed 를 부르지
  않는다). 그래서 이 자리의 의무는 `_handle_sell_fill` 하나로 좁아진다.
- G2-OE-AST (PASS, 불변): `execute_sell` → `_handle_sell_final_failure`
  호출 배선(이 메서드는 여전히 미분류 거부의 CRITICAL 1행 뒤처리를 한다 —
  `_handle_sell_final_failure` 자신은 더 이상 positions 를 건드리지 않는다).
- G2-STRUCT-INVARIANT (HIGH, cycle429 로 재조준):
  (1) site 집합(불변식): order_engine 의 `state.positions` 제거
      (`del ...positions[...]` / `...positions.pop(...)`) 직접 포함 함수 집합
      == `{_handle_sell_fill}` **하나뿐**(2번째 site 추가 영구 차단). D1 안A
      이전에는 `_handle_sell_final_failure` 도 포함된 둘이었으나, 자동 삭제
      경로가 없어지며 제거 자리가 하나로 줄었다.
  (2) companion (PASS): 그 함수에 `on_position_closed` Call 동반 의무.
"""

from __future__ import annotations

import ast
from pathlib import Path

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
    """order_engine `_handle_sell_fill` 에 on_position_closed Call ≥ 1.

    cycle429(D1 안A) 재조준 — `_handle_sell_final_failure` 는 더 이상
    포지션을 제거하지 않는다(수량 부족 자동 삭제 경로 폐지). 그래서
    `on_position_closed` 동반 의무는 `_handle_sell_fill` 하나로 좁아진다.
    """
    tree = _parse(_oe_mod)
    for fname in ("_handle_sell_fill",):
        fn = _find_func(tree, fname)
        assert fn is not None, f"{fname} FunctionDef 존재 의무"
        calls = _on_position_closed_calls(fn)
        assert len(calls) >= 1, f"{fname} 영역 on_position_closed Call 노드 ≥ 1 의무"

    # D1 안A 불변식 — `_handle_sell_final_failure` 는 더 이상 on_position_closed
    # 를 부르지 않는다(포지션을 건드리지 않으므로). 되살리면 회귀다.
    final_failure_fn = _find_func(tree, "_handle_sell_final_failure")
    assert final_failure_fn is not None, "_handle_sell_final_failure FunctionDef 존재 의무"
    assert not _on_position_closed_calls(final_failure_fn), (
        "_handle_sell_final_failure 가 on_position_closed 를 부른다 — "
        "D1 안A 이후 이 함수는 포지션을 제거하지 않아야 한다"
    )


def test_G2_OE_AST_execute_sell_wires_final_failure_handoff() -> None:
    """execute_sell → `_handle_sell_final_failure` 호출 배선 의무 (약화 금지).

    위 테스트가 제거 자리를 `_handle_sell_final_failure` 로 재조준하는 대신,
    `execute_sell` 이 실제로 그 메서드를 부르는지를 이 테스트가 지킨다 —
    안 그러면 추출된 메서드가 죽은 코드로 방치돼도 위 테스트는 계속 통과한다
    (G1-WIRING-AST 와 같은 패턴).
    """
    tree = _parse(_oe_mod)
    fn = _find_func(tree, "execute_sell")
    assert fn is not None, "execute_sell FunctionDef 존재 의무"
    hits = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "_handle_sell_final_failure"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "self"
    ]
    assert len(hits) >= 1, (
        "execute_sell 안에 self._handle_sell_final_failure(...) 호출(배선) 의무"
    )


def _final_failure_refs(tree: ast.AST, func_of: dict) -> list:
    """`_handle_sell_final_failure` 를 가리키는 노드의 직속 enclosing 함수명 목록.

    호출뿐 아니라 맨 참조(`cb = self._handle_sell_final_failure`)와
    `getattr(..., "_handle_sell_final_failure")` 문자열 상수까지 센다 —
    우회 배선도 「다른 자리에서 부른다」 와 같기 때문이다. 정의(FunctionDef
    이름)는 노드가 아니라 세지 않는다. docstring 은 백틱 등으로 이름과
    정확히 같지 않아 걸리지 않는다.
    """
    name = "_handle_sell_final_failure"
    out: list = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.Attribute) and n.attr == name) or (
            isinstance(n, ast.Constant) and n.value == name
        ):
            out.append(func_of.get(n))
    return out


def test_G2_OE_AST_final_failure_called_only_from_execute_sell() -> None:
    """`_handle_sell_final_failure` 의 부르는 자리 == `execute_sell` 정확히 1건.

    B4-5(cycle426) 관문 3 보강 — 위 배선 테스트는 「execute_sell 이 ≥1회
    부른다」 만 본다. cycle429(D1 안A) 이후 이 메서드는 미분류 거부의
    CRITICAL 뒤처리만 하지만(포지션 제거 분기는 사라졌다), 다른 메서드가
    이 메서드를 부르면 「제거 자리는 `_handle_sell_fill` 하나뿐」 불변식이
    이름만 지켜진 채 실질 2번째 제거 경로가 생길 수 있다(관문 1 돌연변이
    M6 — 가드·그물 모두 놓쳤다). 그래서 order_engine 전체의 참조 자리를
    정확히 `["execute_sell"]` 로 묶고, `src/` 의 다른 모듈에서는 참조 0 을
    요구한다.
    """
    tree = _parse(_oe_mod)
    refs = _final_failure_refs(tree, _func_of_map(tree))
    assert refs == ["execute_sell"], (
        "order_engine 안 `_handle_sell_final_failure` 참조 자리는 execute_sell "
        f"1건뿐이어야 한다(실질 3번째 포지션 제거 경로 차단): {refs}"
    )

    oe_path = Path(_oe_mod.__file__).resolve()
    src_root = oe_path.parents[1]  # src/
    outside: list = []
    for py in sorted(src_root.rglob("*.py")):
        if py.resolve() == oe_path:
            continue
        mod_tree = ast.parse(py.read_text(encoding="utf-8"))
        hits = _final_failure_refs(mod_tree, _func_of_map(mod_tree))
        outside.extend(f"{py.relative_to(src_root.parent)}:{fn}" for fn in hits)
    assert outside == [], (
        f"order_engine 밖에서 `_handle_sell_final_failure` 를 참조한다: {outside}"
    )


# ---------------------------------------------------------------------------
# G2-STRUCT-INVARIANT (HIGH) — site 집합 불변식 (양쪽 PASS) + companion (Red)
# ---------------------------------------------------------------------------
def test_G2_STRUCT_INVARIANT_site_set_exactly_two() -> None:
    """order_engine state.positions 제거 site 집합 == {_handle_sell_fill} 하나뿐.

    cycle429(D1 안A, 사용자 승인 2026-10-10) 재조준 — 수량 부족 거부
    (APBK1234·APBK0400 실보유 0) 의 자동 삭제 경로를 없앴다. 포지션을
    지우는 길은 이제 체결통보 보유 축(`_handle_sell_fill`) · 재기동 복구 ·
    사람(수동 정리) 셋뿐이고, `order_engine.py` 안에서는 `_handle_sell_fill`
    하나다. 2번째 제거 site 추가 시 가드 FAIL(도메인 권고 B 재확인 의무).
    """
    tree = _parse(_oe_mod)
    func_of = _func_of_map(tree)
    funcs = _positions_removal_funcs(tree, func_of)
    assert funcs == {"_handle_sell_fill"}, (
        f"order_engine 메모리 positions 제거 site 불변식 위반: {funcs}. "
        "D1 안A(cycle429) 이후 제거 자리는 _handle_sell_fill 하나뿐이어야 한다."
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
