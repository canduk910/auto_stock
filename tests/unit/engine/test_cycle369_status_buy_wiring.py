"""cycle369 Red — 매수 차단 배선: 공통 게이트 · 관측 훅 · 실제 매수 경로 통합.

## 막는 자리 (명세 §4.4)

`StrategyBase._account_soft_gate_blocked` 의 **첫 문장**:

    if self._status_buy_blocked(ticker):
        return True

7전략의 `check_buy_signal` 은 모두 이 게이트를 지난다(cycle233 AST G-1 — 폴·래치형
5전략은 첫 문장, momentum·VB 는 기준가 갱신 **뒤** 발사 직전). 그래서 매수 경로 2곳
(틱 `risk.on_tick` · 스윙 REST 폴 `scheduler._swing_buy_poll_loop`)이 전부 막히고,
momentum·VB 기준가가 얼지 않는다(K13).

## 관측 훅 (명세 §4.4 끝)

`src/api/condition.py::_fetch_stock_detail_and_cache` 안, `output = data.get("output", {})`
바로 다음 · 캐시 lock 앞:

    _notify_status_observer(ticker, output)

`_notify_status_observer` 는 lazy import + `try/except Exception` 이중 안전(K19).
훅 덕분에 이미 나가는 조회 3경로가 **추가 호출 0 으로 결정적**이 된다:
스윙 매수 폴(J13) · VB/LTV 기준가 REST(J14) · momentum 급등 스캔(J15).

## 이 파일의 시계

- 새 leaf = `status_exit_watch._now_kst` seam (`clock` 픽스처)
- 전략 모듈 = 모듈의 `datetime` 이름을 같은 Clock 을 따르는 서브클래스로 교체
  (freezegun 은 naive 를 UTC 로 돌려줘 donchian 시간 가드와 aware 코드가 갈라진다)
"""
from __future__ import annotations

import asyncio
import datetime as _datetime_module
import logging
import time as _time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.unit.engine._cycle369_support import (
    ALL_SIDS,
    LIVE,
    FakeOrderEngine,
    clean,
    clock,  # noqa: F401 — pytest 픽스처
    db_modes,  # noqa: F401
    dblog,  # noqa: F401
    fetch,  # noqa: F401
    field,
    frozen_datetime_class,
    gate,
    kst,
    leaf,
    lines,
    managed,
    open_info,
    overheat,
    pin_module_clock,
    record,
    records,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.real_status_watch,
    pytest.mark.usefixtures("no_real_kis"),
]

_T = "005160"


@pytest.fixture(autouse=True)
def _info(caplog, db_modes):
    open_info(caplog)
    try:
        from src.engine import account_risk_watcher

        account_risk_watcher.reset_state_for_test()
    except Exception:
        pass


@pytest.fixture
def quote(monkeypatch):
    """`condition.kis_get_quote` 교체 — 진짜 `fetch_stock_detail` → 캐시 → 훅 경로를 태운다."""
    from src.api import condition

    state = {"table": {}, "calls": []}

    async def _fake(url, tr_id, params, *a, **k):
        t = params.get("fid_input_iscd")
        state["calls"].append((tr_id, t))
        out = state["table"].get(t)
        if out is None:
            out = clean(t)
        return {"output": dict(out), "rt_cd": "0", "msg_cd": "MCA00000", "msg1": "정상처리"}

    condition.clear_caches()
    monkeypatch.setattr(condition, "kis_get_quote", _fake)
    yield state
    condition.clear_caches()


_STRATS = {
    "momentum": ("src.engine.strategies.momentum", "MomentumStrategy"),
    "volatility_breakout": ("src.engine.strategies.volatility_breakout", "VolatilityBreakoutStrategy"),
    "long_tail_volatility": ("src.engine.strategies.long_tail_volatility", "LongTailVolatilityStrategy"),
    "donchian_swing": ("src.engine.strategies.donchian_swing", "DonchianSwingStrategy"),
    "bull_flag_breakout": ("src.engine.strategies.bull_flag_breakout", "BullFlagBreakoutStrategy"),
    "vcp_breakout": ("src.engine.strategies.vcp_breakout", "VcpBreakoutStrategy"),
    "kojiro": ("src.engine.strategies.kojiro", "KojiroStrategy"),
}
_GATE_FIRST = ("long_tail_volatility", "donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro")


