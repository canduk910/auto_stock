"""balance + performance 라우트 계약 — /api/balance/*, /api/performance/*"""

from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.contract


def test_balance_returns_holdings_and_summary(contract_env):
    r = contract_env.client.get("/api/balance")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert "holdings" in data
    assert "summary" in data
    assert isinstance(data["holdings"], list)
    # AccountSummary pydantic dump 확인
    assert "deposit" in data["summary"]
    assert "net_asset" in data["summary"]
    assert "total_eval_amount" in data["summary"]


def test_balance_holdings_include_stock_master_fields(contract_env, monkeypatch):
    """J1: /api/balance Holding 응답에 stock_master 의 NXT/KRX 거래가능 필드가 join 되어야 한다.

    - 보유 종목별 `stock_master.get(ticker)` 조회 결과를 합쳐
      `nxt_tradable / krx_halted / excg_dvsn_cd` 3필드를 노출.
    - 미캐시(None) 종목은 None 그대로 유지 (UI 가 "확인중" 표시).
    - 캐시 조회 예외는 종목별 흡수 — 나머지 종목 계속.
    """
    from src.models.balance import AccountSummary, StockHolding
    from src.models.stock import StockBasics

    async def fake_get_balance():
        contract_env.calls.get_balance.append({})
        summary = AccountSummary(
            deposit=10_000_000,
            stock_eval_amount=2_160_000,
            total_eval_amount=12_160_000,
            net_asset=12_160_000,
            purchase_total=2_000_000,
            eval_total=2_160_000,
            profit_loss_total=160_000,
        )
        holdings = [
            StockHolding(
                ticker="005930", name="삼성전자", quantity=10,
                sellable_quantity=10, avg_price=70_000.0, purchase_amount=700_000,
                current_price=72_000, eval_amount=720_000,
                eval_profit_loss=20_000, eval_profit_rate=2.86,
            ),
            StockHolding(
                ticker="012200", name="계양전기", quantity=5,
                sellable_quantity=5, avg_price=8_000.0, purchase_amount=40_000,
                current_price=8_500, eval_amount=42_500,
                eval_profit_loss=2_500, eval_profit_rate=6.25,
            ),
            StockHolding(
                ticker="900110", name="확인안된종목", quantity=1,
                sellable_quantity=1, avg_price=1_000.0, purchase_amount=1_000,
                current_price=1_100, eval_amount=1_100,
                eval_profit_loss=100, eval_profit_rate=10.0,
            ),
            StockHolding(
                ticker="999999", name="조회실패종목", quantity=1,
                sellable_quantity=1, avg_price=1_000.0, purchase_amount=1_000,
                current_price=1_100, eval_amount=1_100,
                eval_profit_loss=100, eval_profit_rate=10.0,
            ),
        ]
        return holdings, summary

    async def fake_stock_master_get(ticker):
        if ticker == "005930":
            return StockBasics(
                ticker="005930", name="삼성전자", excg_dvsn_cd="02",
                nxt_tradable=True, krx_halted=False, admin_item=False,
            )
        if ticker == "012200":
            return StockBasics(
                ticker="012200", name="계양전기", excg_dvsn_cd="02",
                nxt_tradable=False, krx_halted=False, admin_item=False,
            )
        if ticker == "900110":
            return None  # 캐시 miss
        if ticker == "999999":
            raise RuntimeError("supabase down")
        return None

    monkeypatch.setattr("src.routes.balance.get_balance", fake_get_balance)
    monkeypatch.setattr("src.routes.balance.stock_master_get", fake_stock_master_get, raising=False)

    r = contract_env.client.get("/api/balance")
    assert r.status_code == 200
    holdings = r.json()["data"]["holdings"]
    by_ticker = {h["ticker"]: h for h in holdings}

    # 캐시 hit + NXT 가능
    assert by_ticker["005930"]["nxt_tradable"] is True
    assert by_ticker["005930"]["krx_halted"] is False
    assert by_ticker["005930"]["excg_dvsn_cd"] == "02"

    # 캐시 hit + NXT 불가
    assert by_ticker["012200"]["nxt_tradable"] is False
    assert by_ticker["012200"]["krx_halted"] is False
    assert by_ticker["012200"]["excg_dvsn_cd"] == "02"

    # 캐시 miss → None 유지
    assert by_ticker["900110"]["nxt_tradable"] is None
    assert by_ticker["900110"]["krx_halted"] is None
    assert by_ticker["900110"]["excg_dvsn_cd"] is None

    # 조회 예외 흡수 → None 으로 fallback, 응답 정상 (다른 종목 영향 없음)
    assert by_ticker["999999"]["nxt_tradable"] is None
    assert by_ticker["999999"]["krx_halted"] is None
    assert by_ticker["999999"]["excg_dvsn_cd"] is None


