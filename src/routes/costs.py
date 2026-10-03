"""실비용 라우트: /api/costs/* (트랙 C).

- `POST /api/costs/reconcile?from=YYYY-MM-DD&to=YYYY-MM-DD` — KIS `TTTC8715R` 정산값을 가져와
  `trade_cost_daily` 에 저장한다(백필 겸용, 운영자 수동 실행). 실제 KIS 를 부른다.
- `GET /api/costs/summary?from=&to=&strategy=` — 전략별 gross·수수료·세금·net·실효 왕복 bp·슬리피지.

오류를 삼키지 않는다 — 날짜 형식·순서·범위 422 · 모의 환경 409 · KIS 거부 502 · 그 밖 500
(+`[trade_cost_route_error]`). 빈 결과로 위장하면 「비용 0」 으로 읽힌다.
`Decimal` 은 여기서 `float` 로 사영한다(pydantic v2 는 `Decimal` 을 JSON 문자열로 낸다).
인증은 최외곽 미들웨어 단일 지점이 맡는다(POST 는 리포터 스코프에서 403).
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from src.api.base import KisApiError
from src.api.trade_profit import RealEnvRequired
from src.engine import trade_cost
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/costs", tags=["costs"])

_MARKER_ERROR = "[trade_cost_route_error]"
_MAX_SPAN_DAYS = 366


def _parse_range(from_: str, to: str) -> tuple[date, date]:
    try:
        if len(from_) != 10 or len(to) != 10:
            raise ValueError
        start, end = date.fromisoformat(from_), date.fromisoformat(to)
    except ValueError:
        raise HTTPException(status_code=422, detail="from/to 는 YYYY-MM-DD 여야 한다")
    if start > end:
        raise HTTPException(status_code=422, detail="from 이 to 보다 늦다")
    if (end - start).days + 1 > _MAX_SPAN_DAYS:
        raise HTTPException(status_code=422, detail=f"기간은 {_MAX_SPAN_DAYS}일 이하")
    return start, end


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


@router.post("/reconcile")
async def reconcile_costs(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
) -> ApiResponse:
    start, end = _parse_range(from_, to)
    try:
        result = await trade_cost.reconcile(start, end)
    except RealEnvRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except KisApiError as exc:
        logger.warning("%s reconcile KIS 거부 msg_cd=%s msg1=%s", _MARKER_ERROR, exc.msg_cd, exc.msg1)
        raise HTTPException(status_code=502, detail=f"KIS 거부 [{exc.msg_cd}] {exc.msg1}")
    except Exception as exc:
        logger.warning("%s reconcile 실패: %r", _MARKER_ERROR, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="실비용 대사 실패")
    return ApiResponse(success=True, data=_plain(result), message="")


@router.get("/summary")
async def cost_summary(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    strategy: str | None = Query(None),
) -> ApiResponse:
    start, end = _parse_range(from_, to)
    try:
        result = await trade_cost.build_summary(start, end, strategy)
    except Exception as exc:
        logger.warning("%s summary 실패: %r", _MARKER_ERROR, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="실비용 요약 조회 실패")
    return ApiResponse(success=True, data=_plain(result), message="")
