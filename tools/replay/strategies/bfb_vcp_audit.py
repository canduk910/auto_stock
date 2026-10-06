#!/usr/bin/env python3
"""운용 전략 전수 점검 단계 6 — vcp_breakout(S3) · bull_flag_breakout(S4) 판정 실행.

정본 = ``_workspace/analysis/strategy_audit_20261005/prereg.frozen.md``(sha 2d7e7b42) §1 · §3.3 · §3.4 +
``prereg.md`` 끝 사후 발견. 사용자 결정(10-05): D-8 현 설정 시작일 = rules 판(VCP 09-28 · BFB 09-30) ·
C7 = 단독 풀 4,707,820원.

순서(§1.5): K1(엔진 상수 ↔ 추출본 DB 값) → P6 관문 → P1·P2·P5 → P3·P4 → L1 → 보고판.
판정판 = 장중 거래량 조건 없음(룩어헤드 없음) · color 경로 · 비용 0.38% · 시가 > 추격 상한이면 진입 없음.

실행: python3 tools/replay/strategies/bfb_vcp_audit.py vcp|bfb
산출: ``_workspace/analysis/strategy_audit_20261005/{vcp,bfb}/results.json`` + ``trades_w5y.csv.gz``
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import date

for _k in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.setdefault(_k, "audit-dummy")          # 단계 1 R3 — import 용 더미(값은 쓰이지 않는다)

import numpy as np
import pandas as pd

_TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from replay.audit import book as BK  # noqa: E402
from replay.audit import config as C  # noqa: E402
from replay.audit import judge as J  # noqa: E402
from replay.audit import live as LV  # noqa: E402
from replay.audit import market_unit as MU  # noqa: E402
from replay.audit import panel as PN  # noqa: E402
from replay.audit.sizing import OpSizer  # noqa: E402
from replay.strategies import bfb_vcp_engine as EN  # noqa: E402

OUT_ROOT = os.path.join(C.REPO, "_workspace/analysis/strategy_audit_20261005")
LIVE_TRIPS = os.path.join(C.SCRATCH, "live_trips.json")
RULES_START = {"vcp": "2026-09-28", "bfb": "2026-09-30"}       # 사용자 결정(10-05) — rules 판
SID = {"vcp": "vcp_breakout", "bfb": "bull_flag_breakout"}
PROV_CUTOFF = "2026-09-28"
SLIPS = (0.01, 0.02, 0.03)          # 보고판 — 체결 지연(돌파선 위 체결) 격자


# ── 데이터 ─────────────────────────────────────────────────────────────────────

def _krx_tick(px: float) -> float:
    for lim, t in ((2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500)):
        if px < lim:
            return t
    return 1000


def db_frame_with_flags(ext: dict) -> pd.DataFrame:
    """DB 일봉(H) — ETF류 제외 · 잠정 종가 의심 행 표시(D-6, 평균회귀 ``provisional_close_flags`` 와 같은 식)."""
    cols, rows = ext["daily"]
    df = pd.DataFrame(rows, columns=cols)
    df["bas_dd"] = pd.to_datetime(df["bas_dd"].str[:10])
    df = df[(df.bas_dd >= pd.Timestamp(C.H1Y[0])) & (df.bas_dd <= pd.Timestamp(C.H1Y[1]))].copy()
    df = df.rename(columns={"open_price": "open", "high_price": "high", "low_price": "low", "close_price": "close"})
    for k in ("open", "high", "low", "close", "volume", "trade_value", "change_rate"):
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df = df.sort_values(["ticker", "bas_dd"]).reset_index(drop=True)
    nxt_c = df.groupby("ticker")["close"].shift(-1)
    nxt_chg = df.groupby("ticker")["change_rate"].shift(-1)
    implied = nxt_c / (1.0 + nxt_chg / 100.0)
    tick = df["close"].fillna(1000).map(_krx_tick)
    tol = np.maximum(tick, implied.abs() * 5e-7 + nxt_c * 5e-5 / 100 * 100 + 1e-9)
    prov = (df.bas_dd < pd.Timestamp(PROV_CUTOFF)) & implied.notna() & df["close"].notna() & \
        ((df["close"] - implied).abs() > tol)
    df["prov"] = prov.to_numpy()
    return df


def load(kind: str):
    t0 = time.time()
    PN.check_archive(C.STOCK_ARCHIVE, C.STOCK_PARQUET_SHA)
    ext_sha = PN.sha256(C.DB_EXTRACT)
    ext = PN.load_db_extract()
    arch = PN.load_archive(C.STOCK_ARCHIVE, end=C.W5Y[1])
    arch = arch[arch.ticker.str.match(r"^\d{6}$") & arch.market.isin(["KOSPI", "KOSDAQ"])].copy()
    arch["prov"] = False
    mcols, mrows = ext["master"]
    master = {r[0]: dict(zip(mcols, r)) for r in mrows}
    db = db_frame_with_flags(ext)
    etf_like = {t for t, m in master.items()
                if str(m.get("scty_grp_id_cd") or "").strip().upper() in ("EF", "EN", "FE")}
    db = db[db.ticker.str.match(r"^\d{6}$") & ~db.ticker.isin(etf_like) & db.ticker.isin(set(master))]
    st = PN.build_store(arch, db=db, nontrade="flag", junction_rescale=True, extra_cols=("prov",))
    # 시장 유닛 — 069500: ETF 보관소(~09-23) + DB(09-24~)
    etf = PN.load_archive(C.ETF_ARCHIVE, columns=["ticker", "bas_dd", "close_adj"])
    k = etf[etf.ticker == MU.SOURCE_TICKER].sort_values("bas_dd")
    dcols, drows = ext["daily"]
    ix = {c: i for i, c in enumerate(dcols)}
    extra = sorted((pd.Timestamp(r[ix["bas_dd"]][:10]), float(r[ix["close_price"]])) for r in drows
                   if r[ix["ticker"]] == MU.SOURCE_TICKER and pd.Timestamp(r[ix["bas_dd"]][:10]) > k.bas_dd.max())
    kd = pd.DatetimeIndex(list(k.bas_dd) + [d for d, _ in extra])
    kc = np.r_[k.close_adj.to_numpy(float), [c for _, c in extra]]
    m = MU.m_for_days(st.cal, kd, kc)
    bench = pd.Series(kc, index=kd)
    print(f"[{kind}] store {st.meta} m-days {np.isfinite(m).sum()} {time.time()-t0:.0f}s", flush=True)
    return st, m, master, ext, ext_sha, bench


def universes(st, master: dict, p: dict) -> "tuple[dict, dict]":
    """신호 봉 기준 유니버스 — ② 그날 시총(판정) · ① 오늘 시총(보고). 둘 다 거래대금·가격 필터 같음."""
    asof, today = {}, {}
    lo, hi = EN.PRICE_FILTER
    for t, b in st.bars.items():
        mc = b["mktcap"].astype(float).copy()
        db = b["src"] == 1
        hts = master.get(t, {}).get("hts_avls_eok")
        if db.any():
            if hts:
                last = b["c_raw"][db][-1]
                mc[db] = float(hts) * 1e8 * b["c_raw"][db] / last if last > 0 else np.nan
            else:
                mc[db] = np.nan
        base = (b["tv"] >= p["min_trade_amount"]) & (b["c_raw"] >= lo) & (b["c_raw"] <= hi) & ~b["notrade"]
        with np.errstate(invalid="ignore"):
            asof[t] = base & np.nan_to_num(mc >= p["min_market_cap"]).astype(bool)
        today[t] = base & bool(hts and float(hts) * 1e8 >= p["min_market_cap"])
    return asof, today


# ── 판정 재료 ───────────────────────────────────────────────────────────────────

def trade_rows(pop, cal, cost_rt):
    out = []
    for ps in pop:
        out.append(dict(t=ps.s.ticker, d=str(cal[ps.s.gd].date()), x=(str(cal[ps.exit_gd].date())
                                                                       if ps.exit_gd is not None else ""),
                        E=ps.E, X=ps.exit_px, r=EN.net_ret(ps, cost_rt), why=ps.exit_reason, m=ps.s.m,
                        entry=ps.s.entry, vol_ok=ps.s.vol_ok, hold=(ps.exit_gd - ps.s.gd) if ps.exit_gd else None,
                        gd=ps.s.gd))
    return out


def p1_of(rows):
    if not rows:
        return {"n": 0, "label": "판정 불가"}
    r = J.p1([x["r"] for x in rows], [x["t"] for x in rows], [x["d"] for x in rows])
    r["median"] = float(np.median([x["r"] for x in rows]))
    r["win"] = float(np.mean([x["r"] > 0 for x in rows]))
    return r


def simple(rows):
    if not rows:
        return {"n": 0}
    v = np.array([x["r"] for x in rows])
    srt = np.sort(v)
    k = max(1, int(round(len(v) * 0.01)))
    return {"n": len(v), "mean": float(v.mean()), "median": float(np.median(v)), "win": float((v > 0).mean()),
            "mean_ex_top1pct": float(srt[:-k].mean()) if len(v) > k else float("nan"),
            "sum_top1pct_share": float(srt[-k:].sum() / v.sum()) if v.sum() != 0 else float("nan")}


def by_year(rows):
    g = defaultdict(list)
    for x in rows:
        g[x["d"][:4]].append(x)
    return {y: simple(v) for y, v in sorted(g.items())}


def exit_mix(rows):
    c = Counter(x["why"] for x in rows)
    n = sum(c.values())
    out = {k: {"n": v, "share": v / n, "mean": float(np.mean([x["r"] for x in rows if x["why"] == k]))}
           for k, v in c.most_common()}
    out["_hold_median"] = float(np.median([x["hold"] for x in rows if x["hold"] is not None])) if rows else None
    return out


def er_series(closes: np.ndarray, n: int = 20) -> np.ndarray:
    out = np.full(len(closes), np.nan)
    for t in range(n, len(closes)):
        seg = closes[t - n: t + 1]
        den = float(np.sum(np.abs(np.diff(seg))))
        if den > 0:
            out[t] = abs(float(seg[-1] - seg[0])) / den
    return out


def regime_table(rows, cal, bench: pd.Series):
    """시장 유닛 4칸 × ER 삼분위(069500, 신호 봉 = 진입 전날까지, 경계 = W5y 앞 60%) — 보고만."""
    er = er_series(bench.to_numpy(float))
    er_s = pd.Series(er, index=bench.index)
    w = er_s[(er_s.index >= pd.Timestamp(C.W5Y[0])) & (er_s.index <= pd.Timestamp(C.W5Y[1]))]
    cut = int(len(w) * 0.6)
    v = w.to_numpy()[:cut]
    v = v[np.isfinite(v)]
    lo, hi = float(np.quantile(v, 1 / 3)), float(np.quantile(v, 2 / 3))
    pos = bench.index.searchsorted(cal, side="left") - 1          # 진입일 D 보다 앞선 마지막 봉
    out = defaultdict(list)
    for x in rows:
        p = pos[x["gd"]]
        e = er[p] if p >= 0 else np.nan
        b = -1 if not np.isfinite(e) else (0 if e <= lo else (1 if e <= hi else 2))
        out[(x["m"], b)].append(x["r"])
    tab = {f"mu={k[0]}|er={k[1]}": {"n": len(v), "mean": float(np.mean(v))} for k, v in sorted(out.items())}
    return {"er_bounds_front60": [lo, hi], "cells": tab}


def bench_w4(bench: pd.Series):
    s = bench[(bench.index >= pd.Timestamp(C.W4[0])) & (bench.index <= pd.Timestamp(C.W4[1]))].to_numpy(float)
    eq = s / s[0]
    yrs = len(s) / 252.0
    return {"cagr": float(eq[-1] ** (1 / yrs) - 1), "mdd": float((eq / np.maximum.accumulate(eq) - 1).min()),
            "note": "069500(KODEX 200) 수정 종가 보유 — 코스피 근사 지수 대신(동결본 §1.1 시장 유닛과 같은 원천)"}


def random_control(pop_rows, st, feats, asof, kind, p, cal, end_gd, *, reps: int = 5):
    """③ 무작위 진입 대조군 — 같은 날짜 분포 · 같은 유니버스에서 종목만 무작위, 그날 시가 진입, 청산·쿨다운 없음.
    구조선(base_low·flag_low·측정 이동)은 무작위 종목에 없으므로 둘 다 구조선 없이 잰다(짝 비교)."""
    by_gd = defaultdict(list)
    tick_idx = {}
    for t, b in st.bars.items():
        f = feats[t]
        ok = asof[t][:-1] & (f["atr"][:-1] > 0)
        for i in np.nonzero(ok)[0]:
            D = i + 1
            if b["di"][D] != b["di"][i] + 1 or b["notrade"][D] or not (b["o"][D] > 0):
                continue
            by_gd[int(b["di"][D])].append((t, D))
        tick_idx[t] = True
    rng = np.random.default_rng(C.BOOT_SEED)
    means = []
    for _ in range(reps):
        vals = []
        for x in pop_rows:
            pool = by_gd.get(x["gd"])
            if not pool:
                continue
            t, D = pool[int(rng.integers(len(pool)))]
            b = st.bars[t]
            f = feats[t]
            O = float(b["o"][D])
            s = EN.Sig(t, D, int(b["di"][D]), O, O * float(b["raw"][D]), float(f["atr"][D - 1]), O, float("nan"),
                       float("nan"), x["m"], True, "gap")
            ps = EN.run_path(s, b, f, end_gd, kind=kind, p=p, cal=cal, mode="color", struct=False)
            vals.append(EN.net_ret(ps, C.COST_RT_JUDGE))
        means.append(float(np.mean(vals)))
    return {"reps": reps, "n_per_rep": len(pop_rows), "mean_of_means": float(np.mean(means)), "means": means}


# ── 계좌(P3·P4) ────────────────────────────────────────────────────────────────

class _CooldownSignals:
    """``run_book`` 이 날마다 ``.get(gd)`` 로 읽는 신호 — 그 계좌의 청산 기록으로 재진입 쿨다운을 건다."""

    def __init__(self, sbg: dict, cd: int):
        self.sbg, self.cd, self.last_exit = sbg, cd, {}
        self.blocked = 0

    def note_exit(self, ticker, gd):
        self.last_exit[ticker] = gd

    def get(self, gd, default=None):
        out = []
        for s in self.sbg.get(gd, default or []):
            le = self.last_exit.get(s.ticker)
            if le is not None and gd <= le + self.cd:
                self.blocked += 1
                continue
            out.append(s)
        return out


def run_books(sigs, st, feats, kind, p, cls, win, *, mode="color", cost_rt=C.COST_RT_JUDGE):
    sid = SID[kind]
    op = OpSizer(cls, sid, dict(p), atr_keys=("atr14",))
    sbg = defaultdict(list)
    for s in sigs:
        sbg[s.gd].append(s)
    runs, liq = [], []
    for seed in C.BOOK_SEEDS:
        cs = _CooldownSignals(sbg, int(p["reentry_cooldown_days"]))

        def size_fn(s, B, used):
            P = int(round(s.E_raw))
            if s.m <= 0:
                return 0, "mu"
            N_raw = s.N * (s.E_raw / s.E)
            if op.blocks_entry(P, N_raw, budget=int(B), used=int(used), m=s.m, ticker=s.ticker):
                return 0, "mu"
            q = op.qty(P, N_raw, budget=int(B), used=int(used), m=s.m, ticker=s.ticker)
            if q > 0:
                b = st.bars[s.ticker]
                tvp = b["tv"][s.ti - 1] if s.ti >= 1 else np.nan
                if seed == 0 and tvp > 0:
                    liq.append(q * P / tvp)
                return q, "ok"
            return 0, ("funds" if int(B) - int(used) < P else "design")

        def open_pos(s, q, _cs=cs):
            return EN.BPos(s, st.bars[s.ticker], feats[s.ticker], q, kind=kind, p=p, cal=st.cal, mode=mode,
                           on_exit=_cs.note_exit)
        r = BK.run_book(cs, open_pos, size_fn, st.cal, win[0], win[1], seed, start_equity=float(C.BUDGET_C7),
                        cost_side=cost_rt / 2, max_pos=int(p["max_positions"]), daily_cap=None)
        r["cooldown_blocked"] = cs.blocked
        runs.append(r)
    sm = BK.book_summary(runs, float(C.BUDGET_C7))
    sm["cooldown_blocked_seed0"] = runs[0]["cooldown_blocked"]
    lq = np.array(liq)
    sm["lot_over_1pct_of_prev_day_tv_share_seed0"] = float((lq > 0.01).mean()) if len(lq) else float("nan")
    tr0 = runs[0]["trades"]
    sm["seed0_exit_mix"] = dict(Counter(ps.exit_reason for ps in tr0))
    sm["seed0_trade_mean_net"] = float(np.mean([ps.exit_px / ps.E - 1 - cost_rt for ps in tr0
                                                if ps.exit_reason != "OPEN"])) if tr0 else float("nan")
    return sm


# ── 실거래(P6 · L1) ────────────────────────────────────────────────────────────

def live_buys(kind: str):
    d = json.load(open(LIVE_TRIPS))
    sid = SID[kind]
    out = []
    for t in d["trips"]:
        if t["strategy"] == sid:
            for bo in t["buy_orders"]:
                out.append((t["ticker"], bo[0], "closed"))
    for o in d["open"]:
        if o["strategy"] == sid:
            out.append((o["ticker"], str(LV.kst_date(o["buy_ts"])), "open"))
    trips = [t for t in d["trips"] if t["strategy"] == sid]
    return sorted(set(out)), trips, d["extract_sha256"] if "extract_sha256" in d else None


def p6_block(kind, sigs_all, feats, st, start):
    buys, trips, _ = live_buys(kind)
    sig_set = {(s.ticker, str(st.cal[s.gd].date())) for s in sigs_all}
    cand_set = set()
    gd_of = {str(d.date()): i for i, d in enumerate(st.cal)}
    detail = []
    for t, d, state in buys:
        b = st.bars.get(t)
        gd = gd_of.get(d)
        info = {"ticker": t, "date": d, "state": state, "replay_signal": (t, d) in sig_set}
        if b is not None and gd is not None:
            k = int(np.searchsorted(b["di"], gd))
            if k < len(b["di"]) and b["di"][k] == gd and k >= 1:
                f = feats[t]
                info.update(cand_prev_bar=bool(f["cand"][k - 1]), stage_prev_bar=int(f["stage"][k - 1]),
                            line=float(f["line"][k - 1]) if f["cand"][k - 1] else None,
                            bar=[float(b["o"][k]), float(b["h"][k]), float(b["l"][k]), float(b["c"][k])])
                if f["cand"][k - 1]:
                    cand_set.add((t, d))
        detail.append(info)
    rules = [x for x in detail if x["date"] >= start]
    res = J.p6([(x["ticker"], x["date"]) for x in rules], sig_set)
    res["hits_even_if_small"] = sum(1 for x in rules if x["replay_signal"])
    allr = J.p6([(x["ticker"], x["date"]) for x in detail], sig_set)
    return {"rules_start": start, "rules": res, "all_live_reference": dict(allr, n_total=len(detail)),
            "detail": detail}


def l1_block(kind, start):
    _, trips, _ = live_buys(kind)
    judged = [t for t in trips if t["buy_date"] >= start and t["in_window"] and not t["ca_flag"]]
    allw = [t for t in trips if t["in_window"] and not t["ca_flag"]]
    res = J.l1([t["net"] for t in judged], [t["buy_date"] for t in judged])
    ref = {"n": len(allw)}
    if allw:
        v = np.array([t["net"] for t in allw])
        w = np.array([t["buy_amt"] for t in allw])
        ref.update(mean=float(v.mean()), median=float(np.median(v)), win=float((v > 0).mean()),
                   amt_weighted=float((v * w).sum() / w.sum()),
                   one_share_share=float(np.mean([t["one_share"] for t in allw])),
                   first=allw[0]["buy_date"], last=allw[-1]["sell_date"])
    return {"rules_window": res, "all_trips_reference_pre_rules": ref}


def live_vs_replay(kind, sigs, st, feats, p, end_gd):
    """실거래 왕복 ↔ 같은 날 같은 종목 재현 신호의 경로(현 파라미터 · color · 1주) — 보고만."""
    d = json.load(open(LIVE_TRIPS))
    sid = SID[kind]
    by = {(s.ticker, str(st.cal[s.gd].date())): s for s in sigs}
    out = []
    for t in [x for x in d["trips"] if x["strategy"] == sid]:
        s = by.get((t["ticker"], t["buy_date"]))
        row = {"ticker": t["ticker"], "buy": t["buy_date"], "sell": t["sell_date"], "live_px": t["buy_px"],
               "live_exit_px": t["sell_px"], "live_net": t["net"], "replay": None}
        if s is not None:
            ps = EN.run_path(s, st.bars[s.ticker], feats[s.ticker], end_gd, kind=kind, p=p, cal=st.cal)
            row["replay"] = {"E_raw": s.E_raw, "entry": s.entry, "exit": (str(st.cal[ps.exit_gd].date())
                                                                         if ps.exit_gd is not None else None),
                             "why": ps.exit_reason, "net": EN.net_ret(ps, C.COST_RT_JUDGE)}
        out.append(row)
    for o in [x for x in d["open"] if x["strategy"] == sid]:
        dd = str(LV.kst_date(o["buy_ts"]))
        s = by.get((o["ticker"], dd))
        row = {"ticker": o["ticker"], "buy": dd, "sell": None, "live_open": True, "replay": None}
        if s is not None:
            ps = EN.run_path(s, st.bars[s.ticker], feats[s.ticker], end_gd, kind=kind, p=p, cal=st.cal)
            row["replay"] = {"E_raw": s.E_raw, "entry": s.entry, "exit": (str(st.cal[ps.exit_gd].date())
                                                                         if ps.exit_gd is not None else None),
                             "why": ps.exit_reason, "net": EN.net_ret(ps, C.COST_RT_JUDGE)}
        out.append(row)
    m = [r for r in out if r["replay"] is not None and r.get("live_net") is not None]
    summ = {"n_matched_closed": len(m),
            "live_mean": float(np.mean([r["live_net"] for r in m])) if m else None,
            "replay_mean": float(np.mean([r["replay"]["net"] for r in m])) if m else None}
    return {"summary": summ, "rows": out}


# ── K1 ────────────────────────────────────────────────────────────────────────

def k1_block(kind, ext, cls):
    cols, rows = ext["strategy_config"]
    d = {r[0]: dict(zip(cols, r)) for r in rows}
    prm = d[SID[kind]]["params"]
    prm = prm if isinstance(prm, dict) else json.loads(prm)
    eng = EN.VCP_DB if kind == "vcp" else EN.BFB_DB
    code = cls.DEFAULT_PARAMS
    rows_out = []
    for k in sorted(set(prm) | set(eng)):
        rows_out.append({"key": k, "db": prm.get(k, "<absent>"), "code_default": code.get(k, "<absent>"),
                         "engine": eng.get(k, "<not used>"),
                         "engine_eq_db": (eng.get(k) == prm.get(k)) if k in eng else None})
    return {"rows": rows_out, "engine_mismatch": [r["key"] for r in rows_out if r["engine_eq_db"] is False],
            "db_ne_code": [r["key"] for r in rows_out if r["db"] != r["code_default"]]}


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main(kind: str):
    t0 = time.time()
    if kind == "vcp":
        from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy as cls
        p, featf = EN.VCP_DB, EN.vcp_features
    else:
        from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy as cls
        p, featf = EN.BFB_DB, EN.bfb_features
    out = {"strategy": SID[kind], "prereg_sha256": open(os.path.join(OUT_ROOT, "prereg.md.sha256")).read().split()[0]}
    st, m, master, ext, ext_sha, bench = load(kind)
    out["inputs"] = {"db_extract_sha256": ext_sha, "store": st.meta,
                     "engine_sha256": PN.sha256(os.path.join(os.path.dirname(__file__), "bfb_vcp_engine.py")),
                     "runner_sha256": PN.sha256(__file__)}
    out["K1"] = k1_block(kind, ext, cls)
    asof, today = universes(st, master, p)
    feats = {}
    for n_done, (t, b) in enumerate(st.bars.items()):
        feats[t] = featf(b, p)
    print(f"[{kind}] features {time.time()-t0:.0f}s", flush=True)
    stage_ct = Counter()
    for t, f in feats.items():
        u = asof[t]
        for sv in range(1, 6):
            stage_ct[sv] += int(((f["stage"] >= sv) & u).sum())
    out["funnel_ticker_days_in_universe"] = dict(stage_ct)

    sigs = EN.build_signals(st.bars, feats, m, p, asof)
    sigs_latch = EN.build_signals(st.bars, feats, m, p, asof, latch=True)
    sigs_today = EN.build_signals(st.bars, feats, m, p, today)
    print(f"[{kind}] signals {len(sigs)} latch {len(sigs_latch)} today {len(sigs_today)} {time.time()-t0:.0f}s",
          flush=True)
    cal = st.cal
    gw = lambda w: (int(cal.searchsorted(pd.Timestamp(w[0]))),  # noqa: E731
                    int(cal.searchsorted(pd.Timestamp(w[1]), side="right")) - 1)
    g5, gH, g4 = gw(C.W5Y), gw(C.H1Y), gw(C.W4)

    # P6
    out["P6"] = p6_block(kind, sigs, feats, st, RULES_START[kind])
    print(f"[{kind}] P6 {out['P6']['rules']} ref {out['P6']['all_live_reference']}", flush=True)

    def pop(ss, w, **kw):
        return EN.population(ss, st.bars, feats, w[0], w[1], kind=kind, p=p, cal=cal, **kw)

    P = {}
    P["w5y"] = trade_rows(pop(sigs, g5), cal, C.COST_RT_JUDGE)
    P["w5y_adverse"] = trade_rows(pop(sigs, g5, mode="adverse"), cal, C.COST_RT_JUDGE)
    for md in ("adverse_lit", "adv_entry", "adv_later"):
        P[f"w5y_{md}"] = trade_rows(pop(sigs, g5, mode=md), cal, C.COST_RT_JUDGE)
    P["h"] = trade_rows(pop(sigs, gH), cal, C.COST_RT_JUDGE)
    P["h_adverse"] = trade_rows(pop(sigs, gH, mode="adverse"), cal, C.COST_RT_JUDGE)
    P["w5y_vol"] = trade_rows(pop(sigs, g5, vol_filter=True), cal, C.COST_RT_JUDGE)
    P["h_vol"] = trade_rows(pop(sigs, gH, vol_filter=True), cal, C.COST_RT_JUDGE)
    P["w5y_latch"] = trade_rows(pop(sigs_latch, g5), cal, C.COST_RT_JUDGE)
    P["w5y_today_universe"] = trade_rows(pop(sigs_today, g5), cal, C.COST_RT_JUDGE)
    for sl in SLIPS:
        ss = EN.build_signals(st.bars, feats, m, p, asof, slip=sl)
        P[f"w5y_slip{sl}"] = trade_rows(pop(ss, g5), cal, C.COST_RT_JUDGE)
        P[f"h_slip{sl}"] = trade_rows(pop(ss, gH), cal, C.COST_RT_JUDGE)
    P["w5y_nostruct"] = trade_rows(pop(sigs, g5, struct=False), cal, C.COST_RT_JUDGE)
    P["w4"] = [x for x in P["w5y"] if x["gd"] >= g4[0]]
    # D-6 잠정 종가 halt 판(H)
    prov_bars = {}
    for t, b in st.bars.items():
        if b["prov"].any():
            nb = dict(b)
            nb["notrade"] = b["notrade"] | b["prov"].astype(bool)
            prov_bars[t] = nb
    bars_h = dict(st.bars)
    bars_h.update(prov_bars)
    asof_h = {t: (asof[t] & ~bars_h[t]["notrade"]) for t in st.bars}
    sigs_h = EN.build_signals(bars_h, feats, m, p, asof_h)
    P["h_prov_halt"] = trade_rows(EN.population(sigs_h, bars_h, feats, gH[0], gH[1], kind=kind, p=p, cal=cal),
                                  cal, C.COST_RT_JUDGE)
    out["prov_rows_flagged"] = int(sum(int(b["prov"].sum()) for b in st.bars.values()))
    touch = 0
    for x in P["h"]:
        b = st.bars[x["t"]]
        k0 = int(np.searchsorted(b["di"], x["gd"]))
        k1 = int(np.searchsorted(b["di"], x["gd"] + (x["hold"] or 0)))
        touch += int(b["prov"][max(0, k0 - 1):k1 + 1].astype(bool).any())
    out["prov_trades_touched_h"] = touch
    print(f"[{kind}] populations {[(k, len(v)) for k, v in P.items()]} {time.time()-t0:.0f}s", flush=True)

    # P1 · P2 · P5
    p1 = p1_of(P["w5y"])
    p1["cost_sens"] = {}
    for cst in C.COST_RT_SENS:
        rr = [dict(x, r=x["r"] + C.COST_RT_JUDGE - cst) for x in P["w5y"]]
        p1["cost_sens"][f"{cst:.4f}"] = {k: v for k, v in p1_of(rr).items() if k in ("n", "mean", "lo90", "label")}
    out["P1"] = p1
    out["P2"] = J.p2([x["r"] for x in P["h"]], p1.get("mean", float("nan")))
    out["P2_prov_halt"] = J.p2([x["r"] for x in P["h_prov_halt"]], p1.get("mean", float("nan")))
    pa = p1_of(P["w5y_adverse"])
    out["P5"] = J.p5(p1.get("mean", float("nan")), pa.get("mean", float("nan")))
    out["P5"]["adverse_p1"] = {k: pa.get(k) for k in ("n", "mean", "lo90", "label")}
    print(f"[{kind}] P1 {out['P1']['mean']:.5f} lo {out['P1']['lo90']:.5f} P2 {out['P2']} P5 {out['P5']}", flush=True)

    # P3 · P4 (W4 계좌)
    out["book_W4"] = run_books(sigs, st, feats, kind, p, cls, C.W4)
    out["P3"] = J.p3(out["book_W4"])
    out["P4"] = J.p4(out["book_W4"])
    print(f"[{kind}] P3 {out['P3']} P4 {out['P4']} {time.time()-t0:.0f}s", flush=True)
    bk_adv = run_books(sigs, st, feats, kind, p, cls, C.W4, mode="adverse")
    out["book_W4_adverse"] = {k: bk_adv[k] for k in ("cagr_median", "mdd_median", "fills_per_year_median",
                                                       "trades_median")}
    for sl in (0.01, 0.02):
        bs = run_books(EN.build_signals(st.bars, feats, m, p, asof, slip=sl), st, feats, kind, p, cls, C.W4)
        out[f"book_W4_slip{sl}"] = {k: bs[k] for k in ("cagr_median", "mdd_median", "fills_per_year_median",
                                                       "trades_median")}
    out["book_H_report"] = {k: v for k, v in run_books(sigs, st, feats, kind, p, cls, C.H1Y).items()
                            if k in ("cagr_median", "mdd_median", "fills_per_year_median", "trades_median",
                                     "unaffordable_ratio_median", "recon_max_abs")}

    # L1
    out["L1"] = l1_block(kind, RULES_START[kind])

    # 보고판
    rep = {}
    for k in ("w5y_adverse_lit", "w5y_adv_entry", "w5y_adv_later"):
        rep[k] = simple(P[k])
    for sl in SLIPS:
        rep[f"w5y_slip{sl}_p1"] = {k: v for k, v in p1_of(P[f"w5y_slip{sl}"]).items()
                                   if k in ("n", "mean", "lo90", "label")}
        rep[f"h_slip{sl}"] = simple(P[f"h_slip{sl}"])
    rep["live_vs_replay"] = live_vs_replay(kind, sigs, st, feats, p, gH[1])
    for k in ("w5y", "w5y_adverse", "w4", "h", "h_adverse", "w5y_vol", "h_vol", "w5y_latch", "w5y_today_universe",
              "w5y_nostruct", "h_prov_halt"):
        rep[k] = simple(P[k])
    rep["w5y_vol_p1"] = {k: v for k, v in p1_of(P["w5y_vol"]).items() if k in ("n", "mean", "lo90", "label")}
    rep["w5y_latch_p1"] = {k: v for k, v in p1_of(P["w5y_latch"]).items() if k in ("n", "mean", "lo90", "label")}
    rep["by_year"] = by_year(P["w5y"]) | {"H": simple(P["h"])}
    rep["exit_mix_w5y"] = exit_mix(P["w5y"])
    rep["entry_mix_w5y"] = dict(Counter(x["entry"] for x in P["w5y"]))
    rep["vol_ok_share_w5y"] = float(np.mean([x["vol_ok"] for x in P["w5y"]])) if P["w5y"] else None
    rep["regime"] = regime_table(P["w5y"], cal, bench)
    rep["bench_069500_W4"] = bench_w4(bench)
    rep["random_control"] = random_control(P["w5y"], st, feats, asof, kind, p, cal, g5[1])
    rep["random_control"]["real_nostruct_mean"] = rep["w5y_nostruct"]["mean"]
    if kind == "vcp":
        eff_short = [x for x in P["w5y"] if feats[x["t"]]["eff"][
            int(np.searchsorted(st.bars[x["t"]]["di"], x["gd"])) - 1] < 200]
        keep = {(x["t"], x["d"]) for x in eff_short}
        rep["eff_long_lt200"] = {"n": len(eff_short),
                                 "w5y_excluding": simple([x for x in P["w5y"] if (x["t"], x["d"]) not in keep])}
    out["report"] = rep
    out["elapsed_s"] = time.time() - t0
    od = os.path.join(OUT_ROOT, kind)
    os.makedirs(od, exist_ok=True)
    with open(os.path.join(od, "results.json"), "w") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    with gzip.open(os.path.join(od, "trades_w5y.csv.gz"), "wt") as fh:
        pd.DataFrame(P["w5y"]).to_csv(fh, index=False)
    with gzip.open(os.path.join(od, "trades_h.csv.gz"), "wt") as fh:
        pd.DataFrame(P["h"]).to_csv(fh, index=False)
    print(f"[{kind}] done {out['elapsed_s']:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
