"""리스크 관리 모듈.

- 실시간 시세에 따른 손절/익일청산 신호 감시
- 포지션 비중 제한
"""

import logging

from src.engine.order_engine import OrderEngine
from src.engine.strategy import (
    Signal,
    StrategyState,
    check_buy_signal,
    check_next_day_clear,
    check_stop_loss,
)

logger = logging.getLogger(__name__)


class RiskManager:
    """실시간 시세를 감시하며 매매 신호에 따라 주문을 실행한다."""

    def __init__(self, state: StrategyState, order_engine: OrderEngine) -> None:
        self.state = state
        self.order_engine = order_engine

    async def on_tick(
        self,
        ticker: str,
        current_price: int,
        open_price: int,
        change_rate: float,
    ) -> None:
        """실시간 체결가 수신 시 호출된다."""
        from src.engine.scanner import ticker_prev_close, ticker_prices
        prev_close = ticker_prev_close.get(ticker, 0)
        prdy_ctrt = round((current_price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0
        ticker_prices[ticker] = {
            "current_price": current_price,
            "open_price": open_price,
            "change_rate": round(change_rate, 2),
            "prdy_ctrt": prdy_ctrt,
        }
        # 일일 손실 한도 초과 시 신규 매수 중단
        if self.state.is_daily_loss_exceeded() and not self.state.buy_disabled:
            self.state.buy_disabled = True
            logger.warning("일일 최대 손실 한도 도달, 신규 매수 중단")

        # 보유 중이면 고가 갱신
        pos = self.state.positions.get(ticker)
        if pos:
            pos.high_since_buy = max(pos.high_since_buy, current_price)

        # 1. 당일 손절 확인
        signal = check_stop_loss(ticker, current_price, self.state)
        if signal == Signal.STOP_LOSS:
            await self.order_engine.execute_sell(ticker, signal)
            return

        # 2. 익일 청산 확인
        signal = check_next_day_clear(
            ticker, open_price, current_price, self.state
        )
        if signal in (Signal.NEXT_DAY_CLEAR, Signal.TRAILING_STOP):
            await self.order_engine.execute_sell(ticker, signal)
            return

        # 3. 매수 신호 확인
        signal = check_buy_signal(ticker, current_price, open_price, self.state)
        if signal == Signal.BUY:
            await self.order_engine.execute_buy(ticker, current_price)
