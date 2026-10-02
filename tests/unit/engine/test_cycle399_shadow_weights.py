"""cycle399 Red — 섀도 전략은 비중 0 이어도 켜짐(`enabled`)을 지킨다 (w01~w07).

명세 정본 = `_workspace/red/cycle399_shadow_mode.md` §1 W1~W3 · §2
근거 = `_workspace/domain_consult/cycle398_refactor_cards_2_3.md` §3(c) — 「비중 0(예산 0 = 주문이 구조적으로
불가능) + `enabled=True` 유지」. 최소 비중은 Σ 정규화로 실전 전략 예산을 깎으므로 쓰지 않는다.

🔴 바꾸는 자리 `StrategyRegistry.update_weights` 는 8영역이다(사용자 승인 10-02 R1, 한 줄). 섀도가 아닌 전략의
`enabled = weight > 0` 은 그대로여야 한다 — w02 가 그 현행을 못박는다.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.engine._cycle384_support import make

pytestmark = pytest.mark.unit


def _reg(*strategies):
    from src.engine.strategy_registry import StrategyRegistry

    reg = StrategyRegistry()
    for s in strategies:
        reg.register(s)
    return reg


def _strat(sid: str, *, weight: float, enabled: bool = True, shadow=None):
    s = make(sid)
    s.config.weight = weight
    s.config.enabled = enabled
    if shadow is not None:
        s.config.params["shadow_mode"] = shadow
    return s


# ===========================================================================
# w01~w05 — update_weights
# ===========================================================================
def test_w01_shadow_strategy_keeps_enabled_at_weight_zero():
    s = _strat("vcp_breakout", weight=0.0, enabled=True, shadow=True)
    _reg(s).update_weights({"vcp_breakout": 0.0})
    assert s.config.weight == 0.0
    assert s.config.enabled is True, (
        "[Red] 섀도 전략이 비중 저장으로 꺼졌다 — 평가가 안 돌아 섀도 기록이 0 이 된다(ETF S1 함정)"
    )


def test_w01b_other_strategy_weight_save_does_not_turn_shadow_off():
    """비중 화면은 전 전략 비중을 한 번에 보낸다 — 다른 전략을 저장해도 섀도 전략이 꺼지면 안 된다."""
    sh = _strat("vcp_breakout", weight=0.0, enabled=True, shadow=True)
    real = _strat("kojiro", weight=0.4)
    _reg(sh, real).update_weights({"kojiro": 0.5, "vcp_breakout": 0.0})
    assert sh.config.enabled is True and real.config.enabled is True


@pytest.mark.parametrize("shadow", [False, None], ids=["shadow_false", "key_default"])
def test_w02_non_shadow_weight_zero_still_disables_byte_same(shadow):
    s = _strat("vcp_breakout", weight=0.2, enabled=True, shadow=shadow)
    _reg(s).update_weights({"vcp_breakout": 0.0})
    assert s.config.enabled is False, "섀도가 아닌 전략의 weight=0 → enabled=False 현행이 바뀌었다"


def test_w03_disabled_shadow_strategy_is_not_turned_on_by_weight_zero():
    s = _strat("vcp_breakout", weight=0.0, enabled=False, shadow=True)
    _reg(s).update_weights({"vcp_breakout": 0.0})
    assert s.config.enabled is False, "비중 저장이 꺼져 있던 섀도 전략을 켰다 — 켜기는 별도 승인 절차다"


def test_w04_positive_weight_enables_regardless_of_shadow():
    for shadow in (True, False):
        s = _strat("vcp_breakout", weight=0.0, enabled=False, shadow=shadow)
        _reg(s).update_weights({"vcp_breakout": 0.1})
        assert s.config.enabled is True


@pytest.mark.parametrize("value", ["true", 1, None], ids=["str_true", "one", "null"])
def test_w05_non_true_shadow_value_does_not_keep_enabled(value):
    s = _strat("vcp_breakout", weight=0.2, enabled=True, shadow=value)
    _reg(s).update_weights({"vcp_breakout": 0.0})
    assert s.config.enabled is False, f"{value!r} 를 섀도 켜짐으로 읽었다 — `is True` 만 켜짐"


def test_w05b_shadow_probe_is_static_and_never_raises():
    from src.engine.strategy_base import StrategyBase

    assert StrategyBase.shadow_mode_on(_strat("kojiro", weight=0.1, shadow=True)) is True
    assert StrategyBase.shadow_mode_on(_strat("kojiro", weight=0.1, shadow=False)) is False

    class Broken:
        config = None

    assert StrategyBase.shadow_mode_on(Broken()) is False, "판정 실패는 꺼짐(현행 weight>0 규칙)"


# ===========================================================================
# w06 — allocate_funds: 섀도 전략 예산 0, 다른 전략 예산은 그대로
# ===========================================================================
def test_w06_allocate_funds_shadow_zero_budget_others_unchanged():
    a, b = _strat("kojiro", weight=0.6), _strat("donchian_swing", weight=0.4)
    _reg(a, b).allocate_funds(10_000_000)
    base = (a.state.total_investment, b.state.total_investment)

    a2, b2 = _strat("kojiro", weight=0.6), _strat("donchian_swing", weight=0.4)
    sh = _strat("vcp_breakout", weight=0.0, enabled=True, shadow=True)
    reg = _reg(a2, b2, sh)
    reg.update_weights({"vcp_breakout": 0.0})
    reg.allocate_funds(10_000_000)
    assert sh.config.enabled is True
    assert sh.state.total_investment == 0, "섀도 전략에 예산이 갔다 — 주문이 구조적으로 불가능해야 한다"
    assert (a2.state.total_investment, b2.state.total_investment) == base, (
        "섀도 전략이 실전 전략 예산을 깎았다 — 섀도가 실전 행위를 바꾸면 섀도가 아니다"
    )


# ===========================================================================
# w07 — DB save_weights(keep_enabled=…)
# ===========================================================================
def _enabled_arg(pg_mod) -> bool:
    # save(strategy_id, enabled, weight, params, updated_at) → execute(sql, *args)
    return pg_mod.execute.await_args.args[2]


@pytest.mark.parametrize("weight,keep,want", [
    (0.0, (), False),
    (0.0, ("vcp_breakout",), True),
    (0.0, ("kojiro",), False),
    (0.3, (), True),
    (0.3, ("vcp_breakout",), True),
], ids=["zero_no_keep", "zero_keep", "zero_keep_other", "pos", "pos_keep"])
async def test_w07_save_weights_keep_enabled(weight, keep, want):
    from src.db import strategy_config

    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"params": {"shadow_mode": True}}])
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        if keep:
            await strategy_config.save_weights({"vcp_breakout": weight}, keep_enabled=keep)
        else:
            await strategy_config.save_weights({"vcp_breakout": weight})
    assert _enabled_arg(pg_mod) is want


async def test_w07b_save_weights_without_keep_is_current_rule_even_if_db_params_shadow():
    """DB 행 params 만으로 판정하지 않는다 — 판정은 메모리를 가진 호출자가 한다(명세 §2)."""
    from src.db import strategy_config

    with patch.object(strategy_config, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"params": {"shadow_mode": True}}])
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await strategy_config.save_weights({"vcp_breakout": 0.0})
    assert _enabled_arg(pg_mod) is False
