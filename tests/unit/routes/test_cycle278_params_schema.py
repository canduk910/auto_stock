"""cycle278 — `GET /api/strategies/params-schema` 계약 (C11~C16 · B43~B52).

정본 명세 = `_workspace/red/cycle278_param_catalog_ui_spec.md` §3.2 · §4 · §7.1.

⚠️ **작성 경위** — 명세 §7.1 은 이 파일(B43~B52 10건)을 Red 산출물로 열거했으나
워크트리에 존재하지 않았다(라운드 1 Green 착수 시점 실측: `tests/unit/routes/` 에
`test_cycle278_params_validation.py` 만 있었다). 스키마 엔드포인트를 무검정으로
배선하면 화면이 통째로 그 응답에 의존하는 구조에서 회귀 가드가 0 이 되므로,
Green 단계에서 명세의 계약을 그대로 옮겨 작성했다.

## 이 파일이 잠그는 계약

* **C11** 200 + `data.params` 99 항목, 각 항목이 `ParamSpec` 의 **전 필드**를 가진다.
* **C12** `data.strategies` 는 등록 전략마다 1행 — `keys`(= `keys_for_strategy`) ·
  `params`(현재값) · `defaults`(코드 기본값)를 **함께** 준다.
  현재값을 별도 `GET /api/strategies`(staleTime 15s)와 섞으면 diff 미리보기가
  낡은 기준값으로 계산된다.
* **C13** 응답 생성이 `DEFAULT_PARAMS`·`config.params` 를 **변경하지 않는다**.
  기본값 dict 는 클래스 속성이라 참조를 그대로 실으면 상위 계층의 변형이 전략의
  기본값을 조용히 덮는다.
* **C14** `groups`/`types`/`risks`/`units` 닫힌 어휘를 그대로 준다 — 화면이 어휘를
  하드코딩하지 않게 하는 것이 목적이다.
* **C15** `invariants.budget` + `invariants.order`(12건).
* **C16** 이 경로가 `PUT /{strategy_id}/params` 를 가리지 않는다.
* **C46(파생)** 프론트/E2E 골든 픽스처가 **실제 응답과 같은 형태**다. cycle266
  (종목마스터 일봉 탭)은 목 세 곳이 *의도한 계약*만 담고 *실제 응답*을 담지 않아
  3개월 넘게 초록이었다 — 여기서는 픽스처를 실응답과 직접 대조한다.

검증 패턴: TestClient 대신 라우트 함수 직접 await (사이클 127 anyio portal hang 차단).
"""

from __future__ import annotations

import copy
import dataclasses
import json
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.engine import param_catalog as pc

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_STRATEGY_META: tuple[tuple[str, str, str, str], ...] = (
    ("momentum", "momentum", "MomentumStrategy", "상한가 모멘텀"),
    ("volatility_breakout", "volatility_breakout", "VolatilityBreakoutStrategy", "변동성 돌파"),
    ("long_tail_volatility", "long_tail_volatility", "LongTailVolatilityStrategy", "롱테일 변동성"),
    ("donchian_swing", "donchian_swing", "DonchianSwingStrategy", "돈치안 스윙"),
    ("bull_flag_breakout", "bull_flag_breakout", "BullFlagBreakoutStrategy", "불플래그 돌파"),
    ("vcp_breakout", "vcp_breakout", "VcpBreakoutStrategy", "VCP 돌파"),
    ("kojiro", "kojiro", "KojiroStrategy", "고지로 대순환"),
)


@lru_cache(maxsize=1)
def _real_classes() -> dict[str, type]:
    import importlib

    out: dict[str, type] = {}
    for sid, mod_name, cls_name, _label in _STRATEGY_META:
        mod = importlib.import_module(f"src.engine.strategies.{mod_name}")
        out[sid] = getattr(mod, cls_name)
    return out


def _make_strategy(sid: str, name: str):
    """실 전략 클래스의 `DEFAULT_PARAMS` **객체 자체**를 물고 있는 더블.

    같은 dict 객체를 물려야 "응답 생성이 클래스 기본값을 변형하지 않는다"(C13)를
    실제로 잴 수 있다.
    """
    real_cls = _real_classes()[sid]
    fake_cls = type(f"_Fake_{sid}", (), {"DEFAULT_PARAMS": real_cls.DEFAULT_PARAMS})
    obj = fake_cls()
    obj.strategy_id = sid
    obj.config = SimpleNamespace(
        strategy_id=sid,
        name=name,
        enabled=True,
        params=copy.deepcopy(dict(real_cls.DEFAULT_PARAMS)),
    )
    return obj


