"""사이클 20 (2026-05-20) — 토큰 발급 분당 1개 한도 직렬화 회귀 가드.

KIS `/oauth2/tokenP` 는 분당 1개 / 전역 한도. 4 매니저 동시 발급 시 일부 403.
- (A) Lock 직렬화 — 동시 2 매니저 호출 시 직렬 실행
- (B) gap 강제 — `_ISSUE_GAP_SECS` 미달 시 sleep 호출
- (C) gap 충분히 지남 — sleep 호출 안 함
- (D) 캐시 hit 시 issue() skip — `_is_valid()` True 면 발급/직렬화 0
- (E) gather race — `asyncio.gather` 시 직렬화 보장
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_token_state(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """각 테스트 전 모듈 전역 lock + 마지막 발급 시각 + 캐시 경로 초기화."""
    from src.auth import token as token_mod

    # 캐시 경로 격리 (디렉토리 단위 + 호환 fallback 양쪽)
    monkeypatch.setattr(token_mod, "_TOKEN_CACHE_DIR", tmp_path / ".token_cache")
    monkeypatch.setattr(token_mod, "_TOKEN_CACHE_PATH", tmp_path / ".token_cache" / "main.json")
    monkeypatch.setattr(token_mod, "_LEGACY_MAIN_CACHE_PATH", tmp_path / ".token_cache.json")
    monkeypatch.setattr(token_mod, "_QUOTE_TOKEN_CACHE_PREFIX", "quote_")

    def _safe(label: str) -> Path:
        safe_label = "".join(
            ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in label
        )
        return tmp_path / ".token_cache" / f"quote_{safe_label}.json"

    monkeypatch.setattr(token_mod, "_safe_cache_filename", _safe)

    token_mod.reset_quote_token_managers()
    token_mod.reset_global_issue_state()
    yield
    token_mod.reset_quote_token_managers()
    token_mod.reset_global_issue_state()


def _make_token_response(token: str = "ACCESS-TOK", hours: int = 23) -> MagicMock:
    """KIS /oauth2/tokenP 더미 응답."""
    expired = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(
        return_value={
            "access_token": token,
            "access_token_token_expired": expired,
        }
    )
    return resp


class _MonotonicClock:
    """time.monotonic 시뮬레이션 — issue() 안 두 호출(체크/갱신) 모두 동일 시각 반환.

    `advance(secs)` 로 시간 진행. 운영 코드의 monotonic 호출 횟수에 견고.
    """

    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, secs: float) -> None:
        self._now += secs


@pytest.mark.asyncio
async def test_A_lock_serializes_concurrent_issue_calls(
    monkeypatch: pytest.MonkeyPatch,
):
    """(A) 동시 2 매니저 issue() 호출 — Lock 으로 직렬화. 두 번째는 60s 대기.

    실제 동시 발사는 (E) 에서 검증. 본 케이스는 순차 호출 + gap 1s 시뮬레이션.
    """
    from src.auth import token as token_mod

    sleep_calls: list[float] = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    monkeypatch.setattr(token_mod.asyncio, "sleep", fake_sleep)

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *_a, **_kw):
            return _make_token_response()

    monkeypatch.setattr(token_mod.httpx, "AsyncClient", lambda: _Client())

    # start>0 — 첫 발급 후 _LAST_ISSUE_AT 가 0 보다 커야 두 번째 호출에서 gap 체크됨
    clock = _MonotonicClock(start=100.0)
    monkeypatch.setattr(token_mod.time, "monotonic", clock)

    mgr1 = token_mod.TokenManager()
    mgr2 = token_mod.TokenManager()

    # 첫 발급: _LAST_ISSUE_AT=0 → sleep 없음, 발급 후 _LAST_ISSUE_AT=100.0
    await mgr1.issue()
    # 1초만 경과 후 두 번째 발급 → gap 60s sleep 필요
    clock.advance(1.0)
    await mgr2.issue()

    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(60.0, rel=0.01)


@pytest.mark.asyncio
async def test_B_gap_enforced_when_under_threshold(
    monkeypatch: pytest.MonkeyPatch,
):
    """(B) `_LAST_ISSUE_AT` 직후 두 번째 호출 시 `_ISSUE_GAP_SECS` 미달이면 sleep."""
    from src.auth import token as token_mod

    sleep_calls: list[float] = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    monkeypatch.setattr(token_mod.asyncio, "sleep", fake_sleep)

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *_a, **_kw):
            return _make_token_response()

    monkeypatch.setattr(token_mod.httpx, "AsyncClient", lambda: _Client())

    # 첫 발급 후 10초 경과 → 두 번째 발급은 51s sleep
    clock = _MonotonicClock(start=100.0)
    monkeypatch.setattr(token_mod.time, "monotonic", clock)

    mgr = token_mod.TokenManager()
    await mgr.issue()  # _LAST_ISSUE_AT 갱신
    clock.advance(10.0)
    await mgr.issue()  # gap 10s → sleep 51s

    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(51.0, rel=0.01)


@pytest.mark.asyncio
async def test_C_no_sleep_when_gap_sufficient(
    monkeypatch: pytest.MonkeyPatch,
):
    """(C) `_LAST_ISSUE_AT` 후 61s+ 경과 → sleep 호출 안 함 + 즉시 발급."""
    from src.auth import token as token_mod

    sleep_calls: list[float] = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    monkeypatch.setattr(token_mod.asyncio, "sleep", fake_sleep)

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *_a, **_kw):
            return _make_token_response()

    monkeypatch.setattr(token_mod.httpx, "AsyncClient", lambda: _Client())

    # 첫 발급 후 100초 경과 → 두 번째 발급은 sleep 호출 안 함
    clock = _MonotonicClock(start=100.0)
    monkeypatch.setattr(token_mod.time, "monotonic", clock)

    mgr = token_mod.TokenManager()
    await mgr.issue()
    clock.advance(100.0)  # 61s 이상 — gap 충분
    await mgr.issue()

    assert sleep_calls == []  # gap 충분 → sleep 0건


@pytest.mark.asyncio
async def test_D_cache_hit_skips_issue_entirely(
    monkeypatch: pytest.MonkeyPatch,
):
    """(D) `_is_valid()=True` 면 `get_token()` 이 issue() 호출 안 함.

    캐시 hit 경로는 lock + sleep + httpx 모두 0 호출.
    """
    from src.auth import token as token_mod

    sleep_calls: list[float] = []
    httpx_calls = {"n": 0}

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    monkeypatch.setattr(token_mod.asyncio, "sleep", fake_sleep)

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *_a, **_kw):
            httpx_calls["n"] += 1
            return _make_token_response()

    monkeypatch.setattr(token_mod.httpx, "AsyncClient", lambda: _Client())

    mgr = token_mod.TokenManager()
    # 유효 토큰 시뮬레이션
    mgr.access_token = "CACHED-TOK"
    mgr.token_expired = datetime.now() + timedelta(hours=2)

    tok = await mgr.get_token()

    assert tok == "CACHED-TOK"
    assert sleep_calls == []
    assert httpx_calls["n"] == 0


@pytest.mark.asyncio
async def test_E_gather_race_serialized_with_gap(
    monkeypatch: pytest.MonkeyPatch,
):
    """(E) `asyncio.gather(mgr1.issue(), mgr2.issue())` — 직렬화 + 두 번째 sleep.

    동시 발사 시에도 lock 으로 순차 실행 보장. 두 번째는 60s gap.
    """
    from src.auth import token as token_mod

    sleep_calls: list[float] = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    monkeypatch.setattr(token_mod.asyncio, "sleep", fake_sleep)

    issue_order: list[str] = []

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *_a, **_kw):
            return _make_token_response()

    monkeypatch.setattr(token_mod.httpx, "AsyncClient", lambda: _Client())

    # 동시 race 시뮬레이션 — 시간은 고정 (lock 으로 직렬화 강제)
    # start>0 — 첫 발급 후 _LAST_ISSUE_AT 가 양수가 되어야 두 번째 호출에서 gap 체크됨
    clock = _MonotonicClock(start=100.0)
    monkeypatch.setattr(token_mod.time, "monotonic", clock)

    mgr1 = token_mod.TokenManager(label="m1")
    mgr2 = token_mod.TokenManager(label="m2")

    # 기존 issue 를 감싸서 호출 순서 기록
    original_issue = token_mod.TokenManager.issue

    async def traced_issue(self):
        issue_order.append(f"begin:{self._label}")
        await original_issue(self)
        issue_order.append(f"end:{self._label}")

    monkeypatch.setattr(token_mod.TokenManager, "issue", traced_issue)

    await asyncio.gather(mgr1.issue(), mgr2.issue())

    # 직렬화: 첫 매니저 begin/end 후 두 번째 매니저 begin/end
    assert issue_order[0].startswith("begin:")
    assert issue_order[1].startswith("end:")
    assert issue_order[2].startswith("begin:")
    assert issue_order[3].startswith("end:")
    # 첫과 두 번째가 같은 label 이 아닐 것 (분리)
    assert issue_order[0] != issue_order[2]

    # 첫 발급: _LAST_ISSUE_AT=0 → sleep 없음. 발급 후 _LAST_ISSUE_AT=100.0
    # 두 번째 발급: clock 고정 (race), gap 0초 → 61.0 - 0 = 61.0s sleep
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(61.0, rel=0.01)
