"""사이클 C Red — BFB(눌림목 돌파) 브레이크이븐 승격 (default-off + live-ATR 래치).

명세: `_workspace/red/_behaviors_cycleC_breakeven_20260730.md` 행위 C-B1~C-B4.
자문: `_workspace/domain_consult/cycle_breakeven_promotion_rollout.md`
      (Q3(b) — BFB 는 measured-move 가 승자 전량 청산 + 최대 5영업일 → 한계효용 낮음,
       default-off 배포 후 관측. 롤아웃을 BFB 로 시작하지 말 것).
선례: VCP 동형 (`test_cycleC_vcp_breakeven.py`) — live ATR 래치 필수 논리 동일.

## VCP 와의 차이

- 로그 prefix `[bfb_breakeven_promote]`, N=1.5 동일.
- **recompute_high_since_buy 이식은 범위 외** (자문 — BFB 5영업일 한도라 한계효용 낮음, 후순위).
- `on_position_closed` 래치 discard 는 기존 `_partial_exit.pop` + 쿨다운 등록 *옆에* 동행.

## 인터페이스 계약 (tdd-engineer 확정 — backend-dev 구현 대상)

- 신규 인스턴스 필드 `self._breakeven_latched: set[str]` (`__init__`).
- 신규 DEFAULT_PARAMS `breakeven_promote_atr = 0.0` (default-off). PARAM_RANGES/INT_PARAMS 미편입.
- `check_exit_signal` 승격 로직 (VCP 동형, live atr = `_candidates[ticker]["atr14"]`):
    래치 add 조건 `high_since_buy >= buy + mult×atr` (최초 관측) → 이후 ATR 무관 유지,
    발화 `latched AND current_price <= buy_price` → STOP_LOSS (tighten-only).
- `on_position_closed(ticker)` 에 `_breakeven_latched.discard(ticker)` 추가.
"""

from __future__ import annotations

import datetime as _dt
from datetime import date

import pytest

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig
from src.engine.recommendation_engine import PARAM_RANGES, INT_PARAMS

pytestmark = pytest.mark.unit
KST = _dt.timezone(_dt.timedelta(hours=9))


def _mk(**params):
    cfg = StrategyConfig(strategy_id="bull_flag_breakout", name="BFB", weight=0.2,
                         params=dict(params))
    s = BullFlagBreakoutStrategy(cfg)
    s.state.total_investment = 100_000_000
    return s


def _pos(ticker="005490", buy_price=100_000, high_since_buy=0, buy_date=None):
    p = Position(ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
                 strategy_id="bull_flag_breakout", buy_date=buy_date or date(2026, 7, 30))
    p.high_since_buy = high_since_buy
    return p


def _isolating_info(atr14=2_000, flag_low=90_000):
    """승격 외 청산(하드손절/flag_low/measured-move/트레일링/시간)을 격리하는 _candidates 정보.

    measured_target = flag_high(96000) + (pole_high(95000)-pole_start(80000)) = 111000
    → current(≤ buy 근처) 미도달. flag_low 는 buy 아래로 격리.
    """
    return {
        "atr14": atr14,
        "flag_low": flag_low,
        "flag_high": 96_000,
        "pole_high": 95_000,
        "pole_start": 80_000,
    }


class _FrozenNow:
    """bull_flag_breakout.datetime 패치용 — 시간 청산(max_hold) 을 buy_date 당일로 고정."""

    def __init__(self, dt):
        self._dt = dt

    def now(self, tz=None):
        return self._dt


# ─────────────────────────────────────────────────────────────────────────
# C-B1 (HIGH) — live-ATR 래치 병리 재현: ATR 팽창해도 승격 유지
# ─────────────────────────────────────────────────────────────────────────
def test_CB1_latch_persists_after_atr_expansion(monkeypatch):
    """VCP C-V1 동형 — 고점이 buy+1.5×ATR 도달 래치 후, ATR 팽창해도 승격 유지.

    tick1: atr=2000, high=103000=buy+1.5×2000 → 래치 (가격 고점, 미발화).
    tick2: atr 10000 팽창 → 조건 산술상 거짓, 그래도 래치 유지 → buy 도달 STOP_LOSS.
    현행: 래치 필드 부재 → AttributeError 또는 무발화 → RED.
    """
    import src.engine.strategies.bull_flag_breakout as _bfb
    monkeypatch.setattr(_bfb, "datetime",
                        _FrozenNow(_dt.datetime(2026, 7, 30, 10, 0, tzinfo=KST)))

    s = _mk(breakeven_promote_atr=1.5)
    s.state.positions["005490"] = _pos(buy_price=100_000, high_since_buy=103_000,
                                       buy_date=date(2026, 7, 30))
    s._candidates["005490"] = _isolating_info(atr14=2_000)

    assert s.check_exit_signal("005490", 103_000, 0) == Signal.NONE
    assert "005490" in s._breakeven_latched, "C-B1: 최초 관측 시 래치 add"

    s._candidates["005490"]["atr14"] = 10_000  # 팽창 (un-latch 병리 트리거)
    sig = s.check_exit_signal("005490", 100_000, 0)
    assert sig == Signal.STOP_LOSS, (
        f"C-B1: ATR 팽창 후에도 래치 유지 → buy 도달 STOP_LOSS 기대, got {sig}"
    )


