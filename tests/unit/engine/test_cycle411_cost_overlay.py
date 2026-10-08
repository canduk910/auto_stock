"""cycle411 Red — 실적 화면에 실비용(수수료·세금) 합치기: 순수 계산 (`src/engine/cost_overlay.py`).

명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` (사용자 결정 10-08 Q1~Q4).
Red 메모 = `_workspace/red/cycle411/cost_overlay.md`.

| # | 계약 |
|---|---|
| R1 | 추정 요율 = 정산 행 Σfee ÷ Σ(buy_amt+sll_amt) · Σtl_tax ÷ Σsll_amt, `source="measured"` |
| R2 | 정산 행이 없으면 기본값 수수료 0.142% · 세금 0.199%, `source="default"` |
| A1 | `trade_cost.allocate_rows(..., key="strategy")` 는 기존 `attribute` 와 결과가 같다(행위 보존) |
| A2 | `allocate_rows(..., key="id")` = 같은 날·종목 정산 1행을 체결 행마다 — 수수료는 체결금액 비율, 세금은 매도 행만 매도금액 비율 |
| T1 | 정산 행이 있는 체결 = `cost_status="settled"` · 한 날 한 종목 체결 행 1개면 `allocated=False` |
| T2 | 3주문·2전략이 한 날 한 종목을 나눠 가짐 = 행별 배분 합이 KIS 정산값과 1원 이내 · 전부 `allocated=True` |
| T3 | 정산 행이 없는 체결 = 추정 요율 × 체결금액(세금은 매도만), `cost_status="estimated"` |
| T4 | ETF·ETN 매도는 추정 세금 0 (정산값이 있으면 정산값을 그대로 쓴다) |
| N1 | net TWR 재누적 — 순손익 = 실현손익 − 수수료 − 세금, 분모 = 가장 가까운 이전 0 아닌 `total_asset`, 누적 = (Π(1+r/100) − 1)×100 |
| N2 | 비용 0 이면 net 일·누적 = gross 일·누적 (DB 함수 `recompute_daily_performance` 와 같은 식) |
| N3 | 날짜별 `cost_status` — 그날 체결이 전부 정산 = settled · 전부 추정 = estimated · 섞임 = mixed |
| E1 | 새 leaf 는 8영역·`scheduler.py` 를 import 하지 않는다 |

⚠️ 함수 이름·인자 모양은 이 Red 가 정한 계약이다(구현 담당과 합의 대상) — 메모 §인터페이스.
"""

from __future__ import annotations

import ast
import importlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
D1 = date(2026, 10, 6)
D2 = date(2026, 10, 7)
D3 = date(2026, 10, 8)


def _ov():
    return importlib.import_module("src.engine.cost_overlay")


def _tc():
    return importlib.import_module("src.engine.trade_cost")


def _cost(pdno, trad_dt, **over) -> dict:
    row = {
        "trad_dt": trad_dt, "pdno": pdno, "prdt_name": "",
        "buy_qty": Decimal(0), "buy_amt": Decimal(0), "sll_qty": Decimal(0),
        "sll_amt": Decimal(0), "rlzt_pfls": Decimal(0), "fee": Decimal(0),
        "tl_tax": Decimal(0), "row_count": 1, "raw": [],
    }
    row.update({k: Decimal(str(v)) for k, v in over.items()})
    return row


def _trade(tid, strategy, trade_type, price, qty, *, ticker="005930", trade_date=D1,
           ticker_name="삼성전자", profit_loss=0) -> dict:
    return {
        "id": tid, "trade_date": trade_date, "ticker": ticker, "ticker_name": ticker_name,
        "trade_type": trade_type, "strategy": strategy, "price": Decimal(str(price)),
        "quantity": qty, "profit_loss": Decimal(str(profit_loss)), "order_no": f"O{tid}",
        "order_price": None, "status": "COMPLETED",
    }


# ── R: 추정 요율 ──────────────────────────────────────────────────────────────

def test_r1_rates_when_cost_rows_exist_then_measured_ratio():
    rows = [
        _cost("005930", D1, buy_amt=700000, fee=99),
        _cost("005930", D2, sll_amt=720000, fee=102, tl_tax=1433),
    ]
    r = _ov().estimate_rates(rows)
    assert r["source"] == "measured"
    assert r["fee_rate"] == pytest.approx((99 + 102) / (700000 + 720000))
    assert r["tax_rate"] == pytest.approx(1433 / 720000)


def test_r2_rates_when_no_cost_rows_then_default_0142_and_0199_percent():
    r = _ov().estimate_rates([])
    assert r["source"] == "default"
    assert r["fee_rate"] == pytest.approx(0.00142)
    assert r["tax_rate"] == pytest.approx(0.00199)


# ── A: allocate_rows 일반화 (trade_cost.py) ──────────────────────────────────

