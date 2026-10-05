#!/usr/bin/env python3
"""여러 나라 자산배분 — 후보 비중 규칙 · 모의 집행 · 걷기 전진 · 판정 (사전 등록 ``global_alloc_20261006/prereg.frozen.md``).

입력 = ``tools/replay/global_alloc_data.py`` 가 만든 ``global_daily_krw.parquet``.

    python tools/replay/global_alloc.py <global_daily_krw.parquet> <out_dir>
"""
from __future__ import annotations

import itertools
import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.engine import market_regime_label as MRL  # noqa: E402  (읽기 전용 — 방향·변동 한 걸음 규칙)

RISKY = ("K200", "SPX", "NDX", "NKY", "HSCEI", "UST10", "USD")
COLS = RISKY + ("CASH",)
NA = len(COLS)
I_CASH = NA - 1
I_UST = RISKY.index("UST10")
EQUITY = ("K200", "SPX", "NDX", "NKY", "HSCEI")
I_EQ = tuple(RISKY.index(a) for a in EQUITY)
FEE = {"K200": 0.0015, "SPX": 0.0007, "NDX": 0.0010, "NKY": 0.0040, "HSCEI": 0.0040, "UST10": 0.0015,
       "USD": 0.0025, "CASH": 0.0005}
COST_ONE_WAY = 0.0019                          # 왕복 0.38% 의 한쪽
TAX = 0.154
TAXABLE_GAIN = {"SPX", "NDX", "NKY", "HSCEI", "UST10", "USD"}
DIV_FOR_TAX = {"K200": 0.016, "SPX": 0.019, "NDX": 0.008, "NKY": 0.013, "HSCEI": 0.030}
OOS_START = 2006
HEDGEABLE = ("SPX", "NDX", "NKY", "HSCEI", "UST10")


# ───────────────────────────── 데이터 ─────────────────────────────

@dataclass
class Market:
    dates: pd.DatetimeIndex
    ret: np.ndarray            # T×8 일별 원화 수익(보수 차감 전)
    fee: np.ndarray            # T×8 일별 보수
    idx: np.ndarray            # T×8 누적 총수익 지수(신호용)
    local_px: np.ndarray       # T×7 장세 라벨용 현지 가격(UST10 = 현지 총수익 · USD = 환율)
    dt_y: np.ndarray
    cache: dict = field(default_factory=dict)


def load_market(df: pd.DataFrame, hedged: bool = False, k200_div_shift: float = 0.0) -> Market:
    dates = pd.DatetimeIndex(df.index)
    days = pd.Series(dates, index=dates).diff().dt.days.fillna(1).to_numpy(float)
    dt_y = days / 365.0
    ret = np.zeros((len(dates), NA))
    for j, a in enumerate(RISKY):
        col = f"{a}_hret" if (hedged and a in HEDGEABLE) else f"{a}_ret"
        ret[:, j] = df[col].to_numpy(float)
    ret[:, 0] += k200_div_shift * dt_y
    ret[:, I_CASH] = df["CASH_ret"].to_numpy(float)
    ret[0, :] = 0.0
    fee = np.outer(dt_y, np.array([FEE[c] for c in COLS]))
    idx = np.cumprod(1 + ret, axis=0)
    lp = np.zeros((len(dates), len(RISKY)))
    for j, a in enumerate(RISKY):
        if a in EQUITY:
            lp[:, j] = df[f"{a}_px_local"].to_numpy(float)
        elif a == "UST10":
            lp[:, j] = np.cumprod(1 + df["UST10_lret"].to_numpy(float))
        else:
            lp[:, j] = df["fx_usdkrw"].to_numpy(float)
    return Market(dates, ret, fee, idx, lp, dt_y)


