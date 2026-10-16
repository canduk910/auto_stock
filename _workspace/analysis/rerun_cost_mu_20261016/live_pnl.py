"""운영 왕복(/api/history/pnl, 10-16 15:09 KST 수집) — 5전략 세전·실비용 후·NEW/OLD 재가격 (prereg §5 보조)."""
import json, sys
import numpy as np
rows = json.load(open(sys.argv[1]))
NEW = {"etf_trend": 0.028}; OLD = {"etf_trend": 0.284}
out = {}
for sid in ("kojiro", "donchian_swing", "bull_flag_breakout", "vcp_breakout", "etf_trend"):
    for wn, d0 in (("d90", "2026-07-18"), ("all", "0000")):
        r = [x for x in rows if x["strategy"] == sid and x["status"] == "closed" and x["sell_date"] >= d0]
        if not r:
            out[f"{sid}|{wn}"] = {"n": 0}; continue
        g = np.array([x["profit_rate"] for x in r], float)
        nt = np.array([x["net_profit_rate"] if x.get("net_profit_rate") is not None else np.nan for x in r], float)
        bp = np.array([x["cost_bp"] if x.get("cost_bp") is not None else np.nan for x in r], float)
        nw = g - NEW.get(sid, 0.228); od = g - OLD.get(sid, 0.484)
        win = nw > 0
        out[f"{sid}|{wn}"] = {"n": len(r), "gross": float(g.mean()), "net_actual": float(np.nanmean(nt)),
                              "cost_bp_mean": float(np.nanmean(bp)), "new": float(nw.mean()), "old": float(od.mean()),
                              "win_new": float(win.mean()), "avg_win_new": float(nw[win].mean()) if win.any() else None,
                              "avg_loss_new": float(nw[~win].mean()) if (~win).any() else None,
                              "first_sell": min(x["sell_date"] for x in r), "last_sell": max(x["sell_date"] for x in r)}
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
for k, v in out.items():
    print(k, {a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()})
