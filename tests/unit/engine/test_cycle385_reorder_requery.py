"""cycle385 J-2 — 손절 잔여 재주문 **직전** 보유 재조회 (T20~T26).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` §f
자문 = `_workspace/domain_consult/cycle332_buy_cancel_timer.md` §9 J-2

## 결함 (HEAD)

`_cancel_and_reorder` 는 30초 전에 찍어 둔 `remaining` 을 **그대로** 발사한다.
포지션 재조회가 한 줄도 없다(cycle329 자문 실측). 그 30초(+ `cancel_order` 왕복)
동안 체결이 더 났거나 포지션이 이미 닫혔으면, 없는 주식을 파는 주문이 나간다.

## 시정 = 마지막 await 뒤 · `place_order` 앞(동기)에서 **registry 전수**로 재조회

| 보유자 | 발사 |
|---|---|
| 정확히 1 | `min(remaining, 보유)` — 🔴 상한이지 증액이 아니다(운영자가 남긴 주식을 팔지 않는다) |
| 0 | **발사 안 함** + `_selling` 해제 |
| 2 이상 · 판정 예외 | `remaining`(현행) — 의심스러우면 쏜다. 손절 잔여를 버리는 쪽이 더 비싸다 |

🔴 전략 한정 조회(`registry.get(strategy_id)`)는 **`"momentum"` 기본값 함정**에 걸린다 —
`_cancel_and_reorder` 는 `self._order_strategy.get(order_no, "momentum")` 을 쓰므로 매핑이
없으면 momentum 에서 찾다가 「보유 0」으로 오판해 손절 잔여를 버린다(T23).

🔴 caplog 단언은 레벨 + prefix 로 한정한다(CI 루트 로거 DEBUG — cycle252 T2).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.engine.order_engine import CANCEL_AXIS_SELL, OrderEngine
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_OE_LOGGER = "src.engine.order_engine"

TICKER = "161580"
#: 🔴 원주문 ↔ 재주문 번호가 달라야 키 오염을 가른다.
ORIG_NO = "ORD-PARTIAL-3850"
NEW_NO = "ORD-REORDER-3859"


class _Strat(StrategyBase):
    def __init__(self, sid: str) -> None:
        super().__init__(
            StrategyConfig(strategy_id=sid, name=f"{sid}-dummy", enabled=True,
                           weight=0.25, params={"exchange": "KRX"})
        )
        self.state.total_investment = 10_000_000

    async def prepare(self) -> None:
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return 0


def _pos(sid: str, qty: int) -> Position:
    return Position(ticker=TICKER, buy_price=10_000, quantity=qty, order_no="BUY-1",
                    strategy_id=sid, buy_date=date(2026, 9, 21))


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch):
    import src.db.stock_master as _sm
    import src.engine.order_engine as _oe
    import src.engine.scanner as _scanner
    from src.engine.session import session_tracker

    monkeypatch.setattr(_oe, "PARTIAL_FILL_WAIT", 0)
    monkeypatch.setattr(_oe, "write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "safe_write_log", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "insert_trade", AsyncMock(return_value=None))
    monkeypatch.setattr(_oe, "update_trade_status", AsyncMock(return_value=1))
    monkeypatch.setattr(_sm, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(_scanner, "ticker_prices", {TICKER: {"current_price": 35_000}})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    # 벽시계 독립 — 실전 설정이면 16:00~20:00 에 애프터 호가쌍 교체가 끼어든다.
    from src.config import settings
    monkeypatch.setattr(settings, "kis_env", "vts")

    reg = StrategyRegistry()
    strats = {sid: _Strat(sid) for sid in ("momentum", "kojiro", "donchian_swing")}
    for s in strats.values():
        reg.register(s)
    engine = OrderEngine(reg)
    engine._order_exchange[ORIG_NO] = "KRX"

    place = AsyncMock(return_value=SimpleNamespace(order_no=NEW_NO, order_time="110000",
                                                   krx_org_no=""))
    cancel = AsyncMock(return_value=None)
    monkeypatch.setattr(_oe, "place_order", place)
    monkeypatch.setattr(_oe, "cancel_order", cancel)

    yield SimpleNamespace(engine=engine, reg=reg, s=strats, place=place, cancel=cancel)

    for task in list(engine._pending_cancel_tasks.values()):
        task.cancel()
    engine._pending_cancel_tasks.clear()


def _requery_lines(caplog, verdict: str, *, level: int) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.name == _OE_LOGGER and r.levelno == level
        and r.getMessage().startswith("[reorder_requery]")
        and f"verdict={verdict}" in r.getMessage()
    ]


def _fired_qty(env) -> list[int]:
    return [c.kwargs.get("quantity") for c in env.place.await_args_list]


# ── T20 ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_t20_holding_covers_remaining_fires_remaining(env, caplog):
    """🔵 T20 — 보유 6 ≥ remaining 6 → 취소 1 · 발사 1 (6주) · `verdict=same` INFO."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env.s["kojiro"].state.positions[TICKER] = _pos("kojiro", 6)
    env.engine._order_strategy[ORIG_NO] = "kojiro"

    await env.engine._cancel_and_reorder(TICKER, ORIG_NO, 6, is_stop_loss=True)

    assert env.cancel.await_count == 1
    assert _fired_qty(env) == [6]
    assert env.engine._order_qty.get(NEW_NO) == 6
    assert len(_requery_lines(caplog, "same", level=logging.INFO)) == 1


