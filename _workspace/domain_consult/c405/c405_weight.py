"""cycle405 §12 — donchian 비중별 랏 모양 · W4 소매(보고판 전용, 사전 등록 판정과 무관).
예산 = 4,955,600 × 0.95 × w. c405_sim.py 를 그대로 쓰고 시작 자산만 바꾼다."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import c405_sim as S

NET, CASH = 4_955_600, 0.95
W = [0.1579, 0.20, 0.25, 0.30, 0.35]
d, feats, sigs = S.load()
cal, panel = d["cal"], d["panel"]
sbg = S.group(sigs)
g0 = int(cal.searchsorted(pd.Timestamp(S.W4[0])))
geo_sigs = [s for s in sigs if s.gd >= g0]
out = {}
for w in W:
    B = int(NET * CASH * w)
    S.START_EQUITY = B
    geo = S.lot_geometry(geo_sigs, B=B)
    kk, Rk, _ = S.book_stats("kk", sbg, panel, feats, cal, S.W4)
    cur, Rc, _ = S.book_stats("cur", sbg, panel, feats, cal, S.W4)
    out[str(w)] = {"budget": B, "cap_price": int(B * 0.15), "geo_kk": geo["kk"], "geo_cur": geo["cur"], "n": geo["n"],
                   "kk": {k: kk[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median", "trades_median", "one_share_lot_share", "lot_median", "recon_max_abs")},
                   "cur": {k: cur[k] for k in ("cagr_median", "mdd_median")},
                   "kk_daily_ret_mean_ann": float(Rk.mean() * 252 * 100)}
    print(w, json.dumps(out[str(w)], ensure_ascii=False), flush=True)
json.dump(out, open(Path(__file__).parent / "weight_results.json", "w"), ensure_ascii=False, indent=1)
