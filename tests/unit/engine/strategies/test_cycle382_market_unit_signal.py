"""cycle382 Red — 시장 유닛: 신호 시점 필터 `_market_unit_blocks_entry` (R32~R40).

명세 = `_workspace/red/cycle382_market_unit_spec.md` §6 · §7 · §11.2(신호)

계약 요약(§6):
- `enforce` ∧ m<1 에서 줄인 랏으로 **살 수 없으면**(`zero_state`·`rounds_to_zero`·`no_fallback`)
  `check_buy_signal` 이 `Signal.NONE` — 주문 엔진에 닿지 않으므로 「매수 수량 0 → 900s 쿨다운
  (투자금 …)」 로 **오귀인되지 않는다**. `funds`(잔여 부족)는 거르지 않는다(기존 자금 경로가 맞다).
- 필터는 부작용 0 — `_bought_today`·`buy_signals`·`_position_setup`·`_breakout_high`·`_position_atr`·
  `_position_sectors`·`_vol_latch` 를 건드리지 않는다. 그래서 킬스위치(PUT `off`)가 다음 평가부터 먹는다.
- 자리 = 각 전략 「매수 확정 블록」 바로 앞(kojiro·donchian 은 마지막 `_bought_today.add` 앞,
  BFB·VCP 는 `_evaluate_vol_gate` 추격 상한 거부 뒤·`latch_age_sec = 0` 앞). BFB·VCP 는
  `_prev_price` 가 이미 이번 틱 값이라 끈 뒤 첫 틱이 **거짓 교차가 되지 않는다**.
- 줄 = `[market_unit] … skip=1 reason=<…> where=signal` 1회/(ticker)/일.

시계: kojiro = aware KST 09:10 · donchian = naive 09:10 · BFB/VCP = naive 10:00 (날짜는 모두 09-28).
Red 유효성: `_market_unit_*`·leaf 부재 → 스냅샷을 심는 `seed` 에서 `[Red]` 로 실패한다.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from src.engine import tick_volume
from src.engine.strategy_base import Signal
from tests.unit.engine._cycle382_support import (
    T, TURTLE4, field, fnum, kst_naive_datetime_class, lines, make, need_base, open_info, seed,
    strategy_module,
)

pytestmark = pytest.mark.unit

_FREEZE = {
    "kojiro": "2026-09-28T09:10:00+09:00",
    "donchian_swing": "2026-09-28 09:10:00",
    "bull_flag_breakout": "2026-09-28 10:00:00",
    "vcp_breakout": "2026-09-28 10:00:00",
}
_TOUCHED = ("_bought_today", "_position_setup", "_breakout_high", "_position_atr",
            "_position_sectors", "_vol_latch")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, caplog):
    tick_volume.reset_for_test()
    monkeypatch.setattr("src.engine.scanner.ticker_prices", {}, raising=False)
    try:
        from src.engine import account_risk_watcher

        account_risk_watcher.reset_state_for_test()
    except Exception:
        pass
    open_info(caplog)
    yield
    tick_volume.reset_for_test()


# ===========================================================================
# 전략별 「다른 게이트는 모두 통과」 입력
# ===========================================================================
class Ready:
    """sid 별 신호 평가 준비. ``level`` = 돌파선(BFB flag_high · VCP base_high)."""

    def __init__(self, sid: str, *, mode: str = "enforce", budget: int | None = None,
                 sizing: str | None = None, price: int | None = None, level: int | None = None,
                 atr=None, vol: int | None = None) -> None:
        self.sid = sid
        if sid == "kojiro":
            self.s = make(sid, budget=budget or 2_000_000, mode=mode, sizing_mode=sizing or "turtle",
                          risk_pct=0.005, position_ratio=0.166, max_positions=6)
            self.s._candidates[T] = {"stage": 1, "prev_close": 50_000, "atr": 1_000.0 if atr is None else atr,
                                     "sector": "반도체", "name": "합성"}
            self.price, self.open = price or 50_500, 50_000
            self.level = None
        elif sid == "donchian_swing":
            self.s = make(sid, budget=budget or 1_000_000, mode=mode, sizing_mode=sizing or "turtle",
                          risk_pct=0.01, position_ratio=0.2, max_positions=5)
            self.s._candidates[T] = {"prev_close": 10_000, "atr": 500 if atr is None else atr,
                                     "ema60": 9_000, "donchian_high": 10_000}
            self.price, self.open = price or 10_100, 10_050
            self.level = None
        elif sid == "bull_flag_breakout":
            self.level = level or 136_200
            self.s = make(sid, budget=budget or 10_000_000, mode=mode, sizing_mode=sizing or "position_ratio",
                          risk_pct=0.01, position_ratio=0.25, max_positions=4,
                          breakout_retention_minutes=0)
            self.s._candidates[T] = {
                "pole_start": 100_000, "pole_high": 130_000, "flag_high": self.level,
                "flag_low": int(self.level * 0.87), "flag_avg_volume": 10_000.0, "pole_len": 5,
                "flag_len": 9, "atr14": 3_000 if atr is None else atr, "prev_close": self.level - 3_000,
            }
            self.price, self.open = price or int(self.level * 1.006), int(self.level * 0.95)
            tick_volume.record_acml_vol(T, 50_000 if vol is None else vol)       # 임계 20,000
        elif sid == "vcp_breakout":
            self.level = level or 50_000
            self.s = make(sid, budget=budget or 10_000_000, mode=mode, sizing_mode=sizing or "turtle",
                          risk_pct=0.01, position_ratio=0.2, max_positions=5)
            self.s._candidates[T] = {
                "base_high": self.level, "base_low": int(self.level * 0.9), "avg_volume_20": 100_000,
                "atr14": 1_500 if atr is None else atr, "ema50": int(self.level * 0.94),
            }
            self.price, self.open = price or int(self.level * 1.01), int(self.level * 0.98)
            tick_volume.record_acml_vol(T, 200_000 if vol is None else vol)      # 임계 150,000
        else:  # pragma: no cover
            raise AssertionError(sid)

    def signal(self, *, cross: bool = True, price: int | None = None) -> Signal:
        """BFB·VCP 는 ``cross=True`` 면 직전 틱을 돌파선 바로 아래로 둬 edge-crossing 을 만든다."""
        if self.level is not None and cross:
            self.s._prev_price[T] = self.level - 100
        return self.s.check_buy_signal(T, price if price is not None else self.price, self.open)

    def touched(self) -> dict:
        out = {}
        for name in _TOUCHED:
            v = getattr(self.s, name, None)
            if isinstance(v, dict):
                out[name] = {k: (dict(x) if isinstance(x, dict) else x) for k, x in v.items()}
            elif isinstance(v, set):
                out[name] = set(v)
        out["buy_signals"] = len(self.s.state.buy_signals)
        return out


@contextmanager
def _clock(sid: str):
    with freeze_time(_FREEZE[sid]):
        yield


def _sig_lines(caplog):
    return [ln for ln in lines(caplog, "[market_unit]") if field(ln, "where") == "signal"]


# ===========================================================================
# R32 — m=0 필터 · 줄 1회 · 부작용 0
# ===========================================================================
@pytest.mark.parametrize("sid", TURTLE4)
def test_r32_zero_state_filters_signal_without_side_effects(caplog, sid):
    with _clock(sid):
        r = Ready(sid)
        seed(r.s, 0.0)
        before = r.touched()
        assert r.signal() == Signal.NONE, "m=0 enforce 인데 BUY(M16)"
        assert r.touched() == before, "신호 필터가 상태를 바꿨다(킬스위치가 다음 평가에 안 먹는다)"
        ls = _sig_lines(caplog)
        assert len(ls) == 1, ls
        ln = ls[0]
        assert field(ln, "strategy") == sid and field(ln, "ticker") == T
        assert (field(ln, "state"), fnum(ln, "m"), field(ln, "mode")) == ("down_falling", 0.0, "enforce")
        assert (field(ln, "skip"), field(ln, "reason")) == ("1", "zero_state")
        assert r.signal() == Signal.NONE
        assert len(_sig_lines(caplog)) == 1, "같은 종목 두 번째 평가에 줄이 또 나왔다(M23)"
        assert r.touched() == before


# ===========================================================================
# R34 — 양성 대조 (m=1 enforce → 현행 BUY · 부수효과 그대로)
# ===========================================================================
@pytest.mark.parametrize("sid", TURTLE4)
def test_r34_positive_control_m1_buys_with_existing_side_effects(caplog, sid):
    with _clock(sid):
        r = Ready(sid)
        seed(r.s, 1.0)
        assert r.signal() == Signal.BUY
        assert T in r.s._bought_today
        assert len(r.s.state.buy_signals) == 1
        if sid == "kojiro":
            assert r.s._position_atr[T] == 1_000.0 and r.s._position_sectors[T] == "반도체"
        elif sid == "donchian_swing":
            assert r.s._breakout_high[T] == 10_000
        else:
            assert T in r.s._position_setup and T not in r.s._vol_latch
        assert _sig_lines(caplog) == []


@pytest.mark.parametrize("sid", TURTLE4)
def test_r34_reduced_but_buyable_is_not_filtered(caplog, sid):
    with _clock(sid):
        r = Ready(sid)
        seed(r.s, 0.5)
        assert r.signal() == Signal.BUY, "½ 로 줄여도 살 수 있는데 걸렀다"
        assert _sig_lines(caplog) == []


# ===========================================================================
# R35 — ½ 날 줄여서 0주 · 폴백 없음
# ===========================================================================
@pytest.mark.parametrize(
    "price,level,reason",
    [(150_000, 146_000, "rounds_to_zero"), (300_000, 292_000, "no_fallback")],
)
def test_r35_bfb_ratio_half_day_unbuyable_is_filtered(caplog, price, level, reason):
    with _clock("bull_flag_breakout"):
        r = Ready("bull_flag_breakout", budget=1_000_000, price=price, level=level)
        seed(r.s, 0.5)
        assert r.signal() == Signal.NONE
        ln = _sig_lines(caplog)[0]
        assert (field(ln, "reason"), field(ln, "skip"), field(ln, "path")) == (reason, "1", "ratio")
        if reason == "no_fallback":
            assert field(ln, "fallback") == "one_share"


def test_r35_donchian_turtle_atr_missing_half_day_is_no_fallback(caplog):
    """cycle405 — ATR 결측이면 설계 랏 0 → 어느 날이든 신호 단계 NONE(비중 낙하 없음).

    m=1 날은 시장 유닛 필터가 아니라 설계 랏 0 거름(`[donchian_kk_lot_zero]`)이 받는다.
    """
    caplog.set_level(logging.INFO)
    with _clock("donchian_swing"):
        r = Ready("donchian_swing", atr=0)
        seed(r.s, 0.5)
        assert r.signal() == Signal.NONE
        r1 = Ready("donchian_swing", atr=0)
        seed(r1.s, 1.0)
        assert r1.signal() == Signal.NONE, "m=1 의 데이터 결손도 사지 않는다(깡토식 — 비중 낙하 없음)"
        zero = [rec.getMessage() for rec in caplog.records
                if rec.levelno >= logging.INFO and rec.getMessage().startswith("[donchian_kk_lot_zero] ")]
        assert zero, "m=1 의 설계 랏 0 은 `[donchian_kk_lot_zero]` 로 남는다"


# ===========================================================================
# R36 — 자금 부족은 거르지 않는다
# ===========================================================================
def test_r36_funds_shortage_is_not_filtered(caplog):
    with _clock("bull_flag_breakout"):
        r = Ready("bull_flag_breakout", budget=1_000_000, price=100_000, level=97_000)
        r.s.state.pending_buy_amounts["OTHER"] = 950_000
        seed(r.s, 0.5)
        assert r.signal() == Signal.BUY, "잔여 < 가격(funds)을 시장 유닛이 걸렀다(M24)"
        assert _sig_lines(caplog) == []
        r0 = Ready("bull_flag_breakout", budget=1_000_000, price=100_000, level=97_000)
        r0.s.state.pending_buy_amounts["OTHER"] = 950_000
        seed(r0.s, 0.0)
        assert r0.signal() == Signal.NONE
        assert field(_sig_lines(caplog)[0], "reason") == "zero_state"


# ===========================================================================
# R37 — shadow 는 거르지 않는다
# ===========================================================================
@pytest.mark.parametrize("sid", TURTLE4)
def test_r37_shadow_never_filters(caplog, sid):
    with _clock(sid):
        r = Ready(sid, mode="shadow")
        seed(r.s, 0.0)
        assert r.signal() == Signal.BUY, "shadow 인데 신호를 걸렀다(M17)"
        assert _sig_lines(caplog) == []


# ===========================================================================
# R38 — 킬스위치 즉시 (재준비 없음)
# ===========================================================================
@pytest.mark.parametrize("sid", TURTLE4)
def test_r38_kill_switch_takes_effect_on_next_evaluation(sid):
    with _clock(sid):
        r = Ready(sid)
        seed(r.s, 0.0)
        assert r.signal() == Signal.NONE
        r.s.config.params["market_unit_mode"] = "off"
        assert r.signal() == Signal.BUY, "PUT off 뒤 다음 평가가 BUY 가 아니다(필터가 상태를 남겼다 — M18)"


# ===========================================================================
# R39 — BFB·VCP 기준가 얼음 없음 / 래치 대조
# ===========================================================================
@pytest.mark.parametrize("sid", ["bull_flag_breakout", "vcp_breakout"])
def test_r39_no_false_crossing_after_kill_switch(sid):
    with _clock(sid):
        r = Ready(sid)
        seed(r.s, 0.0)
        assert r.signal() == Signal.NONE
        assert r.s._prev_price[T] == r.price, "걸러진 틱이 기준가를 갱신하지 않았다(필터가 `_prev_price` 갱신 앞 — M18)"
        assert T not in r.s._vol_latch
        r.s.config.params["market_unit_mode"] = "off"
        assert r.signal(cross=False) == Signal.NONE, "끈 뒤 첫 틱이 거짓 교차로 샀다"
        assert r.signal(cross=False, price=r.level - 500) == Signal.NONE
        assert r.signal(cross=False) == Signal.BUY, "진짜 재교차에서는 사야 한다"


@pytest.mark.parametrize("sid", ["bull_flag_breakout", "vcp_breakout"])
def test_r39_armed_latch_survives_filter_and_fires_after_off(sid):
    with _clock(sid):
        r = Ready(sid, vol=1)                              # 첫 교차 = 거래량 부족 → 래치 무장
        seed(r.s, 0.0)
        assert r.signal() == Signal.NONE
        assert T in r.s._vol_latch, "전제 — 거래량 부족 교차가 래치를 무장해야 한다"
        tick_volume.record_acml_vol(T, 10_000_000)
        assert r.signal(cross=False) == Signal.NONE, "래치 재평가 경로도 m=0 이면 걸러야 한다"
        assert T in r.s._vol_latch, "필터가 래치를 해제했다(부작용)"
        r.s.config.params["market_unit_mode"] = "off"
        assert r.signal(cross=False) == Signal.BUY


# ===========================================================================
# R40 — 첫 문장 게이트 순서 보존
# ===========================================================================
@pytest.mark.parametrize("sid", TURTLE4)
def test_r40_account_soft_gate_short_circuits_market_unit(monkeypatch, sid):
    need_base()
    with _clock(sid):
        r = Ready(sid)
        seed(r.s, 0.0)
        calls: list = []
        orig = r.s._market_unit_blocks_entry

        def _spy(*a, **k):
            calls.append(a)
            return orig(*a, **k)

        view_calls: list = []
        orig_view = r.s._market_unit_view

        def _vspy(*a, **k):
            view_calls.append(a)
            return orig_view(*a, **k)

        monkeypatch.setattr(r.s, "_market_unit_blocks_entry", _spy)
        monkeypatch.setattr(r.s, "_market_unit_view", _vspy)
        monkeypatch.setattr(r.s, "_account_soft_gate_blocked", lambda ticker=None: True)
        assert r.signal() == Signal.NONE
        assert (calls, view_calls) == ([], []), "첫 문장 게이트보다 시장 유닛이 먼저 불렸다"
        monkeypatch.setattr(r.s, "_account_soft_gate_blocked", lambda ticker=None: False)
        assert r.signal() == Signal.NONE
        assert len(calls) == 1, "양성 대조 — 게이트 통과 시 시장 유닛 필터가 정확히 1회 불려야 한다"


# cycle405 — donchian 은 설계 랏 자체가 m 을 품는다(§5). `_market_unit_lots` 를 터뜨리면 시장 유닛
# 필터는 fail-open 하지만 m=0 설계 랏 0 거름이 그대로 NONE 을 낸다 — 옳은 동작이다. donchian 의
# fail-open 계약은 아래 `test_r40b_donchian_view_exception_fails_open_to_m1` 이 m 원천(view) 예외로 잰다.
@pytest.mark.parametrize("sid", [x for x in TURTLE4 if x != "donchian_swing"])
def test_r40_signal_helper_exception_fails_open(monkeypatch, caplog, sid):
    """명세 §6 — 필터 헬퍼 예외는 `[market_unit_error] where=signal` + 거르지 않는다(현행 BUY)."""
    need_base()
    with _clock(sid):
        r = Ready(sid)
        seed(r.s, 0.0)

        def _boom(*a, **k):
            raise RuntimeError("lots failed")

        monkeypatch.setattr(r.s, "_market_unit_lots", _boom)
        assert r.signal() == Signal.BUY, "필터 예외가 매수를 막았다(fail-closed)"
        errs = lines(caplog, "[market_unit_error]", min_level=logging.WARNING)
        assert len(errs) == 1 and field(errs[0], "where") == "signal" and field(errs[0], "strategy") == sid


def test_r40b_donchian_view_exception_fails_open_to_m1(monkeypatch, caplog):
    """cycle405 — 시장 유닛 판정(view)이 터지면 donchian 은 m=1 로 산다(신호 BUY · 수량 = m=1 설계 랏)."""
    need_base()
    with _clock("donchian_swing"):
        r = Ready("donchian_swing")
        seed(r.s, 0.0)

        def _boom(*a, **k):
            raise RuntimeError("view failed")

        monkeypatch.setattr(r.s, "_market_unit_view", _boom)
        assert r.signal() == Signal.BUY, "m 판정 예외가 매수를 막았다(fail-closed)"
        # 예산 1,000,000 · risk 0.01 · R = max(808, 750) → floor(10,000 / 808) = 12 (명목 상한 19)
        r.s.state.pending_buys.clear()
        assert r.s.calc_buy_quantity(r.price, T) == 12


# ===========================================================================
# R33 — 실제 매수 경로: 「투자금 부족」 으로 기록되지 않는다
# ===========================================================================
async def _tick_path(monkeypatch, r: Ready):
    from src.engine import risk as risk_mod
    from src.engine import scanner
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    monkeypatch.setattr(risk_mod.session_tracker, "is_tradable", lambda sid, params: True)
    monkeypatch.setattr(scanner, "ticker_prev_close", {T: r.level - 3_000})
    monkeypatch.setattr(scanner, "ticker_prices", {})
    monkeypatch.setattr(scanner, "ticker_last_tick", {})
    reg = StrategyRegistry()
    reg.register(r.s)
    oe = MagicMock()
    oe.execute_buy = AsyncMock()
    oe.execute_sell = AsyncMock()
    oe._selling = set()
    calc: list = []
    orig = r.s.calc_buy_quantity
    monkeypatch.setattr(r.s, "calc_buy_quantity", lambda *a, **k: (calc.append(a), orig(*a, **k))[1])
    rm = RiskManager(registry=reg, order_engine=oe)
    r.s._prev_price[T] = r.level - 100
    await rm.on_tick(ticker=T, current_price=r.price, open_price=r.open, change_rate=1.0,
                     acml_vol=10_000_000)
    return oe, calc


@pytest.mark.parametrize("sid", ["bull_flag_breakout", "vcp_breakout"])
@pytest.mark.parametrize("m,buys", [(0.0, 0), (1.0, 1)], ids=["zero_state", "positive_control"])
async def test_r33_tick_path_zero_state_never_reaches_order_engine(monkeypatch, caplog, sid, m, buys):
    with _clock(sid):
        r = Ready(sid)
        seed(r.s, m)
        oe, calc = await _tick_path(monkeypatch, r)
        assert oe.execute_buy.await_count == buys
        if buys == 0:
            assert calc == [], "m=0 신호가 수량 산출까지 갔다"
            assert r.s.state.signal_count_today == 0
            assert r.s.state.is_low_funds_blocked(T, _time.time()) is False, "「투자금 부족」 쿨다운으로 오귀인"
            assert len(_sig_lines(caplog)) == 1
            assert not [x for x in caplog.records if "매수 수량 0" in x.getMessage()]


async def _swing_path(monkeypatch, r: Ready):
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_registry import StrategyRegistry

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = StrategyRegistry()
    sched.registry.register(r.s)
    sched._pending_next_day_clear = set()
    sched._running = True
    oe = MagicMock()
    oe.execute_buy = AsyncMock()
    sched.order_engine = oe
    r.s._scanned_tickers = [T]
    fetched: list = []

    async def _fetch(t):
        fetched.append(t)
        sched._running = False            # 이번 한 바퀴만
        return {"stck_prpr": str(r.price), "stck_oprc": str(r.open)}

    monkeypatch.setattr("src.api.condition.fetch_stock_detail", _fetch)
    await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=10.0)
    assert fetched == [T], "스윙 폴이 후보를 조회하지 않았다 — 시나리오 전제 붕괴"
    return oe


@pytest.mark.parametrize("sid", ["kojiro", "donchian_swing"])
@pytest.mark.parametrize("m,buys", [(0.0, 0), (1.0, 1)], ids=["zero_state", "positive_control"])
async def test_r33_swing_poll_zero_state_never_reaches_order_engine(monkeypatch, caplog, sid, m, buys):
    # donchian 시간 가드는 naive, 폴 루프는 aware. freezegun 은 모듈 속성 캐시로 freeze 시작 때
    # `datetime` 이름을 다시 FakeDatetime 으로 덮으므로 **freeze 안에서** 바꾸고 **freeze 안에서** 되돌린다
    # (바깥 monkeypatch 로 두면 teardown 이 FakeDatetime 을 영구히 남긴다).
    with freeze_time("2026-09-28T09:10:00+09:00", real_asyncio=True):
        with monkeypatch.context() as mp:
            if sid == "donchian_swing":
                mp.setattr(strategy_module(sid), "datetime", kst_naive_datetime_class())
            r = Ready(sid)
            seed(r.s, m)
            oe = await _swing_path(mp, r)
            assert oe.execute_buy.await_count == buys
            if buys == 0:
                assert r.s.state.signal_count_today == 0
                assert r.s.state.is_low_funds_blocked(T, _time.time()) is False
                assert len(_sig_lines(caplog)) == 1
                assert T not in r.s._bought_today


def test_r33_marker_logger_is_market_unit(caplog):
    """모든 시장 유닛 줄은 로거 `src.engine.market_unit` 하나로 나간다(명세 §3.1)."""
    with _clock("kojiro"):
        r = Ready("kojiro")
        seed(r.s, 0.0)
        r.signal()
        recs = [x for x in caplog.records if x.getMessage().startswith("[market_unit] ")]
        assert recs and {x.name for x in recs} == {"src.engine.market_unit"}
        assert all(x.levelno == logging.INFO for x in recs)
