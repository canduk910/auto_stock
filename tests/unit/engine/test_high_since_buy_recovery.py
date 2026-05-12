"""E3 — donchian_swing high_since_buy 일봉 폴백 보정 단위 테스트.

명세: `/Users/koscom/Projects/auto_stock/_workspace/00_leader_trading_rules.md`
       "high_since_buy 일봉 폴백 (E3, 2026-05-12)" 섹션.

대상: `DonchianSwingStrategy.recompute_high_since_buy()` (신규 메서드).
원리: 보유 종목별 매수일~전영업일까지 KIS 일봉 high max 로 `pos.high_since_buy` 보정.
      시세 미수신 누적으로 chandelier 트레일링이 매수가 부근에 동결되는 결함 차단.

테스트 케이스(8종):
- A: 매수일=어제, 일봉 어제 high > buy_price → 보정 + DB UPDATE
- B: 매수일=오늘 → skip (fetch 호출도 안 함)
- C: 일봉 응답 빈 리스트 → skip, 값 변경 없음
- D: fetch_daily_candles raise → 해당 종목 skip + 다른 포지션 정상
- E: 일별 high 모두 buy_price 미만 → 보정 안 함
- F: 일봉에 매수일/오늘 데이터 포함 → 매수일 < bsop_date < today 만 max
- G: pos.buy_date > today (비정상) → skip + WARNING
- H: 다중 보유 3종목, 1종목 fetch 실패 → 나머지 2종목 정상 (sequential)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, StrategyConfig

pytestmark = pytest.mark.unit

# 운영 코드(`donchian_swing.py`)는 `today = datetime.now(KST).date()` 로 평가하므로
# 테스트도 동일 기준으로 맞춘다. CI/로컬이 UTC 인 환경에서 KST 자정 직후~09시 사이
# `_today_kst()` 와 1일 어긋나는 결함 차단.
_KST = timezone(timedelta(hours=9))


def _today_kst() -> date:
    return datetime.now(_KST).date()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def donchian():
    return DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="20일 신고가", weight=0.2)
    )


def _add_position(strategy, ticker, *, buy_price, buy_date, high_since_buy=0):
    """Position을 strategy.state.positions에 추가한다."""
    pos = Position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=10,
        order_no=f"ORD-{ticker}",
        strategy_id="donchian_swing",
        buy_date=buy_date,
        high_since_buy=high_since_buy or buy_price,
    )
    strategy.state.positions[ticker] = pos
    return pos


def _candle(yyyymmdd: str, *, high: int, low: int = 0, close: int = 0):
    """fetch_daily_candles 응답 row 단순화 헬퍼."""
    return {
        "stck_bsop_date": yyyymmdd,
        "stck_hgpr": str(high),
        "stck_lwpr": str(low or high - 1000),
        "stck_clpr": str(close or high - 500),
    }


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# Case A: 매수일=어제, 어제 high > buy_price → 보정 + DB UPDATE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recover_when_yesterday_high_above_buy_price_then_update():
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="20일 신고가", weight=0.2)
    )
    today = _today_kst()
    yesterday = today - timedelta(days=1)
    # 매수일은 어제 이전(그제) — buy_date < bsop_date < today 경계 충족 위해
    day_before_yesterday = today - timedelta(days=2)
    pos = _add_position(strat, "139480", buy_price=115600, buy_date=day_before_yesterday)

    # 일봉 응답: 가장 최근(어제) high=120000 → 매수일 다음 영업일이자 전영업일
    candles = [_candle(_ymd(yesterday), high=120000)]

    with patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=candles),
    ), patch(
        "src.db.positions.update_high",
        new=AsyncMock(),
    ) as mock_update:
        await strat.recompute_high_since_buy()

    assert pos.high_since_buy == 120000
    mock_update.assert_awaited_once_with("139480", 120000)


# ---------------------------------------------------------------------------
# Case B: 매수일=오늘 → skip (fetch도 안 함)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skip_when_buy_date_is_today(donchian):
    today = _today_kst()
    pos = _add_position(donchian, "005930", buy_price=70000, buy_date=today)

    with patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=[]),
    ) as mock_fetch, patch(
        "src.db.positions.update_high",
        new=AsyncMock(),
    ) as mock_update:
        await donchian.recompute_high_since_buy()

    assert pos.high_since_buy == 70000  # 변경 없음 (buy_price 그대로)
    mock_fetch.assert_not_awaited()       # fetch 호출 자체 안 함
    mock_update.assert_not_awaited()


# ---------------------------------------------------------------------------
# Case C: 일봉 응답 빈 리스트 → skip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skip_when_empty_candles(donchian):
    yesterday = _today_kst() - timedelta(days=1)
    pos = _add_position(donchian, "005930", buy_price=70000, buy_date=yesterday)

    with patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=[]),
    ), patch(
        "src.db.positions.update_high",
        new=AsyncMock(),
    ) as mock_update:
        await donchian.recompute_high_since_buy()

    assert pos.high_since_buy == 70000
    mock_update.assert_not_awaited()


# ---------------------------------------------------------------------------
# Case D: fetch raise → 해당 종목 skip + 다른 포지션 정상
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_when_fetch_raises_then_skip_one_and_continue_others():
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="20일 신고가", weight=0.2)
    )
    today = _today_kst()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)
    pos_a = _add_position(strat, "111111", buy_price=10000, buy_date=day_before)
    pos_b = _add_position(strat, "222222", buy_price=20000, buy_date=day_before)

    async def fake_fetch(ticker, days):
        if ticker == "111111":
            raise RuntimeError("KIS 5xx")
        return [_candle(_ymd(yesterday), high=25000)]

    with patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=fake_fetch),
    ), patch(
        "src.db.positions.update_high",
        new=AsyncMock(),
    ) as mock_update:
        await strat.recompute_high_since_buy()

    # 111111: 실패 → 변경 없음
    assert pos_a.high_since_buy == 10000
    # 222222: 정상 보정
    assert pos_b.high_since_buy == 25000
    # update_high는 222222에 대해서만 호출
    mock_update.assert_awaited_once_with("222222", 25000)


# ---------------------------------------------------------------------------
# Case E: 일별 high 모두 buy_price 미만 → 보정 안 함
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_when_all_highs_below_buy_price_then_no_change(donchian):
    today = _today_kst()
    five_days_ago = today - timedelta(days=5)
    yesterday = today - timedelta(days=1)
    pos = _add_position(donchian, "005930", buy_price=70000, buy_date=five_days_ago)

    # buy_price 미만의 high들만
    candles = [
        _candle(_ymd(yesterday), high=68000),
        _candle(_ymd(today - timedelta(days=2)), high=67500),
        _candle(_ymd(today - timedelta(days=3)), high=66800),
    ]

    with patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=candles),
    ), patch(
        "src.db.positions.update_high",
        new=AsyncMock(),
    ) as mock_update:
        await donchian.recompute_high_since_buy()

    assert pos.high_since_buy == 70000  # buy_price 그대로
    mock_update.assert_not_awaited()


# ---------------------------------------------------------------------------
# Case F: 일봉에 매수일/오늘 데이터 포함 → 매수일 < bsop_date < today만 max
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_boundary_excludes_buy_date_and_today():
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="20일 신고가", weight=0.2)
    )
    today = _today_kst()
    buy_day = today - timedelta(days=5)
    pos = _add_position(strat, "005930", buy_price=70000, buy_date=buy_day)

    # candles[0]=오늘(부분봉, 999999 매우 큰 high — 반드시 제외돼야)
    # candles[?]=buy_day(매수 당일, 888888 매우 큰 high — 반드시 제외돼야)
    # 매수일 다음~전영업일: 75000, 73000 (75000이 max)
    candles = [
        _candle(_ymd(today), high=999999),
        _candle(_ymd(today - timedelta(days=1)), high=73000),
        _candle(_ymd(today - timedelta(days=2)), high=75000),
        _candle(_ymd(today - timedelta(days=3)), high=72000),
        _candle(_ymd(buy_day), high=888888),
    ]

    with patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=candles),
    ), patch(
        "src.db.positions.update_high",
        new=AsyncMock(),
    ) as mock_update:
        await strat.recompute_high_since_buy()

    assert pos.high_since_buy == 75000   # 999999/888888 모두 제외
    mock_update.assert_awaited_once_with("005930", 75000)


# ---------------------------------------------------------------------------
# Case G: buy_date > today (비정상) → skip + WARNING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skip_when_buy_date_in_future(donchian, caplog):
    import logging
    future = _today_kst() + timedelta(days=3)
    pos = _add_position(donchian, "005930", buy_price=70000, buy_date=future)

    with patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=[]),
    ) as mock_fetch, patch(
        "src.db.positions.update_high",
        new=AsyncMock(),
    ) as mock_update, caplog.at_level(logging.WARNING, logger="src.engine.strategies.donchian_swing"):
        await donchian.recompute_high_since_buy()

    assert pos.high_since_buy == 70000
    mock_fetch.assert_not_awaited()    # 미래일자는 fetch 호출도 안 함
    mock_update.assert_not_awaited()
    # WARNING 로그가 한 번 이상 남았는지 확인
    assert any("buy_date" in rec.message or "비정상" in rec.message
               for rec in caplog.records), "비정상 buy_date에 대해 WARNING 로그가 필요"


# ---------------------------------------------------------------------------
# Case H: 다중 보유 + sequential await (병렬 금지)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_positions_sequential_and_partial_failure_isolated():
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="20일 신고가", weight=0.2)
    )
    today = _today_kst()
    yesterday = today - timedelta(days=1)
    pos_a = _add_position(strat, "111111", buy_price=50000, buy_date=yesterday)
    pos_b = _add_position(strat, "222222", buy_price=60000, buy_date=yesterday)
    pos_c = _add_position(strat, "333333", buy_price=80000, buy_date=yesterday)

    call_order: list[str] = []

    async def fake_fetch(ticker, days):
        call_order.append(ticker)
        if ticker == "222222":
            raise RuntimeError("fetch fail mid-loop")
        return [_candle(_ymd(yesterday), high=int(ticker[:2]) * 1000 + 5000)]

    with patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=fake_fetch),
    ), patch(
        "src.db.positions.update_high",
        new=AsyncMock(),
    ) as mock_update:
        await strat.recompute_high_since_buy()

    # 3종목 모두 fetch 시도(sequential)
    assert set(call_order) == {"111111", "222222", "333333"}
    # 111111: high=11000+5000=16000 < buy_price=50000 → 변경 없음 (Case E와 동일)
    assert pos_a.high_since_buy == 50000
    # 222222: 실패 → 변경 없음
    assert pos_b.high_since_buy == 60000
    # 333333: high=33000+5000=38000 < buy_price=80000 → 변경 없음
    assert pos_c.high_since_buy == 80000
    # DB UPDATE는 한 건도 발생 안 함 (모든 high가 buy_price 미만)
    mock_update.assert_not_awaited()


# ---------------------------------------------------------------------------
# 추가: 다중 보유 + 실제 보정 발생 케이스 (H 보완 — 정상 보정 검증)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_positions_partial_recovery():
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="20일 신고가", weight=0.2)
    )
    today = _today_kst()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)
    pos_a = _add_position(strat, "139480", buy_price=115600, buy_date=day_before)
    pos_b = _add_position(strat, "012450", buy_price=95000, buy_date=day_before)

    async def fake_fetch(ticker, days):
        if ticker == "139480":
            return [_candle(_ymd(yesterday), high=120000)]
        if ticker == "012450":
            raise RuntimeError("KIS network err")
        return []

    with patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=fake_fetch),
    ), patch(
        "src.db.positions.update_high",
        new=AsyncMock(),
    ) as mock_update:
        await strat.recompute_high_since_buy()

    assert pos_a.high_since_buy == 120000  # 정상 보정
    assert pos_b.high_since_buy == 95000   # fetch 실패 → buy_price 그대로
    mock_update.assert_awaited_once_with("139480", 120000)


# ---------------------------------------------------------------------------
# 회귀: recompute_held_atr 가 high_since_buy 보정도 함께 수행하는지 (통합점)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recompute_held_atr_also_recovers_high_since_buy():
    """`_boot()` 에서 호출되는 `recompute_held_atr()` 가 high_since_buy 보정도
    함께 수행해야 한다 (fetch 비용 절감 — 일봉 1회로 ATR + high 양쪽 갱신)."""
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="20일 신고가", weight=0.2)
    )
    today = _today_kst()
    yesterday = today - timedelta(days=1)
    # 매수일 5일 전(buy_date < yesterday 경계 충족)
    five_days_ago = today - timedelta(days=5)
    pos = _add_position(strat, "139480", buy_price=115600, buy_date=five_days_ago)

    # ATR 계산용으로 충분한 길이의 일봉 (atr_period+2 이상)
    candles = []
    # 가장 최근(=어제)에 high=120000
    candles.append({
        "stck_bsop_date": _ymd(yesterday),
        "stck_hgpr": "120000",
        "stck_lwpr": "118000",
        "stck_clpr": "119000",
    })
    # 그 이전 영업일들 — 단순 더미
    for i in range(2, 20):
        d = today - timedelta(days=i)
        candles.append({
            "stck_bsop_date": _ymd(d),
            "stck_hgpr": "115000",
            "stck_lwpr": "113000",
            "stck_clpr": "114000",
        })

    with patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=candles),
    ), patch(
        "src.db.positions.update_high",
        new=AsyncMock(),
    ):
        await strat.recompute_held_atr()

    # ATR 재계산 결과 (_candidates 등록) — 기존 회귀
    assert "139480" in strat._candidates
    assert strat._candidates["139480"]["atr"] > 0
    # E3 신규 — high_since_buy 보정도 수행
    assert pos.high_since_buy == 120000
