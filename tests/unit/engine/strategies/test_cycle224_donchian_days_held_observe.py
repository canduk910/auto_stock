"""사이클 224 Red — donchian 시간청산 보유일 **상시 관측 로그** (`[days_held_observe]`).

## 왜 (사각)

사이클 223 S3 가 시간청산 `days_held` 를 달력일 → **영업일**로 바꿨는데(`18b3c81`),
그 변경이 라이브에서 무엇을 하는지 **볼 수단이 없다**. 현재 `days_held` 가 로그에
남는 경로는 둘뿐이다:

  (a) `used_fallback=True` (거래일 캐시가 직전 영업일 미도달) → `[days_held_fallback]`
  (b) 시간청산이 **실제로 발화**했을 때 → `도치안 시간 기반 청산: ...`

즉 **시간 기반 청산인데 발화할 때만 보유일이 보인다** — "얼마나 근접했나"를 영영
못 본다. 라이브 시나리오가 이 사각을 그대로 드러낸다. donchian 유일 포지션
`403870`(HPSP) = 금 2026-08-21 09:05 매수 · `breakout_fail_n_days=2`:

    월 08-24 : 영업일 1 (달력 3) → 게이트 `days_held >= n_days` 미충족 → 청산 로그 없음
               cache_max=08-21 == _prev_weekday(08-24)=08-21 → used_fallback=False
               → 폴백 로그도 없음  ⇒ **아무것도 안 찍힌다**
    화 08-25 : 영업일 2 → 게이트 열림

월요일의 무음은 "S3 가 잘 돌았다"와 "가격 조건 미충족"과 "다른 분기 선발화"를
구분하지 못한다. 이건 이번 판단용 임시방편이 아니라 **상시 관측성 결함**이다.

## 인터페이스 계약 (tdd-engineer 확정 — backend-dev 구현 대상)

1. 신규 메서드 `_emit_days_held_observation(...)` — 로그 prefix **`[days_held_observe]`**.
   `logger.info` 레벨(기존 `_emit_days_held_fallback` 선례).

2. 호출 위치 = `check_exit_signal` 안, `_business_days_held()` **직후** ·
   게이트 `if breakout_high > 0 and days_held >= n_days and ...` **보다 앞** ·
   `if pos.buy_date:` 블록 **안**(보유일 개념이 없으면 관측 대상이 아니다).
   ⇒ **게이트 충족 여부와 무관하게** 남는다.

3. **DailyEmitCap 1회/ticker/일** — 기존 `_days_held_fallback_logged` 와 **별개**
   인스턴스 필드. 날짜 키 자기리셋(`_days_held_fallback_day` 선례) — `_reset_daily_state`
   훅에 의존하지 않는다.

4. 로그 필드 (같은 한 줄에 전부):

       [days_held_observe] ticker=%s [strategy=%s] buy_date=%s
           days_held=%d calendar_days=%d n_days=%d
           breakout_high=%d current_price=%d days_ok=%s price_ok=%s

   - `days_held`    = **영업일** (S3 산출값)
   - `calendar_days`= `(today - buy_date).days` = **달력일**
     ⇒ 두 값을 한 줄에 나란히 두는 것이 이 로그의 **존재 이유**다. 월요일에
       `days_held=1 calendar_days=3` 이 찍히면 그 자체가 S3 의 직접 확인이다.
   - `breakout_high`= 0 이면 재도출 실패 = 시간청산 **무장 해제** 상태
   - `days_ok`      = `days_held >= n_days`               (보유일 조건 충족 여부)
   - `price_ok`     = `breakout_high > 0 and current_price < breakout_high`
                                                          (가격 조건 충족 여부)
     (두 조건이 **각각** 판독 가능해야 한다 — AND 결과 하나만으론 어느 쪽이
      막고 있는지 못 가린다.)
   - `strategy=` 는 선택(폴백 로그와의 서식 일관용) — 본 테스트는 강제하지 않는다.

5. **어떤 예외도 흡수** — 관측이 청산 판정을 막지 않는다(`_emit_days_held_fallback`
   의 `except Exception: pass` 선례).

6. **행위 변경 0** — `check_exit_signal` 의 반환 시그널이 어떤 입력에서도 달라지지
   않는다. hot path 라 `await`/DB/HTTP 금지, 로그 인자는 int/date 수준.

7. 기존 `_emit_days_held_fallback` 은 **무변경**. "캐시가 스테일하다"는 별개 사실이고
   사이클 223 F4/G/G1/G4 테스트가 못박고 있다. 폴백이 선 날 두 줄이 나오는 것은 정상.

## Red 유효성 (production 미변경 시점)

- OB-0 ~ OB-8, OB-11, OB-12 = FAIL (`_emit_days_held_observation` 미구현 →
  `[days_held_observe]` 로그 0건). OB-12 는 폴백 비회귀 단언(현행 PASS)과 관측 단언
  (현행 FAIL)을 한 테스트에 묶는다 — 관측 신설이 폴백을 밀어내지 않는지 같이 본다.
- OB-9 (`buy_date` 부재) · OB-10a/b (예외 흡수) · OB-13 (행위 무변경 표) = PASS
  — 구현 후에도 계속 PASS 해야 하는 가드다. OB-10 은 관측 로그가 생긴 뒤에야
  poison 이 실제로 발화하므로, Green 시점에 비로소 유효한 검증이 된다.
"""

