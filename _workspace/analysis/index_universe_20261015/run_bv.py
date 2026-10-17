"""질문 ② BFB·VCP — 유니버스 A(현행 시대 중립) vs B(A ∧ 지수 구성 근사), 원천 comp/idx/etf (prereg §3).

재사용: ``y30_bfbvcp``(신호·포지션·모집단·통계 — 30년 재검증 엔진 그대로) · ``y30_data``(보관소·비용·유니버스).
이 파일이 더하는 것 = 지수 구성 표시(mem) · 시장별 m 덮어쓰기 · 지수 밖 거래 추가 체결 오차를 넣은 계좌(run_book 복사).
실행: python -I run_bv.py <scratch> vcp|bfb
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter, defaultdict

for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/koscom/Projects/auto_stock/tools")
sys.path.insert(0, "/Users/koscom/Projects/auto_stock")
from replay.audit import config as C  # noqa
from replay.audit import market_unit as MU  # noqa
from replay.strategies import bfb_vcp_opt as OP  # noqa
from replay.strategies import y30_bfbvcp as YB  # noqa
from replay.strategies import y30_data as Y  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
SCR, KIND = sys.argv[1], sys.argv[2]
Y.CACHE_DIR = os.path.join(SCR, "bfbvcp")
W = {"T": YB.T_WIN, "V": YB.V_WIN, "H": YB.H_WIN}
LIVE_OVR = {"vcp": dict(max_positions=3, position_ratio=0.33, max_lot_ratio_mult=1.5),
            "bfb": dict(breakout_volume_mult=1.5)}
t0 = time.time()


def log(*a):
    print(f"[{KIND} {time.time()-t0:5.0f}s]", *a, flush=True)


def m_series(cal):
    ser = pd.read_csv(os.path.join(SCR, "series.csv"), index_col=0, parse_dates=True)
    out = {}
    for nm in ("kospi", "kosdaq", "k200", "q150a", "etf"):
        x = ser[nm].dropna()
        out[nm] = MU.m_for_days(cal, pd.DatetimeIndex(x.index), x.to_numpy(float))
    return out


def attach_mem(st):
    mem = pd.read_parquet(os.path.join(SCR, "mem.parquet"))
    by = {t: g.bas_dd.values.astype("datetime64[ns]") for t, g in mem.groupby("ticker")}
    for t, b in st.bars.items():
        d = st.cal[b["di"]].to_numpy().astype("datetime64[ns]")
        b["mem"] = np.isin(d, by[t]) if t in by else np.zeros(len(d), bool)
        b["kq"] = (np.asarray(b["mkt"]) == 1) if np.ndim(b["mkt"]) else np.full(len(d), b["mkt"] == 1)


def run_book(sbg, open_pos, size_fn, cal, start, end, seed, *, start_equity, cost, max_pos, slip_of):
    """``y30_bfbvcp.run_book`` 복사 + 종목별 추가 왕복 비용(매수·매도 반반)."""
    rng = np.random.default_rng(seed)
    g0 = int(cal.searchsorted(pd.Timestamp(start)))
    g1 = int(cal.searchsorted(pd.Timestamp(end), side="right")) - 1
    cash = float(start_equity)
    pos, equity, trades = {}, [], []
    cnt = Counter()
    eq_prev = float(start_equity)

    def close(ps, gd):
        nonlocal cash
        ps._sc = cost.sell(gd) + ps._sl
        cash += ps.k * ps.exit_px * (1 - ps._sc)
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
        stop = None
        for s in todays:
            if s.ticker in pos or s.ticker in sold:
                continue
            cnt["signal"] += 1
            if stop is None and len(pos) >= max_pos:
                stop = "slot_full"
            if stop is not None:
                cnt[stop] += 1
                continue
            used = sum(x.cost_basis for x in pos.values())
            q, why = size_fn(s, B, used)
            if q <= 0:
                cnt["zero_" + why] += 1
                continue
            ps = open_pos(s, q)
            ps._sl = slip_of(s) / 2
            ps._bc = cost.buy(gd) + ps._sl
            cash -= q * s.E_raw * (1 + ps._bc)
            pos[s.ticker] = ps
            cnt["fill"] += 1
            cnt["fill_index" if s.mem else "fill_out"] += 1
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
        ps._sc = 0.0
        trades.append(ps)
    eq = np.array(equity)
    return {"equity": eq, "trades": trades, "counts": dict(cnt), "recon": 0.0,
            "years": YB.cal_years(cal, g0, g1), "start_equity": start_equity}


def books(sigs, st, feats, p, cls, win, cost, slip):
    from replay.audit.sizing import OpSizer
    sid = "vcp_breakout" if KIND == "vcp" else "bull_flag_breakout"
    op = OpSizer(cls, sid, {k: v for k, v in p.items() if not k.startswith("_")}, atr_keys=("atr14",))
    sbg = defaultdict(list)
    for s in sigs:
        sbg[s.gd].append(s)
    runs = []
    for seed in C.BOOK_SEEDS:
        cs = YB._CD(sbg, int(p["reentry_cooldown_days"]))

        def size_fn(s, B, used):
            P = int(round(s.E_raw))
            if s.m <= 0:
                return 0, "mu"
            N_raw = s.N * (s.E_raw / s.E)
            if op.blocks_entry(P, N_raw, budget=int(B), used=int(used), m=s.m, ticker=s.ticker):
                return 0, "mu"
            q = op.qty(P, N_raw, budget=int(B), used=int(used), m=s.m, ticker=s.ticker)
            return (q, "ok") if q > 0 else (0, "funds" if int(B) - int(used) < P else "design")

        def open_pos(s, q, _cs=cs):
            return YB.YPos(s, st.bars[s.ticker], feats[s.ticker], q, kind=KIND, p=p, cal=st.cal, on_exit=_cs.note_exit)
        runs.append(run_book(cs, open_pos, size_fn, st.cal, win[0], win[1], seed, start_equity=float(C.BUDGET_C7),
                             cost=cost, max_pos=int(p["max_positions"]), slip_of=lambda s: 0.0 if s.mem else slip))
    sm = YB.book_summary(runs)
    c = Counter()
    for r in runs:
        c.update(r["counts"])
    return {"cagr": sm["cagr_median"], "cagr_min": sm["cagr_min"], "cagr_max": sm["cagr_max"], "mdd": sm["mdd_median"],
            "fills_y": sm["fills_per_year_median"], "per_seed": sm["per_seed_cagr"],
            "out_fill_share": c["fill_out"] / max(1, c["fill"]), "slot_full_share": c["slot_full"] / max(1, c["signal"]),
            "zero_mu_share": c["zero_mu"] / max(1, c["signal"]), "counts16": dict(c)}


def main():
    cls, featf = YB._classes(KIND)
    st, meta = Y.build()
    cal = st.cal
    attach_mem(st)
    log("store", len(st.bars))
    M = m_series(cal)
    cost = YB.EraCostY(cal)
    p = OP.params_for(KIND, "cur", "X0")
    p.update(LIVE_OVR[KIND])
    feats = {t: featf(b, p) for t, b in st.bars.items()}
    log("features")
    uA = Y.universe(st, meta["ratios"], KIND, mode="pct")
    uB = {t: uA[t] & st.bars[t]["mem"] for t in uA}
    _, meth, cap, k = {e[0]: e for e in OP.entries_for(KIND)}["I"]

    def sigs(u, src):
        mkp = {"comp": "kospi", "idx": "k200", "etf": "etf"}[src]
        mkq = {"comp": "kosdaq", "idx": "q150a", "etf": "etf"}[src]
        sg = YB.build_signals(st.bars, feats, M[mkp], p, u, method=meth, cap=cap, k=k)
        for s in sg:
            b = st.bars[s.ticker]
            s.mem = bool(b["mem"][s.ti - 1])
            s.kq = bool(b["kq"][s.ti - 1])
            if s.kq:
                v = M[mkq][s.gd]
                s.m = 1.0 if not np.isfinite(v) else float(v)
        return sg

    R = {"kind": KIND, "params_override": LIVE_OVR[KIND], "ratios": meta["ratios"]}
    # 후보(셋업) 수 — 하루 평균(운영 퍼널 최종 후보와 대조)
    cand = {}
    for nm, u in (("A", uA), ("B", uB)):
        cnt = np.zeros(len(cal))
        for t, b in st.bars.items():
            ok = feats[t]["cand"] & u[t]
            np.add.at(cnt, b["di"][ok], 1)
        cand[nm] = {w: float(cnt[int(cal.searchsorted(pd.Timestamp(a))):int(cal.searchsorted(pd.Timestamp(z), side="right"))].mean())
                    for w, (a, z) in {**W, "Y1": ("2025-10-01", "2026-10-02")}.items()}
    R["cand_per_day"] = cand
    log("cand", cand)
    variants = (("A|comp", uA, "comp"), ("B|comp", uB, "comp"), ("B|idx", uB, "idx"), ("A|etf", uA, "etf"))
    for vn, u, src in variants:
        sg = sigs(u, src)
        R[vn] = {"n_sig": len(sg)}
        for wn, win in W.items():
            g0, g1 = int(cal.searchsorted(pd.Timestamp(win[0]))), int(cal.searchsorted(pd.Timestamp(win[1]), side="right")) - 1
            pop, jumped = YB.population(sg, st.bars, feats, g0, g1, kind=KIND, p=p, cal=cal)
            memo = {(ps.s.ticker, ps.s.gd): ps.s.mem for ps in pop}
            kqm = {(ps.s.ticker, ps.s.gd): ps.s.kq for ps in pop}
            rr = YB.rows_of(pop, cal, cost, g1)
            for x in rr:
                x["mem"] = memo[(x["t"], x["gd"])]
                x["kq"] = kqm[(x["t"], x["gd"])]
            yrs = YB.cal_years(cal, g0, g1)
            d = {"pop": YB.stat_block(rr, yrs), "pop_in": YB.stat_block([x for x in rr if x["mem"]], yrs),
                 "pop_out": YB.stat_block([x for x in rr if not x["mem"]], yrs),
                 "pop_kq": YB.stat_block([x for x in rr if x["kq"]], yrs),
                 "pop_kp": YB.stat_block([x for x in rr if not x["kq"]], yrs),
                 "sig_per_day": len([s for s in sg if g0 <= s.gd <= g1]) / max(1, g1 - g0 + 1),
                 "m_mean_sig": float(np.mean([s.m for s in sg if g0 <= s.gd <= g1] or [np.nan]))}
            for sl in ((0.0, 0.005, 0.01) if vn == "A|comp" else (0.0,)):
                d[f"book_s{sl}"] = books(sg, st, feats, p, cls, win, cost, sl)
            if vn == "A|comp":
                for sl in (0.005, 0.01):
                    d[f"pop_s{sl}"] = YB.stat_block([dict(x, r=x["r"] - (0 if x["mem"] else sl)) for x in rr], yrs)
            R[vn][wn] = d
            log(vn, wn, "pop", d["pop"]["n"], round(d["pop"]["mean"], 5), "in", round(d["pop_in"].get("mean", np.nan), 5),
                "out", round(d["pop_out"].get("mean", np.nan), 5), "book", round(d["book_s0.0"]["cagr"], 4),
                round(d["book_s0.0"]["mdd"], 3), "fills", round(d["book_s0.0"]["fills_y"], 1))
            with open(os.path.join(HERE, f"result_{KIND}.json"), "w") as fh:
                json.dump(R, fh, ensure_ascii=False, indent=1, default=YB._js)
    log("done")


if __name__ == "__main__":
    main()
