"""사후(판정 밖) — 금 모형에 실물 대조 차(ACE KRX금현물 −0.70%/년)를 보수로 더했을 때 · 미국채10년에 KODEX 대조 차(−0.67%/년)."""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import riskoff_asset as R

out = {}
for tag, col, extra in (("E_gold_gap", "GOLD", 0.0070), ("C_ust10_gap", "UST10", 0.0067)):
    R.FEE[col] += extra
    m, _ = R.load()
    cv = R.cost_vec("high")
    ref = R.run_option(m, "A'", cv)
    row = {}
    for x in ("C", "E", "F"):
        r = R.run_option(m, x, cv)
        row[x] = {"J1": r["cagr_post"] - ref["cagr_post"], "J2": r["mdd_post"] - ref["mdd_post"],
                  "J3": {h: r["halves_post"][h]["cagr"] - ref["halves_post"][h]["cagr"] for h in r["halves_post"]}}
    out[tag] = row
    R.FEE[col] -= extra
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "posthoc.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
