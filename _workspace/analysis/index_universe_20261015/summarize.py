"""prereg §2·§3 판정을 결과 json 에서 그대로 계산 → summary.json + 표 출력."""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
L = lambda f: json.load(open(os.path.join(HERE, f)))
out = {}


def seeds(a, b):
    return int(sum(x > y for x, y in zip(a, b)))


# ① donchian
D = L("result_donchian.json")
rows = {}
for w in "TVH":
    c, i, e = (D[k][w]["book_s0.0"] for k in ("U0|mkt", "U0|idx", "U0|etf"))
    rows[w] = {"comp": [c["cagr"], c["mdd"], c["fills_y"]], "idx": [i["cagr"], i["mdd"], i["fills_y"]],
               "etf": [e["cagr"], e["mdd"], e["fills_y"]], "d_idx": i["cagr"] - c["cagr"],
               "d_mdd_idx": i["mdd"] - c["mdd"], "seeds_idx_gt_comp": seeds(i["per_seed"], c["per_seed"]),
               "seeds_etf_gt_comp": seeds(e["per_seed"], c["per_seed"]),
               "pop": {k: [D[k][w]["pop_s0.0"]["n"], D[k][w]["pop_s0.0"]["mean"], D[k][w]["pop_s0.0"]["lo90"]]
                       for k in ("U0|mkt", "U0|idx", "U0|etf")},
               "pop_kq": {k: [D[k][w]["pop_kq"]["n"], D[k][w]["pop_kq"]["mean"]] for k in ("U0|mkt", "U0|idx", "U0|etf")},
               "m_sig": {k: D[k][w]["m_of_signals"] for k in ("U0|mkt", "U0|idx", "U0|etf")}}
E1 = rows["T"]["d_idx"] > 0 and rows["V"]["d_idx"] > 0 and rows["V"]["seeds_idx_gt_comp"] >= 10
E2 = rows["T"]["d_mdd_idx"] >= -0.05 and rows["V"]["d_mdd_idx"] >= -0.05
Hrev = np.sign(rows["V"]["d_idx"]) != np.sign(rows["H"]["d_idx"])
if E1 and E2 and not Hrev:
    lab = "idx 전환 지지(성과)"
elif rows["T"]["d_idx"] < 0 and rows["V"]["d_idx"] < 0 and rows["V"]["seeds_idx_gt_comp"] <= 6:
    lab = "comp 유지(성과)"
else:
    lab = "성과 차이 없음 — 일관성·운영 단순성으로 정한다"
out["donchian"] = {"rows": rows, "E1": E1, "E2": E2, "H_reversed": bool(Hrev), "label": lab}

