"""cycle414 Red — `GET /api/strategies/monitor` 읽기 전용 라우트 행위 (명세 §3 · §4 · §8.1 R1·R3~R6·R8).

명세 = `_workspace/red/cycle414/monitor_spec.md`. 엔진 메모리에만 있는 값(ETF 깔때기 중간 수 · 보유
방어선 구성 · 래치 · 오늘 거르기 사유 · 준비 기준일 · 시장 유닛 스냅샷)을 화면에 여는 **유일한 창**이다.
잘못 짜면 운영 전략 객체(래치·캡·스냅샷·보유)를 바꿔 손절·매수 판정이 깨진다.

계약(Green 이 지킬 이름) — 전부 `src/routes/strategies.py` 안:

| 이름 | 뜻 |
|---|---|
| `get_strategies_monitor()` | `@router.get("/monitor")` 핸들러. `async def` · 내부 `await` 0 |
| `_monitor_cache` | 모듈 전역 캐시(`None` = 비어 있음) — 테스트가 `None` 으로 비운다 |
| `_monitor_clock()` | 캐시 시계(초, 단조) — 테스트가 바꿔 끼운다(exit-lines `_exit_lines_clock` 꼴) |
| `_MONITOR_CACHE_TTL_S` | `2.0` |

응답 모양 = 명세 §3.2. 전략별 고유 키(이 파일이 고정하는 것만):

- etf `candidates[t]` = `line`·`prev_close`·`n`·`atr20`·`tv20`·`design_qty`·`cluster_partners`(list)·`cluster_blocked`(bool)
- etf `holdings[t]` = `entry_n`·`hsb_closed`·`bars_since_buy`·`lines{hard,breakeven,trail,channel}`·`breakout_fail{line,active}`·`effective_stop`
- donchian `candidates[t]` = `r_won`·`r_pct`·`design_lot`
- donchian `holdings[t]` = `r_won`·`stop`·`armed`·`channel`·`arm_price`·`target_1r`·`reached_1r`·`days_held`·`days_fallback`·`time_exit_bars`·`max_hold_bars`
- donchian `extra.daily_entries` = `{count, cap}`
- VCP·BFB `candidates[t]` = `latch_armed_at`(ISO+09:00 또는 None) · VCP 는 `first_cross_at`·`max` 도
- `skips` = `{known, day, counts{reason: 종목 수}, by_ticker{t: [reason…]}}` — donchian 사유 키 = `kk_lot_zero`·`daily_entry_cap`

| # | 계약 |
|---|---|
| R1 | 모양 — 등록 전략 전부에 10키 · 깔때기 행은 5키(생존·탈락 **목록 없음**) · prepare/market_unit/ticks/paused_skips/shadow_buys 값 · 빈 레지스트리 = `strategies={}` · 예외 = HTTP 200 `success=false` · 2초 캐시 |
| R3 | 무변경 — 호출 전후 전략 객체(래치·캡 `_day`/`_emitted`·스냅샷·후보·보유) 깊은 복사 같음 · 어제 캡/래치/스냅샷은 응답에서 빠지고 객체에는 그대로 |
| R4 | 엔진 값과 일치 — etf 활성 구성 선 max == `get_effective_stop_price` · donchian 무장·무장가 == exit-lines `_exit_lines_kk` · 시간청산 `due ≤ 0 ∧ ¬reached_1r` ⇔ `check_force_clear()` 포함(공휴일 낀 주) |
| R5 | 사유 사상 — etf `_skip_logged` 키 `ticker|reason` · VCP/BFB `_gate_emit_capped` `(ticker, kind)` · donchian 캡 2종 → 종목 수 기준 |
| R6 | etf `design_qty` == `_pure_turtle_qty(prev_close, info)` · 예산 0 → 0 · `sizing_mode` 오조작 → 0 |
| R8 | 성능 — 8전략 × 후보 50 × 보유 6 한 번 조립 < 50ms(5회 중 최소) · DB·KIS 호출 0 |

호출은 TestClient 가 아니라 코루틴을 한 번 `send(None)` 해서 끝낸다 — `await` 양보점이 있으면
`StopIteration` 대신 값이 나와 그 자체로 실패한다(R2 「await 0」의 행위 쪽 증거, cycle127 anyio portal hang 회피).
"""
from __future__ import annotations

import copy
import importlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
FROZEN_UTC = "2026-10-12 00:12:03"  # → KST 2026-10-12(월) 09:12:03
TODAY = date(2026, 10, 12)
PREV_DAY = date(2026, 10, 11)

ETF_A, ETF_B, ETF_HELD = "069500", "229200", "102110"
DC_CAND, DC_HELD = "005930", "000660"
VCP_A, BFB_A, KJ_HELD, VB_SHADOW = "006120", "003160", "000520", "010170"

MONITOR_KEYS = {
    "prepare", "funnel", "market_unit", "skips", "paused_skips", "shadow_buys",
    "ticks", "candidates", "holdings", "extra",
}
FUNNEL_KEYS = {"step_no", "step_name", "step_conditions", "survived_count", "excluded_count"}
MU_STRATEGIES = {"kojiro", "donchian_swing", "vcp_breakout", "bull_flag_breakout", "etf_trend"}
ALL_SIDS = MU_STRATEGIES | {"volatility_breakout", "momentum", "long_tail_volatility"}

