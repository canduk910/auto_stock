"""kojiro 2ATR 하드손절의 `_candidates` 의존 결함 — 회귀 가드.

## 라이브 실증 (2026-08-04 12:00, 삼영무역 002810)

    매수 23,400 × 2주 · 현재가 21,550 (−7.9%)
      2ATR 손절선 21,674  ← 현재가가 124원 아래인데 **미발화**
      −8% backstop 21,528 ← 22원 남음

`_candidates` 8건 중 보유 6종목 가운데 **002810 만 부재**(07:48 부팅 recompute 시엔
`ATR=863.0` 으로 존재했음). 당일 `[kojiro_atr_stop]` 로그 0건.

## 결함 메커니즘

`check_exit_signal` 의 2ATR 분기가 `_candidates` live ATR 에만 의존한다:

    info = self._candidates.get(ticker)
    atr = float(info["atr"]) if info else 0.0
    if atr > 0 and pos.buy_price > 0:      # ← 부재 시 분기 통째로 skip
        eff = max(base, self._stop_floor.get(ticker))   # ← floor 도 여기서만 읽힘

`_candidates` 는 `prepare()` 마다 `{}` 로 와이프되고 held 재채움은 ATR 밴드·유니버스
컷에 걸리면 보장되지 않는다. 결과: **2ATR 손절이 조용히 사라지고 −8% backstop 만
남는다**. 저ATR 종목이면 −3% 에 나갔어야 할 손절이 −8% 까지 방치돼 최대 5%p 지연.

부수 결함: 이미 저장된 `_stop_floor`(트레일링으로 올려둔 손절선)조차 `atr > 0`
블록 안에서만 읽히므로 ATR 이 사라지면 **함께 무시**된다.

## 시정 (사이클 J `_position_sectors` 패턴 답습)

1. **`_position_atr` 영속 맵** — `_candidates` 와이프 독립, 포지션 수명 생존.
   stamp 3지점: `recompute_held_atr`(전일 held 정본) / `check_buy_signal` BUY 반환
   직전(당일 매수) / `on_position_closed` pop.
2. **ATR 폴백 우선순위** — `_candidates` live ATR(설계 의도 = 변동성 변화 반영) →
   부재 시 `_position_atr` 마지막 정본.
3. **`_stop_floor` 독립 승격** — ATR 이 전무해도 마지막 확정 손절선으로 손절 판정.

⚠️ `_reset_daily_state` override 추가 금지 — 멀티데이 held 의 ATR 이 밤새 소멸한다
(사이클 J 와 동일 이유, AST 봉인).

donchian 은 `_entry_atr` 를 포지션 수명 dict 로 별도 보관해 이 병리가 없다. kojiro 만
휘발성 `_candidates` 에 의존했다.
"""

from __future__ import annotations

import inspect

import pytest

from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit


def _kojiro(**extra):
    s = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.6, params=extra),
    )
    s.state.total_investment = 690_111
    return s


def _hold(s, ticker="002810", buy=23_400, qty=2):
    s.state.positions[ticker] = Position(
        ticker=ticker, buy_price=buy, quantity=qty, order_no="O", strategy_id="kojiro",
    )
    return s.state.positions[ticker]


# ---------------------------------------------------------------------------
# E-1 — 핵심: `_candidates` 부재 + `_position_atr` 존재 → 2ATR 손절 정상 발화
#        (2026-08-04 삼영무역 실측 재현)
# ---------------------------------------------------------------------------
def test_atr_stop_fires_from_position_atr_when_candidates_missing():
    s = _kojiro()
    _hold(s)
    s._position_atr["002810"] = 863.0          # 07:48 recompute 정본
    assert "002810" not in s._candidates       # prepare 와이프로 소실된 상태
    # 손절선 = 23,400 − 2×863 = 21,674. 현재가 21,550 ≤ 21,674 → 발화해야 한다
    assert s.check_exit_signal("002810", 21_550, 23_400) == Signal.STOP_LOSS


def test_no_stop_above_line_even_with_fallback_atr():
    s = _kojiro()
    _hold(s)
    s._position_atr["002810"] = 863.0
    assert s.check_exit_signal("002810", 21_700, 23_400) == Signal.NONE


# ---------------------------------------------------------------------------
# E-2 — `_candidates` live ATR 우선 (설계 의도 보존)
# ---------------------------------------------------------------------------
def test_candidates_atr_takes_precedence_over_position_atr():
    s = _kojiro()
    _hold(s)
    s._candidates["002810"] = {"atr": 400.0, "stage": 1, "prev_close": 23_400}
    s._position_atr["002810"] = 863.0
    # live 400 → 손절선 22,600. 폴백 863 이었다면 21,674 라 미발화였을 구간
    assert s.check_exit_signal("002810", 22_550, 23_400) == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# E-3 — ATR 전무 + `_stop_floor` 존재 → 마지막 확정 손절선으로 판정
