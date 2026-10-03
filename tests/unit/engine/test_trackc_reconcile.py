"""트랙 C(실비용 산출) — 사후 대사 흐름 `trade_cost.reconcile` / `build_summary`.

명세 = `_workspace/design/2026-10-01_mean_reversion_handoff.md` §4.2-1·3·5

| # | 계약 |
|---|---|
| C1 | KIS 조회 → 집계 → `trade_cost_daily` upsert + 기간 합계 upsert, 저장 건수·쪽수 반환 |
| C2 | 행 합계(수수료·세금)와 KIS output2 합계가 같으면 `totals_match=True`, 다르면 False |
| C3 | 경보 기준 없음(None) = `[trade_cost_high]` 0건 · system_logs 0건 |
| C4 | 기준 있음 + 30일 창 실효 bp 초과 = `[trade_cost_high]` WARNING 1행 + system_logs WARNING |
| C5 | 경보 계산이 실패해도 대사 결과는 돌려준다(관측 전용) |
| C6 | `build_summary` 는 DB 에서 비용 행·체결 행·주문가를 읽어 `summarize` 결과를 돌려준다 |
| C7 | 경보 창 = `end` 를 포함한 30 달력일 |
"""

from __future__ import annotations

import importlib
import logging
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit

D = date(2026, 9, 30)


def _mod():
    return importlib.import_module("src.engine.trade_cost")


def _kis_row(pdno="035760", fee="27", tl_tax="270", sll_amt="180550"):
    return {"trad_dt": "20260930", "pdno": pdno, "prdt_name": "X", "buy_qty": "0",
            "buy_amt": "0", "sll_qty": "5", "sll_amt": sll_amt, "rlzt_pfls": "-16980",
            "fee": fee, "tl_tax": tl_tax}


@pytest.fixture
def env(monkeypatch):
    m = _mod()
    fetched = SimpleNamespace(
        rows=[_kis_row()],
        summary={"tot_fee": "27", "tot_tltx": "270", "sll_fee_smtl": "27",
                 "sll_tltx_smtl": "270", "buy_fee_smtl": "0", "buy_tax_smtl": "0",
                 "tot_rlzt_pfls": "-16980"},
        pages=1, truncated=False,
    )
    fetch = AsyncMock(return_value=fetched)
    upsert_daily = AsyncMock(side_effect=lambda rows: len(rows))
    upsert_total = AsyncMock(return_value=None)
    get_daily = AsyncMock(return_value=[{
        "trad_dt": D, "pdno": "035760", "prdt_name": "X", "buy_qty": Decimal(0),
        "buy_amt": Decimal(197000), "sll_qty": Decimal(5), "sll_amt": Decimal(180550),
        "rlzt_pfls": Decimal(-16980), "fee": Decimal(57), "tl_tax": Decimal(270),
        "row_count": 1, "raw": [],
    }])
    get_trades = AsyncMock(return_value=[
        {"trade_date": D, "ticker": "035760", "trade_type": "SELL", "strategy": "kojiro",
         "price": Decimal(36110), "quantity": 5, "profit_loss": Decimal(-16450),
         "order_no": "S1"},
    ])
    get_prices = AsyncMock(return_value=[])
    threshold = AsyncMock(return_value=None)
    write_log = AsyncMock(return_value=None)

    monkeypatch.setattr(m.trade_profit, "fetch_period_trade_profit", fetch)
    monkeypatch.setattr(m.trade_cost_db, "upsert_daily", upsert_daily)
    monkeypatch.setattr(m.trade_cost_db, "upsert_period_total", upsert_total)
    monkeypatch.setattr(m.trade_cost_db, "get_daily_range", get_daily)
    monkeypatch.setattr(m.trade_cost_db, "get_completed_trades", get_trades)
    monkeypatch.setattr(m.trade_cost_db, "get_buy_order_prices", get_prices)
    monkeypatch.setattr(m.system_config, "get_trade_cost_alert_bp", threshold)
    monkeypatch.setattr(m.system_logs, "write_log", write_log)
    return SimpleNamespace(m=m, fetch=fetch, upsert_daily=upsert_daily,
                           upsert_total=upsert_total, get_daily=get_daily,
                           get_trades=get_trades, get_prices=get_prices,
                           threshold=threshold, write_log=write_log, fetched=fetched)


def _high(caplog):
    return [r for r in caplog.records
            if r.levelno >= logging.WARNING and r.getMessage().startswith("[trade_cost_high] ")]


