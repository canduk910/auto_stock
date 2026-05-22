"""사이클 38 (2026-05-22) — LTV 디폴트 복원 + tradable_boards 매수 전용 정책 명문화.

배경:
- 사이클 26 (2026-05-20) 가 LTV `DEFAULT_TRADABLE_BOARDS=("main",)` 로 변경.
- 사용자 운영 의도: LTV 는 연속 상한가 종목 익일 청산 모드 + PRE/POST_NXT 야간 매수 가능.
- DB `strategy_config` 는 `["pre_nxt","main","post_nxt"]` 보존되어 운영 중이지만 코드 디폴트가 어긋남.

사용자 정책 명확화:
- `tradable_boards` 는 매수 진입 전용 설정.
- 매도/손절/Trailing/익일청산은 어떤 전략에서도 PRE/POST 무관 항상 작동.

본 사이클 (38) 변경:
- LTV `DEFAULT_TRADABLE_BOARDS = ("pre_nxt", "main", "post_nxt")` 복원
- session.py `_DEFAULT_TRADABLE_BOARDS["long_tail_volatility"]` 동기화
- 사이클 26 KRX ONLY 회귀 가드 폐기 (사용자 의도와 어긋남)
- VB 디폴트 `("main",)` 절대 보존 (사용자 정책 부합)
- 매도 분기 보드 가드 무관 회귀 가드 추가 (POST_NXT 시간대 보유 손절/Trailing 정상)

사양 (D-1 ~ D-7):
- D-1: LTV `DEFAULT_TRADABLE_BOARDS == ("pre_nxt", "main", "post_nxt")` 복원
- D-2: LTV `DEFAULT_PARAMS["tradable_boards"]` 자동 동기 (list 변환)
- D-3: session.py `_DEFAULT_TRADABLE_BOARDS["long_tail_volatility"]` 3 보드 포함
- D-4: VB 디폴트 절대 보존 — `("main",)` 단독 (사용자 정책 부합)
- D-5: LTV PRE_NXT 시간대 매수 신호 평가 허용 (is_tradable=True)
- D-6: LTV POST_NXT 시간대 매수 신호 평가 허용 (is_tradable=True)
- D-7: 매도/손절은 보드 가드 무관 — POST_NXT 시간대 보유 종목 손절/Trailing 정상 발사
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# D-1: LTV DEFAULT_TRADABLE_BOARDS 복원
# ===========================================================================
def test_ltv_default_tradable_boards_restored_to_3_boards():
    """LTV `DEFAULT_TRADABLE_BOARDS == ("pre_nxt", "main", "post_nxt")` 복원."""
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy

    boards = LongTailVolatilityStrategy.DEFAULT_TRADABLE_BOARDS
    assert "pre_nxt" in boards, (
        "사이클 38: LTV 사용자 운영 의도 — PRE_NXT 매수 가능 (야간 모드)"
    )
    assert "main" in boards
    assert "post_nxt" in boards, (
        "사이클 38: LTV 사용자 운영 의도 — POST_NXT 매수 가능 (연속 상한가 익일 청산)"
    )


# ===========================================================================
# D-2: LTV DEFAULT_PARAMS["tradable_boards"] 자동 동기
# ===========================================================================
def test_ltv_default_params_tradable_boards_matches():
    """LTV `DEFAULT_PARAMS["tradable_boards"]` 가 디폴트 튜플의 list 변환."""
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy

    expected = list(LongTailVolatilityStrategy.DEFAULT_TRADABLE_BOARDS)
    actual = LongTailVolatilityStrategy.DEFAULT_PARAMS["tradable_boards"]
    assert actual == expected, (
        f"DEFAULT_PARAMS['tradable_boards'] = {actual} 가 디폴트 {expected} 와 불일치"
    )


# ===========================================================================
# D-3: session.py _DEFAULT_TRADABLE_BOARDS 동기화
# ===========================================================================
def test_session_default_tradable_boards_for_ltv_includes_3_boards():
    """`session._DEFAULT_TRADABLE_BOARDS["long_tail_volatility"]` 3 보드 포함."""
    from src.engine.session import _DEFAULT_TRADABLE_BOARDS, MarketBoard

    ltv_boards = _DEFAULT_TRADABLE_BOARDS.get("long_tail_volatility", frozenset())
    assert MarketBoard.PRE_NXT in ltv_boards, (
        "session.py fallback LTV PRE_NXT 누락 (사이클 38 복원)"
    )
    assert MarketBoard.MAIN in ltv_boards
    assert MarketBoard.POST_NXT in ltv_boards, (
        "session.py fallback LTV POST_NXT 누락 (사이클 38 복원)"
    )


# ===========================================================================
# D-4: VB 디폴트 절대 보존 (사용자 정책 부합)
# ===========================================================================
def test_vb_default_tradable_boards_preserved_main_only():
    """VB `DEFAULT_TRADABLE_BOARDS == ("main",)` 절대 보존 (사용자 정책).

    VB 는 15:20 일괄 청산 정책이라 POST_NXT 추가 금지 (CLAUDE.md 절대 규칙).
    """
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    boards = VolatilityBreakoutStrategy.DEFAULT_TRADABLE_BOARDS
    assert boards == ("main",), (
        f"VB 디폴트 절대 보존 위반 — 실제={boards}. "
        f"15:20 일괄 청산 정책 + OVERNIGHT 결함 차단."
    )


# ===========================================================================
# D-5: LTV PRE_NXT 시간대 매수 신호 평가 허용
# ===========================================================================
def test_ltv_is_tradable_in_pre_nxt(monkeypatch):
    """LTV PRE_NXT 보드 활성 시 is_tradable=True (매수 신호 평가 허용)."""
    from src.engine.session import MarketBoard, session_tracker

    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.PRE_NXT}))
    # LTV 파라미터 없이 호출 — 디폴트 fallback 적용
    assert session_tracker.is_tradable("long_tail_volatility") is True, (
        "사이클 38: LTV PRE_NXT 시간대 매수 평가 허용 (사용자 의도 복원)"
    )


# ===========================================================================
# D-6: LTV POST_NXT 시간대 매수 신호 평가 허용
# ===========================================================================
def test_ltv_is_tradable_in_post_nxt(monkeypatch):
    """LTV POST_NXT 보드 활성 시 is_tradable=True (사이클 38 복원)."""
    from src.engine.session import MarketBoard, session_tracker

    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.POST_NXT}))
    assert session_tracker.is_tradable("long_tail_volatility") is True, (
        "사이클 38: LTV POST_NXT 시간대 매수 평가 허용 (사용자 의도 복원)"
    )


# ===========================================================================
# D-7: 매도/손절은 보드 가드 무관 — POST_NXT 시간대 보유 손절 정상
# ===========================================================================
@pytest.mark.asyncio
async def test_exit_signal_evaluated_regardless_of_tradable_boards(monkeypatch):
    """매도/손절은 `tradable_boards` 무관 — risk.on_tick 의 `check_exit_signal` 분기는
    보유 종목 진입 즉시 평가 (보드 가드 *없이*).

    POST_NXT 시간대에 VB 디폴트는 `("main",)` 라 매수 평가는 차단되지만,
    보유 종목 손절/Trailing 은 정상 발사되어야 함.
    """
    from src.engine.risk import RiskManager

    # VB 보유 종목 시나리오 — POST_NXT 시간대
    held_ticker = "005930"

    # 보유 + 손절 신호 발사하는 전략 더블
    state = MagicMock()
    state.positions = {held_ticker: MagicMock(buy_price=100000, high_since_buy=100000)}
    state.has_position = MagicMock(return_value=True)
    state.is_buy_blocked = MagicMock(return_value=False)
    state.is_low_funds_blocked = MagicMock(return_value=False)
    state.buy_disabled = False
    state.total_investment = 10_000_000
    state.signal_count_today = 0
    state.buy_signals = set()
    state.pending_buys = set()
    state.sold_today = set()

    # 손절 신호 발사
    from src.engine.strategy_base import Signal
    strategy = MagicMock()
    strategy.strategy_id = "volatility_breakout"
    strategy.state = state
    strategy.is_daily_loss_exceeded = MagicMock(return_value=False)
    strategy.check_exit_signal = MagicMock(return_value=Signal.STOP_LOSS)
    strategy.check_buy_signal = MagicMock(return_value=Signal.NONE)

    registry = MagicMock()
    registry.enabled = MagicMock(return_value=[strategy])
    registry.is_ticker_blocked_for_buy = MagicMock(return_value=False)

    from unittest.mock import AsyncMock
    order_engine = MagicMock()
    order_engine._selling = set()
    order_engine.execute_buy = AsyncMock()
    order_engine.execute_sell = AsyncMock()

    rm = RiskManager(registry, order_engine)

    # 가드 우회 + scanner mock
    from src.engine import scanner as scanner_mod
    from src.engine.session import MarketBoard, session_tracker
    monkeypatch.setattr(scanner_mod, "ticker_prev_close", {}, raising=False)
    monkeypatch.setattr(scanner_mod, "ticker_prices", {}, raising=False)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {}, raising=False)

    # POST_NXT 시간대 — VB tradable_boards=("main",) 에는 없음
    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.POST_NXT}))

    # market_regime 가드 우회
    from src.engine import market_regime as mr_mod
    fake_regime = MagicMock()
    fake_state = MagicMock()
    fake_state.mode = "OFF"
    fake_state.blocked = False
    fake_state.reasons = []
    fake_state.soft_multiplier = 1.0
    fake_regime.get_buy_block_state = AsyncMock(return_value=fake_state)
    monkeypatch.setattr(mr_mod, "get_current_regime", lambda: fake_regime)

    # tick 발사 — 손절 가격 (-10%)
    await rm.on_tick(held_ticker, current_price=90000, open_price=100000, change_rate=-10.0)

    # check_exit_signal 호출됨 (보드 가드 무관)
    strategy.check_exit_signal.assert_called(), (
        "매도/손절은 tradable_boards 무관 — POST_NXT 시간대에도 정상 평가"
    )
    # execute_sell 호출됨 (손절 신호 발사)
    order_engine.execute_sell.assert_awaited(), (
        "STOP_LOSS 신호 → execute_sell 호출. tradable_boards 가드 적용되면 안 됨."
    )
    # check_buy_signal 은 호출 안 됨 (VB tradable_boards=('main',) 에 POST_NXT 없음 → 보드 가드 skip)
    strategy.check_buy_signal.assert_not_called(), (
        "VB POST_NXT 시간대 매수 평가 차단 (tradable_boards 가드 정상 동작)"
    )
