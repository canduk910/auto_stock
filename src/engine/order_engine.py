"""주문 실행 엔진.

- 매수/매도 주문 실행 및 결과 처리
- 중복 주문 차단
- 부분 체결 관리 (PARTIAL 상태 기록, 30초 후 잔여 취소)
- 손절 부분 체결 시 잔여 재주문
- trade_history DB 기록
"""

import asyncio
import logging
import time

from src.api.balance import get_buyable, is_insufficient_cash, is_insufficient_quantity
from src.api.base import KisApiError
from src.api.order import cancel_order, place_order
from src.db.system_logs import write_log
from src.db.trade_history import insert_trade, update_trade_status
from src.engine.strategy_base import Position, Signal, StrategyBase
from src.engine.strategy_registry import StrategyRegistry
from src.engine.scanner import t
from src.models.order import OrderSide
from src.models.trade import TradeRecord, TradeStatus, TradeType

logger = logging.getLogger(__name__)

PARTIAL_FILL_WAIT = 30  # 부분 체결 후 잔여 취소 대기(초)
SELL_MAX_RETRIES = 3     # 매도 실패 시 최대 재시도 횟수
SELL_RETRY_DELAY = 1.0   # 재시도 간격(초)
BUYABLE_CACHE_TTL = 60.0  # get_buyable 캐시 유효시간(초)
BUY_BLOCK_DURATION = 900.0  # 잔고 부족 락 기본 지속(초) — 다음 잔고 sync(15분)와 정합


