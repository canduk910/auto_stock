"""`_normalize_stop_loss_rate` VB 보드별 키 확장 (사이클 3, 2026-05-17).

배경:
    사이클 3 — VB 보드별 손절 분리. `recommendation_metrics._normalize_stop_loss_rate()`
    가 기존 3 키(`stop_loss_rate`/`intraday_stop_loss`/`overnight_stop_loss`) 만
    후보로 → VB 가 보드별 키(`stop_loss_main`/`stop_loss_pre_nxt`) 만 설정하면
    `stop_loss_hits` 카운트가 0 으로 잘못 누적되는 결함 차단.

    Phase A2 (LTV) 결함과 동일 패턴 — `min(candidates)` 로 가장 보수적인
    (절대값 큰) 단일 임계로 정규화.

확장:
    기존 후보 키 (3) → 5
    - stop_loss_rate
    - intraday_stop_loss
    - overnight_stop_loss
    - stop_loss_main         (신규, VB 보드별)
    - stop_loss_pre_nxt      (신규, VB 보드별)

    `stop_loss_post_nxt` 는 VB POST_NXT 미사용이라 제외.

Red 의도:
    G: VB 보드별 키만 → 정규화 정상 작동
    H: 보드별 + top-level 혼합 → 더 보수적 쪽
    I: 사이클 3 이전 회귀 5 케이스 (LTV/단일/없음/혼합/None) 보존
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# G. VB 보드별 키만 → 정규화 정상 작동 (사이클 3 신규)
# ---------------------------------------------------------------------------
def test_vb_board_keys_only_normalize_to_most_conservative():
    """VB params 가 `stop_loss_main=-3.0` + `stop_loss_pre_nxt=-4.0` 만.

    candidates = [-3.0, -4.0], min = -4.0 (절대값 큰 = 가장 보수적).
    LTV 분리 키 패턴과 일관.
    """
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    params = {"stop_loss_main": -3.0, "stop_loss_pre_nxt": -4.0}
    result = _normalize_stop_loss_rate(params)
    assert result == -4.0, (
        f"VB 보드별 키 정규화: 가장 보수적인 -4.0 기대, got {result}"
    )


def test_vb_single_board_key_returns_that_value():
    """VB params 가 `stop_loss_main=-2.5` 만 → -2.5 반환.

    pre_nxt 키 부재 케이스 (운영자가 main 만 차별화).
    """
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    params = {"stop_loss_main": -2.5}
    result = _normalize_stop_loss_rate(params)
    assert result == -2.5, f"단일 보드 키 -2.5 기대, got {result}"


def test_vb_board_keys_combined_with_top_level():
    """VB params 가 보드별 + top-level 혼합:
    `stop_loss_main=-2.5` + `stop_loss_pre_nxt=-3.0` + `stop_loss_rate=-5.0`.

    candidates = [-2.5, -3.0, -5.0], min = -5.0.
    실제 운영에서 발생 가능 (마이그 024 적용 후 운영자가 추가 차별화).
    """
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    params = {
        "stop_loss_main": -2.5,
        "stop_loss_pre_nxt": -3.0,
        "stop_loss_rate": -5.0,
    }
    result = _normalize_stop_loss_rate(params)
    assert result == -5.0, (
        f"보드별 + top-level 혼합: 가장 보수적 -5.0 기대, got {result}"
    )


# ---------------------------------------------------------------------------
# H. 사이클 3 회귀 보존 — 기존 5 케이스 그대로
# ---------------------------------------------------------------------------
def test_regression_single_stop_loss_rate():
    """`stop_loss_rate` 단일 키 → 그대로 반환 (5 전략 회귀)."""
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    assert _normalize_stop_loss_rate({"stop_loss_rate": -3.5}) == -3.5


def test_regression_ltv_separated_keys():
    """LTV `intraday_stop_loss`/`overnight_stop_loss` 분리 키 정규화 (Phase A2 회귀)."""
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    params = {"intraday_stop_loss": -2.5, "overnight_stop_loss": -2.0}
    assert _normalize_stop_loss_rate(params) == -2.5


def test_regression_empty_params_returns_zero():
    """후보 모두 부재 → 0.0 반환 (compute_metrics 분기 skip 보존)."""
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    assert _normalize_stop_loss_rate({}) == 0.0


def test_regression_positive_value_ignored():
    """양수 손절은 무시. 양수만 있는 케이스 → 0.0."""
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    assert _normalize_stop_loss_rate({"stop_loss_rate": 2.0}) == 0.0
    assert _normalize_stop_loss_rate({"stop_loss_main": 1.0, "stop_loss_pre_nxt": -3.0}) == -3.0


def test_regression_none_values_handled():
    """None 값은 _safe_float 가 0.0 으로 변환 → 양수 필터로 자동 skip."""
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    params = {
        "stop_loss_rate": None,
        "stop_loss_main": None,
        "stop_loss_pre_nxt": -3.5,
    }
    assert _normalize_stop_loss_rate(params) == -3.5


# ---------------------------------------------------------------------------
# I. compute_metrics 통합 — VB 보드별 키 케이스에서 stop_loss_hits 정상 카운트
# ---------------------------------------------------------------------------
def test_compute_metrics_counts_stop_loss_hits_with_vb_board_keys():
    """VB 보드별 키만 설정 → compute_metrics stop_loss_hits 정상 카운트.

    fixture: 2 SELL (-3.5%, -1.0%) + `stop_loss_main=-3.0`/`stop_loss_pre_nxt=-4.0`.
    정규화 → -4.0 (가장 보수적). threshold = -4.0 + 0.5 = -3.5.
    -3.5% <= -3.5 → 1 카운트 (경계).
    -1.0% > -3.5 → skip.
    """
    from src.engine.recommendation_metrics import compute_metrics

    trades = [
        {
            "trade_type": "SELL",
            "status": "COMPLETED",
            "strategy": "volatility_breakout",
            "price": 10000,
            "quantity": 10,
            "profit_loss": -3500,  # -3.5%
            "ticker": "066570",
        },
        {
            "trade_type": "SELL",
            "status": "COMPLETED",
            "strategy": "volatility_breakout",
            "price": 20000,
            "quantity": 5,
            "profit_loss": -1000,  # -1.0%
            "ticker": "005930",
        },
    ]
    current_params = {
        "stop_loss_main": -3.0,
        "stop_loss_pre_nxt": -4.0,
    }
    result = compute_metrics(trades=trades, performance=[], current_params=current_params)

    # 정규화 -4.0 + 0.5 = -3.5, -3.5% <= -3.5 → 1 카운트
    assert result["stop_loss_hits"] >= 1, (
        f"VB 보드별 키 정규화 결함 — stop_loss_hits=0 (Phase A2 LTV 결함과 동일 패턴): {result}"
    )
