"""시스템 로그 라우트: /api/logs/*

사이클 6 (2026-05-17) — 기간 필터 + 페이징.
사이클 6 통합 (2026-05-20) — `/api/logs/search` 키워드 검색 추가.

- 기존 ``?limit=50&level=ERROR`` 하위 호환 보존
- ``?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD`` KST 기간 필터
- ``?page=N&size=M`` (1-base, size 1~200)
- 응답 ``data`` 는 ``{items, total, total_pages}`` dict

검색:
- ``GET /api/logs/search?q=...&level=...&start=...&end=...&limit=N`` — ILIKE substring 매칭
- 응답 ``data`` 는 ``{logs, total, has_more}`` dict

검증:
- ``from_date > to_date`` → 422 (자동 swap 안 함, 운영자 오타 보호)
- ``page < 1`` 또는 ``size`` 범위 외 → 422
- 검색 ``q`` 빈 문자열 → 422
- ``limit`` 1~1000 외 → 422
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.db.system_logs import get_logs, search_logs
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


@router.get("/search", response_model=ApiResponse)
async def search(
    q: str = Query(..., min_length=1, description="검색 키워드 (ILIKE substring, 대소문자 무시)"),
    level: str | None = Query(None, description="등급 필터 (INFO/WARNING/ERROR/CRITICAL/ALL)"),
    start: str | None = Query(None, description="시작 시각 ISO 8601 (예: 2026-05-19T00:00:00+09:00)"),
    end: str | None = Query(None, description="종료 시각 ISO 8601"),
    limit: int = Query(200, ge=1, le=1000, description="최대 행 수 (기본 200, 최대 1000)"),
):
    """시스템 로그 키워드 검색 (사이클 6 통합, 2026-05-20).

    응답: ``{logs: [...], total: int, has_more: bool}``
    """
    payload = await search_logs(q, level=level, start=start, end=end, limit=limit)
    return ApiResponse(success=True, data=payload)
