"""사이클 184 (2026-06-28) Red — 2-pass 슬롯 계산 풀 기반 AST 정적 가드.

source 텍스트 스캔 금지 — AST 노드 검사 (사이클 167/179 false-positive 교훈).
범위 한정: `subscribe_filtered_stocks` 의 `remaining` *할당* 노드만 대상
(L1166 `total_subscribed = len(kis_ws._subscriptions)` 드롭 요약 로그 라인 = 대상 외, 시정 범위 외).

## 가드 (모두 현재 FAIL → Green 후 PASS)
- AST-1: `remaining` 할당이 `len(kis_ws._subscriptions)`(메인 단독) 잔존 0건.
- AST-2: `remaining` 할당이 `len(kis_ws_pool._subscriptions)`(풀 union) 사용
         (= `get_subscribed_tickers()` TICK-only 아닌 `_subscriptions` 전 tr_id property).
- AST-3: `subscribe_filtered_stocks` 가 `kis_ws_pool.get_session_status` 호출 (풀 총용량 세션 카운트).
- AST-4: 탐지기 self-test (false-negative 차단) — PASS 항상.
"""
from __future__ import annotations

import ast

import pytest

pytestmark = pytest.mark.unit


def _parse_scanner() -> ast.Module:
    import src.engine.scanner as scanner_mod
    with open(scanner_mod.__file__, encoding="utf-8") as f:
        return ast.parse(f.read())


def _func_node(tree: ast.AST, name: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _remaining_assigns(fn: ast.AST) -> list[ast.Assign]:
    """fn 내부 target name 'remaining' 인 ast.Assign 노드 리스트."""
    out: list[ast.Assign] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if "remaining" in names:
                out.append(node)
    return out


def _len_subscriptions_objs(value: ast.AST) -> list[str]:
    """value 하위에서 `len(X._subscriptions)` 의 X(Name id) 목록 반환.

    AST 노드 검사 — `len` Call + 단일 arg Attribute(attr='_subscriptions', value=Name).
    """
    objs: list[str] = []
    for sub in ast.walk(value):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "len"
            and sub.args
        ):
            arg = sub.args[0]
            if (
                isinstance(arg, ast.Attribute)
                and arg.attr == "_subscriptions"
                and isinstance(arg.value, ast.Name)
            ):
                objs.append(arg.value.id)
    return objs


# ===========================================================================
# AST-1 — remaining 할당에 메인 단독 len(kis_ws._subscriptions) 잔존 0건
# ===========================================================================
def test_AST1_no_main_solo_subscriptions_in_remaining():
    """`subscribe_filtered_stocks` 의 `remaining` 할당이 `len(kis_ws._subscriptions)`
    (메인 단독) 미사용 (잔존 0건).

    현재 L1118/L1146 `remaining = MAX_SUBSCRIPTIONS - len(kis_ws._subscriptions)` → FAIL (Red).
    Green `remaining = _pool_total_slots - len(kis_ws_pool._subscriptions)` → PASS.
    (L1166 `total_subscribed` 할당은 'remaining' 타깃 아님 → 대상 외, false-positive 없음.)
    """
    fn = _func_node(_parse_scanner(), "subscribe_filtered_stocks")
    assert fn is not None, "AST-1 — `subscribe_filtered_stocks` 미발견."

    assigns = _remaining_assigns(fn)
    assert len(assigns) >= 1, (
        "AST-1 탐지기 결함 또는 구조 변경 — `remaining` 할당 미발견 (재점검 의무)."
    )

    violations: list[str] = []
    for a in assigns:
        if "kis_ws" in _len_subscriptions_objs(a.value):
            violations.append(
                f"scanner.py:L{a.lineno} — `remaining` 할당이 메인 단독 "
                f"`len(kis_ws._subscriptions)` 사용 (풀 총용량 미반영)"
            )

    assert not violations, (
        "AST-1 (Red) — 2-pass 슬롯 계산이 메인 단독 카운트 사용. 보조 세션 존재 시 "
        "잔여 슬롯 오산(과다 drop). 풀 union `len(kis_ws_pool._subscriptions)` 의무:\n"
        + "\n".join(violations)
    )


