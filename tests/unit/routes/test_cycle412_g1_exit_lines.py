"""cycle412 Red — G1 `GET /api/balance/exit-lines` 행위 (사용자 결정 E1b, 설계 관찰자안 3절 G1 · 5절 ②③).

엔진 이벤트 루프 안에서 도는 **유일한 새 코드**다. 손절선 계산 입력(`_entry_atr`·래치·무장 여부)은
엔진 메모리에만 있어 워커가 이 GET 으로 읽는다. 잘못 짜면 운영 Position·params 를 바꿔 손절이 깨진다
(`vars(pos)["buy_date"]=문자열` → `is_next_day` TypeError → 익일청산 판정 붕괴 · `params.pop` → BFB/VCP 청산 KeyError).

| # | 계약 |
|---|---|
| E1 | 응답 = `{success, data:{running, as_of(KST), items:[…]}}` · item 키 14개 · 전략마다 보유마다 1 item |
| E2 | 값 = `resolve_exit_lines([s], t)` 그대로 + 같은 순간 Position 값 + `entry_atr`(kojiro 는 `_position_atr`) |
| E3 | donchian 무장가 = `ceil(E + kk_breakeven_r × (E − 손절선))` — 차분: 고점이 무장가면 무장, 1원 아래면 미무장 |
| E4 | **변이 0** — 7전략 registry(보유·래치·params·ATR·buy_signals)를 deepcopy 해 두고 호출 전후 값 `==` · 컨테이너 `is` 동일 · `buy_date` 는 여전히 date |
| E5 | KIS(`get_balance`)·DB(`pg.*`) 호출 0 |
| E6 | 5초 캐시 — 직전 성공 응답 뒤 5초 안 재호출은 바이트 동일, 5초 뒤엔 새로 |
| E7 | 실패 → HTTP 200 `success=false` · `src.routes.balance` 로거 INFO 이상 0줄 |
| E8 | 엔진 정지 → `running=false` 로 그대로 응답 |
"""
from __future__ import annotations

import copy
import importlib
import json
import logging
import math
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

T = "005930"
ITEM_KEYS = {"strategy_id", "ticker", "stop_price", "stop_source", "target_price", "target_source",
             "buy_price", "quantity", "high_since_buy", "buy_date", "order_no", "entry_atr", "kk_armed",
             "kk_arm_price"}


def _strategies():
    from src.engine.strategy_base import Position, StrategyConfig
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategies.kojiro import KojiroStrategy
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategies.momentum import MomentumStrategy
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    out = []
    for cls, sid, ticker in [(KojiroStrategy, "kojiro", "000520"), (DonchianSwingStrategy, "donchian_swing", T),
                             (BullFlagBreakoutStrategy, "bull_flag_breakout", "003160"),
                             (LongTailVolatilityStrategy, "long_tail_volatility", "457370"),
                             (MomentumStrategy, "momentum", "393210"),
                             (VolatilityBreakoutStrategy, "volatility_breakout", "010170"),
                             (VcpBreakoutStrategy, "vcp_breakout", "006120")]:
        s = cls(StrategyConfig(strategy_id=sid, name=sid))
        s.state.positions[ticker] = Position(ticker, 10000, 3, f"O-{sid}", sid, date(2026, 10, 6), 10500)
        s.state.buy_signals.append({"ticker": ticker, "price": 10000, "time": "09:05:00"})
        if hasattr(s, "_entry_atr"):
            s._entry_atr[ticker] = 400.0
        elif hasattr(s, "_position_atr"):
            s._position_atr[ticker] = 400.0  # kojiro 는 진입 ATR 을 `_position_atr` 에 둔다
        if sid == "bull_flag_breakout":
            s._position_setup[ticker] = {"flag_low": 9400, "flag_high": 10200, "pole_high": 10400,
                                         "pole_start": 9000, "atr14": 300}
            s._partial_exit[ticker] = False
            s._breakeven_latched.add(ticker)
        if sid == "vcp_breakout":
            s._position_setup[ticker] = {"base_low": 9300, "base_high": 10100, "atr14": 300, "ema50": 9100}
            s._breakeven_latched.add(ticker)
        if sid == "kojiro":
            s._stop_floor[ticker] = 9600
        if sid == "long_tail_volatility":
            s._limit_up_reached.add(ticker)
        if sid == "donchian_swing":
            s._channel_low[ticker] = 9800
        out.append(s)
    return out


