"""cycle409 — 사용자 결정 10-04 Q1: 매일 자동 대사 훅 (`src/engine/trade_cost_reconcile_task.py`).

실행 시각은 코드 상수가 아니라 `system_config.trade_cost_reconcile_time`(`{"value":"HH:MM","days":N}`) —
**키 없음 = 실행 안 함**(관측 기능이라 꺼짐이 기본). 시각은 사용자가 첫날 실측 뒤 정한다.

| # | 계약 |
|---|---|
| T1 | `parse_schedule` — `HH:MM`(00~23:00~59 두 자리) 만 받는다 · 키 없음/None/형식 오류/루프 수명 밖 = None(꺼짐) · `days` 기본 1, 1~31 밖 = None |
| T2 | `is_due` — 오늘 아직 안 돌았고 `at ≤ now < at + 60분` 일 때만 참(늦은 기동이 장중에 몰래 돌지 않게) |
| T3 | 키 없음 = 그 시각이 와도 `reconcile` 을 부르지 않는다 · 키 조회 예외도 꺼짐으로 읽고 루프를 깨지 않는다 |
| T4 | 시각이 오면 직전 영업일 1일(`days=N` 이면 직전 영업일까지 N 달력일)을 `reconcile(from, to)` 한다 · 하루 1회 |
| T5 | 오늘이 휴장일(False)이면 돌지 않는다 · 직전 영업일을 모르면(None) WARNING 1행 후 돌지 않는다 |
| T6 | `reconcile` 실패·상한 초과 = `[trade_cost_reconcile_failed]` WARNING 1행으로 흡수 · 루프는 계속 · 같은 날 재시도 없음 |
| T7 | 성공 = `[trade_cost_reconcile_done]` INFO 1행 |
| T8 | `_running` 이 꺼지면 루프가 끝난다 |
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
TODAY = date(2026, 10, 6)   # 화
PREV = date(2026, 10, 5)    # 월


def _mod():
    return importlib.import_module("src.engine.trade_cost_reconcile_task")


# ── T1 ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ({"value": "08:30"}, (time(8, 30), 1)),
    ({"value": "21:00", "days": 3}, (time(21, 0), 3)),
    ("08:30", (time(8, 30), 1)),
])
def test_t1_parse_ok(raw, expected):
    assert _mod().parse_schedule(raw) == expected


@pytest.mark.parametrize("raw", [
    None, {}, {"value": None}, {"value": ""}, {"value": "8:30"}, {"value": "24:00"},
    {"value": "08:60"}, {"value": "0830"}, {"value": " 08:30"}, {"value": 830},
    {"value": "07:44"}, {"value": "21:30"}, {"value": "23:00"},
    {"value": "08:30", "days": 0}, {"value": "08:30", "days": 32},
    {"value": "08:30", "days": "3"}, {"value": "08:30", "days": True},
])
def test_t1_parse_off(raw):
    assert _mod().parse_schedule(raw) is None


# ── T2 ───────────────────────────────────────────────────────────────────────

def _at(h, m, d=TODAY):
    return datetime.combine(d, time(h, m), tzinfo=KST)


@pytest.mark.parametrize("now,done,expected", [
    (_at(8, 29), None, False),
    (_at(8, 30), None, True),
    (_at(9, 29), None, True),
    (_at(9, 30), None, False),
    (_at(8, 31), TODAY, False),
    (_at(8, 31), PREV, True),
])
def test_t2_is_due(now, done, expected):
    assert _mod().is_due(now, time(8, 30), done) is expected


# ── 루프 하네스 ───────────────────────────────────────────────────────────────

class _Clock:
    def __init__(self, times):
        self.times = list(times)
        self.i = 0

    def now(self):
        return self.times[min(self.i, len(self.times) - 1)]


@pytest.fixture
def env(monkeypatch):
    m = _mod()
    sched = SimpleNamespace(_running=True)
    clock = _Clock([_at(8, 30)])
    state = {"schedule": {"value": "08:30"}}

    async def get_raw():
        s = state["schedule"]
        if isinstance(s, Exception):
            raise s
        return s

    async def fake_sleep(_secs):
        clock.i += 1
        if clock.i >= len(clock.times):
            sched._running = False

    reconcile = AsyncMock(return_value={"saved_rows": 3, "totals_match": True, "kis_rows": 3})
    is_open = AsyncMock(return_value=True)
    prev = AsyncMock(return_value=PREV)
    monkeypatch.setattr(m, "_now_kst", clock.now)
    monkeypatch.setattr(m, "_sleep", fake_sleep)
    monkeypatch.setattr(m.system_config, "get_trade_cost_reconcile_schedule_raw", get_raw)
    monkeypatch.setattr(m.trade_cost, "reconcile", reconcile)
    monkeypatch.setattr(m.trading_calendar, "is_open_day", is_open)
    monkeypatch.setattr(m.trading_calendar, "previous_trading_day", prev)
    return SimpleNamespace(m=m, sched=sched, clock=clock, state=state, reconcile=reconcile,
                           is_open=is_open, prev=prev)


def _marked(caplog, prefix, level=logging.WARNING):
    return [r for r in caplog.records
            if r.levelno >= level and r.getMessage().startswith(prefix + " ")]


# ── T3 ───────────────────────────────────────────────────────────────────────

async def test_t3_no_key_never_runs(env):
    env.state["schedule"] = None
    env.clock.times = [_at(8, 30), _at(8, 31), _at(12, 0)]
    await env.m.task_loop(env.sched)
    env.reconcile.assert_not_awaited()


async def test_t3_key_read_error_is_off_and_loop_survives(env):
    env.state["schedule"] = RuntimeError("db down")
    env.clock.times = [_at(8, 30), _at(8, 31)]
    await env.m.task_loop(env.sched)
    env.reconcile.assert_not_awaited()
    assert env.sched._running is False  # 끝까지 돌았다


# ── T4 ───────────────────────────────────────────────────────────────────────

async def test_t4_runs_previous_trading_day_once(env, caplog):
    caplog.set_level(logging.INFO)
    env.clock.times = [_at(8, 29), _at(8, 30), _at(8, 31), _at(8, 45)]
    await env.m.task_loop(env.sched)
    env.reconcile.assert_awaited_once_with(PREV, PREV)
    env.prev.assert_awaited_with(TODAY)
    assert len(_marked(caplog, "[trade_cost_reconcile_done]", logging.INFO)) == 1


async def test_t4_days_window(env):
    env.state["schedule"] = {"value": "08:30", "days": 3}
    await env.m.task_loop(env.sched)
    env.reconcile.assert_awaited_once_with(PREV - timedelta(days=2), PREV)


async def test_t4_schedule_change_takes_effect_without_restart(env, monkeypatch):
    env.state["schedule"] = None
    env.clock.times = [_at(8, 30), _at(8, 31), _at(8, 32)]

    calls = {"n": 0}
    orig = env.m.system_config.get_trade_cost_reconcile_schedule_raw

    async def flip():
        calls["n"] += 1
        if calls["n"] >= 2:
            env.state["schedule"] = {"value": "08:30"}
        return await orig()

    monkeypatch.setattr(env.m.system_config, "get_trade_cost_reconcile_schedule_raw", flip)
    await env.m.task_loop(env.sched)
    env.reconcile.assert_awaited_once()


# ── T5 ───────────────────────────────────────────────────────────────────────

async def test_t5_holiday_skips(env):
    env.is_open.return_value = False
    await env.m.task_loop(env.sched)
    env.reconcile.assert_not_awaited()


async def test_t5_unknown_previous_day_warns_and_skips(env, caplog):
    env.prev.return_value = None
    env.clock.times = [_at(8, 30), _at(8, 31)]
    await env.m.task_loop(env.sched)
    env.reconcile.assert_not_awaited()
    assert len(_marked(caplog, "[trade_cost_reconcile_failed]")) == 1


# ── T6 ───────────────────────────────────────────────────────────────────────

async def test_t6_failure_one_warning_no_retry_same_day(env, caplog):
    env.reconcile.side_effect = RuntimeError("KIS 500")
    env.clock.times = [_at(8, 30), _at(8, 31), _at(8, 32)]
    await env.m.task_loop(env.sched)
    assert env.reconcile.await_count == 1
    assert len(_marked(caplog, "[trade_cost_reconcile_failed]")) == 1
    assert env.sched._running is False


async def test_t6_timeout_is_capped(env, caplog, monkeypatch):
    monkeypatch.setattr(env.m, "_RUN_TIMEOUT_SECS", 0.01)

    async def hang(*_a, **_k):
        await asyncio.sleep(5)

    env.reconcile.side_effect = hang
    await env.m.task_loop(env.sched)
    assert len(_marked(caplog, "[trade_cost_reconcile_failed]")) == 1


async def test_t6_runs_again_next_day(env):
    tomorrow = TODAY + timedelta(days=1)
    env.clock.times = [_at(8, 30), _at(8, 31), _at(8, 30, tomorrow)]
    env.prev.side_effect = [PREV, TODAY]
    await env.m.task_loop(env.sched)
    assert [c.args for c in env.reconcile.await_args_list] == [(PREV, PREV), (TODAY, TODAY)]


# ── T8 ───────────────────────────────────────────────────────────────────────

async def test_t8_exits_when_not_running(env):
    env.sched._running = False
    await env.m.task_loop(env.sched)
    env.reconcile.assert_not_awaited()
