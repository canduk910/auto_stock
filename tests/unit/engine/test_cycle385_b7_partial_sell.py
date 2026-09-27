"""cycle385 B7 — 부분 수량 매도가 **남은 보유까지 지우던** 결함 (보유 축 분리).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` §a·§b·§c·§d·§e·§g·§h (T1~T19)
사용자 결정(2026-09-26/27) = 「보유수량보다 적게 매도… 부분매도해도 잔여보유수량에 대한
추가매도가 가능하도록 실시간잔고의 매도상황을 추적관리할 수 있다는 전제하에 허용」 +
「b7 분할매도 진행」.

## 결함 (HEAD)

`_handle_sell_fill` 은 **주문**의 수량으로 「전량」을 판정한다(`total_filled >= ordered_qty`).
그리고 그 판정 하나로 **포지션 전체**를 지운다. 전략 매도는 언제나 보유 전량을 내므로 두
말이 같았지만, 사람이 일부만 팔면 갈라진다 —

```
보유 10주 · manual-sell 3주 · 3주 체결 → 주문 전량 → del positions + delete_position + sold_today
                                        → 남은 7주가 손절·트레일링·15:20 청산 누구의 눈에도 없다
```

부분 체결은 `pos.quantity` 를 **줄이지도 않는다**.

## 시정 = 판정을 두 축으로 나눈다

- **주문 축** (`total_filled >= ordered_qty` — 그 주문이 끝났나): 장부·매핑·타이머·`_selling`
- **보유 축** (`pos.quantity` 를 체결량만큼 빼고 0 이 됐나): 삭제·DB 삭제·`on_position_closed`·
  `sold_today`·구독 해제

주문이 끝났는데 보유가 남으면 `_selling` 은 **해제**한다 — 남기면 잔여 보유의 손절이 막힌다.

## 이 파일이 지키는 금기

- 보유 축에 **출처 게이트가 없다**(cycle329) — `map`/`payload`/`increment` 어느 출처든 뺀다.
- 소유 전략을 `"momentum"` 기본값으로 짚어 **남의 DB 행을 지우지 않는다**(§e).
- `_selling` 좀비 금지(§g) — 「주문 종료 ∧ 보유 남음」 이면 `_selling` 은 비어 있어야 한다.
- 🔴 caplog 단언은 WARNING 이상 + prefix 로만 센다(CI 루트 로거 DEBUG — cycle252 T2).
  INFO 한 줄(「매도 부분 체결」 의 `held_after=`)만 예외로, 레벨 **정확히 INFO** + 메시지
  **앞머리**로 한정한다.
"""
from __future__ import annotations

import inspect
import logging
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.engine.order_engine import CANCEL_AXIS_SELL, OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.unit

_OE_LOGGER = "src.engine.order_engine"

TICKER = "005930"
#: 🔴 판별력의 전제 — 매수가·체결가·수량이 서로 달라야 손익·수량 맞바꿈이 드러난다.
BUY_PRICE = 10_000
FILL_PRICE = 11_000
HIGH_SINCE_BUY = 12_345
BUY_DATE = date(2026, 9, 21)
BUY_ORDER_NO = "BUY-0000001"

_SIDS = ("momentum", "kojiro", "volatility_breakout", "long_tail_volatility")


class _Strat(StrategyBase):
    """`on_position_closed` 호출을 기록하는 더미 전략."""

    def __init__(self, strategy_id: str) -> None:
        super().__init__(
            StrategyConfig(
                strategy_id=strategy_id,
                name=f"{strategy_id}-dummy",
                enabled=True,
                weight=0.25,
                params={"exchange": "KRX"},
            )
        )
        self.state.total_investment = 10_000_000
        self.closed_calls: list[str] = []

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 0

    def on_position_closed(self, ticker: str) -> None:
        self.closed_calls.append(ticker)


def _position(sid: str, qty: int) -> Position:
    return Position(
        ticker=TICKER, buy_price=BUY_PRICE, quantity=qty, order_no=BUY_ORDER_NO,
        strategy_id=sid, buy_date=BUY_DATE, high_since_buy=HIGH_SINCE_BUY,
    )


