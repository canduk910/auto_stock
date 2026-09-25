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
    """**2026-09-11 계약 변경 (사이클 278)** — 예산 불변식이 422 로 강제된다.

    종전 본문은 momentum 에 `position_ratio=0.3` 을 보냈다. momentum 의
    `max_positions=4` 이므로 `0.3 × 4 = 1.2 > 1.0` 이라 그 payload 는 이제 422 다
    (한 전략이 배정 자금의 120% 를 청약하는 설정). 정상 저장 경로를 계속 재려고 값만
    `0.2`(= 0.8) 로 낮췄다 — 두 키를 함께 보내는 경로는 아래 케이스가 잰다.
    """
    r = contract_env.client.put(
        "/api/strategies/momentum/params",
        json={"params": {"position_ratio": 0.2}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["applied"] == {"position_ratio": 0.2}
    # 메모리 + DB 양쪽 반영
    momentum = contract_env.scheduler.registry.get("momentum")
    assert momentum.config.params["position_ratio"] == 0.2
    assert contract_env.calls.save_params
    assert contract_env.calls.save_params[-1]["strategy_id"] == "momentum"


def test_update_params_when_budget_keys_sent_together_then_applied(contract_env):
    """사이클 278 — 비중을 올리려면 동시 보유 종목수를 같은 저장에서 함께 줄인다.

    ⚠️ `contract_env` 는 scheduler **싱글톤**을 쓰고 params 를 되돌리지 않는다 —
    이 케이스가 바꾼 두 키는 끝에서 직접 복원한다(뒤 테스트 오염 차단).
    """
    momentum = contract_env.scheduler.registry.get("momentum")
    before = dict(momentum.config.params)
    try:
        r = contract_env.client.put(
            "/api/strategies/momentum/params",
            json={"params": {"position_ratio": 0.3, "max_positions": 3}},
        )
        assert r.status_code == 200
        assert r.json()["success"] is True
        assert momentum.config.params["position_ratio"] == 0.3
        assert momentum.config.params["max_positions"] == 3
    finally:
        momentum.config.params.clear()
        momentum.config.params.update(before)


def test_update_params_when_budget_invariant_violated_then_422(contract_env):
    """사이클 278 — `position_ratio × max_positions > 1.0` 은 422 이고 아무것도 저장되지 않는다."""
    momentum = contract_env.scheduler.registry.get("momentum")
    before = dict(momentum.config.params)

    r = contract_env.client.put(
        "/api/strategies/momentum/params",
        json={"params": {"position_ratio": 0.9, "stop_loss_rate": -6.0}},
    )

    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list) and detail[0]["code"] == "budget_invariant"
    assert momentum.config.params == before, "422 인데 통과분이 저장됐다 (all-or-nothing 위반)"


def test_update_params_when_unknown_key_then_422(contract_env):
    """**2026-09-11 계약 변경 (사이클 278)** — 미지 키는 조용히 버리지 않는다.

    종전 이름 `test_update_params_ignores_unknown_keys` 가 잰 것은 "오타가 성공 응답을
    받는다"였다. 오타·신규 키가 200 을 받고 무시되던 것이 이 사이클이 고친 결함이므로,
    같은 payload 가 이제 **422 `unknown_key`** 임을 잰다.
    """
    momentum = contract_env.scheduler.registry.get("momentum")

    r = contract_env.client.put(
        "/api/strategies/momentum/params",
        json={"params": {"some_unknown_key": 999}},
    )

    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list) and detail[0]["code"] == "unknown_key"
    assert detail[0]["key"] == "some_unknown_key"
    assert "some_unknown_key" not in momentum.config.params


def test_get_params_schema_returns_catalog_and_strategy_rows(contract_env):
    """사이클 278 — 편집 화면이 렌더에 쓰는 유일한 응답 (앱 경로 계약)."""
    r = contract_env.client.get("/api/strategies/params-schema")

    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    # cycle290 — 킬스위치 2키 등재로 99→101 · cycle300 — 일봉 깊이 스위치로 101→102 ·
    # cycle352 — 15:20 상한가 유지 확인 킬스위치로 102→103
    assert len(data["params"]) == 103
    assert {s["strategy_id"] for s in data["strategies"]} >= {"momentum", "kojiro"}
    momentum = next(s for s in data["strategies"] if s["strategy_id"] == "momentum")
    assert momentum["keys"] and set(momentum["params"]) == set(momentum["keys"])
    assert set(momentum["defaults"]) == set(momentum["keys"])


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