def _split_case():
    cost = [_cost("000660", D2, buy_amt=800000, sll_amt=510000, fee=183, tl_tax=1015)]
    trades = [
        _trade(3, "volatility_breakout", "BUY", 100000, 5, ticker="000660", trade_date=D2),
        _trade(4, "kojiro", "BUY", 100000, 3, ticker="000660", trade_date=D2),
        _trade(5, "volatility_breakout", "SELL", 102000, 5, ticker="000660", trade_date=D2,
               profit_loss=10000),
    ]
    return cost, trades


def test_a1_allocate_rows_by_strategy_equals_attribute():
    cost, trades = _split_case()
    tc = _tc()
    assert tc.allocate_rows(cost, trades, key="strategy") == tc.attribute(cost, trades)


def test_a2_allocate_rows_by_id_splits_fee_by_amount_and_tax_by_sells_only():
    cost, trades = _split_case()
    rows = _tc().allocate_rows(cost, trades, key="id")
    by_id = {r["id"]: r for r in rows}
    total = 500000 + 300000 + 510000
    assert by_id[3]["fee"] == pytest.approx(183 * 500000 / total)
    assert by_id[4]["fee"] == pytest.approx(183 * 300000 / total)
    assert by_id[5]["fee"] == pytest.approx(183 * 510000 / total)
    assert by_id[3]["tl_tax"] == pytest.approx(0)
    assert by_id[4]["tl_tax"] == pytest.approx(0)
    assert by_id[5]["tl_tax"] == pytest.approx(1015)


# ── T: 체결 행 단위 비용 ────────────────────────────────────────────────────

def test_t1_single_trade_with_cost_row_is_settled_and_not_allocated():
    cost = [_cost("005930", D1, buy_amt=700000, fee=99)]
    trades = [_trade(1, "momentum", "BUY", 70000, 10)]
    out = _ov().trade_costs(cost, trades, _ov().estimate_rates(cost))
    assert out[1]["fee"] == pytest.approx(99)
    assert out[1]["tax"] == pytest.approx(0)
    assert out[1]["cost_status"] == "settled"
    assert out[1]["allocated"] is False


def test_t2_three_orders_two_strategies_sum_within_one_won_of_kis():
    cost, trades = _split_case()
    out = _ov().trade_costs(cost, trades, _ov().estimate_rates(cost))
    assert set(out) == {3, 4, 5}
    assert abs(sum(v["fee"] for v in out.values()) - 183) <= 1
    assert abs(sum(v["tax"] for v in out.values()) - 1015) <= 1
    assert all(v["allocated"] is True for v in out.values())
    assert all(v["cost_status"] == "settled" for v in out.values())
    # 전략 단위로 다시 접어도 KIS 1행과 1원 이내
    vb = out[3]["fee"] + out[5]["fee"] + out[5]["tax"]
    kj = out[4]["fee"]
    assert abs(vb + kj - (183 + 1015)) <= 1


def test_t3_unreconciled_trade_is_estimated_from_rates():
    rates = {"fee_rate": 0.0015, "tax_rate": 0.002, "source": "measured"}
    trades = [
        _trade(10, "momentum", "BUY", 50000, 4, ticker="035720", trade_date=D3, ticker_name="카카오"),
        _trade(11, "momentum", "SELL", 51000, 4, ticker="035720", trade_date=D3, ticker_name="카카오"),
    ]
    out = _ov().trade_costs([], trades, rates)
    assert out[10]["fee"] == pytest.approx(200000 * 0.0015, abs=1)
    assert out[10]["tax"] == pytest.approx(0, abs=1e-9)
    assert out[11]["fee"] == pytest.approx(204000 * 0.0015, abs=1)
    assert out[11]["tax"] == pytest.approx(204000 * 0.002, abs=1)
    assert out[10]["cost_status"] == "estimated"
    assert out[11]["cost_status"] == "estimated"


def test_t4_etf_sell_estimated_tax_is_zero_by_etf_tickers_set():
    rates = {"fee_rate": 0.0015, "tax_rate": 0.002, "source": "measured"}
    trades = [_trade(12, "etf_trend", "SELL", 30300, 10, ticker="069500", trade_date=D3,
                     ticker_name="KODEX 200")]
    out = _ov().trade_costs([], trades, rates, etf_tickers=frozenset({"069500"}))
    assert out[12]["tax"] == 0
    assert out[12]["fee"] == pytest.approx(303000 * 0.0015, abs=1)


def test_t4b_etf_sell_estimated_tax_is_zero_by_name_fallback():
    """stock_master 코드를 못 읽어도 `etf_like.is_etf_like(None, ticker_name)` 이름 규칙으로 0."""
    rates = {"fee_rate": 0.0015, "tax_rate": 0.002, "source": "measured"}
    trades = [_trade(13, "etf_trend", "SELL", 30300, 10, ticker="069500", trade_date=D3,
                     ticker_name="KODEX 200")]
    out = _ov().trade_costs([], trades, rates)
    assert out[13]["tax"] == 0


