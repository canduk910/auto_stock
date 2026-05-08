"""리스크 관리 모듈.

- 실시간 시세에 따른 손절/익일청산 신호 감시
- 전략별 포지션 비중 제한
- 전략 간 중복 매수 방지
"""

import logging

from src.engine.order_engine import OrderEngine
from src.engine.strategy_base import Signal
from src.engine.strategy_registry import StrategyRegistry

logger = logging.getLogger(__name__)


class RiskManager:
    """실시간 시세를 감시하며 전략별 매매 신호에 따라 주문을 실행한다."""

    def __init__(self, registry: StrategyRegistry, order_engine: OrderEngine) -> None:
        self.registry = registry
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

        # 동일가 연속 틱 감지 — 직전 캐시의 current_price와 비교 (PR7)
        # 시세 캐시는 항상 갱신하되, 가격이 바뀌지 않은 틱은 신호 평가/포지션 순회를 skip해
        # on_tick 호출 빈도(분당 수천 틱)에서 불필요한 CPU 소모 차단.
        # 안전장치 검토: VB/momentum의 돌파 가드는 "이전 < 기준 AND 현재 ≥ 기준"이라 동일가
        # 연속 틱에서는 결과가 변하지 않음(매수/매도 판정 동일 결과). 손절·트레일링도 동일가면
        # 결과 변경 없음. high_since_buy = max(...)이라 동일가 시 변화 없어 skip 안전.
        prev_info = ticker_prices.get(ticker)
        same_price = bool(prev_info) and prev_info.get("current_price") == current_price

        # 1. 공용 시세 갱신 (1회) — same_price 여부 무관하게 항상 최신 메타 반영
        prev_close = ticker_prev_close.get(ticker, 0)
        prdy_ctrt = round((current_price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0
        ticker_prices[ticker] = {
            "current_price": current_price,
            "open_price": open_price,
            "change_rate": round(change_rate, 2),
            "prdy_ctrt": prdy_ctrt,
        }

        if same_price:
            return

        # 2. 활성화된 전략별 순회
        for strategy in self.registry.enabled():
            state = strategy.state

            # 일일 손실 한도 초과 시 신규 매수 중단
            if strategy.is_daily_loss_exceeded() and not state.buy_disabled:
                state.buy_disabled = True
                logger.warning("일일 최대 손실 한도 도달: %s, 신규 매수 중단", strategy.strategy_id)

            # 보유 중이면 고가 갱신
            pos = state.positions.get(ticker)
            if pos:
                pos.high_since_buy = max(pos.high_since_buy, current_price)

            # 3. 청산 신호 확인 (보유 중인 경우)
            if state.has_position(ticker):
                signal = strategy.check_exit_signal(ticker, current_price, open_price)
                if signal != Signal.NONE:
                    await self.order_engine.execute_sell(ticker, signal, strategy.strategy_id)
                    continue  # 청산 주문 후 매수 신호 확인 불필요

            # 4. 매수 신호 확인
            # 전략 간 중복 매수 방지: 보유/주문 중/당일 매도 모두 가로질러 차단
            if self.registry.is_ticker_blocked_for_buy(ticker):
                continue

            signal = strategy.check_buy_signal(ticker, current_price, open_price)
            if signal == Signal.BUY:
                await self.order_engine.execute_buy(ticker, current_price, strategy)
