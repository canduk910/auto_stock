"""cycle295 Red — (A) 축 · **라우트 표면에서 갭 다이얼 소멸** (G-D4).

명세 = `_workspace/red/cycle295_gap_hold_removal_spec.md` §5-1 G-D4 · §6-1
행위 자매 = `tests/unit/engine/test_cycle295_gap_hold_removed.py`
AST 자매 = `tests/unit/ast/test_cycle295_ast_gap_hold_removed.py`

## 🔴 필드 삭제의 실패 모드는 422 가 아니라 **무음**이다 [실측 — pydantic 2.11.2]

`TickChannelModeRequest` 는 `model_config` 를 두지 않아 기본이 `extra="ignore"` 다.
`gap_hold_enabled` 필드를 뺀 모델에 `{"mode":"enforce","gap_hold_enabled":false}` 를
넣으면 **검증을 통과**하고 그 키는 조용히 버려진다. 즉 `src/realtime/CLAUDE.md:315`
의 런북 curl 이 사고 중에 **HTTP 200 / success:true** 를 돌려주며 아무 일도 안 한다.

### 결정 — **422 로 바꾸지 않는다. 조용히 무시한다.**

근거 = 같은 요청의 `mode` 킬스위치까지 막히기 때문이다. 그 카드는 사고 중에 반드시
눌려야 하고, 운영자가 옛 런북을 복사해 붙여 넣었다는 이유로 `mode="off"` 가 422 로
튕기면 이 사이클이 없앤 위험보다 큰 위험을 새로 만든다. 대신 **런북을 같은 커밋에서
지우고**(§6-1) 이 파일이 그 무시를 못박아 운영자가 "껐다" 고 오해하지 않게 한다.

⚠️ 이 네 필드는 **cycle295 이전 테스트 0건**이었다(cycle293 이 지적한 "킬스위치 라우트
테스트 0건" 의 재현). 지우면서 처음 테스트가 생긴다.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.asyncio

#: 09-14 제도 변경(K6) **이후**. UTC 01:00 = KST 10:00 (정규장 중, 전환 창 밖).
_FROZEN_UTC = "2026-09-15 01:00:00"
DAY = _dt.date(2026, 9, 15)
OFFSET = 300

#: 🔴 응답에서 사라져야 하는 키.
_FORBIDDEN_GET_KEYS = ("gap_hold_enabled", "gap_config_key", "nxt_gap_window")
_FORBIDDEN_PUT_KEYS = ("gap_hold_enabled", "gap_persisted")

#: 🔵 양성 대조군 — 같은 응답에 반드시 남아야 하는 키.
_REQUIRED_GET_KEYS = (
    "mode", "stored", "default", "valid_modes", "config_key",
    "switch_enabled", "switch_offset_secs", "switch_config_key", "switch_windows",
)
_REQUIRED_PUT_KEYS = ("mode", "persisted", "switch_enabled", "switch_persisted")


@pytest.fixture(autouse=True)
def _isolate():
    from src.engine import tick_channel_clock, tick_channel_mode

    for mod in (tick_channel_clock, tick_channel_mode):
        reset = getattr(mod, "reset_state_for_test", None)
        if callable(reset):
            reset()
    yield
    for mod in (tick_channel_clock, tick_channel_mode):
        reset = getattr(mod, "reset_state_for_test", None)
        if callable(reset):
            reset()


def _routes():
    from src.routes.realtime import get_tick_channel_mode, put_tick_channel_mode

    return get_tick_channel_mode, put_tick_channel_mode


def _request_model():
    from src.routes.realtime import TickChannelModeRequest

    return TickChannelModeRequest


def _patch_db(monkeypatch) -> list[tuple[str, object]]:
    """DB 쓰기·읽기를 기록기로 갈아끼운다. 반환 = 호출 로그."""
    from src.db import system_config

    calls: list[tuple[str, object]] = []

    async def _set_mode(mode: str) -> None:
        calls.append(("set_tick_channel_resolver_mode", mode))

    async def _set_switch(enabled: bool) -> None:
        calls.append(("set_tick_channel_switch_enabled", enabled))

    async def _get_mode():
        return "enforce"

    monkeypatch.setattr(system_config, "set_tick_channel_resolver_mode", _set_mode, raising=False)
    monkeypatch.setattr(
        system_config, "set_tick_channel_switch_enabled", _set_switch, raising=False,
    )
    monkeypatch.setattr(
        system_config, "get_tick_channel_resolver_mode", _get_mode, raising=False,
    )
    return calls


# ===========================================================================
# G-D4a — 요청 모델
# ===========================================================================
async def test_gd4a_request_model_has_no_gap_field_but_keeps_the_others():
    """🔴 G-D4a — `TickChannelModeRequest` 에 `gap_hold_enabled` 필드가 없다.

    🔵 양성 대조군 — `mode`(필수)와 `switch_enabled`(선택)는 **남는다**. 모델을 통째로
    비우는 퇴화를 죽인다.
    """
    model = _request_model()
    fields = set(model.model_fields)

    assert "gap_hold_enabled" not in fields, (
        f"요청 모델에 `gap_hold_enabled` 가 남았다: {sorted(fields)}"
    )
    assert not [f for f in fields if "gap" in f], (
        f"요청 모델에 갭 계열 필드가 이름만 바뀌어 남았다: {sorted(fields)}"
    )
    assert "mode" in fields and "switch_enabled" in fields, (
        f"🔵 양성 대조군 실패 — 살아남아야 할 필드가 사라졌다: {sorted(fields)}"
    )


async def test_gd4b_unknown_gap_key_is_silently_ignored_not_422():
    """🔴 G-D4b — 옛 런북 payload 는 **검증을 통과하고 조용히 버려진다**.

    422 로 바꾸지 않는 이유는 파일 상단 「결정」 절에 있다. 사고 중에 반드시 눌려야
    하는 `mode` 카드를 옛 키 하나 때문에 막을 수 없다.
    """
    model = _request_model()
    req = model(**{"mode": "off", "gap_hold_enabled": False})   # ← 예외 없이 통과해야 한다

    assert req.mode == "off"
    assert not hasattr(req, "gap_hold_enabled"), (
        "모델이 미지 키를 흡수해 속성으로 들고 있다 — `extra=\"ignore\"` 계약 위반"
    )


# ===========================================================================
# G-D4c — GET 응답 표면
# ===========================================================================
@freeze_time(_FROZEN_UTC)
async def test_gd4c_get_response_has_no_gap_keys(monkeypatch):
    """🔴 G-D4c — GET 응답에서 갭 3키가 사라진다.

    🔵 양성 대조군 — `mode`·`switch_enabled`·`switch_windows` 등 9키는 **남고**,
    `switch_windows` 는 아침 창 하나만 담는다(운영자가 화면 없이 확인하는 유일한 채널).
    """
    _patch_db(monkeypatch)
    get, _put = _routes()

    resp = await get()
    data = resp.data

    left = [k for k in _FORBIDDEN_GET_KEYS if k in data]
    assert not left, f"GET 응답에 갭 키가 남았다: {left} (전체 {sorted(data)})"
    assert not [k for k in data if "gap" in k], (
        f"GET 응답에 갭 계열 키가 이름만 바뀌어 남았다: {sorted(data)}"
    )

    missing = [k for k in _REQUIRED_GET_KEYS if k not in data]
    assert not missing, f"🔵 양성 대조군 실패 — GET 응답에서 사라진 키: {missing}"

    labels = [w["label"] for w in data["switch_windows"]]
    assert labels == ["pre_to_krx"], (
        f"GET 이 보여 주는 전환 창이 {labels} 다 — cycle295 는 전환 창을 아침 하나로 "
        "되돌린다(사용자 결정 「전환 1회」)"
    )


# ===========================================================================
# G-D4d — PUT 응답 표면 + 상태 불변
# ===========================================================================
@freeze_time(_FROZEN_UTC)
async def test_gd4d_put_with_the_old_gap_key_changes_nothing(monkeypatch):
    """🔴 G-D4d — 옛 런북 curl 이 **아무 상태도 바꾸지 않는다**.

    `{"mode":"enforce","gap_hold_enabled":true}` — 갭 홀드를 **켜려는** 요청이다.
    오늘은 그 요청이 실제로 3개 창을 만든다. cycle295 뒤에는 200 을 받고 창은 하나다.

    🔵 양성 대조군 3중 — ① `mode` 는 정상 적용·영속되고 ② 응답에 살아남는 4키가 있고
    ③ DB 쓰기 로그에 리졸버 모드 **한 건만** 남는다.
    """
    from src.engine import tick_channel_clock, tick_channel_mode

    calls = _patch_db(monkeypatch)
    _get, put = _routes()
    model = _request_model()

    resp = await put(model(**{"mode": "enforce", "gap_hold_enabled": True}))
    data = resp.data

    left = [k for k in _FORBIDDEN_PUT_KEYS if k in data]
    assert not left, f"PUT 응답에 갭 키가 남았다: {left} (전체 {sorted(data)})"
    assert not [k for k in data if "gap" in k], (
        f"PUT 응답에 갭 계열 키가 남았다: {sorted(data)}"
    )

    missing = [k for k in _REQUIRED_PUT_KEYS if k not in data]
    assert not missing, f"🔵 양성 대조군 실패 — PUT 응답에서 사라진 키: {missing}"
    assert resp.success is True and data["mode"] == "enforce"
    assert tick_channel_mode.current_mode() == "enforce", (
        "🔵 양성 대조군 실패 — `mode` 즉시 반영이 함께 죽었다"
    )
    assert calls == [("set_tick_channel_resolver_mode", "enforce")], (
        f"DB 쓰기가 리졸버 모드 한 건이 아니다: {calls} — 옛 갭 키가 아직 영속 경로를 탄다"
    )

    windows = tick_channel_clock.switch_windows(DAY, offset_secs=OFFSET)
    labels = [label for _s, _e, label in windows]
    assert labels == ["pre_to_krx"], (
        f"갭 홀드를 켜려는 요청 뒤 전환 창이 {labels} 가 됐다 — 요청이 실제로 먹었다. "
        "cycle295 에서 그 요청은 **조용히 무시**되어야 한다"
    )


@freeze_time(_FROZEN_UTC)
async def test_gd4e_switch_enabled_dial_still_works_end_to_end(monkeypatch):
    """🔵 G-D4e 양성 대조군 — **형제 다이얼은 살아 있다**.

    갭 다이얼을 지우면서 `switch_enabled` 까지 같이 지우는 것이 가장 흔한 과잉 제거다.
    그 다이얼은 "채널이 문제" 와 "전환이 문제" 를 가르는 유일한 카드이고 cycle295 는
    그것을 건드리지 않는다.
    """
    from src.engine import tick_channel_mode

    calls = _patch_db(monkeypatch)
    _get, put = _routes()
    model = _request_model()

    resp = await put(model(**{"mode": "enforce", "switch_enabled": False}))

    assert resp.data["switch_enabled"] is False
    assert resp.data["switch_persisted"] is True
    assert tick_channel_mode.switch_enabled() is False, "형제 다이얼 즉시 반영이 죽었다"
    assert ("set_tick_channel_switch_enabled", False) in calls
