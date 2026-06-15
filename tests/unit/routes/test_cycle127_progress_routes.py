"""사이클 127 — fire-and-forget POST 라우트 + GET /refresh-progress 회귀 가드.

배경: 사이클 126 push 후 사용자 보고 = "기본정보 새로고침" 클릭 → 13분 39초 후
"KIS API 일시 결함" 토스트. axios 디폴트 timeout silent 결함.
시정: 3 POST 라우트 fire-and-forget (FastAPI BackgroundTasks) + GET /refresh-progress 5초 폴링.

검증 패턴: TestClient 의존을 폐기하고 라우트 함수를 직접 await 호출.
이유: TestClient + anyio portal thread + BackgroundTasks 환경에서 event loop hang
silent 결함 발생 (사이클 127 초기 시정 시점에 902초 timeout 검출).
라우트 본체는 production 환경에서 정상 작동 — 검증 영역만 단순화.

회귀 가드 영역:
- G-ROUTE-U1~U4: universe 라우트 (started 응답 / 409 / background task 등록 / 응답 즉시)
- G-ROUTE-B1~B4: basics 동일
- G-ROUTE-D1~D4: daily 동일
- G-ROUTE-GET1~2: 3 작업 통합 응답 + 10 키 schema + idle 디폴트
"""
from __future__ import annotations

import time

import pytest
from fastapi import BackgroundTasks, HTTPException

from src.engine import refresh_progress as _rp
from src.models.response import ApiResponse
from src.routes.stock_master import (
    get_refresh_progress,
    refresh_basics_now,
    refresh_daily_now,
    refresh_universe_now,
)


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """모든 사이클 127 라우트 테스트 격리 — 사이클 131 의미 전환 영속.

    1) refresh_progress state 전수 초기화 (before + after)
    2) **사이클 131 카드 #22 의미 전환**: `_run_*_background` 3 헬퍼 폐기 후
       `_resolve_once_callable` 헬퍼 monkeypatch 로 영역 전환.
       헬퍼 추출 후 BackgroundTasks 가 dispatch → runner → once_callable chain 호출 영역.
       once_callable 영역만 mock 하면 실제 KIS 호출 영구 차단 영속.

    영속 의무 매트릭스:
    - 사이클 127 fire-and-forget BackgroundTasks 영속
    - 사이클 131 dispatch 헬퍼 영속
    - TestClient 의존 폐기 + 라우트 함수 직접 await 호출 영속 (anyio portal hang 차단)
    """
    _rp.reset_all_progress()

    async def _noop(*_args, **_kwargs):
        return {"status": "ok"}

    # 사이클 131 의미 전환 — `_resolve_once_callable` 헬퍼 영역 monkeypatch.
    # dispatch → runner → once_callable chain 에서 once_callable 직접 차단.
    def _resolve_noop(task_key: str):
        return _noop

    monkeypatch.setattr("src.routes.stock_master._resolve_once_callable", _resolve_noop)
    yield
    _rp.reset_all_progress()


# ==================== universe 라우트 ====================


@pytest.mark.asyncio
async def test_g_route_u1_universe_post_returns_started():
    """G-ROUTE-U1: POST /refresh-universe 즉시 ApiResponse + status="started" + task_key."""
    bt = BackgroundTasks()
    resp = await refresh_universe_now(bt, force=True)

    assert isinstance(resp, ApiResponse)
    assert resp.success is True
    assert resp.data["status"] == "started"
    assert resp.data["task_key"] == "universe"
    assert "refresh-progress" in resp.message


@pytest.mark.asyncio
async def test_g_route_u2_universe_409_when_running():
    """G-ROUTE-U2: running 중 두 번째 POST → HTTPException 409."""
    _rp.start_progress("universe", total=100)
    bt = BackgroundTasks()
    with pytest.raises(HTTPException) as exc_info:
        await refresh_universe_now(bt, force=True)
    assert exc_info.value.status_code == 409
    assert "진행 중" in exc_info.value.detail


@pytest.mark.asyncio
async def test_g_route_u3_universe_background_task_registered():
    """G-ROUTE-U3: BackgroundTasks 에 task 등록 영속."""
    bt = BackgroundTasks()
    await refresh_universe_now(bt, force=True)
    assert len(bt.tasks) == 1, "background task 등록 누락 — fire-and-forget 위반"


