"""kojiro 30년 재검증(2026-10-06) — 5년판 전략 층(``kojiro.py``·``kojiro_opt.py``) 위의 30년 데이터·시대 층.

사전 등록 = ``_workspace/analysis/strategy_30y_20261006/kojiro/prereg.frozen.md``. 규칙(신호·청산·사이징)은
5년판을 그대로 쓰고 여기서는 다음만 바꾼다.

- 로더: ``data/archive/krx_daily_long/unified``(1996~2026, 상장폐지 포함). 6자리 숫자 코드만 · 종가 ≤ 0 행 제외 ·
  가격제한폭 위반 표시 행(``meta/unified_jump_flags.csv``) 제외(``drop_flags``).
- 유니버스(시대 중립): 그날 횡단면 시총 백분위 > 1 − ``U_CAP`` ∧ 거래대금 백분위 > 1 − ``U_TV`` ∧ 원주가 전일 종가
  3,000~500,000. ``U_CAP``·``U_TV`` = 2025 년 「시총 ≥ 500억」·「거래대금 ≥ 10억」 비율의 거래일 평균(동결 전 계산).
- 비용: ``meta/regime_costs.csv`` 시기별 — 매수 = 그날 수수료, 매도 = 그날 수수료 + 거래세(``Cost``).
- 하한가 잠김: ``meta/regime_price_limit.csv`` 시장·날짜별 제한폭(``Y30Pos._locked``).
- 계좌: ``audit.book.run_book`` 과 같은 하루 순서, 비용만 날짜별(``run_book30``). 연 환산 = 달력 연수.
- 지표 속도: 5년판 ``_ewm_full``(파이썬 루프)을 같은 값의 pandas ``ewm(adjust=False)`` 로 바꾼다(``patch_fast_ewm``).
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd

from replay.audit import book as BK
from replay.audit import config as C
from replay.audit import panel as PN
from replay.strategies import kojiro as KJ
from replay.strategies import kojiro_opt as KO

ARCHIVE = os.path.join(C.MAIN_REPO, "data/archive/krx_daily_long")
UNIFIED = os.path.join(ARCHIVE, "unified")
U_CAP = 0.7582        # prereg §3 — 2025 「시총 ≥ 500억」 비율 평균
U_TV = 0.3329         # prereg §3 — 2025 「거래대금 ≥ 10억」 비율 평균
KOSDAQ_FIXED_LIMIT = 0.05   # 1996-07-01~11-24 정액제 근사
LOAD_COLS = PN.ARCH_COLS + ["no_trade"]

T_WIN = ("1997-01-02", "2012-12-28")
TA_WIN = ("1997-01-02", "2004-12-30")
TB_WIN = ("2005-01-03", "2012-12-28")
V_WIN = ("2013-01-02", "2020-12-30")
H_WIN = ("2021-01-04", "2026-10-02")
ERAS = {"1997-2001": ("1997-01-02", "2001-12-31"), "2002-2006": ("2002-01-02", "2006-12-31"),
        "2007-2011": ("2007-01-02", "2011-12-31"), "2012-2016": ("2012-01-02", "2016-12-31"),
        "2017-2021": ("2017-01-02", "2021-12-31"), "2022-2026": ("2022-01-03", "2026-10-02")}


# ── 지표 속도 ─────────────────────────────────────────────────────────────

def ewm_full_fast(x: np.ndarray, alpha: float, first: "np.ndarray | None" = None) -> np.ndarray:
    """``KJ._ewm_full`` 과 같은 값(acc₀ = first₀ 또는 x₀, accⱼ = (1−a)·accⱼ₋₁ + a·xⱼ). 입력에 NaN 이 없어야 한다."""
    v = np.asarray(x, dtype=float).copy()
    if len(v) == 0:
        return v
    if first is not None:
        v[0] = float(first[0])
    return pd.Series(v).ewm(alpha=alpha, adjust=False).mean().to_numpy()


def patch_fast_ewm() -> None:
    KJ._ewm_full = ewm_full_fast


# ── 데이터 ───────────────────────────────────────────────────────────────

def load_flags() -> pd.DataFrame:
    f = pd.read_csv(os.path.join(ARCHIVE, "meta/unified_jump_flags.csv"), dtype={"ticker": str})
    f["bas_dd"] = pd.to_datetime(f["bas_dd"])
    return f[["ticker", "bas_dd"]]


def add_pct(df: pd.DataFrame) -> pd.DataFrame:
    """그날 횡단면(그날 행이 있는 종목 전부) 백분위 — 순위 ÷ 종목 수(동순위 평균)."""
    g = df.groupby("bas_dd", sort=False)
    df["cap_pct"] = g["mktcap"].rank(pct=True, method="average").fillna(0.0).to_numpy()
    df["tv_pct"] = g["trade_value"].rank(pct=True, method="average").fillna(0.0).to_numpy()
    return df


def load_unified(y0: int = 1996, y1: int = 2026, *, drop_flags: bool = True) -> "tuple[pd.DataFrame, dict]":
    fs = [os.path.join(UNIFIED, f"krx_unified_{y}.parquet") for y in range(y0, y1 + 1)]
    import pyarrow as pa
    import pyarrow.parquet as pq
    dict_cols = ["ticker", "name", "market"]      # 문자열 1,500만 개 대신 사전 부호화(메모리)
    tabs = [pq.read_table(f, columns=LOAD_COLS, read_dictionary=dict_cols) for f in fs if os.path.exists(f)]
    df = pa.concat_tables(tabs).unify_dictionaries().to_pandas()
    del tabs
    df["bas_dd"] = pd.to_datetime(df["bas_dd"])
    meta = {"rows_raw": len(df)}
    df = df[df.ticker.str.fullmatch(r"\d{6}")]
    meta["rows_6digit"] = len(df)
    df = df[(df.close > 0) & df.close_adj.notna() & (df.close_adj > 0)].copy()
    meta["rows_close_pos"] = len(df)
    df["mktcap"] = df["mktcap"].fillna(0.0)
    df["trade_value"] = df["trade_value"].fillna(0.0)
    df = add_pct(df)
    fl = load_flags()
    keys = set(zip(fl.ticker, fl.bas_dd.values.astype("int64")))
    cand = df.ticker.isin(set(fl.ticker)).to_numpy()
    sub = df.loc[cand, ["ticker", "bas_dd"]]
    hit = np.zeros(len(df), dtype=bool)
    hit[np.nonzero(cand)[0]] = [k in keys for k in zip(sub.ticker, sub.bas_dd.values.astype("int64"))]
    meta["flag_rows_matched"] = int(hit.sum())
    df["flag"] = hit
    if drop_flags:
        df = df[~hit]
    meta["rows_used"] = len(df)
    return df, meta


def build(df: pd.DataFrame, cal: "pd.DatetimeIndex | None" = None, tickers: "set | None" = None) -> PN.Store:
    return PN.build_store(df, db=None, nontrade="flag", junction_rescale=False, cal=cal, tickers=tickers,
                          extra_cols=("cap_pct", "tv_pct"))


def mu_series() -> "tuple[pd.DatetimeIndex, np.ndarray]":
    s = pd.read_csv(os.path.join(ARCHIVE, "index/market_unit_series.csv"))
    s = s[s.close.notna()]
    return pd.DatetimeIndex(pd.to_datetime(s.date)), s.close.to_numpy(float)


# ── 시대 표 ──────────────────────────────────────────────────────────────

@dataclass
class Cost:
    """날짜(전역 달력)별 한쪽 수수료 ``fee`` · 매도 거래세 ``tax``."""

    fee: np.ndarray
    tax: np.ndarray
    name: str = "era"

    def buy(self, gd: int) -> float:
        return float(self.fee[gd])

    def sell(self, gd: int) -> float:
        return float(self.fee[gd] + self.tax[gd])

    def rt(self, g_in: int, g_out: "int | None") -> float:
        go = g_in if g_out is None else g_out
        return self.buy(g_in) + self.sell(go)


def era_cost(cal: pd.DatetimeIndex) -> Cost:
    t = pd.read_csv(os.path.join(ARCHIVE, "meta/regime_costs.csv"))
    fee = np.full(len(cal), np.nan)
    tax = np.full(len(cal), np.nan)
    for _, r in t.iterrows():
        a = pd.Timestamp(r["from"])
        b = pd.Timestamp(r["to"]) if isinstance(r["to"], str) and r["to"] else pd.Timestamp("2100-01-01")
        m = (cal >= a) & (cal <= b)
        fee[m] = float(r["fee_one_way_pct_assumed"]) / 100.0
        tax[m] = float(r["sell_tax_kospi_pct"]) / 100.0
    if np.isnan(fee).any():
        raise SystemExit("[kojiro_y30] 비용표가 덮지 못한 날이 있다")
    return Cost(fee, tax, "era")


def const_cost(cal: pd.DatetimeIndex, rt: float = C.COST_RT_JUDGE) -> Cost:
    return Cost(np.full(len(cal), rt / 2), np.zeros(len(cal)), f"const{rt}")


def limit_table(cal: pd.DatetimeIndex) -> np.ndarray:
    """LIM[시장(0=KOSPI·기타, 1=KOSDAQ), 날] = 가격제한폭(비율)."""
    t = pd.read_csv(os.path.join(ARCHIVE, "meta/regime_price_limit.csv"))
    lim = np.full((2, len(cal)), np.nan)
    for _, r in t.iterrows():
        a = pd.Timestamp(r["from"])
        b = pd.Timestamp(r["to"]) if isinstance(r["to"], str) and r["to"] else pd.Timestamp("2100-01-01")
        m = (cal >= a) & (cal <= b)
        v = KOSDAQ_FIXED_LIMIT if str(r["limit_pct"]) == "정액제" else float(r["limit_pct"]) / 100.0
        rows = {"KOSPI": (0,), "KOSDAQ": (1,), "ALL": (0, 1)}[r["market"]]
        for k in rows:
            lim[k, m] = v
    lim[1, np.isnan(lim[1])] = KOSDAQ_FIXED_LIMIT     # 1996-01~06 KOSDAQ 자료 없음 — 쓰이지 않는다
    lim[0, np.isnan(lim[0])] = 0.06
    return lim


def gd_range(cal: pd.DatetimeIndex, win) -> "tuple[int, int]":
    return (int(cal.searchsorted(pd.Timestamp(win[0]))),
            int(cal.searchsorted(pd.Timestamp(win[1]), side="right")) - 1)


def cal_years(cal: pd.DatetimeIndex, g0: int, g1: int) -> float:
    return max((cal[g1] - cal[g0]).days, 1) / 365.25


# ── 유니버스 ─────────────────────────────────────────────────────────────

def universe_era(b: dict, *, u_cap: float = U_CAP, u_tv: float = U_TV) -> np.ndarray:
    craw = b["c_raw"].astype(float)
    with np.errstate(invalid="ignore"):
        return ((b["cap_pct"].astype(float) > 1.0 - u_cap) & (b["tv_pct"].astype(float) > 1.0 - u_tv)
                & (craw >= KJ.PRICE_FILTER[0]) & (craw <= KJ.PRICE_FILTER[1]) & ~b["notrade"])


# ── 포지션 · 모집단 ────────────────────────────────────────────────────────

class Y30Pos(KO.OptPos):
    """5년판 ``OptPos`` + 시대별 하한가 잠김. ``LIM`` = ``limit_table`` (실행기가 넣는다)."""

    LIM: "np.ndarray | None" = None

    def _locked(self, ti: int) -> bool:
        if not self.locks or ti <= 0:
            return False
        b = self.b
        o, h, l, pc = float(b["o"][ti]), float(b["h"][ti]), float(b["l"][ti]), float(b["c"][ti - 1])
        if not (pc > 0 and h == l and o < pc):
            return False
        lim = 0.30 if self.LIM is None else float(self.LIM[1 if int(b["mkt"][ti]) == 1 else 0, int(b["di"][ti])])
        return o <= pc * (1.0 - lim) * 1.01


def run_path(sig, b, f, p, end_gd: int, mode: str = "color", time_n: "int | None" = None) -> Y30Pos:
    ps = Y30Pos(sig, b, f, 1, p, mode=mode, time_n=time_n)
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


class PathMemo(KO.PathMemo):
    def get(self, s, cfg, end_gd, slip, mode="color"):
        key = (s.ticker, s.ti, cfg, end_gd, slip, mode)
        ps = self.memo.get(key)
        if ps is None:
            ps = run_path(KO.slip_sig(s, slip), self.bars[s.ticker], self.feats[s.ticker], cfg.params(self.p),
                          end_gd, mode, cfg.time_n)
            self.memo[key] = ps
        return ps


def population(sigs, memo: PathMemo, cfg: KO.ExitCfg, g0: int, g1: int, slip: float, mode: str = "color"):
    return KO.population_memo(sigs, memo, cfg, g0, g1, slip, mode)


def net(ps, cost: Cost) -> float:
    return ps.exit_px / ps.E - 1.0 - cost.rt(ps.s.gd, ps.exit_gd)


# ── 계좌 ─────────────────────────────────────────────────────────────────

class Gates30(KJ.Gates):
    """5년판 게이트 그대로 — 보유 목록만 매번 정리한다(30년 누적 목록의 O(n²) 회피, 판정 같음)."""

    def size(self, s, B, used):
        self.opened = [x for x in self.opened if x.exit_reason is None or x.exit_gd == s.gd]
        return super().size(s, B, used)


def run_book30(signals_by_gd: dict, open_pos, size_fn, cal: pd.DatetimeIndex, start: str, end: str, seed: int, *,
               start_equity: float, cost: Cost, max_pos: int) -> dict:
    """``audit.book.run_book`` 과 같은 하루 순서. 비용만 날짜별(매수 = 수수료, 매도 = 수수료 + 거래세)."""
    rng = np.random.default_rng(seed)
    g0, g1 = gd_range(cal, (start, end))
    cash = float(start_equity)
    pos: dict = {}
    eq_prev = float(start_equity)
    equity, trades = [], []
    cnt = Counter()
    for gd in range(g0, g1 + 1):
        B = eq_prev
        sold_today = set()
        cs = cost.sell(gd)
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                continue
            if ps.open_phase(ti, gd):
                cash += ps.k * ps.exit_px * (1 - cs)
                trades.append(ps)
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
            cash -= q * s.E_raw * (1 + cost.buy(gd))
            pos[s.ticker] = ps
            cnt["fill"] += 1
        for t in list(pos):
            ps = pos[t]
            ti = ps.cur_ti(gd)
            if ti is None:
                if ps.data_ended(gd):
                    ps._exit(ps.last_px, "END", gd)
                    cash += ps.k * ps.exit_px * (1 - cs)
                    trades.append(ps)
                    del pos[t]
                continue
            if ps.intraday_phase(ti, gd, ti == ps.s.ti):
                cash += ps.k * ps.exit_px * (1 - cs)
                trades.append(ps)
                del pos[t]
        eq = cash + sum(x.value() for x in pos.values())
        equity.append(eq)
        eq_prev = eq
    for ps in pos.values():
        ps._exit(ps.last_px, "OPEN", None)
        trades.append(ps)
    eq = np.array(equity)
    return {"equity": eq, "trades": trades, "dates": cal[g0:g1 + 1], "counts": dict(cnt), "g": (g0, g1),
            "recon": reconcile30(eq, trades, start_equity, cost)}


def reconcile30(eq, trades, start_equity, cost: Cost) -> float:
    tot = 0.0
    for ps in trades:
        buy = ps.qty * ps.s.E_raw * (1 + cost.buy(ps.s.gd))
        if ps.exit_reason == "OPEN":
            tot += ps.k * ps.last_px - buy
        else:
            tot += ps.k * ps.exit_px * (1 - cost.sell(ps.exit_gd)) - buy
    return float(eq[-1] - (start_equity + tot)) if len(eq) else 0.0


def cagr_cal(eq: np.ndarray, start_equity: float, years: float) -> float:
    if len(eq) < 2 or years <= 0:
        return float("nan")
    return float((eq[-1] / start_equity) ** (1.0 / years) - 1)


def summary30(runs: "list[dict]", start_equity: float, cal: pd.DatetimeIndex) -> dict:
    g0, g1 = runs[0]["g"]
    yrs = cal_years(cal, g0, g1)
    cg = [cagr_cal(r["equity"], start_equity, yrs) for r in runs]
    md = [BK.mdd(r["equity"], start_equity) for r in runs]
    nt = [len(r["trades"]) for r in runs]
    fills = [r["counts"].get("fill", 0) for r in runs]
    unaff = []
    for r in runs:
        c = r["counts"]
        free = c.get("signal", 0) - c.get("slot_full", 0)
        unaff.append(c.get("zero_funds", 0) / free if free > 0 else float("nan"))
    return {"cagr_median": float(np.median(cg)), "cagr_min": float(np.min(cg)), "cagr_max": float(np.max(cg)),
            "mdd_median": float(np.median(md)), "trades_median": float(np.median(nt)),
            "fills_per_year_median": float(np.median(fills) / yrs),
            "unaffordable_ratio_median": float(np.nanmedian(unaff)) if any(u == u for u in unaff) else float("nan"),
            "recon_max_abs": float(max(abs(r["recon"]) for r in runs)), "years": yrs,
            "counts_seed0": runs[0]["counts"]}


# ── 기준선 ───────────────────────────────────────────────────────────────

def baselines(kd: pd.DatetimeIndex, kc: np.ndarray, win) -> dict:
    """단순 보유 · m 비례 보유(날 D 수익 × m(D), m(D) = D 앞 마지막 봉까지 판정, 판정 불가 = 1.0). 비용 없음."""
    from replay.audit import market_unit as MU
    mb = MU.m_at_bars(kc)
    a, b = pd.Timestamp(win[0]), pd.Timestamp(win[1])
    idx = np.nonzero((kd >= a) & (kd <= b))[0]
    if len(idx) < 2:
        return {}
    i0 = idx[0]
    r = kc[idx] / kc[idx - 1] - 1.0 if i0 > 0 else np.concatenate([[0.0], kc[idx[1:]] / kc[idx[:-1]] - 1.0])
    m = mb[idx - 1] if i0 > 0 else np.concatenate([[1.0], mb[idx[:-1]]])
    m = np.where(np.isfinite(m), m, 1.0)
    yrs = max((kd[idx[-1]] - (kd[i0 - 1] if i0 > 0 else kd[i0])).days, 1) / 365.25
    out = {}
    for nm, rr in (("hold", r), ("m_hold", r * m)):
        eq = np.cumprod(1.0 + rr)
        out[nm] = {"cagr": float(eq[-1] ** (1.0 / yrs) - 1), "mdd": float((eq / np.maximum.accumulate(
            np.concatenate([[1.0], eq]))[1:] - 1).min()), "total": float(eq[-1] - 1)}
    out["m_mean"] = float(m.mean())
    return out
