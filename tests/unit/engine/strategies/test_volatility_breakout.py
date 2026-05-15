"""src/engine/strategies/volatility_breakout.py 단위 테스트.

- on_open_price_confirmed: 보드별 target_price = open_price + base × k_value_{board}
- check_buy_signal: 현재 활성 보드의 target_price 돌파 순간 BUY (보드별 first tick 기록만)
- check_exit_signal: 매수가 -3% 손절
- check_force_clear: 보유 전체 반환
- calc_buy_quantity: position_ratio + 1주 fallback
"""

from __future__ import annotations

import pytest

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def vb(monkeypatch):
    """scanner 격리 + session_tracker 활성 보드 초기화한 VB 인스턴스."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {"005930": "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="변동성 돌파", weight=0.3)
    )


def _activate(board: str):
    """SessionTracker active 보드 강제 셋팅."""
    session_tracker._active = frozenset({MarketBoard(board)})


def _seed_target(strategy, ticker, *, prev_range=1000, k=0.5):
    """prepare() 결과를 모사 — _targets dict 직접 시드."""
    target_offset_base = int(prev_range * k)
    strategy._targets[ticker] = {
        "k": k,
        "prev_range": prev_range,
        "target_offset_base": target_offset_base,
        "target_offset": target_offset_base,
        "target_price": 0,
        "open_price": 0,
        "boards": {},
    }
    strategy._open_confirmed[ticker] = {}


# ---------------------------------------------------------------------------
# DEFAULT_PARAMS — 보드별 K값 키 존재 검증
# ---------------------------------------------------------------------------
def test_default_params_includes_board_k_values():
    p = VolatilityBreakoutStrategy.DEFAULT_PARAMS
    assert p["k_value_krx_main"] == 1.0
    assert p["k_value_nxt_pre"] == 1.0
    # k_value_nxt_post 키는 보존 — DB 마이그레이션 + AI자문 응답 호환성 위해 유지
    # (실제로 사용되지 않지만 컬럼/필드 호환 보존, 2026-05-15 결함 D)
    assert p["k_value_nxt_post"] == 1.0
    # 2026-05-15 결함 D — VB 당일 15:20 일괄매도 정책 → POST_NXT 제외
    assert p["tradable_boards"] == ["pre_nxt", "main"]
    assert p["stop_loss_rate"] == -3.0


# ---------------------------------------------------------------------------
# on_open_price_confirmed — 보드별 시가/target 계산
# ---------------------------------------------------------------------------
def test_on_open_when_main_board_then_target_uses_krx_main_k(vb):
    _seed_target(vb, "005930", prev_range=1000, k=0.5)  # base = 500
    vb.config.params["k_value_krx_main"] = 1.2
    vb.on_open_price_confirmed("005930", open_price=80000, board="main")

    board = vb._targets["005930"]["boards"]["main"]
    assert board["open_price"] == 80000
    # target_offset = 500 * 1.2 = 600
    assert board["target_offset"] == 600
    assert board["target_price"] == 80600
    assert vb._open_confirmed["005930"]["main"] is True


def test_on_open_when_pre_nxt_board_then_target_uses_nxt_pre_k(vb):
    _seed_target(vb, "005930", prev_range=2000, k=0.4)  # base = 800
    vb.config.params["k_value_nxt_pre"] = 0.5
    vb.on_open_price_confirmed("005930", open_price=70000, board="pre_nxt")

    board = vb._targets["005930"]["boards"]["pre_nxt"]
    # 800 * 0.5 = 400
    assert board["target_offset"] == 400
    assert board["target_price"] == 70400


def test_on_open_when_unknown_ticker_then_no_op(vb):
    # 시드 안 한 ticker — 예외 없이 무시
    vb.on_open_price_confirmed("000660", open_price=100000, board="main")
    assert "000660" not in vb._targets


def test_on_open_records_top_level_compat_for_first_confirmed_board(vb):
    _seed_target(vb, "005930", prev_range=1000, k=0.5)
    vb.config.params["k_value_krx_main"] = 1.0
    vb.on_open_price_confirmed("005930", open_price=80000, board="main")

    info = vb._targets["005930"]
    # backwards-compat: 첫 보드 확정 시 top-level 에 노출
    assert info["open_price"] == 80000
    assert info["target_price"] == 80500


# ---------------------------------------------------------------------------
# check_buy_signal — 가드
# ---------------------------------------------------------------------------
def test_buy_when_no_active_board_then_none(vb):
    _seed_target(vb, "005930")
    # active 보드 비어있음
    assert vb.check_buy_signal("005930", 81000, 80000) == Signal.NONE


def test_buy_when_active_board_not_in_tradable_then_none(vb):
    _seed_target(vb, "005930")
    vb.config.params["tradable_boards"] = ["main"]
    _activate("pre_nxt")
    assert vb.check_buy_signal("005930", 81000, 80000) == Signal.NONE


def test_buy_when_target_unset_then_none(vb):
    _seed_target(vb, "005930")
    _activate("main")
    # 시가 0 → 자동 확정도 못 함 → target 0
    assert vb.check_buy_signal("005930", 81000, 0) == Signal.NONE


def test_buy_when_already_held_then_none(vb):
    _seed_target(vb, "005930")
    _activate("main")
    vb.state.positions["005930"] = Position(
        ticker="005930", buy_price=80000, quantity=1,
        order_no="O1", strategy_id="volatility_breakout",
    )
    assert vb.check_buy_signal("005930", 90000, 80000) == Signal.NONE


# ---------------------------------------------------------------------------
# check_buy_signal — 돌파 순간 감지 (보드별 first tick 기록만)
# ---------------------------------------------------------------------------
def test_buy_first_tick_per_board_records_only(vb):
    _seed_target(vb, "005930", prev_range=1000, k=0.5)  # base 500
    vb.config.params["k_value_krx_main"] = 1.0
    _activate("main")
    # 시가 80000 → target 80500
    # 첫 틱이 이미 81000 (target 초과)이지만 first tick 은 기록만
    assert vb.check_buy_signal("005930", 81000, 80000) == Signal.NONE


def test_buy_when_breakout_moment_then_buy(vb):
    _seed_target(vb, "005930", prev_range=1000, k=0.5)
    vb.config.params["k_value_krx_main"] = 1.0
    _activate("main")
    # 첫 틱 80200 (target 80500 미달) — 기록
    assert vb.check_buy_signal("005930", 80200, 80000) == Signal.NONE
    # 두 번째 틱 80500 (target 도달) — 돌파 → BUY
    assert vb.check_buy_signal("005930", 80500, 80000) == Signal.BUY
    # buy_signals 기록
    assert len(vb.state.buy_signals) == 1
    assert vb.state.buy_signals[0]["board"] == "main"


def test_buy_when_above_target_but_no_breakout_moment_then_none(vb):
    _seed_target(vb, "005930", prev_range=1000, k=0.5)
    vb.config.params["k_value_krx_main"] = 1.0
    _activate("main")
    # 첫 틱 80700 (이미 target 80500 초과) — first tick 은 기록만
    assert vb.check_buy_signal("005930", 80700, 80000) == Signal.NONE
    # 두 번째 틱 81000 — prev 80700 도 이미 target 이상이라 "돌파 순간" 아님
    assert vb.check_buy_signal("005930", 81000, 80000) == Signal.NONE


def test_buy_signal_per_board_is_independent(vb):
    """main 보드에서 first tick 기록 후 pre_nxt 보드 활성화되면 pre_nxt 첫 틱도 기록만."""
    _seed_target(vb, "005930", prev_range=1000, k=0.5)
    vb.config.params["k_value_krx_main"] = 1.0
    vb.config.params["k_value_nxt_pre"] = 1.0

    _activate("main")
    vb.check_buy_signal("005930", 80200, 80000)  # main 첫 틱

    # 보드 전환
    _activate("pre_nxt")
    # pre_nxt 의 첫 틱: 그 보드에서는 기록만 — target도 새로 확정해야 함
    # 시가 70000 → target 70500
    assert vb.check_buy_signal("005930", 80000, 70000) == Signal.NONE
    # 보드별 _prev_price 분리 검증
    assert vb._prev_price["005930"]["pre_nxt"] == 80000


# ---------------------------------------------------------------------------
# check_exit_signal — 손절
# ---------------------------------------------------------------------------
def test_exit_when_loss_breaches_minus_3_then_stop_loss(vb):
    vb.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="volatility_breakout",
    )
    assert vb.check_exit_signal("005930", 97000, 100000) == Signal.STOP_LOSS


def test_exit_when_loss_within_threshold_then_none(vb):
    vb.state.positions["005930"] = Position(
        ticker="005930", buy_price=100000, quantity=1,
        order_no="O1", strategy_id="volatility_breakout",
    )
    # -2.99% → 미발동
    assert vb.check_exit_signal("005930", 97001, 100000) == Signal.NONE


def test_exit_when_no_position_then_none(vb):
    assert vb.check_exit_signal("005930", 50000, 100000) == Signal.NONE


# ---------------------------------------------------------------------------
# check_force_clear / calc_buy_quantity
# ---------------------------------------------------------------------------
def test_force_clear_returns_all_positions(vb):
    vb.state.positions["005930"] = Position(
        ticker="005930", buy_price=80000, quantity=1,
        order_no="O1", strategy_id="volatility_breakout",
    )
    vb.state.positions["000660"] = Position(
        ticker="000660", buy_price=100000, quantity=2,
        order_no="O2", strategy_id="volatility_breakout",
    )
    assert set(vb.check_force_clear()) == {"005930", "000660"}


def test_calc_qty_when_amount_covers_qty(vb):
    vb.state.total_investment = 10_000_000  # 10% = 1M
    assert vb.calc_buy_quantity(current_price=10_000) == 100


def test_calc_qty_when_ratio_zero_but_total_covers_one_share(vb):
    vb.state.total_investment = 100_000  # 10% = 10k
    # 가격 50_000 → ratio 기준 0주, but total 100k >= 50k → 1주
    assert vb.calc_buy_quantity(current_price=50_000) == 1


def test_calc_qty_when_total_below_share_price_then_zero(vb):
    vb.state.total_investment = 30_000
    assert vb.calc_buy_quantity(current_price=50_000) == 0
