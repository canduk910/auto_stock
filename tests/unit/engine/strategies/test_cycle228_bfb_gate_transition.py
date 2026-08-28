"""cycle228-A (RED) — BFB 거래량 게이트 전환 + 충족 래치 + 추격 상한.

## 이 사이클이 뒤집는 것

cycle227 Stage 0 은 배관만 깔고 게이트는 유령 키(`ticker_prices["acml_vol"]`)를
그대로 읽게 두었다. 이틀 관측 결과 **`would_pass = 0/5`** — 판정 기준상
"0건 = P1-3 충족 래치 선행 필수" 에 해당한다(`_workspace/00_URGENT_WORKLIST.md`).

자문(`_workspace/domain_consult/cycle228_vol_gate_latch.md` §1)이 그 이유를 실측으로
확정했다. 관측 5건의 **당일 총거래량**을 역산했더니:

| 종목 | 관측 시각 | 관측/임계 | 당일 총량/임계 | 래치 판정 |
|---|---|---|---|---|
| **280360 롯데웰푸드** | 09:08 | **8%** | **2.26** | ✅ 매수 |
| 001450 현대해상 | 10:00 | 40% | 0.93 | ❌ |
| 161890 한국콜마 | 09:26 | 25% | 0.66 | ❌ |
| 257720 실리콘투 | 09:19 | 19% | 0.60 | ❌ |

⇒ 280360 은 **당일 거래량의 3.6% 만 쌓인 상태로 심사받아 탈락**했다.
게이트가 잰 것은 그 종목의 거래량이 아니라 **시계**였다.
그리고 래치를 넣어도 나머지 4건은 여전히 탈락한다 — 하루치 거래량을 전부 써도
임계에 못 닿는다. **래치는 임계를 낮추지 않고 시각 편향만 걷어낸다.**

## 이 파일이 고정하는 계약 (명세 A1·A2·A4)

- **A1** 게이트 소스 = `tick_volume.get_observed_acml_vol` / 미관측 → **fail-closed**
- **A2** 래치 상태 기계 — 후퇴에도 유지, 해제선은 **전략 자신의 §2 손절선**(`flag_low`)
- **A4** 추격 상한 `max_breakout_extension_pct=5.0` — **`current_price` 로 판정**
  (donchian 의 `daily_high` 구현을 베끼면 `ticker_prices` 커플링이 딸려온다)

## ⚠️ 라이브 파라미터 ≠ 코드 기본값 (자문 실측 정정 1)

라이브 DB 는 `breakout_volume_mult=1.0`(코드 2.0)·`breakout_retention_minutes=1`(코드 3)
이다. 이 파일은 **코드 기본값 기준**으로 쓰고 라이브 값을 가정하지 않는다.
"""

from __future__ import annotations

import logging

import pytest
from freezegun import freeze_time

from src.engine import tick_volume
from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = pytest.mark.unit

LOGGER_NAME = "src.engine.strategies.bull_flag_breakout"

# ── 280360 롯데웰푸드 실측 (2026-08-26) ──────────────────────────────────────
TICKER = "280360"
FLAG_HIGH = 136_200
FLAG_LOW = 118_900
THRESHOLD = 37_303          # = int(flag_avg_volume × breakout_volume_mult(2.0))
FLAG_AVG_VOLUME = 18_651.5
OBSERVED_0908 = 2_990       # 09:08 관측 = 당일 총량의 3.6%
OBSERVED_1045 = 40_000      # 래치가 살아 있었다면 ≈10:45 에 임계 교차


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """관측 모듈 격리 + `ticker_prices` 빈 dict.

    ⚠️ 이 파일은 `ticker_prices` 에 `acml_vol` 을 **주입하지 않는다** — 그 손주입이
    P0-1 을 전 기간 은폐한 장치다. 게이트는 이제 `tick_volume` 만 읽어야 한다.
    """
    tick_volume.reset_for_test()
    monkeypatch.setattr("src.engine.scanner.ticker_prices", {}, raising=False)
    yield
    tick_volume.reset_for_test()


