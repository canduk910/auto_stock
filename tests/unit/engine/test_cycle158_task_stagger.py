"""사이클 158 Q3 — task_loop_helper initial_delay_secs 인자 + scheduler 4 task stagger 회귀 가드.

운영 사례 (2026-06-17 08:13:14 ~ 08:16:39 KST):
- 4 task (full_universe / basics / daily / master) 동시 발화
- Supabase HTTP/2 풀 race → ConnectionTerminated / Broken pipe / Connection reset 폭주

시정 (옵션 C — stagger):
- task_loop_helper: initial_delay_secs 인자 신규 (default 0 = 회귀 보존)
- scheduler 4 task 발화 stagger 명시 (0/60/120/180)

회귀 가드 3 케이스:
- G-158-Q3-1: task_loop_helper.run_periodic_task_loop initial_delay_secs 인자 지원
- G-158-Q3-2: scheduler 4 task wrapper 영역에서 stagger 인자 명시 (AST 정적)
- G-158-Q3-3: default 0 = 회귀 보존 (사이클 152 _wait_until 영속)
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import task_loop_helper as helper_mod
from src.engine.task_loop_helper import run_periodic_task_loop


# ──────────────────────────────────────────────────────────────────────
# G-158-Q3-1 — task_loop_helper.run_periodic_task_loop initial_delay_secs 인자 지원
# ──────────────────────────────────────────────────────────────────────


def test_G_158_Q3_1_helper_initial_delay_param_exists() -> None:
    """run_periodic_task_loop 시그너처에 initial_delay_secs 인자 존재 + default=0."""
    sig = inspect.signature(run_periodic_task_loop)
    assert "initial_delay_secs" in sig.parameters, (
        "task_loop_helper initial_delay_secs 인자 부재 (사이클 158 Q3 stagger 영역)"
    )
    param = sig.parameters["initial_delay_secs"]
    assert param.default == 0, (
        f"initial_delay_secs default = 0 회귀 보존 의무 (실측 {param.default})"
    )


@pytest.mark.asyncio
async def test_G_158_Q3_1_initial_delay_invokes_sleep_before_once() -> None:
    """initial_delay_secs > 0 시 once_callable 호출 전 asyncio.sleep 발화."""
    scheduler = MagicMock()
    scheduler._running = False  # 즉시 종료 (immediate_first_run + initial_delay 검증만)

    once_mock = AsyncMock(return_value={"total": 0})
    record_mock = MagicMock()
    flush_mock = MagicMock()

    sleep_mock = AsyncMock(return_value=None)
    with patch("src.engine.task_loop_helper.asyncio.sleep", new=sleep_mock):
        from datetime import time
        await run_periodic_task_loop(
            scheduler=scheduler,
            task_label="test_task",
            wait_time=time(16, 0),
            once_callable=once_mock,
            record_fn=record_mock,
            flush_fn=flush_mock,
            summary_log_format="[test] total=%d",
            summary_keys=("total",),
            immediate_first_run=True,
            initial_delay_secs=60,
        )

    # sleep(60) 호출 ≥1건
    sleep_60_calls = [c for c in sleep_mock.call_args_list if c.args and c.args[0] == 60]
    assert len(sleep_60_calls) >= 1, (
        f"initial_delay_secs=60 sleep 호출 부재 (전체 {sleep_mock.call_args_list})"
    )

    # initial_delay sleep 후 once_callable 호출
    assert once_mock.await_count == 1, "initial_delay 후 once_callable 1회 호출 의무"


@pytest.mark.asyncio
async def test_G_158_Q3_1_default_delay_zero_no_sleep_before_once() -> None:
    """initial_delay_secs default(0) 시 sleep 발화 없음 (회귀 보존)."""
    scheduler = MagicMock()
    scheduler._running = False

    once_mock = AsyncMock(return_value={"total": 0})
    record_mock = MagicMock()
    flush_mock = MagicMock()

    sleep_mock = AsyncMock(return_value=None)
    with patch("src.engine.task_loop_helper.asyncio.sleep", new=sleep_mock):
        from datetime import time
        await run_periodic_task_loop(
            scheduler=scheduler,
            task_label="test_task",
            wait_time=time(16, 0),
            once_callable=once_mock,
            record_fn=record_mock,
            flush_fn=flush_mock,
            summary_log_format="[test] total=%d",
            summary_keys=("total",),
            immediate_first_run=True,
            # initial_delay_secs 미지정 = default 0
        )

    # default 0 = 초기 sleep 0건 (sleep(0) 호출 안 되어야 함)
    sleep_initial_calls = [c for c in sleep_mock.call_args_list if c.args and c.args[0] == 0]
    assert len(sleep_initial_calls) == 0, (
        "default initial_delay_secs=0 시 sleep 발화 영역 외 의무 (회귀 보존)"
    )


# ──────────────────────────────────────────────────────────────────────
# G-158-Q3-2 — scheduler 4 task wrapper 영역에서 stagger 인자 명시 (AST 정적)
# ──────────────────────────────────────────────────────────────────────


def test_G_158_Q3_2_scheduler_4_tasks_stagger_keywords() -> None:
    """scheduler.py 4 task wrapper 영역 (_full_universe_load / _stock_master_basics_refresh /
    _stock_master_daily_load / _stock_master_master_load) 영역에 initial_delay_secs 인자 명시 영역.

    4 task 영역 각 stagger 값 = 합집합 ≥ 3종 (0/60/120/180 등 분리 발화).
    """
    src = Path(__file__).parent.parent.parent.parent / "src" / "engine" / "scheduler.py"
    tree = ast.parse(src.read_text())

    target_methods = {
        "_full_universe_load_task_loop",
        "_stock_master_daily_load_task_loop",
        "_stock_master_basics_refresh_task_loop",
        "_stock_master_master_load_task_loop",
    }

    delay_values: dict[str, int] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if node.name not in target_methods:
            continue
        # run_periodic_task_loop 호출 영역에서 initial_delay_secs 키워드 확인
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func_name = ""
                if isinstance(sub.func, ast.Name):
                    func_name = sub.func.id
                elif isinstance(sub.func, ast.Attribute):
                    func_name = sub.func.attr
                if func_name != "run_periodic_task_loop":
                    continue
                for kw in sub.keywords:
                    if kw.arg == "initial_delay_secs":
                        if isinstance(kw.value, ast.Constant):
                            delay_values[node.name] = kw.value.value

    assert len(delay_values) == 4, (
        f"4 task wrapper 영역 initial_delay_secs 키워드 명시 의무 "
        f"(실측 {len(delay_values)}/4 = {list(delay_values.keys())})"
    )

    # stagger 분리 = 4 task 영역 delay 값 합집합 ≥ 3 종 (동시 발화 차단 의무)
    unique_delays = set(delay_values.values())
    assert len(unique_delays) >= 3, (
        f"stagger 분리 의무 (실측 unique delay = {sorted(unique_delays)} / 동시 발화 영역 race 차단 부족)"
    )


# ──────────────────────────────────────────────────────────────────────
# G-158-Q3-3 — 사이클 152 _wait_until hotfix 영속 (변경 0)
# ──────────────────────────────────────────────────────────────────────


def test_G_158_Q3_3_helper_wait_until_invocation_preserved() -> None:
    """task_loop_helper while 루프 영역 _wait_until 호출 영속 (사이클 152 hotfix 영역)."""
    src_path = Path(helper_mod.__file__)
    tree = ast.parse(src_path.read_text())

    wait_until_calls = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "_wait_until":
            wait_until_calls += 1

    assert wait_until_calls >= 1, (
        "task_loop_helper _wait_until 호출 영속 의무 (사이클 152 hotfix 영역)"
    )
