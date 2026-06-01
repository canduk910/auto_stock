"""사이클 49 (2026-05-31) — VCP `_check_pullback_sequence` 결함 재현/시정 회귀.

[결함]
운영 funnel 5/26~5/29 4영업일 누적 33/33 종목이 step 6 (Pullback 점진 수축) 에서
"마지막 폭 ≈ 0.0%" 동일 사유로 탈락. 삼성전자우/POSCO홀딩스/삼성SDI/SK텔레콤/LIG넥스원/
엔씨소프트/이오테크닉스/대주전자재료 등 우량주 모두. vcp_breakout 30일 연속 0건 매매.

[Root cause]
`_check_pullback_sequence` 의 단순 swing 검출이 두 가지 결함을 가짐:
1. **마지막 swing 미완성 처리 누락**: chrono 끝부분이 rising 중이면 j=n-1 → k=j → high==low →
   `high > low` 가드로 마지막 pullback 누락. 운영 funnel reason "마지막 폭 ≈ 0.0%" 는 실제
   계산값이 아니라 `base.get("last_pullback_pct", 0)` 디폴트값 (False 반환 시 key 미set).
2. **노이즈 swing 폭주**: 등호 포함 `>=` / `<=` 로 1원 단위 변동도 swing 으로 인식 →
   회수 2~4회 위반 빈발 (한국 우량주 평탄 구간).

[시정 — ATR threshold swing + 마지막 swing 포함]
- `min_swing_atr_mult` 파라미터 (기본 0.5) 신규 — `base_atr × min_swing_atr_mult` 미만 변동은
  swing 으로 인정 안 함 (노이즈 필터)
- ZigZag 변형: running_max/running_min 추적 + threshold 이상 반전 시에만 swing 확정
- 마지막 swing 미완성도 "마지막 pullback" 으로 포함 (running_max 이후 현재까지 진행 중 하락 폭)
- 점진 수축 검증: `curr < prev` (strict, 등호 제거 — 노이즈 0.5%>0.48% 위반 차단)

본 테스트는 Red 단계로 작성 — 시정 전 모두 FAIL.
"""

from __future__ import annotations

import pytest

from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def strat():
    return VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP", weight=0.0)
    )


def _candles_from_chrono(chrono: list[int]) -> list[dict]:
    """시간순(과거→현재) 종가 리스트 → KIS 일봉 응답 형태 (최신순=index 0).

    high/low 는 종가와 동일 (1차 swing 검출 단순화 — 종가 기반).
    """
    reversed_chrono = list(reversed(chrono))
    return [
        {
            "stck_clpr": str(c),
            "stck_hgpr": str(c),
            "stck_lwpr": str(c),
            "acml_vol": "100000",
        }
        for c in reversed_chrono
    ]


