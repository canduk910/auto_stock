"""사이클 159 — Supabase HTTP/2 race 차단 stagger 임계 상향 회귀 가드.

배경 (운영 실측 2026-06-17, Supabase MCP):
- 사이클 158 stagger (0/60/120/180) 배포 후 24h 실측:
  master_skip 992 / basics_skip 1,958 / Server disc 303 / ConnTerm 310 / deque_mut 16
- 약 50% 감소 효과 있으나 운영 불충분
- 근본 원인 = stagger 시간(60s) < 단일 task 처리 시간(~280s)

시정 (옵션 C — refactor-expert 자문 산출물 채택):
- full_universe = 0 / daily = 240 / basics = 480 / master = 720 초

회귀 가드 8 케이스:
- G-159-STAGGER-1: 4 task initial_delay_secs = 0/240/480/720 정확 발화 (AST 정적)
- G-159-STAGGER-2: 4 task wrapper 별 인자 정확 매칭
- G-159-STAGGER-3: 사이클 158 default 0 인자 회귀 보존
- G-159-SAFETY-1: risk/order_engine/realtime/auth import 0건 (HIGH)
- G-159-SAFETY-2: 매수 진입 전 영역 한정 (사이클 38 명문화)
- G-159-AST-1: scheduler.py initial_delay_secs= 호출 ≥ 4건
- G-159-AST-2: 4 wrapper sub-method 명 정확 호출
- G-159-INT-1: task_loop_helper initial_delay_secs > 0 시 asyncio.sleep 호출
"""
from __future__ import annotations

import ast
import inspect
from datetime import time as dtime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import task_loop_helper as helper_mod
from src.engine.task_loop_helper import run_periodic_task_loop


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCHEDULER_PATH = _REPO_ROOT / "src" / "engine" / "scheduler.py"


# 사이클 159 신규 stagger 임계 (옵션 C)
_CYCLE_159_STAGGER = {
    "_full_universe_load_task_loop": 0,
    "_stock_master_daily_load_task_loop": 240,
    "_stock_master_basics_refresh_task_loop": 480,
    "_stock_master_master_load_task_loop": 720,
}


def _extract_stagger_per_wrapper() -> dict[str, int]:
    """scheduler.py 4 task wrapper 영역에서 initial_delay_secs 값 추출."""
    tree = ast.parse(_SCHEDULER_PATH.read_text())
    target_methods = set(_CYCLE_159_STAGGER.keys())
    delay_values: dict[str, int] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if node.name not in target_methods:
            continue
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
    return delay_values


# ──────────────────────────────────────────────────────────────────────
# G-159-STAGGER-1 — 4 task initial_delay_secs = 0/240/480/720 정확 발화
# ──────────────────────────────────────────────────────────────────────


def test_G_159_STAGGER_1_four_tasks_match_cycle159_threshold() -> None:
    """4 task wrapper 영역에서 옵션 C 권고 stagger 정확 적용."""
    delay_values = _extract_stagger_per_wrapper()

    assert len(delay_values) == 4, (
        f"4 wrapper 모두 initial_delay_secs 키워드 명시 의무 "
        f"(실측 {len(delay_values)}/4 = {sorted(delay_values.keys())})"
    )

    for method_name, expected_delay in _CYCLE_159_STAGGER.items():
        actual = delay_values.get(method_name)
        assert actual == expected_delay, (
            f"{method_name} initial_delay_secs = {expected_delay} 의무 "
            f"(실측 {actual}, 사이클 159 옵션 C 권고 영역)"
        )


# ──────────────────────────────────────────────────────────────────────
# G-159-STAGGER-2 — 4 task wrapper 별 인자 정확 매칭 (full=0 / daily=240 / basics=480 / master=720)
# ──────────────────────────────────────────────────────────────────────


