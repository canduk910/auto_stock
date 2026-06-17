"""사이클 158 Q1 — momentum 익일 청산 로그 폭주 DailyEmitCap 시정 회귀 가드.

운영 사례 (2026-06-17 08:14:06 ~ 08:14:31 KST):
- 씨에스윈드(112610) 익일 즉시 청산 logger.info ~26회/30초 발화
- 근본 원인: check_exit_signal 익일 청산 분기에 DailyEmitCap 없음
- 시정: 모듈 전역 _next_day_clear_logged_today: DailyEmitCap[str] 도입
- 사이클 31 R6 / 57 V-1 패턴 답습 (DailyEmitCap + reset_daily 동행)

회귀 가드 7 케이스:
- G-158-Q1-1: 모듈 전역 _next_day_clear_logged_today 정의
- G-158-Q1-2: 익일 청산 분기 진입 시 should_emit 검사
- G-158-Q1-3: 동일 ticker 동일 일자 logger.info 1회 cap
- G-158-Q1-4: 다른 ticker 격리 검증
- G-158-Q1-5: reset 동행 (모듈 reset 헬퍼 / _reset_daily_state 위임)
- G-158-Q1-6: Signal.NEXT_DAY_CLEAR 반환 영속 (cap 영역 = logger 한정)
- G-158-Q1-7: 트레일링 분기 변경 0
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

_KST = timezone(timedelta(hours=9))

import pytest

from src.engine import strategies as _strategies_pkg  # noqa: F401  (패키지 import 보장)
from src.engine.daily_emit_cap import DailyEmitCap
from src.engine.strategies import momentum as momentum_mod
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig


def _make_strategy() -> MomentumStrategy:
    config = StrategyConfig(strategy_id="momentum", name="모멘텀", params={}, enabled=True, weight=1.0)
    s = MomentumStrategy(config)
    s.state.total_investment = 10_000_000
    return s


def _seed_next_day_position(s: MomentumStrategy, ticker: str, buy_price: int) -> None:
    yesterday = datetime.now(_KST).date() - timedelta(days=1)
    s.state.positions[ticker] = Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=10,
        order_no="ORD-X",
        strategy_id="momentum",
        buy_date=yesterday,
    )


# ──────────────────────────────────────────────────────────────────────
# G-158-Q1-1 — 모듈 전역 _next_day_clear_logged_today 정의
# ──────────────────────────────────────────────────────────────────────


def test_G_158_Q1_1_module_emit_cap_defined() -> None:
    """모듈 전역 _next_day_clear_logged_today 정의 + DailyEmitCap[str] 타입."""
    assert hasattr(momentum_mod, "_next_day_clear_logged_today")
    cap = momentum_mod._next_day_clear_logged_today
    assert isinstance(cap, DailyEmitCap)


# ──────────────────────────────────────────────────────────────────────
# G-158-Q1-2/3 — 동일 ticker 동일 일자 logger.info 1회 cap
# ──────────────────────────────────────────────────────────────────────


def test_G_158_Q1_3_same_ticker_log_capped_to_once(caplog) -> None:
    """동일 ticker 10 tick → logger.info "익일 즉시 청산" 1회만 발화."""
    momentum_mod._next_day_clear_logged_today.reset_daily()
    s = _make_strategy()
    ticker = "112610"
    _seed_next_day_position(s, ticker, buy_price=56_800)

    with caplog.at_level("INFO", logger="src.engine.strategies.momentum"), \
         patch("src.engine.scanner.t", return_value=ticker):
        for _ in range(10):
            sig = s.check_exit_signal(ticker, current_price=61_000, open_price=61_400)
            assert sig == Signal.NEXT_DAY_CLEAR

    next_day_logs = [r for r in caplog.records if "익일 즉시 청산" in r.getMessage()]
    assert len(next_day_logs) == 1, f"기대 1회, 실제 {len(next_day_logs)}회 (운영 사례 26회 폭주 영역)"


# ──────────────────────────────────────────────────────────────────────
# G-158-Q1-4 — 다른 ticker 는 cap 격리
# ──────────────────────────────────────────────────────────────────────


def test_G_158_Q1_4_different_tickers_independent(caplog) -> None:
    """ticker A 발화 후 ticker B 첫 진입 시 cap 영향 없음."""
    momentum_mod._next_day_clear_logged_today.reset_daily()
    s = _make_strategy()
    _seed_next_day_position(s, "112610", buy_price=56_800)
    _seed_next_day_position(s, "005930", buy_price=70_000)

    with caplog.at_level("INFO", logger="src.engine.strategies.momentum"), \
         patch("src.engine.scanner.t", side_effect=lambda x: x):
        # ticker A 3회 → 1 log
        for _ in range(3):
            s.check_exit_signal("112610", current_price=61_000, open_price=61_400)
        # ticker B 첫 진입 → 1 log
        s.check_exit_signal("005930", current_price=72_000, open_price=72_500)

    next_day_logs = [r for r in caplog.records if "익일 즉시 청산" in r.getMessage()]
    assert len(next_day_logs) == 2, "2 ticker 격리 발화 기대"


# ──────────────────────────────────────────────────────────────────────
# G-158-Q1-5 — reset 동행 (모듈 reset 헬퍼)
# ──────────────────────────────────────────────────────────────────────


def test_G_158_Q1_5_reset_daily_clears_cap(caplog) -> None:
    """reset_next_day_clear_logged_today() (또는 cap.reset_daily()) 호출 후 재발화."""
    momentum_mod._next_day_clear_logged_today.reset_daily()
    s = _make_strategy()
    _seed_next_day_position(s, "112610", buy_price=56_800)

    with caplog.at_level("INFO", logger="src.engine.strategies.momentum"), \
         patch("src.engine.scanner.t", return_value="112610"):
        s.check_exit_signal("112610", current_price=61_000, open_price=61_400)
        # 일일 reset 시뮬레이션
        momentum_mod._next_day_clear_logged_today.reset_daily()
        s.check_exit_signal("112610", current_price=61_000, open_price=61_400)

    next_day_logs = [r for r in caplog.records if "익일 즉시 청산" in r.getMessage()]
    assert len(next_day_logs) == 2, "reset 후 재발화 의무"


# ──────────────────────────────────────────────────────────────────────
# G-158-Q1-6 — Signal.NEXT_DAY_CLEAR 반환 영속 (cap = logger 영역만)
# ──────────────────────────────────────────────────────────────────────


def test_G_158_Q1_6_signal_returned_even_when_cap_blocks_log() -> None:
    """cap 로 logger 차단되어도 Signal.NEXT_DAY_CLEAR 반환 영속.

    사이클 32 R4 보유 절대 보호 + execute_sell 발사 trigger 영속.
    """
    momentum_mod._next_day_clear_logged_today.reset_daily()
    s = _make_strategy()
    _seed_next_day_position(s, "112610", buy_price=56_800)

    with patch("src.engine.scanner.t", return_value="112610"):
        sig1 = s.check_exit_signal("112610", current_price=61_000, open_price=61_400)
        sig2 = s.check_exit_signal("112610", current_price=61_000, open_price=61_400)

    assert sig1 == Signal.NEXT_DAY_CLEAR
    assert sig2 == Signal.NEXT_DAY_CLEAR, "2번째 tick도 매도 시도 trigger 의무"


# ──────────────────────────────────────────────────────────────────────
# G-158-Q1-7 — 트레일링 분기 변경 0
# ──────────────────────────────────────────────────────────────────────


def test_G_158_Q1_7_trailing_branch_not_affected(caplog) -> None:
    """갭률 ≥ 10% 트레일링 분기는 익일 청산 cap 영향 외 (변경 0)."""
    momentum_mod._next_day_clear_logged_today.reset_daily()
    s = _make_strategy()
    ticker = "112610"
    _seed_next_day_position(s, ticker, buy_price=56_800)

    # 갭률 +11% = 트레일링 모드 진입
    open_price = int(56_800 * 1.11)
    s.state.positions[ticker].high_since_buy = open_price

    with caplog.at_level("INFO", logger="src.engine.strategies.momentum"), \
         patch("src.engine.scanner.t", return_value=ticker):
        # 첫 tick 트레일링 모드 진입만, 즉시 청산 발화 없음
        sig = s.check_exit_signal(ticker, current_price=open_price, open_price=open_price)
        # 트레일링 분기에서 NONE 반환 가능 (drop_rate=0 → 임계 미충족)
        assert sig in (Signal.NONE, Signal.TRAILING_STOP)

    # "익일 즉시 청산" 로그 0건 = 트레일링 분기 진입 → 익일 청산 분기 미진입
    next_day_logs = [r for r in caplog.records if "익일 즉시 청산" in r.getMessage()]
    assert len(next_day_logs) == 0
