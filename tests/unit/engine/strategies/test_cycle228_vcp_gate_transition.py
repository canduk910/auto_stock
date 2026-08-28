"""cycle228-A (RED) — VCP 거래량 게이트 전환 + 충족 래치 + 추격 상한.

## 왜 VCP 에도 래치를 적용하는가 (자문 Q4)

반론이 있었다 — 미너비니 VCP 의 피벗 돌파는 **돌파 그 순간의 거래량 폭발이 정의의
일부**이고, 늦게 채운 거래량으로 사면 그건 VCP 가 아니다. **이 반론은 트레이딩
이론으로 옳다.**

그런데 우리 게이트는 그 검사를 **하고 있지 않다.** 현행은
`당일 누적 거래량 ≥ 20일 평균 × mult` 인데, 09:06 에 그 값은 하루의 약 2% 다.
이건 피벗 거래량 측정이 아니라 **시계 읽기**다.

⇒ "순수성을 지키자" 는 논거가 **지키려는 그 측정이 애초에 존재하지 않는다.**
래치를 거부해도 미너비니식 검증을 얻는 게 아니라 **시각 편향을 유지할 뿐**이다.
진짜 미너비니 구현에 필요한 RVOL(당일 누적 ÷ 같은 시각까지의 평년 누적)은
종목별 일중 누적 곡선 데이터가 없어 지금은 불가 — 별도 사이클 사안이다.

## BFB 와의 차이 (자문 Q4 표)

| 축 | BFB | VCP |
|---|---|---|
| 래치 무장 시점 | retention(1분) 완주 | **edge-crossing 즉시** |
| 무장 기준선 | `flag_high` | `base_high` |
| 해제선 | `flag_low` | **`base_low`** (§2 손절선 — 동형) |
| 추격 상한 | +5.0% | **+7.5%** (−7% 손절에서 도출) |

**VCP 에 retention 을 신설하지 않는다** — 그건 진입 임계 신설이고 표본 보호와
충돌한다. 무장 문턱이 BFB 보다 낮은 것은 현행 설계의 성질이지 이번 사이클이
만드는 차이가 아니다.

## ⚠️ 기대치 보정

VCP 는 오늘 후보 **0** 이다(추세 44 → 베이스 23 → pullback **1** → 거래량수축 **0**).
`[vcp_latch_armed]` 0건은 결함 신호가 아니며, VCP 배선 검증은 **단위 테스트로만**
가능하다. 그래서 이 파일이 유일한 검증 수단이다.
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

TICKER = "005930"
BASE_HIGH = 12_000
BASE_LOW = 10_500
AVG_VOLUME_20 = 300_000
THRESHOLD = 450_000          # int(300_000 × breakout_volume_mult(1.5))


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    tick_volume.reset_for_test()
    monkeypatch.setattr("src.engine.scanner.ticker_prices", {}, raising=False)
    yield
    tick_volume.reset_for_test()


def _make_strat(
    *, base_high: int = BASE_HIGH, base_low: int = BASE_LOW,
    avg_volume_20: int = AVG_VOLUME_20,
) -> VcpBreakoutStrategy:
    strat = VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.10)
    )
    strat._candidates[TICKER] = {
        "base_high": base_high,
        "base_low": base_low,
        "last_pullback_pct": 0.05,
        "atr14": 200,
        "ema50": 11_500,
        "ema150": 11_000,
        "ema200": 10_800,
        "prev_close": 11_900,
        "avg_volume_20": avg_volume_20,
    }
    return strat


def _cross(strat, price: int, *, base_high: int = BASE_HIGH) -> Signal:
    strat._prev_price[TICKER] = base_high - 100
    return strat.check_buy_signal(TICKER, price, 11_900)


def _tick(strat, price: int) -> Signal:
    return strat.check_buy_signal(TICKER, price, 11_900)


def _lines(caplog, marker: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if marker in r.getMessage()]


# ###########################################################################
# A1 — 게이트 소스 전환
# ###########################################################################

@freeze_time("2026-08-27 10:00:00")
def test_gate_when_tick_volume_sufficient_then_buy():
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    assert _cross(strat, BASE_HIGH + 100) == Signal.BUY
    assert TICKER in strat._bought_today


@freeze_time("2026-08-27 10:00:00")
def test_gate_when_ticker_prices_has_acml_vol_then_ignored():
    from src.engine import scanner as _scanner

    strat = _make_strat()
    _scanner.ticker_prices[TICKER] = {"acml_vol": THRESHOLD * 100}
    assert _cross(strat, BASE_HIGH + 100) == Signal.NONE


@freeze_time("2026-08-27 10:00:00")
def test_gate_when_no_observation_then_fail_closed_with_warning(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    strat = _make_strat()

    assert _cross(strat, BASE_HIGH + 100) == Signal.NONE

    warns = [
        r for r in caplog.records
        if "[vcp_vol_gate_no_data]" in r.getMessage() and r.levelno >= logging.WARNING
    ]
    assert len(warns) == 1, (
        f"미관측 fail-closed WARNING 부재. records="
        f"{[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )


@freeze_time("2026-08-27 10:00:00")
def test_gate_mirror_when_threshold_is_zero_then_pass():
    """A1 — VCP 거울 정합 유지: `vol_threshold <= 0` → 게이트 통과.

    현행 게이트가 `if vol_threshold > 0 and acml_vol < vol_threshold` 라
    임계 0 이면 통과시킨다. 전환 후에도 그 의미론을 보존한다.
    """
    strat = _make_strat(avg_volume_20=0)
    tick_volume.record_acml_vol(TICKER, 0)
    assert _cross(strat, BASE_HIGH + 100) == Signal.BUY


@freeze_time("2026-08-27 10:00:00")
def test_gate_mirror_zero_threshold_passes_even_without_observation():
    """A1 — 임계 0 이면 관측 자체가 무의미하므로 `no_data` fail-closed 보다 앞선다.

    현행 게이트가 `acml_vol` 을 **아예 보지 않는** 분기라 의미론 보존이 그렇게 된다.
    """
    strat = _make_strat(avg_volume_20=0)
    assert _cross(strat, BASE_HIGH + 100) == Signal.BUY


# ###########################################################################
# A3 — VCP 충족 래치 (retention 없음 = edge-crossing 즉시 무장)
# ###########################################################################

def test_vol_latch_attribute_exists():
    assert hasattr(_make_strat(), "_vol_latch")


@freeze_time("2026-08-27 09:30:00")
def test_latch_armed_on_edge_crossing_without_retention(caplog):
    """A3 — VCP 는 retention 이 없으므로 **edge-crossing 순간** 무장한다."""
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)

    assert _cross(strat, BASE_HIGH + 100) == Signal.NONE
    assert TICKER in strat._vol_latch
    assert len(_lines(caplog, "[vcp_latch_armed]")) == 1


def test_latch_fires_when_volume_crosses_later(caplog):
    """A3 — 래치 재평가로 매수 + `latch_age_sec`.

    VCP 창은 09:05~14:30 = 최대 5시간 25분으로 BFB(3h55m)보다 길다.
    """
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()

    with freeze_time("2026-08-27 09:30:00"):
        tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)
        assert _cross(strat, BASE_HIGH + 100) == Signal.NONE

    with freeze_time("2026-08-27 13:00:00"):
        tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
        assert _tick(strat, BASE_HIGH + 100) == Signal.BUY

    passes = _lines(caplog, "[vcp_vol_gate_pass]")
    assert len(passes) == 1
    assert "latch_age_sec=12600" in passes[0], f"09:30→13:00 = 12,600초: {passes[0]}"


@freeze_time("2026-08-27 10:00:00")
def test_latch_survives_retreat_below_base_high():
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)
    _cross(strat, BASE_HIGH + 100)

    mid = (BASE_LOW + BASE_HIGH) // 2
    assert _tick(strat, mid) == Signal.NONE
    assert TICKER in strat._vol_latch


@freeze_time("2026-08-27 10:00:00")
def test_latch_released_when_price_breaks_base_low(caplog):
    """A3 — 해제선은 `base_low`(§2 손절선) — BFB 의 `flag_low` 와 동형."""
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)
    _cross(strat, BASE_HIGH + 100)

    assert _tick(strat, BASE_LOW - 1) == Signal.NONE
    assert TICKER not in strat._vol_latch
    released = _lines(caplog, "[vcp_latch_released]")
    assert len(released) == 1
    assert "reason=stop_line" in released[0]


@freeze_time("2026-08-27 10:00:00")
def test_latch_does_not_buy_inside_base_even_with_huge_volume():
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)
    _cross(strat, BASE_HIGH + 100)

    tick_volume.record_acml_vol(TICKER, THRESHOLD * 100)
    assert _tick(strat, (BASE_LOW + BASE_HIGH) // 2) == Signal.NONE
    assert TICKER in strat._vol_latch


@freeze_time("2026-08-27 10:00:00")
def test_latch_requires_candidate_membership():
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)
    _cross(strat, BASE_HIGH + 100)

    strat._candidates.pop(TICKER)
    tick_volume.record_acml_vol(TICKER, THRESHOLD * 10)
    assert _tick(strat, BASE_HIGH + 100) == Signal.NONE


@freeze_time("2026-08-27 10:00:00")
def test_latch_released_when_live_levels_move_under_it():
    """자문 §Q1 "구현 시 못박을 것 2" — 명세 A3 미명시(결과 문서에 기재)."""
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)
    _cross(strat, BASE_HIGH + 100)

    strat._candidates[TICKER]["base_high"] = BASE_HIGH - 500
    tick_volume.record_acml_vol(TICKER, THRESHOLD * 10)
    assert _tick(strat, BASE_HIGH) == Signal.NONE
    assert TICKER not in strat._vol_latch


def test_latch_is_daily_scoped_by_date_key_self_reset():
    strat = _make_strat()
    with freeze_time("2026-08-27 09:30:00"):
        tick_volume.record_acml_vol(TICKER, THRESHOLD - 1)
        _cross(strat, BASE_HIGH + 100)
        assert TICKER in strat._vol_latch

    with freeze_time("2026-08-28 10:00:00"):
        tick_volume.record_acml_vol(TICKER, THRESHOLD * 10)
        assert _tick(strat, BASE_HIGH + 100) == Signal.NONE
        assert TICKER not in strat._vol_latch


# ###########################################################################
# A4 — 추격 상한 (VCP = 7.5)
# ###########################################################################

def test_extension_cap_default_is_seven_point_five():
    """A4 — VCP 손절 −7% → `entry ≤ base_high / 1.07` = +7.53% → 보수적 내림 7.5."""
    assert VcpBreakoutStrategy.DEFAULT_PARAMS["max_breakout_extension_pct"] == 7.5


@freeze_time("2026-08-27 10:00:00")
def test_extension_cap_rejects_chase_but_keeps_latch(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)

    assert _cross(strat, int(BASE_HIGH * 1.09)) == Signal.NONE
    rejects = _lines(caplog, "[vcp_vol_gate_reject]")
    assert len(rejects) == 1
    assert "reason=extension" in rejects[0]
    assert TICKER in strat._vol_latch

    assert _tick(strat, int(BASE_HIGH * 1.05)) == Signal.BUY


@freeze_time("2026-08-27 10:00:00")
def test_extension_cap_boundary_allows_within_cap():
    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    assert _cross(strat, int(BASE_HIGH * 1.07)) == Signal.BUY


@freeze_time("2026-08-27 10:00:00")
def test_extension_judged_on_current_price_not_daily_high():
    from src.engine import scanner as _scanner

    strat = _make_strat()
    tick_volume.record_acml_vol(TICKER, THRESHOLD + 1)
    _scanner.ticker_prices[TICKER] = {
        "stck_hgpr": int(BASE_HIGH * 1.12),
        "high_price": int(BASE_HIGH * 1.12),
        "current_price": int(BASE_HIGH * 1.02),
    }
    assert _cross(strat, int(BASE_HIGH * 1.02)) == Signal.BUY


# ###########################################################################
# A4 — 부팅 불변식
# ###########################################################################

def test_extension_cap_invariant_helper_exists():
    assert hasattr(_make_strat(), "_check_extension_cap_invariant")


def test_extension_cap_invariant_silent_when_satisfied(caplog):
    """`1.075 × 0.93 = 0.99975 ≤ 1.0` → 경고 없음."""
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    strat = _make_strat()
    strat._check_extension_cap_invariant()
    assert _lines(caplog, "[extension_cap_invariant]") == []


def test_extension_cap_invariant_warns_when_ai_widens_stop(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    strat = _make_strat()
    strat.config.params["stop_loss_rate"] = -14.0
    strat._check_extension_cap_invariant()

    warns = [
        r for r in caplog.records
        if "[extension_cap_invariant]" in r.getMessage() and r.levelno >= logging.WARNING
    ]
    assert len(warns) == 1


def test_extension_cap_invariant_does_not_auto_clamp():
    strat = _make_strat()
    strat.config.params["stop_loss_rate"] = -14.0
    strat._check_extension_cap_invariant()
    assert strat.config.params["max_breakout_extension_pct"] == 7.5
    assert strat.config.params["stop_loss_rate"] == -14.0
