"""etf_trend — 모집단 덤프(pop) · 계좌 변형(acct). 설정 코드는 mu_riskoff run_e.py 그대로(원천 = KOSPI 종합 m).
하드선 = max(E − a·N, E×(1−b)) 를 변형 값으로 바꿔 끼운다(엔진 상수 2.0 · 9%).
실행: /opt/anaconda3/envs/upbit-trader/bin/python drv_e.py <scratch> pop|acct
"""
from __future__ import annotations

import json
import os
import pickle
import sys

for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "mu_riskoff_20261016"))
sys.path.insert(0, "/Users/koscom/Projects/auto_stock/tools")
sys.path.insert(0, "/Users/koscom/Projects/auto_stock")
import common as CM  # noqa: E402
import xcommon as X  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import market_unit as MU  # noqa: E402
from replay.strategies import etf_trend_opt as EO  # noqa: E402
from replay.strategies import etf_trend_b_audit as EA  # noqa: E402

SCR, MODE = sys.argv[1], sys.argv[2]
W = {"T": EO.T_WIN, "V": EO.V_WIN, "H": EO.H_WIN}
RT_NEW = 0.00028
HARD = {"a": 2.0, "b": 0.09}


def _patch_c391():
    from replay.audit import gate_c391b as GT
    orig = GT.load_c391

    def wrapped():
        m = orig()
        m.DB_FIELDS = "/Users/koscom/Projects/auto_stock/_workspace/analysis/wfo_window_20261009/input/stock_master_etf_fields.json"
        return m
    GT.load_c391 = wrapped


def _post(ps):
    a, b = HARD["a"], HARD["b"]
    lines = [ps.E - a * ps.s.N] if a is not None else []
    if b is not None:
        lines.append(ps.E * (1.0 - b))
    ps.hard = max(lines) if lines else -np.inf
    ps.stop = ps.hard


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
    EO.COST = RT_NEW
    calx = pd.DatetimeIndex(cal)
    bars = {t: {"o": d["o"], "h": d["h"], "l": d["l"], "c": d["c"], "di": d["ci"]} for t, d in data.items()}
    if MODE == "pop":
        recs = []
        for wn, win in W.items():
            g0 = int(calx.searchsorted(pd.Timestamp(win[0])))
            g1 = int(calx.searchsorted(pd.Timestamp(win[1]), side="right")) - 1
            busy = {}
            for t in sorted(sig_on, key=lambda x: (x["entry_ci"], x["ticker"])):
                if not (t["fu"] and EO.mu_ok(t["m"], "gt0")):
                    continue
                if t["entry_ci"] < g0 or t["entry_ci"] > g1 or busy.get(t["ticker"], -1) >= t["entry_ci"]:
                    continue
                raw = V["store"].bars[t["ticker"]]["raw"][t["j"] + 1]
                s = EA.ETFSig(t["ticker"], t["j"] + 1, t["entry_ci"], t["E"], t["E"] * raw, t["N"], t["line"], t["m"],
                              t["tv20"], t["sig_ci"])
                d = data[t["ticker"]]
                ps = EO.run_path_v(s, d, trail=1.8, chan=10, bl=True)
                if ps.exit_gd is not None and ps.exit_gd > g1:
                    ps.exit_gd = None
                busy[t["ticker"]] = ps.exit_gd if ps.exit_gd is not None else 10 ** 9
                recs.append(X.pop_record(ps, bars[t["ticker"]], False, wn))
            print("[etf] pop", wn, len(recs), flush=True)
        X.dump(os.path.join(SCR, "xr", "pop_etf.pkl"), {"cal": np.asarray(cal), "recs": recs,
                                                        "cur": {"hard_atr": 2.0, "hard_pct": 9.0, "trail": 1.8, "chan": 10}})
        return
    specs = json.load(open(os.path.join(HERE, "variants.json")))["etf"]
    prev = pickle.load(open(os.path.join(SCR, "mr", "etf.pkl"), "rb"))
    ist = X.index_state(calx, os.path.join(SCR, "series.csv"))
    X.patch_overlay(EO.EtfPosV, bars_key="d")
    X.patch_exit_line(EO.EtfPosV, lambda ps: ps.stop)
    X.patch_init_params(EO.EtfPosV, "_none", {"ovr": None, "post": _post})
    R = {"cal": np.asarray(cal), "book": {}, "curves": {}, "trades": {}}
    for vn, sp in specs.items():
        ov = sp.get("ovr") or {}
        HARD["a"] = ov.get("hard_atr", 2.0)
        HARD["b"] = ov.get("hard_pct", 9.0)
        HARD["b"] = None if HARD["b"] is None else HARD["b"] / 100.0
        tr = ov.get("trail", 1.8)
        X.CFG["crash"] = None if sp.get("crash") is None else X.crash_flags(calx, ist, sp["crash"], sp.get("shift", 0))
        X.CFG["stall"] = sp.get("stall")
        for wn in sp["wins"]:
            b = EO.run_book(V, sig_on, (20, tr, 10, True, "gt0"), W[wn], seeds=C.BOOK_SEEDS, mu_mode="enforce")
            runs = CM.take()
            bk = {"cagr": b["cagr_median"], "mdd": b["mdd_median"]}
            R["book"][(vn, wn)] = bk
            R["curves"][(vn, wn)] = CM.curves(runs, calx, W[wn])
            if "|" not in vn:
                R["trades"][(vn, wn)] = X.trade_rows(runs, bars, RT_NEW, calx)
            if vn == "V0":
                pv = prev["book"][("on", wn)]
                dd = max(abs(bk["cagr"] - pv["cagr"]), abs(bk["mdd"] - pv["mdd"]))
                print("[etf] repro-book", wn, dd, flush=True)
                if dd > 1e-9:
                    raise SystemExit("V0 계좌 재현 실패 — 중단")
            print("[etf]", vn, wn, round(bk["cagr"], 5), round(bk["mdd"], 5), flush=True)
    X.dump(os.path.join(SCR, "xr", "acct_etf.pkl"), R)
    print("[etf] done", flush=True)


if __name__ == "__main__":
    main()