#: 거래일 캐시(합성) — 09-24·09-25(추석)·10-05(대체)·10-09(한글날) 휴장.
_HOLIDAYS = {date(2026, 9, 24), date(2026, 9, 25), date(2026, 10, 5), date(2026, 10, 9)}


def _trading_days(start: date, end: date) -> set[date]:
    out, d = set(), start
    while d <= end:
        if d.weekday() < 5 and d not in _HOLIDAYS:
            out.add(d)
        d += timedelta(days=1)
    return out


def _cap(day: str, keys) -> object:
    from src.engine.daily_emit_cap import KstDailyEmitCap

    cap = KstDailyEmitCap[str]()
    cap._day = day
    cap._emitted = set(keys)
    return cap


def _funnel(stages, counts) -> list[dict]:
    return [
        {
            "step_no": int(st.step_no), "step_name": str(st.step_name),
            "step_conditions": f"조건-{st.step_no}",
            "survived": [{"ticker": "X", "name": "x"}] * min(c, 3), "survived_count": c,
            "excluded": [{"ticker": "Y", "name": "y", "reason": "r"}], "excluded_count": 1,
        }
        for st, c in zip(stages, counts)
    ]


def _snap(as_of: date, *, m: float = 0.75, ok: bool = True, state: str = "up_falling"):
    from src.engine.market_unit import Snapshot

    return Snapshot(
        as_of=as_of, preview=False, ok=ok, state=state if ok else "unavailable", m=m if ok else 1.0,
        reason="ok" if ok else "no_rows", bar_date=date(2026, 10, 8) if ok else None,
        expected_head=date(2026, 10, 8), rows=120 if ok else 0, close=1.0, sma60=1.0,
        sma60_prev=1.0, above=True, rising=False,
    )


