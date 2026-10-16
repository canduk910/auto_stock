"""도출 규칙의 m 계열 (prereg §4 D*) · 신탁 판 ORC (§6).

규칙 값은 derived_2012.json(전 지수) · derived_2012_kr.json(국내만, 보조) 의 "rule" 에서 읽는다 — 손으로 옮기지 않는다.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STALE = 10
RULES = {"DS": "derived_2012.json", "DKR": "derived_2012_kr.json"}


def rule(name):
    with open(os.path.join(HERE, RULES[name])) as fh:
        return json.load(fh)["rule"]


def sma(c, L):
    return pd.Series(c).rolling(L, min_periods=L).mean().to_numpy()


def volp(c, hist=1000, mn=250):
    r = np.diff(np.log(c), prepend=np.nan)
    sg = pd.Series(r).rolling(20, min_periods=20).std(ddof=1).to_numpy()
    out = np.full(len(c), np.nan)
    for k in range(len(c)):
        if not np.isfinite(sg[k]):
            continue
        h = sg[max(0, k - hist):k]
        h = h[np.isfinite(h)]
        if len(h) < mn:
            continue
        out[k] = np.mean(h < sg[k])
    return out


def m_rule(c, R):
    c = np.asarray(c, float)
    L, lb, band, tab = int(R["L"]), int(R["lb"]), float(R["band"]), R["table"]
    s = sma(c, L)
    out = np.full(len(c), np.nan)
    prev = None
    for k in range(L + lb - 1, len(c)):
        if band > 0 and prev is not None:
            above = (c[k] >= s[k] * (1 - band)) if prev else (c[k] > s[k] * (1 + band))
        else:
            above = c[k] > s[k]
        prev = bool(above)
        rising = s[k] > s[k - lb]
        out[k] = float(tab[("A" if above else "B") + ("R" if rising else "F")])
    ov = R.get("overlay")
    if ov and float(ov["cap"]) < 1.0:
        assert ov["var"] == "VOLP", ov
        x = volp(c)
        st = False
        for k in range(len(c)):
            if not np.isfinite(x[k]):
                continue
            if not st and x[k] >= ov["theta"]:
                st = True
            elif st and x[k] < ov["theta_off"]:
                st = False
            if st and np.isfinite(out[k]):
                out[k] = min(out[k], float(ov["cap"]))
    return out


def to_days(cal, bar_dates, mk):
    bd = pd.DatetimeIndex(bar_dates)
    pos = bd.searchsorted(cal, side="left") - 1
    out = np.full(len(cal), np.nan)
    for i, p in enumerate(pos):
        if p < 0 or (cal[i] - bd[p]).days > STALE:
            continue
        out[i] = mk[p]
    return out


def crash_days(cal, ks_dates, ks_close):
    ks = pd.Series(np.asarray(ks_close, float), index=pd.DatetimeIndex(ks_dates))
    k20 = ks / ks.shift(20) - 1.0
    mark = pd.Series(False, index=ks.index)
    for i in np.nonzero((k20 <= -0.10).to_numpy())[0]:
        mark.iloc[max(0, i - 19):i + 1] = True
    cd = set(mark.index[mark.to_numpy()])
    return np.array([0.0 if d in cd else 1.0 for d in pd.DatetimeIndex(cal)])


def all_days(cal, src, MU, names, crash_src):
    out = {nm: {} for nm in names}
    orc = crash_days(cal, *crash_src)
    for mk, (d, c) in src.items():
        c = np.asarray(c, float)
        for nm in names:
            if nm == "V0":
                out[nm][mk] = to_days(cal, d, MU.m_at_bars(c))
            elif nm == "ORC":
                out[nm][mk] = orc.copy()
            else:
                out[nm][mk] = to_days(cal, d, m_rule(c, rule(nm)))
    return out
