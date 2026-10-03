#!/usr/bin/env python3
"""평균회귀(OU) 트랙 R 연구 실행기 — 1단계: 종목별 추정·통과율·거래 목록.

지시서 = ``_workspace/design/2026-10-01_mean_reversion_handoff.md`` §3.
연구 venv(numpy·pandas·scipy·statsmodels)에서만 돈다. 네트워크·DB 접속 없음.

    python tools/replay/run_mean_reversion.py stage1 <segment: archive|db> <out.pkl> [--db-extract PATH]
    python tools/replay/analyze_mean_reversion.py ...   (2단계 — 판정·표)
"""
from __future__ import annotations

import math
import multiprocessing as mp
import os
import pickle
import sys
import time

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from replay import data as D  # noqa: E402
from replay import universe as U  # noqa: E402
from replay.execution import Rule, simulate_ticker  # noqa: E402
from replay.strategies.mean_reversion import leung as LG  # noqa: E402
from replay.strategies.mean_reversion.signals import REASON_CODES, estimate_series  # noqa: E402
from src.engine.market_unit import classify  # noqa: E402  (라이브 판정 그대로)

SEED = 20261001
R_ANNUAL = 0.035
COSTS = (0.0028, 0.0038, 0.0048)
Z_ENTRY = (-1.5, -2.0, -2.5)
Z_EXIT = (-0.5, -0.25, 0.0)
STOP_PCT = (5.0, 7.0, 10.0)
K_STOP = (1.0, 1.5, 2.0)
BASE_STOP = (7.0, 1.5)
TRADE_COLS = ("tj", "ei", "xi", "sig_day", "entry_px", "exit_px", "gross", "reason", "z_entry",
              "z_exit", "hl", "held", "mae", "mfe", "mu", "entry_raw")
REASONS = ("profit", "disaster_pct", "disaster_z", "regime_break", "timeout", "leung_stop")


def build_rules(segment: str) -> "list[tuple[str, str, str, Rule]]":
    """(키, 모드, 유니버스, 규칙)."""
    uni = "asof" if segment == "archive" else "db"
    out = []
    for ez in Z_ENTRY:
        for xz in Z_EXIT:
            for cost in COSTS:
                out.append((f"z|{ez}|{xz}|{cost}|{BASE_STOP[0]}|{BASE_STOP[1]}|resid|{uni}|mu", "resid", uni,
                            Rule("z", ez, xz, cost, *BASE_STOP)))
            for sp in STOP_PCT:
                for k in K_STOP:
                    if (sp, k) == BASE_STOP:
                        continue
                    out.append((f"z|{ez}|{xz}|0.0038|{sp}|{k}|resid|{uni}|mu", "resid", uni,
                                Rule("z", ez, xz, 0.0038, sp, k)))
            out.append((f"z|{ez}|{xz}|0.0038|7.0|1.5|price|{uni}|mu", "price", uni,
                        Rule("z", ez, xz, 0.0038, *BASE_STOP)))
            out.append((f"z|{ez}|{xz}|0.0038|7.0|1.5|resid|{uni}|nomu", "resid", uni,
                        Rule("z", ez, xz, 0.0038, *BASE_STOP, mu_block=False)))
            out.append((f"z|{ez}|{xz}|0.0038|7.0|1.5|resid|{uni}|mumiss", "resid", uni,
                        Rule("z", ez, xz, 0.0038, *BASE_STOP, mu_missing_enter=True)))
            if segment == "archive":
                out.append((f"z|{ez}|{xz}|0.0038|7.0|1.5|resid|today|mu", "resid", "today",
                            Rule("z", ez, xz, 0.0038, *BASE_STOP)))
    for cost in COSTS:
        out.append((f"leung|r3.5|{cost}|7.0|1.5|resid|{uni}|mu", "resid", uni,
                    Rule("leung", cost=cost, stop_pct=7.0, k_stop=1.5)))
    for sp in STOP_PCT:
        for k in K_STOP:
            if (sp, k) != BASE_STOP:
                out.append((f"leung|r3.5|0.0038|{sp}|{k}|resid|{uni}|mu", "resid", uni,
                            Rule("leung", cost=0.0038, stop_pct=sp, k_stop=k)))
    out.append((f"leung|r10|0.0038|7.0|1.5|resid|{uni}|mu", "resid", uni,
                Rule("leung", cost=0.0038, stop_pct=7.0, k_stop=1.5)))
    out.append((f"leung|r3.5|0.0038|7.0|1.5|resid|{uni}|nomu", "resid", uni,
                Rule("leung", cost=0.0038, stop_pct=7.0, k_stop=1.5, mu_block=False)))
    if segment == "archive":
        out.append((f"leung|r3.5|0.0038|7.0|1.5|resid|today|mu", "resid", "today",
                    Rule("leung", cost=0.0038, stop_pct=7.0, k_stop=1.5)))
    return out


# ── 작업자 (fork 로 전역 공유) ────────────────────────────────────────────────
G: dict = {}


