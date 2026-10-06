#!/usr/bin/env python3
"""장세 판단 기준 재설계 — 백테스트 기준 (사전 등록 ``regime_v2_20261006/prereg.frozen.md``).

네 판을 두 용도로 잰다.
(가) 현행 6장세 라벨 + 「이름대로」 해석 · (나) 한 단계 당긴 해석(순환 순서의 다음 칸 행동) ·
(다) 라벨마다 학습 1997~2012 에서 행동을 정해 고정 · (라) 라벨 대신 특징 문턱 규칙(145개 중 학습 MAR 최대).
용도 ① 지수 노출(KOSPI200 원화 총수익 0 / 0.5 / 1 / 2배 — ``global_alloc_b`` 모형) ·
용도 ② 개별 전략 신규 진입 허용(donchian · VCP · kojiro — ``regime_gate`` 어댑터, 비용 왕복 0.38% 상수판).

    python tools/replay/regime_v2.py breadth                 # 시장 폭 계열(스크래치 캐시)
    python tools/replay/regime_v2.py index <out_dir>         # 용도 ① + 설명 표
    python tools/replay/regime_v2.py strat <out_dir> [sid…]  # 용도 ② (index 산출의 (라) 규칙을 읽는다)
    python tools/replay/regime_v2.py report <out_dir>        # 판정 · result.json · scoreboard_entries.json
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(_HERE), os.path.dirname(os.path.dirname(_HERE))):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import global_alloc as G  # noqa: E402
from replay import global_alloc_b as GB  # noqa: E402
from replay import regime_gate as RG  # noqa: E402  (운영 전략 import 용 더미 환경변수도 여기서 선다)
from replay import regime_gate_alloc as RA  # noqa: E402

ARCHIVE = os.path.join(RG.MAIN_REPO, "data/archive/krx_daily_long")
KOSDAQ_CSV = os.path.join(ARCHIVE, "index/krx_kosdaq.csv")
SCR = os.path.join(RG.SCRATCH_ROOT, "regime_v2")
BREADTH_CACHE = os.path.join(SCR, "breadth60.csv")

CELLS = RG.CELLS                                    # UL UH SL SH DL DH
NAMES = RG.NAMES
LADDER = (0.0, 0.5, 1.0, 2.0)
DIR = {"UL": 1, "UH": 1, "SL": 0, "SH": 0, "DL": -1, "DH": -1}
VOLX = {"UL": 0, "UH": 1, "SL": 0, "SH": 1, "DL": 0, "DH": 1}
NEXT = {"UL": "UH", "UH": "SH", "SH": "DH", "DH": "DL", "DL": "SL", "SL": "UL"}   # 순환 순서(사전 고정)
MIN_CELL_DAYS = 60
MIN_CELL_SIGS = 30
SWITCH_CAP = 12.0
COST_RT = 0.0038
SEEDS = tuple(range(16))
BOOT_REPS = 5000
BOOT_SEED = 20261006
STRATS = ("donchian", "vcp", "kojiro")
PLANS = ("ga", "na", "da", "ra")
PLAN_NAMES = {"ga": "(가) 현행 라벨·현행 해석", "na": "(나) 한 단계 당긴 해석", "da": "(다) 장세별 행동 학습",
              "ra": "(라) 새 판단 기준", "base": "쉬지 않음 / KOSPI200 보유"}
ERAS = RA.ERAS


def ladder_map() -> dict:
    """(가) 해석 — 사다리 칸 = clip(2 + 방향 − 변동, 0, 3)."""
    return {c: LADDER[min(3, max(0, 2 + DIR[c] - VOLX[c]))] for c in CELLS}


M_GA = ladder_map()
M_NA = {c: M_GA[NEXT[c]] for c in CELLS}


def allow_of(e: float) -> bool:
    return e >= 1.0


# ═════════════════════════════════ 재료 ═════════════════════════════════

def load_mkt() -> GB.Mkt:
    return RA.load_market()


def signal_close(m: GB.Mkt) -> pd.Series:
    s = pd.read_csv(RG.SERIES_CSV)
    s = s[s.close.notna()]
    ser = pd.Series(s.close.to_numpy(float), index=pd.DatetimeIndex(pd.to_datetime(s.date)))
    out = ser.reindex(m.dates)
    if out.isna().any():
        raise SystemExit(f"[v2] 판단 지수 계열이 자산 달력 {int(out.isna().sum())}일을 덮지 못한다")
    return out


def build_breadth() -> pd.Series:
    """시장 폭 = 6자리 숫자 · ETF류 이름 제외 종목 중 자기 최근 60행 close_adj 평균보다 위인 비율(그날 행 기준)."""
    import glob
    from src.engine.etf_like import is_etf_like
    files = sorted(glob.glob(os.path.join(ARCHIVE, "unified", "krx_unified_*.parquet")))
    parts = [pd.read_parquet(f, columns=["ticker", "name", "bas_dd", "close_adj"]) for f in files]
    df = pd.concat(parts, ignore_index=True)
    df = df[df.ticker.astype(str).str.fullmatch(r"\d{6}")]
    names = df.name.dropna().unique()
    etf = {n for n in names if is_etf_like(None, n)}
    df = df[~df.name.isin(etf) & (df.close_adj > 0)]
    df["bas_dd"] = pd.to_datetime(df.bas_dd)
    df = df.sort_values(["ticker", "bas_dd"])
    sma = df.groupby("ticker", sort=False).close_adj.transform(lambda x: x.rolling(60, min_periods=60).mean())
    ok = sma.notna()
    above = (df.close_adj > sma) & ok
    g = pd.DataFrame({"d": df.bas_dd, "ok": ok, "ab": above}).groupby("d")
    br = g.ab.sum() / g.ok.sum().replace(0, np.nan)
    os.makedirs(SCR, exist_ok=True)
    pd.DataFrame({"date": br.index.strftime("%Y-%m-%d"), "breadth60": br.to_numpy(),
                  "n": g.ok.sum().to_numpy()}).to_csv(BREADTH_CACHE, index=False)
    print(f"[v2] 시장 폭 {len(br)}일 · ETF류 이름 {len(etf)}개 제외 · {BREADTH_CACHE}", flush=True)
    return br


def load_breadth(m: GB.Mkt) -> pd.Series:
    b = pd.read_csv(BREADTH_CACHE)
    s = pd.Series(b.breadth60.to_numpy(float), index=pd.DatetimeIndex(pd.to_datetime(b.date)))
    return s.reindex(m.dates)


def features(m: GB.Mkt) -> pd.DataFrame:
    """종가 t 기준 특징(미래 정보 없음)."""
    c = signal_close(m)
    f = pd.DataFrame(index=m.dates)
    for k, n in (("T1", 20), ("T2", 60), ("T3", 120), ("T4", 200)):
        f[k] = c / c.rolling(n).mean() - 1
    for k, n in (("T5", 20), ("T6", 60), ("T7", 120)):
        s = c.rolling(n).mean()
        f[k] = s / s.shift(20) - 1
    kq = pd.read_csv(KOSDAQ_CSV)
    kq = pd.Series(kq.close.to_numpy(float), index=pd.DatetimeIndex(pd.to_datetime(kq.date)))
    kq = kq.reindex(m.dates).ffill(limit=5)
    f["T8"] = kq / kq.rolling(60).mean() - 1
    br = load_breadth(m)
    f["T9"] = br - 0.5
    lr = np.log(c).diff()
    f["R1"] = lr.rolling(20).std() * math.sqrt(252)
    f["R2"] = lr.rolling(60).std() * math.sqrt(252)
    f["R3"] = c / c.rolling(60).max() - 1
    f["R4"] = c / c.rolling(250).max() - 1
    f["R5"] = br
    return f


TREND = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9")
FEAT_NAMES = {"T1": "종가/20일선", "T2": "종가/60일선", "T3": "종가/120일선", "T4": "종가/200일선",
              "T5": "20일선 20일 기울기", "T6": "60일선 20일 기울기", "T7": "120일선 20일 기울기",
              "T8": "코스닥 종가/60일선", "T9": "시장 폭(60일선 위 비율) − 0.5",
              "R1": "20일 변동성", "R2": "60일 변동성", "R3": "60일 고점 대비", "R4": "250일 고점 대비", "R5": "시장 폭"}
RISK = (("R1", ">=", 0.16), ("R1", ">=", 0.20), ("R2", ">=", 0.16), ("R2", ">=", 0.20),
        ("R3", "<=", -0.05), ("R3", "<=", -0.10), ("R4", "<=", -0.10), ("R4", "<=", -0.20),
        ("R5", "<=", 0.30), ("R5", "<=", 0.40))


def candidates() -> list[tuple]:
    """후보 규칙 145개 — 조건 튜플 (특징, 부등호, 문턱) 1~2개. 순서 = 사전 등록 목록 순서(동점 깨기)."""
    tr = [(k, ">", 0.0) for k in TREND]
    out = [(t,) for t in tr] + [(r,) for r in RISK]
    out += [(t, r) for t in tr for r in RISK]
    out += [(tr[i], tr[j]) for i in range(len(tr)) for j in range(i + 1, len(tr))]
    return out


def cond_name(c) -> str:
    k, op, th = c
    if op == ">":
        return f"{FEAT_NAMES[k]} > 0"
    if k in ("R1", "R2", "R5"):
        return f"{FEAT_NAMES[k]} {op.replace('>=', '≥').replace('<=', '≤')} {th:.0%}" if k != "R5" else \
            f"{FEAT_NAMES[k]} ≤ {th:.1f}"
    return f"{FEAT_NAMES[k]} ≤ {th:.0%}"


def rule_name(rule) -> str:
    return " × ".join(cond_name(c) for c in rule)


def rule_keys(f: pd.DataFrame, rule) -> np.ndarray:
    """칸 키 = 조건 참/거짓 비트 문자열(결측 = 거짓)."""
    bits = []
    for k, op, th in rule:
        x = f[k].to_numpy(float)
        with np.errstate(invalid="ignore"):
            b = x > th if op == ">" else (x >= th if op == ">=" else x <= th)
        bits.append(np.where(np.isfinite(x), b, False))
    return np.array(["".join("1" if bb[i] else "0" for bb in bits) for i in range(len(f))], dtype=object)


def label_keys(m: GB.Mkt) -> np.ndarray:
    return RA.states(m)                                # 종가 t 로 확정된 6칸 코드(앞부분 None)


# ═════════════════════════════════ 지수 용도 ═════════════════════════════════

I_K = GB.COLS.index("K200")
I_L = GB.COLS.index("LK200")


def weights(e: float) -> np.ndarray:
    w = np.zeros(GB.N)
    if e == 2.0:
        w[I_L] = 1.0
    else:
        w[I_K] = e
        w[GB.I_CASH] = 1.0 - e
    return w


def expo_of(keys: np.ndarray, amap: dict) -> np.ndarray:
    return np.array([amap.get(k, 1.0) if k is not None else 1.0 for k in keys], dtype=float)


def schedule(m: GB.Mkt, expo: np.ndarray, a: int, b: int) -> dict:
    dps = set(int(i) for i in GB.decision_points(m.dates, "M") if a <= i < b)
    dps.add(a)
    for i in range(a + 1, b):
        if expo[i] != expo[i - 1]:
            dps.add(i)
    return {i: weights(float(expo[i])) for i in sorted(dps)}


def run_index(m: GB.Mkt, expo: np.ndarray, win, tax: bool = False) -> GB.Sim:
    a, b = RA.win_ab(m, win)
    return GB.simulate(m, schedule(m, expo, a, b), a, b, tax=tax)


def switches_per_year(m: GB.Mkt, expo: np.ndarray, win) -> float:
    a, b = RA.win_ab(m, win)
    x = expo[a:b + 1]
    yrs = (m.dates[b] - m.dates[a]).days / 365.25
    return float((x[1:] != x[:-1]).sum() / yrs)


def learn_index(m: GB.Mkt, keys: np.ndarray, win=RG.T_WIN) -> dict:
    """키마다 학습 창에서 그 상태로 들고 있던 세션(t → t+2) 수익의 평균 로그 성장이 가장 큰 노출."""
    a, b = RA.win_ab(m, win)
    r = m.ret - m.fee
    t = np.arange(a, b - 1)
    out, detail = {}, {}
    for k in sorted({x for x in keys[t] if x is not None}):
        sel = t[keys[t] == k] + 2
        n = int(len(sel))
        g = {}
        for e in LADDER:
            rr = r[sel, I_L] if e == 2.0 else e * r[sel, I_K] + (1 - e) * r[sel, GB.I_CASH]
            g[e] = float(np.mean(np.log1p(rr))) * 252 if n else float("nan")
        if n < MIN_CELL_DAYS:
            best = 1.0
        else:
            best = LADDER[0]
            for e in LADDER[1:]:
                if g[e] > g[best]:
                    best = e
        out[k] = best
        detail[k] = {"n": n, "growth_ann": g, "chosen": best, "default": n < MIN_CELL_DAYS}
    return {"map": out, "detail": detail}


def index_metrics(m: GB.Mkt, sim: GB.Sim, win) -> dict:
    a, b = RA.win_ab(m, win)
    mt = GB.metrics(m, sim.value, a, b)
    yrs = (m.dates[b] - m.dates[a]).days / 365.25
    mt["turnover_yr"] = sim.turnover / yrs
    mt["cost_yr"] = sim.cost / yrs
    return mt


def boot(rc: np.ndarray, rb: np.ndarray, cash: np.ndarray, reps: int = BOOT_REPS) -> dict:
    """정상 블록 부트스트랩(평균 12개월 · 같은 달 짝) — 차이(대상 − 기준). 90% · Bonferroni(3) 하한."""
    rng = np.random.default_rng(BOOT_SEED)
    n = len(rc)
    acc = {k: np.empty(reps) for k in ("mar", "cagr", "sharpe")}
    for k in range(reps):
        ix = G.stationary_idx(n, 12.0, rng)
        acc["mar"][k] = G.m_mar(rc[ix]) - G.m_mar(rb[ix])
        acc["cagr"][k] = RA.m_cagr(rc[ix]) - RA.m_cagr(rb[ix])
        acc["sharpe"][k] = G.m_sharpe(rc[ix], cash[ix]) - G.m_sharpe(rb[ix], cash[ix])
    pt = {"mar": G.m_mar(rc) - G.m_mar(rb), "cagr": RA.m_cagr(rc) - RA.m_cagr(rb),
          "sharpe": G.m_sharpe(rc, cash) - G.m_sharpe(rb, cash)}
    return {k: {"d": float(pt[k]), "p05": float(np.percentile(acc[k], 5)), "p95": float(np.percentile(acc[k], 95)),
                "p_bonf3": float(np.percentile(acc[k], 100 * 0.10 / 3))}
            for k in acc}


def era_stats(dates: pd.DatetimeIndex, v: np.ndarray) -> dict:
    """시대별 연 복리 · 그 시대 안 최대 낙폭 · MAR — 시대 직전 마지막 값에서 출발(``regime_gate_alloc`` 과 같다)."""
    s = pd.Series(np.asarray(v, float), index=pd.DatetimeIndex(dates))
    out = {}
    for nm, (w0, w1) in ERAS:
        before = s.loc[:pd.Timestamp(w0) - pd.Timedelta(days=1)]
        seg = s.loc[w0:w1]
        if not len(seg):
            continue
        d0, x0 = (before.index[-1], before.iloc[-1]) if len(before) else (seg.index[0], seg.iloc[0])
        x = np.r_[x0, seg.to_numpy()]
        y = (seg.index[-1] - d0).days / 365.25
        cg = float((x[-1] / x[0]) ** (1 / y) - 1) if x[-1] > 0 else -1.0
        mdd = float((x / np.maximum.accumulate(x) - 1).min())
        out[nm] = {"cagr": cg, "mdd": mdd, "mar": cg / abs(mdd) if mdd < 0 else None}
    return out


def empirical_next(keys: np.ndarray, m: GB.Mkt, win=RG.T_WIN) -> dict:
    """학습 창의 실제 라벨 전이 — 칸이 바뀐 순간의 다음 칸 빈도(수익 정보 없음)."""
    a, b = RA.win_ab(m, win)
    cnt = {c: {} for c in CELLS}
    for t in range(a + 1, b + 1):
        x, y = keys[t - 1], keys[t]
        if x is not None and y is not None and x != y:
            cnt[x][y] = cnt[x].get(y, 0) + 1
    nxt = {}
    for c in CELLS:
        if cnt[c]:
            nxt[c] = max(cnt[c], key=lambda y: (cnt[c][y], -CELLS.index(y)))
    return {"counts": cnt, "next": nxt}


def eta2(x: np.ndarray, keys: np.ndarray) -> float:
    ok = np.isfinite(x) & np.array([k is not None for k in keys])
    x, k = x[ok], keys[ok]
    if len(x) < 2:
        return float("nan")
    mu = x.mean()
    tot = float(((x - mu) ** 2).sum())
    btw = sum(float((k == c).sum()) * (float(x[k == c].mean()) - mu) ** 2 for c in set(k))
    return btw / tot if tot > 0 else float("nan")


def win_slice(m: GB.Mkt, win) -> slice:
    a, b = RA.win_ab(m, win)
    return slice(a + 1, b + 1)


def index_stage(out_dir: str) -> dict:
    t0 = time.time()
    m = load_mkt()
    f = features(m)
    c = signal_close(m)
    lk = label_keys(m)
    # 라벨 재현 관문 — 세션 라벨(D−1 종가) = 종가 상태의 한 칸 밀기
    lab = RG.label_series()
    skm = {m.dates[i]: lk[i - 1] for i in range(1, len(m.dates))}
    bad = sum(1 for d, x in lab.items() if d in skm and skm[d] != x)
    full_counts = lab.loc[RG.FULL[0]:RG.FULL[1]].value_counts().to_dict()
    print(f"[v2] 라벨 재현: 불일치 {bad} · 30년 칸 수 {full_counts}", flush=True)
    if bad:
        raise SystemExit("[v2] 라벨 불일치")

    plans: dict = {}
    plans["base"] = {"keys": np.array(["all"] * len(lk), dtype=object), "map": {"all": 1.0}}
    plans["ga"] = {"keys": lk, "map": dict(M_GA)}
    plans["na"] = {"keys": lk, "map": dict(M_NA)}
    da = learn_index(m, lk)
    plans["da"] = {"keys": lk, "map": da["map"], "learn": da["detail"]}
    emp = empirical_next(lk, m)
    plans["na_emp"] = {"keys": lk, "map": {x: M_GA[emp["next"].get(x, x)] for x in CELLS}, "empirical_next": emp}

    # (라) 후보 145개
    rows = []
    fwd20 = (c.shift(-20) / c - 1).to_numpy()
    fwd60 = (c.shift(-60) / c - 1).to_numpy()
    sT = win_slice(m, RG.T_WIN)
    for i, rule in enumerate(candidates()):
        keys = rule_keys(f, rule)
        lr = learn_index(m, keys)
        expo = expo_of(keys, lr["map"])
        sw = switches_per_year(m, expo, RG.T_WIN)
        sim = run_index(m, expo, RG.T_WIN)
        mt = index_metrics(m, sim, RG.T_WIN)
        rows.append({"i": i, "rule": [list(x) for x in rule], "name": rule_name(rule), "n_cond": len(rule),
                     "map": lr["map"], "learn": lr["detail"], "switch_T": sw, "eligible": sw <= SWITCH_CAP,
                     "T_mar": mt["mar"], "T_cagr": mt["cagr"], "T_mdd": mt["mdd"], "T_sharpe": mt["sharpe"],
                     "eta2_fwd20_T": eta2(fwd20[sT], keys[sT]), "eta2_fwd60_T": eta2(fwd60[sT], keys[sT])})
    elig = [r for r in rows if r["eligible"] and r["T_mar"] is not None]
    best = max(elig, key=lambda r: (r["T_mar"], -r["n_cond"], -r["i"]))
    rule = tuple(tuple(x) for x in best["rule"])
    rk = rule_keys(f, rule)
    plans["ra"] = {"keys": rk, "map": best["map"], "rule": best["rule"], "rule_name": best["name"],
                   "learn": best["learn"]}
    print(f"[v2] (라) 후보 {len(rows)} · 전환 상한 통과 {len(elig)} · 고른 규칙 {best['name']} "
          f"· T MAR {best['T_mar']:+.3f} · 행동 {best['map']} · {time.time() - t0:.0f}s", flush=True)

    # 판마다 창 실행
    res = {}
    for p, d in plans.items():
        expo = expo_of(d["keys"], d["map"])
        r = {"windows": {}}
        for wn, win in RG.WINS.items():
            sim = run_index(m, expo, win)
            a, b = RA.win_ab(m, win)
            mt = index_metrics(m, sim, win)
            mt["switch_yr"] = switches_per_year(m, expo, win)
            held = expo[a:b]                                       # 결정 t → 세션 t+2 보유(대략)
            mt["expo_share"] = {str(e): float((held == e).mean()) for e in LADDER}
            mo = GB.monthly(m, sim.value, a, b)
            r["windows"][wn] = {"metrics": mt, "monthly": mo, "value": sim.value[a:b + 1], "dates": m.dates[a:b + 1]}
            if wn == "FULL":
                st = GB.simulate(m, schedule(m, expo, a, b), a, b, tax=True)
                vt = st.value[a:b + 1]
                yrs = (m.dates[b] - m.dates[a]).days / 365.25
                r["after_tax_cagr"] = float((vt[-1] / vt[0]) ** (1 / yrs) - 1)
                r["eras"] = era_stats(m.dates[a:b + 1], sim.value[a:b + 1])
        res[p] = r
        w = r["windows"]
        print(f"[v2] 지수 {p:6s} T {w['T']['metrics']['cagr']:+.3f}/{w['T']['metrics']['mar'] or 0:+.3f} "
              f"V {w['V']['metrics']['cagr']:+.3f}/{w['V']['metrics']['mar'] or 0:+.3f} "
              f"H {w['H']['metrics']['cagr']:+.3f}/{w['H']['metrics']['mar'] or 0:+.3f}", flush=True)

    # 부트스트랩 — 판 − (가) · 판 − KOSPI200 보유
    for p in res:
        res[p]["boot_vs_ga"], res[p]["boot_vs_base"] = {}, {}
        for wn in ("T", "V", "H"):
            mo, mg, mb = (res[p]["windows"][wn]["monthly"], res["ga"]["windows"][wn]["monthly"],
                          res["base"]["windows"][wn]["monthly"])
            if p != "ga":
                res[p]["boot_vs_ga"][wn] = boot(mo["r"].to_numpy(), mg["r"].to_numpy(), mg["cash"].to_numpy())
            if p != "base":
                res[p]["boot_vs_base"][wn] = boot(mo["r"].to_numpy(), mb["r"].to_numpy(), mb["cash"].to_numpy())

    desc = describe(m, c, lk, f, rows, plans)
    out = {"plans": {p: {k: v for k, v in d.items() if k != "keys"} for p, d in plans.items()}, "res": res,
           "cand_rows": rows, "desc": desc, "label_counts_30y": full_counts,
           "maps": {"M_GA": M_GA, "M_NA": M_NA, "NEXT": NEXT}}
    os.makedirs(SCR, exist_ok=True)
    with open(os.path.join(SCR, "index.pkl"), "wb") as fh:
        pickle.dump({**out, "keys": {p: d["keys"] for p, d in plans.items()}, "dates": m.dates}, fh)
    with open(os.path.join(out_dir, "ra_rule.json"), "w") as fh:
        json.dump({"rule": best["rule"], "name": best["name"], "map": best["map"]}, fh, ensure_ascii=False, indent=1)
    print(f"[v2] 지수 단계 끝 {time.time() - t0:.0f}s", flush=True)
    return out


def describe(m, c, lk, f, rows, plans) -> dict:
    """설명용 표 — 라벨 뒤 20일 수익 · 상승 두 칸 보유일 에지 · (라) 상위 5 분리도."""
    out = {}
    lab = RG.label_series()
    sess = pd.Series(lab.reindex(m.dates).to_numpy(object), index=m.dates)
    # 1) 라벨 뒤 20일 수익 C(D+19)/C(D−1) − 1 · 해석 순위 상관
    fwd = c.shift(-19) / c.shift(1) - 1
    tab = {}
    for wn, (w0, w1) in RG.WINS.items():
        s, x = sess.loc[w0:w1], fwd.loc[w0:w1]
        mean = {cc: float(x[s == cc].mean()) for cc in CELLS}
        nn = {cc: int((s == cc).sum()) for cc in CELLS}
        vals = pd.Series(mean)
        tab[wn] = {"mean": mean, "n": nn,
                   "spearman_ga": float(vals.corr(pd.Series(M_GA), method="spearman")),
                   "spearman_na": float(vals.corr(pd.Series(M_NA), method="spearman")),
                   "next_mean": {cc: mean[NEXT[cc]] for cc in CELLS}}
    out["fwd20_by_label"] = tab
    # 2) 상승 두 칸 보유일(그날 K200 총수익) 연율 − 나머지 · 일 단위 정상 블록 부트스트랩(평균 20세션)
    rk = pd.Series(m.ret[:, I_K] - m.fee[:, I_K], index=m.dates)
    edge = {}
    rng0 = BOOT_SEED
    for wn, (w0, w1) in RG.WINS.items():
        s = sess.loc[w0:w1].to_numpy(object)
        r = rk.loc[w0:w1].to_numpy(float)
        ok = np.array([x is not None and x == x for x in s])
        s, r = s[ok], r[ok]
        e = {}
        for nm, grp in (("UL+UH", ("UL", "UH")), ("UL", ("UL",)), ("UH", ("UH",))):
            g = np.isin(s, grp)
            pt = (r[g].mean() - r[~g].mean()) * 252
            rng = np.random.default_rng(rng0)
            bs = np.empty(BOOT_REPS)
            for k in range(BOOT_REPS):
                ix = G.stationary_idx(len(r), 20.0, rng)
                gg = g[ix]
                bs[k] = (r[ix][gg].mean() - r[ix][~gg].mean()) * 252 if gg.any() and (~gg).any() else np.nan
            e[nm] = {"diff_ann": float(pt), "p05": float(np.nanpercentile(bs, 5)),
                     "p95": float(np.nanpercentile(bs, 95)), "n_in": int(g.sum()), "n_out": int((~g).sum()),
                     "ann_in": float(r[g].mean() * 252), "ann_out": float(r[~g].mean() * 252),
                     "vol_in": float(r[g].std(ddof=1) * math.sqrt(252)),
                     "vol_out": float(r[~g].std(ddof=1) * math.sqrt(252))}
        per = {cc: {"n": int((s == cc).sum()), "ann": float(r[s == cc].mean() * 252) if (s == cc).any() else None,
                    "vol": float(r[s == cc].std(ddof=1) * math.sqrt(252)) if (s == cc).sum() > 1 else None}
               for cc in CELLS}
        edge[wn] = {"groups": e, "per_label": per}
    out["edge"] = edge
    # 3) (라) 상위 5 (전환 상한 통과 · T MAR 순)
    el = sorted([r for r in rows if r["eligible"] and r["T_mar"] is not None], key=lambda r: -r["T_mar"])
    out["ra_top5"] = [{k: r[k] for k in ("name", "map", "switch_T", "T_mar", "T_cagr", "T_mdd", "eta2_fwd20_T",
                                         "eta2_fwd60_T")} for r in el[:5]]
    out["ra_n_eligible"] = len(el)
    out["ra_top_eta2_fwd20"] = sorted(({"name": r["name"], "eta2": r["eta2_fwd20_T"]} for r in rows),
                                      key=lambda z: -(z["eta2"] if z["eta2"] == z["eta2"] else -1))[:5]
    # 4) (라) 칸별 앞 20·60일 수익 · 보유일 연율(T·V·H)
    rkk = plans["ra"]["keys"]
    f20 = (c.shift(-20) / c - 1).to_numpy()
    f60 = (c.shift(-60) / c - 1).to_numpy()
    cells = {}
    for wn, win in RG.WINS.items():
        sl = win_slice(m, win)
        kk = rkk[sl]
        r2 = np.r_[m.ret[:, I_K] - m.fee[:, I_K], [np.nan, np.nan]][2:][sl]     # 상태 t → 세션 t+2 수익
        cells[wn] = {k: {"n": int((kk == k).sum()), "fwd20": float(np.nanmean(f20[sl][kk == k])),
                         "fwd60": float(np.nanmean(f60[sl][kk == k])),
                         "held_ann": float(np.nanmean(r2[kk == k]) * 252)} for k in sorted(set(kk))}
    out["ra_cells"] = cells
    return out


# ═════════════════════════════════ 전략 용도 ═════════════════════════════════

def load_bundle(sid: str) -> RG.Bundle:
    """``regime_gate`` 어댑터 + 비용 왕복 0.38% 상수판으로 교체."""
    b = RG.load_bundle(sid)
    if sid == "kojiro":
        from replay.strategies import kojiro_y30 as Y
        b.cost = Y.const_cost(b.cal, COST_RT)
    elif sid == "donchian":
        from replay.strategies import donchian_y30 as D
        b.era = D.Costs(b.cal, flat=COST_RT)
    elif sid in ("vcp", "bfb"):
        from replay.strategies import y30_bfbvcp as YB
        b.cost = YB.EraCostY(b.cal, const=COST_RT)
    else:
        raise SystemExit(sid)
    return b


def session_keys_on(cal: pd.DatetimeIndex, dates: pd.DatetimeIndex, keys: np.ndarray) -> np.ndarray:
    """세션 D 의 키 = 지수 달력에서 D 바로 앞 종가의 상태. 지수 달력에 없는 날 = None(허용)."""
    skm = {dates[i]: keys[i - 1] for i in range(1, len(dates))}
    return np.array([skm.get(pd.Timestamp(d)) for d in cal], dtype=object)


def allow_on(cal_keys: np.ndarray, amap: dict) -> np.ndarray:
    return np.array([True if k is None else bool(amap.get(k, True)) for k in cal_keys], dtype=bool)


_B = None
_MASKS: dict = {}


def _job(args):
    name, win, seeds = args
    mask = _MASKS[name]
    runs, dates = _B.run(_B.keep(mask), win, seeds)
    return name, win, runs, dates, int(mask.sum())


def _pmap(jobs, nproc):
    if nproc <= 1:
        return [_job(j) for j in jobs]
    with mp.get_context("fork").Pool(nproc) as pool:
        return pool.map(_job, jobs, chunksize=1)


def in_win(cal: pd.DatetimeIndex, gd: np.ndarray, win) -> np.ndarray:
    g0 = int(cal.searchsorted(pd.Timestamp(win[0])))
    g1 = int(cal.searchsorted(pd.Timestamp(win[1]), "right")) - 1
    return (gd >= g0) & (gd <= g1)


def strat_stage(sid: str, out_dir: str, nproc: int) -> dict:
    global _B, _MASKS
    t0 = time.time()
    with open(os.path.join(SCR, "index.pkl"), "rb") as fh:
        ix = pickle.load(fh)
    dates = ix["dates"]
    _B = load_bundle(sid)
    cal = _B.cal
    gd = _B.entry_gd()
    lk_cal = session_keys_on(cal, dates, ix["keys"]["ga"])
    rk_cal = session_keys_on(cal, dates, ix["keys"]["ra"])
    # 라벨 관문 — 운영 session_labels 와 같아야 한다
    ref = RG.labels_on(cal, RG.label_series())
    bad = int(sum(1 for a_, b_ in zip(lk_cal, ref) if a_ is not None and b_ is not None and a_ != b_))
    if bad:
        raise SystemExit(f"[v2 {sid}] 세션 라벨 불일치 {bad}")
    lk_sig, rk_sig = lk_cal[gd], rk_cal[gd]
    inT = in_win(cal, gd, RG.T_WIN)

    # 학습 — 칸 하나에서만 진입 허용한 학습 창 계좌(씨앗 16)
    _MASKS = {}
    learn_jobs, learn = [], {"da": {}, "ra": {}}
    for plan, ks in (("da", lk_sig), ("ra", rk_sig)):
        cells = sorted({k for k in ks if k is not None})
        for k in cells:
            nT = int((inT & (ks == k)).sum())
            learn[plan][k] = {"n_sig_T": nT}
            if nT < MIN_CELL_SIGS:
                learn[plan][k].update({"allow": True, "default": True})
                continue
            nm = f"only_{plan}_{k}"
            _MASKS[nm] = ks == k
            learn_jobs.append((nm, RG.T_WIN, SEEDS))
    for nm, win, runs, d, n_kept in _pmap(learn_jobs, nproc):
        _, plan, k = nm.split("_", 2)
        sm = RG.seed_summary(runs, float(RG.C.BUDGET_C7), d)
        learn[plan][k].update({"allow": bool(sm["cagr_median"] > 0), "default": False,
                               "cagr_median_T": sm["cagr_median"], "mdd_median_T": sm["mdd_median"],
                               "n_kept": n_kept})
    amaps = {"base": None,
             "ga": {c: allow_of(M_GA[c]) for c in CELLS},
             "na": {c: allow_of(M_NA[c]) for c in CELLS},
             "da": {k: v["allow"] for k, v in learn["da"].items()},
             "ra": {k: v["allow"] for k, v in learn["ra"].items()}}
    print(f"[v2 {sid}] 학습 {time.time() - t0:.0f}s · (다) {amaps['da']} · (라) {amaps['ra']}", flush=True)

    allow_cal = {}
    _MASKS = {}
    for p, amap in amaps.items():
        if amap is None:
            ac = np.ones(len(cal), bool)
        else:
            ac = allow_on(rk_cal if p == "ra" else lk_cal, amap)
        allow_cal[p] = ac
        _MASKS[p] = ac[gd]
    jobs = [(p, w, SEEDS) for p in amaps for w in RG.WINS.values()]
    res = {}
    for p, win, runs, d, n_kept in _pmap(jobs, nproc):
        wn = next(k for k, v in RG.WINS.items() if v == win)
        g0 = int(cal.searchsorted(pd.Timestamp(win[0])))
        g1 = int(cal.searchsorted(pd.Timestamp(win[1]), "right")) - 1
        res[(p, wn)] = {"dates": [str(x.date()) for x in d], "runs": [(int(s), np.asarray(e, float)) for s, e in runs],
                        "n_kept": n_kept, "n_all_win": int(in_win(cal, gd, win).sum()),
                        "n_kept_win": int((_MASKS[p] & in_win(cal, gd, win)).sum()),
                        "allow_ratio": float(allow_cal[p][g0:g1 + 1].mean())}
    with open(os.path.join(SCR, f"strat_{sid}.pkl"), "wb") as fh:
        pickle.dump({"sid": sid, "learn": learn, "amaps": amaps, "start": float(RG.C.BUDGET_C7), "res": res}, fh)
    print(f"[v2 {sid}] 끝 {time.time() - t0:.0f}s", flush=True)
    return res


# ═════════════════════════════════ 판정 · 산출 ═════════════════════════════════

def judge(bv: dict, bh: dict) -> str:
    if bv["mar"]["p05"] > 0:
        return "우위" if bh["mar"]["d"] > 0 else "검증만"
    if bv["mar"]["p95"] < 0:
        return "(가) 가 낫다"
    return "가려지지 않음"


def _month_ret(SB, dates, v) -> pd.Series:
    me = SB.month_points(pd.DatetimeIndex(dates), np.asarray(v, float))
    r = me.pct_change().dropna()
    r.index = r.index.to_period("M")
    return r


def _start_dates(rec) -> pd.DatetimeIndex:
    d0 = pd.Timestamp(rec["dates"][0]) - pd.Timedelta(days=1)
    return pd.DatetimeIndex([d0]).append(pd.DatetimeIndex(rec["dates"]))


def seed_mean_monthly(SB, rec, start) -> pd.Series:
    dates = _start_dates(rec)
    return pd.concat([_month_ret(SB, dates, np.r_[start, e]) for _, e in rec["runs"]], axis=1).mean(axis=1)


def rep_curve(rec, start):
    finals = np.array([float(e[-1]) for _, e in rec["runs"]])
    k = int(np.argsort(finals, kind="stable")[(len(finals) - 1) // 2])
    return _start_dates(rec), np.r_[start, np.asarray(rec["runs"][k][1], float)], int(rec["runs"][k][0])


def entry(id_, name, desc, group, dates, v, mt, *, source="", **opt) -> dict:
    d = pd.DatetimeIndex(dates)
    v = np.asarray(v, float)
    return {"id": id_, "name": name, "desc": desc, "group": group, "group_title": "장세 판단 재설계(regime_v2) · 참고",
            "status": "참고", "status_ref": "_workspace/analysis/regime_v2_20261006/result.md", "source": source,
            "period": [str(d[0].date()), str(d[-1].date())],
            "curve": {"dates": [str(x.date()) for x in d], "cum": [float(x / v[0]) for x in v]},
            "yearly": {y: x["ret"] for y, x in mt["yearly"].items()}, **opt}


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()
                if not str(k).startswith("_") and k not in ("value", "monthly", "runs", "dates", "keys")}
    if isinstance(o, (list, tuple)):
        return [_clean(x) for x in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (pd.Timestamp,)):
        return str(o.date())
    return o


def _clean_e(o):
    """성적표 입력용 — 키를 버리지 않는다(``curve.dates`` 보존)."""
    if isinstance(o, dict):
        return {str(k): _clean_e(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean_e(x) for x in o]
    return _clean(o)


IDX_DESC = {
    "ga": "6장세 라벨을 이름대로 — 안정상승 2배 · 변동상승·안정횡보 1배 · 변동횡보·안정하락 0.5배 · 변동하락 현금",
    "na": "라벨이 X 면 순환 순서 다음 칸의 (가) 행동 — 안정횡보 2배 · 안정상승·안정하락 1배 · 변동상승·변동하락 0.5배 · 변동횡보 현금",
    "da": "라벨마다 1997~2012 학습에서 평균 로그 성장이 가장 큰 노출(0·0.5·1·2배)을 골라 고정",
    "ra": "라벨 대신 특징 문턱 규칙(145개 중 1997~2012 MAR 최대) · 칸별 노출 학습 고정",
}


def report(out_dir: str) -> dict:
    from replay import scoreboard as SB
    with open(os.path.join(SCR, "index.pkl"), "rb") as fh:
        ix = pickle.load(fh)
    m = load_mkt()
    rf = pd.Series(np.cumprod(1 + m.ret[:, GB.I_CASH]), index=m.dates)
    bench = pd.Series(np.cumprod(1 + (m.ret[:, I_K] - m.fee[:, I_K])), index=m.dates)
    entries, out = [], {"meta": {}, "index": {}, "strategies": {}}
    # 지수 용도
    for p, r in ix["res"].items():
        w = r["windows"]["FULL"]
        mt = SB.compute_metrics(w["dates"], w["value"], rf, bench)
        row = {"windows": {wn: x["metrics"] for wn, x in r["windows"].items()}, "full_sb": mt, "eras": r["eras"],
               "after_tax_cagr": r["after_tax_cagr"], "boot_vs_ga": r["boot_vs_ga"], "boot_vs_base": r["boot_vs_base"]}
        if p in ("na", "da", "ra", "na_emp"):
            row["judge"] = judge(r["boot_vs_ga"]["V"], r["boot_vs_ga"]["H"])
        out["index"][p] = row
        if p in PLANS:
            fm = r["windows"]["FULL"]["metrics"]
            nm = PLAN_NAMES[p] + (f" — {ix['plans']['ra']['rule_name']}" if p == "ra" else "")
            entries.append(entry(f"R2_IDX_{p}", f"지수 노출 {nm}", IDX_DESC[p], "regime_v2_index", w["dates"],
                                 w["value"], mt, source="tools/replay/regime_v2.py index_stage",
                                 turnover_yr=fm["turnover_yr"], cost_yr=fm["cost_yr"],
                                 after_tax_cagr=r["after_tax_cagr"],
                                 tax_note="국내 KOSPI200·2배 차익 비과세 가정 · 현금 이자 15.4%"))
    # 전략 용도
    for sid in STRATS:
        pth = os.path.join(SCR, f"strat_{sid}.pkl")
        if not os.path.exists(pth):
            print(f"[v2 report] {sid} 없음 — 건너뜀", flush=True)
            continue
        sp = pickle.load(open(pth, "rb"))
        start = sp["start"]
        rows = {}
        for p in ("base",) + PLANS:
            rp = {"windows": {}}
            for wn in RG.WINS:
                rec = sp["res"][(p, wn)]
                sm = RG.seed_summary(rec["runs"], start, pd.DatetimeIndex(rec["dates"]))
                rp["windows"][wn] = {"cagr": sm["cagr_median"], "mdd": sm["mdd_median"], "mar": sm["mar_median"],
                                     "allow_ratio": rec["allow_ratio"], "n_kept_win": rec["n_kept_win"],
                                     "n_all_win": rec["n_all_win"]}
            rec = sp["res"][(p, "FULL")]
            er = [era_stats(_start_dates(rec), np.r_[start, e]) for _, e in rec["runs"]]
            rp["eras"] = {nm: {k: float(np.median([x[nm][k] for x in er if x[nm][k] is not None]))
                               for k in ("cagr", "mdd", "mar")} for nm, _ in ERAS if nm in er[0]}
            d, v, seed = rep_curve(rec, start)
            mt = SB.compute_metrics(d, v, rf, bench)
            rp["full_sb"] = mt
            rp["rep_seed"] = seed
            if p in PLANS:
                entries.append(entry(f"R2_{sid}_{p}", f"{RA_SID.get(sid, sid)} · 진입 문 {PLAN_NAMES[p]}",
                                     f"진입 세션 상태가 막음 칸이면 신규 진입 안 함(보유분은 원래 청산) · 허용 칸 = "
                                     f"{_allow_text(sp['amaps'][p])} · 비용 왕복 0.38%", "regime_v2_strategy", d, v,
                                     mt, source=f"tools/replay/regime_v2.py strat_stage {sid}"))
            rows[p] = rp
        cash_m = rf.groupby(rf.index.to_period("M")).last().pct_change()
        for p in ("na", "da", "ra", "base"):
            rows[p]["boot_vs_ga"] = {}
            for wn in ("T", "V", "H"):
                mg = seed_mean_monthly(SB, sp["res"][("ga", wn)], start)
                mp_ = seed_mean_monthly(SB, sp["res"][(p, wn)], start)
                cm = cash_m.reindex(mg.index).fillna(0.0)
                rows[p]["boot_vs_ga"][wn] = boot(mp_.to_numpy(), mg.to_numpy(), cm.to_numpy())
            if p != "base":
                rows[p]["judge"] = judge(rows[p]["boot_vs_ga"]["V"], rows[p]["boot_vs_ga"]["H"])
                # 사후(결과 문서 「사후 변경」 1): 검증 창에 진입이 하나도 없으면 MAR 이 정의되지 않는다
                # (``m_mar`` 은 낙폭 0 에 10.0 을 돌려준다) — 판정 대신 「매매 없음」 으로 적는다.
                if rows[p]["windows"]["V"]["n_kept_win"] == 0:
                    rows[p]["judge"] = "매매 없음(MAR 정의 안 됨)"
        out["strategies"][sid] = {"learn": sp["learn"], "amaps": sp["amaps"], "plans": rows}
        print(f"[v2 report] {sid} " + " · ".join(f"{p} {rows[p].get('judge')}" for p in ("na", "da", "ra")),
              flush=True)
    out["meta"] = {"prereg_sha256": open(os.path.join(out_dir, "prereg.sha256")).read().split()[0],
                   "label_counts_30y": ix["label_counts_30y"], "maps": ix["maps"],
                   "plans": _clean(ix["plans"]), "desc": ix["desc"],
                   "cand_rows": [{k: r[k] for k in ("name", "switch_T", "eligible", "T_mar", "T_cagr", "T_mdd",
                                                    "eta2_fwd20_T", "eta2_fwd60_T", "map")} for r in ix["cand_rows"]]}
    with open(os.path.join(out_dir, "result.json"), "w") as fh:
        json.dump(_clean(out), fh, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "scoreboard_entries.json"), "w") as fh:
        json.dump(_clean_e({"source": "regime_v2 2026-10-06 · tools/replay/regime_v2.py "
                                    "(_workspace/analysis/regime_v2_20261006/result.md)", "entries": entries}),
                  fh, ensure_ascii=False)
    with open(os.path.join(SCR, "report.pkl"), "wb") as fh:
        pickle.dump(out, fh)
    print(f"[v2 report] 끝 · 성적표 항목 {len(entries)}", flush=True)
    return out


RA_SID = {"kojiro": "kojiro", "donchian": "donchian_swing", "vcp": "vcp_breakout"}


def _allow_text(amap) -> str:
    if amap is None:
        return "전부"
    ok = [k for k, v in amap.items() if v]
    return "·".join(NAMES.get(k, k) for k in ok) or "없음"


def main():
    cmd = sys.argv[1]
    os.makedirs(SCR, exist_ok=True)
    if cmd == "breadth":
        build_breadth()
        return
    out_dir = sys.argv[2]
    if cmd == "index":
        index_stage(out_dir)
    elif cmd == "strat":
        nproc = int(os.environ.get("V2_NPROC", 6))
        for sid in (sys.argv[3:] or STRATS):
            strat_stage(sid, out_dir, nproc)
    elif cmd == "report":
        report(out_dir)
    else:
        raise SystemExit(cmd)


if __name__ == "__main__":
    main()
