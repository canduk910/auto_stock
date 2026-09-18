"""공용 체제 판단 모듈.

3개 서비스(advisory/portfolio_advisor/pipeline)가 공유하는 시장 체제(regime) 판단 로직.

- 버핏지수 × 공포탐욕 16셀 매트릭스 기반 체제 결정
- VIX > 35 시 강제 extreme_fear 오버라이드
- previous_regime 제공 시 경계값 ±5점 하이스테리시스로 체제 토글 방지

에이전트 원문 스펙: .claude/agents/macro-sentinel.md
"""

from __future__ import annotations

from typing import Optional


# ── 공용 상수 ─────────────────────────────────────────────────

# 버핏지수 × 공포탐욕 교차표 (macro-sentinel.md 스펙)
REGIME_MATRIX: dict[tuple[str, str], str] = {
    ("low", "extreme_fear"): "accumulation",
    ("low", "fear"): "accumulation",
    ("low", "neutral"): "selective",
    ("low", "greed"): "cautious",
    ("low", "extreme_greed"): "cautious",
    ("normal", "extreme_fear"): "selective",
    ("normal", "fear"): "selective",
    ("normal", "neutral"): "cautious",
    ("normal", "greed"): "cautious",
    ("normal", "extreme_greed"): "defensive",
    ("high", "extreme_fear"): "selective",
    ("high", "fear"): "cautious",
    ("high", "neutral"): "cautious",
    ("high", "greed"): "defensive",
    ("high", "extreme_greed"): "defensive",
    ("extreme", "extreme_fear"): "cautious",
    ("extreme", "fear"): "defensive",
    ("extreme", "neutral"): "defensive",
    ("extreme", "greed"): "defensive",
    ("extreme", "extreme_greed"): "defensive",
}

# 체제별 파라미터 (margin: 요구 안전마진 %, stock_max: 주식 최대 비중, cash_min: 현금 최소 비중, single_cap: 종목당 한도)
REGIME_PARAMS: dict[str, dict] = {
    "accumulation": {
        "margin": 20,
        "stock_max": 75,
        "cash_min": 25,
        "single_cap": 5,
        "per_max": 20,
        "pbr_max": 2.0,
        "roe_min": 5,
    },
    "selective": {
        "margin": 30,
        "stock_max": 65,
        "cash_min": 35,
        "single_cap": 4,
        "per_max": 15,
        "pbr_max": 1.5,
        "roe_min": 8,
    },
    "cautious": {
        "margin": 40,
        "stock_max": 50,
        "cash_min": 50,
        "single_cap": 3,
        "per_max": 12,
        "pbr_max": 1.2,
        "roe_min": 10,
    },
    "defensive": {
        "margin": 999,  # 진입 금지 센티넬
        "stock_max": 25,
        "cash_min": 75,
        "single_cap": 0,
        "per_max": 0,
        "pbr_max": 0,
        "roe_min": 0,
    },
}

# 한국어 라벨 (프롬프트/UI 표시용)
REGIME_DESC: dict[str, str] = {
    "accumulation": "축적 (탐욕 매수)",
    "selective": "선별 (중립 적극)",
    "cautious": "신중 (방어 선별)",
    "defensive": "방어 (공포 현금)",
}


# ── 분류 헬퍼 ─────────────────────────────────────────────────

def _classify_buffett(ratio: Optional[float]) -> str:
    """버핏지수(시총/GDP 소수) → level."""
    if ratio is None:
        return "normal"
    if ratio < 0.8:
        return "low"
    if ratio < 1.2:
        return "normal"
    if ratio < 1.6:
        return "high"
    return "extreme"


def _classify_fear_greed(score: Optional[float], vix: Optional[float] = None) -> str:
    """공포탐욕지수 → level. VIX > 35 오버라이드."""
    # VIX > 35: 공포탐욕 수치와 무관하게 extreme_fear
    if vix is not None and vix > 35:
        return "extreme_fear"
    if score is None:
        return "neutral"
    if score < 20:
        return "extreme_fear"
    if score < 40:
        return "fear"
    if score < 60:
        return "neutral"
    if score < 80:
        return "greed"
    return "extreme_greed"


def _classify_buffett_with_hysteresis(
    ratio: Optional[float], previous_level: Optional[str]
) -> str:
    """하이스테리시스 버퍼 ±0.05 (5점 = 0.05 비율) 적용 버핏지수 분류."""
    level = _classify_buffett(ratio)
    if previous_level is None or ratio is None or level == previous_level:
        return level
    # 경계값 ±0.05 내에서 이전 level 유지
    buffers = {
        ("low", "normal"): 0.80,
        ("normal", "high"): 1.20,
        ("high", "extreme"): 1.60,
    }
    pairs = [("low", "normal"), ("normal", "high"), ("high", "extreme")]
    for lo, hi in pairs:
        threshold = buffers[(lo, hi)]
        if previous_level == lo and level == hi and ratio < threshold + 0.05:
            return lo
        if previous_level == hi and level == lo and ratio > threshold - 0.05:
            return hi
    return level