def test_t4c_settled_value_wins_over_etf_rule():
    """정산값이 들어오면 그 값이 정본이다 — ETF 라도 KIS 가 낸 세금을 0 으로 덮지 않는다."""
    cost = [_cost("069500", D3, sll_amt=303000, fee=43, tl_tax=7)]
    trades = [_trade(14, "etf_trend", "SELL", 30300, 10, ticker="069500", trade_date=D3,
                     ticker_name="KODEX 200")]
    out = _ov().trade_costs(cost, trades, _ov().estimate_rates(cost),
                            etf_tickers=frozenset({"069500"}))
    assert out[14]["tax"] == pytest.approx(7)
    assert out[14]["cost_status"] == "settled"


# ── N: net TWR 재누적 ────────────────────────────────────────────────────────

def _perf():
    return [
        {"date": date(2026, 10, 5), "total_asset": 10_000_000, "daily_realized_pnl": 0,
         "daily_profit_rate": 0.0, "cumulative_return_rate": 0.0},
        {"date": D1, "total_asset": 10_000_000, "daily_realized_pnl": 0,
         "daily_profit_rate": 0.0, "cumulative_return_rate": 0.0},
        {"date": D2, "total_asset": 10_030_000, "daily_realized_pnl": 30_000,
         "daily_profit_rate": 0.3, "cumulative_return_rate": 0.3},
        {"date": D3, "total_asset": 0, "daily_realized_pnl": 3_000,
         "daily_profit_rate": 3_000 / 10_030_000 * 100,
         "cumulative_return_rate": ((1.003) * (1 + 3_000 / 10_030_000) - 1) * 100},
    ]


def test_n1_net_twr_recomputes_from_net_pnl_and_prev_nonzero_asset():
    costs = {
        D1: {"fee": 99.0, "tax": 0.0, "cost_status": "settled"},
        D2: {"fee": 285.0, "tax": 2448.0, "cost_status": "settled"},
        D3: {"fee": 80.0, "tax": 0.0, "cost_status": "estimated"},
    }
    out = _ov().net_twr(_perf(), costs)
    by = {r["date"]: r for r in out}
    assert by[D1]["daily_fee"] == pytest.approx(99)
    assert by[D1]["daily_net_pnl"] == pytest.approx(-99)
    assert by[D1]["net_daily_profit_rate"] == pytest.approx(-99 / 10_000_000 * 100)
    net2 = 30_000 - 285 - 2448
    assert by[D2]["daily_net_pnl"] == pytest.approx(net2)
    assert by[D2]["net_daily_profit_rate"] == pytest.approx(net2 / 10_000_000 * 100)
    net3 = 3_000 - 80
    assert by[D3]["net_daily_profit_rate"] == pytest.approx(net3 / 10_030_000 * 100)
    cum = 1.0
    for r in (-99 / 10_000_000, net2 / 10_000_000, net3 / 10_030_000):
        cum *= 1 + r
    assert by[D3]["net_cumulative_return_rate"] == pytest.approx((cum - 1) * 100)
    assert by[D3]["daily_tax"] == pytest.approx(0)


def test_n2_zero_costs_reproduce_gross_series():
    perf = _perf()
    out = _ov().net_twr(perf, {})
    for src, got in zip(perf, out):
        assert got["date"] == src["date"]
        assert got["net_daily_profit_rate"] == pytest.approx(src["daily_profit_rate"])
        assert got["net_cumulative_return_rate"] == pytest.approx(src["cumulative_return_rate"])


def test_n3_day_cost_status_from_trade_statuses():
    ov = _ov()
    assert ov.day_cost_status(["settled", "settled"]) == "settled"
    assert ov.day_cost_status(["estimated"]) == "estimated"
    assert ov.day_cost_status(["settled", "estimated"]) == "mixed"


# ── E: 새 leaf 의 import 경계 ─────────────────────────────────────────────────

def test_e1_cost_overlay_imports_no_eight_areas_or_scheduler():
    leaf = _ROOT / "src" / "engine" / "cost_overlay.py"
    assert leaf.exists(), "src/engine/cost_overlay.py 가 없다"
    banned = ("src.engine.risk", "src.engine.order_engine", "src.engine.session",
              "src.engine.scanner", "src.engine.strategy_registry", "src.engine.scheduler",
              "src.api.order", "src.realtime", "src.auth")
    for node in ast.walk(ast.parse(leaf.read_text(encoding="utf-8"))):
        mods: list[str] = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        for m in mods:
            assert not m.startswith(banned), m
