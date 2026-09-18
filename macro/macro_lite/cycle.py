"""경기 사이클 국면 판단.

macro_regime.py와 완전 독립. 수익률곡선, 신용스프레드, VIX,
섹터 로테이션, 달러 강도 5개 지표 가중합산으로 4국면 판단.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── 4국면 정의 ──────────────────────────────────────────────────────────────

CYCLE_PHASES = {
    "recovery": {
        "label": "회복기",
        "desc": "수익률곡선 정상화, VIX 하락, 신용스프레드 축소",
    },
    "expansion": {
        "label": "확장기",
        "desc": "양의 수익률곡선, 낮은 VIX, 좁은 신용스프레드",
    },
    "overheating": {
        "label": "과열기",
        "desc": "수익률곡선 평탄화, VIX 저점, 방어 전환",
    },
    "contraction": {
        "label": "수축기",
        "desc": "수익률곡선 역전, VIX 급등, 신용스프레드 확대",
    },
}

# ── 국면별 선도 섹터 ────────────────────────────────────────────────────────

LEADER_SECTORS = {
    "recovery": ["XLF", "XLI", "XLB"],
    "expansion": ["XLK", "XLY", "XLC"],
    "overheating": ["XLE", "XLB", "XLP"],
    "contraction": ["XLU", "XLV", "XLP"],
}


# ── 점수 계산 ───────────────────────────────────────────────────────────────

def _score_yield_curve(
    spread: Optional[float],
    direction: str,
) -> dict[str, float]:
    """수익률곡선 30% 가중치 점수."""
    scores = {"recovery": 0, "expansion": 0, "overheating": 0, "contraction": 0}

    if spread is None:
        return scores

    if spread > 1.5:
        scores["recovery"] = 0.7
        scores["expansion"] = 0.3
    elif spread > 0:
        scores["expansion"] = 0.5
        scores["overheating"] = 0.5
    else:  # 역전
        scores["contraction"] = 1.0

    # 방향 보정
    if direction == "steepening":
        scores["recovery"] += 0.3
    elif direction == "flattening":
        scores["overheating"] += 0.3

    return scores


def _score_credit(direction: str, oas_momentum_6m: Optional[float] = None) -> dict[str, float]:
    """하이일드 신용스프레드 20% 가중치 점수.

    oas_momentum_6m: HY OAS 6개월 변화율(%). 양수=확대(contraction), 음수=축소(recovery).
    - momentum > +50% → contraction +0.3 가중 (신용 패닉 가속)
    - momentum < -30% → recovery +0.3 가중 (신용 패닉 해소 → 회복 시그널)
    """
    scores = {"recovery": 0, "expansion": 0, "overheating": 0, "contraction": 0}

    if direction == "narrowing":
        scores["recovery"] = 0.5
        scores["expansion"] = 0.5
    elif direction == "widening":
        scores["contraction"] = 1.0
    else:
        scores["expansion"] = 0.3
        scores["overheating"] = 0.3

    # OAS momentum 가중 (Phase 3, 2026-05-04)
    if oas_momentum_6m is not None:
        if oas_momentum_6m > 50.0:
            scores["contraction"] += 0.3
        elif oas_momentum_6m < -30.0:
            scores["recovery"] += 0.3

    return scores


def _score_vix(value: Optional[float], level: str) -> dict[str, float]:
    """VIX 20% 가중치 점수."""
    scores = {"recovery": 0, "expansion": 0, "overheating": 0, "contraction": 0}

    if value is None:
        return scores

    if value > 35:
        # 강제 contraction
        scores["contraction"] = 1.0
        return scores

    if value < 15:
        scores["expansion"] = 0.7
        scores["overheating"] = 0.3
    elif value < 25:
        scores["expansion"] = 0.3
        scores["recovery"] = 0.3
        scores["overheating"] = 0.2
    else:  # 25~35
        scores["contraction"] = 0.7
        scores["recovery"] = 0.3

    return scores


def _score_sector(rotation: str) -> dict[str, float]:
    """섹터 로테이션 15% 가중치 점수."""
    scores = {"recovery": 0, "expansion": 0, "overheating": 0, "contraction": 0}

    if rotation == "cyclical":
        scores["expansion"] = 0.7
        scores["recovery"] = 0.3
    elif rotation == "defensive":
        scores["contraction"] = 0.7
        scores["overheating"] = 0.3
    else:
        scores["expansion"] = 0.25
        scores["overheating"] = 0.25

    return scores


def _score_dollar(strength: str) -> dict[str, float]:
    """달러 강도 15% 가중치 점수."""
    scores = {"recovery": 0, "expansion": 0, "overheating": 0, "contraction": 0}

    if strength == "weakening":
        scores["expansion"] = 0.7
        scores["recovery"] = 0.3
    elif strength == "strengthening":
        scores["contraction"] = 0.7
        scores["overheating"] = 0.3
    else:
        scores["expansion"] = 0.25
        scores["overheating"] = 0.25

    return scores


# ── 국면 판단 ───────────────────────────────────────────────────────────────

def determine_cycle_phase(inputs: dict) -> dict:
    """5개 지표로 경기 사이클 국면 판단.

    Args:
        inputs: fetch_cycle_inputs() 반환값
            - yield_spread, yield_direction, credit_direction,
              vix_value, vix_level, sector_rotation, dollar_strength

    Returns:
        {
            "phase": str,          # recovery / expansion / overheating / contraction
            "label": str,          # 한글 레이블
            "description": str,    # 설명
            "confidence": int,     # 0~100
            "scores": dict,        # 국면별 점수
            "leader_sectors": list, # 선도 섹터 ETF 심볼
            "inputs_summary": dict, # 입력 지표 요약
        }
    """
    # 가중치
    weights = {
        "yield": 0.30,
        "credit": 0.20,
        "vix": 0.20,
        "sector": 0.15,
        "dollar": 0.15,
    }

    # 개별 점수 계산
    s_yield = _score_yield_curve(inputs.get("yield_spread"), inputs.get("yield_direction", "stable"))
    s_credit = _score_credit(
        inputs.get("credit_direction", "stable"),
        oas_momentum_6m=inputs.get("oas_momentum_6m"),
    )
    s_vix = _score_vix(inputs.get("vix_value"), inputs.get("vix_level", "normal"))
    s_sector = _score_sector(inputs.get("sector_rotation", "mixed"))
    s_dollar = _score_dollar(inputs.get("dollar_strength", "stable"))

    # 가중합산
    phases = ["recovery", "expansion", "overheating", "contraction"]
    final_scores = {}
    for phase in phases:
        final_scores[phase] = round(
            s_yield[phase] * weights["yield"]
            + s_credit[phase] * weights["credit"]
            + s_vix[phase] * weights["vix"]
            + s_sector[phase] * weights["sector"]
            + s_dollar[phase] * weights["dollar"],
            4,
        )

    # 최고 점수 국면
    sorted_phases = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)
    top_phase = sorted_phases[0][0]
    top_score = sorted_phases[0][1]
    second_score = sorted_phases[1][1] if len(sorted_phases) > 1 else 0

    # 신뢰도: (1위 - 2위) * 200, 최대 100
    confidence = min(100, round((top_score - second_score) * 200))

    phase_info = CYCLE_PHASES[top_phase]

    # 지표별 한국어 신호 생성
    _DIR_KO = {"steepening": "확대 중", "flattening": "축소 중", "stable": "안정"}
    _CREDIT_KO = {"narrowing": "축소 중", "widening": "확대 중", "stable": "안정"}
    _VIX_KO = {"low": "낮음", "normal": "보통", "high": "높음", "extreme": "극단"}
    _SECTOR_KO = {"cyclical": "경기민감주 우위", "defensive": "방어주 우위", "mixed": "혼합"}
    _DOLLAR_KO = {"weakening": "약세", "strengthening": "강세", "stable": "보합"}

    ys = inputs.get("yield_spread")
    ys_signal = f"스프레드 {ys:+.2f}%" if ys is not None else "-"
    vx = inputs.get("vix_value")
    vx_signal = f"{vx:.1f} ({_VIX_KO.get(inputs.get('vix_level', ''), '')})" if vx is not None else "-"

    scores = {
        "yield_curve": {
            "score": round(s_yield.get(top_phase, 0) * weights["yield"], 3),
            "weight": weights["yield"],
            "signal": ys_signal,
        },
        "credit_spread": {
            "score": round(s_credit.get(top_phase, 0) * weights["credit"], 3),
            "weight": weights["credit"],
            "signal": _CREDIT_KO.get(inputs.get("credit_direction", "stable"), "안정"),
        },
        "vix": {
            "score": round(s_vix.get(top_phase, 0) * weights["vix"], 3),
            "weight": weights["vix"],
            "signal": vx_signal,
        },
        "sector_rotation": {
            "score": round(s_sector.get(top_phase, 0) * weights["sector"], 3),
            "weight": weights["sector"],
            "signal": _SECTOR_KO.get(inputs.get("sector_rotation", "mixed"), "혼합"),
        },
        "dollar": {
            "score": round(s_dollar.get(top_phase, 0) * weights["dollar"], 3),
            "weight": weights["dollar"],
            "signal": _DOLLAR_KO.get(inputs.get("dollar_strength", "stable"), "보합"),
        },
    }

    return {
        "phase": top_phase,
        "phase_label": phase_info["label"],
        "phase_desc": phase_info["desc"],
        "confidence": confidence,
        "scores": scores,
        "leader_sectors": LEADER_SECTORS[top_phase],
    }
