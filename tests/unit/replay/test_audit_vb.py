"""운용 전략 전수 점검(2026-10-05) — volatility_breakout 일봉 근사 재현 층 단위 테스트.

사전 등록 = ``_workspace/analysis/strategy_audit_20261005/prereg.frozen.md`` §3.5 · §1.4 · C7.
네트워크·DB·보관소 파일 0 — 합성 입력만 쓴다.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")    # 전략 모듈 import 용(값은 쓰이지 않는다 — 단계 1 R3)

from replay.audit import book as BK  # noqa: E402
from replay.strategies import vb as VB  # noqa: E402

pytestmark = pytest.mark.unit


def _bars(o, h, l, c, *, tv=None, c_raw=None, di=None, notrade=None):
    n = len(o)
    return {"o": np.array(o, float), "h": np.array(h, float), "l": np.array(l, float), "c": np.array(c, float),
            "c_raw": np.array(c_raw if c_raw is not None else c, float), "raw": np.ones(n),
            "tv": np.array(tv if tv is not None else [6e10] * n, float),
            "di": np.array(di if di is not None else range(n)),
            "notrade": np.array(notrade if notrade is not None else [False] * n)}


# ── 목표가 ──────────────────────────────────────────────────────────────

def test_noise_k_excludes_prev_bar_and_uses_k_period_plus_one_bars():
    """운영: days=k_period+2 최신순 → candles[0]=D−1 은 range 용, candles[1:] (k_period+1 봉) 가 noise."""
    n = 30
    o = np.full(n, 100.0)
    h = np.full(n, 110.0)
    l = np.full(n, 90.0)
    c = np.full(n, 105.0)          # noise = 1 − 5/20 = 0.75
    i = 25
    c[i - 1] = 110.0               # D−1 noise = 0.5 — 빠져야 한다
    c[i - 2 - 15] = 100.0          # D−17 noise = 1.0 — 들어가야 한다(16번째 봉)
    c[i - 2 - 16] = 90.0           # D−18 noise = 0.5 — 빠져야 한다
    k = VB.noise_k(o, h, l, c, i, 15)
    assert k == pytest.approx((0.75 * 15 + 1.0) / 16)


def test_noise_k_skips_zero_range_bars_and_short_history():
    o = np.array([100, 100, 100, 100.0])
    h = np.array([100, 110, 100, 100.0])
    l = np.array([100, 90, 100, 100.0])
    c = np.array([100, 105, 100, 100.0])
    assert VB.noise_k(o, h, l, c, 3, 15) == pytest.approx(0.75)   # 봉 1 만(봉 0 은 범위 0)
    assert np.isnan(VB.noise_k(o, h, l, c, 1, 15))


def test_target_offset_uses_prev_range_k_and_board_multiplier():
    assert VB.target_offset(110, 90, 0.5, 1.3) == pytest.approx(13.0)


# ── 두 판 청산 ───────────────────────────────────────────────────────────

def test_exit_ambiguous_day_pessimistic_stops_optimistic_holds_to_close():
    E = 100.0
    assert VB.exit_px(E, 106, 94, 101, -5.0, "pes") == (pytest.approx(95.0), "STOP_LOSS")
    assert VB.exit_px(E, 106, 94, 101, -5.0, "opt") == (101, "FORCE_CLEAR_1520")


def test_exit_close_below_stop_is_stop_in_both_versions():
    for v in VB.VERSIONS:
        assert VB.exit_px(100.0, 104, 93, 94, -5.0, v) == (pytest.approx(95.0), "STOP_LOSS")


def test_exit_no_stop_is_close():
    for v in VB.VERSIONS:
        assert VB.exit_px(100.0, 108, 97, 103, -5.0, v) == (103, "FORCE_CLEAR_1520")


def test_exit_unknown_version_raises():
    with pytest.raises(ValueError):
        VB.exit_px(100.0, 1, 1, 1, -5.0, "x")


# ── 후보 · 신호 ─────────────────────────────────────────────────────────

def _flat(n, base=10000.0):
    o = np.full(n, base)
    h = np.full(n, base * 1.02)
    l = np.full(n, base * 0.98)
    c = np.full(n, base * 1.01)
    return o, h, l, c


def test_universe_mask_trade_value_mcap_price_and_contiguity():
    o, h, l, c = _flat(5)
    b = _bars(o, h, l, c, tv=[6e10, 6e10, 4e10, 6e10, 6e10])
    p = VB.VB_OP
    assert VB.universe_mask(b, 4, p, 6e10)
    assert not VB.universe_mask(b, 3, p, 6e10)            # 전일 거래대금 400억
    assert not VB.universe_mask(b, 4, p, 4e10)            # 전일 시총 400억
    assert not VB.universe_mask(b, 4, p, float("nan"))
    b2 = _bars(o, h, l, c, c_raw=[2000.0] * 5)
    assert not VB.universe_mask(b2, 4, p, 6e10)           # 전일 종가 < 3,000
    b3 = _bars(o, h, l, c, di=[0, 1, 2, 4, 5])
    assert not VB.universe_mask(b3, 3, p, 6e10)           # 전일 봉이 바로 앞 거래일이 아님(정지 다음 날)


def test_signals_breakout_entry_at_target_and_none_without_touch():
    n = 25
    o, h, l, c = _flat(n)
    h[n - 1] = 10000 * 1.10
    bars = {"005930": _bars(o, h, l, c)}
    cands = VB.day_candidates(bars, lambda t, b, i: 1e12)
    sigs = VB.signals_from_candidates(cands, bars)
    last = [s for s in sigs if s.ti == n - 1]
    assert len(last) == 1
    k = (1 - 100 / 400)           # |c−o| = 100, range = 400
    assert last[0].E == pytest.approx(10000 + 400 * k * 1.3)
    # 고가가 목표가에 못 닿은 날은 신호가 없다
    assert all(s.H >= s.E for s in sigs)
    assert not [s for s in sigs if s.ti == n - 2]


def test_non_numeric_ticker_excluded():
    o, h, l, c = _flat(25)
    h[-1] = 20000
    bars = {"00088K": _bars(o, h, l, c)}
    assert VB.day_candidates(bars, lambda t, b, i: 1e12) == {}


# ── 쿨다운 ──────────────────────────────────────────────────────────────

def _sig(t, gd, E=100.0, H=110.0, L=99.0, C=105.0):
    return VB.Sig(t, gd, gd, E, E, 99.0, H, L, C, 0.5, 1.0)


def test_population_cooldown_blocks_next_two_trading_days():
    sigs = [_sig("A", d) for d in (10, 11, 12, 13, 14, 17)]
    pop = VB.population(sigs, "pes", 0, 100)
    assert [s.gd for s, _px, _w in pop] == [10, 13, 17]


def test_population_window_bounds():
    sigs = [_sig("A", d) for d in (5, 50, 150)]
    assert [s.gd for s, *_ in VB.population(sigs, "opt", 10, 100)] == [50]


# ── 계좌(C7) ────────────────────────────────────────────────────────────

def test_book_two_slots_same_day_exit_and_reconcile():
    cal = pd.DatetimeIndex(pd.bdate_range("2024-01-01", periods=10))
    sigs = {2: [_sig("A", 2), _sig("B", 2), _sig("C", 2)], 3: [_sig("A", 3), _sig("D", 3)]}
    qty = lambda P, B, used: VB.spec_qty(P, B, used)    # noqa: E731
    open_pos, size_fn = VB.make_book_fns("opt", qty)
    r = BK.run_book(sigs, open_pos, size_fn, cal, str(cal[0].date()), str(cal[-1].date()), 0,
                    start_equity=1_000_000.0, cost_side=0.0019, max_pos=2)
    assert r["counts"]["fill"] == 3                    # 첫날 2 · 다음 날 D 1(A 는 쿨다운)
    assert r["counts"]["slot_full"] == 1
    assert r["counts"]["zero_cooldown"] == 1            # 씨앗 0 은 첫날 A 를 샀다 → 다음 날 A 는 쿨다운
    assert abs(r["recon"]) < 1e-6
    assert all(t.exit_gd == t.s.gd for t in r["trades"])


def test_operating_sizer_matches_spec_on_grid():
    from replay.audit.sizing import OpSizer
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    op = OpSizer(VolatilityBreakoutStrategy, "volatility_breakout",
                 {"position_ratio": 0.35, "max_positions": 2, "max_lot_ratio_mult": 1.0})
    sz = VB.lot_qty_operating(op)
    diff = []
    for B in (94_156, 148_767, 4_707_820):
        for used in (0, int(B * 0.35), int(B * 0.9)):
            for P in (3_000, 33_000, 33_001, 87_000, 150_000, 499_000, 1_700_000):
                a, b = VB.spec_qty(P, B, used), sz(P, B, used)
                if a != b:
                    diff.append((B, used, P, a, b))
    assert diff == []
