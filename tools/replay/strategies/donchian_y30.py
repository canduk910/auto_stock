#!/usr/bin/env python3
"""donchian_swing(깡토 개조) 30년(1996~2026) 재검증 — 사전 등록
``_workspace/analysis/strategy_30y_20261006/donchian/prereg.md``(sha256 = 같은 폴더 ``prereg.sha256``) 그대로 돌린다.

현행판 = 5년 전수 점검 운영 해석판(``donchian_kk_audit.VARIANTS["op"]`` — 10-06 21:35 배포 예정 규칙과 같다).
입력 = ``donchian_y30_data.build``(30년 단일 보관소). 재사용 = ``DK.KKPos``·``DK.build_signals``·``DK.kk_R`` ·
``audit.sizing.OpSizer``(브랜치 전략 파일) · ``audit.judge`` · ``audit.book.book_summary`` · ``donchian_opt.diff_boot``.

5년 판 대비 이 모듈이 바꾸는 것:
- 거래대금 문턱 = 그날 거래대금 상위 p*(시대 중립, ``tvok``) — 명목 200억은 민감도
- 시기별 실제 비용(매수 = 그날 수수료 · 매도 = 왕복 − 수수료) — 일정 0.38% 는 민감도
- 가격제한폭: 하한가 잠김 봉(고가 = 저가 ∧ 종가 ≤ 전일 × (1 − 제한폭) × 1.005)에서는 팔지 못한다(다음 봉으로)
- 위반 표시 행(``jump``): 신호봉 앞 62봉 ~ 진입봉 안에 있으면 진입 없음 · 보유 중 만나면 직전 종가로 정리(``JUMP``)

실행: python tools/replay/strategies/donchian_y30.py [--out PATH] [--only A|B]
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
from replay.audit import indicators as IND  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.audit.sizing import OpSizer, load_strategy_class  # noqa: E402
from replay.strategies import donchian_kk as DK  # noqa: E402
from replay.strategies import donchian_kk_audit as DA  # noqa: E402
from replay.strategies import donchian_opt as DO  # noqa: E402
from replay.strategies import donchian_y30_data as YD  # noqa: E402

PREREG_SHA = "729f62c760d75fe2d011aed47f3e2de2069775a08799e4e11bb0c37057630704"
HERE = os.path.join(C.REPO, "_workspace/analysis/strategy_30y_20261006/donchian")
CACHE = os.path.join(os.path.dirname(C.SCRATCH), "y30_donchian", "store.pkl")

T = ("1997-01-02", "2012-12-28")
V = ("2013-01-02", "2020-12-30")
H = ("2021-01-04", "2026-10-02")
WINDOWS = {"T": T, "V": V, "H": H}
T_SUB = (("1997-01-02", "2000-12-29"), ("2001-01-02", "2004-12-31"), ("2005-01-03", "2008-12-30"),
         ("2009-01-02", "2012-12-28"))
ERAS = (("1997-01-02", "2001-12-31"), ("2002-01-02", "2006-12-29"), ("2007-01-02", "2011-12-29"),
        ("2012-01-02", "2016-12-29"), ("2017-01-02", "2021-12-30"), ("2022-01-03", "2026-10-02"))
ROBUST_MIN_SUB = 3
MIN_TRADES_PER_YEAR = 30
COST_FLAT = 0.0038
JUMP_LOOKBACK = 62

ENTRY0 = dict(entry_n=20, vol_mult=1.5, clv=None, mu="cur")
EXIT0 = dict(r=(8.0, 1.5), be_r=3.0, time_bars=20, chan=10)
ACCT0 = dict(slots=(6, 0.15), daily_cap=3)
GRID_A = [dict(entry_n=a, vol_mult=b, clv=c, mu=d) for a, b, c, d in itertools.product(
    (20, 55), (1.5, 2.5), (None, 0.6), ("cur", "m1", "off"))]
GRID_B = [dict(r=a, be_r=b, time_bars=c, chan=d) for a, b, c, d in itertools.product(
    ((8.0, 1.5), (6.0, 2.5), (10.0, 1.5)), (2.0, 3.0, 4.0), (10, 20, 30), (10, 20, 30))]
GRID_C = [dict(slots=a, daily_cap=b) for a, b in itertools.product(
    ((6, 0.15), (4, 0.25), (5, 0.20), (8, 0.12), (10, 0.10)), (2, 3, 5))]
N_COMBOS = len(GRID_A) + len(GRID_B) + len(GRID_C)
assert N_COMBOS == 120


# ── 비용 ─────────────────────────────────────────────────────────────

class Costs:
    """달력 날마다 매수 쪽(수수료) · 매도 쪽(왕복 − 수수료). ``flat`` 이면 둘 다 flat/2."""

    def __init__(self, cal: pd.DatetimeIndex, flat: "float | None" = None):
        if flat is None:
            rt = YD.cost_rt_on(cal)
            fee = YD.fee_one_way_on(cal)
            self.buy, self.sell = fee, rt - fee
            self.tag = "era"
        else:
            self.buy = np.full(len(cal), flat / 2)
            self.sell = np.full(len(cal), flat / 2)
            self.tag = f"flat{flat:g}"

    def rt(self, gd_in: int, gd_out: "int | None") -> float:
        go = gd_in if gd_out is None else gd_out
        return float(self.buy[gd_in] + self.sell[min(go, len(self.sell) - 1)])


# ── 신호 층 ─────────────────────────────────────────────────────────

def jump_block(jump: np.ndarray, lookback: int = JUMP_LOOKBACK) -> np.ndarray:
    """신호봉 j 기준 [j − lookback, j + 1] 안에 위반 표시 행이 있으면 True(진입봉 j+1 포함)."""
    n = len(jump)
    cs = np.concatenate([[0], np.cumsum(jump.astype(int))])
    i = np.arange(n)
    lo = np.clip(i - lookback, 0, n)
    hi = np.clip(i + 2, 0, n)
    return (cs[hi] - cs[lo]) > 0


def features_y30(b: dict, *, entry_n: int = 20, vol_mult: float = 1.5, clv: "float | None" = None,
                 tv_mode: str = "pct") -> dict:
    """``DK.features(turnover="cv")`` 와 같은 식 + 시대 중립 거래대금 문턱 · 위반 표시 행 거름.

    ``tv_mode``: ``"pct"`` = 그날 거래대금 상위 p*(판정) · ``"nominal"`` = 명목 200억(``b["tv"]``, 5년 판 식) ·
    ``"none"`` = 문턱 없음.
    """
    o, h, l, c = b["o"], b["h"], b["l"], b["c"]
    n = len(c)
    atr = IND.atr_sma(h, l, c, 14)
    ph = IND.prior_max(h, entry_n)
    ema = IND.ema_fir(c, 60)
    ema_y = np.full(n, np.nan)
    ema_y[1:] = ema[:-1]
    tvx = np.asarray(b["c_raw"], float) * np.asarray(b["vol"], float)
    avg = IND.prior_mean(tvx, 20)
    if tv_mode == "pct":
        tvg = np.asarray(b["tvok"], bool)
    elif tv_mode == "nominal":
        tvg = np.asarray(b["tv"], float) >= DK.ENTRY["min_trade"]
    elif tv_mode == "none":
        tvg = np.ones(n, bool)
    else:
        raise ValueError(tv_mode)
    jb = jump_block(np.asarray(b.get("jump", np.zeros(n, bool)), bool))
    with np.errstate(invalid="ignore"):
        cond = ((np.arange(n) >= 62) & (c > ph) & (ph > 0) & (ema > ema_y) & (c > ema)
                & (avg > 0) & (tvx >= vol_mult * avg) & (atr > 0)
                & np.asarray(b["mem"], bool) & tvg & ~b["notrade"] & ~jb)
    cond = np.nan_to_num(cond).astype(bool)
    if clv is not None:
        rng = h - l
        with np.errstate(invalid="ignore", divide="ignore"):
            cl = np.where(rng > 0, (c - l) / np.where(rng > 0, rng, 1.0), np.nan)
            cond = cond & np.nan_to_num(cl >= clv).astype(bool)
    return {"atr": atr, "prior_high": ph, "cond": cond, "chan10": IND.prior_min(l, 10),
            "chan20": IND.prior_min(l, 20), "chan30": IND.prior_min(l, 30),
            "turnover": tvx, "turnover_avg20": avg, "jump_block": jb}


def feats_view(f: dict, chan: int) -> dict:
    if chan == 10:
        return f
    g = dict(f)
    g["chan10"] = f[f"chan{chan}"]
    return g


def kk_of(ex: dict, acct: dict = ACCT0) -> dict:
    r_floor, r_atr = ex["r"]
    return dict(DK.KK, chan_strict=True, r_floor=r_floor / 100.0, r_atr=r_atr, be_r=ex["be_r"],
                time_bars=ex["time_bars"], max_pos=acct["slots"][0], pr=acct["slots"][1],
                daily_cap=acct["daily_cap"])


def mu_apply(sigs: list, mu: str) -> list:
    """``cur`` = 운영(m ≤ 0 진입 없음 · 랏 × m) · ``m1`` = m = 1 일 때만 · ``off`` = 시장 유닛을 안 쓴다(m = 1 로 본다)."""
    if mu == "cur":
        return sigs
    if mu == "m1":
        return [s for s in sigs if s.m >= 1.0]
    if mu == "off":
        out = []
        for s in sigs:
            s2 = DK.Sig(**{**s.__dict__, "m": 1.0})
            out.append(s2)
        return out
    raise ValueError(mu)


# ── 포지션 층(가격제한폭 · 위반 표시 행) ─────────────────────────────────

def locked_down(b: dict, ti: int) -> bool:
    if ti <= 0:
        return False
    pc = b["c"][ti - 1]
    lim = b["lim"][ti] if "lim" in b else 0.30
    return bool(pc > 0 and b["h"][ti] == b["l"][ti] and b["c"][ti] <= pc * (1 - lim) * 1.005
                and not b["notrade"][ti])


class Y30Pos(DK.KKPos):
    def open_phase(self, ti: int, gd: int) -> bool:
        b = self.b
        if b.get("jump") is not None and b["jump"][ti]:
            self._exit(self.last_px, "JUMP", gd)
            return True
        if locked_down(b, ti):
            return False
        return super().open_phase(ti, gd)

    def intraday_phase(self, ti: int, gd: int, is_entry: bool) -> bool:
        b = self.b
        if locked_down(b, ti):
            self.last_px = b["c"][ti]
            return False
        return super().intraday_phase(ti, gd, is_entry)


def run_path(sig, b, f, end_gd, mode="color", kk=DK.KK) -> Y30Pos:
    ps = Y30Pos(sig, b, f, 1, mode=mode, kk=kk)
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


def population(sigs, bars, feats, start_gd, end_gd, mode="color", kk=DK.KK) -> list:
    out, busy = [], {}
    for s in sigs:
        if s.gd < start_gd or s.gd > end_gd or s.m <= 0:
            continue
        if busy.get(s.ticker, -1) >= s.gd:
            continue
        ps = run_path(s, bars[s.ticker], feats[s.ticker], end_gd, mode, kk=kk)
        busy[s.ticker] = ps.exit_gd if ps.exit_gd is not None else 10 ** 9
        out.append(ps)
    return out


def pop_rows(pop, costs: Costs, end_gd: int) -> list:
    rows = []
    for p in pop:
        cr = costs.rt(p.s.gd, p.exit_gd if p.exit_gd is not None else end_gd)
        rows.append({"t": p.s.ticker, "gd": p.s.gd, "m": p.s.m, "net": p.exit_px / p.E - 1 - cr,
                     "R": (p.exit_px / p.E - 1 - cr) / (p.Rw / p.E), "why": p.exit_reason,
                     "hold": (p.exit_gd - p.s.gd + 1) if p.exit_gd is not None else None})
    return rows


def stats(rows, cal, sub_windows=()) -> dict:
    if not rows:
        return {"n": 0}
    r = J.p1([x["net"] for x in rows], [x["t"] for x in rows], [cal[x["gd"]].date() for x in rows])
    keys = [J.iso_week_key(x["t"], cal[x["gd"]].date()) for x in rows]
    _, rlo, _ = J.cluster_bootstrap([x["R"] for x in rows], keys, order="sorted")
    srt = sorted(x["net"] for x in rows)
    k = int(np.ceil(0.01 * len(srt)))
    out = {"n": r["n"], "mean": r["mean"], "lo90": r["lo90"], "hi90": r["hi90"], "P1_pass": r["pass"],
           "R_mean": float(np.mean([x["R"] for x in rows])), "R_lo90": rlo,
           "win_rate": float(np.mean([x["net"] > 0 for x in rows])),
           "mean_ex_top1pct": float(np.mean(srt[:len(srt) - k])) if len(srt) > k else float("nan"),
           "exit_reasons": dict(Counter(x["why"] for x in rows)),
           "hold_median": float(np.median([x["hold"] for x in rows if x["hold"] is not None]))
           if any(x["hold"] is not None for x in rows) else None}
    if sub_windows:
        subs = []
        for a, b_ in sub_windows:
            v = [x["net"] for x in rows if pd.Timestamp(a) <= cal[x["gd"]] <= pd.Timestamp(b_)]
            subs.append({"win": [a, b_], "n": len(v), "mean": float(np.mean(v)) if v else None})
        out["sub"] = subs
        out["robust"] = sum(1 for s in subs if s["mean"] is not None and s["mean"] > 0) >= ROBUST_MIN_SUB
    return out


# ── 계좌 층(시기별 비용) ─────────────────────────────────────────────

def run_book(signals_by_gd, open_pos, size_fn, cal, start, end, seed, *, start_equity, costs: Costs,
             max_pos, daily_cap=None) -> dict:
    """``audit.book.run_book`` 과 같은 하루 순서 — 비용만 날짜별(매수 = costs.buy[gd] · 매도 = costs.sell[gd])."""
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
        ps._cs_sell = costs.sell[gd]
        cash += ps.k * ps.exit_px * (1 - ps._cs_sell)
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
        n_new = 0
        stop_why = None
        for s in todays:
            if s.ticker in pos or s.ticker in sold_today:
                continue
            cnt["signal"] += 1
            if stop_why is None and len(pos) >= max_pos:
                stop_why = "slot_full"
            if stop_why is None and daily_cap is not None and n_new >= daily_cap:
                stop_why = "daily_cap"
            if stop_why is not None:
                cnt[stop_why] += 1
                continue
            used = sum(x.cost_basis for x in pos.values())
            q, why = size_fn(s, B, used)
            if q <= 0:
                cnt["zero_" + why] += 1
                continue
            ps = open_pos(s, q)
            ps._cs_buy = costs.buy[gd]
            cash -= q * s.E_raw * (1 + ps._cs_buy)
            pos[s.ticker] = ps
            n_new += 1
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
        trades.append(ps)
    eq = np.array(equity)
    tot = 0.0
    for ps in trades:
        buy = ps.qty * ps.s.E_raw * (1 + ps._cs_buy)
        tot += (ps.k * ps.last_px - buy) if ps.exit_reason == "OPEN" else (ps.k * ps.exit_px * (1 - ps._cs_sell) - buy)
    recon = float(eq[-1] - (start_equity + tot)) if len(eq) else 0.0
    return {"equity": eq, "trades": trades, "dates": cal[g0:g1 + 1], "counts": dict(cnt), "recon": recon}


def books(sigs, bars, feats, win, kk, op, costs: Costs, mode="color", seeds=C.BOOK_SEEDS) -> dict:
    sbg = defaultdict(list)
    for s in sigs:
        sbg[s.gd].append(s)

    def opsize(s, B, used):
        P = int(round(s.E_raw))
        if s.m <= 0 or P <= 0:
            return 0, "mu"
        q = op.qty(P, s.N * (s.E_raw / s.E), budget=int(B), used=int(used), m=s.m)
        if q > 0:
            return q, "ok"
        return 0, ("funds" if int(B) - int(used) < P else "design")

    def open_pos(s, q):
        return Y30Pos(s, bars[s.ticker], feats[s.ticker], q, mode=mode, kk=kk)

    runs = [run_book(sbg, open_pos, opsize, cal_of(bars), win[0], win[1], sd, start_equity=float(C.BUDGET_C7),
                     costs=costs, max_pos=kk["max_pos"], daily_cap=kk["daily_cap"]) for sd in seeds]
    sm = BK.book_summary(runs, float(C.BUDGET_C7))
    sm["exit_reasons_seed0"] = dict(Counter(ps.exit_reason for ps in runs[0]["trades"]))
    keep = ("cagr_median", "cagr_min", "cagr_max", "mdd_median", "trades_median", "fills_per_year_median",
            "unaffordable_ratio_median", "recon_max_abs", "counts_seed0", "exit_reasons_seed0")
    out = {k: sm[k] for k in keep}
    out["per_seed_cagr"] = [x["cagr"] for x in sm["per_seed"]]
    out["P3_pass"] = bool(out["cagr_median"] > 0 and out["mdd_median"] >= C.P3_MDD)
    ua = out["unaffordable_ratio_median"]
    out["P4_pass"] = bool(out["fills_per_year_median"] >= C.P4_FILLS_PER_YEAR and not (ua == ua and ua >= C.P4_UNAFF))
    return out


_CAL = {}


def cal_of(_bars):
    return _CAL["cal"]


# ── 기준선 ───────────────────────────────────────────────────────────

def baselines(kser: pd.Series, m: np.ndarray, cal: pd.DatetimeIndex, win) -> dict:
    """지수(KOSPI200 → 069500) 단순 보유 · 시장 유닛 m 비례 보유(m 바뀐 만큼 그날 수수료 한쪽)."""
    a, b = pd.Timestamp(win[0]), pd.Timestamp(win[1])
    k = kser[(kser.index >= a - pd.Timedelta(days=10)) & (kser.index <= b)]
    k = k[~k.index.duplicated()]
    s = k[k.index >= a]
    if len(s) < 2:
        return {}
    first = k.index.get_loc(s.index[0])
    px = k.to_numpy(float)
    eq_bh = px[first:] / px[first - 1] if first > 0 else px / px[0]
    mser = pd.Series(m, index=cal).reindex(s.index).fillna(1.0).to_numpy(float)
    fee = YD.fee_one_way_on(pd.DatetimeIndex(s.index))
    rets = px[first:] / px[first - 1:-1] - 1 if first > 0 else np.concatenate([[0.0], px[1:] / px[:-1] - 1])
    eq, prev_m = 1.0, mser[0]
    eqm = []
    for i, r in enumerate(rets):
        mi = mser[i]
        eq *= (1 + mi * r) * (1 - abs(mi - prev_m) * fee[i])
        prev_m = mi
        eqm.append(eq)
    eqm = np.array(eqm)

    def cm(e):
        yrs = len(e) / 252.0
        return {"cagr": float(e[-1] ** (1 / yrs) - 1), "mdd": float((np.concatenate([[1.0], e]) /
                                                                     np.maximum.accumulate(np.concatenate([[1.0], e])) - 1).min()),
                "total": float(e[-1] - 1)}
    return {"index_bh": cm(eq_bh), "m_weighted": cm(eqm), "m_mean": float(np.mean(mser))}


# ── 무작위 진입 대조군 ───────────────────────────────────────────────

def random_control(pop, bars, feats, end_gd, kk, costs: Costs, reps=5) -> dict:
    elig = defaultdict(list)
    for t, b in bars.items():
        f = feats[t]
        di = b["di"]
        ok = ((np.arange(len(di)) >= 62) & b["mem"] & b["tvok"] & ~b["notrade"] & ~f["jump_block"]
              & (np.nan_to_num(f["atr"]) > 0))
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
            b = bars[t]
            D = j + 1
            s = DK.Sig(t, D, int(b["di"][D]), float(b["o"][D]), float(b["o"][D] * b["raw"][D]),
                       float(feats[t]["atr"][j]), float("nan"), p.s.m)
            q = run_path(s, b, feats[t], end_gd, kk=kk)
            vals.append(q.exit_px / q.E - 1 - costs.rt(q.s.gd, q.exit_gd if q.exit_gd is not None else end_gd))
        means.append(float(np.mean(vals)) if vals else float("nan"))
    return {"reps": reps, "mean_of_means": float(np.nanmean(means)), "per_rep": means}


# ── 선택 ─────────────────────────────────────────────────────────────

def n_changed(cfg, base):
    return sum(1 for k in base if cfg[k] != base[k])


def pick(cands, base, min_n):
    ok = [x for x in cands if x["T"]["n"] >= min_n and np.isfinite(x["T"].get("lo90", np.nan))]
    if not ok:
        return None, "후보 없음(거래 수 하한)"
    rob = [x for x in ok if x["T"].get("robust")]
    pool, note = (rob, "강건") if rob else (ok, "강건 아님")
    best = max(x["T"]["lo90"] for x in pool)
    tied = [x for x in pool if best - x["T"]["lo90"] < 1e-9]
    return min(tied, key=lambda x: n_changed(x["cfg"], base)), note


# ── 실행 ─────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(HERE, "result.json")
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else "AB"
    if DA.PN.sha256(os.path.join(HERE, "prereg.md")) != PREREG_SHA:
        raise SystemExit("[y30-donchian] prereg.md sha256 불일치 — 동결본이 아니다. 멈춘다")
    st, m, kser, info = YD.build(CACHE)
    cal = st.cal
    _CAL["cal"] = cal
    bars = st.bars
    era = Costs(cal)
    flat = Costs(cal, COST_FLAT)

    def gd_of(d, side="left"):
        return int(cal.searchsorted(pd.Timestamp(d), side=side)) - (1 if side == "right" else 0)

    win = {k: (gd_of(a), gd_of(b, "right")) for k, (a, b) in WINDOWS.items()}
    eras = [(a, b, gd_of(a), gd_of(b, "right")) for a, b in ERAS]
    t_years = (pd.Timestamp(T[1]) - pd.Timestamp(T[0])).days / 365.25
    min_n = int(np.ceil(MIN_TRADES_PER_YEAR * t_years))
    cls = load_strategy_class(DA.BRANCH_DONCHIAN, "DonchianSwingStrategy", "y30_branch_donchian_kk")
    if DA.PN.sha256(DA.BRANCH_DONCHIAN) != DA.BRANCH_SHA:
        raise SystemExit("[y30-donchian] 브랜치 전략 파일 sha256 불일치")
    fc: dict = {}
    res = {"prereg_sha256": PREREG_SHA, "data": info, "windows": WINDOWS, "T_sub": T_SUB, "eras": ERAS,
           "min_T_trades": min_n, "n_combos": N_COMBOS}

    def sigs_for(entry, kk, tv_mode="pct"):
        key = (entry["entry_n"], entry["vol_mult"], entry["clv"], tv_mode)
        if key not in fc:
            feats = {t: features_y30(b, entry_n=key[0], vol_mult=key[1], clv=key[2], tv_mode=tv_mode)
                     for t, b in bars.items()}
            raw = DK.build_signals(bars, feats, m)
            fc[key] = (feats, raw)
        feats, raw = fc[key]
        sg = [s for s in raw if not DA.r_half_blocked(s.E, s.N, kk)]
        return feats, mu_apply(sg, entry["mu"])

    def pop_for(entry, ex, w, *, mode="color", tv_mode="pct", acct=ACCT0, gw=None):
        kk = kk_of(ex, acct)
        feats, sg = sigs_for(entry, kk, tv_mode)
        fv = {t: feats_view(f, ex["chan"]) for t, f in feats.items()}
        g = win[w] if gw is None else gw
        return population(sg, bars, fv, g[0], g[1], mode=mode, kk=kk), sg, fv, kk, g

    def book_for(entry, ex, acct, rng_dates, *, costs=era, mode="color", tv_mode="pct"):
        kk = kk_of(ex, acct)
        feats, sg = sigs_for(entry, kk, tv_mode)
        fv = {t: feats_view(f, ex["chan"]) for t, f in feats.items()}
        op = OpSizer(cls, "donchian_swing", {"market_unit_mode": "enforce", "risk_pct": kk["risk_pct"],
                                             "position_ratio": acct["slots"][1], "max_positions": acct["slots"][0],
                                             "kk_r_floor_pct": ex["r"][0], "kk_r_atr_mult": ex["r"][1]})
        return books(sg, bars, fv, rng_dates, kk, op, costs, mode=mode)

    def rows_of(pop, g, costs=era):
        return pop_rows(pop, costs, g[1])

    # ═══ A — 현행 규칙 30년 판정 ═══
    if "A" in only:
        A = {"n_signals_raw": None}
        feats0, sg0 = sigs_for(ENTRY0, kk_of(EXIT0))
        A["n_signals"] = len(sg0)
        A["n_jump_blocked_bars"] = int(sum(int((f["jump_block"] & (np.arange(len(f["jump_block"])) >= 62)
                                                 & bars[t]["mem"]).sum()) for t, f in feats0.items()))
        for w in ("T", "V", "H"):
            pop, sg, fv, kk, g = pop_for(ENTRY0, EXIT0, w)
            rows = rows_of(pop, g)
            R = {"pop": stats(rows, cal, T_SUB if w == "T" else ())}
            R["pop_flat038"] = stats(rows_of(pop, g, flat), cal)
            popA, *_ = pop_for(ENTRY0, EXIT0, w, mode="adverse")
            sA = stats(rows_of(popA, g), cal)
            R["P5"] = dict(J.p5(R["pop"]["mean"], sA["mean"]), adverse_mean=sA["mean"],
                           n_trades_differ=int(sum(1 for a, b in zip(pop, popA)
                                                   if (a.exit_gd, a.exit_px) != (b.exit_gd, b.exit_px))))
            popN, *_ = pop_for(ENTRY0, EXIT0, w, tv_mode="nominal")
            R["pop_tv_nominal200"] = stats(rows_of(popN, g), cal)
            R["random_control"] = random_control(pop, bars, fv, g[1], kk, era)
            R["book"] = book_for(ENTRY0, EXIT0, ACCT0, WINDOWS[w])
            R["book_flat038"] = {k: v for k, v in book_for(ENTRY0, EXIT0, ACCT0, WINDOWS[w], costs=flat).items()
                                 if k in ("cagr_median", "mdd_median", "fills_per_year_median")}
            R["book_adverse"] = {k: v for k, v in book_for(ENTRY0, EXIT0, ACCT0, WINDOWS[w], mode="adverse").items()
                                 if k in ("cagr_median", "mdd_median")}
            R["baseline"] = baselines(kser, m, cal, WINDOWS[w])
            jump_tr = [x for x in rows if x["why"] == "JUMP"]
            R["jump_exits"] = len(jump_tr)
            A[w] = R
            print(f"[y30-donchian] A {w} n {R['pop']['n']} mean {R['pop']['mean']:+.5f} lo {R['pop']['lo90']:+.5f} | "
                  f"book {R['book']['cagr_median']:+.4f} mdd {R['book']['mdd_median']:+.3f} | "
                  f"bh {R['baseline'].get('index_bh', {}).get('cagr', float('nan')):+.4f}", f"{time.time()-t0:.0f}s",
                  flush=True)
        signs = [np.sign(A[w]["pop"]["mean"]) for w in ("T", "V", "H")]
        A["same_sign_TVH"] = bool(len(set(signs)) == 1)
        A["P_all"] = {w: {"P1": A[w]["pop"]["P1_pass"], "P3": A[w]["book"]["P3_pass"], "P4": A[w]["book"]["P4_pass"],
                          "P5": A[w]["P5"]["label"]} for w in ("T", "V", "H")}
        # 시대별(5년 단위) — 모집단 · 계좌(새 출발) · 기준선
        E = []
        for a, b, g0, g1 in eras:
            pop, sg, fv, kk, g = pop_for(ENTRY0, EXIT0, "T", gw=(g0, g1))
            rows = rows_of(pop, g)
            bk = book_for(ENTRY0, EXIT0, ACCT0, (a, b))
            E.append({"win": [a, b], "pop": stats(rows, cal),
                      "book": {k: bk[k] for k in ("cagr_median", "mdd_median", "fills_per_year_median")},
                      "baseline": baselines(kser, m, cal, (a, b)),
                      "by_m": {str(mv): {"n": sum(1 for x in rows if x["m"] == mv),
                                         "mean": float(np.mean([x["net"] for x in rows if x["m"] == mv]))
                                         if any(x["m"] == mv for x in rows) else None} for mv in (1.0, 0.75, 0.5)}})
            print(f"[y30-donchian] era {a[:4]}-{b[:4]} n {E[-1]['pop']['n']} mean {E[-1]['pop'].get('mean', float('nan')):+.5f}"
                  f" book {bk['cagr_median']:+.4f}", f"{time.time()-t0:.0f}s", flush=True)
        A["eras"] = E
        # 연도별 모집단(전 구간)
        pop, sg, fv, kk, g = pop_for(ENTRY0, EXIT0, "T", gw=(win["T"][0], win["H"][1]))
        rows = rows_of(pop, g)
        by = defaultdict(list)
        for x in rows:
            by[cal[x["gd"]].year].append(x["net"])
        A["yearly"] = {str(y): {"n": len(v), "mean": float(np.mean(v))} for y, v in sorted(by.items())}
        # 사전 등록 가설 H1 — 무장 뒤 채널 10 → 20 단독
        ex20 = dict(EXIT0, chan=20)
        H1 = {}
        cur_rows, new_rows = {}, {}
        for w in ("T", "V", "H"):
            pc, *_, g = pop_for(ENTRY0, EXIT0, w)
            pn, *_, g = pop_for(ENTRY0, ex20, w)
            cur_rows[w], new_rows[w] = rows_of(pc, g), rows_of(pn, g)
            H1[w] = {"new": stats(new_rows[w], cal), "diff": DO.diff_boot(new_rows[w], cur_rows[w], cal)}
            bn = book_for(ENTRY0, ex20, ACCT0, WINDOWS[w])
            bc = A[w]["book"]
            H1[w]["book_new"] = {k: bn[k] for k in ("cagr_median", "mdd_median", "fills_per_year_median")}
            H1[w]["seeds_new_better"] = int(sum(a > b for a, b in zip(bn["per_seed_cagr"], bc["per_seed_cagr"])))
        tv_new = new_rows["T"] + new_rows["V"]
        tv_cur = cur_rows["T"] + cur_rows["V"]
        H1["TV_pooled_diff"] = DO.diff_boot(tv_new, tv_cur, cal)
        H1["verdict"] = {
            "TV_lo90_pos": bool(H1["TV_pooled_diff"]["diff"] > 0 and H1["TV_pooled_diff"][f"q{C.BOOT_Q:g}"] > 0),
            "T_V_same_positive": bool(H1["T"]["diff"]["diff"] > 0 and H1["V"]["diff"]["diff"] > 0),
            "H_sign": float(np.sign(H1["H"]["diff"]["diff"]))}
        H1["verdict"]["pass"] = bool(H1["verdict"]["TV_lo90_pos"] and H1["verdict"]["T_V_same_positive"])
        A["H1_chan20"] = H1
        print(f"[y30-donchian] H1 TV diff {H1['TV_pooled_diff']['diff']:+.5f} lo {H1['TV_pooled_diff'][f'q{C.BOOT_Q:g}']:+.5f}"
              f" pass {H1['verdict']['pass']}", f"{time.time()-t0:.0f}s", flush=True)
        res["A"] = A
        _dump(res, out_path)

    # ═══ B — 최적화 ═══
    if "B" in only:
        Ares = []
        for cfg in GRID_A:
            pop, *_, g = pop_for(cfg, EXIT0, "T")
            Ares.append({"cfg": cfg, "T": stats(rows_of(pop, g), cal, T_SUB)})
        selA, noteA = pick(Ares, ENTRY0, min_n)
        print(f"[y30-donchian] B-A 선택 {selA and selA['cfg']} ({noteA})", f"{time.time()-t0:.0f}s", flush=True)
        Bres = []
        for cfg in GRID_B:
            pop, *_, g = pop_for(selA["cfg"], cfg, "T")
            Bres.append({"cfg": cfg, "T": stats(rows_of(pop, g), cal, T_SUB)})
        selB, noteB = pick(Bres, EXIT0, min_n)
        print(f"[y30-donchian] B-B 선택 {selB and selB['cfg']} ({noteB})", f"{time.time()-t0:.0f}s", flush=True)
        Cres = []
        for cfg in GRID_C:
            bv = book_for(selA["cfg"], selB["cfg"], cfg, T)
            ok = (bv["mdd_median"] >= C.P3_MDD and bv["fills_per_year_median"] >= C.P4_FILLS_PER_YEAR
                  and not (bv["unaffordable_ratio_median"] == bv["unaffordable_ratio_median"]
                           and bv["unaffordable_ratio_median"] >= C.P4_UNAFF))
            Cres.append({"cfg": cfg, "T_book": {k: v for k, v in bv.items()}, "eligible": ok})
        elig = [x for x in Cres if x["eligible"]] or Cres
        bestc = max(x["T_book"]["cagr_median"] for x in elig)
        selC = min([x for x in elig if bestc - x["T_book"]["cagr_median"] < 1e-12],
                   key=lambda x: n_changed(x["cfg"], ACCT0))
        print(f"[y30-donchian] B-C 선택 {selC['cfg']}", f"{time.time()-t0:.0f}s", flush=True)
        Bout = {"stageA": {"selected": selA["cfg"], "note": noteA, "grid": Ares},
                "stageB": {"selected": selB["cfg"], "note": noteB, "grid": Bres},
                "stageC": {"selected": selC["cfg"], "grid": Cres}}
        for name, lst in (("stageA", Ares), ("stageB", Bres)):
            okl = [x for x in lst if x["T"]["n"] >= min_n]
            Bout[name]["best_by_R_lo90"] = max(okl, key=lambda x: x["T"]["R_lo90"])["cfg"] if okl else None
        cur = (ENTRY0, EXIT0, ACCT0)
        new = (selA["cfg"], selB["cfg"], selC["cfg"])
        Jd, rowsd = {}, {}
        for tag, (en, ex, ac) in {"current": cur, "selected": new}.items():
            R = {}
            for w in ("T", "V", "H"):
                pop, sg, fv, kk, g = pop_for(en, ex, w)
                rws = rows_of(pop, g)
                rowsd[(tag, w)] = rws
                R[f"pop_{w}"] = stats(rws, cal)
                R[f"pop_{w}_flat038"] = stats(rows_of(pop, g, flat), cal).get("mean")
                R[f"book_{w}"] = book_for(en, ex, ac, WINDOWS[w])
            popA, *_, g = pop_for(en, ex, "V", mode="adverse")
            R["P5_V"] = J.p5(R["pop_V"]["mean"], stats(rows_of(popA, g), cal)["mean"])
            pop, sg, fv, kk, g = pop_for(en, ex, "V")
            R["random_control_V"] = random_control(pop, bars, fv, g[1], kk, era)
            R["P_V"] = {"P1": R["pop_V"]["P1_pass"], "P2_H_sign": bool(np.sign(R["pop_H"]["mean"]) == np.sign(R["pop_V"]["mean"])),
                        "P3": R["book_V"]["P3_pass"], "P4": R["book_V"]["P4_pass"], "P5": R["P5_V"]["label"]}
            Jd[tag] = R
        if selC["cfg"] != ACCT0:
            Jd["selected_AB_currentC"] = {f"book_{w}": book_for(selA["cfg"], selB["cfg"], ACCT0, WINDOWS[w])
                                          for w in ("T", "V", "H")}
        q_bonf = 0.05 / N_COMBOS
        dV = DO.diff_boot(rowsd[("selected", "V")], rowsd[("current", "V")], cal)
        dVb = DO.diff_boot(rowsd[("selected", "V")], rowsd[("current", "V")], cal, n_boot=20000, qs=(q_bonf,))
        dT = DO.diff_boot(rowsd[("selected", "T")], rowsd[("current", "T")], cal)
        dH = DO.diff_boot(rowsd[("selected", "H")], rowsd[("current", "H")], cal)
        sv, cv = Jd["selected"]["book_V"]["per_seed_cagr"], Jd["current"]["book_V"]["per_seed_cagr"]
        seeds_better = int(sum(a > b for a, b in zip(sv, cv)))
        rule3 = bool(dV["diff"] > 0 and dV[f"q{C.BOOT_Q:g}"] > 0)
        rule3_b = bool(dV["diff"] > 0 and dVb[f"q{q_bonf:g}"] > 0)
        pv = Jd["selected"]["P_V"]
        p_all = bool(pv["P1"] and pv["P2_H_sign"] and pv["P3"] and pv["P4"] and pv["P5"] == "유지")
        h_flip = bool(np.sign(dH["diff"]) != np.sign(dV["diff"]))
        label = ("채택 권고" if (rule3 and p_all and not h_flip) else "보류" if (rule3 and h_flip) else "현행 유지")
        Bout["judge"] = {"diff_T": dT, "diff_V": dV, "diff_V_bonferroni": dVb, "diff_H": dH, "rule3_pass": rule3,
                         "rule3_bonferroni_pass": rule3_b, "P1toP5_pass": p_all, "H_flip": h_flip,
                         "V_book_seeds_selected_better": seeds_better,
                         "stageC_adopt": bool(selC["cfg"] == ACCT0 or seeds_better >= 12), "label": label}
        Bout["detail"] = Jd
        res["B"] = Bout
        print(f"[y30-donchian] B 판정 {label} V 차 {dV['diff']:+.5f} lo {dV[f'q{C.BOOT_Q:g}']:+.5f} H 차 {dH['diff']:+.5f}"
              f" 씨앗 {seeds_better}/16", f"{time.time()-t0:.0f}s", flush=True)
        _dump(res, out_path)
    res["elapsed_s"] = time.time() - t0
    _dump(res, out_path)
    print("[y30-donchian] done", out_path, f"{res['elapsed_s']:.0f}s")


def _dump(res, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        try:
            with open(path) as fh:
                old = json.load(fh)
            for k in ("A", "B"):
                if k in old and k not in res:
                    res[k] = old[k]
        except Exception:
            pass
    with open(path, "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else (list(o) if isinstance(o, tuple) else str(o)))


if __name__ == "__main__":
    main()
