"""사이클 23 P3-1+2 Red — auto_apply_recommendations() 자동 적용 함수.

요구 행위:
1. auto_apply_enabled=False → {"applied": 0, "reason": "disabled"} 반환, DB 변경 0
2. recommended_weight < current_weight → save_weights 호출, applied_auto 상태 마킹
3. recommended_weight > current_weight → SKIP (증액 차단) + [auto_apply_skip_increase] 로그
4. recommended_weight < current_weight × 0.5 → new_weight = current_weight × 0.5 (50% cap)
5. 보수적 키 (stop_loss_rate=-5 from -7) 자동 적용, 비보수적 키 (k_value_krx_main=1.5) skip
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

pytestmark = pytest.mark.unit

TARGET_DATE = date(2026, 5, 20)


def _make_rec(
    strategy_id: str,
    recommended_weight: float | None,
    current_weight: float = 0.2,
    recommended_params: dict | None = None,
    status: str = "pending",
):
    return {
        "id": f"rec-{strategy_id}",
        "strategy_id": strategy_id,
        "recommended_weight": recommended_weight,
        "recommended_params": recommended_params or {},
        "status": status,
        "target_date": TARGET_DATE.isoformat(),
    }


# ---------------------------------------------------------------------------
# 케이스 1: auto_apply_enabled=False → disabled 반환
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_apply_disabled_returns_disabled(monkeypatch):
    """auto_apply_enabled=False 시 즉시 {"applied": 0, "reason": "disabled"} 반환."""
    from src.engine import recommendation_engine as re_mod

    monkeypatch.setattr(
        "src.db.system_config.get_auto_apply_enabled", AsyncMock(return_value=False)
    )

    result = await re_mod.auto_apply_recommendations(TARGET_DATE)

    assert result["applied"] == 0
    assert result.get("reason") == "disabled"


# ---------------------------------------------------------------------------
# 케이스 2: recommended_weight < current_weight → 자동 감액 적용
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_apply_reduces_weight_when_recommended_less(monkeypatch):
    """recommended_weight < current_weight → save_weights 호출 + applied_auto 마킹."""
    from src.engine import recommendation_engine as re_mod

    rec = _make_rec("donchian_swing", recommended_weight=0.1, current_weight=0.2)

    # get_auto_apply_enabled
    monkeypatch.setattr(
        "src.db.system_config.get_auto_apply_enabled", AsyncMock(return_value=True)
    )
    # list_pending_by_date
    monkeypatch.setattr(
        "src.db.parameter_recommendations.list_pending_by_date",
        AsyncMock(return_value=[rec]),
    )
    # registry mock
    mock_strategy = MagicMock()
    mock_strategy.strategy_id = "donchian_swing"
    mock_strategy.config.weight = 0.2
    mock_strategy.config.params = {}
    mock_registry = MagicMock()
    mock_registry.all.return_value = [mock_strategy]
    mock_registry.get.return_value = mock_strategy

    import src.engine.scheduler as sched_mod
    mock_scheduler = MagicMock()
    mock_scheduler.registry = mock_registry
    monkeypatch.setattr(sched_mod, "trading_scheduler", mock_scheduler)

    save_weights_mock = AsyncMock()
    monkeypatch.setattr(re_mod, "save_weights", save_weights_mock)
    update_mock = AsyncMock()
    monkeypatch.setattr(
        "src.db.parameter_recommendations.update_recommendation_status", update_mock
    )
    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())

    result = await re_mod.auto_apply_recommendations(TARGET_DATE)

    assert result["applied"] >= 1
    save_weights_mock.assert_called_once()
    # status='applied_auto' 마킹 확인
    update_mock.assert_called_once()
    call_kwargs = update_mock.call_args
    assert "applied_auto" in str(call_kwargs)


# ---------------------------------------------------------------------------
# 케이스 3: recommended_weight > current_weight → SKIP (증액 차단)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_apply_skips_weight_increase(monkeypatch):
    """recommended_weight > current_weight → SKIP (증액 차단) + [auto_apply_skip_increase] 로그."""
    from src.engine import recommendation_engine as re_mod

    rec = _make_rec("donchian_swing", recommended_weight=0.4, current_weight=0.2)

    monkeypatch.setattr(
        "src.db.system_config.get_auto_apply_enabled", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "src.db.parameter_recommendations.list_pending_by_date",
        AsyncMock(return_value=[rec]),
    )

    mock_strategy = MagicMock()
    mock_strategy.strategy_id = "donchian_swing"
    mock_strategy.config.weight = 0.2
    mock_strategy.config.params = {}
    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_strategy
    mock_registry.all.return_value = [mock_strategy]

    import src.engine.scheduler as sched_mod
    mock_scheduler = MagicMock()
    mock_scheduler.registry = mock_registry
    monkeypatch.setattr(sched_mod, "trading_scheduler", mock_scheduler)

    save_weights_mock = AsyncMock()
    monkeypatch.setattr(re_mod, "save_weights", save_weights_mock)
    monkeypatch.setattr(
        "src.db.parameter_recommendations.update_recommendation_status", AsyncMock()
    )
    write_log_mock = AsyncMock()
    monkeypatch.setattr("src.db.system_logs.write_log", write_log_mock)

    result = await re_mod.auto_apply_recommendations(TARGET_DATE)

    assert result["applied"] == 0
    save_weights_mock.assert_not_called()
    # [auto_apply_skip_increase] 로그 발행 확인
    log_calls = [str(c) for c in write_log_mock.call_args_list]
    assert any("auto_apply_skip_increase" in c for c in log_calls)


# ---------------------------------------------------------------------------
# 케이스 4: recommended_weight < current_weight × 0.5 → 50% cap 발동
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_apply_50_percent_cap_applies(monkeypatch):
    """recommended_weight < current_weight × 0.5 → new_weight = current_weight × 0.5."""
    from src.engine import recommendation_engine as re_mod

    rec = _make_rec("donchian_swing", recommended_weight=0.05, current_weight=0.2)

    monkeypatch.setattr(
        "src.db.system_config.get_auto_apply_enabled", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "src.db.parameter_recommendations.list_pending_by_date",
        AsyncMock(return_value=[rec]),
    )

    mock_strategy = MagicMock()
    mock_strategy.strategy_id = "donchian_swing"
    mock_strategy.config.weight = 0.2
    mock_strategy.config.params = {}
    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_strategy
    mock_registry.all.return_value = [mock_strategy]

    import src.engine.scheduler as sched_mod
    mock_scheduler = MagicMock()
    mock_scheduler.registry = mock_registry
    monkeypatch.setattr(sched_mod, "trading_scheduler", mock_scheduler)

    save_weights_mock = AsyncMock()
    monkeypatch.setattr(re_mod, "save_weights", save_weights_mock)
    monkeypatch.setattr(
        "src.db.parameter_recommendations.update_recommendation_status", AsyncMock()
    )
    monkeypatch.setattr("src.db.system_logs.write_log", AsyncMock())

    result = await re_mod.auto_apply_recommendations(TARGET_DATE)

    assert result["applied"] >= 1
    # save_weights 에 전달된 weight 가 0.1 (current × 0.5) 이어야 함
    call_args = save_weights_mock.call_args
    weights_dict = call_args[0][0]  # 첫 번째 positional arg
    applied_w = weights_dict.get("donchian_swing")
    assert applied_w == pytest.approx(0.1)  # 0.2 × 0.5 = 0.1 (cap)


# ---------------------------------------------------------------------------
# 케이스 5: 보수적 파라미터 자동 적용 + 비보수적 키 skip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_apply_conservative_params_only(monkeypatch):
    """stop_loss_rate 보수적 변경(더 음수에서 덜 음수) 자동 적용, k_value_krx_main skip."""
    from src.engine import recommendation_engine as re_mod

    rec = _make_rec(
        "donchian_swing",
        recommended_weight=0.15,  # 감액 → 적용됨
        current_weight=0.2,
        recommended_params={
            "stop_loss_rate": -5.0,      # -7% → -5% (보수적: 절대값 감소)
            "k_value_krx_main": 1.5,     # 비보수적 키 — skip
        },
    )

    monkeypatch.setattr(
        "src.db.system_config.get_auto_apply_enabled", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "src.db.parameter_recommendations.list_pending_by_date",
        AsyncMock(return_value=[rec]),
    )

    mock_strategy = MagicMock()
    mock_strategy.strategy_id = "donchian_swing"
    mock_strategy.config.weight = 0.2
    mock_strategy.config.params = {"stop_loss_rate": -7.0, "k_value_krx_main": 1.0}
    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_strategy
    mock_registry.all.return_value = [mock_strategy]

    import src.engine.scheduler as sched_mod
    mock_scheduler = MagicMock()
    mock_scheduler.registry = mock_registry
    monkeypatch.setattr(sched_mod, "trading_scheduler", mock_scheduler)

    monkeypatch.setattr(re_mod, "save_weights", AsyncMock())
    save_params_mock = AsyncMock()
    monkeypatch.setattr(re_mod, "save_params", save_params_mock)
    monkeypatch.setattr(
        "src.db.parameter_recommendations.update_recommendation_status", AsyncMock()
    )
    write_log_mock = AsyncMock()
    monkeypatch.setattr("src.db.system_logs.write_log", write_log_mock)

    await re_mod.auto_apply_recommendations(TARGET_DATE)

    # stop_loss_rate 적용됨
    assert mock_strategy.config.params.get("stop_loss_rate") == -5.0
    # k_value_krx_main 변경 안 됨
    assert mock_strategy.config.params.get("k_value_krx_main") == 1.0
    # [auto_params_apply] 로그 발행
    log_calls = [str(c) for c in write_log_mock.call_args_list]
    assert any("auto_params_apply" in c for c in log_calls)
