#!/usr/bin/env python3
"""운용 전략 전수 점검 S1 kojiro — 동결본 §3.1 그대로: P6 관문 → P1·P2·P5 → P3·P4 → L1(rules 판) → 보고판.

입력(읽기만): 주식 보관소 parquet 6개(sha 대조) · ETF 보관소(069500 — 시장 유닛) · 단계 1 DB 추출본(sha 대조).
출력: 스크래치 ``audit/kojiro/result.json`` (+ 거래 목록 csv). 결과 md 는 사람이 이 JSON 으로 쓴다.

실행: python tools/replay/strategies/kojiro_run.py
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import book as BK  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay import judge as JR  # noqa: E402  (ER 삼분위 — 평균회귀 판정 층)
from replay.audit import live as LV  # noqa: E402
from replay.audit import market_unit as MU  # noqa: E402
from replay.audit import panel as PN  # noqa: E402
from replay.audit.sizing import OpSizer  # noqa: E402
from replay.strategies import kojiro as KJ  # noqa: E402
from src.engine.etf_like import is_etf_like  # noqa: E402
from src.engine.strategies.kojiro import KojiroStrategy  # noqa: E402

EXTRACT_SHA = "e31e842ba7e7f47e8f96ac6cd4dad223dcc047c23f6c99f8686606d02e2ccebf"
OUT = os.path.join(C.SCRATCH, "kojiro")
RULES_START = "2026-08-19"        # D-8 rules 판(사용자 결정 10-05) — stage1_result §3.2
STARTS = {"strict": "2026-10-02", "ex_mu": "2026-09-08", "rules": RULES_START}
PROV_CUTOFF = "2026-09-28"        # D-6
T0 = time.time()


def log(*a):
    print(f"[kojiro {time.time() - T0:6.0f}s]", *a, flush=True)


# ── 데이터 ───────────────────────────────────────────────────────────────

def load_all():
    got = PN.sha256(C.DB_EXTRACT)
    if got != EXTRACT_SHA:
        raise SystemExit(f"[kojiro] 추출본 sha 불일치 {got}")
    arch_sha = PN.check_archive(C.STOCK_ARCHIVE, C.STOCK_PARQUET_SHA)
    etf_sha = PN.check_archive(C.ETF_ARCHIVE, C.ETF_PARQUET_SHA)
    ext = PN.load_db_extract()
    arch = PN.load_archive(C.STOCK_ARCHIVE, end=C.W5Y[1])
    arch = arch[arch.ticker.str.fullmatch(r"\d{6}")]
    mcols, mrows = ext["master"]
    master = {r[0]: dict(zip(mcols, r)) for r in mrows}
    for d in master.values():
        raw = d.get("master_raw")
        d["raw"] = json.loads(raw) if isinstance(raw, str) else raw
    db = PN.db_daily_frame(ext, C.H1Y[0], C.H1Y[1])
    keep = []
    for t in db.ticker.unique():
        mm = master.get(t)
        if not (len(t) == 6 and t.isdigit()):
            continue
        if mm is not None and is_etf_like(mm.get("raw"), mm.get("name")):
            continue
        keep.append(t)
    etf_tickers_db = sorted(set(db.ticker.unique()) - set(keep))
    db = db[db.ticker.isin(keep)]
    st = PN.build_store(arch, db=db, nontrade="flag", junction_rescale=True)
    # R2 — DB 구간 시총 근사: 현재 시총 × (그날 원본 종가 ÷ 최신 원본 종가)
    r2 = Counter()
    for t, b in st.bars.items():
        msk = b["src"] == 1
        if not msk.any():
            continue
        mm = master.get(t)
        cap = (mm or {}).get("hts_avls_eok")
        craw = b["c_raw"].astype(float)
        last = craw[msk][-1]
        if cap and last > 0:
            b["mktcap"] = b["mktcap"].astype(float)
            b["mktcap"][msk] = float(cap) * 1e8 * craw[msk] / last
            r2["approx"] += 1
        else:
            r2["no_master"] += 1
    # 시장 유닛: ETF 보관소 069500 + 그 뒤 DB 069500
    etf = PN.load_archive(C.ETF_ARCHIVE, columns=["ticker", "bas_dd", "close_adj"])
    k = etf[etf.ticker == MU.SOURCE_TICKER].sort_values("bas_dd")
    dcols, drows = ext["daily"]
    ix = {c: i for i, c in enumerate(dcols)}
    extra = sorted((pd.Timestamp(r[ix["bas_dd"]][:10]), float(r[ix["close_price"]])) for r in drows
                   if r[ix["ticker"]] == MU.SOURCE_TICKER and pd.Timestamp(r[ix["bas_dd"]][:10]) > k.bas_dd.max())
    kd = pd.DatetimeIndex(list(k.bas_dd) + [x[0] for x in extra])
    kc = np.concatenate([k.close_adj.to_numpy(float), np.array([x[1] for x in extra])])
    m = MU.m_for_days(st.cal, kd, kc)
    meta = {"extract_sha": got, "archive_sha": arch_sha, "etf_sha": etf_sha, "r2": dict(r2),
            "db_etf_like_dropped": len(etf_tickers_db), "store": st.meta, "mu_069500_db_tail_days": len(extra)}
    return ext, master, st, m, (kd, kc), meta


def kospi_proxy(kd, kc, cal, win):
    s = pd.Series(kc, index=kd)
    s = s[(s.index >= pd.Timestamp(win[0])) & (s.index <= pd.Timestamp(win[1]))]
    eq = s.to_numpy() / s.iloc[0]
    return {"cagr": float(eq[-1] ** (252.0 / len(eq)) - 1), "mdd": float((eq / np.maximum.accumulate(eq) - 1).min()),
            "n_days": int(len(eq))}


def er_on_cal(cal, kd, kc, n=20):
    """069500 Kaufman ER(20) — 날 D 의 값 = D 보다 앞선 마지막 069500 봉까지(시장 유닛과 같은 정렬)."""
    er = np.full(len(kc), np.nan)
    for t in range(n, len(kc)):
        seg = kc[t - n:t + 1]
        den = np.abs(np.diff(seg)).sum()
        if den > 0:
            er[t] = abs(seg[-1] - seg[0]) / den
    pos = pd.DatetimeIndex(kd).searchsorted(cal, side="left") - 1
    out = np.full(len(cal), np.nan)
    ok = pos >= 0
    out[ok] = er[pos[ok]]
    return out


# ── 실거래 ───────────────────────────────────────────────────────────────

def live_rows(ext):
    cols, rows = ext["trades_all"]
    return [dict(zip(cols, r)) for r in rows if r[cols.index("strategy")] == "kojiro"]


def live_buys(rows):
    """COMPLETED·PARTIAL 매수 주문(order_no 묶음) → [(ticker, KST 날짜, qty, price)]."""
    kept = [r for r in rows if r["trade_type"] == "BUY" and r["status"] in LV.JUDGE_STATUSES]
    orders = LV._collapse_orders(sorted(kept, key=lambda r: r["timestamp"]))
    return [(o["ticker"], LV.kst_date(o["timestamp"]).isoformat(), int(o["quantity"]), float(o["price"]))
            for o in orders]


# ── 재현 묶음 ─────────────────────────────────────────────────────────────

def gd_range(cal, win):
    return (int(cal.searchsorted(pd.Timestamp(win[0]))),
            int(cal.searchsorted(pd.Timestamp(win[1]), side="right")) - 1)


def pop_stats(pop, cost=C.COST_RT_JUDGE):
    if not pop:
        return {"n": 0}
    r = np.array([KJ.net_ret(p, cost) for p in pop])
    reasons = Counter(p.exit_reason for p in pop)
    hold = np.array([(p.exit_gd if p.exit_gd is not None else p.s.gd) - p.s.gd + 1 for p in pop])
    srt = np.sort(r)
    k1 = max(1, int(round(len(r) * 0.01)))
    return {"n": len(r), "mean": float(r.mean()), "median": float(np.median(r)), "std": float(r.std()),
            "win": float((r > 0).mean()), "mean_ex_top1pct": float(srt[:-k1].mean()) if len(r) > k1 else float("nan"),
            "hold_bars_median": float(np.median(hold)), "exit_reasons": dict(reasons),
            "stage3_share": reasons.get("TREND_EXIT", 0) / len(r), "be_hit_share": float(np.mean([p.be_hit for p in pop]))}


def p1_of(pop, cal, cost=C.COST_RT_JUDGE):
    r = [KJ.net_ret(p, cost) for p in pop]
    return J.p1(r, [p.s.ticker for p in pop], [cal[p.s.gd].date() for p in pop])


@contextmanager
def no_shuffle():
    """보고판(점수 순서) 전용 — book.run_book 의 같은 날 섞기를 끈다(신호 목록을 점수 내림차순으로 넣는다)."""
    real = BK.np.random.default_rng

    class _R:
        def __init__(self, *_a, **_k):
            pass

        def shuffle(self, x):
            return None
    BK.np.random.default_rng = _R
    try:
        yield
    finally:
        BK.np.random.default_rng = real


def run_books(sigs, st, feats, p, win, *, cost_rt=C.COST_RT_JUDGE, mode="color", seeds=C.BOOK_SEEDS,
              gates_kw=None, rank_order=False):
    sizer = OpSizer(KojiroStrategy, "kojiro", p, atr_keys=("atr",))
    sbg = defaultdict(list)
    for s in sigs:
        sbg[s.gd].append(s)
    if rank_order:
        for g in sbg:
            sbg[g].sort(key=lambda s: -s.score)
    runs, gates_all = [], []
    for seed in seeds:
        g = KJ.Gates(p, sizer, **(gates_kw or {}))

        def open_pos(s, q, g=g):
            ps = KJ.KJPos(s, st.bars[s.ticker], feats[s.ticker], q, p, mode=mode)
            g.opened.append(ps)
            return ps
        if rank_order:
            with no_shuffle():
                r = BK.run_book(sbg, open_pos, g.size, st.cal, win[0], win[1], seed, start_equity=float(C.BUDGET_C7),
                                cost_side=cost_rt / 2, max_pos=int(p["max_positions"]))
        else:
            r = BK.run_book(sbg, open_pos, g.size, st.cal, win[0], win[1], seed, start_equity=float(C.BUDGET_C7),
                            cost_side=cost_rt / 2, max_pos=int(p["max_positions"]))
        r["gate_hits"] = dict(g.hits)
        runs.append(r)
        gates_all.append(g)
    return runs


def book_report(runs, st, win):
    sm = BK.book_summary(runs, float(C.BUDGET_C7))
    out = {k: sm[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median", "trades_median",
                              "fills_per_year_median", "unaffordable_ratio_median", "recon_max_abs", "counts_seed0")}
    hits = Counter()
    for r in runs:
        hits.update(r["gate_hits"])
    out["gate_hits_total_16seeds"] = dict(hits)
    out["gate_hits_seed0"] = runs[0]["gate_hits"]
    tr0 = [ps for ps in runs[0]["trades"]]
    reasons = Counter(ps.exit_reason for ps in tr0)
    out["exit_reasons_seed0"] = dict(reasons)
    out["stage3_share_seed0"] = reasons.get("TREND_EXIT", 0) / max(1, len(tr0))
    # 유동성(보고만): 랏 금액이 진입일 거래대금의 1% 초과
    big = [ps for ps in tr0 if ps.cost_basis > 0.01 * float(st.bars[ps.s.ticker]["tv"][ps.s.ti] or 0)]
    out["lots_over_1pct_tv_seed0"] = {"n": len(big), "share": len(big) / max(1, len(tr0))}
    q = [ps.qty for ps in tr0]
    out["lot_qty_seed0"] = {"median": float(np.median(q)) if q else None, "one_share_share": float(np.mean(np.array(q) == 1)) if q else None,
                            "lot_won_median": float(np.median([ps.cost_basis for ps in tr0])) if tr0 else None}
    # 연도별 평가액(씨앗 0)
    eq, dates = runs[0]["equity"], runs[0]["dates"]
    yr = {}
    prev = float(C.BUDGET_C7)
    for y in sorted(set(d.year for d in dates)):
        msk = np.array([d.year == y for d in dates])
        last = float(eq[msk][-1])
        yr[str(y)] = last / prev - 1
        prev = last
    out["year_return_seed0"] = yr
    return out, sm


def p6_block(buys, sigset, candset, diag_fn, start):
    sel = [(t, d) for (t, d, *_r) in buys if d >= start]
    res = {"signals_gap_filtered": J.p6(sel, sigset), "candidates_pre_gap": J.p6(sel, candset), "detail": []}
    for t, d in sel:
        res["detail"].append({"ticker": t, "date": d, "signal": (t, d) in sigset, "candidate": (t, d) in candset,
                              **diag_fn(t, d)})
    return res


def main():
    os.makedirs(OUT, exist_ok=True)
    ext, master, st, m_day, (kd, kc), meta = load_all()
    log("store", meta["store"], "r2", meta["r2"])
    sc = {r[0]: r for r in [tuple(x) for x in ext["strategy_config"][1]]}
    scols = ext["strategy_config"][0]
    row = dict(zip(scols, sc["kojiro"]))
    p = KJ.op_params(row)
    res = {"meta": meta, "params_db": json.loads(row["params"]) if isinstance(row["params"], str) else row["params"],
           "params_used": {k: p[k] for k in sorted(p) if not isinstance(p[k], (list, dict))}}
    cal = st.cal
    sectors = KJ.sectors_from_master(ext["master"][0], ext["master"][1])

    feats, univ, ties = {}, {}, 0
    for t, b in st.bars.items():
        f = KJ.features(b, p)
        feats[t] = f
        univ[t] = KJ.universe(b, p)
        ties += f["ties"]
    log("features", len(feats), "ties", ties)
    sigs, cnt = KJ.build_signals(st.bars, feats, univ, m_day, p, sectors)
    res["signal_counts"] = cnt
    res["stage_ties_filled"] = ties
    log("signals", len(sigs), cnt)

    # 운영 enrich 직접 대조(전 후보 + 무작위 비후보 표본) — 벡터 재현의 자기 검증
    res["self_check"] = self_check(st, feats, univ, p)
    log("self_check", res["self_check"])

    def key(s):
        return (s.ticker, cal[s.gd].date().isoformat())
    sigset = {key(s) for s in sigs}
    candset = set()
    for t, f in feats.items():
        b = st.bars[t]
        for i in np.nonzero(f["tech"] & univ[t])[0]:
            if i + 1 < len(b["di"]):
                candset.add((t, cal[b["di"][i + 1]].date().isoformat()))
            else:
                nd = int(b["di"][i]) + 1
                if nd < len(cal):
                    candset.add((t, cal[nd].date().isoformat()))

    # ── P6 관문 ─────────────────────────────────────────────────────────
    rows = live_rows(ext)
    buys = live_buys(rows)

    def diag(t, d):
        b = st.bars.get(t)
        if b is None:
            return {"why": "no_bars"}
        gd = int(cal.searchsorted(pd.Timestamp(d)))
        k = int(np.searchsorted(b["di"], gd))
        i = k - 1
        if i < 0:
            return {"why": "no_prev_bar"}
        f = feats[t]
        out = {"bar_i": str(cal[b["di"][i]].date()), "nbars": int(f["nbars"][i]), "stage": int(f["stage"][i]),
               "atr_ratio": float(f["ratio"][i]), "tech": bool(f["tech"][i]), "univ": bool(univ[t][i]),
               "mktcap_eok": float(b["mktcap"][i] / 1e8) if np.isfinite(b["mktcap"][i]) else None,
               "tv_eok": float(b["tv"][i] / 1e8), "close_gt_ema5": bool(f["prev_close"][i] > f["ema_s"][i])}
        if k < len(b["di"]) and b["di"][k] == gd:
            pc = f["prev_close"][i]
            out["gap_pct"] = float((b["o"][k] - pc) / pc * 100)
        return out
    res["P6"] = {nm: p6_block(buys, sigset, candset, diag, s0) for nm, s0 in STARTS.items()}
    res["P6"]["all_live_buys"] = p6_block(buys, sigset, candset, diag, "2026-01-01")
    log("P6 rules", {k: v for k, v in res["P6"]["rules"]["signals_gap_filtered"].items()})

    # ── P1 · P5 (W5y 모집단) ───────────────────────────────────────────────
    g5 = gd_range(cal, C.W5Y)
    pop = KJ.population(sigs, st.bars, feats, p, g5[0], g5[1], "color")
    popA = KJ.population(sigs, st.bars, feats, p, g5[0], g5[1], "adverse")
    res["P1"] = p1_of(pop, cal)
    res["P1_stats"] = pop_stats(pop)
    res["P1_cost_sens"] = {str(c): p1_of(pop, cal, c) for c in C.COST_RT_SENS}
    res["P5"] = J.p5(res["P1"]["mean"], float(np.mean([KJ.net_ret(x, C.COST_RT_JUDGE) for x in popA])))
    res["P5"]["adverse_P1"] = p1_of(popA, cal)
    res["P5"]["adverse_stats"] = pop_stats(popA)
    log("P1", res["P1"], "P5", {k: res["P5"][k] for k in ("mean_color", "mean_adverse", "label")})
    write_trades(os.path.join(OUT, "pop_w5y.csv"), pop, cal)

    # 연도 · 시장 유닛 × ER 삼분위 (보고판 ②)
    er = er_on_cal(cal, kd, kc)
    cut = g5[0] + int(0.6 * (g5[1] - g5[0] + 1))
    bounds = JR.er_terciles(er[g5[0]:g5[1] + 1], cut - g5[0])
    erb = JR.er_bucket(er, bounds)
    res["regime"] = {"er_bounds_front60": bounds, "table": regime_table(pop, cal, m_day, erb),
                     "by_year": by_year(pop, cal)}

    # ── P2 (H 모집단) + D-6 잠정 종가 판 ────────────────────────────────────
    gh = gd_range(cal, C.H1Y)
    popH = KJ.population(sigs, st.bars, feats, p, gh[0], gh[1], "color")
    hr = [KJ.net_ret(x, C.COST_RT_JUDGE) for x in popH]
    res["P2"] = J.p2(hr, res["P1"]["mean"])
    res["P2_stats"] = pop_stats(popH)
    res["P2_adverse"] = pop_stats(KJ.population(sigs, st.bars, feats, p, gh[0], gh[1], "adverse"))
    res["D6"] = d6_variant(ext, st, feats, sigs, p, gh, cal)
    log("P2", res["P2"], "D6", res["D6"])
    write_trades(os.path.join(OUT, "pop_h.csv"), popH, cal)

    # ── P3 · P4 (W4 계좌, C7) ─────────────────────────────────────────────
    runs = run_books(sigs, st, feats, p, C.W4)
    rep, sm = book_report(runs, st, C.W4)
    res["book_W4"] = rep
    res["P3"] = J.p3(sm)
    res["P4"] = J.p4(sm)
    log("P3", res["P3"], "P4", res["P4"])
    runsA = run_books(sigs, st, feats, p, C.W4, mode="adverse")
    repA, smA = book_report(runsA, st, C.W4)
    res["book_W4_adverse"] = {k: repA[k] for k in ("cagr_median", "mdd_median", "trades_median", "fills_per_year_median")}
    res["P3_adverse"] = J.p3(smA)
    res["book_W4_cost_sens"] = {}
    for c in C.COST_RT_SENS:
        rr, ss = book_report(run_books(sigs, st, feats, p, C.W4, cost_rt=c), st, C.W4)
        res["book_W4_cost_sens"][str(c)] = {k: rr[k] for k in ("cagr_median", "mdd_median")}
    log("book adverse", res["book_W4_adverse"], "cost", res["book_W4_cost_sens"])
    # 보고판: 점수 순서(운영 폴 순서) · 섹터/리스크 캡 끔 · W5y 책 · H 책
    rr, _ = book_report(run_books(sigs, st, feats, p, C.W4, seeds=(0,), rank_order=True), st, C.W4)
    res["book_W4_rank_order"] = {k: rr[k] for k in ("cagr_median", "mdd_median", "trades_median", "gate_hits_seed0")}
    rr, _ = book_report(run_books(sigs, st, feats, p, C.W4, gates_kw={"sector_cap": False, "risk_cap": False}), st, C.W4)
    res["book_W4_no_caps"] = {k: rr[k] for k in ("cagr_median", "mdd_median", "trades_median", "fills_per_year_median")}
    rr, _ = book_report(run_books(sigs, st, feats, p, C.W5Y), st, C.W5Y)
    res["book_W5y"] = {k: rr[k] for k in ("cagr_median", "mdd_median", "trades_median", "fills_per_year_median",
                                         "year_return_seed0")}
    rr, _ = book_report(run_books(sigs, st, feats, p, C.H1Y), st, C.H1Y)
    res["book_H"] = {k: rr[k] for k in ("cagr_median", "mdd_median", "trades_median", "fills_per_year_median")}
    res["kospi_proxy_069500"] = {"W4": kospi_proxy(kd, kc, cal, C.W4), "H": kospi_proxy(kd, kc, cal, C.H1Y)}
    log("books extra done")

    # ── 보고판 ① 오늘 시총 유니버스 · ③ 무작위 진입 대조군 · ⑤ 상위 1% 제외 ─────────
    res["today_universe"] = today_universe(st, feats, master, m_day, p, sectors, g5, cal)
    res["random_control"] = random_control(st, feats, univ, pop, p, g5, cal)
    res["no_market_unit"] = pop_stats(KJ.population(
        [KJ.Sig(**{**s.__dict__, "m": 1.0}) for s in sigs], st.bars, feats, p, g5[0], g5[1]))
    log("reports", res["today_universe"].get("mean"), res["random_control"])

    # ── L1 (rules 판) · L2 ────────────────────────────────────────────────
    ca = LV.ca_days_from_db(*ext["daily"])
    rt = LV.round_trips(rows, cost_rt=C.COST_RT_JUDGE, ca_days=ca)
    res["live"] = live_block(rt)
    log("L1", res["live"]["rules"]["L1"])

    res["elapsed_s"] = time.time() - T0
    with open(os.path.join(OUT, "result.json"), "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=_js)
    log("written", os.path.join(OUT, "result.json"))


def _js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (date, pd.Timestamp)):
        return str(o)
    return str(o)


def write_trades(path, pop, cal):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "entry", "exit", "E", "exit_px", "reason", "net038", "m", "N", "gap", "be_hit"])
        for x in pop:
            w.writerow([x.s.ticker, cal[x.s.gd].date(), cal[x.exit_gd].date() if x.exit_gd is not None else "",
                        round(x.E, 4), round(x.exit_px, 4), x.exit_reason, round(KJ.net_ret(x, C.COST_RT_JUDGE), 6),
                        x.s.m, round(x.s.N, 4), round(x.s.gap, 3), x.be_hit])


def regime_table(pop, cal, m_day, erb):
    out = {}
    net = np.array([KJ.net_ret(x, C.COST_RT_JUDGE) for x in pop])
    mu = np.array([x.s.m for x in pop])
    eb = np.array([erb[x.s.gd] for x in pop])
    for mv in (1.0, 0.75, 0.5, None):
        for b in (0, 1, 2, None):
            msk = np.ones(len(pop), bool)
            if mv is not None:
                msk &= mu == mv
            if b is not None:
                msk &= eb == b
            n = int(msk.sum())
            out[f"mu={mv}|er={b}"] = {"n": n, "mean": float(net[msk].mean()) if n else None, "thin": n < 10}
    return out


def by_year(pop, cal):
    d = defaultdict(list)
    for x in pop:
        d[cal[x.s.gd].year].append(KJ.net_ret(x, C.COST_RT_JUDGE))
    return {str(y): {"n": len(v), "mean": float(np.mean(v))} for y, v in sorted(d.items())}


def self_check(st, feats, univ, p, n_neg=1500, seed=C.BOOT_SEED):
    """벡터 재현 ↔ 운영 enrich 판정(봉 단위). 전 후보 + 무작위 비후보 ``n_neg`` 개."""
    rng = np.random.default_rng(seed)
    from src.engine.kojiro_indicators import KojiroIndicatorConfig, enrich
    from src.engine.strategies.kojiro import _stage_recently
    cfg = KojiroIndicatorConfig(ema_short=p["ema_short"], ema_mid=p["ema_mid"], ema_long=p["ema_long"],
                                macd_signal=p["macd_signal"], atr_period=p["atr_period"], slope_lookback=p["slope_lookback"])

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
    pos = [(t, int(i)) for t, f in feats.items() for i in np.nonzero(f["tech"] & univ[t])[0]]
    tick = list(feats)
    neg = []
    while len(neg) < n_neg:
        t = tick[rng.integers(len(tick))]
        nb = len(st.bars[t]["c"])
        if nb < KJ.MIN_BARS:
            continue
        i = int(rng.integers(KJ.MIN_BARS - 1, nb))
        if not feats[t]["tech"][i]:
            neg.append((t, i))
    pos_bad = [(t, i) for t, i in pos if not op(st.bars[t], i)]
    neg_bad = [(t, i) for t, i in neg if op(st.bars[t], i)]
    return {"pos_checked": len(pos), "pos_mismatch": len(pos_bad), "neg_checked": len(neg), "neg_mismatch": len(neg_bad),
            "examples": [(t, str(st.cal[st.bars[t]["di"][i]].date())) for t, i in (pos_bad + neg_bad)[:10]]}


def d6_variant(ext, st, feats, sigs, p, gh, cal):
    """D-6 — 2026-09-28 전 DB 행 중 잠정 종가 의심 행을 거래 정지로 넣은 판(진입·청산 없음)."""
    from replay.data import krx_tick
    dcols, drows = ext["daily"]
    ix = {c: i for i, c in enumerate(dcols)}
    by = defaultdict(list)
    for r in drows:
        by[r[ix["ticker"]]].append((r[ix["bas_dd"]][:10], r[ix["close_price"]], r[ix["change_rate"]]))
    flagged = defaultdict(set)
    nflag = 0
    for t, rs in by.items():
        rs.sort()
        for a, b2 in zip(rs, rs[1:]):
            if a[0] >= PROV_CUTOFF:
                break
            if not a[1] or not b2[1] or b2[2] is None:
                continue
            implied = b2[1] / (1.0 + float(b2[2]) / 100.0)
            tol = max(krx_tick(a[1]), abs(implied) * 5e-7 + b2[1] * 5e-7 + 1e-9)
            if abs(a[1] - implied) > tol:
                flagged[t].add(a[0])
                nflag += 1
    bars2 = {}
    for t, b in st.bars.items():
        if t in flagged:
            b2 = dict(b)
            nt = b["notrade"].copy()
            for k, di in enumerate(b["di"]):
                if b["src"][k] == 1 and str(cal[di].date()) in flagged[t]:
                    nt[k] = True
            b2["notrade"] = nt
            bars2[t] = b2
        else:
            bars2[t] = b
    keep = [s for s in sigs if not bars2[s.ticker]["notrade"][s.ti] and not bars2[s.ticker]["notrade"][s.ti - 1]]
    pop2 = KJ.population(keep, bars2, feats, p, gh[0], gh[1])
    st2 = pop_stats(pop2)
    return {"flagged_rows": nflag, "flagged_tickers": len(flagged), "n": st2.get("n"), "mean": st2.get("mean"),
            "dropped_signals_H": sum(1 for s in sigs if gh[0] <= s.gd <= gh[1]) - sum(1 for s in keep if gh[0] <= s.gd <= gh[1])}


def today_universe(st, feats, master, m_day, p, sectors, g5, cal):
    """보고판 ① — 오늘(2026-10-02 스냅샷) 시총으로 고른 유니버스(생존 편향 크기)."""
    univ2 = {}
    for t, b in st.bars.items():
        cap = (master.get(t) or {}).get("hts_avls_eok")
        mc = np.full(len(b["c"]), float(cap) * 1e8 if cap else 0.0)
        univ2[t] = KJ.universe(b, p, mktcap=mc)
    sigs2, _ = KJ.build_signals(st.bars, feats, univ2, m_day, p, sectors)
    pop2 = KJ.population(sigs2, st.bars, feats, p, g5[0], g5[1])
    return pop_stats(pop2)


def random_control(st, feats, univ, pop, p, g5, cal, seed=C.BOOT_SEED):
    """보고판 ③ — 같은 날짜 분포 · 같은 유니버스(시총·거래대금·가격 · 80봉 · ATR>0)에서 진입만 무작위."""
    rng = np.random.default_rng(seed)
    by_gd = defaultdict(list)
    for t, b in st.bars.items():
        f = feats[t]
        ok = univ[t] & (f["nbars"] >= KJ.MIN_BARS) & np.isfinite(f["atr"]) & (f["atr"] > 0)
        for i in np.nonzero(ok[:-1])[0]:
            D = i + 1
            if b["di"][D] == b["di"][i] + 1 and not b["notrade"][D] and b["o"][D] > 0:
                by_gd[int(b["di"][D])].append((t, int(D)))
    out = []
    for x in pop:
        pool = by_gd.get(x.s.gd)
        if not pool:
            continue
        t, D = pool[rng.integers(len(pool))]
        b = st.bars[t]
        s = KJ.Sig(t, D, int(b["di"][D]), float(b["o"][D]), float(b["o"][D] * b["raw"][D]), float(feats[t]["atr"][D - 1]), x.s.m)
        out.append(KJ.run_path(s, b, feats[t], p, g5[1]))
    a = pop_stats(out)
    real = np.array([KJ.net_ret(x, C.COST_RT_JUDGE) for x in pop])
    a["real_mean"] = float(real.mean())
    a["diff_real_minus_random"] = float(real.mean() - a["mean"]) if a.get("n") else None
    return a


def live_block(rt):
    trips = [t for t in rt["trips"] if t["strategy"] == "kojiro"]
    out = {"n_all": len(trips), "open": [o for o in rt["open"] if o["strategy"] == "kojiro"],
           "excluded": {str(k): v for k, v in rt["excluded"].items() if k[0] == "kojiro"}}
    for nm, s0 in {**STARTS, "all": "2026-04-29"}.items():
        sel = [t for t in trips if t["buy_date"] >= s0 and not t["ca_flag"]]
        net = [t["net"] for t in sel]
        blk = {"start": s0, "L1": J.l1(net, [t["buy_date"] for t in sel])}
        if sel:
            amt = np.array([t["buy_amt"] for t in sel])
            nv = np.array(net)
            srt = sorted(net, reverse=True)
            blk["L2"] = {"amount_weighted_mean": float((amt * nv).sum() / amt.sum()),
                         "one_share_share": float(np.mean([t["one_share"] for t in sel])),
                         "mean_ex_top5": float(np.mean(srt[5:])) if len(srt) > 5 else None,
                         "win": float(np.mean(nv > 0)), "median": float(np.median(nv)),
                         "hold_days_cal_median": float(np.median([t["hold_days_cal"] for t in sel]))}
            blk["trips"] = [{k: t[k] for k in ("ticker", "name", "buy_date", "sell_date", "qty", "buy_px", "sell_px", "net")}
                            for t in sel]
        out[nm] = blk
    return out


if __name__ == "__main__":
    main()
