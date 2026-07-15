"""사이클 211 (2026-07-15) — BFB `flag_retracement_max` 0.382→0.5 완화 Red 회귀.

[배경 — Phase B funnel 병목 + 오프라인 스윕]
`_workspace/red/cycle211_bfb_flag_retracement.md`:
- BFB 폴/플래그 단계 병목. flag_retracement_max 0.382→0.5 = 폴+플래그 통과 3→10 (3.3배).
- pole_min_return DB 20→15 는 이미 지혈 (코드 default 15).
- flag_volume_ratio(0.60) 거래량 수축 안전장치는 절대 불변 (급락 되돌림 오판 방어선).

[변경 대상 — 단일 파라미터]
`bull_flag_breakout.py::DEFAULT_PARAMS["flag_retracement_max"]` 0.382 → 0.5.
검출 함수 `_detect_pole_and_flag_detailed` 의 flag_retracement 게이트
`actual_retracement > retracement_max` 가 완화되어 폴 폭의 38.2%~50% 조정 눌림도 통과.
그 외 임계(pole_min_return / flag_volume_ratio / pole_max_red_ratio) 전부 불변.

[Red 유효성 — 현재 코드(flag_retracement_max=0.382)에서]
- G-211-1 (e): DEFAULT_PARAMS["flag_retracement_max"] == 0.5 단언 (현재 0.382 → FAIL).
- G-211-2 (a, HIGH): 폴폭 45% 조정 셋업 → 0.382 은 None / 0.5 는 검출.
  DEFAULT 대조 = 현재 코드(0.382) None → FAIL.
- G-211-3 (SAFETY 불변식): 거래량 수축 미달 셋업은 retr 0.5 여도 volume_contraction 탈락
  (0.382/0.5 양쪽 PASS) + 인접 안전장치 임계 불변 (Red 아님, 회귀 가드).

freezegun 금지 (합성 candle = 시간 무관). 날짜 하드코딩 회피 (순수 시리즈).
"""

from __future__ import annotations

import pytest

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit


def _strat(params: dict | None = None) -> BullFlagBreakoutStrategy:
    return BullFlagBreakoutStrategy(
        StrategyConfig(
            strategy_id="bull_flag_breakout",
            name="눌림목 돌파",
            weight=0.0,
            params=params or {},
        )
    )


def _candle(close: int, high: int, low: int, open_: int, vol: int) -> dict:
    return {
        "stck_clpr": str(close),
        "stck_hgpr": str(high),
        "stck_lwpr": str(low),
        "stck_oprc": str(open_),
        "acml_vol": str(vol),
    }


def _flat_candle(price: int, vol: int) -> dict:
    return _candle(price, price, price, price, vol)


# ---------------------------------------------------------------------------
# 합성 빌더 — 폴 폭의 ~45% 조정 (0.382 초과 / 0.5 이내) 플래그 셋업.
#   구조 (최신순 index 0): [flag(flag_len)] + [단일 점프봉(pole_high)] + [flat pole run] + [padding].
#
#   설계 핵심 (combo 누출 방어):
#   - 폴 상승은 flag 바로 직전의 *단일 점프봉* 하나로만 발생 (pole_start→pole_high).
#     그 이전 pole run + padding 은 전부 flat(pole_start) → 조합이 점프봉을
#     flag 슬라이스로 흡수하면 남은 폴 = 전부 flat → pole_return 0% → pole_return 탈락.
#     점프봉을 흡수하지 않으면 pole_high 가 살아 retracement 게이트만 판정 → 0.382/0.5 갈림.
#   - flag 봉 high 는 pole_high 미만(돌파 아님), low = flag_low.
#     retracement = (pole_high - flag_low)/pole_width = (13,000-11,650)/3,000 = 0.45.
#   - 거래량: flag_vol(고갈) 로 volume_contraction 통과 → flag_retracement 단계에서만 갈림.
# ---------------------------------------------------------------------------
def _build_mid_retracement_flag(
    *,
    flag_len: int = 3,
    pole_start: int = 10_000,
    pole_high: int = 13_000,   # +30% 폴 (임계 15% 통과, 음봉 0)
    flag_low: int = 11_650,    # 폴폭 45% 조정 (0.382 초과 / 0.5 이내)
    pole_vol: int = 1_000_000,
    flag_vol: int = 400_000,   # 거래량 고갈 (0.4 < 0.6 수축 통과)
    pole_run: int = 4,         # 점프봉 이전 flat pole 봉 수 (흡수 시 return 0% 탈락)
    pad: int = 20,
) -> list[dict]:
    """폴 폭의 ~45% 조정 + 거래량 고갈 플래그 셋업 (combo 누출 방어).

    retracement=0.45 이므로:
    - flag_retracement_max=0.382 → 점프봉 미흡수 조합은 retracement 게이트 탈락
      (fail_stage="flag_retracement", rank 3), 점프봉 흡수 조합은 pole_return 0% 탈락
      (rank 1) → 어느 조합도 통과 못함 → None.
    - flag_retracement_max=0.5   → retracement 통과 → 거래량 수축 통과 → 검출.
    """
    candles: list[dict] = []

    # flag 구간 (최신, flag_len 봉) — 폴폭 45% 조정 + 거래량 고갈.
    for _ in range(flag_len):
        candles.append(_candle(
            close=flag_low + 300, high=pole_high - 100, low=flag_low,
            open_=flag_low + 200, vol=flag_vol,
        ))

    # 단일 점프봉 (flag 직전) — pole_start 시가에서 pole_high 로 급등 (양봉, 큰 거래량).
    candles.append(_candle(
        close=pole_high - 50, high=pole_high, low=pole_start,
        open_=pole_start + 100, vol=pole_vol,
    ))

    # flat pole run — pole_start 유지 (흡수돼도 return 0% → pole_return 탈락 유도).
    for _ in range(pole_run):
        candles.append(_flat_candle(pole_start, pole_vol))

    for _ in range(pad):
        candles.append(_flat_candle(pole_start, pole_vol))

    return candles


