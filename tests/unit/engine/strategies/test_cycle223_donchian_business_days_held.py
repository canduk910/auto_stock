"""사이클 223 Red (S3) — donchian 시간청산 `days_held` 달력일 → 영업일.

> 자문: `_workspace/domain_consult/donchian_exit_retune.md` §3-2 / §4 C1
> 선례: `_workspace/refactor/2026-06-27_full_review.md` `strat-6` CONFIRMED **미시정**

## 결함

    :892-894  today = datetime.now(KST).date()
              days_held = (today - pos.buy_date).days      ← 순수 달력 차이
              if days_held >= n_days and current_price < breakout_high:

`breakout_fail_n_days=2`(라이브) 와 결합하면 **금요일 매수 → 월요일 = 3일 ≥ 2** 로
실거래 **1일** 만에 청산 자격을 얻는다. 실측 13건 중 7건이 금요일 매수, 6건이 실제
그 경로였다 — 예외가 아니라 상시 경로다. 매매 규칙 정본(`_workspace/00_leader_trading_rules.md`)
은 "보유 5**영업일**" 이라 코드↔계약 불일치이기도 하다.

## ⚠️ hot path 제약

`check_exit_signal` 은 `risk.on_tick` 에서 초당 수십~수백 회 호출된다.
**신규 `await`/DB/HTTP 절대 금지** — `StrategyBase._refine_cooldown_business_days` 가
쓰는 KIS `add_business_days`(CTCA0903R) 는 async 라 여기서 못 쓴다.

## 인터페이스 계약 (tdd-engineer 확정 — backend-dev 구현 대상)

1. `self._trading_days: set[datetime.date]` — 거래일 캐시.
   `prepare()` 와 `recompute_held_atr()` 가 이미 fetch 한 일봉의 거래일로 **update**
   (와이프 금지 — 종목마다 fetch 창이 달라 합집합이어야 한다). 날짜 추출은
   `StrategyBase._candle_trade_date` 위임 (KIS `stck_bsop_date` / 정규화 `bas_dd`
   양쪽 수용 — 어댑터가 raw 없는 row 를 row 자체로 돌려주는 경로 대응).

2. `_business_days_held(buy_date, today) -> tuple[int, bool]` — **동기 순수함수, I/O 0**.
   반환 `(영업일 보유일수, 폴백_사용_여부)`.
   - 캐시 사용 조건: 캐시 비지 않음 **그리고** `min(cache) <= buy_date`
     (캐시가 매수일까지 못 닿으면 조용한 과소 계상 → 폴백해야 한다)
   - 캐시 경로: `len({d in cache : buy_date < d <= today})`, 단 `today > buy_date`
     이고 `today not in cache` 면 **+1** (`run_daily` 가 휴장일을 건너뛰므로 오늘은
     영업일 보장 · 캐시는 D-1 까지만 있을 수 있다)
   - 폴백 경로: `(buy_date, today]` 구간의 **weekday(주말 제외) 개수**, `used_fallback=True`.
     공휴일을 영업일로 세므로 약간 과다 계상 = 약간 이른 청산 — 현행 달력일보다는
     엄격히 낫다(달력일은 주말까지 센다).

3. 로그: 발화 문구는 기존 prefix **`도치안 시간 기반 청산`** 를 유지하되(운영자 grep
   이력) 일수가 **영업일**임이 드러나야 한다. 폴백으로 센 경우 그 사실도 로그에
   드러나야 한다(`폴백` 또는 `days_held_fallback`). hot path 라 폴백 로그는 발화
   분기 안이거나 종목·일자 dedup — **틱마다 방출 금지**.

4. `n_days`(2) 값은 **불변**. 이번 사이클은 세는 방법만 고친다.

## Red 유효성 (production 미변경)

- S3-1/S3-4/S3-5/S3-6/S3-10 = FAIL (`_business_days_held`/`_trading_days` 부재 → AttributeError,
  또는 달력일이라 조기 발화)
- S3-2/S3-12 = PASS (발화 유지 회귀 가드)
"""
from __future__ import annotations

