"""전략 베이스 모듈.

모든 매매 전략이 구현해야 하는 추상 인터페이스와 공통 데이터 모델.
새 전략 추가 시 StrategyBase를 상속하고 추상 메서드를 구현하면 된다.
"""

import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar

from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.observer_trace import trace_observer_failure
from src.engine.turtle_sizing import compute_unit_qty

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))

# ── cycle242 랏당 최대 유닛 상한 (터틀 전략 한정) — 리스크 정체성 상수,
# PARAM_RANGES/INT_PARAMS 편입 금지(AST G-242-1). 4 터틀 전략 DEFAULT_PARAMS
# ["max_lot_units"] 는 _MAX_LOT_UNITS_DEFAULT 와 동치여야 한다(AST G-242-6).
_MAX_LOT_UNITS_DEFAULT = 2.0   # K — 1주 폴백/PR 낙하 랏도 이 유닛 수를 넘지 못한다
_MAX_LOT_UNITS_MIN = 1.0       # K<1 은 "터틀 유닛보다 작게" = 정의상 무의미.
                                # 하한 1.0 = T 경로(정상 터틀 랏 ≤ u*) 무접촉의 수학적 전제
_MAX_LOT_UNITS_MAX = 20.0      # 관측 최대 M1 15.61 < 20 → 사실상 현행 복귀(롤백 다이얼)

# ── cycle245 랏 명목 ρ축 상한 (= K축이 실제로 심사하지 못한 모든 랏) —
# 리스크 정체성 상수, PARAM_RANGES/INT_PARAMS 편입 금지(AST G-245-1).
# 7 전략 DEFAULT_PARAMS["max_lot_ratio_mult"] 는 _MAX_LOT_RATIO_MULT_DEFAULT 와
# 동치여야 한다(AST G-245-6 — strategies/*.py glob 전수 = 신규 전략의 무방비 편입 차단).
_MAX_LOT_RATIO_MULT_DEFAULT = 2.5   # K_ρ — 랏 명목 ≤ K_ρ × (position_ratio × 예산)
_MAX_LOT_RATIO_MULT_MIN = 1.0       # K_ρ<1 은 정상 비중 랏까지 잘라 전면 무매매 = 정의상 금지.
                                    # 하한 1.0 = 주 분기(qty>0) 무접촉의 수학적 전제
