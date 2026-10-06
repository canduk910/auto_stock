"""volatility_breakout 효율화 탐색 층(``vb_opt``) 단위 테스트 — 합성 입력만.

사전 고정 = ``_workspace/analysis/strategy_opt_20261005/vb/prereg.md``.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")

from replay.audit import book as BK  # noqa: E402
from replay.strategies import vb_opt as VO  # noqa: E402

pytestmark = pytest.mark.unit


def _b(o, h, l, c):
    n = len(o)
    return {"o": np.array(o, float), "h": np.array(h, float), "l": np.array(l, float), "c": np.array(c, float),
            "raw": np.ones(n), "di": np.arange(n)}


def test_grid_size_within_cap_and_contains_current():
    g = VO.grid()
    assert len(g) == 189 <= 200
    assert VO.CURRENT in g


@pytest.mark.parametrize("version,stop_expected", [("pes", True), ("opt", False)])
def test_same_day_stop_two_versions(version, stop_expected):
    # 체결 100 · 저가 94(−6%) · 종가 97 → 손절 −5 는 비관판만
    b = _b([95, 99], [101, 100], [94, 98], [97, 99])
    px, why, xi = VO.outcome(b, 0, 100.0, -5.0, "C", version)
    assert (why == "STOP_LOSS") is stop_expected
    assert xi == 0
    assert px == (95.0 if stop_expected else 97.0)


def test_hold_next_open_and_winner_only():
    b = _b([95, 103], [104, 105], [99, 101], [102, 104])
    assert VO.outcome(b, 0, 100.0, -5.0, "N", "opt") == (103.0, "NEXT_OPEN", 1)
    assert VO.outcome(b, 0, 100.0, -5.0, "W", "opt") == (103.0, "NEXT_OPEN", 1)       # 종가 102 > 100
    assert VO.outcome(b, 0, 102.5, -5.0, "W", "opt") == (102.0, "CLOSE", 0)           # 종가 ≤ 체결가 → 당일 청산
    assert VO.outcome(b, 0, 100.0, -5.0, "C", "opt") == (102.0, "CLOSE", 0)


def test_overnight_without_next_bar_exits_at_close():
    b = _b([95], [104], [99], [102])
    assert VO.outcome(b, 0, 100.0, -5.0, "N", "opt") == (102.0, "CLOSE", 0)


def test_filters():
    mk = lambda t, k, tv, tr, rp: VO.Cand(t, 5, 0, k, 1.0, tv, tr, rp)  # noqa: E731
    cs = [mk("000001", 0.4, 10, True, 0.06), mk("000002", 0.6, 30, False, 0.03)]
    assert [x.ticker for x in VO.filter_day(cs, "F3", 1.0)] == ["000001"]
    assert [x.ticker for x in VO.filter_day(cs, "F4", 1.0)] == ["000001"]
    assert [x.ticker for x in VO.filter_day(cs, "F5", 1.0)] == ["000001"]
    assert VO.filter_day(cs, "F1", 0.75) == [] and len(VO.filter_day(cs, "F2", 0.75)) == 2
    assert len(VO.filter_day(cs, "F1", float("nan"))) == 2                          # 판정 불가 = m 1
    many = [mk(f"{i:06d}", 0.5, i, True, 0.1) for i in range(15)]
    top = VO.filter_day(many, "F6", 1.0)
    assert len(top) == VO.F6_TOP and top[0].tv_prev == 14


def test_trend_flag_uses_only_past_bars():
    c = np.arange(1, 40, dtype=float)
    assert VO.trend_flag(c, 30)
    c2 = c.copy()
    c2[30:] = 0.0                       # D 이후 값을 바꿔도 판정이 같아야 한다
    assert VO.trend_flag(c2, 30)
    assert not VO.trend_flag(c, 10)     # SMA 자료 부족


def test_population_cooldown_counts_from_exit_day():
    b = _b([95] * 8, [104] * 8, [99] * 8, [102] * 8)
    bars = {"000001": b}
    sigs = [VO.OSig("000001", i, i, 100.0, 100.0, 100.0, 0.5, 1.0) for i in range(8)]
    pop_n = VO.population(sigs, bars, "N", -5.0, "opt", 0, 7, cooldown=2)
    # 진입 0 → 청산 1 · 다음 허용 = 1 + 2 + 1 = 4 → 청산 5 · 다음 8(범위 밖)
    assert [s.gd for s, *_ in pop_n] == [0, 4]
    pop_c = VO.population(sigs, bars, "C", -5.0, "opt", 0, 7, cooldown=2)
    assert [s.gd for s, *_ in pop_c] == [0, 3, 6]


def test_week_block_diff_sign_and_zero():
    d0 = date(2024, 1, 1)
    dates = [d0 + timedelta(days=7 * i) for i in range(40)]
    a = np.full(40, 0.01)
    r = VO.week_block_diff(a, dates, a - 0.005, dates)
    assert r["diff"] == pytest.approx(0.005) and r["lo90"] == pytest.approx(0.005)
    r2 = VO.week_block_diff(a, dates, a, dates)
    assert r2["diff"] == pytest.approx(0.0)


def test_book_overnight_position_reconciles():
    cal = pd.DatetimeIndex(pd.bdate_range("2024-01-01", periods=6))
    b = _b([95, 103, 100, 100, 100, 100], [104, 105, 101, 101, 101, 101], [99, 101, 99, 99, 99, 99],
           [102, 104, 100, 100, 100, 100])
    bars = {"000001": b}
    s = VO.OSig("000001", 0, 0, 100.0, 100.0, 100.0, 0.5, 1.0)
    open_pos, size_fn = VO.make_book_fns(bars, "N", -5.0, "opt", lambda P, B, used: 10)
    res = BK.run_book({0: [s]}, open_pos, size_fn, cal, str(cal[0].date()), str(cal[-1].date()), 0,
                      start_equity=10_000.0, cost_side=0.0019, max_pos=2)
    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t.exit_px == 103.0 and t.exit_reason == "NEXT_OPEN" and t.exit_gd == 1
    assert res["equity"][0] == pytest.approx(10_000 - 1000 * 1.0019 + 10 * 102)   # D 종가 평가
    assert abs(res["recon"]) < 1e-6


def test_close_stop_mode_is_version_free_except_disaster():
    # 체결 100 · 저가 94 · 종가 96 → 종가 손절 −3 은 두 판 같다(종가 96 청산)
    b = _b([95, 99], [101, 100], [94, 98], [96, 99])
    for v in ("pes", "opt"):
        assert VO.outcome(b, 0, 100.0, -3.0, "N", v, "close") == (96.0, "CLOSE_STOP", 0)
    # 손절 −5 면 종가 96 > 95 → 보유 N 은 다음 날 시가
    assert VO.outcome(b, 0, 100.0, -5.0, "N", "pes", "close") == (99.0, "NEXT_OPEN", 1)
    # 재난 손절 −10: 저가 89 · 종가 97 → 비관판만 90 에 청산
    b2 = _b([95, 99], [101, 100], [89, 98], [97, 99])
    assert VO.outcome(b2, 0, 100.0, -5.0, "C", "pes", "close") == (90.0, "DISASTER_STOP", 0)
    assert VO.outcome(b2, 0, 100.0, -5.0, "C", "opt", "close") == (97.0, "CLOSE", 0)
