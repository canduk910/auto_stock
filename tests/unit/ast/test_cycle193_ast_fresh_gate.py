"""사이클 193 (2026-07-04) Red — immediate 신선도 게이트 AST/구조 가드 (F-10).

source 텍스트 grep 금지 — AST 노드 검사 (사이클 167/179/184/187 false-positive 교훈).
`tests/unit/ast/_ast_helpers.py` 재사용.

가드:
- F-10-1: 시간 게이트 wrapper (master/financial) 의 `run_periodic_task_loop` 호출에
  `immediate_skip_if_fresh_hours` 키워드 명시 + 슬롯 게이트 wrapper
  (basics/daily_load/full_universe) 에 `immediate_skip_if_fresh_since_trading_slot` 명시
  (시간 kw 부재). — 사이클 363 개정, 아래 🔁 절.
- F-10-2: 게이트 미대상 2 wrapper (purge/evening_funnel) 에 두 키워드 모두 부재.

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

🔁 **사이클 363 (2026-09-25) 개정 — 값·목록만** (사용자 결정 D4 카드1 (가)·카드2 (나)).
게이트가 두 갈래가 됐다: 시간 게이트(`immediate_skip_if_fresh_hours`) = master·financial,
**영업일 슬롯 게이트**(`immediate_skip_if_fresh_since_trading_slot`) = basics·daily·**full_universe**.
- basics·daily 는 시간 kw 를 떠나 슬롯 kw 로 옮겼다 — 주말·연휴를 「낡았다」로 세던 20h 시계가
  월요일마다 보충 적재를 돌렸다(cycle360 메모 §1.1).
- **full_universe 가 무게이트 목록(F-10-2)을 떠난다.** 이 파일이 적어 둔 제외 근거
  「TTL 멱등이라 즉시 실행이 저렴」은 실측과 다르다 — 10거래일 중 즉시 실행이 일을 한 날은
  두 월요일(09-14·09-21)뿐이고, 그 일은 **전량 덮어쓰기**였으며 09-21 에 들어간 값은
  **목요일 KRX 값**이었다(KRX 는 직전 영업일 자료를 다음 영업일 07:53 까지 내놓지 않는다).
  자가 치유(populator)는 행 수 하한(`FULL_UNIVERSE_IMMEDIATE_MIN_ROWS=2000`, force check)으로
  보존한다. 근거 = `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §1.1·§1.2·§6.
- purge·evening_funnel 은 무게이트 그대로다(+600초 재준비 게이트는 단계 3·카드3 결정 뒤).
상세 구조 가드 = `tests/unit/ast/test_cycle363_ast_business_day_gate.py`.
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
# 사이클 363 — 영업일 슬롯 게이트 kw (시간 게이트와 동시 지정 = ValueError)
_SLOT_GATE_KW = "immediate_skip_if_fresh_since_trading_slot"
_HELPER_CALL = "run_periodic_task_loop"

# 시간 게이트 wrapper (사이클 193 master · 사이클 C3 financial)
# 사이클 363 — basics·daily_load 는 슬롯 게이트로 옮겼다(모듈 docstring 🔁 절).
_TARGET_WRAPPERS = (
    "_stock_master_master_load_task_loop",
    "_stock_master_financial_load_task_loop",
)
# 영업일 슬롯 게이트 wrapper (사이클 363). daily_load 는 사이클 263 에 시간 게이트로
# 들어왔다가(`max_bas_dd` 멱등이 껍데기 봉 때문에 깨져 있었다) 사이클 363 에 슬롯으로 옮겼다.
# full_universe 는 사이클 363 에 무게이트 목록을 떠났다(모듈 docstring 🔁 절).
_SLOT_TARGET_WRAPPERS = (
    "_stock_master_basics_refresh_task_loop",
    "_stock_master_daily_load_task_loop",
    "_full_universe_load_task_loop",
)
# 게이트 미대상 (사이클 192 후 저렴 + 사용자 결정 범위 외)
_UNGATED_WRAPPERS = (
    "_stock_master_daily_purge_task_loop",  # 사이클 192 후 저렴 + burst 아님
    "_evening_funnel_capture_task_loop",  # +600초 재준비 — 단계 3·카드3 결정 전 게이트 금지
)


def _scheduler_source() -> str:
    # refactor-review B1 (2026-08-09) — task loop 본체(게이트 키워드 포함)는
    # data_load_tasks.py 로 위임 이관. 게이트 검사는 이 모듈을 본다.
    import src.engine.data_load_tasks as _dlt

    return read_module_source(_dlt.__file__)


def _helper_source() -> str:
    import src.engine.task_loop_helper as _helper

    return read_module_source(_helper.__file__)


def _wrapper_has_gate_kw(scheduler_src: str, wrapper_name: str, kw_name: str = _GATE_KW) -> bool:
    """wrapper 함수 내 run_periodic_task_loop 호출에 게이트 키워드 명시 여부 (AST).

    사이클 363 — `kw_name` 인자 추가(기본 = 시간 게이트 kw, 슬롯 게이트는 `_SLOT_GATE_KW`).
    """
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
            if kw.arg == kw_name:
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
    slot_sample = (
        "async def _w_slot(s):\n"
        "    await run_periodic_task_loop(scheduler=s, immediate_skip_if_fresh_since_trading_slot=True)\n"
    )
    assert _wrapper_has_gate_kw(slot_sample, "_w_slot", _SLOT_GATE_KW) is True, "self-test — 슬롯 kw 탐지 실패"
    assert _wrapper_has_gate_kw(slot_sample, "_w_slot") is False, "self-test — 슬롯 kw 를 시간 kw 로 오탐"

    assert _count_naive_now("x = datetime.now()\n") == 1, "self-test — naive now 탐지 실패"
    assert _count_naive_now("x = datetime.now(KST)\n") == 0, "self-test — tz 명시 오탐"


# ---------------------------------------------------------------------------
# F-10-1 — 게이트 대상 wrapper 게이트 키워드 명시 (사이클 363: 시간/슬롯 두 갈래)
# ---------------------------------------------------------------------------
def test_F10_1_gated_wrappers_have_gate_kw():
    """시간 게이트 wrapper(master·financial) = 시간 kw · 슬롯 게이트 wrapper
    (basics·daily_load·full_universe) = 슬롯 kw 명시 의무 + 시간 kw 부재.

    사이클 193 = 멱등 없는 실제 burst 2 task(basics/master).
    사이클 263 = daily_load 추가 — 믿었던 `max_bas_dd` 멱등이 깨져 있었다(모듈 docstring).
    🔁 사이클 363 = basics·daily_load 가 시간→슬롯, full_universe 신규 슬롯(모듈 docstring 🔁 절).
    """
    scheduler_src = _scheduler_source()
    missing = [
        name for name in _TARGET_WRAPPERS if not _wrapper_has_gate_kw(scheduler_src, name)
    ]
    assert not missing, (
        "F-10-1 — 시간 게이트 키워드 미명시 wrapper:\n  " + ", ".join(missing)
    )
    slot_missing = [
        name for name in _SLOT_TARGET_WRAPPERS
        if not _wrapper_has_gate_kw(scheduler_src, name, _SLOT_GATE_KW)
    ]
    assert not slot_missing, (
        "F-10-1 — 슬롯 게이트 키워드 미명시 wrapper (사이클 363):\n  " + ", ".join(slot_missing)
    )
    both = [
        name for name in _SLOT_TARGET_WRAPPERS if _wrapper_has_gate_kw(scheduler_src, name)
    ]
    assert not both, (
        "F-10-1 — 슬롯 게이트 wrapper 에 시간 kw 잔존 (동시 지정 = ValueError):\n  " + ", ".join(both)
    )


# ---------------------------------------------------------------------------
# F-10-2 (불변식) — 게이트 미대상 2 wrapper 게이트 부재
# (사이클 263: daily_load 제외 · 사이클 363: full_universe 제외)
# ---------------------------------------------------------------------------
def test_F10_2_ungated_wrappers_no_gate():
    """purge/evening_funnel = 시간·슬롯 게이트 키워드 모두 부재 의무.

    purge = 사이클 192 후 저렴 + burst 아님. evening_funnel = +600초 재준비 — 게이트는
    단계 3(카드3 결정 뒤) 몫이라 지금은 금지(cycle363 지시서 §1).
    ⚠️ daily_load 는 사이클 263, full_universe 는 사이클 363 에 이 목록을 떠났다.
    full_universe 제외 근거였던 「TTL 멱등이라 즉시 실행이 저렴 + self-heal 상실」 중 앞은
    실측과 달랐고(월요일 전량 덮어쓰기 = 목요일 KRX 값), 뒤는 행 수 하한이 보존한다
    (모듈 docstring 🔁 절 · cycle360 메모 §1.1·§1.2·§6).
    """
    scheduler_src = _scheduler_source()
    unexpected = [
        name for name in _UNGATED_WRAPPERS
        if _wrapper_has_gate_kw(scheduler_src, name)
        or _wrapper_has_gate_kw(scheduler_src, name, _SLOT_GATE_KW)
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
