"""후보 m 계열 (prereg §2). 봉 단위 m → 날 단위 m(앞선 마지막 봉 · 10일 묵음 = NaN) 은 MU.m_for_days 와 같은 대응."""
from __future__ import annotations

import numpy as np
import pandas as pd

TABLE = {(True, True): 1.0, (True, False): 0.75, (False, True): 0.5, (False, False): 0.0}
STALE = 10
BASIC = ("V0", "V1a", "V1b", "V2a", "V2b", "V3", "V4", "V5a", "V5b")


def sma(c, L):
    cs = np.concatenate([[0.0], np.cumsum(c)])
    out = np.full(len(c), np.nan)
    out[L - 1:] = (cs[L:] - cs[:-L]) / L
    return out


def m_float(c, L=60, lb=20, band=0.0):
    """기본 판정(실수 계산). band>0 이면 위/아래에 히스테리시스."""
    s = sma(c, L)
    out = np.full(len(c), np.nan)
    prev_above = None
    for k in range(L + lb - 1, len(c)):
        raw_above = c[k] > s[k]
        if band > 0 and prev_above is not None:
            above = (c[k] >= s[k] * (1 - band)) if prev_above else (c[k] > s[k] * (1 + band))
        else:
            above = raw_above
        prev_above = above
        rising = s[k] > s[k - lb]
        out[k] = TABLE[(bool(above), bool(rising))]
    return out


def confirm(m, n):
    out = np.full(len(m), np.nan)
    eff = np.nan
    for k in range(len(m)):
        if not np.isfinite(m[k]):
            eff = np.nan
            continue
        if not np.isfinite(eff):
            eff = m[k]
        elif m[k] != eff and k - n + 1 >= 0 and all(np.isfinite(m[k - j]) and m[k - j] == m[k] for j in range(n)):
            eff = m[k]
        out[k] = eff
    return out


def dd_trigger(c, on=-0.08, off=-0.04, w=20):
    act = np.zeros(len(c), bool)
    st = False
    for k in range(len(c)):
        if k < w - 1:
            continue
        dd = c[k] / c[k - w + 1:k + 1].max() - 1.0
        if not st and dd <= on:
            st = True
        elif st and dd > off:
            st = False
        act[k] = st
    return act


def vol_trigger(c, q=0.90, w=20, hist=1000, mn=250):
    r = np.diff(np.log(c), prepend=np.nan)
    sg = pd.Series(r).rolling(w, min_periods=w).std(ddof=1).to_numpy()
    act = np.zeros(len(c), bool)
    for k in range(len(c)):
        if not np.isfinite(sg[k]):
            continue
        h = sg[max(0, k - hist):k]
        h = h[np.isfinite(h)]
        if len(h) < mn:
            continue
        act[k] = np.mean(h < sg[k]) >= q
    return act


def overlay(m, act, cap):
    out = m.copy()
    ok = np.isfinite(out) & act
    out[ok] = np.minimum(out[ok], cap)
    return out


def bars_m(name, c, base0, f_star=None, x_star=None):
    """name 의 봉 단위 m. base0 = 운영 classify 그대로의 V0(MU.m_at_bars)."""
    c = np.asarray(c, float)
    if name == "V0":
        return base0.copy()
    if name == "V1a":
        return confirm(base0, 2)
    if name == "V1b":
        return confirm(base0, 3)
    if name == "V2a":
        return m_float(c, band=0.01)
    if name == "V2b":
        return m_float(c, band=0.02)
    if name == "V3":
        return overlay(base0, dd_trigger(c), 0.0)
    if name == "V4":
        return overlay(base0, vol_trigger(c), 0.5)
    if name == "V5a":
        return m_float(c, L=60, lb=10)
    if name == "V5b":
        return m_float(c, L=20, lb=20)
    if name == "V6":
        assert f_star and x_star
        if x_star in ("V3", "V4"):
            fb = bars_m(f_star, c, base0)
            return bars_m(x_star, c, fb)            # 덮기는 F* 처리한 기저 위에(확인·띠 지연 없음)
        xb = bars_m(x_star, c, base0)
        if f_star in ("V1a", "V1b"):
            return confirm(xb, 2 if f_star == "V1a" else 3)
        L, lb = (60, 10) if x_star == "V5a" else (20, 20)
        return m_float(c, L=L, lb=lb, band=0.01 if f_star == "V2a" else 0.02)
    raise KeyError(name)


def to_days(cal, bar_dates, mk):
    bd = pd.DatetimeIndex(bar_dates)
    pos = bd.searchsorted(cal, side="left") - 1
    out = np.full(len(cal), np.nan)
    for i, p in enumerate(pos):
        if p < 0 or (cal[i] - bd[p]).days > STALE:
            continue
        out[i] = mk[p]
    return out


def all_days(cal, src, MU, names, f_star=None, x_star=None):
    """src = {'kospi': (dates, closes), 'kosdaq': ...} → {name: {'kospi': arr, 'kosdaq': arr}}"""
    out = {nm: {} for nm in names}
    for mk, (d, c) in src.items():
        c = np.asarray(c, float)
        base0 = MU.m_at_bars(c)
        for nm in names:
            out[nm][mk] = to_days(cal, d, bars_m(nm, c, base0, f_star, x_star))
    return out