def _build() -> list:
    """8전략 합성 상태. 반드시 freeze_time 안에서 부른다."""
    from src.engine.strategy_base import Position, StrategyConfig
    from src.engine.strategies import bull_flag_breakout as bfb_mod
    from src.engine.strategies import donchian_swing as dc_mod
    from src.engine.strategies import etf_trend as etf_mod
    from src.engine.strategies import kojiro as kj_mod
    from src.engine.strategies import vcp_breakout as vcp_mod
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategies.momentum import MomentumStrategy
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    started = datetime(2026, 10, 12, 7, 45, 10, tzinfo=KST)
    finished = datetime(2026, 10, 12, 7, 46, 2, tzinfo=KST)

    # ── etf_trend (멈춤 + 섀도 꺼짐 + 시장 유닛 shadow) ─────────────────────
    etf = etf_mod.EtfTrendStrategy(StrategyConfig(
        strategy_id="etf_trend", name="ETF 추세",
        params={"buy_paused": True, "shadow_mode": False, "market_unit_mode": "shadow"},
    ))
    etf.state.total_investment = 10_000_000
    etf._candidates = {
        ETF_A: {"prev_close": 10_000, "line": 9_950.0, "n": 150.0, "atr": 150.0, "atr20": 160.0,
                "tv20": 5_000_000_000.0, "ema60": 9_500.0, "cluster_key": None},
        ETF_B: {"prev_close": 20_000, "line": 19_800.0, "n": 300.0, "atr": 300.0, "atr20": 310.0,
                "tv20": 3_000_000_000.0, "ema60": 19_000.0, "cluster_key": None},
    }
    etf._scanned_tickers = [ETF_A, ETF_B]
    etf._cluster_pairs = {frozenset({ETF_B, ETF_HELD})}
    etf.state.positions[ETF_HELD] = Position(ETF_HELD, 10_000, 30, "O-etf", "etf_trend", date(2026, 10, 7), 10_800)
    etf._entry_atr[ETF_HELD] = 200.0
    etf._hsb_closed[ETF_HELD] = 10_600.0
    etf._bars_since_buy[ETF_HELD] = 2
    etf._channel_low[ETF_HELD] = 10_100
    etf._breakout_line[ETF_HELD] = 9_900.0
    etf._funnel_steps = _funnel(etf_mod.FUNNEL_STAGES, [41, 38, 20, 3, 2, 2, 2])
    etf._live_prepare_meta = {"as_of": TODAY, "phase": "boot", "started_at": started,
                              "finished_at": finished, "ok": True}
    etf._market_unit_snaps = {TODAY: _snap(TODAY), PREV_DAY: _snap(PREV_DAY, m=0.5)}
    etf._skip_logged = _cap("2026-10-12", {f"{ETF_A}|gap_up", f"{ETF_A}|collapse", f"{ETF_B}|cluster_held"})
    etf._buy_paused_logged = _cap("2026-10-12", {f"skip|{ETF_A}", "cfg|p|True"})

    # ── donchian_swing (멈춤, 시장 유닛 스냅샷은 어제 것뿐) ──────────────────
    dc = dc_mod.DonchianSwingStrategy(StrategyConfig(
        strategy_id="donchian_swing", name="돈키언",
        params={"buy_paused": True, "market_unit_mode": "shadow", "risk_pct": 0.01, "position_ratio": 0.25},
    ))
    dc.state.total_investment = 10_000_000
    dc._candidates = {DC_CAND: {"prev_close": 50_000, "atr": 1_500, "ema60": 45_000, "donchian_high": 49_500}}
    dc._scanned_tickers = [DC_CAND]
    dc.state.positions[DC_HELD] = Position(DC_HELD, 100_000, 5, "O-dc", "donchian_swing", date(2026, 9, 14), 104_000)
    dc._entry_atr[DC_HELD] = 3_000.0
    dc._channel_low[DC_HELD] = 95_000
    dc._trading_days = _trading_days(date(2026, 8, 3), date(2026, 10, 8))
    dc._funnel_steps = _funnel(dc_mod.FUNNEL_STAGES, [400, 380, 300, 290, 12, 6, 3, 3, 3])
    dc._market_unit_snaps = {PREV_DAY: _snap(PREV_DAY)}
    dc._kk_lot_zero_logged = _cap("2026-10-12", {"005380"})
    dc._kk_entry_cap_logged = _cap("2026-10-12", {"035720"})

    # ── vcp_breakout (래치 오늘 1 · 어제 1 · 게이트 캡 오늘) ─────────────────
    vcp = vcp_mod.VcpBreakoutStrategy(StrategyConfig(strategy_id="vcp_breakout", name="VCP"))
    vcp._candidates = {VCP_A: {"base_high": 10_100, "base_low": 9_300, "atr14": 300, "ema50": 9_100,
                               "avg_volume_20": 100_000, "prev_close": 9_900}}
    vcp._scanned_tickers = [VCP_A]
    vcp._vol_latch = {
        VCP_A: {"armed_at": datetime(2026, 10, 12, 9, 10, 0, tzinfo=KST), "armed_date": TODAY,
                "base_high": 10_100, "base_low": 9_300},
        "900100": {"armed_at": datetime(2026, 10, 11, 9, 20, 0, tzinfo=KST), "armed_date": PREV_DAY,
                   "base_high": 5_000, "base_low": 4_500},
    }
    vcp._gate_emit_capped = {(VCP_A, "no_data"), (VCP_A, "latch_armed")}
    vcp._gate_emit_day = TODAY
    vcp._breakout_watch = {"date": TODAY, "run_at": "09:05:00", "tickers": {
        VCP_A: {"base_high": 10_100, "max": 10_250, "ticks": 5, "first_cross_at": "09:09:58",
                "first_tick_at": "09:05:01", "last_tick_at": "09:12:00"}}}
    vcp._funnel_steps = _funnel(vcp_mod.FUNNEL_STAGES, [2000, 900, 850, 800, 40, 9, 8, 8, 8])

    # ── bull_flag_breakout ───────────────────────────────────────────────────
    bfb = bfb_mod.BullFlagBreakoutStrategy(StrategyConfig(strategy_id="bull_flag_breakout", name="BFB"))
    bfb._candidates = {BFB_A: {"pole_start": 9_000, "pole_high": 10_400, "flag_high": 10_200, "flag_low": 9_400,
                               "atr14": 300, "flag_avg_volume": 50_000, "prev_close": 10_000}}
    bfb._scanned_tickers = [BFB_A]
    bfb._vol_latch = {BFB_A: {"armed_at": datetime(2026, 10, 12, 9, 11, 0, tzinfo=KST), "armed_date": TODAY,
                              "flag_high": 10_200, "flag_low": 9_400}}
    bfb._gate_emit_capped = {(BFB_A, "seen"), (BFB_A, "retreat")}
    bfb._gate_emit_day = TODAY
    bfb._breakout_first_seen = {BFB_A: datetime(2026, 10, 12, 9, 8, 0, tzinfo=KST)}

    # ── kojiro (보유 1) ───────────────────────────────────────────────────────
    kj = kj_mod.KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로"))
    kj.state.positions[KJ_HELD] = Position(KJ_HELD, 10_000, 3, "O-kj", "kojiro", date(2026, 10, 6), 10_500)
    kj._position_atr[KJ_HELD] = 400.0
    kj._stop_floor[KJ_HELD] = 9_600
    kj._market_unit_snaps = {TODAY: _snap(TODAY, m=0.0, state="down_falling")}

    # ── volatility_breakout (섀도 — 섀도 기록 오늘 1) ────────────────────────
    vb = VolatilityBreakoutStrategy(StrategyConfig(
        strategy_id="volatility_breakout", name="VB", weight=0.0, params={"shadow_mode": True},
    ))
    vb._shadow_logged = _cap("2026-10-12", {f"buy|{VB_SHADOW}", "cfg|s|True"})

    mom = MomentumStrategy(StrategyConfig(strategy_id="momentum", name="모멘텀"))
    ltv = LongTailVolatilityStrategy(StrategyConfig(strategy_id="long_tail_volatility", name="LTV", enabled=False))
    return [etf, dc, vcp, bfb, kj, vb, mom, ltv]


@pytest.fixture
def frozen():
    with freeze_time(FROZEN_UTC, tz_offset=9):
        yield


@pytest.fixture
def engine(frozen, monkeypatch):
    from src.engine import scanner, tick_volume
    from src.engine.strategy_registry import StrategyRegistry

    reg = StrategyRegistry()
    for s in _build():
        reg.register(s)
    fake = SimpleNamespace(registry=reg, is_running=True, _running=True, scanner=scanner)
    monkeypatch.setattr(importlib.import_module("src.engine.scheduler"), "trading_scheduler", fake)
    monkeypatch.setattr(importlib.import_module("src.routes.strategies"), "trading_scheduler", fake)
    monkeypatch.setitem(scanner.ticker_last_tick, ETF_A, datetime(2026, 10, 12, 9, 12, 0, tzinfo=KST))
    monkeypatch.setitem(scanner.ticker_last_tick, ETF_HELD, datetime(2026, 10, 12, 9, 7, 0, tzinfo=KST))
    tick_volume.reset_for_test()
    tick_volume.record_acml_vol(VCP_A, 123_456)
    yield fake
    tick_volume.reset_for_test()


