"""prereg §4 재현 관문 · §6 판정을 결과 json 에서 그대로 계산 → summary.json + 표 출력."""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OLDD = os.path.join(HERE, "..", "index_universe_20261015")
L = lambda d, f: json.load(open(os.path.join(d, f)))
STK = {"kojiro": ("result_kojiro.json", "A|comp", "pop", "book_s0.0"),
       "donchian": ("result_donchian.json", "U0|mkt", "pop_s0.0", "book_s0.0"),
       "bfb": ("result_bfb.json", "A|comp", "pop", "book_s0.0"),
       "vcp": ("result_vcp.json", "A|comp", "pop", "book_s0.0")}
out = {"repro": {}, "strat": {}}


def seeds(a, b):
    return int(sum(x > y for x, y in zip(a, b)))


R = {k: L(HERE, f) for k, (f, *_) in STK.items()}
R["etf"] = L(HERE, "result_etf.json")

# §4 재현
for k, (f, vk, pk, bk) in STK.items():
    o = L(OLDD, f)[vk]
    rr = {}
    for w in "TVH":
        a, b = o[w][pk], R[k]["on"][w]["pop_ERA"]
        x, y = o[w][bk], R[k]["on"][w]["book_ERA"]
        rr[w] = {"n_eq": a["n"] == b["n"], "mean_absdiff": abs(a["mean"] - b["mean"]),
                 "cagr_absdiff": abs(x["cagr"] - y["cagr"]), "mdd_absdiff": abs(x["mdd"] - y["mdd"])}
    ok = all(v["n_eq"] and v["mean_absdiff"] < 1e-9 and v["cagr_absdiff"] < 1e-6 and v["mdd_absdiff"] < 1e-6
             for v in rr.values())
    out["repro"][k] = {"ok": ok, "rows": rr}

# 표 재료
for k in list(STK) + ["etf"]:
    s = {}
    for w in "TVH":
        on, off = R[k]["on"][w], R[k]["off"][w]
        s[w] = {f"{mu}|{ck}": {"n": d[f"pop_{ck}"]["n"], "mean": d[f"pop_{ck}"]["mean"], "lo90": d[f"pop_{ck}"]["lo90"],
                                "cagr": d[f"book_{ck}"]["cagr"], "mdd": d[f"book_{ck}"]["mdd"],
                                "fills_y": d[f"book_{ck}"]["fills_y"]}
                for mu, d in (("on", on), ("off", off)) for ck in ("NEW", "OLD")}
        s[w]["m0_share_sig_on"] = on.get("m0_share_sig")
        if k != "etf":
            s[w]["seeds_on_gt_off_NEW"] = seeds(on["book_NEW"]["per_seed"], off["book_NEW"]["per_seed"])
        if k == "kojiro":
            s[w]["book_budget"] = {b: {x: on[f"book_NEW_{b}"][x] for x in ("cagr", "mdd", "fills_y")}
                                   for b in ("w030", "w025")}
    out["strat"][k] = s

# Q2 부호 바뀜
q2 = {}
for k, s in out["strat"].items():
    q2[k] = {w: bool(np.sign(s[w]["on|OLD"]["mean"]) != np.sign(s[w]["on|NEW"]["mean"])) for w in "TVH"}
lv = L(HERE, "live_pnl.json")
q2["live_d90"] = {k: bool(np.sign(v["net_actual"]) != np.sign(v["new"])) for k, v in lv.items()
                  if k.endswith("|d90") and v["n"]}
out["Q2"] = q2