def _make_strat(
    *, retention_minutes: int = 0, flag_high: int = FLAG_HIGH, flag_low: int = FLAG_LOW,
    flag_avg_volume: float = FLAG_AVG_VOLUME,
) -> BullFlagBreakoutStrategy:
    strat = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="BFB", weight=0.15)
    )
    strat.config.params["breakout_retention_minutes"] = retention_minutes
    strat._candidates[TICKER] = {
        "pole_start": 100_000,
        "pole_high": 130_000,
        "flag_high": flag_high,
        "flag_low": flag_low,
        "flag_avg_volume": flag_avg_volume,
        "pole_len": 5,
        "flag_len": 9,
        "atr14": 3_000,
        "prev_close": 133_000,
    }
    return strat


def _cross(strat, price: int, *, flag_high: int = FLAG_HIGH) -> Signal:
    """edge-crossing 을 만들어 게이트 지점까지 도달시킨다 (retention=0)."""
    strat._prev_price[TICKER] = flag_high - 100
    return strat.check_buy_signal(TICKER, price, 130_000)


def _tick(strat, price: int) -> Signal:
    """edge-crossing 없는 평범한 틱 (래치 재평가 경로용)."""
    return strat.check_buy_signal(TICKER, price, 130_000)


def _lines(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if marker in r.getMessage()]


# ###########################################################################
# A1 — 게이트 소스 전환 (ticker_prices → tick_volume)
# ###########################################################################

@freeze_time("2026-08-27 09:30:00")
def test_gate_when_tick_volume_sufficient_then_buy():
    """A1 — 실측 관측치가 임계 이상이면 **매수한다**.

    cycle227 까지는 이 시나리오가 구조적으로 `Signal.NONE` 이었다
    (`ticker_prices["acml_vol"]` 대입부가 전 소스에 없어 항상 0).
    """
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)

    assert _cross(strat, FLAG_HIGH + 100) == Signal.BUY, (
        "tick_volume 관측치가 임계를 넘었는데 매수하지 않았다 — 게이트가 아직 "
        "유령 키(ticker_prices)를 읽고 있다"
    )
    assert TICKER in strat._bought_today


@freeze_time("2026-08-27 09:30:00")
def test_gate_when_ticker_prices_has_acml_vol_then_ignored():
    """A1 — `ticker_prices` 는 더 이상 게이트 입력이 아니다.

    구 경로에 충분한 값을 넣어도 매수하면 안 된다(= 소스가 안 바뀐 것).
    래치는 무장돼야 한다(= 미달로 판정됐다는 증거).
    """
    from src.engine import scanner as _scanner

    strat = _make_strat()
    _scanner.ticker_prices[TICKER] = {"acml_vol": THRESHOLD * 100}
    # tick_volume 은 비어 있다 = 진짜 관측은 미수신

    assert _cross(strat, FLAG_HIGH + 100) == Signal.NONE


@freeze_time("2026-08-27 09:30:00")
def test_gate_when_no_observation_then_fail_closed_with_warning(caplog):
    """A1 — 미관측(`None`)은 **fail-closed** + `[bfb_vol_gate_no_data]` **WARNING**.

    WARNING 인 이유: `_DbLogHandler` 가 INFO 컷이라 `logger.debug` 단독이면
    `system_logs` 에 안 남고 **도입 이전 무음과 구별 불가**해진다(cycle225 교훈).
    이 결함이 전 기간 살아남은 단 하나의 이유가 *조용한 fail-closed* 였다.
    """
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    strat = _make_strat()

    assert _cross(strat, FLAG_HIGH + 100) == Signal.NONE

    warns = [
        r for r in caplog.records
        if "[bfb_vol_gate_no_data]" in r.getMessage() and r.levelno >= logging.WARNING
    ]
    assert len(warns) == 1, (
        "미관측 fail-closed 가 WARNING 흔적을 남기지 않았다 — 조용한 fail-closed 는 "
        f"이 사이클이 없애려는 바로 그 병리다. records="
        f"{[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )


@freeze_time("2026-08-27 09:30:00")
def test_gate_when_observed_zero_then_not_no_data():
    """A1 — `0`(진짜 거래량 0)과 `None`(미수신)은 계속 다른 사건이다."""
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, 0)

    assert _cross(strat, FLAG_HIGH + 100) == Signal.NONE
    assert TICKER in strat._vol_latch, (
        "관측치 0 은 '정상 미달' 이므로 래치가 무장돼야 한다 (미수신과 구별)"
    )


