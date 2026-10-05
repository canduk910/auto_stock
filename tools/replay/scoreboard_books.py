#!/usr/bin/env python3
"""성적표용 개별 매매 전략 계좌 곡선 — 30년 재검증의 계좌 집행을 「한 계좌로 이어서」 다시 돈다.

30년 재검증은 T·V·H 창마다 4,707,820원으로 새로 시작했다. 성적표는 「30년을 그대로 투자」 를 묻기 때문에
같은 신호·같은 집행 함수·같은 사이저로 1997-01-02 ~ 2026-10-02 를 한 번에 돈다(새 최적화·새 선택 없음).
대조로 H 창(2021-01-04 ~ 2026-10-02)도 같은 경로로 다시 돌려 공표값과 나란히 적는다.

씨앗 16 중 최종 평가액이 하위 중앙(8번째)인 씨앗의 곡선을 저장한다(씨앗별 CAGR·낙폭은 meta 에).

    python tools/replay/scoreboard_books.py <books_dir> [kojiro donchian vcp bfb vb etf_trend mr_band mr_fkeep]
"""
from __future__ import annotations

import json
import os
import sys
import time

for _k in ("KIS_APP_KEY_REAL", "KIS_APP_SECRET_REAL", "KIS_ACCOUNT_NO_REAL", "KIS_APP_KEY_VTS", "KIS_APP_SECRET_VTS",
           "KIS_ACCOUNT_NO_VTS", "SUPABASE_URL", "SUPABASE_KEY", "DATABASE_URL"):
    os.environ.setdefault(_k, "audit-dummy")          # 운영 전략 클래스 import 용 더미(값은 쓰이지 않는다)

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay.audit import config as C  # noqa: E402

FULL = ("1997-01-02", "2026-10-02")
CHECK = ("2021-01-04", "2026-10-02")
S30 = "_workspace/analysis/strategy_30y_20261006"
# 공표값(H 창 · 씨앗 16 중앙 연 복리 · 낙폭) — 대조용
PUBLISHED_H = {
    "kojiro": ((-0.0275, -0.397), f"{S30}/kojiro/result.md A 표 H 시가"),
    "donchian": ((0.1254, -0.323), f"{S30}/donchian/result.md §1.1 H"),
    "vcp": ((-0.1101, -0.6285), f"{S30}/vcp/results.json A.basic.H.book"),
    "bfb": ((-0.3220, -0.8988), f"{S30}/bfb/results.json A.basic.H.book"),
    "vb": ((-0.671, -0.998), f"{S30}/vb/result.md §2.3 기본판 낙관 H"),
    "etf_trend": ((0.1299, -0.251), f"{S30}/etf_base/result.md §1.2 H"),
    "mr_band": ((-0.1841, -0.7280), f"{S30}/mr_regime/band_results_stock.json detail.current.book.H"),
    "mr_fkeep": ((-0.1370, -0.6693), f"{S30}/mr_regime/band_results_stock.json detail.F-keep.book.H"),
}
# 공표값의 연율 규약 — 공용 ``audit.book.cagr``(거래일 252일 = 1년)를 쓴 연구 · 나머지는 달력 연수
PUBLISHED_ANN_252 = {"donchian", "vb"}
# 공표값과 다를 수밖에 없는 사유(대조 표에 그대로 적는다)
PUBLISHED_NOTE = {
    "mr_band": "원 연구의 볼린저 계좌는 실행마다 흔들린다 — 후보를 병렬 풀(imap_unordered)이 모으는 순서가 씨앗 섞기의 입력 순서가 "
               "되기 때문(같은 코드 3회: H 연복리 −17.6 ~ −18.7% · 낙폭 −71.3 ~ −72.2%). 성적표는 (진입일, 종목) 순으로 고정",
    "mr_fkeep": "같은 사유(후보 수집 순서 비결정 — 같은 코드 5회: H 연복리 −14.2 ~ −15.0% · 낙폭 −67.7 ~ −70.1%). "
                "성적표는 (진입일, 종목) 순으로 고정",
}


def _cagr(eq, start, d0, d1):
    yrs = (d1 - d0).days / 365.25
    return float((eq[-1] / start) ** (1 / yrs) - 1) if eq[-1] > 0 else -1.0


def _mdd(eq, start):
    e = np.r_[start, eq]
    return float((e / np.maximum.accumulate(e) - 1).min())