def _module(sid):
    import importlib

    return importlib.import_module(_STRATS[sid][0])


def _make(sid, **params):
    from src.engine.strategy_base import StrategyConfig

    cls = getattr(_module(sid), _STRATS[sid][1])
    s = cls(StrategyConfig(strategy_id=sid, name=sid, params={"exchange": "KRX", **params}))
    s.state.total_investment = 10_000_000
    return s


def _gate_spy(monkeypatch, result: bool):
    calls: list[tuple] = []

    def _spy(ticker, strategy_id, *a, **k):
        calls.append((ticker, strategy_id))
        return result

    monkeypatch.setattr(leaf(), "buy_gate", _spy)
    return calls


def _vb_ready(monkeypatch, s, ticker=_T):
    s._targets[ticker] = {
        "k": 0.5, "prev_range": 1000, "target_offset_base": 500, "target_offset": 500,
        "target_price": 10500, "open_price": 10000,
        "boards": {"main": {"open_price": 10000, "target_price": 10500, "target_offset": 500}},
    }
    s._open_confirmed[ticker] = {"main": True}
    monkeypatch.setattr(s, "_resolve_active_board", lambda: "main")


# ===========================================================================
# J10 — 7전략 배선 (양성·음성)
# ===========================================================================
@pytest.mark.parametrize("sid", _GATE_FIRST)
def test_j10_gate_first_strategies_consult_status_gate(sid, clock, monkeypatch):
    """폴·래치형 5전략 — 상태 차단이 켜지면 `check_buy_signal` 즉시 NONE, 게이트가 실제로 불렸다."""
    from src.engine.strategy_base import Signal

    clock.set(9, 10)
    calls = _gate_spy(monkeypatch, True)
    s = _make(sid)
    assert s.check_buy_signal(_T, 10600, 10100) == Signal.NONE
    assert (_T, sid) in calls, f"{sid}: 공통 게이트가 상태 차단을 묻지 않았다"


def test_j10_donchian_positive_control_buys_when_not_blocked(clock, monkeypatch):
    """J10 양성 대조 — 차단 off 에서 donchian 이 실제로 BUY 를 낸다(부정 단언만이면 공허)."""
    from src.engine import scanner
    from src.engine.strategy_base import Signal

    pin_module_clock(monkeypatch, clock, _module("donchian_swing"))
    monkeypatch.setattr(scanner, "ticker_prices", {})
    clock.set(9, 10)

    def _build():
        s = _make("donchian_swing")
        s._candidates[_T] = {"prev_close": 10000, "donchian_high": 10500, "ema60": 9000, "atr": 200}
        return s

    calls = _gate_spy(monkeypatch, False)
    assert _build().check_buy_signal(_T, 10600, 10100) == Signal.BUY
    assert (_T, "donchian_swing") in calls
    _gate_spy(monkeypatch, True)
    assert _build().check_buy_signal(_T, 10600, 10100) == Signal.NONE


def test_j10_momentum_crossing_blocked_and_positive_control(clock, monkeypatch):
    from src.engine import scanner
    from src.engine.strategy_base import Signal

    pin_module_clock(monkeypatch, clock, _module("momentum"))
    monkeypatch.setattr(scanner, "ticker_prev_close", {_T: 10000})
    clock.set(9, 40)

    calls = _gate_spy(monkeypatch, True)
    s = _make("momentum")
    assert s.check_buy_signal(_T, 12800, 12000) == Signal.NONE   # 첫 틱 기록
    assert s.check_buy_signal(_T, 12950, 12000) == Signal.NONE   # 교차 — 차단
    assert (_T, "momentum") in calls

    _gate_spy(monkeypatch, False)
    s2 = _make("momentum")
    s2.check_buy_signal(_T, 12800, 12000)
    assert s2.check_buy_signal(_T, 12950, 12000) == Signal.BUY


