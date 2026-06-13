"""사이클 110 MEDIUM-2 (G-EXC1) — graceful Exception → HTTPException 500.

Red 명세 (`_workspace/red/cycle110_silent_defect_fix.md`):

`_full_universe_load_once` 영역 영구 영속이 Exception 발생 시 → HTTPException 500.
사이클 102 G-REJECT 영속 (양 agent 일치, 매수/매도/익일청산 hot path 보존).

위험 등급 MEDIUM (graceful 영역 영구 영속이 + 운영자 정확한 에러 메시지 영역).

영속 의무:
- 사이클 102 G-REJECT 영속 (매수/매도 hot path 영역 보존)
- 사이클 90 graceful 영속 (Exception → 500 + detail 전달)
- 사이클 88 G-REJECT 영속 (재구독 영역 폐기 금지)
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason="사이클 127 fire-and-forget BackgroundTasks 전환 — 라우트가 _full_universe_load_once 동기 호출 폐기 → 예외는 background task 내부에서 graceful + finish_progress('failed') (사이클 66 K-2 패턴)",
)
def test_g_exc1_runtime_error_returns_500(monkeypatch):
    """G-EXC1: RuntimeError 발생 시 HTTPException 500 + detail 전달.

    사이클 110 영역 영구 영속이 시정 = `_full_universe_load_once` 영역 raise → except → 500.
    """
    from src.engine import scanner

    monkeypatch.setattr(
        scanner,
        "_full_universe_load_once",
        AsyncMock(side_effect=RuntimeError("KIS API 일시 결함")),
        raising=False,
    )

    from src.main import app
    client = TestClient(app)

    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 500, (
        f"RuntimeError → 500 의무 (실제 {res.status_code}, body={res.text[:200]}) — "
        "사이클 110 시정 영역 영구 영속이 graceful 영역 위반"
    )

    body = res.json()
    assert "KIS API 일시 결함" in body.get("detail", ""), (
        f"500 detail 영역 영구 영속이 원인 메시지 전달 의무, 실제 {body}"
    )


@pytest.mark.xfail(
    strict=False,
    reason="사이클 127 fire-and-forget BackgroundTasks 전환 — 동기 응답 schema/Lock 의미 폐기 (사이클 66 K-2 패턴)",
)
def test_g_exc1_value_error_returns_500(monkeypatch):
    """G-EXC1-bis: ValueError 발생 시 HTTPException 500 (다양한 Exception 타입 영역 영구 영속이)."""
    from src.engine import scanner

    monkeypatch.setattr(
        scanner,
        "_full_universe_load_once",
        AsyncMock(side_effect=ValueError("market_cap 응답 형식 오류")),
        raising=False,
    )

    from src.main import app
    client = TestClient(app)

    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 500, (
        f"ValueError → 500 의무 (실제 {res.status_code}) — graceful 영역 영구 영속이 위반"
    )
