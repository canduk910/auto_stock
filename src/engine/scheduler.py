"""매매 스케줄러 — KRX/NXT 통합 운영(08:00~20:00).

- 07:45 자동 시작 / 07:50 부팅 / 07:55 사전 구독
- 08:00 NXT 프리 진입 → 익일 청산 + VB/LTV PRE_NXT 매매 시작 (Q2=B)
- 09:00:05 KRX 메인 시가 확정 → VB/LTV MAIN 보드 매매 (Q1=C 보드별 분리)
- 09:30 모멘텀 스캔
- 15:20 KRX 메인 신규 매수 중단 + KRX 메인 종목 강제 청산 (POST_NXT 활성 종목은 유지)
- 15:30 KRX 메인 마감 → NXT 애프터 진입
- 19:50 NXT 애프터 신규 매수 중단 + 16:00 AI자문 → 19:50으로 이동
- 20:00 NXT 애프터 종료, unsubscribe
- 20:10 정산: daily_performance 기록, 일일 로그 분석
"""

from __future__ import annotations

import asyncio
import logging
import time as _time_mod
from datetime import date, datetime, time, timedelta

from src.api.balance import get_balance, get_daily_orders
from src.api.condition import fetch_stock_detail
from src.auth.token import token_manager
from src.db.daily_performance import get_latest_performance, recompute_from_trades, upsert_daily_performance
from src.db.system_config import get_cash_usage_ratio
from src.db.system_logs import write_log
from src.engine.order_engine import OrderEngine
from src.engine.risk import RiskManager
from src.engine.scanner import scan_stocks, subscribe_filtered_stocks, unsubscribe_all
from src.engine.session import MarketBoard, session_tracker
from src.engine.daily_emit_cap import DailyEmitCap
from src.engine.strategy_base import Signal, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.realtime.handler import (
    dispatch_message,
    flush_silent_drop_count,
    register_board_handler,
    register_execution_handler,
    register_tick_handler,
)
from src.realtime.websocket import kis_ws
from src.realtime.websocket_pool import kis_ws_pool

logger = logging.getLogger(__name__)

# 시간 상수 — NXT 통합 운영 (08:00~20:00)
TIME_AUTO_START = time(7, 45)
TIME_BOOT = time(7, 55)          # 사이클 92 (2026-06-10) — KIS 07:50 강제 중단 후 5분 마진 (Q28=E)
TIME_PRESUBSCRIBE = time(7, 59)  # 사이클 92 (2026-06-10) — _boot 완료 후 4분 마진, race 회피 (Q32=B)
TIME_PRE_NXT_OPEN = time(8, 0)             # NXT 프리 진입 (익일 청산)
TIME_KRX_OPEN_CONFIRM = time(9, 0, 5)      # KRX 메인 시가 확정 → VB/LTV MAIN 매매
# 사이클 26 (2026-05-20): 보드 전환 사전 구독 마진 — 50초 선행
TIME_KRX_MAIN_OPEN_PRESUBSCRIBE = time(8, 59, 10)   # KRX 채널 사전 subscribe 시작
TIME_POST_NXT_OPEN_PRESUBSCRIBE = time(15, 39, 10)  # NXT 채널 사전 subscribe 시작
TIME_POST_NXT_OPEN = time(15, 40)          # NXT 애프터 진입 (사이클 26: 15:30 → 15:40)
TIME_SCAN_START = time(9, 30)              # 모멘텀 스캔
TIME_KRX_MAIN_BUY_STOP = time(15, 20)      # KRX 메인 신규 매수 중단 + 강제 청산
TIME_KRX_MAIN_CLOSE = time(15, 30)         # KRX 메인 마감 (종가 흡수 마진 시작, _force_clear_main_only 가드 기준)
TIME_STOCK_MASTER_DAILY_LOAD = time(16, 0) # 사이클 122 — KIS 일봉 일괄 적재 (KRX 메인 종료 30분 후 안전 마진)
TIME_STOCK_MASTER_BASICS_REFRESH = time(16, 10)  # 사이클 126 — KIS CTPF1002R 매스 보강 (일봉 task 직후 10분 마진)
TIME_STOCK_MASTER_MASTER_LOAD = time(16, 30)  # 사이클 129 — KIS 종목 마스터 파일 (kospi_code.mst / kosdaq_code.mst) 일괄 적재 (basics task 직후 20분 마진, domain-consult 의제 5 옵션 A)
TIME_STOCK_MASTER_DAILY_PURGE = time(16, 15)  # 사이클 150 — stock_master_daily T-150일 retention cron (일봉 task 16:00 적재 직후 15분 마진)
TIME_EVENING_FUNNEL_CAPTURE = time(16, 20)  # 사이클 171 — 저녁 잠정 funnel 캡처 (16:00 일봉 → 16:10 basics 직후, 16:30 마스터 직전. 운영자 밤 후보 확인. domain-consult 의제 4 우선순위 2)
TIME_NXT_POST_BUY_STOP = time(19, 50)      # NXT 애프터 신규 매수 중단 (안전 마감, 변경 금지)
TIME_RECOMMENDATION = time(20, 0)          # AI자문 (Phase 0, 2026-05-15: 19:50 → 20:00 이동 — 백테스트 검증 정합성)
TIME_FULL_UNIVERSE_LOAD = time(20, 0, 5)   # 사이클 101 — 전체 유니버스 적재 (AI자문 직후 5초 마진)
TIME_NXT_POST_CLOSE = time(20, 0)          # NXT 애프터 종료, unsubscribe (자문과 동시 발화, 백그라운드 task 분리)
TIME_SETTLEMENT = time(20, 10)             # 정산 + 일일 로그 분석
SCAN_INTERVAL = 300                         # 5분마다 스캔
SESSION_TICK_INTERVAL = 30                  # 보드 전환 감시 주기 (초)
NEXT_DAY_STABILIZE_SECS = 30                # 익일 청산 시가 안정화 (Q2=B 단축)

# K (2026-05-12) — WebSocket 시세 silent inactive 자동 복구 stale_watcher
# F1(재연결 1회) + `_scan_loop`(5분) 으로 못 잡는 silent inactive 즉시 회복.
# 11:48 fresh=1/stale=26 운영 사고(2026-05-12) 대응.
#
# 사이클 9 (2026-05-18) — KIS 차단 회피 안전망
# KIS Open API 공지: 무한 연결/종료, 검증 없는 무한 등록/해제 반복 → IP/앱키
# 일시 차단. K stale watcher × 보조 세션 5개 트래픽 1.5배 수준 회복.
# - 30s → 120s (분당 발화 1/4)
# - 3 → 10 (10회 × 120s = 20분 stale 누적 후 강제 재등록 — 단발 끊김 즉시 unsub/sub 차단)
# - FRESHNESS 60 보존 (5/12 운영 사고 대응 의도 그대로)
STALE_WATCHER_INTERVAL_SECS = 120           # task 발화 주기 (사이클 9: 30 → 120)
# STALE_FRESHNESS_SECS: 사이클 61 Phase 2-A2 (2026-06-05) stale_manager.py 로 이전 후 아래 re-export 에서 import.
# 사이클 17 보강 (2026-05-19) — KIS 공식 답변 반영 ("기 요청된 목록 관리하여 기등록한 사항을 재등록하지 않도록").
# 1~5회 재SEND (`pool.resend_subscribe_for_ticker`) 분기 폐기 → 첫 stale 즉시 unsubscribe + subscribe(HIGH,
# bypass_limit=True) 강제 재등록. KIS 정상 "신규 등록" 패턴 (재SEND 0건). 5/12 silent inactive 사고
# 안전망 보존. retry > MAX 면 skip — 다음 _scan_loop 위임 (영구 stale 의심 종목 보호).
STALE_FORCE_REREGISTER_AFTER = 5            # (deprecated, 호환 보존) — 분기 임계가 아닌 회귀 가드 의미만 유지. 실제 동작은 MAX_STALE_RETRIES.

# 사이클 60 Phase 2-A1 (2026-06-04) — 5 상수를 stale_manager.py 로 이전 후 re-export.
# 사이클 61 Phase 2-A2 (2026-06-05) — 추가 5 상수 (SILENT_INACTIVE_* + STALE_FRESHNESS_SECS) re-export 추가.
# 외부 `from src.engine.scheduler import MAX_STALE_RETRIES` 호환 보존 (`is` 동일성).
from src.engine.stale_manager import (  # noqa: E402
    MAX_STALE_RETRIES,
    STALE_FORCE_RETRY_AFTER_SECS,
    STALE_FORCE_RETRY_HOURLY_CAP,
    UNIVERSE_LOW_VOLUME_THRESHOLD,
    SILENT_INACTIVE_FRESH_RATIO_THRESHOLD,
    STALE_FRESHNESS_SECS,               # 사이클 61 A2 신규 re-export (G1)
    SILENT_INACTIVE_MIN_SUBSCRIBED,     # 사이클 61 A2 신규 re-export (G2)
    SILENT_INACTIVE_PERSIST_SECS,       # 사이클 61 A2 신규 re-export (G2)
    SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR,   # 사이클 61 A2 신규 re-export (G2)
    SILENT_INACTIVE_RECOVERY_WINDOW_SECS,    # 사이클 61 A2 신규 re-export (G2)
)

# 사이클 24 (2026-05-20) — 세션 단위 silent inactive 감지 + 강제 reconnect
# K stale watcher 가 종목별 재등록 외에 세션 자체 결함도 5분 지속 후 _ws.close() 발화.
# 3중 가드: fresh=0 + subscribed>=5 (위양성 차단) + 5분 지속 (단발 끊김 즉시 close 차단)
# 시간당 2회 cap — KIS LMS / 앱정보 이용중지 위험 사전 차단.
# 2026-05-20 14:58 운영 결함: 메인 세션 sub=11 ack=11 fresh=0 stale=11 대응.
# SILENT_INACTIVE_MIN_SUBSCRIBED / PERSIST_SECS / CAP_PER_HOUR / WINDOW_SECS:
#   사이클 61 A2 에서 stale_manager.py 로 이전 후 위 re-export 에서 import.
# STALE_FRESHNESS_SECS: 사이클 61 A2 에서 stale_manager.py 로 이전 후 위 re-export 에서 import.

# B (2026-05-15) — donchian_swing 일중 시세 REST 폴링 보강
# WS stale 시에도 보유 종목의 ATR×2 트레일링/하드 -7% 손절 평가가 끊기지 않도록
# 09:30~15:20 KRX 메인 시간대 60s 주기 REST 폴링. WS 정상이면 멱등 갱신, stale 이면 메꿈.
SWING_REST_POLL_INTERVAL_SECS = 60          # 폴링 사이클 주기
SWING_REST_POLL_TICKER_SLEEP_SECS = 0.05    # 종목 사이 Rate Limit 보호 (KIS 20req/s 대비 안전)
SWING_REST_POLL_WINDOW_START = time(9, 30)  # 09:30 (모멘텀 스캔 시작 시각과 동일)
SWING_REST_POLL_WINDOW_END = time(15, 20)   # 15:20 (KRX 메인 매수 중단 시각과 동일)

# Backwards-compat aliases — 기존 코드 참조 호환
TIME_NEXT_DAY_CLEAR = TIME_PRE_NXT_OPEN
TIME_VB_OPEN_CONFIRM = TIME_KRX_OPEN_CONFIRM
TIME_BUY_STOP = TIME_KRX_MAIN_BUY_STOP
TIME_MARKET_CLOSE = TIME_KRX_MAIN_CLOSE


# ── 사이클 74 옵션 C — [swing_rest_poll] 5분 aggregation collector ─────────────────
_swing_rest_poll_collector: list[dict] = []


def record_swing_rest_poll(stats: dict) -> None:
    """5분 윈도우 누적 (사이클 74 옵션 C aggregation).

    stats keys: candidates / held / pending / updated / failed / elapsed_ms
    5분 윈도우 내 ~5 회 poll 을 1 행으로 합산 (80% 감소).
    """
    _swing_rest_poll_collector.append(stats)


def flush_swing_rest_poll_collector() -> None:
    """5분 윈도우 종료 시 `[swing_rest_poll_summary]` 1행 emit + collector 초기화.

    scheduler shutdown / _swing_rest_poll_loop cancel 직전 마지막 flush 1회 호출 의무
    (Q5 옵션 A — 잔여 카운터 손실 방지, 정산 *직전* 데이터 보존).
    collector 비어 있으면 emit skip (no-op).
    """
    if not _swing_rest_poll_collector:
        return
    polls = len(_swing_rest_poll_collector)
    candidates_avg = sum(s["candidates"] for s in _swing_rest_poll_collector) / polls
    candidates_max = max(s["candidates"] for s in _swing_rest_poll_collector)
    total_held = _swing_rest_poll_collector[-1]["held"]
    elapsed_ms_avg = sum(s["elapsed_ms"] for s in _swing_rest_poll_collector) / polls
    logger.info(
        "[swing_rest_poll_summary] polls=%d candidates_avg=%.1f max=%d total_held=%d elapsed_ms_avg=%.1f",
        polls, candidates_avg, candidates_max, total_held, elapsed_ms_avg,
    )
    _swing_rest_poll_collector.clear()


async def capture_funnel_snapshots(registry, *, is_provisional: bool = False) -> int:
    """사이클 171 — funnel snapshot 단계별 캡처 공통 헬퍼 (3 호출처 공유).

    `_auto_capture_funnel_snapshots` (09:30 자동) 의 "registry 순회 → 각 strategy
    `_funnel_steps` 단계별 + step_no=99 insert_snapshot" 로직을 추출. 3 호출처 공유:
    - (a) 09:30 자동 (`_auto_capture_funnel_snapshots` 위임, is_provisional=False)
    - (b) 16:20 저녁 (`_evening_funnel_capture_once`, is_provisional=True)
    - (c) 수동 trigger (`routes/strategy_funnel.py::trigger_snapshot`, is_provisional=False)

    흐름 (사이클 39 인프라 + 사이클 170 in-place upsert 영속):
    1. `registry.all()` 순회 — `_funnel_steps` 가 있는 전략만
    2. 각 전략 단계별 (`step_no=1..N`) row + 최종 (`step_no=99`) row insert_snapshot
    3. 한 전략 처리 중 예외 → 다른 전략 계속 (graceful, 사이클 88 답습)
    4. `_funnel_steps` 빈 리스트 → 단계 row 0건 + 최종 row 만 (사이클 132 momentum 영구 제외)

    Args:
        registry: StrategyRegistry — `all()` 순회.
        is_provisional: 잠정(True) / 확정(False, 기본) — insert_snapshot 전파.

    Returns:
        저장된 row 수 (saved_count).

    안전 가드 (관찰성 한정 — 매매 hot path diff 0):
    - 본체 예외 graceful (호출자 try/except 흡수)
    - DB JSONB cap 200/20 (사이클 34 strategy_funnel.py 자동 적용)
    - check_exit_signal / check_buy_signal funnel hook 0건 (사이클 143/170 SAFETY 영속)
    """
    from datetime import datetime as _dt
    from src.db.strategy_funnel import insert_snapshot
    from src.engine.scanner import KST_TZ as _KST_TZ

    today_kst = _dt.now(_KST_TZ).date()
    saved_count = 0

    try:
        strategies = registry.all()
    except Exception:
        logger.exception("[funnel_snapshot] registry 접근 실패")
        return 0

    for strategy in strategies:
        sid = getattr(strategy, "strategy_id", "")
        if not sid:
            continue
        try:
            funnel_steps = getattr(strategy, "_funnel_steps", []) or []
        except Exception:
            logger.exception("[funnel_snapshot] %s _funnel_steps 접근 실패", sid)
            continue

        # 단계별 row — 사이클 41 step_conditions 전달 + 사이클 171 is_provisional
        for step in funnel_steps:
            try:
                row = await insert_snapshot(
                    target_date=today_kst,
                    strategy_id=sid,
                    step_no=int(step.get("step_no", 0)),
                    step_name=str(step.get("step_name", "")),
                    survived_tickers=list(step.get("survived", []) or []),
                    excluded_sample=list(step.get("excluded", []) or []),
                    survived_count=int(step.get("survived_count", 0)),
                    excluded_count=int(step.get("excluded_count", 0)),
                    step_conditions=step.get("step_conditions"),  # 사이클 41
                    is_provisional=is_provisional,  # 사이클 171
                )
                if row:
                    saved_count += 1
            except Exception:
                logger.exception(
                    "[funnel_snapshot] %s step_no=%s INSERT 실패",
                    sid, step.get("step_no"),
                )
                continue

        # 최종 단계 (step_no=99) row — 사이클 34 호환 (수동 trigger 형식 유지)
        try:
            get_scanned = getattr(strategy, "get_scanned_tickers", None)
            scanned = list(get_scanned()) if callable(get_scanned) else []
            row = await insert_snapshot(
                target_date=today_kst,
                strategy_id=sid,
                step_no=99,
                step_name="최종 prepared (auto)",
                survived_tickers=scanned,
                survived_count=len(scanned),
                excluded_count=0,
                excluded_sample=[],
                is_provisional=is_provisional,  # 사이클 171
            )
            if row:
                saved_count += 1
        except Exception:
            logger.exception("[funnel_snapshot] %s 최종 단계 INSERT 실패", sid)

    logger.info(
        "[funnel_snapshot] 캡처 완료 — target_date=%s saved=%d provisional=%s",
        today_kst.isoformat(), saved_count, is_provisional,
    )
    # 사이클 72 hotfix: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT
    return saved_count


