"""cycle446 D-6(최소안) — `GET /api/system/alerts` 에 `exit_ai_runs` 오늘 실패를 더한다.

`llm_worker` 는 `system_logs` 에 쓰지 않으므로 워커 실행 자체는 `exit_ai_runs` 조회로만
드러난다. 기존 cycle434 행위(system_logs 집계)는 그대로 보존한다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.contract


def _client(monkeypatch, *, rows=None, log_raise=None, run=None, run_raise=None):
    from src.routes import system as routes_system

    async def fake_get_today_alert_logs(patterns, *, day=None):
        if log_raise is not None:
            raise log_raise
        return rows or []

    async def fake_get_today_run_status(day):
        if run_raise is not None:
            raise run_raise
        return run

    monkeypatch.setattr(routes_system, "get_today_alert_logs", fake_get_today_alert_logs, raising=False)
    monkeypatch.setattr(routes_system, "get_today_run_status", fake_get_today_run_status, raising=False)

    from src.main import app
    return TestClient(app)


def test_no_run_row_leaves_green(monkeypatch):
    client = _client(monkeypatch, rows=[], run=None)
    data = client.get("/api/system/alerts").json()["data"]
    assert data["status"] == "green"
    job = next(c for c in data["categories"] if c["key"] == "daily_job_failure")
    assert job["count"] == 0


def test_run_with_zero_failed_leaves_green(monkeypatch):
    run = {"run_date": "2026-10-14", "bar_date": "2026-10-13", "status": "done",
          "n_targets": 5, "n_ok": 5, "n_failed": 0, "n_skipped": 0, "finished_at_iso": None}
    client = _client(monkeypatch, rows=[], run=run)
    data = client.get("/api/system/alerts").json()["data"]
    assert data["status"] == "green"
    job = next(c for c in data["categories"] if c["key"] == "daily_job_failure")
    assert job["count"] == 0


def test_run_with_failures_bumps_daily_job_failure_to_yellow(monkeypatch):
    run = {"run_date": "2026-10-14", "bar_date": "2026-10-13", "status": "partial",
          "n_targets": 5, "n_ok": 3, "n_failed": 2, "n_skipped": 0,
          "finished_at_iso": "2026-10-14T08:16:00.000000+09:00"}
    client = _client(monkeypatch, rows=[], run=run)
    data = client.get("/api/system/alerts").json()["data"]
    assert data["status"] == "yellow"
    job = next(c for c in data["categories"] if c["key"] == "daily_job_failure")
    assert job["count"] == 1
    assert job["max_level"] == "WARNING"
    assert any("exit_ai_runs" in m["message"] for m in job["recent_messages"])


def test_red_from_logs_is_not_downgraded_by_exit_ai_check(monkeypatch):
    rows = [{"log_level": "ERROR", "message": "[holding_qty_unexplained] ticker=005930",
            "timestamp": "2026-10-14T09:30:00+09:00"}]
    run = {"run_date": "2026-10-14", "status": "partial", "n_failed": 1, "finished_at_iso": None}
    client = _client(monkeypatch, rows=rows, run=run)
    data = client.get("/api/system/alerts").json()["data"]
    assert data["status"] == "red"


def test_exit_ai_check_failure_is_graceful_and_keeps_log_based_result(monkeypatch):
    client = _client(monkeypatch, rows=[], run_raise=RuntimeError("db down"))
    resp = client.get("/api/system/alerts")
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "green"
