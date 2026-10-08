"""거래일지 워커 루프(cycle412 계약 3.9절). 과거분 적재 모듈을 전혀 모른다."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from jw.config import BACKOFF_MAX_SECONDS, CYCLE_SECONDS, G0_PATH, G1_PATH, IDLE_CYCLE_SECONDS
from jw.grammar import parse_line
from jw.http import JournalFetchError, fetch
from jw.pairing import Pairer
from jw.stops import StopTracker
from jw.tailer import read_chunk

KST = timezone(timedelta(hours=9))


def backoff_delay(failures: int) -> float:
    return min(CYCLE_SECONDS * (2 ** failures), BACKOFF_MAX_SECONDS)


async def run_forever(rotate, *, sleep=asyncio.sleep, stop=lambda: False) -> None:
    failures = 0
    while not stop():
        delay = CYCLE_SECONDS
        try:
            status = await rotate()
        except Exception:
            failures += 1
            delay = backoff_delay(failures)
        else:
            if status == "active":
                failures = 0
                delay = CYCLE_SECONDS
            elif status == "idle":
                failures = 0
                delay = IDLE_CYCLE_SECONDS
            else:
                failures += 1
                delay = backoff_delay(failures)
        finally:
            await sleep(delay)


class Worker:
    def __init__(self, *, client, db, log_dir, pairer=None, tracker=None, now=None):
        self.client = client
        self.db = db
        self.log_dir = log_dir
        self._pairer = pairer
        self._tracker = tracker
        self._now = now
        self._booted = False
        self._cursor = None
        self._prev_chunk_end = None

    async def _boot(self):
        self._cursor = await self.db.load_cursor()
        self._prev_chunk_end = self._cursor
        last_rows = await self.db.last_stop_rows()
        if self._pairer is None:
            self._pairer = Pairer()
        if self._tracker is None:
            self._tracker = StopTracker(last_rows=last_rows)
        self._booted = True

    def _clock(self):
        return self._now() if self._now is not None else datetime.now(KST)

    async def rotate(self) -> str:
        if not self._booted:
            await self._boot()

        now = self._clock()
        degraded = False
        g0 = None
        try:
            g0 = await fetch(self.client, G0_PATH)
        except JournalFetchError:
            degraded = True
            g0 = None

        idle = g0 is None or (not g0.get("running")) or g0.get("phase") == "idle"
        if g0 is not None and idle:
            return "idle"

        g1 = None
        if g0 is not None:
            try:
                g1 = await fetch(self.client, G1_PATH)
            except JournalFetchError:
                degraded = True
                g1 = None

        self._pairer.feed_snapshot(g0, g1, now)

        lines, new_cursor = read_chunk(self.log_dir, self._cursor)
        events = [e for e in (parse_line(ln) for ln in lines) if e is not None]
        self._pairer.feed_events(events)

        result = self._pairer.drain(trade_strategies={})
        for row in result["orders"]:
            await self.db.insert_order(row)
        for ev in result["stops"]:
            await self.db.insert_stop(ev)

        stop_events = self._tracker.observe(observed_at=now, g0=g0, g1=g1)
        for ev in stop_events:
            await self.db.insert_stop(ev)

        save_target = self._prev_chunk_end if self._prev_chunk_end is not None else \
            {**new_cursor, "byte_offset": 0}
        await self.db.save_cursor(save_target)
        self._prev_chunk_end = new_cursor
        self._cursor = new_cursor

        return "degraded" if degraded else "active"