class TradingScheduler:
    """매매 스케줄러."""

    def __init__(self) -> None:
        # 전략 레지스트리 생성 + 전략 등록 (기본값, DB 로드 전)
        self.registry = StrategyRegistry()
        momentum = MomentumStrategy(StrategyConfig(
            strategy_id="momentum",
            name="상한가 모멘텀",
            enabled=True,
            weight=1.0,
        ))
        self.registry.register(momentum)

        vb = VolatilityBreakoutStrategy(StrategyConfig(
            strategy_id="volatility_breakout",
            name="변동성 돌파",
            enabled=False,
            weight=0.0,
        ))
        self.registry.register(vb)

        ltv = LongTailVolatilityStrategy(StrategyConfig(
            strategy_id="long_tail_volatility",
            name="롱테일 변동성 돌파",
            enabled=False,
            weight=0.0,
        ))
        self.registry.register(ltv)

        ds = DonchianSwingStrategy(StrategyConfig(
            strategy_id="donchian_swing",
            name="20일 신고가 스윙",
            enabled=False,
            weight=0.0,
        ))
        self.registry.register(ds)

        bull = BullFlagBreakoutStrategy(StrategyConfig(
            strategy_id="bull_flag_breakout",
            name="눌림목 돌파",
            enabled=False,
            weight=0.0,
        ))
        self.registry.register(bull)

        vcp = VcpBreakoutStrategy(StrategyConfig(
            strategy_id="vcp_breakout",
            name="변동성 수축 돌파",
            enabled=False,
            weight=0.0,
        ))
        self.registry.register(vcp)

        self.order_engine = OrderEngine(self.registry)
        # 사이클 15-A (2026-05-19) — _handle_sell_fill 의 unsubscribe hook 이
        # `_pending_next_day_clear` 조회할 수 있도록 provider 주입.
        self.order_engine._pending_next_day_clear_provider = (
            lambda: self._pending_next_day_clear
        )
        self.risk_manager = RiskManager(self.registry, self.order_engine)
        self._running = False
        self._phase: str = "idle"
        self._config_loaded = False
        # 익일 청산 백그라운드 task 추적 (좀비 task 방지 — start() finally에서 cancel)
        self._next_day_task: asyncio.Task | None = None
        # 보드 전환 감시 background task
        self._session_task: asyncio.Task | None = None
        # P1(B): NXT 시가 미수신으로 08:00 청산이 보류된 (ticker, strategy_id) 집합.
        # `_confirm_breakout_open_prices(board="main")` 직후 `_drain_pending_next_day_clear`
        # 에서 시장가로 정리한다.
        self._pending_next_day_clear: set[tuple[str, str]] = set()
        # K (2026-05-12) — WebSocket silent inactive 자동 복구 watcher task + 종목별 연속 stale 카운터
        self._stale_watcher_task: asyncio.Task | None = None
        # 사이클 46 (2026-05-22, refactor-review 카드 #6) — 세션 헬스 통합 5분 주기 task.
        # 사이클 42 KisWebSocket._heartbeat_metrics_loop 세션별 분산 task → 통합. 메인+보조 일관성.
        self._session_health_task: asyncio.Task | None = None
        # 사이클 48 (2026-05-22, refactor-review 카드 #2) — Stale 추적 7 필드 통합.
        # 사이클 17/24/28/29-R1/32/37/45 누적된 7 dict/set 필드 → 단일 데이터클래스.
        # 호환 layer (7 property, 본 클래스 메서드 정의 영역) 가 기존 `self._stale_*` 직접 접근
        # 패턴 모두 보존. `_reset_daily_state` 동행 clear 의무 → `_stale_state.reset_daily()` 위임.
        # 사이클 45 TTL evict 정책 보존 (`last_ccnl_cache` 5분 + `force_retry_history` 60분).
        from src.engine.stale_tracker import StaleTrackerState
        self._stale_state = StaleTrackerState()
        # 사이클 39 (2026-05-22) — 09:30 자동 funnel snapshot 일일 1회 가드.
        # `_scan_loop` 첫 진입 시 활성 전략의 `_funnel_steps` 를 DB strategy_funnel_snapshots 에
        # 단계별 row 로 INSERT. `_reset_daily_state` 동행 reset (매일 1회).
        self._auto_funnel_snapshot_done_today: bool = False
        # 사이클 189 (2026-07-02) — reprepare WARNING 로그 DailyEmitCap (1회/전략/일)
        # 사이클 31 R6 / 158 momentum 패턴 답습. 행위(prepare 재시도)는 cap 밖.
        self._reprepare_empty_logged_today: DailyEmitCap[str] = DailyEmitCap()
        # 사이클 18 (2026-05-19, A-1) — 5xx WARNING dedupe summary 60s 주기 task
        self._5xx_dedupe_summary_task: asyncio.Task | None = None
        # G안 (2026-05-12) — donchian_swing Pull 폴링 매수 평가 task (09:05~09:30)
        self._swing_poll_task: asyncio.Task | None = None
        # 사이클 13-E-2 — start() 본문 로컬 task 를 속성 승격, finally 좀비 차단
        self._ws_task: asyncio.Task | None = None
        self._scan_task: asyncio.Task | None = None

    async def _load_strategy_config(self) -> None:
        """DB에서 전략 설정(비중/파라미터)을 로드하여 적용한다."""
        if self._config_loaded:
            return
        try:
            from src.db.strategy_config import load_all
            configs = await load_all()
            if not configs:
                logger.info("DB 전략 설정 없음, 기본값 사용")
                self._config_loaded = True
                return

            for sid, cfg in configs.items():
                strategy = self.registry.get(sid)
                if not strategy:
                    continue
                strategy.config.enabled = cfg["enabled"]
                strategy.config.weight = cfg["weight"]
                if cfg["params"]:
                    for key, val in cfg["params"].items():
                        if key in strategy.config.params:
                            strategy.config.params[key] = val
                logger.info("DB 전략 설정 로드: %s (enabled=%s, weight=%.0f%%)",
                            sid, cfg["enabled"], cfg["weight"] * 100)
            self._config_loaded = True
        except Exception:
            logger.warning("전략 설정 DB 로드 실패, 기본값 사용")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _is_auto_start_enabled(self) -> bool:
        """DB system_config에서 auto_start 설정을 조회한다."""
        try:
            from src.db.supabase import supabase
            result = supabase.table("system_config").select("value").eq("key", "auto_start").execute()
            raw = result.data[0]["value"] if result.data else False
            return raw is True or raw == "true"
        except Exception:
            from src.config import settings
            return settings.auto_start

    # ------------------------------------------------------------------
    # 사이클 48 (2026-05-22, refactor-review 카드 #2) — Stale 추적 호환 layer.
    # 사이클 17/24/28/29-R1/32/37/45 누적 7 필드 → `StaleTrackerState` 통합.
    # 본 7 property (getter + setter) 가 기존 `self._stale_*` 직접 접근/할당 패턴 모두 호환 보존.
    # - getter: dict 인스턴스 동일성 보장 (매번 동일 객체 반환 — race 차단)
    # - setter: 외부 코드 (test 등) 의 `__new__ + sched._stale_retry_count = {}` 패턴 지원
    # _stale_state 미설정 인스턴스 보호 — setter 진입 시 자동 init (graceful)
    # ------------------------------------------------------------------
    def _ensure_stale_state(self) -> None:
        """`_stale_state` 미설정 시 자동 init (graceful — `__new__` 인스턴스 보호)."""
        if not hasattr(self, "_stale_state"):
            from src.engine.stale_tracker import StaleTrackerState
            object.__setattr__(self, "_stale_state", StaleTrackerState())

    @property
    def _stale_retry_count(self) -> dict[str, int]:
        self._ensure_stale_state()
        return self._stale_state.retry_count

    @_stale_retry_count.setter
    def _stale_retry_count(self, value: dict[str, int]) -> None:
        self._ensure_stale_state()
        self._stale_state.retry_count = value

    @property
    def _stale_last_resubscribe_at(self) -> dict[str, datetime]:
        self._ensure_stale_state()
        return self._stale_state.last_resubscribe_at

    @_stale_last_resubscribe_at.setter
    def _stale_last_resubscribe_at(self, value: dict[str, datetime]) -> None:
        self._ensure_stale_state()
        self._stale_state.last_resubscribe_at = value

    @property
    def _stale_force_retry_history(self) -> dict[str, list[datetime]]:
        self._ensure_stale_state()
        return self._stale_state.force_retry_history

    @_stale_force_retry_history.setter
    def _stale_force_retry_history(self, value: dict[str, list[datetime]]) -> None:
        self._ensure_stale_state()
        self._stale_state.force_retry_history = value

    @property
    def _silent_inactive_first_seen(self) -> dict[str, datetime]:
        self._ensure_stale_state()
        return self._stale_state.silent_inactive_first_seen

    @_silent_inactive_first_seen.setter
    def _silent_inactive_first_seen(self, value: dict[str, datetime]) -> None:
        self._ensure_stale_state()
        self._stale_state.silent_inactive_first_seen = value

    @property
    def _silent_inactive_recovery_count(self) -> dict[str, list[float]]:
        self._ensure_stale_state()
        return self._stale_state.silent_inactive_recovery_count

    @_silent_inactive_recovery_count.setter
    def _silent_inactive_recovery_count(self, value: dict[str, list[float]]) -> None:
        self._ensure_stale_state()
        self._stale_state.silent_inactive_recovery_count = value

    @property
    def _universe_excluded_today(self) -> set[str]:
        self._ensure_stale_state()
        return self._stale_state.universe_excluded_today

    @_universe_excluded_today.setter
    def _universe_excluded_today(self, value: set[str]) -> None:
        self._ensure_stale_state()
        self._stale_state.universe_excluded_today = value

    @property
    def _last_ccnl_cache(self) -> dict[str, dict]:
        self._ensure_stale_state()
        return self._stale_state.last_ccnl_cache

    @_last_ccnl_cache.setter
    def _last_ccnl_cache(self, value: dict[str, dict]) -> None:
        self._ensure_stale_state()
        self._stale_state.last_ccnl_cache = value

    async def start(self) -> None:
        """매매 프로세스를 시작한다 — KRX/NXT 통합 운영(08:00~20:00).

        현재 시각에 따라 적절한 단계부터 시작한다:
        - 07:50 이전: 07:50까지 대기 후 전체 스케줄 실행
        - 07:50~15:20: 즉시 부팅 + 현재 시각 이후 스케줄부터 실행
        - 15:20~20:10: NXT 애프터 단계, 신규 매수는 보드별 정책에 따름
        - 20:10 이후: 장 종료, 시작 불가
        """
        if self._running:
            logger.warning("이미 실행 중")
            return

        now = datetime.now().time()

        if now >= TIME_SETTLEMENT:
            logger.warning("장 종료 후에는 시작할 수 없습니다 (현재 %s, 정산 %s)",
                           now.strftime("%H:%M"), TIME_SETTLEMENT.strftime("%H:%M"))
            await write_log("WARNING", "장 종료 후 시작 시도 — 거부됨")
            return

        self._running = True
        self._phase = "booting"
        await write_log("INFO", f"매매 시스템 시작 (현재 {now.strftime('%H:%M:%S')})")

        try:
            await self._boot()
            register_tick_handler(self.risk_manager.on_tick)
            register_execution_handler(self.order_engine.handle_execution_notice)
            register_board_handler(session_tracker.on_h0nxmko0)

            # WebSocket 연결 (별도 태스크)
            self._ws_task = asyncio.create_task(
                kis_ws.connect(dispatch_message)
            )

            # 사이클 7-C — 보조 시세 세션 풀 시작 (graceful: 보조 0개면 noop)
            # 메인 connect 직후 호출 — 보조 세션은 각자 별도 task 에서 connect.
            # 보조 토큰 매니저 발급/connect 실패는 해당 세션만 skip (메인 흐름 영향 0)
            try:
                from src.realtime.websocket_pool import kis_ws_pool
                await kis_ws_pool.start(dispatch_message=dispatch_message)
            except Exception:
                logger.warning("[pool_start] 풀 시작 실패 — 메인 only 동작", exc_info=True)

            # 체결통보 구독 (실전: H0STCNI0 + HTS ID, 모의: H0STCNI9 + 계좌번호)
            await asyncio.sleep(2)  # WebSocket 연결 대기
            from src.config import settings as _cfg
            if _cfg.is_production:
                cni_tr_id = "H0STCNI0"
                cni_tr_key = _cfg.kis_hts_id
                if not cni_tr_key:
                    logger.error("실전 체결통보 구독에 KIS_HTS_ID가 필요합니다. .env에 KIS_HTS_ID_REAL을 설정하세요.")
                    raise RuntimeError("KIS_HTS_ID_REAL 미설정")
            else:
                cni_tr_id = "H0STCNI9"
                cni_tr_key = _cfg.kis_account_no
            await kis_ws.subscribe(cni_tr_id, cni_tr_key)
            logger.info("체결통보 구독: %s / %s", cni_tr_id, cni_tr_key)

            # 통합 장운영정보(H0UNMKO0) 구독 — 종목 단위 구독이지만 보드 전환 코드(MKOP_CLS_CODE)는
            # 시장 전체 공통이므로 대표 종목 1개만 구독해 전체 보드 전환을 실시간 수신
            # 모의(VTS) 미지원 — 실전 한정. 실패 시 시각 기반 SessionTracker fallback으로 동작
            if _cfg.is_production:
                try:
                    await kis_ws.subscribe("H0UNMKO0", "005930")  # 삼성전자 — KOSPI 대표 종목
                    logger.info("통합 장운영정보 구독: H0UNMKO0 / 005930")
                except Exception:
                    logger.warning("통합 장운영정보 구독 실패 — 시각 기반 보드 매핑으로 동작")

            # 세션 트래커 background task — 1분 주기 보드 전환 감시
            self._session_task = asyncio.create_task(self._session_loop())

            # K (2026-05-12) — WebSocket silent inactive 30s 자동 복구 watcher
            # F1(재연결 1회) + `_scan_loop`(5분) + K(30s) 3중 안전망. lifecycle: finally cancel
            self._stale_watcher_task = asyncio.create_task(self._stale_watcher_loop())

            # 사이클 46 (2026-05-22, refactor-review 카드 #6) — 세션 헬스 통합 5분 주기 task.
            # 사이클 42 KisWebSocket._heartbeat_metrics_loop 세션별 분산 task → scheduler 통합.
            # 메인 + 보조 일관성 + 좀비 task 방지. _stale_watcher_loop(120s) 와 별도 보존.
            self._session_health_task = asyncio.create_task(self._session_health_loop())

            # G안 (2026-05-12) — donchian_swing Pull 폴링 매수 평가 task (09:05~09:30)
            # WebSocket tick 흐름에서 매수 평가가 빠진 자리를 1분 주기 REST 폴링으로 채운다.
            # 보유 종목 청산(ATR 트레일링/-7%)은 risk.on_tick 의 check_exit_signal 그대로 사용.
            self._swing_poll_task = asyncio.create_task(self._swing_buy_poll_loop())

            # B (2026-05-15) — donchian_swing 일중 시세 REST 폴링 보강 task (09:30~15:20)
            # WS stale 시에도 보유 종목의 ATR/-7% 손절 평가가 끊기지 않도록 60s 주기 REST 폴링.
            # `_swing_buy_poll_loop` 는 매수 평가 전용 (09:05~09:30) 으로 보존, 본 task 는
            # 시세 갱신 + 보유 평가만 책임. 별도 청산 경로 신설 금지 — risk.on_tick 재사용.
            self._swing_rest_poll_task = asyncio.create_task(self._swing_rest_poll_loop())

            # 사이클 18 (2026-05-19, A-1) — 5xx dedupe 60s summary task.
            # `_record_5xx_for_dedupe` 가 첫 발생만 WARNING, 윈도우 내 재발생은 카운트만 누적.
            # 본 task 가 60s 주기로 만료된 카운트를 1행 INFO summary 후 dedupe state clear.
            self._5xx_dedupe_summary_task = asyncio.create_task(self._5xx_dedupe_summary_loop())

            # 사이클 76 (2026-06-08) — recovered 5분 collector flush task.
            # `_record_api_recovered` / `_record_quote_recovered` 가 5분 누적 → 1행 summary.
            self._api_recovered_collector_task = asyncio.create_task(
                self._api_recovered_collector_loop()
            )

            # 사이클 83 (2026-06-09) — 후보 풀 ticker stock_master eager refresh 5분 task.
            # `subscribe_filtered_stocks` 진입점 hook (Q1=B) 이 누적한 후보 ticker 를
            # 5분 주기로 stock_master upsert (24h TTL skip + 50ms sleep, Q3=B).
            self._scan_pool_eager_refresh_task = asyncio.create_task(
                self._scan_pool_eager_refresh_loop()
            )

            # 사이클 101 (2026-06-11) — 매일 20:00:05 전체 유니버스 적재 task.
            # Q68=A (fluctuation 영구 폐기) + Q69=B (_universe_eager_refresh_loop 영구 폐기)
            # _full_universe_load_task_loop 가 TIME_FULL_UNIVERSE_LOAD(20:00:05) 대기 후
            # _full_universe_load_once() 호출. 사이클 74/78/79 lifecycle 패턴 답습.
            self._full_universe_load_task = asyncio.create_task(
                self._full_universe_load_task_loop()
            )

            # 사이클 122 (2026-06-12) — 매일 16:00 KST 일봉 (FHKST03010100) 적재 task.
            # 사용자 결정 Q1=A 16:00 KST + Q2=C T-100일 + Q3=B 점진 + Q4=B DB 적재만.
            # 사이클 106 lifecycle race 차단 패턴 답습 (start() 직후 즉시 1회 + while 루프).
            self._stock_master_daily_load_task = asyncio.create_task(
                self._stock_master_daily_load_task_loop()
            )

            # 사이클 126 (2026-06-13) — 매일 16:10 KST KIS CTPF1002R 매스 보강 task.
            # KRX 1차 폴백 (`_full_universe_load_krx_primary`) 의 NXT/정지/관리종목
            # 하드코딩 False 결함 시정 — KIS CTPF1002R 호출로 실제 값 보강.
            # 사이클 122 일봉 task 100% 답습 (lifecycle race 차단 + start() 즉시 1회 + while).
            self._stock_master_basics_refresh_task = asyncio.create_task(
                self._stock_master_basics_refresh_task_loop()
            )

            # 사이클 129 (2026-06-13) — 매일 16:30 KST KIS 종목 마스터 파일 (kospi_code.mst / kosdaq_code.mst) 일괄 적재 task.
            # Q4=A 마스터 우선 + Q6=C master_raw 별도 컬럼 (사이클 81 G-AST1 raw 분리 영속).
            # domain-consult 의제 5 옵션 A 채택 — 16:30 KST 단일 task (D-1 영업일 종가 기준 = 17시간 lag 영역 명시 수용).
            # 사이클 122/126 패턴 100% 답습 (lifecycle race 차단 + start() 즉시 1회 + while).
            self._stock_master_master_load_task = asyncio.create_task(
                self._stock_master_master_load_task_loop()
            )

            # 사이클 150 (2026-06-16) — 매일 16:15 KST stock_master_daily T-150일 retention cron task.
            # 사용자 결정 Q3=C T-150일 (VCP T-120일 + 30일 안전 마진) + Q5=B 즉시 DROP.
            # 사이클 122 일봉 task (16:00) 적재 직후 15분 마진 + 보유/익일청산 ticker 절대 보호 (사이클 32 R4 답습).
            # 사이클 134 task_loop_helper 패턴 답습 (lifecycle race 차단 + start() 즉시 1회 + while).
            self._stock_master_daily_purge_task = asyncio.create_task(
                self._stock_master_daily_purge_task_loop()
            )

            # 사이클 171 (2026-06-22) — 매일 16:20 KST 저녁 잠정 funnel 캡처 task.
            # 16:00 일봉 → 16:10 basics → 16:20 funnel → 16:30 마스터 순서 (운영자 밤 후보 확인).
            # domain-consult 의제 4 우선순위 2 + 사이클 134 task_loop_helper 패턴 답습.
            self._evening_funnel_capture_task = asyncio.create_task(
                self._evening_funnel_capture_task_loop()
            )

            now = datetime.now().time()

            # 07:55 사전 구독: 돌파 종목 + 보유 포지션 → NXT 프리(08:00) 시가 즉시 수신
            if now < TIME_PRESUBSCRIBE:
                self._phase = "presubscribe_wait"
                await self._wait_until(TIME_PRESUBSCRIBE)
            if now <= TIME_KRX_OPEN_CONFIRM:
                # boot 시점의 prepare 실패 시 재실행 (KIS API 미준비 사례)
                if not self._collect_breakout_tickers():
                    logger.info("돌파 전략 유니버스 비어있음 → prepare 재실행")
                    await write_log("INFO", "돌파 유니버스 비어있어 prepare 재실행")
                    for sid in ("volatility_breakout", "long_tail_volatility"):
                        strategy = self.registry.get(sid)
                        if strategy and strategy.config.enabled:
                            try:
                                await strategy.prepare()
                            except Exception:
                                logger.exception("재 prepare 실패: %s", sid)
                ds = self.registry.get("donchian_swing")
                if ds and ds.config.enabled and not ds.get_scanned_tickers():
                    logger.info("스윙 전략 유니버스 비어있음 → prepare 재실행")
                    await write_log("INFO", "스윙 유니버스 비어있어 prepare 재실행")
                    try:
                        await ds.prepare()
                    except Exception:
                        logger.exception("재 prepare 실패: donchian_swing")

                presub = self._collect_presubscribe_tickers()
                if presub:
                    source_counts = self._build_subscription_source_counts(momentum_tickers=None)
                    priority_groups = self._build_priority_groups(momentum_tickers=None)
                    await subscribe_filtered_stocks(
                        [], extra_tickers=presub, source_counts=source_counts,
                        priority_groups=priority_groups,
                    )
                    logger.info("사전 구독: %d종목 (돌파 + 스윙 + 보유)", len(presub))
                    await write_log("INFO", f"사전 구독 {len(presub)}종목")

            # 08:00 NXT 프리 진입 — 익일 청산(NEXT_DAY_STABILIZE_SECS 후) + VB/LTV PRE_NXT 매매 시작
            if now < TIME_PRE_NXT_OPEN:
                self._phase = "pre_nxt_wait"
                await self._wait_until(TIME_PRE_NXT_OPEN)
            if now <= TIME_KRX_OPEN_CONFIRM:
                # 익일 청산: PRE_NXT 첫 거래 시가에서 청산 (Q2=B)
                self._next_day_task = asyncio.create_task(self._execute_next_day_clear())
                # 시가 확정 폴링 — 1차 시가는 NXT 프리 첫 거래.
                # 보드 경계 정각 호출은 board 명시 (2026-05-15, 결함 A): SessionTracker
                # `_session_loop` 30초 race 로 자동 결정 분기가 잘못된 보드로 폴백되는 결함 차단.
                await self._confirm_breakout_open_prices(board="pre_nxt")
                if self._collect_breakout_tickers():
                    self._phase = "pre_nxt_trading"
                    logger.info("VB/LTV PRE_NXT 매매 시작 (08:00~)")
                    await write_log("INFO", "NXT 프리 매매 시작")

                # KRX 메인 시가 확정(09:00:05) 까지 대기
                await self._wait_until(TIME_KRX_OPEN_CONFIRM)
                # KRX 메인 시가 재확정 (NXT 프리 시가와 별도, Phase 5 보드별 분리).
                # board="main" 명시 (2026-05-15, 결함 A): 09:00:05 시점 SessionTracker 가
                # 아직 main 진입 미반영이라 자동 결정은 pre_nxt 폴백 → boards["main"] 영영 비어
                # 5/14·5/15 KRX 메인 시간대 매수 신호 0건 사고 회귀 차단.
                await self._confirm_breakout_open_prices(board="main")
                # P1(B): NXT 시가 미수신으로 보류된 익일 청산을 시장가 정리
                await self._drain_pending_next_day_clear()
                self._phase = "main_trading"
                logger.info("KRX 메인 시가 확정 — VB/LTV MAIN 매매 진입")
                await write_log("INFO", "KRX 메인 매매 시작")
            elif now <= TIME_SCAN_START:
                # 중간 부팅 (KRX 메인 시간대)
                presub = self._collect_presubscribe_tickers()
                if presub:
                    source_counts = self._build_subscription_source_counts(momentum_tickers=None)
                    priority_groups = self._build_priority_groups(momentum_tickers=None)
                    await subscribe_filtered_stocks(
                        [], extra_tickers=presub, source_counts=source_counts,
                        priority_groups=priority_groups,
                    )
                await self._confirm_breakout_open_prices()
                await self._drain_pending_next_day_clear()
                if self._collect_breakout_tickers():
                    self._phase = "main_trading"
                    logger.info("KRX 메인 매매 시작 (중간 부팅): %d종목", len(presub))

            # 09:30~ 모멘텀 스캔 + 매매
            if now < TIME_SCAN_START:
                self._phase = "scanning"
                await self._wait_until(TIME_SCAN_START)

            if now < TIME_KRX_MAIN_BUY_STOP:
                tickers = await scan_stocks()
                extra = self._collect_breakout_tickers() + self._collect_swing_tickers()
                source_counts = self._build_subscription_source_counts(momentum_tickers=tickers)
                priority_groups = self._build_priority_groups(momentum_tickers=tickers)
                await subscribe_filtered_stocks(
                    tickers, extra_tickers=extra, source_counts=source_counts,
                    priority_groups=priority_groups,
                )

                # 09:00:05 이후 시작이면 시가 확정 재시도
                if now > TIME_KRX_OPEN_CONFIRM:
                    await self._confirm_breakout_open_prices()

                self._phase = "trading"
                self._scan_task = asyncio.create_task(self._scan_loop())
                logger.info("매매 모드 진입 (KRX 메인 + NXT)")

                await self._wait_until(TIME_KRX_MAIN_BUY_STOP)
                if self._scan_task is not None and not self._scan_task.done():
                    self._scan_task.cancel()
            else:
                self._scan_task = None
                logger.info("15:20 이후 시작 — KRX 메인 매수 중단 상태로 진입")

            # 15:20 KRX 메인 신규 매수 중단 + KRX 메인 종목 강제 청산
            # POST_NXT 활성 종목(VB/LTV)은 유지 — Phase 8 tradable_boards에서 보드 가드
            self._phase = "krx_main_stopped"
            await self._force_clear_main_only()
            await write_log("INFO", "15:20 KRX 메인 매수 중단 + 강제 청산")

            # 15:30 KRX 메인 마감 — NXT 애프터로 전환. 구독은 유지(POST_NXT 종목 시세 필요)
            await self._wait_until(TIME_KRX_MAIN_CLOSE)
            self._phase = "post_nxt_trading"
            await write_log("INFO", "15:30 KRX 메인 마감 → NXT 애프터 전환")
            # Phase 5 보드별 분리 (M, 2026-05-12) — POST_NXT 시가 확정 폴링.
            # board="post_nxt" 명시: 자동 결정은 main 우선이라 SessionTracker 전환 race 회피.
            # 누락 시 VB/LTV 후보의 `_targets[t]["boards"]["post_nxt"]["open_price"]` 영영 비어
            # 사용자 화면에 "시가 대기" 종목 잠복 (2026-05-12 운영 사고).
            await self._confirm_breakout_open_prices(board="post_nxt")

            # NXT 애프터에서도 _scan_loop 유지 (재구독은 보드별 화이트리스트로 결정 — Phase 8)
            if self._scan_task is None or self._scan_task.done():
                self._scan_task = asyncio.create_task(self._scan_loop())

            # 19:50 NXT 애프터 신규 매수 중단 (자문 호출은 20:00 으로 이동 — Phase 0, 2026-05-15)
            await self._wait_until(TIME_NXT_POST_BUY_STOP)
            self._phase = "post_nxt_stopped"
            for s in self.registry.enabled():
                s.state.buy_disabled = True
            await write_log("INFO", "19:50 NXT 애프터 매수 중단")

            # 20:00 NXT 애프터 종료 + AI자문 (둘 다 동시 발화, 백그라운드 task 로 race 회피)
            await self._wait_until(TIME_NXT_POST_CLOSE)
            self._phase = "closing"
            if self._scan_task and not self._scan_task.done():
                self._scan_task.cancel()
            await unsubscribe_all()
            await write_log("INFO", "20:00 NXT 애프터 종료, 구독 해제")

            # 20:00 전략수정 AI자문 (Phase 0, 2026-05-15: 19:50 → 20:00 이동)
            # - 백테스트 검증 정합성 사전 확보 (Phase 3 에서 외부 MCP 백테스트 enqueue)
            # - settlement(20:10) 와 10분 간격 — OpenAI 호출(전략당 30s × 6 = 3분) 수용 마진
            try:
                from src.engine.recommendation_engine import generate_recommendations
                await generate_recommendations()
                await write_log("INFO", "20:00 전략수정 AI자문 생성 완료")
            except Exception as e:
                import traceback
                logger.exception("전략수정 AI자문 생성 실패")
                tb = traceback.format_exc()
                # 1000자 제한 — system_logs 가독성
                await write_log(
                    "ERROR",
                    f"전략수정 AI자문 생성 실패: type={type(e).__name__} msg={e!s} trace={tb[:1000]}",
                )

            # 사이클 23 P3-1 — AI 자문 자동 적용 (감액만 + 50% cap)
            # 사이클 36 (긴급, 2026-05-21) — `KST` 미정의 NameError 시정.
            # scheduler 다른 함수들 (line 2209, 2362, 2575, 2739) 과 일관되게 `KST_TZ` 사용.
            try:
                from src.engine.recommendation_engine import auto_apply_recommendations
                from src.engine.scanner import KST_TZ as _AUTO_APPLY_KST_TZ
                target_date = datetime.now(_AUTO_APPLY_KST_TZ).date()
                result = await auto_apply_recommendations(target_date)
                await write_log(
                    "INFO",
                    f"20:00 AI 자문 자동 적용: applied={result.get('applied', 0)}"
                    f" skipped={result.get('skipped', 0)} reason={result.get('reason', '')}",
                )
            except Exception as e:
                logger.exception("AI 자문 자동 적용 실패")
                await write_log(
                    "ERROR",
                    f"AI 자문 자동 적용 실패: {type(e).__name__}: {e!s}",
                )

            # 20:10 정산
            await self._wait_until(TIME_SETTLEMENT)
            self._phase = "settling"
            # 사이클 62 (2026-06-05) — 가격 필터 일일 집계 (_settle 직전, Q6 자문)
            try:
                from src.engine import scanner as _scanner_mod
                await _scanner_mod.emit_price_filter_scanner_daily_summary()
            except Exception:
                logger.debug("[price_filter_scanner_daily_summary] scheduler emit 실패", exc_info=True)
            await self._settle()

            # 정산 직후: 일일 로그 분석 리포트 (실패해도 정산엔 영향 없음)
            # 주의: _reset_daily_state()는 log_analysis 후 호출 — funnel 카운터 수집 전에 0이 되면 안 됨
            self._phase = "log_analysis"
            try:
                from src.engine.log_analysis_engine import generate_daily_log_report
                await generate_daily_log_report()
                await write_log("INFO", "일일 로그 분석 리포트 생성 완료")
            except Exception as e:
                import traceback
                logger.exception("일일 로그 분석 리포트 생성 실패")
                tb = traceback.format_exc()
                # 1000자 제한 — system_logs 가독성
                await write_log(
                    "ERROR",
                    f"일일 로그 분석 리포트 생성 실패: type={type(e).__name__} msg={e!s} trace={tb[:1000]}",
                )

            # 사이클 6 통합 (2026-05-20) — 로그 retention 정리.
            # INFO 2일 / WARNING+ 30일 cutoff. 실패는 graceful (다음 사이클 재시도).
            # log_analysis 가 system_logs 를 *읽은 후* 에 호출 (분석 데이터 보존).
            try:
                from src.db.system_logs import purge_old_logs
                await purge_old_logs()
            except Exception as e:
                logger.exception("로그 retention 정리 실패")
                try:
                    await write_log(
                        "INFO",
                        f"[log_retention_skip] reason={type(e).__name__} msg={e!s}",
                    )
                except Exception:
                    pass  # write_log 자체 실패 시 본 흐름 보호

            # log_analysis가 funnel 카운터를 수집한 후에 일일 상태 초기화
            self._reset_daily_state()

            await kis_ws.disconnect()
            _ws_task = self._ws_task
            if _ws_task is not None:
                try:
                    await _ws_task
                except asyncio.CancelledError:
                    pass

        except Exception as exc:
            # 사이클 146 (2026-06-16) — 결함 #1 시정 graceful recovery 영구 영속:
            # 운영 사례 = 2026-06-16 09:01:16~09:07:43 KST KIS `/trading/inquire-balance`
            # 5xx 6회 retry exhausted → KisApiError 전파 → start() 영역 영구 영속 except
            # 진입 → 매매 프로세스 영역 영구 영속 비정상 종료 → run_daily 영역 영구 영속이
            # 다음 영업일 08:20 까지 대기 = 8시간 매매 손실 영역 영구 영속.
            # 시정 = KIS API 일시 5xx 영역 영구 영속 (잔고/시세/주문 영역) = 매매 hot path
            # 영역 영구 영속 보존 + WARNING 영역 영구 영속 + finally 영역 영구 영속 진입 안 함
            # → 다음 _scan_loop / _stale_watcher 영역 영구 영속이 자동 복구 영구 영속.
            # 기타 Exception 영역 영구 영속 = 기존 동작 영역 영구 영속 보존 (사이클 13-E-2 답습).
            from src.api.base import KisApiError
            if isinstance(exc, KisApiError):
                logger.warning(
                    "[매매 프로세스] KIS API 일시 장애 graceful 영역 영구 영속 (매매 프로세스 보존): %s",
                    exc,
                )
                await write_log(
                    "WARNING",
                    f"[매매 프로세스] KIS API 일시 장애 graceful (매매 프로세스 보존): {exc}",
                )
                # graceful = finally 진입 안 함 + 매매 프로세스 영역 영구 영속 보존
                # 다음 _scan_loop / _stale_watcher 영역 영구 영속 자동 복구 영구 영속.
                # 사이클 13-E-2 task lifecycle 영역 영구 영속 보존 영구 영속 (좀비 task 0).
                return
            logger.exception("매매 프로세스 오류")
            await write_log("ERROR", f"매매 프로세스 비정상 종료: {type(exc).__name__}: {str(exc)[:150]}")
        finally:
            # 사이클 13-E-2 — ws_task / scan_task 도 self.* 속성화 후 동일 cancel 루프 포함.
            # 정리 순서: 백그라운드 task 7종 cancel → 메인 ws disconnect → pool stop.
            # ws_task 가 살아있으면 disconnect 가 race 가능 → cancel 을 먼저.
            # 백그라운드 task lifecycle — 비정상 종료 시 좀비 task 방지
            for task_attr in (
                "_next_day_task", "_session_task", "_stale_watcher_task",
                "_session_health_task",  # 사이클 46
                "_swing_poll_task", "_swing_rest_poll_task",
                "_5xx_dedupe_summary_task",
                "_api_recovered_collector_task",  # 사이클 79 추가 — 사이클 76 도입, cancel 누락 시정
                "_scan_pool_eager_refresh_task",  # 사이클 83 추가 — 후보 풀 eager refresh task
                "_full_universe_load_task",       # 사이클 101 추가 — Q68=A+Q69=B 대체 daily 적재 task
                "_stock_master_daily_load_task",  # 사이클 122 추가 — KIS 일봉 적재 task
                "_stock_master_basics_refresh_task",  # 사이클 126 추가 — KIS CTPF1002R 매스 보강 task
                "_stock_master_master_load_task",  # 사이클 129 추가 — KIS 종목 마스터 파일 적재 task
                "_stock_master_daily_purge_task",  # 사이클 150 추가 — T-150일 retention cron task
                "_evening_funnel_capture_task",  # 사이클 171 추가 — 16:20 KST 저녁 잠정 funnel 캡처 task
                "_ws_task", "_scan_task",
            ):
                task = getattr(self, task_attr, None)
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
                setattr(self, task_attr, None)

            # 사이클 13-E-1 리뷰 ① — 비정상 종료 경로에서도 메인 disconnect 보장 (best-effort).
            # `start()` 본문 488 라인 도달 전 예외 발생 시 `try` 의 `kis_ws.disconnect()` 가
            # 건너뛰어진 채 `finally` 진입 가능 → 메인 WebSocket 이 연결된 채 잔존 + 다음 부팅
            # 시 동일 계정 중복 접속 위험. `disconnect()` 는 idempotent (websocket.py:163-169
            # `if self._ws:` 가드 + `self._ws = None` nullify) — 정상 경로에서 두 번째 호출은
            # noop. 따라서 항상 호출해도 회귀 0.
            try:
                await kis_ws.disconnect()
            except Exception:
                logger.warning("[scheduler_shutdown] main disconnect 실패 (best-effort)", exc_info=True)

            # 추가: 보조 세션 풀 정리 — 정상·비정상 종료 양쪽 보장
            # _started=False 재설정으로 다음 _boot start() 재초기화 + 24h 토큰 만료 후
            # silent death 차단. 메인→보조 순서 (위 disconnect 후) 보존.
            try:
                from src.realtime.websocket_pool import kis_ws_pool as _wsp
                await _wsp.stop()
            except Exception:
                logger.warning("[scheduler_shutdown] pool.stop 실패", exc_info=True)

            self._running = False
            self._phase = "idle"
            logger.info("매매 시스템 종료")
            # 사이클 72 hotfix: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT

    async def run_daily(self) -> None:
        """매일 08:20에 자동 시작하는 무한 루프.

        장 종료(정산 완료) 후 다음 날 08:20까지 대기 → 자동 시작을 반복한다.
        주말(토/일)은 건너뛴다.
        """
        while True:
            now = datetime.now()
            weekday = now.weekday()  # 0=월 ~ 6=일

            # 주말이면 월요일까지 대기
            if weekday >= 5:
                days_until_monday = 7 - weekday
                next_start = datetime.combine(
                    now.date() + timedelta(days=days_until_monday),
                    TIME_AUTO_START,
                )
                wait_secs = (next_start - now).total_seconds()
                logger.info("주말 — 월요일 %s까지 대기 (%.0f시간)",
                            next_start.strftime("%m-%d %H:%M"), wait_secs / 3600)
                await asyncio.sleep(max(wait_secs, 0))
                continue

            # 오늘 08:20 이전이면 08:20까지 대기
            today_start = datetime.combine(now.date(), TIME_AUTO_START)
            if now < today_start:
                wait_secs = (today_start - now).total_seconds()
                logger.info("매매 자동 시작 대기: %s (%.0f분 후)",
                            today_start.strftime("%H:%M"), wait_secs / 60)
                await asyncio.sleep(max(wait_secs, 0))

            # 이미 장 종료 시간이면 내일로
            if now.time() >= TIME_SETTLEMENT:
                tomorrow_start = datetime.combine(
                    now.date() + timedelta(days=1),
                    TIME_AUTO_START,
                )
                wait_secs = (tomorrow_start - now).total_seconds()
                logger.info("장 종료 — 내일 %s까지 대기 (%.0f시간)",
                            tomorrow_start.strftime("%m-%d %H:%M"), wait_secs / 3600)
                await asyncio.sleep(max(wait_secs, 0))
                continue

            # 매매 시작 전 auto_start 설정 재확인 (Settings에서 비활성화했을 수 있음)
            if not await self._is_auto_start_enabled():
                logger.info("auto_start 비활성화 — 자동 매매 건너뜀")
                await asyncio.sleep(60)
                continue

            # 휴장일(공휴일) 차단 — KIS chk-holiday API
            from src.api.condition import is_market_open, next_trading_day
            from src.auth.token import token_manager
            try:
                await token_manager.get_token()  # 토큰 선발급(휴장일 API 호출용)
                if not await is_market_open(now.date()):
                    nxt = await next_trading_day(now.date())
                    next_start = datetime.combine(nxt, TIME_AUTO_START)
                    wait_secs = (next_start - datetime.now()).total_seconds()
                    logger.info(
                        "오늘(%s) 휴장 — 다음 영업일 %s까지 대기 (%.0f시간)",
                        now.date(), nxt, max(wait_secs, 0) / 3600,
                    )
                    await write_log("INFO", f"오늘({now.date()}) 휴장 — 다음 영업일 {nxt}까지 대기")
                    await asyncio.sleep(max(wait_secs, 60))
                    continue
            except Exception:
                logger.exception("휴장일 체크 실패 — 영업일로 가정하고 진행")

            # 매매 시작
            logger.info("=== 자동 매매 시작 (%s) ===", now.strftime("%Y-%m-%d %H:%M"))
            try:
                await self.start()
            finally:
                # 사이클 83 (2026-06-09) — 비정상 종료 경로 task cancel 보강 (사이클 13-E-2 패턴 답습).
                # start() 내부 finally 가 이미 정리하나 run_daily 레벨에서도 동일 task_attrs 튜플로
                # 이중 보장 (이미 None 인 경우 getattr None → skip 분기 — idempotent).
                for task_attr in (
                    "_next_day_task", "_session_task", "_stale_watcher_task",
                    "_session_health_task",
                    "_swing_poll_task", "_swing_rest_poll_task",
                    "_5xx_dedupe_summary_task",
                    "_api_recovered_collector_task",  # 사이클 79 영속
                    "_scan_pool_eager_refresh_task",  # 사이클 83 추가 — 후보 풀 eager refresh task
                    "_full_universe_load_task",       # 사이클 101 추가 — Q68=A+Q69=B 대체 daily 적재 task
                    "_stock_master_daily_load_task",  # 사이클 122 추가 — KIS 일봉 적재 task
                "_stock_master_basics_refresh_task",  # 사이클 126 추가 — KIS CTPF1002R 매스 보강 task
                "_stock_master_master_load_task",  # 사이클 129 추가 — KIS 종목 마스터 파일 적재 task
                "_stock_master_daily_purge_task",  # 사이클 150 추가 — T-150일 retention cron task
                "_evening_funnel_capture_task",  # 사이클 171 추가 — 16:20 KST 저녁 잠정 funnel 캡처 task
                    "_ws_task", "_scan_task",
                ):
                    task = getattr(self, task_attr, None)
                    if task and not task.done():
                        task.cancel()
                        try:
                            await task
                        except (asyncio.CancelledError, Exception):
                            pass
                    setattr(self, task_attr, None)

            # start()가 종료되면 (정산 완료 또는 에러) 다음 날 대기
            logger.info("금일 매매 종료, 익일 자동 시작 대기")
            await asyncio.sleep(60)  # 정산 직후 바로 재시작 방지

    async def stop(self) -> None:
        """매매 프로세스를 중지한다."""
        self._running = False
        # 사이클 13-E-3 — finally 블록 (line 500~518) 과 동일한 7종 task cancel.
        # `_ws_task`/`_scan_task` 누락 시 stop→start 빠른 재시작 race 에서
        # 좀비 connect 루프 + scan_loop 가 중복 동작 가능 (Copilot 리뷰 #1).
        for task_attr in (
            "_next_day_task", "_session_task", "_stale_watcher_task",
            "_session_health_task",  # 사이클 46
            "_swing_poll_task", "_swing_rest_poll_task",
            "_5xx_dedupe_summary_task",
            "_api_recovered_collector_task",  # 사이클 79 추가 — 사이클 76 도입, cancel 누락 시정
            "_scan_pool_eager_refresh_task",  # 사이클 83 추가 — 후보 풀 eager refresh task
            "_full_universe_load_task",       # 사이클 101 추가 — Q68=A+Q69=B 대체 daily 적재 task
            "_stock_master_daily_load_task",  # 사이클 122 추가 — KIS 일봉 적재 task
            "_stock_master_basics_refresh_task",  # 사이클 126 추가 — KIS CTPF1002R 매스 보강 task
            "_stock_master_master_load_task",  # 사이클 129 추가 — KIS 종목 마스터 파일 적재 task
            "_stock_master_daily_purge_task",  # 사이클 150 추가 — T-150일 retention cron task
            "_evening_funnel_capture_task",  # 사이클 171 추가 — 16:20 KST 저녁 잠정 funnel 캡처 task
            "_ws_task", "_scan_task",
        ):
            task = getattr(self, task_attr, None)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            setattr(self, task_attr, None)
        # 사이클 78 hotfix: 잔존 collector 마지막 flush (Q5 사이클 74 G-SP4 답습)
        # 운영 종료 직전 부분 누적 잔존 카운터 손실 방지
        try:
            flush_swing_rest_poll_collector()
        except Exception:
            logger.exception("[swing_rest_poll_collector] shutdown flush 실패")
        try:
            from src.engine.stale_watcher_core import flush_stale_watcher_collector
            flush_stale_watcher_collector()
        except Exception:
            logger.exception("[stale_watcher_collector] shutdown flush 실패")
        # 사이클 83 hotfix: 잔존 eager refresh collector 마지막 flush (사이클 78 답습)
        try:
            from src.engine.scanner import flush_scan_pool_eager_refresh_collector
            flush_scan_pool_eager_refresh_collector()
        except Exception:
            logger.exception("[scan_pool_eager_refresh_collector] shutdown flush 실패")
        # 사이클 89 hotfix: universe collector 마지막 flush (사이클 78 G-SP4 답습)
        try:
            from src.engine.stock_master_metrics import flush_universe_collector
            flush_universe_collector()
        except Exception:
            logger.exception("[universe_collector] shutdown flush 실패")
        # 사이클 101 hotfix: full_universe_load_collector 마지막 flush (사이클 78 G-SP4 답습)
        try:
            from src.engine.stock_master_metrics import flush_full_universe_load_collector
            flush_full_universe_load_collector()
        except Exception:
            logger.exception("[full_universe_load_collector] shutdown flush 실패")
        await unsubscribe_all()
        await kis_ws.disconnect()
        # 추가: 수동 중지 시에도 동일 보장
        try:
            from src.realtime.websocket_pool import kis_ws_pool as _wsp
            await _wsp.stop()
        except Exception:
            logger.warning("[scheduler_stop] pool.stop 실패", exc_info=True)
        logger.info("매매 시스템 수동 중지")
        # 사이클 72 hotfix: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT

    async def _session_loop(self) -> None:
        """SessionTracker 1분 주기 tick — 보드 진입/종료 콜백 발화."""
        while self._running:
            try:
                await session_tracker.tick()
            except Exception:
                logger.exception("session_tracker.tick 실패")
            await asyncio.sleep(SESSION_TICK_INTERVAL)

    def get_status(self) -> dict:
        """현재 상태를 반환한다."""
        from src.engine.scanner import get_scan_status, ticker_names

        # 기존 필드 합산 유지
        total_positions = sum(len(s.state.positions) for s in self.registry.all())
        total_pending = sum(len(s.state.pending_buys) for s in self.registry.all())
        all_position_tickers = []
        all_pending_tickers = []
        total_realized_pnl = 0
        total_investment = 0
        any_buy_disabled = False
        all_buy_signals = []

        for s in self.registry.all():
            all_position_tickers.extend(s.state.positions.keys())
            all_pending_tickers.extend(s.state.pending_buys)
            total_realized_pnl += s.state.daily_realized_pnl
            total_investment += s.state.total_investment
            if s.state.buy_disabled:
                any_buy_disabled = True
            all_buy_signals.extend(s.state.buy_signals)

        # 시간순 정렬 후 최근 10개
        all_buy_signals.sort(key=lambda x: x.get("time", ""), reverse=True)

        positions_detail = {}
        for s in self.registry.all():
            for ticker, pos in s.state.positions.items():
                positions_detail[ticker] = {
                    "name": ticker_names.get(ticker, ""),
                    "buy_price": pos.buy_price,
                    "quantity": pos.quantity,
                    "high_since_buy": pos.high_since_buy,
                    "buy_date": pos.buy_date.isoformat(),
                    "is_next_day": pos.is_next_day,
                    "strategy_id": pos.strategy_id,
                }

        order_fills = {}
        for order_no, filled in self.order_engine._filled_qty.items():
            ordered = self.order_engine._order_qty.get(order_no, 0)
            order_fills[order_no] = {
                "filled_qty": filled,
                "order_qty": ordered,
            }

        from src.config import settings as _settings

        return {
            "running": self._running,
            "env": _settings.kis_env,
            "positions": total_positions,
            "pending_buys": total_pending,
            "position_tickers": all_position_tickers,
            "phase": self._phase,
            "scan": get_scan_status(),
            "positions_detail": positions_detail,
            "orders": {
                "pending_buy_tickers": all_pending_tickers,
                "pending_buy_orders": {
                    no: {**info, "name": ticker_names.get(info["ticker"], "")}
                    for no, info in self.order_engine._pending_buy_orders.items()
                },
                "fills": order_fills,
                "pending_cancels": list(self.order_engine._pending_cancel_tasks.keys()),
            },
            "strategy": {
                "buy_disabled": any_buy_disabled,
                "daily_realized_pnl": total_realized_pnl,
                "total_investment": total_investment,
                "buy_signals": all_buy_signals[:10],
            },
            "strategies": self.registry.get_strategies_status(),
        }

    # -- private --------------------------------------------------------

    async def _execute_next_day_clear(self) -> None:
        """09:00 익일 청산 로직.

        익일 청산을 지원하는 전략(momentum, long_tail_volatility, volatility_breakout)
        의 is_next_day 포지션을 처리한다.

        - momentum / LTV: 정책상 익일 청산 정상 경로
        - VB: 안전망 (2026-05-15, 결함 D 잔여) — VB 정책은 당일 15:20 일괄 매도이나
          그게 누락되면 본 경로로 다음 영업일 NXT 프리 청산. 5/15 LG전자(066570) 사고 대응.

        1. 전일 매수 보유 종목 목록 조회
        2. 각 종목의 당일 시가 확인 (WebSocket 시세 구독으로 수신)
        3. 60초 대기하여 시가 안정화 (대기 중 on_tick의 NEXT_DAY_CLEAR 억제)
        4. 시가가 매수가 대비 gap_up_threshold 이상 → 트레일링 스탑 모드
        5. gap_up_threshold 미만 → 즉시 시장가 전량 매도
        """
        # 익일 청산 대상 전략 수집 (momentum + long_tail_volatility + volatility_breakout 안전망)
        overnight_strategies: list[tuple[str, object]] = []
        for sid in ("momentum", "long_tail_volatility", "volatility_breakout"):
            s = self.registry.get(sid)
            if s and s.config.enabled:
                overnight_strategies.append((sid, s))

        # 전략별 익일 포지션 수집
        all_next_day: list[tuple[str, object, str]] = []  # (ticker, pos, strategy_id)
        for sid, strategy in overnight_strategies:
            for ticker, p in strategy.state.positions.items():
                if p.is_next_day:
                    all_next_day.append((ticker, p, sid))

        if not all_next_day:
            logger.info("익일 청산 대상 없음")
            return

        await write_log("INFO", f"익일 청산 대상: {[(t, sid) for t, _, sid in all_next_day]}")

        # on_tick에서 즉시 청산하지 않도록 대기 플래그 설정 (손절은 계속 작동)
        for _, strategy in overnight_strategies:
            if hasattr(strategy, '_next_day_clear_pending'):
                strategy._next_day_clear_pending = True

        # 보유 종목에 대해 시세 구독 (시가 수신용)
        from src.engine.scanner import TICK_TR_ID
        for ticker, _, _ in all_next_day:
            await kis_ws.subscribe(TICK_TR_ID, ticker)

        # 시가 안정화 대기 — Q2=B (NXT 프리 첫 거래 후 짧은 안정화)
        await asyncio.sleep(NEXT_DAY_STABILIZE_SECS)

        # 대기 완료 — on_tick 가드 해제
        for _, strategy in overnight_strategies:
            if hasattr(strategy, '_next_day_clear_pending'):
                strategy._next_day_clear_pending = False

        from src.engine.scanner import t, ticker_prices
        from src.engine.util.tick_size import step_down

        # Phase G (2026-05-11) — stock_master 사전 판별로 NXT 거래 불가 종목은 즉시 보류.
        # 시가 폴링/안정화 대기를 거치지 않고 09:00 KRX 시장가 청산 경로로 직행.
        from src.db import stock_master as _stock_master_mod

        for ticker, pos, strategy_id in all_next_day:
            strategy = self.registry.get(strategy_id)
            if not strategy or ticker not in strategy.state.positions:
                continue  # 대기 중 손절로 이미 처리됨

            # Phase G: stock_master 1순위 사전 차단
            try:
                basics = await _stock_master_mod.get(ticker)
            except Exception:
                basics = None
                logger.exception("stock_master.get 실패 (시가 휴리스틱 fallback): %s", ticker)

            if basics is not None and not basics.nxt_tradable:
                # NXT 등록 안 됨 (또는 정지) — 시가 수신 무관 즉시 보류
                self._pending_next_day_clear.add((ticker, strategy_id))
                # 사이클 162 (2026-06-17) — DB 영속화 (의제 D, 메모리 휘발 차단).
                # EC2 재기동 시 _boot() 영역에서 load_pending_ndc() 로 메모리 복구.
                try:
                    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
                    from src.db.pending_next_day_clear import save_pending_ndc
                    _kst = _tz(_td(hours=9))
                    _today = _dt.now(_kst).date()
                    await save_pending_ndc(_today, ticker, strategy_id, reason="nxt_not_tradable")
                except Exception:
                    logger.exception(
                        "[pending_ndc_save_skip] ticker=%s strategy=%s — 메모리 set 보존 graceful",
                        ticker, strategy_id,
                    )
                logger.info(
                    "stock_master nxt_tradable=False — 익일 청산 보류 (09:00 KRX 시장가 청산 예약): "
                    "%s (전략: %s)", t(ticker), strategy_id,
                )
                await write_log(
                    "INFO",
                    f"NXT 거래 불가 사전 판별 — 익일 청산 보류: {t(ticker)} ({strategy_id})",
                )
                # PR-B (2026-05-14): 구조화 로그 prefix — Loki 파싱용 별도 행
                await write_log(
                    "INFO",
                    f"[next_day_clear_deferred] ticker={ticker} strategy={strategy_id} "
                    f"reason=nxt_not_tradable",
                )
                continue

            gap_up_threshold = strategy.config.params.get("gap_up_threshold", 10.0)

            # WebSocket에서 수신한 실제 시가 사용 (사전구독되어 있으면 08:00:00에 들어옴 — NXT 프리)
            price_data = ticker_prices.get(ticker, {})
            today_open = price_data.get("open_price", 0)
            if today_open <= 0:
                # 30초 대기에도 시가 미수신 → 짧은 폴링 + KIS API 폴백
                today_open = await self._resolve_open_price(ticker, max_wait_s=2.0)

            # P1(B): NXT 시가 미수신 → NXT 거래 불가 종목으로 추정 (stock_master cache miss fallback).
            # high_since_buy 폴백으로 갭률 0% 즉시 청산하던 위험 경로 제거.
            # 청산을 09:00 KRX 메인 시가 확정 이후로 보류 (_drain_pending_next_day_clear).
            if today_open <= 0:
                self._pending_next_day_clear.add((ticker, strategy_id))
                # 사이클 162 (2026-06-17) — DB 영속화 (의제 D).
                try:
                    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
                    from src.db.pending_next_day_clear import save_pending_ndc
                    _kst = _tz(_td(hours=9))
                    _today = _dt.now(_kst).date()
                    await save_pending_ndc(_today, ticker, strategy_id, reason="nxt_open_missing")
                except Exception:
                    logger.exception(
                        "[pending_ndc_save_skip] ticker=%s strategy=%s — 메모리 set 보존 graceful",
                        ticker, strategy_id,
                    )
                logger.warning(
                    "NXT 시가 미수신 — 익일 청산 보류 (KRX 시가 확정 후 재시도): %s (전략: %s)",
                    t(ticker), strategy_id,
                )
                await write_log(
                    "WARNING",
                    f"NXT 시가 미수신 — 익일 청산 보류: {t(ticker)} ({strategy_id})",
                )
                # PR-B (2026-05-14): 구조화 로그 prefix — Loki 파싱용 별도 행
                await write_log(
                    "INFO",
                    f"[next_day_clear_deferred] ticker={ticker} strategy={strategy_id} "
                    f"reason=nxt_open_missing",
                )
                continue

            if pos.buy_price > 0:
                gap_rate = (today_open - pos.buy_price) / pos.buy_price * 100
            else:
                gap_rate = 0.0

            if gap_rate >= gap_up_threshold:
                # 사이클 142 — 결함 #2 시정: LTV strategy 후성 동기화 (자문 영속 정합).
                # 후성 093370 운영 사례 (6/12 매수 → 6/15 트레일링 silent 미발화 -5.91% 손실).
                # check_exit_signal 익일 트레일링 분기 진입 의무 영역 영구 영속:
                # - _limit_up_reached.add(ticker) = 상한가 모드 영역 영구 영속 진입 보장
                # - pos.high_since_buy = today_open = 트레일링 기준점 영역 영구 영속 설정
                # VB 변경 0 영역 영구 영속 (strategy_id 가드).
                if strategy_id == "long_tail_volatility":
                    ltv_strategy = self.registry.get(strategy_id)
                    if ltv_strategy is not None and hasattr(ltv_strategy, "_limit_up_reached"):
                        ltv_strategy._limit_up_reached.add(ticker)
                    pos.high_since_buy = today_open
                logger.info(
                    "트레일링 스탑 모드: %s 갭률 %.1f%% (전략: %s, 기준가: %d)",
                    t(ticker), gap_rate, strategy_id, today_open,
                )
                await write_log(
                    "INFO",
                    f"트레일링 스탑 모드: {t(ticker)} 갭률 {gap_rate:.1f}% "
                    f"({strategy_id}, 기준가: {today_open})",
                )
            else:
                # NXT 프리에서는 지정가 매도 (직전가 -1호가, KRX 호가단위 적용)
                limit_price = step_down(int(today_open), steps=1)
                logger.info(
                    "익일 NXT 지정가 청산: %s 갭률 %.1f%% (전략: %s, 지정가: %d)",
                    t(ticker), gap_rate, strategy_id, limit_price,
                )
                await self.order_engine.execute_sell(
                    ticker, Signal.NEXT_DAY_CLEAR, strategy_id, limit_price=limit_price,
                )
                await write_log(
                    "INFO",
                    f"익일 NXT 지정가 청산 실행: {t(ticker)} 갭률 {gap_rate:.1f}% "
                    f"({strategy_id}, 지정가: {limit_price})",
                )

        logger.info("익일 청산 실행 완료")

    async def _drain_pending_next_day_clear(self) -> None:
        """KRX 시가 확정 후 보류된 익일 청산 종목을 시장가로 청산한다.

        P1(B): NXT 거래 불가 종목은 08:00 청산을 보류했다가 09:00 KRX 메인 시가
        확정 직후(`_confirm_breakout_open_prices(board="main")` 호출 후)에 이 메서드를
        호출해 시장가 매도로 일괄 정리한다. 정규장 시간대이므로 시장가 OK.
        """
        if not self._pending_next_day_clear:
            return

        from src.engine.scanner import t

        pending = list(self._pending_next_day_clear)
        logger.info("보류된 익일 청산 처리 시작: %d건", len(pending))
        await write_log("INFO", f"보류된 익일 청산 처리: {len(pending)}건")

        import time as _time

        for ticker, strategy_id in pending:
            strategy = self.registry.get(strategy_id)
            if not strategy or ticker not in strategy.state.positions:
                # 그 사이 손절 등으로 이미 처리됨
                self._pending_next_day_clear.discard((ticker, strategy_id))
                continue
            # PR-B (2026-05-14): drained 결과 + elapsed_ms 구조화 로그
            _start = _time.monotonic()
            _result = "success"
            try:
                await self.order_engine.execute_sell(
                    ticker, Signal.NEXT_DAY_CLEAR, strategy_id,
                )
                await write_log(
                    "INFO",
                    f"보류 익일 청산(시장가) 실행: {t(ticker)} ({strategy_id})",
                )
            except Exception:
                _result = "fail"
                logger.exception("보류 익일 청산 실패: %s (%s)", ticker, strategy_id)
            finally:
                self._pending_next_day_clear.discard((ticker, strategy_id))
                # 사이클 162 (2026-06-17) — DB 영속화 동행 DELETE (의제 D).
                try:
                    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
                    from src.db.pending_next_day_clear import delete_pending_ndc
                    _kst = _tz(_td(hours=9))
                    _today = _dt.now(_kst).date()
                    await delete_pending_ndc(_today, ticker, strategy_id)
                except Exception:
                    logger.exception(
                        "[pending_ndc_delete_skip] ticker=%s strategy=%s graceful",
                        ticker, strategy_id,
                    )
                _elapsed_ms = int((_time.monotonic() - _start) * 1000)
                _level = "INFO" if _result == "success" else "WARNING"
                await write_log(
                    _level,
                    f"[next_day_clear_drained] ticker={ticker} strategy={strategy_id} "
                    f"result={_result} elapsed_ms={_elapsed_ms}",
                )

    async def _confirm_breakout_open_prices(
        self, *, max_wait_s: float = 5.0, interval_s: float = 0.5, board: str | None = None,
    ) -> None:
        """돌파 전략(VB, LTV)의 보드별 시가를 확정한다.

        1차: WebSocket ticker_prices 캐시를 max_wait_s 동안 interval_s 간격으로 폴링
        2차: 폴링 종료 시점에도 미확정인 종목만 KIS 개별시세 API로 폴백 조회

        `board` 미지정 시 SessionTracker의 활성 보드 중 우선순위(main → post_nxt → pre_nxt)로 결정.
        """
        from src.engine.scanner import ticker_prices

        # 호출 시점의 활성 보드 결정 (board 인자가 없으면 SessionTracker에서)
        if board is None:
            from src.engine.session import session_tracker, MarketBoard
            active = session_tracker.active
            for candidate in ("main", "post_nxt", "pre_nxt"):
                if MarketBoard(candidate) in active:
                    board = candidate
                    break
            if board is None:
                # 활성 보드 없음 — 시각 기반 fallback
                now_t = datetime.now().time()
                if now_t < time(9, 0):
                    board = "pre_nxt"
                elif now_t < time(15, 30):
                    board = "main"
                else:
                    board = "post_nxt"

        # 대상 전략 + 종목 수집 — 해당 board를 활성화한 전략만
        from src.engine.session import get_tradable_boards, MarketBoard
        targets: list[tuple[str, object, list[str]]] = []
        for sid in ("volatility_breakout", "long_tail_volatility"):
            strategy = self.registry.get(sid)
            if not strategy or not strategy.config.enabled:
                continue
            if not hasattr(strategy, '_targets') or not hasattr(strategy, 'on_open_price_confirmed'):
                continue
            allowed = get_tradable_boards(sid, strategy.config.params)
            if MarketBoard(board) not in allowed:
                continue
            targets.append((sid, strategy, list(strategy._targets.keys())))

        if not targets:
            return

        def _is_confirmed(strategy, ticker: str) -> bool:
            states = strategy._open_confirmed.get(ticker)
            if isinstance(states, dict):
                return states.get(board, False)
            return bool(states)

        # PR-H (P4, 2026-05-15) — idempotent 강화: 모든 종목이 이미 해당 board 로 confirmed 면
        # 1차 폴링 / 2차 KIS API 폴백 / 종합 INFO 로그 / `_emit_breakout_open_confirm` 모두 skip.
        # 결함: 운영 로그 15:30~16:39 동안 LTV 만 4번 시가 재확정 (VB 1회) — 진단 결과
        # `_scanned_tickers` 빈 케이스에서 `_reprepare_breakout_if_empty` 가 LTV 만 발화
        # → prepare 가 `_open_confirmed[ticker]={}` reset → 시가 재확정 호출 → 매번 INFO 로그.
        # 모두 confirmed 인 호출은 KIS Rate Limit + 운영 가시성 노이즈 모두 차단.
        all_already_confirmed = all(
            _is_confirmed(strategy, ticker)
            for _, strategy, tickers in targets
            for ticker in tickers
        )
        if all_already_confirmed:
            logger.debug(
                "[confirm_open_prices_skip] board=%s — 모든 대상 종목이 이미 confirmed (idempotent)",
                board,
            )
            return

        # 1차: WebSocket 폴링
        elapsed = 0.0
        while elapsed < max_wait_s:
            all_done = True
            for _, strategy, tickers in targets:
                for ticker in tickers:
                    if _is_confirmed(strategy, ticker):
                        continue
                    price_info = ticker_prices.get(ticker)
                    if price_info and price_info.get("open_price", 0) > 0:
                        strategy.on_open_price_confirmed(ticker, price_info["open_price"], board=board)
                    else:
                        all_done = False
            if all_done:
                break
            await asyncio.sleep(interval_s)
            elapsed += interval_s

        # 2차: 미확정 종목만 KIS API 폴백
        from src.api.condition import fetch_stock_detail
        for sid, strategy, tickers in targets:
            unconfirmed = [t for t in tickers if not _is_confirmed(strategy, t)]
            for ticker in unconfirmed:
                try:
                    detail = await fetch_stock_detail(ticker)
                    open_price = int(detail.get("stck_oprc", "0"))
                    if open_price > 0:
                        strategy.on_open_price_confirmed(ticker, open_price, board=board)
                except Exception:
                    logger.debug("%s 시가 조회 실패: %s", sid, ticker)

            confirmed = sum(1 for t in tickers if _is_confirmed(strategy, t))
            logger.info("%s 시가 확정 [%s]: %d/%d종목", strategy.config.name, board, confirmed, len(tickers))
            # 가설 C (2026-05-12): 보드별 시가 확정 상세 — confirmed/empty/sample 노출
            self._emit_breakout_open_confirm(board, strategy)

    def _emit_breakout_open_confirm(self, board: str, strategy) -> None:
        """가설 C (2026-05-12) — `_confirm_breakout_open_prices` 직후 1행 INFO 로그.

        형식: [breakout_open_confirm] board=BOARD strategy=SID confirmed=N empty=M sample={t:open_price,...}
        - confirmed: open_price > 0 인 후보 수
        - empty: open_price == 0 (시가 미확정) 후보 수
        - sample: sorted(ticker) 처음 5개의 {ticker: open_price} dict
        """
        try:
            status = strategy.get_targets_status()
        except Exception:
            logger.debug("[breakout_open_confirm] get_targets_status 실패", exc_info=True)
            return
        confirmed = 0
        empty = 0
        opens: dict[str, int] = {}
        for ticker, info in (status or {}).items():
            # 보드별 시가 우선, 없으면 단일 open_price
            board_info = (info.get("boards") or {}).get(board) if isinstance(info, dict) else None
            if isinstance(board_info, dict):
                op = int(board_info.get("open_price") or 0)
            else:
                op = int(info.get("open_price") or 0) if isinstance(info, dict) else 0
            opens[ticker] = op
            if op > 0:
                confirmed += 1
            else:
                empty += 1
        sample_keys = sorted(opens.keys())[:5]
        sample = {t: opens[t] for t in sample_keys}
        sid = getattr(strategy, "strategy_id", None) or getattr(strategy.config, "strategy_id", "?")
        logger.info(
            "[breakout_open_confirm] board=%s strategy=%s confirmed=%d empty=%d sample=%s",
            board, sid, confirmed, empty, sample,
        )

    def _collect_breakout_tickers(self) -> list[str]:
        """돌파 4 전략(VB / LTV / BFB / VCP)의 스캔 종목을 합산한다.

        사이클 32 (R4, 2026-05-21) — `_universe_excluded_today` 종목 필터링.
        stale > 5 + 거래량 빈약 자동 제외 (매일 reset).

        사이클 48 (2026-05-27, PR #15 P1 후속) — bull_flag_breakout / vcp_breakout 편입.
        BFB/VCP 매수 신호는 폴링 루프 없이 `risk.on_tick`(WebSocket tick) 으로만 평가되므로
        이 함수(= `_scan_loop` extra / `_collect_presubscribe_tickers` / `_build_priority_groups`
        breakout 그룹의 유일한 소스)에 포함되어야 구독 → tick 수신 → 매수 평가가 성립한다.
        미포함 시 유니버스/임계 완화를 해도 BFB/VCP 0건 지속.
        """
        tickers: list[str] = []
        for sid in (
            "volatility_breakout",
            "long_tail_volatility",
            "bull_flag_breakout",
            "vcp_breakout",
        ):
            strategy = self.registry.get(sid)
            if strategy and strategy.config.enabled and hasattr(strategy, 'get_scanned_tickers'):
                tickers.extend(strategy.get_scanned_tickers())
        # 사이클 32 — universe 제외 종목 필터링 (사전 init 누락 인스턴스 보호)
        excluded = getattr(self, "_universe_excluded_today", None) or set()
        if excluded:
            tickers = [t for t in tickers if t not in excluded]
        return tickers

    def _collect_swing_tickers(self) -> list[str]:
        """스윙 전략(donchian_swing)의 스캔 종목을 반환한다.

        시세 미수신 시 check_buy_signal/check_exit_signal이 호출되지 않으므로
        사전구독·통합구독에 반드시 포함시켜야 한다.
        """
        tickers: list[str] = []
        strategy = self.registry.get("donchian_swing")
        if strategy and strategy.config.enabled and hasattr(strategy, "get_scanned_tickers"):
            tickers.extend(strategy.get_scanned_tickers())
        return tickers

    def _collect_presubscribe_tickers(self) -> list[str]:
        """09:00 시가 수신용 사전 구독 대상.

        - 돌파 전략(VB, MB) 스캔 종목
        - 모든 전략의 보유 포지션 (모멘텀 익일청산/스윙 트레일링 시가 수신용)

        G안(2026-05-12): donchian_swing 스캔 후보는 제외. Pull 폴링(`_swing_buy_poll_loop`)
        으로 매수 평가하므로 WebSocket 슬롯 불필요. 보유 종목은 positions 합집합 경로로
        자동 포함되어 청산 평가(ATR 트레일링/하드 -7%) 보장.
        """
        tickers: set[str] = set(self._collect_breakout_tickers())
        for s in self.registry.all():
            tickers.update(s.state.positions.keys())
        return list(tickers)

    def _build_subscription_source_counts(
        self, momentum_tickers: list[str] | None = None,
    ) -> dict[str, int]:
        """구독 발화 시점의 출처별 카운트(원본 후보 개수, 합집합 *전*) dict 를 산출한다 (Phase B).

        - `vb`         : volatility_breakout.get_scanned_tickers() 개수
        - `ltv`        : long_tail_volatility.get_scanned_tickers() 개수
        - `bfb`        : bull_flag_breakout.get_scanned_tickers() 개수 (사이클 48)
        - `vcp`        : vcp_breakout.get_scanned_tickers() 개수 (사이클 48)
        - `swing`      : donchian_swing.get_scanned_tickers() 개수
        - `momentum`   : momentum_tickers 인자 길이 (scan_stocks() 결과)
        - `positions`  : 모든 전략 보유 포지션 합산 (중복 가능)

        합집합 후 실제 구독 개수는 `subscribe_filtered_stocks` 가 자체 계산해 `total=` 로 노출.
        어제(2026-05-11) "기타 23종목" 표기에서 VB/LTV 0건 식별 불가 결함 보완.
        """
        counts: dict[str, int] = {
            "vb": 0,
            "ltv": 0,
            "bfb": 0,
            "vcp": 0,
            "swing": 0,
            "momentum": len(momentum_tickers) if momentum_tickers else 0,
            "positions": 0,
        }
        vb = self.registry.get("volatility_breakout")
        if vb and hasattr(vb, "get_scanned_tickers"):
            try:
                counts["vb"] = len(vb.get_scanned_tickers())
            except Exception:
                counts["vb"] = 0
        ltv = self.registry.get("long_tail_volatility")
        if ltv and hasattr(ltv, "get_scanned_tickers"):
            try:
                counts["ltv"] = len(ltv.get_scanned_tickers())
            except Exception:
                counts["ltv"] = 0
        bfb = self.registry.get("bull_flag_breakout")
        if bfb and hasattr(bfb, "get_scanned_tickers"):
            try:
                counts["bfb"] = len(bfb.get_scanned_tickers())
            except Exception:
                counts["bfb"] = 0
        vcp = self.registry.get("vcp_breakout")
        if vcp and hasattr(vcp, "get_scanned_tickers"):
            try:
                counts["vcp"] = len(vcp.get_scanned_tickers())
            except Exception:
                counts["vcp"] = 0
        ds = self.registry.get("donchian_swing")
        if ds and hasattr(ds, "get_scanned_tickers"):
            try:
                counts["swing"] = len(ds.get_scanned_tickers())
            except Exception:
                counts["swing"] = 0
        # positions 는 전 전략 합 (중복 가능 — 동일 종목이 두 전략 보유 시 2로 카운트)
        positions_total = 0
        for s in self.registry.all():
            try:
                positions_total += len(s.state.positions)
            except Exception:
                pass
        counts["positions"] = positions_total
        return counts

    def _build_priority_groups(
        self, momentum_tickers: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """우선순위 큐 구독용 5개 카테고리 dict 를 산출한다 (E1, 2026-05-12).

        키 (HIGH → LOW):
        - positions       : 모든 전략 보유 합집합 (dedupe). bypass_limit=True 적용 — 한도 무시 절대 보장
        - next_day_clear  : `_pending_next_day_clear` set 의 ticker (dedupe). 동일 — 절대 보장
        - swing           : `_collect_swing_tickers()` (donchian_swing 후보)
        - momentum        : `momentum_tickers` 인자 그대로 (보통 `scan_stocks()` 결과)
        - breakout        : `_collect_breakout_tickers()` (volatility_breakout + long_tail_volatility
                            + bull_flag_breakout + vcp_breakout — 사이클 48). LOW + bypass_limit=False.

        빈 카테고리도 키 자체는 항상 5개 존재 (빈 리스트). `subscribe_filtered_stocks(priority_groups=...)`
        가 받아 HIGH→LOW 순서로 구독한다. 후순위만 잔여 슬롯 초과 시 drop, HIGH 는 한도 무시.

        어제·오늘 donchian_swing 조기 손절 사건의 루트 원인(보유 종목 시세 누락) 차단.
        """
        # positions: 전 전략 합집합 — 순서 보존 dedupe (dict.fromkeys)
        position_tickers: list[str] = []
        for s in self.registry.all():
            try:
                position_tickers.extend(s.state.positions.keys())
            except Exception:
                pass
        positions = list(dict.fromkeys(position_tickers))

        # next_day_clear: (ticker, strategy_id) 튜플에서 ticker 만
        ndc_tickers = [t for (t, _sid) in self._pending_next_day_clear]
        next_day_clear = list(dict.fromkeys(ndc_tickers))

        # G안(2026-05-12): swing 키는 항상 빈 list — donchian_swing 후보는 Pull 폴링으로 평가하므로
        # WebSocket 구독 미사용. 보유 종목은 positions HIGH 그룹으로 별도 유입되어 청산 평가 보장.
        # 시그니처 호환을 위해 키 자체는 5개 모두 유지.
        momentum_list = list(momentum_tickers or [])
        breakout_list = self._collect_breakout_tickers()
        return {
            "positions": positions,
            "next_day_clear": next_day_clear,
            "swing": [],
            "momentum": momentum_list,
            "breakout": breakout_list,
        }

    async def _atomic_board_transition(
        self,
        ticker: str,
        stale_tr_id: str,
        new_tr_id: str | None,
        ack_timeout_secs: float = 2.0,
    ) -> bool:
        """종목 1개의 시세 채널 원자 전환: unsubscribe → ACK 확인 → subscribe.

        사이클 26 (2026-05-20) — 보드 전환 시 종목 단위 원자 처리.

        흐름:
        1. kis_ws_pool.unsubscribe(stale_tr_id, ticker) 호출
        2. kis_ws_pool 의 _subscriptions_acked 에서 (stale_tr_id, ticker) 제거 확인
           (polling, timeout = ack_timeout_secs)
           - timeout 도달 시 WARNING [atomic_transition_ack_timeout] + 다음 단계 강행
        3. new_tr_id 가 None 이 아니면 kis_ws_pool.subscribe(new_tr_id, ticker) 호출
        4. 50ms sleep (다음 종목 KIS 부담 회피)

        Returns:
            True = 정상 (ACK 확인 후 subscribe), False = timeout 강행
        """
        import time as _time_mod

        # (1) unsubscribe
        try:
            await kis_ws_pool.unsubscribe(stale_tr_id, ticker)
        except Exception:
            logger.warning(
                "[atomic_transition] unsubscribe 실패 (강행): ticker=%s stale=%s",
                ticker, stale_tr_id,
            )

        # (2) ACK 확인 polling
        ack_confirmed = False
        deadline = _time_mod.monotonic() + ack_timeout_secs
        poll_interval = 0.05  # 50ms

        while _time_mod.monotonic() < deadline:
            # kis_ws_pool 의 _subscriptions_acked 에서 제거 확인
            # WebsocketPool.get_acked_tickers() 합집합에서 (stale_tr_id, ticker) 부재 확인
            try:
                acked = getattr(kis_ws_pool, "_subscriptions_acked", None)
                if acked is not None:
                    if (stale_tr_id, ticker) not in acked:
                        ack_confirmed = True
                        break
                else:
                    # _subscriptions_acked 접근 불가 — fallback: 즉시 확인으로 처리
                    ack_confirmed = True
                    break
            except Exception:
                ack_confirmed = True
                break
            await asyncio.sleep(poll_interval)

        if not ack_confirmed:
            logger.warning(
                "[atomic_transition_ack_timeout] ticker=%s stale=%s timeout=%.1fs — 강행",
                ticker, stale_tr_id, ack_timeout_secs,
            )

        # (3) subscribe (new_tr_id 가 None 이면 장 종료 — subscribe 없음)
        if new_tr_id is not None:
            try:
                # 보유/익일청산 여부로 priority 결정
                priority_groups = self._build_priority_groups()
                is_high = (
                    ticker in priority_groups.get("positions", [])
                    or ticker in priority_groups.get("next_day_clear", [])
                )
                priority = "HIGH" if is_high else "LOW"
                bypass_limit = is_high

                await kis_ws_pool.subscribe(
                    new_tr_id, ticker,
                    priority=priority,
                    bypass_limit=bypass_limit,
                )
            except Exception:
                logger.warning(
                    "[atomic_transition] subscribe 실패: ticker=%s new=%s",
                    ticker, new_tr_id,
                )

        # (4) 50ms sleep (KIS 부담 회피)
        await asyncio.sleep(0.05)

        return ack_confirmed

    async def _board_transition_loop(
        self,
        stale_tr_id: str,
        new_tr_id: str | None,
        tickers: list[str],
        priority_groups: dict | None = None,
    ) -> None:
        """종목 list 를 순회하며 시세 채널 원자 전환.

        사이클 26 (2026-05-20) — 보드 전환 시 HIGH (보유/익일청산) 우선 처리.

        Args:
            stale_tr_id: 제거할 TR_ID
            new_tr_id: 새로 구독할 TR_ID. None 이면 장 종료 (unsubscribe only)
            tickers: 전환 대상 종목 list
            priority_groups: HIGH/LOW 우선순위 구분 dict (없으면 자동 산출)
        """
        import time as _time_mod

        if priority_groups is None:
            priority_groups = self._build_priority_groups()

        # HIGH: 보유 + 익일청산 (시세 끊김 위험 최소)
        high_set = set(priority_groups.get("positions", []))
        high_set.update(priority_groups.get("next_day_clear", []))
        high_tickers = [t for t in tickers if t in high_set]
        low_tickers = [t for t in tickers if t not in high_set]

        start_mono = _time_mod.monotonic()
        total = 0

        for ticker in high_tickers + low_tickers:
            await self._atomic_board_transition(ticker, stale_tr_id, new_tr_id)
            total += 1

        elapsed = _time_mod.monotonic() - start_mono
        logger.info(
            "[board_transition_complete] stale=%s new=%s count=%d elapsed=%.2fs "
            "(high=%d low=%d)",
            stale_tr_id, new_tr_id, total, elapsed, len(high_tickers), len(low_tickers),
        )

    async def _resolve_open_price(
        self, ticker: str, *, max_wait_s: float = 5.0, interval_s: float = 0.5,
    ) -> int:
        """시가를 해결한다. WebSocket 폴링 → KIS API 폴백 순서.

        WebSocket으로 ticker_prices[ticker]["open_price"]가 채워지길 max_wait_s 동안
        interval_s 간격으로 폴링한다. 시간 초과 시 KIS 개별시세 API로 폴백 조회.
        """
        from src.engine.scanner import ticker_prices

        elapsed = 0.0
        while elapsed < max_wait_s:
            price_info = ticker_prices.get(ticker)
            if price_info and price_info.get("open_price", 0) > 0:
                return int(price_info["open_price"])
            await asyncio.sleep(interval_s)
            elapsed += interval_s

        # KIS API 폴백
        try:
            from src.api.condition import fetch_stock_detail
            detail = await fetch_stock_detail(ticker)
            return int(detail.get("stck_oprc", "0"))
        except Exception:
            logger.debug("시가 KIS API 조회 실패: %s", ticker)
            return 0

    async def _force_clear_intraday_strategies(self) -> None:
        """[Backwards-compat] 호출자가 남아있을 경우 main 전용 강제 청산으로 위임."""
        await self._force_clear_main_only()

    async def _force_clear_main_only(self) -> None:
        """15:20 KRX 메인 강제 청산 — `tradable_boards`에 POST_NXT가 없는 전략의 종목만 청산.

        VB/LTV가 POST_NXT를 활성화하고 있으면 NXT 애프터까지 보유 유지. POST_NXT 미활성
        전략(또는 momentum 익일청산 후보가 아닌 당일청산 종목)만 즉시 청산한다.

        시간 가드 (2026-05-15 hot fix, 5/15 16:04 사고 대응):
            KRX 메인 마감(15:30) 이후 호출이면 즉시 skip. 재시작 시점이 15:30 이후면
            scheduler.start() 의 line 380 호출이 무조건 발동되어 VB 보유를 SOR 시장가로
            청산 시도 → KRX 애프터 시간대 APBK3013 ([애프터마켓]지정가 및 최유리/최우선
            지정가 주문만 가능합니다.) 거부 × 3회 재시도 모두 실패 + 시세 캐시 미확보로
            `step_down(가격, 5)` 폴백 불발 → CRITICAL 매도 실패. 본 가드로 차단하고
            다음 영업일 `_execute_next_day_clear` 안전망(VB 포함, 결함 D 잔여 fix) 에 위임.
        """
        now_t = datetime.now().time()
        if now_t >= TIME_KRX_MAIN_CLOSE:
            logger.info(
                "KRX 메인 마감(15:30) 이후 호출 — _force_clear_main_only skip "
                "(현재 %s, 익일 청산 안전망에 위임)",
                now_t.strftime("%H:%M:%S"),
            )
            try:
                await write_log(
                    "INFO",
                    f"_force_clear_main_only skip — 현재 {now_t.strftime('%H:%M:%S')} "
                    f"≥ 15:30 (KRX 메인 마감 후, 익일 청산 안전망 위임)",
                )
            except Exception:
                pass
            return

        from src.engine.scanner import t
        from src.engine.session import MarketBoard, get_tradable_boards

        for sid in ("volatility_breakout", "long_tail_volatility"):
            strategy = self.registry.get(sid)
            if not strategy or not strategy.config.enabled:
                continue
            if not hasattr(strategy, 'check_force_clear'):
                continue

            # 사이클 142 — 결함 #1 시정: POST_NXT 활성 여부 무관 check_force_clear() 호출.
            # 사용자 의도 (사이클 38 명세) + 자문 영속 정합:
            # - LTV.check_force_clear() 본체가 _limit_up_reached 영역 영구 영속 상한가 모드 종목 제외 영속
            # - 일반 종목 (상한가 미도달) = 15:20 즉시 청산 의무 영속
            # - VB.check_force_clear() = 전량 청산 영속 (변경 0, POST_NXT 미포함)
            # 현행 결함 = keeps_post_nxt 시 continue 분기 영역 영구 영속 → 모든 종목 보류 (의도 위반)
            clear_tickers = strategy.check_force_clear()
            if not clear_tickers:
                continue

            allowed = get_tradable_boards(sid, strategy.config.params)
            keeps_post_nxt = MarketBoard.POST_NXT in allowed
            if keeps_post_nxt:
                logger.info(
                    "%s POST_NXT 활성 — 15:20 강제 청산: %d 종목 (상한가 모드 영역 영구 영속 종목 제외)",
                    strategy.config.name, len(clear_tickers),
                )

            await write_log("INFO", f"{strategy.config.name} 15:20 강제 청산 대상: {clear_tickers}")
            for ticker in clear_tickers:
                if ticker in strategy.state.positions:
                    await self.order_engine.execute_sell(ticker, Signal.FORCE_CLEAR, sid)
                    logger.info("%s 강제 청산: %s", strategy.config.name, t(ticker))

    async def _preissue_all_tokens(self) -> None:
        """사이클 20 (2026-05-20) — 모든 매니저 토큰 사전 순차 발급.

        KIS `/oauth2/tokenP` 분당 1개 / 전역 한도 대응.
        캐시 hit 면 즉시 return. miss 면 모듈 전역 lock 안에서 60s gap 강제 직렬화.
        보조 매니저 발급 실패는 메인 흐름 보존 (try/except 흡수).
        """
        from src.auth.token import token_manager as _token_manager, get_token_manager
        from src.db import kis_quote_accounts as kqa

        # 1) 메인 매니저
        try:
            await _token_manager.get_token()
        except Exception:
            logger.exception("[boot_preissue] main 토큰 발급 실패 — 메인 흐름 보존")

        # 2) 보조 매니저 list (active=true)
        try:
            accounts = await kqa.list_accounts(active_only=True)
        except Exception:
            logger.exception("[boot_preissue] kis_quote_accounts list 실패 — 보조 skip")
            return

        for account in accounts:
            try:
                manager = await get_token_manager(account.label)
                # 캐시 hit 면 즉시 return, miss 면 lock 안에서 60s 대기
                await manager.get_token()
                logger.info("[boot_preissue] label=%s 사전 발급 완료", account.label)
            except Exception:
                logger.exception(
                    "[boot_preissue] label=%s 발급 실패 — 다음 보조로 진행",
                    account.label,
                )

    async def _boot(self) -> None:
        """시스템 기동: 토큰 갱신, 잔고 동기화 + 포지션 복구.

        사이클 51 (2026-06-01): 본체는 `src/engine/boot_manager.py::boot()` 로 이전.
        외부 import 경로(`from src.engine.scheduler import ...`) 영향 0.
        """
        from src.engine.boot_manager import boot as _boot_impl
        await _boot_impl(self)

    async def _refresh_market_regime_and_persist(self) -> None:
        """사이클 2 (2026-05-17): 매크로 fetch → 메모리 레짐 갱신 → DB snapshot INSERT.

        외부 의존성 (dkstock.cloud) 실패 시 graceful — empty regime 으로 메모리 갱신
        (매수 가드 비활성 + cash_usage_ratio 자동 조정 비활성 → 운영자 수동값 보존).

        호출 결과 무관 _boot 진행. DB INSERT 실패도 graceful (메모리 레짐 유효).
        """
        from src.engine.market_regime import (
            persist_snapshot, refresh_from_dkstock, set_current_regime,
        )

        try:
            regime = await refresh_from_dkstock()
        except Exception:
            logger.exception("[market_regime] refresh 예외 — empty 폴백")
            from src.engine.market_regime import MarketRegime
            regime = MarketRegime.empty()
        set_current_regime(regime)

        # DB snapshot INSERT — empty regime 은 persist_snapshot 내부에서 skip
        try:
            from src.engine.scanner import KST_TZ as _KST_TZ_REGIME
            await persist_snapshot(regime, datetime.now(_KST_TZ_REGIME).date())
        except Exception:
            logger.exception("[market_regime] snapshot INSERT 실패 — 메모리 레짐 유효")

        # 운영 가시성: regime + 매수가드 + 자동조정 결과 1행
        # 사이클 72 hotfix: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT
        logger.info(
            "[market_regime] regime=%s buy_blocked=%s block_reason=%s "
            "cash_min=%s computed_ratio=%s",
            regime.regime, regime.buy_blocked, regime.block_reason,
            regime.cash_min, regime.computed_cash_usage_ratio(),
        )

    async def _resolve_cash_usage_ratio(self) -> float:
        """사이클 2 (2026-05-17): `auto_regime_adjust` 토글에 따라 cash_usage_ratio 결정.

        - `auto_regime_adjust=False` (운영자 수동 모드) → `get_cash_usage_ratio()` 그대로.
        - `auto_regime_adjust=True` (기본) → 레짐 `computed_cash_usage_ratio()` 우선:
            - 산출 가능 → 자동 갱신 (`set_cash_usage_ratio` 호출, DB 저장).
            - 산출 불가 (empty regime / cash_min=None) → 수동값 폴백.
        """
        from src.db.system_config import get_auto_regime_adjust, set_cash_usage_ratio
        from src.engine.market_regime import get_current_regime

        manual_ratio = await get_cash_usage_ratio()

        try:
            auto_enabled = await get_auto_regime_adjust()
        except Exception:
            logger.exception("[auto_regime_adjust] 조회 실패 — 수동 모드 폴백")
            return manual_ratio

        if not auto_enabled:
            return manual_ratio

        regime = get_current_regime()
        computed = regime.computed_cash_usage_ratio()
        if computed is None:
            # 외부 fetch 실패 / empty regime → 운영자 수동값 보존
            return manual_ratio

        # 5% step 자동 보정은 set_cash_usage_ratio 가 책임. 음수/1초과 입력은
        # cash_usage_ratio_from_regime 가 사전 clamp 하므로 안전.
        try:
            await set_cash_usage_ratio(computed)
        except Exception:
            logger.exception(
                "[market_regime] cash_usage_ratio 자동 갱신 실패 — 메모리 적용만 진행: %s",
                computed,
            )
        # 산출값 자체를 반환 (5% 보정값보다 의도 명확)
        # set 직후 다시 get 하면 round-trip 비용 증가 — 호출자가 직접 사용.
        return computed

    async def _eager_refresh_stock_master_for_held_positions(self) -> None:
        """_boot() 후 보유 종목 + 익일청산 후보 ticker 를 stock_master 에 eager 갱신.

        Phase G(2026-05-11) 의 lazy 갱신은 캐시 miss 시 첫 사이클은 전략 기본
        exchange(SOR/NXT) 그대로 발사 → KIS 거부. 매수 진입은 매 요청마다 lazy 갱신해도
        비용이 작지만, 익일청산은 09:00 단발 발사 + 시간 압박이라 캐시 miss 가 사고로
        직결됨 (2026-05-12 계양전기 사례). _boot 시점에 미리 채워 둠.

        대상:
        - 모든 전략 보유 포지션 ticker
        - 익일청산 보류 set `_pending_next_day_clear` 의 ticker
        - 합집합 dedupe, 6자리 영숫자만 필터(`isalnum()` — 사후처리 규약)

        Rate limit 보호: sequential await (보통 10개 미만이라 parallel 불필요).
        24h TTL fresh 면 skip 으로 KIS 호출 최소화. 종목별 예외는 흡수.
        """
        from src.api.condition import inquire_stock_basics
        from src.db import stock_master

        tickers: set[str] = set()
        for strategy in self.registry.all():
            for ticker in strategy.state.positions.keys():
                if ticker and len(ticker) == 6 and ticker.isalnum():
                    tickers.add(ticker)
        for (t, _sid) in self._pending_next_day_clear:
            if t and len(t) == 6 and t.isalnum():
                tickers.add(t)

        if not tickers:
            return

        refreshed = 0
        skipped = 0
        for ticker in sorted(tickers):
            try:
                if not await stock_master.is_stale(ticker, max_age_hours=24):
                    skipped += 1
                    continue
                basics = await inquire_stock_basics(ticker)
                await stock_master.upsert_one(basics)
                refreshed += 1
            except Exception:
                logger.exception("[stock_master_eager] 갱신 실패: %s", ticker)
                # 사이클 72 hotfix: write_log 제거 — logger.exception → _DbLogHandler 위임 단일 INSERT

        logger.info(
            "[stock_master_eager] 보유+익일청산 %d종목 갱신 완료 (refreshed=%d, skipped=%d)",
            len(tickers), refreshed, skipped,
        )
        # 사이클 72 hotfix: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT

        # 멀티데이 보유 전략(donchian_swing) 보유 종목의 ATR 재계산
        ds = self.registry.get("donchian_swing")
        if ds and hasattr(ds, "recompute_held_atr"):
            try:
                await ds.recompute_held_atr()
            except Exception:
                logger.exception("donchian_swing recompute_held_atr 실패")

    async def _sync_orders_to_db(self, orders: list[dict]) -> None:
        """KIS 주문체결내역을 DB trade_history에 동기화한다.

        MTS/HTS에서 수동 매매한 건도 여기서 DB에 반영된다.
        매수/매도를 각각 독립적으로 체크하여 누락 없이 동기화.

        중복 판정은 (ticker, order_no) 페어 기준 — 같은 ticker 다른 order_no
        주문(분할 매수 / 두 번 매수 등)을 위양성 skip 하지 않는다. 2026-05-12
        005930 보완 INSERT 사고(같은 ticker 가 다른 가격/strategy 로 중복 INSERT)
        직접 원인의 다른 한 축.
        """
        # 사이클 30 (긴급, 2026-05-21) — 042700 무한 핑퐁 사고 대응.
        # `get_today_buy_trades()` (ticker dedupe) → `get_today_buy_trades_for_sync()`
        # (dedupe 없음 + CANCELLED 제외) 호출 교체. 같은 ticker 다른 order_no 정확 추적.
        # 매수 strategy 매핑은 별도 dedupe 된 `get_today_buy_trades()` 사용 (포지션 복구 시 의도).
        from src.db.trade_history import (
            get_today_buy_trades,
            get_today_buy_trades_for_sync,
            get_today_sell_trades_for_sync,
            insert_trade,
        )
        from src.models.trade import TradeRecord, TradeStatus, TradeType

        if not orders:
            return

        # 사이클 30: sync 중복 판정용 — dedupe 없음 (raw 모든 (ticker, order_no) 페어)
        existing_buys_raw = await get_today_buy_trades_for_sync()
        existing_buy_keys = {(row["ticker"], row.get("order_no", "") or "") for row in existing_buys_raw}

        existing_sells_raw = await get_today_sell_trades_for_sync()
        existing_sell_keys = {(row["ticker"], row.get("order_no", "") or "") for row in existing_sells_raw}

        # DB 매수 기록에서 strategy 매핑 (매도 시 참조) — ticker 별 1건만 필요하므로 dedupe 함수 사용
        existing_buys_for_strategy = await get_today_buy_trades()
        db_strategy_map = {row["ticker"]: row.get("strategy", "momentum") for row in existing_buys_for_strategy}

        synced = 0
        for order in orders:
            ticker = order.get("pdno", "")
            ccld_qty = int(order.get("tot_ccld_qty", "0"))
            if ccld_qty <= 0 or not ticker:
                continue

            is_buy = order.get("sll_buy_dvsn_cd") == "02"
            avg_price = int(order.get("avg_prvs", "0"))
            kis_order_no = order.get("odno", "") or ""
            key = (ticker, kis_order_no)

            if is_buy and key in existing_buy_keys:
                continue
            if not is_buy and key in existing_sell_keys:
                continue

            # 매도 시 전략/손익 매핑
            strategy = "momentum"
            profit_loss = 0.0
            if is_buy:
                strategy = db_strategy_map.get(ticker, "momentum")
            else:
                strategy = db_strategy_map.get(ticker, "momentum")
                # 보유 포지션에서 매수가 참조하여 손익 계산
                for s in self.registry.all():
                    if ticker in s.state.positions:
                        buy_price = s.state.positions[ticker].buy_price
                        profit_loss = (avg_price - buy_price) * ccld_qty
                        strategy = s.strategy_id
                        break

            from src.engine.scanner import ticker_names
            record = TradeRecord(
                ticker=ticker,
                ticker_name=ticker_names.get(ticker, order.get("prdt_name", "")),
                trade_type=TradeType.BUY if is_buy else TradeType.SELL,
                price=avg_price,
                quantity=ccld_qty,
                profit_loss=profit_loss,
                status=TradeStatus.COMPLETED,
                strategy=strategy,
                order_no=kis_order_no,
            )
            await insert_trade(record)
            if is_buy:
                existing_buy_keys.add(key)
            else:
                existing_sell_keys.add(key)
            synced += 1
            side_str = "매수" if is_buy else "매도"
            logger.info("DB 동기화: %s %s %d주 @ %d (전략: %s)", side_str, ticker, ccld_qty, avg_price, strategy)

        if synced > 0:
            logger.info("DB 동기화 완료: %d건 주문체결 내역 추가", synced)

    async def _scan_loop(self) -> None:
        """주기적으로 종목을 스캔하고 구독을 업데이트한다."""
        sync_counter = 0
        while self._running:
            await asyncio.sleep(SCAN_INTERVAL)
            if not self._running:
                break
            try:
                tickers = await scan_stocks()
                # 돌파(VB+LTV) + 모든 전략 보유 포지션 합집합으로 재구독
                # G안(2026-05-12): donchian_swing 스캔 후보는 Pull 폴링으로 매수 평가 → WS 구독 제외.
                # donchian_swing 보유 종목은 positions 합집합 경로로 그대로 유입 → 청산(ATR 트레일링/-7%) 보장.
                extra = list(set(
                    self._collect_breakout_tickers()
                    + [t for s in self.registry.all() for t in s.state.positions.keys()]
                ))
                source_counts = self._build_subscription_source_counts(momentum_tickers=tickers)
                priority_groups = self._build_priority_groups(momentum_tickers=tickers)
                # 사이클 15-A (2026-05-19) — KIS 정상 패턴 준수.
                # 기존 `unsubscribe_all()` (전체 해제) → `_delta_unsubscribe_dropped`(빠진 종목만).
                # KIS 공지 "비정상 케이스 2" (무한 등록/해제 반복) 패턴 차단.
                new_set = set(tickers) | set(extra)
                await self._delta_unsubscribe_dropped(new_set)
                await subscribe_filtered_stocks(
                    tickers, extra_tickers=extra, source_counts=source_counts,
                    priority_groups=priority_groups,
                )

                # VB/LTV 빈 _targets 자동 재 prepare 가드 (KIS 5xx 회복)
                # 07:50 _boot / 09:00:05 재 prepare 가 일시장애로 실패해 _scanned_tickers 가
                # 빈 채로 굳으면, 5분 주기 재구독은 후보가 없어 종일 시세 미수신 + 매매 휴면이 된다.
                # donchian_swing 은 고정 유니버스라 대상 아님.
                await self._reprepare_breakout_if_empty()

                # 사이클 164 (2026-06-18) — VB/LTV 시가 확정 chain 재시도 안전망.
                # 6/18 11:03 KST EC2 재기동 → prepare 11:17 완료 → _targets 등록되지만
                # 시가 확정 chain 부재로 UI "시가 대기" 영구 잔존 결함 시정.
                # `_reprepare_breakout_if_empty` 직후 = prepare 완료된 종목 영역에서 시가
                # 미확정 종목 자동 재시도. 본체 예외는 흡수 — 다음 사이클 자연 재시도.
                try:
                    await self._confirm_breakout_open_prices_if_pending()
                except Exception:
                    logger.exception(
                        "_confirm_breakout_open_prices_if_pending 실패 — "
                        "다음 사이클 자연 재시도"
                    )

                # 사이클 13-D (2026-05-18): stale 우선 재구독.
                # K stale watcher 가 120s 주기로 발화하는데 _scan_loop 는 5분 주기다.
                # 통합 구독 직후 1행으로 stale 종목을 HIGH 우선순위로 즉시 재구독해
                # 5분 주기의 자연 회복 경로를 별도 추가한다. cap=10 + 50ms sleep 으로
                # KIS Rate Limit 보호. 본체 예외는 흡수 — 다음 사이클 자연 재시도.
                try:
                    await self._resubscribe_stale_priority(cap=10)
                except Exception:
                    logger.exception("_resubscribe_stale_priority 실패 — 다음 사이클 자연 재시도")

                # 사이클 32 (R4, 2026-05-21) — universe stale 가드.
                # stale > MAX_STALE_RETRIES + 거래량 빈약 종목 자동 제외 + WebSocket unsubscribe.
                # 보유/익일청산은 사전 차단. 본체 예외는 흡수 — 다음 사이클 자연 재시도.
                try:
                    await self._evaluate_universe_guard(list(new_set))
                except Exception:
                    logger.exception("_evaluate_universe_guard 실패 — 다음 사이클 자연 재시도")

                # 사이클 149 (2026-06-16) — 종목별 H0UNMKO0 구독 확장 5분 delta hook.
                # 보유/익일청산 (HIGH) + 전략 후보 (LOW cap=20) 합집합 종목별 구독.
                # 자문 의제 2/3 (자문 채택) = 메인 세션 단일 + bypass_limit=True (HIGH) / cap=20 (LOW).
                # 본체 예외는 흡수 — 다음 사이클 자연 재시도.
                try:
                    await self._subscribe_market_operation_tickers(new_set)
                except Exception:
                    logger.exception(
                        "_subscribe_market_operation_tickers 실패 — 다음 사이클 자연 재시도"
                    )

                # 사이클 37 (2026-05-21) — KIS 실제 last_cntg_hour 캐시 갱신.
                # stale r≥2 종목 대상 inquire_ccnl 호출 + TTL 5분 + cap 20.
                # UI 에서 last_tick vs last_cntg_hour 비교로 WS 구독 문제 진단.
                # R4 와 동일 사이클에서 호출되어도 캐시 TTL 로 중복 호출 자연 차단.
                try:
                    await self._refresh_stale_ccnl_cache(list(new_set))
                except Exception:
                    logger.exception("_refresh_stale_ccnl_cache 실패 — 다음 사이클 자연 재시도")

                # 사이클 39 (2026-05-22) — 09:30 자동 funnel snapshot.
                # 첫 _scan_loop 진입 시 활성 전략의 `_funnel_steps` 단계별 row INSERT.
                # 일일 1회 가드 (`_auto_funnel_snapshot_done_today`) + 본체 예외 흡수.
                if not self._auto_funnel_snapshot_done_today:
                    try:
                        await self._auto_capture_funnel_snapshots()
                        self._auto_funnel_snapshot_done_today = True
                    except Exception:
                        logger.exception(
                            "_auto_capture_funnel_snapshots 실패 — 다음 사이클 자연 재시도"
                        )

                # Phase D: 구독 종목 중 최근 60초 내 tick 수신 비율 카운트 노출.
                # "구독은 됐으나 시세가 안 들어오는 종목"을 운영자가 즉시 인지하도록 1행 로그.
                # 2026-05-11 VB/LTV 종일 시세 무수신 사고 가시성 결함 보완.
                await self._report_tick_coverage()
            except Exception:
                logger.exception("종목 스캔 오류")

            # 체결통보 못 받았을 때를 대비한 포지션 동기화 (3회 스캔마다 = 15분)
            sync_counter += 1
            if sync_counter % 3 == 0:
                try:
                    await self._sync_positions_from_balance()
                except Exception:
                    logger.debug("포지션 동기화 실패")

    async def _confirm_breakout_open_prices_if_pending(self) -> None:
        """사이클 164 (2026-06-18) — VB/LTV 시가 확정 chain 재시도 안전망.

        근본 원인 (6/18 11:03 KST EC2 재기동 사례):
        - 09:00:05 KST 정상 시가 확정 후 11:03 EC2 재기동
        - run_daily 재진입 시 `now > TIME_KRX_OPEN_CONFIRM` 분기에서 L640
          `_confirm_breakout_open_prices()` 호출되지만, prepare 미완료라 `_targets`
          비어 silent skip (L1413 `if not targets: return`)
        - 이후 prepare 완료되어도 시가 확정 재시도 chain 부재 → UI "시가 대기" 영구 잔존

        시정 영역:
        - `_targets` 에 종목 1개 이상 존재 AND 활성 보드에서 `_open_confirmed` 미확정
          종목 1개 이상 시 → `_confirm_breakout_open_prices(board=active_board)` 재시도
        - 모든 종목 confirmed → silent skip (idempotent, 호출 0건)
        - prepare 미완료 (`_targets` 빈 dict) → 다른 영역 (`_reprepare_breakout_if_empty`) 담당
        - 예외 graceful — 다음 사이클 자연 재시도 영속

        영속 의무:
        - 사이클 26 VB MAIN 단독 + 사이클 38 LTV 3보드 영속
        - 사이클 88 G-REJECT graceful 영속
        - 사이클 38 명문화 영속 — 매수 진입 *전* 영역 한정 + 매도/익일청산 hot path 무관
        """
        from src.engine.session import session_tracker, MarketBoard
        from datetime import datetime as _dt, time as _t

        # 활성 보드 결정 — SessionTracker 위임 + 시각 기반 fallback
        # (`_confirm_breakout_open_prices` 영속 패턴 답습, L1382~L1397)
        active = session_tracker.active
        active_board: str | None = None
        for candidate in ("main", "post_nxt", "pre_nxt"):
            try:
                if MarketBoard(candidate) in active:
                    active_board = candidate
                    break
            except Exception:
                continue
        if active_board is None:
            now_t = _dt.now().time()
            if now_t < _t(9, 0):
                active_board = "pre_nxt"
            elif now_t < _t(15, 30):
                active_board = "main"
            else:
                active_board = "post_nxt"

        # VB + LTV 합집합 — 한쪽이라도 미확정 종목 존재 시 재시도
        for sid in ("volatility_breakout", "long_tail_volatility"):
            strategy = self.registry.get(sid)
            if strategy is None or not strategy.config.enabled:
                continue
            targets = getattr(strategy, "_targets", None) or {}
            if not targets:
                # prepare 미완료 — `_reprepare_breakout_if_empty` 담당
                continue
            open_confirmed = getattr(strategy, "_open_confirmed", None) or {}

            unconfirmed = [
                ticker
                for ticker in targets.keys()
                if not open_confirmed.get(ticker, {}).get(active_board, False)
            ]
            if not unconfirmed:
                # 모든 종목 confirmed — idempotent skip
                continue

            logger.info(
                "[open_confirm_retry] strategy=%s board=%s unconfirmed=%d/%d — 재시도",
                sid, active_board, len(unconfirmed), len(targets),
            )
            try:
                await self._confirm_breakout_open_prices(board=active_board)
            except Exception:
                logger.exception(
                    "_confirm_breakout_open_prices_if_pending 재시도 실패 — "
                    "다음 사이클 자연 재시도 (strategy=%s)", sid,
                )

    async def _reprepare_breakout_if_empty(self) -> None:
        """VB/LTV/BFB/VCP 의 `_scanned_tickers` 가 비어있으면 prepare() 를 1회 재시도한다.

        - 매 _scan_loop 사이클 1회 발화 (성공/실패 무관하게 다음 5분 사이클에 자연 재시도)
        - donchian_swing 은 대상 아님 (고정 유니버스이므로 prepare 실패해도 KOSPI200/KOSDAQ150 사용)
        - prepare() 가 raise 해도 가드 본체는 예외를 흡수하여 _scan_loop sleep/cancel 흐름을 보존한다
        - 사이클 48 (2026-05-27): bull_flag_breakout / vcp_breakout 추가 — boot 실패/일시 API
          오류 회복용 안전망 (주 메커니즘은 prdy 기반 시간무관 유니버스). 후보가 비었을 때만
          호출되므로 KIS rate limit 부담 미미 (전략당 5분 1회)
        """
        for sid in ("volatility_breakout", "long_tail_volatility",
                    "bull_flag_breakout", "vcp_breakout"):
            strategy = self.registry.get(sid)
            if strategy is None or not strategy.config.enabled:
                continue
            if not hasattr(strategy, "get_scanned_tickers"):
                continue
            try:
                scanned = strategy.get_scanned_tickers()
            except Exception:
                logger.exception("get_scanned_tickers 실패: %s", sid)
                continue
            if scanned:
                continue

            # getattr 폴백 = __init__ 우회 스텁 인스턴스 호환 (사이클 56-D AttributeError 가드 답습)
            _reprepare_cap = getattr(self, "_reprepare_empty_logged_today", None)
            if _reprepare_cap is None or _reprepare_cap.should_emit(sid):
                logger.warning("스캔 후보 비어있음 — 재 prepare 시도: %s", sid)
                try:
                    await write_log("WARNING", f"{sid} 후보 비어있음 — 재 prepare 시도")
                except Exception:
                    logger.debug("write_log WARNING 실패: %s", sid)
                if _reprepare_cap is not None:
                    _reprepare_cap.mark_emitted(sid)

            try:
                await strategy.prepare()
            except Exception:
                logger.exception("재 prepare 실패: %s", sid)
                try:
                    await write_log("ERROR", f"{sid} 재 prepare 실패")
                except Exception:
                    logger.debug("write_log ERROR 실패: %s", sid)

    async def _swing_buy_poll_loop(self) -> None:
        """donchian_swing — 09:05~09:30 KST 1분 주기 매수 평가 폴링 (G안, 2026-05-12).

        donchian_swing 은 일봉 전략이라 실시간 tick 평가가 구조적 낭비.
        WebSocket 구독을 끊고(작업 2-1) 1분 주기 KIS REST(`fetch_stock_detail`)로 매수 평가.
        보유 종목 청산(ATR 트레일링/하드 -7%)은 `risk.on_tick` 의 `check_exit_signal` 분기 그대로.

        - 09:05 이전: 1초 폴링하며 대기
        - 09:30 초과: task 종료
        - 매 사이클: candidate 종목별 sequential await (KIS Rate Limit 20/s 보호)
        - 본체 예외는 ERROR 로그 흡수, 다음 사이클 자연 재시도
        - `[swing_poll] candidates=N filtered=M bought=K elapsed=T.Ts` INFO 로그 1행
        - sleep 은 1초 단위로 쪼개 `_running=False` 즉시 반응
        """
        from datetime import time as _time, datetime as _datetime, timedelta as _timedelta
        from src.api.condition import fetch_stock_detail
        from src.engine.scanner import KST_TZ as _KST, TICK_TR_ID as _TICK_TR_ID, kis_ws as _kis_ws
        from src.engine.strategy_base import Signal as _Signal

        BUY_WINDOW_START = _time(9, 5)
        BUY_WINDOW_END = _time(9, 30)

        async def _sleep_chunked(total_secs: float, *, chunk_secs: float = 1.0) -> None:
            """`_running=False` 즉시 반응 위해 chunk 단위로 쪼갠 sleep.

            기본 1초 chunk(매분 sleep 등 짧은 간격용). 09:05 이전 장시간 대기는
            chunk_secs=2.0 으로 호출 (Codex 추가검토 3, 2026-05-12) — _running=False
            반응 지연 ≤2s 로 절제하면서 매초 wake-up 결함 차단.
            """
            remaining = total_secs
            while remaining > 0 and self._running:
                chunk = min(chunk_secs, remaining)
                await asyncio.sleep(chunk)
                remaining -= chunk

        while self._running:
            # 시간 가드: 09:30 이후 task 종료 (KST aware — UTC 서버 환경 일관성)
            now_dt = _datetime.now(_KST)
            now_t = now_dt.time()
            if now_t > BUY_WINDOW_END:
                logger.info("[swing_poll] window closed (after 09:30)")
                return
            # 09:05 이전: chunked sleep (Codex 추가검토 3, 2026-05-12)
            # 결함: 매초 wake-up → 07:50 시작 시 4400회+ 불필요 wake-up.
            # 09:05 까지 남은 초 만큼 chunked(_running=False 즉시 반응 보장),
            # 60s cap 으로 시간 가드 재진입 빈도 유지(시계 변경/sleep 누적 오차 보호).
            if now_t < BUY_WINDOW_START:
                target_dt = now_dt.replace(hour=9, minute=5, second=0, microsecond=0)
                if target_dt < now_dt:  # 자정 넘김 가드 (매수 윈도우는 항상 같은 영업일이지만 방어)
                    target_dt += _timedelta(days=1)
                remaining_s = (target_dt - now_dt).total_seconds()
                # chunk_secs=2.0 — _running=False 반응 지연 ≤2s 로 절제하면서 매초 wake-up 차단.
                await _sleep_chunked(min(60.0, max(remaining_s, 1.0)), chunk_secs=2.0)
                continue

            cycle_start = _time_mod.time()
            strategy = self.registry.get("donchian_swing")
            if strategy is None or not strategy.config.enabled:
                # 비활성 — 1분 대기 후 시간 가드 재진입 (`_running=False` 즉시 반응)
                logger.debug("[swing_poll] donchian_swing not enabled — sleep 60s")
                await _sleep_chunked(60.0)
                continue

            try:
                candidates = list(strategy.get_scanned_tickers())
            except Exception:
                logger.exception("[swing_poll] get_scanned_tickers 실패")
                candidates = []

            filtered: list[str] = []
            for t in candidates:
                # _bought_today: 같은 종목 중복 진입 차단
                if t in getattr(strategy, "_bought_today", set()):
                    continue
                # 전략 간 통합 중복 가드: 보유 / 주문중 / 당일매도
                try:
                    if self.registry.is_ticker_blocked_for_buy(t):
                        continue
                except Exception:
                    logger.debug("[swing_poll] is_ticker_blocked_for_buy 실패: %s", t, exc_info=True)
                    continue
                filtered.append(t)

            bought = 0
            for t in filtered:
                if not self._running:
                    break
                try:
                    detail = await fetch_stock_detail(t)
                except Exception:
                    logger.debug("[swing_poll] fetch_stock_detail 실패: %s", t, exc_info=True)
                    continue
                try:
                    current_price = int(detail.get("stck_prpr") or 0)
                    open_price = int(detail.get("stck_oprc") or 0)
                except (ValueError, TypeError):
                    continue
                if current_price <= 0 or open_price <= 0:
                    # 시가/현재가 0 — KIS 응답 미완성. skip
                    continue

                try:
                    signal = strategy.check_buy_signal(t, current_price, open_price)
                except Exception:
                    logger.exception("[swing_poll] check_buy_signal 실패: %s", t)
                    continue

                if signal == _Signal.BUY:
                    # PR-A (2026-05-13): swing pull BUY 신호 시 퍼널 카운터 증가.
                    # 결함: PR #1 swing pull 분리 후 risk.on_tick 의 donchian 매수 평가가 skip
                    # 되어 `signal_count_today` 가 0 으로 잔존 → metrics.strategy_funnel
                    # `signals=0 orders=1 fills=1` 비정합 (2026-05-13 운영 metrics).
                    # `risk.py:on_tick` 의 동일 카운터 증가 규약과 짝.
                    strategy.state.signal_count_today += 1
                    # Codex 추가검토 1 (2026-05-12): 매수 *성공* 시에만 WS subscribe.
                    # 결함: 기존 코드는 execute_buy raise 후에도 subscribe 호출 →
                    # 매수 실패 종목까지 HIGH bypass 슬롯 점유 → MAX_SUBSCRIPTIONS=41 압박.
                    # 매수 성공 판정 = raise 없이 return + ticker 가
                    # (a) `pending_buys` 등록(place_order 응답 후 동기 등록) 또는
                    # (b) `positions` 등록(즉시 체결로 pending_buys 비워진 race)
                    buy_succeeded = False
                    try:
                        await self.order_engine.execute_buy(t, current_price, strategy)
                        buy_succeeded = (
                            t in strategy.state.pending_buys
                            or t in strategy.state.positions
                        )
                        if buy_succeeded:
                            bought += 1
                    except Exception:
                        logger.exception("[swing_poll] execute_buy 실패: %s", t)
                    if buy_succeeded:
                        # 안전 불변식: donchian_swing 보유 종목 ATR 트레일링/-7% 하드 손절 평가 필수.
                        # 다음 5분 _scan_loop 통합 구독까지 시세 무수신 구간 차단.
                        # `bypass_limit=True` — positions HIGH 절대 보장 규약과 동일.
                        try:
                            await _kis_ws.subscribe(_TICK_TR_ID, t, bypass_limit=True)
                        except Exception:
                            logger.debug(
                                "[swing_poll] 매수 직후 시세 구독 실패: %s (다음 _scan_loop 5분 사이클에서 회복)",
                                t, exc_info=True,
                            )

                # KIS Rate Limit 보호 — 종목간 50ms 간격
                await asyncio.sleep(0.05)

            elapsed = _time_mod.time() - cycle_start
            logger.info(
                "[swing_poll] candidates=%d filtered=%d bought=%d elapsed=%.1fs",
                len(candidates), len(filtered), bought, elapsed,
            )

            # 다음 분 정각까지 sleep — `_running=False` 즉시 반응 위해 chunked (KST 일관성)
            now_dt = _datetime.now(_KST)
            sleep_secs = 60 - (now_dt.second + now_dt.microsecond / 1_000_000)
            await _sleep_chunked(max(sleep_secs, 1.0))

    async def _run_swing_rest_poll_once(self) -> dict:
        """donchian_swing 일중 시세 REST 폴링 1사이클 (B, 2026-05-15, 결함 B).

        대상: `_scanned_tickers` ∪ `state.positions` ∪ `state.pending_buys`
        동작: `fetch_stock_detail` 로 KIS 단건 시세 조회 → `scanner.ticker_prices`
              갱신 + `ticker_last_tick` touch + `ticker_names` 보강. 보유 종목 한정
              `RiskManager.on_tick` 호출 → 기존 트레일링/하드 손절 평가 경로 재사용.
        예외: 종목별 try/except 로 격리 (다음 종목 진행). 본체 raise 없음.
        Returns:
            stats dict — `candidates/held/pending/updated/failed/elapsed_ms`
        """
        from src.engine.scanner import (
            KST_TZ as _KST,
            ticker_last_tick as _last_tick,
            ticker_names as _names,
            ticker_prices as _prices,
        )

        ds = self.registry.get("donchian_swing")
        if ds is None or not ds.config.enabled:
            return {"candidates": 0, "held": 0, "pending": 0, "updated": 0, "failed": 0, "elapsed_ms": 0}

        # 대상 ticker 합집합 — 6자리 영숫자 필터 + dedupe (입력 순서 보존)
        candidates = list(getattr(ds, "_scanned_tickers", []) or [])
        held = list(ds.state.positions.keys())
        pending = list(ds.state.pending_buys)
        held_set = set(held)
        seen: set[str] = set()
        all_tickers: list[str] = []
        for t in candidates + held + pending:
            if t in seen:
                continue
            if not (len(t) == 6 and t.isalnum()):
                continue
            seen.add(t)
            all_tickers.append(t)

        cycle_start = _time_mod.monotonic()
        updated = 0
        failed = 0

        for ticker in all_tickers:
            if not self._running:
                break
            try:
                detail = await fetch_stock_detail(ticker)
            except Exception:
                failed += 1
                logger.debug("[swing_rest_poll] fetch 실패: %s", ticker, exc_info=True)
                await asyncio.sleep(SWING_REST_POLL_TICKER_SLEEP_SECS)
                continue

            try:
                current = int(detail.get("stck_prpr", "0") or 0)
                open_p = int(detail.get("stck_oprc", "0") or 0)
                prdy_ctrt = float(detail.get("prdy_ctrt", "0") or 0)
            except (ValueError, TypeError):
                failed += 1
                await asyncio.sleep(SWING_REST_POLL_TICKER_SLEEP_SECS)
                continue

            if current <= 0:
                failed += 1
                await asyncio.sleep(SWING_REST_POLL_TICKER_SLEEP_SECS)
                continue

            # change_rate 는 시가 대비 (risk.on_tick 시그니처와 호환). open_p<=0 폴백 0.0.
            change_rate = round((current - open_p) / open_p * 100, 2) if open_p > 0 else 0.0
            _prices[ticker] = {
                "current_price": current,
                "open_price": open_p,
                "change_rate": change_rate,
                "prdy_ctrt": prdy_ctrt,
            }
            _last_tick[ticker] = datetime.now(_KST)

            # 종목명 보강 — UI "최종 후보" 빈칸 표시 복구
            name = (detail.get("hts_kor_isnm") or "").strip()
            if name and not _names.get(ticker):
                _names[ticker] = name

            updated += 1

            # 보유 종목만 risk.on_tick 호출 — 기존 트레일링/하드 손절 평가 재사용.
            # candidates/pending 은 매수 평가 대상 아님 (매수는 `_swing_buy_poll_loop` 09:05~09:30 전용).
            if ticker in held_set:
                try:
                    await self.risk_manager.on_tick(ticker, current, open_p, change_rate)
                except Exception:
                    logger.exception("[swing_rest_poll] on_tick 실패: %s", ticker)

            await asyncio.sleep(SWING_REST_POLL_TICKER_SLEEP_SECS)

        elapsed_ms = int((_time_mod.monotonic() - cycle_start) * 1000)
        stats = {
            "candidates": len(candidates),
            "held": len(held),
            "pending": len(pending),
            "updated": updated,
            "failed": failed,
            "elapsed_ms": elapsed_ms,
        }
        # 사이클 74 옵션 C aggregation: [swing_rest_poll] INFO → 5분 collector 흡수
        # 직접 logger.info("[swing_rest_poll] ...") 제거 → record_swing_rest_poll 위임
        record_swing_rest_poll(stats)
        # _DbLogHandler 위임 단일 INSERT — write_log 직접 호출 제거 (사이클 73 S-1)
        return stats

    async def _swing_rest_poll_loop(self) -> None:
        """donchian_swing 일중 시세 REST 폴링 loop — 09:30~15:20 KRX 메인, 60s 주기.

        WebSocket stale 시에도 보유 종목의 ATR×2 트레일링/하드 -7% 손절 평가가
        끊기지 않도록 보강. WS 정상이면 멱등 갱신, stale 이면 메꿈.

        - 09:30 이전 / 15:20 이후: chunked sleep 으로 시간 가드 대기
        - 매 사이클: `_run_swing_rest_poll_once()` 호출 + 60s sleep (chunked, `_running=False` 반응)
        - 본체 예외는 ERROR 로그로 흡수, 다음 사이클 자연 재시도
        - `_swing_buy_poll_loop` 와 동시 운영 — 매수(09:05~09:30) 와 시세 보강(09:30~15:20)
          시간 윈도우가 분리되어 충돌 없음
        """
        async def _sleep_chunked(total_secs: float, *, chunk_secs: float = 2.0) -> None:
            remaining = total_secs
            while remaining > 0 and self._running:
                chunk = min(chunk_secs, remaining)
                await asyncio.sleep(chunk)
                remaining -= chunk

        while self._running:
            now_t = datetime.now().time()
            if now_t < SWING_REST_POLL_WINDOW_START or now_t > SWING_REST_POLL_WINDOW_END:
                # 윈도우 외 — 60s 단위로 시간 가드 재진입 (_running=False 즉시 반응)
                await _sleep_chunked(min(60.0, float(SWING_REST_POLL_INTERVAL_SECS)))
                continue

            try:
                await self._run_swing_rest_poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[swing_rest_poll] loop 사이클 실패 — 다음 사이클 자연 재시도")

            await _sleep_chunked(float(SWING_REST_POLL_INTERVAL_SECS))

    async def _stale_watcher_loop(self) -> None:
        """120s 주기 stale 감지 + 자동 재구독 + 세션 단위 silent inactive 감지 (K, 2026-05-12).

        KIS WebSocket silent inactive(구독은 됐는데 시세 송신 없음) 즉시 복구.
        F1(재연결 직후 1회) + `_scan_loop`(5분 주기) + K(120s) 3중 안전망.

        사이클 24 (2026-05-20) — 세션 단위 silent inactive 감지 + 강제 reconnect 추가:
        종목별 unsubscribe+subscribe 재등록으로 회복 안 되는 세션 자체 결함을 5분 지속 후
        `_force_reconnect_session(label)` 으로 처리. 시간당 2회 cap.

        - 매 사이클 `_check_and_resubscribe_stale()` 호출 후 silent inactive 감지
        - 본체 예외는 ERROR 로그로 흡수 — 다음 사이클 정상 진행
        - `_running=False` 진입 시 즉시 break
        - 좀비 task 방지: `start()` finally 블록에서 cancel + await
        """
        while self._running:
            await asyncio.sleep(STALE_WATCHER_INTERVAL_SECS)
            if not self._running:
                break
            try:
                await self._check_and_resubscribe_stale()
            except Exception:
                logger.exception("[stale_watcher] 사이클 실패")

            # 사이클 24 (2026-05-20) — 세션 단위 silent inactive 감지 + 강제 reconnect
            try:
                silent_labels = self._detect_silent_inactive_sessions()
                for label in silent_labels:
                    await self._force_reconnect_session(label)
            except Exception:
                logger.exception("[silent_inactive_detect] 실패 — 다음 사이클 자연 재시도")

    async def _5xx_dedupe_summary_loop(self) -> None:
        """사이클 18 (2026-05-19) — 5xx WARNING dedupe summary 60s 주기 task.

        `src/api/base.py::_record_5xx_for_dedupe` 가 동일 (path, label, status) 키 60s 윈도우 내
        재발생 시 첫 1회만 WARNING + 나머지 카운트만 누적. 본 task 가 60s 주기로
        `_emit_5xx_dedupe_summary` 호출 → 만료된 카운트 ≥ 2 인 키를 1행 INFO summary 출력.

        - 윈도우 만료 키는 모두 dedupe state 에서 제거 (count 무관) — 다음 발생은 새 WARNING
        - 본체 예외는 ERROR 로그로 흡수 — 다음 사이클 정상 진행
        - `_running=False` 진입 시 즉시 break
        - 좀비 task 방지: `start()` finally 블록에서 cancel + await
        """
        from src.api.base import _QUOTE_5XX_DEDUPE_WINDOW, _emit_5xx_dedupe_summary

        while self._running:
            await asyncio.sleep(_QUOTE_5XX_DEDUPE_WINDOW)
            if not self._running:
                break
            try:
                await _emit_5xx_dedupe_summary()
            except Exception:
                logger.exception("[5xx_dedupe_summary] 사이클 실패")

    async def _api_recovered_collector_loop(self) -> None:
        """사이클 76 (2026-06-08) — [api_retry_recovered] 5분 collector flush task.

        `_record_api_recovered` / `_record_quote_recovered` 가 `_request` / `_request_via_quote_pool`
        retry 성공 시 5분 윈도우 누적 → flush 시 `[api_retry_recovered_summary]` 1행 emit.
        사이클 18 `_5xx_dedupe_summary_loop` 패턴 답습 (60s → 300s 주기).
        Q2: 빈 윈도우 skip (헬퍼 내부 처리). Q4: 메인 + 풀 각각 별도 flush.
        """
        from src.api.base import (
            _API_RECOVERED_COLLECTOR_WINDOW,
            _flush_api_recovered_collector,
            _flush_quote_recovered_collector,
        )

        from src.engine.stale_watcher_core import flush_stale_watcher_collector

        while self._running:
            await asyncio.sleep(_API_RECOVERED_COLLECTOR_WINDOW)
            # `if not self._running: break` 가드 제거 — flush 는 _running=False 후에도
            # 최종 1회 실행 보장 (잔존 카운터 손실 방지, 사이클 78 hotfix 의도)
            try:
                await _flush_api_recovered_collector()
            except Exception:
                logger.exception("[api_recovered_collector] 메인 flush 실패")
            try:
                await _flush_quote_recovered_collector()
            except Exception:
                logger.exception("[api_recovered_collector] 풀 flush 실패")
            # 사이클 78 hotfix: 사이클 74 도입 누락 (flush 호출 사이트 0건, 메모리 leak HIGH) 시정
            try:
                flush_swing_rest_poll_collector()
            except Exception:
                logger.exception("[swing_rest_poll_collector] flush 실패")
            try:
                flush_stale_watcher_collector()
            except Exception:
                logger.exception("[stale_watcher_collector] flush 실패")
            # 사이클 102 (2026-06-11) — dispatch silent drop 가시화 flush (사이클 78 패턴 답습)
            try:
                flush_silent_drop_count()
            except Exception:
                logger.exception("[dispatch_drop_collector] flush 실패")
            if not self._running:
                break

    async def _scan_pool_eager_refresh_loop(self) -> None:
        """사이클 83 (2026-06-09) — _scan_loop 후보 풀 ticker stock_master 5분 eager refresh task.

        `subscribe_filtered_stocks` 진입점 hook (Q1=B) 이 5분 윈도우 누적한
        후보 ticker 를 순차적으로 stock_master upsert.
        - 24h TTL fresh skip (Q3=B) → KIS 호출 최소화
        - ticker 간 50ms sleep (Q3=B) → Rate Limit 20/s 보호
        - 사이클 42 `_heartbeat_metrics_loop` 5분 주기 패턴 답습
        - 사이클 78 flush 전 `_running` 재검사 패턴 답습 (마지막 1회 flush 보장)
        """
        from src.engine.scanner import (
            _scan_pool_eager_refresh_loop as _scanner_eager_refresh,
            flush_scan_pool_eager_refresh_collector,
            _SCAN_POOL_EAGER_REFRESH_WINDOW_SECS,
        )

        while self._running:
            await asyncio.sleep(_SCAN_POOL_EAGER_REFRESH_WINDOW_SECS)
            try:
                await _scanner_eager_refresh()
            except Exception:
                logger.exception("[scan_pool_eager_refresh] refresh 실패")
            try:
                flush_scan_pool_eager_refresh_collector()
            except Exception:
                logger.exception("[scan_pool_eager_refresh_collector] flush 실패")
            if not self._running:
                break

    async def _full_universe_load_task_loop(self) -> None:
        """사이클 101 + 사이클 106 + 사이클 134 (2026-06-15) — 매일 20:00:05 전체 유니버스 일괄 적재 task facade.

        사이클 134 카드 #21 영속: `run_periodic_task_loop` 헬퍼 위임 (사이클 67 facade 답습).
        lifecycle 영역 영구 영속 = 헬퍼 영역 영구 영속에서 흡수 (사이클 106 race 차단 + 사이클 88 graceful).

        영속 의무 매트릭스:
        - 사이클 79 G-AST2 영속 (task_attrs 4 위치 영속)
        - 사이클 78 G-AST1 영속 (record + flush 호출 사이트 영속 = 헬퍼 영역 영구 영속 내부)
        - 사이클 101 idempotency (24h TTL fresh skip)
        - 사이클 106 lifecycle race 차단 패턴 영속
        """
        from src.engine.scanner import _full_universe_load_once as _load_once
        from src.engine.stock_master_metrics import (
            record_full_universe_load_summary,
            flush_full_universe_load_collector,
        )
        from src.engine.task_loop_helper import run_periodic_task_loop

        await run_periodic_task_loop(
            scheduler=self,
            task_label="full_universe_load",
            wait_time=TIME_FULL_UNIVERSE_LOAD,  # 20:00:05
            once_callable=_load_once,
            record_fn=record_full_universe_load_summary,
            flush_fn=flush_full_universe_load_collector,
            summary_log_format=(
                "[full_universe_load_summary] total=%d kospi=%d kosdaq=%d "
                "fetched=%d skipped_ttl=%d failed=%d elapsed_ms=%d"
            ),
            summary_keys=(
                "total", "kospi", "kosdaq",
                "fetched", "skipped_ttl", "failed", "elapsed_ms",
            ),
            # 사이클 158 Q3 stagger — 가장 무거운 task = 즉시 발화 (0초)
            initial_delay_secs=0,
        )

    async def _stock_master_daily_load_task_loop(self) -> None:
        """사이클 122 + 사이클 134 (2026-06-15) — 매일 16:00 KST KIS 일봉 적재 task facade.

        사이클 134 카드 #21 영속: `run_periodic_task_loop` 헬퍼 위임 (사이클 67 facade 답습).

        영속 의무 매트릭스:
        - 사이클 14 fetch_daily_candles 재사용 (신규 KIS API 도입 0건)
        - 사이클 17 OPSP0002 backoff 안전 마진
        - 사이클 38 명문화 (scanner 영역 = 매수 진입 전, 매도 hot path 무관)
        - 사이클 79 G-AST2 영속 (task_attrs 4 위치 영속)
        - 사이클 88 G-REJECT graceful 단위 = 헬퍼 영역 영구 영속 내부
        - 사이클 106 lifecycle race 차단 = 헬퍼 영역 영구 영속 내부
        """
        from src.engine.scanner import _stock_master_daily_load_once
        from src.engine.stock_master_daily_metrics import (
            record_stock_master_daily_load,
            flush_stock_master_daily_load_collector,
        )
        from src.engine.task_loop_helper import run_periodic_task_loop

        await run_periodic_task_loop(
            scheduler=self,
            task_label="stock_master_daily_load",
            wait_time=TIME_STOCK_MASTER_DAILY_LOAD,  # 16:00 KST
            once_callable=_stock_master_daily_load_once,
            record_fn=record_stock_master_daily_load,
            flush_fn=flush_stock_master_daily_load_collector,
            summary_log_format=(
                "[stock_master_daily_load_summary] total=%d fetched=%d upserted_rows=%d "
                "skipped_fresh=%d failed=%d elapsed_ms=%d mode=%s"
            ),
            summary_keys=(
                "total", "fetched", "upserted_rows",
                "skipped_fresh", "failed", "elapsed_ms", "mode",
            ),
            # 사이클 159 stagger 임계 상향 (refactor-expert 자문 옵션 C)
            # = full_universe 처리 (~280s) 완료 *직후* 진입 = 0 overlap
            initial_delay_secs=240,
        )

    async def _stock_master_basics_refresh_task_loop(self) -> None:
        """사이클 126 (2026-06-13) — 매일 16:10 KST KIS CTPF1002R 매스 보강 task.

        KRX 1차 폴백 영역의 NXT/정지/관리종목 하드코딩 False 결함 시정:
        - KIS CTPF1002R 호출 (사이클 107 raw 보강 영속)
        - stock_master.upsert_one (사이클 84 history trigger 영속)

        lifecycle (사이클 122 일봉 task 100% 답습):
        - start() 직후 즉시 1회 실행 → 빠른 운영 가시화 + lifecycle race 영구 차단
        - while 루프 _wait_until(16:10:00) 무한 루프 + asyncio.sleep(60) 안전 마진
        - stop() task_attrs 튜플에 _stock_master_basics_refresh_task 포함 (사이클 79 답습)

        emit (사이클 74/101/122 collector 패턴 답습):
        - [stock_master_basics_refresh_summary] — 적재 완료 후 1행 INFO

        영속 의무:
        - 사이클 17 KIS LMS chain 안전 마진 (50ms sleep)
        - 사이클 38 명문화 (scanner 영역 = 매수 진입 전, 매도 hot path 무관)
        - 사이클 88 G-REJECT graceful 단위
        - 사이클 106 lifecycle race 차단
        - 사이클 107 CTPF1002R + FHKST01010100 merge 영속
        """
        from src.engine.scanner import _stock_master_basics_refresh_once
        from src.engine.stock_master_basics_metrics import (
            record_stock_master_basics_refresh,
            flush_stock_master_basics_refresh_collector,
        )
        from src.engine.task_loop_helper import run_periodic_task_loop

        await run_periodic_task_loop(
            scheduler=self,
            task_label="stock_master_basics_refresh",
            wait_time=TIME_STOCK_MASTER_BASICS_REFRESH,  # 16:10 KST
            once_callable=_stock_master_basics_refresh_once,
            record_fn=record_stock_master_basics_refresh,
            flush_fn=flush_stock_master_basics_refresh_collector,
            summary_log_format=(
                "[stock_master_basics_refresh_summary] total=%d updated=%d "
                "skipped=%d failed=%d elapsed_ms=%d"
            ),
            summary_keys=(
                "total", "updated", "skipped", "failed", "elapsed_ms",
            ),
            # 사이클 159 stagger 임계 상향 (refactor-expert 자문 옵션 C)
            # = full_universe 280s 처리 시간 정합 + 30s overlap 허용
            # 운영 실측 06-17 = master_skip 992 / basics_skip 1958 / 24h 폭주 영역 시정
            initial_delay_secs=480,
        )

    async def _stock_master_master_load_task_loop(self) -> None:
        """사이클 129 (2026-06-13) — 매일 16:30 KST KIS 종목 마스터 파일 적재 task.

        KIS 정본 (kis-mcp-query 검증 영구 영속):
        - KOSPI master = kospi_code.mst.zip (cp949, 후미 228 byte, part2 70 컬럼)
        - KOSDAQ master = kosdaq_code.mst.zip (cp949, 후미 222 byte, part2 64 컬럼)

        사용자 결정 영구 영속:
        - Q4=A 마스터 우선 + Q5=C 전수 보존 + Q6=C master_raw 별도 컬럼
        - Q12 시정: 시총 환산 × 100 (사용자 verbatim 정합)

        lifecycle (사이클 122/126 task 100% 답습):
        - start() 직후 즉시 1회 실행 → 빠른 운영 가시화 + lifecycle race 영구 차단
        - while 루프 _wait_until(16:30:00) 무한 루프 + asyncio.sleep(60) 안전 마진
        - stop() task_attrs 튜플에 _stock_master_master_load_task 포함 (사이클 79 G-AST2 영속)

        emit (사이클 122 collector 패턴 답습):
        - [stock_master_master_load_summary] — 적재 완료 후 1행 INFO

        영속 의무:
        - 사이클 17 KIS LMS chain 안전 (50ms sleep 영역 영속, kis_master.py 영역)
        - 사이클 38 명문화 (scanner 영역 = 매수 진입 전, 매도 hot path 무관)
        - 사이클 81 G-AST1 영속 (master_raw 별도 컬럼 = raw 변경 0)
        - 사이클 88 G-REJECT graceful (KOSPI 또는 KOSDAQ 단독 실패 → 다른 쪽 계속)
        - 사이클 106 lifecycle race 차단
        - 사이클 127 fire-and-forget + refresh_progress 영속
        - domain-consult 의제 5 옵션 A 채택 (16:30 KST 단일 task + 17시간 lag 명시 수용)
        """
        from src.engine.scanner import _stock_master_master_load_once
        # 사이클 133 — master metrics collector 통합 영속 (카드 #24 일관성 결함 해소)
        from src.engine.stock_master_master_metrics import (
            record_stock_master_master_load,
            flush_stock_master_master_load_collector,
        )
        from src.engine.task_loop_helper import run_periodic_task_loop

        await run_periodic_task_loop(
            scheduler=self,
            task_label="stock_master_master_load",
            wait_time=TIME_STOCK_MASTER_MASTER_LOAD,  # 16:30 KST
            once_callable=_stock_master_master_load_once,
            record_fn=record_stock_master_master_load,
            flush_fn=flush_stock_master_master_load_collector,
            summary_log_format=(
                "[stock_master_master_load_summary] kospi=%d kosdaq=%d "
                "total=%d updated=%d failed=%d elapsed_ms=%d"
            ),
            summary_keys=(
                "kospi_count", "kosdaq_count", "total",
                "updated", "failed", "elapsed_ms",
            ),
            # 사이클 159 stagger 임계 상향 (refactor-expert 자문 옵션 C)
            # = basics 완료 30초 후 진입 = HTTP/2 race 차단 마진 확보
            initial_delay_secs=720,
        )

    async def _evening_funnel_capture_once(self) -> dict:
        """사이클 171 — 16:20 저녁 잠정 funnel 캡처 본체 (한 번 실행).

        흐름 (domain-consult 의제 4 우선순위 2):
        1. 16:00 일봉 적재 완료 대기 — `stock_master_daily.count_all()` 폴링
           (사이클 163 boot prepare 가드 패턴, 일봉 미적재 시 빈 funnel 영속 방지)
        2. 5 전략 `prepare()` 호출 (기존 KIS-fetch 그대로 — 16:20 한가, 속도 무관.
           HIGH DB일봉 전환은 사이클 173). graceful (사이클 88) — 전략별 실패 격리
        3. `capture_funnel_snapshots(registry, is_provisional=True)` 단계별 + step_no=99 캡처

        안전 가드 (관찰성 한정 — 매매 hot path diff 0):
        - 16:00 일봉 → 16:10 basics → 16:20 prepare → 16:30 마스터 순서 의존성 보장
        - 사이클 158 재시도 hook + 사이클 32 R4 보유/익일청산 보호 영속
        - 사이클 132 momentum funnel 영구 제외 (prepare 호출은 하되 _funnel_steps 미적재)
        """
        from src.db.stock_master_daily import count_all as _daily_count_all

        # (1) 16:00 일봉 적재 완료 대기 (사이클 163 count polling 패턴 답습, 5분 cap)
        _WAIT_CAP_SECS = 300
        _POLL_SECS = 10
        waited = 0
        while waited < _WAIT_CAP_SECS:
            try:
                cnt = await _daily_count_all()
            except Exception:
                logger.exception("[evening_funnel] count_all 예외 graceful")
                cnt = 0
            if cnt > 0:
                if waited > 0:
                    logger.info(
                        "[evening_funnel] stock_master_daily count=%d (waited=%ds)",
                        cnt, waited,
                    )
                break
            await asyncio.sleep(_POLL_SECS)
            waited += _POLL_SECS

        # (2) 5 전략 prepare (graceful — 전략별 실패 격리, 사이클 88 답습)
        prepared = 0
        try:
            strategies = self.registry.all()
        except Exception:
            logger.exception("[evening_funnel] registry 접근 실패 graceful")
            strategies = []

        for strategy in strategies:
            prep = getattr(strategy, "prepare", None)
            if not callable(prep):
                continue
            try:
                await prep()
                prepared += 1
            except Exception:
                logger.exception(
                    "[evening_funnel] %s prepare 실패 graceful",
                    getattr(strategy, "strategy_id", "?"),
                )
                continue

        # (3) 잠정 funnel 캡처 (is_provisional=True)
        saved = await capture_funnel_snapshots(self.registry, is_provisional=True)

        return {"prepared": prepared, "saved": saved}

    async def _evening_funnel_capture_task_loop(self) -> None:
        """사이클 171 — 매일 16:20 KST 저녁 잠정 funnel 캡처 task.

        domain-consult 의제 4 우선순위 2 — 운영자가 전날 밤 다음 영업일 후보 확인.
        funnel 은 D-1 일봉 기반이라 장중 불변 → 한가한 저녁에 미리 생성.

        lifecycle (사이클 129/134 task 100% 답습):
        - start() 직후 즉시 1회 실행 + 매일 16:20 KST 정기 (lifecycle race 차단)
        - run_periodic_task_loop 헬퍼 위임 (사이클 134 카드 #21 영속)
        - stagger initial_delay_secs — basics(16:10) 완료 후 진입 (HTTP/2 race 마진)

        영속 의무:
        - 사이클 32 R4 보유/익일청산 절대 보호 (prepare 영역, 영향 0)
        - 사이클 38 명문화 (scanner/prepare 영역 = 매수 진입 전, 매도 hot path 무관)
        - 사이클 79 G-AST2 task_attrs 4 위치 (_evening_funnel_capture_task)
        - 사이클 88 G-REJECT graceful (전략별 prepare 실패 격리)
        - 사이클 132 momentum funnel 영구 제외 영속
        - 사이클 163 일봉 적재 완료 count polling 가드
        - 사이클 170 in-place upsert 영속 (같은 step_no 교체)
        """
        from src.engine.task_loop_helper import run_periodic_task_loop

        # metrics collector 미사용 (funnel = DB 직접 영속) → no-op record/flush
        # (사이클 134 헬퍼는 record_fn/flush_fn 무조건 호출 → None 불가, no-op 위임)
        def _noop_record(_summary: dict) -> None:
            return None

        def _noop_flush() -> None:
            return None

        await run_periodic_task_loop(
            scheduler=self,
            task_label="evening_funnel_capture",
            wait_time=TIME_EVENING_FUNNEL_CAPTURE,  # 16:20 KST
            once_callable=self._evening_funnel_capture_once,
            record_fn=_noop_record,
            flush_fn=_noop_flush,
            summary_log_format=(
                "[evening_funnel_capture_summary] prepared=%d saved=%d"
            ),
            summary_keys=("prepared", "saved"),
            # basics(16:10) 완료 후 진입 = HTTP/2 race 차단 마진 (사이클 159 답습)
            initial_delay_secs=600,
        )

    async def _stock_master_daily_purge_task_loop(self) -> None:
        """사이클 150 (2026-06-16) — 매일 16:15 KST stock_master_daily T-150일 retention cron task.

        SUPABASE 용량초과 시정 영구 영속 — 사용자 결정 Q3=C (VCP T-120일 + 30일 안전 마진).

        영속 의무 매트릭스:
        - 사이클 6 retention 패턴 답습 (purge_old_logs 영역 정합)
        - 사이클 32 R4 universe guard 보유/익일청산 절대 보호 (protected_tickers 영역 영속)
        - 사이클 38 명문화 (scanner 영역 = 매수 진입 전, 매도 hot path 무관)
        - 사이클 48 VCP EMA effective_long T-120일 영역 영속 (T-150일 안전 마진 영구 영속)
        - 사이클 79 G-AST2 영속 (task_attrs 4 위치 영속)
        - 사이클 88 G-REJECT graceful 단위 = 헬퍼 영역 영구 영속 내부
        - 사이클 106 lifecycle race 차단 = 헬퍼 영역 영구 영속 내부
        - 사이클 122 stock_master_daily T-100일 백필 영역 영속 (T-150일 retention 정합)
        - 사이클 134 task_loop_helper 영속 (run_periodic_task_loop 패턴 답습)
        """
        from datetime import timedelta as _timedelta
        from src.db._kst import today_kst
        from src.db.stock_master_daily import (
            DAILY_RETENTION_DAYS,
            purge_old_rows,
        )
        from src.engine.task_loop_helper import run_periodic_task_loop

        async def _purge_once() -> dict:
            """T-150일 cutoff + 보유/익일청산 protected_tickers 합집합 영역."""
            # 사이클 32 R4 답습 — 보유 ∪ 익일청산 합집합 영구 영속 보호
            protected: set[str] = set()
            try:
                for strategy in self.registry.all():
                    state = strategy.state
                    for ticker in (state.positions or {}).keys():
                        if ticker:
                            protected.add(ticker)
            except Exception:
                logger.exception("[stock_master_daily_purge] protected tickers 영역 수집 실패 graceful")

            try:
                for entry in (self._pending_next_day_clear or set()):
                    # entry 는 (ticker, strategy_id) 튜플 영속
                    if isinstance(entry, tuple) and entry:
                        ticker = entry[0]
                    else:
                        ticker = entry
                    if ticker:
                        protected.add(str(ticker))
            except Exception:
                logger.exception("[stock_master_daily_purge] pending_next_day_clear 영역 수집 실패 graceful")

            cutoff = today_kst() - _timedelta(days=DAILY_RETENTION_DAYS)
            summary = await purge_old_rows(cutoff, protected_tickers=protected or None)
            # task_loop_helper summary 영역 정합 — cutoff 키 추가
            summary["cutoff"] = cutoff.isoformat()
            return summary

        # 사이클 150 영역 = collector 단순화 — record/flush 영역 미사용 (운영 effect = retention 단일)
        def _noop_record(summary: dict) -> None:  # noqa: ARG001
            return None

        def _noop_flush() -> None:
            return None

        await run_periodic_task_loop(
            scheduler=self,
            task_label="stock_master_daily_purge",
            wait_time=TIME_STOCK_MASTER_DAILY_PURGE,  # 16:15 KST
            once_callable=_purge_once,
            record_fn=_noop_record,
            flush_fn=_noop_flush,
            summary_log_format=(
                "[stock_master_daily_purge_summary] deleted=%d protected=%d "
                "elapsed_ms=%d cutoff=%s"
            ),
            summary_keys=("deleted", "protected_count", "elapsed_ms", "cutoff"),
        )

    def _detect_silent_inactive_sessions(self) -> list[str]:
        """세션 단위 silent inactive 감지 — 사이클 61 Phase 2-A2 stale_manager 위임."""
        from src.engine import stale_manager
        return stale_manager.detect_silent_inactive_sessions(self)

    async def _force_reconnect_session(self, label: str) -> bool:
        """세션 단위 silent inactive 강제 reconnect — 사이클 61 Phase 2-A2 stale_manager 위임."""
        from src.engine import stale_manager
        return await stale_manager.force_reconnect_session(self, label)

    async def _check_and_resubscribe_stale(self) -> None:
        """K stale watcher 본체 — 사이클 63 Phase 2-A3 stale_manager 위임."""
        from src.engine import stale_manager
        await stale_manager.check_and_resubscribe_stale(self)

    # -----------------------------------------------------------------
    # 사이클 28 (2026-05-21) — 진단 로그 강화 헬퍼
    # 트리거: 2026-05-21 09:13 VB 돌파 미매수 진단 — stale 16/30 (53%) 의 종목별/세션별
    # 분포·last_resub 시각·세션 부하 가시화. 안전 가드:
    #   G1 기존 prefix 보존 / G3 stale>0 세션만 + cap 20 / G4 보조 미등록 OK
    # -----------------------------------------------------------------

    _STALE_DETAIL_TICKER_CAP = 20  # G3 — detail 행 종목 리스트 최대치 (로그 폭주 차단)

    def _build_session_subscription_view(self) -> list[dict]:
        """세션별 분포 dict 리스트 — 사이클 60 Phase 2-A1 (2026-06-04) stale_manager 위임."""
        from src.engine import stale_manager
        return stale_manager.build_session_subscription_view(self)

    def _emit_stale_session_detail(
        self, stale_tickers: list[str], now: datetime
    ) -> None:
        """``[stale_watcher_detail]`` 세션별 분포 행 출력 — 사이클 60 Phase 2-A1 stale_manager 위임."""
        from src.engine import stale_manager
        stale_manager.emit_stale_session_detail(self, stale_tickers, now)

    async def _delta_unsubscribe_dropped(self, new_set: set[str]) -> list[str]:
        """`_scan_loop` delta unsubscribe — 사이클 61 Phase 2-A2 stale_manager 위임."""
        from src.engine import stale_manager
        return await stale_manager.delta_unsubscribe_dropped(self, new_set)

    async def _resubscribe_stale_priority(self, cap: int = 10) -> list[str]:
        """`_scan_loop` 5분 stale 우선순위 재구독 — 사이클 63 Phase 2-A3 stale_manager 위임."""
        from src.engine import stale_manager
        return await stale_manager.resubscribe_stale_priority(self, cap=cap)

    async def _evaluate_universe_guard(self, candidate_tickers: list[str]) -> None:
        """universe stale 가드 평가 — 사이클 61 Phase 2-A2 stale_manager 위임."""
        from src.engine import stale_manager
        await stale_manager.evaluate_universe_guard(self, candidate_tickers)

    async def _subscribe_market_operation_tickers(
        self, candidate_tickers: set[str], *, cap: int = 20,
    ) -> int:
        """사이클 149 (2026-06-16) — 종목별 H0UNMKO0 구독 확장.

        보유/익일청산 (HIGH) + 전략 후보 (LOW cap=20) 합집합 종목별 구독.
        메인 세션 단일 + bypass_limit=True (자문 의제 2/3 자문 채택).

        domain-expert 자문 산출물:
            `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md`

        영속 의무:
        - 의제 2: H0UNMKO0 LMS 한도 41 영역 = bypass_limit=True 가드 의존 (사이클 17 영속)
        - 의제 3: HIGH 절대 보장 + LOW cap=20 (사이클 66 K-10 패턴 답습)
        - 사이클 26 005930 대표 구독 영역 보존 (시장 단위 신호 영속)

        매매 안전성 무영향 (사이클 38 명문화 영속):
        - WebSocket 시세 TICK 영역 변경 0
        - `risk.on_tick` / `order_engine` / `auth` 변경 0
        """
        from src.api.market_operation import MARKET_OP_TR_ID
        from src.realtime.websocket import kis_ws

        if kis_ws is None or not getattr(kis_ws, "_ws", None):
            return 0

        # HIGH = 보유 + 익일청산 (절대 보장)
        high_tickers: set[str] = set()
        try:
            for s in self.registry.all():
                try:
                    high_tickers.update(s.state.positions.keys())
                except Exception:
                    pass
        except Exception:
            pass
        try:
            high_tickers.update(t for (t, _sid) in self._pending_next_day_clear)
        except Exception:
            pass

        # LOW = 전략 후보 (cap=20 sorted 결정적 순서)
        low_tickers = sorted(set(candidate_tickers) - high_tickers)[:cap]

        # 메인 세션 단일 구독 (보조 세션 절대 금지, 자문 의제 2)
        subscribed = 0
        for ticker in sorted(high_tickers):
            try:
                # HIGH = bypass_limit=True 강제 (사이클 17 OPSP0002 backoff 영속)
                await kis_ws.subscribe(MARKET_OP_TR_ID, ticker, bypass_limit=True)
                subscribed += 1
                await asyncio.sleep(0.05)  # Rate Limit 보호 (사이클 17 LMS chain)
            except Exception:
                logger.exception(
                    "[market_op_subscribe] HIGH 구독 실패 ticker=%s graceful", ticker,
                )

        for ticker in low_tickers:
            try:
                await kis_ws.subscribe(MARKET_OP_TR_ID, ticker, bypass_limit=False)
                subscribed += 1
                await asyncio.sleep(0.05)
            except Exception:
                logger.exception(
                    "[market_op_subscribe] LOW 구독 실패 ticker=%s graceful", ticker,
                )

        logger.info(
            "[market_op_subscribe_summary] high=%d low=%d total_subscribed=%d cap=%d",
            len(high_tickers), len(low_tickers), subscribed, cap,
        )
        return subscribed

    async def _refresh_stale_ccnl_cache(
        self, candidate_tickers: list[str], *, cap: int = 20,
    ) -> None:
        """stale 종목 KIS 실제 last_cntg_hour 갱신 — 사이클 60 Phase 2-A1 stale_manager 위임."""
        from src.engine import stale_manager
        await stale_manager.refresh_stale_ccnl_cache(self, candidate_tickers, cap=cap)

    def _evict_expired_ccnl(self, now: datetime, ttl_secs: float = 300) -> int:
        """`_last_ccnl_cache` TTL 만료 항목 자동 제거 — 사이클 60 Phase 2-A1 stale_manager 위임."""
        from src.engine import stale_manager
        return stale_manager.evict_expired_ccnl(self, now, ttl_secs=ttl_secs)

    def _prune_force_retry_history(
        self, ticker: str, now: datetime, window_secs: float = 3600
    ) -> None:
        """`_stale_force_retry_history` 빈 list 제거 — 사이클 60 Phase 2-A1 stale_manager 위임."""
        from src.engine import stale_manager
        stale_manager.prune_force_retry_history(self, ticker, now, window_secs=window_secs)

    # ------------------------------------------------------------------------
    # 사이클 46 (2026-05-22, refactor-review 카드 #6) — 세션 헬스 통합 5분 주기
    # ------------------------------------------------------------------------
    async def _session_health_loop(self) -> None:
        """5분 주기 세션 헬스 통합 task.

        사이클 42 `KisWebSocket._heartbeat_metrics_loop` 세션별 분산 task (메인 + 보조 N) →
        scheduler 통합 호출로 일원화. 메인+보조 일관성 + 좀비 task 방지 + 단순화.

        담당:
        - `_emit_heartbeat_metrics_all_sessions` — 메인 + 보조 세션 일괄 `_heartbeat_metrics_emit_once`

        보존 정책:
        - `_stale_watcher_loop` (120s) 별도 보존 — 재시도 빈도 우선 (사이클 24/29-R1/29-R3 안전망)
        - `_report_tick_coverage` 는 `_scan_loop` (5분) 안에서 호출 — 중복 발화 차단

        본체 예외 graceful — 다음 사이클 자연 재시도.
        """
        # 사이클 42 `HEARTBEAT_METRICS_INTERVAL_SECS=300` 정합
        INTERVAL_SECS = 300
        while self._running:
            try:
                await asyncio.sleep(INTERVAL_SECS)
                if not self._running:
                    break
                try:
                    await self._emit_heartbeat_metrics_all_sessions()
                except Exception:
                    logger.exception("[session_health] heartbeat_metrics 실패 — 다음 사이클 재시도")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("[session_health_loop] 사이클 실패")

    async def _emit_heartbeat_metrics_all_sessions(self) -> None:
        """메인 + 보조 모든 KisWebSocket 세션 [ws_heartbeat] 단발 emit 통합.

        사이클 42 인스턴스별 task → scheduler 일괄 호출. 메인 + 보조 일관성.
        한 세션 실패 → 다른 세션 계속 (graceful).
        """
        from src.realtime import websocket as _ws_mod
        from src.realtime import websocket_pool as _wp_mod

        # 메인 세션
        main_ws = getattr(_ws_mod, "kis_ws", None)
        sessions = []
        if main_ws is not None:
            sessions.append(main_ws)
        # 보조 세션 (사이클 43 DB 라벨 — ISA/sub/gold)
        pool = getattr(_wp_mod, "kis_ws_pool", None)
        if pool is not None:
            quotes = getattr(pool, "_quotes", None) or []
            sessions.extend(quotes)

        for ws in sessions:
            emit_fn = getattr(ws, "_heartbeat_metrics_emit_once", None)
            if not callable(emit_fn):
                continue
            try:
                await emit_fn()
            except Exception:
                label = getattr(ws, "_label", "unknown")
                logger.exception(
                    "[session_health] %s _heartbeat_metrics_emit_once 실패 — 격리", label
                )

    async def _auto_capture_funnel_snapshots(self) -> None:
        """사이클 39 (2026-05-22) — 09:30 자동 funnel snapshot.

        사이클 171 (2026-06-22) — 공통 헬퍼 `capture_funnel_snapshots(registry, *,
        is_provisional)` 위임 (3 호출처 공유: 09:30 자동 / 16:20 저녁 / 수동 trigger).
        09:30 자동 = 확정 캡처 (is_provisional=False) — 행위 보존 (단계별 + step_no=99).

        흐름 (헬퍼 본체):
        1. `registry.all()` 순회 — `_funnel_steps` 가 있는 전략만
        2. 각 전략 단계별 (`step_no=1..N`) row + 최종 (`step_no=99`) row INSERT
        3. 한 전략 처리 중 예외 → 다른 전략 계속 (graceful)

        안전 가드:
        - 본체 예외는 호출자 `_scan_loop` 가 try/except 흡수
        - DB JSONB cap 200/20 (사이클 34 strategy_funnel.py 자동 적용)
        - 일일 1회 가드는 호출자 (`_auto_funnel_snapshot_done_today`) 가 보장
        """
        await capture_funnel_snapshots(self.registry, is_provisional=False)

    async def _report_tick_coverage(self) -> None:
        """현재 TICK 구독 종목 중 최근 60초 내 tick 수신 비율을 로깅한다 (Phase D + 가설 B 확장 2026-05-12).

        - 5분 주기 `_scan_loop` 사이클당 1행 노출 (`INFO`/`WARNING` + `system_logs`)
        - 임계값 60초: SCAN_INTERVAL(300s) 내 1분 미수신은 시장 미체결 정상 가능,
          5분 미수신은 시세 문제 의심. 둘 다 카운트 노출
        - `ticker_last_tick` 키 부재 종목은 stale 로 카운트 (구독 직후 0초 경과 가능)
        - 본체 예외는 `_scan_loop` 흐름 보호 위해 흡수

        확장(가설 B, 2026-05-12):
        - `ratio=R%` — fresh / subscribed 비율 (1자리 소수)
        - `stale_sample=[t1,t2,...]` — sorted(stale) 최대 10개
        - `last_tick_avg_age=Xs` — 전체 평균 마지막 tick 경과시간(초). 키 없으면 -1
        - stale_ratio > 0.30 이면 WARNING 레벨 (INFO 대신)
        """
        from datetime import datetime as _dt
        from src.engine.scanner import KST_TZ, ticker_last_tick
        # 사이클 14-A (2026-05-18) — 메인 단독 → 풀 전체로 확장. 사이클 11 에서
        # `scanner.get_scan_status()` 만 풀 통합되고 짝궁 메서드 누락되어 운영자가
        # `[tick_coverage] subscribed=0` 을 보고 "전부 끊김"이라고 오인하던 결함 차단.
        from src.realtime.websocket_pool import kis_ws_pool

        try:
            subscribed = kis_ws_pool.get_subscribed_tickers()
            now = _dt.now(KST_TZ)
            fresh_threshold = timedelta(seconds=60)
            fresh_tickers: set[str] = set()
            stale_tickers: list[str] = []
            ages: list[float] = []
            for t in subscribed:
                last_tick = ticker_last_tick.get(t)
                if last_tick is None:
                    stale_tickers.append(t)
                    # 키 없음 — 평균 계산에서 제외
                    continue
                age_s = (now - last_tick).total_seconds()
                ages.append(age_s)
                if (now - last_tick) <= fresh_threshold:
                    fresh_tickers.add(t)
                else:
                    stale_tickers.append(t)
            fresh = len(fresh_tickers)
            stale = len(stale_tickers)
            total = len(subscribed)
            ratio_pct = round(100.0 * fresh / total, 1) if total > 0 else 0.0
            stale_ratio = (stale / total) if total > 0 else 0.0
            avg_age = round(sum(ages) / len(ages), 1) if ages else -1.0
            stale_sample = sorted(stale_tickers)[:10]
            msg = (
                f"[tick_coverage] subscribed={total} fresh={fresh} stale={stale} "
                f"ratio={ratio_pct}% stale_sample={stale_sample} "
                f"last_tick_avg_age={avg_age}s"
            )
            level = "WARNING" if stale_ratio > 0.30 else "INFO"
            if level == "WARNING":
                logger.warning(msg)
            else:
                logger.info(msg)
            try:
                await write_log(level, msg)
            except Exception:
                logger.debug("write_log [tick_coverage] 실패")

            # 사이클 28 (2026-05-21) — [tick_coverage_session] 세션별 분포 신규 행
            # 기존 [tick_coverage] 보존 (G1) + 별도 prefix 1행 추가. subscribed=0 → skip
            if total > 0:
                try:
                    view = self._build_session_subscription_view()
                    if view:
                        parts = [
                            f"{s['label']} sub={s['capacity_used']}/{s['capacity_max']} "
                            f"fresh={s['fresh']} stale={s['stale']} "
                            f"({s['stale_ratio']:.2f})"
                            for s in view
                        ]
                        sess_msg = "[tick_coverage_session] " + " | ".join(parts)
                        logger.info(sess_msg)
                        try:
                            await write_log("INFO", sess_msg)
                        except Exception:
                            logger.debug("write_log [tick_coverage_session] 실패")
                except Exception:
                    logger.debug("[tick_coverage_session] 빌드 실패", exc_info=True)
        except Exception:
            logger.exception("_report_tick_coverage 실패")

    async def _sync_positions_from_balance(self) -> None:
        """KIS 잔고를 조회하여 체결통보 누락된 포지션을 보완한다."""
        from src.engine.strategy_base import Position
        from src.engine.scanner import ticker_names
        from src.db.trade_history import update_trade_status
        from src.models.trade import TradeType, TradeStatus

        holdings, _ = await get_balance()

        for h in holdings:
            if h.quantity <= 0:
                continue
            if not (len(h.ticker) == 6 and h.ticker.isalnum()):
                continue

            # DB에서 PENDING 상태인 매수 기록이 있으면 COMPLETED로 갱신
            # (체결통보 누락으로 상태가 갱신되지 않은 경우)
            try:
                from src.db.supabase import supabase
                supabase.table("trade_history").update(
                    {"status": "COMPLETED"}
                ).eq("ticker", h.ticker).eq(
                    "trade_type", "BUY"
                ).eq("status", "PENDING").execute()
            except Exception:
                pass

            # 이미 어떤 전략에 포지션이 있으면 건너뜀
            if self.registry.is_ticker_held_by_any(h.ticker):
                continue
            # 체결통보 누락 — KIS 잔고에는 있지만 내부 포지션에 없음
            # strategy 매핑: trade_history의 직전 BUY 행에서 상속
            # (이전엔 무조건 'momentum' 하드코딩이라 BUY=VB / SELL=momentum strategy 어긋남 — 알루코 사례 재발 차단)
            strategy_id = "momentum"
            try:
                from src.db.supabase import supabase as _sb
                th = _sb.table("trade_history").select("strategy").eq(
                    "ticker", h.ticker
                ).eq("trade_type", "BUY").order(
                    "timestamp", desc=True
                ).limit(1).execute()
                if th.data:
                    strategy_id = th.data[0].get("strategy") or "momentum"
            except Exception:
                pass

            target = self.registry.get(strategy_id) or self.registry.get("momentum")
            if target:
                actual_sid = target.strategy_id
                target.state.positions[h.ticker] = Position(
                    ticker=h.ticker,
                    buy_price=int(h.avg_price),
                    quantity=h.quantity,
                    order_no="",
                    strategy_id=actual_sid,
                )
                if h.name:
                    ticker_names[h.ticker] = h.name
                logger.warning(
                    "포지션 동기화 (체결통보 누락 보완): %s %d주 @ %d (전략: %s)",
                    h.name or h.ticker, h.quantity, int(h.avg_price), actual_sid,
                )

        # 잔고 동기화 후 모든 전략의 매수 락/캐시 해제 — 가용액이 회복됐을 가능성 반영
        for s in self.registry.all():
            if s.state.buy_blocked_until > 0 or s.state.cached_buyable_at > 0:
                s.state.unblock_buy()
            # per-ticker 투자금 부족 cooldown도 잔고 sync 후 해제 — 비중 변경/예수금 입금 등 반영
            if s.state.low_funds_tickers:
                s.state.clear_low_funds()

    async def _settle(self) -> None:
        """일일 정산: 잔고 조회 후 전략별 + 합산 daily_performance 기록.

        새 수익률 모델:
        - 외부 입출금 자동 추정: (Δ예수금) - (매도총액 - 매수총액)
        - 일별 수익률(실현손익 기준) = daily_realized_pnl / 어제 자산
        - 누적 수익률 = TWR 복리: (1 + prev_cum) × (1 + daily_rate) - 1
        """
        from src.db.trade_history import get_today_trades_for_settlement

        try:
            _, summary = await get_balance()
            from src.engine.scanner import KST_TZ as _KST_TZ_SETTLE
            today = datetime.now(_KST_TZ_SETTLE).date()

            # 전체('total') 정산
            prev_total = await get_latest_performance(strategy="total")
            prev_total_asset = float(prev_total["total_asset"]) if prev_total else float(summary.net_asset)
            prev_deposit = float(prev_total["deposit"]) if prev_total else float(summary.deposit)
            prev_cum_rate = float(prev_total["cumulative_return_rate"]) if prev_total else 0.0

            # 당일 체결 raw (전 전략 합산)
            today_trades_all = await get_today_trades_for_settlement()
            buy_total = sum(float(t.get("price", 0)) * int(t.get("quantity", 0))
                            for t in today_trades_all if t.get("trade_type") == "BUY")
            sell_total = sum(float(t.get("price", 0)) * int(t.get("quantity", 0))
                             for t in today_trades_all if t.get("trade_type") == "SELL")
            net_trade_cashflow = sell_total - buy_total  # 매매로 인한 예수금 증가분

            # 외부 입출금 추정 (Δ예수금 - 매매 cashflow)
            net_ext_cashflow = (float(summary.deposit) - prev_deposit) - net_trade_cashflow

            # 당일 실현손익 합 (매도 거래 profit_loss)
            daily_realized_pnl_total = sum(
                float(t.get("profit_loss") or 0) for t in today_trades_all
                if t.get("trade_type") == "SELL"
            )

            # 일별 실현 수익률 — 어제 자산 분모
            daily_rate = (daily_realized_pnl_total / prev_total_asset * 100) if prev_total_asset > 0 else 0.0
            # 누적 TWR 복리
            cum_rate = ((1 + prev_cum_rate / 100) * (1 + daily_rate / 100) - 1) * 100

            await upsert_daily_performance(
                target_date=today,
                total_asset=float(summary.net_asset),
                daily_profit_rate=daily_rate,
                strategy="total",
                net_external_cashflow=net_ext_cashflow,
                daily_realized_pnl=daily_realized_pnl_total,
                deposit=float(summary.deposit),
                cumulative_return_rate=cum_rate,
            )

            # 전략별 기록 (TWR 복리 누적)
            for strategy in self.registry.all():
                sid = strategy.strategy_id
                prev_s = await get_latest_performance(strategy=sid)
                prev_s_asset = float(prev_s["total_asset"]) if prev_s else float(strategy.state.total_investment)
                prev_s_cum = float(prev_s["cumulative_return_rate"]) if prev_s else 0.0

                s_pnl = float(strategy.state.daily_realized_pnl)
                s_rate = (s_pnl / prev_s_asset * 100) if prev_s_asset > 0 else 0.0
                s_cum = ((1 + prev_s_cum / 100) * (1 + s_rate / 100) - 1) * 100

                # total_asset baseline: state.total_investment 우선, 0이면 직전 영업일 total_asset fallback.
                # 정산 시점에 state.total_investment=0인 경우(자금 분배 직전/직후 등) total_asset이
                # 0으로 기록되면 다음 영업일의 daily_profit_rate 분모가 0이 되는 함정을 막는다.
                s_investment = float(strategy.state.total_investment)
                if s_investment <= 0 and prev_s_asset > 0:
                    s_investment = prev_s_asset
                await upsert_daily_performance(
                    target_date=today,
                    total_asset=s_investment + s_pnl,
                    daily_profit_rate=s_rate,
                    strategy=sid,
                    daily_realized_pnl=s_pnl,
                    cumulative_return_rate=s_cum,
                )

            await write_log(
                "INFO",
                f"일일 정산: 순자산 {summary.net_asset:,}원, 실현 {daily_rate:.2f}%, "
                f"누적 {cum_rate:.2f}%, 외부입출금 {net_ext_cashflow:,.0f}원",
            )

            # 정산 직후 trade_history 기반 일괄 재계산 — 누락된 영업일/cumulative 보정
            try:
                await recompute_from_trades()
            except Exception:
                logger.exception("정산 후 재계산 실패 (소급 정합성 보정)")
        except Exception:
            logger.exception("정산 오류")
            await write_log("ERROR", "일일 정산 실패")

        # 사이클 65 (2026-06-06) — 거래대금 필터 daily_summary 직접 호출 (H-2 NO_TRY).
        # ★ try/except 금지 (H-2 AST 가드) — AttributeError 가 silent 되면 운영 가시화 무력화.
        # 사이클 64 hotfix 영구 패턴 답습.
        from src.engine import scanner as _scanner_settle_mod
        await _scanner_settle_mod.emit_trade_amount_filter_scanner_daily_summary()

        # 일간 상태 초기화는 _settle 호출자(run loop)에서 log_analysis 후 별도 호출 — funnel 카운터 보존을 위해

    def _reset_daily_state(self) -> None:
        """일간 상태를 초기화한다. 정산 완료 후 호출."""
        for strategy in self.registry.all():
            strategy.state.positions.clear()
            strategy.state.pending_buys.clear()
            strategy.state.pending_buy_amounts.clear()
            strategy.state.sold_today.clear()
            strategy.state.daily_realized_pnl = 0
            strategy.state.total_investment = 0
            strategy.state.buy_disabled = False
            strategy.state.buy_signals.clear()
            strategy.state.low_funds_tickers.clear()
            strategy.state.signal_count_today = 0
            strategy.state.order_attempt_today = 0
            strategy.state.fill_count_today = 0
            # 사이클 185 클러스터 ① 메커니즘 1 — transient cross-day 상태 정리
            try:
                strategy._reset_daily_state()
            except Exception:
                logger.exception(
                    "[strategy_reset_daily_skip] strategy=%s graceful", strategy.strategy_id
                )

        # OrderEngine 추적 상태 초기화
        self.order_engine._selling.clear()
        self.order_engine._filled_qty.clear()
        self.order_engine._order_qty.clear()
        self.order_engine._order_strategy.clear()
        self.order_engine._order_ticker.clear()
        self.order_engine._pending_buy_orders.clear()
        for task in self.order_engine._pending_cancel_tasks.values():
            task.cancel()
        self.order_engine._pending_cancel_tasks.clear()
        # 사이클 B-1 (2026-06-01) — 장운영시간 외 거부 TTL 게이트 일일 초기화 (캡슐화 위임)
        self.order_engine.reset_daily_state()

        # P1(B) 익일 청산 보류 set 도 매일 초기화
        self._pending_next_day_clear.clear()
        # 사이클 162 (2026-06-17) — DB 영속화 영역 동행 정리 (의제 D, fire-and-forget).
        # `_reset_daily_state` 는 sync 함수 → running event loop 존재 시만 schedule.
        # 다음 영업일 _boot 영역 진입 전 = target_date 이전 영역 일괄 DELETE.
        try:
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz
            from src.db.pending_next_day_clear import purge_pending_ndc_before
            _kst = _tz(_td(hours=9))
            _today = _dt.now(_kst).date()
            try:
                _loop = asyncio.get_running_loop()
                _loop.create_task(purge_pending_ndc_before(_today))
            except RuntimeError:
                # event loop 부재 (테스트 sync 호출 영역) — graceful skip
                pass
        except Exception:
            logger.exception("[pending_ndc_purge_skip] reset_daily graceful")

        # 사이클 48 (2026-05-22, refactor-review 카드 #2) — Stale 추적 7 필드 통합 reset.
        # 사이클 17/24/28/29-R1/32/37/45 누적 7 dict/set 일괄 clear:
        #   - retry_count (사이클 17 이전, K) — stale_watcher 종목별 연속 stale 카운터
        #   - last_resubscribe_at (사이클 28) — 강제 재구독 시각 추적 (G5 cleanup 동행)
        #   - force_retry_history (사이클 29-R1) — 영구 stale 시간당 cap 60분 sliding window
        #   - silent_inactive_first_seen + recovery_count (사이클 24) — 세션 reconnect cap
        #   - universe_excluded_today (사이클 32 R4) — 영구 블랙리스트 금지 (다음 영업일 재진입)
        #   - last_ccnl_cache (사이클 37) — KIS 체결시각 캐시 (사이클 45 TTL evict 와 이중 안전망)
        self._stale_state.reset_daily()

        # 사이클 31 (R6, 2026-05-21) — risk.py 사전 가드 침묵 가시화 emit cap 일일 초기화.
        # `(ticker, strategy_id)` 페어 1회/일 INFO emit cap. 익일 첫 호출 시 재 emit 가능.
        # 사이클 56-D: reset_daily_state() 캡슐화 위임 (사이클 52 OrderEngine 패턴 답습).
        try:
            self.risk_manager.reset_daily_state()
        except AttributeError:
            # 후방호환 가드 — RiskManager 가 reset_daily_state 메서드 없는 경우 (구버전 호환)
            pass

        # 사이클 158 Q1 — momentum 익일 청산 logger DailyEmitCap 일일 초기화.
        # 사이클 31 R6 / 57 V-1 패턴 답습 — ticker 단위 1회/일 cap reset.
        try:
            from src.engine.strategies.momentum import reset_next_day_clear_logged_today
            reset_next_day_clear_logged_today()
        except Exception:
            logger.exception("momentum reset_next_day_clear_logged_today 실패")
        # 사이클 189 (2026-07-02) — reprepare WARNING DailyEmitCap 일일 초기화 (1회/전략/일 cap).
        self._reprepare_empty_logged_today.reset_daily()
        # 사이클 39 (2026-05-22) — 09:30 자동 funnel snapshot 일일 1회 가드 reset
        self._auto_funnel_snapshot_done_today = False

        # Phase 3 (2026-05-16) — 백테스트 폴 루프 진입 가드 set 매일 초기화.
        # 정상 종료 시 finally 에서 discard 되지만 예외/취소 시 잔재 가능성 차단.
        try:
            from src.engine.recommendation_engine import _backtest_poll_loop_running
            _backtest_poll_loop_running.clear()
        except Exception:
            logger.exception("backtest_poll_loop_running clear 실패")

        # scanner 글로벌 dict 누수 방지 — 정산 후 매일 정리(STATIC_TICKER_NAMES는 모듈 import 시 자동 시드되므로 그대로 유지)
        from src.engine.scanner import (
            STATIC_TICKER_NAMES, ticker_last_tick, ticker_market_info, ticker_names,
            ticker_prev_close, ticker_prices,
        )
        ticker_prices.clear()
        ticker_prev_close.clear()
        ticker_market_info.clear()
        ticker_names.clear()
        ticker_names.update(STATIC_TICKER_NAMES)  # 정적 시드 재주입
        ticker_last_tick.clear()  # Phase D — 다른 scanner dict들과 일관성

        # PR-C (2026-05-14) — condition.py TTL 캐시(시세/일봉) 일괄 무효화.
        # 야간 누적 방지 + 다음 영업일 시작 시 신선한 KIS 값으로 재충전.
        try:
            from src.api import condition as _cond
            _cond.clear_caches()
        except Exception:
            logger.exception("condition cache clear 실패")

        # 사이클 64 (2026-06-06) — scanner 가격 필터 emit cap + 일일 카운터 동행 reset.
        # E-2 회귀 가드 의무 — CLAUDE.md `_reset_daily_state` 동행 reset.
        try:
            from src.engine import scanner as _scanner_mod
            _scanner_mod.reset_price_filter_daily_state()
        except Exception:
            logger.exception("scanner.reset_price_filter_daily_state 실패")

        # 사이클 65 (2026-06-06) — 거래대금 필터 daily_state reset 동행
        from src.engine import scanner as _scanner_mod
        _scanner_mod.reset_trade_amount_filter_daily_state()

        # 사이클 149 (2026-06-16) — 종목별 H0UNMKO0 state reset 동행.
        # 사이클 88 G-REJECT 영속 답습 = 모든 dict 일일 0 초기화 의무.
        # `_vi_active_tickers` + `_halt_active_tickers` + `_market_op_last_event` 3 dict 일괄 clear.
        try:
            from src.engine import market_operation_monitor as _market_op_mod
            _market_op_mod.reset_market_op_state()
        except Exception:
            logger.exception("market_operation_monitor.reset_market_op_state 실패 graceful")

        logger.info("일간 상태 초기화 완료 (scanner 캐시 clear 포함)")

    async def _wait_until(self, target: time, *, advance_if_passed: bool = False) -> None:
        """지정 시각까지 대기한다.

        사이클 160 hotfix (2026-06-17) — 사이클 152 hotfix 결정타 결함 시정:
        사이클 152 가 `_wait_until` 본질을 깨뜨려 target 도달 시에도 break 하지 않고
        다음 날로 미루는 결함을 도입. 결과 = `run_daily()` 영역 모든 phase 전환
        (15:20 강제청산 / 15:30 마감 / 19:50 매수중단 / 20:00 자문 / 20:10 정산) 영구
        누락. 6/17 운영 사례 = 알테오젠 (VB) + 알지노믹스 (LTV) 15:20 매도 누락.

        본질 복원 (사이클 160):
        - 기본 (advance_if_passed=False) = target 도달 즉시 return. `run_daily()` 영역
          phase 시각 도달 시 즉시 다음 phase 진입 의무 영속.
        - advance_if_passed=True = target 이 *이미 지났으면* 내일 동일 시각 대기.
          task_loop_helper 영역 폭주 차단 (사이클 152 hotfix 의도 영속).

        사이클 152 운영 사례 (18:00 KST 시점 task 폭주):
        - task_loop_helper 가 `advance_if_passed=True` 로 호출하면 18:00 시점 _wait_until(16:30)
          → target_dt = 내일 16:30 → 86,400s 대기 → 폭주 차단 정상.
        - run_daily 영역은 advance_if_passed=False (default) 로 호출 → target 도달 시 즉시
          return → phase 전환 정상.

        사이클 188 회귀 시정 (2026-07-02) — advance 모드 never-return 결함 차단:
        사이클 160 구현이 while 루프 내부에서 매 iteration 마다 target_dt 를 오늘 기준으로
        재계산(now_dt.replace(...))하여, advance 모드에서 +1일 후에도 다음 루프에서 다시
        오늘 target 으로 초기화 → now >= target 조건 재성립 → 또 +1일 → 영원히 return
        불가. 결과 = task_loop_helper 정기 발화 0회 (16:00 일봉 / 16:10 basics 등 미발화).
        시정 원칙:
        - target_dt 를 *호출 시점 1회 확정* (while 루프 진입 전). 루프 내 재계산 금지.
        - while 루프는 `now >= 확정 target_dt` 도달 시 즉시 return (사이클 188 신규 경로).
        - advance 모드(target 이미 지남) = +1일 확정 후 루프 진입 → 익일 도달 시 return.
        - `_running=False` → 발화 없이 return (CancelledError 는 헬퍼가 처리).
        """
        now_dt = datetime.now()
        target_dt = now_dt.replace(
            hour=target.hour, minute=target.minute,
            second=target.second or 0, microsecond=0,
        )
        if now_dt >= target_dt:
            if not advance_if_passed:
                # 본질 = target 도달 즉시 return (run_daily phase 전환 영속)
                return
            # task_loop_helper 영역 = 내일 동일 시각으로 1회 확정 (폭주 차단 영속)
            target_dt += timedelta(days=1)
        while self._running:
            now_dt = datetime.now()
            if now_dt >= target_dt:
                # 확정 target 도달 → return (사이클 188 신규 경로, 재-advance 차단)
                return
            await asyncio.sleep(min((target_dt - now_dt).total_seconds(), 60))


trading_scheduler = TradingScheduler()
