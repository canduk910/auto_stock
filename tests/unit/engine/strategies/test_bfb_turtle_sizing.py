"""B-2 게이트 2 미러 — BFB(bull_flag_breakout) 터틀 유닛 사이징 + 하드손절 ATR화 회귀 가드.

`test_vcp_turtle_sizing.py` 를 BFB 로 정확히 미러링한다. **기본
`sizing_mode="position_ratio"` = 배포 시 byte-identical**, DB 토글로만 활성.

## 왜 사이징만 바꿀 수 없는가 (VCP 함정 #1 답습)

    수량 = 예산 × risk_pct ÷ (진입가 − 손절가)

손절이 고정 %(−5%)면 명목 = `예산 × risk_pct/s` = 종목 무관 상수 = 지금의
position_ratio 와 수학적으로 동일하다. 사이징만 ATR 로 바꾸면 정규화가 오히려
깨지므로 하드손절 ATR화와 **반드시 한 커밋에** 묶는다.

## BFB 값이 VCP 와 다른 이유

BFB 기존 하드손절은 −5%(VCP −7%보다 이미 타이트) — 그래서 `turtle_backstop_pct`
(−7.0, VCP −9.0)와 `turtle_min_stop_pct`(−4.0, VCP −5.0) 모두 2%p 씩 강등된 값을
쓴다.

## 게이트 규약

`sizing_mode` 가 아니라 **`_entry_atr` 스탬프 존재**가 ATR 손절의 자연 게이트다.
position_ratio 매수(미스탬프)는 기존 −5% 경로를 byte 동일하게 탄다.

## BFB 는 익일 청산 전략 — 재시작 복구 인프라 불필요

VCP/donchian 은 `Position._MULTIDAY_STRATEGIES` 멤버(멀티데이 보유)라 재시작 시
`_entry_atr` 소실을 막기 위해 `_rederive_entry_atr` + `recompute_high_since_buy`
scheduler 배선이 필요했다. BFB 는 비멤버(매일 청산)라 이 인프라 자체가 불필요 —
장중 재시작으로 `_entry_atr` 가 소실돼도 `turtle_backstop_pct` 가 방어한다.
"""

from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone

import pytest

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))


def _today() -> date:
    """KST 오늘 — CI(UTC) 와 production(KST) 1일 어긋남 차단 (사이클 68 가드)."""
    return datetime.now(_KST).date()


BUDGET = 100_000_000
RATIO = 0.25


def _bfb(*, turtle: bool = False, budget: int = BUDGET, **extra):
    params = dict(extra)
    if turtle:
        params["sizing_mode"] = "turtle"
    s = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="BFB", weight=0.2, params=params),
    )
    s.state.total_investment = budget
    return s


def _hold(s, ticker: str, buy_price: int, *, high: int = 0, days_ago: int = 1):
    pos = Position(
        ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
        strategy_id="bull_flag_breakout",
        buy_date=_today() - timedelta(days=days_ago),
    )
    pos.high_since_buy = high or buy_price
    s.state.positions[ticker] = pos
    return pos


def _pr_qty(budget: int, price: int, ratio: float = RATIO) -> int:
    return int(budget * ratio) // price


# ---------------------------------------------------------------------------
# B2-DEFAULT — 신규 6키 기본값 + 다크런치(기본 position_ratio)
# ---------------------------------------------------------------------------
def test_turtle_default_params_present_and_dark():
    dp = BullFlagBreakoutStrategy.DEFAULT_PARAMS
    assert dp["sizing_mode"] == "position_ratio", "다크런치 — 기본은 비율 사이징"
    assert dp["risk_pct"] == 0.005
    assert dp["stop_atr"] == 2.0
    assert dp["turtle_backstop_pct"] == -7.0
    assert dp["min_vol_floor_pct"] == 1.0
    assert dp["turtle_min_stop_pct"] == -4.0


def test_turtle_keys_excluded_from_param_ranges():
    """사이징·청산 정체성 상수는 AI 자동튜닝 대상이 아니다."""
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    for key in (
        "sizing_mode", "risk_pct", "stop_atr",
        "turtle_backstop_pct", "min_vol_floor_pct", "turtle_min_stop_pct",
    ):
        assert key not in PARAM_RANGES, f"{key} 는 PARAM_RANGES 편입 금지"
        assert key not in INT_PARAMS, f"{key} 는 INT_PARAMS 편입 금지"


# ---------------------------------------------------------------------------
# B2-BYTE — 기본(position_ratio) 경로 byte-identical + 미스탬프 + 기존 −5% 재현
# ---------------------------------------------------------------------------
def test_position_ratio_default_is_byte_identical():
    s = _bfb()
    s._candidates["005930"] = {"atr14": 600}
    price = 20_000
    assert s.calc_buy_quantity(price, "005930") == _pr_qty(BUDGET, price)
    assert "005930" not in s._entry_atr, "position_ratio 매수는 entry_atr 미스탬프"