def _surrogate(logp: np.ndarray, rng, kind: str) -> np.ndarray:
    out = np.full_like(logp, np.nan)
    fin = np.where(np.isfinite(logp))[0]
    if len(fin) < 3:
        return out
    seg = logp[fin[0]:fin[-1] + 1].copy()
    r = np.diff(seg)
    ok = np.isfinite(r)
    rr = r[ok]
    if kind == "shuffle":
        rr = rng.permutation(rr)
    else:
        rr = rng.normal(0.0, np.std(rr) if len(rr) > 1 else 0.01, size=len(rr))
    new = np.full(len(r), 0.0)
    new[ok] = rr
    path = seg[0] + np.concatenate([[0.0], np.cumsum(new)])
    path[~np.isfinite(seg)] = np.nan
    out[fin[0]:fin[-1] + 1] = path
    return out


def _pass_stats(sig, elig) -> dict:
    est = np.where(sig.is_est)[0]
    codes = sig.est_reason[est]
    el = elig[est]
    usable = el & ~np.isin(codes, [REASON_CODES["warmup"], REASON_CODES["halt"], REASON_CODES["short"]])
    ok = usable & (codes == REASON_CODES["ok"])
    consec = bool(np.any(ok[1:] & ok[:-1])) if len(ok) > 1 else False
    return dict(n_usable=int(usable.sum()), n_ok=int(ok.sum()),
                codes=np.bincount(codes[usable].astype(int), minlength=9), ever=bool(ok.any()),
                consec=consec, any_usable=bool(usable.any()),
                ok_days=est[ok])


def work(j: int) -> dict:
    P = G["panel"]
    t = P.tickers[j]
    o, h, l, c = P.o[:, j], P.h[:, j], P.l[:, j], P.c[:, j]
    logp = np.log(c)
    logb = G["logb_of"](t)
    halt = G["halt"][:, j]
    elig_asof = G["elig"][:, j]
    rng = np.random.default_rng(SEED + j)
    res = dict(j=j, ticker=t)
    s_resid = estimate_series(logp, logb, halt)
    s_price = estimate_series(logp, None, halt)
    res["pass"] = {"resid": _pass_stats(s_resid, elig_asof), "price": _pass_stats(s_price, elig_asof)}
    for kind in ("shuffle", "rw"):
        sp = _surrogate(logp, rng, kind)
        ss = estimate_series(sp, logb, np.zeros_like(halt) | ~np.isfinite(sp))
        res["pass"][kind] = _pass_stats(ss, elig_asof)
    okd = res["pass"]["resid"]["ok_days"]
    res["hl"] = (s_resid.hl[okd], s_resid.hl_adj[okd])
    # Leung 경계 — 날짜별 (그날 적용 중인 추정)
    lb_cache = {}

    def leung_by_day(r_annual, cost):
        key = (r_annual, cost)
        if key in lb_cache:
            return lb_cache[key]
        arr = [None] * len(c)
        cur = None
        fails = 0
        tried = 0
        for i in range(len(c)):
            if s_resid.is_est[i]:
                cur = None
                if s_resid.valid[i]:
                    tried += 1
                    cur = G["leung_grid"].bounds(s_resid.theta[i], s_resid.sigma_stat[i],
                                                 r_annual / 252.0, cost)
                    if cur is None:
                        fails += 1
            arr[i] = cur if s_resid.valid[i] else None
        lb_cache[key] = (arr, tried, fails)
        return lb_cache[key]

    elig_today = np.full(len(c), t in G["today"])
    trades = {}
    leung_fail = {}
    for key, mode, uni, rule in G["rules"]:
        sig = s_resid if mode == "resid" else s_price
        elig = elig_asof if uni in ("asof", "db") else elig_today
        lbd = None
        if rule.kind == "leung":
            r_ann = 0.10 if "|r10|" in key else R_ANNUAL
            lbd, tried, fails = leung_by_day(r_ann, rule.cost)
            leung_fail[key] = (tried, fails)
        tr = simulate_ticker(o, h, l, c, sig, elig, G["mu_exec"], rule, lbd)
        if tr:
            rows = [[j, x["ei"], x["xi"], x["sig_day"], x["entry_px"], x["exit_px"], x["gross"],
                     REASONS.index(x["reason"]), x["z_entry"], x["z_exit"], x["hl"], x["held"],
                     x["mae"], x["mfe"], x["mu"], P.o_raw[x["ei"], j]] for x in tr]
            trades[key] = np.array(rows, dtype=float)
    res["trades"] = trades
    res["leung_fail"] = leung_fail
    return res


def build_leung_grid(ctx, path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_workspace", "analysis", "mean_reversion_20261001",
                                             ".leung_grid_L-2.pkl")):
    """표준화 Leung 경계 격자 — 한 번 풀어 파일로 둔다(입력이 상수라 재현 가능)."""
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return LG.BoundsGrid(pickle.load(fh))
    pts = [(ia, ic) for ia in range(len(LG.GRID_A)) for ic in range(len(LG.GRID_CS))]
    with ctx.Pool(max(1, os.cpu_count() - 1)) as pool:
        vals = pool.map(LG.solve_grid_point, [(LG.GRID_A[ia], LG.GRID_CS[ic], -2.0) for ia, ic in pts])
    table = dict(zip(pts, vals))
    with open(path, "wb") as fh:
        pickle.dump(table, fh)
    return LG.BoundsGrid(table)


