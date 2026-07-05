"""사이클 193 (2026-07-04) Red — immediate 신선도 게이트 AST/구조 가드 (F-10).

source 텍스트 grep 금지 — AST 노드 검사 (사이클 167/179/184/187 false-positive 교훈).
`tests/unit/ast/_ast_helpers.py` 재사용.

가드:
- F-10-1: scheduler 게이트 대상 2 wrapper (basics/master) 의 `run_periodic_task_loop`
  호출에 `immediate_skip_if_fresh_hours` 키워드 명시. (사이클 193 검증 워크플로우 결과 —
  멱등 있는 daily_load/full_universe/purge 는 off-by-one/self-heal 위험 + burst 아님 →
  게이트 대상에서 제외, basics/master 만 = 멱등 없는 실제 burst).
- F-10-2: 게이트 미대상 4 wrapper (full_universe/daily_load/purge/evening_funnel) 부재.
- F-10-3: task_loop_helper 모듈-레벨 `IMMEDIATE_FRESH_SKIP_HOURS` 상수 존재.
- F-10-4: 게이트 경로 naive `datetime.now()` 0건 (KST 강제, CLAUDE.md).
"""

from __future__ import annotations

import ast

import pytest

from tests.unit.ast._ast_helpers import (
    find_constant_value,
    find_function_def,
    read_module_source,
)

pytestmark = pytest.mark.unit

_GATE_KW = "immediate_skip_if_fresh_hours"
_HELPER_CALL = "run_periodic_task_loop"

# 게이트 적용 2 wrapper (사이클 193 검증 후 — 멱등 없는 실제 burst 만)
_TARGET_WRAPPERS = (
    "_stock_master_basics_refresh_task_loop",
    "_stock_master_master_load_task_loop",
)
# 게이트 미대상 (멱등/TTL 있어 immediate 이미 저렴 + off-by-one/self-heal 위험 회피 + 범위 외)
_UNGATED_WRAPPERS = (
    "_full_universe_load_task_loop",   # TTL 멱등 + 유니버스 populator self-heal
    "_stock_master_daily_load_task_loop",  # max_bas_dd 멱등 + 후장 완결 off-by-one 회피
    "_stock_master_daily_purge_task_loop",  # 사이클 192 후 저렴 + burst 아님
    "_evening_funnel_capture_task_loop",  # 사용자 결정 범위 외
)


def _scheduler_source() -> str:
    import src.engine.scheduler as _sched

    return read_module_source(_sched.__file__)


def _helper_source() -> str:
    import src.engine.task_loop_helper as _helper

    return read_module_source(_helper.__file__)


def _wrapper_has_gate_kw(scheduler_src: str, wrapper_name: str) -> bool:
    """wrapper 함수 내 run_periodic_task_loop 호출에 게이트 키워드 명시 여부 (AST)."""
    node = find_function_def(scheduler_src, wrapper_name)
    assert node is not None, f"wrapper `{wrapper_name}` 미발견 (구조 변경 재점검)."

    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        func_name = ""
        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr
        if func_name != _HELPER_CALL:
            continue
        for kw in sub.keywords:
            if kw.arg == _GATE_KW:
                return True
    return False


def _count_naive_now(source: str) -> int:
    """naive `datetime.now()` (인자 0 + 키워드 0) Call 개수.

    `datetime.now(KST)` / `now_kst_iso()` 등 tz 명시/헬퍼 경유는 제외.
    """
    tree = ast.parse(source)
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "now":
            if not node.args and not node.keywords:
                count += 1
    return count


# ---------------------------------------------------------------------------
# self-test — 탐지기 false-negative 차단 (사이클 167/184/187 교훈)
# ---------------------------------------------------------------------------
def test_F10_detector_self_test():
    """게이트 키워드 탐지기 + naive now 탐지기 self-test."""
    sample = (
        "class S:\n"
        "    async def _w_yes(self):\n"
        "        await run_periodic_task_loop(scheduler=self, immediate_skip_if_fresh_hours=20.0)\n"
        "    async def _w_no(self):\n"
        "        await run_periodic_task_loop(scheduler=self, initial_delay_secs=0)\n"
    )
    assert _wrapper_has_gate_kw(sample, "_w_yes") is True, "self-test — 게이트 키워드 탐지 실패"
    assert _wrapper_has_gate_kw(sample, "_w_no") is False, "self-test — 부재 오탐"

    assert _count_naive_now("x = datetime.now()\n") == 1, "self-test — naive now 탐지 실패"
    assert _count_naive_now("x = datetime.now(KST)\n") == 0, "self-test — tz 명시 오탐"