# ---------------------------------------------------------------------------
def test_stop_floor_alone_still_stops_when_atr_unavailable():
    s = _kojiro()
    _hold(s)
    s._stop_floor["002810"] = 22_000          # 과거 확정된 손절선
    assert not s._candidates and not s._position_atr
    assert s.check_exit_signal("002810", 21_900, 23_400) == Signal.STOP_LOSS
    assert s.check_exit_signal("002810", 22_100, 23_400) == Signal.NONE


# ---------------------------------------------------------------------------
# E-4 — 셋 다 없으면 기존대로 −8% backstop 만 (byte 동일)
# ---------------------------------------------------------------------------
def test_falls_back_to_pct_backstop_when_nothing_available():
    s = _kojiro()
    _hold(s)
    assert s.check_exit_signal("002810", 21_600, 23_400) == Signal.NONE   # −7.7%
    assert s.check_exit_signal("002810", 21_528, 23_400) == Signal.STOP_LOSS  # −8.0%


# ---------------------------------------------------------------------------
# E-5 — tighten-only 유지: 폴백 ATR 로도 손절선이 내려가지 않는다
# ---------------------------------------------------------------------------
def test_fallback_atr_never_loosens_existing_floor():
    s = _kojiro()
    _hold(s)
    s._stop_floor["002810"] = 22_500          # 트레일링으로 상향된 선
    s._position_atr["002810"] = 863.0         # base 21,674 (더 낮음)
    # 더 높은 22,500 이 유지돼야 한다
    assert s.check_exit_signal("002810", 22_400, 23_400) == Signal.STOP_LOSS
    assert s._stop_floor["002810"] >= 22_500


# ---------------------------------------------------------------------------
# E-6 — stamp 3지점
# ---------------------------------------------------------------------------
def test_recompute_stamps_position_atr():
    # recompute 는 일봉 fetch + pandas enrich 의존 — 스탬프 지점 존재를 정적으로 고정
    src = inspect.getsource(KojiroStrategy.recompute_held_atr)
    assert "_position_atr[" in src, (
        "recompute_held_atr 가 _position_atr 를 stamp 해야 한다 (전일 held 정본)"
    )


def test_check_buy_signal_stamps_position_atr():
    src = inspect.getsource(KojiroStrategy.check_buy_signal)
    assert "_position_atr[" in src, "당일 매수분도 stamp 해야 _candidates 와이프를 견딘다"


def test_on_position_closed_pops_position_atr():
    s = _kojiro()
    s._position_atr["002810"] = 863.0
    s.on_position_closed("002810")
    assert "002810" not in s._position_atr, "재진입 stale ATR 차단"


# ---------------------------------------------------------------------------
# E-7 — `_reset_daily_state` override 금지 (멀티데이 held ATR 밤샘 보존)
# ---------------------------------------------------------------------------
def test_no_reset_daily_state_override():
    assert "_reset_daily_state" not in KojiroStrategy.__dict__, (
        "kojiro 에 _reset_daily_state override 를 추가하면 멀티데이 보유 종목의 "
        "_position_atr/_position_sectors 가 20:10 정산에 소멸해 익일 손절이 무력화된다"
    )


def test_source_has_no_position_atr_clear():
    src = inspect.getsource(KojiroStrategy)
    assert "_position_atr.clear()" not in src, "일괄 clear 금지 — 포지션 수명 동안 유지"


# ---------------------------------------------------------------------------
# E-8 — 리스크 캡 계산도 동일 폴백 사용 (실제 손절선과 일치)
# ---------------------------------------------------------------------------
def test_open_risk_uses_same_atr_fallback():
    s = _kojiro()
    _hold(s)
    s._position_atr["002810"] = 863.0
    # 손절선 21,674 → 리스크 = 2주 × (23,400 − 21,674) = 3,452
    assert s._open_risk_won() == pytest.approx(3_452, abs=4)


def test_open_risk_matches_actual_stop_decision():
    """리스크 계산이 쓰는 손절선 = check_exit_signal 이 실제로 발화하는 선."""
    s = _kojiro()
    _hold(s)
    s._position_atr["002810"] = 863.0
    stop = s._position_stop_price("002810", s.state.positions["002810"])
    assert s.check_exit_signal("002810", stop, 23_400) == Signal.STOP_LOSS
    assert s.check_exit_signal("002810", stop + 1, 23_400) == Signal.NONE
