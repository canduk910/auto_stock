"""LTV 작업 1 (2026-05-13) — get_targets_status 가 활성 보드만 노출한다.

VB 와 동일 구조의 검증. `limit_up_reached` 키는 보존되어야 한다.

명세 (`_workspace/00_leader_trading_rules.md` L420~466):
- `active_boards = session_tracker.active` (frozenset[MarketBoard])
- `tradable = parse_tradable_boards(...)` 또는 `DEFAULT_TRADABLE_BOARDS` fallback
- `visible = {b.value for b in (active_boards & tradable)}`
- ticker 별:
  - `visible == set()`: `boards={}`, top-level `target_price/open_price/target_offset=0`, `open_confirmed={}`
  - `visible != set()`: 기존 `info.get("boards", {})` 중 `b in visible` 만 dict 에 포함
  - top-level 은 노출 보드 중 우선순위(main → post_nxt → pre_nxt) 첫 `confirmed=True` 보드 기준 → 없으면 우선순위 첫 보드 값(미확정이면 0)
- session_tracker import/`active` 접근 예외 시 → **기존 모든 보드 노출** (fallback)
"""

from __future__ import annotations

import pytest

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def ltv(monkeypatch):
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {"005930": "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="롱테일 변동성", weight=0.3)
    )


def _seed_with_boards(strategy, ticker, *, boards: dict, confirmed: dict, k=0.5):
    """`_targets[ticker].boards` 와 `_open_confirmed[ticker]` 를 직접 시드."""
    strategy._targets[ticker] = {
        "k": k,
        "prev_range": 1000,
        "target_offset_base": int(1000 * k),
        "target_offset": 0,
        "target_price": 0,
        "open_price": 0,
        "boards": boards,
    }
    strategy._open_confirmed[ticker] = confirmed


# ---------------------------------------------------------------------------
# 1. active={MAIN} → boards={"main"} 만 노출
# ---------------------------------------------------------------------------
def test_get_targets_status_returns_only_active_boards(ltv):
    session_tracker._active = frozenset({MarketBoard.MAIN})
    _seed_with_boards(
        ltv,
        "005930",
        boards={
            "main": {"open_price": 80000, "target_price": 80500, "target_offset": 500},
            "pre_nxt": {"open_price": 79000, "target_price": 79400, "target_offset": 400},
        },
        confirmed={"main": True, "pre_nxt": True},
    )

    status = ltv.get_targets_status()

    assert "005930" in status
    assert list(status["005930"]["boards"].keys()) == ["main"]
    assert status["005930"]["boards"]["main"]["target_price"] == 80500
    # top-level 도 main 기준 (확정)
    assert status["005930"]["target_price"] == 80500
    assert status["005930"]["open_price"] == 80000
    # open_confirmed 도 노출 보드만
    assert status["005930"]["open_confirmed"] == {"main": True}
    # limit_up_reached 키 보존
    assert "limit_up_reached" in status["005930"]
    assert status["005930"]["limit_up_reached"] is False


# ---------------------------------------------------------------------------
# 2. active 보드와 tradable 교집합 없음 → boards={} + top-level=0
# ---------------------------------------------------------------------------
def test_get_targets_status_returns_empty_when_no_active_board_intersection(ltv):
    # KRX_AFTER 는 LTV tradable_boards (pre_nxt/main/post_nxt) 에 없음
    session_tracker._active = frozenset({MarketBoard.KRX_AFTER})
    _seed_with_boards(
        ltv,
        "005930",
        boards={
            "main": {"open_price": 80000, "target_price": 80500, "target_offset": 500},
        },
        confirmed={"main": True},
    )

    status = ltv.get_targets_status()

    assert status["005930"]["boards"] == {}
    assert status["005930"]["target_price"] == 0
    assert status["005930"]["open_price"] == 0
    assert status["005930"]["target_offset"] == 0
    assert status["005930"]["open_confirmed"] == {}
    # limit_up_reached 키 보존
    assert "limit_up_reached" in status["005930"]


