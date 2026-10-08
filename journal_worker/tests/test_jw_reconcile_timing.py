"""cycle412 보완2 Red — 대사가 로그를 앞질러 실측 행을 빈 행으로 선점한다(직전 판정 N1·N1-b·N2·N3·N5).

직전 판정(10-09) 원문 요지:
- N1(중간) `jw/main.py` `_reconcile`·`_write_row` — 대사가 벽시계 `now − 120초` 와 메모리 `_journal_keys` 를
  기준으로 삼아, 로그를 아직 다 읽지 못한 주문을 먼저 `unmatched` 빈 행으로 넣는다. 로그로 만든 실측 행은
  `ON CONFLICT DO NOTHING` 에 막혀 버려진다. `INSERT 0 0` 도 `_day_rows` 에 더해져 항등식이 ok 가 되고
  경고는 1줄 뒤 사라진다. 장중 2분 넘게 멈췄다 다시 뜰 때·장중 첫 기동 때 난다(재현: 주문 5분 뒤 첫 기동 →
  2/2건 unmatched · 첫 기동 15:45 재생 → 8/8건 unmatched).
- N1-b `_done_events.extend` — 커서 저장 실패 때 같은 덩어리를 다시 읽어 완료 줄을 거듭 센다(저장 실패 3회 →
  주문 2건에 done_events 8·day_rows 8). N1 을 고친 뒤 `INSERT 0 0` 을 빼면 그날 끝까지 거짓 `[journal_gap]`.
- N2(낮음) 항등식이 어긋나면 60초마다 경고(하루 598줄) · N3(낮음) 재시작·첫 기동 직후 거짓 경고 1회.

계약 = `_workspace/red/cycle412/journal_contract.md` 7절. 이 파일의 시험은 전부 `run_forever` 를 가짜 시계로
돌리고, 로그는 시계를 따라 자란다(`jw_testkit.LiveLog` — 문법이 모르는 「심장 박동」 줄이 15초마다 붙는다).

| # | 계약 |
|---|---|
| N1a | 주문 5분 뒤 첫 기동 — 두 주문 모두 실측 행(`log_harvest`) · 그 주문으로 빈 행(`unmatched`·`external`)을 쓰려 하지 않는다 · `[journal_gap]` 0 |
| N1b | 첫 기동 15:45 — 그날 로그 재생 8건 전부 실측 행 · 빈 행 시도 0 · `[journal_gap]` 0 |
| N1c | 6분 정지 뒤 재시작(새 Worker, 같은 DB 커서) — 정지 중 주문 2건 실측 행 · 빈 행 시도 0 · `[journal_gap]` 0 |
| N1d | 따라잡기(로그 ≈ 10MB, 읽기 창 여럿) — 한 회전에 읽는 양 ≤ `MAX_READ_BYTES`(= 4MiB, N5) · 4건 실측 행 · 빈 행 시도 0 · `[journal_gap]` 0 |
| N1e | 승격 — 빈 행(`unmatched`·`external`)이 먼저 있어도 나중에 온 로그 실측 행이 그 행을 실측으로 바꾼다(빈 칸만 채움 · source = 로그 행 것 · 전략 `"unknown"` 은 빈 칸으로 본다) · 항등식에 센다 |
| N1f | `INSERT 0 0` 은 그 자체로 쓴 행이 아니다 — 빈 행 승격이 실패하면 그 주문은 행으로 세지 않는다(`[journal_gap]`) |
| N1g | 커서 저장 실패 3회(같은 덩어리 재읽기) — 완료 줄·행을 (주문번호, side) 고유값으로 센다: 깨진 항등식의 경고 값이 `sell_done=1 sell_rows=1 buy_done=1 buy_rows=0` |
| N1h | 커서 저장 실패 3회 + 정상 주문 — `[journal_gap]` 0 (재읽기의 `INSERT 0 0` 이 이미 센 키를 지우지 않는다) |
| N1i | 커서가 뒤로 간 채 재시작(이미 쓴 로그를 다시 읽음) — 이미 실측 행이 있는 키는 행으로 센다 · `[journal_gap]` 0 · 빈 행 시도 0 |
| N2 | 같은 값으로 어긋난 항등식은 경고 1줄 — 값이 바뀌면 그때 1줄 더(15분 동안 정확히 2줄) |

보완2(직전 판정 N10, 계약 7절 뒤 추가) — 완료 줄과 행(접수 등)이 1초 벌어진 주문에서, 대사 기준선
(`W − 120초`)이 그 사이에 걸리면 한쪽만 포함돼 거짓 `[journal_gap]` 이 난다. 짝(주문번호, side)의
두 시각 중 늦은 쪽을 기준으로 함께 자른다. gap 이 풀리면 `[journal_gap_resolved]` INFO 1줄.

| # | 계약 |
|---|---|
| N10a | `_cutoff_split` — 완료·행이 1초 벌어진 짝을 경계 전후 여러 위상(phase)에서 전수 — 항상 둘 다 포함되거나 둘 다 빠진다(거짓 gap 0) |
| N10b | `_reconcile` 와이어링 — 경계가 정확히 그 사이에 걸리는 실제 호출에서도 `[journal_gap]` 0 |
| N10c | 어긋난 항등식이 풀리면 `[journal_gap_resolved]` INFO 1줄(그 전엔 없음, 반복 없음) |

보완3(직전 판정 N11, 머지·배포 가능 뒤 마지막 손질) — `_roll_day` 가 `_last_reconcile_result` 를 날짜 경계에서
비우지 않아, 미해소 gap 을 안고 날이 바뀌면 다음 날 첫 대사(값은 trivially ok)가 전날의 어긋난 결과와 달라
"해소"로 오판해 거짓 `[journal_gap_resolved]` INFO 를 남긴다.

| # | 계약 |
|---|---|
| N11a | `_roll_day` — 날짜가 바뀌는 순간 직전 `_last_reconcile_result` 가 어긋난 채였으면 `[journal_gap_unresolved_at_rollover]` WARNING 1줄(그 날의 마지막 값) 뒤 `_last_reconcile_result` 를 None 으로 비운다. 전날이 ok 였으면 WARNING 없이 비우기만 |
| N11b | `_reconcile` 와이어링 — 미해소 gap 을 안고 날이 바뀌면, 다음 날 첫 대사가 trivially ok 여도 `[journal_gap_resolved]` 가 나지 않는다(전날 값과 비교하지 않는다) |
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta, timezone

import httpx
import pytest

from jw_testkit import FakeJournalDB, LiveLog, heartbeats, jw, kst, log_line

pytestmark = pytest.mark.unit

UTC = timezone.utc
OE = "src.engine.order_engine"
DAY = (2026, 10, 13)
EMPTY = ("unmatched", "external")


def T(h, m, s=0):
    return kst(*DAY, h, m, s)


def _ymd_hms(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def done(at, side, ticker, qty, no):
    return log_line(_ymd_hms(at), "INFO", "src.api.order", f"{side} 주문 완료: {ticker} {qty}주 @ 0 (주문번호: {no})")


def sell_accept(at, signal, no, ticker, qty=3, sid="kojiro"):
    return log_line(_ymd_hms(at), "INFO", OE,
                    f"{signal} 매도 주문 접수: 종목({ticker}) {qty}주 (주문번호: {no}, 전략: {sid})")


def buy_accept(at, no, ticker, qty=3, price=70000, sid="kojiro"):
    return log_line(_ymd_hms(at), "INFO", OE,
                    f"매수 주문 접수: 종목({ticker}) {qty}주 @ {price} (주문번호: {no}, 전략: {sid})")


def sell_order(at, no, ticker, signal="FORCE_CLEAR"):
    return [done(at, "SELL", ticker, 3, no), sell_accept(at, signal, no, ticker)]


def buy_order(at, no, ticker):
    return [done(at, "BUY", ticker, 3, no), buy_accept(at, no, ticker)]


def th(no, side, at, ticker, *, status="COMPLETED", strategy="kojiro"):
    """trade_history 행 — asyncpg 처럼 UTC aware."""
    return {"order_no": no, "trade_type": side, "strategy": strategy, "ticker": ticker,
            "timestamp": at.astimezone(UTC), "status": status, "price": 70000, "order_price": None}


def _status():
    return {"success": True, "message": "", "data": {
        "running": True, "phase": "main_trading", "positions_detail": {},
        "strategies": {"kojiro": {"enabled": True, "params": {}, "buy_signals": [], "position_tickers": []}}}}


def _ok(req):
    if req.url.raw_path.decode().startswith("/api/trading/status"):
        return httpx.Response(200, json=_status())
    return httpx.Response(200, json={"success": True, "message": "", "data": {
        "running": True, "as_of": "2026-10-13T10:00:00+09:00", "items": []}})


class Rig:
    """가짜 시계 + 시계를 따라 자라는 로그 + 같은 DB. ``run()`` 할 때마다 새 Worker(= 컨테이너 재시작)."""

    def __init__(self, tmp_path, db, lines, *, boot_at):
        self.tmp_path = tmp_path
        self.db = db
        self.t = boot_at
        self.log = LiveLog(tmp_path, lines)
        self.log.advance(self.t)

    def pause(self, seconds):
        """워커가 멈춘 동안에도 운영 로그는 계속 쌓인다."""
        self.t += timedelta(seconds=seconds)
        self.log.advance(self.t)

    def run(self, rotations):
        client = jw("http").build_client(base_url="http://backend:8000", reporter_key="rk",
                                         transport=httpx.MockTransport(_ok))
        w = jw("main").Worker(client=client, db=self.db, log_dir=self.tmp_path, now=lambda: self.t)
        n = {"sleeps": 0}

        async def sleep(d):
            n["sleeps"] += 1
            self.t += timedelta(seconds=d)
            self.log.advance(self.t)

        async def go():
            async with client:
                await jw("main").run_forever(w.rotate, sleep=sleep, stop=lambda: n["sleeps"] >= rotations)

        asyncio.run(go())
        return w


def _gaps(caplog):
    return [r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING and (r.name == "jw" or r.name.startswith("jw."))
            and r.getMessage().startswith("[journal_gap] ")]


def _warnings(caplog, prefix):
    return [r.getMessage() for r in caplog.records
            if r.levelno == logging.WARNING and (r.name == "jw" or r.name.startswith("jw."))
            and r.getMessage().startswith(prefix)]


def _empty_attempts(db, order_nos):
    """대사가 이 주문들로 빈 행(unmatched·external)을 쓰려 한 시도."""
    return [a for a in db.attempts if a[0] == "insert_order" and a[1] in order_nos and a[3] in EMPTY]


def _sources(db, order_nos):
    return {no: [r["source"] for r in db.rows(order_no=no)] for no in order_nos}


# ── N1a 주문 5분 뒤 첫 기동 ─────────────────────────────────────────────────────

def test_n1a_first_boot_five_minutes_after_orders_keeps_measured_rows(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    a, b = "0000300100", "0000200100"
    lines = (sell_order(T(10, 0, 8), a, "005930") + buy_order(T(10, 0, 9), b, "000660")
             + heartbeats(T(9, 55), T(10, 30)))
    db = FakeJournalDB(trade_rows=[th(a, "SELL", T(10, 0, 8), "005930"), th(b, "BUY", T(10, 0, 9), "000660")])
    rig = Rig(tmp_path, db, lines, boot_at=T(10, 5, 10))
    rig.run(20)
    assert _sources(db, (a, b)) == {a: ["log_harvest"], b: ["log_harvest"]}, (
        "로그를 아직 다 읽지 못한 주문을 대사가 빈 행으로 먼저 넣어 실측 행이 버려졌다")
    assert _empty_attempts(db, (a, b)) == [], "대사가 로그를 앞질렀다 — 기준은 벽시계가 아니라 행까지 쓴 로그 줄의 시각"
    assert _gaps(caplog) == [], "첫 기동 직후 거짓 [journal_gap](N3)"


# ── N1b 첫 기동 15:45 — 그날 로그 재생 ──────────────────────────────────────────

DAY_ORDERS = [  # (시각, 주문번호, side, 종목, 매도 신호)
    (T(9, 3, 11), "0000100100", "BUY", "000660", None),
    (T(9, 41, 2), "0000100200", "BUY", "035720", None),
    (T(10, 12, 40), "0000100300", "SELL", "005930", "STOP_LOSS"),
    (T(11, 30, 5), "0000100400", "BUY", "051910", None),
    (T(13, 2, 59), "0000100500", "SELL", "000660", "TRAILING_STOP"),
    (T(14, 15, 0), "0000100600", "BUY", "068270", None),
    (T(15, 0, 30), "0000100700", "SELL", "035720", "STOP_LOSS"),
    (T(15, 20, 0), "0000100800", "SELL", "051910", "FORCE_CLEAR"),
]


def _day_lines_and_trades(orders):
    lines, trades = [], []
    for at, no, side, tk, sig in orders:
        lines += buy_order(at, no, tk) if side == "BUY" else sell_order(at, no, tk, sig)
        trades.append(th(no, side, at, tk))
    return lines, trades


def test_n1b_first_boot_at_1545_replays_the_day_into_measured_rows(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    lines, trades = _day_lines_and_trades(DAY_ORDERS)
    nos = tuple(o[1] for o in DAY_ORDERS)
    db = FakeJournalDB(trade_rows=trades)
    rig = Rig(tmp_path, db, lines + heartbeats(T(8, 59), T(16, 10)), boot_at=T(15, 45))
    rig.run(12)
    got = _sources(db, nos)
    assert got == {no: ["log_harvest"] for no in nos}, f"재생 주문이 빈 행이 됐다: {got}"
    assert _empty_attempts(db, nos) == []
    assert _gaps(caplog) == []


# ── N1c 6분 정지 뒤 재시작 ─────────────────────────────────────────────────────

def test_n1c_restart_after_six_minute_stop_keeps_measured_rows(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    a, b = "0000300100", "0000200100"
    lines = (sell_order(T(10, 1, 8), a, "005930") + buy_order(T(10, 2, 9), b, "000660")
             + heartbeats(T(9, 55), T(10, 30)))
    db = FakeJournalDB(trade_rows=[th(a, "SELL", T(10, 1, 8), "005930"), th(b, "BUY", T(10, 2, 9), "000660")])
    rig = Rig(tmp_path, db, lines, boot_at=T(9, 58))
    rig.run(8)                    # 09:58:00 → 10:00:00, 주문 전
    rig.pause(6 * 60)             # 10:00 ~ 10:06 정지 — 이 사이 두 주문
    rig.run(20)                   # 새 Worker(재시작), 같은 DB 커서
    assert _sources(db, (a, b)) == {a: ["log_harvest"], b: ["log_harvest"]}
    assert _empty_attempts(db, (a, b)) == []
    assert _gaps(caplog) == [], "재시작 직후 거짓 [journal_gap](N3)"


# ── N1d 따라잡기 — 읽기 창 여럿 · 한 회전 읽기 상한(N5) ──────────────────────────

CATCHUP_ORDERS = [
    (T(9, 30, 1), "0000110100", "BUY", "000660", None),
    (T(11, 0, 2), "0000110200", "SELL", "005930", "STOP_LOSS"),
    (T(12, 30, 3), "0000110300", "BUY", "035720", None),
    (T(14, 50, 4), "0000110400", "SELL", "000660", "FORCE_CLEAR"),
]


def test_n1d_catch_up_over_several_read_windows(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    lines, trades = _day_lines_and_trades(CATCHUP_ORDERS)
    nos = tuple(o[1] for o in CATCHUP_ORDERS)
    backlog = heartbeats(T(9, 0), T(15, 45), every_s=3, pad=1200)     # ≈ 10MB — 읽기 창 4MiB 로 3번
    live = heartbeats(T(15, 45, 15), T(16, 10))
    db = FakeJournalDB(trade_rows=trades)
    rig = Rig(tmp_path, db, lines + backlog + live, boot_at=T(15, 45))
    size = rig.log.path.stat().st_size
    assert size > 9 * 1024 * 1024, size
    rig.run(12)

    got = _sources(db, nos)
    assert got == {no: ["log_harvest"] for no in nos}, f"따라잡는 동안 대사가 빈 행을 먼저 넣었다: {got}"
    assert _empty_attempts(db, nos) == []
    assert _gaps(caplog) == [], "따라잡는 동안 거짓 [journal_gap]"

    cap = jw("config").MAX_READ_BYTES
    assert cap == 4 * 1024 * 1024, f"읽기 창 = 4MiB(N5) — 지금 {cap}"
    offsets = [c[1]["byte_offset"] for c in db.calls if c[0] == "save_cursor"]
    steps = [b - a for a, b in zip([0] + offsets, offsets)]
    assert offsets and max(steps) <= cap, f"한 회전에 읽기 창보다 많이 읽었다(따라잡기 메모리): {steps}"
    assert offsets[-1] >= size - 64 * 1024, "따라잡기가 끝나지 않았다"


# ── N1e 승격 — 먼저 들어간 빈 행을 로그 실측 행으로 바꾼다 ────────────────────────

def test_n1e_measured_row_promotes_an_earlier_empty_row(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    a, b = "0000300100", "0000200100"
    d = T(10, 0).date()
    db = FakeJournalDB(trade_rows=[th(a, "SELL", T(10, 0, 8), "005930"), th(b, "BUY", T(10, 0, 9), "000660")])
    db.seed({"order_date": d, "order_no": a, "side": "SELL", "strategy": "kojiro", "ticker": "005930",
             "source": "unmatched", "noted_at": T(10, 0, 8)})
    db.seed({"order_date": d, "order_no": b, "side": "BUY", "strategy": "unknown", "ticker": "000660",
             "source": "external", "order_price": 70100, "noted_at": T(10, 0, 9)})
    lines = sell_order(T(10, 0, 8), a, "005930") + buy_order(T(10, 0, 9), b, "000660") + \
        heartbeats(T(9, 55), T(10, 30))
    rig = Rig(tmp_path, db, lines, boot_at=T(10, 0, 10))
    rig.run(16)

    (ra,) = db.rows(order_no=a)
    assert ra["source"] == "log_harvest", f"빈 행이 실측으로 승격되지 않았다: {ra['source']}"
    assert ra["reason_code"] == "FORCE_CLEAR" and isinstance(ra["signal"], dict)
    assert ra["signal"].get("path") == "accept"
    (rb,) = db.rows(order_no=b)
    assert (rb["source"], rb["reason_code"], rb["strategy"]) == ("log_harvest", "ENTRY", "kojiro"), rb
    assert rb["order_price"] == 70100, "승격은 빈 칸만 채운다 — 이미 있는 값은 그대로"
    assert _gaps(caplog) == [], "승격한 행은 항등식에 센다"


# ── N1f INSERT 0 0 은 그 자체로 쓴 행이 아니다 ─────────────────────────────────

def test_n1f_conflict_without_promotion_is_not_counted(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    a = "0000300100"
    db = FakeJournalDB(trade_rows=[th(a, "SELL", T(10, 0, 8), "005930")], fail_promote={a})
    db.seed({"order_date": T(10, 0).date(), "order_no": a, "side": "SELL", "strategy": "kojiro",
             "ticker": "005930", "source": "unmatched", "noted_at": T(10, 0, 8)})
    rig = Rig(tmp_path, db, sell_order(T(10, 0, 8), a, "005930") + heartbeats(T(9, 55), T(10, 30)),
              boot_at=T(10, 0, 10))
    rig.run(16)
    assert [r["source"] for r in db.rows(order_no=a)] == ["unmatched"]
    gaps = _gaps(caplog)
    assert gaps, "실측 행이 저장되지 않았는데(INSERT 0 0 + 승격 실패) 행으로 셌다 — [journal_gap] 이 없다"
    assert "sell_done=1 sell_rows=0" in gaps[-1], gaps[-1]


# ── N1g·N1h 커서 저장 실패 → 같은 덩어리 재읽기 ─────────────────────────────────

def test_n1g_reread_after_cursor_save_failures_counts_unique_orders(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    a, b = "0000300100", "0000200100"
    lines = (sell_order(T(10, 0, 8), a, "005930")
             + [done(T(10, 0, 9), "BUY", "000660", 3, b)]          # 접수 줄 없는 매수 = 항등식이 정말 깨진다
             + heartbeats(T(9, 55), T(10, 40)))
    db = FakeJournalDB(trade_rows=[th(a, "SELL", T(10, 0, 8), "005930"), th(b, "BUY", T(10, 0, 9), "000660")],
                       fail_saves=3)
    rig = Rig(tmp_path, db, lines, boot_at=T(10, 0, 10))
    rig.run(30)
    gaps = _gaps(caplog)
    assert gaps, "항등식이 깨졌는데 [journal_gap] 이 없다"
    assert "sell_done=1 sell_rows=1 buy_done=1 buy_rows=0 unknown_reason_sells=0" in gaps[-1], (
        f"재읽기로 완료 줄·행을 거듭 셌다 — (주문번호, side) 고유값으로 센다: {gaps[-1]}")


def test_n1h_reread_after_cursor_save_failures_gives_no_false_gap(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    a, b = "0000300100", "0000200100"
    lines = sell_order(T(10, 0, 8), a, "005930") + buy_order(T(10, 0, 9), b, "000660") + \
        heartbeats(T(9, 55), T(10, 40))
    db = FakeJournalDB(trade_rows=[th(a, "SELL", T(10, 0, 8), "005930"), th(b, "BUY", T(10, 0, 9), "000660")],
                       fail_saves=3)
    rig = Rig(tmp_path, db, lines, boot_at=T(10, 0, 10))
    rig.run(30)
    assert _sources(db, (a, b)) == {a: ["log_harvest"], b: ["log_harvest"]}
    assert _gaps(caplog) == [], "재읽기의 INSERT 0 0 때문에 거짓 [journal_gap]"


# ── N1i 커서가 뒤로 간 채 재시작 ───────────────────────────────────────────────

def test_n1i_restart_with_stale_cursor_counts_existing_measured_rows(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    a, b = "0000300100", "0000200100"
    lines = sell_order(T(10, 0, 8), a, "005930") + buy_order(T(10, 0, 9), b, "000660") + \
        heartbeats(T(9, 55), T(10, 40))
    db = FakeJournalDB(trade_rows=[th(a, "SELL", T(10, 0, 8), "005930"), th(b, "BUY", T(10, 0, 9), "000660")])
    rig = Rig(tmp_path, db, lines, boot_at=T(10, 0, 10))
    rig.run(16)
    assert _sources(db, (a, b)) == {a: ["log_harvest"], b: ["log_harvest"]}
    db.cursor = {**db.cursor, "byte_offset": 0}      # 마지막 커서 저장이 실패한 채 멈췄다
    rig.pause(5 * 60)
    rig.run(16)                                      # 새 Worker 가 이미 쓴 로그를 다시 읽는다
    assert _sources(db, (a, b)) == {a: ["log_harvest"], b: ["log_harvest"]}
    assert _empty_attempts(db, (a, b)) == []
    assert _gaps(caplog) == [], "이미 실측 행이 있는 주문을 다시 읽었을 뿐인데 [journal_gap]"


# ── N2 같은 값의 어긋남은 1줄 ──────────────────────────────────────────────────

def test_n2_gap_is_logged_once_per_distinct_result(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    a, b, c = "0000300100", "0000200100", "0000300200"
    lines = (sell_order(T(10, 0, 8), a, "005930")
             + [done(T(10, 0, 9), "BUY", "000660", 3, b),              # 접수 줄 없음 — 10:00 부터 어긋남
                done(T(10, 8, 0), "SELL", "035720", 3, c)]             # 접수 줄 없음 — 10:08 에 값이 바뀜
             + heartbeats(T(9, 55), T(10, 30)))
    db = FakeJournalDB(trade_rows=[th(a, "SELL", T(10, 0, 8), "005930"), th(b, "BUY", T(10, 0, 9), "000660"),
                                   th(c, "SELL", T(10, 8, 0), "035720")])
    rig = Rig(tmp_path, db, lines, boot_at=T(10, 0, 10))
    rig.run(60)                                       # 10:00:10 → 10:15:10
    gaps = _gaps(caplog)
    assert len(gaps) == 2, f"값이 바뀔 때만 경고한다 — 15분 동안 {len(gaps)}줄: {gaps}"
    assert "sell_done=1 sell_rows=1 buy_done=1 buy_rows=0" in gaps[0], gaps
    assert "sell_done=2 sell_rows=1 buy_done=1 buy_rows=0" in gaps[1], gaps


# ── N10 완료 줄·행이 1초 벌어진 주문 — 대사 경계가 그 사이에 걸리면 거짓 gap ──────────────

def _infos(caplog, prefix):
    return [r.getMessage() for r in caplog.records
            if r.levelno == logging.INFO and (r.name == "jw" or r.name.startswith("jw."))
            and r.getMessage().startswith(prefix)]


def test_n10a_cutoff_split_never_splits_a_paired_order_across_phases():
    """매도 1건의 완료(T+1)·행(T) 이 1초 벌어진다 — 경계를 전후로 쓸며도 둘은 항상 함께 포함되거나 빠진다."""
    m = jw("main")
    T = kst(*DAY, 10, 0, 8)
    done_evt = {"kind": "order_done", "side": "SELL", "order_no": "0000300100", "ts": T + timedelta(seconds=1)}
    row = {"side": "SELL", "order_no": "0000300100", "source": "log_harvest", "reason_code": "STOP_LOSS",
           "noted_at": T}
    for offset in range(-3, 4):
        cutoff = T + timedelta(seconds=offset)
        kept_done, kept_rows = m._cutoff_split([done_evt], [row], cutoff)
        assert (len(kept_done) == 1) == (len(kept_rows) == 1), (
            f"offset={offset}s(cutoff={cutoff}): done={len(kept_done)} rows={len(kept_rows)} — "
            "짝이 경계에서 쪼개져 거짓 [journal_gap] 이 난다")


def test_n10a_cutoff_split_keeps_unpaired_events_on_their_own_timestamp():
    """짝이 없는 완료 줄(접수 줄 없음)·행은 그대로 자기 시각 기준 — 기존 동작을 바꾸지 않는다."""
    m = jw("main")
    T = kst(*DAY, 10, 0, 8)
    orphan_done = {"kind": "order_done", "side": "BUY", "order_no": "0000200100", "ts": T}
    cutoff = T  # ts <= cutoff
    kept_done, kept_rows = m._cutoff_split([orphan_done], [], cutoff)
    assert len(kept_done) == 1 and kept_rows == []
    cutoff_before = T - timedelta(seconds=1)  # ts > cutoff
    kept_done2, _ = m._cutoff_split([orphan_done], [], cutoff_before)
    assert kept_done2 == []


def test_n10b_reconcile_wiring_gives_no_false_gap_when_boundary_falls_between_done_and_row(tmp_path, caplog):
    """`_reconcile` 실제 경로 — 완료(10:00:09)·행(10:00:08) 1초 차, W 를 그 사이로 맞춰도 [journal_gap] 0."""
    caplog.set_level(logging.INFO)
    db = FakeJournalDB()
    client = jw("http").build_client(base_url="http://backend:8000", reporter_key="rk",
                                     transport=httpx.MockTransport(_ok))
    w = jw("main").Worker(client=client, db=db, log_dir=tmp_path)
    w._pairer = jw("pairing").Pairer()
    w._booted = True
    w._day = kst(*DAY, 0, 0).date()

    accept_ts = kst(*DAY, 10, 0, 8)
    done_ts = accept_ts + timedelta(seconds=1)
    w._done_events = [{"kind": "order_done", "side": "SELL", "order_no": "0000300100", "ts": done_ts}]
    w._day_rows = [{"side": "SELL", "order_no": "0000300100", "source": "log_harvest",
                    "reason_code": "STOP_LOSS", "noted_at": accept_ts}]
    # W − RECONCILE_MIN_AGE_SECONDS == accept_ts(행의 시각) — done_ts 는 그 1초 뒤라 경계 바로 밖.
    # 짝짓기 없이 독립적으로 자르면 행은 포함되고 완료는 빠져 거짓 gap 이 난다.
    reconcile_cfg = jw("config")
    W = accept_ts + timedelta(seconds=reconcile_cfg.RECONCILE_MIN_AGE_SECONDS)

    async def go():
        async with client:
            await w._reconcile(W, W, catching_up=False)

    asyncio.run(go())
    assert _gaps(caplog) == [], "완료 줄·행이 1초 벌어진 주문이 대사 경계에서 쪼개져 거짓 [journal_gap]"


def test_n10c_gap_resolution_logs_info_once(tmp_path, caplog):
    """어긋난 항등식이 다음 회차에 풀리면 WARNING 1줄 뒤 INFO [journal_gap_resolved] 1줄."""
    caplog.set_level(logging.INFO)
    db = FakeJournalDB()
    client = jw("http").build_client(base_url="http://backend:8000", reporter_key="rk",
                                     transport=httpx.MockTransport(_ok))
    w = jw("main").Worker(client=client, db=db, log_dir=tmp_path)
    w._pairer = jw("pairing").Pairer()
    w._booted = True
    w._day = kst(*DAY, 0, 0).date()
    age = jw("config").RECONCILE_MIN_AGE_SECONDS

    async def go():
        async with client:
            # 1회차 — 완료 줄만 있고 행이 없다(접수 줄 없는 매도) → 항등식이 깨진다.
            T1 = kst(*DAY, 10, 0, 8)
            w._done_events = [{"kind": "order_done", "side": "SELL", "order_no": "0000300100", "ts": T1}]
            w._day_rows = []
            W1 = T1 + timedelta(seconds=age)
            await w._reconcile(W1, W1, catching_up=False)
            # 2회차(60초 뒤) — 행이 들어와 항등식이 풀린다.
            w._day_rows = [{"side": "SELL", "order_no": "0000300100", "source": "log_harvest",
                            "reason_code": "FORCE_CLEAR", "noted_at": T1}]
            W2 = W1 + timedelta(seconds=65)
            await w._reconcile(W2, W2, catching_up=False)

    asyncio.run(go())
    warn = _gaps(caplog)
    resolved = _infos(caplog, "[journal_gap_resolved]")
    assert len(warn) == 1, warn
    assert len(resolved) == 1, resolved
    assert "sell_done=1 sell_rows=1" in resolved[0], resolved


# ── N11 날짜 경계 — 미해소 gap 을 안고 날이 바뀌면 거짓 [journal_gap_resolved] ────────────

def test_n11a_roll_day_warns_and_clears_unresolved_result(tmp_path, caplog):
    """`_roll_day` 가 전날 미해소 결과로 경고 1줄을 남긴 뒤 비운다 — 다음 날이 그 값과 비교되지 않는다."""
    caplog.set_level(logging.WARNING)
    w = jw("main").Worker(client=None, db=None, log_dir=tmp_path)
    w._day = kst(*DAY, 0, 0).date()
    w._last_reconcile_result = {"sell_done": 2, "sell_rows": 1, "buy_done": 1, "buy_rows": 1,
                                "unknown_reason_sells": 0, "ok": False}
    w._roll_day(kst(2026, 10, 14, 7, 45, 0))

    assert w._last_reconcile_result is None, "날이 바뀐 뒤에도 전날 결과가 남아 있다"
    warn = _warnings(caplog, "[journal_gap_unresolved_at_rollover]")
    assert len(warn) == 1, warn
    assert "sell_done=2 sell_rows=1 buy_done=1 buy_rows=1 unknown_reason_sells=0" in warn[0], warn[0]


def test_n11a_roll_day_is_quiet_when_prior_day_was_ok(tmp_path, caplog):
    """전날 항등식이 이미 ok 였으면 비우기만 하고 경고는 없다."""
    caplog.set_level(logging.WARNING)
    w = jw("main").Worker(client=None, db=None, log_dir=tmp_path)
    w._day = kst(*DAY, 0, 0).date()
    w._last_reconcile_result = {"sell_done": 1, "sell_rows": 1, "buy_done": 0, "buy_rows": 0,
                                "unknown_reason_sells": 0, "ok": True}
    w._roll_day(kst(2026, 10, 14, 7, 45, 0))

    assert w._last_reconcile_result is None
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_n11b_reconcile_does_not_falsely_resolve_across_day_rollover(tmp_path, caplog):
    """미해소 gap 을 안고 날이 바뀌면, 다음 날 첫(trivially ok) 대사에서 [journal_gap_resolved] 가 나면 안 된다."""
    caplog.set_level(logging.INFO)
    db = FakeJournalDB()
    client = jw("http").build_client(base_url="http://backend:8000", reporter_key="rk",
                                     transport=httpx.MockTransport(_ok))
    w = jw("main").Worker(client=client, db=db, log_dir=tmp_path)
    w._pairer = jw("pairing").Pairer()
    w._booted = True
    age = jw("config").RECONCILE_MIN_AGE_SECONDS

    async def go():
        async with client:
            # 1일차 — 접수 줄 없는 매도 완료만 있어 항등식이 깨진 채 하루가 끝난다(해소 안 됨).
            w._day = kst(*DAY, 0, 0).date()
            T1 = kst(*DAY, 10, 0, 8)
            w._done_events = [{"kind": "order_done", "side": "SELL", "order_no": "0000300100", "ts": T1}]
            w._day_rows = []
            W1 = T1 + timedelta(seconds=age)
            await w._reconcile(W1, W1, catching_up=False)
            # 날이 바뀐다 — rotate() 맨 앞의 _roll_day 를 그대로 흉내낸다.
            next_day = T1 + timedelta(days=1, hours=14)
            w._roll_day(next_day)
            # 2일차 첫 대사 — 오늘 안에는 아무 사건도 없다(trivially ok). 전날 값과 비교되면 "해소"로 오판한다.
            W2 = next_day + timedelta(seconds=age + 60)
            await w._reconcile(W2, W2, catching_up=False)

    asyncio.run(go())
    warn = _gaps(caplog)
    resolved = _infos(caplog, "[journal_gap_resolved]")
    assert len(warn) == 1, warn
    assert resolved == [], f"날이 바뀐 뒤 거짓 [journal_gap_resolved] — 전날 미해소 gap 과 비교해 해소로 오판했다: {resolved}"
