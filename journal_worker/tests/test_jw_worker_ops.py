"""cycle412 보완 Red — 워커 운영 결함 2·3·9 (직전 판정 원문 번호 그대로).

| # | 결함 | 계약 |
|---|---|---|
| W2·W2b | 2 `main.py:100` `trade_strategies={}` | 워커가 `trade_history` 를 주문번호로 조회해 짝짓기에 넘긴다(새 DB 메서드 없이 `JournalDB.trades_since`) — 폴백 매수·부모 없는 재주문 행이 전략을 갖고 저장된다 |
| W2c | 2 저장 실패가 같은 회차 다른 행을 지움 | 행 단위 예외 격리 — 한 행의 쓰기 실패는 그 행만 잃고 WARNING(주문번호 포함), 같은 회차 다른 행·커서 저장은 계속된다. `rotate()` 는 예외를 올리지 않는다 |
| W3 | 3 대사(W3) 실행 루프 미연결 | `run_forever` 첫 회전 안에서 대사가 돈다 — 일지에 없는 체결 `trade_history` 행이 `unmatched`/`external` 행(047 칸 전부)으로 저장된다 |
| W3b | 3 | 항등식이 깨지면 `[journal_gap]` WARNING(접두 고정, `jw` 로거) |
| W3c | 3 | 정상 흐름(한 회전 보류 포함)에서는 `[journal_gap]` 0줄 · 일지에 있는 주문으로 대사 행을 다시 쓰지 않는다 |
| W3d | 3 대사 실패 | 대사(trade_history 조회) 예외는 WARNING 으로 남기고 그 회전의 수확(행 쓰기·커서)은 계속된다 |
| W3e | 3 `run_forever` 가 예외를 소리 없이 삼킴 | 회전 예외 = `jw` 로거 WARNING(예외 문구 포함) + 백오프 |
| W3f | 3 | G0/G1 조회 실패(`degraded` — 리포터 키 오설정 등)도 WARNING |
| W3g | 3 워커 패키지에 로그 0줄 | `python -m jw run` 이 `main()` 안에서 표준 출력·평문(JSON 아님)·INFO 로 로깅을 설정한다 |
| W9·W9b | 9 `create_pool` 기본값(연결 10개) | run·backfill 모두 `min_size`·`max_size` 를 명시 — 1 ≤ min ≤ max ≤ 2 |
| W9c·W9d | 8 backfill CLI | `python -m jw backfill <경로…>` = 종료 코드 0 · `log_restore` 행 · 경로가 없으면 사용법 오류이고 DB 에 붙지 않는다 |
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from datetime import timedelta, timezone

import httpx
import pytest

from jw_testkit import GOLDEN_LOG, ORDER_KEYS, FakeJournalDB, jw, kst, log_line

pytestmark = pytest.mark.unit

UTC = timezone.utc
OE = "src.engine.order_engine"
D = "2026-10-13"
START = kst(2026, 10, 13, 10, 0, 10)


def L(hms, logger, msg, level="INFO"):
    return log_line(f"{D} {hms}", level, logger, msg)


def done(hms, side, ticker, qty, price, no):
    return L(hms, "src.api.order", f"{side} 주문 완료: {ticker} {qty}주 @ {price} (주문번호: {no})")


def sell_accept(hms, signal, no, ticker="005930", qty=3, sid="kojiro"):
    return L(hms, OE, f"{signal} 매도 주문 접수: 삼성전자({ticker}) {qty}주 (주문번호: {no}, 전략: {sid})")


def buy_accept(hms, no, ticker="000660", qty=3, price=70000, sid="kojiro"):
    return L(hms, OE, f"매수 주문 접수: SK하이닉스({ticker}) {qty}주 @ {price} (주문번호: {no}, 전략: {sid})")


def th(no, side, at_kst, *, status="COMPLETED", strategy="kojiro", ticker="005930"):
    """trade_history 행 — asyncpg 가 돌려주는 그대로 UTC aware(결함 7 과 같은 조건)."""
    return {"order_no": no, "trade_type": side, "strategy": strategy, "ticker": ticker,
            "timestamp": at_kst.astimezone(UTC), "status": status, "price": 70000, "order_price": None}


def _status():
    return {"success": True, "message": "", "data": {
        "running": True, "phase": "main_trading", "positions_detail": {},
        "strategies": {"kojiro": {"enabled": True, "params": {}, "buy_signals": [], "position_tickers": []}}}}


def _exit_lines():
    return {"success": True, "message": "", "data": {"running": True, "as_of": START.isoformat(), "items": []}}


def _ok(req):
    if req.url.raw_path.decode().startswith("/api/trading/status"):
        return httpx.Response(200, json=_status())
    return httpx.Response(200, json=_exit_lines())


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _setup(tmp_path, lines, db, handler=_ok):
    (tmp_path / "auto_stock.log").write_text("".join(ln + "\n" for ln in lines), encoding="utf-8")
    clock = Clock(START)
    client = jw("http").build_client(base_url="http://backend:8000", reporter_key="rk",
                                     transport=httpx.MockTransport(handler))
    w = jw("main").Worker(client=client, db=db, log_dir=tmp_path, now=clock)
    return client, w, clock


def _spin(tmp_path, lines, db, *, rotations, handler=_ok):
    """`run_forever` 를 실제로 돌린다 — sleep 이 가짜 시계를 그만큼 민다."""
    client, w, clock = _setup(tmp_path, lines, db, handler)
    n = {"sleeps": 0}

    async def sleep(d):
        n["sleeps"] += 1
        clock.t = clock.t + timedelta(seconds=d)

    async def go():
        async with client:
            await jw("main").run_forever(w.rotate, sleep=sleep, stop=lambda: n["sleeps"] >= rotations)

    asyncio.run(go())
    return w


def _jw_warnings(caplog, prefix=""):
    return [r for r in caplog.records if r.levelno >= logging.WARNING
            and (r.name == "jw" or r.name.startswith("jw."))
            and r.getMessage().startswith(prefix)]


def _mentions(rec, text):
    blob = rec.getMessage()
    if rec.exc_info and rec.exc_info[1] is not None:
        blob += " " + repr(rec.exc_info[1])
    return text in blob


# ── W2 trade_history 로 전략 채우기 ───────────────────────────────────────────

def test_w2_buy_fallback_row_gets_strategy_from_trade_history(tmp_path):
    lines = [done("10:00:08", "BUY", "005930", 3, 70500, "0000200700"),
             L("10:00:08", OE, "시장가 거부 → 지정가 5호가 폴백: 삼성전자(005930) @ 70500 (원인 [APBK1943] 시장가 불가)",
               level="WARNING")]
    db = FakeJournalDB(trade_rows=[th("0000200700", "BUY", kst(2026, 10, 13, 10, 0, 8), status="PENDING")])
    _spin(tmp_path, lines, db, rotations=3)
    (r,) = db.rows(order_no="0000200700")
    assert (r["strategy"], r["source"]) == ("kojiro", "fallback_inferred")


def test_w2b_orphan_reorder_row_gets_strategy_from_trade_history(tmp_path):
    lines = [done("10:00:40", "SELL", "005930", 2, 0, "0000300900"),
             L("10:00:40", OE, "손절 잔여 재주문: 삼성전자(005930) 2주")]
    db = FakeJournalDB(trade_rows=[th("0000300900", "SELL", kst(2026, 10, 13, 10, 0, 40), status="PENDING",
                                      strategy="donchian_swing")])
    _spin(tmp_path, lines, db, rotations=3)
    (r,) = db.rows(order_no="0000300900")
    assert (r["strategy"], r["source"]) == ("donchian_swing", "reorder_inferred")


def test_w2c_one_failing_row_does_not_take_the_others_down(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    lines = [done("10:00:08", "SELL", "005930", 3, 0, "0000300100"),
             sell_accept("10:00:08", "FORCE_CLEAR", "0000300100"),
             done("10:00:08", "SELL", "035720", 3, 0, "0000300200"),
             sell_accept("10:00:08", "FORCE_CLEAR", "0000300200", ticker="035720"),
             done("10:00:09", "BUY", "000660", 3, 0, "0000200100"),
             buy_accept("10:00:09", "0000200100")]
    db = FakeJournalDB(fail_orders={"0000300200"})
    client, w, clock = _setup(tmp_path, lines, db)

    async def go():
        async with client:
            await w.rotate()
            clock.t += timedelta(seconds=15)
            await w.rotate()      # 예외를 올리면 실패

    asyncio.run(go())
    assert {k[1] for k in db.orders} == {"0000300100", "0000200100"}
    assert any(_mentions(r, "0000300200") for r in _jw_warnings(caplog)), "실패한 행의 주문번호가 WARNING 에 없다"
    assert [c for c in db.calls if c[0] == "save_cursor"], "행 하나가 실패해도 커서 저장은 이어진다"


# ── W3 대사 연결 ──────────────────────────────────────────────────────────────

def test_w3_reconcile_runs_within_first_run_forever_rotation(tmp_path):
    db = FakeJournalDB(trade_rows=[
        th("0000100200", "BUY", kst(2026, 10, 13, 9, 50, 0), ticker="000660"),   # 10분 전 체결 · 일지 없음
    ])
    _spin(tmp_path, [], db, rotations=1)
    rows = db.rows(order_no="0000100200")
    assert len(rows) == 1, "run_forever 첫 회전 안에서 대사가 돌지 않았다(일지 밖 체결이 행이 안 됐다)"
    r = rows[0]
    assert set(ORDER_KEYS) <= set(r)
    assert (r["side"], r["source"], r["strategy"], r["ticker"], r["reason_code"]) == (
        "BUY", "unmatched", "kojiro", "000660", None)
    assert r["order_date"] == kst(2026, 10, 13).date()


def test_w3b_gap_is_reported_once_rows_are_settled(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    lines = [done("10:00:08", "SELL", "005930", 3, 0, "0000300100")]   # 완료 줄만 — 접수 줄 없음
    db = FakeJournalDB(trade_rows=[th("0000300100", "SELL", kst(2026, 10, 13, 10, 0, 8))])
    _spin(tmp_path, lines, db, rotations=16)   # 10:00:10 → 10:03:55 (보류·120초 문턱을 넘긴다)
    gaps = _jw_warnings(caplog, "[journal_gap] ")
    assert gaps, "항등식이 깨졌는데 [journal_gap] 이 없다"
    assert "sell_done=1" in gaps[-1].getMessage() and "sell_rows=0" in gaps[-1].getMessage()
    assert [r["source"] for r in db.rows(order_no="0000300100")] == ["unmatched"]


def test_w3c_normal_flow_reports_no_gap_and_no_reconcile_rows(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    lines = [done("10:00:08", "SELL", "005930", 3, 0, "0000300100"),
             sell_accept("10:00:08", "FORCE_CLEAR", "0000300100"),
             done("10:00:09", "BUY", "000660", 3, 0, "0000200100"),
             buy_accept("10:00:09", "0000200100")]
    db = FakeJournalDB(trade_rows=[th("0000300100", "SELL", kst(2026, 10, 13, 10, 0, 8)),
                                   th("0000200100", "BUY", kst(2026, 10, 13, 10, 0, 9), ticker="000660")])
    _spin(tmp_path, lines, db, rotations=16)
    assert _jw_warnings(caplog, "[journal_gap] ") == [], "정상 흐름(한 회전 보류 포함)에서 거짓 [journal_gap]"
    assert sorted(r["source"] for r in db.orders.values()) == ["log_harvest", "log_harvest"]
    assert sorted(db.order_attempts) == ["0000200100", "0000300100"], (
        f"일지에 있는 주문으로 대사 행을 다시 쓰려 했다: {db.order_attempts}")


def test_w3d_reconcile_failure_is_logged_and_harvest_continues(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    lines = [done("10:00:08", "SELL", "005930", 3, 0, "0000300100"),
             sell_accept("10:00:08", "FORCE_CLEAR", "0000300100")]
    db = FakeJournalDB(trades_error=RuntimeError("trade_history down"))
    client, w, clock = _setup(tmp_path, lines, db)

    async def go():
        async with client:
            for _ in range(6):
                await w.rotate()          # 예외를 올리면 실패
                clock.t += timedelta(seconds=15)

    asyncio.run(go())
    assert db.rows(order_no="0000300100"), "대사 실패가 수확(행 쓰기)을 막았다"
    assert db.cursor and db.cursor["byte_offset"] > 0, "대사 실패가 커서 저장을 막았다"
    assert any(_mentions(r, "trade_history down") for r in _jw_warnings(caplog)), "대사 실패가 WARNING 으로 안 남았다"


def test_w3e_run_forever_logs_rotation_exceptions(caplog):
    caplog.set_level(logging.INFO)
    sleeps = []

    async def rotate():
        raise RuntimeError("boom-412")

    async def sleep(d):
        sleeps.append(d)

    asyncio.run(jw("main").run_forever(rotate, sleep=sleep, stop=lambda: len(sleeps) >= 2))
    assert sleeps == [30, 60]
    recs = [r for r in _jw_warnings(caplog) if _mentions(r, "boom-412")]
    assert len(recs) == 2, "회전 예외를 소리 없이 삼켰다 — 회전마다 WARNING 1줄"


def test_w3f_degraded_fetch_is_logged(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    db = FakeJournalDB()
    _spin(tmp_path, [], db, rotations=1, handler=lambda req: httpx.Response(401, json={"detail": "x"}))
    assert _jw_warnings(caplog), "G0/G1 조회 실패(리포터 키 오설정 등)가 소리 없이 degraded 로만 남았다"


# ── W3e·W9 기동 — 로깅 설정 · 연결 풀 크기 ─────────────────────────────────────

class FakePool:
    def __init__(self):
        self.executed: list = []
        self.closed = False
        self._keys: set = set()

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        if "INSERT INTO trade_journal_orders" in sql:
            key = (args[0], args[1], args[2])
            if key in self._keys:
                return "INSERT 0 0"
            self._keys.add(key)
        return "INSERT 0 1"

    async def fetch(self, sql, *args):
        return []

    async def fetchrow(self, sql, *args):
        return None

    async def fetchval(self, sql, *args):
        return None

    async def close(self):
        self.closed = True


@pytest.fixture
def boot(monkeypatch):
    """`python -m jw …` 를 프로세스 없이 — 풀 생성 인자를 잡고, 루프는 즉시 끝낸다."""
    import asyncpg

    captured = {"pool_kwargs": [], "pools": []}

    async def fake_create_pool(*args, **kwargs):
        captured["pool_kwargs"].append(kwargs)
        pool = FakePool()
        captured["pools"].append(pool)
        return pool

    async def fake_run_forever(rotate, **kw):
        return None

    monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)
    monkeypatch.setattr(jw("main"), "run_forever", fake_run_forever)
    monkeypatch.setenv("JOURNAL_DATABASE_URL", "postgresql://journal_worker@127.0.0.1:1/x")
    monkeypatch.setenv("API_REPORTER_KEY", "rk")
    return captured


@contextlib.contextmanager
def bare_root_logger():
    """루트 로거를 비운 채로(실 컨테이너 기동과 같은 조건) — 끝나면 그 순간의 핸들러·레벨로 되돌린다.

    pytest 는 테스트 본문 직전에 루트에 자기 핸들러를 붙이므로 픽스처가 아니라 본문 안에서 비운다.
    """
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    for h in list(root.handlers):
        root.removeHandler(h)
    try:
        yield root
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in saved[0]:
            root.addHandler(h)
        root.setLevel(saved[1])


def _main(argv):
    """진입점 실행 — 설정된 루트 로거가 다른 테스트로 새지 않게 끝나면 되돌린다."""
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    try:
        jw("__main__").main(argv)
    except SystemExit as e:
        return e.code
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        for h in saved[0]:
            root.addHandler(h)
        root.setLevel(saved[1])
    return 0


def test_w3g_run_configures_plain_stdout_logging_at_info(boot):
    with bare_root_logger() as root:
        jw("__main__").main(["run"])
        outs = [h for h in root.handlers if isinstance(h, logging.StreamHandler) and h.stream is sys.stdout]
        level = root.level
        fmt = outs[0].formatter._fmt if outs and outs[0].formatter else ""
        rendered = outs[0].format(logging.LogRecord("jw.test", logging.WARNING, __file__, 1, "[journal_gap] x=1",
                                                    None, None)) if outs else ""
    assert outs, "표준 출력 핸들러가 없다(docker logs 로 못 본다)"
    assert level == logging.INFO
    assert not fmt.lstrip().startswith("{"), "JSON 이 아니라 평문"
    assert "[journal_gap] x=1" in rendered


def _assert_small_pool(kwargs):
    assert "min_size" in kwargs and "max_size" in kwargs, f"create_pool 기본값(연결 10개) — {kwargs}"
    assert 1 <= kwargs["min_size"] <= kwargs["max_size"] <= 2, kwargs


def test_w9_run_pool_is_one_or_two_connections(boot):
    _main(["run"])
    (kwargs,) = boot["pool_kwargs"]
    _assert_small_pool(kwargs)
    assert boot["pools"][0].closed


def test_w9b_backfill_pool_is_one_or_two_connections(boot, tmp_path):
    p = tmp_path / "auto_stock.log.2026-09-17"
    p.write_text(GOLDEN_LOG.read_text(encoding="utf-8"), encoding="utf-8")
    assert _main(["backfill", str(p)]) in (0, None)
    (kwargs,) = boot["pool_kwargs"]
    _assert_small_pool(kwargs)


def test_w9c_backfill_cli_writes_restore_rows_idempotently(boot, tmp_path):
    p = tmp_path / "auto_stock.log.2026-09-17"
    p.write_text(GOLDEN_LOG.read_text(encoding="utf-8"), encoding="utf-8")
    assert _main(["backfill", str(p)]) in (0, None)
    assert _main(["backfill", str(p)]) in (0, None)
    inserts = [(sql, args) for pool in boot["pools"] for sql, args in pool.executed
               if "INSERT INTO trade_journal_orders" in sql]
    assert len(inserts) == 2 * 145
    assert {args[5] for _, args in inserts} == {"log_restore"}
    assert all(pool.closed for pool in boot["pools"])


def test_w9d_backfill_cli_without_paths_is_a_usage_error(boot):
    code = _main(["backfill"])
    assert code not in (0, None), "경로 없이 backfill 을 부르면 사용법 오류여야 한다"
    assert boot["pool_kwargs"] == [], "경로가 없으면 DB 에 붙지도 않는다"
