"""사이클 129 — POST /master/refresh 라우트 Red 회귀 가드.

배경:
- 사이클 127 fire-and-forget BackgroundTasks 패턴 100% 답습
- 사이클 128 envelope 응답 영속 (GET /list 영향 0)
- refresh_progress TaskKey 4 확장 (universe / basics / daily / master)

회귀 가드 4 케이스:
- G-RT1: POST /master/refresh BackgroundTasks fire-and-forget 영역
- G-RT2: 409 Conflict (running 영역)
- G-RT3: 응답 schema {status: "started", task_key: "master"} (사이클 128 envelope)
- G-RT4: refresh_progress TaskKey 4 확장 (universe / basics / daily / master)
"""
from __future__ import annotations

import pytest
from fastapi import BackgroundTasks, HTTPException

from src.engine import refresh_progress as _rp
from src.models.response import ApiResponse


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """격리 — state 초기화 + 백그라운드 함수 mock."""
    _rp.reset_all_progress()

    async def _noop(*_args, **_kwargs):
        return None

    # _run_master_background mock (실제 KIS 호출 차단)
    try:
        monkeypatch.setattr(
            "src.routes.stock_master._run_master_background", _noop, raising=False
        )
    except AttributeError:
        pass

    yield
    _rp.reset_all_progress()


@pytest.mark.asyncio
async def test_g_rt1_master_route_background_task():
    """G-RT1: POST /master/refresh 즉시 ApiResponse + BackgroundTasks 등록."""
    from src.routes.stock_master import refresh_master_now

    bt = BackgroundTasks()
    resp = await refresh_master_now(bt, force=True)

    assert isinstance(resp, ApiResponse), (
        "G-RT1: ApiResponse 래퍼 영역 위반"
    )
    assert resp.success is True, "G-RT1: success=True 영역 위반"
    assert len(bt.tasks) == 1, (
        f"G-RT1: BackgroundTasks 등록 영역 위반 (실제 {len(bt.tasks)})"
    )


@pytest.mark.asyncio
async def test_g_rt2_master_route_409_when_running():
    """G-RT2: running 중 두 번째 POST → HTTPException 409."""
    from src.routes.stock_master import refresh_master_now

    _rp.start_progress("master", total=100)

    bt = BackgroundTasks()
    with pytest.raises(HTTPException) as exc_info:
        await refresh_master_now(bt, force=True)
    assert exc_info.value.status_code == 409, (
        f"G-RT2: 409 Conflict 영역 위반 (실제 {exc_info.value.status_code})"
    )


@pytest.mark.asyncio
async def test_g_rt3_master_response_schema():
    """G-RT3: 응답 schema {status: "started", task_key: "master"} (사이클 128 envelope)."""
    from src.routes.stock_master import refresh_master_now

    bt = BackgroundTasks()
    resp = await refresh_master_now(bt, force=True)

    assert resp.data["status"] == "started", (
        f"G-RT3: status=\"started\" 영역 위반 (실제 {resp.data.get('status')!r})"
    )
    assert resp.data["task_key"] == "master", (
        f"G-RT3: task_key=\"master\" 영역 위반 (실제 {resp.data.get('task_key')!r})"
    )


def test_g_rt4_refresh_progress_taskkey_extended():
    """G-RT4: refresh_progress TaskKey 4 확장 (universe / basics / daily / master).

    사이클 127 L34 Literal + L37 tuple 2 위치 동행 영속 의무.
    """
    # TaskKey Literal 영역 검증
    assert "master" in _rp.TASK_KEYS, (
        f"G-RT4: TASK_KEYS tuple 'master' 영역 부재 "
        f"(실제 {_rp.TASK_KEYS!r})"
    )
    assert len(_rp.TASK_KEYS) == 4, (
        f"G-RT4: TASK_KEYS 4 확장 위반 (실제 길이 {len(_rp.TASK_KEYS)})"
    )

    # master state 초기화 영역 영속
    state = _rp.get_progress("master")
    assert state["status"] == "idle", (
        f"G-RT4: master 초기 status='idle' 영역 위반 (실제 {state['status']!r})"
    )
