"""TDD Red — refactor 카드 B3 (백테스트 오케스트레이션 위임 분해, 행위 보존).

recommendation_engine.py 의 백테스트 오케스트레이션(5 함수 + 전역/상수)을 신규
``src/engine/backtest_orchestration.py`` 로 이관하되, **재export 로 기존 import 경로를
전부 보존**한다(scheduler.py:3760 `from ...recommendation_engine import
_backtest_poll_loop_running` 미접촉 + 기존 backtest/poll 테스트 import 경로 불변).

이관 대상 (recommendation_engine.py 현 위치):
    전역/상수:  _backtest_poll_loop_running(set[date]) / _BACKTEST_POLL_INTERVAL_SECS(60)
                / _BACKTEST_POLL_TIMEOUT_HOURS(24)
    5 함수:     _get_backtest_engine(sync) / _spawn_backtest_poll_task(sync)
                / _enqueue_backtest_jobs(async) / _backtest_poll_loop(async)
                / _emit_pending_summaries(async)

순환 import 없음(리팩토링 자문에서 확인): 5 함수는 `_db_*`(src.db aliased import)·
backtest_engine·`compute_metric_diff`(src.models.backtest)·`ExternalAPIError`/`ConfigError`
(src.services.exceptions)만 사용 — recommendation_engine core(`_validate_recommendations`
/`_call_openai`/`generate_recommendations`/`compute_metrics`)는 미호출 → 신규 모듈은 leaf.

이 파일은 **Red 전용**(구현 전 FAIL → 이관 후 PASS). 신규 모듈 부재 상태에서 아래 8
케이스는 모두 실패한다. 구현(Green)은 backend-dev 가 수행한다.

⚠️ 기존 backtest/poll 테스트 patch 경로 적응(수정은 backend-dev/tester 협의)은
_workspace/red/refactor_b3_backtest_orchestration.md 에 정본 기록.
"""

from __future__ import annotations

import ast
import importlib
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 이관 대상 정본
# ---------------------------------------------------------------------------
_ASYNC_MOVED = ("_enqueue_backtest_jobs", "_backtest_poll_loop", "_emit_pending_summaries")
_SYNC_MOVED = ("_get_backtest_engine", "_spawn_backtest_poll_task")
_MOVED_FUNCTIONS = _SYNC_MOVED + _ASYNC_MOVED
_MOVED_GLOBALS = (
    "_backtest_poll_loop_running",
    "_BACKTEST_POLL_INTERVAL_SECS",
    "_BACKTEST_POLL_TIMEOUT_HOURS",
)
# recommendation_engine 재export 로 기존 import 경로 보존이 요구되는 이름 전부
_REEXPORT_NAMES = _MOVED_FUNCTIONS + ("_backtest_poll_loop_running",)

SUPPORTED = ("momentum", "volatility_breakout", "donchian_swing")
FALLBACK = ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout", "kojiro")
ALL_STRATEGIES = SUPPORTED + FALLBACK


# ---------------------------------------------------------------------------
# 경로/모듈 헬퍼 — cwd 무관하게 recommendation_engine 위치에서 파생
# ---------------------------------------------------------------------------
def _engine_dir() -> Path:
    rec_mod = importlib.import_module("src.engine.recommendation_engine")
    return Path(rec_mod.__file__).resolve().parent


def _orchestration_path() -> Path:
    return _engine_dir() / "backtest_orchestration.py"


def _parse_orchestration() -> ast.Module:
    p = _orchestration_path()
    if not p.exists():
        pytest.fail(f"backtest_orchestration.py 미존재 (이관 전 RED): {p}")
    return ast.parse(p.read_text(encoding="utf-8"))


def _import_orchestration():
    try:
        return importlib.import_module("src.engine.backtest_orchestration")
    except ModuleNotFoundError:
        pytest.fail("src.engine.backtest_orchestration 모듈 미존재 (이관 전 RED)")


def _make_inserted_rows(target_date: date) -> list[dict]:
    """generate_recommendations() 가 _enqueue_backtest_jobs 로 넘기는 페이로드."""
    return [
        {
            "id": f"rec-{sid}",
            "target_date": target_date.isoformat(),
            "strategy_id": sid,
            "current_params": {"buy_threshold": 29.0},
            "recommended_params": {"buy_threshold": 27.0},
        }
        for sid in ALL_STRATEGIES
    ]


def _install_db_doubles(monkeypatch, mod):
    """_db_insert_run / _db_update_status 더블을 *신규 모듈* 네임스페이스에 설치."""
    update_records: list[dict] = []

    async def fake_insert_run(target_date, strategy_id, params_kind, params_snapshot):
        return {
            "id": f"run-{strategy_id}-{params_kind}",
            "strategy_id": strategy_id,
            "params_kind": params_kind,
            "params_snapshot": dict(params_snapshot),
            "status": "queued",
        }

    async def fake_update_status(run_id, status, **kwargs):
        update_records.append({"run_id": run_id, "status": status, **kwargs})
        return {"id": run_id, "status": status}

    monkeypatch.setattr(mod, "_db_insert_run", fake_insert_run, raising=False)
    monkeypatch.setattr(mod, "_db_update_status", fake_update_status, raising=False)
    return update_records


