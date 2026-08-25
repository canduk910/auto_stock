"""cycle227 W5 (RED) — VCP 거래량 게이트 `would_pass` 관측 훅 (**행위 변경 0**).

W4(BFB)와 **의미론 동일**이다. 자문 §7 판정: 데이터 소스·fail 방향·로그 규약을
갈라놓으면 두 전략의 거래량 확인이 서로 다른 정의를 갖게 되어 비교·귀인이 불가능해진다.
갈리는 것은 *기대치와 관찰 계획* 뿐이다 —

- 실효 난이도 BFB **2.86** vs VCP **1.80** (= mult ÷ 창 마감 시각 누적비율) = 1.59배 차이.
- 표본 확보 속도도 다르다: BFB 는 후보 48·완주 21회/일이라 즉시 쌓이지만,
  VCP 는 후보가 사실상 0(추세필터 97.9% 탈락)이라 **몇 주간 한 건도 안 나올 수 있다.**
  ⇒ 관측 0건을 "시정 실패"로 오판하지 않으려면 이 비대칭을 미리 알고 있어야 한다.

## VCP 고유 계약 1건

VCP 게이트는 `if vol_threshold > 0 and acml_vol < vol_threshold` 다 —
`vol_threshold <= 0` 이면 **게이트가 통과시킨다**. 관측기는 그 거울이어야 하므로
`would_pass=True`(outcome=pass) 로 집계한다. BFB 게이트에는 `> 0` 조건이 없어
`observed >= threshold` 만으로 자연히 같은 결과가 나온다.
"""

from __future__ import annotations

import logging

import pytest
from freezegun import freeze_time

from src.engine import tick_volume
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import Signal, StrategyConfig

pytestmark = pytest.mark.unit

LOGGER_NAME = "src.engine.strategies.vcp_breakout"
MARKER = "[vcp_vol_gate_observe]"
FAIL_MARKER = "[vcp_vol_gate_observe_failed]"

TICKER = "005930"
BASE_HIGH = 12_000
AVG_VOLUME_20 = 300_000            # × breakout_volume_mult(1.5) = threshold 450,000
THRESHOLD = 450_000


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    tick_volume.reset_for_test()
    monkeypatch.setattr("src.engine.scanner.ticker_prices", {}, raising=False)
    yield
    tick_volume.reset_for_test()


def _make_strat(*, avg_volume_20: int = AVG_VOLUME_20) -> VcpBreakoutStrategy:
    strat = VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.10)
    )
    strat._candidates[TICKER] = {
        "base_high": BASE_HIGH,
        "base_low": 10_500,
        "last_pullback_pct": 0.05,
        "atr14": 200,
        "ema50": 11_500,
        "ema150": 11_000,
        "ema200": 10_800,
        "prev_close": 11_900,
        "avg_volume_20": avg_volume_20,
    }
    return strat


def _fire(strat, ticker: str = TICKER) -> Signal:
    """edge-crossing(`prev < base_high <= current`) 을 만든다."""
    strat._prev_price[ticker] = BASE_HIGH - 100
    return strat.check_buy_signal(ticker, BASE_HIGH + 100, 11_900)


def _observe_lines(caplog) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if MARKER in r.getMessage() and FAIL_MARKER not in r.getMessage()
    ]


# ===========================================================================
# W5-1 / W5-2 / W5-3 — 세 outcome
# ===========================================================================

@freeze_time("2026-08-25 10:00:00")
def test_observe_when_observed_ge_threshold_then_would_pass_true(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)

    _fire(strat)

    msg = _observe_lines(caplog)[0]
    assert f"ticker={TICKER}" in msg
    assert f"observed={THRESHOLD + 1}" in msg
    assert f"threshold={THRESHOLD}" in msg
    assert "would_pass=True" in msg


@freeze_time("2026-08-25 10:00:00")
def test_observe_when_observed_below_threshold_then_would_pass_false(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)

    _fire(strat)

    assert "would_pass=False" in _observe_lines(caplog)[0]