def decision_points(dates: pd.DatetimeIndex, freq: str) -> np.ndarray:
    """결정일 위치 = 주기(월 M · 주 W · 분기 Q)의 마지막 거래일. 마지막 행은 집행일이 없어 뺀다."""
    s = pd.Series(np.arange(len(dates)), index=dates)
    if freq == "M":
        key = dates.to_period("M")
    elif freq == "Q":
        key = dates.to_period("Q")
    elif freq == "W":
        key = dates.to_period("W-FRI")
    else:
        raise ValueError(freq)
    last = s.groupby(key).max().to_numpy()
    return last[last < len(dates) - 1]


# ───────────────────────────── 신호 ─────────────────────────────

def _mom(m: Market, months: int) -> np.ndarray:
    k = ("mom", months)
    if k not in m.cache:
        n = 21 * months
        out = np.full_like(m.idx, np.nan)
        out[n:] = m.idx[n:] / m.idx[:-n] - 1
        m.cache[k] = out
    return m.cache[k]


def _sma_ratio(m: Market, months: int) -> np.ndarray:
    k = ("sma", months)
    if k not in m.cache:
        n = 21 * months
        df = pd.DataFrame(m.idx)
        m.cache[k] = (df / df.rolling(n, min_periods=n).mean()).to_numpy()
    return m.cache[k]


def _vol(m: Market, w: int) -> np.ndarray:
    k = ("vol", w)
    if k not in m.cache:
        m.cache[k] = pd.DataFrame(m.ret).rolling(w, min_periods=w).std().to_numpy() * np.sqrt(252)
    return m.cache[k]


def score(m: Market, kind: str, i: int) -> np.ndarray:
    """위험 자산 7개 점수와 현금 같은 창 수익(초과수익 판정용)을 함께 돌려준다: (점수, 초과수익)."""
    if kind == "B":
        ms = [_mom(m, L)[i] for L in (1, 3, 6, 12)]
        sc = np.mean([x[:7] for x in ms], axis=0)
        ex = np.mean([x[:7] - x[I_CASH] for x in ms], axis=0)
        return sc, ex
    L = int(kind[1:])
    x = _mom(m, L)[i]
    return x[:7], x[:7] - x[I_CASH]


def market_unit(m: Market, i: int) -> np.ndarray:
    """주식 5개 시장 유닛형 배수 — 60일선 위·상승 1 · 위·하락 0.75 · 아래·상승 0.5 · 아래·하락 0(동률 = 약한 쪽)."""
    k = "mu"
    if k not in m.cache:
        df = pd.DataFrame(m.idx[:, :7])
        sma = df.rolling(60, min_periods=60).mean()
        above = (df > sma).to_numpy()
        up = (sma > sma.shift(20)).to_numpy()
        mu = np.where(above & up, 1.0, np.where(above, 0.75, np.where(up, 0.5, 0.0)))
        mu[np.isnan(sma.shift(20).to_numpy())] = np.nan
        m.cache[k] = mu
    return m.cache[k][i]


def regime_states(m: Market) -> tuple[np.ndarray, np.ndarray]:
    """자산별 (하락?, 변동?) 상태 — 종가 i 까지 걸어 온 상태. 준비 전 = NaN."""
    if "regime" in m.cache:
        return m.cache["regime"]
    T = len(m.dates)
    down = np.full((T, 7), np.nan)
    volat = np.full((T, 7), np.nan)
    for j in range(7):
        c = pd.Series(m.local_px[:, j])
        sma = c.rolling(MRL.MA_WINDOW).mean()
        slope = (sma / sma.shift(MRL.SLOPE_LOOKBACK) - 1).to_numpy()
        lr = np.log(c / c.shift(1))
        vol = (lr.rolling(MRL.VOL_WINDOW).std() * np.sqrt(MRL.ANNUALIZATION))
        med = vol.expanding(min_periods=252).median().to_numpy()
        vol = vol.to_numpy()
        d, v = "flat", "stable"
        for t in range(T):
            if np.isnan(slope[t]) or np.isnan(vol[t]) or np.isnan(med[t]) or med[t] <= 0:
                continue
            d = MRL.step_direction(d, float(slope[t]))
            v = MRL.step_volatility(v, float(vol[t] * 0.18 / med[t]))
            down[t, j] = 1.0 if d == "down" else 0.0
            volat[t, j] = 1.0 if v == "volatile" else 0.0
    m.cache["regime"] = (down, volat)
    return down, volat