@pytest.fixture
def mon(monkeypatch):
    """`src.routes.strategies` — 캐시 비움 + DB·KIS 호출을 전부 실패로 바꿔 둔다(I/O 0 증명)."""
    mod = importlib.import_module("src.routes.strategies")
    if hasattr(mod, "_monitor_cache"):
        monkeypatch.setattr(mod, "_monitor_cache", None)
    pg = importlib.import_module("src.db.pg")
    for name in ("fetch", "fetchrow", "fetchval", "execute"):
        monkeypatch.setattr(pg, name, AsyncMock(side_effect=AssertionError("DB 호출 금지")), raising=False)
    monkeypatch.setattr(mod, "get_trade_pairs", AsyncMock(side_effect=AssertionError("DB 호출 금지")))
    base = importlib.import_module("src.api.base")
    for name in ("kis_get", "kis_post", "kis_get_quote", "kis_post_quote"):
        if hasattr(base, name):
            monkeypatch.setattr(base, name, AsyncMock(side_effect=AssertionError("KIS 호출 금지")))
    return mod


def _drive(coro):
    """코루틴을 이벤트 루프 없이 한 번에 끝낸다 — 양보점(await 중단)이 있으면 실패."""
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    coro.close()
    raise AssertionError("핸들러가 await 에서 멈췄다 — 스냅샷 구간에 양보점이 있으면 안 된다(명세 §3.1)")


def _body(resp) -> tuple[int, dict]:
    status = getattr(resp, "status_code", 200)
    raw = getattr(resp, "body", None)
    if isinstance(raw, (bytes, bytearray)):
        return status, json.loads(raw)
    if hasattr(resp, "model_dump"):
        return status, json.loads(json.dumps(resp.model_dump(), default=str))
    return status, json.loads(json.dumps(resp, default=str))


def _call(mon) -> dict:
    assert hasattr(mon, "get_strategies_monitor"), "핸들러 `get_strategies_monitor` 가 없다(명세 §3.1)"
    status, body = _body(_drive(mon.get_strategies_monitor()))
    assert status == 200
    return body


def _data(mon) -> dict:
    body = _call(mon)
    assert body.get("success") is True, body
    return body["data"]


def _sid(engine, sid):
    return engine.registry.get(sid)


# ── R1 모양 ───────────────────────────────────────────────────────────────────

def test_r1a_route_registered_under_strategies_prefix():
    mod = importlib.import_module("src.routes.strategies")
    paths = {(r.path, tuple(sorted(getattr(r, "methods", ()) or ()))) for r in mod.router.routes}
    assert ("/api/strategies/monitor", ("GET",)) in paths, sorted(paths)


def test_r1b_shape_every_registered_strategy(engine, mon):
    data = _data(mon)
    assert data["running"] is True
    as_of = datetime.fromisoformat(data["as_of"])
    assert as_of.utcoffset() == timedelta(hours=9), "as_of 는 KST(+09:00)"
    assert as_of.date() == TODAY
    assert set(data["strategies"]) == ALL_SIDS
    for sid, entry in data["strategies"].items():
        assert MONITOR_KEYS <= set(entry), (sid, sorted(MONITOR_KEYS - set(entry)))
        assert isinstance(entry["funnel"], list)
        assert isinstance(entry["paused_skips"], list) and isinstance(entry["shadow_buys"], list)
        for k in ("ticks", "candidates", "holdings", "extra", "skips"):
            assert isinstance(entry[k], dict), (sid, k)


def test_r1c_cache_contract_names_exist():
    mod = importlib.import_module("src.routes.strategies")
    assert hasattr(mod, "_monitor_cache"), "모듈 캐시 `_monitor_cache` (None = 비어 있음)"
    assert callable(getattr(mod, "_monitor_clock", None)), "캐시 시계 `_monitor_clock()`"
    assert getattr(mod, "_MONITOR_CACHE_TTL_S", None) == 2.0


def test_r1d_funnel_rows_have_counts_only_no_ticker_lists(engine, mon):
    from src.engine.strategies.etf_trend import FUNNEL_STAGES

    rows = _data(mon)["strategies"]["etf_trend"]["funnel"]
    assert [r["step_no"] for r in rows] == [st.step_no for st in FUNNEL_STAGES]
    for r, st, c in zip(rows, FUNNEL_STAGES, [41, 38, 20, 3, 2, 2, 2]):
        assert set(r) == FUNNEL_KEYS, f"생존·탈락 목록을 5초 폴링에 싣지 않는다: {sorted(r)}"
        assert r["step_name"] == st.step_name and r["step_conditions"] == f"조건-{st.step_no}"
        assert (r["survived_count"], r["excluded_count"]) == (c, 1)
    assert _data(mon)["strategies"]["momentum"]["funnel"] == []


def test_r1e_prepare_meta_iso_kst_or_null(engine, mon):
    s = _data(mon)["strategies"]
    p = s["etf_trend"]["prepare"]
    assert p["as_of"] == "2026-10-12" and p["phase"] == "boot" and p["ok"] is True
    assert datetime.fromisoformat(p["started_at"]) == datetime(2026, 10, 12, 7, 45, 10, tzinfo=KST)
    assert datetime.fromisoformat(p["finished_at"]).utcoffset() == timedelta(hours=9)
    assert s["momentum"]["prepare"] is None, "준비 기록이 없는 전략은 null"


