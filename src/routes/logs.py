"""시스템 로그 라우트: /api/logs/*"""

from fastapi import APIRouter, Query

from src.db.system_logs import get_logs
from src.models.response import ApiResponse

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=ApiResponse)
async def recent_logs(
    limit: int = Query(50, ge=1, le=200),
    level: str | None = None,
):
    """최근 시스템 로그를 조회한다."""
    logs = await get_logs(limit=limit, log_level=level)
    return ApiResponse(success=True, data=logs)
