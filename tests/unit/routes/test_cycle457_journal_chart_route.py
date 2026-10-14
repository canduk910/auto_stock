"""cycle457 — `GET /api/journal-chart`(`src/routes/journal_chart.py`). 읽기 전용.

| # | 계약 |
|---|---|
| R1 | 일봉 = `period_chart.fetch_candle_chart(ticker, "D", 5)`(모듈 참조) · 지표 = 엔진 전략 객체의 `chart_indicators` 결과 그대로 |
| R2 | 엔진에 그 전략이 없으면 캔들만 + `indicator_source="unavailable"` + 안내 |
| R3 | 지표 계산 예외 = 캔들은 그대로 · `indicator_source="error"` · `[journal_chart_error]` |
| R4 | KIS 실패 · 대기 초과 = HTTP 200 + `success=false` · 인자 위반만 422 |
| R5 | `from` 이 있으면 그 날짜 앞 150봉부터 계산(`indicator_start_index`), 없으면 마지막 260봉 |
| R6 | 응답 정리 — 길이가 봉 수와 다른 선은 버리고 NaN·inf 는 null, 모르는 pane 은 price |
| R7 | 계산은 `asyncio.to_thread` 로(이벤트 루프를 막지 않는다) · 라우트에 지표 계산식 없음 |
"""

from __future__ import annotations

import ast
import importlib
import math
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

ROUTE_SRC = Path(__file__).resolve().parents[3] / "src" / "routes" / "journal_chart.py"


def _chart(n: int):
    from src.models.candle_chart import CandleBar, CandleChart

    bars, d = [], date(2025, 1, 2)
    while len(bars) < n:
        if d.weekday() < 5:
            c = 10_000 + 7 * len(bars) + (len(bars) % 5) * 30
            bars.append(CandleBar(date=d.isoformat(), open=c - 20, high=c + 60, low=c - 70, close=c,
                                  volume=1000, amount=c * 1000))
        d += timedelta(days=1)
    return CandleChart(ticker="005930", name="삼성전자", period="D", years=5, adjusted=True, market="J",
                       start_date=bars[0].date, end_date=bars[-1].date, bars=bars, complete=True,
                       incomplete_reason=None, last_bar_provisional=False, dropped_bars=0, kis_calls=1,
                       cached=False, fetched_at="2026-10-15T06:00:00+09:00")


class _Reg:
    def __init__(self, by):
        self._by = by

    def get(self, sid):
        return self._by.get(sid)


@pytest.fixture
def wire(monkeypatch):
    pc = importlib.import_module("src.api.period_chart")
    sched = importlib.import_module("src.engine.scheduler")
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategy_base import StrategyConfig

    state = {"chart": _chart(400), "reg": {}, "calls": []}
    state["reg"]["donchian_swing"] = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="d", params={}, enabled=True))

    async def fetch(ticker, period="D", years=5, **k):
        state["calls"].append((ticker, period, years))
        if isinstance(state["chart"], Exception):
            raise state["chart"]
        return state["chart"]

    monkeypatch.setattr(pc, "fetch_candle_chart", fetch)
    monkeypatch.setattr(sched, "trading_scheduler", SimpleNamespace(registry=_Reg(state["reg"])))
    return state


def _get(params: dict, status: int = 200):
    app = FastAPI()
    app.include_router(importlib.import_module("src.routes.journal_chart").router)
    r = TestClient(app, raise_server_exceptions=False).get("/api/journal-chart", params=params)
    assert r.status_code == status, r.text
    return r.json()


def test_r1_candles_plus_strategy_indicators(wire):
    body = _get({"ticker": "005930", "strategy": "donchian_swing", "from": "2026-03-02"})
    assert body["success"] is True
    d = body["data"]
    assert wire["calls"] == [("005930", "D", 5)]
    assert len(d["bars"]) == 400 and d["strategy"] == "donchian_swing"
    assert d["indicator_source"] == "engine"
    keys = [line["key"] for line in d["indicators"]["lines"]]
    assert keys == ["ema", "donchian_high", "channel_low", "atr"]
    want = wire["reg"]["donchian_swing"].chart_indicators(d["bars"], d["indicator_start_index"])
    for k in keys:
        assert len(d["indicators"]["series"][k]) == 400
        assert d["indicators"]["series"][k][-1] == pytest.approx(round(want["series"][k][-1], 2))


def test_r2_strategy_missing(wire):
    d = _get({"ticker": "005930", "strategy": "kojiro"})["data"]
    assert d["indicator_source"] == "unavailable"
    assert d["indicators"]["lines"] == []
    assert any("엔진에 이 전략이 없어" in n for n in d["indicators"]["notes"])
    assert len(d["bars"]) == 400


def test_r3_indicator_error_keeps_candles(wire, caplog):
    class Boom:
        def chart_indicators(self, bars, start):
            raise RuntimeError("boom")

    wire["reg"]["kojiro"] = Boom()
    d = _get({"ticker": "005930", "strategy": "kojiro"})["data"]
    assert d["indicator_source"] == "error" and len(d["bars"]) == 400
    assert any("[journal_chart_error]" in r.getMessage() for r in caplog.records)


def test_r4_failures(wire):
    from src.api.base import KisApiError
    pc = importlib.import_module("src.api.period_chart")

    wire["chart"] = KisApiError("1", "EGW00123", "실패")
    body = _get({"ticker": "005930", "strategy": "donchian_swing"})
    assert body["success"] is False and body["data"] is None and "EGW00123" in body["message"]
    wire["chart"] = pc.ChartBusyError("busy")
    assert _get({"ticker": "005930", "strategy": "donchian_swing"})["success"] is False
    _get({"ticker": "12345", "strategy": "donchian_swing"}, status=422)
    _get({"ticker": "005930", "strategy": "donchian_swing", "from": "2026/03/02"}, status=422)


def test_r5_start_index(wire):
    d = _get({"ticker": "005930", "strategy": "donchian_swing", "from": "2026-03-02"})["data"]
    first = next(i for i, b in enumerate(d["bars"]) if b["date"] >= "2026-03-02")
    assert d["indicator_start_index"] == first - 150
    assert all(v is None for v in d["indicators"]["series"]["ema"][: first - 150])
    d2 = _get({"ticker": "005930", "strategy": "donchian_swing"})["data"]
    assert d2["indicator_start_index"] == 400 - 260


def test_r6_sanitize():
    m = importlib.import_module("src.routes.journal_chart")
    raw = {
        "lines": [{"key": "a", "title": "A", "pane": "weird"}, {"key": "b", "title": "B"}, {"key": "c"}],
        "series": {"a": [1.234, math.nan, math.inf], "b": [1, 2]},
        "notes": ["n"],
    }
    out = m._sanitize(raw, 3)
    assert [line["key"] for line in out["lines"]] == ["a"]
    assert out["lines"][0]["pane"] == "price"
    assert out["series"]["a"] == [1.23, None, None]


def test_r7_to_thread_and_no_formula():
    src = ROUTE_SRC.read_text(encoding="utf-8")
    assert "asyncio.to_thread(strat.chart_indicators" in src
    assert "period_chart.fetch_candle_chart(" in src
    tree = ast.parse(src)
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not called & {"sum", "min"}, called  # max 는 봉 번호 하한(0) 클램프뿐