# ===========================================================================
# AST-2 — remaining 할당이 풀 union len(kis_ws_pool._subscriptions) 사용
# ===========================================================================
def test_AST2_remaining_uses_pool_union_subscriptions():
    """`remaining` 할당이 풀 union `len(kis_ws_pool._subscriptions)` 사용 의무.

    `get_subscribed_tickers()`(TICK-only) 아닌 `_subscriptions`(전 tr_id 합집합) →
    체결통보/장운영정보 구독도 슬롯 점유하므로 총량 정합 (gate #4).

    현재: remaining 할당이 `kis_ws`(메인) 만 참조 → FAIL (Red).
    Green: `kis_ws_pool._subscriptions` → PASS.
    """
    fn = _func_node(_parse_scanner(), "subscribe_filtered_stocks")
    assert fn is not None, "AST-2 — `subscribe_filtered_stocks` 미발견."

    assigns = _remaining_assigns(fn)
    assert len(assigns) >= 1, "AST-2 탐지기 결함 — `remaining` 할당 미발견."

    bad: list[str] = []
    for a in assigns:
        objs = _len_subscriptions_objs(a.value)
        if "kis_ws_pool" not in objs:
            bad.append(
                f"scanner.py:L{a.lineno} — `remaining` 할당 RHS 가 "
                f"`len(kis_ws_pool._subscriptions)` 미사용 (실제 len 대상={objs})"
            )

    assert not bad, (
        "AST-2 (Red) — `remaining` 슬롯 계산이 풀 union(`kis_ws_pool._subscriptions`) 미사용. "
        "보조 세션 합산 슬롯 정합 의무:\n" + "\n".join(bad)
    )


# ===========================================================================
# AST-3 — subscribe_filtered_stocks 가 kis_ws_pool.get_session_status 호출
# ===========================================================================
def test_AST3_uses_pool_get_session_status_for_total_slots():
    """`subscribe_filtered_stocks` 가 `kis_ws_pool.get_session_status()` 호출 (풀 총용량 산정).

    `_pool_total_slots = MAX_SUBSCRIPTIONS × len(get_session_status())` = 1+N 세션 정합.
    현재: 미호출 → FAIL (Red). Green: 호출 → PASS.
    """
    fn = _func_node(_parse_scanner(), "subscribe_filtered_stocks")
    assert fn is not None, "AST-3 — `subscribe_filtered_stocks` 미발견."

    found = False
    for sub in ast.walk(fn):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "get_session_status"
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id == "kis_ws_pool"
        ):
            found = True
            break

    assert found, (
        "AST-3 (Red) — `kis_ws_pool.get_session_status()` 미호출. 풀 총용량 "
        "`MAX_SUBSCRIPTIONS × (1+보조수)` 산정에 세션 카운트 필요."
    )


# ===========================================================================
# AST-4 — 탐지기 self-test (false-negative 차단, PASS 항상)
# ===========================================================================
def test_AST4_detector_self_test():
    """`_len_subscriptions_objs` 탐지기 정확성 self-test (사이클 167 false-negative 교훈).

    합성 스니펫으로 메인 단독 / 풀 union 패턴을 정확히 식별하는지 검증.
    탐지기 자체가 silent 무력화(항상 빈 리스트)되면 AST-1/2 가 위양성 PASS → 영구 차단.
    """
    bad = ast.parse("remaining = MAX_SUBSCRIPTIONS - len(kis_ws._subscriptions)")
    good = ast.parse("remaining = _pool_total_slots - len(kis_ws_pool._subscriptions)")

    bad_assign = bad.body[0]
    good_assign = good.body[0]
    assert isinstance(bad_assign, ast.Assign) and isinstance(good_assign, ast.Assign)

    assert _len_subscriptions_objs(bad_assign.value) == ["kis_ws"], (
        "AST-4 self-test — 메인 단독 패턴 탐지 실패 (탐지기 결함)."
    )
    assert _len_subscriptions_objs(good_assign.value) == ["kis_ws_pool"], (
        "AST-4 self-test — 풀 union 패턴 탐지 실패 (탐지기 결함)."
    )

    # _remaining_assigns 도 self-test (타깃 name 식별)
    fn = ast.parse(
        "def f():\n"
        "    remaining = 1 - len(kis_ws._subscriptions)\n"
        "    total_subscribed = len(kis_ws._subscriptions)\n"
    ).body[0]
    rem = _remaining_assigns(fn)
    assert len(rem) == 1, (
        "AST-4 self-test — `remaining` 할당만 식별해야 함 "
        "(total_subscribed 라인 제외 = false-positive 차단)."
    )