class _FakeRegistry:
    def __init__(self, strategies: list) -> None:
        self._list = strategies

    def all(self) -> list:
        return list(self._list)

    def get(self, sid: str):
        return next((s for s in self._list if s.strategy_id == sid), None)

    def get_strategies_status(self) -> dict:
        return {s.strategy_id: {"params": dict(s.config.params)} for s in self._list}


@pytest.fixture
def schema_env(monkeypatch):
    from src.routes import strategies as st

    registry = _FakeRegistry([_make_strategy(sid, label) for sid, _m, _c, label in _STRATEGY_META])
    monkeypatch.setattr(st, "trading_scheduler", SimpleNamespace(registry=registry))
    return registry


async def _get_schema() -> dict:
    """라우트가 실제로 만든 `data` **객체 자체**를 돌려준다.

    ⚠️ `resp.model_dump()` 를 거치면 안 된다 — pydantic v2 가 직렬화 과정에서 dict·list 를
    새로 만들어 주므로 "응답이 클래스 기본값과 **같은 리스트 객체**를 공유한다"는 결함이
    테스트에서 사라진다(깊은 복사를 지워도 초록인 상태 = 공허한 가드).
    """
    from src.routes import strategies as st

    resp = await st.get_params_schema()
    assert resp.success is True, resp
    assert isinstance(resp.data, dict), resp.data
    return resp.data


def _strategy_row(data: dict, sid: str) -> dict:
    row = next((s for s in data["strategies"] if s["strategy_id"] == sid), None)
    assert row is not None, f"{sid} 행이 없다 — 등록 전략마다 1행이어야 한다 (C12)"
    return row


# ===========================================================================
# C11 — 카탈로그 전체
# ===========================================================================
async def test_schema_when_requested_then_200_with_99_params(schema_env):
    """B43/C11 — 99 항목 전수. 부분 노출은 지금의 재드리프트(73키 화면 밖)의 재현이다."""
    data = await _get_schema()

    assert data["catalog_version"] == pc.CATALOG_VERSION
    keys = [p["key"] for p in data["params"]]
    assert keys == list(pc.all_keys()), "params 순서/집합이 카탈로그 정의 순서와 다르다"
    assert len(keys) == 99, f"{len(keys)}개 — 99 전수여야 한다"


async def test_schema_when_read_then_each_param_has_all_fields(schema_env):
    """B44/C11 — 각 항목이 `ParamSpec` 의 **전 필드**를 가진다.

    필드를 하나라도 빼면 화면이 그 정보를 자기 코드에 하드코딩하게 되고,
    그 순간 "키를 프론트에 두지 않는다"는 이 사이클의 전제가 깨진다.
    """
    data = await _get_schema()
    expected_fields = {f.name for f in dataclasses.fields(pc.ParamSpec)}

    for item in data["params"]:
        assert set(item) == expected_fields, (
            f"{item.get('key')}: 필드 차이 {set(item) ^ expected_fields}"
        )
        assert isinstance(item["applies_to"], list) and item["applies_to"]
        assert isinstance(item["choices"], list)
        assert isinstance(item["deprecated_for"], list)

    spec_choice_fields = {f.name for f in dataclasses.fields(pc.Choice)}
    for item in data["params"]:
        for choice in item["choices"]:
            assert set(choice) == spec_choice_fields, choice


# ===========================================================================
# C12 · C13 — 전략별 현재값/기본값
# ===========================================================================
async def test_schema_when_read_then_strategies_have_keys_params_defaults(schema_env):
    """B45/C12 — 전략마다 `keys`·`params`·`defaults` 를 함께 준다."""
    data = await _get_schema()

    assert [s["strategy_id"] for s in data["strategies"]] == [m[0] for m in _STRATEGY_META]
    for row in data["strategies"]:
        sid = row["strategy_id"]
        assert row["keys"] == list(pc.keys_for_strategy(sid)), sid
        assert set(row["params"]) == set(row["keys"]), sid
        assert set(row["defaults"]) == set(row["keys"]), sid
        assert isinstance(row["name"], str) and row["name"]
        assert isinstance(row["enabled"], bool)


async def test_schema_when_read_then_defaults_match_class_default_params(schema_env):
    """B46/C12 — `defaults` 는 그 전략 클래스의 `DEFAULT_PARAMS` 와 값이 같다."""
    data = await _get_schema()
    classes = _real_classes()

    for row in data["strategies"]:
        sid = row["strategy_id"]
        real = dict(classes[sid].DEFAULT_PARAMS)
        for key, value in row["defaults"].items():
            assert value == real[key], f"{sid}.{key}: {value!r} != {real[key]!r}"
        assert set(row["defaults"]) == set(real), (
            f"{sid}: 카탈로그 키 집합과 DEFAULT_PARAMS 키 집합이 다르다"
            f" — {set(row['defaults']) ^ set(real)}"
        )


