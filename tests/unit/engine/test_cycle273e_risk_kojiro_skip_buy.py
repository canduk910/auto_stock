"""cycle273e Red — F-3(D2 나): `risk.py:646` 매수 평가 skip 에 **kojiro** 추가.

명세 = `_workspace/red/cycle273e_kojiro_gap_gate_spec.md`
자문 = `_workspace/domain_consult/cycle273_kojiro_gap_gate_20260910.md` §4 (R1~R11)
정본 = `_workspace/analysis/2026-09-10_cycle273_UB_risk_gap.md`

## 무엇을 고치는가

kojiro 의 갭업(5.0%)·갭다운(−4.0%)·**붕괴 가드**(`current_price < open_price`)가
전부 같은 인자 `open_price` 하나에 매달려 있는데(`kojiro.py:868·871·880·891`),
경로 B(`risk.on_tick`)에서 그 인자는 통합채널 `H0UNCNT0` `[7] STCK_OPRC` 를
**스코프 필터 없이** 그대로 실은 값이다(`handler.py:417`). 형제 필드 `[8] 고가`는
`[27] HGPR_HOUR` MAIN 창 필터를 갖는데 `[7]` 에는 대응물이 없다.

09-07 실측 N=103 — WS 시가 ≠ KRX 확정 시가 **98/103(95.1%)**, 진짜 갭업(≥5%)
**탐지율 0/8**. 즉 "갭업 스킵" 이 갭업을 못 본다.

## 이 변경의 행위 영향은 딱 한 문장

> **WebSocket 틱을 통한 kojiro 신규 매수 = 0.** (경로 A `_swing_buy_poll_loop`
> 09:05~09:30 1분 주기가 후보 전체를 계속 덮는다.)

청산·손절·트레일링·익일청산·`day_high` 앵커·보드 카운터·자금 가드 로그는
전부 skip 지점보다 **앞**이라 무접촉이다(UB §1.1 표).

## HEAD 기준 RED / GREEN

| # | 테스트 | HEAD |
|---|---|---|
| R1 | `test_r1_kojiro_check_buy_signal_skipped_in_on_tick` | **RED** |
| R2 | `test_r2_kojiro_check_exit_signal_still_called_when_held` | GREEN(계약) |
| R3 | `test_r3_stop_loss_still_reaches_execute_sell` | GREEN(계약) |
| R4 | `test_r4_tradable_skip_counter_unchanged` / `..._risk_silent_skip_unchanged` | GREEN(위치 계약) |
| R5 | `test_r5_is_ticker_blocked_for_buy_call_count_unchanged` | GREEN(위치 계약) |
| R6 | `test_r6_swing_poll_loop_still_evaluates_kojiro` | GREEN(경로 A 무접촉) |
| R7 | `test_r7_donchian_skip_unchanged` | GREEN(회귀 0) |
| R8 | `test_r8_third_strategy_still_evaluated` | **RED**(kojiro skip + momentum 평가 동시) |

R2/R3(청산이 skip 보다 앞)과 R4/R5(카운터·호출 횟수 불변 = 삽입 위치)는 이
변경의 안전성이 걸린 두 축이다 — 뮤테이션(skip 을 청산 앞으로 이동 · `continue`
→ `pass`)까지 KILL 해야 한다(자문 §8).

**테스트하지 않는 것** — "붕괴 가드 재시도 빈도가 1분" 은 시간 의존이라 계약에
넣지 않는다. R6 이 폴 루프 1사이클만 검증하고 빈도는 운영 로그 서명 #2
(`caller=_swing_buy_poll_loop` ≥6행 유지)에 맡긴다.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as _datetime_module
import logging

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.engine.risk import RiskManager
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

TICKER = "005930"
_KST = _datetime_module.timezone(_datetime_module.timedelta(hours=9))


class _SpyStrategy(StrategyBase):
    """`check_buy_signal` / `check_exit_signal` 호출 추적 스파이."""

    def __init__(self, config, *, exit_signal: Signal = Signal.NONE):
        super().__init__(config)
        self.buy_calls: list[tuple[str, int, int]] = []
        self.exit_calls: list[tuple[str, int, int]] = []
        self._exit_signal = exit_signal
        self._bought_today: set[str] = set()
        self._scanned: list[str] = [TICKER]

    async def prepare(self):
        pass

    def get_scanned_tickers(self):
        return list(self._scanned)

    def check_buy_signal(self, ticker, current_price, open_price):
        self.buy_calls.append((ticker, current_price, open_price))
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        self.exit_calls.append((ticker, current_price, open_price))
        return self._exit_signal

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0


def _spy(strategy_id: str, *, boards=("main",), exit_signal=Signal.NONE) -> _SpyStrategy:
    s = _SpyStrategy(
        StrategyConfig(
            strategy_id=strategy_id, name=strategy_id, weight=1.0, enabled=True,
            params={"tradable_boards": list(boards)},
        ),
        exit_signal=exit_signal,
    )
    s.state.total_investment = 100_000_000
    return s


@pytest.fixture(autouse=True)
def _active_main_board(monkeypatch):
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))


@pytest.fixture(autouse=True)
def _ticker_state(monkeypatch):
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_prev_close", {TICKER: 70000})
    monkeypatch.setattr(scanner, "ticker_prices", {})


@pytest.fixture(autouse=True)
def _pin_clock(monkeypatch):
    """프리장 청산 보류 게이트 결정화 (tests/conftest.py `_pin_pre_market_clock` 과 동형).

    최종 목적지(tests/) 에서는 conftest autouse 가 같은 일을 한다 — 중복은 무해.
    """
    from src.engine import risk as _risk
    pinned = _datetime_module.datetime(2026, 1, 5, 10, 30, 0, tzinfo=_KST)
    monkeypatch.setattr(_risk, "_now_kst", lambda: pinned, raising=False)


def _order_engine() -> MagicMock:
    oe = MagicMock()
    oe.execute_buy = AsyncMock()
    oe.execute_sell = AsyncMock()
    oe._selling = set()
    return oe


# ===========================================================================
# R1 — 본체
# ===========================================================================
@pytest.mark.asyncio
async def test_r1_kojiro_check_buy_signal_skipped_in_on_tick():
    """RED (HEAD) — WebSocket 틱을 통한 kojiro 매수 평가는 일어나지 않아야 한다."""
    registry = StrategyRegistry()
    kojiro = _spy("kojiro")
    registry.register(kojiro)
    oe = _order_engine()
    risk = RiskManager(registry, oe)

    await risk.on_tick(TICKER, current_price=85000, open_price=80000, change_rate=21.43)

    assert kojiro.buy_calls == [], (
        "kojiro 매수 평가가 경로 B(WS 틱)에서 살아 있다 — 오염된 `[7] STCK_OPRC` 가 "
        "갭업·갭다운·붕괴 가드 세 관문을 동시에 틀리게 한다(09-07 N=103, 탐지율 0/8)"
    )
    assert oe.execute_buy.await_count == 0


# ===========================================================================
# R2/R3 — skip 은 청산보다 **뒤**에 있다
# ===========================================================================
@pytest.mark.asyncio
async def test_r2_kojiro_check_exit_signal_still_called_when_held():
    """GREEN(계약) — 깨지면 손절이 죽는다. skip 을 청산 앞으로 옮기는 뮤테이션 KILL."""
    registry = StrategyRegistry()
    kojiro = _spy("kojiro")
    kojiro.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=70000, quantity=10, order_no="O-1", strategy_id="kojiro",
    )
    registry.register(kojiro)
    risk = RiskManager(registry, _order_engine())

    await risk.on_tick(TICKER, current_price=65000, open_price=70000, change_rate=-7.14)

    assert len(kojiro.exit_calls) == 1, "보유 중 kojiro 청산 평가가 사라졌다"
    assert kojiro.exit_calls[0][0] == TICKER
    assert kojiro.buy_calls == []


@pytest.mark.asyncio
async def test_r3_stop_loss_still_reaches_execute_sell():
    """GREEN(계약) — R2 의 끝단. 반환값만으로는 배관을 못 잰다."""
    registry = StrategyRegistry()
    kojiro = _spy("kojiro", exit_signal=Signal.STOP_LOSS)
    kojiro.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=70000, quantity=10, order_no="O-1", strategy_id="kojiro",
    )
    registry.register(kojiro)
    oe = _order_engine()
    risk = RiskManager(registry, oe)

    await risk.on_tick(TICKER, current_price=60000, open_price=70000, change_rate=-14.3)

    assert oe.execute_sell.await_count == 1, "kojiro 손절 주문이 발사되지 않았다"
    args = oe.execute_sell.await_args.args
    assert args[0] == TICKER and args[1] == Signal.STOP_LOSS and args[2] == "kojiro"


# ===========================================================================
# R4/R5 — 삽입 위치 계약 (관측 지표·호출 횟수 드리프트 차단)
# ===========================================================================
@pytest.mark.asyncio
async def test_r4_tradable_skip_counter_unchanged(caplog):
    """GREEN(위치 계약) — 보드 밖 틱은 여전히 `[tradable_skip]` 카운터를 올린다.

    skip 을 보드 가드보다 **앞**으로 옮기면 이 카운터가 조용히 0 이 된다
    (= 관측 지표 드리프트 = 행위 변경 범위 확대).
    """
    registry = StrategyRegistry()
    kojiro = _spy("kojiro", boards=("pre_nxt",))   # MAIN 활성 ↔ 보드 불일치
    registry.register(kojiro)
    risk = RiskManager(registry, _order_engine())

    caplog.set_level(logging.DEBUG)
    await risk.on_tick(TICKER, current_price=85000, open_price=80000, change_rate=21.43)

    assert risk._tradable_skip_count.get("kojiro", 0) == 1, (
        "보드 가드 카운터가 kojiro 에 대해 더 이상 올라가지 않는다"
    )
    assert kojiro.buy_calls == []


@pytest.mark.asyncio
async def test_r4b_risk_silent_skip_unchanged(caplog):
    """GREEN(위치 계약) — 자금 사전 가드의 `[risk_silent_skip]` INFO 도 그대로."""
    registry = StrategyRegistry()
    kojiro = _spy("kojiro")
    kojiro.state.total_investment = 1_000        # current_price > total_investment
    registry.register(kojiro)
    risk = RiskManager(registry, _order_engine())

    caplog.set_level(logging.INFO)
    await risk.on_tick(TICKER, current_price=85000, open_price=80000, change_rate=21.43)

    rows = [
        r.getMessage() for r in caplog.records
        if r.getMessage().startswith("[risk_silent_skip]")
    ]
    assert rows, "자금 사전 가드의 가시화 INFO 가 사라졌다"
    assert "strategy=kojiro" in rows[0]
    assert kojiro.buy_calls == []


@pytest.mark.asyncio
async def test_r5_is_ticker_blocked_for_buy_call_count_unchanged(monkeypatch):
    """GREEN(위치 계약) — 중복 가드 호출 횟수가 변하지 않는다(R4 와 같은 축)."""
    registry = StrategyRegistry()
    kojiro = _spy("kojiro")
    registry.register(kojiro)

    calls: list[str] = []
    real = registry.is_ticker_blocked_for_buy

    def _spy_blocked(ticker: str) -> bool:
        calls.append(ticker)
        return real(ticker)

    monkeypatch.setattr(registry, "is_ticker_blocked_for_buy", _spy_blocked)
    risk = RiskManager(registry, _order_engine())

    await risk.on_tick(TICKER, current_price=85000, open_price=80000, change_rate=21.43)

    assert calls == [TICKER], (
        f"`is_ticker_blocked_for_buy` 호출 횟수가 바뀌었다({calls}) — "
        f"skip 이 이 가드보다 앞으로 옮겨졌다"
    )
    # ⚠️ 여기서 `kojiro.buy_calls` 는 보지 않는다 — 그 계약은 R1 이 진다.
    #    한 테스트가 위치 계약과 본체 계약을 겸하면 RED/GREEN 판정이 섞인다.


# ===========================================================================
# R7/R8 — 회귀 0
# ===========================================================================
@pytest.mark.asyncio
async def test_r7_donchian_skip_unchanged():
    """GREEN(회귀 0) — donchian 은 종전대로 skip. 기존 4케이스는
    `tests/unit/engine/test_risk_donchian_skip_buy.py` 가 그대로 진다."""
    registry = StrategyRegistry()
    donchian = _spy("donchian_swing")
    registry.register(donchian)
    risk = RiskManager(registry, _order_engine())

    await risk.on_tick(TICKER, current_price=85000, open_price=80000, change_rate=21.43)

    assert donchian.buy_calls == []


@pytest.mark.asyncio
async def test_r8_third_strategy_still_evaluated():
    """RED (HEAD) — kojiro 는 skip 되고 제3 전략은 그대로 평가된다.

    `continue` 를 `pass` 로 바꾸는 뮤테이션과, skip 이 루프 전체를 끊는(break)
    구현을 동시에 잡는다.
    """
    registry = StrategyRegistry()
    kojiro = _spy("kojiro")
    momentum = _spy("momentum")
    registry.register(kojiro)
    registry.register(momentum)
    risk = RiskManager(registry, _order_engine())

    await risk.on_tick(TICKER, current_price=85000, open_price=80000, change_rate=21.43)

    assert kojiro.buy_calls == []
    assert len(momentum.buy_calls) == 1, "제3 전략의 매수 평가가 함께 죽었다"


# ===========================================================================
# R6 — 경로 A 무접촉 (실 `_swing_buy_poll_loop`)
# ===========================================================================
@contextlib.contextmanager
def _freeze_kst(iso: str):
    """`datetime.now` 만 patch — freegun 은 monotonic 까지 얼려 `asyncio.sleep` 이 멈춘다.

    `tests/unit/engine/test_cycle268_tester_real_call_paths.py::_freeze_kst` 답습.
    """
    base_naive = _datetime_module.datetime.fromisoformat(iso)
    base_kst = base_naive.replace(tzinfo=_KST)

    class _Frozen(_datetime_module.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return base_naive
            off = getattr(tz, "utcoffset", lambda _x: None)(None)
            if off == _KST.utcoffset(None):
                return base_kst
            return base_kst.astimezone(tz)

    real = _datetime_module.datetime
    _datetime_module.datetime = _Frozen

    from src.engine import scheduler as _sched

    patched = []
    if getattr(_sched, "datetime", None) is real:
        _sched.datetime = _Frozen
        patched.append(_sched)
    try:
        yield
    finally:
        _datetime_module.datetime = real
        for mod in patched:
            mod.datetime = real


@pytest.mark.asyncio
async def test_r6_swing_poll_loop_still_evaluates_kojiro():
    """GREEN(경로 A 무접촉) — F-3 이 kojiro 매수를 **통째로** 죽이지 않았다는 증거.

    이 테스트가 붉어지면 F-3 는 "오염 차단" 이 아니라 "전략 정지" 다.
    """
    from unittest.mock import patch

    from src.engine.scheduler import TradingScheduler

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = StrategyRegistry()
    sched._pending_next_day_clear = set()
    sched._running = True
    kojiro = _spy("kojiro")
    sched.registry.register(kojiro)
    sched.order_engine = MagicMock()
    sched.order_engine.execute_buy = AsyncMock()

    detail = {"stck_prpr": "10100", "stck_oprc": "10050"}

    with _freeze_kst("2026-05-12 09:10:00"), \
         patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value=detail)):
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False

        t = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=10.0)
        await t

    assert kojiro.buy_calls, (
        "경로 A(_swing_buy_poll_loop)에서도 kojiro 매수 평가가 사라졌다 — "
        "F-3 의 범위를 넘었다"
    )
    assert kojiro.buy_calls[0][0] == TICKER
    assert kojiro.buy_calls[0][2] == 10050, "경로 A 의 시가는 REST `stck_oprc` 여야 한다"