def test_G_159_STAGGER_2_wrapper_mapping_exact() -> None:
    """wrapper 별 stagger 값 매핑 정확 (옵션 C = 4분/8분/12분 분산)."""
    delay_values = _extract_stagger_per_wrapper()

    # full_universe = 0 (즉시 발화, 가장 무거운 task 선행 처리)
    assert delay_values.get("_full_universe_load_task_loop") == 0, (
        "full_universe = 0 영속 (사이클 158 답습 + 사이클 159 영구 유지)"
    )

    # daily = 240 (full_universe 280s 처리 시간 정합)
    assert delay_values.get("_stock_master_daily_load_task_loop") == 240, (
        "daily = 240 (4분 간격 = 단일 task 처리 시간 정합)"
    )

    # basics = 480 (daily 완료 후 진입)
    assert delay_values.get("_stock_master_basics_refresh_task_loop") == 480, (
        "basics = 480 (8분 간격 = 30s overlap 허용)"
    )

    # master = 720 (basics 완료 후 진입)
    assert delay_values.get("_stock_master_master_load_task_loop") == 720, (
        "master = 720 (12분 간격 = 30s overlap 허용)"
    )


# ──────────────────────────────────────────────────────────────────────
# G-159-STAGGER-3 — task_loop_helper default 0 회귀 보존 (사이클 158)
# ──────────────────────────────────────────────────────────────────────


def test_G_159_STAGGER_3_helper_default_zero_preserved() -> None:
    """task_loop_helper.run_periodic_task_loop initial_delay_secs default = 0 회귀 보존."""
    sig = inspect.signature(run_periodic_task_loop)
    assert "initial_delay_secs" in sig.parameters, (
        "사이클 158 도입 initial_delay_secs 인자 회귀 보존 의무"
    )
    param = sig.parameters["initial_delay_secs"]
    assert param.default == 0, (
        f"default 0 회귀 보존 의무 (실측 {param.default}, 사이클 158 G-158-Q3-1 영속)"
    )


# ──────────────────────────────────────────────────────────────────────
# G-159-SAFETY-1 (HIGH) — risk/order_engine/realtime/auth 영역 변경 0
# ──────────────────────────────────────────────────────────────────────


def test_G_159_SAFETY_1_helper_no_risk_order_realtime_auth_import() -> None:
    """task_loop_helper.py 영역 = lifecycle 영역 한정 (매매 hot path 변경 0).

    risk / order_engine / realtime / auth 영역 import 0건 의무.
    """
    src = (_REPO_ROOT / "src" / "engine" / "task_loop_helper.py").read_text()
    forbidden_imports = [
        "src.engine.risk",
        "src.engine.order_engine",
        "src.realtime.",
        "src.auth.",
    ]
    for forbidden in forbidden_imports:
        assert forbidden not in src, (
            f"task_loop_helper 영역 매매 hot path import 금지 "
            f"(forbidden '{forbidden}' 발견 — 사이클 38 명문화 영속)"
        )


# ──────────────────────────────────────────────────────────────────────
# G-159-SAFETY-2 (HIGH) — 매수 진입 전 영역 한정 (사이클 38 명문화)
# ──────────────────────────────────────────────────────────────────────


def test_G_159_SAFETY_2_stagger_only_in_scanner_lifecycle() -> None:
    """stagger 영역 = scheduler 4 task wrapper 한정 (매수 진입 전 영역).

    매도/익일청산/손절/15:20 강제청산 영역 = task lifecycle 영역 외 의무.
    """
    tree = ast.parse(_SCHEDULER_PATH.read_text())
    stagger_call_methods: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
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
                        stagger_call_methods.add(node.name)

    allowed_methods = set(_CYCLE_159_STAGGER.keys())
    forbidden_methods = stagger_call_methods - allowed_methods

    assert not forbidden_methods, (
        f"매수 진입 전 영역 외 stagger 발화 금지 "
        f"(사이클 38 명문화 영속) — forbidden = {forbidden_methods}"
    )


# ──────────────────────────────────────────────────────────────────────
# G-159-AST-1 — scheduler.py initial_delay_secs= 호출 사이트 ≥ 4건
# ──────────────────────────────────────────────────────────────────────