# ###########################################################################
# A2 — 충족 래치 상태 기계
# ###########################################################################

def test_vol_latch_attribute_exists():
    assert hasattr(_make_strat(), "_vol_latch"), "`_vol_latch` 상태 부재"


@freeze_time("2026-08-27 09:08:00")
def test_latch_armed_when_retention_complete_but_volume_short(caplog):
    """A2 — 완주 후 거래량 미달 → **래치 등록** + `[bfb_latch_armed]`.

    280360 실측: 09:08 관측 2,990 vs 임계 37,303 (8%).
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, OBSERVED_0908)

    assert _cross(strat, FLAG_HIGH + 100) == Signal.NONE
    assert TICKER in strat._vol_latch, "거래량 미달인데 래치가 무장되지 않았다"
    assert len(_lines(caplog, "[bfb_latch_armed]")) == 1
    assert TICKER not in strat._breakout_first_seen, (
        "`_breakout_first_seen` pop 은 현행 유지 계약이다 (명세 A2)"
    )


def test_latch_fires_when_volume_crosses_later_280360_regression(caplog):
    """A2 **핵심 회귀** — 280360 시나리오. 래치 없으면 영구 미매수, 있으면 매수.

    09:08 탈락(2,990 / 37,303) → 래치 유지 → 10:45 관측 40,000 → **BUY**.
    이 종목은 당일 총거래량이 임계의 2.26배였다. 09:08 심사는 그 중 3.6% 만 보고
    "거래량 없음" 이라고 판정했다 — 게이트가 잰 것은 거래량이 아니라 시계였다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()

    with freeze_time("2026-08-27 09:08:00"):
        tick_volume.record_acml_vol(TICKER, OBSERVED_0908)
        assert _cross(strat, FLAG_HIGH + 100) == Signal.NONE

    with freeze_time("2026-08-27 10:45:00"):
        tick_volume.record_acml_vol(TICKER, OBSERVED_1045)
        # edge-crossing 은 이미 소진됐다(가격이 계속 flag_high 위) — 래치가 없으면
        # `prev < flag_high <= current` 가 재성립하지 않아 영구 미매수다.
        assert _tick(strat, FLAG_HIGH + 100) == Signal.BUY, (
            "래치 재평가 경로가 없다 — 깨끗한 돌파(뚫고 안 돌아본 종목)가 "
            "재심사를 못 받아 영구 탈락하는 역선택이 그대로 남는다"
        )

    assert TICKER in strat._bought_today


def test_latch_records_latch_age_sec_on_fire(caplog):
    """A2 — 매수 시 `latch_age_sec` 동반 (자문 Q2 — N=10 후 TTL 판단 데이터).

    래치 나이는 거래량 품질의 단조 프록시다. 지금 TTL 캡을 거는 것은
    측정 전에 결론을 박는 것이라, 대신 나이를 남겨 실측으로 답한다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()

    with freeze_time("2026-08-27 09:08:00"):
        tick_volume.record_acml_vol(TICKER, OBSERVED_0908)
        _cross(strat, FLAG_HIGH + 100)
    with freeze_time("2026-08-27 10:45:00"):
        tick_volume.record_acml_vol(TICKER, OBSERVED_1045)
        _tick(strat, FLAG_HIGH + 100)

    passes = _lines(caplog, "[bfb_vol_gate_pass]")
    assert len(passes) == 1, f"매수 시 `[bfb_vol_gate_pass]` 1행이 없다: {passes}"
    assert "latch_age_sec=5820" in passes[0], (
        f"09:08→10:45 = 5,820초가 기록돼야 한다: {passes[0]}"
    )


@freeze_time("2026-08-27 09:30:00")
def test_latch_age_sec_is_zero_when_never_latched(caplog):
    """A2 — 래치 없이 즉시 통과한 매수는 `latch_age_sec=0`.

    필드를 조건부로 빼면 로그 파서가 두 형태를 다뤄야 한다 — 항상 넣는다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    _cross(strat, FLAG_HIGH + 100)

    assert "latch_age_sec=0" in _lines(caplog, "[bfb_vol_gate_pass]")[0]