def test_r1f_market_unit_today_snapshot_only_for_mu_strategies(engine, mon):
    s = _data(mon)["strategies"]
    etf_mu = s["etf_trend"]["market_unit"]
    assert {k: etf_mu.get(k) for k in ("mode", "ok", "m", "state", "bar_date")} == {
        "mode": "shadow", "ok": True, "m": 0.75, "state": "up_falling", "bar_date": "2026-10-08",
    }, "엔진 스냅샷 `_market_unit_snaps[오늘]` 그대로(어제 m=0.5 아님)"
    dc = s["donchian_swing"]["market_unit"]
    assert (dc["mode"], dc["ok"], dc["reason"]) == ("shadow", False, "not_computed"), (
        "오늘 스냅샷이 없으면 어제 것으로 메우지 않는다(명세 §2.4)")
    kj = s["kojiro"]["market_unit"]
    assert kj["ok"] is True and kj["m"] == 0.0 and kj["state"] == "down_falling"
    for sid in ("volatility_breakout", "momentum", "long_tail_volatility"):
        assert s[sid]["market_unit"] is None, sid


def test_r1g_ticks_cover_candidates_and_holdings(engine, mon):
    s = _data(mon)["strategies"]
    etf_ticks = s["etf_trend"]["ticks"]
    assert {ETF_A, ETF_B, ETF_HELD} <= set(etf_ticks)
    assert datetime.fromisoformat(etf_ticks[ETF_A]["last_tick_at"]) == datetime(2026, 10, 12, 9, 12, 0, tzinfo=KST)
    assert etf_ticks[ETF_B]["last_tick_at"] is None, "틱을 못 받은 종목은 null(0·지금 시각으로 메우지 않는다)"
    assert s["vcp_breakout"]["ticks"][VCP_A]["acml_vol"] == 123_456
    assert etf_ticks[ETF_A]["acml_vol"] is None, "미관측 거래량은 null — 0 은 「진짜 0」 이다(tick_volume sentinel)"


def test_r1h_paused_skips_and_shadow_buys_today(engine, mon):
    s = _data(mon)["strategies"]
    assert s["etf_trend"]["paused_skips"] == [ETF_A]
    assert s["volatility_breakout"]["shadow_buys"] == [VB_SHADOW]
    assert s["donchian_swing"]["paused_skips"] == []


def test_r1i_empty_registry_is_success_with_no_strategies(frozen, mon, monkeypatch):
    from src.engine.strategy_registry import StrategyRegistry

    fake = SimpleNamespace(registry=StrategyRegistry(), is_running=False, _running=False)
    monkeypatch.setattr(importlib.import_module("src.engine.scheduler"), "trading_scheduler", fake)
    monkeypatch.setattr(mon, "trading_scheduler", fake)
    data = _data(mon)
    assert data["strategies"] == {} and data["running"] is False


def test_r1j_exception_is_http200_success_false(frozen, mon, monkeypatch):
    class Boom:
        def all(self):
            raise RuntimeError("registry 폭발")

        def get(self, _sid):
            raise RuntimeError("registry 폭발")

    fake = SimpleNamespace(registry=Boom(), is_running=True, _running=True)
    monkeypatch.setattr(importlib.import_module("src.engine.scheduler"), "trading_scheduler", fake)
    monkeypatch.setattr(mon, "trading_scheduler", fake)
    body = _call(mon)
    assert body["success"] is False


