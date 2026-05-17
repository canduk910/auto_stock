"""시스템 로그 라우트: /api/logs/*

사이클 6 (2026-05-17) — 기간 필터 + 페이징.

- 기존 ``?limit=50&level=ERROR`` 하위 호환 보존
- ``?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD`` KST 기간 필터
- ``?page=N&size=M`` (1-base, size 1~200)
- 응답 ``data`` 는 ``{items, total, total_pages}`` dict

검증:
- ``from_date > to_date`` → 422 (자동 swap 안 함, 운영자 오타 보호)
- ``page < 1`` 또는 ``size`` 범위 외 → 422
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.db.system_logs import get_logs
from src.models.response import ApiResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=ApiResponse)
async def recent_logs(
    limit: int = Query(50, ge=1, le=200),
    level: str | None = None,
    from_date: date | None = Query(None, description="시작일(KST). YYYY-MM-DD"),
    to_date: date | None = Query(None, description="종료일(KST). YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    size: int | None = Query(None, ge=1, le=200, description="페이지 크기(미지정 시 limit 사용)"),
):
    """시스템 로그를 조회한다 (페이징 + KST 기간 필터)."""
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status_code=422,
            detail="from_date 는 to_date 이하여야 합니다.",
        )
    payload = await get_logs(
        limit=limit,
        log_level=level,
        from_date=from_date,
        to_date=to_date,
        page=page,
        size=size,
    )
    return ApiResponse(success=True, data=payload)
