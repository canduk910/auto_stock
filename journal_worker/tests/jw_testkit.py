"""cycle412 — 워커 테스트 공용 도우미(테스트 모듈이 `from jw_testkit import …` 로 쓴다).

`conftest.py` 가 `journal_worker/` 와 이 디렉터리를 sys.path 앞에 넣는다.
계약 = `_workspace/red/cycle412/journal_contract.md` 3절.
"""
from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parent
JW_DIR = WORKER_ROOT / "jw"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN_LOG = FIXTURES / "golden_2026-09-17_10-07.log"
GOLDEN_EXPECTED = FIXTURES / "golden_expected.json"
KST = timezone(timedelta(hours=9))


def jw(module: str):
    """`jw.<module>` 을 테스트 안에서 늦게 import 한다 — 모듈이 없으면 그 테스트만 실패한다."""
    return importlib.import_module(f"jw.{module}")


def kst(y, mo, d, h=0, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=KST)


def golden_lines() -> list[str]:
    return GOLDEN_LOG.read_text(encoding="utf-8").splitlines()


def golden_expected() -> dict:
    return json.loads(GOLDEN_EXPECTED.read_text(encoding="utf-8"))


def log_line(ts: str, level: str, logger: str, msg: str) -> str:
    """운영 파일 로그 한 줄(`src/main.py` LOG_FORMAT) — 레벨 칸은 8자 왼쪽 정렬."""
    return f"{ts} [{level:<8}] {logger} — {msg}"


def parse_all(lines) -> list[dict]:
    g = jw("grammar")
    return [e for e in (g.parse_line(ln) for ln in lines) if e is not None]


