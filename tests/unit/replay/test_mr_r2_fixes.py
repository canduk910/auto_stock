"""평균회귀 연구(트랙 R) 2차 — 확정 결함 M1~M9 · R1·R3·R4 회귀 테스트.

사전 등록 = ``_workspace/analysis/mean_reversion_20261004_r2/prereg.md`` §1·§2.
연구 전용 의존성(statsmodels·scipy)이 없는 운영 테스트 환경에서는 통째로 건너뛴다.
"""
from __future__ import annotations

import math
import os
import sys

import pytest

pytest.importorskip("statsmodels")
pytest.importorskip("scipy")

import numpy as np  # noqa: E402

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import analyze_mean_reversion as AN  # noqa: E402
from replay.data import Panel  # noqa: E402
from replay.execution import Rule, simulate_ticker  # noqa: E402
from replay.run_mean_reversion import _pass_stats, surrogate_series  # noqa: E402
from replay.strategies.mean_reversion import leung as LG  # noqa: E402
from replay.strategies.mean_reversion import ou  # noqa: E402
from replay.strategies.mean_reversion.signals import (REASON_CODES, SignalSeries,  # noqa: E402
                                                      estimate_series)


def _flat_sig(n, z, valid=True, hl=2.0, est_every=5, reason=None):
    return SignalSeries(
        z=np.asarray(z, dtype=float), valid=np.full(n, valid) if np.isscalar(valid) else np.asarray(valid),
        is_est=np.array([i % est_every == 0 for i in range(n)]),
        est_reason=np.zeros(n, dtype=np.int8) if reason is None else np.asarray(reason, dtype=np.int8),
        hl=np.full(n, hl), hl_adj=np.full(n, hl),
        sigma_stat=np.full(n, 0.05), theta=np.full(n, math.log(2) / hl), adf_p=np.full(n, 0.01))


# ── M5 / R1 — Engle–Granger 임계값 (MacKinnon N=2) ───────────────────────────

def test_mackinnon_n2_matches_statsmodels():
    from statsmodels.tsa.adfvalues import mackinnonp
    for tau in (-19.0, -6.0, -3.9, -3.34, -2.62, -2.0, 0.0, 0.92, 1.5):
        assert ou.mackinnon_p(tau, n_series=2) == pytest.approx(
            float(mackinnonp(tau, regression="c", N=2)), abs=1e-12)


def test_resid_mode_uses_engle_granger_and_price_mode_does_not():
    """잔차 모드의 ADF p = N=2 표, 가격 모드 = N=1 표. 같은 τ 면 N=2 p 가 더 크다."""
    rng = np.random.default_rng(7)
    n = 200
    lb = np.cumsum(rng.normal(0, 0.01, n)) + 7.0
    e = np.zeros(n)
    for i in range(1, n):
        e[i] = 0.6 * e[i - 1] + rng.normal(0, 0.02)
    lp = 1.1 * lb + e - 3.0
    halt = np.zeros(n, dtype=bool)
    s = estimate_series(lp, lb, halt)
    e0 = 120
    beta = ou.rolling_beta(lp, lb, e0)
    x = lp[e0 - 59:e0 + 1] - beta * lb[e0 - 59:e0 + 1]
    tau, _p1, _lag = ou.adf_c_aic(x)
    assert s.adf_p[e0] == pytest.approx(ou.mackinnon_p(tau, n_series=2), abs=1e-12)
    sp = estimate_series(lp, None, halt)
    tau_p, _p, _l = ou.adf_c_aic(lp[e0 - 59:e0 + 1])
    assert sp.adf_p[e0] == pytest.approx(ou.mackinnon_p(tau_p, n_series=1), abs=1e-12)
    assert ou.mackinnon_p(-3.0, n_series=2) > ou.mackinnon_p(-3.0, n_series=1)


# ── M4 — 대조군 halt 마스크 = 진짜 마스크 ───────────────────────────────────

