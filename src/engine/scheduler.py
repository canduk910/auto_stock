"""매매 스케줄러.

- 08:25 기동: 토큰 갱신, 잔고 동기화
- 08:30~16:00 매매 프로세스 가동
- 16:10 정산: daily_performance 기록, 프로세스 정리
"""

import asyncio
import logging
from datetime import date, datetime, time, timedelta

from src.api.balance import get_balance, get_daily_orders
from src.auth.token import token_manager
from src.db.daily_performance import get_latest_performance, recompute_from_trades, upsert_daily_performance
from src.db.system_logs import write_log
from src.engine.order_engine import OrderEngine
from src.engine.risk import RiskManager
from src.engine.scanner import scan_stocks, subscribe_filtered_stocks, unsubscribe_all
from src.engine.strategy_base import Signal, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.realtime.handler import dispatch_message, register_execution_handler, register_tick_handler
from src.realtime.websocket import kis_ws

logger = logging.getLogger(__name__)

TIME_AUTO_START = time(8, 20)
TIME_BOOT = time(8, 25)
TIME_MARKET_OPEN = time(8, 30)
TIME_PRESUBSCRIBE = time(8, 55)
TIME_NEXT_DAY_CLEAR = time(9, 0)
TIME_VB_OPEN_CONFIRM = time(9, 0, 5)
TIME_SCAN_START = time(9, 30)
TIME_BUY_STOP = time(15, 20)
TIME_MARKET_CLOSE = time(15, 30)
TIME_RECOMMENDATION = time(16, 0)
TIME_SETTLEMENT = time(16, 10)
SCAN_INTERVAL = 300  # 5분마다 스캔


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

        self.order_engine = OrderEngine(self.registry)
        self.risk_manager = RiskManager(self.registry, self.order_engine)
        self._running = False
        self._phase: str = "idle"
        self._config_loaded = False

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
        """매매 프로세스를 시작한다.

        현재 시각에 따라 적절한 단계부터 시작한다:
        - 08:25 이전: 08:25까지 대기 후 전체 스케줄 실행
        - 08:25~15:20: 즉시 부팅 + 현재 시각 이후 스케줄부터 실행
        - 15:20~16:10: 매수 중단 상태로 진입, 정산만 대기
        - 16:10 이후: 장 종료, 시작 불가
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

            # WebSocket 연결 (별도 태스크)
            ws_task = asyncio.create_task(
                kis_ws.connect(dispatch_message)
            )

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

            now = datetime.now().time()

            # 08:55 사전 구독: 돌파 종목 + 보유 포지션
            # → 09:00:00 시가를 WebSocket으로 즉시 수신 가능하게 함
            if now < TIME_PRESUBSCRIBE:
                self._phase = "presubscribe_wait"
                await self._wait_until(TIME_PRESUBSCRIBE)
            if now <= TIME_VB_OPEN_CONFIRM:
                # 08:25 boot 시점의 prepare에서 KIS API 미준비로 유니버스 0종목인 경우 재실행
                # (KIS inquire-price가 장 시작 전 부정확 → 시총/거래대금 필터 실패 사례)
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
                # 스윙 전략도 동일 안전망 — 보유 포지션이 없으면 _scanned_tickers가 곧 후보
                ds = self.registry.get("donchian_swing")
                if ds and ds.config.enabled and not ds.get_scanned_tickers():
                    logger.info("스윙 전략 유니버스 비어있음 → prepare 재실행")
                    await write_log("INFO", "스윙 유니버스 비어있어 prepare 재실행")
                    try:
                        await ds.prepare()
                    except Exception:
                        logger.exception("재 prepare 실패: donchian_swing")

                # 09:00:05 이전 진입 시 항상 사전구독 (kis_ws.subscribe는 set 기반이라 중복 안전)
                presub = self._collect_presubscribe_tickers()
                if presub:
                    await subscribe_filtered_stocks([], extra_tickers=presub)
                    logger.info("사전 구독: %d종목 (돌파 + 보유)", len(presub))
                    await write_log("INFO", f"사전 구독 {len(presub)}종목")

            # 09:00 익일 청산은 백그라운드로 (내부 60초 sleep) + 동시에 시가 확정
            next_day_task: asyncio.Task | None = None
            if now < TIME_NEXT_DAY_CLEAR:
                self._phase = "next_day_clear"
                await self._wait_until(TIME_NEXT_DAY_CLEAR)
            if now <= TIME_VB_OPEN_CONFIRM:
                next_day_task = asyncio.create_task(self._execute_next_day_clear())
                # 5초 폴링으로 돌파 시가 확정 → 09:00:05 매매 진입
                await self._confirm_breakout_open_prices()
                if self._collect_breakout_tickers():
                    self._phase = "vb_trading"
                    logger.info("돌파 전략 매매 시작 (09:00:05 전후)")
                    await write_log("INFO", "돌파 전략 매매 시작")
            elif now <= TIME_SCAN_START:
                # 09:00:05 이후 중간 부팅 — 사전구독 + 시가 확정 즉시 실행
                presub = self._collect_presubscribe_tickers()
                if presub:
                    await subscribe_filtered_stocks([], extra_tickers=presub)
                await self._confirm_breakout_open_prices()
                if self._collect_breakout_tickers():
                    self._phase = "vb_trading"
                    logger.info("돌파 전략 매매 시작 (중간 부팅): %d종목", len(presub))

            # 09:30~ 종목 스캔 + 매매
            if now < TIME_SCAN_START:
                self._phase = "scanning"
                await self._wait_until(TIME_SCAN_START)

            if now < TIME_BUY_STOP:
                # 스캔 + 매매 모드 진입
                tickers = await scan_stocks()
                extra = self._collect_breakout_tickers() + self._collect_swing_tickers()
                await subscribe_filtered_stocks(tickers, extra_tickers=extra)

                # 09:00:05 이후 시작이면 시가 확정 재시도 (KIS API 조회)
                if now > TIME_VB_OPEN_CONFIRM:
                    await self._confirm_breakout_open_prices()

                self._phase = "trading"
                scan_task = asyncio.create_task(self._scan_loop())
                logger.info("매매 모드 진입")

                # 15:20까지 대기
                await self._wait_until(TIME_BUY_STOP)
                scan_task.cancel()
            else:
                logger.info("15:20 이후 시작 — 매수 중단 상태로 진입")

            # 15:20 신규 매수 중단 + 당일 청산 전략 강제 청산
            self._phase = "buy_stopped"
            for s in self.registry.enabled():
                s.state.buy_disabled = True
            await self._force_clear_intraday_strategies()
            await write_log("INFO", "15:20 신규 매수 중단")

            # 15:30 장 마감, 구독 해제
            await self._wait_until(TIME_MARKET_CLOSE)
            self._phase = "closing"
            await unsubscribe_all()
            await write_log("INFO", "15:30 WebSocket 구독 해제")

            # 16:00 전략수정 AI자문 생성
            await self._wait_until(TIME_RECOMMENDATION)
            self._phase = "recommending"
            try:
                from src.engine.recommendation_engine import generate_recommendations
                await generate_recommendations()
                await write_log("INFO", "16:00 전략수정 AI자문 생성 완료")
            except Exception:
                logger.exception("전략수정 AI자문 생성 실패")
                await write_log("ERROR", "전략수정 AI자문 생성 실패")

            # 16:10 정산
            await self._wait_until(TIME_SETTLEMENT)
            self._phase = "settling"
            await self._settle()

            # 정산 직후: 일일 로그 분석 리포트 생성 (실패해도 정산엔 영향 없음)
            self._phase = "log_analysis"
            try:
                from src.engine.log_analysis_engine import generate_daily_log_report
                await generate_daily_log_report()
                await write_log("INFO", "일일 로그 분석 리포트 생성 완료")
            except Exception:
                logger.exception("일일 로그 분석 리포트 생성 실패")
                await write_log("ERROR", "일일 로그 분석 리포트 생성 실패")

            await kis_ws.disconnect()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass

        except Exception:
            logger.exception("매매 프로세스 오류")
            await write_log("ERROR", "매매 프로세스 비정상 종료")
        finally:
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
        await unsubscribe_all()
        await kis_ws.disconnect()
        await write_log("INFO", "매매 시스템 수동 중지")

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

        익일 청산을 지원하는 전략(momentum, long_tail_volatility)의 is_next_day 포지션을 처리한다.
        1. 전일 매수 보유 종목 목록 조회
        2. 각 종목의 당일 시가 확인 (WebSocket 시세 구독으로 수신)
        3. 60초 대기하여 시가 안정화 (대기 중 on_tick의 NEXT_DAY_CLEAR 억제)
        4. 시가가 매수가 대비 gap_up_threshold 이상 → 트레일링 스탑 모드
        5. gap_up_threshold 미만 → 즉시 시장가 전량 매도
        """
        # 익일 청산 대상 전략 수집 (momentum + long_tail_volatility)
        overnight_strategies: list[tuple[str, object]] = []
        for sid in ("momentum", "long_tail_volatility"):
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

        # 시가 안정화 대기 (09:01까지 60초 — on_tick의 NEXT_DAY_CLEAR 억제 구간)
        await asyncio.sleep(60)

        # 대기 완료 — on_tick 가드 해제
        for _, strategy in overnight_strategies:
            if hasattr(strategy, '_next_day_clear_pending'):
                strategy._next_day_clear_pending = False

        from src.engine.scanner import t, ticker_prices

        for ticker, pos, strategy_id in all_next_day:
            strategy = self.registry.get(strategy_id)
            if not strategy or ticker not in strategy.state.positions:
                continue  # 대기 중 손절로 이미 처리됨

            gap_up_threshold = strategy.config.params.get("gap_up_threshold", 10.0)

            # WebSocket에서 수신한 실제 시가 사용 (사전구독되어 있으면 09:00:00에 들어옴)
            price_data = ticker_prices.get(ticker, {})
            today_open = price_data.get("open_price", 0)
            if today_open <= 0:
                # 60초 대기에도 시가 미수신 → 짧은 폴링 + KIS API 폴백
                today_open = await self._resolve_open_price(ticker, max_wait_s=2.0)
            if today_open <= 0:
                today_open = pos.high_since_buy
                logger.warning("시가 미수신, high_since_buy 사용: %s (%d)", t(ticker), today_open)

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
                logger.info(
                    "익일 즉시 청산: %s 갭률 %.1f%% (전략: %s)",
                    t(ticker), gap_rate, strategy_id,
                )
                await self.order_engine.execute_sell(ticker, Signal.NEXT_DAY_CLEAR, strategy_id)
                await write_log("INFO", f"익일 즉시 청산 실행: {t(ticker)} 갭률 {gap_rate:.1f}% ({strategy_id})")

        logger.info("익일 청산 실행 완료")

    async def _confirm_breakout_open_prices(
        self, *, max_wait_s: float = 5.0, interval_s: float = 0.5,
    ) -> None:
        """돌파 전략(VB, MB)의 시가를 확정한다.

        1차: WebSocket ticker_prices 캐시를 max_wait_s 동안 interval_s 간격으로 폴링
            (사전구독되어 있으면 09:00:00 시가가 즉시 들어옴)
        2차: 폴링 종료 시점에도 미확정인 종목만 KIS 개별시세 API로 폴백 조회
        """
        from src.engine.scanner import ticker_prices

        # 대상 전략 + 종목 수집
        targets: list[tuple[str, object, list[str]]] = []  # (sid, strategy, ticker_list)
        for sid in ("volatility_breakout", "long_tail_volatility"):
            strategy = self.registry.get(sid)
            if not strategy or not strategy.config.enabled:
                continue
            if not hasattr(strategy, '_targets') or not hasattr(strategy, 'on_open_price_confirmed'):
                continue
            targets.append((sid, strategy, list(strategy._targets.keys())))

        if not targets:
            return

        # 1차: WebSocket 폴링 (max_wait_s 동안)
        elapsed = 0.0
        while elapsed < max_wait_s:
            all_done = True
            for _, strategy, tickers in targets:
                for ticker in tickers:
                    if strategy._open_confirmed.get(ticker, False):
                        continue
                    price_info = ticker_prices.get(ticker)
                    if price_info and price_info.get("open_price", 0) > 0:
                        strategy.on_open_price_confirmed(ticker, price_info["open_price"])
                    else:
                        all_done = False
            if all_done:
                break
            await asyncio.sleep(interval_s)
            elapsed += interval_s

        # 2차: 미확정 종목만 KIS API 폴백
        from src.api.condition import fetch_stock_detail
        for sid, strategy, tickers in targets:
            unconfirmed = [t for t in tickers if not strategy._open_confirmed.get(t, False)]
            for ticker in unconfirmed:
                try:
                    detail = await fetch_stock_detail(ticker)
                    open_price = int(detail.get("stck_oprc", "0"))
                    if open_price > 0:
                        strategy.on_open_price_confirmed(ticker, open_price)
                except Exception:
                    logger.debug("%s 시가 조회 실패: %s", sid, ticker)

            confirmed = sum(1 for t in tickers if strategy._open_confirmed.get(t, False))
            logger.info("%s 시가 확정: %d/%d종목", strategy.config.name, confirmed, len(tickers))

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
        - 스윙 전략(donchian_swing) 스캔 종목
        - 모든 전략의 보유 포지션 (모멘텀 익일청산/스윙 트레일링 시가 수신용)
        """
        tickers: set[str] = set(self._collect_breakout_tickers())
        tickers.update(self._collect_swing_tickers())
        for s in self.registry.all():
            tickers.update(s.state.positions.keys())
        return list(tickers)

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
        """15:20 당일 청산 전략(VB, MB)의 강제 청산."""
        from src.engine.scanner import t

        for sid in ("volatility_breakout", "long_tail_volatility"):
            strategy = self.registry.get(sid)
            if not strategy or not strategy.config.enabled:
                continue
            if not hasattr(strategy, 'check_force_clear'):
                continue

            clear_tickers = strategy.check_force_clear()
            if not clear_tickers:
                continue

            await write_log("INFO", f"{strategy.config.name} 강제 청산 대상: {clear_tickers}")
            for ticker in clear_tickers:
                if ticker in strategy.state.positions:
                    await self.order_engine.execute_sell(ticker, Signal.FORCE_CLEAR, sid)
                    logger.info("%s 강제 청산: %s", strategy.config.name, t(ticker))

    async def _boot(self) -> None:
        """시스템 기동: 토큰 갱신, 잔고 동기화 + 포지션 복구.

        1차: DB positions 테이블에서 포지션 복구 (정확한 매수가/전략/매수일)
        2차: KIS 잔고 API와 교차 검증 — DB에 없지만 KIS에 있으면 보완 등록
        """
        await token_manager.get_token()

        # DB에서 전략 설정(비중/파라미터) 로드
        await self._load_strategy_config()

        holdings, summary = await get_balance()

        # 전략별 자금 분배
        self.registry.allocate_funds(summary.net_asset)

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
            if target_strategy:
                target_strategy.state.pending_buys.add(ticker)
            order_no = order.get("odno", "")
            self.order_engine._pending_buy_orders[order_no] = {
                "ticker": ticker,
                "price": int(order.get("ord_unpr", "0")),
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
        """
        from src.db.trade_history import insert_trade, get_today_buy_trades
        from src.models.trade import TradeRecord, TradeStatus, TradeType

        if not orders:
            return

        # 기존 DB 기록: 매수/매도 각각 조회
        existing_buys = await get_today_buy_trades()
        existing_buy_tickers = {row["ticker"] for row in existing_buys}

        from src.db.trade_history import get_today_sell_trades
        existing_sells = await get_today_sell_trades()
        existing_sell_tickers = {row["ticker"] for row in existing_sells}

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

            if is_buy and ticker in existing_buy_tickers:
                continue
            if not is_buy and ticker in existing_sell_tickers:
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
            kis_order_no = order.get("odno", "")
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
                existing_buy_tickers.add(ticker)
            else:
                existing_sell_tickers.add(ticker)
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
                # 돌파(VB+LTV) + 스윙(donchian) + 모든 전략 보유 포지션 합집합으로 재구독
                # → 09:30 이후 5분 주기 unsubscribe 시 swing/LTV 시세가 끊겨 대시보드에서
                #   현재가/갭률이 비고 손절 감시도 누락되던 결함 차단
                extra = list(set(
                    self._collect_breakout_tickers()
                    + self._collect_swing_tickers()
                    + [t for s in self.registry.all() for t in s.state.positions.keys()]
                ))
                await unsubscribe_all()
                await subscribe_filtered_stocks(tickers, extra_tickers=extra)
            except Exception:
                logger.exception("종목 스캔 오류")

            # 체결통보 못 받았을 때를 대비한 포지션 동기화 (3회 스캔마다 = 15분)
            sync_counter += 1
            if sync_counter % 3 == 0:
                try:
                    await self._sync_positions_from_balance()
                except Exception:
                    logger.debug("포지션 동기화 실패")

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

        # 정산 후 전략별 일간 상태 초기화 (다음 날 _boot()에서 DB 기반으로 재구성)
        self._reset_daily_state()

    def _reset_daily_state(self) -> None:
        """일간 상태를 초기화한다. 정산 완료 후 호출."""
        for strategy in self.registry.all():
            strategy.state.positions.clear()
            strategy.state.pending_buys.clear()
            strategy.state.sold_today.clear()
            strategy.state.daily_realized_pnl = 0
            strategy.state.total_investment = 0
            strategy.state.buy_disabled = False
            strategy.state.buy_signals.clear()
            strategy.state.low_funds_tickers.clear()

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

        logger.info("일간 상태 초기화 완료")

    async def _wait_until(self, target: time) -> None:
        """지정 시각까지 대기한다."""
        while self._running:
            now = datetime.now().time()
            if now >= target:
                break
            await asyncio.sleep(10)


trading_scheduler = TradingScheduler()