from __future__ import annotations

import datetime as _dt
import logging

import pytest
from freezegun import freeze_time

import src.engine.strategies.donchian_swing as _mod
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_LOGGER = "src.engine.strategies.donchian_swing"
_OBS = "[days_held_observe]"
_FB = "[days_held_fallback]"
_EXIT = "도치안 시간 기반 청산"

D = _dt.date


# ===========================================================================
# rig (사이클 223 `test_cycle223g1_donchian_weekend_today.py` 패턴 재사용)
# ===========================================================================
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
    if breakout_high:
        s._breakout_high[ticker] = breakout_high
    return pos


def _cache(s, days: list[D]) -> None:
    s._trading_days = set(days)


def _lines(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if marker in r.getMessage()]


def _one(caplog, marker: str = _OBS) -> str:
    got = _lines(caplog, marker)
    assert len(got) == 1, f"{marker} 로그 1행 기대 — got {len(got)}: {got}"
    return got[0]


def _assert_tokens(line: str, *tokens: str) -> None:
    missing = [t for t in tokens if t not in line]
    assert not missing, f"관측 로그 필드 누락 {missing} — got {line!r}"


# 2026-08 달력: 17(월) 18(화) 19(수) 20(목) 21(금) / 22(토) 23(일) / 24(월) 25(화)
_W_1721 = [D(2026, 8, 17), D(2026, 8, 18), D(2026, 8, 19), D(2026, 8, 20), D(2026, 8, 21)]


# ===========================================================================
# OB-0 — 관측 emitter 자체가 존재한다 (계약 §1)
# ===========================================================================
def test_ob_0_observation_emitter_exists():
    s = _mk()
    assert callable(getattr(s, "_emit_days_held_observation", None)), (
        "계약 §1: 관측 emitter `_emit_days_held_observation` 부재"
    )


# ===========================================================================
# OB-1 (핵심) — 게이트 미충족(`days_held < n_days`)에도 로그가 남는다
# ===========================================================================
@freeze_time("2026-08-20 10:00:00+09:00")
def test_ob_1_emitted_even_when_days_gate_not_met(caplog):
    """보유 1영업일 < n_days 3 → 청산 미발화. 그래도 관측 로그는 남아야 한다.

    현행: 발화도 폴백도 없으니 `days_held` 가 **어디에도** 안 남는다 = 이 사이클의 사각.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=3)
    _cache(s, _W_1721[:3])                      # 08-17·18·19 (D-1 까지)
    _arm(s, buy_date=D(2026, 8, 19))

    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE
    assert not _lines(caplog, _EXIT), "탐지기 self-test — 게이트 미충족 전제"
    assert not _lines(caplog, _FB), "탐지기 self-test — 폴백 미사용 전제"

    line = _one(caplog)
    _assert_tokens(line, "ticker=005930", "days_held=1", "n_days=3", "days_ok=False")


# ===========================================================================
# OB-2 — 게이트 충족·청산 발화 시에도 남는다 (관측 로그 + 청산 로그 둘 다)
# ===========================================================================
@freeze_time("2026-08-21 10:00:00+09:00")
def test_ob_2_emitted_alongside_actual_exit(caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, _W_1721[:-1])                     # 08-17~08-20 (오늘 미포함)
    _arm(s, buy_date=D(2026, 8, 19))            # 08-20 + today = 2 영업일

    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.STOP_LOSS
    assert _lines(caplog, _EXIT), "청산 로그(기존 계약)가 사라지면 안 된다"

    line = _one(caplog)
    _assert_tokens(line, "days_held=2", "n_days=2", "days_ok=True", "price_ok=True")


# ===========================================================================
# OB-3 — 한 줄에 영업일과 달력일이 **둘 다** 들어 있다 (이 로그의 존재 이유)
# ===========================================================================
@freeze_time("2026-08-24 10:00:00+09:00")
def test_ob_3_single_line_carries_business_and_calendar_days(caplog):
    """금 매수 → 월: 영업일 1 · 달력 3. 두 값이 **같은 한 줄**에 있어야 대조가 된다."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, _W_1721)                          # cache_max = 08-21(금)
    _arm(s, buy_date=D(2026, 8, 21))

    s.check_exit_signal("005930", 9_800, 9_900)
    line = _one(caplog)
    _assert_tokens(line, "days_held=1", "calendar_days=3")


