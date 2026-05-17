"""logs 라우트 계약 — /api/logs

사이클 6 (2026-05-17) — 기간 필터(from_date/to_date) + 페이징(page/size) 확장.

기존 ``?limit=50&level=ERROR`` 하위 호환은 보존 (limit/level 단독 호출도 dict 응답).
응답 ``data`` 는 ``{items, total, total_pages}`` dict.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def _logs_payload(items=None, total=None, total_pages=None):
    items = list(items or [])
    if total is None:
        total = len(items)
    if total_pages is None:
        total_pages = 1 if total else 0
    return {"items": items, "total": total, "total_pages": total_pages}


def test_logs_default_returns_dict_with_meta(contract_env):
    contract_env.state.logs = _logs_payload(
        items=[
            {
                "id": 1,
                "timestamp": "2026-05-17T10:00:00+09:00",
                "log_level": "INFO",
                "message": "ok",
            }
        ],
        total=1,
        total_pages=1,
    )
    r = contract_env.client.get("/api/logs")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "items" in body["data"]
    assert "total" in body["data"]
    assert "total_pages" in body["data"]
    assert body["data"]["total"] == 1
    assert body["data"]["total_pages"] == 1
    last = contract_env.calls.get_logs[-1]
    # 기본 size=50, page=1
    assert last["size"] == 50
    assert last["page"] == 1


def test_logs_legacy_limit_level_still_works(contract_env):
    contract_env.state.logs = _logs_payload(items=[], total=0, total_pages=0)
    r = contract_env.client.get("/api/logs?limit=20&level=ERROR")
    assert r.status_code == 200
    last = contract_env.calls.get_logs[-1]
    # limit 단독은 size 흡수
    assert last["size"] == 20
    assert last["log_level"] == "ERROR"


def test_logs_invalid_limit_returns_422(contract_env):
    r = contract_env.client.get("/api/logs?limit=300")  # le=200 위반
    assert r.status_code == 422


def test_logs_with_date_filter(contract_env):
    contract_env.state.logs = _logs_payload(items=[], total=0, total_pages=0)
    r = contract_env.client.get(
        "/api/logs?from_date=2026-05-15&to_date=2026-05-17"
    )
    assert r.status_code == 200
    last = contract_env.calls.get_logs[-1]
    # date 객체로 라우트가 변환 후 전달
    assert str(last["from_date"]) == "2026-05-15"
    assert str(last["to_date"]) == "2026-05-17"


def test_logs_with_page_size(contract_env):
    contract_env.state.logs = _logs_payload(items=[], total=0, total_pages=0)
    r = contract_env.client.get("/api/logs?page=2&size=20")
    assert r.status_code == 200
    last = contract_env.calls.get_logs[-1]
    assert last["page"] == 2
    assert last["size"] == 20


def test_logs_invalid_page_zero_returns_422(contract_env):
    r = contract_env.client.get("/api/logs?page=0")
    assert r.status_code == 422


def test_logs_invalid_size_too_large_returns_422(contract_env):
    r = contract_env.client.get("/api/logs?size=300")
    assert r.status_code == 422


def test_logs_from_after_to_returns_422(contract_env):
    r = contract_env.client.get(
        "/api/logs?from_date=2026-05-17&to_date=2026-05-15"
    )
    assert r.status_code == 422


def test_logs_response_includes_total_and_total_pages(contract_env):
    contract_env.state.logs = _logs_payload(
        items=[
            {
                "id": i,
                "timestamp": "2026-05-17T10:00:00+09:00",
                "log_level": "INFO",
                "message": f"m{i}",
            }
            for i in range(20)
        ],
        total=23,
        total_pages=2,
    )
    r = contract_env.client.get("/api/logs?page=1&size=20")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["total"] == 23
    assert body["data"]["total_pages"] == 2
    assert len(body["data"]["items"]) == 20
