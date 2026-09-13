"""cycle290 Red — 개통 축: 두 킬스위치 키의 `PUT /api/strategies/{id}/params`.

정본 = cycle290 도메인 자문 §S6-D1 · 브리프 「개통 축」 (2026-09-13).

## 🔴 이 사이클 **전**에는 두 키가 `unknown_key` 였다 (회귀 봉인)

2026-09-13 실측:

    order_exchange_clock_mode   → param_catalog 없음 → PUT errors=[unknown_key] → 422
    after_market_exit_division  → param_catalog 없음 → PUT errors=[unknown_key] → 422

원인 = `param_validation.validate_params` 의 미지 키 판정이
`key not in current_params **or** spec is None` 이라 **카탈로그 등재와 전략
`DEFAULT_PARAMS` 등재가 둘 다** 필요하다. cycle287 은 "전략 7파일 diff 0" 제약 때문에
후자를 넣지 못했고, 그래서 09-14(월) 16:00~20:00 에 애프터 청산을 끌 수단이 셋 다
막혀 있었다(PUT 422 · SQL 은 재시작 후 · revert 재배포는 그 창의 재시작 그 자체).

⇒ **다음 사람이 카탈로그나 `DEFAULT_PARAMS` 에서 두 키를 빼면 이 파일이 붉어진다.**
그때 되돌아가는 상태가 위의 실측 로그다 — 고쳐야 할 것은 이 테스트가 아니라 등재다.

## 검증 패턴

TestClient 대신 **라우트 함수 직접 await** — 사이클 127 의 anyio portal hang 차단
관례이고 `tests/unit/routes/test_cycle278_params_validation.py` 가 같은 헬퍼를 쓴다.
브리프는 "TestClient 로 찔러라" 고 적었지만 이 리포에서는 그 관례가 우선이다(라우트
함수·검증·레지스트리·DB 저장 seam 을 전부 실제로 통과하므로 잰 범위는 같다).

## 🔴 `current_params` 를 손으로 만들지 않는다

cycle287 `test_s7` 이 합성 dict `{"exchange": ..., "tradable_boards": ...}` 를 넘겨
**등재 후에도 초록인 채로 거짓**이 된다(키가 그 dict 에 없으니 영원히 `unknown_key`).
이 파일은 실 `DEFAULT_PARAMS` 를 그대로 레지스트리에 심어 그 함정을 피한다.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

_MODE_KEY = "order_exchange_clock_mode"
_DIAL_KEY = "after_market_exit_division"
_NEW_KEYS: tuple[str, ...] = (_MODE_KEY, _DIAL_KEY)

_STRATEGY_IDS: tuple[str, ...] = (
    "momentum",
    "volatility_breakout",
    "long_tail_volatility",
    "donchian_swing",
    "bull_flag_breakout",
    "vcp_breakout",
    "kojiro",
)


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
    def __init__(self, sid: str, params: dict) -> None:
        self.strategy_id = sid
        self.config = SimpleNamespace(name=f"{sid}-전략", params=params)


class _FakeRegistry:
    def __init__(self, m: dict[str, _FakeStrategy]) -> None:
        self._m = m

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

    def clock_params(self, sid: str) -> tuple[str, str]:
        """등재가 열어야 하는 것 = 이 값이 실제로 바뀌는 것이다."""
        from src.engine.order_engine import OrderEngine

        return OrderEngine._clock_params(SimpleNamespace(registry=self.registry), sid)


@pytest.fixture
def env(monkeypatch):
    """라우트가 보는 레지스트리와 DB 저장을 격리한다(실 `DEFAULT_PARAMS` 기반)."""
    import src.db.strategy_config as sc
    from src.routes import strategies as st

    e = _Env(_FakeRegistry({
        sid: _FakeStrategy(sid, copy.deepcopy(d)) for sid, d in _class_defaults().items()
    }))

    async def _fake_save_params(strategy_id: str, params: dict) -> None:
        e.saved.append({"strategy_id": strategy_id, "params": copy.deepcopy(params)})

    monkeypatch.setattr(sc, "save_params", _fake_save_params, raising=True)
    monkeypatch.setattr(st, "save_params", _fake_save_params, raising=False)
    monkeypatch.setattr(st, "trading_scheduler", SimpleNamespace(registry=e.registry))
    return e


async def _put(sid: str, params: dict) -> tuple[int, dict]:
    """(status, body) — 422 는 어떤 경로로 와도 같은 모양으로 정규화한다."""
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import ValidationError

    from src.routes import strategies as st

    try:
        req = st.ParamsRequest(params=params)
    except ValidationError as exc:
        return 422, {"detail": exc.errors()}
    try:
        resp = await st.update_params(sid, req)
    except HTTPException as exc:
        return exc.status_code, {"detail": exc.detail}
    except ValidationError as exc:
        return 422, {"detail": exc.errors()}
    if isinstance(resp, JSONResponse):
        return resp.status_code, json.loads(bytes(resp.body).decode("utf-8"))
    return 200, resp.model_dump()


def _codes(body: dict) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for item in body.get("detail") or []:
        if isinstance(item, dict) and "key" in item and "code" in item:
            out.add((item["key"], item["code"]))
    return out


# ===========================================================================
# P1 — 7 전략 전부에서 기본값 PUT 이 200 (RED: 현재는 unknown_key 422)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("sid", _STRATEGY_IDS)
@pytest.mark.parametrize("key", _NEW_KEYS)
async def test_p290_1_put_default_value_returns_200_for_every_strategy(
    env, sid: str, key: str
) -> None:
    """RED — 두 키를 기본값으로 보내는 PUT 이 **7 전략 전부** 200 이다.

    라우팅·애프터 변환은 `strategy_id` 로 params 를 조회하는 전 전략 공통 경로다 —
    일부만 등재하면 나머지 전략은 여전히 422 이고, 하필 그 전략이 보유 중이면 그
    순간 끌 수단이 없다.
    """
    from src.engine import order_engine as oe

    value = (
        oe._ORDER_EXCHANGE_CLOCK_MODE_DEFAULT if key == _MODE_KEY
        else oe._AFTER_EXIT_DIVISION_DEFAULT
    )
    status, body = await _put(sid, {key: value})
    assert status == 200, (
        f"{sid}/{key} PUT 이 {status} — 2026-09-13 실측처럼 `unknown_key` 라면 "
        f"카탈로그/`DEFAULT_PARAMS` 등재가 빠진 것이다. detail={body.get('detail')}"
    )
    assert body["success"] is True, body
    assert body["data"]["applied"] == {key: value}, body["data"]["applied"]


# ===========================================================================
# P2 — 허용값 전수 저장 성공 + 메모리 즉시 반영
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["enforce", "sell_only", "off"])
async def test_p290_2_all_three_modes_are_accepted(env, mode: str) -> None:
    """RED — mode 허용값 3종이 전부 200 이고 `_clock_params` 가 그 값을 돌려준다.

    `enforce` = 현행 / `sell_only` = 매도만 라우팅(애프터 청산 유지, 16:00~19:50 LTV
    야간 매수 복귀) / `off` = 전면 정지(⚠️ 애프터 44/41 변환까지 함께 죽는다).
    """
    sid = "long_tail_volatility"
    status, body = await _put(sid, {_MODE_KEY: mode})
    assert status == 200, body.get("detail")
    assert env.params(sid)[_MODE_KEY] == mode
    assert env.clock_params(sid)[0] == mode, (
        "PUT 이 200 인데 `_clock_params` 가 그 값을 못 본다 — 메모리 반영 사슬이 끊겼다"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("dial", ["44", "41"])
async def test_p290_3_both_dials_are_accepted(env, dial: str) -> None:
    """RED — dial 허용값 2종이 전부 200 이고 `_clock_params` 가 그 값을 돌려준다.

    허용 집합은 `order_engine._AFTER_EXIT_DIVISION_ALLOWED` 가 정본이다 — 그 집합이
    바뀌면 `test_g290_34` 가 카탈로그 `choices` 와의 불일치를 먼저 잡는다.
    """
    from src.engine import order_engine as oe

    assert dial in oe._AFTER_EXIT_DIVISION_ALLOWED, "테스트 전제(허용 집합) 붕괴"
    sid = "long_tail_volatility"
    status, body = await _put(sid, {_DIAL_KEY: dial})
    assert status == 200, body.get("detail")
    assert env.params(sid)[_DIAL_KEY] == dial
    assert env.clock_params(sid)[1] == dial


@pytest.mark.asyncio
async def test_p290_4_both_keys_together_are_accepted(env) -> None:
    """RED — 두 키 동시 PUT 200 + `accepted` 2건 + `_clock_params` 동시 반영."""
    sid = "long_tail_volatility"
    status, body = await _put(sid, {_MODE_KEY: "sell_only", _DIAL_KEY: "41"})
    assert status == 200, body.get("detail")
    assert body["data"]["applied"] == {_MODE_KEY: "sell_only", _DIAL_KEY: "41"}
    assert env.clock_params(sid) == ("sell_only", "41")


# ===========================================================================
# P3 — 허용값 밖은 422 `not_in_choices` (RED: 지금은 `unknown_key`)
# ===========================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key, bad",
    [
        # 🔴 대소문자 변형이 가장 위험하다 — 읽는 쪽은 `mode == "off"` 정확 비교라
        #    "OFF" 가 저장되면 조용히 `enforce` 로 동작한다. enum 이 유일한 관문이다.
        (_MODE_KEY, "ENFORCE"),
        (_MODE_KEY, "OFF"),
        (_MODE_KEY, "on"),
        (_MODE_KEY, ""),
        (_MODE_KEY, "sell-only"),
        # dial 은 문자열이다 — 정수 44 는 거부돼야 한다(조용히 통과하면 안 된다).
        (_DIAL_KEY, "42"),
        (_DIAL_KEY, "00"),
        (_DIAL_KEY, "47"),
        (_DIAL_KEY, "01"),
        (_DIAL_KEY, 44),
    ],
)
async def test_p290_5_out_of_vocabulary_value_is_422_not_in_choices(
    env, key: str, bad
) -> None:
    """RED — 어휘 밖 값은 `not_in_choices` 422 이고 **아무것도 저장되지 않는다**.

    읽는 쪽은 미지 mode 를 `enforce` 로, 허용 밖 dial 을 `"44"` 로 해석한다(둘 다 청산을
    여는 방향). 그래서 오타를 막는 관문은 카탈로그 enum **하나**뿐이다 — DB 직접
    UPDATE 는 이 관문을 지나지 않는다.
    """
    sid = "long_tail_volatility"
    before = copy.deepcopy(env.params(sid))
    status, body = await _put(sid, {key: bad})
    assert status == 422, f"{key}={bad!r} 가 통과했다: {body}"
    assert (key, "not_in_choices") in _codes(body), (
        f"사유가 `not_in_choices` 가 아니다: {sorted(_codes(body))} — `unknown_key` 라면 "
        f"등재가 빠진 것이고, 그러면 **유효값도 저장할 수 없다**"
    )
    assert env.params(sid) == before, "422 인데 params 가 바뀌었다"
    assert not env.saved, "422 인데 save_params 가 호출됐다 (all-or-nothing 위반)"


@pytest.mark.asyncio
async def test_p290_6_mixed_valid_and_invalid_is_all_or_nothing(env) -> None:
    """RED — 유효 mode + 무효 dial 동시 전송 시 **둘 다** 저장되지 않는다."""
    sid = "long_tail_volatility"
    before = copy.deepcopy(env.params(sid))
    status, body = await _put(sid, {_MODE_KEY: "off", _DIAL_KEY: "42"})
    assert status == 422, body
    assert (_DIAL_KEY, "not_in_choices") in _codes(body), sorted(_codes(body))
    assert env.params(sid) == before
    assert not env.saved


# ===========================================================================
# P4 — 저장 사슬 사실 고정 (F-290-2)
# ===========================================================================
@pytest.mark.asyncio
async def test_p290_7_save_params_receives_the_merged_dict_including_both_keys(env) -> None:
    """RED — `save_params` 는 **병합된 전체 dict** 로 호출되고 두 키가 함께 박힌다.

    🔴 **F-290-2** — 라우트가 `save_params(sid, strategy.config.params)` 로 전체 dict 를
    쓰므로 배포 후 **아무 키든** 첫 PUT 을 받은 전략은 그 순간 두 키가
    `strategy_config.params` JSONB 에 박힌다. 그 뒤로는 `order_engine` 모듈 상수를
    바꿔도 그 전략에는 반영되지 않는다(DB 가 이긴다). 오늘의 행위 변경은 아니지만
    미래 사이클이 기본값을 옮길 때 조용히 안 듣는 전략이 생기는 경로이므로 문서와
    보고서에 남긴다. 99키 전부에 이미 적용되는 구조적 성질이다.
    """
    sid = "donchian_swing"
    status, _ = await _put(sid, {"max_positions": 5})
    assert status == 200
    assert len(env.saved) == 1
    persisted = env.saved[0]["params"]
    for key in _NEW_KEYS:
        assert key in persisted, (
            f"`{key}` 가 저장 dict 에 없다 — `DEFAULT_PARAMS` 등재가 빠졌다"
        )


@pytest.mark.asyncio
async def test_p290_8_identity_keys_are_not_blocked_by_the_server(env) -> None:
    """RED — identity 등급이어도 서버는 막지 않는다(2단계 확인은 **화면의 절차**).

    서버가 막으면 장중 긴급 롤백(PUT 이 유일 경로)이 함께 막힌다 —
    `update_params` 독스트링이 그 계약을 명문화하고 있다. `curl` 비상 경로 무영향.
    """
    from src.engine import param_catalog as pc

    for key in _NEW_KEYS:
        spec = pc.get_spec(key)
        assert spec is not None, f"`{key}` 스펙 부재"
        assert spec.risk == "identity", spec.risk

    status, body = await _put("kojiro", {_MODE_KEY: "off"})
    assert status == 200, body.get("detail")
    assert env.params("kojiro")[_MODE_KEY] == "off"


@pytest.mark.asyncio
async def test_p290_9_unknown_strategy_still_returns_200_success_false(env) -> None:
    """기존 계약 보존 — 미지 전략 id 는 422 가 아니라 200 + `success=false`."""
    status, body = await _put("no_such_strategy", {_MODE_KEY: "off"})
    assert status == 200, body
    assert body["success"] is False, body
