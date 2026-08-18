"""strategies 라우트 계약 — /api/strategies/*"""

from __future__ import annotations

import pytest

from src.engine.strategy_base import Position

pytestmark = pytest.mark.contract


def test_get_strategies_returns_dict_with_strategy_keys(contract_env):
    r = contract_env.client.get("/api/strategies")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    # 4 전략이 모두 등록돼 있어야 한다
    assert "momentum" in data
    assert "volatility_breakout" in data
    assert "long_tail_volatility" in data
    assert "donchian_swing" in data


def test_update_weights_when_ratios_then_saved_verbatim(contract_env):
    """**2026-08-18 계약 변경 — 요청 바디 단위 = 비율(0.0~1.0)**.

    종전에는 프론트가 0~100 퍼센트로 보내고 라우트가 `v / 100 if v > 1` 로 단위를
    추론했다. 그 추론이 1%(=정수 1)를 100%로 저장하는 결함이라 폐기했다.
    이제 바디는 비율이고 저장값은 **무변환**이다(GET↔PUT 왕복 항등).
    """
    r = contract_env.client.put(
        "/api/strategies/weights",
        json={"weights": {"momentum": 0.4, "volatility_breakout": 0.3, "long_tail_volatility": 0.2, "donchian_swing": 0.1}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    # save_weights 호출 — 입력 비율 그대로
    saved = contract_env.calls.save_weights[-1]["weights"]
    assert saved["momentum"] == 0.4
    assert saved["donchian_swing"] == 0.1


def test_update_weights_when_below_min_invested_then_failure(contract_env):
    """이미 매수된 금액이 있는데 그보다 낮은 비중 변경 시도 → 실패."""
    sched = contract_env.scheduler
    # momentum 에 보유 — 매수금액 50_000_000 (전체 100_000_000 의 50%)
    momentum = sched.registry.get("momentum")
    momentum.state.positions["005930"] = Position(
        ticker="005930", buy_price=5_000_000, quantity=10,
        order_no="O1", strategy_id="momentum",
    )

    r = contract_env.client.put(
        "/api/strategies/weights",
        json={"weights": {"momentum": 0.1}},  # 10% — 50% 미만
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "최소" in body["message"]


def test_update_params_when_unknown_strategy_then_failure(contract_env):
    r = contract_env.client.put(
        "/api/strategies/ghost/params",
        json={"params": {"position_ratio": 0.3}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False


def test_update_params_when_known_strategy_then_applied(contract_env):
    r = contract_env.client.put(
        "/api/strategies/momentum/params",
        json={"params": {"position_ratio": 0.3}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    # 메모리 + DB 양쪽 반영
    momentum = contract_env.scheduler.registry.get("momentum")
    assert momentum.config.params["position_ratio"] == 0.3
    assert contract_env.calls.save_params
    assert contract_env.calls.save_params[-1]["strategy_id"] == "momentum"


def test_update_params_ignores_unknown_keys(contract_env):
    """파라미터 dict 에 없는 키는 무시 (silently dropped)."""
    r = contract_env.client.put(
        "/api/strategies/momentum/params",
        json={"params": {"some_unknown_key": 999}},
    )
    assert r.status_code == 200
    momentum = contract_env.scheduler.registry.get("momentum")
    assert "some_unknown_key" not in momentum.config.params


def test_get_auto_start_returns_value(contract_env):
    contract_env.state.auto_start_value = True
    r = contract_env.client.get("/api/strategies/system/auto-start")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["auto_start"] is True


def test_set_auto_start_persists_value(contract_env):
    r = contract_env.client.put(
        "/api/strategies/system/auto-start", json={"enabled": True}
    )
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert contract_env.state.auto_start_value is True
