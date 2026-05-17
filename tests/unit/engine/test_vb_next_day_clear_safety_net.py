"""VB 익일 청산 안전망 (2026-05-15, 결함 D 잔여).

배경:
    VB 정책은 "당일 15:20 무조건 매도"인데, 15:20 청산이 어떤 이유로든 누락되면
    (예: tradable_boards 설정 오류로 POST_NXT 활성 / 시세 미수신 / 시장가 거부 /
    프로세스 재시작 race) -3% 손절선 외에 청산 트리거가 없어 영구 보유 가능.

    5/15 LG전자(066570) 14:33 매수가 본 경로로 청산 트리거 부재 상태로 잔존.

결정 (2026-05-15):
    안전망으로 VB 도 `_execute_next_day_clear()` 대상에 추가.
    - VB Position 의 is_next_day=True 면 다음 영업일 NXT 프리 시가 청산
    - 사용자 정책상 정상 동작은 15:20 청산이므로 본 경로는 비상 회복용

Red 의도:
    1. `VolatilityBreakoutStrategy.__init__` 에 `_next_day_clear_pending = False` 초기화
    2. `check_exit_signal` 이 `is_next_day=True` 보유 종목에 NEXT_DAY_CLEAR 신호 반환
       (단 `_next_day_clear_pending=True` 면 보류 — scheduler 가 직접 처리 중)
    3. `scheduler._execute_next_day_clear()` 의 overnight_strategies 에
       "volatility_breakout" 포함
"""

from __future__ import annotations

import inspect
from datetime import date, timedelta

import pytest

from src.engine.scheduler import TradingScheduler
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit


def test_vb_has_next_day_clear_pending_attr():
    """VB 인스턴스는 `_next_day_clear_pending = False` 초기화되어야 한다.

    `_execute_next_day_clear` 가 hasattr 가드 후 True 로 세팅하는 흐름이라
    속성 자체가 존재해야 가드가 활성화된다.
    """
    vb = VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3, enabled=True)
    )
    assert hasattr(vb, "_next_day_clear_pending"), (
        "VB 에 `_next_day_clear_pending` 속성 없음 — `_execute_next_day_clear` 의 "
        "on_tick 가드(`hasattr` 후 True 세팅)가 무시되어 시가 안정화 중에도 "
        "on_tick 청산이 발화될 위험."
    )
    assert vb._next_day_clear_pending is False, "초기값은 False"


def test_vb_check_exit_signal_returns_next_day_clear_for_yesterday_position():
    """is_next_day=True (전일 매수) 보유 종목에 NEXT_DAY_CLEAR 신호 반환.

    사용자 정책상 VB 는 OVERNIGHT 거부지만, 15:20 청산이 누락된 이상 보유 상태
    회복은 즉시 청산이 정답. 갭률·트레일링 분기 없이 단순 NEXT_DAY_CLEAR.
    """
    vb = VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3, enabled=True)
    )
    yesterday = date.today() - timedelta(days=1)
    vb.state.positions["066570"] = Position(
        ticker="066570", buy_price=237000, quantity=1,
        order_no="O-TEST", strategy_id="volatility_breakout", buy_date=yesterday,
    )
    pos = vb.state.positions["066570"]
    assert pos.is_next_day is True, "fixture sanity — 전일 매수면 is_next_day"

    signal = vb.check_exit_signal("066570", current_price=235000, open_price=235000)
    assert signal == Signal.NEXT_DAY_CLEAR, (
        f"is_next_day=True VB 포지션에 NEXT_DAY_CLEAR 신호가 반환되지 않음: {signal}. "
        "안전망 발동 경로 미동작."
    )


def test_vb_check_exit_signal_suppressed_while_scheduler_pending():
    """`_next_day_clear_pending=True` 이면 on_tick 청산 보류 — scheduler 가 직접 처리.

    시가 안정화 대기 중(`_execute_next_day_clear` 의 30s sleep) 즉시 청산하면
    안정화 의미 손실 + race 발생. momentum 패턴과 동일.
    """
    vb = VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3, enabled=True)
    )
    yesterday = date.today() - timedelta(days=1)
    vb.state.positions["066570"] = Position(
        ticker="066570", buy_price=237000, quantity=1,
        order_no="O-TEST", strategy_id="volatility_breakout", buy_date=yesterday,
    )
    vb._next_day_clear_pending = True

    # 손절선(-3%) 도달 안 한 일반 가격
    signal = vb.check_exit_signal("066570", current_price=235000, open_price=235000)
    assert signal == Signal.NONE, (
        "_next_day_clear_pending=True 상태인데 check_exit_signal 이 청산 신호 반환. "
        "scheduler 안정화 대기 중 on_tick race 발생 위험."
    )


