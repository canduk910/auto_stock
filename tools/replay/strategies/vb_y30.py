"""volatility_breakout 30년 재검증 층 — 30년 보관소(``krx_daily_long/unified``) 위의 VB 재현.

사전 고정 = ``_workspace/analysis/strategy_30y_20261006/vb/prereg.md``(sha256 동결).
전수 점검 재현(``vb.py``)·효율화 축(``vb_opt.py``)과 같은 규칙을 **배열로** 다시 쓴다(30년 = 후보 수십만 행).
바뀐 것만:
- 유니버스 = 시총·거래대금 원화 문턱 → 그날 순위 백분위(X 는 2025 년 비율 평균, prereg §2)
- 비용 = 진입일의 시기별 왕복 비용(``meta/regime_costs.csv``)
- 체결가 = 목표가 × fill, 그날 고가로 자름 · 하한가 잠김 날의 종가 청산 → 다음 봉 시가
- 가격제한폭 위반 표시 행 제외(``meta/unified_jump_flags.csv``)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..audit import panel as PN
from . import vb as VB

ARCHIVE = "/Users/koscom/Projects/auto_stock/data/archive/krx_daily_long"
UNIFIED = os.path.join(ARCHIVE, "unified")
ARCH_COLS = ["ticker", "name", "bas_dd", "open", "high", "low", "close", "prev_diff", "volume", "trade_value",
             "mktcap", "market", "open_adj", "high_adj", "low_adj", "close_adj", "adj_factor"]
LOCK_TOL = 1.005          # 하한가 잠김 판정 여유(호가 단위 반올림)
NEAR_UPPER = 0.995        # 상한가 근처 진입 보고 칸
FILL_BASE = 1.0193        # 30년 규약 6 기본판(BFB 실측)
FILL_VB = 1.0008          # VB 실거래 실측 중앙(보고판)
FILL_TARGET = 1.0         # 낙관 체결판
DISASTER_PCT = -10.0


# ── 자료 ────────────────────────────────────────────────────────────────

NPZ_CACHE = ("/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/1177b759-a6e8-4448-8205-8c5f1396a3a3/"
             "scratchpad/opt/vb_y30/unified_cols.npz")


def export_npz(path: str = NPZ_CACHE) -> str:
    """보관소 parquet → 열별 npz. 운영 의존성이 있는 파이썬의 pyarrow 가 새 parquet 을 못 읽어서 둔다
    (pyarrow 19 「Repetition level histogram size mismatch」). 값은 그대로 옮긴다."""
    fs = sorted(f for f in os.listdir(UNIFIED) if f.endswith(".parquet"))
    df = pd.concat([pd.read_parquet(os.path.join(UNIFIED, f), columns=ARCH_COLS) for f in fs], ignore_index=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    arr = {}
    for c in ARCH_COLS:
        if c == "bas_dd":
            arr[c] = pd.to_datetime(df[c]).to_numpy().astype("datetime64[ns]").astype(np.int64)
        elif df[c].dtype.kind in "fiub":
            arr[c] = df[c].to_numpy()
        else:
            arr[c] = df[c].astype(str).to_numpy().astype("U")
    np.savez(path, **arr)
    return path


def load_unified(end: "str | None" = None) -> pd.DataFrame:
    fs = sorted(f for f in os.listdir(UNIFIED) if f.endswith(".parquet"))
    try:
        df = pd.concat([pd.read_parquet(os.path.join(UNIFIED, f), columns=ARCH_COLS) for f in fs], ignore_index=True)
    except OSError:
        z = np.load(NPZ_CACHE)
        df = pd.DataFrame({c: z[c] for c in ARCH_COLS})
        df["bas_dd"] = pd.to_datetime(df["bas_dd"].astype("int64"))
    df["bas_dd"] = pd.to_datetime(df["bas_dd"])
    if end is not None:
        df = df[df.bas_dd <= pd.Timestamp(end)]
    return df


def add_rank_pct(df: pd.DataFrame) -> pd.DataFrame:
    """그날 전 종목 안 내림차순 순위 ÷ 종목 수 → ``mc_pct``·``tv_pct``(작을수록 큼). 결측 = 맨 뒤."""
    g = df.groupby("bas_dd")
    n = g["ticker"].transform("size").astype(float)
    df["mc_pct"] = df["mktcap"].fillna(-1).groupby(df["bas_dd"]).rank(ascending=False, method="max") / n
    df["tv_pct"] = df["trade_value"].fillna(-1).groupby(df["bas_dd"]).rank(ascending=False, method="max") / n
    return df


def x_thresholds(df: pd.DataFrame, year: int = 2025, mcap: float = 5e10, tv: float = 5e10) -> dict:
    """prereg §2 — 그해 각 거래일의 「원화 문턱 이상」 종목 비율의 평균."""
    y = df[df.bas_dd.dt.year == year]
    g = y.groupby("bas_dd")
    fm = g["mktcap"].apply(lambda s: float((s >= mcap).mean()))
    ft = g["trade_value"].apply(lambda s: float((s >= tv).mean()))
    return {"X_mcap": float(fm.mean()), "X_tv": float(ft.mean()), "year": year, "days": int(len(fm)),
            "X_mcap_minmax": [float(fm.min()), float(fm.max())], "X_tv_minmax": [float(ft.min()), float(ft.max())]}


def load_jump_flags() -> pd.DataFrame:
    j = pd.read_csv(os.path.join(ARCHIVE, "meta/unified_jump_flags.csv"), dtype={"ticker": str})
    j["bas_dd"] = pd.to_datetime(j["bas_dd"])
    return j[["ticker", "bas_dd"]]


def drop_jump_rows(df: pd.DataFrame, jumps: pd.DataFrame) -> "tuple[pd.DataFrame, int]":
    key = pd.MultiIndex.from_frame(jumps)
    m = pd.MultiIndex.from_frame(df[["ticker", "bas_dd"]]).isin(key)
    return df[~m], int(m.sum())


def load_costs() -> pd.DataFrame:
    c = pd.read_csv(os.path.join(ARCHIVE, "meta/regime_costs.csv"))
    c["from"] = pd.to_datetime(c["from"])
    c["to"] = pd.to_datetime(c["to"])
    return c


def cost_rt_for_dates(dates: pd.DatetimeIndex, costs: pd.DataFrame) -> np.ndarray:
    """날짜마다 왕복 비용(비율). 표 밖 = NaN(실행이 멈추게)."""
    out = np.full(len(dates), np.nan)
    for _, r in costs.iterrows():
        hi = r["to"] if pd.notna(r["to"]) else pd.Timestamp("2100-01-01")
        m = (dates >= r["from"]) & (dates <= hi)
        out[m] = float(r["round_trip_pct_assumed"]) / 100.0
    return out


def load_limits() -> pd.DataFrame:
    p = pd.read_csv(os.path.join(ARCHIVE, "meta/regime_price_limit.csv"))
    p["from"] = pd.to_datetime(p["from"])
    p["to"] = pd.to_datetime(p["to"])
    return p


def limit_for(market_code: int, dates: pd.DatetimeIndex, limits: pd.DataFrame) -> np.ndarray:
    """``mkt`` 0 = KOSPI · 1 = KOSDAQ(GLOBAL 포함) · 날짜별 제한폭(비율). 정액제·모름 = NaN."""
    name = "KOSPI" if market_code == 0 else "KOSDAQ"
    out = np.full(len(dates), np.nan)
    for _, r in limits.iterrows():
        if r["market"] not in (name, "ALL"):
            continue
        try:
            v = float(r["limit_pct"]) / 100.0
        except ValueError:
            continue
        hi = r["to"] if pd.notna(r["to"]) else pd.Timestamp("2100-01-01")
        m = (dates >= r["from"]) & (dates <= hi)
        out[m] = v
    return out


def build(end: "str | None" = None, *, drop_jumps: bool = True):
    """(Store, 메타). Store.bars 키 = ``panel.build_store`` + ``mc_pct tv_pct prev_diff``."""
    df = load_unified(end)
    xs = x_thresholds(df)
    df = add_rank_pct(df)
    nj = 0
    if drop_jumps:
        df, nj = drop_jump_rows(df, load_jump_flags())
    st = PN.build_store(df, db=None, nontrade="flag", junction_rescale=False,
                        extra_cols=("mc_pct", "tv_pct", "prev_diff"))
    return st, {"X": xs, "jump_rows_dropped": nj, **st.meta}


# ── 후보(배열) ───────────────────────────────────────────────────────────

def noise_k_series(o, h, l, c, k_period: int = 15) -> np.ndarray:
    """봉 i 의 k = i−2 … i−(k_period+2) noise 평균(범위 0 봉 제외) — ``vb.noise_k`` 의 배열판."""
    rng = h - l
    nz = np.where(rng > 0, 1.0 - np.abs(c - o) / np.where(rng > 0, rng, 1.0), np.nan)
    s = pd.Series(nz).rolling(k_period + 1, min_periods=1).mean().to_numpy()
    out = np.full(len(c), np.nan)
    out[2:] = s[:-2]
    return out


def sma(c: np.ndarray, n: int = 20) -> np.ndarray:
    return pd.Series(c).rolling(n, min_periods=n).mean().to_numpy()


@dataclass
class Cands:
    """그날 아침 후보 전부(평평한 배열). 행 = (종목, D)."""
    tk: np.ndarray      # 종목 번호(``names`` 색인)
    names: list
    i: np.ndarray       # 종목 봉 인덱스 D
    gd: np.ndarray      # 전역 달력 인덱스 D
    k: np.ndarray
    rng_prev: np.ndarray
    tv_prev: np.ndarray
    trend: np.ndarray
    range_pct: np.ndarray
    O: np.ndarray
    H: np.ndarray
    L: np.ndarray
    C: np.ndarray
    raw: np.ndarray     # 원주가 ÷ 수정주가(D)
    nxt_o: np.ndarray   # 다음 봉 시가(수정) · 없으면 NaN
    nxt_gd: np.ndarray  # 다음 봉 전역 인덱스 · 없으면 −1
    lock_dn: np.ndarray  # D 하한가 잠김
    near_up: np.ndarray  # D 고가가 상한가 −0.5% 이내
    m: np.ndarray


def candidates(st, X: dict, m_day: np.ndarray, limits: pd.DataFrame, p: dict = VB.VB_OP,
               absolute: "tuple[float, float] | None" = None) -> Cands:
    """prereg §2·§3. ``absolute=(min_mcap, min_tv)`` 이면 원화 문턱(5년 재현 대조용)."""
    cal = st.cal
    cols = {k: [] for k in ("tk", "i", "gd", "k", "rng_prev", "tv_prev", "trend", "range_pct", "O", "H", "L", "C",
                            "raw", "nxt_o", "nxt_gd", "lock_dn", "near_up")}
    names = []
    for t in sorted(st.bars):
        if not (len(t) == 6 and t.isdigit()):
            continue
        b = st.bars[t]
        n = len(b["c"])
        if n < 3:
            continue
        di = b["di"].astype(np.int64)
        o, h, l, c = b["o"], b["h"], b["l"], b["c"]
        ok = np.zeros(n, bool)
        ok[1:] = (di[:-1] == di[1:] - 1) & ~b["notrade"][:-1] & ~b["notrade"][1:]
        ok[:2] = False
        j = np.maximum(np.arange(n) - 1, 0)
        if absolute is None:
            ok &= (b["mc_pct"][j] <= X["X_mcap"]) & (b["tv_pct"][j] <= X["X_tv"])
        else:
            mc = b["mktcap"][j]
            ok &= np.isfinite(mc) & (mc >= absolute[0]) & (b["tv"][j] >= absolute[1])
        pc = b["c_raw"][j]
        ok &= (pc >= p["price_min"]) & (pc <= p["price_max"])
        k = noise_k_series(o, h, l, c, p["k_period"])
        rp = h[j] - l[j]
        ok &= np.isfinite(k) & (rp * k > 0) & (o > 0)
        idx = np.nonzero(ok)[0]
        if len(idx) == 0:
            continue
        s20 = sma(c)
        tr = np.zeros(n, bool)
        a, bb = s20[idx - 1], np.where(idx - 6 >= 0, s20[np.maximum(idx - 6, 0)], np.nan)
        tr[idx] = np.isfinite(a) & np.isfinite(bb) & (c[idx - 1] > a) & (a > bb)
        dates = cal[di[idx]]
        kq = np.asarray(b["mkt"][idx]) == 1
        lim = np.where(kq, limit_for(1, dates, limits), limit_for(0, dates, limits))
        base = b["c_raw"][idx] - b["prev_diff"][idx]
        cr = b["c_raw"][idx]
        lock = np.isfinite(lim) & (base > 0) & (l[idx] == c[idx]) & (cr <= base * (1 - lim) * LOCK_TOL)
        hr = h[idx] * b["raw"][idx]
        near = np.isfinite(lim) & (base > 0) & (hr >= base * (1 + lim) * NEAR_UPPER)
        nx = idx + 1
        has = nx < n
        nxt_o = np.where(has, o[np.minimum(nx, n - 1)], np.nan)
        nxt_gd = np.where(has, di[np.minimum(nx, n - 1)], -1)
        ti = len(names)
        names.append(t)
        cols["tk"].append(np.full(len(idx), ti))
        cols["i"].append(idx)
        cols["gd"].append(di[idx])
        cols["k"].append(k[idx])
        cols["rng_prev"].append(rp[idx])
        cols["tv_prev"].append(b["tv"][idx - 1])
        cols["trend"].append(tr[idx])
        cols["range_pct"].append(np.where(c[idx - 1] > 0, rp[idx] / np.where(c[idx - 1] > 0, c[idx - 1], 1), np.nan))
        cols["O"].append(o[idx])
        cols["H"].append(h[idx])
        cols["L"].append(l[idx])
        cols["C"].append(c[idx])
        cols["raw"].append(b["raw"][idx])
        cols["nxt_o"].append(nxt_o)
        cols["nxt_gd"].append(nxt_gd)
        cols["lock_dn"].append(lock)
        cols["near_up"].append(near)
    arr = {k: np.concatenate(v) for k, v in cols.items()}
    order = np.lexsort((arr["tk"], arr["gd"]))
    arr = {k: v[order] for k, v in arr.items()}
    mv = m_day[arr["gd"]]
    return Cands(names=names, m=mv, **arr)


# ── 신호 · 청산 ─────────────────────────────────────────────────────────

def filter_mask(cd: Cands, filt: str, f4_k_max: float = 0.50, f5_min: float = 0.05, f6_top: int = 10) -> np.ndarray:
    m1 = np.where(np.isfinite(cd.m), cd.m, 1.0)     # 판정 불가 = 운영 fail-open(m = 1)
    if filt == "F0":
        return np.ones(len(cd.gd), bool)
    if filt == "F1":
        return m1 >= 1.0
    if filt == "F2":
        return m1 >= 0.75
    if filt == "F3":
        return cd.trend.astype(bool)
    if filt == "F4":
        return cd.k <= f4_k_max
    if filt == "F5":
        return np.isfinite(cd.range_pct) & (cd.range_pct >= f5_min)
    if filt == "F6":
        # 그날 전일 거래대금 상위 N(동률 = 종목코드 순)
        df = pd.DataFrame({"gd": cd.gd, "tv": -cd.tv_prev, "nm": [cd.names[x] for x in cd.tk]})
        r = df.sort_values(["gd", "tv", "nm"]).groupby("gd").cumcount()
        return (r.reindex(df.index).to_numpy() < f6_top)
    raise ValueError(filt)


@dataclass
class Sigs:
    idx: np.ndarray     # Cands 행 번호
    E: np.ndarray       # 체결가(수정)
    target: np.ndarray


def signals(cd: Cands, km: float, filt: str, fill: float, fmask_cache: "dict | None" = None) -> Sigs:
    fm = filter_mask(cd, filt) if fmask_cache is None else fmask_cache[filt]
    tgt = cd.O + cd.rng_prev * cd.k * km
    hit = fm & (cd.H >= tgt)
    idx = np.nonzero(hit)[0]
    E = np.minimum(tgt[idx] * fill, cd.H[idx])
    return Sigs(idx, E, tgt[idx])


def outcome(cd: Cands, sg: Sigs, hold: str, stop_mode: str, stop: float, version: str):
    """(청산가(수정), 사유 코드, 청산 gd) 배열. 사유 = 0 CLOSE · 1 STOP · 2 CLOSE_STOP · 3 DISASTER ·
    4 NEXT_OPEN · 5 LOCK_NEXT_OPEN."""
    ix = sg.idx
    E = sg.E
    H, L, C = cd.H[ix], cd.L[ix], cd.C[ix]
    nxo, nxg = cd.nxt_o[ix], cd.nxt_gd[ix]
    gd = cd.gd[ix]
    if version not in ("pes", "opt"):
        raise ValueError(version)
    probe = L if version == "pes" else C
    px = C.copy()
    why = np.zeros(len(ix), np.int8)
    xg = gd.copy()
    done = np.zeros(len(ix), bool)
    if stop_mode == "intraday":
        line = E * (1 + stop / 100.0)
        s = probe <= line
        px[s], why[s], done[s] = line[s], 1, True
    elif stop_mode == "close":
        dline = E * (1 + DISASTER_PCT / 100.0)
        s = probe <= dline
        px[s], why[s], done[s] = dline[s], 3, True
        cs = ~done & (C <= E * (1 + stop / 100.0))
        px[cs], why[cs], done[cs] = C[cs], 2, True
    else:
        raise ValueError(stop_mode)
    if hold == "C":
        on = np.zeros(len(ix), bool)
    elif hold == "N":
        on = ~done
    elif hold == "W":
        on = ~done & (C > E)
    else:
        raise ValueError(hold)
    on &= nxg >= 0
    px[on], why[on], xg[on] = nxo[on], 4, nxg[on]
    # 하한가 잠김: 종가 청산(CLOSE · CLOSE_STOP)인데 그날 팔 수 없다 → 다음 봉 시가
    lk = (~on) & ((why == 0) | (why == 2)) & cd.lock_dn[ix] & (nxg >= 0)
    px[lk], why[lk], xg[lk] = nxo[lk], 5, nxg[lk]
    return px, why, xg


def cooldown_keep(cd: Cands, sg: Sigs, xg: np.ndarray, cooldown: int = VB.VB_OP["cooldown_days"]) -> np.ndarray:
    """P1 모집단 — 종목마다 청산일 + N 거래일까지 재진입 금지. 신호는 (gd, 종목) 순으로 정렬돼 있다."""
    tk = cd.tk[sg.idx]
    gd = cd.gd[sg.idx]
    keep = np.zeros(len(tk), bool)
    last: dict = {}
    for j in range(len(tk)):
        t = int(tk[j])
        le = last.get(t)
        if le is not None and gd[j] <= le + cooldown:
            continue
        keep[j] = True
        last[t] = int(xg[j])
    return keep


# ── 판정 재료 ────────────────────────────────────────────────────────────

def cluster_boot(values, keys, *, n_boot: int = 2000, seed: int = 20261005, q: float = 0.05,
                 chunk: int = 250) -> "tuple[float, float, float]":
    """``judge.cluster_bootstrap(order="sorted")`` 와 같은 난수 소비를 덩어리로 나눠 메모리를 줄인 판."""
    v = np.asarray(values, float)
    if len(v) == 0:
        return float("nan"), float("nan"), float("nan")
    est = float(v.mean())
    uk, idx = np.unique(np.asarray(keys), return_inverse=True)
    K = len(uk)
    if K < 2:
        return est, float("nan"), float("nan")
    s1 = np.bincount(idx, weights=v, minlength=K)
    s0 = np.bincount(idx, minlength=K).astype(float)
    rng = np.random.default_rng(seed)
    stats = []
    left = n_boot
    pv = np.full(K, 1.0 / K)
    while left > 0:
        m = min(chunk, left)
        cnt = rng.multinomial(K, pv, size=m).astype(float)
        stats.append(np.einsum("ij,j->i", cnt, s1) / np.einsum("ij,j->i", cnt, s0))
        left -= m
    st = np.concatenate(stats)
    return est, float(np.percentile(st, 100 * q)), float(np.percentile(st, 100 * (1 - q)))


def week_keys(cal: pd.DatetimeIndex, names: list, tk: np.ndarray, gd: np.ndarray) -> np.ndarray:
    iso = cal.isocalendar()
    yw = (iso["year"].to_numpy() * 100 + iso["week"].to_numpy()).astype(np.int64)
    return tk.astype(np.int64) * 1_000_000 + yw[gd]


def week_block_diff(a_ret, a_wk, b_ret, b_wk, *, n_boot: int = 2000, seed: int = 20261005, q: float = 0.05) -> dict:
    """두 판 평균 차(a − b)의 달력 ISO 주 블록 부트스트랩(``vb_opt.week_block_diff`` 와 같은 식, 주 키 = yyyyww)."""
    keys = np.unique(np.r_[a_wk, b_wk])
    K = len(keys)
    ia, ib = np.searchsorted(keys, a_wk), np.searchsorted(keys, b_wk)
    sa, na = np.bincount(ia, weights=a_ret, minlength=K), np.bincount(ia, minlength=K).astype(float)
    sb, nb = np.bincount(ib, weights=b_ret, minlength=K), np.bincount(ib, minlength=K).astype(float)
    est = float(sa.sum() / na.sum() - sb.sum() / nb.sum())
    rng = np.random.default_rng(seed)
    cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=n_boot).astype(float)
    e = lambda x: np.einsum("ij,j->i", cnt, x)  # noqa: E731
    stat = e(sa) / e(na) - e(sb) / e(nb)
    return {"diff": est, "lo90": float(np.percentile(stat, 100 * q)), "hi90": float(np.percentile(stat, 100 * (1 - q))),
            "se": float(np.std(stat, ddof=1)), "n_weeks": int(K)}


# ── 계좌(C7 · 시기별 비용) ────────────────────────────────────────────────

@dataclass
class BSig:
    ticker: str
    gd: int
    E: float
    E_raw: float
    px: float
    why: int
    xg: int
    Cc: float           # D 종가(수정) — 다음 날 청산 랏의 그날 평가


class Y30Pos:
    """한 랏 — 결과가 미리 정해진 랏(당일 또는 다음 봉 시가 청산)."""

    def __init__(self, s: BSig, qty: int):
        self.s, self.qty = s, qty
        self.k = qty * s.E_raw / s.E
        self.cost_basis = qty * s.E_raw
        self.exit_px = self.exit_reason = self.exit_gd = None
        self.last_px = s.E


def run_book_var(sbg: dict, sizer, cal: pd.DatetimeIndex, g0: int, g1: int, seed: int, *, start_equity: float,
                 cost_rt_gd: np.ndarray, max_pos: int, cooldown: int = VB.VB_OP["cooldown_days"]) -> dict:
    """``audit.book.run_book`` 과 같은 하루 순서 · 비용만 날짜별(한쪽 = 그날 왕복 ÷ 2).
    쿨다운은 계좌가 실제로 산 종목에만(청산일 기준). 다음 날 청산 랏은 진입일 종가로 평가."""
    from collections import Counter
    rng = np.random.default_rng(seed)
    cash = float(start_equity)
    pos: dict = {}
    eq_prev = float(start_equity)
    equity, trades = [], []
    cnt = Counter()
    last_exit: dict = {}
    for gd in range(g0, g1 + 1):
        B = eq_prev
        cs = cost_rt_gd[gd] / 2
        sold = set()
        for t in list(pos):
            ps = pos[t]
            if ps.s.xg == gd and ps.s.gd != gd:          # 다음 봉 시가 청산
                ps.exit_px, ps.exit_gd = ps.s.px, gd
                cash += ps.k * ps.exit_px * (1 - cs)
                trades.append(ps)
                sold.add(t)
                del pos[t]
        todays = list(sbg.get(gd, []))
        rng.shuffle(todays)
        stop_why = None
        for s in todays:
            if s.ticker in pos or s.ticker in sold:
                continue
            cnt["signal"] += 1
            if stop_why is None and len(pos) >= max_pos:
                stop_why = "slot_full"
            if stop_why is not None:
                cnt[stop_why] += 1
                continue
            le = last_exit.get(s.ticker)
            if le is not None and gd <= le + cooldown:
                cnt["zero_cooldown"] += 1
                continue
            P = int(round(s.E_raw))
            used = sum(x.cost_basis for x in pos.values())
            q = sizer(P, int(B), int(used)) if P > 0 else 0
            if q <= 0:
                cnt["zero_funds" if int(B) - int(used) < P else "zero_design"] += 1
                continue
            ps = Y30Pos(s, q)
            cash -= q * s.E_raw * (1 + cs)
            pos[s.ticker] = ps
            last_exit[s.ticker] = s.xg
            cnt["fill"] += 1
        for t in list(pos):
            ps = pos[t]
            if ps.s.gd != gd:
                continue
            if ps.s.xg == gd:
                ps.exit_px, ps.exit_gd = ps.s.px, gd
                cash += ps.k * ps.exit_px * (1 - cs)
                trades.append(ps)
                del pos[t]
            else:
                ps.last_px = ps.s.Cc
        eq = cash + sum(x.k * x.last_px for x in pos.values())
        equity.append(eq)
        eq_prev = eq
    for ps in pos.values():
        ps.exit_px, ps.exit_reason = ps.last_px, "OPEN"
        trades.append(ps)
    return {"equity": np.array(equity), "trades": trades, "counts": dict(cnt)}


def book_summary(runs: list, start_equity: float) -> dict:
    from ..audit import book as BK
    cg = [BK.cagr(r["equity"], start_equity) for r in runs]
    md = [BK.mdd(r["equity"], start_equity) for r in runs]
    yrs = len(runs[0]["equity"]) / 252.0
    fills = [r["counts"].get("fill", 0) for r in runs]
    ua = []
    for r in runs:
        c = r["counts"]
        free = c.get("signal", 0) - c.get("slot_full", 0)
        ua.append(c.get("zero_funds", 0) / free if free > 0 else float("nan"))
    return {"cagr_median": float(np.median(cg)), "cagr_min": float(np.min(cg)), "cagr_max": float(np.max(cg)),
            "mdd_median": float(np.median(md)), "trades_median": float(np.median([len(r["trades"]) for r in runs])),
            "fills_per_year_median": float(np.median(fills) / yrs),
            "unaffordable_ratio_median": float(np.nanmedian(ua)) if any(u == u for u in ua) else float("nan")}


# ── 기준선 ──────────────────────────────────────────────────────────────

def index_series() -> pd.DataFrame:
    s = pd.read_csv(os.path.join(ARCHIVE, "index/market_unit_series.csv"), parse_dates=["date"])
    return s[["date", "close"]].dropna().sort_values("date").reset_index(drop=True)


def baseline(idx: pd.DataFrame, m_of_date, start: str, end: str) -> dict:
    """지수 단순 보유 · m 비례 보유(m(D) × 그날 수익, 판정 불가 = 1) — 연 복리(252일) · 낙폭."""
    w = idx[(idx.date >= pd.Timestamp(start)) & (idx.date <= pd.Timestamp(end))]
    prev = idx[idx.date < pd.Timestamp(start)].tail(1)
    c = np.r_[prev.close.to_numpy(), w.close.to_numpy()].astype(float)
    r = c[1:] / c[:-1] - 1
    m = np.array([m_of_date(d) for d in w.date])
    m = np.where(np.isfinite(m), m, 1.0)
    out = {}
    for nm, rr in (("hold", r), ("m_hold", r * m)):
        eq = np.cumprod(1 + rr)
        n = len(eq)
        cagr = float(eq[-1] ** (252.0 / n) - 1) if n else float("nan")
        e = np.r_[1.0, eq]
        mdd = float((e / np.maximum.accumulate(e) - 1).min())
        out[nm] = {"cagr": cagr, "mdd": mdd, "days": n}
    return out
