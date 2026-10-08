"""cycle412 Red — 워커 루프(설계 관찰자안 3절 「한 회전」 · 5절 ③ 호출 빈도 상한).

백엔드에는 빈도 제한이 없고 워커는 nginx 를 거치지 않는다. 예외 경로에서 sleep 을 빠뜨리면
uvicorn 단일 워커의 루프를 점유해 틱·체결통보 처리가 밀린다.

| # | 계약 |
|---|---|
| L1 | sleep 은 `finally` 에 — 예외가 나도 매 회전 sleep 한다(AST + 행위) |
| L2 | 주기: active 15초 · idle 300초 · 실패(예외·degraded) 지수 백오프 30→60→120→240→300 상한, 성공하면 처음부터 |
| L3 | `BaseException`(취소)은 삼키지 않는다 |
| L4 | 한 회전 = G0 → G1 → 로그 → 짝짓기 → DB(행 쓰기 뒤 커서) |
| L5 | idle(엔진 정지·`phase=idle`) → G1·로그·DB 0 |
| L6 | G0/G1 실패 → 스냅샷 없이 로그 수확은 계속(`degraded`) |
| L7 | 커서는 행이 DB 에 다 쓰인 청크 끝까지만 전진한다(한 회전 보류 중인 청크는 다시 읽게 남긴다) |

보완2(직전 판정 N9, 계약 7절 뒤 추가) — 커서 저장이 거듭 실패하면 같은 덩어리를 다시 읽어, 같은 매도
주문의 exit 사건(`trade_journal_stops`)이 중복 기록된다. 그 회전에 매도 주문 행을 **새로** 쓰지(승격
포함) 않았으면 exit 도 쓰지 않는다.

| # | 계약 |
|---|---|
| N9 | 커서 저장 실패 3회(같은 덩어리 재읽기) — 매도 1건 → exit 사건 1행(중복 0) |

보완3(직전 판정 N11, 머지·배포 가능 뒤 마지막 손질) — `JournalDB.fill_order_division` 을 부르는 곳이 jw/ 안에
0곳이라, 행을 쓴 뒤에 온 접수 통보(`[order_notice]`)의 주문구분이 NULL 로 남는다.

| # | 계약 |
|---|---|
| N11 | 회전마다 읽은 줄 중 `rctf=="0"` 인 `[order_notice]` 는 — 보류 중인 행이든 이미 쓰인 행이든 — `fill_order_division(order_date, order_no, side, division)` 으로 연결한다(빈 칸만 채우는 UPDATE, 덮어쓰기 금지는 DB 쪽 WHERE 가 지킨다) |
"""
from __future__ import annotations

import ast
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from jw_testkit import FakeJournalDB, jw, jw_sources, log_line

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

G0 = "/api/trading/status?include=system,holdings,strategies"
G1 = "/api/balance/exit-lines"


# ── L1·L2·L3 run_forever ─────────────────────────────────────────────────────

def _drive(statuses, *, stop_after=None):
    sleeps: list[float] = []
    it = iter(statuses)

    async def rotate():
        s = next(it)
        if isinstance(s, BaseException):
            raise s
        return s

    async def sleep(d):
        sleeps.append(d)

    n = stop_after if stop_after is not None else len(statuses)
    asyncio.run(jw("main").run_forever(rotate, sleep=sleep, stop=lambda: len(sleeps) >= n))
    return sleeps


