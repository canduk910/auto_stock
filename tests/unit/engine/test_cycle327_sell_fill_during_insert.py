"""cycle327 — 매도 PENDING INSERT 도중 체결통보가 착지하면 **이미 팔린 것을 다시 판다**.

## 결함 (2026-09-20 발견 · 5개월간 미검출)

cycle271 이 매수 쪽에 세운 race 흡수기(`_insert_pending_buy_or_absorb_race`, `:831`)가
**매도에는 없다.** 매수는 `:1192`·`:1306` 두 자리에서 그 헬퍼를 쓰는데,
매도는 `:1557`·`:1896` 에서 **맨 `await insert_trade(record)`** 다.

## 실패 사슬 (전부 `order_engine.py` 안에서 닫힌다)

```
_handle_sell_fill:2486  UPDATE affected == 0
        :2494           _completed_orders.add(order_no)
        :2497           COMPLETED 직접 INSERT          ← 같은 (ticker, order_no, 'SELL')
execute_sell:1557       insert_trade → UniqueViolationError   (migration 029 부분 UNIQUE)
        :1565           except KisApiError  ← UniqueViolationError 는 여기 안 걸린다
        :1983           except Exception    ← 여기 잡힌다 → "매도 주문 실패" WARNING
        :1990           sleep
        :1516           재시도 루프 재진입
        :1521           place_order(quantity=pos.quantity)   ← 🔴 **다시 판다**
```

🔴 `pos` 는 `:1377` 에서 잡은 **지역 참조**다. `_handle_sell_fill:2471` 이
`state.positions` 에서 지운 뒤에도 **옛 수량을 그대로 들고 있다.**

## 왜 안 보였나

- `insert_trade`(`src/db/trade_history.py`)는 `try/except` 가 없어 예외를 그대로 올린다.
- 매수 쪽에는 회귀 테스트가 둘 있는데(`test_cycle271_*` · `test_cycle273a_*`)
  **매도 쪽 INSERT-중 race 테스트는 0건**이었다(`grep -rn UniqueViolation tests/` 실측).
- 정본(`src/engine/CLAUDE.md`)은 "체결통보 선행 race 가드 매수·매도 양쪽"이라 적는데,
  양쪽에 있는 것은 **발사 직후 선행 체크**(`:1538`/`:1877`)뿐이고
  **INSERT 도중 착지 흡수**는 매수 전용이다. 문서와 코드가 어긋나 있었다.

## 🔴 이 파일은 행위 보존 테스트가 아니다

고치면 행위가 **바뀐다**(지금 = 재시도 / 뒤 = 흡수 + return).
그래서 `execute_sell` 리팩토링 커밋과 **섞지 않는다** — 별도 승인 대상이다.
이 파일은 우선 **결함이 실재함을 증명**한다.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.engine.strategy_base import Signal

pytestmark = pytest.mark.unit

TICKER = "005930"
PRICE = 70_000
QTY = 10


def _make_sell_env(monkeypatch):
    """매도 경로 격리 환경 — `insert_trade` 의 `await` 창에 체결통보를 끼워 넣는다."""
    import asyncpg

    from src.models.order import OrderResult
    from src.engine import scanner
    from src.engine.order_engine import OrderEngine
    from src.engine.session import MarketBoard, session_tracker
    from src.engine.strategies.momentum import MomentumStrategy
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    monkeypatch.setattr(scanner, "ticker_names", {TICKER: "테스트종목"}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prev_close", {TICKER: PRICE}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prices", {TICKER: PRICE}, raising=False)
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.MAIN}))

    registry = StrategyRegistry()
    strat = MomentumStrategy(
        StrategyConfig(strategy_id="momentum", name="모멘텀", weight=1.0,
                       params={"exchange": "KRX"})
    )
    registry.register(strat)
    registry.allocate_funds(total_asset=100_000_000)
    engine = OrderEngine(registry)

    calls = SimpleNamespace(place_order=[], inserted=[], logs=[])
    fired = {"done": False}

    async def fake_place_order(ticker, side, quantity, price=0, **kwargs):
        calls.place_order.append({"side": side, "quantity": quantity})
        n = len(calls.place_order)
        return OrderResult(order_no=f"SELL-{n:06d}", order_time="090501",
                           krx_org_no="00950")

    async def fake_insert_trade(record):
        # 🔴 이 `await` 가 체결통보가 끼어들 수 있는 유일한 창이다.
        if not fired["done"] and getattr(record, "trade_type", "") == "SELL":
            fired["done"] = True
            # 상대편(_handle_sell_fill)이 먼저 완주한 상태를 만든다 —
            # `_completed_orders` 에 올리고 COMPLETED 행을 선점한다.
            engine._completed_orders.add(record.order_no)
            calls.inserted.append(("COMPLETED-by-fill", record.order_no))
            raise asyncpg.exceptions.UniqueViolationError(
                "duplicate key value violates unique constraint "
                '"uq_trade_history_ticker_order_no_type"'
            )
        calls.inserted.append(("PENDING", getattr(record, "order_no", "?")))

    async def noop(*a, **k):
        return None

    async def fake_update_status(*a, **k):
        return 1

    monkeypatch.setattr("src.engine.order_engine.place_order", fake_place_order)
    monkeypatch.setattr("src.engine.order_engine.insert_trade", fake_insert_trade)
    monkeypatch.setattr("src.engine.order_engine.update_trade_status", fake_update_status)
    monkeypatch.setattr("src.engine.order_engine.write_log", noop)
    monkeypatch.setattr("src.engine.order_engine.SELL_RETRY_DELAY", 0, raising=False)

    import src.db.positions as positions_mod
    monkeypatch.setattr(positions_mod, "delete_position", noop, raising=False)
    monkeypatch.setattr(positions_mod, "save_position", noop, raising=False)

    return SimpleNamespace(engine=engine, registry=registry, strategy=strat, calls=calls)


def _seed_position(strat):
    from src.engine.strategy_base import Position

    from datetime import date

    pos = Position(ticker=TICKER, buy_price=PRICE, quantity=QTY,
                   order_no="BUY-000001", strategy_id="momentum",
                   buy_date=date(2026, 9, 19))
    strat.state.positions[TICKER] = pos
    return pos


@pytest.mark.asyncio
async def test_sell_does_not_refire_when_fill_lands_during_insert(monkeypatch):
    """🔴 INSERT 도중 체결이 착지해도 **매도 주문을 다시 내지 않는다**.

    이것이 이 사이클의 계약이다. 지금은 깨져 있다 —
    `UniqueViolationError` 가 `except Exception` 에 잡혀 재시도 루프를 돌고,
    `pos.quantity` 를 **그대로 다시 발사**한다(포지션은 이미 삭제됐는데도).

    막는 회귀 = 매수에만 있는 흡수기를 매도에 안 두는 것.
    """
    env = _make_sell_env(monkeypatch)
    _seed_position(env.strategy)

    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "momentum")

    sells = [c for c in env.calls.place_order if str(c["side"]).endswith("SELL")]
    assert len(sells) == 1, (
        f"매도 주문이 {len(sells)}회 나갔다 — INSERT 도중 체결이 착지했는데 재발사했다.\n"
        f"  발사 내역: {env.calls.place_order}\n"
        "  → 매수의 `_insert_pending_buy_or_absorb_race` 와 같은 흡수기가 매도에 없다."
    )


@pytest.mark.asyncio
async def test_sell_absorbs_only_with_evidence(monkeypatch):
    """증거 없는 `UniqueViolationError` 는 **삼키지 않는다**.

    매수 헬퍼의 계약과 같다 — `_completed_orders` 에 그 주문번호가 있을 때만 흡수한다.
    무조건 삼키면 다른 원인(진짜 중복 INSERT)이 은폐된다.
    """
    import asyncpg

    env = _make_sell_env(monkeypatch)
    _seed_position(env.strategy)

    async def always_violate(record):
        # 증거(_completed_orders 등재) 없이 위반만 일으킨다.
        raise asyncpg.exceptions.UniqueViolationError("no evidence")

    monkeypatch.setattr("src.engine.order_engine.insert_trade", always_violate)

    # 흡수하지 않으므로 조용히 성공해서는 안 된다 — 재시도든 예외든 「그냥 지나감」이 아니어야 한다.
    await env.engine.execute_sell(TICKER, Signal.STOP_LOSS, "momentum")
    sells = [c for c in env.calls.place_order if str(c["side"]).endswith("SELL")]
    assert len(sells) >= 1, "증거 없는 위반인데 주문 자체가 안 나갔다 — 전제가 깨졌다"
