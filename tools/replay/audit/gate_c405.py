#!/usr/bin/env python3
"""관문 1 — 공용 층으로 cycle405(donchian 깡토 개조) W4 수치를 다시 낸다(동결본 §4 단계 2).

원 가정 그대로(예산 743,000원 · 비용 왕복 0.35% · 씨앗 0..15 · 시장 유닛 enforce · c405 사이징) 돌려
c405 ``results.json`` 의 W4 kk 책 · 거래 단위 수치와 대조한다. 같은 입력(c405 이 쓴 DB 덤프 ``db_dump.tsv``)을
쓰고, 단계마다(달력 → 종목 배열 → 시장 유닛 → 신호 → 계좌 → 거래 단위) 원본과 비교해 어긋나는 첫 단계를 보고한다.

그 뒤 보고판(관문 아님):
- 운영 사이징 어댑터(``OpSizer`` + 브랜치 donchian 클래스)로 같은 책 — 명세 복제 ``size_spec`` 과 다른가
- C7 가정(4,707,820원 · 비용 0.38%)판 W4

실행: python tools/replay/audit/gate_c405.py  → 표준출력 JSON + 스크래치 audit/gate_c405.json
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import book as BK  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import market_unit as MU  # noqa: E402
from replay.audit import panel as PN  # noqa: E402
from replay.audit.sizing import OpSizer, load_strategy_class  # noqa: E402
from replay.strategies import donchian_kk as DK  # noqa: E402

SCR405 = ("/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/"
          "1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/c405")
REF_DIR = os.path.join(C.SCRATCH, "c405")          # git show 로 꺼낸 c405 스크립트·결과
BRANCH_DONCHIAN = os.path.join(C.SCRATCH, "donchian_kk_branch.py")
DB_START, DB_END = "2025-10-10", "2026-09-30"
ORIG = dict(start_equity=743_000.0, cost_side=0.00175)


def load_c405_dbdump(path: str):
    sm, recs = None, []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("SM\t"):
                sm = json.loads(line[3:])
                continue
            p = line.rstrip("\n").split("\t")
            recs.append((p[1], p[2], int(p[3]), int(p[4]), int(p[5]), int(p[6]), int(p[7]),
                         int(p[8]) if p[8] not in ("", "None") else 0))
    db = pd.DataFrame(recs, columns=["ticker", "bas_dd", "open", "high", "low", "close", "volume", "trade_value"])
    db["bas_dd"] = pd.to_datetime(db.bas_dd)
    db = db[(db.bas_dd >= pd.Timestamp(DB_START)) & (db.bas_dd <= pd.Timestamp(DB_END))]
    return db, {r["ticker"]: r for r in sm}


def db_member(meta: dict, t: str) -> bool:
    r = meta.get(t)
    if not r:
        return False
    g = (r.get("g1") or r.get("g2") or "")
    if g in ("EF", "EN", "FE"):
        return False
    return bool(r.get("is_kospi200")) or bool(r.get("is_kosdaq150"))


def build(db_frame, db_meta):
    PN.check_archive(C.STOCK_ARCHIVE, C.STOCK_PARQUET_SHA)
    arch = PN.load_archive(C.STOCK_ARCHIVE, end=C.W5Y[1])
    arch["mem"] = DK.index_member_archive(arch).to_numpy()
    db = db_frame.copy()
    db["mem"] = [db_member(db_meta, t) for t in db.ticker]
    st = PN.build_store(arch, db=db, nontrade="flag", junction_rescale=True, extra_cols=("mem",))
    etf = PN.load_archive(C.ETF_ARCHIVE, columns=["ticker", "bas_dd", "close_adj"])
    k = etf[etf.ticker == MU.SOURCE_TICKER].sort_values("bas_dd")
    m = MU.m_for_days(st.cal, pd.DatetimeIndex(k.bas_dd), k.close_adj.to_numpy(float))
    return st, m


def compare_panel(st, m, ref) -> dict:
    out = {"cal_equal": bool(len(st.cal) == len(ref["cal"]) and (st.cal == ref["cal"]).all())}
    keys = ("di", "o", "h", "l", "c", "raw", "tv", "mem", "notrade")
    bad, n = [], 0
    for t, rp in ref["panel"].items():
        b = st.bars.get(t)
        if b is None:
            bad.append((t, "missing"))
            continue
        n += 1
        for kk in keys:
            a, r = np.asarray(b[kk]), np.asarray(rp[kk])
            if a.shape != r.shape or not np.array_equal(a, r, equal_nan=a.dtype.kind == "f"):
                bad.append((t, kk))
                break
    out["tickers_ref"] = len(ref["panel"])
    out["tickers_mine"] = len(st.bars)
    out["ticker_array_mismatch"] = bad[:20]
    out["n_mismatch"] = len(bad)
    ref_m, my_m = np.asarray(ref["m_for_day"]), np.asarray(m)
    w4 = (st.cal >= pd.Timestamp(C.W4[0])) & (st.cal <= pd.Timestamp(C.W4[1]))
    out["m_equal_W4"] = bool(np.array_equal(ref_m[w4], my_m[w4], equal_nan=True))
    out["m_equal_all"] = bool(np.array_equal(ref_m, my_m, equal_nan=True))
    diff = np.where(~((ref_m == my_m) | (np.isnan(ref_m) & np.isnan(my_m))))[0]
    out["m_diff_days"] = [(str(st.cal[i].date()), float(ref_m[i]), float(my_m[i])) for i in diff[:10]]
    out["m_diff_n"] = int(len(diff))
    return out


def sig_tuple(s):
    return (s.ticker, s.gd, s.ti, s.E, s.E_raw, s.N, s.bh, s.m)


def run_books(sigs, st, feats, win, *, start_equity, cost_side, size):
    sbg = {}
    for s in sigs:
        sbg.setdefault(s.gd, []).append(s)
    runs = []
    for seed in C.BOOK_SEEDS:
        def size_fn(s, B, used):
            return size(s, B, used)

        def open_pos(s, q):
            return DK.KKPos(s, st.bars[s.ticker], feats[s.ticker], q)
        runs.append(BK.run_book(sbg, open_pos, size_fn, st.cal, win[0], win[1], seed,
                                start_equity=start_equity, cost_side=cost_side,
                                max_pos=DK.KK["max_pos"], daily_cap=DK.KK["daily_cap"]))
    return runs


def main():
    t0 = time.time()
    with open(os.path.join(SCR405, "c405_panel.pkl"), "rb") as fh:
        ref = pickle.load(fh)
    refres = json.load(open(os.path.join(REF_DIR, "results.json")))
    out = {"inputs": {"c405_panel.pkl": PN.sha256(os.path.join(SCR405, "c405_panel.pkl")),
                      "db_dump.tsv": PN.sha256(os.path.join(SCR405, "db_dump.tsv")),
                      "c405_results.json": PN.sha256(os.path.join(REF_DIR, "results.json"))}}
    db, meta = load_c405_dbdump(os.path.join(SCR405, "db_dump.tsv"))
    st, m = build(db, meta)
    out["panel"] = compare_panel(st, m, ref)
    print("[gate405] panel", json.dumps(out["panel"], ensure_ascii=False), f"{time.time()-t0:.0f}s", flush=True)

    feats = {t: DK.features(b, b["mem"].astype(bool)) for t, b in st.bars.items()}
    sigs = DK.build_signals(st.bars, feats, m)
    # 원본 신호(c405 그대로) — 스크래치 사본 모듈을 불러 원본 pkl 로 만든다
    sys.path.insert(0, REF_DIR)
    import c405_sim as S405  # noqa: E402
    rfeats = {t: S405.ticker_features(p) for t, p in ref["panel"].items()}
    rsigs = S405.build_signals(ref["panel"], ref["m_for_day"], rfeats)
    mine_t = [sig_tuple(s) for s in sigs]
    ref_t = [sig_tuple(s) for s in rsigs]
    out["signals"] = {"n_ref": len(ref_t), "n_mine": len(mine_t), "equal": mine_t == ref_t,
                      "first_diff": next((i for i, (a, b) in enumerate(zip(mine_t, ref_t)) if a != b), None),
                      "n_ref_header": refres["n_signals"]}
    print("[gate405] signals", out["signals"], flush=True)

    g0 = int(st.cal.searchsorted(pd.Timestamp(C.W4[0])))
    g1 = int(st.cal.searchsorted(pd.Timestamp(C.W4[1]), side="right")) - 1

    def spec(s, B, used):
        return DK.size_spec(B, used, s.E_raw, s.N * (s.E_raw / s.E), s.m)

    runs = run_books(sigs, st, feats, C.W4, size=spec, **ORIG)
    sm = BK.book_summary(runs, ORIG["start_equity"])
    rk = refres["W4"]["kk"]
    per_ref = [(p["n_trades"], p["final"]) for p in rk["per_seed"]]
    per_mine = [(len(r["trades"]), float(r["equity"][-1])) for r in runs]
    out["book_W4_orig"] = {
        "mine": {k: sm[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median", "trades_median",
                                    "recon_max_abs")},
        "ref": {k: rk[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median", "trades_median",
                                   "recon_max_abs")},
        "per_seed_trades_equal": [a[0] == b[0] for a, b in zip(per_mine, per_ref)],
        "per_seed_final_absdiff_max": float(max(abs(a[1] - b[1]) for a, b in zip(per_mine, per_ref))),
        "counts_seed0": sm["counts_seed0"],
    }
    print("[gate405] book", json.dumps(out["book_W4_orig"], ensure_ascii=False), f"{time.time()-t0:.0f}s",
          flush=True)

    pop = DK.population(sigs, st.bars, feats, g0, g1)
    w = np.array([p.s.m for p in pop])
    R = np.array([DK.kk_R(p, 2 * ORIG["cost_side"]) for p in pop])
    ret = np.array([p.exit_px / p.E - 1 - 2 * ORIG["cost_side"] for p in pop])
    tr = refres["W4"]["tu_kk"]
    out["population_W4_orig"] = {"mine": {"n": len(pop), "R_mweighted": float((w * R).sum() / w.sum()),
                                          "ret_mean_pct": float(ret.mean() * 100)},
                                 "ref": {k: tr[k] for k in ("n", "R_mweighted", "ret_mean_pct")}}
    print("[gate405] population", out["population_W4_orig"], flush=True)

    # ── 보고판: 운영 사이징 어댑터(브랜치 donchian 클래스) ──
    cls = load_strategy_class(BRANCH_DONCHIAN, "DonchianSwingStrategy", "audit_branch_donchian_kk")
    op = OpSizer(cls, "donchian_swing", {"market_unit_mode": "enforce", "risk_pct": DK.KK["risk_pct"],
                                         "position_ratio": DK.KK["pr"], "max_positions": DK.KK["max_pos"]})

    def opsize(s, B, used):
        P = int(round(s.E_raw))
        if s.m <= 0:
            return 0, "mu"
        q = op.qty(P, s.N * (s.E_raw / s.E), budget=int(B), used=int(used), m=s.m)
        if q > 0:
            return q, "ok"
        return 0, ("funds" if int(B) - int(used) < P else "design")

    # 원 가정 + 정수 가격 반올림만 다른 명세판(운영은 정수 원 가격으로 계산한다)
    def spec_int(s, B, used):
        P = int(round(s.E_raw))
        return DK.size_spec(int(B), int(used), P, s.N * (s.E_raw / s.E), s.m)

    lot_cmp = {"n": 0, "diff": 0, "examples": []}
    for s in sigs[:: max(1, len(sigs) // 3000)]:
        if s.m <= 0:
            continue
        for B, used in ((743_000, 0), (743_000, 300_000), (C.BUDGET_C7, 0)):
            a = spec_int(s, B, used)[0]
            b = opsize(s, B, used)[0]
            lot_cmp["n"] += 1
            if a != b:
                lot_cmp["diff"] += 1
                if len(lot_cmp["examples"]) < 10:
                    lot_cmp["examples"].append({"t": s.ticker, "P": int(round(s.E_raw)), "N": s.N * s.E_raw / s.E,
                                                "m": s.m, "B": B, "used": used, "spec": a, "op": b})
    out["lot_spec_vs_operating"] = lot_cmp
    print("[gate405] lots spec vs operating", lot_cmp, flush=True)

    runs_op = run_books(sigs, st, feats, C.W4, size=opsize, **ORIG)
    so = BK.book_summary(runs_op, ORIG["start_equity"])
    out["book_W4_orig_operating_sizer"] = {k: so[k] for k in ("cagr_median", "mdd_median", "trades_median",
                                                               "recon_max_abs")}
    print("[gate405] book operating sizer", out["book_W4_orig_operating_sizer"], flush=True)

    # ── 보고판: C7 가정(단독 풀 4,707,820원 · 왕복 0.38%) — 새 측정, 관문 아님 ──
    c7 = dict(start_equity=float(C.BUDGET_C7), cost_side=C.COST_RT_JUDGE / 2)
    runs_c7 = run_books(sigs, st, feats, C.W4, size=opsize, **c7)
    s7 = BK.book_summary(runs_c7, c7["start_equity"])
    out["book_W4_C7_operating_sizer"] = {k: s7[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median",
                                                             "trades_median", "fills_per_year_median",
                                                             "unaffordable_ratio_median", "recon_max_abs",
                                                             "counts_seed0")}
    print("[gate405] book C7", out["book_W4_C7_operating_sizer"], flush=True)
    out["elapsed_s"] = time.time() - t0
    os.makedirs(C.SCRATCH, exist_ok=True)
    with open(os.path.join(C.SCRATCH, "gate_c405.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: out[k] for k in ("signals", "book_W4_orig", "population_W4_orig")}, ensure_ascii=False,
                     default=str))


if __name__ == "__main__":
    main()