import datetime as _dt
import logging
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit
KST = _dt.timezone(_dt.timedelta(hours=9))
_LOGGER = "src.engine.strategies.donchian_swing"

D = _dt.date


def _mk(n_days: int = 2, **params) -> DonchianSwingStrategy:
    cfg = StrategyConfig(
        strategy_id="donchian_swing", name="도치안", weight=0.2,
        params={"sizing_mode": "position_ratio", "breakout_fail_n_days": n_days, **params},
    )
    s = DonchianSwingStrategy(cfg)
    s.state.total_investment = 100_000_000
    return s


def _arm(s, ticker="005930", buy_date=None, buy_price=10_000, breakout_high=11_000):
    """시간청산 분기만 노출 — 손절/채널/트레일링 전부 미해당 상태로 격리."""
    pos = Position(ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
                   strategy_id="donchian_swing", buy_date=buy_date)
    pos.high_since_buy = buy_price
    s.state.positions[ticker] = pos
    s._candidates[ticker] = {"prev_close": buy_price, "atr": 0, "ema60": 0,
                             "donchian_high": breakout_high}
    s._breakout_high[ticker] = breakout_high
    return pos


def _cache(s, days: list[D]) -> None:
    s._trading_days = set(days)


# 거래일 캐시 픽스처 (실제 KRX 영업일)
_AUG_WEEK = [D(2026, 8, 10), D(2026, 8, 11), D(2026, 8, 12), D(2026, 8, 13), D(2026, 8, 14)]
_AUG_NEXT = _AUG_WEEK + [D(2026, 8, 17), D(2026, 8, 18), D(2026, 8, 19), D(2026, 8, 20)]


# ===========================================================================
# S3-1 (핵심) — 금요일 매수 → 월요일 = 1 영업일 (달력 3 아님) → n=2 미발화
# ===========================================================================
@freeze_time("2026-08-17 10:00:00+09:00")
def test_s3_1_friday_buy_monday_is_one_business_day():
    """금(08-14) 매수 → 월(08-17): 영업일 1 < n_days 2 → 청산 미발화.

    현행: 달력 3일 ≥ 2 → STOP_LOSS (실거래 1일 만에 청산 자격 = 결함).
    """
    s = _mk(n_days=2)
    _cache(s, _AUG_WEEK)                       # 캐시는 D-1(08-14) 까지
    _arm(s, buy_date=D(2026, 8, 14))

    assert s._business_days_held(D(2026, 8, 14), D(2026, 8, 17)) == (1, False)
    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE, (
        "S3-1: 금요일 매수 → 월요일은 1 영업일 — n_days=2 에서 발화 금지"
    )


# ===========================================================================
# S3-2 — 화요일 매수 → 목요일 = 2 영업일 → n=2 발화 (회귀 가드)
# ===========================================================================
@freeze_time("2026-08-20 10:00:00+09:00")
def test_s3_2_tuesday_buy_thursday_is_two_business_days_fires():
    """화(08-18) 매수 → 목(08-20): 영업일 2 ≥ 2 → STOP_LOSS 유지."""
    s = _mk(n_days=2)
    _cache(s, _AUG_NEXT[:-1])                  # 캐시 D-1(08-19) 까지 = 오늘 미포함
    _arm(s, buy_date=D(2026, 8, 18))

    assert s._business_days_held(D(2026, 8, 18), D(2026, 8, 20)) == (2, False)
    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.STOP_LOSS


def test_s3_3_today_in_cache_is_not_double_counted():
    """캐시에 오늘이 이미 있으면 `+1` 보정을 하지 않는다 (이중 계상 차단)."""
    s = _mk(n_days=3)
    _cache(s, _AUG_NEXT)                       # 08-20(오늘) 포함
    assert s._business_days_held(D(2026, 8, 18), D(2026, 8, 20)) == (2, False)


def test_s3_3b_same_day_buy_is_zero():
    """매수 당일은 0 영업일 (`+1` 보정이 매수일 자신을 세면 안 된다)."""
    s = _mk()
    _cache(s, _AUG_NEXT)
    days, _fb = s._business_days_held(D(2026, 8, 20), D(2026, 8, 20))
    assert days == 0