# ===========================================================================
# OB-4 — 403870(HPSP) 실측 재현: 월요일 무음 → 화요일 게이트 개방
# ===========================================================================
@freeze_time("2026-08-24 10:30:00+09:00")
def test_ob_4a_hpsp_monday_observed_but_not_exited(caplog):
    """금 08-21 매수 · n_days=2 · 캐시 최신 08-21 → 월 08-24 = 1영업일(달력 3).

    청산 미발화 + 폴백 미사용 = 현행에서 **완전 무음**인 바로 그 상태.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, _W_1721)
    _arm(s, ticker="403870", buy_date=D(2026, 8, 21), buy_price=30_000,
         breakout_high=33_000)

    assert s._business_days_held(D(2026, 8, 21), D(2026, 8, 24)) == (1, False), (
        "탐지기 self-test — S3 산출값(영업일 1 · 폴백 False) 전제"
    )
    assert s.check_exit_signal("403870", 29_500, 29_800) == Signal.NONE
    assert not _lines(caplog, _EXIT)
    assert not _lines(caplog, _FB)

    line = _one(caplog)
    _assert_tokens(
        line,
        "ticker=403870", "buy_date=2026-08-21",
        "days_held=1", "calendar_days=3", "n_days=2",
        "breakout_high=33000", "current_price=29500",
        "days_ok=False", "price_ok=True",
    )


@freeze_time("2026-08-25 10:30:00+09:00")
def test_ob_4b_hpsp_tuesday_gate_opens(caplog):
    """화 08-25 = 2영업일(달력 4) → 게이트 개방. 관측 로그가 그 전이를 기록한다.

    화요일 아침 prepare 가 08-24 봉을 캐시에 넣은 상태를 재현한다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, _W_1721 + [D(2026, 8, 24)])
    _arm(s, ticker="403870", buy_date=D(2026, 8, 21), buy_price=30_000,
         breakout_high=33_000)

    assert s.check_exit_signal("403870", 29_500, 29_800) == Signal.STOP_LOSS
    line = _one(caplog)
    _assert_tokens(line, "days_held=2", "calendar_days=4", "days_ok=True", "price_ok=True")


# ===========================================================================
# OB-5 / OB-6 / OB-7 — DailyEmitCap: 1회/ticker/일 · 날짜 전환 재발화 · 종목별
# ===========================================================================
@freeze_time("2026-08-24 10:30:00+09:00")
def test_ob_5_capped_once_per_ticker_per_day(caplog):
    """hot path — 같은 날 같은 종목 200틱에 1행."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, _W_1721)
    _arm(s, buy_date=D(2026, 8, 21))

    for _ in range(200):
        assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE
    assert len(_lines(caplog, _OBS)) == 1, (
        f"관측 로그 틱 폭주 — {len(_lines(caplog, _OBS))}건"
    )


def test_ob_6_reemits_on_day_change(caplog):
    """날짜가 바뀌면 재발화 — 날짜 키 자기리셋(`_reset_daily_state` 훅 비의존)."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=5)
    _cache(s, _W_1721)
    _arm(s, buy_date=D(2026, 8, 21))

    with freeze_time("2026-08-24 10:30:00+09:00"):
        for _ in range(5):
            s.check_exit_signal("005930", 9_800, 9_900)
        assert len(_lines(caplog, _OBS)) == 1

    # 화요일 아침 prepare 가 08-24(월) 봉을 캐시에 union → 보유일 1 → 2
    s._trading_days.add(D(2026, 8, 24))
    with freeze_time("2026-08-25 10:30:00+09:00"):
        for _ in range(5):
            s.check_exit_signal("005930", 9_800, 9_900)

    got = _lines(caplog, _OBS)
    assert len(got) == 2, f"날짜 전환 후 재발화 실패 — {len(got)}건: {got}"
    assert "days_held=1" in got[0] and "days_held=2" in got[1], (
        f"날짜별로 갱신된 보유일이 찍혀야 한다 — got {got}"
    )


