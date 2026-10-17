"""donchian 유니버스 확대 비교 — prereg.md 그대로. 재사용: donchian_y30(신호·포지션·모집단) · donchian_y30_data(비용·제한폭·p*)."""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/Users/koscom/Projects/auto_stock/tools")
from replay.audit import config as C  # noqa
from replay.audit import book as BK  # noqa
from replay.audit import judge as J  # noqa
from replay.audit import market_unit as MU  # noqa
from replay.audit import panel as PN  # noqa
from replay.audit.sizing import OpSizer, load_strategy_class  # noqa
from replay.strategies import donchian_kk as DK  # noqa
from replay.strategies import donchian_kk_audit as DA  # noqa
from replay.strategies import donchian_y30 as Y  # noqa
from replay.strategies import donchian_y30_data as YD  # noqa

CACHE = os.path.join(HERE, "store_full.pkl")
BRANCH = os.path.join(HERE, "donchian_kk_branch.py")
LONG = YD.LONG
WINDOWS = Y.WINDOWS
t0 = time.time()


def log(*a):
    print(f"[du {time.time()-t0:5.0f}s]", *a, flush=True)


def build():
    if os.path.exists(CACHE):
        with open(CACHE, "rb") as fh:
            return pickle.load(fh)
    p1 = YD.load_pass1()
    cal = pd.DatetimeIndex(sorted(p1.bas_dd.unique()))
    calib = YD.calibrate_p_star(p1)
    ps = calib["p_star"]
    p1["mem"] = YD.member_flags(p1)
    p1["tvok"] = YD.tv_top_flags(p1, ps)
    common = p1.ticker.str.match(YD._COMMON) & ~p1.name.fillna("").str.contains("스팩") & (p1.mktcap > 0)
    p1["common"] = common.to_numpy()
    # 시총 시대 중립 문턱 — 2025 년 보통주 중 시총 ≥ X 비율의 평균
    c25 = p1[common & (p1.bas_dd.dt.year == 2025)]
    q = {}
    for nm, thr in (("m3k", 3000e8), ("m1k", 1000e8)):
        q[nm] = float(c25.groupby("bas_dd")["mktcap"].apply(lambda x: (x >= thr).mean()).mean())
    sub = p1[common]
    rk = sub.groupby("bas_dd")["mktcap"].rank(ascending=False, method="first")
    nday = sub.groupby("bas_dd")["mktcap"].transform("size")
    for nm in q:
        f = pd.Series(False, index=p1.index)
        f.loc[sub.index] = (rk <= q[nm] * nday)
        p1[nm] = f.to_numpy()
    # 오늘(마지막 날) 규모 참고
    last = p1[p1.bas_dd == cal[-1]]
    info = {"p_star": ps, "q": q, "cal": [str(cal[0].date()), str(cal[-1].date()), len(cal)],
            "last_day": {"common": int(last.common.sum()), "mem": int(last.mem.sum()),
                         "common_tvok": int((last.common & last.tvok).sum()),
                         "mem_tvok": int((last.mem & last.tvok).sum()),
                         "m3k": int(last.m3k.sum()), "m1k": int(last.m1k.sum()),
                         "m3k_tvok": int((last.m3k & last.tvok).sum()), "m1k_tvok": int((last.m1k & last.tvok).sum())}}
    keep = set(p1.loc[p1.common & p1.tvok, "ticker"])
    info["keep_tickers"] = len(keep)
    flags = p1.loc[p1.ticker.isin(keep), ["ticker", "bas_dd", "mem", "tvok", "m3k", "m1k", "common"]]
    del p1
    fs = [os.path.join(YD.UNIFIED, f) for f in sorted(os.listdir(YD.UNIFIED)) if f.endswith(".parquet")]
    arch = pd.concat([pd.read_parquet(f, columns=YD.P2_COLS, filters=[("ticker", "in", sorted(keep))]) for f in fs],
                     ignore_index=True)
    arch["bas_dd"] = pd.to_datetime(arch["bas_dd"])
    arch = arch.merge(flags, on=["ticker", "bas_dd"], how="left")
    for k in ("mem", "tvok", "m3k", "m1k", "common"):
        arch[k] = arch[k].fillna(False).astype(bool)
    arch["tv200"] = (arch.trade_value >= YD.TV_NOMINAL).to_numpy()
    arch["kq"] = YD.mkt_group(arch.market).eq("KOSDAQ").to_numpy()
    jr = YD.jump_rows()
    jr["jump"] = True
    arch = arch.merge(jr, on=["ticker", "bas_dd"], how="left")
    arch["jump"] = arch["jump"].fillna(False).astype(bool)
    arch["lim"] = YD.limit_for(arch.bas_dd, arch.market)
    nt = arch.no_trade.fillna(False).astype(bool)
    arch.loc[nt, "volume"] = 0.0
    arch = arch.sort_values(["ticker", "bas_dd"]).reset_index(drop=True)
    st = PN.build_store(arch, db=None, nontrade="flag", junction_rescale=False, cal=cal,
                        extra_cols=("mem", "tvok", "tv200", "jump", "lim", "m3k", "m1k", "common", "kq"))
    for b in st.bars.values():
        for k in ("mem", "tvok", "tv200", "jump", "m3k", "m1k", "common", "kq"):
            b[k] = b[k].astype(bool)
        b["lim"] = b["lim"].astype(float)
    mus = YD.market_unit_series()
    m_etf = MU.m_for_days(cal, pd.DatetimeIndex(mus.date), mus.close.to_numpy(float))
    ms = {}
    for nm, fn in (("kospi", "krx_kospi.csv"), ("kosdaq", "krx_kosdaq.csv")):
        ix = pd.read_csv(os.path.join(LONG, "index", fn))
        ix["date"] = pd.to_datetime(ix["date"])
        ix = ix.dropna(subset=["close"]).sort_values("date")
        ms[nm] = MU.m_for_days(cal, pd.DatetimeIndex(ix.date), ix.close.to_numpy(float))
    out = (st, {"etf": m_etf, **ms}, info)
    with open(CACHE, "wb") as fh:
        pickle.dump(out, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return out


# ── 슬리피지 붙은 계좌(run_book 복사 + 종목별 추가 비용) ──────────────────

def run_book(sbg, open_pos, size_fn, cal, start, end, seed, *, start_equity, costs, max_pos, daily_cap,
             slip_of, prio=None):
    rng = np.random.default_rng(seed)
    g0 = int(cal.searchsorted(pd.Timestamp(start)))
    g1 = int(cal.searchsorted(pd.Timestamp(end), side="right")) - 1
    cash = float(start_equity)
    pos, equity, trades = {}, [], []
    cnt = Counter()
    eq_prev = float(start_equity)

    def close(ps, gd):
        nonlocal cash
        ps._cs_sell = costs.sell[gd] + ps._slip
        cash += ps.k * ps.exit_px * (1 - ps._cs_sell)
        trades.append(ps)

    for gd in range(g0, g1 + 1):
        B = eq_prev
        sold = set()
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                continue
            if ps.open_phase(ti, gd):
                close(ps, gd); sold.add(t); del pos[t]
        todays = list(sbg.get(gd, []))
        rng.shuffle(todays)
        if prio is not None:
            todays.sort(key=lambda s: 0 if prio(s) else 1)
        n_new, stop = 0, None
        for s in todays:
            if s.ticker in pos or s.ticker in sold:
                continue
            cnt["signal"] += 1
            if stop is None and len(pos) >= max_pos:
                stop = "slot_full"
            if stop is None and n_new >= daily_cap:
                stop = "daily_cap"
            if stop is not None:
                cnt[stop] += 1
                continue
            used = sum(x.cost_basis for x in pos.values())
            q, why = size_fn(s, B, used)
            if q <= 0:
                cnt["zero_" + why] += 1
                continue
            ps = open_pos(s, q)
            ps._slip = slip_of(s)
            ps._cs_buy = costs.buy[gd] + ps._slip
            cash -= q * s.E_raw * (1 + ps._cs_buy)
            pos[s.ticker] = ps
            n_new += 1
            cnt["fill"] += 1
            cnt["fill_added" if not s.mem else "fill_index"] += 1
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                if ps.data_ended(gd):
                    ps._exit(ps.last_px, "END", gd); close(ps, gd); del pos[t]
                continue
            if ps.intraday_phase(ti, gd, ti == ps.s.ti):
                close(ps, gd); del pos[t]
        eq = cash + sum(x.value() for x in pos.values())
        equity.append(eq)
        eq_prev = eq
    for ps in pos.values():
        ps._exit(ps.last_px, "OPEN", None)
        trades.append(ps)
    return {"equity": np.array(equity), "trades": trades, "counts": dict(cnt), "recon": 0.0}


def main():
    st, M, info = build()
    log("store", len(st.bars), info)
    cal = st.cal
    Y._CAL["cal"] = cal
    bars = st.bars
    era = Y.Costs(cal)
    kk = Y.kk_of(Y.EXIT0)
    # 기본 특징(유니버스 마스크 없이) — mem 을 전부 True 로 보고 cond 계산 후 마스크
    feats = {}
    for t, b in bars.items():
        bb = dict(b)
        bb["mem"] = b["common"]
        feats[t] = Y.features_y30(bb, entry_n=20, vol_mult=1.5, clv=None, tv_mode="pct")
    log("features")
    masks = {"U0": "mem", "U1": "common", "U2": "m3k", "U3": "m1k"}

    def signals(uni, mkey):
        fv = {}
        for t, f in feats.items():
            g = dict(f)
            g["cond"] = f["cond"] & bars[t][masks[uni]]
            fv[t] = g
        if mkey == "etf":
            sg = DK.build_signals(bars, fv, M["etf"])
        else:
            sg = DK.build_signals(bars, fv, M["kospi"])
            mk = M["kosdaq"]
            for s in sg:
                if bars[s.ticker]["kq"][s.ti - 1]:
                    v = mk[s.gd]
                    s.m = 1.0 if not np.isfinite(v) else float(v)
        sg = [s for s in sg if not DA.r_half_blocked(s.E, s.N, kk)]
        for s in sg:
            b = bars[s.ticker]
            s.mem = bool(b["mem"][s.ti - 1])
            s.kq = bool(b["kq"][s.ti - 1])
            s.mcap_rank = None
        return sg

    def gwin(w):
        a, b = WINDOWS[w]
        return int(cal.searchsorted(pd.Timestamp(a))), int(cal.searchsorted(pd.Timestamp(b), side="right")) - 1

    def rows(pop, end_gd, slip):
        out = []
        for p in pop:
            cr = era.rt(p.s.gd, p.exit_gd if p.exit_gd is not None else end_gd) + (0 if p.s.mem else slip)
            net = p.exit_px / p.E - 1 - cr
            out.append({"t": p.s.ticker, "gd": p.s.gd, "m": p.s.m, "net": net, "R": net / (p.Rw / p.E),
                        "why": p.exit_reason, "mem": p.s.mem, "kq": p.s.kq,
                        "hold": (p.exit_gd - p.s.gd + 1) if p.exit_gd is not None else None})
        return out

    def st_(rs):
        if not rs:
            return {"n": 0}
        r = J.p1([x["net"] for x in rs], [x["t"] for x in rs], [cal[x["gd"]].date() for x in rs])
        w = [x["net"] for x in rs if x["net"] > 0]
        l = [x["net"] for x in rs if x["net"] <= 0]
        return {"n": r["n"], "mean": r["mean"], "lo90": r["lo90"], "win": len(w) / len(rs),
                "avg_win": float(np.mean(w)) if w else None, "avg_loss": float(np.mean(l)) if l else None,
                "payoff": float(np.mean(w) / -np.mean(l)) if w and l else None,
                "R_mean": float(np.mean([x["R"] for x in rs])),
                "hold_med": float(np.median([x["hold"] for x in rs if x["hold"]])) if any(x["hold"] for x in rs) else None,
                "kq_share": float(np.mean([x["kq"] for x in rs])),
                "why": dict(Counter(x["why"] for x in rs))}

    cls = load_strategy_class(BRANCH, "DonchianSwingStrategy", "du_branch")
    op = OpSizer(cls, "donchian_swing", {"market_unit_mode": "enforce", "risk_pct": 0.012, "position_ratio": 0.15,
                                         "max_positions": 6, "kk_r_floor_pct": 8.0, "kk_r_atr_mult": 1.5})

    def opsize(s, B, used):
        P = int(round(s.E_raw))
        if s.m <= 0 or P <= 0:
            return 0, "mu"
        q = op.qty(P, s.N * (s.E_raw / s.E), budget=int(B), used=int(used), m=s.m)
        return (q, "ok") if q > 0 else (0, "funds" if int(B) - int(used) < P else "design")

    def book(sg, w, slip, prio=None):
        sbg = defaultdict(list)
        for s in sg:
            sbg[s.gd].append(s)
        fv = feats

        def open_pos(s, q):
            return Y.Y30Pos(s, bars[s.ticker], fv[s.ticker], q, mode="color", kk=kk)
        runs = [run_book(sbg, open_pos, opsize, cal, WINDOWS[w][0], WINDOWS[w][1], sd, start_equity=float(C.BUDGET_C7),
                         costs=era, max_pos=6, daily_cap=3, slip_of=lambda s: 0.0 if s.mem else slip / 2, prio=prio)
                for sd in C.BOOK_SEEDS]
        sm = BK.book_summary(runs, float(C.BUDGET_C7))
        c = Counter()
        for r in runs:
            c.update(r["counts"])
        # 체결 거래의 지수 밖 비중·사유
        tr = [ps for r in runs for ps in r["trades"]]
        return {"cagr": sm["cagr_median"], "cagr_min": sm["cagr_min"], "cagr_max": sm["cagr_max"],
                "mdd": sm["mdd_median"], "fills_y": sm["fills_per_year_median"],
                "per_seed": [x["cagr"] for x in sm["per_seed"]], "per_seed_mdd": [x["mdd"] for x in sm["per_seed"]],
                "counts16": dict(c), "added_fill_share": c["fill_added"] / max(1, c["fill"]),
                "slot_full_share": c["slot_full"] / max(1, c["signal"]), "daily_cap_share": c["daily_cap"] / max(1, c["signal"])}

    R = {"info": info}
    for mkey in ("mkt", "etf"):
        for uni in ("U0", "U1", "U2", "U3"):
            if mkey == "etf" and uni in ("U2", "U3"):
                continue
            sg = signals(uni, mkey)
            spd = Counter(s.gd for s in sg)
            key = f"{uni}|{mkey}"
            R[key] = {"n_sig": len(sg)}
            for w in ("T", "V", "H"):
                g = gwin(w)
                pop = Y.population(sg, bars, feats, g[0], g[1], kk=kk)
                d = {}
                for sl in (0.0, 0.005, 0.01):
                    rs = rows(pop, g[1], sl)
                    d[f"pop_s{sl}"] = st_(rs)
                    d[f"pop_added_s{sl}"] = st_([x for x in rs if not x["mem"]])
                    d[f"pop_index_s{sl}"] = st_([x for x in rs if x["mem"]])
                days = [spd.get(x, 0) for x in range(g[0], g[1] + 1)]
                d["sig_per_day_mean"] = float(np.mean(days))
                d["sig_days_ge4_share"] = float(np.mean([x >= 4 for x in days]))
                if mkey == "mkt" or uni in ("U0", "U1"):
                    for sl in ((0.0, 0.005, 0.01) if (mkey == "mkt" and uni != "U0") else (0.005,)):
                        d[f"book_s{sl}"] = book(sg, w, sl)
                    if uni == "U1" and mkey == "mkt":
                        d["book_prio_s0.005"] = book(sg, w, 0.005, prio=lambda s: s.mem)
                        d["book_prio_s0.01"] = book(sg, w, 0.01, prio=lambda s: s.mem)
                R[key][w] = d
                log(key, w, "pop", round(d["pop_s0.005"].get("mean", np.nan), 5), "added",
                    d["pop_added_s0.005"].get("n"), round(d["pop_added_s0.005"].get("mean", np.nan) or np.nan, 5),
                    "book", round(d["book_s0.005"]["cagr"], 4), round(d["book_s0.005"]["mdd"], 3))
            with open(os.path.join(HERE, "result.json"), "w") as fh:
                json.dump(R, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    # 최근 신호(겹침 분석용) — U1·U0 mkt, 2026-08-01 이후 진입일
    sgs = {u: signals(u, "mkt") for u in ("U0", "U1", "U2", "U3")}
    g0 = int(cal.searchsorted(pd.Timestamp("2026-08-01")))
    R["recent"] = {u: [[str(cal[s.gd].date()), s.ticker, s.mem, s.kq, s.m] for s in sg if s.gd >= g0] for u, sg in sgs.items()}
    with open(os.path.join(HERE, "result.json"), "w") as fh:
        json.dump(R, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    log("done")


if __name__ == "__main__":
    main()