# 시장 유닛 효과(NEW)
mu = {}
for k, s in out["strat"].items():
    d1 = {w: s[w]["on|NEW"]["mean"] - s[w]["off|NEW"]["mean"] for w in "TVH"}
    d2 = {w: s[w]["on|NEW"]["cagr"] - s[w]["off|NEW"]["cagr"] for w in "TVH"}
    d3 = {w: s[w]["on|NEW"]["mdd"] - s[w]["off|NEW"]["mdd"] for w in "TVH"}
    MU1 = d1["T"] > 0 and d1["V"] > 0
    sv = s["V"].get("seeds_on_gt_off_NEW")
    MU2 = d2["T"] > 0 and d2["V"] > 0 and (sv is None or sv >= 10)
    MU3 = d3["T"] >= -0.05 and d3["V"] >= -0.05
    if MU1 and MU2 and MU3:
        lab = "시장 유닛이 성과를 올린다"
    elif d1["T"] < 0 and d1["V"] < 0 and d2["T"] < 0 and d2["V"] < 0:
        lab = "시장 유닛이 성과를 깎는다"
    else:
        lab = "혼재"
    if np.sign(d2["V"]) != np.sign(d2["H"]):
        lab += " (H 반전)"
    mu[k] = {"d_mean": d1, "d_cagr": d2, "d_mdd": d3, "MU1": MU1, "MU2": MU2, "MU3": MU3, "seeds_V": sv, "label": lab}
out["MU"] = mu

# Q3 kojiro 비중
S4 = ("kojiro", "donchian", "bfb", "vcp")
E = {k: {w: out["strat"][k][w]["on|NEW"]["mean"] for w in "TVH"} for k in S4}
med = {w: float(np.median([E[k][w] for k in S4])) for w in "TV"}
W1 = E["kojiro"]["T"] < med["T"] and E["kojiro"]["V"] < med["V"]
W2 = E["kojiro"]["T"] < 0 and E["kojiro"]["V"] < 0
Rset = [k for k in S4 if k != "kojiro" and E[k]["T"] > 0 and E[k]["V"] > 0
        and out["strat"][k]["V"]["on|NEW"]["lo90"] > -0.002]
if W1 and W2 and Rset:
    best = max(Rset, key=lambda k: E[k]["V"])
    lab = f"0.25 로 줄이고 0.05 를 {best} 에"
elif W1 and not Rset:
    lab = "0.25 — 덜 나쁜 쪽으로 Σ 정규화 재배분. 기대값을 양으로 만들지는 못한다"
elif W2:
    lab = "0.30 유지 — 다 같이 음이고 kojiro 가 상대적으로 낫지 않지도 않다. 배분 변경 근거 없음"
else:
    lab = "0.30 유지"
if np.sign(E["kojiro"]["V"]) != np.sign(E["kojiro"]["H"]):
    lab += " (H 반전 — 확신 낮음)"
conf = {}
for k in list(S4) + ["etf"]:
    v = out["strat"][k]["V"]["on|NEW"]
    conf[k] = "높음" if v["lo90"] > 0 else ("중간" if v["mean"] > 0 else "음의 기대값 확인")
out["Q3"] = {"E": E, "median": med, "W1": W1, "W2": W2, "R": Rset, "label": lab, "confidence": conf}

json.dump(out, open(os.path.join(HERE, "summary.json"), "w"), ensure_ascii=False, indent=1,
          default=lambda o: o.item() if hasattr(o, "item") else str(o))
pc = lambda x: f"{x*100:+.2f}"
print("repro", {k: v["ok"] for k, v in out["repro"].items()})
for k, s in out["strat"].items():
    print(f"== {k}")
    for w in "TVH":
        r = s[w]
        print(" ", w, " | ".join(f"{c}: n{r[c]['n']} {pc(r[c]['mean'])} lo{pc(r[c]['lo90'])} cagr{pc(r[c]['cagr'])} "
                                 f"mdd{pc(r[c]['mdd'])} f{r[c]['fills_y']:.0f}" for c in ("on|NEW", "off|NEW", "on|OLD")),
              "m0", None if r["m0_share_sig_on"] is None else round(r["m0_share_sig_on"], 3), "seeds", r.get("seeds_on_gt_off_NEW"))
    if k == "kojiro":
        print("  budget", {w: s[w]["book_budget"] for w in "TVH"})
print("Q2", out["Q2"])
for k, v in out["MU"].items():
    print("MU", k, v["label"], {a: {w: round(b[w] * 100, 2) for w in "TVH"} for a, b in (("dm", v["d_mean"]), ("dc", v["d_cagr"]), ("dd", v["d_mdd"]))}, v["seeds_V"])
print("Q3", out["Q3"]["label"], out["Q3"]["W1"], out["Q3"]["W2"], out["Q3"]["R"], out["Q3"]["median"], out["Q3"]["confidence"])
