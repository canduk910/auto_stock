"""상한가 모멘텀 전략.

- 매수: 전일종가 대비 +29% 돌파 순간 (29% 미만 → 이상 돌파 시)
- 상한가(+30%) 종목 제외
- 손절: 매수 체결가 대비 -7.5%
- 익일 청산: 시가 갭 +10% → 트레일링 스탑 -2% / 그 외 즉시 매도
"""

import logging
from datetime import datetime

from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

logger = logging.getLogger(__name__)


class MomentumStrategy(StrategyBase):
    """상한가 모멘텀 전략 (기존 전략)."""

    # 매매 가능 보드 (Phase 8) — momentum은 KRX 동시호가/메인만. 상한가 +29% 신호는 KRX 기준
    DEFAULT_TRADABLE_BOARDS = ("krx_open", "main")

    DEFAULT_PARAMS = {
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        # 거래소 라우팅 — 익일 청산이 08:00 NXT 프리 시점에 실행되므로 SOR/NXT 권장(실전).
        # 모의(vts)는 KRX만 허용 — UI가 환경별로 SOR/NXT 선택지 차단.
        "exchange": "KRX",
        "buy_threshold": 29.0,
        "stop_loss_rate": -7.5,
        "gap_up_threshold": 10.0,
        "trailing_stop_rate": -2.0,
        "position_ratio": 0.25,
        "max_positions": 4,
        "daily_loss_limit": -5.0,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        self._prev_prdy_rate: dict[str, float] = {}
        self._next_day_clear_pending = False  # 익일 청산 대기 중 플래그 (시가 안정화 대기)

    async def prepare(self) -> None:
        """준비 작업 없음 (실시간 스캔 기반)."""
        pass

    def check_buy_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """전일종가 대비 29% 돌파 순간 매수."""
        from src.engine.scanner import t, ticker_names, ticker_prev_close

        if self.state.buy_disabled:
            return Signal.NONE
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker) or self.state.is_sold_today(ticker):
            return Signal.NONE
        if self.is_max_positions():
            return Signal.NONE
        if self.is_daily_loss_exceeded():
            return Signal.NONE

        prev_close = ticker_prev_close.get(ticker, 0)
        if prev_close <= 0:
            return Signal.NONE

        change_rate = (current_price - prev_close) / prev_close * 100

        # 상한가(+30%) 종목 제외
        if change_rate >= 30.0:
            return Signal.NONE

        # 첫 tick은 기록만 (이미 상승한 종목 즉시 매수 방지)
        if ticker not in self._prev_prdy_rate:
            self._prev_prdy_rate[ticker] = change_rate
            return Signal.NONE

        prev_rate = self._prev_prdy_rate[ticker]
        self._prev_prdy_rate[ticker] = change_rate

        threshold = self.config.params["buy_threshold"]
        if prev_rate < threshold and change_rate >= threshold:
            logger.info(
                "매수 신호: %s 전일종가(%d) 대비 %.1f%% (현재가: %d, 직전: %.1f%%)",
                t(ticker), prev_close, change_rate, current_price, prev_rate,
            )
            self.state.buy_signals.append({
                "ticker": ticker,
                "name": ticker_names.get(ticker, ""),
                "price": current_price,
                "prev_close": prev_close,
                "change_rate": round(change_rate, 1),
                "time": datetime.now().strftime("%H:%M:%S"),
            })
            if len(self.state.buy_signals) > 20:
                self.state.buy_signals.pop(0)
            return Signal.BUY

        return Signal.NONE

    def check_exit_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """손절 + 익일 청산 통합 판단."""
        from src.engine.scanner import t

        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        # 1. 당일 손절: 매수가 대비 -7.5%
        loss_rate = (current_price - pos.buy_price) / pos.buy_price * 100
        stop_loss = self.config.params["stop_loss_rate"]
        if loss_rate <= stop_loss:
            logger.info(
                "손절 신호: %s 매수가(%d) 대비 %.1f%% (현재가: %d)",
                t(ticker), pos.buy_price, loss_rate, current_price,
            )
            return Signal.STOP_LOSS

        # 2. 익일 청산
        if not pos.is_next_day:
            return Signal.NONE

        # 시가 안정화 대기 중에는 on_tick에서 청산 판단하지 않음
        # (scheduler._execute_next_day_clear가 60초 대기 후 직접 처리)
        if self._next_day_clear_pending:
            return Signal.NONE

        gap_threshold = self.config.params["gap_up_threshold"]
        trailing_rate = self.config.params["trailing_stop_rate"]

        gap_rate = (open_price - pos.buy_price) / pos.buy_price * 100 if pos.buy_price > 0 else 0

        if gap_rate < gap_threshold:
            logger.info(
                "익일 즉시 청산: %s 갭률 %.1f%% (시가: %d, 매수가: %d)",
                t(ticker), gap_rate, open_price, pos.buy_price,
            )
            return Signal.NEXT_DAY_CLEAR

        # 갭상승 +10% → 트레일링 스탑
        pos.high_since_buy = max(pos.high_since_buy, current_price)
        drop_rate = (current_price - pos.high_since_buy) / pos.high_since_buy * 100

        if drop_rate <= trailing_rate:
            logger.info(
                "트레일링 스탑: %s 고점(%d) 대비 %.1f%% (현재가: %d)",
                t(ticker), pos.high_since_buy, drop_rate, current_price,
            )
            return Signal.TRAILING_STOP

        return Signal.NONE

    def calc_buy_quantity(self, current_price: int) -> int:
        """할당 자금의 position_ratio 비중. 비중 기준 0주여도 1주 살 수 있으면 1주 매수."""
        if current_price <= 0:
            return 0
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        qty = amount // current_price
        if qty > 0:
            return qty
        if self.state.total_investment >= current_price:
            return 1
        return 0
