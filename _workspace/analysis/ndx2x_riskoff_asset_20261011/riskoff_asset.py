#!/usr/bin/env python3
"""나스닥2배-위험회피(RAUS_NDX_U_C) — 위험회피 구간 피난처 비교 (사전 등록 ``prereg.frozen.md``).

신호·2배 다리·정렬·집행 시점은 ``tools/replay/ra_us.py`` + ``global_alloc_b.py`` 를 그대로 import 해서 쓴다.
덧붙인 것은 피난처 열 · 자산별 한쪽 비용 · 세금을 새로 사는 자산에서 비례로 빼는 집행뿐이다.

    uv run --no-project --python 3.13 --with "pyarrow>=25" --with "pandas>=2.2" --with "numpy>=2" \
        python _workspace/analysis/ndx2x_riskoff_asset_20261011/riskoff_asset.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
for p in (os.path.join(ROOT, "tools"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from replay import global_alloc as G  # noqa: E402
from replay import global_alloc_b as GB  # noqa: E402
from replay import global_alloc_data as GD  # noqa: E402
from replay import gold_alloc as GA  # noqa: E402
from replay import ra_us as RU  # noqa: E402
from replay import regime_gate_alloc as RA  # noqa: E402
from replay import regime_v2 as V  # noqa: E402

TAX = G.TAX
COMMISSION = 0.000140527                       # 새 주계좌 한쪽 0.0140527%
RULE_C = (("T7", ">", 0.0), ("R4", "<=", -0.2))
MAP_C = {"00": 2.0, "01": 0.0, "10": 2.0, "11": 2.0}
DEP_RATE = 0.006                               # KIS 예수금 이용료 100만 원 초과 구간
COLS = ("LNDX", "ZERO", "DEP", "CDETF", "UST10", "UST30", "GOLD", "CASHSB")
IX = {c: i for i, c in enumerate(COLS)}
N = len(COLS)
FEE = {"LNDX": 0.0, "ZERO": 0.0, "DEP": 0.0, "CDETF": 0.0003, "UST10": 0.0015, "UST30": 0.0015,
       "GOLD": GA.GOLD_FEE, "CASHSB": G.FEE["CASH"]}
SALE_TAX = {"LNDX", "CDETF", "UST10", "UST30", "GOLD"}
INT_TAX = {"DEP", "CASHSB"}
# 호가 반폭 + 슬리피지(수수료 별도) — 낮음 · 중간 · 높음
SPREAD = {"LNDX": (0.0001, 0.0003, 0.0010), "CDETF": (0.00001, 0.00003, 0.0001),
          "UST10": (0.0002, 0.0005, 0.0015), "UST30": (0.00025, 0.0006, 0.0020),
          "GOLD": (0.0001, 0.0004, 0.0015)}
SCEN = ("low", "mid", "high")
OPTIONS = {"A": {"ZERO": 1.0}, "A'": {"DEP": 1.0}, "B": {"CDETF": 1.0}, "C": {"UST10": 1.0},
           "D": {"UST30": 1.0}, "E": {"GOLD": 1.0}, "F": {"UST10": 0.5, "GOLD": 0.5}}
OPT_NAMES = {"A": "원화 현금(이자 0)", "A'": "원화 현금 + 예수금 이용료 0.60%", "B": "금리형 ETF(CD금리)",
             "C": "미국채 10년 환노출", "D": "미국채 30년 환노출", "E": "금 환노출", "F": "미국채10년·금 반반"}
CANDS = ("B", "C", "D", "E", "F")
FULL = RU.US_WINS["FULL"]
HALVES = (("1995-2010", ("1995-01-01", "2010-12-31")), ("2011-2026", ("2011-01-01", "2026-12-31")))
CRISES = (("2001~03", ("2001-01-01", "2003-12-31")), ("2008", ("2008-01-01", "2008-12-31")),
          ("2020", ("2020-01-01", "2020-12-31")), ("2022", ("2022-01-01", "2022-12-31")))
SB_ENTRIES = os.path.join(ROOT, "_workspace/analysis/ra_us_20261006/scoreboard_entries.json")


# ═════════════════════════════ 시장 ═════════════════════════════

class Mkt:
    pass


def ust30_series(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    idx = pd.DatetimeIndex(df.index)
    y30 = GD._align(GD._fred(os.path.join(HERE, "input", "fred_DGS30.csv")) / 100.0, idx, True)
    dt_y = pd.Series(idx, index=idx).diff().dt.days.fillna(1).astype(float) / 365.0
    yp = y30.shift(1).bfill().to_numpy()
    loc = pd.Series(GD.par_bond_return(yp, y30.to_numpy(), dt_y.to_numpy(), n=30), index=idx)
    loc.iloc[0] = 0.0
    fx = df["fx_usdkrw"].astype(float)
    fxr = (fx / fx.shift(1)).fillna(1.0) - 1.0
    return (1 + loc) * (1 + fxr) - 1, loc


def load() -> tuple[Mkt, pd.DataFrame]:
    df = pd.read_parquet(RU.PARQUET)
    base = GB.load(df, "U")
    m = Mkt()
    m.dates = base.dates
    m.dt_y = base.dt_y
    T = len(m.dates)
    gold = GA.gold_columns(df, GA.load_gold_csv(os.path.join(RU.RAW, "usagold_xauusd_daily.csv")))
    u30, u30_loc = ust30_series(df)
    ret = np.zeros((T, N))
    ret[:, IX["LNDX"]] = base.ret[:, GB.COLS.index("LNDX")]
    ret[:, IX["DEP"]] = DEP_RATE * m.dt_y
    ret[:, IX["CDETF"]] = df["CASH_ret"].to_numpy(float)
    ret[:, IX["UST10"]] = df["UST10_ret"].to_numpy(float)
    ret[:, IX["UST30"]] = u30.to_numpy(float)
    ret[:, IX["GOLD"]] = gold["GOLD_ret"].to_numpy(float)
    ret[:, IX["CASHSB"]] = df["CASH_ret"].to_numpy(float)
    ret[0, :] = 0.0
    m.ret = ret
    m.fee = np.outer(m.dt_y, np.array([FEE[c] for c in COLS]))
    m.sale_tax = np.array([c in SALE_TAX for c in COLS])
    m.int_tax = np.array([c in INT_TAX for c in COLS])
    m.divtax = np.zeros(N)
    m.divtax[IX["LNDX"]] = base.divtax[GB.COLS.index("LNDX")]
    m.u30_loc = u30_loc
    m.gold = gold
    m.df = df
    # 신호 — RAUS_NDX_U_C 그대로
    f = RU.us_features("NDX", m.dates)
    m.keys = V.rule_keys(f, RULE_C)
    m.expo = RU.expo_of(m.keys, MAP_C)
    m.a, m.b = RA.win_ab(base, FULL)
    m.base = base
    return m, df


# ═════════════════════════════ 집행 ═════════════════════════════

def weights_of(d: dict) -> np.ndarray:
    w = np.zeros(N)
    for k, v in d.items():
        w[IX[k]] = v
    return w


def schedule(m: Mkt, shelter: dict) -> dict:
    a, b = m.a, m.b
    dps = set(int(i) for i in GB.decision_points(m.dates, "M") if a <= i < b)
    dps.add(a)
    for i in range(a + 1, b):
        if m.expo[i] != m.expo[i - 1]:
            dps.add(i)
    w_on, w_off = weights_of({"LNDX": 1.0}), weights_of(shelter)
    return {i: (w_on if m.expo[i] == 2.0 else w_off) for i in sorted(dps)}


def cost_vec(scen: str | None, shelter_override: float | None = None, lev_cost: float | None = None) -> np.ndarray:
    """한쪽 비용 벡터. scen=None → 재현용(비현금 0.19%)."""
    c = np.zeros(N)
    if scen is None:
        for k in ("LNDX", "CDETF", "UST10", "UST30", "GOLD"):
            c[IX[k]] = G.COST_ONE_WAY
        return c
    s = SCEN.index(scen)
    for k, v in SPREAD.items():
        c[IX[k]] = COMMISSION + v[s]
    if shelter_override is not None:
        for k in ("CDETF", "UST10", "UST30", "GOLD"):
            c[IX[k]] = shelter_override
    if lev_cost is not None:
        c[IX["LNDX"]] = lev_cost
    return c


def simulate(m: Mkt, sched: dict, cost: np.ndarray, tax: bool, start_col: str = "ZERO") -> dict:
    a, b = m.a, m.b
    r = m.ret - m.fee
    hold = np.zeros(N)
    hold[IX[start_col]] = 1.0
    basis = hold.copy()
    val = np.full(len(m.dates), np.nan)
    val[a] = 1.0
    exec_at = {i + 1: w for i, w in sched.items() if a <= i and i + 1 <= b}
    sh = np.ones(N, bool)
    sh[IX["LNDX"]] = False
    sh_cost = sh_fee = tax_paid = 0.0
    for t in range(a + 1, b + 1):
        prev = hold.copy()
        hold = hold * (1 + r[t])
        sh_fee += float((prev * m.fee[t])[sh].sum() / prev.sum())
        if tax:
            d = hold * m.divtax * m.dt_y[t]
            d = d + np.where(m.int_tax, hold * TAX * np.maximum(r[t], 0.0), 0.0)
            hold = hold - d
            tax_paid += float(d.sum())
        Vt = hold.sum()
        if t in exec_at and Vt > 0:
            tgt = exec_at[t]
            cur = hold / Vt
            dw = np.abs(tgt - cur)
            c = float((dw * cost).sum() * Vt)
            sh_cost += float((dw * cost)[sh].sum())
            tx = 0.0
            if tax:
                for _ in range(4):
                    new = tgt * (Vt - c - tx)
                    sell = (new < hold) & (hold > 0)
                    frac = np.where(sell, (hold - new) / np.where(hold > 0, hold, 1), 0.0)
                    gain = (hold - basis) * frac
                    tx_new = float(TAX * np.where(m.sale_tax & sell & (gain > 0), gain, 0.0).sum())
                    if abs(tx_new - tx) < 1e-15:
                        tx = tx_new
                        break
                    tx = tx_new
                new = tgt * (Vt - c - tx)
                for j in range(N):
                    if new[j] < hold[j] and hold[j] > 0:
                        basis[j] *= (1 - (hold[j] - new[j]) / hold[j])
                    elif new[j] > hold[j]:
                        basis[j] += new[j] - hold[j]
                tax_paid += tx
            else:
                new = tgt * (Vt - c)
            hold = new
            Vt = hold.sum()
        val[t] = Vt
    if tax:
        g = float(TAX * np.where(m.sale_tax, np.maximum(hold - basis, 0.0), 0.0).sum())
        val[b] -= g
        tax_paid += g
    return {"value": val, "sh_cost": sh_cost, "sh_fee": sh_fee, "tax": tax_paid}


def cagr_mdd(m: Mkt, v: np.ndarray) -> tuple[float, float]:
    x = v[m.a:m.b + 1]
    yrs = (m.dates[m.b] - m.dates[m.a]).days / 365.25
    return float((x[-1] / x[0]) ** (1 / yrs) - 1), float((x / np.maximum.accumulate(x) - 1).min())


def sub_cagr(m: Mkt, v: np.ndarray, eras) -> dict:
    st = RU.era_stats(m.dates[m.a:m.b + 1], v[m.a:m.b + 1], eras)
    return {k: {"cagr": x["cagr"], "ret": x["ret"], "mdd": x["mdd"]} for k, x in st.items()}


# ═════════════════════════════ 구간 ═════════════════════════════

def episodes(m: Mkt) -> list[tuple[int, int]]:
    """위험회피 결정 구간 [s, e] (결정일 기준). 보유 = s+1 종가 → e+2 종가, 보유일 = e−s+1."""
    out, s = [], None
    for i in range(m.a, m.b):
        if m.expo[i] == 0.0 and s is None:
            s = i
        elif m.expo[i] != 0.0 and s is not None:
            out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, m.b - 1))
    return out


def episode_returns(m: Mkt, shelter: dict, cost: np.ndarray, eps) -> list[float]:
    """구간 피난처 순수익(세전, 진입·퇴장 비용 포함, F 는 월말 재조정 무시 근사 아님 — 매일 비중 표류 후 월말 50:50)."""
    r = m.ret - m.fee
    w0 = weights_of(shelter)
    c1 = float((w0 * cost).sum())
    month_end = set(int(i) for i in GB.decision_points(m.dates, "M"))
    out = []
    for s, e in eps:
        h = w0 * (1 - c1)
        t_end = min(e + 2, m.b)
        for t in range(s + 2, t_end + 1):
            h = h * (1 + r[t])
            if (t - 1) in month_end and t < t_end and (t - 1) >= s + 1 and len(shelter) > 1:
                Vt = h.sum()
                dw = np.abs(w0 - h / Vt)
                h = w0 * (Vt - float((dw * cost).sum() * Vt))
        Vt = h.sum()
        Vt *= 1 - float((h / Vt * cost).sum())
        out.append(float(Vt - 1))
    return out


# ═════════════════════════════ 모형-실물 대조 ═════════════════════════════

def etf_check(m: Mkt) -> dict:
    files = sorted(glob.glob(os.path.join(ROOT, "data/archive/krx_etf_daily/parquet/*.parquet")))
    want = {"459580": "CDETF", "357870": "CDETF", "305080": "UST10", "308620": "UST10",
            "476760": "UST30", "411060": "GOLD", "418660": "LNDX"}
    etf = pd.concat([pd.read_parquet(f, columns=["ticker", "name", "bas_dd", "close_adj"]) for f in files])
    etf = etf[etf.ticker.isin(list(want))]
    out = {}
    mr = pd.DataFrame(m.ret - m.fee, index=m.dates, columns=COLS)
    for t, col in want.items():
        s = etf[etf.ticker == t].set_index("bas_dd")["close_adj"].astype(float).sort_index()
        s.index = pd.DatetimeIndex(s.index)
        common = s.index.intersection(mr.index)
        s = s.reindex(common)
        er = s.pct_change().iloc[1:]
        mo = mr[col].reindex(common).iloc[1:]
        yrs = (common[-1] - common[0]).days / 365.25
        diff = float((np.prod(1 + er) / np.prod(1 + mo)) ** (1 / yrs) - 1)
        w_e = (1 + er).groupby(np.arange(len(er)) // 5).prod() - 1
        w_m = (1 + mo).groupby(np.arange(len(mo)) // 5).prod() - 1
        w_m1 = (1 + mo.shift(-1).fillna(0)).groupby(np.arange(len(mo)) // 5).prod() - 1
        te = float((er - mo).std() * np.sqrt(252))
        out[t] = {"name": etf[etf.ticker == t]["name"].iloc[-1], "model": col, "from": str(common[0].date()),
                  "to": str(common[-1].date()), "etf_cagr": float(np.prod(1 + er) ** (1 / yrs) - 1),
                  "model_cagr_net_fee": float(np.prod(1 + mo) ** (1 / yrs) - 1), "diff_ann": diff,
                  "corr5_lag0": float(np.corrcoef(w_e, w_m)[0, 1]), "corr5_lead1": float(np.corrcoef(w_e, w_m1)[0, 1]),
                  "daily_te_ann": te}
    return out


def usd_bond_check(m: Mkt) -> dict:
    """미국채 모형(달러) ↔ IEF · TLT 수정종가(달러) — KRX 날짜 정렬(앞선 미국 관측)."""
    out = {}
    loc10 = m.df["UST10_lret"].astype(float)
    for sym, loc in (("IEF", loc10), ("TLT", m.u30_loc)):
        y = GD._yahoo_adj(os.path.join(HERE, "input", f"yahoo_{sym}.json")) if hasattr(GD, "_yahoo_adj") else None
        if y is None:
            with open(os.path.join(HERE, "input", f"yahoo_{sym}.json")) as fh:
                rr = json.load(fh)["chart"]["result"][0]
            off = rr["meta"].get("gmtoffset", 0)
            from datetime import datetime, timezone
            d = [datetime.fromtimestamp(t + off, tz=timezone.utc).date() for t in rr["timestamp"]]
            y = pd.Series(rr["indicators"]["adjclose"][0]["adjclose"], index=pd.DatetimeIndex(d), dtype=float).dropna()
            y = y[~y.index.duplicated(keep="last")].sort_index()
        ya = GD._align(y, m.dates, True)
        ok = ya.notna() & (ya.index >= pd.Timestamp(ya.first_valid_index()) + pd.Timedelta(days=5))
        er = ya[ok].pct_change().iloc[1:]
        lo = loc[ok].iloc[1:]
        yrs = (er.index[-1] - er.index[0]).days / 365.25
        yearly = pd.DataFrame({"etf": (1 + er).groupby(er.index.year).prod() - 1,
                               "model": (1 + lo).groupby(lo.index.year).prod() - 1})
        out[sym] = {"from": str(er.index[0].date()), "etf_cagr": float(np.prod(1 + er) ** (1 / yrs) - 1),
                    "model_cagr": float(np.prod(1 + lo) ** (1 / yrs) - 1),
                    "corr_daily": float(np.corrcoef(er, lo)[0, 1]),
                    "yearly": {int(k): {"etf": float(v.etf), "model": float(v.model)} for k, v in yearly.iterrows()}}
    return out


# ═════════════════════════════ 실행 ═════════════════════════════

def run_option(m: Mkt, opt: str, cost: np.ndarray) -> dict:
    sch = schedule(m, OPTIONS[opt])
    pre = simulate(m, sch, cost, tax=False)
    aft = simulate(m, sch, cost, tax=True)
    yrs = (m.dates[m.b] - m.dates[m.a]).days / 365.25
    c0, d0 = cagr_mdd(m, pre["value"])
    c1, d1 = cagr_mdd(m, aft["value"])
    return {"cagr_pre": c0, "mdd_pre": d0, "cagr_post": c1, "mdd_post": d1,
            "shelter_cost_yr": pre["sh_cost"] / yrs, "shelter_fee_yr": pre["sh_fee"] / yrs,
            "tax_drag": c0 - c1, "halves_post": sub_cagr(m, aft["value"], HALVES),
            "crises_post": sub_cagr(m, aft["value"], CRISES), "crises_pre": sub_cagr(m, pre["value"], CRISES),
            "_v_pre": pre["value"], "_v_post": aft["value"]}


def breakeven(m: Mkt, opt: str, ref_post: float) -> float | None:
    lev = cost_vec("high")[IX["LNDX"]]

    def gap(x):
        return run_post(m, opt, cost_vec("high", shelter_override=x, lev_cost=lev)) - ref_post

    lo, hi = 0.0, 0.05
    if gap(lo) <= 0:
        return 0.0
    if gap(hi) > 0:
        return None
    for _ in range(30):
        mid = (lo + hi) / 2
        if gap(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def run_post(m: Mkt, opt: str, cost: np.ndarray) -> float:
    return cagr_mdd(m, simulate(m, schedule(m, OPTIONS[opt]), cost, tax=True)["value"])[0]


def reproduce(m: Mkt) -> dict:
    sch = schedule(m, {"CASHSB": 1.0})
    c = cost_vec(None)
    pre = simulate(m, sch, c, tax=False, start_col="CASHSB")["value"][m.a:m.b + 1]
    aft = simulate(m, sch, c, tax=True, start_col="CASHSB")["value"]
    ent = next(e for e in json.load(open(SB_ENTRIES))["entries"] if e["id"] == "RAUS_NDX_U_C")
    cum = np.asarray(ent["curve"]["cum"], float)
    err = float(np.max(np.abs(pre / pre[0] / cum - 1))) if len(cum) == len(pre) else float("inf")
    at = cagr_mdd(m, aft)[0]
    return {"curve_err": err, "n": len(pre), "after_tax": at, "after_tax_ref": ent["after_tax_cagr"],
            "after_tax_err": abs(at - ent["after_tax_cagr"])}


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [clean(x) for x in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def main() -> None:
    t0 = time.time()
    m, df = load()
    rep = reproduce(m)
    print(f"[repro] curve err {rep['curve_err']:.2e} · after-tax {rep['after_tax']:.10f} vs {rep['after_tax_ref']:.10f}",
          flush=True)
    if rep["curve_err"] > 1e-9 or rep["after_tax_err"] > 1e-9:
        raise SystemExit("재현 불일치 — 멈춘다")
    eps = episodes(m)
    res = {"meta": {"prereg_sha256": open(os.path.join(HERE, "prereg.sha256")).read().split()[0],
                    "repro": rep, "period": [str(m.dates[m.a].date()), str(m.dates[m.b].date())],
                    "n_episodes": len(eps), "commission": COMMISSION, "spread": SPREAD, "fee": FEE,
                    "dep_rate": DEP_RATE,
                    "riskoff_share": float((m.expo[m.a:m.b] == 0).mean())},
           "episodes": [], "scen": {}}
    for s, e in eps:
        res["episodes"].append({"start": str(m.dates[s + 1].date()), "end": str(m.dates[min(e + 2, m.b)].date()),
                                "days": e - s + 1})
    # 30년물 단절일 상태
    d0 = pd.Timestamp("2006-02-10")
    k = int(np.searchsorted(m.dates, d0))
    res["meta"]["dgs30_splice_state"] = {"date": str(m.dates[k].date()), "expo": float(m.expo[k - 1])}
    for scen in SCEN:
        cv = cost_vec(scen)
        rows = {}
        for opt in OPTIONS:
            rows[opt] = run_option(m, opt, cv)
            rows[opt]["episode_ret"] = episode_returns(m, OPTIONS[opt], cv, eps)
        res["scen"][scen] = rows
        print(f"[{scen}] " + " · ".join(f"{o} {rows[o]['cagr_post']:+.4f}/{rows[o]['mdd_post']:+.3f}" for o in rows)
              + f" · {time.time() - t0:.0f}s", flush=True)
    # 판정 (높음 · 기준 A')
    H = res["scen"]["high"]
    ref = H["A'"]
    yrs = (m.dates[m.b] - m.dates[m.a]).days / 365.25
    judge = {}
    for x in CANDS:
        r = H[x]
        j1v = r["cagr_post"] - ref["cagr_post"]
        j2v = r["mdd_post"] - ref["mdd_post"]
        j3v = {h: r["halves_post"][h]["cagr"] - ref["halves_post"][h]["cagr"] for h in r["halves_post"]}
        ex = [(1 + a) / (1 + b) - 1 for a, b in zip(r["episode_ret"], ref["episode_ret"])]
        kbest = int(np.argmax(ex))
        vx = r["_v_pre"][m.b] / r["_v_pre"][m.a] / (1 + ex[kbest])
        j4v = float(vx ** (1 / yrs) - 1) - ref["cagr_pre"]
        judge[x] = {"J1": j1v, "J1_pass": j1v >= 0.003, "J2": j2v, "J2_pass": j2v >= -0.005,
                    "J3": j3v, "J3_pass": all(v > 0 for v in j3v.values()),
                    "J4": j4v, "J4_best_episode": res["episodes"][kbest], "J4_best_excess": ex[kbest],
                    "J4_pass": j4v >= 0}
        judge[x]["pass"] = all(judge[x][k] for k in ("J1_pass", "J2_pass", "J3_pass", "J4_pass"))
    res["judge"] = judge
    # 손익분기
    res["breakeven_one_way"] = {x: breakeven(m, x, ref["cagr_post"]) for x in CANDS}
    print(f"[breakeven] {res['breakeven_one_way']} · {time.time() - t0:.0f}s", flush=True)
    res["etf_check"] = etf_check(m)
    res["usd_bond_check"] = usd_bond_check(m)
    with open(os.path.join(HERE, "result.json"), "w") as fh:
        json.dump(clean(res), fh, ensure_ascii=False, indent=1)
    print(f"끝 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
