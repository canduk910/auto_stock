"""cycle446 — 청산 AI 섀도 지표 함수. `src/engine/llm_features.py` 에서 **복사**한 순수 함수
(`ema`·`rsi_wilder`·`macd`·`atr_wilder`·`hv_annualized`·`channel`·`compute_technicals`)만
담는다. 공용 패키지로 빼지 않는 이유 = 설계 §4.1(backend Dockerfile COPY 를 바꾸면 full
배포가 된다). 대신 backend 쪽 테스트(`tests/unit/engine/test_cycle446_feature_parity.py`)
가 같은 고정 입력에 두 구현을 넣어 값이 같은지 대조한다(드리프트 덫).

이 모듈은 **순수 함수만** 담는다 — `src.*`·`lw.*` 그 밖 import 0, I/O 0, `await` 0.

## 규약(`src/engine/llm_features.py` docstring 그대로, byte 동일 유지 의무)

1. EMA — 첫 `period` 값의 단순평균을 시드로 잡고 `α = 2/(period+1)` 재귀.
2. RSI — Wilder. 시드는 첫 `period` 변화량의 단순평균, 이후 `avg=(avg*(p-1)+x)/p`.
   `avg_loss==0`→100, `avg_gain==0`→0, **둘 다 0(완전 평탄)→50.0**.
3. ATR — Wilder. `TR=max(H-L,|H-C_prev|,|L-C_prev|)`, 시드는 첫 `period` TR 의 단순평균.
4. HV — 최근 `period`개 로그수익의 **표본표준편차(ddof=1)** × √252 × 100(%).
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# 안전 변환 헬퍼
# ---------------------------------------------------------------------------


def _to_float(x) -> "float | None":
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _to_int(x) -> "int | None":
    v = _to_float(x)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# EMA — 규약 1
# ---------------------------------------------------------------------------


def ema(values, period: int) -> "float | None":
    """asc(오래된→최근) `values` 의 지수이동평균. 표본 부족 시 None."""
    if period is None or period <= 0:
        return None
    try:
        vals = [float(v) for v in values]
    except (TypeError, ValueError):
        return None
    if len(vals) < period:
        return None
    result = sum(vals[:period]) / period
    alpha = 2.0 / (period + 1)
    for v in vals[period:]:
        result = result + alpha * (v - result)
    return result


# ---------------------------------------------------------------------------
# RSI — 규약 2 (Wilder)
# ---------------------------------------------------------------------------


def rsi_wilder(closes, period: int = 14) -> "float | None":
    try:
        vals = [float(c) for c in closes]
    except (TypeError, ValueError):
        return None
    if len(vals) < period + 1:
        return None
    changes = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
    seed = changes[:period]
    avg_gain = sum(max(c, 0.0) for c in seed) / period
    avg_loss = sum(max(-c, 0.0) for c in seed) / period
    for c in changes[period:]:
        gain = max(c, 0.0)
        loss = max(-c, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_gain == 0 and avg_loss == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


# ---------------------------------------------------------------------------
# MACD — 규약 1 의 EMA 합성
# ---------------------------------------------------------------------------


def macd(closes, fast: int = 12, slow: int = 26, signal: int = 9):
    """`(macd, signal, hist)` — 각 `float 또는 None`. `macd` 는 같은 파일의 `ema` 로만 합성한다."""
    try:
        vals = [float(c) for c in closes]
    except (TypeError, ValueError):
        return None, None, None
    if len(vals) < slow:
        return None, None, None

    macd_series: list[float] = []
    for i in range(slow - 1, len(vals)):
        window = vals[: i + 1]
        ema_fast = ema(window, fast)
        ema_slow = ema(window, slow)
        if ema_fast is None or ema_slow is None:
            continue
        macd_series.append(ema_fast - ema_slow)

    if not macd_series:
        return None, None, None

    macd_val = macd_series[-1]
    if len(macd_series) < signal:
        return macd_val, None, None

    signal_val = ema(macd_series, signal)
    if signal_val is None:
        return macd_val, None, None
    return macd_val, signal_val, macd_val - signal_val


# ---------------------------------------------------------------------------
# ATR — 규약 3 (Wilder TR)
# ---------------------------------------------------------------------------


def atr_wilder(highs, lows, closes, period: int = 14) -> "float | None":
    try:
        h = [float(x) for x in highs]
        low = [float(x) for x in lows]
        c = [float(x) for x in closes]
    except (TypeError, ValueError):
        return None
    n = min(len(h), len(low), len(c))
    if n < period + 1:
        return None
    trs = []
    for i in range(1, n):
        tr = max(h[i] - low[i], abs(h[i] - c[i - 1]), abs(low[i] - c[i - 1]))
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


# ---------------------------------------------------------------------------
# HV — 규약 4
# ---------------------------------------------------------------------------


def hv_annualized(closes, period: int = 20) -> "float | None":
    try:
        vals = [float(c) for c in closes]
    except (TypeError, ValueError):
        return None
    if len(vals) < period + 1:
        return None
    tail = vals[-(period + 1):]
    rets = []
    for i in range(1, len(tail)):
        try:
            if tail[i - 1] <= 0 or tail[i] <= 0:
                return None
            rets.append(math.log(tail[i] / tail[i - 1]))
        except (ValueError, ZeroDivisionError):
            return None
    if len(rets) < 2:
        return None
    mean_r = sum(rets) / len(rets)
    var = sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252) * 100.0


# ---------------------------------------------------------------------------
# 20일 채널
# ---------------------------------------------------------------------------


def channel(highs, lows, period: int = 20):
    try:
        h = [float(x) for x in highs]
        low = [float(x) for x in lows]
    except (TypeError, ValueError):
        return None, None
    if len(h) < period or len(low) < period:
        return None, None
    return max(h[-period:]), min(low[-period:])


# ---------------------------------------------------------------------------
# compute_technicals — A군 조립 (desc 입력 → 내부 반전)
# ---------------------------------------------------------------------------


def compute_technicals(bars_desc, *, current_price, today_open_won: int = 0) -> dict:
    """§3.2 A군 20필드. **never-raise** — 오염 입력은 필드별 None 으로 흡수한다."""
    out: dict = {}
    try:
        rows = list(bars_desc) if bars_desc else []
    except Exception:
        rows = []

    parsed = []
    for row in rows:
        try:
            parsed.append({
                "open": _to_float(row.get("stck_oprc")),
                "high": _to_float(row.get("stck_hgpr")),
                "low": _to_float(row.get("stck_lwpr")),
                "close": _to_float(row.get("stck_clpr")),
                "vol": _to_float(row.get("acml_vol")),
            })
        except Exception:
            parsed.append({"open": None, "high": None, "low": None, "close": None, "vol": None})

    asc = list(reversed(parsed))
    asc_closes = [p["close"] for p in asc if p["close"] is not None]
    asc_highs = [p["high"] for p in asc if p["high"] is not None]
    asc_lows = [p["low"] for p in asc if p["low"] is not None]

    out["ema5_won"] = ema(asc_closes, 5)
    out["ema10_won"] = ema(asc_closes, 10)
    out["ema20_won"] = ema(asc_closes, 20)
    out["ema50_won"] = ema(asc_closes, 50)

    e5, e10, e20 = out["ema5_won"], out["ema10_won"], out["ema20_won"]
    if e5 is not None and e10 is not None and e20 is not None and e5 > e10 > e20:
        out["ema_stack"] = "bull"
    elif e5 is not None and e10 is not None and e20 is not None and e5 < e10 < e20:
        out["ema_stack"] = "bear"
    else:
        out["ema_stack"] = "mixed"

    out["rsi14"] = rsi_wilder(asc_closes, 14)

    m, s, h = macd(asc_closes)
    out["macd"], out["macd_signal"], out["macd_hist"] = m, s, h

    atr = atr_wilder(asc_highs, asc_lows, asc_closes, 14)
    out["atr14_won"] = atr
    try:
        last_close = asc_closes[-1] if asc_closes else None
        out["atr14_pct"] = (atr / last_close * 100.0) if (atr is not None and last_close) else None
    except Exception:
        out["atr14_pct"] = None

    out["hv20_pct"] = hv_annualized(asc_closes, 20)

    ch_hi, ch_lo = channel(asc_highs, asc_lows, 20)
    out["ch20_high_won"] = int(ch_hi) if ch_hi is not None else None
    out["ch20_low_won"] = int(ch_lo) if ch_lo is not None else None

    try:
        if ch_hi is not None and ch_lo is not None and (ch_hi - ch_lo) != 0:
            out["pos_in_ch20_pct"] = (current_price - ch_lo) / (ch_hi - ch_lo) * 100.0
        else:
            out["pos_in_ch20_pct"] = None
    except Exception:
        out["pos_in_ch20_pct"] = None

    try:
        out["above_ch20_high"] = bool(ch_hi is not None and current_price > ch_hi)
    except Exception:
        out["above_ch20_high"] = False

    try:
        out["vol_avg20_shares"] = (
            sum(p["vol"] for p in parsed[:20] if p["vol"] is not None) / 20
            if len(parsed) >= 20 else None
        )
    except Exception:
        out["vol_avg20_shares"] = None

    streak = 0
    try:
        for p in parsed:
            o, c = p["open"], p["close"]
            if o is None or c is None or not (c > o):
                break
            streak += 1
    except Exception:
        streak = 0
    out["up_days_streak"] = streak

    def _ret_pct(n: int) -> "float | None":
        try:
            if len(parsed) <= n:
                return None
            c0, cn = parsed[0]["close"], parsed[n]["close"]
            if c0 is None or not cn:
                return None
            return (c0 - cn) / cn * 100.0
        except Exception:
            return None

    out["ret5_pct"] = _ret_pct(5)
    out["ret20_pct"] = _ret_pct(20)

    try:
        p0 = parsed[0] if parsed else None
        if p0 and p0["high"] is not None and p0["low"] is not None and p0["close"]:
            out["prev_range_pct"] = (p0["high"] - p0["low"]) / p0["close"] * 100.0
        else:
            out["prev_range_pct"] = None
    except Exception:
        out["prev_range_pct"] = None

    try:
        prev_close = parsed[0]["close"] if parsed else None
        if today_open_won and prev_close:
            out["gap_open_pct"] = (today_open_won - prev_close) / prev_close * 100.0
        else:
            out["gap_open_pct"] = None
    except Exception:
        out["gap_open_pct"] = None

    return out
