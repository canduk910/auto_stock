"""cycle295 Red — (C) 축 · `system_config` **bool 왕복 불변식**.

명세 = `_workspace/red/cycle295_gap_hold_removal_spec.md` §2-0
자매 = `tests/integration/test_cycle295_bool_roundtrip_pg.py` (실 Postgres 왕복)

## 무엇이 깨져 있나 — 2026-09-15 실증

10:0x 에 `PUT /api/realtime/tick-channel-mode {"mode":"enforce","gap_hold_enabled":false}`
를 보냈고 응답이 `gap_hold_enabled: false · gap_persisted: true` 였다. 그런데
**15:41:56 에 갭 전환 7건이 그대로 일어났다**(`[tick_channel_switch] … mode=high` ×7).

원인은 setter 와 getter 의 **왕복 불변식 파괴**다.

    set_tick_channel_gap_hold_enabled(False)
      → _set_string(key, "false")       → DB: {"value": "false"}   ← 문자열
    _get_bool_or_none(key)
      → raw = {"value": "false"}  (dict)
      → isinstance(raw, dict) 분기 진입
      → return bool(raw.get("value")) = bool("false") = True        ← 🔴

`_get_bool_or_none` 은 바로 아래에 `"true"/"false"` 정규화 분기를 갖고 있지만
**dict 로 감싸인 값은 그 분기에 도달하지 못한다**. PUT 직후에는 `apply_*` 가 메모리를
직접 덮어 False 지만, 120초 `refresh_switch_params()` 가 DB 를 다시 읽어
`bool("false")=True` 로 **되돌린다**. 즉 **끄면 켜지는 킬스위치**다.

## 🔴 이 파일은 cycle295 가 `gap_hold` 를 제거해도 계속 필요하다

`tick_channel_switch_enabled` 가 **같은 결함을 그대로 갖고 남는다**(그 킬스위치도
지금 작동하지 않는다). 그 키는 운영 DB 에 행이 아직 없어 잠복 중이라 가드가 없으면
다음에 또 조용히 재발한다.

## 설계 결정 — dict 분기의 문자열 정규화 계약 (cycle295 에서 확정)

`_get_bool_or_none` 이 `{"value": v}` 를 볼 때:

| `v` | 반환 | 근거 |
|---|---|---|
| `True` / `False` (JSON boolean) | 그대로 | 정본 형태 |
| `"true"` / `"false"` (대소문자·공백 무관) | `True` / `False` | 🔴 지금 깨진 경로 |
| `0` / `1` 등 숫자 | `bool(v)` | 현행 유지 |
| `None` | `None` | 현행 유지(키는 있으나 값 없음) |
| 그 밖의 문자열(`"maybe"` 등) | **`None`** | 🔴 결정 — bool 이 아닌 문자열을 `True` 로 읽는 것이 이 결함의 본질이다. `None` 은 「모른다」이고 호출자 계약(`refresh_switch_params` = 현재 값 유지 / `get_auto_apply_enabled` = False)이 전부 **안전한 쪽**이다 |

**시정 방향 2택(둘 다 해도 좋다)** — ① `_get_bool_or_none` 의 dict 분기가 꺼낸 값을
기존 문자열 정규화 경로로 흘려보낸다(한 곳만 고쳐 모든 키가 이득) ② 두 tick_channel
setter 를 `_set_bool` 로 바꾼다(`set_auto_start` docstring 이 이미 경고한 관례).
**①만 하면 A·B 두 절이 다 초록이고, ②만 하면 A 절은 초록이지만 B 절(`_get_bool_or_none`
직접 계약)이 붉게 남는다** — 그래서 ① 이 권고다.
"""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit


#: 🔴 지금 깨져 있는 쌍 — `_set_string("true"/"false")` 로 저장한다.
_BROKEN_TODAY = (
    "tick_channel_switch_enabled",
    "tick_channel_gap_hold_enabled",
)