# ── T21 ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_t21_fills_during_cancel_shrink_the_reorder(env, caplog):
    """🔴 T21 — 취소 왕복 도중 체결로 보유 6 → 2 → 재주문은 **2주**(`shrunk` WARNING).

    HEAD: 30초 전 스냅샷 6 을 그대로 발사 → 없는 4주 매도 → APBK0400.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    pos = _pos("kojiro", 6)
    env.s["kojiro"].state.positions[TICKER] = pos
    env.engine._order_strategy[ORIG_NO] = "kojiro"

    async def _cancel_side_effect(*a, **k):
        pos.quantity = 2  # 취소 응답 전에 4주가 더 체결됐다(B7 이 보유를 줄였다)
        return None

    env.cancel.side_effect = _cancel_side_effect

    await env.engine._cancel_and_reorder(TICKER, ORIG_NO, 6, is_stop_loss=True)

    assert _fired_qty(env) == [2], f"재주문 수량 {_fired_qty(env)} (기대 [2])"
    assert env.engine._order_qty.get(NEW_NO) == 2, (
        "재주문 매핑 수량이 발사 수량과 다르다 — 부분/전량 판정이 어긋난다"
    )
    assert len(_requery_lines(caplog, "shrunk", level=logging.WARNING)) == 1


# ── T22 ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_t22_position_gone_skips_reorder_and_releases_selling(env, caplog):
    """🔴 T22 — 재조회 시점에 보유가 없다 → 취소는 내고, 재주문은 **내지 않고**,
    `_selling`·`_selling_since` 를 비운다(원주문은 방금 취소됐고 새 주문도 없다).

    HEAD: 스냅샷 수량으로 발사 → 이미 판 주식을 또 판다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env.engine._order_strategy[ORIG_NO] = "kojiro"
    env.engine._selling.add(TICKER)
    env.engine._selling_since[TICKER] = datetime.now(KST)

    env.engine._schedule_cancel_and_reorder(TICKER, ORIG_NO, 5, is_stop_loss=True)
    key = (TICKER, CANCEL_AXIS_SELL)
    task = env.engine._pending_cancel_tasks[key]
    await task

    assert env.cancel.await_count == 1, "원주문 취소는 현행대로 나가야 한다"
    assert env.place.await_count == 0, "보유가 없는데 재주문이 나갔다"
    assert TICKER not in env.engine._selling, "새 주문이 없는데 `_selling` 이 남았다(좀비)"
    assert TICKER not in env.engine._selling_since
    assert key not in env.engine._pending_cancel_tasks, "자기 타이머 키가 남았다"
    assert len(_requery_lines(caplog, "gone", level=logging.WARNING)) == 1


# ── T23 ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("held", [6, 4])
async def test_t23_registry_wide_lookup_escapes_momentum_default(env, held):
    """🔴 T23 — 매핑 miss(→`"momentum"`) · 실제 보유자 kojiro → kojiro 기준으로 발사.

    전략 한정 조회면 momentum 에서 「보유 0」 → 손절 잔여를 버린다.
    held=4 는 HEAD(스냅샷 6 발사)와도 갈린다.
    """
    env.s["kojiro"].state.positions[TICKER] = _pos("kojiro", held)
    assert ORIG_NO not in env.engine._order_strategy

    await env.engine._cancel_and_reorder(TICKER, ORIG_NO, 6, is_stop_loss=True)

    assert _fired_qty(env) == [min(6, held)], (
        f"재주문 {_fired_qty(env)} (기대 [{min(6, held)}]) — registry 전수가 아니라 "
        "`_order_strategy` 기본값(momentum)으로 좁혀 찾았다"
    )


