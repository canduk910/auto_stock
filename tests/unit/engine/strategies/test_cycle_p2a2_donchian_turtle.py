"""Phase 2A-2 (게이트 1) — donchian 터틀 유닛 sizing + 하드손절 ATR화 회귀 가드.

확정 설계 (domain-consult + 적대검증):
- stop_atr 2.0(=atr_trail_mult, dead code 방지) / % → backstop(-9%, 삭제 아님) 강등
- ATR손절은 sizing_mode 게이팅 금지 → entry_atr 존재가 자연 게이트
  (position_ratio 매수 미스탬프 → % -7% 손절 byte 동일)
- entry_atr = calc_buy_quantity 원자 스탬프(sizing 과 동일 값) + recompute buy_date 재도출(재시작 loosen 차단)
- 저ATR qty 폭증 = compute_unit_qty_guarded 변동성 floor + notional 클램프
"""

from __future__ import annotations

import datetime as _dt
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig
from src.engine.recommendation_engine import PARAM_RANGES

pytestmark = pytest.mark.unit
KST = _dt.timezone(_dt.timedelta(hours=9))


def _mk(sizing_mode="position_ratio", **params):
    cfg = StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.2,
                         params={"sizing_mode": sizing_mode, **params})
    s = DonchianSwingStrategy(cfg)
    s.state.total_investment = 100_000_000
    return s


# ── sizing: 터틀 분기 + entry_atr 원자 스탬프 ──

def test_turtle_sizing_used_and_stamps_entry_atr():
    s = _mk(sizing_mode="turtle")
    s._candidates["005930"] = {"prev_close": 60000, "atr": 3000, "ema60": 0, "donchian_high": 0}
    # compute_unit_qty(100M,3000,0.5%)=166, notional cap=20M//60000=333>166 → 166
    qty = s.calc_buy_quantity(60000, "005930")
    assert qty == 166
    # sizing 과 동일 ATR 값으로 하드손절 entry_atr 스탬프 (원자 결합)
    assert s._entry_atr["005930"] == 3000.0


def test_position_ratio_default_is_byte_identical_no_stamp():
    s = _mk()  # sizing_mode=position_ratio (기본)
    s._candidates["005930"] = {"prev_close": 60000, "atr": 3000, "ema60": 0, "donchian_high": 0}
    qty = s.calc_buy_quantity(60000, "005930")
    assert qty == int(100_000_000 * 0.20) // 60000  # 333 (기존 계산 불변)
    assert "005930" not in s._entry_atr           # 미스탬프 → % 손절 경로


def test_turtle_vol_floor_falls_back_no_stamp():
    # atr/price = 0.5% < min_vol_floor_pct(1%) → 터틀 0 → position_ratio 낙하 + 미스탬프
    s = _mk(sizing_mode="turtle")
    s._candidates["005930"] = {"prev_close": 100000, "atr": 500, "ema60": 0, "donchian_high": 0}
    qty = s.calc_buy_quantity(100000, "005930")
    assert qty == int(100_000_000 * 0.20) // 100000  # 200 (position_ratio)
    assert "005930" not in s._entry_atr             # 미스탬프 = 함정#1 차단


def test_turtle_no_ticker_falls_back():
    # ticker=None (호출부 미지원 경로) → 터틀 미적용
    s = _mk(sizing_mode="turtle")
    assert s.calc_buy_quantity(60000, None) == int(100_000_000 * 0.20) // 60000


# ── 불변식: 유닛당 리스크 = 예산×risk_pct×stop_atr (변동성 무관) ──

def test_invariant_entry_atr_equals_sizing_atr():
    s = _mk(sizing_mode="turtle")
    for tk, price, atr in [("A", 60000, 3000), ("B", 30000, 900), ("C", 200000, 6000)]:
        s._candidates[tk] = {"prev_close": price, "atr": atr, "ema60": 0, "donchian_high": 0}
        qty = s.calc_buy_quantity(price, tk)
        if qty > 0:
            # entry_atr(하드손절) == sizing ATR → qty×stop_atr×entry_atr ≈ 예산×2×risk_pct 상수
            assert s._entry_atr[tk] == float(atr)
            unit_risk = qty * 2.0 * s._entry_atr[tk]
            assert unit_risk <= 100_000_000 * 2.0 * 0.005 * 1.05  # floor 오차 + notional cap 하방만


# ── check_exit: entry_atr 게이트 (ATR손절 / backstop / % byte 동일) ──

def _pos(buy_price=60000, buy_date=None):
    return Position(ticker="005930", buy_price=buy_price, quantity=10, order_no="O",
                    strategy_id="donchian_swing", buy_date=buy_date or _dt.date(2026, 7, 1))


def test_turtle_atr_hard_stop_fires():
    s = _mk(sizing_mode="turtle")
    s.state.positions["005930"] = _pos()
    s._entry_atr["005930"] = 3000.0            # base = 60000 - 2×3000 = 54000
    s._candidates["005930"] = {"atr": 3000}
    assert s.check_exit_signal("005930", 53900, 60000) == Signal.STOP_LOSS   # ≤ 54000
    assert s.check_exit_signal("005930", 55000, 60000) == Signal.NONE        # > 54000, 트레일 없음


