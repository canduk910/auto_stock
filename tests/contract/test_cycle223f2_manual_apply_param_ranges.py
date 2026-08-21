"""사이클 223-F2 Red — 수동 apply 라우트의 PARAM_RANGES 화이트리스트 재검증.

## 결함 (리뷰 F2, MEDIUM → 실질 최우선)

사이클 223 S1 이 `PARAM_RANGES`/`INT_PARAMS` 에서 `breakout_fail_n_days`·`atr_trail_mult`
두 청산 정체성 상수를 제거했는데, **그 제거가 실제 구멍을 못 막았다**:

    src/routes/recommendations.py
    :65   valid_keys = set(req.keys) & set(recommended_params.keys())   ← 화이트리스트 없음
    :139  for k in valid_keys:
    :141      strategy.config.params[k] = recommended_params[k]

자동 경로(`recommendation_engine.auto_apply_recommendations`)에는
`if k not in PARAM_RANGES: [auto_apply_safeguard_skip]` 가드가 있는데 **수동 경로에만 없다**.
라이브 이탈값(`breakout_fail_n_days=2`, `atr_trail_mult=1.8`)이 들어온 경로가 바로 여기로
추정된다. 2026-08-08 kojiro `ratio×maxp=1.2`(운영자 수동 DB apply 사각)와 동일 클래스.

**운영 실측**: 자문 131건 중 30건이 두 키를 담고 있고 그중 `status=pending` 1건
(2026-08-20 donchian_swing, `breakout_fail_n_days: 3`)이 **지금도 UI 에서 적용 가능**하다.

## 계약

1. `valid_keys` 는 `set(req.keys) ∩ recommended_params ∩ PARAM_RANGES`.
2. 걸러진 키는 `strategy.config.params` 를 **바꾸지 않고** `applied_params` 에도 안 들어간다.
3. 걸러진 사유가 로그로 남는다 — 자동 경로 `[auto_apply_safeguard_skip] key=… reason=…`
   와 **같은 계열** 태그 + `reason='out_of_param_ranges'`.
4. **과제거 금지** — 같은 요청의 정상 키(PARAM_RANGES 등재)는 그대로 적용된다.
5. 전 키가 걸러지면 **조용한 성공 금지** (운영자가 "적용됐다"고 오인하면 안 된다).
6. `apply_weight` 경로 불변 (이번 범위 밖).
"""

from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.contract

_ROUTE_LOGGER = "src.routes.recommendations"
_BLOCKED = ("breakout_fail_n_days", "atr_trail_mult")


def _donchian_rec(rec_id="R1", params=None, status="pending"):
    return {
        "id": rec_id,
        "strategy_id": "donchian_swing",
        "current_params": {},
        "recommended_params": params if params is not None else {"breakout_fail_n_days": 3},
        "applied_params": {},
        "reasoning": "..",
        "metrics": {},
        "status": status,
        "target_date": "2026-08-20",
        "created_at": "2026-08-20T20:00:00+09:00",
        "recommended_weight": None,
        "applied_weight": None,
    }


@pytest.fixture
def donchian_env(contract_env):
    """donchian 청산 파라미터 스냅샷/복원 (테스트 간 누수 차단)."""
    st = contract_env.scheduler.registry.get("donchian_swing")
    snapshot = dict(st.config.params)
    yield contract_env
    st.config.params.clear()
    st.config.params.update(snapshot)


# ===========================================================================
# F2-1 — 차단 키만 요청 → params 불변 + save_params 미호출 + 성공 아님
# ===========================================================================
@pytest.mark.parametrize("key,value", [("breakout_fail_n_days", 3), ("atr_trail_mult", 1.8)])
def test_f2_1_excluded_key_is_not_applied(donchian_env, key, value):
    env = donchian_env
    st = env.scheduler.registry.get("donchian_swing")
    before = st.config.params.get(key)
    env.state.recommendations = [_donchian_rec("R1", {key: value})]

    r = env.client.post("/api/recommendations/R1/apply", json={"keys": [key]})

    assert r.status_code == 200
    assert st.config.params.get(key) == before, (
        f"F2: PARAM_RANGES 미등재 키 '{key}' 가 수동 apply 로 적용됐다 "
        f"(before={before}, after={st.config.params.get(key)})"
    )
    assert env.calls.save_params == [], "F2: 차단 키만 있는 요청은 save_params 를 호출하지 않는다"


# ===========================================================================
# F2-2 — 전 키 차단 시 조용한 성공 금지
# ===========================================================================
def test_f2_2_all_keys_blocked_is_not_a_silent_success(donchian_env):
    env = donchian_env
    env.state.recommendations = [
        _donchian_rec("R1", {"breakout_fail_n_days": 3, "atr_trail_mult": 1.8})
    ]

    r = env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": ["breakout_fail_n_days", "atr_trail_mult"]},
    )
    body = r.json()

    assert body["success"] is False, (
        "F2: 전 키가 안전가드에 걸렸는데 success=True 면 운영자가 '적용됐다'고 오인한다 "
        f"— got {body}"
    )
    msg = body.get("message") or ""
    assert any(k in msg for k in _BLOCKED), (
        f"F2: 차단 사유/키가 응답 메시지에 드러나야 한다 — got {msg!r}"
    )
    # 상태 전이도 일어나지 않는다 (applied/partial 로 마킹 금지)
    assert env.calls.update_rec_status == [], (
        "F2: 아무것도 적용 안 됐는데 status 전이를 기록하면 안 된다"
    )


