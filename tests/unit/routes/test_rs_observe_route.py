"""RS·재무 관찰 화면 — `GET /api/rs-observe`(`src/routes/rs_observe.py`). 읽기 전용.

| # | 계약 |
|---|---|
| O1 | `date` 없음 = 가장 최근 기록일 · 행·날짜 목록·전략 넷을 돌려준다 |
| O2 | `date`·`strategy` 를 그대로 DB 읽기에 넘긴다 |
| O3 | 기록이 하나도 없으면 `target_date=None` · 행 0 (DB 행 조회를 하지 않는다) |
| O4 | NULL 은 null 그대로(0 으로 채우지 않는다) · NaN·inf 도 null |
| O5 | 형식 위반 date · 모르는 strategy = 422 |
| O6 | DB 예외 = 200 + success=false + `[rs_observe_read_error]` |
| O7 | 전략 목록 = `rs_fundamental_observe.TARGET_STRATEGIES` · 라우트는 엔진·KIS 를 import 하지 않는다 |
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

ROUTE_SRC = Path(__file__).resolve().parents[3] / "src" / "routes" / "rs_observe.py"

ROW = {
    "target_date": "2026-10-15", "strategy_id": "kojiro", "ticker": "005930", "role": "candidate",
    "name": "삼성전자", "rs_raw": 0.12, "rs_pct": 91, "sector_key": "전기전자", "vs_sector": 0.05,
    "sector_pct": 70, "in_sector_pct": 88, "revision_breadth": None, "target_median_change": None,
    "opinion_brokers": None, "fin_quarter": "2026Q2", "op_income_q": 1.0e12, "op_income_q_yoy": 0.3,
    "op_turnaround": False, "op_yoy_growth": 0.3, "revenue_yoy_growth": float("nan"), "net_turnaround": None,
    "roe": 0.11, "debt_ratio_latest": 30.0, "debt_ratio_down_years": 2, "ttm_op_to_max_ratio": 0.8,
    "rs_population": 2400, "computed_at": "2026-10-15T07:50:00+09:00",
}


@pytest.fixture
def wire(monkeypatch):
    import src.db.candidate_scores as cs_db
    from src.routes import rs_observe

    dates = AsyncMock(return_value=["2026-10-15", "2026-10-14"])
    snap = AsyncMock(return_value=[dict(ROW)])
    monkeypatch.setattr(cs_db, "list_dates", dates)
    monkeypatch.setattr(cs_db, "list_snapshot", snap)
    app = FastAPI()
    app.include_router(rs_observe.router)
    return TestClient(app), dates, snap


def test_o1_latest_date_by_default(wire):
    client, _, snap = wire
    body = client.get("/api/rs-observe").json()
    assert body["success"] is True
    d = body["data"]
    assert d["target_date"] == "2026-10-15"
    assert d["dates"] == ["2026-10-15", "2026-10-14"]
    assert d["strategies"] == ["donchian_swing", "vcp_breakout", "kojiro", "etf_trend"]
    assert d["rows"][0]["ticker"] == "005930" and d["rows"][0]["name"] == "삼성전자"
    snap.assert_awaited_once_with("2026-10-15", None)


def test_o2_passes_date_and_strategy(wire):
    client, _, snap = wire
    client.get("/api/rs-observe", params={"date": "2026-10-14", "strategy": "vcp_breakout"})
    snap.assert_awaited_once_with("2026-10-14", "vcp_breakout")


def test_o3_no_records(wire):
    client, dates, snap = wire
    dates.return_value = []
    d = client.get("/api/rs-observe").json()["data"]
    assert d["target_date"] is None and d["rows"] == [] and d["dates"] == []
    snap.assert_not_awaited()


def test_o4_nulls_stay_null(wire):
    client, _, _ = wire
    r = client.get("/api/rs-observe").json()["data"]["rows"][0]
    assert r["revision_breadth"] is None and r["opinion_brokers"] is None and r["net_turnaround"] is None
    assert r["revenue_yoy_growth"] is None  # NaN → null
    assert r["op_turnaround"] is False and r["rs_pct"] == 91


@pytest.mark.parametrize("params", [{"date": "20261015"}, {"date": "2026-10-1"}, {"strategy": "momentum"}])
def test_o5_bad_args_422(wire, params):
    client, _, _ = wire
    assert client.get("/api/rs-observe", params=params).status_code == 422


def test_o6_db_error(wire, caplog):
    client, dates, _ = wire
    dates.side_effect = RuntimeError("pool down")
    with caplog.at_level(logging.WARNING):
        res = client.get("/api/rs-observe")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False and "조회 실패" in body["message"]
    assert any("[rs_observe_read_error]" in r.getMessage() for r in caplog.records)


def test_o7_strategies_match_engine_and_no_engine_import():
    from src.engine.rs_fundamental_observe import TARGET_STRATEGIES
    from src.routes.rs_observe import STRATEGIES

    assert tuple(STRATEGIES) == tuple(TARGET_STRATEGIES)
    tree = ast.parse(ROUTE_SRC.read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
    assert not [m for m in mods if m.startswith(("src.engine", "src.api", "src.realtime", "src.auth"))], mods