def _make_env(monkeypatch, *, holdings: dict[str, int], update_affected: int = 1,
              lookup: str | None = None):
    """보유 전략·장부 응답을 고른 매도 체결 환경.

    - `holdings` = {strategy_id: 보유수량}. 나머지 전략은 미보유.
    - `update_affected` = `update_trade_status` 가 돌려줄 행 수(0 = 장부 행 없음 → 보정 INSERT).
    - `lookup` = `_lookup_strategy_from_trade_history` 가 돌려줄 전략(None = 장부 miss).
    """
    import src.db.positions as positions_mod
    import src.engine.order_engine as _oe
    from src.engine import scanner
    from src.engine.session import MarketBoard, session_tracker

    monkeypatch.setattr(scanner, "ticker_names", {TICKER: "테스트종목"}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prices", {TICKER: {"current_price": FILL_PRICE}},
                        raising=False)
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))
    # 벽시계 독립 — 실전 설정이면 16:00~20:00 에 애프터 44/41 변환이 끼어든다.
    from src.config import settings
    monkeypatch.setattr(settings, "kis_env", "vts")

    registry = StrategyRegistry()
    strats: dict[str, _Strat] = {}
    for sid in _SIDS:
        s = _Strat(sid)
        registry.register(s)
        strats[sid] = s
    for sid, qty in holdings.items():
        strats[sid].state.positions[TICKER] = _position(sid, qty)

    engine = OrderEngine(registry)
    unsubscribe = AsyncMock(return_value=None)
    engine._unsubscribe_if_no_other_strategy = unsubscribe

    calls = SimpleNamespace(update=[], insert=[], save=[], delete=[], place=[])

    async def fake_update(*args, **kwargs):
        calls.update.append((args, kwargs))
        return update_affected

    async def fake_insert(record, *a, **k):
        calls.insert.append(record)
        return None

    _save_sig = inspect.signature(positions_mod.save_position)

    async def fake_save(*args, **kwargs):
        bound = _save_sig.bind(*args, **kwargs)
        bound.apply_defaults()
        calls.save.append(dict(bound.arguments))
        if env.save_raises is not None:
            raise env.save_raises
        return None

    async def fake_delete(ticker, *a, **k):
        calls.delete.append(ticker)
        return None

    async def fake_lookup(*a, **k):
        return env.lookup

    noop = AsyncMock(return_value=None)
    monkeypatch.setattr(_oe, "update_trade_status", fake_update)
    monkeypatch.setattr(_oe, "insert_trade", fake_insert)
    monkeypatch.setattr(_oe, "_update_trade_status_by_order_no", AsyncMock(return_value=1))
    monkeypatch.setattr(_oe, "_lookup_strategy_from_trade_history", fake_lookup)
    monkeypatch.setattr(_oe, "write_log", noop)
    monkeypatch.setattr(_oe, "safe_write_log", noop)
    monkeypatch.setattr(positions_mod, "save_position", fake_save)
    monkeypatch.setattr(positions_mod, "delete_position", fake_delete)
    import src.db.stock_master as _sm
    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))

    env = SimpleNamespace(
        engine=engine, registry=registry, s=strats, calls=calls,
        unsubscribe=unsubscribe, lookup=lookup, save_raises=None,
    )
    return env


@pytest.fixture(autouse=True)
def _drain_timers():
    """남은 30초 재주문 타이머를 정리한다 — 'Task was destroyed' 경고 차단."""
    engines: list[OrderEngine] = []
    yield engines
    for eng in engines:
        for task in list(eng._pending_cancel_tasks.values()):
            task.cancel()
        eng._pending_cancel_tasks.clear()


def _track(drain, env):
    drain.append(env.engine)
    return env


async def _sell_notice(env, order_no: str, qty: int, *, payload: int = 0,
                       price: int = FILL_PRICE) -> None:
    await env.engine.handle_execution_notice(
        ticker=TICKER, order_no=order_no, side="SELL", price=price, quantity=qty,
        ordered_qty_payload=payload,
    )


def _map_order(env, order_no: str, qty: int, sid: str) -> None:
    """우리가 낸 매도 주문의 매핑(= `execute_sell`/manual-sell 이 발사 직후 등록하는 것)."""
    env.engine._order_qty[order_no] = qty
    env.engine._order_strategy[order_no] = sid
    env.engine._order_ticker[order_no] = TICKER


def _held(env, sid: str):
    """그 전략의 추적 보유 수량(포지션이 없으면 None)."""
    pos = env.s[sid].state.positions.get(TICKER)
    return None if pos is None else pos.quantity


def _status_calls(env, status: TradeStatus) -> list:
    return [(a, k) for a, k in env.calls.update if len(a) >= 3 and a[2] == status]


def _warn_lines(caplog, prefix: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.name == _OE_LOGGER and r.levelno >= logging.WARNING
        and r.getMessage().startswith(prefix)
    ]


def _error_lines(caplog, prefix: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.name == _OE_LOGGER and r.levelno >= logging.ERROR
        and r.getMessage().startswith(prefix)
    ]


