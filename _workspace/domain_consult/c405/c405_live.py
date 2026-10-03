"""cycle405 §7 — 운영 donchian 체결(05-11 ~ 09-29)에 개조안 청산을 얹어 본다(방향만).
입력 = 스크래치 live_trades.json(trade_history 읽기 전용 조회 2026-10-03) + c405_panel.pkl."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import c405_sim as S

d, feats, sigs = S.load()
cal, panel = d["cal"], d["panel"]
th = json.load(open(S.SCR / "live_trades.json"))
rows = []
open_buys = {}
for r in th:
    ts = pd.Timestamp(r["timestamp"]).tz_localize("UTC").tz_convert("Asia/Seoul") if pd.Timestamp(r["timestamp"]).tzinfo is None else pd.Timestamp(r["timestamp"]).tz_convert("Asia/Seoul")
    r["kst"] = ts
    if r["trade_type"] == "BUY":
        open_buys.setdefault(r["ticker"], []).append(r)
    else:
        b = open_buys[r["ticker"]].pop(0)
        rows.append((b, r))
for t, lst in open_buys.items():
    for b in lst:
        rows.append((b, None))
out = []
for b, s in rows:
    t = b["ticker"]; p = panel.get(t); f = feats.get(t)
    bd = pd.Timestamp(b["kst"].date())
    E = float(b["price"]); q = int(float(b["quantity"]))
    act = (float(s["price"]) / E - 1 - 0.0035) if s else None
    rec = {"ticker": t, "buy": str(bd.date()), "E": E, "qty": q,
           "sell": str(s["kst"].date()) if s else None, "act_ret": act}
    if p is None:
        rec["kk"] = "no_bars"; out.append(rec); continue
    gd = int(cal.searchsorted(bd))
    k = int(np.searchsorted(p["di"], gd))
    if k >= len(p["di"]) or p["di"][k] != gd or k < 15:
        rec["kk"] = "no_bar_on_buy"; out.append(rec); continue
    N = float(f["atr"][k - 1])
    m = d["m_for_day"][gd]
    sig = S.Sig(t, k, gd, E * (p["o"][k] / p["o"][k]), E, N, float(f["prior_high"][k - 1]), float(m) if np.isfinite(m) else 1.0)
    # 진입가를 실제 체결가로: 수정 경로 위에서 E 를 그대로 쓴다(DB 가격 ≈ 원가)
    ps = S.run_trade_path(sig, "kk", True, p, f, S.KK, int(len(cal) - 1))
    rec.update({"m": sig.m, "R_pct": ps.Rw / E, "kk_exit": str(cal[ps.exit_gd].date()) if ps.exit_gd is not None else "open@09-30",
                "kk_reason": ps.exit_reason, "kk_ret": ps.exit_px / E - 1 - 0.0035})
    out.append(rec)
df = pd.DataFrame(out)
pd.set_option("display.width", 200)
print(df.to_string())
done = df[df.sell.notna() & df.kk_ret.notna()]
print("n", len(df), "closed", len(done))
print("actual mean %.2f%%  kk mean %.2f%%" % (done.act_ret.mean() * 100, done.kk_ret.mean() * 100))
print("m=0 buys", int((df.m == 0).sum()), "m dist", df.m.value_counts().to_dict())
print("by m", done.groupby("m")[["act_ret", "kk_ret"]].mean().round(4).to_dict())
print("kk still open at 09-30:", int((df.kk_reason == "END").sum()))
json.dump(out, open(Path(__file__).parent / "live_rescore.json", "w"), ensure_ascii=False, indent=1, default=str)
