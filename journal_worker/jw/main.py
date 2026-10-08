"""거래일지 워커 루프(cycle412 계약 3.9절). 과거분 적재 모듈을 전혀 모른다."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from jw.config import BACKOFF_MAX_SECONDS, CYCLE_SECONDS, G0_PATH, G1_PATH, IDLE_CYCLE_SECONDS, \
    RECONCILE_MIN_AGE_SECONDS
from jw.grammar import parse_line
from jw.http import JournalFetchError, fetch
from jw.pairing import Pairer
from jw.reconcile import check_identities, emit_gap, rows_from_trade_history
from jw.stops import StopTracker
from jw.tailer import read_chunk

KST = timezone(timedelta(hours=9))
log = logging.getLogger(__name__)
RECONCILE_EVERY = 60


def backoff_delay(failures: int) -> float:
    return min(CYCLE_SECONDS * (2 ** failures), BACKOFF_MAX_SECONDS)


async def run_forever(rotate, *, sleep=asyncio.sleep, stop=lambda: False) -> None:
    failures = 0
    while not stop():
        delay = CYCLE_SECONDS
        try:
            status = await rotate()
        except Exception as exc:
            failures += 1
            delay = backoff_delay(failures)
            log.warning("[journal_rotate_error] %s: %s", type(exc).__name__, exc, exc_info=True)
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
        self._last_reconcile = None
        self._day = None
        self._done_events: list = []
        self._day_rows: list = []
        self._journal_keys: set = set()

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

    def _roll_day(self, now):
        d = now.astimezone(KST).date()
        if d != self._day:
            self._day = d
            self._done_events, self._day_rows, self._journal_keys = [], [], set()

    async def _write_row(self, row):
        try:
            await self.db.insert_order(row)
        except Exception as exc:
            log.warning("[journal_write_error] order_no=%s side=%s %s: %s", row.get("order_no"), row.get("side"),
                        type(exc).__name__, exc)
            return
        self._journal_keys.add((row["order_date"], row["order_no"], row["side"]))
        self._day_rows.append({"side": row["side"], "source": row["source"], "reason_code": row["reason_code"],
                               "noted_at": row["noted_at"]})

    async def _trade_strategies(self, now):
        start = datetime.combine(now.astimezone(KST).date(), datetime.min.time(), tzinfo=KST)
        try:
            rows = await self.db.trades_since(start)
        except Exception as exc:
            log.warning("[journal_trade_lookup_error] %s: %s", type(exc).__name__, exc)
            return {}
        return {r["order_no"]: r["strategy"] for r in rows if r.get("strategy")}

    async def _reconcile(self, now):
        if self._last_reconcile is not None and (now - self._last_reconcile).total_seconds() < RECONCILE_EVERY:
            return
        self._last_reconcile = now
        start = datetime.combine(now.astimezone(KST).date(), datetime.min.time(), tzinfo=KST)
        try:
            trades = await self.db.trades_since(start)
        except Exception as exc:
            log.warning("[journal_reconcile_error] %s: %s", type(exc).__name__, exc)
            return
        for row in rows_from_trade_history(trades, self._journal_keys, self._pairer.external_notice_orders(),
                                           now=now):
            await self._write_row(row)
        cutoff = now - timedelta(seconds=RECONCILE_MIN_AGE_SECONDS)
        res = check_identities([e for e in self._done_events if e["ts"] <= cutoff],
                               [r for r in self._day_rows if r["noted_at"] <= cutoff])
        emit_gap(res, log)

    async def rotate(self) -> str:
        if not self._booted:
            await self._boot()

        now = self._clock()
        self._roll_day(now)
        degraded = False
        g0 = None
        try:
            g0 = await fetch(self.client, G0_PATH)
        except JournalFetchError as exc:
            degraded = True
            log.warning("[journal_fetch_error] G0 %s", exc)
            g0 = None

        idle = g0 is None or (not g0.get("running")) or g0.get("phase") == "idle"
        if g0 is not None and idle:
            return "idle"

        g1 = None
        if g0 is not None:
            try:
                g1 = await fetch(self.client, G1_PATH)
            except JournalFetchError as exc:
                degraded = True
                log.warning("[journal_fetch_error] G1 %s", exc)
                g1 = None

        self._pairer.feed_snapshot(g0, g1, now)

        lines, new_cursor = read_chunk(self.log_dir, self._cursor)
        events = [e for e in (parse_line(ln) for ln in lines) if e is not None]
        self._done_events.extend({"kind": "order_done", "side": e["side"], "ts": e["ts"]}
                                 for e in events if e["kind"] == "order_done")
        self._pairer.feed_events(events)

        result = self._pairer.drain(trade_strategies=await self._trade_strategies(now))
        for row in result["orders"]:
            await self._write_row(row)
        for ev in result["stops"]:
            try:
                await self.db.insert_stop(ev)
            except Exception as exc:
                log.warning("[journal_write_error] stop %s: %s", type(exc).__name__, exc)

        for ev in self._tracker.observe(observed_at=now, g0=g0, g1=g1):
            try:
                await self.db.insert_stop(ev)
            except Exception as exc:
                log.warning("[journal_write_error] stop %s: %s", type(exc).__name__, exc)

        save_target = self._prev_chunk_end if self._prev_chunk_end is not None else \
            {**new_cursor, "byte_offset": 0}
        await self.db.save_cursor(save_target)
        self._prev_chunk_end = new_cursor
        self._cursor = new_cursor

        await self._reconcile(now)
        return "degraded" if degraded else "active"