# ════════════════════════════════════════════════════════════════════════════
# T1 (§b) — 보유보다 작은 주문의 전량 체결 = B7 본체
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_t1_smaller_order_full_fill_keeps_remaining_holding(
    monkeypatch, caplog, _drain_timers,
):
    """🔴 T1 — 10주 보유 중 3주 주문이 다 체결되면 **7주가 남아 추적된다**.

    HEAD: `3 >= 3` → `del positions` + `delete_position` + `sold_today` → 7주 무방비.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))
    _map_order(env, "S1", 3, "kojiro")
    env.engine._selling.add(TICKER)  # 주문 진행 중 표식(발사 뒤 상태)

    await _sell_notice(env, "S1", 3, payload=3)

    koj = env.s["kojiro"]
    pos = koj.state.positions.get(TICKER)
    assert pos is not None, (
        "보유 10주 중 3주 주문이 전량 체결됐는데 포지션이 삭제됐다 — 남은 7주가 "
        "손절·트레일링·15:20 청산 누구의 눈에도 없다(B7 본체)"
    )
    assert pos.quantity == 7, f"보유가 체결량만큼 줄지 않았다: {pos.quantity} (기대 7)"

    # DB — 차감 수량으로 upsert, 나머지 필드는 그대로(upsert 라 한 필드라도 빠지면 덮인다)
    assert len(env.calls.save) == 1, f"save_position 호출 {len(env.calls.save)}회 (기대 1)"
    saved = env.calls.save[0]
    assert saved["ticker"] == TICKER
    assert saved["quantity"] == 7
    assert saved["buy_price"] == BUY_PRICE
    assert saved["order_no"] == BUY_ORDER_NO
    assert saved["strategy_id"] == "kojiro"
    assert saved["buy_date"] == BUY_DATE
    assert saved["high_since_buy"] == HIGH_SINCE_BUY
    assert isinstance(saved["ticker_name"], str)
    assert env.calls.delete == [], "보유가 남았는데 DB 포지션 행이 지워졌다"

    # 닫힘 효과는 하나도 없어야 한다
    assert TICKER not in koj.state.sold_today, "보유가 남았는데 당일 재매수 차단이 걸렸다"
    assert koj.closed_calls == [], "보유가 남았는데 on_position_closed 가 불렸다"
    assert env.unsubscribe.await_count == 0, "보유가 남았는데 시세 구독을 해제하려 했다"

    # 주문 축은 끝났다 — 진행 중 표식 해제(남기면 잔여 손절 마비)
    assert TICKER not in env.engine._selling, (
        "주문은 끝났고 보유는 남았는데 `_selling` 이 남았다 — risk.on_tick 이 "
        "잔여 7주의 손절 평가를 건너뛴다(좀비)"
    )
    completed = _status_calls(env, TradeStatus.COMPLETED)
    assert len(completed) == 1, f"COMPLETED 장부 갱신 {len(completed)}회 (기대 1)"
    assert completed[0][1].get("match_partial") is True
    assert completed[0][1].get("order_no") == "S1"
    for mp in ("_order_qty", "_order_strategy", "_order_ticker", "_filled_qty"):
        assert "S1" not in getattr(env.engine, mp), f"주문 종료인데 {mp}[S1] 가 남았다"

    assert len(_warn_lines(caplog, "[sell_fill_holding_remains]")) == 1, (
        "분할 매도의 성공 서명 `[sell_fill_holding_remains]` WARNING 이 1행이어야 한다"
    )
    assert koj.state.daily_realized_pnl == (FILL_PRICE - BUY_PRICE) * 3, (
        "실현손익은 **판 3주분만** 잡혀야 한다"
    )


# ════════════════════════════════════════════════════════════════════════════
# T2 · T2b · T3 (§a) — 부분 체결은 보유를 줄이고, 누적으로 0 이 되면 닫는다
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_t2_partial_fill_decrements_holding_and_keeps_order_open(
    monkeypatch, caplog, _drain_timers,
):
    """🔴 T2 — 10주 주문의 4주 부분 체결 → 보유 6 · 저장 6 · PARTIAL · `_selling` 유지 · 타이머.

    HEAD: 부분 체결은 `pos.quantity` 를 줄이지 않는다(10 그대로).
    """
    caplog.set_level(logging.INFO, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))
    _map_order(env, "S2", 10, "kojiro")
    env.engine._selling.add(TICKER)

    await _sell_notice(env, "S2", 4, payload=10)

    koj = env.s["kojiro"]
    assert koj.state.positions[TICKER].quantity == 6, (
        f"부분 체결 4주 뒤 보유 {koj.state.positions[TICKER].quantity} (기대 6)"
    )
    assert [c["quantity"] for c in env.calls.save] == [6]
    assert env.calls.save[0]["strategy_id"] == "kojiro"
    assert env.calls.delete == []
    assert len(_status_calls(env, TradeStatus.PARTIAL)) == 1
    assert _status_calls(env, TradeStatus.COMPLETED) == []
    assert TICKER in env.engine._selling, "주문이 아직 열려 있는데 `_selling` 이 풀렸다"
    assert (TICKER, CANCEL_AXIS_SELL) in env.engine._pending_cancel_tasks, (
        "map 출처 부분 체결인데 잔여 취소·재주문 타이머가 없다(cycle273a·332 회귀)"
    )
    assert env.engine._pending_cancel_order_no[(TICKER, CANCEL_AXIS_SELL)] == "S2"
    partial_info = [
        r.getMessage() for r in caplog.records
        if r.name == _OE_LOGGER and r.levelno == logging.INFO
        and r.getMessage().startswith("매도 부분 체결")
    ]
    assert len(partial_info) == 1, partial_info
    assert "held_after=6" in partial_info[0], (
        f"「매도 부분 체결」 INFO 에 보유 잔량이 없다: {partial_info[0]!r}"
    )


@pytest.mark.asyncio
async def test_t2b_two_partials_subtract_increments_not_cumulative(
    monkeypatch, _drain_timers,
):
    """🔴 T2b — 차감은 **증분**(`quantity`)이지 누적(`total_filled`)이 아니다.

    10주 주문 3주 → 2주: 보유 10 → 7 → 5. 누적으로 빼면 10 → 7 → 2(5주 증발).
    명세 M3 를 죽이는 판별 시나리오(T3 는 둘 다 0 으로 수렴해 못 가른다).
    """
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))
    _map_order(env, "S2B", 10, "kojiro")

    await _sell_notice(env, "S2B", 3, payload=10)
    await _sell_notice(env, "S2B", 2, payload=10)

    assert _held(env, "kojiro") == 5, f"보유 {_held(env, 'kojiro')} (기대 5)"
    assert [c["quantity"] for c in env.calls.save] == [7, 5]


@pytest.mark.asyncio
async def test_t3_partial_then_rest_closes_position_once(
    monkeypatch, _drain_timers,
):
    """🔴 T3 — 4주 부분 뒤 6주 체결 → 보유 0 → 닫는다(삭제·훅·당일차단·DB 삭제·구독 해제).

    손익은 두 증분의 합(4주 + 6주)이다.
    """
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))
    _map_order(env, "S3", 10, "kojiro")
    env.engine._selling.add(TICKER)

    await _sell_notice(env, "S3", 4, payload=10)
    await _sell_notice(env, "S3", 6, payload=10)

    koj = env.s["kojiro"]
    assert TICKER not in koj.state.positions, "보유가 0 이 됐는데 포지션이 남았다"
    assert koj.closed_calls == [TICKER], f"on_position_closed 호출 {koj.closed_calls}"
    assert TICKER in koj.state.sold_today
    assert env.calls.delete == [TICKER]
    assert env.unsubscribe.await_count == 1
    assert TICKER not in env.engine._selling
    assert [c["quantity"] for c in env.calls.save] == [6], (
        "닫히는 체결에서는 저장하지 않고 지운다(저장은 부분 체결 6 한 번뿐)"
    )
    assert koj.state.daily_realized_pnl == (FILL_PRICE - BUY_PRICE) * 10
    assert (TICKER, CANCEL_AXIS_SELL) not in env.engine._pending_cancel_tasks, (
        "주문 종료인데 자기 order_no 의 재주문 타이머가 남았다(cycle273a)"
    )


# ════════════════════════════════════════════════════════════════════════════
# T4 · T15 (§b 전제 · §g) — 잔여분 추가 매도가 가능하다
# ════════════════════════════════════════════════════════════════════════════
def _install_place_order(monkeypatch, env, *, inject=None, first_error=None):
    """`src.engine.order_engine.place_order` 를 기록기로 바꾼다.

    `inject(order_no)` 가 있으면 `await place_order` 가 걸린 동안(= 주문번호 매핑이
    아직 비어 있는 창) 그 코루틴을 먼저 돌린다.
    """
    import src.engine.order_engine as _oe
    from src.models.order import OrderResult

    errors = [first_error] if first_error is not None else []

    async def fake_place_order(ticker, side, quantity, price=0, **kwargs):
        env.calls.place.append({"ticker": ticker, "side": str(side), "quantity": quantity,
                                "price": price, **kwargs})
        if errors:
            raise errors.pop(0)
        order_no = f"SELL-{len(env.calls.place):06d}"
        if inject is not None:
            await inject(order_no)
        return OrderResult(order_no=order_no, order_time="100501", krx_org_no="00950")

    monkeypatch.setattr(_oe, "place_order", fake_place_order)


@pytest.mark.asyncio
async def test_t4_next_sell_uses_remaining_holding(monkeypatch, _drain_timers):
    """🔴 T4 — 분할 매도 뒤 손절은 **잔여 7주**를 판다(10주가 아니다).

    15:20 청산·익일청산·트레일링 모두 `execute_sell` 경유라 이 한 경로가 전부다.
    """
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))
    _map_order(env, "S4", 3, "kojiro")
    await _sell_notice(env, "S4", 3, payload=3)
    _install_place_order(monkeypatch, env)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert len(env.calls.place) == 1, (
        f"잔여 보유의 손절이 발사되지 않았다(place_order {len(env.calls.place)}회) — "
        "포지션이 사라졌거나 `_selling` 좀비가 막았다"
    )
    assert env.calls.place[0]["quantity"] == 7, (
        f"손절 수량 {env.calls.place[0]['quantity']} (기대 7 = 차감된 보유)"
    )


@pytest.mark.asyncio
async def test_t15_order_done_with_holding_left_releases_selling(monkeypatch, _drain_timers):
    """🔴 T15 (§g-2) — 「주문 종료 ∧ 보유 남음」 이면 `_selling` 은 비어 있고,
    곧바로 `execute_sell` 이 중복 차단(`ticker in _selling`)에 걸리지 않는다."""
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))
    _map_order(env, "S15", 3, "kojiro")
    env.engine._selling.add(TICKER)
    await _sell_notice(env, "S15", 3, payload=3)

    assert TICKER not in env.engine._selling
    _install_place_order(monkeypatch, env)
    await env.engine.execute_sell(TICKER, Signal.TRAILING_STOP, "kojiro")
    assert len(env.calls.place) == 1, "잔여 보유 매도가 `_selling` 중복 차단에 막혔다"


@pytest.mark.asyncio
async def test_t16_partial_fill_keeps_selling(monkeypatch, _drain_timers):
    """🔵 T16 (§g 회귀) — 주문이 열려 있으면(부분) `_selling` 은 유지된다."""
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))
    _map_order(env, "S16", 10, "kojiro")
    env.engine._selling.add(TICKER)

    await _sell_notice(env, "S16", 4, payload=10)

    assert TICKER in env.engine._selling, (
        "부분 체결에서 `_selling` 이 풀렸다 — 열린 주문 위에 같은 종목 매도가 또 나간다"
    )


# ════════════════════════════════════════════════════════════════════════════
# T5 · T6 (§c) — 추적 보유보다 큰 체결
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_t5_fill_larger_than_holding_closes_without_negative(
    monkeypatch, caplog, _drain_timers,
):
    """🔴 T5 — 보유 5 · 주문 8 · 체결 8 → 음수 없이 0 으로 닫고 WARNING 1행.

    손익은 현행대로 체결 증분(8주) 기준이다(추적 밖 주식의 원가를 모른다 — §m-5).
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 5}))
    _map_order(env, "S5", 8, "kojiro")
    pos_obj = env.s["kojiro"].state.positions[TICKER]

    await _sell_notice(env, "S5", 8, payload=8)

    koj = env.s["kojiro"]
    assert pos_obj.quantity == 0, f"보유 수량이 음수/잔존: {pos_obj.quantity} (기대 0)"
    assert TICKER not in koj.state.positions
    assert koj.closed_calls == [TICKER]
    assert env.calls.delete == [TICKER]
    assert all(c["quantity"] >= 0 for c in env.calls.save), env.calls.save
    assert len(_warn_lines(caplog, "[sell_fill_exceeds_holding]")) == 1
    assert koj.state.daily_realized_pnl == (FILL_PRICE - BUY_PRICE) * 8


