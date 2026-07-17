"""지표 계산 — 대순환 분석 스테이지, 대순환 MACD, ATR.

입력은 pandas DataFrame (index: 날짜 오름차순, columns: open/high/low/close).
"""
import numpy as np
import pandas as pd

# 스테이지 정의: (단기,중기,장기)의 위→아래 배열 → 1~6
# 1: S>M>L  2: M>S>L  3: M>L>S  4: L>M>S  5: L>S>M  6: S>L>M
_STAGE_MAP = {
    ("s", "m", "l"): 1,
    ("m", "s", "l"): 2,
    ("m", "l", "s"): 3,
    ("l", "m", "s"): 4,
    ("l", "s", "m"): 5,
    ("s", "l", "m"): 6,
}


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Wilder ATR — 종목의 하루 평균 보폭."""
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def stage_of(s: float, m: float, l: float, prev_stage: int | None = None) -> int | None:
    """세 EMA 값의 배열로 스테이지 판별. 동가면 직전 스테이지 유지."""
    trio = sorted([("s", s), ("m", m), ("l", l)], key=lambda x: -x[1])
    key = tuple(name for name, _ in trio)
    if s == m or m == l or s == l:      # 동가 → 판별 보류
        return prev_stage
    return _STAGE_MAP.get(key, prev_stage)


def enrich(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """OHLC 데이터프레임에 전략에 필요한 모든 지표 컬럼을 추가."""
    out = df.copy()
    out["ema_s"] = ema(out["close"], cfg.ema_short)
    out["ema_m"] = ema(out["close"], cfg.ema_mid)
    out["ema_l"] = ema(out["close"], cfg.ema_long)

    # 스테이지 (동가 시 직전값 유지 → 순차 계산)
    stages: list = []
    prev = None
    for s, m, l in zip(out["ema_s"], out["ema_m"], out["ema_l"]):
        prev = stage_of(s, m, l, prev)
        stages.append(prev)
    out["stage"] = stages

    # 기울기 (우상향 여부)
    lb = cfg.slope_lookback
    for col in ("ema_s", "ema_m", "ema_l"):
        out[f"{col}_up"] = out[col] > out[col].shift(lb)

    # 대순환 MACD: MACD1=S-M, MACD2=S-L, MACD3(띠)=M-L + 각 9일 시그널
    out["macd1"] = out["ema_s"] - out["ema_m"]
    out["macd2"] = out["ema_s"] - out["ema_l"]
    out["macd3"] = out["ema_m"] - out["ema_l"]
    for i in (1, 2, 3):
        out[f"macd{i}_sig"] = ema(out[f"macd{i}"], cfg.macd_signal)

    out["band_width"] = (out["ema_m"] - out["ema_l"]).abs()
    out["atr"] = atr(out, cfg.atr_period)
    return out


def crossed_up(line: pd.Series, sig: pd.Series, i: int = -1) -> bool:
    """골든크로스: 직전 봉에서 line<=sig, 현재 봉에서 line>sig."""
    if len(line) < 2 or line.iloc[i] is np.nan:
        return False
    return bool(line.iloc[i - 1] <= sig.iloc[i - 1] and line.iloc[i] > sig.iloc[i])


def crossed_down(line: pd.Series, sig: pd.Series, i: int = -1) -> bool:
    return bool(line.iloc[i - 1] >= sig.iloc[i - 1] and line.iloc[i] < sig.iloc[i])