#: 🔵 양성 대조군 — 이미 `{"value": bool}` 로 저장해 정상인 쌍. 시정이 이쪽을
#:    깨뜨리면(예: 정규화를 반대로 달면) 이 목록이 붉어진다.
_HEALTHY_CONTROL = (
    "dkstock_regime_enabled",
    "kis_mcp_enabled",
    "auto_apply_enabled",
    "etf_regime_enabled",
    "auto_regime_adjust",
    "auto_start",
)

#: (A) 축이 제거하는 이름. 제거 뒤에는 `_discover_bool_dials()` 에서 자연히 빠지고
#: 이 파일은 그대로 초록이다 — (C) 와 (A) 를 한 파일에 묶지 않는 이유가 이것이다.
_REMOVED_BY_AXIS_A = ("tick_channel_gap_hold_enabled",)


def _sysconf():
    from src.db import system_config

    return system_config


def _discover_bool_dials() -> list[str]:
    """`set_<name>(bool)` ↔ `get_<name>()` 쌍을 **동적으로** 찾는다.

    명시 목록만 두면 다음 사이클이 새 bool 다이얼을 `_set_string` 으로 추가할 때
    이 가드가 조용히 비껴간다(cycle294 가 정확히 그렇게 두 키를 넣었다). 동적
    스캔이 그 구멍을 막고, 아래 `test_a0_*` 가 스캔 자체의 양성 대조군이다.
    """
    sc = _sysconf()
    found: list[str] = []
    for name, fn in vars(sc).items():
        if not name.startswith("set_") or not inspect.iscoroutinefunction(fn):
            continue
        params = [
            p for p in inspect.signature(fn).parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if len(params) != 1:
            continue
        ann = params[0].annotation
        if ann is not bool and str(ann) != "bool":
            continue
        getter = getattr(sc, "get_" + name[4:], None)
        if getter is None or not inspect.iscoroutinefunction(getter):
            continue
        if len(inspect.signature(getter).parameters) != 0:
            continue
        found.append(name[4:])
    return sorted(found)


# ===========================================================================
# A — 🔵 스캐너 자체의 양성 대조군 (부정 단언이 공허해지는 것을 막는다)
# ===========================================================================
def test_a0_scanner_actually_finds_the_known_bool_dials():
    """🔵 양성 대조군 — 스캐너가 실제로 쌍을 찾는가.

    cycle292 교훈: 본체가 떠나면 "0건" 부정 단언이 전부 참이 되어 조용히 공허해진다.
    아래 왕복 단언은 `_discover_bool_dials()` 가 빈 목록이면 **하나도 실행되지 않고**
    초록이다. 이 테스트가 그 퇴화를 사살한다.
    """
    found = set(_discover_bool_dials())
    assert found, "bool 다이얼 쌍을 하나도 못 찾았다 — 스캐너가 고장났다(공허 가드)"
    missing = [n for n in _HEALTHY_CONTROL if n not in found]
    assert not missing, (
        f"이미 정상이던 bool 다이얼이 스캔에서 사라졌다: {missing}. "
        "setter 시그니처(`value: bool`)나 getter 이름 규약이 바뀌었는지 확인하라"
    )
    still = [n for n in _BROKEN_TODAY if n not in found and n not in _REMOVED_BY_AXIS_A]
    assert not still, (
        f"시정 대상 다이얼이 스캔에서 사라졌다: {still} — (A) 축이 지우는 것은 "
        "`tick_channel_gap_hold_enabled` **하나뿐**이고 `tick_channel_switch_enabled` 는 "
        "남는다(그 킬스위치도 같은 결함을 갖고 있다)"
    )


# ===========================================================================
# B — 🔴 왕복 불변식: set(x) → get() == x (모든 bool 다이얼)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("name", _discover_bool_dials())
@pytest.mark.parametrize("value", [False, True])
async def test_b1_set_then_get_returns_the_same_boolean(
    monkeypatch: pytest.MonkeyPatch, fake_pg_kv, name: str, value: bool,
):
    """🔴 왕복 불변식 — 저장한 bool 이 그대로 돌아온다.

    `value=False` 의 `tick_channel_switch_enabled` / `tick_channel_gap_hold_enabled`
    가 오늘 붉다(`bool("false") = True`). 나머지 쌍은 이미 초록이고 **그대로 초록이어야
    한다**(대조군).

    ⚠️ 이 테스트가 붉어졌다면 값을 기대에 맞추지 말고 `_get_bool_or_none`/`_set_*` 를
    고쳐라. 킬스위치가 "끄면 켜지는" 상태로 배포되는 것이 이 사이클이 막는 사고다.
    """
    sc = _sysconf()
    monkeypatch.setattr(sc, "pg", fake_pg_kv)

    await getattr(sc, f"set_{name}")(value)
    got = await getattr(sc, f"get_{name}")()

    assert got is value, (
        f"`set_{name}({value})` 직후 `get_{name}()` 이 {got!r} 를 돌려줬다 "
        f"(저장 형태 = {fake_pg_kv.store!r}). 왕복 불변식 파괴 — 운영자가 끈 다이얼이 "
        "다음 폴링에서 되살아난다"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", _discover_bool_dials())
async def test_b2_toggle_sequence_survives_repeated_writes(
    monkeypatch: pytest.MonkeyPatch, fake_pg_kv, name: str,
):
    """B2 — True → False → True 왕복. 마지막 쓰기가 항상 이긴다."""
    sc = _sysconf()
    monkeypatch.setattr(sc, "pg", fake_pg_kv)
    setter, getter = getattr(sc, f"set_{name}"), getattr(sc, f"get_{name}")

    seen = []
    for v in (True, False, True, False):
        await setter(v)
        seen.append(await getter())

    assert seen == [True, False, True, False], (
        f"{name} 토글 시퀀스가 {seen} 로 돌아왔다 — 마지막 쓰기가 이기지 않는다"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", _discover_bool_dials())
async def test_b3_stored_value_is_a_json_boolean_not_a_string(
    monkeypatch: pytest.MonkeyPatch, fake_pg_kv, name: str,
):
    """B3 — 🔴 **저장 형태**까지 잠근다(왕복만 고치고 형태를 남기면 재발한다).

    `{"value": "false"}` 는 `jsonb_typeof(value->'value') = 'string'` 이다. 운영자가
    DB 를 직접 들여다볼 때, 그리고 다른 언어/도구가 같은 행을 읽을 때 문자열 `"false"`
    는 참으로 읽힌다. 정본 형태는 `set_auto_start` docstring 이 이미 못박은
    **JSONB `{"value": bool}`** 다.

    ⚠️ 시정 ①(getter 정규화)만 해도 `test_b1`/`test_b2` 는 초록이지만 이 테스트는
    붉게 남는다 — ②(두 setter 를 `_set_bool` 로)까지 해야 닫힌다. 둘 다 하라.
    """
    sc = _sysconf()
    monkeypatch.setattr(sc, "pg", fake_pg_kv)
    await getattr(sc, f"set_{name}")(False)

    stored = [v for v in fake_pg_kv.store.values()]
    assert len(stored) == 1, f"쓰기가 정확히 1행이 아니다: {fake_pg_kv.store!r}"
    payload = stored[0]
    assert isinstance(payload, dict) and "value" in payload, (
        f"{name} 저장 형태가 `{{'value': …}}` 이 아니다: {payload!r}"
    )
    assert isinstance(payload["value"], bool), (
        f"{name} 이 bool 이 아니라 {type(payload['value']).__name__}"
        f"({payload['value']!r}) 로 저장됐다. JSONB 문자열 \"false\" 는 다른 어떤 "
        "판독자에게도 **참**이다 — 정본 형태는 `{\"value\": bool}`"
    )


# ===========================================================================
# C — `_get_bool_or_none` 의 dict 분기 계약 (한 곳만 고치면 전부 이득)
# ===========================================================================
_DICT_BRANCH_CASES = [
    # (저장된 raw, 기대)
    ({"value": False}, False),
    ({"value": True}, True),
    ({"value": "false"}, False),      # 🔴 오늘 True
    ({"value": "true"}, True),
    ({"value": "FALSE"}, False),      # 🔴 오늘 True
    ({"value": "TRUE"}, True),
    ({"value": " false "}, False),    # 🔴 오늘 True
    ({"value": " true "}, True),
    ({"value": 0}, False),
    ({"value": 1}, True),
    ({"value": None}, None),
    ({"value": "maybe"}, None),       # 🔴 오늘 True — §설계 결정
    ({"value": ""}, None),            # 🔴 오늘 False(우연히 맞음) — "" 는 bool 이 아니다
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("raw", "expected"), _DICT_BRANCH_CASES)
async def test_c1_get_bool_or_none_normalizes_the_dict_branch(
    monkeypatch: pytest.MonkeyPatch, fake_pg_kv, raw, expected,
):
    """🔴 C1 — `{"value": …}` 안의 값도 문자열 정규화를 받는다.

    지금은 dict 분기가 `bool(raw.get("value"))` 로 끝나 **아래 문자열 분기에 도달하지
    못한다**. 이 계약을 세우면 `tick_channel_*` 두 키뿐 아니라 앞으로 어떤 키가
    문자열로 들어와도 같은 답이 나온다.

    `"maybe"`/`""` → `None` 은 이 사이클의 **설계 결정**이다(파일 상단 표 참조) —
    bool 이 아닌 문자열을 `True` 로 읽는 것이 이 결함의 본질이므로 「모른다」로
    돌려주고 호출자의 안전한 기본값에 맡긴다.
    """
    sc = _sysconf()
    monkeypatch.setattr(sc, "pg", fake_pg_kv)
    fake_pg_kv.store["cycle295_probe"] = raw

    got = await sc._get_bool_or_none("cycle295_probe")

    assert got is expected, (
        f"`_get_bool_or_none` 이 {raw!r} 를 {got!r} 로 읽었다(기대 {expected!r}). "
        "dict 분기가 문자열 정규화 경로로 흐르지 않는다"
    )


@pytest.mark.asyncio
async def test_c2_missing_key_still_returns_none(
    monkeypatch: pytest.MonkeyPatch, fake_pg_kv,
):
    """🔵 C2 양성 대조군 — 키 부재 계약은 **바뀌지 않는다**.

    `None` 은 호출자에게 「DB 에 의견이 없다」이고 `refresh_switch_params` 는 그때
    현재 값을 유지한다. 정규화를 넣으면서 이 경로를 `False` 로 바꾸면 부팅 기본값이
    조용히 뒤집힌다.
    """
    sc = _sysconf()
    monkeypatch.setattr(sc, "pg", fake_pg_kv)
    assert await sc._get_bool_or_none("cycle295_absent") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("raw", "expected"), [
    (True, True), (False, False),
    ("true", True), ("false", False), ("TRUE", True), (" false ", False),
    ("nonsense", None),
])
async def test_c3_bare_value_branch_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, fake_pg_kv, raw, expected,
):
    """🔵 C3 양성 대조군 — dict 로 감싸이지 **않은** 값의 기존 계약은 그대로다.

    이 절이 붉어지면 정규화를 dict 분기가 아니라 **공용 경로**에 잘못 달았다는 뜻이다.
    """
    sc = _sysconf()
    monkeypatch.setattr(sc, "pg", fake_pg_kv)
    fake_pg_kv.store["cycle295_bare"] = raw
    assert await sc._get_bool_or_none("cycle295_bare") is expected


@pytest.mark.asyncio
async def test_c4_get_failure_still_returns_none(monkeypatch: pytest.MonkeyPatch):
    """🔵 C4 양성 대조군 — 조회 예외는 여전히 `None`(fail-open, 호출자 폴백)."""
    sc = _sysconf()

    class _Boom:
        async def fetch(self, *_a, **_k):
            raise RuntimeError("db down")

    monkeypatch.setattr(sc, "pg", _Boom())
    assert await sc._get_bool_or_none("anything") is None
