"""recommendations 라우트 계약 — /api/recommendations/*"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


def _make_rec(rec_id="R1", strategy="momentum", status="pending"):
    return {
        "id": rec_id,
        "strategy_id": strategy,
        "current_params": {"position_ratio": 0.25},
        "recommended_params": {"position_ratio": 0.3, "stop_loss_rate": -8.0},
        "applied_params": {},
        "reasoning": "..",
        "metrics": {},
        "status": status,
        "target_date": "2026-05-08",
        "created_at": "2026-05-08T16:00:00+09:00",
    }


def test_list_recommendations_returns_array(contract_env):
    contract_env.state.recommendations = [_make_rec("R1"), _make_rec("R2")]
    r = contract_env.client.get("/api/recommendations")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert len(body["data"]) == 2


def test_get_recommendation_when_not_found_then_failure(contract_env):
    r = contract_env.client.get("/api/recommendations/ghost")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "찾을 수 없" in body["message"]


def test_get_recommendation_when_found_then_returns_it(contract_env):
    contract_env.state.recommendations = [_make_rec("R1")]
    r = contract_env.client.get("/api/recommendations/R1")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["id"] == "R1"


def test_apply_recommendation_when_status_not_pending_then_rejected(contract_env):
    contract_env.state.recommendations = [_make_rec("R1", status="applied")]
    r = contract_env.client.post(
        "/api/recommendations/R1/apply", json={"keys": ["position_ratio"]}
    )
    assert r.status_code == 200
    assert r.json()["success"] is False


def test_apply_recommendation_with_subset_keys_then_partial(contract_env):
    """recommended_params 에 2개 키, body 에 1개만 → status=partial."""
    contract_env.state.recommendations = [_make_rec("R1")]
    r = contract_env.client.post(
        "/api/recommendations/R1/apply", json={"keys": ["position_ratio"]}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    # 적용된 전략 파라미터 변경 확인
    momentum = contract_env.scheduler.registry.get("momentum")
    assert momentum.config.params["position_ratio"] == 0.3
    # status 갱신 호출
    last = contract_env.calls.update_rec_status[-1]
    assert last["status"] == "partial"
    assert last["applied_params"] == {"position_ratio": 0.3}


def test_apply_recommendation_with_all_keys_then_applied(contract_env):
    contract_env.state.recommendations = [_make_rec("R1")]
    r = contract_env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": ["position_ratio", "stop_loss_rate"]},
    )
    assert r.status_code == 200
    last = contract_env.calls.update_rec_status[-1]
    assert last["status"] == "applied"


def test_apply_recommendation_with_no_intersecting_keys_then_failure(contract_env):
    contract_env.state.recommendations = [_make_rec("R1")]
    r = contract_env.client.post(
        "/api/recommendations/R1/apply", json={"keys": ["nonexistent"]}
    )
    assert r.status_code == 200
    assert r.json()["success"] is False


def test_reject_recommendation_when_pending_then_status_rejected(contract_env):
    contract_env.state.recommendations = [_make_rec("R1")]
    r = contract_env.client.post("/api/recommendations/R1/reject")
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert contract_env.calls.update_rec_status[-1]["status"] == "rejected"


def test_reject_recommendation_when_already_applied_then_failure(contract_env):
    contract_env.state.recommendations = [_make_rec("R1", status="applied")]
    r = contract_env.client.post("/api/recommendations/R1/reject")
    assert r.status_code == 200
    assert r.json()["success"] is False


# ---------- Phase J4 (2026-05-12) — apply_weight 옵션 ----------


def _make_rec_with_weight(rec_id="R1", strategy="momentum", weight=0.35, notes=None):
    """J4 신규 필드 (recommended_weight / code_review_notes) 포함 픽스처."""
    rec = {
        "id": rec_id,
        "strategy_id": strategy,
        "current_params": {"position_ratio": 0.25},
        "recommended_params": {"position_ratio": 0.3},
        "applied_params": {},
        "reasoning": "..",
        "metrics": {},
        "status": "pending",
        "target_date": "2026-05-08",
        "created_at": "2026-05-08T16:00:00+09:00",
        "recommended_weight": weight,
        "code_review_notes": notes,
        "applied_weight": None,
    }
    return rec


def test_apply_weight_true_with_recommended_weight_sets_strategy_weight(contract_env):
    """apply_weight=true + recommended_weight=0.35 → save_weights 호출 + applied_weight 갱신."""
    contract_env.state.recommendations = [_make_rec_with_weight("R1", weight=0.35)]

    r = contract_env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": [], "apply_weight": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True

    # save_weights 호출 검증 (전략별 weight 갱신)
    assert len(contract_env.calls.save_weights) == 1
    assert contract_env.calls.save_weights[-1]["weights"] == {"momentum": 0.35}

    # update_recommendation_status 호출 시 applied_weight 포함
    last = contract_env.calls.update_rec_status[-1]
    assert last.get("applied_weight") == 0.35

    # 응답 데이터에 applied_weight 포함
    assert body["data"].get("applied_weight") == 0.35


def test_apply_weight_true_when_recommended_weight_is_null_then_failure(contract_env):
    """apply_weight=true 인데 recommended_weight 가 null 이면 400 (적용할 weight 없음)."""
    contract_env.state.recommendations = [_make_rec_with_weight("R1", weight=None)]

    r = contract_env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": [], "apply_weight": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "weight" in body["message"]

    # save_weights 호출 안 됨
    assert contract_env.calls.save_weights == []


def test_apply_keys_and_weight_simultaneously(contract_env):
    """apply_keys + apply_weight=true 동시 → 둘 다 적용."""
    rec = _make_rec_with_weight("R1", weight=0.4)
    contract_env.state.recommendations = [rec]

    r = contract_env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": ["position_ratio"], "apply_weight": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True

    # 1) 파라미터 적용
    momentum = contract_env.scheduler.registry.get("momentum")
    assert momentum.config.params["position_ratio"] == 0.3

    # 2) weight 적용
    assert contract_env.calls.save_weights[-1]["weights"] == {"momentum": 0.4}
    last = contract_env.calls.update_rec_status[-1]
    assert last.get("applied_weight") == 0.4


def test_apply_without_apply_weight_skips_save_weights(contract_env):
    """apply_weight 누락(False) 시 save_weights 호출 안 됨 (기존 동작 보존)."""
    contract_env.state.recommendations = [_make_rec_with_weight("R1", weight=0.35)]

    r = contract_env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": ["position_ratio"]},
    )
    assert r.status_code == 200
    assert r.json()["success"] is True

    # weight 는 적용 안 됨
    assert contract_env.calls.save_weights == []
    last = contract_env.calls.update_rec_status[-1]
    assert last.get("applied_weight") is None


# ---------- N1 (2026-08-18) — 자문 증액 Σ 사전 검증 ----------
#
# 배경: PUT /api/strategies/weights 가 Σ>1.0 을 거부하고 프론트 Settings 는 서버 저장값
#   Σ>1.01 이면 저장 버튼을 잠그므로, 이 경로가 무제한 증액하면 Settings 가 영구 잠긴다.
#   감액은 **항상** 통과해야 한다 — 오염된 Σ 를 되돌리는 유일한 복구 수단이기 때문이다.


@pytest.fixture
def weight_env(contract_env):
    """registry 의 config.weight 를 스냅샷/복원 (테스트 간 누수 차단)."""
    registry = contract_env.scheduler.registry
    snapshot = {s.strategy_id: s.config.weight for s in registry.all()}
    yield contract_env
    for s in registry.all():
        s.config.weight = snapshot[s.strategy_id]


def _set_weights(env, target: str, target_weight: float, others_total: float):
    """대상 전략 = target_weight, 나머지 전략에 others_total 을 첫 전략에 몰아준다."""
    registry = env.scheduler.registry
    others = [s for s in registry.all() if s.strategy_id != target]
    for s in others:
        s.config.weight = 0.0
    if others:
        others[0].config.weight = others_total
    registry.get(target).config.weight = target_weight


def test_apply_weight_increase_over_sum_limit_then_rejected(weight_env):
    """다른 전략 합 0.95 + 대상 현재 0.05 → recommended 0.30 (Σ=1.25) → 거부."""
    env = weight_env
    _set_weights(env, "momentum", target_weight=0.05, others_total=0.95)
    env.state.recommendations = [_make_rec_with_weight("R1", weight=0.30)]
    params_before = dict(env.scheduler.registry.get("momentum").config.params)

    r = env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": ["position_ratio"], "apply_weight": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "100%" in body["message"]

    # 저장 미수행 + 메모리 weight 불변
    assert env.calls.save_weights == []
    assert env.scheduler.registry.get("momentum").config.weight == 0.05
    # params 도 미적용 (early return 이 계약)
    assert env.calls.save_params == []
    assert env.calls.update_rec_status == []
    assert env.scheduler.registry.get("momentum").config.params == params_before


def test_apply_weight_increase_within_sum_limit_then_applied(weight_env):
    """다른 전략 합 0.60 + 대상 현재 0.05 → recommended 0.30 (Σ=0.90) → 통과."""
    env = weight_env
    _set_weights(env, "momentum", target_weight=0.05, others_total=0.60)
    env.state.recommendations = [_make_rec_with_weight("R1", weight=0.30)]

    r = env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": [], "apply_weight": True},
    )
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert env.calls.save_weights[-1]["weights"] == {"momentum": 0.30}
    assert env.scheduler.registry.get("momentum").config.weight == 0.30


def test_apply_weight_decrease_passes_even_when_sum_polluted(weight_env):
    """Σ=2.98 오염 상태에서도 감액(1.0 → 0.01)은 통과 — 복구 경로 보존 (핵심)."""
    env = weight_env
    _set_weights(env, "momentum", target_weight=1.0, others_total=1.98)
    total_before = sum(s.config.weight for s in env.scheduler.registry.all())
    assert total_before == pytest.approx(2.98)

    env.state.recommendations = [_make_rec_with_weight("R1", weight=0.01)]
    r = env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": [], "apply_weight": True},
    )
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert env.calls.save_weights[-1]["weights"] == {"momentum": 0.01}
    assert env.scheduler.registry.get("momentum").config.weight == 0.01


def test_apply_weight_same_value_reapply_passes(weight_env):
    """current == recommended (증액 아님) → Σ 초과 상태여도 통과."""
    env = weight_env
    _set_weights(env, "momentum", target_weight=0.50, others_total=0.90)
    env.state.recommendations = [_make_rec_with_weight("R1", weight=0.50)]

    r = env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": [], "apply_weight": True},
    )
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert env.calls.save_weights[-1]["weights"] == {"momentum": 0.50}


def test_apply_weight_false_skips_sum_check_and_applies_params(weight_env):
    """apply_weight=false 면 Σ 초과 recommended_weight 라도 검사 미발동 + params 정상 적용."""
    env = weight_env
    _set_weights(env, "momentum", target_weight=0.05, others_total=0.95)
    env.state.recommendations = [_make_rec_with_weight("R1", weight=0.90)]

    r = env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": ["position_ratio"]},
    )
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert env.calls.save_weights == []
    assert env.scheduler.registry.get("momentum").config.params["position_ratio"] == 0.3
    assert env.scheduler.registry.get("momentum").config.weight == 0.05


def test_apply_weight_sum_tolerance_is_single_source_of_truth():
    """허용오차는 strategies 라우트의 상수를 재사용한다 (단일 진실원)."""
    import src.routes.recommendations as _rec
    import src.routes.strategies as _st

    assert _rec._WEIGHT_SUM_TOLERANCE is _st._WEIGHT_SUM_TOLERANCE
