"""사이클 201 AST Red — VB 재진입 쿨다운 배선 구조 정적 가드.

작업 지시서 = `_workspace/red/cycle201_vb_reentry_cooldown.md` §회귀 가드 (6)(7).

source 텍스트 grep 금지 — AST 노드 검사 (사이클 167/179/185/191 교훈: 주석/별칭/공백 false-positive 차단).

- (6) G-VB-NO-DAILY-RESET (HIGH, 불변식): VB `_reset_daily_state`/`prepare` 본체에
  `_cooldown_until` mutation 0건 (multi-day 상태 영구 보호). 현행 PASS (미래 재발 차단).
  사이클 191 G-191-NO-DAILY-RESET 답습.
- (7) SAFETY (불변식): 다른 전략 `reentry_cooldown_days` DEFAULT_PARAMS 값 불변
  (BFB=3 / VCP=7 보존). + VB on_position_closed 내 register_cooldown_after_exit Call ≥ 1.
"""

from __future__ import annotations

import ast

import pytest

import src.engine.strategies.bull_flag_breakout as _bfb_mod
import src.engine.strategies.vcp_breakout as _vcp_mod
import src.engine.strategies.volatility_breakout as _vb_mod

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# AST 헬퍼 (사이클 191 답습)
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
    """함수 내 `_cooldown_until` 대입/clear/pop/재대입 노드 목록."""
    hits: list = []
    for node in ast.walk(func_node):
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


def _default_params_dict(tree: ast.AST) -> ast.Dict | None:
    """클래스 본문 `DEFAULT_PARAMS = { ... }` 의 Dict 노드 반환."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "DEFAULT_PARAMS":
                    if isinstance(node.value, ast.Dict):
                        return node.value
    return None


def _dict_const_value(dnode: ast.Dict, key: str):
    """Dict 노드에서 문자열 키의 상수값 반환 (없으면 KeyError sentinel)."""
    for k, v in zip(dnode.keys, dnode.values):
        if isinstance(k, ast.Constant) and k.value == key:
            if isinstance(v, ast.Constant):
                return v.value
            # UnaryOp(-, Constant) 등 대비 (음수 리터럴)
            if isinstance(v, ast.UnaryOp) and isinstance(v.operand, ast.Constant):
                return v.operand.value
            return v  # 비상수 → 노드 그대로 (검사 측에서 판단)
    return _MISSING


_MISSING = object()


# ---------------------------------------------------------------------------
# (6) G-VB-NO-DAILY-RESET (HIGH, 불변식) — VB 일일/prepare 리셋 절대 금지
# ---------------------------------------------------------------------------
def test_6_no_cooldown_reset_in_vb_daily_or_prepare() -> None:
    """(6) G-VB-NO-DAILY-RESET: VB `_reset_daily_state`/`prepare` 에 `_cooldown_until` mutation 0건.

    multi-day 상태 → 일일/prepare 리셋 시 2영업일 쿨다운 매일 소멸 = 익일 재진입 방어 붕괴.
    현재 VB 에 두 메서드/`_cooldown_until` 부재 → 미접촉 PASS (불변식, 미래 회귀 차단).
    Green 후 `_reset_daily_state` override 신설 시에도 `_cooldown_until` 접촉 영구 금지.
    """
    tree = _parse(_vb_mod)
    for fname in ("_reset_daily_state", "prepare"):
        fn = _find_func(tree, fname)
        if fn is None:
            continue  # override 부재 = 미접촉 (PASS)
        muts = _cooldown_mutations(fn)
        assert not muts, (
            f"volatility_breakout.{fname} 에 _cooldown_until mutation {len(muts)}건 — "
            "multi-day 쿨다운 일일 소멸 영구 차단 위반 (사이클 191 G-191-NO-DAILY-RESET 답습)"
        )


# ---------------------------------------------------------------------------
# (7a) SAFETY 불변식 — 다른 전략 reentry_cooldown_days 값 불변 (BFB=3 / VCP=7)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mod,expected",
    [(_bfb_mod, 3), (_vcp_mod, 7)],
    ids=["bfb=3", "vcp=7"],
)
def test_7a_other_strategy_cooldown_days_unchanged(mod, expected) -> None:
    """(7a) SAFETY: BFB `reentry_cooldown_days`==3 / VCP ==7 DEFAULT_PARAMS 값 불변.

    사이클 201 은 VB 단독 신설 → BFB/VCP 값 변경 0 (혼선 방지).
    현행 PASS (불변식) — VB 작업이 다른 전략 값을 실수로 바꾸지 않게 영구 가드.
    """
    tree = _parse(mod)
    dnode = _default_params_dict(tree)
    assert dnode is not None, f"{mod.__name__} DEFAULT_PARAMS Dict 노드 존재 의무"
    val = _dict_const_value(dnode, "reentry_cooldown_days")
    assert val is not _MISSING, f"{mod.__name__} reentry_cooldown_days 키 존재 의무 (사이클 191)"
    assert val == expected, (
        f"{mod.__name__} reentry_cooldown_days == {expected} 불변 (사이클 201 VB 신설 무관)"
    )


# ---------------------------------------------------------------------------
# (7b) Red — VB on_position_closed 내 register 호출 존재 의무 (고아 재발 차단)
# ---------------------------------------------------------------------------
def test_7b_vb_on_position_closed_calls_register() -> None:
    """(7b) Red: VB `on_position_closed` FunctionDef 존재 + `register_cooldown_after_exit` Call ≥ 1.

    현재 FAIL = VB on_position_closed override 부재 (고아 배선).
    사이클 191 A-2 답습 — Green 후 배선 확립.
    """
    tree = _parse(_vb_mod)
    fn = _find_func(tree, "on_position_closed")
    assert fn is not None, (
        "volatility_breakout.on_position_closed override 신설 의무 (고아 쿨다운 배선)"
    )
    calls = _register_calls(fn)
    assert len(calls) >= 1, (
        "volatility_breakout.on_position_closed 에 register_cooldown_after_exit Call ≥ 1 의무"
    )


# ---------------------------------------------------------------------------
# (7c) Red — VB DEFAULT_PARAMS reentry_cooldown_days == 2 (AST 정적)
# ---------------------------------------------------------------------------
def test_7c_vb_default_params_cooldown_days_is_2_ast() -> None:
    """(7c) Red: VB DEFAULT_PARAMS Dict 에 `reentry_cooldown_days: 2` 리터럴.

    현재 FAIL = 키 부재. 동작 테스트(test_8) 와 AST 이중 가드.
    """
    tree = _parse(_vb_mod)
    dnode = _default_params_dict(tree)
    assert dnode is not None, "VB DEFAULT_PARAMS Dict 노드 존재 의무"
    val = _dict_const_value(dnode, "reentry_cooldown_days")
    assert val is not _MISSING, "VB DEFAULT_PARAMS 에 reentry_cooldown_days 키 신설 의무"
    assert val == 2, "VB reentry_cooldown_days 리터럴 == 2 (당일청산 특성)"
