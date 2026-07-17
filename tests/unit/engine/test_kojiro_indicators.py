"""고지로 대순환 순수 지표 (`src/engine/kojiro_indicators.py`) 골든/회귀 테스트.

성격: 순수 함수 (DB/HTTP/시계 미접촉) → mock/freeze_time 불필요.
레퍼런스 `_workspace/kojiro_ma/kojiro/indicators.py` verbatim vendoring 검증.

## 못박는 계약
- stage_of: 6배열 매핑 + 동가(tie)→직전 스테이지 유지(None 전파).
- ema: pandas ewm(span, adjust=False).
- atr: **Wilder ewm(alpha=1/period)** ≠ 단순 rolling 평균 (손절선 정의 단일 진실원).
- enrich: 지표 컬럼 전수 + 추세 시리즈 last-bar 스테이지.
- 100봉 truncation vs full-history: EMA40 수렴으로 last-bar stage/EMA 정합(무해 증명).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.engine import kojiro_indicators as ki
from src.engine.kojiro_indicators import KojiroIndicatorConfig, atr, ema, enrich, stage_of


CFG = KojiroIndicatorConfig()


def _ohlc(closes: list[float]) -> pd.DataFrame:
    """종가 리스트 → OHLCV DataFrame (index 오름차순). high/low = close ±0.5%."""
    closes = [float(c) for c in closes]
    return pd.DataFrame({
        "open": closes,
        "high": [c * 1.005 for c in closes],
        "low": [c * 0.995 for c in closes],
        "close": closes,
        "volume": [1_000_000] * len(closes),
    })


# ── stage_of: 6배열 + 동가 ──

@pytest.mark.parametrize("s,m,l,expected", [
    (3, 2, 1, 1),  # S>M>L
    (2, 3, 1, 2),  # M>S>L
    (1, 3, 2, 3),  # M>L>S
    (1, 2, 3, 4),  # L>M>S
    (2, 1, 3, 5),  # L>S>M
    (3, 1, 2, 6),  # S>L>M
])
def test_stage_of_six_arrangements(s, m, l, expected):
    assert stage_of(s, m, l, prev_stage=None) == expected


def test_stage_of_tie_holds_prev_stage():
    # 동가(s==m) → 판별 보류 → 직전 스테이지 유지
    assert stage_of(2.0, 2.0, 1.0, prev_stage=1) == 1
    assert stage_of(2.0, 2.0, 1.0, prev_stage=None) is None
    # m==l tie
    assert stage_of(3.0, 2.0, 2.0, prev_stage=6) == 6
    # s==l tie
    assert stage_of(2.0, 3.0, 2.0, prev_stage=5) == 5


# ── ema ──

def test_ema_matches_pandas_ewm():
    s = pd.Series([10.0, 11, 12, 13, 14, 15, 16, 17, 18, 19])
    got = ema(s, 5)
    exp = s.ewm(span=5, adjust=False).mean()
    pd.testing.assert_series_equal(got, exp)


# ── atr = Wilder ewm(alpha=1/period), NOT simple mean (★ 손절선 안전성) ──

def test_atr_is_wilder_ewm_not_simple_mean():
    closes = [100 + i + (i % 3) * 2 for i in range(60)]
    df = _ohlc(closes)
    got = atr(df, period=20)

    # true range
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)

    wilder = tr.ewm(alpha=1 / 20, adjust=False).mean()
    simple = tr.rolling(20).mean()

    # kojiro ATR == Wilder ewm
    pd.testing.assert_series_equal(got, wilder)
    # 그리고 단순 rolling 평균과는 유의미하게 다름 (donchian _atr/get_atr 재사용 금지 근거)
    last_got = got.iloc[-1]
    last_simple = simple.iloc[-1]
    assert not np.isnan(last_got)
    assert abs(last_got - last_simple) > 1e-9


# ── enrich: 컬럼 전수 + 추세 last-bar stage ──

def test_enrich_produces_all_columns():
    df = _ohlc([100 + i for i in range(60)])
    out = enrich(df, CFG)
    for col in ("ema_s", "ema_m", "ema_l", "stage",
                "ema_s_up", "ema_m_up", "ema_l_up",
                "macd1", "macd2", "macd3",
                "macd1_sig", "macd2_sig", "macd3_sig",
                "band_width", "atr"):
        assert col in out.columns


def test_enrich_uptrend_last_bar_is_stage1_all_up():
    # 장기 완만 상승 → 단기>중기>장기 정배열(stage1) + 3선 우상향
    df = _ohlc([100 + i * 0.8 for i in range(120)])
    out = enrich(df, CFG)
    last = out.iloc[-1]
    assert last["ema_s"] > last["ema_m"] > last["ema_l"]
    assert last["stage"] == 1
    assert bool(last["ema_s_up"]) and bool(last["ema_m_up"]) and bool(last["ema_l_up"])
    # 종가 > EMA5 (진입 조건4)
    assert last["close"] > last["ema_s"]


def test_enrich_macd3_is_band_ema20_minus_ema40():
    df = _ohlc([100 + i * 0.5 for i in range(80)])
    out = enrich(df, CFG)
    last = out.iloc[-1]
    assert last["macd3"] == pytest.approx(last["ema_m"] - last["ema_l"])
    assert last["band_width"] == pytest.approx(abs(last["ema_m"] - last["ema_l"]))


# ── 100봉 truncation vs full-history 정합 (EMA40 수렴 무해 증명) ──

def test_100bar_truncation_last_bar_matches_full_history():
    rng = np.random.default_rng(42)
    # 250봉 랜덤워크 상승 드리프트
    steps = rng.normal(0.3, 1.5, 250).cumsum()
    closes = [100 + s for s in steps]
    full = enrich(_ohlc(closes), CFG)
    trunc = enrich(_ohlc(closes[-100:]), CFG)

    f, t = full.iloc[-1], trunc.iloc[-1]
    # EMA40 seed 잔여가중이 100봉에서 <~1% → last-bar EMA 상대오차 미미
    for col in ("ema_s", "ema_m", "ema_l"):
        assert abs(f[col] - t[col]) / abs(f[col]) < 0.01, col
    # stage 판정 동일 (경계 아닌 명확 추세)
    assert f["stage"] == t["stage"]


# ── crossed_up/down (Phase1 dormant, 존재 검증만) ──

def test_crossed_up_down_basic():
    line = pd.Series([1.0, 2.0])
    sig = pd.Series([1.5, 1.5])
    assert ki.crossed_up(line, sig) is True
    assert ki.crossed_down(pd.Series([2.0, 1.0]), pd.Series([1.5, 1.5])) is True
