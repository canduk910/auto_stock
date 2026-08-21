"""사이클 223-G1/G2/G4 Red — 캐시 분기의 주말 `today` 과다 계상 + 플래그 거짓 음성 + 폴백 로그 사각.

## G1 (MEDIUM) — 한 함수의 두 경로가 서로 다른 달력을 쓴다

`_business_days_held` 의 캐시 분기는 갭 기여를 **무조건** 더한다:

    if today > buy_date and today not in cache: held += 1

반면 바로 아래 전면 폴백 분기는 `if cursor.weekday() < 5` 로 주말을 배제한다.
즉 **같은 입력에 두 경로가 다른 값**을 낸다:

    buy=금 08-14, today=토 08-15  →  캐시 (1, False)   폴백 (0, True)   진실 0
    buy=목 08-13, today=일 08-16  →  캐시 (2, False)   폴백 (1, True)   진실 1

G 는 "오늘은 활성 세션 = 영업일 보장"을 근거로 갭을 오늘 하루로 한정했는데,
그 전제가 깨지는 실제 경로가 있다:

- `routes/trading.py` 의 `POST /api/trading/start` · `/restart` 에 휴장·주말 가드가
  없다 (`run_daily` 의 skip 은 자동 경로 전용). 수동 시작하면 `_swing_rest_poll_loop`
  가 `datetime.now().time()` 만 보고 날짜는 안 봐서 주말에도 돈다.
- `scheduler.py` 의 `except Exception: "휴장일 체크 실패 — 영업일로 가정하고 진행"`
  fail-open. fail-open 자체는 정당하나 G 산식이 그것을 계상 오류로 증폭한다.

방향이 **과다 계상 = 조기 청산**이고 `used_fallback=False` 라 **무음**이다 — F1 지적의
본질(무음)을 G 가 `today` 축으로 되살린 꼴. `n_days=2` 면 주말 첫 틱에 발화한다.

시정: 캐시 분기 조건에 `and today.weekday() < 5` → 두 경로의 달력이 일치한다.
(평일 공휴일은 달력 없이 불가 → G2 에서 docstring 을 "보장"에서 "가정"으로 낮춘다.)

## G2 (MEDIUM) — `_prev_weekday` docstring 의 "한 방향으로만 틀린다" 가 거짓

docstring 은 오탐(false positive)만 인정하는데 **거짓 음성**이 실재한다:

- 평일 공휴일 `today` → `cache_max == _prev_weekday(today)` → 플래그 **False** 인데
  갭 보정 `+1` 이 휴장일을 세어 값이 과다
- 16:20 저녁 funnel prepare 가 오늘 봉을 캐시에 넣으므로 15:40~20:00 구간엔
  `cache_max == today` → 캐시 **중간 결손**이 있어도 플래그 False (조용한 과소)

## G4 (LOW-MED) — 폴백 로그가 최악 상태에서 정확히 침묵

`_emit_days_held_fallback` 호출부가 `if breakout_high > 0 and pos.buy_date:` **안**이라
`재시작 + _breakout_high 미복구 + 빈 캐시` = 관측이 가장 필요한 상태에서 로그가 0건.
S2 의 길이 가드 강화(`period` → `period+1`)가 `_breakout_high` 미복구 확률을 올렸다.
"""

from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path

import pytest
from freezegun import freeze_time

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit
_LOGGER = "src.engine.strategies.donchian_swing"
D = _dt.date

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DONCHIAN = _REPO_ROOT / "src" / "engine" / "strategies" / "donchian_swing.py"


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
    if breakout_high:
        s._breakout_high[ticker] = breakout_high
    return pos


# 2026-08 달력: 10(월) 11(화) 12(수) 13(목) 14(금) 15(토) 16(일) / 17(월) … 21(금)
_W1 = [D(2026, 8, 10), D(2026, 8, 11), D(2026, 8, 12), D(2026, 8, 13), D(2026, 8, 14)]
_SAT, _SUN = D(2026, 8, 15), D(2026, 8, 16)


# ===========================================================================
# G1-1 ~ G1-3 — 주말 `today`: 캐시 경로가 폴백 경로와 **같은 값**을 낸다
# ===========================================================================
@pytest.mark.parametrize(
    "buy,today,expected",
    [
        (D(2026, 8, 14), _SAT, 0),   # 금 매수 → 토: 경과 영업일 0
        (D(2026, 8, 13), _SAT, 1),   # 목 매수 → 토: 08-14 하나
        (D(2026, 8, 13), _SUN, 1),   # 목 매수 → 일: 08-14 하나
        (D(2026, 8, 14), _SUN, 0),   # 금 매수 → 일: 0
    ],
)
def test_g1_1_weekend_today_is_not_counted_on_cache_path(buy, today, expected):
    """캐시 분기가 주말 `today` 를 영업일로 세면 안 된다 (과다 계상 = 조기 청산)."""
    s = _mk()
    s._trading_days = set(_W1)
    days, _fb = s._business_days_held(buy, today)
    assert days == expected, (
        f"G1: 주말 today({today:%a})를 캐시 분기가 세고 있다 — 진실 {expected}, got {days}"
    )