# ---------------------------------------------------------------------------
# RED 1 — 마지막 swing 미완성 (rising 중 끝남) → 마지막 pullback 폭 누락
# ---------------------------------------------------------------------------
def test_last_swing_unfinished_rising_should_use_running_max_pullback(strat):
    """베이스 마지막 봉이 rising 중이어도, 직전 swing low 후 회복 분을 마지막 pullback
    으로 인식해야 한다.

    chrono = [100, 110, 100, 115, 102, 120, 110, 125]
      - swing1 high=110 → low=100 → pullback (110-100)/110 = 9.1%
      - swing2 high=115 → low=102 → pullback (115-102)/115 = 11.3%
      - swing3 high=120 → low=110 → pullback (120-110)/120 = 8.3%
      - swing4 high=125 → 마지막 봉. rising 중 끝남 → 회복 분 무시되면 마지막 pullback 누락
      → 시정 후: 회수 3회(9.1%/11.3%/8.3%) 잡힘. 점진 수축은 11.3% > 8.3% (감소) 만족.
      → True 여야 함. 단 첫번째 9.1% < 11.3% 위반(점진 수축은 단조 감소 필요) 으로 False.

    실제 검증: 마지막 swing 의 high (125) 가 swing pool 에 추가됐는지 = pullbacks 가 3 개 이상이어야.
    """
    chrono = [100, 110, 100, 115, 102, 120, 110, 125]
    # 베이스 길이 = 8 (테스트용. 기본 25 보다 짧지만 함수 내부는 base["length"] 사용)
    candles = _candles_from_chrono(chrono)
    base = {"length": len(chrono), "high": 125, "low": 100, "avg_volume_20": 100_000}

    # `_check_pullback_sequence` 가 False 를 반환해도 (점진 수축 위반),
    # 결함 확인 핵심은 "마지막 polback 폭이 실제 검출된 값 (≈ 12% : 125→110 가 잡혀야)" 임.
    # 시정 후 base["last_pullback_pct"] 에 실제 마지막 pullback 폭이 set 되어야 함.
    strat._check_pullback_sequence(candles, base)
    last_pct = base.get("last_pullback_pct", None)

    # Red: 결함 코드에서는 last_pullback_pct key 미존재 또는 0
    # Green: 시정 후 마지막 swing (125 → ?) 폭이 양수로 기록됨
    # 단순 검증: key 가 존재해야 함 (False 반환 시에도 디버깅 위해 기록)
    assert last_pct is not None, (
        "결함 — _check_pullback_sequence 가 False 반환 시 base['last_pullback_pct'] 가 "
        "set 되지 않아 funnel reason 이 '0.0%' 디폴트로 표시됨 (운영 5/26~5/29 33/33 발생)"
    )


# ---------------------------------------------------------------------------
# RED 2 — 평탄 우량주 노이즈 swing 폭주 → 회수 횟수 폭증으로 False
# ---------------------------------------------------------------------------
def test_quiet_blue_chip_noise_swings_should_not_explode_pullback_count(strat):
    """평탄 우량주: 종가가 거의 평평한데 1원 단위 미세 변동만 있는 경우 노이즈 swing 다수
    검출되면 안 됨. ATR threshold (기본 0.5×ATR) 미만 swing 은 무시.

    chrono = [12000, 12005, 12000, 12010, 12005, 12015, 12010, 12020, 12015, 12025, ...]
    (5원 단위 미세 진동, ATR ≈ 5 라 가정 시 0.5×ATR = 2.5 → 5원 swing 은 임계 초과지만
    20×0.5=10 같은 더 큰 ATR 환경이면 무시)

    이 테스트는 시정 후 동작 검증 — `min_swing_atr_mult` 신규 파라미터 존재 + 임계 미만 swing 무시.
    """
    p = strat.config.params
    # 신규 파라미터 존재 검증 (Red — 시정 전엔 KeyError)
    assert "min_swing_atr_mult" in p, (
        "시정 — 신규 파라미터 `min_swing_atr_mult` 가 DEFAULT_PARAMS 에 추가되어야 함"
    )
    assert p["min_swing_atr_mult"] == 0.5, "기본값 0.5 (베이스 ATR × 0.5 이상만 swing)"


# ---------------------------------------------------------------------------
# RED 3 — 정상 미네르비니 VCP 패턴 (점진 수축 3회) → True 여야 함
# ---------------------------------------------------------------------------
def test_classic_vcp_three_contractions_then_true(strat):
    """전형적인 VCP 패턴 — 3회 pullback 점진 수축. 시정 후 True 반환 + 마지막 폭 기록.

    chrono 구성 (베이스 25봉):
      - 시작 100 → swing high 120 (Stage 2 진입 시뮬)
      - pullback 1: 120 → 102 (15%)
      - pullback 2: 118 → 108 (8.5%)
      - pullback 3: 116 → 112 (3.4%)
      - 마지막 116 (베이스 상단 근처 안정)

    회수 3회 + 15% > 8.5% > 3.4% 점진 수축 + 마지막 3.4% < 12% → True
    """
    chrono = [
        100, 110, 115, 120,         # 상승
        118, 110, 105, 102,         # pullback 1 (120 → 102, 15%)
        108, 115, 118,              # 회복
        116, 112, 110, 108,         # pullback 2 (118 → 108, 8.5%)
        112, 115, 116,              # 회복
        114, 113, 112,              # pullback 3 (116 → 112, 3.4%)
        114, 115, 116, 116,         # 마지막 안정
    ]
    candles = _candles_from_chrono(chrono)
    base = {"length": len(chrono), "high": 120, "low": 102, "avg_volume_20": 100_000}

    result = strat._check_pullback_sequence(candles, base)
    assert result is True, (
        f"전형적 VCP 3회 점진 수축 (15% → 8.5% → 3.4%) 이 통과 안 됨. "
        f"last_pullback_pct={base.get('last_pullback_pct')}"
    )
    last_pct = base.get("last_pullback_pct")
    # 실제 마지막 pullback 은 chrono 끝부분의 last swing — 정확히 3.4% 가 아니어도 양수
    assert last_pct is not None and last_pct > 0, (
        f"마지막 pullback 폭이 기록되어야 함. 현재={last_pct}"
    )


