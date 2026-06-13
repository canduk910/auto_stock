"""사이클 110 LOW-1 (G-EMIT1) — 사이클 89 [stock_master_bulk_refresh] emit 영역 영구 영속이.

Red 명세 (`_workspace/red/cycle110_silent_defect_fix.md`):

`_full_universe_load_once` 영역 영구 영속이 내부에서 emit 발화 (별도 chain 호출 불필요).
사이클 110 시정 영역 영구 영속이 = `_full_universe_load_once` 단일 호출 영역 영구 영속이
(emit chain 영역 영구 영속이 내장 활용).

위험 등급 LOW (운영자 가시화 영역 영구 영속이 의무).

영속 의무:
- 사이클 89 [stock_master_bulk_refresh] emit 영속 (Q27=A 자동/수동 구분 0)
- 사이클 101 영속 (`_full_universe_load_once` 영역 영구 영속이 emit 내장)
- 사이클 110 영속 (단일 호출 영역 emit chain 활용)
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason="사이클 127 fire-and-forget BackgroundTasks 전환 — 라우트가 _full_universe_load_once 직접 호출 폐기 → _run_universe_background 위임 (사이클 66 K-2 패턴)",
)
def test_g_emit1_full_universe_load_once_called_for_emit(monkeypatch):
    """G-EMIT1: `_full_universe_load_once` 호출 영역 영구 영속이 = emit 발화 영역 활용.

    사이클 89 [stock_master_bulk_refresh] emit 영역 영구 영속이 의무:
    - `_full_universe_load_once` 영역 내부에서 emit 발화 (별도 chain 호출 불필요)
    - 사이클 110 시정 영역 영구 영속이 = 단일 호출 영역 영구 영속이 (emit chain 활용)
    """
    from src.engine import scanner

    mock = AsyncMock(return_value={
        "total": 500,
        "kospi": 250,
        "kosdaq": 250,
        "securities": 480,
        "etf": 20,
        "fetched": 490,
        "skipped_ttl": 10,
        "failed": 0,
        "elapsed_ms": 60_000,
    })
    monkeypatch.setattr(scanner, "_full_universe_load_once", mock, raising=False)

    from src.main import app
    client = TestClient(app)

    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 200, (
        f"POST 200 의무 (실제 {res.status_code}) — 사이클 110 시정 영역 영구 영속이 미적용"
    )

    # `_full_universe_load_once` 영역 영구 영속이 호출 영역 = emit chain 영역 활용 의무
    assert mock.call_count == 1, (
        f"_full_universe_load_once 1회 호출 의무 (emit chain 영역 영구 영속이 활용), "
        f"실제 {mock.call_count}회"
    )

    # 응답 영역 영구 영속이 정합성 = summary 전달 영역 영구 영속이
    body = res.json()
    assert body["data"]["universe"] == 500, (
        f"universe = summary['total'] (500) 의무, 실제 {body['data']['universe']}"
    )
    assert body["data"]["fetched"] == 490, (
        f"fetched (490) 의무, 실제 {body['data']['fetched']}"
    )
