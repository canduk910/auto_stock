"""전략 비중 단위 계약 — PUT /api/strategies/weights (2026-08-18).

**확정 계약: 요청 바디 단위 = 비율(0.0 ~ 1.0). 퍼센트(0~100) 금지.**

종전 라우트는 `weights = {k: v / 100 if v > 1 else v ...}` 로 **값 크기를 보고 단위를
추측**했다. 프론트는 항상 정수 퍼센트를 보냈으므로 `1%`(=정수 1)는 `v > 1` 이 거짓이라
변환되지 않고 **비율 1.0(=100%)으로 저장**됐다. 운영 비중에 1% 짜리가 둘(VB·LTV)
있어 저장할 때마다 DB 합이 2.98 로 오염됐고, 프론트 로드 휴리스틱이 그 오염을
"3개 전략 33.3% 균등분배" 화면으로 위장했다.

DB 컬럼 · `GET /api/strategies` · `save_weights` · AI 자문 경로가 **이미 전부 비율**이고
PUT 바디 하나만 예외였다. 비율로 통일하면 GET↔PUT 왕복이 항등이 되고 추론 변환
코드 자체가 사라진다.

가드 대상 두 축:
1. **무변환** — 들어온 비율이 그대로 저장된다(추론 변환 부활 금지).
2. **시끄러운 거부** — 범위 위반(퍼센트/음수)은 422, Σ>1.0 오염 payload 는
   `success=False` + **저장/메모리 반영 0건**(split-brain 차단).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


@pytest.fixture
def weights_env(contract_env):
    """contract_env + 전략 비중(config.weight/enabled) 스냅샷 복원.

    `contract_env` 는 state 만 리셋하고 `config.weight` 는 되돌리지 않아
    비중 변경 테스트가 싱글톤 registry 를 오염시킨다. 이 fixture 안에서만
    스냅샷/복원해 다른 테스트에 누수시키지 않는다.
    """
    registry = contract_env.scheduler.registry
    snapshot = {
        s.strategy_id: (s.config.weight, s.config.enabled) for s in registry.all()
    }
    yield contract_env
    for sid, (weight, enabled) in snapshot.items():
        s = registry.get(sid)
        if s:
            s.config.weight = weight
            s.config.enabled = enabled


def _put(env, weights: dict):
    return env.client.put("/api/strategies/weights", json={"weights": weights})


# ---------------------------------------------------------------------------
# 1. 무변환 — 비율은 그대로 저장된다
# ---------------------------------------------------------------------------


def test_ratio_payload_saved_verbatim(weights_env):
    """비율 payload 는 어떤 변환도 거치지 않고 그대로 저장된다."""
    r = _put(weights_env, {"volatility_breakout": 0.01, "kojiro": 0.99})
    assert r.status_code == 200
    assert r.json()["success"] is True

    saved = weights_env.calls.save_weights[-1]["weights"]
    assert saved["volatility_breakout"] == pytest.approx(0.01)
    assert saved["kojiro"] == pytest.approx(0.99)


def test_integer_one_percent_no_longer_becomes_full_allocation(weights_env):
    """라이브 오염 재현 payload — 1% 전략이 100% 로 부풀지 않는다.

    운영 비중(kojiro 60 / donchian 18 / VB 1 / LTV 1 / BFB 10 / VCP 10)을
    **비율로** 보내면 6개 값이 전부 원본 그대로 저장되고 합은 정확히 1.0 이다.
    종전 추론 변환에서는 이 조합이 정수 퍼센트로 전송돼 VB·LTV 의 `1` 이
    각각 1.0(=100%)으로 저장되며 DB 합이 2.98 로 오염됐다.
    """
    payload = {
        "kojiro": 0.60,
        "donchian_swing": 0.18,
        "volatility_breakout": 0.01,
        "long_tail_volatility": 0.01,
        "bull_flag_breakout": 0.10,
        "vcp_breakout": 0.10,
    }
    r = _put(weights_env, payload)
    assert r.status_code == 200
    assert r.json()["success"] is True

    saved = weights_env.calls.save_weights[-1]["weights"]
    assert set(saved) == set(payload)
    for sid, expected in payload.items():
        assert saved[sid] == pytest.approx(expected), f"{sid} 값이 변환됐다"
    assert sum(saved.values()) == pytest.approx(1.0, abs=1e-3)

    # 같은 비중을 **퍼센트로** 보낸 레거시 형식은 조용히 흡수되지 않고 거부된다.
    legacy_percent = {sid: (w * 100) for sid, w in payload.items()}
    r2 = _put(weights_env, legacy_percent)
    assert r2.status_code == 422, "퍼센트 payload 가 조용히 변환되면 안 된다"


def test_value_exactly_one_alone_allowed(weights_env):
    """단독 몰빵(1.0)은 정당한 비율이다 — 경계값 통과."""
    r = _put(weights_env, {"kojiro": 1.0})
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert weights_env.calls.save_weights[-1]["weights"]["kojiro"] == pytest.approx(1.0)


@pytest.mark.parametrize("value", [0.0, 0.005, 0.5, 1.0])
def test_boundary_values(weights_env, value):
    """경계 비율은 무변환 통과한다."""
    before = len(weights_env.calls.save_weights)
    r = _put(weights_env, {"kojiro": value})
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert len(weights_env.calls.save_weights) == before + 1
    assert weights_env.calls.save_weights[-1]["weights"]["kojiro"] == pytest.approx(value)


def test_empty_payload_ok(weights_env):
    """빈 payload 는 성공(기존 행위 보존)."""
    r = _put(weights_env, {})
    assert r.status_code == 200
    assert r.json()["success"] is True


# ---------------------------------------------------------------------------
# 2. 시끄러운 거부 — 범위/Σ 위반
# ---------------------------------------------------------------------------


def test_percent_payload_rejected_loudly(weights_env):
    """퍼센트(0~100) payload 는 조용히 변환되지 않고 422 로 거부된다."""
    before = len(weights_env.calls.save_weights)
    r = _put(weights_env, {"momentum": 40, "donchian_swing": 30})
    assert r.status_code == 422, f"status={r.status_code} (조용히 통과했다)"
    assert len(weights_env.calls.save_weights) == before, "거부 payload 가 저장됐다"


def test_negative_weight_rejected(weights_env):
    """음수 비중은 422 로 거부된다."""
    before = len(weights_env.calls.save_weights)
    r = _put(weights_env, {"momentum": -0.5})
    assert r.status_code == 422, f"status={r.status_code} (조용히 통과했다)"
    assert len(weights_env.calls.save_weights) == before


def test_sum_over_one_rejected_and_nothing_saved(weights_env):
    """Σ > 1.0 payload 는 거부 + DB/메모리 **양쪽 모두 미반영**(split-brain 차단).

    라이브 오염 상태(Σ=2.98)를 그대로 저장 시도하는 시나리오. 거부 시
    `registry.update_weights` / `save_weights` 를 **호출하기 전에** early return
    해야 메모리와 DB 가 갈라지지 않는다.
    """
    registry = weights_env.scheduler.registry
    payload = {"kojiro": 0.6, "volatility_breakout": 1.0, "long_tail_volatility": 1.0}
    before_calls = len(weights_env.calls.save_weights)
    before_weights = {
        sid: registry.get(sid).config.weight for sid in payload if registry.get(sid)
    }

    r = _put(weights_env, payload)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False, "Σ=2.6 payload 가 통과했다"
    assert "100%" in (body["message"] or "")

    assert len(weights_env.calls.save_weights) == before_calls, "거부인데 DB 저장이 일어났다"
    for sid, weight in before_weights.items():
        assert registry.get(sid).config.weight == weight, (
            f"거부인데 메모리 비중이 바뀌었다: {sid}"
        )


def test_partial_payload_under_one_allowed(weights_env):
    """부분 payload(Σ<1)는 통과한다 — Σ 가드는 **초과만** 잡는 비대칭 가드.

    복구 저장(전략 하나만 되돌리기)을 막지 않기 위한 계약.
    """
    r = _put(weights_env, {"kojiro": 0.3})
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert weights_env.calls.save_weights[-1]["weights"]["kojiro"] == pytest.approx(0.3)