def test_l1_sleep_lives_in_finally():
    srcs = jw_sources()
    assert "jw/main.py" in srcs, "jw/main.py 가 없다"
    tree = ast.parse(srcs["jw/main.py"])
    fn = next((n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_forever"),
              None)
    assert fn is not None, "run_forever 가 없다"
    ok = False
    for node in ast.walk(fn):
        if isinstance(node, ast.Try) and node.finalbody:
            for sub in node.finalbody:
                for x in ast.walk(sub):
                    if isinstance(x, ast.Await) and isinstance(x.value, ast.Call):
                        f = x.value.func
                        name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
                        ok = ok or name == "sleep"
    assert ok, "sleep 을 finally 안에서 await 해야 한다(예외 경로에서도 쉰다)"


def test_l1b_exception_path_still_sleeps():
    sleeps = _drive([RuntimeError("x")] * 3)
    assert len(sleeps) == 3 and all(d > 0 for d in sleeps)


def test_l2_delays_by_outcome():
    sleeps = _drive(["active", RuntimeError("a"), RuntimeError("b"), "degraded", "idle", "active"])
    assert sleeps == [15, 30, 60, 120, 300, 15]


def test_l2b_backoff_caps_at_five_minutes():
    sleeps = _drive([RuntimeError("x")] * 7)
    assert sleeps == [30, 60, 120, 240, 300, 300, 300]
    m = jw("main")
    assert [m.backoff_delay(n) for n in (1, 2, 3, 4, 5, 9)] == [30, 60, 120, 240, 300, 300]
    cfg = jw("config")
    assert (cfg.CYCLE_SECONDS, cfg.IDLE_CYCLE_SECONDS, cfg.BACKOFF_MAX_SECONDS) == (15, 300, 300)


def test_l3_cancellation_is_not_swallowed():
    with pytest.raises(asyncio.CancelledError):
        _drive(["active", asyncio.CancelledError()], stop_after=10)


# ── L4~L7 Worker.rotate ──────────────────────────────────────────────────────

class FakeDB:
    def __init__(self, cursor=None):
        self.calls: list[tuple] = []
        self._cursor = cursor

    async def insert_order(self, row):
        self.calls.append(("insert_order", row["order_no"]))
        return True                        # 보완2 N1 — 새로 넣었으면 True

    async def promote_order(self, row):    # 보완2 N1 — 빈 행 승격(이 가짜 DB 에는 빈 행이 없다)
        self.calls.append(("promote_order", row["order_no"]))
        return False

    async def fill_order_division(self, *a):
        self.calls.append(("fill_order_division",) + tuple(a))

    async def insert_stop(self, ev):
        self.calls.append(("insert_stop", ev["event"]))

    async def load_cursor(self, name="main"):
        self.calls.append(("load_cursor",))
        return self._cursor

    async def save_cursor(self, cursor, name="main"):
        self.calls.append(("save_cursor", dict(cursor)))
        self._cursor = dict(cursor)

    async def last_stop_rows(self):
        self.calls.append(("last_stop_rows",))
        return {}

    async def trades_since(self, since):
        self.calls.append(("trades_since",))
        return []

    def writes(self):
        return [c for c in self.calls if c[0] in ("insert_order", "fill_order_division", "insert_stop",
                                                    "save_cursor")]


def _status(running=True, phase="main_trading"):
    return {"success": True, "message": "", "data": {
        "running": running, "phase": phase, "positions_detail": {},
        "strategies": {"kojiro": {"enabled": True, "params": {}, "buy_signals": [], "position_tickers": []}}}}


def _lines():
    return [log_line("2026-10-13 10:00:08", "INFO", "src.api.order",
                     "SELL 주문 완료: 005930 3주 @ 0 (주문번호: 0000300100)"),
            log_line("2026-10-13 10:00:08", "INFO", "src.engine.order_engine",
                     "FORCE_CLEAR 매도 주문 접수: 삼성전자(005930) 3주 (주문번호: 0000300100, 전략: kojiro)")]


def _worker(tmp_path, handler, db):
    client = jw("http").build_client(base_url="http://backend:8000", reporter_key="rk",
                                     transport=httpx.MockTransport(handler))
    return client, jw("main").Worker(client=client, db=db, log_dir=tmp_path)


def _ok_handler(http_log, status=None):
    def handler(req):
        path = req.url.raw_path.decode()
        http_log.append(path)
        if path.startswith("/api/trading/status"):
            return httpx.Response(200, json=status or _status())
        return httpx.Response(200, json={"success": True, "message": "", "data": {
            "running": True, "as_of": "2026-10-13T10:00:10+09:00", "items": []}})
    return handler


def test_l4_rotation_order_and_cursor_after_rows(tmp_path):
    chunk = "\n".join(_lines()) + "\n"
    (tmp_path / "auto_stock.log").write_text(chunk, encoding="utf-8")
    http_log: list[str] = []
    db = FakeDB()

    async def go():
        client, w = _worker(tmp_path, _ok_handler(http_log), db)
        async with client:
            s1 = await w.rotate()
            assert [p.split("?")[0] for p in http_log] == ["/api/trading/status", "/api/balance/exit-lines"]
            # 첫 회전: 행은 보류 → 쓰기 0, 커서도 이 청크를 넘어 저장하지 않는다(L7)
            assert not [c for c in db.calls if c[0] == "insert_order"]
            assert all(c[1]["byte_offset"] == 0 for c in db.calls if c[0] == "save_cursor")
            s2 = await w.rotate()
            return s1, s2

    s1, s2 = asyncio.run(go())
    assert (s1, s2) == ("active", "active")
    writes = db.writes()
    names = [c[0] for c in writes]
    assert ("insert_order", "0000300100") in writes
    saves = [c for c in writes if c[0] == "save_cursor"]
    assert saves and saves[-1][1]["byte_offset"] == len(chunk.encode("utf-8"))
    assert names.index("insert_order") < max(i for i, n in enumerate(names) if n == "save_cursor")


@pytest.mark.parametrize("status", [_status(running=False), _status(phase="idle")])
def test_l5_idle_touches_nothing(tmp_path, status):
    (tmp_path / "auto_stock.log").write_text("\n".join(_lines()) + "\n", encoding="utf-8")
    http_log: list[str] = []
    db = FakeDB()

    async def go():
        client, w = _worker(tmp_path, _ok_handler(http_log, status=status), db)
        async with client:
            return [await w.rotate(), await w.rotate()]

    assert asyncio.run(go()) == ["idle", "idle"]
    assert all(p.startswith("/api/trading/status") for p in http_log)
    assert db.writes() == []


def test_l6_snapshot_failure_keeps_harvesting(tmp_path):
    (tmp_path / "auto_stock.log").write_text("\n".join(_lines()) + "\n", encoding="utf-8")
    db = FakeDB()

    async def go():
        client, w = _worker(tmp_path, lambda req: httpx.Response(401, json={"detail": "x"}), db)
        async with client:
            return [await w.rotate(), await w.rotate()]

    assert asyncio.run(go()) == ["degraded", "degraded"]
    assert ("insert_order", "0000300100") in db.writes()


# ── 보완2 N9 — 커서 저장 실패 → 같은 덩어리 재읽기가 exit 사건을 중복 기록 ──────────────

FIXED_NOW = datetime(2026, 10, 13, 9, 55, 0, tzinfo=KST)  # 매도 접수(10:00:08) 이전 — G1 스냅샷이 "그 전" 값이어야 한다
G1_ITEM = {"strategy_id": "kojiro", "ticker": "005930", "stop_price": 68000, "stop_source": "atr",
           "buy_price": 70000, "buy_date": "2026-10-10", "order_no": "POS0001",
           "target_price": None, "target_source": None, "kk_arm_price": None}


def _n9_lines():
    return [log_line("2026-10-13 10:00:08", "INFO", "src.api.order",
                     "SELL 주문 완료: 005930 3주 @ 68000 (주문번호: 0000300100)"),
            log_line("2026-10-13 10:00:08", "INFO", "src.engine.order_engine",
                     "STOP_LOSS 매도 주문 접수: 삼성전자(005930) 3주 (주문번호: 0000300100, 전략: kojiro)")]


def _n9_handler(http_log):
    def handler(req):
        path = req.url.raw_path.decode()
        http_log.append(path)
        if path.startswith("/api/trading/status"):
            return httpx.Response(200, json=_status())
        return httpx.Response(200, json={"success": True, "message": "", "data": {
            "running": True, "as_of": "2026-10-13T10:05:00+09:00", "items": [G1_ITEM]}})
    return handler


def test_n9_cursor_save_failures_do_not_duplicate_exit_stops(tmp_path):
    (tmp_path / "auto_stock.log").write_text("\n".join(_n9_lines()) + "\n", encoding="utf-8")
    http_log: list[str] = []
    db = FakeJournalDB(fail_saves=3)
    client = jw("http").build_client(base_url="http://backend:8000", reporter_key="rk",
                                     transport=httpx.MockTransport(_n9_handler(http_log)))
    w = jw("main").Worker(client=client, db=db, log_dir=tmp_path, now=lambda: FIXED_NOW)

    async def go():
        async with client:
            n = {"sleeps": 0}

            async def sleep(_d):
                n["sleeps"] += 1

            await jw("main").run_forever(w.rotate, sleep=sleep, stop=lambda: n["sleeps"] >= 10)

    asyncio.run(go())

    exit_stops = [s for s in db.stops if s["event"] == "exit"]
    assert len(exit_stops) == 1, (
        f"커서 저장 실패 3회가 같은 덩어리를 재읽어 exit 사건을 중복 기록했다: {len(exit_stops)}행 — {exit_stops}")
    assert exit_stops[0]["inputs"]["sell_order_no"] == "0000300100"


# ── 보완3 N11 — 행을 쓴 뒤에 온 접수 통보가 주문구분을 못 채운다 ───────────────────────

def test_n11_late_order_notice_fills_division_after_row_already_written(tmp_path):
    """매도 행이 이미 `log_harvest` 로 쓰인 뒤(한 회전 보류가 끝난 뒤) 도착한 `[order_notice]` 도
    `fill_order_division` 로 그 행의 빈 주문구분 칸을 채워야 한다."""
    log_path = tmp_path / "auto_stock.log"
    log_path.write_text("\n".join(_lines()) + "\n", encoding="utf-8")
    http_log: list[str] = []
    db = FakeJournalDB()
    client, w = _worker(tmp_path, _ok_handler(http_log), db)

    async def go():
        async with client:
            await w.rotate()   # 1회차 — 앵커 보류
            await w.rotate()   # 2회차 — 드레인되어 행이 쓰인다(이 시점엔 통보가 없어 order_division=None)
            (row,) = db.rows(order_no="0000300100")
            assert row["order_division"] is None, "사전조건: 아직 주문구분을 모른다"

            notice = log_line("2026-10-13 10:00:40", "INFO", "src.realtime.handler",
                              "[order_notice] order_no=0000300100 orig_order_no= side=SELL rctf=0 kind=01 "
                              "cond=0 ticker=005930 qty=0000000003 price=000000000 hour=100040 rfus=0 "
                              "acpt=1 ord_qty=000000003")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(notice + "\n")
            await w.rotate()   # 3회차 — 늦게 온 통보를 읽는다. 행은 이미 DB 에 있다.

    asyncio.run(go())
    (row,) = db.rows(order_no="0000300100")
    assert row["order_division"] == "01", "이미 쓰인 행의 주문구분이 늦게 온 접수 통보로 채워지지 않았다"
    assert ("fill_order_division", "0000300100") in db.calls
    # 매도 주문 행 자체도 정확히 한 번만 실측으로 들어간다(중복 재읽기가 그 자체로 새 쓰기가 아니다).
    assert [r["source"] for r in db.rows(order_no="0000300100")] == ["log_harvest"]
