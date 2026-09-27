"""cycle384 Red — `PUT /api/strategies/{id}/params` 로 `buy_paused` 켜고 끄기 (R01~R05).

명세 = `_workspace/red/cycle384_buy_paused_spec.md` §7 · §9.6 · §11(09-28 운영 절차) · §12(롤백)

- R01 PUT `{"buy_paused": true}` → 200 · `applied == {"buy_paused": True}` · `warnings == []` ·
  `save_params` 가 **병합 전체 dict** 로 1회(운영값 보존 — 설정 로드 뒤의 PUT 이 옳은 이유).
- R02 bool 이 아닌 값(`"true"`·`1`·`null`) → 422 `type_mismatch`, 아무것도 저장하지 않는다.
- R03 R01 직후 **같은 레지스트리**의 donchian 이 창 안 후보에 NONE — 재시작 없이. 롤백 PUT `false` 도 즉시.
- R04 AI 자문 적용 두 경로(수동 `POST /api/recommendations/{id}/apply` · 자동
  `auto_apply_recommendations`)가 `buy_paused` 를 바꾸지 못한다(`PARAM_RANGES` 화이트리스트).
- R05 `GET /api/strategies/params-schema` 에 bool · identity · editable · entry · 7전략.

파일 위치: 명세 §9 는 `tests/unit/routes/` 를 적었지만 실제 라우트·레지스트리 하네스(`contract_env`)가
`tests/contract/conftest.py` 에 있어 cycle382 R49 선례대로 여기에 둔다.

⚠️ `contract_env` 는 scheduler **싱글톤**을 쓴다 — 바꾼 params·후보는 끝에서 되돌린다.
Red 유효성: 7전략 `DEFAULT_PARAMS`·카탈로그에 키가 없어 PUT 이 `unknown_key` 로 422 다.
"""
from __future__ import annotations

import logging
from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.engine.strategy_base import Signal
from tests.unit.engine._cycle369_support import Clock, kst
from tests.unit.engine._cycle384_support import ALL7, T, U, pin_clocks

pytestmark = pytest.mark.contract

_SID = "donchian_swing"


@pytest.fixture
def donchian(contract_env):
    """싱글톤 donchian 의 params·후보·당일 매수 기록을 스냅샷하고 되돌린다."""
    st = contract_env.scheduler.registry.get(_SID)
    params = dict(st.config.params)
    cands = dict(st._candidates)
    bought = set(st._bought_today)
    signals = list(st.state.buy_signals)
    yield st
    st.config.params.clear()
    st.config.params.update(params)
    st._candidates.clear()
    st._candidates.update(cands)
    st._bought_today.clear()
    st._bought_today.update(bought)
    st.state.buy_signals[:] = signals


def _put(env, value, sid=_SID):
    return env.client.put(f"/api/strategies/{sid}/params", json={"params": {"buy_paused": value}})


# ===========================================================================
# R01 — PUT true: 즉시 메모리 반영 + 병합 전체 dict 저장
# ===========================================================================
def test_r01_put_true_applies_and_saves_merged_full_dict(contract_env, donchian):
    before = dict(donchian.config.params)
    axes = (donchian.config.enabled, donchian.config.weight)
    n0 = len(contract_env.calls.save_params)
    r = _put(contract_env, True)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["data"]["applied"] == {"buy_paused": True}
    assert body["data"]["warnings"] == [], "bool·enum 키는 range_unbounded 경고가 붙지 않아야 한다"
    assert donchian.config.params["buy_paused"] is True, "메모리 즉시 반영이 아니다"
    assert len(contract_env.calls.save_params) == n0 + 1
    saved = contract_env.calls.save_params[-1]
    assert saved["strategy_id"] == _SID
    want = {**before, "buy_paused": True}
    assert dict(saved["params"]) == want, "save_params 가 병합 전체 dict 가 아니다 — 운영값이 사라진다"
    for key in ("sizing_mode", "max_positions", "stop_loss_rate"):
        assert saved["params"][key] == before[key], f"{key} 가 바뀌었다"
    assert (donchian.config.enabled, donchian.config.weight) == axes, (
        "멈춤이 enabled/weight 를 건드렸다 — 보유분 손절 정지(M06)"
    )


@pytest.mark.parametrize("sid", ALL7)
def test_r01_every_strategy_accepts_the_key(contract_env, sid):
    st = contract_env.scheduler.registry.get(sid)
    assert st is not None, sid
    before = dict(st.config.params)
    try:
        r = _put(contract_env, False, sid)
        assert r.status_code == 200, f"{sid}: {r.text} (DEFAULT_PARAMS 누락이면 unknown_key — M11)"
        assert st.config.params["buy_paused"] is False
    finally:
        st.config.params.clear()
        st.config.params.update(before)


# ===========================================================================
# R02 — 모양 오류는 422 · 저장 0
# ===========================================================================
@pytest.mark.parametrize("value", ["true", 1, None], ids=["str_true", "one", "null"])
def test_r02_non_bool_is_422_type_mismatch_and_saves_nothing(contract_env, donchian, value):
    # 전제 — 키가 있어야 type_mismatch 까지 간다(없으면 unknown_key)
    assert "buy_paused" in donchian.config.params, "[Red] donchian params 에 buy_paused 없음"
    before = dict(donchian.config.params)
    n0 = len(contract_env.calls.save_params)
    r = _put(contract_env, value)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail[0]["code"] == "type_mismatch" and detail[0]["key"] == "buy_paused", detail
    assert donchian.config.params == before
    assert len(contract_env.calls.save_params) == n0


