"""cycle411 Red — 사용자 결정 10-08 Q2: TE·승률·손익비 판정을 순손익(비용 차감) 기준으로.

명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` · `src/engine/te_metrics.py::compute_te_rr`.

| # | 계약 |
|---|---|
| Q1 | 페어에 `net_profit_rate`·`net_profit_loss` 가 있으면 승/패·TE·RR·verdict 는 그 값으로 판정한다 |
| Q2 | 세전 값은 `*_gross` 칸으로 남는다 — `te_pct_gross`·`te_krw_avg_gross`·`win_rate_gross` |
| Q3 | `realized_sum_krw` 는 세전 합(기존 의미 불변) · `realized_net_sum_krw` 가 순손익 합 · `fee_sum`·`tax_sum` |
| Q4 | net 칸이 없는 페어(구 입력)는 세전 값으로 판정한다 — 기존 `test_cycleF_te_rr_metrics.py` 무수정 통과 |
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from src.engine.te_metrics import compute_te_rr

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 8, 20, 0, tzinfo=KST)


def _pair(i, rate, pl, *, net_rate=None, net_pl=None, fee=None, tax=None):
    p = {
        "status": "closed", "sell_date": "2026-10-01", "profit_rate": rate, "profit_loss": pl,
        "strategy": "momentum", "pair_key": f"momentum:005930:O{i}",
    }
    if net_rate is not None:
        p.update({"net_profit_rate": net_rate, "net_profit_loss": net_pl, "fee": fee, "tax": tax})
    return p


def _gross_win_net_loss(n=20):
    # 세전 +0.1% (+700원) · 비용 0.48% (3,360원) → 순 −0.38% (−2,660원)
    return [_pair(i, 0.1, 700, net_rate=-0.38, net_pl=-2660, fee=1960, tax=1400) for i in range(n)]


def test_q1_verdict_and_te_use_net_when_present():
    m = compute_te_rr(_gross_win_net_loss(), now=NOW, strategy_id="momentum")
    assert m.n == 20
    assert m.win == 0 and m.loss == 20
    assert m.te_pct == pytest.approx(-0.38)
    assert m.te_krw_avg == pytest.approx(-2660)
    assert m.verdict == "inferior"


def test_q2_gross_values_kept_in_gross_fields():
    d = asdict(compute_te_rr(_gross_win_net_loss(), now=NOW, strategy_id="momentum"))
    assert d["te_pct_gross"] == pytest.approx(0.1)
    assert d["te_krw_avg_gross"] == pytest.approx(700)
    assert d["win_rate_gross"] == pytest.approx(1.0)


def test_q3_realized_sums_gross_net_fee_tax():
    d = asdict(compute_te_rr(_gross_win_net_loss(), now=NOW, strategy_id="momentum"))
    assert d["realized_sum_krw"] == pytest.approx(700 * 20)
    assert d["realized_net_sum_krw"] == pytest.approx(-2660 * 20)
    assert d["fee_sum"] == pytest.approx(1960 * 20)
    assert d["tax_sum"] == pytest.approx(1400 * 20)


def test_q4_pairs_without_net_fields_fall_back_to_gross():
    pairs = [_pair(i, 1.0, 1000) for i in range(20)]
    d = asdict(compute_te_rr(pairs, now=NOW, strategy_id="momentum"))
    assert d["verdict"] == "superior"
    assert d["te_pct"] == pytest.approx(1.0)
    assert d["te_pct_gross"] == pytest.approx(1.0)
    assert d["realized_net_sum_krw"] == pytest.approx(d["realized_sum_krw"])


def test_q4b_empty_metrics_carry_new_fields():
    d = asdict(compute_te_rr([], now=NOW, strategy_id="momentum"))
    for k in ("te_pct_gross", "te_krw_avg_gross", "win_rate_gross",
              "realized_net_sum_krw", "fee_sum", "tax_sum"):
        assert k in d, k
