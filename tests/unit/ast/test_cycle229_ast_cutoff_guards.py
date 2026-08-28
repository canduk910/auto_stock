"""사이클 229 Red — 매수 컷 AST 영구 가드 (명세 W4-8).

명세 정본 `_workspace/red/cycle229_buy_cutoff_spec.md` W4-8 /
자문 정본 `_workspace/domain_consult/cycle229_vb_1530_single_price.md` §3 구현 3원칙 /
행위 분해 `_workspace/red/cycle229_behaviors.md` §5.

**Red 단계 — 실패 테스트만. 프로덕션 미변경.**

| # | 가드 | 지키는 것 |
|---|---|---|
| G-1 | `check_buy_signal` 안에 naive `datetime.now().time()` **0건** | 컨테이너 `TZ` 의존 제거 (구현 3원칙 #1) |
| G-2 | **모듈 레벨** `BUY_CUTOFF_KST == time(15, 20)` | 상수가 클래스/params 안으로 숨지 않는다 |
| G-3 | `BUY_CUTOFF_KST` 첫 참조 < prev 상태 첫 참조 (라인 순서) | 게이트를 아래로 내리는 뮤테이션 검출 (구현 3원칙 #2) |
| G-4 | 두 전략 파일이 서로를 import 하지 않는다 | 상수 공유 금지 = 파일 간 결합 회피 |
| G-5 | 게이트 판정문이 tz-aware `datetime.now(<tz>)` 를 동반 | G-1(음성)의 **양성** 짝 |

## ⚠️ 범위 — BFB/VCP 는 이 가드가 다루지 않는다

`bull_flag_breakout.py:929` / `vcp_breakout.py:1045` 의 naive `datetime.now().time()` 은
**P2-6 에 등재된 별건 결함**이고 이번 사이클의 시정 범위가 아니다. G-1 을 그 두 파일로
넓히면 사이클 229 가 즉시 RED 가 되어 이 사이클의 Green 판정이 불가능해진다.
자문이 지목한 따라야 할 선례는 kojiro `:796` `datetime.now(KST).time()` 이다.

## G-3 의 비-공허성 (사이클 224 교훈)

사이클 224 의 AST 가드는 기준선을 **호출 위치 자신**에서 유도해 "정의상 항상 참" 이었고
뮤테이션 전후 모두 통과했다. G-3 의 기준선은 `_prev_price` / `_prev_prdy_rate` 의 첫 참조
라인 — **게이트 위치와 독립**이다. 게이트를 그 아래로 옮기면 부등식이 즉시 뒤집히고,
상수가 아예 없으면 "참조 0건" 으로 명시 FAIL 한다(조용한 vacuous PASS 없음).
prev 상태 참조가 0건이면 rig 전제가 깨진 것이므로 그 역시 FAIL 시킨다.
"""

from __future__ import annotations

import ast
from datetime import time
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import read_module_source as _read

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]

# rel_path → check_buy_signal 안에서 쓰이는 "이전 틱 상태" 속성명 (G-3 기준선)
_TARGETS: dict[str, tuple[str, str]] = {
    "vb": ("src/engine/strategies/volatility_breakout.py", "_prev_price"),
    "momentum": ("src/engine/strategies/momentum.py", "_prev_prdy_rate"),
}
_IDS = list(_TARGETS)
_CASES = [_TARGETS[k] for k in _IDS]


# ---------------------------------------------------------------------------
# AST 헬퍼
# ---------------------------------------------------------------------------
def _tree(rel: str) -> tuple[ast.Module, str]:
    src = _read(_REPO_ROOT / rel)
    return ast.parse(src), src