def test_j10_vb_crossing_blocked_and_positive_control(clock, monkeypatch):
    from src.engine.strategy_base import Signal

    pin_module_clock(monkeypatch, clock, _module("volatility_breakout"))
    clock.set(9, 40)

    calls = _gate_spy(monkeypatch, True)
    s = _make("volatility_breakout")
    _vb_ready(monkeypatch, s)
    assert s.check_buy_signal(_T, 10400, 10000) == Signal.NONE
    assert s.check_buy_signal(_T, 10550, 10000) == Signal.NONE
    assert (_T, "volatility_breakout") in calls

    _gate_spy(monkeypatch, False)
    s2 = _make("volatility_breakout")
    _vb_ready(monkeypatch, s2)
    s2.check_buy_signal(_T, 10400, 10000)
    assert s2.check_buy_signal(_T, 10550, 10000) == Signal.BUY


def test_j10_all_seven_account_gates_see_real_registry(clock):
    """spy 없이 — 실제 레지스트리 기록 하나로 7전략 공통 게이트가 전부 True."""
    record(_T, LIVE[_T], kst(10, 0), src="p1")
    clock.set(10, 0)
    for sid in ALL_SIDS:
        assert _make(sid)._account_soft_gate_blocked(_T) is True, sid
        assert _make(sid)._account_soft_gate_blocked("005930") is False, sid


# ===========================================================================
# J11 — edge 전략 기준가 (K13)
# ===========================================================================
def test_j11_momentum_baseline_keeps_moving_while_blocked(clock, monkeypatch):
    """장 전 차단 중 교차 틱 → NONE. 해제 뒤 임계 위에 머문 틱은 **새 교차가 아니다**(거짓 돌파 금지).

    게이트를 `check_buy_signal` 최상단이나 `risk.on_tick` 으로 옮기면 `_prev_prdy_rate` 가
    얼어 해제 직후 첫 틱이 거짓 돌파로 BUY 가 된다(추격 상한 없는 매수).
    """
    from src.engine import scanner
    from src.engine.strategy_base import Signal

    pin_module_clock(monkeypatch, clock, _module("momentum"))
    monkeypatch.setattr(scanner, "ticker_prev_close", {_T: 10000})
    record(_T, LIVE[_T], kst(8, 45), src="p0")

    s = _make("momentum")
    clock.set(8, 55)
    assert gate(_T) is True
    assert s.check_buy_signal(_T, 12800, 12000) == Signal.NONE
    assert s.check_buy_signal(_T, 12950, 12000) == Signal.NONE

    clock.set(9, 0, 5)
    record(_T, clean(_T), kst(9, 0, 5), src="p1")
    assert gate(_T) is False
    assert s.check_buy_signal(_T, 12960, 12000) == Signal.NONE, "기준가가 얼었다 — 거짓 돌파"
    # 양성: 임계 아래로 내려갔다 다시 넘으면 산다
    assert s.check_buy_signal(_T, 12700, 12000) == Signal.NONE
    assert s.check_buy_signal(_T, 12950, 12000) == Signal.BUY


def test_j11_vb_baseline_keeps_moving_while_blocked(clock, monkeypatch):
    from src.engine.strategy_base import Signal

    pin_module_clock(monkeypatch, clock, _module("volatility_breakout"))
    record(_T, LIVE[_T], kst(8, 45), src="p0")
    s = _make("volatility_breakout")
    _vb_ready(monkeypatch, s)

    clock.set(9, 40)
    assert gate(_T) is True
    assert s.check_buy_signal(_T, 10400, 10000) == Signal.NONE
    assert s.check_buy_signal(_T, 10550, 10000) == Signal.NONE

    clock.set(9, 41)
    record(_T, clean(_T), kst(9, 41), src="inc")
    assert s.check_buy_signal(_T, 10560, 10000) == Signal.NONE, "VB 기준가가 얼었다 — 거짓 돌파"
    assert s.check_buy_signal(_T, 10400, 10000) == Signal.NONE
    assert s.check_buy_signal(_T, 10550, 10000) == Signal.BUY