def test_latch_survives_retreat_below_flag_high_001450_regression(caplog):
    """A2 — **후퇴해도 래치는 산다**. 해제선은 `flag_high` 가 아니라 `flag_low` 다.

    001450 현대해상 실측(8/26): flag_high 51,000 / flag_low 48,000 /
    당일 저가 49,200 = flag_high 대비 **−3.53%**. 1차 감지 55회.

    "즉시 해제" 안이면 래치가 당일 최대 55회 생성·소멸해 현행 진동을 답습한다.
    고정 %밴드는 1~2% 면 3.53% 하락에 뚫리고, 3.6%+ 면 flag_low(−5.9%)에 수렴해
    존재 의의가 없다 — 라이브 후보 43종목의 flag 높이 중앙값이 **15.6%** 라
    고정 밴드는 그 폭 안에서 아무 구조적 의미가 없는 임의의 선이다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat(flag_high=51_000, flag_low=48_000, flag_avg_volume=202_133.0)
    threshold = int(202_133.0 * 2.0)   # 404,266 — 로그 역산 검증치

    with freeze_time("2026-08-27 10:00:00"):
        tick_volume.record_acml_vol(TICKER, 163_258)      # 40%
        assert _cross(strat, 51_200, flag_high=51_000) == Signal.NONE
        assert TICKER in strat._vol_latch

        # 49,200 까지 후퇴 (−3.53%) — flag_low(48,000) 위
        assert _tick(strat, 49_200) == Signal.NONE
        assert TICKER in strat._vol_latch, (
            "flag_high 아래로 내려왔다고 래치를 풀면 001450 은 당일 55회 재생성된다"
        )

        # 51,500 복귀 + 거래량 여전히 미달(당일 총량 376,136 < 404,266)
        tick_volume.record_acml_vol(TICKER, 376_136)
        assert _tick(strat, 51_500) == Signal.NONE, (
            "래치가 임계를 낮추면 안 된다 — 하루치 거래량 전부로도 미달인 종목이다"
        )
        assert threshold == 404_266


@freeze_time("2026-08-27 10:00:00")
def test_latch_released_when_price_breaks_flag_low(caplog):
    """A2 — `flag_low` 이탈 = **베이스 소멸** → 래치 해제.

    돌파선 아래로 되돌아온 것은 "아직 증명 안 됨" 이고 셋업은 멀쩡하다.
    플래그 하단을 깨면 **돌파할 대상이 없어진다** — 이 전략이 이미 채택한 정의다
    (`flag_low` 이탈은 `check_exit_signal` §2 의 손절선). *들고 있으면 파는 가격* 과
    *기다리다 포기하는 가격* 이 같아야 정합적이고, 그래서 신규 파라미터가 0이다.

    차단하는 병리: 09:08 무장 → 10:00 급락으로 flag_low 붕괴 → 12:00 패닉 거래량으로
    임계 충족 + 가격 복귀 → **붕괴가 만든 거래량으로 죽은 셋업을 산다.**
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, OBSERVED_0908)
    _cross(strat, FLAG_HIGH + 100)
    assert TICKER in strat._vol_latch

    assert _tick(strat, FLAG_LOW - 1) == Signal.NONE
    assert TICKER not in strat._vol_latch, "flag_low 이탈인데 래치가 살아 있다"

    released = _lines(caplog, "[bfb_latch_released]")
    assert len(released) == 1
    assert "reason=stop_line" in released[0]

    # 해제 후에는 거래량이 충족돼도 (edge-crossing 없이는) 사지 않는다
    tick_volume.record_acml_vol(TICKER, THRESHOLD * 10)
    assert _tick(strat, FLAG_HIGH + 100) == Signal.NONE


