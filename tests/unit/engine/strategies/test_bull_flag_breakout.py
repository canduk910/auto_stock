"""src/engine/strategies/bull_flag_breakout.py 단위 테스트.

눌림목 돌파(bull flag) 전략 — 폴/플래그 → 플래그 상단 재돌파.

검증 포인트:
- DEFAULT_PARAMS — 명세 (`_workspace/00_leader_trading_rules.md` 6-E) 와 일치
- check_buy_signal:
    * 진입 시간대 가드 (09:05 ~ 13:00 KRX 메인)
    * 플래그 상단 돌파 순간(prev<flag_high AND now>=flag_high)
    * 거래량 컷 (≥ flag_avg_volume × breakout_volume_mult)
    * 보유/주문중/당일매도 가드, _bought_today 1회 가드
    * buy_disabled / max_positions / daily_loss_exceeded 가드
    * 쿨다운 (재진입 3영업일) 가드
- check_exit_signal:
    * 하드 손절 -5%
    * 플래그 하단(flag_low) 이탈 → STOP_LOSS
    * 측정된 이동(measured move) 타겟가 도달 → 청산 신호
    * 잔여 ATR×2 트레일링 (partial_exit 마킹 후)
    * 시간 청산 5영업일 초과 → FORCE_CLEAR/TRAILING_STOP
- check_force_clear: 진입 시간대 외 강제 청산 없음(빈 리스트) — 기본
- calc_buy_quantity: position_ratio 25% + _fallback_one_share 1주 폴백
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def strat():
    s = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목 돌파", weight=0.0)
    )
    # 사이클 23 P2-1: 기존 테스트 회귀 — retention=0이면 즉시 진입 (기존 동작 보존)
    s.config.params["breakout_retention_minutes"] = 0
    return s


def _seed_candidate(
    s,
    ticker,
    *,
    pole_start=10_000,
    pole_high=12_500,
    flag_high=12_300,
    flag_low=11_800,
    flag_avg_volume=200_000,
    atr14=300,
    prev_close=12_100,
):
    s._candidates[ticker] = {
        "pole_start": pole_start,
        "pole_high": pole_high,
        "flag_high": flag_high,
        "flag_low": flag_low,
        "flag_avg_volume": flag_avg_volume,
        "atr14": atr14,
        "prev_close": prev_close,
    }


# ---------------------------------------------------------------------------
# DEFAULT_PARAMS 검증
# ---------------------------------------------------------------------------
def test_default_params_thresholds():
    p = BullFlagBreakoutStrategy.DEFAULT_PARAMS
    assert p["tradable_boards"] == ["main"]
    assert p["exchange"] == "KRX"
    # 사이클 48 (2026-05-27) — Pole 검출 0건 결함 완화 (20.0→15.0 / 0.30→0.45)
    assert p["pole_min_return"] == 15.0
    assert p["pole_max_red_ratio"] == 0.45
    assert p["flag_retracement_max"] == 0.382
    assert p["flag_volume_ratio"] == 0.60
    assert p["breakout_volume_mult"] == 2.0
    assert p["entry_start"] == "09:05"
    assert p["entry_end"] == "13:00"
    assert p["position_ratio"] == 0.25
    assert p["max_positions"] == 4
    assert p["stop_loss_rate"] == -5.0
    assert p["atr_trail_mult"] == 2.0
    assert p["max_hold_days"] == 5
    assert p["reentry_cooldown_days"] == 3


def test_default_tradable_boards_constant():
    assert BullFlagBreakoutStrategy.DEFAULT_TRADABLE_BOARDS == ("main",)


# ---------------------------------------------------------------------------
# check_buy_signal — 시간 가드
# ---------------------------------------------------------------------------
def test_buy_when_before_0905_then_none(strat):
    _seed_candidate(strat, "005930")
    with freeze_time("2026-05-08 09:04:00"):
        assert strat.check_buy_signal("005930", 12_400, 12_100) == Signal.NONE


def test_buy_when_after_1300_then_none(strat):
    _seed_candidate(strat, "005930")
    with freeze_time("2026-05-08 13:01:00"):
        assert strat.check_buy_signal("005930", 12_400, 12_100) == Signal.NONE


# ---------------------------------------------------------------------------
# check_buy_signal — 돌파 순간 + 거래량 컷
# ---------------------------------------------------------------------------
def test_buy_when_breakout_with_volume_then_buy(strat):
    _seed_candidate(strat, "005930", flag_high=12_300, flag_avg_volume=200_000)
    # 거래량 컷 통과를 위해 scanner.ticker_prices 에 누적 거래량 mock 시도
    # — 구현체가 어떤 키를 사용하든 (acml_vol 또는 분당 누적), 충분히 큰 값 주입
    from src.engine import scanner as _scanner
    _scanner.ticker_prices["005930"] = {
        "current_price": 12_350,
        "open_price": 12_100,
        "acml_vol": 500_000,  # flag_avg_volume × 2.0 = 400_000 초과
    }
    # 직전 틱 < 12_300, 현재 틱 ≥ 12_300 (돌파 순간)
    strat._prev_price["005930"] = 12_290

    with freeze_time("2026-05-08 09:30:00"):
        result = strat.check_buy_signal("005930", 12_350, 12_100)

    assert result == Signal.BUY
    assert "005930" in strat._bought_today


def test_buy_when_no_breakout_then_none(strat):
    _seed_candidate(strat, "005930", flag_high=12_300)
    strat._prev_price["005930"] = 12_100
    with freeze_time("2026-05-08 09:30:00"):
        # 현재가 12_200 < flag_high 12_300 → 돌파 안 함
        assert strat.check_buy_signal("005930", 12_200, 12_100) == Signal.NONE


def test_buy_when_breakout_but_low_volume_then_none(strat):
    _seed_candidate(strat, "005930", flag_high=12_300, flag_avg_volume=200_000)
    from src.engine import scanner as _scanner
    _scanner.ticker_prices["005930"] = {
        "current_price": 12_350,
        "open_price": 12_100,
        "acml_vol": 300_000,  # < 200_000 × 2.0 = 400_000
    }
    strat._prev_price["005930"] = 12_290
    with freeze_time("2026-05-08 09:30:00"):
        assert strat.check_buy_signal("005930", 12_350, 12_100) == Signal.NONE


def test_buy_when_already_in_bought_today_then_none(strat):
    _seed_candidate(strat, "005930")
    strat._bought_today.add("005930")
    with freeze_time("2026-05-08 09:30:00"):
        assert strat.check_buy_signal("005930", 12_400, 12_100) == Signal.NONE


def test_buy_when_no_candidate_then_none(strat):
    with freeze_time("2026-05-08 09:30:00"):
        assert strat.check_buy_signal("005930", 12_400, 12_100) == Signal.NONE


def test_buy_when_already_held_then_none(strat):
    _seed_candidate(strat, "005930")
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_100, quantity=10,
        order_no="O1", strategy_id="bull_flag_breakout",
    )
    with freeze_time("2026-05-08 09:30:00"):
        assert strat.check_buy_signal("005930", 12_400, 12_100) == Signal.NONE


def test_buy_when_buy_disabled_then_none(strat):
    _seed_candidate(strat, "005930")
    strat.state.buy_disabled = True
    with freeze_time("2026-05-08 09:30:00"):
        assert strat.check_buy_signal("005930", 12_400, 12_100) == Signal.NONE


# ---------------------------------------------------------------------------
# check_buy_signal — 쿨다운 3영업일
# ---------------------------------------------------------------------------
def test_buy_when_in_cooldown_then_none(strat):
    _seed_candidate(strat, "005930")
    # 청산일 (today - 2 영업일) → 3영업일 쿨다운 아직 안 지남
    with freeze_time("2026-05-08 09:30:00"):
        today = date(2026, 5, 8)
        strat._cooldown_until["005930"] = today + timedelta(days=1)  # 내일까지 쿨다운
        from src.engine import scanner as _scanner
        _scanner.ticker_prices["005930"] = {
            "current_price": 12_350, "open_price": 12_100, "acml_vol": 500_000,
        }
        strat._prev_price["005930"] = 12_290
        assert strat.check_buy_signal("005930", 12_350, 12_100) == Signal.NONE


def test_buy_when_cooldown_expired_then_buy(strat):
    _seed_candidate(strat, "005930", flag_high=12_300, flag_avg_volume=200_000)
    with freeze_time("2026-05-08 09:30:00"):
        today = date(2026, 5, 8)
        strat._cooldown_until["005930"] = today - timedelta(days=1)  # 어제 만료
        from src.engine import scanner as _scanner
        _scanner.ticker_prices["005930"] = {
            "current_price": 12_350, "open_price": 12_100, "acml_vol": 500_000,
        }
        strat._prev_price["005930"] = 12_290
        assert strat.check_buy_signal("005930", 12_350, 12_100) == Signal.BUY


# ---------------------------------------------------------------------------
# check_exit_signal — 하드 손절 / 플래그 하단 이탈
# ---------------------------------------------------------------------------
def test_exit_when_loss_breaches_minus_5_then_stop_loss(strat):
    _seed_candidate(strat, "005930", flag_low=11_800, atr14=300)
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="bull_flag_breakout",
    )
    # -5% 정확히: 12_000 × 0.95 = 11_400
    assert strat.check_exit_signal("005930", 11_400, 12_000) == Signal.STOP_LOSS


def test_exit_when_below_flag_low_then_stop_loss(strat):
    _seed_candidate(strat, "005930", flag_low=11_800, atr14=300)
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="bull_flag_breakout",
    )
    # 손절 -5% 안 닿았지만 (12_000 × 0.95 = 11_400, 현재 11_750 > 11_400)
    # flag_low 11_800 이탈 → STOP_LOSS
    assert strat.check_exit_signal("005930", 11_750, 12_000) == Signal.STOP_LOSS


# ---------------------------------------------------------------------------
# check_exit_signal — 측정된 이동(measured move) 익절
# ---------------------------------------------------------------------------
def test_exit_when_measured_move_reached_then_trailing_stop(strat):
    # 폴 폭 = pole_high(12_500) - pole_start(10_000) = 2_500
    # 타겟가 = flag_high(12_300) + 2_500 = 14_800
    _seed_candidate(
        strat, "005930",
        pole_start=10_000, pole_high=12_500,
        flag_high=12_300, flag_low=11_800, atr14=300,
    )
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_300, quantity=10,
        order_no="O1", strategy_id="bull_flag_breakout",
        high_since_buy=14_800,
    )
    # current 14_800 (타겟 정확히 도달) → 익절 신호
    result = strat.check_exit_signal("005930", 14_800, 12_300)
    assert result in (Signal.TRAILING_STOP, Signal.FORCE_CLEAR)
    # 측정된 이동 도달 마킹
    assert strat._partial_exit.get("005930") is True


# ---------------------------------------------------------------------------
# check_exit_signal — ATR×2 트레일링 (partial_exit 후)
# ---------------------------------------------------------------------------
def test_exit_atr_trailing_after_partial(strat):
    _seed_candidate(
        strat, "005930",
        pole_start=10_000, pole_high=12_500,
        flag_high=12_300, flag_low=11_800, atr14=300,
    )
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_300, quantity=10,
        order_no="O1", strategy_id="bull_flag_breakout",
        high_since_buy=15_500,  # 측정된 이동 후 추가 상승
    )
    strat._partial_exit["005930"] = True
    # chandelier = 15_500 - 300×2 = 14_900. current 14_800 ≤ 14_900 → TRAILING_STOP
    assert strat.check_exit_signal("005930", 14_800, 12_300) == Signal.TRAILING_STOP


# ---------------------------------------------------------------------------
# check_exit_signal — 시간 청산 5영업일 초과
# ---------------------------------------------------------------------------
def test_exit_when_held_over_5_days_then_force_clear(strat):
    _seed_candidate(strat, "005930", flag_low=11_800, atr14=300)
    # buy_date = today - 7일 (캘린더일 5영업일 ≈ 캘린더일 7~9일)
    with freeze_time("2026-05-15 14:00:00"):
        today = date(2026, 5, 15)
        strat.state.positions["005930"] = Position(
            ticker="005930", buy_price=12_000, quantity=10,
            order_no="O1", strategy_id="bull_flag_breakout",
            buy_date=today - timedelta(days=9),  # 9일 전 매수 → 5영업일 초과
            high_since_buy=12_500,
        )
        result = strat.check_exit_signal("005930", 12_400, 12_000)
        # 명세상 잔량 시장가 — TRAILING_STOP 또는 FORCE_CLEAR 둘 다 OK
        assert result in (Signal.TRAILING_STOP, Signal.FORCE_CLEAR)


def test_exit_when_no_position_then_none(strat):
    assert strat.check_exit_signal("005930", 12_400, 12_100) == Signal.NONE


# ---------------------------------------------------------------------------
# check_force_clear
# ---------------------------------------------------------------------------
def test_force_clear_returns_empty_list_by_default(strat):
    # 본 전략은 15:20 강제 청산 없음 — `max_hold_days` 는 check_exit_signal 에서 처리
    strat.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10,
        order_no="O1", strategy_id="bull_flag_breakout",
    )
    assert strat.check_force_clear() == []


# ---------------------------------------------------------------------------
# calc_buy_quantity + 1주 폴백
# ---------------------------------------------------------------------------
def test_calc_qty_when_amount_covers_qty(strat):
    strat.state.total_investment = 10_000_000  # 25% = 2.5M
    assert strat.calc_buy_quantity(current_price=10_000) == 250


def test_calc_qty_falls_back_to_one_share_when_remaining_covers(strat):
    # position_ratio × total_investment 가 1주 미만이지만, 잔여 자금이 1주는 살 수 있음
    strat.state.total_investment = 100_000  # 25% = 25_000 < 50_000 (1주)
    # 다른 보유/주문중 없음 → 잔여 = 100_000 ≥ 50_000 → 1주
    assert strat.calc_buy_quantity(current_price=50_000) == 1


def test_calc_qty_returns_zero_when_remaining_below_one_share(strat):
    strat.state.total_investment = 100_000
    # 이미 다른 종목으로 90_000 사용 → 잔여 10_000 < 50_000 → 0
    strat.state.positions["111111"] = Position(
        ticker="111111", buy_price=90_000, quantity=1,
        order_no="O9", strategy_id="bull_flag_breakout",
    )
    assert strat.calc_buy_quantity(current_price=50_000) == 0


# ---------------------------------------------------------------------------
# prepare 통합 (가벼운 smoke — _candidates 가 정상 셋업 후 채워짐)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prepare_populates_candidates_on_valid_setup(strat, monkeypatch):
    """폴 +25%, 플래그 retracement 20%, 거래량 수축 통과 → _candidates 등록."""
    # 일봉 mock — 최신순(idx=0 이 최신)
    # 폴 5일(+25% 상승), 플래그 4일(완만 조정 + 거래량 수축), 그 외 노이즈
    # candles[0] 이 오늘이 아닌 영업일이어야 prev_idx=0 정상 동작
    fake_candles = [
        # 플래그 종료 (idx 0~3) — flag_low 좀 더 깊지 않게, 거래량 평균 200_000
        {"stck_bsop_date": "20260507", "stck_clpr": "12100", "stck_hgpr": "12200", "stck_lwpr": "11900", "stck_oprc": "12150", "acml_vol": "150000"},
        {"stck_bsop_date": "20260506", "stck_clpr": "12150", "stck_hgpr": "12250", "stck_lwpr": "11950", "stck_oprc": "12200", "acml_vol": "180000"},
        {"stck_bsop_date": "20260502", "stck_clpr": "12200", "stck_hgpr": "12300", "stck_lwpr": "12050", "stck_oprc": "12250", "acml_vol": "200000"},
        {"stck_bsop_date": "20260430", "stck_clpr": "12250", "stck_hgpr": "12300", "stck_lwpr": "12100", "stck_oprc": "12280", "acml_vol": "220000"},
        # 폴 5일 (10000 → 12500, +25%, 거래량 폭증 평균 ~500_000)
        {"stck_bsop_date": "20260429", "stck_clpr": "12500", "stck_hgpr": "12550", "stck_lwpr": "12100", "stck_oprc": "12200", "acml_vol": "600000"},
        {"stck_bsop_date": "20260428", "stck_clpr": "12100", "stck_hgpr": "12200", "stck_lwpr": "11500", "stck_oprc": "11500", "acml_vol": "550000"},
        {"stck_bsop_date": "20260427", "stck_clpr": "11500", "stck_hgpr": "11600", "stck_lwpr": "10800", "stck_oprc": "10800", "acml_vol": "500000"},
        {"stck_bsop_date": "20260424", "stck_clpr": "10800", "stck_hgpr": "10900", "stck_lwpr": "10300", "stck_oprc": "10300", "acml_vol": "450000"},
        {"stck_bsop_date": "20260423", "stck_clpr": "10300", "stck_hgpr": "10400", "stck_lwpr": "10000", "stck_oprc": "10000", "acml_vol": "400000"},
        # 폴 이전 횡보 (10일치 추가)
    ] + [
        {"stck_bsop_date": f"2026040{9-i}", "stck_clpr": "10000", "stck_hgpr": "10100", "stck_lwpr": "9900", "stck_oprc": "10000", "acml_vol": "100000"}
        for i in range(15)
    ]

    async def fake_fetch(ticker, days):
        return fake_candles

    async def fake_universe(self):
        return ["005930"]

    monkeypatch.setattr("src.api.condition.fetch_daily_candles", fake_fetch)
    monkeypatch.setattr(BullFlagBreakoutStrategy, "_scan_universe", fake_universe)
    # 사이클 187 회귀 흡수 — prepare() 의 DB일봉 어댑터(stock_master_daily.
    # get_recent_daily_normalized → get_recent_daily)가 실연결을 시도하면
    # httpx.ConnectError → 사이클 187 retry 래퍼가 `await asyncio.sleep(0.2)` 진입 →
    # freeze_time 으로 동결된 monotonic 때문에 이벤트 루프가 영원히 깨어나지 못해 60s hang.
    # DB read 를 빈 결과로 결정화하면 어댑터는 lock/신선도 게이트(`if db_rows:`)를 건너뛰고
    # 기존 KIS 폴백(위 fetch_daily_candles mock) 경로로 그대로 진행 → pre-187 동작 보존 +
    # retry 경로 미진입(실연결·sleep 차단). candidate 생성 검증 의도는 불변.
    monkeypatch.setattr(
        "src.db.stock_master_daily.get_recent_daily",
        AsyncMock(return_value=[]),
    )

    with freeze_time("2026-05-08 07:50:00"):
        await strat.prepare()

    assert "005930" in strat._candidates
    info = strat._candidates["005930"]
    assert info["pole_high"] >= 12_500
    assert info["flag_high"] > 0
    assert info["flag_low"] > 0
    assert info["atr14"] > 0