@pytest.mark.parametrize("buy,today", [
    (D(2026, 8, 14), _SAT), (D(2026, 8, 13), _SAT), (D(2026, 8, 13), _SUN),
])
def test_g1_2_cache_path_and_fallback_path_agree_on_weekend(buy, today):
    """한 함수의 두 경로가 **같은 달력**을 쓴다 — 주말에서 값이 갈리면 안 된다.

    캐시 경로 = 캐시가 매수일에 닿을 때 / 폴백 경로 = 빈 캐시.
    """
    cached = _mk()
    cached._trading_days = set(_W1)
    fallback = _mk()
    fallback._trading_days = set()

    cached_days, _ = cached._business_days_held(buy, today)
    fb_days, fb_flag = fallback._business_days_held(buy, today)
    assert fb_flag is True, "폴백 경로 전제 확인 (탐지기 self-test)"
    assert cached_days == fb_days, (
        f"G1: 두 경로가 다른 달력을 쓴다 — 캐시 {cached_days} vs 폴백 {fb_days}"
    )


@freeze_time("2026-08-15 10:00:00+09:00")
def test_g1_3_no_early_time_exit_on_saturday_tick():
    """수동 `/api/trading/start` 로 토요일에 폴이 돌아도 시간청산이 앞당겨지지 않는다.

    buy=금 08-14 · n_days=2 → 진실 0영업일. 캐시 분기가 `+1` 하면 1, 그리고 주말이
    이틀이라 일요일엔 2 = **실거래 0일 만에 청산 자격**.
    """
    s = _mk(n_days=1)
    s._trading_days = set(_W1)
    _arm(s, buy_date=D(2026, 8, 14))
    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE, (
        "G1: 토요일 틱이 시간청산을 발화시키면 안 된다 (진실 0영업일)"
    )


# ===========================================================================
# G1-4 — 평일 `today` 회귀 0
# ===========================================================================
@pytest.mark.parametrize(
    "cache,buy,today,expected,flag",
    [
        (_W1, D(2026, 8, 14), D(2026, 8, 17), 1, False),          # 캐시 D-1 · 월
        (_W1, D(2026, 8, 10), D(2026, 8, 14), 4, False),          # 캐시가 오늘 포함
        (_W1[:-1], D(2026, 8, 10), D(2026, 8, 17), 4, True),      # 공휴일(08-14) 직후
        (_W1, D(2026, 8, 14), D(2026, 8, 20), 1, True),           # 스테일 (과소·가시)
    ],
)
def test_g1_4_weekday_today_unchanged(cache, buy, today, expected, flag):
    s = _mk()
    s._trading_days = set(cache)
    assert s._business_days_held(buy, today) == (expected, flag)


# ===========================================================================
# G2 — `_prev_weekday` docstring 이 **거짓 음성**을 인정한다
# ===========================================================================
def test_g2_1_prev_weekday_docstring_admits_false_negative():
    """"한 방향으로만 틀린다" = 거짓. 오탐과 거짓 음성을 **둘 다** 적어야 한다."""
    doc = DonchianSwingStrategy._prev_weekday.__doc__ or ""
    assert "한 방향으로만 틀린다" not in doc, (
        "G2: 거짓 음성이 실재하므로 '한 방향으로만 틀린다' 는 유지 불가"
    )
    assert "거짓 음성" in doc, "G2: 거짓 음성(false negative) 경로를 명시해야 한다"
    assert "공휴일" in doc, "G2: 평일 공휴일 today 거짓 음성 경로 명시 의무"
    assert "prepare" in doc, (
        "G2: 저녁 prepare 가 오늘 봉을 캐시에 넣어 `cache_max == today` 가 되는 "
        "거짓 음성 경로(15:40~20:00) 명시 의무"
    )
    assert "오탐" in doc, "G2: 기존 오탐(연 12~15회) 서술은 유지"


def test_g2_2_false_negative_evening_cache_gap_is_silent():
    """저녁 prepare 후 `cache_max == today` → 중간 결손이 있어도 플래그 False.

    캐시 = 08-10~08-14 + 08-20 (08-17·18·19 결손) · buy=08-14 · today=08-20.
    `_prev_weekday(08-20)=08-19 < cache_max(08-20)` 이라 플래그가 안 선다.
    값은 1 (진실 4) = 과소 계상 = 보유 연장(H-1 원칙, 안전 방향)이나 **무음**이다.
    """
    s = _mk()
    s._trading_days = set(_W1) | {D(2026, 8, 20)}
    days, used_fallback = s._business_days_held(D(2026, 8, 14), D(2026, 8, 20))
    assert (days, used_fallback) == (1, False), (
        f"G2: 거짓 음성 실증 — got ({days}, {used_fallback})"
    )


