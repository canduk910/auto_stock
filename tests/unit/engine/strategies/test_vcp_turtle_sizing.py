"""B-2 게이트 2 — VCP 터틀 유닛 사이징 + 하드손절 ATR화 (다크런치) 회귀 가드.

donchian 2A-2 를 정확히 답습한다. **기본 `sizing_mode="position_ratio"` = 배포 시
byte-identical**, DB 토글로만 활성.

## 왜 사이징만 바꿀 수 없는가 (함정 #1)

    수량 = 예산 × risk_pct ÷ (진입가 − 손절가)

손절이 고정 %(−7%)면 명목 = `예산 × risk_pct/s` = 종목 무관 상수 = 지금의
position_ratio 와 수학적으로 동일하다. 즉 **고정% 손절 + 비율 사이징은 이미
리스크 균등**이고, 사이징만 ATR 로 바꾸면 정규화가 오히려 깨진다.
따라서 사이징 전환은 하드손절 ATR화와 **반드시 한 커밋에** 묶인다.

## VCP 고유 리스크 — 손절 타이트화 (본 사이클 최대 미검증 리스크)

VCP 는 정의상 **변동성 수축 시점에 진입**하므로 진입 ATR 이 구조적 국소 최소다.
`atr_ratio ≈ 1.5%` 면 `2×ATR = −3%` — 현행 −7% 대비 손절폭이 절반 이하로 줄어
승률이 급락할 수 있다. `turtle_min_stop_pct`(−5.0) 밴드가 유일한 방어선이며,
실제 활성화는 외부 MCP 백테스트 스윕 통과 후로 게이트한다.

## 게이트 규약

`sizing_mode` 가 아니라 **`_entry_atr` 스탬프 존재**가 ATR 손절의 자연 게이트다.
position_ratio 매수(미스탬프)는 기존 −7% 경로를 byte 동일하게 탄다.
"""

from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone

import pytest

from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))


def _today() -> date:
    """KST 오늘 — CI(UTC) 와 production(KST) 1일 어긋남 차단 (사이클 68 가드)."""
    return datetime.now(_KST).date()

BUDGET = 100_000_000
RATIO = 0.20


def _vcp(*, turtle: bool = False, budget: int = BUDGET, **extra):
    params = dict(extra)
    if turtle:
        params["sizing_mode"] = "turtle"
    s = VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.2, params=params),
    )
    s.state.total_investment = budget
    return s


