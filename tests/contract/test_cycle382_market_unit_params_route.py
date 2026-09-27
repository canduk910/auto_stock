"""cycle382 Red — `PUT /api/strategies/{id}/params` 로 `market_unit_mode` 켜고 끄기 (R49 · 킬스위치 경로).

명세 = `_workspace/red/cycle382_market_unit_spec.md` §0-7 · §4 · §13(롤백 1순위 = PUT 즉시)

- 터틀 4전략: `off`·`shadow`·`enforce` 저장 → 메모리 즉시 반영 + DB 병합 저장.
- 선택지 밖(`"on"`) → 422 `not_in_choices`, 아무것도 저장하지 않는다(all-or-nothing).
- VB 등 3전략: 키가 없으니 422 `unknown_key`(조용히 버리지 않는다).

⚠️ `contract_env` 는 scheduler **싱글톤**을 쓴다 — 바꾼 params 는 끝에서 되돌린다.
Red 유효성: 4전략 `DEFAULT_PARAMS`·카탈로그에 키가 없어 kojiro PUT 이 `unknown_key` 로 422 다.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


@pytest.mark.parametrize("sid", ["kojiro", "donchian_swing", "bull_flag_breakout", "vcp_breakout"])
def test_r49_put_enforce_then_off_applies_immediately(contract_env, sid):
    strategy = contract_env.scheduler.registry.get(sid)
    before = dict(strategy.config.params)
    try:
        for value in ("enforce", "off", "shadow"):
            r = contract_env.client.put(f"/api/strategies/{sid}/params",
                                        json={"params": {"market_unit_mode": value}})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["success"] is True
            assert body["data"]["applied"] == {"market_unit_mode": value}
            assert strategy.config.params["market_unit_mode"] == value, "메모리 즉시 반영이 아니다"
            saved = contract_env.calls.save_params[-1]
            assert saved["strategy_id"] == sid
    finally:
        strategy.config.params.clear()
        strategy.config.params.update(before)


def test_r49_put_invalid_choice_is_422_and_saves_nothing(contract_env):
    strategy = contract_env.scheduler.registry.get("kojiro")
    before = dict(strategy.config.params)
    n_saves = len(contract_env.calls.save_params)
    r = contract_env.client.put("/api/strategies/kojiro/params",
                                json={"params": {"market_unit_mode": "on"}})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail[0]["code"] == "not_in_choices", detail
    assert strategy.config.params == before
    assert len(contract_env.calls.save_params) == n_saves


def test_r49_put_on_vb_is_unknown_key(contract_env):
    r = contract_env.client.put("/api/strategies/volatility_breakout/params",
                                json={"params": {"market_unit_mode": "enforce"}})
    assert r.status_code == 422
    assert r.json()["detail"][0]["code"] == "unknown_key"


def test_r49_params_schema_lists_market_unit_mode_for_turtle4_only(contract_env):
    r = contract_env.client.get("/api/strategies/params-schema")
    assert r.status_code == 200
    data = r.json()["data"]
    keys = {p["key"] for p in data["params"]}
    assert "market_unit_mode" in keys
    by_sid = {s["strategy_id"]: s for s in data["strategies"]}
    for sid in ("kojiro", "donchian_swing", "bull_flag_breakout", "vcp_breakout"):
        assert "market_unit_mode" in by_sid[sid]["keys"], sid
        assert by_sid[sid]["defaults"]["market_unit_mode"] == "shadow", sid
    for sid in ("momentum", "volatility_breakout", "long_tail_volatility"):
        if sid in by_sid:
            assert "market_unit_mode" not in by_sid[sid]["keys"], sid
