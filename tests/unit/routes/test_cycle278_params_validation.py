"""cycle278 Red — `PUT /api/strategies/{id}/params` 검증 강화 (C17~C30 · B53~B66).

정본 명세 = `_workspace/red/cycle278_param_catalog_ui_spec.md` §3.3 · §5 · §7.1.

## 왜 필요한가 (실측)

현행 라우트(`src/routes/strategies.py`)는 `if key in strategy.config.params` 로 **기존 키만**
반영하고 나머지는 **조용히 버린다**. 오타·신규 키가 200 성공 응답을 받고도 무시되며,
범위 밖 값·자료형 오류는 그대로 저장돼 다음 부팅에서야(또는 영원히) 드러난다.

## 이 파일이 잠그는 계약

* **C17** `ParamsRequest.params` 유니언에 `bool` 이 **맨 앞**. 현행 유니언은 pydantic 2.11.2
  에서 `True → 1.0(float)` 로 강등한다(실측) — bool 키 저장이 전건 실패한다(M10).
* **C18** 그 전략에 없는 키 → **422 `unknown_key`** (조용히 버리지 않는다, M3).
* **C19/C20/C21** 자료형·범위·enum·정규식 위반 → 422 `type_mismatch` / `out_of_range` /
  `not_in_choices` / `pattern_mismatch`. `entry_start="25:00"` 은 반드시 422 다(HAZARD-8, M12).
* **C22** `editable=False`(레거시 8키) 저장 → 422 `not_editable`.
* **C23** 예산 불변식 `position_ratio × max_positions <= 1.0` → 422 `budget_invariant`.
  단 **이미 위반 중인 상태를 악화시키지 않는 편집은 통과 + 경고**(§5.3) — 그러지 않으면
  그 전략은 영구 편집 불가가 되고 복구 수단이 DB 직접 UPDATE 뿐이다(M4·M5).
* **C24** 오류가 하나라도 있으면 **아무것도 저장하지 않는다**(all-or-nothing).
  요청에 없는 키는 **보존**된다(부분 dict 병합, M9).
* **C25** 422 본문의 `detail` 은 **배열**이고 각 원소가 한글 `msg` 를 가진다
  (프론트의 기존 `extractValidationMessage`(`detail[0].msg`)가 그대로 동작한다).
* **C26** 알 수 없는 전략 id 는 **현행대로 200 + `success=false`**(422 로 바꾸지 않는다).
* **C27** 성공 응답은 `data.applied` 와 `data.warnings` 를 담는다.
* **C29/C30** `deprecated_for` 해당 전략 저장 → 200 + `no_effect_for_strategy` 경고,
  `range_src="none"` 키 저장 → 200 + `range_unbounded` 경고.

**identity 키는 API 로 저장 가능하다.** 2단계 확인은 *화면의 절차*이지 서버의 거부가 아니다 —
서버가 막으면 장중 긴급 롤백(`PUT` 이 유일 경로, cycle232 D6)이 함께 막힌다.

## Red 상태

라우트 검증 강화(`src/engine/param_validation.py` + `strategies.py`)가 **아직 없다**.
따라서 이 파일의 대부분은 RED 다. Green = backend-dev.

검증 패턴: TestClient 대신 라우트 함수 직접 await (사이클 127 anyio portal hang 차단).
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from functools import lru_cache
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 테스트 더블 — 레지스트리/전략 (실 전략의 DEFAULT_PARAMS 를 현재값으로 심는다)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _class_defaults() -> dict[str, dict]:
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategies.kojiro import KojiroStrategy
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategies.momentum import MomentumStrategy
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    return {
        "momentum": dict(MomentumStrategy.DEFAULT_PARAMS),
        "volatility_breakout": dict(VolatilityBreakoutStrategy.DEFAULT_PARAMS),
        "long_tail_volatility": dict(LongTailVolatilityStrategy.DEFAULT_PARAMS),
        "donchian_swing": dict(DonchianSwingStrategy.DEFAULT_PARAMS),
        "bull_flag_breakout": dict(BullFlagBreakoutStrategy.DEFAULT_PARAMS),
        "vcp_breakout": dict(VcpBreakoutStrategy.DEFAULT_PARAMS),
        "kojiro": dict(KojiroStrategy.DEFAULT_PARAMS),
    }


class _FakeStrategy:
    def __init__(self, strategy_id: str, params: dict) -> None:
        self.strategy_id = strategy_id
        self.config = SimpleNamespace(name=f"{strategy_id}-전략", params=params)


class _FakeRegistry:
    def __init__(self, strategies: dict[str, _FakeStrategy]) -> None:
        self._m = strategies

    def get(self, sid: str):
        return self._m.get(sid)

    def all(self):
        return list(self._m.values())

    def get_strategies_status(self) -> dict:
        return {sid: {"params": dict(s.config.params)} for sid, s in self._m.items()}


@dataclass
class _Env:
    registry: _FakeRegistry
    saved: list = field(default_factory=list)

    def params(self, sid: str) -> dict:
        return self.registry.get(sid).config.params

    def snapshot(self, sid: str) -> dict:
        return copy.deepcopy(self.params(sid))


@pytest.fixture
def params_env(monkeypatch):
    """라우트가 보는 레지스트리와 DB 저장을 격리한다."""
    from src.routes import strategies as st
    import src.db.strategy_config as sc

    env = _Env(_FakeRegistry({
        sid: _FakeStrategy(sid, copy.deepcopy(defaults))
        for sid, defaults in _class_defaults().items()
    }))

    async def _fake_save_params(strategy_id: str, params: dict) -> None:
        env.saved.append({"strategy_id": strategy_id, "params": copy.deepcopy(params)})

    monkeypatch.setattr(sc, "save_params", _fake_save_params, raising=True)
    # Green 이 모듈 레벨 import 로 바꿔도 잡히도록 라우트 모듈 속성도 함께 덮는다.
    monkeypatch.setattr(st, "save_params", _fake_save_params, raising=False)
    monkeypatch.setattr(st, "trading_scheduler", SimpleNamespace(registry=env.registry))
    return env


# ---------------------------------------------------------------------------
# 호출 헬퍼 — (status, body). 422 는 HTTPException / JSONResponse / pydantic 어느
# 경로로 와도 같은 모양으로 정규화한다.
# ---------------------------------------------------------------------------
async def _put(strategy_id: str, params: dict) -> tuple[int, dict]:
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import ValidationError

    from src.routes import strategies as st

    try:
        req = st.ParamsRequest(params=params)
    except ValidationError as exc:  # 모델 레벨 거부도 422 로 본다
        return 422, {"detail": exc.errors()}

    try:
        resp = await st.update_params(strategy_id, req)
    except HTTPException as exc:
        return exc.status_code, {"detail": exc.detail}
    except ValidationError as exc:
        return 422, {"detail": exc.errors()}

    if isinstance(resp, JSONResponse):
        return resp.status_code, json.loads(bytes(resp.body).decode("utf-8"))
    return 200, resp.model_dump()


def _details(body: dict) -> list[dict]:
    detail = body.get("detail")
    assert isinstance(detail, list), f"detail 은 배열이어야 한다 (C25) — got {type(detail).__name__}: {detail!r}"
    assert detail, "detail 이 비었다"
    for item in detail:
        assert isinstance(item, dict), f"detail 원소가 dict 가 아니다: {item!r}"
    return detail


def _codes(body: dict) -> set[str]:
    return {str(d.get("code")) for d in _details(body)}


def _entry(body: dict, code: str) -> dict:
    for d in _details(body):
        if d.get("code") == code:
            return d
    raise AssertionError(f"code={code} 가 없다 — 받은 detail: {body['detail']!r}")


def _warnings(body: dict) -> list[dict]:
    data = body.get("data")
    assert isinstance(data, dict), f"성공 응답의 data 는 dict 여야 한다 (C27) — got {data!r}"
    warns = data.get("warnings")
    assert isinstance(warns, list), f"data.warnings 가 배열이 아니다 (C27) — got {warns!r}"
    return warns


def _warning_codes(body: dict) -> set[str]:
    return {str(w.get("code")) for w in _warnings(body)}


# ===========================================================================
# C17 — pydantic 유니언 순서 (M10)
# ===========================================================================
async def test_put_when_bool_sent_then_stored_as_bool_not_float(params_env):
    """B53/C17 — `True` 가 `1.0` 으로 강등되지 않는다.

    실측(pydantic 2.11.2): `float | int | str | list[str] | None` 은 `True → 1.0`,
    `bool` 을 맨 앞에 두면 `True → True` 이면서 `5 → 5(int)` 도 유지된다.
    """
    from src.routes import strategies as st

    parsed = st.ParamsRequest(params={"failed_breakout_exit_enabled": True}).params
    value = parsed["failed_breakout_exit_enabled"]
    assert isinstance(value, bool) and value is True, (
        f"유니언이 bool 을 강등한다 — got {value!r} ({type(value).__name__})"
    )

    status, body = await _put("volatility_breakout", {"failed_breakout_exit_enabled": True})
    assert status == 200 and body["success"] is True, body
    assert params_env.params("volatility_breakout")["failed_breakout_exit_enabled"] is True
    assert params_env.saved[-1]["params"]["failed_breakout_exit_enabled"] is True


async def test_put_when_int_sent_then_stays_int_after_bool_union(params_env):
    """B54/C17 — `bool` 을 앞에 둬도 정수는 정수로 남는다(왕복 항등).

    `int` 가 `float` 로 강등되면 `api/order.py` 가 `ORD_QTY="2.0"` 을 KIS 로 보낸다.
    """
    from src.routes import strategies as st

    parsed = st.ParamsRequest(params={"max_positions": 3, "position_ratio": 0.2}).params
    assert isinstance(parsed["max_positions"], int) and not isinstance(parsed["max_positions"], bool)
    assert isinstance(parsed["position_ratio"], float)

    status, body = await _put("momentum", {"max_positions": 3})
    assert status == 200, body
    stored = params_env.params("momentum")["max_positions"]
    assert isinstance(stored, int) and stored == 3, f"{stored!r}"


# ===========================================================================
# C18 · C19 · C20 · C21 · C22 — 422 어휘
# ===========================================================================
async def test_put_when_unknown_key_then_422_unknown_key(params_env):
    """B55/C18 — 미지 키는 조용히 버리지 않는다(M3 — 현행 동작 복귀를 죽인다)."""
    before = params_env.snapshot("momentum")

    status, body = await _put("momentum", {"some_unknown_key": 999})

    assert status == 422, f"미지 키가 성공 응답을 받았다 — {body!r}"
    entry = _entry(body, "unknown_key")
    assert entry.get("key") == "some_unknown_key"
    assert entry.get("strategy_id") == "momentum"
    assert params_env.params("momentum") == before and not params_env.saved


async def test_put_when_key_belongs_to_other_strategy_then_422(params_env):
    """B55b/C18 — 카탈로그에 있어도 **그 전략의 키가 아니면** 422.

    `buy_threshold` 는 momentum 전용이다. vcp 에 보내면 미지 키다.
    """
    status, body = await _put("vcp_breakout", {"buy_threshold": 10.0})
    assert status == 422, body
    assert _entry(body, "unknown_key")["key"] == "buy_threshold"


async def test_put_when_type_mismatch_then_422_type_mismatch(params_env):
    """B55c/C19 — `int` 키에 `2.5`, `list_str` 키에 스칼라 → `type_mismatch`."""
    status, body = await _put("momentum", {"max_positions": 2.5})
    assert status == 422, body
    assert _entry(body, "type_mismatch")["key"] == "max_positions"

    status2, body2 = await _put("momentum", {"tradable_boards": "main"})
    assert status2 == 422, body2
    assert _entry(body2, "type_mismatch")["key"] == "tradable_boards"


async def test_put_when_out_of_range_then_422_with_key_and_expected(params_env):
    """B56/C20 — 범위 위반은 `key` 와 `expected`(min/max) 를 함께 돌려준다."""
    status, body = await _put("momentum", {"stop_loss_rate": -50.0})

    assert status == 422, body
    entry = _entry(body, "out_of_range")
    assert entry["key"] == "stop_loss_rate"
    assert entry.get("given") == -50.0
    expected = entry.get("expected") or {}
    assert expected.get("min") == -15.0 and expected.get("max") == 0.0, expected
    assert not params_env.saved


async def test_put_when_sign_gated_key_gets_positive_then_422(params_env):
    """B56b/C20 — 부호 규약 위반은 반드시 막는다(M11).

    `hard_stop_pct` 는 게이트가 없어(`loss_rate <= hard_stop_pct`) 양수를 넣으면
    **모든 포지션이 즉시 손절**된다.
    """
    status, body = await _put("kojiro", {"hard_stop_pct": 8.0})
    assert status == 422, f"양수 하드손절이 저장됐다 — 전 포지션 즉시 손절 경로: {body!r}"
    entry = _entry(body, "out_of_range")
    assert entry["key"] == "hard_stop_pct"
    assert isinstance(entry.get("msg"), str) and entry["msg"], entry


async def test_put_when_enum_value_unknown_then_422_not_in_choices(params_env):
    """B56c/C21 — enum·보드 목록의 오타를 무증상으로 통과시키지 않는다."""
    status, body = await _put("momentum", {"exchange": "BAD"})
    assert status == 422, body
    assert _entry(body, "not_in_choices")["key"] == "exchange"

    status2, body2 = await _put("momentum", {"tradable_boards": ["mian"]})
    assert status2 == 422, body2
    assert _entry(body2, "not_in_choices")["key"] == "tradable_boards"


async def test_put_when_entry_start_malformed_then_422_pattern_mismatch(params_env):
    """B56d/C21 — `entry_start="25:00"` 은 422 (HAZARD-8 · M12).

    형식이 깨지면 `int()` 캐스트가 `check_buy_signal` 안에서 `ValueError` 를 던지고
    그 예외가 `risk.on_tick` 으로 전파된다.
    """
    for bad in ("25:00", "9시5분"):
        status, body = await _put("bull_flag_breakout", {"entry_start": bad})
        assert status == 422, f"{bad!r} 가 통과했다 — {body!r}"
        assert _entry(body, "pattern_mismatch")["key"] == "entry_start"


async def test_put_when_legacy_key_then_422_not_editable(params_env):
    """B57/C22 — 값이 매매를 안 바꾸는 키에 저장 성공을 돌려주지 않는다."""
    status, body = await _put("volatility_breakout", {"quant_filter_enabled": True})

    assert status == 422, body
    assert _entry(body, "not_editable")["key"] == "quant_filter_enabled"
    assert not params_env.saved


async def test_put_when_multiple_errors_then_all_reported(params_env):
    """§5.1 — 첫 오류에서 멈추지 않는다.

    멈추면 운영자가 오류를 하나씩 왕복하며 고치게 되고, 그 왕복마다
    all-or-nothing(C24)이 다시 걸린다.
    """
    status, body = await _put(
        "momentum", {"some_unknown_key": 1, "stop_loss_rate": -50.0, "exchange": "BAD"},
    )
    assert status == 422, body
    assert {"unknown_key", "out_of_range", "not_in_choices"} <= _codes(body), _codes(body)


# ===========================================================================
# C23 — 예산 불변식 (M4 · M5)
# ===========================================================================
async def test_put_when_budget_invariant_violated_then_422_with_product_in_message(params_env):
    """B58/C23 — `0.3 × 4 = 1.2 > 1.0` → 422, 메시지가 두 값과 곱을 보여 준다."""
    status, body = await _put("momentum", {"position_ratio": 0.3})

    assert status == 422, body
    entry = _entry(body, "budget_invariant")
    assert entry.get("key") is None, f"불변식 오류는 특정 필드에 붙지 않는다 — {entry!r}"
    msg = entry.get("msg") or ""
    assert "0.3" in msg and "4" in msg and "1.2" in msg, f"두 값과 곱이 메시지에 없다: {msg!r}"
    assert not params_env.saved


async def test_put_when_product_exactly_one_then_pass(params_env):
    """B58b/C23 — 곱이 정확히 `1.0` 이면 **통과**(EPS 경계, M5).

    7 전략 중 6 전략의 현재 기본값이 정확히 1.0 이다. 부등호를 `<` 로 바꾸면
    그 6 전략이 전면 저장 불가가 된다.
    """
    status, body = await _put("momentum", {"position_ratio": 0.25, "max_positions": 4})
    assert status == 200, f"곱 1.0 이 막혔다 — 6 전략 전면 저장 불가: {body!r}"
    assert body["success"] is True


async def test_put_when_both_keys_sent_together_then_pass(params_env):
    """B58c/C23 — 두 키를 같은 저장에 함께 보내면 통과한다(`0.3 × 3 = 0.9`)."""
    status, body = await _put("momentum", {"position_ratio": 0.3, "max_positions": 3})
    assert status == 200, body
    assert params_env.params("momentum")["position_ratio"] == 0.3
    assert params_env.params("momentum")["max_positions"] == 3


async def test_put_when_preexisting_violation_and_not_worsened_then_200_with_warning(params_env):
    """B59/C23 §5.3 — 이미 위반 중인 상태를 **악화시키지 않는** 편집은 통과 + 경고.

    막으면 그 전략은 영구 편집 불가가 되고 복구 수단이 DB 직접 UPDATE 뿐이다
    (장중 재시작 금지 D6 때문에 더 위험하다).
    """
    params_env.params("momentum")["position_ratio"] = 0.5  # 0.5 × 4 = 2.0 (기존 위반)

    status, body = await _put("momentum", {"stop_loss_rate": -8.0})

    assert status == 200, f"기존 위반 상태의 무관한 편집이 막혔다 — {body!r}"
    assert "budget_invariant_preexisting" in _warning_codes(body), _warnings(body)
    assert params_env.params("momentum")["stop_loss_rate"] == -8.0
    assert params_env.saved


async def test_put_when_preexisting_violation_and_worsened_then_422(params_env):
    """B60/C23 §5.3 — 기존 위반을 **악화**시키면 422."""
    params_env.params("momentum")["position_ratio"] = 0.5  # 2.0

    status, body = await _put("momentum", {"max_positions": 5})  # 2.5 — 악화

    assert status == 422, body
    assert "budget_invariant" in _codes(body)
    assert not params_env.saved


# ===========================================================================
# C24 — all-or-nothing + 부분 병합 보존 (M9)
# ===========================================================================
async def test_put_when_any_error_then_nothing_saved(params_env):
    """B61/C24 — 오류가 하나라도 있으면 통과분도 저장하지 않는다."""
    before = params_env.snapshot("momentum")

    status, body = await _put("momentum", {"stop_loss_rate": -8.0, "some_unknown_key": 1})

    assert status == 422, body
    assert not params_env.saved, "오류가 있는데 save_params 가 호출됐다 — 절반만 반영된 상태"
    assert params_env.params("momentum") == before, "메모리 params 가 오염됐다"


async def test_put_when_partial_dict_then_unsent_keys_preserved(params_env):
    """B62/C24 — 요청에 없는 키는 보존된다(부분 dict 병합, M9).

    전체 덮어쓰기로 바뀌면 화면이 보낸 키 말고 전부 조용히 사라진다.
    """
    before = params_env.snapshot("momentum")

    status, body = await _put("momentum", {"stop_loss_rate": -8.0})
    assert status == 200, body

    saved = params_env.saved[-1]["params"]
    assert set(saved) == set(before), f"저장 dict 의 키 집합이 달라졌다: {set(before) ^ set(saved)}"
    assert saved["stop_loss_rate"] == -8.0
    for key, value in before.items():
        if key != "stop_loss_rate":
            assert saved[key] == value, f"{key} 가 조용히 바뀌었다: {value!r} → {saved[key]!r}"


async def test_put_when_success_then_save_params_receives_merged_full_dict(params_env):
    """B62b/C28 — `save_params` 는 **병합된 전체 dict** 로 호출된다(현행 동작 보존)."""
    status, _body = await _put("momentum", {"stop_loss_rate": -8.0})
    assert status == 200
    call = params_env.saved[-1]
    assert call["strategy_id"] == "momentum"
    assert call["params"] == params_env.params("momentum")


# ===========================================================================
# C25 · C26 · C27 — 응답 형태
# ===========================================================================
async def test_put_when_422_then_detail_is_list_with_msg_first_element(params_env):
    """B63/C25 — `detail` 은 배열, 각 원소에 한글 `msg`.

    프론트의 기존 추출기 `extractValidationMessage`(`detail[0].msg`)가 재포장 없이 동작한다.
    pydantic 접두사(`Value error, `)를 넣지 않는다.
    """
    status, body = await _put("momentum", {"stop_loss_rate": -50.0})
    assert status == 422
    first = _details(body)[0]
    assert isinstance(first.get("msg"), str) and first["msg"].strip(), first
    assert not first["msg"].startswith("Value error, "), first["msg"]
    assert any("가" <= ch <= "힣" for ch in first["msg"]), f"한글 메시지가 아니다: {first['msg']!r}"


async def test_put_when_unknown_strategy_then_200_success_false_not_422(params_env):
    """B64/C26 — 알 수 없는 전략 id 는 **현행대로** 200 + `success=false`.

    422 로 바꾸면 기존 호출자의 오류 처리가 달라진다.
    """
    status, body = await _put("ghost", {"position_ratio": 0.2})
    assert status == 200, body
    assert body["success"] is False
    assert not params_env.saved


async def test_put_when_success_then_response_contains_applied_keys(params_env):
    """B65/C27 — 성공 응답에 `data.applied`(저장된 키·값)와 `data.warnings`.

    서버가 무엇을 저장했는지 화면이 확인할 수 없으면 조용한 데이터 소실이 계속 보이지 않는다.
    """
    status, body = await _put("momentum", {"stop_loss_rate": -8.0})

    assert status == 200 and body["success"] is True, body
    data = body["data"]
    assert isinstance(data, dict), data
    applied = data.get("applied")
    assert applied == {"stop_loss_rate": -8.0}, f"applied={applied!r}"
    assert isinstance(data.get("warnings"), list)


# ===========================================================================
# C29 · C30 — 경고(200 동반)
# ===========================================================================
async def test_put_when_vb_k_value_nxt_post_sent_then_200_with_no_effect_warning(params_env):
    """B66/C29 — VB 의 `k_value_nxt_post` 는 저장되지만 "이 전략에선 무효" 경고가 붙는다.

    422 가 아니다 — 값 자체는 유효하고 VB `tradable_boards` 에 보드를 추가하면 되살아난다.
    """
    status, body = await _put("volatility_breakout", {"k_value_nxt_post": 1.2})

    assert status == 200, body
    assert "no_effect_for_strategy" in _warning_codes(body), _warnings(body)
    assert params_env.params("volatility_breakout")["k_value_nxt_post"] == 1.2


async def test_put_when_ltv_k_value_nxt_post_sent_then_no_warning(params_env):
    """B66b/C29 — §0 정정-2: LTV 는 그 키를 **실제로 곱한다** → 경고 없음.

    전역 `deprecated` 로 올리면 여기서 거짓 경고가 뜬다(M16).
    """
    status, body = await _put("long_tail_volatility", {"k_value_nxt_post": 1.2})

    assert status == 200, body
    assert "no_effect_for_strategy" not in _warning_codes(body), _warnings(body)


async def test_put_when_range_unbounded_key_sent_then_200_with_warning(params_env):
    """B66c/C30 — `max_scan_stocks`(range_src="none") 는 저장되고 `range_unbounded` 경고.

    범위 근거가 없다는 사실이 화면에 남는다. PARAM_RANGES 상한(500)을 범위로 쓰면
    bfb·vcp·kojiro 기본값 4000 이 즉시 422 다(HAZARD-1).
    """
    status, body = await _put("kojiro", {"max_scan_stocks": 3000})

    assert status == 200, f"근거 없는 범위로 4자리 기본값을 막았다 — {body!r}"
    assert "range_unbounded" in _warning_codes(body), _warnings(body)
    assert params_env.params("kojiro")["max_scan_stocks"] == 3000


# ===========================================================================
# identity 키 — 서버는 막지 않는다 (막는 것은 화면의 2단계 확인 절차다)
# ===========================================================================
@pytest.mark.parametrize(
    ("strategy_id", "payload"),
    [
        ("momentum", {"max_positions": 3}),
        ("momentum", {"tradable_boards": ["main"]}),
        ("donchian_swing", {"sizing_mode": "turtle"}),
        ("volatility_breakout", {"open_price_scope_mode": "off"}),
        ("volatility_breakout", {"llm_gate_mode": "off"}),
    ],
)
async def test_put_when_identity_key_then_saved_without_extra_server_gate(
    params_env, strategy_id: str, payload: dict[str, Any],
):
    """identity 키도 API 로는 저장 가능하다.

    서버가 확인 절차를 요구하면 장중 긴급 롤백(`PUT` 이 유일 경로 — `strategy_config`
    SQL UPDATE 는 다음 재시작에서만 반영, cycle232 D6)이 함께 막힌다.
    """
    status, body = await _put(strategy_id, payload)

    assert status == 200, f"identity 키 저장이 서버에서 막혔다 — 장중 롤백 경로 상실: {body!r}"
    for key, value in payload.items():
        assert params_env.params(strategy_id)[key] == value


# ===========================================================================
# 후속 시정 1 (MEDIUM · 가드 후퇴) — 빈 `tradable_boards` 는 422
# ===========================================================================
#
# 구 화면 `Settings.tsx::ExchangeBoardRow` 는 "최소 1개 이상의 매매 보드를 선택해야
# 합니다" 로 빈 목록 저장을 막고 있었다. cycle278 의 신규 편집기가 주 경로가 되면
# 그 가드가 화면에서 사라지므로, 정본을 **서버**로 올린다(화면 차단은 사전 안내다).
#
# 왜 200 이면 안 되는가 — 빈 목록의 효과가 전략마다 **정반대**다. 아래 두 테스트가
# 그 비대칭을 실측으로 못박는다.
_ALL_SEVEN = (
    "momentum",
    "volatility_breakout",
    "long_tail_volatility",
    "donchian_swing",
    "bull_flag_breakout",
    "vcp_breakout",
    "kojiro",
)

#: `session._DEFAULT_TRADABLE_BOARDS` 에 폴백 항목이 **있는** 전략 (빈 목록 → 매수 계속).
_BOARD_FALLBACK_STRATEGIES = (
    "momentum",
    "volatility_breakout",
    "long_tail_volatility",
    "donchian_swing",
)
#: 폴백 항목이 **없는** 전략 (빈 목록 → 허용 보드 공집합 → 매수 전면 중단).
_BOARD_NO_FALLBACK_STRATEGIES = ("bull_flag_breakout", "vcp_breakout", "kojiro")


def test_empty_boards_effect_is_asymmetric_across_strategies():
    """빈 목록 거부의 **근거** — 같은 값이 전략 절반에서 폴백, 절반에서 매수 중단.

    이 비대칭이 사라지면(예: 7 전략 전부 폴백을 갖게 되면) 422 의 근거가 약해지므로
    가드가 아니라 이 사실 자체를 먼저 다시 읽어야 한다.
    """
    from src.engine.session import get_tradable_boards

    assert set(_BOARD_FALLBACK_STRATEGIES) | set(_BOARD_NO_FALLBACK_STRATEGIES) == set(
        _ALL_SEVEN
    ), "두 코호트의 합이 7 전략이 아니다"

    for sid in _BOARD_FALLBACK_STRATEGIES:
        boards = get_tradable_boards(sid, {"tradable_boards": []})
        assert boards, (
            f"{sid}: 빈 목록이 코드 기본 보드로 폴백하지 않는다 — 이 사실이 바뀌면"
            " 422 메시지의 '저장했는데 아무 일도 일어나지 않는다' 설명이 거짓이 된다"
        )

    for sid in _BOARD_NO_FALLBACK_STRATEGIES:
        boards = get_tradable_boards(sid, {"tradable_boards": []})
        assert boards == frozenset(), (
            f"{sid}: 빈 목록이 공집합이 아니다 — 폴백이 생겼다면 422 메시지의"
            " '매수 전면 중단' 설명이 거짓이 된다"
        )


@pytest.mark.parametrize("strategy_id", _ALL_SEVEN)
async def test_put_when_tradable_boards_empty_then_422_too_few_items(
    params_env, strategy_id: str,
):
    """빈 `tradable_boards` 는 **7 전략 전부** 422 — 아무것도 저장되지 않는다."""
    before = params_env.snapshot(strategy_id)

    status, body = await _put(strategy_id, {"tradable_boards": []})

    assert status == 422, (
        f"{strategy_id}: 빈 보드 목록이 200 을 받았다 — 구 화면 가드의 후퇴: {body!r}"
    )
    entry = _entry(body, "too_few_items")
    assert entry["key"] == "tradable_boards"
    assert entry["given"] == []
    assert entry["expected"].get("min_items") == 1
    assert params_env.params(strategy_id) == before and not params_env.saved


async def test_put_when_boards_empty_then_message_points_to_disabling_strategy(params_env):
    """오류 문구가 **올바른 조작**을 가리킨다 — 보드를 비우지 말고 전략을 비활성화하라."""
    _, body = await _put("bull_flag_breakout", {"tradable_boards": []})
    msg = _entry(body, "too_few_items")["msg"]

    assert "비활성화" in msg, f"대안 조작을 안내하지 않는다: {msg}"
    assert "전면 중단" in msg and "폴백" in msg, (
        f"전략별 효과 비대칭을 설명하지 않는다: {msg}"
    )


async def test_put_when_exclude_tickers_empty_then_200(params_env):
    """다른 `list_str` 키의 빈 목록은 **정상**이다 — 일괄 규칙으로 막지 않는다.

    `exclude_tickers: []` 는 donchian·kojiro 의 코드 기본값("제외 없음")이다.
    빈 목록을 자료형 단위로 거부하면 그 기본값을 저장할 수 없게 된다 —
    그래서 판정은 카탈로그의 `min_items` 로만 한다.
    """
    from src.engine import param_catalog as pc

    assert pc.get_spec("exclude_tickers").min_items == 0
    status, body = await _put("donchian_swing", {"exclude_tickers": []})
    assert status == 200, body
    assert params_env.params("donchian_swing")["exclude_tickers"] == []


async def test_put_when_boards_nonempty_then_200(params_env):
    """비지 않은 목록은 종전대로 통과한다(가드가 정상 편집을 막지 않는다)."""
    status, body = await _put("kojiro", {"tradable_boards": ["main", "pre_nxt"]})
    assert status == 200, body
    assert params_env.params("kojiro")["tradable_boards"] == ["main", "pre_nxt"]


# ===========================================================================
# 후속 시정 2 (LOW · 절대 규칙 위반 경로) — VB + `post_nxt` 는 422
# ===========================================================================
async def test_put_when_vb_gets_post_nxt_then_422_forbidden_choice(params_env):
    """루트 `CLAUDE.md` 의 VB 조항을 화면 체크박스 한 번으로 깰 수 없다.

    "VB 당일 15:20 일괄매도 — `DEFAULT_TRADABLE_BOARDS=("main",)`, POST_NXT 추가 금지".
    VB 는 15:20 KRX 일괄 청산을 전제로 설계돼 있어 NXT 애프터(15:40~20:00)에 매수가
    열리면 그 종목이 청산 없이 다음 날로 넘어간다(사이클 26 이 없앤 OVERNIGHT 결함).
    """
    before = params_env.snapshot("volatility_breakout")

    status, body = await _put(
        "volatility_breakout", {"tradable_boards": ["main", "post_nxt"]},
    )

    assert status == 422, f"VB 에 post_nxt 가 저장됐다 — 절대 규칙 위반 경로: {body!r}"
    entry = _entry(body, "forbidden_choice")
    assert entry["key"] == "tradable_boards"
    assert entry["strategy_id"] == "volatility_breakout"
    assert "CLAUDE.md" in entry["msg"], f"근거를 밝히지 않는다: {entry['msg']}"
    assert "POST_NXT 추가 금지" in entry["msg"], entry["msg"]
    assert params_env.params("volatility_breakout") == before and not params_env.saved


async def test_put_when_ltv_gets_post_nxt_then_200(params_env):
    """LTV 는 3보드가 **정상**이다 — 금지는 전략별이고 키 단위 전역이 아니다.

    LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt","main","post_nxt")` (사용자 의도 —
    연속 상한가 익일 청산 + 야간 매수). 키 단위로 막으면 이 설계가 죽는다.
    """
    status, body = await _put(
        "long_tail_volatility", {"tradable_boards": ["pre_nxt", "main", "post_nxt"]},
    )

    assert status == 200, f"LTV 의 정상 3보드가 막혔다: {body!r}"
    assert params_env.params("long_tail_volatility")["tradable_boards"] == [
        "pre_nxt", "main", "post_nxt",
    ]


async def test_put_when_vb_removes_post_nxt_then_200(params_env):
    """이미 위반 중인 VB 를 **되돌리는** 저장은 통과한다(복구 경로 보존).

    금지 판정은 요청에 실린 값만 본다 — 현재값이 위반 중이라고 전략을 영구 편집 불가로
    만들면 복구 수단이 DB 직접 UPDATE 뿐이 된다(장중 재시작 금지 D6 때문에 더 위험).
    """
    params_env.params("volatility_breakout")["tradable_boards"] = ["main", "post_nxt"]

    status, body = await _put("volatility_breakout", {"tradable_boards": ["main"]})

    assert status == 200, f"위반 상태의 복구 저장이 막혔다: {body!r}"
    assert params_env.params("volatility_breakout")["tradable_boards"] == ["main"]


async def test_forbidden_choice_is_declared_only_for_vb_post_nxt():
    """금지 조합의 **정본 목록**은 카탈로그다 — 늘어나면 이 테스트가 알린다."""
    from src.engine import param_catalog as pc

    declared = [
        (spec.key, f.strategy_id, f.value)
        for spec in pc.PARAM_SPECS
        for f in spec.forbidden_choices
    ]
    assert declared == [("tradable_boards", "volatility_breakout", "post_nxt")], (
        f"금지 조합이 바뀌었다: {declared} — 신규 항목은 근거(루트 CLAUDE.md 조항 등)와"
        " 회귀 가드를 함께 추가한다"
    )
    assert pc.forbidden_choices_for("tradable_boards", "long_tail_volatility") == ()


# ===========================================================================
# 후속 시정 3 (LOW · 목 드리프트) — MSW 기본 핸들러 ↔ 실응답 형태 대조
# ===========================================================================
#
# ⚠️ 이 두 테스트는 **프론트/E2E 파일을 읽는 백엔드 가드**다 (cycle256 g251 관례).
# 프론트 전용 사이클의 검증 목록(`grep -rl 'frontend/' tests/unit`)에 이 파일이 걸리게
# 하려고 여기 명시한다.
#
# 왜 필요한가 — `handlers.ts` 의 기본 응답은 종전 `{ updated: true }` 였고, 서버는 그
# 모양을 한 번도 낸 적이 없다. 목이 *의도한 계약*만 담고 *실제 응답*을 담지 않으면
# 스위트는 초록인데 화면은 깨진다(cycle266 종목마스터 일봉 탭이 3개월 넘게 그랬다).
_MSW_HANDLERS = "frontend/src/test/handlers.ts"
_E2E_MOCKS = "e2e/fixtures/api-mocks.ts"


def _mock_source(rel: str) -> str:
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / rel
    assert path.exists(), f"{rel} 이 없다 — 목 파일이 이동했으면 이 가드를 함께 고친다"
    return path.read_text(encoding="utf-8")


def _keys_in_block(body: str, start_marker: str, keys: set[str]) -> set[str]:
    """`start_marker` 이후 **그 핸들러 하나** 안에 등장하는 최상위 키 이름들.

    창을 고정 길이로 잡으면 다음 핸들러(`/strategies/weights` 의 `{updated:true}`)까지
    새어 들어와 오탐이 난다 — 다음 라우트 등록(`http.`/`page.route(`)에서 자른다.
    """
    import re

    idx = body.index(start_marker)
    rest = body[idx + len(start_marker) :]
    cut = min(
        (m.start() for m in (re.search(r"\bhttp\.", rest), re.search(r"page\.route\(", rest))
         if m is not None),
        default=len(rest),
    )
    window = rest[:cut]
    assert window.strip(), f"핸들러 블록을 잘라내지 못했다 (marker={start_marker!r})"
    return {k for k in keys if re.search(rf"(?<![A-Za-z0-9_]){k}\s*:", window)}


async def test_msw_default_put_handler_matches_live_response_shape(params_env):
    """`handlers.ts` PUT 기본 응답의 최상위 키 = 실응답 `data` 의 키.

    형태만 잰다(값은 목이 자유롭게 정한다). GET 스키마 쪽
    `test_cycle278_params_schema.py::test_fixture_matches_live_schema_response` 와 같은 취지다.
    """
    status, body = await _put("momentum", {"max_positions": 3})
    assert status == 200, body
    live_keys = set(body["data"])
    assert live_keys, "실응답 data 가 비었다"

    src = _mock_source(_MSW_HANDLERS)
    found = _keys_in_block(src, "/strategies/:id/params`", live_keys | {"updated"})

    assert "updated" not in found, (
        f"{_MSW_HANDLERS}: 서버가 낸 적 없는 `updated` 키가 아직 있다 (cycle266 목 드리프트)"
    )
    assert found == live_keys, (
        f"{_MSW_HANDLERS}: PUT 기본 응답 키 {sorted(found)} != 실응답 {sorted(live_keys)}"
    )


async def test_e2e_put_mock_response_keys_are_subset_of_live(params_env):
    """Playwright 목의 200 응답 키는 실응답 키의 **부분집합**이다.

    부분집합까지만 요구하는 이유 — E2E 목은 `strategies`(레지스트리 전체 상태)처럼
    화면이 읽지 않는 무거운 필드를 일부러 생략한다. 실응답에 **없는** 키를 만들어 내는
    것만 결함이다.
    """
    status, body = await _put("momentum", {"max_positions": 3})
    assert status == 200, body
    live_keys = set(body["data"])

    src = _mock_source(_E2E_MOCKS)
    marker = 'await page.route("**/api/strategies/*/params", async (route)'
    found = _keys_in_block(src, marker, live_keys | {"updated"})

    assert "updated" not in found, f"{_E2E_MOCKS}: `updated` 키가 있다"
    assert found <= live_keys, (
        f"{_E2E_MOCKS}: 실응답에 없는 키 {sorted(found - live_keys)}"
    )
    assert "applied" in found and "warnings" in found, (
        f"{_E2E_MOCKS}: 화면이 읽는 두 필드가 없다 — got {sorted(found)}"
    )