# ── T24 ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_t24_two_holders_fire_remaining(env, caplog):
    """🔵 T24 — 보유자 2(판정 불가) → 현행대로 `remaining` 발사 · `ambiguous` WARNING."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env.s["momentum"].state.positions[TICKER] = _pos("momentum", 1)
    env.s["kojiro"].state.positions[TICKER] = _pos("kojiro", 1)
    env.engine._order_strategy[ORIG_NO] = "kojiro"

    await env.engine._cancel_and_reorder(TICKER, ORIG_NO, 6, is_stop_loss=True)

    assert _fired_qty(env) == [6], "판정 불가인데 손절 잔여를 줄이거나 버렸다"
    assert len(_requery_lines(caplog, "ambiguous", level=logging.WARNING)) == 1


# ── T25 ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_t25_lookup_error_fires_remaining(env, caplog, monkeypatch):
    """🔵 T25 — 재조회 자체가 터지면 **쏜다**(`remaining`) · `error` WARNING."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    env.s["kojiro"].state.positions[TICKER] = _pos("kojiro", 1)
    env.engine._order_strategy[ORIG_NO] = "kojiro"

    def _boom():
        raise RuntimeError("registry broken")

    monkeypatch.setattr(env.reg, "all", _boom)

    await env.engine._cancel_and_reorder(TICKER, ORIG_NO, 6, is_stop_loss=True)

    assert _fired_qty(env) == [6], "판정 예외에서 손절 잔여를 버렸다"
    assert len(_requery_lines(caplog, "error", level=logging.WARNING)) == 1


# ── T26 ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_t26_holding_above_remaining_is_a_cap_not_a_raise(env):
    """🔴 T26 — 3주 manual 주문 · 1주 체결 → remaining 2, 보유 9 → 발사 **2주**(9 아님).

    보유로 올리면 운영자가 남기려던 7주까지 판다 = 분할 매도 허용 결정의 정면 위반.
    """
    env.s["kojiro"].state.positions[TICKER] = _pos("kojiro", 9)
    env.engine._order_strategy[ORIG_NO] = "kojiro"

    await env.engine._cancel_and_reorder(TICKER, ORIG_NO, 2, is_stop_loss=True)

    assert _fired_qty(env) == [2]
    assert env.engine._order_qty.get(NEW_NO) == 2


# ════════════════════════════════════════════════════════════════════════════
# 부록 R-4 (F-2) — manual 라우트 주문은 운영자 의도를 따른다 (TR22 · TR24 · TR25)
# 부록 R-5 (b) — M22b 킬러 (TR26)
#
# J-2 `gone`(보유자 0 → 발사 0)이 manual 라우트로 **추적 밖 주식**을 판 주문의 잔여 재주문까지
# 버렸다(프로브 test_p2: B7 0 / HEAD 3). manual 표식(`_manual_sell_orders`)이 붙은 주문은
# 보유자와 무관하게 `remaining` 을 쏜다(verdict=manual). 표식은 **명시**다 — `strategy_id`
# (라우트는 보유 전략이 있으면 그 id 를 쓴다)나 `"momentum"` 기본값으로 추론하지 않는다.
# ════════════════════════════════════════════════════════════════════════════
async def _partial_notice(engine, order_no: str, filled: int, ordered: int) -> None:
    await engine.handle_execution_notice(
        ticker=TICKER, order_no=order_no, side="SELL", price=35_000, quantity=filled,
        ordered_qty_payload=ordered,
    )


def _map(engine, order_no: str, qty: int, sid: str) -> None:
    engine._order_qty[order_no] = qty
    engine._order_strategy[order_no] = sid
    engine._order_ticker[order_no] = TICKER


async def _await_sell_timer(engine) -> None:
    task = engine._pending_cancel_tasks.get((TICKER, CANCEL_AXIS_SELL))
    assert task is not None, "부분 체결(map)인데 매도 잔여 타이머가 걸리지 않았다"
    await task


