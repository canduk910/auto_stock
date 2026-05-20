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
    register_board_handler,
    register_execution_handler,
    register_tick_handler,
)
from src.realtime.websocket import kis_ws

logger = logging.getLogger(__name__)

# 시간 상수 — NXT 통합 운영 (08:00~20:00)
TIME_AUTO_START = time(7, 45)
TIME_BOOT = time(7, 50)
TIME_PRESUBSCRIBE = time(7, 55)
TIME_PRE_NXT_OPEN = time(8, 0)             # NXT 프리 진입 (익일 청산 + VB/LTV PRE_NXT 시작)
TIME_KRX_OPEN_CONFIRM = time(9, 0, 5)      # KRX 메인 시가 확정 → VB/LTV MAIN 매매
TIME_SCAN_START = time(9, 30)              # 모멘텀 스캔
TIME_KRX_MAIN_BUY_STOP = time(15, 20)      # KRX 메인 신규 매수 중단 + 강제 청산
TIME_KRX_MAIN_CLOSE = time(15, 30)         # KRX 메인 마감 → NXT 애프터 전환
TIME_NXT_POST_BUY_STOP = time(19, 50)      # NXT 애프터 신규 매수 중단 (안전 마감, 변경 금지)
TIME_RECOMMENDATION = time(20, 0)          # AI자문 (Phase 0, 2026-05-15: 19:50 → 20:00 이동 — 백테스트 검증 정합성)
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
STALE_FRESHNESS_SECS = 60                   # 이 시간 내 tick 없으면 stale 판정 (F1 의 VERIFY_FRESHNESS_SECS 동일)
# 사이클 17 보강 (2026-05-19) — KIS 공식 답변 반영 ("기 요청된 목록 관리하여 기등록한 사항을 재등록하지 않도록").
# 1~5회 재SEND (`pool.resend_subscribe_for_ticker`) 분기 폐기 → 첫 stale 즉시 unsubscribe + subscribe(HIGH,
# bypass_limit=True) 강제 재등록. KIS 정상 "신규 등록" 패턴 (재SEND 0건). 5/12 silent inactive 사고
# 안전망 보존. retry > MAX 면 skip — 다음 _scan_loop 위임 (영구 stale 의심 종목 보호).
STALE_FORCE_REREGISTER_AFTER = 5            # (deprecated, 호환 보존) — 분기 임계가 아닌 회귀 가드 의미만 유지. 실제 동작은 MAX_STALE_RETRIES.
MAX_STALE_RETRIES = 5                       # 연속 N회 초과 stale 시 skip (영구 stale 의심). 6회 이상 → 다음 _scan_loop 위임.

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
        # ticker -> 연속 stale 사이클 수 (fresh 회복 시 자동 clear, _reset_daily_state 에서도 clear)
        self._stale_retry_count: dict[str, int] = {}
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

            # 20:10 정산
            await self._wait_until(TIME_SETTLEMENT)
            self._phase = "settling"
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

        except Exception:
            logger.exception("매매 프로세스 오류")
            await write_log("ERROR", "매매 프로세스 비정상 종료")
        finally:
            # 사이클 13-E-2 — ws_task / scan_task 도 self.* 속성화 후 동일 cancel 루프 포함.
            # 정리 순서: 백그라운드 task 7종 cancel → 메인 ws disconnect → pool stop.
            # ws_task 가 살아있으면 disconnect 가 race 가능 → cancel 을 먼저.
            # 백그라운드 task lifecycle — 비정상 종료 시 좀비 task 방지
            for task_attr in (
                "_next_day_task", "_session_task", "_stale_watcher_task",
                "_swing_poll_task", "_swing_rest_poll_task",
                "_5xx_dedupe_summary_task",
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
            await write_log("INFO", "매매 시스템 종료")

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
            await self.start()

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
            "_swing_poll_task", "_swing_rest_poll_task",
            "_5xx_dedupe_summary_task",
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
        await unsubscribe_all()
        await kis_ws.disconnect()
        # 추가: 수동 중지 시에도 동일 보장
        try:
            from src.realtime.websocket_pool import kis_ws_pool as _wsp
            await _wsp.stop()
        except Exception:
            logger.warning("[scheduler_stop] pool.stop 실패", exc_info=True)
        await write_log("INFO", "매매 시스템 수동 중지")

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
                logger.info(
                    "트레일링 스탑 모드: %s 갭률 %.1f%% (전략: %s)",
                    t(ticker), gap_rate, strategy_id,
                )
                await write_log("INFO", f"트레일링 스탑 모드: {t(ticker)} 갭률 {gap_rate:.1f}% ({strategy_id})")
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
        """돌파 전략(VB, MB)의 스캔 종목을 합산한다."""
        tickers: list[str] = []
        for sid in ("volatility_breakout", "long_tail_volatility"):
            strategy = self.registry.get(sid)
            if strategy and strategy.config.enabled and hasattr(strategy, 'get_scanned_tickers'):
                tickers.extend(strategy.get_scanned_tickers())
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
        - `swing`      : donchian_swing.get_scanned_tickers() 개수
        - `momentum`   : momentum_tickers 인자 길이 (scan_stocks() 결과)
        - `positions`  : 모든 전략 보유 포지션 합산 (중복 가능)

        합집합 후 실제 구독 개수는 `subscribe_filtered_stocks` 가 자체 계산해 `total=` 로 노출.
        어제(2026-05-11) "기타 23종목" 표기에서 VB/LTV 0건 식별 불가 결함 보완.
        """
        counts: dict[str, int] = {
            "vb": 0,
            "ltv": 0,
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
        - breakout        : `_collect_breakout_tickers()` (volatility_breakout + long_tail_volatility)

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

            allowed = get_tradable_boards(sid, strategy.config.params)
            keeps_post_nxt = MarketBoard.POST_NXT in allowed
            if keeps_post_nxt:
                logger.info("%s POST_NXT 활성 — 15:20 강제 청산 보류, 19:50 매수 중단까지 유지", strategy.config.name)
                continue

            clear_tickers = strategy.check_force_clear()
            if not clear_tickers:
                continue

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

        1차: DB positions 테이블에서 포지션 복구 (정확한 매수가/전략/매수일)
        2차: KIS 잔고 API와 교차 검증 — DB에 없지만 KIS에 있으면 보완 등록

        사이클 20 (2026-05-20) — 진입 초입에 `_preissue_all_tokens()` 호출:
        - 메인 + 보조 N 매니저 토큰을 분당 1개 한도 직렬화로 사전 발급
        - 캐시 hit 시 0초 / miss 시 N분 boot 지연 (07:50 라 KRX 영향 0)
        """
        # 사이클 20 — 모든 매니저 사전 순차 발급 (KIS 분당 1개 한도)
        await self._preissue_all_tokens()

        await token_manager.get_token()

        # DB에서 전략 설정(비중/파라미터) 로드
        await self._load_strategy_config()

        holdings, summary = await get_balance()

        # 사이클 2 (2026-05-17): 시장 레짐 fetch + snapshot INSERT + cash_usage_ratio 자동 조정.
        # `DKSTOCK_REGIME_ENABLED=false` 면 empty regime (graceful, 외부 호출 0건).
        # 외부 fetch 실패 시에도 empty regime → 매수 가드 비활성 + 운영자 수동 cash_usage_ratio 보존.
        # `auto_regime_adjust=true` 면 레짐 cash_min 기반 자동 갱신, false 면 수동값 그대로.
        await self._refresh_market_regime_and_persist()
        ratio = await self._resolve_cash_usage_ratio()

        # J3 (2026-05-12): 매매 가용 자금 비율 적용 — `system_config.cash_usage_ratio`.
        # 변경 즉시 적용 안 함, 다음 _boot() 부터 반영. Settings UI 안내 "다음 영업일부터 반영".
        available_for_trading = int(summary.net_asset * ratio)
        self.registry.allocate_funds(available_for_trading)
        logger.info(
            "[cash_usage_ratio] net_asset=%d ratio=%.2f available=%d",
            summary.net_asset, ratio, available_for_trading,
        )
        await write_log(
            "INFO",
            f"[cash_usage_ratio] net_asset={summary.net_asset} "
            f"ratio={ratio:.2f} available={available_for_trading}",
        )

        # 전략별 prepare 호출
        for strategy in self.registry.enabled():
            try:
                await strategy.prepare()
            except Exception:
                logger.exception("전략 prepare 실패: %s", strategy.strategy_id)

        from src.engine.strategy_base import Position
        from src.engine.scanner import ticker_names

        today = date.today()
        yesterday = today - timedelta(days=1)

        # 1차: DB positions 테이블에서 포지션 복구
        from src.db.positions import load_all as load_db_positions
        db_positions = await load_db_positions()
        db_restored = 0

        # KIS 잔고의 실제 보유종목 (6자리 영숫자 — ETF·ETN·신주인수권 등 알파벳 포함 종목 포함)
        kis_tickers = {
            h.ticker for h in holdings
            if h.quantity > 0 and len(h.ticker) == 6 and h.ticker.isalnum()
        }

        for row in db_positions:
            ticker = row["ticker"]
            # KIS 잔고에도 있는 종목만 복구 (이미 매도된 종목 방지)
            if ticker not in kis_tickers:
                from src.db.positions import delete_position
                await delete_position(ticker)
                logger.info("DB 포지션 정리 (KIS 미보유): %s", ticker)
                continue

            strategy_id = row["strategy_id"]
            target = self.registry.get(strategy_id) or self.registry.get("momentum")
            if not target:
                continue

            buy_dt = date.fromisoformat(row["buy_date"]) if row.get("buy_date") else yesterday
            target.state.positions[ticker] = Position(
                ticker=ticker,
                buy_price=row["buy_price"],
                quantity=row["quantity"],
                order_no=row.get("order_no", ""),
                strategy_id=target.strategy_id,
                buy_date=buy_dt,
                high_since_buy=row.get("high_since_buy", 0),
            )
            if row.get("ticker_name"):
                ticker_names[ticker] = row["ticker_name"]
            db_restored += 1
            logger.info(
                "DB 포지션 복구: %s %d주 @ %d (%s, 전략: %s)",
                row.get("ticker_name") or ticker, row["quantity"], row["buy_price"],
                "당일매수" if buy_dt == today else "익일청산",
                target.strategy_id,
            )

        # 2차: KIS 잔고에 있지만 DB에 없는 종목 보완
        db_tickers = {row["ticker"] for row in db_positions}
        kis_only = 0
        for h in holdings:
            if h.quantity <= 0:
                continue
            if not (len(h.ticker) == 6 and h.ticker.isalnum()):
                continue
            if h.ticker in db_tickers:
                continue
            if self.registry.is_ticker_held_by_any(h.ticker):
                continue

            # DB에 없는 종목 — trade_history에서 전략 확인 + KIS 주문체결내역으로 매수일 판정
            buy_price = int(h.avg_price)
            buy_dt = yesterday  # 기본 전일 매수로 간주
            strategy_id = "momentum"

            # trade_history에서 전략 정보 조회
            try:
                from src.db.supabase import supabase as _sb
                th_result = _sb.table("trade_history").select("strategy").eq(
                    "ticker", h.ticker
                ).eq("trade_type", "BUY").order(
                    "timestamp", desc=True
                ).limit(1).execute()
                if th_result.data:
                    strategy_id = th_result.data[0].get("strategy", "momentum")
            except Exception:
                pass

            try:
                orders = await get_daily_orders()
                for order in orders:
                    if order.get("pdno") == h.ticker and order.get("sll_buy_dvsn_cd") == "02":
                        avg = int(order.get("avg_prvs", "0"))
                        if avg > 0:
                            buy_price = avg
                        buy_dt = today
                        break
            except Exception:
                pass

            target = self.registry.get(strategy_id)
            if target:
                target.state.positions[h.ticker] = Position(
                    ticker=h.ticker,
                    buy_price=buy_price,
                    quantity=h.quantity,
                    order_no="",
                    strategy_id=strategy_id,
                    buy_date=buy_dt,
                )
                if h.name:
                    ticker_names[h.ticker] = h.name
                # DB에도 저장
                from src.db.positions import save_position
                await save_position(
                    ticker=h.ticker, ticker_name=h.name,
                    buy_price=buy_price, quantity=h.quantity,
                    order_no="", strategy_id=strategy_id, buy_date=buy_dt,
                )
                kis_only += 1
                logger.warning(
                    "KIS 잔고 보완 복구: %s %d주 @ %d (%s, 전략: %s)",
                    h.name or h.ticker, h.quantity, buy_price,
                    "당일매수" if buy_dt == today else "익일청산",
                    strategy_id,
                )

        # PENDING 매수 기록 일괄 COMPLETED 처리
        try:
            from src.db.supabase import supabase
            for ticker in kis_tickers:
                supabase.table("trade_history").update(
                    {"status": "COMPLETED"}
                ).eq("ticker", ticker).eq(
                    "trade_type", "BUY"
                ).eq("status", "PENDING").execute()
        except Exception:
            pass

        # 당일 전체 주문 내역 조회 (DB 동기화 + 미체결 복구에 공용)
        all_orders: list[dict] = []
        try:
            all_orders = await get_daily_orders()
        except Exception:
            logger.warning("당일 주문내역 조회 실패")

        # DB에 누락된 체결 내역 동기화
        try:
            await self._sync_orders_to_db(all_orders)
        except Exception:
            logger.warning("DB 동기화 실패")

        # 미체결 매수 주문의 전략 매핑 (DB 포지션 + trade_history 기반)
        db_strategy_map: dict[str, str] = {
            row["ticker"]: row["strategy_id"]
            for row in db_positions if row.get("strategy_id")
        }
        try:
            from src.db.supabase import supabase as _sb2
            th_buys = _sb2.table("trade_history").select("ticker, strategy").eq(
                "trade_type", "BUY"
            ).gte(
                "timestamp", today.isoformat()
            ).execute()
            for row in (th_buys.data or []):
                if row["ticker"] not in db_strategy_map:
                    db_strategy_map[row["ticker"]] = row.get("strategy", "momentum")
                # 당일 매수 종목을 해당 전략 sold_today에 시드 — 서버 재기동 race로 같은 종목이
                # 짧은 시간에 여러 번 매수되던 결함 차단(모멘텀 `_prev_prdy_rate` 휘발 + 보유 가드 race).
                # 의미적으론 매도가 아니지만 모든 전략의 check_buy_signal이 sold_today를 가드로 사용하므로
                # 같은 영업일 재매수 차단 효과 즉시 확보.
                seed_sid = row.get("strategy") or "momentum"
                seed_strategy = self.registry.get(seed_sid)
                if seed_strategy:
                    seed_strategy.state.sold_today.add(row["ticker"])
        except Exception:
            pass

        # 미체결 매수 주문 복구 → pending_buys에 등록하여 중복 주문 방지
        unfilled_count = 0
        for order in all_orders:
            if order.get("sll_buy_dvsn_cd") != "02":  # 매수만
                continue
            rmn_qty = int(order.get("rmn_qty", "0"))
            if rmn_qty <= 0:
                continue
            ticker = order.get("pdno", "")
            if not ticker:
                continue
            # 이미 어떤 전략에 포지션이 있으면 건너뜀
            if self.registry.is_ticker_held_by_any(ticker):
                continue
            # 미체결 매수 주문 존재 → 해당 전략의 pending_buys에 등록
            strategy_id = db_strategy_map.get(ticker, "momentum")
            target_strategy = self.registry.get(strategy_id) or self.registry.get("momentum")
            order_unpr = int(order.get("ord_unpr", "0"))
            if target_strategy:
                target_strategy.state.pending_buys.add(ticker)
                # 잔여 자금 폴백 계산용 — pending_buys 와 동기 등록 (2026-05-11 P1)
                target_strategy.state.pending_buy_amounts[ticker] = order_unpr * rmn_qty
            order_no = order.get("odno", "")
            self.order_engine._pending_buy_orders[order_no] = {
                "ticker": ticker,
                "price": order_unpr,
                "quantity": rmn_qty,
                "strategy_id": strategy_id,
            }
            self.order_engine._order_qty[order_no] = int(order.get("ord_qty", "0"))
            self.order_engine._order_strategy[order_no] = strategy_id
            self.order_engine._order_ticker[order_no] = ticker
            unfilled_count += 1
            logger.info("미체결 주문 복구: %s %d주 (주문번호: %s, 전략: %s)", ticker, rmn_qty, order_no, strategy_id)

        total_pos = sum(len(s.state.positions) for s in self.registry.all())
        await write_log(
            "INFO",
            f"기동 완료: 순자산 {summary.net_asset:,}원, "
            f"보유 {total_pos}종목 (DB복구: {db_restored}, KIS복원: {kis_only}, 미체결: {unfilled_count})",
        )
        logger.info(
            "기동 완료: 순자산 %s, 보유 %d종목 (DB복구: %d, KIS복원: %d, 미체결: %d)",
            summary.net_asset, total_pos, db_restored, kis_only, unfilled_count,
        )

        # I3 (2026-05-12): 보유 + 익일청산 후보 ticker 의 stock_master 캐시 eager 갱신.
        # Phase G lazy 한계 — 첫 사이클 캐시 miss 시 SOR/NXT 그대로 발사 → KIS 거부.
        # 2026-05-12 09:00:12 KST 계양전기(012200) NEXT_DAY_CLEAR SOR 거부 사례 대응.
        try:
            await self._eager_refresh_stock_master_for_held_positions()
        except Exception:
            logger.exception("[stock_master_eager] _boot 후 eager 갱신 실패 — lazy 경로로 자연 보강")

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
            await persist_snapshot(regime, date.today())
        except Exception:
            logger.exception("[market_regime] snapshot INSERT 실패 — 메모리 레짐 유효")

        # 운영 가시성: regime + 매수가드 + 자동조정 결과 1행
        try:
            await write_log(
                "INFO",
                f"[market_regime] regime={regime.regime} "
                f"buy_blocked={regime.buy_blocked} "
                f"block_reason={regime.block_reason} "
                f"cash_min={regime.cash_min} "
                f"computed_ratio={regime.computed_cash_usage_ratio()}",
            )
        except Exception:
            pass

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
                logger.exception("stock_master eager 갱신 실패: %s", ticker)
                await write_log(
                    "WARNING",
                    f"[stock_master_eager] 갱신 실패 ticker={ticker}",
                )

        logger.info(
            "[stock_master_eager] 보유+익일청산 %d종목 갱신 완료 (refreshed=%d, skipped=%d)",
            len(tickers), refreshed, skipped,
        )
        await write_log(
            "INFO",
            f"[stock_master_eager] total={len(tickers)} refreshed={refreshed} skipped={skipped}",
        )

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
        from src.db.trade_history import insert_trade, get_today_buy_trades
        from src.models.trade import TradeRecord, TradeStatus, TradeType

        if not orders:
            return

        # 기존 DB 기록: 매수/매도 각각 조회
        existing_buys = await get_today_buy_trades()
        existing_buy_keys = {(row["ticker"], row.get("order_no", "") or "") for row in existing_buys}

        from src.db.trade_history import get_today_sell_trades
        existing_sells = await get_today_sell_trades()
        existing_sell_keys = {(row["ticker"], row.get("order_no", "") or "") for row in existing_sells}

        # DB 매수 기록에서 strategy 매핑 (매도 시 참조)
        db_strategy_map = {row["ticker"]: row.get("strategy", "momentum") for row in existing_buys}

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

                # 사이클 13-D (2026-05-18): stale 우선 재구독.
                # K stale watcher 가 120s 주기로 발화하는데 _scan_loop 는 5분 주기다.
                # 통합 구독 직후 1행으로 stale 종목을 HIGH 우선순위로 즉시 재구독해
                # 5분 주기의 자연 회복 경로를 별도 추가한다. cap=10 + 50ms sleep 으로
                # KIS Rate Limit 보호. 본체 예외는 흡수 — 다음 사이클 자연 재시도.
                try:
                    await self._resubscribe_stale_priority(cap=10)
                except Exception:
                    logger.exception("_resubscribe_stale_priority 실패 — 다음 사이클 자연 재시도")

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

    async def _reprepare_breakout_if_empty(self) -> None:
        """VB/LTV 의 `_scanned_tickers` 가 비어있으면 prepare() 를 1회 재시도한다.

        - 매 _scan_loop 사이클 1회 발화 (성공/실패 무관하게 다음 5분 사이클에 자연 재시도)
        - donchian_swing 은 대상 아님 (고정 유니버스이므로 prepare 실패해도 KOSPI200/KOSDAQ150 사용)
        - prepare() 가 raise 해도 가드 본체는 예외를 흡수하여 _scan_loop sleep/cancel 흐름을 보존한다
        """
        for sid in ("volatility_breakout", "long_tail_volatility"):
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

            logger.warning("VB/LTV 후보 비어있음 — 재 prepare 시도: %s", sid)
            try:
                await write_log("WARNING", f"{sid} 후보 비어있음 — 재 prepare 시도")
            except Exception:
                logger.debug("write_log WARNING 실패: %s", sid)

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
        logger.info(
            "[swing_rest_poll] candidates=%d held=%d pending=%d updated=%d failed=%d elapsed_ms=%d",
            stats["candidates"], stats["held"], stats["pending"],
            stats["updated"], stats["failed"], stats["elapsed_ms"],
        )
        try:
            await write_log(
                "INFO",
                f"[swing_rest_poll] candidates={stats['candidates']} held={stats['held']} "
                f"pending={stats['pending']} updated={stats['updated']} failed={stats['failed']} "
                f"elapsed_ms={stats['elapsed_ms']}",
            )
        except Exception:
            # system_logs 실패는 swallow — 본체 흐름 보존
            pass
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
        """30s 주기 stale 감지 + 자동 재구독 (K, 2026-05-12).

        KIS WebSocket silent inactive(구독은 됐는데 시세 송신 없음) 즉시 복구.
        F1(재연결 직후 1회) + `_scan_loop`(5분 주기) + K(30s) 3중 안전망.

        - 매 사이클 `_check_and_resubscribe_stale()` 호출
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

    async def _check_and_resubscribe_stale(self) -> None:
        """현재 TICK 구독 종목 중 stale 한 것에 대해 강제 재등록 (K).

        사이클 17 보강 (2026-05-19) — KIS 공식 답변 반영. 1~5회 `resend_subscribe_for_ticker`
        (같은 종목 재SEND) 분기 완전 폐기. KIS 답변 인용: "기 요청된 목록을 관리하여 기등록한
        사항을 재등록하지 않도록 부탁드립니다. (다수 요청 시 LMS + 앱정보 이용중지 처리)"
        첫 stale 즉시 unsubscribe + subscribe(HIGH, bypass_limit=True) 강제 재등록 ←
        KIS 정상 "신규 등록" 패턴. 5/12 silent inactive 사고 안전망 보존.

        흐름:
        1. `kis_ws_pool.get_subscribed_tickers()` 로 TICK 구독 집합 조회
        2. 비어있으면 즉시 return (retry_count 보존 — 다음 구독 시 자연 회복)
        3. `scanner.ticker_last_tick` 비교: `STALE_FRESHNESS_SECS` 초과면 stale
        4. 전체 fresh 시 `_stale_retry_count.clear()` (회복 누적값 초기화)
        5. stale ticker 별로:
           - retry > MAX_STALE_RETRIES (=5, 6회 이상) → skip (영구 stale 의심, 다음 _scan_loop 위임)
           - 그 외 (1~5회) → `pool.unsubscribe_in_pool` + `pool.subscribe(priority=HIGH, bypass_limit=True)`
             강제 재등록 (KIS 정상 패턴, 재SEND 0건)
        6. Rate Limit 보호: 각 종목별 50ms sleep

        안전 불변식:
        - `_subscriptions` set 직접 수정 금지 — `pool` 인터페이스만 사용
        - 강제 재등록은 `bypass_limit=True` (보유/익일청산 종목 영향 없음, 한도 검사 skip)
        - 종목별 예외는 격리해 다른 stale ticker 영향 차단
        - `pool.resend_subscribe_for_ticker` 호출 금지 (KIS 측 부담 + LMS 위험)
        """
        from src.engine.scanner import KST_TZ as _KST_TZ, TICK_TR_ID, ticker_last_tick
        # 사이클 7-C — 풀의 분배 추적을 활용한 stale watcher
        from src.realtime.websocket_pool import kis_ws_pool

        # 사이클 13-E (2026-05-18): 메인 단독 → 풀 전체로 확장. 사이클 7-C 풀 통합 시
        # 함수 진입점 갱신 누락 결함 — 메인 세션 비어있을 때(보유 0, 시세는 보조에 집중)
        # 즉시 return 으로 stale_watcher 본체가 영원히 발동 안 하던 결함 차단.
        subscribed = kis_ws_pool.get_subscribed_tickers()
        if not subscribed:
            return

        now = datetime.now(_KST_TZ)
        threshold = timedelta(seconds=STALE_FRESHNESS_SECS)
        min_dt = datetime.min.replace(tzinfo=_KST_TZ)
        stale_tickers = sorted(
            t for t in subscribed
            if (now - ticker_last_tick.get(t, min_dt)) > threshold
        )

        if not stale_tickers:
            # 모두 fresh — 누적 retry 카운터 리셋 (회복 케이스)
            self._stale_retry_count.clear()
            return

        force_reregistered = 0
        skipped_giveup = 0

        for ticker in stale_tickers:
            retry = self._stale_retry_count.get(ticker, 0) + 1
            self._stale_retry_count[ticker] = retry

            if retry > MAX_STALE_RETRIES:
                # 6회 이상 → 영구 stale 의심 (거래정지·이상 종목 등). skip + 다음 _scan_loop 위임
                # (사이클 17 보강 — KIS 답변 반영, 재SEND 분기 폐기)
                skipped_giveup += 1
                continue

            # 1~5회 — 첫 stale 즉시 강제 재등록 (KIS 정상 "신규 등록" 패턴, 재SEND 0건)
            # KIS 공식 답변: "기등록한 사항을 재등록하지 않도록" (LMS + 앱정보 이용중지 위험)
            try:
                await kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)
                await asyncio.sleep(0.05)
                await kis_ws_pool.subscribe(
                    TICK_TR_ID, ticker,
                    priority="HIGH", bypass_limit=True,
                )
                force_reregistered += 1
            except Exception:
                logger.exception("[stale_watcher] 강제 재등록 실패: %s", ticker)

            await asyncio.sleep(0.05)  # Rate Limit 보호

        logger.info(
            "[stale_watcher] subscribed=%d stale=%d force_reregistered=%d skipped=%d",
            len(subscribed), len(stale_tickers), force_reregistered, skipped_giveup,
        )
        try:
            await write_log(
                "INFO",
                f"[stale_watcher] subscribed={len(subscribed)} stale={len(stale_tickers)} "
                f"force_reregistered={force_reregistered} skipped={skipped_giveup}",
            )
        except Exception:
            # fire-and-forget — system_logs 실패해도 재구독 흐름 보존
            logger.debug("[stale_watcher] write_log 실패", exc_info=True)

    async def _delta_unsubscribe_dropped(self, new_set: set[str]) -> list[str]:
        """`_scan_loop` 의 새 합집합에서 빠진 종목만 unsubscribe (사이클 15-A, 2026-05-19).

        KIS 공지의 "비정상 케이스 2" (무한 등록/해제 반복) 패턴 차단.
        기존 `unsubscribe_all()` 전체 해제 → 빠진 종목 (delta_remove) 만 unsubscribe.

        흐름:
        1. 현재 풀 TICK 구독 합집합 `kis_ws_pool.get_subscribed_tickers()` 조회
        2. `delta_remove = current - new_set` 계산
        3. 각 종목 `kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)` 호출
        4. 종목 간 50ms sleep — KIS Rate Limit 보호
        5. 종목별 예외 격리

        Returns:
            unsubscribe 한 ticker 리스트 (테스트/모니터링용)

        안전 불변식:
        - TICK_TR_ID 종목만 처리 — 체결통보(H0STCNI0/9) / 장운영정보(H0UNMKO0) 영향 0
        - `_subscriptions` set 직접 수정 금지 — `kis_ws_pool.unsubscribe` 만 사용
        - 본체 예외는 호출자(`_scan_loop`)가 try/except 로 흡수
        """
        from src.engine.scanner import TICK_TR_ID
        from src.realtime.websocket_pool import kis_ws_pool

        current = kis_ws_pool.get_subscribed_tickers()
        delta_remove = sorted(current - new_set)
        if not delta_remove:
            return []

        unsubscribed: list[str] = []
        for ticker in delta_remove:
            try:
                await kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)
                unsubscribed.append(ticker)
            except Exception:
                logger.exception("[delta_unsubscribe] %s 실패", ticker)
            await asyncio.sleep(0.05)

        logger.info(
            "[scan_loop_delta] unsubscribed=%d tickers=%s",
            len(unsubscribed), unsubscribed[:10],
        )
        try:
            await write_log(
                "INFO",
                f"[scan_loop_delta] unsubscribed={len(unsubscribed)} "
                f"tickers={unsubscribed[:10]}",
            )
        except Exception:
            logger.debug("[scan_loop_delta] write_log 실패", exc_info=True)
        return unsubscribed

    async def _resubscribe_stale_priority(self, cap: int = 10) -> list[str]:
        """`_scan_loop` 통합 구독 직후 stale 종목을 HIGH 우선순위로 즉시 재구독한다.

        K stale watcher 는 120s 주기로 발화하고 (사이클 9 — KIS 차단 회피),
        `_scan_loop` 는 5분(300s) 주기다. WS silent inactive 발생 시 회복 시간이
        최대 120s ~ 600s 까지 늘어진다. 본 헬퍼는 5분 주기의 별도 자연 회복 경로
        — 통합 구독 직후 stale 종목을 HIGH 우선순위로 즉시 재구독한다.

        흐름:
        1. `scanner.ticker_last_tick` 풀 전체 합집합 사용 (메인+보조 — `risk.on_tick` 단일 진입점)
        2. 현재시각 - last_tick > `STALE_FRESHNESS_SECS`(=60s) 종목만 수집
        3. 최대 `cap` 건 (기본 10) — KIS Rate Limit 보호
        4. 각 종목에 `kis_ws_pool.subscribe(TICK_TR_ID, ticker, priority='HIGH', bypass_limit=True)` 호출
        5. 종목 간 50ms sleep
        6. 종목별 예외 격리 (continue, ERROR 로그)

        Returns:
            재구독한 ticker 리스트 (호출 카운트 + 회귀 검증용)

        안전 불변식:
        - `_subscriptions` set 직접 수정 금지 — `kis_ws_pool.subscribe` 만 사용
        - HIGH + bypass_limit=True 로 보유 종목과 동일 우선순위 (메인 fallback 허용)
        - 종목별 예외는 격리해 다른 stale ticker 영향 차단
        - 본체 예외는 호출자(`_scan_loop`)가 try/except 로 흡수 — 다음 사이클 자연 재시도
        """
        from src.engine.scanner import KST_TZ as _KST_TZ, TICK_TR_ID, ticker_last_tick
        from src.realtime.websocket_pool import kis_ws_pool

        now = datetime.now(_KST_TZ)
        threshold = timedelta(seconds=STALE_FRESHNESS_SECS)
        min_dt = datetime.min.replace(tzinfo=_KST_TZ)

        # sorted 로 결정적 순서 보장 — cap 적용 시 동일 입력에 동일 출력
        stale_tickers = sorted(
            t for t, last in ticker_last_tick.items()
            if (now - last if isinstance(last, datetime) else now - min_dt) > threshold
        )

        if not stale_tickers:
            return []

        targets = stale_tickers[:cap]
        resubscribed: list[str] = []

        for ticker in targets:
            try:
                await kis_ws_pool.subscribe(
                    TICK_TR_ID, ticker,
                    priority="HIGH", bypass_limit=True,
                )
                resubscribed.append(ticker)
            except Exception:
                logger.exception("[stale_priority_resubscribe] 재구독 실패: %s", ticker)
                continue
            await asyncio.sleep(0.05)  # Rate Limit 보호

        logger.info(
            "[stale_priority_resubscribe] count=%d tickers=%s",
            len(resubscribed), resubscribed,
        )
        try:
            await write_log(
                "INFO",
                f"[stale_priority_resubscribe] count={len(resubscribed)} "
                f"tickers={resubscribed}",
            )
        except Exception:
            # fire-and-forget — system_logs 실패해도 재구독 흐름 보존
            logger.debug("[stale_priority_resubscribe] write_log 실패", exc_info=True)

        return resubscribed

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
            today = date.today()

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

        # P1(B) 익일 청산 보류 set 도 매일 초기화
        self._pending_next_day_clear.clear()

        # K (2026-05-12) — stale_watcher 종목별 연속 stale 카운터 매일 초기화
        self._stale_retry_count.clear()

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

        logger.info("일간 상태 초기화 완료 (scanner 캐시 clear 포함)")

    async def _wait_until(self, target: time) -> None:
        """지정 시각까지 대기한다."""
        while self._running:
            now = datetime.now().time()
            if now >= target:
                break
            await asyncio.sleep(10)


trading_scheduler = TradingScheduler()
