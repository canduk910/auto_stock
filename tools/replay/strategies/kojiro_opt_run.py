#!/usr/bin/env python3
"""kojiro 효율화 — 사전 등록(``strategy_opt_20261005/kojiro/prereg.frozen.md``) 그대로 실행.

순서: 데이터(전수 점검 ``kojiro_run.load_all`` — sha 대조 포함) → T 192조합 → 선택 → V 판정(J1 · P1~P5)
→ 축별 한계 효과(T·V) → H(부호) → 보고판(체결가 3판 · 섹터 캡 · 점수 순서).
출력: 스크래치 ``audit/kojiro_opt/result.json``.

실행: python tools/replay/strategies/kojiro_opt_run.py
"""
from __future__ import annotations

import itertools
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

from replay.audit import book as BK  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.audit.sizing import OpSizer  # noqa: E402
from replay.strategies import kojiro as KJ  # noqa: E402
from replay.strategies import kojiro_opt as KO  # noqa: E402
from replay.strategies import kojiro_run as KR  # noqa: E402
from src.engine.strategies.kojiro import KojiroStrategy  # noqa: E402

OUT = os.path.join(C.SCRATCH, "kojiro_opt")
T_WIN = ("2020-10-05", "2023-09-29")
TA_WIN = ("2020-10-05", "2022-03-31")
TB_WIN = ("2022-04-01", "2023-09-29")
V_WIN = ("2023-10-04", "2025-10-02")
H_WIN = C.H1Y
SLIP = 0.0076
SLIP_REPORT = (0.0, 0.0076, 0.0116)
MIN_TPY = 30
N_BOOT_J1 = 20000

GRID = {
    "mu": KO.MU_RULES,
    "band": (0.06, 0.045),
    "fresh": (5, 3),
    "rank": (None, 2),
    "be": (1.5, 0.0),
    "trail": (2.5, 3.5),
    "time_n": (None, 15),
}
CURRENT = {"mu": "cur", "band": 0.06, "fresh": 5, "rank": None, "be": 1.5, "trail": 2.5, "time_n": None}
T0 = time.time()


def log(*a):
    print(f"[kojiro-opt {time.time() - T0:6.0f}s]", *a, flush=True)


def cfg_name(c: dict) -> str:
    return (f"mu={c['mu']}|band={c['band']}|fresh={c['fresh']}|rank={c['rank'] or 'all'}|be={c['be']}"
            f"|trail={c['trail']}|time={c['time_n'] or '-'}")


def exit_cfg(c: dict) -> KO.ExitCfg:
    return KO.ExitCfg(be=c["be"], trail=c["trail"], time_n=c["time_n"])


def stats(pop, cal, cost=C.COST_RT_JUDGE, boot=True) -> dict:
    if not pop:
        return {"n": 0}
    r = [KJ.net_ret(x, cost) for x in pop]
    out = {"n": len(r), "mean": float(np.mean(r)), "win": float(np.mean(np.array(r) > 0)),
           "exit": dict(Counter(x.exit_reason for x in pop))}
    if boot:
        p1 = J.p1(r, [x.s.ticker for x in pop], [cal[x.s.gd].date() for x in pop])
        out.update({"lo90": p1["lo90"], "hi90": p1["hi90"], "P1_pass": p1["pass"]})
    return out


def week_key(cal, gd):
    y, w, _ = cal[gd].isocalendar()
    return f"{y}-W{w:02d}"


def paired_week_boot(pa, pb, cal, n_boot=N_BOOT_J1, seed=C.BOOT_SEED, qs=(0.05,)):
    """mean(a) − mean(b), 진입 주를 블록으로 두 판에서 같이 뽑는다."""
    ka = [week_key(cal, x.s.gd) for x in pa]
    kb = [week_key(cal, x.s.gd) for x in pb]
    weeks = sorted(set(ka) | set(kb))
    ix = {w: i for i, w in enumerate(weeks)}
    K = len(weeks)
    ra = np.array([KJ.net_ret(x, C.COST_RT_JUDGE) for x in pa])
    rb = np.array([KJ.net_ret(x, C.COST_RT_JUDGE) for x in pb])
    ia = np.array([ix[k] for k in ka])
    ib = np.array([ix[k] for k in kb])
    s1a, s0a = np.bincount(ia, ra, K), np.bincount(ia, None, K).astype(float)
    s1b, s0b = np.bincount(ib, rb, K), np.bincount(ib, None, K).astype(float)
    rng = np.random.default_rng(seed)
    diffs = []
    for chunk in range(0, n_boot, 2000):
        cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=min(2000, n_boot - chunk)).astype(float)
        da = (cnt @ s1a) / np.maximum(cnt @ s0a, 1e-12)
        db = (cnt @ s1b) / np.maximum(cnt @ s0b, 1e-12)
        diffs.append(da - db)
    d = np.concatenate(diffs)
    return {"diff": float(ra.mean() - rb.mean()), "weeks": K,
            **{f"q{q:g}": float(np.quantile(d, q)) for q in qs}}