# ───────────────────────────── 후보 규칙 ─────────────────────────────

def _to_fallback(w: np.ndarray, freed: float, fallback: str, ust_on: bool) -> np.ndarray:
    if freed <= 0:
        return w
    if fallback == "ust" and ust_on:
        w[I_UST] += freed
    else:
        w[I_CASH] += freed
    return w


def _cash_only() -> np.ndarray:
    w = np.zeros(NA)
    w[I_CASH] = 1.0
    return w


def weights(m: Market, fam: str, p: tuple, i: int) -> np.ndarray:
    w = np.zeros(NA)
    if fam == "B0":
        w[0] = 1.0
        return w
    if fam == "B1":
        w[0], w[I_UST] = 0.6, 0.4
        return w
    if fam == "B2":
        w[:7] = 1 / 7
        return w
    if fam == "B3":
        for j in I_EQ:
            w[j] = 0.12
        w[I_UST] = 0.4
        return w
    if fam == "F1":
        L, sig, fb = p
        if sig == "ret":
            x = _mom(m, L)[i]
            if np.isnan(x).any():
                return _cash_only()
            on = x[:7] > x[I_CASH]
        else:
            x = _sma_ratio(m, L)[i]
            if np.isnan(x).any():
                return _cash_only()
            on = x[:7] > 1.0
        freed = 0.0
        for j in range(7):
            if on[j]:
                w[j] = 1 / 7
            else:
                freed += 1 / 7
        return _to_fallback(w, freed, fb, bool(on[I_UST]))
    if fam in ("F2", "F3"):
        kind, N = p[0], p[1]
        sc, ex = score(m, kind, i)
        if np.isnan(sc).any() or np.isnan(ex).any():
            return _cash_only()
        top = np.argsort(-sc, kind="stable")[:N]
        if fam == "F2":
            w[top] = 1 / N
            return w
        fb = p[2]
        freed = 0.0
        for j in top:
            if ex[j] > 0:
                w[j] += 1 / N
            else:
                freed += 1 / N
        return _to_fallback(w, freed, fb, bool(ex[I_UST] > 0))
    if fam == "F4":
        W, tgt = p
        v = _vol(m, W)[i, :7]
        if i < W or np.isnan(v).any() or (v <= 0).any():
            return _cash_only()
        raw = (1 / v) / (1 / v).sum()
        if tgt is not None:
            cov = np.cov(m.ret[i - W + 1:i + 1, :7].T) * 252
            pv = float(np.sqrt(raw @ cov @ raw))
            raw = raw * min(1.0, tgt / pv) if pv > 0 else raw
        w[:7] = raw
        w[I_CASH] = 1 - raw.sum()
        return w
    if fam == "F5":
        kind, N, mu_on = p
        sc, ex = score(m, kind, i)
        v = _vol(m, 63)[i, :7]
        mu = market_unit(m, i)
        if np.isnan(sc).any() or np.isnan(ex).any() or np.isnan(v).any() or np.isnan(mu).any():
            return _cash_only()
        top = [j for j in np.argsort(-sc, kind="stable")[:N] if ex[j] > 0]
        if top:
            iv = np.array([1 / v[j] for j in top])
            iv = iv / iv.sum()
            for j, x in zip(top, iv):
                w[j] = x * (mu[j] if (mu_on and j in I_EQ) else 1.0)
        w[I_CASH] = 1 - w[:7].sum()
        return w
    if fam == "F6":
        mv, md, fb = p
        down, volat = regime_states(m)
        if np.isnan(down[i]).any() or np.isnan(volat[i]).any():
            return _cash_only()
        mult = np.where(volat[i] > 0, mv, 1.0) * np.where(down[i] > 0, md, 1.0)
        w[:7] = mult / 7
        freed = (1 - mult).sum() / 7
        ust_on = bool(mult[I_UST] >= 1.0)
        return _to_fallback(w, freed, fb, ust_on)
    raise ValueError(fam)