def mu_exec_series(closes: np.ndarray) -> np.ndarray:
    """체결일 d 의 시장 유닛 = classify(closes[:d]) — 직전 영업일 봉까지 (market_unit 규약)."""
    out = np.full(len(closes), np.nan)
    for d in range(len(closes)):
        cl, _why = classify(list(closes[:d]))
        if cl is not None:
            out[d] = cl.m
    return out


def prepare(segment: str, db_extract: "str | None", exclude_prov: bool = False):
    if segment == "archive":
        P = D.load_archive()
        idx = D.kospi_approx_index(P)
        logb_all = np.log(idx)
        G["logb_of"] = lambda t: logb_all
        mu = mu_exec_series(idx)
        excl = U.base_exclusions(P)
        elig = U.asof_mask(P)
        today = U.today_set(P)
        bench = {"kospi_approx": idx}
    else:
        ext = D.load_db_extract(db_extract)
        P = D.db_panel(ext)
        j200 = P.tickers.index("069500")
        jq = P.tickers.index("229200")
        lb200 = np.log(P.c[:, j200])
        lbq = np.log(P.c[:, jq])
        G["logb_of"] = lambda t: (lbq if P.market.get(t) == "KOSDAQ" else lb200)
        mu = mu_exec_series(P.c[:, j200])
        excl = U.base_exclusions(P, P.meta["group_code"])
        elig = np.ones(P.c.shape, dtype=bool)
        today = set(P.tickers)
        bench = {"069500": P.c[:, j200], "229200": P.c[:, jq]}
    halt = ~np.isfinite(P.c) | ~(np.nan_to_num(P.vol) > 0)
    jump = np.zeros_like(halt)
    jump[1:] = np.abs(P.c[1:] / P.c[:-1] - 1.0) > 0.30   # 가격제한 밖 = 미보정 기업행위
    halt |= jump
    prov = None
    if segment == "db":
        prov = D.provisional_close_flags(P)
        if exclude_prov:
            halt |= prov
    for t, why in excl.items():
        elig[:, P.tickers.index(t)] = False
    G.update(panel=P, mu_exec=mu, elig=elig, halt=halt, today=today,
             rules=build_rules(segment))
    return P, excl, bench, prov, jump


def main():
    stage, segment, out = sys.argv[1], sys.argv[2], sys.argv[3]
    db_extract = None
    sample = None
    exclude_prov = "--exclude-prov" in sys.argv
    if "--db-extract" in sys.argv:
        db_extract = sys.argv[sys.argv.index("--db-extract") + 1]
    if "--sample" in sys.argv:
        sample = int(sys.argv[sys.argv.index("--sample") + 1])
    t0 = time.time()
    P, excl, bench, prov, jump = prepare(segment, db_extract, exclude_prov)
    cols = [j for j, t in enumerate(P.tickers) if t not in excl]
    if sample:
        rng = np.random.default_rng(SEED)
        cols = sorted(rng.choice(cols, size=min(sample, len(cols)), replace=False).tolist())
    print(f"[{segment}] tickers={len(cols)} excluded={len(excl)} rules={len(G['rules'])} "
          f"prep={time.time() - t0:.1f}s", flush=True)
    ctx = mp.get_context("fork")
    G["leung_grid"] = build_leung_grid(ctx)
    results = []
    with ctx.Pool(max(1, os.cpu_count() - 1)) as pool:
        for k, r in enumerate(pool.imap_unordered(work, cols, chunksize=4)):
            results.append(r)
            if (k + 1) % 200 == 0:
                print(f"  {k + 1}/{len(cols)} {time.time() - t0:.0f}s", flush=True)
    results.sort(key=lambda r: r["j"])   # 작업자 완료 순서와 무관하게 같은 합산 순서 (부동소수 결정성)
    meta = dict(segment=segment, panel_meta={k: v for k, v in P.meta.items() if k not in ("chg", "group_code")},
                excluded=excl, n_cols=len(cols), sample=sample, seed=SEED,
                exclude_prov=exclude_prov, seconds=time.time() - t0,
                prov_flags=None if prov is None else dict(n=int(prov.sum()),
                                                          n_obs=int(np.isfinite(P.c).sum()),
                                                          by_day=prov.sum(axis=1).tolist()),
                jump_rows=int(jump.sum()))
    payload = dict(meta=meta, results=results, dates=P.dates, tickers=P.tickers,
                   market=P.market, mu_exec=G["mu_exec"], bench=bench, rules=[r[0] for r in G["rules"]])
    with open(out, "wb") as fh:
        pickle.dump(payload, fh)
    print(f"done {time.time() - t0:.0f}s → {out}")


if __name__ == "__main__":
    main()