@freeze_time("2026-08-25 10:00:00")
def test_observe_when_no_observation_then_distinct_reason(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()

    _fire(strat)

    msg = _observe_lines(caplog)[0]
    assert "reason=no_observation" in msg
    assert "observed=0" not in msg


# ===========================================================================
# W5-x — `vol_threshold <= 0` 거울 정합 (VCP 고유)
# ===========================================================================

@freeze_time("2026-08-25 10:00:00")
def test_observe_when_threshold_is_zero_then_would_pass_true(caplog):
    """게이트가 `vol_threshold > 0` 일 때만 컷하므로, 0 이면 통과 = would_pass True.

    관측기가 이 분기를 거울로 반영하지 않으면 관측과 실제 게이트가 어긋나
    전환 판정이 틀린 표본 위에서 이뤄진다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat(avg_volume_20=0)
    tick_volume.record_acml_vol(TICKER, 0)

    _fire(strat)

    msg = _observe_lines(caplog)[0]
    assert "would_pass=True" in msg, (
        f"threshold=0 이면 게이트는 통과시킨다 — 관측기가 거울이 아니다: {msg}"
    )
    assert strat.get_scan_stats()["vol_gate_observe_pass"] == 1


# ===========================================================================
# W5-4 — 행위 변경 0 (Stage 0 봉인)
# ===========================================================================

@freeze_time("2026-08-25 10:00:00")
@pytest.mark.parametrize(
    "observed", [None, THRESHOLD - 1, THRESHOLD, THRESHOLD * 10],
    ids=["no_obs", "below", "exact", "far_above"],
)
def test_gate_still_returns_none_regardless_of_observation(observed):
    strat = _make_strat()
    if observed is not None:
        tick_volume.record_acml_vol(TICKER, observed)

    assert _fire(strat) == Signal.NONE
    assert TICKER not in strat._bought_today
    assert strat.state.buy_signals == []


# ===========================================================================
# W5-5 / W5-6 — `_scan_stats` 카운터
# ===========================================================================

def test_scan_stats_exposes_three_observe_counters_from_fresh_instance():
    stats = _make_strat().get_scan_stats()
    for key in ("vol_gate_observe_pass", "vol_gate_observe_fail", "vol_gate_observe_no_obs"):
        assert key in stats, f"`{key}` 카운터 부재"
        assert stats[key] == 0


@freeze_time("2026-08-25 10:00:00")
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
    assert stats[key] == 1, f"`{key}` 미증가: {stats}"
    for other in {
        "vol_gate_observe_pass", "vol_gate_observe_fail", "vol_gate_observe_no_obs",
    } - {key}:
        assert stats[other] == 0


# ===========================================================================
# W5-7 ~ W5-10 — cap
# ===========================================================================

@freeze_time("2026-08-25 10:00:00")
def test_cap_when_same_ticker_and_outcome_repeats_then_one_log_but_counter_grows(caplog):
    """VCP 는 edge-crossing 재트리거로 관측 이벤트가 다발 가능 → cap 필수."""
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)

    for _ in range(5):
        _fire(strat)

    assert len(_observe_lines(caplog)) == 1
    assert strat.get_scan_stats()["vol_gate_observe_pass"] == 5


@freeze_time("2026-08-25 10:00:00")
def test_cap_when_outcome_changes_then_separate_line(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()

    _fire(strat)                                        # no_obs
    tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)
    _fire(strat)                                        # fail
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    _fire(strat)                                        # pass

    lines = _observe_lines(caplog)
    assert len(lines) == 3, f"{len(lines)}행: {lines}"


@freeze_time("2026-08-25 10:00:00")
def test_cap_when_other_ticker_then_separate_line(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    other = "000660"
    strat._candidates[other] = dict(strat._candidates[TICKER])
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    tick_volume.record_acml_vol(other, THRESHOLD + 1)

    _fire(strat)
    _fire(strat, other)

    lines = _observe_lines(caplog)
    assert len(lines) == 2
    assert any(f"ticker={other}" in m for m in lines)


def test_cap_resets_on_date_change(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()

    with freeze_time("2026-08-25 10:00:00"):
        tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
        _fire(strat)
    with freeze_time("2026-08-26 10:00:00"):
        tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
        _fire(strat)

    assert len(_observe_lines(caplog)) == 2


# ===========================================================================
# W5-11 — 관측기 자기실패 흡수
# ===========================================================================

@freeze_time("2026-08-25 10:00:00")
def test_observer_failure_when_lookup_raises_then_warning_and_evaluation_survives(
    caplog, monkeypatch,
):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    strat = _make_strat()

    def _boom(_ticker):
        raise RuntimeError("관측 모듈 폭발")

    monkeypatch.setattr(tick_volume, "get_observed_acml_vol", _boom)

    assert _fire(strat) == Signal.NONE

    warns = [
        r for r in caplog.records
        if FAIL_MARKER in r.getMessage() and r.levelno >= logging.WARNING
    ]
    assert len(warns) == 1, (
        f"`{FAIL_MARKER}` WARNING 1행이 없다. "
        f"records={[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )


# ===========================================================================
# W5-12 — grep 정밀성
# ===========================================================================

@freeze_time("2026-08-25 10:00:00")
def test_log_body_does_not_contain_other_markers(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    _fire(strat)

    msg = _observe_lines(caplog)[0]
    for foreign in ("[bfb_vol_gate_observe]", "[day_high_adopted]", FAIL_MARKER):
        assert foreign not in msg, f"로그 본문에 타 마커 `{foreign}` 포함: {msg}"
