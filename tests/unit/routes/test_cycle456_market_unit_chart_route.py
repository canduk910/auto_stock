"""cycle456 — `GET /api/market-unit/chart`(`src/routes/market_unit_chart.py`). 읽기 전용.

| # | 계약 |
|---|---|
| C1 | 시장마다(코스피 `0001` · 코스닥 `1001`) `domestic_index.get_recent_bars(code, limit=200)` 로 읽고, 오늘(KST) 봉은 쓰지 않는다 |
| C2 | 봉마다 `sma60` = 그 봉까지 60개 종가 평균 · 판정(state·m) = 운영 `market_unit.classify(그 봉까지 종가)` 그대로 · 80봉 미만 = null |
| C3 | 최근 `CHART_BARS`(120) 봉만 · 시가·고가·저가는 저장된 값 그대로(없으면 null) |
| C4 | `decision` = 운영 로더 `compute_snapshot(오늘, market=)` 결과 |
| C5 | `engine` = 엔진 메모리 오늘 스냅샷 · 없으면 null · `effective` = 결측 대체 규칙(제 시장 → 다른 시장 → 1) |
| C6 | `modes` = 축소 대상 전략마다 `market_unit_mode`(정규화) · 미등록 = null |
"""

from __future__ import annotations

import importlib
import math
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

TODAY = date(2026, 10, 15)


