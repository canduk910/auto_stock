"""사이클 223 Red (S1) — `breakout_fail_n_days`·`atr_trail_mult` AI 튜닝 대상 제외.

> 자문: `_workspace/domain_consult/donchian_exit_retune.md` §4 C9 / §5 S1
> 선례: 사이클 208(box 2키) · 209(max_breakout_extension_pct) · 212(buy_threshold·donchian_period)

## 근거

같은 청산축의 `breakeven_promote_atr`·`channel_exit_period` 는 소스 주석이
"전략 정체성 상수 — PARAM_RANGES/INT_PARAMS 미편입 (사이클 208/209/212 선례)" 라
선언하고 이미 제외돼 있다. **남긴 두 키만 코드 기본값에서 이탈했고**(5→2, 2.0→1.8)
둘 다 "더 빨리·더 타이트" 방향이며 `breakout_fail_n_days` 는 범위 하한 `(2, 20)` 의
**하한에 정확히** 붙어 있다 — 사이클 209 `max_breakout_extension_pct` 3.0→0.5 와 동형 서명.

청산 임계는 전략의 **보유기간 정체성**을 정한다. 단기 손실을 목적함수로 삼는 튜너는
구조적으로 이 둘을 하한으로 밀어 추세추종을 데이트레이딩으로 변태시킨다.

## 범위

**매매 행위 diff 0** — AI 권고 "생성"만 막는다. DB 라이브 값(2, 1.8)은 **그대로 둔다**.
`_validate_recommendations` 의 기존 동작(PARAM_RANGES 밖 키 drop)에 의존한다.

## Red 유효성 (production 미변경)

- S1-1 ~ S1-4 = FAIL (현재 PARAM_RANGES :84/:92, INT_PARAMS :104 잔존)
- S1-5 ~ S1-8 = PASS (과제거 회귀 가드 — 잔존 의무 키 / 이전 사이클 제외 유지)
"""
from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit

_EXCLUDED = ("breakout_fail_n_days", "atr_trail_mult")


# ===========================================================================
# S1-1 / S1-2 — 런타임 dict 부재
# ===========================================================================
@pytest.mark.parametrize("key", _EXCLUDED)
def test_s1_1_absent_from_param_ranges(key):
    from src.engine.recommendation_engine import PARAM_RANGES
    assert key not in PARAM_RANGES, (
        f"PARAM_RANGES 에 '{key}' 잔존 금지 (사이클 223 — 청산 임계 = 보유기간 정체성 상수)"
    )


def test_s1_2_absent_from_int_params():
    from src.engine.recommendation_engine import INT_PARAMS
    assert "breakout_fail_n_days" not in INT_PARAMS, (
        "INT_PARAMS 에 'breakout_fail_n_days' 잔존 금지 (사이클 223 제거)"
    )
    assert "atr_trail_mult" not in INT_PARAMS, (
        "'atr_trail_mult' 은 float — INT_PARAMS 미등록 (제거 후에도 부재 유지)"
    )


# ===========================================================================
# S1-3 / S1-4 — `_validate_recommendations` 가 drop (기존 화이트리스트 동작 의존)
# ===========================================================================
def test_s1_3_validate_drops_excluded_keys(caplog):
    """AI 가 두 키를 (기존 범위 내 값으로) 권고해도 validated 에서 사라진다.

    ⚠️ 픽스처 정정 (backend-dev, GREEN 단계) — 원 Red 픽스처는
    `current["max_positions"] = 5` 였다. 그러면 대조군 `position_ratio=0.25` 가
    `0.25 × 5 = 1.25 > 1.0` 으로 **2026-08-03 전략 예산 불변식**
    (`_validate_recommendations` 교차검증, CLAUDE.md 핵심 안전 규칙)에 걸려 pop 되고,
    `validated["position_ratio"]` 가 KeyError 로 죽는다. 이는 S1 과 무관한 픽스처 결함이며
    통과시키려면 프로덕션의 예산 불변식을 약화해야 하므로 **불가**.
    `max_positions` 를 4 로 낮춰(0.25×4 = 1.0 ≤ 1.0) 원 의도 — "잔존 화이트리스트 키는
    계속 통과한다" — 를 그대로 검증한다. 단언은 하나도 완화하지 않았다.
    """
    from src.engine.recommendation_engine import _validate_recommendations

    caplog.set_level(logging.WARNING, logger="src.engine.recommendation_engine")
    raw = {
        "recommended_params": {
            "breakout_fail_n_days": 2,     # 구 범위 (2,20) 하한 — 이제 비화이트리스트
            "atr_trail_mult": 1.8,         # 구 범위 (1.0,5.0) 내 — 이제 비화이트리스트
            "position_ratio": 0.25,        # 잔존 키 — 통과해야 함
        },
        "reasoning": "청산 조임 권고",
    }
    current = {
        "breakout_fail_n_days": 5,
        "atr_trail_mult": 2.0,
        "position_ratio": 0.20,
        "max_positions": 4,   # 픽스처 정정 — 0.25×5=1.25 는 예산 불변식 위반 (docstring 참조)
    }
    validated, reasoning, _w, _n, _wr = _validate_recommendations(raw, current)

    for key in _EXCLUDED:
        assert key not in validated, (
            f"사이클 223 — '{key}' 는 PARAM_RANGES 제거로 drop 되어야 한다 (got {validated})"
        )
    assert validated["position_ratio"] == 0.25, "잔존 화이트리스트 키는 계속 통과"
    assert reasoning == "청산 조임 권고"
    # 비화이트리스트 drop 은 debug 경로 — "범위 초과" WARNING 이 나면 안 된다
    assert not [r for r in caplog.records if "범위 초과" in r.getMessage()], (
        "비화이트리스트 키는 범위 검증 전에 drop (ghost_param 동일 취급)"
    )


