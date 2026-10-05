"""운용 전략 전수 점검(2026-10-05) — 실거래(K4) 판정·보고 층 단위 테스트 (VB · momentum · LTV).

사전 등록 = ``prereg.frozen.md`` §1.3 L1·L2 · §3.5 · §3.6 · §3.8. 합성 왕복만 쓴다.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.strategies import vb_live as VL  # noqa: E402

pytestmark = pytest.mark.unit


def _trip(t="000001", bd="2026-09-15", sd=None, gross=0.01, qty=1, bp=10000.0, strat="volatility_breakout",
          in_window=True, ca=False):
    sd = sd or bd
    return {"strategy": strat, "ticker": t, "buy_date": bd, "sell_date": sd, "qty": qty, "buy_px": bp,
            "sell_px": bp * (1 + gross), "buy_amt": bp * qty, "gross": gross, "net": gross - 0.0038,
            "one_share": qty == 1, "ca_flag": ca, "in_window": in_window}


def test_select_applies_start_window_and_ca_flag():
    tr = [_trip(bd="2026-09-13"), _trip(bd="2026-09-14"), _trip(bd="2026-09-20", ca=True),
          _trip(bd="2026-09-21", in_window=False), _trip(bd="2026-09-22", strat="momentum")]
    got = VL.select(tr, "volatility_breakout", "2026-09-14")
    assert [t["buy_date"] for t in got] == ["2026-09-14"]


def test_select_end_bound():
    tr = [_trip(bd="2026-09-01"), _trip(bd="2026-10-01")]
    assert [t["buy_date"] for t in VL.select(tr, "volatility_breakout", "2026-09-01", end="2026-09-30")] == \
        ["2026-09-01"]


def test_l1_needs_30_and_uses_judge_cost():
    tr = [_trip(bd=f"2026-09-{d:02d}", gross=0.01) for d in range(1, 21)]
    r = VL.l1_block(tr)
    assert r["l1"]["label"] == "판정 불가" and r["l1"]["n"] == 20
    assert r["mean_net"] == pytest.approx(0.01 - 0.0038)
    tr2 = tr + [_trip(t=f"{i:06d}", bd="2026-08-01", gross=0.02) for i in range(15)]
    r2 = VL.l1_block(tr2)
    assert r2["l1"]["n"] == 35 and r2["l1"]["label"] in ("통과", "실패")


def test_l2_amount_weighted_one_share_and_top5():
    tr = [_trip(gross=0.10, qty=1, bp=1000), _trip(gross=-0.02, qty=10, bp=1000)] + \
         [_trip(gross=0.0) for _ in range(6)]
    l2 = VL.l2_block(tr)
    w = ((0.10 - 0.0038) * 1000 + (-0.02 - 0.0038) * 10000 + 6 * (-0.0038) * 10000) / (1000 + 10000 + 60000)
    assert l2["amount_weighted_net"] == pytest.approx(w)
    assert l2["one_share_share"] == pytest.approx(7 / 8)
    nets = sorted([0.10, -0.02] + [0.0] * 6)[:-5]
    assert l2["mean_net_ex_top5"] == pytest.approx(np.mean(nets) - 0.0038)


def test_vb_exit_reason_classes():
    assert VL.vb_exit_reason(_trip(gross=-0.0505)) == "STOP_LOSS(≈−5%)"
    assert VL.vb_exit_reason(_trip(gross=-0.02)) == "FORCE_CLEAR_1520"
    assert VL.vb_exit_reason(_trip(bd="2026-09-15", sd="2026-09-16")) == "OVERNIGHT"


def test_momentum_gap_bucket_uses_next_trading_day_open():
    opens = {("000001", "2026-09-16"): 11_500.0, ("000002", "2026-09-16"): 10_500.0}
    days = ["2026-09-15", "2026-09-16", "2026-09-17"]
    a = _trip(t="000001", bd="2026-09-15", sd="2026-09-16", strat="momentum")
    b = _trip(t="000002", bd="2026-09-15", sd="2026-09-16", strat="momentum")
    c = _trip(t="000003", bd="2026-09-15", sd="2026-09-15", strat="momentum")
    assert VL.momentum_bucket(a, opens, days) == "gap_ge_10"
    assert VL.momentum_bucket(b, opens, days) == "gap_lt_10"
    assert VL.momentum_bucket(c, opens, days) == "same_day"
    d = _trip(t="000009", bd="2026-09-15", sd="2026-09-16", strat="momentum")
    assert VL.momentum_bucket(d, opens, days) == "gap_unknown"


def test_ltv_mode_split():
    assert VL.ltv_mode(_trip(bd="2026-09-15", sd="2026-09-15")) == "intraday"
    assert VL.ltv_mode(_trip(bd="2026-09-15", sd="2026-09-16")) == "overnight"
