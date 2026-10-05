#!/usr/bin/env python3
"""volatility_breakout(S5) 판정 실행 — 동결본 §3.5 순서: P6 → P1·P2(두 판) → P3·P4(두 판) → 보고판.

입력 = 주식 보관소(sha 대조) + DB 추출본(``audit_db_extract.jsonl.gz``, sha 기록) + 실거래 왕복 표(``live_trips.json``).
출력 = 스크래치 ``audit/vb/vb_result.json``(종목별 거래 원장 포함 — 리포 밖) + 표준출력 요약(집계값만).

실행: ``python3 tools/replay/strategies/vb_run.py``
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")    # 전략 모듈 import 용(값은 쓰이지 않는다 — 단계 1 R3)

from replay.audit import book as BK  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.audit import market_unit as MU  # noqa: E402
from replay.audit import panel as PN  # noqa: E402
from replay.audit.sizing import OpSizer  # noqa: E402
from replay.strategies import vb as VB  # noqa: E402

OUT_DIR = os.path.join(C.SCRATCH, "vb")
LIVE_RULES_START = "2026-09-14"     # D-8 rules 판(사용자 결정 10-05)
LIVE_STRICT_START = "2026-09-28"


def gd_of(cal, d: str, side="left") -> int:
    return int(cal.searchsorted(pd.Timestamp(d), side=side)) - (1 if side == "right" else 0)


def load_all():
    PN.check_archive(C.STOCK_ARCHIVE, C.STOCK_PARQUET_SHA)
    PN.check_archive(C.ETF_ARCHIVE, C.ETF_PARQUET_SHA)
    arch = PN.load_archive(C.STOCK_ARCHIVE, end=C.W5Y[1])
    ext = PN.load_db_extract()
    db = PN.db_daily_frame(ext, C.H1Y[0], C.H1Y[1])
    st = PN.build_store(arch, db=db, nontrade="flag", junction_rescale=True)
    return arch, ext, db, st


def mcap_fn_factory(st, ext):
    """보관소 = 그날 시총(전일 봉). DB 구간 = 단계 1 R2 근사: 현재 시총 × (전일 종가 ÷ 최신 종가)."""
    mcols, mrows = ext["master"]
    mi = {c: i for i, c in enumerate(mcols)}
    now_cap = {r[mi["ticker"]]: (float(r[mi["hts_avls_eok"]]) * 1e8 if r[mi["hts_avls_eok"]] else np.nan)
               for r in mrows}
    last_c = {}
    for t, b in st.bars.items():
        msk = b["src"] == 1
        if msk.any():
            last_c[t] = float(b["c_raw"][msk][-1])

    def f(t, b, i):
        j = i - 1
        if b["src"][j] == 0:
            return float(b["mktcap"][j])
        nc, lc = now_cap.get(t, np.nan), last_c.get(t, np.nan)
        if not (np.isfinite(nc) and np.isfinite(lc) and lc > 0):
            return np.nan
        return nc * float(b["c_raw"][j]) / lc
    return f


def m_series(st, ext):
    etf = PN.load_archive(C.ETF_ARCHIVE, columns=["ticker", "bas_dd", "close"])
    e = etf[etf.ticker == MU.SOURCE_TICKER].sort_values("bas_dd")
    dcols, drows = ext["daily"]
    ix = {c: i for i, c in enumerate(dcols)}
    extra = sorted((r[ix["bas_dd"]][:10], r[ix["close_price"]]) for r in drows if r[ix["ticker"]] == MU.SOURCE_TICKER)
    dates = list(e.bas_dd)
    closes = list(e.close.astype(float))
    last = dates[-1]
    for d, cpx in extra:
        if pd.Timestamp(d) > last:
            dates.append(pd.Timestamp(d))
            closes.append(float(cpx))
    return MU.m_for_days(st.cal, pd.DatetimeIndex(dates), np.array(closes))


def pop_stats(pop, cost_rt, cal):
    r = np.array([VB.net_ret(s.E, px, cost_rt) for s, px, _ in pop])
    tk = [s.ticker for s, *_ in pop]
    dd = [cal[s.gd].date() for s, *_ in pop]
    p1 = J.p1(r, tk, dd)
    why = Counter(w for *_x, w in pop)
    srt = np.sort(r)
    k1 = max(1, int(round(len(r) * 0.01)))
    return {"p1": p1, "n": len(r), "mean": float(r.mean()) if len(r) else float("nan"),
            "median": float(np.median(r)) if len(r) else float("nan"),
            "win": float((r > 0).mean()) if len(r) else float("nan"),
            "stop_share": why.get("STOP_LOSS", 0) / max(1, len(r)),
            "mean_ex_top1pct": float(srt[:-k1].mean()) if len(r) > k1 else float("nan"),
            "_r": r}


def main():
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    arch, ext, db, st = load_all()
    cal = st.cal
    out = {"extract_sha256": PN.sha256(C.DB_EXTRACT), "store": st.meta, "params": VB.VB_OP}
    print("[vb] store", st.meta, f"{time.time()-t0:.0f}s", flush=True)

    mcap_fn = mcap_fn_factory(st, ext)
    mday = m_series(st, ext)
    cands = VB.day_candidates(st.bars, mcap_fn)
    sigs = VB.signals_from_candidates(cands, st.bars, mday)
    ncand = np.array([len(cands.get(g, [])) for g in range(len(cal))])
    w5 = (gd_of(cal, C.W5Y[0]), gd_of(cal, C.W5Y[1], "right"))
    w4 = (gd_of(cal, C.W4[0]), gd_of(cal, C.W4[1], "right"))
    hh = (gd_of(cal, C.H1Y[0]), gd_of(cal, C.H1Y[1], "right"))
    out["universe"] = {
        "cand_per_day_W5y": {"median": float(np.median(ncand[w5[0]:w5[1] + 1])),
                             "max": int(ncand[w5[0]:w5[1] + 1].max()),
                             "days_over_100": int((ncand[w5[0]:w5[1] + 1] > 100).sum())},
        "cand_per_day_H": {"median": float(np.median(ncand[hh[0]:hh[1] + 1])),
                           "max": int(ncand[hh[0]:hh[1] + 1].max()),
                           "days_over_100": int((ncand[hh[0]:hh[1] + 1] > 100).sum())},
        "signals_W5y": sum(1 for s in sigs if w5[0] <= s.gd <= w5[1]),
        "signals_H": sum(1 for s in sigs if hh[0] <= s.gd <= hh[1]),
    }
    sig_days = {s.gd for s in sigs if w5[0] <= s.gd <= w5[1]}
    out["universe"]["signal_days_W5y"] = len(sig_days)
    out["universe"]["trading_days_W5y"] = w5[1] - w5[0] + 1
    out["universe"]["trading_days_H"] = hh[1] - hh[0] + 1
    ks = [s.k for s in sigs if w5[0] <= s.gd <= w5[1]]
    out["universe"]["k_signal_median_W5y"] = float(np.median(ks))
    print("[vb] universe", out["universe"], flush=True)

    # ── P6 관문: 실거래 매수(rules 판 09-14~) ↔ 재현 신호(같은 날 같은 종목) ──
    live = json.load(open(os.path.join(C.SCRATCH, "live_trips.json")))
    vb_trips = [t for t in live["trips"] if t["strategy"] == "volatility_breakout"]
    live_buys = []
    for t in vb_trips:
        for (d, q, px) in t["buy_orders"]:
            live_buys.append((t["ticker"], d, px))
    rs = {(s.ticker, str(cal[s.gd].date())): s for s in sigs}
    rc = {}
    for g, lst in cands.items():
        for (t, i, k, off) in lst:
            rc[(t, str(cal[g].date()))] = (i, k, off)
    p6_rows = []
    for (t, d, px) in live_buys:
        if d < LIVE_RULES_START:
            continue
        row = {"ticker": t, "date": d, "live_px": px}
        if (t, d) in rs:
            s = rs[(t, d)]
            row.update(status="hit", replay_target_raw=s.E_raw, live_over_target=px / s.E_raw - 1)
        elif (t, d) in rc:
            i, k, off = rc[(t, d)]
            b = st.bars[t]
            tgt = (b["o"][i] + off) * b["raw"][i]
            row.update(status="cand_no_daily_touch", replay_target_raw=tgt, high_raw=b["h"][i] * b["raw"][i],
                       live_over_target=px / tgt - 1)
        else:
            b = st.bars.get(t)
            why = "no_bar"
            if b is not None:
                gd = gd_of(cal, d)
                idx = np.searchsorted(b["di"], gd)
                if idx < len(b["di"]) and b["di"][idx] == gd:
                    i = int(idx)
                    why = []
                    if b["tv"][i - 1] < VB.VB_OP["min_tv"]:
                        why.append(f"prev_tv={b['tv'][i-1]/1e8:.0f}억")
                    mc = mcap_fn(t, b, i)
                    if not (np.isfinite(mc) and mc >= VB.VB_OP["min_mcap"]):
                        why.append(f"prev_mcap={mc/1e8 if np.isfinite(mc) else float('nan'):.0f}억")
                    pc = b["c_raw"][i - 1]
                    if not (VB.VB_OP["price_min"] <= pc <= VB.VB_OP["price_max"]):
                        why.append(f"prev_close={pc:.0f}")
                    why = ",".join(why) or "other"
            row.update(status="not_candidate", why=why)
        p6_rows.append(row)
    p6 = J.p6([(r["ticker"], r["date"]) for r in p6_rows],
              {k for k in rs})
    p6_strict = J.p6([(r["ticker"], r["date"]) for r in p6_rows if r["date"] >= LIVE_STRICT_START], set(rs))
    # 반대 방향(보고): 그 창에서 재현이 낸 신호 중 실거래가 산 비율
    win_sigs = [s for s in sigs if str(cal[s.gd].date()) >= LIVE_RULES_START and s.gd <= hh[1]]
    bought = {(r["ticker"], r["date"]) for r in p6_rows}
    out["p6"] = {"rules": p6, "strict_0928": p6_strict, "status_counts": Counter(r["status"] for r in p6_rows),
                 "replay_signals_in_window": len(win_sigs),
                 "replay_signals_bought_live": sum(1 for s in win_sigs if (s.ticker, str(cal[s.gd].date())) in bought),
                 "replay_signal_days_in_window": len({s.gd for s in win_sigs}),
                 "hit_live_over_target_median": float(np.median([r["live_over_target"] for r in p6_rows
                                                                  if r["status"] == "hit"]))
                 if any(r["status"] == "hit" for r in p6_rows) else None,
                 "_rows": p6_rows}
    print("[vb] P6", {k: v for k, v in out["p6"].items() if not k.startswith("_")}, flush=True)

    # ── P1 · P2 (두 판) ──
    pops = {}
    for v in VB.VERSIONS:
        pw = VB.population(sigs, v, w5[0], w5[1])
        ph = VB.population(sigs, v, hh[0], hh[1])
        a = pop_stats(pw, C.COST_RT_JUDGE, cal)
        h = pop_stats(ph, C.COST_RT_JUDGE, cal)
        sens = {f"{c:.4f}": float(np.mean([VB.net_ret(s.E, px, c) for s, px, _ in pw])) for c in C.COST_RT_SENS}
        p2 = J.p2(h["_r"], a["mean"])
        pops[v] = {"W5y": a, "H": h, "sens": sens, "p2": p2, "_pw": pw, "_ph": ph}
        out[f"P1_{v}"] = {**a["p1"], "median": a["median"], "win": a["win"], "stop_share": a["stop_share"],
                          "mean_ex_top1pct": a["mean_ex_top1pct"], "cost_sens_mean": sens}
        out[f"P2_{v}"] = {**p2, "H_n": h["n"], "H_p1": h["p1"], "H_win": h["win"], "H_stop_share": h["stop_share"]}
        print(f"[vb] P1 {v}", out[f"P1_{v}"], flush=True)
        print(f"[vb] P2 {v}", out[f"P2_{v}"], flush=True)

    # 보정 대조(보고): P6 에서 맞은 실거래 매수의 실제 왕복 총수익 ↔ 같은 거래의 재현 청산(실거래 매수가 기준)
    tmap = {(t["ticker"], t["buy_date"]): t for t in vb_trips}
    cal_rows = []
    for row in p6_rows:
        k = (row["ticker"], row["date"])
        if row["status"] != "hit" or k not in tmap:
            continue
        e = {}
        for v in VB.VERSIONS:
            hitp = [(s, px, w) for s, px, w in pops[v]["_ph"] if (s.ticker, str(cal[s.gd].date())) == k]
            if hitp:
                s, px, w = hitp[0]
                e[v] = (px * s.E_raw / s.E) / tmap[k]["buy_px"] - 1
        if len(e) == 2:
            cal_rows.append((tmap[k]["gross"], e["opt"], e["pes"]))
    if cal_rows:
        a = np.array(cal_rows)
        out["calibration_matched_live"] = {"n": len(a), "live_gross_mean": float(a[:, 0].mean()),
                                           "opt_gross_mean": float(a[:, 1].mean()),
                                           "pes_gross_mean": float(a[:, 2].mean()),
                                           "opt_abs_diff_le_0p5pp": int((abs(a[:, 1] - a[:, 0]) <= 0.005).sum()),
                                           "pes_abs_diff_le_0p5pp": int((abs(a[:, 2] - a[:, 0]) <= 0.005).sum())}
        print("[vb] calibration", out["calibration_matched_live"], flush=True)

    # D-6 잠정 종가: H 거래 중 진입일(=청산일) 종가 · 전일 봉이 잠정 표시인 것을 뺀 판
    dcols, drows = ext["daily"]
    prov = VB.provisional_flags(dcols, drows)
    out["D6"] = {"flag_rows": len(prov)}
    for v in VB.VERSIONS:
        ph = pops[v]["_ph"]
        keep = [(s, px, w) for s, px, w in ph
                if (s.ticker, str(cal[s.gd].date())) not in prov
                and (s.ticker, str(cal[int(st.bars[s.ticker]["di"][s.ti - 1])].date())) not in prov]
        r = [VB.net_ret(s.E, px, C.COST_RT_JUDGE) for s, px, _ in keep]
        out["D6"][v] = {"n_kept": len(keep), "n_dropped": len(ph) - len(keep),
                        "mean": float(np.mean(r)) if r else None}
    print("[vb] D6", out["D6"], flush=True)

    # ── P3 · P4 (두 판) — C7 단독 풀 · W4 · 씨앗 16 · 운영 사이저 ──
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    cfg_rows = dict((r[0], r) for r in ext["strategy_config"][1])
    sc_cols = ext["strategy_config"][0]
    vrow = dict(zip(sc_cols, cfg_rows["volatility_breakout"]))
    vparams = vrow["params"] if isinstance(vrow["params"], dict) else json.loads(vrow["params"])
    op = OpSizer(VolatilityBreakoutStrategy, "volatility_breakout", vparams)
    sizer = VB.lot_qty_operating(op)
    sbg = defaultdict(list)
    for s in sigs:
        sbg[s.gd].append(s)
    for v in VB.VERSIONS:
        runs = []
        for seed in C.BOOK_SEEDS:
            open_pos, size_fn = VB.make_book_fns(v, sizer)
            runs.append(BK.run_book(sbg, open_pos, size_fn, cal, C.W4[0], C.W4[1], seed,
                                    start_equity=float(C.BUDGET_C7), cost_side=C.COST_RT_JUDGE / 2,
                                    max_pos=VB.VB_OP["max_pos"]))
        sm = BK.book_summary(runs, float(C.BUDGET_C7))
        tr0 = runs[0]["trades"]
        notional = np.array([t.cost_basis for t in tr0])
        out[f"P3_{v}"] = J.p3(sm)
        out[f"P4_{v}"] = J.p4(sm)
        out[f"book_{v}"] = {k: sm[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median",
                                               "trades_median", "fills_per_year_median",
                                               "unaffordable_ratio_median", "recon_max_abs", "counts_seed0")}
        out[f"book_{v}"]["lot_notional_seed0_median"] = float(np.median(notional)) if len(notional) else None
        out[f"book_{v}"]["one_share_share_seed0"] = float(np.mean([t.qty == 1 for t in tr0])) if tr0 else None
        out[f"book_{v}"]["trade_net_mean_seed0"] = float(np.mean([t.exit_px / t.s.E - 1 - C.COST_RT_JUDGE
                                                                   for t in tr0])) if tr0 else None
        print(f"[vb] book {v}", out[f"book_{v}"], out[f"P3_{v}"]["label"], out[f"P4_{v}"]["label"], flush=True)

    # ── 보고판 ──
    rep = {}
    for v in VB.VERSIONS:
        pw = pops[v]["_pw"]
        yr = defaultdict(list)
        mu = defaultdict(list)
        for s, px, _w in pw:
            r = VB.net_ret(s.E, px, C.COST_RT_JUDGE)
            yr[cal[s.gd].year].append(r)
            mu["nan" if not np.isfinite(s.m) else f"{s.m:g}"].append(r)
        rep[f"by_year_{v}"] = {str(k): {"n": len(x), "mean": float(np.mean(x))} for k, x in sorted(yr.items())}
        rep[f"by_mu_{v}"] = {k: {"n": len(x), "mean": float(np.mean(x))} for k, x in sorted(mu.items())}
        ctrl = []
        for sd in range(4):
            ctrl += VB.random_control(cands, sigs, st.bars, v, w5[0], w5[1], C.BOOT_SEED + sd)
        rr = np.array([x[2] for x in ctrl]) - C.COST_RT_JUDGE
        rep[f"random_open_entry_{v}"] = {"n": len(rr), "mean": float(rr.mean()),
                                         "note": "그날 후보에서 신호 수만큼 무작위 · 시가 진입 · 같은 청산(씨앗 4개 합)"}
        # ① 오늘 시총 유니버스(생존 편향): 지금 master 에 있는 종목만
        mcols, mrows = ext["master"]
        alive = {r[mcols.index("ticker")] for r in mrows}
        ra = [VB.net_ret(s.E, px, C.COST_RT_JUDGE) for s, px, _ in pw if s.ticker in alive]
        rep[f"survivor_only_{v}"] = {"n": len(ra), "mean": float(np.mean(ra)) if ra else None}
        # 진입가 칸(운영 예산에서 살 수 있었나 — cycle381 문턱 86,794원)
        cheap = [VB.net_ret(s.E, px, C.COST_RT_JUDGE) for s, px, _ in pw if s.E_raw <= 86_794]
        dear = [VB.net_ret(s.E, px, C.COST_RT_JUDGE) for s, px, _ in pw if s.E_raw > 86_794]
        rep[f"price_bucket_{v}"] = {"le_86794": {"n": len(cheap), "mean": float(np.mean(cheap)) if cheap else None},
                                    "gt_86794": {"n": len(dear), "mean": float(np.mean(dear)) if dear else None}}
    out["report"] = rep
    print("[vb] report", json.dumps(rep, ensure_ascii=False), flush=True)

    # 원장(스크래치)
    ledger = {v: [{"t": s.ticker, "d": str(cal[s.gd].date()), "E_raw": s.E_raw, "exit_ratio": px / s.E, "why": w}
                  for s, px, w in pops[v]["_pw"] + pops[v]["_ph"]] for v in VB.VERSIONS}
    out["elapsed_s"] = time.time() - t0
    clean = {k: v for k, v in out.items()}
    for v in VB.VERSIONS:
        for kk in ("W5y", "H"):
            pops[v][kk].pop("_r", None)
    with open(os.path.join(OUT_DIR, "vb_result.json"), "w") as fh:
        json.dump({"result": clean, "ledger": ledger}, fh, ensure_ascii=False, indent=1, default=str)
    print("[vb] done", f"{out['elapsed_s']:.0f}s", flush=True)


if __name__ == "__main__":
    main()
