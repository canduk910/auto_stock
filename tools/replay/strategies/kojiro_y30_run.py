#!/usr/bin/env python3
"""kojiro 30년 재검증 — 사전 등록(``strategy_30y_20261006/kojiro/prereg.frozen.md``) 그대로 실행.

순서: 데이터(30년 보관소 · DB 추출본 sha 대조) → 지표·신호 → 자기 검증 → A(현행 규칙: T·V·H·시대, 두 체결가 판,
보고판) → B(T 192조합 → 선택 → V 판정 → H). 출력 = 스크래치 ``audit/kojiro_y30/result.json``.

실행: python tools/replay/strategies/kojiro_y30_run.py [--only A|B] [--sample N]   (--sample = 연기 시험)
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

from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.audit import market_unit as MU  # noqa: E402
from replay.audit import panel as PN  # noqa: E402
from replay.audit.sizing import OpSizer  # noqa: E402
from replay.strategies import kojiro as KJ  # noqa: E402
from replay.strategies import kojiro_opt as KO  # noqa: E402
from replay.strategies import kojiro_opt_run as KOR  # noqa: E402
from replay.strategies import kojiro_run as KR  # noqa: E402
from replay.strategies import kojiro_y30 as Y  # noqa: E402
from src.engine.etf_like import is_etf_like  # noqa: E402
from src.engine.strategies.kojiro import KojiroStrategy  # noqa: E402

OUT = os.path.join(C.SCRATCH, "kojiro_y30")
PREREG_SHA = os.path.join(KR._TOOLS, "..", "_workspace", "analysis", "strategy_30y_20261006", "kojiro",
                          "prereg.md.sha256")
SLIP = 0.0076
FILLS = (0.0, SLIP)
MIN_TPY = 30
GRID = KOR.GRID
CURRENT = KOR.CURRENT
T0 = time.time()


def log(*a):
    print(f"[kojiro-y30 {time.time() - T0:6.0f}s]", *a, flush=True)


def _js(o):
    return KR._js(o)


# ── 준비 ─────────────────────────────────────────────────────────────────

def prepare(sample: "int | None" = None):
    Y.patch_fast_ewm()
    got = PN.sha256(C.DB_EXTRACT)
    if got != KR.EXTRACT_SHA:
        raise SystemExit(f"[kojiro-y30] 추출본 sha 불일치 {got}")
    ext = PN.load_db_extract()
    row = dict(zip(ext["strategy_config"][0], {r[0]: r for r in ext["strategy_config"][1]}["kojiro"]))
    p = KJ.op_params(row)
    sectors = KJ.sectors_from_master(ext["master"][0], ext["master"][1])
    df, meta = Y.load_unified(drop_flags=False)
    if sample:                      # 연기 시험 전용 — 종목 일부(백분위는 전체 횡단면에서 이미 계산)
        keep = sorted(df.ticker.unique())[::max(1, df.ticker.nunique() // sample)]
        df = df[df.ticker.isin(set(keep))]
        meta["SAMPLE"] = len(keep)
    etf_names = sorted(n for n in df.name.dropna().unique() if is_etf_like(None, n))
    meta["etf_like_names"] = len(etf_names)
    if etf_names:
        df = df[~df.name.isin(etf_names)]
    cal = pd.DatetimeIndex(sorted(df.bas_dd.unique()))
    flag_tickers = set(df.ticker[df.flag].unique())
    st = Y.build(df[~df.flag], cal=cal)
    st_fk = Y.build(df[df.ticker.isin(flag_tickers)], cal=cal, tickers=flag_tickers)
    meta["flag_tickers"] = len(flag_tickers)
    log("store", st.meta, meta)
    del df
    kd, kc = Y.mu_series()
    m_day = MU.m_for_days(cal, kd, kc)
    meta["m_nan_days"] = int(np.isnan(m_day).sum())
    feats_by = {}
    for fresh in GRID["fresh"]:
        pf = {**p, "stage1_freshness": fresh}
        feats_by[fresh] = {t: KJ.features(b, pf) for t, b in st.bars.items()}
        log("features", fresh, len(feats_by[fresh]))
    feats_fk = {t: KJ.features(b, p) for t, b in st_fk.bars.items()}
    univ = {t: Y.universe_era(b) for t, b in st.bars.items()}
    univ_nom = {t: KJ.universe(b, p) for t, b in st.bars.items()}
    univ_fk = {t: Y.universe_era(b) for t, b in st_fk.bars.items()}
    sigs_by, cnts = {}, {}
    for fresh in GRID["fresh"]:
        pf = {**p, "stage1_freshness": fresh}
        for band in GRID["band"]:
            fb = {t: {**f, "tech": f["tech"] & (f["ratio"] <= band)} for t, f in feats_by[fresh].items()}
            sigs_by[(fresh, band)], cnts[f"{fresh}|{band}"] = KJ.build_signals(
                st.bars, fb, univ, m_day, {**pf, "atr_ratio_max": band}, sectors)
            log("signals", fresh, band, len(sigs_by[(fresh, band)]), cnts[f"{fresh}|{band}"])
    sigs_nom, cnt_nom = KJ.build_signals(st.bars, feats_by[5], univ_nom, m_day, p, sectors)
    # 표시 행 남긴 판: 표시 종목만 바꿔 끼운다
    bars_fk = {**st.bars, **st_fk.bars}
    feats_fk_all = {**feats_by[5], **feats_fk}
    univ_fk_all = {**univ, **univ_fk}
    sigs_fk, cnt_fk = KJ.build_signals(bars_fk, feats_fk_all, univ_fk_all, m_day, p, sectors)
    meta.update({"signal_counts": cnts, "signal_counts_nominal": cnt_nom, "signal_counts_flags_kept": cnt_fk,
                 "store": st.meta})
    return dict(p=p, sectors=sectors, st=st, cal=cal, kd=kd, kc=kc, m_day=m_day, feats_by=feats_by, univ=univ,
                univ_nom=univ_nom, sigs_by=sigs_by, sigs_nom=sigs_nom, bars_fk=bars_fk, feats_fk_all=feats_fk_all,
                univ_fk_all=univ_fk_all, sigs_fk=sigs_fk, meta=meta)


# ── 공통 ─────────────────────────────────────────────────────────────────

def stats(pop, cal, cost, boot=True) -> dict:
    if not pop:
        return {"n": 0}
    r = np.array([Y.net(x, cost) for x in pop])
    reasons = Counter(x.exit_reason for x in pop)
    srt = np.sort(r)
    k1 = max(1, int(round(len(r) * 0.01)))
    out = {"n": len(r), "mean": float(r.mean()), "median": float(np.median(r)), "win": float((r > 0).mean()),
           "mean_ex_top1pct": float(srt[:-k1].mean()) if len(r) > k1 else None, "exit": dict(reasons)}
    if boot:
        p1 = J.p1(r, [x.s.ticker for x in pop], [cal[x.s.gd].date() for x in pop])
        out.update({"lo90": p1["lo90"], "hi90": p1["hi90"], "P1_pass": p1["pass"]})
    return out


def run_books(sigs, st_bars, feats, p, cal, win, cost, *, slip=0.0, c=None, mode="color", seeds=C.BOOK_SEEDS):
    c = c or CURRENT
    pe = KOR.exit_cfg(c).params(p)
    sizer = OpSizer(KojiroStrategy, "kojiro", p, atr_keys=("atr",))
    sbg = defaultdict(list)
    g0, g1 = Y.gd_range(cal, win)
    for s in sigs:
        if g0 <= s.gd <= g1:
            sbg[s.gd].append(KO.slip_sig(s, slip))
    runs = []
    for seed in seeds:
        g = Y.Gates30(p, sizer)

        def open_pos(s, q, g=g):
            ps = Y.Y30Pos(s, st_bars[s.ticker], feats[s.ticker], q, pe, mode=mode, time_n=c["time_n"])
            g.opened.append(ps)
            return ps
        r = Y.run_book30(sbg, open_pos, g.size, cal, win[0], win[1], seed, start_equity=float(C.BUDGET_C7),
                         cost=cost, max_pos=int(p["max_positions"]))
        r["gate_hits"] = dict(g.hits)
        runs.append(r)
    sm = Y.summary30(runs, float(C.BUDGET_C7), cal)
    hits = Counter()
    for r in runs:
        hits.update(r["gate_hits"])
    sm["gate_hits_total"] = dict(hits)
    tr0 = runs[0]["trades"]
    sm["exit_seed0"] = dict(Counter(x.exit_reason for x in tr0))
    q = [x.qty for x in tr0]
    sm["lot_seed0"] = {"qty_median": float(np.median(q)) if q else None,
                       "one_share": float(np.mean(np.array(q) == 1)) if q else None,
                       "won_median": float(np.median([x.cost_basis for x in tr0])) if tr0 else None,
                       "over_1pct_tv": float(np.mean([x.cost_basis > 0.01 * float(st_bars[x.s.ticker]["tv"][x.s.ti] or 0)
                                                      for x in tr0])) if tr0 else None}
    eq, dates = runs[0]["equity"], runs[0]["dates"]
    yr, prev = {}, float(C.BUDGET_C7)
    for y in sorted(set(d.year for d in dates)):
        last = float(eq[np.array([d.year == y for d in dates])][-1])
        yr[str(y)] = last / prev - 1
        prev = last
    sm["year_return_seed0"] = yr
    return sm


def self_check(st, feats, univ, p, n=400, seed=C.BOOT_SEED):
    """운영 ``enrich`` 판정 ↔ 벡터 재현(무작위 후보 n · 비후보 n)."""
    from src.engine.kojiro_indicators import KojiroIndicatorConfig, enrich
    from src.engine.strategies.kojiro import _stage_recently
    rng = np.random.default_rng(seed)
    cfg = KojiroIndicatorConfig(ema_short=p["ema_short"], ema_mid=p["ema_mid"], ema_long=p["ema_long"],
                                macd_signal=p["macd_signal"], atr_period=p["atr_period"],
                                slope_lookback=p["slope_lookback"])

    def op(b, i):
        s = max(0, i - KJ.WINDOW + 1)
        df = pd.DataFrame({"open": b["o"][s:i + 1], "high": b["h"][s:i + 1], "low": b["l"][s:i + 1],
                           "close": b["c"][s:i + 1], "volume": np.ones(i + 1 - s)})
        en = enrich(df, cfg)
        last = en.iloc[-1]
        pc = int(last["close"])
        if pc <= 0:
            return False
        r = float(last["atr"]) / pc
        return bool(i + 1 - s >= KJ.MIN_BARS and p["atr_ratio_min"] <= r <= p["atr_ratio_max"] and last["stage"] == 1
                    and bool(last["ema_s_up"] and last["ema_m_up"] and last["ema_l_up"])
                    and _stage_recently(en["stage"].tolist(), 6, 1, within=int(p["stage1_freshness"]))
                    and pc > float(last["ema_s"]))
    pos = [(t, int(i)) for t, f in feats.items() for i in np.nonzero(f["tech"])[0]]
    pick = [pos[k] for k in rng.choice(len(pos), size=min(n, len(pos)), replace=False)]
    tick = [t for t in feats if len(st.bars[t]["c"]) >= KJ.MIN_BARS]
    neg = []
    while len(neg) < n:
        t = tick[rng.integers(len(tick))]
        i = int(rng.integers(KJ.MIN_BARS - 1, len(st.bars[t]["c"])))
        if not feats[t]["tech"][i]:
            neg.append((t, i))
    pb = [(t, i) for t, i in pick if not op(st.bars[t], i)]
    nb = [(t, i) for t, i in neg if op(st.bars[t], i)]
    return {"pos_total": len(pos), "pos_checked": len(pick), "pos_mismatch": len(pb), "neg_checked": len(neg),
            "neg_mismatch": len(nb), "examples": [(t, str(st.cal[st.bars[t]["di"][i]].date())) for t, i in (pb + nb)[:10]]}


def random_control(st, feats, univ, pop, p, cal, end_gd, cost, seed=C.BOOT_SEED):
    """같은 진입일 · 같은 유니버스(80봉 · ATR>0 · 다음 날 거래)에서 종목만 무작위, 같은 청산."""
    rng = np.random.default_rng(seed)
    tick = sorted(st.bars)
    E = np.full((len(tick), len(cal)), -1, dtype=np.int32)
    for k, t in enumerate(tick):
        b, f = st.bars[t], feats[t]
        ok = univ[t] & (f["nbars"] >= KJ.MIN_BARS) & np.isfinite(f["atr"]) & (f["atr"] > 0)
        i = np.nonzero(ok[:-1])[0]
        D = i + 1
        good = (b["di"][D] == b["di"][i] + 1) & ~b["notrade"][D] & (b["o"][D] > 0)
        E[k, b["di"][D[good]]] = D[good]
    pe = KOR.exit_cfg(CURRENT).params(p)
    out = []
    for x in pop:
        cand = np.nonzero(E[:, x.s.gd] >= 0)[0]
        if not len(cand):
            continue
        k = cand[rng.integers(len(cand))]
        t, D = tick[k], int(E[k, x.s.gd])
        b = st.bars[t]
        s = KJ.Sig(t, D, int(b["di"][D]), float(b["o"][D]), float(b["o"][D] * b["raw"][D]),
                   float(feats[t]["atr"][D - 1]), x.s.m)
        out.append(Y.run_path(s, b, feats[t], pe, end_gd))
    r = np.array([Y.net(x, cost) for x in out])
    real = np.array([Y.net(x, cost) for x in pop])
    return {"n": len(r), "mean": float(r.mean()) if len(r) else None, "real_mean": float(real.mean()),
            "diff_real_minus_random": float(real.mean() - r.mean()) if len(r) else None}


# ── A ────────────────────────────────────────────────────────────────────

def part_a(D, cost_era, cost_c):
    p, st, cal = D["p"], D["st"], D["cal"]
    feats = D["feats_by"][5]
    sigs = KO.select(D["sigs_by"][(5, 0.06)], "cur", None)
    memo = Y.PathMemo(st.bars, feats, p)
    cfg = KOR.exit_cfg(CURRENT)
    wins = {"T": Y.T_WIN, "Ta": Y.TA_WIN, "Tb": Y.TB_WIN, "V": Y.V_WIN, "H": Y.H_WIN, **Y.ERAS}
    A = {"windows": {}, "baselines": {}}
    for nm, w in wins.items():
        g0, g1 = Y.gd_range(cal, w)
        A["baselines"][nm] = Y.baselines(D["kd"], D["kc"], w)
        row = {"range": [str(cal[g0].date()), str(cal[g1].date())], "years": Y.cal_years(cal, g0, g1)}
        for slip in FILLS:
            pop = Y.population(sigs, memo, cfg, g0, g1, slip)
            popA = Y.population(sigs, memo, cfg, g0, g1, slip, "adverse")
            s = stats(pop, cal, cost_era)
            sa = stats(popA, cal, cost_era, boot=False)
            row[f"fill{slip}"] = {"pop": s, "pop_const038": stats(pop, cal, cost_c, boot=False),
                                  "P1": {"pass": s.get("P1_pass"), "mean": s.get("mean"), "lo90": s.get("lo90")},
                                  "P5": J.p5(s["mean"], sa["mean"]) if s.get("n") else None,
                                  "adverse_mean": sa.get("mean"),
                                  "m_cells": {str(mv): stats([x for x in pop if x.s.m == mv], cal, cost_era, boot=False)
                                              for mv in (1.0, 0.75, 0.5)}}
            if nm not in ("Ta", "Tb"):
                bk = run_books(sigs, st.bars, feats, p, cal, w, cost_era, slip=slip)
                row[f"fill{slip}"]["book"] = bk
                row[f"fill{slip}"]["P3"] = J.p3(bk)
                row[f"fill{slip}"]["P4"] = J.p4(bk)
            log("A", nm, slip, s.get("n"), s.get("mean"), s.get("lo90"),
                row[f"fill{slip}"].get("book", {}).get("cagr_median"), row[f"fill{slip}"].get("book", {}).get("mdd_median"))
        A["windows"][nm] = row
    # 보고판
    rep = {}
    for nm, w in (("T", Y.T_WIN), ("V", Y.V_WIN), ("H", Y.H_WIN)):
        g0, g1 = Y.gd_range(cal, w)
        pop = Y.population(sigs, memo, cfg, g0, g1, 0.0)
        bk = run_books(sigs, st.bars, feats, p, cal, w, cost_c)
        memo_n = Y.PathMemo(st.bars, feats, p)
        pn = Y.population(KO.select(D["sigs_nom"], "cur", None), memo_n, cfg, g0, g1, 0.0)
        memo_f = Y.PathMemo(D["bars_fk"], D["feats_fk_all"], p)
        pf = Y.population(KO.select(D["sigs_fk"], "cur", None), memo_f, cfg, g0, g1, 0.0)
        rep[nm] = {"book_const038": {k: bk[k] for k in ("cagr_median", "mdd_median", "trades_median")},
                   "nominal_universe": stats(pn, cal, cost_era),
                   "flags_kept": stats(pf, cal, cost_era, boot=False),
                   "random_control": random_control(st, feats, D["univ"], pop, p, cal, g1, cost_era),
                   "no_market_unit": stats(Y.population([KJ.Sig(**{**s.__dict__, "m": 1.0}) for s in sigs],
                                                        Y.PathMemo(st.bars, feats, p), cfg, g0, g1, 0.0),
                                           cal, cost_era, boot=False)}
        log("A rep", nm, rep[nm]["nominal_universe"].get("mean"), rep[nm]["flags_kept"].get("mean"),
            rep[nm]["random_control"])
    # 5년 창 맞대기(5년 점검 = 시가 · 0.38% · 명목 유니버스 · n 10,027 · −0.092%)
    g0, g1 = Y.gd_range(cal, C.W5Y)
    p5y = Y.population(KO.select(D["sigs_nom"], "cur", None), Y.PathMemo(st.bars, feats, p), cfg, g0, g1, 0.0)
    rep["w5y_check"] = stats(p5y, cal, cost_c)
    rep["w5y_check_era_universe"] = stats(Y.population(sigs, memo, cfg, g0, g1, 0.0), cal, cost_c, boot=False)
    log("w5y check", rep["w5y_check"])
    # 연도별(현행 · 시가 · 시기별 비용)
    gT0, _ = Y.gd_range(cal, Y.T_WIN)
    _, gH1 = Y.gd_range(cal, Y.H_WIN)
    by = defaultdict(list)
    for x in Y.population(sigs, memo, cfg, gT0, gH1, 0.0):
        by[cal[x.s.gd].year].append(Y.net(x, cost_era))
    rep["by_year_fill0"] = {str(y): {"n": len(v), "mean": float(np.mean(v))} for y, v in sorted(by.items())}
    A["report"] = rep
    return A


# ── B ────────────────────────────────────────────────────────────────────

def part_b(D, cost_era, cost_c):
    p, st, cal = D["p"], D["st"], D["cal"]
    feats = D["feats_by"][5]
    memo = Y.PathMemo(st.bars, feats, p)
    G = {nm: Y.gd_range(cal, w) for nm, w in (("T", Y.T_WIN), ("Ta", Y.TA_WIN), ("Tb", Y.TB_WIN), ("V", Y.V_WIN),
                                              ("H", Y.H_WIN))}
    t_years = Y.cal_years(cal, *G["T"])

    def sigs_of(c):
        return KO.select(D["sigs_by"][(c["fresh"], c["band"])], c["mu"], c["rank"])

    def pop(c, win, slip=SLIP, mode="color"):
        g0, g1 = G[win]
        return Y.population(sigs_of(c), memo, KOR.exit_cfg(c), g0, g1, slip, mode)

    keys = list(GRID)
    combos = [dict(zip(keys, v)) for v in itertools.product(*(GRID[k] for k in keys))]
    assert len(combos) == 192
    table = []
    for i, c in enumerate(combos):
        pt = pop(c, "T")
        s = stats(pt, cal, cost_era)
        s_c = stats(pt, cal, cost_c)
        ra = [Y.net(x, cost_era) for x in pt if x.s.gd <= G["Ta"][1]]
        rb = [Y.net(x, cost_era) for x in pt if x.s.gd >= G["Tb"][0]]
        s.update({"name": KOR.cfg_name(c), "cfg": c, "tpy": s["n"] / t_years,
                  "Ta_mean": float(np.mean(ra)) if ra else None, "Ta_n": len(ra),
                  "Tb_mean": float(np.mean(rb)) if rb else None, "Tb_n": len(rb),
                  "const038_mean": s_c.get("mean"), "const038_lo90": s_c.get("lo90")})
        s["eligible"] = s["tpy"] >= MIN_TPY
        s["robust"] = bool(ra and rb and s["Ta_mean"] > 0 and s["Tb_mean"] > 0)
        table.append(s)
        if i % 12 == 0:
            log("T", i, s["name"], round(s["mean"], 5), round(s["lo90"], 5), "Ta", s["Ta_mean"], "Tb", s["Tb_mean"])
    elig = [r for r in table if r["eligible"]]
    rob = [r for r in elig if r["robust"]]
    pool = rob if rob else elig
    chosen = max(pool, key=lambda r: (r["lo90"], r["mean"]))
    chosen_c = max(elig, key=lambda r: (r["const038_lo90"], r["const038_mean"]))
    cur_row = next(r for r in table if r["cfg"] == CURRENT)
    order = sorted(table, key=lambda r: (-r["lo90"], -r["mean"]))
    B = {"t_years": t_years, "n_combos": len(table), "n_eligible": len(elig), "n_robust": len(rob),
         "n_T_mean_pos": sum(1 for r in table if r["mean"] > 0), "chosen": chosen, "chosen_robust": bool(rob),
         "chosen_const038_same": chosen_c["name"] == chosen["name"], "chosen_const038": chosen_c["name"],
         "current": cur_row, "rank_of_current": 1 + order.index(cur_row), "top10": order[:10],
         "robust_list": [r["name"] for r in rob]}
    log("chosen", chosen["name"], chosen["mean"], chosen["lo90"], "robust", bool(rob), "n_robust", len(rob))
    cc = chosen["cfg"]

    # V 판정
    pv_c, pv_0 = pop(cc, "V"), pop(CURRENT, "V")
    J1 = paired_week_boot(pv_c, pv_0, cal, cost_era)
    J1["pass"] = bool(J1["diff"] > 0 and J1["q0.05"] > 0)
    J1["pass_bonferroni"] = bool(J1["diff"] > 0 and J1[f"q{0.05 / 192:g}"] > 0)
    V = {"J1": J1}
    for nm, c, pv in (("chosen", cc, pv_c), ("current", CURRENT, pv_0)):
        sv = stats(pv, cal, cost_era)
        sva = stats(pop(c, "V", mode="adverse"), cal, cost_era, boot=False)
        bk = run_books(sigs_of(c), st.bars, feats, p, cal, Y.V_WIN, cost_era, slip=SLIP, c=c)
        bkA = run_books(sigs_of(c), st.bars, feats, p, cal, Y.V_WIN, cost_era, slip=SLIP, c=c, mode="adverse")
        V[nm] = {"pop": sv, "pop_const038": stats(pv, cal, cost_c, boot=False), "P5": J.p5(sv["mean"], sva["mean"]),
                 "book": {k: bk[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median", "trades_median",
                                             "fills_per_year_median", "unaffordable_ratio_median", "recon_max_abs",
                                             "gate_hits_total")},
                 "P3": J.p3(bk), "P4": J.p4(bk), "P3_adverse": J.p3(bkA),
                 "T_minus_V": (chosen if nm == "chosen" else cur_row)["mean"] - sv["mean"]}
        log("V", nm, sv["mean"], sv.get("lo90"), bk["cagr_median"], bk["mdd_median"])
    B["V"] = V
    log("J1", J1)
    # 축별 한계 효과
    marg = {}
    for k in keys:
        for v in GRID[k]:
            if v == CURRENT[k]:
                continue
            c = {**CURRENT, k: v}
            marg[f"{k}={v}"] = {w: stats(pop(c, w), cal, cost_era, boot=False).get("mean") for w in ("T", "V")}
    B["marginal"] = marg
    # H(부호만) + 시대별
    Hres = {}
    for nm, c in (("chosen", cc), ("current", CURRENT)):
        ph = pop(c, "H")
        sh = stats(ph, cal, cost_era, boot=False)
        bk = run_books(sigs_of(c), st.bars, feats, p, cal, Y.H_WIN, cost_era, slip=SLIP, c=c)
        Hres[nm] = {"pop": sh, "P2_sign_vs_V": J.p2([Y.net(x, cost_era) for x in ph], V[nm]["pop"]["mean"]),
                    "book": {k: bk[k] for k in ("cagr_median", "mdd_median", "trades_median")}}
        eras = {}
        for en, w in Y.ERAS.items():
            g0, g1 = Y.gd_range(cal, w)
            pe = Y.population(sigs_of(c), memo, KOR.exit_cfg(c), g0, g1, SLIP)
            eras[en] = stats(pe, cal, cost_era, boot=False).get("mean")
        Hres[nm]["eras"] = eras
    B["H"] = Hres
    log("H", {k: (v["pop"].get("mean"), v["book"]["cagr_median"]) for k, v in Hres.items()})
    return B


def week_key(cal, gd):
    y, w, _ = cal[gd].isocalendar()
    return f"{y}-W{w:02d}"


def paired_week_boot(pa, pb, cal, cost, n_boot=20000, seed=C.BOOT_SEED, qs=(0.05, 0.05 / 192)):
    ka = [week_key(cal, x.s.gd) for x in pa]
    kb = [week_key(cal, x.s.gd) for x in pb]
    weeks = sorted(set(ka) | set(kb))
    ix = {w: i for i, w in enumerate(weeks)}
    K = len(weeks)
    ra = np.array([Y.net(x, cost) for x in pa])
    rb = np.array([Y.net(x, cost) for x in pb])
    ia = np.array([ix[k] for k in ka])
    ib = np.array([ix[k] for k in kb])
    s1a, s0a = np.bincount(ia, ra, K), np.bincount(ia, None, K).astype(float)
    s1b, s0b = np.bincount(ib, rb, K), np.bincount(ib, None, K).astype(float)
    rng = np.random.default_rng(seed)
    diffs = []
    for chunk in range(0, n_boot, 2000):
        cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=min(2000, n_boot - chunk)).astype(float)
        diffs.append((cnt @ s1a) / np.maximum(cnt @ s0a, 1e-12) - (cnt @ s1b) / np.maximum(cnt @ s0b, 1e-12))
    d = np.concatenate(diffs)
    return {"diff": float(ra.mean() - rb.mean()), "weeks": K, **{f"q{q:g}": float(np.quantile(d, q)) for q in qs}}


def main():
    os.makedirs(OUT, exist_ok=True)
    sample = int(sys.argv[sys.argv.index("--sample") + 1]) if "--sample" in sys.argv else None
    D = prepare(sample)
    cal = D["cal"]
    Y.Y30Pos.LIM = Y.limit_table(cal)
    cost_era, cost_c = Y.era_cost(cal), Y.const_cost(cal)
    res = {"meta": D["meta"], "prereg_sha": open(PREREG_SHA).read().strip(),
           "params": {k: D["p"][k] for k in ("atr_ratio_max", "stage1_freshness", "breakeven_promote_atr", "trail_atr",
                                            "stop_atr", "hard_stop_pct", "max_positions", "max_positions_per_sector",
                                            "max_open_risk_pct", "market_unit_mode", "sizing_mode", "position_ratio",
                                            "risk_pct")}}
    res["self_check"] = self_check(D["st"], D["feats_by"][5], D["univ"], D["p"])
    log("self_check", res["self_check"])
    stage = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else "AB"
    if sample:
        OUT_NAME[0] = f"sample{sample}_"
    if "A" in stage:
        res["A"] = part_a(D, cost_era, cost_c)
        _dump(res, "result_A.json")
    if "B" in stage:
        res["B"] = part_b(D, cost_era, cost_c)
    res["elapsed_s"] = time.time() - T0
    _dump(res, "result.json" if stage == "AB" else f"result_{stage}.json")


OUT_NAME = [""]


def _dump(res, name):
    path = os.path.join(OUT, OUT_NAME[0] + name)
    with open(path, "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=_js)
    log("written", path)


if __name__ == "__main__":
    main()
