"""사이클 193 (2026-07-04) Red — immediate 신선도 게이트 AST/구조 가드 (F-10).

source 텍스트 grep 금지 — AST 노드 검사 (사이클 167/179/184/187 false-positive 교훈).
`tests/unit/ast/_ast_helpers.py` 재사용.

가드:
- F-10-1: scheduler 게이트 대상 3 wrapper (basics/master/**daily_load**) 의
  `run_periodic_task_loop` 호출에 `immediate_skip_if_fresh_hours` 키워드 명시.
- F-10-2: 게이트 미대상 3 wrapper (full_universe/purge/evening_funnel) 부재.

⚠️ **사이클 263 (2026-09-06) 이 daily_load 제외 결정을 뒤집었다** (사용자 결정 09-06 카드 ④).
사이클 193 이 daily_load 만 게이트에서 뺀 근거는 "`max_bas_dd` 멱등이 immediate 를 이미
저렴하게 한다" 였는데, **그 멱등이 실제로는 깨져 있었다**: 아침 immediate(07:56)가 장 전
KIS 오늘봉(껍데기 = O·H·L·C 전일종가, 거래량 0)을 먼저 써서 `max_bas_dd == today` 를
만들고 그날 16:00 정기 실행을 전 종목 skip 시켰다(09-03 `fetched=0 skipped_fresh=982` ·
09-04 `fetched=1 skipped_fresh=1015` 실측). 게이트 투입은 껍데기 생성 주체를 없애
**사이클 193 의 전제를 되살리는 방향**이다. 우려했던 off-by-one 은 (a) 마커가 once() 성공
시에만 갱신되므로 16:00 실패·다운 시 다음 아침 immediate 가 자동 부활하고 (b) 사이클 263
오늘봉 시각 필터가 낮 재배포 구멍까지 닫아 해소된다.
상세 = `_workspace/specs/cycle263_daily_load_stub_fix.md` ·
`_workspace/consult/2026-09-06_daily_load_stub_bar.md` 부록 A-1.
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

# 게이트 적용 3 wrapper (사이클 193 basics/master + 사이클 263 daily_load)
_TARGET_WRAPPERS = (
    "_stock_master_basics_refresh_task_loop",
    "_stock_master_master_load_task_loop",
    # 사이클 263 — `max_bas_dd` 멱등이 껍데기 봉 때문에 깨져 있었다(모듈 docstring 참조).
    # 게이트가 아침 껍데기 생성 주체를 없애 16:00 정기 실행을 되살린다.
    "_stock_master_daily_load_task_loop",
)
# 게이트 미대상 (멱등/TTL 있어 immediate 이미 저렴 + self-heal 위험 회피 + 범위 외)
_UNGATED_WRAPPERS = (
    "_full_universe_load_task_loop",   # TTL 멱등 + 유니버스 populator self-heal
    "_stock_master_daily_purge_task_loop",  # 사이클 192 후 저렴 + burst 아님
    "_evening_funnel_capture_task_loop",  # 사용자 결정 범위 외
)


def _scheduler_source() -> str:
    # refactor-review B1 (2026-08-09) — task loop 본체(게이트 키워드 포함)는
    # data_load_tasks.py 로 위임 이관. 게이트 검사는 이 모듈을 본다.
    import src.engine.data_load_tasks as _dlt

    return read_module_source(_dlt.__file__)


def _helper_source() -> str:
    import src.engine.task_loop_helper as _helper

    return read_module_source(_helper.__file__)


def _wrapper_has_gate_kw(scheduler_src: str, wrapper_name: str) -> bool:
    """wrapper 함수 내 run_periodic_task_loop 호출에 게이트 키워드 명시 여부 (AST)."""
    # B1 위임 이관 — data_load_tasks 함수명은 언더스코어 없음. exact(self-test 합성명) →
    # strip(실 wrapper→본체) 순으로 조회.
    node = find_function_def(scheduler_src, wrapper_name) or \
        find_function_def(scheduler_src, wrapper_name.lstrip("_"))
    assert node is not None, f"함수 `{wrapper_name}` 미발견 (구조 변경 재점검)."

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
    """basics/master/daily_load wrapper run_periodic_task_loop 게이트 키워드 명시 의무.

    사이클 193 = 멱등 없는 실제 burst 2 task(basics/master).
    사이클 263 = daily_load 추가 — 믿었던 `max_bas_dd` 멱등이 깨져 있었다(모듈 docstring).
    """
    scheduler_src = _scheduler_source()
    missing = [
        name for name in _TARGET_WRAPPERS if not _wrapper_has_gate_kw(scheduler_src, name)
    ]
    assert not missing, (
        "F-10-1 — 게이트 키워드 미명시 wrapper:\n  " + ", ".join(missing)
    )


# ---------------------------------------------------------------------------
# F-10-2 (불변식) — 게이트 미대상 3 wrapper 게이트 부재 (사이클 263: daily_load 제외)
# ---------------------------------------------------------------------------
def test_F10_2_ungated_wrappers_no_gate():
    """full_universe/purge/evening_funnel = 게이트 키워드 부재 의무.

    full_universe/purge = TTL 멱등이 immediate 를 이미 저렴하게 함 + self-heal 상실
    (populator) 위험 → 제외. evening_funnel = 사용자 결정 범위 외.
    ⚠️ daily_load 는 사이클 263 에서 이 목록을 떠나 게이트 대상이 됐다(모듈 docstring).
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