_SUPPORTED_RUN_IDS = {f"run-{s}-{k}" for s in SUPPORTED for k in ("current", "recommended")}


# ---------------------------------------------------------------------------
# 1. 모듈 존재 + 5 함수 + 전역/상수 이관 (AsyncFunctionDef 3 + FunctionDef 2)
# ---------------------------------------------------------------------------
def test_orchestration_module_defines_moved_functions_and_globals():
    """backtest_orchestration.py 가 5 함수(비동기 3 + 동기 2) + 3 전역/상수를 module-level
    로 정의한다. 신규 모듈 부재 상태에서 RED."""
    tree = _parse_orchestration()

    top_async = {n.name for n in tree.body if isinstance(n, ast.AsyncFunctionDef)}
    top_sync = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}

    for fn in _ASYNC_MOVED:
        assert fn in top_async, f"비동기 함수 이관 누락: {fn} (module-level async def 부재)"
    for fn in _SYNC_MOVED:
        assert fn in top_sync, f"동기 함수 이관 누락: {fn} (module-level def 부재)"

    # module-level 할당(Assign / AnnAssign) 이름 수집
    assigned: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assigned.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assigned.add(node.target.id)

    for g in _MOVED_GLOBALS:
        assert g in assigned, f"전역/상수 이관 누락: {g}"


# ---------------------------------------------------------------------------
# 2. 재export 호환 — recommendation_engine 경로가 신규 모듈과 동일 객체
# ---------------------------------------------------------------------------
def test_recommendation_engine_reexports_same_objects():
    """`from src.engine.recommendation_engine import <name>` 이 이관 후에도 전부 성공하고,
    각 이름이 backtest_orchestration 의 동일 객체를 가리켜야 한다(재export). RED: 신규 모듈 부재."""
    orch = _import_orchestration()
    rec_mod = importlib.import_module("src.engine.recommendation_engine")

    for name in _REEXPORT_NAMES:
        assert hasattr(rec_mod, name), f"recommendation_engine 재export 누락: {name}"
        assert hasattr(orch, name), f"backtest_orchestration 정의 누락: {name}"
        assert getattr(rec_mod, name) is getattr(orch, name), (
            f"재export 가 동일 객체가 아님(복사본이면 scheduler/test patch 무력화): {name}"
        )


# ---------------------------------------------------------------------------
# 3. 순환 import 0 (AST) — 신규 모듈이 recommendation_engine 을 import 하지 않음
# ---------------------------------------------------------------------------
def test_orchestration_has_no_recommendation_engine_import():
    """backtest_orchestration.py 는 recommendation_engine 을 정적으로 import 하지 않는다
    (leaf 모듈 — 순환 방지)."""
    tree = _parse_orchestration()
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if "recommendation_engine" in a.name]
        elif isinstance(node, ast.ImportFrom):
            if "recommendation_engine" in (node.module or ""):
                offenders.append(node.module or "")
    assert offenders == [], f"순환 import — backtest_orchestration 가 recommendation_engine import: {offenders}"


