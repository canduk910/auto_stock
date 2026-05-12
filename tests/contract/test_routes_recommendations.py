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
