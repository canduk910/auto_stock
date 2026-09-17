"""history 라우트 계약 — /api/history, /api/history/pnl"""

from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.contract


def _make_trade(i, *, ticker="005930", strategy="momentum"):
    """`price`/`profit_loss` 는 **Decimal** 이다 — 프로덕션을 재현한다.

    `trade_history.price`·`profit_loss` 는 PG NUMERIC 이고 `src/db/pg.py` 에 numeric
    코덱이 없어 asyncpg 가 `Decimal` 을 준다. 종전 스텁은 python int 를 먹여 라우트가
    Decimal 을 한 번도 태우지 않았고, 그래서 pydantic v2 가 Decimal 을 JSON **문자열**로
    내보내 거래내역 화면의 '가격'·'매매손익' 열이 전 행 `-` 로 보이던 결함
    (2026-07-16 RDS 이전 이후)을 이 계약 테스트가 한 번도 잡지 못했다.
    """
    return {
        "id": i, "ticker": ticker, "ticker_name": "삼성전자",
        "trade_type": "BUY", "price": Decimal(f"{70000 + i}.00"), "quantity": 1,
        "profit_loss": Decimal("0"), "status": "COMPLETED", "strategy": strategy,
        "order_no": f"O-{i}", "timestamp": "2026-05-08T15:00:00+09:00",
    }


def test_history_numeric_fields_are_json_numbers(contract_env):
    """NUMERIC 컬럼은 JSON **숫자**로 나간다 — 프론트 계약 `TradeRecord.price: number`.

    문자열로 새면 `TradeHistoryGrid` 가 그 열을 `-` 로 떨군다. 라우트의 Decimal 사영을
    되돌리면 이 단언이 붉어진다.
    """
    contract_env.state.trades = [
        _make_trade(0) | {"profit_loss": Decimal("-4600.00")},
    ]
    r = contract_env.client.get("/api/history")
    assert r.status_code == 200
    row = r.json()["data"]["trades"][0]

    assert isinstance(row["price"], (int, float)) and not isinstance(row["price"], bool), (
        f"price 가 {type(row['price']).__name__} 다 — Decimal 사영이 빠졌다: {row['price']!r}"
    )
    assert isinstance(row["profit_loss"], (int, float)), (
        f"profit_loss 가 {type(row['profit_loss']).__name__} 다: {row['profit_loss']!r}"
    )
    assert row["price"] == 70000.0
    assert row["profit_loss"] == -4600.0
    # 비수치 컬럼은 사영 대상이 아니다 — 문자열 그대로 유지.
    assert row["ticker"] == "005930"
    assert row["quantity"] == 1


def test_history_default_pagination(contract_env):
    contract_env.state.trades = [_make_trade(i) for i in range(5)]
    r = contract_env.client.get("/api/history")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["page"] == 1
    assert data["size"] == 20
    assert data["total"] == 5
    assert data["total_pages"] == 1
    assert len(data["trades"]) == 5


def test_history_with_pagination_params(contract_env):
    contract_env.state.trades = [_make_trade(i) for i in range(50)]
    r = contract_env.client.get("/api/history?page=2&size=10")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["page"] == 2
    assert data["size"] == 10
    assert data["total"] == 50
    assert data["total_pages"] == 5
    assert len(data["trades"]) == 10
    # offset = 10 → trades[10:20]
    assert contract_env.calls.get_trades[-1]["offset"] == 10


def test_history_invalid_page_returns_422(contract_env):
    r = contract_env.client.get("/api/history?page=0")
    assert r.status_code == 422  # ge=1 위반


def test_history_size_max_100_validated(contract_env):
    r = contract_env.client.get("/api/history?size=500")
    assert r.status_code == 422  # le=100 위반


def test_history_strategy_filter_passes_through(contract_env):
    r = contract_env.client.get("/api/history?strategy=momentum&ticker=005930")
    assert r.status_code == 200
    last = contract_env.calls.get_trades[-1]
    assert last["strategy"] == "momentum"
    assert last["ticker"] == "005930"


def test_history_pnl_default_pagination(contract_env):
    contract_env.state.trade_pairs = [
        {"ticker": "005930", "ticker_name": "", "buy_price": 70000, "sell_price": 75000,
         "quantity": 10, "profit_loss": 50000, "profit_rate": 7.14, "strategy": "momentum"},
    ]
    r = contract_env.client.get("/api/history/pnl")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["page"] == 1
    assert data["size"] == 50
    assert data["total"] == 1
    assert len(data["pairs"]) == 1
    # ticker_name fallback (DB 빈값 + scanner 매핑)
    assert data["pairs"][0]["ticker_name"] == "삼성전자"


def test_history_pnl_pagination_slices_results(contract_env):
    contract_env.state.trade_pairs = [
        {"ticker": f"00{i:04d}", "buy_price": 1, "sell_price": 1, "quantity": 1,
         "profit_loss": 0, "strategy": "momentum"}
        for i in range(150)
    ]
    r = contract_env.client.get("/api/history/pnl?page=2&size=50")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 150
    assert data["total_pages"] == 3
    assert len(data["pairs"]) == 50
