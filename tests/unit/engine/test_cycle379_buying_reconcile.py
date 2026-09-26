"""cycle379 Red — ⑨A `buying_reconcile`: 체결 0 으로 끝난 매수의 pending 회수.

명세 정본 = `_workspace/red/cycle379_buying_reconcile_spec.md` (§2.3 판정 순서 · §3 마커 · §4 T1~T22)
실측 = `_workspace/domain_consult/cycle373_bundleD_S2_measurements.md` §2
사용자 결정 2026-09-27 「9-a 풀어준 종목 재매수가능」 — 해제 뒤 같은 날 재진입을 막지 않는다.

## 이 파일이 못박는 leaf 표면

``src/engine/buying_reconcile.py``

| 이름 | 계약 |
|---|---|
| ``reconcile_stale_buying(registry, order_engine, holdings, *, min_age_s=300, now=None, max_lookups=10)`` | 코루틴 · never-raise(``CancelledError`` 는 전파) |
| ``BUYING_RECONCILE_MIN_AGE_S`` · ``MAX_ORDER_LOOKUPS_PER_PASS`` · ``ORD_TMD_FUTURE_TOLERANCE_S`` | 300 · 10 · 60 |
| ``reset_buying_reconcile_state()`` | hold cap · 그날 해제 횟수 초기화 |
| ``logger`` | ``logging.getLogger(__name__)`` = ``src.engine.buying_reconcile`` |

KIS·DB seam 은 **모듈 경로**다 — ``src.api.balance.get_daily_orders``(새 keyword-only ``odno=``) ·
``src.db.trade_history.update_trade_status``. leaf 가 함수 안에서 지연 import 하든 최상단에서
import 하든 이 파일의 픽스처가 양쪽을 다 갈아 끼운다.

## 이 설계의 네 축 (명세 §8-1) — 먼저 붉어야 하는 것

1. **양성 증거로만 푼다** — T1(거부 행 → 해제)
2. **부재는 해제 근거가 아니다** — T8(행 없음·다른 주문 행 → 유지)
3. **보유면 유지** — T4·T7(체결통보 유실 = 손절 사각 신호)
4. **await 경합** — T12(조회 도중 체결·새 주문·다른 전략 → 유지 ``raced``)

## HEAD 기준

전부 **RED** — leaf 가 없다. 부재는 수집 오류가 아니라 테스트 안의 ``pytest.fail`` 로 드러낸다.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.db import trade_history as _th_real
from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.unit

_LEAF = "src.engine.buying_reconcile"
_ENTRY = "reconcile_stale_buying"
_M_REL = "[buying_reconcile]"
_M_HOLD = "[buying_hold]"
_M_ERR = "[buying_reconcile_error]"

KST = timezone(timedelta(hours=9))

# 실측 코호트 원형 — 437730 삼현 09-15 09:48:29 momentum 1주 시장가 KRX, 접수 뒤 거래소 거부.
TICKER = "437730"
ODNO = "0000454500"
SID = "momentum"
PRICE = 52_400
DAY_STR = "20260915"

#: 명세 §3 — `[buying_hold]` 사유별 레벨. 쉬는 지정가(`open_order`)가 매일 WARNING 을 내면
#: 21:30 `top_patterns` 가 오염되므로 정상 상태는 INFO 다.
_WARN_REASONS = {"held", "fill_seen", "not_found", "bad_row", "ambiguous_owner", "age_unknown"}
_INFO_REASONS = {"open_order", "too_young", "no_order_no", "lookup_error", "deferred", "raced"}

#: 패치 전에 실 시그니처를 잡아 둔다 — 호출 인자를 위치/키워드 무관하게 정규화한다.
_UTS_SIG = inspect.signature(_th_real.update_trade_status)


def kst(h: int, m: int = 0, s: int = 0, *, day: int = 15) -> datetime:
    return datetime(2026, 9, day, h, m, s, tzinfo=KST)


NOW = kst(10, 0, 0)


# ---------------------------------------------------------------------------
# leaf 접근 — 부재는 명시 RED
# ---------------------------------------------------------------------------
def _leaf():
    try:
        return importlib.import_module(_LEAF)
    except ModuleNotFoundError as exc:
        pytest.fail(f"[Red] leaf `{_LEAF}` 미구현 — {exc} (명세 §2.1)")


def _entry():
    fn = getattr(_leaf(), _ENTRY, None)
    if fn is None:
        pytest.fail(f"[Red] `{_LEAF}.{_ENTRY}` 미구현 (명세 §2.2)")
    return fn


@pytest.fixture(autouse=True)
def _reset_leaf_state():
    """hold cap · 그날 해제 횟수는 모듈 전역이다 — 테스트마다 비운다(명세 §4 파일 autouse)."""

    def _reset() -> None:
        try:
            mod = importlib.import_module(_LEAF)
        except ModuleNotFoundError:
            return
        fn = getattr(mod, "reset_buying_reconcile_state", None)
        if callable(fn):
            fn()

    _reset()
    yield
    _reset()


# ---------------------------------------------------------------------------
# 세계 — 실 StrategyRegistry · 실 OrderEngine · 가짜 KIS · 가짜 DB
# ---------------------------------------------------------------------------
class _Strat(StrategyBase):
    def __init__(self, sid: str, *, max_positions: int = 4) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=sid,
                name=f"{sid}-stub",
                enabled=True,
                weight=0.5,
                params={"exchange": "KRX", "max_positions": max_positions},
            )
        )
        self.state.total_investment = 1_000_000

    async def prepare(self, *, as_of=None) -> None:  # pragma: no cover — 미사용
        return None

    def check_buy_signal(self, ticker, current_price, open_price):  # pragma: no cover
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):  # pragma: no cover
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:  # pragma: no cover
        return 0


class _FakeKis:
    """TTTC0081R 모의 — 새 시그니처 ``(target_date="", exchange="ALL", *, odno="")``.

    - ``odno`` 없음 = 그날 전체 목록(``all_rows``)
    - ``odno`` 있음 = 그 주문 행만. ``by_odno`` 에 있으면 그 값, 없으면 ``all_rows`` 를 odno 로 거른다
      (실측: `ODNO` 단독 필터가 그 주문 1행만 돌려준다 — cycle373 §2)
    - ``on_lookup(odno)`` = 주문번호 조회의 **await 도중**에 세계를 바꾸는 훅(경합 재현)
    """

    def __init__(self) -> None:
        self.all_rows: list[dict] = []
        self.by_odno: dict[str, list[dict]] = {}
        self.calls: list[SimpleNamespace] = []
        self.fail_list: BaseException | None = None
        self.fail_odno: dict[str, BaseException] = {}
        self.on_lookup = None

    async def __call__(self, target_date: str = "", exchange: str = "ALL", *, odno: str = ""):
        self.calls.append(SimpleNamespace(target_date=target_date, exchange=exchange, odno=odno))
        if not odno:
            if self.fail_list is not None:
                raise self.fail_list
            return [dict(r) for r in self.all_rows]
        if self.on_lookup is not None:
            self.on_lookup(odno)
        if odno in self.fail_odno:
            raise self.fail_odno[odno]
        if odno in self.by_odno:
            return [dict(r) for r in self.by_odno[odno]]
        return [dict(r) for r in self.all_rows if r.get("odno") == odno]

    @property
    def list_calls(self) -> list[SimpleNamespace]:
        return [c for c in self.calls if not c.odno]

    @property
    def odno_calls(self) -> list[SimpleNamespace]:
        return [c for c in self.calls if c.odno]


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    import src.api.balance as _bal
    import src.db.system_logs as _sl
    import src.db.trade_history as _th

    kis = _FakeKis()
    uts = AsyncMock(return_value=1)
    wl = AsyncMock(return_value=None)
    monkeypatch.setattr(_bal, "get_daily_orders", kis)
    monkeypatch.setattr(_th, "update_trade_status", uts)
    monkeypatch.setattr(_sl, "write_log", wl)
    try:
        mod = importlib.import_module(_LEAF)
    except ModuleNotFoundError:
        mod = None
    if mod is not None:
        # 최상단 import 로 바인딩을 잡은 구현도 같은 가짜를 보게 한다.
        for name, obj in (("get_daily_orders", kis), ("update_trade_status", uts), ("write_log", wl)):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, obj)

    reg = StrategyRegistry()
    strats: dict[str, _Strat] = {}
    for sid in ("momentum", "volatility_breakout", "long_tail_volatility"):
        s = _Strat(sid)
        reg.register(s)
        strats[sid] = s
    eng = OrderEngine(reg)
    return SimpleNamespace(
        registry=reg, engine=eng, strats=strats, kis=kis, uts=uts, write_log=wl, holdings=[],
    )


@pytest.fixture
def cap(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """leaf 로거 INFO 이상 + 접두 필터(명세 §4 — CI 루트 DEBUG 행을 세지 않는다)."""
    caplog.set_level(logging.INFO, logger=_LEAF)
    return caplog


def _arm(w, ticker: str = TICKER, odno: str = ODNO, sid: str = SID, *, qty: int = 1, price: int = PRICE) -> None:
    """`execute_buy` 가 `place_order` 응답 직후 동기 영역에서 세우는 상태를 그대로 재현한다."""
    s = w.strats[sid]
    s.state.pending_buys.add(ticker)
    s.state.pending_buy_amounts[ticker] = price * qty
    e = w.engine
    e._order_qty[odno] = qty
    e._order_strategy[odno] = sid
    e._order_ticker[odno] = ticker
    e._order_exchange[odno] = "KRX"
    e._order_division[odno] = "01"
    e._pending_buy_orders[odno] = {
        "ticker": ticker, "price": price, "quantity": qty, "strategy_id": sid,
    }


def _s(v) -> str:
    return v if isinstance(v, str) else str(v)


def _row(
    odno: str = ODNO,
    ticker: str = TICKER,
    *,
    sll="02",
    ord_qty=1,
    ccld=0,
    rmn=0,
    cncl=0,
    rjct=0,
    tmd="094829",
    name="현금매수",
    drop: tuple[str, ...] = (),
    **over,
) -> dict:
    """TTTC0081R output1 한 행(값은 KIS 처럼 전부 문자열). 키 모양 = cycle373 원자료."""
    r = {
        "ord_dt": DAY_STR, "ord_gno_brno": "06010", "odno": odno, "orgn_odno": "",
        "ord_dvsn_name": "시장가", "sll_buy_dvsn_cd": sll, "sll_buy_dvsn_cd_name": name,
        "pdno": ticker, "prdt_name": "", "ord_qty": _s(ord_qty), "ord_unpr": "0",
        "ord_tmd": tmd, "tot_ccld_qty": _s(ccld), "avg_prvs": "0", "cncl_yn": "",
        "tot_ccld_amt": "0", "ord_dvsn_cd": "01", "cncl_cfrm_qty": _s(cncl),
        "rmn_qty": _s(rmn), "rjct_qty": _s(rjct), "excg_id_dvsn_cd": "KRX",
    }
    r.update(over)
    for k in drop:
        r.pop(k, None)
    return r


async def _run(w, *, now: datetime = NOW, **kw) -> None:
    await _entry()(w.registry, w.engine, w.holdings, now=now, **kw)


def _recs(caplog, prefix: str) -> list[logging.LogRecord]:
    return [
        r for r in caplog.records
        if r.name == _LEAF and r.getMessage().startswith(prefix + " ")
    ]


def _fields(msg: str) -> dict[str, str]:
    return dict(re.findall(r"(\w+)=(\S+)", msg))


def _holds(caplog) -> list[tuple[str | None, str | None, int]]:
    out = []
    for r in _recs(caplog, _M_HOLD):
        f = _fields(r.getMessage())
        out.append((f.get("ticker"), f.get("reason"), r.levelno))
    return out


def _releases(caplog) -> list[dict[str, str]]:
    out = []
    for r in _recs(caplog, _M_REL):
        f = _fields(r.getMessage())
        f["_level"] = str(r.levelno)
        out.append(f)
    return out


def _uts_calls(w) -> list[dict]:
    """`update_trade_status` 호출을 실 시그니처에 bind — 명시로 넘긴 인자만 남는다."""
    return [dict(_UTS_SIG.bind(*c.args, **c.kwargs).arguments) for c in w.uts.await_args_list]


def _assert_hold(caplog, reason: str, ticker: str = TICKER) -> None:
    got = [(t, rs, lv) for (t, rs, lv) in _holds(caplog) if t == ticker]
    reasons = [rs for (_, rs, _) in got]
    assert reason in reasons, f"`{_M_HOLD} ticker={ticker} reason={reason}` 없음 — 실제 {got}"
    want_level = logging.WARNING if reason in _WARN_REASONS else logging.INFO
    levels = {lv for (_, rs, lv) in got if rs == reason}
    assert levels == {want_level}, (
        f"reason={reason} 레벨이 {sorted(levels)} (기대 {logging.getLevelName(want_level)} — 명세 §3)"
    )


def _assert_untouched(
    w, caplog, *, ticker: str = TICKER, odnos: tuple[str, ...] = (ODNO,), sid: str = SID,
    amount: int = PRICE,
) -> None:
    s = w.strats[sid]
    assert ticker in s.state.pending_buys, f"{ticker} pending 이 풀렸다 — 유지여야 한다"
    assert s.state.pending_buy_amounts.get(ticker) == amount, (
        f"pending_buy_amounts[{ticker}] = {s.state.pending_buy_amounts.get(ticker)} (기대 {amount})"
    )
    for o in odnos:
        assert o in w.engine._pending_buy_orders, f"_pending_buy_orders[{o}] 가 사라졌다"
    w.uts.assert_not_awaited()
    rel = [f for f in _releases(caplog) if f.get("ticker") == ticker]
    assert not rel, f"유지여야 하는데 `{_M_REL}` 이 났다 — {rel}"


# ===========================================================================
# T0 — 표면
# ===========================================================================
def test_t0_surface_constants_signature_and_logger() -> None:
    mod = _leaf()
    fn = _entry()
    assert inspect.iscoroutinefunction(fn), "reconcile_stale_buying 은 코루틴이어야 한다"
    assert getattr(mod, "BUYING_RECONCILE_MIN_AGE_S", None) == 300
    assert getattr(mod, "MAX_ORDER_LOOKUPS_PER_PASS", None) == 10
    assert getattr(mod, "ORD_TMD_FUTURE_TOLERANCE_S", None) == 60
    assert callable(getattr(mod, "reset_buying_reconcile_state", None))

    params = inspect.signature(fn).parameters
    names = list(params)
    assert names[:3] == ["registry", "order_engine", "holdings"], names
    for kw, default in (("min_age_s", 300), ("now", None), ("max_lookups", 10)):
        assert kw in params, f"키워드 `{kw}` 없음"
        assert params[kw].kind is inspect.Parameter.KEYWORD_ONLY, f"`{kw}` 는 keyword-only"
        assert params[kw].default == default, f"`{kw}` 기본값 {params[kw].default!r} (기대 {default!r})"

    lg = getattr(mod, "logger", None)
    assert isinstance(lg, logging.Logger) and lg.name == _LEAF, (
        f"logger 는 getLogger(__name__) = {_LEAF} (신규 leaf — 옛 접두 연속성 없음, 명세 §2.2)"
    )
    assert lg.propagate is True, "영속은 루트 `_DbLogHandler`(src.* INFO 이상) 몫 — 전파를 끊으면 system_logs 에 안 남는다"


# ===========================================================================
# T1 — 거부 행 = 양성 증거 → 해제 (축 1)
# ===========================================================================
async def test_t1_rejected_row_releases_pending_keeps_mappings_and_marks_cancelled(world, cap) -> None:
    _arm(world)
    world.kis.all_rows = [_row(rjct=1)]  # 437730 원형: ord1 · ccld0 · rmn0 · cncl0 · rjct1
    await _run(world)

    s = world.strats[SID]
    e = world.engine
    # 해제 = `_handle_buy_fill` 첫 체결 경로가 지우는 것과 같은 세 가지
    assert TICKER not in s.state.pending_buys
    assert TICKER not in s.state.pending_buy_amounts
    assert ODNO not in e._pending_buy_orders
    # 🔴 매핑 5종은 남긴다 — 판단이 틀려 늦은 체결통보가 와도 올바른 전략·수량으로 선다
    assert e._order_qty.get(ODNO) == 1
    assert e._order_strategy.get(ODNO) == SID
    assert e._order_ticker.get(ODNO) == TICKER
    assert e._order_exchange.get(ODNO) == "KRX"
    assert e._order_division.get(ODNO) == "01"

    calls = _uts_calls(world)
    assert len(calls) == 1, f"update_trade_status {len(calls)}회 (기대 1)"
    a = calls[0]
    assert a["ticker"] == TICKER
    assert a["trade_type"] == TradeType.BUY
    assert a["status"] == TradeStatus.CANCELLED
    assert a.get("strategy") == SID
    assert a.get("order_no") == ODNO, "CANCELLED 는 그 주문 한 건으로 좁혀야 한다(order_no=)"
    assert "match_partial" not in a, "match_partial 을 넘기면 PARTIAL 행까지 CANCELLED 로 뒤집힌다"

    rel = _releases(cap)
    assert len(rel) == 1, f"`{_M_REL}` {len(rel)}줄 (기대 1)"
    f = rel[0]
    assert f["_level"] == str(logging.WARNING)
    assert f.get("ticker") == TICKER
    assert f.get("strategy") == SID
    assert f.get("odno") == ODNO
    assert f.get("kind") == "rejected"
    assert f.get("ord") == "1" and f.get("rjct") == "1" and f.get("cncl") == "0"
    assert f.get("age_s") == "691", f"age_s={f.get('age_s')} (10:00:00 − 09:48:29 = 691)"
    assert f.get("amount") == str(PRICE)
    assert f.get("db") == "1", "db= 에 update_trade_status 의 affected 를 싣는다"
    assert f.get("release_n") == "1"

    # 영속은 루트 `_DbLogHandler` 몫 — leaf 가 write_log 로 한 번 더 쓰지 않는다
    world.write_log.assert_not_awaited()

    # KIS: 전체 목록 1회 + 자기 주문번호 1회, 둘 다 주입 시계의 날짜 · 거래소 ALL
    assert len(world.kis.list_calls) == 1
    assert [c.odno for c in world.kis.odno_calls] == [ODNO]
    assert {c.target_date for c in world.kis.calls} == {DAY_STR}, (
        f"target_date 는 주입된 now 의 날짜여야 한다 — {[c.target_date for c in world.kis.calls]}"
    )
    assert {c.exchange for c in world.kis.calls} == {"ALL"}


# ===========================================================================
# T2 — GTP 08:50 자동취소 행(073240 원형) → 해제, kind=auto_cancel
# ===========================================================================
async def test_t2_gtp_auto_cancel_row_releases(world, cap) -> None:
    tk, od = "073240", "0000149100"
    _arm(world, tk, od, "long_tail_volatility", price=5_160)
    world.kis.all_rows = [
        _row(od, tk, tmd="082934", name="GTP매수자동취소*", ord_dvsn_cd="27", excg_id_dvsn_cd="NXT",
             ord_dt="20260914"),
    ]
    await _run(world, now=kst(9, 45, 0, day=14))

    s = world.strats["long_tail_volatility"]
    assert tk not in s.state.pending_buys
    assert od not in world.engine._pending_buy_orders
    rel = _releases(cap)
    assert len(rel) == 1 and rel[0].get("kind") == "auto_cancel", rel
    assert {c.target_date for c in world.kis.calls} == {"20260914"}


# ===========================================================================
# T3 — kind 는 관측 전용(판정에 안 쓴다) — 네 모양 전부 해제
# ===========================================================================
@pytest.mark.parametrize(
    "row_kw, kind",
    [
        ({"rjct": 1}, "rejected"),
        ({"cncl": 1}, "cancelled"),
        ({"name": "GTP매수자동취소*"}, "auto_cancel"),
        ({}, "zero"),  # 모든 수량 칸 0 · 이름 평범 — KRX 15:30 자동취소가 이 모양일 수 있다
    ],
    ids=["rejected", "cancelled", "auto_cancel", "zero"],
)
async def test_t3_kind_is_observational_every_terminal_shape_releases(world, cap, row_kw, kind) -> None:
    _arm(world)
    world.kis.all_rows = [_row(**row_kw)]
    await _run(world)
    assert TICKER not in world.strats[SID].state.pending_buys
    rel = _releases(cap)
    assert len(rel) == 1 and rel[0].get("kind") == kind, rel


# ===========================================================================
# T4 · T7 — 보유면 유지 (축 3) · KIS 호출 0
# ===========================================================================
async def test_t4_partial_fill_then_cancel_with_holdings_holds_as_held(world, cap) -> None:
    _arm(world)
    world.kis.all_rows = [_row(ccld=1, rmn=0, cncl=1)]
    world.holdings = [SimpleNamespace(ticker=TICKER, quantity=1)]
    await _run(world)
    _assert_untouched(world, cap)
    _assert_hold(cap, "held")
    assert world.kis.calls == [], "메모리 단계(A2)에서 걸렸는데 KIS 를 불렀다"


async def test_t7_zero_row_but_kis_holding_holds_as_held(world, cap) -> None:
    _arm(world)
    world.kis.all_rows = [_row(rjct=1)]
    world.holdings = [SimpleNamespace(ticker=TICKER, quantity=3)]
    await _run(world)
    _assert_untouched(world, cap)
    _assert_hold(cap, "held")
    assert world.kis.calls == []


async def test_t7b_other_strategy_position_holds_as_held(world, cap) -> None:
    _arm(world)
    world.kis.all_rows = [_row(rjct=1)]
    world.strats["volatility_breakout"].state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=PRICE, quantity=1, order_no="X", strategy_id="volatility_breakout",
    )
    await _run(world)
    _assert_untouched(world, cap)
    _assert_hold(cap, "held")
    assert world.kis.calls == []


# ===========================================================================
# T5 — 체결 흔적(잔고 지연) → 유지 fill_seen
# ===========================================================================
async def test_t5_fill_seen_without_holdings_holds(world, cap) -> None:
    _arm(world)
    world.kis.all_rows = [_row(ccld=1, rmn=0, cncl=1)]
    # 수량 0 인 잔고 원소는 "보유" 가 아니다(A2 는 qty>0 만 본다)
    world.holdings = [SimpleNamespace(ticker=TICKER, quantity=0)]
    await _run(world)
    _assert_untouched(world, cap)
    _assert_hold(cap, "fill_seen")


# ===========================================================================
# T6 — 열린 주문 → 유지 open_order (INFO)
# ===========================================================================
async def test_t6a_own_row_has_remaining_qty_holds(world, cap) -> None:
    """자기 행 `rmn>0`. 전체 목록은 비어 있다(첫 쪽 잘림) — B7 만이 이것을 잡는다."""
    _arm(world)
    world.kis.all_rows = []
    world.kis.by_odno = {ODNO: [_row(rmn=1)]}
    await _run(world)
    _assert_untouched(world, cap)
    _assert_hold(cap, "open_order")


async def test_t6b_other_open_buy_on_same_ticker_holds(world, cap) -> None:
    """자기 행은 끝났는데 같은 종목의 다른 매수(수동 MTS 포함)가 열려 있다 — B2."""
    _arm(world)
    world.kis.all_rows = [_row(rjct=1), _row("0000999900", rmn=1, tmd="095000")]
    await _run(world)
    _assert_untouched(world, cap)
    _assert_hold(cap, "open_order")
    assert world.kis.odno_calls == [], "B2(전체 목록)에서 걸린 후보를 주문번호로 또 조회했다"


async def test_t6c_open_buy_on_another_ticker_does_not_block(world, cap) -> None:
    """B2 는 `pdno==t` 로 좁힌다 — 다른 종목의 열린 매수가 이 종목 해제를 막지 않는다."""
    _arm(world)
    world.kis.all_rows = [_row(rjct=1), _row("0000999900", "005930", rmn=1, tmd="095000")]
    await _run(world)
    assert TICKER not in world.strats[SID].state.pending_buys
    assert len(_releases(cap)) == 1


# ===========================================================================
# T8 — 부재는 해제 근거가 아니다 (축 2)
# ===========================================================================
@pytest.mark.parametrize(
    "rows",
    [
        [],                                   # 조회 결과 0행
        [_row(sll="01")],                     # 같은 odno 인데 매도 행
        [_row(ticker="005930")],              # 같은 odno 인데 다른 종목
        [_row(odno="0000454501")],            # 다른 주문 행이 돌아왔다
    ],
    ids=["empty", "sell_row", "other_pdno", "other_odno"],
)
async def test_t8_no_matching_row_holds_as_not_found(world, cap, rows) -> None:
    _arm(world)
    world.kis.all_rows = []
    world.kis.by_odno = {ODNO: rows}
    await _run(world)
    _assert_untouched(world, cap)
    _assert_hold(cap, "not_found")


async def test_t8b_padded_odno_and_pdno_still_match(world, cap) -> None:
    """행 매칭은 `strip()` 비교다(명세 B5) — 주문번호 형식 차이가 기능을 죽이지 않게."""
    _arm(world)
    world.kis.by_odno = {ODNO: [_row(odno=f" {ODNO} ", ticker=f"{TICKER} ", rjct=1)]}
    await _run(world)
    assert TICKER not in world.strats[SID].state.pending_buys
    assert len(_releases(cap)) == 1


# ===========================================================================
# T9 — 주문번호 매핑 없음 → 유지 · KIS 호출 0
# ===========================================================================
async def test_t9_no_order_mapping_holds_without_kis(world, cap) -> None:
    s = world.strats[SID]
    s.state.pending_buys.add(TICKER)
    s.state.pending_buy_amounts[TICKER] = PRICE
    # 다른 종목의 매핑은 있어도 이 종목의 연결 주문은 0 개 (`await place_order` 창)
    world.engine._pending_buy_orders["0000777700"] = {
        "ticker": "005930", "price": 70_000, "quantity": 1, "strategy_id": SID,
    }
    world.kis.all_rows = [_row(rjct=1)]
    await _run(world)
    assert TICKER in s.state.pending_buys
    assert s.state.pending_buy_amounts.get(TICKER) == PRICE
    world.uts.assert_not_awaited()
    _assert_hold(cap, "no_order_no")
    assert world.kis.calls == []


# ===========================================================================
# T10 · T11 — 나이 (출처 = 그 주문 자신의 `ord_tmd`, KST)
# ===========================================================================
@pytest.mark.parametrize(
    "tmd, released",
    [("095501", False), ("095500", True)],
    ids=["299s_too_young", "300s_released"],
)
async def test_t10_min_age_boundary_is_inclusive(world, cap, tmd, released) -> None:
    _arm(world)
    world.kis.all_rows = [_row(rjct=1, tmd=tmd)]
    await _run(world)
    if released:
        assert TICKER not in world.strats[SID].state.pending_buys, "정확히 300초는 풀려야 한다(>=)"
        assert len(_releases(cap)) == 1
    else:
        _assert_untouched(world, cap)
        _assert_hold(cap, "too_young")


@pytest.mark.parametrize(
    "tmd_kw",
    [
        {"tmd": ""},
        {"tmd": "9A0000"},
        {"tmd": "95500"},        # 6자리 아님
        {"tmd": "100200"},       # now + 120초 — 허용 60초 초과 미래
        {"drop": ("ord_tmd",)},  # 키 부재
    ],
    ids=["empty", "non_digit", "five_digits", "future_120s", "missing"],
)
async def test_t11_unreadable_or_future_ord_tmd_holds_as_age_unknown(world, cap, tmd_kw) -> None:
    _arm(world)
    world.kis.all_rows = [_row(rjct=1, **tmd_kw)]
    await _run(world)
    _assert_untouched(world, cap)
    _assert_hold(cap, "age_unknown")


async def test_t11b_small_future_skew_is_tolerated_as_too_young(world, cap) -> None:
    """+30초(허용 60초 안) 는 age_unknown 이 아니다 — 음수 나이 = too_young."""
    _arm(world)
    world.kis.all_rows = [_row(rjct=1, tmd="100030")]
    await _run(world)
    _assert_untouched(world, cap)
    _assert_hold(cap, "too_young")
    assert "age_unknown" not in [rs for (_, rs, _) in _holds(cap)]


# ===========================================================================
# T12 · T13 — await 경합 (축 4): 마지막 await 뒤 재검증, 어긋나면 변이 0
# ===========================================================================
def _race_fill(w):
    def hook(_odno: str) -> None:
        # `_handle_buy_fill` 첫 체결 경로를 흉내 — pending 3종 정리 + 포지션 등록
        s = w.strats[SID]
        s.state.pending_buys.discard(TICKER)
        s.state.pending_buy_amounts.pop(TICKER, None)
        w.engine._pending_buy_orders.pop(ODNO, None)
        s.state.positions[TICKER] = Position(
            ticker=TICKER, buy_price=PRICE, quantity=1, order_no=ODNO, strategy_id=SID,
        )
    return hook


def _race_second_owner(w):
    def hook(_odno: str) -> None:
        w.strats["volatility_breakout"].state.pending_buys.add(TICKER)
    return hook


def _race_new_order(w):
    def hook(_odno: str) -> None:
        w.engine._pending_buy_orders["0000454599"] = {
            "ticker": TICKER, "price": PRICE, "quantity": 1, "strategy_id": SID,
        }
    return hook


def _race_other_position(w):
    def hook(_odno: str) -> None:
        w.strats["long_tail_volatility"].state.positions[TICKER] = Position(
            ticker=TICKER, buy_price=PRICE, quantity=1, order_no="", strategy_id="long_tail_volatility",
        )
    return hook


async def test_t12_fill_during_lookup_is_raced_and_never_cancelled(world, cap) -> None:
    """조회 도중 체결 — 재검증 ①(pending 에 아직 있는가)이 막는다. CANCELLED 호출 0."""
    _arm(world)
    world.kis.all_rows = [_row(rjct=1)]
    world.kis.on_lookup = _race_fill(world)
    await _run(world)
    s = world.strats[SID]
    assert TICKER in s.state.positions, "경합으로 세워진 포지션이 사라졌다"
    world.uts.assert_not_awaited()
    assert not _releases(cap), f"경합인데 해제 마커가 났다 — {_releases(cap)}"
    _assert_hold(cap, "raced")


@pytest.mark.parametrize(
    "make_hook, odnos",
    [
        (_race_second_owner, (ODNO,)),                 # ② 다른 전략이 같은 종목을 pending 으로 들었다
        (_race_new_order, (ODNO, "0000454599")),       # ③ 같은 종목 연결 주문 집합이 바뀌었다
        (_race_other_position, (ODNO,)),               # ④ 다른 전략이 그 종목을 보유하게 됐다
    ],
    ids=["second_owner", "new_order_no", "other_position"],
)
async def test_t13_world_changes_during_lookup_are_raced(world, cap, make_hook, odnos) -> None:
    _arm(world)
    world.kis.all_rows = [_row(rjct=1)]
    world.kis.on_lookup = make_hook(world)
    await _run(world)
    _assert_untouched(world, cap, odnos=odnos)
    _assert_hold(cap, "raced")


# ===========================================================================
# T14 — 재진입 허용 (사용자 결정 9-a): 새 당일 차단을 만들지 않는다
# ===========================================================================
async def test_t14_release_allows_same_day_reentry_and_returns_slot_and_funds(world, cap) -> None:
    reg = StrategyRegistry()
    s = _Strat(SID, max_positions=1)
    reg.register(s)
    world.registry = reg
    world.strats = {SID: s}
    world.engine = OrderEngine(reg)
    _arm(world)
    s.state.buy_blocked_until = 123.0
    s.state.low_funds_tickers["005930"] = 999.0
    world.engine._completed_buy_orders.add("0000000001")
    world.kis.all_rows = [_row(rjct=1)]

    assert reg.is_ticker_blocked_for_buy(TICKER) is True
    assert s.is_max_positions() is True
    used_before = s._calc_used_funds()

    await _run(world)

    assert reg.is_ticker_blocked_for_buy(TICKER) is False, "풀린 종목은 같은 날 다시 살 수 있어야 한다"
    assert s.is_max_positions() is False, "슬롯 1개가 돌아와야 한다"
    assert used_before - s._calc_used_funds() == PRICE, "그 금액만큼 전략 예산이 돌아와야 한다"
    assert s.state.sold_today == set(), "sold_today 에 넣으면 그것이 곧 당일 재매수 차단이다"
    assert s.state.buy_blocked_until == 123.0
    assert s.state.low_funds_tickers == {"005930": 999.0}
    assert world.engine._completed_buy_orders == {"0000000001"}


# ===========================================================================
# T15 — never-raise (CancelledError 만 전파)
# ===========================================================================
async def test_t15a_list_lookup_error_holds_everyone(world, cap) -> None:
    _arm(world)
    world.kis.fail_list = RuntimeError("TTTC0081R 5xx")
    await _run(world)
    _assert_untouched(world, cap)
    _assert_hold(cap, "lookup_error")
    assert world.kis.odno_calls == [], "전체 목록이 실패하면 주문번호 조회로 넘어가지 않는다"


async def test_t15b_order_lookup_error_holds_only_that_candidate(world, cap) -> None:
    _arm(world)
    tk2, od2 = "005930", "0000454600"
    _arm(world, tk2, od2, "volatility_breakout", price=70_000)
    world.kis.all_rows = [_row(rjct=1), _row(od2, tk2, rjct=1)]
    world.kis.fail_odno = {ODNO: RuntimeError("timeout")}
    await _run(world)
    s = world.strats[SID]
    assert TICKER in s.state.pending_buys and s.state.pending_buy_amounts.get(TICKER) == PRICE
    assert ODNO in world.engine._pending_buy_orders
    _assert_hold(cap, "lookup_error")
    assert tk2 not in world.strats["volatility_breakout"].state.pending_buys, "다른 후보는 풀려야 한다"
    assert [f.get("ticker") for f in _releases(cap)] == [tk2]
    assert [a.get("order_no") for a in _uts_calls(world)] == [od2], "실패한 후보에 CANCELLED 를 적었다"


async def test_t15c_db_error_keeps_memory_release_and_marks_db_error(world, cap) -> None:
    _arm(world)
    world.kis.all_rows = [_row(rjct=1)]
    world.uts.side_effect = RuntimeError("pg down")
    await _run(world)
    s = world.strats[SID]
    assert TICKER not in s.state.pending_buys, "DB 실패로 메모리 해제를 되돌리지 않는다(KIS 사실은 확정)"
    assert ODNO not in world.engine._pending_buy_orders
    rel = _releases(cap)
    assert len(rel) == 1 and rel[0].get("db") == "error", rel


async def test_t15d_registry_explodes_is_logged_not_raised(world, cap) -> None:
    def _boom():
        raise RuntimeError("registry boom")

    world.registry.all = _boom  # type: ignore[method-assign]
    await _run(world)
    errs = [
        r for r in cap.records
        if r.name == _LEAF and r.getMessage().startswith(_M_ERR) and r.levelno >= logging.ERROR
    ]
    assert errs, f"`{_M_ERR}` ERROR 흔적이 없다(logger.exception)"


async def test_t15e_malformed_holdings_do_not_raise_and_do_not_release(world, cap) -> None:
    """잔고를 못 읽으면 `held` 를 판정할 수 없다 — 증거 부족 = 유지."""
    _arm(world)
    world.kis.all_rows = [_row(rjct=1)]
    world.holdings = [object()]
    await _run(world)
    _assert_untouched(world, cap)


@pytest.mark.parametrize(
    "row_kw",
    [
        {"ccld": ""},
        {"rmn": ""},
        {"ccld": "abc"},
        {"rmn": "1.5x"},
        {"drop": ("rmn_qty",)},
        {"drop": ("tot_ccld_qty",)},
    ],
    ids=["ccld_empty", "rmn_empty", "ccld_alpha", "rmn_garbage", "rmn_missing", "ccld_missing"],
)
async def test_t15f_unreadable_quantity_is_bad_row_never_zero(world, cap, row_kw) -> None:
    """🔴 빈 값을 0 으로 읽지 않는다 — 양성 증거는 명시값이어야 한다(명세 B6)."""
    _arm(world)
    world.kis.all_rows = []
    world.kis.by_odno = {ODNO: [_row(rjct=1, **row_kw)]}
    await _run(world)
    _assert_untouched(world, cap)
    _assert_hold(cap, "bad_row")


async def test_t15g_cancelled_error_propagates(world, cap) -> None:
    _arm(world)
    world.kis.all_rows = [_row(rjct=1)]
    world.kis.fail_odno = {ODNO: asyncio.CancelledError()}
    with pytest.raises(asyncio.CancelledError):
        await _run(world)
    _assert_untouched(world, cap)


# ===========================================================================
# T16 — 한 종목 연결 주문이 여럿: 전부가 통과해야 푼다
# ===========================================================================
_ODNO_B = "0000454700"


@pytest.mark.parametrize(
    "b_rows, reason",
    [
        ([_row(_ODNO_B, rmn=1, tmd="094900")], "open_order"),
        ([], "not_found"),
    ],
    ids=["b_open", "b_not_found"],
)
async def test_t16a_one_live_order_keeps_the_ticker(world, cap, b_rows, reason) -> None:
    _arm(world)
    _arm(world, odno=_ODNO_B)
    world.kis.all_rows = []
    world.kis.by_odno = {ODNO: [_row(rjct=1)], _ODNO_B: b_rows}
    await _run(world)
    _assert_untouched(world, cap, odnos=(ODNO, _ODNO_B))
    _assert_hold(cap, reason)


async def test_t16b_all_orders_terminal_pops_every_order_and_one_marker(world, cap) -> None:
    _arm(world)
    _arm(world, odno=_ODNO_B)
    world.kis.all_rows = [_row(rjct=1), _row(_ODNO_B, cncl=1, tmd="094900")]
    await _run(world)
    e = world.engine
    assert ODNO not in e._pending_buy_orders and _ODNO_B not in e._pending_buy_orders
    assert TICKER not in world.strats[SID].state.pending_buys
    got = sorted(a.get("order_no") for a in _uts_calls(world))
    assert got == sorted([ODNO, _ODNO_B]), f"CANCELLED 주문번호 {got}"
    rel = _releases(cap)
    assert len(rel) == 1, f"해제 1건 = 마커 1줄 — {rel}"
    assert set(rel[0].get("odno", "").split(",")) == {ODNO, _ODNO_B}


# ===========================================================================
# T17 — 두 전략이 같은 종목을 pending 으로 든다 → 유지 · KIS 호출 0
# ===========================================================================
async def test_t17_ambiguous_owner_holds_without_kis(world, cap) -> None:
    _arm(world)
    world.strats["volatility_breakout"].state.pending_buys.add(TICKER)
    world.kis.all_rows = [_row(rjct=1)]
    await _run(world)
    _assert_untouched(world, cap)
    assert TICKER in world.strats["volatility_breakout"].state.pending_buys
    _assert_hold(cap, "ambiguous_owner")
    assert world.kis.calls == []


# ===========================================================================
# T18 — `[buying_hold]` cap = 1회/(ticker, reason)/일 (사유 전이는 새 줄)
# ===========================================================================
async def test_t18_hold_cap_per_ticker_reason_day(world, cap) -> None:
    _arm(world)
    world.kis.all_rows = [_row(rjct=1, tmd="095900")]
    await _run(world, now=kst(10, 0, 0))   # 60s  → too_young
    await _run(world, now=kst(10, 0, 30))  # 90s  → too_young (같은 날·같은 사유 = 무음)
    assert [rs for (_, rs, _) in _holds(cap)] == ["too_young"]

    world.kis.all_rows = [_row(rjct=1, tmd="095900", rmn=1)]
    await _run(world, now=kst(10, 1, 0))   # 사유 전이 → open_order 새 줄
    assert [rs for (_, rs, _) in _holds(cap)] == ["too_young", "open_order"]

    await _run(world, now=kst(10, 0, 0, day=16))  # 다음 날 → 같은 사유라도 다시 1줄
    assert [rs for (_, rs, _) in _holds(cap)] == ["too_young", "open_order", "open_order"]
    _assert_untouched(world, cap)


# ===========================================================================
# T19 — 후보 0 이면 KIS 호출 0 (기존 sync 테스트의 호출 수 불변 근거)
# ===========================================================================
async def test_t19_no_pending_means_no_kis_call(world, cap) -> None:
    await _run(world)
    assert world.kis.calls == []
    assert not _recs(cap, _M_HOLD) and not _recs(cap, _M_REL)


async def test_t19b_all_candidates_fail_memory_stage_means_no_kis_call(world, cap) -> None:
    _arm(world)  # held
    world.holdings = [SimpleNamespace(ticker=TICKER, quantity=1)]
    s = world.strats["volatility_breakout"]  # no_order_no
    s.state.pending_buys.add("005930")
    s.state.pending_buy_amounts["005930"] = 70_000
    for sid in ("volatility_breakout", "long_tail_volatility"):  # ambiguous_owner
        world.strats[sid].state.pending_buys.add("000660")
    await _run(world)
    assert world.kis.calls == []


# ===========================================================================
# T20 — 패스당 주문번호 조회 상한
# ===========================================================================
@pytest.mark.parametrize("max_lookups, want", [(None, 10), (3, 3)], ids=["default_10", "injected_3"])
async def test_t20_order_lookups_are_capped_per_pass(world, cap, max_lookups, want) -> None:
    tickers = [f"1000{i:02d}" for i in range(1, 13)]
    rows = []
    for i, tk in enumerate(tickers):
        od = f"00005000{i:02d}"
        _arm(world, tk, od, price=10_000)
        rows.append(_row(od, tk, rjct=1))
    world.kis.all_rows = rows
    kw = {} if max_lookups is None else {"max_lookups": max_lookups}
    await _run(world, **kw)
    assert len(world.kis.odno_calls) == want, f"주문번호 조회 {len(world.kis.odno_calls)}회 (기대 {want})"
    assert len(_releases(cap)) == want
    deferred = [t for (t, rs, _) in _holds(cap) if rs == "deferred"]
    assert len(deferred) == 12 - want, f"deferred {deferred}"
    assert all(lv == logging.INFO for (_, rs, lv) in _holds(cap) if rs == "deferred")
    assert len(world.strats[SID].state.pending_buys) == 12 - want


# ===========================================================================
# T21 — 거부 반복: 행위 제한 없음, release_n 으로만 드러낸다(그날 기준)
# ===========================================================================
async def test_t21_repeated_release_same_ticker_counts_without_blocking(world, cap) -> None:
    for n, od in enumerate(("0000454500", "0000460000", "0000470000"), start=1):
        _arm(world, odno=od)
        world.kis.all_rows = [_row(od, rjct=1)]
        await _run(world, now=kst(10, 0, 0) + timedelta(minutes=15 * (n - 1)))
        assert TICKER not in world.strats[SID].state.pending_buys, f"{n}회차가 막혔다"
        assert _releases(cap)[-1].get("release_n") == str(n)

    od = "0000100000"
    _arm(world, odno=od)
    world.kis.all_rows = [_row(od, rjct=1)]
    await _run(world, now=kst(10, 0, 0, day=16))
    assert _releases(cap)[-1].get("release_n") == "1", "release_n 은 그날 그 종목의 횟수다"


# ===========================================================================
# T22 — 같은 주문번호 여러 행(SOR 분할 대비): 수량은 합, ord_tmd 는 가장 늦은 값
# ===========================================================================
@pytest.mark.parametrize(
    "rows, outcome",
    [
        ([_row(rjct=1), _row(rmn=1)], "open_order"),
        ([_row(rjct=1, tmd="094000"), _row(rjct=1, tmd="095501")], "too_young"),
        ([_row(rjct=1), _row(ccld=1)], "fill_seen"),
        ([_row(rjct=1, tmd="094000"), _row(rjct=1, tmd="094500")], "released"),
    ],
    ids=["sum_rmn", "max_ord_tmd", "sum_ccld", "both_terminal"],
)
async def test_t22_multi_row_same_order_no(world, cap, rows, outcome) -> None:
    _arm(world)
    world.kis.all_rows = []
    world.kis.by_odno = {ODNO: rows}
    await _run(world)
    if outcome == "released":
        assert TICKER not in world.strats[SID].state.pending_buys
        assert len(_releases(cap)) == 1
    else:
        _assert_untouched(world, cap)
        _assert_hold(cap, outcome)
