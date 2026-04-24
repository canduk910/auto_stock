"""매매 전략 모듈.

- 매수: 당일 시가 대비 +29.5% 도달 시 투자대금 25% 비중 시장가 매수
- 당일 손절: 매수가 대비 -7.5% 시 즉시 전량 매도
- 익일 청산: 시가 갭 +10% 이상이면 트레일링 스탑(-2%), 미만이면 즉시 전량 매도
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

logger = logging.getLogger(__name__)

BUY_THRESHOLD = 29.0       # 시가 대비 매수 진입 등락률(%)
STOP_LOSS_RATE = -7.5      # 매수가 대비 손절 등락률(%)
GAP_UP_THRESHOLD = 10.0    # 익일 갭상승 기준(%)
TRAILING_STOP_RATE = -2.0  # 트레일링 스탑: 고점 대비(%)
POSITION_RATIO = 0.25      # 1종목 투자 비중 (25%)
MAX_POSITIONS = 4          # 동시 보유 최대 종목 수
DAILY_LOSS_LIMIT = -5.0    # 일일 최대 손실 한도(%)


class Signal(str, Enum):
    NONE = "NONE"
    BUY = "BUY"
    STOP_LOSS = "STOP_LOSS"
    NEXT_DAY_CLEAR = "NEXT_DAY_CLEAR"
    TRAILING_STOP = "TRAILING_STOP"


@dataclass
class Position:
    """보유 포지션 정보."""
    ticker: str
    buy_price: int
    quantity: int
    order_no: str
    buy_date: date = field(default_factory=date.today)  # 매수일자
    high_since_buy: int = 0       # 매수 이후 고가 (트레일링용)

    @property
    def is_next_day(self) -> bool:
        """매수일자가 오늘이 아니면 익일 청산 대상."""
        return self.buy_date < date.today()

    def __post_init__(self):
        self.high_since_buy = self.buy_price


@dataclass
class StrategyState:
    """매매 전략 상태."""
    positions: dict[str, Position] = field(default_factory=dict)
    pending_buys: set[str] = field(default_factory=set)  # 매수 주문 중인 종목
    total_investment: int = 0      # 총 투자가능금액 (당일 시작 시점)
    daily_realized_pnl: int = 0    # 당일 실현 손익
    buy_disabled: bool = False     # 신규 매수 중단 플래그
    buy_signals: list[dict] = field(default_factory=list)  # 최근 매수 신호 이력 (최대 20개)

    def has_position(self, ticker: str) -> bool:
        return ticker in self.positions

    def is_buy_pending(self, ticker: str) -> bool:
        return ticker in self.pending_buys

    def is_max_positions(self) -> bool:
        return len(self.positions) >= MAX_POSITIONS

    def is_daily_loss_exceeded(self) -> bool:
        if self.total_investment <= 0:
            return False
        loss_rate = self.daily_realized_pnl / self.total_investment * 100
        return loss_rate <= DAILY_LOSS_LIMIT


# 종목별 직전 전일대비 등락률 (돌파 감지용)
_prev_prdy_rate: dict[str, float] = {}


def check_buy_signal(
    ticker: str,
    current_price: int,
    open_price: int,
    state: StrategyState,
) -> Signal:
    """매수 신호를 판단한다.

    전일종가 대비 등락률이 29% 미만 → 29% 이상으로 돌파하는 순간 매수.
    이미 상한가(+30%)에 있는 종목은 제외.
    """
    from src.engine.scanner import t, ticker_prev_close

    if state.buy_disabled:
        return Signal.NONE

    if state.has_position(ticker) or state.is_buy_pending(ticker):
        return Signal.NONE

    if state.is_max_positions():
        return Signal.NONE

    if state.is_daily_loss_exceeded():
        return Signal.NONE

    # 전일종가 기준 등락률 계산
    prev_close = ticker_prev_close.get(ticker, 0)
    if prev_close <= 0:
        return Signal.NONE

    change_rate = (current_price - prev_close) / prev_close * 100

    # 상한가(+30%) 종목 제외
    if change_rate >= 30.0:
        return Signal.NONE

    # 직전 tick 등락률 확인 — 29% 미만에서 29% 이상으로 돌파하는 순간만 매수
    # 첫 tick(기록 없음)은 현재 등락률만 기록하고 건너뜀 (이미 상승한 종목 즉시 매수 방지)
    if ticker not in _prev_prdy_rate:
        _prev_prdy_rate[ticker] = change_rate
        return Signal.NONE

    prev_rate = _prev_prdy_rate[ticker]
    _prev_prdy_rate[ticker] = change_rate

    if prev_rate < BUY_THRESHOLD and change_rate >= BUY_THRESHOLD:
        logger.info(
            "매수 신호: %s 전일종가(%d) 대비 %.1f%% (현재가: %d, 직전: %.1f%%)",
            t(ticker), prev_close, change_rate, current_price, prev_rate,
        )
        from src.engine.scanner import ticker_names
        state.buy_signals.append({
            "ticker": ticker,
            "name": ticker_names.get(ticker, ""),
            "price": current_price,
            "prev_close": prev_close,
            "change_rate": round(change_rate, 1),
            "time": datetime.now().strftime("%H:%M:%S"),
        })
        if len(state.buy_signals) > 20:
            state.buy_signals.pop(0)
        return Signal.BUY

    return Signal.NONE


def check_stop_loss(
    ticker: str,
    current_price: int,
    state: StrategyState,
) -> Signal:
    """당일 손절 신호를 판단한다."""
    pos = state.positions.get(ticker)
    if not pos:
        return Signal.NONE

    from src.engine.scanner import t

    loss_rate = (current_price - pos.buy_price) / pos.buy_price * 100
    if loss_rate <= STOP_LOSS_RATE:
        logger.info(
            "손절 신호: %s 매수가(%d) 대비 %.1f%% (현재가: %d)",
            t(ticker), pos.buy_price, loss_rate, current_price,
        )
        return Signal.STOP_LOSS

    return Signal.NONE


def check_next_day_clear(
    ticker: str,
    today_open: int,
    current_price: int,
    state: StrategyState,
) -> Signal:
    """익일 청산 신호를 판단한다."""
    pos = state.positions.get(ticker)
    if not pos or not pos.is_next_day:
        return Signal.NONE

    from src.engine.scanner import t

    gap_rate = (today_open - pos.buy_price) / pos.buy_price * 100

    if gap_rate < GAP_UP_THRESHOLD:
        logger.info(
            "익일 즉시 청산: %s 갭률 %.1f%% (시가: %d, 매수가: %d)",
            t(ticker), gap_rate, today_open, pos.buy_price,
        )
        return Signal.NEXT_DAY_CLEAR

    # 갭상승 +10% 이상 → 트레일링 스탑 모드
    pos.high_since_buy = max(pos.high_since_buy, current_price)
    drop_rate = (current_price - pos.high_since_buy) / pos.high_since_buy * 100

    if drop_rate <= TRAILING_STOP_RATE:
        logger.info(
            "트레일링 스탑: %s 고점(%d) 대비 %.1f%% (현재가: %d)",
            t(ticker), pos.high_since_buy, drop_rate, current_price,
        )
        return Signal.TRAILING_STOP

    return Signal.NONE


def calc_buy_quantity(total_investment: int, current_price: int) -> int:
    """매수 수량을 계산한다. 총 투자대금의 25% 비중."""
    if current_price <= 0:
        return 0
    amount = int(total_investment * POSITION_RATIO)
    return amount // current_price
