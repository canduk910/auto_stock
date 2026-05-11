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
    # 매수가능금액 캐시 — get_buyable() KIS 호출 빈도 절감용 (TTL 60초)
    cached_buyable_qty: int = -1       # -1: 미초기화
    cached_buyable_amount: int = 0     # 매수가능 총 금액
    cached_buyable_at: float = 0.0     # epoch 초
    # 잔고 부족 락 — 이 시각까지 KIS 매수 호출 차단 (잔고 sync 후 해제)
    buy_blocked_until: float = 0.0     # epoch 초
    # per-ticker 매수 수량 0 cooldown — calc_buy_quantity() == 0인 종목에 대해
    # 매 틱마다 똑같은 경고가 반복되는 로그 스팸 + 무의미 호출 차단. 잔고 sync 시 해제.
    low_funds_tickers: dict[str, float] = field(default_factory=dict)  # ticker -> 만료 epoch
    # 매수 주문중인 종목의 예정 금액 (ticker -> 가격×수량). pending_buys(set)와 동기 라이프사이클.
    # 1주 폴백 잔여 자금 계산에 사용 — OrderEngine.execute_buy 에서 pending_buys.add 옆에 동시 등록,
    # pending_buys.discard 옆에 동시 정리. 시장가/지정가 폴백 양쪽 모두 동일 규약.
    pending_buy_amounts: dict[str, int] = field(default_factory=dict)
    # 일일 매매 퍼널 — 신호→주문→체결 단계별 카운터. _reset_daily_state에서 0 초기화.
    signal_count_today: int = 0
    order_attempt_today: int = 0
    fill_count_today: int = 0

    def has_position(self, ticker: str) -> bool:
        return ticker in self.positions

    def is_buy_pending(self, ticker: str) -> bool:
        return ticker in self.pending_buys

    def is_sold_today(self, ticker: str) -> bool:
        return ticker in self.sold_today

    def is_buy_blocked(self, now_ts: float) -> bool:
        """잔고 부족 락이 유효한지 확인."""
        return self.buy_blocked_until > now_ts

    def block_buy(self, until_ts: float) -> None:
        """잔고 부족 락 등록 + 캐시 무효화."""
        self.buy_blocked_until = until_ts
        self.cached_buyable_at = 0.0
        self.cached_buyable_qty = -1
        self.cached_buyable_amount = 0

    def unblock_buy(self) -> None:
        """락 해제 + 캐시 무효화 (다음 호출 시 fresh 조회)."""
        self.buy_blocked_until = 0.0
        self.cached_buyable_at = 0.0
        self.cached_buyable_qty = -1
        self.cached_buyable_amount = 0

    def is_buyable_cache_fresh(self, now_ts: float, ttl: float) -> bool:
        return self.cached_buyable_qty >= 0 and (now_ts - self.cached_buyable_at) < ttl

    def is_low_funds_blocked(self, ticker: str, now_ts: float) -> bool:
        """투자금 부족(매수 수량 0) cooldown이 유효한지 확인."""
        until = self.low_funds_tickers.get(ticker, 0.0)
        if until > now_ts:
            return True
        if until and until <= now_ts:
            # 만료된 항목 정리
            self.low_funds_tickers.pop(ticker, None)
        return False

    def block_low_funds(self, ticker: str, until_ts: float) -> None:
        """투자금 부족 cooldown 등록."""
        self.low_funds_tickers[ticker] = until_ts

    def clear_low_funds(self) -> None:
        """모든 ticker의 low-funds cooldown 해제 (잔고 sync 직후 호출)."""
        self.low_funds_tickers.clear()


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

    # ------------------------------------------------------------------
    # 자금 사용량 / 1주 폴백 공통 헬퍼 (2026-05-11 P1 — 전략 한도 초과 차단)
    # ------------------------------------------------------------------
    def _calc_used_funds(self) -> int:
        """해당 전략이 이미 사용한(또는 예정된) 자금 합계.

        = 보유 포지션 `buy_price × quantity` 합계
        + 매수 주문중 `pending_buy_amounts` 합계 (pending_buys 와 동기 dict)

        다른 전략의 사용액은 포함하지 않음 — strategy_id 격리.
        """
        held = sum(
            pos.buy_price * pos.quantity for pos in self.state.positions.values()
        )
        pending = sum(self.state.pending_buy_amounts.values())
        return held + pending

    def _fallback_one_share(self, current_price: int) -> int:
        """비중 기준 0주일 때 1주 폴백 — 전략 잔여 자금 기준.

        잔여 = total_investment - _calc_used_funds()
        잔여 >= current_price 이면 1주, 아니면 0주.

        결함 차단: 기존 로직은 total_investment(고정 총액)와 직접 비교 →
        다른 종목에 자금 거의 다 쓴 뒤에도 1주 추가 매수 → 전략 한도 초과.
        4개 전략(momentum/volatility_breakout/long_tail_volatility/donchian_swing)
        모두 동일 규약 — calc_buy_quantity 에서 이 메서드 호출.
        """
        if current_price <= 0:
            return 0
        remaining = self.state.total_investment - self._calc_used_funds()
        return 1 if remaining >= current_price else 0
