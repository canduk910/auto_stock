"""매매 스케줄러.

- 08:25 기동: 토큰 갱신, 잔고 동기화
- 08:30~16:00 매매 프로세스 가동
- 16:10 정산: daily_performance 기록, 프로세스 정리
"""

import asyncio
import logging
from datetime import date, datetime, time

from src.api.balance import get_balance
from src.auth.token import token_manager
from src.db.daily_performance import upsert_daily_performance
from src.db.system_logs import write_log
from src.engine.order_engine import OrderEngine
from src.engine.risk import RiskManager
from src.engine.scanner import scan_stocks, subscribe_filtered_stocks, unsubscribe_all
from src.engine.strategy import StrategyState
from src.realtime.handler import dispatch_message, register_execution_handler, register_tick_handler
from src.realtime.websocket import kis_ws

logger = logging.getLogger(__name__)

TIME_BOOT = time(8, 25)
TIME_MARKET_OPEN = time(8, 30)
TIME_NEXT_DAY_CLEAR = time(9, 0)
TIME_SCAN_START = time(9, 30)
TIME_BUY_STOP = time(15, 20)
TIME_MARKET_CLOSE = time(15, 30)
TIME_SETTLEMENT = time(16, 10)
SCAN_INTERVAL = 300  # 5분마다 스캔