def _func(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _is_datetime_now_call(node: ast.AST) -> bool:
    """`datetime.now(...)` / `datetime.today(...)` 형태의 Call 인가."""
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    if not isinstance(fn, ast.Attribute) or fn.attr not in ("now", "today"):
        return False
    base = fn.value
    if isinstance(base, ast.Name) and base.id == "datetime":
        return True
    return isinstance(base, ast.Attribute) and base.attr == "datetime"


def _is_naive_now_call(node: ast.AST) -> bool:
    """인자 없는 `datetime.now()` = 컨테이너 로컬 타임존 의존."""
    return (
        _is_datetime_now_call(node)
        and not getattr(node, "args", [])
        and not getattr(node, "keywords", [])
    )


def _is_tz_aware_now_call(node: ast.AST) -> bool:
    """인자 있는 `datetime.now(KST)` = 타임존 명시."""
    return _is_datetime_now_call(node) and bool(
        getattr(node, "args", []) or getattr(node, "keywords", [])
    )


def _names_bound_to(func: ast.AST, predicate) -> set[str]:
    """함수 안에서 `predicate` 를 만족하는 표현식이 대입된 지역 변수명 집합.

    한 단계 대입을 전이적으로 되짚는다 — `_now = datetime.now(KST)` 처럼 지역변수를
    경유해도 가드가 거짓 판정하지 않도록(사이클 226 자기 가드 공허화 재발 방지).
    """
    bound: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if value is None:
            continue
        if not any(predicate(sub) for sub in ast.walk(value)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for tgt in targets:
            if isinstance(tgt, ast.Name):
                bound.add(tgt.id)
    return bound


def _ref_linenos(node: ast.AST, symbol: str) -> list[int]:
    """`symbol` 을 Name 또는 Attribute 로 참조하는 모든 라인."""
    hits: list[int] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == symbol:
            hits.append(sub.lineno)
        elif isinstance(sub, ast.Attribute) and sub.attr == symbol:
            hits.append(sub.lineno)
    return sorted(hits)


# ===========================================================================
# G-1 — [Green 구속] naive `datetime.now().time()` 0건
# ===========================================================================
@pytest.mark.parametrize(("rel", "_prev_attr"), _CASES, ids=_IDS)
def test_g1_no_naive_now_time_in_check_buy_signal(rel: str, _prev_attr: str) -> None:
    """G-1: 컷 판정이 컨테이너 `TZ` 환경변수에 의존하면 안 된다.

    `TZ=Asia/Seoul` 이 깨지는 순간(도커 이미지 변경·CI·로컬 실행) 컷 시각이 통째로
    9시간 어긋난다 — 매수를 **막아야 할 때 열고, 열어야 할 때 막는다**.

    착수 시점 두 파일 모두 `check_buy_signal` 안에 `.time()` 호출 자체가 없어 지금은
    통과한다(공허). Green 이 naive 로 구현하는 순간 RED 가 되는 것이 이 가드의 목적이다.

    ⚠️ 이 가드는 `.time()` 만 본다 — VB `:873` 의 `datetime.now().strftime("%H:%M:%S")`
    (buy_signals 표시용)는 범위 밖이다. 그 줄까지 건드리면 이번 사이클이 표시 행위를
    바꾸게 되고, 그건 명세에 없다.
    """
    tree, _ = _tree(rel)
    fn = _func(tree, "check_buy_signal")
    assert fn is not None, f"{rel} 에 `check_buy_signal` 부재 — rig 전제 붕괴"

    naive_locals = _names_bound_to(fn, _is_naive_now_call)

    bad: list[int] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if not isinstance(f, ast.Attribute) or f.attr != "time":
            continue
        base = f.value
        if _is_naive_now_call(base):
            bad.append(node.lineno)
        elif isinstance(base, ast.Name) and base.id in naive_locals:
            bad.append(node.lineno)

    assert bad == [], (
        f"{rel}::check_buy_signal 에 naive `datetime.now().time()` (lines {bad}). "
        "BFB `:929`/VCP `:1045` 의 naive 는 **P2-6 등재 결함**이지 따라할 선례가 아니다 — "
        "선례는 kojiro `:796` `datetime.now(KST).time()`"
    )


# ===========================================================================
# G-2 — [RED] 모듈 레벨 상수 `BUY_CUTOFF_KST == time(15, 20)`
# ===========================================================================
@pytest.mark.parametrize(("rel", "_prev_attr"), _CASES, ids=_IDS)
def test_g2_module_level_cutoff_constant(rel: str, _prev_attr: str) -> None:
    """G-2 (RED): 상수는 **모듈 레벨**이어야 한다.

    클래스 속성이나 `DEFAULT_PARAMS` 안으로 들어가면 `strategy_config.params` 머지
    (`__init__` 의 `{**DEFAULT_PARAMS, **config.params}`)를 타서 DB 로 덮인다.
    VB 의 OVERNIGHT 금지는 DB 토글 하나로 뚫려선 안 되는 규칙이다.
    """
    tree, _ = _tree(rel)
    module_level = [
        node for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(t, ast.Name) and t.id == "BUY_CUTOFF_KST"
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
    ]
    assert module_level, (
        f"{rel} 에 **모듈 레벨** `BUY_CUTOFF_KST` 대입 부재 "
        "(클래스 속성/DEFAULT_PARAMS 안은 DB override 경로에 노출된다)"
    )

    mod_name = rel.removesuffix(".py").replace("/", ".")
    mod = __import__(mod_name, fromlist=["BUY_CUTOFF_KST"])
    assert getattr(mod, "BUY_CUTOFF_KST", None) == time(15, 20), (
        "컷 시각은 15:20 — 연속매매가 존재하는 마지막 순간이다"
    )


# ===========================================================================
# G-3 — [RED] 게이트가 prev 상태 참조보다 **앞**
# ===========================================================================
@pytest.mark.parametrize(("rel", "prev_attr"), _CASES, ids=_IDS)
def test_g3_gate_precedes_prev_state_reference(rel: str, prev_attr: str) -> None:
    """G-3 (RED): 게이트를 `_prev_price`/`_prev_prdy_rate` 아래로 내리면 안 된다.

    뒤에 두면 종가/예상체결가가 baseline 으로 기록된다. VB `prepare()` 의
    `_prev_price.clear()` 가 익일 오염은 막지만, **당일 장중 재시작 시** 그 값이
    baseline 이 되어 09:00~15:20 재개 구간에서 거짓 미돌파를 만든다.
    momentum 은 첫 틱 기록 자체가 그 dict 라 영향이 더 직접적이다.

    기준선(prev 상태 첫 참조)이 게이트 위치와 **독립**이라 이 가드는 공허하지 않다 —
    게이트를 내리는 뮤테이션에서 부등식이 그대로 뒤집힌다.
    """
    tree, _ = _tree(rel)
    fn = _func(tree, "check_buy_signal")
    assert fn is not None, f"{rel} 에 `check_buy_signal` 부재 — rig 전제 붕괴"

    gate_lines = _ref_linenos(fn, "BUY_CUTOFF_KST")
    prev_lines = _ref_linenos(fn, prev_attr)

    assert prev_lines, (
        f"{rel}::check_buy_signal 에 `{prev_attr}` 참조 0건 — 이 가드의 기준선이 사라졌다. "
        "리팩터로 필드명이 바뀌었다면 이 테스트의 `_TARGETS` 를 함께 갱신하라"
    )
    assert gate_lines, (
        f"{rel}::check_buy_signal 이 `BUY_CUTOFF_KST` 를 참조하지 않는다 — 게이트 미배선"
    )
    assert gate_lines[0] < prev_lines[0], (
        f"{rel}: 컷 게이트(line {gate_lines[0]})가 `{prev_attr}`(line {prev_lines[0]}) "
        "보다 뒤에 있다 — 컷 틱이 baseline 을 오염시킨다"
    )


# ===========================================================================
# G-4 — [보존] 두 전략 파일이 서로를 import 하지 않는다
# ===========================================================================
@pytest.mark.parametrize(("rel", "_prev_attr"), _CASES, ids=_IDS)
def test_g4_no_cross_strategy_import(rel: str, _prev_attr: str) -> None:
    """G-4: 값이 같다고 상수를 공유하면 두 전략의 진입 정체성이 한 리터럴에 묶인다.

    한쪽만 바꾸려는 미래의 변경이 다른 쪽을 조용히 끌고 간다. 명세 W2 가 명시적으로
    "상수 공유 금지 — 전략별 자기 상수, 파일 간 결합 회피" 를 못 박았다.
    """
    other = {"volatility_breakout", "momentum"} - {Path(rel).stem}
    (other_mod,) = other

    tree, _ = _tree(rel)
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and other_mod in (node.module or ""):
            hits.append(node.lineno)
        elif isinstance(node, ast.Import):
            hits.extend(node.lineno for a in node.names if other_mod in a.name)

    assert hits == [], (
        f"{rel} 이 `{other_mod}` 를 import 한다 (lines {hits}) — 전략 간 결합 발생"
    )


# ===========================================================================
# G-5 — [RED] 게이트 판정문이 tz-aware `datetime.now(<tz>)` 를 동반
# ===========================================================================
@pytest.mark.parametrize(("rel", "_prev_attr"), _CASES, ids=_IDS)
def test_g5_gate_statement_uses_tz_aware_now(rel: str, _prev_attr: str) -> None:
    """G-5 (RED): G-1(naive 금지, 음성)의 **양성** 짝.

    G-1 만으로는 "시각을 아예 안 읽는" 구현(예: 보드 멤버십으로 판정)도 통과한다.
    자문이 보드 결합을 명시적으로 반대했다 — MAIN 이 15:39:59 까지 유지되는 이유는
    **종가 흡수 + 청산 평가 유지**이고 매수 목적으로 정해진 값이 아니라서, 매수 컷을
    보드에 결합하면 청산 마진을 조정할 때 매수창이 따라 움직인다.

    지역변수 경유(`_now = datetime.now(KST)` → `_now.time() >= BUY_CUTOFF_KST`)도
    전이적으로 인정한다.
    """
    tree, _ = _tree(rel)
    fn = _func(tree, "check_buy_signal")
    assert fn is not None, f"{rel} 에 `check_buy_signal` 부재 — rig 전제 붕괴"

    tz_locals = _names_bound_to(fn, _is_tz_aware_now_call)

    def _stmt_is_tz_aware(stmt: ast.stmt) -> bool:
        for sub in ast.walk(stmt):
            if _is_tz_aware_now_call(sub):
                return True
            if isinstance(sub, ast.Name) and sub.id in tz_locals:
                return True
        return False

    carriers = [
        stmt for stmt in ast.walk(fn)
        if isinstance(stmt, ast.stmt) and _ref_linenos(stmt, "BUY_CUTOFF_KST")
    ]
    assert carriers, (
        f"{rel}::check_buy_signal 이 `BUY_CUTOFF_KST` 를 참조하지 않는다 — 게이트 미배선"
    )
    assert any(_stmt_is_tz_aware(stmt) for stmt in carriers), (
        f"{rel}: 컷 판정문에 tz 인자 있는 `datetime.now(...)` 가 없다. "
        "판정 소스는 보드가 아니라 **KST 명시 시각**이어야 한다"
    )
