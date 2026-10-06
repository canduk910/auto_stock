"""donchian_swing 30년 재검증(2026-10-06) — ``donchian_y30``·``donchian_y30_data`` 단위 테스트.

5년 판 식과 같은 자리(명목 문턱이면 신호가 같다) · 새로 넣은 층(시대 중립 거래대금 · 편입 근사 · 가격제한폭 잠김 ·
위반 표시 행 · 시기별 비용)이 뜻대로 움직이는지 본다. 합성 입력 + 보관소 meta CSV(비용·제한폭 표)만 읽는다.
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

from replay.strategies import donchian_kk as DK  # noqa: E402
from replay.strategies import donchian_y30 as Y  # noqa: E402
from replay.strategies import donchian_y30_data as YD  # noqa: E402

pytestmark = pytest.mark.unit
_HAS_META = os.path.exists(os.path.join(YD.LONG, "meta/regime_costs.csv"))


def _series(n=400, seed=0):
    rng = np.random.default_rng(seed)
    c = 10000 * np.exp(np.cumsum(rng.normal(0.003, 0.02, n)))
    o = c * (1 + rng.normal(0, 0.005, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.01, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.01, n)))
    vol = rng.integers(1_000_000, 5_000_000, n).astype(float)
    vol[rng.random(n) < 0.15] *= 4
    return {"di": np.arange(n), "o": o, "h": h, "l": l, "c": c, "c_raw": c, "raw": np.ones(n), "vol": vol,
            "tv": np.full(n, 300e8), "notrade": np.zeros(n, bool), "mem": np.ones(n, bool),
            "tvok": np.ones(n, bool), "tv200": np.ones(n, bool), "jump": np.zeros(n, bool), "lim": np.full(n, 0.3)}


def test_grid_sizes_and_invariant():
    assert (len(Y.GRID_A), len(Y.GRID_B), len(Y.GRID_C)) == (24, 81, 15)
    assert Y.ENTRY0 in Y.GRID_A and Y.EXIT0 in Y.GRID_B and Y.ACCT0 in Y.GRID_C
    for g in Y.GRID_C:
        assert g["slots"][0] * g["slots"][1] <= 1.0 + 1e-12


@pytest.mark.parametrize("seed", range(4))
def test_nominal_mode_equals_five_year_features(seed):
    b = _series(seed=seed)
    f0 = DK.features(b, b["mem"], turnover="cv")
    f1 = Y.features_y30(b, tv_mode="nominal")
    assert f0["cond"].any() and np.array_equal(f0["cond"], f1["cond"])
    assert np.array_equal(np.nan_to_num(f0["chan10"]), np.nan_to_num(f1["chan10"]))


def test_pct_mode_uses_tvok_only():
    b = _series(seed=1)
    b["tv"] = np.full(len(b["c"]), 1e8)                    # 명목 200억 미달이어도
    assert Y.features_y30(b, tv_mode="pct")["cond"].any()   # 그날 상위 p* 이면 통과
    b["tvok"][:] = False
    assert not Y.features_y30(b, tv_mode="pct")["cond"].any()


def test_jump_block_window():
    j = np.zeros(200, bool)
    j[100] = True
    jb = Y.jump_block(j, 62)
    assert jb[99] and jb[100] and jb[162] and not jb[163] and not jb[98]   # 신호봉 99 → 진입봉 100 이 표시 행


def test_jump_blocks_signals_and_exits_held_position():
    b = _series(seed=2)
    f = Y.features_y30(b)
    j = int(np.nonzero(f["cond"])[0][0])
    b2 = dict(b, jump=b["jump"].copy())
    b2["jump"][j + 1] = True
    assert not Y.features_y30(b2)["cond"][j]
    sig = DK.Sig("000000", j + 1, j + 1, float(b["o"][j + 1]), float(b["o"][j + 1]), float(f["atr"][j]),
                 float(f["prior_high"][j]), 1.0)
    b3 = dict(b, jump=b["jump"].copy())
    b3["jump"][j + 3] = True
    p = Y.run_path(sig, b3, f, 10 ** 9, kk=Y.kk_of(Y.EXIT0))
    if p.exit_gd is not None and p.exit_gd >= j + 3:
        assert p.exit_reason == "JUMP" and p.exit_gd == j + 3 and p.exit_px == pytest.approx(b3["c"][j + 2])


def test_locked_limit_down_defers_exit():
    n = 30
    b = {"di": np.arange(n), "o": np.full(n, 100.0), "h": np.full(n, 101.0), "l": np.full(n, 99.0),
         "c": np.full(n, 100.0), "raw": np.ones(n), "notrade": np.zeros(n, bool), "jump": np.zeros(n, bool),
         "lim": np.full(n, 0.15)}
    # 10번 봉 하한가 잠김(85 · 고가 = 저가), 11번 봉 시가 80
    b["o"][10] = b["h"][10] = b["l"][10] = b["c"][10] = 85.0
    b["o"][11:], b["h"][11:], b["l"][11:], b["c"][11:] = 80.0, 81.0, 79.0, 80.0
    f = {"chan10": np.full(n, np.nan), "atr": np.full(n, 1.0)}
    sig = DK.Sig("000000", 2, 2, 100.0, 100.0, 1.0, 100.0, 1.0)
    kk = Y.kk_of(Y.EXIT0)
    assert Y.locked_down(b, 10) and not Y.locked_down(b, 11)
    p = Y.run_path(sig, b, f, 10 ** 9, kk=kk)
    assert p.exit_gd == 11 and p.exit_px == 80.0 and p.exit_reason == "STOP_LOSS"
    # 잠김이 아니면(시가 95 · 고가 ≠ 저가) 10번 봉 장중에 손절선(92)에서 판다
    b["o"][10], b["h"][10] = 95.0, 96.0
    p2 = Y.run_path(sig, b, f, 10 ** 9, kk=kk)
    assert p2.exit_gd == 10 and p2.exit_px == pytest.approx(92.0)


def test_mu_apply_modes():
    s = [DK.Sig("a", 1, 1, 1.0, 1.0, 1.0, 1.0, m) for m in (1.0, 0.75, 0.5)]
    assert [x.m for x in Y.mu_apply(s, "cur")] == [1.0, 0.75, 0.5]
    assert [x.m for x in Y.mu_apply(s, "m1")] == [1.0]
    assert [x.m for x in Y.mu_apply(s, "off")] == [1.0, 1.0, 1.0]
    assert [x.m for x in s] == [1.0, 0.75, 0.5]                # 원본 불변


def test_tv_top_flags_and_member_flags():
    d = pd.Timestamp("2000-01-04")
    rows = [{"ticker": f"{i:05d}0", "name": f"N{i}", "bas_dd": d, "mktcap": 1000 - i,
             "market": "KOSDAQ GLOBAL" if i < 3 else "KOSDAQ", "trade_value": float(1000 - i)} for i in range(200)]
    rows.append({"ticker": "Q0001K", "name": "영숫자", "bas_dd": d, "mktcap": 1e9, "market": "KOSPI",
                 "trade_value": 1e12})
    df = pd.DataFrame(rows)
    tv = YD.tv_top_flags(df, 0.1)
    assert tv[:20].all() and not tv[20:200].any() and not tv[200]        # 6자리 숫자 200 중 상위 10%
    mem = YD.member_flags(df)
    assert mem[:150].all() and not mem[150:].any()                       # KOSDAQ GLOBAL 도 KOSDAQ 순위에


@pytest.mark.skipif(not _HAS_META, reason="보관소 meta 없음")
def test_era_costs_and_limits():
    cal = pd.DatetimeIndex(["1997-03-03", "2003-05-02", "2025-06-02", "2026-03-03"])
    c = Y.Costs(cal)
    assert [round(c.rt(i, i), 4) for i in range(4)] == [0.013, 0.005, 0.0018, 0.0023]
    f = Y.Costs(cal, 0.0038)
    assert f.rt(0, 3) == pytest.approx(0.0038)
    lim = YD.limit_for(pd.Series(pd.to_datetime(["1997-01-03", "1998-06-01", "2005-01-03", "2016-01-04"])),
                       pd.Series(["KOSPI", "KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"]))
    assert list(np.round(lim, 2)) == [0.08, 0.12, 0.12, 0.30]
