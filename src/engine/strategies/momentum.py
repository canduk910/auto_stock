"""상한가 모멘텀 전략.

- 매수: 전일종가 대비 +29% 돌파 순간 (29% 미만 → 이상 돌파 시)
- 상한가(+30%) 종목 제외
- 손절: 매수 체결가 대비 -7.5%
- 익일 청산: 시가 갭 +10% → 트레일링 스탑 -2% / 그 외 즉시 매도
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from src.engine.daily_emit_cap import DailyEmitCap
from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# cycle229 (P1-5, 2026-08-28) — 매수 컷오프 15:20 KST. **모듈 상수 = DB override 불가.**
# 15:20~15:30 장후 동시호가의 확정 종가 틱이 만드는 +29% 는 "돌파 순간"이 아니라
# **상한가 잠금 실패 마감** 표본이다(momentum 이 +30% 상한가를 제외하므로 이 틱이
# 잡는 것은 하루 종일 두드렸으나 못 잠근 종목 = 원 가설의 정확한 반대). VB 와 값
# 동일하나 상수는 전략별 소유(파일 간 결합 회피). PARAM_RANGES/DEFAULT_PARAMS 미편입.
# 자문 = cycle229_vb_1530_single_price.md Q2.
BUY_CUTOFF_KST = time(15, 20)


# 사이클 158 Q1 (2026-06-17) — momentum 익일 청산 logger 폭주 차단.
# 운영 사례 = 씨에스윈드(112610) 익일 즉시 청산 logger.info 26회/30초 폭주.
# 근본 원인 = check_exit_signal 익일 청산 분기 매 tick 발화.
# 사이클 19 _selling 가드는 KIS 호출 차단만 (신호 평가 미차단).
# 사이클 31 R6 / 57 V-1 DailyEmitCap 패턴 답습 — ticker 단위 1회/일 cap.
# 시정 영역 = logger 한정 (Signal.NEXT_DAY_CLEAR 반환 영속 = 사이클 32 R4 보유 절대 보호).
_next_day_clear_logged_today: DailyEmitCap[str] = DailyEmitCap[str]()


def reset_next_day_clear_logged_today() -> None:
    """사이클 158 Q1 — 일일 reset 헬퍼 (사이클 31 R6 답습).

    `_reset_daily_state()` 또는 매수 진입 전 시점 호출 영역.
    """
    _next_day_clear_logged_today.reset_daily()


class MomentumStrategy(StrategyBase):
    """상한가 모멘텀 전략 (기존 전략)."""

    # 매매 가능 보드 (Phase 8) — momentum은 KRX 동시호가/메인만. 상한가 +29% 신호는 KRX 기준
    DEFAULT_TRADABLE_BOARDS = ("krx_open", "main")

    DEFAULT_PARAMS = {
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        # 거래소 라우팅 — 익일 청산이 08:00 NXT 프리 시점에 실행되므로 SOR/NXT 권장(실전).
        # 모의(vts)는 KRX만 허용 — UI가 환경별로 SOR/NXT 선택지 차단.
        "exchange": "KRX",
        "buy_threshold": 29.0,
        "stop_loss_rate": -7.5,
        "gap_up_threshold": 10.0,
        "trailing_stop_rate": -2.0,
        "position_ratio": 0.25,
        "max_positions": 4,
        "daily_loss_limit": -5.0,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        self._prev_prdy_rate: dict[str, float] = {}
        self._next_day_clear_pending = False  # 익일 청산 대기 중 플래그 (시가 안정화 대기)
        # cycle229 (P1-5) — `[momentum_buy_cutoff]` 1회/일 관측 cap (날짜 키 자기 리셋)
        self._buy_cutoff_logged_day: date | None = None

    def _reset_daily_state(self) -> None:
        """사이클 185 — cross-day 전일등락율 캐시 초기화. 익일 첫 tick 거짓돌파 차단."""
        self._prev_prdy_rate.clear()

    async def prepare(self) -> None:
        """준비 작업 없음 — 실시간 본질 영역 영구 영속.

        momentum 전략 = 전일종가 +29% 돌파 순간 실시간 감지 영역 영구 영속.
        prepare() 영역 = empty stub 영속 (실시간 본질 영역 = 사전 준비 불필요 영속).

        사이클 132 (2026-06-15) Q2=C 영구 영속 명시:
        - funnel 미적재 영구 영속 (사이클 39+41 자동 hook 대상 = BFB/VCP/donchian 한정 영속).
        - momentum 영역 = funnel snapshot 영역 외 영속 (실시간 본질 영역 영구 영속).
        - UI 가시화 영역 = "이 전략은 실시간 돌파 기반 — funnel 적재 미적용" 안내 동행 영속.

        사이클 21 (2026-05-20) momentum scan_filter_stats 영역 영속 = scanner 전역 dict
        7 키 (universe_candidates / rate_pass / mcap_pass / trade_amount_pass / limit_up_excluded
        / final_prepared / last_run_at) 활용 (`get_scan_stats` 사본 반환 영속).
        """
        pass

    def get_scan_stats(self) -> dict:
        """사이클 21 — 모멘텀 단계별 스캔 통계.

        momentum 은 prepare 없이 09:30 실시간 `scanner.scan_stocks()` 기반.
        `scanner.scan_filter_stats` 모듈 전역 dict 의 사본을 반환 → ScanMonitor 깔때기.
        """
        from src.engine import scanner
        return dict(scanner.scan_filter_stats)

    def check_buy_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """전일종가 대비 29% 돌파 순간 매수."""
        from src.engine.scanner import t, ticker_names, ticker_prev_close

        # cycle229 (P1-5) — 15:20 매수 컷 (VB 동형, 최상단·상태 갱신 이전·KST 명시).
        _now_kst = datetime.now(KST)
        if _now_kst.time() >= BUY_CUTOFF_KST:
            if self._buy_cutoff_logged_day != _now_kst.date():
                self._buy_cutoff_logged_day = _now_kst.date()
                logger.info(
                    "[momentum_buy_cutoff] 15:20 이후 매수 신호 차단 — ticker=%s "
                    "(확정 종가 틱의 +29%%는 상한가 잠금 실패 마감 표본)",
                    ticker,
                )
            return Signal.NONE

        if self.state.buy_disabled:
            return Signal.NONE
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker) or self.state.is_sold_today(ticker):
            return Signal.NONE
        if self.is_max_positions():
            return Signal.NONE
        if self.is_daily_loss_exceeded():
            return Signal.NONE

        prev_close = ticker_prev_close.get(ticker, 0)
        if prev_close <= 0:
            return Signal.NONE

        change_rate = (current_price - prev_close) / prev_close * 100

        # 상한가(+30%) 종목 제외
        if change_rate >= 30.0:
            return Signal.NONE

        # 첫 tick은 기록만 (이미 상승한 종목 즉시 매수 방지)
        if ticker not in self._prev_prdy_rate:
            self._prev_prdy_rate[ticker] = change_rate
            return Signal.NONE

        prev_rate = self._prev_prdy_rate[ticker]
        self._prev_prdy_rate[ticker] = change_rate

        threshold = self.config.params["buy_threshold"]
        if prev_rate < threshold and change_rate >= threshold:
            logger.info(
                "매수 신호: %s 전일종가(%d) 대비 %.1f%% (현재가: %d, 직전: %.1f%%)",
                t(ticker), prev_close, change_rate, current_price, prev_rate,
            )
            self.state.buy_signals.append({
                "ticker": ticker,
                "name": ticker_names.get(ticker, ""),
                "price": current_price,
                "prev_close": prev_close,
                "change_rate": round(change_rate, 1),
                "time": datetime.now().strftime("%H:%M:%S"),
            })
            if len(self.state.buy_signals) > 20:
                self.state.buy_signals.pop(0)
            return Signal.BUY

        return Signal.NONE

    def check_exit_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """손절 + 익일 청산 통합 판단."""
        from src.engine.scanner import t

        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        # 1. 당일 손절: 매수가 대비 -7.5%
        loss_rate = (current_price - pos.buy_price) / pos.buy_price * 100
        stop_loss = self.config.params["stop_loss_rate"]
        if loss_rate <= stop_loss:
            logger.info(
                "손절 신호: %s 매수가(%d) 대비 %.1f%% (임계: %.1f%%, 현재가: %d)",
                t(ticker), pos.buy_price, loss_rate, stop_loss, current_price,
            )
            return Signal.STOP_LOSS

        # 2. 익일 청산
        if not pos.is_next_day:
            return Signal.NONE

        # 시가 안정화 대기 중에는 on_tick에서 청산 판단하지 않음
        # (scheduler._execute_next_day_clear가 60초 대기 후 직접 처리)
        if self._next_day_clear_pending:
            return Signal.NONE

        gap_threshold = self.config.params["gap_up_threshold"]
        trailing_rate = self.config.params["trailing_stop_rate"]

        gap_rate = (open_price - pos.buy_price) / pos.buy_price * 100 if pos.buy_price > 0 else 0

        if gap_rate < gap_threshold:
            # 사이클 158 Q1 — DailyEmitCap 1회/ticker/일 cap (logger 영역만).
            # Signal.NEXT_DAY_CLEAR 반환 영속 (KIS 호출 trigger 보존, 사이클 32 R4 보유 절대 보호).
            if _next_day_clear_logged_today.should_emit(ticker):
                logger.info(
                    "익일 즉시 청산: %s 갭률 %.1f%% (시가: %d, 매수가: %d)",
                    t(ticker), gap_rate, open_price, pos.buy_price,
                )
                _next_day_clear_logged_today.mark_emitted(ticker)
            return Signal.NEXT_DAY_CLEAR

        # 갭상승 +10% → 트레일링 스탑
        pos.high_since_buy = max(pos.high_since_buy, current_price)
        drop_rate = (current_price - pos.high_since_buy) / pos.high_since_buy * 100

        if drop_rate <= trailing_rate:
            logger.info(
                "트레일링 스탑: %s 고점(%d) 대비 %.1f%% (현재가: %d)",
                t(ticker), pos.high_since_buy, drop_rate, current_price,
            )
            return Signal.TRAILING_STOP

        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        """할당 자금의 position_ratio 비중. 예산 잔여로 클램프(`_apply_budget_limit`).

        비중 기준 0주면 관문이 `_fallback_one_share` 로 위임 — 잔여가 1주를 감당하면 1주.
        """
        if current_price <= 0:
            return 0
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        return self._apply_budget_limit(amount // current_price, current_price, ticker)