class OrderEngine:
    """주문 실행 엔진."""

    def __init__(self, registry: StrategyRegistry) -> None:
        self.registry = registry
        self._pending_cancel_tasks: dict[str, asyncio.Task] = {}  # ticker -> 취소 대기 태스크
        self._filled_qty: dict[str, int] = {}  # order_no -> 누적 체결 수량
        self._order_qty: dict[str, int] = {}   # order_no -> 원래 주문 수량
        self._pending_buy_orders: dict[str, dict] = {}  # order_no -> {ticker, price, quantity, strategy_id}
        self._order_strategy: dict[str, str] = {}  # order_no -> strategy_id
        self._order_ticker: dict[str, str] = {}   # order_no -> ticker (체결통보 종목코드 보정용)
        self._selling: set[str] = set()  # 매도 진행 중인 종목 (중복 매도 차단)
        # 체결통보가 place_order 응답보다 먼저 도착해 COMPLETED row를 직접 INSERT한 order_no.
        # 뒤늦게 도착한 execute_buy/execute_sell이 PENDING row를 추가 INSERT하는 것을 막기 위함.
        self._completed_orders: set[str] = set()

    async def execute_buy(self, ticker: str, current_price: int, strategy: StrategyBase) -> None:
        """매수 주문을 실행한다."""
        state = strategy.state
        if state.has_position(ticker) or state.is_buy_pending(ticker):
            logger.warning("중복 매수 차단: %s (전략: %s)", t(ticker), strategy.strategy_id)
            return
        # 전략 간 통합 가드 (race condition 대비)
        if self.registry.is_ticker_blocked_for_buy(ticker):
            logger.warning(
                "전략 간 중복 매수 차단: %s (요청 전략: %s, 다른 전략이 보유/주문중/당일매도)",
                t(ticker), strategy.strategy_id,
            )
            return

        now_ts = time.time()
        # 잔고 부족 락 — 다음 잔고 sync까지 KIS 호출 자체를 차단
        if state.is_buy_blocked(now_ts):
            logger.debug(
                "매수 차단(잔고 부족 락): %s (전략: %s, 해제 %.0fs 후)",
                t(ticker), strategy.strategy_id, state.buy_blocked_until - now_ts,
            )
            return

        # 매수가능금액 — 캐시(60초 TTL) 우선, 없으면 KIS 조회
        if state.is_buyable_cache_fresh(now_ts, BUYABLE_CACHE_TTL):
            max_buy_qty = state.cached_buyable_qty
            cache_hit = True
        else:
            try:
                buyable = await get_buyable(ticker, current_price)
            except KisApiError as e:
                if is_insufficient_cash(e):
                    state.block_buy(now_ts + BUY_BLOCK_DURATION)
                    logger.warning(
                        "매수가능조회 잔고부족 응답 → 매수 락(%ds): %s [%s] %s",
                        int(BUY_BLOCK_DURATION), strategy.strategy_id, e.msg_cd, e.msg1,
                    )
                    return
                raise
            state.cached_buyable_qty = buyable.max_buy_quantity
            state.cached_buyable_amount = buyable.max_buy_amount
            state.cached_buyable_at = now_ts
            max_buy_qty = buyable.max_buy_quantity
            cache_hit = False

        quantity = strategy.calc_buy_quantity(current_price)

        if quantity <= 0:
            logger.warning("매수 수량 0: %s (투자금: %d, 현재가: %d, 전략: %s)",
                           ticker, state.total_investment, current_price, strategy.strategy_id)
            return

        # 매수가능수량 제한
        if max_buy_qty <= 0:
            # 잔고 부족이 확정 — 다음 잔고 sync까지 락
            state.block_buy(now_ts + BUY_BLOCK_DURATION)
            logger.warning(
                "매수가능수량 0 → 매수 락(%ds): %s (전략: %s, %s)",
                int(BUY_BLOCK_DURATION), t(ticker), strategy.strategy_id,
                "캐시" if cache_hit else "KIS 조회",
            )
            return
        if quantity > max_buy_qty:
            quantity = max_buy_qty

        if quantity <= 0:
            logger.warning("최종 매수수량 0: %s", t(ticker))
            return

        state.pending_buys.add(ticker)

        try:
            result = await place_order(
                ticker=ticker,
                side=OrderSide.BUY,
                quantity=quantity,
                price=0,  # 시장가
            )

            # 주문번호 매핑 즉시 등록 — await insert_trade 진입 전 동기 영역에서 처리.
            # 시장가 즉시체결 시 체결통보가 insert_trade await 도중 도착해도 매핑이 보장된다.
            self._order_qty[result.order_no] = quantity
            self._order_strategy[result.order_no] = strategy.strategy_id
            self._order_ticker[result.order_no] = ticker
            self._pending_buy_orders[result.order_no] = {
                "ticker": ticker,
                "price": current_price,
                "quantity": quantity,
                "strategy_id": strategy.strategy_id,
            }

            # 체결통보가 응답보다 먼저 도착해 COMPLETED row가 이미 INSERT됐다면 PENDING INSERT 생략
            already_completed = result.order_no in self._completed_orders
            if already_completed:
                self._completed_orders.discard(result.order_no)
                logger.warning(
                    "매수 응답보다 체결통보 선행 — PENDING INSERT 생략: %s (주문번호: %s)",
                    t(ticker), result.order_no,
                )
            else:
                # trade_history 기록 (PENDING — 체결 전)
                record = TradeRecord(
                    ticker=ticker,
                    ticker_name=t(ticker).split("(")[0] if "(" in t(ticker) else "",
                    trade_type=TradeType.BUY,
                    price=current_price,
                    quantity=quantity,
                    status=TradeStatus.PENDING,
                    strategy=strategy.strategy_id,
                    order_no=result.order_no,
                )
                await insert_trade(record)

            logger.info("매수 주문 접수: %s %d주 @ %d (주문번호: %s, 전략: %s)",
                         t(ticker), quantity, current_price, result.order_no, strategy.strategy_id)
            # 매수 접수 직후 캐시 무효화 — 다음 매수 호출 시 fresh 조회로 가용액 재산정
            state.cached_buyable_at = 0.0

        except KisApiError as e:
            state.pending_buys.discard(ticker)
            if is_insufficient_cash(e):
                state.block_buy(time.time() + BUY_BLOCK_DURATION)
                logger.warning(
                    "매수 주문 잔고부족 → 매수 락(%ds): %s (전략: %s, [%s] %s)",
                    int(BUY_BLOCK_DURATION), t(ticker), strategy.strategy_id, e.msg_cd, e.msg1,
                )
                return
            raise
        except Exception:
            state.pending_buys.discard(ticker)
            raise

    async def execute_sell(self, ticker: str, signal: Signal, strategy_id: str) -> None:
        """매도 주문을 실행한다. 실패 시 최대 3회 재시도."""
        # 매도 진행 중 중복 차단
        if ticker in self._selling:
            logger.debug("매도 진행 중 — 중복 차단: %s", t(ticker))
            return
        self._selling.add(ticker)

        strategy = self.registry.get(strategy_id)
        if not strategy:
            logger.warning("전략 없음: %s", strategy_id)
            self._selling.discard(ticker)
            return

        pos = strategy.state.positions.get(ticker)
        if not pos:
            logger.warning("포지션 없음: %s (전략: %s)", t(ticker), strategy_id)
            self._selling.discard(ticker)
            return

        last_error: Exception | None = None
        insufficient_qty = False
        for attempt in range(1, SELL_MAX_RETRIES + 1):
            try:
                result = await place_order(
                    ticker=ticker,
                    side=OrderSide.SELL,
                    quantity=pos.quantity,
                    price=0,  # 시장가
                )

                # 주문번호 매핑 즉시 등록 — await insert_trade 진입 전 동기 영역에서 처리.
                # 시장가 즉시체결 시 체결통보가 insert_trade await 도중 도착해도 매핑이 보장된다.
                self._order_qty[result.order_no] = pos.quantity
                self._order_strategy[result.order_no] = strategy_id
                self._order_ticker[result.order_no] = ticker

                # 체결통보가 응답보다 먼저 도착해 COMPLETED row가 이미 INSERT됐다면 PENDING INSERT 생략
                if result.order_no in self._completed_orders:
                    self._completed_orders.discard(result.order_no)
                    logger.warning(
                        "매도 응답보다 체결통보 선행 — PENDING INSERT 생략: %s (주문번호: %s)",
                        t(ticker), result.order_no,
                    )
                else:
                    # trade_history 기록
                    record = TradeRecord(
                        ticker=ticker,
                        ticker_name=t(ticker).split("(")[0] if "(" in t(ticker) else "",
                        trade_type=TradeType.SELL,
                        price=pos.buy_price,
                        quantity=pos.quantity,
                        profit_loss=0,  # 체결 확정 시 계산
                        status=TradeStatus.PENDING,
                        strategy=strategy_id,
                        order_no=result.order_no,
                    )
                    await insert_trade(record)

                logger.info(
                    "%s 매도 주문 접수: %s %d주 (주문번호: %s, 전략: %s)",
                    signal.value, t(ticker), pos.quantity, result.order_no, strategy_id,
                )
                return  # 성공 — _selling은 체결통보에서 제거

            except KisApiError as e:
                last_error = e
                if is_insufficient_quantity(e):
                    # 매도가능수량 부족 — 재시도 의미 없음 (메모리 포지션이 KIS와 어긋난 상태)
                    insufficient_qty = True
                    logger.warning(
                        "매도 매도가능수량 부족 — 재시도 중단: %s (전략: %s, [%s] %s)",
                        t(ticker), strategy_id, e.msg_cd, e.msg1,
                    )
                    break
                logger.warning(
                    "매도 주문 실패 (시도 %d/%d): %s — [%s] %s",
                    attempt, SELL_MAX_RETRIES, ticker, e.msg_cd, e.msg1,
                )
                if attempt < SELL_MAX_RETRIES:
                    await asyncio.sleep(SELL_RETRY_DELAY * (2 ** (attempt - 1)))
            except Exception as e:
                last_error = e
                logger.warning(
                    "매도 주문 실패 (시도 %d/%d): %s — %s",
                    attempt, SELL_MAX_RETRIES, ticker, e,
                )
                if attempt < SELL_MAX_RETRIES:
                    await asyncio.sleep(SELL_RETRY_DELAY * (2 ** (attempt - 1)))

        # 모든 시도 실패 — 잔고부족이면 메모리 포지션 즉시 정리(스케줄러 sync로 후속 보정)
        self._selling.discard(ticker)
        if insufficient_qty:
            # KIS에 보유 수량이 없으므로 메모리 포지션도 제거. trade_history는 sync 시 보정.
            strategy.state.positions.pop(ticker, None)
            from src.db.positions import delete_position
            try:
                await delete_position(ticker)
            except Exception:
                logger.exception("잔고부족 매도 후 DB positions 삭제 실패: %s", ticker)
            await write_log(
                "WARNING",
                f"매도가능수량 부족 — 메모리 포지션 정리: {t(ticker)} (전략: {strategy_id})",
            )
            return
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
        """체결통보를 처리한다.

        매수: 체결통보 수신 시 포지션 등록 (주문 시점이 아닌 체결 시점)
        매도: 체결 수량만큼 손익 계산, 포지션 제거
        부분 체결: PARTIAL 상태 기록 + 30초 후 잔여 취소
        """
        # 주문번호로 정확한 종목코드를 조회 (체결통보의 ticker는 신뢰하지 않음)
        known_ticker = self._order_ticker.get(order_no)
        if known_ticker:
            ticker = known_ticker
        else:
            if len(ticker) != 6 or not ticker.isalnum():
                logger.warning("체결통보: 주문번호 %s 종목매핑 없음 + payload ticker 비정상(%s), 처리 불가", order_no, ticker)
                # pending_buys 잔류 방지: _pending_buy_orders에서 ticker를 찾아 제거
                pending_info = self._pending_buy_orders.pop(order_no, None)
                if pending_info:
                    sid = pending_info.get("strategy_id", "")
                    strat = self.registry.get(sid)
                    if strat:
                        strat.state.pending_buys.discard(pending_info["ticker"])
                        logger.warning("체결통보 매핑 실패 → pending_buys 제거: %s (전략: %s)", pending_info["ticker"], sid)
                return
            logger.warning("체결통보: 주문번호 %s에 대한 종목 매핑 없음, payload ticker 사용: %s", order_no, ticker)

        # 원래 주문 수량 조회
        ordered_qty = self._order_qty.get(order_no, quantity)

        # 누적 체결 수량 추적
        self._filled_qty[order_no] = self._filled_qty.get(order_no, 0) + quantity
        total_filled = self._filled_qty[order_no]

        if side == "BUY":
            await self._handle_buy_fill(ticker, order_no, price, quantity, total_filled, ordered_qty)
        elif side == "SELL":
            await self._handle_sell_fill(ticker, order_no, price, quantity, total_filled, ordered_qty)

    async def _handle_buy_fill(
        self, ticker: str, order_no: str, price: int,
        quantity: int, total_filled: int, ordered_qty: int,
    ) -> None:
        """매수 체결 처리 — 체결통보 수신 시 올바른 전략에 포지션 등록."""
        strategy_id = self._order_strategy.get(order_no, "momentum")
        strategy = self.registry.get(strategy_id)
        if not strategy:
            logger.error("체결통보: 전략 찾을 수 없음: %s (order_no: %s)", strategy_id, order_no)
            return

        state = strategy.state
        pos = state.positions.get(ticker)

        if not pos:
            # 첫 체결 → 포지션 신규 등록
            state.positions[ticker] = Position(
                ticker=ticker,
                buy_price=price,
                quantity=total_filled,
                order_no=order_no,
                strategy_id=strategy_id,
            )
            logger.info("매수 체결 → 포지션 등록: %s %d주 @ %d (전략: %s)", t(ticker), total_filled, price, strategy_id)
        else:
            # 추가 체결 (부분 체결 이후) → 수량/가격 갱신
            pos.quantity = total_filled
            pos.buy_price = price

        # pending_buys에서 제거
        state.pending_buys.discard(ticker)
        # _pending_buy_orders 정리
        self._pending_buy_orders.pop(order_no, None)

        if total_filled >= ordered_qty:
            # 전량 체결 → DB 포지션 저장
            affected = await update_trade_status(ticker, TradeType.BUY, TradeStatus.COMPLETED, strategy=strategy_id)
            if affected == 0:
                # 체결통보가 execute_buy의 insert_trade(PENDING)보다 먼저 도착한 race
                # → COMPLETED 상태로 직접 INSERT, execute_buy 측에 PENDING INSERT 생략 신호
                self._completed_orders.add(order_no)
                from src.engine.scanner import ticker_names as _tn
                await insert_trade(TradeRecord(
                    ticker=ticker,
                    ticker_name=_tn.get(ticker, ""),
                    trade_type=TradeType.BUY,
                    price=price,
                    quantity=total_filled,
                    profit_loss=0,
                    status=TradeStatus.COMPLETED,
                    strategy=strategy_id,
                    order_no=order_no,
                ))
                logger.warning(
                    "체결통보 선행 race — COMPLETED 직접 INSERT: 매수 %s (주문번호: %s)",
                    t(ticker), order_no,
                )
            from src.db.positions import save_position
            from src.engine.scanner import ticker_names
            await save_position(
                ticker=ticker, ticker_name=ticker_names.get(ticker, ""),
                buy_price=price, quantity=total_filled, order_no=order_no,
                strategy_id=strategy_id, buy_date=state.positions[ticker].buy_date,
            )
            self._filled_qty.pop(order_no, None)
            self._order_qty.pop(order_no, None)
            self._order_strategy.pop(order_no, None)
            self._order_ticker.pop(order_no, None)
            # 매수 체결 → 가용액이 변동했으므로 캐시 무효화
            state.cached_buyable_at = 0.0
            logger.info("매수 전량 체결: %s %d주 @ %d (전략: %s)", t(ticker), total_filled, price, strategy_id)
        else:
            # 부분 체결 → PARTIAL 기록, 30초 후 잔여 취소
            await update_trade_status(ticker, TradeType.BUY, TradeStatus.PARTIAL, strategy=strategy_id)
            self._schedule_cancel(ticker, order_no, ordered_qty, strategy_id)
            logger.info("매수 부분 체결: %s %d/%d주 @ %d (전략: %s)", t(ticker), total_filled, ordered_qty, price, strategy_id)

    async def _handle_sell_fill(
        self, ticker: str, order_no: str, price: int,
        quantity: int, total_filled: int, ordered_qty: int,
    ) -> None:
        """매도 체결 처리 — 올바른 전략에서 포지션 제거."""
        strategy_id = self._order_strategy.get(order_no, "momentum")
        strategy = self.registry.get(strategy_id)
        if not strategy:
            logger.error("매도 체결: 전략 찾을 수 없음: %s (order_no: %s)", strategy_id, order_no)
            self._selling.discard(ticker)
            return

        state = strategy.state
        pos = state.positions.get(ticker)
        if not pos:
            logger.warning("매도 체결: 포지션 없음 — 손익 계산 생략: %s (order_no: %s)", t(ticker), order_no)
            buy_price = price  # 손익 0으로 처리
        else:
            buy_price = pos.buy_price
        profit_loss = (price - buy_price) * quantity
        state.daily_realized_pnl += profit_loss

        if total_filled >= ordered_qty:
            # 전량 체결 → 포지션 제거 + DB 삭제 + 매도 잠금 해제 + 당일 재매수 차단
            if pos:
                del state.positions[ticker]
            state.sold_today.add(ticker)
            from src.db.positions import delete_position
            await delete_position(ticker)
            self._selling.discard(ticker)
            affected = await update_trade_status(
                ticker, TradeType.SELL, TradeStatus.COMPLETED,
                strategy=strategy_id, price=price, profit_loss=profit_loss,
            )
            if affected == 0:
                # 체결통보가 execute_sell의 insert_trade(PENDING)보다 먼저 도착한 race
                # → COMPLETED 상태로 직접 INSERT, execute_sell 측에 PENDING INSERT 생략 신호
                self._completed_orders.add(order_no)
                from src.engine.scanner import ticker_names as _tn
                await insert_trade(TradeRecord(
                    ticker=ticker,
                    ticker_name=_tn.get(ticker, ""),
                    trade_type=TradeType.SELL,
                    price=price,
                    quantity=total_filled,
                    profit_loss=profit_loss,
                    status=TradeStatus.COMPLETED,
                    strategy=strategy_id,
                    order_no=order_no,
                ))
                logger.warning(
                    "체결통보 선행 race — COMPLETED 직접 INSERT: 매도 %s (주문번호: %s, 손익: %d)",
                    t(ticker), order_no, profit_loss,
                )
            self._filled_qty.pop(order_no, None)
            self._order_qty.pop(order_no, None)
            self._order_strategy.pop(order_no, None)
            self._order_ticker.pop(order_no, None)
            logger.info("매도 전량 체결: %s %d주 @ %d (손익: %d, 전략: %s)", t(ticker), total_filled, price, profit_loss, strategy_id)
        else:
            # 부분 체결 → PARTIAL, 30초 후 잔여 취소 + 손절 시 재주문
            await update_trade_status(ticker, TradeType.SELL, TradeStatus.PARTIAL, strategy=strategy_id, price=price, profit_loss=profit_loss)
            remaining = ordered_qty - total_filled
            self._schedule_cancel_and_reorder(ticker, order_no, remaining, is_stop_loss=True)
            logger.info("매도 부분 체결: %s %d/%d주 @ %d (전략: %s)", t(ticker), total_filled, ordered_qty, price, strategy_id)

    def _schedule_cancel(self, ticker: str, order_no: str, original_qty: int, strategy_id: str = "momentum") -> None:
        """30초 후 미체결 잔량을 취소하는 태스크를 등록한다."""
        if ticker in self._pending_cancel_tasks:
            self._pending_cancel_tasks[ticker].cancel()

        async def _cancel_after_wait():
            await asyncio.sleep(PARTIAL_FILL_WAIT)
            try:
                await cancel_order(order_no, 0, cancel_all=True)
                await update_trade_status(ticker, TradeType.BUY, TradeStatus.CANCELLED, strategy=strategy_id)
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
                strategy_id = self._order_strategy.get(order_no, "momentum")
                await update_trade_status(ticker, TradeType.SELL, TradeStatus.CANCELLED, strategy=strategy_id)
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

    async def cancel_remaining(self, ticker: str, strategy_id: str) -> None:
        """미체결 잔량을 취소한다."""
        strategy = self.registry.get(strategy_id)
        if not strategy:
            return
        pos = strategy.state.positions.get(ticker)
        if not pos:
            return
        try:
            await cancel_order(pos.order_no, pos.quantity, cancel_all=True)
            logger.info("미체결 취소: %s (주문번호: %s)", t(ticker), pos.order_no)
        except Exception:
            logger.exception("미체결 취소 실패: %s", ticker)
