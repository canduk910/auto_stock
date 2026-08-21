"""사이클 223-F1/F4 Red — 거래일 캐시의 **조용한 과소 계상** + 폴백 가시성.

## F1 결함 (리뷰 MEDIUM)

S3 가 도입한 `_business_days_held` 캐시 경로:

    if cache and min(cache) <= buy_date:
        held = sum(1 for d in cache if buy_date < d <= today)
        if today > buy_date and today not in cache: held += 1
        return held, False

`+1` 은 **"캐시에 없는 날은 오늘 하나뿐"** 을 가정한다. 캐시 최신일이 D-1 이 아니면
그 가정이 깨지는데, `min(cache)` 가드는 **구간의 시작만** 보므로 못 잡고
`used_fallback=False` 로 돌아와 **로그가 한 줄도 안 남는다**.

실측 재현 (⚠️ "진실" 열은 **캐시 결손 = 스테일** 을 전제한 것 — G 에서 이 전제가
깨졌다. 결손이 휴장이었다면 그 값은 오히려 과다 계상이다):
    캐시 max=08-18 (08-19 결손) · buy=08-17 · today=08-20  →  (2, False)  스테일 가정 3
    캐시 max=08-14              · buy=08-14 · today=08-20  →  (1, False)  스테일 가정 4

두 번째는 `n_days=2` 에서 시간청산이 억제되고 방향이 S2 와 같아(둘 다 보유 연장)
겹친다. 트리거는 좁다 — `prepare` 조기 return(사이클 158/163 재발 이력) 과
`recompute_held_atr` 종목별 `except: continue` 가 **같은 부팅에서 동시에** 나야 한다.
좁지만 **무음**이고, 실패하는 날이 바로 그게 필요한 날이다 — 그래서 G 이후에도
가시성 절반은 남는다(값은 남지 않는다).

## 시정 계약 (I/O 0 유지) — ⚠️ 사이클 223 **G 에서 계상분 철회**

F1 은 갭을 weekday 로 메우는 일반화를 넣었고, 그것이 **공휴일 다음 첫 거래일마다
과다 계상**(연 12~15회 캘린더 이벤트)을 낳는다는 것이 검증에서 드러났다. 갭의 원인이
스테일인지 휴장인지는 구분 불가이고, 라이브 세션 중 `cache_max` 는 구조적으로 직전
거래일이라 **갭의 흔한 원인은 휴장** 쪽이다. → `tests/.../test_cycle223g_donchian_holiday_gap.py`

따라서 현재 계약은:

- 계상: `|{d ∈ cache : buy < d ≤ today}| + (1 if today > buy and today ∉ cache else 0)`
  — **갭 기여는 오늘 하루뿐**(오늘은 활성 세션이라 영업일 보장, 나머지 날은 판별 불가)
- 가시성: 캐시가 **직전 영업일**(today 이전 최근 weekday)까지 못 닿으면
  `used_fallback=True` → 열화가 로그로 보인다. **F1 지적의 본질은 값이 아니라 무음이었고,
  이 절반은 유지된다.**
- 남는 오차는 과소 한 방향(= 청산을 늦춘다 = 보유 연장, H-1 원칙)이며 무음이 아니다.
- hot path — `await`/DB/HTTP 추가 금지.

아래 F1-1/2/3/6 은 **값이 바뀐 것이 아니라 가정이 틀렸던** 케이스다 (G 의미 전환).

## F4 결함 (리뷰 LOW)

폴백 사실이 **시간청산이 실제 발화할 때만** 로그에 남는다. 폴백 상태에서 미발화가
계속되면 열화가 영원히 안 보인다. → `DailyEmitCap`(1회/ticker/일, KST 날짜 자기리셋
= `StrategyBase._emit_budget_clamp` 선례)으로 폴백 사용 자체를 드러낸다.
"""

from __future__ import annotations

import datetime as _dt
import logging

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit
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
    pos = Position(ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
                   strategy_id="donchian_swing", buy_date=buy_date)
    pos.high_since_buy = buy_price
    s.state.positions[ticker] = pos
    s._candidates[ticker] = {"prev_close": buy_price, "atr": 0, "ema60": 0,
                             "donchian_high": breakout_high}
    s._breakout_high[ticker] = breakout_high
    return pos


# KRX 영업일 (2026-08)
_W1 = [D(2026, 8, 10), D(2026, 8, 11), D(2026, 8, 12), D(2026, 8, 13), D(2026, 8, 14)]
_W2 = _W1 + [D(2026, 8, 17), D(2026, 8, 18), D(2026, 8, 19), D(2026, 8, 20)]


