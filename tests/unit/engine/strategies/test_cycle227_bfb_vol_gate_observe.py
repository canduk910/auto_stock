"""cycle227 W4 (RED) — BFB 거래량 게이트 `would_pass` 관측 훅 (**행위 변경 0**).

## Stage 0 의 요점

배관(W1~W3)이 실측 누적거래량을 흘려도 **게이트는 이번 사이클에서 바뀌지 않는다.**
`check_buy_signal` 은 여전히 `ticker_prices["acml_vol"]`(=항상 부재)을 읽고
여전히 `Signal.NONE` 을 돌려준다. 이번에 넣는 것은 **"고쳤다면 통과했을까"** 를
로그로 남기는 관측기뿐이다.

1~2 영업일 관측 후 전환 판정(자문 §10) — 주 3건↑ = 전환 / 0건 = P1-3 래치 선행 필수 /
일 10건↑ = 스코프 불일치 재조사.

## 계약 (`_workspace/red/cycle227_acml_vol_stage0_spec.md` W4)

- 위치: retention 완주 **직후**, 기존 "거래량 컷" 블록 **직전**.
- 마커: `[bfb_vol_gate_observe] ticker=... observed=... threshold=... would_pass=...`
  / 미수신은 `[bfb_vol_gate_observe] ticker=... reason=no_observation threshold=...`
  (자문 C — 미수신과 미달을 **다른 사유 문자열**로 분리. 이 결함이 전 기간 살아남은
  이유가 정확히 *조용한 fail-closed* 였다.)
- `logger.debug` 단독 금지 — `_DbLogHandler` 가 INFO 컷이라 `system_logs` 에 안 남고
  **도입 이전 무음과 구별 불가**해진다(cycle225 교훈). INFO 로 emit.
- cap = `(ticker, outcome)` 1회/일, outcome ∈ {pass, fail, no_obs} → 최대 3행/종목/일.
  P1-3 실측(001450 한 종목이 2시간 로그의 42% 점유)이 cap 의 근거다.
- **cap 과 무관하게** `_scan_stats` 3 카운터 누적 (총량은 API 로 관측).
- 관측 블록 전체 try/except — 실패 시 `[bfb_vol_gate_observe_failed]` **WARNING 1행**
  후 기존 흐름 계속. **관측기 자기실패가 매수 평가를 죽이면 안 된다.**

## 테스트가 요구하는 구현 제약 1건

관측 함수는 **호출 시점에 해석**돼야 한다 — `tick_volume.get_observed_acml_vol(...)`
형태(모듈 참조). 모듈 상단에서 `from src.engine.tick_volume import get_observed_acml_vol`
로 이름을 당겨오면 관측기 실패 경로를 테스트로 재현할 수 없다.
같은 파일이 이미 `from src.engine.scanner import ticker_prices` 를 **함수 안**에서
하는 관행과 일치한다.
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
MARKER = "[bfb_vol_gate_observe]"
FAIL_MARKER = "[bfb_vol_gate_observe_failed]"

TICKER = "001450"
FLAG_HIGH = 12_000
FLAG_AVG_VOLUME = 500_000          # × breakout_volume_mult(2.0) = threshold 1,000,000
THRESHOLD = 1_000_000


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """관측 모듈 격리 + `ticker_prices` 빈 dict = **프로덕션 실제 상태 재현**.

    ⚠️ 이 사이클은 `ticker_prices` 에 `acml_vol` 을 손주입하는 기존 테스트 관행이
    결함을 은폐했다는 진단에서 출발한다. 신규 테스트는 어디서도 주입하지 않는다.
    """
    tick_volume.reset_for_test()
    monkeypatch.setattr("src.engine.scanner.ticker_prices", {}, raising=False)
    yield
    tick_volume.reset_for_test()


def _make_strat(retention_minutes: int = 0) -> BullFlagBreakoutStrategy:
    strat = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="BFB", weight=0.15)
    )
    strat.config.params["breakout_retention_minutes"] = retention_minutes
    strat._candidates[TICKER] = {
        "pole_start": 9_000,
        "pole_high": 11_500,
        "flag_high": FLAG_HIGH,
        "flag_low": 11_000,
        "flag_avg_volume": FLAG_AVG_VOLUME,
        "pole_len": 5,
        "flag_len": 4,
        "atr14": 300,
        "prev_close": 11_800,
    }
    return strat


def _fire(strat, *, price: int = FLAG_HIGH + 100) -> Signal:
    """edge-crossing 을 만들어 거래량 컷 지점까지 도달시킨다 (retention=0)."""
    strat._prev_price[TICKER] = FLAG_HIGH - 100
    return strat.check_buy_signal(TICKER, price, 11_500)


def _observe_lines(caplog) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if MARKER in r.getMessage() and FAIL_MARKER not in r.getMessage()
    ]


# ===========================================================================
# W4-1 / W4-2 / W4-3 — 세 outcome 이 서로 다른 로그를 낸다
# ===========================================================================

@freeze_time("2026-08-25 09:30:00")
def test_observe_when_observed_ge_threshold_then_would_pass_true(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)

    _fire(strat)

    lines = _observe_lines(caplog)
    assert len(lines) == 1, f"관측 로그 1행이 나와야 한다 — 실제 {len(lines)}행: {lines}"
    msg = lines[0]
    assert f"ticker={TICKER}" in msg
    assert f"observed={THRESHOLD + 1}" in msg
    assert f"threshold={THRESHOLD}" in msg
    assert "would_pass=True" in msg, f"통과 판정이 로그에 없다: {msg}"


@freeze_time("2026-08-25 09:30:00")
def test_observe_when_observed_below_threshold_then_would_pass_false(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)

    _fire(strat)

    msg = _observe_lines(caplog)[0]
    assert "would_pass=False" in msg
    assert "reason=no_observation" not in msg, (
        "미달을 미수신으로 표기하면 두 사유가 다시 뭉개진다 (자문 §5)"
    )


@freeze_time("2026-08-25 09:30:00")
def test_observe_when_no_observation_then_distinct_reason(caplog):
    """W4-3 — 미수신은 `reason=no_observation` 으로 **분리 표기**.

    `observed=0` 으로 뭉개면 P0 결함(미수신 = 거래량 0)을 그대로 이식하는 것이다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()

    _fire(strat)

    msg = _observe_lines(caplog)[0]
    assert "reason=no_observation" in msg, f"미수신 사유가 분리되지 않았다: {msg}"
    assert f"threshold={THRESHOLD}" in msg
    assert "observed=0" not in msg, (
        "미수신을 `observed=0` 으로 표기하면 '진짜 거래량 0' 과 구별 불가가 된다"
    )


