"""사이클 183 (2026-06-28) Red — stale-3 + stale-4 AST 정적 가드.

source 텍스트 스캔 금지 — AST 노드 검사 (사이클 167/179 false-positive 교훈).

## stale-3 AST (KST 강제)
- AST-3a: `_last_scan_time` 할당 RHS 의 `datetime.now(...)` 호출은 인자 ≥1 (KST_TZ) 의무.
- AST-3b: 모듈 전역 인자 0개 `datetime.now()` Call 0건 (L681 naive now 잔존 0).
  현재 L681 `datetime.now()` 0-arg 1건 존재 → 양쪽 FAIL (Red). Green 후 0건 → PASS.

## stale-4 AST (캐시 경유)
- AST-4: `_apply_price_filter` 함수 본문이 `_get_price_filter_for_scanner()` 호출 +
  `get_price_filter()` 직접 호출 0건. 현재 직접 `get_price_filter()` → FAIL (Red).
"""
from __future__ import annotations

import ast

import pytest

pytestmark = pytest.mark.unit

_SCANNER = "src/engine/scanner.py"


def _parse_scanner() -> ast.Module:
    import src.engine.scanner as scanner_mod
    with open(scanner_mod.__file__, encoding="utf-8") as f:
        return ast.parse(f.read())


def _is_datetime_now_call(node: ast.AST) -> bool:
    """`datetime.now(...)` Call 노드인가? (Attribute(attr='now', value=Name('datetime')))."""
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    return (
        isinstance(fn, ast.Attribute)
        and fn.attr == "now"
        and isinstance(fn.value, ast.Name)
        and fn.value.id == "datetime"
    )


def _func_node(tree: ast.Module, name: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ===========================================================================
# stale-3 AST-3a — _last_scan_time 할당 now() 인자 ≥1 (KST_TZ)
# ===========================================================================
def test_AST3a_last_scan_time_assignment_now_has_tz_arg():
    """`_last_scan_time` 할당 RHS 의 `datetime.now(...)` 은 인자 ≥1 (KST_TZ) 의무.

    현재 L681 `datetime.now()` 인자 0 → FAIL (Red). Green `datetime.now(KST_TZ)` → PASS.
    """
    tree = _parse_scanner()

    now_calls: list[tuple[int, int, int]] = []  # (lineno, n_args, n_kwargs)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        target_names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if "_last_scan_time" not in target_names:
            continue
        for sub in ast.walk(node.value):
            if _is_datetime_now_call(sub):
                now_calls.append((node.lineno, len(sub.args), len(sub.keywords)))

    assert now_calls, (
        "stale-3 AST-3a — `_last_scan_time = datetime.now(...).strftime(...)` 할당 미발견. "
        "탐지기 결함 또는 할당 구조 변경 — 재점검 의무."
    )
    naive = [(ln, a, k) for (ln, a, k) in now_calls if a == 0 and k == 0]
    assert not naive, (
        "stale-3 AST-3a 위반 — `_last_scan_time` 할당이 인자 0개 naive `datetime.now()` 사용. "
        f"`datetime.now(KST_TZ)` 의무 (위반 위치 {naive})."
    )


# ===========================================================================
# stale-3 AST-3b — 모듈 전역 0-arg datetime.now() Call 0건
# ===========================================================================
def test_AST3b_no_zero_arg_naive_datetime_now_in_module():
    """scanner.py 전역에 인자 0개 `datetime.now()` Call 0건 (naive now 영구 차단).

    현재 L681 1건 → FAIL (Red). Green 후 0건 → PASS.
    (KST_TZ/kst 인자 동반 호출은 카운트 제외 — L220/409/541/685/712 정상.)
    """
    tree = _parse_scanner()

    zero_arg: list[int] = []
    for node in ast.walk(tree):
        if _is_datetime_now_call(node) and not node.args and not node.keywords:
            zero_arg.append(node.lineno)

    assert zero_arg == [], (
        "stale-3 AST-3b 위반 — 인자 0개 naive `datetime.now()` 잔존 "
        f"(위반 라인 {zero_arg}). 모든 시각 데이터 KST 강제 — `datetime.now(KST_TZ)` 의무."
    )


# ===========================================================================
# stale-4 AST-4 — _apply_price_filter 캐시 헬퍼 경유
# ===========================================================================
def test_AST4_apply_price_filter_uses_cached_helper_not_direct():
    """`_apply_price_filter` 본문은 `_get_price_filter_for_scanner()` 호출 +
    `get_price_filter()` 직접 호출 0건 (60s TTL 캐시 경유).

    현재 본문 `await get_price_filter()` 직접 → FAIL (Red).
    Green `await _get_price_filter_for_scanner()` → PASS.

    함수 본문 *범위 한정* (모듈 전역 get_price_filter 호출은
    `_get_price_filter_for_scanner` 내부에 별도 존재 — 정상, 본 가드 대상 외).
    """
    tree = _parse_scanner()
    fn = _func_node(tree, "_apply_price_filter")
    assert fn is not None, "stale-4 AST-4 — `_apply_price_filter` 함수 미발견."

    direct_name_calls: list[str] = []
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
            direct_name_calls.append(sub.func.id)

    assert "_get_price_filter_for_scanner" in direct_name_calls, (
        "stale-4 AST-4 위반 — `_apply_price_filter` 가 캐시 헬퍼 "
        "`_get_price_filter_for_scanner()` 미호출 (60s TTL 캐시 우회)."
    )
    assert "get_price_filter" not in direct_name_calls, (
        "stale-4 AST-4 위반 — `_apply_price_filter` 본문이 `get_price_filter()` 직접 호출 "
        "(캐시 우회). `_get_price_filter_for_scanner()` 경유 의무."
    )