_MAX_LOT_RATIO_MULT_MAX = 20.0      # 09-04 예산에서 K=20 컷오프가 비터틀 5전략 전부
                                    # price_filter_max(500,000) 초과 = 사실상 현행 복귀(롤백 다이얼)


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

    # cycle242 — 캡 ATR 소스 키. 터틀 사이징이 읽는 `_candidates[ticker]` 의 키와
    # 동일 집합이어야 한다(donchian·kojiro = "atr" / VCP·BFB = "atr14", 실측
    # 상호 배타). 두 키가 서로 다른 값을 동시에 가지면 채택하지 않는다(ambiguous).
    _SIZING_ATR_KEYS: ClassVar[tuple[str, ...]] = ("atr", "atr14")

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.state = StrategyState(strategy_id=config.strategy_id)
        # 사이클 39 (2026-05-22) — funnel 단계별 ticker 캡처. prepare() 마다 reset.
        # 09:30 자동 snapshot 이 본 리스트를 DB `strategy_funnel_snapshots` 단계별 row 로 변환.
        self._funnel_steps: list[dict] = []
        # 예산 이중제한 관측 — `[budget_clamp]` 1회/(ticker,전략)/일 cap.
        # 날짜 키 자기 리셋 — `KstDailyEmitCap`(사이클 258 카드 #4)가 내부에서
        # KST 날짜 롤오버를 자체 처리한다(`_reset_daily_state` 훅 미의존 — 서브클래스
        # override 가 super() 를 호출하지 않아 리셋이 누락될 수 있었던 문제도 함께 소멸).
        self._budget_clamp_logged: KstDailyEmitCap[str] = KstDailyEmitCap[str]()
        # cycle233 — 계좌 SOFT 게이트 스킵 관측(1회/전략/일) + 1주 폴백 notional
        # 초과 관측(1회/ticker/일). 날짜 키 자기 리셋(KstDailyEmitCap 내장).
        self._account_gate_logged: KstDailyEmitCap[str] = KstDailyEmitCap[str]()
        self._oversized_logged: KstDailyEmitCap[str] = KstDailyEmitCap[str]()
        # cycle242 — 랏 유닛 상한 관측 cap (복합 키: "cap|{ticker}" / "skip|{ticker}|{reason}"
        # / "cfg"). 날짜 키 자기 리셋(KstDailyEmitCap 내장).
        self._lot_cap_logged: KstDailyEmitCap[str] = KstDailyEmitCap[str]()
        # cycle245 — ρ축 랏 명목 상한 관측 cap (복합 키: "blk|{ticker}" /
        # "skip|{ticker}|{reason}" / "cfg" / "clamp"). cycle242 `_lot_cap_logged` 와
        # **별개 인스턴스** — 한 사이클의 키 폭주·날짜 리셋이 다른 사이클 관측을
        # 지우지 않게 한다(cycle236 "별개 cap 가드" 선례). 날짜 키 자기 리셋(KstDailyEmitCap 내장).
        self._ratio_cap_logged: KstDailyEmitCap[str] = KstDailyEmitCap[str]()

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
    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
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

    def _apply_budget_limit(
        self, qty: int, current_price: int, ticker: str | None = None,
    ) -> int:
        """전략 예산 이중제한 ② 명목 축 — 7 전략 `calc_buy_quantity` 공통 return 관문.

        이중제한 = ① 개수 `max_positions`(`is_max_positions`, check_buy_signal 담당)
                 + ② 명목 `Σ매수금액 ≤ total_investment`(본 관문).

        잔여 = ``total_investment − _calc_used_funds()`` (보유 원금 + pending 예정액)
          - ``qty <= 0`` → `_fallback_one_share` 위임 (기존 계약 보존 — **분기 순서가 계약**)
          - ``qty  > 0`` → ``min(qty, 잔여 // price)``. 잔여 < price 면 0.

        부분 매수를 허용한다(유닛 미만 스킵 아님) — 부분 유닛의 리스크는 1유닛 *미만*
        (under-risk)이라 안전 방향이고, 소액 계좌에서 스킵은 사실상 무매매를 만든다.
        **단, `sizing_mode="turtle"` 전략에서는 최종 랏이 `max_lot_units`(K) 유닛을
        초과하면 초과분을 자르고, K 유닛이 1주에 못 미치면 매수하지 않는다**
        (cycle242 — 1주 폴백이 설계 유닛의 수 배가 되던 §0.0 결함 시정. 고정%손절
        전략은 position_ratio 가 이미 리스크 균등이라 범위 밖).
        **그리고 K축이 이 랏을 실제로 심사하지 못한 랏(비터틀 전략 전부 + 터틀이지만
        ATR 배관이 끊긴 랏)은 최종 명목이 `max_lot_ratio_mult`(K_ρ) × `position_ratio`
        × 예산 을 넘으면 그만큼 자르고, 1주도 못 사면 매수하지 않는다**(cycle245 —
        1주 폴백 랏 크기가 그 종목의 *주가* 로 결정되던 §5 결함 시정. 09-04 실측
        4.23배 랏(LTV 000500)이 그날 최대 손실 −11,000원을 냈다). 두 캡은
        **상호배타** — `min` 합성이 아니라 K축 심사 여부로 갈린다.

        결함 배경: 주 분기가 ``int(예산×ratio)//price`` 를 잔여 검증 없이 반환해
        ``position_ratio × max_positions > 1.0`` 인 전략이 예산을 초과 매수할 수 있었다.
        잔여 클램프는 `_fallback_one_share` 와 turtle opt-in 분기에만 있었다.

        **원자성 조건**: `order_engine.execute_buy` 는 `calc_buy_quantity` 호출부터
        `pending_buys.add` 까지 `await` 0건이라 본 관문의 read 가 pending 등록까지
        원자적이다. 따라서 이 메서드 안에서 ``await``/DB/HTTP 는 **절대 금지**
        (AST 가드 A-PURE / A-ATOMIC 가 양쪽을 영구 고정).
        """
        if current_price <= 0:
            return 0
        if qty <= 0:
            final = self._fallback_one_share(current_price)
            _via_fallback = True
        else:
            remaining = max(0, self.state.total_investment - self._calc_used_funds())
            final = min(qty, remaining // current_price)
            _via_fallback = False
            if final < qty:
                self._emit_budget_clamp(ticker, qty, final, remaining)
        # cycle242 — 랏당 최대 유닛 상한 (행위, 터틀 전략 한정). 폴백/잔여 클램프
        # **뒤** · `[oversized_fallback]` 관측 **앞**에 배치 — 관측기가 캡 이후
        # 최종 수량을 재도록 한다. 캡 산출 실패는 현행 수량 유지(fail-open) —
        # 헬퍼 내부에서 흡수·LOUD.
        final = self._apply_lot_units_cap(
            final, current_price, ticker, via_fallback=_via_fallback,
        )
        # cycle233 — 1주 폴백 notional 초과 **관측만** (자문 cycle232 §정정 1·부속안 ③).
        # 수량은 절대 바꾸지 않는다 — 차단(부속안 ②)은 매수를 좁히는 변경이라
        # 사용자 결정으로 기각(표본 보호 국면). 관측 실패도 수량 산출을 못 깨뜨린다.
        # cycle242 — ρ 축(`position_ratio×예산`) 관측은 K 축(`max_lot_units`) 행위와
        # **병존**한다. K>1 이면 캡 통과 랏도 ρ 축 상한을 넘을 수 있어 **비제로가
        # 정상**(의미 반전 — cycle228/240/241 교훈, 배포 전후 같은 grep 합산 금지).
        try:
            self._emit_oversized_fallback(ticker, final, current_price)
        except Exception:  # pragma: no cover — 관측 자기실패 흡수
            pass
        # cycle245 — ρ축 랏 명목 상한 (행위). K축(cycle242)이 이 랏을 실제로
        # 심사하지 못한 경우에만 적용 = 두 캡은 상호배타(min 합성 없음).
        # 관측(`[oversized_fallback]`) **뒤**에 두는 것이 계약 — 앞에 두면 차단된
        # 랏의 ρ 관측이 `final_qty < 1` 조기탈출로 통째로 사라져 R7 자기검증
        # 불변식이 성립하지 않는다. 캡 산출 실패는 현행 수량 유지(fail-open) —
        # 헬퍼 내부에서 흡수·LOUD.
        final = self._apply_ratio_notional_cap(
            final, current_price, ticker, via_fallback=_via_fallback,
        )
        return final

    # ──────────── cycle242 — 랏당 최대 유닛 상한 (`max_lot_units`, 터틀 한정) ────────────

    def _read_max_lot_units(self) -> float:
        """`max_lot_units` 읽기 + 클램프.

        비수치·None·bool·비유한·<MIN → `_MAX_LOT_UNITS_DEFAULT` / >MAX → MAX.
        PUT 라우트/DB 병합에 화이트리스트가 없어 임의 값이 들어올 수 있으므로
        읽는 쪽에서 항상 안전 범위로 정규화한다(쓰는 쪽 검증 아님).

        cycle242 R4 — **키가 명시적으로 존재하는데** 값이 무효/범위밖이라
        클램프가 실제 발동하면 `[fallback_cap_clamped]` WARNING 1회/전략/일로
        흔적을 남긴다(`raw=` 원본 값 병기). **키 부재**(DB/params 에 값이 없어
        코드 기본값을 쓰는 정상 구성)는 클램프가 아니므로 무발화 — 그렇지
        않으면 "DB 미설정"과 "PUT 으로 무효 값을 넣었다가 걸러짐"이 로그에서
        구별 불가해진다(루트 CLAUDE.md "비중 단위 추론 변환 금지" 독트린의
        "위반은 조용히 흡수 말고 시끄럽게 거부" 원칙 적용).
        """
        has_key = "max_lot_units" in self.config.params
        raw = self.config.params.get("max_lot_units", _MAX_LOT_UNITS_DEFAULT)
        clamped = False
        if isinstance(raw, bool):
            result = _MAX_LOT_UNITS_DEFAULT
            clamped = has_key
        else:
            try:
                k = float(raw)
            except (TypeError, ValueError):
                result = _MAX_LOT_UNITS_DEFAULT
                clamped = has_key
            else:
                if not math.isfinite(k) or k < _MAX_LOT_UNITS_MIN:
                    result = _MAX_LOT_UNITS_DEFAULT
                    clamped = has_key
                elif k > _MAX_LOT_UNITS_MAX:
                    result = _MAX_LOT_UNITS_MAX
                    clamped = True
                else:
                    result = k
        if clamped:
            self._emit_fallback_cap_clamped(raw, result)
        return result

    def _resolve_sizing_atr(self, ticker: str | None) -> tuple[float | None, str]:
        """터틀 사이징과 **같은 소스**(`_candidates[ticker]`)에서 ATR 을 읽는다 — read-only.

        반환 (atr, reason): reason ∈ {"ok","no_ticker","no_candidates","no_atr","ambiguous_atr"}.
        `_SIZING_ATR_KEYS` 중 양수로 파싱되는 값을 모아 **서로 다른 값이 2개 이상이면
        채택하지 않는다**(어느 키가 사이징에 쓰였는지 관문은 모르므로 — 틀린 ATR 로
        상한을 계산하느니 현행 유지). `_candidates` 를 변경·생성하지 않는다
        (setdefault/pop/update 금지 — AST G-242-8).
        """
        if not ticker:
            return None, "no_ticker"
        cands = getattr(self, "_candidates", None)
        if not isinstance(cands, dict):
            return None, "no_candidates"
        info = cands.get(ticker)
        if not isinstance(info, dict):
            return None, "no_atr"
        values: list[float] = []
        for key in self._SIZING_ATR_KEYS:
            raw = info.get(key)
            if raw is None or isinstance(raw, bool):
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(v) and v > 0 and v not in values:
                values.append(v)
        if not values:
            return None, "no_atr"
        if len(values) > 1:
            return None, "ambiguous_atr"
        return values[0], "ok"

    def _apply_lot_units_cap(
        self, final: int, current_price: int, ticker: str | None, *, via_fallback: bool,
    ) -> int:
        """랏당 최대 유닛 상한 — `sizing_mode == "turtle"` 전략의 모든 랏에
        `min(final, floor(K × 예산 × risk_pct ÷ ATR))` 을 적용한다.

        - 캡 산출은 `turtle_sizing.compute_unit_qty(budget, atr, risk_pct, fraction=K)`
          재사용(새 수식 금지) — 정상 터틀 랏(K≥1, `_calc_used_funds` 클램프까지 거친
          `compute_unit_qty_guarded` 결과)은 이 캡보다 항상 작거나 같다.
        - fail-open: `sizing_mode != "turtle"` / `ticker is None` / ATR 결측·모호 /
          `risk_pct <= 0` / 예외 → `final` 그대로. ATR·risk_pct·예외 사유는
          `[fallback_cap_skipped]` WARNING 으로 LOUD. 모드 아님·ticker None 은 조용히
          (터틀 분기 자체가 같은 조건에서 조용히 off 하는 것과 정합).
        - 행위(반환값)는 관측 성패와 무관 — 세 emit 은 내부에서 예외 흡수.
        """
        if final < 1 or current_price <= 0:
            return final
        try:
            params = self.config.params
            mode = params.get("sizing_mode")
            k = self._read_max_lot_units()
            budget = int(self.state.total_investment or 0)
            try:
                risk_pct = float(params.get("risk_pct") or 0)
            except (TypeError, ValueError):
                risk_pct = 0.0
            # 첫 관문 평가마다 캡 상태를 기록 — 캡이 조용히 꺼진 채(DB `sizing_mode`
            # 리셋 등) 매수가 나가는 사고를 감지하기 위한 카나리아(1회/전략/일).
            self._emit_fallback_cap_config(mode, k, budget, risk_pct)
            if mode != "turtle" or ticker is None:
                return final
            if risk_pct <= 0 or budget <= 0:
                self._emit_fallback_cap_skipped(
                    ticker, "no_risk_pct" if risk_pct <= 0 else "no_budget",
                    final, current_price,
                )
                return final
            atr, reason = self._resolve_sizing_atr(ticker)
            if atr is None:
                self._emit_fallback_cap_skipped(ticker, reason, final, current_price)
                return final
            cap_qty = compute_unit_qty(budget, atr, risk_pct, fraction=k)
            if final <= cap_qty:
                return final
            self._emit_fallback_notional_capped(
                ticker, via_fallback=via_fallback, price=current_price, atr=atr, k=k,
                req_qty=final, capped_qty=cap_qty, budget=budget, risk_pct=risk_pct,
            )
            return cap_qty
        except Exception:
            # 캡 산출 자체가 던지면 현행 수량 유지 (변경 이전 행위 쪽으로 fail)
            # cycle242 R1/R2 — `logger.debug` 도 emit 과 같은 try 안(관문 밖으로
            # 예외가 전파되지 않게, §3 불변계약 9 "행위는 cap 밖" 적용 대상은
            # 관측 *성패* 뿐 아니라 관측 *시도* 자체도 포함한다 — 로거가 죽어도
            # 매수 수량 산출은 살아야 한다).
            try:
                self._emit_fallback_cap_skipped(ticker, "exception", final, current_price)
                logger.debug(
                    "[fallback_cap_skipped] exception ticker=%s", ticker, exc_info=True,
                )
            except Exception:  # pragma: no cover
                pass
            return final

    def _emit_fallback_notional_capped(
        self, ticker: str | None, *, via_fallback: bool, price: int, atr: float,
        k: float, req_qty: int, capped_qty: int, budget: int, risk_pct: float,
    ) -> None:
        """`[fallback_notional_capped]` — 랏이 `max_lot_units`(K) 초과해 잘렸다(행위 확정 후 기록).

        cycle242 — §0.0 결함(1주 폴백/PR 낙하 랏이 설계 유닛의 수 배가 되던 것)의
        직접 증거. INFO, 1회/(전략,ticker)/일(날짜 키 자기 리셋). 캡 자체는 이미
        `_apply_lot_units_cap` 이 확정했으므로 여기서의 발화 성패는 매수 수량에
        영향을 주지 않는다(peek → 로그 → mark).
        """
        try:
            key = f"cap|{ticker or '-'}"
            if not self._lot_cap_logged.should_emit(key):
                return
            unit_qty = (budget * risk_pct / atr) if atr > 0 else 0.0
            denom = budget * risk_pct
            units_before = (req_qty * atr / denom) if denom > 0 else 0.0
            units_after = (capped_qty * atr / denom) if denom > 0 else 0.0
            path = "fallback" if via_fallback else "sized"
            logger.info(
                "[fallback_notional_capped] ticker=%s strategy=%s path=%s price=%d "
                "atr=%d unit_qty=%.3f k=%.2f req_qty=%d capped_qty=%d "
                "units_before=%.2f units_after=%.2f budget=%d risk_pct=%.4f",
                ticker or "-", self.strategy_id, path, price, int(atr), unit_qty, k,
                req_qty, capped_qty, units_before, units_after, budget, risk_pct,
            )
            self._lot_cap_logged.mark_emitted(key)
        except Exception:
            trace_observer_failure(
                "[fallback_notional_capped_failed]", ticker or "-", self._lot_cap_logged,
            )

    def _emit_fallback_cap_skipped(
        self, ticker: str | None, reason: str, final: int, price: int,
    ) -> None:
        """`[fallback_cap_skipped]` — 캡 미적용(현행 수량 유지, fail-open) LOUD.

        reason ∈ {no_candidates,no_atr,ambiguous_atr,no_risk_pct,no_budget,exception}.
        WARNING, 1회/(전략,ticker,reason)/일. ATR 배관 결함이 조용히 지나가지 않게
        하되, 매수 자체는 캡 이전 수량 그대로 진행된다(fail-open — cycle228 유령
        키 P0-1 재현 방지, fail-closed 구현은 계약 위반).

        cycle242 R3 — 꼬리 `atr=`/`units=` 진단 필드(캡 산출과 무관, read-only).
        `[oversized_fallback]` 은 notional(ρ 축)이 상한을 넘을 때만 발화해서
        PR 경로(`path=sized`)가 `no_atr`/`ambiguous_atr` 로 fail-open 스킵되면
        K 초과 사실이 **어떤 마커에도** 안 남는 사각이 있었다 — `_candidates`
        의 미채택 원시 ATR 후보값과 그 값 기준 유닛 배수를 그대로 노출해
        메운다. ambiguous_atr/no_atr 는 정의상 `atr=-` (`_resolve_sizing_atr`
        의 "채택 안 함" 계약과 정합 — 이 필드는 그 판단을 바꾸지 않는다).
        """
        try:
            key = f"skip|{ticker or '-'}|{reason}"
            if not self._lot_cap_logged.should_emit(key):
                return
            atr_desc, units_desc = self._describe_lot_cap_diagnostics(ticker, final)
            logger.warning(
                "[fallback_cap_skipped] ticker=%s strategy=%s reason=%s qty=%d "
                "price=%d atr=%s units=%s — 캡 미적용(현행 수량 유지, fail-open)",
                ticker or "-", self.strategy_id, reason, final, price,
                atr_desc, units_desc,
            )
            self._lot_cap_logged.mark_emitted(key)
        except Exception:
            trace_observer_failure(
                "[fallback_cap_skipped_failed]", ticker or "-", self._lot_cap_logged,
            )

    def _describe_lot_cap_diagnostics(
        self, ticker: str | None, final: int,
    ) -> tuple[str, str]:
        """cycle242 R3 — 진단 전용 read-only 헬퍼.

        `[fallback_cap_skipped]` 가 fail-open 으로 스킵할 때 `_candidates[ticker]`
        의 `_SIZING_ATR_KEYS` **원시값**(채택 여부와 무관 — `_resolve_sizing_atr`
        가 no_atr/ambiguous_atr 로 불채택한 값도 그대로 노출)과, 그 값 기준
        유닛 배수(`final*atr/(budget*risk_pct)`)를 각각 `key=value` `|` 구분
        문자열로 반환한다. 캡 산출 로직에는 관여하지 않는다(read-only,
        `_candidates` 변경 없음). 값이 하나도 없거나 예외 시 `("-", "-")`.
        """
        try:
            cands = getattr(self, "_candidates", None)
            if not isinstance(cands, dict) or not ticker:
                return "-", "-"
            info = cands.get(ticker)
            if not isinstance(info, dict):
                return "-", "-"
            try:
                budget = int(self.state.total_investment or 0)
                risk_pct = float(self.config.params.get("risk_pct") or 0)
            except (TypeError, ValueError):
                budget, risk_pct = 0, 0.0
            atr_parts: list[str] = []
            unit_parts: list[str] = []
            for skey in self._SIZING_ATR_KEYS:
                raw = info.get(skey)
                if raw is None or isinstance(raw, bool):
                    continue
                try:
                    v = float(raw)
                except (TypeError, ValueError):
                    continue
                if not (math.isfinite(v) and v > 0):
                    continue
                atr_parts.append(f"{skey}={v:.0f}")
                if budget > 0 and risk_pct > 0:
                    unit_parts.append(f"{final * v / (budget * risk_pct):.2f}")
                else:
                    unit_parts.append("-")
            if not atr_parts:
                return "-", "-"
            return "|".join(atr_parts), "|".join(unit_parts)
        except Exception:  # pragma: no cover — 진단 실패가 매수/로그를 막지 않는다
            return "-", "-"

    def _emit_fallback_cap_config(
        self, mode: str | None, k: float, budget: int, risk_pct: float,
    ) -> None:
        """`[fallback_cap_config]` — 캡 활성 상태 카나리아. INFO, 1회/전략/일.

        캡이 조용히 꺼진 채(DB `sizing_mode` 리셋 등) 매수가 나가는 사고를
        `[fallback_cap_config] cap=off` 부재/존재로 감지하기 위한 상시 표식.
        """
        try:
            key = "cfg"
            if not self._lot_cap_logged.should_emit(key):
                return
            cap_state = "on" if mode == "turtle" else "off"
            atr_max = int(k * budget * risk_pct)
            logger.info(
                "[fallback_cap_config] strategy=%s sizing_mode=%s cap=%s k=%.2f "
                "budget=%d risk_pct=%.4f atr_max=%d",
                self.strategy_id, mode, cap_state, k, budget, risk_pct, atr_max,
            )
            self._lot_cap_logged.mark_emitted(key)
        except Exception:
            trace_observer_failure(
                "[fallback_cap_config_failed]", self.strategy_id, self._lot_cap_logged,
            )

    def _emit_fallback_cap_clamped(self, raw: object, result: float) -> None:
        """`[fallback_cap_clamped]` — `max_lot_units` 가 실제로 클램프됐다. WARNING, 1회/전략/일.

        cycle242 R4 — `_read_max_lot_units` 가 키가 **명시적으로 존재하는데**
        무효/범위밖이라 클램프를 발동시킬 때만 호출된다(키 부재 = 정상 기본값
        사용이라 클램프 아님 — 호출 자체가 안 일어난다). `raw=` 에 원본 값을
        그대로 `repr` 해 "DB 미설정"과 "PUT 으로 무효 값이 들어와 걸러짐"을
        `[fallback_cap_config] k=` 만으로는 구별 못 하던 사각을 메운다.
        """
        try:
            key = "clamp"
            if not self._lot_cap_logged.should_emit(key):
                return
            logger.warning(
                "[fallback_cap_clamped] strategy=%s raw=%r clamped_to=%.2f "
                "— max_lot_units 범위 밖 값이 클램프됨(DB/PUT 확인 필요)",
                self.strategy_id, raw, result,
            )
            self._lot_cap_logged.mark_emitted(key)
        except Exception:
            trace_observer_failure(
                "[fallback_cap_clamped_failed]", self.strategy_id, self._lot_cap_logged,
            )

    def _emit_oversized_fallback(
        self, ticker: str | None, final_qty: int, current_price: int,
    ) -> None:
        """`[oversized_fallback]` — 최종 수량 명목이 notional 상한을 넘은 관측.

        cycle233 (자문 cycle232 §정정 1) — `_fallback_one_share` 가 notional 상한
        (`position_ratio × 예산`)을 보지 않아 고가주 1주가 설계 유닛의 3배+ 명목이
        된다(실측 000815 3.10배 = R15 동일 종목 4유닛 위반). **관측 전용** — 수량
        무변경, 1회/(ticker)/일 cap, 어떤 실패도 흡수. position_ratio 결측/0 은
        상한 정의 불가라 무발화 (fail-open).

        cycle242 — ρ 축(본 마커, `position_ratio×예산`) 관측은 K 축
        (`max_lot_units` 캡, `_apply_lot_units_cap` 행위)과 **병존**한다. K>1 이면
        캡을 통과한 랏도 ρ 축 상한을 넘을 수 있어 **비제로가 정상**(의미 반전 —
        08-28 이전과 배포 전후 같은 grep 합산 금지). 꼬리 `units=` 필드는
        `_resolve_sizing_atr`(터틀 사이징과 동일 소스) 기준 유닛 배수 — ATR/risk_pct
        결측 시 `-`.

        cycle245 — 이 마커는 ρ캡(`_apply_ratio_notional_cap`) **앞**에서 발화하므로
        의미가 **"실제로 산 랏" → "사려 했던 랏"** 으로 전환됐다. 차단된 랏
        (`[ratio_notional_blocked]`)도 여기에 1행 남는다.

        **자기검증 불변식(R7 — 라운드 1 재정의)**: `ratio` 가 **그날 그 전략의
        `[ratio_cap_config] k=` 값**(리터럴 2.50 이 아니다 — 롤백으로 3.0/20.0 이
        될 수 있고 그때 리터럴 판정은 상시 오탐이 된다)을 넘고 그 전략의 `cap=on`
        인데 같은 (전략, ticker, 일자)에 `[ratio_notional_blocked]` **도**
        `[ratio_cap_skipped]` **도** 없으면 캡 우회 = 결함. ⚠️ `cap=backstop`
        (터틀) 행은 **정상**이다 — K축(`compute_unit_qty`)은 무상한 유닛 축이라
        저ATR·고가 랏에서 ρ 상한의 3.86~5.00배가 통과하며, 그 잔여 노출은 결정 ⑦
        (상호배타)의 알려진 귀결로 별건 후속(§8 F-9)에 등재돼 있다.
        ⚠️ 배포(09-04) 전후 같은 grep 합산 금지. 로그 서식은 byte 불변
        (AST G-245-10 이 포맷 문자열을 핀 — cycle233 형 `"3.10" in message` 호환).
        """
        try:
            if final_qty < 1 or current_price <= 0:
                return
            ratio = float(self.config.params.get("position_ratio") or 0)
            budget = int(self.state.total_investment or 0)
            if ratio <= 0 or budget <= 0:
                return
            cap = int(budget * ratio)
            notional = final_qty * current_price
            if cap <= 0 or notional <= cap:
                return
            key = ticker or "-"
            if self._oversized_logged.should_emit(key):
                # peek → 로그 → mark (cycle226 D-3 — 로그 자기실패가 그날 관측을 지우지 않게)
                atr, _reason = self._resolve_sizing_atr(ticker)
                try:
                    risk_pct = float(self.config.params.get("risk_pct") or 0)
                except (TypeError, ValueError):
                    risk_pct = 0.0
                if atr and risk_pct > 0:
                    units_s = f"{final_qty * atr / (budget * risk_pct):.2f}"
                else:
                    units_s = "-"
                logger.info(
                    "[oversized_fallback] ticker=%s strategy=%s qty=%d notional=%d "
                    "cap=%d ratio=%.2f — 1주 폴백이 notional 상한 초과 (관측 전용) "
                    "units=%s",
                    key, self.strategy_id, final_qty, notional, cap, notional / cap,
                    units_s,
                )
                self._oversized_logged.mark_emitted(key)
        except Exception:
            trace_observer_failure(
                "[oversized_fallback_failed]", ticker or "-", self._oversized_logged,
            )

    # ──────────── cycle245 — ρ축 랏 명목 상한 (`max_lot_ratio_mult`) ────────────

    def _read_max_lot_ratio_mult(self) -> float | None:
        """`max_lot_ratio_mult` 읽기 + 클램프. **키 부재는 `None`**(= 캡 OFF).

        ⚠️ cycle242 `_read_max_lot_units` 와 **반대 관례**다. 이 캡은 *매수를 막는*
        통제이므로 "설정이 없으면 막는다"(fail-closed)는 P0-1 유령 키 재현 경로다
        (유령 키 → 항상 차단 → 전 기간 체결 0). 키는 7 전략 `DEFAULT_PARAMS` 에
        전부 명시돼 라이브는 항상 ON 이고, 키가 없는 것은 `StrategyBase` 를 직접
        상속한 테스트 더블뿐이다(AST G-245-6 이 `strategies/*.py` glob 전수로 키
        존재를 강제하고, 조용한 꺼짐은 `[ratio_cap_config] cap=off` 가 감지).

        키 존재 + 무효/범위밖 → `_MAX_LOT_RATIO_MULT_DEFAULT` 또는 MAX 로 정규화하고
        `[ratio_cap_clamped]` WARNING 1회/전략/일(`raw=%r` 병기). `PUT /api/strategies
        /{id}/params` 가 화이트리스트 없이 기존 키를 덮어쓰므로 읽는 쪽 클램프가
        필수다(쓰는 쪽 검증 아님). bool 은 수치로 보지 않는다.
        """
        if "max_lot_ratio_mult" not in self.config.params:
            return None
        raw = self.config.params.get("max_lot_ratio_mult")
        clamped = False
        if isinstance(raw, bool):
            result = _MAX_LOT_RATIO_MULT_DEFAULT
            clamped = True
        else:
            try:
                k = float(raw)
            except (TypeError, ValueError):
                result = _MAX_LOT_RATIO_MULT_DEFAULT
                clamped = True
            else:
                if not math.isfinite(k) or k < _MAX_LOT_RATIO_MULT_MIN:
                    result = _MAX_LOT_RATIO_MULT_DEFAULT
                    clamped = True
                elif k > _MAX_LOT_RATIO_MULT_MAX:
                    result = _MAX_LOT_RATIO_MULT_MAX
                    clamped = True
                else:
                    result = k
        if clamped:
            self._emit_ratio_cap_clamped(raw, result)
        return result

    def _lot_units_cap_governs(self, ticker: str | None) -> tuple[bool, str]:
        """cycle242 K축 캡이 **이 랏을 실제로 심사하는가** — ρ축 미적용 조건 (read-only, 무음).

        반환 `(governs, reason)`. `_apply_lot_units_cap` 의 fail-open 4조건과 **같은
        소스·같은 판정**을 쓴다(`params["sizing_mode"]` / `params["risk_pct"]` /
        `state.total_investment` / `_resolve_sizing_atr`) — 판정이 드리프트하면 두
        캡 사이에 무방비 구간이나 이중 캡이 생긴다(AST G-245-8 이 소스 동일성을 핀).
        로그를 내지 않는다 — 판정기가 시끄러우면 랏마다 2배로 찍힌다(관측은
        `[ratio_cap_config]` 카나리아 담당).

        reason ∈ {"k_axis", "not_turtle", "no_ticker", "no_risk_pct", "no_budget",
                  "no_atr", "probe_error"}.
        - `"k_axis"` → K축이 심사 = ρ축 **미적용**(조용히)
        - `"probe_error"` → 판정 자체가 실패 = **fail-open 방향으로 미적용** + LOUD
        - 그 외 → ρ축 **적용**(백스톱 — 터틀인데 ATR 배관이 끊긴 랏도 여기로 온다)
        """
        try:
            params = self.config.params
            if params.get("sizing_mode") != "turtle":
                return False, "not_turtle"
            if ticker is None:
                return False, "no_ticker"
            try:
                risk_pct = float(params.get("risk_pct") or 0)
            except (TypeError, ValueError):
                return False, "no_risk_pct"
            if risk_pct <= 0:
                return False, "no_risk_pct"
            if int(self.state.total_investment or 0) <= 0:
                return False, "no_budget"
            atr, _reason = self._resolve_sizing_atr(ticker)
            if atr is None:
                return False, "no_atr"
            return True, "k_axis"
        except Exception:  # pragma: no cover — 판정 실패는 fail-open 방향
            # 판정 실패는 "현행 수량 유지" 쪽으로 fail (착수 제약: fail-open + LOUD).
            # 호출자가 `probe_error` 를 보고 `[ratio_cap_skipped]` 로 LOUD 하게 남긴다.
            return True, "probe_error"

    def _apply_ratio_notional_cap(
        self, final: int, current_price: int, ticker: str | None, *, via_fallback: bool,
    ) -> int:
        """랏 명목 ρ축 상한 — `min(final, int(K_ρ × int(예산 × position_ratio)) // 현재가)`.

        - 산식의 `cap = int(예산 × position_ratio)` 는 `_emit_oversized_fallback`
          (cycle233) · `portfolio_risk.compute_over_cap_positions` 와 **동일**하다
          (세 번째 복제가 아니라 이미 두 곳이 재고 있는 축에 행위를 얹는 것) —
          §7 R7 자기검증 불변식의 전제다.
        - 차단 조건은 `final × price > cutoff` = **경계 포함 통과**(`>=` 아님).
        - `K_ρ ≥ 1` 이므로 주 분기(`qty > 0`)는 정의상 무접촉이다 — 호출자가
          `int(예산×ratio)//price` 로 만든 수량은 명목이 이미 `cap` 이하이고
          `cutoff ≥ cap` 이기 때문(F-4/F-5 가 항등식으로 봉인).
        - fail-open: 키 부재 / K축 심사 / `position_ratio` ≤ 0 / 예산 ≤ 0 / cap 0 /
          예외 → `final` 그대로. 사유는 `[ratio_cap_skipped]` WARNING(키 부재·K축
          심사는 조용히 — 정상 구성이고 `[ratio_cap_config]` 가 이미 기록한다).
        - 행위(반환값)는 관측 성패와 무관 — 네 emit 은 내부에서 예외 흡수(cycle237).
        """
        if final < 1 or current_price <= 0:
            return final
        try:
            params = self.config.params
            k = self._read_max_lot_ratio_mult()        # None = 키 부재 = OFF
            mode = params.get("sizing_mode")
            try:
                pos_ratio = float(params.get("position_ratio") or 0)
            except (TypeError, ValueError):
                pos_ratio = 0.0
            budget = int(self.state.total_investment or 0)
            cap = int(budget * pos_ratio) if (pos_ratio > 0 and budget > 0) else 0
            cutoff = int(k * cap) if (k is not None and cap > 0) else 0
            governs, gov_reason = self._lot_units_cap_governs(ticker)
            # 캡 상태 카나리아 (1회/전략/일) — 조용히 꺼진 채 매수가 나가는 사고 감지
            self._emit_ratio_cap_config(mode, k, budget, pos_ratio, cap, cutoff)
            if k is None:
                return final                                  # 키 부재 = OFF (조용히)
            if governs:
                if gov_reason == "probe_error":
                    self._emit_ratio_cap_skipped(
                        ticker, "k_axis_probe_error", final, current_price,
                    )
                return final                                  # K축이 심사 = 이중 캡 금지
            if cap <= 0:
                reason = ("no_ratio" if pos_ratio <= 0
                          else "no_budget" if budget <= 0 else "no_cap")
                self._emit_ratio_cap_skipped(ticker, reason, final, current_price)
                return final
            cap_qty = cutoff // current_price
            if final <= cap_qty:
                return final
            self._emit_ratio_notional_blocked(
                ticker, via_fallback=via_fallback, price=current_price, cap=cap,
                cutoff=cutoff, k=k, req_qty=final, capped_qty=cap_qty,
                budget=budget, pos_ratio=pos_ratio,
            )
            return cap_qty
        except Exception:
            # 캡 산출 자체가 던지면 현행 수량 유지 (변경 이전 행위 쪽으로 fail).
            # `logger.debug` 도 emit 과 **같은 try 안** — cycle242 R1/R2 교훈
            # (로거가 죽어도 매수 수량 산출은 살아야 한다).
            try:
                self._emit_ratio_cap_skipped(ticker, "exception", final, current_price)
                logger.debug(
                    "[ratio_cap_skipped] exception ticker=%s", ticker, exc_info=True,
                )
            except Exception:  # pragma: no cover
                pass
            return final

    def _emit_ratio_notional_blocked(
        self, ticker: str | None, *, via_fallback: bool, price: int, cap: int,
        cutoff: int, k: float, req_qty: int, capped_qty: int, budget: int,
        pos_ratio: float,
    ) -> None:
        """`[ratio_notional_blocked]` — 랏 명목이 ρ 상한을 넘어 잘렸다(행위 확정 후 기록).

        cycle245 — §5 결함(1주 폴백 랏 크기가 그 종목 주가로 결정되던 것)의 직접
        증거. INFO, 1회/(전략,ticker)/일(날짜 키 자기 리셋). 캡 자체는 이미
        `_apply_ratio_notional_cap` 이 확정했으므로 여기서의 발화 성패는 매수 수량에
        영향을 주지 않는다(peek → 로그 → mark, cycle226 D-3). `ratio` 는
        `[oversized_fallback]` 의 `ratio` 와 **같은 정의**(명목 ÷ cap)라 두 마커를
        같은 축에서 대조할 수 있다(R7 자기검증).
        """
        try:
            key = f"blk|{ticker or '-'}"
            if not self._ratio_cap_logged.should_emit(key):
                return
            ratio = (req_qty * price / cap) if cap > 0 else 0.0
            path = "fallback" if via_fallback else "sized"
            logger.info(
                "[ratio_notional_blocked] ticker=%s strategy=%s path=%s price=%d "
                "cap=%d cutoff=%d k=%.2f ratio=%.2f req_qty=%d capped_qty=%d "
                "budget=%d pos_ratio=%.4f",
                ticker or "-", self.strategy_id, path, price, cap, cutoff, k, ratio,
                req_qty, capped_qty, budget, pos_ratio,
            )
            self._ratio_cap_logged.mark_emitted(key)
        except Exception:
            trace_observer_failure(
                "[ratio_notional_blocked_failed]", ticker or "-", self._ratio_cap_logged,
            )

    def _emit_ratio_cap_skipped(
        self, ticker: str | None, reason: str, final: int, price: int,
    ) -> None:
        """`[ratio_cap_skipped]` — ρ캡 미적용(현행 수량 유지, fail-open) LOUD.

        reason ∈ {no_ratio, no_budget, no_cap, k_axis_probe_error, exception}.
        WARNING, 1회/(전략,ticker,reason)/일. 예산 배분 결함·코드 결함이 조용히
        지나가지 않게 하되, 매수 자체는 캡 이전 수량 그대로 진행된다(fail-open —
        P0-1 유령 키 재현 방지, fail-closed 구현은 계약 위반). **키 부재**(정상
        OFF 구성)와 **K축 심사**(정상 터틀 랏)는 여기로 오지 않는다 —
        `[ratio_cap_config]` 가 이미 그 상태를 1행으로 기록하기 때문이다.
        """
        try:
            key = f"skip|{ticker or '-'}|{reason}"
            if not self._ratio_cap_logged.should_emit(key):
                return
            logger.warning(
                "[ratio_cap_skipped] ticker=%s strategy=%s reason=%s qty=%d "
                "price=%d — ρ캡 미적용(현행 수량 유지, fail-open)",
                ticker or "-", self.strategy_id, reason, final, price,
            )
            self._ratio_cap_logged.mark_emitted(key)
        except Exception:
            trace_observer_failure(
                "[ratio_cap_skipped_failed]", ticker or "-", self._ratio_cap_logged,
            )

    def _emit_ratio_cap_config(
        self, mode: str | None, k: float | None, budget: int, pos_ratio: float,
        cap: int, cutoff: int,
    ) -> None:
        """`[ratio_cap_config]` — ρ캡 활성 상태 카나리아. INFO, 1회/(전략, 값 조합)/일.

        cap 키가 **값-민감**(`cap 상태 | k | cutoff`)이라 정상 운영에서는 하루 1행이지만
        누가 `PUT /api/strategies/{id}/params` 로 `max_lot_ratio_mult` 를 바꾸거나
        `weight` 변경이 예산을 재분배해 `cutoff_price` 가 달라지면 **그때 1행이 더**
        찍힌다(cycle245 R1 — 공식 롤백 수단을 확인할 채널이 없던 사각).

        캡이 조용히 꺼진 채(`max_lot_ratio_mult` 키 소실 등) 매수가 나가는 사고를
        `cap=off` 존재로 감지한다. 라벨은 **`sizing_mode` 기준**이다(랏별 `governs`
        판정이 아니라) — 이 마커는 하루 첫 랏에서 1회만 찍히므로 랏 단위 판정을
        실으면 그날의 나머지를 대표하지 못한다.

        cap = "off"      (k is None — 키 부재)
            | "backstop" (mode == "turtle" — K축 우선, ρ는 K축이 fail-open 할 때만)
            | "on"       (그 외 = ρ축이 주 상한)

        ⚠️ `cutoff_price` 는 **필수 필드**다 — 운영자가 아침에 한 줄로 "오늘 LTV 는
        130,100원 넘는 종목을 못 산다"를 읽어야 한다(자문 §8.1).
        """
        try:
            if k is None:
                cap_state = "off"
            elif mode == "turtle":
                cap_state = "backstop"
            else:
                cap_state = "on"
            k_desc = "-" if k is None else f"{k:.2f}"
            # cycle245 R1 — cap 키는 **값-민감**이다(`cfg` 단일 키 아님). 공식 롤백
            # 수단(`PUT /api/strategies/{id}/params` → `max_lot_ratio_mult=20.0`)은
            # in-memory 를 즉시 덮어쓰는데, 단일 키면 그날 첫 랏이 이미 cap 을 소진해
            # **변경 후 새 k 를 확인할 마커가 0 개**가 된다(차단이 사라지면
            # `[ratio_notional_blocked]` 도 안 나온다). `weight` PUT 이 예산을
            # 재분배해 `cutoff_price` 가 stale 이 되는 것도 같은 사각이다.
            # 정상 운영에선 값이 안 바뀌므로 여전히 1행/일이고, 실제로 바뀐 날에만
            # 1행이 추가된다 = 폭주 없이 롤백 확인이 회복된다.
            key = f"cfg|{cap_state}|{k_desc}|{cutoff}"
            if not self._ratio_cap_logged.should_emit(key):
                return
            logger.info(
                "[ratio_cap_config] strategy=%s sizing_mode=%s cap=%s k=%s "
                "budget=%d pos_ratio=%.4f cap_notional=%d cutoff_price=%d",
                self.strategy_id, mode, cap_state, k_desc, budget, pos_ratio,
                cap, cutoff,
            )
            self._ratio_cap_logged.mark_emitted(key)
        except Exception:
            trace_observer_failure(
                "[ratio_cap_config_failed]", self.strategy_id, self._ratio_cap_logged,
            )

    def _emit_ratio_cap_clamped(self, raw: object, result: float) -> None:
        """`[ratio_cap_clamped]` — `max_lot_ratio_mult` 가 실제로 클램프됐다. WARNING, 1회/(전략, raw)/일.

        `_read_max_lot_ratio_mult` 가 키가 **존재하는데** 무효/범위밖이라 클램프를
        발동시킬 때만 호출된다(키 부재 = 캡 OFF 라 클램프가 아니고, 호출 자체가
        일어나지 않는다). `raw=` 에 원본 값을 그대로 `repr` 해 "DB 미설정"과
        "PUT 으로 무효 값이 들어와 걸러짐"을 `[ratio_cap_config] k=` 만으로는 구별
        못 하던 사각을 메운다. cap 키는 `raw` 별이다 — 단일 키면 같은 날 두 번째
        범위밖 값이 무음 클램프돼 운영자가 현재 K 를 오판한다(cycle245 R1).
        """
        try:
            # cycle245 R1 — `raw` 별 키. 단일 `clamp` 키면 같은 날 두 번째 범위밖
            # 값이 **무음 클램프**된다(09:30 `0.5` → 13:00 `25.0` 이면 로그엔 raw=0.5
            # 만 남아 운영자가 현재 K 를 2.50 으로 오판한다). 키 길이는 잘라
            # 이상 입력이 cap 사전을 부풀리지 못하게 한다.
            key = f"clamp|{raw!r}"[:96]
            if not self._ratio_cap_logged.should_emit(key):
                return
            logger.warning(
                "[ratio_cap_clamped] strategy=%s raw=%r clamped_to=%.2f "
                "— max_lot_ratio_mult 범위 밖 값이 클램프됨(DB/PUT 확인 필요)",
                self.strategy_id, raw, result,
            )
            self._ratio_cap_logged.mark_emitted(key)
        except Exception:
            trace_observer_failure(
                "[ratio_cap_clamped_failed]", self.strategy_id, self._ratio_cap_logged,
            )

    def get_effective_stop_price(self, ticker: str) -> int | None:
        """포지션의 **현재 실효 손절선**(원) — 척도 병기용 read-only 추정기 (cycle233).

        기본 구현 = None (프록시 폴백 신호 — `portfolio_risk` 가 하드손절% 프록시로
        폴백). 보유형 전략(kojiro/donchian/VCP/BFB)은 자신의 `check_exit_signal`
        가격선들과 **동일 산식·동일 상태 소스**의 max 를 반환하도록 override 한다.
        계약: **read-only** — 래치·`_stop_floor`·로그 어느 것도 변경/발화 금지
        (kojiro `_position_stop_price` 독트린). 가격 무관 청산(시간·stage3·
        measured-move)은 모델 제외.
        """
        return None

    def _account_soft_gate_blocked(self, ticker: str | None = None) -> bool:
        """계좌 SOFT Σ상한 순간 게이트 소비처 (cycle233 M6 — check_buy_signal 최상단).

        `account_risk_watcher.is_soft_gated()` True 면 신규 매수 신호만 차단.
        **fail-open** — import/판정 실패 시 False (매수 경로가 죽지 않는다).
        lazy import — strategy_base 최상위 import 금지 (AST G-5, 순환 차단).
        관측 = `[account_gate_skip]` 1회/전략/일 (날짜 키 자기 리셋).
        """
        try:
            from src.engine import account_risk_watcher
            if not account_risk_watcher.is_soft_gated():
                return False
            try:
                if self._account_gate_logged.should_emit(self.strategy_id):
                    # peek → 로그 → mark (cycle226 D-3 규약)
                    logger.info(
                        "[account_gate_skip] strategy=%s ticker=%s — 계좌 Σ오픈리스크 "
                        "SOFT 상한으로 신규 매수 신호 보류 (청산·손절 무관)",
                        self.strategy_id, ticker or "-",
                    )
                    self._account_gate_logged.mark_emitted(self.strategy_id)
            except Exception:
                trace_observer_failure(
                    "[account_gate_skip_failed]", self.strategy_id, self._account_gate_logged,
                )
            return True
        except Exception:
            # fail-open — 단 완전 무음은 금지(F8): debug 흔적만 남긴다
            # (INFO 이상이면 hot path 폭주 — cap 상태 자체가 위 try 안이라 못 쓴다)
            logger.debug("[account_gate_skip_failed] 게이트 판정 실패 fail-open",
                         exc_info=True)
            return False

    def _emit_budget_clamp(
        self, ticker: str | None, requested: int, clamped: int, remaining: int,
    ) -> None:
        """`[budget_clamp]` 관측 로그 — 1회/(ticker,전략)/일 cap.

        클램프 바인딩 빈도 실측용(부분 매수 정책 재평가 근거). 어떤 실패도 흡수 —
        매수 수량 산출 흐름에 영향 0.

        cycle242 §2.6 — `mark_emitted` 는 `logger.info` **뒤**(peek → 로그 → mark,
        cycle226 D-3 / cycle233 F4 규약). 로그 자기실패가 그날 관측을 지우지 않게.
        """
        try:
            key = ticker or "-"
            if self._budget_clamp_logged.should_emit(key):
                logger.info(
                    "[budget_clamp] ticker=%s strategy=%s requested=%d clamped=%d "
                    "remaining=%d budget=%d",
                    key, self.strategy_id, requested, clamped,
                    remaining, self.state.total_investment,
                )
                self._budget_clamp_logged.mark_emitted(key)
        except Exception:
            trace_observer_failure(
                "[budget_clamp_failed]", ticker or "-", self._budget_clamp_logged,
            )

    # ──────────── 트레일링 기준점 복구 (H-1, 2026-08-06 · 단일 진실원) ────────────

    # 복구 성공 로그의 전략 표기. `None` 이면 `strategy_id` 를 쓴다.
    # donchian/VCP 는 단일 진실원 추출 *이전*의 한글 표기를 그대로 보존한다 —
    # 운영자가 과거 인시던트를 `grep "도치안 스윙 high_since_buy 보정"` 으로 찾는데
    # 접두사가 바뀌면 추출 시점 이후 복구 이력이 0건으로 보인다.
    _HIGH_RECOVER_LABEL: ClassVar[str | None] = None
    # 진입 ATR 재도출(재시작 복구) 로그 접두사 — vcp/bfb/donchian 전략별 (refactor-review A5).
    _ENTRY_ATR_REDERIVE_LABEL: ClassVar[str | None] = None
    # prepare 가격/마스터차단 필터 로그 접두사 — vb/ltv/dc/bfb/vcp (refactor-review A1·A2).
    _PREPARE_LOG_LABEL: ClassVar[str | None] = None
    # 재진입 쿨다운 영업일 정정 실패 로그 접두사 — bfb/vcp/ltv/vb (refactor-review A3).
    _COOLDOWN_LOG_LABEL: ClassVar[str | None] = None

    @staticmethod
    def _candle_trade_date(candle: dict) -> date | None:
        """일봉 1행에서 영업일을 뽑는다 — KIS 원본 키 / 정규화 컬럼 양쪽 수용.

        `stck_bsop_date` = KIS 원본(`"20260722"` 문자열) · `bas_dd` = DB 정규화
        컬럼(asyncpg 가 `date` 객체로 반환). 어댑터 `get_recent_daily_normalized`
        는 raw JSONB 가 없는 row 를 **row 자체로** 돌려주므로, 한 형태만 읽으면
        그 종목의 봉이 조용히 전부 skip 된다.
        """
        raw = candle.get("stck_bsop_date") or candle.get("bas_dd")
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        text = str(raw or "").replace("-", "")[:8]
        if len(text) != 8 or not text.isdigit():
            return None
        try:
            return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        except ValueError:
            return None

    @staticmethod
    def _candle_high(candle: dict) -> int:
        """일봉 1행의 고가 — KIS `stck_hgpr` / 정규화 `high_price`. 실패 시 0.

        ⚠️ `except Exception` 이 계약이다. `int(float("inf"))` 은
        `(TypeError, ValueError)` 가 아니라 **OverflowError** 를 던지는데, 이게
        새어 나가면 봉 하나가 `_apply_high_since_buy_from_candles` 를 통째로
        중단시켜 **같은 루프의 남은 보유 종목까지** 그날 복구를 잃는다
        (donchian 은 뒤따르는 `_breakout_high`/`_channel_low` 재도출도 함께 유실).
        추출 실패는 "그 봉만 버린다"여야 한다.
        """
        raw = candle.get("stck_hgpr")
        if raw is None or raw == "":
            raw = candle.get("high_price")
        try:
            return int(float(raw))
        except Exception:
            return 0

    async def _apply_high_since_buy_from_candles(
        self, pos, candles: list[dict], today,
    ) -> None:
        """일봉 응답의 `buy_date < 영업일 < today` 범위 high max 로 고점을 보정한다.

        보정값이 기존 `high_since_buy` 를 **초과할 때만** 갱신 + DB UPDATE +
        `system_logs` 1행. 시세 미수신 누적 또는 재시작(`_boot` 이 DB row 로
        Position 을 재생성)으로 트레일링 기준점이 매수가 부근에 동결되는 결함을
        회복한다.

        경계가 엄격한 이유 — **과대복구 구조적 차단**:
          - 매수일 당일 제외: 그 날 고가는 매수 *전* 구간을 포함할 수 있어
            실제로 보유하지 않은 고점을 잡는다(샹들리에 과대 → 조기 청산).
          - 오늘 제외: 장중 미확정 봉.
        따라서 남는 오차는 과소복구 한 방향뿐이고 그 방향은 청산을 늦춘다.

        단일 진실원 — donchian_swing / vcp_breakout / kojiro 공유. 로그 접두사만
        다른 복사본이 전략 파일마다 생기면 세 곳이 드리프트한다(회귀 가드
        `test_kojiro_high_since_buy_recovery.py::test_no_duplicate_helper_definition_in_strategy_files`).
        """
        eligible_highs: list[int] = []
        for c in candles:
            bd = self._candle_trade_date(c)
            if bd is None or not (pos.buy_date < bd < today):
                continue
            hi = self._candle_high(c)
            if hi > 0:
                eligible_highs.append(hi)

        if not eligible_highs:
            return
        candidate = max(eligible_highs)
        if candidate <= pos.high_since_buy:
            return

        prev = pos.high_since_buy
        pos.high_since_buy = candidate
        label = self._HIGH_RECOVER_LABEL or self.strategy_id
        logger.info(
            "%s high_since_buy 보정: %s %d → %d (매수일 %s 이후 %d영업일 일별 high max)",
            label, pos.ticker, prev, candidate,
            pos.buy_date, len(eligible_highs),
        )
        # DB 영속화 + system_logs (fire-and-forget — 실패해도 메모리 보정은 유지)
        try:
            from src.db.positions import update_high
            await update_high(pos.ticker, candidate)
        except Exception:
            logger.exception("%s high_since_buy DB UPDATE 실패: %s", label, pos.ticker)
        try:
            from src.db.system_logs import write_log
            await write_log(
                "INFO",
                f"[high_since_buy_recover] ticker={pos.ticker} prev={prev} "
                f"new={candidate} days={len(eligible_highs)} buy_date={pos.buy_date}",
            )
        except Exception:
            pass

    @staticmethod
    def _atr(highs, lows, closes, period: int) -> float:
        """ATR(period) — 최근 period일 True Range **단순평균(SMA)**.

        highs/lows/closes 최신순(idx=0 이 어제), closes[i+1]=직전일 종가.
        ⚠️ SMA baseline — kojiro Wilder ATR(kojiro_indicators.atr, ewm α=1/N)과 정의가
        다르다. kojiro 는 self._atr 을 쓰지 않는다(ATR 이원화 봉인, 회귀 가드
        test_refactor_a5a6_atr_base.py). donchian/VCP/BFB 공유 (refactor-review A6).
        """
        if len(highs) <= period or len(lows) <= period or len(closes) <= period + 1:
            return 0.0
        trs = []
        for i in range(period):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i + 1]),
                abs(lows[i] - closes[i + 1]),
            )
            trs.append(tr)
        return sum(trs) / period

    def _rederive_entry_atr(self, ticker: str, pos, candles: list, atr_period: int) -> None:
        """재시작으로 소실된 `_entry_atr` 을 **매수일 이전 봉만으로** 재도출 (loosen 차단).

        매수일 당일/이후 봉을 섞으면 돌파 당일 변동이 ATR 을 부풀려 손절선이 넓어진다.
        진입 시점 ATR 재현이 목적이라 `bsop_date < buy_date` 만 사용. 봉 부족/실패 시
        미스탬프 — 고정% 손절 경로로 남는 편이 잘못된 ATR 손절선보다 낫다.

        단일 진실원 — donchian/VCP/BFB 공유 (refactor-review A5). 로그 접두사는
        `_ENTRY_ATR_REDERIVE_LABEL` 로 전략별 보존(운영자 grep 이력, _HIGH_RECOVER_LABEL 선례).
        """
        label = self._ENTRY_ATR_REDERIVE_LABEL or self.strategy_id
        try:
            buy_dd = pos.buy_date.strftime("%Y%m%d")
            prior = [c for c in candles if str(c.get("stck_bsop_date", "")) < buy_dd]
            if len(prior) < atr_period + 2:
                return
            highs = [int(c.get("stck_hgpr", "0") or 0) for c in prior]
            lows = [int(c.get("stck_lwpr", "0") or 0) for c in prior]
            closes = [int(c.get("stck_clpr", "0") or 0) for c in prior]
            e_atr = self._atr(highs, lows, closes, atr_period)
            if e_atr > 0:
                self._entry_atr[ticker] = float(int(e_atr))
                logger.info("[%s_entry_atr_rederive] %s buy_date=%s entry_atr=%d",
                            label, ticker, pos.buy_date, int(e_atr))
        except Exception:
            logger.exception("[%s_entry_atr_rederive] 재도출 실패: %s", label, ticker)

    async def _refine_cooldown_business_days(self, ticker: str) -> None:
        """재진입 쿨다운을 정확한 N영업일로 정정 (refactor-review A3, 단일 진실원).

        1단계(`register_cooldown_after_exit`)가 즉시 달력일 근사(days+2)로 세팅한
        `_cooldown_until[ticker]` 를, KIS `chk-holiday`(CTCA0903R) 1회 호출로 정확한
        N영업일로 교체한다. 실패 시 1단계 근사값을 그대로 유지(graceful).

        bfb/vcp/ltv/vb 4 전략에 로그 접두사만 다른 byte-identical 4벌로 존재하던 것을
        base 로 승격(H-1 `_apply_high_since_buy_from_candles` 선례 동형). 로그 접두사는
        `_COOLDOWN_LOG_LABEL` ClassVar 로 전략별 보존.

        ⚠️ `add_business_days` 는 `src.api.condition` 을 base 에서 직접 참조하지 않고
        **concrete 전략 모듈 네임스페이스**(`sys.modules[type(self).__module__]`)에서
        resolve 한다 — cycle191/201/213 테스트 + 본 메서드 행위 테스트가 전략 모듈
        바인딩(`monkeypatch.setattr(<strategy_mod>, "add_business_days", ...)`)을
        패치하기 때문(stale_manager `sys.modules.get` 패턴 답습).
        """
        days = self.config.params["reentry_cooldown_days"]
        today = datetime.now(_KST).date()
        try:
            import sys as _sys

            _mod = _sys.modules.get(type(self).__module__)
            _add_business_days = getattr(_mod, "add_business_days", None)
            if _add_business_days is None:
                from src.api.condition import add_business_days as _add_business_days  # 폴백

            accurate = await _add_business_days(today, days)
            self._cooldown_until[ticker] = accurate
        except Exception:
            logger.warning(
                "%s 영업일 정정 실패 (ticker=%s) — 근사값 유지",
                self._COOLDOWN_LOG_LABEL, ticker,
            )

    async def _apply_master_block_filter_in_prepare(
        self, tickers: list[str]
    ) -> tuple[list[str], list[dict]]:
        """prepare 영역 1단계 진입 차단 13건 hook (사이클 157, refactor-review A2 base 승격).

        사이클 32 R4 보유/익일청산 절대 보호 + scanner.apply_master_block_filter 위임.
        로그 접두사는 `_PREPARE_LOG_LABEL` 로 전략별 보존(vb/ltv/dc/bfb/vcp). donchian/VCP/
        VB/LTV/BFB 공유 — kojiro 는 자체 정의 유지(FREEZE, override).

        Returns:
            (survived, excluded). excluded = [{ticker, name, reason}] (사이클 41 답습).
        """
        from src.engine import scanner as _scanner_mod

        label = self._PREPARE_LOG_LABEL or self.strategy_id
        protected: set[str] = set()
        try:
            protected = _scanner_mod._collect_protected_tickers_for_scanner()
        except Exception:
            logger.debug(
                "[%s_master_block_prepare] protected_tickers 조회 실패 graceful",
                label, exc_info=True,
            )
        return await _scanner_mod.apply_master_block_filter(
            tickers, protected_tickers=protected
        )

    async def _apply_price_filter_in_prepare(self, tickers: list[str]) -> list[str]:
        """prepare 영역 가격 필터 후처리 (사이클 148/151, refactor-review A1 base 승격).

        사이클 64 scanner `_apply_price_filter` 패턴 답습 + PriceFilter 단일 source.
        보유 종목 절대 보호 (사이클 32 R4) + raw.bfdy_clpr miss graceful 통과.
        로그 접두사는 `_PREPARE_LOG_LABEL` 로 전략별 보존(vb/ltv/dc/bfb/vcp).

        - PriceFilter 비활성 (min=0, max=0) → 전체 통과 (회귀 보존)
        - 보유 종목 → 무조건 통과 (사이클 30 005935 매매 안전성 영속)
        - raw.bfdy_clpr miss → graceful 통과 (사이클 64 답습)
        - min_price > 0 + bfdy_clpr < min_price → 차단
        - max_price > 0 + bfdy_clpr > max_price → 차단 (운영 실증 6/16)
        """
        from src.db import stock_master as _sm_mod
        from src.db.system_config import get_price_filter

        pf = await get_price_filter()
        if not pf.is_active:
            return tickers

        label = self._PREPARE_LOG_LABEL or self.strategy_id
        # 보유 종목 절대 보호 (사이클 32 R4 + 사이클 64 Q1 옵션 D 답습)
        protected: set[str] = set()
        try:
            from src.engine import scanner as _scanner_mod
            protected = _scanner_mod._collect_protected_tickers_for_scanner()
        except Exception:
            logger.debug(
                "[%s_price_filter_prepare] protected_tickers 조회 실패 graceful",
                label, exc_info=True,
            )

        survivors: list[str] = []
        for ticker in tickers:
            if ticker in protected:
                survivors.append(ticker)
                continue
            prdy_clpr = 0
            try:
                basics = await _sm_mod.get(ticker)
                if basics and basics.raw:
                    raw_val = basics.raw.get("bfdy_clpr", 0)
                    if raw_val:
                        prdy_clpr = int(raw_val)
            except Exception:
                logger.debug(
                    "[%s_price_filter_prepare] stock_master 조회 실패 graceful: %s",
                    label, ticker, exc_info=True,
                )

            if prdy_clpr <= 0:
                # graceful 통과 (사이클 64 Q2 답습 — 신규 상장 영구 차단 방지)
                survivors.append(ticker)
                continue

            below_min = pf.min_price > 0 and prdy_clpr < pf.min_price
            above_max = pf.max_price > 0 and prdy_clpr > pf.max_price
            if not (below_min or above_max):
                survivors.append(ticker)

        return survivors