GRID = {
    "F1": list(itertools.product((3, 6, 9, 12), ("ret", "sma"), ("cash", "ust"))),
    "F2": list(itertools.product(("R3", "R6", "R12", "B"), (1, 2, 3))),
    "F3": list(itertools.product(("R3", "R6", "R12", "B"), (1, 2, 3), ("cash", "ust"))),
    "F4": list(itertools.product((63, 126), (None, 0.06, 0.08, 0.10, 0.12))),
    "F5": list(itertools.product(("R6", "R12", "B"), (2, 3), (True, False))),
    "F6": list(itertools.product((1.0, 0.5, 0.0), (1.0, 0.5, 0.0), ("cash", "ust"))),
}
FAMILIES = ("F1", "F2", "F3", "F4", "F5", "F6")


# ───────────────────────────── 모의 집행 ─────────────────────────────

@dataclass
class SimResult:
    value: np.ndarray          # 일별 가치(시작 = 1)
    turnover: np.ndarray       # 일별 한쪽 회전량(집행일에만 값)
    cost: np.ndarray           # 일별 비용(가치 대비)
    tax_paid: float = 0.0


def simulate(m: Market, sched: dict[int, np.ndarray], start: int, end: int | None = None,
             tax: bool = False, cost_one_way: float = COST_ONE_WAY) -> SimResult:
    """start 종가에 현금 1 로 시작. 결정 i 의 비중을 i+1 종가에 집행. 세금 모드 = 평균단가 · 차익 15.4%."""
    T = len(m.dates) if end is None else end + 1
    r = m.ret - m.fee
    w = _cash_only()
    V = 1.0
    val = np.full(T, np.nan)
    to = np.zeros(T)
    co = np.zeros(T)
    val[start] = V
    exec_at = {i + 1: wt for i, wt in sched.items() if start <= i and i + 1 < T}
    hold = w * V
    basis = hold.copy()
    tax_paid = 0.0
    taxable = np.array([c in TAXABLE_GAIN for c in COLS])
    divtax = np.array([DIV_FOR_TAX.get(c, 0.0) * TAX for c in COLS])
    for t in range(start + 1, T):
        hold = hold * (1 + r[t])
        if tax:
            d = hold * divtax * m.dt_y[t]
            d[I_CASH] = hold[I_CASH] * TAX * max(r[t, I_CASH], 0.0)
            hold = hold - d
            tax_paid += d.sum()
        V = hold.sum()
        if t in exec_at:
            tgt = exec_at[t]
            cur = hold / V
            turn = float(np.abs(tgt[:I_CASH] - cur[:I_CASH]).sum())
            c = turn * cost_one_way * V
            V2 = V - c
            new = tgt * V2
            if tax:
                tx = 0.0
                for j in range(NA):
                    if new[j] < hold[j] and hold[j] > 0:
                        frac = (hold[j] - new[j]) / hold[j]
                        gain = (hold[j] - basis[j]) * frac
                        if taxable[j] and gain > 0:
                            tx += TAX * gain
                        basis[j] *= (1 - frac)
                    elif new[j] > hold[j]:
                        basis[j] += new[j] - hold[j]
                new[I_CASH] -= tx
                tax_paid += tx
            hold = new
            to[t] = turn
            co[t] = c / V
            V = hold.sum()
        val[t] = V
    if tax:
        gain = np.where(taxable, np.maximum(hold - basis, 0.0), 0.0).sum()
        val[T - 1] -= TAX * gain
        tax_paid += TAX * gain
    return SimResult(val, to, co, tax_paid)