@pytest.fixture
def engine(monkeypatch):
    from src.engine.strategy_registry import StrategyRegistry

    reg = StrategyRegistry()
    for s in _strategies():
        reg.register(s)
    fake = SimpleNamespace(registry=reg, is_running=True, _running=True)
    sched = importlib.import_module("src.engine.scheduler")
    monkeypatch.setattr(sched, "trading_scheduler", fake)
    return fake


@pytest.fixture
def bal(monkeypatch):
    mod = importlib.import_module("src.routes.balance")
    monkeypatch.setattr(mod, "_exit_lines_cache", None, raising=False)
    monkeypatch.setattr(mod, "get_balance", AsyncMock(side_effect=AssertionError("KIS 호출 금지")))
    monkeypatch.setattr(mod, "get_buyable", AsyncMock(side_effect=AssertionError("KIS 호출 금지")))
    pg = importlib.import_module("src.db.pg")
    for name in ("fetch", "fetchrow", "fetchval", "execute"):
        monkeypatch.setattr(pg, name, AsyncMock(side_effect=AssertionError("DB 호출 금지")), raising=False)
    return mod


def _client(bal):
    app = FastAPI()
    app.include_router(bal.router)
    return TestClient(app, raise_server_exceptions=False)


def _get(bal):
    r = _client(bal).get("/api/balance/exit-lines")
    assert r.status_code == 200, r.text
    return r


def _data(bal):
    body = _get(bal).json()
    assert body["success"] is True, body
    return body["data"]


def _by(data):
    return {(i["strategy_id"], i["ticker"]): i for i in data["items"]}


# ── E1·E2 모양과 값 ───────────────────────────────────────────────────────────

def test_e1_shape(engine, bal):
    data = _data(bal)
    assert data["running"] is True
    assert datetime.fromisoformat(data["as_of"]).utcoffset().total_seconds() == 9 * 3600
    assert len(data["items"]) == 7
    for it in data["items"]:
        assert set(it) == ITEM_KEYS, it


def test_e2_values_mirror_leaf_and_position(engine, bal):
    from src.engine.position_exit_lines import resolve_exit_lines

    items = _by(_data(bal))
    for s in engine.registry.all():
        (t, pos), = s.state.positions.items()
        it = items[(s.strategy_id, t)]
        leaf = resolve_exit_lines([s], t)
        for k in ("stop_price", "stop_source", "target_price", "target_source"):
            assert it[k] == leaf[k], (s.strategy_id, k)
        assert (it["buy_price"], it["quantity"], it["high_since_buy"]) == (10000, 3, 10500)
        assert it["buy_date"] == "2026-10-06" and it["order_no"] == f"O-{s.strategy_id}"
        has_atr = hasattr(s, "_entry_atr") or hasattr(s, "_position_atr")
        assert it["entry_atr"] == (400.0 if has_atr else None), s.strategy_id
    assert items[("bull_flag_breakout", "003160")]["target_price"] == 11600
    assert items[("long_tail_volatility", "457370")]["stop_source"] == "mode_dependent"
    assert items[("kojiro", "000520")]["kk_armed"] is None


# ── E3 donchian 무장가 차분 ───────────────────────────────────────────────────

def _donchian(engine):
    return next(s for s in engine.registry.all() if s.strategy_id == "donchian_swing")


