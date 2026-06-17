"""사이클 152 hotfix — _wait_until target 이후 시점 폭주 결함 영구 차단.

사이클 160 의미 전환 (2026-06-17):
사이클 152 hotfix 가 `_wait_until` 본질 (target 도달 즉시 break) 을 깨뜨려
`run_daily` 영역 모든 phase 전환 누락 결함 도입. 6/17 알테오젠+알지노믹스
15:20 강제청산 누락 운영 사례. 사이클 160 시정 = 2 모드 분기
(default=즉시 break, advance_if_passed=True=내일 대기).

본 파일의 사이클 152 케이스 = 사이클 152 의도 자체는 보존하지만 default 모드는
이제 즉시 return 으로 의미 전환. `advance_if_passed=True` 명시 시점만 사이클 152
동작 유지. 사이클 66 K-2 의미 전환 패턴 답습.

운영 사례 (verbatim):
- 2026-06-16 18:00 KST 시점 EC2 자동 배포 후 사이클 122/126/129/150 task 모두 폭주
- _wait_until(16:00) / (16:10) / (16:30) / (16:15) 모두 즉시 break
- task_loop_helper while 루프 → once 호출 → 즉시 break → 무한 반복
- Supabase HTTP/2 ConnectionTerminated / Server disconnected / Broken pipe 폭주
- [stock_master_daily_purge] 실패 graceful 5초 간격 발화

회귀 가드 (사이클 152 시점, 사이클 160 의미 전환 반영):
- G-152-PAST-1 (HIGH): target 이미 지난 시점 → `advance_if_passed=True` 시 다음 날 대기
- G-152-FUTURE-1: target 미래 시점 → 정상 대기
- G-152-AST: 이전 결함 패턴 (`if now >= target: break` 본체 영역) 영구 차단
"""

from __future__ import annotations

import asyncio
import ast
import pathlib
from datetime import datetime, time, timedelta
from unittest.mock import patch

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SCHEDULER_PATH = _REPO_ROOT / "src" / "engine" / "scheduler.py"


class _FakeScheduler:
    """`_wait_until` 단독 테스트 영역."""

    def __init__(self):
        self._running = True


@pytest.mark.asyncio
async def test_g_152_past_1_target_already_passed_no_immediate_break():
    """G-152-PAST-1 (HIGH) — target 이미 지난 시점 즉시 break 금지.

    재현 = 6/16 18:00 KST 시점 _wait_until(16:15) 호출
    이전 결함 = now >= target → 즉시 break → 폭주
    시정 영속 = target_dt = 내일 16:15 → wait_secs > 0 → asyncio.sleep
    """
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True

    # 18:00 KST 영역 _wait_until(16:15) 영역 호출 simulation
    target_18 = time(16, 15)
    now_18 = datetime(2026, 6, 16, 18, 0, 0)

    sleep_calls: list[float] = []

    real_datetime = datetime

    class _MockDT:
        @classmethod
        def now(cls):
            return now_18

    async def _fake_sleep(secs: float):
        sleep_calls.append(secs)
        # 첫 sleep 후 _running=False 영역 → 루프 종료
        sched._running = False

    with patch("src.engine.scheduler.datetime", _MockDT), \
         patch("asyncio.sleep", _fake_sleep):
        # 사이클 160 의미 전환 — `advance_if_passed=True` 명시 시 사이클 152 동작 영속
        await sched._wait_until(target_18, advance_if_passed=True)

    # 즉시 break 금지 = asyncio.sleep 호출 ≥ 1
    assert len(sleep_calls) >= 1, "target 지난 시점 즉시 break 결함 (사이클 152 영구 차단)"
    # 첫 sleep > 0 (안전망 sleep(10) 또는 정상 wait_secs)
    assert sleep_calls[0] > 0


@pytest.mark.asyncio
async def test_g_152_future_1_target_future_normal_wait():
    """G-152-FUTURE-1 — target 미래 시점 정상 대기 영역 영속."""
    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched._running = True

    # 10:00 KST 영역 _wait_until(16:15) 영역 호출 simulation
    target = time(16, 15)
    now = datetime(2026, 6, 16, 10, 0, 0)

    sleep_calls: list[float] = []

    class _MockDT:
        @classmethod
        def now(cls):
            return now

    async def _fake_sleep(secs: float):
        sleep_calls.append(secs)
        sched._running = False

    with patch("src.engine.scheduler.datetime", _MockDT), \
         patch("asyncio.sleep", _fake_sleep):
        await sched._wait_until(target)

    # 정상 대기 = sleep ≥ 1회
    assert len(sleep_calls) >= 1
    # 첫 sleep > 0 (최대 60초 cap)
    assert sleep_calls[0] > 0
    assert sleep_calls[0] <= 60


def test_g_152_ast_now_ge_target_immediate_break_forbidden():
    """G-152-AST (HIGH) — `if now >= target: break` 패턴 영구 차단.

    사이클 152 hotfix 패턴 영역 영구 영속 = 폭주 결함 재발 차단.
    """
    src = _SCHEDULER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # _wait_until 함수 body 영역 검색
    target_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_wait_until":
            target_func = node
            break

    assert target_func is not None, "_wait_until 함수 영역 미발견"

    # body 영역 영역 `if now >= target: break` 패턴 검색
    forbidden = False
    for sub in ast.walk(target_func):
        if isinstance(sub, ast.If):
            # 조건 = `now >= target` (or `.time() >= target`)
            test_str = ast.unparse(sub.test) if hasattr(ast, "unparse") else ""
            body_str = "\n".join(
                ast.unparse(b) if hasattr(ast, "unparse") else ""
                for b in sub.body
            )
            if ">= target" in test_str and "break" in body_str and "timedelta" not in body_str:
                # 사이클 152 시정 = `if now_dt >= target_dt: target_dt += timedelta(days=1)` 영역 영속
                # 결함 = `if now >= target: break` 영역 영구 차단
                if "target_dt += " not in body_str:
                    forbidden = True
                    break

    assert not forbidden, (
        "_wait_until 영역 `if now >= target: break` 폭주 결함 패턴 영구 차단 (사이클 152)"
    )
