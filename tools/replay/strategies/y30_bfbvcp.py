#!/usr/bin/env python3
"""30년(1996~2026) 재검증 — vcp_breakout · bull_flag_breakout.

정본 = ``_workspace/analysis/strategy_30y_20261006/{vcp,bfb}/prereg.md``(실행 전 sha256 동결) + 메인 세션
30년 규약(``scratchpad/opt/protocol_30y.md``) + 효율화 공통 규약(``scratchpad/opt/protocol.md``).

재현 층 = 전수 점검 엔진 ``bfb_vcp_engine``(후보 판정 · 봉 걷기, 운영 메서드 대조 테스트 통과본) +
효율화 층 ``bfb_vcp_opt``(진입 방식 3종 · 청산 변형 · 시장 유닛 사용법). 두 파일은 고치지 않는다.
이 파일이 더하는 것 = 30년 보관소(``y30_data``) · 시대별 가격제한폭(상한가 시가 · 하한가 잠김) ·
가격제한폭 위반 표시 행 처리 · 시기별 실제 비용 · 시대 중립 유니버스 · 달력 연수 기준 연 복리.

실행: python tools/replay/strategies/y30_bfbvcp.py vcp|bfb [--skip-B]
산출: ``_workspace/analysis/strategy_30y_20261006/{vcp,bfb}/results.json`` · ``grid_T.csv`` · ``trades_A.csv.gz``
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from collections import Counter, defaultdict

for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")          # import 용 더미(값은 쓰이지 않는다)

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_REPO = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay.audit import bars as BR  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.audit import panel as PN  # noqa: E402
from replay.strategies import bfb_vcp_engine as EN  # noqa: E402
from replay.strategies import bfb_vcp_opt as OP  # noqa: E402
from replay.strategies import y30_data as Y  # noqa: E402

# ── 고정값(prereg 와 같다) ─────────────────────────────────────────────────────────
WARMUP_END = "1996-12-31"
T_WIN = ("1997-01-02", "2012-12-28")
V_WIN = ("2013-01-02", "2020-12-30")
H_WIN = ("2021-01-04", "2026-10-02")
T_SUB = (("1997-01-02", "2000-12-31"), ("2001-01-01", "2004-12-31"), ("2005-01-01", "2008-12-31"),
         ("2009-01-01", "2012-12-28"))
ROBUST_MIN_POS = 3                    # 하위 구간 4개 중 양(+) ≥ 3
ERAS = (("1997-01-02", "2001-12-31"), ("2002-01-01", "2006-12-31"), ("2007-01-01", "2011-12-31"),
        ("2012-01-01", "2016-12-31"), ("2017-01-01", "2021-12-31"), ("2022-01-01", "2026-10-02"))
LIVE_SLIP = 0.0193                    # 체결가 보정 기본판(BFB 실거래 14건 평균, 전수 점검 B1)
SLIPPAGE_ALLOWANCE = 0.0015           # 주판정 비용 = 표(수수료+거래세) + 0.15%p — 2026 = 0.38%(규약 문구)
CONST_COST = 0.0038                   # 민감도판 — 일정 왕복 0.38%
MIN_TRADES_PER_YEAR = 30
DIFF_BOOT = 20000
LIMIT_FRAC = 29.0 / 30.0              # 상한가·하한가 판정 = 제한폭 × 29/30(30% 시대 = 운영 1.29·0.71 과 같음)
OUT_ROOT_REL = "_workspace/analysis/strategy_30y_20261006"
# 사전 등록 가설(5년 효율화의 고른 판 — 30년 자료를 보기 전에 고정)
HYP = {"vcp": {"main": "cur|C_cap3_k1.5|X0|all", "entry_only": "cur|C_cap7.5_k0|X0|all"},
       "bfb": {"main": "cur|C_cap5_k0|X2|eq1", "entry_only": "cur|C_cap5_k0|X0|all"}}
CURRENT_ID = OP.CURRENT_ID            # "cur|I|X0|all"


# ── 시대 규칙 ─────────────────────────────────────────────────────────────────────

def limit_up(px: float, prev_c: float, lim: float) -> bool:
    return np.isfinite(px) and np.isfinite(prev_c) and prev_c > 0 and px >= prev_c * (1 + lim * LIMIT_FRAC)


def locked_down(o: float, h: float, l: float, prev_c: float, lim: float) -> bool:
    return (np.isfinite(o) and np.isfinite(prev_c) and prev_c > 0
            and o <= prev_c * (1 - lim * LIMIT_FRAC) and h == l)


class EraCostY(Y.EraCost):
    """주판정 = 표 + 0.15%p(매수·매도 반반)."""

    def __init__(self, cal, *, const=None, allowance=SLIPPAGE_ALLOWANCE):
        super().__init__(cal, const=const)
        if const is None:
            self.fee = self.fee + allowance / 2


# ── 신호 ─────────────────────────────────────────────────────────────────────────

def build_signals(bars, feats, m_for_day, p, universe, *, method: str, cap: float, k: float,
                  slip: float = LIVE_SLIP, close_slip: float = 0.0) -> "list[EN.Sig]":
    """``bfb_vcp_opt.build_signals_opt`` 와 같은 진입 규칙 + 시대별 상한가 + 표시 행(진입 봉) 제외.

    I = 장중 추격: 시가 > 돌파선 × (1+cap%) 면 없음 · 고가 < 돌파선이면 없음 · 체결가 = min(고가, max(시가, 돌파선 ×
    (1+slip)))(slip=0 이면 전수 점검 판정판 max(시가, 돌파선)) · 시가 상한가면 없음.
    C = 종가 확인: D 종가 > 돌파선 ∧ ≤ 돌파선 × (1+cap%) ∧ 거래량 ≥ k × 평균 ∧ 종가 상한가 아님 → D 종가.
    N = 다음 날 시가: D 종가 > 돌파선 ∧ 거래량 조건 → D+1 시가(≤ 돌파선 × (1+cap%), 상한가 시가 아님).
    """
    out = []
    for t, b in bars.items():
        f = feats[t]
        n = len(b["c"])
        ok = f["cand"][:-1] & universe[t][:-1]
        for i in np.nonzero(ok)[0]:
            D = i + 1
            if b["di"][D] != b["di"][i] + 1 or b["notrade"][D] or b["jump"][D]:
                continue
            line = float(f["line"][i])
            if not (line > 0):
                continue
            lim = float(b["lim"][D])
            avg = float(f["avg"][i])
            if method == "I":
                O, H = float(b["o"][D]), float(b["h"][D])
                if not (O > 0) or limit_up(O, b["c"][i], lim):
                    continue
                px = BR.breakout_fill(O, H, line, cap)
                if px is None:
                    continue
                if slip > 0:
                    px = min(H, max(O, line * (1 + slip)))
                kind_ = "gap" if px <= O else "cross"
                thr = int(avg * float(p["breakout_volume_mult"]))
                vol_ok = bool(thr <= 0 or b["vol"][D] >= thr)
                E, ti, N = px, D, float(f["atr"][i])
                vr = float(b["vol"][D] / thr) if thr > 0 else float("nan")
            else:
                Cd = float(b["c"][D])
                if not (Cd > line):
                    continue
                if k > 0 and not (avg > 0 and b["vol"][D] >= avg * k):
                    continue
                vol_ok = True
                vr = float(b["vol"][D] / avg) if avg > 0 else float("nan")
                if method == "C":
                    if Cd > line * (1 + cap / 100.0) or limit_up(Cd, b["c"][i], lim):
                        continue
                    E, ti, N = Cd * (1 + close_slip), D, float(f["atr"][i])
                    kind_ = "close"
                elif method == "N":
                    E1 = D + 1
                    if E1 >= n or b["di"][E1] != b["di"][D] + 1 or b["notrade"][E1] or b["jump"][E1]:
                        continue
                    O = float(b["o"][E1])
                    if not (O > 0) or limit_up(O, Cd, float(b["lim"][E1])) or O > line * (1 + cap / 100.0):
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
                              float(f["low"][i]), float(f["target"][i]), mv, vol_ok, kind_, vr))
    out.sort(key=lambda s: (s.gd, s.ticker))
    return out


# ── 포지션 ───────────────────────────────────────────────────────────────────────

class YPos(OP.OPos):
    """효율화 ``OPos`` + 시대별 하한가 잠김."""

    def _locked(self, ti) -> bool:
        b = self.b
        return ti >= 1 and locked_down(b["o"][ti], b["h"][ti], b["l"][ti], b["c"][ti - 1], float(b["lim"][ti]))


def run_path(sig, b, f, end_gd, *, kind, p, cal, mode="color") -> YPos:
    ps = YPos(sig, b, f, 1, kind=kind, p=p, cal=cal, mode=mode)
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


def population(sigs, bars, feats, g0, g1, *, kind, p, cal, mu_thr=0.0, mode="color"):
    """전수 점검 모집단 규칙(종목마다 앞 거래 청산 + 쿨다운 뒤 · m ≤ 0 진입 없음) + m ≥ mu_thr.
    반환 = (포지션 목록, 표시 행이 보유 구간에 낀 포지션 수). 낀 포지션은 목록에서 뺀다(쿨다운은 그대로 건다)."""
    out, busy, jumped = [], {}, 0
    cd = int(p["reentry_cooldown_days"])
    for s in sigs:
        if s.gd < g0 or s.gd > g1 or s.m <= 0 or s.m < mu_thr:
            continue
        if busy.get(s.ticker, -1) >= s.gd:
            continue
        b = bars[s.ticker]
        ps = run_path(s, b, feats[s.ticker], g1, kind=kind, p=p, cal=cal, mode=mode)
        busy[s.ticker] = (ps.exit_gd + cd) if ps.exit_gd is not None else 10 ** 9
        last_gd = ps.exit_gd if ps.exit_gd is not None else g1
        te = int(np.searchsorted(b["di"], last_gd, side="right"))
        if b["jump"][s.ti:te].any():
            jumped += 1
            continue
        out.append(ps)
    return out, jumped


def rows_of(pop, cal, cost: Y.EraCost, g1: int):
    out = []
    for ps in pop:
        gx = ps.exit_gd if ps.exit_gd is not None else g1
        out.append(dict(t=ps.s.ticker, d=str(cal[ps.s.gd].date()), gd=ps.s.gd,
                        r=ps.exit_px / ps.E - 1 - cost.rt(ps.s.gd, gx), g=ps.exit_px / ps.E - 1,
                        why=ps.exit_reason, m=ps.s.m, entry=ps.s.entry,
                        hold=(ps.exit_gd - ps.s.gd) if ps.exit_gd is not None else None))
    return out


def cal_years(cal, g0, g1) -> float:
    return max((cal[g1] - cal[g0]).days, 1) / 365.25


def stat_block(rows, years: float) -> dict:
    if not rows:
        return {"n": 0, "per_year": 0.0, "mean": float("nan"), "lo90": float("nan"), "pass": False}
    r = J.p1([x["r"] for x in rows], [x["t"] for x in rows], [x["d"] for x in rows])
    v = np.array([x["r"] for x in rows])
    srt = np.sort(v)
    kk = max(1, int(round(len(v) * 0.01)))
    return {"n": len(rows), "per_year": len(rows) / years, "mean": r["mean"], "lo90": r["lo90"],
            "hi90": r["hi90"], "pass": r["pass"], "median": float(np.median(v)), "win": float((v > 0).mean()),
            "gross_mean": float(np.mean([x["g"] for x in rows])),
            "mean_ex_top1pct": float(srt[:-kk].mean()) if len(v) > kk else float("nan")}


def sub_means(rows, subs) -> "list[float]":
    out = []
    for a, b in subs:
        v = [x["r"] for x in rows if a <= x["d"] <= b]
        out.append(float(np.mean(v)) if v else float("nan"))
    return out


def exit_mix(rows) -> dict:
    c = Counter(x["why"] for x in rows)
    n = sum(c.values()) or 1
    return {k: {"n": v, "share": v / n, "mean": float(np.mean([x["r"] for x in rows if x["why"] == k]))}
            for k, v in c.most_common()}


# ── 계좌 ─────────────────────────────────────────────────────────────────────────

def run_book(signals_by_gd, open_pos, size_fn, cal, start, end, seed, *, start_equity, cost: Y.EraCost,
             max_pos: int) -> dict:
    """공용 ``book.run_book`` 과 같은 하루 순서 — 비용만 날짜별(매수 = 그날 수수료, 매도 = 그날 수수료+거래세)."""
    rng = np.random.default_rng(seed)
    g0 = int(cal.searchsorted(pd.Timestamp(start)))
    g1 = int(cal.searchsorted(pd.Timestamp(end), side="right")) - 1
    cash = float(start_equity)
    pos: dict = {}
    eq_prev = float(start_equity)
    equity, trades = [], []
    cnt = Counter()

    def close(ps, gd):
        nonlocal cash
        sc = cost.sell(gd)
        ps._sc = sc
        cash += ps.k * ps.exit_px * (1 - sc)
        trades.append(ps)

    for gd in range(g0, g1 + 1):
        B = eq_prev
        sold_today = set()
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                continue
            if ps.open_phase(ti, gd):
                close(ps, gd)
                sold_today.add(t)
                del pos[t]
        todays = list(signals_by_gd.get(gd, []))
        rng.shuffle(todays)
        stop_why = None
        for s in todays:
            if s.ticker in pos or s.ticker in sold_today:
                continue
            cnt["signal"] += 1
            if stop_why is None and len(pos) >= max_pos:
                stop_why = "slot_full"
            if stop_why is not None:
                cnt[stop_why] += 1
                continue
            used = sum(x.cost_basis for x in pos.values())
            q, why = size_fn(s, B, used)
            if q <= 0:
                cnt["zero_" + why] += 1
                continue
            ps = open_pos(s, q)
            ps._bc = cost.buy(gd)
            cash -= q * s.E_raw * (1 + ps._bc)
            pos[s.ticker] = ps
            cnt["fill"] += 1
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                if ps.data_ended(gd):
                    ps._exit(ps.last_px, "END", gd)
                    close(ps, gd)
                    del pos[t]
                continue
            if ps.intraday_phase(ti, gd, ti == ps.s.ti):
                close(ps, gd)
                del pos[t]
        eq = cash + sum(x.value() for x in pos.values())
        equity.append(eq)
        eq_prev = eq
    for ps in pos.values():
        ps._exit(ps.last_px, "OPEN", None)
        ps._sc = 0.0
        trades.append(ps)
    eq = np.array(equity)
    tot = 0.0
    for ps in trades:
        buy = ps.qty * ps.s.E_raw * (1 + ps._bc)
        tot += (ps.k * ps.last_px - buy) if ps.exit_reason == "OPEN" else (ps.k * ps.exit_px * (1 - ps._sc) - buy)
    recon = float(eq[-1] - (start_equity + tot)) if len(eq) else 0.0
    return {"equity": eq, "trades": trades, "counts": dict(cnt), "recon": recon,
            "years": cal_years(cal, g0, g1), "start_equity": start_equity}


def book_summary(runs) -> dict:
    cg, md, nt, fills, unaff = [], [], [], [], []
    for r in runs:
        eq, se, yrs = r["equity"], r["start_equity"], r["years"]
        cg.append(float((eq[-1] / se) ** (1 / yrs) - 1) if len(eq) and eq[-1] > 0 else -1.0)
        e = np.concatenate([[se], eq])
        md.append(float((e / np.maximum.accumulate(e) - 1).min()))
        nt.append(len(r["trades"]))
        c = r["counts"]
        fills.append(c.get("fill", 0) / yrs)
        free = c.get("signal", 0) - c.get("slot_full", 0)
        unaff.append(c.get("zero_funds", 0) / free if free > 0 else float("nan"))
    tr0 = runs[0]["trades"]
    closed = [ps for ps in tr0 if ps.exit_reason != "OPEN"]
    return {"cagr_median": float(np.median(cg)), "cagr_min": float(np.min(cg)), "cagr_max": float(np.max(cg)),
            "mdd_median": float(np.median(md)), "trades_median": float(np.median(nt)),
            "fills_per_year_median": float(np.median(fills)),
            "unaffordable_ratio_median": float(np.nanmedian(unaff)) if any(u == u for u in unaff) else float("nan"),
            "recon_max_abs": float(max(abs(r["recon"]) for r in runs)), "counts_seed0": runs[0]["counts"],
            "seed0_exit_mix": dict(Counter(ps.exit_reason for ps in tr0)),
            "seed0_trade_mean_net": float(np.mean([ps.exit_px / ps.E - 1 - ps._bc - ps._sc for ps in closed]))
            if closed else float("nan"),
            "lot_over_1pct_tv_share_seed0": runs[0].get("liq", float("nan")),
            "per_seed_cagr": cg}


class _CD:
    def __init__(self, sbg, cd):
        self.sbg, self.cd, self.last = sbg, cd, {}

    def note_exit(self, t, gd):
        self.last[t] = gd

    def get(self, gd, default=None):
        return [s for s in self.sbg.get(gd, default or [])
                if not (self.last.get(s.ticker) is not None and gd <= self.last[s.ticker] + self.cd)]


def run_books(sigs, st, feats, kind, p, cls, win, cost, *, mu_thr=0.0, mode="color", seeds=C.BOOK_SEEDS):
    from replay.audit.sizing import OpSizer
    sid = "vcp_breakout" if kind == "vcp" else "bull_flag_breakout"
    op = OpSizer(cls, sid, {k: v for k, v in p.items() if not k.startswith("_")}, atr_keys=("atr14",))
    sbg = defaultdict(list)
    for s in sigs:
        sbg[s.gd].append(s)
    runs = []
    for seed in seeds:
        cs = _CD(sbg, int(p["reentry_cooldown_days"]))
        liq = []

        def size_fn(s, B, used, _liq=liq, _seed=seed):
            P = int(round(s.E_raw))
            if s.m <= 0 or s.m < mu_thr:
                return 0, "mu"
            N_raw = s.N * (s.E_raw / s.E)
            if op.blocks_entry(P, N_raw, budget=int(B), used=int(used), m=s.m, ticker=s.ticker):
                return 0, "mu"
            q = op.qty(P, N_raw, budget=int(B), used=int(used), m=s.m, ticker=s.ticker)
            if q > 0:
                if _seed == 0:
                    b = st.bars[s.ticker]
                    tvp = b["tv"][s.ti - 1] if s.ti >= 1 else np.nan
                    if tvp > 0:
                        _liq.append(q * P / tvp)
                return q, "ok"
            return 0, ("funds" if int(B) - int(used) < P else "design")

        def open_pos(s, q, _cs=cs):
            return YPos(s, st.bars[s.ticker], feats[s.ticker], q, kind=kind, p=p, cal=st.cal, mode=mode,
                        on_exit=_cs.note_exit)
        r = run_book(cs, open_pos, size_fn, st.cal, win[0], win[1], seed, start_equity=float(C.BUDGET_C7),
                     cost=cost, max_pos=int(p["max_positions"]))
        if seed == 0:
            lq = np.array(liq)
            r["liq"] = float((lq > 0.01).mean()) if len(lq) else float("nan")
        runs.append(r)
    return book_summary(runs)


# ── 메인 ─────────────────────────────────────────────────────────────────────────

def _classes(kind):
    if kind == "vcp":
        from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy as cls
        return cls, EN.vcp_features
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy as cls
    return cls, EN.bfb_features


def run(kind: str, skip_b: bool = False):
    t0 = time.time()
    cls, featf = _classes(kind)
    od = os.path.join(_REPO, OUT_ROOT_REL, kind)
    prereg = os.path.join(od, "prereg.md")
    frozen = open(prereg + ".sha256").read().split()[0]
    if PN.sha256(prereg) != frozen:
        raise SystemExit("prereg.md 가 동결 sha 와 다르다 — 실행 중단")
    me = PN.sha256(__file__)
    exp_code = [ln.split("`")[1] for ln in open(prereg) if ln.startswith("- 실행 코드 sha256")]
    if exp_code and exp_code[0] != me:
        raise SystemExit(f"실행 코드 sha 가 prereg 와 다르다 — 중단 ({me})")
    out = {"strategy": kind, "prereg_sha256": frozen, "code_sha256": me,
           "engine_sha256": PN.sha256(os.path.join(os.path.dirname(__file__), "bfb_vcp_engine.py")),
           "opt_sha256": PN.sha256(os.path.join(os.path.dirname(__file__), "bfb_vcp_opt.py")),
           "data_sha256": PN.sha256(os.path.join(os.path.dirname(__file__), "y30_data.py"))}
    st, meta = Y.build()
    cal = st.cal
    m, bench = Y.market_unit(cal)
    out["data_meta"] = meta
    out["m_days_finite"] = int(np.isfinite(m).sum())
    cost = EraCostY(cal)
    cost_c = EraCostY(cal, const=CONST_COST)

    def gw(w):
        return (int(cal.searchsorted(pd.Timestamp(w[0]))), int(cal.searchsorted(pd.Timestamp(w[1]), side="right")) - 1)
    W = {"T": T_WIN, "V": V_WIN, "H": H_WIN}
    G = {k: gw(v) for k, v in W.items()}
    YR = {k: cal_years(cal, *G[k]) for k in W}
    out["years"] = YR
    out["bench"] = {k: Y.bench_stats(bench, m, cal, W[k]) for k in W}
    out["bench_eras"] = {f"{a}~{b}": Y.bench_stats(bench, m, cal, (a, b)) for a, b in ERAS}
    out["cost_rt_examples"] = {d: cost.rt(int(cal.searchsorted(pd.Timestamp(d))),
                                          int(cal.searchsorted(pd.Timestamp(d))))
                               for d in ("1997-06-02", "2000-06-01", "2010-06-01", "2020-06-01", "2026-06-01")}

    setups = OP.SETUPS[kind]
    feats_by, univ_by = {}, {}
    for s in setups:
        p_s = OP.params_for(kind, s, "X0")
        feats_by[s] = {t: featf(b, p_s) for t, b in st.bars.items()}
        univ_by[s] = Y.universe(st, meta["ratios"], kind, mode="pct")
        print(f"[{kind}] features {s} {time.time()-t0:.0f}s", flush=True)
    univ_nom = Y.universe(st, meta["ratios"], kind, mode="nominal")
    out["universe_ratio"] = {"mcap_top": meta["ratios"]["mcap"], "tv_top": meta["ratios"][f"tv_{kind}"]}

    entries = {e[0]: e for e in OP.entries_for(kind)}
    sig_cache = {}

    def sigs_of(setup, ename, slip=LIVE_SLIP, univ="pct", close_slip=0.0):
        key = (setup, ename, slip, univ, close_slip)
        if key not in sig_cache:
            _, meth, cap, k = entries[ename]
            p_s = OP.params_for(kind, setup, "X0")
            u = univ_by[setup] if univ == "pct" else univ_nom
            sig_cache[key] = build_signals(st.bars, feats_by[setup], m, p_s, u, method=meth, cap=cap, k=k,
                                           slip=slip, close_slip=close_slip)
        return sig_cache[key]

    def evaluate(gid, win, *, slip=LIVE_SLIP, c=cost, mode="color", univ="pct"):
        s_, e_, x_, mu_ = gid.split("|")
        p_g = OP.params_for(kind, s_, x_)
        g0, g1 = gw(win)
        pop, jumped = population(sigs_of(s_, e_, slip, univ), st.bars, feats_by[s_], g0, g1, kind=kind, p=p_g,
                                 cal=cal, mu_thr=OP.MU_THR[mu_], mode=mode)
        rr = rows_of(pop, cal, c, g1)
        sb = stat_block(rr, cal_years(cal, g0, g1))
        sb["jump_excluded"] = jumped
        return sb, rr

    def book(gid, win, *, slip=LIVE_SLIP, c=cost, mode="color"):
        s_, e_, x_, mu_ = gid.split("|")
        p_g = OP.params_for(kind, s_, x_)
        return run_books(sigs_of(s_, e_, slip), st, feats_by[s_], kind, p_g, cls, win, c,
                         mu_thr=OP.MU_THR[mu_], mode=mode)

    # ── 0. 재현 확인 — 원화 문턱 유니버스 · 일정 0.38% · 체결 보정 없음 · W5y(전수 점검 판정판과 비교)
    sb0, _ = evaluate(CURRENT_ID, C.W5Y, slip=0.0, c=cost_c, univ="nominal")
    out["repro_w5y_nominal_noslip_const038"] = sb0
    print(f"[{kind}] repro {sb0['n']} {sb0['mean']:.4f} {time.time()-t0:.0f}s", flush=True)

    # ── A. 현행 규칙 30년 판정
    A = {}
    trades_dump = []
    for vname, slip in (("basic", LIVE_SLIP), ("optimistic", 0.0)):
        res = {}
        for wn, win in W.items():
            sb, rr = evaluate(CURRENT_ID, win, slip=slip)
            sa, _ = evaluate(CURRENT_ID, win, slip=slip, mode="adverse")
            sc, _ = evaluate(CURRENT_ID, win, slip=slip, c=cost_c)
            bk = book(CURRENT_ID, win, slip=slip)
            res[wn] = {"P1": sb, "P1_const038": sc, "adverse": sa, "P5": J.p5(sb["mean"], sa["mean"]),
                       "book": bk, "P3": J.p3(bk), "P4": J.p4(bk), "exit_mix": exit_mix(rr),
                       "by_year": {y: stat_block([x for x in rr if x["d"][:4] == y], 1.0)
                                   for y in sorted({x["d"][:4] for x in rr})}}
            if vname == "basic":
                trades_dump += [dict(x, win=wn) for x in rr]
            print(f"[{kind}] A {vname} {wn} n {sb['n']} mean {sb['mean']:.4f} lo {sb['lo90']:.4f} adv "
                  f"{sa['mean']:.4f} book {bk['cagr_median']:.3f}/{bk['mdd_median']:.3f} {time.time()-t0:.0f}s",
                  flush=True)
        eras = {}
        for a, b in ERAS:
            sb, _ = evaluate(CURRENT_ID, (a, b), slip=slip)
            bk = book(CURRENT_ID, (a, b), slip=slip)
            eras[f"{a}~{b}"] = {"P1": sb, "book": {k: bk[k] for k in ("cagr_median", "mdd_median",
                                                                      "fills_per_year_median")}}
        res["eras"] = eras
        signs = [np.sign(res[w]["P1"]["mean"]) for w in W]
        res["persistent_same_sign"] = bool(len(set(signs)) == 1)
        res["labels"] = {w: _label(res[w]) for w in W}
        A[vname] = res
    out["A"] = A
    pd.DataFrame(trades_dump).to_csv(os.path.join(od, "trades_A_basic.csv.gz"), index=False)

    # ── 가설(사전 등록) — 종가 확인 진입 vs 현행(장중 추격 · 기본판)
    hyp = {}
    for hn, gid in HYP[kind].items():
        hr = {"id": gid}
        for wn, win in W.items():
            sb, rr = evaluate(gid, win)
            _, rc = evaluate(CURRENT_ID, win)
            hr[wn] = {"stat": sb, "diff": OP.month_block_diff(rr, rc, n_boot=DIFF_BOOT, qs=(0.05,))}
        hr["supported"] = bool(all(hr[w]["diff"]["est"] > 0 for w in W)
                               and hr["T"]["diff"]["lower"]["0.05"] > 0 and hr["V"]["diff"]["lower"]["0.05"] > 0)
        if hn == "main":
            hr["book"] = {wn: book(gid, win) for wn, win in W.items()}
        hyp[hn] = hr
        print(f"[{kind}] HYP {hn} {gid} " + " ".join(f"{w} {hr[w]['diff']['est']:+.4f}" for w in W), flush=True)
    out["hypothesis"] = hyp

    # ── B. 최적화(T 선택 → V 판정 → H 부호)
    if not skip_b:
        out["B"] = _run_b(kind, evaluate, book, gw, cal)
    out["elapsed_s"] = time.time() - t0
    with open(os.path.join(od, "results.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=_js)
    print(f"[{kind}] done {out['elapsed_s']:.0f}s", flush=True)


def _label(w: dict) -> str:
    if w["P5"]["flip"]:
        return "판정 보류(일봉 해상도 부족)"
    ok = w["P1"]["pass"] and w["P3"]["pass"] and w["P4"]["pass"]
    return "통과" if ok else "실패(" + ",".join(k for k in ("P1", "P3", "P4") if not w[k]["pass"]) + ")"


def _js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _run_b(kind, evaluate, book, gw, cal):
    G = OP.grid(kind)
    rows_T = []
    t0 = time.time()
    for gi, g in enumerate(G):
        sb, rr = evaluate(g["id"], T_WIN)
        sm = sub_means(rr, T_SUB)
        npos = int(sum(1 for x in sm if x > 0))
        sb.update(id=g["id"], sub_means=sm, sub_pos=npos, eligible=bool(sb["per_year"] >= MIN_TRADES_PER_YEAR),
                  robust=bool(npos >= ROBUST_MIN_POS))
        rows_T.append(sb)
        if gi % 12 == 0:
            print(f"[{kind}] B-T {gi+1}/{len(G)} {g['id']} n {sb['n']} mean {sb['mean']:.4f} lo {sb['lo90']:.4f} "
                  f"{time.time()-t0:.0f}s", flush=True)
    od = os.path.join(_REPO, OUT_ROOT_REL, kind)
    dfT = pd.DataFrame(rows_T)
    dfT.to_csv(os.path.join(od, "grid_T.csv"), index=False)
    elig = dfT[dfT.eligible & dfT.robust].sort_values(["lo90", "mean"], ascending=False)
    chosen = str(elig.iloc[0]["id"]) if len(elig) else None
    B = {"n_combos": len(G), "n_eligible": int(dfT.eligible.sum()), "n_eligible_robust": int(len(elig)),
         "chosen": chosen, "current_T": dfT[dfT.id == CURRENT_ID].iloc[0].to_dict(),
         "current_rank_by_lo90": int((dfT.sort_values("lo90", ascending=False).id.tolist()).index(CURRENT_ID)) + 1,
         "top10": elig.head(10).to_dict("records")}
    ev, R = {}, {}
    for name, gid in (("current", CURRENT_ID), ("chosen", chosen)):
        if gid is None:
            continue
        res = {"id": gid}
        R[name] = {}
        for wn, win in (("T", T_WIN), ("V", V_WIN), ("H", H_WIN)):
            res[wn], R[name][wn] = evaluate(gid, win)
            res[wn]["exit_mix"] = exit_mix(R[name][wn])
        res["V_adverse"], _ = evaluate(gid, V_WIN, mode="adverse")
        res["P5_V"] = J.p5(res["V"]["mean"], res["V_adverse"]["mean"])
        res["book_V"] = book(gid, V_WIN)
        res["P3_V"] = J.p3(res["book_V"])
        res["P4_V"] = J.p4(res["book_V"])
        res["book_T"] = book(gid, T_WIN)
        res["book_H"] = book(gid, H_WIN)
        ev[name] = res
        print(f"[{kind}] B {name} {gid} V {res['V']['mean']:.4f} lo {res['V']['lo90']:.4f} H {res['H']['mean']:.4f}",
              flush=True)
    K = len(G)
    if chosen is not None and chosen != CURRENT_ID:
        B["diff_V"] = OP.month_block_diff(R["chosen"]["V"], R["current"]["V"], qs=(0.05, 0.05 / K))
        B["diff_T"] = OP.month_block_diff(R["chosen"]["T"], R["current"]["T"], n_boot=2000, qs=(0.05,))
        B["diff_H"] = OP.month_block_diff(R["chosen"]["H"], R["current"]["H"], n_boot=2000, qs=(0.05,))
        c = ev["chosen"]
        cond = {"a_mean_gt_current": bool(c["V"]["mean"] > ev["current"]["V"]["mean"]),
                "b_diff_lo90_gt0": bool(B["diff_V"]["lower"]["0.05"] > 0),
                "b_bonferroni_lo_gt0": bool(B["diff_V"]["lower"][f"{0.05 / K:.6g}"] > 0),
                "c_P1": bool(c["V"]["pass"]), "c_P3": bool(c["P3_V"]["pass"]), "c_P4": bool(c["P4_V"]["pass"]),
                "c_P5": not c["P5_V"]["flip"]}
        v_ok = all(cond[k] for k in ("a_mean_gt_current", "b_diff_lo90_gt0", "c_P1", "c_P3", "c_P4", "c_P5"))
        h_ok = bool(c["H"]["mean"] > 0 and B["diff_H"]["est"] > 0)
        B["conditions_V"] = cond
        B["H_ok"] = h_ok
        B["label"] = ("폐기" if not v_ok else ("보류" if not h_ok else
                                              ("채택" if cond["b_bonferroni_lo_gt0"] else "채택(보정 미달 표기)")))
    else:
        B["label"] = "현행 유지" if chosen == CURRENT_ID else "고른 판 없음"
    B["eval"] = ev
    return B


if __name__ == "__main__":
    run(sys.argv[1], skip_b="--skip-B" in sys.argv)
