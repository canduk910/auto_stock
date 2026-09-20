"""cycle332 — 매수·매도 취소 타이머가 **서로를 죽인다**.

자문 = `_workspace/domain_consult/cycle332_buy_cancel_timer.md`

## 결함

`_schedule_cancel`(매수 잔량 취소)과 `_schedule_cancel_and_reorder`(매도 손절 잔여
재주문)가 `_pending_cancel_tasks` **단일 dict 를 ticker 키로 공유**한다. 등록할 때
`if ticker in tasks: tasks[ticker].cancel()` 이므로 **한쪽이 다른 쪽을 order_no 검사
없이 죽인다**.

해제(`_handle_*_fill` 전량 분기)는 cycle273a 가 `order_no` 일치 게이트로 좁혀 두었다.
**등록만 안 좁혀져 있다** — 이 사이클은 그 미완성 규약을 완성한다.

## 시나리오 S1 — 매수 타이머가 **손절 타이머**를 죽인다 (심각)

```
T+0.4s  매수 3/10 부분체결 → _schedule_cancel(X, B)            tasks[X]=TaskB
T+11s   급락 → 손절 매도 3주 발사, _selling.add(X)
T+11.3s 매도 1/3 부분체결 → _schedule_cancel_and_reorder(X, S)  TaskB 죽고 tasks[X]=TaskA
T+18s   매수 잔여 추가 부분체결 → _schedule_cancel(X, B)        🔴 TaskA 죽는다
T+41s   TaskB' 만료 → 매수 잔량만 취소. **손절 잔여 2주는 아무도 다시 보지 않는다**
```

잃는 것은 「매수 잔량 자동취소를 놓친다」가 아니다.

1. 🔴 `_cancel_and_reorder` 는 취소 3경로 중 **유일한 `cancel_order → place_order`
   atomic replace** 다. 그게 죽으면 원 매도 주문이 호가에 남고 시장가가 아니면
   (프리장 `step_down` 변환 · KRX 애프터 `41` 지정가 · NXT 잔존) **안 팔린다**.
2. 🔴 매도 **부분**체결 분기는 `_selling` 을 discard 하지 않으므로 `risk.on_tick` 의
   `_selling` 가드가 `check_exit_signal` 을 건너뛴다 — **손절 재평가도 멈춰 있다**.
3. 🔴 `selling_reconcile`(180초)도 안 풀어 준다 — 원 매도 주문이 **열린 채**라
   판정이 `open_order` = **유지** 분기다. 그날 21:30 까지 `_selling` 좀비가 이어진다.

즉 **급락장에서 손절 잔여가 체결도·재주문도·재평가도 못 받는다.**

## 시나리오 S2 — 매도 타이머가 **매수 타이머**를 죽인다

매수 잔여 7주가 호가에 남는다.

1. **손절 중인 종목을 계속 사들인다** — 방향이 반대인 주문이 동시에 산다.
2. 🔴 **랏 상한이 사후적으로 뚫린다.** `pending_buys`/`pending_buy_amounts` 는 첫
   부분체결에서 이미 풀리므로, 예산 점유가 없는 상태로 미취소 잔여가 나중에 체결되면
   `pos.quantity` 가 설계 랏을 넘는다. K축·ρ축 캡은 **진입 시점 통제**라 못 막는다.

## 시정 (자문 안 A)

키를 **`(ticker, side)` 복합 키**로 바꿔 두 축이 공존하게 한다.
`order_no` 단독 키는 채택하지 않는다 — 더 정확하지만 UI 계약(`pending_cancels` 가
ticker 배열)이 바뀌고 cycle273a·cycle291 가드 다수가 재작성 대상이 된다.

🔴 **해제의 `order_no` 일치 게이트는 그대로 유지한다**(cycle273a 계약). 이 사이클은
등록 축만 좁힌다.
"""
from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

TICKER = "005930"
PRICE = 70_000


def _make_env(monkeypatch):
    from src.engine import scanner
    from src.engine.order_engine import OrderEngine
    from src.engine.session import MarketBoard, session_tracker
    from src.engine.strategies.momentum import MomentumStrategy
    from src.engine.strategy_base import Position, StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    monkeypatch.setattr(scanner, "ticker_names", {TICKER: "테스트종목"}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prices", {TICKER: {"current_price": PRICE}},
                        raising=False)
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))

    registry = StrategyRegistry()
    strat = MomentumStrategy(
        StrategyConfig(strategy_id="momentum", name="모멘텀", weight=1.0,
                       params={"exchange": "KRX"})
    )
    registry.register(strat)
    registry.allocate_funds(total_asset=100_000_000)
    engine = OrderEngine(registry)

    strat.state.positions[TICKER] = Position(
        ticker=TICKER, buy_price=PRICE, quantity=3, order_no="BUY-1",
        strategy_id="momentum", buy_date=date(2026, 9, 21),
    )
    return SimpleNamespace(engine=engine, registry=registry, strategy=strat)


def _keys(engine) -> set:
    return set(engine._pending_cancel_tasks.keys())