# ===========================================================================
# S3-4 — 공휴일이 낀 구간은 캐시 거래일 기준으로 정확히 센다
# ===========================================================================
def test_s3_4_holiday_gap_counted_from_cache():
    """추석 휴장(10-01~10-05) — 09-30 매수 → 10-06 은 **1 영업일**.

    달력일이면 6, weekday 폴백이면 4(10-01·02·05·06). 캐시 경로만 1을 낸다.
    """
    s = _mk(n_days=2)
    _cache(s, [D(2026, 9, 25), D(2026, 9, 28), D(2026, 9, 29), D(2026, 9, 30),
               D(2026, 10, 6)])
    assert s._business_days_held(D(2026, 9, 30), D(2026, 10, 6)) == (1, False)


@freeze_time("2026-10-06 10:00:00+09:00")
def test_s3_4b_holiday_gap_does_not_fire():
    """같은 구간에서 n_days=2 청산이 발화하지 않는다 (달력 6일 → 현행 발화)."""
    s = _mk(n_days=2)
    _cache(s, [D(2026, 9, 25), D(2026, 9, 28), D(2026, 9, 29), D(2026, 9, 30),
               D(2026, 10, 6)])
    _arm(s, buy_date=D(2026, 9, 30))
    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE


# ===========================================================================
# S3-5 / S3-6 — 폴백 (캐시 부재 / 캐시가 매수일까지 못 닿음)
# ===========================================================================
@freeze_time("2026-08-17 10:00:00+09:00")
def test_s3_5_weekday_fallback_when_cache_empty():
    """캐시 비어있음(재시작 직후 prepare 전) → weekday 폴백, 주말은 제외한다."""
    s = _mk(n_days=2)
    _cache(s, [])
    _arm(s, buy_date=D(2026, 8, 14))

    assert s._business_days_held(D(2026, 8, 14), D(2026, 8, 17)) == (1, True)
    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE, (
        "S3-5: 폴백도 주말은 세지 않는다 — 금→월 = 1 < 2"
    )


def test_s3_6_fallback_when_cache_does_not_reach_buy_date():
    """캐시 최소일 > 매수일 → 조용한 과소 계상 대신 폴백."""
    s = _mk(n_days=2)
    _cache(s, [D(2026, 8, 19), D(2026, 8, 20)])
    days, used_fallback = s._business_days_held(D(2026, 8, 14), D(2026, 8, 20))
    assert used_fallback is True, "캐시가 매수일 이전까지 못 닿으면 폴백 의무"
    assert days == 4, f"폴백 weekday 계산 (08-17·18·19·20) 기대 4, got {days}"


# ===========================================================================
# S3-7 / S3-8 — 로그 계약 (기존 prefix 유지 + 영업일 명시 + 폴백 노출)
# ===========================================================================
@freeze_time("2026-08-20 10:00:00+09:00")
def test_s3_7_exit_log_keeps_prefix_and_says_business_days(caplog):
    """발화 로그: prefix `도치안 시간 기반 청산` 유지 + `영업일` 명시."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, _AUG_NEXT)
    _arm(s, buy_date=D(2026, 8, 18))

    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.STOP_LOSS
    msgs = [r.getMessage() for r in caplog.records]
    assert any("도치안 시간 기반 청산" in m for m in msgs), (
        f"기존 grep 이력 prefix 유지 의무 — got {msgs}"
    )
    assert any("도치안 시간 기반 청산" in m and "영업일" in m for m in msgs), (
        f"일수가 영업일임이 드러나야 한다 — got {msgs}"
    )
    assert not any("폴백" in m or "days_held_fallback" in m for m in msgs), (
        "캐시 경로에서는 폴백 표기 금지"
    )


@freeze_time("2026-08-21 10:00:00+09:00")
def test_s3_8_fallback_fact_is_logged_on_fire(caplog):
    """폴백으로 센 경우 그 사실이 로그로 드러난다."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, [])
    _arm(s, buy_date=D(2026, 8, 10))           # weekday 폴백 9일 ≥ 2 → 발화

    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.STOP_LOSS
    msgs = [r.getMessage() for r in caplog.records]
    assert any("폴백" in m or "days_held_fallback" in m for m in msgs), (
        f"폴백 사용 사실이 로그에 드러나야 한다 — got {msgs}"
    )