# ===========================================================================
# F1-1 / F1-2 — 실측 재현 두 케이스 (진실값 + used_fallback=True)
# ===========================================================================
def test_f1_1_cache_gap_undercounts_but_is_no_longer_silent():
    """캐시 max=08-18 (08-19 결손) · buy=08-17 · today=08-20 → (2, True).

    **G 의미 전환** — F1 은 여기서 진실 3 을 요구했다(갭을 weekday 로 메움). 그러나
    08-19 가 결손인 이유가 스테일인지 **휴장**인지는 구분 불가이고, 공휴일이었다면
    3 은 과다 계상(조기 청산)이다. 갭 기여를 오늘 하루로 한정하면 2 — 휴장이면 정확,
    스테일이면 과소(= 청산 지연 = 보유 연장, H-1 원칙).

    바뀐 것은 **값이 아니라 가정**이다. F1 이 실제로 지적한 결함은 침묵이었고,
    그 절반(`used_fallback=True`)은 그대로 남는다.
    """
    s = _mk(n_days=2)
    s._trading_days = set(_W1 + [D(2026, 8, 17), D(2026, 8, 18)])
    days, used_fallback = s._business_days_held(D(2026, 8, 17), D(2026, 8, 20))
    assert days == 2, (
        f"G: 갭(08-19)은 휴장/스테일 구분 불가 — 오늘 하루만 계상해 2 — got {days}"
    )
    assert used_fallback is True, (
        "F1(유지): 캐시가 직전 영업일(08-19)까지 못 닿으면 열화가 로그로 보여야 한다"
    )


def test_f1_2_stale_cache_underreports_but_is_visible():
    """캐시 max=08-14 · buy=08-14 · today=08-20 → (1, True). 진실은 4.

    **G 의미 전환** — F1 은 4 를 요구했다. 그러나 08-17~08-19 결손이 스테일인지
    3일 연휴인지 코드는 알 수 없다. 연휴였다면 4 는 **+3 과다 계상**이다.
    과소(1)는 청산을 늦추는 방향이고 `used_fallback=True` 로 드러나므로,
    무음(F1 이 지적한 진짜 결함)만 사라지고 위험한 방향의 오차는 만들지 않는다.
    """
    s = _mk(n_days=2)
    s._trading_days = set(_W1)
    days, used_fallback = s._business_days_held(D(2026, 8, 14), D(2026, 8, 20))
    assert days == 1, f"G: 갭 기여는 오늘 하루뿐 — got {days}"
    assert used_fallback is True, "가시성은 유지 — 과소 계상이 무음이면 안 된다"