# ===========================================================================
# W4-4 — **행위 변경 0** (Stage 0 핵심 봉인 · 보존 검증)
# ===========================================================================

@freeze_time("2026-08-25 09:30:00")
@pytest.mark.parametrize(
    "observed", [None, THRESHOLD - 1, THRESHOLD, THRESHOLD * 10],
    ids=["no_obs", "below", "exact", "far_above"],
)
def test_gate_still_returns_none_regardless_of_observation(observed):
    """W4-4 — 관측이 무엇이든 게이트 반환은 여전히 `Signal.NONE`.

    Stage 0 = 배관 + 관측만. 게이트 전환은 1~2 영업일 실측 후 **별도 사이클**이다.
    이 테스트가 깨지면 관측 훅이 매수 행위를 바꾼 것이다.
    """
    strat = _make_strat()
    if observed is not None:
        tick_volume.record_acml_vol(TICKER, observed)

    assert _fire(strat) == Signal.NONE
    assert TICKER not in strat._bought_today
    assert strat.state.buy_signals == []


# ===========================================================================
# W4-5 / W4-13 — `_scan_stats` 3 카운터
# ===========================================================================

def test_scan_stats_exposes_three_observe_counters_from_fresh_instance():
    """W4-13 — 신규 인스턴스부터 3키가 존재해야 API 가 항상 총량을 보여준다."""
    stats = _make_strat().get_scan_stats()
    for key in ("vol_gate_observe_pass", "vol_gate_observe_fail", "vol_gate_observe_no_obs"):
        assert key in stats, f"`{key}` 카운터 부재 — 총량 관측 경로가 없다"
        assert stats[key] == 0


@freeze_time("2026-08-25 09:30:00")
@pytest.mark.parametrize(
    "observed,key",
    [
        (THRESHOLD + 1, "vol_gate_observe_pass"),
        (THRESHOLD - 1, "vol_gate_observe_fail"),
        (None, "vol_gate_observe_no_obs"),
    ],
    ids=["pass", "fail", "no_obs"],
)
def test_observe_increments_matching_counter_only(observed, key):
    strat = _make_strat()
    if observed is not None:
        tick_volume.record_acml_vol(TICKER, observed)

    _fire(strat)

    stats = strat.get_scan_stats()
    assert stats[key] == 1, f"`{key}` 가 증가하지 않았다: {stats}"
    others = {
        "vol_gate_observe_pass", "vol_gate_observe_fail", "vol_gate_observe_no_obs",
    } - {key}
    for other in others:
        assert stats[other] == 0, f"`{other}` 가 잘못 증가했다: {stats}"


# ===========================================================================
# W4-6 / W4-7 / W4-8 / W4-9 — cap
# ===========================================================================

