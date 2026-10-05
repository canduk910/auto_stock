#!/usr/bin/env python3
"""30년 재검증 — 6장세 라벨(현행 D4×V4) 30년 성질 · 급락 탐지 지연 (사전 등록 ``mr_regime/prereg.frozen.md`` §4).

라벨 = ``src.engine.market_regime_label.session_labels`` 그대로(D 라벨 = D−1 종가까지), 입력 = 연속 계열
(KOSPI200 지수 × 64.578750 → 2002-10-14 부터 069500). 정답·지그재그·지표는 6장세 튜닝(``opt_regime``) 함수를 그대로 쓴다.

    python -m replay.y30_regime <scratch_dir> <out_dir>
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, ".."), os.path.join(_HERE, "..", "..")):
    _p = os.path.abspath(_p)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay import opt_regime as OR  # noqa: E402
from replay import y30_mr_data as Y  # noqa: E402
from src.engine.market_regime_label import session_labels  # noqa: E402

ALL = ("1997-01-02", "2026-10-02")
EVENTS = {"1997 외환위기": ("1997-07-01", "1998-06-30"), "2000 닷컴": ("2000-01-01", "2001-09-30"),
          "2008 금융위기": ("2008-01-01", "2008-12-31"), "2020 코로나": ("2020-01-01", "2020-06-30")}
CODE = {"stable_up": "UL", "volatile_up": "UH", "stable_flat": "SL", "volatile_flat": "SH",
        "stable_down": "DL", "volatile_down": "DH"}
# 사후(동결 뒤 추가): 동결 창의 2000 사건은 2001-09 바닥을 골라 2000-01 고점을 놓쳤다 → 2000 년 안 바닥 창을 따로 둔다.
EVENTS_POST = {"2000 닷컴(사후 창 2000-01~12)": ("2000-01-01", "2000-12-31")}
NAMES = {"UL": "1 안정상승", "UH": "2 변동상승", "SL": "3 안정횡보", "SH": "4 변동횡보", "DL": "5 안정하락",
         "DH": "6 변동하락"}


def labels(sd, sc) -> pd.Series:
    ds = [date.fromisoformat(str(d)) for d in sd]
    lab = {pd.Timestamp(d): CODE[p.label] for d, p in session_labels(ds, list(sc))}
    idx = pd.DatetimeIndex(sd.astype("datetime64[ns]"))
    return pd.Series([lab.get(d) for d in idx], index=idx, dtype=object)


def dd60_series(c: pd.Series) -> pd.Series:
    """세션 D 의 값 = C(D−1) / max(C(D−60..D−1)) − 1."""
    return (c / c.rolling(60, min_periods=60).max() - 1).shift(1)


def detect(first_true: np.ndarray, p: int, q: int, c: np.ndarray, horizon: int = 250):
    """고점 p 다음 세션부터 처음 참인 세션 → (지연, 그날 위치, 이미 고점 날 참이었나)."""
    already = bool(first_true[p])
    for i in range(p + 1, min(len(c), q + horizon)):
        if first_true[i]:
            return i - p, i, already
    return None, None, already


def window_stats(lab6: pd.Series, c, tdir, tvol, d0, d1, sp):
    m = OR.metrics(lab6, c, tdir, tvol, d0, d1, sp=sp)
    sl = lab6.loc[d0:d1].dropna()
    yrs = (pd.Timestamp(d1) - pd.Timestamp(d0)).days / 365.25
    m["sw_per_cal_year"] = int((sl != sl.shift()).sum() - 1) / yrs
    m["days"] = {NAMES[k]: int((sl == k).sum()) for k in NAMES}
    sp_in = [s for s in sp if pd.Timestamp(d0) <= s[0] <= pd.Timestamp(d1)]
    m["spell_len_median"] = float(np.median([s[2] for s in sp_in])) if sp_in else None
    m["spells_by_cell"] = {NAMES[k]: int(sum(1 for s in sp_in if s[1] == k)) for k in NAMES}
    fwd = (c.shift(-19) / c.shift(1) - 1).reindex(sl.index)
    m["fwd20_by_cell"] = {NAMES[k]: (float(fwd[sl == k].mean()) if (sl == k).any() else None) for k in NAMES}
    lr = np.log(c).diff()
    fvol = (lr.rolling(20).std().shift(-19) * np.sqrt(252)).reindex(sl.index)
    m["fwd_vol_by_cell"] = {NAMES[k]: (float(fvol[sl == k].mean()) if (sl == k).any() else None) for k in NAMES}
    m["fwd20_all"] = float(fwd.mean())
    m["order_up_gt_dn"] = bool(m["fwd_up"] > m["fwd_dn"]) if np.isfinite(m["fwd_spread"]) else None
    return m


def main(scratch, out_dir):
    mk = np.load(os.path.join(scratch, "mkt.npz"))
    sd, sc = mk["sd"], mk["sc"]
    c = pd.Series(sc, index=pd.DatetimeIndex(sd.astype("datetime64[ns]")))
    lab6 = labels(sd, sc)
    # 6장세 코드 → 'U|S|D' + 'L|H' 문자열 (opt_regime.metrics 입력 꼴)
    conv = {"UL": "UL", "UH": "UH", "SL": "SL", "SH": "SH", "DL": "DL", "DH": "DH"}
    lab6 = lab6.map(lambda x: conv.get(x) if x else None)
    tdir, tvol = OR.truth_dir(c), OR.truth_vol(c)
    sp = OR.spells(lab6.dropna())
    res = {"first_label": str(lab6.dropna().index[0].date()), "windows": {}}
    for nm, w in (("30년", ALL),) + Y.SEGS + Y.ERAS:
        res["windows"][nm] = window_stats(lab6, c, tdir, tvol, w[0], w[1], sp)
    # 급락 사건
    mu = pd.Series(np.nan, index=c.index)
    sess = pd.DatetimeIndex(np.load(os.path.join(scratch, "mkt.npz"))["sd"].astype("datetime64[ns]"))
    del sess
    with open(os.path.join(scratch, "panel.pkl"), "rb") as fh:
        import pickle
        P = pickle.load(fh)
    pdates = pd.DatetimeIndex(P.dates.astype("datetime64[ns]"))
    del P
    mu.loc[pdates] = mk["mu"]
    dd = dd60_series(c)
    dirs = lab6.str[0]
    conds = {"a_dd60_le_-10%": (dd <= -0.10).to_numpy(), "b_mu_le_0.5": (mu <= 0.5).to_numpy(),
             "c_mu_eq_0": (mu == 0.0).to_numpy(), "d_label_not_up": (dirs != "U").to_numpy() & dirs.notna().to_numpy(),
             "e_label_down": (dirs == "D").to_numpy()}
    cv = c.to_numpy()
    idx = c.index

    def event_row(p, q):
        row = {"peak": str(idx[p].date()), "peak_close": float(cv[p]), "trough": str(idx[q].date()),
               "trough_close": float(cv[q]), "drop": float(cv[q] / cv[p] - 1), "peak_to_trough_sessions": int(q - p)}
        for nm, arr in conds.items():
            lag, i, already = detect(arr, p, q, cv)
            if lag is None:
                row[nm] = {"lag": None, "already_at_peak": already}
                continue
            row[nm] = {"lag": int(lag), "date": str(idx[i].date()), "already_at_peak": already,
                       "dd_at_detect": float(cv[i - 1] / cv[p] - 1),
                       "remaining_to_trough": float(cv[q] / cv[i - 1] - 1) if i <= q else None,
                       "after_trough": bool(i > q)}
        row["labels_peak_to_trough"] = {NAMES[k]: int((lab6.iloc[p + 1:q + 1] == k).sum()) for k in NAMES}
        return row

    ev = {}
    for nm, (a, b) in EVENTS.items():
        sub = c.loc[a:b]
        q = idx.get_loc(sub.idxmin())
        p0 = max(0, q - 250)
        p = p0 + int(np.argmax(cv[p0:q + 1]))
        ev[nm] = event_row(p, q)
    res["events"] = ev
    evp = {}
    for nm, (a, b) in EVENTS_POST.items():
        sub = c.loc[a:b]
        q = idx.get_loc(sub.idxmin())
        p0 = max(0, q - 250)
        p = p0 + int(np.argmax(cv[p0:q + 1]))
        evp[nm] = event_row(p, q)
    res["events_posthoc"] = evp
    zz = OR.zigzag(c.loc["1996-01-01":], 0.20)
    zrows = []
    for j, (t, kind) in enumerate(zz):
        if kind != "P" or t < pd.Timestamp(ALL[0]):
            continue
        nxt = next(((tt, kk) for tt, kk in zz[j + 1:] if kk == "T"), None)
        if nxt is None:
            continue
        zrows.append(event_row(idx.get_loc(t), idx.get_loc(nxt[0])))
    res["zigzag20_peaks"] = zrows
    # 6장세 × 시장 유닛 (1997 ~)
    sl = lab6.loc[ALL[0]:ALL[1]]
    mm = mu.loc[ALL[0]:ALL[1]]
    res["cross_mu"] = {NAMES[k]: {str(m): int(((sl == k) & (mm == m)).sum()) for m in (1.0, 0.75, 0.5, 0.0)}
                       for k in NAMES}
    # 5년 라벨과의 일치(관문 재확인)
    ref = "/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/regime/final_labels.csv"
    if os.path.exists(ref):
        r = pd.read_csv(ref, parse_dates=["d"]).set_index("d")
        common = r.index.intersection(lab6.index)
        res["gate_5y"] = {"common": int(len(common)), "mismatch": int((r.loc[common, "reg"] != lab6.loc[common]).sum())}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "regime_results.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=float)
    print(json.dumps({k: res["events"][k] for k in res["events"]}, ensure_ascii=False, indent=0)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