def _build_mid_retracement_high_volume(
    *,
    flag_len: int = 3,
    pole_start: int = 10_000,
    pole_high: int = 13_000,
    flag_low: int = 11_650,           # 폴폭 45% 조정 (0.5 통과 범위)
    pole_vol: int = 1_000_000,
    flag_high_vol: int = 1_200_000,   # 거래량 유지/증가 (수축 아님)
    pole_run: int = 4,
    pad: int = 20,
) -> list[dict]:
    """폴폭 45% 조정 (retr 0.5 통과) + 거래량 유지/증가 (하락 초입 위장).

    구조는 `_build_mid_retracement_flag` 와 동일 (단일 점프봉 + flat run) 이되,
    flag 봉 거래량만 flag_high_vol(유지/증가) 로 바꿔 volume_contraction 을 유일
    탈락 단계로 만든다. flag_avg_volume >= pole_avg × 0.60 →
    flag_volume_ratio(0.60) 안전장치가 유일 방어선임을 고정.
    """
    candles: list[dict] = []

    for _ in range(flag_len):
        candles.append(_candle(
            close=flag_low + 300, high=pole_high - 100, low=flag_low,
            open_=flag_low + 200, vol=flag_high_vol,
        ))

    candles.append(_candle(
        close=pole_high - 50, high=pole_high, low=pole_start,
        open_=pole_start + 100, vol=pole_vol,
    ))

    for _ in range(pole_run):
        candles.append(_flat_candle(pole_start, pole_vol))

    for _ in range(pad):
        candles.append(_flat_candle(pole_start, pole_vol))

    return candles


# ===========================================================================
# G-211-1 (e) — flag_retracement_max 최종값 == 0.5 (구현 후 Green)
# ===========================================================================
def test_g211_1_flag_retracement_max_is_0_5():
    """구현 후 BFB DEFAULT_PARAMS["flag_retracement_max"] == 0.5.

    Red: 현재 코드 0.382 → FAIL. Green: 완화 후 0.5.
    """
    assert BullFlagBreakoutStrategy.DEFAULT_PARAMS["flag_retracement_max"] == 0.5, (
        "사이클 211 — flag_retracement_max 0.382→0.5 완화. 현재 코드(0.382)에서는 Red."
    )


