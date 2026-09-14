"""cycle293 Green — 시세 채널 리졸버 **킬스위치 라우트** 회귀 가드.

적대 검증(HIGH) — `PUT/GET /api/realtime/tick-channel-mode` 를 참조하는 테스트가
리포 전체에 **0건**이었다. 절대 규칙 4 가 요구한 "즉시 반영 읽기 경로" 의 실체가
무가드였고, 다음 두 뮤테이션이 ESCAPED 였다:

* `apply_mode(mode)` → `current_mode()` 로 바꿔치기 = DB 에만 쓰고 **메모리 미반영**
  → 다음 폴링(≤5분)까지 킬스위치가 안 듣는다 = **cycle287 실패의 재현**.
* 어휘 검증 422 삭제 = 미지 값 무음 흡수 → 운영자가 무엇이 적용됐는지 모른다.

D6(보유 중 장중 재시작 금지)·D8(20:00~21:35 금지) 때문에 "다음 재시작에만 반영"
은 사실상 "영원히 못 끔" 이다 — 그래서 이 셋은 같은 커밋의 계약이다.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _isolate_mode():
    from src.engine import tick_channel_mode

    tick_channel_mode.reset_state_for_test()
    yield
    tick_channel_mode.reset_state_for_test()


def _routes():
    from src.routes.realtime import get_tick_channel_mode, put_tick_channel_mode

    return get_tick_channel_mode, put_tick_channel_mode


def _req(mode: str):
    from src.routes.realtime import TickChannelModeRequest

    return TickChannelModeRequest(mode=mode)


async def test_put_applies_to_memory_in_the_same_request(monkeypatch):
    """🔴 PUT 은 **같은 요청 안에서** 엔진 메모리를 덮는다 (재시작·폴링 대기 없음)."""
    from src.db import system_config
    from src.engine import scanner, tick_channel_mode

    saved: list[str] = []

    async def _set(mode: str) -> None:
        saved.append(mode)

    monkeypatch.setattr(system_config, "set_tick_channel_resolver_mode", _set, raising=False)
    _get, put = _routes()

    tick_channel_mode.set_mode_for_test("enforce")
    resp = await put(_req("off"))

    assert resp.success is True
    assert resp.data["mode"] == "off"
    assert resp.data["persisted"] is True
    assert saved == ["off"], "DB 저장이 안 됐다 — 재시작 후 되살아난다"
    assert tick_channel_mode.current_mode() == "off", (
        "DB 에만 쓰고 메모리를 안 덮었다 — 다음 폴링(≤5분)까지 킬스위치가 안 듣는다 "
        "= cycle287 실패의 재현"
    )
    # 리졸버가 그 즉시 현행 채널을 돌려주는지까지 확인한다(계약의 끝).
    assert scanner.tick_tr_id_for("003470") == scanner.TICK_TR_ID


async def test_put_rejects_unknown_mode_with_422(monkeypatch):
    """어휘 밖 값은 **422** — 조용히 기본값으로 흡수하지 않는다."""
    from src.db import system_config
    from src.engine import tick_channel_mode

    called: list[str] = []

    async def _set(mode: str) -> None:
        called.append(mode)

    monkeypatch.setattr(system_config, "set_tick_channel_resolver_mode", _set, raising=False)
    _get, put = _routes()
    tick_channel_mode.set_mode_for_test("enforce")

    with pytest.raises(HTTPException) as exc:
        await put(_req("ENFORCE_EVERYTHING"))

    assert exc.value.status_code == 422
    assert called == [], "미지 값이 DB 까지 갔다"
    assert tick_channel_mode.current_mode() == "enforce", "미지 값이 모드를 흔들었다"


async def test_put_applies_to_memory_even_when_db_write_fails(monkeypatch):
    """DB 저장이 실패해도 **메모리 반영은 시도**한다.

    사고 중 `off` 는 이번 프로세스에서 듣는 것이 먼저다(다음 재시작에 되살아나는
    것은 그 다음 문제). 실패 사실은 `persisted=false` + `message` 로 알린다.
    """
    from src.db import system_config
    from src.engine import tick_channel_mode

    async def _boom(mode: str) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(system_config, "set_tick_channel_resolver_mode", _boom, raising=False)
    _get, put = _routes()
    tick_channel_mode.set_mode_for_test("enforce")

    resp = await put(_req("off"))

    assert resp.data["mode"] == "off"
    assert resp.data["persisted"] is False
    assert resp.message, "DB 저장 실패를 응답이 침묵했다"
    assert tick_channel_mode.current_mode() == "off"


async def test_get_reports_memory_and_stored_and_vocabulary(monkeypatch):
    """GET 은 메모리 값·DB 값·유효 어휘·설정 키를 함께 준다(운영 판독 채널)."""
    from src.db import system_config
    from src.engine import tick_channel_mode

    async def _get_stored():
        return "enforce_low"

    monkeypatch.setattr(
        system_config, "get_tick_channel_resolver_mode", _get_stored, raising=False,
    )
    get, _put = _routes()
    tick_channel_mode.set_mode_for_test("observe")

    resp = await get()

    assert resp.data["mode"] == "observe"
    assert resp.data["stored"] == "enforce_low"
    assert resp.data["default"] == tick_channel_mode.DEFAULT_MODE
    assert sorted(resp.data["valid_modes"]) == ["enforce", "enforce_low", "observe", "off"]
    assert resp.data["config_key"] == "tick_channel_resolver_mode"


async def test_get_is_graceful_when_db_is_down(monkeypatch):
    """GET 은 DB 조회 실패에도 200 — 메모리 값은 항상 보여야 한다."""
    from src.db import system_config
    from src.engine import tick_channel_mode

    async def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(
        system_config, "get_tick_channel_resolver_mode", _boom, raising=False,
    )
    get, _put = _routes()
    tick_channel_mode.set_mode_for_test("enforce")

    resp = await get()
    assert resp.success is True
    assert resp.data["mode"] == "enforce"
    assert resp.data["stored"] is None
