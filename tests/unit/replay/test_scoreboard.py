"""30년 전략 성적표 — 지표 계산 손계산 대조(CAGR · 낙폭 · 회복 · 샤프 · 소르티노 · 연도 · 울서 · 12개월)."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay import scoreboard as S  # noqa: E402
from replay import scoreboard_books as SB  # noqa: E402


def _rf(dates, monthly=0.0):
    return pd.Series(np.ones(len(dates)), index=pd.DatetimeIndex(dates)) if monthly == 0 else None


def test_cagr_hand():
    d0, d1 = pd.Timestamp("2000-01-01"), pd.Timestamp("2004-01-01")      # 1,461일 = 4.0 년(365.25)
    assert S.cagr(100.0, 200.0, d0, d1) == pytest.approx(2 ** 0.25 - 1, abs=1e-12)
    assert S.cagr(100.0, 0.0, d0, d1) == -1.0


def test_max_drawdown_dates_and_recovery():
    dates = pd.DatetimeIndex(["2001-01-01", "2001-02-01", "2001-03-01", "2001-04-01", "2001-05-01", "2001-06-01"])
    v = np.array([100, 120, 90, 60, 100, 125], float)
    md = S.max_drawdown(dates, v)
    assert md["mdd"] == pytest.approx(60 / 120 - 1)                     # −50%
    assert (md["peak"], md["trough"], md["recovery"]) == ("2001-02-01", "2001-04-01", "2001-06-01")
    md2 = S.max_drawdown(dates[:5], v[:5])
    assert md2["recovery"] is None                                       # 100 < 120 — 미회복


def test_longest_underwater_ongoing_and_closed():
    dates = pd.DatetimeIndex(["2001-01-01", "2001-01-11", "2001-01-21", "2001-02-10", "2001-03-12"])
    v = np.array([100, 90, 101, 95, 99], float)
    uw = S.longest_underwater(dates, v)
    # 닫힌 구간 01-01→01-21 = 20일, 열린 구간 01-21→03-12 = 50일(끝까지 미회복)
    assert uw == {"days": 50, "ongoing": True, "from": "2001-01-21"}
    uw2 = S.longest_underwater(dates[:3], v[:3])
    assert uw2 == {"days": 20, "ongoing": False, "from": "2001-01-01"}


def test_ulcer_hand():
    v = np.array([100, 90, 100, 80], float)                              # 낙폭 0, −10, 0, −20 %
    assert S.ulcer_index(v) == pytest.approx(math.sqrt((0 + 100 + 0 + 400) / 4))


def test_sharpe_sortino_hand():
    r = np.array([0.02, -0.01, 0.03, -0.02])
    rf = np.array([0.0, 0.0, 0.0, 0.0])
    sh, so = S.sharpe_sortino(r, rf)
    mean = 0.005
    sd = np.std(r, ddof=1)
    assert sh == pytest.approx(mean / sd * math.sqrt(12))
    down = math.sqrt((0.01 ** 2 + 0.02 ** 2) / 4) * math.sqrt(12)       # 하방 편차 — 전체 개수로 나눈다
    assert so == pytest.approx(mean * 12 / down)


def test_sharpe_uses_excess_over_rf():
    r = np.array([0.02, 0.01, 0.03, 0.00])
    sh0, _ = S.sharpe_sortino(r, np.zeros(4))
    sh1, _ = S.sharpe_sortino(r, np.full(4, 0.01))
    assert sh1 < sh0
    assert sh1 == pytest.approx(0.005 / np.std(r - 0.01, ddof=1) * math.sqrt(12))


def test_month_points_and_yearly():
    dates = pd.DatetimeIndex(["2000-12-28", "2001-01-15", "2001-01-31", "2001-02-27", "2001-12-28",
                              "2002-06-28", "2002-12-27"])
    v = np.array([100, 101, 110, 99, 121, 130, 133.1])
    me = S.month_points(dates, v, cutoff=pd.Period("2002-12", "M"))
    assert list(me.index.strftime("%Y-%m-%d")) == ["2000-12-28", "2001-01-31", "2001-02-27", "2001-12-28",
                                                   "2002-06-28", "2002-12-27"]
    yr = S.yearly_returns(dates, v)
    assert yr[2001]["ret"] == pytest.approx(0.21)
    assert yr[2002]["ret"] == pytest.approx(0.10)
    assert yr[2001]["full"] and yr[2002]["full"]
    assert 2000 not in yr                                                # 시작점 하나뿐인 해는 없다


def test_compute_metrics_constant_growth():
    """매달 1% 씩 오르는 곡선 — CAGR · 낙폭 0 · 최악 12개월 = 1.01¹² − 1 · 최고/최악 해."""
    dates = pd.DatetimeIndex(pd.date_range("1999-12-31", periods=37, freq="ME"))
    v = 1.01 ** np.arange(37)
    rf = pd.Series(np.ones(37), index=dates)
    m = S.compute_metrics(dates, v, rf, bench=pd.Series(v, index=dates))
    assert m["cagr"] == pytest.approx(v[-1] ** (365.25 / (dates[-1] - dates[0]).days) - 1)
    assert m["mdd"] == 0.0
    assert m["worst_12m"] == pytest.approx(1.01 ** 12 - 1)
    assert m["best_year"]["ret"] == pytest.approx(1.01 ** 12 - 1)
    assert m["pos_year_ratio"] == 1.0
    assert m["final_value_10m"] == pytest.approx(1e7 * 1.01 ** 36)
    assert m["excess_vs_k200"] == pytest.approx(0.0)
    assert math.isnan(m["sharpe"]) and math.isnan(m["sortino"])     # 초과수익 변동 0 — 비율을 내지 않는다


def test_compute_metrics_sortino_matches_manual_on_monthly():
    dates = pd.DatetimeIndex(["2000-12-29", "2001-01-31", "2001-02-28", "2001-03-30", "2001-04-30"])
    r = np.array([0.05, -0.04, 0.02, -0.01])
    v = 100 * np.cumprod(np.r_[1.0, 1 + r])
    rf = pd.Series(1.001 ** np.arange(5), index=dates)                  # 월 0.1%
    m = S.compute_metrics(dates, v, rf)
    ex = r - 0.001
    assert m["sharpe"] == pytest.approx(ex.mean() / ex.std(ddof=1) * math.sqrt(12))
    assert m["sortino"] == pytest.approx(ex.mean() * 12 / (math.sqrt(np.mean(np.minimum(ex, 0) ** 2)) * math.sqrt(12)))
    assert m["vol"] == pytest.approx(r.std(ddof=1) * math.sqrt(12))


def test_corr_and_excess_against_bench_window():
    dates = pd.DatetimeIndex(pd.date_range("2000-01-31", periods=30, freq="ME"))
    rng = np.random.default_rng(1)
    rb = rng.normal(0.01, 0.05, 29)
    b = 100 * np.cumprod(np.r_[1.0, 1 + rb])
    v = 50 * np.cumprod(np.r_[1.0, 1 + 0.5 * rb + 0.002])
    rf = pd.Series(np.ones(30), index=dates)
    bench = pd.Series(b, index=dates)
    m = S.compute_metrics(dates[5:], v[5:], rf, bench)
    assert m["corr_k200"] == pytest.approx(np.corrcoef(np.diff(v[5:]) / v[5:-1], np.diff(b[5:]) / b[5:-1])[0, 1])
    k = S.cagr(b[5], b[-1], dates[5], dates[-1])
    assert m["excess_vs_k200"] == pytest.approx(m["cagr"] - k)


def test_books_pack_picks_lower_median_seed():
    dates = pd.DatetimeIndex(pd.bdate_range("2001-01-02", periods=5))
    runs = [(s, np.full(5, 100.0 + s * (1 if s % 2 else -1))) for s in range(16)]
    p = SB.pack("x", dates, runs, 100.0, source="t")
    finals = sorted(100.0 + s * (1 if s % 2 else -1) for s in range(16))
    assert p["equity"][-1] == finals[7]
    assert p["equity"][0] == 100.0 and p["dates"][0] == "2001-01-01"
    assert len(p["dates"]) == len(p["equity"]) == 6


def test_registry_ids_unique_and_status_vocab():
    ids = [e.id for e in S.REGISTRY]
    assert len(ids) == len(set(ids))
    assert all(e.status in S.STATUSES for e in S.REGISTRY)


def test_books_npz_roundtrip(tmp_path):
    dates = pd.DatetimeIndex(pd.bdate_range("2001-01-02", periods=4))
    p = SB.pack("zz", dates, [(0, np.array([101.0, 99.0, 103.0, 104.0]))], 100.0, source="t", extra={"fills_per_year": 3})
    SB.save(str(tmp_path), p)
    c = S.load_books(str(tmp_path))["zz"]
    assert list(c.value) == [100.0, 101.0, 99.0, 103.0, 104.0]
    assert c.dates[0] == pd.Timestamp("2001-01-01") and c.extra["fills_per_year"] == 3


def test_won_format():
    assert S._won(166_940_000) == "1억 6,694만"
    assert S._won(22_670_000) == "2,267만"


def _ext_doc(tmp_path, entries):
    import json
    p = tmp_path / "scoreboard_entries.json"
    p.write_text(json.dumps({"source": "t", "entries": entries}, ensure_ascii=False))
    return str(p)


def test_external_missing_file_is_skipped(tmp_path):
    rows, warn = S.load_external([str(tmp_path / "없음.json")])
    assert rows == [] and len(warn) == 1


def test_external_entry_loaded_and_validated(tmp_path):
    good = {"id": "X1", "name": "x", "desc": "d", "period": ["2000-12-29", "2001-02-28"],
            "curve": {"dates": ["2000-12-29", "2001-01-31", "2001-02-28"], "cum": [1.0, 1.1, 1.21]},
            "yearly": {"2001": 0.21}, "status": "없는상태"}
    dup = dict(good, id="K200")
    bad = {"id": "X2", "name": "x", "desc": "d", "period": ["2000-12-29", "2001-01-31"], "curve": {"dates": ["2000-12-29"]}}
    rows, warn = S.load_external([_ext_doc(tmp_path, [good, dup, bad])], {"K200"})
    assert [r["entry"].id for r in rows] == ["X1"]
    r = rows[0]
    assert r["entry"].group == "external" and r["entry"].status == "참고"
    assert r["curve"].extra["curve_freq"] == "월말" and r["curve"].value[-1] == 1.21
    assert len(warn) == 2                                               # 중복 id · 필수 칸 없음
