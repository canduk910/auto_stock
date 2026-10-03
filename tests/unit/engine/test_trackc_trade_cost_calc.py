"""트랙 C(실비용 산출) — KIS 정산 행 집계 · 전략 귀속 · 요약 · 경보 판정 (`src/engine/trade_cost.py`).

명세 = `_workspace/design/2026-10-01_mean_reversion_handoff.md` §4.2-1·2·4·5 · cycle392 §5.3 메모

| # | 계약 |
|---|---|
| A1 | KIS 행은 `(trad_dt, pdno 뒤 6자리)` 로 접혀 숫자 칸이 합산되고 원문은 `raw` 목록에 남는다 |
| A2 | 빈 칸·쉼표·소수 문자열을 `Decimal` 로 읽는다 · 날짜/종목이 빈 행은 버린다 |
| R1 | 한 전략만 거래한 날·종목 = 그 전략에 100% 귀속, `estimated=False` |
| R2 | 두 전략이 같은 날·종목을 거래 = 수수료는 체결금액(매수+매도) 비율, 세금은 매도 체결금액 비율, `estimated=True` |
| R3 | 매도가 없는 날·종목의 세금은 전체 체결금액 비율로 나눈다(합계 보존) |
| R4 | `trade_history` 에 짝이 없는 KIS 행 = `unattributed` |
| R5 | 귀속 뒤 전략 합계 = KIS 원 행 합계(수수료·세금 보존) |
| S1 | 요약 = 전략별 gross(=`trade_history` SELL `profit_loss` 합) · 수수료 · 세금 · net = gross − 수수료 − 세금 |
| S2 | 실효 왕복비용 bp = (수수료+세금) ÷ ((매수금액+매도금액)/2) × 10⁴ · 분모 0 이면 None |
| S3 | 슬리피지 = 주문가(`llm_buy_evaluations.order_price_won`) 대비 체결가(`trade_history.price`), BUY 만, 덮인 건수 `slippage_n` |
| S4 | `strategy=` 필터는 그 전략 행만 남기고 total 도 그 행으로 계산한다 |
| L1 | 경보 기준이 None(설정 없음) = 경보 0 — 기준값을 코드에 두지 않는다 |
| L2 | 기준 초과 전략만 경보 · `unattributed` 는 경보 대상이 아니다 |
"""

from __future__ import annotations

import importlib
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

D = date(2026, 9, 30)


def _mod():
    return importlib.import_module("src.engine.trade_cost")


def _kis(trad_dt="20260930", pdno="035760", **over) -> dict:
    row = {
        "trad_dt": trad_dt, "pdno": pdno, "prdt_name": "CJ ENM", "trad_dvsn_name": "현금",
        "buy_qty": "0", "buy_amt": "0", "sll_qty": "0", "sll_amt": "0",
        "rlzt_pfls": "0", "fee": "0", "tl_tax": "0",
    }
    row.update(over)
    return row


def _cost(pdno="035760", trad_dt=D, **over) -> dict:
    row = {
        "trad_dt": trad_dt, "pdno": pdno, "prdt_name": "",
        "buy_qty": Decimal(0), "buy_amt": Decimal(0), "sll_qty": Decimal(0),
        "sll_amt": Decimal(0), "rlzt_pfls": Decimal(0), "fee": Decimal(0),
        "tl_tax": Decimal(0), "row_count": 1, "raw": [],
    }
    row.update({k: (Decimal(str(v)) if isinstance(v, (int, float)) and k != "row_count" else v)
                for k, v in over.items()})
    return row


def _trade(strategy, trade_type, price, qty, *, ticker="035760", trade_date=D,
           profit_loss=0, order_no="0000000001") -> dict:
    return {
        "trade_date": trade_date, "ticker": ticker, "trade_type": trade_type,
        "strategy": strategy, "price": Decimal(str(price)), "quantity": qty,
        "profit_loss": Decimal(str(profit_loss)), "order_no": order_no,
    }


# ── A: KIS 행 집계 ────────────────────────────────────────────────────────────

def test_a1_rows_fold_by_date_and_ticker_and_keep_raw():
    rows = [
        _kis(pdno="035760", sll_qty="1", sll_amt="36150", fee="5", tl_tax="54"),
        _kis(pdno="035760", sll_qty="4", sll_amt="144400", fee="22", tl_tax="216"),
        _kis(pdno="149950", buy_qty="3", buy_amt="37050", fee="5"),
    ]
    out = _mod().aggregate_kis_rows(rows)
    by = {(r["trad_dt"], r["pdno"]): r for r in out}
    a = by[(D, "035760")]
    assert a["sll_qty"] == Decimal(5)
    assert a["sll_amt"] == Decimal(180550)
    assert a["fee"] == Decimal(27)
    assert a["tl_tax"] == Decimal(270)
    assert a["row_count"] == 2
    assert a["raw"] == rows[:2]
    assert by[(D, "149950")]["buy_amt"] == Decimal(37050)
    assert len(out) == 2