def test_s1_4_validate_drops_even_out_of_old_range_values():
    """구 범위를 벗어난 값이어도 동일하게 drop — 경로가 화이트리스트 단계로 앞당겨진다."""
    from src.engine.recommendation_engine import _validate_recommendations

    raw = {"recommended_params": {"breakout_fail_n_days": 99, "atr_trail_mult": 0.1},
           "reasoning": ""}
    current = {"breakout_fail_n_days": 5, "atr_trail_mult": 2.0}
    validated, _, _w, _n, _wr = _validate_recommendations(raw, current)
    assert validated == {}


# ===========================================================================
# S1-5 ~ S1-8 — 과제거 회귀 가드 (잔존 의무 / 이전 사이클 제외 유지)
# ===========================================================================
def test_s1_5_other_param_ranges_keys_remain():
    from src.engine.recommendation_engine import PARAM_RANGES
    for key in (
        "stop_loss_rate", "gap_up_threshold", "trailing_stop_rate", "position_ratio",
        "daily_loss_limit", "k_period", "min_market_cap", "min_trade_amount",
        "max_scan_stocks", "min_prdy_rate", "exclude_consecutive_limit",
        "limit_up_threshold", "intraday_stop_loss", "overnight_stop_loss",
        "stop_loss_main", "stop_loss_pre_nxt",
        "k_value_krx_main", "k_value_nxt_pre", "k_value_nxt_post",
        "long_ma_period", "volume_multiplier",
        "base_depth_pct", "volume_contraction_ratio", "breakout_volume_mult",
        "last_pullback_max", "breakout_retention_minutes",
    ):
        assert key in PARAM_RANGES, f"잔존 의무 PARAM_RANGES 키 누락: {key}"


def test_s1_6_other_int_params_keys_remain():
    from src.engine.recommendation_engine import INT_PARAMS
    for key in ("k_period", "max_scan_stocks", "exclude_consecutive_limit",
                "long_ma_period", "breakout_retention_minutes"):
        assert key in INT_PARAMS, f"잔존 의무 INT_PARAMS 키 누락: {key}"


def test_s1_7_int_params_subset_of_param_ranges():
    """INT_PARAMS ⊆ PARAM_RANGES 규약 보존 (두 dict 동시 제거로 유지)."""
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES
    assert INT_PARAMS.issubset(PARAM_RANGES.keys()), (
        f"INT_PARAMS 가 PARAM_RANGES 밖: {INT_PARAMS - set(PARAM_RANGES.keys())}"
    )


def test_s1_8_previous_cycle_exclusions_still_absent():
    """사이클 208/209/212 + 2026-08-03 예산 제외 키가 계속 부재."""
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES
    for key in ("box_contraction_period", "max_box_volatility_pct",
                "max_breakout_extension_pct", "buy_threshold", "donchian_period",
                "max_positions",
                # donchian 레이어드 청산 2키 (P1-A) — 애초에 미편입
                "breakeven_promote_atr", "channel_exit_period"):
        assert key not in PARAM_RANGES, f"PARAM_RANGES 에 '{key}' 잔존 금지"
        assert key not in INT_PARAMS, f"INT_PARAMS 에 '{key}' 잔존 금지"
