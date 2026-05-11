"""주문 실행 엔진.

- 매수/매도 주문 실행 및 결과 처리
- 중복 주문 차단
- 부분 체결 관리 (PARTIAL 상태 기록, 30초 후 잔여 취소)
- 손절 부분 체결 시 잔여 재주문
- trade_history DB 기록
"""

from __future__ import annotations

import asyncio
import logging
import time

from src.api.balance import (
    get_buyable,
    is_insufficient_cash,
    is_insufficient_quantity,
    is_market_closed_rejection,
    is_market_order_disallowed,
)
from src.engine.util.tick_size import step_up
from src.api.base import KisApiError
from src.api.order import cancel_order, place_order
from src.db.system_logs import write_log
from src.db.trade_history import insert_trade, update_trade_status
from src.engine.strategy_base import Position, Signal, StrategyBase
from src.engine.strategy_registry import StrategyRegistry
from src.engine.scanner import t
from src.models.order import OrderDivision, OrderSide
from src.models.trade import TradeRecord, TradeStatus, TradeType

logger = logging.getLogger(__name__)

PARTIAL_FILL_WAIT = 30  # 부분 체결 후 잔여 취소 대기(초)
SELL_MAX_RETRIES = 3     # 매도 실패 시 최대 재시도 횟수
SELL_RETRY_DELAY = 1.0   # 재시도 간격(초)
BUYABLE_CACHE_TTL = 60.0  # get_buyable 캐시 유효시간(초)
BUY_BLOCK_DURATION = 900.0  # 잔고 부족 락 기본 지속(초) — 다음 잔고 sync(15분)와 정합
LOW_FUNDS_COOLDOWN = 900.0  # per-ticker 매수 수량 0 cooldown — 잔고 sync(15분)와 동일 주기


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

    def _strategy_exchange(self, strategy_id: str | None) -> str:
        """전략의 exchange 파라미터(KRX/NXT/SOR) 조회. 미지정 시 KRX.

        후방호환 동기 버전 — ticker 기반 NXT 사전 차단이 필요한 호출부는
        `_strategy_exchange_async(strategy_id, ticker=...)` 사용.
        """
        if not strategy_id:
            return "KRX"
        strategy = self.registry.get(strategy_id)
        if not strategy:
            return "KRX"
        return str(strategy.config.params.get("exchange", "KRX")).upper()

    async def _strategy_exchange_async(
        self, strategy_id: str | None, *, ticker: str | None = None
    ) -> str:
        """전략 exchange + stock_master NXT 사전 차단 (Phase G, 2026-05-11).

        ticker 인자가 주어지고 `stock_master.get(ticker).nxt_tradable=False` 이면
        NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]` system_logs 1행.
        캐시 miss / KIS 오류 시 전략 기본 exchange 그대로 (보수적 fallback).
        """
        base = self._strategy_exchange(strategy_id)
        if not ticker or base == "KRX":
            return base

        try:
            from src.db import stock_master  # lazy — 단위테스트 격리 + circular import 방지

            basics = await stock_master.get(ticker)
        except Exception:  # supabase 오류 등 — 전략 기본 유지
            logger.exception("stock_master.get 실패 (전략 기본 exchange 유지): %s", ticker)
            return base

        if basics is None:
            return base  # cache miss — 보수적 fallback

        if basics.nxt_tradable:
            return base

        # nxt_tradable=False — KRX 강제 다운그레이드
        try:
            await write_log(
                "WARNING",
                f"[nxt_downgrade] {ticker} strategy={strategy_id} "
                f"from={base} to=KRX reason=nxt_not_tradable",
            )
        except Exception:
            pass  # 로그 실패는 본 흐름 보존
        return "KRX"

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
        # per-ticker 투자금 부족 cooldown — 같은 종목에서 매 틱 "매수 수량 0" 반복 차단
        if state.is_low_funds_blocked(ticker, now_ts):
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
            # per-ticker cooldown 등록 — 다음 잔고 sync 또는 LOW_FUNDS_COOLDOWN 만료까지 같은 종목 매수 시도 차단
            state.block_low_funds(ticker, now_ts + LOW_FUNDS_COOLDOWN)
            logger.warning(
                "매수 수량 0 → %ds cooldown: %s (투자금: %d, 현재가: %d, 전략: %s)",
                int(LOW_FUNDS_COOLDOWN),
                ticker, state.total_investment, current_price, strategy.strategy_id,
            )
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
        # 1주 폴백 잔여 자금 계산용 — pending_buys 와 동기 라이프사이클 (2026-05-11 P1)
        state.pending_buy_amounts[ticker] = current_price * quantity
        state.order_attempt_today += 1

        # exchange 결정 — stock_master 사전 차단 (Phase G). place_order 호출 전 await 로 완료.
        buy_exchange = await self._strategy_exchange_async(
            strategy.strategy_id, ticker=ticker
        )

        try:
            result = await place_order(
                ticker=ticker,
                side=OrderSide.BUY,
                quantity=quantity,
                price=0,  # 시장가
                exchange=buy_exchange,
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
            state.pending_buy_amounts.pop(ticker, None)
            if is_insufficient_cash(e):
                state.block_buy(time.time() + BUY_BLOCK_DURATION)
                logger.warning(
                    "매수 주문 잔고부족 → 매수 락(%ds): %s (전략: %s, [%s] %s)",
                    int(BUY_BLOCK_DURATION), t(ticker), strategy.strategy_id, e.msg_cd, e.msg1,
                )
                return
            if is_market_order_disallowed(e):
                # 시장가 거부 → 지정가 5호가 폴백 1회 (시장가 의도 보존)
                fallback_price = step_up(current_price, steps=5)
                try:
                    state.pending_buys.add(ticker)  # 폴백 진입 — 재등록
                    # 폴백 가격 기준으로 예정 금액 재등록 (시장가 경로와 동일 규약)
                    state.pending_buy_amounts[ticker] = fallback_price * quantity
                    result = await place_order(
                        ticker=ticker,
                        side=OrderSide.BUY,
                        quantity=quantity,
                        price=fallback_price,
                        order_division=OrderDivision.LIMIT,
                        exchange=buy_exchange,
                    )

                    # 매핑 즉시 등록 — await insert_trade 진입 전 동기 영역에서 처리.
                    # 시장가 경로와 동일한 순서 (루트 CLAUDE.md 안전 규칙 준수).
                    self._order_qty[result.order_no] = quantity
                    self._order_strategy[result.order_no] = strategy.strategy_id
                    self._order_ticker[result.order_no] = ticker
                    self._pending_buy_orders[result.order_no] = {
                        "ticker": ticker,
                        "price": fallback_price,
                        "quantity": quantity,
                        "strategy_id": strategy.strategy_id,
                    }

                    # 체결통보 선행 race 가드 (기존 시장가 경로 동일)
                    if result.order_no in self._completed_orders:
                        self._completed_orders.discard(result.order_no)
                        logger.warning(
                            "폴백 응답보다 체결통보 선행 — PENDING INSERT 생략: %s",
                            t(ticker),
                        )
                    else:
                        ticker_name = t(ticker).split("(")[0] if "(" in t(ticker) else ""
                        record = TradeRecord(
                            ticker=ticker,
                            ticker_name=ticker_name,
                            trade_type=TradeType.BUY,
                            price=fallback_price,
                            quantity=quantity,
                            status=TradeStatus.PENDING,
                            strategy=strategy.strategy_id,
                            order_no=result.order_no,
                        )
                        await insert_trade(record)

                    logger.warning(
                        "시장가 거부 → 지정가 5호가 폴백: %s @ %d (원인 [%s] %s)",
                        t(ticker), fallback_price, e.msg_cd, e.msg1,
                    )
                    state.cached_buyable_at = 0.0
                    return
                except KisApiError as e2:
                    state.pending_buys.discard(ticker)
                    state.pending_buy_amounts.pop(ticker, None)
                    state.block_low_funds(ticker, time.time() + LOW_FUNDS_COOLDOWN)
                    logger.error(
                        "지정가 폴백도 거부 → cooldown: %s ([%s] %s → [%s] %s)",
                        t(ticker), e.msg_cd, e.msg1, e2.msg_cd, e2.msg1,
                    )
                    return
            raise
        except Exception:
            state.pending_buys.discard(ticker)
            state.pending_buy_amounts.pop(ticker, None)
            raise

    async def execute_sell(
        self,
        ticker: str,
        signal: Signal,
        strategy_id: str,
        *,
        limit_price: int = 0,
    ) -> None:
        """매도 주문을 실행한다. 실패 시 최대 3회 재시도.

        `limit_price > 0` 이면 지정가(`ORD_DVSN=00`) 매도, 0 이면 시장가(`ORD_DVSN=01`).
        지정가는 NXT 프리 시간대 익일 청산 등에 사용된다 (P1(B) 옵션 B).
        호출자가 호가단위 정렬을 책임진다 (`src.engine.util.tick_size.step_down`).
        """
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
        # 지정가 매도 분기 (P1(B))
        order_division = (
            OrderDivision.LIMIT if limit_price > 0 else OrderDivision.MARKET
        )
        order_unpr = limit_price if limit_price > 0 else 0
        # 지정가 NXT 청산은 거래소도 NXT 로 강제 (전략 기본 exchange 무관).
        # 시장가 청산은 stock_master 사전 차단(NXT/SOR → KRX) 적용 — Phase G.
        if limit_price > 0:
            target_exchange = "NXT"
        else:
            target_exchange = await self._strategy_exchange_async(
                strategy_id, ticker=ticker
            )
        for attempt in range(1, SELL_MAX_RETRIES + 1):
            try:
                result = await place_order(
                    ticker=ticker,
                    side=OrderSide.SELL,
                    quantity=pos.quantity,
                    price=order_unpr,
                    order_division=order_division,
                    exchange=target_exchange,
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
                # 1) 장운영시간 외 거부 — 재시도 의미 없고 positions 보존해야 함.
                #    다음 거래 가능 시각(예: 09:00 KRX 시가 확정 후)에 자연 재트리거되도록.
                if is_market_closed_rejection(e):
                    logger.warning(
                        "매도 장운영시간 외 거부 — positions 보존 + 재시도 중단: %s "
                        "(전략: %s, [%s] %s)",
                        t(ticker), strategy_id, e.msg_cd, e.msg1,
                    )
                    self._selling.discard(ticker)
                    await write_log(
                        "WARNING",
                        f"매도 거부(장운영시간 외) — 포지션 보존: {t(ticker)} "
                        f"(전략: {strategy_id}, [{e.msg_cd}] {e.msg1})",
                    )
                    # 사후 보강 (Phase G): NXT 거래 불가 종목으로 추정 → stock_master 에 즉시 반영.
                    # 다음 사이클에서 _strategy_exchange_async 가 KRX 로 사전 다운그레이드.
                    # NXT 시간대(08:00~09:00, 15:30~20:00) 거부에서만 적용 — KRX 정규장 거부는 보강하지 않음.
                    try:
                        from datetime import datetime, time as _dtime
                        now_t = datetime.now().time()
                        is_nxt_window = (
                            _dtime(8, 0) <= now_t < _dtime(9, 0)
                            or _dtime(15, 30) <= now_t < _dtime(20, 0)
                        )
                        if is_nxt_window:
                            from src.db import stock_master
                            existing = await stock_master.get(ticker)
                            existing_raw = existing.raw if existing else {}
                            existing_name = existing.name if existing else ""
                            existing_excg = existing.excg_dvsn_cd if existing else ""
                            from src.models.stock import StockBasics
                            await stock_master.upsert_one(
                                StockBasics(
                                    ticker=ticker,
                                    name=existing_name,
                                    excg_dvsn_cd=existing_excg,
                                    nxt_tradable=False,
                                    krx_halted=existing.krx_halted if existing else False,
                                    admin_item=existing.admin_item if existing else False,
                                    raw=existing_raw,
                                )
                            )
                            logger.info(
                                "stock_master 사후 보강: %s nxt_tradable=False (거부 응답 기반)",
                                ticker,
                            )
                    except Exception:
                        logger.exception("stock_master 사후 보강 실패: %s", ticker)
                    return  # positions / DB 보존, 다음 trigger 대기
                # 2) 진짜 보유 부족(APBK1234 등) — 기존 동작 유지
                if is_insufficient_quantity(e):
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
                        strat.state.pending_buy_amounts.pop(pending_info["ticker"], None)
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
            state.fill_count_today += 1
            logger.info("매수 체결 → 포지션 등록: %s %d주 @ %d (전략: %s)", t(ticker), total_filled, price, strategy_id)
        else:
            # 추가 체결 (부분 체결 이후) → 수량/가격 갱신
            pos.quantity = total_filled
            pos.buy_price = price

        # pending_buys에서 제거 + 예정 금액 정리 (잔여 자금 폴백 계산용 동기 dict)
        state.pending_buys.discard(ticker)
        state.pending_buy_amounts.pop(ticker, None)
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
            try:
                await asyncio.sleep(PARTIAL_FILL_WAIT)
                await cancel_order(order_no, 0, cancel_all=True, exchange=self._strategy_exchange(strategy_id))
                await update_trade_status(ticker, TradeType.BUY, TradeStatus.CANCELLED, strategy=strategy_id)
                logger.info("부분 체결 잔여 취소: %s (주문번호: %s)", t(ticker), order_no)
            except asyncio.CancelledError:
                pass  # 새 task로 교체됨 — pop은 새 task가 관리
            except Exception:
                logger.exception("부분 체결 잔여 취소 실패: %s", ticker)
            finally:
                # cancel-replace race 방어 — 본인이 dict에 있을 때만 pop
                if self._pending_cancel_tasks.get(ticker) is asyncio.current_task():
                    self._pending_cancel_tasks.pop(ticker, None)

        self._pending_cancel_tasks[ticker] = asyncio.create_task(_cancel_after_wait())

    def _schedule_cancel_and_reorder(
        self, ticker: str, order_no: str, remaining: int, *, is_stop_loss: bool
    ) -> None:
        """30초 후 미체결 잔량을 취소하고, 손절인 경우 잔여 재주문한다."""
        if ticker in self._pending_cancel_tasks:
            self._pending_cancel_tasks[ticker].cancel()

        async def _cancel_and_reorder():
            try:
                await asyncio.sleep(PARTIAL_FILL_WAIT)
                strategy_id = self._order_strategy.get(order_no, "momentum")
                ex = self._strategy_exchange(strategy_id)
                await cancel_order(order_no, 0, cancel_all=True, exchange=ex)
                await update_trade_status(ticker, TradeType.SELL, TradeStatus.CANCELLED, strategy=strategy_id)
                logger.info("매도 잔여 취소: %s %d주", t(ticker), remaining)

                if is_stop_loss and remaining > 0:
                    # 손절 잔여분 재주문
                    await place_order(
                        ticker=ticker,
                        side=OrderSide.SELL,
                        quantity=remaining,
                        price=0,
                        exchange=ex,
                    )
                    logger.info("손절 잔여 재주문: %s %d주", t(ticker), remaining)
            except asyncio.CancelledError:
                pass  # 새 task로 교체됨 — pop은 새 task가 관리
            except Exception:
                logger.exception("매도 잔여 취소/재주문 실패: %s", ticker)
            finally:
                # cancel-replace race 방어 — 본인이 dict에 있을 때만 pop
                if self._pending_cancel_tasks.get(ticker) is asyncio.current_task():
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
            await cancel_order(pos.order_no, pos.quantity, cancel_all=True, exchange=self._strategy_exchange(strategy_id))
            logger.info("미체결 취소: %s (주문번호: %s)", t(ticker), pos.order_no)
        except Exception:
            logger.exception("미체결 취소 실패: %s", ticker)