# ---------------------------------------------------------------------------
# 4. 본체 이관 완료 — recommendation_engine.py 에 5 함수 정의(def) 부재
# ---------------------------------------------------------------------------
def test_recommendation_engine_no_longer_defines_moved_functions():
    """recommendation_engine.py 소스에 5 함수의 `def`/`async def` 정의가 없어야 한다
    (재export 만 잔존). 현재 5 함수 전부 정의됨 → RED."""
    rec_path = _engine_dir() / "recommendation_engine.py"
    tree = ast.parse(rec_path.read_text(encoding="utf-8"))
    top_defs = {
        n.name for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    still_defined = [fn for fn in _MOVED_FUNCTIONS if fn in top_defs]
    assert still_defined == [], (
        f"본체가 recommendation_engine 에 잔존(재export 만 해야 함): {still_defined}"
    )


# ---------------------------------------------------------------------------
# 5a. 행위 보존 — enqueue: DB 토글 True → 지원 3종 submit + poll 발화
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_behavior_preserved_enabled(monkeypatch: pytest.MonkeyPatch):
    """신규 모듈 _enqueue_backtest_jobs 가 is_enabled_async()=True 일 때 지원 3종 6 row 를
    submit + running 전이 + _spawn_backtest_poll_task 발화. patch 타깃 = backtest_orchestration.*."""
    orch = _import_orchestration()
    target = date(2026, 7, 24)
    recs = _make_inserted_rows(target)
    update_records = _install_db_doubles(monkeypatch, orch)

    submit_calls: list[tuple[str, str]] = []

    class FakeEngine:
        enabled = False  # 정적 .env — 게이트는 is_enabled_async 를 봐야 한다

        async def is_enabled_async(self):
            return True

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            submit_calls.append((strategy_id, kind))
            return f"job-{strategy_id}-{kind}"

    monkeypatch.setattr(orch, "_get_backtest_engine", lambda: FakeEngine(), raising=False)
    spawn_calls: list = []
    monkeypatch.setattr(
        orch, "_spawn_backtest_poll_task", lambda td: spawn_calls.append(td), raising=False
    )

    await orch._enqueue_backtest_jobs(target, recs)

    submitted = set(submit_calls)
    expected = {(s, k) for s in SUPPORTED for k in ("current", "recommended")}
    assert submitted == expected, f"지원 3종 submit 되어야 함: 실제={submitted}"

    running_ids = {u["run_id"] for u in update_records if u["status"] == "running"}
    assert running_ids == _SUPPORTED_RUN_IDS
    assert spawn_calls == [target], "지원 submit>0 이면 poll 발화"


# ---------------------------------------------------------------------------
# 5b. 행위 보존 — enqueue: DB 토글 False → 지원 3종 skipped + submit/발화 0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_behavior_preserved_disabled(monkeypatch: pytest.MonkeyPatch):
    """is_enabled_async()=False 면 지원 3종 'MCP 비활성' skipped + run_for_strategy 미호출 +
    poll 미발화. 폴백 4종은 항상 '로컬 백테스트 실행기 없음' skipped."""
    orch = _import_orchestration()
    target = date(2026, 7, 24)
    recs = _make_inserted_rows(target)
    update_records = _install_db_doubles(monkeypatch, orch)

    submit_calls: list[str] = []

    class FakeEngine:
        enabled = True

        async def is_enabled_async(self):
            return False

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            submit_calls.append(strategy_id)
            return "job-should-not-be-called"

    monkeypatch.setattr(orch, "_get_backtest_engine", lambda: FakeEngine(), raising=False)
    spawn_calls: list = []
    monkeypatch.setattr(
        orch, "_spawn_backtest_poll_task", lambda td: spawn_calls.append(td), raising=False
    )

    await orch._enqueue_backtest_jobs(target, recs)

    supported_skipped = {
        u["run_id"] for u in update_records
        if u["status"] == "skipped" and u["run_id"] in _SUPPORTED_RUN_IDS
    }
    assert supported_skipped == _SUPPORTED_RUN_IDS
    assert submit_calls == [], "비활성 시 run_for_strategy 호출 0"
    assert spawn_calls == [], "비활성 시 poll 미발화"

    # 폴백 4종(kojiro 포함) × 2 kind = 8 row 는 enabled 무관 항상 skipped
    fallback_ids = {f"run-{s}-{k}" for s in FALLBACK for k in ("current", "recommended")}
    fallback_skipped = {
        u["run_id"] for u in update_records
        if u["status"] == "skipped" and u["run_id"] in fallback_ids
    }
    assert fallback_skipped == fallback_ids


# ---------------------------------------------------------------------------
# 6. 행위 보존 — poll loop 중복 가드 (_backtest_poll_loop_running 즉시 return)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_loop_duplicate_guard_preserved(monkeypatch: pytest.MonkeyPatch):
    """_backtest_poll_loop 는 target_date 가 _backtest_poll_loop_running 에 있으면 즉시 return
    (_db_list_by_date 호출 0). patch 타깃 = backtest_orchestration.*."""
    orch = _import_orchestration()
    target = date(2026, 5, 16)

    monkeypatch.setattr(orch, "_backtest_poll_loop_running", {target}, raising=False)

    list_calls = {"n": 0}

    async def fake_list_by_date(td):
        list_calls["n"] += 1
        return []

    monkeypatch.setattr(orch, "_db_list_by_date", fake_list_by_date, raising=False)

    await orch._backtest_poll_loop(target)

    assert list_calls["n"] == 0, "중복 가드가 있으면 _db_list_by_date 미호출"


# ---------------------------------------------------------------------------
# 7. 8영역 무관 — scheduler.py import 경로 보존 + 가드 set 동일 객체 공유
# ---------------------------------------------------------------------------
def test_scheduler_import_path_preserved_and_guard_shared():
    """scheduler.py 는 여전히 recommendation_engine 경로로 _backtest_poll_loop_running 을
    import 한다(무변경). 그리고 그 재export 된 set 은 backtest_orchestration 의 것과 **동일
    객체**여야 scheduler._reset_daily_state 의 `.clear()` 가 실제 가드에 반영된다."""
    sched_path = _engine_dir() / "scheduler.py"
    src = sched_path.read_text(encoding="utf-8")
    assert (
        "from src.engine.recommendation_engine import _backtest_poll_loop_running" in src
    ), "scheduler.py 의 재export import 경로가 바뀌었다(8영역 무접촉 원칙 위반)"

    orch = _import_orchestration()
    rec_mod = importlib.import_module("src.engine.recommendation_engine")
    assert rec_mod._backtest_poll_loop_running is orch._backtest_poll_loop_running, (
        "재export 된 가드 set 이 신규 모듈과 다른 객체 — scheduler .clear() 가 무력화됨"
    )
