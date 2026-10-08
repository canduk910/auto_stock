"""cycle411 보완 Red — 순수 계산 leaf 결함 고정 (메인 세션 결정 10-08 「보완 결정」).

계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「보완 결정」 절.

| # | 계약 |
|---|---|
| H2b | 정산 행의 매도 체결금액 합(`sell_tot`)이 0 인데 `tl_tax > 0` 이면 세금을 매수 행에 **몰지 않는다** — 그 세금은 미배분 + `[cost_overlay_tax_unallocated] ` WARNING |
| H2c | 위 처리는 `cost_overlay.trade_costs` 가 한다 — `trade_cost.attribute`/`allocate_rows(key="strategy")` 결과는 그대로(트랙 C 요약 행위 보존) |
| M3 | `trade_costs(..., etf_flags={ticker: bool})` — 판정이 있는 종목은 그 값만 본다(이름 키워드 폴백보다 우선). 없는 종목은 기존대로 `etf_tickers` → 이름 폴백 |
| M5 | `compute_te_rr` 가 세전 승/패 수 `win_gross`·`loss_gross` 를 함께 싣는다(세전 화면의 승률·승/패 표시용) |
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.engine import cost_overlay, trade_cost
from src.engine.te_metrics import compute_te_rr

pytestmark = pytest.mark.unit

D2 = date(2026, 10, 7)
KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 8, 20, 0, tzinfo=KST)
RATES = {"fee_rate": 0.00142, "tax_rate": 0.00199, "source": "default"}


def _cost(pdno, trad_dt, **over) -> dict:
    row = {
        "trad_dt": trad_dt, "pdno": pdno, "prdt_name": "",
        "buy_qty": Decimal(0), "buy_amt": Decimal(0), "sll_qty": Decimal(0),
        "sll_amt": Decimal(0), "rlzt_pfls": Decimal(0), "fee": Decimal(0),
        "tl_tax": Decimal(0), "row_count": 1, "raw": [],
    }
    row.update({k: Decimal(str(v)) for k, v in over.items()})
    return row


def _t(tid, strategy, tt, price, qty, *, ticker="000660", name="SK하이닉스") -> dict:
    return {
        "id": tid, "trade_date": D2, "ticker": ticker, "ticker_name": name, "trade_type": tt,
        "strategy": strategy, "price": Decimal(str(price)), "quantity": qty,
        "profit_loss": Decimal(0), "order_price": None, "status": "COMPLETED",
    }


# ── H2b·H2c: 매도 없는 날의 정산 세금 ──────────────────────────────────────────

_BUY_ONLY = [_t(1, "volatility_breakout", "BUY", 100_000, 5), _t(2, "kojiro", "BUY", 100_000, 3)]
_TAX_NO_SELL = [_cost("000660", D2, buy_amt=800_000, fee=114, tl_tax=50)]


def test_h2b_tax_without_sell_is_not_dumped_on_buy_rows(caplog):
    with caplog.at_level(logging.DEBUG):
        costs = cost_overlay.trade_costs(_TAX_NO_SELL, _BUY_ONLY, RATES)
    assert costs[1]["tax"] == pytest.approx(0) and costs[2]["tax"] == pytest.approx(0), costs
    # 수수료는 그대로 체결금액 비율로 나뉜다(총합 보존)
    assert costs[1]["fee"] + costs[2]["fee"] == pytest.approx(114)
    assert costs[1]["fee"] == pytest.approx(114 * 5 / 8)
    warns = [r for r in caplog.records
             if r.levelno >= logging.WARNING
             and r.getMessage().startswith("[cost_overlay_tax_unallocated] ")]
    assert len(warns) == 1, [r.getMessage() for r in caplog.records]


def test_h2b2_tax_with_sell_still_goes_to_sell_rows(caplog):
    trades = _BUY_ONLY + [_t(3, "volatility_breakout", "SELL", 102_000, 5)]
    rows = [_cost("000660", D2, buy_amt=800_000, sll_amt=510_000, fee=183, tl_tax=1015)]
    with caplog.at_level(logging.DEBUG):
        costs = cost_overlay.trade_costs(rows, trades, RATES)
    assert costs[3]["tax"] == pytest.approx(1015)
    assert costs[1]["tax"] == pytest.approx(0) and costs[2]["tax"] == pytest.approx(0)
    assert not [r for r in caplog.records
                if r.getMessage().startswith("[cost_overlay_tax_unallocated] ")]


def test_h2c_attribute_behavior_preserved_for_tax_without_sell():
    """트랙 C 전략 귀속(`attribute`)은 이번 보완으로 바뀌지 않는다 — 기존 규칙(매도 없으면 전체 비율)."""
    rows = trade_cost.attribute(_TAX_NO_SELL, _BUY_ONLY)
    by = {r["strategy"]: r for r in rows}
    assert by["volatility_breakout"]["tl_tax"] == pytest.approx(50 * 5 / 8)
    assert by["kojiro"]["tl_tax"] == pytest.approx(50 * 3 / 8)


# ── M3: stock_master 구분 코드 판정 우선 ───────────────────────────────────────

def test_m3_etf_flags_override_name_keyword_fallback():
    trades = [
        _t(61, "momentum", "SELL", 10_000, 10, ticker="138930", name="BNK금융지주"),
        _t(62, "etf_trend", "SELL", 10_000, 10, ticker="999999", name="KIWOOM 200"),
        _t(63, "etf_trend", "SELL", 10_000, 10, ticker="069500", name="KODEX 200"),  # 판정 없음 → 이름 폴백
    ]
    costs = cost_overlay.trade_costs([], trades, RATES,
                                     etf_flags={"138930": False, "999999": True})
    assert costs[61]["tax"] == pytest.approx(100_000 * 0.00199)
    assert costs[62]["tax"] == pytest.approx(0)
    assert costs[63]["tax"] == pytest.approx(0)


# ── M5: 세전 승/패 수 ─────────────────────────────────────────────────────────

def _pair(i, rate, pl, net_rate, net_pl):
    return {
        "status": "closed", "sell_date": "2026-10-01", "profit_rate": rate, "profit_loss": pl,
        "strategy": "momentum", "pair_key": f"momentum:005930:O{i}",
        "net_profit_rate": net_rate, "net_profit_loss": net_pl, "fee": 1960, "tax": 1400,
    }


def test_m5_te_metrics_carry_gross_win_loss_counts():
    # 세전 +0.1% 승 15건 · 세전 −1% 패 5건 — 세후로는 20건 전부 패
    pairs = ([_pair(i, 0.1, 700, -0.38, -2660) for i in range(15)]
             + [_pair(100 + i, -1.0, -7000, -1.48, -10360) for i in range(5)])
    d = asdict(compute_te_rr(pairs, now=NOW, strategy_id="momentum"))
    assert d["win"] == 0 and d["loss"] == 20  # 판정 = 세후(기존)
    assert d["win_gross"] == 15
    assert d["loss_gross"] == 5
    assert d["win_rate_gross"] == pytest.approx(0.75)


def test_m5b_empty_metrics_carry_gross_counts():
    d = asdict(compute_te_rr([], now=NOW, strategy_id="momentum"))
    assert d["win_gross"] == 0 and d["loss_gross"] == 0
