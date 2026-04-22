"""주문 실행 엔진.

- 매수/매도 주문 실행 및 결과 처리
- 중복 주문 차단
- 부분 체결 관리 (PARTIAL 상태 기록, 30초 후 잔여 취소)
- 손절 부분 체결 시 잔여 재주문
- trade_history DB 기록
"""

import asyncio
import logging

from src.api.balance import get_buyable
from src.api.order import cancel_order, place_order
from src.db.system_logs import write_log
from src.db.trade_history import insert_trade, update_trade_status
from src.engine.strategy import (
    Position,
    Signal,
    StrategyState,
    calc_buy_quantity,
)
from src.engine.scanner import t
from src.models.order import OrderSide
from src.models.trade import TradeRecord, TradeStatus, TradeType

logger = logging.getLogger(__name__)

PARTIAL_FILL_WAIT = 30  # 부분 체결 후 잔여 취소 대기(초)
SELL_MAX_RETRIES = 3     # 매도 실패 시 최대 재시도 횟수
SELL_RETRY_DELAY = 1.0   # 재시도 간격(초)


class OrderEngine:
    """주문 실행 엔진."""

    def __init__(self, state: StrategyState) -> None:
        self.state = state
        self._pending_cancel_tasks: dict[str, asyncio.Task] = {}  # ticker -> 취소 대기 태스크
        self._filled_qty: dict[str, int] = {}  # order_no -> 누적 체결 수량
        self._order_qty: dict[str, int] = {}   # order_no -> 원래 주문 수량

    async def execute_buy(self, ticker: str, current_price: int) -> None:
        """매수 주문을 실행한다."""
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker):
            logger.warning("중복 매수 차단: %s", t(ticker))
            return

        # 매수가능금액 사전 조회
        buyable = await get_buyable(ticker, current_price)
        quantity = calc_buy_quantity(self.state.total_investment, current_price)

        if quantity <= 0:
            logger.warning("매수 수량 0: %s (투자금: %d, 현재가: %d)",
                           ticker, self.state.total_investment, current_price)
            return

        # 매수가능수량 제한
        if quantity > buyable.max_buy_quantity:
            quantity = buyable.max_buy_quantity

        self.state.pending_buys.add(ticker)

        try:
            result = await place_order(
                ticker=ticker,
                side=OrderSide.BUY,
                quantity=quantity,
                price=0,  # 시장가
            )

            # trade_history 기록
            record = TradeRecord(
                ticker=ticker,
                trade_type=TradeType.BUY,
                price=current_price,
                quantity=quantity,
                status=TradeStatus.PENDING,
            )
            await insert_trade(record)

            # 포지션 등록
            self.state.positions[ticker] = Position(
                ticker=ticker,
                buy_price=current_price,
                quantity=quantity,
                order_no=result.order_no,
            )
            self._order_qty[result.order_no] = quantity
            logger.info("매수 주문 실행: %s %d주 @ %d", t(ticker), quantity, current_price)

        finally:
            self.state.pending_buys.discard(ticker)

    async def execute_sell(self, ticker: str, signal: Signal) -> None:
        """매도 주문을 실행한다. 실패 시 최대 3회 재시도."""
        pos = self.state.positions.get(ticker)
        if not pos:
            logger.warning("포지션 없음: %s", t(ticker))
            return

        last_error: Exception | None = None
        for attempt in range(1, SELL_MAX_RETRIES + 1):
            try:
                result = await place_order(
                    ticker=ticker,
                    side=OrderSide.SELL,
                    quantity=pos.quantity,
                    price=0,  # 시장가
                )

                # trade_history 기록
                record = TradeRecord(
                    ticker=ticker,
                    trade_type=TradeType.SELL,
                    price=pos.buy_price,
                    quantity=pos.quantity,
                    profit_loss=0,  # 체결 확정 시 계산
                    status=TradeStatus.PENDING,
                )
                await insert_trade(record)

                # 포지션 제거
                self._order_qty[result.order_no] = pos.quantity
                del self.state.positions[ticker]
                logger.info(
                    "%s 매도 주문: %s %d주 (주문번호: %s)",
                    signal.value, ticker, pos.quantity, result.order_no,
                )
                return  # 성공

            except Exception as e:
                last_error = e
                logger.warning(
                    "매도 주문 실패 (시도 %d/%d): %s — %s",
                    attempt, SELL_MAX_RETRIES, ticker, e,
                )
                if attempt < SELL_MAX_RETRIES:
                    await asyncio.sleep(SELL_RETRY_DELAY * (2 ** (attempt - 1)))

        # 3회 모두 실패 — CRITICAL 레벨 기록
        error_msg = f"매도 주문 최종 실패: {ticker} {signal.value} — {last_error}"
        logger.critical(error_msg)
        await write_log("CRITICAL", error_msg)

    async def handle_execution_notice(
        self,
        ticker: str,
        order_no: str,
        side: str,
        price: int,
        quantity: int,
    ) -> None:
        """체결통보를 처리한다. 부분 체결 시 PARTIAL 상태 기록 + 30초 후 잔여 취소."""
        pos = self.state.positions.get(ticker)
        if not pos and side == "SELL":
            # 매도 체결은 포지션 삭제 후에도 수신될 수 있음
            self.state.daily_realized_pnl += price * quantity
            return
        if not pos:
            return

        # 원래 주문 수량 조회
        ordered_qty = self._order_qty.get(order_no, pos.quantity)

        # 누적 체결 수량 추적
        self._filled_qty[order_no] = self._filled_qty.get(order_no, 0) + quantity
        total_filled = self._filled_qty[order_no]

        if side == "BUY":
            pos.buy_price = price
            if total_filled >= ordered_qty:
                # 전량 체결
                await update_trade_status(ticker, TradeType.BUY, TradeStatus.COMPLETED)
                self._filled_qty.pop(order_no, None)
                self._order_qty.pop(order_no, None)
                logger.info("매수 전량 체결: %s %d주 @ %d", t(ticker), total_filled, price)
            else:
                # 부분 체결 → PARTIAL 기록, 30초 후 잔여 취소
                await update_trade_status(ticker, TradeType.BUY, TradeStatus.PARTIAL)
                pos.quantity = total_filled  # 체결된 수량으로 갱신
                self._schedule_cancel(ticker, order_no, ordered_qty)
                logger.info("매수 부분 체결: %s %d/%d주 @ %d", t(ticker), total_filled, ordered_qty, price)

        elif side == "SELL":
            profit_loss = (price - pos.buy_price) * quantity
            self.state.daily_realized_pnl += profit_loss

            if total_filled >= ordered_qty:
                # 전량 체결
                await update_trade_status(ticker, TradeType.SELL, TradeStatus.COMPLETED)
                self._filled_qty.pop(order_no, None)
                self._order_qty.pop(order_no, None)
                logger.info("매도 전량 체결: %s %d주 @ %d (손익: %d)", t(ticker), total_filled, price, profit_loss)
            else:
                # 부분 체결 → PARTIAL, 30초 후 잔여 취소 + 손절 시 재주문
                await update_trade_status(ticker, TradeType.SELL, TradeStatus.PARTIAL)
                remaining = ordered_qty - total_filled
                self._schedule_cancel_and_reorder(ticker, order_no, remaining, is_stop_loss=True)
                logger.info("매도 부분 체결: %s %d/%d주 @ %d", t(ticker), total_filled, ordered_qty, price)

    def _schedule_cancel(self, ticker: str, order_no: str, original_qty: int) -> None:
        """30초 후 미체결 잔량을 취소하는 태스크를 등록한다."""
        if ticker in self._pending_cancel_tasks:
            self._pending_cancel_tasks[ticker].cancel()

        async def _cancel_after_wait():
            await asyncio.sleep(PARTIAL_FILL_WAIT)
            try:
                await cancel_order(order_no, 0, cancel_all=True)
                await update_trade_status(ticker, TradeType.BUY, TradeStatus.CANCELLED)
                logger.info("부분 체결 잔여 취소: %s (주문번호: %s)", t(ticker), order_no)
            except Exception:
                logger.exception("부분 체결 잔여 취소 실패: %s", ticker)
            finally:
                self._pending_cancel_tasks.pop(ticker, None)

        self._pending_cancel_tasks[ticker] = asyncio.create_task(_cancel_after_wait())

    def _schedule_cancel_and_reorder(
        self, ticker: str, order_no: str, remaining: int, *, is_stop_loss: bool
    ) -> None:
        """30초 후 미체결 잔량을 취소하고, 손절인 경우 잔여 재주문한다."""
        if ticker in self._pending_cancel_tasks:
            self._pending_cancel_tasks[ticker].cancel()

        async def _cancel_and_reorder():
            await asyncio.sleep(PARTIAL_FILL_WAIT)
            try:
                await cancel_order(order_no, 0, cancel_all=True)
                await update_trade_status(ticker, TradeType.SELL, TradeStatus.CANCELLED)
                logger.info("매도 잔여 취소: %s %d주", t(ticker), remaining)

                if is_stop_loss and remaining > 0:
                    # 손절 잔여분 재주문
                    await place_order(
                        ticker=ticker,
                        side=OrderSide.SELL,
                        quantity=remaining,
                        price=0,
                    )
                    logger.info("손절 잔여 재주문: %s %d주", t(ticker), remaining)
            except Exception:
                logger.exception("매도 잔여 취소/재주문 실패: %s", ticker)
            finally:
                self._pending_cancel_tasks.pop(ticker, None)

        self._pending_cancel_tasks[ticker] = asyncio.create_task(_cancel_and_reorder())

    async def cancel_remaining(self, ticker: str) -> None:
        """미체결 잔량을 취소한다."""
        pos = self.state.positions.get(ticker)
        if not pos:
            return
        try:
            await cancel_order(pos.order_no, pos.quantity, cancel_all=True)
            logger.info("미체결 취소: %s (주문번호: %s)", t(ticker), pos.order_no)
        except Exception:
            logger.exception("미체결 취소 실패: %s", ticker)
