"""평균회귀 재검증 — 횡보장 전용 볼린저 밴드 (연구 전용, 운영 코드 무접촉).

사전 등록 = ``_workspace/analysis/strategy_opt_20261005/mrband/prereg.frozen.md``.
이 모듈은 순수 함수만 둔다(파일·DB 0). 실행·판정 = ``mrband_run.py``.

- ``regime_labels`` — 6장세 메모 §1.4(D4 × V4, D−1 기준) 그대로
- ``bollinger`` · ``atr_sma`` · ``entry_days`` — 신호
- ``sim_trade`` — 거래 하나의 청산(봉 안 경로 · 갭 · 지정가 · 손절 · 시간 · 장세 이탈 · 잠김 미룸)
- ``population`` — 종목마다 앞 거래 청산 뒤에만 다음 진입(자금 제약 없음)
- ``run_book`` — 정수 주 계좌(고정 비율 · 슬롯 · 1주 폴백 없음)
- ``cboot`` — 군집 부트스트랩(군집 복원 추출)
"""
from __future__ import annotations

import math
from collections import Counter
from typing import NamedTuple

import numpy as np
import pandas as pd

try:  # 속도용. 없으면 같은 코드를 파이썬으로 돈다(테스트 환경).
    from numba import njit
except Exception:  # pragma: no cover
    def njit(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

# ── 상수 (사전 등록 §3) ─────────────────────────────────────────────────────────
MAX_HOLD = 10            # 진입 봉 포함 10 거래일 → 11번째 봉 시가
PCT_STOP = 0.07
ATR_N = 14
ATR_MULT = 2.0
JUMP = 0.30              # |수정 종가 수익| > 30% = 기업행위 의심
LIMIT_UP = 1.29
LIMIT_DOWN = 0.71

EXIT_MID, EXIT_UPPER, EXIT_MIDCLOSE = 0, 1, 2
EXITS = {"mid": EXIT_MID, "upper": EXIT_UPPER, "mid_close": EXIT_MIDCLOSE}
STOPS = ("pct", "atr")
ENTRIES = ("touch", "reentry")

R_TP, R_STOP, R_TIME, R_LIQ, R_END = 0, 1, 2, 3, 4
REASONS = {R_TP: "TP", R_STOP: "STOP", R_TIME: "TIME", R_LIQ: "LIQ", R_END: "END"}

REG_NAMES = {"UL": "1 안정상승", "UH": "2 변동상승", "SL": "3 안정횡보",
             "SH": "4 변동횡보", "DL": "5 안정하락", "DH": "6 변동하락"}
REG_CODE = {"UL": 1, "UH": 2, "SL": 3, "SH": 4, "DL": 5, "DH": 6}
SIDEWAYS = (3, 4)


# ── 장세 라벨 ──────────────────────────────────────────────────────────────────

def _hyst_dir(sl, en=0.03, ex=0.01):
    st, out = "S", []
    for v in sl:
        if st == "S":
            if v > en:
                st = "U"
            elif v < -en:
                st = "D"
        elif st == "U" and v < ex:
            st = "D" if v < -en else "S"
        elif st == "D" and v > -ex:
            st = "U" if v > en else "S"
        out.append(st)
    return out


def _hyst_vol(v, hi=0.20, lo=0.16):
    st, out = "L", []
    for x in v:
        if st == "L" and x > hi:
            st = "H"
        elif st == "H" and x < lo:
            st = "L"
        out.append(st)
    return out


def regime_labels(close: pd.Series) -> pd.DataFrame:
    """069500 종가(날짜 인덱스) → D 일 라벨(D−1 종가까지). 열 ``slope vol20 dir vol reg code``."""
    c = close.astype(float)
    lr = np.log(c).diff()
    sma = c.rolling(60).mean()
    F = pd.DataFrame({"slope": sma / sma.shift(20) - 1,
                      "vol20": lr.rolling(20).std() * np.sqrt(252)}).shift(1)
    F = F[F.slope.notna() & F.vol20.notna()].copy()
    F["dir"] = _hyst_dir(F.slope.values)
    F["vol"] = _hyst_vol(F.vol20.values)
    F["reg"] = F["dir"] + F["vol"]
    F["code"] = F.reg.map(REG_CODE).astype(int)
    return F


# ── 지표 ───────────────────────────────────────────────────────────────────────

def bollinger(c: np.ndarray, n: int, k: float):
    """(mid, lo, up) — 모표준편차(ddof=0). 앞 n−1 봉 = NaN."""
    s = pd.Series(np.asarray(c, dtype=float))
    mid = s.rolling(n).mean()
    sd = s.rolling(n).std(ddof=0)
    return mid.to_numpy(), (mid - k * sd).to_numpy(), (mid + k * sd).to_numpy()


def atr_sma(h, l, c, n: int = ATR_N) -> np.ndarray:
    h, l, c = (np.asarray(x, dtype=float) for x in (h, l, c))
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    return pd.Series(tr).rolling(n).mean().to_numpy()


def entry_days(c: np.ndarray, lo: np.ndarray, mode: str) -> np.ndarray:
    """신호일 t(bool). touch = c_t < lo_t · reentry = c_{t−1} < lo_{t−1} ∧ c_t ≥ lo_t."""
    c = np.asarray(c, dtype=float)
    with np.errstate(invalid="ignore"):
        below = c < lo
        if mode == "touch":
            return below & np.isfinite(lo)
        if mode == "reentry":
            prev = np.r_[False, below[:-1]]
            return prev & (c >= lo) & np.isfinite(lo)
    raise ValueError(mode)


def locked_bars(o, h, l, c) -> np.ndarray:
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    pc = np.r_[np.nan, c[:-1]]
    with np.errstate(invalid="ignore"):
        return (pc > 0) & (o <= pc * LIMIT_DOWN) & (h == l)


def jump_bars(c) -> np.ndarray:
    c = np.asarray(c, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.r_[0.0, c[1:] / c[:-1] - 1]
    return np.abs(np.nan_to_num(r)) > JUMP


# ── 거래 하나 ──────────────────────────────────────────────────────────────────

@njit(cache=True)
def sim_trade(o, h, l, c, notrade, locked, mid, up, nonside, e, stop_px, exit_mode, liq, adverse,
              max_hold=MAX_HOLD):
    """진입 봉 e(시가 체결) → (청산 봉, 청산가(수정), 사유, 단계 0=시가 1=장중·종가).

    지정가 이익선 = 전일 값(``mid[d-1]`` 또는 ``up[d-1]``) · ``exit_mode==2`` 는 종가 ≥ mid → 다음 시가.
    ``nonside[d]`` = d 일 라벨이 횡보가 아님(``liq`` 일 때만 씀). 잠김·거래 없는 봉은 체결을 다음 시가로 미룬다.
    """
    n = len(o)
    pending = -1
    for d in range(e, n):
        tp = np.nan
        if exit_mode == 0:
            tp = mid[d - 1]
        elif exit_mode == 1:
            tp = up[d - 1]
        if d > e:
            if liq and nonside[d] and pending < 0:
                pending = 3
            if notrade[d]:
                continue
            od = o[d]
            if pending >= 0:
                if locked[d]:
                    continue
                return d, od, pending, 0
            if od <= stop_px:
                if locked[d]:
                    pending = 1
                    continue
                return d, od, 1, 0
            if tp == tp and od >= tp:
                return d, od, 0, 0
        if not notrade[d] and not locked[d]:
            od = o[d]
            if d == e and tp == tp and od >= tp:
                return d, od, 0, 1          # 산 시가가 이미 이익선 위 — 지정가가 곧바로 체결
            if adverse or c[d] >= od:
                p1, p2 = l[d], h[d]
            else:
                p1, p2 = h[d], l[d]
            prev = od
            for px in (p1, p2, c[d]):
                if px < prev:
                    if px <= stop_px:
                        return d, min(prev, stop_px), 1, 1
                elif px > prev:
                    if tp == tp and px >= tp:
                        return d, max(prev, tp), 0, 1
                prev = px
        if pending < 0:
            if exit_mode == 2 and mid[d] == mid[d] and c[d] >= mid[d]:
                pending = 0
            elif d - e + 1 >= max_hold:
                pending = 2
    return n - 1, c[n - 1], 4, 1


def stop_price(E: float, stop: str, atr_t: float) -> float:
    if stop == "pct":
        return E * (1.0 - PCT_STOP)
    if stop == "atr":
        return E - ATR_MULT * atr_t if atr_t == atr_t else E * (1.0 - PCT_STOP)
    raise ValueError(stop)


def net_ret(E: float, X: float, cost_rt: float) -> float:
    cs = cost_rt / 2.0
    return (1 - cs) * X / ((1 + cs) * E) - 1


# ── 후보 · 모집단 ─────────────────────────────────────────────────────────────

class Cand(NamedTuple):
    ticker: str
    e: int           # 종목 안 진입 봉 위치
    x: int           # 종목 안 청산 봉 위치
    e_gd: int
    x_gd: int
    phase: int
    E: float         # 수정 진입가
    X: float         # 수정 청산가(판정판)
    reason: int
    reg: int         # 진입일 라벨 코드
    jump: bool       # 기업행위 의심 거래
    E_raw: float     # 원본 시가(수량 계산)
    X_adv: float     # 불리판 청산가
    x_adv: int


def ticker_ind(b: dict, lab_gd: np.ndarray, n: int, k: float) -> dict:
    """종목 하나 · (N, k) 하나의 지표 묶음 — 청산·손절 조합끼리 다시 쓰려고 따로 뺐다."""
    o, h, l, c = b["o"], b["h"], b["l"], b["c"]
    mid, lo, up = bollinger(c, n, k)
    lab = lab_gd[b["di"]]
    return {"mid": mid, "lo": lo, "up": up, "atr": atr_sma(h, l, c),
            "nt": np.asarray(b["notrade"], dtype=np.bool_), "lk": locked_bars(o, h, l, c),
            "jcs": np.r_[0, np.cumsum(jump_bars(c))], "lab": lab, "nonside": ~np.isin(lab, SIDEWAYS),
            "pc": np.r_[np.nan, c[:-1]], "sig": {m: entry_days(c, lo, m) for m in ENTRIES}}


def candidates_for_ticker(t: str, b: dict, lab_gd: np.ndarray, sig_ok: np.ndarray, *, n: int, k: float,
                          exit_mode: int, stop: str, liq: bool, sideways_only: bool,
                          entry_modes=ENTRIES, ind: "dict | None" = None) -> "dict[str, list[Cand]]":
    """한 종목의 진입 후보(진입 방식별). ``sig_ok[t]`` = 신호일 유니버스 거름(시총·거래대금·거래 있음)."""
    o, h, l, c = b["o"], b["h"], b["l"], b["c"]
    di = b["di"]
    nb = len(o)
    out = {m: [] for m in entry_modes}
    if nb < n + 2:
        return out
    if ind is None:
        ind = ticker_ind(b, lab_gd, n, k)
    mid, up, atr, nt, lk, jcs, lab, nonside, pc = (ind[x] for x in ("mid", "up", "atr", "nt", "lk", "jcs",
                                                                    "lab", "nonside", "pc"))
    sig = {m: ind["sig"][m] & sig_ok for m in entry_modes}
    anyday = np.zeros(nb, dtype=bool)
    for m in entry_modes:
        anyday |= sig[m]
    cache = {}
    for ts in np.nonzero(anyday[:-1])[0]:
        e = ts + 1
        if nt[e] or not (o[e] > 0) or lab[e] == 0:
            continue
        if pc[e] > 0 and o[e] >= pc[e] * LIMIT_UP:
            continue
        if sideways_only and lab[e] not in SIDEWAYS:
            continue
        if e not in cache:
            sp = stop_price(o[e], stop, atr[ts])
            x, X, r, ph = sim_trade(o, h, l, c, nt, lk, mid, up, nonside, e, sp, exit_mode, liq, False)
            xa, Xa, _, _ = sim_trade(o, h, l, c, nt, lk, mid, up, nonside, e, sp, exit_mode, liq, True)
            j0 = max(0, ts - n + 1)
            jump = bool(jcs[max(x, xa) + 1] - jcs[j0 + 1] > 0) if max(x, xa) >= j0 + 1 else False
            cache[e] = Cand(t, int(e), int(x), int(di[e]), int(di[x]), int(ph), float(o[e]), float(X), int(r),
                            int(lab[e]), jump, float(b["o_raw"][e]), float(Xa), int(xa))
        for m in entry_modes:
            if sig[m][ts]:
                out[m].append(cache[e])
    return out


def population(cands: "list[Cand]") -> "list[Cand]":
    """종목마다 앞 거래 청산 봉 뒤에만 다음 진입(청산 당일 재진입 없음)."""
    by = {}
    for cd in cands:
        by.setdefault(cd.ticker, []).append(cd)
    out = []
    for t, lst in by.items():
        lst.sort(key=lambda z: z.e)
        last_x = -1
        for cd in lst:
            if cd.e > last_x:
                out.append(cd)
                last_x = cd.x
    out.sort(key=lambda z: (z.e_gd, z.ticker))
    return out


# ── 부트스트랩 ────────────────────────────────────────────────────────────────

def cboot(values, keys, *, n_boot: int = 2000, seed: int = 20261005, q: float = 0.05,
          chunk: int = 250) -> "tuple[float, float, float, float]":
    """(평균, q 분위, 1−q 분위, 표준오차). 군집 복원 추출 — 점추정 = Σv/n."""
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return (float("nan"),) * 4
    _, idx = np.unique(np.asarray(keys), return_inverse=True)
    K = int(idx.max()) + 1
    s1 = np.bincount(idx, weights=v, minlength=K)
    s0 = np.bincount(idx, minlength=K).astype(float)
    est = float(v.mean())
    if K < 2:
        return est, float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    stats = []
    left = n_boot
    while left > 0:
        m = min(chunk, left)
        pick = rng.integers(0, K, size=(m, K))
        stats.append(s1[pick].sum(axis=1) / s0[pick].sum(axis=1))
        left -= m
    st = np.concatenate(stats)
    return est, float(np.percentile(st, 100 * q)), float(np.percentile(st, 100 * (1 - q))), float(st.std(ddof=1))


def week_key(cal: pd.DatetimeIndex, gd: int) -> str:
    y, w, _ = cal[gd].isocalendar()
    return f"{y}-W{w:02d}"


def diff_week_boot(a_vals, a_weeks, b_vals, b_weeks, *, n_boot: int = 2000, seed: int = 20261005,
                   q: float = 0.05) -> "tuple[float, float, float]":
    """두 팔 평균 차(a − b) — 공통 ISO 주 블록을 같이 재표집."""
    weeks = sorted(set(a_weeks) | set(b_weeks))
    wi = {w: i for i, w in enumerate(weeks)}
    K = len(weeks)
    ia = np.array([wi[w] for w in a_weeks], dtype=np.int64)
    ib = np.array([wi[w] for w in b_weeks], dtype=np.int64)
    a1 = np.bincount(ia, weights=np.asarray(a_vals, float), minlength=K)
    a0 = np.bincount(ia, minlength=K).astype(float)
    b1 = np.bincount(ib, weights=np.asarray(b_vals, float), minlength=K)
    b0 = np.bincount(ib, minlength=K).astype(float)
    est = float(np.mean(a_vals) - np.mean(b_vals))
    rng = np.random.default_rng(seed)
    st = []
    for _ in range(0, n_boot, 250):
        pick = rng.integers(0, K, size=(min(250, n_boot), K))
        with np.errstate(invalid="ignore", divide="ignore"):
            st.append(a1[pick].sum(1) / a0[pick].sum(1) - b1[pick].sum(1) / b0[pick].sum(1))
    st = np.concatenate(st)[:n_boot]
    st = st[np.isfinite(st)]
    return est, float(np.percentile(st, 100 * q)), float(np.percentile(st, 100 * (1 - q)))


# ── 계좌 ───────────────────────────────────────────────────────────────────────

def run_book(cands: "list[Cand]", bars: dict, cal: pd.DatetimeIndex, g0: int, g1: int, seed: int, *,
             start_equity: float, cost_rt: float, pos_ratio: float, max_pos: int) -> dict:
    """후보 전부(겹침 포함) 위에서 하루 순서대로 산다. 경로는 후보에 이미 정해져 있다.

    하루 = ① 시가 단계 청산 ② 그날 신호 매수(씨앗 섞기 · 보유/당일 매도 종목 제외 · 슬롯) ③ 장중·종가 청산
    ④ 종가 평가(수량 × 원본 진입가 × 수정 종가 ÷ 수정 진입가).
    """
    cs = cost_rt / 2.0
    rng = np.random.default_rng(seed)
    by_e = {}
    for cd in cands:
        if g0 <= cd.e_gd <= g1:
            by_e.setdefault(cd.e_gd, []).append(cd)
    cash = float(start_equity)
    pos = {}                 # ticker -> (cand, qty)
    eq_prev = float(start_equity)
    equity, trades = [], []
    cnt = Counter()
    gd2loc = {}

    def loc_close(t, gd):
        b = bars[t]
        key = (t, gd)
        if key not in gd2loc:
            i = int(np.searchsorted(b["di"], gd, side="right")) - 1
            gd2loc[key] = i
        i = gd2loc[key]
        return b["c"][i]

    def close_out(t, px, gd):
        nonlocal cash
        cd, q = pos.pop(t)
        cash += q * cd.E_raw * (px / cd.E) * (1 - cs)
        trades.append((cd, q, px, gd))

    for gd in range(g0, g1 + 1):
        B = eq_prev
        sold = set()
        for t in list(pos):
            cd, q = pos[t]
            if cd.x_gd == gd and cd.phase == 0:
                close_out(t, cd.X, gd)
                sold.add(t)
        todays = list(by_e.get(gd, []))
        rng.shuffle(todays)
        for cd in todays:
            if cd.ticker in pos or cd.ticker in sold:
                continue
            cnt["signal"] += 1
            if len(pos) >= max_pos:
                cnt["slot_full"] += 1
                continue
            q = int(math.floor(B * pos_ratio / cd.E_raw)) if cd.E_raw > 0 else 0
            if q * cd.E_raw * (1 + cs) > cash:
                q = int(math.floor(cash / (cd.E_raw * (1 + cs))))
            if q <= 0:
                cnt["zero_funds"] += 1
                continue
            cash -= q * cd.E_raw * (1 + cs)
            pos[cd.ticker] = (cd, q)
            cnt["fill"] += 1
        for t in list(pos):
            cd, q = pos[t]
            if cd.x_gd == gd and cd.phase == 1:
                close_out(t, cd.X, gd)
        eq = cash + sum(q * cd.E_raw * (loc_close(t, gd) / cd.E) for t, (cd, q) in pos.items())
        equity.append(eq)
        eq_prev = eq
    open_mtm = 0.0
    for t, (cd, q) in list(pos.items()):
        px = loc_close(t, g1)
        open_mtm += q * cd.E_raw * (px / cd.E) - q * cd.E_raw * (1 + cs)
        trades.append((cd, q, px, None))
    eq = np.array(equity)
    closed = sum(q * cd.E_raw * (px / cd.E) * (1 - cs) - q * cd.E_raw * (1 + cs)
                 for cd, q, px, g in trades if g is not None)
    recon = float(eq[-1] - (start_equity + closed + open_mtm)) if len(eq) else 0.0
    return {"equity": eq, "trades": trades, "counts": dict(cnt), "recon": recon}


def cagr(eq: np.ndarray, start: float) -> float:
    return float((eq[-1] / start) ** (252.0 / len(eq)) - 1) if len(eq) >= 2 else float("nan")


def mdd(eq: np.ndarray, start: float) -> float:
    e = np.concatenate([[start], eq])
    return float((e / np.maximum.accumulate(e) - 1).min())