async def test_schema_when_called_then_default_params_not_mutated(schema_env):
    """B47/C13 — 응답 생성이 클래스 `DEFAULT_PARAMS` 를 건드리지 않는다.

    참조를 그대로 실으면 상위 계층의 어떤 변형이 전략의 기본값을 조용히 덮는다.
    """
    classes = _real_classes()
    before = {sid: copy.deepcopy(dict(cls.DEFAULT_PARAMS)) for sid, cls in classes.items()}

    data = await _get_schema()
    # 응답을 변형해도 원본이 오염되지 않아야 한다 (깊은 복사 계약).
    row = _strategy_row(data, "momentum")
    row["defaults"]["max_positions"] = 999
    # ⚠️ **중첩 리스트가 진짜 시험대다** — dict 컴프리헨션은 바깥 dict 만 새로 만들기
    #    때문에, 깊은 복사를 빼면 `tradable_boards` 리스트가 클래스 기본값과 **같은
    #    객체**가 되어 응답을 받은 쪽의 append 하나가 전략의 기본 보드를 바꾼다.
    row["defaults"]["tradable_boards"].append("krx_after")
    row["params"]["tradable_boards"].append("krx_after")
    await _get_schema()

    for sid, cls in classes.items():
        assert dict(cls.DEFAULT_PARAMS) == before[sid], f"{sid}: DEFAULT_PARAMS 가 오염됐다"


async def test_schema_when_called_then_config_params_not_mutated(schema_env):
    """B48/C13 — 응답 생성이 `config.params`(현재값)를 건드리지 않는다."""
    before = {s.strategy_id: copy.deepcopy(dict(s.config.params)) for s in schema_env.all()}

    data = await _get_schema()
    row = _strategy_row(data, "kojiro")
    row["params"]["position_ratio"] = 0.99
    row["params"]["exclude_tickers"].append("000000")  # 중첩 리스트 공유 여부

    for strategy in schema_env.all():
        assert dict(strategy.config.params) == before[strategy.strategy_id], (
            f"{strategy.strategy_id}: config.params 가 오염됐다"
        )


async def test_schema_when_current_differs_from_default_then_both_visible(schema_env):
    """B45b/C12 — 현재값이 기본값과 다르면 **둘 다** 보인다("되돌리기" 계약의 전제)."""
    momentum = schema_env.get("momentum")
    momentum.config.params["buy_threshold"] = 27.0

    row = _strategy_row(await _get_schema(), "momentum")

    assert row["params"]["buy_threshold"] == 27.0
    assert row["defaults"]["buy_threshold"] == _real_classes()["momentum"].DEFAULT_PARAMS[
        "buy_threshold"
    ]
    assert row["params"]["buy_threshold"] != row["defaults"]["buy_threshold"]


# ===========================================================================
# C14 · C15 — 닫힌 어휘와 불변식
# ===========================================================================
async def test_schema_when_read_then_groups_units_types_risks_are_closed_vocab(schema_env):
    """B49/C14 — 어휘를 응답이 준다. 화면이 그것을 자기 코드에 복제하지 않게 한다."""
    data = await _get_schema()

    assert [g["id"] for g in data["groups"]] == list(pc.GROUP_IDS)
    assert [g["label_ko"] for g in data["groups"]] == [g[1] for g in pc.GROUPS]
    assert [g["description"] for g in data["groups"]] == [g[2] for g in pc.GROUPS]
    assert data["types"] == list(pc.TYPES)
    assert data["risks"] == list(pc.RISKS)
    assert data["units"] == list(pc.UNITS)

    assert {p["group"] for p in data["params"]} <= set(pc.GROUP_IDS)
    assert {p["unit"] for p in data["params"]} <= set(pc.UNITS)


async def test_schema_when_read_then_invariants_budget_and_twelve_order_rules(schema_env):
    """B50/C15 — 예산 불변식(강제) + 순서 불변식 12건(경고)."""
    from src.engine.param_validation import BUDGET_KEYS, MAX_BUDGET_PRODUCT

    inv = (await _get_schema())["invariants"]

    budget = inv["budget"]
    assert budget["keys"] == list(BUDGET_KEYS)
    assert budget["enforced"] is True
    assert str(MAX_BUDGET_PRODUCT) in budget["expr"], budget["expr"]
    assert budget["description"] == pc.BUDGET_INVARIANT

    order = inv["order"]
    assert len(order) == len(pc.ORDER_INVARIANTS) == 12
    for got, spec in zip(order, pc.ORDER_INVARIANTS, strict=True):
        assert got["lo_key"] == spec.lo_key and got["hi_key"] == spec.hi_key
        assert got["strategies"] == list(spec.strategies)
        assert got["enforced"] is False, "순서 불변식은 422 가 아니라 경고다"
        assert got["consequence"] == spec.consequence