def test_a1b_pdno_long_form_uses_last_six_digits():
    out = _mod().aggregate_kis_rows([_kis(pdno="A00000035760", fee="3")])
    assert out[0]["pdno"] == "035760"


def test_a2_numeric_parsing_and_blank_rows_dropped():
    rows = [
        _kis(fee="", tl_tax=" 1,234 ", sll_amt="100.50"),
        _kis(trad_dt="", fee="9"),
        _kis(pdno="  ", fee="9"),
    ]
    out = _mod().aggregate_kis_rows(rows)
    assert len(out) == 1
    assert out[0]["fee"] == Decimal(0)
    assert out[0]["tl_tax"] == Decimal(1234)
    assert out[0]["sll_amt"] == Decimal("100.50")


# ── R: 전략 귀속 ──────────────────────────────────────────────────────────────

def test_r1_single_strategy_gets_everything():
    cost = [_cost(sll_amt=180550, fee=27, tl_tax=270, rlzt_pfls=-16980)]
    trades = [_trade("kojiro", "SELL", 36110, 5)]
    out = _mod().attribute(cost, trades)
    assert len(out) == 1
    r = out[0]
    assert r["strategy"] == "kojiro"
    assert r["fee"] == pytest.approx(27)
    assert r["tl_tax"] == pytest.approx(270)
    assert r["sll_amt"] == pytest.approx(180550)
    assert r["estimated"] is False


def test_r2_two_strategies_split_and_flag():
    cost = [_cost(buy_amt=10000, sll_amt=11000, fee=30, tl_tax=20)]
    trades = [
        _trade("donchian_swing", "BUY", 1000, 10),
        _trade("vcp_breakout", "SELL", 1100, 10),
    ]
    out = {r["strategy"]: r for r in _mod().attribute(cost, trades)}
    assert set(out) == {"donchian_swing", "vcp_breakout"}
    assert out["donchian_swing"]["fee"] == pytest.approx(30 * 10000 / 21000)
    assert out["vcp_breakout"]["fee"] == pytest.approx(30 * 11000 / 21000)
    assert out["donchian_swing"]["tl_tax"] == pytest.approx(0)
    assert out["vcp_breakout"]["tl_tax"] == pytest.approx(20)
    assert out["donchian_swing"]["buy_amt"] == pytest.approx(10000)
    assert out["vcp_breakout"]["sll_amt"] == pytest.approx(11000)
    assert out["donchian_swing"]["estimated"] is True
    assert out["vcp_breakout"]["estimated"] is True


def test_r3_tax_without_sells_falls_back_to_total_share():
    cost = [_cost(buy_amt=3000, fee=6, tl_tax=3)]
    trades = [_trade("a", "BUY", 100, 10), _trade("b", "BUY", 100, 20)]
    out = {r["strategy"]: r for r in _mod().attribute(cost, trades)}
    assert out["a"]["tl_tax"] + out["b"]["tl_tax"] == pytest.approx(3)
    assert out["a"]["tl_tax"] == pytest.approx(1)


def test_r4_unmatched_cost_row_is_unattributed():
    cost = [_cost(pdno="005930", sll_amt=70000, fee=10, tl_tax=105)]
    trades = [_trade("kojiro", "SELL", 36110, 5)]  # 다른 종목
    out = _mod().attribute(cost, trades)
    assert [r["strategy"] for r in out] == ["unattributed"]
    assert out[0]["fee"] == pytest.approx(10)
    assert out[0]["estimated"] is False


def test_r4b_other_day_same_ticker_does_not_match():
    cost = [_cost(fee=10)]
    trades = [_trade("kojiro", "SELL", 36110, 5, trade_date=date(2026, 9, 29))]
    out = _mod().attribute(cost, trades)
    assert [r["strategy"] for r in out] == ["unattributed"]


def test_r5_totals_preserved_across_split():
    cost = [
        _cost(buy_amt=7000, sll_amt=13000, fee=31, tl_tax=29),
        _cost(pdno="149950", sll_amt=5000, fee=1, tl_tax=11),
    ]
    trades = [
        _trade("a", "BUY", 700, 10),
        _trade("b", "SELL", 1300, 10),
        _trade("c", "SELL", 500, 10, ticker="149950"),
    ]
    out = _mod().attribute(cost, trades)
    assert sum(r["fee"] for r in out) == pytest.approx(32)
    assert sum(r["tl_tax"] for r in out) == pytest.approx(40)