@pytest.mark.asyncio
async def test_t6_partial_fill_exceeding_holding_closes_but_keeps_order_open(
    monkeypatch, caplog, _drain_timers,
):
    """🔴 T6 — 보유 5 · 주문 8 · 체결 6(부분) → 부분 분기에서 닫되 `_selling` 유지 · 타이머.

    주문은 아직 2주가 열려 있다 — 해제는 그 주문의 종료 통보 또는 J-2 `gone` 이 한다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 5}))
    _map_order(env, "S6", 8, "kojiro")
    env.engine._selling.add(TICKER)

    await _sell_notice(env, "S6", 6, payload=8)

    koj = env.s["kojiro"]
    assert TICKER not in koj.state.positions, "보유 5 에 6주가 체결됐는데 포지션이 남았다"
    assert koj.closed_calls == [TICKER]
    assert TICKER in koj.state.sold_today
    assert env.calls.delete == [TICKER]
    assert env.unsubscribe.await_count == 0, "주문이 열려 있는 동안은 구독을 끊지 않는다"
    assert TICKER in env.engine._selling, "주문이 열려 있는데 `_selling` 이 풀렸다"
    assert (TICKER, CANCEL_AXIS_SELL) in env.engine._pending_cancel_tasks
    assert len(_warn_lines(caplog, "[sell_fill_exceeds_holding]")) == 1


# ════════════════════════════════════════════════════════════════════════════
# T7 · T8 · T9 (§d) — 매핑 부재 매도(MTS/HTS 수동 · 발사 창)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_t7_mts_partial_sell_decrements_the_real_owner(
    monkeypatch, caplog, _drain_timers,
):
    """🔴 T7 — kojiro 보유 종목을 MTS 로 3주 팔면 kojiro 에서 7주로 줄어든다.

    HEAD: 매핑·장부 miss → `"momentum"` 폴백 → momentum 에서 `sold_today`·훅 +
    `delete_position(ticker)` 가 **kojiro 의 DB 행을 지운다**(PK=ticker).
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(
        monkeypatch, holdings={"kojiro": 10}, update_affected=0, lookup=None,
    ))
    # 우리 손절이 `[sell_qty_partial_locked]` 로 `_selling` 을 유지해 둔 상태(§d)
    env.engine._selling.add(TICKER)
    # cycle385 부록 R-3 (R-10 기대값 조정) — 그 동결은 `_selling_locked_wait` 표식을 함께 세운다.
    # 매핑 없는 외부 종료가 `_selling` 을 푸는 것은 **동결이 기다리던** 종료일 때뿐이다(무관한
    # 종료는 우리 발사 중 표식을 못 푼다 — LOW #3). 이 테스트가 재는 「MTS 종료 → 해제」는 그
    # 동결 상태의 행위다.
    env.engine._selling_locked_wait.add(TICKER)

    await _sell_notice(env, "MTS-0001", 3, payload=3)

    koj, mom = env.s["kojiro"], env.s["momentum"]
    assert _held(env, "kojiro") == 7, f"주인 전략(kojiro) 보유 {_held(env, 'kojiro')} (기대 7)"
    assert TICKER not in mom.state.sold_today, "보유하지 않은 momentum 에 당일 차단이 걸렸다"
    assert mom.closed_calls == [] and koj.closed_calls == []
    assert env.calls.delete == [], "MTS 부분 매도가 kojiro 의 DB 포지션 행을 지웠다"
    assert [c["strategy_id"] for c in env.calls.save] == ["kojiro"]
    lines = _warn_lines(caplog, "[sell_fill_owner_from_holding]")
    assert len(lines) == 1 and "from=none" in lines[0], lines
    # 보정 INSERT(장부 행 없음) 는 보유 전략으로 적힌다 — momentum 오귀속 금지
    assert len(env.calls.insert) == 1
    rec = env.calls.insert[0]
    assert rec.strategy == "kojiro", f"보정 INSERT 전략 {rec.strategy!r} (기대 kojiro)"
    assert rec.trade_type == TradeType.SELL and rec.status == TradeStatus.COMPLETED
    assert TICKER not in env.engine._selling, (
        "MTS 주문이 끝났는데 우리 `_selling` 이 남았다 — 차감된 잔여 7주의 손절 재평가가 막힌다"
    )