def jw_sources() -> dict[str, str]:
    """`journal_worker/jw/**/*.py` 원문 {상대경로: 내용}. 없으면 빈 dict(호출 쪽이 단언)."""
    if not JW_DIR.is_dir():
        return {}
    return {
        p.relative_to(WORKER_ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(JW_DIR.rglob("*.py"))
        if "__pycache__" not in p.parts
    }


# ── cycle412 보완 Red — 공용 도우미 ─────────────────────────────────────────────

import gc as _gc
import logging as _logging
import sys as _sys
import types as _types

# 047 `trade_journal_orders` 칸(id 제외)과 NOT NULL 칸 — 가짜 DB 가 실 DB 처럼 거부하게 한다.
ORDER_KEYS = ("order_date", "order_no", "side", "strategy", "ticker", "source", "reason_code",
              "reason_sub", "judge_price", "order_price", "order_division", "exchange",
              "parent_order_no", "fired_line", "effective_line", "signal", "params", "noted_at")
ORDER_NOT_NULL = ("order_date", "order_no", "side", "strategy", "ticker", "source", "noted_at")
STOP_KEYS = ("strategy", "ticker", "buy_date", "pos_order_no", "observed_at", "event", "stop_price",
             "stop_kind", "target_price", "target_hit", "arm_price", "inputs")
STOP_NOT_NULL = ("strategy", "ticker", "observed_at", "event")


class FakeNotNullViolation(Exception):
    """asyncpg.NotNullViolationError 대역 — 워커가 이름으로 잡지 못하게 일부러 다른 클래스."""


class FakeJournalDB:
    """`jw.db.JournalDB` 와 같은 메서드 — 047 의 UNIQUE(order_date, order_no, side)·NOT NULL 을 흉내 낸다.

    - ``insert_order``: 칸이 모자라면 KeyError · NOT NULL 칸이 None 이면 FakeNotNullViolation ·
      ``fail_orders`` 의 주문번호는 RuntimeError · 같은 키는 조용히 무시(ON CONFLICT DO NOTHING).
      반환 = 새로 넣었으면 True(``INSERT 0 1``) · 이미 있으면 False(``INSERT 0 0``) — 계약 7절 N1.
    - ``promote_order``(계약 7절 N1): 같은 키의 행이 ``unmatched``·``external`` 일 때만 그 행의 빈 칸
      (None · 전략 ``"unknown"``)을 채우고 source 를 로그 행 것으로 바꾼다 → True. 그 밖(행 없음 · 이미
      실측 행) → False · ``fail_promote`` 의 주문번호는 RuntimeError.
    - ``save_cursor``: 처음 ``fail_saves`` 번은 RuntimeError(커서 저장 실패 — 계약 7절 N1-b).
    - ``trades_since(since)``: ``trade_rows`` 중 ``timestamp >= since`` 만 · ``trades_error`` 면 그 예외.
    - ``attempts`` = 쓰기 시도 (메서드, 주문번호, side, source) 전부 — 대사가 빈 행을 먼저 쓰려 했는지 본다.
    """

    def __init__(self, *, cursor=None, trade_rows=(), fail_orders=(), trades_error=None, last_rows=None,
                 fail_saves=0, fail_promote=()):
        self.orders: dict = {}
        self.order_attempts: list = []
        self.attempts: list = []
        self.stops: list = []
        self.calls: list = []
        self.cursor = cursor
        self.trade_rows = list(trade_rows)
        self.fail_orders = set(fail_orders)
        self.trades_error = trades_error
        self.fail_saves = fail_saves
        self.fail_promote = set(fail_promote)
        self._last_rows = dict(last_rows or {})

    def seed(self, row):
        """이전 실행(또는 이전 판)이 남긴 행을 미리 넣는다 — 칸이 모자라면 None 으로 채운다."""
        full = {k: row.get(k) for k in ORDER_KEYS}
        self.orders[(full["order_date"], full["order_no"], full["side"])] = full
        return full

    async def insert_order(self, row):
        self.calls.append(("insert_order", row.get("order_no")))
        self.order_attempts.append(row.get("order_no"))
        self.attempts.append(("insert_order", row.get("order_no"), row.get("side"), row.get("source")))
        missing = [k for k in ORDER_KEYS if k not in row]
        if missing:
            raise KeyError(f"insert_order 칸 누락: {missing}")
        if row["order_no"] in self.fail_orders:
            raise RuntimeError(f"forced insert failure order_no={row['order_no']}")
        nulls = [k for k in ORDER_NOT_NULL if row[k] is None]
        if nulls:
            raise FakeNotNullViolation(f"null value in column {nulls[0]!r} of trade_journal_orders")
        key = (row["order_date"], row["order_no"], row["side"])
        if key in self.orders:
            return False
        self.orders[key] = dict(row)
        return True

    async def promote_order(self, row):
        self.calls.append(("promote_order", row.get("order_no")))
        self.attempts.append(("promote_order", row.get("order_no"), row.get("side"), row.get("source")))
        missing = [k for k in ORDER_KEYS if k not in row]
        if missing:
            raise KeyError(f"promote_order 칸 누락: {missing}")
        if row["order_no"] in self.fail_promote:
            raise RuntimeError(f"forced promote failure order_no={row['order_no']}")
        cur = self.orders.get((row["order_date"], row["order_no"], row["side"]))
        if cur is None or cur["source"] not in ("unmatched", "external"):
            return False
        for k in ORDER_KEYS:
            if k in ("order_date", "order_no", "side", "ticker", "noted_at"):
                continue
            if k == "source":
                cur["source"] = row["source"]
            elif k == "strategy":
                if cur["strategy"] == "unknown" and row["strategy"] is not None:
                    cur["strategy"] = row["strategy"]
            elif cur.get(k) is None:
                cur[k] = row[k]
        return True

    async def fill_order_division(self, order_date, order_no, side, division):
        self.calls.append(("fill_order_division", order_no))
        r = self.orders.get((order_date, order_no, side))
        if r is not None and r.get("order_division") is None:
            r["order_division"] = division

    async def insert_stop(self, ev):
        self.calls.append(("insert_stop", ev.get("event")))
        missing = [k for k in STOP_KEYS if k not in ev]
        if missing:
            raise KeyError(f"insert_stop 칸 누락: {missing}")
        nulls = [k for k in STOP_NOT_NULL if ev[k] is None]
        if nulls:
            raise FakeNotNullViolation(f"null value in column {nulls[0]!r} of trade_journal_stops")
        self.stops.append(dict(ev))

    async def load_cursor(self, name="main"):
        self.calls.append(("load_cursor",))
        return dict(self.cursor) if self.cursor else None

    async def save_cursor(self, cursor, name="main"):
        self.calls.append(("save_cursor", dict(cursor)))
        if self.fail_saves > 0:
            self.fail_saves -= 1
            raise RuntimeError("forced save_cursor failure")
        self.cursor = dict(cursor)

    async def last_stop_rows(self):
        self.calls.append(("last_stop_rows",))
        return dict(self._last_rows)

    async def trades_since(self, since):
        self.calls.append(("trades_since", since))
        if self.trades_error is not None:
            raise self.trades_error
        return [dict(t) for t in self.trade_rows if t["timestamp"] >= since]

    def rows(self, **match):
        return [r for r in self.orders.values() if all(r.get(k) == v for k, v in match.items())]


_SKIP_TYPES = (type, _types.ModuleType, _types.FunctionType, _types.BuiltinFunctionType,
               _types.MethodType, _types.CodeType, _types.FrameType, _logging.Logger,
               _logging.PlaceHolder, _logging.Manager)


def _walk(root, exclude=()):
    seen = {id(x) for x in exclude}
    stack = [root]
    while stack:
        o = stack.pop()
        if id(o) in seen:
            continue
        seen.add(id(o))
        if isinstance(o, _SKIP_TYPES):
            continue
        yield o
        stack.extend(_gc.get_referents(o))


def retained_bytes(root, *, exclude=()) -> int:
    """root 에서 닿는 객체들의 ``sys.getsizeof`` 합(클래스·모듈·함수·로거는 공유물이라 뺀다)."""
    return sum(_sys.getsizeof(o) for o in _walk(root, exclude))


def reachable_ids(root, *, exclude=()) -> set:
    return {id(o) for o in _walk(root, exclude)}


def reachable_objects(root, *, exclude=()) -> list:
    """root 에서 닿는 객체 목록(``retained_bytes`` 와 같은 걸음) — 보완2 M5 가 전날 시각을 찾는다."""
    return list(_walk(root, exclude))


# ── cycle412 보완2 Red — 살아 있는 로그 · 심장 박동 줄 (계약 7절 N1) ─────────────────
#
# 대사 기준이 「행까지 쓴 로그 줄의 시각」 이 되었으므로, 대사가 도는 시험은 로그가 시계를 따라
# 자라야 한다(정적 파일이면 기준 시각이 멈춰 대사가 영영 돌지 않는다). 운영 로그는 문법이 모르는 줄
# (스캔 루프·체결 수 등)이 끊임없이 찍히므로, 같은 역할의 「심장 박동」 줄을 넣는다.


def line_ts(line: str) -> datetime:
    """운영 로그 줄 앞머리 `YYYY-MM-DD HH:MM:SS` → KST aware."""
    return datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)


