"""거래 내역 라우트: /api/history/*"""

from fastapi import APIRouter, Query

from src.db.trade_history import get_trades
from src.models.response import ApiResponse

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=ApiResponse)
async def trade_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    ticker: str | None = None,
):
    """거래 내역을 페이징 조회한다."""
    offset = (page - 1) * size
    trades, total = await get_trades(limit=size, offset=offset, ticker=ticker)
    return ApiResponse(
        success=True,
        data={
            "trades": trades,
            "page": page,
            "size": size,
            "total": total,
            "total_pages": (total + size - 1) // size if size > 0 else 0,
        },
    )
