"""종목 차트 응답 모델 (cycle387) — `GET /api/stock-chart/candles`.

정본: `_workspace/red/cycle387_stock_chart_spec.md` §1.2.
`src/api/period_chart.py::fetch_candle_chart` 의 반환형이자 라우트 응답 `data` 의 계약이다.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

#: 불완전 조회의 사유 — §1.3-4 멈춤 조건 #7·#8·#9 및 #2(둘째 창 이후 예외).
IncompleteReason = Literal["call_cap", "time_budget", "window_error", "no_progress"]


class CandleBar(BaseModel):
    """OHLCV 봉 하나. 숫자 6칸은 전부 JSON 정수(문자열·float 금지, cycle266 계열)."""

    date: str
    open: int
    high: int
    low: int
    close: int
    volume: int
    amount: int


class CandleChart(BaseModel):
    """`GET /api/stock-chart/candles` 응답 `data` (필드 16개)."""

    ticker: str
    name: Optional[str] = None
    period: Literal["D", "W", "M"]
    years: int
    adjusted: bool
    market: str
    start_date: str
    end_date: str
    bars: list[CandleBar]
    complete: bool
    incomplete_reason: Optional[IncompleteReason] = None
    last_bar_provisional: bool
    dropped_bars: int
    kis_calls: int
    cached: bool
    fetched_at: str
