"""매매 실적 라우트: /api/performance/*"""

from fastapi import APIRouter

from src.db.daily_performance import get_latest_performance, get_performance
from src.models.response import ApiResponse

router = APIRouter(prefix="/api/performance", tags=["performance"])


@router.get("/summary", response_model=ApiResponse)
async def summary(strategy: str = "total"):
    """최근 30일 실적 요약. 누적은 TWR 복리, 평균은 일별 실현 수익률 평균."""
    records = await get_performance(days=30, strategy=strategy)
    if not records:
        return ApiResponse(success=True, data={
            "total_days": 0,
            "total_profit_rate": 0,
            "avg_daily_profit_rate": 0,
            "latest_asset": 0,
            "strategy": strategy,
        })

    latest = await get_latest_performance(strategy=strategy)
    cum_rate = float(latest.get("cumulative_return_rate", 0) or 0) if latest else 0.0

    daily_rates = [float(r.get("daily_profit_rate", 0) or 0) for r in records]
    avg_rate = sum(daily_rates) / len(daily_rates) if daily_rates else 0.0

    return ApiResponse(
        success=True,
        data={
            "total_days": len(records),
            "total_profit_rate": round(cum_rate, 2),
            "avg_daily_profit_rate": round(avg_rate, 2),
            "latest_asset": records[-1]["total_asset"] if records else 0,
            "strategy": strategy,
        },
    )


@router.get("/daily", response_model=ApiResponse)
async def daily(days: int = 30, strategy: str = "total"):
    """일별 실적 데이터를 반환한다.

    응답 필드:
    - daily_profit_rate: 일별 실현손익 기반 수익률(%)
    - cumulative_return_rate: TWR 복리 누적 수익률(%)
    - daily_realized_pnl: 당일 실현손익
    - net_external_cashflow: 외부 입출금 추정 (입금 +, 출금 −)
    - total_asset: 정산 시점 순자산
    - deposit: 정산 시점 예수금
    """
    records = await get_performance(days=days, strategy=strategy)
    return ApiResponse(success=True, data=records)
