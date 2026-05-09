"""log-reports 라우트 계약 — /api/log-reports/*"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.contract


def _make_report(target_date="2026-05-08"):
    return {
        "id": 1, "target_date": date.fromisoformat(target_date),
        "summary": "정상", "findings": [], "metrics": {},
        "model": "gpt-4", "created_at": "2026-05-08T20:15:00+09:00",
    }


def test_list_reports_with_default_days(contract_env):
    contract_env.state.log_reports = [_make_report()]
    r = contract_env.client.get("/api/log-reports")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert len(body["data"]) == 1
    # default days=30
    assert contract_env.calls.list_log_reports[-1]["days"] == 30


def test_list_reports_with_custom_days(contract_env):
    r = contract_env.client.get("/api/log-reports?days=7")
    assert r.status_code == 200
    assert contract_env.calls.list_log_reports[-1]["days"] == 7


def test_get_report_with_invalid_date_format_returns_failure(contract_env):
    r = contract_env.client.get("/api/log-reports/not-a-date")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "날짜 형식" in body["message"]


def test_get_report_when_not_found_returns_failure(contract_env):
    r = contract_env.client.get("/api/log-reports/2026-05-08")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "리포트가 없" in body["message"]


def test_get_report_when_exists_returns_data(contract_env):
    contract_env.state.log_reports = [_make_report()]
    r = contract_env.client.get("/api/log-reports/2026-05-08")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["id"] == 1


def test_run_now_when_engine_succeeds_returns_data(contract_env):
    r = contract_env.client.post("/api/log-reports/run")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "id" in body["data"]


def test_run_now_when_engine_raises_returns_failure(contract_env, monkeypatch):
    async def boom(*_args, **_kwargs):
        raise RuntimeError("OpenAI down")

    monkeypatch.setattr(
        "src.routes.log_reports.generate_daily_log_report", boom, raising=False,
    )
    r = contract_env.client.post("/api/log-reports/run")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "분석 실행 실패" in body["message"]


def test_run_now_when_engine_returns_none_then_failure_with_message(contract_env, monkeypatch):
    """이미 오늘 리포트가 있거나 OPENAI_API_KEY 미설정 시 None 반환 → success=False."""

    async def returns_none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "src.routes.log_reports.generate_daily_log_report", returns_none, raising=False,
    )
    r = contract_env.client.post("/api/log-reports/run")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "분석 결과 없음" in body["message"]
