"""사이클 110 MEDIUM-1 (G-LOCK1) — asyncio.Lock 영역 영구 영속이 영속.

Red 명세 (`_workspace/red/cycle110_silent_defect_fix.md`):

사이클 90 영역 영구 영속이 의무 (Q25=A 영속) = 동시 호출 시 두 번째 호출 즉시 409 Conflict.
사이클 110 시정 영역 영구 영속이 = `_full_universe_load_once` 단일 호출 영역 (lock 영역 영구 영속이
유지 의무).

위험 등급 MEDIUM (KIS Rate Limit 폭주 차단 영역 + 사이클 90 영속 의무).

영속 의무:
- 사이클 90 Q25=A 영속 (단일 in-flight 가드 영역 영구 영속이)
- 사이클 110 영속 (`_full_universe_load_once` 영역 단일 호출 lock 영역 유지)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def test_g_lock1_concurrent_call_returns_409(monkeypatch):
    """G-LOCK1: 동시 호출 시 두 번째 호출 즉시 409 Conflict 영역 영구 영속이.

    사이클 90 영역 영구 영속이 Q25=A 영속 = `_refresh_universe_lock.locked()` 검사 영역.
    """
    from src.engine import scanner

    # `_full_universe_load_once` 영역 영구 영속이 느린 mock (lock 점유 영역 시뮬레이션)
    async def slow_load():
        await asyncio.sleep(0.1)
        return {
            "total": 100, "kospi": 50, "kosdaq": 50,
            "securities": 100, "etf": 0,
            "fetched": 100, "skipped_ttl": 0, "failed": 0,
            "elapsed_ms": 100,
        }

    monkeypatch.setattr(scanner, "_full_universe_load_once", slow_load, raising=False)

    # 라우트 모듈 영역 영구 영속이 lock 영역 강제 활성화
    from src.routes import stock_master as routes_sm

    # `_refresh_universe_lock` 영역 영구 영속이 locked 상태 시뮬레이션
    async def acquire_lock():
        await routes_sm._refresh_universe_lock.acquire()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(acquire_lock())

        from src.main import app
        client = TestClient(app)

        # lock 영역 영구 영속이 점유 중 → 두 번째 호출 즉시 409
        res = client.post("/api/stock-master/refresh-universe")
        assert res.status_code == 409, (
            f"동시 호출 시 409 Conflict 의무 (실제 {res.status_code}) — "
            "사이클 90 Q25=A 영속 의무 위반 (단일 in-flight 가드 영역 영구 영속이)"
        )
        body = res.json()
        assert "잠시 후 재시도" in body.get("detail", ""), (
            f"409 detail 영역 영구 영속이 메시지 누락: {body}"
        )
    finally:
        routes_sm._refresh_universe_lock.release()
        loop.close()
