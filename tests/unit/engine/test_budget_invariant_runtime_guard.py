"""불변식 `position_ratio × max_positions ≤ 1.0` 런타임 가드 (2026-08-08).

## 배경 (사각 실증)

kojiro DB 값이 `ratio 0.20 × maxp 6 = 1.2 > 1.0` 로 불변식을 위반한 채 운영됐다.
기존 가드는 두 경로만 검사한다:
  - C-DEFAULT (AST): 소스 `DEFAULT_PARAMS` 리터럴만 — DB 런타임 값은 못 봄
  - C-CROSS (`_validate_recommendations`): AI 추천만 — 운영자 수동 apply 는 못 봄

즉 **운영자 수동 `PUT /api/strategies/{id}/params` 또는 DB 직접 수정**이 불변식을
우회하는 사각이 있었고, 이번 1.2 위반이 정확히 그 경로로 생겼다. 금전 초과매수는
`_apply_budget_limit` 이 부분매수로 흡수하지만(피해 0), 정직도가 무너지고 마지막
슬롯에서 리스크 정규화가 깨진다.

## 시정 — 부트 config-load 후 실행값 검증 (관찰 WARNING, 배제 0)

`portfolio_risk.check_budget_invariant(strategies)` 순수 함수가 실행 params 로
`position_ratio × max_positions ≤ 1.0` 을 검증하고 위반 목록을 반환한다.
boot_manager 가 config-load 직후 호출해 WARNING 을 남긴다 — **매수/청산 미개입**
(관찰 전용). fail-open(파라미터 결측/비정상은 위반 아님으로 skip).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from src.engine import portfolio_risk

pytestmark = pytest.mark.unit


def _strat(sid, ratio, maxp):
    params = {}
    if ratio is not None:
        params["position_ratio"] = ratio
    if maxp is not None:
        params["max_positions"] = maxp
    return SimpleNamespace(strategy_id=sid, config=SimpleNamespace(params=params))


def test_detects_ratio_maxp_violation():
    """kojiro 1.2 위반 실측 재현 — 위반 목록에 잡힌다."""
    strategies = [_strat("kojiro", 0.20, 6), _strat("donchian_swing", 0.18, 3)]
    violations = portfolio_risk.check_budget_invariant(strategies)
    assert any(v["strategy_id"] == "kojiro" for v in violations)
    koj = next(v for v in violations if v["strategy_id"] == "kojiro")
    assert koj["product"] == pytest.approx(1.2, abs=1e-9)


def test_no_violation_when_within_invariant():
    """0.166×6=0.996, 0.20×5=1.0 — 위반 없음(경계 1.0 포함)."""
    strategies = [_strat("kojiro", 0.166, 6), _strat("x", 0.20, 5)]
    assert portfolio_risk.check_budget_invariant(strategies) == []


def test_fail_open_on_missing_params():
    """파라미터 결측/비정상 전략은 위반 아님(skip) — 가드가 부팅을 막지 않는다."""
    strategies = [
        _strat("no_ratio", None, 5),
        _strat("no_maxp", 0.2, None),
        SimpleNamespace(strategy_id="broken", config=None),
    ]
    assert portfolio_risk.check_budget_invariant(strategies) == []


def test_float_precision_boundary():
    """0.1667×6=1.0002 는 위반, 0.166×6=0.996 은 아님 (부동소수 경계)."""
    assert portfolio_risk.check_budget_invariant([_strat("a", 0.1667, 6)])
    assert portfolio_risk.check_budget_invariant([_strat("b", 0.166, 6)]) == []


def test_pure_function_no_mutation():
    """관찰 전용 — 입력 전략/params 무변경."""
    s = _strat("kojiro", 0.20, 6)
    before = dict(s.config.params)
    portfolio_risk.check_budget_invariant([s])
    assert s.config.params == before


def test_module_stays_registry_free():
    """portfolio_risk 는 registry/매매 hot path 미참조 (8영역 무관 순수 모듈)."""
    src = inspect.getsource(portfolio_risk)
    assert "from src.engine.risk" not in src
    assert "from src.engine.order_engine" not in src


def test_boot_manager_wires_the_guard():
    """boot_manager 가 config-load 후 가드를 호출한다 (dead code 방지)."""
    from src.engine import boot_manager

    src = inspect.getsource(boot_manager)
    assert "check_budget_invariant" in src, (
        "부트가 불변식 가드를 호출해야 한다 — 수동 DB apply 사각 차단"
    )