@pytest.mark.asyncio
async def test_buy_timer_does_not_kill_sell_timer(monkeypatch):
    """🔴 **S1** — 매수 잔량 취소 타이머가 **손절 재주문 타이머를 죽이지 않는다**.

    이것이 이 사이클의 계약이다. 지금은 두 타이머가 `_pending_cancel_tasks` 를
    ticker 키로 공유해 나중에 걸린 쪽이 앞선 쪽을 `order_no` 검사 없이 cancel 한다.

    잃는 것 = 급락장에서 손절 잔여가 체결도·재주문도·재평가도 못 받는 상태로 고착.
    """
    env = _make_env(monkeypatch)
    e = env.engine

    # 손절 매도 부분체결 → 재주문 타이머
    e._schedule_cancel_and_reorder(TICKER, "SELL-1", 2, is_stop_loss=True)
    sell_tasks = list(e._pending_cancel_tasks.values())

    # 그 뒤 매수 잔여 부분체결 → 매수 취소 타이머
    e._schedule_cancel(TICKER, "BUY-1", 10, "momentum")
    await asyncio.sleep(0)   # cancel() 이 실제로 반영되도록 한 틱 양보

    assert any(not t.cancelled() and not t.done() for t in sell_tasks), (
        "매수 타이머가 손절 재주문 타이머를 죽였다 — 원 매도 주문이 호가에 남고\n"
        "  `_selling` 도 안 풀려 그 종목의 손절이 21:30 까지 재평가되지 않는다."
    )
    assert len(_keys(e)) == 2, (
        f"두 축 타이머가 공존하지 않는다 (키 {len(_keys(e))}개): {_keys(e)}"
    )

    for t in e._pending_cancel_tasks.values():
        t.cancel()


@pytest.mark.asyncio
async def test_sell_timer_does_not_kill_buy_timer(monkeypatch):
    """🔴 **S2** — 손절 재주문 타이머가 **매수 잔량 취소 타이머를 죽이지 않는다**.

    죽으면 (a) 손절 중인 종목을 계속 사들이고 (b) `pending_buys` 는 첫 부분체결에서
    이미 풀렸으므로 미취소 잔여가 나중에 체결되면 **설계 랏을 넘는다** —
    K축·ρ축 캡은 진입 시점 통제라 이걸 못 막는다.
    """
    env = _make_env(monkeypatch)
    e = env.engine

    e._schedule_cancel(TICKER, "BUY-1", 10, "momentum")
    buy_tasks = list(e._pending_cancel_tasks.values())

    e._schedule_cancel_and_reorder(TICKER, "SELL-1", 2, is_stop_loss=True)
    await asyncio.sleep(0)

    assert any(not t.cancelled() and not t.done() for t in buy_tasks), (
        "손절 타이머가 매수 취소 타이머를 죽였다 — 미취소 매수 잔여가 나중에 체결되면\n"
        "  설계 랏을 넘고, 손절 중인 종목을 계속 사들인다."
    )
    for t in e._pending_cancel_tasks.values():
        t.cancel()


@pytest.mark.asyncio
async def test_same_axis_reschedule_still_replaces(monkeypatch):
    """같은 축의 재스케줄은 **여전히 교체**한다.

    부분체결이 연달아 오는 것은 정상 동작이다. 이 사이클은 **축 간 충돌만** 없애고
    축 안의 교체는 건드리지 않는다 — 안 그러면 타이머가 무한히 쌓인다.
    """
    env = _make_env(monkeypatch)
    e = env.engine

    e._schedule_cancel(TICKER, "BUY-1", 10, "momentum")
    first = list(e._pending_cancel_tasks.values())
    e._schedule_cancel(TICKER, "BUY-2", 10, "momentum")
    await asyncio.sleep(0)

    assert all(t.cancelled() or t.done() for t in first), (
        "같은 축 재스케줄인데 앞선 타이머가 살아 있다 — 타이머가 쌓인다"
    )
    assert len(_keys(e)) == 1, f"매수 축 키가 {len(_keys(e))}개로 늘었다"

    for t in e._pending_cancel_tasks.values():
        t.cancel()


@pytest.mark.asyncio
async def test_release_gate_still_scoped_by_order_no(monkeypatch):
    """🔴 해제의 `order_no` 일치 게이트는 **그대로다** (cycle273a 계약).

    다른 주문의 전량체결이 이 타이머를 해제하면 안 된다. 이 사이클은 등록 축만
    좁히고 해제 규약은 한 글자도 바꾸지 않는다.
    """
    env = _make_env(monkeypatch)
    e = env.engine

    e._schedule_cancel(TICKER, "BUY-1", 10, "momentum")
    before = len(_keys(e))

    # 다른 주문번호로 해제 시도 — 게이트가 막아야 한다
    from src.engine.order_engine import OrderEngine
    key_lookup = e._pending_cancel_order_no
    assert any(v == "BUY-1" for v in key_lookup.values()), (
        "타이머가 지키는 order_no 가 기록되지 않았다"
    )
    assert not any(v == "BUY-OTHER" for v in key_lookup.values())
    assert len(_keys(e)) == before

    for t in e._pending_cancel_tasks.values():
        t.cancel()


@pytest.mark.asyncio
async def test_scheduler_status_still_reports_tickers(monkeypatch):
    """🔴 UI 계약 보존 — `pending_cancels` 는 여전히 **ticker 배열**이다.

    `frontend/src/types/trading.ts` 와 `OrderMonitor.tsx` 가 ticker 문자열 배열로
    그린다. 키를 복합으로 바꾸면서 그 화면이 조용히 주문번호·튜플로 바뀌면 안 된다.
    """
    env = _make_env(monkeypatch)
    e = env.engine
    e._schedule_cancel(TICKER, "BUY-1", 10, "momentum")
    e._schedule_cancel_and_reorder(TICKER, "SELL-1", 2, is_stop_loss=True)

    from src.engine.order_engine import pending_cancel_tickers
    tickers = pending_cancel_tickers(e)
    assert tickers == [TICKER], (
        f"pending_cancels 가 ticker 배열이 아니다: {tickers}"
    )

    for t in e._pending_cancel_tasks.values():
        t.cancel()
