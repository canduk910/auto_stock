"""L5 Red — `TradingScheduler._sync_orders_to_db` (ticker, order_no) 페어 중복 체크.

배경:
- 2026-05-12 005930(삼성전자) 보완 INSERT 결함 추적 결과:
  현재 `existing_buy_tickers = {row["ticker"]}` 만 보고 중복 판정 →
  동일 ticker 가 같은 영업일에 2번 매수될 수 있는 경우 위양성(잘못된 skip).
- 또한 매수 timezone 결함과 결합해 09시 이전 매수 기록이 누락된 상태에서
  같은 ticker 새 주문이 들어오면 중복으로 잘못 INSERT 되는 결함이 발생.

요구 행위:
F. 같은 ticker 다른 order_no 의 주문 2건은 둘 다 INSERT 된다.
G. 같은 ticker + 같은 order_no 는 1건만 INSERT (멱등).
H. 매도(`sll_buy_dvsn_cd="01"`) 도 동일 `(ticker, order_no)` 페어로 판정.

테스트 더블:
- `TradingScheduler.__init__` 의 무거운 의존성을 우회하려고 `__new__` + 필요한 속성만 주입.
- `get_today_buy_trades / get_today_sell_trades / insert_trade` 를 monkeypatch.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.unit


def _make_scheduler():
    """무거운 __init__ 우회 — `_sync_orders_to_db` 만 호출하는 데 필요한 최소 상태."""
    from src.engine.scheduler import TradingScheduler

    # `__new__` 로 객체만 만들고 사용하지 않는 속성은 비워둔다.
    scheduler = TradingScheduler.__new__(TradingScheduler)

    # `_sync_orders_to_db` 내부에서 self.registry.all() 순회 → 매도 손익 계산.
    # 빈 registry 면 strategy 매핑은 db_strategy_map fallback 사용.
    class _Reg:
        def all(self):
            return []

    scheduler.registry = _Reg()
    return scheduler


@pytest.fixture
def patched_db(monkeypatch: pytest.MonkeyPatch):
    """get_today_*_trades / insert_trade 를 인메모리로 패치하고 inserted 리스트 노출."""
    from src.db import trade_history as th
    from src.engine import scheduler as sch_mod

    inserted: list[dict[str, Any]] = []
    existing_buys: list[dict[str, Any]] = []
    existing_sells: list[dict[str, Any]] = []

    async def _fake_get_buys(strategy=None):
        return list(existing_buys)

    async def _fake_get_sells(strategy=None):
        return list(existing_sells)

    async def _fake_insert(record):
        # TradeRecord pydantic → dict 로 평탄화
        inserted.append({
            "ticker": record.ticker,
            "trade_type": record.trade_type.value,
            "price": float(record.price),
            "quantity": record.quantity,
            "strategy": record.strategy,
            "order_no": record.order_no,
        })

    # `_sync_orders_to_db` 내부에서 from src.db.trade_history import ... 를 사용하므로
    # 두 위치 모두 패치한다 (함수 본문 import + 모듈 글로벌).
    monkeypatch.setattr(th, "get_today_buy_trades", _fake_get_buys)
    monkeypatch.setattr(th, "get_today_sell_trades", _fake_get_sells)
    monkeypatch.setattr(th, "insert_trade", _fake_insert)

    # 사이클 30 (긴급, 2026-05-21) — 신규 `_for_sync` 함수 mock (042700 핑퐁 사고 대응).
    # `_sync_orders_to_db` 가 본 함수로 교체되어 호출하므로 미패치 시 실제 supabase 호출 → ConnectError.
    async def _fake_get_buys_for_sync(ticker=None):
        return list(existing_buys)

    async def _fake_get_sells_for_sync(ticker=None):
        return list(existing_sells)

    monkeypatch.setattr(th, "get_today_buy_trades_for_sync", _fake_get_buys_for_sync, raising=False)
    monkeypatch.setattr(th, "get_today_sell_trades_for_sync", _fake_get_sells_for_sync, raising=False)

    # ticker_names 도 import 됨 → 빈 dict 으로 충분
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_names", {}, raising=False)

    from types import SimpleNamespace
    return SimpleNamespace(
        inserted=inserted,
        existing_buys=existing_buys,
        existing_sells=existing_sells,
    )


@pytest.mark.asyncio
async def test_sync_orders_to_db_inserts_distinct_order_no_for_same_ticker(patched_db):
    """F. 같은 ticker 다른 order_no 주문 2건은 둘 다 INSERT 된다."""
    scheduler = _make_scheduler()

    # 같은 ticker(005930) 다른 order_no — 둘 다 신규 (existing 없음)
    orders = [
        {
            "pdno": "005930",
            "tot_ccld_qty": "10",
            "sll_buy_dvsn_cd": "02",
            "avg_prvs": "70000",
            "odno": "0000001111",
            "prdt_name": "삼성전자",
        },
        {
            "pdno": "005930",
            "tot_ccld_qty": "5",
            "sll_buy_dvsn_cd": "02",
            "avg_prvs": "70500",
            "odno": "0000002222",
            "prdt_name": "삼성전자",
        },
    ]

    await scheduler._sync_orders_to_db(orders)

    inserted = patched_db.inserted
    assert len(inserted) == 2, f"같은 ticker 다른 order_no 2건이 모두 INSERT 되어야 함. 실제: {inserted}"
    assert {r["order_no"] for r in inserted} == {"0000001111", "0000002222"}


@pytest.mark.asyncio
async def test_sync_orders_to_db_idempotent_for_same_ticker_and_order_no(patched_db):
    """G. 같은 ticker + 같은 order_no 는 1건만 INSERT (멱등)."""
    scheduler = _make_scheduler()

    # 이미 DB 에 005930 / 0000001111 매수가 있는 상태
    patched_db.existing_buys.append({
        "ticker": "005930",
        "order_no": "0000001111",
        "strategy": "momentum",
        "trade_type": "BUY",
    })

    orders = [
        {
            "pdno": "005930",
            "tot_ccld_qty": "10",
            "sll_buy_dvsn_cd": "02",
            "avg_prvs": "70000",
            "odno": "0000001111",  # 동일 order_no — skip
            "prdt_name": "삼성전자",
        },
        {
            "pdno": "005930",
            "tot_ccld_qty": "5",
            "sll_buy_dvsn_cd": "02",
            "avg_prvs": "70500",
            "odno": "0000002222",  # 신규 order_no — INSERT
            "prdt_name": "삼성전자",
        },
    ]

    await scheduler._sync_orders_to_db(orders)

    inserted = patched_db.inserted
    # 기존 0000001111 은 skip, 신규 0000002222 만 INSERT
    assert len(inserted) == 1
    assert inserted[0]["order_no"] == "0000002222"


@pytest.mark.asyncio
async def test_sync_orders_to_db_sells_also_use_ticker_orderno_pair(patched_db):
    """H. 매도 경로도 (ticker, order_no) 페어 사용."""
    scheduler = _make_scheduler()

    # 이미 DB 에 005930 / 9999990001 매도 1건 있음
    patched_db.existing_sells.append({
        "ticker": "005930",
        "order_no": "9999990001",
        "strategy": "momentum",
        "trade_type": "SELL",
    })

    orders = [
        {
            "pdno": "005930",
            "tot_ccld_qty": "10",
            "sll_buy_dvsn_cd": "01",  # 매도
            "avg_prvs": "71000",
            "odno": "9999990001",  # 동일 order_no — skip
            "prdt_name": "삼성전자",
        },
        {
            "pdno": "005930",
            "tot_ccld_qty": "5",
            "sll_buy_dvsn_cd": "01",  # 매도
            "avg_prvs": "71500",
            "odno": "9999990002",  # 신규 — INSERT
            "prdt_name": "삼성전자",
        },
    ]

    await scheduler._sync_orders_to_db(orders)

    inserted = patched_db.inserted
    assert len(inserted) == 1
    assert inserted[0]["order_no"] == "9999990002"
    assert inserted[0]["trade_type"] == "SELL"