async def test_c1_reconcile_saves_and_reports(env):
    out = await env.m.reconcile(date(2026, 9, 1), D)
    env.fetch.assert_awaited_once_with("20260901", "20260930")
    (rows,), _ = env.upsert_daily.await_args
    assert len(rows) == 1 and rows[0]["pdno"] == "035760" and rows[0]["fee"] == Decimal(27)
    a = env.upsert_total.await_args
    assert a.args[0] == date(2026, 9, 1) and a.args[1] == D
    assert a.args[2] == env.fetched.summary
    assert out["kis_rows"] == 1
    assert out["saved_rows"] == 1
    assert out["pages"] == 1
    assert out["truncated"] is False
    assert out["row_fee"] == pytest.approx(27)
    assert out["row_tax"] == pytest.approx(270)
    assert out["kis_tot_fee"] == pytest.approx(27)
    assert out["kis_tot_tltx"] == pytest.approx(270)


async def test_c2_totals_match_flag(env):
    out = await env.m.reconcile(date(2026, 9, 1), D)
    assert out["totals_match"] is True
    env.fetched.summary = dict(env.fetched.summary, tot_fee="28")
    out2 = await env.m.reconcile(date(2026, 9, 1), D)
    assert out2["totals_match"] is False


async def test_c2b_empty_summary_totals_match_none(env):
    env.fetched.summary = {}
    out = await env.m.reconcile(date(2026, 9, 1), D)
    assert out["totals_match"] is None


async def test_c3_no_threshold_no_alert(env, caplog):
    caplog.set_level(logging.DEBUG)
    out = await env.m.reconcile(date(2026, 9, 1), D)
    assert out["alerts"] == []
    assert _high(caplog) == []
    env.write_log.assert_not_awaited()


async def test_c4_threshold_exceeded_emits_warning(env, caplog):
    caplog.set_level(logging.DEBUG)
    env.threshold.return_value = 10.0
    out = await env.m.reconcile(date(2026, 9, 1), D)
    assert [a["strategy"] for a in out["alerts"]] == ["kojiro"]
    recs = _high(caplog)
    assert len(recs) == 1
    assert "strategy=kojiro" in recs[0].getMessage()
    assert "threshold_bp=10" in recs[0].getMessage()
    levels = [c.args[0] for c in env.write_log.await_args_list]
    assert levels == ["WARNING"]
    assert env.write_log.await_args.args[1].startswith("[trade_cost_high] ")


async def test_c5_alert_failure_does_not_break_reconcile(env, caplog):
    caplog.set_level(logging.DEBUG)
    env.threshold.side_effect = RuntimeError("db down")
    out = await env.m.reconcile(date(2026, 9, 1), D)
    assert out["saved_rows"] == 1
    assert out["alerts"] == []


async def test_c6_build_summary_reads_db(env):
    s = await env.m.build_summary(date(2026, 9, 1), D)
    env.get_daily.assert_awaited_once_with(date(2026, 9, 1), D)
    env.get_trades.assert_awaited_once_with(date(2026, 9, 1), D)
    env.get_prices.assert_awaited_once_with(date(2026, 9, 1), D)
    (k,) = s["strategies"]
    assert k["strategy"] == "kojiro"
    assert k["net_pnl"] == pytest.approx(-16450 - 57 - 270)


async def test_c7_alert_window_is_30_days_ending_at_end(env):
    env.threshold.return_value = 10.0
    await env.m.reconcile(date(2026, 9, 25), D)
    env.get_daily.assert_awaited_with(date(2026, 9, 1), D)


# ── 경보 기준 읽기 `system_config.get_trade_cost_alert_bp` ─────────────────────

@pytest.mark.parametrize("stored, expected", [
    (None, None),                 # 키 없음 = 경보 끔
    ({"value": 35}, 35.0),
    ({"value": 12.5}, 12.5),
    (40, 40.0),
    ({"value": 0}, None),         # 0 이하 = 끔
    ({"value": -3}, None),
    ({"value": "30"}, None),      # 숫자가 아니면 끔
    ({"value": True}, None),
])
async def test_t1_alert_threshold_reader(fake_pg_kv, monkeypatch, stored, expected):
    from src.db import system_config

    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    if stored is not None:
        fake_pg_kv.store["trade_cost_alert_bp"] = stored
    assert await system_config.get_trade_cost_alert_bp() == expected