# ===========================================================================
# R03 — PUT 직후 같은 레지스트리의 donchian 이 멈춘다(재시작 없이) · 롤백 PUT 도 즉시
# ===========================================================================
def test_r03_put_takes_effect_on_the_live_registry_without_restart(contract_env, donchian, monkeypatch):
    clock = Clock(kst(9, 10))
    pin_clocks(monkeypatch, clock, _SID)
    cand = {"prev_close": 10_000, "donchian_high": 10_500, "ema60": 9_000, "atr": 200}
    donchian._candidates[T] = dict(cand)
    donchian._candidates[U] = dict(cand)
    assert donchian.check_buy_signal(U, 10_600, 10_100) == Signal.BUY, "양성 대조 — 창 안 후보는 산다"

    assert _put(contract_env, True).status_code == 200
    assert contract_env.scheduler.registry.get(_SID) is donchian
    assert donchian.check_buy_signal(T, 10_600, 10_100) == Signal.NONE, (
        "PUT 뒤에도 매수 신호 — 값을 캐시했거나(M07) 클래스 기본값에서 읽는다(M25)"
    )
    assert T not in donchian._bought_today

    assert _put(contract_env, False).status_code == 200            # 롤백 1순위
    assert donchian.check_buy_signal(T, 10_600, 10_100) == Signal.BUY, "롤백 PUT 이 즉시 먹지 않았다"


# ===========================================================================
# R04 — AI 자문 적용 두 경로가 buy_paused 를 바꾸지 못한다
# ===========================================================================
def _rec(params):
    return {
        "id": "R384", "strategy_id": _SID, "current_params": {},
        "recommended_params": params, "applied_params": {}, "reasoning": "..", "metrics": {},
        "status": "pending", "target_date": "2026-09-28",
        "created_at": "2026-09-27T20:00:00+09:00",
        "recommended_weight": None, "applied_weight": None,
    }


def test_r04_manual_apply_skips_buy_paused(contract_env, donchian, caplog):
    caplog.set_level(logging.INFO, logger="src.routes.recommendations")
    donchian.config.params["buy_paused"] = True
    contract_env.state.recommendations = [_rec({"buy_paused": False, "volume_multiplier": 2.5})]
    r = contract_env.client.post("/api/recommendations/R384/apply",
                                 json={"keys": ["buy_paused", "volume_multiplier"]})
    assert r.status_code == 200, r.text
    assert donchian.config.params["buy_paused"] is True, "AI 자문 수동 적용이 멈춤을 풀었다(M12)"
    assert donchian.config.params["volume_multiplier"] == 2.5, "과제거 — 정상 키는 적용돼야 한다"
    hit = [x.getMessage() for x in caplog.records if "[manual_apply_safeguard_skip]" in x.getMessage()]
    assert any("key=buy_paused" in m for m in hit), hit
    last = contract_env.calls.update_rec_status[-1]
    assert "buy_paused" not in (last.get("applied_params") or {})


async def test_r04_auto_apply_never_touches_buy_paused(contract_env, donchian, monkeypatch):
    from src.engine import recommendation_engine as re_mod

    donchian.config.params["buy_paused"] = True
    monkeypatch.setattr("src.db.system_config.get_auto_apply_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr("src.db.parameter_recommendations.list_pending_by_date",
                        AsyncMock(return_value=[_rec({"buy_paused": False})]))
    monkeypatch.setattr("src.db.parameter_recommendations.update_recommendation_status", AsyncMock())
    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())
    monkeypatch.setattr(re_mod, "save_params", AsyncMock(), raising=False)
    monkeypatch.setattr(re_mod, "save_weights", AsyncMock(), raising=False)
    await re_mod.auto_apply_recommendations(date(2026, 9, 28))
    assert donchian.config.params["buy_paused"] is True, "AI 자동 적용이 멈춤을 풀었다(M12)"


# ===========================================================================
# R05 — params-schema
# ===========================================================================
def test_r05_params_schema_lists_buy_paused_for_all_seven(contract_env):
    r = contract_env.client.get("/api/strategies/params-schema")
    assert r.status_code == 200
    data = r.json()["data"]
    rows = [p for p in data["params"] if p["key"] == "buy_paused"]
    assert len(rows) == 1, "[Red] params-schema 에 buy_paused 없음"
    row = rows[0]
    assert (row["type"], row["risk"], row["editable"], row["group"], row["auto_tunable"]) == (
        "bool", "identity", True, "entry", False)
    assert sorted(row["applies_to"]) == sorted(ALL7)
    by_sid = {s["strategy_id"]: s for s in data["strategies"]}
    for sid in ALL7:
        if sid in by_sid:
            assert "buy_paused" in by_sid[sid]["keys"], sid
            assert by_sid[sid]["defaults"]["buy_paused"] is False, sid