# ---------------------------------------------------------------------------
# 3. top-level 은 활성 보드 중 우선순위 첫 confirmed 보드 기준
# ---------------------------------------------------------------------------
def test_get_targets_status_top_level_uses_first_active_confirmed_board(ltv):
    # 사이클 38 (2026-05-22): LTV tradable_boards = ("pre_nxt", "main", "post_nxt") 복원.
    # MAIN + PRE_NXT 동시 활성 + 둘 다 LTV tradable_boards 에 포함 → 둘 다 visible.
    # top-level 은 우선순위(main → post_nxt → pre_nxt) 첫 confirmed 보드 기준 → main.
    session_tracker._active = frozenset({MarketBoard.MAIN, MarketBoard.PRE_NXT})
    _seed_with_boards(
        ltv,
        "005930",
        boards={
            "main": {"open_price": 80000, "target_price": 80500, "target_offset": 500},
            "pre_nxt": {"open_price": 79000, "target_price": 79400, "target_offset": 400},
        },
        confirmed={"main": True, "pre_nxt": True},
    )

    status = ltv.get_targets_status()

    # 사이클 38: LTV tradable_boards = 3 보드 → main + pre_nxt 둘 다 노출
    assert set(status["005930"]["boards"].keys()) == {"main", "pre_nxt"}
    # top-level 은 main 기준 (우선순위 첫 confirmed)
    assert status["005930"]["target_price"] == 80500
    assert status["005930"]["open_price"] == 80000
    assert status["005930"]["target_offset"] == 500


# ---------------------------------------------------------------------------
# 3-bis. top-level 우선순위 보드가 미확정이면 0 (값 유출 차단)
# ---------------------------------------------------------------------------
def test_get_targets_status_top_level_zero_when_priority_board_unconfirmed(ltv):
    # MAIN 활성, main 미확정 → top-level 은 main 0
    session_tracker._active = frozenset({MarketBoard.MAIN})
    _seed_with_boards(
        ltv,
        "005930",
        boards={
            "main": {"open_price": 0, "target_price": 0, "target_offset": 0},
        },
        confirmed={"main": False},
    )

    status = ltv.get_targets_status()

    assert status["005930"]["boards"]["main"]["confirmed"] is False
    # top-level 은 미확정 보드 값 그대로 = 0
    assert status["005930"]["target_price"] == 0
    assert status["005930"]["open_price"] == 0


# ---------------------------------------------------------------------------
# 4. session_tracker import 실패 시 모든 보드 노출 (외부 호환 fallback)
# ---------------------------------------------------------------------------
def test_get_targets_status_when_session_module_unavailable_falls_back_to_all_boards(ltv, monkeypatch):
    """session.session_tracker 접근이 예외 발생 → 기존 모든 보드 노출 동작 유지."""
    _seed_with_boards(
        ltv,
        "005930",
        boards={
            "main": {"open_price": 80000, "target_price": 80500, "target_offset": 500},
            "pre_nxt": {"open_price": 79000, "target_price": 79400, "target_offset": 400},
        },
        confirmed={"main": True, "pre_nxt": True},
    )

    # session_tracker.active 접근 시 예외 발생하도록 monkeypatch
    class _Boom:
        @property
        def active(self):
            raise RuntimeError("simulated session module failure")

    import src.engine.session as sess
    monkeypatch.setattr(sess, "session_tracker", _Boom())

    status = ltv.get_targets_status()

    # fallback — 모든 보드 노출
    assert set(status["005930"]["boards"].keys()) == {"main", "pre_nxt"}


# ---------------------------------------------------------------------------
# 5. limit_up_reached=True 상태 시에도 활성 보드 필터링 적용 + 키 보존
# ---------------------------------------------------------------------------
def test_get_targets_status_preserves_limit_up_reached_flag_after_filter(ltv):
    """LTV 특유의 `limit_up_reached` 필드는 활성 보드 필터링과 무관하게 보존."""
    session_tracker._active = frozenset({MarketBoard.MAIN})
    _seed_with_boards(
        ltv,
        "005930",
        boards={
            "main": {"open_price": 80000, "target_price": 80500, "target_offset": 500},
            "pre_nxt": {"open_price": 79000, "target_price": 79400, "target_offset": 400},
        },
        confirmed={"main": True, "pre_nxt": True},
    )
    ltv._limit_up_reached.add("005930")

    status = ltv.get_targets_status()

    # 노출 보드 main 만 + limit_up_reached True 보존
    assert list(status["005930"]["boards"].keys()) == ["main"]
    assert status["005930"]["limit_up_reached"] is True
