"""매매 관리 라우트: /api/trading/*"""

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from src.engine.scheduler import trading_scheduler
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

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


class ManualSellRequest(BaseModel):
    ticker: str
    quantity: int


@router.post("/manual-sell", response_model=ApiResponse)
async def manual_sell(req: ManualSellRequest):
    """수동 매도 주문을 실행한다.

    자동매매와 동일하게 시장가 매도 + trade_history 기록.
    포지션이 있는 전략을 자동으로 찾아서 해당 전략으로 기록한다.
    """
    from src.api.order import place_order
    from src.models.order import OrderSide
    from src.db.trade_history import insert_trade
    from src.models.trade import TradeRecord, TradeType, TradeStatus
    from src.engine.scanner import t, ticker_names

    registry = trading_scheduler.registry

    # 포지션이 있는 전략 찾기
    strategy = registry.find_strategy_for_ticker(req.ticker)
    strategy_id = strategy.strategy_id if strategy else "momentum"
    pos = strategy.state.positions.get(req.ticker) if strategy else None
    buy_price = pos.buy_price if pos else 0

    try:
        result = await place_order(
            ticker=req.ticker,
            side=OrderSide.SELL,
            quantity=req.quantity,
            price=0,  # 시장가
        )

        # 주문 추적 매핑 등록 — `place_order` 응답 직후 동기 영역에서 수행해야
        # 시장가 즉시체결 시 체결통보가 insert_trade await 도중 도착해도
        # `_order_ticker[order_no]`가 비어있지 않다 (CLAUDE.md 안전장치 준수)
        engine = trading_scheduler.order_engine
        engine._order_qty[result.order_no] = req.quantity
        engine._order_strategy[result.order_no] = strategy_id
        engine._order_ticker[result.order_no] = req.ticker
        engine._selling.add(req.ticker)

        # trade_history 기록 (await — 위에서 이미 매핑 등록 완료)
        name = ticker_names.get(req.ticker, "")
        record = TradeRecord(
            ticker=req.ticker,
            ticker_name=name,
            trade_type=TradeType.SELL,
            price=buy_price,
            quantity=req.quantity,
            profit_loss=0,  # 체결 시 확정
            status=TradeStatus.PENDING,
            strategy=strategy_id,
            order_no=result.order_no,
        )
        await insert_trade(record)

        logger.info("수동 매도 주문 접수: %s %d주 (주문번호: %s, 전략: %s)",
                     t(req.ticker), req.quantity, result.order_no, strategy_id)

        return ApiResponse(
            success=True,
            message=f"{name or req.ticker} {req.quantity}주 매도 주문 접수 (주문번호: {result.order_no})",
        )

    except Exception as e:
        logger.error("수동 매도 실패: %s — %s", req.ticker, e)
        return ApiResponse(success=False, message=f"매도 주문 실패: {e}")
