"""매매 관리 라우트: /api/trading/*"""

import asyncio

from fastapi import APIRouter

from src.engine.scheduler import trading_scheduler
from src.models.response import ApiResponse

router = APIRouter(prefix="/api/trading", tags=["trading"])


@router.post("/start", response_model=ApiResponse)
async def start_trading():
    """매매 프로세스를 시작한다."""
    if trading_scheduler.is_running:
        return ApiResponse(success=False, message="이미 실행 중입니다")
    asyncio.create_task(trading_scheduler.start())
    return ApiResponse(success=True, message="매매 시작")


@router.post("/stop", response_model=ApiResponse)
async def stop_trading():
    """매매 프로세스를 중지한다."""
    if not trading_scheduler.is_running:
        return ApiResponse(success=False, message="실행 중이 아닙니다")
    await trading_scheduler.stop()
    return ApiResponse(success=True, message="매매 중지")


@router.post("/restart", response_model=ApiResponse)
async def restart_trading():
    """매매 프로세스를 재기동한다 (정지 → 시작)."""
    if trading_scheduler.is_running:
        await trading_scheduler.stop()
        await asyncio.sleep(1)
    asyncio.create_task(trading_scheduler.start())
    return ApiResponse(success=True, message="매매 재기동")


@router.get("/status")
async def get_status():
    """현재 매매 상태를 반환한다."""
    return ApiResponse(success=True, data=trading_scheduler.get_status())
