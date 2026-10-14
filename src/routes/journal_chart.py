"""거래일지 차트 — `GET /api/journal-chart` (cycle457). **읽기 전용 — 매매에 쓰지 않는다.**

사용자 요청(2026-10-15): 「매매일지에 캔들차트와 함께 전략들에서 사용하는 기술적 지표들을 표시하고
진입청산위치를 캔들차트위에 표시하고 싶어」 · 「기술적지표 계산함수를 설마 새로 만든거야? … 명백히 소스
중복아닌가」 → 지표는 **그 전략 객체의 `chart_indicators`** 가 전략이 매수·청산 판정에 쓰는 같은 함수로
계산한다. 이 라우트는 일봉을 받아 넘기고 결과를 그대로 싣는다(계산식 0).

- 일봉 = `period_chart.fetch_candle_chart(ticker, "D", 5)` — 종목 차트(`/api/stock-chart/candles`)와 같은
  조회·같은 서버 캐시(모듈 참조 호출 = 테스트 seam).
- 전략 = 엔진 레지스트리의 살아 있는 객체(지금 저장된 설정값). 없으면 지표 없이 캔들만 + 안내.
- 계산 범위 = `from`(매수일) 앞 `_WARMUP_BARS` 봉부터 끝까지(없으면 마지막 `_DEFAULT_BARS` 봉). 그 앞은 `None`.
- 계산은 `asyncio.to_thread` — 봉마다 다시 계산하는 전략(고지로 등)이 이벤트 루프(시세·주문)를 막지 않게.
- 실패는 전부 HTTP 200 + `success=false`(인자 위반만 422). 지표 계산 실패는 캔들은 그대로 내고 안내만.
"""

from __future__ import annotations

import asyncio
import logging
import math

from fastapi import APIRouter, Query

from src.api import period_chart
from src.api.base import KisApiError
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/journal-chart", tags=["journal-chart"])

_WARMUP_BARS = 150
_DEFAULT_BARS = 260
_ALLOWED_PANES = {"price", "atr", "macd"}


def _engine_strategy(strategy_id: str):
    from src.engine import scheduler as _sched

    try:
        return _sched.trading_scheduler.registry.get(strategy_id)
    except Exception:
        return None


def _start_index(bars: list[dict], from_date: str | None) -> int:
    if from_date:
        for i, b in enumerate(bars):
            if b["date"] >= from_date:
                return max(0, i - _WARMUP_BARS)
        return max(0, len(bars) - _WARMUP_BARS)
    return max(0, len(bars) - _DEFAULT_BARS)


def _clean(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 2) if math.isfinite(f) else None


def _sanitize(raw: dict, n: int) -> dict:
    """전략이 낸 결과를 응답 모양으로 — 길이가 봉 수와 다른 선·모르는 칸은 버린다(값은 고치지 않는다)."""
    series_in = raw.get("series") or {}
    lines, series = [], {}
    for line in raw.get("lines") or []:
        key = line.get("key")
        vals = series_in.get(key)
        if not isinstance(key, str) or not isinstance(vals, list) or len(vals) != n:
            continue
        pane = line.get("pane") if line.get("pane") in _ALLOWED_PANES else "price"
        lines.append({
            "key": key, "title": str(line.get("title") or key), "pane": pane,
            "tone": str(line.get("tone") or "gray"), "dashed": bool(line.get("dashed")),
        })
        series[key] = [_clean(v) for v in vals]
    notes = [str(x) for x in (raw.get("notes") or [])]
    return {"lines": lines, "series": series, "notes": notes}


@router.get("", response_model=ApiResponse)
async def get_journal_chart(
    ticker: str = Query(..., pattern=r"^[0-9]{6}$"),
    strategy: str = Query(..., min_length=1, max_length=40),
    from_date: str | None = Query(None, alias="from", pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> ApiResponse:
    try:
        chart = await period_chart.fetch_candle_chart(ticker, "D", 5)
    except KisApiError as exc:
        logger.warning("[journal_chart_error] ticker=%s stage=candles err=%s", ticker, exc)
        return ApiResponse(success=False, data=None, message=f"KIS 조회 실패 [{exc.msg_cd}] {exc.msg1}")
    except period_chart.ChartBusyError:
        return ApiResponse(success=False, data=None,
                           message="다른 차트 조회가 진행 중입니다 — 잠시 후 다시 시도하세요")
    except Exception as exc:  # noqa: BLE001 - 예외 문자열은 로그에만
        logger.warning("[journal_chart_error] ticker=%s stage=unexpected err=%s", ticker, exc)
        return ApiResponse(success=False, data=None, message="차트 조회 실패 — 서버 로그 [journal_chart_error] 확인")

    data = chart.model_dump(mode="json")
    bars = data["bars"]
    start = _start_index(bars, from_date)
    indicators = {"lines": [], "series": {}, "notes": []}
    source = "engine"
    strat = _engine_strategy(strategy)
    if strat is None:
        source = "unavailable"
        indicators["notes"].append("엔진에 이 전략이 없어 지표를 그리지 않았습니다")
    elif bars:
        try:
            raw = await asyncio.to_thread(strat.chart_indicators, bars, start)
            indicators = _sanitize(raw if isinstance(raw, dict) else {}, len(bars))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[journal_chart_error] ticker=%s strategy=%s stage=indicators err=%s",
                           ticker, strategy, exc, exc_info=True)
            source = "error"
            indicators = {"lines": [], "series": {}, "notes": ["지표 계산 실패 — 서버 로그 [journal_chart_error] 확인"]}
        if source == "engine" and not indicators["lines"]:
            indicators["notes"].append("이 전략은 일봉 차트에 그릴 지표가 없습니다")
    data.update({"strategy": strategy, "indicators": indicators, "indicator_source": source,
                 "indicator_start_index": start})
    return ApiResponse(success=True, data=data, message="")
