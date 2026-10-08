"""거래일지 워커 루프(cycle412 계약 3.9절 · 보완2 7절 N1~N3). 과거분 적재 모듈을 전혀 모른다."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from jw.config import BACKOFF_MAX_SECONDS, CYCLE_SECONDS, G0_PATH, G1_PATH, IDLE_CYCLE_SECONDS, \
    MAX_READ_BYTES, RECONCILE_MIN_AGE_SECONDS
from jw.grammar import parse_line
from jw.http import JournalFetchError, fetch
from jw.pairing import Pairer
from jw.reconcile import check_identities, emit_gap, rows_from_trade_history
from jw.stops import StopTracker
from jw.tailer import read_chunk

KST = timezone(timedelta(hours=9))
log = logging.getLogger(__name__)
RECONCILE_EVERY = 60

# 대사 행(reconcile 이 trade_history 로 만든 보강 행)의 source — 항등식에 세지 않는다(계약 3.5절 C4).
_EMPTY_SOURCES = ("unmatched", "external")
# 읽기 창이 이 바이트 이내로 꽉 찼으면 "따라잡는 중"으로 본다(청크 끝의 미완성 줄 보류분 여유).
_CATCHUP_MARGIN = 64 * 1024

_LINE_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _last_line_ts(lines):
    """청크의 마지막 줄 시각(KST) — 문법이 모르는 줄도 센다(보완2 N1). 줄이 없으면 None."""
    for ln in reversed(lines):
        m = _LINE_TS_RE.match(ln)
        if m:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    return None


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
        self._prev_chunk_last_ts = None
        self._last_reconcile = None
        self._last_reconcile_result = None
        self._day = None
        self._done_events: list = []
        self._day_rows: list = []
        self._journal_keys: set = set()
        self._done_order_sides: set = set()
        self._counted_pairs: set = set()

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
            self._done_order_sides, self._counted_pairs = set(), set()

    async def _write_row(self, row):
        is_empty = row["source"] in _EMPTY_SOURCES
        try:
            counted = await self.db.insert_order(row)
            if not counted and not is_empty:
                # insert 가 False 라는 것은 그 키의 행이 이미 있다는 뜻 — promote 가 예외 없이 끝나면
                # (True 든 False 든) 그 키에 측정 가능한 행이 있다는 것이 확인된다(보완2 N1).
                await self.db.promote_order(row)
                counted = True
        except Exception as exc:
            log.warning("[journal_write_error] order_no=%s side=%s %s: %s", row.get("order_no"),
                        row.get("side"), type(exc).__name__, exc)
            return
        key = (row["order_date"], row["order_no"], row["side"])
        self._journal_keys.add(key)
        if is_empty:
            return
        pair = (row["order_no"], row["side"])
        if pair in self._counted_pairs:
            return
        self._counted_pairs.add(pair)
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

    async def _reconcile(self, now, w, *, catching_up):
        if w is None or catching_up:
            return
        if self._last_reconcile is not None and (now - self._last_reconcile).total_seconds() < RECONCILE_EVERY:
            return
        self._last_reconcile = now
        start = datetime.combine(w.astimezone(KST).date(), datetime.min.time(), tzinfo=KST)
        try:
            trades = await self.db.trades_since(start)
        except Exception as exc:
            log.warning("[journal_reconcile_error] %s: %s", type(exc).__name__, exc)
            return
        for row in rows_from_trade_history(trades, self._journal_keys, self._pairer.external_notice_orders(),
                                           now=w):
            await self._write_row(row)
        cutoff = w - timedelta(seconds=RECONCILE_MIN_AGE_SECONDS)
        res = check_identities([e for e in self._done_events if e["ts"] <= cutoff],
                               [r for r in self._day_rows if r["noted_at"] <= cutoff])
        if res != self._last_reconcile_result:
            emit_gap(res, log)
            self._last_reconcile_result = res

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
        cur_chunk_last_ts = _last_line_ts(lines)
        catching_up = sum(len(ln.encode("utf-8")) + 1 for ln in lines) >= MAX_READ_BYTES - _CATCHUP_MARGIN
        w = self._prev_chunk_last_ts

        events = [e for e in (parse_line(ln) for ln in lines) if e is not None]
        for e in events:
            if e["kind"] != "order_done":
                continue
            pair = (e["order_no"], e["side"])
            if pair in self._done_order_sides:
                continue
            self._done_order_sides.add(pair)
            self._done_events.append({"kind": "order_done", "side": e["side"], "order_no": e["order_no"],
                                       "ts": e["ts"]})
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
        self._prev_chunk_last_ts = cur_chunk_last_ts if cur_chunk_last_ts is not None else \
            self._prev_chunk_last_ts
        self._cursor = new_cursor

        await self._reconcile(now, w, catching_up=catching_up)
        return "degraded" if degraded else "active"
