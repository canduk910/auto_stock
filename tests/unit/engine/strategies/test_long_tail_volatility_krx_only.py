"""사이클 26 — LTV DEFAULT_TRADABLE_BOARDS = ("main",) 단독 검증.

계획서 H 영역: 3 케이스
- DEFAULT_TRADABLE_BOARDS == ("main",) 단독
- PRE_NXT 보드에서 매수 신호 0
- POST_NXT 보드에서 매수 신호 0
"""

from __future__ import annotations

import pytest

from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def ltv():
    return LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="롱테일 변동성", weight=0.3)
    )


# ---------------------------------------------------------------------------
# 1. DEFAULT_TRADABLE_BOARDS = ("main",) 단독 확인
# ---------------------------------------------------------------------------
def test_ltv_default_tradable_boards_krx_only(ltv):
    """LTV DEFAULT_TRADABLE_BOARDS 는 ("main",) 만 포함해야 한다 (사이클 26)."""
    boards = ltv.DEFAULT_TRADABLE_BOARDS
    assert "main" in boards
    assert "pre_nxt" not in boards, "PRE_NXT 가 제거되어야 한다 (사이클 26)"
    assert "post_nxt" not in boards, "POST_NXT 포함 금지 (OVERNIGHT 결함)"


# ---------------------------------------------------------------------------
# 2. PRE_NXT 보드 단독 활성 시 매수 신호 0
# ---------------------------------------------------------------------------
def test_ltv_buy_signal_zero_in_pre_nxt(ltv, monkeypatch):
    """session_tracker 가 PRE_NXT 만 활성일 때 LTV 매수 신호는 NONE 이어야 한다."""
    from src.engine.session import MarketBoard, session_tracker

    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.PRE_NXT}))
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", {
        "005930": {"current_price": 99000, "open_price": 90000, "change_rate": 10.0, "prev_close": 88000},
    })

    # _targets 에 PRE_NXT 타겟 등록
    ltv._targets["005930"] = {
        "k": 0.5,
        "prev_range": 1000,
        "target_offset_base": 500,
        "target_offset": 500,
        "target_price": 91000,
        "open_price": 0,
        "boards": {
            "pre_nxt": {"open_price": 90000, "target_price": 91000, "target_offset": 500},
        },
    }
    ltv._open_confirmed["005930"] = {"pre_nxt": True}
    ltv._prev_price["005930"] = {"pre_nxt": 90500}

    signal = ltv.check_buy_signal("005930", 99000, {})

    assert signal == Signal.NONE, (
        "PRE_NXT 활성 시 LTV 는 NONE 반환 — tradable_boards 에 pre_nxt 가 없어 보드 가드 차단"
    )


# ---------------------------------------------------------------------------
# 3. POST_NXT 보드 단독 활성 시 매수 신호 0
# ---------------------------------------------------------------------------
def test_ltv_buy_signal_zero_in_post_nxt(ltv, monkeypatch):
    """session_tracker 가 POST_NXT 만 활성일 때 LTV 매수 신호는 NONE 이어야 한다."""
    from src.engine.session import MarketBoard, session_tracker

    monkeypatch.setattr(session_tracker, "_active", frozenset({MarketBoard.POST_NXT}))
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", {
        "005930": {"current_price": 99000, "open_price": 90000, "change_rate": 10.0, "prev_close": 88000},
    })

    ltv._targets["005930"] = {
        "k": 0.5,
        "prev_range": 1000,
        "target_offset_base": 500,
        "target_offset": 500,
        "target_price": 91000,
        "open_price": 0,
        "boards": {
            "post_nxt": {"open_price": 90000, "target_price": 91000, "target_offset": 500},
        },
    }
    ltv._open_confirmed["005930"] = {"post_nxt": True}
    ltv._prev_price["005930"] = {"post_nxt": 90500}

    signal = ltv.check_buy_signal("005930", 99000, {})

    assert signal == Signal.NONE, (
        "POST_NXT 활성 시 LTV 는 NONE 반환 — tradable_boards 에 post_nxt 가 없어 보드 가드 차단"
    )
