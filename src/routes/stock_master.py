"""stock_master READ-ONLY 라우트 (사이클 84).

5 엔드포인트 (GET only — Q9=B 결정, L-2 AST 영구 가드):
- GET /api/stock-master/stats
- GET /api/stock-master/list
- GET /api/stock-master/scan-pool/summary
- GET /api/stock-master/{ticker}/history
- GET /api/stock-master/{ticker}

라우트 순서 의무: 정적 경로 (stats / list / scan-pool) 를 동적 ({ticker}) 보다 먼저 등록.
/{ticker}/history 도 /{ticker} 보다 먼저 등록 (FastAPI LIFO 정합).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from src.db import stock_master
from src.models.response import ApiResponse

router = APIRouter()


@router.get("/stats")
async def get_stock_master_stats():
    """stock_master 집계 — count_all / bfdy_clpr_present / nxt_tradable_count / top_10_recent."""
    data = await stock_master.get_stats()
    return ApiResponse(success=True, data=data, message="")


@router.get("/list")
async def list_stock_master(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """stock_master 페이징 list. limit ∈ [1, 1000], offset ≥ 0."""
    data = await stock_master.list_all(limit=limit, offset=offset)
    return ApiResponse(success=True, data=data, message="")


@router.get("/scan-pool/summary")
async def get_scan_pool_summary():
    """사이클 83 [scan_pool_eager_refresh] 오늘 KST 발생 카운트."""
    count = await stock_master.count_eager_refresh_today()
    return ApiResponse(
        success=True,
        data={"eager_refresh_today": count},
        message="",
    )


@router.get("/{ticker}/history")
async def get_stock_master_history(
    ticker: str,
    limit: int = Query(100, ge=1, le=1000),
):
    """ticker 별 변경 이력 (changed_at DESC). migration 032 stock_master_history 조회."""
    data = await stock_master.list_history(ticker=ticker, limit=limit)
    return ApiResponse(success=True, data=data, message="")


@router.get("/{ticker}")
async def get_stock_master_detail(ticker: str):
    """단건 조회. 미존재 시 404."""
    data = await stock_master.get(ticker)
    if data is None:
        raise HTTPException(status_code=404, detail=f"ticker={ticker} not found")
    # StockBasics → dict 변환 (model_dump 사용)
    if hasattr(data, "model_dump"):
        return ApiResponse(success=True, data=data.model_dump(), message="")
    return ApiResponse(success=True, data=dict(data), message="")
