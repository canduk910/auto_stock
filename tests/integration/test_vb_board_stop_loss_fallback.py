"""VB 보드별 손절 fallback 통합 (사이클 3, 2026-05-17).

배경:
    사이클 3 — VB 보드별 손절 분리. 마이그 024 적용 전(기존 `stop_loss_rate` 만)
    과 적용 후(보드별 키 자동 복사) 두 시나리오에서 운영 매매 흐름이 동일하게
    작동함을 통합 수준에서 검증.

시나리오:
    M: 마이그 024 적용 전 (5/18 첫 발화 직전 운영 상태)
       - params = {"stop_loss_rate": -3.5}
       - 모든 활성 보드에서 -3.5% fallback

    N: 마이그 024 적용 후 (운영자 Settings 미갱신)
       - params = {"stop_loss_rate": -3.5, "stop_loss_main": -3.5, "stop_loss_pre_nxt": -3.5}
       - 보드별 키 = top-level 동일값으로 자동 복사 → 동일 동작

    O: 마이그 024 적용 후 + 운영자 차별화
       - params = {"stop_loss_rate": -3.5, "stop_loss_main": -3.0, "stop_loss_pre_nxt": -4.0}
       - main: -3.0 / pre_nxt: -4.0 — 보드별 차별 손절
"""

from __future__ import annotations

from datetime import date

import pytest

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.integration


def _make_vb_with_position(params: dict) -> VolatilityBreakoutStrategy:
    config = StrategyConfig(
        strategy_id="volatility_breakout", name="VB", weight=0.3, enabled=True,
    )
    config.params = dict(params)
    vb = VolatilityBreakoutStrategy(config)
    vb.state.positions["066570"] = Position(
        ticker="066570",
        buy_price=10_000,
        quantity=1,
        order_no="O-TEST",
        strategy_id="volatility_breakout",
        buy_date=date.today(),  # 당일 매수 — is_next_day=False
    )
    return vb


def _activate(monkeypatch, board: MarketBoard) -> None:
    monkeypatch.setattr(session_tracker, "_active", frozenset({board}))


# ---------------------------------------------------------------------------
# M. 마이그 024 적용 전 — 5/18 첫 발화 직전 상태
# ---------------------------------------------------------------------------
def test_pre_migration_top_level_only_works_on_all_boards(monkeypatch):
    """마이그 024 미적용 — `stop_loss_rate` 단일 키 → 모든 보드 동일 적용.

    실전 fixture: 운영 EC2 가 5/18 월 20:00 첫 자문 발화 직전.
    DB strategy_config.params 갱신 없이도 본 코드 변경이 회귀 0건임을 보장.
    """
    params = {"stop_loss_rate": -3.5}
    vb = _make_vb_with_position(params)

    for board in (MarketBoard.MAIN, MarketBoard.PRE_NXT):
        _activate(monkeypatch, board)
        # -3.51% 손실 → top-level -3.5% fallback → STOP_LOSS
        signal_hard = vb.check_exit_signal("066570", current_price=9_649, open_price=10_000)
        assert signal_hard == Signal.STOP_LOSS, (
            f"마이그 전 회귀 결함: board={board.value}, 5/18 첫 발화 영향 위험. got {signal_hard}"
        )
        # -3.0% 손실은 임계 미달 → NONE
        signal_mild = vb.check_exit_signal("066570", current_price=9_700, open_price=10_000)
        assert signal_mild == Signal.NONE, (
            f"마이그 전 회귀 결함 (오발동): board={board.value}, got {signal_mild}"
        )


