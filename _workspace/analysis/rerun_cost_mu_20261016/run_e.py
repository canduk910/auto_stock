"""etf_trend — 시장 유닛 on/off × 비용 NEW/OLD(+엔진 판정 0.38%) (prereg §1~§3).

재사용: ``tools/replay/strategies/etf_trend_opt`` 의 load·gen_signals·attach_exit·stats·run_book(현행 조합 L20|TR1.8|CH10|BLon).
바꾸는 것 = 시장 유닛 원천(069500 → KOSPI 종합, 운영 cycle455 와 같게) · 비용(왕복 상수).
실행: /opt/anaconda3/envs/upbit-trader/bin/python run_e.py <scratch>
"""
from __future__ import annotations

import json
import os
import sys

for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/koscom/Projects/auto_stock/tools")
sys.path.insert(0, "/Users/koscom/Projects/auto_stock")
from replay.audit import config as C  # noqa
from replay.audit import market_unit as MU  # noqa
from replay.strategies import etf_trend_b as EB  # noqa
from replay.strategies import etf_trend_opt as EO  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = sys.argv[1]
RT = {"NEW": 0.00028, "OLD": 0.00284, "J038": 0.0038}
W = {"T": EO.T_WIN, "V": EO.V_WIN, "H": EO.H_WIN}


def _patch_c391():
    """원 스크래치 입력이 사라져 리포 사본(wfo_window_20261009/input, sha 기록 있음)으로 가리킨다."""
    from replay.audit import gate_c391b as GT
    orig = GT.load_c391

    def wrapped():
        m = orig()
        m.DB_FIELDS = "/Users/koscom/Projects/auto_stock/_workspace/analysis/wfo_window_20261009/input/stock_master_etf_fields.json"
        return m
    GT.load_c391 = wrapped


def main():
    _patch_c391()
    V = EO.load()
    cal, data, fadj, corr = V["cal"], V["data"], V["fadj"], V["corr"]
    ser = pd.read_csv(os.path.join(SCR, "series.csv"), index_col=0, parse_dates=True)["kospi"].dropna()
    mk = MU.m_at_bars(ser.to_numpy(float))
    pos = {d: i for i, d in enumerate(pd.DatetimeIndex(ser.index))}
    mu = np.full(len(cal), np.nan)
    for ci, d in enumerate(cal):
        i = pos.get(d)
        if i is not None:
            mu[ci] = mk[i]
    agree = np.isfinite(mu) & np.isfinite(V["mu"])
    R = {"rt": RT, "m_src_agree_with_069500": float(np.mean(mu[agree] == V["mu"][agree])), "n_agree_days": int(agree.sum())}
    print("[etf] loaded · m 일치율(KOSPI 종합 vs 069500)", R["m_src_agree_with_069500"], flush=True)
    sig_on = EO.gen_signals(data, V["cls"], mu, 20)
    sig_off = [dict(s, m=1.0) for s in sig_on]
    cb = (20, 1.8, 10, True, "gt0")
    for mu_name, sg in (("on", sig_on), ("off", sig_off)):
        R[mu_name] = {}
        ex = EO.attach_exit(sg, data, fadj, cal, 1.8, 10, True)
        ded = EB.dedup([t for t in ex if t["fu"] and EO.mu_ok(t["m"], "gt0")], corr)
        for wn, win in W.items():
            d = {"m0_share_sig": float(np.mean([not (s["m"] is not None and s["m"] > 0) for s in sg
                                                if win[0] <= str(cal[s["entry_ci"]].date()) <= win[1]] or [np.nan]))}
            for ck, rt in RT.items():
                ts = [dict(t, RN=t["ret"] - rt) for t in ded if EO.in_win(t, win)]
                d[f"pop_{ck}"] = EO.stats(ts)
                EO.COST = rt
                b = EO.run_book(V, sg, cb, win, seeds=C.BOOK_SEEDS, mu_mode="enforce" if mu_name == "on" else "off")
                d[f"book_{ck}"] = {"cagr": b["cagr_median"], "mdd": b["mdd_median"], "fills_y": b["fills_per_year_median"]}
            R[mu_name][wn] = d
            print("[etf]", mu_name, wn, {ck: (d[f"pop_{ck}"]["n"], round(d[f"pop_{ck}"]["mean"], 5),
                                             round(d[f"book_{ck}"]["cagr"], 4)) for ck in RT}, flush=True)
    with open(os.path.join(HERE, "result_etf.json"), "w") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("[etf] done", flush=True)


if __name__ == "__main__":
    main()