def _classify_fg_with_hysteresis(
    score: Optional[float],
    vix: Optional[float],
    previous_level: Optional[str],
) -> str:
    """하이스테리시스 버퍼 ±5점 적용 공포탐욕 분류. VIX 오버라이드는 버퍼 없이 강제 적용."""
    # VIX 오버라이드는 하이스테리시스 예외 — 시장 패닉에 즉각 반응
    if vix is not None and vix > 35:
        return "extreme_fear"
    level = _classify_fear_greed(score, vix)
    if previous_level is None or score is None or level == previous_level:
        return level
    boundaries = [
        ("extreme_fear", "fear", 20),
        ("fear", "neutral", 40),
        ("neutral", "greed", 60),
        ("greed", "extreme_greed", 80),
    ]
    for lo, hi, threshold in boundaries:
        if previous_level == lo and level == hi and score < threshold + 5:
            return lo
        if previous_level == hi and level == lo and score > threshold - 5:
            return hi
    return level


# ── 메인 API ─────────────────────────────────────────────────

def _step_fg_level(level: str, direction: str) -> str:
    """fg_level을 한 단계 fear/greed 쪽으로 이동.

    direction: "fear" | "greed"
    """
    order = ["extreme_greed", "greed", "neutral", "fear", "extreme_fear"]
    try:
        idx = order.index(level)
    except ValueError:
        return level
    if direction == "fear" and idx < len(order) - 1:
        return order[idx + 1]
    if direction == "greed" and idx > 0:
        return order[idx - 1]
    return level


