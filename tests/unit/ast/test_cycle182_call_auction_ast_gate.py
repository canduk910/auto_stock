"""사이클 182 — AST 정적 가드: is_call_auction_now() 시간창 게이트 영구 보존.

대상: ``src/engine/session.py::SessionTracker.is_call_auction_now``

domain-expert 자문: ``_workspace/domain_consult/cycle182_call_auction_time_gate.md``
사이클 167/179 패턴 답습 — source 텍스트 전수 스캔(주석/docstring false positive,
사이클 167 교훈)이 아니라 **AST 노드**만 검사.

가드:
- G-182-AST-1 (HIGH): 코드 분기('110'/'121' 문자열 비교) 는 ``time(...)`` 비교와 ``and``
  동반 의무 (시간창 게이트 영구 보존). 현재 코드 ``in ("110","121")`` 는 게이트 0 →
  FAIL = Red. 미래 게이트 없는 무조건 ``return True`` 재발 영구 차단.
- G-182-AST-2 (LOW, stale-5): 함수 내 naive ``datetime.now()`` (인자 0개) Call 노드 0건.
  현재 코드 L213 ``datetime.now()`` → FAIL = Red. Green = ``datetime.now(_KST)`` 만.
- G-182-AST-3 (sanity): 게이트 대상 코드 상수 '110'/'121' 가 함수 내 실제 존재
  (AST-1 가드 비공허 보장).
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

REPO_ROOT = Path(__file__).resolve().parents[3]
SESSION_PY = REPO_ROOT / "src" / "engine" / "session.py"

assert SESSION_PY.exists(), f"session.py 부재 ({SESSION_PY})"
_SRC = read_module_source(SESSION_PY)
_FUNC = find_function_def(_SRC, "is_call_auction_now")

_CALL_AUCTION_CODES = ("110", "121")


# ───────── AST 헬퍼 (parent 추적 + time() 게이트 검출) ─────────


def _build_parent_map(root: ast.AST) -> dict:
    """root 서브트리의 child→parent 매핑 (ast 는 parent 링크를 안 줌)."""
    parents: dict = {}
    for node in ast.walk(root):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _enclosing_and_boolop(node: ast.AST, parents: dict):
    """node 를 감싸는 가장 가까운 ``BoolOp(And)`` 반환 (없으면 None)."""
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, ast.BoolOp) and isinstance(cur.op, ast.And):
            return cur
        cur = parents.get(cur)
    return None


def _contains_time_call(node: ast.AST) -> bool:
    """서브트리 내 ``time(...)`` 또는 ``X.time(...)`` Call 존재 여부 (시간창 게이트 신호)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name) and func.id == "time":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "time":
                return True
    return False


def _code_constants(func: ast.AST):
    """함수 내 값이 '110'/'121' 인 문자열 Constant 노드.

    docstring 은 단일 Constant(값=전체 문자열)라 ``value in (...)`` 미매칭 → 자동 제외
    (주석/docstring 단순 언급 무시 = 사이클 167 false positive 차단 패턴).
    """
    return [
        n
        for n in ast.walk(func)
        if isinstance(n, ast.Constant) and n.value in _CALL_AUCTION_CODES
    ]


# ───────── 가드 ─────────


def test_function_exists():
    """sanity: 대상 함수 존재."""
    assert _FUNC is not None, "is_call_auction_now 함수 부재 (session.py)"


def test_G_182_AST_3_codes_present_sanity():
    """G-182-AST-3 (sanity): '110'/'121' 코드 상수가 함수 내 실제 존재 → AST-1 비공허.

    현재 코드: 튜플 ``("110","121")`` 내 / Green: ``code == "110"`` 비교 내 — 양쪽 존재.
    """
    found = {c.value for c in _code_constants(_FUNC)}
    assert found == set(_CALL_AUCTION_CODES), (
        f"코드 상수 누락 — AST-1 가드 공허화 위험. 발견: {found}"
    )


def test_G_182_AST_1_code_branch_time_window_gated():
    """G-182-AST-1 (HIGH): 모든 '110'/'121' 코드 상수는 time() 게이트 ``and`` 동반 의무.

    현재 코드: ``if self._last_nxt_mkop_code in ("110","121"): return True`` →
    코드 상수가 BoolOp(And) 밖 + time() 동반 0 → FAIL = Red.
    Green: ``code == "110" and time(8,25) <= t < time(9,5)`` → BoolOp(And) 내부 +
    time() 동반 → 통과. 미래 게이트 없는 무조건 ``return True`` 재발 영구 차단.
    """
    parents = _build_parent_map(_FUNC)
    consts = _code_constants(_FUNC)
    assert consts, "코드 상수 부재 (G-182-AST-3 sanity 참조)"
    for const in consts:
        boolop = _enclosing_and_boolop(const, parents)
        assert boolop is not None and _contains_time_call(boolop), (
            f"[게이트 결함] 코드 상수 {const.value!r} 가 time() 시간창 게이트 `and` "
            "미동반 — 고착 코드 시간 무관 영구 True 결함 재발 위험. "
            "사이클 182 = 코드 분기는 `code == ... and time(...) <= t < time(...)` 의무."
        )


def test_G_182_AST_2_no_naive_datetime_now():
    """G-182-AST-2 (LOW, stale-5): 함수 내 naive ``datetime.now()`` (인자 0개) Call 0건.

    현재 코드 L213 ``now = now or datetime.now()`` → 인자 0개 → FAIL = Red.
    Green: ``datetime.now(_KST)`` (인자 1개) 만 → 통과 (KST 강제, CLAUDE.md 불변식).
    """
    naive_now_calls = []
    for sub in ast.walk(_FUNC):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        is_now = (isinstance(func, ast.Attribute) and func.attr == "now") or (
            isinstance(func, ast.Name) and func.id == "now"
        )
        if is_now and not sub.args and not sub.keywords:
            naive_now_calls.append(sub)
    assert not naive_now_calls, (
        f"[stale-5 결함] is_call_auction_now 내 naive datetime.now() (인자 0개) "
        f"{len(naive_now_calls)}건 — KST 강제 위반. Green = datetime.now(_KST)."
    )