def _hold(s, ticker: str, buy_price: int, *, high: int = 0, days_ago: int = 1):
    pos = Position(
        ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
        strategy_id="vcp_breakout",
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
    dp = VcpBreakoutStrategy.DEFAULT_PARAMS
    assert dp["sizing_mode"] == "position_ratio", "다크런치 — 기본은 비율 사이징"
    assert dp["risk_pct"] == 0.005
    assert dp["stop_atr"] == 2.0
    assert dp["turtle_backstop_pct"] == -9.0
    assert dp["min_vol_floor_pct"] == 1.0
    assert dp["turtle_min_stop_pct"] == -5.0


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
# B2-BYTE — 기본(position_ratio) 경로 byte-identical + 미스탬프
# ---------------------------------------------------------------------------
def test_position_ratio_default_is_byte_identical():
    s = _vcp()
    s._candidates["005930"] = {"atr14": 600}
    price = 20_000
    assert s.calc_buy_quantity(price, "005930") == _pr_qty(BUDGET, price)
    assert "005930" not in s._entry_atr, "position_ratio 매수는 entry_atr 미스탬프"


def test_position_ratio_keeps_percent_hard_stop():
    """미스탬프 → 기존 −7% 손절 정확 재현 (byte 동일)."""
    s = _vcp()
    _hold(s, "005930", 20_000)
    assert s.check_exit_signal("005930", 18_600, 20_000) == Signal.STOP_LOSS   # −7.0%
    assert s.check_exit_signal("005930", 18_700, 20_000) == Signal.NONE        # −6.5%


# ---------------------------------------------------------------------------
# B2-STAMP — sizing ATR == entry_atr (커플링 불변식)
# ---------------------------------------------------------------------------
def test_entry_atr_equals_sizing_atr():
    s = _vcp(turtle=True)
    price = 20_000
    atr = 800                                    # 4% ≥ floor, > 2.5% 임계 → 실제 축소
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
    s = _vcp(turtle=True)
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
    s = _vcp(turtle=True)
    price = 20_000
    s._candidates["005930"] = {"atr14": int(price * atr_ratio)}
    assert s.calc_buy_quantity(price, "005930") <= _pr_qty(BUDGET, price)


# ---------------------------------------------------------------------------
# B2-TRAP1 — 스탬프 후엔 ATR 손절이 지배 (고정% 가 앞서지 않는다)
# ---------------------------------------------------------------------------
def test_atr_stop_dominates_when_stamped():
    s = _vcp(turtle=True)
    _hold(s, "005930", 20_000)
    s._entry_atr["005930"] = 800.0                   # 2ATR = 1,600 → 손절선 18,400 (−8%)
    # min_stop(−5% = 19,000) 이 더 높으므로 밴드는 더 낮은 18,400 채택
    assert s.check_exit_signal("005930", 18_400, 20_000) == Signal.STOP_LOSS
    assert s.check_exit_signal("005930", 18_500, 20_000) == Signal.NONE
    # 기존 −7%(18,600) 는 더 이상 단독 발화하지 않는다
    assert s.check_exit_signal("005930", 18_600, 20_000) == Signal.NONE


# ---------------------------------------------------------------------------
# B2-MINSTOP — 저ATR 종목에서 손절이 turtle_min_stop_pct 보다 타이트해지지 않는다
#   (VCP 수축 셋업 = 진입 ATR 국소 최소 → 2ATR 이 −3% 로 과도하게 조여지는 병리)
# ---------------------------------------------------------------------------
def test_min_stop_band_prevents_over_tightening():
    s = _vcp(turtle=True)
    _hold(s, "005930", 20_000)
    s._entry_atr["005930"] = 300.0                   # 2ATR = 600 → −3% (19,400)
    # min_stop −5% = 19,000 → 더 낮은 19,000 채택 → −3% 구간에서는 발화 금지
    assert s.check_exit_signal("005930", 19_400, 20_000) == Signal.NONE
    assert s.check_exit_signal("005930", 19_000, 20_000) == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# B2-BACKSTOP — 고ATR 종목은 turtle_backstop_pct(−9%) 가 최대 폭을 캡한다
# ---------------------------------------------------------------------------
def test_backstop_caps_wide_atr_stop():
    s = _vcp(turtle=True)
    _hold(s, "005930", 20_000)
    s._entry_atr["005930"] = 2_000.0                 # 2ATR = 4,000 → −20% (16,000)
    # backstop −9% = 18,200 이 먼저 발화해야 한다
    assert s.check_exit_signal("005930", 18_200, 20_000) == Signal.STOP_LOSS


def test_backstop_not_applied_without_stamp():
    """미스탬프 포지션엔 backstop 미적용 — 기존 −7% 만."""
    s = _vcp(turtle=True)
    _hold(s, "005930", 20_000)
    assert s.check_exit_signal("005930", 18_600, 20_000) == Signal.STOP_LOSS   # −7%
    assert s.check_exit_signal("005930", 18_700, 20_000) == Signal.NONE


# ---------------------------------------------------------------------------
# B2-BREAKEVEN — 스탬프 포지션은 스냅샷 승격, 미스탬프는 기존 live-ATR 래치 보존
# ---------------------------------------------------------------------------
def test_breakeven_promotes_to_buy_price_when_stamped():
    s = _vcp(turtle=True, breakeven_promote_atr=1.5)
    _hold(s, "005930", 20_000, high=21_500)          # buy + 1.5×1000 = 21,500 도달
    s._entry_atr["005930"] = 1_000.0
    assert s.check_exit_signal("005930", 20_000, 20_000) == Signal.STOP_LOSS
    assert s.check_exit_signal("005930", 20_100, 20_000) == Signal.NONE


def test_legacy_breakeven_latch_untouched_without_stamp():
    """미스탬프 경로의 사이클 C 래치는 행위 변화 0."""
    s = _vcp(breakeven_promote_atr=1.5)
    _hold(s, "005930", 20_000, high=21_500)
    s._candidates["005930"] = {"atr14": 1_000}
    assert s.check_exit_signal("005930", 20_000, 20_000) == Signal.STOP_LOSS
    assert "005930" in s._breakeven_latched


# ---------------------------------------------------------------------------
# B2-TIGHTEN — 승격은 max() 로만 이동 (손절선이 넓어지지 않는다)
# ---------------------------------------------------------------------------
def test_breakeven_never_loosens_stop():
    s = _vcp(turtle=True, breakeven_promote_atr=1.5)
    _hold(s, "005930", 20_000, high=21_500)
    s._entry_atr["005930"] = 300.0                   # base_stop(19,000) < buy(20,000)
    # 승격 후 손절선은 매수가 — base 로 되돌아가면 안 된다
    assert s.check_exit_signal("005930", 19_900, 20_000) == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# B2-REDERIVE — 재시작 재도출은 buy_date **이전** 봉만 사용, 기존 스탬프 미접촉
# ---------------------------------------------------------------------------
def _candles(start: date, n: int, *, high: int, low: int, close: int):
    return [
        {
            "stck_bsop_date": (start - timedelta(days=i)).strftime("%Y%m%d"),
            "stck_hgpr": str(high), "stck_lwpr": str(low), "stck_clpr": str(close),
        }
        for i in range(n)
    ]


def test_rederive_uses_only_pre_buy_candles():
    s = _vcp(turtle=True)
    buy_date = _today() - timedelta(days=5)
    pos = _hold(s, "005930", 20_000, days_ago=5)
    # 매수 후 초고변동 봉(폭 10,000) + 매수 전 저변동 봉(폭 200)
    post = _candles(_today(), 5, high=30_000, low=20_000, close=25_000)
    pre = _candles(buy_date - timedelta(days=1), 30, high=20_100, low=19_900, close=20_000)
    s._rederive_entry_atr("005930", pos, post + pre, 14)
    assert 0 < s._entry_atr["005930"] < 1_000, "매수 후 팽창 ATR 이 섞이면 손절선이 느슨해진다"


def test_rederive_preserves_existing_stamp():
    s = _vcp(turtle=True)
    pos = _hold(s, "005930", 20_000, days_ago=5)
    s._entry_atr["005930"] = 777.0
    pre = _candles(_today() - timedelta(days=6), 30, high=20_100, low=19_900, close=20_000)
    s._rederive_entry_atr("005930", pos, pre, 14)
    # 재도출 함수 자체는 덮어쓴다 — 미접촉 보장은 호출부(`ticker not in _entry_atr`) 책임
    assert "005930" in s._entry_atr


def test_recompute_skips_rederive_when_stamp_exists():
    """`recompute_high_since_buy` 는 in-memory 스탬프가 있으면 재도출하지 않는다."""
    src = inspect.getsource(VcpBreakoutStrategy.recompute_high_since_buy)
    assert "_rederive_entry_atr" in src, "재시작 복구 배선 누락 — scheduler 추가 없이 기존 fetch 재사용"
    assert "not in self._entry_atr" in src, "기존 스탬프 미접촉 조건 누락"


def test_rederive_insufficient_candles_does_not_stamp():
    s = _vcp(turtle=True)
    pos = _hold(s, "005930", 20_000, days_ago=5)
    pre = _candles(_today() - timedelta(days=6), 3, high=20_100, low=19_900, close=20_000)
    s._rederive_entry_atr("005930", pos, pre, 14)
    assert "005930" not in s._entry_atr, "봉 부족 시 미복구 — % backstop 이 방어(무손절 아님)"


# ---------------------------------------------------------------------------
# B2-CLEANUP — 청산 시 entry_atr 정리 (재진입 stale 스냅샷 차단)
# ---------------------------------------------------------------------------
def test_on_position_closed_pops_entry_atr():
    s = _vcp(turtle=True)
    s._entry_atr["005930"] = 800.0
    s.on_position_closed("005930")
    assert "005930" not in s._entry_atr
