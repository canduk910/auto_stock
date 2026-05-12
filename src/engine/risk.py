"""리스크 관리 모듈.

- 실시간 시세에 따른 손절/익일청산 신호 감시
- 전략별 포지션 비중 제한
- 전략 간 중복 매수 방지
- 전략별 매매 가능 보드(KRX 메인 / NXT 프리 / NXT 애프터) 가드 — Phase 8
"""

from __future__ import annotations

import logging
import time

from src.engine.order_engine import OrderEngine
from src.engine.session import session_tracker
from src.engine.strategy_base import Signal
from src.engine.strategy_registry import StrategyRegistry

logger = logging.getLogger(__name__)


class RiskManager:
    """실시간 시세를 감시하며 전략별 매매 신호에 따라 주문을 실행한다."""

    def __init__(self, registry: StrategyRegistry, order_engine: OrderEngine) -> None:
        self.registry = registry
        self.order_engine = order_engine
        # 가설 D (2026-05-12): tradable=False skip 카운터. 1분 1회 INFO 로그 + reset.
        self._tradable_skip_count: dict[str, int] = {}
        self._last_tradable_emit_ts: float = 0.0

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
            if state.has_position(ticker):
                signal = strategy.check_exit_signal(ticker, current_price, open_price)
                if signal != Signal.NONE:
                    await self.order_engine.execute_sell(ticker, signal, strategy.strategy_id)
                    continue  # 청산 주문 후 매수 신호 확인 불필요

            # 4. 매수 신호 확인
            # 보드 가드 — 전략의 tradable_boards에 현재 활성 보드 포함 여부 (Phase 8)
            if not session_tracker.is_tradable(strategy.strategy_id, strategy.config.params):
                # 가설 D (2026-05-12): skip 카운트 누적 + 1분 주기 [tradable_skip] emit
                self._tradable_skip_count[strategy.strategy_id] = (
                    self._tradable_skip_count.get(strategy.strategy_id, 0) + 1
                )
                self._maybe_emit_tradable_skip()
                continue

            # 전략 간 중복 매수 방지: 보유/주문 중/당일 매도 모두 가로질러 차단
            if self.registry.is_ticker_blocked_for_buy(ticker):
                continue

            # 자금 부족 사전 가드 — calc_buy_quantity 1주 fallback 조건과 동일.
            # OrderEngine cooldown 등록(매 틱 경고 5건/일)을 줄이기 위해 신호 평가 자체 skip.
            now_ts = time.time()
            if state.is_low_funds_blocked(ticker, now_ts):
                continue
            if state.total_investment > 0 and current_price > state.total_investment:
                continue

            # G안 (2026-05-12): donchian_swing 매수 평가는 Pull 폴링(_swing_buy_poll_loop)에서만.
            # WebSocket tick 흐름에서는 skip — 일봉 전략이라 실시간 tick 평가가 구조적 낭비.
            # 청산(ATR 트레일링/하드 -7%)은 위 check_exit_signal 분기에서 정상 동작 — 영향 없음.
            if strategy.strategy_id == "donchian_swing":
                continue
            signal = strategy.check_buy_signal(ticker, current_price, open_price)
            if signal == Signal.BUY:
                state.signal_count_today += 1
                await self.order_engine.execute_buy(ticker, current_price, strategy)

    def _maybe_emit_tradable_skip(self) -> None:
        """가설 D (2026-05-12) — 분당 1회 [tradable_skip] INFO 로그 + 카운터 reset.

        - 60s 미만 경과면 카운터만 누적
        - 60s 경과 시: 누적 카운트 + 활성 보드를 1행 INFO 로그로 노출 후 카운터/ts 초기화
        - active_boards 는 `session_tracker._active` 의 정렬된 board.value 리스트
        """
        now_ts = time.time()
        if now_ts - self._last_tradable_emit_ts < 60.0:
            return
        if not self._tradable_skip_count:
            self._last_tradable_emit_ts = now_ts
            return
        try:
            active = sorted(b.value for b in session_tracker._active)
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
