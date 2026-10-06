#!/usr/bin/env python3
"""donchian_swing(깡토 개조) 효율화 — 사전 등록 ``_workspace/analysis/strategy_opt_20261005/donchian/prereg.md``
(sha256 = 같은 폴더 ``prereg.sha256``) 그대로 돌린다.

현행판 = 전수 점검 운영 해석판(``donchian_kk_audit.VARIANTS["op"]``). 입력·사이저·계좌는 전수 점검과 같다
(``donchian_kk_audit.build_inputs`` · ``OpSizer`` · ``audit.book``). 이 모듈이 더하는 것:

- 진입 필터 확장(채널 길이 · 대금 배수 · 상대강도 · 종가 위치) — ``features_opt``
- 시장 유닛 사용법(m = 1 만 진입) — ``mu_filter``
- 청산 확장(R 정의 · 무장 R · 시간 청산 봉 · 무장 뒤 채널 길이) — ``kk_of`` · ``feats_view``
- 단계 A → B → C 선택(T 만 본다) → V 판정 · H 부호 — ``main``
- 두 판 평균 차의 주 블록 부트스트랩 — ``diff_boot``

실행: python tools/replay/strategies/donchian_opt.py [--out PATH]
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import config as C  # noqa: E402
from replay.audit import indicators as IND  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.audit.sizing import OpSizer, load_strategy_class  # noqa: E402
from replay.strategies import donchian_kk as DK  # noqa: E402
from replay.strategies import donchian_kk_audit as DA  # noqa: E402

PREREG_SHA = "e78c84c35977a2312194e34cdfb1aa11c3148eca8a9742c90c3e8d8f644da6b1"
T = ("2020-10-05", "2023-09-29")
V = ("2023-10-04", "2025-10-02")
H = ("2025-10-10", "2026-10-02")
T_SUB = (("2020-10-05", "2021-09-30"), ("2021-10-01", "2022-09-30"), ("2022-10-01", "2023-09-29"))
MIN_TRADES_PER_YEAR = 30
N_COMBOS = 119
COST = C.COST_RT_JUDGE

# 현행판(단계별 기본값)
ENTRY0 = dict(entry_n=20, vol_mult=1.5, rs=False, clv=None, mu="cur")
EXIT0 = dict(r=(8.0, 1.5), be_r=3.0, time_bars=20, chan=10)
ACCT0 = dict(slots=(6, 0.15), daily_cap=3)

GRID_A = [dict(entry_n=a, vol_mult=b, rs=c, clv=d, mu=e) for a, b, c, d, e in itertools.product(
    (20, 55), (1.5, 2.5), (False, True), (None, 0.6), ("cur", "m1"))]
GRID_B = [dict(r=a, be_r=b, time_bars=c, chan=d) for a, b, c, d in itertools.product(
    ((8.0, 1.5), (6.0, 1.5), (10.0, 1.5), (6.0, 2.5)), (2.0, 3.0, 4.0), (10, 20, 30), (10, 20))]
GRID_C = [dict(slots=a, daily_cap=b) for a, b in itertools.product(
    ((6, 0.15), (4, 0.25), (5, 0.20), (8, 0.12), (10, 0.10)), (2, 3, 5))]
assert len(GRID_A) + len(GRID_B) + len(GRID_C) == N_COMBOS


# ── 신호 · 청산 층 ─────────────────────────────────────────────────────

def market_close_on_cal(kser: pd.Series, cal: pd.DatetimeIndex) -> np.ndarray:
    return kser.reindex(cal).ffill().to_numpy(float)


def features_opt(b: dict, mem: np.ndarray, kc: np.ndarray, *, entry_n: int = 20, vol_mult: float = 1.5,
                 rs: bool = False, clv: "float | None" = None) -> dict:
    """``DK.features(turnover="cv")`` 의 확장. 현행 인자(20 · 1.5 · 끔 · 끔)면 ``cond`` 가 같다.

    - ``entry_n``: 돌파 기준 = 직전 ``entry_n`` 봉 고가
    - ``rs``: 종목 60봉 수익률 > 069500 같은 60봉 수익률(``kc`` = 전역 달력 위 069500 종가)
    - ``clv``: (종가 − 저가) ÷ (고가 − 저가) ≥ ``clv`` (고가 = 저가면 탈락)
    """
    f = DK.features(b, mem, turnover="cv")
    o, h, l, c = b["o"], b["h"], b["l"], b["c"]
    n = len(c)
    cond = f["cond"].copy()
    if entry_n != 20:
        ph = IND.prior_max(h, entry_n)
        with np.errstate(invalid="ignore"):
            brk = np.nan_to_num((c > ph) & (ph > 0)).astype(bool)
        # 20봉 돌파 항을 갈아 끼운다(나머지 항은 ``DK.features`` 와 같은 식)
        cond = _cond_wo_breakout(b, f, mem, vol_mult=1.5) & brk
        f["prior_high"] = ph
    if vol_mult != 1.5:
        tvx, avg = f["turnover"], f["turnover_avg20"]
        with np.errstate(invalid="ignore"):
            cond = cond & np.nan_to_num(tvx >= vol_mult * avg).astype(bool)
    if rs:
        di = b["di"]
        ok = np.zeros(n, bool)
        j = np.arange(60, n)
        with np.errstate(invalid="ignore", divide="ignore"):
            rs_s = c[j] / c[j - 60] - 1
            rs_m = kc[di[j]] / kc[di[j - 60]] - 1
            ok[j] = np.nan_to_num(rs_s > rs_m).astype(bool)
        cond = cond & ok
    if clv is not None:
        rng = h - l
        with np.errstate(invalid="ignore", divide="ignore"):
            cl = np.where(rng > 0, (c - l) / np.where(rng > 0, rng, 1.0), np.nan)
            cond = cond & np.nan_to_num(cl >= clv).astype(bool)
    f["cond"] = cond
    f["chan20"] = IND.prior_min(l, 20)
    return f


def _cond_wo_breakout(b: dict, f: dict, mem: np.ndarray, vol_mult: float) -> np.ndarray:
    """``DK.features`` 의 조건에서 20봉 돌파 항만 뺀 것(같은 식 — 돌파 길이를 바꿀 때 쓴다)."""
    c, tv = b["c"], b["tv"]
    n = len(c)
    ema = IND.ema_fir(c, 60)
    ema_y = np.full(n, np.nan)
    ema_y[1:] = ema[:-1]
    tvx, avg = f["turnover"], f["turnover_avg20"]
    with np.errstate(invalid="ignore"):
        cond = ((np.arange(n) >= 62) & (ema > ema_y) & (c > ema) & (avg > 0) & (tvx >= vol_mult * avg)
                & (f["atr"] > 0) & mem & (tv >= DK.ENTRY["min_trade"]) & ~b["notrade"])
    return np.nan_to_num(cond).astype(bool)


def feats_view(f: dict, chan: int) -> dict:
    """``KKPos`` 는 ``f["chan10"]`` 을 읽는다 — 채널 길이를 바꾼 사본을 준다."""
    if chan == 10:
        return f
    g = dict(f)
    g["chan10"] = f["chan20"] if chan == 20 else None
    if g["chan10"] is None:
        raise ValueError(chan)
    return g


def kk_of(ex: dict, acct: dict = ACCT0) -> dict:
    r_floor, r_atr = ex["r"]
    return dict(DK.KK, chan_strict=True, r_floor=r_floor / 100.0, r_atr=r_atr, be_r=ex["be_r"],
                time_bars=ex["time_bars"], max_pos=acct["slots"][0], pr=acct["slots"][1],
                daily_cap=acct["daily_cap"])


def mu_filter(sigs: list, mu: str) -> list:
    if mu == "cur":
        return sigs
    if mu == "m1":
        return [s for s in sigs if s.m >= 1.0]
    raise ValueError(mu)


def signals(st, m, kc, entry: dict, kk: dict, feats_cache: dict) -> "tuple[dict, list]":
    key = (entry["entry_n"], entry["vol_mult"], entry["rs"], entry["clv"])
    if key not in feats_cache:
        feats_cache[key] = {t: features_opt(b, b["mem"].astype(bool), kc, entry_n=key[0], vol_mult=key[1],
                                            rs=key[2], clv=key[3]) for t, b in st.bars.items()}
    feats = feats_cache[key]
    sigs = DK.build_signals(st.bars, feats, m)
    sigs = [s for s in sigs if not DA.r_half_blocked(s.E, s.N, kk)]
    return feats, mu_filter(sigs, entry["mu"])


# ── 지표 ─────────────────────────────────────────────────────────────

def diff_boot(new_rows: list, cur_rows: list, cal, *, n_boot: int = C.N_BOOT, seed: int = C.BOOT_SEED,
              qs=(C.BOOT_Q,)) -> dict:
    """두 판 평균 차(new − cur)의 블록 부트스트랩. 블록 = 진입일 ISO 주(종목 무관, 두 판 공통)."""
    def wk(gd):
        y, w, _ = cal[gd].date().isocalendar()
        return f"{y}-W{w:02d}"
    keys = sorted({wk(x["gd"]) for x in new_rows} | {wk(x["gd"]) for x in cur_rows})
    ix = {k: i for i, k in enumerate(keys)}
    K = len(keys)

    def sums(rows):
        idx = np.fromiter((ix[wk(x["gd"])] for x in rows), dtype=np.int64, count=len(rows))
        v = np.array([x["net"] for x in rows], float)
        return np.bincount(idx, weights=v, minlength=K), np.bincount(idx, minlength=K).astype(float)
    a1, a0 = sums(new_rows)
    b1, b0 = sums(cur_rows)
    est = float(a1.sum() / a0.sum() - b1.sum() / b0.sum())
    rng = np.random.default_rng(seed)
    cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=n_boot).astype(float)
    dot = lambda x: np.einsum("ij,j->i", cnt, x)  # noqa: E731  (matmul 은 macOS BLAS 가 거짓 경고를 낸다)
    stat = dot(a1) / dot(a0) - dot(b1) / dot(b0)
    return {"diff": est, "blocks": K, "n_boot": n_boot,
            **{f"q{q:g}": float(np.quantile(stat, q)) for q in qs}}


def pop_stats(pop: list, cal, sub_windows=()) -> dict:
    rows = DA.pop_rows(pop, COST)
    if not rows:
        return {"n": 0, "rows": rows}
    p = DA.p1_of(rows, cal)
    keys = [J.iso_week_key(x["t"], cal[x["gd"]].date()) for x in rows]
    _, rlo, _ = J.cluster_bootstrap([x["R"] for x in rows], keys, order="sorted")
    out = {"n": p["n"], "mean": p["mean"], "lo90": p["lo90"], "hi90": p["hi90"], "R_mean": p["R_mean"],
           "R_lo90": rlo, "win_rate": p["win_rate"], "mean_ex_top1pct": p["mean_ex_top1pct"],
           "exit_reasons": {k: int(v) for k, v in p["exit_reasons"].items()},
           "hold_median": float(np.median([x["hold"] for x in rows if x["hold"] is not None]))
           if any(x["hold"] is not None for x in rows) else None, "rows": rows}
    subs = []
    for a, b in sub_windows:
        v = [x["net"] for x in rows if pd.Timestamp(a) <= cal[x["gd"]] <= pd.Timestamp(b)]
        subs.append({"win": [a, b], "n": len(v), "mean": float(np.mean(v)) if v else None})
    if sub_windows:
        out["sub"] = subs
        out["robust"] = sum(1 for s in subs if s["mean"] is not None and s["mean"] > 0) >= 2
    return out


def strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "rows"}


def n_changed(cfg: dict, base: dict) -> int:
    return sum(1 for k in base if cfg[k] != base[k])


def pick(cands: list, base: dict, min_n: int) -> "tuple[dict, str]":
    """규약 2 선택: 거래 수 하한 → 강건 우선 → 90% 하한 최대 → 동률이면 현행에 가까운 쪽."""
    ok = [x for x in cands if x["T"]["n"] >= min_n and np.isfinite(x["T"].get("lo90", np.nan))]
    rob = [x for x in ok if x["T"].get("robust")]
    pool, note = (rob, "강건") if rob else (ok, "강건 아님")
    best = max(x["T"]["lo90"] for x in pool)
    tied = [x for x in pool if best - x["T"]["lo90"] < 1e-9]
    return min(tied, key=lambda x: n_changed(x["cfg"], base)), note


# ── 실행 ─────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    here = os.path.join(C.REPO, "_workspace/analysis/strategy_opt_20261005/donchian")
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(here, "result.json")
    if DA.PN.sha256(os.path.join(here, "prereg.md")) != PREREG_SHA:
        raise SystemExit("[opt-donchian] prereg.md sha256 불일치 — 동결본이 아니다. 멈춘다")
    st, m, kser, seam, _ = DA.build_inputs()
    cal = st.cal
    kc = market_close_on_cal(kser, cal)

    def gd_of(d, side="left"):
        return int(cal.searchsorted(pd.Timestamp(d), side=side)) - (1 if side == "right" else 0)

    win = {k: (gd_of(a), gd_of(b, "right")) for k, (a, b) in {"T": T, "V": V, "H": H}.items()}
    t_years = (pd.Timestamp(T[1]) - pd.Timestamp(T[0])).days / 365.25
    min_n = int(np.ceil(MIN_TRADES_PER_YEAR * t_years))
    cls = load_strategy_class(DA.BRANCH_DONCHIAN, "DonchianSwingStrategy", "opt_branch_donchian_kk")
    fc: dict = {}
    res = {"prereg_sha256": PREREG_SHA, "n_combos": N_COMBOS, "min_T_trades": min_n,
           "windows": {"T": T, "V": V, "H": H, "T_sub": T_SUB}, "seam": seam}

    def pop_for(entry, ex, w, mode="color", acct=ACCT0):
        kk = kk_of(ex, acct)
        feats, sigs = signals(st, m, kc, entry, kk, fc)
        fv = {t: feats_view(f, ex["chan"]) for t, f in feats.items()}
        return DK.population(sigs, st.bars, fv, *win[w], mode=mode, kk=kk), sigs, fv, kk

    def books(entry, ex, acct, w, cost=COST, mode="color"):
        kk = kk_of(ex, acct)
        feats, sigs = signals(st, m, kc, entry, kk, fc)
        fv = {t: feats_view(f, ex["chan"]) for t, f in feats.items()}
        op = OpSizer(cls, "donchian_swing", {"market_unit_mode": "enforce", "risk_pct": kk["risk_pct"],
                                             "position_ratio": acct["slots"][1],
                                             "max_positions": acct["slots"][0],
                                             "kk_r_floor_pct": ex["r"][0], "kk_r_atr_mult": ex["r"][1]})
        rng = {"T": T, "V": V, "H": H}[w]
        sm = DA.run_books(sigs, st, fv, rng, kk, op, cost_rt=cost, mode=mode)
        v = DA.book_view(sm)
        v["per_seed_cagr"] = [x["cagr"] for x in sm["per_seed"]]
        return v

    # 단계 A
    A = []
    for cfg in GRID_A:
        pop, *_ = pop_for(cfg, EXIT0, "T")
        A.append({"cfg": cfg, "T": pop_stats(pop, cal, T_SUB)})
    selA, noteA = pick(A, ENTRY0, min_n)
    print(f"[opt-donchian] A 선택 {selA['cfg']} lo90 {selA['T']['lo90']:+.5f} ({noteA})", f"{time.time()-t0:.0f}s",
          flush=True)
    # 단계 B
    Bs = []
    for cfg in GRID_B:
        pop, *_ = pop_for(selA["cfg"], cfg, "T")
        Bs.append({"cfg": cfg, "T": pop_stats(pop, cal, T_SUB)})
    selB, noteB = pick(Bs, EXIT0, min_n)
    print(f"[opt-donchian] B 선택 {selB['cfg']} lo90 {selB['T']['lo90']:+.5f} ({noteB})", f"{time.time()-t0:.0f}s",
          flush=True)
    # 단계 C (규약 밖 추가 규칙 — prereg §3)
    Cs = []
    for cfg in GRID_C:
        bv = books(selA["cfg"], selB["cfg"], cfg, "T")
        ok = (bv["mdd_median"] >= C.P3_MDD and bv["fills_per_year_median"] >= C.P4_FILLS_PER_YEAR
              and not (bv["unaffordable_ratio_median"] == bv["unaffordable_ratio_median"]
                       and bv["unaffordable_ratio_median"] >= C.P4_UNAFF))
        Cs.append({"cfg": cfg, "T_book": bv, "eligible": ok})
    elig = [x for x in Cs if x["eligible"]] or Cs
    bestc = max(x["T_book"]["cagr_median"] for x in elig)
    selC = min([x for x in elig if bestc - x["T_book"]["cagr_median"] < 1e-12], key=lambda x: n_changed(x["cfg"], ACCT0))
    print(f"[opt-donchian] C 선택 {selC['cfg']} T cagr {selC['T_book']['cagr_median']:+.4f}", f"{time.time()-t0:.0f}s",
          flush=True)

    def ser(lst):
        return [{"cfg": {k: (list(v) if isinstance(v, tuple) else v) for k, v in x["cfg"].items()},
                 **{k: (strip(v) if isinstance(v, dict) and "rows" in v else v) for k, v in x.items() if k != "cfg"}}
                for x in lst]
    res["stageA"] = {"selected": ser([selA])[0], "note": noteA, "grid": ser(A)}
    res["stageB"] = {"selected": ser([selB])[0], "note": noteB, "grid": ser(Bs)}
    res["stageC"] = {"selected": ser([selC])[0], "grid": ser(Cs)}
    # R 기준 순위(보고만)
    for name, lst in (("A", A), ("B", Bs)):
        okl = [x for x in lst if x["T"]["n"] >= min_n]
        res[f"stage{name}"]["best_by_R_lo90"] = ser([max(okl, key=lambda x: x["T"]["R_lo90"])])[0]

    # ── 판정 (V 한 번 · H 부호) ──
    cur = (ENTRY0, EXIT0, ACCT0)
    new = (selA["cfg"], selB["cfg"], selC["cfg"])
    newAB = (selA["cfg"], selB["cfg"], ACCT0)
    J_ = {}
    for tag, (en, ex, ac) in {"current": cur, "selected": new}.items():
        R = {}
        for w in ("T", "V", "H"):
            pop, sigs, fv, kk = pop_for(en, ex, w)
            R[f"pop_{w}"] = pop_stats(pop, cal)
        popA, *_ = pop_for(en, ex, "V", mode="adverse")
        R["P5_V"] = J.p5(R["pop_V"]["mean"], pop_stats(popA, cal)["mean"])
        R["P1_V"] = {k: R["pop_V"][k] for k in ("n", "mean", "lo90", "hi90")}
        R["P1_V"]["pass"] = bool(R["pop_V"]["mean"] > 0 and R["pop_V"]["lo90"] > C.P1_LO)
        R["P2_H"] = J.p2([x["net"] for x in R["pop_H"]["rows"]], R["pop_V"]["mean"])
        R["pop_V_cost_sens"] = {str(c): float(np.mean([x["net"] + COST - c for x in R["pop_V"]["rows"]]))
                                for c in C.COST_RT_SENS}
        pop, sigs, fv, kk = pop_for(en, ex, "V")
        R["random_control_V"] = DA.random_control(pop, st, fv, win["V"][1], kk, COST)
        for w in ("T", "V", "H"):
            R[f"book_{w}"] = books(en, ex, ac, w)
        R["P3_V"] = J.p3(R["book_V"])
        R["P4_V"] = J.p4(R["book_V"])
        R["book_V_adverse"] = {k: v for k, v in books(en, ex, ac, "V", mode="adverse").items()
                               if k in ("cagr_median", "mdd_median")}
        J_[tag] = R
    if selC["cfg"] != ACCT0:
        J_["selected_AB_currentC"] = {f"book_{w}": books(*newAB, w) for w in ("T", "V", "H")}
    # 규약 3 차이 판정
    q_bonf = 0.05 / N_COMBOS
    dV = diff_boot(J_["selected"]["pop_V"]["rows"], J_["current"]["pop_V"]["rows"], cal)
    dVb = diff_boot(J_["selected"]["pop_V"]["rows"], J_["current"]["pop_V"]["rows"], cal, n_boot=20000,
                    qs=(q_bonf,))
    dT = diff_boot(J_["selected"]["pop_T"]["rows"], J_["current"]["pop_T"]["rows"], cal)
    dH = diff_boot(J_["selected"]["pop_H"]["rows"], J_["current"]["pop_H"]["rows"], cal)
    sv, cv = J_["selected"]["book_V"]["per_seed_cagr"], J_["current"]["book_V"]["per_seed_cagr"]
    seeds_better = int(sum(a > b for a, b in zip(sv, cv)))
    rule3 = bool(dV["diff"] > 0 and dV[f"q{C.BOOT_Q:g}"] > 0)
    rule3_bonf = bool(dV["diff"] > 0 and dVb[f"q{q_bonf:g}"] > 0)
    p_all = bool(J_["selected"]["P1_V"]["pass"] and J_["selected"]["P2_H"].get("pass")
                 and J_["selected"]["P3_V"]["pass"] and J_["selected"]["P4_V"]["pass"]
                 and J_["selected"]["P5_V"]["label"] == "유지")
    h_flip = bool(np.sign(dH["diff"]) != np.sign(dV["diff"]))
    label = ("채택 권고" if (rule3 and p_all and not h_flip) else
             "보류" if (rule3 and h_flip) else "현행 유지")
    res["judge"] = {"diff_T": dT, "diff_V": dV, "diff_V_bonferroni": dVb, "diff_H": dH,
                    "rule3_pass": rule3, "rule3_bonferroni_pass": rule3_bonf, "P1toP5_pass": p_all,
                    "H_flip": h_flip, "V_book_seeds_selected_better": seeds_better,
                    "stageC_adopt": bool(selC["cfg"] == ACCT0 or seeds_better >= 12), "label": label}
    res["detail"] = {k: {kk_: (strip(v) if isinstance(v, dict) and "rows" in v else v) for kk_, v in R.items()}
                     for k, R in J_.items()}
    res["elapsed_s"] = time.time() - t0
    with open(out_path, "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else (list(o) if isinstance(o, tuple) else str(o)))
    print(f"[opt-donchian] 판정 {label} · V 차 {dV['diff']:+.5f} 하한 {dV[f'q{C.BOOT_Q:g}']:+.5f} · H 차 {dH['diff']:+.5f}",
          f"· 씨앗 우위 {seeds_better}/16 · {out_path}", f"{res['elapsed_s']:.0f}s", flush=True)


if __name__ == "__main__":
    main()
