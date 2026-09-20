"""cycle333 — AI 자문 적용 경로가 **비중 0 가드를 우회**한다.

발견 = 다음 작업 식별 워크플로 B5

## 결함

cycle325 는 「보유 중인 전략의 비중을 0 으로 만들지 못한다」를 세웠다. 이유 =
`registry.update_weights` 가 **`config.enabled = weight > 0` 을 자동 토글**하고
`risk.on_tick` 은 `registry.enabled()` 만 순회하므로, **비중 0 = 비활성화 =
그 전략 보유분의 손절·트레일링·익일청산·15:20 청산이 전부 정지**다.

그런데 그 가드는 `PUT /api/strategies/weights`(`routes/strategies.py`) **한 문**에만
있다. `POST /api/recommendations/{id}/apply`(`routes/recommendations.py`)는
`save_weights()` 를 **가드 없이** 부른다.

## 도달 경로 — 운영자의 클릭 한 번

1. 20:00 AI 자문이 `recommended_weight = 0.0` 을 낸다
   (`recommendation_engine` 의 검증은 0 을 유효한 비중으로 받는다 — 범위가 `[0, 1]` 이다).
2. 운영자가 자문 화면에서 「비중도 함께 적용」 체크박스를 누른다.
3. `save_weights({sid: 0.0})` → DB `strategy_config.weight = 0` · `enabled = False`.

🔴 **당일은 아무 일도 안 일어난다** — 이 경로는 `strategy.config.weight` 만 메모리에
반영하고 `enabled` 는 안 건드리므로 그날은 계속 돈다(화면·로그 정상). 다음 재시작에서
`_load_strategy_config` 가 DB 의 `enabled=False` 를 읽는 순간 **그 전략 보유분의
손절이 전면 정지**한다. 즉 **사고와 발현 사이에 재시작 하나가 끼어 원인 추적이 끊긴다**.

1순위 위험 = kojiro(운영 DB 최대 비중·실보유).

## 시정

`save_weights` 직전에 cycle325 와 **같은 판정**을 건다. 보유가 있으면 비중 적용만
거부하고 **파라미터 적용은 그대로 진행**한다 — 자문의 나머지 권고까지 버릴 이유가 없다.
거부 사실은 응답과 로그 양쪽에 남긴다(조용한 skip 금지).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_apply_weight_zero_is_rejected_when_strategy_holds(monkeypatch):
    """🔴 보유 중인 전략에는 자문 경로로도 **비중 0 을 적용하지 못한다**.

    이것이 이 사이클의 계약이다. 지금은 `save_weights({sid: 0.0})` 가 그대로 나가
    DB `enabled=False` 가 되고, **다음 재시작에서** 그 전략 보유분의 손절이 멈춘다.
    """
    from src.routes import recommendations as mod

    calls = {"save_weights": []}

    async def fake_save_weights(weights):
        calls["save_weights"].append(dict(weights))
        return True

    async def held(strategy_id):
        return ["005930"] if strategy_id == "kojiro" else []

    monkeypatch.setattr(mod, "save_weights", fake_save_weights)
    monkeypatch.setattr(mod, "_weight_zero_blocked_by_holdings", held, raising=False)

    blocked = await mod._reject_zero_weight_if_held("kojiro", 0.0)
    assert blocked, (
        "보유 중인 전략의 비중 0 적용이 통과했다 — 다음 재시작에서 그 전략의 "
        "손절·트레일링·익일청산이 전부 멈춘다"
    )
    assert calls["save_weights"] == [], "거부했는데 save_weights 가 불렸다"


@pytest.mark.asyncio
async def test_apply_weight_zero_is_allowed_when_flat(monkeypatch):
    """보유가 없으면 비중 0 을 막지 않는다.

    이 가드가 지키는 것은 **보유분의 손절**이지 「비중 0 그 자체」가 아니다.
    보유 0 인 전략을 끄는 것은 정당한 운영 조작이다 — 막으면 전략을 영구히
    못 끄게 된다.
    """
    from src.routes import recommendations as mod

    async def held(strategy_id):
        return []

    monkeypatch.setattr(mod, "_weight_zero_blocked_by_holdings", held, raising=False)
    blocked = await mod._reject_zero_weight_if_held("vcp_breakout", 0.0)
    assert not blocked, "보유 0 인 전략까지 막았다 — 전략을 영구히 끌 수 없게 된다"


@pytest.mark.asyncio
async def test_positive_weight_is_never_blocked(monkeypatch):
    """양수 비중은 판정 자체를 하지 않는다.

    보유 조회는 DB 왕복이다. 비중 0 이 아닌 대다수 호출에 그 비용을 얹으면 안 되고,
    더 중요하게는 **조회가 실패하는 날 정상 비중 적용까지 막히면 안 된다**.
    """
    from src.routes import recommendations as mod

    called = {"n": 0}

    async def held(strategy_id):
        called["n"] += 1
        return ["005930"]

    monkeypatch.setattr(mod, "_weight_zero_blocked_by_holdings", held, raising=False)
    assert not await mod._reject_zero_weight_if_held("kojiro", 0.35)
    assert called["n"] == 0, "양수 비중인데 보유 조회를 했다"


@pytest.mark.asyncio
async def test_probe_failure_falls_open(monkeypatch):
    """🔴 보유 조회가 실패하면 **막지 않는다**(fail-open).

    cycle325 초판이 여기서 한 번 틀렸다 — DB 조회 실패 시 무조건 거부했더니
    DB 없는 맥락까지 막아 기존 계약 테스트가 깨졌다. 이 가드는 **사고를 줄이는
    보조 장치**이지 비중 적용의 관문이 아니다. 판정 불가를 차단으로 바꾸면
    자문 적용 경로 전체가 DB 가용성에 묶인다.

    ⚠️ 대신 조용히 넘어가지 않는다 — 판정 실패는 WARNING 으로 남는다.
    """
    from src.routes import recommendations as mod

    async def boom(strategy_id):
        raise RuntimeError("DB 없음")

    monkeypatch.setattr(mod, "_weight_zero_blocked_by_holdings", boom, raising=False)
    assert not await mod._reject_zero_weight_if_held("kojiro", 0.0), (
        "보유 조회 실패를 차단으로 바꿨다 — 자문 적용이 DB 가용성에 묶인다"
    )


def test_apply_route_actually_calls_the_guard():
    """🔴 **배선 가드** — 라우트가 `save_weights` 를 부르기 전에 판정을 통과한다.

    위 네 케이스는 헬퍼의 *판정*만 본다. 헬퍼가 아무리 정확해도 **라우트가 그것을
    부르지 않으면** 뒷문은 열린 채다 — 실제로 가드 호출을 `if False:` 로 바꾸는
    돌연변이가 네 케이스를 **전부 통과했다**. 그물이 자기가 지킨다는 것을 판정하지
    못한 것이고, 이 케이스가 그 빈틈을 닫는다.

    AST 로 본다 — `apply_rec` 안에서 `save_weights(...)` 호출보다 **앞**에
    `_reject_zero_weight_if_held(...)` 호출이 있어야 한다.
    """
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[3] / "src" / "routes" / "recommendations.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "apply_rec"),
        None,
    )
    assert fn is not None, "`apply_rec` 를 찾지 못했다 — 가드의 대상이 사라졌다"

    def _call_lines(name: str) -> list[int]:
        out = []
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                f = n.func
                if (isinstance(f, ast.Name) and f.id == name) or (
                    isinstance(f, ast.Attribute) and f.attr == name
                ):
                    out.append(n.lineno)
        return sorted(out)

    saves = _call_lines("save_weights")
    guards = _call_lines("_reject_zero_weight_if_held")

    assert saves, "`save_weights` 호출이 없다 — 이 가드의 전제가 깨졌다(양성 대조군)"
    assert guards, (
        "라우트가 `_reject_zero_weight_if_held` 를 부르지 않는다 — "
        "헬퍼는 정확한데 뒷문은 그대로 열려 있다"
    )
    assert min(guards) < min(saves), (
        f"가드(line {min(guards)})가 `save_weights`(line {min(saves)}) 보다 뒤에 있다 — "
        "이미 저장된 뒤에 막는 것은 막는 것이 아니다"
    )
