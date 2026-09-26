"""cycle369 round 2 Red — Q1. 킬스위치가 조용히 되살아나지 않는다.

round-1 리뷰 3건이 같은 구멍을 재현했다(MEDIUM): `PUT /status-exit {"sell_mode":"off"}` 의
DB 쓰기가 실패하면(`persisted=false`) 메모리만 `off` 가 되고, 다음 패스의
`refresh_modes()` 가 DB 를 다시 읽어 **60초(매수)·300초(청산) 안에 enforce 로 되돌린다**.
사고 중 운영자가 끈 시장가 매도가 로그 한 줄 없이 다시 나간다.

## main-session 결정 Q1 (계약)

| 항목 | 계약 |
|---|---|
| 고정(pin) | `apply_mode(kind, mode, persisted=False)` = 그 축을 메모리에 **고정**한다 |
| 고정 수명 | `refresh_modes()` 는 고정된 축을 덮지 않는다 — 그 축의 **다음 성공 저장**(`persisted=True`) 또는 재시작(`reset_state_for_test`)까지 |
| 관측 | 고정 동안 `[status_exit_mode_pinned]` WARNING **1회/일** |
| 세대 번호 | 축마다 세대 번호 — PUT **전에** 시작한 refresh 의 결과는 버린다(in-flight 덮어쓰기 금지) |
| 망가진 저장 행 | `{"mode":…}`(value 없음) · `{"value": null}` · JSONB null · 숫자 · 목록 → **observe + `[status_exit_mode_invalid]`**. **키가 정말 없을 때만** enforce |

`apply_mode(kind, mode)` 의 기본(`persisted` 미지정)은 저장 성공 = 고정 없음이다(round-1 호출 호환).
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from tests.unit.engine._cycle369_support import (
    NEXT_DAY,
    clock,  # noqa: F401 — pytest 픽스처
    db_modes,  # noqa: F401
    leaf,
    open_info,
    records,
)

pytestmark = [pytest.mark.unit, pytest.mark.real_status_watch]


@pytest.fixture(autouse=True)
def _info(caplog):
    open_info(caplog)


def _pin(kind, mode):
    """라우트가 DB 저장 실패 뒤 부르는 경로 — `apply_mode(kind, mode, persisted=False)`."""
    leaf().apply_mode(kind, mode, persisted=False)


# ===========================================================================
# 고정 — refresh 가 덮지 않는다
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("db_value", [None, "enforce", "observe"])
async def test_q1_pinned_axis_survives_refresh(clock, db_modes, db_value):
    """저장 실패로 고정된 `off` 는 DB 가 무엇을 말하든 refresh 에 덮이지 않는다.

    `None`(키 없음 — 첫 PUT 이 실패하면 행이 없다)이 가장 흔한 사고 모양이다.
    """
    clock.set(10, 0)
    _pin("sell", "off")
    db_modes(sell=db_value, buy=None)
    for _ in range(3):
        await leaf().refresh_modes()
    assert leaf().current_modes()["sell"] == "off", (
        "저장 실패로 고정한 off 를 refresh 가 되돌렸다 — 끈 시장가 매도가 다시 나간다"
    )


@pytest.mark.asyncio
async def test_q1_pin_is_per_axis(clock, db_modes):
    """sell 만 고정 — buy 는 DB 를 그대로 따른다."""
    clock.set(10, 0)
    _pin("sell", "off")
    db_modes(sell="enforce", buy="observe")
    await leaf().refresh_modes()
    assert leaf().current_modes() == {"sell": "off", "buy": "observe"}


@pytest.mark.asyncio
async def test_q1_later_successful_write_unpins(clock, db_modes):
    """그 축의 다음 성공 저장이 고정을 푼다 — 그 뒤 SQL UPDATE 는 다시 반영된다."""
    clock.set(10, 0)
    _pin("sell", "off")
    leaf().apply_mode("sell", "observe", persisted=True)
    db_modes(sell="enforce", buy=None)     # 운영자의 SQL UPDATE
    await leaf().refresh_modes()
    assert leaf().current_modes()["sell"] == "enforce", "성공 저장 뒤에도 고정이 남았다"


@pytest.mark.asyncio
async def test_q1_default_apply_mode_does_not_pin(clock, db_modes):
    """`persisted` 미지정(round-1 호출)은 저장 성공 = 고정 없음."""
    clock.set(10, 0)
    leaf().apply_mode("sell", "off")
    db_modes(sell="enforce", buy=None)
    await leaf().refresh_modes()
    assert leaf().current_modes()["sell"] == "enforce"


@pytest.mark.asyncio
async def test_q1_restart_clears_pin(clock, db_modes):
    clock.set(10, 0)
    _pin("buy", "off")
    leaf().reset_state_for_test()           # 프로세스 재시작과 같은 효과
    db_modes(sell=None, buy="enforce")
    await leaf().refresh_modes()
    assert leaf().current_modes()["buy"] == "enforce"


@pytest.mark.asyncio
async def test_q1_pinned_warning_once_per_day(clock, db_modes, caplog):
    """고정 동안 `[status_exit_mode_pinned]` WARNING 1회/일 — 날짜가 바뀌면 다시 1회."""
    clock.set(10, 0)
    _pin("sell", "off")
    db_modes(sell=None, buy=None)
    for _ in range(3):
        await leaf().refresh_modes()
    day1 = records(caplog, "[status_exit_mode_pinned]", min_level=logging.WARNING)
    assert len(day1) == 1, f"고정 경고는 하루 1회: {len(day1)}"
    assert "sell" in day1[0].getMessage()

    clock.set(9, 1, day=NEXT_DAY)
    await leaf().refresh_modes()
    await leaf().refresh_modes()
    both = records(caplog, "[status_exit_mode_pinned]", min_level=logging.WARNING)
    assert len(both) == 2, f"다음 날에도 고정이면 다시 1회: {len(both)}"


@pytest.mark.asyncio
async def test_q1_no_pinned_warning_when_not_pinned(clock, db_modes, caplog):
    clock.set(10, 0)
    db_modes(sell="off", buy=None)
    await leaf().refresh_modes()
    assert records(caplog, "[status_exit_mode_pinned]", min_level=logging.WARNING) == []


# ===========================================================================
# 세대 번호 — PUT 전에 시작한 refresh 는 버린다
# ===========================================================================
@pytest.mark.asyncio
async def test_q1_inflight_refresh_started_before_put_is_discarded(clock, monkeypatch):
    """refresh 의 DB 읽기가 걸려 있는 동안 PUT(off, 저장 성공)이 들어오면, 그 뒤 돌아온
    **옛 값**(enforce)이 PUT 을 덮으면 안 된다(round-1 탐침 case 2 재현).

    축마다 세대가 따로라 sell PUT 이 buy 의 읽기 결과까지 버리지는 않는다.
    """
    from src.db import system_config as sc

    clock.set(10, 0)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def _slow_sell():
        entered.set()
        await release.wait()
        return "enforce"        # 읽기를 시작한 순간의 옛 값

    async def _buy():
        return "observe"

    monkeypatch.setattr(sc, "get_status_exit_mode_raw", _slow_sell, raising=False)
    monkeypatch.setattr(sc, "get_status_buy_block_mode_raw", _buy, raising=False)

    task = asyncio.create_task(leaf().refresh_modes())
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    leaf().apply_mode("sell", "off", persisted=True)     # 저장 성공 PUT
    release.set()
    await asyncio.wait_for(task, timeout=2.0)
    assert leaf().current_modes()["sell"] == "off", (
        "PUT 전에 시작한 refresh 가 PUT 의 off 를 옛 값으로 덮었다"
    )
    assert leaf().current_modes()["buy"] == "observe", "세대는 축마다 — buy 읽기까지 버렸다"


@pytest.mark.asyncio
async def test_q1_put_on_one_axis_does_not_discard_other_axis_read(clock, monkeypatch):
    """세대 번호는 **축마다**다 — sell PUT 이 그 순간 걸려 있던 buy 읽기를 버리면 안 된다.

    buy 읽기가 걸린 동안 sell 을 PUT(저장 성공 — DB 에도 off) 한다. 끝 상태 = sell off · buy 는 DB 값.
    세대를 두 축이 공유하면 buy 읽기가 버려져 기본값(enforce)에 머문다.
    """
    from src.db import system_config as sc

    clock.set(10, 0)
    store = {"sell": "enforce"}
    entered = asyncio.Event()
    release = asyncio.Event()

    async def _sell():
        return store["sell"]

    async def _slow_buy():
        entered.set()
        await release.wait()
        return "observe"

    monkeypatch.setattr(sc, "get_status_exit_mode_raw", _sell, raising=False)
    monkeypatch.setattr(sc, "get_status_buy_block_mode_raw", _slow_buy, raising=False)

    task = asyncio.create_task(leaf().refresh_modes())
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    store["sell"] = "off"                                  # PUT 이 DB 에 저장
    leaf().apply_mode("sell", "off", persisted=True)       # 같은 요청에서 메모리 반영
    release.set()
    await asyncio.wait_for(task, timeout=2.0)
    assert leaf().current_modes() == {"sell": "off", "buy": "observe"}, leaf().current_modes()


@pytest.mark.asyncio
async def test_q1_refresh_started_after_put_is_applied(clock, db_modes):
    """세대 번호가 이후의 refresh 를 영구히 막으면 안 된다 — PUT 뒤에 시작한 refresh 는 반영."""
    clock.set(10, 0)
    leaf().apply_mode("sell", "off", persisted=True)
    db_modes(sell="observe", buy=None)
    await leaf().refresh_modes()
    assert leaf().current_modes()["sell"] == "observe"


# ===========================================================================
# 망가진 저장 행 → observe (키 없음만 enforce)
# ===========================================================================
class _Missing:
    pass


_ABSENT = _Missing()


@pytest.fixture
def raw_pg(monkeypatch):
    """`src.db.pg.fetch` 교체 — **실제** `system_config` getter 가 이 원값을 읽는다.

    `rows[key]` 가 `_ABSENT` 면 행 없음(키 없음), 그 밖은 JSONB 원값 그대로(`None` = JSONB null 행).
    """
    import src.db.pg as pg

    rows: dict = {"status_exit_mode": _ABSENT, "status_buy_block_mode": _ABSENT}

    async def _fetch(sql, *args):
        key = args[0] if args else None
        v = rows.get(key, _ABSENT)
        if v is _ABSENT:
            return []
        return [{"value": v}]

    monkeypatch.setattr(pg, "fetch", _fetch)
    return rows


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", [
    {"mode": "off"},        # dict 인데 value 키가 없다 (SQL UPDATE 오타)
    {"value": None},        # value 가 null
    None,                   # JSONB null 행
    0,                      # 숫자
    ["off"],                # 목록
], ids=["dict_without_value", "value_null", "jsonb_null", "number", "list"])
async def test_q1_malformed_stored_row_resolves_observe(clock, raw_pg, caplog, stored):
    """행은 있는데 모양이 틀렸다 = 「키 없음」이 아니다 → observe + invalid 마커(명세 §5 「알 수 없는 값」).

    현재 `_string_from_raw` 가 이 모양들을 None 으로 접어 「키 없음 = enforce」 로 떨어진다 —
    롤백용 SQL UPDATE 오타 하나가 경고 없이 청산을 켠다.
    """
    clock.set(10, 0)
    raw_pg["status_exit_mode"] = stored
    await leaf().refresh_modes()
    assert leaf().current_modes()["sell"] == "observe", (
        f"망가진 저장 행 {stored!r} 이 enforce 로 읽혔다 — 키가 있으면 「모르는 값」이다"
    )
    assert records(caplog, "[status_exit_mode_invalid]", min_level=logging.WARNING)


@pytest.mark.asyncio
async def test_q1_truly_missing_key_is_enforce_control(clock, raw_pg, caplog):
    """대조 — 행이 정말 없을 때만 enforce(경고 없음)."""
    clock.set(10, 0)
    await leaf().refresh_modes()
    assert leaf().current_modes() == {"sell": "enforce", "buy": "enforce"}
    assert records(caplog, "[status_exit_mode_invalid]", min_level=logging.WARNING) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stored,expected", [({"value": "off"}, "off"), ("observe", "observe")])
async def test_q1_wellformed_rows_still_parse(clock, raw_pg, stored, expected):
    """대조 — 정상 모양(`{"value": str}`·맨 문자열)은 그대로."""
    clock.set(10, 0)
    raw_pg["status_buy_block_mode"] = stored
    await leaf().refresh_modes()
    assert leaf().current_modes()["buy"] == expected