# ② BFB · VCP · kojiro
for k, f in (("bfb", "result_bfb.json"), ("vcp", "result_vcp.json"), ("kojiro", "result_kojiro.json")):
    R = L(f)
    rs = {}
    for w in "TVH":
        A, B, Bi, Ae = (R[v][w] for v in ("A|comp", "B|comp", "B|idx", "A|etf"))
        a, b = A["book_s0.0"], B["book_s0.0"]
        rs[w] = {"A": [a["cagr"], a["mdd"], a["fills_y"], a["slot_full_share"], a["out_fill_share"]],
                 "B": [b["cagr"], b["mdd"], b["fills_y"], b["slot_full_share"]],
                 "B_idx": [Bi["book_s0.0"]["cagr"], Bi["book_s0.0"]["mdd"], Bi["book_s0.0"]["fills_y"]],
                 "A_etf": [Ae["book_s0.0"]["cagr"], Ae["book_s0.0"]["mdd"]],
                 "A_s0.005": [A["book_s0.005"]["cagr"], A["book_s0.005"]["mdd"]],
                 "A_s0.01": [A["book_s0.01"]["cagr"], A["book_s0.01"]["mdd"]],
                 "d": b["cagr"] - a["cagr"], "d_s0.005": b["cagr"] - A["book_s0.005"]["cagr"],
                 "d_s0.01": b["cagr"] - A["book_s0.01"]["cagr"], "d_mdd": b["mdd"] - a["mdd"],
                 "seeds_B_gt_A": seeds(b["per_seed"], a["per_seed"]),
                 "seeds_Bidx_gt_B": seeds(Bi["book_s0.0"]["per_seed"], b["per_seed"]),
                 "pop_A": [A["pop"]["n"], A["pop"]["mean"], A["pop"].get("lo90")],
                 "pop_A_in": [A["pop_in"]["n"], A["pop_in"].get("mean")],
                 "pop_A_out": [A["pop_out"]["n"], A["pop_out"].get("mean")],
                 "pop_B": [B["pop"]["n"], B["pop"]["mean"], B["pop"].get("lo90")],
                 "pop_A_kq": [A["pop_kq"]["n"], A["pop_kq"].get("mean")],
                 "sig_per_day": [A["sig_per_day"], B["sig_per_day"]]}
    D1 = rs["T"]["d"] > 0 and rs["V"]["d"] > 0 and rs["V"]["seeds_B_gt_A"] >= 10
    D2 = rs["T"]["d_mdd"] >= -0.05 and rs["V"]["d_mdd"] >= -0.05
    D3 = rs["V"]["B"][2] >= 12
    Hrev = np.sign(rs["V"]["d"]) != np.sign(rs["H"]["d"])
    if D1 and D2 and D3 and not Hrev:
        lab = "좁힘 지지"
    elif rs["T"]["d"] < 0 and rs["V"]["d"] < 0:
        lab = "현행 유지"
    else:
        lab = "혼재 — 현행 유지(변경 근거 부족)"
    abs_note = "덜 나쁨(절대 수준 음)" if rs["V"]["B"][0] <= 0 else ""
    out[k] = {"rows": rs, "cand_per_day": R["cand_per_day"], "D1": D1, "D2": D2, "D3": D3, "H_reversed": bool(Hrev),
              "label": lab, "abs_note": abs_note}

json.dump(out, open(os.path.join(HERE, "summary.json"), "w"), ensure_ascii=False, indent=1,
          default=lambda o: o.item() if hasattr(o, "item") else str(o))
f = lambda x: f"{x*100:+.2f}" if isinstance(x, float) else str(x)
print("donchian", out["donchian"]["label"], out["donchian"]["E1"], out["donchian"]["E2"], out["donchian"]["H_reversed"])
for w, r in out["donchian"]["rows"].items():
    print(" ", w, "comp", [f(x) for x in r["comp"][:2]], "idx", [f(x) for x in r["idx"][:2]], "etf", [f(x) for x in r["etf"][:2]],
          "d", f(r["d_idx"]), "seeds", r["seeds_idx_gt_comp"], r["seeds_etf_gt_comp"])
for k in ("bfb", "vcp", "kojiro"):
    o = out[k]
    print(k, o["label"], o["abs_note"], "D1", o["D1"], "D2", o["D2"], "D3", o["D3"], "Hrev", o["H_reversed"])
    for w, r in o["rows"].items():
        print(" ", w, "A", [f(x) for x in r["A"][:2]], round(r["A"][2], 1), "B", [f(x) for x in r["B"][:2]], round(r["B"][2], 1),
              "d", f(r["d"]), "d.5", f(r["d_s0.005"]), "d1", f(r["d_s0.01"]), "seeds", r["seeds_B_gt_A"],
              "Bidx", [f(x) for x in r["B_idx"][:2]], "BidxSeeds", r["seeds_Bidx_gt_B"],
              "| pop A", r["pop_A"][0], f(r["pop_A"][1]), "in", f(r["pop_A_in"][1]), "out", r["pop_A_out"][0], f(r["pop_A_out"][1]),
              "B", r["pop_B"][0], f(r["pop_B"][1]), f(r["pop_B"][2]), "slotA", round(r["A"][3], 2), "slotB", round(r["B"][3], 2),
              "outfillA", round(r["A"][4], 2), "sig/d", [round(x, 2) for x in r["sig_per_day"]])
