"""cycle384 Red (P01) — 실 Postgres: `buy_paused` 가 JSONB **boolean** 으로 왕복하고 재시작 뒤에도 유지된다.

명세 = `_workspace/red/cycle384_buy_paused_spec.md` §9.6(P01) · §11.1-6(`jsonb_typeof = boolean`) · §12

잰 것:
- `strategy_config.save_params` → 실 JSONB 컬럼 → `jsonb_typeof(params->'buy_paused') = 'boolean'`
  (문자열 `"true"` 로 저장되면 게이트가 `is True` 로 읽어 **멈추지 않는다** — 조용한 해제).
- `load_all` 이 Python `True`(bool) 로 돌려준다.
- 새 스케줄러의 `_load_strategy_config` 가 메모리 params 에 True 를 덮는다 — 09-28 PUT 이 재시작
  (배포 full) 뒤에도 살아 있다. 코드 기본값(False)은 DB 값에 진다.
- 게이트까지 — 로드된 donchian 이 창 안 후보에 NONE.

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_SID = "donchian_swing"


def _fresh_scheduler():
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategy_registry import StrategyRegistry

    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = StrategyRegistry()
    s = DonchianSwingStrategy(StrategyConfig(strategy_id=_SID, name="d", enabled=True, weight=0.2,
                                             params={"exchange": "KRX"}))
    s.state.total_investment = 10_000_000
    sched.registry.register(s)
    sched._config_loaded = False
    return sched, s


async def test_p01_buy_paused_roundtrips_as_jsonb_boolean_and_survives_restart(
    clean_strategy_config, monkeypatch,
):
    from src.db import strategy_config
    from src.engine.strategy_base import Signal
    from tests.unit.engine._cycle369_support import Clock, kst
    from tests.unit.engine._cycle384_support import T, pin_clocks

    pg = clean_strategy_config
    _, template = _fresh_scheduler()
    assert template.config.params.get("buy_paused") is False, "[Red] donchian DEFAULT_PARAMS 에 buy_paused 없음"

    params = dict(template.config.params)
    params.update({"buy_paused": True, "sizing_mode": "turtle", "max_positions": 3, "stop_loss_rate": -6.0})
    await strategy_config.save_params(_SID, params)

    rows = await pg.fetch(
        "SELECT jsonb_typeof(params->'buy_paused') AS t, params->'buy_paused' AS v "
        "FROM strategy_config WHERE strategy_id = $1", _SID,
    )
    assert rows and rows[0]["t"] == "boolean", f"JSONB 에 boolean 이 아니라 {rows[0]['t'] if rows else None}"

    loaded = await strategy_config.load_all()
    assert loaded[_SID]["params"]["buy_paused"] is True

    sched, s = _fresh_scheduler()
    assert s.config.params["buy_paused"] is False
    await sched._load_strategy_config()
    assert s.config.params["buy_paused"] is True, "재시작 뒤 DB 의 멈춤이 메모리에 오르지 않았다"
    assert (s.config.params["sizing_mode"], s.config.params["max_positions"], s.config.params["stop_loss_rate"]) \
        == ("turtle", 3, -6.0), "운영값이 함께 로드되지 않았다"

    clock = Clock(kst(9, 10))
    pin_clocks(monkeypatch, clock, _SID)
    s._candidates[T] = {"prev_close": 10_000, "donchian_high": 10_500, "ema60": 9_000, "atr": 200}
    assert s.check_buy_signal(T, 10_600, 10_100) == Signal.NONE, "로드된 멈춤이 게이트에서 먹지 않았다"
