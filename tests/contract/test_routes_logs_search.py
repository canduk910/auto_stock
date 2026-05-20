"""사이클 6 통합 Red — `/api/logs/search` 엔드포인트 계약 (검색).

요구:
A. `GET /api/logs/search?q=OPSP` → 200 + `data.logs` 배열 + total/has_more
B. `q` 누락 → 422
C. `q=""` → 422 (min_length=1)
D. `limit>1000` → 422
E. `limit=0` → 422
F. 응답 ApiResponse 래퍼 `{success, data, message}`
G. level/start/end 인자 그대로 db 함수에 전달
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def _search_payload(logs=None, total=None, has_more=False):
    logs = list(logs or [])
    if total is None:
        total = len(logs)
    return {"logs": logs, "total": total, "has_more": has_more}


@pytest.fixture
def search_env(contract_env, monkeypatch):
    """contract_env 에 search_logs fake 추가."""
    calls = contract_env.calls
    calls_search = []

    async def fake_search_logs(q, *, level=None, start=None, end=None, limit=200):
        calls_search.append({
            "q": q,
            "level": level,
            "start": start,
            "end": end,
            "limit": limit,
        })
        return contract_env.state.search or _search_payload()

    # state.search 신규 필드 (dict)
    contract_env.state.search = None
    contract_env.calls.search_logs = calls_search

    monkeypatch.setattr(
        "src.routes.logs.search_logs", fake_search_logs, raising=False
    )
    return contract_env


# ---------------------------------------------------------------------------
# A. 정상 검색
# ---------------------------------------------------------------------------


def test_search_returns_200_with_logs(search_env):
    search_env.state.search = _search_payload(
        logs=[
            {
                "id": 1,
                "timestamp": "2026-05-20T10:00:00+09:00",
                "log_level": "ERROR",
                "message": "OPSP0002 폭주",
            }
        ],
        total=1,
        has_more=False,
    )
    r = search_env.client.get("/api/logs/search?q=OPSP")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "logs" in body["data"]
    assert "total" in body["data"]
    assert "has_more" in body["data"]
    assert body["data"]["total"] == 1
    assert len(body["data"]["logs"]) == 1

    last = search_env.calls.search_logs[-1]
    assert last["q"] == "OPSP"
    assert last["limit"] == 200  # 기본


# ---------------------------------------------------------------------------
# B/C. q 누락/빈값
# ---------------------------------------------------------------------------


def test_search_q_missing_returns_422(search_env):
    r = search_env.client.get("/api/logs/search")
    assert r.status_code == 422


def test_search_q_empty_returns_422(search_env):
    r = search_env.client.get("/api/logs/search?q=")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# D/E. limit 경계
# ---------------------------------------------------------------------------


def test_search_limit_too_large_returns_422(search_env):
    r = search_env.client.get("/api/logs/search?q=x&limit=2000")
    assert r.status_code == 422


def test_search_limit_zero_returns_422(search_env):
    r = search_env.client.get("/api/logs/search?q=x&limit=0")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# F. ApiResponse 래퍼
# ---------------------------------------------------------------------------


def test_search_response_uses_api_response_wrapper(search_env):
    search_env.state.search = _search_payload()
    r = search_env.client.get("/api/logs/search?q=x")
    assert r.status_code == 200
    body = r.json()
    assert "success" in body
    assert "data" in body
    assert "message" in body


# ---------------------------------------------------------------------------
# G. level/start/end 전달
# ---------------------------------------------------------------------------


def test_search_passes_level_start_end(search_env):
    search_env.state.search = _search_payload()
    r = search_env.client.get(
        "/api/logs/search?q=foo&level=ERROR"
        "&start=2026-05-19T00:00:00%2B09:00&end=2026-05-20T23:59:59%2B09:00"
    )
    assert r.status_code == 200
    last = search_env.calls.search_logs[-1]
    assert last["q"] == "foo"
    assert last["level"] == "ERROR"
    assert last["start"] == "2026-05-19T00:00:00+09:00"
    assert last["end"] == "2026-05-20T23:59:59+09:00"