def test_turtle_backstop_fires_when_atr_stop_naked():
    # entry_atr 과대 → base_stop ≤ 0 (naked) → % backstop(-9%)가 최후 방어
    s = _mk(sizing_mode="turtle")
    s.state.positions["005930"] = _pos()
    s._entry_atr["005930"] = 40000.0           # base = 60000-80000 <0 → ATR손절 skip
    s._candidates["005930"] = {"atr": 40000}
    assert s.check_exit_signal("005930", 54000, 60000) == Signal.STOP_LOSS   # -10% ≤ -9%
    assert s.check_exit_signal("005930", 55500, 60000) == Signal.NONE        # -7.5% > -9%


def test_position_ratio_percent_stop_byte_identical():
    # entry_atr 미스탬프 → 기존 -7% 손절 (byte 동일). -9% backstop 미적용.
    s = _mk()
    s.state.positions["005930"] = _pos()
    s._candidates["005930"] = {"atr": 3000}
    assert s.check_exit_signal("005930", 55800, 60000) == Signal.STOP_LOSS   # -7% 정확
    assert s.check_exit_signal("005930", 56000, 60000) == Signal.NONE        # -6.7% > -7%


# ── 재시작 복구: recompute 가 buy_date 이전 봉으로 entry_atr 재도출 (loosen 차단) ──

def _candles_desc(dates_ohlc):
    """dates_ohlc = [(yyyymmdd, high, low, close), ...] DESC (idx0=최신)."""
    return [{"stck_bsop_date": d, "stck_hgpr": str(h), "stck_lwpr": str(lo), "stck_clpr": str(c)}
            for d, h, lo, c in dates_ohlc]


async def test_recompute_rederives_entry_atr_not_inflated():
    s = _mk(sizing_mode="turtle")
    buy_date = _dt.date(2026, 7, 1)
    s.state.positions["005930"] = _pos(buy_price=60000, buy_date=buy_date)
    s._candidates["005930"] = {"atr": 3000}  # need_atr=False 로 만들어 pos_needs_high_recover 로 진입
    # 매수 후(>=0701) 봉 = 초고변동(range 20000), 매수 전(<0701) 봉 = 저변동(range 300)
    post = [(f"202607{d:02d}", 80000, 60000, 70000) for d in (14, 11, 10, 9, 8, 7, 4, 3, 2, 1)]
    pre = [(f"202606{d:02d}", 60300, 60000, 60100) for d in range(30, 10, -1)]  # 20봉, range=300
    candles = _candles_desc(post + pre)
    with patch("src.api.condition.fetch_daily_candles", new=AsyncMock(return_value=candles)), \
         patch("src.engine.strategies.donchian_swing.datetime") as _dtmock:
        _dtmock.now.return_value = _dt.datetime(2026, 7, 15, 8, 0, tzinfo=KST)
        # high_since_buy 보정 헬퍼는 무해 스텁
        s._apply_high_since_buy_from_candles = AsyncMock()
        await s.recompute_held_atr()
    # entry_atr 은 매수 전 저변동(≈300) 기반 → 매수 후 팽창(20000) 반영 안 됨 (loosen 차단)
    assert "005930" in s._entry_atr
    assert s._entry_atr["005930"] < 1000   # 저변동 pre-buy ATR (팽창 20000 아님)


async def test_recompute_preserves_existing_entry_atr_stamp():
    # in-memory entry_atr 존재(당일 매수 미재시작) → recompute 미접촉 (정확 스탬프 보존)
    s = _mk(sizing_mode="turtle")
    s.state.positions["005930"] = _pos(buy_date=_dt.date(2026, 7, 1))
    s._candidates["005930"] = {"atr": 3000}
    s._entry_atr["005930"] = 2777.0   # 이미 스탬프됨
    candles = _candles_desc([(f"202606{d:02d}", 61000, 60000, 60500) for d in range(30, 5, -1)])
    with patch("src.api.condition.fetch_daily_candles", new=AsyncMock(return_value=candles)), \
         patch("src.engine.strategies.donchian_swing.datetime") as _dtmock:
        _dtmock.now.return_value = _dt.datetime(2026, 7, 15, 8, 0, tzinfo=KST)
        s._apply_high_since_buy_from_candles = AsyncMock()
        await s.recompute_held_atr()
    assert s._entry_atr["005930"] == 2777.0   # 불변 (재도출 skip)


# ── on_position_closed: entry_atr pop ──

def test_on_position_closed_pops_entry_atr():
    s = _mk(sizing_mode="turtle")
    s._entry_atr["005930"] = 3000.0
    s.on_position_closed("005930")
    assert "005930" not in s._entry_atr
    s.on_position_closed("999999")  # 미존재 graceful


# ── PARAM_RANGES 제외 (정체성 상수, AI 자동튜닝 차단) ──

def test_turtle_identity_keys_excluded_from_param_ranges():
    for key in ("sizing_mode", "risk_pct", "stop_atr", "turtle_backstop_pct", "min_vol_floor_pct"):
        assert key not in PARAM_RANGES, f"{key} 는 PARAM_RANGES 편입 금지 (정체성 상수)"
