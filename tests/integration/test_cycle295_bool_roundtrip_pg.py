"""cycle295 Red — (C) 축 · bool 다이얼 **실 Postgres** 왕복 + `jsonb_typeof`.

명세 = `_workspace/red/cycle295_gap_hold_removal_spec.md` §2-0 ③
자매(단위) = `tests/unit/db/test_cycle295_bool_roundtrip_invariant.py`

단위 자매는 `fake_pg_kv`(파이썬 dict)로 왕복을 잰다. 이 파일은 그 왕복이 **실제
JSONB 컬럼과 asyncpg codec 을 거쳐도** 같은지, 그리고 저장된 값의 `jsonb_typeof` 가
`boolean` 인지를 mock 없이 확인한다.

2026-09-15 즉시 조치로 운영 DB 의 `tick_channel_gap_hold_enabled` 행은 손으로
`{"value": false}`(JSON boolean)로 **이미 교체됐다**. 그것은 **우회**이고 코드 결함은
그대로다 — 누구든 다시 `PUT` 하면 문자열로 되돌아간다. 이 파일이 그 되돌아감을 막는다.

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


#: 🔴 지금 `_set_string("true"/"false")` 로 저장하는 쌍.
#: `tick_channel_gap_hold_enabled` 는 (A) 축이 제거하므로 `getattr` 로 관대 접근하되,
#: **둘 다 사라지면 FAIL** 한다(아래 `test_p0`). 공허 가드 금지.
_CANDIDATES = (
    "tick_channel_switch_enabled",
    "tick_channel_gap_hold_enabled",
)

#: 🔵 양성 대조군 — 이미 `{"value": bool}` 인 쌍. 시정이 이쪽을 깨면 여기가 붉어진다.
_CONTROL = ("dkstock_regime_enabled", "kis_mcp_enabled", "auto_regime_adjust")


def _pairs(names):
    from src.db import system_config

    out = []
    for n in names:
        setter = getattr(system_config, f"set_{n}", None)
        getter = getattr(system_config, f"get_{n}", None)
        if setter is not None and getter is not None:
            out.append((n, setter, getter))
    return out


def _key_of(name: str) -> str:
    """`system_config` 행의 실제 키 이름 — 헬퍼 이름과 1:1 이다."""
    return name


@pytest.mark.asyncio
async def test_p0_at_least_one_tick_channel_dial_survives_to_be_tested():
    """🔵 P0 양성 대조군 — 시정 대상이 통째로 사라지면 아래가 **전부 공허**해진다.

    (A) 축은 `tick_channel_gap_hold_enabled` **하나만** 지운다.
    `tick_channel_switch_enabled` 는 남고 **같은 결함을 그대로 갖고 있다**.
    둘 다 없어졌다면 누군가 이 결함을 "지워서" 닫은 것이므로 멈춰야 한다.
    """
    assert _pairs(_CANDIDATES), (
        "`tick_channel_switch_enabled` 다이얼이 사라졌다 — (A) 축의 제거 범위는 "
        "`gap_hold` 하나뿐이다. 이 파일의 왕복 단언이 통째로 공허해졌다"
    )
    assert _pairs(_CONTROL), "양성 대조군 다이얼이 전부 사라졌다"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [False, True])
async def test_p1_real_pg_roundtrip_preserves_the_boolean(clean_system_config, value):
    """🔴 P1 — 실 PG 왕복. `set(False)` → `get()` 이 `False` 여야 한다.

    오늘은 `tick_channel_switch_enabled`(그리고 아직 남아 있다면 `gap_hold`)의
    `value=False` 가 `True` 로 돌아온다 — `_set_string` 이 심은 JSONB **문자열**
    `"false"` 를 `_get_bool_or_none` 의 dict 분기가 `bool("false")` 로 읽는다.
    """
    offenders = []
    for name, setter, getter in _pairs(_CANDIDATES + _CONTROL):
        await setter(value)
        got = await getter()
        if got is not value:
            offenders.append(f"{name}: set({value}) → get()={got!r}")

    assert not offenders, (
        "실 Postgres 왕복에서 bool 다이얼이 값을 잃었다:\n  " + "\n  ".join(offenders)
        + "\n운영자가 끈 킬스위치가 다음 폴링(120초)에서 되살아난다"
    )


@pytest.mark.asyncio
async def test_p2_stored_jsonb_value_type_is_boolean(clean_system_config, pg_pool):
    """🔴 P2 — `jsonb_typeof(value->'value')` 가 `boolean` 이다.

    2026-09-15 즉시 조치가 운영 DB 에서 **손으로** 한 그 교체를 코드가 스스로 하게
    만든다. `string` 이면 그 행을 읽는 모든 판독자(우리 코드·psql·다른 도구)에게
    `"false"` 가 참이다.
    """
    wrong = []
    for name, setter, _getter in _pairs(_CANDIDATES + _CONTROL):
        await setter(False)
        typ = await pg_pool.fetchval(
            "SELECT jsonb_typeof(value->'value') FROM system_config WHERE key = $1",
            _key_of(name),
        )
        if typ != "boolean":
            wrong.append(f"{name}: jsonb_typeof={typ!r}")

    assert not wrong, (
        "bool 다이얼이 JSONB boolean 이 아닌 형태로 저장됐다:\n  " + "\n  ".join(wrong)
        + "\n정본 형태는 `set_auto_start` docstring 이 못박은 `{\"value\": bool}` 이다"
    )


@pytest.mark.asyncio
async def test_p3_legacy_string_rows_are_read_as_booleans(clean_system_config, pg_pool):
    """🔴 P3 — 이미 DB 에 들어가 있는 **문자열 행**도 올바로 읽힌다.

    시정을 setter 쪽에만 하고 getter 를 그대로 두면, 09-15 이전에 저장된 행(그리고
    다른 경로로 들어오는 행)이 계속 잘못 읽힌다. 운영 DB 에는 지금 정확히 그런 행이
    있었다 — 그래서 사람이 손으로 고쳐야 했다.
    """
    from src.db import system_config

    # ⚠️ `src/db/pg.py::_init_conn` 이 jsonb encoder=json.dumps 를 등록하므로
    #    **raw dict 를 직접 바인딩**한다(문자열을 넘기면 JSON 문자열로 이중 인코딩되어
    #    `value->'value'` 가 NULL 이 되고 이 테스트가 엉뚱한 이유로 붉어진다).
    cases = [
        ("cycle295_legacy_false", {"value": "false"}, False),
        ("cycle295_legacy_true", {"value": "true"}, True),
        ("cycle295_legacy_upper", {"value": "FALSE"}, False),
        ("cycle295_legacy_bool", {"value": False}, False),
    ]
    for key, raw, _exp in cases:
        await pg_pool.execute(
            "INSERT INTO system_config (key, value, updated_at) "
            "VALUES ($1, $2::jsonb, now()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            key, raw,
        )

    bad = []
    for key, raw, exp in cases:
        got = await system_config._get_bool_or_none(key)
        if got is not exp:
            bad.append(f"{key} ({raw}) → {got!r}, 기대 {exp!r}")

    assert not bad, (
        "DB 에 남아 있는 문자열 bool 행을 잘못 읽는다:\n  " + "\n  ".join(bad)
    )
