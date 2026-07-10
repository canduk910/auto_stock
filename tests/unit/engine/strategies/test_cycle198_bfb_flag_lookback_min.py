"""사이클 198 (2026-07-09) — BFB `flag_lookback_min` 3→2 완화 Red 회귀.

[배경 — 도메인 자문 + 298종목×4일 DB 실측]
`_workspace/domain_consult/cycle198_pattern_strictness_korea.md`:
- 한국 급등주는 눌림(플래그)이 얕고 빠르다 — 상한가 익일 눌림 → 3일차 재돌파 리듬.
  flag_lookback_min=3 이면 2일 얕은 눌림을 플래그로 못 잡음 → 검출 0.
- 298종목 as-of 실측: flag_lookback_min 3→2 = 유의미 레버 (7/9 2→9, 7/7 0→2).
- flag_volume_ratio(0.60) 안전장치가 저품질(급락 되돌림) 후보를 전량 흡수 실증
  (7/8 완화 시 PASS +0, 거래량수축미달 탈락 16→33).

[변경 대상 — 단일 파라미터]
`bull_flag_breakout.py::DEFAULT_PARAMS["flag_lookback_min"]` 3 → 2.
검출 함수 `_detect_pole_and_flag_detailed` 의 flag_len 루프 `range(flag_min, flag_max+1)`
가 flag_min=2 면 2일 플래그 조합을 포함하게 됨. 그 외 임계 전부 불변.

[Red 유효성 — 현재 코드(flag_lookback_min=3)에서]
- (a) FAIL: 얕은 2일 눌림 + 거래량 고갈 셋업 → min=3 은 None (2일 플래그 미시도).
- (e) FAIL: DEFAULT_PARAMS["flag_lookback_min"] == 2 단언 (현재 3).
- (b) PASS(불변식): 2일 급락 + 거래량 유지 → min=2 여도 volume_contraction 탈락.
- (d) PASS(불변식): 인접 키(flag_volume_ratio/pole_min_return/flag_retracement_max) 불변.

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
# 합성 빌더 — flag_len 을 인자로 받아 "정확히 flag_len 일 짜리 플래그"를 만든다.
#   구조 (최신순 index 0): [flag(flag_len)] + [pole(pole_len)] + [padding].
#   pole: 가장 옛날 종가 = pole_start, 고점 = pole_high (강한 상승 + 음봉 0).
#   flag: peak 근처 소폭 조정 (flag_low) + 거래량 flag_vol.
#
# 핵심: flag 구간 봉을 flag_len 개만 만들어, 3일 플래그 조합으로는 안 잡히고
#       2일 플래그 조합에서만 셋업이 성립하도록 구성한다 (3일차부터는 pole 봉).
# ---------------------------------------------------------------------------
def _build_shallow_2day_flag(
    *,
    flag_len: int = 2,
    pole_len: int = 5,
    pole_start: int = 10_000,
    pole_high: int = 13_000,   # +30% 폴 (임계 15% 통과, 음봉 0)
    flag_low: int = 12_500,    # 얕은 조정 (retracement 통과)
    pole_vol: int = 1_000_000,
    flag_vol: int = 400_000,   # 거래량 고갈 (0.4 < 0.6 수축 통과)
    pad: int = 20,
) -> list[dict]:
    """정확히 `flag_len` 일 짜리 얕은 눌림 + 거래량 고갈 플래그 셋업.

    flag_len=2 로 만들면: 2일 플래그 조합(flag_len=2)에서만 flag 구간이 정확히
    거래량 고갈 봉들로 채워지고, 3일 플래그 조합(flag_len=3)은 3번째 봉이
    pole 고점(큰 거래량) 봉을 삼켜 → flag_avg_volume 이 올라가 수축 탈락하거나
    flag_low 가 달라져 셋업이 성립하지 않는다.
    """
    candles: list[dict] = []

    # flag 구간 (최신, flag_len 봉) — 얕은 조정 + 거래량 고갈
    for _ in range(flag_len):
        candles.append(_candle(
            close=pole_high - 200, high=pole_high - 100, low=flag_low,
            open_=pole_high - 150, vol=flag_vol,
        ))

    # pole 구간 — idx flag_len..flag_len+pole_len-1. 큰 거래량.
    for j in range(pole_len):
        is_oldest = (j == pole_len - 1)
        close = (
            pole_start
            if is_oldest
            else pole_start + (pole_high - pole_start) * (pole_len - 1 - j) // pole_len
        )
        candles.append(_candle(
            close=close,
            high=pole_high if j == 0 else close + 50,
            low=max(1, close - 50),
            open_=max(1, close - 100),  # 양봉 (음봉 0)
            vol=pole_vol,
        ))

    for _ in range(pad):
        candles.append(_flat_candle(pole_start, pole_vol))

    return candles


def _build_2day_drop_high_volume(
    *,
    pole_start: int = 10_000,
    pole_high: int = 13_000,
    pole_vol: int = 1_000_000,
    flag_high_vol: int = 1_200_000,  # 거래량 유지/증가 (수축 아님 = 하락 초입 위장)
    flag_low: int = 12_500,          # 얕은 조정 (retracement 통과 — 위장 셋업)
    pad: int = 20,
) -> list[dict]:
    """폴 직후 2일 눌림 (얕은 조정 통과) + 거래량 유지/증가 (하락 초입 위장).

    핵심: retracement(38.2%)·pole_return 은 통과하도록 얕은 조정을 유지하되,
    flag_avg_volume >= pole_avg × 0.60 (거래량 유지)라 volume_contraction 단계에서만
    탈락해야 함 = flag_volume_ratio 가 유일 방어선임을 고정 (자문 §반례 #2).
    거래량 수축이 없으면 "진짜 눌림(매물 소화)"이 아니라 하락 전환일 수 있음.
    """
    candles: list[dict] = []
    pole_len = 5

    # 2일 눌림 구간 (최신) — 얕은 조정 (good 케이스와 동일 구조) + 큰 거래량 유지
    for _ in range(2):
        candles.append(_candle(
            close=pole_high - 200, high=pole_high - 100, low=flag_low,
            open_=pole_high - 150, vol=flag_high_vol,
        ))

    # pole 구간 — 큰 거래량
    for j in range(pole_len):
        is_oldest = (j == pole_len - 1)
        close = (
            pole_start
            if is_oldest
            else pole_start + (pole_high - pole_start) * (pole_len - 1 - j) // pole_len
        )
        candles.append(_candle(
            close=close,
            high=pole_high if j == 0 else close + 50,
            low=max(1, close - 50),
            open_=max(1, close - 100),
            vol=pole_vol,
        ))

    for _ in range(pad):
        candles.append(_flat_candle(pole_start, pole_vol))

    return candles


# ===========================================================================
# (a) [핵심 완화 실증] flag_lookback_min=2 시 검출 성공 / 3 시 실패
# ===========================================================================
def test_a_shallow_2day_flag_detected_only_with_min2():
    """동일 얕은 2일 눌림 시리즈: min=3 → None (미시도) / min=2 → dict (검출).

    Red: 현재 DEFAULT_PARAMS(flag_lookback_min=3) → default strat 는 None → FAIL.
    Green: 완화 후 default strat(min=2) → dict.
    """
    candles = _build_shallow_2day_flag(flag_len=2)

    # 명시 대비 — min=3 은 2일 플래그를 시도조차 안 하므로 검출 실패.
    strat_min3 = _strat({"flag_lookback_min": 3})
    result_min3, _, _ = strat_min3._detect_pole_and_flag_detailed(candles)
    assert result_min3 is None, (
        "flag_lookback_min=3 은 2일 플래그 조합을 시도하지 않아 얕은 2일 눌림을 "
        f"검출하지 못해야 함. 실제={result_min3}"
    )

    # 명시 완화 — min=2 는 2일 플래그를 시도해 검출 성공.
    strat_min2 = _strat({"flag_lookback_min": 2})
    result_min2, fail_stage2, detail2 = strat_min2._detect_pole_and_flag_detailed(candles)
    assert result_min2 is not None, (
        "flag_lookback_min=2 는 얕은 2일 눌림 + 거래량 고갈 셋업을 검출해야 함. "
        f"fail_stage={fail_stage2} detail={detail2}"
    )
    assert result_min2["flag_len"] == 2, (
        f"검출된 셋업의 flag_len 은 2 여야 함. 실제={result_min2['flag_len']}"
    )

    # 핵심 Red 단언 — DEFAULT (완화 채택 시 min=2) 에서 검출되어야 함.
    strat_default = _strat()
    result_default, fail_stage_d, detail_d = strat_default._detect_pole_and_flag_detailed(candles)
    assert result_default is not None, (
        "DEFAULT_PARAMS flag_lookback_min 완화(3→2) 후 얕은 2일 눌림 셋업이 "
        f"검출되어야 함. 현재 코드(min=3)에서는 Red. fail_stage={fail_stage_d} detail={detail_d}"
    )


# ===========================================================================
# (b) [SAFETY 불변] flag_volume_ratio 오판 차단 (min=3/min=2 양쪽 PASS)
# ===========================================================================
@pytest.mark.parametrize("flag_min", [3, 2])
def test_b_2day_drop_high_volume_rejected(flag_min):
    """폴 직후 2일 급락 + 거래량 유지 → flag_lookback_min=2 여도 검출 실패.

    완화가 급락 되돌림(하락 초입)을 플래그로 오판하지 않음 =
    flag_volume_ratio(0.60) 안전장치가 유일 방어선임을 고정.
    min=3/min=2 양쪽 불변식 (Red 아님, 회귀 가드).
    """
    candles = _build_2day_drop_high_volume()
    strat = _strat({"flag_lookback_min": flag_min})
    result, fail_stage, detail = strat._detect_pole_and_flag_detailed(candles)
    assert result is None, (
        f"2일 급락 + 거래량 유지는 검출 실패해야 함 (flag_min={flag_min}). "
        f"fail_stage={fail_stage} detail={detail}"
    )
    assert fail_stage == "volume_contraction", (
        "거래량 수축 미달이 바인딩 단계여야 함 (flag_volume_ratio 안전장치). "
        f"실제 fail_stage={fail_stage} detail={detail}"
    )


# ===========================================================================
# (d) [불변] 인접 안전장치 임계 불변 — 완화 범위가 단일 파라미터임을 고정
# ===========================================================================
def test_d_adjacent_safety_params_unchanged():
    """flag_lookback_min 외 인접 키 불변 단언 (완화 범위 = 단일 파라미터)."""
    dp = BullFlagBreakoutStrategy.DEFAULT_PARAMS
    assert dp["flag_volume_ratio"] == 0.60, (
        "거래량 고갈 안전장치 flag_volume_ratio 는 절대 불변 (자문 §반례 #2). "
        f"실제={dp['flag_volume_ratio']}"
    )
    assert dp["pole_min_return"] == 15.0, (
        f"pole_min_return 불변 (사이클 48 완화 유지). 실제={dp['pole_min_return']}"
    )
    assert dp["flag_retracement_max"] == 0.382, (
        f"flag_retracement_max 불변 (2순위, 사이클 198 범위 외). 실제={dp['flag_retracement_max']}"
    )
    assert dp["pole_max_red_ratio"] == 0.45, (
        f"pole_max_red_ratio 불변 (사이클 48). 실제={dp['pole_max_red_ratio']}"
    )
    assert dp["flag_lookback_max"] == 10, (
        f"flag_lookback_max 불변. 실제={dp['flag_lookback_max']}"
    )


# ===========================================================================
# (e) [불변] flag_lookback_min 최종값 == 2 (구현 후 Green)
# ===========================================================================
def test_e_flag_lookback_min_is_2():
    """구현 후 BFB DEFAULT_PARAMS["flag_lookback_min"] == 2.

    Red: 현재 코드 3 → FAIL. Green: 완화 후 2.
    """
    assert BullFlagBreakoutStrategy.DEFAULT_PARAMS["flag_lookback_min"] == 2, (
        "사이클 198 — flag_lookback_min 3→2 완화. 현재 코드(3)에서는 Red."
    )
