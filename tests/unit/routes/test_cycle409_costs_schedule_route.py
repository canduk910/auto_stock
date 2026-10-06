"""cycle409 — 사용자 결정 10-04 Q1: 매일 자동 대사 시각 저장 API (`src/routes/costs.py`).

| # | 계약 |
|---|---|
| H1 | `PUT /api/costs/schedule {"time":"HH:MM","days":N}` → `system_config.trade_cost_reconcile_time = {"value":"HH:MM","days":N}` 저장 |
| H2 | `HH:MM` 형식이 아니거나 루프 수명(07:45 ≤ t < 21:30) 밖이거나 `days` 가 1~31 밖 = 422 · 저장하지 않는다 |
| H3 | `{"time": null}` = 끄기 — `{"value": null}` 을 저장한다(키 삭제 아님) |
| H4 | `GET /api/costs/schedule` → 저장값을 해석해 `{enabled, time, days}` 로 낸다 · 키 없음 = enabled false |
| H5 | 저장 DB 예외 = 500 + `[trade_cost_route_error]`(조용히 성공으로 내지 않는다) |
"""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(importlib.import_module("src.routes.costs").router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def cfg(monkeypatch):
    sc = importlib.import_module("src.db.system_config")
    setter = AsyncMock(return_value=None)
    getter = AsyncMock(return_value=None)
    monkeypatch.setattr(sc, "set_trade_cost_reconcile_schedule", setter)
    monkeypatch.setattr(sc, "get_trade_cost_reconcile_schedule_raw", getter)
    return setter, getter


def test_h1_put_saves(cfg):
    setter, _ = cfg
    r = _client().put("/api/costs/schedule", json={"time": "08:30", "days": 2})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    setter.assert_awaited_once_with({"value": "08:30", "days": 2})


def test_h1_days_defaults_to_one(cfg):
    setter, _ = cfg
    r = _client().put("/api/costs/schedule", json={"time": "20:45"})
    assert r.status_code == 200
    setter.assert_awaited_once_with({"value": "20:45", "days": 1})


@pytest.mark.parametrize("body", [
    {"time": "8:30"}, {"time": "24:00"}, {"time": "08:61"}, {"time": "abc"},
    {"time": "07:44"}, {"time": "21:30"}, {"time": "22:00"},
    {"time": "08:30", "days": 0}, {"time": "08:30", "days": 32},
])
def test_h2_invalid_is_422_and_not_saved(cfg, body):
    setter, _ = cfg
    r = _client().put("/api/costs/schedule", json=body)
    assert r.status_code == 422, (body, r.text)
    setter.assert_not_awaited()


def test_h3_null_turns_off(cfg):
    setter, _ = cfg
    r = _client().put("/api/costs/schedule", json={"time": None})
    assert r.status_code == 200
    setter.assert_awaited_once_with({"value": None})


def test_h4_get_reports_parsed(cfg):
    _, getter = cfg
    getter.return_value = {"value": "08:30", "days": 3}
    r = _client().get("/api/costs/schedule")
    assert r.status_code == 200
    assert r.json()["data"] == {"enabled": True, "time": "08:30", "days": 3}


def test_h4_get_missing_is_off(cfg):
    r = _client().get("/api/costs/schedule")
    assert r.json()["data"] == {"enabled": False, "time": None, "days": None}


def test_h5_save_error_is_500(cfg, caplog):
    setter, _ = cfg
    setter.side_effect = RuntimeError("db down")
    r = _client().put("/api/costs/schedule", json={"time": "08:30"})
    assert r.status_code == 500
    assert any(rec.getMessage().startswith("[trade_cost_route_error] ")
               for rec in caplog.records if rec.levelno >= 30)
