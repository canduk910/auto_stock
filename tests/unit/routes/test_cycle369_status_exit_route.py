"""cycle369 Red — R. 킬스위치 라우트 `GET/PUT /api/integrations/status-exit` (명세 §5).

두 축을 한 라우트로 다룬다(롤백 시나리오가 달라서 키는 둘):

| 필드 | DB 키 | 대상 |
|---|---|---|
| `sell_mode` | `system_config.status_exit_mode` | 보유 청산 |
| `buy_block_mode` | `system_config.status_buy_block_mode` | 당일 매수 차단 |

- PUT 바디 = `src.models.system_integrations.StatusExitModeRequest{sell_mode?, buy_block_mode?}`
- 둘 다 없으면 422 · 어휘(`enforce`·`observe`·`off`) 밖이면 422 + **아무것도 바꾸지 않음**
- DB 저장 실패여도 메모리는 반영(`persisted=false`) — 사고 중 `off` 가 먼저다(cycle293 선례)
- 반영 = `status_exit_watch.apply_mode(kind, mode)` **같은 요청 안에서**(재시작·폴링 대기 없음)

검증 패턴 = 라우트 함수 직접 await(사이클 127 anyio portal hang 차단 관례 ·
`test_cycle293_kill_switch_route.py`). 함수 이름에 묶이지 않도록 라우터에서 경로로 찾는다.
"""
from __future__ import annotations

import json
import logging

import pytest
from fastapi import HTTPException

pytestmark = [pytest.mark.unit, pytest.mark.real_status_watch]

_PATH = "/api/integrations/status-exit"


def _leaf():
    try:
        from src.engine import status_exit_watch
    except ImportError as exc:  # pragma: no cover — Red
        pytest.fail(f"[Red] status_exit_watch 미존재 — {exc}")
    return status_exit_watch


def _endpoint(method: str):
    from src.routes import system_integrations

    for r in system_integrations.router.routes:
        if getattr(r, "path", None) == _PATH and method in getattr(r, "methods", set()):
            return r.endpoint
    pytest.fail(f"[Red] {method} {_PATH} 라우트 미등록")


def _req(**body):
    from src.models.system_integrations import StatusExitModeRequest

    return StatusExitModeRequest(**body)


@pytest.fixture
def store(monkeypatch):
    """system_config getter/setter 4종 스텁 — 저장 호출 기록 + 저장값 반영."""
    from src.db import system_config as sc

    state = {"sell": None, "buy": None, "saved": [], "fail": False, "read_fail": False}

    async def _get_sell():
        if state["read_fail"]:
            raise RuntimeError("db down")
        return state["sell"]

    async def _get_buy():
        if state["read_fail"]:
            raise RuntimeError("db down")
        return state["buy"]

    async def _set_sell(mode):
        if state["fail"]:
            raise RuntimeError("db down")
        state["saved"].append(("status_exit_mode", mode))
        state["sell"] = mode

    async def _set_buy(mode):
        if state["fail"]:
            raise RuntimeError("db down")
        state["saved"].append(("status_buy_block_mode", mode))
        state["buy"] = mode

    monkeypatch.setattr(sc, "get_status_exit_mode_raw", _get_sell, raising=False)
    monkeypatch.setattr(sc, "get_status_buy_block_mode_raw", _get_buy, raising=False)
    monkeypatch.setattr(sc, "set_status_exit_mode", _set_sell, raising=False)
    monkeypatch.setattr(sc, "set_status_buy_block_mode", _set_buy, raising=False)
    return state


