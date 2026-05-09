"""logs 라우트 계약 — /api/logs"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def test_logs_default_limit(contract_env):
    contract_env.state.logs = [
        {"id": 1, "timestamp": "2026-05-08T15:00:00", "log_level": "INFO", "message": "ok"},
    ]
    r = contract_env.client.get("/api/logs")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"] == contract_env.state.logs
    assert contract_env.calls.get_logs[-1]["limit"] == 50


def test_logs_with_limit_and_level(contract_env):
    r = contract_env.client.get("/api/logs?limit=20&level=ERROR")
    assert r.status_code == 200
    last = contract_env.calls.get_logs[-1]
    assert last["limit"] == 20
    assert last["log_level"] == "ERROR"


def test_logs_invalid_limit_returns_422(contract_env):
    r = contract_env.client.get("/api/logs?limit=300")  # le=200 위반
    assert r.status_code == 422