def schedule(m: Market, fam: str, p: tuple, dps: np.ndarray) -> dict[int, np.ndarray]:
    return {int(i): weights(m, fam, p, int(i)) for i in dps}


# ───────────────────────────── 지표 ─────────────────────────────

def daily_metrics(m: Market, val: np.ndarray, a: int, b: int) -> dict:
    v = val[a:b + 1]
    rr = v[1:] / v[:-1] - 1
    cash = m.ret[a + 1:b + 1, I_CASH]
    ex = rr - cash
    yrs = (m.dates[b] - m.dates[a]).days / 365.25
    cagr = (v[-1] / v[0]) ** (1 / yrs) - 1
    peak = np.maximum.accumulate(v)
    mdd = float((v / peak - 1).min())
    sd = ex.std(ddof=1)
    return {"cagr": cagr, "vol": rr.std(ddof=1) * np.sqrt(252), "sharpe": ex.mean() / sd * np.sqrt(252) if sd > 0 else 0.0,
            "mdd": mdd, "mar": cagr / abs(mdd) if mdd < 0 else np.inf}


def in_sample_sharpe(m: Market, val: np.ndarray, y0: int, y1: int) -> float:
    yr = m.dates.year
    sel = np.where((yr >= y0) & (yr <= y1))[0]
    a, b = max(int(sel[0]) - 1, 0), int(sel[-1])
    v = val[a:b + 1]
    if np.isnan(v).any():
        return -np.inf
    rr = v[1:] / v[:-1] - 1
    ex = rr - m.ret[a + 1:b + 1, I_CASH]
    sd = ex.std(ddof=1)
    return ex.mean() / sd * np.sqrt(252) if sd > 0 else -np.inf


def monthly(m: Market, val: np.ndarray, a: int, b: int) -> pd.DataFrame:
    s = pd.Series(val[a:b + 1], index=m.dates[a:b + 1])
    me = s.groupby(s.index.to_period("M")).last()
    first = pd.Series([s.iloc[0]], index=[me.index[0] - 1])
    me = pd.concat([first, me])
    r = me.pct_change().dropna()
    c = pd.Series(np.cumprod(1 + m.ret[a:b + 1, I_CASH]), index=m.dates[a:b + 1])
    cm = c.groupby(c.index.to_period("M")).last()
    cm = pd.concat([pd.Series([c.iloc[0]], index=[cm.index[0] - 1]), cm]).pct_change().dropna()
    return pd.DataFrame({"r": r, "cash": cm})


def m_sharpe(r: np.ndarray, c: np.ndarray) -> float:
    ex = r - c
    sd = ex.std(ddof=1)
    return ex.mean() / sd * np.sqrt(12) if sd > 0 else 0.0


def m_mar(r: np.ndarray) -> float:
    v = np.cumprod(np.concatenate([[1.0], 1 + r]))
    yrs = len(r) / 12
    cagr = v[-1] ** (1 / yrs) - 1
    mdd = (v / np.maximum.accumulate(v) - 1).min()
    return cagr / abs(mdd) if mdd < 0 else 10.0