def test_r1k_two_second_cache(engine, mon, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(mon, "_monitor_clock", lambda: clock["t"])
    first = _data(mon)
    etf = _sid(engine, "etf_trend")
    etf._funnel_steps = []  # 엔진 상태가 바뀌어도
    clock["t"] += 1.9
    assert _data(mon) == first, "2초 안 재호출은 캐시"
    clock["t"] += 0.2
    assert _data(mon)["strategies"]["etf_trend"]["funnel"] == [], "2초 뒤엔 새로 조립"


# ── R3 무변경 ──────────────────────────────────────────────────────────────────

def _state_snapshot(s) -> dict:
    from src.engine.daily_emit_cap import DailyEmitCap

    snap = {}
    for owner, prefix in ((s, ""), (s.state, "state."), (s.config, "config.")):
        for k, v in vars(owner).items():
            if isinstance(v, (dict, list, set)):
                snap[prefix + k] = (id(v), copy.deepcopy(v))
            elif isinstance(v, DailyEmitCap):
                snap[prefix + k] = (id(v), getattr(v, "_day", None), set(v._emitted))
            elif isinstance(v, (date, type(None), bool, int, float, str)):
                snap[prefix + k] = v
            elif hasattr(type(v), "__slots__") and type(v).__module__.startswith("src.engine"):
                # `_market_unit_caps`(state·attempt·warn 캡 3개) — `_market_unit_view()` 가
                # 미계산 날 여기에 기록을 남긴다(명세 §3.3 금지 호출의 흔적).
                snap[prefix + k] = {
                    slot: (getattr(getattr(v, slot), "_day", None), set(getattr(getattr(v, slot), "_emitted", ())))
                    for slot in type(v).__slots__
                }
    snap["positions"] = {t: (id(p), copy.deepcopy(vars(p)), type(p.buy_date))
                         for t, p in s.state.positions.items()}
    return snap


def test_r3a_route_does_not_mutate_any_strategy(engine, mon):
    before = {s.strategy_id: _state_snapshot(s) for s in engine.registry.all()}
    for _ in range(3):
        mon._monitor_cache = None
        _data(mon)
    after = {s.strategy_id: _state_snapshot(s) for s in engine.registry.all()}
    for sid in before:
        diff = sorted(k for k in before[sid] if before[sid][k] != after[sid].get(k))
        assert diff == [], f"{sid} 상태가 바뀌었다: {diff}"


def test_r3b_yesterday_caps_latches_snapshots_are_reported_empty_but_kept(engine, mon):
    etf, vcp = _sid(engine, "etf_trend"), _sid(engine, "vcp_breakout")
    etf._skip_logged = _cap("2026-10-11", {f"{ETF_A}|gap_up"})
    etf._buy_paused_logged = _cap("2026-10-11", {f"skip|{ETF_A}"})
    vcp._gate_emit_day = PREV_DAY
    s = _data(mon)["strategies"]

    sk = s["etf_trend"]["skips"]
    assert sk["known"] is True and sk.get("counts", {}) == {} and sk.get("day") == "2026-10-11", sk
    assert s["etf_trend"]["paused_skips"] == []
    assert s["vcp_breakout"]["skips"].get("counts", {}) == {}
    assert "900100" not in s["vcp_breakout"]["candidates"], "어제 무장 래치는 응답에서 뺀다"

    # 객체는 그대로 — 어제 항목을 지우지 않는다(`_latch_entry`·`should_emit`·`_roll_gate_day_if_needed` 금지)
    assert etf._skip_logged._day == "2026-10-11" and etf._skip_logged._emitted == {f"{ETF_A}|gap_up"}
    assert etf._buy_paused_logged._emitted == {f"skip|{ETF_A}"}
    assert vcp._gate_emit_day == PREV_DAY and vcp._gate_emit_capped == {(VCP_A, "no_data"), (VCP_A, "latch_armed")}
    assert "900100" in vcp._vol_latch, "지난 래치를 pop 하면 안 된다(_latch_entry 호출 금지)"
    assert PREV_DAY in etf._market_unit_snaps, "지난 스냅샷을 지우면 안 된다(_market_unit_view 호출 금지)"


# ── R4 엔진 값과 일치 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "bars,hsb,n,be_atr,chan,expect",
    [
        # (보유 봉, 확정 고점, 진입 N, 본전 승격 배수, 채널 저가, 기대 구성 선)
        (0, None, None, 1.5, 10_100, {"hard": 9_100, "breakeven": None, "trail": None, "channel": None}),
        (1, 10_600.0, 200.0, 1.5, 10_100, {"hard": 9_600, "breakeven": 10_000, "trail": 10_240, "channel": 10_100}),
        (2, 10_200.0, 200.0, 1.5, 10_100, {"hard": 9_600, "breakeven": None, "trail": 9_840, "channel": 10_100}),
        (2, 10_050.0, 200.0, 0.0, None, {"hard": 9_600, "breakeven": 10_000, "trail": 9_690, "channel": None}),
        (3, None, 200.0, 1.5, 9_000, {"hard": 9_600, "breakeven": None, "trail": None, "channel": 9_000}),
    ],
)
def test_r4a_etf_holding_lines_match_engine(engine, mon, bars, hsb, n, be_atr, chan, expect):
    etf = _sid(engine, "etf_trend")
    etf.config.params["breakeven_promote_atr"] = be_atr
    etf._bars_since_buy[ETF_HELD] = bars
    for d, v in ((etf._hsb_closed, hsb), (etf._entry_atr, n), (etf._channel_low, chan)):
        d.pop(ETF_HELD, None)
        if v is not None:
            d[ETF_HELD] = v
    eff = etf.get_effective_stop_price(ETF_HELD)
    h = _data(mon)["strategies"]["etf_trend"]["holdings"][ETF_HELD]

    assert h["effective_stop"] == eff, "실효 손절선은 엔진 `get_effective_stop_price` 그대로"
    lines = h["lines"]
    assert set(lines) == {"hard", "breakeven", "trail", "channel"}
    for k, v in expect.items():
        if v is None:
            assert lines[k] is None, (k, lines[k])
        else:
            assert lines[k] is not None and abs(lines[k] - v) <= 1, (k, lines[k], v)
    active = [v for v in lines.values() if v is not None]
    assert abs(max(active) - eff) <= 1, "활성 구성 선의 최댓값 == 엔진 실효선(±1원)"
    assert h["bars_since_buy"] == bars and h["entry_n"] == n and h["hsb_closed"] == hsb
    assert h["breakout_fail"]["line"] == 9_900.0
    assert h["breakout_fail"]["active"] is (bars >= etf.config.params["breakout_fail_min_bars"])