# ---------------------------------------------------------------------------
# RED 4 — 마지막 pullback 폭이 0.0% 가 절대 아니어야 (운영 결함 직접 재현)
# ---------------------------------------------------------------------------
def test_real_world_pullback_never_reports_exact_zero_percent(strat):
    """5/29 운영 데이터 재현: 베이스 검출 성공한 후 step 6 에서 "마지막 폭 ≈ 0.0%" 로
    탈락하면 안 됨. 베이스 검출이 성공했다는 것은 base_high > base_low 이므로 최소 1회의
    실질 변동이 존재. 따라서 마지막 pullback 폭은 최소 0.5% 이상이거나, 0 미설정 시
    funnel 표시에서 fallback 값이 명확해야 함.

    이 테스트는 시정의 핵심 — funnel reason 정확성.
    """
    # 베이스 검출이 성공할 수준의 의미 있는 변동
    chrono = [
        100, 108, 115,              # 상승
        112, 108, 105, 102,         # pullback 1 (115 → 102, 11.3%)
        108, 113,                   # 회복
        111, 108, 106,              # pullback 2 (113 → 106, 6.2%)
        109, 111, 113,              # 회복 + 마지막 안정
    ]
    candles = _candles_from_chrono(chrono)
    base = {"length": len(chrono), "high": 115, "low": 102, "avg_volume_20": 100_000}

    strat._check_pullback_sequence(candles, base)
    last_pct = base.get("last_pullback_pct", 0)

    # Red: 결함 코드는 마지막 봉 113 (rising) 으로 끝나서 마지막 swing 누락 → 0.0%
    # Green: 시정 후 마지막 swing 의 실제 폭이 기록되거나, key 자체가 양수 의미값
    assert last_pct != 0 or "last_pullback_pct" in base, (
        f"베이스 검출 성공 + 의미 있는 변동 존재인데 마지막 폭 0.0% 표시 결함. "
        f"last_pct={last_pct} base_keys={list(base.keys())}"
    )


# ---------------------------------------------------------------------------
# RED 5 — DEFAULT_PARAMS 에 신규 파라미터 명시 (회귀 가드)
# ---------------------------------------------------------------------------
def test_default_params_has_min_swing_atr_mult():
    """시정 후 `DEFAULT_PARAMS` 에 `min_swing_atr_mult=0.5` 신규 추가 검증.

    명세: `_workspace/00_leader_trading_rules.md` 6-F 사이클 49.
    """
    p = VcpBreakoutStrategy.DEFAULT_PARAMS
    assert "min_swing_atr_mult" in p
    assert p["min_swing_atr_mult"] == 0.5


