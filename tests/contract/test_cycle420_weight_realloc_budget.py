"""cycle420 — 같은 날 비중을 두 번 바꾸면 전략 예산이 부푸는 결함 (리팩토링 카드 #7).

정본 자문 = `_workspace/domain_consult/2026-10-09_weight_double_change.md`.
사용자 승인 2026-10-09 21:2x 「둘 다 권고대로 진행해」.

## 결함

`PUT /api/strategies/weights`(`src/routes/strategies.py`)가 재배분 기준 총액을
`Σ registry.all() 의 total_investment` 로 잡는다. 비중 0 으로 꺼진(=`enabled=False`)
전략은 `registry.allocate_funds()` 가 `enabled()` 만 다시 채우므로 그 전략의 옛 예산이
그 합에 그대로 남는다 — 다음 PUT 마다 기준 총액이 그 잔존분만큼 선형으로 불어난다.

## 권고 (자문 (나) + 꺼진 전략 예산 0 + 사각 경고)

1. 재배분 기준 총액 = `update_weights` 호출 **전** 켜진 전략들(`registry.enabled()`)의
   `total_investment` 합. 매수금액 하한선 검증도 같은 값을 쓴다.
2. 재배분 뒤, 이번 변경으로 꺼진(비중 0 & `enabled=False`, 섀도 제외) 전략의
   `total_investment` 를 0 으로 비운다.
3. 기준이 0 인 원인이 「직전 변경이 켜진 전략 비중을 전부 0 으로 만든 것」일 때만
   `[weight_realloc_skipped]` WARNING(21:30 리셋 뒤·부팅 전 정상 건너뜀에는 울리지 않는다).

## 시나리오 — R1~R3(현재 붉음) + G1~G5(회귀 방지)

기준선 = `momentum`·`volatility_breakout`·`long_tail_volatility`·`donchian_swing` 4전략
전부 켜짐·비중 합 1.0·전략당 1억(Σ=4억), 나머지 3전략은 꺼짐·0. 정수 절사가 있어
단언은 `abs(합 − 기준) ≤ 전략 수` 로 한다.
"""
from __future__ import annotations

import logging

import pytest

from src.engine.strategy_base import Position

pytestmark = pytest.mark.contract

_SIDS = ("momentum", "volatility_breakout", "long_tail_volatility", "donchian_swing")
_OTHER_SIDS = ("bull_flag_breakout", "vcp_breakout", "kojiro")
_WEIGHTS = (0.40, 0.25, 0.20, 0.15)
_BASE_TOTAL = 400_000_000
_TOL = 10  # 정수 절사 누적 허용오차(≤ 전략 수 × 몇 원)
_LOGGER_NAME = "src.routes.strategies"


@pytest.fixture
def budget_env(contract_env, monkeypatch):
    """`contract_env` + 비중/켜짐/예산/보유/파라미터 스냅샷 복원.

    `src.db.positions.load_all` 을 빈 목록으로 고정(비중 0 가드의 DB 조회가
    예외로 fail-open 되긴 하지만, 조용한 WARNING 없이 결정적으로 통과시킨다).
    `save_weights` 는 `keep_enabled` 키워드까지 받는 스파이로 교체한다
    (섀도 시나리오 — 기존 contract_env 가짜는 `weights` 하나만 받는다).
    """
    registry = contract_env.scheduler.registry

    async def _load_all_empty():
        return []

    monkeypatch.setattr("src.db.positions.load_all", _load_all_empty, raising=False)

    async def _fake_save_weights(weights, **kw):
        contract_env.calls.save_weights.append({"weights": dict(weights), **kw})

    import src.db.strategy_config as _sc

    monkeypatch.setattr(_sc, "save_weights", _fake_save_weights, raising=False)
    monkeypatch.setattr(
        "src.routes.recommendations.save_weights", _fake_save_weights, raising=False,
    )

    snap = {
        s.strategy_id: (
            dict(s.config.params), s.config.enabled, s.config.weight,
            dict(s.state.positions), s.state.total_investment,
        )
        for s in registry.all()
    }
    yield contract_env
    for s in registry.all():
        params, enabled, weight, positions, inv = snap[s.strategy_id]
        s.config.params.clear()
        s.config.params.update(params)
        s.config.enabled = enabled
        s.config.weight = weight
        s.state.positions.clear()
        s.state.positions.update(positions)
        s.state.total_investment = inv


