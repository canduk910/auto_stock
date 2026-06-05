"""리스크 관리 모듈.

- 실시간 시세에 따른 손절/익일청산 신호 감시
- 전략별 포지션 비중 제한
- 전략 간 중복 매수 방지
- 전략별 매매 가능 보드(KRX 메인 / NXT 프리 / NXT 애프터) 가드 — Phase 8
- **사이클 2 (2026-05-17)**: 시장 레짐 매수 가드 (defensive/VIX>25/F&G 극단 시 매수 차단).
  매도/손절 분기는 무관 — 보유 종목 청산 정상.
- **사이클 62 (2026-06-05)**: 가격 필터 (매수 진입 전용, 3 모드 HARD/WARN/OFF).
  check_exit_signal 분기 *후*, check_buy_signal 분기 *전* 가드 (사이클 38 명문화 보존).
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from src.db.system_config import PriceFilter, get_price_filter
from src.engine.daily_emit_cap import DailyEmitCap
from src.engine.market_regime import get_current_regime
from src.engine.order_engine import OrderEngine
from src.engine.session import session_tracker
from src.engine.strategy_base import Signal
from src.engine.strategy_registry import StrategyRegistry

logger = logging.getLogger(__name__)

# 사이클 62 — 60s TTL 캐시 상수 (사이클 56-E BUY_BLOCK_CACHE_TTL 답습)
PRICE_FILTER_CACHE_TTL: float = 60.0


class RiskManager:
    """실시간 시세를 감시하며 전략별 매매 신호에 따라 주문을 실행한다."""

    def __init__(self, registry: StrategyRegistry, order_engine: OrderEngine) -> None:
        self.registry = registry
        self.order_engine = order_engine
        # 가설 D (2026-05-12): tradable=False skip 카운터. 1분 1회 INFO 로그 + reset.
        self._tradable_skip_count: dict[str, int] = {}
        self._last_tradable_emit_ts: float = 0.0
        # 사이클 2 (2026-05-17): 시장 레짐 매수 가드 skip 카운터. 1분 1회 INFO emit.
        self._regime_block_count: dict[str, int] = {}
        self._last_regime_block_emit_ts: float = 0.0
        # 사이클 31 (R6, 2026-05-21): `risk.py:152` 사전 가드 침묵 가시화.
        # `current_price > state.total_investment` skip 분기에서 1회/(ticker, strategy)/일
        # INFO emit cap. 매 틱 폭주 차단 + scheduler `_reset_daily_state` 동행 clear.
        # 2026-05-21 09:13 VB 미매수 사고 디버깅 곤란의 근본 원인 (skip 침묵).
        # 사이클 56-D: DailyEmitCap[tuple[str, str]] 마이그레이션. tuple key 호환 보장.
        # scheduler 외부 직접 clear → reset_daily_state() 캡슐화 위임 (사이클 52 OrderEngine 패턴 답습).
        self._risk_silent_skip_logged_today: DailyEmitCap[tuple[str, str]] = DailyEmitCap[tuple[str, str]]()
        # 사이클 62 (2026-06-05) — 가격 필터 emit cap (1회/(ticker, strategy)/일)
        # HARD 차단 emit + WARN 경고 emit 각각 별도 cap (G 카테고리)
        self._price_filter_skip_logged_today: DailyEmitCap[tuple[str, str]] = DailyEmitCap[tuple[str, str]]()
        self._price_filter_warn_logged_today: DailyEmitCap[tuple[str, str]] = DailyEmitCap[tuple[str, str]]()
        # 사이클 62 — 60s TTL 캐시 (사이클 56-E BUY_BLOCK_CACHE_TTL 답습)
        self._price_filter_cache: Optional[PriceFilter] = None
        self._price_filter_cache_expires_at: float = 0.0
        # 사이클 62 — 일일 집계 카운터 (H 카테고리 — _settle() 직전 emit)
        self._price_filter_skip_count_today: int = 0
        self._price_filter_warn_count_today: int = 0
        self._price_filter_skip_reasons_today: dict[str, int] = {}

    def reset_daily_state(self) -> None:
        """사이클 56-D — 일일 RiskManager 상태 초기화 (scheduler 위임).

        사이클 31 R6 _risk_silent_skip_logged_today 일괄 clear.
        사이클 52 OrderEngine.reset_daily_state() 패턴 답습 (캡슐화).
        사이클 62 — 가격 필터 emit cap 2종 + 일일 집계 카운터 3 필드 reset 추가.
        """
        self._risk_silent_skip_logged_today.clear()
        # 사이클 62 — emit cap 2 종 reset (C-2 회귀 가드 의무)
        self._price_filter_skip_logged_today.clear()
        self._price_filter_warn_logged_today.clear()
        # 사이클 62 — 일일 집계 카운터 3 필드 reset (H 카테고리)
        self._price_filter_skip_count_today = 0
        self._price_filter_warn_count_today = 0
        self._price_filter_skip_reasons_today.clear()

    async def on_tick(
        self,
        ticker: str,
        current_price: int,
        open_price: int,
        change_rate: float,
    ) -> None:
        """실시간 체결가 수신 시 호출된다."""
        from datetime import datetime as _dt
        from src.engine.scanner import KST_TZ, ticker_last_tick, ticker_prev_close, ticker_prices

        # 1. 공용 시세 갱신 (1회)
        prev_close = ticker_prev_close.get(ticker, 0)
        prdy_ctrt = round((current_price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0
        ticker_prices[ticker] = {
            "current_price": current_price,
            "open_price": open_price,
            "change_rate": round(change_rate, 2),
            "prdy_ctrt": prdy_ctrt,
        }
        # Phase D: 마지막 tick 수신 시각 추적 (5분 주기 _report_tick_coverage 가 사용)
        # dict assign 1회 비용 — on_tick은 초당 수십~수백 호출 가능하므로 추가 연산 금지
        ticker_last_tick[ticker] = _dt.now(KST_TZ)

        # PR7(동일가 연속 틱 신호 평가 skip) 롤백 — 회귀 발견:
        # VB/LTV 시가 확정 직후 첫 on_tick에서 _prev_price=0 → check_buy_signal first-tick skip.
        # 이후 같은 가격이 반복되면 PR7 가드로 skip → _prev_price=0 유지 → 가격 변화가 와도
        # prev=0이라 돌파 가드("prev<target AND current>=target") 통과 못 해 매수 신호가
        # 끝까지 발생하지 않는 결함. 2026-05-11 운영 중 13종목 중 5종목 돌파 상태인데
        # VB 매수 신호 로그 0건 확인. 이벤트 루프 부담보다 매수 기회 누락이 큰 손실이라 즉시 롤백.

        # 2. 활성화된 전략별 순회
        for strategy in self.registry.enabled():
            state = strategy.state

            # 일일 손실 한도 초과 시 신규 매수 중단
            if strategy.is_daily_loss_exceeded() and not state.buy_disabled:
                state.buy_disabled = True
                logger.warning("일일 최대 손실 한도 도달: %s, 신규 매수 중단", strategy.strategy_id)

            # 보유 중이면 고가 갱신
            pos = state.positions.get(ticker)
            if pos:
                pos.high_since_buy = max(pos.high_since_buy, current_price)

            # 3. 청산 신호 확인 (보유 중인 경우)
            # 사이클 38 (2026-05-22) — `tradable_boards` 는 **매수 진입 전용** 정책 명문화.
            # 매도/손절/Trailing/익일청산/15:20 강제청산은 PRE/MAIN/POST 무관 항상 평가 —
            # 본 분기는 보드 가드 *없이* 진입 (line 102 `is_tradable` 검사 *전*).
            if state.has_position(ticker):
                # 사이클 19 (2026-05-20) — 매도 발사 후 체결통보 도착 전까지 check_exit_signal 호출 skip.
                # `_selling` 은 execute_sell 진입 직후 add, 체결통보 _handle_sell_fill 시 discard.
                # 매도 1회 보존 + 손절 로그 폭주 차단 (운영 결함: 042700 7초 18+ 행). 6 전략 공통.
                if ticker in self.order_engine._selling:
                    continue
                signal = strategy.check_exit_signal(ticker, current_price, open_price)
                if signal != Signal.NONE:
                    await self.order_engine.execute_sell(ticker, signal, strategy.strategy_id)
                    continue  # 청산 주문 후 매수 신호 확인 불필요

            # 4. 매수 신호 확인
            # 사이클 38 명문화 — 본 분기 *부터* `tradable_boards` 가드 적용 (매수 전용).
            # 보드 가드 — 전략의 tradable_boards에 현재 활성 보드 포함 여부 (Phase 8)
            if not session_tracker.is_tradable(strategy.strategy_id, strategy.config.params):
                # 가설 D (2026-05-12): skip 카운트 누적 + 1분 주기 [tradable_skip] emit
                self._tradable_skip_count[strategy.strategy_id] = (
                    self._tradable_skip_count.get(strategy.strategy_id, 0) + 1
                )
                self._maybe_emit_tradable_skip()
                continue

            # 사이클 2 (2026-05-17) + **사이클 8 (2026-05-18)** — 매수 가드 4 모드 분기.
            # `get_buy_block_state()` 가 DB 모드+임계 조회 후 BuyBlockState 반환:
            # - HARD blocked → 매수 skip (사이클 2 회귀)
            # - WARN blocked → 매수 허용 + WARNING 로그
            # - SOFT blocked → 매수 허용 + soft_multiplier=0.5 (OrderEngine 에서 수량 축소)
            # - OFF → 가드 자체 비활성
            # 매도/손절은 check_exit_signal 분기에서 무관 → 보유 종목 청산 정상.
            # 외부 fetch 실패 / DKSTOCK_REGIME_ENABLED=false 면 empty regime → reasons=[] (graceful).
            regime = get_current_regime()
            try:
                buy_block_state = await regime.get_buy_block_state()
            except Exception:
                logger.exception(
                    "[buy_block_state] 조회 실패 — HARD fallback (안전)"
                )
                from src.engine.market_regime import BuyBlockState
                buy_block_state = BuyBlockState(
                    mode="HARD", blocked=False, soft_multiplier=1.0, reasons=[],
                )

            soft_multiplier = 1.0
            if buy_block_state.mode == "HARD" and buy_block_state.blocked:
                # 사이클 2 회귀 — 매수 차단
                self._regime_block_count[strategy.strategy_id] = (
                    self._regime_block_count.get(strategy.strategy_id, 0) + 1
                )
                self._maybe_emit_regime_block(regime)
                continue
            if buy_block_state.mode == "WARN" and buy_block_state.reasons:
                # WARN 모드 — 매수 허용 + WARNING 로그 (감사용)
                logger.warning(
                    "[buy_block_warn] strategy=%s reasons=%s",
                    strategy.strategy_id, buy_block_state.reasons,
                )
            elif buy_block_state.mode == "SOFT" and buy_block_state.reasons:
                # SOFT 모드 — 매수 허용 + 수량 ×0.5 (OrderEngine 에 kwarg 전달)
                soft_multiplier = buy_block_state.soft_multiplier

            # 전략 간 중복 매수 방지: 보유/주문 중/당일 매도 모두 가로질러 차단
            if self.registry.is_ticker_blocked_for_buy(ticker):
                continue

            # 자금 부족 사전 가드 — calc_buy_quantity 1주 fallback 조건과 동일.
            # OrderEngine cooldown 등록(매 틱 경고 5건/일)을 줄이기 위해 신호 평가 자체 skip.
            now_ts = time.time()
            if state.is_low_funds_blocked(ticker, now_ts):
                continue
            if state.total_investment > 0 and current_price > state.total_investment:
                # 사이클 31 (R6, 2026-05-21) — 사전 가드 침묵 가시화.
                # 1회/(ticker, strategy)/일 emit cap — 매 틱 폭주 차단 + scheduler
                # `_reset_daily_state` 동행 clear. 2026-05-21 09:13 VB 미매수 사고
                # 디버깅 곤란의 근본 원인 (skip 침묵) 대응.
                emit_key = (ticker, strategy.strategy_id)
                if emit_key not in self._risk_silent_skip_logged_today:
                    self._risk_silent_skip_logged_today.add(emit_key)
                    logger.info(
                        "[risk_silent_skip] ticker=%s strategy=%s "
                        "reason=price_gt_total_investment price=%d total=%d",
                        ticker, strategy.strategy_id, current_price, state.total_investment,
                    )
                continue

            # 사이클 62 (2026-06-05) — 가격 필터 가드 (매수 진입 전용)
            # **사이클 38 명문화 보존**: check_exit_signal 분기 *후* 위치 의무.
            # 매도/손절/Trailing/익일청산/15:20 강제청산 영향 0.
            # Q2 자문: prev_close 우선 + current_price fallback + 양쪽 0 graceful 통과
            # Q4 자문: HARD(차단) / WARN(경고+허용) / OFF(비활성)
            price_filter = await self._get_price_filter_cached()
            if price_filter.is_active:
                from src.engine.scanner import ticker_prev_close as _prev_close_dict
                ref_price = _prev_close_dict.get(ticker, 0)
                if ref_price <= 0:
                    ref_price = int(current_price) if current_price and current_price > 0 else 0
                if ref_price > 0:
                    below_min = price_filter.min_price > 0 and ref_price < price_filter.min_price
                    above_max = price_filter.max_price > 0 and ref_price > price_filter.max_price
                    if below_min or above_max:
                        reason = "below_min" if below_min else "above_max"
                        if price_filter.mode == "HARD":
                            await self._emit_price_filter_skip(
                                ticker=ticker,
                                strategy_id=strategy.strategy_id,
                                reason=reason,
                                ref_price=ref_price,
                                price_filter=price_filter,
                            )
                            continue  # 매수 신호 평가 skip
                        elif price_filter.mode == "WARN":
                            await self._emit_price_filter_warn(
                                ticker=ticker,
                                strategy_id=strategy.strategy_id,
                                reason=reason,
                                ref_price=ref_price,
                                price_filter=price_filter,
                            )
                            # WARN 모드 — 매수 허용 (continue 안 함)

            # G안 (2026-05-12): donchian_swing 매수 평가는 Pull 폴링(_swing_buy_poll_loop)에서만.
            # WebSocket tick 흐름에서는 skip — 일봉 전략이라 실시간 tick 평가가 구조적 낭비.
            # 청산(ATR 트레일링/하드 -7%)은 위 check_exit_signal 분기에서 정상 동작 — 영향 없음.
            if strategy.strategy_id == "donchian_swing":
                continue
            signal = strategy.check_buy_signal(ticker, current_price, open_price)
            if signal == Signal.BUY:
                state.signal_count_today += 1
                # 사이클 8 (2026-05-18) — SOFT 모드 시 OrderEngine 이 수량 ×0.5
                await self.order_engine.execute_buy(
                    ticker, current_price, strategy,
                    soft_multiplier=soft_multiplier,
                )

    # ---------------------------------------------------------------------------
    # 사이클 62 — 가격 필터 헬퍼 메서드
    # ---------------------------------------------------------------------------

    async def _get_price_filter_cached(self) -> PriceFilter:
        """60s TTL 캐시. invalidate 토글 시 즉시 무효화 (Q5 자문).

        사이클 56-E BUY_BLOCK_CACHE_TTL 답습. `time.monotonic()` 사용 (datetime.now() 금지).
        """
        now = time.monotonic()
        if self._price_filter_cache is not None and now < self._price_filter_cache_expires_at:
            return self._price_filter_cache
        pf = await get_price_filter()
        self._price_filter_cache = pf
        self._price_filter_cache_expires_at = now + PRICE_FILTER_CACHE_TTL
        return pf

    def invalidate_price_filter_cache(self) -> None:
        """Settings PUT 직후 즉시 반영 (Q5 자문 — 5분 grace 금지)."""
        self._price_filter_cache = None
        self._price_filter_cache_expires_at = 0.0

    async def _emit_price_filter_skip(
        self,
        *,
        ticker: str,
        strategy_id: str,
        reason: str,
        ref_price: int,
        price_filter: PriceFilter,
    ) -> None:
        """HARD 모드 매수 차단 로그 emit. 1회/(ticker, strategy)/일 cap.

        사이클 31 R6 `_risk_silent_skip_logged_today` 패턴 답습.
        """
        emit_key = (ticker, strategy_id)
        if emit_key not in self._price_filter_skip_logged_today:
            self._price_filter_skip_logged_today.add(emit_key)
            logger.info(
                "[price_filter_skip] ticker=%s strategy=%s reason=%s "
                "ref_price=%d min=%d max=%d mode=%s",
                ticker, strategy_id, reason, ref_price,
                price_filter.min_price, price_filter.max_price, price_filter.mode,
            )
            try:
                from src.db.system_logs import write_log
                await write_log(
                    "INFO",
                    f"[price_filter_skip] ticker={ticker} strategy={strategy_id} "
                    f"reason={reason} ref_price={ref_price} "
                    f"min={price_filter.min_price} max={price_filter.max_price} "
                    f"mode={price_filter.mode}",
                )
            except Exception:
                logger.debug("[price_filter_skip] write_log 실패", exc_info=True)
        # 일일 집계 카운터 (H-1 — cap 밖에서 매 차단 누적)
        self._price_filter_skip_count_today += 1
        self._price_filter_skip_reasons_today[reason] = (
            self._price_filter_skip_reasons_today.get(reason, 0) + 1
        )

    async def _emit_price_filter_warn(
        self,
        *,
        ticker: str,
        strategy_id: str,
        reason: str,
        ref_price: int,
        price_filter: PriceFilter,
    ) -> None:
        """WARN 모드 경고 로그 emit. 1회/(ticker, strategy)/일 cap (skip cap 과 별도).

        G 카테고리 — 매수 허용 + 사후 가시화 (사이클 8 buy_block WARN 답습).
        """
        emit_key = (ticker, strategy_id)
        if emit_key not in self._price_filter_warn_logged_today:
            self._price_filter_warn_logged_today.add(emit_key)
            logger.warning(
                "[price_filter_warn] ticker=%s strategy=%s reason=%s "
                "ref_price=%d min=%d max=%d mode=%s",
                ticker, strategy_id, reason, ref_price,
                price_filter.min_price, price_filter.max_price, price_filter.mode,
            )
            try:
                from src.db.system_logs import write_log
                await write_log(
                    "WARNING",
                    f"[price_filter_warn] ticker={ticker} strategy={strategy_id} "
                    f"reason={reason} ref_price={ref_price} "
                    f"min={price_filter.min_price} max={price_filter.max_price} "
                    f"mode={price_filter.mode}",
                )
            except Exception:
                logger.debug("[price_filter_warn] write_log 실패", exc_info=True)
        # 일일 집계 카운터
        self._price_filter_warn_count_today += 1

    async def _emit_price_filter_daily_summary(self) -> None:
        """`_settle()` 직전 호출. 일일 집계 1행 INFO emit (Q6 자문).

        포함 필드: skip_count (HARD 차단) / warn_count (WARN 경고) / mode.
        사이클 41 funnel 진단 패턴 답습.
        """
        try:
            pf = await self._get_price_filter_cached()
            msg = (
                f"[price_filter_daily_summary] "
                f"skip_count={self._price_filter_skip_count_today} "
                f"warn_count={self._price_filter_warn_count_today} "
                f"reasons={dict(self._price_filter_skip_reasons_today)} "
                f"mode={pf.mode} min={pf.min_price} max={pf.max_price}"
            )
            logger.info(msg)
            try:
                from src.db.system_logs import write_log
                await write_log("INFO", msg)
            except Exception:
                logger.debug("[price_filter_daily_summary] write_log 실패", exc_info=True)
        except Exception:
            logger.debug("[price_filter_daily_summary] emit 실패", exc_info=True)

    def _maybe_emit_tradable_skip(self) -> None:
        """가설 D (2026-05-12) — 분당 1회 [tradable_skip] INFO 로그 + 카운터 reset.

        - 60s 미만 경과면 카운터만 누적
        - 60s 경과 시: 누적 카운트 + 활성 보드를 1행 INFO 로그로 노출 후 카운터/ts 초기화
        - active_boards 는 `session_tracker.active` 프로퍼티의 정렬된 board.value 리스트

        Codex 추가검토 2 (2026-05-12): `_last_tradable_emit_ts=0.0` 초기화로
        신규 RiskManager 의 첫 tick 에서 `now - 0.0 > 60` 즉시 emit 되던 결함 차단.
        첫 호출 시점을 기준점으로 등록만 하고 emit 보류 — 이후 60s 누적 후 첫 emit.
        """
        now_ts = time.time()
        # 첫 호출 가드 — 기준점만 등록하고 reset 없이 카운터는 누적 유지(다음 emit 으로 노출).
        if self._last_tradable_emit_ts == 0.0:
            self._last_tradable_emit_ts = now_ts
            return
        if now_ts - self._last_tradable_emit_ts < 60.0:
            return
        if not self._tradable_skip_count:
            self._last_tradable_emit_ts = now_ts
            return
        try:
            # Copilot P3 (2026-05-12): private `_active` 직접 접근 대신 `active` 프로퍼티 사용
            active = sorted(b.value for b in session_tracker.active)
        except Exception:
            active = []
        # 형식: [tradable_skip] momentum=X breakout=Y ltv=Z swing=W active_boards=[...]
        # 누적된 strategy_id 알파벳 순으로 노출 (테스트 가시성)
        parts = " ".join(
            f"{sid}={cnt}" for sid, cnt in sorted(self._tradable_skip_count.items())
        )
        logger.info("[tradable_skip] %s active_boards=%s", parts, active)
        self._tradable_skip_count.clear()
        self._last_tradable_emit_ts = now_ts

    def _maybe_emit_regime_block(self, regime) -> None:  # type: ignore[no-untyped-def]
        """사이클 2 (2026-05-17) — 분당 1회 [regime_block] INFO 로그.

        시장 레짐 매수 차단 카운트를 1분 주기로 노출. 첫 호출 시 기준점만 등록하고
        emit 보류 (tradable_skip 패턴과 동일).
        """
        now_ts = time.time()
        if self._last_regime_block_emit_ts == 0.0:
            self._last_regime_block_emit_ts = now_ts
            return
        if now_ts - self._last_regime_block_emit_ts < 60.0:
            return
        if not self._regime_block_count:
            self._last_regime_block_emit_ts = now_ts
            return
        parts = " ".join(
            f"{sid}={cnt}" for sid, cnt in sorted(self._regime_block_count.items())
        )
        try:
            reason = regime.block_reason or "unknown"
        except Exception:
            reason = "unknown"
        logger.info("[regime_block] %s reason=%s", parts, reason)
        self._regime_block_count.clear()
        self._last_regime_block_emit_ts = now_ts
