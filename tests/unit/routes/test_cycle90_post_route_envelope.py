"""사이클 90 H-1 (HIGH) — POST /refresh-universe ApiResponse 정합.

Red 명세 (`_workspace/red/cycle90_manual_refresh_universe_api.md`):

backend-dev Green 단계 `src/routes/stock_master.py` 신규 POST 라우트
`refresh-universe` 가 ApiResponse 래퍼 의무 (`success`/`data`/`message`).
응답 data 는 `{universe: int, elapsed_ms: int}` 의 두 키 의무.

위험 등급 HIGH (사이클 65 답습 영속 + 프론트 사이클 90 H-5 연동 정합성).

영속 의무:
- 사이클 84 Q9=B (READ-ONLY GET only) 원칙 의미 영속 (POST 1개 예외 허용)
- 사이클 89 [stock_master_bulk_refresh] emit 영속 (Q27=A 자동/수동 구분 0)
- 사이클 38 명문화 영속 (tradable_boards 매수 진입 전용, 영역 무관)
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client(monkeypatch):
    """fetch_top_500_universe mock — 사이클 89 영속 영역 격리."""
    from src.engine import scanner

    monkeypatch.setattr(
        scanner,
        "fetch_top_500_universe",
        AsyncMock(return_value=["005930", "402340", "035720"]),
        raising=False,
    )

    from src.main import app
    return TestClient(app)


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q69=B — `fetch_top_500_universe` 영구 폐기 "
        "(POST /refresh-universe 라우트 대상 함수). "
        "사이클 90 시점 ApiResponse 래퍼 정합 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_h1_post_refresh_universe_returns_api_response_envelope(client):
    """H-1: POST `/api/stock-master/refresh-universe` 가 ApiResponse 래퍼 응답.

    backend-dev Green 단계 라우트 작성 시 `response_model=ApiResponse[dict]` +
    `return ApiResponse(...)` 의무. universe + elapsed_ms 두 키 의무.
    """
    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 200, (
        f"POST refresh-universe 200 의무 (실제 {res.status_code}, body={res.text[:200]}) — "
        "backend-dev Green 단계 `src/routes/stock_master.py` POST 라우트 미작성"
    )
    body = res.json()
    assert "success" in body, "ApiResponse `success` 필드 누락"
    assert "data" in body, "ApiResponse `data` 필드 누락"
    assert body["success"] is True, f"success=True 의무 (실제 {body['success']})"

    # 사이클 89 영속: data 는 {universe: int, elapsed_ms: int}
    data = body["data"]
    assert isinstance(data, dict), f"data 가 dict 의무 (실제 {type(data).__name__})"
    assert "universe" in data, "data.universe 키 누락 (3 ticker mock = 3 의무)"
    assert "elapsed_ms" in data, "data.elapsed_ms 키 누락"
    assert data["universe"] == 3, (
        f"universe = mock 결과 ticker 수 (3) 의무, 실제 {data['universe']}"
    )
    assert isinstance(data["elapsed_ms"], int), (
        f"elapsed_ms int 의무 (실제 {type(data['elapsed_ms']).__name__})"
    )
    assert data["elapsed_ms"] >= 0, (
        f"elapsed_ms >= 0 의무 (실제 {data['elapsed_ms']})"
    )
