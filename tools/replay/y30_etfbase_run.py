#!/usr/bin/env python3
"""30년 재검증 — etf_trend · 바탕 층 · 60일 고점 −10% 진단. 사전 등록 = ``prereg.md``(sha 동결본, 같은 폴더).

연구 전용. 순서 = 관문(§6) → 바탕 층 A · B → etf_trend A · B-a · B-b → −10% 진단 → result.json.

실행: python tools/replay/y30_etfbase_run.py [--out PATH] [--only base|etf|dd|gate]
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import base_layer as BL  # noqa: E402
from replay import y30_etfbase_data as YD  # noqa: E402
from replay.audit import bars as BR  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402

OUT_DIR = os.path.join(C.REPO, "_workspace/analysis/strategy_30y_20261006/etf_base")
T_WIN = ("1997-01-02", "2012-12-28")
T_SUB = (("1997-01-02", "2001-12-28"), ("2002-01-02", "2006-12-28"), ("2007-01-02", "2012-12-28"))
V_WIN = ("2013-01-02", "2020-12-30")
H_WIN = ("2021-01-04", "2026-10-02")
ERAS = (("1997-01-02", "2001-12-31"), ("2002-01-01", "2006-12-31"), ("2007-01-01", "2011-12-31"),
        ("2012-01-01", "2016-12-31"), ("2017-01-01", "2021-12-31"), ("2022-01-01", "2026-10-02"))
VP_WIN = ("2015-01-02", "2020-12-30")          # etf_trend 판정 V'
F_WIN = ("2015-01-02", "2020-09-29")           # etf_trend 바깥 표본(5년 연구 이전)
PRE_WIN = ("2003-01-02", "2014-12-30")         # etf_trend 판정 제외 구간(보고)
VP_SUB = (("2015-01-02", "2016-12-30"), ("2017-01-02", "2018-12-28"), ("2019-01-02", "2020-12-30"))
G5 = {"T": ("2020-10-05", "2023-09-29"), "V": ("2023-10-04", "2025-10-02"), "H": ("2025-10-10", "2026-09-23")}
G5_REF = {"B0": {"T": 0.0401, "V": 0.2701, "H": 1.3721}, "ref": {"T": 0.0539, "V": 0.1763, "H": 1.2166}}
BLOCK = 40
N_BOOT_T = 2000
N_BOOT_V = 20000
N_COMBOS = 133
BONF_BASE = 0.10 / N_COMBOS
BONF_ETF = 0.10 / 108
A_CANDS = {
    "A1": {"fam": "B3", "base": "hold", "X": 0.15, "a": 0.5, "Y": "Y2", "park": "short"},
    "A2": {"fam": "B1", "park": "cash", "R": "D", "band": 0.0},
    "A3": {"fam": "B1", "park": "short", "R": "W", "band": 0.5},
    "A4": {"fam": "B3", "base": "hold", "X": 0.10, "a": 0.0, "Y": "Y1", "park": "short"},
    "A5": {"fam": "B2", "def": "usdktb", "R": "M", "band": 0.5},
}


# ── 공통: 계좌 · 연율 · 부트스트랩 ────────────────────────────────────────

def years_cal(cal, g0: int, g1: int) -> float:
    """구간 달력 연수 — 첫 봉 전날부터 끝 봉까지(봉 1개 = 하루 이상)."""
    return max((cal[g1] - cal[g0]).days + 1, 1) / 365.25


def run_account30(W: np.ndarray, O: np.ndarray, Cl: np.ndarray, g0: int, g1: int, cs_day: np.ndarray, cal,
                  budget: float = float(C.BUDGET_C7), ann: str = "cal") -> dict:
    """``BL.run_account`` 와 같은 집행 — 비용만 날마다(``cs_day`` = 한쪽 비율), 연율은 달력(``ann="cal"``) 또는 252봉."""
    na = W.shape[1]
    cash, sh = float(budget), np.zeros(na, dtype=np.int64)
    eqs, stock_share = [], []
    orders, paid, traded = 0, 0.0, 0.0
    prev = None
    for g in range(g0, g1 + 1):
        w = W[g]
        o = O[g]
        cs = float(cs_day[g])
        chg = np.ones(na, dtype=bool) if prev is None else ~np.isclose(w, prev, atol=1e-12)
        if chg.any():
            eq_o = cash + float((sh * np.nan_to_num(o)).sum())
            want = sh.copy()
            for i in np.where(chg)[0]:
                want[i] = int((eq_o * w[i]) // (o[i] * (1 + cs))) if w[i] > 0 else 0
            for i in np.where(want < sh)[0]:
                q = int(sh[i] - want[i])
                amt = q * o[i]
                cash += amt - amt * cs
                paid += amt * cs
                traded += amt
                sh[i] = want[i]
                orders += 1
            for i in np.where(want > sh)[0]:
                q = int(want[i] - sh[i])
                q = min(q, int(cash // (o[i] * (1 + cs))))
                if q <= 0:
                    continue
                amt = q * o[i]
                cash -= amt + amt * cs
                paid += amt * cs
                traded += amt
                sh[i] += q
                orders += 1
            prev = w.copy()
        val = sh * np.nan_to_num(Cl[g])
        eq = cash + float(val.sum())
        eqs.append(eq)
        stock_share.append(float(val[0] + val[1]) / eq)
    eq = np.array(eqs)
    yrs = years_cal(cal, g0, g1) if ann == "cal" else len(eq) / 252.0
    cg = float((eq[-1] / budget) ** (1.0 / yrs) - 1)
    e = np.r_[budget, eq]
    md = float((e / np.maximum.accumulate(e) - 1).min())
    return {"equity": eq, "cagr": cg, "mdd": md, "mar": cg / abs(md) if md < 0 else float("nan"),
            "orders_per_year": orders / yrs, "cost_per_year_pct": float(paid / eq.mean() / yrs * 100),
            "turnover_per_year": float(traded / eq.mean() / yrs), "avg_stock_share": float(np.mean(stock_share)),
            "days": len(eq), "years": yrs}


def mar_paths30(r: np.ndarray, idx: np.ndarray, yrs: float) -> np.ndarray:
    rr = r[idx]
    path = np.cumprod(1 + rr, axis=1)
    cg = path[:, -1] ** (1.0 / yrs) - 1
    e = np.concatenate([np.ones((path.shape[0], 1)), path], axis=1)
    md = (e / np.maximum.accumulate(e, axis=1) - 1).min(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(md < 0, cg / np.abs(md), np.nan)


def mar_diff_boot30(rA, rB, reps: int, yrs: float, chunk: int = 2000, seed: int = C.BOOT_SEED) -> np.ndarray:
    """짝 원형 블록 — 같은 색인으로 MAR(A) − MAR(B). 색인 전체를 한 번에 만들고(씨앗 고정) 덩어리로 잰다."""
    idx = BL.boot_index(len(rA), reps, BLOCK, seed)
    out = np.empty(reps)
    for s in range(0, reps, chunk):
        ii = idx[s:s + chunk]
        out[s:s + chunk] = mar_paths30(rA, ii, yrs) - mar_paths30(rB, ii, yrs)
    return out


def win_idx(cal, win) -> tuple:
    return int(cal.searchsorted(pd.Timestamp(win[0]))), int(cal.searchsorted(pd.Timestamp(win[1]), side="right")) - 1


def _s(r: dict) -> dict:
    return {k: v for k, v in r.items() if k != "equity"}


def q(a, p):
    return float(np.nanquantile(a, p))


# ── 바탕 층 ─────────────────────────────────────────────────────────────

def base_inputs(div_report: bool = False) -> dict:
    A = YD.load_base_assets(div_report=div_report)
    cal = A["cal"]
    c = A["Cl"][:, 0]
    m = YD.market_unit(A["c_idx"])
    dd = BL.drawdown60(A["c_idx"])
    costs = YD.load_costs()
    cs = {k: YD.cost_rt_on(cal, costs, k) / 2 for k in ("table", "const", "fee")}
    return {**A, "m": m, "dd": dd, "c": c, "cs": cs}


def m1_only_path(cal, m) -> np.ndarray:
    """기준선 「m = 1 일 때만 전액, 아니면 현금」(5년 etf_trend 기준선 B3)."""
    msess = np.r_[np.nan, m[:-1]]
    msess = np.where(np.isfinite(msess), msess, 1.0)
    W = np.zeros((len(cal), len(YD.ASSETS)))
    W[:, 0] = (msess >= 1.0).astype(float)
    return W


def base_gate(B: dict) -> dict:
    """관문 1 — 5년 창 · 한쪽 0.19% · 252봉 연율로 B0 · 참고 B1 이 5년 연구 값 ±1%p."""
    cal, O, Cl = B["cal"], B["O"], B["Cl"]
    const = B["cs"]["const"]
    W0 = BL.weights_path({"fam": "B0"}, cal, B["m"], B["dd"], B["c"])
    Wr = BL.weights_path(A_CANDS["A2"], cal, B["m"], B["dd"], B["c"])
    out = {}
    for nm, W in (("B0", W0), ("ref", Wr)):
        for k, win in G5.items():
            g0, g1 = win_idx(cal, win)
            r = run_account30(W, O, Cl, g0, g1, const, cal, ann="252")
            out[f"{nm}|{k}"] = {"cagr": r["cagr"], "ref": G5_REF[nm][k], "diff": r["cagr"] - G5_REF[nm][k]}
    out["max_abs_diff"] = max(abs(v["diff"]) for v in out.values() if isinstance(v, dict))
    out["pass"] = bool(out["max_abs_diff"] <= 0.01)
    return out


def base_run(B: dict) -> dict:  # noqa: C901
    cal, O, Cl, m, dd, c = B["cal"], B["O"], B["Cl"], B["m"], B["dd"], B["c"]
    cs = B["cs"]["table"]
    G = BL.grid()
    assert len(G) == N_COMBOS
    wins = {"T": win_idx(cal, T_WIN), "V": win_idx(cal, V_WIN), "H": win_idx(cal, H_WIN)}
    subs = [win_idx(cal, w) for w in T_SUB]
    eras = [win_idx(cal, w) for w in ERAS]
    paths = [BL.weights_path(cb, cal, m, dd, c) for cb in G]
    res = []
    for cb, W in zip(G, paths):
        row = {"combo": cb, "name": BL.name(cb), "W": W}
        for k, (g0, g1) in wins.items():
            row[k] = run_account30(W, O, Cl, g0, g1, cs, cal)
        row["T_sub"] = [run_account30(W, O, Cl, g0, g1, cs, cal) for g0, g1 in subs]
        res.append(row)
    b0 = res[0]
    assert b0["combo"]["fam"] == "B0"
    # T 선택
    gT0, gT1 = wins["T"]
    yT = years_cal(cal, gT0, gT1)
    idxT = BL.boot_index(b0["T"]["days"], N_BOOT_T, BLOCK, C.BOOT_SEED)
    rB0T = BL.daily_returns(b0["T"]["equity"])
    marB0 = mar_paths30(rB0T, idxT, yT)
    for row in res[1:]:
        row["robust_n"] = int(sum(s["mar"] > s0["mar"] for s, s0 in zip(row["T_sub"], b0["T_sub"])))
        row["robust"] = row["robust_n"] >= 2
        dif = mar_paths30(BL.daily_returns(row["T"]["equity"]), idxT, yT) - marB0
        row["T_boot"] = {"mean": float(np.nanmean(dif)), "lo90": q(dif, 0.05), "hi90": q(dif, 0.95)}
    cands = [r for r in res[1:] if r["robust"]]
    robust_none = not cands
    if robust_none:
        cands = res[1:]
    chosen = max(cands, key=lambda r: (r["T_boot"]["lo90"], -r["T"]["turnover_per_year"]))
    # V 판정
    gV0, gV1 = wins["V"]
    yV = years_cal(cal, gV0, gV1)
    rBV = BL.daily_returns(b0["V"]["equity"])
    difV = mar_diff_boot30(BL.daily_returns(chosen["V"]["equity"]), rBV, N_BOOT_V, yV)
    J1 = {"mar_chosen": chosen["V"]["mar"], "mar_b0": b0["V"]["mar"], "diff": chosen["V"]["mar"] - b0["V"]["mar"],
          "lo90": q(difV, 0.05), "hi90": q(difV, 0.95), "lo_bonf": q(difV, BONF_BASE),
          "p_le0": float(np.nanmean(difV <= 0))}
    J1["pass"] = bool(J1["diff"] > 0 and J1["lo90"] > 0)
    J1["pass_bonf"] = bool(J1["diff"] > 0 and J1["lo_bonf"] > 0)
    J2 = {"cagr_ge": bool(chosen["V"]["cagr"] >= b0["V"]["cagr"]), "mdd_shallower": bool(chosen["V"]["mdd"] > b0["V"]["mdd"])}
    J2["pass"] = J2["cagr_ge"] and J2["mdd_shallower"]
    Hs = {"mar_diff": chosen["H"]["mar"] - b0["H"]["mar"], "cagr_diff": chosen["H"]["cagr"] - b0["H"]["cagr"],
          "mdd_diff": chosen["H"]["mdd"] - b0["H"]["mdd"]}
    Hs["mar_sign_kept"] = bool(np.sign(Hs["mar_diff"]) == np.sign(J1["diff"]))
    # A 고정 후보 — T · V · H 짝 부트스트랩(2,000) + 시대표
    byname = {json.dumps(r["combo"], sort_keys=True): r for r in res}
    A = {}
    for an, cb in A_CANDS.items():
        r = byname[json.dumps(cb, sort_keys=True)]
        a = {"name": r["name"]}
        for k, (g0, g1) in wins.items():
            yy = years_cal(cal, g0, g1)
            d = mar_diff_boot30(BL.daily_returns(r[k]["equity"]), BL.daily_returns(b0[k]["equity"]), N_BOOT_T, yy)
            a[k] = {**_s(r[k]), "mar_diff": r[k]["mar"] - b0[k]["mar"], "lo90": q(d, 0.05), "hi90": q(d, 0.95)}
        sg = [np.sign(a[k]["mar_diff"]) for k in ("T", "V", "H")]
        a["persist_same_sign"] = bool(sg[0] == sg[1] == sg[2])
        a["T_sub_mar"] = [s["mar"] for s in r["T_sub"]]
        A[an] = a
    # 시대표 — B0 · A 후보 · 고른 판 · 참고(m=1 만)
    W_m1 = m1_only_path(cal, m)
    era_rows = {}
    for nm, W in [("B0", b0["W"]), ("chosen", chosen["W"]), ("m1_only", W_m1)] + \
                 [(an, byname[json.dumps(cb, sort_keys=True)]["W"]) for an, cb in A_CANDS.items()]:
        era_rows[nm] = [_s(run_account30(W, O, Cl, g0, g1, cs, cal)) for g0, g1 in eras]
    m1 = {k: _s(run_account30(W_m1, O, Cl, g0, g1, cs, cal)) for k, (g0, g1) in wins.items()}
    # 민감도 — 일정 0.38% · 수수료만
    sens = {}
    for ck in ("const", "fee"):
        for nm, W in [("B0", b0["W"]), ("chosen", chosen["W"])] + \
                     [(an, byname[json.dumps(cb, sort_keys=True)]["W"]) for an, cb in A_CANDS.items()]:
            sens[f"{ck}|{nm}"] = {k: _s(run_account30(W, O, Cl, g0, g1, B["cs"][ck], cal)) for k, (g0, g1) in wins.items()}
    # 묶음 최선(보고)
    fam_best = {}
    for f in ("B1", "B2", "B3", "B4"):
        rows = [r for r in res if r["combo"]["fam"] == f]
        rr = [r for r in rows if r["robust"]] or rows
        b = max(rr, key=lambda r: (r["T_boot"]["lo90"], -r["T"]["turnover_per_year"]))
        d = mar_diff_boot30(BL.daily_returns(b["V"]["equity"]), rBV, N_BOOT_T, yV)
        fam_best[f] = {"name": b["name"], "robust_n": b["robust_n"], "T_lo90": b["T_boot"]["lo90"],
                       "T": _s(b["T"]), "V": _s(b["V"]), "H": _s(b["H"]), "V_mar_diff": b["V"]["mar"] - b0["V"]["mar"],
                       "V_lo90": q(d, 0.05), "V_hi90": q(d, 0.95)}
    # 사후(보고) — V 에서 하한 > 0 인 조합 수(2,000회)
    post = {"n": 0, "n_lo_pos": 0, "n_mar_gt": 0, "lo_pos": []}
    for r in res[1:]:
        d = mar_diff_boot30(BL.daily_returns(r["V"]["equity"]), rBV, N_BOOT_T, yV)
        post["n"] += 1
        post["n_mar_gt"] += int(r["V"]["mar"] > b0["V"]["mar"])
        if q(d, 0.05) > 0:
            post["n_lo_pos"] += 1
            post["lo_pos"].append({"name": r["name"], "lo90": q(d, 0.05), "robust_n": r["robust_n"],
                                   "T_mar": r["T"]["mar"], "H_mar_diff": r["H"]["mar"] - b0["H"]["mar"]})
    x10 = [{"name": r["name"], "T": _s(r["T"]), "V": _s(r["V"]), "H": _s(r["H"]), "robust_n": r["robust_n"]}
           for r in res if r["combo"]["fam"] == "B3" and abs(r["combo"]["X"] - 0.10) < 1e-9]
    n_x10_beat_all = sum(1 for x in x10 if all(x[k]["mar"] > _s(b0[k])["mar"] for k in ("T", "V", "H")))
    top = sorted(res[1:], key=lambda r: (not r["robust"], -r["T_boot"]["lo90"]))

    def row_out(r):
        o = {"name": r["name"], "combo": r["combo"]}
        for k in ("T", "V", "H"):
            o[k] = _s(r[k])
        o["T_sub_mar"] = [s["mar"] for s in r["T_sub"]]
        for k in ("robust_n", "robust", "T_boot"):
            if k in r:
                o[k] = r[k]
        return o
    return {"n_combos": len(G), "n_robust": sum(r.get("robust", False) for r in res[1:]), "robust_none": robust_none,
            "B0": row_out(b0), "chosen": row_out(chosen), "J1": J1, "J2": J2, "H": Hs, "A": A,
            "eras": {"windows": [list(w) for w in ERAS], "rows": era_rows}, "m1_only": m1, "sens": sens,
            "family_best": fam_best, "posthoc_V": post, "b3_x10": x10, "n_x10_beat_b0_all3": n_x10_beat_all,
            "top10": [row_out(r) for r in top[:10]], "all": [row_out(r) for r in res],
            "chosen_W": chosen["W"], "b0_W": b0["W"]}


def base_div_report(chosen_combo: dict) -> dict:
    """보고판 — 2002-10 이전 069500 에 연 1.5% 배당. 신호(m · 낙폭)는 그대로 가격 지수로."""
    B = base_inputs(div_report=True)
    cal, O, Cl = B["cal"], B["O"], B["Cl"]
    Bp = base_inputs(div_report=False)
    out = {}
    for nm, cb in (("B0", {"fam": "B0"}), ("chosen", chosen_combo)):
        W = BL.weights_path(cb, cal, Bp["m"], Bp["dd"], Bp["c"])
        out[nm] = {k: _s(run_account30(W, O, Cl, *win_idx(cal, w), B["cs"]["table"], cal))
                   for k, w in (("T", T_WIN), ("V", V_WIN), ("H", H_WIN))}
    return out


# ── etf_trend ───────────────────────────────────────────────────────────

def etf_load() -> dict:
    from replay.audit import gate_c391b as GT
    from replay.strategies import etf_trend_b as EB
    c391 = GT.load_c391()
    cls, meta = GT.classify(c391)
    df = YD.load_etf_panel(cls)
    cal = pd.DatetimeIndex(sorted(df.bas_dd.unique()))
    bars = YD.etf_bars(df, cal)
    data = {t: EB.ticker_arrays(b) for t, b in bars.items()}
    k = data[YD.K200]
    mu = np.full(len(cal), np.nan)
    mu[k["ci"]] = YD.market_unit(k["c"])
    defl = YD.deflator(cal)
    lim = YD.price_limit_on(cal)
    tick_list = sorted(data)
    col = {t: i for i, t in enumerate(tick_list)}
    ret = np.full((len(cal), len(tick_list)), np.nan)
    for t, d in data.items():
        cc = np.full(len(cal), np.nan)
        cc[d["ci"]] = d["c"]
        ret[1:, col[t]] = cc[1:] / cc[:-1] - 1
    costs = YD.load_costs()
    cost_rt = {kk: YD.cost_rt_on(cal, costs, kk) for kk in ("table", "const", "fee")}
    # 이상 봉 · 잠김 봉
    anom, lock = {}, {}
    for t, d in data.items():
        ci = d["ci"]
        cp = np.r_[np.nan, d["c"][:-1]]
        contig = np.r_[False, ci[1:] == ci[:-1] + 1]
        chg = d["c"] / cp - 1
        anom[t] = contig & (np.abs(chg) > lim[ci] + 0.01)
        lock[t] = contig & (d["o"] == d["h"]) & (d["h"] == d["l"]) & (d["l"] == d["c"]) & (np.abs(chg) >= lim[ci] - 0.01)
    return {"cls": cls, "meta": meta, "cal": cal, "data": {t: d for t, d in data.items() if cls.get(t)},
            "bars": bars, "mu": mu, "defl": defl, "corr": EB.Corr(ret, col), "cost_rt": cost_rt,
            "anom": anom, "lock": lock, "k200": k}


def gen_signals30(data: dict, mu: np.ndarray, L: int, thr: np.ndarray, anom: dict, lock: dict) -> tuple:
    """``etf_trend_opt.gen_signals`` 의 진입 조건 — 거래대금 문턱만 날짜별(``thr[ci]``), 시총 문턱 없음.

    진입봉 잠김이면 진입하지 않는다. 반환 (신호 목록, 진입봉 잠김으로 뺀 수).
    """
    from replay.audit import indicators as IND
    from replay.strategies import etf_trend_b as EB
    out, n_lock = [], 0
    for t, d in data.items():
        hpL = d["hi_prev20"] if L == 20 else d.setdefault(f"hi_prev{L}", IND.prior_max(d["h"], L))
        n = len(d["c"])
        e60 = d["e60"]
        for j in range(EB.MIN_BARS - 1, n - 1):
            ci = d["ci"][j]
            if d["ci"][j + 1] != ci + 1:
                continue
            c = d["c"][j]
            a20 = d["atr20"][j]
            atr_pct = a20 / c
            if not (d["tv20"][j] >= thr[ci] and d["craw"][j] >= EB.PX_MIN and atr_pct >= EB.ATR_LO):
                continue
            hp = hpL[j]
            if not (hp > 0 and c > hp):
                continue
            if not (e60[j] > e60[j - 1] and c > e60[j]):
                continue
            tvp = d["tvprev20"][j]
            if not (tvp > 0 and d["tv"][j] >= 1.5 * tvp):
                continue
            N = d["n14"][j]
            if not (N > 0):
                continue
            o1 = d["o"][j + 1]
            if o1 >= c * 1.03 or o1 > hp * 1.04:
                continue
            if lock[t][j + 1]:
                n_lock += 1
                continue
            m = mu[ci]
            out.append({"ticker": t, "j": int(j), "sig_ci": int(ci), "entry_ci": int(ci + 1), "line": float(hp),
                        "E": float(o1), "N": float(N), "rw": float(2.0 * N), "m": float(m) if m == m else None,
                        "tv20": float(d["tv20"][j]),
                        "fu": bool(d["craw"][j] <= EB.PX_MAX and atr_pct <= EB.ATR_HI and d["qual60"][j])})
    return out, n_lock


def attach30(sigs: list, V: dict, trail, chan, bl, mode="color") -> list:
    from replay.strategies import etf_trend_opt as EO
    data, cal = V["data"], V["cal"]
    out = []
    for s in sigs:
        d = data[s["ticker"]]
        k, px, why = EO.sim_v(d, s["j"], s["line"], trail, chan, bl, mode=mode)
        an = bool(V["anom"][s["ticker"]][s["j"] + 1:k + 1].any())
        ret = px / s["E"] - 1.0
        ec = s["entry_ci"]
        out.append(dict(s, k=int(k), exit_ci=int(d["ci"][k]), exit_px=float(px), reason=why, ret=float(ret),
                        anom=an, cost_table=float(V["cost_rt"]["table"][ec]), cost_fee=float(V["cost_rt"]["fee"][ec]),
                        entry_date=str(cal[ec].date()), exit_date=str(cal[d["ci"][k]].date())))
    return out


def with_cost(ts: list, kind: str) -> list:
    key = {"table": "cost_table", "fee": "cost_fee"}
    return [dict(t, RN=t["ret"] - (0.0038 if kind == "const" else t[key[kind]])) for t in ts]


def in_win(t, win) -> bool:
    return win[0] <= t["entry_date"] <= win[1]


def etf_book30(V: dict, sigs: list, cb, win, *, seeds, cost_kind="table", mu_mode="shadow", mode="color") -> dict:
    """``etf_trend_opt.run_book`` + ``EA.etf_book`` 의 하루 순서 — 비용만 날마다, 연율 달력."""
    from replay.audit.sizing import OpSizer
    from replay.strategies import etf_trend_b as EB
    from replay.strategies import etf_trend_b_audit as EA
    from replay.strategies import etf_trend_opt as EO
    L, tr, ch, bl, mu = cb
    op = OpSizer(EA._import_operating_class(), "etf_trend", {"market_unit_mode": mu_mode}, atr_keys=("atr",))
    data, cal = V["data"], V["cal"]
    cs_day = (np.full(len(cal), 0.0019) if cost_kind == "const" else V["cost_rt"][cost_kind] / 2)
    sbg = defaultdict(list)
    for t in sigs:
        if not (t["fu"] and EO.mu_ok(t["m"], mu)):
            continue
        sbg[t["entry_ci"]].append(EA.ETFSig(t["ticker"], t["j"] + 1, t["entry_ci"], t["E"], t["E"], t["N"],
                                            t["line"], t["m"], t["tv20"], t["sig_ci"]))
    g0, g1 = win_idx(cal, win)
    yrs = years_cal(cal, g0, g1)
    runs = []
    for sd in seeds:
        rng = np.random.default_rng(sd)
        cash = float(C.BUDGET_C7)
        pos, eq_prev, equity, trades, cnt, paid = {}, float(C.BUDGET_C7), [], [], Counter(), 0.0
        for gd in range(g0, g1 + 1):
            cs = float(cs_day[gd])
            B = eq_prev
            sold_today = set()
            for t in list(pos):
                ps = pos[t]
                ti = ps.cur_ti(gd)
                if ti is None:
                    continue
                if ps.open_phase(ti, gd):
                    amt = ps.k * ps.exit_px
                    cash += amt * (1 - cs)
                    paid += amt * cs
                    trades.append(ps)
                    sold_today.add(t)
                    del pos[t]
            todays = list(sbg.get(gd, []))
            rng.shuffle(todays)
            todays.sort(key=lambda s: -s.tv20)
            taken = []
            for s in todays:
                if s.ticker in pos or s.ticker in sold_today:
                    continue
                cnt["signal"] += 1
                if len(pos) >= EB.SLOTS:
                    cnt["slot_full"] += 1
                    continue
                pool = set(pos) | sold_today | set(taken)
                if any(EB.same_cluster(V["corr"], s.ticker, o, s.sig_ci) for o in pool if o != s.ticker):
                    cnt["cluster"] += 1
                    continue
                used = sum(x.cost_basis for x in pos.values())
                P = int(round(s.E_raw))
                qn = op.qty(P, s.N, budget=int(B), used=int(used), m=s.m)
                if qn <= 0:
                    cnt["zero_" + ("funds" if int(B) - int(used) < P else "design")] += 1
                    continue
                ps = EO.EtfPosV(s, data[s.ticker], qn, trail=tr, chan=ch, bl=bl, mode=mode, fadj=None)
                amt = qn * s.E_raw
                cash -= amt * (1 + cs)
                paid += amt * cs
                pos[s.ticker] = ps
                taken.append(s.ticker)
                cnt["fill"] += 1
            for t in list(pos):
                ps = pos[t]
                ti = ps.cur_ti(gd)
                if ti is None:
                    if ps.data_ended(gd):
                        ps._exit(ps.last_px, "END", gd)
                        amt = ps.k * ps.exit_px
                        cash += amt * (1 - cs)
                        paid += amt * cs
                        trades.append(ps)
                        del pos[t]
                    continue
                if ps.intraday_phase(ti, gd, ti == ps.s.ti):
                    amt = ps.k * ps.exit_px
                    cash += amt * (1 - cs)
                    paid += amt * cs
                    trades.append(ps)
                    del pos[t]
            eq = cash + sum(x.value() for x in pos.values())
            equity.append(eq)
            eq_prev = eq
        eqa = np.array(equity)
        e = np.r_[float(C.BUDGET_C7), eqa]
        free = cnt["signal"] - cnt["slot_full"]
        runs.append({"cagr": float((eqa[-1] / C.BUDGET_C7) ** (1 / yrs) - 1),
                     "mdd": float((e / np.maximum.accumulate(e) - 1).min()), "fills": cnt["fill"],
                     "unaff": cnt["zero_funds"] / free if free > 0 else float("nan"), "counts": dict(cnt),
                     "cost_pct": float(paid / eqa.mean() / yrs * 100), "equity": eqa})
    return {"cagr_median": float(np.median([r["cagr"] for r in runs])),
            "mdd_median": float(np.median([r["mdd"] for r in runs])),
            "fills_per_year_median": float(np.median([r["fills"] for r in runs]) / yrs),
            "unaffordable_ratio_median": float(np.nanmedian([r["unaff"] for r in runs])) if any(
                r["unaff"] == r["unaff"] for r in runs) else float("nan"),
            "cost_per_year_pct_seed0": runs[0]["cost_pct"], "counts_seed0": runs[0]["counts"],
            "per_seed_identical": len({round(r["cagr"], 9) for r in runs}) == 1, "years": yrs,
            "equity_seed0": runs[0]["equity"]}


def stats30(ts: list) -> dict:
    if not ts:
        return {"n": 0, "mean": float("nan"), "lo90": float("nan"), "hi90": float("nan")}
    est, lo, hi = J.cluster_bootstrap([t["RN"] for t in ts], [J.iso_week_key(t["ticker"], t["entry_date"]) for t in ts],
                                      order="sorted")
    return {"n": len(ts), "mean": est, "lo90": lo, "hi90": hi,
            "hold_median": float(np.median([t["exit_ci"] - t["entry_ci"] for t in ts])),
            "win_rate": float(np.mean([t["RN"] > 0 for t in ts]))}


def p_judge(st: dict, bk: dict, adv_mean: float) -> dict:
    return {"P1": bool(st["n"] > 0 and st["mean"] > 0 and st["lo90"] > C.P1_LO),
            "P3": bool(bk["cagr_median"] > 0 and bk["mdd_median"] >= C.P3_MDD),
            "P4": bool(bk["fills_per_year_median"] >= C.P4_FILLS_PER_YEAR
                       and not (bk["unaffordable_ratio_median"] >= C.P4_UNAFF)),
            "P5_same_sign": bool(np.sign(adv_mean) == np.sign(st["mean"])) if st["n"] else None}


def etf_run(V: dict, base: dict) -> dict:  # noqa: C901
    from replay.strategies import etf_trend_b as EB
    from replay.strategies import etf_trend_opt as EO
    cal = V["cal"]
    thr = 2e9 * V["defl"]
    thr_nom = np.full(len(cal), 2e9)
    out = {}
    # 유니버스 표(연도별 그날 적격 수 중앙값 · 클래스 해당 종목 수)
    elig = np.zeros(len(cal))
    elig_nom = np.zeros(len(cal))
    for t, d in V["data"].items():
        okb = np.arange(len(d["ci"])) >= EB.MIN_BARS - 1
        for arr, th in ((elig, thr), (elig_nom, thr_nom)):
            mk = okb & (d["tv20"] >= th[d["ci"]])
            np.add.at(arr, d["ci"][mk], 1)
    yy = pd.Series(elig, index=cal).groupby(cal.year).median()
    yn = pd.Series(elig_nom, index=cal).groupby(cal.year).median()
    nt = {int(y): int(sum(1 for d in V["data"].values() if any(cal[d["ci"]].year == y))) for y in sorted(set(cal.year))}
    out["universe"] = {int(y): {"elig_defl": float(yy[y]), "elig_nom": float(yn[y]), "class_tickers": nt[int(y)]}
                       for y in yy.index}
    out["anomaly_bars"] = int(sum(a.sum() for t, a in V["anom"].items() if t in V["data"]))
    out["lock_bars"] = int(sum(a.sum() for t, a in V["lock"].items() if t in V["data"]))
    sigs, nlock = {}, {}
    for L in EO.L_GRID:
        sigs[L], nlock[L] = gen_signals30(V["data"], V["mu"], L, thr, V["anom"], V["lock"])
    out["entry_lock_skipped"] = nlock
    exits = {}
    for L in EO.L_GRID:
        for tr, ch, bl in itertools.product(EO.TR_GRID, EO.CH_GRID, EO.BL_GRID):
            exits[(L, tr, ch, bl)] = attach30(sigs[L], V, tr, ch, bl)
    ded = {}
    n_anom = {}
    for cb in EO.grid():
        L, tr, ch, bl, mu = cb
        pool = [t for t in exits[(L, tr, ch, bl)] if t["fu"] and EO.mu_ok(t["m"], mu)]
        n_anom[cb] = sum(t["anom"] for t in pool)
        ded[cb] = EB.dedup([t for t in pool if not t["anom"]], V["corr"])
    CUR = EO.CURRENT
    CH5 = (20, 3.0, 10, True, "ge075")
    out["anom_trades_excluded_current"] = n_anom[CUR]

    def adv_mean(cb, ts, kind):
        L, tr, ch, bl, mu = cb
        v = []
        for t in ts:
            d = V["data"][t["ticker"]]
            k, px, _ = EO.sim_v(d, t["j"], t["line"], tr, ch, bl, mode="adverse")
            c = 0.0038 if kind == "const" else t["cost_table"]
            v.append(px / t["E"] - 1 - c)
        return float(np.mean(v)) if v else float("nan")

    # ── A: 현행 규칙 ──
    A = {}
    cur_tab = with_cost(ded[CUR], "table")
    cur_const = with_cost(ded[CUR], "const")
    for wn, win in (("Vp", VP_WIN), ("H", H_WIN), ("pre", PRE_WIN), ("F", F_WIN)):
        ts = [t for t in cur_tab if in_win(t, win)]
        st = stats30(ts)
        stc = stats30([t for t in cur_const if in_win(t, win)])
        bk = etf_book30(V, sigs[20], CUR, win, seeds=C.BOOK_SEEDS)
        bkc = etf_book30(V, sigs[20], CUR, win, seeds=(0,), cost_kind="const")
        am = adv_mean(CUR, ts, "table")
        A[wn] = {"stats": st, "stats_const": stc, "stats_fee": stats30([t for t in with_cost(ded[CUR], "fee") if in_win(t, win)]),
                 "book": {k: v for k, v in bk.items() if k != "equity_seed0"},
                 "book_const": {k: v for k, v in bkc.items() if k != "equity_seed0"}, "adverse_mean": am,
                 "judge": p_judge(st, bk, am), "reasons": dict(Counter(t["reason"] for t in ts)),
                 "per_year": len(ts) / years_cal(cal, *win_idx(cal, win))}
    A["persist_Vp_H"] = bool(np.sign(A["Vp"]["stats"]["mean"]) == np.sign(A["H"]["stats"]["mean"]))
    # 명목 문턱 판(보고 한 줄)
    s_nom, _ = gen_signals30(V["data"], V["mu"], 20, thr_nom, V["anom"], V["lock"])
    e_nom = attach30(s_nom, V, 1.8, 10, True)
    d_nom = with_cost(EB.dedup([t for t in e_nom if t["fu"] and EO.mu_ok(t["m"], "gt0") and not t["anom"]], V["corr"]),
                      "table")
    A["nominal_thr"] = {wn: stats30([t for t in d_nom if in_win(t, w)]) for wn, w in (("Vp", VP_WIN), ("H", H_WIN))}
    # 연도별 · 시대별
    yrs = sorted({t["entry_date"][:4] for t in cur_tab})
    A["by_year"] = {y: {k: v for k, v in stats30([t for t in cur_tab if t["entry_date"][:4] == y]).items()
                        if k in ("n", "mean", "lo90", "win_rate")} for y in yrs}
    A["by_era"] = [{"win": list(w), **{k: v for k, v in stats30([t for t in cur_tab if in_win(t, w)]).items()
                                       if k in ("n", "mean", "lo90", "hi90")}} for w in ERAS]
    out["A"] = A

    # ── B-a: 5년 선택판 바깥 표본(F) ──
    def side(cb, win, kind="table"):
        return [t for t in with_cost(ded[cb], kind) if in_win(t, win)]
    Ba = {}
    for nm, cb in (("current", CUR), ("chosen5", CH5)):
        tsF = side(cb, F_WIN)
        bk = etf_book30(V, sigs[cb[0]], cb, F_WIN, seeds=C.BOOK_SEEDS)
        Ba[nm] = {"F": stats30(tsF), "H": stats30(side(cb, H_WIN)), "pre": stats30(side(cb, PRE_WIN)),
                  "Vp": stats30(side(cb, VP_WIN)), "F_const": stats30(side(cb, F_WIN, "const")),
                  "book_F": {k: v for k, v in bk.items() if k != "equity_seed0"}, "adverse_F": adv_mean(cb, tsF, "table")}
    d1 = EO.diff_bootstrap(side(CH5, F_WIN), side(CUR, F_WIN))
    d1c = EO.diff_bootstrap(side(CH5, F_WIN, "const"), side(CUR, F_WIN, "const"))
    hd = Ba["chosen5"]["H"]["mean"] - Ba["current"]["H"]["mean"]
    pd_ = Ba["chosen5"]["pre"]["mean"] - Ba["current"]["pre"]["mean"] if Ba["current"]["pre"]["n"] else None
    ch = Ba["chosen5"]
    Ba["D1"] = {**d1, "pass": bool(d1["diff"] > 0 and d1["lo90"] > 0), "pass_bonf108": bool(d1["lo_bonf"] > 0)}
    Ba["D1_const"] = d1c
    Ba["D2"] = bool(ch["F"]["mean"] > 0 and ch["F"]["lo90"] > C.P1_LO)
    Ba["D3"] = bool(ch["book_F"]["cagr_median"] > 0 and ch["book_F"]["mdd_median"] >= C.P3_MDD)
    Ba["D4"] = bool(ch["book_F"]["fills_per_year_median"] >= C.P4_FILLS_PER_YEAR)
    Ba["D5_same_sign"] = bool(np.sign(ch["adverse_F"]) == np.sign(ch["F"]["mean"]))
    Ba["H_diff"] = hd
    Ba["H_diff_sign_same"] = bool(np.sign(hd) == np.sign(d1["diff"]))
    Ba["pre_diff"] = pd_
    out["B_a"] = Ba

    # ── B-b: V' 에서 재선택 → H 판정 ──
    yVp = years_cal(cal, *win_idx(cal, VP_WIN))
    cur_sub = [np.mean([t["RN"] for t in side(CUR, w)] or [np.nan]) for w in VP_SUB]
    rows = []
    for cb in EO.grid():
        ts = side(cb, VP_WIN)
        s = stats30(ts)
        sub = [np.mean([t["RN"] for t in side(cb, w)] or [np.nan]) for w in VP_SUB]
        dpos = sum(1 for x, y in zip(sub, cur_sub) if x == x and y == y and x - y > 0)
        rows.append({"combo": EO.combo_name(cb), "cb": list(cb), "Vp": s, "per_year": s["n"] / yVp,
                     "sub_mean": sub, "sub_diff_pos": dpos, "eligible": bool(s["n"] / yVp >= EO.MIN_TRADES_PER_YEAR),
                     "robust": bool(dpos >= 2) if cb != CUR else None,
                     "H": {k: v for k, v in stats30(side(cb, H_WIN)).items() if k in ("n", "mean", "lo90")}})
    cur_row = next(r for r in rows if tuple(r["cb"]) == CUR)
    cand = [r for r in rows if tuple(r["cb"]) != CUR and r["eligible"] and r["robust"]]
    cand.sort(key=lambda r: (-r["Vp"]["lo90"], r["Vp"]["n"]))
    pick = cand[0] if cand and cand[0]["Vp"]["lo90"] > cur_row["Vp"]["lo90"] else None
    chosen = tuple(pick["cb"]) if pick else CUR
    Bb = {"n_grid": len(rows), "n_eligible": sum(r["eligible"] for r in rows), "n_eligible_robust": len(cand),
          "chosen": EO.combo_name(chosen), "chosen_is_current": chosen == CUR, "current_Vp": cur_row,
          "top10": sorted([r for r in rows if r["eligible"]], key=lambda r: -r["Vp"]["lo90"])[:10]}
    if chosen != CUR:
        dH = EO.diff_bootstrap(side(chosen, H_WIN), side(CUR, H_WIN))
        bH = etf_book30(V, sigs[chosen[0]], chosen, H_WIN, seeds=C.BOOK_SEEDS)
        Bb["H_D1"] = {**dH, "pass": bool(dH["diff"] > 0 and dH["lo90"] > 0), "pass_bonf108": bool(dH["lo_bonf"] > 0)}
        Bb["chosen_H"] = stats30(side(chosen, H_WIN))
        Bb["chosen_book_H"] = {k: v for k, v in bH.items() if k != "equity_seed0"}
        Bb["chosen_F_vs_current"] = EO.diff_bootstrap(side(chosen, F_WIN), side(CUR, F_WIN))
    out["B_b"] = Bb

    # ── 기준선(바탕 층 계좌 — 같은 비용 표) ──
    bcal, O, Cl = base["cal"], base["O"], base["Cl"]
    W_b0 = BL.weights_path({"fam": "B0"}, bcal, base["m"], base["dd"], base["c"])
    W_m = BL.weights_path(A_CANDS["A2"], bcal, base["m"], base["dd"], base["c"])
    W_1 = m1_only_path(bcal, base["m"])
    out["baselines"] = {f"{nm}|{wn}": _s(run_account30(W, O, Cl, *win_idx(bcal, w), base["cs"]["table"], bcal))
                        for nm, W in (("hold", W_b0), ("x_m", W_m), ("m1_only", W_1))
                        for wn, w in (("Vp", VP_WIN), ("H", H_WIN), ("F", F_WIN), ("pre", PRE_WIN))}
    return out


def etf_gate(V: dict) -> dict:
    """관문 2 — 2020-10-05 ~ 2026-09-23 진입 현행판: 네이버(명목 문턱 · 시총 문턱 없음) 대 5년 KRX 파이프라인."""
    from replay.strategies import etf_trend_b as EB
    from replay.strategies import etf_trend_opt as EO
    win = ("2020-10-05", "2026-09-23")
    thr_nom = np.full(len(V["cal"]), 2e9)
    s, _ = gen_signals30(V["data"], V["mu"], 20, thr_nom, V["anom"], V["lock"])
    mine = with_cost(EB.dedup([t for t in attach30(s, V, 1.8, 10, True)
                               if t["fu"] and EO.mu_ok(t["m"], "gt0") and not t["anom"]], V["corr"]), "const")
    mine = [t for t in mine if in_win(t, win)]
    K = EO.load()
    ks = EO.gen_signals(K["data"], K["cls"], K["mu"], 20)
    kall = EO.attach_exit(ks, K["data"], K["fadj"], K["cal"], 1.8, 10, True)
    kded = [t for t in EB.dedup([t for t in kall if t["fu"] and EO.mu_ok(t["m"], "gt0")], K["corr"]) if in_win(t, win)]
    # 시총 문턱만으로 빠진 신호(시총 외 조건은 통과)
    only_mc = 0
    for t in kall:
        d = K["data"][t["ticker"]]
        j = t["j"]
        rest = d["craw"][j] <= EB.PX_MAX and d["atr20"][j] / d["c"][j] <= EB.ATR_HI and d["qual60"][j]
        if rest and not d["mc"][j] >= EB.MCAP_MIN and EO.mu_ok(t["m"], "gt0") and in_win(t, win):
            only_mc += 1
    listed = {t: m["listed_at_end"] for t, m in K["meta"].items()}
    a = {(t["ticker"], t["entry_date"]) for t in mine}
    b = {(t["ticker"], t["entry_date"]) for t in kded}
    # m 일치
    kc = pd.DatetimeIndex(K["cal"])
    mk = pd.Series(K["mu"], index=kc)
    mn = pd.Series(V["mu"], index=V["cal"])
    common = kc.intersection(V["cal"])
    common = common[(common >= pd.Timestamp(win[0])) & (common <= pd.Timestamp(win[1]))]
    x, y = mk.reindex(common).to_numpy(), mn.reindex(common).to_numpy()
    ok = np.isfinite(x) & np.isfinite(y)
    return {"naver_n": len(mine), "krx_n": len(kded), "overlap": len(a & b),
            "overlap_of_krx": len(a & b) / max(len(b), 1), "overlap_of_naver": len(a & b) / max(len(a), 1),
            "naver_mean_RN": float(np.mean([t["RN"] for t in mine])) if mine else None,
            "krx_mean_RN": float(np.mean([t["RN"] for t in kded])) if kded else None,
            "krx_delisted_trades": sum(1 for t in kded if not listed.get(t["ticker"], True)),
            "krx_delisted_mean_RN": (float(np.mean([t["RN"] for t in kded if not listed.get(t["ticker"], True)]))
                                     if any(not listed.get(t["ticker"], True) for t in kded) else None),
            "krx_signals_blocked_by_mcap_only": only_mc,
            "m_agree_ratio": float(np.mean(x[ok] == y[ok])), "m_days": int(ok.sum()),
            "pass": bool(len(a & b) / max(len(b), 1) >= 0.5)}


# ── −10% 진단 ───────────────────────────────────────────────────────────

DD_ERAS = (("1995-01-01", "2001-12-31"), ("2002-01-01", "2008-12-31"), ("2009-01-01", "2015-12-31"),
           ("2016-01-01", "2020-12-31"), ("2021-01-01", "2026-12-31"))


def dd_run(B: dict) -> dict:
    from src.engine import market_regime_label as RL
    cal = B["cal"]
    c = B["c_idx"]
    o = YD.load_index_series().open.to_numpy(float)
    dd = BL.drawdown60(c)
    m = B["m"]
    sl = RL.session_labels(list(cal.date), list(c))
    lab = {d: p for d, p in sl}
    dir_close = [None] * len(cal)
    for i in range(len(cal) - 1):
        p = lab.get(cal[i + 1].date())
        dir_close[i] = p.direction if p is not None else None
    last = RL.label_after_closes(list(c))[-1]
    dir_close[-1] = last.direction if last is not None else None
    ev = BL.event_table(cal, c, o, dd, m, dir_close, 0.10)
    counts = {f"X{int(x * 100)}": len(BL.dd_events(dd, x)) for x in (0.07, 0.10, 0.12, 0.15)}

    def base_rates(lo, hi):
        i0 = max(int(cal.searchsorted(pd.Timestamp(lo))), 59)
        i1 = int(cal.searchsorted(pd.Timestamp(hi), side="right"))
        out = {}
        for h in (20, 60):
            fr = np.array([c[t + h] / c[t] - 1 for t in range(i0, min(i1, len(c) - h))])
            out[f"fwd{h}"] = {"n": len(fr), "mean": float(fr.mean()), "median": float(np.median(fr)),
                              "pos": float((fr > 0).mean())} if len(fr) else None
        return out

    def summ(rows):
        if not rows:
            return {"n": 0}
        f20 = [r["fwd20"] for r in rows if r["fwd20"] is not None]
        f60 = [r["fwd60"] for r in rows if r["fwd60"] is not None]
        fa = [r["false_alarm"] for r in rows if r["false_alarm"] is not None]
        fd = [r["further_drop60"] for r in rows if r["further_drop60"] is not None]
        leads = {k: [r[k + "_lead"] for r in rows if r[k + "_lead"] is not None]
                 for k in ("m_lt1", "m_eq0", "label_not_up", "label_down")}
        return {"n": len(rows), "false_alarm": int(sum(fa)), "false_alarm_n": len(fa),
                "further_drop_le10": int(sum(x <= -0.10 for x in fd)), "further_n": len(fd),
                "fwd20_mean": float(np.mean(f20)) if f20 else None, "fwd20_median": float(np.median(f20)) if f20 else None,
                "fwd60_mean": float(np.mean(f60)) if f60 else None, "fwd60_median": float(np.median(f60)) if f60 else None,
                "lead_pos": {k: {"pos": int(sum(x > 0 for x in v)), "n": len(v), "none": len(rows) - len(v)}
                             for k, v in leads.items()},
                "peak_to_signal_median": float(np.median([r["peak_to_signal"] for r in rows]))}
    eras = []
    for lo, hi in DD_ERAS:
        rows = [r for r in ev if lo <= r["signal"] <= hi]
        eras.append({"win": [lo, hi], **summ(rows), "base": base_rates(lo, hi)})
    fast = [r for r in ev if r["peak_to_signal"] <= 10]
    slow = [r for r in ev if r["peak_to_signal"] > 10]
    return {"events": ev, "counts": counts, "all": summ(ev), "base_all": base_rates("1995-01-01", "2026-12-31"),
            "eras": eras, "fast": summ(fast), "slow": summ(slow),
            "first_valid": str(cal[int(np.argmax(np.isfinite(dd)))].date())}


# ── 실행 ────────────────────────────────────────────────────────────────

def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items() if not (isinstance(v, np.ndarray) and v.ndim > 1)}
    if isinstance(o, (list, tuple)):
        return [_clean(x) for x in o]
    if isinstance(o, np.ndarray):
        return [_clean(x) for x in o.tolist()]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float) and o != o:
        return None
    return o


def main():
    t0 = time.time()
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(OUT_DIR, "result.json")
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    res = {"prereg_sha256": open(os.path.join(OUT_DIR, "prereg.sha256")).read().split()[0],
           "fred_sha256": {f: YD.sha256(os.path.join(YD.FRED_DIR, f)) for f in sorted(os.listdir(YD.FRED_DIR))},
           "code_sha256": {f: YD.sha256(os.path.join(os.path.dirname(__file__), f))
                           for f in ("y30_etfbase_data.py", "y30_etfbase_run.py", "base_layer.py")}}
    B = base_inputs()
    print(f"[y30] base inputs {time.time()-t0:.0f}s", flush=True)
    if only in (None, "gate", "base"):
        res["gate_base"] = base_gate(B)
        print("[y30] gate_base", json.dumps(_clean(res["gate_base"]))[:600], flush=True)
        if not res["gate_base"]["pass"]:
            print("[y30] 관문 1 실패 — 결과는 남기되 원인부터 본다", flush=True)
    if only in (None, "base"):
        br = base_run(B)
        res["base"] = {k: v for k, v in br.items() if k not in ("chosen_W", "b0_W")}
        res["base"]["div_report"] = base_div_report(br["chosen"]["combo"])
        print(f"[y30] base {time.time()-t0:.0f}s chosen={br['chosen']['name']} J1={br['J1']['pass']}", flush=True)
    if only in (None, "etf", "gate"):
        V = etf_load()
        print(f"[y30] etf load {time.time()-t0:.0f}s", flush=True)
        res["gate_etf"] = etf_gate(V)
        print("[y30] gate_etf", json.dumps(_clean(res["gate_etf"])), flush=True)
        if only != "gate":
            res["etf"] = etf_run(V, B)
            print(f"[y30] etf {time.time()-t0:.0f}s", flush=True)
    if only in (None, "dd"):
        res["dd"] = dd_run(B)
        print(f"[y30] dd {time.time()-t0:.0f}s", flush=True)
    res["elapsed_s"] = round(time.time() - t0, 1)
    with open(out_path, "w") as fh:
        json.dump(_clean(res), fh, ensure_ascii=False, indent=1, default=str)
    print("[y30] done", out_path, res["elapsed_s"], flush=True)


if __name__ == "__main__":
    main()
