"""6장세 판단 규칙 튜닝 연구 — 사전 등록 `_workspace/analysis/strategy_opt_20261005/regime/prereg.md`.

연구 전용. 운영 코드(`src/`)를 읽지도 쓰지도 않는다. 규칙 꼴은 `src/engine/market_regime_label.py`
(cycle410)의 히스테리시스와 같다 — 상태 = 종가 i 까지, 세션 i+1 의 라벨(하루 밀기).

순수 함수(라벨·정답·지표)와 실행부(`main`)로 나뉜다. 테스트는 순수 함수만 본다.
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import sys

import numpy as np
import pandas as pd

ETF_DIR = "/Users/koscom/Projects/auto_stock/data/archive/krx_etf_daily/parquet"
STK_DIR = "/Users/koscom/Projects/auto_stock/data/archive/krx_daily/parquet"

PERIODS = {
    "T": ("2020-10-05", "2023-09-29"),
    "V": ("2023-10-04", "2025-10-02"),
    "H": ("2025-10-10", "2026-10-02"),
}
T_SUB = [("2020-10-05", "2021-09-30"), ("2021-10-01", "2022-09-30"), ("2022-10-01", "2023-09-29")]

UP, FLAT, DOWN = "U", "S", "D"
NAMES = {"UL": "1 안정상승", "UH": "2 변동상승", "SL": "3 안정횡보",
         "SH": "4 변동횡보", "DL": "5 안정하락", "DH": "6 변동하락"}


# ---------------------------------------------------------------- 규칙 꼴

def hyst(x, enter, exit_):
    """방향 히스테리시스(= market_regime_label.step_direction 꼴). NaN 동안은 출력 None, 상태 유지."""
    st = FLAT
    out = []
    for v in x:
        if v is None or not np.isfinite(v):
            out.append(None)
            continue
        if st == UP:
            if v < exit_:
                st = DOWN if v < -enter else FLAT
        elif st == DOWN:
            if v > -exit_:
                st = UP if v > enter else FLAT
        else:
            if v > enter:
                st = UP
            elif v < -enter:
                st = DOWN
        out.append(st)
    return out


def hyst_vol(x, hi, lo):
    """변동 히스테리시스 — 시작 = 안정, 사이는 직전 유지."""
    st = "L"
    out = []
    for v in x:
        if v is None or not np.isfinite(v):
            out.append(None)
            continue
        if st == "L" and v > hi:
            st = "H"
        elif st == "H" and v < lo:
            st = "L"
        out.append(st)
    return out


def confirm(raw, n):
    """원상태가 n일 연속 같아야 라벨이 바뀐다. 시작 라벨 = 횡보."""
    lab = FLAT
    run_v, run_n = None, 0
    out = []
    for v in raw:
        if v is None:
            out.append(None)
            continue
        if v == run_v:
            run_n += 1
        else:
            run_v, run_n = v, 1
        if v != lab and run_n >= n:
            lab = v
        out.append(lab)
    return out


def sma(c, n):
    return c.rolling(n, min_periods=n).mean()


def dir_A(c, L, k, e, ex):
    m = sma(c, L)
    return hyst((m / m.shift(k) - 1).values, e, ex)


def dir_B(c, L, n):
    m = sma(c, L)
    m10 = m.shift(10)
    raw = []
    for ci, mi, mp in zip(c.values, m.values, m10.values):
        if not (np.isfinite(mi) and np.isfinite(mp)):
            raw.append(None)
        elif ci > mi and mi > mp:
            raw.append(UP)
        elif ci < mi and mi < mp:
            raw.append(DOWN)
        else:
            raw.append(FLAT)
    return confirm(raw, n)


def dir_C(c, s, l, b):
    return hyst((sma(c, s) / sma(c, l) - 1).values, b, b / 3)


def dir_D(c, base, theta):
    """낙폭/반등 덧씌움. base = 같은 길이의 기본 라벨 목록."""
    mx = c.rolling(60, min_periods=60).max()
    mn = c.rolling(60, min_periods=60).min()
    dd = (c / mx - 1).values
    ru = (c / mn - 1).values
    out = []
    for b, d, r in zip(base, dd, ru):
        if b is None or not np.isfinite(d):
            out.append(None if b is None else b)
            continue
        if d <= -theta:
            out.append(DOWN)
        elif r >= theta and d > -theta / 2:
            out.append(UP)
        else:
            out.append(b)
    return out


def dir_E(breadth, h, m):
    b = breadth.rolling(m, min_periods=m).mean() if m > 1 else breadth
    return hyst((b - 0.5).values, h - 0.5, h - 0.6)


def realized_vol(c, w):
    lr = np.log(c).diff()
    return lr.rolling(w, min_periods=w).std() * np.sqrt(252)


# ---------------------------------------------------------------- 정답·지표

def truth_dir(c, half=20, thr=0.05):
    r = c.shift(-half) / c.shift(half) - 1
    out = pd.Series(np.where(r > thr, UP, np.where(r < -thr, DOWN, FLAT)), index=c.index)
    return out.where(r.notna())


def truth_vol(c, half=10, thr=0.18):
    lr = np.log(c).diff()
    # 수익률 k = D-9 .. D+10 (종가 D-10 .. D+10) 20개
    v = lr.rolling(2 * half, min_periods=2 * half).std().shift(-half) * np.sqrt(252)
    return pd.Series(np.where(v > thr, "H", "L"), index=c.index).where(v.notna())


def zigzag(c, theta=0.10):
    """사후 지그재그 전환점 [(날짜, 'P'|'T')] — 되돌림 theta 로 확정된 극점."""
    v = c.values
    idx = c.index
    pts = []
    trend = 0
    hi_i = lo_i = 0
    for i in range(1, len(v)):
        if trend == 0:
            if v[i] > v[hi_i]:
                hi_i = i
            if v[i] < v[lo_i]:
                lo_i = i
            if v[i] <= v[hi_i] * (1 - theta):
                pts.append((idx[hi_i], "P")); trend = -1; lo_i = i
            elif v[i] >= v[lo_i] * (1 + theta):
                pts.append((idx[lo_i], "T")); trend = 1; hi_i = i
        elif trend == 1:
            if v[i] > v[hi_i]:
                hi_i = i
            elif v[i] <= v[hi_i] * (1 - theta):
                pts.append((idx[hi_i], "P")); trend = -1; lo_i = i
        else:
            if v[i] < v[lo_i]:
                lo_i = i
            elif v[i] >= v[lo_i] * (1 + theta):
                pts.append((idx[lo_i], "T")); trend = 1; hi_i = i
    return pts


def turn_lags(dir_lab, turns, d0, d1):
    """구간 [d0,d1] 안 전환점마다 (날짜, 종류, 이탈 지연, 진입 지연, 놓침?)."""
    idx = dir_lab.index
    res = []
    for j, (t, kind) in enumerate(turns):
        if not (pd.Timestamp(d0) <= t <= pd.Timestamp(d1)):
            continue
        nxt = turns[j + 1][0] if j + 1 < len(turns) else idx[-1]
        p = idx.get_loc(t)
        q = idx.get_loc(nxt) if nxt in idx else len(idx) - 1
        old, new = (UP, DOWN) if kind == "P" else (DOWN, UP)
        seg = dir_lab.iloc[p:q] if q > p else dir_lab.iloc[p:p + 1]
        lv = next((i for i, v in enumerate(seg.values) if v != old), None)
        en = next((i for i, v in enumerate(seg.values) if v == new), None)
        res.append(dict(date=str(t.date()), kind=kind, seg=len(seg),
                        leave=lv if lv is not None else len(seg), enter=en if en is not None else len(seg),
                        leave_miss=lv is None, enter_miss=en is None))
    return res


def balanced_acc(pred, truth):
    ok = truth.notna() & pred.notna()
    p, t = pred[ok], truth[ok]
    recs = [float((p[t == k] == k).mean()) for k in sorted(t.unique())]
    return float(np.mean(recs)) if recs else float("nan")


def spells(lab):
    """[(시작 날짜, 라벨, 길이)] — 전체 시리즈 기준."""
    out = []
    cur, start, n = None, None, 0
    for d, v in lab.items():
        if v != cur:
            if cur is not None:
                out.append((start, cur, n))
            cur, start, n = v, d, 0
        n += 1
    if cur is not None:
        out.append((start, cur, n))
    return out


def metrics(lab6, c, tdir, tvol, d0, d1, sp=None):
    """lab6 = 'U'|'S'|'D' + 'L'|'H' 문자열 Series (세션 날짜 색인)."""
    sl = lab6.loc[d0:d1].dropna()
    days = sl.index
    dr = sl.str[0]
    vl = sl.str[1]
    bad = float(balanced_acc(dr, tdir.reindex(days)))
    bav = float(balanced_acc(vl, tvol.reindex(days)))
    t6 = (tdir.reindex(days) + tvol.reindex(days))
    ok = t6.notna()
    acc6 = float((sl[ok] == t6[ok]).mean())
    fwd = (c.shift(-19) / c.shift(1) - 1).reindex(days)
    lr = np.log(c).diff()
    fvol = (lr.rolling(20).std().shift(-19) * np.sqrt(252)).reindex(days)
    up_f = fwd[dr == UP].mean()
    dn_f = fwd[dr == DOWN].mean()
    sw = int((sl != sl.shift()).sum() - 1)
    sp = sp if sp is not None else spells(lab6.dropna())
    sp_in = [s for s in sp if pd.Timestamp(d0) <= s[0] <= pd.Timestamp(d1)]
    short = sum(1 for s in sp_in if s[2] <= 5)
    return dict(
        n=len(sl), BA_dir=bad, BA_vol=bav, S=(bad + bav) / 2, acc6=acc6,
        fwd_up=float(up_f) if np.isfinite(up_f) else float("nan"),
        fwd_flat=float(fwd[dr == FLAT].mean()),
        fwd_dn=float(dn_f) if np.isfinite(dn_f) else float("nan"),
        fwd_spread=float(up_f - dn_f) if np.isfinite(up_f) and np.isfinite(dn_f) else float("nan"),
        fwd_vol_ratio=float(fvol[vl == "H"].mean() / fvol[vl == "L"].mean()),
        sw_yr=sw / (len(sl) / 252), short_share=short / max(len(sp_in), 1), n_spells=len(sp_in),
        n_up=int((dr == UP).sum()), n_flat=int((dr == FLAT).sum()), n_dn=int((dr == DOWN).sum()),
        n_H=int((vl == "H").sum()), n_L=int((vl == "L").sum()),
    )


def score_on(days, dr, vl, tdir, tvol):
    return (balanced_acc(dr.loc[days], tdir.loc[days]) + balanced_acc(vl.loc[days], tvol.loc[days])) / 2


def block_boot(days, labA, labB, tdir, tvol, block=40, reps=2000, seed=7):
    """순환 블록 부트스트랩 — S(B) − S(A) 분포."""
    rng = np.random.default_rng(seed)
    n = len(days)
    dA, vA = labA.str[0].reindex(days).values, labA.str[1].reindex(days).values
    dB, vB = labB.str[0].reindex(days).values, labB.str[1].reindex(days).values
    td, tv = tdir.reindex(days).values, tvol.reindex(days).values

    def ba(p, t):
        m = pd.notna(t) & pd.notna(p)
        p, t = p[m], t[m]
        return np.mean([np.mean(p[t == k] == k) for k in np.unique(t)])

    nb = int(np.ceil(n / block))
    out = []
    for _ in range(reps):
        st = rng.integers(0, n, nb)
        ix = np.concatenate([(s + np.arange(block)) % n for s in st])[:n]
        sA = (ba(dA[ix], td[ix]) + ba(vA[ix], tv[ix])) / 2
        sB = (ba(dB[ix], td[ix]) + ba(vB[ix], tv[ix])) / 2
        out.append(sB - sA)
    return np.array(out)


# ---------------------------------------------------------------- 데이터

def _etf_close(ticker):
    fs = sorted(glob.glob(os.path.join(ETF_DIR, "*.parquet")))
    parts = [pd.read_parquet(f, columns=["ticker", "bas_dd", "close_adj"]) for f in fs]
    d = pd.concat(parts)
    s = d[d.ticker == ticker].set_index("bas_dd").close_adj.astype(float).sort_index()
    s.index = pd.to_datetime(s.index)
    return s


def load(db_daily_parquet, db_master_parquet):
    db = pd.read_parquet(db_daily_parquet)
    db["bas_dd"] = pd.to_datetime(db.bas_dd)
    closes = {}
    seam = {}
    for t in ("069500", "229200"):
        a = _etf_close(t)
        b = db[db.ticker == t].set_index("bas_dd").close_price.astype(float).sort_index()
        b = b[b.index > a.index.max()]
        closes[t] = pd.concat([a, b])
        seam[t] = (str(a.index.max().date()), float(a.iloc[-1]), str(b.index.min().date()), float(b.iloc[0]))
    # 시장 폭
    fs = sorted(glob.glob(os.path.join(STK_DIR, "*.parquet")))
    stk = pd.concat([pd.read_parquet(f, columns=["ticker", "bas_dd", "close_adj"]) for f in fs])
    stk["bas_dd"] = pd.to_datetime(stk.bas_dd)
    pa = stk.pivot_table(index="bas_dd", columns="ticker", values="close_adj", aggfunc="last")
    mst = pd.read_parquet(db_master_parquet)
    st_t = set(mst[mst.scty_grp_id_cd == "ST"].ticker)
    dbs = db[db.ticker.isin(st_t) & (db.bas_dd > pa.index.max())]
    pb = dbs.pivot_table(index="bas_dd", columns="ticker", values="close_price", aggfunc="last").astype(float)
    px = pd.concat([pa, pb]).sort_index()
    px = px.where(px > 0)
    m60 = px.rolling(60, min_periods=60).mean()
    valid = m60.notna() & px.notna()
    breadth = ((px > m60) & valid).sum(axis=1) / valid.sum(axis=1)
    nvalid = valid.sum(axis=1)
    idx = closes["069500"].index
    breadth = breadth.reindex(idx)
    return closes, breadth, nvalid.reindex(idx), seam


# ---------------------------------------------------------------- 후보

def dir_candidates(c, c2, breadth):
    """{이름: (군, 상태 목록(종가 색인))} — 47개."""
    out = {}
    for L, k in [(20, 10), (40, 10), (40, 20), (60, 10), (60, 20)]:
        for e, ex in [(0.02, 0.005), (0.03, 0.01), (0.04, 0.015)]:
            out[f"A_L{L}_k{k}_e{e}_x{ex}"] = dir_A(c, L, k, e, ex)
    for L in (20, 40, 60, 120):
        for n in (3, 5):
            out[f"B_L{L}_n{n}"] = dir_B(c, L, n)
    for s, l in [(5, 20), (10, 40), (20, 60), (20, 120)]:
        for b in (0.01, 0.02):
            out[f"C_s{s}_l{l}_b{b}"] = dir_C(c, s, l, b)
    bases = {"cur": out["A_L60_k20_e0.03_x0.01"], "A40": out["A_L40_k10_e0.03_x0.01"]}
    for bn, base in bases.items():
        for th in (0.08, 0.10, 0.12, 0.15):
            out[f"D_{bn}_th{th}"] = dir_D(c, base, th)
    for h in (0.60, 0.65, 0.70):
        for m in (1, 10):
            out[f"E_h{h}_m{m}"] = dir_E(breadth, h, m)
    comp = np.exp((np.log(c / c.iloc[0]) + np.log(c2 / c2.iloc[0])) / 2)
    out["F_L60_k20"] = dir_A(comp, 60, 20, 0.03, 0.01)
    out["F_L40_k10"] = dir_A(comp, 40, 10, 0.03, 0.01)
    return out


def vol_candidates(c):
    out = {}
    for w in (10, 20, 40):
        for hi, lo in [(0.20, 0.16), (0.24, 0.18)]:
            out[f"V_w{w}_h{hi}_l{lo}"] = hyst_vol(realized_vol(c, w).values, hi, lo)
    return out


CURRENT = ("A_L60_k20_e0.03_x0.01", "V_w20_h0.2_l0.16")


def session_label(c, dstates, vstates):
    """종가 i 의 상태 → 세션 i+1 라벨."""
    s = pd.Series([(a + b) if (a is not None and b is not None) else None
                   for a, b in zip(dstates, vstates)], index=c.index, dtype=object)
    return s.shift(1)


def market_unit(c):
    m = sma(c, 60)
    above = c > m
    rising = m > m.shift(20)
    mu = pd.Series(np.where(above & rising, "up_rising", np.where(above, "up_falling",
                   np.where(rising, "down_rising", "down_falling"))), index=c.index).where(m.shift(20).notna())
    return mu.shift(1)


# ---------------------------------------------------------------- 실행

def main(out_dir, db_daily, db_master):
    closes, breadth, nvalid, seam = load(db_daily, db_master)
    c = closes["069500"]
    c2 = closes["229200"].reindex(c.index).ffill()
    D = dir_candidates(c, c2, breadth)
    V = vol_candidates(c)
    labs = {(dn, vn): session_label(c, ds, vs) for dn, ds in D.items() for vn, vs in V.items()}
    assert len(labs) == 282, len(labs)
    common = None
    for s in labs.values():
        ok = s.notna()
        common = ok if common is None else (common & ok)
    first = common[common].index.min()
    tdir, tvol = truth_dir(c), truth_vol(c)
    has_truth = tdir.notna() & tvol.notna()
    turns = zigzag(c, 0.10)

    def per(lab, p):
        d0, d1 = PERIODS[p]
        d0 = max(pd.Timestamp(d0), first)
        lab_c = lab.loc[first:]
        days = lab_c.loc[d0:d1].index
        days = days[has_truth.reindex(days).values]
        return lab_c, days, d0, d1

    rows = []
    sp_cache = {}
    for key, lab in labs.items():
        lab_c = lab.loc[first:]
        sp = spells(lab_c)
        sp_cache[key] = sp
        d0 = first
        d1 = PERIODS["T"][1]
        tdays = lab_c.loc[d0:d1].index
        tdays = tdays[has_truth.reindex(tdays).values]
        m = metrics(lab_c.loc[tdays], c, tdir, tvol, d0, d1, sp=sp)
        # sw/short 은 정답 유무와 무관하게 기간 전체 라벨로
        mm = metrics(lab_c, c, tdir, tvol, d0, d1, sp=sp)
        m["sw_yr"], m["short_share"], m["n_spells"] = mm["sw_yr"], mm["short_share"], mm["n_spells"]
        m["fwd_spread"] = mm["fwd_spread"]
        lg = turn_lags(lab_c.str[0], turns, d0, d1)
        m["lag_enter_med"] = float(np.median([x["enter"] for x in lg])) if lg else float("nan")
        m["lag_leave_med"] = float(np.median([x["leave"] for x in lg])) if lg else float("nan")
        m["enter_miss"] = sum(x["enter_miss"] for x in lg)
        m["dir"], m["vol"] = key
        rows.append(m)
    G = pd.DataFrame(rows)
    G["pass"] = ((G.sw_yr <= 8) & (G.short_share <= 0.10) & (G.fwd_spread > 0)
                 & (G.n_up >= 20) & (G.n_flat >= 20) & (G.n_dn >= 20) & (G.n_H >= 20) & (G.n_L >= 20))
    G["S4"] = G.S.round(4)
    G = G.sort_values(["pass", "S4", "lag_enter_med", "sw_yr"], ascending=[False, False, True, True])
    G.to_csv(os.path.join(out_dir, "grid_train.csv"), index=False)
    pick = tuple(G[G["pass"]].iloc[0][["dir", "vol"]])
    cur = CURRENT

    report = dict(first_label_day=str(first.date()), seam=seam, n_turns=len(turns),
                  turns=[(str(t.date()), k) for t, k in turns], pick=pick, current=cur)
    # 기간별
    per_rows = {}
    for name, key in (("current", cur), ("pick", pick)):
        lab = labs[key]
        for p in ("T", "V", "H"):
            lab_c, days, d0, d1 = per(lab, p)
            m = metrics(lab_c.loc[days], c, tdir, tvol, d0, d1, sp=sp_cache[key])
            mm = metrics(lab_c, c, tdir, tvol, d0, d1, sp=sp_cache[key])
            for f in ("sw_yr", "short_share", "n_spells", "fwd_spread", "fwd_up", "fwd_flat", "fwd_dn", "fwd_vol_ratio"):
                m[f] = mm[f]
            lg = turn_lags(lab_c.str[0], turns, d0, d1)
            m["lags"] = lg
            m["lag_enter_med"] = float(np.median([x["enter"] for x in lg])) if lg else None
            m["lag_leave_med"] = float(np.median([x["leave"] for x in lg])) if lg else None
            per_rows[f"{name}_{p}"] = m
        for i, (a, b) in enumerate(T_SUB):
            lab_c = lab.loc[first:]
            days = lab_c.loc[max(pd.Timestamp(a), first):b].index
            days = days[has_truth.reindex(days).values]
            per_rows[f"{name}_Tsub{i}"] = dict(S=score_on(days, lab_c.str[0], lab_c.str[1], tdir, tvol))
    report["per"] = per_rows
    # 부트스트랩 V, H
    for p in ("V", "H"):
        lab_c, days, _, _ = per(labs[pick], p)
        bs = block_boot(days, labs[cur], labs[pick], tdir, tvol)
        report[f"boot_{p}"] = dict(mean=float(bs.mean()), sd=float(bs.std()), lo90=float(np.quantile(bs, 0.10)),
                                    bonf=float(bs.mean() - 3.39 * bs.std()), n_days=len(days))
    # 상위 10 V 값(진단)
    top = G[G["pass"]].head(10)
    diag = []
    for _, r in top.iterrows():
        key = (r["dir"], r["vol"])
        lab_c, days, _, _ = per(labs[key], "V")
        diag.append(dict(dir=key[0], vol=key[1], S_T=r["S"], S_V=score_on(days, lab_c.str[0], lab_c.str[1], tdir, tvol)))
    report["top10_diag"] = diag
    # 군별 최고(학습) — 진단
    G["fam"] = G["dir"].str[0]
    report["best_by_family"] = G[G["pass"]].groupby("fam").head(1)[["dir", "vol", "S", "BA_dir", "BA_vol", "sw_yr", "lag_enter_med"]].to_dict("records")
    report["n_pass"] = int(G["pass"].sum())
    # H 일별
    mu = market_unit(c)
    H0, H1 = PERIODS["H"]
    hc = pd.DataFrame(dict(close=c, cur=labs[cur], new=labs[pick], truth_dir=tdir, truth_vol=tvol, mu=mu,
                           breadth=breadth.shift(1))).loc[H0:H1]
    hc["cur_name"] = hc.cur.map(NAMES)
    hc["new_name"] = hc.new.map(NAMES)
    hc.to_csv(os.path.join(out_dir, "labels_h.csv"))
    # 전 기간 시장 유닛 교차
    allc = pd.DataFrame(dict(new=labs[pick].map(NAMES), cur=labs[cur].map(NAMES), mu=mu)).loc[first:].dropna()
    report["xt_new_mu"] = pd.crosstab(allc.new, allc.mu).to_dict()
    report["xt_cur_mu"] = pd.crosstab(allc.cur, allc.mu).to_dict()
    report["xt_new_cur"] = pd.crosstab(allc.cur, allc.new).to_dict()
    report["spells_cur"] = [(str(a.date()), NAMES[b], n) for a, b, n in sp_cache[cur]]
    report["spells_new"] = [(str(a.date()), NAMES[b], n) for a, b, n in sp_cache[pick]]
    report["breadth_nvalid_H"] = dict(min=int(nvalid.loc[H0:H1].min()), max=int(nvalid.loc[H0:H1].max()),
                                      pre=int(nvalid.loc[:"2025-10-02"].iloc[-1]))
    with open(os.path.join(out_dir, "result.json"), "w") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1, default=str)
    return report, G, labs, c, tdir, tvol, turns, first


if __name__ == "__main__":
    out = sys.argv[1]
    main(out, sys.argv[2], sys.argv[3])
