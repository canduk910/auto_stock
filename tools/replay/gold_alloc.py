#!/usr/bin/env python3
"""금 투자 추가 — 30년 성적표 자산배분 묶음 (사전 등록 ``_workspace/analysis/gold_20261006/prereg.frozen.md``).

기존 여러 나라 자산배분 연구(``global_alloc`` · ``global_alloc_b``)의 원화 총수익 지수 모형 · 집행(결정일 다음 종가) ·
비용(왕복 0.38%) · 일일 2배 모형 · 걷기 전진 규칙을 그대로 쓰고, 자산 목록만 바꿀 수 있게 일반화했다.

입력
- ``data/archive/global_long/global_daily_krw.parquet`` (기존 계열 · 다시 만들지 않는다)
- ``data/archive/global_long/raw/usagold_xauusd_daily.csv`` (런던 금 현물 달러 일별 · usagold.com)

    python tools/replay/gold_alloc.py <global_daily_krw.parquet> <gold_csv> <out_dir>
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_TOOLS)
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import global_alloc as G  # noqa: E402
from replay import global_alloc_b as GB  # noqa: E402

GOLD_FEE = 0.0045                      # 국내 금 ETF 총보수 0.39~0.68% 의 가운데(연)
C_LEV = GB.C_LEV_BASE                  # 2배 상품 연 부대비용 0.8%
EQUITY_LIKE = set(G.EQUITY) | {"LNDX"}  # 시장 유닛(F5)을 받는 자산


# ═════════════════════════════════ 금 계열 ═════════════════════════════════

def load_gold_csv(path: str) -> pd.Series:
    d = pd.read_csv(path, parse_dates=["date"])
    s = d.set_index("date")["usd_oz"].astype(float)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s[s > 0]


def align_before(s: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    """KRX 거래일 D 마다 D 보다 앞선 마지막 관측(미국 자산 관례 — ``global_alloc_data._align(strict_before=True)``)."""
    src = s.shift(1, freq="D")
    return src.reindex(src.index.union(idx)).ffill().reindex(idx)


def gold_columns(df: pd.DataFrame, gold_usd: pd.Series) -> pd.DataFrame:
    """금 원화 일 수익 열. ``GOLD_lret`` 달러 가격 변화 · ``GOLD_ret`` 환노출 · ``GOLD_hret`` 환헤지(금리차) · ``GOLD_px_local``.

    환율·금리는 기존 parquet 의 ``fx_usdkrw`` · ``r_kr`` · ``r_us`` (이미 D 앞 관측으로 정렬돼 있다)를 그대로 쓴다.
    """
    idx = pd.DatetimeIndex(df.index)
    px = align_before(gold_usd, idx)
    if px.isna().any():
        raise ValueError(f"금 가격 결측 {int(px.isna().sum())}일 — 첫 날 {px[px.isna()].index[0].date()}")
    dt_y = pd.Series(idx, index=idx).diff().dt.days.fillna(1).astype(float) / 365.0
    lret = px.pct_change().fillna(0.0)
    fx = df["fx_usdkrw"].astype(float)
    fxr = (fx / fx.shift(1)).fillna(1.0) - 1.0
    ret = (1 + lret) * (1 + fxr) - 1
    carry = (df["r_kr"].shift(1).bfill() - df["r_us"].shift(1).bfill()) * dt_y
    hret = lret + carry
    out = pd.DataFrame({"GOLD_lret": lret, "GOLD_ret": ret, "GOLD_hret": hret, "GOLD_px_local": px}, index=idx)
    out.iloc[0, :3] = 0.0
    return out


def lev2(lret: np.ndarray, ret: np.ndarray, hret: np.ndarray, cash: np.ndarray, dt: np.ndarray, kind: str,
         c: float = C_LEV) -> np.ndarray:
    """일일 2배 상품 원화 일 수익 — ``global_alloc_b.lev_returns`` 의 해외 자산 식 그대로.

    rf(현지 조달금리·dt) = cash − (hret − lret) · fx = (1+ret)/(1+lret) − 1.
    U(환노출) = (1 + 2·lret − rf − c·dt)(1 + fx) − 1 · H(환헤지) = 2·lret − rf − c·dt + (cash − rf).
    """
    fx = (1 + ret) / (1 + lret) - 1
    rf = cash - (hret - lret)
    if kind == "U":
        x = (1 + 2 * lret - rf - c * dt) * (1 + fx) - 1
    elif kind == "H":
        x = 2 * lret - rf - c * dt + (cash - rf)
    else:
        raise ValueError(kind)
    x = np.maximum(x, -1.0)
    x[0] = 0.0
    return x


# ═════════════════════════════════ 일반 시장 ═════════════════════════════════

@dataclass
class AMkt:
    """자산 목록을 고를 수 있는 시장. 현금은 항상 마지막 열."""
    dates: pd.DatetimeIndex
    cols: tuple
    ret: np.ndarray            # T×N 일 원화 수익(보수 차감 전)
    fee: np.ndarray            # T×N 일 보수
    dt_y: np.ndarray
    taxable: np.ndarray
    divtax: np.ndarray
    local_px: np.ndarray       # T×(N−1) 장세 라벨용 현지 가격
    cache: dict = field(default_factory=dict)

    @property
    def i_cash(self) -> int:
        return len(self.cols) - 1

    @property
    def nr(self) -> int:
        return len(self.cols) - 1

    @property
    def idx(self) -> np.ndarray:
        if "idx" not in self.cache:
            self.cache["idx"] = np.cumprod(1 + self.ret, axis=0)
        return self.cache["idx"]


def asset_series(df: pd.DataFrame, a: str) -> tuple[np.ndarray, float, bool, float, np.ndarray]:
    """자산 이름 → (원화 일 수익, 연 보수, 차익 과세, 연 배당 원천징수율, 장세용 현지 가격)."""
    T = len(df)
    dates = pd.DatetimeIndex(df.index)
    dt = pd.Series(dates, index=dates).diff().dt.days.fillna(1).to_numpy(float) / 365.0
    cash = df["CASH_ret"].to_numpy(float)
    if a in G.RISKY:
        r = df[f"{a}_ret"].to_numpy(float)
        if a in G.EQUITY:
            lp = df[f"{a}_px_local"].to_numpy(float)
        elif a == "UST10":
            lp = np.cumprod(1 + df["UST10_lret"].to_numpy(float))
        else:
            lp = df["fx_usdkrw"].to_numpy(float)
        return r, G.FEE[a], a in G.TAXABLE_GAIN, G.DIV_FOR_TAX.get(a, 0.0) * G.TAX, lp
    if a == "CASH":
        return cash, G.FEE["CASH"], False, 0.0, np.ones(T)
    gl, gr, gh = (df[c].to_numpy(float) for c in ("GOLD_lret", "GOLD_ret", "GOLD_hret"))
    gp = df["GOLD_px_local"].to_numpy(float)
    if a == "GOLD":
        return gr, GOLD_FEE, True, 0.0, gp
    if a == "GOLD_H":
        return gh, GOLD_FEE, True, 0.0, gp
    if a in ("LGOLD", "LGOLD_H"):
        return lev2(gl, gr, gh, cash, dt, "U" if a == "LGOLD" else "H"), 0.0, True, 0.0, gp
    if a == "LNDX":
        x = GB.lev_returns(df, "U", C_LEV)["LNDX"]
        return x, 0.0, True, 2 * G.DIV_FOR_TAX["NDX"] * G.TAX, df["NDX_px_local"].to_numpy(float)
    raise ValueError(a)


def build_mkt(df: pd.DataFrame, risky: tuple) -> AMkt:
    cols = tuple(risky) + ("CASH",)
    dates = pd.DatetimeIndex(df.index)
    dt = pd.Series(dates, index=dates).diff().dt.days.fillna(1).to_numpy(float) / 365.0
    T, N = len(dates), len(cols)
    ret, lp = np.zeros((T, N)), np.zeros((T, N - 1))
    fee_rate, taxable, divtax = np.zeros(N), np.zeros(N, bool), np.zeros(N)
    for j, a in enumerate(cols):
        r, f, tx, dv, p = asset_series(df, a)
        ret[:, j], fee_rate[j], taxable[j], divtax[j] = r, f, tx, dv
        if j < N - 1:
            lp[:, j] = p
    ret[0, :] = 0.0
    return AMkt(dates, cols, ret, np.outer(dt, fee_rate), dt, taxable, divtax, lp)


def wvec(m: AMkt, spec: dict) -> np.ndarray:
    w = np.zeros(len(m.cols))
    for a, x in spec.items():
        w[m.cols.index(a)] = x
    if abs(w.sum() - 1.0) > 1e-9:
        raise ValueError(f"비중 합 {w.sum()} ≠ 1")
    return w


# ═════════════════════════════════ 집행 ═════════════════════════════════

@dataclass
class Sim:
    value: np.ndarray
    turnover: float
    cost: float
    n_trades: int


def simulate(m: AMkt, sched: dict, a: int, b: int, tax: bool = False,
             cost_one_way: float = G.COST_ONE_WAY) -> Sim:
    """``global_alloc_b.simulate`` 와 같은 규칙(밴드 제외): a 종가 현금 1 · 결정 i 의 비중을 i+1 종가 집행."""
    N, ic = len(m.cols), m.i_cash
    r = m.ret - m.fee
    hold = np.zeros(N)
    hold[ic] = 1.0
    basis = hold.copy()
    val = np.full(len(m.dates), np.nan)
    val[a] = 1.0
    exec_at = {i + 1: w for i, w in sched.items() if a <= i and i + 1 <= b}
    risky = np.arange(N) != ic
    turn_tot = cost_tot = 0.0
    nt = 0
    for t in range(a + 1, b + 1):
        hold = hold * (1 + r[t])
        if tax:
            d = hold * m.divtax * m.dt_y[t]
            d[ic] = hold[ic] * G.TAX * max(r[t, ic], 0.0)
            hold = hold - d
        V = hold.sum()
        if t in exec_at and V > 0:
            tgt = exec_at[t]
            cur = hold / V
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
                new[ic] -= tx
            hold = new
            turn_tot += turn
            cost_tot += c / V
            nt += 1
            V = hold.sum()
        val[t] = V
    if tax:
        gain = np.where(m.taxable, np.maximum(hold - basis, 0.0), 0.0).sum()
        val[b] -= G.TAX * gain
    return Sim(val, turn_tot, cost_tot, nt)


def static_schedule(m: AMkt, w: np.ndarray, a: int, b: int, freq: str | None) -> dict:
    """freq None = 시작일에 사서 보유. 'M'·'Q' = 그 주기 마지막 거래일 결정(시작일 a 포함)."""
    if freq is None:
        return {a: w}
    dps = [int(i) for i in G.decision_points(m.dates, freq) if a <= i < b]
    if a not in dps:
        dps = [a] + dps
    return {i: w for i in dps}


def inv_vol_weights(m: AMkt, i: int, risky_share: float = 0.75, window: int = 252) -> np.ndarray:
    """위험 자산 전부를 직전 window 거래일 원화 일 변동성 역수로 나눠 risky_share, 나머지 현금.
    window 일 미만(또는 변동성 0)이면 위험 자산 균등 risky_share."""
    nr = m.nr
    w = np.zeros(len(m.cols))
    if i + 1 >= window:
        v = m.ret[i - window + 1:i + 1, :nr].std(axis=0, ddof=1)
        if np.all(v > 0) and np.all(np.isfinite(v)):
            iv = (1 / v) / (1 / v).sum()
            w[:nr] = risky_share * iv
            w[m.i_cash] = 1 - risky_share
            return w
    w[:nr] = risky_share / nr
    w[m.i_cash] = 1 - risky_share
    return w


# ═════════════════════════════════ 걷기 전진 (1차 규칙 · 자산 수 일반화) ═════════════════════════════════

def _i_ust(m: AMkt):
    return m.cols.index("UST10") if "UST10" in m.cols else None


def _eq_idx(m: AMkt) -> tuple:
    return tuple(j for j, a in enumerate(m.cols[:-1]) if a in EQUITY_LIKE)


def _mom(m: AMkt, months: int) -> np.ndarray:
    k = ("mom", months)
    if k not in m.cache:
        n = 21 * months
        idx = m.idx
        out = np.full_like(idx, np.nan)
        out[n:] = idx[n:] / idx[:-n] - 1
        m.cache[k] = out
    return m.cache[k]


def _sma_ratio(m: AMkt, months: int) -> np.ndarray:
    k = ("sma", months)
    if k not in m.cache:
        n = 21 * months
        d = pd.DataFrame(m.idx)
        m.cache[k] = (d / d.rolling(n, min_periods=n).mean()).to_numpy()
    return m.cache[k]


def _vol(m: AMkt, w: int) -> np.ndarray:
    k = ("vol", w)
    if k not in m.cache:
        m.cache[k] = pd.DataFrame(m.ret).rolling(w, min_periods=w).std().to_numpy() * np.sqrt(252)
    return m.cache[k]


def score(m: AMkt, kind: str, i: int) -> tuple[np.ndarray, np.ndarray]:
    nr, ic = m.nr, m.i_cash
    if kind == "B":
        ms = [_mom(m, L)[i] for L in (1, 3, 6, 12)]
        return np.mean([x[:nr] for x in ms], axis=0), np.mean([x[:nr] - x[ic] for x in ms], axis=0)
    x = _mom(m, int(kind[1:]))[i]
    return x[:nr], x[:nr] - x[ic]


def market_unit(m: AMkt, i: int) -> np.ndarray:
    if "mu" not in m.cache:
        d = pd.DataFrame(m.idx[:, :m.nr])
        sma = d.rolling(60, min_periods=60).mean()
        above = (d > sma).to_numpy()
        up = (sma > sma.shift(20)).to_numpy()
        mu = np.where(above & up, 1.0, np.where(above, 0.75, np.where(up, 0.5, 0.0)))
        mu[np.isnan(sma.shift(20).to_numpy())] = np.nan
        m.cache["mu"] = mu
    return m.cache["mu"][i]


def regime_states(m: AMkt) -> tuple[np.ndarray, np.ndarray]:
    if "regime" in m.cache:
        return m.cache["regime"]
    MRL = G.MRL
    T, nr = len(m.dates), m.nr
    down = np.full((T, nr), np.nan)
    volat = np.full((T, nr), np.nan)
    for j in range(nr):
        if m.cols[j] == "CASH":
            continue
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


def _cash_only(m: AMkt) -> np.ndarray:
    w = np.zeros(len(m.cols))
    w[m.i_cash] = 1.0
    return w


def _to_fallback(m: AMkt, w: np.ndarray, freed: float, fb: str, ust_on: bool) -> np.ndarray:
    if freed <= 0:
        return w
    iu = _i_ust(m)
    if fb == "ust" and ust_on and iu is not None:
        w[iu] += freed
    else:
        w[m.i_cash] += freed
    return w


def weights(m: AMkt, fam: str, p: tuple, i: int) -> np.ndarray:
    """``global_alloc.weights`` 의 F1~F6 을 위험 자산 수 nr 로 일반화(1/7 → 1/nr). 미국채가 없으면 대피 = 현금."""
    nr, ic, iu, eq = m.nr, m.i_cash, _i_ust(m), _eq_idx(m)
    w = np.zeros(len(m.cols))
    if fam == "F1":
        L, sig, fb = p
        if sig == "ret":
            x = _mom(m, L)[i]
            if np.isnan(x).any():
                return _cash_only(m)
            on = x[:nr] > x[ic]
        else:
            x = _sma_ratio(m, L)[i]
            if np.isnan(x).any():
                return _cash_only(m)
            on = x[:nr] > 1.0
        freed = 0.0
        for j in range(nr):
            if on[j]:
                w[j] = 1 / nr
            else:
                freed += 1 / nr
        return _to_fallback(m, w, freed, fb, bool(on[iu]) if iu is not None else False)
    if fam in ("F2", "F3"):
        kind, N = p[0], p[1]
        sc, ex = score(m, kind, i)
        if np.isnan(sc).any() or np.isnan(ex).any():
            return _cash_only(m)
        top = np.argsort(-sc, kind="stable")[:N]
        if fam == "F2":
            w[top] = 1 / N
            return w
        freed = 0.0
        for j in top:
            if ex[j] > 0:
                w[j] += 1 / N
            else:
                freed += 1 / N
        return _to_fallback(m, w, freed, p[2], bool(ex[iu] > 0) if iu is not None else False)
    if fam == "F4":
        W, tgt = p
        v = _vol(m, W)[i, :nr]
        if i < W or np.isnan(v).any() or (v <= 0).any():
            return _cash_only(m)
        raw = (1 / v) / (1 / v).sum()
        if tgt is not None:
            cov = np.cov(m.ret[i - W + 1:i + 1, :nr].T) * 252
            pv = float(np.sqrt(raw @ cov @ raw))
            raw = raw * min(1.0, tgt / pv) if pv > 0 else raw
        w[:nr] = raw
        w[ic] = 1 - raw.sum()
        return w
    if fam == "F5":
        kind, N, mu_on = p
        sc, ex = score(m, kind, i)
        v = _vol(m, 63)[i, :nr]
        mu = market_unit(m, i)
        if np.isnan(sc).any() or np.isnan(ex).any() or np.isnan(v).any() or np.isnan(mu).any():
            return _cash_only(m)
        top = [j for j in np.argsort(-sc, kind="stable")[:N] if ex[j] > 0]
        if top:
            iv = np.array([1 / v[j] for j in top])
            iv = iv / iv.sum()
            for j, x in zip(top, iv):
                w[j] = x * (mu[j] if (mu_on and j in eq) else 1.0)
        w[ic] = 1 - w[:nr].sum()
        return w
    if fam == "F6":
        mv, md, fb = p
        down, volat = regime_states(m)
        if np.isnan(down[i]).any() or np.isnan(volat[i]).any():
            return _cash_only(m)
        mult = np.where(volat[i] > 0, mv, 1.0) * np.where(down[i] > 0, md, 1.0)
        w[:nr] = mult / nr
        freed = (1 - mult).sum() / nr
        return _to_fallback(m, w, freed, fb, bool(mult[iu] >= 1.0) if iu is not None else False)
    raise ValueError(fam)


def in_sample_sharpe(m: AMkt, val: np.ndarray, y0: int, y1: int) -> float:
    yr = m.dates.year
    sel = np.where((yr >= y0) & (yr <= y1))[0]
    a, b = max(int(sel[0]) - 1, 0), int(sel[-1])
    v = val[a:b + 1]
    if np.isnan(v).any():
        return -np.inf
    rr = v[1:] / v[:-1] - 1
    ex = rr - m.ret[a + 1:b + 1, m.i_cash]
    sd = ex.std(ddof=1)
    return ex.mean() / sd * np.sqrt(252) if sd > 0 else -np.inf


def year_of_decision(m: AMkt, i: int) -> int:
    return int(m.dates[min(i + 1, len(m.dates) - 1)].year)


def walk_forward_W(m: AMkt, freq: str = "M") -> dict:
    """1차 ``global_alloc.walk_forward`` 의 W: 모든 조합을 전 기간 한 번 모의 → 해마다 직전 10년 일 샤프 최고 조합 →
    그해 결정일 비중을 그 조합 것으로 이어 붙인다. 검증 시작 = 2006 년 첫 집행 결정일."""
    dps = G.decision_points(m.dates, freq)
    combos = [(f, p) for f in G.FAMILIES for p in G.GRID[f]]
    b = len(m.dates) - 1
    scheds, vals = {}, {}
    for c in combos:
        s = {int(i): weights(m, c[0], c[1], int(i)) for i in dps}
        scheds[c] = s
        vals[c] = simulate(m, s, 0, b).value
    picks = {}
    last_year = int(m.dates.year.max())
    for Y in range(G.OOS_START, last_year + 1):
        sc = {c: in_sample_sharpe(m, vals[c], Y - 10, Y - 1) for c in combos}
        picks[Y] = max(combos, key=lambda c: (sc[c], -combos.index(c)))
    st = {}
    for i in dps:
        Y = year_of_decision(m, int(i))
        if Y in picks:
            st[int(i)] = scheds[picks[Y]][int(i)]
    a = min(st)
    return {"sched": st, "a": a, "b": b, "picks": {str(Y): [c[0], list(c[1])] for Y, c in picks.items()}}


# ═════════════════════════════════ 지표 · 판정 ═════════════════════════════════

CRISES = {"1997": ("1997-01-01", "1997-12-31"), "2000-02": ("2000-01-01", "2002-12-31"),
          "2008": ("2008-01-01", "2008-12-31"), "2020": ("2020-01-01", "2020-12-31"),
          "2022": ("2022-01-01", "2022-12-31")}


def window_return(dates: pd.DatetimeIndex, v: np.ndarray, d0: str, d1: str) -> float | None:
    """구간 첫 날 전 마지막 값 → 구간 끝 날 이하 마지막 값. 곡선이 구간 시작 전에 없으면 None."""
    s = pd.Series(v, index=dates).dropna()
    before = s[s.index < pd.Timestamp(d0)]
    upto = s[s.index <= pd.Timestamp(d1)]
    if before.empty or upto.empty or upto.index[-1] < pd.Timestamp(d0):
        return None
    return float(upto.iloc[-1] / before.iloc[-1] - 1)


def monthly_r(m: AMkt, v: np.ndarray, a: int, b: int) -> pd.DataFrame:
    s = pd.Series(v[a:b + 1], index=m.dates[a:b + 1])
    c = pd.Series(np.cumprod(1 + m.ret[a:b + 1, m.i_cash]), index=m.dates[a:b + 1])
    out = {}
    for k, ser in (("r", s), ("cash", c)):
        me = ser.groupby(ser.index.to_period("M")).last()
        me = pd.concat([pd.Series([ser.iloc[0]], index=[me.index[0] - 1]), me])
        out[k] = me.pct_change().dropna()
    d = pd.DataFrame(out)
    return d[d.index <= pd.Period("2026-09", "M")]


def judge(m: AMkt, v: np.ndarray, base: dict, a: int, b: int, n_bonf: int) -> dict:
    """성적표 기존 기준(``global_alloc_b.judge`` 의 G1~G3): B0·B1 대비 월 Δ샤프·ΔMAR 5백분위 > 0 · 최대 낙폭 얕거나 같다."""
    mc = monthly_r(m, v, a, b)
    cash = mc["cash"].to_numpy()
    vs, mdd = {}, {}
    for k, vb in base.items():
        vs[k] = GB.boot(mc["r"].to_numpy(), monthly_r(m, vb, a, b)["r"].to_numpy(), cash, n_bonf)
        mdd[k] = float(np.min(vb[a:b + 1] / np.maximum.accumulate(vb[a:b + 1]) - 1))
    mdd_c = float(np.min(v[a:b + 1] / np.maximum.accumulate(v[a:b + 1]) - 1))
    g1 = all(vs[k]["d_sharpe_p05"] > 0 for k in base)
    g2 = all(vs[k]["d_mar_p05"] > 0 for k in base)
    g3 = all(mdd_c >= mdd[k] for k in base)
    return {"vs": vs, "mdd": mdd_c, "mdd_base": mdd, "G1": g1, "G2": g2, "G3": g3, "pass": bool(g1 and g2 and g3)}


# ═════════════════════════════════ ETF 대조 ═════════════════════════════════

def etf_close(ticker: str, archive: str = "/Users/koscom/Projects/auto_stock/data/archive/krx_daily_long/parquet_etf") -> pd.Series:
    import glob
    parts = []
    for f in sorted(glob.glob(os.path.join(archive, "naver_daily_*.parquet"))):
        x = pd.read_parquet(f, filters=[("ticker", "==", ticker)], columns=["bas_dd", "close"])
        if len(x):
            parts.append(x)
    d = pd.concat(parts)
    s = d.set_index(pd.to_datetime(d["bas_dd"]))["close"].astype(float)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s[s > 0]


def tracking(model_ret: pd.Series, etf_px: pd.Series) -> dict:
    """모형 일 수익(보수 차감) ↔ ETF 종가. 겹치는 거래일 기준 연 수익 차 · 연율 추적 차 · 월 상관 · 누적 차."""
    er = etf_px.pct_change()
    c = pd.concat([model_ret, er], axis=1, join="inner").dropna()
    c.columns = ["model", "etf"]
    c = c.iloc[1:]
    cm = (1 + c).cumprod()
    yr = cm.groupby(cm.index.year).last()
    yr0 = pd.concat([pd.DataFrame([[1.0, 1.0]], columns=cm.columns, index=[yr.index[0] - 1]), yr])
    yret = (yr0 / yr0.shift(1) - 1).dropna()
    mo = cm.groupby(cm.index.to_period("M")).last().pct_change().dropna()
    yrs = (c.index[-1] - c.index[0]).days / 365.25
    return {"start": str(c.index[0].date()), "end": str(c.index[-1].date()), "days": int(len(c)),
            "cagr_model": float(cm["model"].iloc[-1] ** (1 / yrs) - 1), "cagr_etf": float(cm["etf"].iloc[-1] ** (1 / yrs) - 1),
            "ann_diff": float((c["model"] - c["etf"]).mean() * 252),
            "te_daily_ann": float((c["model"] - c["etf"]).std() * np.sqrt(252)),
            "te_monthly_ann": float((mo["model"] - mo["etf"]).std() * np.sqrt(12)),
            "corr_monthly": float(mo.corr().iloc[0, 1]),
            "yearly": {int(y): {"model": float(r.model), "etf": float(r.etf), "diff": float(r.model - r.etf)}
                       for y, r in yret.iterrows()}}