# ===========================================================================
# J0 · J12 — 첫날 시나리오 통합 (틱 매수 경로)
# ===========================================================================
async def _first_day_on_tick(monkeypatch, clock, fetch, p1_output):
    from src.engine import risk as risk_mod
    from src.engine import scanner
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    monkeypatch.setattr(risk_mod.session_tracker, "is_tradable", lambda sid, params: True)
    monkeypatch.setattr(scanner, "ticker_prev_close", {_T: 10000})
    monkeypatch.setattr(scanner, "ticker_prices", {})
    monkeypatch.setattr(scanner, "ticker_last_tick", {})
    pin_module_clock(monkeypatch, clock, _module("momentum"))

    mom = _make("momentum")
    reg = StrategyRegistry()
    reg.register(mom)
    oe = MagicMock()
    oe.execute_buy = AsyncMock()
    oe.execute_sell = AsyncMock()
    oe._selling = set()
    rm = RiskManager(registry=reg, order_engine=oe)

    # T일 후보는 진입 필터를 통과했다(raw short_over_yn=N). T+1 09:00:00 P1 이 라이브로 읽는다.
    fetch.table[_T] = p1_output
    clock.set(9, 0, 0)
    await leaf().run_buy_pass(SimpleNamespace(registry=reg, order_engine=FakeOrderEngine(),
                                              _running=True), kind="p1")
    clock.set(9, 0, 5)
    await rm.on_tick(ticker=_T, current_price=12800, open_price=12000, change_rate=28.0)
    clock.set(9, 0, 6)
    await rm.on_tick(ticker=_T, current_price=12950, open_price=12000, change_rate=29.5)
    return mom, oe


@pytest.mark.asyncio
async def test_j0_first_day_designation_blocks_tick_buy(clock, fetch, dblog, monkeypatch):
    """J0 · J12 — 지정 첫날 비보유 후보: 돌파해도 `execute_buy` 0회 · 오귀인 없음."""
    mom, oe = await _first_day_on_tick(monkeypatch, clock, fetch, LIVE[_T])
    assert oe.execute_buy.await_count == 0, "지정 첫날 매수가 나갔다"
    assert mom.state.signal_count_today == 0, "신호 카운터가 오염됐다(차단은 신호 단계)"
    assert mom.state.is_low_funds_blocked(_T, _time.time()) is False, (
        "「투자금 부족」 쿨다운으로 오귀인됐다(K14)"
    )


@pytest.mark.asyncio
async def test_j0_positive_control_clean_read_buys(clock, fetch, dblog, monkeypatch):
    _mom, oe = await _first_day_on_tick(monkeypatch, clock, fetch, clean(_T))
    assert oe.execute_buy.await_count == 1


# ===========================================================================
# J13 — 스윙 매수 폴: 조회 → 훅 → 신호 (P1/INC 없이도 결정적)
# ===========================================================================
def _swing_sched(order_engine):
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    class _GateFirstSwing(StrategyBase):
        """donchian 모양 더블 — 첫 문장이 공통 게이트(cycle233 G-1 이 실제 7전략에 강제)."""

        def __init__(self):
            super().__init__(StrategyConfig(strategy_id="donchian_swing", name="d",
                                            enabled=True, weight=0.2, params={"exchange": "KRX"}))
            self._bought_today: set[str] = set()

        async def prepare(self):
            return None

        def get_scanned_tickers(self):
            return [_T]

        def check_buy_signal(self, ticker, current_price, open_price):
            if self._account_soft_gate_blocked(ticker):
                return Signal.NONE
            return Signal.BUY

        def check_exit_signal(self, *a):
            return Signal.NONE

        def calc_buy_quantity(self, current_price, ticker=None):
            return 1

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = StrategyRegistry()
    sched._pending_next_day_clear = set()
    sched._running = True
    sched.registry.register(_GateFirstSwing())
    sched.order_engine = order_engine
    return sched


