"""refactor-review B1 (2026-08-09) — 저녁 데이터적재 task 위임 분해 회귀 가드.

scheduler.py 재비대(사이클 67 3,007L → 4,230L) 시정 — 8개 task loop 본체를
data_load_tasks.py 로 위임(사이클 51/67 패턴). 핵심 불변식:
  1. 순환 import 0 (data_load_tasks 는 scheduler 를 import 하지 않는다).
  2. scheduler 8 wrapper 가 data_load_tasks 로 위임.
  3. 8 task 함수가 data_load_tasks 에 존재.
"""
import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_DLT = _REPO / "src" / "engine" / "data_load_tasks.py"
_SCHED = _REPO / "src" / "engine" / "scheduler.py"

# scheduler wrapper 명(언더스코어) → data_load_tasks 함수명(언더스코어 없음)
_WRAPPERS = {
    "_scan_pool_eager_refresh_loop": "scan_pool_eager_refresh_loop",
    "_full_universe_load_task_loop": "full_universe_load_task_loop",
    "_stock_master_daily_load_task_loop": "stock_master_daily_load_task_loop",
    "_stock_master_basics_refresh_task_loop": "stock_master_basics_refresh_task_loop",
    "_stock_master_master_load_task_loop": "stock_master_master_load_task_loop",
    "_stock_master_financial_load_task_loop": "stock_master_financial_load_task_loop",
    "_evening_funnel_capture_task_loop": "evening_funnel_capture_task_loop",
    "_stock_master_daily_purge_task_loop": "stock_master_daily_purge_task_loop",
}


def test_data_load_tasks_does_not_import_scheduler():
    """순환 import 차단 — data_load_tasks 는 scheduler 를 import 하지 않는다."""
    tree = ast.parse(_DLT.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if "scheduler" in a.name]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith("scheduler") or mod.endswith("scheduler."):
                offenders.append(mod)
    assert not offenders, f"data_load_tasks 는 scheduler import 금지 (순환) — {offenders}"


def test_all_task_functions_exist_in_data_load_tasks():
    """8 task 함수가 data_load_tasks 에 존재 (본체 이관 완료)."""
    tree = ast.parse(_DLT.read_text(encoding="utf-8"))
    fns = {
        n.name for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef)
    }
    missing = set(_WRAPPERS.values()) - fns
    assert not missing, f"data_load_tasks 이관 누락 함수 — {missing}"


def test_scheduler_wrappers_delegate_to_data_load_tasks():
    """scheduler 8 wrapper 가 data_load_tasks.<fn> 로 위임 (본체 잔류 금지)."""
    tree = ast.parse(_SCHED.read_text(encoding="utf-8"))
    wrapper_nodes = {
        n.name: n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name in _WRAPPERS
    }
    assert set(wrapper_nodes) == set(_WRAPPERS), (
        f"scheduler wrapper 누락 — {set(_WRAPPERS) - set(wrapper_nodes)}"
    )
    for wname, node in wrapper_nodes.items():
        expected_fn = _WRAPPERS[wname]
        delegated = False
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                if (
                    sub.func.attr == expected_fn
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == "data_load_tasks"
                ):
                    delegated = True
                    break
        assert delegated, (
            f"{wname} 가 data_load_tasks.{expected_fn} 위임 안 함 (본체 잔류 의심)"
        )


def test_scheduler_bloat_reduced():
    """scheduler.py 재비대 시정 — B1 후 < 4,000L (사이클 67 수준 방향 복귀)."""
    line_count = len(_SCHED.read_text(encoding="utf-8").splitlines())
    assert line_count < 4000, (
        f"scheduler.py {line_count}L — B1 위임 후 < 4,000L 의무 (재비대 시정)"
    )
