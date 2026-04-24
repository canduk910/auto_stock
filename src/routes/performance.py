"""매매 실적 라우트: /api/performance/*"""

from fastapi import APIRouter

from src.db.daily_performance import get_performance
from src.models.response import ApiResponse

router = APIRouter(prefix="/api/performance", tags=["performance"])


@router.get("/summary", response_model=ApiResponse)
async def summary(strategy: str = "total"):
    """최근 30일 실적 요약을 반환한다."""
    records = await get_performance(days=30, strategy=strategy)
    if not records:
        return ApiResponse(success=True, data={
            "total_days": 0,
            "total_profit_rate": 0,
            "avg_daily_profit_rate": 0,
            "latest_asset": 0,
            "strategy": strategy,
        })

    total_rate = sum(r["daily_profit_rate"] for r in records)
    avg_rate = total_rate / len(records)

    return ApiResponse(
        success=True,
        data={
            "total_days": len(records),
            "total_profit_rate": round(total_rate, 2),
            "avg_daily_profit_rate": round(avg_rate, 2),
            "latest_asset": records[-1]["total_asset"] if records else 0,
            "strategy": strategy,
        },
    )


@router.get("/daily", response_model=ApiResponse)
async def daily(days: int = 30, strategy: str = "total"):
    """일별 실적 데이터를 반환한다."""
    records = await get_performance(days=days, strategy=strategy)
    return ApiResponse(success=True, data=records)


@router.get("/monthly", response_model=ApiResponse)
async def monthly(strategy: str = "total"):
    """월별 실적을 반환한다."""
    records = await get_performance(days=365, strategy=strategy)
    monthly_data: dict[str, list[dict]] = {}
    for r in records:
        month = r["date"][:7]  # "YYYY-MM"
        monthly_data.setdefault(month, []).append(r)

    result = []
    for month, days in sorted(monthly_data.items()):
        total_rate = sum(d["daily_profit_rate"] for d in days)
        result.append({
            "month": month,
            "trading_days": len(days),
            "total_profit_rate": round(total_rate, 2),
            "latest_asset": days[0]["total_asset"],
        })

    return ApiResponse(success=True, data=result)