@freeze_time("2026-08-27 10:00:00")
def test_latch_does_not_buy_inside_flag_even_with_huge_volume():
    """A2 — 래치는 **가격 조건을 우회하지 않는다**.

    래치가 기억하는 것은 "오늘 retention 을 이미 통과했다" 뿐이다.
    플래그 안에 있는 동안엔 거래량이 넘쳐도 사지 않는다.
    """
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, OBSERVED_0908)
    _cross(strat, FLAG_HIGH + 100)

    tick_volume.record_acml_vol(TICKER, THRESHOLD * 100)
    mid = (FLAG_LOW + FLAG_HIGH) // 2
    assert _tick(strat, mid) == Signal.NONE, (
        "래치 상태에서 flag_high 미만인데 매수했다 — 가격 조건 우회"
    )
    assert TICKER in strat._vol_latch, "중간 지대에서는 래치를 유지한다"


@freeze_time("2026-08-27 10:00:00")
def test_latch_requires_candidate_membership():
    """A2 — 후보 소멸 = 매수 불가(fail-closed). 현행 계약 유지."""
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, OBSERVED_0908)
    _cross(strat, FLAG_HIGH + 100)

    strat._candidates.pop(TICKER)
    tick_volume.record_acml_vol(TICKER, THRESHOLD * 10)
    assert _tick(strat, FLAG_HIGH + 100) == Signal.NONE


@freeze_time("2026-08-27 10:00:00")
def test_latch_released_when_live_levels_move_under_it(caplog):
    """A2 — 무장 당시 레벨이 라이브에서 이동하면 **래치 해제**.

    `prepare()` 는 후보가 빌 때 장중 재실행될 수 있다(`scheduler.py:2662`).
    골대가 래치 아래에서 움직이면 무장 근거가 사라진 것이므로 다시 무장해야 한다.

    ⚠️ 명세 A2 에 명시되지 않은 항목이다 — 자문 §Q1 "구현 시 못박을 것 2" 와
    tdd 권고 6 이 요구한다. 채택 여부는 team-leader 판정 사안으로 결과 문서에 기재.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, OBSERVED_0908)
    _cross(strat, FLAG_HIGH + 100)
    assert TICKER in strat._vol_latch

    strat._candidates[TICKER]["flag_high"] = FLAG_HIGH - 5_000   # 골대 이동

    tick_volume.record_acml_vol(TICKER, THRESHOLD * 10)
    assert _tick(strat, FLAG_HIGH) == Signal.NONE
    assert TICKER not in strat._vol_latch


def test_latch_is_daily_scoped_by_date_key_self_reset():
    """A2 — `_vol_latch` 는 **날짜 키 자기 리셋**(scheduler.py diff 0 설계 목표).

    ⚠️ 부수 관찰: `_prev_price` 는 현행에서 일 경계를 넘어 잔존한다(P1-3 항목 3).
    이 테스트가 통과하는 이유의 일부가 그 잔존이므로, `_prev_price` 일일 clear 를
    도입하는 사이클은 이 케이스를 함께 다시 봐야 한다(결과 문서에 기재).
    """
    strat = _make_strat()
    with freeze_time("2026-08-27 09:08:00"):
        tick_volume.record_acml_vol(TICKER, OBSERVED_0908)
        _cross(strat, FLAG_HIGH + 100)
        assert TICKER in strat._vol_latch

    with freeze_time("2026-08-28 09:30:00"):
        tick_volume.record_acml_vol(TICKER, THRESHOLD * 10)
        assert _tick(strat, FLAG_HIGH + 100) == Signal.NONE, (
            "어제 래치가 오늘 발화했다 — 래치는 일일 스코프여야 한다"
        )
        assert TICKER not in strat._vol_latch


# ###########################################################################
# A4 — 추격 상한 (매수가 보호)
# ###########################################################################

def test_extension_cap_default_is_five_percent():
    """A4 — BFB `max_breakout_extension_pct = 5.0`.

    도출: `entry ≤ flag_high / (1 + stop/100)` — 손절 −5% → +5.26% → 보수적 내림.
    트레이더 규칙 한 줄 = **"손절선이 돌파선 위로 올라가는 가격에서는 사지 않는다."**
    돌파 후 돌파선까지 되밀리는 retest 는 정상이고 건강한 움직임인데, 내 손절이
    돌파선 위에 있으면 **내 셋업의 정상 확인 과정에 털린다**. 그게 추격의 정의다.
    """
    assert BullFlagBreakoutStrategy.DEFAULT_PARAMS["max_breakout_extension_pct"] == 5.0


@freeze_time("2026-08-27 10:45:00")
def test_extension_cap_rejects_chase_but_keeps_latch(caplog):
    """A4 — 상한 초과 시 매수 거부 + `reason=extension`, **래치는 유지**.

    가격이 상한 안으로 복귀하면 그때 산다. 래치까지 풀면 되돌림 진입을 잃는다.
    280360 실측: 캡 143,010 vs 당일 고가 143,500 — 최고 490원(변동폭의 0.34%)만
    잘라낸다. 사야 할 종목을 막지 않으면서 폭주만 막는 성질이다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)

    over = int(FLAG_HIGH * 1.06)      # +6.0% > 5.0
    assert _cross(strat, over) == Signal.NONE
    rejects = _lines(caplog, "[bfb_vol_gate_reject]")
    assert len(rejects) == 1, f"추격 거부 로그가 없다: {rejects}"
    assert "reason=extension" in rejects[0]
    assert TICKER in strat._vol_latch, "추격 거부는 래치를 풀지 않는다"

    # 상한 안으로 복귀 → 매수
    assert _tick(strat, int(FLAG_HIGH * 1.04)) == Signal.BUY