def test_position_ratio_keeps_percent_hard_stop():
    """미스탬프 → 기존 −5% 손절 정확 재현 (byte 동일)."""
    s = _bfb()
    _hold(s, "005930", 20_000)
    assert s.check_exit_signal("005930", 19_000, 20_000) == Signal.STOP_LOSS   # −5.0%
    assert s.check_exit_signal("005930", 19_001, 20_000) == Signal.NONE       # −4.995%


# ---------------------------------------------------------------------------
# B2-STAMP — sizing ATR == entry_atr (커플링 불변식)
# ---------------------------------------------------------------------------
def test_entry_atr_equals_sizing_atr():
    s = _bfb(turtle=True)
    price = 20_000
    atr = 800                                    # 4% ≥ floor → 실제 축소
    s._candidates["005930"] = {"atr14": atr}
    qty = s.calc_buy_quantity(price, "005930")
    assert qty > 0
    assert s._entry_atr["005930"] == float(atr)
    # 유닛 리스크 상수: qty × stop_atr × entry_atr ≈ 예산 × risk_pct × stop_atr
    assert qty * 2.0 * atr <= BUDGET * 0.005 * 2.0 * 1.05


# ---------------------------------------------------------------------------
# B2-NOSTAMP — 터틀 0 낙하 경로는 미스탬프 (함정 #1 차단)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("setup", ["vol_floor", "no_candidate", "atr_zero", "ticker_none"])
def test_turtle_zero_paths_do_not_stamp(setup):
    s = _bfb(turtle=True)
    price = 20_000
    if setup == "vol_floor":
        s._candidates["005930"] = {"atr14": 100}      # 0.5% < 1%
    elif setup == "atr_zero":
        s._candidates["005930"] = {"atr14": 0}
    elif setup == "ticker_none":
        s._candidates["005930"] = {"atr14": 800}
        assert s.calc_buy_quantity(price, None) == _pr_qty(BUDGET, price)
        assert not s._entry_atr
        return
    assert s.calc_buy_quantity(price, "005930") == _pr_qty(BUDGET, price)
    assert "005930" not in s._entry_atr


# ---------------------------------------------------------------------------
# B2-NARROW — 터틀 수량 ≤ position_ratio 수량 (순수 축소)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("atr_ratio", [0.011, 0.02, 0.025, 0.04, 0.08])
def test_turtle_never_increases_qty(atr_ratio):
    s = _bfb(turtle=True)
    price = 20_000
    s._candidates["005930"] = {"atr14": int(price * atr_ratio)}
    assert s.calc_buy_quantity(price, "005930") <= _pr_qty(BUDGET, price)


# ---------------------------------------------------------------------------
# B2-TRAP1 — 스탬프 후엔 ATR 손절이 지배 (고정% 가 앞서지 않는다)
# ---------------------------------------------------------------------------
def test_atr_stop_dominates_when_stamped():
    s = _bfb(turtle=True)
    _hold(s, "005930", 20_000)
    s._entry_atr["005930"] = 600.0                   # 2ATR = 1,200 → 손절선 18,800 (−6%)
    # min_stop(−4% = 19,200) 보다 base_stop(−6%) 이 더 낮으므로 ATR 이 지배
    assert s.check_exit_signal("005930", 18_800, 20_000) == Signal.STOP_LOSS
    assert s.check_exit_signal("005930", 18_801, 20_000) == Signal.NONE
    # 기존 −5%(19,000) 는 더 이상 단독 발화하지 않는다
    assert s.check_exit_signal("005930", 19_000, 20_000) == Signal.NONE


# ---------------------------------------------------------------------------
# B2-MINSTOP — 저ATR 종목에서 손절이 turtle_min_stop_pct 보다 타이트해지지 않는다
# ---------------------------------------------------------------------------
def test_min_stop_band_prevents_over_tightening():
    s = _bfb(turtle=True)
    _hold(s, "005930", 20_000)
    s._entry_atr["005930"] = 150.0                   # 2ATR = 300 → −1.5% (19,700)
    # min_stop −4% = 19,200 → 더 낮은 19,200 채택 → −1.5% 구간에서는 발화 금지
    assert s.check_exit_signal("005930", 19_700, 20_000) == Signal.NONE
    assert s.check_exit_signal("005930", 19_200, 20_000) == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# B2-BACKSTOP — 고ATR 종목은 turtle_backstop_pct(−7%) 가 최대 폭을 캡한다
