"""cycle384 Red — 공통 `buy_paused`: 게이트 배선 · 청산 무접촉 · 마커 · 상호작용 (T01~T13 · T24~T32).

명세 정본 = `_workspace/red/cycle384_buy_paused_spec.md` §2 · §3 · §5 · §6 · §9
사용자 결정(2026-09-27 「09-27 결정 세트」) = 「돈키언 신규매수 중지」 — 보유분은 원래 청산 규약대로
자연 소진. `enabled`/`weight` 로는 못 한다(끄는 순간 보유분 손절이 멈춘다 — 루트 금기).

## 막는 자리

`StrategyBase._account_soft_gate_blocked` 의 **두 번째 문장**(첫 문장 = cycle369 상태 차단, J25):

    if self._status_buy_blocked(ticker):
        return True
    if self._buy_paused_blocked(ticker):      # cycle384
        return True
    try:  ... 계좌 SOFT (byte 동일)

7전략 `check_buy_signal` 이 모두 이 게이트를 지난다(첫 문장 5 · 발사 직전 2 — cycle233 규약).
그래서 전략 7파일에는 `DEFAULT_PARAMS` 한 줄 말고 손대지 않는다.

## 이 파일이 잰 것

- T01~T10 게이트·배선·값 해석(§3 표)
- T11~T13 청산 무접촉(7전략 차분 · `risk.on_tick` · 스윙 폴 하네스)
- T24~T29 마커 두 종(`[buy_paused_config]` 카나리아 · `[buy_paused_skip]`)
- T30~T32 다른 관문과의 관계(시장 유닛 · 상태 차단 · 전략 간 번짐)

해제 첫 틱(거짓 돌파·낡은 래치) = `strategies/test_cycle384_buy_paused_unpause.py`(T14~T23).
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.strategy_base import Position, Signal
from tests.unit.engine._cycle384_support import (
    ALL7,
    DAY,
    NEXT_DAY,
    SB_LOGGER,
    T,
    U,
    V,
    Clock,
    field,
    kst,
    lines,
    need_pause_surface,
    open_info,
    pause,
    ready,
    recs,
    strategy_class,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, caplog):
    from src.engine import scanner, tick_volume

    tick_volume.reset_for_test()
    monkeypatch.setattr(scanner, "ticker_prev_close", {}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prices", {}, raising=False)
    try:
        from src.engine import account_risk_watcher

        account_risk_watcher.reset_state_for_test()
    except Exception:
        pass
    open_info(caplog)
    yield
    tick_volume.reset_for_test()


def _skip_lines(caplog, sid: str | None = None) -> list[str]:
    out = lines(caplog, "[buy_paused_skip]")
    return [ln for ln in out if sid is None or field(ln, "strategy") == sid]


def _cfg_lines(caplog, sid: str | None = None, *, min_level: int = logging.INFO) -> list[str]:
    out = lines(caplog, "[buy_paused_config]", min_level=min_level)
    return [ln for ln in out if sid is None or field(ln, "strategy") == sid]


# ===========================================================================
# T01 — 7전략 DEFAULT_PARAMS["buy_paused"] is False
# ===========================================================================
@pytest.mark.parametrize("sid", ALL7)
def test_t01_default_params_has_buy_paused_false(sid):
    d = strategy_class(sid).DEFAULT_PARAMS
    assert "buy_paused" in d, f"[Red] {sid} DEFAULT_PARAMS 에 buy_paused 없음 — PUT 이 unknown_key 422 가 된다"
    assert d["buy_paused"] is False, f"{sid} 기본값이 False(bool) 가 아니다: {d['buy_paused']!r} (M10)"


@pytest.mark.parametrize("sid", ALL7)
def test_t01b_instance_params_carry_the_default(sid):
    """`__init__` 병합(`{**DEFAULT_PARAMS, **config.params}`)으로 인스턴스 params 에 키가 선다 — PUT 의 전제."""
    from tests.unit.engine._cycle384_support import make

    assert make(sid).config.params.get("buy_paused") is False


# ===========================================================================
# T02 · T03 · T04 — 게이트 순서 (상태 차단 → 멈춤 → 계좌 SOFT)
# ===========================================================================
@pytest.mark.parametrize("sid", ALL7)
def test_t02_status_block_wins_and_pause_is_not_evaluated(sid, monkeypatch):
    need_pause_surface()
    r = ready(sid, monkeypatch)
    pause(r.s)
    calls: list = []

    def _spy(ticker):
        calls.append(ticker)
        return True

    monkeypatch.setattr(r.s, "_status_buy_blocked", lambda ticker: True)
    monkeypatch.setattr(r.s, "_buy_paused_blocked", _spy)
    assert r.s._account_soft_gate_blocked(T) is True
    assert calls == [], "멈춤이 상태 차단보다 먼저 평가됐다(J25 — M02)"

    monkeypatch.setattr(r.s, "_status_buy_blocked", lambda ticker: False)
    assert r.s._account_soft_gate_blocked(T) is True
    assert calls == [T], "양성 대조 — 상태 차단이 없으면 멈춤이 평가돼야 한다"


def test_t03_pause_precedes_account_soft_gate_no_misattribution(monkeypatch, caplog):
    """멈춘 전략에서 `[account_gate_skip]` 이 찍히면 원인이 「계좌 오픈리스크」로 오귀인된다(M03)."""
    from src.engine import account_risk_watcher

    monkeypatch.setattr(account_risk_watcher, "is_soft_gated", lambda *a, **k: True)
    r = ready("donchian_swing", monkeypatch)
    pause(r.s)
    assert r.fire() == Signal.NONE
    assert lines(caplog, "[account_gate_skip]") == [], "멈춘 전략이 계좌 게이트 skip 으로 기록됐다(M03)"
    assert len(_skip_lines(caplog, "donchian_swing")) == 1


def test_t04_unpaused_account_soft_gate_unchanged(monkeypatch, caplog):
    """회귀 — 멈춤이 아니면 계좌 SOFT 게이트는 기존대로 막고 `[account_gate_skip]` 을 남긴다."""
    from src.engine import account_risk_watcher

    monkeypatch.setattr(account_risk_watcher, "is_soft_gated", lambda *a, **k: True)
    r = ready("donchian_swing", monkeypatch)
    assert r.fire() == Signal.NONE
    assert len(lines(caplog, "[account_gate_skip]")) == 1
    assert _skip_lines(caplog) == []


# ===========================================================================
# T05 — 7전략: 멈추지 않으면 BUY 인 입력에서 멈추면 NONE
# ===========================================================================
@pytest.mark.parametrize("sid", ALL7)
def test_t05_positive_control_unpaused_buys(sid, monkeypatch):
    r = ready(sid, monkeypatch)
    r.prime()
    assert r.fire() == Signal.BUY, f"{sid}: 합성 입력이 BUY 를 못 낸다 — 아래 멈춤 단언이 공허해진다"


@pytest.mark.parametrize("sid", ALL7)
def test_t05_paused_blocks_new_buy_signal(sid, monkeypatch):
    r = ready(sid, monkeypatch)
    pause(r.s)
    r.prime()
    before = len(r.s.state.buy_signals)
    assert r.fire() == Signal.NONE, f"{sid}: buy_paused=True 인데 BUY (M01 · M29)"
    assert len(r.s.state.buy_signals) == before, "멈춘 평가가 buy_signals 에 흔적을 남겼다"
    assert r.fire() == Signal.NONE


# ===========================================================================
# T06 — PUT 과 같은 경로(같은 params dict)로 즉시 반영, 재시작·prepare 없음
# ===========================================================================
def test_t06_toggle_takes_effect_on_next_call_without_restart(monkeypatch):
    r = ready("donchian_swing", monkeypatch)
    pause(r.s, True)
    assert r.fire() == Signal.NONE, "켠 직후 다음 평가가 멈추지 않았다(M07 · M25)"
    pause(r.s, False)
    assert r.fire() == Signal.BUY, "끈 직후 다음 평가가 BUY 가 아니다 — 값을 캐시했다(M07)"
    # 반대 방향 — 같은 인스턴스, 다른 후보
    r.s._candidates[U] = dict(r.s._candidates[T])
    pause(r.s, True)
    assert r.s.check_buy_signal(U, 10_600, 10_100) == Signal.NONE
    pause(r.s, False)
    assert r.s.check_buy_signal(U, 10_600, 10_100) == Signal.BUY


# ===========================================================================
# T07 — 수량 단계에 멈춤이 없다 (M04)
# ===========================================================================
@pytest.mark.parametrize("sid", ["donchian_swing", "kojiro", "momentum"])
def test_t07_calc_buy_quantity_is_independent_of_pause(sid, monkeypatch):
    r = ready(sid, monkeypatch)
    q0 = r.s.calc_buy_quantity(r.fire_px, r.t)
    pause(r.s)
    q1 = r.s.calc_buy_quantity(r.fire_px, r.t)
    assert q0 > 0, f"{sid}: 전제 — 수량이 0 이면 비교가 공허하다"
    assert q1 == q0, f"{sid}: 멈춤이 수량을 바꿨다 — 0 반환은 900초 「투자금 부족」 오귀인(M04)"


# ===========================================================================
# T08 — 멈춘 평가 30회 뒤 상태 불변 (M05 · M17)
# ===========================================================================
@pytest.mark.parametrize("sid", ["donchian_swing", "kojiro", "bull_flag_breakout", "vcp_breakout"])
def test_t08_paused_evaluations_leave_no_buy_state(sid, monkeypatch):
    r = ready(sid, monkeypatch)
    pause(r.s)
    bought = set(r.s._bought_today)
    pending = set(r.s.state.pending_buys)
    for _ in range(30):
        r.prime()
        assert r.fire() == Signal.NONE
    assert r.s.state.buy_disabled is False, "일일 손실 래치로 구현했다(M05)"
    assert set(r.s.state.pending_buys) == pending
    assert r.s._bought_today == bought, "멈춤이 _bought_today 에 넣었다 — 같은 날 해제가 무의미(M17)"
    assert r.s.state.is_low_funds_blocked(T, _time.time()) is False
    assert r.s.state.signal_count_today == 0


# ===========================================================================
# T09 — 값 해석표 (명세 §3): `is True` 만 멈춤
# ===========================================================================
_ABSENT = object()
_NOT_PAUSING = [
    pytest.param(False, True, "False", id="false"),
    pytest.param(_ABSENT, True, "absent", id="absent"),
    pytest.param("true", False, "'true'", id="str_true"),
    pytest.param("True", False, "'True'", id="str_True"),
    pytest.param(1, False, "1", id="one"),
    pytest.param(0, False, "0", id="zero"),
    pytest.param(None, False, "None", id="null"),
    pytest.param("false", False, "'false'", id="str_false"),
    pytest.param([], False, "[]", id="empty_list"),
]


@pytest.mark.parametrize("value,valid,raw", _NOT_PAUSING)
def test_t09_non_true_values_do_not_pause(value, valid, raw, monkeypatch, caplog):
    r = ready("donchian_swing", monkeypatch)
    if value is _ABSENT:
        r.s.config.params.pop("buy_paused", None)
    else:
        r.s.config.params["buy_paused"] = value
    assert r.fire() == Signal.BUY, f"{value!r} 가 멈춤으로 읽혔다 — `bool(raw)`(M08) 또는 fail-closed(M09)"
    for _ in range(3):
        r.fire()
    cfg = _cfg_lines(caplog, "donchian_swing")
    assert len(cfg) == 1, f"카나리아는 1회/(전략,값)/일: {cfg}"
    ln = cfg[0]
    assert (field(ln, "paused"), field(ln, "valid"), field(ln, "raw")) == ("0", "1" if valid else "0", raw), ln
    rec = recs(caplog, "[buy_paused_config]")[0]
    want = logging.INFO if valid else logging.WARNING
    assert rec.levelno == want, f"값 {value!r}: 레벨 {rec.levelname} (기대 {logging.getLevelName(want)})"


def test_t09_true_pauses_with_warning_canary(monkeypatch, caplog):
    r = ready("donchian_swing", monkeypatch)
    pause(r.s, True)
    assert r.fire() == Signal.NONE
    cfg = recs(caplog, "[buy_paused_config]")
    assert len(cfg) == 1
    ln = cfg[0].getMessage()
    assert cfg[0].levelno == logging.WARNING
    assert (field(ln, "strategy"), field(ln, "paused"), field(ln, "valid"), field(ln, "raw")) == (
        "donchian_swing", "1", "1", "True")


# ===========================================================================
# T10 — ticker 가 비어도 전략 단위로 멈춘다 (M30)
# ===========================================================================
@pytest.mark.parametrize("tk", [None, ""])
def test_t10_empty_ticker_is_still_paused_without_side_effects(tk, monkeypatch, caplog):
    r = ready("long_tail_volatility", monkeypatch)
    r.s._prev_price[T] = {"main": 10_400}
    pause(r.s)
    assert r.s._account_soft_gate_blocked(tk) is True, "ticker 가 비면 멈춤이 빠졌다(M30)"
    assert r.s._prev_price[T] == {"main": 10_400}, "빈 ticker 로 남의 기준가를 건드렸다"
    assert _skip_lines(caplog) == []
    pause(r.s, False)
    assert r.s._account_soft_gate_blocked(tk) is False


# ===========================================================================
# T11 — 청산 무접촉: 7전략 차분 (M06 · M16 · M26)
# ===========================================================================
_EXIT_PATH = (10_000, 10_700, 11_400, 11_000, 10_600, 10_150, 8_300)


def _exit_state(s) -> dict:
    out: dict = {}
    for name, v in vars(s).items():
        if name in ("config", "state") or not isinstance(v, (dict, set, list)):
            continue
        out[name] = repr(sorted(v, key=repr)) if isinstance(v, set) else repr(v)
    for t, p in s.state.positions.items():
        out[f"pos:{t}"] = (p.buy_price, p.quantity, p.high_since_buy)
    out["sold_today"] = sorted(s.state.sold_today)
    return out


def _run_exit_path(s) -> list:
    sigs = []
    pos = s.state.positions[T]
    for px in _EXIT_PATH:
        pos.high_since_buy = max(pos.high_since_buy, px)       # risk.on_tick 과 같은 규약
        sigs.append(s.check_exit_signal(T, px, 10_000))
    return sigs


@pytest.mark.parametrize("sid", ALL7)
def test_t11_exit_signals_and_exit_state_identical_when_paused(sid, monkeypatch):
    clock = Clock(kst(10, 30))
    a = ready(sid, monkeypatch, clock)
    b = ready(sid, monkeypatch, clock)
    clock.set(10, 30)
    pause(b.s, True)
    for x in (a, b):
        x.s.state.positions[T] = Position(
            ticker=T, buy_price=10_000, quantity=10, order_no="ORD-384",
            strategy_id=sid, buy_date=DAY, high_since_buy=10_000,
        )
    sa, sb = _run_exit_path(a.s), _run_exit_path(b.s)
    assert any(x != Signal.NONE for x in sa), f"{sid}: 경로에 청산 신호가 하나도 없다 — 비교가 공허하다 {sa}"
    assert sb == sa, f"{sid}: 멈춤이 청산 신호를 바꿨다(M26) — 끔={sa} 멈춤={sb}"
    assert _exit_state(b.s) == _exit_state(a.s), f"{sid}: 멈춤이 청산 상태를 바꿨다(M16)"


# ===========================================================================
# T12 — risk.on_tick: 멈춘 전략의 보유분 손절은 그대로 나간다
# ===========================================================================
def _rm(monkeypatch, *strategies):
    from src.engine import risk as risk_mod
    from src.engine import scanner
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    monkeypatch.setattr(risk_mod.session_tracker, "is_tradable", lambda sid, params: True)
    monkeypatch.setattr(scanner, "ticker_prices", {})
    monkeypatch.setattr(scanner, "ticker_last_tick", {})
    reg = StrategyRegistry()
    for s in strategies:
        reg.register(s)
    oe = MagicMock()
    oe.execute_buy = AsyncMock()
    oe.execute_sell = AsyncMock()
    oe._selling = set()
    return RiskManager(registry=reg, order_engine=oe), oe


@pytest.mark.parametrize("paused,buys", [(True, 0), (False, 1)], ids=["paused", "positive_control"])
async def test_t12_ltv_paused_holding_stop_fires_and_new_buy_does_not(monkeypatch, paused, buys):
    r = ready("long_tail_volatility", monkeypatch, ticker=U)
    r.s.config.params["buy_paused"] = paused
    r.s.state.positions[T] = Position(ticker=T, buy_price=10_000, quantity=10, order_no="ORD-T",
                                      strategy_id="long_tail_volatility", buy_date=DAY,
                                      high_since_buy=10_000)
    rm, oe = _rm(monkeypatch, r.s)
    # 순서가 요점 — 멈춘 게이트를 **먼저** 지난 뒤에도 같은 전략의 보유분 손절이 나가야 한다
    # (멈춤을 `enabled=False` 로 구현하면 이 뒤 틱에서 `registry.enabled()` 가 전략을 빼 손절이 멈춘다 — M06)
    await rm.on_tick(ticker=U, current_price=10_400, open_price=10_000, change_rate=4.0)
    await rm.on_tick(ticker=U, current_price=10_550, open_price=10_000, change_rate=5.5)
    assert oe.execute_buy.await_count == buys, "멈춘 LTV 의 목표가 교차가 매수로 나갔다" if paused else "양성 대조"
    await rm.on_tick(ticker=T, current_price=8_500, open_price=10_000, change_rate=-15.0)
    assert oe.execute_sell.await_count == 1, "멈춘 LTV 보유분 손절이 나가지 않았다(M06)"
    assert oe.execute_sell.await_args.args[0] == T
    assert r.s.config.enabled is True and r.s.state.buy_disabled is False


async def test_t12_donchian_paused_holding_stop_fires(monkeypatch):
    r = ready("donchian_swing", monkeypatch)
    pause(r.s)
    r.s.state.positions[U] = Position(ticker=U, buy_price=10_000, quantity=10, order_no="ORD-U",
                                      strategy_id="donchian_swing", buy_date=DAY, high_since_buy=10_000)
    rm, oe = _rm(monkeypatch, r.s)
    assert r.fire() == Signal.NONE                          # 09:10 스윙 폴이 멈춘 게이트를 먼저 지난다
    await rm.on_tick(ticker=U, current_price=9_000, open_price=10_000, change_rate=-10.0)
    assert oe.execute_sell.await_count == 1, "멈춘 돈키언 보유분 손절이 나가지 않았다(M06)"
    assert oe.execute_buy.await_count == 0


# ===========================================================================
# T13 — 스윙 매수 폴: 멈춘 donchian 은 안 사고, kojiro 는 산다. 다음 분에도 donchian 후보가 남는다
# ===========================================================================
class _FastAsyncio:
    """`scheduler` 모듈의 `asyncio` 이름만 바꾼다 — 분 단위 대기를 즉시 통과시킨다."""

    def __init__(self, real_sleep):
        self._real_sleep = real_sleep

    def __getattr__(self, name):
        return getattr(asyncio, name)

    async def sleep(self, *_a, **_k):
        await self._real_sleep(0)


async def test_t13_swing_poll_paused_donchian_does_not_buy_kojiro_does(monkeypatch, caplog):
    from freezegun import freeze_time

    from src.engine import scheduler as sched_mod
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_registry import StrategyRegistry
    from tests.unit.engine._cycle382_support import kst_naive_datetime_class
    from tests.unit.engine._cycle384_support import Buyable, strategy_module

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    real_sleep = asyncio.sleep
    with freeze_time("2026-09-28T09:10:00+09:00", real_asyncio=True):
        with monkeypatch.context() as mp:
            mp.setattr(strategy_module("donchian_swing"), "datetime", kst_naive_datetime_class())
            mp.setattr(sched_mod, "asyncio", _FastAsyncio(real_sleep))
            clock = Clock(kst(9, 10))
            d = Buyable("donchian_swing", mp, clock, ticker=T)
            k = Buyable("kojiro", mp, clock, ticker=U)
            d.s._scanned_tickers = [T]
            k.s._scanned_tickers = [U]
            pause(d.s)
            d_sigs: list = []
            orig = d.s.check_buy_signal

            def _spy(*a, **kw):
                sig = orig(*a, **kw)
                d_sigs.append(sig)
                return sig

            mp.setattr(d.s, "check_buy_signal", _spy)

            sched = TradingScheduler.__new__(TradingScheduler)
            sched.registry = StrategyRegistry()
            sched.registry.register(d.s)
            sched.registry.register(k.s)
            sched._pending_next_day_clear = set()
            sched._running = True
            oe = MagicMock()
            oe.execute_buy = AsyncMock()
            sched.order_engine = oe
            fetched: list[str] = []
            px = {T: (d.fire_px, d.open), U: (k.fire_px, k.open)}

            async def _fetch(t):
                fetched.append(t)
                if fetched.count(T) >= 2:
                    sched._running = False          # donchian 후보가 두 번째 분에도 조회되면 멈춘다
                return {"stck_prpr": str(px[t][0]), "stck_oprc": str(px[t][1])}

            mp.setattr("src.api.condition.fetch_stock_detail", _fetch)
            await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=10.0)

    assert fetched.count(T) == 2, f"멈춘 donchian 후보가 다음 분에 filtered 에서 빠졌다: {fetched}"
    assert d_sigs == [Signal.NONE, Signal.NONE], f"멈춘 donchian 이 신호를 냈다: {d_sigs}"
    bought = [c.args[0] for c in oe.execute_buy.await_args_list]
    assert bought == [U], f"execute_buy 는 kojiro 몫만이어야 한다: {bought}"
    assert T not in d.s._bought_today
    assert d.s.state.signal_count_today == 0


# ===========================================================================
# T24 · T25 — `[buy_paused_skip]` 1회/(종목,전략)/일 · INFO · 후보만
# ===========================================================================
def test_t24_skip_line_once_per_candidate_per_day(monkeypatch, caplog):
    r = ready("donchian_swing", monkeypatch)
    pause(r.s)
    for _ in range(50):
        assert r.fire() == Signal.NONE
    got = _skip_lines(caplog, "donchian_swing")
    assert len(got) == 1, f"skip 은 정확히 1줄이어야 한다(M19): {got}"
    ln = got[0]
    assert (field(ln, "ticker"), field(ln, "cand"), field(ln, "dropped")) == (T, "1", "-"), ln

    # 비후보 — 막되 줄은 없다(M18)
    assert r.s.check_buy_signal(V, 10_600, 10_100) == Signal.NONE
    assert [x for x in _skip_lines(caplog) if field(x, "ticker") == V] == [], "비후보 종목에 skip 줄(M18)"

    # 다음 KST 날짜 — 다시 1줄
    r.clock.set(9, 10, day=NEXT_DAY)
    for _ in range(5):
        assert r.fire() == Signal.NONE
    assert len([x for x in _skip_lines(caplog) if field(x, "ticker") == T]) == 2, "다음 날 cap 이 풀리지 않았다"


def test_t24_late_candidate_is_still_recorded(monkeypatch, caplog):
    """장중 `prepare()` 재실행으로 뒤늦게 후보가 된 종목 — 후보가 아닐 때는 mark 하지 않는다(M31)."""
    r = ready("donchian_swing", monkeypatch)
    pause(r.s)
    assert r.s.check_buy_signal(U, 10_600, 10_100) == Signal.NONE       # 아직 후보 아님
    assert [x for x in _skip_lines(caplog) if field(x, "ticker") == U] == []
    r.s._candidates[U] = dict(r.s._candidates[T])                        # 뒤늦게 후보 편입
    assert r.s.check_buy_signal(U, 10_600, 10_100) == Signal.NONE
    got = [x for x in _skip_lines(caplog) if field(x, "ticker") == U]
    assert len(got) == 1, f"비후보 때 cap 을 소진해 뒤늦은 후보가 기록되지 않았다(M31): {got}"


@pytest.mark.parametrize("sid", ALL7)
def test_t25_skip_is_info_on_strategy_base_logger(sid, monkeypatch, caplog):
    r = ready(sid, monkeypatch)
    pause(r.s)
    r.prime()
    r.fire()
    got = [x for x in caplog.records
           if x.levelno >= logging.INFO and x.getMessage().startswith("[buy_paused_skip] ")]
    assert len(got) == 1, f"{sid}: skip 줄 {len(got)}"
    assert got[0].levelno == logging.INFO, f"{sid}: skip 은 INFO(M23) — {got[0].levelname}"
    assert got[0].name == SB_LOGGER
    assert field(got[0].getMessage(), "strategy") == sid


# ===========================================================================
# T26 — 카나리아 1회/(전략,값)/일 · paused=1 WARNING · paused=0 INFO (M22)
# ===========================================================================
def test_t26_canary_levels_and_cap(monkeypatch, caplog):
    r = ready("donchian_swing", monkeypatch)
    pause(r.s, True)
    r.fire()
    r.fire()
    pause(r.s, False)
    r.fire()
    r.fire()
    pause(r.s, True)
    r.fire()
    got = recs(caplog, "[buy_paused_config]")
    assert [(x.levelno, field(x.getMessage(), "paused")) for x in got] == [
        (logging.WARNING, "1"),
        (logging.INFO, "0"),
    ], [(x.levelname, x.getMessage()) for x in got]
    assert all(field(x.getMessage(), "strategy") == "donchian_swing" for x in got)
    assert all(x.name == SB_LOGGER for x in got)


# ===========================================================================
# T27 — 관측은 행위 밖: 로거가 죽어도 게이트 결과 불변 · 다음 호출이 다시 시도
# ===========================================================================
def test_t27_logger_death_never_changes_the_gate_and_retries(monkeypatch, caplog):
    need_pause_surface()
    from src.engine import strategy_base as sb

    caplog.set_level(logging.DEBUG)
    r = ready("donchian_swing", monkeypatch)
    pause(r.s)
    st = {"armed": True, "fired": 0}

    def _bomb(orig):
        def _f(msg, *a, **k):
            rendered = str(msg)
            if a:
                try:
                    rendered = str(msg) % a
                except Exception:
                    pass
            if st["armed"] and rendered.startswith("[buy_paused_"):
                st["fired"] += 1
                raise RuntimeError("logger dead (cycle384 T27)")
            return orig(msg, *a, **k)
        return _f

    monkeypatch.setattr(sb.logger, "info", _bomb(sb.logger.info))
    monkeypatch.setattr(sb.logger, "warning", _bomb(sb.logger.warning))

    assert r.fire() == Signal.NONE, "관측 예외가 게이트를 바꿨다"
    assert r.s._account_soft_gate_blocked(T) is True
    assert st["fired"] >= 2, "전제 — 카나리아·skip 두 줄 모두 시도됐어야 한다"
    assert [x for x in caplog.records
            if x.levelno == logging.DEBUG and "[buy_paused_" in x.getMessage()], "debug 흔적이 없다"
    assert _cfg_lines(caplog) == [] and _skip_lines(caplog) == []

    st["armed"] = False
    assert r.fire() == Signal.NONE
    assert len(_cfg_lines(caplog, "donchian_swing", min_level=logging.WARNING)) == 1, (
        "복구 뒤 카나리아가 없다 — mark 가 log 보다 앞이다(M20)"
    )
    assert len(_skip_lines(caplog, "donchian_swing")) == 1, "복구 뒤 skip 줄이 없다(M20)"


def test_t27_observer_exception_never_leaves_check_buy_signal(monkeypatch):
    need_pause_surface()
    r = ready("long_tail_volatility", monkeypatch)
    pause(r.s)

    def _boom(*a, **k):
        raise RuntimeError("cap dead")

    monkeypatch.setattr(r.s._buy_paused_logged, "should_emit", _boom)
    r.prime()
    assert r.fire() == Signal.NONE, "관측 예외가 check_buy_signal 밖으로 샜다(M21)"


# ===========================================================================
# T28 — `write_log` 병행 0 (루트 `_DbLogHandler` 가 이미 영속한다) (M24)
# ===========================================================================
def test_t28_no_write_log_pair(monkeypatch):
    from src.db import system_logs

    calls: list = []

    def _spy(*a, **k):
        calls.append(a)
        return None

    monkeypatch.setattr(system_logs, "write_log", _spy)
    monkeypatch.setattr(system_logs, "safe_write_log", _spy, raising=False)
    r = ready("donchian_swing", monkeypatch)
    pause(r.s)
    for _ in range(3):
        r.fire()
    r.s.config.params["buy_paused"] = "true"          # 모양 오류 카나리아(WARNING)도
    r.fire()
    assert calls == [], f"buy_paused 경로가 write_log 를 불렀다(M24): {calls}"


# ===========================================================================
# T29 — `dropped=` 는 첫 멈춤 틱에 뺀 래치를 담는다 (BFB)
# ===========================================================================
def test_t29_bfb_first_paused_tick_reports_dropped_latches(monkeypatch, caplog):
    need_pause_surface()
    r = ready("bull_flag_breakout", monkeypatch, breakout_retention_minutes=3)
    now = r.clock.now
    r.s._breakout_first_seen[T] = now
    r.s._vol_latch[T] = {"armed_at": now, "armed_date": now.date(), "flag_high": 10_000, "flag_low": 9_500}
    pause(r.s)
    assert r.fire() == Signal.NONE
    got = _skip_lines(caplog, "bull_flag_breakout")
    assert len(got) == 1 and field(got[0], "dropped") == "breakout_first_seen,vol_latch", got
    assert T not in r.s._breakout_first_seen and T not in r.s._vol_latch


# ===========================================================================
# T30 — 시장 유닛: 멈춘 전략은 신호 필터에 닿지 않고, prepare 쪽 스냅샷은 계속된다 (M28)
# ===========================================================================
def test_t30_paused_donchian_never_reaches_market_unit_signal_filter(monkeypatch, caplog):
    from tests.unit.engine._cycle382_support import MU_LOGGER, seed

    caplog.set_level(logging.INFO, logger=MU_LOGGER)

    def _sig(c):
        return [x.getMessage() for x in c.records
                if x.name == MU_LOGGER and x.getMessage().startswith("[market_unit] ")
                and "where=signal" in x.getMessage()]

    clock = Clock(kst(9, 10))
    a = ready("donchian_swing", monkeypatch, clock, market_unit_mode="enforce")
    seed(a.s, 0.0, DAY)
    assert a.fire() == Signal.NONE
    assert len(_sig(caplog)) == 1, "양성 대조 — 멈추지 않은 enforce·m=0 는 신호 필터에 닿는다"

    b = ready("donchian_swing", monkeypatch, clock, ticker=U, market_unit_mode="enforce")
    seed(b.s, 0.0, DAY)
    pause(b.s)
    assert b.fire() == Signal.NONE
    assert len(_sig(caplog)) == 1, "멈춘 donchian 이 시장 유닛 신호 필터에 닿았다(게이트 뒤여야 한다)"


async def test_t30_refresh_market_unit_still_emits_state_while_paused(monkeypatch, caplog):
    from tests.unit.engine._cycle382_support import MU_LOGGER, Seams

    caplog.set_level(logging.INFO, logger=MU_LOGGER)
    Seams().install(monkeypatch)
    r = ready("donchian_swing", monkeypatch)
    pause(r.s)
    await r.s._refresh_market_unit(as_of_date=DAY, preview=False)
    st = [x.getMessage() for x in caplog.records
          if x.name == MU_LOGGER and x.getMessage().startswith("[market_unit_state] ")]
    assert st, "멈춘 전략이 시장 유닛 스냅샷을 건너뛰었다(M28)"
    assert DAY in r.s._market_unit_snaps


# ===========================================================================
# T31 — 상태 차단(cycle369)이 이긴다: 둘 다 걸리면 status skip 만
# ===========================================================================
@pytest.mark.real_status_watch
def test_t31_status_block_and_pause_only_status_skip_is_logged(monkeypatch, caplog):
    from tests.unit.engine._cycle369_support import LEAF_LOGGER, leaf, overheat, record, set_db_modes

    set_db_modes(monkeypatch)
    lf = leaf()
    clock = Clock(kst(9, 10))
    monkeypatch.setattr(lf, "_now_kst", lambda: clock.now)
    caplog.set_level(logging.INFO, logger=LEAF_LOGGER)
    r = ready("donchian_swing", monkeypatch, clock)
    record(T, overheat(T), kst(9, 5), src="p1")
    pause(r.s)
    assert r.fire() == Signal.NONE
    status = [x.getMessage() for x in caplog.records
              if x.name == LEAF_LOGGER and x.getMessage().startswith("[status_block_buy_skip]")]
    assert status, "전제 — 상태 차단 skip 이 찍혀야 한다"
    assert _skip_lines(caplog) == [], "상태 차단보다 멈춤이 먼저 평가됐다(M02)"


# ===========================================================================
# T32 — 멈춤은 인스턴스별 params — 다른 전략에 번지지 않는다
# ===========================================================================
def test_t32_pause_does_not_leak_to_other_strategy(monkeypatch):
    clock = Clock(kst(9, 10))
    d = ready("donchian_swing", monkeypatch, clock, ticker=T)
    k = ready("kojiro", monkeypatch, clock, ticker=U)
    pause(d.s)
    assert d.fire() == Signal.NONE
    assert k.s.config.params.get("buy_paused") is False
    assert k.fire() == Signal.BUY, "donchian 멈춤이 kojiro 로 번졌다"
    assert strategy_class("donchian_swing").DEFAULT_PARAMS.get("buy_paused") is False, (
        "PUT 경로가 클래스 기본값 dict 를 고쳤다 — 인스턴스 params 가 공유됐다"
    )