def test_surrogate_uses_real_halt_mask():
    rng = np.random.default_rng(1)
    n = 260
    logp = np.log(100) + np.cumsum(rng.normal(0, 0.02, n))
    logb = np.log(2000) + np.cumsum(rng.normal(0, 0.01, n))
    halt = np.zeros(n, dtype=bool)
    halt[150] = True                          # 진짜 가격의 거래량 0 / 30% 점프 같은 halt
    for kind in ("shuffle", "rw"):
        ss = surrogate_series(logp, logb, halt, np.random.default_rng(5), kind)
        assert ss.est_reason[150] == REASON_CODES["halt"], kind   # 150 을 창에 품은 재추정일
        assert ss.est_reason[205] == REASON_CODES["halt"], kind


# ── M9 — 기록: halt 창 수 ─────────────────────────────────────────────────────

def test_pass_stats_counts_halt_windows():
    n = 40
    reason = np.full(n, -1, dtype=np.int8)
    est = np.arange(0, n, 5)
    reason[est] = [REASON_CODES[k] for k in ("warmup", "halt", "ok", "halt", "adf", "ok", "halt", "ok")]
    sig = _flat_sig(n, np.zeros(n), est_every=5, reason=reason)
    elig = np.ones(n, dtype=bool)
    elig[30] = False
    ps = _pass_stats(sig, elig)
    assert ps["n_halt"] == 3            # 재추정일 사유 halt 전부
    assert ps["n_halt_eligible"] == 2   # 그중 진입 자격이 있던 날


# ── R3 — 회귀 깨짐 두 갈래 기록 ───────────────────────────────────────────────

@pytest.mark.parametrize("code,kind", [("adf", 1), ("half_life", 1), ("b_range", 1), ("sigma", 1),
                                       ("halt", 2), ("short", 2), ("adf_fail", 2)])
def test_regime_break_kind_recorded(code, kind):
    n = 30
    o = c = np.full(n, 100.0)
    h, l = c + 0.5, c - 0.5
    z = np.full(n, -1.0)
    z[4] = -3.0
    valid = np.ones(n, dtype=bool)
    valid[10:] = False
    reason = np.zeros(n, dtype=np.int8)
    reason[10] = REASON_CODES[code]
    sig = _flat_sig(n, z, valid=valid, hl=50.0, reason=reason)
    tr = simulate_ticker(o, h, l, c, sig, np.ones(n, bool), np.ones(n), Rule("z", -2.0, 0.0, 0.0, 50.0, 9.0))
    assert tr[0]["reason"] == "regime_break" and tr[0]["xi"] == 11
    assert tr[0]["rb_kind"] == kind


def test_non_regime_break_has_rb_kind_zero():
    n = 30
    o = c = np.full(n, 100.0)
    h, l = c + 0.5, c - 0.5
    z = np.full(n, -1.0)
    z[4] = -3.0
    z[7] = 0.5
    sig = _flat_sig(n, z, hl=50.0, est_every=1000)
    tr = simulate_ticker(o, h, l, c, sig, np.ones(n, bool), np.ones(n), Rule("z", -2.0, 0.0, 0.0, 50.0, 9.0))
    assert tr[0]["reason"] == "profit" and tr[0]["rb_kind"] == 0


# ── M7 — 하한가 잠김 날의 % 손절은 다음 날 시가 ──────────────────────────────

def test_pct_stop_deferred_on_locked_limit_down():
    n = 20
    o = np.full(n, 100.0)
    c = np.full(n, 100.0)
    h, l = c + 0.5, c - 0.5
    o[8] = h[8] = l[8] = c[8] = 71.0      # 시가 = 전일 × 0.71, 고가 = 저가 → 잠김
    o[9], h[9], l[9], c[9] = 65.0, 66.0, 64.0, 65.5
    z = np.full(n, -1.0)
    z[5] = -3.0
    sig = _flat_sig(n, z, hl=50.0, est_every=1000)
    tr = simulate_ticker(o, h, l, c, sig, np.ones(n, bool), np.ones(n), Rule("z", -2.0, 0.0, 0.0, 7.0, 9.0))
    assert tr[0]["reason"] == "disaster_pct"
    assert tr[0]["xi"] == 9 and tr[0]["exit_px"] == 65.0