@freeze_time("2026-08-27 10:45:00")
def test_extension_cap_allows_within_cap():
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    assert _cross(strat, int(FLAG_HIGH * 1.04)) == Signal.BUY


@freeze_time("2026-08-27 10:45:00")
def test_extension_judged_on_current_price_not_daily_high():
    """A4 — 판정 기준은 **`current_price`**. `daily_high` 금지.

    donchian 은 `ticker_prices` 에서 `daily_high = max(stck_hgpr, high_price, ...)` 를
    읽는다(`donchian_swing.py:1588-1595`). 그대로 이식하면 금지된 커플링이 딸려온다.
    게다가 `daily_high` 기준은 *한 번 치솟았다 돌파선으로 되돌아온* 종목을 영구
    차단하는데, 그건 **retest-and-go = 가장 좋은 진입**이다. 잘못된 방향으로 엄격하다.

    ⚠️ 여기서 `ticker_prices` 에 고가를 넣는 것은 은폐가 아니라 **비참조 실증**이다
    (게이트 입력인 `acml_vol` 주입과 목적이 정반대다).
    """
    from src.engine import scanner as _scanner

    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    _scanner.ticker_prices[TICKER] = {
        "stck_hgpr": int(FLAG_HIGH * 1.08),   # 오늘 +8% 를 스쳤다
        "high_price": int(FLAG_HIGH * 1.08),
        "current_price": int(FLAG_HIGH * 1.02),
    }

    assert _cross(strat, int(FLAG_HIGH * 1.02)) == Signal.BUY, (
        "당일 고가를 보고 막았다 — retest-and-go 진입을 영구 차단하는 방향이다"
    )


# ###########################################################################
# A4 — 부팅 불변식 WARNING (자문 충돌 항목 선택지 A)
# ###########################################################################

def test_extension_cap_invariant_helper_exists():
    """A4 — 불변식 검증은 **이름 있는 헬퍼**여야 테스트가 닿는다.

    `prepare()` 본체는 DB/KIS 를 타고 0건 시 `asyncio.sleep(30)` 재시도가 있어
    단위 테스트로 돌릴 수 없다. cycle224 가 쓴 방식(헬퍼 직접 검증 + 호출부는
    AST 가드)을 답습한다 — 호출 위치 가드는 `test_cycle228_ast_gate_guards.py`.
    """
    assert hasattr(_make_strat(), "_check_extension_cap_invariant")


