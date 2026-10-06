"""환헤지 항목의 금리차 뺀 판 — 계열 정의 · 재현 관문 · 성적표 대체판 붙이기."""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
for _p in (os.path.join(_ROOT, "tools"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import global_alloc_b as GB  # noqa: E402
from replay import gold_alloc as A  # noqa: E402
from replay import hedge_nocarry as H  # noqa: E402
from replay import scoreboard as SB  # noqa: E402


def _toy(n=300, seed=1):
    rng = np.random.default_rng(seed)
    lret = rng.normal(0.0004, 0.012, n)
    carry = np.full(n, 0.02 / 365)                # 한국 − 현지 = 연 2%
    cash = np.full(n, 0.035 / 365)                # 한국 3개월
    hret = lret + carry
    fx = rng.normal(0, 0.006, n)
    ret = (1 + lret) * (1 + fx) - 1
    dt = np.full(n, 1 / 365)
    return lret, ret, hret, cash, dt, carry


def test_lev2_with_carry_is_the_original_formula():
    lret, ret, hret, cash, dt, _ = _toy()
    np.testing.assert_array_equal(H.lev2_hedged(lret, hret, cash, dt, 0.008, carry=True),
                                  A.lev2(lret, ret, hret, cash, dt, "H", 0.008))


def test_lev2_nocarry_drops_only_the_carry_term():
    lret, ret, hret, cash, dt, carry = _toy()
    a = H.lev2_hedged(lret, hret, cash, dt, 0.008, carry=True)
    b = H.lev2_hedged(lret, hret, cash, dt, 0.008, carry=False)
    np.testing.assert_allclose((a - b)[1:], carry[1:], atol=1e-15)          # 차이 = 금리차 항 하나
    rf = cash - carry                                                        # 현지 조달금리는 그대로
    np.testing.assert_allclose(b[1:], (2 * lret - rf - 0.008 * dt)[1:], atol=1e-15)
    assert b[0] == 0.0 and b.min() >= -1.0


def test_lev2_nocarry_keeps_the_minus_100_floor():
    lret, ret, hret, cash, dt, _ = _toy(5)
    lret = lret.copy()
    lret[2] = -0.7
    assert H.lev2_hedged(lret, lret + 0.0001, cash, dt, 0.008, carry=False)[2] == -1.0


def test_carry_of_is_hret_minus_lret():
    lret, _, hret, _, _, carry = _toy()
    np.testing.assert_allclose(H.carry_of(lret, hret), carry, atol=1e-15)


def test_repro_gate_tolerances():
    v = np.cumprod(np.r_[1.0, np.full(9, 1.01)]) * 3.0
    cum = v / v[0]
    assert H.repro_ok(v, cum)
    assert H.repro_ok(v, np.round(cum, 8))                                   # 소수 8자리 반올림한 파일
    assert not H.repro_ok(v, cum * (1 + 1e-6))
    assert not H.repro_ok(v, cum[:-1])                                      # 길이 다르면 실패


def test_gb_nocarry_swaps_only_hedged_columns():
    n = 40
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(3)
    df = pd.DataFrame(index=idx)
    for a in GB.RISKY:
        lr = rng.normal(0, 0.01, n)
        df[f"{a}_lret"] = lr
        df[f"{a}_hret"] = lr + 0.0001
        df[f"{a}_ret"] = lr + rng.normal(0, 0.005, n)
    df["CASH_ret"] = 0.0001
    m = GB.load(df, "H", hedged=True)
    m2 = H.gb_nocarry(m, df, one_x=True, lev=True)
    for a in GB.RISKY:
        j = GB.COLS.index(a)
        if a in H.G.HEDGEABLE:
            np.testing.assert_allclose(m2.ret[1:, j], df[f"{a}_lret"].to_numpy()[1:])
            jl = GB.COLS.index("L" + a)
            np.testing.assert_allclose((m.ret - m2.ret)[1:, jl], 0.0001, atol=1e-15)
        else:
            np.testing.assert_array_equal(m2.ret[:, j], m.ret[:, j])          # K200 · USD 그대로
    np.testing.assert_array_equal(m2.ret[:, GB.I_CASH], m.ret[:, GB.I_CASH])
    assert m.ret is not m2.ret                                               # 원 시장은 안 바뀐다


def test_attach_alts_moves_nc_rows_onto_base_rows():
    rows = [{"id": "OL_SPX_H", "metrics": {"cagr": 0.18}}, {"id": "SPX", "metrics": {}}]
    alts = [{"id": "OL_SPX_H__NC", "name": "x · 금리차 제외", "source": "s", "metrics": {"cagr": 0.155}, "curves": {}},
            {"id": "NOPE__NC", "name": "n", "source": "s", "metrics": {}, "curves": {}}]
    warn = SB.attach_alts(rows, alts)
    assert rows[0]["alt_nocarry"]["metrics"]["cagr"] == 0.155 and rows[0]["alt_nocarry"]["judged"] is False
    assert "alt_nocarry" not in rows[1] and len(warn) == 1 and "NOPE__NC" in warn[0]


_SBJ = os.path.join(_ROOT, H.SB_JSON)
_RES = os.path.join(_ROOT, H.OUT_REL, "result.json")


@pytest.mark.skipif(not os.path.exists(_RES), reason="hedge_nocarry result.json 없음")
def test_recorded_gate_passed_for_all_items():
    res = json.load(open(_RES))
    assert res["gate_fail"] == [] and res["n"] == len(res["gate"]) >= 29
    for k, g in res["gate"].items():
        assert g["ok"], k
        assert g["max_rel_err"] < H.REPRO_TOL or g["max_abs_err"] <= H.ROUND_TOL, k
    for k, s in res["summary"].items():
        assert s["cagr_nc"] < s["cagr_orig"], k                             # 한국 금리 > 현지 금리였던 30년 — 금리차 빼면 낮아진다


@pytest.mark.skipif(not os.path.exists(_SBJ), reason="scoreboard.json 없음")
def test_scoreboard_rows_carry_alt_and_nc_rows_are_not_counted():
    d = json.load(open(_SBJ))
    ids = [r["id"] for r in d["rows"]]
    assert not any(i.endswith("__NC") for i in ids)
    alt = [r for r in d["rows"] if "alt_nocarry" in r]
    assert len(alt) >= 29
    for r in alt:
        a = r["alt_nocarry"]
        assert a["id"] == r["id"] + "__NC" and a["judged"] is False
        assert set(a["metrics"]) >= {"cagr", "mdd", "yearly"} and a["curves"]["month_end"]
        assert r["status"] in SB.STATUSES                                    # 원판 판정 그대로
