"""공통 테스트 fixture.

외부 의존성(KIS REST/WebSocket, Supabase, 시계)을 모두 격리하여
단위/통합 테스트가 결정론적이고 빠르게 실행되도록 한다.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys


# ---------------------------------------------------------------------------
# Python 3.10+ 만 import 가능한 src 모듈을 다루는 테스트는 3.9 .venv 에서 자동 스킵.
# 운영 컨테이너는 3.11/3.12 이고 CI 도 3.12 라 정상 실행된다.
# 새 PEP 604 의존 테스트가 추가되면 이 목록에 경로를 더한다.
# ---------------------------------------------------------------------------
collect_ignore_glob: list[str] = []
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# settings import 실패 방지용 환경변수 기본값.
# 실제 .env 가 있으면 그 값이 우선되며, CI 등 .env 부재 환경에서도 import 가능.
os.environ.setdefault("KIS_APP_KEY_VTS", "test-vts-key")
os.environ.setdefault("KIS_APP_SECRET_VTS", "test-vts-secret")
os.environ.setdefault("KIS_ACCOUNT_NO_VTS", "12345678")
os.environ.setdefault("KIS_ACCOUNT_PRODUCT_VTS", "01")
os.environ.setdefault("KIS_APP_KEY_REAL", "test-real-key")
os.environ.setdefault("KIS_APP_SECRET_REAL", "test-real-secret")
os.environ.setdefault("KIS_ACCOUNT_NO_REAL", "12345678")
os.environ.setdefault("KIS_ACCOUNT_PRODUCT_REAL", "01")
os.environ.setdefault("KIS_ENV", "vts")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
# supabase-py 가 import 시점에 Client(supabase_key) 를 검증한다.
# JWT 형태가 아니면 SupabaseException 발생 — 테스트에서는 더미 JWT 로 통과시킨다.
# (테스트는 실제 supabase 호출을 하지 않고 db 모듈을 monkeypatch 로 격리한다.)
os.environ.setdefault(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJ0ZXN0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDAwMDAwMDB9."
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
)
os.environ.setdefault("AUTO_START", "false")

import pytest
import respx
from freezegun import freeze_time

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# KIS REST 모킹
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_kis() -> Iterable[respx.MockRouter]:
    """KIS REST 호출을 모두 가로채는 respx 라우터.

    테스트 안에서 ``mock_kis.post("...").respond(json=...)`` 형태로 라우트를 등록.
    등록되지 않은 호출은 즉시 실패해 누락을 드러낸다.
    """

    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router


def load_kis_fixture(name: str) -> dict[str, Any]:
    """fixtures/kis_responses/<name>.json 로드 헬퍼."""
    path = FIXTURES_DIR / "kis_responses" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# KIS WebSocket 가짜 구현
# ---------------------------------------------------------------------------
@dataclass
class FakeKisWebSocket:
    """메시지 큐 기반 가짜 WS. 실제 네트워크 없이 시세/체결통보 메시지를 흘린다."""

    _queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    _subscribed: set[tuple[str, str]] = field(default_factory=set)
    closed: bool = False

    async def push(self, tr_id: str, payload: str) -> None:
        """raw 메시지 한 줄 주입. payload는 KIS 파이프 구분 문자열."""
        framed = f"0|{tr_id}|001|{payload}"
        await self._queue.put(framed)

    async def push_json(self, tr_id: str, body: dict[str, Any]) -> None:
        await self._queue.put(json.dumps({"header": {"tr_id": tr_id, "tr_key": ""}, "body": body}))

    async def recv(self) -> str:
        if self.closed:
            raise ConnectionError("FakeKisWebSocket closed")
        return await self._queue.get()

    async def send(self, message: str) -> None:
        try:
            parsed = json.loads(message)
            tr_id = parsed["header"]["tr_id"]
            tr_key = parsed["header"].get("tr_key", "")
            self._subscribed.add((tr_id, tr_key))
        except (json.JSONDecodeError, KeyError):
            pass

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[str]:
        while not self.closed:
            yield await self.recv()


@pytest.fixture
def fake_ws() -> FakeKisWebSocket:
    return FakeKisWebSocket()


# ---------------------------------------------------------------------------
# Supabase 가짜 저장소
# ---------------------------------------------------------------------------
class _FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = list(rows)
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None

    def select(self, *_columns: str) -> "_FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "_FakeQuery":
        self._filters.append((column, "eq", value))
        return self

    def neq(self, column: str, value: Any) -> "_FakeQuery":
        self._filters.append((column, "neq", value))
        return self

    def is_(self, column: str, value: Any) -> "_FakeQuery":
        """supabase-py 의 `is_("col", "null")` 호환.

        문자열 "null" 입력 시 None 매칭. 기타 값은 동등 비교.
        """
        self._filters.append((column, "is_", value))
        return self

    def gte(self, column: str, value: Any) -> "_FakeQuery":
        self._filters.append((column, "gte", value))
        return self

    def lt(self, column: str, value: Any) -> "_FakeQuery":
        self._filters.append((column, "lt", value))
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> "_FakeQuery":
        return self

    def limit(self, n: int) -> "_FakeQuery":
        self._limit = n
        return self

    def execute(self) -> Any:
        result = self._rows
        for col, op, val in self._filters:
            if op == "eq":
                result = [r for r in result if r.get(col) == val]
            elif op == "neq":
                result = [r for r in result if r.get(col) != val]
            elif op == "is_":
                # "null" 문자열은 None 매칭, 그 외는 그대로 비교
                target = None if val in ("null", None) else val
                result = [r for r in result if r.get(col) == target]
            elif op == "gte":
                result = [r for r in result if r.get(col) is not None and r.get(col) >= val]
            elif op == "lt":
                result = [r for r in result if r.get(col) is not None and r.get(col) < val]
        if self._limit is not None:
            result = result[: self._limit]
        return type("Resp", (), {"data": result})()


class _FakeTable:
    def __init__(self, name: str, store: dict[str, list[dict[str, Any]]]):
        self.name = name
        self.store = store
        self.store.setdefault(name, [])

    def select(self, *columns: str) -> _FakeQuery:
        return _FakeQuery(self.store[self.name])

    def insert(self, row: dict[str, Any] | list[dict[str, Any]]) -> "_FakeTable":
        import uuid as _uuid

        rows = row if isinstance(row, list) else [row]
        # 운영 Supabase 가 PK uuid 컬럼 DEFAULT gen_random_uuid() 로 자동 부여하는 거동 모사.
        # 호출자가 id 를 명시했으면 보존, 없으면 fake uuid 부여.
        for r in rows:
            if "id" not in r or r["id"] is None:
                r["id"] = str(_uuid.uuid4())
        self.store[self.name].extend(rows)
        # 운영 supabase-py 의 INSERT ... RETURNING * 동작 모사:
        # execute() 가 방금 INSERT 된 row 만 반환하도록 _pending_insert 저장.
        self._pending_insert = rows
        return self

    def update(self, patch: dict[str, Any]) -> "_FakeUpdate":
        return _FakeUpdate(self.store, self.name, patch)

    def delete(self) -> "_FakeDelete":
        return _FakeDelete(self.store, self.name)

    def upsert(self, row: dict[str, Any], on_conflict: str | None = None) -> "_FakeTable":
        if on_conflict and on_conflict in row:
            key = on_conflict
            existing = next((r for r in self.store[self.name] if r.get(key) == row[key]), None)
            if existing:
                existing.update(row)
                return self
        self.store[self.name].append(row)
        return self

    def execute(self) -> Any:
        # INSERT 직후 호출 시 방금 들어간 row 만 반환 (RETURNING * 동작 모사).
        # 그 외(upsert 등)는 store 전체.
        pending = getattr(self, "_pending_insert", None)
        if pending is not None:
            self._pending_insert = None
            return type("Resp", (), {"data": list(pending)})()
        return type("Resp", (), {"data": self.store[self.name]})()


class _FakeUpdate:
    def __init__(self, store: dict[str, list[dict[str, Any]]], table: str, patch: dict[str, Any]):
        self.store = store
        self.table = table
        self.patch = patch
        self._filters: list[tuple[str, Any]] = []

    def eq(self, column: str, value: Any) -> "_FakeUpdate":
        self._filters.append((column, value))
        return self

    def execute(self) -> Any:
        affected = []
        for r in self.store[self.table]:
            if all(r.get(c) == v for c, v in self._filters):
                r.update(self.patch)
                affected.append(r)
        return type("Resp", (), {"data": affected})()


class _FakeDelete:
    def __init__(self, store: dict[str, list[dict[str, Any]]], table: str):
        self.store = store
        self.table = table
        self._filters: list[tuple[str, Any]] = []

    def eq(self, column: str, value: Any) -> "_FakeDelete":
        self._filters.append((column, value))
        return self

    def execute(self) -> Any:
        keep = []
        removed = []
        for r in self.store[self.table]:
            if all(r.get(c) == v for c, v in self._filters):
                removed.append(r)
            else:
                keep.append(r)
        self.store[self.table] = keep
        return type("Resp", (), {"data": removed})()


@dataclass
class FakeSupabase:
    """인메모리 dict 기반 supabase-py 호환 클라이언트.

    실제 supabase-py와 동일한 .table().select().eq().execute() 체인을 지원한다.
    필요하면 ``store["positions"]`` 직접 접근으로 어설션 가능.
    """

    store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(name, self.store)


@pytest.fixture
def fake_supabase() -> FakeSupabase:
    return FakeSupabase()


# ---------------------------------------------------------------------------
# 시계 freeze
# ---------------------------------------------------------------------------
@pytest.fixture
def kst_clock():
    """KST 시계 freeze 헬퍼.

    인자는 KST 시각 문자열. ``datetime.now()`` 가 그 시각 그대로 반환하도록 freeze.
    예: ``with kst_clock("2026-05-08 15:19:55"): ...``

    freezegun 의 tz_offset 은 ``time.localtime()`` 계열에만 작용하고
    ``datetime.now()`` 는 입력값 자체를 반환한다. 따라서 그냥 KST 문자열을 넘긴다.
    """

    def _factory(kst_str: str):
        return freeze_time(kst_str)

    return _factory


# ---------------------------------------------------------------------------
# asyncio.sleep 즉시 진행 (시간 freeze 통합 테스트용)
# ---------------------------------------------------------------------------
@pytest.fixture
def fast_sleep(monkeypatch: pytest.MonkeyPatch):
    """asyncio.sleep을 즉시 반환하도록 패치.

    스케줄러 테스트에서 실제 대기 없이 진행하기 위함.
    """

    async def _no_sleep(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    return _no_sleep
