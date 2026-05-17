"""LTV `stop_loss_hits=0` 결함(Phase A2, 2026-05-17) 회귀 가드.

5/15 운영 데이터 분석에서 LTV(`long_tail_volatility`) 만:
- `metrics.stop_loss_hits = 0`
- `metrics.max_loss_pct = -7.554%`, `metrics.avg_loss_pct = -3.797%`
- 손절 임계: `intraday_stop_loss = -2.5%`, `overnight_stop_loss = -2.0%`

→ 10영업일 동안 최대 -7.55% 손실이 발생했고 평균 손실도 임계치(-2.5%) 초과인데
`stop_loss_hits = 0` 고정. `recommendation_metrics.compute_metrics()` 의
`current_params.get("stop_loss_rate")` **단일 키** 참조 결함.

→ LTV 만 분리 키(`intraday_stop_loss` / `overnight_stop_loss`) 사용.
다른 5 전략은 `stop_loss_rate` 단일 키.

Phase A2 fix: `_normalize_stop_loss_rate()` 헬퍼 도입 — 두 케이스 모두 더 보수적인
(절대값 큰) 단일 임계로 정규화. 다른 5 전략 회귀 보존.

진단 보고서: `_workspace/red/phase-a-ltv-stop-loss-hits.md`.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Case A — LTV 분리 키 정규화 (5/15 운영값)
# ---------------------------------------------------------------------------


def test_ltv_separated_keys_returns_more_conservative_threshold():
    """LTV `intraday_stop_loss=-2.5` + `overnight_stop_loss=-2.0` 정규화.

    더 보수적인(절대값 큰) 쪽 = -2.5 반환. 절대값 큰 임계가 손절 카운트의
    "확실히 도달" 기준 — underestimate 보수적 카운트.
    """
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    params = {"intraday_stop_loss": -2.5, "overnight_stop_loss": -2.0}
    result = _normalize_stop_loss_rate(params)
    assert result == -2.5, f"expected -2.5 (절대값 큰 쪽), got {result}"


# ---------------------------------------------------------------------------
# Case B — 다른 전략 단일 키 회귀 보존
# ---------------------------------------------------------------------------


def test_other_strategy_single_key_regression_preserved():
    """momentum/VB/donchian/bull_flag/vcp 의 `stop_loss_rate` 단일 키 회귀 보존.

    `_normalize_stop_loss_rate({"stop_loss_rate": -3.2})` → -3.2 (그대로).
    """
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    params = {"stop_loss_rate": -3.2}
    result = _normalize_stop_loss_rate(params)
    assert result == -3.2, f"expected -3.2 (단일 키 그대로), got {result}"


# ---------------------------------------------------------------------------
# Case C — 두 키 모두 부재
# ---------------------------------------------------------------------------


def test_no_stop_loss_keys_returns_zero():
    """손절 키 없음 → 0.0 반환 (compute_metrics 분기 skip 보존).

    `compute_metrics` 의 `if stop_loss_rate < 0` 분기가 False 처리 → skip.
    None 대신 0.0 으로 통일해 `_safe_float` 호환 + None 체크 분기 불필요.
    """
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    params: dict = {}
    result = _normalize_stop_loss_rate(params)
    assert result == 0.0, f"expected 0.0 (두 키 모두 부재), got {result}"


# ---------------------------------------------------------------------------
# Case D — 5/15 LTV 실측 통합 fixture
# ---------------------------------------------------------------------------


def test_ltv_5_15_integration_stop_loss_hits_counted():
    """5/15 LTV 실측: SELL 2건 중 1건 -3.030%, 1건 -1.2% + LTV 분리 키 params.

    `intraday_stop_loss=-2.5` + threshold +0.5%p = -2.0 (compute_metrics 분기).
    -3.030% <= -2.5 → stop_loss_hits=1.
    -1.2% > -2.5 → 카운트 안 함.

    회귀 가드: 진단 보고서 SQL 검증 결과(`below_intraday_stop_minus_2_5 = 1`) 와 일치.
    """
    from src.engine.recommendation_metrics import compute_metrics

    # 5/15 LTV SELL 2건 (064400 = -3.030%, 다른 종목 = -1.2%)
    # gross = price × qty 기준. pnl = gross × pct / 100.
    # 064400 fixture: price=10000, qty=10 → gross=100000, pnl=-3030 → pct=-3.030
    # other  fixture: price=20000, qty= 5 → gross=100000, pnl=-1200 → pct=-1.200
    trades = [
        {
            "trade_type": "SELL",
            "status": "COMPLETED",
            "strategy": "long_tail_volatility",
            "price": 10000,
            "quantity": 10,
            "profit_loss": -3030,
            "ticker": "064400",
        },
        {
            "trade_type": "SELL",
            "status": "COMPLETED",
            "strategy": "long_tail_volatility",
            "price": 20000,
            "quantity": 5,
            "profit_loss": -1200,
            "ticker": "111111",
        },
    ]

    # LTV 5/15 운영 params
    current_params = {
        "intraday_stop_loss": -2.5,
        "overnight_stop_loss": -2.0,
    }

    result = compute_metrics(trades=trades, performance=[], current_params=current_params)

    # 회귀 가드: 1건 (또는 그 이상) 카운트되어야 함
    assert result["stop_loss_hits"] >= 1, (
        f"expected stop_loss_hits >= 1 (5/15 064400 -3.030%), "
        f"got {result['stop_loss_hits']}"
    )
    # 정확히 1건만 카운트됨 (다른 종목 -1.2% 는 임계 미달)
    assert result["stop_loss_hits"] == 1, (
        f"expected stop_loss_hits == 1, got {result['stop_loss_hits']}"
    )
    # 회귀 가드: loss_count / max_loss_pct 도 같이 검증
    assert result["loss_count"] == 2
    assert result["max_loss_pct"] == pytest.approx(-3.030, abs=0.01)


# ---------------------------------------------------------------------------
# Case E — LTV intraday 만 정의된 케이스
# ---------------------------------------------------------------------------


def test_ltv_intraday_only_returns_intraday():
    """`intraday_stop_loss` 단일 정의 (overnight_stop_loss 부재) → -3.0 반환.

    candidates = [-3.0], min(candidates) = -3.0.
    """
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    params = {"intraday_stop_loss": -3.0}
    result = _normalize_stop_loss_rate(params)
    assert result == -3.0, f"expected -3.0 (intraday 만 정의), got {result}"


# ---------------------------------------------------------------------------
# Case F — 혼합: stop_loss_rate + intraday_stop_loss 동시 존재
# ---------------------------------------------------------------------------


def test_mixed_keys_returns_most_conservative():
    """`stop_loss_rate=-3.5` + `intraday_stop_loss=-2.5` 동시 존재.

    candidates = [-3.5, -2.5], min(candidates) = -3.5 (절대값 큰 = 가장 보수적).

    실제 운영에서 발생할 수 없는 혼합 케이스지만, 알고리즘의 명확한 우선순위
    검증. min(candidates) 정책이 LTV 분리 키만 있는 일반 경우와 일관되게 작동.
    """
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    params = {"stop_loss_rate": -3.5, "intraday_stop_loss": -2.5}
    result = _normalize_stop_loss_rate(params)
    assert result == -3.5, f"expected -3.5 (혼합, 절대값 큰 쪽), got {result}"


# ---------------------------------------------------------------------------
# Edge cases — 회귀 보강 (양수 값, None 값)
# ---------------------------------------------------------------------------


def test_positive_value_ignored():
    """양수 손절 임계는 무의미 — `_normalize_stop_loss_rate` 가 무시.

    음수만 손절 임계로 인정. params 가 잘못 설정된 케이스 (예: stop_loss_rate=2.0)
    가 들어와도 다른 후보가 음수면 그쪽 선택. 후보 모두 양수면 0.0.
    """
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    # 양수만 있는 케이스 → 0.0
    params_all_positive = {"stop_loss_rate": 2.0, "intraday_stop_loss": 1.5}
    assert _normalize_stop_loss_rate(params_all_positive) == 0.0

    # 양수 + 음수 혼합 → 음수만 선택
    params_mixed = {"stop_loss_rate": 2.0, "intraday_stop_loss": -2.5}
    assert _normalize_stop_loss_rate(params_mixed) == -2.5


def test_none_values_handled_safely():
    """`None` 값은 `_safe_float` 가 0.0 으로 변환 — 그러나 음수 필터로 자동 skip.

    Supabase 응답에서 키 자체가 없는 케이스(`.get()` → None) 와 동등 처리.
    """
    from src.engine.recommendation_metrics import _normalize_stop_loss_rate

    params = {"stop_loss_rate": None, "intraday_stop_loss": -2.5}
    result = _normalize_stop_loss_rate(params)
    assert result == -2.5
