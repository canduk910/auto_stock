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


# ── cycle405 — 깡토식 사이징·청산으로 대체 (명세 `_workspace/red/cycle405_donchian_kkangto_spec.md` §2·§5) ──
# 설계 랏 q = floor(B × risk_pct ÷ R) → min(q, int(B × position_ratio) // P), R = max(8%·P, 1.5·N).
# `sizing_mode` 는 사이징이 보지 않는다(재도출 게이트만 본다). 1주 폴백·비중 낙하·변동성 floor 낙하 없음.
# 손절 = E − R(스탬프 없으면 R = 8%·E). 2ATR·−9% 받침선·미스탬프 −7% 는 없어졌다.
# 옛 `test_turtle_backstop_fires_when_atr_stop_naked` 는 지웠다(−9% 받침선 폐지 — §2 「끄는 것」).

def test_turtle_sizing_used_and_stamps_entry_atr():
    s = _mk(sizing_mode="turtle")
    s._candidates["005930"] = {"prev_close": 60000, "atr": 3000, "ema60": 0, "donchian_high": 0}
    # R = max(4,800, 4,500) = 4,800 → floor(1,200,000 / 4,800) = 250 · 명목 15M//60,000 = 250
    qty = s.calc_buy_quantity(60000, "005930")
    assert qty == 250
    assert s._entry_atr["005930"] == 3000.0


def test_sizing_mode_position_ratio_is_not_read_by_sizing():
    s = _mk()  # sizing_mode=position_ratio
    s._candidates["005930"] = {"prev_close": 60000, "atr": 3000, "ema60": 0, "donchian_high": 0}
    assert s.calc_buy_quantity(60000, "005930") == 250
    assert s._entry_atr["005930"] == 3000.0         # 모든 랏이 스탬프된다


def test_low_vol_has_no_ratio_fallthrough_and_is_stamped():
    # atr/price = 0.5% — 옛 변동성 floor 낙하 대신 R 하한(8%)이 수량을 정한다
    s = _mk(sizing_mode="turtle")
    s._candidates["005930"] = {"prev_close": 100000, "atr": 500, "ema60": 0, "donchian_high": 0}
    assert s.calc_buy_quantity(100000, "005930") == 150   # floor(1.2M / 8,000) = 150
    assert s._entry_atr["005930"] == 500.0


def test_no_ticker_buys_nothing():
    s = _mk(sizing_mode="turtle")
    assert s.calc_buy_quantity(60000, None) == 0


def test_invariant_entry_atr_equals_sizing_atr_and_r_risk_bounded():
    s = _mk(sizing_mode="turtle")
    for tk, price, atr in [("A", 60000, 3000), ("B", 30000, 900), ("C", 200000, 6000)]:
        s._candidates[tk] = {"prev_close": price, "atr": atr, "ema60": 0, "donchian_high": 0}
        qty = s.calc_buy_quantity(price, tk)
        assert qty > 0
        assert s._entry_atr[tk] == float(atr)
        r = max(0.08 * price, 1.5 * atr)
        assert qty * r <= 100_000_000 * 0.012 + 1e-6, "1R 손실 ≤ 예산 × risk_pct"


def _pos(buy_price=60000, buy_date=None):
    return Position(ticker="005930", buy_price=buy_price, quantity=10, order_no="O",
                    strategy_id="donchian_swing", buy_date=buy_date or _dt.date(2026, 7, 1))


def test_stamped_stop_is_entry_minus_r():
    s = _mk(sizing_mode="turtle")
    s.state.positions["005930"] = _pos()
    s._entry_atr["005930"] = 3000.0            # R = max(4,800, 4,500) = 4,800 → 55,200
    s._candidates["005930"] = {"atr": 3000}
    assert s.check_exit_signal("005930", 55200, 60000) == Signal.STOP_LOSS
    assert s.check_exit_signal("005930", 55201, 60000) == Signal.NONE


def test_unstamped_stop_is_8pct():
    s = _mk()
    s.state.positions["005930"] = _pos()
    s._candidates["005930"] = {"atr": 3000}
    assert s.check_exit_signal("005930", 55200, 60000) == Signal.STOP_LOSS   # −8%
    assert s.check_exit_signal("005930", 55800, 60000) == Signal.NONE        # 옛 −7% 자리


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