def pack(sid: str, dates: pd.DatetimeIndex, runs: list, start_equity: float, *, source: str, note: str = "",
         check: "dict | None" = None, extra: "dict | None" = None) -> dict:
    """runs = [(씨앗, equity 배열)] · dates = 각 equity 의 날짜(같은 길이). 대표 = 최종 평가액 하위 중앙 씨앗."""
    dates = pd.DatetimeIndex(dates)
    finals = np.array([float(e[-1]) for _, e in runs])
    order = np.argsort(finals, kind="stable")
    rep = order[(len(runs) - 1) // 2]
    d_start = pd.Timestamp(dates[0]) - pd.Timedelta(1, unit="D")
    per_seed = [{"seed": int(s), "cagr": _cagr(e, start_equity, d_start, dates[-1]), "mdd": _mdd(e, start_equity),
                 "final": float(e[-1])} for s, e in runs]
    meta = {"source": source, "note": note, "window": [str(dates[0].date()), str(dates[-1].date())],
            "start_equity": start_equity, "rep_seed": int(runs[rep][0]), "n_seeds": len(runs),
            "seed_cagr_median": float(np.median([x["cagr"] for x in per_seed])),
            "seed_cagr_min": float(min(x["cagr"] for x in per_seed)),
            "seed_cagr_max": float(max(x["cagr"] for x in per_seed)),
            "seed_mdd_median": float(np.median([x["mdd"] for x in per_seed])),
            "per_seed": per_seed, "check_H": check, **(extra or {})}
    eq = np.r_[start_equity, np.asarray(runs[rep][1], float)]
    dd = pd.DatetimeIndex([d_start]).append(dates)
    return {"sid": sid, "dates": np.array([str(d.date()) for d in dd]), "equity": eq, "meta": meta}


def save(out_dir: str, p: dict) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{p['sid']}.npz")
    np.savez_compressed(path, dates=p["dates"], equity=p["equity"], meta=json.dumps(p["meta"], ensure_ascii=False))
    return path


def _check(sid, runs, start_equity, dates):
    d_start = pd.Timestamp(pd.DatetimeIndex(dates)[0]) - pd.Timedelta(1, unit="D")
    cg = float(np.median([_cagr(e, start_equity, d_start, pd.DatetimeIndex(dates)[-1]) for _, e in runs]))
    md = float(np.median([_mdd(e, start_equity) for _, e in runs]))
    cg252 = float(np.median([(e[-1] / start_equity) ** (252.0 / len(e)) - 1 if e[-1] > 0 else -1.0 for _, e in runs]))
    (pc, pm), ref = PUBLISHED_H[sid]
    return {"window": list(CHECK), "cagr_median": cg, "cagr_median_252": cg252, "mdd_median": md,
            "published_cagr": pc, "published_mdd": pm, "published_ref": ref, "note": PUBLISHED_NOTE.get(sid, ""),
            "published_ann": "252" if sid in PUBLISHED_ANN_252 else "cal",
            "diff_cagr": cg - pc, "diff_cagr_252": cg252 - pc, "diff_mdd": md - pm}


class _Grab:
    """``모듈.함수`` 를 잠시 감싸 첫 인자(runs)를 붙잡는다 — 원 함수 결과는 그대로 돌려준다."""

    def __init__(self, mod, name):
        self.mod, self.name, self.orig, self.runs = mod, name, getattr(mod, name), None

    def __enter__(self):
        def wrap(runs, *a, **k):
            self.runs = runs
            return self.orig(runs, *a, **k)
        setattr(self.mod, self.name, wrap)
        return self

    def __exit__(self, *exc):
        setattr(self.mod, self.name, self.orig)


# ═════════════════════════════════ 전략별 ═════════════════════════════════

def kojiro(out_dir):
    from replay.audit import market_unit as MU
    from replay.audit import panel as PN
    from replay.strategies import kojiro as KJ
    from replay.strategies import kojiro_opt as KO
    from replay.strategies import kojiro_run as KR
    from replay.strategies import kojiro_y30 as Y
    from replay.strategies import kojiro_y30_run as R
    from src.engine.etf_like import is_etf_like
    Y.patch_fast_ewm()
    if PN.sha256(C.DB_EXTRACT) != KR.EXTRACT_SHA:
        raise SystemExit("[books kojiro] 추출본 sha 불일치")
    ext = PN.load_db_extract()
    row = dict(zip(ext["strategy_config"][0], {r[0]: r for r in ext["strategy_config"][1]}["kojiro"]))
    p = KJ.op_params(row)
    sectors = KJ.sectors_from_master(ext["master"][0], ext["master"][1])
    df, _ = Y.load_unified(drop_flags=False)
    etf_names = sorted(n for n in df.name.dropna().unique() if is_etf_like(None, n))
    if etf_names:
        df = df[~df.name.isin(etf_names)]
    cal = pd.DatetimeIndex(sorted(df.bas_dd.unique()))
    st = Y.build(df[~df.flag], cal=cal)
    del df
    kd, kc = Y.mu_series()
    m_day = MU.m_for_days(cal, kd, kc)
    pf = {**p, "stage1_freshness": 5}
    feats = {t: KJ.features(b, pf) for t, b in st.bars.items()}
    univ = {t: Y.universe_era(b) for t, b in st.bars.items()}
    fb = {t: {**f, "tech": f["tech"] & (f["ratio"] <= 0.06)} for t, f in feats.items()}
    sigs, _ = KJ.build_signals(st.bars, fb, univ, m_day, {**pf, "atr_ratio_max": 0.06}, sectors)
    sigs = KO.select(sigs, "cur", None)
    Y.Y30Pos.LIM = Y.limit_table(cal)
    cost = Y.era_cost(cal)
    out = {}
    for tag, win in (("full", FULL), ("check", CHECK)):
        with _Grab(Y, "summary30") as g:
            R.run_books(sigs, st.bars, feats, p, cal, win, cost, slip=0.0)
        out[tag] = ([(i, r["equity"]) for i, r in enumerate(g.runs)], g.runs[0]["dates"],
                    float(np.median([r["counts"].get("fill", 0) for r in g.runs])))
    runs, dates, fills = out["full"]
    yrs = (dates[-1] - dates[0]).days / 365.25
    return pack("kojiro", dates, runs, float(C.BUDGET_C7),
                source="kojiro_y30_run.run_books(시가 · 시기별 비용 · 운영 DB 파라미터)",
                check=_check("kojiro", out["check"][0], float(C.BUDGET_C7), out["check"][1]),
                extra={"fills_per_year": fills / yrs})


def donchian(out_dir):
    from replay.audit import book as BK
    from replay.audit.sizing import OpSizer, load_strategy_class
    from replay.strategies import donchian_kk as DK
    from replay.strategies import donchian_kk_audit as DA
    from replay.strategies import donchian_y30 as D
    from replay.strategies import donchian_y30_data as YD
    st, m, _, _ = YD.build(D.CACHE)
    cal = st.cal
    D._CAL["cal"] = cal
    bars = st.bars
    era = D.Costs(cal)
    if DA.PN.sha256(DA.BRANCH_DONCHIAN) != DA.BRANCH_SHA:
        raise SystemExit("[books donchian] 브랜치 전략 파일 sha256 불일치")
    cls = load_strategy_class(DA.BRANCH_DONCHIAN, "DonchianSwingStrategy", "y30_branch_donchian_kk")
    entry, ex, acct = D.ENTRY0, D.EXIT0, D.ACCT0
    kk = D.kk_of(ex, acct)
    feats = {t: D.features_y30(b, entry_n=entry["entry_n"], vol_mult=entry["vol_mult"], clv=entry["clv"],
                               tv_mode="pct") for t, b in bars.items()}
    raw = DK.build_signals(bars, feats, m)
    sg = D.mu_apply([s for s in raw if not DA.r_half_blocked(s.E, s.N, kk)], entry["mu"])
    fv = {t: D.feats_view(f, ex["chan"]) for t, f in feats.items()}
    op = OpSizer(cls, "donchian_swing", {"market_unit_mode": "enforce", "risk_pct": kk["risk_pct"],
                                         "position_ratio": acct["slots"][1], "max_positions": acct["slots"][0],
                                         "kk_r_floor_pct": ex["r"][0], "kk_r_atr_mult": ex["r"][1]})
    out = {}
    for tag, win in (("full", FULL), ("check", CHECK)):
        with _Grab(BK, "book_summary") as g:
            D.books(sg, bars, fv, win, kk, op, era)
        out[tag] = ([(i, r["equity"]) for i, r in enumerate(g.runs)], g.runs[0]["dates"],
                    float(np.median([r["counts"].get("fill", 0) for r in g.runs])))
    runs, dates, fills = out["full"]
    yrs = (dates[-1] - dates[0]).days / 365.25
    return pack("donchian", dates, runs, float(C.BUDGET_C7),
                source="donchian_y30.books(현행 ENTRY0·EXIT0·ACCT0 · 시기별 비용)",
                check=_check("donchian", out["check"][0], float(C.BUDGET_C7), out["check"][1]),
                extra={"fills_per_year": fills / yrs})


def _bfbvcp(kind, out_dir):
    from replay.strategies import bfb_vcp_opt as OP
    from replay.strategies import y30_bfbvcp as YB
    Y = YB.Y
    cls, featf = YB._classes(kind)
    st, meta = Y.build()
    cal = st.cal
    m, _ = Y.market_unit(cal)
    cost = YB.EraCostY(cal)
    s_, e_, x_, mu_ = YB.CURRENT_ID.split("|")
    p_s = OP.params_for(kind, s_, "X0")
    feats = {t: featf(b, p_s) for t, b in st.bars.items()}
    univ = Y.universe(st, meta["ratios"], kind, mode="pct")
    entries = {e[0]: e for e in OP.entries_for(kind)}
    _, meth, cap, k = entries[e_]
    sigs = YB.build_signals(st.bars, feats, m, p_s, univ, method=meth, cap=cap, k=k, slip=YB.LIVE_SLIP,
                            close_slip=0.0)
    p_g = OP.params_for(kind, s_, x_)
    out = {}
    for tag, win in (("full", FULL), ("check", CHECK)):
        with _Grab(YB, "book_summary") as g:
            YB.run_books(sigs, st, feats, kind, p_g, cls, win, cost, mu_thr=OP.MU_THR[mu_])
        g0 = int(cal.searchsorted(pd.Timestamp(win[0])))
        dates = cal[g0:g0 + len(g.runs[0]["equity"])]
        out[tag] = ([(i, r["equity"]) for i, r in enumerate(g.runs)], dates,
                    float(np.median([r["counts"].get("fill", 0) for r in g.runs])))
    runs, dates, fills = out["full"]
    yrs = (dates[-1] - dates[0]).days / 365.25
    return pack(kind, dates, runs, float(C.BUDGET_C7),
                source=f"y30_bfbvcp.run_books({YB.CURRENT_ID} · 기본판 체결 +{YB.LIVE_SLIP:.2%} · 시기별 비용 + 0.15%p)",
                check=_check(kind, out["check"][0], float(C.BUDGET_C7), out["check"][1]),
                extra={"fills_per_year": fills / yrs})


def vcp(out_dir):
    return _bfbvcp("vcp", out_dir)


def bfb(out_dir):
    return _bfbvcp("bfb", out_dir)


def vb(out_dir):
    from replay.strategies import vb_y30_run as R
    Y = R.Y
    st, meta = R.load()
    ctx = R.Ctx(st, meta)
    sizer, _ = R.vb_sizer()
    km, hold, mode, stop, filt = R.CUR
    sall = R.allsig(ctx, km, hold, mode, stop, filt, R.FILLS["base"], "opt")
    out = {}
    for tag, win in (("full", FULL), ("check", CHECK)):
        g = R.gwin(ctx.cal, win)
        with _Grab(Y, "book_summary") as gr:
            R.book(ctx, sall, g, sizer)
        dates = ctx.cal[g[0]:g[1] + 1]
        out[tag] = ([(i, r["equity"]) for i, r in enumerate(gr.runs)], dates,
                    float(np.median([r["counts"].get("fill", 0) for r in gr.runs])))
    runs, dates, fills = out["full"]
    yrs = (dates[-1] - dates[0]).days / 365.25
    return pack("vb", dates, runs, float(C.BUDGET_C7),
                source="vb_y30_run.book(현행 k 1.3 · 기본판 체결 ×1.0193 · 낙관판 · 시기별 비용)",
                note="계좌가 1~2년 안에 녹아 1주도 못 사는 상태로 남는다(공표 결과와 같음)",
                check=_check("vb", out["check"][0], float(C.BUDGET_C7), out["check"][1]),
                extra={"fills_per_year": fills / yrs})


ETF_FULL = ("2003-01-02", FULL[1])


def etf_trend(out_dir):
    from replay import y30_etfbase_run as YR
    from replay.strategies import etf_trend_opt as EO
    V = YR.etf_load()
    thr = 2e9 * V["defl"]
    sigs, _ = YR.gen_signals30(V["data"], V["mu"], 20, thr, V["anom"], V["lock"])
    out = {}
    for tag, win in (("full", ETF_FULL), ("check", CHECK)):
        bk = YR.etf_book30(V, sigs, EO.CURRENT, win, seeds=C.BOOK_SEEDS)
        g0, g1 = YR.win_idx(V["cal"], win)
        out[tag] = (bk, V["cal"][g0:g1 + 1])
    bk, dates = out["full"]
    if not bk["per_seed_identical"]:
        raise SystemExit("[books etf_trend] 씨앗별 결과가 다르다 — 씨앗 0 곡선만으로는 안 된다")
    runs = [(0, bk["equity_seed0"])]
    cb, cd = out["check"]
    ck = _check("etf_trend", [(0, cb["equity_seed0"])], float(C.BUDGET_C7), cd)
    return pack("etf_trend", dates, runs, float(C.BUDGET_C7),
                source="y30_etfbase_run.etf_book30(현행 · 시기별 비용 표 · 씨앗 16 동일 결과)",
                note="2014 년까지는 적격 ETF 가 0~9개(대부분 KOSPI200 추종) — 판정은 2015 년부터였다",
                check=ck, extra={"fills_per_year": bk["fills_per_year_median"],
                                 "cost_yr": bk["cost_per_year_pct_seed0"] / 100.0})


MR_SCRATCH = os.path.join(os.path.dirname(C.SCRATCH), "y30mr")


def _mr(out_dir, which):
    from replay import y30_mr_band as MB
    Y = MB.Y
    key = MB.CURRENT["stock"] if which == "mr_band" else ("F-keep", 20, 2.5, "reentry", "mid", "atr")
    dates, bars, sig_ok, names, lab, cost, meta = MB.load(MR_SCRATCH, "stock")
    MB.G.update(bars=bars, sig_ok=sig_ok, lab=lab)
    _, allc = MB.build("stock", [key], keep_all=frozenset([key]), nproc=int(os.environ.get("Y30_NPROC", 6)))
    # 병렬 수집 순서가 씨앗 섞기 결과를 바꾸므로 (진입일, 종목) 순으로 고정한다(원 연구는 고정하지 않았다)
    cands = sorted((c for c in allc.get(key, []) if not c.jump), key=lambda c: (c.e_gd, c.tid))
    pr, mp_ = MB.BOOK["stock"]
    out = {}
    for tag, win in (("full", FULL), ("check", CHECK)):
        g0, g1 = Y.seg_bounds(dates, win)
        rr = [MB.run_book(cands, bars, cost, g0, g1, s, start_equity=MB.C7, pos_ratio=pr, max_pos=mp_)
              for s in MB.SEEDS]
        dd = pd.DatetimeIndex(np.asarray(dates[g0:g1 + 1]).astype("datetime64[ns]"))
        out[tag] = ([(i, r["equity"]) for i, r in enumerate(rr)], dd,
                    float(np.median([r["counts"].get("fill", 0) for r in rr])))
    runs, dd, fills = out["full"]
    yrs = (dd[-1] - dd[0]).days / 365.25
    return pack(which, dd, runs, float(MB.C7), source=f"y30_mr_band.run_book({'·'.join(map(str, key))} · 5슬롯 × 20%)",
                check=_check(which, out["check"][0], float(MB.C7), out["check"][1]),
                extra={"fills_per_year": fills / yrs, "key": list(key)})


def mr_band(out_dir):
    return _mr(out_dir, "mr_band")


def mr_fkeep(out_dir):
    return _mr(out_dir, "mr_fkeep")


ADAPTERS = {"kojiro": kojiro, "donchian": donchian, "vcp": vcp, "bfb": bfb, "vb": vb, "etf_trend": etf_trend,
            "mr_band": mr_band, "mr_fkeep": mr_fkeep}


def main():
    out_dir = sys.argv[1]
    names = sys.argv[2:] or list(ADAPTERS)
    for nm in names:
        t0 = time.time()
        p = ADAPTERS[nm](out_dir)
        path = save(out_dir, p)
        mt = p["meta"]
        print(f"[books] {nm} {time.time() - t0:.0f}s → {path} · 대표 씨앗 {mt['rep_seed']} · 씨앗 CAGR 중앙 "
              f"{mt['seed_cagr_median']:+.4f} · 낙폭 중앙 {mt['seed_mdd_median']:+.3f} · H 대조 "
              f"{mt['check_H']['cagr_median']:+.4f}/{mt['check_H']['mdd_median']:+.3f} vs 공표 "
              f"{mt['check_H']['published_cagr']:+.4f}/{mt['check_H']['published_mdd']:+.3f}", flush=True)


if __name__ == "__main__":
    main()
