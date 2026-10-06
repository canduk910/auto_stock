#!/usr/bin/env python3
"""여러 나라 자산배분 2차 — 동일 비중 B 재검증 · 변형 · 일일 2배 레버리지 비교
(사전 등록 ``global_alloc_20261006/prereg_b.frozen.md``).

입력 = 1차와 같은 ``global_daily_krw.parquet``. 1차 모듈(``global_alloc``)의 상수·부트스트랩 함수를 그대로 쓴다.

    python tools/replay/global_alloc_b.py <global_daily_krw.parquet> <out_dir>
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))

from replay import global_alloc as G  # noqa: E402

RISKY = G.RISKY
EQUITY = G.EQUITY
HEDGEABLE = G.HEDGEABLE
LEV = tuple("L" + a for a in RISKY)
COLS = RISKY + ("CASH",) + LEV
N = len(COLS)
I_CASH = COLS.index("CASH")
I_UST, I_USD = COLS.index("UST10"), COLS.index("USD")
C_LEV_BASE = 0.008                     # 레버리지 연 부대비용(보수 + 조달 스프레드) 기본
BAND = 0.05
SEED = 20261006
PRIMARY_END = "2005-12-31"
SEEN_START_YEAR = 2006


@dataclass
class Mkt:
    dates: pd.DatetimeIndex
    ret: np.ndarray            # T×N 일 원화 수익(보수 차감 전)
    fee: np.ndarray            # T×N 일 보수
    dt_y: np.ndarray
    taxable: np.ndarray        # N 차익 과세 여부
    divtax: np.ndarray         # N 연 배당 원천징수율(= 배당수익률 × 15.4%)


def lev_returns(df: pd.DataFrame, kind: str, c: float) -> dict[str, np.ndarray]:
    """일일 2배 상품의 일 원화 수익. kind = 'U'(지수 2배 + 환 1배) · 'H'(지수 2배 + 금리차) · 'R'(실재 상품 구조)."""
    dates = pd.DatetimeIndex(df.index)
    dt = pd.Series(dates, index=dates).diff().dt.days.fillna(1).to_numpy(float) / 365.0
    cash = df["CASH_ret"].to_numpy(float)
    out = {}
    real = {"SPX": "H", "NDX": "U", "NKY": "H", "HSCEI": "H", "UST10": "H"}
    for a in RISKY:
        r = df[f"{a}_ret"].to_numpy(float)
        if a == "K200":
            x = 2 * r - cash - c * dt
        elif a == "USD":
            x = cash + 2 * (r - cash) - c * dt
        else:
            rl = df[f"{a}_lret"].to_numpy(float)
            h = df[f"{a}_hret"].to_numpy(float)
            fx = (1 + r) / (1 + rl) - 1
            rf = cash - (h - rl)
            k = real[a] if kind == "R" else kind
            if k == "U":
                x = (1 + 2 * rl - rf - c * dt) * (1 + fx) - 1
            else:
                x = 2 * rl - rf - c * dt + (cash - rf)
        x = np.maximum(x, -1.0)             # 하루 −100% 아래는 없다(가치 0)
        x[0] = 0.0
        out["L" + a] = x
    return out


def load(df: pd.DataFrame, lev_kind: str = "U", c: float = C_LEV_BASE, hedged: bool = False) -> Mkt:
    dates = pd.DatetimeIndex(df.index)
    dt = pd.Series(dates, index=dates).diff().dt.days.fillna(1).to_numpy(float) / 365.0
    ret = np.zeros((len(dates), N))
    for j, a in enumerate(RISKY):
        col = f"{a}_hret" if (hedged and a in HEDGEABLE) else f"{a}_ret"
        ret[:, j] = df[col].to_numpy(float)
    ret[:, I_CASH] = df["CASH_ret"].to_numpy(float)
    lv = lev_returns(df, lev_kind, c)
    for a in LEV:
        ret[:, COLS.index(a)] = lv[a]
    ret[0, :] = 0.0
    fee_rate = np.array([G.FEE[x] if x in G.FEE else 0.0 for x in COLS])   # 레버리지 보수는 c 에 들어 있다
    fee = np.outer(dt, fee_rate)
    taxable = np.array([(x in G.TAXABLE_GAIN) or (x.startswith("L") and x != "LK200") for x in COLS])
    divtax = np.array([G.DIV_FOR_TAX.get(x, 0.0) * G.TAX if x in G.DIV_FOR_TAX
                       else (2 * G.DIV_FOR_TAX.get(x[1:], 0.0) * G.TAX if x.startswith("L") else 0.0)
                       for x in COLS])
    return Mkt(dates, ret, fee, dt, taxable, divtax)


# ───────────────────────────── 비중 ─────────────────────────────

def target(name: str) -> np.ndarray:
    w = np.zeros(N)
    ix = {a: COLS.index(a) for a in COLS}
    if name in ("B", "B-Q", "B-A", "B-Band", "B-H", "LEV1"):
        for a in RISKY:
            w[ix[a]] = 1 / 7
    elif name == "B0":
        w[ix["K200"]] = 1.0
    elif name == "B1":
        w[ix["K200"]], w[ix["UST10"]] = 0.6, 0.4
    elif name == "B-EQ":
        for a in EQUITY:
            w[ix[a]] = 0.2
    elif name == "LEV2a":
        for a in LEV:
            w[ix[a]] = 1 / 14
        w[I_CASH] = 0.5
    elif name == "LEV2b":
        for a in LEV:
            w[ix[a]] = 1 / 14
        w[I_UST] += 0.25
        w[I_USD] += 0.25
    elif name == "LEV3":
        for a in LEV:
            w[ix[a]] = 1 / 7
    elif name == "LEV4":
        for a in EQUITY:
            w[ix["L" + a]] = 1 / 7
        w[I_UST] = 1 / 7
        w[I_USD] = 1 / 7
    else:
        raise ValueError(name)
    return w


def erc_weights(cov: np.ndarray, tol: float = 1e-10, it: int = 10_000) -> np.ndarray:
    """위험 동일 기여 — w_i (Σw)_i 가 모두 같아지는 비중(합 1, 양수). 순환 좌표 하강(Griveau-Billion 형)."""
    n = cov.shape[0]
    b = np.full(n, 1.0 / n)
    x = 1.0 / np.sqrt(np.diag(cov))
    x = x / x.sum()
    for _ in range(it):
        x_old = x.copy()
        for i in range(n):
            s = cov[i] @ x - cov[i, i] * x[i]
            x[i] = (-s + np.sqrt(s * s + 4 * cov[i, i] * b[i])) / (2 * cov[i, i])
        if np.max(np.abs(x - x_old)) < tol:
            break
    return x / x.sum()


def erc_at(m: Mkt, i: int, W: int = 126) -> np.ndarray:
    w = np.zeros(N)
    if i + 1 < W:
        w[:7] = 1 / 7
        return w
    cov = np.cov(m.ret[i - W + 1:i + 1, :7].T) * 252
    w[:7] = erc_weights(cov)
    return w


def decision_points(dates: pd.DatetimeIndex, freq: str) -> np.ndarray:
    if freq in ("M", "Q"):
        return G.decision_points(dates, freq)
    if freq == "A":
        s = pd.Series(np.arange(len(dates)), index=dates)
        last = s.groupby(dates.year).max().to_numpy()
        return last[last < len(dates) - 1]
    raise ValueError(freq)


def schedule(m: Mkt, name: str, a: int, b: int) -> dict[int, np.ndarray] | str:
    """결정일 → 목표 비중. 시작일 a 는 항상 결정일(현금으로 출발 → a+1 종가 매수). 밴드는 'band'."""
    if name == "B-Band":
        return "band"
    if name == "B0":
        return {a: target("B0")}
    freq = {"B-Q": "Q", "B-A": "A"}.get(name, "M")
    dps = [int(i) for i in decision_points(m.dates, freq) if a <= i < b]
    if a not in dps:
        dps = [a] + dps
    if name == "B-ERC":
        return {i: erc_at(m, i) for i in dps}
    w = target(name)
    return {i: w for i in dps}


# ───────────────────────────── 모의 집행 ─────────────────────────────

@dataclass
class Sim:
    value: np.ndarray
    turnover: float
    cost: float
    n_trades: int


def simulate(m: Mkt, sched, a: int, b: int, tax: bool = False, band_target: np.ndarray | None = None,
             cost_one_way: float = G.COST_ONE_WAY) -> Sim:
    """a 종가에 현금 1 로 시작. 결정 i 의 비중을 i+1 종가에 집행. 'band' = 매일 종가에 밴드 이탈 검사."""
    r = m.ret - m.fee
    hold = np.zeros(N)
    hold[I_CASH] = 1.0
    basis = hold.copy()
    val = np.full(len(m.dates), np.nan)
    val[a] = 1.0
    band = sched == "band"
    if band:
        tgt_b = band_target if band_target is not None else target("B")
        exec_at = {a + 1: tgt_b}
    else:
        exec_at = {i + 1: w for i, w in sched.items() if a <= i and i + 1 <= b}
    turn_tot = cost_tot = 0.0
    nt = 0
    for t in range(a + 1, b + 1):
        hold = hold * (1 + r[t])
        if tax:
            d = hold * m.divtax * m.dt_y[t]
            d[I_CASH] = hold[I_CASH] * G.TAX * max(r[t, I_CASH], 0.0)
            hold = hold - d
        V = hold.sum()
        if t in exec_at and V > 0:
            tgt = exec_at[t]
            cur = hold / V
            risky = np.arange(N) != I_CASH
            turn = float(np.abs(tgt[risky] - cur[risky]).sum())
            c = turn * cost_one_way * V
            new = tgt * (V - c)
            if tax:
                tx = 0.0
                for j in range(N):
                    if new[j] < hold[j] and hold[j] > 0:
                        frac = (hold[j] - new[j]) / hold[j]
                        gain = (hold[j] - basis[j]) * frac
                        if m.taxable[j] and gain > 0:
                            tx += G.TAX * gain
                        basis[j] *= (1 - frac)
                    elif new[j] > hold[j]:
                        basis[j] += new[j] - hold[j]
                new[I_CASH] -= tx
            hold = new
            turn_tot += turn
            cost_tot += c / V
            nt += 1
            V = hold.sum()
        if band and t < b and (t + 1) not in exec_at and V > 0:
            if np.max(np.abs(hold / V - tgt_b)) > BAND:
                exec_at[t + 1] = tgt_b
        val[t] = V
    if tax:
        gain = np.where(m.taxable, np.maximum(hold - basis, 0.0), 0.0).sum()
        val[b] -= G.TAX * gain
    return Sim(val, turn_tot, cost_tot, nt)


# ───────────────────────────── 지표 ─────────────────────────────

def metrics(m: Mkt, v: np.ndarray, a: int, b: int) -> dict:
    x = v[a:b + 1]
    rr = x[1:] / x[:-1] - 1
    cash = m.ret[a + 1:b + 1, I_CASH]
    yrs = (m.dates[b] - m.dates[a]).days / 365.25
    cagr = (x[-1] / x[0]) ** (1 / yrs) - 1 if x[-1] > 0 else -1.0
    peak = np.maximum.accumulate(x)
    dd = x / peak - 1
    mdd = float(dd.min())
    ex = rr - cash
    sd = ex.std(ddof=1)
    worst1y = float(np.min(x[252:] / x[:-252] - 1)) if len(x) > 252 else None
    # 최장 회복 기간(달력 일)
    longest, ongoing, start = 0, False, None
    dts = m.dates[a:b + 1]
    for k in range(len(x)):
        if dd[k] < 0 and start is None:
            start = k - 1
        elif dd[k] >= 0 and start is not None:
            longest = max(longest, (dts[k] - dts[start]).days)
            start = None
    if start is not None:
        span = (dts[-1] - dts[start]).days
        if span > longest:
            longest, ongoing = span, True
    return {"cagr": cagr, "vol": float(rr.std(ddof=1) * np.sqrt(252)),
            "sharpe": float(ex.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0, "mdd": mdd,
            "mar": cagr / abs(mdd) if mdd < 0 else None, "worst1y": worst1y,
            "recovery_days": int(longest), "recovery_ongoing": ongoing}


def monthly(m: Mkt, v: np.ndarray, a: int, b: int) -> pd.DataFrame:
    s = pd.Series(v[a:b + 1], index=m.dates[a:b + 1])
    c = pd.Series(np.cumprod(1 + m.ret[a:b + 1, I_CASH]), index=m.dates[a:b + 1])
    out = {}
    for k, ser in (("r", s), ("cash", c)):
        me = ser.groupby(ser.index.to_period("M")).last()
        me = pd.concat([pd.Series([ser.iloc[0]], index=[me.index[0] - 1]), me])
        out[k] = me.pct_change().dropna()
    df = pd.DataFrame(out)
    return df[df.index <= pd.Period("2026-09", "M")]


def boot(rc: np.ndarray, rb: np.ndarray, cash: np.ndarray, n_bonf: int, reps: int = 5000) -> dict:
    rng = np.random.default_rng(SEED)
    ds, dm = np.empty(reps), np.empty(reps)
    n = len(rc)
    for k in range(reps):
        ix = G.stationary_idx(n, 12.0, rng)
        ds[k] = G.m_sharpe(rc[ix], cash[ix]) - G.m_sharpe(rb[ix], cash[ix])
        dm[k] = G.m_mar(rc[ix]) - G.m_mar(rb[ix])
    q = 100 * 0.10 / n_bonf if n_bonf > 1 else 5.0
    return {"d_sharpe": G.m_sharpe(rc, cash) - G.m_sharpe(rb, cash), "d_sharpe_p05": float(np.percentile(ds, 5)),
            "d_sharpe_pbonf": float(np.percentile(ds, q)), "d_mar": G.m_mar(rc) - G.m_mar(rb),
            "d_mar_p05": float(np.percentile(dm, 5)), "d_mar_pbonf": float(np.percentile(dm, q))}


def ruin_paths(mos: dict[str, np.ndarray], reps: int = 5000, horizon: int = 120) -> dict:
    """모든 판 같은 달로 짝지어 10년 경로를 뽑는다 — 최대 낙폭 −50%·−80% 이하 비율 · 원금 미만 비율."""
    rng = np.random.default_rng(SEED)
    n = len(next(iter(mos.values())))
    acc = {k: {"dd50": 0, "dd80": 0, "below1": 0, "med_end": []} for k in mos}
    for _ in range(reps):
        ix = G.stationary_idx(n, 12.0, rng)[:horizon] if n >= horizon else None
        if ix is None:
            ix = np.concatenate([G.stationary_idx(n, 12.0, rng) for _ in range(horizon // n + 1)])[:horizon]
        for k, r in mos.items():
            v = np.cumprod(1 + r[ix])
            vv = np.concatenate([[1.0], v])
            dd = (vv / np.maximum.accumulate(vv) - 1).min()
            acc[k]["dd50"] += dd <= -0.5
            acc[k]["dd80"] += dd <= -0.8
            acc[k]["below1"] += v[-1] < 1
            acc[k]["med_end"].append(v[-1])
    return {k: {"p_dd50": x["dd50"] / reps, "p_dd80": x["dd80"] / reps, "p_below_principal": x["below1"] / reps,
                "median_end_x": float(np.median(x["med_end"])), "p05_end_x": float(np.percentile(x["med_end"], 5))}
            for k, x in acc.items()}


# ───────────────────────────── 실행 ─────────────────────────────

def periods(m: Mkt) -> dict[str, tuple[int, int]]:
    dps = G.decision_points(m.dates, "M")
    a_full = int(dps[0])
    b_prim = int(np.where(m.dates <= pd.Timestamp(PRIMARY_END))[0][-1])
    a_seen = int([i for i in dps if m.dates[min(i + 1, len(m.dates) - 1)].year >= SEEN_START_YEAR][0])
    b_end = len(m.dates) - 1
    return {"primary": (a_full, b_prim), "seen": (a_seen, b_end), "full": (a_full, b_end)}


def eras_of(period: str) -> dict[str, tuple[int, int]]:
    if period == "primary":
        return {"1995-99": (1995, 1999), "2000-05": (2000, 2005)}
    if period == "seen":
        return {"2006-10": (2006, 2010), "2011-15": (2011, 2015), "2016-20": (2016, 2020), "2021-26": (2021, 2026)}
    return {}


def era_sharpe(m: Mkt, v: np.ndarray, a: int, b: int, y0: int, y1: int) -> dict:
    yr = m.dates.year
    sel = np.where((yr >= y0) & (yr <= y1) & (np.arange(len(yr)) > a) & (np.arange(len(yr)) <= b))[0]
    return metrics(m, v, int(sel[0]) - 1, int(sel[-1]))


def run_set(m: Mkt, names: list[str], a: int, b: int, tax: bool = True) -> dict:
    out, vals = {}, {}
    for nm in names:
        s = schedule(m, nm, a, b)
        sim = simulate(m, s, a, b)
        yrs = (m.dates[b] - m.dates[a]).days / 365.25
        d = metrics(m, sim.value, a, b)
        d["turnover_yr"] = sim.turnover / yrs
        d["cost_yr"] = sim.cost / yrs
        d["n_trades"] = sim.n_trades
        if tax:
            d["after_tax"] = metrics(m, simulate(m, s, a, b, tax=True).value, a, b)["cagr"]
        out[nm] = d
        vals[nm] = sim.value
    return {"m": out, "vals": vals}


def judge(m: Mkt, vals: dict, a: int, b: int, cands: list[str], n_bonf: int, period: str) -> dict:
    mos = {k: monthly(m, v, a, b) for k, v in vals.items()}
    cash = mos["B0"]["cash"].to_numpy()
    res = {}
    for c in cands:
        rc = mos[c]["r"].to_numpy()
        vs = {bb: boot(rc, mos[bb]["r"].to_numpy(), cash, n_bonf) for bb in ("B0", "B1")}
        mc = metrics(m, vals[c], a, b)
        mb = {bb: metrics(m, vals[bb], a, b) for bb in ("B0", "B1")}
        eras = {}
        for e, (y0, y1) in eras_of(period).items():
            ec = era_sharpe(m, vals[c], a, b, y0, y1)
            eras[e] = {"cand": ec, **{f"d_sharpe_vs_{bb}": ec["sharpe"] - era_sharpe(m, vals[bb], a, b, y0, y1)["sharpe"]
                                      for bb in ("B0", "B1")},
                       **{f"d_cagr_vs_{bb}": ec["cagr"] - era_sharpe(m, vals[bb], a, b, y0, y1)["cagr"]
                          for bb in ("B0", "B1")}}
        g1 = all(vs[x]["d_sharpe_p05"] > 0 for x in ("B0", "B1"))
        g2 = all(vs[x]["d_mar_p05"] > 0 for x in ("B0", "B1"))
        g3 = all(mc["mdd"] >= mb[x]["mdd"] for x in ("B0", "B1"))
        g4 = all(eras[e][f"d_sharpe_vs_{x}"] > 0 for e in eras for x in ("B0", "B1")) if eras else None
        res[c] = {"vs": vs, "eras": eras, "G1": g1, "G2": g2, "G3": g3, "G4": g4,
                  "pass": bool(g1 and g2 and g3 and (g4 is None or g4)), "n_months": len(rc)}
    return res


BASE = ["B0", "B1", "B"]
VARIANTS = ["B-Q", "B-A", "B-Band", "B-EQ", "B-ERC"]
LEVS = ["LEV1", "LEV2a", "LEV2b", "LEV3", "LEV4"]


def _js(o):
    if isinstance(o, dict):
        return {str(k): _js(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_js(x) for x in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def main(parquet: str, out_dir: str) -> None:
    df = pd.read_parquet(parquet)
    out: dict = {"periods": {}}
    m = load(df, "U")
    mh = load(df, "U", hedged=True)
    P = periods(m)
    for pn, (a, b) in P.items():
        out["periods"][pn] = [str(m.dates[a].date()), str(m.dates[b].date())]
        rs = run_set(m, BASE + VARIANTS + LEVS, a, b)
        rh = run_set(mh, ["B"], a, b)
        rs["m"]["B-H"] = rh["m"]["B"]
        rs["vals"]["B-H"] = rh["vals"]["B"]
        sec = {"metrics": rs["m"],
               "judge_B": judge(m, rs["vals"], a, b, ["B"], 1, pn),
               "judge_variants": judge(m, rs["vals"], a, b, VARIANTS + ["B-H"], 6, pn),
               "judge_lev_U": judge(m, rs["vals"], a, b, ["LEV2a", "LEV2b", "LEV3", "LEV4"], 4, pn)}
        for kind in ("H", "R"):
            mk = load(df, kind)
            sec[f"lev_{kind}"] = run_set(mk, LEVS, a, b)["m"]
        for c in (0.005, 0.012):
            mk = load(df, "U", c=c)
            sec[f"lev_U_c{c}"] = run_set(mk, LEVS, a, b, tax=False)["m"]
        out[pn] = sec
        if pn == "full":
            mos = {k: monthly(m, rs["vals"][k], a, b)["r"].to_numpy() for k in ["B0", "B1"] + LEVS}
            mr = load(df, "R")
            rr = run_set(mr, LEVS, a, b, tax=False)
            mos.update({f"{k}-R": monthly(mr, rr["vals"][k], a, b)["r"].to_numpy() for k in LEVS[1:]})
            out["ruin"] = ruin_paths(mos)
            # 연도별 수익(보고용)
            yrs = {}
            for k in ["B0", "B1", "B"] + LEVS:
                s = pd.Series(rs["vals"][k][a:b + 1], index=m.dates[a:b + 1])
                yrs[k] = (s.groupby(s.index.year).last() / s.groupby(s.index.year).last().shift(1).fillna(1.0) - 1)
            out["yearly"] = {k: {int(y): float(x) for y, x in v.items()} for k, v in yrs.items()}
    with open(os.path.join(out_dir, "results_b.json"), "w") as f:
        json.dump(_js(out), f, ensure_ascii=False, indent=1)
    print("done", out["periods"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