async def test_schema_when_vb_read_then_deprecated_for_keys_lists_two_k_values(schema_env):
    """B51/C12 — VB 행만 `k_value_nxt_*` 2키를 "이 전략에선 무효"로 표시한다.

    LTV 는 그 키를 야간 목표가에 **실제로 곱한다** — 전역 deprecated 로 올리면
    LTV 화면에 거짓말을 한다.
    """
    data = await _get_schema()

    assert _strategy_row(data, "volatility_breakout")["deprecated_for_keys"] == [
        "k_value_nxt_pre",
        "k_value_nxt_post",
    ]
    assert _strategy_row(data, "long_tail_volatility")["deprecated_for_keys"] == []
    assert _strategy_row(data, "momentum")["deprecated_for_keys"] == []


# ===========================================================================
# C16 — 경로 충돌 없음
# ===========================================================================
def test_schema_path_when_registered_then_does_not_shadow_put_params():
    """B52/C16 — `/params-schema` 가 `PUT /{strategy_id}/params` 를 가리지 않는다."""
    from src.routes import strategies as st

    schema_path = "/api/strategies/params-schema"
    put_path = "/api/strategies/momentum/params"

    get_matches = [
        r for r in st.router.routes
        if "GET" in getattr(r, "methods", set()) and r.path_regex.match(schema_path)
    ]
    assert get_matches, "params-schema 를 받는 GET 라우트가 없다"
    assert get_matches[0].endpoint is st.get_params_schema, (
        f"다른 라우트가 먼저 가로챈다: {get_matches[0].path}"
    )

    put_matches = [
        r for r in st.router.routes
        if "PUT" in getattr(r, "methods", set()) and r.path_regex.match(put_path)
    ]
    assert put_matches and put_matches[0].endpoint is st.update_params

    # 알 수 없는 전략 id 로도 스키마 경로가 GET 을 가로채지 않는다(반대 방향).
    assert not any(
        "GET" in getattr(r, "methods", set()) and r.path_regex.match("/api/strategies/ghost")
        for r in st.router.routes
    ), "GET /{strategy_id} 가 생기면 params-schema 가 전략 id 로 해석될 수 있다"


# ===========================================================================
# C46(파생) — 프론트/E2E 골든 픽스처 ↔ 실응답 대조
# ===========================================================================
_FIXTURES = (
    "frontend/src/test/fixtures/paramSchema.fixture.ts",
    "e2e/fixtures/param-schema.fixture.ts",
)


def _load_fixture(rel: str) -> dict:
    """TS 픽스처에서 `PARAM_SCHEMA_FIXTURE` 의 JSON 리터럴만 떼어 낸다."""
    body = (_ROOT / rel).read_text(encoding="utf-8")
    marker = "export const PARAM_SCHEMA_FIXTURE: ParamSchemaData = "
    start = body.index(marker) + len(marker)
    end = body.index("\n}\n", start) + 2
    return json.loads(body[start:end])


@pytest.mark.parametrize("rel", _FIXTURES)
async def test_fixture_matches_live_schema_response(schema_env, rel: str):
    """목이 *의도한 계약*이 아니라 *실제 응답*을 담는다 (cycle266 재발 방지).

    현재값(`params`)·`name`·`enabled` 은 픽스처가 일부러 다르게 심으므로 제외하고,
    카탈로그에서 나오는 부분(스펙 99 · 어휘 · 불변식 · 전략별 keys/defaults)을 대조한다.
    """
    fixture = _load_fixture(rel)
    live = json.loads(json.dumps(await _get_schema(), ensure_ascii=False))

    for field in ("catalog_version", "groups", "types", "risks", "units", "params", "invariants"):
        assert fixture[field] == live[field], f"{rel}: `{field}` 가 실응답과 다르다"

    assert [s["strategy_id"] for s in fixture["strategies"]] == [
        s["strategy_id"] for s in live["strategies"]
    ]
    for fx, lv in zip(fixture["strategies"], live["strategies"], strict=True):
        assert fx["keys"] == lv["keys"], fx["strategy_id"]
        assert fx["defaults"] == lv["defaults"], fx["strategy_id"]
        assert fx["deprecated_for_keys"] == lv["deprecated_for_keys"], fx["strategy_id"]
        assert set(fx["params"]) == set(lv["params"]), fx["strategy_id"]
