"""질문 ② kojiro — 유니버스 A(현행 시대 중립) vs B(A ∧ 지수 구성 근사), 원천 comp/idx/etf (prereg §3).

재사용: ``kojiro_y30``(보관소·지표·포지션·게이트 — 30년 재검증 엔진 그대로) · ``kojiro``(신호) · ``kojiro_opt``.
파라미터 = 운영 strategy_config 10-15 행(``live_check`` 와 같은 SELECT) · 업종 = 운영 master_raw 10-15 덤프 소급.
판정 체결 = 시가 + 0.76%(30년 재검증 실거래 보정판). 실행: python -I run_kojiro.py <scratch>
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
from replay.audit import judge as J  # noqa
from replay.audit import market_unit as MU  # noqa
from replay.audit.sizing import OpSizer  # noqa
from replay.strategies import kojiro as KJ  # noqa
from replay.strategies import kojiro_opt as KO  # noqa
from replay.strategies import kojiro_opt_run as KOR  # noqa
from replay.strategies import kojiro_y30 as Y  # noqa
from src.engine.etf_like import is_etf_like  # noqa
from src.engine.strategies import kojiro as KS  # noqa
from src.engine.strategies.kojiro import KojiroStrategy  # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = sys.argv[1]
SLIP = 0.0076
W = {"T": Y.T_WIN, "V": Y.V_WIN, "H": Y.H_WIN}
t0 = time.time()


def log(*a):
    print(f"[kojiro {time.time()-t0:5.0f}s]", *a, flush=True)


def live_params():
    for ln in open(os.path.join(SCR, "live.txt"), encoding="utf-8"):
        if ln.startswith("kojiro|"):
            return KJ.op_params({"params": ln.split("|", 3)[3].strip()})
    raise SystemExit("kojiro 운영 행 없음")


def sectors():
    out = {}
    for ln in open(os.path.join(SCR, "master_raw.jsonl"), encoding="utf-8"):
        d = json.loads(ln)
        raw = d.get("r")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = None
        out[d["t"]] = KS._kojiro_sector_key(raw if isinstance(raw, dict) else None, d["t"])
    return out


def run_book30(sbg, open_pos, size_fn, cal, start, end, seed, *, start_equity, cost, max_pos, slip_of):
    """``kojiro_y30.run_book30`` 복사 + 종목별 추가 왕복 비용(매수·매도 반반)."""
    rng = np.random.default_rng(seed)
    g0, g1 = Y.gd_range(cal, (start, end))
    cash = float(start_equity)
    pos, equity, trades = {}, [], []
    eq_prev = float(start_equity)
    cnt = Counter()
    for gd in range(g0, g1 + 1):
        B = eq_prev
        sold = set()
        cs = cost.sell(gd)
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                continue
            if ps.open_phase(ti, gd):
                cash += ps.k * ps.exit_px * (1 - cs - ps._sl)
                trades.append(ps); sold.add(t); del pos[t]
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
            cash -= q * s.E_raw * (1 + cost.buy(gd) + ps._sl)
            pos[s.ticker] = ps
            cnt["fill"] += 1
            cnt["fill_index" if s.extra.get("mem") else "fill_out"] += 1
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                if ps.data_ended(gd):
                    ps._exit(ps.last_px, "END", gd)
                    cash += ps.k * ps.exit_px * (1 - cs - ps._sl)
                    trades.append(ps); del pos[t]
                continue
            if ps.intraday_phase(ti, gd, ti == ps.s.ti):
                cash += ps.k * ps.exit_px * (1 - cs - ps._sl)
                trades.append(ps); del pos[t]
        eq = cash + sum(x.value() for x in pos.values())
        equity.append(eq)
        eq_prev = eq
    for ps in pos.values():
        ps._exit(ps.last_px, "OPEN", None)
        trades.append(ps)
    return {"equity": np.array(equity), "trades": trades, "dates": cal[g0:g1 + 1], "counts": dict(cnt), "g": (g0, g1),
            "recon": 0.0}


def books(sigs, bars, feats, p, cal, win, cost, extra_slip):
    pe = KOR.exit_cfg(KOR.CURRENT).params(p)
    sizer = OpSizer(KojiroStrategy, "kojiro", p, atr_keys=("atr",))
    sbg = defaultdict(list)
    g0, g1 = Y.gd_range(cal, win)
    for s in sigs:
        if g0 <= s.gd <= g1:
            sbg[s.gd].append(KO.slip_sig(s, SLIP))
    runs = []
    for seed in C.BOOK_SEEDS:
        g = Y.Gates30(p, sizer)

        def open_pos(s, q, g=g):
            ps = Y.Y30Pos(s, bars[s.ticker], feats[s.ticker], q, pe, mode="color", time_n=None)
            g.opened.append(ps)
            return ps
        runs.append(run_book30(sbg, open_pos, g.size, cal, win[0], win[1], seed, start_equity=float(C.BUDGET_C7),
                               cost=cost, max_pos=int(p["max_positions"]),
                               slip_of=lambda s: 0.0 if s.extra.get("mem") else extra_slip))
    sm = Y.summary30(runs, float(C.BUDGET_C7), cal)
    yrs = sm["years"]
    cg = [Y.cagr_cal(r["equity"], float(C.BUDGET_C7), yrs) for r in runs]
    c = Counter()
    for r in runs:
        c.update(r["counts"])
    return {"cagr": sm["cagr_median"], "cagr_min": sm["cagr_min"], "cagr_max": sm["cagr_max"], "mdd": sm["mdd_median"],
            "fills_y": sm["fills_per_year_median"], "per_seed": cg,
            "out_fill_share": c["fill_out"] / max(1, c["fill"]), "slot_full_share": c["slot_full"] / max(1, c["signal"]),
            "counts16": dict(c)}


def stats(pop, cal, cost, extra=0.0):
    if not pop:
        return {"n": 0}
    r = np.array([Y.net(x, cost) - (0 if x.s.extra.get("mem") else extra) for x in pop])
    p1 = J.p1(r, [x.s.ticker for x in pop], [cal[x.s.gd].date() for x in pop])
    return {"n": len(r), "mean": float(r.mean()), "lo90": p1["lo90"], "median": float(np.median(r)),
            "win": float((r > 0).mean()), "exit": dict(Counter(x.exit_reason for x in pop))}


def main():
    Y.patch_fast_ewm()
    p = live_params()
    sec = sectors()
    df, meta = Y.load_unified(drop_flags=True)
    etf_names = sorted(n for n in df.name.dropna().unique() if is_etf_like(None, n))
    if etf_names:
        df = df[~df.name.isin(etf_names)]
    cal = pd.DatetimeIndex(sorted(df.bas_dd.unique()))
    st = Y.build(df, cal=cal)
    del df
    Y.Y30Pos.LIM = Y.limit_table(cal)
    cost = Y.era_cost(cal)
    log("store", len(st.bars), {k: p[k] for k in ("atr_ratio_max", "stage1_freshness", "risk_pct", "max_positions",
                                                  "position_ratio", "sizing_mode", "min_market_cap")})
    mem = pd.read_parquet(os.path.join(SCR, "mem.parquet"))
    by = {t: g.bas_dd.values.astype("datetime64[ns]") for t, g in mem.groupby("ticker")}
    for t, b in st.bars.items():
        d = cal[b["di"]].to_numpy().astype("datetime64[ns]")
        b["mem"] = np.isin(d, by[t]) if t in by else np.zeros(len(d), bool)
        mk = np.asarray(b["mkt"])
        b["kq"] = (mk == 1) if mk.ndim else np.full(len(d), int(mk) == 1)
    ser = pd.read_csv(os.path.join(SCR, "series.csv"), index_col=0, parse_dates=True)
    M = {}
    for nm in ("kospi", "kosdaq", "k200", "q150a", "etf"):
        x = ser[nm].dropna()
        M[nm] = MU.m_for_days(cal, pd.DatetimeIndex(x.index), x.to_numpy(float))
    band = float(p["atr_ratio_max"])
    feats = {}
    for t, b in st.bars.items():
        f = KJ.features(b, p)
        f["tech"] = f["tech"] & (f["ratio"] <= band)
        feats[t] = f
    log("features")
    uA = {t: Y.universe_era(b) for t, b in st.bars.items()}
    uB = {t: uA[t] & st.bars[t]["mem"] for t in uA}

    def sigs(u, src):
        mkp = {"comp": "kospi", "idx": "k200", "etf": "etf"}[src]
        mkq = {"comp": "kosdaq", "idx": "q150a", "etf": "etf"}[src]
        sg, cnt = KJ.build_signals(st.bars, feats, u, M[mkp], p, sec)
        for s in sg:
            b = st.bars[s.ticker]
            i = s.ti - 1
            s.extra["mem"] = bool(b["mem"][i])
            s.extra["kq"] = bool(b["kq"][i])
            if s.extra["kq"]:
                v = M[mkq][s.gd]
                s.m = 1.0 if not np.isfinite(v) else float(v)
        return KO.select(sg, "cur", None), cnt

    R = {"params": {k: p[k] for k in ("atr_ratio_max", "stage1_freshness", "risk_pct", "max_positions", "position_ratio",
                                      "sizing_mode", "min_market_cap", "min_trade_amount", "max_open_risk_pct",
                                      "max_positions_per_sector")}}
    cand = {}
    for nm, u in (("A", uA), ("B", uB)):
        cnt = np.zeros(len(cal))
        for t, b in st.bars.items():
            ok = feats[t]["tech"] & u[t]
            np.add.at(cnt, b["di"][ok], 1)
        cand[nm] = {w: float(cnt[int(cal.searchsorted(pd.Timestamp(a))):int(cal.searchsorted(pd.Timestamp(z), side="right"))].mean())
                    for w, (a, z) in {**W, "Y1": ("2025-10-01", "2026-10-02")}.items()}
    R["cand_per_day"] = cand
    log("cand", cand)
    cfg = KOR.exit_cfg(KOR.CURRENT)
    for vn, u, src in (("A|comp", uA, "comp"), ("B|comp", uB, "comp"), ("B|idx", uB, "idx"), ("A|etf", uA, "etf")):
        sg, cnt = sigs(u, src)
        memo = Y.PathMemo(st.bars, feats, p)
        R[vn] = {"n_sig": len(sg), "sig_counts": cnt}
        for wn, win in W.items():
            g0, g1 = Y.gd_range(cal, win)
            pop = Y.population(sg, memo, cfg, g0, g1, SLIP)
            d = {"pop": stats(pop, cal, cost), "pop_in": stats([x for x in pop if x.s.extra["mem"]], cal, cost),
                 "pop_out": stats([x for x in pop if not x.s.extra["mem"]], cal, cost),
                 "pop_kq": stats([x for x in pop if x.s.extra["kq"]], cal, cost),
                 "pop_kp": stats([x for x in pop if not x.s.extra["kq"]], cal, cost),
                 "sig_per_day": len([s for s in sg if g0 <= s.gd <= g1]) / max(1, g1 - g0 + 1),
                 "m_mean_sig": float(np.mean([s.m for s in sg if g0 <= s.gd <= g1] or [np.nan]))}
            for sl in ((0.0, 0.005, 0.01) if vn == "A|comp" else (0.0,)):
                d[f"book_s{sl}"] = books(sg, st.bars, feats, p, cal, win, cost, sl)
            if vn == "A|comp":
                for sl in (0.005, 0.01):
                    d[f"pop_s{sl}"] = stats(pop, cal, cost, extra=sl)
            R[vn][wn] = d
            log(vn, wn, "pop", d["pop"]["n"], round(d["pop"]["mean"], 5), "in", round(d["pop_in"].get("mean", np.nan), 5),
                "out", round(d["pop_out"].get("mean", np.nan), 5), "book", round(d["book_s0.0"]["cagr"], 4),
                round(d["book_s0.0"]["mdd"], 3), "fills", round(d["book_s0.0"]["fills_y"], 1))
            with open(os.path.join(HERE, "result_kojiro.json"), "w") as fh:
                json.dump(R, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    log("done")


if __name__ == "__main__":
    main()
