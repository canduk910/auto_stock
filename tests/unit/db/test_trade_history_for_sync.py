"""사이클 30 (긴급) — trade_history 중복 INSERT 결함 (042700 사고) 대응.

배경 (사고 — 2026-05-20 042700 한미반도체):
- trade_history 19건 중 15건 중복 (실거래 4건). 매매손익 8건 잡힘 (실거래 2건).
- 동일 패턴 5/4 1건 (옛 케이스).

결함 (코드 레벨 확정):
- `_sync_orders_to_db` (scheduler.py:1996-2001) 의 중복 판정 키 소스 결함.
  ```python
  existing_buys = await get_today_buy_trades()    # ← ticker 별 dedupe 적용된 함수!
  existing_buy_keys = {(row["ticker"], row.get("order_no", "") or "") for row in existing_buys}
  ```
- `get_today_buy_trades()` (line 150-157) 가 `seen[ticker] = row` 로 ticker 별 1건만 반환.
  → 같은 ticker 의 다른 order_no 가 가려져 신규 판정 → INSERT.
- 같은 결함: `get_today_sell_trades()` (line 207-213).

무한 핑퐁 메커니즘:
1. 재기동 #N → existing_buy_keys 가 ticker 당 1건만 → 다른 order_no 신규 판정 → INSERT
2. 재기동 #N+1 → 방금 INSERT 가 최신 → 반대편 order_no 신규 판정 → INSERT
3. 매 재기동마다 BUY+SELL 2건씩 누적

DB 안전망 부재: `(ticker, order_no, trade_type)` UNIQUE 없음 (pk = id UUID).

본 사이클 (30) 변경:
- 신규 함수 `get_today_buy_trades_for_sync()` / `get_today_sell_trades_for_sync()`:
  * dedupe 없음 (raw 반환, ticker × order_no 페어 모두 보존)
  * CANCELLED 제외 (PENDING/COMPLETED/PARTIAL 만)
  * optional ticker filter
- `_sync_orders_to_db` 가 신규 함수 호출 (호출 교체)
- 기존 `get_today_buy_trades()` / `get_today_sell_trades()` 동작은 그대로 보존
  (포지션 복구용으로 의도된 dedupe — 매수 시점 매핑 잔존)
- 기존 `get_today_buy_trades_for_funnel()` 은 CANCELLED 포함이라 재활용 불가.

회귀 가드 (S1~S6):
- S-1: `get_today_buy_trades_for_sync()` 가 같은 ticker 다른 order_no 모두 반환 (042700 사고 재현)
- S-2: CANCELLED 매수 제외
- S-3: ticker filter optional (전체 또는 단일 ticker)
- S-4: `get_today_sell_trades_for_sync()` 동일 동작
- S-5: 기존 `get_today_buy_trades()` 의 ticker dedupe 동작 보존 (포지션 복구용)
- S-6: 기존 `get_today_sell_trades()` 의 ticker dedupe 동작 보존
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Supabase mock helper — _query() 가 호출되면 인메모리 rows 반환
# ---------------------------------------------------------------------------
def _patch_supabase_with_rows(monkeypatch, rows: list[dict]):
    """`src.db.trade_history.supabase.table(...).select(...).execute()` 가 rows 반환하도록 mock.

    체인 메서드 호출 (eq/gte/in_/order/execute) 후 마지막 execute 가 .data 노출.
    """
    from src.db import trade_history as th

    # 체인의 마지막 execute() 응답
    response = SimpleNamespace(data=rows)

    # 모든 체인 메서드가 self 반환하는 fluent mock
    fluent = MagicMock()
    fluent.select.return_value = fluent
    fluent.eq.return_value = fluent
    fluent.gte.return_value = fluent
    fluent.in_.return_value = fluent
    fluent.order.return_value = fluent
    fluent.execute.return_value = response

    supabase_mock = MagicMock()
    supabase_mock.table.return_value = fluent
    monkeypatch.setattr(th, "supabase", supabase_mock)
    return fluent, supabase_mock


# ===========================================================================
# S-1: `get_today_buy_trades_for_sync` 가 같은 ticker 다른 order_no 모두 반환
# ===========================================================================
@pytest.mark.asyncio
async def test_for_sync_buys_preserves_distinct_order_no_for_same_ticker(monkeypatch):
    """042700 사고 재현: 같은 ticker (042700) 의 4종 order_no 모두 반환."""
    rows = [
        {"ticker": "042700", "order_no": "0000462500", "trade_type": "BUY",
         "status": "COMPLETED", "timestamp": "2026-05-20T02:14:16+09:00"},
        {"ticker": "042700", "order_no": "0000573412", "trade_type": "BUY",
         "status": "COMPLETED", "timestamp": "2026-05-20T03:21:16+09:00"},
        {"ticker": "042700", "order_no": "0000684523", "trade_type": "BUY",
         "status": "COMPLETED", "timestamp": "2026-05-20T13:21:16+09:00"},
        {"ticker": "042700", "order_no": "0000795634", "trade_type": "BUY",
         "status": "PARTIAL", "timestamp": "2026-05-20T14:05:00+09:00"},
    ]
    _patch_supabase_with_rows(monkeypatch, rows)

    from src.db.trade_history import get_today_buy_trades_for_sync
    result = await get_today_buy_trades_for_sync()

    assert len(result) == 4, (
        f"같은 ticker 다른 order_no 4건 모두 반환되어야 함 (dedupe 금지). "
        f"실제 {len(result)}건. 042700 무한 핑퐁 재발."
    )
    order_nos = {r["order_no"] for r in result}
    assert order_nos == {"0000462500", "0000573412", "0000684523", "0000795634"}


# ===========================================================================
# S-2: CANCELLED 매수 제외
# ===========================================================================
@pytest.mark.asyncio
async def test_for_sync_buys_excludes_cancelled(monkeypatch):
    """`status` filter 가 ['PENDING', 'COMPLETED', 'PARTIAL'] — CANCELLED 제외.

    Note: 실제 status 필터링은 supabase `.in_()` 가 처리 — 본 테스트는 호출 인자 검증.
    """
    rows: list[dict] = []
    fluent, _ = _patch_supabase_with_rows(monkeypatch, rows)

    from src.db.trade_history import get_today_buy_trades_for_sync
    await get_today_buy_trades_for_sync()

    # .in_("status", [...]) 호출 인자 검증
    in_calls = fluent.in_.call_args_list
    assert len(in_calls) >= 1, "status filter (in_) 호출 누락"
    found_status_filter = False
    for call in in_calls:
        args, _kw = call
        if args[0] == "status":
            statuses = set(args[1])
            assert "CANCELLED" not in statuses, (
                f"CANCELLED 가 status filter 에 포함됨 (제외되어야 함). 실제={statuses}"
            )
            assert statuses == {"PENDING", "COMPLETED", "PARTIAL"}, (
                f"CANCELLED 제외 + PENDING/COMPLETED/PARTIAL 포함 필요. 실제={statuses}"
            )
            found_status_filter = True
    assert found_status_filter, "status filter 누락"


# ===========================================================================
# S-3: ticker filter optional
# ===========================================================================
@pytest.mark.asyncio
async def test_for_sync_buys_applies_ticker_filter_when_provided(monkeypatch):
    """`ticker` 인자 명시 시 `.eq("ticker", ticker)` 추가."""
    rows: list[dict] = []
    fluent, _ = _patch_supabase_with_rows(monkeypatch, rows)

    from src.db.trade_history import get_today_buy_trades_for_sync
    await get_today_buy_trades_for_sync(ticker="042700")

    # .eq("ticker", "042700") 호출 검증
    eq_calls = fluent.eq.call_args_list
    found_ticker_filter = any(
        call.args == ("ticker", "042700") for call in eq_calls
    )
    assert found_ticker_filter, (
        f"ticker filter (.eq(ticker, 042700)) 누락. 호출={eq_calls}"
    )


@pytest.mark.asyncio
async def test_for_sync_buys_no_ticker_filter_when_none(monkeypatch):
    """`ticker=None` (기본) 시 ticker filter 없음."""
    rows: list[dict] = []
    fluent, _ = _patch_supabase_with_rows(monkeypatch, rows)

    from src.db.trade_history import get_today_buy_trades_for_sync
    await get_today_buy_trades_for_sync()  # 기본 None

    eq_calls = fluent.eq.call_args_list
    ticker_filter_present = any(
        call.args[0] == "ticker" for call in eq_calls
    )
    assert not ticker_filter_present, (
        f"ticker=None 인데 ticker filter 적용됨. 호출={eq_calls}"
    )


# ===========================================================================
# S-4: `get_today_sell_trades_for_sync` 동일 동작
# ===========================================================================
@pytest.mark.asyncio
async def test_for_sync_sells_preserves_distinct_order_no_for_same_ticker(monkeypatch):
    """매도도 같은 ticker 다른 order_no 모두 반환."""
    rows = [
        {"ticker": "042700", "order_no": "9999990001", "trade_type": "SELL",
         "status": "COMPLETED", "timestamp": "2026-05-20T11:00:00+09:00"},
        {"ticker": "042700", "order_no": "9999990002", "trade_type": "SELL",
         "status": "COMPLETED", "timestamp": "2026-05-20T13:00:00+09:00"},
        {"ticker": "042700", "order_no": "9999990003", "trade_type": "SELL",
         "status": "PARTIAL", "timestamp": "2026-05-20T14:00:00+09:00"},
    ]
    _patch_supabase_with_rows(monkeypatch, rows)

    from src.db.trade_history import get_today_sell_trades_for_sync
    result = await get_today_sell_trades_for_sync()

    assert len(result) == 3
    assert {r["order_no"] for r in result} == {"9999990001", "9999990002", "9999990003"}


@pytest.mark.asyncio
async def test_for_sync_sells_excludes_cancelled(monkeypatch):
    """매도도 CANCELLED 제외."""
    rows: list[dict] = []
    fluent, _ = _patch_supabase_with_rows(monkeypatch, rows)

    from src.db.trade_history import get_today_sell_trades_for_sync
    await get_today_sell_trades_for_sync()

    in_calls = fluent.in_.call_args_list
    found = False
    for call in in_calls:
        if call.args[0] == "status":
            statuses = set(call.args[1])
            assert "CANCELLED" not in statuses
            assert statuses == {"PENDING", "COMPLETED", "PARTIAL"}, (
                f"매도 sync 도 PENDING/COMPLETED/PARTIAL. 실제={statuses}"
            )
            found = True
    assert found


# ===========================================================================
# S-5: 기존 `get_today_buy_trades()` 의 ticker dedupe 동작 보존 (포지션 복구용)
# ===========================================================================
@pytest.mark.asyncio
async def test_existing_get_today_buy_trades_keeps_ticker_dedupe(monkeypatch):
    """회귀 가드: 기존 `get_today_buy_trades()` 는 포지션 복구용 — ticker 별 1건 dedupe 유지.

    `_sync_orders_to_db` 결함 수정 후에도 본 함수 동작은 변경 금지.
    포지션 복구는 같은 ticker 의 최신 row 1건만 필요.
    """
    rows = [
        {"ticker": "042700", "order_no": "0000573412", "trade_type": "BUY",
         "status": "COMPLETED", "timestamp": "2026-05-20T03:21:16+09:00"},
        {"ticker": "042700", "order_no": "0000462500", "trade_type": "BUY",
         "status": "COMPLETED", "timestamp": "2026-05-20T02:14:16+09:00"},
    ]
    _patch_supabase_with_rows(monkeypatch, rows)

    from src.db.trade_history import get_today_buy_trades
    result = await get_today_buy_trades()

    # 같은 ticker 1건만 dedupe
    assert len(result) == 1, (
        f"기존 get_today_buy_trades() ticker dedupe 회귀. 실제={len(result)}건"
    )


# ===========================================================================
# S-6: 기존 `get_today_sell_trades()` 의 ticker dedupe 동작 보존
# ===========================================================================
@pytest.mark.asyncio
async def test_existing_get_today_sell_trades_keeps_ticker_dedupe(monkeypatch):
    """회귀 가드: 기존 `get_today_sell_trades()` 도 ticker 별 dedupe 유지."""
    rows = [
        {"ticker": "042700", "order_no": "9999990002", "trade_type": "SELL",
         "status": "COMPLETED", "timestamp": "2026-05-20T13:00:00+09:00"},
        {"ticker": "042700", "order_no": "9999990001", "trade_type": "SELL",
         "status": "COMPLETED", "timestamp": "2026-05-20T11:00:00+09:00"},
    ]
    _patch_supabase_with_rows(monkeypatch, rows)

    from src.db.trade_history import get_today_sell_trades
    result = await get_today_sell_trades()
    assert len(result) == 1