async def _run_swing_once(monkeypatch, clock, quote, output):
    quote["table"][_T] = output
    monkeypatch.setattr(_datetime_module, "datetime", frozen_datetime_class(clock))
    clock.set(9, 10)
    oe = MagicMock()
    oe.execute_buy = AsyncMock()
    sched = _swing_sched(oe)

    async def _stopper():
        await asyncio.sleep(0.3)
        sched._running = False

    stop = asyncio.create_task(_stopper())
    await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=5.0)
    await stop
    return oe


@pytest.mark.asyncio
async def test_j13_swing_poll_blocked_by_hook_without_p1(clock, quote, dblog, monkeypatch, caplog):
    oe = await _run_swing_once(monkeypatch, clock, quote, managed(_T))
    assert ("FHKST01010100", _T) in quote["calls"]
    assert oe.execute_buy.await_count == 0, "스윙 폴 조회가 훅을 지나지 않았다(M23)"
    armed = lines(caplog, "[status_block_armed]", min_level=logging.WARNING)
    assert armed and field(armed[0], "src") == "fetch"


@pytest.mark.asyncio
async def test_j13_swing_poll_positive_control(clock, quote, dblog, monkeypatch):
    oe = await _run_swing_once(monkeypatch, clock, quote, clean(_T))
    assert oe.execute_buy.await_count == 1


# ===========================================================================
# J14 — VB/LTV 기준가 REST 라운드: 목표가는 서고, 매수는 막힌다
# ===========================================================================
def _vb_basis_sched():
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    vb = VolatilityBreakoutStrategy(StrategyConfig(
        strategy_id="volatility_breakout", name="vb", enabled=True, weight=0.3))
    vb.config.params["open_price_scope_mode"] = "enforce"
    vb.config.params["tradable_boards"] = ["main"]
    vb._targets[_T] = {
        "k": 0.5, "prev_range": 1000, "target_offset_base": 500, "target_offset": 500,
        "target_price": 0, "open_price": 0, "boards": {},
    }
    vb._open_confirmed[_T] = {}
    reg = StrategyRegistry()
    reg.register(vb)
    return SimpleNamespace(registry=reg, _running=True), vb


@pytest.mark.asyncio
async def test_j14_rest_basis_round_sets_target_and_blocks(clock, quote, dblog, caplog):
    from src.engine import open_price_rest

    quote["table"][_T] = overheat(_T, stck_oprc="10000")
    sched, vb = _vb_basis_sched()
    clock.set(9, 0, 35)
    await open_price_rest.run_main_rest_basis_round(sched, round_no=1, total_rounds=19, kind="fast")
    assert vb._open_confirmed.get(_T, {}).get("main") is True, "훅이 기준가 소비자를 깨뜨렸다(K19)"
    assert vb._account_soft_gate_blocked(_T) is True, "기준가 조회가 훅을 지나지 않았다(M23)"
    armed = lines(caplog, "[status_block_armed]", min_level=logging.WARNING)
    assert armed and field(armed[0], "src") == "fetch"


@pytest.mark.asyncio
async def test_j14_positive_control(clock, quote, dblog):
    from src.engine import open_price_rest

    quote["table"][_T] = clean(_T, stck_oprc="10000")
    sched, vb = _vb_basis_sched()
    clock.set(9, 0, 35)
    await open_price_rest.run_main_rest_basis_round(sched, round_no=1, total_rounds=19, kind="fast")
    assert vb._open_confirmed.get(_T, {}).get("main") is True
    assert vb._account_soft_gate_blocked(_T) is False


