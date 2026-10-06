"""트랙 C(실비용 산출) — `/api/costs/*` 라우트 (`src/routes/costs.py`).

명세 = `_workspace/design/2026-10-01_mean_reversion_handoff.md` §4.2-3·4

| # | 계약 |
|---|---|
| R1 | `POST /api/costs/reconcile?from=&to=` → `ApiResponse(success=True, data=<대사 결과>)` |
| R2 | 날짜가 `YYYY-MM-DD` 가 아니거나 from > to 거나 366일 초과 = 422(KIS 를 부르지 않는다) |
| R3 | 모의 환경(`RealEnvRequired`) = 409 · KIS 거부(`KisApiError`) = 502 · 그 밖 예외 = 500 + `[trade_cost_route_error]` |
| R4 | `GET /api/costs/summary?from=&to=&strategy=` → `build_summary(from, to, strategy)` 결과를 그대로 싣는다 |
| R5 | 요약 DB 예외 = 500(빈 결과로 위장하지 않는다) |
| R6 | 응답에 `Decimal` 이 남지 않는다(JSON 숫자) |
"""

from __future__ import annotations

import importlib
import logging
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def _route():
    return importlib.import_module("src.routes.costs")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(_route().router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def engine(monkeypatch):
    eng = importlib.import_module("src.engine.trade_cost")
    rec = AsyncMock(return_value={"kis_rows": 2, "saved_rows": 2, "pages": 1,
                                  "truncated": False, "totals_match": True, "alerts": [],
                                  "row_fee": 27.0, "row_tax": 270.0})
    summ = AsyncMock(return_value={"strategies": [{"strategy": "kojiro", "fee": 57.0,
                                                   "cost_bp": Decimal("17.33")}],
                                   "total": {"fee": 57.0}})
    monkeypatch.setattr(eng, "reconcile", rec)
    monkeypatch.setattr(eng, "build_summary", summ)
    return rec, summ


def test_r1_reconcile_ok(engine):
    rec, _ = engine
    r = _client().post("/api/costs/reconcile", params={"from": "2026-09-01", "to": "2026-09-30"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["saved_rows"] == 2
    rec.assert_awaited_once_with(date(2026, 9, 1), date(2026, 9, 30))


@pytest.mark.parametrize("params", [
    {"from": "20260901", "to": "2026-09-30"},
    {"from": "2026-09-31", "to": "2026-09-30"},
    {"from": "2026-10-01", "to": "2026-09-30"},
    {"from": "2025-01-01", "to": "2026-09-30"},
    {"to": "2026-09-30"},
])
def test_r2_bad_dates_422(engine, params):
    rec, _ = engine
    r = _client().post("/api/costs/reconcile", params=params)
    assert r.status_code == 422
    rec.assert_not_awaited()


def test_r3_vts_409(engine):
    rec, _ = engine
    tp = importlib.import_module("src.api.trade_profit")
    rec.side_effect = tp.RealEnvRequired("실전 전용")
    r = _client().post("/api/costs/reconcile", params={"from": "2026-09-01", "to": "2026-09-30"})
    assert r.status_code == 409


def test_r3b_kis_error_502(engine):
    rec, _ = engine
    from src.api.base import KisApiError

    rec.side_effect = KisApiError("1", "OPSQ0002", "없는 서비스")
    r = _client().post("/api/costs/reconcile", params={"from": "2026-09-01", "to": "2026-09-30"})
    assert r.status_code == 502
    assert "OPSQ0002" in r.text


def test_r3c_other_error_500_with_marker(engine, caplog):
    caplog.set_level(logging.DEBUG)
    rec, _ = engine
    rec.side_effect = RuntimeError("db down")
    r = _client().post("/api/costs/reconcile", params={"from": "2026-09-01", "to": "2026-09-30"})
    assert r.status_code == 500
    assert any(x.levelno >= logging.WARNING and x.getMessage().startswith("[trade_cost_route_error] ")
               for x in caplog.records)


def test_r4_summary_ok_and_r6_no_decimal(engine):
    _, summ = engine
    r = _client().get("/api/costs/summary",
                      params={"from": "2026-09-01", "to": "2026-09-30", "strategy": "kojiro"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["strategies"][0]["cost_bp"] == pytest.approx(17.33)
    assert isinstance(body["data"]["strategies"][0]["cost_bp"], float)
    summ.assert_awaited_once_with(date(2026, 9, 1), date(2026, 9, 30), "kojiro")


def test_r4b_summary_without_strategy(engine):
    _, summ = engine
    r = _client().get("/api/costs/summary", params={"from": "2026-09-01", "to": "2026-09-30"})
    assert r.status_code == 200
    summ.assert_awaited_once_with(date(2026, 9, 1), date(2026, 9, 30), None)


def test_r4c_summary_bad_dates_422(engine):
    r = _client().get("/api/costs/summary", params={"from": "2026-09-30", "to": "2026-09-01"})
    assert r.status_code == 422


def test_r5_summary_db_error_500(engine):
    _, summ = engine
    summ.side_effect = RuntimeError("db down")
    r = _client().get("/api/costs/summary", params={"from": "2026-09-01", "to": "2026-09-30"})
    assert r.status_code == 500


def test_main_includes_costs_router():
    from pathlib import Path

    src = Path("src/main.py").read_text(encoding="utf-8")
    assert "costs" in src and "app.include_router(costs.router)" in src