@freeze_time("2026-08-24 10:30:00+09:00")
def test_ob_7_cap_is_per_ticker(caplog):
    """cap 은 종목별 — 두 종목이면 각각 1행."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, _W_1721)
    _arm(s, ticker="005930", buy_date=D(2026, 8, 21))
    _arm(s, ticker="000660", buy_date=D(2026, 8, 20))

    for _ in range(100):
        s.check_exit_signal("005930", 9_800, 9_900)
        s.check_exit_signal("000660", 9_800, 9_900)

    got = _lines(caplog, _OBS)
    assert len(got) == 2, f"종목별 1회/일 cap 위반 — {len(got)}건"
    assert any("ticker=005930" in m for m in got) and any("ticker=000660" in m for m in got)


# ===========================================================================
# OB-8 — `breakout_high == 0` (재도출 실패 = 시간청산 무장 해제) 에도 남는다
# ===========================================================================
@freeze_time("2026-08-24 10:30:00+09:00")
def test_ob_8_emitted_when_breakout_high_unrecovered(caplog):
    """관측이 가장 필요한 상태(재시작 + `_breakout_high` 미복구)에서 침묵 금지.

    사이클 223 G4 가 폴백 로그에 대해 세운 원칙을 관측 로그가 그대로 승계한다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, _W_1721)
    _arm(s, buy_date=D(2026, 8, 21), breakout_high=0)
    assert "005930" not in s._breakout_high, "탐지기 self-test — 미복구 상태 전제"

    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE
    line = _one(caplog)
    _assert_tokens(line, "breakout_high=0", "days_held=1", "calendar_days=3",
                   "price_ok=False")


# ===========================================================================
# OB-9 — `buy_date` 부재 시 로그하지 않는다 (경과일 개념 자체가 없다)
# ===========================================================================
@freeze_time("2026-08-24 10:30:00+09:00")
def test_ob_9_no_emit_without_buy_date(caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, _W_1721)
    _arm(s, buy_date=None)

    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE
    assert not _lines(caplog, _OBS), "`buy_date` 없이 보유일을 관측할 수 없다"


# ===========================================================================
# OB-10 — 예외 흡수 (관측이 청산 판정을 막지 않는다)
# ===========================================================================
class _PoisonLogger:
    """`[days_held_observe]` emit 만 폭발시키는 로거 래퍼 (내부 구현 비침습)."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def info(self, msg, *args, **kwargs):
        rendered = str(msg)
        if _OBS in rendered or "days_held_observe" in rendered:
            raise RuntimeError("관측 로그 폭발 (인위적)")
        return self._real.info(msg, *args, **kwargs)


@freeze_time("2026-08-21 10:00:00+09:00")
def test_ob_10a_observation_failure_does_not_block_exit(caplog, monkeypatch):
    """관측이 던져도 시간청산 STOP_LOSS 는 그대로 나온다."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, _W_1721[:-1])
    _arm(s, buy_date=D(2026, 8, 19))
    monkeypatch.setattr(_mod, "logger", _PoisonLogger(_mod.logger))

    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.STOP_LOSS, (
        "계약 §5: 관측 실패가 청산 판정을 막으면 안 된다"
    )
    assert _lines(caplog, _EXIT), "청산 로그는 계속 나와야 한다"