def test_r4b_donchian_arm_matches_exit_lines(engine, mon):
    from src.routes import balance

    dc = _sid(engine, "donchian_swing")
    pos = dc.state.positions[DC_HELD]
    r = dc._kk_r(pos.buy_price, dc._entry_atr[DC_HELD])  # max(8%×100000, 1.5×3000) = 8000
    arm = int(math.ceil(pos.buy_price + dc._kk("kk_breakeven_r") * r))  # 124000
    for high in (arm - 1, arm):  # 1원 아래 = 미무장 / 바로 그 가격 = 무장
        pos.high_since_buy = high
        mon._monitor_cache = None
        h = _data(mon)["strategies"]["donchian_swing"]["holdings"][DC_HELD]
        kk_armed, kk_arm = balance._exit_lines_kk(dc, "donchian_swing", DC_HELD, pos)
        stop, armed, channel = dc._kk_exit_lines(DC_HELD, pos)
        assert h["armed"] is kk_armed is armed
        assert h["arm_price"] == kk_arm
        assert h["stop"] == pytest.approx(stop) and h["channel"] == channel
        assert h["r_won"] == pytest.approx(r)
        assert h["target_1r"] == pytest.approx(pos.buy_price + dc._kk("kk_time_exit_min_r") * r)
        assert h["reached_1r"] is (pos.high_since_buy >= h["target_1r"])
        assert (h["time_exit_bars"], h["max_hold_bars"]) == (dc._kk("kk_time_exit_bars"), dc._kk("kk_max_hold_bars"))


@pytest.mark.parametrize(
    "buy_date,high_offset_r",
    [
        # 거래일 캐시는 10-08 까지 + 오늘(10-12) 하루 · 09-24·09-25·10-05 휴장 → 09-14 매수 = 16영업일
        (date(2026, 9, 14), 0.5),   # 16일 · due 3 · +1R 미도달 → 아직
        (date(2026, 9, 9), 0.5),    # 18일 · due 1 → 아직(경계 하나 앞)
        (date(2026, 9, 8), 0.5),    # 19일 · due 0 → 오늘 15:20 대상
        (date(2026, 9, 8), 1.2),    # 19일이지만 +1R 넘음 → 면제
        (date(2026, 9, 1), 0.5),    # 24일 · due < 0 → 대상
        (date(2026, 10, 6), 0.0),   # 갓 산 종목
    ],
)
def test_r4c_donchian_time_exit_due_agrees_with_check_force_clear(engine, mon, buy_date, high_offset_r):
    dc = _sid(engine, "donchian_swing")
    pos = dc.state.positions[DC_HELD]
    pos.buy_date = buy_date
    r = dc._kk_r(pos.buy_price, dc._entry_atr[DC_HELD])
    pos.high_since_buy = int(pos.buy_price + high_offset_r * r)
    h = _data(mon)["strategies"]["donchian_swing"]["holdings"][DC_HELD]

    days_held, fb = dc._business_days_held(buy_date, TODAY)
    assert (h["days_held"], h["days_fallback"]) == (days_held, fb)
    due = h["time_exit_bars"] - 1 - h["days_held"]
    due_today = (due <= 0 and not h["reached_1r"]) or h["days_held"] >= h["max_hold_bars"] - 1
    assert (DC_HELD in dc.check_force_clear()) is due_today, (buy_date, high_offset_r, h)


def test_r4d_donchian_daily_entries_extra(engine, mon):
    from src.engine.strategy_base import Position

    dc = _sid(engine, "donchian_swing")
    dc.state.positions["035420"] = Position("035420", 50_000, 2, "O-n", "donchian_swing", TODAY, 50_000)
    dc.state.pending_buys.add("051910")
    extra = _data(mon)["strategies"]["donchian_swing"]["extra"]
    assert extra["daily_entries"] == {"count": 2, "cap": dc._kk("max_daily_entries")}, (
        "오늘 매수일 보유 + 주문 중(엔진 `_kk_daily_cap_blocks` 와 같은 합) — 어제 보유는 세지 않는다")


def test_r4e_donchian_candidate_r_and_design_lot(engine, mon):
    dc = _sid(engine, "donchian_swing")
    c = _data(mon)["strategies"]["donchian_swing"]["candidates"][DC_CAND]
    info = dc._candidates[DC_CAND]
    r = dc._kk_r(info["prev_close"], info["atr"])
    assert c["r_won"] == pytest.approx(r)
    assert c["r_pct"] == pytest.approx(r / info["prev_close"] * 100)
    assert c["design_lot"] == dc._kk_design_lot(info["prev_close"], DC_CAND, 1.0)[0]


def test_r4f_vcp_bfb_latch_and_first_cross(engine, mon):
    s = _data(mon)["strategies"]
    v = s["vcp_breakout"]["candidates"][VCP_A]
    assert datetime.fromisoformat(v["latch_armed_at"]) == datetime(2026, 10, 12, 9, 10, 0, tzinfo=KST)
    assert v["first_cross_at"] == "09:09:58" and v["max"] == 10_250
    b = s["bull_flag_breakout"]["candidates"][BFB_A]
    assert datetime.fromisoformat(b["latch_armed_at"]) == datetime(2026, 10, 12, 9, 11, 0, tzinfo=KST)


# ── R5 사유 사상 ──────────────────────────────────────────────────────────────

def test_r5a_etf_skip_reasons_count_tickers(engine, mon):
    sk = _data(mon)["strategies"]["etf_trend"]["skips"]
    assert sk["known"] is True and sk["day"] == "2026-10-12"
    assert sk["counts"] == {"gap_up": 1, "collapse": 1, "cluster_held": 1}
    assert {t: set(v) for t, v in sk["by_ticker"].items()} == {ETF_A: {"gap_up", "collapse"}, ETF_B: {"cluster_held"}}


def test_r5b_vcp_bfb_gate_caps_by_ticker(engine, mon):
    s = _data(mon)["strategies"]
    v = s["vcp_breakout"]["skips"]
    assert v["known"] is True and v["counts"] == {"no_data": 1, "latch_armed": 1}
    assert {t: set(x) for t, x in v["by_ticker"].items()} == {VCP_A: {"no_data", "latch_armed"}}
    b = s["bull_flag_breakout"]["skips"]
    assert b["counts"] == {"seen": 1, "retreat": 1}


