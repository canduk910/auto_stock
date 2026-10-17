"""진단(사후, 판정 무관): 추가 종목이 왜 나쁜가 + 최근 후보 겹침."""
import json, os, pickle, sys
from collections import Counter
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/Users/koscom/Projects/auto_stock/tools")
from replay.strategies import donchian_kk as DK  # noqa
from replay.strategies import donchian_kk_audit as DA  # noqa
from replay.strategies import donchian_y30 as Y  # noqa

st, M, info = pickle.load(open(os.path.join(HERE, "store_full.pkl"), "rb"))
cal = st.cal; bars = st.bars; Y._CAL["cal"] = cal
kk = Y.kk_of(Y.EXIT0)
feats = {}
for t, b in bars.items():
    bb = dict(b); bb["mem"] = b["common"]
    feats[t] = Y.features_y30(bb, tv_mode="pct")
out = {}
# 1) 진입 거름(갭·추격) 통과율 · R 크기 · 첫 5봉 손절 — V+H(2013~2026) · 신호봉 기준 지수 안/밖
g0 = int(cal.searchsorted(pd.Timestamp("2013-01-02")))
stat = {True: Counter(), False: Counter()}
rpct = {True: [], False: []}
nxt = {True: [], False: []}  # 신호봉 다음 날 시가/신호봉 종가 −1
d5 = {True: [], False: []}   # 진입 후 5봉 종가 수익(시가 진입)
for t, b in bars.items():
    f = feats[t]; c = f["cond"] & b["common"]
    for j in np.nonzero(c[:-1])[0]:
        if b["di"][j] < g0:
            continue
        mem = bool(b["mem"][j]); D = j + 1
        stat[mem]["cand"] += 1
        if b["di"][D] != b["di"][j] + 1 or b["notrade"][D] or b["o"][D] <= 0:
            stat[mem]["nobar"] += 1; continue
        O = b["o"][D]
        nxt[mem].append(O / b["c"][j] - 1)
        if O >= b["c"][j] * 1.03:
            stat[mem]["gap_skip"] += 1; continue
        if O > f["prior_high"][j] * 1.04:
            stat[mem]["ext_skip"] += 1; continue
        R = max(0.08 * O, 1.5 * f["atr"][j])
        if R >= 0.5 * O:
            stat[mem]["r_half"] += 1; continue
        stat[mem]["enter"] += 1
        rpct[mem].append(R / O)
        if D + 5 < len(b["c"]):
            d5[mem].append(b["c"][D + 5] / O - 1)
for mem in (True, False):
    r = np.array(rpct[mem]); x = np.array(nxt[mem]); y = np.array(d5[mem])
    out["index" if mem else "added"] = {
        **dict(stat[mem]),
        "R_pct_median": float(np.median(r)), "R_atr_driven_share": float(np.mean(r > 0.0801)),
        "next_open_gap_median": float(np.median(x)), "next_open_gap_le0_share": float(np.mean(x <= 0)),
        "ret5_median": float(np.median(y)), "ret5_mean": float(np.mean(y)), "ret5_le_m8_share": float(np.mean(y <= -0.08))}
# 2) 최근 후보(신호봉 cond) — 진입일 = 다음 거래일. 2026-09-15 ~ 10-02
rec = {"U0": {}, "U1": {}}
gs = int(cal.searchsorted(pd.Timestamp("2026-09-01")))
for t, b in bars.items():
    f = feats[t]
    for j in np.nonzero(f["cond"] & b["common"])[0]:
        if b["di"][j] < gs:
            continue
        nd = int(b["di"][j]) + 1
        ed = str(cal[nd].date()) if nd < len(cal) else "next"
        rec["U1"].setdefault(ed, []).append(t)
        if b["mem"][j]:
            rec["U0"].setdefault(ed, []).append(t)
out["recent_candidates"] = rec
json.dump(out, open(os.path.join(HERE, "diag.json"), "w"), ensure_ascii=False, indent=1, default=float)
print(json.dumps({k: v for k, v in out.items() if k != "recent_candidates"}, ensure_ascii=False, indent=1, default=float))
