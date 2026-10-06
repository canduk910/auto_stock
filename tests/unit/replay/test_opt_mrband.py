"""횡보장 전용 볼린저 밴드 재검증 — 핵심 규칙 고정(사전 등록 §2·§3·§5).

합성 시리즈로 장세 라벨 · 밴드 · 신호 · 청산 순서 · 모집단 · 계좌 대사를 고정한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.replay.strategies import mrband as M


def _arr(*xs):
    return [np.asarray(x, dtype=float) for x in xs]


def _sim(o, h, l, c, *, e=1, stop=0.0, exit_mode=M.EXIT_MID, mid=None, up=None, liq=False, nonside=None,
         notrade=None, locked=None, adverse=False, max_hold=M.MAX_HOLD):
    o, h, l, c = _arr(o, h, l, c)
    n = len(o)
    mid = np.full(n, np.nan) if mid is None else np.asarray(mid, float)
    up = np.full(n, np.nan) if up is None else np.asarray(up, float)
    nonside = np.zeros(n, bool) if nonside is None else np.asarray(nonside, bool)
    notrade = np.zeros(n, bool) if notrade is None else np.asarray(notrade, bool)
    locked = np.zeros(n, bool) if locked is None else np.asarray(locked, bool)
    return M.sim_trade(o, h, l, c, notrade, locked, mid, up, nonside, e, stop, exit_mode, liq, adverse,
                       max_hold)


# ── 장세 라벨 ─────────────────────────────────────────────────────────────────

def test_regime_label_is_shifted_one_day_and_hysteresis_holds():
    d = pd.bdate_range("2021-01-01", periods=200)
    up = pd.Series(np.exp(np.linspace(0, 0.6, 200)), index=d)       # 꾸준한 상승 · 낮은 변동
    F = M.regime_labels(up)
    assert F.index[0] == d[80]                    # 60일선 + 20일 기울기 + 하루 밀기 = 81번째 봉
    assert set(F.reg) <= {"SL", "UL"}
    assert F.reg.iloc[-1] == "UL"
    # 하루 밀기 — D 일 기울기 = D−1 종가까지
    sma = up.rolling(60).mean()
    assert F.slope.iloc[0] == pytest.approx((sma / sma.shift(20) - 1).iloc[79])


def test_hysteresis_direction_band():
    out = M._hyst_dir([0.0, 0.031, 0.02, 0.011, 0.009, -0.02, -0.031, -0.02, -0.009, 0.0])
    assert out == ["S", "U", "U", "U", "S", "S", "D", "D", "S", "S"]
    assert M._hyst_dir([0.04, -0.05]) == ["U", "D"]          # 상승 풀리는 날 −3% 아래면 곧장 하락
    assert M._hyst_vol([0.19, 0.21, 0.17, 0.159, 0.19]) == ["L", "H", "H", "L", "L"]


# ── 밴드 · 신호 ───────────────────────────────────────────────────────────────

def test_bollinger_population_std_and_signals():
    c = np.array([10, 10, 10, 10, 6, 11], float)
    mid, lo, up = M.bollinger(c, 4, 1.0)
    assert np.isnan(mid[2]) and mid[3] == 10 and lo[3] == 10
    w = c[1:5]
    assert lo[4] == pytest.approx(w.mean() - w.std(ddof=0))
    t = M.entry_days(c, lo, "touch")
    r = M.entry_days(c, lo, "reentry")
    assert list(np.nonzero(t)[0]) == [4]
    assert list(np.nonzero(r)[0]) == [5]                     # 이탈 다음 날 하단 위로 복귀


# ── 청산 ──────────────────────────────────────────────────────────────────────

def test_mid_limit_uses_previous_day_line_and_gap_open():
    mid = [np.nan, 100, 104, 104]
    # d=2 시가 105 ≥ 전일 mid(=100 at d=1) → 시가 청산
    x, X, r, ph = _sim([90, 95, 105, 105], [90, 98, 106, 106], [90, 94, 104, 104], [90, 96, 105, 105],
                       mid=mid, stop=80)
    assert (x, X, r, ph) == (2, 105.0, M.R_TP, 0)


def test_mid_limit_intraday_fill_at_line():
    mid = [np.nan, 100, 104, 104]
    x, X, r, ph = _sim([90, 95, 97, 97], [90, 98, 101, 101], [90, 94, 96, 96], [90, 96, 99, 99],
                       mid=mid, stop=80)
    assert (x, X, r, ph) == (2, 100.0, M.R_TP, 1)


def test_entry_bar_open_above_line_exits_at_open():
    mid = [101, 100, 100]
    x, X, r, ph = _sim([90, 102, 102], [90, 103, 103], [90, 99, 99], [90, 101, 101], mid=mid, stop=80)
    assert (x, X, r) == (1, 102.0, M.R_TP)


def test_stop_and_adverse_order():
    # 양봉 봉에 손절선(95)과 이익선(103)이 다 있다: 판정판 시→저→고 = 손절 먼저 / 음봉이면 고 먼저
    mid = [np.nan, 103, 103]
    bull = dict(o=[100, 100, 100], h=[100, 101, 104], l=[100, 99, 94], c=[100, 100, 103])
    x, X, r, _ = _sim(**bull, mid=mid, stop=95)
    assert (r, X) == (M.R_STOP, 95.0)
    bear = dict(o=[100, 100, 100], h=[100, 101, 104], l=[100, 99, 94], c=[100, 100, 96])
    assert _sim(**bear, mid=mid, stop=95)[2] == M.R_TP
    assert _sim(**bear, mid=mid, stop=95, adverse=True)[2] == M.R_STOP


def test_gap_stop_fills_at_open_and_locked_defers():
    o, h, l, c = [100, 100, 90, 70, 75], [100, 101, 91, 70, 76], [100, 99, 89, 70, 74], [100, 100, 90, 70, 75]
    assert _sim(o, h, l, c, stop=93)[:3] == (2, 90.0, M.R_STOP)
    lk = [False, False, True, True, False]
    assert _sim(o, h, l, c, stop=93, locked=lk)[:3] == (4, 75.0, M.R_STOP)


def test_time_exit_after_max_hold_bars():
    n = 15
    flat = [100.0] * n
    x, X, r, ph = _sim(flat, flat, flat, flat, stop=50, max_hold=10)
    assert (x, r, ph) == (11, M.R_TIME, 0)                   # 봉 1..10 보유 → 11번째 봉 시가


def test_mid_close_exits_next_open():
    mid = [np.nan, 100, 100, 100, 100]
    x, X, r, ph = _sim([90, 95, 99, 103, 104], [90, 97, 101, 104, 105], [90, 94, 98, 102, 103],
                       [90, 96, 100.5, 103, 104], mid=mid, stop=50, exit_mode=M.EXIT_MIDCLOSE)
    assert (x, X, r, ph) == (3, 103.0, M.R_TP, 0)


def test_liq_on_non_sideways_label_at_open_and_keep_ignores():
    flat = [100.0] * 6
    ns = [False, False, False, True, True, False]
    assert _sim(flat, flat, flat, flat, stop=50, liq=True, nonside=ns)[:3] == (3, 100.0, M.R_LIQ)
    assert _sim(flat, flat, flat, flat, stop=50, liq=False, nonside=ns)[2] == M.R_END


def test_notrade_bar_defers_liq():
    flat = [100.0] * 6
    ns = [False, False, False, True, False, False]
    nt = [False, False, False, True, False, False]
    assert _sim(flat, flat, flat, flat, stop=50, liq=True, nonside=ns, notrade=nt)[:3] == (4, 100.0, M.R_LIQ)


# ── 후보 · 모집단 ─────────────────────────────────────────────────────────────

def _bars(c, start_di=0):
    c = np.asarray(c, float)
    n = len(c)
    return {"di": np.arange(start_di, start_di + n), "o": c.copy(), "h": c * 1.001, "l": c * 0.999, "c": c,
            "o_raw": c.copy(), "notrade": np.zeros(n, bool)}


def test_candidates_respect_sideways_filter_and_population_no_overlap():
    rng = np.random.default_rng(0)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))
    b = _bars(c)
    lab = np.full(300, 3)
    lab[150:] = 1                                              # 뒤 절반 상승
    ok = np.ones(300, bool)
    allc = M.candidates_for_ticker("A", b, lab, ok, n=20, k=1.5, exit_mode=M.EXIT_MID, stop="pct",
                                   liq=False, sideways_only=False)
    side = M.candidates_for_ticker("A", b, lab, ok, n=20, k=1.5, exit_mode=M.EXIT_MID, stop="pct",
                                   liq=False, sideways_only=True)
    assert all(cd.reg in M.SIDEWAYS for cd in side["touch"])
    assert len(side["touch"]) < len(allc["touch"])
    pop = M.population(allc["touch"])
    for a, bb in zip(pop, pop[1:]):
        assert bb.e > a.x                                      # 청산 봉 뒤에만 다음 진입


def test_net_return_cost():
    assert M.net_ret(100, 100, 0.0038) == pytest.approx(0.9981 / 1.0019 - 1)


def test_cboot_and_week_diff_are_deterministic():
    v = np.r_[np.full(50, 0.01), np.full(50, -0.005)]
    keys = [f"k{i // 2}" for i in range(100)]
    a = M.cboot(v, keys, n_boot=500)
    b = M.cboot(v, keys, n_boot=500)
    assert a == b and a[1] < a[0] < a[2]


def test_book_reconciles_and_never_uses_one_share_fallback():
    c = np.array([100.0] * 5 + [90, 95, 100, 105, 110] + [110.0] * 5)
    b = _bars(c)
    b["o_raw"] = b["o_raw"] * 1000                               # 1주 = 10만 원대 → 작은 예산이면 0주
    cal = pd.bdate_range("2024-01-01", periods=len(c))
    cd = M.Cand("A", 6, 8, 6, 8, 1, 95.0, 105.0, M.R_TP, 3, False, 95_000.0, 105.0, 8)
    out = M.run_book([cd], {"A": b}, cal, 0, len(c) - 1, 0, start_equity=1_000_000, cost_rt=0.0038,
                     pos_ratio=0.2, max_pos=5)
    assert out["counts"]["fill"] == 1 and abs(out["recon"]) < 1e-6
    poor = M.run_book([cd], {"A": b}, cal, 0, len(c) - 1, 0, start_equity=300_000, cost_rt=0.0038,
                      pos_ratio=0.2, max_pos=5)
    assert poor["counts"].get("zero_funds") == 1 and poor["counts"].get("fill", 0) == 0