def _put(env, weights: dict):
    return env.client.put("/api/strategies/weights", json={"weights": weights})


def _set_baseline(registry) -> None:
    """4전략 기준선 — 전부 켜짐 · 비중 합 1.0 · 전략당 1억(Σ=4억) · 보유 0."""
    for sid, w in zip(_SIDS, _WEIGHTS):
        s = registry.get(sid)
        s.config.weight = w
        s.config.enabled = True
        s.config.params.pop("shadow_mode", None)
        s.state.positions.clear()
        s.state.total_investment = 100_000_000
    for sid in _OTHER_SIDS:
        s = registry.get(sid)
        s.config.weight = 0.0
        s.config.enabled = False
        s.config.params.pop("shadow_mode", None)
        s.state.positions.clear()
        s.state.total_investment = 0


def _total_enabled_investment(registry) -> int:
    return sum(s.state.total_investment for s in registry.enabled())


# ===========================================================================
# R1 — 연속 2회 PUT 뒤 기준 총액이 불어나지 않는다 + 꺼진 전략 예산 0
# ===========================================================================


def test_r1_two_consecutive_puts_keep_budget_base_stable(budget_env):
    env = budget_env
    registry = env.scheduler.registry
    _set_baseline(registry)

    # PUT#1 — 보유 0 인 long_tail_volatility 를 비중 0 으로 끈다. 나머지가 재배분.
    r1 = _put(env, {
        "momentum": 0.50, "volatility_breakout": 0.25,
        "long_tail_volatility": 0.0, "donchian_swing": 0.25,
    })
    assert r1.status_code == 200 and r1.json()["success"] is True, r1.text

    ltv = registry.get("long_tail_volatility")
    assert ltv.config.enabled is False
    assert ltv.state.total_investment == 0, "꺼진 전략의 예산이 비워지지 않았다"

    enabled_sum_1 = _total_enabled_investment(registry)
    assert abs(enabled_sum_1 - _BASE_TOTAL) <= _TOL, (
        f"PUT#1 뒤 켜진 전략 예산 합이 기준({_BASE_TOTAL})에서 벗어났다: {enabled_sum_1}"
    )

    # PUT#2 — LTV 는 그대로 꺼진 채, 켜진 셋만 미세 조정.
    r2 = _put(env, {
        "momentum": 0.45, "volatility_breakout": 0.25, "donchian_swing": 0.30,
    })
    assert r2.status_code == 200 and r2.json()["success"] is True, r2.text

    enabled_sum_2 = _total_enabled_investment(registry)
    assert abs(enabled_sum_2 - _BASE_TOTAL) <= _TOL, (
        f"PUT#2 뒤 기준 총액이 부풀었다: {enabled_sum_2} (기준 {_BASE_TOTAL})"
    )
    assert ltv.state.total_investment == 0, "꺼진 전략의 예산이 다시 채워졌다"


# ===========================================================================
# R2 — 매수금액 하한선 검증도 부풀어난 기준으로 느슨해지면 안 된다
# ===========================================================================