class TradingScheduler:
    """매매 스케줄러."""

    def __init__(self) -> None:
        self.state = StrategyState()
        self.order_engine = OrderEngine(self.state)
        self.risk_manager = RiskManager(self.state, self.order_engine)
        self._running = False
        self._phase: str = "idle"

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """매매 프로세스를 시작한다."""
        if self._running:
            logger.warning("이미 실행 중")
            return

        self._running = True
        self._phase = "booting"
        await write_log("INFO", "매매 시스템 시작")

        try:
            await self._boot()
            register_tick_handler(self.risk_manager.on_tick)
            register_execution_handler(self.order_engine.handle_execution_notice)

            # WebSocket 연결 (별도 태스크)
            ws_task = asyncio.create_task(
                kis_ws.connect(dispatch_message)
            )

            # 09:00 익일 청산 실행
            self._phase = "next_day_clear"
            await self._wait_until(TIME_NEXT_DAY_CLEAR)
            await self._execute_next_day_clear()

            # 09:30 종목 스캔 시작
            self._phase = "scanning"
            await self._wait_until(TIME_SCAN_START)
            tickers = await scan_stocks()
            await subscribe_filtered_stocks(tickers)

            # 주기적 스캔 루프
            self._phase = "trading"
            scan_task = asyncio.create_task(self._scan_loop())

            # 15:20 신규 매수 중단
            await self._wait_until(TIME_BUY_STOP)
            self._phase = "buy_stopped"
            self.state.buy_disabled = True
            await write_log("INFO", "15:20 신규 매수 중단")

            # 15:30 장 마감, 구독 해제
            await self._wait_until(TIME_MARKET_CLOSE)
            self._phase = "closing"
            await unsubscribe_all()
            await write_log("INFO", "15:30 WebSocket 구독 해제")

            # 16:10 정산
            await self._wait_until(TIME_SETTLEMENT)
            self._phase = "settling"
            await self._settle()

            scan_task.cancel()
            await kis_ws.disconnect()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass

        except Exception:
            logger.exception("매매 프���세스 오류")
            await write_log("ERROR", "매매 프로세스 비정상 종료")
        finally:
            self._running = False
            self._phase = "idle"
            await write_log("INFO", "매매 시스템 종료")

    async def stop(self) -> None:
        """매매 프로세스를 중지한다."""
        self._running = False
        await unsubscribe_all()
        await kis_ws.disconnect()
        await write_log("INFO", "매매 시스템 수동 중지")

    def get_status(self) -> dict:
        """현재 상태를 반환한다."""
        from src.engine.scanner import get_scan_status, ticker_names

        positions_detail = {}
        for ticker, pos in self.state.positions.items():
            positions_detail[ticker] = {
                "name": ticker_names.get(ticker, ""),
                "buy_price": pos.buy_price,
                "quantity": pos.quantity,
                "high_since_buy": pos.high_since_buy,
                "is_next_day": pos.is_next_day,
            }

        order_fills = {}
        for order_no, filled in self.order_engine._filled_qty.items():
            ordered = self.order_engine._order_qty.get(order_no, 0)
            order_fills[order_no] = {
                "filled_qty": filled,
                "order_qty": ordered,
            }

        from src.config import settings as _settings

        return {
            "running": self._running,
            "env": _settings.kis_env,
            "positions": len(self.state.positions),
            "pending_buys": len(self.state.pending_buys),
            "position_tickers": list(self.state.positions.keys()),
            "phase": self._phase,
            "scan": get_scan_status(),
            "positions_detail": positions_detail,
            "orders": {
                "pending_buy_tickers": list(self.state.pending_buys),
                "fills": order_fills,
                "pending_cancels": list(self.order_engine._pending_cancel_tasks.keys()),
            },
            "strategy": {
                "buy_disabled": self.state.buy_disabled,
                "daily_realized_pnl": self.state.daily_realized_pnl,
                "total_investment": self.state.total_investment,
                "buy_signals": self.state.buy_signals[-10:],
            },
        }

    async def mark_next_day_positions(self) -> None:
        """전일 보유 포지션을 익일 청산 대상으로 마킹한다."""
        for pos in self.state.positions.values():
            pos.is_next_day = True
        logger.info("익일 청산 대상 마킹: %d종목", len(self.state.positions))

    # -- private --------------------------------------------------------

    async def _execute_next_day_clear(self) -> None:
        """09:00 익일 청산 로직. 보유 중 is_next_day 포지션을 처리한다.

        1. 전일 매수 보유 종목 목록 조회
        2. 각 종목의 당일 시가 확인 (WebSocket 시세 구독으로 수신)
        3. 시가가 매수가 대비 +10% 이상 → 트레일링 스탑 모드 (on_tick에서 고점 추적)
        4. 시가가 +10% 미만 → 즉시 시장가 전량 매도
        """
        from src.engine.strategy import Signal, GAP_UP_THRESHOLD

        next_day_positions = [
            (t, p) for t, p in self.state.positions.items() if p.is_next_day
        ]
        if not next_day_positions:
            logger.info("익일 청산 대상 없음")
            return

        await write_log("INFO", f"익일 청산 대상: {[t for t, _ in next_day_positions]}")

        # 보유 종목에 대해 시세 구독 (시가 수신용)
        from src.engine.scanner import TICK_TR_ID
        for ticker, _ in next_day_positions:
            await kis_ws.subscribe(TICK_TR_ID, ticker)

        # 시가 확정 대기 (09:01까지 최대 60초)
        await asyncio.sleep(60)

        for ticker, pos in list(next_day_positions):
            if ticker not in self.state.positions:
                continue  # 이미 on_tick에서 처리됨

            # 당일 시가로 갭상승 판단
            today_open = pos.high_since_buy  # on_tick에서 갱신된 고가 = 시가 부근
            if pos.buy_price > 0:
                gap_rate = (today_open - pos.buy_price) / pos.buy_price * 100
            else:
                gap_rate = 0.0

            if gap_rate >= GAP_UP_THRESHOLD:
                # +10% 이상 갭상승 → 트레일링 스탑 모드 유지 (on_tick에서 고점 추적)
                logger.info(
                    "트레일링 스탑 모드: %s 갭률 %.1f%% (시가: %d, 매수가: %d)",
                    ticker, gap_rate, today_open, pos.buy_price,
                )
                from src.engine.scanner import t
                await write_log("INFO", f"트레일링 스탑 모드: {t(ticker)} 갭률 {gap_rate:.1f}%")
            else:
                # +10% 미만 → 즉시 시장가 전량 매도
                logger.info(
                    "익일 즉시 청산: %s 갭률 %.1f%% (시가: %d, 매수가: %d)",
                    ticker, gap_rate, today_open, pos.buy_price,
                )
                await self.order_engine.execute_sell(ticker, Signal.NEXT_DAY_CLEAR)
                from src.engine.scanner import t
                await write_log("INFO", f"익일 즉시 청산 실행: {t(ticker)} 갭률 {gap_rate:.1f}%")

        logger.info("익일 청산 실행 완료")

    async def _boot(self) -> None:
        """시스템 기동: 토큰 갱신, 잔고 동기화."""
        await token_manager.get_token()
        holdings, summary = await get_balance()
        self.state.total_investment = summary.net_asset

        # 기존 보유 종목 → 익일 청산 대상으로 등록
        for h in holdings:
            if h.quantity > 0:
                from src.engine.strategy import Position
                self.state.positions[h.ticker] = Position(
                    ticker=h.ticker,
                    buy_price=int(h.avg_price),
                    quantity=h.quantity,
                    order_no="",
                    is_next_day=True,
                )

        await write_log("INFO", f"기동 완료: 순자산 {summary.net_asset:,}원, 보유 {len(holdings)}종목")
        logger.info("기동 완료: 순자산 %s, 보유 %d종목", summary.net_asset, len(holdings))

    async def _scan_loop(self) -> None:
        """주기적으로 종목을 스캔하고 구독을 업데이트한다."""
        while self._running:
            await asyncio.sleep(SCAN_INTERVAL)
            if not self._running:
                break
            try:
                tickers = await scan_stocks()
                await unsubscribe_all()
                await subscribe_filtered_stocks(tickers)
            except Exception:
                logger.exception("종목 스캔 오류")

    async def _settle(self) -> None:
        """일일 정산: 잔고 조회 후 daily_performance 기록."""
        try:
            _, summary = await get_balance()
            # 수익률 계산 (당일 순자산 변동 기준)
            if self.state.total_investment > 0:
                profit_rate = (
                    (summary.net_asset - self.state.total_investment)
                    / self.state.total_investment
                    * 100
                )
            else:
                profit_rate = 0.0

            await upsert_daily_performance(
                target_date=date.today(),
                total_asset=float(summary.net_asset),
                daily_profit_rate=profit_rate,
            )
            await write_log(
                "INFO",
                f"일일 정산: 순자산 {summary.net_asset:,}원, 수익률 {profit_rate:.2f}%",
            )
        except Exception:
            logger.exception("정산 오류")
            await write_log("ERROR", "일일 정산 실패")

    async def _wait_until(self, target: time) -> None:
        """지정 시각까지 대기한다."""
        while self._running:
            now = datetime.now().time()
            if now >= target:
                break
            await asyncio.sleep(10)


trading_scheduler = TradingScheduler()
