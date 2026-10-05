#!/usr/bin/env python3
"""전략 효율화(2026-10-05) — vcp_breakout · bull_flag_breakout 탐색·판정 실행.

정본 = ``_workspace/analysis/strategy_opt_20261005/{vcp,bfb}/prereg.md``(실행 전 sha256 동결) + 메인 세션 공통 규약.
재현 층 = 전수 점검 엔진 ``bfb_vcp_engine``(운영 메서드 대조 테스트 통과본) — 이 파일은 그 위에 진입 방식 3종
(장중 추격 · 종가 확인 · 다음 날 시가) · 청산 변형 · 시장 유닛 사용법만 얹는다. 엔진 파일은 고치지 않는다.

기간: 학습 T(선택) · 검증 V(고른 판 + 현행만) · 보류 H(마지막 한 번, 부호만).
실행: python3 tools/replay/strategies/bfb_vcp_opt.py vcp|bfb
산출: ``_workspace/analysis/strategy_opt_20261005/{vcp,bfb}/results.json`` · ``grid_T.csv``
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from collections import Counter, defaultdict
from dataclasses import replace

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import bars as BR  # noqa: E402
from replay.audit import book as BK  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.strategies import bfb_vcp_engine as EN  # noqa: E402

# ── 고정값(prereg 와 같다) ─────────────────────────────────────────────────────────
T_WIN = ("2020-10-05", "2023-09-29")
V_WIN = ("2023-10-04", "2025-10-02")
H_WIN = ("2025-10-10", "2026-10-02")
T_SUB = (("2020-10-05", "2021-09-30"), ("2021-10-01", "2022-09-30"), ("2022-10-01", "2023-09-29"))
LIVE_SLIP = 0.0193                    # BFB 실거래 14건 운영 체결가 ÷ 재현 체결가 평균(전수 점검 B1)
MIN_TRADES_PER_YEAR = 30
DIFF_BOOT = 20000
OUT_ROOT_REL = "_workspace/analysis/strategy_opt_20261005"

SETUPS = {
    "vcp": {"cur": {}, "strict": dict(base_depth_pct=0.30, pullback_count_min=2, last_pullback_max=0.12,
                                       volume_contraction_ratio=0.70)},
    "bfb": {"cur": {}, "strict": dict(pole_min_return=20, flag_retracement_max=0.38)},
}
EXITS = {
    "vcp": {"X0": dict(stop_atr=2.0, atr_trail_mult=2), "X1": dict(stop_atr=2.0, atr_trail_mult=3),
            "X2": dict(stop_atr=1.5, atr_trail_mult=2), "X3": dict(stop_atr=2.0, atr_trail_mult=4)},
    "bfb": {"X0": dict(max_hold_days=5, _target=True), "X1": dict(max_hold_days=10, _target=True),
            "X2": dict(max_hold_days=10, atr_trail_mult=3, _target=True),
            "X3": dict(max_hold_days=10, atr_trail_mult=3, _target=False)},
}
ALT_CAP = 3.0
MU_THR = {"all": 0.0, "ge075": 0.75, "eq1": 1.0}       # m > 0(현행) · m ≥ 0.75 · m = 1 만 진입


def entries_for(kind: str) -> "list[tuple]":
    """(이름, 방식, 추격 상한%, 거래량 배수 k). 방식 I = 장중 추격(실거래 보정 체결) · C = 종가 확인 · N = 다음 날 시가."""
    cur = float((EN.VCP_DB if kind == "vcp" else EN.BFB_DB)["max_breakout_extension_pct"])
    out = [("I", "I", cur, 0.0)]
    for cap, k in itertools.product((cur, ALT_CAP), (0.0, 1.5)):
        out.append((f"C_cap{cap:g}_k{k:g}", "C", cap, k))
    for k in (0.0, 1.5):
        out.append((f"N_k{k:g}", "N", cur, k))
    return out


def grid(kind: str) -> "list[dict]":
    out = []
    for s, e, x, m in itertools.product(SETUPS[kind], entries_for(kind), EXITS[kind], MU_THR):
        out.append({"id": f"{s}|{e[0]}|{x}|{m}", "setup": s, "entry": e, "exit": x, "mu": m})
    return out


CURRENT_ID = "cur|I|X0|all"


def params_for(kind: str, setup: str, exit_: str) -> dict:
    p = dict(EN.VCP_DB if kind == "vcp" else EN.BFB_DB)
    p.update(SETUPS[kind][setup])
    p.update({k: v for k, v in EXITS[kind][exit_].items() if not k.startswith("_")})
    p["_target"] = EXITS[kind][exit_].get("_target", True)
    return p


# ── 신호 ─────────────────────────────────────────────────────────────────────────

def build_signals_opt(bars: dict, feats: dict, m_for_day: np.ndarray, p: dict, universe: dict, *,
                      method: str, cap: float, k: float, slip: float = LIVE_SLIP,
                      close_slip: float = 0.0) -> "list[EN.Sig]":
    """후보(신호 봉 i) ∧ 유니버스(i) → 진입.

    I(장중 추격) = 전수 점검 엔진 ``build_signals(slip=)`` 그대로(체결가 = min(고가, max(시가, 돌파선 × (1+slip)))) ·
    C(종가 확인) = D 종가 > 돌파선 ∧ D 종가 ≤ 돌파선 × (1+cap%) ∧ D 거래량 ≥ k × 평균 → D 종가 체결(× (1+close_slip)) ·
    N(다음 날 시가) = D 종가 > 돌파선 ∧ D 거래량 ≥ k × 평균 → D+1 시가 체결, D+1 시가 ≤ 돌파선 × (1+cap%) ·
    상한가 시가(+29%) 진입 없음. ATR = 체결 시점에 아는 마지막 봉까지(C = i, N = D).
    """
    if method == "I":
        pp = dict(p, max_breakout_extension_pct=cap)
        return EN.build_signals(bars, feats, m_for_day, pp, universe, slip=slip)
    out = []
    for t, b in bars.items():
        f = feats[t]
        n = len(b["c"])
        ok = f["cand"][:-1] & universe[t][:-1]
        for i in np.nonzero(ok)[0]:
            D = i + 1
            if b["di"][D] != b["di"][i] + 1 or b["notrade"][D]:
                continue
            line = float(f["line"][i])
            Cd = float(b["c"][D])
            if not (Cd > line > 0):
                continue
            avg = float(f["avg"][i])
            thr = avg * k
            if k > 0 and not (avg > 0 and b["vol"][D] >= thr):
                continue
            vr = float(b["vol"][D] / avg) if avg > 0 else float("nan")
            if method == "C":
                if Cd > line * (1 + cap / 100.0) or BR.limit_up_open(Cd, b["c"][i]):
                    continue
                E = Cd * (1 + close_slip)
                ti, N = D, float(f["atr"][i])
                kind_ = "close"
            elif method == "N":
                E1 = D + 1
                if E1 >= n or b["di"][E1] != b["di"][D] + 1 or b["notrade"][E1]:
                    continue
                O = float(b["o"][E1])
                if not (O > 0) or BR.limit_up_open(O, Cd) or O > line * (1 + cap / 100.0):
                    continue
                E, ti, N = O, E1, float(f["atr"][D])
                kind_ = "gap"
            else:
                raise ValueError(method)
            if not (N > 0):
                continue
            mv = m_for_day[b["di"][ti]]
            mv = 1.0 if (mv is None or not np.isfinite(mv)) else float(mv)
            out.append(EN.Sig(t, int(ti), int(b["di"][ti]), float(E), float(E * b["raw"][ti]), N, line,
                              float(f["low"][i]), float(f["target"][i]), mv, True, kind_, vr))
    out.sort(key=lambda s: (s.gd, s.ticker))
    return out


# ── 포지션 ───────────────────────────────────────────────────────────────────────

class OPos(EN.BPos):
    """전수 점검 ``BPos`` + 종가 진입(진입 봉 경로 없음) · BFB 측정 이동 익절 끄기(``p['_target']``)."""

    def entry_seq(self):
        if self.s.entry == "close":
            return self.s.E, ()
        return super().entry_seq()

    def _target(self) -> float:
        if not self.p.get("_target", True):
            return float("inf")
        return super()._target()


def run_path(sig, b, f, end_gd, *, kind, p, cal, mode="color") -> OPos:
    ps = OPos(sig, b, f, 1, kind=kind, p=p, cal=cal, mode=mode)
    if ps.intraday_phase(sig.ti, sig.gd, True):
        return ps
    for t in range(sig.ti + 1, len(b["c"])):
        gd = int(b["di"][t])
        if gd > end_gd:
            break
        if ps.open_phase(t, gd) or ps.intraday_phase(t, gd, False):
            return ps
    ps._exit(ps.last_px, "END", None)
    return ps


def population(sigs, bars, feats, g0, g1, *, kind, p, cal, mu_thr=0.0, mode="color") -> "list[OPos]":
    """전수 점검 ``population`` 과 같은 규칙(종목마다 앞 거래 청산 + 쿨다운 뒤 · m ≤ 0 진입 없음) + m ≥ mu_thr."""
    out, busy = [], {}
    cd = int(p["reentry_cooldown_days"])
    for s in sigs:
        if s.gd < g0 or s.gd > g1 or s.m <= 0 or s.m < mu_thr:
            continue
        if busy.get(s.ticker, -1) >= s.gd:
            continue
        ps = run_path(s, bars[s.ticker], feats[s.ticker], g1, kind=kind, p=p, cal=cal, mode=mode)
        busy[s.ticker] = (ps.exit_gd + cd) if ps.exit_gd is not None else 10 ** 9
        out.append(ps)
    return out


def rows_of(pop, cal, cost_rt=C.COST_RT_JUDGE):
    return [dict(t=ps.s.ticker, d=str(cal[ps.s.gd].date()), gd=ps.s.gd, r=EN.net_ret(ps, cost_rt),
                 why=ps.exit_reason, m=ps.s.m, entry=ps.s.entry,
                 hold=(ps.exit_gd - ps.s.gd) if ps.exit_gd is not None else None) for ps in pop]


# ── 통계 ─────────────────────────────────────────────────────────────────────────

def stat_block(rows, years: float) -> dict:
    if not rows:
        return {"n": 0, "per_year": 0.0, "mean": float("nan"), "lo90": float("nan")}
    r = J.p1([x["r"] for x in rows], [x["t"] for x in rows], [x["d"] for x in rows])
    v = np.array([x["r"] for x in rows])
    return {"n": len(rows), "per_year": len(rows) / years, "mean": r["mean"], "lo90": r["lo90"],
            "hi90": r["hi90"], "median": float(np.median(v)), "win": float((v > 0).mean())}


def sub_means(rows, subs) -> "list[float]":
    out = []
    for a, b in subs:
        v = [x["r"] for x in rows if a <= x["d"] <= b]
        out.append(float(np.mean(v)) if v else float("nan"))
    return out


def month_block_diff(rows_a, rows_b, *, n_boot: int = DIFF_BOOT, seed: int = C.BOOT_SEED,
                     qs=(0.05,)) -> dict:
    """달력 월 블록 부트스트랩 — 같은 월 집합을 뽑아 (A 평균 − B 평균). 반환 = 점추정 + 분위수별 하한."""
    months = sorted({x["d"][:7] for x in rows_a} | {x["d"][:7] for x in rows_b})
    ix = {m: i for i, m in enumerate(months)}
    K = len(months)

    def sums(rows):
        s1 = np.zeros(K)
        s0 = np.zeros(K)
        for x in rows:
            s1[ix[x["d"][:7]]] += x["r"]
            s0[ix[x["d"][:7]]] += 1
        return s1, s0
    a1, a0 = sums(rows_a)
    b1, b0 = sums(rows_b)
    est = a1.sum() / a0.sum() - b1.sum() / b0.sum()
    rng = np.random.default_rng(seed)
    cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=n_boot).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        st = (np.einsum("ij,j->i", cnt, a1) / np.einsum("ij,j->i", cnt, a0)
                  - np.einsum("ij,j->i", cnt, b1) / np.einsum("ij,j->i", cnt, b0))
    st = st[np.isfinite(st)]
    return {"est": float(est), "months": K, "n_boot_valid": int(len(st)),
            "lower": {f"{q:.6g}": float(np.quantile(st, q)) for q in qs}}


def years_of(cal, g0, g1) -> float:
    return (g1 - g0 + 1) / 252.0


# ── 계좌 ─────────────────────────────────────────────────────────────────────────

class _CD:
    def __init__(self, sbg, cd):
        self.sbg, self.cd, self.last = sbg, cd, {}

    def note_exit(self, t, gd):
        self.last[t] = gd

    def get(self, gd, default=None):
        return [s for s in self.sbg.get(gd, default or [])
                if not (self.last.get(s.ticker) is not None and gd <= self.last[s.ticker] + self.cd)]


def run_books_opt(sigs, st, feats, kind, p, cls, win, *, mu_thr=0.0, mode="color", seeds=C.BOOK_SEEDS):
    from replay.audit.sizing import OpSizer
    sid = "vcp_breakout" if kind == "vcp" else "bull_flag_breakout"
    op = OpSizer(cls, sid, {k: v for k, v in p.items() if not k.startswith("_")}, atr_keys=("atr14",))
    sbg = defaultdict(list)
    for s in sigs:
        sbg[s.gd].append(s)
    runs = []
    for seed in seeds:
        cs = _CD(sbg, int(p["reentry_cooldown_days"]))

        def size_fn(s, B, used):
            P = int(round(s.E_raw))
            if s.m <= 0 or s.m < mu_thr:
                return 0, "mu"
            N_raw = s.N * (s.E_raw / s.E)
            if op.blocks_entry(P, N_raw, budget=int(B), used=int(used), m=s.m, ticker=s.ticker):
                return 0, "mu"
            q = op.qty(P, N_raw, budget=int(B), used=int(used), m=s.m, ticker=s.ticker)
            if q > 0:
                return q, "ok"
            return 0, ("funds" if int(B) - int(used) < P else "design")

        def open_pos(s, q, _cs=cs):
            return OPos(s, st.bars[s.ticker], feats[s.ticker], q, kind=kind, p=p, cal=st.cal, mode=mode,
                        on_exit=_cs.note_exit)
        runs.append(BK.run_book(cs, open_pos, size_fn, st.cal, win[0], win[1], seed,
                                start_equity=float(C.BUDGET_C7), cost_side=C.COST_RT_JUDGE / 2,
                                max_pos=int(p["max_positions"]), daily_cap=None))
    sm = BK.book_summary(runs, float(C.BUDGET_C7))
    sm["recon_max_abs"] = float(max(abs(r["recon"]) for r in runs))
    return {k: sm[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median", "fills_per_year_median",
                               "unaffordable_ratio_median", "trades_median", "recon_max_abs")}


# ── 메인 ─────────────────────────────────────────────────────────────────────────

def _audit():
    from replay.strategies import bfb_vcp_audit as AU
    return AU


def run(kind: str):
    t0 = time.time()
    AU = _audit()
    if kind == "vcp":
        from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy as cls
        featf = EN.vcp_features
    else:
        from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy as cls
        featf = EN.bfb_features
    od = os.path.join(C.REPO, OUT_ROOT_REL, kind)
    prereg = os.path.join(od, "prereg.md")
    sha_file = prereg + ".sha256"
    frozen = open(sha_file).read().split()[0]
    if AU.PN.sha256(prereg) != frozen:
        raise SystemExit("prereg.md 가 동결 sha 와 다르다 — 실행 중단")
    out = {"strategy": kind, "prereg_sha256": frozen,
           "opt_sha256": AU.PN.sha256(__file__),
           "engine_sha256": AU.PN.sha256(os.path.join(os.path.dirname(__file__), "bfb_vcp_engine.py"))}
    st, m, master, ext, ext_sha, bench = AU.load(kind)
    out["db_extract_sha256"] = ext_sha
    cal = st.cal

    def gw(w):
        return (int(cal.searchsorted(pd.Timestamp(w[0]))), int(cal.searchsorted(pd.Timestamp(w[1]), side="right")) - 1)
    gT, gV, gH = gw(T_WIN), gw(V_WIN), gw(H_WIN)
    yT, yV, yH = years_of(cal, *gT), years_of(cal, *gV), years_of(cal, *gH)
    out["years"] = {"T": yT, "V": yV, "H": yH}

    feats_by, asof_by = {}, {}
    for s in SETUPS[kind]:
        p_s = params_for(kind, s, "X0")
        asof_by[s], _ = AU.universes(st, master, p_s)
        feats_by[s] = {t: featf(b, p_s) for t, b in st.bars.items()}
        print(f"[{kind}] features {s} {time.time()-t0:.0f}s", flush=True)

    sig_cache = {}

    def sigs_of(setup, entry):
        key = (setup, entry[0])
        if key not in sig_cache:
            _, meth, cap, k = entry
            p_s = params_for(kind, setup, "X0")
            sig_cache[key] = build_signals_opt(st.bars, feats_by[setup], m, p_s, asof_by[setup],
                                               method=meth, cap=cap, k=k)
        return sig_cache[key]

    # ── 0. 재현 확인(선택과 무관): I + slip 0.02 · W5y 가 전수 점검 보고판과 같은가
    p0 = params_for(kind, "cur", "X0")
    chk_sigs = EN.build_signals(st.bars, feats_by["cur"], m, p0, asof_by["cur"], slip=0.02)
    g5 = gw(C.W5Y)
    chk = population(chk_sigs, st.bars, feats_by["cur"], *g5, kind=kind, p=p0, cal=cal)
    out["repro_check_w5y_slip002"] = stat_block(rows_of(chk, cal), years_of(cal, *g5))
    print(f"[{kind}] repro {out['repro_check_w5y_slip002']}", flush=True)

    # ── 1. 학습 T 탐색
    G = grid(kind)
    rows_T = []
    for gi, g in enumerate(G):
        p_g = params_for(kind, g["setup"], g["exit"])
        sg = sigs_of(g["setup"], g["entry"])
        pop = population(sg, st.bars, feats_by[g["setup"]], *gT, kind=kind, p=p_g, cal=cal,
                         mu_thr=MU_THR[g["mu"]])
        rr = rows_of(pop, cal)
        sb = stat_block(rr, yT)
        sm = sub_means(rr, T_SUB)
        sb.update(id=g["id"], sub_means=sm, sub_pos=int(sum(1 for x in sm if x > 0)),
                  eligible=bool(sb["per_year"] >= MIN_TRADES_PER_YEAR),
                  robust=bool(sum(1 for x in sm if x > 0) >= 2))
        rows_T.append(sb)
        if gi % 12 == 0:
            print(f"[{kind}] T {gi+1}/{len(G)} {g['id']} n {sb['n']} mean {sb['mean']:.4f} lo {sb['lo90']:.4f} "
                  f"{time.time()-t0:.0f}s", flush=True)
    dfT = pd.DataFrame(rows_T)
    dfT.to_csv(os.path.join(od, "grid_T.csv"), index=False)
    elig = dfT[dfT.eligible & dfT.robust].sort_values(["lo90", "mean"], ascending=False)
    chosen_id = str(elig.iloc[0]["id"]) if len(elig) else None
    out["T"] = {"n_combos": len(G), "n_eligible": int(dfT.eligible.sum()),
                "n_eligible_robust": int(len(elig)), "chosen": chosen_id,
                "current": dfT[dfT.id == CURRENT_ID].iloc[0].to_dict(),
                "top10": elig.head(10).to_dict("records")}
    print(f"[{kind}] chosen {chosen_id}", flush=True)

    # ── 2. 검증 V · 3. 보류 H — 현행 + 고른 판만
    gmap = {g["id"]: g for g in G}
    ev = {}
    for name, gid in (("current", CURRENT_ID), ("chosen", chosen_id)):
        if gid is None:
            continue
        g = gmap[gid]
        p_g = params_for(kind, g["setup"], g["exit"])
        sg = sigs_of(g["setup"], g["entry"])
        fe = feats_by[g["setup"]]
        mt = MU_THR[g["mu"]]
        res = {"id": gid}
        R = {}
        for wn, gg, yy in (("T", gT, yT), ("V", gV, yV), ("H", gH, yH)):
            R[wn] = rows_of(population(sg, st.bars, fe, *gg, kind=kind, p=p_g, cal=cal, mu_thr=mt), cal)
            res[wn] = stat_block(R[wn], yy)
            res[wn]["exit_mix"] = dict(Counter(x["why"] for x in R[wn]))
        R["V_adverse"] = rows_of(population(sg, st.bars, fe, *gV, kind=kind, p=p_g, cal=cal, mu_thr=mt,
                                            mode="adverse"), cal)
        res["V_adverse"] = stat_block(R["V_adverse"], yV)
        # 판정(V, 전수 점검 P1·P2·P5 + 계좌 P3·P4)
        res["P1_V"] = J.p1([x["r"] for x in R["V"]], [x["t"] for x in R["V"]], [x["d"] for x in R["V"]])
        res["P2_H_vs_V"] = J.p2([x["r"] for x in R["H"]], res["V"]["mean"])
        res["P5_V"] = J.p5(res["V"]["mean"], res["V_adverse"]["mean"])
        res["book_V"] = run_books_opt(sg, st, fe, kind, p_g, cls, V_WIN, mu_thr=mt)
        res["P3_V"] = J.p3(res["book_V"])
        res["P4_V"] = J.p4(res["book_V"])
        res["book_T"] = run_books_opt(sg, st, fe, kind, p_g, cls, T_WIN, mu_thr=mt)
        res["book_H"] = run_books_opt(sg, st, fe, kind, p_g, cls, (H_WIN[0], H_WIN[1]), mu_thr=mt)
        if g["entry"][1] == "C":       # 종가 체결 민감도(보고만): 종가 + 0.5%
            _, meth, cap, k = g["entry"]
            sgs = build_signals_opt(st.bars, fe, m, p_g, asof_by[g["setup"]], method=meth, cap=cap, k=k,
                                    close_slip=0.005)
            res["V_close_slip0.005"] = stat_block(rows_of(population(sgs, st.bars, fe, *gV, kind=kind, p=p_g,
                                                                     cal=cal, mu_thr=mt), cal), yV)
        ev[name] = res
        ev[name]["_rows"] = R
        print(f"[{kind}] {name} {gid} V {res['V']['mean']:.4f} lo {res['V']['lo90']:.4f} H {res['H']['mean']:.4f} "
              f"bookV {res['book_V']['cagr_median']:.3f}/{res['book_V']['mdd_median']:.3f} {time.time()-t0:.0f}s",
              flush=True)
    # 차이 검정(V) — 월 블록 부트스트랩, 90% 하한 + Bonferroni 수준
    K = len(G)
    if chosen_id is not None and chosen_id != CURRENT_ID:
        out["diff_V"] = month_block_diff(ev["chosen"]["_rows"]["V"], ev["current"]["_rows"]["V"],
                                         qs=(0.05, 0.05 / K))
        out["diff_V"]["bonferroni_K"] = K
        out["diff_H_sign"] = month_block_diff(ev["chosen"]["_rows"]["H"], ev["current"]["_rows"]["H"],
                                              n_boot=2000, qs=(0.05,))
        out["diff_T"] = month_block_diff(ev["chosen"]["_rows"]["T"], ev["current"]["_rows"]["T"],
                                         n_boot=2000, qs=(0.05,))
    for v in ev.values():
        v.pop("_rows", None)
    out["eval"] = ev
    # 현행 장중판의 「체결 보정 없음」(전수 점검 판정판 체결가) — 보고만
    sg_ns = EN.build_signals(st.bars, feats_by["cur"], m, p0, asof_by["cur"])
    out["current_noslip_ref"] = {wn: stat_block(rows_of(population(sg_ns, st.bars, feats_by["cur"], *gg, kind=kind,
                                                                   p=p0, cal=cal), cal), yy)
                                 for wn, gg, yy in (("T", gT, yT), ("V", gV, yV))}
    out["elapsed_s"] = time.time() - t0
    with open(os.path.join(od, "results.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"[{kind}] done {out['elapsed_s']:.0f}s", flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
