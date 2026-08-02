"""기술적 지표 순수함수 (사이클 G Part B).

RSI(상대강도지수) / 상대강도(RS) 전용 순수함수. DB/HTTP/시계 미접촉
(quant_score.py / kojiro_indicators.py 선례 — 매매 안전성 8영역 미접촉).

⚠️ kojiro_indicators.py 의 ema/atr 재사용 금지 — 그 ATR 은 kojiro 대순환
정체성(Wilder ewm(1/20))이라 손절선 단일 진실원. 본 모듈은 RSI/RS 전용
독립 정의로, VB 진입 품질 관찰(사이클 G Part B) 및 향후 실배제에 사용.

시리즈는 시간 오름차순(ASC, 과거→최신) 을 기대한다. get_recent_daily 는
DESC(최신 먼저) 반환이므로 호출자가 역순 변환 후 전달할 것.
"""

from __future__ import annotations

from typing import Optional, Sequence


def rsi(closes: Optional[Sequence[float]], period: int = 14) -> Optional[float]:
    """Wilder RSI. 데이터 부족(len < period+1) 시 None.

    - 전 구간 상승(avg_loss=0, avg_gain>0) → 100.0
    - 전 구간 하락(avg_gain=0) → 0.0
    - 완전 평탄(둘 다 0) → 50.0 (중립)
    """
    if closes is None:
        return None
    try:
        vals = [float(c) for c in closes]
    except (TypeError, ValueError):
        return None
    if len(vals) < period + 1:
        return None

    deltas = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    # 첫 평균 = 최초 period 개 delta 의 단순 평균 (Wilder 초기값)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    # 나머지는 Wilder 평활 (prev*(period-1) + cur) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    if avg_gain == 0:
        return 0.0
    rs_ratio = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs_ratio)


def relative_strength(
    stock_closes: Optional[Sequence[float]],
    index_closes: Optional[Sequence[float]],
    period: int = 20,
) -> Optional[float]:
    """종목 N일 수익률 − 지수 N일 수익률 (%p). 클수록 지수 대비 강세.

    데이터 부족(len < period+1) 또는 분모 0 시 None. 양수=지수 초과(강세),
    음수=지수 미달(약세). 오닐/미너비니 돌파 선도주 판별 근거.
    """
    if stock_closes is None or index_closes is None:
        return None
    try:
        s = [float(c) for c in stock_closes]
        ix = [float(c) for c in index_closes]
    except (TypeError, ValueError):
        return None
    if len(s) < period + 1 or len(ix) < period + 1:
        return None

    s_base = s[-1 - period]
    ix_base = ix[-1 - period]
    if s_base == 0 or ix_base == 0:
        return None
    s_ret = (s[-1] - s_base) / s_base
    ix_ret = (ix[-1] - ix_base) / ix_base
    return (s_ret - ix_ret) * 100.0
