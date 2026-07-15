"""사이클 213 AST Red — LTV 재진입 쿨다운 배선 구조 정적 가드.

작업 지시서 = `_workspace/red/cycle213_ltv_reentry_cooldown.md` §회귀 가드 (4 AST)(6).

source 텍스트 grep 금지 — AST 노드 검사 (사이클 167/179/185/191/201 교훈: 주석/별칭/공백 false-positive 차단).

- G-213-4-AST (HIGH, DISCARD-ORDER): LTV `on_position_closed` 에서 `was_limit_up`(멤버십
  판정)이 `_limit_up_reached.discard` Call *전* 라인. discard 먼저면 was_limit_up 항상
  False → 상한가 면제 붕괴. Green 후 순서 역전 영구 차단.
- G-213-6 (HIGH, NO-DAILY-RESET): LTV `_reset_daily_state`/`prepare` 본체에
  `_cooldown_until` mutation 0건 (multi-day 상태 영구 보호). 현행 미접촉 PASS.
  사이클 191 G-191-NO-DAILY-RESET 답습.
- 부가 Red: LTV `on_position_closed` 내 `register_cooldown_after_exit` Call ≥ 1 +
  `_limit_up_reached.discard` Call ≥ 1.
- 부가 Red: LTV DEFAULT_PARAMS `reentry_cooldown_days: 2` 리터럴.
- SAFETY 불변식: 다른 전략 값 불변 (BFB=3 / VCP=7 / VB=2).
"""

from __future__ import annotations

import ast

import pytest

import src.engine.strategies.bull_flag_breakout as _bfb_mod
import src.engine.strategies.long_tail_volatility as _ltv_mod
import src.engine.strategies.vcp_breakout as _vcp_mod
import src.engine.strategies.volatility_breakout as _vb_mod

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# AST 헬퍼 (사이클 191/201 답습)
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


def _is_limit_up_attr(node: ast.AST) -> bool:
    """`*._limit_up_reached` Attribute 노드 판별."""
    return isinstance(node, ast.Attribute) and node.attr == "_limit_up_reached"


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


