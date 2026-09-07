"""cycle268 tester 추가 가드 — `caller` depth=2 전제를 **실제 프로덕션 호출 경로**로 실증.

기존 cycle268 테스트는 `on_tick` / `_swing_buy_poll_loop` 라는 **이름만 같은 합성 shim**
으로 `caller` 필드를 검정한다(`test_cycle268_kojiro_gap_behavior.py::on_tick` 등). 그
shim 은 "`sys._getframe(2)` 가 직접 호출자의 이름을 준다" 는 것만 증명할 뿐,
**진짜 `risk.RiskManager.on_tick` 과 `scheduler.TradingScheduler._swing_buy_poll_loop`
가 그 depth 를 실제로 만족하는지**는 증명하지 않는다. 두 실 호출자는 모두
`async def` 이고, 그 사이에 데코레이터·프록시·래퍼가 끼면 depth 는 조용히 어긋나
`caller` 가 틀린 값이 되며 **판독(경로 A/B 비율)이 통째로 뒤집힌다**.

이 파일은 그 간극을 메운다 — 실제 `RiskManager.on_tick` / 실제
`TradingScheduler._swing_buy_poll_loop` 를 **실제 `KojiroStrategy`** 와 함께 태워
마커 행의 `caller` 를 읽는다.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as _datetime_module
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.risk import RiskManager
from src.engine.scheduler import TradingScheduler
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategy_base import StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

MARKER = "[kojiro_gap_observe]"
TICKER = "131290"


@contextlib.contextmanager
def _freeze_kst(iso: str):
    """`datetime.now` 만 patch (freezegun 은 monotonic 까지 얼려 asyncio.sleep 이 멈춘다).

    `test_swing_poll_loop.py::freeze_time` 과 동형이되 kojiro 모듈까지 덮는다.
    """
    base_naive = _datetime_module.datetime.fromisoformat(iso)
    _KST = _datetime_module.timezone(_datetime_module.timedelta(hours=9))
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
    from src.engine.strategies import kojiro as _koj

    patched = []
    for mod in (_sched, _koj):
        if getattr(mod, "datetime", None) is real:
            mod.datetime = _Frozen
            patched.append(mod)
    try:
        yield
    finally:
        _datetime_module.datetime = real
        for mod in patched:
            mod.datetime = real


@pytest.fixture(autouse=True)
def _isolate():
    from src.engine import scanner
    from src.engine.kojiro_gap_observe import reset_kojiro_gap_observe_cap

    reset_kojiro_gap_observe_cap()
    saved = dict(scanner.ticker_prices)
    scanner.ticker_prices.clear()
    yield
    reset_kojiro_gap_observe_cap()
    scanner.ticker_prices.clear()
    scanner.ticker_prices.update(saved)


@contextlib.contextmanager
def _main_board_active():
    """`session_tracker.is_tradable` 이 True 가 되도록 MAIN 보드를 활성화."""
    from src.engine.session import MarketBoard, session_tracker

    saved = set(session_tracker._active)
    session_tracker._active = frozenset({MarketBoard.MAIN})
    try:
        yield
    finally:
        session_tracker._active = saved


def _kojiro() -> KojiroStrategy:
    s = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.2, enabled=True)
    )
    s._candidates[TICKER] = {
        "prev_close": 10000, "atr": 200.0, "stage": 1,
        "ema_s": 9900.0, "ema_m": 9800.0, "ema_l": 9700.0, "atr_ratio": 0.02,
    }
    s._scanned_tickers = [TICKER]
    s.state.total_investment = 100_000_000
    return s


def _rows(caplog):
    """마커 **관측 행**만 (실패 흔적 `observer_failed` 행은 제외)."""
    return [r.getMessage() for r in caplog.records
            if r.getMessage().startswith(MARKER + " ticker=")]


def _fields(line):
    return dict(kv.split("=", 1)
                for kv in line.split(MARKER + " ", 1)[1].split(" "))


# ===========================================================================
# 경로 A — 실제 `TradingScheduler._swing_buy_poll_loop`
# ===========================================================================
@pytest.mark.asyncio
async def test_real_swing_poll_loop_yields_caller_swing_buy_poll_loop(caplog):
    """경로 A 를 **실 프로덕션 호출 스택**으로 봉인한다 — 합성 shim 이 아니다.

    `tests/unit/engine/test_cycle268_kojiro_gap_observe.py` 와
    `.../strategies/test_cycle268_kojiro_gap_behavior.py` 의 `_swing_buy_poll_loop`
    는 이름만 같은 **테스트 shim** 이라, 프레임 개수가 맞아떨어지도록 테스트가
    스스로 맞춰 준 것일 수 있다. 이 테스트는 진짜
    `TradingScheduler._swing_buy_poll_loop` 을 돌려 `sys._getframe(2)` 전제를 잰다.

    ⚠️ **이 축이 잡는 것** — `depth` 기본값 뮤테이션(2→1/3)과 kojiro 쪽 래퍼 메서드
    도입(`self._observe(...)`)을 **둘 다** 검출하는 유일한 테스트다. 합성 shim 축은
    자기 프레임 수에 맞춰져 있어 그 둘 중 하나를 통과시킬 수 있다. 삭제하지 마라.
    """
    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = StrategyRegistry()
    sched._pending_next_day_clear = set()
    sched._running = True
    strategy = _kojiro()
    sched.registry.register(strategy)
    sched.order_engine = MagicMock()
    sched.order_engine.execute_buy = AsyncMock()

    detail = {"stck_prpr": "10100", "stck_oprc": "10050"}

    caplog.set_level(logging.INFO)
    with _freeze_kst("2026-05-12 09:10:00"), \
         patch("src.api.condition.fetch_stock_detail",
               new=AsyncMock(return_value=detail)):
        async def _stopper():
            await asyncio.sleep(0.3)
            sched._running = False
        t = asyncio.create_task(_stopper())
        await asyncio.wait_for(sched._swing_buy_poll_loop(), timeout=10.0)
        await t

    rows = _rows(caplog)
    assert rows, "실제 swing poll 경로에서 마커가 한 행도 나오지 않았다"
    callers = {_fields(r)["caller"] for r in rows}
    assert callers == {"_swing_buy_poll_loop"}, (
        f"depth=2 전제 위반 — 실제 경로 A 의 caller={callers}"
    )


# ===========================================================================
# 경로 B — 실제 `RiskManager.on_tick`
# ===========================================================================
@pytest.mark.asyncio
async def test_real_risk_on_tick_yields_caller_on_tick(caplog):
    """경로 B 를 **실 프로덕션 호출 스택**(`RiskManager.on_tick`)으로 봉인한다.

    위 경로 A 테스트와 같은 성격 — 합성 shim 이 아니라 진짜 호출 스택으로
    `sys._getframe(2)` 전제를 잰다. 두 경로가 **같은 depth 로 서로 다른 이름**을
    내는 것이 `caller` 필드가 A/B 판별 정본으로 성립하는 조건이고, 그 조건은
    두 실경로를 나란히 돌려야만 검정된다(한쪽만으로는 depth 오프셋 오류가
    '양쪽 다 틀린 이름'으로 조용히 통과한다). 삭제하지 마라.
    """
    registry = StrategyRegistry()
    strategy = _kojiro()
    registry.register(strategy)
    order_engine = MagicMock()
    order_engine.execute_buy = AsyncMock()
    rm = RiskManager(registry, order_engine)

    from src.engine import scanner
    scanner.ticker_prev_close[TICKER] = 10000

    caplog.set_level(logging.INFO)
    with _freeze_kst("2026-05-12 09:10:00"), _main_board_active():
        await rm.on_tick(TICKER, 10100, 10050, 0.5)

    scanner.ticker_prev_close.pop(TICKER, None)

    rows = _rows(caplog)
    assert rows, "실제 on_tick 경로에서 마커가 한 행도 나오지 않았다"
    callers = {_fields(r)["caller"] for r in rows}
    assert callers == {"on_tick"}, (
        f"depth=2 전제 위반 — 실제 경로 B 의 caller={callers}"
    )


# ===========================================================================
# 경로 B 의 `ws_*` 는 **동어반복**이다 — 판독 함정 봉인
# ===========================================================================
@pytest.mark.asyncio
async def test_path_b_ws_fields_are_self_referential(caplog):
    """⚠️ 이것은 **회귀 가드가 아니라 판독 함정의 계약화**다 — 깨지면 코드가 아니라
    **명세 §5 판독 절차부터 다시 써야 한다**(아래 마지막 문단).

    `risk.on_tick` 은 `check_buy_signal` **전에** `ticker_prices[t]["open_price"]`
    를 그 틱의 `open_price` 로 덮는다(`risk.py` 상단 "1. 공용 시세 갱신").

    따라서 경로 B 행의 `ws_cmp` 는 **구조적으로 항상 `ws_eq`** 이고 `ws_gap`·
    `ws_verdict` 는 `gap_rate`·`verdict` 의 사본이다 — 그 일치는 "WS 캐시가 인자와
    맞았다" 는 **증거가 아니라 자기 자신과의 비교**다(cycle264 `used_src=rest` →
    `delta_bp=0` 함정과 동형). 경로 B 의 오염 판정은 §5 오프라인 조인으로만 성립한다.

    이 테스트는 그 사실을 **의도된 계약으로 못박아** 판독자가 `ws_cmp=ws_ne` 개수를
    전체 분모로 세는 오독을 막는다. 이 단언이 깨지면(= 경로 B 에서 `ws_ne` 가 나오면)
    `risk.on_tick` 의 갱신 순서가 바뀐 것이므로 판독 절차부터 다시 써야 한다.
    """
    registry = StrategyRegistry()
    strategy = _kojiro()
    registry.register(strategy)
    order_engine = MagicMock()
    order_engine.execute_buy = AsyncMock()
    rm = RiskManager(registry, order_engine)

    from src.engine import scanner
    scanner.ticker_prev_close[TICKER] = 10000
    # 오염된(전혀 다른) WS 캐시를 미리 심어도 on_tick 이 먼저 덮는다.
    scanner.ticker_prices[TICKER] = {"current_price": 1, "open_price": 999999}

    caplog.set_level(logging.INFO)
    with _freeze_kst("2026-05-12 09:10:00"), _main_board_active():
        await rm.on_tick(TICKER, 10100, 10050, 0.5)

    scanner.ticker_prev_close.pop(TICKER, None)

    rows = _rows(caplog)
    assert rows
    for r in rows:
        f = _fields(r)
        assert f["ws_cmp"] == "ws_eq", f"경로 B 는 동어반복이어야 한다: {r}"
        assert f["ws_open"] == f["arg_open"]
        assert f["ws_gap"] == f["gap_rate"]


# ===========================================================================
# tester 뮤테이션 ESCAPED 봉인 3건
# ===========================================================================
def _call_from_named_frame(**kw):
    from src.engine.kojiro_gap_observe import observe_gap

    def _probe_caller():
        observe_gap(**kw)

    def _outer():
        _probe_caller()

    _outer()


def test_ws_absent_when_entry_lacks_open_price_key(caplog):
    """WS 캐시 엔트리가 dict 이지만 `open_price` 키가 **없으면** `ws_absent` 다.

    ESCAPED 뮤테이션 봉인 — `isinstance(ws_entry, dict) and "open_price" in ws_entry`
    에서 `and "open_price" in ws_entry` 를 지워도 전 스위트가 초록이었다. 지우면
    `ws_open=None` 이 되고 `None == arg_open` 이 거짓이라 그 행이 **`ws_ne` 로 찍힌다** —
    "WS 캐시가 인자와 다르다"(= 오염 후보)와 "대조할 값이 아예 없다"가 한 라벨로
    뭉개진다. 명세 §5 가 "`ws_verdict=-` 행을 일치로 세지 마라" 로 막으려던 것의
    거울상이며, 이쪽은 **`ws_ne` 분자를 부풀린다**(더 나쁜 방향).
    """
    from src.engine import scanner
    from src.engine.kojiro_gap_observe import reset_kojiro_gap_observe_cap

    reset_kojiro_gap_observe_cap()
    scanner.ticker_prices[TICKER] = {"current_price": 10100}  # open_price 없음

    caplog.set_level(logging.INFO)
    _call_from_named_frame(
        ticker=TICKER, verdict="candidate", arg_open=10050, prev_close=10000,
        current_price=10100, params={"gap_up_skip_pct": 5.0, "gap_down_skip_pct": -4.0},
    )

    rows = _rows(caplog)
    assert len(rows) == 1
    f = _fields(rows[0])
    assert f["ws_cmp"] == "ws_absent", f"키 부재는 ws_absent 여야 한다: {rows[0]}"
    assert f["ws_open"] == "-"
    assert f["ws_gap"] == "-" and f["ws_verdict"] == "-"


def test_cap_is_peeked_logged_then_marked_not_marked_first(caplog, monkeypatch):
    """cap 은 **peek → 로그 → mark** 순서다(cycle226 D-3 · cycle258 `emit_once` 계약).

    ESCAPED 뮤테이션 봉인 — `_cap.mark_emitted(key)` 를 `logger.info` **앞**으로
    옮겨도 전 스위트가 초록이었다. 그러면 로그 자기실패(핸들러 예외·서식 오류)가
    그날 그 (ticker, caller, verdict) 의 관측을 **영구히 삼킨다** — 흔적은 남지만
    행은 영영 못 나오고, 결측이 "오염이 없었다"로 오독된다(명세 §1 판독 표 5행).
    """
    import src.engine.kojiro_gap_observe as obs

    obs.reset_kojiro_gap_observe_cap()

    calls = {"n": 0}
    real_info = obs.logger.info

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("로그 핸들러 자기실패")
        return real_info(*a, **kw)

    monkeypatch.setattr(obs.logger, "info", flaky)
    caplog.set_level(logging.INFO)

    kw = dict(ticker=TICKER, verdict="pass", arg_open=10050, prev_close=10000,
              current_price=10100,
              params={"gap_up_skip_pct": 5.0, "gap_down_skip_pct": -4.0})
    _call_from_named_frame(**kw)   # 1회차 — 로그가 터진다(never-raise 로 흡수)
    _call_from_named_frame(**kw)   # 2회차 — cap 이 소진되지 않았으므로 다시 나와야 한다

    assert calls["n"] == 2, "1회차 실패가 cap 을 소진해 2회차가 아예 시도되지 않았다"
    assert len(_rows(caplog)) == 1, "2회차 행이 나오지 않았다 = mark 가 로그보다 앞섰다"


def test_cap_key_normalizes_ticker_to_str(caplog):
    """cap 키의 `ticker` 는 `str()` 로 정규화된다 — 같은 종목이 형만 달라 두 번 찍히지 않는다.

    ESCAPED 뮤테이션 봉인 — `str(ticker)` 를 `ticker` 로 바꿔도 전 스위트가 초록이었다.
    프로덕션 두 경로가 모두 `str` 을 주므로 지금은 도달 불가지만, 정규화는 **행 수의
    신뢰성**(이 사이클이 재려는 값)을 지키는 장치이므로 계약으로 못박는다.
    """
    from src.engine.kojiro_gap_observe import reset_kojiro_gap_observe_cap

    reset_kojiro_gap_observe_cap()
    caplog.set_level(logging.INFO)
    base = dict(verdict="candidate", arg_open=10050, prev_close=10000,
                current_price=10100,
                params={"gap_up_skip_pct": 5.0, "gap_down_skip_pct": -4.0})
    _call_from_named_frame(ticker="131290", **base)
    _call_from_named_frame(ticker=131290, **base)

    assert len(_rows(caplog)) == 1, "str/int 혼재가 같은 종목을 두 행으로 갈랐다"
