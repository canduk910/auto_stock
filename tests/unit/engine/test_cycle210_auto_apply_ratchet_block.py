"""사이클 210 Red (P0-B) — auto_apply ratchet 차단.

> 명세: `_workspace/strategy_review/2026-07-14_phaseA_domain_analysis.md` 판단1
> Red memo: `_workspace/red/cycle210_auto_apply_ratchet_block.md`

배경: `auto_apply_recommendations` 의 `_CONSERVATIVE_KEYS` 게이트가 손절/일일한도/
비중을 **조이는 방향만** 자동 적용(완화 경로 없음) = 단조 ratchet → 전략 교살
(donchian daily_loss_limit -6 → -0.8 방치). 시정 = `_CONSERVATIVE_KEYS` 7키 전량
제거(빈 frozenset) → param 자동적용 0, weight 감액만 잔존.

Red 유효성 (production 미변경 = `_CONSERVATIVE_KEYS` 7키 잔존):
  - G-210-1 (빈 집합 단언) = FAIL (현재 7키 잔존)
  - G-210-2 (조임 param 미적용 단언) = FAIL (현재 조임 방향 자동적용)
  - G-210-3 (weight 감액 보존) = PASS (Green 후에도 유지 = 회귀 가드)
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

TARGET_DATE = date(2026, 7, 14)

# ratchet 대상 키 (손절 5 + 일일한도 1 + 비중 1)
_RATCHET_KEYS = frozenset({
    "stop_loss_rate",
    "daily_loss_limit",
    "intraday_stop_loss",
    "overnight_stop_loss",
    "stop_loss_main",
    "stop_loss_pre_nxt",
    "position_ratio",
})


def _make_rec(
    strategy_id: str,
    recommended_weight: float | None,
    recommended_params: dict | None = None,
):
    return {
        "id": f"rec-{strategy_id}",
        "strategy_id": strategy_id,
        "recommended_weight": recommended_weight,
        "recommended_params": recommended_params or {},
        "status": "pending",
        "target_date": TARGET_DATE.isoformat(),
    }


def _wire_common(monkeypatch, re_mod, rec, mock_strategy):
    """auto_apply_recommendations 공통 mock 배선 (기존 fixture 패턴 답습)."""
    monkeypatch.setattr(
        "src.db.system_config.get_auto_apply_enabled", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "src.db.parameter_recommendations.list_pending_by_date",
        AsyncMock(return_value=[rec]),
    )
    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_strategy
    mock_registry.all.return_value = [mock_strategy]

    import src.engine.scheduler as sched_mod
    mock_scheduler = MagicMock()
    mock_scheduler.registry = mock_registry
    monkeypatch.setattr(sched_mod, "trading_scheduler", mock_scheduler)

    save_weights_mock = AsyncMock()
    save_params_mock = AsyncMock()
    update_mock = AsyncMock()
    monkeypatch.setattr(re_mod, "save_weights", save_weights_mock)
    monkeypatch.setattr(re_mod, "save_params", save_params_mock)
    monkeypatch.setattr(
        "src.db.parameter_recommendations.update_recommendation_status", update_mock
    )
    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())
    return save_weights_mock, save_params_mock, update_mock


# ===========================================================================
# G-210-1 — _CONSERVATIVE_KEYS 빈 집합 (7키 전량 부재)
# ===========================================================================
def test_g210_1_conservative_keys_empty():
    """_CONSERVATIVE_KEYS 에 손절/일일한도/비중 7키 전부 부재 (빈 frozenset).

    Red: 현재 L952-960 에 7키 잔존 → FAIL.
    """
    from src.engine.recommendation_engine import _CONSERVATIVE_KEYS

    leaked = _RATCHET_KEYS & set(_CONSERVATIVE_KEYS)
    assert not leaked, (
        f"_CONSERVATIVE_KEYS 에 ratchet 키 잔존 금지 (사이클 210 param 자동적용 차단): "
        f"{sorted(leaked)}"
    )
    # 완전 빈 집합 의무 (weight 전용 auto_apply)
    assert len(_CONSERVATIVE_KEYS) == 0, (
        "_CONSERVATIVE_KEYS 는 빈 frozenset 이어야 함 (param 자동적용 0, weight 감액만 잔존)"
    )


# ===========================================================================
# G-210-2 (HIGH) — 조임 방향 param 자동적용 0 (행위)
# ===========================================================================
@pytest.mark.asyncio
async def test_g210_2_tightening_params_not_applied(monkeypatch):
    """손절/일일한도 조임 + position_ratio 축소 자문 → applied_params 미반영.

    현재 코드 = 조임 방향(is_conservative) 자동적용 → FAIL.
    Green(빈 _CONSERVATIVE_KEYS) 후 = param 미적용 → PASS.
    """
    from src.engine import recommendation_engine as re_mod

    rec = _make_rec(
        "donchian_swing",
        recommended_weight=None,  # weight 미제안 → param 경로만 검증
        recommended_params={
            "stop_loss_rate": -3.0,      # 현재 -6 → -3 (더 조임: 절대값 감소 = 기존 게이트 통과)
            "daily_loss_limit": -1.0,    # 현재 -6 → -1 (더 조임)
            "position_ratio": 0.3,       # 현재 0.5 → 0.3 (축소)
        },
    )

    mock_strategy = MagicMock()
    mock_strategy.strategy_id = "donchian_swing"
    mock_strategy.config.weight = 0.2
    mock_strategy.config.params = {
        "stop_loss_rate": -6.0,
        "daily_loss_limit": -6.0,
        "position_ratio": 0.5,
    }

    _sw, save_params_mock, update_mock = _wire_common(
        monkeypatch, re_mod, rec, mock_strategy
    )

    await re_mod.auto_apply_recommendations(TARGET_DATE)

    # 전략 인스턴스 params 가 조임 자문으로 변경되지 않아야 함
    assert mock_strategy.config.params["stop_loss_rate"] == -6.0, (
        "stop_loss_rate param 자동적용 금지 (사이클 210 ratchet 차단)"
    )
    assert mock_strategy.config.params["daily_loss_limit"] == -6.0, (
        "daily_loss_limit param 자동적용 금지"
    )
    assert mock_strategy.config.params["position_ratio"] == 0.5, (
        "position_ratio param 자동적용 금지"
    )
    # save_params 호출 금지 (auto_params 비어있음)
    save_params_mock.assert_not_called()
    # update_recommendation_status 의 applied_params 에 ratchet 키 부재
    if update_mock.call_args is not None:
        applied = update_mock.call_args.kwargs.get("applied_params")
        if applied:
            assert not (_RATCHET_KEYS & set(applied)), (
                f"applied_params 에 ratchet 키 잔존 금지: "
                f"{sorted(_RATCHET_KEYS & set(applied))}"
            )


# ===========================================================================
# G-210-3 (HIGH) — weight 감액은 여전히 자동 적용 (순기능 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_g210_3_weight_reduction_still_applied(monkeypatch):
    """recommended_weight < current → save_weights 호출 (param 차단이 weight 훼손 X).

    param ratchet 차단이 auto_apply weight 감액 순기능을 보존하는지 확인.
    Green 전후 모두 PASS = 회귀 가드.
    """
    from src.engine import recommendation_engine as re_mod

    rec = _make_rec(
        "donchian_swing",
        recommended_weight=0.1,  # current 0.2 → 감액
        recommended_params={"stop_loss_rate": -3.0},  # 조임 param 동반 (미적용 기대)
    )

    mock_strategy = MagicMock()
    mock_strategy.strategy_id = "donchian_swing"
    mock_strategy.config.weight = 0.2
    mock_strategy.config.params = {"stop_loss_rate": -6.0}

    save_weights_mock, save_params_mock, _upd = _wire_common(
        monkeypatch, re_mod, rec, mock_strategy
    )

    result = await re_mod.auto_apply_recommendations(TARGET_DATE)

    assert result["applied"] >= 1
    # weight 감액 적용됨
    save_weights_mock.assert_called_once()
    weights_dict = save_weights_mock.call_args[0][0]
    assert weights_dict.get("donchian_swing") == pytest.approx(0.1), (
        "weight 감액(0.2→0.1)은 여전히 자동 적용 (순기능 보존)"
    )
    # 동반 param 은 미적용
    assert mock_strategy.config.params["stop_loss_rate"] == -6.0, (
        "동반 조임 param 은 자동적용 금지 (weight 만 적용)"
    )
    save_params_mock.assert_not_called()