@freeze_time("2026-08-25 09:30:00")
def test_cap_when_same_ticker_and_outcome_repeats_then_one_log_but_counter_grows(caplog):
    """W4-6 — 로그는 1행으로 cap, **카운터는 계속 증가**.

    P1-3 실측: 001450 한 종목의 왕복이 2시간 로그 1,753행 중 738행을 점유했다.
    cap 이 없으면 관측기가 진단을 방해한다 — 그런데 총량은 알아야 한다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)

    for _ in range(5):
        _fire(strat)

    assert len(_observe_lines(caplog)) == 1, "cap 미작동 — 관측기가 로그를 점유한다"
    assert strat.get_scan_stats()["vol_gate_observe_pass"] == 5, (
        "cap 이 카운터까지 막으면 총량 관측이 불가능해진다"
    )


@freeze_time("2026-08-25 09:30:00")
def test_cap_when_outcome_changes_then_separate_line(caplog):
    """W4-7 — 같은 종목이라도 outcome 이 다르면 별도 cap (최대 3행/종목/일)."""
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()

    _fire(strat)                                             # no_obs
    tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)
    _fire(strat)                                             # fail
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    _fire(strat)                                             # pass

    lines = _observe_lines(caplog)
    assert len(lines) == 3, f"outcome 별 cap 이 아니다 — {len(lines)}행: {lines}"
    assert sum("reason=no_observation" in m for m in lines) == 1
    assert sum("would_pass=False" in m for m in lines) == 1
    assert sum("would_pass=True" in m for m in lines) == 1


@freeze_time("2026-08-25 09:30:00")
def test_cap_when_other_ticker_then_separate_line(caplog):
    """W4-8 — cap 키에 ticker 가 들어가야 한 종목이 다른 종목의 관측을 삼키지 않는다."""
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    other = "005930"
    strat._candidates[other] = dict(strat._candidates[TICKER])
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    tick_volume.record_acml_vol(other, THRESHOLD + 1)

    _fire(strat)
    strat._prev_price[other] = FLAG_HIGH - 100
    strat.check_buy_signal(other, FLAG_HIGH + 100, 11_500)

    lines = _observe_lines(caplog)
    assert len(lines) == 2
    assert any(f"ticker={TICKER}" in m for m in lines)
    assert any(f"ticker={other}" in m for m in lines)


def test_cap_resets_on_date_change(caplog):
    """W4-9 — cap 은 **날짜 키 자기 리셋**. `_reset_daily_state` 훅 미의존.

    (그 훅에 의존하면 scheduler 배선이 필요해지고, 이번 사이클은 scheduler diff 0 이다.)
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()

    with freeze_time("2026-08-25 09:30:00"):
        tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
        _fire(strat)
    with freeze_time("2026-08-26 09:30:00"):
        tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
        _fire(strat)

    assert len(_observe_lines(caplog)) == 2, "날짜가 바뀌면 cap 이 풀려야 한다"


# ===========================================================================
# W4-10 — 관측기 자기실패 흡수
# ===========================================================================

@freeze_time("2026-08-25 09:30:00")
def test_observer_failure_when_lookup_raises_then_warning_and_evaluation_survives(
    caplog, monkeypatch,
):
    """W4-10 — 관측기가 터져도 매수 평가는 계속된다 + **WARNING 흔적 1행**.

    cycle225 교훈: `except: pass` 무흔적 흡수는 영구 침묵이라 도입 이전 무음과
    구별 불가다. `logger.debug` 단독도 `_DbLogHandler`(INFO 컷)를 못 넘는다.
    """
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    strat = _make_strat()

    def _boom(_ticker):
        raise RuntimeError("관측 모듈 폭발")

    monkeypatch.setattr(tick_volume, "get_observed_acml_vol", _boom)

    sig = _fire(strat)   # 예외가 새면 여기서 터진다

    assert sig == Signal.NONE
    warns = [
        r for r in caplog.records
        if FAIL_MARKER in r.getMessage() and r.levelno >= logging.WARNING
    ]
    assert len(warns) == 1, (
        f"`{FAIL_MARKER}` WARNING 1행이 없다 — 무흔적 흡수는 영구 침묵이다. "
        f"records={[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )


# ===========================================================================
# W4-11 / W4-12 — grep 정밀성 · 훅 위치
# ===========================================================================

@freeze_time("2026-08-25 09:30:00")
def test_log_body_does_not_contain_other_markers(caplog):
    """W4-11 — P2-7 교훈: 로그 본문이 타 마커를 언급하면 substring grep 이 오집계한다.

    2026-08-25 에 실제로 `[day_high_scope_skip]` 4건이 114건으로 오집계됐다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    _fire(strat)

    msg = _observe_lines(caplog)[0]
    for foreign in ("[vcp_vol_gate_observe]", "[day_high_adopted]", FAIL_MARKER):
        assert foreign not in msg, f"로그 본문에 타 마커 `{foreign}` 포함: {msg}"


@freeze_time("2026-08-25 09:30:00")
def test_no_observe_log_while_retention_pending(caplog):
    """W4-12 — retention 대기 중(1차 감지)에는 관측하지 않는다.

    관측 지점은 **완주 직후**다. 대기 중에 찍으면 한 돌파가 여러 번 집계되어
    전환 판정 기준(주 3건↑ / 일 10건↑)이 왜곡된다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat(retention_minutes=3)
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)

    assert _fire(strat) == Signal.NONE
    assert TICKER in strat._breakout_first_seen
    assert _observe_lines(caplog) == [], "retention 대기 중에 관측 로그가 나왔다"
