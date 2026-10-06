"""cycle410 — `GET /api/market-regime-label`(`src/routes/market_regime_label.py`). 관찰 전용.

| # | 계약 |
|---|---|
| R1 | `stock_master_daily.get_recent_daily("069500", 400)` 로 읽는다 |
| R2 | 오늘(KST) 날짜 봉은 쓰지 않는다 — 오늘 라벨 = 오늘 이전 마지막 봉까지(`basis_date`) |
| R3 | 응답 = today{date,label,direction,volatility,slope_pct,vol_pct,basis_date} · history(최근 60, 마지막 = 오늘) · since · since_truncated · warmup_from · thresholds |
| R4 | `since` = 오늘 라벨이 이어진 첫 날. 읽은 이력 첫 라벨까지 같은 칸이면 `since_truncated=true` |
| R5 | 데이터 부족 · 나쁜 종가 = 200 + success=false + message(빈 화면으로 위장하지 않는다) |
| MU1 | `market_unit` = 운영 판정 `market_unit.classify` 그대로(오늘 이전 마지막 80봉) → {m, state, above_sma60, sma60_rising, basis_date, modes} |
| MU2 | 대조 — 오늘·history 날짜마다 m 이 운영 로더 `market_unit.compute_snapshot(D)` 의 m 과 같다 |
| MU1b | `market_unit.source = "db_recompute"` — 엔진 메모리 값이 아니라 운영 DB 종가로 다시 계산한 값 |
| MU3 | `modes` = 시장 유닛 축소 대상(`strategy_manifest.MARKET_UNIT_SCALE_IDS`)마다 운영 엔진 전략 파라미터 `market_unit_mode` 를 `normalize_mode` 로 — 미등록 = null |
"""

from __future__ import annotations

import asyncio
import importlib
import math
from types import SimpleNamespace
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

TODAY = date(2026, 10, 5)  # 월요일