@pytest.mark.asyncio
async def test_t7b_disabled_strategy_holding_is_still_the_owner(
    monkeypatch, _drain_timers,
):
    """🔴 T7b (§e-2) — 꺼진 전략의 보유도 실보유다. 보유자 조회는 `registry.all()`
    이어야 한다(`enabled()` 면 꺼진 kojiro 를 못 보고 momentum 폴백으로 샌다)."""
    env = _track(_drain_timers, _make_env(
        monkeypatch, holdings={"kojiro": 10}, update_affected=0, lookup=None,
    ))
    env.s["kojiro"].config.enabled = False

    await _sell_notice(env, "MTS-0007B", 3, payload=3)

    assert _held(env, "kojiro") == 7, f"꺼진 kojiro 보유 {_held(env, 'kojiro')} (기대 7)"
    assert env.calls.delete == []
    assert TICKER not in env.s["momentum"].state.sold_today


@pytest.mark.asyncio
async def test_t7c_ledger_strategy_not_holding_defers_to_single_holder(
    monkeypatch, caplog, _drain_timers,
):
    """🔴 T7c (§e-3 ④ 둘째 줄) — 장부 전략(VB)은 미보유, 보유자는 kojiro 하나 →
    보유 축(수량·저장·손익)은 kojiro, 장부 축(`update_trade_status(strategy=)`)은 VB.

    PENDING 행이 VB 로 적혀 있으므로 장부 WHERE 는 VB 여야 맞는다. 보유 축을 VB 로
    두면 kojiro 의 7주가 추적에서 어긋난다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))
    _map_order(env, "S7C", 3, "volatility_breakout")

    await _sell_notice(env, "S7C", 3, payload=3)

    koj, vb = env.s["kojiro"], env.s["volatility_breakout"]
    assert _held(env, "kojiro") == 7
    assert [c["strategy_id"] for c in env.calls.save] == ["kojiro"]
    assert koj.state.daily_realized_pnl == (FILL_PRICE - BUY_PRICE) * 3
    assert vb.state.daily_realized_pnl == 0, "손익이 보유하지 않은 장부 전략에 잡혔다"
    completed = _status_calls(env, TradeStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0][1].get("strategy") == "volatility_breakout", (
        f"장부 갱신 전략 {completed[0][1].get('strategy')!r} — PENDING 행의 전략(VB)이어야 "
        "WHERE 가 맞는다"
    )
    lines = _warn_lines(caplog, "[sell_fill_owner_from_holding]")
    assert len(lines) == 1, lines
    assert "from=volatility_breakout" in lines[0] and "to=kojiro" in lines[0], lines[0]


@pytest.mark.asyncio
async def test_t8_increment_source_repeated_notices_subtract_each_time(
    monkeypatch, _drain_timers,
):
    """🔴 T8 — payload 도 매핑도 없는 퇴화(`increment`): 같은 주문번호 2주 → 1주.

    통보마다 주문 종료로 읽히지만(cycle329 현행) 보유 축은 **통보마다 체결량만큼**
    빠지고 0 에서만 닫힌다 — 출처 게이트 없음.
    """
    env = _track(_drain_timers, _make_env(
        monkeypatch, holdings={"kojiro": 10}, update_affected=0, lookup=None,
    ))

    await _sell_notice(env, "MTS-0002", 2)
    await _sell_notice(env, "MTS-0002", 1)

    koj = env.s["kojiro"]
    assert _held(env, "kojiro") == 7, f"보유 {_held(env, 'kojiro')} (기대 7)"
    assert koj.closed_calls == []
    assert env.calls.delete == []
    assert [c["quantity"] for c in env.calls.save] == [8, 7]


@pytest.mark.asyncio
async def test_t9_mts_full_sell_closes_in_the_real_owner(monkeypatch, _drain_timers):
    """🔴 T9 — MTS 로 10주 전부 팔면 **kojiro 에서** 닫힌다(momentum 무접촉)."""
    env = _track(_drain_timers, _make_env(
        monkeypatch, holdings={"kojiro": 10}, update_affected=0, lookup=None,
    ))

    await _sell_notice(env, "MTS-0003", 10, payload=10)

    koj, mom = env.s["kojiro"], env.s["momentum"]
    assert TICKER not in koj.state.positions
    assert koj.closed_calls == [TICKER]
    assert TICKER in koj.state.sold_today
    assert TICKER not in mom.state.sold_today and mom.closed_calls == []
    assert env.calls.delete == [TICKER]


# ════════════════════════════════════════════════════════════════════════════
# T10 · T11 · T11b · T12 (§e) — 소유 해석
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_t10_no_holder_keeps_current_momentum_fallback(
    monkeypatch, caplog, _drain_timers,
):
    """🔵 T10 — 아무도 안 들고 있으면 **현행 그대로**(momentum 폴백 · 멱등 정리)."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={}, lookup=None))

    await _sell_notice(env, "MTS-0010", 3, payload=3)

    mom = env.s["momentum"]
    assert len(_warn_lines(caplog, "[sell_fill_strategy_lookup_fallback]")) == 1
    assert TICKER in mom.state.sold_today
    assert mom.closed_calls == [TICKER]
    assert env.calls.delete == [TICKER]
    assert env.unsubscribe.await_count == 1, "추적 보유 없는 멱등 정리의 구독 해제(현행)"
    assert _warn_lines(caplog, "[sell_fill_owner_from_holding]") == []
    assert _error_lines(caplog, "[sell_fill_owner_ambiguous]") == []