def determine_regime(
    sentiment: dict,
    previous_regime: Optional[str] = None,
    hy_oas_percentile: Optional[float] = None,
    hy_oas_value: Optional[float] = None,
) -> dict:
    """매크로 심리 데이터에서 시장 체제 결정.

    신용 통합 (2026-05-04):
    - Phase 1 (F&G 보정): hy_oas_percentile >= 90 → fg_level 한 단계 fear,
                          hy_oas_percentile <= 10 → 한 단계 greed.
    - Phase 2 (오버라이드): hy_oas_value > 10% OR hy_oas_percentile > 95 →
                          체제 강제 accumulation (단 buffett high/extreme이면 selective 완화).
                          hy_oas_percentile < 5 AND buffett high/extreme → defensive 강제.
    - VIX > 35 오버라이드는 신용 보정보다 우선.

    Args:
        sentiment: macro_service.get_sentiment() 반환 형식.
            fear_greed.{score|value}, vix.{value} 또는 vix(float), buffett_indicator.{ratio} 또는 buffett.{ratio}
        previous_regime: 직전 체제. 제공 시 경계값 ±5점(FG) / ±0.05(Buffett) 하이스테리시스 적용.
        hy_oas_percentile: HY OAS 전 기간 백분위 (0~100). credit_spread 응답에서 전달.
        hy_oas_value: HY OAS 현재값 (%). 절대 안전장치(>10%) 평가용.

    Returns:
        {
            regime: str,
            regime_desc: str,
            params: {margin, stock_max, cash_min, single_cap, per_max, pbr_max, roe_min},
            vix: float | None,
            buffett_ratio: float | None,
            fear_greed_score: float | None,
            buffett_level: str,
            fg_level: str,
            credit_adjustment: str | None,  # Phase 1 보정 결과
            credit_override: str | None,    # Phase 2 오버라이드 결과
        }
    """
    # VIX 추출 — dict 또는 float 양쪽 지원
    raw_vix = sentiment.get("vix") if isinstance(sentiment, dict) else None
    if isinstance(raw_vix, dict):
        vix = raw_vix.get("value")
    else:
        vix = raw_vix

    # 버핏지수 추출 — buffett_indicator 또는 buffett 키 지원
    buffett_data = (
        sentiment.get("buffett_indicator") or sentiment.get("buffett") or {}
        if isinstance(sentiment, dict)
        else {}
    )
    if isinstance(buffett_data, dict):
        buffett_ratio = buffett_data.get("ratio")
    else:
        buffett_ratio = buffett_data

    # 백분율(235.2)이면 소수(2.352)로 변환
    if buffett_ratio is not None and buffett_ratio > 10:
        try:
            buffett_ratio = round(buffett_ratio / 100, 3)
        except Exception:
            buffett_ratio = None

    # 공포탐욕 추출 — score 또는 value 키 지원
    fear_greed = sentiment.get("fear_greed") or {} if isinstance(sentiment, dict) else {}
    if isinstance(fear_greed, dict):
        fg_raw = fear_greed.get("score")
        if fg_raw is None:
            fg_raw = fear_greed.get("value")
        try:
            fg_score = float(fg_raw) if fg_raw is not None else None
        except (TypeError, ValueError):
            fg_score = None
    else:
        try:
            fg_score = float(fear_greed)
        except (TypeError, ValueError):
            fg_score = None

    # VIX 타입 정규화
    try:
        vix_num = float(vix) if vix is not None else None
    except (TypeError, ValueError):
        vix_num = None

    # 이전 체제에서 level 재현 (하이스테리시스용) — previous_regime 단일 정보만 받으므로 근사값
    # 실무상 previous_regime 전달 시 경계에 있는 새 level만 억제하면 충분
    prev_buffett_level = None
    prev_fg_level = None
    if previous_regime:
        # 이전 regime에서 가능한 buffett/fg level 조합을 역추적
        for (bl, fl), r in REGIME_MATRIX.items():
            if r == previous_regime:
                # 첫 매칭만 사용 (복수 매칭 존재하지만 하이스테리시스는 경계 토글 방지 수준이면 충분)
                # 현재 값과 가장 가까운 level 선택
                if prev_buffett_level is None:
                    prev_buffett_level = bl
                    prev_fg_level = fl

    buffett_level = _classify_buffett_with_hysteresis(buffett_ratio, prev_buffett_level)
    fg_level = _classify_fg_with_hysteresis(fg_score, vix_num, prev_fg_level)

    # ── Phase 1: 신용 F&G 보정 (VIX 오버라이드 후) ──────────────────
    # VIX > 35 오버라이드 시 fg_level은 이미 extreme_fear로 강제됨 → 신용 보정 미적용
    credit_adjustment: Optional[str] = None
    vix_overridden = vix_num is not None and vix_num > 35
    if not vix_overridden and hy_oas_percentile is not None:
        if hy_oas_percentile >= 90:
            new_level = _step_fg_level(fg_level, "fear")
            if new_level != fg_level:
                fg_level = new_level
                credit_adjustment = "fear_one_step"
        elif hy_oas_percentile <= 10:
            new_level = _step_fg_level(fg_level, "greed")
            if new_level != fg_level:
                fg_level = new_level
                credit_adjustment = "greed_one_step"

    regime = REGIME_MATRIX.get((buffett_level, fg_level), "cautious")

    # ── Phase 2: 신용 오버라이드 (체제 강제) ──────────────────────
    credit_override: Optional[str] = None
    # 패닉 강제 (HY OAS > 10% 또는 백분위 > 95)
    if (
        (hy_oas_value is not None and hy_oas_value > 10.0)
        or (hy_oas_percentile is not None and hy_oas_percentile > 95)
    ):
        if buffett_level in ("high", "extreme"):
            # 양방향 위기 — selective로 완화
            regime = "selective"
            credit_override = "extreme_fear_selective"
        else:
            regime = "accumulation"
            credit_override = "extreme_fear_accumulation"
    # 신용버블 정점 (HY OAS 백분위 < 5 + 버핏 과열)
    elif (
        hy_oas_percentile is not None
        and hy_oas_percentile < 5
        and buffett_level in ("high", "extreme")
    ):
        regime = "defensive"
        credit_override = "credit_greed_defensive"

    params = REGIME_PARAMS[regime]
    regime_desc = REGIME_DESC.get(regime, regime)

    return {
        "regime": regime,
        "regime_desc": regime_desc,
        "params": params,
        "vix": vix_num,
        "buffett_ratio": buffett_ratio,
        "fear_greed_score": fg_score,
        "buffett_level": buffett_level,
        "fg_level": fg_level,
        "credit_adjustment": credit_adjustment,
        "credit_override": credit_override,
    }