@freeze_time("2026-08-24 10:30:00+09:00")
def test_ob_10b_observation_failure_does_not_break_none_path(caplog, monkeypatch):
    """미발화 경로에서도 예외가 새면 안 된다 (on_tick 이 통째로 죽는다)."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, _W_1721)
    _arm(s, buy_date=D(2026, 8, 21))
    monkeypatch.setattr(_mod, "logger", _PoisonLogger(_mod.logger))

    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE


# ===========================================================================
# OB-11 — 관측 cap 은 폴백 cap 과 **별개** (계약 §3)
# ===========================================================================
@freeze_time("2026-08-24 10:30:00+09:00")
def test_ob_11_observe_cap_independent_of_fallback_cap(caplog):
    """폴백 cap 이 이미 소진된 종목이어도 관측 로그는 나온다 (필드 공유 금지)."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, [])                                # 전면 폴백
    _arm(s, buy_date=D(2026, 8, 21))
    # 사이클 258(C258-T8) — 옛 `s._days_held_fallback_day = <오늘>` 선세팅은 필드가
    # `KstDailyEmitCap` 안으로 흡수돼 죽은 속성 대입(no-op)이 됐다. 선점이 첫
    # `should_emit` 의 날짜 프라이밍에 지워지지 않는 성질은 K-13 계약
    # (`test_cycle258_kst_emit_cap.py`)이 대신 보장한다.
    s._days_held_fallback_logged.mark_emitted("005930")   # 폴백 cap 선점

    s.check_exit_signal("005930", 9_800, 9_900)
    assert not _lines(caplog, _FB), "탐지기 self-test — 폴백 cap 선점 전제"
    assert _lines(caplog, _OBS), (
        "계약 §3: 관측 cap 이 폴백 cap 과 같은 필드를 쓰면 서로를 침묵시킨다"
    )


# ===========================================================================
# OB-12 — 기존 `_emit_days_held_fallback` 비회귀 (사이클 223 F4/G4 계약 보존)
# ===========================================================================
@freeze_time("2026-08-24 10:30:00+09:00")
def test_ob_12_fallback_log_still_emitted_and_capped(caplog):
    """폴백이 선 날은 **두 줄**(서로 다른 사실)이 정상. 폴백 cap 도 그대로 1행."""
    caplog.set_level(logging.INFO, logger=_LOGGER)
    s = _mk(n_days=2)
    _cache(s, [])                                # 전면 폴백 → used_fallback=True
    _arm(s, buy_date=D(2026, 8, 21), breakout_high=0)

    for _ in range(50):
        assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE

    fb = _lines(caplog, _FB)
    assert len(fb) == 1, f"사이클 223 F4/G4 회귀 — 폴백 로그 {len(fb)}건"
    assert "breakout_high=0" in fb[0], "사이클 223 G4 계약(무장 해제 노출) 보존"
    assert len(_lines(caplog, _OBS)) == 1, "관측 로그도 1행"


# ===========================================================================
# OB-13 — 행위 무변경 (대표 입력 표: 반환 시그널이 관측 로그 도입 전과 동일)
# ===========================================================================
def _case_hard_stop():
    s = _mk(n_days=5)
    _cache(s, _W_1721[:-1])
    _arm(s, buy_date=D(2026, 8, 20))
    return s, 9_200, 9_900, Signal.STOP_LOSS      # -8% ≤ stop_loss_rate -7%


def _case_turtle_stop():
    s = _mk(n_days=5)
    _cache(s, _W_1721[:-1])
    _arm(s, buy_date=D(2026, 8, 20))
    s._entry_atr["005930"] = 500.0                # buy 10,000 - 2×500 = 9,000
    return s, 9_000, 9_900, Signal.STOP_LOSS


def _case_time_exit():
    s = _mk(n_days=2)
    _cache(s, _W_1721[:-1])
    _arm(s, buy_date=D(2026, 8, 19))              # 08-20 + today = 2 영업일
    return s, 9_800, 9_900, Signal.STOP_LOSS


def _case_channel_exit():
    s = _mk(n_days=5)
    _cache(s, _W_1721[:-1])
    _arm(s, buy_date=D(2026, 8, 20))
    s._channel_low["005930"] = 9_500
    return s, 9_400, 9_900, Signal.TRAILING_STOP


def _case_trailing():
    s = _mk(n_days=5)
    _cache(s, _W_1721[:-1])
    _arm(s, buy_date=D(2026, 8, 20))
    s._candidates["005930"]["atr"] = 300          # 10,000 - 2.0×300 = 9,400
    return s, 9_400, 9_900, Signal.TRAILING_STOP


def _case_none():
    s = _mk(n_days=5)
    _cache(s, _W_1721[:-1])
    _arm(s, buy_date=D(2026, 8, 20))
    return s, 9_800, 9_900, Signal.NONE


