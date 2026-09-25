"""cycle363 Red — 영업일 기준 신선도(①·①′) 구조 가드 (AST).

지시서(정본) = `_workspace/red/cycle363_business_day_freshness_spec.md` §2 · §3.2.
source 텍스트 grep 금지 — AST 노드만 본다(주석·docstring 오탐 제외, cycle167/179 교훈).
소스 스캔은 `Path.rglob("*.py")` — `git grep`/`git ls-files` 금지(미추적 신규 파일 누락, cycle259 S4b).
해시 핀 없음 — 이 파일은 구조만 고정한다.

가드:
- G363-1  daily·basics·full_universe wrapper = 슬롯 kw `True` · 시간 kw **없음**
- G363-2  master·financial = 시간 kw 유지 · 슬롯 kw 없음 (범위 밖)
- G363-3  purge·evening_funnel = 게이트 kw 전무 (+600초 재준비 게이트 금지 — 단계 3·카드3 전)
- G363-4  full_universe = `immediate_force_run_check`(`reason=below_floor` 기본값) +
          `immediate_skip_if_marker_absent=True` (daily 에는 둘 다 없음)
- G363-11 (F-4, 사용자 승인) basics = `immediate_force_run_check` +
          `immediate_force_run_reason="kis_keys_missing"` 리터럴 · `immediate_skip_if_marker_absent`
          은 여전히 없음(마커 없음 = 실행 유지, 부트스트랩 skip 은 full_universe 전용)
- G363-5  `data_load_tasks.FULL_UNIVERSE_IMMEDIATE_MIN_ROWS == 2000` (모듈 상수)
- G363-6  data_load_tasks·task_loop_helper 에 시각 리터럴 `time(...)` 0 — 슬롯 = `wait_time`
          (scheduler `TIME_*` 정본 이원화 금지) [불변식]
- G363-7  task_loop_helper: 모듈 전역 `_now_kst()` 정의 · `latest_passed_trading_slot` 의 슬롯
          인자 = `wait_time` · `IMMEDIATE_FRESH_SKIP_HOURS == 20.0` 유지(master 가 계속 쓴다)
- G363-8  leaf `src/engine/trading_calendar.py`: 공개 API 5종 · naive `now()`/`today()` 0 ·
          8영역·scheduler·boot_manager import 0 · seam 이 `is_trading_day` 위임 ·
          `is_market_open`(실패 시 True = fail-open) 참조 0
- G363-9  6전략 prepare: 어댑터 호출에 `expected_head=<이름>`(호출식 금지 = 종목마다 조회 금지) ·
          `_resolve_expected_daily_head` 는 prepare 본문에서 정확히 1회, `_fetch_one` 밖
- G363-10 범위 밖 고정 — `src/` 전체에서 `expected_head=` 를 넘기는 어댑터 호출은 6전략
          `prepare` 안뿐 (kojiro `recompute_held_atr` · `llm_buy_gate` 는 현행 달력 판정).
          ⚠️ 이 사이클의 범위 핀이다 — 후속 사이클이 범위를 넓히면 그 사이클이 이 목록을 개정한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import find_constant_value, find_function_def

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_DLT = _ROOT / "src" / "engine" / "data_load_tasks.py"
_HELPER = _ROOT / "src" / "engine" / "task_loop_helper.py"
_LEAF = _ROOT / "src" / "engine" / "trading_calendar.py"
_STRAT_DIR = _ROOT / "src" / "engine" / "strategies"

_HELPER_CALL = "run_periodic_task_loop"
_SLOT_KW = "immediate_skip_if_fresh_since_trading_slot"
_FORCE_KW = "immediate_force_run_check"
_ABSENT_KW = "immediate_skip_if_marker_absent"
_HOURS_KW = "immediate_skip_if_fresh_hours"
_REASON_KW = "immediate_force_run_reason"
_GATE_KWS = (_HOURS_KW, _SLOT_KW, _FORCE_KW, _ABSENT_KW, _REASON_KW)

_SLOT_GATED = (
    "stock_master_daily_load_task_loop",
    "stock_master_basics_refresh_task_loop",
    "full_universe_load_task_loop",
)
_TIME_GATED = (
    "stock_master_master_load_task_loop",
    "stock_master_financial_load_task_loop",
)
_UNGATED = (
    "stock_master_daily_purge_task_loop",
    "evening_funnel_capture_task_loop",
)

_PREPARE_FILES = (
    "volatility_breakout.py",
    "long_tail_volatility.py",
    "donchian_swing.py",
    "bull_flag_breakout.py",
    "vcp_breakout.py",
    "kojiro.py",
)
_ADAPTER = "get_recent_daily_normalized"
_RESOLVER = "_resolve_expected_daily_head"

# 8영역(정본 = test_cycle222a3_ast_followup_fixes.py::_EIGHT_AREAS) + scheduler + boot_manager
_LEAF_FORBIDDEN_IMPORT_PREFIXES = (
    "src.engine.risk",
    "src.engine.order_engine",
    "src.engine.session",
    "src.engine.scanner",
    "src.engine.strategy_registry",
    "src.api.order",
    "src.realtime",
    "src.auth",
    "src.engine.scheduler",
    "src.engine.boot_manager",
)


# ──────────────────────────────────────────────────────────────────────
# 탐지기
# ──────────────────────────────────────────────────────────────────────
def _call_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _helper_call_keywords(src: str, fn_name: str) -> dict[str, ast.expr]:
    node = find_function_def(src, fn_name)
    assert node is not None, f"함수 `{fn_name}` 미발견 (구조 변경 재점검)"
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _call_name(sub) == _HELPER_CALL:
            return {kw.arg: kw.value for kw in sub.keywords if kw.arg}
    raise AssertionError(f"`{fn_name}` 안에 `{_HELPER_CALL}(...)` 호출이 없다")


def _is_true_const(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_none_or_absent(node: ast.expr | None) -> bool:
    return node is None or (isinstance(node, ast.Constant) and node.value is None)


def _str_const(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _time_literal_calls(src: str) -> list[int]:
    """`time(…)`/`dtime(…)`/`datetime.time(…)` 에 숫자 상수 인자가 있는 호출 라인."""
    out = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        if name not in ("time", "dtime"):
            continue
        if any(isinstance(a, ast.Constant) and isinstance(a.value, int) for a in node.args):
            out.append(node.lineno)
    return out


def _count_naive_clock(src: str) -> int:
    """인자 없는 `.now()` / `.today()` (naive 벽시계) 호출 수."""
    n = 0
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("now", "today") and not node.args and not node.keywords:
                n += 1
    return n


def _imported_modules(src: str) -> list[str]:
    mods: list[str] = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
            mods += [f"{node.module}.{a.name}" for a in node.names]
    return mods


def _names_referenced(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            out.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            out.add(sub.attr)
        elif isinstance(sub, ast.alias):
            out.add(sub.name.split(".")[-1])
            if sub.asname:
                out.add(sub.asname)
    return out


def _calls_with_enclosing_function(tree: ast.AST):
    """(call, 가장 안쪽 함수명 체인) 을 순회. 체인은 바깥→안쪽 순서."""
    def _walk(node, chain):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield from _walk(child, chain + (child.name,))
            else:
                if isinstance(child, ast.Call):
                    yield child, chain
                yield from _walk(child, chain)
    yield from _walk(tree, ())


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────
# self-test — 탐지기 false-negative 차단
# ──────────────────────────────────────────────────────────────────────
def test_G363_0_detector_self_test():
    sample = (
        "async def w(scheduler, *, wait_time):\n"
        "    await run_periodic_task_loop(scheduler=scheduler, wait_time=wait_time,\n"
        "        immediate_skip_if_fresh_since_trading_slot=True)\n"
        "x = time(20, 30)\n"
        "y = datetime.now()\n"
        "z = date.today()\n"
        "k = datetime.now(KST)\n"
    )
    kws = _helper_call_keywords(sample, "w")
    assert _is_true_const(kws.get(_SLOT_KW)) and _HOURS_KW not in kws
    assert _time_literal_calls(sample) == [4]
    assert _count_naive_clock(sample) == 2, "naive now()/today() 탐지 실패"

    nested = (
        "async def prepare(self):\n"
        "    eh = await self._resolve_expected_daily_head()\n"
        "    async def _fetch_one(t):\n"
        "        return await get_recent_daily_normalized(t, days=1, expected_head=eh)\n"
    )
    found = [
        (c, ch) for c, ch in _calls_with_enclosing_function(ast.parse(nested))
        if _call_name(c) in (_ADAPTER, _RESOLVER)
    ]
    chains = {_call_name(c): ch for c, ch in found}
    assert chains[_RESOLVER] == ("prepare",)
    assert chains[_ADAPTER] == ("prepare", "_fetch_one")


# ──────────────────────────────────────────────────────────────────────
# G363-1~5 — data_load_tasks 배선
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("fn", _SLOT_GATED)
def test_G363_1_slot_gated_wrappers(fn):
    """M1 — daily·basics·full_universe 는 슬롯 게이트, 시간 게이트 kw 제거."""
    kws = _helper_call_keywords(_read(_DLT), fn)
    assert _is_true_const(kws.get(_SLOT_KW)), (
        f"{fn}: `{_SLOT_KW}=True` 리터럴 의무 (실측 {ast.dump(kws[_SLOT_KW]) if _SLOT_KW in kws else '부재'})"
    )
    assert _is_none_or_absent(kws.get(_HOURS_KW)), f"{fn}: 시간 게이트 kw 금지 (동시 지정 = ValueError)"


@pytest.mark.parametrize("fn", _TIME_GATED)
def test_G363_2_time_gated_wrappers_unchanged(fn):
    kws = _helper_call_keywords(_read(_DLT), fn)
    assert not _is_none_or_absent(kws.get(_HOURS_KW)), f"{fn}: 시간 게이트 유지 (범위 밖)"
    assert _SLOT_KW not in kws, f"{fn}: 슬롯 게이트 금지 (범위 밖)"


@pytest.mark.parametrize("fn", _UNGATED)
def test_G363_3_ungated_wrappers_have_no_gate_kw(fn):
    kws = _helper_call_keywords(_read(_DLT), fn)
    present = [k for k in _GATE_KWS if k in kws]
    assert not present, f"{fn}: 게이트 kw 금지 — {present}"


def test_G363_4_full_universe_floor_and_bootstrap_kws():
    src = _read(_DLT)
    kws = _helper_call_keywords(src, "full_universe_load_task_loop")
    assert not _is_none_or_absent(kws.get(_FORCE_KW)), "M2 — 행 수 하한 콜백 전달 의무"
    assert _is_true_const(kws.get(_ABSENT_KW)), "M6 — 부트스트랩 `immediate_skip_if_marker_absent=True`"
    # F-4 — basics 는 (승인) 강제 실행 콜백을 갖지만 부트스트랩 skip 플래그는 없다.
    # daily 만 시나리오 기존대로 「force 콜백 없음」이 유지된다.
    for fn in ("stock_master_daily_load_task_loop", "stock_master_basics_refresh_task_loop"):
        other = _helper_call_keywords(src, fn)
        assert not _is_true_const(other.get(_ABSENT_KW)), f"{fn}: 마커 없음 = 실행 유지"
    daily = _helper_call_keywords(src, "stock_master_daily_load_task_loop")
    assert _is_none_or_absent(daily.get(_FORCE_KW)), "daily: 강제 실행 콜백 없음(범위 밖)"


def test_G363_11_basics_force_run_check_and_reason():
    """F-4(사용자 승인) — basics 는 KIS 출처 키 결측 임계 콜백 + `reason=kis_keys_missing`."""
    kws = _helper_call_keywords(_read(_DLT), "stock_master_basics_refresh_task_loop")
    assert not _is_none_or_absent(kws.get(_FORCE_KW)), "F-4 — basics 강제 실행 콜백 전달 의무"
    assert _str_const(kws.get(_REASON_KW)) == "kis_keys_missing", (
        f"F-4 — `immediate_force_run_reason=\"kis_keys_missing\"` 리터럴 의무 "
        f"(실측 {ast.dump(kws[_REASON_KW]) if _REASON_KW in kws else '부재'})"
    )


def test_G363_5_floor_constant_is_module_level_2000():
    value = find_constant_value(_read(_DLT), "FULL_UNIVERSE_IMMEDIATE_MIN_ROWS")
    assert value == 2000, f"모듈-레벨 `FULL_UNIVERSE_IMMEDIATE_MIN_ROWS = 2000` 의무 (실측 {value!r})"


@pytest.mark.parametrize("path", [_DLT, _HELPER], ids=["data_load_tasks", "task_loop_helper"])
def test_G363_6_no_time_literal(path):
    """[불변식] 슬롯은 `wait_time`(= scheduler `TIME_*` 정본) — 새 시각 리터럴 금지."""
    lines = _time_literal_calls(_read(path))
    assert not lines, f"{path.name}: 시각 리터럴 `time(...)` 금지 (라인 {lines})"


# ──────────────────────────────────────────────────────────────────────
# G363-7 — task_loop_helper
# ──────────────────────────────────────────────────────────────────────
def test_G363_7a_helper_defines_now_kst_seam():
    tree = ast.parse(_read(_HELPER))
    top = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "_now_kst" in top, "모듈 전역 `_now_kst()` seam 의무 (테스트가 시각을 고정하는 유일 지점)"


def test_G363_7b_helper_passes_wait_time_as_slot():
    src = _read(_HELPER)
    calls = [
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call) and _call_name(n) == "latest_passed_trading_slot"
    ]
    assert calls, "헬퍼가 `latest_passed_trading_slot` 을 부르지 않는다"
    for c in calls:
        slot_arg = c.args[1] if len(c.args) >= 2 else next(
            (kw.value for kw in c.keywords if kw.arg == "slot"), None
        )
        assert isinstance(slot_arg, ast.Name) and slot_arg.id == "wait_time", (
            f"슬롯 인자 = `wait_time` 의무 (라인 {c.lineno}, 실측 "
            f"{ast.dump(slot_arg) if slot_arg is not None else '부재'})"
        )


def test_G363_7c_time_gate_constant_unchanged():
    """[불변식] master 가 계속 쓰는 `IMMEDIATE_FRESH_SKIP_HOURS = 20.0`."""
    assert find_constant_value(_read(_HELPER), "IMMEDIATE_FRESH_SKIP_HOURS") == 20.0


# ──────────────────────────────────────────────────────────────────────
# G363-8 — leaf
# ──────────────────────────────────────────────────────────────────────
def _leaf_src() -> str:
    assert _LEAF.exists(), "leaf `src/engine/trading_calendar.py` 부재"
    return _read(_LEAF)


def test_G363_8a_leaf_public_api():
    tree = ast.parse(_leaf_src())
    defs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name in ("_lookup_open", "is_open_day", "previous_trading_day", "latest_passed_trading_slot"):
        assert isinstance(defs.get(name), ast.AsyncFunctionDef), f"모듈 전역 `async def {name}` 의무"
    assert isinstance(defs.get("_reset_cache_for_tests"), ast.FunctionDef), (
        "모듈 전역 `def _reset_cache_for_tests()` 의무 (conftest 중립화 픽스처가 부른다)"
    )


def test_G363_8b_leaf_no_naive_clock():
    n = _count_naive_clock(_leaf_src())
    assert n == 0, f"leaf naive now()/today() {n}건 — KST 강제"


def test_G363_8c_leaf_import_boundary():
    bad = [
        m for m in _imported_modules(_leaf_src())
        if any(m == p or m.startswith(p + ".") for p in _LEAF_FORBIDDEN_IMPORT_PREFIXES)
    ]
    assert not bad, f"leaf 는 8영역·scheduler·boot_manager import 금지 — {bad}"


def test_G363_8d_leaf_seam_delegates_to_three_state_lookup():
    src = _leaf_src()
    tree = ast.parse(src)
    seam = next(
        (n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_lookup_open"),
        None,
    )
    assert seam is not None
    assert "is_trading_day" in _names_referenced(seam), "seam 은 `condition.is_trading_day`(3상태) 위임"
    assert "is_market_open" not in _names_referenced(tree), (
        "`is_market_open` 은 조회 실패를 True(개장)로 삼킨다 — 「모름 → 실행」을 표현할 수 없다"
    )


# ──────────────────────────────────────────────────────────────────────
# G363-9 — 6전략 prepare
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("fname", _PREPARE_FILES)
def test_G363_9_prepare_passes_resolved_expected_head(fname):
    src = _read(_STRAT_DIR / fname)
    prepare = find_function_def(src, "prepare")
    assert prepare is not None, f"{fname}: prepare 미발견"

    adapter_calls, resolver_calls = [], []
    for call, chain in _calls_with_enclosing_function(prepare):
        if _call_name(call) == _ADAPTER:
            adapter_calls.append((call, chain))
        elif _call_name(call) == _RESOLVER:
            resolver_calls.append((call, chain))

    assert adapter_calls, f"{fname}: prepare 안 어댑터 호출 부재"
    for call, _chain in adapter_calls:
        kw = {k.arg: k.value for k in call.keywords if k.arg}
        assert "expected_head" in kw, f"{fname}:{call.lineno} 어댑터 호출에 `expected_head=` 의무 (M5)"
        assert isinstance(kw["expected_head"], ast.Name), (
            f"{fname}:{call.lineno} `expected_head` 는 prepare 에서 1회 계산한 이름이어야 한다 "
            f"(호출식이면 종목마다 조회 — 실측 {ast.dump(kw['expected_head'])})"
        )

    assert len(resolver_calls) == 1, (
        f"{fname}: `{_RESOLVER}` 는 prepare 당 정확히 1회 (실측 {len(resolver_calls)})"
    )
    assert resolver_calls[0][1] == (), (
        f"{fname}: `{_RESOLVER}` 는 prepare 본문(gather 전)에서 — 중첩 함수 {resolver_calls[0][1]} 안 금지"
    )


# ──────────────────────────────────────────────────────────────────────
# G363-10 — 범위 밖 고정 (src 전체 rglob)
# ──────────────────────────────────────────────────────────────────────
def test_G363_10_expected_head_only_in_six_prepares():
    allowed = {f"src/engine/strategies/{f}" for f in _PREPARE_FILES}
    offenders: list[str] = []
    for path in sorted((_ROOT / "src").rglob("*.py")):
        try:
            tree = ast.parse(_read(path))
        except SyntaxError:
            continue
        rel = path.relative_to(_ROOT).as_posix()
        for call, chain in _calls_with_enclosing_function(tree):
            if _call_name(call) != _ADAPTER:
                continue
            if not any(k.arg == "expected_head" for k in call.keywords):
                continue
            if rel in allowed and chain and chain[0] == "prepare":
                continue
            offenders.append(f"{rel}:{call.lineno} ({'.'.join(chain) or '<module>'})")
    assert not offenders, (
        "cycle363 범위 밖 호출부가 `expected_head` 를 넘긴다 — kojiro recompute_held_atr · "
        "llm_buy_gate · tools 는 현행 달력 판정 유지:\n  " + "\n  ".join(offenders)
    )
