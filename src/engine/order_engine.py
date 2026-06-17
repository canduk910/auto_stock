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
from datetime import datetime, timedelta, timezone

from src.api.balance import (
    get_buyable,
    is_insufficient_cash,
    is_insufficient_quantity,
    is_market_closed_rejection,
    is_market_order_disallowed,
)
from src.engine.util.tick_size import step_down, step_up
from src.api.base import KisApiError
from src.api.order import cancel_order, place_order
from src.db.system_logs import write_log, safe_write_log
from src.db.trade_history import (
    insert_trade,
    update_trade_status,
    _lookup_strategy_from_trade_history,
    _update_trade_status_by_order_no,
)
from src.engine.daily_emit_cap import DailyEmitCap
from src.engine.sell_rejection import SellRejectionTracker, is_krx_main_hours, is_nxt_session_hours
from src.engine.strategy_base import Position, Signal, StrategyBase
from src.engine.strategy_registry import StrategyRegistry
from src.engine.scanner import t
from src.models.order import OrderDivision, OrderSide
from src.models.trade import TradeRecord, TradeStatus, TradeType

logger = logging.getLogger(__name__)

# KST timezone — scanner.KST_TZ 와 동일 (circular import 방지용 재정의)
_KST_TZ = timezone(timedelta(hours=9))