# ===========================================================================
# G-211-2 (a, HIGH) — 폴폭 45% 조정 셋업: 0.382 → None / 0.5 → 검출
# ===========================================================================
def test_g211_2_mid_retracement_detected_only_with_0_5():
    """동일 폴폭 45% 조정 시리즈: 0.382 → flag_retracement 탈락 / 0.5 → 검출.

    Red: 현재 DEFAULT_PARAMS(flag_retracement_max=0.382) → default strat 는 None → FAIL.
    Green: 완화 후 default strat(0.5) → dict.
    """
    candles = _build_mid_retracement_flag()

    # 명시 대비 — 0.382 은 45% 조정을 초과 판정 → flag_retracement 탈락.
    strat_382 = _strat({"flag_retracement_max": 0.382})
    result_382, fail_stage_382, detail_382 = strat_382._detect_pole_and_flag_detailed(candles)
    assert result_382 is None, (
        "flag_retracement_max=0.382 은 폴폭 45% 조정을 초과 판정하여 검출 실패해야 함. "
        f"실제={result_382} detail={detail_382}"
    )
    assert fail_stage_382 == "flag_retracement", (
        "0.382 에서 바인딩 단계는 flag_retracement 여야 함 (거래량 수축은 통과). "
        f"실제 fail_stage={fail_stage_382} detail={detail_382}"
    )

    # 명시 완화 — 0.5 는 45% 조정을 허용 → 검출 성공.
    strat_50 = _strat({"flag_retracement_max": 0.5})
    result_50, fail_stage_50, detail_50 = strat_50._detect_pole_and_flag_detailed(candles)
    assert result_50 is not None, (
        "flag_retracement_max=0.5 는 폴폭 45% 조정 + 거래량 고갈 셋업을 검출해야 함. "
        f"fail_stage={fail_stage_50} detail={detail_50}"
    )

    # 핵심 Red 단언 — DEFAULT (완화 채택 시 0.5) 에서 검출되어야 함.
    strat_default = _strat()
    result_default, fail_stage_d, detail_d = strat_default._detect_pole_and_flag_detailed(candles)
    assert result_default is not None, (
        "DEFAULT_PARAMS flag_retracement_max 완화(0.382→0.5) 후 폴폭 45% 조정 셋업이 "
        f"검출되어야 함. 현재 코드(0.382)에서는 Red. fail_stage={fail_stage_d} detail={detail_d}"
    )


# ===========================================================================
# G-211-3 (SAFETY 불변) — flag_volume_ratio 안전장치 유지 (0.382/0.5 양쪽 PASS)
# ===========================================================================
@pytest.mark.parametrize("retracement_max", [0.382, 0.5])
def test_g211_3_volume_contraction_still_guards(retracement_max):
    """폴폭 45% 조정 + 거래량 유지 → flag_retracement_max=0.5 여도 검출 실패.

    완화가 거래량 유지(하락 초입 위장)를 플래그로 오판하지 않음 =
    flag_volume_ratio(0.60) 안전장치가 유일 방어선임을 고정.
    0.382/0.5 양쪽 불변식 (Red 아님, 회귀 가드).
    """
    candles = _build_mid_retracement_high_volume()
    strat = _strat({"flag_retracement_max": retracement_max})
    result, fail_stage, detail = strat._detect_pole_and_flag_detailed(candles)
    assert result is None, (
        f"폴폭 45% 조정 + 거래량 유지는 검출 실패해야 함 (retracement_max={retracement_max}). "
        f"fail_stage={fail_stage} detail={detail}"
    )
    # 0.382 에서는 retracement 게이트가 먼저 막고, 0.5 에서는 volume_contraction 이 막음.
    # 완화(0.5)의 유일 방어선이 flag_volume_ratio 임을 명시.
    if retracement_max == 0.5:
        assert fail_stage == "volume_contraction", (
            "0.5 완화 시 거래량 수축 미달이 바인딩 단계여야 함 (flag_volume_ratio 안전장치). "
            f"실제 fail_stage={fail_stage} detail={detail}"
        )


def test_g211_3_flag_volume_ratio_and_pole_min_return_unchanged():
    """flag_retracement_max 외 인접 안전장치 임계 불변 (완화 범위 = 단일 파라미터)."""
    dp = BullFlagBreakoutStrategy.DEFAULT_PARAMS
    assert dp["flag_volume_ratio"] == 0.60, (
        "거래량 고갈 안전장치 flag_volume_ratio 는 절대 불변 (급락 되돌림 오판 방어선). "
        f"실제={dp['flag_volume_ratio']}"
    )
    assert dp["pole_min_return"] == 15.0, (
        f"pole_min_return 불변 (DB 20→15 지혈 = 코드 default 15 유지). 실제={dp['pole_min_return']}"
    )
    assert dp["pole_max_red_ratio"] == 0.45, (
        f"pole_max_red_ratio 불변 (사이클 48). 실제={dp['pole_max_red_ratio']}"
    )
    assert dp["flag_lookback_min"] == 2, (
        f"flag_lookback_min 불변 (사이클 198 완화 유지). 실제={dp['flag_lookback_min']}"
    )