def test_pct_stop_not_deferred_when_not_locked():
    n = 20
    o = np.full(n, 100.0)
    c = np.full(n, 100.0)
    h, l = c + 0.5, c - 0.5
    o[8], h[8], l[8], c[8] = 71.0, 75.0, 71.0, 74.0   # 하한가에서 열었지만 풀림
    z = np.full(n, -1.0)
    z[5] = -3.0
    sig = _flat_sig(n, z, hl=50.0, est_every=1000)
    tr = simulate_ticker(o, h, l, c, sig, np.ones(n, bool), np.ones(n), Rule("z", -2.0, 0.0, 0.0, 7.0, 9.0))
    assert tr[0]["xi"] == 8 and tr[0]["exit_px"] == 71.0


# ── M8 — 진입 체결일 ≠ 청산 체결일 (구조 가드, 행위 불변) ────────────────────

def test_entry_fill_never_on_exit_fill_day_and_next_day_reentry_allowed():
    n = 40
    o = c = np.full(n, 100.0)
    h, l = c + 0.5, c - 0.5
    z = np.full(n, -3.0)                 # 늘 진입 신호
    z[[8, 16, 24]] = 0.5                  # 이익 청산 신호
    sig = _flat_sig(n, z, hl=50.0, est_every=1000)
    tr = simulate_ticker(o, h, l, c, sig, np.ones(n, bool), np.ones(n), Rule("z", -2.0, 0.0, 0.0, 50.0, 9.0))
    ents = {t["ei"] for t in tr}
    exits = {t["xi"] for t in tr}
    assert not (ents & exits)
    assert tr[1]["ei"] == tr[0]["xi"] + 1    # 청산일 종가 신호 → 다음 날 진입(1차와 같음)


# ── M9 — 비용 조건 걸림 수 ────────────────────────────────────────────────────

def test_cost_blocked_signals_counted():
    n = 20
    o = c = np.full(n, 100.0)
    h, l = c + 0.5, c - 0.5
    z = np.zeros(n)
    z[5] = -3.0
    sig = _flat_sig(n, z, hl=5.0)
    sig.sigma_stat[:] = 0.0005           # (2 − 0) × 0.0005 = 0.001 ≤ 0.0038 → 비용 조건 탈락
    stats = {}
    tr = simulate_ticker(o, h, l, c, sig, np.ones(n, bool), np.ones(n), Rule("z", -2.0, 0.0, 0.0038),
                         stats=stats)
    assert tr == [] and stats["cost_blocked"] == 1


# ── M1 · M2 — 기존 전략 일별 수익률 재구성 ───────────────────────────────────

def _mini_panel(dates, tickers, closes):
    d = np.array(dates, dtype="datetime64[D]")
    c = np.array(closes, dtype=float)
    z = np.full(c.shape, np.nan)
    return Panel(dates=d, tickers=tickers, names={}, market={}, o=c.copy(), h=c.copy(), l=c.copy(),
                 c=c, o_raw=c.copy(), c_raw=c.copy(), vol=np.ones(c.shape), tv=z, mktcap=z)


_TCOLS = ["timestamp", "ticker", "trade_type", "price", "quantity", "profit_loss", "status", "strategy", "order_no"]
_PCOLS = ["date", "strategy", "total_asset"]


def test_existing_returns_use_kst_date():
    """M2 — UTC 23:30 체결 = KST 다음 날 08:30 → 다음 날에 귀속."""
    P = _mini_panel(["2026-05-04", "2026-05-06", "2026-05-07"], ["000001"], [[100.0], [100.0], [110.0]])
    ext = {"trades": [_TCOLS, [["2026-05-05T23:30:00+00:00", "000001", "BUY", 100.0, 10, 0, "COMPLETED", "s1", ""]]],
           "perf_total": [_PCOLS, [["2026-05-04", "s1", 1000.0]]]}
    pnl, budget, meta = AN.existing_daily_returns(ext, P)
    assert meta["skipped_rows"] == 0
    assert pnl["s1"][1] == pytest.approx(0.0)           # 05-06(KST) 매수, 종가 100
    assert pnl["s1"][2] == pytest.approx(100.0)          # 05-07 +10 × 10주