def stationary_idx(n: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    p = 1.0 / mean_block
    out = np.empty(n, dtype=int)
    out[0] = rng.integers(n)
    for k in range(1, n):
        out[k] = rng.integers(n) if rng.random() < p else (out[k - 1] + 1) % n
    return out


def boot_delta(rc: np.ndarray, rb: np.ndarray, cash: np.ndarray, reps: int = 5000, block: float = 12.0,
               seed: int = 20261006) -> dict:
    rng = np.random.default_rng(seed)
    ds, dm = np.empty(reps), np.empty(reps)
    n = len(rc)
    for k in range(reps):
        ix = stationary_idx(n, block, rng)
        ds[k] = m_sharpe(rc[ix], cash[ix]) - m_sharpe(rb[ix], cash[ix])
        dm[k] = m_mar(rc[ix]) - m_mar(rb[ix])
    return {"d_sharpe": m_sharpe(rc, cash) - m_sharpe(rb, cash), "d_sharpe_p05": float(np.percentile(ds, 5)),
            "d_sharpe_pbonf": float(np.percentile(ds, 100 * 0.10 / 7)),
            "d_mar": m_mar(rc) - m_mar(rb), "d_mar_p05": float(np.percentile(dm, 5)),
            "d_mar_pbonf": float(np.percentile(dm, 100 * 0.10 / 7))}


# ───────────────────────────── 걷기 전진 ─────────────────────────────

def year_of_decision(m: Market, i: int) -> int:
    return int(m.dates[min(i + 1, len(m.dates) - 1)].year)


def walk_forward(m: Market, freq: str, start_full: int, last_year: int) -> dict:
    """모든 조합을 한 번씩 전 기간 모의 → 해마다 직전 10년 샤프 최고 조합 선택 → 이어 붙인 일정."""
    dps = decision_points(m.dates, freq)
    combos = [(f, p) for f in FAMILIES for p in GRID[f]]
    scheds, vals = {}, {}
    for f, p in combos:
        s = schedule(m, f, p, dps)
        scheds[(f, p)] = s
        vals[(f, p)] = simulate(m, s, start_full).value
    picks: dict[str, dict[int, tuple]] = {f: {} for f in FAMILIES + ("W",)}
    is_scores: dict[int, dict] = {}
    for Y in range(OOS_START, last_year + 1):
        sc = {c: in_sample_sharpe(m, vals[c], Y - 10, Y - 1) for c in combos}
        is_scores[Y] = sc
        for f in FAMILIES:
            best = max(GRID[f], key=lambda p: (sc[(f, p)], -GRID[f].index(p)))
            picks[f][Y] = (f, best)
        picks["W"][Y] = max(combos, key=lambda c: (sc[c], -combos.index(c)))
    stitched = {}
    for name in FAMILIES + ("W",):
        st = {}
        for i in dps:
            Y = year_of_decision(m, int(i))
            if Y not in picks[name]:
                continue
            st[int(i)] = scheds[picks[name][Y]][int(i)]
        stitched[name] = st
    return {"dps": dps, "picks": picks, "stitched": stitched, "scheds": scheds, "vals": vals,
            "is_scores": is_scores}


def baseline_schedules(m: Market, dps: np.ndarray, oos_dps: np.ndarray) -> dict:
    out = {}
    for b in ("B0", "B1", "B2", "B3"):
        if b == "B0":
            out[b] = {int(oos_dps[0]): weights(m, "B0", (), int(oos_dps[0]))}
        else:
            out[b] = {int(i): weights(m, b, (), int(i)) for i in oos_dps}
    return out


def regime_k200_labels(m: Market) -> pd.Series:
    from datetime import date as _date
    ds = [_date(d.year, d.month, d.day) for d in m.dates]
    lab = dict(MRL.session_labels(ds, list(m.local_px[:, 0])))
    return pd.Series([lab[d].label if d in lab else None for d in ds], index=m.dates)


def per_regime(m: Market, val: np.ndarray, a: int, b: int, labels: pd.Series) -> dict:
    rr = pd.Series(val[a + 1:b + 1] / val[a:b] - 1, index=m.dates[a + 1:b + 1])
    lab = labels.reindex(rr.index)
    out = {}
    for L in MRL.LABELS:
        x = rr[lab == L]
        if len(x) < 20:
            out[L] = {"days": int(len(x))}
            continue
        up, dn = x[x > 0], x[x < 0]
        out[L] = {"days": int(len(x)), "ann_ret": float(x.mean() * 252), "ann_vol": float(x.std() * np.sqrt(252)),
                  "hit": float((x > 0).mean()), "payoff": float(up.mean() / abs(dn.mean())) if len(dn) and len(up) else None,
                  "cum": float(np.prod(1 + x) - 1)}
    return out


def era_table(m: Market, val: np.ndarray) -> dict:
    eras = {"2006-10": (2006, 2010), "2011-15": (2011, 2015), "2016-20": (2016, 2020), "2021-26": (2021, 2026)}
    yr = m.dates.year
    out = {}
    for k, (y0, y1) in eras.items():
        sel = np.where((yr >= y0) & (yr <= y1))[0]
        out[k] = daily_metrics(m, val, sel[0] - 1, sel[-1])
    return out


def describe_monthly(r: np.ndarray) -> dict:
    up, dn = r[r > 0], r[r < 0]
    return {"win": float((r > 0).mean()), "payoff": float(up.mean() / abs(dn.mean())) if len(dn) else None}


def run_all(m: Market, freq: str = "M", tax: bool = True, boot: bool = True) -> dict:
    yr = m.dates.year
    last_year = int(yr.max())
    start_full = 0
    wf = walk_forward(m, freq, start_full, last_year)
    dps = wf["dps"]
    oos_dps = np.array([i for i in dps if year_of_decision(m, int(i)) >= OOS_START])
    a = int(oos_dps[0])
    b = len(m.dates) - 1
    bases = baseline_schedules(m, dps, oos_dps)
    res = {"freq": freq, "oos_start": str(m.dates[a].date()), "oos_end": str(m.dates[b].date()), "cands": {}}
    vals = {}
    for name, s in list(bases.items()) + [(k, wf["stitched"][k]) for k in FAMILIES + ("W",)]:
        sim = simulate(m, s, a)
        vals[name] = sim.value
        d = daily_metrics(m, sim.value, a, b)
        yrs = (m.dates[b] - m.dates[a]).days / 365.25
        d["turnover_yr"] = float(sim.turnover[a:].sum() / yrs)
        d["cost_yr"] = float(sim.cost[a:].sum() / yrs)
        mo = monthly(m, sim.value, a, b)
        mo = mo[mo.index <= pd.Period("2026-09", "M")]
        d.update(describe_monthly(mo["r"].to_numpy()))
        d["eras"] = era_table(m, sim.value)
        if tax:
            st = simulate(m, s, a, tax=True)
            d["after_tax"] = daily_metrics(m, st.value, a, b)
        res["cands"][name] = d
    # 판정
    mos = {}
    for name, v in vals.items():
        mo = monthly(m, v, a, b)
        mos[name] = mo[mo.index <= pd.Period("2026-09", "M")]
    cash = mos["B0"]["cash"].to_numpy()
    if boot:
        for name in FAMILIES + ("W",):
            rc = mos[name]["r"].to_numpy()
            jd = {}
            for bname in ("B0", "B1"):
                jd[bname] = boot_delta(rc, mos[bname]["r"].to_numpy(), cash)
            c = res["cands"][name]
            g1 = all(jd[x]["d_sharpe_p05"] > 0 for x in ("B0", "B1"))
            g2 = all(jd[x]["d_mar_p05"] > 0 for x in ("B0", "B1"))
            g3 = all(c["mdd"] >= res["cands"][x]["mdd"] for x in ("B0", "B1"))
            c["judge"] = {"vs": jd, "G1": g1, "G2": g2, "G3": g3, "pass": g1 and g2 and g3}
    # 선택 이력
    res["picks"] = {k: {str(Y): [c[0], list(c[1]) if isinstance(c[1], tuple) else c[1]] for Y, c in v.items()}
                    for k, v in wf["picks"].items()}
    labels = regime_k200_labels(m)
    res["regime"] = {name: per_regime(m, v, a, b, labels) for name, v in vals.items()
                     if name in ("B0", "B1", "B2", "W") + FAMILIES}
    res["_vals"] = vals
    res["_wf"] = wf
    res["_ab"] = (a, b)
    return res


ETF = {  # 2026-10-02 종가(보관소 parquet_etf) — 정수 주 점검용
    "K200": ("069500", "KODEX 200", 112060), "SPX": ("360750", "TIGER 미국S&P500", 25780),
    "NDX": ("379810", "KODEX 미국나스닥100", 27385), "NKY": ("241180", "TIGER 일본니케이225", 35485),
    "HSCEI": ("245360", "TIGER 차이나HSCEI", 11470), "UST10": ("305080", "TIGER 미국채10년선물", 11675),
    "USD": ("261240", "KODEX 미국달러선물", 13965),
}


def lot_check(m: Market, sched: dict[int, np.ndarray], capital: float = 5_000_000, since: str = "2024-01-01") -> dict:
    errs, rest = [], []
    for i, w in sched.items():
        if m.dates[i] < pd.Timestamp(since):
            continue
        tot, err = 0.0, 0.0
        for j, a in enumerate(RISKY):
            px = ETF[a][2]
            q = np.floor(w[j] * capital / px)
            got = q * px / capital
            err += abs(w[j] - got)
            tot += got
        errs.append(err)
        rest.append(1 - tot)
    return {"n": len(errs), "err_mean": float(np.mean(errs)), "err_max": float(np.max(errs)),
            "cash_left_mean": float(np.mean(rest))}


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_jsonable(x) for x in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def main(parquet: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    df = pd.read_parquet(parquet)
    out = {}
    m = load_market(df)
    main_res = run_all(m, "M")
    out["M"] = main_res
    a, b = main_res["_ab"]
    rec = main_res["_wf"]["stitched"]["W"]
    out["lot_W"] = lot_check(m, rec)
    out["lot_fam"] = {f: lot_check(m, main_res["_wf"]["stitched"][f]) for f in FAMILIES}
    for fq in ("W", "Q"):
        out[fq] = run_all(load_market(df), fq, tax=False, boot=False)
    out["hedged"] = run_all(load_market(df, hedged=True), "M", tax=False, boot=False)
    for sh in (-0.005, 0.005):
        mm = load_market(df, k200_div_shift=sh)
        s0 = baseline_schedules(mm, main_res["_wf"]["dps"],
                                np.array([i for i in main_res["_wf"]["dps"] if year_of_decision(mm, int(i)) >= OOS_START]))
        out[f"k200div{sh:+.3f}"] = {k: daily_metrics(mm, simulate(mm, s0[k], a).value, a, b) for k in ("B0", "B1")}
    # 최근 선택 비중(2026 마지막 결정일)
    lastd = max(rec)
    out["W_last_weights"] = {"date": str(m.dates[lastd].date()),
                             "w": {c: float(x) for c, x in zip(COLS, rec[lastd])}}
    with open(os.path.join(out_dir, "results.json"), "w") as f:
        json.dump(_jsonable(out), f, ensure_ascii=False, indent=1)
    # 월 수익(검증 구간) 저장
    mo = pd.DataFrame({k: monthly(m, v, a, b)["r"] for k, v in main_res["_vals"].items()})
    mo.to_csv(os.path.join(out_dir, "monthly_returns_M.csv"))
    print("done")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])


def posthoc_static(parquet: str) -> dict:
    """사후(동결 뒤 추가) — 참고 기준선 B2·B3 도 같은 부트스트랩으로 B0·B1 과 비교한다(판정 후보 아님)."""
    m = load_market(pd.read_parquet(parquet))
    dps = decision_points(m.dates, "M")
    oos = np.array([i for i in dps if year_of_decision(m, int(i)) >= OOS_START])
    a, b = int(oos[0]), len(m.dates) - 1
    bases = baseline_schedules(m, dps, oos)
    mos = {}
    for k, s in bases.items():
        mo = monthly(m, simulate(m, s, a).value, a, b)
        mos[k] = mo[mo.index <= pd.Period("2026-09", "M")]
    cash = mos["B0"]["cash"].to_numpy()
    return {c: {bb: boot_delta(mos[c]["r"].to_numpy(), mos[bb]["r"].to_numpy(), cash) for bb in ("B0", "B1")}
            for c in ("B2", "B3")}
