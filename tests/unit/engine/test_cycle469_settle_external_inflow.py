"""cycle469 — 21:30 정산 외부입출금 = D+2 기준 증가분만 인지 (사용자 결정 2026-10-16).

사용자 원문: 「21:30 정산 외부입출금은 D+2 기준보다 늘어날 때만 인지.
현재 예수금 + 전일/당일 매도대금 - 전일/당일 매수대금」.

옛 식 `(Δ예수금) − (당일 매도 − 당일 매수)` 은 예수금이 D+0(결제된 돈)이라
D-2 체결의 결제분이 매일 외부입출금으로 잡혔다.

새 식:
  기준(날짜 X) = X 의 예수금 + 매매대금(X) + 매매대금(X 의 직전 영업일)   (매매대금 = 매도 − 매수)
  raw = 기준(오늘) − 기준(직전 정산일) − Σ매매대금(직전 정산일 뒤 ~ 오늘)
  인지 = raw ≥ INFLOW_MIN_WON 일 때만 raw, 아니면 0  (줄어드는 쪽·수수료 잡음은 인지하지 않는다)
"""
from __future__ import annotations

import logging
from datetime import date

import pytest

from src.engine import settlement_cashflow as sc

pytestmark = pytest.mark.unit

D = date(2026, 10, 16)       # 금
D1 = date(2026, 10, 15)      # 목
D2 = date(2026, 10, 14)      # 수


def _tr(d: date, side: str, price: int, qty: int, status: str = "COMPLETED"):
    return {"timestamp": f"{d.isoformat()}T10:00:00.000000+09:00", "trade_type": side,
            "price": price, "quantity": qty, "status": status}


@pytest.fixture
def env(monkeypatch):
    state = {"trades": [], "prev_td": {D: D1, D1: D2, D2: date(2026, 10, 13)}, "calls": []}

    async def fake_range(start, end, strategy=None):
        state["calls"].append((start, end))
        return [t for t in state["trades"] if start.isoformat() <= t["timestamp"][:10] <= end.isoformat()]

    async def fake_prev(d):
        return state["prev_td"].get(d)

    monkeypatch.setattr(sc, "_get_trades_in_range", fake_range)
    monkeypatch.setattr(sc, "_previous_trading_day", fake_prev)
    return state


async def _run(env, *, deposit, prev_deposit, prev_date=D1):
    return await sc.estimate_external_inflow(
        today=D, deposit=deposit, prev_row={"date": prev_date, "deposit": prev_deposit},
    )


async def test_no_external_flow_settlement_lag_is_not_counted(env):
    """D-1 에 50만원어치 매도 → 오늘 예수금은 아직 그대로(D+2 결제). 옛 식은 0, 새 식도 0 이어야."""
    env["trades"] = [_tr(D1, "SELL", 500_000, 1), _tr(D2, "BUY", 300_000, 1)]
    # 어제 예수금 1,000,000(D-2 매수 결제 전) · 오늘 예수금 700,000(D-2 매수 30만 결제)
    r = await _run(env, deposit=700_000, prev_deposit=1_000_000)
    # 기준(오늘) = 700,000 + 0 + 500,000 = 1,200,000
    # 기준(어제) = 1,000,000 + 500,000 + (−300,000) = 1,200,000
    assert r.raw == 0 and r.recognized == 0


async def test_old_formula_would_show_false_outflow(env):
    """같은 상황에서 옛 식은 −300,000(가짜 출금)을 냈다 — 회귀 근거."""
    env["trades"] = [_tr(D1, "SELL", 500_000, 1), _tr(D2, "BUY", 300_000, 1)]
    old = (700_000 - 1_000_000) - 0
    assert old == -300_000
    r = await _run(env, deposit=700_000, prev_deposit=1_000_000)
    assert r.recognized == 0


async def test_deposit_inflow_is_recognized(env):
    env["trades"] = [_tr(D, "BUY", 200_000, 2)]
    # 오늘 1,000,000 입금. 오늘 매수 40만은 아직 결제 전 → 예수금 2,000,000
    r = await _run(env, deposit=2_000_000, prev_deposit=1_000_000)
    # 기준(오늘) = 2,000,000 − 400,000 = 1,600,000 · 기준(어제) = 1,000,000
    # raw = 600,000 − (−400,000) = 1,000,000
    assert r.raw == 1_000_000 and r.recognized == 1_000_000


async def test_decrease_is_not_recognized(env):
    r = await _run(env, deposit=500_000, prev_deposit=1_000_000)
    assert r.raw == -500_000 and r.recognized == 0


async def test_small_positive_noise_below_threshold_is_ignored(env):
    r = await _run(env, deposit=1_000_000 + sc.INFLOW_MIN_WON - 1, prev_deposit=1_000_000)
    assert r.recognized == 0
    r2 = await _run(env, deposit=1_000_000 + sc.INFLOW_MIN_WON, prev_deposit=1_000_000)
    assert r2.recognized == sc.INFLOW_MIN_WON


async def test_only_completed_and_partial_trades_count(env):
    env["trades"] = [_tr(D, "BUY", 100_000, 1, status="PENDING"), _tr(D, "BUY", 100_000, 1, status="CANCELLED")]
    r = await _run(env, deposit=1_000_000, prev_deposit=1_000_000)
    assert r.raw == 0


async def test_gap_of_several_days_sums_flows_between(env):
    """직전 정산 행이 이틀 전(하루 정산 누락)이면 그 사이 매매대금을 모두 뺀다."""
    env["trades"] = [_tr(D1, "BUY", 100_000, 1)]
    # 직전 정산일 D2. 기준(D2) = 1,000,000 + flows(D2)0 + flows(13일)0
    # 오늘: D1 매수는 아직 미결제 → 예수금 1,000,000 · 기준(D) = 1,000,000 + 0 + (−100,000)
    # raw = 900,000 − 1,000,000 − (flows(D1)+flows(D)) = −100,000 + 100,000 = 0
    r = await _run(env, deposit=1_000_000, prev_deposit=1_000_000, prev_date=D2)
    assert r.raw == 0


async def test_no_prev_row_returns_zero(env):
    r = await sc.estimate_external_inflow(today=D, deposit=1_000_000, prev_row=None)
    assert r.recognized == 0 and r.reason == "no_prev_row"


async def test_calendar_unknown_returns_zero_with_reason(env, caplog):
    env["prev_td"] = {}
    with caplog.at_level(logging.WARNING, logger="src.engine.settlement_cashflow"):
        r = await _run(env, deposit=9_000_000, prev_deposit=1_000_000)
    assert r.recognized == 0 and r.reason == "calendar_unknown"
    assert any("[settle_ext_cashflow]" in m for m in caplog.messages)


async def test_lookup_failure_never_raises(env, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(sc, "_get_trades_in_range", boom)
    r = await _run(env, deposit=9_000_000, prev_deposit=1_000_000)
    assert r.recognized == 0 and r.reason == "lookup_failed"


async def test_single_range_query(env):
    await _run(env, deposit=1_000_000, prev_deposit=1_000_000)
    assert len(env["calls"]) == 1 and env["calls"][0] == (D2, D)


def test_scheduler_settle_uses_leaf():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[3] / "src/engine/scheduler.py").read_text(encoding="utf-8")
    body = src[src.index("async def _settle(self)"):]
    body = body[: body.index("\n    async def ", 10)] if "\n    async def " in body[10:] else body
    assert "estimate_external_inflow" in body
    assert "(float(summary.deposit) - prev_deposit) - net_trade_cashflow" not in body
