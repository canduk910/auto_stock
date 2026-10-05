"""운용 전략 전수 점검(2026-10-05) §3.7 etf_trend — 운영 해석 층 단위 테스트.

- 계좌용 한 랏(``EtfPos``)을 날마다 걸은 결과가 판정판 ``sim_b``(cycle391b, 관문 2 비트 일치)와 같은가
- 운영 leaf ``src.engine.etf_trend_core.simulate_exit`` 가 판정판과 같은 청산을 내는가(K1 — 15:20 해석)
- 계좌의 묶음 캡(보유 ∪ 당일 매도 ∪ 오늘 고른 것)·20일 거래대금 순서
- 비용 다시 매기기 · 원본가 판정 → 수정가 수익 환산
네트워크·DB·보관소 파일 0 — 합성 입력만 쓴다.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for p in (_TOOLS, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from replay.audit import indicators as IND  # noqa: E402
from replay.strategies import etf_trend_b as EB  # noqa: E402
from replay.strategies import etf_trend_b_audit as EA  # noqa: E402

pytestmark = pytest.mark.unit


def _synthetic(seed: int, n: int = 160) -> dict:
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0015, 0.013, n)))
    o = np.r_[c[0], c[:-1] * np.exp(rng.normal(0, 0.006, n - 1))]
    h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.012, n)))
    l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.012, n)))
    return {"ci": np.arange(n), "o": o, "h": h, "l": l, "c": c, "n14": IND.atr_sma(h, l, c, 14),
            "hi_prev20": IND.prior_max(h, 20)}


def _sig(d: dict, j: int, ticker: str = "T") -> "EA.ETFSig":
    return EA.ETFSig(ticker=ticker, ti=j + 1, gd=int(d["ci"][j + 1]), E=float(d["o"][j + 1]),
                     E_raw=float(d["o"][j + 1]), N=float(d["n14"][j]), line=float(d["hi_prev20"][j]),
                     m=1.0, tv20=1.0, sig_ci=int(d["ci"][j]))


def test_daily_stepping_lot_matches_sim_b():
    checked = 0
    for seed in range(30):
        d = _synthetic(seed)
        for j in range(30, 150, 5):
            if not (d["n14"][j] > 0):
                continue
            k, px, why = EB.sim_b(d, j)
            ps = EA.run_path_etf(_sig(d, j), d)
            assert (ps.exit_ti, ps.exit_px, ps.exit_reason) == (k, px, why)
            checked += 1
    assert checked > 400


def test_operating_leaf_simulate_exit_equals_judged_close_version():
    from src.engine import etf_trend_core as core
    checked = 0
    for seed in range(30):
        d = _synthetic(seed)
        lists = [list(map(float, d[x])) for x in ("o", "h", "l", "c")]
        for j in range(30, 150, 5):
            if not (d["n14"][j] > 0):
                continue
            k, px, why = EB.sim_b(d, j)
            k2, px2, why2 = core.simulate_exit(*lists, j)
            assert (k2, why2) == (k, why)
            assert px2 == pytest.approx(px, rel=1e-12, abs=1e-9)
            checked += 1
    assert checked > 400


def test_rnet_at_cost():
    t = {"E": 100.0, "exit_px": 104.0, "rw": 4.0}
    assert EA.rnet_at(t, 0.0038) == pytest.approx((104 - 100 - 0.38) / 4.0)


def test_raw_decision_return_uses_adjusted_factors():
    # 원본가로 판정한 거래 — 진입 100(수정 계수 0.98) · 청산 99(분배락 뒤 계수 1.0) → 수정가 수익 = 99/98 − 1
    r = EA.adj_return(E_raw=100.0, px_raw=99.0, f_entry=0.98, f_exit=1.0)
    assert r == pytest.approx(99.0 / 98.0 - 1)


class _Corr:
    def __init__(self, pairs):
        self.pairs = {frozenset(p) for p in pairs}

    def __call__(self, a, b, ci):
        return 1.0 if (a == b or frozenset((a, b)) in self.pairs) else 0.0


def _flat_d(n=60, px=100.0):
    o = np.full(n, px)
    return {"ci": np.arange(n), "o": o.copy(), "h": o * 1.01, "l": o * 0.99, "c": o.copy(),
            "n14": np.full(n, 2.0), "hi_prev20": np.full(n, 99.0)}


def test_book_cluster_cap_and_tv20_order():
    cal = pd.date_range("2024-01-01", periods=60, freq="B")
    data = {t: _flat_d() for t in ("A", "B", "C")}
    # 같은 날(ci 10 진입) A·B 신호 — 상관 > 0.9 · 거래대금은 B 가 크다 → B 만 산다
    s_a = EA.ETFSig("A", 10, 10, 100.0, 100.0, 2.0, 99.0, 1.0, 5.0, 9)
    s_b = EA.ETFSig("B", 10, 10, 100.0, 100.0, 2.0, 99.0, 1.0, 9.0, 9)
    # 다음 날 C 신호 — B 와 묶음이고 B 보유 중 → 못 산다
    s_c = EA.ETFSig("C", 11, 11, 100.0, 100.0, 2.0, 99.0, 1.0, 7.0, 10)
    sbg = {10: [s_a, s_b], 11: [s_c]}
    corr = _Corr([("A", "B"), ("B", "C")])
    run = EA.etf_book(sbg, lambda s, q: EA.EtfPos(s, data[s.ticker], q), lambda s, B, used: (1, "ok"), cal,
                      str(cal[0].date()), str(cal[30].date()), start_equity=1_000_000.0, cost_side=0.0,
                      max_pos=4, corr=corr)
    bought = sorted(ps.s.ticker for ps in run["trades"])
    assert bought == ["B"]
    assert run["counts"]["cluster"] == 2


def test_book_cluster_pool_includes_sold_today():
    cal = pd.date_range("2024-01-01", periods=60, freq="B")
    dB = _flat_d()
    dB["o"][12] = 80.0                      # B 가 12일 시가 갭으로 손절 → 그날 매도
    data = {"B": dB, "C": _flat_d()}
    s_b = EA.ETFSig("B", 10, 10, 100.0, 100.0, 2.0, 99.0, 1.0, 9.0, 9)
    s_c = EA.ETFSig("C", 12, 12, 100.0, 100.0, 2.0, 99.0, 1.0, 7.0, 11)
    corr = _Corr([("B", "C")])
    run = EA.etf_book({10: [s_b], 12: [s_c]}, lambda s, q: EA.EtfPos(s, data[s.ticker], q),
                      lambda s, B, used: (1, "ok"), cal, str(cal[0].date()), str(cal[30].date()),
                      start_equity=1_000_000.0, cost_side=0.0, max_pos=4, corr=corr)
    assert [ps.s.ticker for ps in run["trades"]] == ["B"]
    assert run["trades"][0].exit_reason == "stop_gap"
    assert abs(run["recon"]) < 1e-6
