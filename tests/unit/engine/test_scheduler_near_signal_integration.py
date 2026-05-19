"""scheduler 통합 — _near_signal_loop + priority_groups mode 분기 (사이클 15-B-2, 2026-05-19).

near_signal_mode env var 토글 + _build_priority_groups 분기 검증.
_near_signal_loop task 자체는 통합 테스트로 분리 (asyncio.sleep 60s) — 본 단위는 분기만.

5 케이스:
1. near_signal_mode=False (기본) — priority_groups momentum/breakout 기존 값 유지
2. near_signal_mode=True — momentum/breakout 빈 list
3. near_signal_mode 토글 무관 positions/next_day_clear 보존
4. _near_signal_task 속성 존재 (init 시점 None)
5. stop 의 task cancel 루프에 _near_signal_task 포함
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def scheduler():
    from src.engine.scheduler import TradingScheduler
    return TradingScheduler()


# ===========================================================================
# Case 1: near_signal_mode=False — 기존 동작
# ===========================================================================
def test_priority_groups_mode_disabled_preserves_candidates(scheduler, monkeypatch):
    """near_signal_mode=False → momentum/breakout 기존 값."""
    from src.config import settings
    monkeypatch.setattr(settings, "near_signal_mode", False, raising=False)

    # mock: breakout_tickers / positions
    monkeypatch.setattr(scheduler, "_collect_breakout_tickers", lambda: ["B001", "B002"])

    groups = scheduler._build_priority_groups(momentum_tickers=["M001", "M002"])

    assert groups["momentum"] == ["M001", "M002"]
    assert groups["breakout"] == ["B001", "B002"]
    assert groups["positions"] == []
    assert groups["next_day_clear"] == []
    assert groups["swing"] == []


# ===========================================================================
# Case 2: near_signal_mode=True — 후보 종목 빈 list
# ===========================================================================
def test_priority_groups_mode_enabled_clears_candidates(scheduler, monkeypatch):
    """near_signal_mode=True → momentum/breakout 빈 list."""
    from src.config import settings
    monkeypatch.setattr(settings, "near_signal_mode", True, raising=False)

    monkeypatch.setattr(scheduler, "_collect_breakout_tickers", lambda: ["B001", "B002"])

    groups = scheduler._build_priority_groups(momentum_tickers=["M001", "M002"])

    assert groups["momentum"] == []
    assert groups["breakout"] == []
    assert groups["swing"] == []


# ===========================================================================
# Case 3: positions / next_day_clear 보존 (mode 무관)
# ===========================================================================
def test_priority_groups_positions_preserved_in_both_modes(scheduler, monkeypatch):
    """positions / next_day_clear 는 mode 무관 항상 채워짐."""
    from src.config import settings
    from src.engine.strategy_base import Position

    # momentum 전략에 보유 1종목
    momentum = scheduler.registry.get("momentum")
    momentum.state.positions["005930"] = Position(
        ticker="005930", buy_price=70000, quantity=10,
        order_no="OS001", strategy_id="momentum",
    )
    scheduler._pending_next_day_clear.add(("079550", "volatility_breakout"))

    for mode in (False, True):
        monkeypatch.setattr(settings, "near_signal_mode", mode, raising=False)
        groups = scheduler._build_priority_groups(momentum_tickers=[])
        assert "005930" in groups["positions"]
        assert "079550" in groups["next_day_clear"]


# ===========================================================================
# Case 4: _near_signal_task 속성 존재
# ===========================================================================
def test_near_signal_task_attribute_init(scheduler):
    assert hasattr(scheduler, "_near_signal_task")
    assert scheduler._near_signal_task is None


# ===========================================================================
# Case 5: stop 의 cancel 루프에 _near_signal_task 포함
# ===========================================================================
def test_stop_cancel_loop_includes_near_signal_task():
    """src/engine/scheduler.py stop() 의 task_attr 튜플에 _near_signal_task 포함 — 회귀 가드."""
    from pathlib import Path
    src = Path("/Users/koscom/Projects/auto_stock/src/engine/scheduler.py").read_text()
    # stop() 함수 안의 task_attr 튜플 확인
    # finally cancel + stop() cancel 2 곳 모두 포함되어야 함
    occurrences = src.count('"_near_signal_task"')
    assert occurrences >= 2, (
        f"_near_signal_task 가 finally + stop() 두 cancel 루프 모두 포함되어야 함. "
        f"실제 count={occurrences}"
    )