def test_g2_3_false_negative_weekday_holiday_today_is_silent():
    """평일 공휴일 `today` → `cache_max == _prev_weekday(today)` → 플래그 False.

    캐시 max=금 08-14 · today=월 08-17 이 **휴장**이라면 진실 0인데 갭 보정이 1.
    달력이 없어 코드로는 못 가르는 잔여 오차 — docstring 이 방향(과다)을 밝혀야 한다.
    """
    s = _mk()
    s._trading_days = set(_W1)
    days, used_fallback = s._business_days_held(D(2026, 8, 14), D(2026, 8, 17))
    assert used_fallback is False
    assert days == 1
    doc = DonchianSwingStrategy._business_days_held.__doc__ or ""
    assert "영업일임은 보장" not in doc, (
        "G2: `_business_days_held` docstring 은 '오늘=영업일' 을 **보장**으로 단언할 수 "
        "없다 — 수동 `/api/trading/start` 와 휴장체크 fail-open 이 전제를 깬다"
    )
    assert "가정" in doc and "과다" in doc, (
        "G2: 전제를 **가정**으로 낮추고 깨질 때의 방향(과다 = 조기 청산)을 밝혀야 한다"
    )


# ===========================================================================
# G4 — 최악 상태(재시작 + `_breakout_high` 미복구 + 빈 캐시)에서 폴백 로그가 남는다
# ===========================================================================
@freeze_time("2026-08-20 10:00:00+09:00")
def test_g4_1_fallback_log_emitted_when_breakout_high_unrecovered(caplog):
    """관측이 가장 필요한 상태 = 로그 0건 이던 사각."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    s._trading_days = set()                       # 전면 폴백
    _arm(s, buy_date=D(2026, 8, 14), breakout_high=0)   # 재시작 후 미복구
    assert "005930" not in s._breakout_high, "탐지기 self-test — 미복구 상태 전제"

    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE
    assert any("days_held_fallback" in r.getMessage() for r in caplog.records), (
        "G4: `_breakout_high` 미복구 + 빈 캐시 = 최악 상태에서 로그가 침묵하면 안 된다"
    )


@freeze_time("2026-08-20 10:00:00+09:00")
def test_g4_2_fallback_log_exposes_breakout_high_state(caplog):
    """로그가 `breakout_high` 를 실어 '시간청산이 무장돼 있는가' 를 가른다."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    s._trading_days = set()
    _arm(s, buy_date=D(2026, 8, 14), breakout_high=0)
    s.check_exit_signal("005930", 9_800, 9_900)
    fb = [r.getMessage() for r in caplog.records if "days_held_fallback" in r.getMessage()]
    assert fb, "폴백 로그 부재"
    assert "breakout_high=0" in fb[0], (
        f"G4: 미복구(0) 와 무장(>0) 을 구분할 단서가 없다 — got {fb[0]}"
    )


@freeze_time("2026-08-20 10:00:00+09:00")
def test_g4_3_unrecovered_state_still_capped_per_ticker_per_day(caplog):
    """hoist 해도 `DailyEmitCap` 1회/ticker/일 계약은 그대로 (hot path 폭주 차단)."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    s._trading_days = set()
    _arm(s, ticker="005930", buy_date=D(2026, 8, 14), breakout_high=0)
    _arm(s, ticker="000660", buy_date=D(2026, 8, 14), breakout_high=0)
    for _ in range(200):
        s.check_exit_signal("005930", 9_800, 9_900)
        s.check_exit_signal("000660", 9_800, 9_900)
    fb = [r.getMessage() for r in caplog.records if "days_held_fallback" in r.getMessage()]
    assert len(fb) == 2, f"G4: 종목당 1회/일 cap 위반 — {len(fb)}건"


@freeze_time("2026-08-20 10:00:00+09:00")
def test_g4_4_no_emit_without_buy_date(caplog):
    """`buy_date` 자체가 없으면 경과일 개념이 없다 — 계상도 로그도 하지 않는다."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    s._trading_days = set()
    _arm(s, buy_date=None, breakout_high=0)
    s.check_exit_signal("005930", 9_800, 9_900)
    assert not [r for r in caplog.records if "days_held_fallback" in r.getMessage()]


@freeze_time("2026-08-20 10:00:00+09:00")
def test_g4_5_exit_still_requires_breakout_high(caplog):
    """관측 hoist 가 **청산 조건을 넓히면 안 된다** — 미복구면 여전히 미발화."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=1)
    s._trading_days = set()
    _arm(s, buy_date=D(2026, 8, 10), breakout_high=0)
    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE, (
        "G4: `_breakout_high` 미복구 상태에서 시간청산이 발화하면 안 된다"
    )
