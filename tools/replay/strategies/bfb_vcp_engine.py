"""VCP(vcp_breakout) · BFB(bull_flag_breakout) — 장중 돌파 두 전략의 재현 엔진(공용 층 위에 얹은 전략 층).

사전 등록 정본 = ``_workspace/analysis/strategy_audit_20261005/prereg.frozen.md`` §1.4 · §3.3 · §3.4.
규칙 정본 = 운영 코드 ``src/engine/strategies/vcp_breakout.py`` · ``bull_flag_breakout.py`` + 운영 DB
``strategy_config.params``(단계 1 추출본, 아래 ``VCP_DB``·``BFB_DB``).

후보 판정(``prepare``)은 운영 메서드를 **빠르게 다시 짠 것**이다(보관소 370만 종목·일을 운영 메서드로 돌리면
느리다). 같은지는 ``tests/unit/replay/test_audit_{vcp,bfb}.py`` 가 운영 메서드와 정수 가격 무작위 시리즈로
대조한다(``_check_trend_filter``·``_detect_base``·``_check_pullback_sequence``·``_check_volume_contraction``·
``_detect_pole_and_flag_detailed``·``StrategyBase._atr``).

일봉 근사(§1.4):
- 신호 봉 = D−1(전날 확정 봉까지로 후보 판정) → D 장중 돌파. 체결가 = max(시가, 돌파선).
  시가가 추격 상한(돌파선 × (1 + cap%)) 위면 진입 없음(동결본 판정판). 운영 래치(상한 위 시가 뒤
  상한 안으로 되돌아온 틱에서 매수)는 ``entry="latch"`` 보고판으로만 잰다.
- 장중 거래량 조건은 일봉으로 알 수 없다 → 판정판 = 조건 없음 · 보고판 = 그날 전체 거래량(룩어헤드).
- 진입 봉 경로: 시가 진입이면 §1.4 경로 그대로. 장중 돌파면 color = 양봉(시→저→고→종 → 돌파 뒤 고·종),
  음봉(시→고→저→종 → 돌파 뒤 고·저·종) · adverse(P5 불리) = 돌파 뒤 저→고→종(손절 먼저).
- 청산선(운영 ``check_exit_signal`` 순서와 무관하게 가장 높은 깨진 선이 이긴다 — 같은 틱이면 같은 체결가):
  터틀 손절 min(E − 2·N진입, E·(1+min_stop%)) → 본전 승격(고점 ≥ E + 1.5·N진입이면 ≥ E) · 백스톱 E·(1+backstop%)
  · 구조 하단(base_low / flag_low, 엄격 <) · 샹들리에(고점 − 2·ATR14(전날)) · VCP EMA50(전날, 엄격 <)
  · BFB 측정 이동 목표(위로 ≥, 전량) · BFB 시간 청산(달력일 > max_hold + 2 → 그날 시가).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from replay.audit import bars as BR
from replay.audit import indicators as IND

# ── 운영 DB 값(단계 1 추출본 strategy_config, 2026-10-05 07:00 KST) — 행위 키만 ─────────────────
VCP_DB = dict(
    ema_short=50, ema_mid=150, ema_long=200, long_ema_uptrend_days=20, daily_fetch_depth_mode="full",
    base_min_days=25, base_max_days=40, base_depth_pct=0.35,
    pullback_count_min=1, pullback_count_max=4, last_pullback_max=0.15, min_swing_atr_mult=1.0,
    volume_contraction_ratio=1.0, breakout_volume_mult=1.2, entry_start="09:05", entry_end="14:30",
    max_breakout_extension_pct=7.5, position_ratio=0.2, max_positions=5,
    stop_loss_rate=-7, atr_period=14, atr_trail_mult=2, breakeven_promote_atr=1.5,
    reentry_cooldown_days=7, sizing_mode="turtle", risk_pct=0.01, stop_atr=2.0,
    turtle_backstop_pct=-9.0, min_vol_floor_pct=1.0, turtle_min_stop_pct=-5.0,
    max_lot_units=2.0, max_lot_ratio_mult=2.5, market_unit_mode="enforce",
    min_market_cap=10_000_000_000, min_trade_amount=1_000_000_000, daily_loss_limit=-8,
)
BFB_DB = dict(
    pole_lookback_min=3, pole_lookback_max=10, pole_min_return=15, pole_max_red_ratio=0.4,
    flag_lookback_min=3, flag_lookback_max=10, flag_retracement_max=0.5, flag_volume_ratio=0.6,
    breakout_volume_mult=1.0, breakout_retention_minutes=0, entry_start="09:05", entry_end="14:30",
    max_breakout_extension_pct=5.0, position_ratio=0.25, max_positions=4,
    stop_loss_rate=-5, atr_period=14, atr_trail_mult=2, breakeven_promote_atr=1.5,
    max_hold_days=5, reentry_cooldown_days=3, sizing_mode="turtle", risk_pct=0.01, stop_atr=2.0,
    turtle_backstop_pct=-7.0, min_vol_floor_pct=1.0, turtle_min_stop_pct=-4.0,
    max_lot_units=2.0, max_lot_ratio_mult=2.5, market_unit_mode="enforce",
    min_market_cap=10_000_000_000, min_trade_amount=1_500_000_000, daily_loss_limit=-6,
)
PRICE_FILTER = (3_000, 500_000)      # system_config price_filter_min/max · mode HARD(전일 종가 기준)
BFB_FETCH_DAYS = 44                   # prepare: pole_max + flag_max + atr_period + 10
BFB_REQUIRED_LEN = 23                 # len(candles) > pole_max + flag_max + 2


def vcp_fetch_days(p: dict = VCP_DB) -> int:
    """``daily_fetch_depth_mode="full"`` → ema_long + base_max + 10(운영 prepare)."""
    if str(p.get("daily_fetch_depth_mode", "cap100")).strip().lower() == "full":
        return p["ema_long"] + p["base_max_days"] + 10
    return min(p["ema_long"] + p["base_max_days"] + 10, 100)


# ── 지표 — 운영 식(최신순 입력을 시간순 배열로) ─────────────────────────────────────────

def ops_atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, period: int = 14) -> np.ndarray:
    """운영 ``StrategyBase._atr`` — 직전 ``period`` 개 TR 단순평균(TR 은 전일 종가 필요). 봉 수 ≤ period+1 이면 0."""
    out = IND.atr_sma(h, l, c, period)
    out[: period + 1] = 0.0      # 운영: len(closes) <= period + 1 → 0.0
    return np.nan_to_num(out, nan=0.0)


def _fir_weights(n: int) -> np.ndarray:
    k = 2.0 / (n + 1)
    w = np.empty(n)
    w[0] = (1 - k) ** (n - 1)
    for j in range(1, n):
        w[j] = k * (1 - k) ** (n - 1 - j)
    return w


def fir_at(c: np.ndarray, i: int, n: int) -> float:
    """운영 ``_ema(chrono[-n:], n)`` 를 인덱스 i 에서(창 = c[i−n+1..i])."""
    seg = c[i - n + 1: i + 1]
    ema = float(seg[0])
    k = 2.0 / (n + 1)
    for v in seg[1:]:
        ema = float(v) * k + ema * (1 - k)
    return ema


# ── VCP 후보(prepare) ───────────────────────────────────────────────────────────────

def vcp_trend(c: np.ndarray, p: dict = VCP_DB) -> "tuple[np.ndarray, np.ndarray, np.ndarray]":
    """인덱스 i(= 신호 봉 D−1) 의 추세 필터. 반환 = (통과, ema50, eff_long). eff_long < 30 = 일봉 부족(제외).

    운영: avail = min(fetch_days, i+1) · eff = min(ema_long, avail − uptrend − 5) · ema_mid ≥ eff 이면
    max(ema_short+1, eff−10) · 종가 > EMAs > EMAm > EMAL(오늘) > EMAL(uptrend 일 전) — 전부 엄격.
    """
    n = len(c)
    u = p["long_ema_uptrend_days"]
    fd = vcp_fetch_days(p)
    avail = np.minimum(fd, np.arange(n) + 1)
    eff = np.minimum(p["ema_long"], avail - u - 5)
    ok = np.zeros(n, dtype=bool)
    e50 = IND.ema_fir(c, p["ema_short"])
    full = eff == p["ema_long"]
    if p["ema_mid"] < p["ema_long"]:
        em = IND.ema_fir(c, p["ema_mid"])
        el = IND.ema_fir(c, p["ema_long"])
        el_past = np.full(n, np.nan)
        el_past[u:] = el[:-u]
        with np.errstate(invalid="ignore"):
            okf = (c > e50) & (e50 > em) & (em > el) & (el > el_past)
        ok[full] = np.nan_to_num(okf[full]).astype(bool)
    for i in np.nonzero(~full & (eff >= 30))[0]:
        L = int(eff[i])
        mid = p["ema_mid"] if p["ema_mid"] < L else max(p["ema_short"] + 1, L - 10)
        if i + 1 < L + u:
            continue
        es = fir_at(c, i, p["ema_short"])
        emi = fir_at(c, i, mid)
        elt = fir_at(c, i, L)
        elp = fir_at(c, i - u, L)
        ok[i] = c[i] > es and es > emi and emi > elt and elt > elp
    eff = np.where(eff >= 30, eff, 0)
    return ok, e50, eff


def vcp_base(h: np.ndarray, l: np.ndarray, i: int, p: dict = VCP_DB) -> "tuple[int, float, float] | None":
    """운영 ``_detect_base`` — 최근 L봉(i 포함)의 최장 박스(깊이 ≤ base_depth_pct). (L, 고가, 저가) 또는 None."""
    avail = min(vcp_fetch_days(p), i + 1)
    for L in range(p["base_max_days"], p["base_min_days"] - 1, -1):
        if L > avail:
            continue
        hh = float(np.max(h[i - L + 1: i + 1]))
        ll = float(np.min(l[i - L + 1: i + 1]))
        if hh <= 0 or ll <= 0:
            continue
        if (hh - ll) / hh > p["base_depth_pct"]:
            continue
        return L, hh, ll
    return None


def vcp_base_vec(h: np.ndarray, l: np.ndarray, p: dict = VCP_DB) -> "tuple[np.ndarray, np.ndarray, np.ndarray]":
    """``vcp_base`` 를 전 인덱스에 벡터로. 반환 = (L, 고가, 저가) — L = 0 이면 베이스 없음."""
    n = len(h)
    avail = np.minimum(vcp_fetch_days(p), np.arange(n) + 1)
    Ls = np.zeros(n, dtype=np.int16)
    hh = np.full(n, np.nan)
    ll = np.full(n, np.nan)
    for L in range(p["base_max_days"], p["base_min_days"] - 1, -1):
        mx = _roll(h, L, "max")
        mn = _roll(l, L, "min")
        with np.errstate(invalid="ignore", divide="ignore"):
            ok = (L <= avail) & (mx > 0) & (mn > 0) & ~((mx - mn) / mx > p["base_depth_pct"])
        ok = np.nan_to_num(ok).astype(bool) & (Ls == 0)
        Ls[ok] = L
        hh[ok] = mx[ok]
        ll[ok] = mn[ok]
    return Ls, hh, ll


def vcp_pullbacks(c: np.ndarray, h: np.ndarray, l: np.ndarray, i: int, L: int, p: dict = VCP_DB) -> list:
    """운영 ``_check_pullback_sequence`` 의 ZigZag(베이스 L봉, 시간순). 반환 = pullback 폭 목록."""
    chrono = [float(x) for x in c[i - L + 1: i + 1]]
    hs, ls = h[i - L + 1: i + 1], l[i - L + 1: i + 1]
    n = len(chrono)
    ranges = [float(a - b) for a, b in zip(hs, ls) if a > 0 and b > 0 and a >= b]
    base_atr = (sum(ranges) / len(ranges)) if ranges else 0
    if base_atr <= 0:
        avg_close = sum(chrono) / n if n > 0 else 0
        base_atr = max(1, int(avg_close * 0.003))
    thr = max(1, base_atr * p.get("min_swing_atr_mult", 0.5))
    pbs: list = []
    if n < 2:
        return pbs
    rmax = rmin = chrono[0]
    state = "undefined"
    lph = None
    for k in range(1, n):
        px = chrono[k]
        if state == "undefined":
            if px - rmin >= thr:
                state, rmax = "up", px
            elif rmax - px >= thr:
                state, lph, rmin = "down", rmax, px
            else:
                rmax, rmin = max(rmax, px), min(rmin, px)
        elif state == "up":
            if px >= rmax:
                rmax = px
            elif rmax - px >= thr:
                lph, state, rmin = rmax, "down", px
        else:
            if px <= rmin:
                rmin = px
            elif px - rmin >= thr:
                if lph is not None and lph > rmin:
                    pbs.append((lph - rmin) / lph)
                state, rmax, lph = "up", px, None
    if state == "down" and lph is not None and lph > rmin:
        pbs.append((lph - rmin) / lph)
    return pbs


def vcp_pullback_ok(pbs: list, p: dict = VCP_DB) -> bool:
    if len(pbs) < p["pullback_count_min"] or len(pbs) > p["pullback_count_max"]:
        return False
    for a, b in zip(pbs, pbs[1:]):
        if b >= a:
            return False
    return pbs[-1] <= p["last_pullback_max"]


def vcp_volc_ok(vol: np.ndarray, i: int, L: int, p: dict = VCP_DB) -> bool:
    """운영 ``_check_volume_contraction`` — 마지막 5봉 평균 < 베이스 직전 20봉 평균 × ratio. 일봉 부족·분모 0 = 통과."""
    avail = min(vcp_fetch_days(p), i + 1)
    if avail < L + 20:
        return True
    last5 = float(np.sum(vol[i - 4: i + 1])) / 5
    pre20 = float(np.sum(vol[i - L - 19: i - L + 1])) / 20
    if pre20 <= 0:
        return True
    return last5 < pre20 * p["volume_contraction_ratio"]


def vcp_features(b: dict, p: dict = VCP_DB) -> dict:
    """종목 배열 → 인덱스 i(신호 봉) 별 후보 여부와 셋업. 가격 = 수정가(신호용)."""
    o, h, l, c, vol = b["o"], b["h"], b["l"], b["c"], b["vol"]
    n = len(c)
    trend, e50, eff = vcp_trend(c, p)
    atr = ops_atr(h, l, c, p["atr_period"])
    cand = np.zeros(n, dtype=bool)
    line = np.full(n, np.nan)
    low = np.full(n, np.nan)
    avg = np.zeros(n)
    stage = np.zeros(n, dtype=np.int8)        # 1 추세 · 2 베이스 · 3 pullback · 4 거래량 수축 · 5 ATR
    Lv, Hv, LLv = vcp_base_vec(h, l, p)
    tr = trend & (eff > 0)
    stage[tr] = 1
    for i in np.nonzero(tr & (Lv > 0))[0]:
        stage[i] = 2
        L, hh, ll = int(Lv[i]), float(Hv[i]), float(LLv[i])
        if not vcp_pullback_ok(vcp_pullbacks(c, h, l, i, L, p), p):
            continue
        stage[i] = 3
        if not vcp_volc_ok(vol, i, L, p):
            continue
        stage[i] = 4
        if atr[i] <= 0:
            continue
        stage[i] = 5
        cand[i] = True
        line[i], low[i] = hh, ll
        avg[i] = int(float(np.sum(vol[i - 19: i + 1])) / 20) if i + 1 >= 20 else 0
    return {"cand": cand, "line": line, "low": low, "avg": avg, "atr": atr, "ema50": e50, "eff": eff,
            "stage": stage, "target": np.full(n, np.nan)}


# ── BFB 후보(prepare) ───────────────────────────────────────────────────────────────

def _roll(x: np.ndarray, w: int, how: str) -> np.ndarray:
    s = pd.Series(x)
    r = s.rolling(w, min_periods=w)
    return getattr(r, how)().to_numpy()


def bfb_detect(o, h, l, c, vol, p: dict = BFB_DB) -> dict:
    """운영 ``_detect_pole_and_flag_detailed`` 를 전 인덱스에 벡터로. 인덱스 i = 최근 봉(D−1).

    조합 순서 = flag_len 오름차순(바깥) · pole_len 오름차순(안) — 처음 통과하는 조합. 반환 배열:
    found · flag_high · flag_low · pole_high · pole_start · flag_avg · fl · pl.
    """
    n = len(c)
    red = ((o > 0) & (c < o)).astype(float)
    found = np.zeros(n, dtype=bool)
    out = {k: np.full(n, np.nan) for k in ("flag_high", "flag_low", "pole_high", "pole_start", "flag_avg")}
    fl_a = np.zeros(n, dtype=np.int16)
    pl_a = np.zeros(n, dtype=np.int16)
    idx = np.arange(n)
    for fl in range(p["flag_lookback_min"], p["flag_lookback_max"] + 1):
        fh = _roll(h, fl, "max")
        flo = _roll(l, fl, "min")
        fav = _roll(vol.astype(float), fl, "sum") / fl
        for pl in range(p["pole_lookback_min"], p["pole_lookback_max"] + 1):
            j = idx - fl                                   # 폴 구간 끝(최근 쪽)
            st = idx - fl - pl + 1                         # 폴 구간 시작(가장 옛 봉)
            valid = st >= 0
            jj = np.clip(j, 0, n - 1)
            ss = np.clip(st, 0, n - 1)
            ph = _roll(h, pl, "max")[jj]
            ps = c[ss]
            rc = _roll(red, pl, "sum")[jj]
            pav = _roll(vol.astype(float), pl, "sum")[jj] / pl
            with np.errstate(invalid="ignore", divide="ignore"):
                ok = valid & (fav > 0) & (ps > 0) & (ph > 0)
                ret = (ph - ps) / ps * 100
                ok &= ~(ret < p["pole_min_return"])
                ok &= ~(rc / pl > p["pole_max_red_ratio"])
                width = ph - ps
                ok &= width > 0
                retr = (ph - flo) / width
                ok &= ~(retr > p["flag_retracement_max"])
                ok &= pav > 0
                ok &= ~(fav >= pav * p["flag_volume_ratio"])
            ok = np.nan_to_num(ok).astype(bool) & ~found
            if ok.any():
                found |= ok
                out["flag_high"][ok] = fh[ok]
                out["flag_low"][ok] = flo[ok]
                out["pole_high"][ok] = ph[ok]
                out["pole_start"][ok] = ps[ok]
                out["flag_avg"][ok] = fav[ok]
                fl_a[ok] = fl
                pl_a[ok] = pl
    out.update(found=found, fl=fl_a, pl=pl_a)
    return out


def bfb_features(b: dict, p: dict = BFB_DB) -> dict:
    o, h, l, c, vol = b["o"], b["h"], b["l"], b["c"], b["vol"]
    n = len(c)
    det = bfb_detect(o, h, l, c, vol, p)
    atr = ops_atr(h, l, c, p["atr_period"])
    enough = (np.arange(n) + 1) >= BFB_REQUIRED_LEN
    cand = det["found"] & enough & (atr > 0)
    width = det["pole_high"] - det["pole_start"]
    target = np.where(cand & (width > 0) & (det["flag_high"] > 0), det["flag_high"] + width, np.nan)
    return {"cand": cand, "line": np.where(cand, det["flag_high"], np.nan),
            "low": np.where(cand, det["flag_low"], np.nan),
            "avg": np.where(cand, np.floor(np.nan_to_num(det["flag_avg"])), 0.0),
            "atr": atr, "ema50": np.full(n, np.nan), "target": target, "fl": det["fl"], "pl": det["pl"],
            "stage": det["found"].astype(np.int8)}


# ── 신호 ───────────────────────────────────────────────────────────────────────────

@dataclass
class Sig:
    ticker: str
    ti: int          # 진입 봉(D) 종목 인덱스
    gd: int          # 진입 봉 전역 달력 인덱스
    E: float         # 체결가(수정)
    E_raw: float     # 체결가(원본, 원)
    N: float         # 진입 ATR14(수정, 전날까지)
    line: float
    low: float
    target: float
    m: float
    vol_ok: bool     # 그날 전체 거래량 ≥ 임계(룩어헤드 보고판)
    entry: str       # "gap"(시가 진입) | "cross"(장중 돌파) | "latch"(상한 위 시가 뒤 상한가로 되돌아옴)
    vol_ratio: float = float("nan")


def build_signals(bars: dict, feats: dict, m_for_day: np.ndarray, p: dict, universe: dict, *,
                  latch: bool = False, slip: float = 0.0) -> "list[Sig]":
    """후보(i) ∧ 유니버스(i) ∧ D=i+1 장중 돌파. ``universe[t]`` = 종목 배열 길이의 bool(신호 봉 기준).

    ``latch=False``(판정판) — 시가 > 추격 상한이면 진입 없음(§1.4). ``latch=True``(보고판) — 그 경우 저가가
    상한가 이하로 내려오면 상한가에 산다(운영 래치 재평가 근사).
    ``slip``(보고판) — 체결 지연: 판정판과 **같은 신호 집합**에서 체결가만 min(고가, max(시가, 돌파선 × (1+slip)))
    로 올린다(고가 조건을 더 걸면 실패 돌파가 빠지는 선택 편향이 생긴다). 운영은 누적 거래량이 임계를 넘는 순간에
    사므로 돌파선보다 높게 산다(실거래 대조 근거).
    """
    cap = float(p["max_breakout_extension_pct"])
    mult = float(p["breakout_volume_mult"])
    out = []
    for t, b in bars.items():
        f = feats[t]
        ok = f["cand"][:-1] & universe[t][:-1]
        for i in np.nonzero(ok)[0]:
            D = i + 1
            if b["di"][D] != b["di"][i] + 1 or b["notrade"][D]:
                continue
            O, H, Lw = b["o"][D], b["h"][D], b["l"][D]
            if not (O > 0) or BR.limit_up_open(O, b["c"][i]):
                continue
            line = f["line"][i]
            px = BR.breakout_fill(O, H, line, cap)
            kind = None
            if px is not None:
                if slip > 0:                       # 같은 신호 집합 — 체결가만 올린다(고가를 넘지 않게)
                    px = min(H, max(O, line * (1 + slip)))
                kind = "gap" if px <= O else "cross"
            elif latch and O > line * (1 + cap / 100.0) and Lw <= line * (1 + cap / 100.0):
                px, kind = line * (1 + cap / 100.0), "latch"
            if px is None:
                continue
            thr = int(f["avg"][i] * mult)
            vol_ok = bool(thr <= 0 or b["vol"][D] >= thr)
            mv = m_for_day[b["di"][D]]
            mv = 1.0 if (mv is None or not np.isfinite(mv)) else float(mv)
            out.append(Sig(t, int(D), int(b["di"][D]), float(px), float(px * b["raw"][D]), float(f["atr"][i]),
                           float(line), float(f["low"][i]), float(f["target"][i]), mv, vol_ok, kind,
                           float(b["vol"][D] / thr) if thr > 0 else float("nan")))
    out.sort(key=lambda s: (s.gd, s.ticker))
    return out


# ── 포지션(봉 걷기) ─────────────────────────────────────────────────────────────────

class BPos:
    """한 랏. 가격 = 수정 기준, 원화 = k × 수정가. ``kind`` = "vcp" | "bfb". ``struct=False`` 면 구조선
    (base_low·flag_low·측정 이동 목표)을 뺀다(무작위 진입 대조군 · 그 짝 비교용)."""

    def __init__(self, sig: Sig, b: dict, f: dict, qty: int, *, kind: str, p: dict, cal,
                 mode: str = "color", struct: bool = True, on_exit=None):
        self.s, self.b, self.f, self.qty, self.kind, self.p, self.cal = sig, b, f, qty, kind, p, cal
        self.mode, self.struct, self.on_exit = mode, struct, on_exit
        self.E = sig.E
        self.hsb = sig.E
        self.eatr = sig.N
        self.be = False
        self.k = (qty * sig.E_raw / sig.E) if sig.E > 0 else 0.0
        self.cost_basis = qty * sig.E_raw
        self.exit_px = self.exit_reason = self.exit_gd = None
        self.last_px = sig.E
        self.pending = None           # 하한가 잠김으로 미룬 청산 사유
        self._ti = sig.ti
        self.min_stop = float(p.get("turtle_min_stop_pct", 0.0) or 0.0)
        self.backstop = float(p.get("turtle_backstop_pct", 0.0) or 0.0)
        self.be_mult = float(p.get("breakeven_promote_atr", 0) or 0)
        self.stop_atr = float(p.get("stop_atr", 2.0))
        self.trail = float(p["atr_trail_mult"])

    # 선 ---------------------------------------------------------------
    def _lines(self):
        E = self.E
        st = E - self.stop_atr * self.eatr
        if self.min_stop < 0:
            st = min(st, E * (1 + self.min_stop / 100.0))
        if self.be:
            st = max(st, E)
        ls = [BR.Line(st, "STOP_LOSS")]
        if self.backstop < 0:
            ls.append(BR.Line(E * (1 + self.backstop / 100.0), "STOP_LOSS"))
        if self.struct and np.isfinite(self.s.low) and self.s.low > 0:
            ls.append(BR.Line(self.s.low, "STOP_LOSS", strict=True))
        ti = self._ti
        atr = self.f["atr"][ti - 1] if ti >= 1 else 0.0
        if atr > 0:
            ls.append(BR.Line(self.hsb - atr * self.trail, "TRAILING_STOP"))
        if self.kind == "vcp":
            e = self.f["ema50"][ti - 1] if ti >= 1 else float("nan")
            if np.isfinite(e) and e > 0:
                ls.append(BR.Line(e, "TREND_EXIT", strict=True))
        return ls

    def _target(self) -> float:
        if self.kind == "bfb" and self.struct and np.isfinite(self.s.target) and self.s.target > 0:
            return self.s.target
        return float("inf")

    def _on_up(self, px: float):
        if px > self.hsb:
            self.hsb = px
        if self.be_mult > 0 and not self.be and self.hsb >= self.E + self.be_mult * self.eatr:
            self.be = True

    def _exit(self, px, reason, gd):
        self.exit_px, self.exit_reason, self.exit_gd = px, reason, gd
        if self.on_exit is not None and gd is not None:
            self.on_exit(self.s.ticker, gd)

    # 걷기 --------------------------------------------------------------
    def _walk(self, start: float, seq, gd: int, locked: bool) -> bool:
        prev = start
        tgt = self._target()
        for px in seq:
            if px > prev:
                self._on_up(px)
                if px >= tgt:
                    if locked:
                        self.pending = "TAKE_PROFIT"
                        return False
                    self._exit(max(prev, tgt), "TAKE_PROFIT", gd)
                    return True
            elif px < prev:
                trig = [ln for ln in self._lines() if BR.hits(px, ln)]
                if trig:
                    bst = BR._pick_default(trig)
                    if locked:
                        self.pending = bst.reason
                        return False
                    self._exit(min(prev, bst.price), bst.reason, gd)
                    return True
            prev = px
        return False

    def cur_ti(self, gd):
        di = self.b["di"]
        k = int(np.searchsorted(di, gd))
        return k if (k < len(di) and di[k] == gd) else None

    def data_ended(self, gd):
        return self.b["di"][-1] < gd

    def _locked(self, ti) -> bool:
        b = self.b
        return ti >= 1 and BR.locked_limit_down(b["o"][ti], b["h"][ti], b["l"][ti], b["c"][ti - 1])

    def _time_up(self, gd) -> bool:
        if self.kind != "bfb":
            return False
        days = (self.cal[gd] - self.cal[self.s.gd]).days
        return days > self.p["max_hold_days"] + 2

    def open_phase(self, ti: int, gd: int) -> bool:
        b = self.b
        if b["notrade"][ti]:
            return False
        self._ti = ti
        O = b["o"][ti]
        locked = self._locked(ti)
        if self.pending is not None:
            if locked:
                return False
            self._exit(O, self.pending, gd)
            return True
        trig = [ln for ln in self._lines() if BR.hits(O, ln)]
        if trig:
            if locked:
                self.pending = BR._pick_default(trig).reason
                return False
            self._exit(O, BR._pick_default(trig).reason, gd)
            return True
        self._on_up(O)
        if O >= self._target():
            self._exit(O, "TAKE_PROFIT", gd)
            return True
        if self._time_up(gd):
            if locked:
                self.pending = "TIME_EXIT"
                return False
            self._exit(O, "TIME_EXIT", gd)
            return True
        return False

    # 경로 모드: color(판정판) · adverse(P5 불리 — 진입 봉은 체결 뒤 저→고→종) · adverse_lit(동결본 문구 그대로 —
    # 봉 전체 시→저→고→종, 장중 돌파는 저가 뒤라 체결 뒤 고·종) · adv_entry(진입 봉만 불리) · adv_later(진입 뒤 봉만 불리)
    _BAR_ADVERSE = ("adverse", "adverse_lit", "adv_later")
    _ENTRY_ADVERSE = ("adverse", "adv_entry")

    @property
    def _bar_mode(self) -> str:
        return "adverse" if self.mode in self._BAR_ADVERSE else "color"

    def entry_seq(self) -> "tuple[float, tuple]":
        b, ti, s = self.b, self.s.ti, self.s
        O, H, L, Cc = b["o"][ti], b["h"][ti], b["l"][ti], b["c"][ti]
        em = ("adverse" if self.mode in self._ENTRY_ADVERSE else
              "lit" if self.mode == "adverse_lit" else "color")
        if s.entry == "gap":
            return O, BR.path_order(O, H, L, Cc, "color" if em == "color" else "adverse")
        if s.entry == "latch":                    # 시가에서 내려오다 상한가에서 산 뒤
            return s.E, ((L, H, Cc) if (em != "color" or Cc >= O) else (L, Cc))
        if em == "adverse":
            return s.E, (L, H, Cc)
        if em == "lit":
            return s.E, (H, Cc)
        return s.E, ((H, Cc) if Cc >= O else (H, L, Cc))

    def intraday_phase(self, ti: int, gd: int, is_entry: bool) -> bool:
        b = self.b
        if b["notrade"][ti]:
            self.last_px = b["c"][ti]
            return False
        self._ti = ti
        if self.pending is not None:
            self.last_px = b["c"][ti]
            return False
        locked = self._locked(ti)
        if is_entry:
            start, seq = self.entry_seq()
        else:
            O, H, L, Cc = b["o"][ti], b["h"][ti], b["l"][ti], b["c"][ti]
            start, seq = O, BR.path_order(O, H, L, Cc, self._bar_mode)
        if self._walk(start, seq, gd, locked):
            return True
        self.last_px = b["c"][ti]
        return False

    def value(self) -> float:
        return self.k * self.last_px


def run_path(sig: Sig, b: dict, f: dict, end_gd: int, *, kind: str, p: dict, cal, mode: str = "color",
             struct: bool = True) -> BPos:
    """자금 제약 없는 한 거래(1주 연속) — P1 모집단용."""
    ps = BPos(sig, b, f, 1, kind=kind, p=p, cal=cal, mode=mode, struct=struct)
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


def population(sigs: "list[Sig]", bars: dict, feats: dict, start_gd: int, end_gd: int, *, kind: str, p: dict,
               cal, mode: str = "color", struct: bool = True, vol_filter: bool = False) -> "list[BPos]":
    """P1 신호 모집단 — 종목마다 앞 거래 청산 + 재진입 쿨다운(``reentry_cooldown_days`` 영업일) 뒤에만 다음 진입 ·
    m ≤ 0 은 진입 없음 · 예산 무관. 쿨다운 = 청산일 gd 뒤 N 거래일까지 막힘(운영 ``cd_until >= today``)."""
    out, busy = [], {}
    cd = int(p["reentry_cooldown_days"])
    for s in sigs:
        if s.gd < start_gd or s.gd > end_gd or s.m <= 0:
            continue
        if vol_filter and not s.vol_ok:
            continue
        if busy.get(s.ticker, -1) >= s.gd:
            continue
        ps = run_path(s, bars[s.ticker], feats[s.ticker], end_gd, kind=kind, p=p, cal=cal, mode=mode,
                      struct=struct)
        busy[s.ticker] = (ps.exit_gd + cd) if ps.exit_gd is not None else 10 ** 9
        out.append(ps)
    return out


def net_ret(ps: BPos, cost_rt: float) -> float:
    return ps.exit_px / ps.E - 1 - cost_rt