@freeze_time("2026-08-20 10:00:00+09:00")
def test_f1_3_stale_cache_delays_exit_but_reports_it(caplog):
    """같은 상황에서 청산은 **지연**되되 그 사실이 로그로 드러난다.

    **G 의미 전환** — F1 은 여기서 STOP_LOSS 를 요구했다(스테일 가정 하 4 ≥ 2).
    갭 원인이 판별 불가인 이상 그 발화는 "연휴였다면 3영업일 조기 청산"과 같은 값이다.
    이 프로젝트는 과소(청산 지연)를 택하고 **대신 침묵하지 않는다** —
    `[days_held_fallback]` 이 남아 운영자가 캐시 열화를 보고 고칠 수 있다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    s._trading_days = set(_W1)
    _arm(s, buy_date=D(2026, 8, 14))
    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE, (
        "G: 갭을 조기 청산 방향으로 추정하지 않는다 (과다 계상 = 승자 절단)"
    )
    assert any("days_held_fallback" in r.getMessage() for r in caplog.records), (
        "F1(유지): 지연을 택하는 대신 열화 사실은 반드시 드러난다"
    )


# ===========================================================================
# F1-4 — 캐시가 직전 영업일까지 닿으면 종전대로 used_fallback=False
# ===========================================================================
@pytest.mark.parametrize(
    "cache,buy,today,expected",
    [
        # 캐시 D-1(금 08-14) · 오늘 월 08-17 → 주말 건너뛴 직전 영업일에 도달
        (_W1, D(2026, 8, 14), D(2026, 8, 17), 1),
        # 캐시 D-1(08-19) · 오늘 08-20
        (_W2[:-1], D(2026, 8, 18), D(2026, 8, 20), 2),
        # 캐시에 오늘 포함
        (_W2, D(2026, 8, 18), D(2026, 8, 20), 2),
        # 매수 당일
        (_W2, D(2026, 8, 20), D(2026, 8, 20), 0),
    ],
)
def test_f1_4_fresh_cache_keeps_no_fallback(cache, buy, today, expected):
    s = _mk()
    s._trading_days = set(cache)
    assert s._business_days_held(buy, today) == (expected, False)


def test_f1_5_holiday_gap_inside_cache_is_not_backfilled():
    """캐시 **안쪽** 휴장 갭은 캐시가 정본 — weekday 로 메우지 않는다.

    추석 휴장(10-01~10-05): 09-30 매수 → 10-06 은 1 영업일.
    (weekday 로 메우면 4 가 되어 과다 계상 = 조기 청산.)
    """
    s = _mk()
    s._trading_days = {D(2026, 9, 25), D(2026, 9, 28), D(2026, 9, 29),
                       D(2026, 9, 30), D(2026, 10, 6)}
    assert s._business_days_held(D(2026, 9, 30), D(2026, 10, 6)) == (1, False)


def test_f1_6_gap_is_not_weekday_filled():
    """캐시 최신일 이후 갭은 **메우지 않는다** — 오늘 하루만 센다.

    캐시 max=목 08-13 · buy=08-13 · today=화 08-18 → 1 (08-18), `used_fallback=True`.

    **G 의미 전환** — F1 은 3(08-14·17·18)을 요구했다. 08-14 와 08-17 이 스테일인지
    휴장인지 구분 불가이고, 둘 다 휴장이었다면 3 은 **+2 과다 계상**이다.
    (주말 제외 규칙 자체는 전면 폴백 경로에서 계속 검정된다 — `test_f1_7`/`test_f1_8`.)
    """
    s = _mk()
    s._trading_days = set(_W1[:-1])       # 08-10~08-13
    days, used_fallback = s._business_days_held(D(2026, 8, 13), D(2026, 8, 18))
    assert days == 1, f"G: 갭 미메움 — 오늘(08-18) 하나만 계상해 1 — got {days}"
    assert used_fallback is True


def test_f1_7_cache_not_reaching_buy_date_still_full_fallback():
    """`min(cache) > buy_date` 는 종전대로 순수 weekday 폴백 (S3-6 회귀)."""
    s = _mk()
    s._trading_days = {D(2026, 8, 19), D(2026, 8, 20)}
    assert s._business_days_held(D(2026, 8, 14), D(2026, 8, 20)) == (4, True)


def test_f1_8_empty_cache_still_full_fallback():
    s = _mk()
    s._trading_days = set()
    assert s._business_days_held(D(2026, 8, 14), D(2026, 8, 17)) == (1, True)


# ===========================================================================
# F4 — 폴백 가시성: 미발화 상태에서도 드러나되 폭주하지 않는다
# ===========================================================================
@freeze_time("2026-08-17 10:00:00+09:00")
def test_f4_1_fallback_visible_even_without_exit(caplog):
    """폴백 + **미발화** 틱에서도 폴백 사용 자체가 로그에 드러난다."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    s._trading_days = set()
    _arm(s, buy_date=D(2026, 8, 14))

    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE
    msgs = [r.getMessage() for r in caplog.records]
    assert any("days_held_fallback" in m for m in msgs), (
        f"F4: 미발화여도 폴백 사용이 드러나야 한다 (열화 관찰성) — got {msgs}"
    )


@freeze_time("2026-08-17 10:00:00+09:00")
def test_f4_2_fallback_log_capped_per_ticker_per_day(caplog):
    """hot path — 200틱 × 2종목이어도 종목당 1건 (DailyEmitCap 선례)."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    s._trading_days = set()
    _arm(s, ticker="005930", buy_date=D(2026, 8, 14))
    _arm(s, ticker="000660", buy_date=D(2026, 8, 14))

    for _ in range(200):
        assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE
        assert s.check_exit_signal("000660", 9_800, 9_900) == Signal.NONE

    fb = [r.getMessage() for r in caplog.records if "days_held_fallback" in r.getMessage()]
    assert len(fb) == 2, f"F4: 종목당 1회/일 cap 위반 — {len(fb)}건"
    assert any("005930" in m for m in fb) and any("000660" in m for m in fb)


def test_f4_3_fallback_cap_resets_next_day(caplog):
    """KST 날짜 자기리셋 — `_reset_daily_state` 훅 의존 금지 (선례 `_budget_clamp_day`)."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=5)          # 두 날 모두 미발화로 격리 (cap 리셋만 검정)
    s._trading_days = set()
    _arm(s, buy_date=D(2026, 8, 14))

    with freeze_time("2026-08-17 10:00:00+09:00"):
        s.check_exit_signal("005930", 9_800, 9_900)
    with freeze_time("2026-08-18 10:00:00+09:00"):
        s.check_exit_signal("005930", 9_800, 9_900)

    fb = [r.getMessage() for r in caplog.records if "days_held_fallback" in r.getMessage()]
    assert len(fb) == 2, f"F4: 날짜가 바뀌면 cap 이 리셋돼야 한다 — {len(fb)}건"


@freeze_time("2026-08-20 10:00:00+09:00")
def test_f4_4_no_fallback_log_on_cache_path(caplog):
    """캐시가 신선하면 폴백 로그 0건 (오탐 금지)."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    s._trading_days = set(_W2)
    _arm(s, buy_date=D(2026, 8, 18))

    for _ in range(20):
        s.check_exit_signal("005930", 9_800, 9_900)
    assert not [r for r in caplog.records if "days_held_fallback" in r.getMessage()]
