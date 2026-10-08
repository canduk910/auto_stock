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


def _cutoff_split(done_events, day_rows, cutoff):
    """완료 줄·행을 (주문번호, side) 로 짝지어 "두 시각 중 늦은 쪽" 을 함께 기준으로 자른다(보완2 N10).

    짝의 완료 시각과 행의 시각(접수 등)이 1초 벌어져 대사 경계가 그 사이에 걸리면, 독립적으로 자를 때
    한쪽만 포함돼 항등식이 거짓으로 어긋난다 — 짝이 있으면 둘 다 같은(늦은) 기준으로 포함되거나 빠진다.
    짝이 없는 경우(접수 줄 없는 완료·행으로 안 남은 완료 등)는 자기 시각 그대로(기존 동작 그대로).
    """
    done_ts = {(e["order_no"], e["side"]): e["ts"] for e in done_events}
    row_ts = {(r["order_no"], r["side"]): r["noted_at"] for r in day_rows if r.get("order_no") is not None}

    kept_done = []
    for e in done_events:
        paired = row_ts.get((e["order_no"], e["side"]))
        eff = max(e["ts"], paired) if paired is not None else e["ts"]
        if eff <= cutoff:
            kept_done.append(e)

    kept_rows = []
    for r in day_rows:
        paired = done_ts.get((r.get("order_no"), r.get("side")))
        eff = max(r["noted_at"], paired) if paired is not None else r["noted_at"]
        if eff <= cutoff:
            kept_rows.append(r)

    return kept_done, kept_rows


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
            if self._day is not None and self._last_reconcile_result is not None and \
                    not self._last_reconcile_result.get("ok"):
                # 전날이 미해소 상태로 끝났다 — 운영자가 그 사실을 알 수 있게 1줄(보완3 N11). 비우지 않으면
                # 다음 날 첫(trivially ok) 대사가 이 값과 달라 "해소"로 오판해 거짓 [journal_gap_resolved] 를 낸다.
                res = self._last_reconcile_result
                log.warning("[journal_gap_unresolved_at_rollover] day=%s sell_done=%s sell_rows=%s "
                            "buy_done=%s buy_rows=%s unknown_reason_sells=%s", self._day, res["sell_done"],
                            res["sell_rows"], res["buy_done"], res["buy_rows"], res["unknown_reason_sells"])
            self._day = d
            self._done_events, self._day_rows, self._journal_keys = [], [], set()
            self._done_order_sides, self._counted_pairs = set(), set()
            self._last_reconcile_result = None

    async def _fill_division(self, notice):
        """행 단위 예외 격리(`_write_row` 와 같은 규약) — 통보 1건 실패가 같은 회전의 다른 처리를 막지 않는다."""
        try:
            await self.db.fill_order_division(notice["ts"].astimezone(KST).date(), notice["order_no"],
                                               notice["side"], notice["division"])
        except Exception as exc:
            log.warning("[journal_write_error] division order_no=%s side=%s %s: %s", notice.get("order_no"),
                        notice.get("side"), type(exc).__name__, exc)

    async def _write_row(self, row):
        """반환 = 이 회전에 실측 행을 **새로** 넣었거나 승격했는가(보완2 N9 — exit 중복 차단에 쓴다).

        `journal_keys`/`day_rows` 집계(보완2 N1)는 그대로다 — insert 가 False 이고 promote 도 False 면
        (충돌 상대가 이미 실측 행) 그 키는 집계에 센다. 다만 그 경우는 "새로" 쓴 것이 아니므로 fresh=False.
        """
        is_empty = row["source"] in _EMPTY_SOURCES
        try:
            inserted = await self.db.insert_order(row)
            promoted = False
            if not inserted and not is_empty:
                # insert 가 False 라는 것은 그 키의 행이 이미 있다는 뜻 — promote 가 예외 없이 끝나면
                # (True 든 False 든) 그 키에 측정 가능한 행이 있다는 것이 확인된다(보완2 N1).
                promoted = await self.db.promote_order(row)
        except Exception as exc:
            log.warning("[journal_write_error] order_no=%s side=%s %s: %s", row.get("order_no"),
                        row.get("side"), type(exc).__name__, exc)
            return False
        key = (row["order_date"], row["order_no"], row["side"])
        self._journal_keys.add(key)
        if is_empty:
            return False
        pair = (row["order_no"], row["side"])
        if pair not in self._counted_pairs:
            self._counted_pairs.add(pair)
            self._day_rows.append({"side": row["side"], "order_no": row["order_no"], "source": row["source"],
                                   "reason_code": row["reason_code"], "noted_at": row["noted_at"]})
        return inserted or promoted

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
        kept_done, kept_rows = _cutoff_split(self._done_events, self._day_rows, cutoff)
        res = check_identities(kept_done, kept_rows)
        if res != self._last_reconcile_result:
            if not res["ok"]:
                emit_gap(res, log)
            elif self._last_reconcile_result is not None and not self._last_reconcile_result.get("ok"):
                # 어긋났던 항등식이 풀렸다 — 운영자가 해소를 알 수 있게 1줄(보완2 N10).
                log.info("[journal_gap_resolved] sell_done=%s sell_rows=%s buy_done=%s buy_rows=%s "
                         "unknown_reason_sells=%s", res["sell_done"], res["sell_rows"], res["buy_done"],
                         res["buy_rows"], res["unknown_reason_sells"])
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
            if e["kind"] == "order_done":
                pair = (e["order_no"], e["side"])
                if pair in self._done_order_sides:
                    continue
                self._done_order_sides.add(pair)
                self._done_events.append({"kind": "order_done", "side": e["side"], "order_no": e["order_no"],
                                           "ts": e["ts"]})
            elif e["kind"] == "order_notice" and e.get("rctf") == "0" and e.get("division") is not None:
                # 보류 중인 행은 Pairer._finalize 가 채운다 — 이 호출은 그 보류가 끝나 행이 이미 쓰인
                # 뒤에 도착한 통보를 위한 것이다(보완3 N11). DB 쪽 WHERE order_division IS NULL 이
                # 덮어쓰기를 막아 두 경로가 겹쳐도 안전하다.
                await self._fill_division(e)
        self._pairer.feed_events(events)

        result = self._pairer.drain(trade_strategies=await self._trade_strategies(now))
        fresh_sell_orders: set = set()
        for row in result["orders"]:
            fresh = await self._write_row(row)
            if fresh and row["side"] == "SELL":
                fresh_sell_orders.add(row["order_no"])
        for ev in result["stops"]:
            # 커서 저장 실패로 같은 덩어리를 다시 읽으면 같은 매도 주문이 또 한 회전 보류를 거쳐
            # 다시 drain 된다 — 그 매도 행이 이번 회전에 "새로" 쓰이지 않았으면(이미 실측 행이 있음)
            # exit 사건도 다시 넣지 않는다(보완2 N9).
            if ev.get("inputs", {}).get("sell_order_no") not in fresh_sell_orders:
                continue
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