# ─────────────────────────────────────────────────────────────────────────
# C-B2 — 승격 발화 + tighten-only
# ─────────────────────────────────────────────────────────────────────────
def test_CB2_promotion_fires_at_buy_price(monkeypatch):
    """래치된 ticker 현재가 = buy → STOP_LOSS (하드손절 -5% 미달·flag_low 위여도 발화)."""
    import src.engine.strategies.bull_flag_breakout as _bfb
    monkeypatch.setattr(_bfb, "datetime",
                        _FrozenNow(_dt.datetime(2026, 7, 30, 10, 0, tzinfo=KST)))
    s = _mk(breakeven_promote_atr=1.5)
    s.state.positions["005490"] = _pos(buy_price=100_000, high_since_buy=103_000,
                                       buy_date=date(2026, 7, 30))
    s._candidates["005490"] = _isolating_info(atr14=2_000)
    s._breakeven_latched.add("005490")  # 현행 코드엔 필드 부재 → AttributeError RED
    assert s.check_exit_signal("005490", 100_000, 0) == Signal.STOP_LOSS


def test_CB2_promotion_tighten_only_no_fire_above_buy(monkeypatch):
    """tighten-only — 래치돼도 현재가 buy 위면 승격 미발화 (손절선 buy 위 확대 케이스 0)."""
    import src.engine.strategies.bull_flag_breakout as _bfb
    monkeypatch.setattr(_bfb, "datetime",
                        _FrozenNow(_dt.datetime(2026, 7, 30, 10, 0, tzinfo=KST)))
    s = _mk(breakeven_promote_atr=1.5)
    s.state.positions["005490"] = _pos(buy_price=100_000, high_since_buy=103_000,
                                       buy_date=date(2026, 7, 30))
    s._candidates["005490"] = _isolating_info(atr14=2_000)
    s._breakeven_latched.add("005490")
    assert s.check_exit_signal("005490", 100_500, 0) == Signal.NONE


# ─────────────────────────────────────────────────────────────────────────
# C-B3 (HIGH) — default-off 회귀 0
# ─────────────────────────────────────────────────────────────────────────
def test_CB3_default_param_is_off():
    """DEFAULT_PARAMS breakeven_promote_atr 기본값 = 0.0 (default-off 배포)."""
    assert BullFlagBreakoutStrategy.DEFAULT_PARAMS.get("breakeven_promote_atr") == 0.0


def test_CB3_disabled_no_latch_no_promotion(monkeypatch):
    """기본(off) 이면 임계 도달해도 래치/승격 무발화 — 기존 청산 스택 불변."""
    import src.engine.strategies.bull_flag_breakout as _bfb
    monkeypatch.setattr(_bfb, "datetime",
                        _FrozenNow(_dt.datetime(2026, 7, 30, 10, 0, tzinfo=KST)))
    s = _mk()  # 기본 0.0
    s.state.positions["005490"] = _pos(buy_price=100_000, high_since_buy=103_000,
                                       buy_date=date(2026, 7, 30))
    s._candidates["005490"] = _isolating_info(atr14=2_000)
    assert s.check_exit_signal("005490", 100_000, 0) == Signal.NONE
    assert not getattr(s, "_breakeven_latched", set()), "off 상태 래치 add 금지"


def test_CB3_existing_exit_stack_preserved_when_off(monkeypatch):
    """default-off 에서 기존 청산 발화 보존 (하드손절 -5% / flag_low / measured-move)."""
    import src.engine.strategies.bull_flag_breakout as _bfb
    monkeypatch.setattr(_bfb, "datetime",
                        _FrozenNow(_dt.datetime(2026, 7, 30, 10, 0, tzinfo=KST)))
    s = _mk()
    # 하드손절 -5% 정확 (트레일링 격리 = high_since_buy 0)
    s.state.positions["005490"] = _pos(buy_price=100_000, high_since_buy=0,
                                       buy_date=date(2026, 7, 30))
    s._candidates["005490"] = _isolating_info(atr14=2_000, flag_low=80_000)
    assert s.check_exit_signal("005490", 95_000, 0) == Signal.STOP_LOSS   # -5%
    assert s.check_exit_signal("005490", 95_100, 0) == Signal.NONE        # -4.9%
    # measured-move 도달 → TRAILING_STOP (전량 청산 신호)
    s.state.positions["005930"] = _pos(ticker="005930", buy_price=100_000,
                                        high_since_buy=111_000, buy_date=date(2026, 7, 30))
    s._candidates["005930"] = _isolating_info(atr14=2_000)  # target=111000
    assert s.check_exit_signal("005930", 111_000, 0) == Signal.TRAILING_STOP


# ─────────────────────────────────────────────────────────────────────────
# C-B4 — on_position_closed 래치 정리 (기존 _partial_exit / 쿨다운 옆 동행)
# ─────────────────────────────────────────────────────────────────────────
def test_CB4_on_position_closed_discards_latch():
    """전량 청산 시 _breakeven_latched discard (기존 _partial_exit.pop / 쿨다운 등록 보존 확인)."""
    s = _mk(breakeven_promote_atr=1.5)
    s._breakeven_latched.add("005490")
    s._partial_exit["005490"] = True
    s.on_position_closed("005490")
    assert "005490" not in s._breakeven_latched, (
        "C-B4: on_position_closed 가 _breakeven_latched 정리 (재진입 stale 차단)"
    )
    # 기존 정리 동작 보존 (회귀 가드)
    assert "005490" not in s._partial_exit
    assert "005490" in s._cooldown_until


# ─────────────────────────────────────────────────────────────────────────
# 신규 파라미터 PARAM_RANGES / INT_PARAMS 제외
# ─────────────────────────────────────────────────────────────────────────
def test_breakeven_key_excluded_from_param_ranges():
    assert "breakeven_promote_atr" not in PARAM_RANGES


def test_breakeven_key_excluded_from_int_params():
    assert "breakeven_promote_atr" not in INT_PARAMS