def _case_no_position():
    s = _mk(n_days=5)
    _cache(s, _W_1721[:-1])
    return s, 9_800, 9_900, Signal.NONE


@freeze_time("2026-08-21 10:00:00+09:00")
@pytest.mark.parametrize("builder", [
    _case_hard_stop, _case_turtle_stop, _case_time_exit, _case_channel_exit,
    _case_trailing, _case_none, _case_no_position,
], ids=["hard_stop", "turtle_stop", "time_exit", "channel_exit",
        "trailing", "none", "no_position"])
def test_ob_13_exit_signal_behavior_unchanged(builder):
    """관측 로그 도입은 순수 관찰 — 반환 시그널을 어떤 입력에서도 바꾸지 않는다."""
    s, price, open_price, expected = builder()
    assert s.check_exit_signal("005930", price, open_price) == expected


# ===========================================================================
# 사이클 224-F — 적대적 검증 후속 시정 3건
#
# 최초 구현은 관측 호출을 §2.5 시간청산 블록 안(`_business_days_held()` 직후)에
# 뒀다. 검증이 그 위치가 **목적을 무력화**함을 실증했다 — 아래 F1 참조.
# ===========================================================================

def _arm_hard_stop(s, ticker="005930", buy_date=None):
    """§1 하드손절이 **즉시** 발화하는 상태. 시간청산 블록에는 도달하지 못한다."""
    pos = _arm(s, ticker=ticker, buy_date=buy_date, buy_price=10_000,
               breakout_high=11_000)
    # entry_atr 존재 = 터틀 경로 → 손절선 = buy - stop_atr×atr = 10,000 - 2×500 = 9,000
    s._entry_atr[ticker] = 500
    s.config.params["stop_atr"] = 2.0
    return pos


def test_f1_observation_survives_hard_stop_firing_on_first_evaluation(caplog):
    """§1 하드손절이 그날 첫 평가에서 발화해도 보유일 관측은 남는다.

    **이 사이클의 목적이 걸린 계약이다.** 관측이 §1 뒤에 있으면 하드손절이 먼저
    return 해 그 종목의 그날 보유일이 **영영 기록되지 않는다**. donchian 보유가
    한 종목뿐인 날이면 사이클 224 의 관측 목적이 통째로 소멸한다.
    """
    s = _mk(n_days=2)
    _arm_hard_stop(s, buy_date=D(2026, 8, 21))
    _cache(s, _W_1721)
    with caplog.at_level(logging.INFO), freeze_time("2026-08-24 10:00:00+09:00"):
        sig = s.check_exit_signal("005930", 8_500, 8_500)   # 손절선 9,000 이탈
    assert sig is Signal.STOP_LOSS, "하드손절은 그대로 발화해야 한다(행위 무변경)"
    line = _one(caplog)
    _assert_tokens(line, "days_held=1", "calendar_days=3", "n_days=2")


def test_f1_observation_not_suppressed_forever_when_sell_is_rejected(caplog):
    """하드손절 반복 발화(매도 거부로 포지션 생존) 상황에서도 관측이 한 번은 남는다.

    NXT 매도 거부(APBK0918) 시 `_selling` 이 discard 되어 포지션이 살아남고,
    매 틱 §1 에서 return 이 반복된다. 관측이 §1 뒤였다면 **영구 억제**다.
    """
    s = _mk(n_days=2)
    _arm_hard_stop(s, buy_date=D(2026, 8, 21))
    _cache(s, _W_1721)
    with caplog.at_level(logging.INFO), freeze_time("2026-08-24 10:00:00+09:00"):
        for _ in range(5):
            assert s.check_exit_signal("005930", 8_500, 8_500) is Signal.STOP_LOSS
    assert len(_lines(caplog, _OBS)) == 1, "cap 은 여전히 하루 1행"


