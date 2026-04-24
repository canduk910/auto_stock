"""전략 베이스 모듈.

모든 매매 전략이 구현해야 하는 추상 인터페이스와 공통 데이터 모델.
새 전략 추가 시 StrategyBase를 상속하고 추상 메서드를 구현하면 된다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Signal(str, Enum):
    """매매 신호."""
    NONE = "NONE"
    BUY = "BUY"
    STOP_LOSS = "STOP_LOSS"
    NEXT_DAY_CLEAR = "NEXT_DAY_CLEAR"
    TRAILING_STOP = "TRAILING_STOP"
    FORCE_CLEAR = "FORCE_CLEAR"


@dataclass
class Position:
    """보유 포지션 정보."""
    ticker: str
    buy_price: int
    quantity: int
    order_no: str
    strategy_id: str
    buy_date: date = field(default_factory=date.today)
    high_since_buy: int = 0

    @property
    def is_next_day(self) -> bool:
        """매수일자가 오늘이 아니면 익일 청산 대상."""
        return self.buy_date < date.today()

    def __post_init__(self):
        if self.high_since_buy == 0:
            self.high_since_buy = self.buy_price


@dataclass
class StrategyState:
    """전략별 독립 상태."""
    strategy_id: str
    positions: dict[str, Position] = field(default_factory=dict)
    pending_buys: set[str] = field(default_factory=set)
    sold_today: set[str] = field(default_factory=set)  # 당일 매도 완료 종목 (재매수 방지)
    total_investment: int = 0
    daily_realized_pnl: int = 0
    buy_disabled: bool = False
    buy_signals: list[dict] = field(default_factory=list)

    def has_position(self, ticker: str) -> bool:
        return ticker in self.positions

    def is_buy_pending(self, ticker: str) -> bool:
        return ticker in self.pending_buys

    def is_sold_today(self, ticker: str) -> bool:
        return ticker in self.sold_today


@dataclass
class StrategyConfig:
    """전략 설정."""
    strategy_id: str
    name: str
    enabled: bool = True
    weight: float = 0.5
    params: dict = field(default_factory=dict)


class StrategyBase(ABC):
    """모든 전략의 추상 베이스 클래스.

    새 전략 추가 시:
    1. StrategyBase를 상속
    2. 추상 메서드 구현
    3. scheduler.py에서 registry.register() 호출
    """

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.state = StrategyState(strategy_id=config.strategy_id)

    @property
    def strategy_id(self) -> str:
        return self.config.strategy_id

    @abstractmethod
    async def prepare(self) -> None:
        """장 시작 전 준비 (데이터 로드 등)."""

    @abstractmethod
    def check_buy_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """매수 신호 판단."""

    @abstractmethod
    def check_exit_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """청산 신호 판단 (손절/익절/강제청산)."""

    @abstractmethod
    def calc_buy_quantity(self, current_price: int) -> int:
        """매수 수량 계산."""

    def is_max_positions(self) -> bool:
        max_pos = self.config.params.get("max_positions", 4)
        # 보유 포지션 + 매수 대기(체결 전) 합산으로 제한
        return len(self.state.positions) + len(self.state.pending_buys) >= max_pos

    def is_daily_loss_exceeded(self) -> bool:
        limit = self.config.params.get("daily_loss_limit", -5.0)
        if self.state.total_investment <= 0:
            return False
        loss_rate = self.state.daily_realized_pnl / self.state.total_investment * 100
        return loss_rate <= limit