@pytest.mark.parametrize("atr,arm_exact", [(400.0, 10000 + 3.0 * 800.0), (601.0, 10000 + 3.0 * 901.5)])
def test_e3_arm_price_differential(engine, bal, monkeypatch, atr, arm_exact):
    d = _donchian(engine)
    d._entry_atr[T] = atr
    pos = d.state.positions[T]
    arm = math.ceil(arm_exact)
    pos.high_since_buy = arm - 1
    monkeypatch.setattr(bal, "_exit_lines_cache", None, raising=False)
    it = _by(_data(bal))[("donchian_swing", T)]
    assert (it["kk_armed"], it["kk_arm_price"]) == (False, arm)
    assert d._kk_exit_lines(T, pos)[1] is False
    pos.high_since_buy = arm  # 바로 그 가격 — 엔진 헬퍼가 무장이라고 말해야 한다
    assert d._kk_exit_lines(T, pos)[1] is True
    monkeypatch.setattr(bal, "_exit_lines_cache", None, raising=False)
    it2 = _by(_data(bal))[("donchian_swing", T)]
    assert it2["kk_armed"] is True and it2["kk_arm_price"] is None


# ── E4 변이 0 ─────────────────────────────────────────────────────────────────

def _snapshot(s):
    snap = {}
    for owner, prefix in ((s, ""), (s.state, "state."), (s.config, "config.")):
        for k, v in vars(owner).items():
            if isinstance(v, (dict, list, set)):
                snap[prefix + k] = (id(v), copy.deepcopy(v))
    snap["positions"] = {t: (id(p), copy.deepcopy(vars(p)), type(p.buy_date)) for t, p in
                         s.state.positions.items()}
    return snap


def test_e4_no_mutation_of_engine_state(engine, bal):
    before = {s.strategy_id: _snapshot(s) for s in engine.registry.all()}
    for _ in range(3):
        bal._exit_lines_cache = None
        _data(bal)
    after = {s.strategy_id: _snapshot(s) for s in engine.registry.all()}
    for sid in before:
        for k in before[sid]:
            assert after[sid][k] == before[sid][k], f"{sid}.{k} 가 G1 호출로 바뀌었다"
    for s in engine.registry.all():
        for p in s.state.positions.values():
            assert type(p.buy_date) is date and p.is_next_day in (True, False)


# ── E5 KIS·DB 0 ──────────────────────────────────────────────────────────────

def test_e5_no_kis_no_db(engine, bal):
    _data(bal)
    bal.get_balance.assert_not_awaited()
    pg = importlib.import_module("src.db.pg")
    for name in ("fetch", "fetchrow", "fetchval", "execute"):
        getattr(pg, name).assert_not_awaited()


# ── E6 5초 캐시 ──────────────────────────────────────────────────────────────

def test_e6_five_second_cache(engine, bal, monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(bal, "_exit_lines_clock", lambda: now["t"])
    assert bal._EXIT_LINES_CACHE_TTL_S == 5.0
    first = _get(bal).text
    _donchian(engine).state.positions[T].buy_price = 20000  # 엔진 값이 바뀌어도
    now["t"] = 1004.9
    assert _get(bal).text == first                           # 5초 안 = 같은 본문
    now["t"] = 1005.1
    third = _get(bal).text
    assert third != first
    assert _by(json.loads(third)["data"])[("donchian_swing", T)]["buy_price"] == 20000


# ── E7 실패 ──────────────────────────────────────────────────────────────────

def test_e7_failure_is_success_false_without_info_log(engine, bal, caplog):
    def boom():
        raise RuntimeError("registry 깨짐")

    engine.registry.all = boom
    caplog.set_level(logging.DEBUG, logger="src.routes.balance")
    r = _get(bal)
    body = r.json()
    assert body["success"] is False and body["data"] is None
    noisy = [rec for rec in caplog.records
             if rec.name == "src.routes.balance" and rec.levelno >= logging.INFO]
    assert noisy == []


def test_e7b_unserializable_value_does_not_escape(engine, bal):
    d = _donchian(engine)
    d._entry_atr[T] = object()  # json 이 모르는 값 — default=str 로 직렬화되거나 success=false, 500 은 아니다
    r = _client(bal).get("/api/balance/exit-lines")
    assert r.status_code == 200 and "success" in r.json()


# ── E8 엔진 정지 ──────────────────────────────────────────────────────────────

def test_e8_engine_stopped_is_reported(engine, bal):
    engine.is_running = False
    engine._running = False
    data = _data(bal)
    assert data["running"] is False