# ── Cycle×Regime 보정 (2026-05-01 신규: 보수성 완화) ──────────────────────
#
# 기존 REGIME_PARAMS는 cycle을 무시하고 단일 체제 기준이라 강세장/회복기에도
# defensive=single_cap=0(매수 절대 금지)을 강제했다. 실제 시장에서는
# defensive 체제에서도 회복/확장기에는 사이클 주도 섹터에 부분 진입이 합리적이다.
#
# 도메인 자문 (MacroSentinel):
# 16셀 single_cap(%) 매트릭스 — 행=regime, 열=cycle_phase
#                | recovery | expansion | overheating | contraction
#  accumulation  |    7     |     6     |      5      |      5
#  selective     |    5     |     4     |      3      |      4
#  cautious      |    4     |     3     |      2      |      3
#  defensive     |    7     |     5     |      2      |      0
#
# (1) defensive+contraction: 0 — 진입 금지 유지 (기존 정책)
# (2) defensive+overheating: 2 — 매우 제한적 매수 허용 (사이클 막바지)
# (3) defensive+expansion:   5 — 사이클 주도 섹터 한정 단계적 매수
# (4) defensive+recovery:    7 — 회복 초기에는 defensive 체제도 적극 진입
# 정책 의도: 동일 defensive라도 cycle이 회복/확장이면 사이클 주도 섹터에 한정해
# advisory에서 분할 매수를 고려할 수 있게 한다.

_CYCLE_SINGLE_CAP: dict[tuple[str, str], int] = {
    ("accumulation", "recovery"): 7,
    ("accumulation", "expansion"): 6,
    ("accumulation", "overheating"): 5,
    ("accumulation", "contraction"): 5,
    ("selective", "recovery"): 5,
    ("selective", "expansion"): 4,
    ("selective", "overheating"): 3,
    ("selective", "contraction"): 4,
    ("cautious", "recovery"): 4,
    ("cautious", "expansion"): 3,
    ("cautious", "overheating"): 2,
    ("cautious", "contraction"): 3,
    ("defensive", "recovery"): 7,
    ("defensive", "expansion"): 5,
    ("defensive", "overheating"): 2,
    ("defensive", "contraction"): 0,
}

# 체제+사이클별 안전마진(%) 보정 — MarginAnalyst 자문
# 강세장(회복/확장)에서 정량 벽이 너무 높아 매수 신호가 사라지는 문제 보정.
_CYCLE_MARGIN: dict[tuple[str, str], int] = {
    ("accumulation", "recovery"): 18,
    ("accumulation", "expansion"): 20,
    ("accumulation", "overheating"): 22,
    ("accumulation", "contraction"): 15,
    ("selective", "recovery"): 25,
    ("selective", "expansion"): 27,
    ("selective", "overheating"): 30,
    ("selective", "contraction"): 20,
    ("cautious", "recovery"): 30,
    ("cautious", "expansion"): 35,
    ("cautious", "overheating"): 40,
    ("cautious", "contraction"): 25,
    ("defensive", "recovery"): 35,
    ("defensive", "expansion"): 40,
    ("defensive", "overheating"): 50,
    ("defensive", "contraction"): 999,  # 사실상 진입 차단
}


def get_regime_params(regime: str, cycle_phase: Optional[str] = None) -> dict:
    """체제+사이클 조합 파라미터.

    cycle_phase가 None이면 기존 REGIME_PARAMS 그대로 반환(하위 호환).
    cycle_phase가 있으면 single_cap/margin을 _CYCLE_SINGLE_CAP/_CYCLE_MARGIN에서 보정.

    Args:
        regime: "accumulation" | "selective" | "cautious" | "defensive"
        cycle_phase: "recovery" | "expansion" | "overheating" | "contraction" | None

    Returns:
        REGIME_PARAMS[regime] 복사본 + single_cap/margin이 cycle 보정값으로 덮어쓰여짐.
    """
    base = REGIME_PARAMS.get(regime, REGIME_PARAMS["selective"]).copy()
    if not cycle_phase:
        return base

    key = (regime, cycle_phase)
    if key in _CYCLE_SINGLE_CAP:
        base["single_cap"] = _CYCLE_SINGLE_CAP[key]
    if key in _CYCLE_MARGIN:
        base["margin"] = _CYCLE_MARGIN[key]
    base["cycle_phase"] = cycle_phase
    return base


def get_margin_requirement(regime: str, cycle_phase: Optional[str] = None) -> int:
    """체제+사이클 조합 안전마진 요구치(%) — Graham 할인율 기준선.

    기존 advisory_service._REGIME_MARGIN(체제 단일)을 cycle 보정 버전으로 대체.
    """
    if not cycle_phase:
        return REGIME_PARAMS.get(regime, {}).get("margin", 25)
    return _CYCLE_MARGIN.get((regime, cycle_phase), REGIME_PARAMS.get(regime, {}).get("margin", 25))


__all__ = [
    "REGIME_MATRIX",
    "REGIME_PARAMS",
    "REGIME_DESC",
    "determine_regime",
    "get_regime_params",
    "get_margin_requirement",
]