# ===========================================================================
# J15 — momentum 급등 스캔: 후보로 받는 순간 기록
# ===========================================================================
async def _rising_then_cross(monkeypatch, clock, quote, output):
    from src.api import condition
    from src.config import settings
    from src.engine import scanner
    from src.engine.strategy_base import Signal  # noqa: F401

    monkeypatch.setattr(settings, "kis_env", "real")
    monkeypatch.setattr(condition, "_fetch_fluctuation_rank",
                        AsyncMock(return_value=[{"stck_shrn_iscd": _T, "prdy_ctrt": "20.5"}]))
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    quote["table"][_T] = dict(output, stck_sdpr="10000")
    pin_module_clock(monkeypatch, clock, _module("momentum"))
    clock.set(9, 40)
    await condition.fetch_rising_stocks()
    assert scanner.ticker_prev_close.get(_T) == 10000
    s = _make("momentum")
    s.check_buy_signal(_T, 12800, 12000)
    return s.check_buy_signal(_T, 12950, 12000)


@pytest.mark.asyncio
async def test_j15_rising_scan_admission_blocks_momentum(clock, quote, dblog, monkeypatch):
    from src.engine.strategy_base import Signal

    assert await _rising_then_cross(monkeypatch, clock, quote, managed(_T)) == Signal.NONE
    assert blocks_by_phase(_T) == "in"


@pytest.mark.asyncio
async def test_j15_positive_control(clock, quote, dblog, monkeypatch):
    from src.engine.strategy_base import Signal

    assert await _rising_then_cross(monkeypatch, clock, quote, clean(_T)) == Signal.BUY


def blocks_by_phase(ticker):
    for b in leaf().snapshot().get("blocks", []):
        if b["ticker"] == ticker:
            return b["phase"]
    return None


# ===========================================================================
# J16 — 훅 안전 (K19)
# ===========================================================================
@pytest.mark.asyncio
async def test_j16_hook_sees_fresh_reads_only(quote, monkeypatch):
    from src.api import condition

    seen: list[tuple] = []
    monkeypatch.setattr(leaf(), "observe_fhkst", lambda t, out: seen.append((t, out)))
    quote["table"][_T] = managed(_T)
    first = await condition.fetch_stock_detail(_T)
    second = await condition.fetch_stock_detail(_T)
    assert len(quote["calls"]) == 1, "캐시가 깨졌다"
    assert len(seen) == 1, "캐시 적중 경로에서 훅이 불렸다(중복 기록)"
    assert seen[0][0] == _T and seen[0][1] == first == second


@pytest.mark.asyncio
async def test_j16_hook_exception_never_breaks_fhkst_consumers(quote, monkeypatch):
    from src.api import condition

    def _boom(*a, **k):
        raise RuntimeError("observer broken")

    monkeypatch.setattr(leaf(), "observe_fhkst", _boom)
    quote["table"][_T] = managed(_T)
    out = await condition.fetch_stock_detail(_T)
    assert out.get("stck_shrn_iscd") == _T, "훅 예외가 조회 결과를 삼켰다 — 모든 FHKST 소비자 사망"
    again = await condition.fetch_stock_detail(_T)
    assert again == out
    assert len(quote["calls"]) == 1, "훅 예외 때문에 캐시 쓰기가 빠졌다"


def test_j16_notify_helper_is_never_raise(monkeypatch):
    from src.api import condition

    def _boom(*a, **k):
        raise RuntimeError("observer broken")

    monkeypatch.setattr(leaf(), "observe_fhkst", _boom)
    assert condition._notify_status_observer(_T, managed(_T)) is None


def test_j16_observe_fhkst_itself_is_never_raise(clock):
    clock.set(10, 0)
    assert leaf().observe_fhkst(_T, object()) is None
    assert leaf().observe_fhkst(None, managed(_T)) is None
