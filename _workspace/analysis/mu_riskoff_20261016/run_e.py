"""etf_trend — on / off / 위약 8판 × NEW · 씨앗별 자산곡선 (prereg §1·§4).

재사용: 앞 재백테스트 run_e.py 그대로(etf_trend_opt load·gen_signals·run_book, 원천 = KOSPI 종합 m).
실행: /opt/anaconda3/envs/upbit-trader/bin/python run_e.py <scratch>
"""
from __future__ import annotations

import os
import sys

for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "/Users/koscom/Projects/auto_stock/tools")
sys.path.insert(0, "/Users/koscom/Projects/auto_stock")
import common as CM  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import market_unit as MU  # noqa: E402
from replay.strategies import etf_trend_opt as EO  # noqa: E402

SCR = sys.argv[1]
W = {"T": EO.T_WIN, "V": EO.V_WIN, "H": EO.H_WIN}
RT_NEW = 0.00028


def _patch_c391():
    from replay.audit import gate_c391b as GT
    orig = GT.load_c391

    def wrapped():
        m = orig()
        m.DB_FIELDS = "/Users/koscom/Projects/auto_stock/_workspace/analysis/wfo_window_20261009/input/stock_master_etf_fields.json"
        return m
    GT.load_c391 = wrapped


def main():
    _patch_c391()
    CM.wrap(EO.BK, "book_summary")
    V = EO.load()
    cal, data = V["cal"], V["data"]
    ser = pd.read_csv(os.path.join(SCR, "series.csv"), index_col=0, parse_dates=True)["kospi"].dropna()
    mk = MU.m_at_bars(ser.to_numpy(float))
    pos = {d: i for i, d in enumerate(pd.DatetimeIndex(ser.index))}
    mu = np.full(len(cal), np.nan)
    for ci, d in enumerate(cal):
        i = pos.get(d)
        if i is not None:
            mu[ci] = mk[i]
    sig_on = EO.gen_signals(data, V["cls"], mu, 20)
    vars_ = {"on": sig_on, "off": [dict(s, m=1.0) for s in sig_on]}
    for sh in CM.SHIFTS:
        ms = CM.shifted(mu, sh)
        vars_[f"plc{sh}"] = [dict(s, m=(float(ms[s["sig_ci"]]) if np.isfinite(ms[s["sig_ci"]]) else None)) for s in sig_on]
    cb = (20, 1.8, 10, True, "gt0")
    EO.COST = RT_NEW
    calx = pd.DatetimeIndex(cal)
    R = {"cal": np.asarray(calx), "m": {"kospi": mu}, "book": {}, "curves": {}}
    for vn, sg in vars_.items():
        wins = ("T", "V", "H") if vn in ("on", "off") else ("T", "V")
        for wn in wins:
            b = EO.run_book(V, sg, cb, W[wn], seeds=C.BOOK_SEEDS, mu_mode="off" if vn == "off" else "enforce")
            R["book"][(vn, wn)] = {"cagr": b["cagr_median"], "mdd": b["mdd_median"]}
            R["curves"][(vn, wn)] = CM.curves(CM.take(), calx, W[wn])
            print("[etf]", vn, wn, round(b["cagr_median"], 5), round(b["mdd_median"], 5), flush=True)
    CM.dump(os.path.join(SCR, "mr", "etf.pkl"), R)
    print("[etf] done", flush=True)


if __name__ == "__main__":
    main()
