"""매매 실적 라우트: /api/performance/*"""

from __future__ import annotations

from fastapi import APIRouter

from src.db.daily_performance import get_latest_performance, get_performance, recompute_from_trades
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
            # `float()` 필수 — `daily_performance.total_asset` 은 NUMERIC 이라 asyncpg 가
            # Decimal 로 주고, pydantic v2 는 JSON 에서 Decimal 을 **문자열**로 직렬화한다.
            # 프론트 계약은 `latest_asset: number`(`types/trading.ts`)이고 `PerformanceCard`
            # 가 `.toLocaleString('ko-KR')` 를 직접 걸어, 문자열이면 `Object.prototype` 쪽으로
            # 떨어져 천단위 구분이 사라진다. 같은 dict 의 다른 두 수치는 위에서 이미 float 다.
            "latest_asset": float(records[-1]["total_asset"] or 0) if records else 0,
            "strategy": strategy,
        },
    )


@router.post("/recompute", response_model=ApiResponse)
async def recompute():
    """trade_history 기반 daily_performance 전체 소급 재계산.

    매일 정산(_settle) 후 자동 호출되지만, 거래 내역이 보정된 경우
    수동 호출하여 즉시 반영할 수 있다. 멱등.
    """
    ok = await recompute_from_trades()
    return ApiResponse(
        success=ok,
        message="일별 실적 재계산 완료" if ok else "재계산 실패",
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