def test_extension_cap_invariant_silent_when_satisfied(caplog):
    """`1.05 × 0.95 = 0.9975 ≤ 1.0` → 경고 없음."""
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    strat = _make_strat()
    strat._check_extension_cap_invariant()
    assert _lines(caplog, "[extension_cap_invariant]") == []


def test_extension_cap_invariant_warns_when_ai_widens_stop(caplog):
    """A4 — `stop_loss_rate` 는 **PARAM_RANGES 멤버**라 매일 밤 AI 가 흔들 수 있다.

    캡을 런타임에 `stop_loss_rate` 로 계산하면 AI 가 −12% 를 권고하는 순간
    추격 상한이 +13.6% 로 **조용히 3배**가 된다. 그래서 값은 리터럴로 못박고
    도출 관계만 관찰한다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    strat.config.params["stop_loss_rate"] = -12.0

    strat._check_extension_cap_invariant()

    warns = [
        r for r in caplog.records
        if "[extension_cap_invariant]" in r.getMessage() and r.levelno >= logging.WARNING
    ]
    assert len(warns) == 1, "불변식 위반이 관찰되지 않았다"


def test_extension_cap_invariant_does_not_auto_clamp():
    """A4 — **자동 보정 금지**(fail-open). 조용히 그럴듯하게 만들면 실측 근거가 사라진다."""
    strat = _make_strat()
    strat.config.params["stop_loss_rate"] = -12.0
    strat._check_extension_cap_invariant()

    assert strat.config.params["max_breakout_extension_pct"] == 5.0
    assert strat.config.params["stop_loss_rate"] == -12.0


def test_extension_cap_invariant_is_fail_open(monkeypatch):
    """관측기 자기실패가 부팅을 막으면 안 된다."""
    strat = _make_strat()
    strat.config.params["stop_loss_rate"] = "not-a-number"
    strat._check_extension_cap_invariant()   # raise 하면 여기서 터진다


# ###########################################################################
# A1 — 관측 읽기 실패 = no_data (team-leader 판정 6, cycle227
#      `test_observer_failure_when_lookup_raises_then_warning_and_evaluation
#      _survives` 의 승계)
# ###########################################################################

@freeze_time("2026-08-27 09:30:00")
def test_gate_read_failure_is_no_data_and_never_escapes(monkeypatch, caplog):
    """A1 — `get_observed_acml_vol` 이 raise 해도 예외가 새지 않는다.

    게이트 본체는 실패를 **fail-open 으로 흡수하면 안 되고**(거래량 미확인 매수 =
    이 사이클의 fail-closed 계약 위반), 미관측(no_data)과 동일하게 처리한다.
    예외가 `check_buy_signal` 밖으로 새면 on_tick 이 죽어 그 종목의 **청산 평가까지
    멈춘다**(P1-5 와 동류) — 매수 게이트의 자기실패가 매도 안전망을 훼손하면 안 된다.
    """
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    strat = _make_strat()

    def _boom(_ticker):
        raise RuntimeError("관측 모듈 자기실패 재현")

    monkeypatch.setattr("src.engine.tick_volume.get_observed_acml_vol", _boom)

    # edge-crossing 경유로 게이트에 실제 도달시킨다 (retention=0)
    strat._prev_price[TICKER] = FLAG_HIGH - 100
    sig = strat.check_buy_signal(TICKER, FLAG_HIGH + 100, 130_000)

    assert sig == Signal.NONE, "읽기 실패가 fail-open(매수)으로 새면 안 된다"
    assert strat.get_scan_stats()["vol_gate_no_data"] == 1, (
        "읽기 실패는 no_data 로 집계돼야 한다 (조용한 삼킴 금지)"
    )
    assert TICKER in strat._vol_latch, "no_data 도 래치를 무장한다 (판정 2)"