def test_G_159_AST_1_scheduler_initial_delay_keyword_count() -> None:
    """scheduler.py 영역 initial_delay_secs= 키워드 인자 호출 ≥ 4건 (4 task)."""
    tree = ast.parse(_SCHEDULER_PATH.read_text())
    keyword_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "initial_delay_secs":
            keyword_count += 1

    assert keyword_count >= 4, (
        f"scheduler.py initial_delay_secs= 호출 사이트 ≥ 4건 의무 "
        f"(실측 {keyword_count} = 사이클 159 4 wrapper 영역)"
    )


# ──────────────────────────────────────────────────────────────────────
# G-159-AST-2 — 4 wrapper sub-method 명 정확 호출 (회귀 가드)
# ──────────────────────────────────────────────────────────────────────


def test_G_159_AST_2_four_wrappers_exist() -> None:
    """4 wrapper AsyncFunctionDef 영역 존재 영속 (사이클 134/158/159 영속)."""
    tree = ast.parse(_SCHEDULER_PATH.read_text())
    found_methods: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            if node.name in _CYCLE_159_STAGGER:
                found_methods.add(node.name)

    expected = set(_CYCLE_159_STAGGER.keys())
    missing = expected - found_methods
    assert not missing, (
        f"4 task wrapper 영역 missing = {missing} "
        f"(사이클 134 facade 영속 + 사이클 159 stagger 영역)"
    )


# ──────────────────────────────────────────────────────────────────────
# G-159-INT-1 — task_loop_helper initial_delay_secs > 0 시 asyncio.sleep 호출 (mock)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_G_159_INT_1_initial_delay_invokes_sleep() -> None:
    """initial_delay_secs > 0 시 once_callable 호출 전 asyncio.sleep 발화 (옵션 C 720s 검증)."""
    scheduler = MagicMock()
    scheduler._running = False  # 즉시 종료 = while 루프 진입 차단

    once_mock = AsyncMock(return_value={"total": 0})
    record_mock = MagicMock()
    flush_mock = MagicMock()

    sleep_mock = AsyncMock(return_value=None)
    with patch("src.engine.task_loop_helper.asyncio.sleep", new=sleep_mock):
        await run_periodic_task_loop(
            scheduler=scheduler,
            task_label="cycle159_test",
            wait_time=dtime(16, 30),
            once_callable=once_mock,
            record_fn=record_mock,
            flush_fn=flush_mock,
            summary_log_format="[cycle159] total=%d",
            summary_keys=("total",),
            immediate_first_run=True,
            initial_delay_secs=720,  # 옵션 C master_load 값
        )

    # 720s sleep 호출 ≥ 1건
    sleep_720_calls = [c for c in sleep_mock.call_args_list if c.args and c.args[0] == 720]
    assert len(sleep_720_calls) >= 1, (
        f"initial_delay_secs=720 sleep 호출 부재 "
        f"(전체 sleep_mock = {sleep_mock.call_args_list})"
    )

    # initial_delay 후 once_callable 호출 1회
    assert once_mock.await_count == 1, (
        "initial_delay 후 once_callable 1회 호출 의무 (사이클 106 lifecycle race 차단 영속)"
    )


# ──────────────────────────────────────────────────────────────────────
# 부가 가드 — 사이클 158 회귀 가드 보존 (의미 충돌 0 의무)
# ──────────────────────────────────────────────────────────────────────


def test_G_159_REGRESSION_cycle158_three_distinct_stagger_values() -> None:
    """사이클 158 G-158-Q3-2 영속 = 4 task delay 값 합집합 ≥ 3종 분리.

    사이클 159 옵션 C = 0/240/480/720 = 4종 분리 = 사이클 158 회귀 가드 강화 PASS.
    """
    delay_values = _extract_stagger_per_wrapper()
    unique_delays = set(delay_values.values())
    assert len(unique_delays) >= 3, (
        f"stagger 분리 의무 = ≥ 3종 (실측 {sorted(unique_delays)}, 사이클 158 G-158-Q3-2 영속)"
    )
