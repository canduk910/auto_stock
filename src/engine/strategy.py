"""매매 전략 모듈.

- 매수: 당일 시가 대비 +29.5% 도달 시 투자대금 25% 비중 시장가 매수
- 당일 손절: 매수가 대비 -7.5% 시 즉시 전량 매도
- 익일 청산: 시가 갭 +10% 이상이면 트레일링 스탑(-2%), 미만이면 즉시 전량 매도
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum

_KST = timezone(timedelta(hours=9))

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
    buy_date: date = field(default_factory=lambda: datetime.now(_KST).date())  # 매수일자
    high_since_buy: int = 0       # 매수 이후 고가 (트레일링용)

    @property
    def is_next_day(self) -> bool:
        """매수일자가 오늘이 아니면 익일 청산 대상."""
        return self.buy_date < datetime.now(_KST).date()

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



def calc_buy_quantity(total_investment: int, current_price: int) -> int:
    """매수 수량을 계산한다. 총 투자대금의 25% 비중."""
    if current_price <= 0:
        return 0
    amount = int(total_investment * POSITION_RATIO)
    return amount // current_price