def _weekdays_before(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def _bars(n: int, base: float, *, with_today: bool = True, ohlc: bool = True) -> list[dict]:
    dates = _weekdays_before(date(2026, 10, 14), n)
    out = []
    for i, d in enumerate(dates):
        c = round(base * math.exp(0.12 * math.sin(i / 11) + 0.01 * math.sin(i * 1.7)), 2)
        out.append({"bas_dd": d, "close": c,
                    "open": c * 0.99 if ohlc else None, "high": c * 1.01 if ohlc else None,
                    "low": c * 0.98 if ohlc else None})
    if with_today:
        out.append({"bas_dd": TODAY, "close": 1.0, "open": None, "high": None, "low": None})
    return out


def _snap(market, *, ok=True, m=0.5, state="down_rising"):
    mu = importlib.import_module("src.engine.market_unit")
    return mu.Snapshot(
        as_of=TODAY, preview=False, ok=ok, state=state if ok else "unavailable", m=m if ok else 1.0,
        reason="ok" if ok else "rows_short", bar_date=date(2026, 10, 14) if ok else None,
        expected_head=date(2026, 10, 14), rows=200, close=100.0 if ok else None, sma60=99.0 if ok else None,
        sma60_prev=98.0 if ok else None, above=True if ok else None, rising=True if ok else None, market=market,
    )


class _Strat:
    def __init__(self, params, snaps_kospi=None, snaps_kq=None):
        self.config = SimpleNamespace(params=params)
        self._k = snaps_kospi or {}
        self._q = snaps_kq or {}

    def _market_unit_snaps_of(self, market):
        return self._q if market == "kosdaq" else self._k


class _Reg:
    def __init__(self, by_sid):
        self._s = by_sid

    def get(self, sid):
        return self._s.get(sid)


@pytest.fixture
def wire(monkeypatch):
    kst = importlib.import_module("src.db._kst")
    di = importlib.import_module("src.db.domestic_index")
    mu = importlib.import_module("src.engine.market_unit")
    sched = importlib.import_module("src.engine.scheduler")
    monkeypatch.setattr(kst, "today_kst", lambda: TODAY)
    state = {"bars": {"0001": _bars(200, 2500.0), "1001": _bars(200, 800.0)}, "calls": [],
             "snap_calls": [], "reg": {}}

    async def get_recent_bars(code, *, limit):
        state["calls"].append((code, limit))
        return list(state["bars"].get(code, []))

    async def compute_snapshot(as_of, *, preview, market="kospi"):
        state["snap_calls"].append((as_of, market))
        return _snap(market, m=0.75 if market == "kosdaq" else 0.0,
                     state="up_falling" if market == "kosdaq" else "down_falling")

    monkeypatch.setattr(di, "get_recent_bars", get_recent_bars)
    monkeypatch.setattr(mu, "compute_snapshot", compute_snapshot)
    monkeypatch.setattr(sched, "trading_scheduler", SimpleNamespace(registry=_Reg(state["reg"])))
    return state


def _get():
    app = FastAPI()
    app.include_router(importlib.import_module("src.routes.market_unit_chart").router)
    r = TestClient(app, raise_server_exceptions=False).get("/api/market-unit/chart")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True, body
    return body["data"]


def test_c1_reads_both_index_codes_and_drops_today(wire):
    d = _get()
    assert sorted(wire["calls"]) == [("0001", 200), ("1001", 200)]
    for mk in ("kospi", "kosdaq"):
        bars = d["markets"][mk]["bars"]
        assert bars[-1]["date"] == "2026-10-14"
        assert all(b["date"] != TODAY.isoformat() for b in bars)
    assert d["markets"]["kospi"]["index_code"] == "0001"
    assert d["markets"]["kosdaq"]["index_code"] == "1001"


def test_c2_per_bar_sma60_and_classify_match_operational(wire):
    mu = importlib.import_module("src.engine.market_unit")
    d = _get()
    src = [b for b in wire["bars"]["0001"] if b["bas_dd"] < TODAY]
    closes = [b["close"] for b in src]
    bars = d["markets"]["kospi"]["bars"]
    offset = len(src) - len(bars)
    for j, b in enumerate(bars):
        i = offset + j
        assert b["sma60"] == pytest.approx(sum(closes[i - 59:i + 1]) / 60)
        want, reason = mu.classify(closes[:i + 1])
        assert reason == "ok"
        assert (b["state"], b["m"], b["above"], b["rising"]) == (want.state, want.m, want.above, want.rising)


def test_c2_short_history_gives_null_judgement(wire):
    wire["bars"]["0001"] = _bars(70, 2500.0)
    d = _get()
    bars = d["markets"]["kospi"]["bars"]
    assert len(bars) == 70
    assert bars[58]["sma60"] is None and bars[59]["sma60"] is not None
    assert all(b["m"] is None and b["state"] is None for b in bars)


def test_c3_last_120_bars_with_ohlc(wire):
    wire["bars"]["1001"] = _bars(200, 800.0, ohlc=False)
    d = _get()
    k = d["markets"]["kospi"]["bars"]
    assert len(k) == 120
    assert k[-1]["high"] == pytest.approx(k[-1]["close"] * 1.01)
    q = d["markets"]["kosdaq"]["bars"]
    assert q[-1]["open"] is None and q[-1]["high"] is None and q[-1]["low"] is None
    assert d["rules"]["multipliers"] == {"up_rising": 1.0, "up_falling": 0.75, "down_rising": 0.5,
                                         "down_falling": 0.0}


def test_c4_decision_from_compute_snapshot(wire):
    d = _get()
    assert sorted(m for _, m in wire["snap_calls"]) == ["kosdaq", "kospi"]
    assert d["markets"]["kospi"]["decision"]["m"] == 0.0
    assert d["markets"]["kosdaq"]["decision"]["state"] == "up_falling"


def test_c5_engine_absent_is_null_and_not_computed(wire):
    d = _get()
    for mk in ("kospi", "kosdaq"):
        assert d["markets"][mk]["engine"] is None
        assert d["markets"][mk]["effective"] == {"m": None, "fallback": "not_computed", "from_market": None}


def test_c5_effective_fallback_rules(wire):
    wire["reg"]["kojiro"] = _Strat(
        {"market_unit_mode": "enforce"},
        snaps_kospi={TODAY: _snap("kospi", ok=True, m=0.0, state="down_falling")},
        snaps_kq={TODAY: _snap("kosdaq", ok=False)},
    )
    d = _get()
    k, q = d["markets"]["kospi"], d["markets"]["kosdaq"]
    assert k["engine"]["m"] == 0.0 and k["engine"]["ok"] is True
    assert k["effective"] == {"m": 0.0, "fallback": "-", "from_market": "kospi"}
    assert q["engine"]["ok"] is False
    assert q["effective"] == {"m": 0.0, "fallback": "other_market", "from_market": "kospi"}


def test_c5_both_failed_gives_one(wire):
    wire["reg"]["kojiro"] = _Strat(
        {}, snaps_kospi={TODAY: _snap("kospi", ok=False)}, snaps_kq={TODAY: _snap("kosdaq", ok=False)},
    )
    d = _get()
    for mk in ("kospi", "kosdaq"):
        assert d["markets"][mk]["effective"] == {"m": 1.0, "fallback": "none", "from_market": None}


def test_c6_modes_normalized_unknown_null(wire):
    wire["reg"]["kojiro"] = _Strat({"market_unit_mode": " ENFORCE "})
    wire["reg"]["donchian_swing"] = _Strat({"market_unit_mode": "shadow"})
    d = _get()
    assert d["modes"]["kojiro"] == "enforce"
    assert d["modes"]["donchian_swing"] == "shadow"
    assert d["modes"]["vcp_breakout"] is None