def run_books_opt(sigs, st, feats, p, win, c, slip, *, mode="color", seeds=C.BOOK_SEEDS, gates_kw=None,
                  rank_order=False, p_gate=None):
    """전수 점검 ``run_books`` 와 같은 계좌, 포지션만 ``OptPos``(본전·샹들리에·시간 청산 축)."""
    pe = exit_cfg(c).params(p)
    sizer = OpSizer(KojiroStrategy, "kojiro", p, atr_keys=("atr",))
    sbg = defaultdict(list)
    for s in sigs:
        sbg[s.gd].append(KO.slip_sig(s, slip))
    if rank_order:
        for g in sbg:
            sbg[g].sort(key=lambda s: -s.score)
    runs = []
    for seed in seeds:
        g = KJ.Gates(p_gate or p, sizer, **(gates_kw or {}))

        def open_pos(s, q, g=g):
            ps = KO.OptPos(s, st.bars[s.ticker], feats[s.ticker], q, pe, mode=mode, time_n=c["time_n"])
            g.opened.append(ps)
            return ps
        kw = dict(start_equity=float(C.BUDGET_C7), cost_side=C.COST_RT_JUDGE / 2, max_pos=int(p["max_positions"]))
        if rank_order:
            with KR.no_shuffle():
                r = BK.run_book(sbg, open_pos, g.size, st.cal, win[0], win[1], seed, **kw)
        else:
            r = BK.run_book(sbg, open_pos, g.size, st.cal, win[0], win[1], seed, **kw)
        r["gate_hits"] = dict(g.hits)
        runs.append(r)
    sm = BK.book_summary(runs, float(C.BUDGET_C7))
    hits = Counter()
    for r in runs:
        hits.update(r["gate_hits"])
    keep = {k: sm[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median", "trades_median",
                               "fills_per_year_median", "unaffordable_ratio_median", "recon_max_abs")}
    keep["gate_hits_total"] = dict(hits)
    keep["counts_seed0"] = runs[0]["counts"]
    return keep, sm


