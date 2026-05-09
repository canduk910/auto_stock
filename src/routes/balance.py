"""잔고 조회 라우트: /api/balance/*"""

from __future__ import annotations

from fastapi import APIRouter

from src.api.balance import get_balance, get_buyable
from src.models.response import ApiResponse

router = APIRouter(prefix="/api/balance", tags=["balance"])


@router.get("", response_model=ApiResponse)
async def balance():
    """보유종목 + 계좌 요약을 반환한다."""
    holdings, summary = await get_balance()
    return ApiResponse(
        success=True,
        data={
            "holdings": [h.model_dump() for h in holdings],
            "summary": summary.model_dump(),
        },
    )


@router.get("/buyable", response_model=ApiResponse)
async def buyable(ticker: str = "", price: int = 0):
    """매수 가능 금액/수량을 반환한다."""
    info = await get_buyable(ticker, price)
    return ApiResponse(success=True, data=info.model_dump())