@pytest.mark.asyncio
async def test_t11_two_holders_with_non_holding_ledger_strategy_is_ambiguous(
    monkeypatch, caplog, _drain_timers,
):
    """🔴 T11 — 장부 전략(VB)은 미보유, 보유자가 둘(momentum·kojiro) → 보유 축 **무동작**.

    어느 한쪽을 고르면 남의 수량·DB 행을 건드린다. ERROR 로 알리고 주문 축만 닫는다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(
        monkeypatch, holdings={"momentum": 4, "kojiro": 6},
    ))
    _map_order(env, "S11", 3, "volatility_breakout")
    env.engine._selling.add(TICKER)

    await _sell_notice(env, "S11", 3, payload=3)

    s = env.s
    assert (_held(env, "momentum"), _held(env, "kojiro")) == (4, 6), (
        "보유자가 둘인데 한쪽 수량을 건드렸다"
    )
    assert env.calls.save == [] and env.calls.delete == []
    for sid in _SIDS:
        assert s[sid].closed_calls == [], f"{sid} 훅이 불렸다"
        assert TICKER not in s[sid].state.sold_today, f"{sid} 에 당일 차단이 걸렸다"
    assert env.unsubscribe.await_count == 0
    assert len(_error_lines(caplog, "[sell_fill_owner_ambiguous]")) == 1
    assert TICKER not in env.engine._selling, "주문 종료인데 `_selling` 이 남았다"
    assert "S11" not in env.engine._order_qty, "주문 종료인데 매핑이 남았다"
    assert _warn_lines(caplog, "[sell_fill_holding_remains]") == [], (
        "보유 축이 무동작인데 분할 매도 성공 서명이 찍혔다 — 판독을 오도한다"
    )


@pytest.mark.asyncio
async def test_t11b_two_holders_without_ledger_falls_to_holding_momentum(
    monkeypatch, caplog, _drain_timers,
):
    """🔵 T11b (§e-3 ② → ④ 첫 줄) — 매핑·장부 miss + 보유자 2 → ② 는 「정확히 1」이
    아니라 momentum 폴백 → momentum 이 **실제로 보유**하므로 ④ 첫 줄로 momentum 에서 뺀다."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(
        monkeypatch, holdings={"momentum": 4, "kojiro": 6}, update_affected=0,
    ))

    await _sell_notice(env, "MTS-0011", 3, payload=3)

    assert (_held(env, "momentum"), _held(env, "kojiro")) == (1, 6), (
        f"(momentum, kojiro) = {(_held(env, 'momentum'), _held(env, 'kojiro'))} (기대 (1, 6))"
    )
    assert _error_lines(caplog, "[sell_fill_owner_ambiguous]") == []