# ===========================================================================
# F2-3 — 과제거 금지: 정상 키가 섞이면 그건 적용된다
# ===========================================================================
def test_f2_3_normal_keys_still_applied_when_mixed(donchian_env):
    env = donchian_env
    st = env.scheduler.registry.get("donchian_swing")
    before_n = st.config.params.get("breakout_fail_n_days")
    env.state.recommendations = [
        _donchian_rec("R1", {"volume_multiplier": 2.5, "breakout_fail_n_days": 3})
    ]

    r = env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": ["volume_multiplier", "breakout_fail_n_days"]},
    )
    body = r.json()

    assert body["success"] is True, f"F2: 정상 키는 적용돼야 한다 — got {body}"
    assert st.config.params.get("volume_multiplier") == 2.5, "F2: 과제거 — 정상 키가 안 먹었다"
    assert st.config.params.get("breakout_fail_n_days") == before_n, (
        "F2: 차단 키는 여전히 적용 금지"
    )
    assert env.calls.save_params, "F2: 정상 키가 하나라도 있으면 save_params 는 호출된다"
    last = env.calls.update_rec_status[-1]
    assert last["applied_params"] == {"volume_multiplier": 2.5}, (
        f"F2: applied_params 에 차단 키가 새면 안 된다 — got {last['applied_params']}"
    )
    assert last["status"] == "partial", (
        "F2: 차단 키가 잔여로 남으므로 'applied' 가 아니라 'partial' 이다"
    )


# ===========================================================================
# F2-4 — 스킵 로그 (자동 경로 `[auto_apply_safeguard_skip]` 와 같은 계열)
# ===========================================================================
def test_f2_4_skip_is_logged_with_reason(donchian_env, caplog):
    caplog.set_level(logging.INFO, logger=_ROUTE_LOGGER)
    env = donchian_env
    env.state.recommendations = [
        _donchian_rec("R1", {"volume_multiplier": 2.5, "atr_trail_mult": 1.8})
    ]

    env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": ["volume_multiplier", "atr_trail_mult"]},
    )

    msgs = [r.getMessage() for r in caplog.records]
    hit = [m for m in msgs if "manual_apply_safeguard_skip" in m]
    assert hit, (
        "F2: 걸러진 키는 사유와 함께 로그로 남아야 한다 "
        f"(자동 경로 `[auto_apply_safeguard_skip]` 와 같은 계열) — got {msgs}"
    )
    assert any("atr_trail_mult" in m for m in hit), f"F2: 스킵 로그에 키 이름 부재 — {hit}"
    assert any("out_of_param_ranges" in m for m in hit), (
        f"F2: 스킵 사유(reason='out_of_param_ranges') 부재 — {hit}"
    )


# ===========================================================================
# F2-5 — 기존 정상 경로 회귀 (momentum 2키 전량 적용)
# ===========================================================================
def test_f2_5_existing_whitelisted_flow_unchanged(contract_env):
    contract_env.state.recommendations = [{
        "id": "R1", "strategy_id": "momentum",
        "current_params": {"position_ratio": 0.25},
        "recommended_params": {"position_ratio": 0.3, "stop_loss_rate": -8.0},
        "applied_params": {}, "reasoning": "..", "metrics": {},
        "status": "pending", "target_date": "2026-08-20",
        "created_at": "2026-08-20T20:00:00+09:00",
    }]
    r = contract_env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": ["position_ratio", "stop_loss_rate"]},
    )
    assert r.json()["success"] is True
    assert contract_env.calls.update_rec_status[-1]["status"] == "applied"


# ===========================================================================
# F2-6 — apply_weight 경로 불변 (범위 밖): 차단 키만 있어도 weight 는 적용된다
# ===========================================================================
def test_f2_6_apply_weight_path_untouched(donchian_env):
    env = donchian_env
    st = env.scheduler.registry.get("donchian_swing")
    prev_weight = st.config.weight
    st.config.weight = 0.5                      # 감액 방향 = N1 Σ 가드 무조건 통과
    rec = _donchian_rec("R1", {"atr_trail_mult": 1.8})
    rec["recommended_weight"] = 0.05
    env.state.recommendations = [rec]
    before = st.config.params.get("atr_trail_mult")

    r = env.client.post(
        "/api/recommendations/R1/apply",
        json={"keys": ["atr_trail_mult"], "apply_weight": True},
    )
    body = r.json()

    assert body["success"] is True, f"F2: weight 적용 경로는 이번 범위 밖 — got {body}"
    assert env.calls.save_weights, "F2: apply_weight 경로 회귀 — save_weights 미호출"
    assert st.config.params.get("atr_trail_mult") == before, "F2: 차단 키는 여전히 적용 금지"
    msg = body.get("message") or ""
    assert "차단" in msg or "안전" in msg, (
        f"F2: weight 만 먹은 경우에도 키가 걸러졌다는 사실이 메시지에 드러나야 한다 — {msg!r}"
    )
    st.config.weight = prev_weight