def test_r5c_vcp_counts_are_tickers_not_events(engine, mon):
    vcp = _sid(engine, "vcp_breakout")
    vcp._gate_emit_capped = {("A1", "no_data"), ("A2", "no_data"), ("A2", "reject_ext")}
    assert _data(mon)["strategies"]["vcp_breakout"]["skips"]["counts"] == {"no_data": 2, "reject_ext": 1}


def test_r5e_vcp_bfb_exclude_invariant_sentinel_ticker(engine, mon):
    """cycle418-M L3 — `_invariant_` 는 `[ext_cap_warn]` 관측용 센티널(진짜 종목이 아니다,
    `bull_flag_breakout.py`/`vcp_breakout.py` 의 `_gate_should_emit("_invariant_", "ext_cap_warn")`).
    `_monitor_skips` 가 이 ticker 를 걸러내지 않으면 화면이 가짜 종목 1건을 세게 된다.
    `latch_released:<reason>` 접두 키는 **진짜 종목**의 사유라 그대로 남는다(프론트가 번역)."""
    vcp = _sid(engine, "vcp_breakout")
    vcp._gate_emit_capped = {
        (VCP_A, "no_data"),
        ("_invariant_", "ext_cap_warn"),
        (VCP_A, "latch_released:level_moved"),
    }
    sk = _data(mon)["strategies"]["vcp_breakout"]["skips"]
    assert "_invariant_" not in sk["by_ticker"]
    assert "ext_cap_warn" not in sk["counts"]
    assert sk["counts"] == {"no_data": 1, "latch_released:level_moved": 1}


def test_r5d_donchian_two_caps_and_unknown_strategies(engine, mon):
    s = _data(mon)["strategies"]
    d = s["donchian_swing"]["skips"]
    assert d["known"] is True
    assert d["counts"] == {"kk_lot_zero": 1, "daily_entry_cap": 1}
    assert {t: set(x) for t, x in d["by_ticker"].items()} == {"005380": {"kk_lot_zero"}, "035720": {"daily_entry_cap"}}
    for sid in ("kojiro", "momentum", "volatility_breakout", "long_tail_volatility"):
        assert s[sid]["skips"].get("known") is False, f"{sid} — 사유를 기록하지 않는 전략은 known=false(0 으로 쓰지 않는다)"


# ── R6 etf 예상 수량 ──────────────────────────────────────────────────────────

def test_r6a_etf_design_qty_equals_pure_turtle_qty(engine, mon):
    etf = _sid(engine, "etf_trend")
    cands = _data(mon)["strategies"]["etf_trend"]["candidates"]
    for t in (ETF_A, ETF_B):
        info = etf._candidates[t]
        assert cands[t]["design_qty"] == etf._pure_turtle_qty(info["prev_close"], info)
        assert cands[t]["design_qty"] > 0
        for k in ("line", "prev_close", "n", "atr20", "tv20"):
            assert cands[t][k] == info[k], (t, k)
    assert cands[ETF_B]["cluster_blocked"] is True and cands[ETF_B]["cluster_partners"] == [ETF_HELD]
    assert cands[ETF_A]["cluster_blocked"] is False and cands[ETF_A]["cluster_partners"] == []


@pytest.mark.parametrize("budget,sizing", [(0, "turtle"), (10_000_000, "position_ratio")])
def test_r6b_etf_design_qty_zero_when_no_budget_or_bad_sizing(engine, mon, budget, sizing):
    etf = _sid(engine, "etf_trend")
    etf.state.total_investment = budget
    etf.config.params["sizing_mode"] = sizing
    for t, c in _data(mon)["strategies"]["etf_trend"]["candidates"].items():
        assert c["design_qty"] == 0, (t, budget, sizing)


# ── R8 성능 ───────────────────────────────────────────────────────────────────

def test_r8_assembly_under_50ms_for_8x50x6(engine, mon):
    # freezegun 은 `time.perf_counter` 도 멈춘다 — 실제 시계로 잰다(멈춘 시계면 0ms 로 공허하게 통과).
    from freezegun.api import real_perf_counter

    from src.engine.strategy_base import Position

    for s in engine.registry.all():
        base = dict(next(iter(s._candidates.values()))) if getattr(s, "_candidates", None) else None
        if base is not None:
            s._candidates = {f"{900000 + i:06d}": dict(base) for i in range(50)}
            s._scanned_tickers = list(s._candidates)
        s.state.positions.clear()
        for i in range(6):
            t = f"{800000 + i:06d}"
            p = Position(t, 10_000, 3, f"O-{i}", s.strategy_id, date(2026, 9, 21), 10_500)
            s.state.positions[t] = p
            if hasattr(s, "_entry_atr"):
                s._entry_atr[t] = 200.0
            if hasattr(s, "_position_atr"):
                s._position_atr[t] = 200.0
    best = math.inf
    for _ in range(5):
        mon._monitor_cache = None
        t0 = real_perf_counter()
        body = _call(mon)
        best = min(best, real_perf_counter() - t0)
        assert body["success"] is True
    assert best < 0.050, f"조립 {best * 1000:.1f}ms — 5초 폴링 엔드포인트가 이벤트 루프를 붙잡으면 안 된다"