def test_existing_returns_missing_first_close_uses_trade_price():
    """M1 — 첫 종가 결측이면 평가액을 0 으로 떨어뜨리지 않고 체결가로 평가한다."""
    P = _mini_panel(["2026-05-04", "2026-05-06", "2026-05-07"], ["000001"],
                    [[np.nan], [np.nan], [105.0]])
    ext = {"trades": [_TCOLS, [["2026-05-04T01:00:00+00:00", "000001", "BUY", 100.0, 10, 0, "COMPLETED", "s1", ""]]],
           "perf_total": [_PCOLS, [["2026-05-01", "s1", 2000.0]]]}
    pnl, _budget, _meta = AN.existing_daily_returns(ext, P)
    assert list(pnl["s1"]) == pytest.approx([0.0, 0.0, 50.0])


def test_existing_budget_is_prior_positive_strategy_row_else_principal():
    P = _mini_panel(["2026-05-04", "2026-05-06", "2026-05-07", "2026-05-08"], ["000001"],
                    [[100.0], [100.0], [100.0], [100.0]])
    ext = {"trades": [_TCOLS, [["2026-05-04T01:00:00+00:00", "000001", "BUY", 100.0, 10, 0, "COMPLETED", "s1", ""]]],
           "perf_total": [_PCOLS, [["2026-05-06", "s1", 3000.0], ["2026-05-07", "s1", 0.0],
                                   ["2026-05-06", "total", 999999.0]]]}
    _pnl, budget, _meta = AN.existing_daily_returns(ext, P)
    b = budget["s1"]
    assert math.isnan(b[0])                  # 05-04: 앞선 행 없음, 전일 보유 없음 → 빠짐
    assert b[1] == pytest.approx(1000.0)     # 05-06: 앞선 행 없음 → 투입 원금(10주 × 100)
    assert b[2] == pytest.approx(3000.0)     # 05-07: 05-06 행
    assert b[3] == pytest.approx(3000.0)     # 05-08: 05-07 행은 0 → 그 앞 0 초과 행
    assert "total" not in budget


def test_existing_negative_quantity_key_excluded():
    P = _mini_panel(["2026-05-04", "2026-05-06"], ["000001", "000002"], [[100.0, 50.0], [90.0, 55.0]])
    rows = [["2026-05-04T01:00:00+00:00", "000001", "SELL", 100.0, 5, 0, "COMPLETED", "s1", ""],
            ["2026-05-04T01:00:00+00:00", "000002", "BUY", 50.0, 2, 0, "COMPLETED", "s1", ""]]
    ext = {"trades": [_TCOLS, rows], "perf_total": [_PCOLS, []]}
    pnl, _b, meta = AN.existing_daily_returns(ext, P)
    assert meta["negative_qty_keys"] == 1 and meta["negative_qty_rows"] == 1
    assert pnl["s1"][1] == pytest.approx(10.0)   # 000002 만: 2주 × +5


def test_combined_existing_return_budget_weighted_and_window():
    pnl = {"a": np.array([0.0, 10.0, 20.0]), "b": np.array([0.0, -5.0, 0.0])}
    budget = {"a": np.array([np.nan, 100.0, 100.0]), "b": np.array([np.nan, 50.0, np.nan])}
    window = np.array([True, True, True])
    comb, simple = AN.combine_existing(pnl, budget, window)
    assert math.isnan(comb[0])
    assert comb[1] == pytest.approx(5.0 / 150.0)
    assert comb[2] == pytest.approx(20.0 / 100.0)
    assert simple[1] == pytest.approx(0.1 - 0.1)
    comb2, _ = AN.combine_existing(pnl, budget, np.array([True, False, True]))
    assert math.isnan(comb2[1])