# ── TR22 (test_p2 이식) ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_tr22_manual_remainder_is_replaced_even_without_holder(env, caplog):
    """🔴 TR22 — 보유 전략 0. manual 5주(표식) 중 2 체결 → 30초 타이머 → 잔여 **3** 재주문 ·
    `[reorder_requery] verdict=manual` WARNING(보유 0).

    B7: `gone` → 발사 0 — 운영자가 「5주 팔아」 라고 눌렀는데 2주만 팔리고 끝난다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    eng = env.engine
    _map(eng, ORIG_NO, 5, "momentum")
    eng._manual_sell_orders[ORIG_NO] = True

    await _partial_notice(eng, ORIG_NO, 2, 5)
    await _await_sell_timer(eng)

    assert _fired_qty(env) == [3], (
        f"재주문 {_fired_qty(env)} (기대 [3]) — manual 주문의 잔여를 「보유 없음」으로 버렸다"
    )
    assert len(_requery_lines(caplog, "manual", level=logging.WARNING)) == 1


@pytest.mark.asyncio
async def test_tr22b_unmarked_remainder_without_holder_is_still_dropped(env, caplog):
    """🔵 TR22b (대조군) — 표식 없는 주문은 J-2 표 그대로: 보유 0 → `gone` → 발사 0."""
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    eng = env.engine
    _map(eng, ORIG_NO, 5, "momentum")

    await _partial_notice(eng, ORIG_NO, 2, 5)
    await _await_sell_timer(eng)

    assert _fired_qty(env) == []
    assert len(_requery_lines(caplog, "gone", level=logging.WARNING)) == 1


# ── TR24 ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_tr24_reorder_inherits_the_manual_mark(env, caplog):
    """🔴 TR24 — TR22 의 재주문(NEW_NO, 3주)이 또 1 부분 체결 → 두 번째 타이머 → 재주문 **2** ·
    두 번 다 `verdict=manual`. 재주문 번호가 표식을 물려받지 않으면(MR29) 두 번째는 `gone` → 0.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    eng = env.engine
    _map(eng, ORIG_NO, 5, "momentum")
    eng._manual_sell_orders[ORIG_NO] = True

    await _partial_notice(eng, ORIG_NO, 2, 5)
    await _await_sell_timer(eng)
    assert eng._manual_sell_orders.get(NEW_NO) is True, "재주문 번호가 manual 표식을 물려받지 않았다"

    await _partial_notice(eng, NEW_NO, 1, 3)
    await _await_sell_timer(eng)

    assert _fired_qty(env) == [3, 2], f"재주문 {_fired_qty(env)} (기대 [3, 2])"
    assert len(_requery_lines(caplog, "manual", level=logging.WARNING)) == 2


# ── TR25 ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sid, marked, expected",
    [("kojiro", True, [4]), ("momentum", False, [])],
    ids=["marked_kojiro_fires", "unmarked_momentum_gone"],
)
async def test_tr25_manual_is_the_mark_not_the_strategy_id(env, sid, marked, expected):
    """🔴 TR25 — ① 표식 있는 주문 · sid=`kojiro` · 보유 0 → 잔여 발사.
    ② 표식 없는 주문 · sid=`momentum` · 보유 0 → 발사 0(`gone`).

    manual 여부를 `strategy_id == "momentum"` 으로 추론하면(MR30) 둘 다 뒤집힌다 — 라우트는
    보유 전략이 있으면 그 id 를 적고, momentum 은 자동 손절 주문의 기본값이기도 하다.
    """
    eng = env.engine
    eng._order_strategy[ORIG_NO] = sid
    if marked:
        eng._manual_sell_orders[ORIG_NO] = True

    await eng._cancel_and_reorder(TICKER, ORIG_NO, 4, is_stop_loss=True)

    assert _fired_qty(env) == expected


# ── TR26 (M22b 킬러) ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_tr26_holder_lookup_raising_still_fires_remaining(env, caplog, monkeypatch):
    """🔴 TR26 — `_ticker_holders` 자체가 예외를 던지면 바깥 `except` 가 받는다 →
    `remaining` 반환(「재조회 자체가 실패, 손절 잔여를 버리지 않는다」 WARNING) → 발사 6.

    T25 는 `registry.all` 을 터뜨려 `_ticker_holders` 가 먼저 삼키므로(`verdict=error`) 바깥
    `except` 에 닿지 않았다 — 그 `return remaining` 을 `return 0` 으로 바꾼 돌연변이(M22b)가 살았다.
    """
    caplog.set_level(logging.DEBUG, logger=_OE_LOGGER)
    eng = env.engine
    eng._order_strategy[ORIG_NO] = "kojiro"

    def _boom(ticker):
        raise RuntimeError("holders broken")

    monkeypatch.setattr(eng, "_ticker_holders", _boom)

    assert eng._reorder_requery(TICKER, "S1", 6) == 6
    outer = [
        r.getMessage() for r in caplog.records
        if r.name == _OE_LOGGER and r.levelno >= logging.WARNING
        and r.getMessage().startswith("[reorder_requery]") and "재조회 자체가 실패" in r.getMessage()
    ]
    assert len(outer) == 1, outer

    await eng._cancel_and_reorder(TICKER, ORIG_NO, 6, is_stop_loss=True)
    assert _fired_qty(env) == [6], "보유 재조회 예외에서 손절 잔여를 버렸다"
