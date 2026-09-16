"""매매 관리 라우트: /api/trading/*"""

from __future__ import annotations

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


# `?include=` 파라미터로 응답을 슬림화 — 분리된 sub-section만 직렬화/송신
# 미지정 또는 'all' 포함 시 기존 전체 응답 (하위 호환)
_INCLUDE_KEY_MAP: dict[str, tuple[str, ...]] = {
    "system": ("running", "env", "phase", "positions", "pending_buys", "strategy"),
    "holdings": ("position_tickers", "positions_detail"),
    "orders": ("orders",),
    "scan": ("scan",),
    "strategies": ("strategies",),
}


@router.get("/status")
async def get_status(include: str = ""):
    """현재 매매 상태를 반환한다.

    `?include=system,holdings`처럼 콤마 구분 sub-section만 명시 시 응답 슬림화.
    미지정 또는 `?include=all`은 전체 응답(하위 호환).
    """
    full = trading_scheduler.get_status()
    keys = {k.strip() for k in include.split(",") if k.strip()} if include else set()

    if not keys or "all" in keys:
        return ApiResponse(success=True, data=full)

    sliced: dict = {}
    for inc in keys:
        for field in _INCLUDE_KEY_MAP.get(inc, ()):
            if field in full:
                sliced[field] = full[field]
    return ApiResponse(success=True, data=sliced)


@router.get("/positions", response_model=ApiResponse)
async def get_positions():
    """보유 포지션 상세만 반환 (BalanceTable 전용 — status 분리)."""
    full = trading_scheduler.get_status()
    return ApiResponse(success=True, data={
        "position_tickers": full.get("position_tickers", []),
        "positions_detail": full.get("positions_detail", {}),
    })


@router.get("/orders", response_model=ApiResponse)
async def get_orders():
    """주문 추적 상태만 반환 (OrderMonitor 전용)."""
    full = trading_scheduler.get_status()
    return ApiResponse(success=True, data=full.get("orders", {}))


class ManualSellRequest(BaseModel):
    ticker: str
    quantity: int


def _market_rest_note() -> str:
    """cycle295 §4-7/§9-Q3 ② — 15:30~16:00 컷의 **명시 면제** 표기.

    이 라우트의 `place_order` 는 `execute_sell` 도 `_apply_clock` 도
    `_route_exchange_by_clock` 도 거치지 않으므로 `_market_rest_gate` 에 닿는
    경로가 **구조적으로 없다**. 운영자의 수동 조작은 컷하지 않기로 했지만
    (③ `execute_sell` 위임은 행위 반경이 커서 별건 카드), 아무것도 안 적으면
    다음 사람이 "15:30~16:00 주문 0건" 판독을 하다가 이 한 건에 걸려 게이트가
    고장났다고 오진한다. 그래서 응답 message 와 로그에 면제 사실을 남긴다.

    never-raise — 판정 실패는 빈 문자열(주문 자체엔 영향 0).
    """
    try:
        from datetime import datetime

        from src.engine.order_engine import _KST_TZ, _market_rest_now

        blocked, _reason = _market_rest_now(datetime.now(_KST_TZ))
        if not blocked:
            return ""
        return (
            " ⚠️ 지금은 자동매매 휴식 구간(15:30~16:00)입니다 — "
            "수동 매도는 컷 면제라 주문이 실제로 나갑니다(cycle295 §4-7)"
        )
    except Exception:
        return ""


@router.post("/manual-sell", response_model=ApiResponse)
async def manual_sell(req: ManualSellRequest):
    """수동 매도 주문을 실행한다.

    자동매매와 동일하게 시장가 매도 + trade_history 기록.
    포지션이 있는 전략을 자동으로 찾아서 해당 전략으로 기록한다.

    🔴 cycle295 (B) **컷 면제 경로**(§4-7 · §9-Q3 ②) — 이 라우트는
    `order_engine._market_rest_gate` 를 거치지 않는다. 15:30~16:00 에 이 버튼을
    누르면 주문은 실제로 나간다(운영자의 수동 조작은 막지 않기로 한 결정).
    D+1 판독에서 그 구간 주문이 1건 나오면 **이 라우트를 먼저 본다.**

    ⚠️ 알려진 별건(cycle287 잔여, 이 사이클 범위 밖) — 16:00~20:00 KRX 애프터에
    이 버튼을 누르면 44/41 호가유형 변환도 KRX 라우팅도 없이 시장가가 나가
    APBK3013 로 거부되고, 실패 경로에 `_selling.discard` 가 없어 stale
    `_selling` 이 남는다. 처분 = §9-Q3 ③(`execute_sell` 위임) 별도 카드.
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

    # 전략의 exchange 라우팅(KRX/NXT/SOR) 반영 — 미설정 시 KRX
    exchange = "KRX"
    if strategy:
        exchange = str(strategy.config.params.get("exchange", "KRX")).upper()

    try:
        result = await place_order(
            ticker=req.ticker,
            side=OrderSide.SELL,
            quantity=req.quantity,
            price=0,  # 시장가
            exchange=exchange,
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

        rest_note = _market_rest_note()
        logger.info("수동 매도 주문 접수: %s %d주 (주문번호: %s, 전략: %s)%s",
                     t(req.ticker), req.quantity, result.order_no, strategy_id,
                     " [market_rest_manual_exempt]" if rest_note else "")

        return ApiResponse(
            success=True,
            message=(
                f"{name or req.ticker} {req.quantity}주 매도 주문 접수 "
                f"(주문번호: {result.order_no}){rest_note}"
            ),
        )

    except Exception as e:
        logger.error("수동 매도 실패: %s — %s", req.ticker, e)
        return ApiResponse(success=False, message=f"매도 주문 실패: {e}")