def _compute_next_market_open_kst(now: datetime) -> datetime:
    """now KST 기준 다음 KRX 정규시간 시작 시각 (09:00) 반환.

    now < 09:00 KST → 당일 09:00.
    now >= 09:00 KST → 다음 영업일 09:00 (주말 스킵, KIS 휴장 처리는 후속 사이클 보류).
    """
    today_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now < today_open:
        return today_open
    # 다음 영업일: 주말 스킵 (토→+2일, 일→+1일, 평일→+1일)
    next_day = now + timedelta(days=1)
    while next_day.weekday() >= 5:  # 5=토, 6=일
        next_day += timedelta(days=1)
    return next_day.replace(hour=9, minute=0, second=0, microsecond=0)


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
        # 사이클 15-A (2026-05-19) — 매도 체결 후 WS unsubscribe hook 의 pending_next_day_clear 조회 provider.
        # scheduler 가 setattr 로 주입. 기본은 빈 set 반환 (테스트/단독 사용 안전).
        self._pending_next_day_clear_provider = lambda: set()
        # 사이클 55 R-1 (2026-06-03) — SellRejectionTracker 단일 정책 객체.
        # 사이클 52 B-1 의 2 필드 (_market_closed_blocked / _market_closed_blocked_logged_today)
        # 를 통합. 호환 layer property 2개 로 기존 참조 보존.
        self._sell_rejection = SellRejectionTracker()
        # 사이클 56-C (2026-06-04) — DailyEmitCap[str] 으로 마이그레이션.
        # 사이클 54 set[str] → DailyEmitCap[str] 호환 layer 경유 (add/clear/__contains__).
        # 다운그레이드 결정 무영향, 로그만 cap. _reset_daily_state 동행 clear.
        self._nxt_downgrade_logged_today: DailyEmitCap[str] = DailyEmitCap[str]()

    # ──────────────────────────── 사이클 52 호환 layer (사이클 55 R-1)

    @property
    def _market_closed_blocked(self) -> dict[str, datetime]:
        """사이클 52 호환 — SellRejectionTracker._blocked_until 직접 노출 (is 동일성).

        기존 테스트/코드의 `_market_closed_blocked[ticker]` 직접 접근 보존.
        사이클 48 stale_tracker 패턴 답습.
        """
        return self._sell_rejection._blocked_until

    @property
    def _market_closed_blocked_logged_today(self) -> "DailyEmitCap[str]":
        """사이클 52 emit cap 호환 — SellRejectionTracker._logged_today 직접 노출.

        사이클 56-B 마이그레이션 후 DailyEmitCap[str] 반환 (set 동형 호환 layer 보유).
        """
        return self._sell_rejection._logged_today

    # ─────────────────────────────────────────────────────────────────────────

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
            # 가설 E (2026-05-12) — 캐시 miss 시 1행 INFO 로그. 본 흐름(전략 기본 유지) 영향 없음.
            await safe_write_log(
                "INFO",
                f"[stock_master_miss] ticker={ticker} strategy={strategy_id} "
                f"exchange_keep={base} reason=miss",
                fallback_debug="[stock_master_miss] write_log 실패",
            )
            return base  # cache miss — 보수적 fallback

        # 가설 E (2026-05-12) — stale 캐시 가시화 (TTL 24h 초과).
        # Codex 추가검토 4 (2026-05-12): is_stale 은 Supabase round-trip → 주문 경로에서
        # 직접 await 하면 시장가 매수/매도 latency 증가. asyncio.create_task 로 분리해
        # 본 흐름은 즉시 반환. task 예외는 내부에서 흡수.
        async def _log_stale_async(t: str, sid: str | None, exch: str) -> None:
            try:
                from src.db import stock_master as _sm
                if await _sm.is_stale(t):
                    await safe_write_log(
                        "INFO",
                        f"[stock_master_miss] ticker={t} strategy={sid} "
                        f"exchange_keep={exch} reason=stale",
                        fallback_debug="[stock_master_miss] stale 체크 실패",
                    )
            except Exception:
                logger.debug("[stock_master_miss] stale 체크 실패", exc_info=True)

        try:
            asyncio.create_task(_log_stale_async(ticker, strategy_id, base))
        except RuntimeError:
            # 이벤트 루프 없는 컨텍스트(테스트 등) — 본 흐름 보존
            logger.debug("[stock_master_miss] stale task 등록 실패", exc_info=True)

        if basics.nxt_tradable:
            return base

        # nxt_tradable=False — KRX 강제 다운그레이드
        # 사이클 54: 로그만 ticker별 1회/일 cap — 다운그레이드 결정(return "KRX")은 cap 밖
        if ticker not in self._nxt_downgrade_logged_today:
            try:
                await write_log(
                    "WARNING",
                    f"[nxt_downgrade] {ticker} strategy={strategy_id} "
                    f"from={base} to=KRX reason=nxt_not_tradable",
                )
                self._nxt_downgrade_logged_today.add(ticker)
            except Exception:
                logger.debug("[nxt_downgrade] write_log 실패", exc_info=True)
        return "KRX"

    async def execute_buy(
        self,
        ticker: str,
        current_price: int,
        strategy: StrategyBase,
        *,
        soft_multiplier: float = 1.0,
    ) -> None:
        """매수 주문을 실행한다.

        **사이클 8 (2026-05-18)** — ``soft_multiplier`` (기본 1.0):
        - risk.on_tick 이 BuyBlockState 가 SOFT 모드 + 가드 발동 시 0.5 를 전달한다.
        - calc_buy_quantity 결과에 곱하고 ``max(1, int(...))`` 로 최소 1주 보장.
        - 1.0 인 경우 기존 동작 100% 보존 (회귀 0).
        """
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

        # 사이클 8 (2026-05-18) — SOFT 모드 수량 축소.
        # multiplier=1.0 이면 no-op (회귀 보존). 1.0 미만이면 max(1, ...) 로 최소 1주 보장.
        # 본 적용은 calc_buy_quantity 의 1주 폴백 이후라 잔여 자금 검증을 거친 수량을 축소.
        if soft_multiplier < 1.0 and quantity > 0:
            adjusted = max(1, int(quantity * soft_multiplier))
            if adjusted != quantity:
                logger.info(
                    "[buy_block_soft] %s: quantity %d → %d (multiplier=%.2f, 전략=%s)",
                    t(ticker), quantity, adjusted, soft_multiplier, strategy.strategy_id,
                )
                quantity = adjusted

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

        # PR-F (P2, 2026-05-15) — NXT 프리마켓 시장가 사전 차단.
        # NXT 프리(08:00~09:00) 는 KIS 정책상 지정가만 허용. session_tracker.active 에
        # PRE_NXT 가 포함 + MAIN 미포함 + exchange in (NXT, SOR) 면 시장가 거부(APBK0918)
        # 100% 예측 → 사전에 step_up(current_price, 5) 지정가로 변환.
        #
        # PR #9 Codex P2 (2026-05-15): 08:30~09:00 동안 active={PRE_NXT, KRX_OPEN}
        # 라 exact equality `== frozenset({PRE_NXT})` 가 false 됨 → 후반 30분 NXT
        # 프리마켓 시간대에도 시장가 거부+폴백 사이클 반복하던 결함 차단.
        # membership 체크로 PRE_NXT 시간대 전체 커버. MAIN 동시 활성(09:00 이후)은 제외.
        # 결함 (운영 로그 2026-05-15 08:00:34): 064400 [APBK0918] [프리마켓] 시장가 매매 불가
        order_division = OrderDivision.MARKET
        order_price = 0
        try:
            from src.engine.session import MarketBoard, session_tracker
            active_boards = session_tracker.active
            is_pre_nxt_period = (
                MarketBoard.PRE_NXT in active_boards
                and MarketBoard.MAIN not in active_boards
            )
            if is_pre_nxt_period and buy_exchange in ("NXT", "SOR"):
                order_price = step_up(current_price, steps=5)
                order_division = OrderDivision.LIMIT
                logger.info(
                    "[market_order_preconvert_pre_nxt] ticker=%s exchange=%s "
                    "current_price=%d converted_to_limit_price=%d",
                    ticker, buy_exchange, current_price, order_price,
                )
                # pending_buy_amounts 도 변환된 가격 기준으로 동기 갱신 (1주 폴백 잔여 자금 정합성)
                state.pending_buy_amounts[ticker] = order_price * quantity
        except Exception:
            # 사전 차단 실패는 swallow — 기존 사후 폴백 분기에서 자연 회복.
            # session import / session_tracker 접근 예외가 매수 흐름 자체를 막으면 안 됨.
            logger.debug("[market_order_preconvert_pre_nxt] 사전 변환 평가 실패", exc_info=True)
            order_division = OrderDivision.MARKET
            order_price = 0

        try:
            # order_division 키워드는 MARKET 일 때 생략 가능하지만 LIMIT 일 때 명시 필수.
            place_kwargs = dict(
                ticker=ticker,
                side=OrderSide.BUY,
                quantity=quantity,
                price=order_price,
                exchange=buy_exchange,
            )
            if order_division == OrderDivision.LIMIT:
                place_kwargs["order_division"] = OrderDivision.LIMIT
            result = await place_order(**place_kwargs)

            # 주문번호 매핑 즉시 등록 — await insert_trade 진입 전 동기 영역에서 처리.
            # 시장가 즉시체결 시 체결통보가 insert_trade await 도중 도착해도 매핑이 보장된다.
            # PR-F: 사전 변환된 경우 record_price 는 변환 가격(order_price), 시장가 경로면 current_price.
            record_price = order_price if order_division == OrderDivision.LIMIT else current_price
            self._order_qty[result.order_no] = quantity
            self._order_strategy[result.order_no] = strategy.strategy_id
            self._order_ticker[result.order_no] = ticker
            self._pending_buy_orders[result.order_no] = {
                "ticker": ticker,
                "price": record_price,
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
                    price=record_price,
                    quantity=quantity,
                    status=TradeStatus.PENDING,
                    strategy=strategy.strategy_id,
                    order_no=result.order_no,
                )
                await insert_trade(record)

            logger.info("매수 주문 접수: %s %d주 @ %d (주문번호: %s, 전략: %s)",
                         t(ticker), quantity, record_price, result.order_no, strategy.strategy_id)
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

        # 사이클 55 R-1 (2026-06-03) — SellRejectionTracker 진입 게이트 위임.
        # 사이클 52 B-1 단일 TTL → 4 분류 통합 정책 객체 (2단계 TTL + 30초 TTL).
        # 진입 게이트 순서 (사이클 52 보존): selling.add → 게이트 → discard + return.
        now_kst = datetime.now(_KST_TZ)
        if self._sell_rejection.is_blocked(ticker, now_kst):
            if self._sell_rejection.should_emit_block_log(ticker):
                self._sell_rejection.mark_block_logged(ticker)
                _expiry_log = self._sell_rejection._blocked_until.get(ticker)
                await safe_write_log(
                    "INFO",
                    f"[market_closed_blocked] ticker={ticker} strategy={strategy_id} "
                    f"reason={self._sell_rejection._blocked_reason.get(ticker, '')} "
                    f"expiry={_expiry_log.isoformat() if _expiry_log else '?'}",
                    fallback_debug="[market_closed_blocked] write_log 실패",
                )
            self._selling.discard(ticker)
            return

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
                    # 사이클 55 R-1 (2026-06-03) — tracker.register_market_closed 위임.
                    # Q1 2단계 TTL: KRX 메인(09:00~15:30) = 5분, NXT 시간대 = 다음 09:00.
                    # emit cap 리셋(_logged_today.discard) 은 register_market_closed 내부에서 수행.
                    _now_kst = datetime.now(_KST_TZ)
                    self._sell_rejection.register_market_closed(
                        ticker, _now_kst, in_krx_main_hours=is_krx_main_hours(_now_kst)
                    )
                    # 사후 보강 (Phase G): NXT 거래 불가 종목으로 추정 → stock_master 에 즉시 반영.
                    # 다음 사이클에서 _strategy_exchange_async 가 KRX 로 사전 다운그레이드.
                    # NXT 시간대(08:00~09:00, 15:30~20:00) 거부에서만 적용 — KRX 정규장 거부는 보강하지 않음.
                    try:
                        from datetime import time as _dtime
                        now_t = _now_kst.time()
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
                # 2) 진짜 보유 부족(APBK1234 등) — 기존 동작 유지 + Q3 history 적재
                if is_insufficient_quantity(e):
                    insufficient_qty = True
                    logger.warning(
                        "매도 매도가능수량 부족 — 재시도 중단: %s (전략: %s, [%s] %s)",
                        t(ticker), strategy_id, e.msg_cd, e.msg1,
                    )
                    # 사이클 55 R-1 Q3 — history 적재 (차단 X: positions 제거가 자연 차단)
                    self._sell_rejection.register_insufficient_quantity(ticker, now_kst)
                    break
                # 3) 시장가 호가 불가(APBK1943 등) — 지정가 5호가 폴백 1회 (매수 패턴과 대칭).
                #    매도는 `step_down(current_price, 5)` 로 호가 깊이로 내려 체결률 확보.
                #    `limit_price>0` 인 지정가 매도에서는 이미 지정가 → 폴백 의미 없음, 기존 재시도 유지.
                #    폴백 실패 시 cooldown 등록 안 함 — 매도는 청산 의무, 다음 사이클 자연 재트리거.
                #    2026-05-11 계양전기 사례 대응 (`docs/kis/error-codes.md` 5-4절).
                if is_market_order_disallowed(e) and order_division == OrderDivision.MARKET:
                    from src.engine.scanner import ticker_prices as _ticker_prices
                    px_info = _ticker_prices.get(ticker) or {}
                    cur_price = int(px_info.get("current_price") or 0)
                    if cur_price <= 0:
                        # 현재가 미확보 — 폴백 불가, 일반 재시도 흐름으로 폴백 (매도 의무 보존)
                        logger.warning(
                            "매도 시장가 호가 불가 — 현재가 캐시 미확보로 폴백 불가, 재시도 진행: %s "
                            "(전략: %s, [%s] %s)",
                            t(ticker), strategy_id, e.msg_cd, e.msg1,
                        )
                    else:
                        fallback_price = step_down(cur_price, steps=5)
                        try:
                            fb_result = await place_order(
                                ticker=ticker,
                                side=OrderSide.SELL,
                                quantity=pos.quantity,
                                price=fallback_price,
                                order_division=OrderDivision.LIMIT,
                                exchange=target_exchange,
                            )

                            # 주문번호 매핑 즉시 등록 — await insert_trade 진입 전 동기 영역 (매수 패턴 동일).
                            self._order_qty[fb_result.order_no] = pos.quantity
                            self._order_strategy[fb_result.order_no] = strategy_id
                            self._order_ticker[fb_result.order_no] = ticker

                            # 체결통보 선행 race 가드 (매수 폴백·시장가 경로 동일 규약)
                            if fb_result.order_no in self._completed_orders:
                                self._completed_orders.discard(fb_result.order_no)
                                logger.warning(
                                    "매도 폴백 응답보다 체결통보 선행 — PENDING INSERT 생략: %s "
                                    "(주문번호: %s)",
                                    t(ticker), fb_result.order_no,
                                )
                            else:
                                record = TradeRecord(
                                    ticker=ticker,
                                    ticker_name=t(ticker).split("(")[0] if "(" in t(ticker) else "",
                                    trade_type=TradeType.SELL,
                                    price=fallback_price,
                                    quantity=pos.quantity,
                                    profit_loss=0,
                                    status=TradeStatus.PENDING,
                                    strategy=strategy_id,
                                    order_no=fb_result.order_no,
                                )
                                await insert_trade(record)

                            logger.warning(
                                "매도 시장가 거부 → 지정가 5호가 폴백: %s @ %d "
                                "(원인 [%s] %s, 주문번호: %s, 전략: %s)",
                                t(ticker), fallback_price, e.msg_cd, e.msg1,
                                fb_result.order_no, strategy_id,
                            )
                            # 사이클 55 R-1 Q2 — 폴백 성공 시에도 30초 TTL 등록 (동일 tick 폭주 차단).
                            # KRX/NXT 무관. next_day_clear_required = is_nxt AND NOT fallback_succeeded
                            # → 성공이므로 False.
                            _now_kst_fb = datetime.now(_KST_TZ)
                            self._sell_rejection.register_market_order_disallowed(
                                ticker, _now_kst_fb,
                                is_nxt_session=is_nxt_session_hours(_now_kst_fb),
                                fallback_succeeded=True,
                            )
                            return  # 폴백 성공 — _selling 은 체결통보에서 해제
                        except KisApiError as fb_err:
                            last_error = fb_err
                            logger.error(
                                "매도 지정가 폴백도 거부 — 재시도 중단, 포지션 보존: %s "
                                "([%s] %s → [%s] %s)",
                                t(ticker), e.msg_cd, e.msg1, fb_err.msg_cd, fb_err.msg1,
                            )
                            self._selling.discard(ticker)
                            await write_log(
                                "WARNING",
                                f"매도 시장가+지정가 폴백 모두 거부 — 포지션 보존: {t(ticker)} "
                                f"(전략: {strategy_id}, [{fb_err.msg_cd}] {fb_err.msg1})",
                            )
                            # 사이클 55 R-1 Q2 — 폴백 실패 30초 TTL + NXT 시 익일 청산 전환.
                            _now_kst_fb = datetime.now(_KST_TZ)
                            _is_nxt = is_nxt_session_hours(_now_kst_fb)
                            _result = self._sell_rejection.register_market_order_disallowed(
                                ticker, _now_kst_fb,
                                is_nxt_session=_is_nxt,
                                fallback_succeeded=False,
                            )
                            if _result.next_day_clear_required:
                                # NXT 폴백 실패 → 익일 09:00 KRX 시장가 청산 큐 등록
                                try:
                                    _pending = self._pending_next_day_clear_provider()
                                    if _pending is not None:
                                        _pending.add((ticker, strategy_id))
                                        await write_log(
                                            "WARNING",
                                            f"[next_day_clear_deferred] ticker={ticker} "
                                            f"strategy={strategy_id} "
                                            f"reason=market_order_disallowed_nxt_fallback_fail",
                                        )
                                except Exception:
                                    logger.debug(
                                        "[next_day_clear_deferred] _pending_next_day_clear 등록 실패: %s",
                                        ticker, exc_info=True,
                                    )
                            return  # positions/DB 보존, 다음 사이클 자연 재트리거
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
            # 사이클 55 R-1 Q3 — [positions_reconciliation] + get_balance() 1회.
            # 수동 부분매도 등으로 실제 잔량이 남아있는 경우를 대비해 잔고를 1회 재조회.
            # 실패 graceful — positions 제거는 이미 완료, 재조회는 보호 목적.
            await safe_write_log(
                "INFO",
                f"[positions_reconciliation] ticker={ticker} strategy={strategy_id} "
                f"reason=insufficient_quantity",
                fallback_debug="[positions_reconciliation] write_log 실패",
            )
            try:
                from src.api.balance import get_balance
                holdings, _ = await get_balance()
                actual_qty = next(
                    (h.quantity for h in holdings if h.ticker == ticker), 0
                )
                if actual_qty > 0:
                    logger.info(
                        "[positions_reconciliation] 실제 잔량 확인: %s qty=%d — positions 재등록 권고",
                        ticker, actual_qty,
                    )
            except Exception:
                logger.debug(
                    "[positions_reconciliation] get_balance 조회 실패: %s",
                    ticker, exc_info=True,
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

    async def _unsubscribe_if_no_other_strategy(self, ticker: str) -> None:
        """매도 전량 체결 후 WS 구독 정리 (사이클 15-A, 2026-05-19).

        KIS 정상 패턴: 불필요 종목 즉시 구독 해제 (5분 _scan_loop 자연 정리 대신).

        다음 모두 만족 시에만 unsubscribe:
        - `registry.is_ticker_held_by_any(ticker) == False` (다른 전략 보유 X)
        - `_pending_next_day_clear` 에 없음 (익일청산 대기 X)
        - 다른 전략 `get_scanned_tickers()` 에 없음 (스캔 후보 X)

        예외 시 swallow — 매도 체결 흐름 무관.
        """
        try:
            # 1) 다른 전략이 같은 종목 보유 중?
            if self.registry.is_ticker_held_by_any(ticker):
                logger.debug("[unsubscribe_skip] %s — 다른 전략 보유 중", ticker)
                return
            # 2) 익일청산 대기 set 에 있음?
            try:
                pending = self._pending_next_day_clear_provider() or set()
            except Exception:
                pending = set()
            for entry in pending:
                if isinstance(entry, tuple) and len(entry) >= 1 and entry[0] == ticker:
                    logger.debug("[unsubscribe_skip] %s — pending_next_day_clear", ticker)
                    return
            # 3) 다른 전략 스캔 후보?
            for strat in self.registry.all():
                try:
                    scanned = strat.get_scanned_tickers()
                except AttributeError:
                    scanned = []
                if ticker in scanned:
                    logger.debug(
                        "[unsubscribe_skip] %s — strategy=%s 스캔 후보",
                        ticker, strat.config.strategy_id,
                    )
                    return
            # 모두 통과 → unsubscribe
            from src.engine.scanner import TICK_TR_ID
            from src.realtime.websocket_pool import kis_ws_pool
            await kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)
            logger.info("[sell_unsubscribe] %s WS 구독 정리", t(ticker))
        except Exception:
            logger.exception("[sell_unsubscribe] %s 실패", ticker)

    async def _handle_buy_fill(
        self, ticker: str, order_no: str, price: int,
        quantity: int, total_filled: int, ordered_qty: int,
    ) -> None:
        """매수 체결 처리 — 체결통보 수신 시 올바른 전략에 포지션 등록.

        사이클 147 (2026-06-16): `_order_strategy.get(order_no, "momentum")` 하드코딩 폴백 폐기.
        매핑 dict miss 시 trade_history PENDING row 영역 strategy 영구 영속 복구
        (005940 사고 영역 패턴 답습 — 매수도 동일 race 가능).
        """
        strategy_id = self._order_strategy.get(order_no)
        if strategy_id is None:
            # 매핑 dict miss — boot/reboot race. trade_history PENDING row 영역 strategy 복구.
            strategy_id = await _lookup_strategy_from_trade_history(
                ticker, order_no, TradeType.BUY,
            )
            if strategy_id is None:
                logger.warning(
                    "[buy_fill_strategy_lookup_fallback] order_no=%s ticker=%s — 매핑 dict miss + trade_history miss → momentum 폴백",
                    order_no, ticker,
                )
                strategy_id = "momentum"
            else:
                logger.info(
                    "[buy_fill_strategy_lookup_recovered] order_no=%s ticker=%s strategy=%s — 매핑 dict miss + trade_history 복구",
                    order_no, ticker, strategy_id,
                )
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
            # 사이클 161 (2026-06-17): `price=price` 인자 명시 — KIS CNTG_UNPR (체결단가)
            # → trade_history.price 갱신 의무 (사용자 보고 005940 BUY 33,400원 vs HTS 33,350원 +50원 차이 시정).
            # PENDING INSERT 시점 record_price (주문가 LIMIT / scanner current_price MARKET)
            # → COMPLETED UPDATE 시점에 체결단가로 정합 보정.
            affected = await update_trade_status(
                ticker, TradeType.BUY, TradeStatus.COMPLETED,
                strategy=strategy_id, price=price,
            )
            if affected == 0:
                # 체결통보가 execute_buy의 insert_trade(PENDING)보다 먼저 도착한 race
                # → COMPLETED 상태로 직접 INSERT, execute_buy 측에 PENDING INSERT 생략 신호
                self._completed_orders.add(order_no)
                from src.engine.scanner import ticker_names as _tn
                try:
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
                except Exception as exc:
                    # 사이클 161 (2026-06-17): 사이클 147 _handle_sell_fill 패턴 100% 답습.
                    # 사이클 30 부분 UNIQUE 인덱스 (ticker, order_no, trade_type) 위반 영역
                    # = PENDING row strategy 불일치 시 매핑 fallback 후에도 잔존 PENDING row 충돌.
                    # → strategy 무관 order_no 단일 키 강제 UPDATE (체결단가 정합 의무).
                    logger.warning(
                        "[buy_fill_correction_unique_violation] ticker=%s order_no=%s strategy_attempted=%s err=%r → strategy 무관 강제 COMPLETED UPDATE",
                        ticker, order_no, strategy_id, exc,
                    )
                    forced_affected = await _update_trade_status_by_order_no(
                        order_no, TradeType.BUY, TradeStatus.COMPLETED,
                        price=price,
                    )
                    if forced_affected == 0:
                        logger.error(
                            "[buy_fill_correction_forced_update_zero] ticker=%s order_no=%s — 강제 UPDATE 영역 0건 (PENDING row 부재 의심)",
                            ticker, order_no,
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
            # 사이클 161 (2026-06-17): `price=price` 인자 명시 — 부분 체결 시점 체결단가 정합.
            await update_trade_status(
                ticker, TradeType.BUY, TradeStatus.PARTIAL,
                strategy=strategy_id, price=price,
            )
            self._schedule_cancel(ticker, order_no, ordered_qty, strategy_id)
            logger.info("매수 부분 체결: %s %d/%d주 @ %d (전략: %s)", t(ticker), total_filled, ordered_qty, price, strategy_id)

    async def _handle_sell_fill(
        self, ticker: str, order_no: str, price: int,
        quantity: int, total_filled: int, ordered_qty: int,
    ) -> None:
        """매도 체결 처리 — 올바른 전략에서 포지션 제거.

        사이클 147 (2026-06-16): `_order_strategy.get(order_no, "momentum")` 하드코딩 폴백 폐기.
        005940 NH투자증권 LTV SELL trade_history PENDING ~6h 영구 잔존 사고 (2026-06-16 08:00→09:18)
        영구 차단. 매핑 dict miss 시 trade_history PENDING row 영역 strategy 영구 복구.
        """
        strategy_id = self._order_strategy.get(order_no)
        if strategy_id is None:
            # 매핑 dict miss — boot/reboot race (005940 사고 영역 정합).
            # trade_history PENDING row 영역 strategy 복구 → update_trade_status 영역 영구 정합.
            strategy_id = await _lookup_strategy_from_trade_history(
                ticker, order_no, TradeType.SELL,
            )
            if strategy_id is None:
                logger.warning(
                    "[sell_fill_strategy_lookup_fallback] order_no=%s ticker=%s — 매핑 dict miss + trade_history miss → momentum 폴백",
                    order_no, ticker,
                )
                strategy_id = "momentum"
            else:
                logger.info(
                    "[sell_fill_strategy_lookup_recovered] order_no=%s ticker=%s strategy=%s — 매핑 dict miss + trade_history 복구",
                    order_no, ticker, strategy_id,
                )
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
                try:
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
                except Exception as exc:
                    # 사이클 147 (2026-06-16): 사이클 30 UNIQUE 인덱스 (ticker, order_no, trade_type)
                    # 위반 영역 (005940 사고 정합 — PENDING row strategy 불일치 시 매핑 fallback 후에도
                    # 잔존 PENDING row 영역 충돌). strategy 무관 order_no 단일 키 강제 UPDATE.
                    logger.warning(
                        "[sell_fill_correction_unique_violation] ticker=%s order_no=%s strategy_attempted=%s err=%r → strategy 무관 강제 COMPLETED UPDATE",
                        ticker, order_no, strategy_id, exc,
                    )
                    forced_affected = await _update_trade_status_by_order_no(
                        order_no, TradeType.SELL, TradeStatus.COMPLETED,
                        price=price, profit_loss=profit_loss,
                    )
                    if forced_affected == 0:
                        logger.error(
                            "[sell_fill_correction_forced_update_zero] ticker=%s order_no=%s — 강제 UPDATE 영역 0건 (PENDING row 부재 영구 영속 의심)",
                            ticker, order_no,
                        )
            self._filled_qty.pop(order_no, None)
            self._order_qty.pop(order_no, None)
            self._order_strategy.pop(order_no, None)
            self._order_ticker.pop(order_no, None)
            logger.info("매도 전량 체결: %s %d주 @ %d (손익: %d, 전략: %s)", t(ticker), total_filled, price, profit_loss, strategy_id)
            # 사이클 15-A (2026-05-19) — 매도 전량 체결 후 WS 구독 정리 (KIS 정상 패턴).
            # 다른 전략이 보유하지 않고, 익일청산 대기 X, 다른 전략 스캔 후보 X 인 경우만 unsubscribe.
            await self._unsubscribe_if_no_other_strategy(ticker)
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

    def reset_daily_state(self) -> None:
        """일일 차단 게이트 상태 초기화 (scheduler `_reset_daily_state` 가 위임 호출).

        사이클 B-1 (2026-06-01): 장운영시간 외 거부 TTL dict + emit cap set 를 매일 정산 후 clear.
        사이클 54 (2026-06-03): NXT 다운그레이드 로그 cap set 동행 clear.
        사이클 55 R-1 (2026-06-03): _market_closed_blocked* 2 필드 직접 clear →
            self._sell_rejection.reset_daily() 4 필드 일괄 위임 (사이클 48 stale_tracker 패턴).
        """
        self._sell_rejection.reset_daily()  # 4 필드 (_blocked_until / _blocked_reason / _logged_today / _history) 일괄 clear
        self._nxt_downgrade_logged_today.clear()  # 사이클 54 유지 (사이클 56-C 통합 완료)

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