def _limit_up_discard_calls(func_node: ast.AST) -> list:
    """`*._limit_up_reached.discard(...)` Call 노드 목록."""
    return [
        n
        for n in ast.walk(func_node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "discard"
        and _is_limit_up_attr(n.func.value)
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


_MISSING = object()


def _dict_const_value(dnode: ast.Dict, key: str):
    for k, v in zip(dnode.keys, dnode.values):
        if isinstance(k, ast.Constant) and k.value == key:
            if isinstance(v, ast.Constant):
                return v.value
            if isinstance(v, ast.UnaryOp) and isinstance(v.operand, ast.Constant):
                return v.operand.value
            return v
    return _MISSING


# ---------------------------------------------------------------------------
# G-213-4-AST (HIGH, DISCARD-ORDER) — was_limit_up 판정이 discard *전*
# ---------------------------------------------------------------------------
def test_g213_4_ast_membership_read_before_discard() -> None:
    """G-213-4-AST (HIGH): LTV `on_position_closed` 에서 `_limit_up_reached` 멤버십 판정이
    `_limit_up_reached.discard` Call *전* 라인.

    was_limit_up = ticker in self._limit_up_reached  (discard 전, membership Compare)
    self._limit_up_reached.discard(ticker)           (그 후)
    → discard 먼저면 was_limit_up 항상 False → 상한가 면제 붕괴.

    현재 FAIL = LTV on_position_closed 에 `_limit_up_reached` 멤버십 Compare(In) 부재
    (현행은 discard 만 하는 사이클 185 override) → membership 라인 미검출.
    Green 후 membership 판정이 discard 앞이면 PASS.
    """
    tree = _parse(_ltv_mod)
    fn = _find_func(tree, "on_position_closed")
    assert fn is not None, "LTV on_position_closed override 존재 의무"

    # membership Compare: `_limit_up_reached` 를 대상으로 한 `in` 비교 (ast.Compare, ops=[In])
    membership_lines = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Compare) and any(
            isinstance(op, ast.In) for op in node.ops
        ):
            # 비교 대상(comparators) 중 하나가 *._limit_up_reached 여야 함
            if any(_is_limit_up_attr(c) for c in node.comparators):
                membership_lines.append(node.lineno)

    discard_calls = _limit_up_discard_calls(fn)
    discard_lines = [c.lineno for c in discard_calls]

    assert membership_lines, (
        "LTV on_position_closed 에 `ticker in self._limit_up_reached` 멤버십 판정 라인 부재 — "
        "상한가 면제 게이트(was_limit_up) 신설 의무 (discard 전 판정)"
    )
    assert discard_lines, (
        "LTV on_position_closed 에 `_limit_up_reached.discard(...)` 부재 (사이클 185 보존)"
    )
    assert min(membership_lines) < min(discard_lines), (
        "was_limit_up 멤버십 판정(line %s)이 _limit_up_reached.discard(line %s) *전* 이어야 함 — "
        "순서 역전 시 was_limit_up 항상 False → 상한가 면제 붕괴 (위험 시나리오 1)"
        % (min(membership_lines), min(discard_lines))
    )


# ---------------------------------------------------------------------------
# 부가 Red — on_position_closed 내 register + discard 호출 존재 의무
# ---------------------------------------------------------------------------
def test_ltv_on_position_closed_calls_register_and_discard() -> None:
    """(Red): LTV `on_position_closed` 에 register_cooldown_after_exit Call ≥ 1
    AND `_limit_up_reached.discard` Call ≥ 1.

    현재 FAIL = register Call 부재 (현행 override 는 discard 만).
    사이클 201 (7b) + 사이클 185 discard 결합 = LTV 특유 (면제 게이트).
    """
    tree = _parse(_ltv_mod)
    fn = _find_func(tree, "on_position_closed")
    assert fn is not None, "LTV on_position_closed override 신설 의무"

    reg = _register_calls(fn)
    assert len(reg) >= 1, (
        "LTV on_position_closed 에 register_cooldown_after_exit Call ≥ 1 의무 (고아 재발 차단)"
    )
    disc = _limit_up_discard_calls(fn)
    assert len(disc) >= 1, (
        "LTV on_position_closed 에 _limit_up_reached.discard Call ≥ 1 의무 (사이클 185 보존)"
    )


# ---------------------------------------------------------------------------
# G-213-6 (HIGH, NO-DAILY-RESET) — LTV 일일/prepare 리셋 절대 금지
# ---------------------------------------------------------------------------
def test_g213_6_no_cooldown_reset_in_ltv_daily_or_prepare() -> None:
    """G-213-6 (NO-DAILY-RESET): LTV `_reset_daily_state`/`prepare` 에 `_cooldown_until` mutation 0건.

    multi-day 상태 → 일일/prepare 리셋 시 2영업일 쿨다운 매일 소멸 = 익일 재진입 방어 붕괴.
    LTV 는 `prepare` 존재 (사이클 180 에서 `_targets`/`_open_confirmed`/`_prev_price` 만 clear).
    `_cooldown_until` 은 청산 모드 결합 multi-day → 절대 미접촉. `_reset_daily_state` override
    신설 시에도 접촉 영구 금지. 현행 미접촉 PASS (미래 회귀 차단, 사이클 191 답습).
    """
    tree = _parse(_ltv_mod)
    for fname in ("_reset_daily_state", "prepare"):
        fn = _find_func(tree, fname)
        if fn is None:
            continue  # override 부재 = 미접촉 (PASS)
        muts = _cooldown_mutations(fn)
        assert not muts, (
            f"long_tail_volatility.{fname} 에 _cooldown_until mutation {len(muts)}건 — "
            "multi-day 쿨다운 일일 소멸 영구 차단 위반 (사이클 191 G-191-NO-DAILY-RESET 답습)"
        )


# ---------------------------------------------------------------------------
# 부가 Red — LTV DEFAULT_PARAMS reentry_cooldown_days == 2 (AST 정적)
# ---------------------------------------------------------------------------
def test_ltv_default_params_cooldown_days_is_2_ast() -> None:
    """(Red): LTV DEFAULT_PARAMS Dict 에 `reentry_cooldown_days: 2` 리터럴.

    현재 FAIL = 키 부재. 동작 테스트(G-213-1) 와 AST 이중 가드.
    """
    tree = _parse(_ltv_mod)
    dnode = _default_params_dict(tree)
    assert dnode is not None, "LTV DEFAULT_PARAMS Dict 노드 존재 의무"
    val = _dict_const_value(dnode, "reentry_cooldown_days")
    assert val is not _MISSING, "LTV DEFAULT_PARAMS 에 reentry_cooldown_days 키 신설 의무"
    assert val == 2, "LTV reentry_cooldown_days 리터럴 == 2 (당일 모드 = VB 동형)"


# ---------------------------------------------------------------------------
# SAFETY 불변식 — 다른 전략 reentry_cooldown_days 값 불변 (BFB=3 / VCP=7 / VB=2)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mod,expected",
    [(_bfb_mod, 3), (_vcp_mod, 7), (_vb_mod, 2)],
    ids=["bfb=3", "vcp=7", "vb=2"],
)
def test_other_strategy_cooldown_days_unchanged(mod, expected) -> None:
    """(SAFETY): BFB==3 / VCP==7 / VB==2 DEFAULT_PARAMS 값 불변.

    사이클 213 은 LTV 단독 신설 → 다른 3전략 값 변경 0 (혼선 방지). 현행 PASS (불변식).
    """
    tree = _parse(mod)
    dnode = _default_params_dict(tree)
    assert dnode is not None, f"{mod.__name__} DEFAULT_PARAMS Dict 노드 존재 의무"
    val = _dict_const_value(dnode, "reentry_cooldown_days")
    assert val is not _MISSING, f"{mod.__name__} reentry_cooldown_days 키 존재 의무"
    assert val == expected, (
        f"{mod.__name__} reentry_cooldown_days == {expected} 불변 (사이클 213 LTV 신설 무관)"
    )
