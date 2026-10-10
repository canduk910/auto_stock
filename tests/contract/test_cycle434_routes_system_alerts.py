"""사이클 434 — `GET /api/system/alerts` 라우트 계약.

대시보드 경고등. 오늘(KST) `system_logs` WARNING 이상 중 명부 패턴에 걸리는 행을
범주별로 집계해 돌려준다. DB 조회 실패는 `success=False`/500 이 아니라
`success=True` + `data.status="unknown"`(「모름」과 「없음」 구분, 라우트는 절대
크래시하지 않는다).

요구 행위:
- CR-1: 매칭 행 0건 → `status="green"`, 3범주 모두 count=0.
- CR-2: red 범주 매칭 1건 → `status="red"`.
- CR-3: DB 조회 예외 → 200 + `success=True` + `data.status="unknown"`.
- CR-4: 인증은 기존 미들웨어 그대로(라우트 자체 인증 분기 없음 — `tests/conftest.py`
        가 중립화하므로 이 테스트는 헤더 없이도 통과한다).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


def _client(monkeypatch, *, rows=None, raise_exc=None):
    from src.routes import system as routes_system

    async def fake_get_today_alert_logs(patterns, *, day=None):
        if raise_exc is not None:
            raise raise_exc
        return rows or []

    monkeypatch.setattr(
        routes_system, "get_today_alert_logs", fake_get_today_alert_logs, raising=False,
    )

    from src.main import app
    return TestClient(app)


def test_CR1_no_matches_is_green(monkeypatch):
    client = _client(monkeypatch, rows=[])
    resp = client.get("/api/system/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "green"
    assert len(data["categories"]) == 3
    for c in data["categories"]:
        assert c["count"] == 0


def test_CR2_ledger_mismatch_row_is_red(monkeypatch):
    rows = [
        {
            "log_level": "ERROR",
            "message": "[holding_qty_unexplained] ticker=005930 tracked=10 kis=8 delta=-2",
            "timestamp": "2026-10-10T09:30:00+09:00",
        }
    ]
    client = _client(monkeypatch, rows=rows)
    resp = client.get("/api/system/alerts")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "red"
    by_key = {c["key"]: c for c in data["categories"]}
    assert by_key["ledger_mismatch"]["count"] == 1
    assert by_key["ledger_mismatch"]["max_level"] == "ERROR"
    assert by_key["ledger_mismatch"]["first_at"] == "2026-10-10T09:30:00+09:00"
    assert by_key["ledger_mismatch"]["last_at"] == "2026-10-10T09:30:00+09:00"
    assert len(by_key["ledger_mismatch"]["recent_messages"]) == 1


def test_CR3_db_failure_is_unknown_not_green(monkeypatch):
    client = _client(monkeypatch, raise_exc=RuntimeError("db down"))
    resp = client.get("/api/system/alerts")
    assert resp.status_code == 200, "DB 실패도 크래시하지 않고 200 이어야 한다"
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "unknown"
    for c in data["categories"]:
        assert c["count"] is None


def test_CR4_response_has_as_of(monkeypatch):
    client = _client(monkeypatch, rows=[])
    resp = client.get("/api/system/alerts")
    data = resp.json()["data"]
    assert "as_of" in data and data["as_of"]
