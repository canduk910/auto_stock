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
# cycle243 — API 인증 키 테스트 기본값(비밀 아님). 개발자 `.env` 유무와 무관하게
# `settings.api_auth_key` 를 결정론적으로 만든다. 인증을 *직접* 검증하는 테스트는
# 값을 monkeypatch 로 명시하므로 이 값에 의존하지 않는다.
os.environ.setdefault("API_AUTH_KEY", "test-api-auth-key-not-a-secret-cycle243")
os.environ.setdefault("API_ALLOWED_ORIGINS", "")

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
# 사이클 M2a (2026-07-16) — system_config pg.* 인메모리 fake (key-value 테이블)
#
# system_config.py 가 supabase-py → src.db.pg(asyncpg) 로 전환되며 기존
# `fake_supabase`(테이블 체인 흉내) 로는 라우팅이 불가(모듈이 supabase 를 더 이상
# import 하지 않음). 동일 round-trip 계약(get/set)을 pg.fetch/execute 인터페이스로
# 흉내내는 최소 fake — SQL 텍스트 파싱이 아니라 system_config.py 가 실제로 발화하는
# 고정 패턴(`SELECT value FROM system_config WHERE key = $1` /
# `INSERT INTO system_config (key, value, updated_at) VALUES ... ON CONFLICT (key)
# DO UPDATE ...`)에 맞춘 key-value dict 구현.
# ---------------------------------------------------------------------------
class FakePgKV:
    """system_config 전용 인메모리 pg.* fake (key → value JSONB dict)."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        # system_config._select_value: "SELECT value FROM system_config WHERE key = $1"
        key = args[0]
        if key not in self.store:
            return []
        return [{"value": self.store[key]}]

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        rows = await self.fetch(sql, *args)
        return rows[0] if rows else None

    async def fetchval(self, sql: str, *args: Any) -> Any:
        rows = await self.fetch(sql, *args)
        return rows[0]["value"] if rows else None

    async def execute(self, sql: str, *args: Any) -> str:
        # system_config._upsert_value: INSERT (key, value, updated_at) ... $1,$2,$3
        key, value = args[0], args[1]
        self.store[key] = value
        return "INSERT 0 1"

    async def _with_retry(self, coro_factory, *, op: str = ""):
        return await coro_factory()


@pytest.fixture
def fake_pg_kv() -> FakePgKV:
    return FakePgKV()


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


# ---------------------------------------------------------------------------
# 사이클 202 — 동시호가 게이트 시간 flakiness 차단 (CI 결정론화)
#
# stale_watcher 테스트(~20 파일)가 `SessionTracker.is_call_auction_now()` 를
# mock/freeze 하지 않아, CI 가 동시호가 시간창(08:30~09:00 / 15:20~15:30 KST)에
# 실행되면 `stale_watcher_core._call_auction_skip` 이 `[stale_skip_call_auction]`
# 을 발화하며 stale 감지를 전량 skip → `_stale_last_resubscribe_at` 미갱신 등으로
# 시간대별 flaky 실패(사이클 173/176 인계, 사이클 201 push 가 15:2x 창에 걸려 실발현).
#
# 근본 시정 = `is_call_auction_now` 를 전역 False 로 중립화(시계 독립화). 단, 이
# 게이트 동작을 *직접 검증*하는 call-auction 테스트(cycle162/182)는 제외하여 실제
# 로직 보존. stale_watcher_core 는 `from src.engine.session import session_tracker`
# 모듈 싱글톤을 호출하므로 싱글톤 메서드 패치로 전 경로 커버.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _neutralize_call_auction_gate(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
):
    # 제외는 *파일명* 기준 (nodeid 전체가 아니라 `::` 앞 파일 경로만). 테스트 *이름*에
    # "call_auction" 이 들어간 경우(예: cycle202 test_fixture_neutralizes_call_auction_gate)
    # 까지 오탐 제외해 시계 의존 flaky 를 유발하던 결함 시정. 게이트 검증 파일
    # (cycle162/182_call_auction_*)은 파일명에 "call_auction" 포함 → 실제 로직 보존.
    if "call_auction" in request.node.nodeid.split("::")[0]:
        return  # cycle162/182 = 게이트 동작 자체를 검증 → 실제 로직 보존
    try:
        from src.engine.session import session_tracker

        monkeypatch.setattr(
            session_tracker,
            "is_call_auction_now",
            lambda now=None: False,
            raising=False,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# cycle238 — 프리장 청산 보류 게이트 **시각 폴백** 결정론화
#
# `_defers_pre_market_exit` 가 `session_tracker.active`(30초 stale 캐시) 외에
# `risk._now_kst()` 기반 시각 폴백을 OR 로 더한다(08:00 정각 ~30초 구멍 시정).
# 그 결과 게이트가 **불가피하게 벽시계에 의존**하게 되어, 08:00~09:00 KST 에
# 실행되는 CI/로컬에서 기존 on_tick 테스트 11+ 파일이 청산 평가를 통째로 보류
# 당해 흔들린다(사이클 202 `_neutralize_call_auction_gate` 와 동형 문제).
#
# 시정 = `risk._now_kst` 를 프리장 **밖**(MAIN 구간)으로 전역 핀.
# - 핀 값 `2026-01-05 10:30:00+09:00` → `session.boards_at(10:30) == {MAIN}`.
# - 게이트를 **직접 검증**하는 테스트는 `@pytest.mark.real_pre_market_clock` 으로
#   옵트아웃하거나, 이 픽스처보다 뒤에 도는 `monkeypatch.setattr(risk, "_now_kst", ...)`
#   로 시각을 명시한다(후자가 이긴다).
# - `raising=False` — Red 단계(`_now_kst` 미존재)에서 전체 스위트가 픽스처 때문에
#   죽지 않는다. Green 이후엔 실제 심볼을 덮어쓴다.
# ---------------------------------------------------------------------------
_PINNED_PRE_MARKET_CLOCK_KST = __import__("datetime").datetime(
    2026, 1, 5, 10, 30, 0,
    tzinfo=__import__("datetime").timezone(__import__("datetime").timedelta(hours=9)),
)


@pytest.fixture(autouse=True)
def _pin_pre_market_clock(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
):
    if request.node.get_closest_marker("real_pre_market_clock"):
        return  # 실 seam(벽시계/freezegun) 자체를 검증하는 테스트 — 핀 금지
    try:
        from src.engine import risk as _risk_mod

        monkeypatch.setattr(
            _risk_mod,
            "_now_kst",
            lambda: _PINNED_PRE_MARKET_CLOCK_KST,
            raising=False,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# cycle317 — 15:30~16:00 완전 휴식 컷 중립화
#
# cycle295 가 그 30분을 「완전 휴식」으로 만들었고(그 창의 주문 0건) 판정은
# `order_engine._market_rest_now(now)` 가 **벽시계**로 한다. 그래서 `execute_buy`/
# `execute_sell` 을 타는 모든 테스트가 그 시각에 돌면 컷된다 — 2026-09-19 실측으로
# 로컬 15:53 과 CI(UTC 06:46 = KST 15:46) 둘 다 **59건**이 붉었다. 컨테이너가
# `TZ=Asia/Seoul` 이라 CI 도 KST 로 돈다. 즉 **매일 30분간 CI 가 붉어지는 상태**였다.
#
# 🔴 **왜 시계가 아니라 판정 함수를 갈아끼우는가** — `src/engine/order_engine.py` 는
# 8영역이라 승인 없이 못 고치는데 그 파일에는 `_now_kst()` 같은 시계 seam 이 없다
# (`datetime.now(_KST_TZ)` 직접 호출). 프로덕션에 seam 을 새로 파려면 승인이 필요하다.
# 다행히 `_market_rest_now` 는 **모듈 전역 이름으로** 불리므로(`order_engine.py:620`)
# 그 이름 하나만 바꾸면 된다 — 프로덕션 코드 무접촉이고 `_neutralize_api_auth` 와 같은 구조다.
#
# 컷 자체를 검증하는 테스트는 `@pytest.mark.real_market_rest` 로 옵트아웃한다.
# 🔴 그 규약이 없으면 이 픽스처가 cycle295 의 회귀 가드를 통째로 무력화한다 —
# 「15:30~16:00 에 주문이 안 나간다」를 검증하는 테스트가 영원히 통과해 버린다.
# `raising=False` — 함수가 사라져도 전체 스위트가 픽스처 때문에 죽지 않는다.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _neutralize_market_rest(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
):
    if request.node.get_closest_marker("real_market_rest"):
        return  # 컷 자체를 검증하는 테스트 — 중립화 금지
    try:
        from src.engine import order_engine as _oe_mod

        monkeypatch.setattr(
            _oe_mod,
            "_market_rest_now",
            lambda _now: (False, ""),
            raising=False,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# cycle243 — API 인증(X-API-Key) 중립화
#
# 인증을 켜면 `src.main.app` 을 TestClient 로 두드리는 기존 40파일·수집 201케이스가
# 401 로 전멸하고 coverage gate(`fail_under=60`)까지 동반 실패한다(진입 경로 =
# `tests/contract/conftest.py` 의 `contract_env` 13파일 + 직접 `from src.main import
# app` 27파일). TestClient 가 27곳에서 각자 생성되므로 "기본 헤더 주입" 은 27곳 수정이
# 필요해 부적합하고, seam 은 한 곳이어야 한다.
#
# ⚠️ **프로덕션 코드에 `_TEST_BYPASS` 류 플래그를 두지 않는다.** 판정 함수 자체를
# 테스트가 갈아끼우는 형태여야 런타임에 우회 경로가 *존재하지 않는다*. 그래서
# `src/middleware/api_auth.py` 는 `authorize` 를 모듈 전역 이름으로 호출하고
# (AST 가드 D-12), 이 픽스처는 그 이름 하나만 바꾼다.
#
# 인증 판정 자체를 검증하는 테스트는 `@pytest.mark.real_api_auth` 로 옵트아웃한다
# (미들웨어 단위 A · 앱 배선 B · 픽스처 옵트아웃 실증 C-2).
# `raising=False` — 미구현 단계에서 전체 스위트가 픽스처 때문에 죽지 않는다.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _neutralize_api_auth(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
):
    if request.node.get_closest_marker("real_api_auth"):
        return  # 인증 자체를 검증하는 테스트 — 중립화 금지
    try:
        from src.middleware import api_auth as _api_auth_mod

        monkeypatch.setattr(_api_auth_mod, "authorize", lambda scope: "", raising=False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# cycle363 — 휴장일 판정 leaf 의 조회 seam 중립화 (cycle295·317 교훈: 게이트를 넣는
# 사이클이 중립화 픽스처를 같이 만든다)
#
# `src/engine/trading_calendar.py` 는 KIS CTCA0903R(`src.api.condition.is_trading_day`)
# 로 개장 여부를 묻고 결과를 **프로세스 수명 메모**에 담는다. 그대로 두면 두 가지가
# 스위트를 흔든다 — (1) 부팅 즉시 실행 슬롯 게이트와 6전략 prepare 가 테스트마다 실 KIS
# 로 나가려 하고 (2) 한 테스트가 채운 메모가 다음 테스트의 판정을 바꾼다.
#
# 시정 = 조회 seam `_lookup_open` 을 **None(모름)** 으로 바꾸고 메모를 비운다. 그래서
# 이 마커가 없는 기존 테스트는 ① 슬롯 게이트에서 `reason=calendar_unknown → RUN`
# (현행 「실행」 방향) ② prepare 에서 `expected_head=None` → 어댑터의 현행 달력 판정을 본다.
# 휴장일 판정 자체를 검증하는 테스트는 `@pytest.mark.real_trading_calendar` 로
# 옵트아웃하거나, 이 픽스처보다 뒤에 도는 `monkeypatch.setattr(... "_lookup_open", ...)`
# 로 달력을 명시한다(후자가 이긴다). 옵트아웃이어도 메모는 비운다(테스트 간 격리).
# Red 단계(leaf 미존재)에서는 import 가 실패하므로 아무것도 하지 않는다 — 전체 스위트가
# 이 픽스처 때문에 죽지 않는다. `raising=False` 도 같은 이유다.
# ---------------------------------------------------------------------------
def _reset_trading_calendar_memo() -> None:
    try:
        from src.engine import trading_calendar as _tc_mod
    except Exception:
        return
    reset = getattr(_tc_mod, "_reset_cache_for_tests", None)
    if callable(reset):
        try:
            reset()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _neutralize_trading_calendar(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
):
    _reset_trading_calendar_memo()
    if not request.node.get_closest_marker("real_trading_calendar"):
        try:
            from src.engine import trading_calendar as _tc_mod

            async def _unknown(_d: Any) -> None:
                return None

            monkeypatch.setattr(_tc_mod, "_lookup_open", _unknown, raising=False)
        except Exception:
            pass
    yield
    _reset_trading_calendar_memo()


# ---------------------------------------------------------------------------
# cycle369 — 종목상태(관리 51·단기과열 59) 매수 차단 레지스트리 중립화 (K20)
#
# `src/engine/status_exit_watch.py` 의 매수 차단 레지스트리는 **모듈 전역**이고, 관측 훅
# (`condition._fetch_stock_detail_and_cache` → `observe_fhkst`)이 FHKST 조회마다 기록한다.
# 그대로 두면 api 테스트가 흘린 `short_over_yn:"Y"` 픽스처가 같은 날짜로 도는 무관한
# 테스트의 `_account_soft_gate_blocked(...)` 를 True 로 뒤집는다(시각·순서 의존 flaky —
# `test_cycle233_watcher_gate.py` 가 `"005930"` 으로 False 를 단언한다).
#
# 시정 = 매 테스트 전·후 `reset_state_for_test()` + 마커 `real_status_watch` 가 **없으면**
#   (1) `observe_fhkst` → no-op (2) `buy_gate` → False
#   (3) `task_loop` → 즉시 반환 코루틴 — `scheduler.start()` 를 도는 기존 테스트가 실 루프를
#       띄워 실 KIS 조회로 새지 않게 한다(cycle363 「게이트를 넣는 사이클이 중립화 픽스처를
#       같이 만든다」 · 일부 start() 테스트는 전역 `asyncio.sleep` 을 AsyncMock 으로 바꿔
#       루프가 헛돌 수 있다).
# leaf·배선을 직접 검증하는 테스트는 `@pytest.mark.real_status_watch` 로 옵트아웃한다.
# Red 단계(leaf 미존재)에서는 import 가 실패하므로 아무것도 하지 않는다 — 전체 스위트가
# 이 픽스처 때문에 죽지 않는다. `raising=False` 도 같은 이유다.
# ---------------------------------------------------------------------------
def _reset_status_watch_state() -> None:
    try:
        from src.engine import status_exit_watch as _sew_mod
    except Exception:
        return
    reset = getattr(_sew_mod, "reset_state_for_test", None)
    if callable(reset):
        try:
            reset()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _neutralize_status_watch(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
):
    _reset_status_watch_state()
    if not request.node.get_closest_marker("real_status_watch"):
        try:
            from src.engine import status_exit_watch as _sew_mod

            async def _inert_task_loop(*_a: Any, **_k: Any) -> None:
                return None

            monkeypatch.setattr(_sew_mod, "observe_fhkst", lambda *_a, **_k: None, raising=False)
            monkeypatch.setattr(_sew_mod, "buy_gate", lambda *_a, **_k: False, raising=False)
            monkeypatch.setattr(_sew_mod, "task_loop", _inert_task_loop, raising=False)
        except Exception:
            pass
    yield
    _reset_status_watch_state()