async def _put_expect_422(body: dict):
    """422 는 pydantic 검증이든 핸들러 HTTPException 이든 된다(구현 자유도)."""
    from pydantic import ValidationError

    try:
        req = _req(**body)
    except ValidationError:
        return
    with pytest.raises(HTTPException) as exc:
        await _endpoint("PUT")(req)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_r1_get_shape(store):
    store["sell"] = "observe"
    _leaf().apply_mode("sell", "observe")
    resp = await _endpoint("GET")()
    assert resp.success is True
    d = resp.data
    for key in ("sell_mode", "buy_block_mode", "stored", "default", "valid_modes",
                "config_keys", "fire_window", "today"):
        assert key in d, f"GET 응답에 `{key}` 없음"
    assert d["sell_mode"] == "observe"
    assert d["buy_block_mode"] == "enforce"
    assert sorted(d["stored"].values(), key=str) == sorted(["observe", None], key=str)
    assert d["default"] == "enforce"
    assert sorted(d["valid_modes"]) == ["enforce", "observe", "off"]
    keys = json.dumps(d["config_keys"])
    assert "status_exit_mode" in keys and "status_buy_block_mode" in keys
    fw = json.dumps(d["fire_window"])
    assert "09:00:30" in fw and "15:28" in fw, "창은 leaf 상수 유래 문자열"
    for part in ("blocks", "armed", "passes"):
        assert part in d["today"]


@pytest.mark.asyncio
async def test_r1b_get_is_graceful_when_db_is_down(store):
    store["read_fail"] = True
    resp = await _endpoint("GET")()
    assert resp.success is True
    assert set(resp.data["stored"].values()) == {None}


@pytest.mark.asyncio
async def test_r2_put_sell_mode_applies_immediately(store, caplog):
    caplog.set_level(logging.WARNING)
    resp = await _endpoint("PUT")(_req(sell_mode="observe"))
    assert resp.success is True
    assert resp.data["sell_mode"] == "observe"
    assert resp.data["persisted"] is True
    assert store["saved"] == [("status_exit_mode", "observe")], "buy 키까지 썼다(R6)"
    assert _leaf().current_modes()["sell"] == "observe", (
        "DB 에만 쓰고 메모리를 안 덮었다 — 다음 패스까지 킬스위치가 안 듣는다(cycle287 실패 재현)"
    )
    marks = [r for r in caplog.records if r.levelno >= logging.WARNING
             and r.getMessage().startswith("[status_exit_mode]")]
    assert marks and "sell_mode=observe" in marks[0].getMessage()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"sell_mode": "bogus"},
    {"buy_block_mode": "ENFORCE_ALL"},
    {"sell_mode": "off", "buy_block_mode": "bogus"},
])
async def test_r3_out_of_vocabulary_is_422_and_changes_nothing(store, body):
    await _put_expect_422(body)
    assert store["saved"] == [], "어휘 밖 값이 DB 까지 갔다(부분 적용 금지)"
    assert _leaf().current_modes() == {"sell": "enforce", "buy": "enforce"}


@pytest.mark.asyncio
async def test_r4_empty_body_is_422(store):
    await _put_expect_422({})
    assert store["saved"] == []


@pytest.mark.asyncio
async def test_r5_db_write_failure_still_applies_memory(store):
    store["fail"] = True
    resp = await _endpoint("PUT")(_req(sell_mode="off", buy_block_mode="off"))
    assert resp.data["persisted"] is False
    assert resp.message, "DB 저장 실패를 응답이 침묵했다"
    assert _leaf().current_modes() == {"sell": "off", "buy": "off"}


@pytest.mark.asyncio
async def test_r6_buy_only_leaves_sell_untouched(store):
    _leaf().apply_mode("sell", "observe")
    resp = await _endpoint("PUT")(_req(buy_block_mode="off"))
    assert store["saved"] == [("status_buy_block_mode", "off")]
    assert _leaf().current_modes() == {"sell": "observe", "buy": "off"}
    assert resp.data["buy_block_mode"] == "off" and resp.data["sell_mode"] == "observe"


def test_r8_request_model_fields():
    from src.models.system_integrations import StatusExitModeRequest

    fields = set(StatusExitModeRequest.model_fields)
    assert fields == {"sell_mode", "buy_block_mode"}