@pytest.mark.asyncio
async def test_t12_ledger_recovered_strategy_without_position_is_cycle147(
    monkeypatch, caplog, _drain_timers,
):
    """🔵 T12 — cycle147 005940 재현(보유 0, 장부 = LTV) → LTV `sold_today` 현행 보존."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(
        monkeypatch, holdings={}, lookup="long_tail_volatility",
    ))

    await _sell_notice(env, "LTV-0012", 5, payload=5)

    ltv = env.s["long_tail_volatility"]
    assert TICKER in ltv.state.sold_today
    assert ltv.closed_calls == [TICKER]
    assert TICKER not in env.s["momentum"].state.sold_today
    assert _warn_lines(caplog, "[sell_fill_owner_from_holding]") == []


# ════════════════════════════════════════════════════════════════════════════
# T13 · T14 (§a-2) — 발사 수량 고정 `send_qty`
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_t13_fill_inside_send_window_does_not_shrink_registered_qty(
    monkeypatch, caplog, _drain_timers,
):
    """🔴 T13 — `await place_order` 도중 3주 체결(payload 10)이 보유를 7 로 줄여도,
    매핑·PENDING 은 **보낸 수량 10** 이다. 그래야 잔여 7주 통보가 overrun 클램프에
    잘리지 않고 보유를 0 으로 닫는다.

    `pos.quantity` 를 발사 뒤 다시 읽으면 7 이 적혀 → 잔여 통보 7 이 `3+7 > 7` 로 4 로
    잘려 → 실보유 0 인데 3주 유령이 남는다(§a-2).
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))

    async def inject(order_no):
        await _sell_notice(env, order_no, 3, payload=10)

    _install_place_order(monkeypatch, env, inject=inject)
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert len(env.calls.place) == 1 and env.calls.place[0]["quantity"] == 10
    order_no = "SELL-000001"
    assert env.engine._order_qty.get(order_no) == 10, (
        f"`_order_qty[{order_no}]` = {env.engine._order_qty.get(order_no)} (기대 10 = 보낸 수량)"
    )
    pending = [r for r in env.calls.insert if r.status == TradeStatus.PENDING]
    assert len(pending) == 1 and pending[0].quantity == 10, (
        f"PENDING 수량 {[r.quantity for r in pending]} (기대 [10])"
    )
    assert _held(env, "kojiro") == 7, f"발사 창 3주 체결 뒤 보유 {_held(env, 'kojiro')} (기대 7)"

    await _sell_notice(env, order_no, 7, payload=10)

    assert _warn_lines(caplog, "[fill_qty_overrun]") == [], (
        "잔여 7주 통보가 overrun 으로 잘렸다 — 매핑에 깎인 수량이 적혔다"
    )
    assert TICKER not in env.s["kojiro"].state.positions, "실보유 0 인데 유령 보유가 남았다"
    assert env.s["kojiro"].state.daily_realized_pnl == (FILL_PRICE - BUY_PRICE) * 10