def test_balance_buyable_with_query_params(contract_env):
    r = contract_env.client.get("/api/balance/buyable?ticker=005930&price=70000")
    assert r.status_code == 200
    data = r.json()["data"]
    # BuyableInfo 필드 확인
    assert "max_buy_quantity" in data
    assert "cash_available" in data
    # fake fixture 가 호출 인자를 받았는지
    assert contract_env.calls.get_buyable[-1] == {"ticker": "005930", "price": 70000}


def test_performance_summary_when_no_records_returns_zero_envelope(contract_env):
    r = contract_env.client.get("/api/performance/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["total_days"] == 0
    assert data["latest_asset"] == 0


def test_performance_summary_with_records_aggregates(contract_env):
    contract_env.state.performance = [
        {"date": "2026-05-01", "daily_profit_rate": 0.5, "cumulative_return_rate": 1.0,
         "total_asset": 10_500_000},
        {"date": "2026-05-02", "daily_profit_rate": 1.0, "cumulative_return_rate": 2.0,
         "total_asset": 10_600_000},
    ]
    r = contract_env.client.get("/api/performance/summary")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total_days"] == 2
    # avg = (0.5 + 1.0) / 2
    assert data["avg_daily_profit_rate"] == pytest.approx(0.75)
    # cumulative 는 latest 의 cumulative_return_rate
    assert data["total_profit_rate"] == 2.0
    assert data["latest_asset"] == 10_600_000


def test_performance_summary_latest_asset_is_json_number(contract_env):
    """`latest_asset` 은 JSON **숫자**로 나간다 — 프론트 계약 `latest_asset: number`.

    `daily_performance.total_asset` 은 NUMERIC 이라 asyncpg 가 `Decimal` 을 주고, 라우트가
    `float()` 를 빠뜨리면 pydantic v2 가 문자열로 직렬화한다. 그러면 `PerformanceCard` 의
    `toLocaleString('ko-KR')` 이 `Object.prototype` 쪽으로 떨어져 **예외 없이** 천단위
    구분만 사라진다(`10720000.00원`). 같은 dict 의 다른 두 수치는 이미 float 라 한 카드
    줄에서 한 칸만 어긋나 눈에 잘 띄지 않는다 — 그래서 단언으로 고정한다.
    """
    contract_env.state.performance = [
        {"date": "2026-05-01", "daily_profit_rate": Decimal("0.5"),
         "cumulative_return_rate": Decimal("1.0"), "total_asset": Decimal("10720000.00")},
    ]
    r = contract_env.client.get("/api/performance/summary")
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data["latest_asset"], (int, float)) and not isinstance(
        data["latest_asset"], bool
    ), f"latest_asset 가 {type(data['latest_asset']).__name__} 다: {data['latest_asset']!r}"
    assert data["latest_asset"] == 10_720_000.0


def test_performance_summary_strategy_filter_passes_through(contract_env):
    r = contract_env.client.get("/api/performance/summary?strategy=momentum")
    assert r.status_code == 200
    # fake_get_performance 호출 시 strategy='momentum' 으로 전달돼야 함
    assert contract_env.calls.get_performance[-1]["strategy"] == "momentum"


def test_performance_daily_returns_records_array(contract_env):
    contract_env.state.performance = [
        {"date": "2026-05-08", "daily_profit_rate": 0.5, "total_asset": 10_500_000}
    ]
    r = contract_env.client.get("/api/performance/daily?days=7")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    # query param 전달 확인
    assert contract_env.calls.get_performance[-1]["days"] == 7


def test_performance_recompute_returns_success(contract_env):
    r = contract_env.client.post("/api/performance/recompute")
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert len(contract_env.calls.recompute) == 1
