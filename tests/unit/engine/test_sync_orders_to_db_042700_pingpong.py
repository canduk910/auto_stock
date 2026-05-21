"""사이클 30 (긴급) — 042700 한미반도체 무한 핑퐁 사고 재현 + 회복 검증.

배경:
- 2026-05-20 042700 trade_history 19건 중 15건 중복 (실거래 4건).
- 매매손익 8건 잡힘 (실거래 2건) — daily_performance 왜곡.

핑퐁 메커니즘:
1. 같은 ticker (042700) 의 4종 order_no 가 진짜로 존재 (실거래 4건).
2. 재기동 #N: `existing_buys = get_today_buy_trades()` → ticker dedupe 결과 1건만 반환.
3. existing_buy_keys = {("042700", "0000462500")} (예: 가장 최신만).
4. KIS orders 7건 중 다른 3개 order_no (`0000573412`, `0000684523`, `0000795634`) 가
   key 미존재 → 신규 판정 → INSERT 3건.
5. 재기동 #N+1: DB 최신 1건이 바뀌어 다른 페어 신규 판정 → INSERT N건.
6. 7회 재기동 = 누적 14건 중복.

본 테스트:
- T-1: prod-mock 으로 무한 핑퐁 재현 (사이클 30 적용 *전* 동작 — 신규 함수 미사용 시 핑퐁)
- T-2: 사이클 30 적용 후 — 재기동 7회 반복해도 INSERT 0건 (042700 4 종 order_no 보유)
- T-3: BUY+SELL 혼합 — 같은 ticker 다른 order_no 양쪽 모두 dedupe
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


def _make_scheduler():
    """무거운 __init__ 우회."""
    from src.engine.scheduler import TradingScheduler
    scheduler = TradingScheduler.__new__(TradingScheduler)

    class _Reg:
        def all(self):
            return []
    scheduler.registry = _Reg()
    return scheduler


@pytest.fixture
def prod_db_mocks(monkeypatch: pytest.MonkeyPatch):
    """실제 prod 동작과 동일한 dedupe 가 적용된 mock — 핑퐁 재현/회복 양쪽 검증.

    Key: `_fake_get_buys_with_dedupe` 가 운영 `get_today_buy_trades()` 와 동일하게
    ticker 별 1건만 반환 → 사이클 30 결함 (dedupe 함수가 sync 용으로 부적합) 재현.
    `_fake_get_buys_for_sync` 는 신규 함수 — dedupe 없이 raw 반환.
    """
    from src.db import trade_history as th
    from src.engine import scanner

    inserted: list[dict[str, Any]] = []
    db_rows_buys: list[dict[str, Any]] = []
    db_rows_sells: list[dict[str, Any]] = []

    async def _fake_get_buys(strategy=None):
        # 운영 동작 동일 — ticker 별 dedupe (최신만)
        seen: dict[str, dict] = {}
        for row in db_rows_buys:
            if row["ticker"] not in seen:
                seen[row["ticker"]] = row
        return list(seen.values())

    async def _fake_get_sells(strategy=None):
        seen: dict[str, dict] = {}
        for row in db_rows_sells:
            if row["ticker"] not in seen:
                seen[row["ticker"]] = row
        return list(seen.values())

    async def _fake_get_buys_for_sync(ticker=None):
        # 신규 함수 — dedupe 없음 + CANCELLED 제외 + ticker filter
        result = [r for r in db_rows_buys if r.get("status") != "CANCELLED"]
        if ticker:
            result = [r for r in result if r["ticker"] == ticker]
        return result

    async def _fake_get_sells_for_sync(ticker=None):
        result = [r for r in db_rows_sells if r.get("status") != "CANCELLED"]
        if ticker:
            result = [r for r in result if r["ticker"] == ticker]
        return result

    async def _fake_insert(record):
        inserted.append({
            "ticker": record.ticker,
            "trade_type": record.trade_type.value,
            "price": float(record.price),
            "quantity": record.quantity,
            "strategy": record.strategy,
            "order_no": record.order_no,
            "status": record.status.value,
        })
        # INSERT 직후 DB 에도 반영 (다음 sync 가 본 row 를 봐야 함)
        target = db_rows_buys if record.trade_type.value == "BUY" else db_rows_sells
        target.append({
            "ticker": record.ticker,
            "order_no": record.order_no,
            "trade_type": record.trade_type.value,
            "status": record.status.value,
            "strategy": record.strategy,
            "timestamp": "2026-05-20T15:00:00+09:00",  # 최신
        })

    monkeypatch.setattr(th, "get_today_buy_trades", _fake_get_buys)
    monkeypatch.setattr(th, "get_today_sell_trades", _fake_get_sells)
    # 신규 함수도 패치 — 사이클 30 구현 후 호출됨
    monkeypatch.setattr(th, "get_today_buy_trades_for_sync", _fake_get_buys_for_sync, raising=False)
    monkeypatch.setattr(th, "get_today_sell_trades_for_sync", _fake_get_sells_for_sync, raising=False)
    monkeypatch.setattr(th, "insert_trade", _fake_insert)
    monkeypatch.setattr(scanner, "ticker_names", {}, raising=False)

    from types import SimpleNamespace
    return SimpleNamespace(
        inserted=inserted,
        db_rows_buys=db_rows_buys,
        db_rows_sells=db_rows_sells,
    )


def _kis_orders_042700_4buys() -> list[dict]:
    """042700 실거래 4 종 매수 — KIS get_daily_orders 응답 형식."""
    return [
        {"pdno": "042700", "tot_ccld_qty": "100", "sll_buy_dvsn_cd": "02",
         "avg_prvs": "120000", "odno": "0000462500", "prdt_name": "한미반도체"},
        {"pdno": "042700", "tot_ccld_qty": "50", "sll_buy_dvsn_cd": "02",
         "avg_prvs": "121000", "odno": "0000573412", "prdt_name": "한미반도체"},
        {"pdno": "042700", "tot_ccld_qty": "80", "sll_buy_dvsn_cd": "02",
         "avg_prvs": "122000", "odno": "0000684523", "prdt_name": "한미반도체"},
        {"pdno": "042700", "tot_ccld_qty": "40", "sll_buy_dvsn_cd": "02",
         "avg_prvs": "123000", "odno": "0000795634", "prdt_name": "한미반도체"},
    ]


# ===========================================================================
# T-1: 042700 무한 핑퐁 재현 (사이클 30 적용 후 발생 안 함 검증)
# ===========================================================================
@pytest.mark.asyncio
async def test_042700_4_order_no_first_sync_inserts_all_4(prod_db_mocks):
    """첫 sync (DB 비어있음) — 4 종 order_no 모두 INSERT (정상)."""
    scheduler = _make_scheduler()

    await scheduler._sync_orders_to_db(_kis_orders_042700_4buys())

    inserted = prod_db_mocks.inserted
    assert len(inserted) == 4, f"첫 sync 4건 모두 INSERT 필요. 실제={len(inserted)}"
    assert {r["order_no"] for r in inserted} == {
        "0000462500", "0000573412", "0000684523", "0000795634"
    }


@pytest.mark.asyncio
async def test_042700_4_order_no_subsequent_sync_idempotent(prod_db_mocks):
    """**핵심 회귀 가드**: DB 에 4건 이미 있는 상태에서 재기동 sync 1회 → INSERT 0건.

    사이클 30 결함:
    - `get_today_buy_trades()` 가 ticker dedupe → 1건만 반환 → existing_buy_keys 1개 → 3건 INSERT (핑퐁).
    사이클 30 수정:
    - `get_today_buy_trades_for_sync()` 가 4건 모두 반환 → 4개 key → INSERT 0건.
    """
    scheduler = _make_scheduler()

    # DB 에 이미 4 종 BUY 존재
    prod_db_mocks.db_rows_buys.extend([
        {"ticker": "042700", "order_no": "0000462500", "trade_type": "BUY",
         "status": "COMPLETED", "timestamp": "2026-05-20T02:14:16+09:00"},
        {"ticker": "042700", "order_no": "0000573412", "trade_type": "BUY",
         "status": "COMPLETED", "timestamp": "2026-05-20T03:21:16+09:00"},
        {"ticker": "042700", "order_no": "0000684523", "trade_type": "BUY",
         "status": "COMPLETED", "timestamp": "2026-05-20T13:21:16+09:00"},
        {"ticker": "042700", "order_no": "0000795634", "trade_type": "BUY",
         "status": "PARTIAL", "timestamp": "2026-05-20T14:05:00+09:00"},
    ])

    await scheduler._sync_orders_to_db(_kis_orders_042700_4buys())

    inserted = prod_db_mocks.inserted
    assert len(inserted) == 0, (
        f"DB 에 4건 이미 있는데 sync 재실행 → INSERT 0건이어야 함. 실제={len(inserted)}. "
        f"사이클 30 결함 재발 — `_sync_orders_to_db` 가 신규 `_for_sync` 함수 미사용."
    )


@pytest.mark.asyncio
async def test_042700_4_order_no_7_restarts_no_pingpong(prod_db_mocks):
    """**핵심 회귀 가드 (운영 시나리오)**: 7회 재기동 가정, 042700 4 종 보유 → 누적 INSERT 0건.

    사이클 30 결함 가정 시: 매 재기동 3건씩 누적 → 7회 = 21건 추가.
    사이클 30 수정 후: 매 재기동 0건 → 7회 = 0건.
    """
    scheduler = _make_scheduler()

    # 초기 DB 상태 (실거래 4건)
    prod_db_mocks.db_rows_buys.extend([
        {"ticker": "042700", "order_no": f"0000{i+100:06d}", "trade_type": "BUY",
         "status": "COMPLETED", "timestamp": f"2026-05-20T{i+2:02d}:00:00+09:00"}
        for i in range(4)
    ])
    initial_count = len(prod_db_mocks.db_rows_buys)

    # KIS orders 도 동일 4건
    orders = [
        {"pdno": "042700", "tot_ccld_qty": "100", "sll_buy_dvsn_cd": "02",
         "avg_prvs": f"12{i}000", "odno": f"0000{i+100:06d}", "prdt_name": "한미반도체"}
        for i in range(4)
    ]

    # 7회 재기동 sync
    for restart in range(7):
        await scheduler._sync_orders_to_db(orders)

    # 누적 INSERT 0건 + DB 행 갯수 변화 없음
    assert len(prod_db_mocks.inserted) == 0, (
        f"7회 재기동 후 누적 INSERT 0건이어야 함. 실제={len(prod_db_mocks.inserted)}건. "
        f"042700 핑퐁 사고 재발."
    )
    assert len(prod_db_mocks.db_rows_buys) == initial_count, (
        f"DB 행 갯수 변화 없어야 함. 실제={len(prod_db_mocks.db_rows_buys)}건"
    )


# ===========================================================================
# T-3: BUY + SELL 혼합 (같은 ticker 다른 order_no)
# ===========================================================================
@pytest.mark.asyncio
async def test_042700_buy_sell_mixed_idempotent(prod_db_mocks):
    """매수 4 + 매도 3 모두 DB 에 있는 상태 → sync 재실행 INSERT 0건."""
    scheduler = _make_scheduler()

    # DB 매수 4
    prod_db_mocks.db_rows_buys.extend([
        {"ticker": "042700", "order_no": f"BUY{i:04d}", "trade_type": "BUY",
         "status": "COMPLETED", "timestamp": f"2026-05-20T{i+2:02d}:00:00+09:00"}
        for i in range(4)
    ])
    # DB 매도 3
    prod_db_mocks.db_rows_sells.extend([
        {"ticker": "042700", "order_no": f"SELL{i:04d}", "trade_type": "SELL",
         "status": "COMPLETED", "timestamp": f"2026-05-20T{i+10:02d}:00:00+09:00"}
        for i in range(3)
    ])

    orders = [
        # 매수 4
        *[
            {"pdno": "042700", "tot_ccld_qty": "50", "sll_buy_dvsn_cd": "02",
             "avg_prvs": "120000", "odno": f"BUY{i:04d}", "prdt_name": "한미반도체"}
            for i in range(4)
        ],
        # 매도 3
        *[
            {"pdno": "042700", "tot_ccld_qty": "30", "sll_buy_dvsn_cd": "01",
             "avg_prvs": "125000", "odno": f"SELL{i:04d}", "prdt_name": "한미반도체"}
            for i in range(3)
        ],
    ]

    await scheduler._sync_orders_to_db(orders)

    assert len(prod_db_mocks.inserted) == 0, (
        f"BUY 4 + SELL 3 모두 DB 에 있는 상태 — sync 재실행 INSERT 0건. "
        f"실제={len(prod_db_mocks.inserted)}건."
    )
