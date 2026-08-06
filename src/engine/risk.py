"""리스크 관리 모듈.

- 실시간 시세에 따른 손절/익일청산 신호 감시
- 전략별 포지션 비중 제한
- 전략 간 중복 매수 방지
- 전략별 매매 가능 보드(KRX 메인 / NXT 프리 / NXT 애프터) 가드 — Phase 8
- **사이클 2 (2026-05-17)**: 시장 레짐 매수 가드 (defensive/VIX>25/F&G 극단 시 매수 차단).
  매도/손절 분기는 무관 — 보유 종목 청산 정상.
- **사이클 62 → 사이클 64 (2026-06-06)**: 가격 필터 risk.on_tick 영역 전면 이전.
  scanner.subscribe_filtered_stocks 진입 직전 단일 hook (Q4 옵션 A) 으로 재배치.
  risk.py 내 가격 필터 코드 완전 제거 (G-1 AST 가드 영속).
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from src.engine.daily_emit_cap import DailyEmitCap
from src.engine.order_engine import OrderEngine
from src.engine.session import session_tracker
from src.engine.strategy_base import Signal
from src.engine.strategy_registry import StrategyRegistry

logger = logging.getLogger(__name__)

# NXT 프리장(08:00~09:00) 청산 **평가** 화이트리스트 (2026-08-06 사용자 결정).
#
# 여기 없는 전략은 프리장 단독 구간 동안 청산 평가(고점 갱신 포함) 자체를 보류한다.
# 근거 = 프리장의 얇은 호가는 전일 상한가 종목의 시초가가 하한가 부근에 형성되는 등
# 왜곡이 잦아(사용자 실측), 왜곡 틱으로 허깨비 손절이 발화하거나 트레일링 고점이
# 오염된다. 30일 APBK0918 매도 거부 전수(momentum 익일매도 2 + donchian 손절 3 +
# LTV 1)에서 KIS 거부가 **우연히** 이 보류를 수행해 전부 09:00 KRX 체결로 밀렸는데,
# 이 게이트가 그 우연을 정식 경로로 만든다.
#
# **평가 보류이지 주문 보류가 아니다** — 주문만 보류하면 프리장 허깨비 틱이 발화시킨
# 신호가 09:00 실제 매도로 전환된다(KRX 시가가 정상이어도 팔림). 평가를 보류하면
# 09:00 부터 정상 시세로 재평가되어 진짜 이탈만 매도된다.
#
# LTV 는 프리장 매매가 설계 의도(상한가 익일 청산 + 프리장 매수, 사이클 38)라 예외.
# ⚠️ `tradable_boards` 로 게이팅 금지 — 그 설정은 매수 전용(사이클 38 명문화)이고,
#    매수 목적의 보드 변경이 청산 규약까지 조용히 바꾸는 커플링을 차단한다(AST 가드).
_PRE_MARKET_EXIT_EVAL_STRATEGIES = frozenset({"long_tail_volatility"})


class RiskManager:
    """실시간 시세를 감시하며 전략별 매매 신호에 따라 주문을 실행한다."""

    def __init__(self, registry: StrategyRegistry, order_engine: OrderEngine) -> None:
        self.registry = registry
        self.order_engine = order_engine
        # 가설 D (2026-05-12): tradable=False skip 카운터. 1분 1회 INFO 로그 + reset.
        self._tradable_skip_count: dict[str, int] = {}
        self._last_tradable_emit_ts: float = 0.0
        # 사이클 31 (R6, 2026-05-21): `risk.py:152` 사전 가드 침묵 가시화.
        # `current_price > state.total_investment` skip 분기에서 1회/(ticker, strategy)/일
        # INFO emit cap. 매 틱 폭주 차단 + scheduler `_reset_daily_state` 동행 clear.
        # 2026-05-21 09:13 VB 미매수 사고 디버깅 곤란의 근본 원인 (skip 침묵).
        # 사이클 56-D: DailyEmitCap[tuple[str, str]] 마이그레이션. tuple key 호환 보장.
        # scheduler 외부 직접 clear → reset_daily_state() 캡슐화 위임 (사이클 52 OrderEngine 패턴 답습).
        self._risk_silent_skip_logged_today: DailyEmitCap[tuple[str, str]] = DailyEmitCap[tuple[str, str]]()
        # 사이클 62 → 사이클 64 (2026-06-06): 가격 필터 필드 전면 제거 (scanner 이전)
        # 프리장 청산 보류 관찰 로그 1회/전략/일 cap (2026-08-06)
        self._pre_market_defer_logged: set[str] = set()

    def _defers_pre_market_exit(self, strategy_id: str) -> bool:
        """NXT 프리장 단독 구간이면 청산 평가를 보류할지 판정.

        판정 소스는 `session_tracker.active`(스케줄러 이벤트 구동) — wall-clock 이
        아니므로 단위 테스트 기본 상태(빈 frozenset)에서 결정적으로 꺼진다.
        조건은 매수측 PR-F 와 동일한 membership(`PRE_NXT ∈ active AND MAIN ∉ active`).
        판정 불가 시 **fail-open**(평가 유지) — 손절 정지가 더 위험하다.
        """
        if strategy_id in _PRE_MARKET_EXIT_EVAL_STRATEGIES:
            return False
        try:
            from src.engine.session import MarketBoard
            active = session_tracker.active
            return (
                MarketBoard.PRE_NXT in active
                and MarketBoard.MAIN not in active
            )
        except Exception:
            return False

    def _maybe_emit_pre_market_defer(self, strategy_id: str) -> None:
        """보류 발생 1회/전략/일 관찰 로그 — 매 틱 폭주 금지."""
        if strategy_id in self._pre_market_defer_logged:
            return
        self._pre_market_defer_logged.add(strategy_id)
        logger.info(
            "[pre_market_exit_deferred] strategy=%s — NXT 프리장 청산 평가 보류, "
            "09:00 KRX 시세로 재개", strategy_id,
        )

    def reset_daily_state(self) -> None:
        """사이클 56-D — 일일 RiskManager 상태 초기화 (scheduler 위임).

        사이클 31 R6 _risk_silent_skip_logged_today 일괄 clear.
        사이클 52 OrderEngine.reset_daily_state() 패턴 답습 (캡슐화).
        사이클 64 — 가격 필터 필드 scanner 이전으로 본 영역에서 제거.
        """
        self._risk_silent_skip_logged_today.clear()
        self._pre_market_defer_logged.clear()

    async def on_tick(
        self,
        ticker: str,
        current_price: int,
        open_price: int,
        change_rate: float,
    ) -> None:
        """실시간 체결가 수신 시 호출된다.

        가드 평가 순서 (사이클 165 명문화 — 변경 0):
          L0. 매도/손절/Trailing/익일청산: 보드 가드 *전* 평가 (사이클 38 명문화 영속).
              `check_exit_signal` 분기는 PRE/MAIN/POST 무관 항상 작동 — `tradable_boards`
              는 매수 진입 전용.
          L1. 보드 가드 (사이클 38): `session_tracker.is_tradable(strategy_id, params)`.
              매수 신호 평가 진입 전 차단.
          L2. (사이클 I 제거) 시장 레짐 매수 가드 폐지 — 레짐은 매수를 차단/축소하지
              않는다 (관찰 전용 전환). 레짐 대응은 cash_usage_ratio 로만.
          L3. 중복 가드: `registry.is_ticker_blocked_for_buy()`.
              보유 OR 주문중 OR 당일매도 통합 차단.
          L4. 자금 사전 가드: `state.is_low_funds_blocked(ticker)` 또는
              `current_price > state.total_investment` skip (사이클 31 R6 가시화).

        매도/손절/Trailing/익일청산은 L1·L3·L4 *전* 평가 → tradable_boards 무관 항상 작동.
        """
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

            # NXT 프리장 청산 평가 보류 게이트 (2026-08-06 사용자 결정) —
            # 프리장 왜곡 틱의 허깨비 손절·트레일링 고점 오염 차단. LTV 만 예외
            # (`_PRE_MARKET_EXIT_EVAL_STRATEGIES`). 09:00 MAIN 진입 시 자동 재개.
            pos = state.positions.get(ticker)
            defer_exit = pos is not None and self._defers_pre_market_exit(
                strategy.strategy_id
            )
            if defer_exit:
                self._maybe_emit_pre_market_defer(strategy.strategy_id)

            # 보유 중이면 고가 갱신 (프리장 보류 중엔 왜곡 고가 앵커 오염 금지)
            if pos and not defer_exit:
                pos.high_since_buy = max(pos.high_since_buy, current_price)

            # 3. 청산 신호 확인 (보유 중인 경우)
            # 사이클 38 (2026-05-22) — `tradable_boards` 는 **매수 진입 전용** 정책 명문화.
            # 매도/손절/Trailing/익일청산/15:20 강제청산은 PRE/MAIN/POST 무관 항상 평가 —
            # 본 분기는 보드 가드 *없이* 진입 (line 102 `is_tradable` 검사 *전*).
            # 유일한 예외 = 위 프리장 평가 보류 게이트(명시 화이트리스트, 보드 설정 무관).
            if state.has_position(ticker) and not defer_exit:
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

            # 사이클 I (2026-08-03) — 레짐 매수 게이트 제거 (관찰 전용 전환).
            # 마켓레짐은 더 이상 매수를 차단/축소하지 않는다. 레짐 대응은
            # cash_usage_ratio(운영자 수동 / auto_regime_adjust)로만 수행.
            # 손절/매도/익일청산은 위 check_exit_signal 분기(레짐 게이트보다 앞)에서 정상.

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

            # 사이클 64 (2026-06-06) — 가격 필터 분기 scanner 이전 (G-1 AST 가드 영속).
            # 본 위치(on_tick)에 가격 필터 코드 없음 — scanner.subscribe_filtered_stocks 에서만 적용.

            # G안 (2026-05-12): donchian_swing 매수 평가는 Pull 폴링(_swing_buy_poll_loop)에서만.
            # WebSocket tick 흐름에서는 skip — 일봉 전략이라 실시간 tick 평가가 구조적 낭비.
            # 청산(ATR 트레일링/하드 -7%)은 위 check_exit_signal 분기에서 정상 동작 — 영향 없음.
            if strategy.strategy_id == "donchian_swing":
                continue
            signal = strategy.check_buy_signal(ticker, current_price, open_price)
            if signal == Signal.BUY:
                state.signal_count_today += 1
                await self.order_engine.execute_buy(
                    ticker, current_price, strategy,
                )

    # ---------------------------------------------------------------------------
    # 사이클 64 (2026-06-06) — 가격 필터 헬퍼 메서드 전면 제거 (scanner 이전)
    # G-1 AST 가드: risk.py 에 price_filter 관련 문자열 0건 의무
    # (scanner.py::_apply_price_filter 가 단일 책임 — Q4 옵션 A)
    # ---------------------------------------------------------------------------

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