@freeze_time("2026-08-17 10:00:00+09:00")
def test_s3_9_fallback_log_not_emitted_per_tick(caplog):
    """hot path — 미발화 틱 50회에 폴백 로그가 쏟아지면 안 된다 (발화 분기 내 또는 dedup)."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, [])
    _arm(s, buy_date=D(2026, 8, 14))

    for _ in range(50):
        assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE
    fb = [r for r in caplog.records
          if "폴백" in r.getMessage() or "days_held_fallback" in r.getMessage()]
    assert len(fb) <= 1, f"폴백 로그 틱 폭주 — {len(fb)}건"


# ===========================================================================
# S3-10 — `_trading_days` 캐시 배선 (recompute_held_atr 가 채운다)
# ===========================================================================
async def test_s3_10_trading_days_cache_filled_by_recompute_held_atr():
    """`recompute_held_atr` 가 이미 fetch 한 일봉의 거래일을 캐시에 union 한다.

    KIS 신규 호출 0 (같은 candles 재사용) — `_breakout_high`/`_channel_low` 선례.
    """
    s = _mk()
    buy_date = D(2026, 8, 14)
    _arm(s, buy_date=buy_date)
    s._candidates.clear()                      # need_atr 경로 진입
    s._trading_days = {D(2026, 7, 31)}         # 기존 값 (와이프 금지 확인용)

    candles = [
        {"stck_bsop_date": "20260820", "stck_hgpr": "11000", "stck_lwpr": "10000",
         "stck_clpr": "10500", "acml_vol": "1000"},
        {"stck_bsop_date": "20260819", "stck_hgpr": "11000", "stck_lwpr": "10000",
         "stck_clpr": "10500", "acml_vol": "1000"},
        {"bas_dd": D(2026, 8, 18), "high_price": 11000, "low_price": 10000,
         "close_price": 10500},                # 정규화 컬럼 row 도 수용
    ]
    with patch("src.api.condition.fetch_daily_candles",
               new=AsyncMock(return_value=candles)), \
         patch("src.engine.strategies.donchian_swing.datetime") as _dtm:
        _dtm.now.return_value = _dt.datetime(2026, 8, 21, 8, 0, tzinfo=KST)
        s._apply_high_since_buy_from_candles = AsyncMock()
        await s.recompute_held_atr()

    assert {D(2026, 8, 20), D(2026, 8, 19), D(2026, 8, 18)}.issubset(s._trading_days), (
        f"거래일 캐시 미갱신 — got {sorted(s._trading_days)}"
    )
    assert D(2026, 7, 31) in s._trading_days, "캐시는 union — 기존 거래일 와이프 금지"


# ===========================================================================
# S3-11 / S3-12 — 회귀 보존
# ===========================================================================
@freeze_time("2026-08-20 10:00:00+09:00")
def test_s3_11_breakout_high_missing_still_graceful():
    """`_breakout_high` 미등록 → 시간청산 분기 진입 자체 없음 (graceful 보존)."""
    s = _mk(n_days=2)
    _cache(s, _AUG_NEXT)
    _arm(s, buy_date=D(2026, 8, 14))
    s._breakout_high.pop("005930", None)
    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE


def test_s3_12_price_above_breakout_high_never_fires():
    """현재가 ≥ 돌파선이면 보유일수와 무관하게 미발화 (AND 조건 불변)."""
    s = _mk(n_days=2)
    _cache(s, _AUG_NEXT)
    with freeze_time("2026-08-20 10:00:00+09:00"):
        _arm(s, buy_date=D(2026, 8, 10))
        assert s.check_exit_signal("005930", 11_500, 11_000) == Signal.NONE