def _weekdays_before(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def _closes(n: int) -> list[float]:
    """느린 큰 물결(60일선 위/아래·상승/하락을 모두 지난다) + 빠른 흔들림."""
    return [
        round(30_000.0 * math.exp(0.15 * math.sin(i / 9) + 0.02 * math.sin(i * 1.9)), 0)
        for i in range(n)
    ]


def _rows(n: int = 200, *, today_close: float | None = 1.0) -> tuple[list[dict], list[date], list[float]]:
    dates = _weekdays_before(date(2026, 10, 2), n)
    closes = _closes(n)
    rows = [{"ticker": "069500", "bas_dd": d, "close_price": c} for d, c in zip(dates, closes)]
    if today_close is not None:
        rows.append({"ticker": "069500", "bas_dd": TODAY, "close_price": today_close})
    return rows[::-1], dates, closes  # DB 는 bas_dd DESC


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(importlib.import_module("src.routes.market_regime_label").router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def wire(monkeypatch):
    smd = importlib.import_module("src.db.stock_master_daily")
    kst = importlib.import_module("src.db._kst")
    monkeypatch.setattr(kst, "today_kst", lambda: TODAY)
    fetch = AsyncMock()
    monkeypatch.setattr(smd, "get_recent_daily", fetch)
    _set_registry(monkeypatch, {})
    return fetch


class _FakeRegistry:
    def __init__(self, params_by_sid: dict):
        self._p = params_by_sid

    def get(self, sid):
        if sid not in self._p:
            return None
        return SimpleNamespace(config=SimpleNamespace(params=self._p[sid]))


def _set_registry(monkeypatch, params_by_sid: dict) -> None:
    sched = importlib.import_module("src.engine.scheduler")
    monkeypatch.setattr(sched, "trading_scheduler", SimpleNamespace(registry=_FakeRegistry(params_by_sid)))


def _get():
    r = _client().get("/api/market-regime-label")
    assert r.status_code == 200, r.text
    return r.json()


def test_r1_reads_069500_400_rows(wire):
    wire.return_value = _rows()[0]
    _get()
    wire.assert_awaited_once_with("069500", 400)


def test_r2_r3_today_uses_bars_before_today(wire):
    mrl = importlib.import_module("src.engine.market_regime_label")
    rows, dates, closes = _rows()
    wire.return_value = rows
    body = _get()
    assert body["success"] is True, body
    t = body["data"]["today"]
    want = mrl.label_after_closes(closes)[-1]
    assert t["date"] == "2026-10-05"
    assert t["basis_date"] == "2026-10-02"
    assert t["label"] == want.label
    assert t["direction"] == want.direction
    assert t["volatility"] == want.volatility
    assert t["slope_pct"] == pytest.approx(want.slope_pct)
    assert t["vol_pct"] == pytest.approx(want.vol_pct)


def test_r2_today_bar_close_does_not_move_label(wire):
    wire.return_value = _rows(today_close=1.0)[0]
    a = _get()["data"]
    wire.return_value = _rows(today_close=999_999.0)[0]
    b = _get()["data"]
    wire.return_value = _rows(today_close=None)[0]
    c = _get()["data"]
    assert a == b == c


def test_r3_history_and_meta(wire):
    mrl = importlib.import_module("src.engine.market_regime_label")
    rows, dates, closes = _rows()
    wire.return_value = rows
    d = _get()["data"]
    hist = d["history"]
    assert len(hist) == 60
    assert {k: hist[-1][k] for k in ("date", "label")} == {"date": "2026-10-05", "label": d["today"]["label"]}
    sess = mrl.session_labels(dates, closes)
    assert [{k: h[k] for k in ("date", "label")} for h in hist[:-1]] == [
        {"date": x.isoformat(), "label": p.label} for x, p in sess[-59:]
    ]
    assert d["warmup_from"] == dates[0].isoformat()
    assert d["thresholds"] == {
        "ma_window": 60, "slope_lookback": 20, "vol_window": 20,
        "dir_enter_pct": 3.0, "dir_exit_pct": 1.0,
        "vol_high_pct": 20.0, "vol_low_pct": 16.0,
    }


def test_r4_since_is_start_of_current_run(wire):
    mrl = importlib.import_module("src.engine.market_regime_label")
    rows, dates, closes = _rows()
    wire.return_value = rows
    d = _get()["data"]
    seq = [(x, p.label) for x, p in mrl.session_labels(dates, closes)]
    seq.append((TODAY, d["today"]["label"]))
    k = len(seq) - 1
    while k > 0 and seq[k - 1][1] == seq[-1][1]:
        k -= 1
    assert d["since"] == seq[k][0].isoformat()
    assert d["since_truncated"] is (k == 0)


def test_r4_since_truncated_when_run_reaches_history_start(wire):
    # 단조 완만 상승 = 처음부터 끝까지 한 칸 → since 는 하한일 뿐이다
    dates = _weekdays_before(date(2026, 10, 2), 120)
    rows = [{"bas_dd": x, "close_price": 10_000.0 * (1.0002 ** i)} for i, x in enumerate(dates)]
    wire.return_value = rows[::-1]
    d = _get()["data"]
    assert d["since"] == dates[80].isoformat()
    assert d["since_truncated"] is True


@pytest.mark.parametrize("n", [0, 10, 79])
def test_r5_short_data_is_graceful_failure(wire, n):
    wire.return_value = _rows(n, today_close=None)[0] if n else []
    body = _get()
    assert body["success"] is False
    assert body["message"]


def test_r5_bad_close_is_graceful_failure(wire):
    rows, _, _ = _rows()
    rows[30]["close_price"] = None
    wire.return_value = rows
    body = _get()
    assert body["success"] is False
    assert body["message"]


def test_r6_registered_in_main_app():
    app = importlib.import_module("src.main").app
    assert "/api/market-regime-label" in {getattr(r, "path", None) for r in app.routes}



# ── 시장 유닛 ────────────────────────────────────────────────────────────────
def test_mu1_today_market_unit_is_operational_classify(wire):
    mu = importlib.import_module("src.engine.market_unit")
    rows, dates, closes = _rows()
    wire.return_value = rows
    d = _get()["data"]
    want, reason = mu.classify(closes[-80:])
    assert reason == "ok"
    m = d["market_unit"]
    assert m["m"] == want.m
    assert m["state"] == want.state
    assert m["above_sma60"] is want.above
    assert m["sma60_rising"] is want.rising
    assert m["basis_date"] == "2026-10-02"
    # 운영 엔진 메모리 스냅샷을 여는 공개 경로가 없다 → DB 종가 재계산판임을 응답이 밝힌다
    assert m["source"] == "db_recompute"


def test_mu1_history_carries_m_per_day(wire):
    mu = importlib.import_module("src.engine.market_unit")
    rows, dates, closes = _rows()
    wire.return_value = rows
    hist = _get()["data"]["history"]
    for h in hist[:-1]:
        k = dates.index(date.fromisoformat(h["date"]))
        assert h["m"] == mu.classify(closes[k - 80:k])[0].m, h
    assert hist[-1]["m"] == mu.classify(closes[-80:])[0].m


def test_mu2_matches_operational_loader_compute_snapshot(wire, monkeypatch):
    """대조 — 같은 행을 운영 로더에 먹여 날짜마다 m 이 같은지(새 판정식 금지)."""
    mu = importlib.import_module("src.engine.market_unit")
    tc = importlib.import_module("src.engine.trading_calendar")
    rows, dates, closes = _rows()
    wire.return_value = rows
    hist = _get()["data"]["history"]

    async def prev_day(as_of):
        return max(d for d in dates if d < as_of)

    monkeypatch.setattr(tc, "previous_trading_day", prev_day)
    states = set()
    for h in hist:
        snap = asyncio.run(mu.compute_snapshot(date.fromisoformat(h["date"]), preview=True))
        assert snap.ok, (h, snap.reason)
        assert h["m"] == snap.m, h
        states.add(snap.state)
    assert len(states) >= 3, states  # 합성 열이 여러 칸을 지나야 대조가 공허하지 않다


def test_mu3_modes_from_engine_params(wire, monkeypatch):
    manifest = importlib.import_module("src.engine.strategy_manifest")
    wire.return_value = _rows()[0]
    _set_registry(monkeypatch, {
        "kojiro": {"market_unit_mode": "enforce"},
        "donchian_swing": {"market_unit_mode": "shadow"},
        "bull_flag_breakout": {},
        "vcp_breakout": {"market_unit_mode": " ENFORCE "},
        "momentum": {"market_unit_mode": "enforce"},
    })
    modes = _get()["data"]["market_unit"]["modes"]
    assert list(modes) == list(manifest.MARKET_UNIT_SCALE_IDS)
    assert modes["kojiro"] == "enforce"
    assert modes["donchian_swing"] == "shadow"
    assert modes["bull_flag_breakout"] == "off"
    assert modes["vcp_breakout"] == "enforce"
    assert "momentum" not in modes
    for sid in manifest.MARKET_UNIT_SCALE_IDS:
        if sid not in {"kojiro", "donchian_swing", "bull_flag_breakout", "vcp_breakout"}:
            assert modes[sid] is None, sid  # 미등록 = 모른다


def test_mu3_registry_failure_is_graceful(wire, monkeypatch):
    sched = importlib.import_module("src.engine.scheduler")

    class Boom:
        def get(self, sid):
            raise RuntimeError("x")

    monkeypatch.setattr(sched, "trading_scheduler", SimpleNamespace(registry=Boom()))
    wire.return_value = _rows()[0]
    body = _get()
    assert body["success"] is True
    assert set(body["data"]["market_unit"]["modes"].values()) == {None}