# ---------------------------------------------------------------------------
def test_backstop_caps_wide_atr_stop():
    s = _bfb(turtle=True)
    _hold(s, "005930", 20_000)
    s._entry_atr["005930"] = 2_000.0                 # 2ATR = 4,000 → −20% (16,000)
    # backstop −7% = 18,600 이 먼저 발화해야 한다
    assert s.check_exit_signal("005930", 18_600, 20_000) == Signal.STOP_LOSS


def test_backstop_not_applied_without_stamp():
    """미스탬프 포지션엔 backstop 미적용 — 기존 −5% 만."""
    s = _bfb(turtle=True)
    _hold(s, "005930", 20_000)
    assert s.check_exit_signal("005930", 19_000, 20_000) == Signal.STOP_LOSS   # −5%
    assert s.check_exit_signal("005930", 19_001, 20_000) == Signal.NONE


# ---------------------------------------------------------------------------
# B2-BREAKEVEN — 스탬프 포지션은 스냅샷 승격, 미스탬프는 기존 live-ATR 래치 보존
# ---------------------------------------------------------------------------
def test_breakeven_promotes_to_buy_price_when_stamped():
    s = _bfb(turtle=True, breakeven_promote_atr=1.5)
    _hold(s, "005930", 20_000, high=21_500)          # buy + 1.5×1000 = 21,500 도달
    s._entry_atr["005930"] = 1_000.0
    assert s.check_exit_signal("005930", 20_000, 20_000) == Signal.STOP_LOSS
    assert s.check_exit_signal("005930", 20_100, 20_000) == Signal.NONE


def test_legacy_breakeven_latch_untouched_without_stamp():
    """미스탬프 경로의 사이클 C 래치는 행위 변화 0."""
    s = _bfb(breakeven_promote_atr=1.5)
    _hold(s, "005930", 20_000, high=21_500)
    s._candidates["005930"] = {"atr14": 1_000}
    assert s.check_exit_signal("005930", 20_000, 20_000) == Signal.STOP_LOSS
    assert "005930" in s._breakeven_latched


# ---------------------------------------------------------------------------
# B2-TIGHTEN — 승격은 max() 로만 이동 (손절선이 넓어지지 않는다)
# ---------------------------------------------------------------------------
def test_breakeven_never_loosens_stop():
    s = _bfb(turtle=True, breakeven_promote_atr=1.5)
    _hold(s, "005930", 20_000, high=21_500)
    s._entry_atr["005930"] = 150.0                   # base_stop(19,200) < buy(20,000)
    # 승격 후 손절선은 매수가 — base 로 되돌아가면 안 된다
    assert s.check_exit_signal("005930", 19_900, 20_000) == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# B2-CLEANUP — 청산 시 entry_atr 정리 (재진입 stale 스냅샷 차단)
# ---------------------------------------------------------------------------
def test_on_position_closed_pops_entry_atr():
    s = _bfb(turtle=True)
    s._entry_atr["005930"] = 800.0
    s.on_position_closed("005930")
    assert "005930" not in s._entry_atr


# ---------------------------------------------------------------------------
# B2-NOMULTIDAY — BFB 는 익일 청산 전략 → 재시작 복구 인프라 불필요 (팀장 지시 명문화)
# ---------------------------------------------------------------------------
def test_bfb_not_multiday_and_no_rederive_infra():
    """BFB 는 `Position._MULTIDAY_STRATEGIES` 비멤버(매일 청산) — VCP/donchian 과 달리
    `_rederive_entry_atr`/`recompute_high_since_buy` 재시작 복구 배선이 불필요하다.
    """
    assert "bull_flag_breakout" not in Position._MULTIDAY_STRATEGIES
    assert not hasattr(BullFlagBreakoutStrategy, "_rederive_entry_atr")
    assert not hasattr(BullFlagBreakoutStrategy, "recompute_high_since_buy")


def test_scheduler_has_no_bfb_entry_atr_wiring():
    """scheduler.py 는 매매 안전성 8영역 — VCP 전용 `_entry_atr` 재도출 배선(recompute_
    high_since_buy 단일 ticker 조회)만 존재, BFB 관련 참조 0건이어야 한다.
    """
    from src.engine import scheduler as scheduler_mod

    src = inspect.getsource(scheduler_mod)
    assert "bull_flag_breakout" in src, "기존 재prepare 안전망 참조는 영속되어야 함"
    # VCP 전용 recompute_high_since_buy 호출부 주변에 BFB 관련 토큰이 섞이지 않았는지 확인
    idx = src.find("recompute_high_since_buy")
    assert idx != -1
    window = src[max(0, idx - 400): idx + 400]
    assert "bull_flag_breakout" not in window
    assert "_entry_atr" not in window