HEARTBEAT_LOGGER = "src.engine.scanner"


def heartbeat(ts: datetime, *, pad: int = 0) -> str:
    """문법이 모르는 줄(`parse_line` → None) — 대사 기준 시각을 앞으로 미는 역할만 한다."""
    msg = "[scan_loop] 구독 유지 41/41" + ((" " + "x" * pad) if pad else "")
    return log_line(ts.strftime("%Y-%m-%d %H:%M:%S"), "INFO", HEARTBEAT_LOGGER, msg)


def heartbeats(start: datetime, end: datetime, *, every_s: int = 15, pad: int = 0) -> list[str]:
    out, t = [], start
    while t <= end:
        out.append(heartbeat(t, pad=pad))
        t += timedelta(seconds=every_s)
    return out


class LiveLog:
    """시계가 간 만큼만 줄이 붙는 `auto_stock.log` — ``advance(t)`` 가 ``시각 ≤ t`` 인 줄을 덧붙인다.

    같은 초의 줄은 넣은 순서를 지킨다(정렬이 안정적). 만들 때 빈 파일로 시작한다.
    """

    def __init__(self, log_dir, lines):
        self.path = Path(log_dir) / "auto_stock.log"
        self._entries = sorted(((line_ts(ln), ln) for ln in lines), key=lambda e: e[0])
        self._i = 0
        self.path.write_text("", encoding="utf-8")

    def advance(self, t: datetime) -> None:
        chunk = []
        while self._i < len(self._entries) and self._entries[self._i][0] <= t:
            chunk.append(self._entries[self._i][1] + "\n")
            self._i += 1
        if chunk:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write("".join(chunk))
