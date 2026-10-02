"""cycle399 Red — 섀도 모드 라우트 계약: params PUT (p01~p04) · 비중 PUT (w08~w10) · AI 자문 적용 (w11).

명세 정본 = `_workspace/red/cycle399_shadow_mode.md` §1 P1 · W4~W6 · §2

- p01 PUT `{"shadow_mode": true}` → 200 · 메모리 즉시 · `enabled`/`weight` 무접촉
- p02 bool 이 아니면 422 `type_mismatch` · 저장 0
- p03 AI 자문 두 경로(수동 적용 · 자동 적용)가 `shadow_mode` 를 바꾸지 못한다
- p04 params-schema 에 bool · identity · 7전략
- w08 섀도 전략 비중 0 PUT → 메모리 `enabled=True` · `save_weights(…, keep_enabled={sid})`
- w09 섀도가 없으면 `save_weights(weights)` 호출 모양 그대로(현행 byte 동일)
- w10 보유가 있는 섀도 전략 비중 0 → 여전히 거부(`[weight_zero_guard]`)
- w11 AI 자문 수동 적용의 비중 0 → 섀도 전략이면 `keep_enabled` 로 DB `enabled` 를 지킨다

⚠️ `contract_env` 는 scheduler **싱글톤**을 쓴다 — 바꾼 params·비중·켜짐은 끝에서 되돌린다.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.engine.strategy_base import Position
from tests.unit.engine._cycle384_support import ALL7

pytestmark = pytest.mark.contract

_SID = "vcp_breakout"      # contract_env 에서 자금 0 · 보유 0 인 전략


@pytest.fixture
def restore(contract_env):
    reg = contract_env.scheduler.registry
    snap = {s.strategy_id: (dict(s.config.params), s.config.enabled, s.config.weight,
                            dict(s.state.positions))
            for s in reg.all()}
    yield reg
    for s in reg.all():
        params, enabled, weight, positions = snap[s.strategy_id]
        s.config.params.clear()
        s.config.params.update(params)
        s.config.enabled = enabled
        s.config.weight = weight
        s.state.positions.clear()
        s.state.positions.update(positions)


@pytest.fixture
def weights_spy(monkeypatch):
    """`save_weights` 를 키워드까지 기록하는 가짜로 — 기존 계약 가짜는 `weights` 하나만 받는다."""
    calls: list[dict] = []

    async def fake(weights, **kw):
        calls.append({"weights": dict(weights), **kw})

    import src.db.strategy_config as sc

    monkeypatch.setattr(sc, "save_weights", fake, raising=False)
    monkeypatch.setattr("src.routes.recommendations.save_weights", fake, raising=False)
    monkeypatch.setattr("src.db.positions.load_all", AsyncMock(return_value=[]))
    return calls


def _put_param(env, value, sid=_SID):
    return env.client.put(f"/api/strategies/{sid}/params", json={"params": {"shadow_mode": value}})


# ===========================================================================
# p01 · p02 — params PUT
# ===========================================================================
def test_p01_put_true_applies_immediately_and_keeps_axes(contract_env, restore):
    st = restore.get(_SID)
    axes = (st.config.enabled, st.config.weight)
    before = dict(st.config.params)
    r = _put_param(contract_env, True)
    assert r.status_code == 200, f"[Red] {r.text}"
    assert r.json()["data"]["applied"] == {"shadow_mode": True}
    assert st.config.params["shadow_mode"] is True, "메모리 즉시 반영이 아니다"
    assert dict(contract_env.calls.save_params[-1]["params"]) == {**before, "shadow_mode": True}
    assert (st.config.enabled, st.config.weight) == axes, "섀도 켜기가 enabled/weight 를 건드렸다"


@pytest.mark.parametrize("sid", ALL7)
def test_p01_every_strategy_accepts_the_key(contract_env, restore, sid):
    r = _put_param(contract_env, False, sid)
    assert r.status_code == 200, f"{sid}: {r.text} (DEFAULT_PARAMS 누락이면 unknown_key)"


@pytest.mark.parametrize("value", ["true", 1, None], ids=["str_true", "one", "null"])
def test_p02_non_bool_is_422_and_saves_nothing(contract_env, restore, value):
    st = restore.get(_SID)
    assert "shadow_mode" in st.config.params, "[Red] params 에 shadow_mode 없음"
    before = dict(st.config.params)
    n0 = len(contract_env.calls.save_params)
    r = _put_param(contract_env, value)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail[0]["code"] == "type_mismatch" and detail[0]["key"] == "shadow_mode", detail
    assert st.config.params == before
    assert len(contract_env.calls.save_params) == n0


# ===========================================================================
# p03 — AI 자문 두 경로가 shadow_mode 를 바꾸지 못한다
# ===========================================================================
def _rec(params, weight=None, sid=_SID):
    return {
        "id": "R399", "strategy_id": sid, "current_params": {},
        "recommended_params": params, "applied_params": {}, "reasoning": "..", "metrics": {},
        "status": "pending", "target_date": "2026-10-05",
        "created_at": "2026-10-02T20:00:00+09:00",
        "recommended_weight": weight, "applied_weight": None,
    }


def test_p03_manual_apply_skips_shadow_mode(contract_env, restore):
    st = restore.get(_SID)
    st.config.params["shadow_mode"] = True
    contract_env.state.recommendations = [_rec({"shadow_mode": False})]
    r = contract_env.client.post("/api/recommendations/R399/apply", json={"keys": ["shadow_mode"]})
    assert r.status_code == 200, r.text
    assert st.config.params["shadow_mode"] is True, "AI 자문 수동 적용이 섀도를 껐다 — 실전 매수가 열린다"


async def test_p03_auto_apply_never_touches_shadow_mode(contract_env, restore, monkeypatch):
    from src.engine import recommendation_engine as re_mod

    st = restore.get(_SID)
    st.config.params["shadow_mode"] = True
    monkeypatch.setattr("src.db.system_config.get_auto_apply_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr("src.db.parameter_recommendations.list_pending_by_date",
                        AsyncMock(return_value=[_rec({"shadow_mode": False})]))
    monkeypatch.setattr("src.db.parameter_recommendations.update_recommendation_status", AsyncMock())
    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())
    monkeypatch.setattr(re_mod, "save_params", AsyncMock(), raising=False)
    monkeypatch.setattr(re_mod, "save_weights", AsyncMock(), raising=False)
    await re_mod.auto_apply_recommendations(date(2026, 10, 5))
    assert st.config.params["shadow_mode"] is True


def test_p04_params_schema_lists_shadow_mode(contract_env):
    r = contract_env.client.get("/api/strategies/params-schema")
    assert r.status_code == 200
    rows = [p for p in r.json()["data"]["params"] if p["key"] == "shadow_mode"]
    assert len(rows) == 1, "[Red] params-schema 에 shadow_mode 없음"
    row = rows[0]
    assert (row["type"], row["risk"], row["editable"], row["auto_tunable"]) == ("bool", "identity", True, False)
    assert sorted(row["applies_to"]) == sorted(ALL7)


# ===========================================================================
# w08 · w09 · w10 — 비중 PUT
# ===========================================================================
def test_w08_shadow_weight_zero_keeps_enabled_memory_and_db(contract_env, restore, weights_spy):
    st = restore.get(_SID)
    st.config.params["shadow_mode"] = True
    st.config.enabled = True
    st.config.weight = 0.1
    r = contract_env.client.put("/api/strategies/weights", json={"weights": {_SID: 0.0}})
    assert r.status_code == 200 and r.json()["success"] is True, r.text
    assert st.config.weight == 0.0
    assert st.config.enabled is True, "[Red] 메모리 — 섀도 전략이 꺼졌다"
    assert weights_spy[-1]["weights"] == {_SID: 0.0}
    assert set(weights_spy[-1].get("keep_enabled") or ()) == {_SID}, (
        "[Red] DB — 다음 재시작에 섀도 전략이 꺼진다(save_weights 가 enabled=False 를 쓴다)"
    )


def test_w09_no_shadow_call_shape_unchanged(contract_env, restore, weights_spy):
    st = restore.get(_SID)
    st.config.enabled = True
    st.config.weight = 0.1
    r = contract_env.client.put("/api/strategies/weights", json={"weights": {_SID: 0.0}})
    assert r.status_code == 200 and r.json()["success"] is True, r.text
    assert st.config.enabled is False, "섀도가 아닌 전략 weight=0 → enabled=False 현행"
    assert weights_spy[-1] == {"weights": {_SID: 0.0}}, "섀도가 없는데 save_weights 호출 모양이 바뀌었다"


def test_w10_held_shadow_strategy_weight_zero_still_rejected(contract_env, restore, weights_spy):
    st = restore.get(_SID)
    st.config.params["shadow_mode"] = True
    st.config.enabled = True
    st.config.weight = 0.1
    st.state.positions["005930"] = Position(ticker="005930", buy_price=70_000, quantity=1,
                                            order_no="O1", strategy_id=_SID,
                                            buy_date=date(2026, 10, 2), high_since_buy=70_000)
    r = contract_env.client.put("/api/strategies/weights", json={"weights": {_SID: 0.0}})
    assert r.json()["success"] is False, "보유 중 비중 0 은 섀도여도 거부해야 한다"
    assert st.config.weight == 0.1 and st.config.enabled is True
    assert weights_spy == []


# ===========================================================================
# w11 — AI 자문 수동 적용의 비중 0
# ===========================================================================
@pytest.mark.parametrize("shadow,keep", [(True, {_SID}), (False, None)], ids=["shadow", "non_shadow"])
def test_w11_manual_apply_weight_zero_keeps_shadow_enabled_in_db(
        contract_env, restore, weights_spy, shadow, keep):
    st = restore.get(_SID)
    st.config.params["shadow_mode"] = shadow
    st.config.enabled = True
    st.config.weight = 0.1
    contract_env.state.recommendations = [_rec({}, weight=0.0)]
    r = contract_env.client.post("/api/recommendations/R399/apply",
                                 json={"keys": [], "apply_weight": True})
    assert r.status_code == 200, r.text
    assert weights_spy, "비중 적용이 save_weights 를 부르지 않았다"
    got = weights_spy[-1]
    assert got["weights"] == {_SID: 0.0}
    if keep:
        assert set(got.get("keep_enabled") or ()) == keep, "[Red] 자문 적용이 섀도 전략을 DB 에서 끈다"
    else:
        assert "keep_enabled" not in got, "섀도가 아닌데 호출 모양이 바뀌었다"