@pytest.mark.asyncio
async def test_t14_fallback_send_uses_same_fixed_qty(monkeypatch, _drain_timers):
    """🔴 T14 — 1차 시장가 거부(APBK1943) → 5호가 지정가 폴백 발사 창에서 3주 체결
    (payload 10) → 폴백 매핑·PENDING 도 **루프 상단 값 10**."""
    from src.api.base import KisApiError

    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))

    async def inject(order_no):
        await _sell_notice(env, order_no, 3, payload=10)

    _install_place_order(
        monkeypatch, env, inject=inject,
        first_error=KisApiError(rt_cd="1", msg_cd="APBK1943",
                                msg1="시장가호가불가로 주문이 불가합니다."),
    )
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "kojiro")

    assert len(env.calls.place) == 2, f"폴백 발사가 없다: {env.calls.place}"
    assert env.calls.place[1]["quantity"] == 10
    fb_no = "SELL-000002"
    assert env.engine._order_qty.get(fb_no) == 10, (
        f"폴백 `_order_qty[{fb_no}]` = {env.engine._order_qty.get(fb_no)} (기대 10)"
    )
    pending = [r for r in env.calls.insert if r.status == TradeStatus.PENDING]
    assert len(pending) == 1 and pending[0].quantity == 10, [r.quantity for r in pending]
    assert pending[0].order_no == fb_no


# ════════════════════════════════════════════════════════════════════════════
# T17 · T18 · T19 (§h)
# ════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_t17_save_failure_is_absorbed_and_order_axis_completes(
    monkeypatch, caplog, _drain_timers,
):
    """🔴 T17 — `save_position` 이 터져도 체결통보 콜백은 예외를 내지 않는다.

    콜백 예외는 WS 재연결을 부른다(`handler.py`). 메모리는 차감되고, 주문 축은
    끝까지 간다(매핑 pop · `_selling` 해제). DB 는 옛 수량 → 재시작 뒤 매도 시점
    #1.5 가 자기 치유한다(§i).
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))
    env.save_raises = RuntimeError("rds down")
    _map_order(env, "S17", 3, "kojiro")
    env.engine._selling.add(TICKER)

    await _sell_notice(env, "S17", 3, payload=3)  # 예외가 나면 여기서 실패한다

    assert _held(env, "kojiro") == 7, f"보유 {_held(env, 'kojiro')} (기대 7)"
    errs = _error_lines(caplog, "[sell_fill_db_error]")
    assert len(errs) == 1 and "step=save_position" in errs[0], errs
    assert "S17" not in env.engine._order_qty
    assert TICKER not in env.engine._selling
    assert len(_status_calls(env, TradeStatus.COMPLETED)) == 1


@pytest.mark.asyncio
async def test_t18_manual_part_then_strategy_rest_closes_once(monkeypatch, _drain_timers):
    """🔴 T18 — manual 3주 종료 → 전략 7주 종료 = `on_position_closed` 전체 **1회**,
    당일 차단은 두 번째에서야 걸린다."""
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))
    _map_order(env, "MAN-1", 3, "kojiro")
    await _sell_notice(env, "MAN-1", 3, payload=3)

    koj = env.s["kojiro"]
    assert TICKER not in koj.state.sold_today
    assert koj.closed_calls == []

    _map_order(env, "STRAT-1", 7, "kojiro")
    await _sell_notice(env, "STRAT-1", 7, payload=7)

    assert koj.closed_calls == [TICKER], f"on_position_closed 호출 {koj.closed_calls} (기대 1회)"
    assert TICKER in koj.state.sold_today
    assert TICKER not in koj.state.positions
    assert env.calls.delete == [TICKER]
    assert koj.state.daily_realized_pnl == (FILL_PRICE - BUY_PRICE) * 10


@pytest.mark.asyncio
async def test_t19_unsubscribe_only_when_holding_reaches_zero(monkeypatch, _drain_timers):
    """🔴 T19 — 잔여 보유의 WS 틱을 끊으면 손절이 REST 폴에만 기댄다.

    3주 종료(보유 7) → 해제 0 / 이어서 7주 종료(보유 0) → 해제 1.
    """
    env = _track(_drain_timers, _make_env(monkeypatch, holdings={"kojiro": 10}))
    _map_order(env, "S19A", 3, "kojiro")
    await _sell_notice(env, "S19A", 3, payload=3)
    assert env.unsubscribe.await_count == 0

    _map_order(env, "S19B", 7, "kojiro")
    await _sell_notice(env, "S19B", 7, payload=7)
    assert env.unsubscribe.await_count == 1