def main():
    os.makedirs(OUT, exist_ok=True)
    ext, master, st, m_day, (kd, kc), meta = KR.load_all()
    cal = st.cal
    sc = {r[0]: r for r in [tuple(x) for x in ext["strategy_config"][1]]}
    row = dict(zip(ext["strategy_config"][0], sc["kojiro"]))
    p = KJ.op_params(row)
    sectors = KJ.sectors_from_master(ext["master"][0], ext["master"][1])
    res = {"meta": meta, "prereg_sha": open(os.path.join(KR._TOOLS, "..", "_workspace", "analysis",
                                                         "strategy_opt_20261005", "kojiro",
                                                         "prereg.md.sha256")).read().strip(),
           "params_current": {k: p[k] for k in ("atr_ratio_max", "stage1_freshness", "breakeven_promote_atr",
                                                "trail_atr", "stop_atr", "hard_stop_pct", "max_positions",
                                                "max_positions_per_sector", "max_open_risk_pct", "market_unit_mode",
                                                "sizing_mode", "position_ratio")}}
    univ = {t: KJ.universe(b, p) for t, b in st.bars.items()}
    feats_by, sigs_by = {}, {}
    for fresh in GRID["fresh"]:
        pf = {**p, "stage1_freshness": fresh}
        feats_by[fresh] = {t: KJ.features(b, pf) for t, b in st.bars.items()}
        for band in GRID["band"]:
            fb = {t: {**f, "tech": f["tech"] & (f["ratio"] <= band)} for t, f in feats_by[fresh].items()}
            sigs_by[(fresh, band)], cnt = KJ.build_signals(st.bars, fb, univ, m_day, {**pf, "atr_ratio_max": band},
                                                           sectors)
            log("signals", fresh, band, len(sigs_by[(fresh, band)]), cnt)
    feats = feats_by[5]                     # 경로 재료(ATR·스테이지)는 신선도·밴드와 무관
    memo = KO.PathMemo(st.bars, feats, p)
    G = {nm: KR.gd_range(cal, w) for nm, w in (("T", T_WIN), ("Ta", TA_WIN), ("Tb", TB_WIN), ("V", V_WIN),
                                              ("H", H_WIN))}
    t_years = (G["T"][1] - G["T"][0] + 1) / 252.0
    res["windows"] = {k: [str(cal[a].date()), str(cal[b].date())] for k, (a, b) in G.items()}

    def sigs_of(c):
        return KO.select(sigs_by[(c["fresh"], c["band"])], c["mu"], c["rank"])

    def pop(c, win, slip=SLIP, mode="color"):
        g0, g1 = G[win]
        return KO.population_memo(sigs_of(c), memo, exit_cfg(c), g0, g1, slip, mode)

    # ── T: 192조합 ──────────────────────────────────────────────────────
    keys = list(GRID)
    combos = [dict(zip(keys, v)) for v in itertools.product(*(GRID[k] for k in keys))]
    assert len(combos) == 192
    table = []
    for i, c in enumerate(combos):
        pt = pop(c, "T")
        s = stats(pt, cal)
        # 하위 구간 = T 경로 그대로에서 진입일로 나눈다
        ra = [KJ.net_ret(x, C.COST_RT_JUDGE) for x in pt if x.s.gd <= G["Ta"][1]]
        rb = [KJ.net_ret(x, C.COST_RT_JUDGE) for x in pt if x.s.gd >= G["Tb"][0]]
        s.update({"name": cfg_name(c), "cfg": c, "tpy": s["n"] / t_years,
                  "Ta_mean": float(np.mean(ra)) if ra else None, "Ta_n": len(ra),
                  "Tb_mean": float(np.mean(rb)) if rb else None, "Tb_n": len(rb)})
        s["eligible"] = s["tpy"] >= MIN_TPY
        s["robust"] = bool(ra and rb and s["Ta_mean"] > 0 and s["Tb_mean"] > 0)
        table.append(s)
        if i % 24 == 0:
            log("T", i, s["name"], round(s["mean"], 5), round(s["lo90"], 5))
    elig = [r for r in table if r["eligible"]]
    rob = [r for r in elig if r["robust"]]
    pool = rob if rob else elig
    chosen = max(pool, key=lambda r: (r["lo90"], r["mean"]))
    cur_row = next(r for r in table if r["cfg"] == CURRENT)
    res["T"] = {"n_combos": len(table), "n_eligible": len(elig), "n_robust": len(rob), "t_years": t_years,
                "chosen": chosen, "chosen_robust": bool(rob), "current": cur_row,
                "top10": sorted(elig, key=lambda r: (-r["lo90"], -r["mean"]))[:10],
                "rank_of_current": 1 + sorted(table, key=lambda r: (-r["lo90"], -r["mean"])).index(cur_row)}
    log("chosen", chosen["name"], chosen["mean"], chosen["lo90"], "robust", bool(rob))
    cc = chosen["cfg"]

    # ── V 판정 ─────────────────────────────────────────────────────────
    pv_c, pv_0 = pop(cc, "V"), pop(CURRENT, "V")
    J1 = paired_week_boot(pv_c, pv_0, cal, qs=(0.05, 0.05 / 192))
    J1["pass"] = bool(J1["diff"] > 0 and J1["q0.05"] > 0)
    J1["pass_bonferroni"] = bool(J1["diff"] > 0 and J1[f"q{0.05 / 192:g}"] > 0)
    V = {"J1": J1}
    for nm, c, pv in (("chosen", cc, pv_c), ("current", CURRENT, pv_0)):
        sv = stats(pv, cal)
        adv = pop(c, "V", mode="adverse")
        sva = stats(adv, cal, boot=False)
        book, sm = run_books_opt(sigs_of(c), st, feats, p, V_WIN, c, SLIP)
        bookA, smA = run_books_opt(sigs_of(c), st, feats, p, V_WIN, c, SLIP, mode="adverse")
        V[nm] = {"pop": sv, "P1": J.p1([KJ.net_ret(x, C.COST_RT_JUDGE) for x in pv], [x.s.ticker for x in pv],
                                        [cal[x.s.gd].date() for x in pv]),
                 "P5": J.p5(sv["mean"], sva["mean"]), "pop_adverse": sva, "book": book, "P3": J.p3(sm),
                 "P4": J.p4(sm), "book_adverse": {k: bookA[k] for k in ("cagr_median", "mdd_median")},
                 "P3_adverse": J.p3(smA),
                 "overfit_T_minus_V": (chosen if nm == "chosen" else cur_row)["mean"] - sv["mean"]}
        log("V", nm, sv["mean"], V[nm]["P1"]["label"], book["cagr_median"], book["mdd_median"])
    res["V"] = V
    log("J1", J1)

    # ── 축별 한계 효과(현행에서 한 축만) — T·V ────────────────────────────
    marg = {}
    for k in keys:
        for v in GRID[k]:
            if v == CURRENT[k]:
                continue
            c = {**CURRENT, k: v}
            marg[f"{k}={v}"] = {"T": stats(pop(c, "T"), cal), "V": stats(pop(c, "V"), cal)}
    marg["current"] = {"T": stats(pop(CURRENT, "T"), cal), "V": V["current"]["pop"]}
    res["marginal"] = marg
    # 「m=1 만」 사후 가설 — 현행판 모집단을 m 칸으로 나눈 T·V 평균
    mcell = {}
    for win in ("T", "V"):
        pc = pop(CURRENT, win)
        for mv in (1.0, 0.75, 0.5):
            r = [KJ.net_ret(x, C.COST_RT_JUDGE) for x in pc if x.s.m == mv]
            mcell[f"{win}|m={mv}"] = {"n": len(r), "mean": float(np.mean(r)) if r else None}
    res["mu_cells_current"] = mcell
    log("marginal done")

    # ── H(부호만) ──────────────────────────────────────────────────────
    Hres = {}
    for nm, c in (("chosen", cc), ("current", CURRENT)):
        ph = pop(c, "H")
        sh = stats(ph, cal, boot=False)
        bk, smh = run_books_opt(sigs_of(c), st, feats, p, H_WIN, c, SLIP)
        Hres[nm] = {"pop": sh, "P2": J.p2([KJ.net_ret(x, C.COST_RT_JUDGE) for x in ph], V[nm]["pop"]["mean"]),
                    "book": {k: bk[k] for k in ("cagr_median", "mdd_median", "trades_median")}}
    res["H"] = Hres
    log("H", {k: (v["pop"].get("mean"), v["book"]["cagr_median"]) for k, v in Hres.items()})

    # ── 보고판 ─────────────────────────────────────────────────────────
    rep = {"slip": {}, "sector_cap_V": {}, "rank_order_V": {}}
    for nm, c in (("chosen", cc), ("current", CURRENT)):
        for sl in SLIP_REPORT:
            rep["slip"][f"{nm}|{sl}"] = {w: stats(pop(c, w, slip=sl), cal, boot=False).get("mean") for w in ("T", "V", "H")}
        bk, _ = run_books_opt(sigs_of(c), st, feats, p, V_WIN, c, SLIP, seeds=(0,), rank_order=True)
        rep["rank_order_V"][nm] = {k: bk[k] for k in ("cagr_median", "mdd_median", "trades_median")}
    for lab, kw, pg in (("cap1", None, {**p, "max_positions_per_sector": 1}), ("cap2", None, None),
                        ("off", {"sector_cap": False}, None)):
        bk, _ = run_books_opt(sigs_of(cc), st, feats, p, V_WIN, cc, SLIP, gates_kw=kw, p_gate=pg)
        rep["sector_cap_V"][lab] = {k: bk[k] for k in ("cagr_median", "mdd_median", "trades_median", "gate_hits_total")}
    # 현행판 T 계좌(과적합 진단 보조)
    for nm, c in (("chosen", cc), ("current", CURRENT)):
        bk, _ = run_books_opt(sigs_of(c), st, feats, p, (T_WIN[0], T_WIN[1]), c, SLIP)
        rep[f"book_T_{nm}"] = {k: bk[k] for k in ("cagr_median", "mdd_median", "trades_median")}
    res["report"] = rep
    res["elapsed_s"] = time.time() - T0
    with open(os.path.join(OUT, "result.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=KR._js)
    log("written", os.path.join(OUT, "result.json"))


if __name__ == "__main__":
    main()