def test_r2_lower_bound_uses_correct_total_asset_after_prior_put(budget_env):
    env = budget_env
    registry = env.scheduler.registry
    _set_baseline(registry)

    donchian = registry.get("donchian_swing")
    donchian.state.positions["005930"] = Position(
        ticker="005930", buy_price=80_000, quantity=1_000,
        order_no="1", strategy_id="donchian_swing",
    )
    # 참 하한 = 80,000,000 / 400,000,000 = 20%

    r1 = _put(env, {
        "momentum": 0.50, "volatility_breakout": 0.25,
        "long_tail_volatility": 0.0, "donchian_swing": 0.25,
    })
    assert r1.status_code == 200 and r1.json()["success"] is True, r1.text
    assert donchian.config.weight == pytest.approx(0.25)

    # PUT#2 — donchian 을 18% 로 내린다. 참 하한(20%) 미달이라 거부돼야 한다.
    r2 = _put(env, {
        "momentum": 0.47, "volatility_breakout": 0.25, "donchian_swing": 0.18,
    })
    body2 = r2.json()
    assert body2["success"] is False, (
        "진짜 하한(80,000,000/400,000,000=20%) 미달인 18% 요청이 통과했다 — "
        "부풀어난 기준 총액(직전 PUT 의 LTV 잔존분 포함)으로 하한선이 느슨해졌다"
    )
    assert donchian.config.weight == pytest.approx(0.25), "거부됐는데 메모리 비중이 바뀌었다"


# ===========================================================================
# R3 — 연속 3회 PUT 에도 선형 누적이 없다
# ===========================================================================


def test_r3_three_consecutive_puts_no_linear_growth(budget_env):
    env = budget_env
    registry = env.scheduler.registry
    _set_baseline(registry)

    puts = [
        {
            "momentum": 0.50, "volatility_breakout": 0.25,
            "long_tail_volatility": 0.0, "donchian_swing": 0.25,
        },
        {"momentum": 0.40, "volatility_breakout": 0.0, "donchian_swing": 0.60},
        {"momentum": 0.30, "volatility_breakout": 0.30, "donchian_swing": 0.40},
    ]
    for i, payload in enumerate(puts, start=1):
        r = _put(env, payload)
        assert r.status_code == 200 and r.json()["success"] is True, f"PUT#{i} 실패: {r.text}"
        total = _total_enabled_investment(registry)
        assert abs(total - _BASE_TOTAL) <= _TOL, (
            f"PUT#{i} 뒤 기준 총액이 불어났다: {total} (기준 {_BASE_TOTAL})"
        )


# ===========================================================================
# G1 — 섀도 전략은 비중 0 이어도 켜짐 유지 + 예산 0(회귀 방지, 현행도 초록)
# ===========================================================================


def test_g1_shadow_strategy_weight_zero_keeps_enabled_and_budget_zero(budget_env):
    env = budget_env
    registry = env.scheduler.registry
    _set_baseline(registry)

    vb = registry.get("volatility_breakout")
    vb.config.params["shadow_mode"] = True

    r = _put(env, {"volatility_breakout": 0.0})
    assert r.status_code == 200 and r.json()["success"] is True, r.text

    assert vb.config.enabled is True, "섀도 전략이 비중 0 에 꺼졌다"
    assert vb.state.total_investment == 0

    total = _total_enabled_investment(registry)
    assert abs(total - _BASE_TOTAL) <= _TOL


# ===========================================================================
# G2 — 같은 날 다시 켜도 기준 총액은 그대로다
# ===========================================================================


def test_g2_reenable_same_day_uses_consistent_base(budget_env):
    env = budget_env
    registry = env.scheduler.registry
    _set_baseline(registry)

    r1 = _put(env, {
        "momentum": 0.50, "volatility_breakout": 0.25,
        "long_tail_volatility": 0.0, "donchian_swing": 0.25,
    })
    assert r1.status_code == 200 and r1.json()["success"] is True, r1.text

    r2 = _put(env, {"long_tail_volatility": 0.20})
    assert r2.status_code == 200 and r2.json()["success"] is True, r2.text

    ltv = registry.get("long_tail_volatility")
    assert ltv.config.enabled is True
    assert ltv.state.total_investment > 0, "다시 켠 전략의 예산이 0 이다"

    total = _total_enabled_investment(registry)
    assert abs(total - _BASE_TOTAL) <= _TOL, (
        f"재켜기 뒤 기준 총액이 불어났다: {total} (기준 {_BASE_TOTAL})"
    )