def test_vb_stop_loss_still_works_when_next_day_pending():
    """`_next_day_clear_pending=True` 라도 -3% 손절은 그대로 작동 (안전 보장)."""
    vb = VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3, enabled=True)
    )
    yesterday = date.today() - timedelta(days=1)
    vb.state.positions["066570"] = Position(
        ticker="066570", buy_price=237000, quantity=1,
        order_no="O-TEST", strategy_id="volatility_breakout", buy_date=yesterday,
    )
    vb._next_day_clear_pending = True

    # -3.5% 손절 도달
    crash = int(237000 * 0.965)
    signal = vb.check_exit_signal("066570", current_price=crash, open_price=237000)
    assert signal == Signal.STOP_LOSS, (
        f"손절선 도달했는데 STOP_LOSS 신호 안 반환: {signal}. "
        "_next_day_clear_pending 가드가 손절까지 막으면 안 됨."
    )


def test_execute_next_day_clear_includes_volatility_breakout_in_overnight_strategies():
    """`_execute_next_day_clear` 의 overnight_strategies 튜플에 volatility_breakout 포함.

    소스 정적 검사로 검증 — 외부 의존성(WebSocket/KIS API) mock 없이 결함 회귀 차단.
    """
    src = inspect.getsource(TradingScheduler._execute_next_day_clear)
    # for sid in ("momentum", "long_tail_volatility", "volatility_breakout"): 패턴
    assert '"volatility_breakout"' in src, (
        "_execute_next_day_clear 의 overnight_strategies 튜플에 volatility_breakout 미포함. "
        "15:20 청산 누락 시 다음 영업일 자동 청산 안전망 미작동 — 5/15 LG전자 사고 회귀 위험."
    )


def test_vb_next_day_clear_signal_sets_pending_flag_idempotent():
    """사이클 10 (2026-05-18 hot fix) — NEXT_DAY_CLEAR 신호 직후 `_next_day_clear_pending=True` 영구 set.

    배경:
        5/18 08:00 정각 컨테이너 재시작 race 로 `_execute_next_day_clear` task cancel +
        `_pending_next_day_clear` set 미등록. scheduler 가 그 종목을 영영 처리 못 하면
        VB `check_exit_signal` 가드(`not self._next_day_clear_pending`) 가 영원히 False →
        매 on_tick(1초) 마다 NEXT_DAY_CLEAR 신호 발사 → OrderEngine NXT/SOR 시장가 →
        KIS `KIOK0320 장운영시간이 아닙니다` 거부 → positions 보존 → 다음 on_tick 또 발사 →
        무한 루프 매초 1회.

    fix:
        NEXT_DAY_CLEAR 신호 return 직전에 `self._next_day_clear_pending = True` set 하여
        idempotent 보장. OrderEngine 시장가 거부 후에도 플래그 True 유지 → 다음 on_tick
        신호 안 보냄. 15:20 `_force_clear_main_only` 가 정규장 KRX 시장가로 청산 흡수.
        LTV/momentum 의 `_next_day_clear_pending` 패턴과 일관.

    Red 의도:
        첫 호출: NEXT_DAY_CLEAR 반환 + 플래그 True 로 set
        두 번째 호출: NONE 반환 (가드에 막힘) — 무한 루프 차단 검증
    """
    vb = VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3, enabled=True)
    )
    yesterday = date.today() - timedelta(days=1)
    vb.state.positions["066570"] = Position(
        ticker="066570", buy_price=237000, quantity=1,
        order_no="O-TEST", strategy_id="volatility_breakout", buy_date=yesterday,
    )
    assert vb._next_day_clear_pending is False, "fixture sanity — 초기값 False"

    # 1st call: NEXT_DAY_CLEAR 신호 + 플래그 True set
    sig1 = vb.check_exit_signal("066570", current_price=235000, open_price=235000)
    assert sig1 == Signal.NEXT_DAY_CLEAR, (
        f"1차 호출에서 NEXT_DAY_CLEAR 신호 미발사: {sig1}"
    )
    assert vb._next_day_clear_pending is True, (
        "NEXT_DAY_CLEAR 신호 발사 직후 `_next_day_clear_pending` 이 True 로 set 되지 않음. "
        "5/18 운영 사고: scheduler `_pending_next_day_clear` 미등록 race 시 매 on_tick 신호 발사 → "
        "KIS KIOK0320 거부 무한 루프. 신호 return 직전에 영구 set 필요."
    )

    # 2nd call: 같은 가격 — 가드에 막혀 NONE
    sig2 = vb.check_exit_signal("066570", current_price=235000, open_price=235000)
    assert sig2 == Signal.NONE, (
        f"2차 호출에서 NEXT_DAY_CLEAR 재발사: {sig2}. "
        "`_next_day_clear_pending=True` 가드가 작동하지 않아 매초 1회 무한 신호 차단 실패. "
        "OrderEngine 시장가 거부 → positions 보존 → 다음 on_tick 또 신호 발사 패턴 회귀 위험."
    )