# ---------------------------------------------------------------------------
# N. 마이그 024 적용 후, 운영자 Settings 미갱신
# ---------------------------------------------------------------------------
def test_post_migration_board_keys_same_as_top_level(monkeypatch):
    """마이그 024 적용 — 보드별 키 = top-level 동일값 자동 복사.

    SQL 결과:
      params = jsonb_build_object('stop_loss_main', stop_loss_rate,
                                   'stop_loss_pre_nxt', stop_loss_rate)
    → main/pre_nxt 모두 -3.5 같은 동작.
    """
    params = {
        "stop_loss_rate": -3.5,
        "stop_loss_main": -3.5,    # 마이그 자동 복사
        "stop_loss_pre_nxt": -3.5,  # 마이그 자동 복사
    }
    vb = _make_vb_with_position(params)

    for board in (MarketBoard.MAIN, MarketBoard.PRE_NXT):
        _activate(monkeypatch, board)
        # -3.51% 손실 → 보드별 -3.5% → STOP_LOSS
        signal_hard = vb.check_exit_signal("066570", current_price=9_649, open_price=10_000)
        assert signal_hard == Signal.STOP_LOSS, (
            f"마이그 후 (운영자 미갱신) 회귀 결함: board={board.value}, got {signal_hard}"
        )
        signal_mild = vb.check_exit_signal("066570", current_price=9_700, open_price=10_000)
        assert signal_mild == Signal.NONE, (
            f"마이그 후 -3.0% 손실 오발동: board={board.value}, got {signal_mild}"
        )


# ---------------------------------------------------------------------------
# O. 마이그 024 적용 후 + 운영자 차별화
# ---------------------------------------------------------------------------
def test_post_migration_operator_differentiated(monkeypatch):
    """마이그 + 운영자 Settings 에서 main -3.0 차별화. PRE_NXT 는 사이클 26 제거.

    사이클 26 (2026-05-20): VB tradable_boards=("main",) → _resolve_active_board가
    PRE_NXT 활성 시 None 반환 → top-level stop_loss_rate 적용.
    """
    params = {
        "stop_loss_rate": -3.5,
        "stop_loss_main": -3.0,
        "stop_loss_pre_nxt": -4.0,
    }
    vb = _make_vb_with_position(params)

    # MAIN — stop_loss_main=-3.0 임계
    _activate(monkeypatch, MarketBoard.MAIN)
    # -3.01% 손실 → MAIN -3.0% 도달
    signal_main_hard = vb.check_exit_signal("066570", current_price=9_699, open_price=10_000)
    assert signal_main_hard == Signal.STOP_LOSS, (
        f"MAIN 차별화 -3.0 임계 미작동: got {signal_main_hard}"
    )
    # -2.5% 손실 → MAIN 임계 미달
    signal_main_mild = vb.check_exit_signal("066570", current_price=9_750, open_price=10_000)
    assert signal_main_mild == Signal.NONE, (
        f"MAIN -2.5% 손실 STOP_LOSS 오발동: got {signal_main_mild}"
    )

    # PRE_NXT — 사이클 26: VB tradable_boards 에서 제거 → board=None → top-level stop_loss_rate=-3.5
    _activate(monkeypatch, MarketBoard.PRE_NXT)
    # -3.5% 손실 → top-level stop_loss_rate=-3.5 도달 → STOP_LOSS 발동
    # (stop_loss_pre_nxt=-4.0 는 tradable_boards 에 pre_nxt 없으므로 무시)
    signal_pre_mild = vb.check_exit_signal("066570", current_price=9_650, open_price=10_000)
    assert signal_pre_mild == Signal.STOP_LOSS, (
        "사이클 26: VB PRE_NXT active + tradable_boards=('main',) → _resolve_active_board=None "
        "→ top-level stop_loss_rate=-3.5 적용 → -3.5% 손실에 STOP_LOSS 발동 기대"
    )
    # -4.01% 손실 → 당연히 STOP_LOSS
    signal_pre_hard = vb.check_exit_signal("066570", current_price=9_599, open_price=10_000)
    assert signal_pre_hard == Signal.STOP_LOSS, (
        f"top-level stop_loss_rate=-3.5 대폭 초과(-4.01%) → STOP_LOSS 기대, got {signal_pre_hard}"
    )