# ===========================================================================
# G3 — AI 자문 적용(비중만) 경로는 allocate_funds 를 다시 부르지 않는다.
#      이어지는 PUT 의 기준 총액도 멀쩡해야 한다(같은 함수를 안 쓰므로 영향 없음 확인).
# ===========================================================================


def test_g3_apply_route_weight_only_then_put_keeps_budget_consistent(budget_env):
    env = budget_env
    registry = env.scheduler.registry
    _set_baseline(registry)

    env.state.recommendations.append({
        "id": "rec-c420-g3",
        "status": "pending",
        "strategy_id": "donchian_swing",
        "recommended_params": {},
        "recommended_weight": 0.10,
        "applied_params": {},
    })

    r_apply = env.client.post(
        "/api/recommendations/rec-c420-g3/apply",
        json={"keys": [], "apply_weight": True},
    )
    assert r_apply.status_code == 200 and r_apply.json()["success"] is True, r_apply.text

    donchian = registry.get("donchian_swing")
    assert donchian.config.weight == pytest.approx(0.10)
    # apply 경로는 allocate_funds 를 다시 부르지 않는다 — total_investment 그대로.
    assert donchian.state.total_investment == 100_000_000

    r_put = _put(env, {
        "momentum": 0.50, "volatility_breakout": 0.20,
        "long_tail_volatility": 0.20, "donchian_swing": 0.10,
    })
    assert r_put.status_code == 200 and r_put.json()["success"] is True, r_put.text

    total = _total_enabled_investment(registry)
    assert abs(total - _BASE_TOTAL) <= _TOL


# ===========================================================================
# G4 — 21:30 리셋 뒤(예산 전부 0, 켜진 비중 합 > 0) PUT → 재배분 없음 · 경고 없음
# ===========================================================================


def test_g4_after_daily_reset_put_skips_realloc_without_warning(budget_env, caplog):
    env = budget_env
    registry = env.scheduler.registry
    _set_baseline(registry)

    for sid in _SIDS:
        registry.get(sid).state.total_investment = 0

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        r = _put(env, {"momentum": 0.42, "volatility_breakout": 0.28, "donchian_swing": 0.30})
    assert r.status_code == 200 and r.json()["success"] is True, r.text

    assert all(registry.get(sid).state.total_investment == 0 for sid in _SIDS), (
        "예산 0 상태에서 재배분이 돌았다 — 다음 영업일 _boot 전에 잘못 할당됐다"
    )
    assert not any(
        "[weight_realloc_skipped]" in rec.message for rec in caplog.records
    ), "정상적인 건너뜀(21:30 리셋 뒤)인데 경고가 울렸다"


# ===========================================================================
# G5 — 사각: 켜진 전략 비중을 전부 0 으로 만든 뒤 하나를 다시 켜면
#      재배분이 건너뛰어지고(예산 0 유지) 경고가 울린다.
# ===========================================================================


def test_g5_all_enabled_turned_off_then_reenable_skips_with_warning(budget_env, caplog):
    env = budget_env
    registry = env.scheduler.registry
    _set_baseline(registry)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        r_a = _put(env, {
            "momentum": 0.0, "volatility_breakout": 0.0,
            "long_tail_volatility": 0.0, "donchian_swing": 0.0,
        })
        assert r_a.status_code == 200 and r_a.json()["success"] is True, r_a.text

        assert all(not registry.get(sid).config.enabled for sid in _SIDS)
        assert all(registry.get(sid).state.total_investment == 0 for sid in _SIDS)

        r_b = _put(env, {"momentum": 0.50})
        assert r_b.status_code == 200 and r_b.json()["success"] is True, r_b.text

    assert registry.get("momentum").config.enabled is True
    assert registry.get("momentum").state.total_investment == 0, (
        "재배분이 건너뛰어졌어야 하는데 예산이 채워졌다"
    )
    assert any(
        "[weight_realloc_skipped]" in rec.message for rec in caplog.records
    ), (
        "켜진 전략 비중이 전부 0 이 된 뒤 재배분이 건너뛰어졌는데 경고가 없다"
    )
