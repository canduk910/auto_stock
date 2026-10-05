#!/usr/bin/env python3
"""운용 전략 전수 점검 §3.2 — donchian_swing(깡토 개조) 판정 실행(동결본 sha 2d7e7b42).

입력 = 주식 보관소(W5y, sha 대조) + 단계 1 DB 추출본(``audit_db_extract.jsonl.gz``, H = 2025-10-10 ~ 2026-10-02)
+ ETF 보관소 069500(시장 유닛, 보관소 끝 09-23 뒤는 DB 069500 으로 잇는다).

두 판을 같은 입력으로 돌린다.
- ``c405`` = cycle405 재현 그대로(관문 1 비트 일치판) — 채널 ≤ · 거래대금 열 배수 · R ≥ 0.5P 거름 없음
- ``op``   = K1 차이를 운영 코드 쪽으로 맞춘 판(판정판) — 채널 < (D1) · 원본 종가×거래량 배수(D2) ·
            R ≥ 0.5 × 가격이면 진입 없음(D3, 운영 ``_kk_design_lot`` L6)

판정(§1.3·§3.2): P1(W5y 신호 모집단) · P2(H 부호) · P5(불리 경로) · P3·P4(W4 C7 단독 풀 계좌, 운영 사이저).
보고만: 비용 0.28·0.48 · 연도별 · 시장 유닛 × ER 삼분위 · 무작위 진입 대조군 · 069500 보유 · 상위 1% 제외 ·
D-6 잠정 종가 halt 판 · H 계좌.

실행: python tools/replay/strategies/donchian_kk_audit.py [--out PATH]
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import defaultdict

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import book as BK  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.audit import market_unit as MU  # noqa: E402
from replay.audit import panel as PN  # noqa: E402
from replay.audit.sizing import OpSizer, load_strategy_class  # noqa: E402
from replay.strategies import donchian_kk as DK  # noqa: E402

BRANCH_DONCHIAN = os.path.join(C.SCRATCH, "donchian_kk_branch.py")
BRANCH_SHA = "c8c7172e8e33fa164e2d11c30641562e8ab2d6474e7a84f241320bf2fbab58f3"   # git show d1b91180:… 와 같음
DB_EXTRACT_SHA = "e31e842ba7e7f47e8f96ac6cd4dad223dcc047c23f6c99f8686606d02e2ccebf"
PROV_CUTOFF = "2026-09-28"
VARIANTS = {
    "c405": dict(kk=DK.KK, turnover="tv", r_half=False),
    "op": dict(kk=dict(DK.KK, chan_strict=True), turnover="cv", r_half=True),
}
OP_PARAMS = {"market_unit_mode": "enforce", "risk_pct": DK.KK["risk_pct"],
             "position_ratio": DK.KK["pr"], "max_positions": DK.KK["max_pos"]}


# ── 작은 순수 함수(테스트 대상) ─────────────────────────────────────────────

def r_half_blocked(E: float, N: float, kk: dict = DK.KK) -> bool:
    """운영 ``_kk_design_lot`` L6 — R = max(8%·가격, 1.5·N) ≥ 0.5 × 가격이면 사지 않는다. N 결측 = ATR 항 0."""
    n = N if (N is not None and math.isfinite(N) and N > 0) else 0.0
    r = max(kk["r_floor"] * E, kk["r_atr"] * n)
    return bool(r >= 0.5 * E)


def db_member(row) -> bool:
    """DB 구간 지수 편입 — ``stock_master.is_kospi200 ∨ is_kosdaq150``(현재 값) · ETF 류(EF/EN/FE) 제외."""
    if not row:
        return False
    g = (row.get("scty_grp_id_cd") or row.get("scty_grp_id_cd_master") or "")
    if g in ("EF", "EN", "FE"):
        return False
    return bool(row.get("is_kospi200")) or bool(row.get("is_kosdaq150"))


def provisional_flags(dates, c, chg, cutoff: str = PROV_CUTOFF) -> np.ndarray:
    """D-6 — t 일 종가가 다음 날 전일 대비로 역산한 전일 종가와 1틱 넘게 다르면 잠정(평균회귀 ``data.py`` 와 같은 식)."""
    from replay.data import krx_tick
    c = np.asarray(c, float)
    chg = np.asarray(chg, float)
    dates = np.asarray(dates, dtype="datetime64[D]")
    out = np.zeros(len(c), dtype=bool)
    cut = np.datetime64(cutoff)
    for i in range(len(c) - 1):
        if dates[i] >= cut:
            break
        if not (np.isfinite(c[i]) and np.isfinite(c[i + 1]) and np.isfinite(chg[i + 1])):
            continue
        implied = c[i + 1] / (1.0 + chg[i + 1] / 100.0)
        tol = max(krx_tick(c[i]), abs(implied) * 5e-7 + c[i + 1] * 5e-7 + 1e-9)
        out[i] = abs(c[i] - implied) > tol
    return out


# ── 데이터 ─────────────────────────────────────────────────────────────

def build_inputs():
    PN.check_archive(C.STOCK_ARCHIVE, C.STOCK_PARQUET_SHA)
    PN.check_archive(C.ETF_ARCHIVE, C.ETF_PARQUET_SHA)
    if PN.sha256(C.DB_EXTRACT) != DB_EXTRACT_SHA:
        raise SystemExit("[donchian] DB 추출본 sha256 불일치 — 멈춘다")
    if PN.sha256(BRANCH_DONCHIAN) != BRANCH_SHA:
        raise SystemExit("[donchian] 브랜치 전략 파일 sha256 불일치 — 멈춘다")
    ext = PN.load_db_extract()
    mc, mr = ext["master"]
    meta = {r[mc.index("ticker")]: dict(zip(mc, r)) for r in mr}
    db = PN.db_daily_frame(ext, C.H1Y[0], C.H1Y[1])
    db = db.sort_values(["ticker", "bas_dd"]).reset_index(drop=True)
    db["mem"] = [db_member(meta.get(t)) for t in db.ticker]
    db["prov"] = False
    for t, g in db.groupby("ticker", sort=False):
        db.loc[g.index, "prov"] = provisional_flags(g.bas_dd.values, g.close.to_numpy(float),
                                                    g.change_rate.to_numpy(float))
    arch = PN.load_archive(C.STOCK_ARCHIVE, end=C.W5Y[1])
    arch["mem"] = DK.index_member_archive(arch).to_numpy()
    arch["prov"] = False
    st = PN.build_store(arch, db=db, nontrade="flag", junction_rescale=True, extra_cols=("mem", "prov"))
    # 시장 유닛 — ETF 보관소 069500 + 보관소 끝 뒤 DB 069500(겹치는 날 종가 일치 확인)
    etf = PN.load_archive(C.ETF_ARCHIVE, columns=["ticker", "bas_dd", "close_adj"])
    k = etf[etf.ticker == MU.SOURCE_TICKER].sort_values("bas_dd")[["bas_dd", "close_adj"]]
    dk = pd.DataFrame([r for r in ext["daily"][1] if r[0] == MU.SOURCE_TICKER], columns=ext["daily"][0])
    dk["bas_dd"] = pd.to_datetime(dk.bas_dd.str[:10])
    ov = k.merge(dk[["bas_dd", "close_price"]], on="bas_dd")
    eq = ov.close_adj.to_numpy(float) == ov.close_price.to_numpy(float)
    first_eq = int(np.argmax(np.cumprod(eq[::-1])[::-1])) if eq[-1] else len(eq)   # 끝에서부터 연속 일치 구간 시작
    seam = {"overlap_days": int(len(ov)), "tail_equal_days": int(len(eq) - first_eq),
            "tail_equal_from": str(ov.bas_dd.iloc[first_eq].date()) if first_eq < len(eq) else None,
            "note": "보관소는 분배 수정가 — 마지막 수정 이후 구간만 DB 원본과 같아야 한다"}
    tail = dk[dk.bas_dd > k.bas_dd.max()][["bas_dd", "close_price"]].rename(columns={"close_price": "close_adj"})
    seam["db_days_appended"] = [str(d.date()) for d in tail.bas_dd]
    k2 = pd.concat([k, tail], ignore_index=True)
    m = MU.m_for_days(st.cal, pd.DatetimeIndex(k2.bas_dd), k2.close_adj.to_numpy(float))
    kser = pd.Series(k2.close_adj.to_numpy(float), index=pd.DatetimeIndex(k2.bas_dd))
    return st, m, kser, seam, ext


# ── 판정 재료 ───────────────────────────────────────────────────────────

def signals_for(st, m, var):
    feats = {t: DK.features(b, b["mem"].astype(bool), turnover=var["turnover"]) for t, b in st.bars.items()}
    sigs = DK.build_signals(st.bars, feats, m)
    n0 = len(sigs)
    if var["r_half"]:
        sigs = [s for s in sigs if not r_half_blocked(s.E, s.N, var["kk"])]
    return feats, sigs, n0 - len(sigs)


def pop_rows(pop, cost):
    rows = []
    for p in pop:
        rows.append({"t": p.s.ticker, "gd": p.s.gd, "m": p.s.m, "net": p.exit_px / p.E - 1 - cost,
                     "R": DK.kk_R(p, cost), "why": p.exit_reason, "hold": (p.exit_gd - p.s.gd + 1)
                     if p.exit_gd is not None else None})
    return rows


def p1_of(rows, cal):
    if not rows:
        return {"n": 0, "label": "판정 불가"}
    r = J.p1([x["net"] for x in rows], [x["t"] for x in rows], [cal[x["gd"]].date() for x in rows])
    w = np.array([x["m"] for x in rows])
    R = np.array([x["R"] for x in rows])
    r["R_mweighted"] = float((w * R).sum() / w.sum())
    r["R_mean"] = float(R.mean())
    srt = sorted(x["net"] for x in rows)
    k = int(np.ceil(0.01 * len(srt)))
    r["mean_ex_top1pct"] = float(np.mean(srt[:len(srt) - k])) if len(srt) > k else float("nan")
    r["exit_reasons"] = dict(pd.Series([x["why"] for x in rows]).value_counts())
    r["win_rate"] = float(np.mean([x["net"] > 0 for x in rows]))
    return r


def run_books(sigs, st, feats, win, kk, op, *, cost_rt, mode="color", seeds=C.BOOK_SEEDS):
    sbg = defaultdict(list)
    for s in sigs:
        sbg[s.gd].append(s)

    def opsize(s, B, used):
        P = int(round(s.E_raw))
        if s.m <= 0:
            return 0, "mu"
        q = op.qty(P, s.N * (s.E_raw / s.E), budget=int(B), used=int(used), m=s.m)
        if q > 0:
            return q, "ok"
        return 0, ("funds" if int(B) - int(used) < P else "design")

    def open_pos(s, q):
        return DK.KKPos(s, st.bars[s.ticker], feats[s.ticker], q, mode=mode, kk=kk)

    runs = [BK.run_book(sbg, open_pos, opsize, st.cal, win[0], win[1], seed, start_equity=float(C.BUDGET_C7),
                        cost_side=cost_rt / 2, max_pos=kk["max_pos"], daily_cap=kk["daily_cap"]) for seed in seeds]
    sm = BK.book_summary(runs, float(C.BUDGET_C7))
    # P4 보조 — 시장 유닛(m=0) 신호를 분모에서 뺀 「슬롯 찬 신호 비율」
    slot = []
    for r in runs:
        c = r["counts"]
        live = c.get("signal", 0) - c.get("zero_mu", 0)
        slot.append((c.get("slot_full", 0) + c.get("daily_cap", 0)) / live if live > 0 else float("nan"))
    sm["slot_or_cap_ratio_ex_mu_median"] = float(np.nanmedian(slot))
    # 유동성 보고(§1.3a) — 랏 금액 ÷ 진입 전날 거래대금 > 1% 비율
    big, tot = 0, 0
    for ps in runs[0]["trades"]:
        b = st.bars[ps.s.ticker]
        j = ps.s.ti - 1
        tv = b["tv"][j] if j >= 0 else np.nan
        if tv and tv > 0:
            tot += 1
            big += int(ps.qty * ps.s.E_raw > 0.01 * tv)
    sm["lot_over_1pct_tv_seed0"] = (big / tot) if tot else float("nan")
    sm["exit_reasons_seed0"] = dict(pd.Series([ps.exit_reason for ps in runs[0]["trades"]]).value_counts())
    return sm


def book_view(sm):
    keep = ("cagr_median", "cagr_min", "cagr_max", "mdd_median", "trades_median", "fills_per_year_median",
            "unaffordable_ratio_median", "slot_or_cap_ratio_ex_mu_median", "recon_max_abs", "counts_seed0",
            "lot_over_1pct_tv_seed0", "exit_reasons_seed0")
    return {k: sm[k] for k in keep}


def random_control(pop, st, feats, end_gd, kk, cost, reps=5):
    """보고판 ③ — 같은 날(신호봉 날짜) 같은 유니버스(편입 ∧ 200억 ∧ 62봉)에서 진입만 무작위, 청산·N 같음."""
    elig = defaultdict(list)
    for t, b in st.bars.items():
        f = feats[t]
        di = b["di"]
        ok = (np.arange(len(di)) >= 62) & b["mem"].astype(bool) & (b["tv"] >= DK.ENTRY["min_trade"]) \
            & ~b["notrade"] & (np.nan_to_num(f["atr"]) > 0)
        for j in np.nonzero(ok[:-1])[0]:
            if di[j + 1] == di[j] + 1 and not b["notrade"][j + 1] and b["o"][j + 1] > 0:
                elig[int(di[j])].append((t, int(j)))
    means = []
    for r in range(reps):
        rng = np.random.default_rng(C.BOOT_SEED + 100 + r)
        vals = []
        for p in pop:
            cand = elig.get(p.s.gd - 1)
            if not cand:
                continue
            t, j = cand[int(rng.integers(len(cand)))]
            b = st.bars[t]
            D = j + 1
            s = DK.Sig(t, D, int(b["di"][D]), float(b["o"][D]), float(b["o"][D] * b["raw"][D]),
                       float(feats[t]["atr"][j]), float("nan"), p.s.m)
            q = DK.run_path(s, b, feats[t], end_gd, kk=kk)
            vals.append(q.exit_px / q.E - 1 - cost)
        means.append(float(np.mean(vals)))
    return {"reps": reps, "mean_of_means": float(np.mean(means)), "per_rep": means}


def yearly(rows, cal):
    by = defaultdict(list)
    for x in rows:
        by[cal[x["gd"]].year].append(x["net"])
    return {str(y): {"n": len(v), "mean": float(np.mean(v))} for y, v in sorted(by.items())}


def mu_er_table(rows, cal, kser):
    from replay import judge as RJ
    from replay.strategies.mean_reversion.ou import efficiency_ratio
    kc = kser.reindex(cal).ffill().to_numpy(float)
    er = np.array([efficiency_ratio(kc, t, 20) for t in range(len(kc))])
    w5 = (cal >= pd.Timestamp(C.W5Y[0])) & (cal <= pd.Timestamp(C.W5Y[1]))
    i0 = int(np.argmax(w5))
    cut = i0 + RJ.split_index(int(w5.sum()))
    bounds = RJ.er_terciles(er[i0:], cut - i0)
    eb = RJ.er_bucket(er, bounds)
    out = {"er_bounds": bounds}
    for mu in (1.0, 0.75, 0.5):
        for b in (0, 1, 2):
            v = [x["net"] for x in rows if x["m"] == mu and eb[x["gd"] - 1] == b]
            out[f"m={mu}|er={b}"] = {"n": len(v), "mean": float(np.mean(v)) if v else None, "thin": len(v) < 10}
    return out


def bh_069500(kser, win):
    s = kser[(kser.index >= pd.Timestamp(win[0])) & (kser.index <= pd.Timestamp(win[1]))]
    eq = s.to_numpy(float)
    return {"cagr": float((eq[-1] / eq[0]) ** (252.0 / len(eq)) - 1),
            "mdd": float((eq / np.maximum.accumulate(eq) - 1).min())}


def main():
    t0 = time.time()
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(
        C.REPO, "_workspace/analysis/strategy_audit_20261005/donchian/result.json")
    st, m, kser, seam, ext = build_inputs()
    cal = st.cal
    res = {"inputs": {"db_extract_sha256": DB_EXTRACT_SHA, "branch_donchian_sha256": BRANCH_SHA,
                      "stock_parquet": "sha 6개 = config.STOCK_PARQUET_SHA 대조 통과",
                      "etf_parquet": "sha 7개 = config.ETF_PARQUET_SHA 대조 통과",
                      "cal": [str(cal[0].date()), str(cal[-1].date()), len(cal)], "store": st.meta,
                      "market_unit_seam": seam,
                      "prov_rows_flagged": int(sum(int(b["prov"].sum()) for b in st.bars.values()))},
           "params": {"KK": DK.KK, "ENTRY": DK.ENTRY, "op_sizer_params": OP_PARAMS,
                      "budget": C.BUDGET_C7, "cost_rt": C.COST_RT_JUDGE}}
    print("[donchian] inputs", json.dumps(res["inputs"], ensure_ascii=False, default=str),
          f"{time.time()-t0:.0f}s", flush=True)

    def gd_of(d, side="left"):
        return int(cal.searchsorted(pd.Timestamp(d), side=side)) - (1 if side == "right" else 0)

    w5 = (gd_of(C.W5Y[0]), gd_of(C.W5Y[1], "right"))
    h = (gd_of(C.H1Y[0]), gd_of(C.H1Y[1], "right"))
    cls = load_strategy_class(BRANCH_DONCHIAN, "DonchianSwingStrategy", "audit_branch_donchian_kk_s2")
    op = OpSizer(cls, "donchian_swing", OP_PARAMS)
    cost = C.COST_RT_JUDGE
    for vname, var in VARIANTS.items():
        kk = var["kk"]
        feats, sigs, n_rhalf = signals_for(st, m, var)
        V = {"n_signals": len(sigs), "n_r_half_dropped": n_rhalf}
        pop = DK.population(sigs, st.bars, feats, *w5, kk=kk)
        rows = pop_rows(pop, cost)
        V["P1"] = p1_of(rows, cal)
        V["P1_cost_sens"] = {str(c): p1_of(pop_rows(pop, c), cal)["mean"] for c in C.COST_RT_SENS}
        popA = DK.population(sigs, st.bars, feats, *w5, mode="adverse", kk=kk)
        rowsA = pop_rows(popA, cost)
        pA = p1_of(rowsA, cal)
        V["P5"] = dict(J.p5(V["P1"]["mean"], pA["mean"]), adverse_P1=pA,
                       n_trades_differ=int(sum(1 for a, b in zip(pop, popA)
                                               if (a.exit_gd, a.exit_px) != (b.exit_gd, b.exit_px))))
        if vname == "c405":   # 관문 1 연결 — W4 · 비용 0.35% 모집단이 cycle405 거래 단위(1,827 · +0.8616%)와 같은가
            g0, g1 = gd_of(C.W4[0]), gd_of(C.W4[1], "right")
            p4 = DK.population(sigs, st.bars, feats, g0, g1, kk=kk)
            V["W4_pop_cost035_vs_c405"] = {"n": len(p4), "ret_mean_pct": float(np.mean(
                [p.exit_px / p.E - 1 - 0.0035 for p in p4]) * 100), "ref": {"n": 1827, "ret_mean_pct": 0.8616}}
        popH = DK.population(sigs, st.bars, feats, *h, kk=kk)
        rowsH = pop_rows(popH, cost)
        V["P2"] = J.p2([x["net"] for x in rowsH], V["P1"]["mean"])
        V["H_population"] = p1_of(rowsH, cal) if rowsH else {"n": 0}
        # D-6 — 잠정 종가 행을 halt 로 넣은 판(H): 표시 봉 = 거래 없음 취급
        bars_h = {t: (dict(b, notrade=b["notrade"] | b["prov"].astype(bool)) if b["prov"].any() else b)
                  for t, b in st.bars.items()}
        feats_h = {t: (DK.features(b, b["mem"].astype(bool), turnover=var["turnover"]) if b is not st.bars[t]
                       else feats[t]) for t, b in bars_h.items()}
        sigs_h = DK.build_signals(bars_h, feats_h, m)
        if var["r_half"]:
            sigs_h = [s for s in sigs_h if not r_half_blocked(s.E, s.N, kk)]
        rowsHp = pop_rows(DK.population(sigs_h, bars_h, feats_h, *h, kk=kk), cost)
        V["P2_prov_halt"] = J.p2([x["net"] for x in rowsHp], V["P1"]["mean"])
        print(f"[donchian:{vname}] P1 {V['P1']['n']} {V['P1']['mean']:+.5f} lo {V['P1']['lo90']:+.5f} | "
              f"P5adv {pA['mean']:+.5f} | P2 H n={V['P2']['n']} {V['P2'].get('mean', float('nan')):+.5f}",
              f"{time.time()-t0:.0f}s", flush=True)
        V["P3P4_W4"] = book_view(run_books(sigs, st, feats, C.W4, kk, op, cost_rt=cost))
        V["P3"] = J.p3(V["P3P4_W4"])
        V["P4"] = J.p4(V["P3P4_W4"])
        V["P3_adverse_W4"] = book_view(run_books(sigs, st, feats, C.W4, kk, op, cost_rt=cost, mode="adverse"))
        V["P3_cost_sens"] = {str(c): {k: v for k, v in book_view(run_books(sigs, st, feats, C.W4, kk, op, cost_rt=c))
                                      .items() if k in ("cagr_median", "mdd_median")} for c in C.COST_RT_SENS}
        V["book_H_report"] = book_view(run_books(sigs, st, feats, C.H1Y, kk, op, cost_rt=cost))
        V["book_W5y_report"] = book_view(run_books(sigs, st, feats, C.W5Y, kk, op, cost_rt=cost))
        print(f"[donchian:{vname}] W4 book cagr {V['P3P4_W4']['cagr_median']:+.4f} mdd {V['P3P4_W4']['mdd_median']:+.4f}"
              f" fills/y {V['P3P4_W4']['fills_per_year_median']:.1f} | adv {V['P3_adverse_W4']['cagr_median']:+.4f}",
              f"{time.time()-t0:.0f}s", flush=True)
        V["report_yearly"] = yearly(rows, cal)
        V["report_mu_er"] = mu_er_table(rows, cal, kser)
        V["report_random_control"] = random_control(pop, st, feats, w5[1], kk, cost)
        V["report_end_open_trades"] = sum(1 for x in rows if x["why"] == "END")
        res[vname] = V
    res["report_bh_069500"] = {"W4": bh_069500(kser, C.W4), "W5y": bh_069500(kser, C.W5Y),
                               "H": bh_069500(kser, C.H1Y)}
    res["elapsed_s"] = time.time() - t0
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("[donchian] done", out_path, f"{res['elapsed_s']:.0f}s")


if __name__ == "__main__":
    main()
