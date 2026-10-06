#!/usr/bin/env python3
"""장세 문 — ETF 자산배분 (사전 등록 ``regime_gate_20261006/prereg.frozen.md`` §1.4 · §2).

입력·집행 = 여러 나라 자산배분 2차 모형(``global_alloc_b``) 그대로: 원화 총수익 일 수익, 결정 i 의 비중을
i+1 종가에 집행, 비용 한쪽 0.19%(왕복 0.38%), 보수 차감, 세후판 = ``simulate(tax=True)``.
장세 = ``market_regime_label.label_after_closes`` — 종가 t 로 확정된 상태(= 세션 t+1 의 라벨).

§1.4 장세별 현금: 쉬는 칸이면 원화 현금(단기금리) 100%, 아니면 기본 배분.
§2 60/40 변형(「안정상승 레버리지」): V1·V2·V3 × 레버리지 비율 90%(민감도 70·100%) · 참고판 S&P500 2배.

    python tools/replay/regime_gate_alloc.py <out_dir>
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import global_alloc as G  # noqa: E402
from replay import global_alloc_b as GB  # noqa: E402
from replay import regime_gate as RG  # noqa: E402

PARQUET = os.path.join(RG.MAIN_REPO, "data/archive/global_long/global_daily_krw.parquet")
BASES = ("B0", "B1", "B")
BASE_NAMES = {"B0": "KOSPI200 보유", "B1": "60/40(KOSPI200 60 · 미국채10년 40)", "B": "7자산 동일 비중"}
ERAS = (("1997-2001", ("1997-01-01", "2001-12-31")), ("2002-2006", ("2002-01-01", "2006-12-31")),
        ("2007-2011", ("2007-01-01", "2011-12-31")), ("2012-2016", ("2012-01-01", "2016-12-31")),
        ("2017-2021", ("2017-01-01", "2021-12-31")), ("2022-2026", ("2022-01-01", "2026-10-02")))
BOOT_REPS = 5000
BOOT_BLOCK = 12.0
BOOT_SEED = 20261006


def win_ab(m: GB.Mkt, win) -> tuple[int, int]:
    """a = 창 첫 세션 바로 전 세션(그 종가에 현금으로 출발 · 첫 결정) · b = 창 마지막 세션."""
    a = int(m.dates.searchsorted(pd.Timestamp(win[0]))) - 1
    b = int(m.dates.searchsorted(pd.Timestamp(win[1]), "right")) - 1
    return max(a, 0), b


def states(m: GB.Mkt) -> np.ndarray:
    st = RG.state_after_close().reindex(m.dates)
    return st.to_numpy(object)


def session_labels_on(m: GB.Mkt) -> np.ndarray:
    lab = RG.label_series()
    return np.array([lab.get(d) for d in m.dates], dtype=object)


# ───────────────────────────── §1.4 장세별 현금 ─────────────────────────────

def gated_schedule(m: GB.Mkt, base: str, rest, a: int, b: int, st: np.ndarray) -> dict:
    tgt = GB.target(base)
    cash = np.zeros(GB.N)
    cash[GB.I_CASH] = 1.0
    rs = set(rest)
    resting = np.array([x in rs for x in st])
    dps = set(int(i) for i in GB.decision_points(m.dates, "M") if a <= i < b)
    dps.add(a)
    for i in range(a + 1, b):
        if resting[i] != resting[i - 1]:
            dps.add(i)
    return {i: (cash if resting[i] else tgt) for i in sorted(dps)}


def base_schedule(m: GB.Mkt, base: str, a: int, b: int) -> dict:
    return GB.schedule(m, base, a, b)


def daily_metrics(m: GB.Mkt, v: np.ndarray, a: int, b: int) -> dict:
    return GB.metrics(m, v, a, b)


def monthly_r(m: GB.Mkt, v: np.ndarray, a: int, b: int) -> pd.DataFrame:
    return GB.monthly(m, v, a, b)


def m_cagr(r: np.ndarray) -> float:
    v = np.prod(1 + r)
    return float(v ** (12 / len(r)) - 1) if v > 0 else -1.0


def boot_diff(rc: np.ndarray, rb: np.ndarray, cash: np.ndarray, reps: int = BOOT_REPS) -> dict:
    """정상 블록 부트스트랩(평균 12개월 · 같은 달 짝) — 차이(대상 − 기준)의 90% 구간."""
    rng = np.random.default_rng(BOOT_SEED)
    n = len(rc)
    out = {k: np.empty(reps) for k in ("cagr", "mar", "sharpe")}
    for k in range(reps):
        ix = G.stationary_idx(n, BOOT_BLOCK, rng)
        out["cagr"][k] = m_cagr(rc[ix]) - m_cagr(rb[ix])
        out["mar"][k] = G.m_mar(rc[ix]) - G.m_mar(rb[ix])
        out["sharpe"][k] = G.m_sharpe(rc[ix], cash[ix]) - G.m_sharpe(rb[ix], cash[ix])
    point = {"cagr": m_cagr(rc) - m_cagr(rb), "mar": G.m_mar(rc) - G.m_mar(rb),
             "sharpe": G.m_sharpe(rc, cash) - G.m_sharpe(rb, cash)}
    return {k: {"d": float(point[k]), "p05": float(np.percentile(out[k], 5)), "p95": float(np.percentile(out[k], 95))}
            for k in out}


def part1(m: GB.Mkt, out: dict) -> None:
    st = states(m)
    lab = session_labels_on(m)
    aT, bT = win_ab(m, RG.T_WIN)
    res = {}
    for base in BASES:
        rows = []
        for s in RG.subsets():
            sl = lab[aT + 1:bT + 1]
            ok = np.array([x is not None for x in sl])
            rr = float(np.isin(sl[ok], list(s)).mean()) if s else 0.0
            if rr > RG.REST_CAP:
                continue
            sched = gated_schedule(m, base, s, aT, bT, st) if s else base_schedule(m, base, aT, bT)
            v = GB.simulate(m, sched, aT, bT).value
            mt = daily_metrics(m, v, aT, bT)
            rows.append({"rest": list(s), "name": RG.set_name(s), "rest_ratio_T": rr, **mt})
        order = {tuple(s): i for i, s in enumerate(RG.subsets())}
        best = max(rows, key=lambda r: (r["mar"] if r["mar"] is not None else -9e9, -order[tuple(r["rest"])]))
        chosen = tuple(best["rest"])
        wins = {}
        for wn, win in RG.WINS.items():
            a, b = win_ab(m, win)
            sb = base_schedule(m, base, a, b)
            sg = gated_schedule(m, base, chosen, a, b, st) if chosen else sb
            r = {}
            for tag, sc in (("base", sb), ("gate", sg)):
                s0 = GB.simulate(m, sc, a, b)
                s1 = GB.simulate(m, sc, a, b, tax=True)
                mt = daily_metrics(m, s0.value, a, b)
                yrs = (m.dates[b] - m.dates[a]).days / 365.25
                vt = s1.value[a:b + 1]
                mt["after_tax_cagr"] = float((vt[-1] / vt[0]) ** (1 / yrs) - 1)
                mt["turnover_yr"] = s0.turnover / yrs
                mt["cost_yr"] = s0.cost / yrs
                mt["n_trades"] = s0.n_trades
                r[tag] = {"metrics": mt, "value": s0.value[a:b + 1], "dates": m.dates[a:b + 1]}
            vb_full = np.full(len(m.dates), np.nan)
            vg_full = np.full(len(m.dates), np.nan)
            vb_full[a:b + 1] = r["base"]["value"]
            vg_full[a:b + 1] = r["gate"]["value"]
            mb = monthly_r(m, vb_full, a, b)
            mg = monthly_r(m, vg_full, a, b)
            sl = lab[a + 1:b + 1]
            ok = np.array([x is not None for x in sl])
            wins[wn] = {"base": r["base"]["metrics"], "gate": r["gate"]["metrics"],
                        "rest_ratio": float(np.isin(sl[ok], list(chosen)).mean()) if chosen else 0.0,
                        "boot": boot_diff(mg["r"].to_numpy(), mb["r"].to_numpy(), mb["cash"].to_numpy())
                        if chosen else None,
                        "_curve_gate": (r["gate"]["dates"], r["gate"]["value"]),
                        "_curve_base": (r["base"]["dates"], r["base"]["value"])}
        res[base] = {"name": BASE_NAMES[base], "chosen": list(chosen), "chosen_name": RG.set_name(chosen),
                     "select_rows": sorted(rows, key=lambda r: -(r["mar"] if r["mar"] is not None else -9e9)),
                     "windows": wins}
        print(f"[alloc] {base} 고른 집합 {RG.set_name(chosen)} · T MAR {best['mar']:+.3f} "
              f"(쉬지 않음 {next(r['mar'] for r in rows if not r['rest']):+.3f})", flush=True)
    out["part1"] = res


# ───────────────────────────── §2 60/40 변형 ─────────────────────────────

def variant_schedule(m: GB.Mkt, kind: str, lev_w: float, lev_col: str, a: int, b: int, st: np.ndarray):
    """kind = V1(평소 60/40) · V2(평소 현금) · V3(첫 안정상승 전 60/40, 그 뒤 이탈 = 현금).
    반환 = (일정, 결정일별 상태 'L'/'N'/'C') — 결정 i 의 상태가 i+1 종가부터의 보유를 정한다."""
    b1 = GB.target("B1")
    cash = np.zeros(GB.N)
    cash[GB.I_CASH] = 1.0
    lev = np.zeros(GB.N)
    lev[GB.COLS.index(lev_col)] = lev_w
    lev[GB.I_CASH] = 1.0 - lev_w
    on = np.array([x == "UL" for x in st])
    seen = False
    cat = np.empty(len(m.dates), dtype=object)
    for i in range(a, b + 1):
        if on[i]:
            seen = True
            cat[i] = "L"
        elif kind == "V1":
            cat[i] = "N"
        elif kind == "V2":
            cat[i] = "C"
        else:
            cat[i] = "C" if seen else "N"
    dps = set(int(i) for i in GB.decision_points(m.dates, "M") if a <= i < b)
    dps.add(a)
    for i in range(a + 1, b):
        if cat[i] != cat[i - 1]:
            dps.add(i)
    w = {"L": lev, "N": b1, "C": cash}
    return {i: w[cat[i]] for i in sorted(dps)}, cat


def part2(m: GB.Mkt, out: dict) -> None:
    st = states(m)
    a, b = win_ab(m, RG.FULL)
    yrs = (m.dates[b] - m.dates[a]).days / 365.25
    runs = {}

    def rec(key, sched, cat=None, desc=""):
        s0 = GB.simulate(m, sched, a, b)
        s1 = GB.simulate(m, sched, a, b, tax=True)
        mt = daily_metrics(m, s0.value, a, b)
        vt = s1.value[a:b + 1]
        mt["after_tax_cagr"] = float((vt[-1] / vt[0]) ** (1 / yrs) - 1)
        mt["turnover_yr"] = s0.turnover / yrs
        mt["cost_yr"] = s0.cost / yrs
        mt["n_trades"] = s0.n_trades
        extra = {}
        if cat is not None:
            held = np.empty(b - a, dtype=object)          # 세션 t(a+1..b) 동안 들고 있던 상태 = 결정 t−1 의 상태
            cur = "C"                                     # a 종가 현금 출발
            exec_cat = {i + 1: cat[i] for i in sched}
            for t in range(a + 1, b + 1):
                held[t - a - 1] = cur                     # 세션 t 수익은 t 종가 집행 전 보유가 받는다
                if t in exec_cat:
                    cur = exec_cat[t]
            hs = pd.Series(held, index=m.dates[a + 1:b + 1])
            sw = int(((hs == "L") != (hs.shift() == "L")).iloc[1:].sum())
            extra = {"lev_day_ratio": float((hs == "L").mean()), "lev_switches": sw,
                     "lev_entries": int(((hs == "L") & (hs.shift() != "L")).iloc[1:].sum()),
                     "cash_day_ratio": float((hs == "C").mean()), "n6040_day_ratio": float((hs == "N").mean()),
                     "lev_day_ratio_by_era": {nm: float((hs.loc[w0:w1] == "L").mean()) for nm, (w0, w1) in ERAS},
                     "_held": hs}
        runs[key] = {"desc": desc, "metrics": mt, "value": s0.value[a:b + 1], "value_tax": vt, **extra}

    for nm in ("B0", "B1"):
        rec(nm, GB.schedule(m, nm, a, b), desc=BASE_NAMES[nm])
    one = {}
    for asset in ("LK200", "LSPX", "CASH"):
        w = np.zeros(GB.N)
        w[GB.COLS.index(asset)] = 1.0
        one[asset] = w
        rec(asset, {a: w}, desc=f"{asset} 보유")
    for kind in ("V1", "V2", "V3"):
        for lw in (0.9, 0.7, 1.0):
            sc, cat = variant_schedule(m, kind, lw, "LK200", a, b, st)
            rec(f"{kind}_{int(lw * 100)}", sc, cat, f"{kind} · 안정상승 KOSPI200 2배 {lw:.0%}")
        sc, cat = variant_schedule(m, kind, 0.9, "LSPX", a, b, st)
        rec(f"{kind}_SPX90", sc, cat, f"{kind} · 안정상승 S&P500 2배 90%(참고)")
    # 시대별
    for key, r in runs.items():
        s = pd.Series(r["value"], index=m.dates[a:b + 1])
        r["eras"] = {}
        for nm, (w0, w1) in ERAS:
            before = s.loc[:pd.Timestamp(w0) - pd.Timedelta(days=1)]
            seg = s.loc[w0:w1]
            d0, x0 = (before.index[-1], before.iloc[-1]) if len(before) else (seg.index[0], seg.iloc[0])
            v = np.r_[x0, seg.to_numpy()]
            y = (seg.index[-1] - d0).days / 365.25
            r["eras"][nm] = {"cagr": float((v[-1] / v[0]) ** (1 / y) - 1),
                             "mdd": float((v / np.maximum.accumulate(v) - 1).min())}
    # 부트스트랩: 변형 vs 60/40 · vs KOSPI200
    mo = {k: monthly_r(m, np.r_[np.full(a, np.nan), r["value"], np.full(len(m.dates) - b - 1, np.nan)], a, b)
          for k, r in runs.items()}
    for key, r in runs.items():
        if key[:2] in ("V1", "V2", "V3"):
            r["boot_vs_B1"] = boot_diff(mo[key]["r"].to_numpy(), mo["B1"]["r"].to_numpy(), mo["B1"]["cash"].to_numpy())
            r["boot_vs_B0"] = boot_diff(mo[key]["r"].to_numpy(), mo["B0"]["r"].to_numpy(), mo["B0"]["cash"].to_numpy())
        print(f"[alloc] {key:9s} CAGR {r['metrics']['cagr']:+.4f} MDD {r['metrics']['mdd']:+.3f} "
              f"MAR {r['metrics']['mar'] or float('nan'):+.3f} 세후 {r['metrics']['after_tax_cagr']:+.4f} "
              f"레버리지 일수 {r.get('lev_day_ratio', float('nan')):.3f}", flush=True)
    out["part2"] = {"window": [str(m.dates[a].date()), str(m.dates[b].date())], "runs": runs,
                    "dates": m.dates[a:b + 1]}


def load_market() -> GB.Mkt:
    return GB.load(pd.read_parquet(PARQUET), "U")