# ── S: 요약 ──────────────────────────────────────────────────────────────────

def test_s1_s2_summary_gross_net_and_bp():
    cost = [_cost(buy_amt=197000, sll_amt=180550, fee=57, tl_tax=270)]
    trades = [
        _trade("kojiro", "BUY", 39400, 5, order_no="B1"),
        _trade("kojiro", "SELL", 36110, 5, profit_loss=-16450, order_no="S1"),
    ]
    s = _mod().summarize(cost, trades)
    (k,) = [r for r in s["strategies"] if r["strategy"] == "kojiro"]
    assert k["gross_pnl"] == pytest.approx(-16450)
    assert k["fee"] == pytest.approx(57)
    assert k["tax"] == pytest.approx(270)
    assert k["net_pnl"] == pytest.approx(-16450 - 57 - 270)
    assert k["cost_bp"] == pytest.approx((57 + 270) / ((197000 + 180550) / 2) * 10000, abs=0.01)
    assert k["estimated_rows"] == 0
    assert s["total"]["net_pnl"] == pytest.approx(-16777)


def test_s1b_gross_counts_sells_even_without_cost_row():
    s = _mod().summarize([], [_trade("vcp_breakout", "SELL", 1000, 1, profit_loss=500)])
    (v,) = s["strategies"]
    assert v["gross_pnl"] == pytest.approx(500)
    assert v["fee"] == 0 and v["tax"] == 0
    assert v["cost_bp"] is None


def test_s3_slippage_from_order_price_buy_only():
    trades = [
        _trade("kojiro", "BUY", 39450, 5, order_no="B1"),
        _trade("kojiro", "SELL", 36110, 5, order_no="S1"),
    ]
    slip = [
        {"trade_date": D, "ticker": "035760", "order_no": "B1", "order_price_won": 39400},
        {"trade_date": D, "ticker": "035760", "order_no": "S1", "order_price_won": 36200},
        {"trade_date": D, "ticker": "035760", "order_no": "ZZ", "order_price_won": 1},
    ]
    s = _mod().summarize([], trades, slip)
    (k,) = s["strategies"]
    assert k["slippage_won"] == pytest.approx(50 * 5)
    assert k["slippage_n"] == 1
    assert k["slippage_bp"] == pytest.approx(250 / (39400 * 5) * 10000, abs=0.01)


def test_s4_strategy_filter():
    cost = [_cost(sll_amt=1000, fee=1), _cost(pdno="149950", sll_amt=2000, fee=2)]
    trades = [
        _trade("a", "SELL", 100, 10, profit_loss=10),
        _trade("b", "SELL", 200, 10, ticker="149950", profit_loss=20),
    ]
    s = _mod().summarize(cost, trades, strategy="b")
    assert [r["strategy"] for r in s["strategies"]] == ["b"]
    assert s["total"]["fee"] == pytest.approx(2)
    assert s["total"]["gross_pnl"] == pytest.approx(20)


# ── L: 경보 ──────────────────────────────────────────────────────────────────

def _summary_with(bp_by_strategy: dict) -> dict:
    return {"strategies": [{"strategy": k, "cost_bp": v} for k, v in bp_by_strategy.items()],
            "total": {}}


def test_l1_no_threshold_no_alert():
    assert _mod().cost_alerts(_summary_with({"kojiro": 999.0}), None) == []


def test_l2_only_strategies_above_threshold_and_not_unattributed():
    s = _summary_with({"kojiro": 40.0, "vcp_breakout": 20.0, "unattributed": 90.0, "x": None})
    out = _mod().cost_alerts(s, 30.0)
    assert [a["strategy"] for a in out] == ["kojiro"]
    assert out[0]["cost_bp"] == pytest.approx(40.0)
    assert out[0]["threshold_bp"] == pytest.approx(30.0)


def test_l3_no_threshold_constant_in_module():
    """기준값은 사용자 결정(Q3) — 모듈에 bp 기준 상수를 두지 않는다."""
    import ast
    from pathlib import Path

    src = Path(_mod().__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:  # 모듈 레벨 상수만 — 함수 안 지역 변수(읽어 온 기준값)는 대상이 아니다
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                name = getattr(t, "id", "")
                assert not ("THRESHOLD" in name.upper() or name.upper().endswith("_BP")), name