@pytest.mark.asyncio
async def test_g_route_u4_universe_returns_quickly():
    """G-ROUTE-U4: 응답 즉시 반환 (≤2초) — fire-and-forget 의무."""
    bt = BackgroundTasks()
    start = time.monotonic()
    await refresh_universe_now(bt, force=True)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"라우트 응답 지연 {elapsed:.2f}s — fire-and-forget 위반"


# ==================== basics 라우트 ====================


@pytest.mark.asyncio
async def test_g_route_b1_basics_post_returns_started():
    """G-ROUTE-B1: POST /basics/refresh 즉시 ApiResponse + status="started"."""
    bt = BackgroundTasks()
    resp = await refresh_basics_now(bt, force=True)
    assert resp.success is True
    assert resp.data["status"] == "started"
    assert resp.data["task_key"] == "basics"


@pytest.mark.asyncio
async def test_g_route_b2_basics_409_when_running():
    """G-ROUTE-B2: basics running 중 → HTTPException 409."""
    _rp.start_progress("basics", total=100)
    bt = BackgroundTasks()
    with pytest.raises(HTTPException) as exc_info:
        await refresh_basics_now(bt, force=True)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_g_route_b3_basics_background_task_registered():
    """G-ROUTE-B3: basics BackgroundTasks 등록."""
    bt = BackgroundTasks()
    await refresh_basics_now(bt, force=True)
    assert len(bt.tasks) == 1


@pytest.mark.asyncio
async def test_g_route_b4_basics_returns_quickly():
    """G-ROUTE-B4: basics 응답 즉시 반환 (≤2초)."""
    bt = BackgroundTasks()
    start = time.monotonic()
    await refresh_basics_now(bt, force=True)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0


# ==================== daily 라우트 ====================


@pytest.mark.asyncio
async def test_g_route_d1_daily_post_returns_started():
    """G-ROUTE-D1: POST /daily/refresh 즉시 ApiResponse + status="started"."""
    bt = BackgroundTasks()
    resp = await refresh_daily_now(bt, force=True)
    assert resp.success is True
    assert resp.data["status"] == "started"
    assert resp.data["task_key"] == "daily"


@pytest.mark.asyncio
async def test_g_route_d2_daily_409_when_running():
    """G-ROUTE-D2: daily running 중 → HTTPException 409."""
    _rp.start_progress("daily", total=100)
    bt = BackgroundTasks()
    with pytest.raises(HTTPException) as exc_info:
        await refresh_daily_now(bt, force=True)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_g_route_d3_daily_background_task_registered():
    """G-ROUTE-D3: daily BackgroundTasks 등록."""
    bt = BackgroundTasks()
    await refresh_daily_now(bt, force=True)
    assert len(bt.tasks) == 1


@pytest.mark.asyncio
async def test_g_route_d4_daily_returns_quickly():
    """G-ROUTE-D4: daily 응답 즉시 반환 (≤2초)."""
    bt = BackgroundTasks()
    start = time.monotonic()
    await refresh_daily_now(bt, force=True)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0


# ==================== GET /refresh-progress ====================


@pytest.mark.asyncio
async def test_g_route_get1_refresh_progress_schema():
    """G-ROUTE-GET1: 4 작업 통합 응답 + 10 키 schema (사이클 129 master 영역 자동 흡수)."""
    _rp.start_progress("universe", total=2700)
    _rp.update_progress("universe", processed=500, updated=450, skipped=30, failed=20)

    resp = await get_refresh_progress()
    assert resp.success is True
    data = resp.data

    # 사이클 129 Q10 hotfix — TASK_KEYS 사용으로 4 작업 자동 흡수
    assert set(data.keys()) == set(_rp.TASK_KEYS)

    # 각 작업 10 키 schema
    expected_keys = {
        "status",
        "total",
        "processed",
        "updated",
        "skipped",
        "failed",
        "started_at",
        "finished_at",
        "elapsed_ms",
        "error_message",
    }
    for task_key in ("universe", "basics", "daily"):
        assert set(data[task_key].keys()) == expected_keys

    # universe 갱신 반영
    assert data["universe"]["status"] == "running"
    assert data["universe"]["total"] == 2700
    assert data["universe"]["processed"] == 500


@pytest.mark.asyncio
async def test_g_route_get2_refresh_progress_idle_default():
    """G-ROUTE-GET2: state 빈 시 idle 디폴트 graceful."""
    resp = await get_refresh_progress()
    assert resp.success is True
    data = resp.data
    for task_key in ("universe", "basics", "daily"):
        assert data[task_key]["status"] == "idle"
        assert data[task_key]["total"] == 0
        assert data[task_key]["error_message"] is None