# ---------------------------------------------------------------------------
# F-10-1 — scheduler 게이트 대상 2 wrapper (basics/master) 게이트 키워드 명시
# ---------------------------------------------------------------------------
def test_F10_1_gated_wrappers_have_gate_kw():
    """basics/master wrapper run_periodic_task_loop 호출에 게이트 키워드 명시 의무.

    사이클 193 검증 후 게이트 대상 = 멱등 없는 실제 burst 2 task 만.
    """
    scheduler_src = _scheduler_source()
    missing = [
        name for name in _TARGET_WRAPPERS if not _wrapper_has_gate_kw(scheduler_src, name)
    ]
    assert not missing, (
        "F-10-1 — 게이트 키워드 미명시 wrapper:\n  " + ", ".join(missing)
    )


# ---------------------------------------------------------------------------
# F-10-2 (불변식) — 게이트 미대상 4 wrapper 게이트 부재
# ---------------------------------------------------------------------------
def test_F10_2_ungated_wrappers_no_gate():
    """full_universe/daily_load/purge/evening_funnel = 게이트 키워드 부재 의무.

    daily_load/full_universe/purge = 멱등/TTL 이 immediate 를 이미 저렴하게 함 +
    게이트 시 off-by-one(daily_load) / self-heal 상실(populator) 위험 → 제외.
    evening_funnel = 사용자 결정 범위 외.
    """
    scheduler_src = _scheduler_source()
    unexpected = [
        name for name in _UNGATED_WRAPPERS if _wrapper_has_gate_kw(scheduler_src, name)
    ]
    assert not unexpected, (
        "F-10-2 — 게이트 미대상인데 키워드 잔존 wrapper:\n  " + ", ".join(unexpected)
    )


# ---------------------------------------------------------------------------
# F-10-3 (Red FAIL) — task_loop_helper IMMEDIATE_FRESH_SKIP_HOURS 상수 존재
# ---------------------------------------------------------------------------
def test_F10_3_helper_skip_hours_constant_exists():
    """task_loop_helper 모듈-레벨 `IMMEDIATE_FRESH_SKIP_HOURS` 상수 존재 + > 0.

    현재 (미도입) = 상수 부재 → find_constant_value None → FAIL (Red).
    """
    helper_src = _helper_source()
    value = find_constant_value(helper_src, "IMMEDIATE_FRESH_SKIP_HOURS")
    assert value is not None, (
        "F-10-3 (Red) — IMMEDIATE_FRESH_SKIP_HOURS 상수 부재 (모듈-레벨 정의 의무)"
    )
    assert isinstance(value, (int, float)) and value > 0, (
        f"IMMEDIATE_FRESH_SKIP_HOURS 양수 시간 의무 (실측 {value!r})"
    )


# ---------------------------------------------------------------------------
# F-10-4 (Red PASS, 불변식) — task_loop_helper 게이트 경로 naive now 0건 (KST 강제)
# ---------------------------------------------------------------------------
def test_F10_4_helper_no_naive_now():
    """task_loop_helper 본체 naive `datetime.now()` 0건 (KST 강제, CLAUDE.md).

    게이트 경과 계산은 `datetime.now(KST)` / `now_kst_iso()` 만 허용.
    현재 (게이트 부재, datetime 미사용) = 0 → PASS. Green 후에도 0 유지 의무.
    """
    helper_src = _helper_source()
    naive = _count_naive_now(helper_src)
    assert naive == 0, (
        f"F-10-4 — task_loop_helper naive datetime.now() {naive}건 잔존 (KST 강제 위반)"
    )