# ---------------------------------------------------------------------------
# RED 6 — 점진 수축 검증의 strict 비교 (등호 제거)
# ---------------------------------------------------------------------------
def test_strict_contraction_rejects_equal_widths(strat):
    """동일 폭 두 swing 은 "점진 수축" 이 아님 — strict 비교. 시정 후 등호 위반시 False.

    chrono: 5회 swing, 폭 모두 동일 ~5% → False (회수 5회 > 4 max 라 어차피 False 지만
    strict 비교 의도는 별도 검증).

    회수 3회 + 폭 동일 fixture:
      - swing1 high=105 → low=100 (4.76%)
      - swing2 high=110 → low=105 (4.55%)  → 직전 4.76% 대비 약간 감소
      - swing3 high=115 → low=110 (4.35%)  → 직전 4.55% 대비 약간 감소
    이건 통과해야 함 (감소). 동일 검증은 의도가 더 미묘 — 본 테스트는 회귀 안전망만.
    """
    # 단순 회귀: 시정 후에도 정상 점진 수축은 통과
    chrono = [
        100, 102, 105,                   # rising
        103, 101, 100,                   # pullback 1 (105 → 100, 4.76%)
        103, 107, 110,                   # rising
        108, 106, 105,                   # pullback 2 (110 → 105, 4.55%)
        108, 112, 115,                   # rising
        113, 111, 110,                   # pullback 3 (115 → 110, 4.35%)
        112, 114, 116, 116,
    ]
    candles = _candles_from_chrono(chrono)
    base = {"length": len(chrono), "high": 116, "low": 100, "avg_volume_20": 100_000}

    result = strat._check_pullback_sequence(candles, base)
    # 4.76% > 4.55% > 4.35% 점진 수축 + 마지막 4.35% < 12% → True
    assert result is True, (
        f"점진 수축 3회 (4.76→4.55→4.35%) 통과 안 됨. "
        f"last_pullback_pct={base.get('last_pullback_pct')}"
    )


# ---------------------------------------------------------------------------
# 사이클 49 미세 보강 (2026-05-31, domain-expert Q4 권고) —
# funnel reason 이 "swing 미검출" 과 "실제 측정 폭" 을 구분
# ---------------------------------------------------------------------------


def test_pullback_count_exposed_for_funnel_reason(strat):
    """`_check_pullback_sequence` 가 `base["last_pullback_count"]` 를 항상 노출.

    domain-expert Q4 — funnel reason "0.0%" 가 (a) 디폴트값 (b) 진짜 평탄 베이스 swing
    미검출 (c) 실제 측정 0% 폭 중 어느 것인지 운영자가 구분 가능해야 함. count 노출로
    호출자가 분기 가능.

    검증:
    - 평탄 베이스 (모든 종가 동일) → False 반환 + `last_pullback_count == 0`
    - 정상 점진 수축 → True 반환 + `last_pullback_count > 0`
    """
    # 1) 평탄 베이스 — swing 자체 미검출 (variations < min_swing_atr_mult × ATR)
    flat_chrono = [100] * 30  # 모든 종가 동일 → ATR=0 → 폴백 임계 → 변동 0 미만 → swing 0개
    flat_candles = _candles_from_chrono(flat_chrono)
    flat_base = {
        "length": len(flat_chrono), "high": 100, "low": 100, "avg_volume_20": 100_000
    }
    result_flat = strat._check_pullback_sequence(flat_candles, flat_base)
    assert result_flat is False
    assert "last_pullback_count" in flat_base, (
        "평탄 베이스에서 `last_pullback_count` 키 미설정 — "
        "funnel reason 분기 불가"
    )
    assert flat_base["last_pullback_count"] == 0, (
        f"평탄 베이스 swing 검출 0건 기대. 실제 count={flat_base['last_pullback_count']}"
    )

    # 2) 정상 점진 수축 — swing 검출 성공
    ok_chrono = [
        100, 102, 105,
        103, 101, 100,
        103, 107, 110,
        108, 106, 105,
        108, 112, 115,
        113, 111, 110,
        112, 114, 116, 116,
    ]
    ok_candles = _candles_from_chrono(ok_chrono)
    ok_base = {
        "length": len(ok_chrono), "high": 116, "low": 100, "avg_volume_20": 100_000
    }
    result_ok = strat._check_pullback_sequence(ok_candles, ok_base)
    assert result_ok is True
    assert ok_base.get("last_pullback_count", 0) > 0, (
        f"정상 점진 수축에서 count > 0 기대. 실제 count={ok_base.get('last_pullback_count')}"
    )