# ── M3 / R4 — Leung 진입은 보상이 양수일 때만 ────────────────────────────────

_PAPER = dict(theta=0.5388, mu=16.6677, sigma=0.1599, r=0.05, c=0.05, c_hat=0.05)
_PAPER_L = 0.4834


def test_leung_literature_point_has_no_entry():
    """보상 V_L(x) − x − ĉ 가 어디서도 양수가 아니면 최적 = 안 산다(J ≡ 0)."""
    p = LG.OUParams(**_PAPER)
    b = LG.exit_level_stop(p, _PAPER_L)
    a, d = LG.entry_interval_stop(p, _PAPER_L, b)
    assert d is not None and math.isnan(d)


def test_leung_research_point_keeps_entry():
    p = LG.OUParams(theta=0.0, mu=1.0, sigma=math.sqrt(2.0), r=5e-4, c=0.05, c_hat=0.05)
    b = LG.exit_level_stop(p, -2.0)
    a, d = LG.entry_interval_stop(p, -2.0, b)
    assert math.isfinite(d) and -1.2 < d < -1.1


def test_std_bounds_no_entry_when_cost_exceeds_band():
    got = LG._std_bounds_cached(5e-4, 1.2, 1.2, -2.0)
    assert got is not None and math.isnan(got[1]) and math.isfinite(got[2])
    from replay.strategies.mean_reversion.signals import entry_leung
    assert not entry_leung(-1.5, got, z_prev=-0.5)


def test_grid_falls_back_to_exact_when_a_corner_is_no_entry():
    table = {(0, 0): (-1.1, -1.0, 1.0), (0, 1): (-1.1, -1.0, 1.0), (1, 0): (-1.1, -1.0, 1.0),
             (1, 1): (float("nan"), float("nan"), 1.0)}
    g = LG.BoundsGrid(table)
    a = math.sqrt(LG.GRID_A[0] * LG.GRID_A[1])
    cs = math.sqrt(LG.GRID_CS[0] * LG.GRID_CS[1])
    exact = LG._std_bounds_cached(LG._sig3(a), LG._sig3(cs), LG._sig3(cs), -2.0)
    assert g.lookup(a, cs) == exact


def test_mc_never_enter_rule_is_zero():
    out = LG.mc_rule_values(5e-4, 0.05, 0.05, -2.0, [None, (-1.2, -1.16, 1.16)], n_paths=500, horizon=5.0)
    assert out[0] == (0.0, 0.0)
    assert math.isfinite(out[1][0])


# ── 사후 발견 1 (M11) — 체결가와 DB 종가의 가격 기준 불일치 키 제외 ─────────

def test_existing_scale_mismatch_key_excluded_only_when_asked():
    """DB 종가가 소급 수정돼 체결가의 5배면 평가액이 가짜로 부푼다 → scale_check 판에서만 그 키를 뺀다."""
    P = _mini_panel(["2026-04-22", "2026-04-23"], ["092220", "000002"], [[9215.0, 50.0], [8005.0, 55.0]])
    rows = [["2026-04-22T01:00:00+00:00", "092220", "BUY", 1843.0, 10, 0, "COMPLETED", "s1", ""],
            ["2026-04-22T01:00:00+00:00", "000002", "BUY", 50.0, 2, 0, "COMPLETED", "s1", ""]]
    ext = {"trades": [_TCOLS, rows], "perf_total": [_PCOLS, []]}
    pnl0, _b, meta0 = AN.existing_daily_returns(ext, P)
    assert meta0["scale_mismatch_keys"] == 0
    assert pnl0["s1"][1] == pytest.approx(-12100.0 + 10.0)    # 안 고친 판(사전 등록) 그대로
    pnl1, _b, meta1 = AN.existing_daily_returns(ext, P, scale_check=True)
    assert meta1["scale_mismatch_keys"] == 1 and meta1["scale_mismatch_rows"] == 1
    assert pnl1["s1"][1] == pytest.approx(10.0)
