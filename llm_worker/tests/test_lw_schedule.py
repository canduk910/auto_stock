"""cycle446 — 08:15/08:35/08:55 KST 루프(`lw/schedule.py`, 설계 §3.2)."""
from __future__ import annotations

from datetime import timedelta

import pytest

from lw import schedule
from lw_testkit import kst

pytestmark = pytest.mark.unit


def test_next_run_at_before_first_slot():
    assert schedule.next_run_at(kst(2026, 10, 14, 7, 0)) == kst(2026, 10, 14, 8, 15)


def test_next_run_at_between_slots():
    assert schedule.next_run_at(kst(2026, 10, 14, 8, 20)) == kst(2026, 10, 14, 8, 35)


def test_next_run_at_exactly_on_slot_returns_same_slot():
    assert schedule.next_run_at(kst(2026, 10, 14, 8, 35, 0)) == kst(2026, 10, 14, 8, 35)


def test_next_run_at_after_last_slot_rolls_to_tomorrow():
    assert schedule.next_run_at(kst(2026, 10, 14, 9, 0)) == kst(2026, 10, 15, 8, 15)


def test_due_today_up_to_window_boundaries():
    assert schedule.due_today_up_to(kst(2026, 10, 14, 8, 15)) is True
    assert schedule.due_today_up_to(kst(2026, 10, 14, 8, 55)) is True
    assert schedule.due_today_up_to(kst(2026, 10, 14, 8, 14, 59)) is False
    assert schedule.due_today_up_to(kst(2026, 10, 14, 8, 55, 1)) is False


class _FakeClock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, secs):
        self.now += timedelta(seconds=secs)


@pytest.mark.asyncio
async def test_run_forever_fires_three_times_a_day_then_waits_for_tomorrow():
    clock = _FakeClock(kst(2026, 10, 14, 8, 10))
    calls = []

    async def run_once():
        calls.append(clock.now)

    async def fake_sleep(secs):
        clock.advance(secs)

    def stop():
        return len(calls) >= 3

    await schedule.run_forever(run_once, now=clock, sleep=fake_sleep, stop=stop)
    assert len(calls) == 3
    assert calls[0].time().replace(microsecond=0) >= schedule.time(8, 15)
    # 세 번 모두 같은 날짜(오늘) 안에서 일어난다.
    assert all(c.date() == kst(2026, 10, 14).date() for c in calls)


@pytest.mark.asyncio
async def test_run_forever_container_start_after_window_waits_for_next_day():
    clock = _FakeClock(kst(2026, 10, 14, 9, 10))  # 08:55 지남
    calls = []

    async def run_once():
        calls.append(clock.now)

    async def fake_sleep(secs):
        clock.advance(secs)

    def stop():
        return len(calls) >= 1

    await schedule.run_forever(run_once, now=clock, sleep=fake_sleep, stop=stop)
    assert len(calls) == 1
    assert calls[0].date() == kst(2026, 10, 15).date(), "오늘은 건너뛰고 다음 날 08:15 에 돈다"
    assert calls[0].time() == schedule.time(8, 15)
