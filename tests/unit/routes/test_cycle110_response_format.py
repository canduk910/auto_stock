"""사이클 110 HIGH-3 (G-RESPONSE1) — 200 응답 영역 영구 영속이 정합성.

Red 명세 (`_workspace/red/cycle110_silent_defect_fix.md`):

사이클 110 응답 영역 영구 영속이 = ApiResponse{success=True, data={...}, message=...}.
data 영역 영구 영속이 신규 키 7종:
- universe (≡ summary["total"], 사이클 89 영역 영속 호환)
- elapsed_ms
- fetched (사이클 110 영역 신규 영역 영구 영속이)
- skipped_ttl (24h TTL idempotency 영역 영구 영속이)
- failed (사이클 88 G-REJECT 영속)
- kospi
- kosdaq

위험 등급 HIGH (응답 영역 정합성 + 운영자 가시화 영역 영구 영속이).

영속 의무:
- 사이클 101 영속 (`_full_universe_load_once` summary 9 키 영역 영구 영속이)
- 사이클 89 영속 (universe 키 영역 호환)
- 사이클 88 G-REJECT 영속 (failed 키 노출)
- 사이클 90 ApiResponse 래퍼 영속
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_full_universe_load_once(monkeypatch):
    """`_full_universe_load_once` mock 영역 영구 영속이 — 사이클 101 영역 정상 함수."""
    from src.engine import scanner

    mock = AsyncMock(return_value={
        "total": 2800,
        "kospi": 1400,
        "kosdaq": 1400,
        "securities": 2700,
        "etf": 100,
        "fetched": 2750,
        "skipped_ttl": 50,
        "failed": 0,
        "elapsed_ms": 180_000,
    })
    monkeypatch.setattr(scanner, "_full_universe_load_once", mock, raising=False)
    return mock


def test_g_response1_returns_api_response_envelope(mock_full_universe_load_once):
    """G-RESPONSE1: ApiResponse 래퍼 영역 영구 영속이 정합성.

    사이클 90 영속: response_model=ApiResponse + return ApiResponse(...).
    """
    from src.main import app
    client = TestClient(app)

    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 200, (
        f"POST 200 의무 (실제 {res.status_code}, body={res.text[:200]})"
    )

    body = res.json()
    assert "success" in body, "ApiResponse `success` 필드 영구 영속이 누락"
    assert "data" in body, "ApiResponse `data` 필드 영구 영속이 누락"
    assert "message" in body, "ApiResponse `message` 필드 영구 영속이 누락"
    assert body["success"] is True, f"success=True 의무 (실제 {body['success']})"


@pytest.mark.xfail(
    strict=False,
    reason="사이클 127 fire-and-forget BackgroundTasks 전환 — 동기 7키 응답 schema 폐기 → {status, task_key} 의미 전환 (사이클 66 K-2 패턴)",
)
def test_g_response1_data_contains_7_keys(mock_full_universe_load_once):
    """G-RESPONSE1-bis: data 영역 영구 영속이 7 키 정합성.

    사이클 110 영역 영구 영속이 신규 영역:
    - universe (사이클 89 호환 영속)
    - elapsed_ms
    - fetched (신규 영역)
    - skipped_ttl (24h TTL idempotency 영역)
    - failed (사이클 88 G-REJECT 영속)
    - kospi
    - kosdaq
    """
    from src.main import app
    client = TestClient(app)

    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 200

    data = res.json()["data"]
    assert isinstance(data, dict), f"data 가 dict 의무 (실제 {type(data).__name__})"

    required_keys = {"universe", "elapsed_ms", "fetched", "skipped_ttl", "failed", "kospi", "kosdaq"}
    missing = required_keys - set(data.keys())
    assert not missing, f"data 영역 영구 영속이 키 누락: {missing}"

    # 사이클 110 영역 영구 영속이 값 검증
    assert data["universe"] == 2800, f"universe = total (2800) 의무, 실제 {data['universe']}"
    assert data["fetched"] == 2750, f"fetched (2750) 의무, 실제 {data['fetched']}"
    assert data["skipped_ttl"] == 50, f"skipped_ttl (50) 의무, 실제 {data['skipped_ttl']}"
    assert data["failed"] == 0, f"failed (0) 의무, 실제 {data['failed']}"
    assert data["kospi"] == 1400, f"kospi (1400) 의무, 실제 {data['kospi']}"
    assert data["kosdaq"] == 1400, f"kosdaq (1400) 의무, 실제 {data['kosdaq']}"
    assert isinstance(data["elapsed_ms"], int), (
        f"elapsed_ms int 의무 (실제 {type(data['elapsed_ms']).__name__})"
    )
    assert data["elapsed_ms"] >= 0, f"elapsed_ms >= 0 의무 (실제 {data['elapsed_ms']})"


@pytest.mark.xfail(
    strict=False,
    reason="사이클 127 fire-and-forget BackgroundTasks 전환 — 동기 summary message 폐기 → 시작 안내 의미 전환 (사이클 66 K-2 패턴)",
)
def test_g_response1_message_includes_summary_stats(mock_full_universe_load_once):
    """G-RESPONSE1-tris: message 영역 영구 영속이 summary 통계 포함.

    사이클 110 message 영역 영구 영속이:
    "universe N ticker 즉시 적재 완료 (fetched=K, skipped_ttl=L, failed=M)"
    """
    from src.main import app
    client = TestClient(app)

    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 200

    message = res.json()["message"]
    assert "2800" in message, f"message 영역 영구 영속이 total (2800) 누락: {message}"
    assert "fetched=2750" in message, f"message 영역 영구 영속이 fetched (2750) 누락: {message}"
    assert "skipped_ttl=50" in message, f"message 영역 영구 영속이 skipped_ttl (50) 누락: {message}"
    assert "failed=0" in message, f"message 영역 영구 영속이 failed (0) 누락: {message}"
