"""전략 베이스 모듈.

모든 매매 전략이 구현해야 하는 추상 인터페이스와 공통 데이터 모델.
새 전략 추가 시 StrategyBase를 상속하고 추상 메서드를 구현하면 된다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar

_KST = timezone(timedelta(hours=9))


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
    buy_date: date = field(default_factory=lambda: datetime.now(_KST).date())
    high_since_buy: int = 0

    # 멀티데이 보유 전략 — 시간 청산 개념 없음 (ATR 트레일링/하드 손절만).
    # is_next_day 프로퍼티에서 항상 False 반환 → OrderMonitor "청산" 배지 노출 차단.
    # 확장 시 frozenset 멤버만 추가 (Position 시그니처 변경 금지). 3 전략 모두 이 리터럴에 명시
    # (import-order 독립 단일 진실원). vcp_breakout 은 과거 import 시점 동적 side-effect 로
    # 자기를 추가하던 취약 패턴(리뷰어 오판 유발)을 2026-07 에 리터럴로 통합.
    _MULTIDAY_STRATEGIES: ClassVar[frozenset[str]] = frozenset(
        {"donchian_swing", "vcp_breakout", "kojiro"}
    )

    @property
    def is_next_day(self) -> bool:
        """매수일자가 오늘이 아니면 익일 청산 대상.

        멀티데이 보유 전략(`_MULTIDAY_STRATEGIES`)은 시간 청산 개념이 없으므로
        항상 False — OrderMonitor 화면의 "청산" 배지가 의미 없이 노출되는 결함 차단.
        (2026-05-12 I2 — donchian_swing 멀티데이 보유)
        """
        if self.strategy_id in self._MULTIDAY_STRATEGIES:
            return False
        return self.buy_date < datetime.now(_KST).date()

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


@dataclass(frozen=True)
class FunnelStage:
    """단계별 funnel 정의 — 사이클 47 (2026-05-22, refactor-review 카드 #3).

    각 전략 파일 상단의 `FUNNEL_STAGES: tuple[FunnelStage, ...]` 모듈 상수로 사용.
    `prepare()` 의 `_record_funnel_pipeline_step(FUNNEL_STAGES[i-1], ...)` 위임 헬퍼와 결합.

    step_conditions 는 runtime 평가 가능한 동적 문자열 (f-string 보존) — 호출 시점 별도 인자 전달.

    Attributes:
        step_no: 단계 번호 (1~8, 또는 99=수동 trigger 최종).
        step_name: UI 표시명 (사용자 명세와 일치 — `/strategy-funnel` 페이지 노출).
    """
    step_no: int
    step_name: str


@dataclass
class StrategyConfig:
    """전략 설정.

    params 핵심 키:
    - `tradable_boards` (list[str]): **매수 진입 전용** 설정. 사이클 38 (2026-05-22) 명문화.
      `["pre_nxt", "main", "post_nxt"]` 등. `session_tracker.is_tradable(strategy_id, params)`
      가 활성 보드 ∩ tradable_boards ≠ ∅ 일 때만 매수 신호 평가 진입.
      **매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은
      어떤 전략에서도 PRE/MAIN/POST 무관 항상 작동** (보드 가드 *없이*).
      → `risk.on_tick` 의 `check_exit_signal` 분기는 `is_tradable` 검사 전 평가.
    - `exchange` (str): 주문 거래소 라우팅 (`KRX` / `NXT` / `SOR`).
    - 그 외 전략별 파라미터 (`k_value_*` / `stop_loss_*` / `donchian_period` 등).
    """
    strategy_id: str
    name: str
    enabled: bool = True
    weight: float = 0.5
    params: dict = field(default_factory=dict)


def _resolve_ticker_name(ticker: str) -> str:
    """사이클 41 (2026-05-22) — funnel 단계별 캡처용 종목명 lookup 헬퍼.

    사이클 44 (2026-05-22, refactor-review 카드 #7) — `scanner.resolve_ticker_name` 위임.
    호환 layer 보존 (사이클 41 호출처 BFB/VCP/donchian 그대로 동작).

    우선순위 (scanner.resolve_ticker_name 동일):
    1. `scanner.ticker_names` (KIS 동적 매핑, 운영 중 갱신)
    2. `scanner.STATIC_TICKER_NAMES` (정적 시드, scanner.py 모듈 자체 파싱)
    3. "" (빈 문자열, lookup miss — 예외 전파 금지, graceful)

    `StrategyBase._record_funnel_step` 가 string 입력 시 자동 호출.
    호출자가 직접 dict 로 입력하면 본 헬퍼 우회 가능.
    """
    try:
        from src.engine import scanner as _scanner
        return _scanner.resolve_ticker_name(ticker)
    except Exception:
        # scanner import 실패 / 다른 예외 — 빈 문자열 폴백 (호출자 prepare 보호)
        return ""


class StrategyBase(ABC):
    """모든 전략의 추상 베이스 클래스.

    새 전략 추가 시:
    1. StrategyBase를 상속
    2. 추상 메서드 구현
    3. scheduler.py에서 registry.register() 호출
    """

    # 사이클 39 (2026-05-22) — funnel 단계별 ticker 캡처 cap (응답/저장 크기 보호).
    # 사이클 34 DB JSONB cap 과 정합 (survived 200 / excluded 20).
    _FUNNEL_SURVIVED_CAP = 200
    _FUNNEL_EXCLUDED_CAP = 20

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.state = StrategyState(strategy_id=config.strategy_id)
        # 사이클 39 (2026-05-22) — funnel 단계별 ticker 캡처. prepare() 마다 reset.
        # 09:30 자동 snapshot 이 본 리스트를 DB `strategy_funnel_snapshots` 단계별 row 로 변환.
        self._funnel_steps: list[dict] = []

    @property
    def strategy_id(self) -> str:
        return self.config.strategy_id

    def _record_funnel_step(
        self,
        step_no: int,
        step_name: str,
        survived: list,  # list[str | dict] — 사이클 41 (2026-05-22)
        excluded: list[dict] | None = None,
        *,
        step_conditions: str | None = None,  # 사이클 41 — 단계 조건 명시 (UI 툴팁)
    ) -> None:
        """사이클 39 (2026-05-22) — 단계별 통과/탈락 ticker 캡처.

        사이클 41 (2026-05-22) — 종목명 + 탈락 사유 정밀 추적 확장:
        - survived: string 입력 시 `_resolve_ticker_name` 으로 자동 dict 변환
          (`[{"ticker": "...", "name": "..."}]`). dict 입력은 그대로 보존.
        - excluded: `[{"ticker", "name", "reason"}]` — reason 은 수치 포함 정확 사유.
        - step_conditions: UI 툴팁용 단계 조건 명시 (예: "VCP: 2~4회 회수 + ...").

        Args:
            step_no: 단계 번호 (1, 2, 3, ...).
            step_name: 단계 이름 (UI/DB 명세와 일치).
            survived: 단계 통과 ticker 리스트 (string or dict).
            excluded: 단계 탈락 sample [{"ticker", "name", "reason"}, ...] (선택).
            step_conditions: 단계 필터 조건 명시 (선택, UI 툴팁용).

        Note:
            survived/excluded cap 자동 적용 (200/20). 원본 카운트는 보존 (cap 이전).
            본체 예외는 호출자 prepare() 가 try/except 흡수 — 회귀 가드.
        """
        survived_raw = list(survived or [])
        # 사이클 41 — string 입력 → dict 자동 변환 (종목명 lookup)
        survived_list: list[dict] = []
        for item in survived_raw:
            if isinstance(item, dict):
                # dict 입력 — 그대로 보존 (호출자 직접 종목명/추가 필드 지정 가능)
                survived_list.append(item)
            else:
                # string 입력 — 종목명 자동 lookup
                ticker_str = str(item)
                survived_list.append({
                    "ticker": ticker_str,
                    "name": _resolve_ticker_name(ticker_str),
                })

        excluded_list = list(excluded or [])
        step_no_int = int(step_no)
        entry = {
            "step_no": step_no_int,
            "step_name": str(step_name),
            "step_conditions": step_conditions,  # 사이클 41 — None or str
            "survived": survived_list[: self._FUNNEL_SURVIVED_CAP],
            "survived_count": len(survived_list),
            "excluded": excluded_list[: self._FUNNEL_EXCLUDED_CAP],
            "excluded_count": len(excluded_list),
        }
        # 사이클 170 카드 B — atomic 일관성 (in-place upsert).
        # 같은 step_no 가 이미 존재하면 in-place 교체 (append-only 누적 차단).
        # `_reset_funnel_steps(stages)` 0-시드와 결합해 조기반환/다중 실행 run 도
        # 전 단계를 일관 기록 → step1=0/step4=7 stale 잔존 패턴 영구 소멸.
        for idx, existing in enumerate(self._funnel_steps):
            if existing.get("step_no") == step_no_int:
                self._funnel_steps[idx] = entry
                return
        self._funnel_steps.append(entry)

    def _reset_funnel_steps(
        self, stages: "tuple[FunnelStage, ...] | None" = None
    ) -> None:
        """사이클 39 — prepare() 첫 단계 진입 시 호출. 이전 사이클 누적 제거.

        사이클 170 카드 B — `stages` 전달 시 모든 `FunnelStage` 를 `survived=[]`
        (count=0) 0-시드 pre-populate. 조기반환/실패 run 에서도 전 단계가 0 으로
        일관 기록되어 이전 성공 run 의 stale 값 (예: step4=7) 영구 차단.
        `stages=None` (인자 미전달) → 빈 리스트 (사이클 39 회귀 보존).
        """
        if stages is None:
            self._funnel_steps = []
            return
        self._funnel_steps = [
            {
                "step_no": int(stage.step_no),
                "step_name": str(stage.step_name),
                "step_conditions": None,
                "survived": [],
                "survived_count": 0,
                "excluded": [],
                "excluded_count": 0,
            }
            for stage in stages
        ]

    def _record_funnel_pipeline_step(
        self,
        stage: FunnelStage,
        survived: list,
        excluded: list[dict] | None = None,
        *,
        step_conditions: str | None = None,
    ) -> None:
        """사이클 47 (2026-05-22, refactor-review 카드 #3) — FunnelStage 기반 위임 헬퍼.

        `FUNNEL_STAGES` 모듈 상수 + `_record_funnel_step` (사이클 39+41) 호환 layer.

        step_no/step_name 은 `FunnelStage` 에서 추출, step_conditions 는 runtime 평가 결과를
        별도 인자로 받음 (f-string 동적 문자열 보존).

        Args:
            stage: 모듈 상수 `FUNNEL_STAGES[i-1]` 또는 직접 `FunnelStage(...)`.
            survived: 단계 통과 ticker 리스트 (string or dict, 사이클 41 호환).
            excluded: 단계 탈락 sample [{"ticker", "name", "reason"}, ...] (사이클 41 호환).
            step_conditions: 단계 필터 조건 (UI 툴팁, runtime 평가).

        Note:
            사이클 39 _record_funnel_step 의 cap/원본 카운트 보존/예외 격리 모두 위임 보존.
        """
        self._record_funnel_step(
            step_no=stage.step_no,
            step_name=stage.step_name,
            survived=survived,
            excluded=excluded,
            step_conditions=step_conditions,
        )

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

    # ------------------------------------------------------------------
    # 사이클 185 클러스터 ① — 생명주기 훅 (기본 no-op, 서브클래스 override)
    # ------------------------------------------------------------------

    def _reset_daily_state(self) -> None:
        """일일 transient cross-day 상태 정리 훅 (기본 no-op).

        scheduler._reset_daily_state(20:10) registry 순회가 전략별 호출.
        cross-day 잔존 시 익일 거짓돌파/가드 우회 유발 transient dict/set 만 override 에서 clear.
        보유결합(_limit_up_reached/_partial_exit)은 본 훅 금지 — on_position_closed 담당.
        """

    def on_position_closed(self, ticker: str) -> None:
        """포지션 전량 청산(매도 체결) 시 per-ticker 보유결합 상태 정리 훅 (기본 no-op).

        order_engine 매도 체결/reconciliation 에서 호출. 보유 중 유지 · 매도 후 정리.
        """

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