def test_f2_disarmed_snapshot_is_upgraded_once_breakout_high_recovers(caplog):
    """`breakout_high=0` 으로 박제되지 않는다 — 무장 성공 시 한 줄 더 남긴다.

    장중 재시작이면 포지션 복구가 `recompute_held_atr`(→`_rederive_breakout_high`)
    보다 앞선다. cap 키가 ticker 단독이면 그날 첫 호출이 `breakout_high=0` 으로
    소진돼, 수 초 뒤 재도출이 성공해도 두 번째 행이 없어 운영자는 그 종목이
    **종일 시간청산 무장 해제**였다고 오독한다.
    """
    s = _mk(n_days=2)
    _arm(s, buy_date=D(2026, 8, 21), breakout_high=0)
    s._breakout_high.pop("005930", None)          # 재도출 전 = 무장 해제
    _cache(s, _W_1721)
    with caplog.at_level(logging.INFO), freeze_time("2026-08-24 10:00:00+09:00"):
        s.check_exit_signal("005930", 9_500, 9_500)
        first = _lines(caplog, _OBS)
        assert len(first) == 1 and "breakout_high=0" in first[0]

        s._breakout_high["005930"] = 11_000        # 재도출 성공
        s.check_exit_signal("005930", 9_500, 9_500)
        both = _lines(caplog, _OBS)
        assert len(both) == 2, f"무장 전환 시 1행 추가 기대 — got {both}"
        assert "breakout_high=11000" in both[1]

        for _ in range(3):                          # 그 뒤로는 더 안 남는다
            s.check_exit_signal("005930", 9_500, 9_500)
    assert len(_lines(caplog, _OBS)) == 2, "무장/무장해제 각 1행 = 최대 2행"


def test_f3_internal_failure_leaves_a_trace_instead_of_silence(caplog):
    """관측 실패를 흡수하되 **흔적 없이** 삼키지 않는다.

    무흔적 흡수는 이 기능이 영구 침묵해도 사이클 224 **이전의 무음과 구별되지
    않는다** — 없애려던 상태로 조용히 되돌아간다. (예외 흡수 자체는 OB-10a/b 가
    이미 못박았고, 여기서 더하는 계약은 **흔적**이다.)

    emitter 를 **직접** 호출한다 — `_breakout_high` 는 §2.5 시간청산 블록에서도
    읽히므로 `check_exit_signal` 경유로 폭발시키면 try 범위 밖에서 터진다.
    """
    s = _mk(n_days=2)
    pos = _arm(s, buy_date=D(2026, 8, 21))
    _cache(s, _W_1721)

    class _Boom(dict):
        def get(self, *a, **k):
            raise RuntimeError("관측 내부 폭발")

    s._breakout_high = _Boom()
    with caplog.at_level(logging.DEBUG), freeze_time("2026-08-24 10:00:00+09:00"):
        s._emit_days_held_observation("005930", pos, 9_500)   # 예외가 새면 여기서 실패
    assert _lines(caplog, "[days_held_observe_failed]"), (
        "실패를 흡수했지만 흔적이 없다 — 영구 침묵이 사이클 224 이전과 구별되지 않는다"
    )
    assert not _lines(caplog, _OBS), "실패했는데 관측 로그가 남으면 안 된다"


def test_f1_observation_precedes_every_exit_branch_in_source():
    """소스 상 관측 호출이 **첫 return 보다 앞**이다 (F1 구조 계약).

    행위 테스트만으로는 '어쩌다 앞에 있는' 상태와 구분되지 않는다. 리팩터가
    호출을 아래로 옮기면 이 가드가 잡는다.
    """
    import ast
    import inspect
    import textwrap

    src = inspect.getsource(DonchianSwingStrategy.check_exit_signal)
    tree = ast.parse(textwrap.dedent(src))
    calls = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "_emit_days_held_observation"
    ]
    assert calls, "관측 호출이 사라졌다"
    returns = sorted(n.lineno for n in ast.walk(tree) if isinstance(n, ast.Return))
    assert len(returns) >= 5, "청산 return 이 여러 개여야 의미 있는 가드다"

    # ⚠️ 기준선은 **호출 위치와 무관하게** 정해야 한다. 한때 `exit_returns` 를
    #    "호출보다 뒤에 있는 return" 으로 정의하고 "호출이 그중 첫째보다 앞이냐" 를
    #    물었는데, 그건 정의상 항상 참이라 가드가 **공허**했다(뮤테이션 전후 모두
    #    통과). 제외 대상은 딱 하나 — `if not pos: return Signal.NONE` = 함수의
    #    **첫 return** 이고, 포지션이 없으면 관측 대상 자체가 없으므로 정당하다.
    exit_returns = returns[1:]
    assert min(calls) < min(exit_returns), (
        f"관측 호출(line {min(calls)})이 청산 return(line {min(exit_returns)}) 뒤에 있다 "
        "— 앞선 분기가 발화하면 그날 보유일이 영영 기록되지 않는다"
    )
