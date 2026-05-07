"""일일 로그 분석 리포트 라우트: /api/log-reports/*"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter

from src.db.log_reports import get_log_report, list_log_reports
from src.engine.log_analysis_engine import generate_daily_log_report
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/log-reports", tags=["log-reports"])


@router.get("", response_model=ApiResponse)
async def list_reports(days: int = 30):
    """최근 N일치 일일 로그 분석 리포트를 신규순으로 반환한다."""
    rows = await list_log_reports(days=days)
    return ApiResponse(success=True, data=rows)


@router.get("/{target_date}", response_model=ApiResponse)
async def get_report(target_date: str):
    """단일 영업일 리포트를 반환한다 (YYYY-MM-DD)."""
    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        return ApiResponse(success=False, message="날짜 형식 오류 (YYYY-MM-DD)")
    row = await get_log_report(d)
    if not row:
        return ApiResponse(success=False, message="리포트가 없습니다")
    return ApiResponse(success=True, data=row)


@router.post("/run", response_model=ApiResponse)
async def run_now():
    """수동 트리거 — 즉시 일일 로그 분석을 실행한다 (정산을 기다리지 않고 임의 시점에 호출 가능)."""
    try:
        row = await generate_daily_log_report()
    except Exception:
        logger.exception("로그 분석 수동 실행 실패")
        return ApiResponse(success=False, message="분석 실행 실패")
    if not row:
        return ApiResponse(
            success=False,
            message="분석 결과 없음(이미 오늘 리포트가 있거나 OPENAI_API_KEY 미설정)",
        )
    return ApiResponse(success=True, data=row)
