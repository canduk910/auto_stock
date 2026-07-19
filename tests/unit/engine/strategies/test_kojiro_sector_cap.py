"""kojiro 섹터/테마 동시보유 캡 회귀 가드 (Phase 2).

동일섹터 ≤ max_positions_per_sector (매수 게이트 전용·fail-open·청산 미차단).
섹터 키 = KRX 산업지수 플래그(주) + 업종 대분류(≠0000) 폴백 + 미분류(독립).
"""
from __future__ import annotations

import datetime as _dt

import pytest
from freezegun import freeze_time

from src.engine.strategies.kojiro import KojiroStrategy, _kojiro_sector_key
from src.engine.strategy_base import Position, Signal, StrategyConfig
from src.engine.recommendation_engine import PARAM_RANGES

pytestmark = pytest.mark.unit
KST = _dt.timezone(_dt.timedelta(hours=9))
WINDOW = _dt.datetime(2026, 5, 8, 9, 10, tzinfo=KST)  # 09:05~09:30 창 내


def _mk(**params):
    return KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.1, params=params))


def _seed(s, ticker, sector, *, stage=1, prev_close=10000, atr=200.0):
    s._candidates[ticker] = {
        "prev_close": prev_close, "atr": atr, "stage": stage,
        "ema_s": 9900.0, "ema_m": 9800.0, "ema_l": 9700.0,
        "atr_ratio": atr / prev_close, "sector": sector,
    }


def _hold(s, ticker, sector, *, buy_price=10000):
    s.state.positions[ticker] = Position(
        ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
        strategy_id="kojiro", buy_date=_dt.date(2026, 5, 1))
    _seed(s, ticker, sector, stage=2)  # 보유분 stage 무관, sector 만 카운트에 사용


# ── (a) 섹터 키 산출 ──

def test_sector_key_krx_flag_primary():
    assert _kojiro_sector_key({"krx_smcn_yn": "Y"}, "005930") == "반도체"
    assert _kojiro_sector_key({"krx_car_yn": "Y", "krx_bio_yn": "N"}, "005380") == "자동차"


def test_sector_key_larg_fallback_nonzero():
    assert _kojiro_sector_key({"bstp_larg_div_code": "1009"}, "X") == "업종-1009"
    assert _kojiro_sector_key({"bstp_larg_div_code": "0000", "bstp_medm_div_code": "1028"}, "Y") == "중분류-1028"


def test_sector_key_0000_and_missing_are_independent():
    assert _kojiro_sector_key({"bstp_larg_div_code": "0000", "bstp_medm_div_code": "0000"}, "AAA") == "미분류-AAA"
    assert _kojiro_sector_key(None, "BBB") == "미분류-BBB"
    assert _kojiro_sector_key({}, "CCC") == "미분류-CCC"


# ── (b~e) 캡 게이트 ──

def test_cap_blocks_third_same_sector():
    s = _mk(max_positions_per_sector=2)
    _hold(s, "P1", "반도체"); _hold(s, "P2", "반도체")
    _seed(s, "C3", "반도체")
    with freeze_time(WINDOW):
        assert s.check_buy_signal("C3", 10100, 10050) == Signal.NONE
    assert "C3" not in s._bought_today  # transient — 섹터 풀리면 재시도 가능


def test_cap_allows_different_sector():
    s = _mk(max_positions_per_sector=2)
    _hold(s, "P1", "반도체"); _hold(s, "P2", "반도체")
    _seed(s, "C3", "자동차")
    with freeze_time(WINDOW):
        assert s.check_buy_signal("C3", 10100, 10050) == Signal.BUY


def test_cap_failopen_on_independent_sector():
    # 미분류(독립 키) 후보 → 동일섹터 카운트 0 → 미차단 (fail-open)
    s = _mk(max_positions_per_sector=2)
    _hold(s, "P1", "반도체"); _hold(s, "P2", "반도체")
    _seed(s, "C3", "미분류-C3")
    with freeze_time(WINDOW):
        assert s.check_buy_signal("C3", 10100, 10050) == Signal.BUY


def test_cap_zero_disables():
    s = _mk(max_positions_per_sector=0)
    _hold(s, "P1", "반도체"); _hold(s, "P2", "반도체"); _hold(s, "P3", "반도체")
    _seed(s, "C4", "반도체")
    with freeze_time(WINDOW):
        assert s.check_buy_signal("C4", 10100, 10050) == Signal.BUY


def test_cap_counts_pending_buys():
    s = _mk(max_positions_per_sector=2)
    _hold(s, "P1", "바이오")
    s.state.pending_buys.add("P2"); _seed(s, "P2", "바이오", stage=2)  # 주문중
    _seed(s, "C3", "바이오")
    with freeze_time(WINDOW):
        assert s.check_buy_signal("C3", 10100, 10050) == Signal.NONE


def test_cap_boundary_one_same_sector_passes():
    # 동일섹터 1보유 + cap 2 → 2번째 통과
    s = _mk(max_positions_per_sector=2)
    _hold(s, "P1", "철강")
    _seed(s, "C2", "철강")
    with freeze_time(WINDOW):
        assert s.check_buy_signal("C2", 10100, 10050) == Signal.BUY


# ── (f) 청산은 섹터 무관 (매도 hot path 미접촉) ──

def test_exit_unaffected_by_sector_cap():
    s = _mk(max_positions_per_sector=2)
    _hold(s, "005930", "반도체", buy_price=10000)  # 동일섹터 초과 상황이어도
    # -8% 고정 하드손절 (섹터 무관 정상 발화)
    assert s.check_exit_signal("005930", 9100, 9100) == Signal.STOP_LOSS


def test_check_exit_source_has_no_sector_gate():
    import inspect
    src = inspect.getsource(KojiroStrategy.check_exit_signal)
    assert "max_positions_per_sector" not in src and "sector" not in src


# ── (g) PARAM_RANGES 제외 ──

def test_max_positions_per_sector_excluded_from_param_ranges():
    assert KojiroStrategy.DEFAULT_PARAMS["max_positions_per_sector"] == 2
    assert "max_positions_per_sector" not in PARAM_RANGES
