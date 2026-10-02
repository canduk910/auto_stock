"""cycle401 (D-1) — 실 Postgres: 행 없는 전략의 `save_params` 가 전략을 켜지 않는다.

잰 것:
- 빈 테이블 + `save_params(..., enabled=False, weight=0.0)` → 생긴 행이 `False`·0 이고,
  새 스케줄러의 `_load_strategy_config` 를 지나도 메모리가 꺼진 채다(재시작에 켜지지 않는다).
- 빈 테이블 + 키워드 없음 → `False`·0.
- 행 있음 + 다른 키워드 → 행의 `enabled`·`weight` 그대로, params 만 바뀐다.

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_SID = "donchian_swing"


def _fresh_scheduler(*, enabled: bool, weight: float):
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = StrategyRegistry()
    s = DonchianSwingStrategy(StrategyConfig(strategy_id=_SID, name="d", enabled=enabled,
                                             weight=weight, params={"exchange": "KRX"}))
    sched.registry.register(s)
    sched._config_loaded = False
    return sched, s


async def test_missing_row_with_memory_disabled_stays_disabled_after_restart(clean_strategy_config):
    from src.db import strategy_config

    pg = clean_strategy_config
    _, mem = _fresh_scheduler(enabled=False, weight=0.0)
    await strategy_config.save_params(
        _SID, dict(mem.config.params), enabled=mem.config.enabled, weight=mem.config.weight,
    )

    rows = await pg.fetch("SELECT enabled, weight FROM strategy_config WHERE strategy_id = $1", _SID)
    assert rows and rows[0]["enabled"] is False and float(rows[0]["weight"]) == 0.0, rows

    # 재시작 — 코드 등록값이 켜져 있어도 DB 값(False·0)이 이긴다 = 저장이 상태를 바꾸지 않았다
    sched, s = _fresh_scheduler(enabled=True, weight=0.2)
    await sched._load_strategy_config()
    assert s.config.enabled is False, "파라미터 저장 하나로 새 전략이 재시작에 켜졌다"
    assert s.config.weight == 0.0


async def test_missing_row_without_memory_values_writes_disabled_zero(clean_strategy_config):
    from src.db import strategy_config

    pg = clean_strategy_config
    await strategy_config.save_params(_SID, {"exchange": "KRX"})
    rows = await pg.fetch("SELECT enabled, weight FROM strategy_config WHERE strategy_id = $1", _SID)
    assert rows[0]["enabled"] is False
    assert float(rows[0]["weight"]) == 0.0


async def test_existing_row_keeps_enabled_weight_regardless_of_memory(clean_strategy_config):
    from src.db import strategy_config

    await strategy_config.save(_SID, True, 0.25, {"old": 1})
    await strategy_config.save_params(_SID, {"new": 2}, enabled=False, weight=0.9)
    loaded = (await strategy_config.load_all())[_SID]
    assert loaded == {"enabled": True, "weight": 0.25, "params": {"new": 2}}
