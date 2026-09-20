"""주문 실행 엔진.

- 매수/매도 주문 실행 및 결과 처리
- 중복 주문 차단
- 부분 체결 관리 (PARTIAL 상태 기록, 30초 후 잔여 취소)
- 손절 부분 체결 시 잔여 재주문
- trade_history DB 기록
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from src.api.balance import (
    get_buyable,
    is_insufficient_cash,
    is_insufficient_quantity,
    is_market_closed_rejection,
    is_market_order_disallowed,
    is_sell_qty_exceeded,
)
from src.engine.util.tick_size import step_down, step_up
from asyncpg.exceptions import UniqueViolationError
from src.api.base import KisApiError
from src.api.order import cancel_order, place_order
from src.db.system_logs import write_log, safe_write_log
from src.db.trade_history import (
    insert_trade,
    update_trade_status,
    _lookup_strategy_from_trade_history,
    _update_trade_status_by_order_no,
)
from src.engine.daily_emit_cap import DailyEmitCap
from src.engine import llm_buy_gate
from src.engine.sell_rejection import SellRejectionTracker, is_krx_main_hours, is_nxt_session_hours
from src.engine.strategy_base import Position, Signal, StrategyBase
from src.engine.strategy_registry import StrategyRegistry
from src.engine.scanner import t
from src.models.order import OrderDivision, OrderSide
from src.models.trade import TradeRecord, TradeStatus, TradeType

logger = logging.getLogger(__name__)

# KST timezone — scanner.KST_TZ 와 동일 (circular import 방지용 재정의)
_KST_TZ = timezone(timedelta(hours=9))

# ─────────────────────────── cycle287 — 시각이 거래소·호가유형을 정한다 ───────
# (2026-09-12, 자문 `cycle287_domain_consult` §1·§4·§9). 규칙 1(라우팅)과
# 규칙 2(KRX 애프터마켓 41/44)가 같은 파일에 산다 — 분리 배포하면 규칙 1 단독은
# 오늘(2026-09-12)보다 나쁘다(§2-C: 09-14 부터 KRX 애프터가 `01`도 `00`도
# 받지 않는데 라우팅만 켜면 지금 NXT 애프터에서 체결되던 청산 경로가 사라진다).
#
# `_CLOCK_ROUTED_BASES` — 이 두 값만 시각 재판정 대상이다. `KRX` 가 여기 들어오면
# `nxt_tradable=False` 다운그레이드가 내린 `KRX` 를 라우터가 되돌리려 들게 되므로
# (프리장에서 그 값이 "복귀"하면 NXT 비대상 종목에 NXT 주문이 나간다) 절대 넣지
# 않는다.
_CLOCK_ROUTED_BASES: tuple[str, ...] = ("NXT", "SOR")

# 우리가 실제로 KIS 에 보낼 수 있는 호가유형 — `OrderDivision` 값 집합과 항상
# 동치여야 한다(enum 확장 시 이 상수도 함께 넓어진다, `test_r1e`). 판정의 전제가
# "우리가 보낼 수 있는 코드" 라서, 이 둘이 갈리면 판정이 조용히 거짓이 된다.
_SENDABLE_DIVISIONS: frozenset[str] = frozenset(d.value for d in OrderDivision)

# 킬스위치 기본값 — 두 신규 파라미터(`order_exchange_clock_mode`·
# `after_market_exit_division`)는 브리프 제약(전략 7파일 diff 0)으로 이 사이클엔
# 어느 전략 `DEFAULT_PARAMS` 에도 없다. 이 모듈 상수가 유일한 정본이고,
# 키 부재 = 이 값이다(cycle287b 가 param_catalog/DEFAULT_PARAMS 에 등재할 때까지).
_ORDER_EXCHANGE_CLOCK_MODE_DEFAULT: str = "enforce"
_AFTER_EXIT_DIVISION_DEFAULT: str = "44"
#: 화이트리스트(클램프 아님) — 밖은 `44` 로 폴백해 청산을 여는 방향으로 떨어진다.
_AFTER_EXIT_DIVISION_ALLOWED: frozenset[str] = frozenset({"44", "41"})
#: K9 봉인2 — 종목당 그 저녁 실패 임계. 상한 검산 = 종목당 ≤10 주문(5회 ×
#: 1차+폴백) / 보유 7종목 전건 실패 ≤70 주문/저녁(KIS 20/s 대비 무해).
_AFTER_EXIT_GIVEUP_THRESHOLD: int = 5


def _resolve_exit_capable_krx_phases() -> frozenset:
    """§4-I 상수 계산 전용 — `market_state` 는 이 함수 **안**에서만 읽는다.

    모듈 최상단에 `from src.engine.market_state import MarketPhase` 를 두면
    `test_s3e`(`order_engine.py` 최상단 `src.*` import 집합 고정)가 즉시 RED 다.
    이 함수는 모듈 로드 시 **한 번** 호출되어 `_EXIT_CAPABLE_KRX_PHASES` 를
    채우고, import 문 자체는 함수 본문 안(비-최상단)에 남는다.
    """
    from src.engine.market_state import MarketPhase

    return frozenset({
        MarketPhase.REGULAR, MarketPhase.CLOSE_AUCTION, MarketPhase.AFTER_MARKET,
    })


#: TTL 축(§4-I) 정의 = "그 시각 KRX 가 우리 청산 호가를 받는가". 09-14 **이전**에는
#: `sell_rejection.is_krx_main_hours`(09:00~15:30)와 완전히 일치한다(K7 AFTER_SINGLE
#: 은 집합 밖). 09-14 부터 AFTER_MARKET(K6) 하나만 늘어난다. ⚠️ `PRE_AUCTION`(시가
#: 단일가)을 넣지 않는다 — 그 창의 거부는 09:00 재평가를 기다리는 것이 옳고, 5분
#: TTL 로 줄이면 단일가에 시장가를 반복 발사한다.
_EXIT_CAPABLE_KRX_PHASES = _resolve_exit_capable_krx_phases()


def _route_exchange_by_clock(
    base: str,
    *,
    side: str = "sell",
    mode: str = "enforce",
    now: datetime | None = None,
) -> tuple[str, str]:
    """규칙 1 — 시각이 거래소를 정한다(자문 §1·§9-B). 순수 함수, never-raise.

    판정 순서(첫 성립에서 반환) — 시각 리터럴은 여기 0건이다. 경계는
    `market_state.MARKET_TABLE`(유일 정본)에서 나온다:

      1. base ∉ {"NXT","SOR"}                               -> (base, "base_krx")
      2. mode == "off"                                      -> (base, "mode_off")
      3. mode == "sell_only" ∧ side != "sell"                -> (base, "mode_sell_only")
      4. PRE_NXT ∈ session_tracker.active ∧ MAIN ∉ active    -> (base, "pre_nxt_keep")
      5. _SENDABLE_DIVISIONS ∩ KRX.order_divisions ≠ ∅       -> ("KRX", "krx_by_clock")
      6. _SENDABLE_DIVISIONS ∩ NXT.order_divisions ≠ ∅       -> (base, "krx_unsupported_keep")
      7. else                                                -> (base, "both_unsupported_keep")
      예외                                                    -> (base, "probe_error")  # fail-open

    프리장 clause 는 매수 PR-F·매도 프리장 사전 지정가 변환과 **같은 출처**
    (`session_tracker.active`)를 읽는다 — 08:50~09:00(NXT N2 휴장)에 여기서
    `market_state` 의 NXT phase 를 쓰면 그 사전 변환이 죽어 시가 단일가에
    시장가가 나간다(자문 §1-B·§G).
    """
    try:
        if base not in _CLOCK_ROUTED_BASES:
            return base, "base_krx"
        if mode == "off":
            return base, "mode_off"
        if mode == "sell_only" and side != "sell":
            return base, "mode_sell_only"

        from src.engine.session import MarketBoard, boards_at, session_tracker

        moment = now if now is not None else datetime.now(_KST_TZ)
        active = session_tracker.active
        if not active:
            # 적대 검증 시정(MEDIUM — exit lens M1 / test lens M4) —
            # `session_tracker.active` 는 `tick()`(30초 주기)이 채우는 **캐시**라
            # 기동 직후 첫 tick 전에는 빈 집합이다. 그 순간이 08:20~09:00 프리장
            # 창과 겹치면 이 clause 가 실패해 아래 KRX 판정으로 떨어지고,
            # KRX PRE_AUCTION(시가 단일가)이 마침 시장가를 받아 조용히 KRX 로
            # 나간다 — 사전 지정가 변환(PR-F)이 같은 `session_tracker.active`
            # 를 읽어 함께 실패하므로 겉으로는 "정상 접수"처럼 보이지만
            # NXT 프리장 매매 의도와 다른 시장으로 샌 것이다. `boards_at`
            # (session.py 의 순수 함수, 파일 자체는 무접촉)로 그 순간의
            # 스케줄을 즉석 재계산해 캐시가 비었을 때만 보강한다 — 캐시가
            # 채워져 있으면(정상 상태) 이 분기는 진입하지 않아 기존 판정과
            # 완전히 동일하다.
            active = boards_at(moment.time())
        if MarketBoard.PRE_NXT in active and MarketBoard.MAIN not in active:
            return base, "pre_nxt_keep"

        from src.engine.market_state import get_market_state

        krx_divisions = set(get_market_state(moment, market="KRX").order_divisions)
        if _SENDABLE_DIVISIONS & krx_divisions:
            return "KRX", "krx_by_clock"
        nxt_divisions = set(get_market_state(moment, market="NXT").order_divisions)
        if _SENDABLE_DIVISIONS & nxt_divisions:
            return base, "krx_unsupported_keep"
        return base, "both_unsupported_keep"
    except Exception:
        return base, "probe_error"


def _exit_capable_krx_window(now: datetime) -> bool:
    """§4-I — 그 시각 KRX 가 우리 청산 호가유형을 받는가(TTL 축 재정의).

    `sell_rejection.py` 는 diff 0 이다 — 이 함수는 그 파일을 고치는 대신
    호출부(`register_market_closed` 의 `in_krx_main_hours=`)가 넘기는 인자의
    **의미**를 "매도 가능 창 안인가" 로 재정의한다. 09-14 이전에는
    `is_krx_main_hours` 와 값이 완전히 같고, 09-14 부터 KRX 애프터마켓
    (16:00~20:00) 하나만 늘어난다. 판정 예외는 그 함수로 fail-open 한다.
    """
    try:
        from src.engine.market_state import get_market_state

        return get_market_state(now, market="KRX").phase in _EXIT_CAPABLE_KRX_PHASES
    except Exception:
        return is_krx_main_hours(now)


def _classify_after_exit_rejection(e: KisApiError) -> str:
    """K10 — 애프터 거부 관측 분류(관측 전용, 폴백 게이트에는 쓰이지 않는다).

    애프터 폴백은 분류에 의존하지 않는 **구조적 폴백**이다(자문 §1-E) — 44 거부의
    msg1 원문이 완전 미지라 이 분류는 오직 `[after_exit_rejected]` 판독용이다.
    """
    if is_market_closed_rejection(e):
        return "closed"
    if is_market_order_disallowed(e):
        return "disallowed"
    return "unclassified"


def _market_rest_now(now: datetime) -> tuple[bool, str]:
    """cycle295 (B) — 순수·never-raise 술어, 모듈 레벨. 시각 리터럴 0건.

    2026-09-15 사용자 결정 — 프리장은 NXT, 그 밖에는 KRX 가 우리 호가유형을
    받을 때만 주문한다. 「15:30~16:00 완전 휴식」은 그 규칙의 따름정리다.

    (가) 사실 — 15:40~16:00 은 KRX 에 연속 체결이 없고 NXT 애프터만 continuous 다
         (`market_state.MARKET_TABLE` 파생. 감시자 = `test_cycle294b::test_n1`).
    (나) cycle294 의 판단 — 따라서 그 구간을 KRX 채널로 덮으면 `nxt_true` 보유의
         손절 커버리지가 매일 20분 사라진다. **이 문장은 여전히 참이다.**
    (다) 2026-09-15 사용자 결정 — "청산측으로도 참여를 하지 않고자 해.
         15:30~16:00 은 완전 휴식하도록 변경해야해." 그 20분의 커버리지 손실을
         **비용으로 수용**했다. 결함이 아니라 결정이다 — 되돌리기 전에
         `_workspace/00_URGENT_WORKLIST.md` 의 2026-09-15 결정을 확인하라.

    🔴 이 함수를 라우터(`_route_exchange_by_clock`) **안**에 넣지 않는다(§3-2 —
    `_probe_nxt_downgrade_base` 가 `nxt_tradable=False` 코호트(마스터 83.2%)를
    `base="KRX"` 로 만들어 clause 1 에서 즉시 반환되므로, 라우터 안에 두면 컷이
    가장 필요한 다수 코호트를 통째로 비껴간다). 대신 주문 발사점
    (`execute_sell`/`execute_buy`/`_cancel_and_reorder`)에서만 이 술어를 부른다.
    """
    try:
        from src.engine.market_state import get_market_state
        from src.engine.session import MarketBoard, boards_at, session_tracker

        active = session_tracker.active or boards_at(now.time())
        if MarketBoard.PRE_NXT in active and MarketBoard.MAIN not in active:
            # 프리장 예외 — 라우터 clause 4·매도 프리장 사전 지정가 변환과
            # 같은 출처(`session_tracker.active`)로 판정한다(§3-3 근거 3).
            return False, "pre_nxt_keep"

        krx = get_market_state(now, market="KRX")
        if _SENDABLE_DIVISIONS & set(krx.order_divisions):
            return False, "krx_sendable"  # KRX 가 우리 호가유형을 받는다

        nxt = get_market_state(now, market="NXT")
        if not krx.order_divisions and not nxt.order_divisions:
            return False, "no_session"  # 야간 — 현행 안전망 보존

        return True, "market_rest"
    except Exception:
        return False, "probe_error"  # fail-open


def _market_rest_window_bounds(now: datetime) -> tuple[int, int] | None:
    """§3-6 카나리아 전용 — 정오 이후 KRX 가 우리 호가유형을 처음 안 받는 분과
    다시 받는 분(분 단위, `[start, end)`). `market_state` 표에서 역산한다 —
    리터럴이 아니다. 못 찾으면 `None`(카나리아는 그 호출에서 조용히 스킵).
    """
    from src.engine.market_state import get_market_state

    on_date = now.date()
    start: int | None = None
    for minute in range(720, 1440):
        moment = datetime(
            on_date.year, on_date.month, on_date.day,
            minute // 60, minute % 60, tzinfo=_KST_TZ,
        )
        sendable = bool(
            _SENDABLE_DIVISIONS & set(get_market_state(moment, market="KRX").order_divisions)
        )
        if start is None:
            if not sendable:
                start = minute
        elif sendable:
            return start, minute
    return None


def _compute_next_market_open_kst(now: datetime) -> datetime:
    """now KST 기준 다음 KRX 정규시간 시작 시각 (09:00) 반환.

    now < 09:00 KST → 당일 09:00.
    now >= 09:00 KST → 다음 영업일 09:00 (주말 스킵, KIS 휴장 처리는 후속 사이클 보류).
    """
    today_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now < today_open:
        return today_open
    # 다음 영업일: 주말 스킵 (토→+2일, 일→+1일, 평일→+1일)
    next_day = now + timedelta(days=1)
    while next_day.weekday() >= 5:  # 5=토, 6=일
        next_day += timedelta(days=1)
    return next_day.replace(hour=9, minute=0, second=0, microsecond=0)


PARTIAL_FILL_WAIT = 30  # 부분 체결 후 잔여 취소 대기(초)

#: cycle332 — 취소 타이머 축. 매수·매도가 `_pending_cancel_tasks` 를 공유하되
#: **서로를 죽이지 않도록** 키에 실린다. 리터럴을 두 등록 함수에 흩어 두면
#: 한쪽 오타가 조용히 옛 충돌을 되살리므로 여기 한 곳에만 둔다.
CANCEL_AXIS_BUY = "buy"
CANCEL_AXIS_SELL = "sell"


def pending_cancel_tickers(engine) -> list[str]:
    """`_pending_cancel_tasks` 를 **ticker 배열**로 편다 (UI 계약 보존, cycle332).

    키가 `(ticker, side)` 복합으로 바뀌어도 `GET /api/trading/status` 의
    `pending_cancels` 는 여전히 종목코드 배열이다 —
    `frontend/src/types/trading.ts` 와 `OrderMonitor.tsx` 가 그렇게 그린다.
    한 종목에 두 축 타이머가 동시에 걸려 있어도 **한 번만** 나온다.
    """
    try:
        return sorted({tk for tk, _ in engine._pending_cancel_tasks.keys()})
    except Exception:
        return []
SELL_MAX_RETRIES = 3     # 매도 실패 시 최대 재시도 횟수
SELL_RETRY_DELAY = 1.0   # 재시도 간격(초)
BUYABLE_CACHE_TTL = 60.0  # get_buyable 캐시 유효시간(초)
BUY_BLOCK_DURATION = 900.0  # 잔고 부족 락 기본 지속(초) — 다음 잔고 sync(15분)와 정합
LOW_FUNDS_COOLDOWN = 900.0  # per-ticker 매수 수량 0 cooldown — 잔고 sync(15분)와 동일 주기


class OrderEngine:
    """주문 실행 엔진."""

    def __init__(self, registry: StrategyRegistry) -> None:
        self.registry = registry
        # cycle332 — 키가 `(ticker, side)` 복합이다. 종전 ticker 단독 키에서는
        # 매수 잔량 취소(`_schedule_cancel`)와 매도 손절 잔여 재주문
        # (`_schedule_cancel_and_reorder`)이 같은 슬롯을 다퉈 **나중에 걸린 쪽이
        # 앞선 쪽을 order_no 검사 없이 죽였다**. 해제는 cycle273a 가 order_no 게이트로
        # 좁혀 두었는데 등록만 안 좁혀져 있던 것이고, 이 키가 그 미완성 규약을 완성한다.
        # 🔴 잃는 것 = 급락장에서 손절 잔여가 **체결도·재주문도·재평가도** 못 받는다
        # (원 매도 주문이 호가에 남고 `_selling` 이 안 풀려 `risk.on_tick` 이 건너뛴다).
        self._pending_cancel_tasks: dict[tuple[str, str], asyncio.Task] = {}  # (ticker, side) -> 취소 대기 태스크
        # cycle273a (D2-가-a) — 위 dict 와 항상 짝으로 갱신되는 order_no 그림자.
        # 키가 ticker 이고 매수(`_schedule_cancel`)·매도(`_schedule_cancel_and_reorder`)가
        # 같은 dict 를 공유하므로, 전량 체결 시 "이 order_no 의 타이머일 때만" 해제하기
        # 위한 게이트 값이다(§1.4 — pop(ticker) 단독은 남의 타이머를 실종시킨다).
        self._pending_cancel_order_no: dict[tuple[str, str], str] = {}  # (ticker, side) -> 그 타이머가 지키는 order_no
        self._filled_qty: dict[str, int] = {}  # order_no -> 누적 체결 수량
        self._order_qty: dict[str, int] = {}   # order_no -> 원래 주문 수량
        self._pending_buy_orders: dict[str, dict] = {}  # order_no -> {ticker, price, quantity, strategy_id}
        self._order_strategy: dict[str, str] = {}  # order_no -> strategy_id
        self._order_ticker: dict[str, str] = {}   # order_no -> ticker (체결통보 종목코드 보정용)
        # cycle287 적대 검증 시정 — order_no -> 그 주문이 실제로 나간 거래소.
        # 취소 경로가 취소 시각의 라우터 재평가 대신 이 값을 우선 사용한다
        # (원주문·취소가 시간 경계를 사이에 두고 다른 거래소로 갈리는 것을 막는다).
        self._order_exchange: dict[str, str] = {}
        # cycle291 — order_no -> 그 주문에 실제로 실린 ORD_DVSN 값(전송한 것만
        # 기록 — 지역변수가 아니라 `place_kwargs` 에서 뽑는다). `_order_exchange`
        # 와 완전 대칭(같은 등록 자리·같은 pop·같은 clear) — 취소 축 Stage A
        # 관측(`[after_cancel_result]` 의 `orig_dvsn=`)이 소비한다.
        self._order_division: dict[str, str] = {}
        # cycle291 적대 검증 시정(B5) — `[pre_nxt_division_config]` 카나리아 cap.
        # DailyEmitCap[str] 단일 키("config") 1회/일. `_order_channel_config_logged`
        # 와 같은 패턴, 별개 인스턴스(값-무관 순수 1회/일이라 tuple 키 불필요).
        self._pre_nxt_division_config_logged: DailyEmitCap[str] = DailyEmitCap[str]()
        self._selling: set[str] = set()  # 매도 진행 중인 종목 (중복 매도 차단)
        self._selling_since: dict[str, datetime] = {}  # ticker -> _selling 진입 시각 (KST). stale 재대조 age gate.
        # 체결통보가 place_order 응답보다 먼저 도착해 COMPLETED row를 직접 INSERT한 order_no.
        # 뒤늦게 도착한 execute_buy/execute_sell이 PENDING row를 추가 INSERT하는 것을 막기 위함.
        self._completed_orders: set[str] = set()
        # P1-B (2026-07-29) — 전량 체결 완료된 order_no 멱등 가드. 사이클 30 `_completed_orders`
        # (선행 race 보정 INSERT 용도) 와 분리 — 후속 중복 체결통보를 즉시 무시해
        # momentum 하드코딩 폴백으로 타 전략 포지션이 실명되는 결함(377450 실사고) 차단.
        self._completed_buy_orders: set[str] = set()
        # 사이클 15-A (2026-05-19) — 매도 체결 후 WS unsubscribe hook 의 pending_next_day_clear 조회 provider.
        # scheduler 가 setattr 로 주입. 기본은 빈 set 반환 (테스트/단독 사용 안전).
        self._pending_next_day_clear_provider = lambda: set()
        # 사이클 55 R-1 (2026-06-03) — SellRejectionTracker 단일 정책 객체.
        # 사이클 52 B-1 의 2 필드 (_market_closed_blocked / _market_closed_blocked_logged_today)
        # 를 통합. 호환 layer property 2개 로 기존 참조 보존.
        self._sell_rejection = SellRejectionTracker()
        # 사이클 56-C (2026-06-04) — DailyEmitCap[str] 으로 마이그레이션.
        # 사이클 54 set[str] → DailyEmitCap[str] 호환 layer 경유 (add/clear/__contains__).
        # 다운그레이드 결정 무영향, 로그만 cap. _reset_daily_state 동행 clear.
        self._nxt_downgrade_logged_today: DailyEmitCap[str] = DailyEmitCap[str]()
        # cycle287 — 규칙 1 관측 cap. 키 = (ticker, side, reason) / (strategy_id, mode, dial).
        # `base == routed` 인 정규장·프리장 폭주(초당 1틱)를 하루 1행으로 접는다.
        self._order_channel_logged: DailyEmitCap[tuple] = DailyEmitCap[tuple]()
        self._order_channel_config_logged: DailyEmitCap[tuple] = DailyEmitCap[tuple]()
        # cycle287 K9 봉인2 — (ticker, KST date) -> 그 저녁 애프터 청산 실패 횟수.
        # `_AFTER_EXIT_GIVEUP_THRESHOLD` 도달 시 그날 밤은 포기(다음 09:00 래치).
        self._after_exit_fails: dict = {}
        # cycle295 (B) — 15:30~16:00 주문 컷 관측 cap. `KstDailyEmitCap` 은 KST
        # 날짜 경계에서 자기 리셋하므로 `reset_daily_state()` 배선이 불필요하다
        # (§3-6). 키 = (ticker, side) — `[market_rest_blocked]` 1회/(ticker,side)/일.
        # lazy import — 모듈 최상단 `src.*` import 집합 불변 계약(`test_c4_2` 등)을
        # 지킨다. 애노테이션도 그 별칭을 쓴다(원 이름은 모듈 스코프에 없어
        # `get_type_hints`/mypy/pyflakes 가 해석에 실패한다).
        from src.engine.daily_emit_cap import KstDailyEmitCap as _KstDailyEmitCap

        self._market_rest_blocked_cap: "_KstDailyEmitCap[tuple[str, str]]" = _KstDailyEmitCap()
        # `[market_rest_window]` 카나리아 — 1회/일(단일 키, 차단 여부 무관).
        self._market_rest_window_cap: "_KstDailyEmitCap[str]" = _KstDailyEmitCap()
        # cycle329 — 주문수량 출처 관측. `map` 은 DEBUG 라 cap 밖이고,
        # `payload`/`increment` 만 1회/(출처,종목,방향)/일로 WARNING 을 낸다.
        self._fill_qty_src_logged: "_KstDailyEmitCap[str]" = _KstDailyEmitCap()
        self._ordered_qty_mismatch_logged: "_KstDailyEmitCap[str]" = _KstDailyEmitCap()
        self._fill_qty_src_count: dict[str, int] = {}

    # ──────────────────────────── 사이클 52 호환 layer (사이클 55 R-1)

    @property
    def _market_closed_blocked(self) -> dict[str, datetime]:
        """사이클 52 호환 — SellRejectionTracker._blocked_until 직접 노출 (is 동일성).

        기존 테스트/코드의 `_market_closed_blocked[ticker]` 직접 접근 보존.
        사이클 48 stale_tracker 패턴 답습.
        """
        return self._sell_rejection._blocked_until

    @property
    def _market_closed_blocked_logged_today(self) -> "DailyEmitCap[str]":
        """사이클 52 emit cap 호환 — SellRejectionTracker._logged_today 직접 노출.

        사이클 56-B 마이그레이션 후 DailyEmitCap[str] 반환 (set 동형 호환 layer 보유).
        """
        return self._sell_rejection._logged_today

    # ─────────────────────────────────────────────────────────────────────────

    def _strategy_exchange(self, strategy_id: str | None) -> str:
        """전략의 exchange 파라미터(KRX/NXT/SOR) 조회. 미지정 시 KRX.

        후방호환 동기 버전 — ticker 기반 NXT 사전 차단이 필요한 호출부는
        `_strategy_exchange_async(strategy_id, ticker=...)` 사용.
        """
        if not strategy_id:
            return "KRX"
        strategy = self.registry.get(strategy_id)
        if not strategy:
            return "KRX"
        return str(strategy.config.params.get("exchange", "KRX")).upper()

    def _clock_params(self, strategy_id: str | None) -> tuple[str, str]:
        """규칙 1·2 공용 — 전략 params 에서 `mode`/`dial` 조회(fail-open).

        `_apply_clock`·`_strategy_exchange_async` 가 공유한다 — 파라미터 조회
        로직이 두 곳으로 갈라지면 한쪽만 킬스위치를 반영하는 사고가 난다.
        """
        try:
            strategy = self.registry.get(strategy_id) if strategy_id else None
            params = strategy.config.params if strategy is not None else {}
        except Exception:
            params = {}
        mode = str(
            params.get("order_exchange_clock_mode", _ORDER_EXCHANGE_CLOCK_MODE_DEFAULT)
        )
        dial = str(
            params.get("after_market_exit_division", _AFTER_EXIT_DIVISION_DEFAULT)
        )
        if dial not in _AFTER_EXIT_DIVISION_ALLOWED:
            dial = _AFTER_EXIT_DIVISION_DEFAULT
        return mode, dial

    def _apply_clock(
        self,
        base: str,
        strategy_id: str | None,
        *,
        side: str = "sell",
        ticker: str | None = None,
        now: datetime | None = None,
    ) -> str:
        """규칙 1(시각이 거래소를 정한다) 적용 지점 — 자문 §S4.

        `limit_price>0` 분기 + 동기 취소 3경로(§S6e, `_cancel_after_wait`·
        `_cancel_and_reorder`·`cancel_remaining`)가 전부 이 메서드를 거친다
        (`_strategy_exchange_async` 는 이미 async 라 §S3g 에 따라 라우터를
        직접 부르고 같은 emit 헬퍼로 마커를 남긴다 — 로직 중복 없이 동일
        서식). 라우터를 호출부마다 직접 부르면 마커·mode 조회·예외 흡수가
        네 군데로 복제되고, 한 곳을 빠뜨리면 그 경로만 조용히 라우팅을
        비켜간다.

        **동기 함수**여야 한다 — 동기 취소 3경로가 이 seam 을 쓴다. 예외는
        전부 흡수하고 `base` 를 반환한다(fail-safe — 판정 실패가 주문 자체를
        막으면 안 된다).
        """
        mode, dial = self._clock_params(strategy_id)
        moment = now if now is not None else datetime.now(_KST_TZ)
        routed, reason = _route_exchange_by_clock(base, side=side, mode=mode, now=moment)

        try:
            self._emit_order_channel_config(strategy_id, mode, dial)
        except Exception:
            logger.debug("[order_channel_config] 발화 실패", exc_info=True)

        # 적대 검증 시정(MEDIUM) — `routed != base` 게이트는 `probe_error` 도
        # 함께 침묵시킨다. 판정 자체가 예외로 죽어도 `base` 로 fail-safe 하므로
        # `routed == base` 라 다른 정상 유지 사유(pre_nxt_keep 등)와 구별이
        # 안 됐다 — 라우팅이 안 걸린 것과 라우팅이 걸릴 필요가 없던 것을
        # 가르는 유일한 신호라 이 사유만 게이트 밖에서 예외적으로 남긴다.
        if routed != base or reason == "probe_error":
            try:
                self._emit_order_channel(side, ticker, strategy_id, base, routed, reason)
            except Exception:
                logger.debug("[order_channel] 발화 실패", exc_info=True)

        return routed

    def _emit_order_channel(
        self,
        side: str,
        ticker: str | None,
        strategy_id: str | None,
        base: str,
        exchange: str,
        reason: str,
    ) -> None:
        """R8 — `[order_channel]` 1회/(ticker,side,reason)/일.

        운영자는 화면에서 `SOR` 을 보면서 `KRX` 로 나가는 주문을 갖게 된다
        (자문 §4-E) — 이 마커가 그 불일치를 매일 남기는 유일한 분모다.
        """
        key = (ticker or "", side, reason)
        if key in self._order_channel_logged:
            return
        self._order_channel_logged.add(key)
        logger.info(
            "[order_channel] side=%s ticker=%s strategy=%s base=%s exchange=%s reason=%s",
            side, ticker, strategy_id, base, exchange, reason,
        )

    def _emit_order_channel_config(
        self, strategy_id: str | None, mode: str, dial: str,
    ) -> None:
        """R8d — `[order_channel_config]` 카나리아 1회/(전략,mode,dial)/일.

        D+1 판독 "라우팅이 켜졌는가" 를 한 줄로 확인하는 채널(cycle245
        `[ratio_cap_config]` 관례). 값-민감 키라 K·예산이 실제로 바뀐 날에만
        1행이 더 붙는다.
        """
        key = (strategy_id, mode, dial)
        if key in self._order_channel_config_logged:
            return
        self._order_channel_config_logged.add(key)
        logger.info(
            "[order_channel_config] strategy=%s mode=%s division=%s",
            strategy_id, mode, dial,
        )

    def _emit_pre_nxt_division_config(
        self, *, effective: int, production: int, exchange_gate: str,
    ) -> None:
        """cycle291 적대 검증 시정(B5) — `[pre_nxt_division_config]` 카나리아 1회/일.

        프리장 매수는 대부분의 날 0~2건이라 `[market_order_preconvert_pre_nxt]`
        만으로는 "게이트가 무장됐는가" 를 주문 없이 확인할 채널이 없었다
        (`[order_channel_config]`/`[ratio_cap_config]` 관례 답습). 값-무관
        순수 1회/일 — 그날 첫 평가 결과만 남긴다(그 뒤 게이트 판정이 시각
        경계를 넘어 바뀌어도 갱신하지 않는다, 카나리아이지 실시간 상태가
        아니다).
        """
        key = "config"
        if key in self._pre_nxt_division_config_logged:
            return
        self._pre_nxt_division_config_logged.add(key)
        logger.info(
            "[pre_nxt_division_config] division=%s effective=%d production=%d "
            "exchange_gate=%s",
            OrderDivision.NXT_GTP_LIMIT.value, effective, production, exchange_gate,
        )

    # ──────────────────────── cycle295 (B) — 15:30~16:00 주문 컷 게이트 ────────

    def _emit_market_rest_window(self, now: datetime) -> None:
        """§3-6 카나리아 — `[market_rest_window]` 1회/일, 컷 0건인 날에도.

        D+1 판독의 성공 서명은 "그 구간 주문 흔적 0건"인데, 0 은 «배선이
        죽었다»와 «정상»을 구별하지 못한다. 차단 여부와 무관하게 게이트가
        평가될 때마다 이 카나리아를 남긴다. `start=`/`end=` 는 리터럴이 아니라
        표에서 역산한다(`_market_rest_window_bounds`). never-raise.
        """
        try:
            if not self._market_rest_window_cap.should_emit("window", now=now):
                return
            bounds = _market_rest_window_bounds(now)
            if bounds is None:
                return
            start_m, end_m = bounds
            self._market_rest_window_cap.emit_once(
                "window", logger.info,
                "[market_rest_window] start=%02d:%02d end=%02d:%02d source=market_table",
                start_m // 60, start_m % 60, end_m // 60, end_m % 60,
                now=now,
            )
        except Exception:
            try:
                from src.engine.observer_trace import trace_observer_failure
                trace_observer_failure(
                    "[market_rest_window]", "window", self._market_rest_window_cap, now=now,
                )
            except Exception:  # pragma: no cover — 2차 예외도 흡수
                pass

    def _emit_market_rest_blocked(
        self, *, side: str, ticker: str, strategy_id: str | None,
        base: str, reason: str, now: datetime,
    ) -> None:
        """§3-6 — `[market_rest_blocked]` 1회/(ticker,side)/일.

        이 사이클이 무엇을 잃는지의 유일한 분모다(§4-5). never-raise
        (`emit_once` 자체가 never-raise).

        적대 검증 시정(MEDIUM) — `base=` 가 빠져 있었다. 그 값이 없으면
        `nxt_tradable=False` 코호트(마스터 83.2%)가 실제로 컷에 걸렸는지
        (§3-2 "라우터 안에 두면 컷을 비껴간다" 의 라이브 증거)를 로그만으로는
        확인할 수 없다.

        ⚠️ **호출부마다 해석 단계가 다르다** — 판독 시 같은 것으로 읽지 마라.
        `execute_sell` = `target_exchange`(다운그레이드 + 시각 라우팅까지 끝난
        값 ⇒ `nxt_false` 코호트가 `base=KRX` 로 보이는 것이 §3-2 증거다) /
        `_cancel_and_reorder` = 원주문의 실제 거래소(`_order_exchange`), 없으면
        전략 설정값 / `execute_buy` = **아직 거래소 해석 전**이라 전략 설정값
        (`_strategy_exchange`)이다. 게이트 자리를 해석 뒤로 옮겨 이 차이를
        없애려 하지 마라 — `execute_buy` 의 자리는 A-ATOMIC 구간 밖이어야 하고
        `get_buyable` 앞이어야 한다(§3-5②).
        """
        self._market_rest_blocked_cap.emit_once(
            (ticker, side), logger.warning,
            "[market_rest_blocked] side=%s ticker=%s strategy=%s base=%s reason=%s",
            side, ticker, strategy_id, base, reason,
            now=now,
        )

    def _market_rest_gate(
        self, *, side: str, ticker: str, strategy_id: str | None,
        base: str, now: datetime,
    ) -> bool:
        """cycle295 (B) 발사점 게이트 — 컷 여부를 판정하고 관측을 남긴다.

        `True` 반환 = 그 주문을 컷한다(호출부는 주문을 내지 않고 즉시 return
        해야 한다 — `_selling`/`pending_buys` 등 **곁가지 상태 정리는 호출부의
        몫**이다. `execute_sell`·`execute_buy`·`_cancel_and_reorder` 셋이 각자
        다른 상태를 갖고 있어 이 헬퍼가 공통으로 만질 수 없다). 카나리아는
        차단 여부와 무관하게 매 호출 평가된다(§3-6). fail-open — 판정 예외는
        `_market_rest_now` 자체가 흡수해 `(False, "probe_error")` 를 낸다.

        🔴 **현실 관측 fail-open(§9-Q2 권고)은 착지 직후 적대 검증으로 철회**
        했다. 해제 키가 `scanner.ticker_last_tick` 신선도였는데 두 가지가 동시에
        성립해 컷을 **100% 무력화**했다 — ① `risk.on_tick` 이 같은 콜스택에서
        그 dict 를 먼저 쓰고(`risk.py:585`) 곧바로 `execute_sell`/`execute_buy`
        를 부르므로 게이트가 재는 틱 나이가 **항상 0.0초**다(그 구간의 청산
        트리거는 WS 틱 단독 — REST 폴은 15:20 에 끝난다) ② 설령 그 타이밍을
        고쳐도 KRX K5(15:30~16:00 장후 시간외 종가, `fixed_price`)가 **같은 채널
        `H0STCNT0` 로 실제 체결 프레임을 보낸다**(표 실측). 즉 "틱이 온다" 와
        "우리 호가유형이 접수된다" 는 완전히 분리된 사실인데 신선도는 둘을
        같은 것으로 취급한다.

        ⚠️ 그래서 **표가 정본이고 해제 조건이 없다.** 남은 한계(§4-6) =
        `market_state` 표는 날짜 범위만 보는 고정 벽시계라 **특별 개장일(지연
        개장, 수능일이 표준 사례)을 모른다** — 그런 날 15:30~16:00 은 실제로
        연속체결 중인 정규장인데 컷이 30분 무음 차단한다(연 1회 수준). 이
        한계는 표에 거래일·특별일 입력을 넣는 별건 카드로 닫는다. 신선도
        기반 해제를 다시 들이지 마라 — 위 ①②가 그대로 재현된다.
        """
        self._emit_market_rest_window(now)

        blocked, reason = _market_rest_now(now)
        if not blocked:
            return False

        self._emit_market_rest_blocked(
            side=side, ticker=ticker, strategy_id=strategy_id,
            base=base, reason=reason, now=now,
        )
        return True

    # ─────────────────────────────────────────────────────────────────────────

    def _register_after_exit_disallowed(
        self, ticker: str, now_kst: datetime, *, fallback_succeeded: bool,
    ) -> bool:
        """K9 봉인① 공용 — TTL(30초) 등록, 성공 여부를 반환한다.

        적대 검증 시정(H1) — `[after_exit_rejected]` 의 `ttl_registered=` 가
        하드코딩 리터럴 `1` 이었다(등록을 시도조차 안 한 경로에서도 참을
        주장). 이 래퍼가 실측 결과를 돌려주고, 호출부는 그 값을 그대로
        로그에 싣는다. never-raise — 등록 실패가 매도 흐름을 막지 않는다.
        """
        try:
            self._sell_rejection.register_market_order_disallowed(
                ticker, now_kst,
                is_nxt_session=is_nxt_session_hours(now_kst),
                fallback_succeeded=fallback_succeeded,
            )
            return True
        except Exception:
            logger.debug(
                "[after_exit_rejected] TTL 등록 실패: %s", ticker, exc_info=True,
            )
            return False

    def _bump_after_exit_fails_and_maybe_giveup(
        self, ticker: str, strategy_id: str, now_kst: datetime,
    ) -> None:
        """K9 봉인② 공용 — 그 저녁 실패(=주문 사이클 전체가 무성사) 횟수 누적.

        적대 검증 시정(CRITICAL C1) — 종전에는 이 카운터가 "폴백을 시도했고
        그것도 거부된" 경로에만 있었다. 폴백을 **시도조차 못 한**
        (`cur_price<=0`) 경로는 카운터가 전혀 늘지 않아 브레이크 없이
        틱마다(16:00~20:00 은 실시간 연속체결) 재발사했다 — 이 헬퍼를 그
        경로에도 호출해 같은 상한을 공유시킨다. `_AFTER_EXIT_GIVEUP_THRESHOLD`
        도달 시 다음 09:00 TTL 로 전환 + 익일청산 등록 + CRITICAL 1행.
        never-raise.
        """
        try:
            fail_key = (ticker, now_kst.date())
            fails = self._after_exit_fails.get(fail_key, 0) + 1
            self._after_exit_fails[fail_key] = fails
            if fails >= _AFTER_EXIT_GIVEUP_THRESHOLD:
                self._sell_rejection.register_market_closed(
                    ticker, now_kst, in_krx_main_hours=False,
                )
                try:
                    pending = self._pending_next_day_clear_provider()
                    if pending is not None:
                        pending.add((ticker, strategy_id))
                except Exception:
                    logger.debug(
                        "[after_exit_giveup] pending 등록 실패: %s",
                        ticker, exc_info=True,
                    )
                logger.critical(
                    "[after_exit_giveup] ticker=%s fails=%d next_day_clear=1",
                    ticker, fails,
                )
        except Exception:
            logger.debug("[after_exit_giveup] 판정 실패: %s", ticker, exc_info=True)

    async def _observe_after_exit_etp(self, ticker: str) -> None:
        """K7 — 애프터 1차 거부 직후 ETP 관측(fail-open, 행위 분기 없음).

        관측을 행복 경로(주문 직전)에 두면 손절에 DB 왕복 지연이 붙으므로
        거부 후로 옮긴다(자문 §4-F/§S5) — 판정에 쓰지 않으니 정보 손실 0.
        판별 정본 = `stock_master.raw.scty_grp_id_cd ∈ {EF,EN,FE}`
        (CTPF1002R #7, 신규 KIS 호출 0 — 값이 이미 `stock_master.raw` 에 있다).
        ⚠️ `prdt_type_cd` 로 판정하면 안 된다 — `stock_master` 전 종목이
        `'300'`(ETF 포함)이라 한 건도 걸러내지 못한다(조사 실측).
        """
        try:
            from src.db import stock_master

            basics = await stock_master.get(ticker)
            raw = basics.raw if basics is not None else None
            scty_grp = raw.get("scty_grp_id_cd") if isinstance(raw, dict) else None
            if scty_grp in ("EF", "EN", "FE"):
                logger.info(
                    "[after_etp_exit_observe] ticker=%s scty_grp=%s source=raw",
                    ticker, scty_grp,
                )
        except Exception:
            logger.debug("[after_etp_exit_observe] 관측 실패", exc_info=True)

    async def _probe_nxt_downgrade_base(
        self, strategy_id: str | None, ticker: str | None,
    ) -> str:
        """전략 exchange + stock_master NXT 사전 차단(Phase G, 2026-05-11) — **다운그레이드까지만**.

        `stock_master.get(ticker).nxt_tradable=False` 이면 NXT/SOR → KRX 강제
        다운그레이드 + `[nxt_downgrade]` system_logs 1행. 캐시 miss / KIS 오류
        시 전략 기본 exchange 그대로 (보수적 fallback).

        cycle287 — 이 메서드는 시각 라우팅을 하지 **않는다**. 호출자
        `_strategy_exchange_async` 가 이 반환값을 받아 함수 말미에서 **한 번**
        `_route_exchange_by_clock` 으로 감싼다(자문 §9-B "함수 말미에서 한 번
        감싼다") — 그래서 `[nxt_downgrade]`/`[stock_master_miss]` 는 항상
        라우팅 **전**에 발화한다.
        """
        base = self._strategy_exchange(strategy_id)
        if not ticker or base == "KRX":
            return base

        try:
            from src.db import stock_master  # lazy — 단위테스트 격리 + circular import 방지

            basics = await stock_master.get(ticker)
        except Exception:  # supabase 오류 등 — 전략 기본 유지
            logger.exception("stock_master.get 실패 (전략 기본 exchange 유지): %s", ticker)
            return base

        if basics is None:
            # 가설 E (2026-05-12) — 캐시 miss 시 1행 INFO 로그. 본 흐름(전략 기본 유지) 영향 없음.
            await safe_write_log(
                "INFO",
                f"[stock_master_miss] ticker={ticker} strategy={strategy_id} "
                f"exchange_keep={base} reason=miss",
                fallback_debug="[stock_master_miss] write_log 실패",
            )
            return base  # cache miss — 보수적 fallback

        # 가설 E (2026-05-12) — stale 캐시 가시화 (TTL 24h 초과).
        # Codex 추가검토 4 (2026-05-12): is_stale 은 Supabase round-trip → 주문 경로에서
        # 직접 await 하면 시장가 매수/매도 latency 증가. asyncio.create_task 로 분리해
        # 본 흐름은 즉시 반환. task 예외는 내부에서 흡수.
        async def _log_stale_async(t: str, sid: str | None, exch: str) -> None:
            try:
                from src.db import stock_master as _sm
                if await _sm.is_stale(t):
                    await safe_write_log(
                        "INFO",
                        f"[stock_master_miss] ticker={t} strategy={sid} "
                        f"exchange_keep={exch} reason=stale",
                        fallback_debug="[stock_master_miss] stale 체크 실패",
                    )
            except Exception:
                logger.debug("[stock_master_miss] stale 체크 실패", exc_info=True)

        try:
            asyncio.create_task(_log_stale_async(ticker, strategy_id, base))
        except RuntimeError:
            # 이벤트 루프 없는 컨텍스트(테스트 등) — 본 흐름 보존
            logger.debug("[stock_master_miss] stale task 등록 실패", exc_info=True)

        if basics.nxt_tradable:
            return base

        # nxt_tradable=False — KRX 강제 다운그레이드
        # 사이클 54: 로그만 ticker별 1회/일 cap — 다운그레이드 결정(return "KRX")은 cap 밖
        if ticker not in self._nxt_downgrade_logged_today:
            try:
                await write_log(
                    "WARNING",
                    f"[nxt_downgrade] {ticker} strategy={strategy_id} "
                    f"from={base} to=KRX reason=nxt_not_tradable",
                )
                self._nxt_downgrade_logged_today.add(ticker)
            except Exception:
                logger.debug("[nxt_downgrade] write_log 실패", exc_info=True)
        return "KRX"

    async def _strategy_exchange_async(
        self,
        strategy_id: str | None,
        *,
        ticker: str | None = None,
        side: str = "sell",
    ) -> str:
        """전략 exchange 결정 — Phase G 다운그레이드 + cycle287 규칙 1 라우팅.

        다운그레이드(`_probe_nxt_downgrade_base`) **뒤**에 라우터를 적용해야
        `[nxt_downgrade]`/`[stock_master_miss]` 관측이 라우팅과 무관하게
        발화한다(함수 맨 앞에 두면 그 관측이 조용히 사라진다 — 자문 §9-B 경고).
        `side` 는 매수 호출부(`execute_buy`)가 `"buy"` 를, 그 외(매도)가
        기본값 `"sell"` 을 쓴다 — `sell_only` 킬스위치가 성립하려면 이 구분이
        필요하다. 이미 async 인 이 함수는 `_apply_clock` 을 거치지 않고
        라우터(`_route_exchange_by_clock`)를 직접 불러 **한 번**(함수 말미)
        감싼다 — 동일한 emit 헬퍼로 `_apply_clock` 과 같은 마커 서식을 낸다.
        """
        base = await self._probe_nxt_downgrade_base(strategy_id, ticker)
        mode, dial = self._clock_params(strategy_id)
        moment = datetime.now(_KST_TZ)
        routed, reason = _route_exchange_by_clock(base, side=side, mode=mode, now=moment)

        try:
            self._emit_order_channel_config(strategy_id, mode, dial)
        except Exception:
            logger.debug("[order_channel_config] 발화 실패", exc_info=True)

        # 적대 검증 시정(MEDIUM) — `_apply_clock` 과 동일하게 `probe_error`
        # 는 `routed == base` 여도 게이트 밖에서 남긴다(판정 실패 신호 보존).
        if routed != base or reason == "probe_error":
            try:
                self._emit_order_channel(side, ticker, strategy_id, base, routed, reason)
            except Exception:
                logger.debug("[order_channel] 발화 실패", exc_info=True)

        return routed

    # cycle327 — 흡수 마커는 축별 **리터럴**로 둔다(로그 grep 의 대상이다).
    # `side` 는 이 표의 키일 뿐이고, 표에 없는 값이면 흡수하지 않고 전파한다.
    _FILL_DURING_INSERT_MARKER = {
        "buy": "[buy_fill_during_insert]",
        "sell": "[sell_fill_during_insert]",
    }

    async def _insert_pending_or_absorb_race(
        self,
        record: TradeRecord,
        *,
        side: str,
        ticker: str,
        order_no: str,
        strategy_id: str,
        path: str,
    ) -> None:
        """PENDING INSERT — 체결통보가 그 `await` 도중 착지하는 race(cycle271) 흡수.

        `await insert_trade` 는 이벤트 루프에 제어를 넘긴다. 그 사이 체결통보
        (`_handle_buy_fill` / `_handle_sell_fill`) 가 먼저 완주하면 보정 INSERT 로
        같은 `(ticker, order_no, trade_type)` COMPLETED 행을 먼저 넣어 두므로,
        재개된 이 PENDING INSERT 는 migration 029 부분 UNIQUE 인덱스를 위반한다.

        `_completed_orders` 에 이 `order_no` 가 있다는 것이 "체결통보가 먼저
        INSERT 했다"는 유일한 증거다 — 그때만 성공 경로로 합류하고
        (누수 방지를 위해 그 order_no 를 소비/discard), 증거 없는
        UniqueViolationError(예: 같은 키의 CANCELLED 잔존 등 다른 원인)는
        그대로 전파한다.

        cycle327 — **매수·매도 공용**이다. 매도에 이 흡수기가 없던 동안
        `UniqueViolationError` 가 `except Exception` 으로 흘러 재시도 루프를
        돌았고, **이미 팔린 수량을 다시 발사**했다.
        """
        try:
            await insert_trade(record)
        except UniqueViolationError:
            marker = self._FILL_DURING_INSERT_MARKER.get(side)
            if marker and order_no in self._completed_orders:
                self._completed_orders.discard(order_no)
                logger.info(
                    "%s ticker=%s order_no=%s strategy=%s path=%s",
                    marker, ticker, order_no, strategy_id, path,
                )
            else:
                raise

    def _emit_fill_qty_src(
        self, order_no: str, ticker: str, side: str, qty_src: str,
        ordered_qty: int, total_filled: int, incr: int,
    ) -> None:
        """`[fill_qty_src]` — 주문수량을 **어디서 얻었는지** 남긴다 (cycle329).

        `src=map` 은 정상이고 하루 수천 건이라 **DEBUG**, 나머지 둘은 **WARNING** 이다.
        `log_analysis_engine._aggregate_log_patterns` 가 WARNING 이상만 `top_patterns`
        에 넣으므로 **비정상만 21:30 리포트에 오른다** — ρ축 마커가 INFO 라 리포트에
        한 글자도 안 들어가 오귀인을 낳은 선례의 반대를 택한 것이다.

        판독 = `src=payload` 가 그날 1건이라도 있으면 **그 창이 실제로 열렸고 우리가
        막았다**(성공 서명). `src=increment` 는 수동·외부 주문이라 그날 수동 매매를
        했다면 정상이고, **안 했는데 있으면 그것이 조사 신호다**.

        🔴 **행위는 cap 밖** — 이 함수가 무엇을 하든 판정은 이미 끝나 있다. never-raise.
        """
        try:
            self._fill_qty_src_count[qty_src] = self._fill_qty_src_count.get(qty_src, 0) + 1
        except Exception:
            pass
        try:
            msg_args = (order_no, t(ticker), side, qty_src, ordered_qty, total_filled, incr)
            fmt = ("[fill_qty_src] order_no=%s ticker=%s side=%s src=%s "
                   "ordered=%d filled_total=%d incr=%d")
            if qty_src == "map":
                logger.debug(fmt, *msg_args)
                return
            # 1회/(출처, 종목, 방향)/일 — `order_no` 를 키에 넣으면 cap 이 무력해진다.
            self._fill_qty_src_logged.emit_once(
                f"{qty_src}|{ticker}|{side}", logger.warning, fmt, *msg_args,
            )
        except Exception:
            # lazy import — `order_engine` 최상단 `src.*` 의존 표면은 동결돼 있다
            # (`test_cycle286_ast_scope.py::test_g4_3`). 관측기 실패 경로라 hot path 무관.
            from src.engine.observer_trace import trace_observer_failure
            trace_observer_failure(
                "[fill_qty_src]", f"{qty_src}|{ticker}|{side}", self._fill_qty_src_logged,
            )

    def _emit_ordered_qty_mismatch(
        self, order_no: str, ticker: str, side: str, mapped: int, payload: int,
    ) -> None:
        """🔴 `[ordered_qty_mismatch]` — payload ODER_QTY 가 우리 기록과 다르다.

        `fields[16]` 배정이 틀리면 cycle235 의 257720 실사고가 재현된다. 그 사고는
        **부분/분할 체결에서만 드러나** 오래 잠복했다. 이 마커는 매핑이 선 **정상
        통보마다** 대조하므로 그 창을 기다리지 않고 즉시 드러난다.

        불일치가 있어도 판정은 `map` 값을 쓴다 — payload 는 매핑 부재 창에서만 쓰인다.
        """
        try:
            self._ordered_qty_mismatch_logged.emit_once(
                f"{ticker}|{side}", logger.warning,
                "[ordered_qty_mismatch] order_no=%s ticker=%s side=%s mapped=%d payload=%d "
                "— KIS ODER_QTY 가 우리 주문수량과 다르다 (fields[16] 배정 재확인 요망)",
                order_no, t(ticker), side, mapped, payload,
            )
        except Exception:
            from src.engine.observer_trace import trace_observer_failure
            trace_observer_failure(
                "[ordered_qty_mismatch]", f"{ticker}|{side}",
                self._ordered_qty_mismatch_logged,
            )

    def emit_fill_qty_src_daily_summary(self) -> None:
        """`_settle()` 직전 1행. 🔴 호출부를 try/except 로 감싸지 않는다.

        감싸면 폐기 메서드 잔존 같은 결함이 AttributeError graceful skip 으로 조용히
        먹혀 운영 가시화가 무력화된다(`scanner` 일일 summary 2종과 같은 이유).
        """
        c = self._fill_qty_src_count
        logger.info(
            "[fill_qty_src_summary] window=day map=%d payload=%d increment=%d",
            c.get("map", 0), c.get("payload", 0), c.get("increment", 0),
        )

    #: `(side, path)` → 선행 체결통보 skip 로그의 **접두 수식어** (cycle334 — 4경로 공용).
    #: **관측 전용**이라 조회가 실패해 행위를 바꿀 수 없어야 한다 — `.get(key, "")` 는
    #: 어떤 값에도 raise 하지 않고, 빈 수식어는 덜 구체적인 문장을 낼 뿐 틀린 문장이 아니다.
    #: 미지 키 자체는 `[*_fill_during_insert]`/`[sell_post_send_error]` 의 `path=%s` 에
    #: 원문으로 실려 별도 채널 없이 드러난다.
    #: ⚠️ `("buy","fallback")` 만 `"매수 폴백 "` 이 아닌 것은 **현행 문구 보존**이다.
    _PENDING_SKIP_PREFIX = {
        ("buy", "market"): "매수 ",
        ("buy", "fallback"): "폴백 ",
        ("sell", "market"): "매도 ",
        ("sell", "fallback"): "매도 폴백 ",
    }

    #: `trade_type` → 마커 축. 🔴 **방향이 계약이다** — 행위값(`trade_type`)에서
    #: 관측값(`side`)을 파생시킨다. 반대로 하면 `side` 오타 하나가 `trade_history` 의
    #: 매수/매도를 뒤집는다.
    _PENDING_SIDE_BY_TRADE_TYPE = {TradeType.BUY: "buy", TradeType.SELL: "sell"}

    async def _persist_pending_after_send(
        self, *, trade_type: TradeType, ticker: str, order_no: str,
        strategy_id: str, record_price: int, quantity: int, path: str,
    ) -> None:
        """접수 후 PENDING 영속화 — **매수·매도 4 경로 공용 코어** (cycle334).

        「선행 체결통보 체크 → skip 로그 → `TradeRecord` 조립 → race 흡수 INSERT」가
        네 곳에 손으로 복제돼 있었고, **그 흩어짐이 cycle327 실사고의 원인**이었다
        (흡수기가 매수 2곳에만 있었다). 이제 그 규칙은 한 곳에서만 고친다.

        🔴 **이 함수는 경계를 닫지 않는다 — 예외를 그대로 전파한다.**
        접수 후 경계(cycle327 ⓑ)는 **호출자 층**의 책임이다. 매도는
        `_persist_sell_pending_after_send` 래퍼가 닫고, **매수는 아직 닫지 않는다**
        (그 부재는 결함이고 별도 승인 사이클 소관이다 — 설계 카드 §2B).
        여기에 `try` 를 들이면 매수 두 경로의 예외 전파가 **조용히 바뀐다**.

        🔴 **본문 앞부분에 `await` 를 추가하지 않는다.** 최초 양보점이
        `_insert_pending_or_absorb_race` 안의 `await insert_trade` 라는 사실이
        「주문번호 매핑은 `place_order` 응답 직후 동기 영역」 금기의 전제다.
        """
        side = self._PENDING_SIDE_BY_TRADE_TYPE.get(trade_type, "")
        if order_no in self._completed_orders:
            self._completed_orders.discard(order_no)
            logger.warning(
                "%s응답보다 체결통보 선행 — PENDING INSERT 생략: %s (주문번호: %s)",
                self._PENDING_SKIP_PREFIX.get((side, path), ""), t(ticker), order_no,
            )
        else:
            record = TradeRecord(
                ticker=ticker,
                ticker_name=t(ticker).split("(")[0] if "(" in t(ticker) else "",
                trade_type=trade_type,
                price=record_price,
                quantity=quantity,
                profit_loss=0,  # 체결 확정 시 계산
                status=TradeStatus.PENDING,
                strategy=strategy_id,
                order_no=order_no,
            )
            await self._insert_pending_or_absorb_race(
                record, side=side, ticker=ticker, order_no=order_no,
                strategy_id=strategy_id, path=path,
            )

    async def _persist_sell_pending_after_send(
        self,
        *,
        ticker: str,
        order_no: str,
        strategy_id: str,
        record_price: int,
        quantity: int,
        path: str,
    ) -> None:
        """🔴 cycle327 ⓑ — 호출 시점에 **주문은 이미 나갔다**.

        여기서 일어나는 어떤 실패도 「발사 실패」가 아니므로 밖으로 내보내지 않는다.
        주 경로에서 새면 재시도 루프가 **이미 팔린 것을 다시 팔고**(실측 3회 발사),
        폴백 경로에서 새면 `except KisApiError` 핸들러가 non-`KisApiError` 를 못 받아
        `execute_sell` 을 통째로 뚫고 **`risk.on_tick` 으로 전파된다**(그 틱의 다른
        종목 손절 평가도 함께 사라진다). 피해 모양은 다르지만 막는 수단은 하나다 —
        경계가 호출부의 문맥이 아니라 **이 함수 자신의 `except Exception`** 에 있어서,
        호출부가 어디에 있든 "이 문장은 예외를 던지지 않는다" 가 유지된다.

        🔴 **본문 앞부분에 `await` 를 추가하지 않는다.** 최초 양보점이
        `_insert_pending_or_absorb_race` 안의 `await insert_trade` 라는 사실이
        「주문번호 매핑은 `place_order` 응답 직후 동기 영역」 금기의 전제다.
        """
        try:
            await self._persist_pending_after_send(
                trade_type=TradeType.SELL, ticker=ticker, order_no=order_no,
                strategy_id=strategy_id, record_price=record_price,
                quantity=quantity, path=path,
            )
        except Exception:
            logger.exception(
                "[sell_post_send_error] ticker=%s order_no=%s strategy=%s path=%s "
                "— 주문은 접수됐다. 재발사하지 않고 체결통보·동기화에 맡긴다.",
                ticker, order_no, strategy_id, path,
            )

    async def execute_buy(
        self,
        ticker: str,
        current_price: int,
        strategy: StrategyBase,
        *,
        soft_multiplier: float = 1.0,
    ) -> None:
        """매수 주문을 실행한다.

        **사이클 8 (2026-05-18)** — ``soft_multiplier`` (기본 1.0):
        - risk.on_tick 이 BuyBlockState 가 SOFT 모드 + 가드 발동 시 0.5 를 전달한다.
        - calc_buy_quantity 결과에 곱하고 ``max(1, int(...))`` 로 최소 1주 보장.
        - 1.0 인 경우 기존 동작 100% 보존 (회귀 0).
        """
        state = strategy.state
        if state.has_position(ticker) or state.is_buy_pending(ticker):
            logger.warning("중복 매수 차단: %s (전략: %s)", t(ticker), strategy.strategy_id)
            return
        # 전략 간 통합 가드 (race condition 대비)
        if self.registry.is_ticker_blocked_for_buy(ticker):
            logger.warning(
                "전략 간 중복 매수 차단: %s (요청 전략: %s, 다른 전략이 보유/주문중/당일매도)",
                t(ticker), strategy.strategy_id,
            )
            return

        # cycle295 (B) — 15:30~16:00 완전 휴식(§9-Q5 결정 = 매수 축도 넣는다).
        # 중복매수 가드 **직후**·`get_buyable` **앞**(§3-5②) — A-ATOMIC 구간
        # (`calc_buy_quantity`~`pending_buys.add`) 밖에 있어야 한다. 그 구간
        # 매수는 오늘 구조적 0(LTV `tradable_boards` 에 `post_nxt` 없음)이라
        # 순수 방어선이다.
        if self._market_rest_gate(
            side="buy", ticker=ticker, strategy_id=strategy.strategy_id,
            base=self._strategy_exchange(strategy.strategy_id),
            now=datetime.now(_KST_TZ),
        ):
            return

        now_ts = time.time()
        # 잔고 부족 락 — 다음 잔고 sync까지 KIS 호출 자체를 차단
        if state.is_buy_blocked(now_ts):
            logger.debug(
                "매수 차단(잔고 부족 락): %s (전략: %s, 해제 %.0fs 후)",
                t(ticker), strategy.strategy_id, state.buy_blocked_until - now_ts,
            )
            return
        # per-ticker 투자금 부족 cooldown — 같은 종목에서 매 틱 "매수 수량 0" 반복 차단
        if state.is_low_funds_blocked(ticker, now_ts):
            return

        # 매수가능금액 — 캐시(60초 TTL) 우선, 없으면 KIS 조회
        if state.is_buyable_cache_fresh(now_ts, BUYABLE_CACHE_TTL):
            max_buy_qty = state.cached_buyable_qty
            cache_hit = True
        else:
            try:
                buyable = await get_buyable(ticker, current_price)
            except KisApiError as e:
                if is_insufficient_cash(e):
                    state.block_buy(now_ts + BUY_BLOCK_DURATION)
                    logger.warning(
                        "매수가능조회 잔고부족 응답 → 매수 락(%ds): %s [%s] %s",
                        int(BUY_BLOCK_DURATION), strategy.strategy_id, e.msg_cd, e.msg1,
                    )
                    return
                raise
            state.cached_buyable_qty = buyable.max_buy_quantity
            state.cached_buyable_amount = buyable.max_buy_amount
            state.cached_buyable_at = now_ts
            max_buy_qty = buyable.max_buy_quantity
            cache_hit = False

        # ticker 전달 (Phase 2A-1 터틀 유닛 sizing 이 _candidates[ticker]['atr'] 참조).
        # position_ratio 전략은 ticker 무시 → 행위 불변.
        quantity = strategy.calc_buy_quantity(current_price, ticker)

        # 사이클 8 (2026-05-18) — SOFT 모드 수량 축소.
        # multiplier=1.0 이면 no-op (회귀 보존). 1.0 미만이면 max(1, ...) 로 최소 1주 보장.
        # 본 적용은 calc_buy_quantity 의 1주 폴백 이후라 잔여 자금 검증을 거친 수량을 축소.
        if soft_multiplier < 1.0 and quantity > 0:
            adjusted = max(1, int(quantity * soft_multiplier))
            if adjusted != quantity:
                logger.info(
                    "[buy_block_soft] %s: quantity %d → %d (multiplier=%.2f, 전략=%s)",
                    t(ticker), quantity, adjusted, soft_multiplier, strategy.strategy_id,
                )
                quantity = adjusted

        if quantity <= 0:
            # per-ticker cooldown 등록 — 다음 잔고 sync 또는 LOW_FUNDS_COOLDOWN 만료까지 같은 종목 매수 시도 차단
            state.block_low_funds(ticker, now_ts + LOW_FUNDS_COOLDOWN)
            logger.warning(
                "매수 수량 0 → %ds cooldown: %s (투자금: %d, 현재가: %d, 전략: %s)",
                int(LOW_FUNDS_COOLDOWN),
                ticker, state.total_investment, current_price, strategy.strategy_id,
            )
            return

        # 매수가능수량 제한
        if max_buy_qty <= 0:
            # 잔고 부족이 확정 — 다음 잔고 sync까지 락
            state.block_buy(now_ts + BUY_BLOCK_DURATION)
            logger.warning(
                "매수가능수량 0 → 매수 락(%ds): %s (전략: %s, %s)",
                int(BUY_BLOCK_DURATION), t(ticker), strategy.strategy_id,
                "캐시" if cache_hit else "KIS 조회",
            )
            return
        if quantity > max_buy_qty:
            quantity = max_buy_qty

        if quantity <= 0:
            logger.warning("최종 매수수량 0: %s", t(ticker))
            return

        state.pending_buys.add(ticker)
        # 1주 폴백 잔여 자금 계산용 — pending_buys 와 동기 라이프사이클 (2026-05-11 P1)
        state.pending_buy_amounts[ticker] = current_price * quantity
        state.order_attempt_today += 1

        # exchange 결정 — stock_master 사전 차단 (Phase G) + cycle287 규칙 1 라우팅.
        # place_order 호출 전 await 로 완료. side="buy" — `sell_only` 킬스위치가
        # 매수/매도 축을 구분하려면 호출부가 이 값을 명시해야 한다(자문 §R5-d).
        buy_exchange = await self._strategy_exchange_async(
            strategy.strategy_id, ticker=ticker, side="buy"
        )

        # PR-F (P2, 2026-05-15) — NXT 프리마켓 시장가 사전 차단.
        # NXT 프리(08:00~09:00) 는 KIS 정책상 지정가만 허용. session_tracker.active 에
        # PRE_NXT 가 포함 + MAIN 미포함 + exchange in (NXT, SOR) 면 시장가 거부(APBK0918)
        # 100% 예측 → 사전에 step_up(current_price, 5) 지정가로 변환.
        #
        # PR #9 Codex P2 (2026-05-15): 08:30~09:00 동안 active={PRE_NXT, KRX_OPEN}
        # 라 exact equality `== frozenset({PRE_NXT})` 가 false 됨 → 후반 30분 NXT
        # 프리마켓 시간대에도 시장가 거부+폴백 사이클 반복하던 결함 차단.
        # membership 체크로 PRE_NXT 시간대 전체 커버. MAIN 동시 활성(09:00 이후)은 제외.
        # 결함 (운영 로그 2026-05-15 08:00:34): 064400 [APBK0918] [프리마켓] 시장가 매매 불가
        order_division = OrderDivision.MARKET
        order_price = 0
        try:
            from src.engine.session import MarketBoard, session_tracker
            active_boards = session_tracker.active
            is_pre_nxt_period = (
                MarketBoard.PRE_NXT in active_boards
                and MarketBoard.MAIN not in active_boards
            )
            if is_pre_nxt_period and buy_exchange in ("NXT", "SOR"):
                order_price = step_up(current_price, steps=5)
                order_division = OrderDivision.LIMIT
                # cycle291 (2026-09-13) — GTP(27) 승격. `27` 은 NXT 프리마켓
                # 전용호가로, 미체결 잔량을 거래소가 프리마켓 종료(08:50)에
                # 일괄 취소한다 — 그 자동취소가 GTP 의 정체성이고, 우리가 이
                # 코드를 쓰는 유일한 이유다. 지금 보내는 `00`(지정가)은 그
                # 취소를 받지 못해 미체결이 NXT 정규장(09:00:30~)으로 새고,
                # 새는 방향이 역선택 쪽으로만 치우쳐 있다(자문 §1-a) — 프리장
                # 매수는 `step_up(현재가,5)` 라 상승이 이어지면 체결되지
                # 않고, 가설이 깨져 시세가 내려올 때만 우리 호가를 때린다.
                #
                # 순수 승격(순수 옵셔널) — 위에서 이미 `order_price`/
                # `order_division` 을 `00`(LIMIT) 으로 확정했다. 아래 판정이
                # 어떤 이유로든 실패하면 그 값이 그대로 남아 **오늘과 byte
                # 동일**하게 나간다(fail-safe). 게이트 4중(자문 §6 조건 5):
                #   (1) 실전 전용 — VTS 는 `EXCG_ID_DVSN_CD` 가 KRX 만 허용해
                #       NXT 주문 자체가 불가(cycle287 애프터 변환 선례와
                #       같은 게이트).
                #   (2) NXT 전용 — SOR 의 27 지원은 정본 미확인
                #       (`market_state._gtp` 의 `exchanges_unknown={"SOR"}`).
                #   (3) 그 시각 NXT 가 `27` 을 실제로 받는가 — `market_state`
                #       표가 시행일(2026-09-14)·프리마켓 종료(08:50) 경계를
                #       **유일하게** 쥐고 있다. 날짜·시각 리터럴을 여기
                #       복제하지 않는다.
                #   (4) 위 프리장 판정(이미 참으로 진입했다).
                # 어느 하나라도 실패·예외면 위에서 확정한 `00` 이 그대로
                # 나간다.
                _gtp_reason = "ok"
                _gtp_production = -1  # 적대 검증 시정(B5) — 카나리아용, 판정에 미사용
                try:
                    from src.config import settings as _settings

                    _gtp_production = 1 if _settings.is_production else 0
                    if not _settings.is_production:
                        _gtp_reason = "vts"
                    elif buy_exchange != "NXT":
                        _gtp_reason = "exchange"
                    else:
                        from src.engine.market_state import get_market_state

                        if OrderDivision.NXT_GTP_LIMIT.value in get_market_state(
                            datetime.now(_KST_TZ), market="NXT",
                        ).order_divisions:
                            order_division = OrderDivision.NXT_GTP_LIMIT
                        else:
                            _gtp_reason = "not_effective"
                except Exception:
                    _gtp_reason = "probe_error"
                logger.info(
                    "[market_order_preconvert_pre_nxt] ticker=%s exchange=%s "
                    "current_price=%d converted_to_limit_price=%d div=%s gtp=%d reason=%s",
                    ticker, buy_exchange, current_price, order_price,
                    order_division.value,
                    1 if order_division is OrderDivision.NXT_GTP_LIMIT else 0,
                    _gtp_reason,
                )
                # 적대 검증 시정(MEDIUM, 3렌즈 공통 지적 — 명세 B5) — 프리장 매수는
                # 대부분의 날 0~2건이라 주문이 없는 날은 위 마커도 침묵해 "게이트가
                # 무장됐는가" 를 확인할 채널이 없었다. 프리장 첫 매수 후보 평가
                # 시점(=이 블록 진입, 실제 후보가 있어야 발화 — 후보 0인 날은 여전히
                # 침묵한다, D+1 판독표에 명시) 1회/일. 관측 실패가 매수를 막지 않는다.
                try:
                    self._emit_pre_nxt_division_config(
                        effective=1 if order_division is OrderDivision.NXT_GTP_LIMIT else 0,
                        production=_gtp_production,
                        exchange_gate=buy_exchange,
                    )
                except Exception:
                    logger.debug("[pre_nxt_division_config] 발화 실패", exc_info=True)
                # pending_buy_amounts 도 변환된 가격 기준으로 동기 갱신 (1주 폴백 잔여 자금 정합성)
                state.pending_buy_amounts[ticker] = order_price * quantity
        except Exception:
            # 사전 차단 실패는 swallow — 기존 사후 폴백 분기에서 자연 회복.
            # session import / session_tracker 접근 예외가 매수 흐름 자체를 막으면 안 됨.
            logger.debug("[market_order_preconvert_pre_nxt] 사전 변환 평가 실패", exc_info=True)
            order_division = OrderDivision.MARKET
            order_price = 0

        try:
            # order_division 키워드는 MARKET 일 때 생략 가능하지만 그 외(LIMIT·
            # cycle291 GTP) 일 때 명시 필수. cycle291 — 화이트리스트 금지
            # (cycle287 `test_s4d` 원칙). `== LIMIT` 열거는 새 호가유형을
            # 조용히 삼켜 `place_order` 기본값 시장가로 되돌린다.
            place_kwargs = dict(
                ticker=ticker,
                side=OrderSide.BUY,
                quantity=quantity,
                price=order_price,
                exchange=buy_exchange,
            )
            if order_division != OrderDivision.MARKET:
                place_kwargs["order_division"] = order_division
            result = await place_order(**place_kwargs)

            # 주문번호 매핑 즉시 등록 — await insert_trade 진입 전 동기 영역에서 처리.
            # 시장가 즉시체결 시 체결통보가 insert_trade await 도중 도착해도 매핑이 보장된다.
            # PR-F: 사전 변환된 경우 record_price 는 변환 가격(order_price), 시장가 경로면 current_price.
            record_price = (
                order_price if order_division != OrderDivision.MARKET else current_price
            )
            self._order_qty[result.order_no] = quantity
            self._order_strategy[result.order_no] = strategy.strategy_id
            self._order_ticker[result.order_no] = ticker
            # 적대 검증 시정(HIGH) — 이 주문이 실제로 나간 거래소를 기억한다.
            # 취소 경로(`_cancel_after_wait`/`_cancel_and_reorder`/`cancel_remaining`)
            # 가 취소 시각의 라우터 재평가 대신 이 값을 우선 사용해야 원주문·취소가
            # 시간 경계를 사이에 두고 다른 거래소로 갈리지 않는다(자문 §4-C2 의도
            # — "동기 3 호출부도 라우터를 거친다" 는 "매번 새로 판정한다" 를
            # 뜻하지 않았다. `cancel_order` 계약도 "원주문이 접수된 거래소" 다).
            self._order_exchange[result.order_no] = buy_exchange
            # cycle291 — 전송한 값만 기록한다(`place_kwargs` 에서 뽑는다, 지역
            # 변수 `order_division` 이 아니다 — B2 를 놓쳤을 때 매핑이 거짓말
            # 하는 것을 구조적으로 막는다).
            _sent_division = place_kwargs.get("order_division", OrderDivision.MARKET)
            self._order_division[result.order_no] = _sent_division.value
            self._pending_buy_orders[result.order_no] = {
                "ticker": ticker,
                "price": record_price,
                "quantity": quantity,
                "strategy_id": strategy.strategy_id,
            }

            # cycle276 — AI 매수평가(shadow) 주문 시점 훅. 주문은 이미 KIS 에 접수됐고
            # 이 호출은 기록만 한다. 동기·never-raise·반환 미사용(Expr statement).
            # 자리 = 매핑 등록 **뒤** · `already_completed` 판정과 PENDING INSERT **앞**.
            # INSERT 뒤로 옮기면 체결통보 선행 코호트(가장 빨리 체결되는 진입)가
            # 기록에서 통째로 빠진다(명세 C7, 09-09 034020·09-10 004990 실측).
            try:
                llm_buy_gate.observe_order(
                    strategy_id=strategy.strategy_id,
                    ticker=ticker,
                    order_no=result.order_no,
                    order_kst=datetime.now(_KST_TZ),
                    order_price_won=record_price,
                    ordered_qty=quantity,
                    # 적대 검증 시정(LOW, exit) — 지역변수 `order_division` 이 아니라
                    # `_sent_division`(=`place_kwargs` 에서 뽑은 값, :886)을 쓴다.
                    # B2 게이트가 회귀해도(예: `== LIMIT` 로 되돌아가도) 이 필드는
                    # 실제 전송값과 항상 같다 — `_order_division` 매핑과 동일 소스.
                    order_division=_sent_division.value,
                    order_path="market",
                    exchange=buy_exchange,
                    current_price_won=current_price,
                    budget_total_won=state.total_investment,
                    budget_remaining_after_won=(
                        state.total_investment - strategy._calc_used_funds()
                    ),
                    open_positions_n=len(state.positions),
                    params_snapshot=dict(strategy.config.params),
                    # 꼬리를 자르지 않는다 — 전략이 `buy_signals` 를 이미 20건으로 cap 하므로
                    # `[-3:]` 는 비용을 아끼지 못하고(dict 20개 얕은 복사), 같은 종목의 신호가
                    # 그 3건 밖으로 밀리면 `_match_signal` 이 실패해 목표가·k·돌파 초과폭이
                    # 통째로 `None` 이 된다 — 값 없음으로 정직하게 기록되긴 하지만 회고분석은
                    # 그 주문을 쓸 수 없다(한 번에 여러 종목이 돌파하는 09:0x 가 그 구간이다).
                    buy_signals_tail=list(state.buy_signals),
                )
            except Exception:
                logger.debug("[llm_buy_gate_call] 주문 시점 관측 호출 실패", exc_info=True)

            # 체결통보 선행 체크 + PENDING INSERT — 4경로 공용 코어에 위임(cycle334).
            # 🔴 이 호출은 **경계를 닫지 않는다** — 매수 축의 접수 후 경계 부재는
            # 결함이고 별도 승인 사이클 소관이다(설계 카드 §2B). 여기에 try 를 들이면
            # 이 단계가 행위 보존이 아니게 된다.
            await self._persist_pending_after_send(
                trade_type=TradeType.BUY,
                ticker=ticker,
                order_no=result.order_no,
                strategy_id=strategy.strategy_id,
                record_price=record_price,
                quantity=quantity,
                path="market",
            )

            logger.info("매수 주문 접수: %s %d주 @ %d (주문번호: %s, 전략: %s)",
                         t(ticker), quantity, record_price, result.order_no, strategy.strategy_id)
            # 매수 접수 직후 캐시 무효화 — 다음 매수 호출 시 fresh 조회로 가용액 재산정
            state.cached_buyable_at = 0.0

        except KisApiError as e:
            state.pending_buys.discard(ticker)
            state.pending_buy_amounts.pop(ticker, None)
            if is_insufficient_cash(e):
                state.block_buy(time.time() + BUY_BLOCK_DURATION)
                logger.warning(
                    "매수 주문 잔고부족 → 매수 락(%ds): %s (전략: %s, [%s] %s)",
                    int(BUY_BLOCK_DURATION), t(ticker), strategy.strategy_id, e.msg_cd, e.msg1,
                )
                return
            # cycle291 — GTP(27) 거부는 우리 분류기 어디에도 걸리지 않는다
            # (`_MARKET_ORDER_DISALLOWED_KEYWORDS` 8종은 전부 "시장가"/"지정가만"
            # 계열, `_MARKET_CLOSED_KEYWORDS` 는 시간 계열). 미분류 매수 거부는
            # 이 핸들러 끝 `raise` 로 `risk.on_tick` 을 죽인다(cycle229 실증:
            # 8/20~8/27 매수 9건이 매일 15:30 WS 재연결을 유발). 그래서 게이트를
            # 키워드가 아니라 **"우리가 27 을 보냈다" 는 우리 쪽 사실**에 건다 —
            # 폴백 본문은 이미 같은 가격 `step_up(5)` + `00` 이라 신설 경로가 없다.
            if is_market_order_disallowed(e) or (
                order_division is OrderDivision.NXT_GTP_LIMIT
            ):
                if order_division is OrderDivision.NXT_GTP_LIMIT:
                    logger.warning(
                        "[pre_nxt_gtp_fallback] ticker=%s reason=rejected "
                        "msg_cd=%s msg1=%s",
                        t(ticker), e.msg_cd, e.msg1,
                    )
                # 시장가 거부 → 지정가 5호가 폴백 1회 (시장가 의도 보존)
                fallback_price = step_up(current_price, steps=5)
                try:
                    state.pending_buys.add(ticker)  # 폴백 진입 — 재등록
                    # 폴백 가격 기준으로 예정 금액 재등록 (시장가 경로와 동일 규약)
                    state.pending_buy_amounts[ticker] = fallback_price * quantity
                    result = await place_order(
                        ticker=ticker,
                        side=OrderSide.BUY,
                        quantity=quantity,
                        price=fallback_price,
                        order_division=OrderDivision.LIMIT,
                        exchange=buy_exchange,
                    )

                    # 매핑 즉시 등록 — await insert_trade 진입 전 동기 영역에서 처리.
                    # 시장가 경로와 동일한 순서 (루트 CLAUDE.md 안전 규칙 준수).
                    self._order_qty[result.order_no] = quantity
                    self._order_strategy[result.order_no] = strategy.strategy_id
                    self._order_ticker[result.order_no] = ticker
                    self._order_exchange[result.order_no] = buy_exchange
                    # cycle291 — 폴백은 항상 `00`(LIMIT) 을 전송한다.
                    self._order_division[result.order_no] = OrderDivision.LIMIT.value
                    self._pending_buy_orders[result.order_no] = {
                        "ticker": ticker,
                        "price": fallback_price,
                        "quantity": quantity,
                        "strategy_id": strategy.strategy_id,
                    }

                    # cycle276 — 지정가 5호가 폴백 경로의 AI 매수평가(shadow) 훅.
                    # 주 경로와 같은 형태·같은 자리. 흡수기가 `except Exception` 인
                    # 이유 = 이 훅은 `except KisApiError` 핸들러 **안**의 중첩 try 라
                    # 형제 핸들러가 non-KisApiError 를 못 잡는다 — 좁히면 관측 실패
                    # 하나가 pending 좀비(손절 마비)를 만든다(명세 C3).
                    try:
                        llm_buy_gate.observe_order(
                            strategy_id=strategy.strategy_id,
                            ticker=ticker,
                            order_no=result.order_no,
                            order_kst=datetime.now(_KST_TZ),
                            order_price_won=fallback_price,
                            ordered_qty=quantity,
                            order_division="LIMIT",
                            order_path="fallback",
                            exchange=buy_exchange,
                            current_price_won=current_price,
                            budget_total_won=state.total_investment,
                            budget_remaining_after_won=(
                                state.total_investment - strategy._calc_used_funds()
                            ),
                            open_positions_n=len(state.positions),
                            params_snapshot=dict(strategy.config.params),
                            # 주 경로와 같은 이유로 꼬리를 자르지 않는다(전략이 20건 cap).
                            buy_signals_tail=list(state.buy_signals),
                        )
                    except Exception:
                        logger.debug("[llm_buy_gate_call] 폴백 주문 시점 관측 호출 실패", exc_info=True)

                    # 체결통보 선행 체크 + PENDING INSERT — 4경로 공용 코어(cycle334).
                    await self._persist_pending_after_send(
                        trade_type=TradeType.BUY,
                        ticker=ticker,
                        order_no=result.order_no,
                        strategy_id=strategy.strategy_id,
                        record_price=fallback_price,
                        quantity=quantity,
                        path="fallback",
                    )

                    logger.warning(
                        "시장가 거부 → 지정가 5호가 폴백: %s @ %d (원인 [%s] %s)",
                        t(ticker), fallback_price, e.msg_cd, e.msg1,
                    )
                    state.cached_buyable_at = 0.0
                    return
                except KisApiError as e2:
                    state.pending_buys.discard(ticker)
                    state.pending_buy_amounts.pop(ticker, None)
                    state.block_low_funds(ticker, time.time() + LOW_FUNDS_COOLDOWN)
                    logger.error(
                        "지정가 폴백도 거부 → cooldown: %s ([%s] %s → [%s] %s)",
                        t(ticker), e.msg_cd, e.msg1, e2.msg_cd, e2.msg1,
                    )
                    return
            raise
        except Exception:
            state.pending_buys.discard(ticker)
            state.pending_buy_amounts.pop(ticker, None)
            raise

    async def execute_sell(
        self,
        ticker: str,
        signal: Signal,
        strategy_id: str,
        *,
        limit_price: int = 0,
    ) -> None:
        """매도 주문을 실행한다. 실패 시 최대 3회 재시도.

        `limit_price > 0` 이면 지정가(`ORD_DVSN=00`) 매도, 0 이면 시장가(`ORD_DVSN=01`).
        지정가는 NXT 프리 시간대 익일 청산 등에 사용된다 (P1(B) 옵션 B).
        호출자가 호가단위 정렬을 책임진다 (`src.engine.util.tick_size.step_down`).
        """
        # 매도 진행 중 중복 차단
        if ticker in self._selling:
            logger.debug("매도 진행 중 — 중복 차단: %s", t(ticker))
            return
        self._selling.add(ticker)
        self._selling_since[ticker] = datetime.now(_KST_TZ)

        # 사이클 55 R-1 (2026-06-03) — SellRejectionTracker 진입 게이트 위임.
        # 사이클 52 B-1 단일 TTL → 4 분류 통합 정책 객체 (2단계 TTL + 30초 TTL).
        # 진입 게이트 순서 (사이클 52 보존): selling.add → 게이트 → discard + return.
        now_kst = datetime.now(_KST_TZ)
        if self._sell_rejection.is_blocked(ticker, now_kst):
            if self._sell_rejection.should_emit_block_log(ticker):
                self._sell_rejection.mark_block_logged(ticker)
                _expiry_log = self._sell_rejection._blocked_until.get(ticker)
                await safe_write_log(
                    "INFO",
                    f"[market_closed_blocked] ticker={ticker} strategy={strategy_id} "
                    f"reason={self._sell_rejection._blocked_reason.get(ticker, '')} "
                    f"expiry={_expiry_log.isoformat() if _expiry_log else '?'}",
                    fallback_debug="[market_closed_blocked] write_log 실패",
                )
            self._selling.discard(ticker)
            return

        strategy = self.registry.get(strategy_id)
        if not strategy:
            logger.warning("전략 없음: %s", strategy_id)
            self._selling.discard(ticker)
            return

        pos = strategy.state.positions.get(ticker)
        if not pos:
            logger.warning("포지션 없음: %s (전략: %s)", t(ticker), strategy_id)
            self._selling.discard(ticker)
            return

        last_error: Exception | None = None
        insufficient_qty = False
        # 지정가 매도 분기 (P1(B))
        order_division = (
            OrderDivision.LIMIT if limit_price > 0 else OrderDivision.MARKET
        )
        order_unpr = limit_price if limit_price > 0 else 0
        # 지정가 NXT 청산은 거래소도 NXT 로 강제 (전략 기본 exchange 무관).
        # 시장가 청산은 stock_master 사전 차단(NXT/SOR → KRX) 적용 — Phase G.
        # cycle287 — 양쪽 다 규칙 1 라우터를 거친다(자문 §S3h/§R7). 호출자가
        # 현재 0곳(dead)이지만 `test_cycle100_strategy_exchange_persistence_sell.py`
        # 가 "limit_price > 0" 소스 문자열을 영속 단정하므로 분기 자체는 지우지
        # 않고 결과에만 라우팅을 씌운다.
        if limit_price > 0:
            target_exchange = self._apply_clock("NXT", strategy_id, side="sell", ticker=ticker)
        else:
            target_exchange = await self._strategy_exchange_async(
                strategy_id, ticker=ticker, side="sell"
            )

        # cycle295 (B) — 15:30~16:00 완전 휴식. `target_exchange` 산출 직후·
        # 재시도 루프 앞(§3-5①) — base·side·mode 와 무관하게 발사점에서
        # 판정한다(§3-2 반증: 라우터 안에 넣으면 `nxt_tradable=False` 코호트가
        # clause 1 에서 즉시 반환돼 컷을 통째로 비껴간다). "하지 말아야 할 것"
        # 4가지(§3-5①) — 거부 등록 안 함·익일청산 전환 안 함·포지션 불변·
        # `_selling` 유지 금지(유지하면 그 자체가 stale `_selling` 좀비다).
        if self._market_rest_gate(
            side="sell", ticker=ticker, strategy_id=strategy_id,
            base=target_exchange, now=datetime.now(_KST_TZ),
        ):
            self._selling.discard(ticker)
            self._selling_since.pop(ticker, None)
            return

        # NXT 프리 시장가 매도 사전 지정가 변환 (2026-08-06 — 매수 PR-F :323 대칭).
        # NXT 프리(08:00~09:00)는 KIS 정책상 지정가만 허용 — 시장가는 APBK0918 로
        # 100% 거부된다(30일 8건 실측, 매수는 PR-F 가 이미 차단하는데 매도엔 대칭
        # 코드가 없었다). risk 게이트가 LTV 외 전략의 프리장 청산 평가를 보류하므로
        # 이 변환의 실효 대상은 LTV(프리장 매매가 설계 의도)다. 매도는 호가 깊이로
        # **내려**(step_down) 체결률을 확보한다. 현재가 미수신이면 변환하지 않는다 —
        # 임의 가격 지정가가 더 위험하고, 시장가 거부 → market_closed 보류가 안전망.
        if order_division == OrderDivision.MARKET:
            try:
                from src.engine.scanner import ticker_prices as _tp
                from src.engine.session import MarketBoard, session_tracker
                _active = session_tracker.active
                _is_pre_nxt_only = (
                    MarketBoard.PRE_NXT in _active
                    and MarketBoard.MAIN not in _active
                )
                if _is_pre_nxt_only and target_exchange in ("NXT", "SOR"):
                    _cur = int(_tp.get(ticker, {}).get("current_price", 0) or 0)
                    if _cur > 0:
                        order_unpr = step_down(_cur, steps=5)
                        order_division = OrderDivision.LIMIT
                        logger.info(
                            "[sell_market_preconvert_pre_nxt] ticker=%s exchange=%s "
                            "current_price=%d converted_to_limit_price=%d",
                            ticker, target_exchange, _cur, order_unpr,
                        )
            except Exception:
                logger.debug(
                    "[sell_market_preconvert_pre_nxt] 판정 실패 — 시장가 유지: %s",
                    ticker, exc_info=True,
                )

        # cycle287 규칙 2 — KRX 애프터마켓(16:00~20:00, 2026-09-14 신설) 청산 호가
        # 변환. 프리장 사전 변환(위 블록) **뒤** · 재시도 루프 **앞** — 이 순서가
        # 계약이다(자문 §S5). `order_division == MARKET` 인 랏만 대상이라 지정가
        # 매도(limit_price>0)·프리장 사전 변환 결과와 상호배타다. VTS 는 41~47
        # 지원 여부가 정본에 없어 실전 전용(`settings.is_production`).
        # `primary_div`/`fallback_div` 는 아래 재시도 루프의 폴백 게이트를
        # "order_division == MARKET" 에서 "order_division == primary_div" 로
        # 일반화하는 데 쓰인다 — 정규장·프리장은 `primary_div is MARKET` 이라
        # 그 일반화가 기존 조건과 논리적으로 항등이다(byte 동일 증명, 보고서 참조).
        primary_div, fallback_div = OrderDivision.MARKET, OrderDivision.LIMIT
        _after_market_dial = ""
        try:
            if (
                order_division == OrderDivision.MARKET
                and target_exchange == "KRX"
            ):
                from src.config import settings
                if settings.is_production:
                    from src.engine.market_state import MarketPhase, get_market_state
                    _now_after = datetime.now(_KST_TZ)
                    if get_market_state(_now_after, market="KRX").phase is MarketPhase.AFTER_MARKET:
                        from src.engine.scanner import ticker_prices as _tp_after
                        _cur_after = int(
                            _tp_after.get(ticker, {}).get("current_price", 0) or 0
                        )
                        _after_market_dial = str(
                            strategy.config.params.get(
                                "after_market_exit_division", _AFTER_EXIT_DIVISION_DEFAULT
                            )
                        )
                        if _after_market_dial not in _AFTER_EXIT_DIVISION_ALLOWED:
                            _after_market_dial = _AFTER_EXIT_DIVISION_DEFAULT
                        if _after_market_dial == "44":
                            primary_div = OrderDivision.KRX_AFTER_BEST
                            fallback_div = OrderDivision.KRX_AFTER_LIMIT
                            order_division, order_unpr = primary_div, 0
                            logger.info(
                                "[after_exit_division] ticker=%s div=%s unpr=%d cur=%d "
                                "exchange=KRX dial=%s",
                                ticker, order_division.value, order_unpr, _cur_after,
                                _after_market_dial,
                            )
                        else:
                            primary_div = fallback_div = OrderDivision.KRX_AFTER_LIMIT
                            if _cur_after > 0:
                                order_division = primary_div
                                order_unpr = step_down(_cur_after, steps=5)
                                logger.info(
                                    "[after_exit_division] ticker=%s div=%s unpr=%d cur=%d "
                                    "exchange=KRX dial=%s",
                                    ticker, order_division.value, order_unpr, _cur_after,
                                    _after_market_dial,
                                )
                            else:
                                # 현재가 미확보 — 41 지정가 가격을 못 정한다.
                                # 임의 가격 지정가가 더 위험하다(기존 프리장 변환과
                                # 같은 판단) — 시장가 유지 + 주문은 그대로 나간다.
                                primary_div, fallback_div = (
                                    OrderDivision.MARKET, OrderDivision.LIMIT,
                                )
        except Exception:
            primary_div, fallback_div = OrderDivision.MARKET, OrderDivision.LIMIT
            order_division, order_unpr = OrderDivision.MARKET, 0
            logger.debug(
                "[after_exit_division] 판정 실패 — 시장가 유지: %s", ticker, exc_info=True,
            )

        for attempt in range(1, SELL_MAX_RETRIES + 1):
            # cycle327 ⓒ — 발사 직전 포지션 재확인. `pos` 는 `:1376` 에서 잡은
            # **지역 참조**라, 재시도 사이에 체결통보가 완주해 포지션이 사라져도
            # 옛 수량을 그대로 들고 있다. 매 시도마다 현재 상태를 다시 읽어,
            # 없어졌으면 발사하지 않고 끝낸다(이미 팔린 것을 다시 팔지 않는다).
            # 수량도 이 재조회 값에서 가져온다 — 피라미딩으로 한 종목의 수량이
            # 사다리로 변하게 되면 옛 참조의 수량은 더 이상 사실이 아니다.
            pos = strategy.state.positions.get(ticker)
            if not pos:
                logger.info(
                    "[sell_position_gone] ticker=%s strategy=%s attempt=%d — "
                    "재시도 전 포지션 소멸(체결 완료 추정) → 재발사 중단",
                    ticker, strategy_id, attempt,
                )
                self._selling.discard(ticker)
                return
            try:
                result = await place_order(
                    ticker=ticker,
                    side=OrderSide.SELL,
                    quantity=pos.quantity,
                    price=order_unpr,
                    order_division=order_division,
                    exchange=target_exchange,
                )

                # 주문번호 매핑 즉시 등록 — await insert_trade 진입 전 동기 영역에서 처리.
                # 시장가 즉시체결 시 체결통보가 insert_trade await 도중 도착해도 매핑이 보장된다.
                self._order_qty[result.order_no] = pos.quantity
                self._order_strategy[result.order_no] = strategy_id
                self._order_ticker[result.order_no] = ticker
                self._order_exchange[result.order_no] = target_exchange
                # cycle291 — 매도 주 경로. 전송한 값(정규장/프리장 `00`·`01`,
                # 애프터 `41`/`44`, 지정가 매도 `00`)을 그대로 기록한다.
                self._order_division[result.order_no] = order_division.value

                # 🔴 cycle327 ⓑ — 여기서부터 **주문은 이미 나갔다**. 접수 후 경계는
                # 헬퍼가 닫는다(매도 두 경로가 그 규칙을 한 곳에서 공유한다).
                await self._persist_sell_pending_after_send(
                    ticker=ticker,
                    order_no=result.order_no,
                    strategy_id=strategy_id,
                    record_price=pos.buy_price,
                    quantity=pos.quantity,
                    path="market",
                )

                logger.info(
                    "%s 매도 주문 접수: %s %d주 (주문번호: %s, 전략: %s)",
                    signal.value, t(ticker), pos.quantity, result.order_no, strategy_id,
                )
                return  # 성공 — _selling은 체결통보에서 제거

            except KisApiError as e:
                last_error = e
                # 1) 장운영시간 외 거부 — 재시도 의미 없고 positions 보존해야 함.
                #    다음 거래 가능 시각(예: 09:00 KRX 시가 확정 후)에 자연 재트리거되도록.
                if is_market_closed_rejection(e):
                    logger.warning(
                        "매도 장운영시간 외 거부 — positions 보존 + 재시도 중단: %s "
                        "(전략: %s, [%s] %s)",
                        t(ticker), strategy_id, e.msg_cd, e.msg1,
                    )
                    self._selling.discard(ticker)
                    await write_log(
                        "WARNING",
                        f"매도 거부(장운영시간 외) — 포지션 보존: {t(ticker)} "
                        f"(전략: {strategy_id}, [{e.msg_cd}] {e.msg1})",
                    )
                    # 사이클 55 R-1 (2026-06-03) — tracker.register_market_closed 위임.
                    # Q1 2단계 TTL: KRX 메인(09:00~15:30) = 5분, NXT 시간대 = 다음 09:00.
                    # emit cap 리셋(_logged_today.discard) 은 register_market_closed 내부에서 수행.
                    _now_kst = datetime.now(_KST_TZ)
                    self._sell_rejection.register_market_closed(
                        ticker, _now_kst, in_krx_main_hours=_exit_capable_krx_window(_now_kst)
                    )
                    # 사후 보강 (Phase G): NXT 거래 불가 종목으로 추정 → stock_master 에 즉시 반영.
                    # 다음 사이클에서 _strategy_exchange_async 가 KRX 로 사전 다운그레이드.
                    # NXT 시간대(08:00~09:00, 15:30~20:00) 거부에서만 적용 — KRX 정규장 거부는 보강하지 않음.
                    try:
                        # cycle286 (C4-a) — `nxt_tradable=False` 사후 보강의 판정축을
                        # **시계 단독 → 거래소 ∧ 좁힌 프리장 창**으로 바꾼다.
                        #  (1) 거래소: 이 주문을 어디로 보냈는지 우리가 이미 안다
                        #      (`target_exchange`, `:664`/`:666`). KRX 로 보낸 주문의
                        #      거부는 NXT 거래가능 여부의 증거가 0이다.
                        #  (2) 창: 2026-09-14 부터 KRX 애프터마켓(16:00~20:00)이 구
                        #      NXT 창 15:30~20:00 안에 통째로 들어온다. 그 구간의
                        #      거부는 어느 시장이 낸 것인지 가릴 수 없고(SOR 은 leg
                        #      정보가 없다), 16:30 이후의 오염은 그날 16:10 전수
                        #      재적재를 이미 지나쳐 **다음 영업일 프리장까지 ≈24h
                        #      존속**하며 자기 강화 래치가 된다. 판단 불가 = 쓰지
                        #      않는다(fail-safe). 상한 08:50 은 NXT 프리마켓 실질
                        #      종료(GTP 미체결 일괄취소) = market_state N1.end.
                        # ⚠️ 이 식은 `is_nxt_session_hours`(TTL 축, `:983`/`:1002`)와
                        #    **의도적으로 다르다** — TTL 은 "팔 수단이 없으니 길게
                        #    막는다" 가 안전측이라 15:30~20:00 유지, 학습은 "모르면
                        #    안 쓴다" 가 안전측이다. 두 축을 같은 창으로 되돌리지 말 것.
                        from datetime import time as _dtime
                        now_t = _now_kst.time()
                        _exchange_ok = target_exchange in ("NXT", "SOR")
                        _window_ok = _dtime(8, 0) <= now_t < _dtime(8, 50)
                        _nxt_evidence = _exchange_ok and _window_ok
                        if _nxt_evidence:
                            from src.db import stock_master
                            existing = await stock_master.get(ticker)
                            existing_raw = existing.raw if existing else {}
                            existing_name = existing.name if existing else ""
                            existing_excg = existing.excg_dvsn_cd if existing else ""
                            from src.models.stock import StockBasics
                            await stock_master.upsert_one(
                                StockBasics(
                                    ticker=ticker,
                                    name=existing_name,
                                    excg_dvsn_cd=existing_excg,
                                    nxt_tradable=False,
                                    krx_halted=existing.krx_halted if existing else False,
                                    admin_item=existing.admin_item if existing else False,
                                    raw=existing_raw,
                                )
                            )
                            logger.info(
                                "[nxt_post_reinforce] ticker=%s exchange=%s div=%s "
                                "now=%s wrote=1 reason=nxt_pre_window",
                                ticker, target_exchange, order_division.value,
                                now_t.strftime("%H:%M:%S"),
                            )
                        else:
                            # 적대 검증 LOW-4(behavior) — 두 조건이 동시에 실패하면
                            # (예: 09-14 이후 KRX 로 보낸 16:xx 애프터 거부는 거래소·
                            # 시각 둘 다 불만족) 종전엔 `exchange` 만 보여 이 사이클의
                            # 핵심 mandate(창 차단)를 `reason=window` 로 관측할 수
                            # 없었다. 복합값으로 **둘 다** 남긴다 — 앞자리가 항상
                            # `exchange`(불만족 시)이므로 기존 `reason=exchange`/
                            # `reason=window` 단독 문자열 판독(부분일치)과 호환된다.
                            _reason_parts = []
                            if not _exchange_ok:
                                _reason_parts.append("exchange")
                            if not _window_ok:
                                _reason_parts.append("window")
                            logger.info(
                                "[nxt_post_reinforce] ticker=%s exchange=%s div=%s "
                                "now=%s wrote=0 reason=%s",
                                ticker, target_exchange, order_division.value,
                                now_t.strftime("%H:%M:%S"),
                                "+".join(_reason_parts) if _reason_parts else "unknown",
                            )
                    except Exception:
                        logger.exception("stock_master 사후 보강 실패: %s", ticker)
                    # 적대 검증 시정(HIGH — market_closed 가 검사 순서 1번이라
                    # 구조적 폴백(41)에 전혀 도달하지 못하는데, cycle287 이 애프터
                    # 창의 TTL 을 5분으로 좁혀 놓아 저녁 내내 최대 ~48회를
                    # 41 을 한 번도 못 써 보고 재시도만 반복할 수 있다. 검사 순서·
                    # 보류 계약(2026-08-06 사용자 결정)은 동결이라 여기서 폴백을
                    # 열지 않는다 — 관측 + 그날 밤 포기 래치만 이 분기 안에서도
                    # 적용해 무제한 재시도를 K9 봉인②의 같은 상한으로 묶는다.
                    if primary_div is not OrderDivision.MARKET:
                        logger.info(
                            "[after_exit_rejected] ticker=%s div=%s msg_cd=%s "
                            "classified=closed ttl_registered=1 msg1=%s",
                            ticker, order_division.value, e.msg_cd, e.msg1,
                        )
                        self._bump_after_exit_fails_and_maybe_giveup(
                            ticker, strategy_id, _now_kst,
                        )
                    return  # positions / DB 보존, 다음 trigger 대기
                # 1.5) 수량 초과(APBK0400, cycle236 N2) — 잔고 재대조 → 수량 보정 재시도.
                #    "요청 > 가능" 은 부분 보유가 내재된 코드다(257720 실사고: 실보유 2주
                #    인데 positions 3주로 3회 재시도 전량 낭비 + 오버나잇). insufficient
                #    경로(통째 삭제)에 태우면 잔여 수량이 손절 감시 밖으로 떨어지므로,
                #    `sellable_quantity`(ord_psbl_qty — 기주문 잔량 차감 반영) 기준으로:
                #    부분 보유 = 보정+재시도(자기 치유) / 전량 잠김 = 보존+중단 /
                #    실보유 0 = 기존 insufficient 경로 / 조회 실패 = 현행 재시도(graceful).
                if is_sell_qty_exceeded(e):
                    sellable = None
                    try:
                        from src.api.balance import get_balance
                        holdings, _summary = await get_balance()
                        h = next((x for x in holdings if x.ticker == ticker), None)
                        held_qty = int(getattr(h, "quantity", 0) or 0) if h else 0
                        sellable = int(getattr(h, "sellable_quantity", 0) or 0) if h else 0
                    except Exception:
                        logger.warning(
                            "[sell_qty_exceeded] %s 잔고 재대조 실패 — 현행 재시도 유지 "
                            "(graceful)", ticker, exc_info=True,
                        )
                    if sellable is None:
                        pass  # 재대조 불가 — 아래 일반 재시도 흐름
                    elif 0 < sellable < pos.quantity and held_qty >= pos.quantity:
                        # 적대 검증 C236-F1 — positions 는 **정확**(held == positions)한데
                        # sellable 만 작다 = 외부(수동) 부분 매도주문 잠김. 오염이 아니므로
                        # 하향 보정 금지(잠긴 주식이 손절 감시 밖으로 떨어진다) — 보존+중단.
                        # `_selling` 유지 규약은 (b) 전량 잠김과 동일(열린 기주문 실재).
                        logger.warning(
                            "[sell_qty_partial_locked] ticker=%s strategy=%s held=%d "
                            "sellable=%d positions=%d — 외부 부분 매도주문 잠김, 보정 "
                            "없이 보존 + 중단 (기주문 체결통보/selling_reconcile 대기)",
                            ticker, strategy_id, held_qty, sellable, pos.quantity,
                        )
                        return
                    elif 0 < sellable < pos.quantity:
                        # 진짜 오염(held < positions) — 보정 목표는 sellable 이 아니라
                        # **held(보유 실체)** 다(C236-F1): 잠긴 주식도 보유는 보유라
                        # 손절 감시 수량은 held 가 정합. 재발사가 sellable 부족으로 다시
                        # 거부되면 그땐 held == positions 라 위 부분 잠김 분기가 흡수한다.
                        target_qty = held_qty if 0 < held_qty < pos.quantity else sellable
                        logger.warning(
                            "[sell_qty_reconciled] ticker=%s strategy=%s positions=%d → "
                            "%d 로 수량 보정 후 재시도 (%d/%d) — APBK0400 오염 자기 치유 "
                            "(held=%d sellable=%d)",
                            ticker, strategy_id, pos.quantity, target_qty,
                            attempt, SELL_MAX_RETRIES, held_qty, sellable,
                        )
                        pos.quantity = target_qty
                        try:
                            from src.db.positions import save_position
                            await save_position(
                                ticker=ticker,
                                ticker_name=t(ticker).split("(")[0] if "(" in t(ticker) else "",
                                buy_price=pos.buy_price,
                                quantity=target_qty,
                                order_no=pos.order_no,
                                strategy_id=strategy_id,
                                buy_date=pos.buy_date,
                                high_since_buy=pos.high_since_buy,
                            )
                        except Exception:
                            logger.exception(
                                "[sell_qty_reconciled] DB positions 수량 보정 실패: %s "
                                "(메모리는 보정 완료 — 단 sync 는 기보유 종목 수량을 "
                                "갱신하지 않으므로 DB 는 다음 보정/청산까지 구값 잔존)",
                                ticker,
                            )
                        continue
                    elif sellable == 0 and held_qty > 0:
                        # 전량이 기주문에 잠김 — 보정해도 거부 반복. 보존 + 중단.
                        # ⚠️ `_selling` 은 **의도적으로 유지**한다(discard 금지) —
                        # sellable=0·보유>0 = 열린 매도 기주문이 실재 = "매도 진행 중"
                        # 표식이 참이고, 유지가 on_tick 매 틱 재진입(APBK0400+
                        # get_balance 폭주)을 차단한다. 기주문 체결 시 통보가,
                        # 미체결 만료 시 `[selling_reconcile]`(180s age gate,
                        # 열린주문 존재 검사 포함)가 정확히 수습한다 — market_closed
                        # 분기의 discard 와 다른 이유는 그쪽엔 열린 주문이 없어서다.
                        logger.warning(
                            "[sell_qty_locked] ticker=%s strategy=%s held=%d sellable=0 "
                            "— 전량 기주문 잠김, positions 보존 + 재시도 중단 (기주문 "
                            "체결통보 또는 selling_reconcile 대기)", ticker, strategy_id,
                            held_qty,
                        )
                        return
                    elif sellable == 0 and held_qty == 0:
                        # 실보유 0 — 기존 insufficient 경로 재사용 (삭제 + reconciliation)
                        insufficient_qty = True
                        logger.warning(
                            "매도 매도가능수량 부족(APBK0400·실보유 0) — 재시도 중단: %s "
                            "(전략: %s)", t(ticker), strategy_id,
                        )
                        self._sell_rejection.register_insufficient_quantity(
                            ticker, now_kst)
                        break
                    else:
                        # sellable >= pos.quantity — 수량은 충분한데 초과 거부(이상).
                        logger.warning(
                            "[sell_qty_exceeded] ticker=%s sellable=%d >= positions=%d "
                            "인데 APBK0400 — 이상 상태, 일반 재시도 지속",
                            ticker, sellable, pos.quantity,
                        )
                # 2) 진짜 보유 부족(APBK1234 등) — 기존 동작 유지 + Q3 history 적재
                if is_insufficient_quantity(e):
                    insufficient_qty = True
                    logger.warning(
                        "매도 매도가능수량 부족 — 재시도 중단: %s (전략: %s, [%s] %s)",
                        t(ticker), strategy_id, e.msg_cd, e.msg1,
                    )
                    # 사이클 55 R-1 Q3 — history 적재 (차단 X: positions 제거가 자연 차단)
                    self._sell_rejection.register_insufficient_quantity(ticker, now_kst)
                    break
                # 3) 시장가 호가 불가(APBK1943 등) — 지정가 5호가 폴백 1회 (매수 패턴과 대칭).
                #    매도는 `step_down(current_price, 5)` 로 호가 깊이로 내려 체결률 확보.
                #    `limit_price>0` 인 지정가 매도에서는 이미 지정가 → 폴백 의미 없음, 기존 재시도 유지.
                #    폴백 실패 시 cooldown 등록 안 함 — 매도는 청산 의무, 다음 사이클 자연 재트리거.
                #    2026-05-11 계양전기 사례 대응 (`docs/kis/error-codes.md` 5-4절).
                # cycle287 규칙 2 — 애프터마켓(primary_div != MARKET)에서는 분류에
                # 의존하지 않는 **구조적 폴백**이다(자문 §1-E) — 44 거부의 msg1
                # 원문이 완전 미지라 키워드에 폴백을 인질로 줄 수 없다. 정규장·
                # 프리장은 `primary_div is MARKET` 이라 이 조건이 기존
                # `is_market_order_disallowed(e) and order_division == MARKET`
                # 과 논리적으로 항등이다.
                if order_division == primary_div and (
                    is_market_order_disallowed(e) or primary_div is not OrderDivision.MARKET
                ):
                    _after_market_primary = primary_div is not OrderDivision.MARKET
                    if _after_market_primary:
                        # K7 — 애프터 1차 거부 직후 ETP 관측(fail-open, 행위 분기 없음).
                        # 적대 검증 시정(MEDIUM) — 자문 §S5/§4-F 는 "관측을 행복
                        # 경로에 두면 손절에 DB 왕복 지연이 붙으므로 거부 후로
                        # 옮긴다" 고 명시했는데, 거부 후라도 `await` 로 41 폴백
                        # 주문 발사 앞을 막으면 지연이 그대로 남는다 — 41 발사와
                        # 무관하게 fire-and-forget 한다(`_log_stale_async` 선례,
                        # `:471` 과 동일 RuntimeError 흡수).
                        try:
                            asyncio.create_task(self._observe_after_exit_etp(ticker))
                        except RuntimeError:
                            logger.debug(
                                "[after_etp_exit_observe] task 등록 실패 — 이벤트 루프 없음",
                                exc_info=True,
                            )
                        logger.info(
                            "[after_exit_rejected] ticker=%s div=%s msg_cd=%s classified=%s "
                            "ttl_registered=1 msg1=%s",
                            ticker, order_division.value, e.msg_cd,
                            _classify_after_exit_rejection(e), e.msg1,
                        )
                    from src.engine.scanner import ticker_prices as _ticker_prices
                    px_info = _ticker_prices.get(ticker) or {}
                    cur_price = int(px_info.get("current_price") or 0)
                    if cur_price <= 0:
                        # 현재가 미확보 — 폴백 불가, 일반 재시도 흐름으로 폴백 (매도 의무 보존)
                        logger.warning(
                            "매도 시장가 호가 불가 — 현재가 캐시 미확보로 폴백 불가, 재시도 진행: %s "
                            "(전략: %s, [%s] %s)",
                            t(ticker), strategy_id, e.msg_cd, e.msg1,
                        )
                        if _after_market_primary:
                            # 적대 검증 시정(CRITICAL) — 이 분기는 폴백을
                            # 시도조차 못 하는데, 종전엔 봉인①(TTL 항상 등록)·
                            # 봉인②(그날 저녁 포기 래치)가 모두 미적용이었다.
                            # 그 결과 다음 틱에도 아무 차단이 없어 애프터마켓
                            # (16:00~20:00, 실시간 연속체결) 동안 매 틱 최대
                            # SELL_MAX_RETRIES(3)발씩 무제한 재발사할 수 있었다
                            # — 정확히 자문 §1-E 가 막으려던 폭주다.
                            _now_np = datetime.now(_KST_TZ)
                            _ttl_np_ok = self._register_after_exit_disallowed(
                                ticker, _now_np, fallback_succeeded=False,
                            )
                            logger.info(
                                "[after_exit_rejected] ticker=%s div=%s msg_cd=%s "
                                "classified=%s ttl_registered=%d msg1=no_price_for_fallback",
                                ticker, order_division.value, e.msg_cd,
                                _classify_after_exit_rejection(e), int(_ttl_np_ok),
                            )
                            self._bump_after_exit_fails_and_maybe_giveup(
                                ticker, strategy_id, _now_np,
                            )
                    else:
                        fallback_price = step_down(cur_price, steps=5)
                        try:
                            fb_result = await place_order(
                                ticker=ticker,
                                side=OrderSide.SELL,
                                quantity=pos.quantity,
                                price=fallback_price,
                                order_division=fallback_div,
                                exchange=target_exchange,
                            )

                            # 주문번호 매핑 즉시 등록 — await insert_trade 진입 전 동기 영역 (매수 패턴 동일).
                            self._order_qty[fb_result.order_no] = pos.quantity
                            self._order_strategy[fb_result.order_no] = strategy_id
                            self._order_ticker[fb_result.order_no] = ticker
                            self._order_exchange[fb_result.order_no] = target_exchange
                            # cycle291 — 매도 폴백(`fallback_div` — 정규장/
                            # 프리장 `00`, 애프터 `41`)의 실제 전송값을 기록한다.
                            self._order_division[fb_result.order_no] = fallback_div.value

                            # 🔴 cycle327 ⓑ — 폴백 주문도 이미 나갔다. 주 경로와 같은
                            # 헬퍼가 경계를 닫는다(문맥이 아니라 헬퍼가 예외를 막는다).
                            await self._persist_sell_pending_after_send(
                                ticker=ticker,
                                order_no=fb_result.order_no,
                                strategy_id=strategy_id,
                                record_price=fallback_price,
                                quantity=pos.quantity,
                                path="fallback",
                            )

                            logger.warning(
                                "매도 시장가 거부 → 지정가 5호가 폴백: %s @ %d "
                                "(원인 [%s] %s, 주문번호: %s, 전략: %s)",
                                t(ticker), fallback_price, e.msg_cd, e.msg1,
                                fb_result.order_no, strategy_id,
                            )
                            if _after_market_primary:
                                logger.info(
                                    "[after_exit_division] ticker=%s div=%s unpr=%d cur=%d "
                                    "exchange=%s dial=%s",
                                    ticker, fallback_div.value, fallback_price, cur_price,
                                    target_exchange, _after_market_dial,
                                )
                            # 사이클 55 R-1 Q2 — 폴백 성공 시에도 30초 TTL 등록 (동일 tick 폭주 차단).
                            # KRX/NXT 무관. next_day_clear_required = is_nxt AND NOT fallback_succeeded
                            # → 성공이므로 False.
                            _now_kst_fb = datetime.now(_KST_TZ)
                            self._sell_rejection.register_market_order_disallowed(
                                ticker, _now_kst_fb,
                                is_nxt_session=is_nxt_session_hours(_now_kst_fb),
                                fallback_succeeded=True,
                            )
                            return  # 폴백 성공 — _selling 은 체결통보에서 해제
                        except KisApiError as fb_err:
                            last_error = fb_err
                            logger.error(
                                "매도 지정가 폴백도 거부 — 재시도 중단, 포지션 보존: %s "
                                "([%s] %s → [%s] %s)",
                                t(ticker), e.msg_cd, e.msg1, fb_err.msg_cd, fb_err.msg1,
                            )
                            self._selling.discard(ticker)
                            await write_log(
                                "WARNING",
                                f"매도 시장가+지정가 폴백 모두 거부 — 포지션 보존: {t(ticker)} "
                                f"(전략: {strategy_id}, [{fb_err.msg_cd}] {fb_err.msg1})",
                            )
                            if _after_market_primary:
                                logger.info(
                                    "[after_exit_rejected] ticker=%s div=%s msg_cd=%s "
                                    "classified=%s ttl_registered=1 msg1=%s",
                                    ticker, fallback_div.value, fb_err.msg_cd,
                                    _classify_after_exit_rejection(fb_err), fb_err.msg1,
                                )
                            # 사이클 55 R-1 Q2 — 폴백 실패 30초 TTL + NXT 시 익일 청산 전환.
                            _now_kst_fb = datetime.now(_KST_TZ)
                            _is_nxt = is_nxt_session_hours(_now_kst_fb)
                            _result = self._sell_rejection.register_market_order_disallowed(
                                ticker, _now_kst_fb,
                                is_nxt_session=_is_nxt,
                                fallback_succeeded=False,
                            )
                            if _result.next_day_clear_required:
                                # NXT 폴백 실패 → 익일 09:00 KRX 시장가 청산 큐 등록
                                try:
                                    _pending = self._pending_next_day_clear_provider()
                                    if _pending is not None:
                                        _pending.add((ticker, strategy_id))
                                        await write_log(
                                            "WARNING",
                                            f"[next_day_clear_deferred] ticker={ticker} "
                                            f"strategy={strategy_id} "
                                            f"reason=market_order_disallowed_nxt_fallback_fail",
                                        )
                                except Exception:
                                    logger.debug(
                                        "[next_day_clear_deferred] _pending_next_day_clear 등록 실패: %s",
                                        ticker, exc_info=True,
                                    )
                            if _after_market_primary:
                                # cycle287 K9 봉인2 — 일일 포기 래치. 30초 TTL 만으로는
                                # 저녁 4시간에 ticker 당 ≈1,440 요청이 남는다. 임계
                                # 도달 시 그날 밤은 포기(다음 09:00 래치) — 위 30초
                                # TTL 등록보다 **뒤**에서 덮어써야 next-09:00 이 이긴다.
                                # 공용 헬퍼(적대 검증 시정) — `cur_price<=0` 분기와
                                # 같은 카운터·같은 임계를 공유한다.
                                self._bump_after_exit_fails_and_maybe_giveup(
                                    ticker, strategy_id, _now_kst_fb,
                                )
                            return  # positions/DB 보존, 다음 사이클 자연 재트리거
                logger.warning(
                    "매도 주문 실패 (시도 %d/%d): %s — [%s] %s",
                    attempt, SELL_MAX_RETRIES, ticker, e.msg_cd, e.msg1,
                )
                if attempt < SELL_MAX_RETRIES:
                    await asyncio.sleep(SELL_RETRY_DELAY * (2 ** (attempt - 1)))
            except Exception as e:
                last_error = e
                logger.warning(
                    "매도 주문 실패 (시도 %d/%d): %s — %s",
                    attempt, SELL_MAX_RETRIES, ticker, e,
                )
                if attempt < SELL_MAX_RETRIES:
                    await asyncio.sleep(SELL_RETRY_DELAY * (2 ** (attempt - 1)))

        # 모든 시도 실패 — 잔고부족이면 메모리 포지션 즉시 정리(스케줄러 sync로 후속 보정)
        self._selling.discard(ticker)
        if insufficient_qty:
            # KIS에 보유 수량이 없으므로 메모리 포지션도 제거. trade_history는 sync 시 보정.
            strategy.state.positions.pop(ticker, None)
            # 사이클 185 클러스터 ① 메커니즘 2 (secondary) — 보유결합 상태 정리 훅
            try:
                strategy.on_position_closed(ticker)
            except Exception as exc:
                logger.error(
                    "[on_position_closed_skip] ticker=%s strategy=%s err=%r",
                    ticker, strategy_id, exc,
                )
            from src.db.positions import delete_position
            try:
                await delete_position(ticker)
            except Exception:
                logger.exception("잔고부족 매도 후 DB positions 삭제 실패: %s", ticker)
            await write_log(
                "WARNING",
                f"매도가능수량 부족 — 메모리 포지션 정리: {t(ticker)} (전략: {strategy_id})",
            )
            # 사이클 55 R-1 Q3 — [positions_reconciliation] + get_balance() 1회.
            # 수동 부분매도 등으로 실제 잔량이 남아있는 경우를 대비해 잔고를 1회 재조회.
            # 실패 graceful — positions 제거는 이미 완료, 재조회는 보호 목적.
            await safe_write_log(
                "INFO",
                f"[positions_reconciliation] ticker={ticker} strategy={strategy_id} "
                f"reason=insufficient_quantity",
                fallback_debug="[positions_reconciliation] write_log 실패",
            )
            try:
                from src.api.balance import get_balance
                holdings, _ = await get_balance()
                actual_qty = next(
                    (h.quantity for h in holdings if h.ticker == ticker), 0
                )
                if actual_qty > 0:
                    logger.info(
                        "[positions_reconciliation] 실제 잔량 확인: %s qty=%d — positions 재등록 권고",
                        ticker, actual_qty,
                    )
            except Exception:
                logger.debug(
                    "[positions_reconciliation] get_balance 조회 실패: %s",
                    ticker, exc_info=True,
                )
            return
        error_msg = f"매도 주문 최종 실패: {ticker} {signal.value} — {last_error}"
        logger.critical(error_msg)
        await write_log("CRITICAL", error_msg)

    async def handle_execution_notice(
        self,
        ticker: str,
        order_no: str,
        side: str,
        price: int,
        quantity: int,
        *,
        ordered_qty_payload: int = 0,
    ) -> None:
        """체결통보를 처리한다.

        매수: 체결통보 수신 시 포지션 등록 (주문 시점이 아닌 체결 시점)
        매도: 체결 수량만큼 손익 계산, 포지션 제거
        부분 체결: PARTIAL 상태 기록 + 30초 후 잔여 취소
        """
        # 주문번호로 정확한 종목코드를 조회 (체결통보의 ticker는 신뢰하지 않음)
        known_ticker = self._order_ticker.get(order_no)
        if known_ticker:
            ticker = known_ticker
        else:
            if len(ticker) != 6 or not ticker.isalnum():
                logger.warning("체결통보: 주문번호 %s 종목매핑 없음 + payload ticker 비정상(%s), 처리 불가", order_no, ticker)
                # pending_buys 잔류 방지: _pending_buy_orders에서 ticker를 찾아 제거
                pending_info = self._pending_buy_orders.pop(order_no, None)
                if pending_info:
                    sid = pending_info.get("strategy_id", "")
                    strat = self.registry.get(sid)
                    if strat:
                        strat.state.pending_buys.discard(pending_info["ticker"])
                        strat.state.pending_buy_amounts.pop(pending_info["ticker"], None)
                        logger.warning("체결통보 매핑 실패 → pending_buys 제거: %s (전략: %s)", pending_info["ticker"], sid)
                return
            logger.warning("체결통보: 주문번호 %s에 대한 종목 매핑 없음, payload ticker 사용: %s", order_no, ticker)

        # cycle235 (적대 검증 C235-F1) — 체결통보의 CNTG_QTY 는 정본상 항상 양수다.
        # 0/음수(빈 필드 파싱 포함)는 이상 신호 → drop (fail-closed). 특히 매핑 부재
        # 폴백(ordered=quantity=0)과 결합하면 `0 >= 0` 전량 판정으로 BUY 0주 포지션
        # 봉인·SELL 포지션 무단 삭제가 가능하던 잔존 리스크의 조기 차단.
        if quantity <= 0:
            logger.warning(
                "[fill_qty_zero] order_no=%s ticker=%s side=%s quantity=%d — "
                "체결수량 비양수 통보 drop (정본상 CNTG_QTY 는 항상 양수)",
                order_no, ticker, side, quantity,
            )
            return

        # 원래 주문 수량 조회 — 우선순위 3단 (cycle329)
        #
        # 🔴 고치는 것 = `await place_order` 가 걸려 있는 동안 착지한 통보는
        # `order_no` 매핑이 **아직 비어 있어** `ordered_qty` 가 증분 체결량으로
        # 폴백되고, 그러면 `total_filled >= ordered_qty` 가 **항상 참**이 되어
        # 첫 부분 체결이 전량으로 읽힌다. 매도는 미체결 잔량이 손절 감시 밖으로
        # 사라지고, 매수는 `_completed_buy_orders` 가 무장해 잔여 통보가 조용히
        # 버려진 채 **영원히 적은 수량으로 믿는다**(15분 sync 도 기보유는 안 고친다).
        #
        # `map` = 우리 주문이고 매핑이 이미 섰다(정상, 하루 수천 건)
        # `payload` = KIS 가 실어 준 ODER_QTY. 매핑 부재 창에서 주문수량을 아는 유일한 길
        # `increment` = 둘 다 없다 → **현행 폴백 그대로**(행위 변경 0)
        known_ordered = order_no in self._order_qty
        payload_qty = ordered_qty_payload if ordered_qty_payload > 0 else 0
        if known_ordered:
            ordered_qty = self._order_qty[order_no]
            qty_src = "map"
            # 🔴 교차검증 — 정상 통보마다 payload 를 대조한다. `fields[16]` 배정이
            # 틀리면(cycle235 가 한 번 겪었다) 이 마커가 **매핑 부재 창을 기다리지 않고**
            # 즉시 드러낸다. 관측 전용이고 판정은 `map` 값을 쓴다.
            if payload_qty and payload_qty != ordered_qty:
                self._emit_ordered_qty_mismatch(
                    order_no, ticker, side, ordered_qty, payload_qty,
                )
        elif payload_qty:
            ordered_qty = payload_qty
            qty_src = "payload"
        else:
            ordered_qty = quantity
            qty_src = "increment"

        # 누적 체결 수량 추적
        prev_total = self._filled_qty.get(order_no, 0)
        self._filled_qty[order_no] = prev_total + quantity
        total_filled = self._filled_qty[order_no]

        # cycle235 — overrun 클램프 (BUY·SELL 공통 최후 방어망). 주문수량 초과 체결은
        # 물리적으로 불가하므로 누적 > 주문수량 = 파싱 오독/중복 통보 이상 신호다
        # (257720 실사고: fields[16] ODER_QTY 오독 유입 (1,2) → 합 3 → positions 3주
        # → 익일 3주 매도 전량 APBK0400). 클램프는 **주문수량을 실제로 아는 경우만** —
        # `qty_src == "increment"`(= 매핑도 payload 도 없는 수동/외부 주문)의
        # ordered=quantity 폴백은 신뢰 불가 값이라 다중 통보를 오캡하면 안 된다
        # (P1-B 멱등 가드가 기존 계약대로 담당). cycle329 가 `known_ordered` →
        # `qty_src != "increment"` 로 넓혔다 — payload ODER_QTY 는 KIS 가 준 주문수량이라
        # 매핑과 같은 신뢰도이고, 그것을 배제하면 이번에 고치는 그 창에서 클램프만 꺼진다.
        # ⚠️ 증분 `quantity` 도 동반 캡 (적대 검증 C235-R1) — `_handle_sell_fill` 이
        # `(price − buy) × quantity` 로 실현손익을 누적하므로, 누적만 캡하고 증분을
        # 원시값으로 흘리면 daily_realized_pnl(일일손실 게이트 소비)이 초과분만큼
        # 왜곡된다. 유효 증분 = ordered − 클램프 전 누적.
        if qty_src != "increment" and ordered_qty > 0 and total_filled > ordered_qty:
            logger.warning(
                "[fill_qty_overrun] order_no=%s ticker=%s side=%s total_filled=%d > "
                "ordered=%d — 주문수량으로 클램프 (파싱/중복 이상 신호, 관측 요망)",
                order_no, ticker, side, total_filled, ordered_qty,
            )
            self._filled_qty[order_no] = ordered_qty
            total_filled = ordered_qty
            quantity = max(0, ordered_qty - prev_total)

        self._emit_fill_qty_src(order_no, ticker, side, qty_src,
                                ordered_qty, total_filled, quantity)

        if side == "BUY":
            await self._handle_buy_fill(ticker, order_no, price, quantity, total_filled,
                                        ordered_qty, qty_src=qty_src)
        elif side == "SELL":
            await self._handle_sell_fill(ticker, order_no, price, quantity, total_filled,
                                         ordered_qty, qty_src=qty_src)

    async def _unsubscribe_if_no_other_strategy(self, ticker: str) -> None:
        """매도 전량 체결 후 WS 구독 정리 (사이클 15-A, 2026-05-19).

        KIS 정상 패턴: 불필요 종목 즉시 구독 해제 (5분 _scan_loop 자연 정리 대신).

        다음 모두 만족 시에만 unsubscribe:
        - `registry.is_ticker_held_by_any(ticker) == False` (다른 전략 보유 X)
        - `_pending_next_day_clear` 에 없음 (익일청산 대기 X)
        - 다른 전략 `get_scanned_tickers()` 에 없음 (스캔 후보 X)

        예외 시 swallow — 매도 체결 흐름 무관.
        """
        try:
            # 1) 다른 전략이 같은 종목 보유 중?
            if self.registry.is_ticker_held_by_any(ticker):
                logger.debug("[unsubscribe_skip] %s — 다른 전략 보유 중", ticker)
                return
            # 2) 익일청산 대기 set 에 있음?
            try:
                pending = self._pending_next_day_clear_provider() or set()
            except Exception:
                pending = set()
            for entry in pending:
                if isinstance(entry, tuple) and len(entry) >= 1 and entry[0] == ticker:
                    logger.debug("[unsubscribe_skip] %s — pending_next_day_clear", ticker)
                    return
            # 3) 다른 전략 스캔 후보?
            for strat in self.registry.all():
                try:
                    scanned = strat.get_scanned_tickers()
                except AttributeError:
                    scanned = []
                if ticker in scanned:
                    logger.debug(
                        "[unsubscribe_skip] %s — strategy=%s 스캔 후보",
                        ticker, strat.config.strategy_id,
                    )
                    return
            # 모두 통과 → unsubscribe
            # cycle293 — 매도 전량 체결 뒤 구독 정리는 **그 종목의 실제 채널**로
            # 나가야 한다. 틀린 채널 해제 = `OPSP0003 UNSUBSCRIBE ERROR not found!`
            # 스팸(cycle215~218 이 잡은 그 ERROR) + 구 채널 튜플의 영구 고아화.
            from src.engine.scanner import subscribed_tick_tr_id
            from src.realtime.websocket_pool import kis_ws_pool
            await kis_ws_pool.unsubscribe(subscribed_tick_tr_id(ticker), ticker)
            logger.info("[sell_unsubscribe] %s WS 구독 정리", t(ticker))
        except Exception:
            logger.exception("[sell_unsubscribe] %s 실패", ticker)

    def _resolve_pending_buy_owner(self, ticker: str) -> str | None:
        """그 종목의 매수 주문을 **방금 낸** 전략이 유일하게 하나인가 (cycle331).

        `await place_order` 가 걸린 동안은 주문번호 매핑이 전부 비어 있어 귀속을
        알 길이 없다. 그 창에서 이미 참인 유일한 사실이 `pending_buys` 다 —
        `execute_buy` 가 `place_order` **앞**에서 넣는다.

        채택 조건(전부 in-memory · `await` 0 · never-raise):
        - `ticker in state.pending_buys` 인 전략이 **정확히 1개**
        - 그 전략이 그 ticker 를 **보유하고 있지 않다**(신규 등록만 담당 —
          보유 중이면 추가 매수라 병합 규약이 따로 필요하다)

        0개·2개 이상·판정 예외는 **`None`**(현행 경로로 낙하 = fail-open).
        결과 집합이 현행의 부분집합이어야 이 단이 「좁히는 것」이지 「넓히는 것」이 아니다.

        🔴 `handle_execution_notice` 는 체결통보 콜백이고 그 예외는
        `realtime/handler.py` 규약상 **WS 재연결**을 부른다 — 이 판정이 무슨 일이 있어도
        밖으로 예외를 내보내면 안 된다.
        """
        try:
            owners = [
                s.strategy_id for s in self.registry.all()
                if ticker in getattr(s.state, "pending_buys", ())
            ]
            if len(owners) != 1:
                return None
            owner = owners[0]
            strat = self.registry.get(owner)
            if strat is None or ticker in strat.state.positions:
                return None
            return owner
        except Exception:
            logger.debug("[buy_fill_strategy_from_pending] 판정 실패", exc_info=True)
            return None

    async def _handle_buy_fill(
        self, ticker: str, order_no: str, price: int,
        quantity: int, total_filled: int, ordered_qty: int,
        *, qty_src: str = "map",
    ) -> None:
        """매수 체결 처리 — 체결통보 수신 시 올바른 전략에 포지션 등록.

        호출 chain (사이클 165 명문화):
          H0STCNI0 수신 → handler._handle_execution → OrderEngine.handle_execution_notice
            → _handle_buy_fill (본 함수, exec_type="2" 체결 분기)

        가드 매트릭스:
          - race: 체결통보가 REST 응답보다 먼저 도착 → `_completed_orders` set 등록 후
            `update_trade_status` UPDATE 영향 0건 시 보정 INSERT (사이클 30 영속).
          - **멱등 (P1-B, 2026-07-29, B-1)**: 전량 체결 완료된 order_no 의 후속 중복 체결통보는
            `_completed_buy_orders` (사이클 30 `_completed_orders` 와 별도 목적 — race 보정용이
            아닌 순수 멱등 가드) 로 즉시 무시. 377450 실사고 — 동일 order_no 2차 통보가
            매핑 pop 이후 도착 시 momentum 하드코딩 폴백으로 kojiro 포지션이 실명되던 결함 차단.
          - strategy 복구 (사이클 147): `_order_strategy` 매핑 dict miss 시
            trade_history PENDING row 영역 lookup 폴백 → momentum 하드코딩 최후 폴백.
          - **폴백 안전 (P1-B, B-2)**: momentum 하드코딩 폴백 직전, ticker 가 이미 어느
            전략이든 보유 중이면 덮어쓰기 대신 skip (기존 포지션 보존).
          - **폴백 가시화 (P1-B, B-3)**: B-1/B-2 미해당인데도 momentum 폴백으로 신규
            포지션이 등록되면 `system_logs` CRITICAL 1행 (fire-and-forget, hot path 블로킹 0).
          - 체결가 정합 (사이클 161): `update_trade_status(..., price=price)` 인자 명시 의무.
            CNTG_UNPR (handler.py fields[10]) = trade_history.price 영구 정합
            (005940 6/16 BUY 50원 차이 시정 영속).
          - UniqueViolation (사이클 161 hotfix): 보정 INSERT 영역 try/except + 강제 UPDATE
            (`_update_trade_status_by_order_no(price=price)`) 폴백.
          - 부분 체결: PARTIAL 상태 + price 인자 명시 (잔여 물량 추적).

        영속 의무:
          사이클 30 trade_history 부분 UNIQUE 인덱스 / 사이클 38 명문화 /
          사이클 102 G-REJECT-1 callback exception raise / 사이클 147 strategy fallback /
          사이클 161 price 정합 / 사이클 163 DB 격리 chain.
        """
        if order_no in self._completed_buy_orders:
            # P1-B (B-1) — 전량 체결 완료된 order_no 의 후속 통보. positions/trade_history/
            # pending 매핑 무변경 (이미 정리 완료) + 즉시 return.
            logger.info(
                "[buy_fill_duplicate_ignored] order_no=%s ticker=%s price=%d qty=%d "
                "— 전량 체결 완료 후 중복 체결통보 무시",
                order_no, ticker, price, quantity,
            )
            return

        orphan_momentum_fallback = False
        strategy_from_pending = False
        strategy_id = self._order_strategy.get(order_no)
        if strategy_id is None:
            # 매핑 dict miss — boot/reboot race. trade_history PENDING row 영역 strategy 복구.
            strategy_id = await _lookup_strategy_from_trade_history(
                ticker, order_no, TradeType.BUY,
            )
            if strategy_id is None:
                # cycle331 — **발사 창 귀속 단**. `order_no` 는 KIS 응답 전까진 존재하지
                # 않으므로 주문번호 축으로는 원리상 가를 수 없다. 창 안에서 이미 참인
                # 유일한 사실은 "그 전략이 그 종목의 매수 주문을 방금 냈다" = `pending_buys` 다.
                #
                # 🔴 고치는 것 = `await place_order` 가 걸린 동안 착지한 **우리 자신의**
                # 매수 체결이 아래 P1-B(B-2) 가드에 걸려 **Position 이 아예 등록되지
                # 않던 것**. 매수 당사자가 `execute_buy` 에서 스스로 `pending_buys` 에
                # 넣고 그 뒤에 `await` 로 양보하므로, `is_ticker_held_by_any`
                # (= `has_position OR is_buy_pending`, 자기 자신 포함)가 **예외 없이** 참이 된다.
                # 그러면 그날 하루 손절·트레일링·15:20 청산이 성립하지 않는다
                # (`risk.on_tick` 은 `state.positions` 를 본다). 실측 96건 중 2건(2.1%),
                # **1주 랏에 집중**된다 — 두 번째 통보가 없어 자기 치유 경로가 구조적으로 없다.
                #
                # 채택은 **정확히 1개 전략만 pending 이고 그 전략이 미보유**일 때뿐이다.
                # 0개·2개 이상은 물러선다(fail-open, 결과 집합 ⊆ 현행). 수동 매매·외부
                # 주문은 우리 `pending_buys` 에 없으므로 **한 글자도 바뀌지 않는다**.
                pending_owner = self._resolve_pending_buy_owner(ticker)
                if pending_owner is not None:
                    strategy_id = pending_owner
                    strategy_from_pending = True
                    logger.warning(
                        "[buy_fill_strategy_from_pending] order_no=%s ticker=%s strategy=%s "
                        "qty_src=%s incr=%d filled_total=%d ordered=%d — 발사 창 귀속",
                        order_no, t(ticker), strategy_id, qty_src,
                        quantity, total_filled, ordered_qty,
                    )
                # P1-B (B-2) — momentum 하드코딩 폴백 직전, ticker 가 이미 어느 전략이든
                # 보유/주문중이면 덮어쓰기 대신 skip (기존 포지션 보존, 377450 실사고 재현 차단).
                # ⚠️ 문구 정정(cycle331) — 종전 "이미 타 전략 보유 중" 은 **거짓이었다**.
                # 실측 2건 모두 *타 전략*이 아니라 **자기 전략**이었고 *보유*가 아니라
                # **주문 중**이었다. 운영자가 그 ERROR 를 읽고 정확히 반대로 이해했다.
                elif self.registry.is_ticker_held_by_any(ticker):
                    logger.error(
                        "[buy_fill_fallback_held_conflict] order_no=%s ticker=%s — 매핑 dict/"
                        "trade_history 모두 miss + 타 전략 보유/주문중 → momentum 폴백 skip",
                        order_no, ticker,
                    )
                    return
                else:
                    logger.warning(
                        "[buy_fill_strategy_lookup_fallback] order_no=%s ticker=%s — 매핑 dict miss + trade_history miss → momentum 폴백",
                        order_no, ticker,
                    )
                    strategy_id = "momentum"
                    orphan_momentum_fallback = True
            else:
                logger.info(
                    "[buy_fill_strategy_lookup_recovered] order_no=%s ticker=%s strategy=%s — 매핑 dict miss + trade_history 복구",
                    order_no, ticker, strategy_id,
                )
        strategy = self.registry.get(strategy_id)
        if not strategy:
            logger.error("체결통보: 전략 찾을 수 없음: %s (order_no: %s)", strategy_id, order_no)
            return

        state = strategy.state
        pos = state.positions.get(ticker)

        if not pos:
            # 첫 체결 → 포지션 신규 등록
            state.positions[ticker] = Position(
                ticker=ticker,
                buy_price=price,
                quantity=total_filled,
                order_no=order_no,
                strategy_id=strategy_id,
            )
            state.fill_count_today += 1
            logger.info("매수 체결 → 포지션 등록: %s %d주 @ %d (전략: %s)", t(ticker), total_filled, price, strategy_id)
            if orphan_momentum_fallback:
                # P1-B (B-3) — B-1/B-2 미해당인데도 momentum 폴백으로 신규 포지션 등록됨
                # (진짜 고아 체결). 운영자 즉시 인지용 CRITICAL — fire-and-forget, hot path 블로킹 0.
                asyncio.create_task(write_log(
                    "CRITICAL",
                    f"[buy_fill_fallback_orphan] order_no={order_no} ticker={ticker} "
                    f"strategy=momentum(폴백) — 매핑/trade_history 모두 miss + 미보유 → "
                    f"신규 포지션 등록됨. 진짜 고아 체결 여부 즉시 확인 필요",
                ))
        else:
            # 추가 체결 (부분 체결 이후) → 수량/가격 갱신
            pos.quantity = total_filled
            pos.buy_price = price

        # pending_buys에서 제거 + 예정 금액 정리 (잔여 자금 폴백 계산용 동기 dict)
        state.pending_buys.discard(ticker)
        state.pending_buy_amounts.pop(ticker, None)
        # _pending_buy_orders 정리
        self._pending_buy_orders.pop(order_no, None)

        if total_filled >= ordered_qty:
            # 전량 체결 → DB 포지션 저장
            # 사이클 161 (2026-06-17): `price=price` 인자 명시 — KIS CNTG_UNPR (체결단가)
            # → trade_history.price 갱신 의무 (사용자 보고 005940 BUY 33,400원 vs HTS 33,350원 +50원 차이 시정).
            # PENDING INSERT 시점 record_price (주문가 LIMIT / scanner current_price MARKET)
            # → COMPLETED UPDATE 시점에 체결단가로 정합 보정.
            #
            # 사이클 163 (2026-06-18): 3 영역 try/except 분리 + 가시화 강화.
            # 6/17 12:43:09 알지노믹스 (476830) callback_exception 영구 차단.
            # 사이클 88 G-REJECT-1 부분 예외 (DB INSERT race 는 재연결로 해결 안 됨).
            # 메모리 positions 등록은 이미 완료 → DB 영역만 graceful, callback raise 0건.
            # `_on_tick` / `_on_board` raise 영속 의무 영역 변경 0 (다른 callback 영역 한정).

            # 영역 1: update_trade_status (PENDING → COMPLETED)
            # cycle273a (D2-가-b) — match_partial=True: 부분 체결로 이미 PARTIAL 이 된
            # 행도 이 1차 UPDATE 로 직접 잡는다(§3.2 — 004990 09-10 09:05 3단 우회 시정).
            try:
                affected = await update_trade_status(
                    ticker, TradeType.BUY, TradeStatus.COMPLETED,
                    strategy=strategy_id, price=price, order_no=order_no, match_partial=True,
                )
            except Exception as exc:
                logger.error(
                    "[buy_fill_db_error] step=update_trade_status ticker=%s order_no=%s err=%r",
                    ticker, order_no, exc,
                )
                affected = 0

            if affected == 0:
                # 체결통보가 execute_buy의 insert_trade(PENDING)보다 먼저 도착한 race
                # → COMPLETED 상태로 직접 INSERT, execute_buy 측에 PENDING INSERT 생략 신호
                self._completed_orders.add(order_no)
                from src.engine.scanner import ticker_names as _tn
                try:
                    await insert_trade(TradeRecord(
                        ticker=ticker,
                        ticker_name=_tn.get(ticker, ""),
                        trade_type=TradeType.BUY,
                        price=price,
                        quantity=total_filled,
                        profit_loss=0,
                        status=TradeStatus.COMPLETED,
                        strategy=strategy_id,
                        order_no=order_no,
                    ))
                    logger.warning(
                        "체결통보 선행 race — COMPLETED 직접 INSERT: 매수 %s (주문번호: %s)",
                        t(ticker), order_no,
                    )
                except Exception as exc:
                    # 사이클 161 (2026-06-17): 사이클 147 _handle_sell_fill 패턴 100% 답습.
                    # 사이클 30 부분 UNIQUE 인덱스 (ticker, order_no, trade_type) 위반 영역
                    # = PENDING row strategy 불일치 시 매핑 fallback 후에도 잔존 PENDING row 충돌.
                    # → strategy 무관 order_no 단일 키 강제 UPDATE (체결단가 정합 의무).
                    logger.warning(
                        "[buy_fill_correction_unique_violation] ticker=%s order_no=%s strategy_attempted=%s err=%r → strategy 무관 강제 COMPLETED UPDATE",
                        ticker, order_no, strategy_id, exc,
                    )
                    # 사이클 163 — forced UPDATE 영역도 try/except 분리 + 가시화 강화
                    try:
                        forced_affected = await _update_trade_status_by_order_no(
                            order_no, TradeType.BUY, TradeStatus.COMPLETED,
                            price=price,
                        )
                        if forced_affected == 0:
                            logger.error(
                                "[buy_fill_correction_forced_update_zero] ticker=%s order_no=%s — 강제 UPDATE 영역 0건 (PENDING row 부재 의심)",
                                ticker, order_no,
                            )
                    except Exception as exc2:
                        logger.error(
                            "[buy_fill_db_error] step=forced_update ticker=%s order_no=%s err=%r",
                            ticker, order_no, exc2,
                        )

            # 영역 3: save_position (positions DB INSERT)
            # 6/17 12:43:09 알지노믹스 사고 영역 핵심 — DB 미동기화 시 15분 sync 회복 기대.
            try:
                from src.db.positions import save_position
                from src.engine.scanner import ticker_names
                await save_position(
                    ticker=ticker, ticker_name=ticker_names.get(ticker, ""),
                    buy_price=price, quantity=total_filled, order_no=order_no,
                    strategy_id=strategy_id, buy_date=state.positions[ticker].buy_date,
                )
            except Exception as exc:
                logger.error(
                    "[buy_fill_db_error] step=save_position ticker=%s order_no=%s err=%r — 메모리 등록 영속, 15분 sync 회복 기대",
                    ticker, order_no, exc,
                )

            self._filled_qty.pop(order_no, None)
            self._order_qty.pop(order_no, None)
            self._order_strategy.pop(order_no, None)
            self._order_ticker.pop(order_no, None)
            self._order_exchange.pop(order_no, None)
            self._order_division.pop(order_no, None)  # cycle291 — 선례와 같은 자리
            # P1-B (B-1) — 전량 체결 처리 완료 시점 동기 등록. 매핑 pop 이후 도착하는
            # 동일 order_no 후속 체결통보를 함수 진입부에서 즉시 무시하기 위한 멱등 마커.
            self._completed_buy_orders.add(order_no)
            # 매수 체결 → 가용액이 변동했으므로 캐시 무효화
            state.cached_buyable_at = 0.0
            logger.info("매수 전량 체결: %s %d주 @ %d (전략: %s)", t(ticker), total_filled, price, strategy_id)
            # cycle273a (D2-가-a) — 자기 order_no 의 잔여취소 타이머 해제.
            # order_no 가 일치할 때만 지운다(§1.4 — 004990 09-10 09:05 APBK0927 재현 차단).
            # cycle332 — 키가 `(ticker, 축)` 이라 **매수 축만** 본다. 해제의 order_no
            # 게이트는 그대로다 — 이 사이클이 좁힌 것은 등록 축뿐이다.
            _ck = (ticker, CANCEL_AXIS_BUY)
            if self._pending_cancel_order_no.get(_ck) == order_no:
                _cancel_task = self._pending_cancel_tasks.pop(_ck, None)
                self._pending_cancel_order_no.pop(_ck, None)
                if _cancel_task is not None and not _cancel_task.done():
                    _cancel_task.cancel()
                logger.info("[partial_cancel_timer_cleared] ticker=%s order_no=%s", t(ticker), order_no)
        else:
            # 부분 체결 → PARTIAL 기록, 30초 후 잔여 취소
            # 사이클 161 (2026-06-17): `price=price` 인자 명시 — 부분 체결 시점 체결단가 정합.
            await update_trade_status(
                ticker, TradeType.BUY, TradeStatus.PARTIAL,
                strategy=strategy_id, price=price, order_no=order_no,
            )
            # 🔴 cycle331 필수 동반 조항 — **귀속이 확정된 랏에만** 잔량 취소 타이머를 건다.
            # cycle331 이 `pending` 귀속 단을 열면서 발사 창의 통보가 **처음으로** 이
            # 분기에 도달한다. `_cancel_after_wait` 는 30초 뒤 잔량을 취소하는데,
            # 귀속이 틀린 랏(특히 `boot_manager` 가 KIS 미체결로 seed 한 `pending_buys`
            # 잔존)에서 걸리면 **사람이 낸 주문을 우리가 취소한다** —
            # cycle327(주문 나간 뒤 재발사 금지)·cycle329(재주문 타이머는 map 한정)와
            # 같은 계열의 사고다. 잃는 것은 없다 — 우리 주문이면 매핑이 곧 서고 잔여
            # 통보가 `src=map` 으로 와서 정상적으로 타이머를 건다.
            if qty_src == "map" and not strategy_from_pending:
                self._schedule_cancel(ticker, order_no, ordered_qty, strategy_id)
            else:
                logger.warning(
                    "[buy_partial_no_cancel_timer] order_no=%s ticker=%s strategy=%s "
                    "src=%s from_pending=%d remaining=%d — 귀속 확정 전이라 취소 타이머 보류",
                    order_no, t(ticker), strategy_id, qty_src,
                    int(strategy_from_pending), max(0, ordered_qty - total_filled),
                )
            logger.info("매수 부분 체결: %s %d/%d주 @ %d (전략: %s)", t(ticker), total_filled, ordered_qty, price, strategy_id)

    async def _handle_sell_fill(
        self, ticker: str, order_no: str, price: int,
        quantity: int, total_filled: int, ordered_qty: int,
        *, qty_src: str = "map",
    ) -> None:
        """매도 체결 처리 — 올바른 전략에서 포지션 제거.

        호출 chain (사이클 165 명문화):
          H0STCNI0 수신 → handler._handle_execution → OrderEngine.handle_execution_notice
            → _handle_sell_fill (본 함수, side=="SELL" + exec_type="2" 체결 분기)

        가드 매트릭스:
          - strategy 복구 (사이클 147): `_order_strategy` 매핑 dict miss 시
            trade_history PENDING row 영역 lookup 폴백 → momentum 하드코딩 최후 폴백.
            005940 NH투자증권 LTV SELL trade_history PENDING ~6h 잔존 사고
            (2026-06-16 08:00→09:18) 영구 차단.
          - 체결가 정합: `update_trade_status(SELL, COMPLETED, price=price)` 인자 명시.
            CNTG_UNPR (handler.py fields[10]) = trade_history.price 정합.
          - UniqueViolation: 보정 INSERT 영역 try/except + `_update_trade_status_by_order_no`
            강제 UPDATE 폴백.
          - WS 구독 정리 (사이클 15-A): `_unsubscribe_if_no_other_strategy(ticker)` —
            모든 전략에서 보유/익일청산/scanned 부재 시만 unsubscribe.
          - sold_today 등록: 당일 동일 ticker 재매수 차단 (`is_ticker_blocked_for_buy`).

        영속 의무:
          사이클 19 `_selling` 가드 / 사이클 30 trade_history 부분 UNIQUE /
          사이클 38 명문화 / 사이클 102 G-REJECT-1 callback exception raise /
          사이클 147 strategy fallback / 사이클 161 price 정합 / 사이클 163 DB 격리 chain.
        """
        strategy_id = self._order_strategy.get(order_no)
        if strategy_id is None:
            # 매핑 dict miss — boot/reboot race (005940 사고 영역 정합).
            # trade_history PENDING row 영역 strategy 복구 → update_trade_status 영역 영구 정합.
            strategy_id = await _lookup_strategy_from_trade_history(
                ticker, order_no, TradeType.SELL,
            )
            if strategy_id is None:
                logger.warning(
                    "[sell_fill_strategy_lookup_fallback] order_no=%s ticker=%s — 매핑 dict miss + trade_history miss → momentum 폴백",
                    order_no, ticker,
                )
                strategy_id = "momentum"
            else:
                logger.info(
                    "[sell_fill_strategy_lookup_recovered] order_no=%s ticker=%s strategy=%s — 매핑 dict miss + trade_history 복구",
                    order_no, ticker, strategy_id,
                )
        strategy = self.registry.get(strategy_id)
        if not strategy:
            logger.error("매도 체결: 전략 찾을 수 없음: %s (order_no: %s)", strategy_id, order_no)
            self._selling.discard(ticker)
            return

        state = strategy.state
        pos = state.positions.get(ticker)
        if not pos:
            logger.warning("매도 체결: 포지션 없음 — 손익 계산 생략: %s (order_no: %s)", t(ticker), order_no)
            buy_price = price  # 손익 0으로 처리
        else:
            buy_price = pos.buy_price
        profit_loss = (price - buy_price) * quantity
        state.daily_realized_pnl += profit_loss

        if total_filled >= ordered_qty:
            # 전량 체결 → 포지션 제거 + DB 삭제 + 매도 잠금 해제 + 당일 재매수 차단
            if pos:
                del state.positions[ticker]
            # 사이클 185 클러스터 ① 메커니즘 2 — 보유결합 상태 정리 훅
            try:
                strategy.on_position_closed(ticker)
            except Exception as exc:
                logger.error(
                    "[on_position_closed_skip] ticker=%s strategy=%s err=%r",
                    ticker, strategy_id, exc,
                )
            state.sold_today.add(ticker)
            from src.db.positions import delete_position
            await delete_position(ticker)
            self._selling.discard(ticker)
            # cycle273a (D2-가-b) — match_partial=True: 부분 체결로 이미 PARTIAL 이 된
            # 행도 이 1차 UPDATE 로 직접 잡는다(매수 축과 동일 계약, §3.2).
            affected = await update_trade_status(
                ticker, TradeType.SELL, TradeStatus.COMPLETED,
                strategy=strategy_id, price=price, profit_loss=profit_loss,
                order_no=order_no, match_partial=True,
            )
            if affected == 0:
                # 체결통보가 execute_sell의 insert_trade(PENDING)보다 먼저 도착한 race
                # → COMPLETED 상태로 직접 INSERT, execute_sell 측에 PENDING INSERT 생략 신호
                self._completed_orders.add(order_no)
                from src.engine.scanner import ticker_names as _tn
                try:
                    await insert_trade(TradeRecord(
                        ticker=ticker,
                        ticker_name=_tn.get(ticker, ""),
                        trade_type=TradeType.SELL,
                        price=price,
                        quantity=total_filled,
                        profit_loss=profit_loss,
                        status=TradeStatus.COMPLETED,
                        strategy=strategy_id,
                        order_no=order_no,
                    ))
                    logger.warning(
                        "체결통보 선행 race — COMPLETED 직접 INSERT: 매도 %s (주문번호: %s, 손익: %d)",
                        t(ticker), order_no, profit_loss,
                    )
                except Exception as exc:
                    # 사이클 147 (2026-06-16): 사이클 30 UNIQUE 인덱스 (ticker, order_no, trade_type)
                    # 위반 영역 (005940 사고 정합 — PENDING row strategy 불일치 시 매핑 fallback 후에도
                    # 잔존 PENDING row 영역 충돌). strategy 무관 order_no 단일 키 강제 UPDATE.
                    logger.warning(
                        "[sell_fill_correction_unique_violation] ticker=%s order_no=%s strategy_attempted=%s err=%r → strategy 무관 강제 COMPLETED UPDATE",
                        ticker, order_no, strategy_id, exc,
                    )
                    forced_affected = await _update_trade_status_by_order_no(
                        order_no, TradeType.SELL, TradeStatus.COMPLETED,
                        price=price, profit_loss=profit_loss,
                    )
                    if forced_affected == 0:
                        logger.error(
                            "[sell_fill_correction_forced_update_zero] ticker=%s order_no=%s — 강제 UPDATE 영역 0건 (PENDING row 부재 영구 영속 의심)",
                            ticker, order_no,
                        )
            self._filled_qty.pop(order_no, None)
            self._order_qty.pop(order_no, None)
            self._order_strategy.pop(order_no, None)
            self._order_ticker.pop(order_no, None)
            self._order_exchange.pop(order_no, None)
            self._order_division.pop(order_no, None)  # cycle291 — 선례와 같은 자리
            logger.info("매도 전량 체결: %s %d주 @ %d (손익: %d, 전략: %s)", t(ticker), total_filled, price, profit_loss, strategy_id)
            # cycle273a (D2-가-a) — 자기 order_no 의 잔여취소/재주문 타이머 해제(매수 축과
            # 동일 게이트, §1.4). 해제하지 않으면 `_cancel_and_reorder` 가 30초 뒤 잔량 0 인
            # 주문을 취소하려다 APBK0927 로 거부되거나, 더 나쁘면 낡은 `remaining` 으로
            # 중복 매도 재주문을 낸다(§1.3).
            # cycle332 — 매도 축만 본다(등록 축 분리). order_no 게이트는 불변.
            _ck = (ticker, CANCEL_AXIS_SELL)
            if self._pending_cancel_order_no.get(_ck) == order_no:
                _cancel_task = self._pending_cancel_tasks.pop(_ck, None)
                self._pending_cancel_order_no.pop(_ck, None)
                if _cancel_task is not None and not _cancel_task.done():
                    _cancel_task.cancel()
                logger.info("[partial_cancel_timer_cleared] ticker=%s order_no=%s", t(ticker), order_no)
            # 사이클 15-A (2026-05-19) — 매도 전량 체결 후 WS 구독 정리 (KIS 정상 패턴).
            # 다른 전략이 보유하지 않고, 익일청산 대기 X, 다른 전략 스캔 후보 X 인 경우만 unsubscribe.
            await self._unsubscribe_if_no_other_strategy(ticker)
        else:
            # 부분 체결 → PARTIAL, 30초 후 잔여 취소 + 손절 시 재주문
            await update_trade_status(ticker, TradeType.SELL, TradeStatus.PARTIAL, strategy=strategy_id, price=price, profit_loss=profit_loss, order_no=order_no)
            remaining = ordered_qty - total_filled
            # 🔴 cycle329 필수 동반 조항 — **매핑이 확정된 주문에만** 취소·재주문 타이머를 건다.
            # 이 시정으로 매핑 부재 창의 통보가 처음으로 **부분 분기에 도달**하는데,
            # `_cancel_and_reorder` 에는 포지션 재조회가 **한 줄도 없어**(실측) 30초 뒤
            # `place_order(quantity=remaining)` 를 그대로 발사한다. `qty_src="payload"` 는
            # 수동 매매(MTS/HTS) 주문도 포함하므로, 그대로 두면 **사람이 낸 주문을 우리가
            # 30초 뒤 취소하고 다시 낸다** — cycle327 이 봉한 「주문이 나간 뒤의 재발사」와
            # 같은 계열의 사고다. 우리 주문의 잔여는 ms 뒤 다음 통보가 `src=map` 으로 와서
            # 정상적으로 타이머를 건다(잃는 것이 없다).
            if qty_src == "map":
                self._schedule_cancel_and_reorder(ticker, order_no, remaining, is_stop_loss=True)
            else:
                logger.warning(
                    "[fill_partial_no_reorder] ticker=%s order_no=%s side=SELL src=%s "
                    "remaining=%d — 매핑 확정 전 통보라 재주문 보류",
                    t(ticker), order_no, qty_src, remaining,
                )
            logger.info("매도 부분 체결: %s %d/%d주 @ %d (전략: %s)", t(ticker), total_filled, ordered_qty, price, strategy_id)

    def _schedule_cancel(self, ticker: str, order_no: str, original_qty: int, strategy_id: str = "momentum") -> None:
        """30초 후 미체결 잔량을 취소하는 태스크를 등록한다."""
        # cycle332 — 키에 **매수 축**을 싣는다. 같은 축 재스케줄만 교체하고
        # 반대 축(매도 손절 잔여 재주문) 타이머는 다른 키라 건드리지 않는다.
        _key = (ticker, CANCEL_AXIS_BUY)
        if _key in self._pending_cancel_tasks:
            self._pending_cancel_tasks[_key].cancel()

        self._pending_cancel_tasks[_key] = asyncio.create_task(
            self._cancel_after_wait(ticker, order_no, strategy_id)
        )
        self._pending_cancel_order_no[_key] = order_no

    async def _cancel_after_wait(self, ticker: str, order_no: str, strategy_id: str) -> None:
        """`_schedule_cancel` 태스크 본체 — 30초 후 미체결 잔량 취소.

        cycle287 §S6e — 예전엔 `_schedule_cancel` 안의 nested closure 였다.
        `_apply_clock` 사용처 AST 가드가 이 메서드를 `OrderEngine` 의 실제
        메서드로 요구해 여기로 승격했다(행위 byte 동일, 자리만 옮겼다).
        """
        try:
            await asyncio.sleep(PARTIAL_FILL_WAIT)
            # 적대 검증 시정(HIGH) — 원주문이 실제로 나간 거래소를 우선
            # 쓴다(`_order_exchange`). 30초 대기 동안 시각 경계(예: 15:59:45
            # 주문 → 16:00:15 취소)를 넘으면 라우터를 다시 부르는 쪽은 원주문과
            # 다른 거래소를 낼 수 있다 — `cancel_order` 의 계약은 "원주문이
            # 접수된 거래소" 다(자문 §4-C2). 매핑이 없을 때만(레거시·매핑 유실)
            # 현행 라우터 재평가로 fail-open 한다.
            ex = self._order_exchange.get(order_no)
            if ex is None:
                ex = self._apply_clock(
                    self._strategy_exchange(strategy_id), strategy_id,
                    side="sell", ticker=ticker,
                )
            # cycle291 — Stage A 관측. `orig_dvsn`/`dvsn_src` 는 원주문이 실제로
            # 실었던 호가유형(매핑 부재 = fail-open `-`/`absent`)이고, `ord_dvsn`
            # 은 이 취소 요청이 **실제로 보낸** 값이다(Stage A 는 `order_division`
            # 을 전달하지 않으므로 언제나 `"00"` — 리터럴이 아니라 사실이다).
            _orig_div = self._order_division.get(order_no)
            _cancel_ok = False
            _cancel_err = ""
            try:
                await cancel_order(order_no, 0, cancel_all=True, exchange=ex)
                _cancel_ok = True
            except KisApiError as _cancel_exc:
                _cancel_err = f"[{_cancel_exc.msg_cd}] {_cancel_exc.msg1}"
                raise
            finally:
                # K11(자문 §4-C1) — 관측만. `ORD_DVSN="00"` 하드코딩은 변경 0.
                logger.info(
                    "[after_cancel_result] ticker=%s order_no=%s ord_dvsn=00 "
                    "orig_dvsn=%s dvsn_src=%s exchange=%s result=%s err=%s",
                    ticker, order_no, _orig_div if _orig_div else "-",
                    "map" if _orig_div else "absent",
                    ex, "ok" if _cancel_ok else "error", _cancel_err,
                )
            await update_trade_status(ticker, TradeType.BUY, TradeStatus.CANCELLED, strategy=strategy_id, order_no=order_no)
            logger.info("부분 체결 잔여 취소: %s (주문번호: %s)", t(ticker), order_no)
        except asyncio.CancelledError:
            pass  # 새 task로 교체됨 — pop은 새 task가 관리
        except Exception:
            logger.exception("부분 체결 잔여 취소 실패: %s", ticker)
        finally:
            # cancel-replace race 방어 — 본인이 dict에 있을 때만 pop
            _k = (ticker, CANCEL_AXIS_BUY)
            if self._pending_cancel_tasks.get(_k) is asyncio.current_task():
                self._pending_cancel_tasks.pop(_k, None)
                self._pending_cancel_order_no.pop(_k, None)

    def _schedule_cancel_and_reorder(
        self, ticker: str, order_no: str, remaining: int, *, is_stop_loss: bool
    ) -> None:
        """30초 후 미체결 잔량을 취소하고, 손절인 경우 잔여 재주문한다."""
        # cycle332 — 키에 **매도 축**을 싣는다. 매수 잔량 취소 타이머와 공존한다.
        _key = (ticker, CANCEL_AXIS_SELL)
        if _key in self._pending_cancel_tasks:
            self._pending_cancel_tasks[_key].cancel()

        self._pending_cancel_tasks[_key] = asyncio.create_task(
            self._cancel_and_reorder(ticker, order_no, remaining, is_stop_loss=is_stop_loss)
        )
        self._pending_cancel_order_no[_key] = order_no

    async def _cancel_and_reorder(
        self, ticker: str, order_no: str, remaining: int, *, is_stop_loss: bool
    ) -> None:
        """`_schedule_cancel_and_reorder` 태스크 본체.

        cycle287 §S6e — 예전엔 `_schedule_cancel_and_reorder` 안의 nested
        closure 였다(승격 사유는 `_cancel_after_wait` 와 동일).
        """
        try:
            await asyncio.sleep(PARTIAL_FILL_WAIT)
            strategy_id = self._order_strategy.get(order_no, "momentum")

            # cycle295 (B) — 쌍 게이트(§3-5③). 이 함수만 취소 3경로 중 유일하게
            # `sleep(30) → cancel_order → place_order` 의 atomic replace 다.
            # 절반만 막으면 "호가창의 손절을 우리가 빼고 아무것도 안 넣은" 상태가
            # 된다 — 컷이면 취소도 하지 않고 작동 중인 주문을 그대로 둔다(16:00
            # 이후 `cancel_remaining` 또는 `risk.on_tick` 재평가에 위임한다).
            if self._market_rest_gate(
                side="sell", ticker=ticker, strategy_id=strategy_id,
                base=(
                    self._order_exchange.get(order_no)
                    or self._strategy_exchange(strategy_id)
                ),
                now=datetime.now(_KST_TZ),
            ):
                return

            # 적대 검증 시정(HIGH) — `_cancel_after_wait` 와 동일 이유로 원주문의
            # 실제 거래소(`_order_exchange`)를 우선한다. 매핑이 없을 때만
            # 현행 라우터 재평가로 fail-open.
            ex = self._order_exchange.get(order_no)
            if ex is None:
                ex = self._apply_clock(
                    self._strategy_exchange(strategy_id), strategy_id,
                    side="sell", ticker=ticker,
                )
            # cycle291 — Stage A 관측(`_cancel_after_wait` 와 동일 규약).
            _orig_div = self._order_division.get(order_no)
            _cancel_ok = False
            _cancel_err = ""
            try:
                await cancel_order(order_no, 0, cancel_all=True, exchange=ex)
                _cancel_ok = True
            except KisApiError as _cancel_exc:
                _cancel_err = f"[{_cancel_exc.msg_cd}] {_cancel_exc.msg1}"
                raise
            finally:
                # K11(자문 §4-C1) — 관측만. `ORD_DVSN="00"` 하드코딩은 변경 0.
                logger.info(
                    "[after_cancel_result] ticker=%s order_no=%s ord_dvsn=00 "
                    "orig_dvsn=%s dvsn_src=%s exchange=%s result=%s err=%s",
                    ticker, order_no, _orig_div if _orig_div else "-",
                    "map" if _orig_div else "absent",
                    ex, "ok" if _cancel_ok else "error", _cancel_err,
                )
            await update_trade_status(ticker, TradeType.SELL, TradeStatus.CANCELLED, strategy=strategy_id, order_no=order_no)
            logger.info("매도 잔여 취소: %s %d주", t(ticker), remaining)

            if is_stop_loss and remaining > 0:
                # 손절 잔여분 재주문 — cycle287 §4-C3. 시장가(price=0)는
                # KRX 애프터마켓(16:00~20:00)에서 100% 거부되므로(§1-A "시장가
                # 없음") 그 창에서만 창 호가쌍으로 교체한다. 그 밖은 순수
                # 추가 계약(byte 동일 — 정규장·프리장 재주문은 그대로 시장가).
                reorder_division: OrderDivision | None = None
                reorder_price = 0
                try:
                    from src.config import settings
                    if ex == "KRX" and settings.is_production:
                        from src.engine.market_state import MarketPhase, get_market_state
                        _now_ro = datetime.now(_KST_TZ)
                        if get_market_state(_now_ro, market="KRX").phase is MarketPhase.AFTER_MARKET:
                            _ro_strategy = self.registry.get(strategy_id)
                            _ro_params = _ro_strategy.config.params if _ro_strategy else {}
                            _ro_dial = str(_ro_params.get(
                                "after_market_exit_division", _AFTER_EXIT_DIVISION_DEFAULT
                            ))
                            if _ro_dial not in _AFTER_EXIT_DIVISION_ALLOWED:
                                _ro_dial = _AFTER_EXIT_DIVISION_DEFAULT
                            if _ro_dial == "44":
                                reorder_division, reorder_price = OrderDivision.KRX_AFTER_BEST, 0
                            else:
                                from src.engine.scanner import ticker_prices as _tp_ro
                                _ro_cur = int(
                                    _tp_ro.get(ticker, {}).get("current_price", 0) or 0
                                )
                                if _ro_cur > 0:
                                    reorder_division = OrderDivision.KRX_AFTER_LIMIT
                                    reorder_price = step_down(_ro_cur, steps=5)
                except Exception:
                    reorder_division, reorder_price = None, 0
                    logger.debug(
                        "[after_exit_division] 잔여 재주문 판정 실패 — 시장가 유지: %s",
                        ticker, exc_info=True,
                    )

                place_kwargs = dict(
                    ticker=ticker, side=OrderSide.SELL, quantity=remaining,
                    price=reorder_price, exchange=ex,
                )
                if reorder_division is not None:
                    place_kwargs["order_division"] = reorder_division
                # cycle295 (D, §2-0b) — 나머지 4곳(매수 주 경로·매수 지정가 폴백·
                # 매도 주 경로·매도 폴백)과 같은 모양으로 결과를 받아 매핑을
                # 등록한다. 필요한 값은 전부 이미 스코프에 있다(`strategy_id`·
                # `ex`·`ticker`·`remaining`·`reorder_division`). 매핑이 없으면
                # 이 재주문의 체결통보가
                # `_order_strategy` miss → `trade_history` miss →
                # `"momentum"` 오귀속으로 흐르고, `_order_qty` 부재로 부분체결이
                # 전량체결로 읽힌다(§2-0b 실측).
                result = await place_order(**place_kwargs)
                if result is not None and getattr(result, "order_no", None):
                    self._order_qty[result.order_no] = remaining
                    self._order_strategy[result.order_no] = strategy_id
                    self._order_ticker[result.order_no] = ticker
                    self._order_exchange[result.order_no] = ex
                    if reorder_division is not None:
                        self._order_division[result.order_no] = reorder_division.value
                    self._completed_orders.discard(result.order_no)
                logger.info("손절 잔여 재주문: %s %d주", t(ticker), remaining)
        except asyncio.CancelledError:
            pass  # 새 task로 교체됨 — pop은 새 task가 관리
        except Exception:
            logger.exception("매도 잔여 취소/재주문 실패: %s", ticker)
        finally:
            # cancel-replace race 방어 — 본인이 dict에 있을 때만 pop
            _k = (ticker, CANCEL_AXIS_SELL)
            if self._pending_cancel_tasks.get(_k) is asyncio.current_task():
                self._pending_cancel_tasks.pop(_k, None)
                self._pending_cancel_order_no.pop(_k, None)

    def reset_daily_state(self) -> None:
        """일일 차단 게이트 상태 초기화 (scheduler `_reset_daily_state` 가 위임 호출).

        사이클 B-1 (2026-06-01): 장운영시간 외 거부 TTL dict + emit cap set 를 매일 정산 후 clear.
        사이클 54 (2026-06-03): NXT 다운그레이드 로그 cap set 동행 clear.
        사이클 55 R-1 (2026-06-03): _market_closed_blocked* 2 필드 직접 clear →
            self._sell_rejection.reset_daily() 4 필드 일괄 위임 (사이클 48 stale_tracker 패턴).
        P1-B (2026-07-29): `_completed_buy_orders` 동행 clear (무한 성장 금지, 매핑 dict 4종과
            동일 일일 정리 주기 — order_no 는 하루 단위로만 유일성 보장).
        """
        self._sell_rejection.reset_daily()  # 4 필드 (_blocked_until / _blocked_reason / _logged_today / _history) 일괄 clear
        self._nxt_downgrade_logged_today.clear()  # 사이클 54 유지 (사이클 56-C 통합 완료)
        self._completed_buy_orders.clear()  # P1-B (B-1) 멱등 마커 일일 정리
        self._order_channel_logged.clear()  # cycle287 규칙 1 관측 cap 일일 정리
        self._fill_qty_src_logged.reset_daily()  # cycle329 주문수량 출처 cap
        self._ordered_qty_mismatch_logged.reset_daily()
        self._fill_qty_src_count.clear()
        self._order_channel_config_logged.clear()
        self._after_exit_fails.clear()  # cycle287 K9 봉인2 일일 정리
        self._order_exchange.clear()  # cycle287 적대 검증 시정 — order_no 는 하루 단위로만 유일
        self._order_division.clear()  # cycle291 — 선례와 같은 정리 주기
        self._pre_nxt_division_config_logged.clear()  # cycle291 B5 카나리아 일일 정리

    async def cancel_remaining(self, ticker: str, strategy_id: str) -> None:
        """미체결 잔량을 취소한다."""
        strategy = self.registry.get(strategy_id)
        if not strategy:
            return
        pos = strategy.state.positions.get(ticker)
        if not pos:
            return
        try:
            # 적대 검증 시정(HIGH) — 원주문 거래소 우선(`_order_exchange`), 매핑
            # 없을 때만 라우터 재평가로 fail-open(`_cancel_after_wait` 동일 이유).
            ex = self._order_exchange.get(pos.order_no)
            if ex is None:
                ex = self._apply_clock(
                    self._strategy_exchange(strategy_id), strategy_id,
                    side="sell", ticker=ticker,
                )
            # cycle291 — Stage A 관측(`_cancel_after_wait` 와 동일 규약).
            _orig_div = self._order_division.get(pos.order_no)
            _cancel_ok = False
            _cancel_err = ""
            try:
                await cancel_order(pos.order_no, pos.quantity, cancel_all=True, exchange=ex)
                _cancel_ok = True
            except KisApiError as _cancel_exc:
                _cancel_err = f"[{_cancel_exc.msg_cd}] {_cancel_exc.msg1}"
                raise
            finally:
                # K11(자문 §4-C1) — 관측만.
                logger.info(
                    "[after_cancel_result] ticker=%s order_no=%s ord_dvsn=00 "
                    "orig_dvsn=%s dvsn_src=%s exchange=%s result=%s err=%s",
                    ticker, pos.order_no, _orig_div if _orig_div else "-",
                    "map" if _orig_div else "absent",
                    ex, "ok" if _cancel_ok else "error", _cancel_err,
                )
            logger.info("미체결 취소: %s (주문번호: %s)", t(ticker), pos.order_no)
        except Exception:
            logger.exception("미체결 취소 실패: %s", ticker)
