"""리스크 관리 모듈.

- 실시간 시세에 따른 손절/익일청산 신호 감시
- 전략별 포지션 비중 제한
- 전략 간 중복 매수 방지
- 전략별 매매 가능 보드(KRX 메인 / NXT 프리 / NXT 애프터) 가드 — Phase 8
"""

import logging

from src.engine.order_engine import OrderEngine
from src.engine.session import session_tracker
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

        # 1. 공용 시세 갱신 (1회)
        prev_close = ticker_prev_close.get(ticker, 0)
        prdy_ctrt = round((current_price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0
        ticker_prices[ticker] = {
            "current_price": current_price,
            "open_price": open_price,
            "change_rate": round(change_rate, 2),
            "prdy_ctrt": prdy_ctrt,
        }

        # PR7(동일가 연속 틱 신호 평가 skip) 롤백 — 회귀 발견:
        # VB/LTV 시가 확정 직후 첫 on_tick에서 _prev_price=0 → check_buy_signal first-tick skip.
        # 이후 같은 가격이 반복되면 PR7 가드로 skip → _prev_price=0 유지 → 가격 변화가 와도
        # prev=0이라 돌파 가드("prev<target AND current>=target") 통과 못 해 매수 신호가
        # 끝까지 발생하지 않는 결함. 2026-05-11 운영 중 13종목 중 5종목 돌파 상태인데
        # VB 매수 신호 로그 0건 확인. 이벤트 루프 부담보다 매수 기회 누락이 큰 손실이라 즉시 롤백.

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
            # 보드 가드 — 전략의 tradable_boards에 현재 활성 보드 포함 여부 (Phase 8)
            if not session_tracker.is_tradable(strategy.strategy_id, strategy.config.params):
                continue

            # 전략 간 중복 매수 방지: 보유/주문 중/당일 매도 모두 가로질러 차단
            if self.registry.is_ticker_blocked_for_buy(ticker):
                continue

            signal = strategy.check_buy_signal(ticker, current_price, open_price)
            if signal == Signal.BUY:
                await self.order_engine.execute_buy(ticker, current_price, strategy)
