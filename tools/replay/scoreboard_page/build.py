import json, sys
SRC = "/Users/koscom/Projects/auto_stock_score/_workspace/analysis/scoreboard_20261006/scoreboard.json"
d = json.load(open(SRC))

def r6(x):
    if x is None: return None
    if isinstance(x, bool): return x
    if isinstance(x, (int,)): return x
    return float(f"{x:.6g}")

KEEP = ["start","end","years","total_return","cagr","mdd","mdd_peak","mdd_trough","mdd_recovery",
        "longest_underwater_days","longest_underwater_ongoing","longest_underwater_from","vol","sharpe",
        "sortino","mar","pos_year_ratio","n_full_years","worst_12m","worst_12m_end","ulcer",
        "final_value_10m","n_months","k200_cagr_same_window","excess_vs_k200","corr_k200",
        "turnover_yr","cost_yr","after_tax_cagr"]
rows = []
for r in d["rows"]:
    m = r["metrics"]
    mm = {k: (r6(m[k]) if not isinstance(m[k], str) else m[k]) for k in KEEP if k in m}
    mm["best_year"] = {"year": m["best_year"]["year"], "ret": r6(m["best_year"]["ret"])} if m.get("best_year") else None
    mm["worst_year"] = {"year": m["worst_year"]["year"], "ret": r6(m["worst_year"]["ret"])} if m.get("worst_year") else None
    mm["yearly"] = {y: [r6(v["ret"]), 1 if v["full"] else 0, v["days"]] for y, v in m["yearly"].items()}
    e = r["extra"]; ex = {}
    for k in ["start_equity","rep_seed","n_seeds","seed_cagr_median","seed_cagr_min","seed_cagr_max",
              "seed_mdd_median","fills_per_year","orders_per_year","avg_stock_share","cost_yr","window"]:
        if k in e: ex[k] = r6(e[k]) if not isinstance(e[k], (str, list)) else e[k]
    c = r["curves"]
    rows.append({
        "id": r["id"], "name": r["name"], "desc": r["desc"], "group": r["group"], "status": r["status"],
        "status_ref": r["status_ref"], "tax_note": r["tax_note"], "source": r["source"], "note": r["note"],
        "extra": ex, "metrics": mm,
        "curves": {"m": [s[:7] for s in c["month_end"]],
                    "c": [r6(float(f"{v:.5g}")) for v in c["cum"]],
                    "d": [round(v, 4) for v in c["dd_min"]]},
    })
out = {"generated_kst": d["generated_kst"], "rules": d["rules"],
       "reconcile": {"n": len(d["reconcile"]), "match": sum(1 for x in d["reconcile"] if x["match"])},
       "rows": rows}
s = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
tpl = open(sys.argv[1]).read()
html = tpl.replace("/*__DATA__*/null", s)
open(sys.argv[2], "w").write(html)
print(len(html), out["reconcile"])
