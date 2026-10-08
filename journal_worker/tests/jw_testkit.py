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
    - ``trades_since(since)``: ``trade_rows`` 중 ``timestamp >= since`` 만 · ``trades_error`` 면 그 예외.
    """

    def __init__(self, *, cursor=None, trade_rows=(), fail_orders=(), trades_error=None, last_rows=None):
        self.orders: dict = {}
        self.order_attempts: list = []
        self.stops: list = []
        self.calls: list = []
        self.cursor = cursor
        self.trade_rows = list(trade_rows)
        self.fail_orders = set(fail_orders)
        self.trades_error = trades_error
        self._last_rows = dict(last_rows or {})

    async def insert_order(self, row):
        self.calls.append(("insert_order", row.get("order_no")))
        self.order_attempts.append(row.get("order_no"))
        missing = [k for k in ORDER_KEYS if k not in row]
        if missing:
            raise KeyError(f"insert_order 칸 누락: {missing}")
        if row["order_no"] in self.fail_orders:
            raise RuntimeError(f"forced insert failure order_no={row['order_no']}")
        nulls = [k for k in ORDER_NOT_NULL if row[k] is None]
        if nulls:
            raise FakeNotNullViolation(f"null value in column {nulls[0]!r} of trade_journal_orders")
        key = (row["order_date"], row["order_no"], row["side"])
        if key not in self.orders:
            self.orders[key] = dict(row)

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
