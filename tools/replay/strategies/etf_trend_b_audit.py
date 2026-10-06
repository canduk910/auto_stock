#!/usr/bin/env python3
"""운용 전략 전수 점검 §3.7 — etf_trend(묶음 B) 판정 실행(동결본 sha 2d7e7b42).

계좌 층(``EtfPos``·``etf_book``)과 운영 해석판 판정을 둔다. 신호·청산 식은 ``etf_trend_b``(관문 2 비트 일치)를 쓴다.

판(같은 보관소 · 같은 유니버스 분류):
- ``adj``  = cycle391b 판정판 그대로 — 분배 수정가로 신호·청산 판정
- ``raw``  = 운영 해석판(판정) — 운영은 DB 원본가(``stock_master_daily``)로 돌파·손절·채널·15:20 을 판정한다(K1 E3).
            판정은 원본가로, 수익은 같은 체결 봉·가격을 수정 계수로 환산해 분배금을 포함한다(``adj_return``)
가중: ``one`` = 운영 시드 ``market_unit_mode="shadow"``(m ≤ 0·결손만 거름, 랏 축소 없음 — K1 E2) ·
      ``m`` = ``enforce``(랏 × m — cycle391b 의 m 가중)
비용: 판정 = 왕복 0.38%(C1) · 민감도 0.28/0.48 · 보고 = cycle391b ETF 비용(0.06/0.11%)

실행: python tools/replay/strategies/etf_trend_b_audit.py [--out PATH]
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ROOT = os.path.abspath(os.path.join(_TOOLS, ".."))
for _p in (_TOOLS, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from replay.audit import bars as BR  # noqa: E402
from replay.audit import book as BK  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.strategies import etf_trend_b as EB  # noqa: E402

FULL_START, FULL_END = "2021-01-01", "2026-09-23"
PERIOD_A = ("2021-01-01", "2022-12-31")
H_START = C.H1Y[0]
SEED_BOOT, SEED_SLEEVE = 20261002, 20263002
T1_MIN_R, T2_MIN_R, T5_MIN_MDD, T6_MIN_RATIO = 0.15, -0.20, -20.0, 0.5


# ── 계좌 층 ─────────────────────────────────────────────────────────────

@dataclass
class ETFSig:
    ticker: str
    ti: int          # 진입 봉(D) — 종목 배열 인덱스
    gd: int          # 진입일 전역 달력 인덱스
    E: float         # 판정 가격 기준 진입가(시가)
    E_raw: float     # 원화 진입가
    N: float         # n14(신호봉)
    line: float      # 돌파선(직전 20봉 고가)
    m: float
    tv20: float
    sig_ci: int


class EtfPos:
    """한 랏을 날마다 걷는다 — ``sim_b`` 와 같은 청산(시가 갭 → 장중 선 → D+2 부터 종가 < 돌파선 → 다음 봉 선 갱신).

    ``fadj`` = 수정가 ÷ 판정가 배율(원본가 판정판의 분배금 환산). 원화 배율 ``k`` 가 보유 중 분배락마다 커진다.
    """

    def __init__(self, sig: ETFSig, d: dict, qty: int, *, mode: str = "color", fadj=None):
        self.s, self.d, self.qty, self.mode, self.fadj = sig, d, qty, mode, fadj
        self.E = sig.E
        self.hard = max(sig.E - 2.0 * sig.N, sig.E * 0.91)
        self.stop = self.hard
        self.hsb = -np.inf
        self._k0 = (qty * sig.E_raw / sig.E) if sig.E > 0 else 0.0
        self.k = self._k0
        self.cost_basis = qty * sig.E_raw
        self.exit_px = self.exit_reason = self.exit_gd = self.exit_ti = None
        self.last_px = sig.E

    def _kupd(self, ti):
        if self.fadj is not None:
            self.k = self._k0 * self.fadj[ti] / self.fadj[self.s.ti]

    def _exit(self, px, reason, gd, ti=None):
        self.exit_px, self.exit_reason, self.exit_gd = px, reason, gd
        if ti is not None:
            self.exit_ti = ti

    def _ch(self, ti):
        if ti >= self.s.ti + 1:
            return float(np.min(self.d["l"][max(0, ti - 10):ti]))
        return -np.inf

    def cur_ti(self, gd):
        ci = self.d["ci"]
        k = int(np.searchsorted(ci, gd))
        return k if (k < len(ci) and ci[k] == gd) else None

    def data_ended(self, gd):
        return self.d["ci"][-1] < gd

    def open_phase(self, ti: int, gd: int) -> bool:
        self._kupd(ti)
        if ti == self.s.ti:
            return False
        o = self.d["o"][ti]
        ch = self._ch(ti)
        if o <= self.stop or o < ch:          # 원본 우선순위(손절선 먼저)
            self._exit(o, "stop_gap" if o <= self.stop else "chan10_gap", gd, ti)
            return True
        return False

    def intraday_phase(self, ti: int, gd: int, is_entry: bool) -> bool:
        self._kupd(ti)
        d = self.d
        ch = self._ch(ti)

        def lines():
            ls = [BR.Line(self.stop, "stop")]
            if np.isfinite(ch):
                ls.append(BR.Line(ch, "chan10", strict=True))
            return ls

        ex = BR.walk_bar(d["o"][ti], d["h"][ti], d["l"][ti], d["c"][ti], lines_fn=lines, mode=self.mode,
                         ratchet="next_bar", gap_check=False, pick=EB._pick)
        if ex is not None:
            self._exit(ex.px, ex.reason, gd, ti)
            return True
        if ti >= self.s.ti + 1 + 1 and d["c"][ti] < self.s.line:     # D+2 부터 15:20 돌파 실패(종가 근사)
            self._exit(d["c"][ti], "below_line", gd, ti)
            return True
        self.last_px = d["c"][ti]
        self.hsb = max(self.hsb, d["h"][ti])
        be = self.E if self.hsb >= self.E + 1.5 * self.s.N else -np.inf
        self.stop = max(self.hard, be, self.hsb - 1.8 * self.s.N)
        return False

    def value(self) -> float:
        return self.k * self.last_px


def run_path_etf(sig: ETFSig, d: dict, *, mode: str = "color", fadj=None) -> EtfPos:
    """자금 제약 없는 한 랏(1주) — ``sim_b`` 와 같은 결과(관문 대조·테스트용)."""
    ps = EtfPos(sig, d, 1, mode=mode, fadj=fadj)
    n = len(d["c"])
    for ti in range(sig.ti, n):
        gd = int(d["ci"][ti])
        if ti > sig.ti and ps.open_phase(ti, gd):
            return ps
        if ps.intraday_phase(ti, gd, ti == sig.ti):
            return ps
    ps._exit(d["c"][n - 1], "end", int(d["ci"][n - 1]), n - 1)
    return ps


def etf_book(signals_by_gd: dict, open_pos, size_fn, cal: pd.DatetimeIndex, start: str, end: str, *,
             start_equity: float, cost_side: float, max_pos: int, corr, seed: int = 0) -> dict:
    """``audit.book.run_book`` 과 같은 하루 순서 + 운영 매수 순서(20일 거래대금 내림차순) + 묶음 캡.

    묶음 캡(운영 ``_cluster_blocked``): 풀 = 보유 ∪ 당일 매도 ∪ 오늘 이미 고른 종목, 상관 > 0.9 이면 거른다.
    검사 순서 = 운영 ``check_buy_signal``(보유·당일 매도 → 슬롯 → 묶음 → 수량).
    """
    rng = np.random.default_rng(seed)
    g0 = int(cal.searchsorted(pd.Timestamp(start)))
    g1 = int(cal.searchsorted(pd.Timestamp(end), side="right")) - 1
    cash = float(start_equity)
    pos: dict = {}
    eq_prev = float(start_equity)
    equity, trades = [], []
    cnt = Counter()
    for gd in range(g0, g1 + 1):
        B = eq_prev
        sold_today = set()
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                continue
            if ps.open_phase(ti, gd):
                cash += ps.k * ps.exit_px * (1 - cost_side)
                trades.append(ps)
                sold_today.add(t)
                del pos[t]
        todays = list(signals_by_gd.get(gd, []))
        rng.shuffle(todays)
        todays.sort(key=lambda s: -s.tv20)            # 안정 정렬 — 동률만 씨앗이 가른다
        taken: list = []
        for s in todays:
            if s.ticker in pos or s.ticker in sold_today:
                continue
            cnt["signal"] += 1
            if len(pos) >= max_pos:
                cnt["slot_full"] += 1
                continue
            pool = set(pos) | sold_today | set(taken)
            if any(EB.same_cluster(corr, s.ticker, o, s.sig_ci) for o in pool if o != s.ticker):
                cnt["cluster"] += 1
                continue
            used = sum(x.cost_basis for x in pos.values())
            q, why = size_fn(s, B, used)
            if q <= 0:
                cnt["zero_" + why] += 1
                continue
            ps = open_pos(s, q)
            cash -= q * s.E_raw * (1 + cost_side)
            pos[s.ticker] = ps
            taken.append(s.ticker)
            cnt["fill"] += 1
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                if ps.data_ended(gd):
                    ps._exit(ps.last_px, "END", gd)
                    cash += ps.k * ps.exit_px * (1 - cost_side)
                    trades.append(ps)
                    del pos[t]
                continue
            if ps.intraday_phase(ti, gd, ti == ps.s.ti):
                cash += ps.k * ps.exit_px * (1 - cost_side)
                trades.append(ps)
                del pos[t]
        eq = cash + sum(x.value() for x in pos.values())
        equity.append(eq)
        eq_prev = eq
    for ps in pos.values():
        ps._exit(ps.last_px, "OPEN", None)
        trades.append(ps)
    eq = np.array(equity)
    return {"equity": eq, "trades": trades, "dates": cal[g0:g1 + 1], "counts": dict(cnt),
            "recon": BK.reconcile(eq, trades, start_equity, cost_side)}


# ── 비용 · 수익 환산 ─────────────────────────────────────────────────────

def rnet_at(t: dict, cost_rt: float) -> float:
    """cycle391 ``Rnet`` 식에 비용만 바꿔 넣는다 — (청산가 − 진입가 − 비용 × 진입가) ÷ 2N."""
    return (t["exit_px"] - t["E"] - cost_rt * t["E"]) / t["rw"]


def adj_return(E_raw: float, px_raw: float, f_entry: float, f_exit: float) -> float:
    """원본가로 판정한 체결 → 수정가 수익(분배금 포함). f = 그 봉의 수정가 ÷ 원본가."""
    return (px_raw * f_exit) / (E_raw * f_entry) - 1.0


def rnet_ret(t: dict, cost_rt: float) -> float:
    return (t["ret"] - cost_rt) / (t["rw"] / t["E"])


# ── 판정 재료 ───────────────────────────────────────────────────────────

def _w(t, weight):
    return t["m"] if weight == "m" else 1.0


def wmean(ts, key, weight):
    if not ts:
        return float("nan")
    w = np.array([_w(t, weight) for t in ts])
    v = np.array([t[key] for t in ts])
    return float((w * v).sum() / w.sum())


def t_stats(ded: list, ded_live: list, weight: str, cost, *, years: float) -> dict:
    """T1~T6(설계서 §8.1 문턱 그대로) + P2(H 부호). ``cost`` = 왕복 비율 또는 "etf"(cycle391 비용)."""
    def rn(t):
        return t["Rnet"] if cost == "etf" else rnet_ret(t, cost)
    ts = [dict(t, RN=rn(t)) for t in ded]
    live = [dict(t, RN=rn(t)) for t in ded_live]
    wR = wmean(ts, "RN", weight)
    _, lo, hi = J.cluster_bootstrap([t["RN"] for t in ts], [t["entry_ci"] for t in ts],
                                    weights=[_w(t, weight) for t in ts], seed=SEED_BOOT, q=0.025, order="first")
    A = [t for t in ts if PERIOD_A[0] <= t["entry_date"] <= PERIOD_A[1]]
    ex25 = [t for t in ts if not t["entry_date"].startswith("2025")]
    k = int(np.ceil(0.01 * len(ts)))
    top = sorted(ts, key=lambda x: -x["RN"])[k:]
    sl_in = [dict(t, Rnet=t["RN"], m=(t["m"] if weight == "m" else 1.0)) for t in ts]
    sl = J.r_sleeve(sl_in, SEED_SLEEVE, years=years)
    wl = wmean(live, "RN", weight)
    ratio = wR / wl if wl > 0 else float("nan")
    H = [t for t in ts if t["entry_date"] >= H_START]
    out = {"n": len(ts), "wR": wR, "ci95": [lo, hi], "n_A": len(A), "wR_A": wmean(A, "RN", weight),
           "wR_ex2025": wmean(ex25, "RN", weight), "wR_ex_top1pct": wmean(top, "RN", weight),
           "sleeve": sl, "T6": {"wR_all": wR, "wR_listed_only": wl, "n_listed_only": len(live), "ratio": ratio},
           "H": {"n": len(H), "wR": wmean(H, "RN", weight)}}
    out["judge"] = {
        "T1": bool(wR >= T1_MIN_R and lo > 0), "T2": bool(out["wR_A"] >= T2_MIN_R),
        "T3": bool(out["wR_ex2025"] > 0), "T4": bool(out["wR_ex_top1pct"] > 0),
        "T5": bool(sl["ann_mean"] > 0 and sl["mdd_median"] >= T5_MIN_MDD),
        "T6_warning_ok": bool(ratio == ratio and ratio >= T6_MIN_RATIO)}
    out["judge"]["pass_T1_T5"] = all(out["judge"][x] for x in ("T1", "T2", "T3", "T4", "T5"))
    out["P2"] = (J.p2([t["RN"] for t in H], wR) if weight == "one" else
                 {"n": len(H), "mean_m_weighted": out["H"]["wR"], "same_sign": bool(np.sign(out["H"]["wR"]) == np.sign(wR))})
    by_y = defaultdict(list)
    for t in ts:
        by_y[t["entry_date"][:4]].append(t)
    out["yearly"] = {y: {"n": len(v), "wR": wmean(v, "RN", weight)} for y, v in sorted(by_y.items())}
    out["reasons"] = dict(Counter(t["reason"] for t in ts))
    return out


def k3_db_tail(cls: dict, since: str = "2026-09-23") -> dict:
    """K3 보고만(§3.7) — 보관소 끝(09-23) 뒤 DB 원본 일봉으로 운영 leaf ``entry_signal``·``gap_skip_reason`` 을 그대로 돌린다.
    유니버스 = 분류(cls) ∧ ``stock_master.hts_avls_eok ≥ 500``. 품질 창(069500 최신봉·60봉 결손)·묶음 캡·슬롯은 적용 전."""
    from replay.audit import market_unit as MU
    from replay.audit import panel as PN
    from src.engine import etf_trend_core as core
    e = PN.load_db_extract()
    mc, mr = e["master"]
    ms = {r[0]: dict(zip(mc, r)) for r in mr}
    c, r = e["daily"]
    df = pd.DataFrame(r, columns=c)
    df["bas_dd"] = df.bas_dd.str[:10]
    df = df[(df.open_price > 0) & (df.high_price > 0) & (df.low_price > 0) & (df.close_price > 0)]
    k = df[df.ticker == MU.SOURCE_TICKER].sort_values("bas_dd")
    mday = dict(zip(k.bas_dd, MU.m_at_bars(k.close_price.to_numpy(float))))
    rows, nuni = [], 0
    for t, g in df.groupby("ticker"):
        if not cls.get(t) or (ms.get(t, {}).get("hts_avls_eok") or 0) < 500:
            continue
        nuni += 1
        g = g.sort_values("bas_dd")
        d = list(g.bas_dd)
        H, L, CC, TV, O = [g[x].tolist() for x in ("high_price", "low_price", "close_price", "trade_value",
                                                    "open_price")]
        for j, dd in enumerate(d):
            if dd < since:
                continue
            sg = core.entry_signal(H[:j + 1], L[:j + 1], CC[:j + 1], TV[:j + 1], j)
            if sg.ok:
                gap = core.gap_skip_reason(O[j + 1], CC[j], sg.line) if j + 1 < len(O) else "no_next_bar"
                rows.append({"ticker": t, "signal_date": dd, "m": float(mday.get(dd, float("nan"))), "gap": gap})
    return {"universe": nuni, "signals": rows,
            "entry_candidates_gap_pass": sum(1 for x in rows if x["gap"] is None)}


def _import_operating_class():
    for k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
        os.environ.setdefault(k, "audit-dummy")        # R3 — import 때 설정 검증만 통과(값은 쓰이지 않는다)
    from src.engine.strategies.etf_trend import EtfTrendStrategy
    return EtfTrendStrategy


def main():  # noqa: C901 — 판정 순서를 한 곳에서 읽히게 둔다
    t0 = time.time()
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(
        C.REPO, "_workspace/analysis/strategy_audit_20261005/etf_trend/result.json")
    from replay.audit import gate_c391b as GT
    from replay.audit import market_unit as MU
    from replay.audit import panel as PN
    from replay.audit.sizing import OpSizer
    from src.engine import etf_trend_core as core

    c391 = GT.load_c391()
    PN.check_archive(C.ETF_ARCHIVE, C.ETF_PARQUET_SHA)
    cls, meta = GT.classify(c391)
    listed = {t: m["listed_at_end"] for t, m in meta.items()}
    full = PN.load_archive(C.ETF_ARCHIVE)
    cal = pd.DatetimeIndex(sorted(full.bas_dd.unique()))
    need = {t for t, v in cls.items() if v} | {MU.SOURCE_TICKER}
    st = PN.build_store(full, nontrade="drop", junction_rescale=False, cal=cal, tickers=need)
    raw_full = full.copy()
    for x in ("open", "high", "low", "close"):
        raw_full[x + "_adj"] = raw_full[x]
    st_raw = PN.build_store(raw_full, nontrade="drop", junction_rescale=False, cal=cal, tickers=need)
    last_ci = len(cal) - 1
    res = {"inputs": {"cycle391_module": GT.BASE_SHA, "etf_parquet": "sha 7개 대조 통과",
                      "U1_class_total": int(sum(cls.values())), "cal": [str(cal[0].date()), str(cal[-1].date()),
                                                                        len(cal)]}}
    V = {}
    for basis, store in (("adj", st), ("raw", st_raw)):
        data = {t: EB.ticker_arrays(b) for t, b in store.bars.items()}
        k200 = data[MU.SOURCE_TICKER]
        mu = np.full(len(cal), np.nan)
        mu[k200["ci"]] = MU.m_at_bars(k200["c"])
        dcls = {t: d for t, d in data.items() if cls.get(t)}
        trades = EB.gen_trades(dcls, cls, mu, cal, listed, last_ci)
        fadj = {t: st.bars[t]["c"] / st_raw.bars[t]["c"] for t in dcls} if basis == "raw" else None
        for t in trades:
            if basis == "adj":
                t["ret"] = t["exit_px"] / t["E"] - 1
            else:
                f = fadj[t["ticker"]]
                t["ret"] = adj_return(t["E"], t["exit_px"], f[t["j"] + 1], f[t["k"]])
                t["Rnet"] = (t["ret"] - t["cost"]) / (t["rw"] / t["E"])    # ETF 비용판도 분배금 포함으로
        tick_list = sorted(data)
        col = {t: i for i, t in enumerate(tick_list)}
        ret = np.full((len(cal), len(tick_list)), np.nan)
        for t, d in data.items():
            cc = np.full(len(cal), np.nan)
            cc[d["ci"]] = d["c"]
            ret[1:, col[t]] = cc[1:] / cc[:-1] - 1
        corr = EB.Corr(ret, col)
        allt = [t for t in trades if t["entry_date"] >= FULL_START and t["m"] is not None]
        base = [t for t in allt if EB.full_u(t)]
        buy = [t for t in base if t["m"] > 0]
        ded = EB.dedup(buy, corr)
        ded_live = EB.dedup([t for t in buy if t["listed_at_end"]], corr)
        V[basis] = dict(data=data, mu=mu, trades=trades, buy=buy, ded=ded, ded_live=ded_live, corr=corr,
                        fadj=fadj, store=store)
        res[f"counts_{basis}"] = {"raw_trades": len(trades), "full_universe": len(base), "m_pos": len(buy),
                                  "dedup": len(ded), "dedup_listed_only": len(ded_live)}
        print(f"[etf:{basis}] counts", res[f"counts_{basis}"], f"{time.time()-t0:.0f}s", flush=True)

    # ── K1 자동 대조 ──
    k1 = {}
    mu_a, mu_r = V["adj"]["mu"], V["raw"]["mu"]
    dm = np.where(~((mu_a == mu_r) | (np.isnan(mu_a) & np.isnan(mu_r))))[0]
    k1["market_unit_adj_vs_raw_diff_days"] = {"n": int(len(dm)), "first": [str(cal[i].date()) for i in dm[:10]]}
    # (a) 운영 leaf simulate_exit = 판정판 sim_b(수정가 배열 · 분류 종목 원 거래 전부)
    nmis, nchk, ex = 0, 0, []
    for t in V["adj"]["trades"]:
        d = V["adj"]["data"][t["ticker"]]
        lists = [list(map(float, d[x])) for x in ("o", "h", "l", "c")]
        k2, px2, why2 = core.simulate_exit(*lists, t["j"])
        why = t["reason"] if t["reason"] not in ("open_end", "delist") else "end"
        nchk += 1
        if not (k2 == t["k"] and why2 == why and abs(px2 - t["exit_px"]) <= 1e-9 * max(1.0, abs(px2))):
            nmis += 1
            if len(ex) < 5:
                ex.append({"t": t["ticker"], "j": t["j"], "op": (k2, px2, why2), "replay": (t["k"], t["exit_px"], why)})
    k1["op_simulate_exit_vs_sim_b"] = {"checked": nchk, "mismatch": nmis, "examples": ex}
    print("[etf] K1 simulate_exit", k1["op_simulate_exit_vs_sim_b"]["checked"], nmis, flush=True)
    # (b) 운영 entry_signal(225봉 창 · EMA60/ATR20 창 시작 효과) = 재현 신호 조건(수정가 · 같은 배열)
    rows = 225
    sig_set = {(t["ticker"], t["j"]) for t in V["adj"]["trades"]}
    n_eval, only_op, only_rep, ex2 = 0, 0, 0, []
    for tk, d in V["adj"]["data"].items():
        if not cls.get(tk):
            continue
        h, l, c, tv = d["h"], d["l"], d["c"], d["tv"]
        o = d["o"]
        hp = d["hi_prev20"]
        for j in np.nonzero((np.arange(len(c)) >= EB.MIN_BARS - 1) & (c > np.nan_to_num(hp, nan=np.inf)))[0]:
            if j + 1 >= len(c) or d["ci"][j + 1] != d["ci"][j] + 1:
                continue
            lo_ = max(0, j - rows + 1)
            s = core.entry_signal(list(h[lo_:j + 1]), list(l[lo_:j + 1]), list(c[lo_:j + 1]), list(tv[lo_:j + 1]),
                                  j - lo_)
            okop = bool(s.ok and core.gap_skip_reason(o[j + 1], c[j], s.line) is None)
            a20 = d["atr20"][j]
            rep = (tk, int(j)) in sig_set and (c[j] <= EB.PX_MAX and a20 / c[j] <= EB.ATR_HI)
            n_eval += 1
            if okop != rep:
                only_op += int(okop)
                only_rep += int(rep)
                if len(ex2) < 8:
                    ex2.append({"t": tk, "date": str(cal[d["ci"][j]].date()), "op": okop, "replay": rep,
                                "op_stage": s.stage})
    k1["op_entry_signal_225rows_vs_replay"] = {"evaluated_breakout_days": n_eval, "only_operating": only_op,
                                               "only_replay": only_rep, "examples": ex2}
    print("[etf] K1 entry_signal", k1["op_entry_signal_225rows_vs_replay"], flush=True)
    # (c) 원본가 판정 ↔ 수정가 판정 신호 집합
    sa = {(t["ticker"], t["entry_ci"]) for t in V["adj"]["buy"]}
    sr = {(t["ticker"], t["entry_ci"]) for t in V["raw"]["buy"]}
    k1["signals_adj_vs_raw"] = {"adj": len(sa), "raw": len(sr), "both": len(sa & sr),
                                "only_adj": len(sa - sr), "only_raw": len(sr - sa)}
    ea = {(t["ticker"], t["entry_ci"]): (t["exit_ci"], t["reason"]) for t in V["adj"]["ded"]}
    er = {(t["ticker"], t["entry_ci"]): (t["exit_ci"], t["reason"]) for t in V["raw"]["ded"]}
    com = set(ea) & set(er)
    k1["exits_adj_vs_raw_common_dedup"] = {"common": len(com), "exit_differs": sum(1 for x in com if ea[x] != er[x]),
                                           "reason_changed": dict(Counter(f"{ea[x][1]}→{er[x][1]}" for x in com
                                                                          if ea[x] != er[x]))}
    res["K1_auto"] = k1

    # ── T1~T6 · P2 ──
    yrs = (pd.Timestamp(FULL_END) - pd.Timestamp(FULL_START)).days / 365.25
    TT = {}
    for basis in ("raw", "adj"):
        for weight in ("one", "m"):
            for cost in (C.COST_RT_JUDGE, *C.COST_RT_SENS, "etf"):
                TT[f"{basis}|{weight}|{cost}"] = t_stats(V[basis]["ded"], V[basis]["ded_live"], weight, cost, years=yrs)
    res["T"] = TT
    for key in ("raw|one|0.0038", "adj|one|0.0038", "raw|m|0.0038", "adj|m|etf"):
        x = TT[key]
        print(f"[etf] T {key}: n={x['n']} wR={x['wR']:+.4f} ci={x['ci95'][0]:+.4f} A={x['wR_A']:+.4f} "
              f"ex25={x['wR_ex2025']:+.4f} top1={x['wR_ex_top1pct']:+.4f} sleeve={x['sleeve']['ann_mean']:+.2f}%/"
              f"{x['sleeve']['mdd_median']:+.2f} T6={x['T6']['ratio']:.2f} pass={x['judge']['pass_T1_T5']}", flush=True)
    # P5 — 이 청산 규칙은 봉 안에서 선을 올리지 않는다 → 불리 경로도 같은 청산
    p5n = 0
    for t in V["raw"]["ded"]:
        d = V["raw"]["data"][t["ticker"]]
        if EB.sim_b(d, t["j"], mode="adverse")[:2] != (t["k"], t["exit_px"]):
            p5n += 1
    res["P5"] = {"trades": len(V["raw"]["ded"]), "exit_differs_adverse": p5n,
                 "label": "유지" if p5n == 0 else "확인 필요"}

    # ── P3 · P4 — C7 단독 풀 계좌(운영 사이저) ──
    EtfTrendStrategy = _import_operating_class()

    def sigs_of(basis):
        data, store = V[basis]["data"], V[basis]["store"]
        out = defaultdict(list)
        for t in V[basis]["buy"]:
            d = data[t["ticker"]]
            j = t["j"]
            raw = store.bars[t["ticker"]]["raw"][j + 1]
            out[t["entry_ci"]].append(ETFSig(t["ticker"], j + 1, t["entry_ci"], float(d["o"][j + 1]),
                                             float(d["o"][j + 1] * raw), float(d["n14"][j]),
                                             float(d["hi_prev20"][j]), float(t["m"]), float(t["tv20"]), t["sig_ci"]))
        return out

    def book(basis, mu_mode, win, cost_rt, seeds=C.BOOK_SEEDS):
        op = OpSizer(EtfTrendStrategy, "etf_trend", {"market_unit_mode": mu_mode}, atr_keys=("atr",))
        data, fadj = V[basis]["data"], V[basis]["fadj"]
        sbg = sigs_of(basis)

        def size_fn(s, B, used):
            P = int(round(s.E_raw))
            q = op.qty(P, s.N * (s.E_raw / s.E), budget=int(B), used=int(used), m=s.m)
            if q > 0:
                return q, "ok"
            return 0, ("funds" if int(B) - int(used) < P else "design")

        def open_pos(s, q):
            return EtfPos(s, data[s.ticker], q, fadj=(fadj[s.ticker] if fadj is not None else None))
        runs = [etf_book(sbg, open_pos, size_fn, cal, win[0], win[1], start_equity=float(C.BUDGET_C7),
                         cost_side=cost_rt / 2, max_pos=EB.SLOTS, corr=V[basis]["corr"], seed=sd) for sd in seeds]
        sm = BK.book_summary(runs, float(C.BUDGET_C7))
        c0 = runs[0]["counts"]
        free = c0.get("signal", 0) - c0.get("slot_full", 0)
        sm["unaffordable_ratio_median"] = sm["unaffordable_ratio_median"]
        sm["cluster_or_slot_ratio_seed0"] = ((c0.get("slot_full", 0) + c0.get("cluster", 0)) / c0["signal"]
                                             if c0.get("signal") else float("nan"))
        sm["free_signals_seed0"] = free
        sm["exit_reasons_seed0"] = dict(Counter(ps.exit_reason for ps in runs[0]["trades"]))
        sm["per_seed_identical"] = len({round(float(r["equity"][-1]), 6) for r in runs}) == 1
        return {k: sm[k] for k in ("cagr_median", "cagr_min", "cagr_max", "mdd_median", "trades_median",
                                   "fills_per_year_median", "unaffordable_ratio_median", "recon_max_abs",
                                   "counts_seed0", "cluster_or_slot_ratio_seed0", "exit_reasons_seed0",
                                   "per_seed_identical")}

    BKS = {}
    for basis in ("raw", "adj"):
        for mu_mode in ("shadow", "enforce"):
            BKS[f"{basis}|{mu_mode}|W4|0.0038"] = book(basis, mu_mode, C.W4, C.COST_RT_JUDGE)
            BKS[f"{basis}|{mu_mode}|full|0.0038"] = book(basis, mu_mode, (FULL_START, FULL_END), C.COST_RT_JUDGE,
                                                        seeds=(0,))
    for c in C.COST_RT_SENS:
        BKS[f"raw|shadow|W4|{c}"] = book("raw", "shadow", C.W4, c, seeds=(0,))
    res["books"] = BKS
    for k, v in BKS.items():
        print(f"[etf] book {k}: cagr {v['cagr_median']:+.4f} mdd {v['mdd_median']:+.4f} fills/y "
              f"{v['fills_per_year_median']:.1f} unaff {v['unaffordable_ratio_median']} recon {v['recon_max_abs']:.2e}",
              flush=True)
    jb = BKS["raw|shadow|W4|0.0038"]
    res["P3"] = J.p3(jb)
    res["P4"] = J.p4(jb)
    # 069500 보유 대비(보고 ④)
    k = st.bars[MU.SOURCE_TICKER]
    kc = pd.Series(k["c"], index=cal[k["di"]])

    def bh(win):
        s = kc[(kc.index >= pd.Timestamp(win[0])) & (kc.index <= pd.Timestamp(win[1]))].to_numpy(float)
        return {"cagr": float((s[-1] / s[0]) ** (252.0 / len(s)) - 1), "mdd": float((s / np.maximum.accumulate(s) - 1).min())}
    res["report_bh_069500"] = {"W4": bh(C.W4), "full": bh((FULL_START, FULL_END))}
    res["K3_db_tail_report"] = k3_db_tail(cls)
    res["elapsed_s"] = time.time() - t0
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("[etf] done", out_path, f"{res['elapsed_s']:.0f}s")


if __name__ == "__main__":
    main()
