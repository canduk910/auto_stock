"""VB 보드별 손절 분리 (사이클 3, 2026-05-17).

배경:
    5/15 첫 자문의 VB `code_review_notes` 권고 — "보드별 개별 손절·진입시간
    파라미터 분리". K값은 이미 보드별 분리(`k_value_krx_main` / `k_value_nxt_pre` /
    `k_value_nxt_post`) 되어 있어 손절도 같은 패턴으로 확장.

VB 현재 운영:
    - 진입: PRE_NXT (08:00~09:00) + MAIN (09:00~15:20)
    - 손절: 단일 `stop_loss_rate = -3.0` (보드 무관)

본 사이클 — VB 의 `check_exit_signal` 가 활성 보드에 따라 보드별 손절 임계를
다르게 적용. 신규 키 우선순위:

    1. `params.get(f"stop_loss_{board}")` (보드별 키, 음수만)
    2. `params.get("stop_loss_rate")` (top-level fallback)

자율 결정 — `active_board` 전달 방식: 옵션 2 (전략 내부 `_resolve_active_board()`
조회). VB 의 `check_exit_signal(ticker, current_price, open_price)` 시그니처는
6 전략 공통이라 변경 없음 — risk.on_tick 호출부 영향 0.

Red 의도:
    A: VB params 에 `stop_loss_main: -3.0` 만 있고 활성 보드 main → 손절 -3% 발동
    B: params 에 `stop_loss_pre_nxt: -4.0` 만 있고 활성 보드 pre_nxt → 손절 -4% 발동
    C: 보드별 키 없고 `stop_loss_rate: -3.5` 만 → 모든 보드에서 -3.5% fallback
    D: 보드별 키 + top-level 모두 있으면 보드별 키 우선
    E: 활성 보드 미감지 (테스트 환경) → top-level fallback
    F: 5/15 운영값 (`stop_loss_rate: -3.5`) → fallback 동작 (회귀 보존)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_KST = timezone(timedelta(hours=9))


def _today_kst():
    """사이클 68 hotfix — CI UTC 자정 너머 KST 어긋남 차단 (production 일관)."""
    return datetime.now(_KST).date()

import pytest

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit


def _make_vb(params_override: dict | None = None) -> VolatilityBreakoutStrategy:
    """VB 인스턴스 빌더 — 매수 포지션 1개(`066570`)를 미리 등록한다.

    buy_date=today 로 익일 청산 분기 (`is_next_day=True`) 진입 방지.
    """
    config = StrategyConfig(
        strategy_id="volatility_breakout", name="VB", weight=0.3, enabled=True,
    )
    if params_override:
        config.params = dict(params_override)
    vb = VolatilityBreakoutStrategy(config)
    vb.state.positions["066570"] = Position(
        ticker="066570",
        buy_price=10_000,
        quantity=1,
        order_no="O-TEST",
        strategy_id="volatility_breakout",
        buy_date=_today_kst(),
    )
    return vb


def _activate_board(monkeypatch, board: MarketBoard) -> None:
    """SessionTracker.active 를 강제로 설정 — `_resolve_active_board` 가 board 반환."""
    monkeypatch.setattr(session_tracker, "_active", frozenset({board}))


def _clear_board(monkeypatch) -> None:
    """SessionTracker.active 를 빈 frozenset 으로 — `_resolve_active_board` 가 None 반환."""
    monkeypatch.setattr(session_tracker, "_active", frozenset())


# ---------------------------------------------------------------------------
# A. stop_loss_main 단독 → MAIN 활성 시 -3% 손절
# ---------------------------------------------------------------------------
def test_main_stop_loss_only_triggers_on_main_board(monkeypatch):
    """params 에 `stop_loss_main=-3.0` 만 있고 활성 보드 main → -3% 손절 발동.

    매수가 10000 → 손절가 9700 (-3.0%). 9699 면 STOP_LOSS 발동.
    """
    vb = _make_vb({
        "stop_loss_main": -3.0,
        # 기본 stop_loss_rate=-3.0 도 DEFAULT_PARAMS 에서 머지 — top-level 도 -3.0
        # 명세상 보드별 키 우선
    })
    _activate_board(monkeypatch, MarketBoard.MAIN)

    # -3.01% 손실 (보드별 임계 -3.0% 초과)
    signal = vb.check_exit_signal("066570", current_price=9_699, open_price=10_000)
    assert signal == Signal.STOP_LOSS, (
        f"stop_loss_main=-3.0 + 보드 main + 손실 -3.01% → STOP_LOSS 기대, got {signal}"
    )


# ---------------------------------------------------------------------------
# B. stop_loss_pre_nxt 단독 → PRE_NXT 활성 시 -4% 손절
# ---------------------------------------------------------------------------
def test_pre_nxt_stop_loss_only_triggers_on_pre_nxt_board(monkeypatch):
    """사이클 26: VB tradable_boards=("main",) → PRE_NXT 활성 시 board=None fallback.

    VB 는 KRX ONLY (MAIN 단독) → _resolve_active_board() 가 PRE_NXT 활성이어도 None 반환.
    None → top-level stop_loss_rate (-3.0) 적용.

    매수가 10000:
    - -3.5% (9650): STOP_LOSS 발동 (top-level -3.0% 임계 초과, board=None fallback)
    - params 에 stop_loss_pre_nxt=-4.0 있어도 pre_nxt 가 tradable_boards 에 없으면 무시
    """
    vb = _make_vb({
        "stop_loss_pre_nxt": -4.0,
        # top-level stop_loss_rate 는 DEFAULT_PARAMS 기본값(-3.0)
        # 사이클 26: pre_nxt 가 tradable_boards 에 없으므로 _resolve_active_board = None
        # → top-level stop_loss_rate (-3.0) fallback
    })
    _activate_board(monkeypatch, MarketBoard.PRE_NXT)

    # 사이클 26: board=None → top-level stop_loss_rate=-3.0 적용
    # -3.5% 손실 → -3.0% 초과이므로 STOP_LOSS 발동
    signal_mild = vb.check_exit_signal("066570", current_price=9_650, open_price=10_000)
    assert signal_mild == Signal.STOP_LOSS, (
        "사이클 26: VB PRE_NXT active + tradable_boards=('main',) → _resolve_active_board=None "
        "→ top-level stop_loss_rate=-3.0 적용 → -3.5% 손실에 STOP_LOSS 발동 기대"
    )

    # -4.01% 손실 → 당연히 STOP_LOSS 발동
    signal_hard = vb.check_exit_signal("066570", current_price=9_599, open_price=10_000)
    assert signal_hard == Signal.STOP_LOSS, (
        f"top-level -3.0% 임계 대폭 초과(-4.01%) → STOP_LOSS 기대, got {signal_hard}"
    )


# ---------------------------------------------------------------------------
# C. 보드별 키 없음 → top-level stop_loss_rate fallback (모든 보드)
# ---------------------------------------------------------------------------
def test_fallback_to_stop_loss_rate_when_board_keys_missing(monkeypatch):
    """보드별 키 모두 부재 + `stop_loss_rate=-3.5` → 모든 보드에서 -3.5% fallback.

    회귀 가드 — 운영자 Settings 갱신 없이 기존 운영값(`stop_loss_rate`) 그대로 작동.
    """
    vb = _make_vb({
        "stop_loss_rate": -3.5,
        # 보드별 키 없음
    })

    # MAIN 보드
    _activate_board(monkeypatch, MarketBoard.MAIN)
    signal_main_mild = vb.check_exit_signal("066570", current_price=9_700, open_price=10_000)
    assert signal_main_mild == Signal.NONE, (
        f"top-level -3.5% 인데 -3.0% 손실에 STOP_LOSS 발동 — fallback 오작동, got {signal_main_mild}"
    )
    signal_main_hard = vb.check_exit_signal("066570", current_price=9_649, open_price=10_000)
    assert signal_main_hard == Signal.STOP_LOSS, (
        f"top-level -3.5% 임계 도달했는데 STOP_LOSS 미발동, got {signal_main_hard}"
    )

    # PRE_NXT 보드
    _activate_board(monkeypatch, MarketBoard.PRE_NXT)
    signal_pre_hard = vb.check_exit_signal("066570", current_price=9_649, open_price=10_000)
    assert signal_pre_hard == Signal.STOP_LOSS, (
        f"PRE_NXT 도 top-level -3.5% fallback 으로 STOP_LOSS 기대, got {signal_pre_hard}"
    )


# ---------------------------------------------------------------------------
# D. 보드별 키 + top-level 모두 있으면 보드별 키 우선
# ---------------------------------------------------------------------------
def test_board_key_takes_precedence_over_top_level(monkeypatch):
    """보드별 `stop_loss_main=-2.5` + top-level `stop_loss_rate=-5.0` 동시.

    활성 보드 main → 보드별 키(-2.5) 우선 → -2.51% 손실에 STOP_LOSS.
    """
    vb = _make_vb({
        "stop_loss_main": -2.5,
        "stop_loss_rate": -5.0,
    })
    _activate_board(monkeypatch, MarketBoard.MAIN)

    # -2.51% 손실 → 보드별 -2.5 도달
    signal = vb.check_exit_signal("066570", current_price=9_749, open_price=10_000)
    assert signal == Signal.STOP_LOSS, (
        f"보드별 키(-2.5) 우선인데 -2.51% 손실에 STOP_LOSS 미발동 — top-level(-5.0) 적용? got {signal}"
    )


# ---------------------------------------------------------------------------
# E. 활성 보드 미감지 → top-level fallback
# ---------------------------------------------------------------------------
def test_no_active_board_falls_back_to_top_level(monkeypatch):
    """SessionTracker.active 가 빈 frozenset → `_resolve_active_board` None
    → 보드별 키 적용 불가 → top-level `stop_loss_rate` fallback.

    테스트 환경에서 session_tracker 미동작 시 자연 회복 경로.
    """
    vb = _make_vb({
        "stop_loss_main": -2.5,  # 보드별 키 있어도 활성 보드 미감지면 무시
        "stop_loss_rate": -3.5,
    })
    _clear_board(monkeypatch)

    # -3.0% 손실 → top-level -3.5% 미달, 보드별 -2.5% 이지만 활성 보드 미감지로 무시
    signal_mild = vb.check_exit_signal("066570", current_price=9_700, open_price=10_000)
    assert signal_mild == Signal.NONE, (
        f"활성 보드 없으면 top-level -3.5% fallback 기대, -3.0% 손실엔 NONE. got {signal_mild}"
    )

    # -3.51% 손실 → top-level -3.5% 도달
    signal_hard = vb.check_exit_signal("066570", current_price=9_649, open_price=10_000)
    assert signal_hard == Signal.STOP_LOSS, (
        f"활성 보드 없을 때 top-level -3.5% fallback 으로 STOP_LOSS 기대, got {signal_hard}"
    )


# ---------------------------------------------------------------------------
# F. 5/15 운영값 회귀 보존
# ---------------------------------------------------------------------------
def test_5_15_operational_params_regression_preserved(monkeypatch):
    """5/15 운영 fixture: `stop_loss_rate=-3.5` 단일 키 + 보드별 키 부재.

    회귀 가드 — 마이그 024 미적용 + 운영자 Settings 미갱신 시 기존 동작 그대로.
    """
    vb = _make_vb({
        "stop_loss_rate": -3.5,
        # 5/15 운영엔 보드별 키 없음
    })

    for board in (MarketBoard.MAIN, MarketBoard.PRE_NXT):
        _activate_board(monkeypatch, board)
        # -3.51% 손실 → top-level -3.5% 도달 → STOP_LOSS
        signal = vb.check_exit_signal("066570", current_price=9_649, open_price=10_000)
        assert signal == Signal.STOP_LOSS, (
            f"5/15 운영값 (top-level only) 회귀 결함: board={board.value}, got {signal}"
        )

        # -3.0% 손실은 top-level -3.5% 미달 → NONE
        signal_mild = vb.check_exit_signal("066570", current_price=9_700, open_price=10_000)
        assert signal_mild == Signal.NONE, (
            f"5/15 운영값 -3.0% 손실 (임계 미달) STOP_LOSS 오발동: board={board.value}, got {signal_mild}"
        )
