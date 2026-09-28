"""종목 차트 조회 라우트 — `GET /api/stock-chart/candles` (cycle387).

정본: `_workspace/red/cycle387_stock_chart_spec.md` §1.2 · §1.5.

잔고·주문체결내역·매매손익 그리드의 행 더블클릭이 쓰는 읽기 전용 KIS 시세 조회 하나다.
서비스 호출은 **모듈 참조**로 한다(`period_chart.fetch_candle_chart(...)`) — 테스트가
`src.api.period_chart.fetch_candle_chart` 자체를 갈아끼운다(`from … import` 로 묶으면
그 seam 이 사라진다).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Query

from src.api import period_chart
from src.api.base import KisApiError
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stock-chart", tags=["stock-chart"])

_PERIOD_LABELS = {"D": "일봉", "W": "주봉", "M": "월봉"}


@router.get("/candles", response_model=ApiResponse)
async def get_candles(
    # `\d` 는 유니코드 숫자(아랍-인도·전각)도 통과시킨다 — ASCII 숫자만 받는다.
    ticker: str = Query(..., pattern=r"^[0-9]{6}$"),
    period: Literal["D", "W", "M"] = Query("D"),
    years: int = Query(5, ge=1, le=5),
) -> ApiResponse:
    """5년 이내 일/주/월봉 — 실패도 HTTP 200(`success=false`), 인자 위반만 422."""
    try:
        chart = await period_chart.fetch_candle_chart(ticker, period, years)
    except KisApiError as exc:
        logger.warning(
            "[stock_chart_error] ticker=%s period=%s stage=first_window err=%s",
            ticker, period, exc,
        )
        return ApiResponse(
            success=False,
            data=None,
            message=f"KIS 조회 실패 [{exc.msg_cd}] {exc.msg1}",
        )
    except period_chart.ChartBusyError:
        # 대기 상한 초과는 `period_chart` 가 이미 [stock_chart_busy] 로 남긴다 — 중복 기록 금지.
        return ApiResponse(
            success=False,
            data=None,
            message="다른 차트 조회가 진행 중입니다 — 잠시 후 다시 시도하세요",
        )
    except Exception as exc:  # noqa: BLE001 - 예외 문자열은 로그에만, 응답에는 싣지 않는다
        logger.warning(
            "[stock_chart_error] ticker=%s period=%s stage=unexpected err=%s",
            ticker, period, exc,
        )
        return ApiResponse(
            success=False,
            data=None,
            message="차트 조회 실패 — 서버 로그 [stock_chart_error] 확인",
        )

    data = chart.model_dump(mode="json")
    label = _PERIOD_LABELS.get(period, period)
    count = len(chart.bars)
    message: str
    if count == 0:
        message = "표시할 봉이 없습니다"
    elif chart.complete:
        message = f"{label} {count:,}개"
    else:
        message = f"{label} {count:,}개 — 일부 구간만({chart.incomplete_reason})"
    return ApiResponse(success=True, data=data, message=message)
