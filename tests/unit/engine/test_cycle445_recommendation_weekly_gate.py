"""cycle445 D8 — `generate_recommendations()` 가 주간 자문일에만 돈다.

시나리오:
- T1: 주간 자문일이 아니면(`should_run_weekly_advisory` → `run=False`) OpenAI 호출·
  DB INSERT·백테스트 enqueue 가 전부 0 — 매일 돌던 비용(30일 589:2 조임 실측,
  `weekly_advice_2026-10-08.md` §5.3)을 끈다.
- T2: 주간 자문일이면(`run=True`) 기존 흐름이 byte 그대로 돈다(회귀).
- T3: `generate_recommendations()` 시그니처는 그대로 무인자(`test_recommendation_engine_smoke.py`
  의 기존 단언과 공존 — 게이트는 함수 안에서 `now`/`settings` 로 판정한다).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

SIX_STRATEGIES = [
    "momentum",
    "volatility_breakout",
    "donchian_swing",
]


def _fake_strategy(strategy_id: str):
    return SimpleNamespace(
        strategy_id=strategy_id,
        config=SimpleNamespace(
            name=strategy_id,
            weight=0.2,
            params={"buy_threshold": 29.0, "stop_loss_rate": -7.5},
        ),
        state=SimpleNamespace(),
    )


def _wire_registry(monkeypatch):
    from src.engine.scheduler import trading_scheduler

    fake_registry = SimpleNamespace(
        enabled=lambda: [_fake_strategy(s) for s in SIX_STRATEGIES],
    )
    monkeypatch.setattr(trading_scheduler, "registry", fake_registry)


def _wire_openai_key(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "test-key", raising=False)


async def test_t1_non_advisory_day_skips_everything(monkeypatch):
    from src.engine import recommendation_engine as rec_mod
    from src.engine import weekly_advisory as wa

    _wire_registry(monkeypatch)
    _wire_openai_key(monkeypatch)

    async def fake_should_run(now):
        return {"run": False, "weekday_code": "thu", "configured_valid": False}

    monkeypatch.setattr(wa, "should_run_weekly_advisory", fake_should_run)

    openai_calls: list = []
    insert_calls: list = []
    expire_calls: list = []

    async def fake_call_openai(**kwargs):
        openai_calls.append(kwargs)
        return {}

    async def fake_insert_recommendation(**kwargs):
        insert_calls.append(kwargs)
        return {"id": "rec"}

    async def fake_expire(target_date):
        expire_calls.append(target_date)
        return 0

    monkeypatch.setattr(rec_mod, "_call_openai", fake_call_openai)
    monkeypatch.setattr(rec_mod, "insert_recommendation", fake_insert_recommendation)
    monkeypatch.setattr(rec_mod, "expire_pending_before", fake_expire)

    bt_calls: list = []

    async def fake_enqueue(*a, **kw):
        bt_calls.append((a, kw))

    monkeypatch.setattr(rec_mod, "_enqueue_backtest_jobs", fake_enqueue)

    result = await rec_mod.generate_recommendations()

    assert result == []
    assert openai_calls == [], "주간 자문일이 아닌데 OpenAI 를 불렀다"
    assert insert_calls == [], "주간 자문일이 아닌데 parameter_recommendations 를 썼다"
    assert bt_calls == [], "주간 자문일이 아닌데 백테스트 enqueue 가 발화했다"
    # expire_pending_before 는 게이트 밖(다음 자문일에 밀려도 안전) — 호출 안 함을 확인
    assert expire_calls == []


async def test_t2_advisory_day_runs_normally(monkeypatch):
    from src.engine import recommendation_engine as rec_mod
    from src.engine import weekly_advisory as wa

    _wire_registry(monkeypatch)
    _wire_openai_key(monkeypatch)

    async def fake_should_run(now):
        return {"run": True, "weekday_code": "thu", "configured_valid": False}

    monkeypatch.setattr(wa, "should_run_weekly_advisory", fake_should_run)

    async def fake_expire(target_date):
        return 0

    async def fake_get_trades_in_range(*a, **kw):
        return []

    async def fake_get_performance(*a, **kw):
        return []

    def fake_compute_metrics(*a, **kw):
        return {}

    openai_calls: list = []

    async def fake_call_openai(**kwargs):
        openai_calls.append(kwargs)
        return {"recommended_params": {"stop_loss_rate": -6.0}, "reasoning": "ok"}

    insert_calls: list = []

    async def fake_insert_recommendation(**kwargs):
        insert_calls.append(kwargs)
        return {"id": f"rec-{kwargs['strategy_id']}"}

    monkeypatch.setattr(rec_mod, "expire_pending_before", fake_expire)
    monkeypatch.setattr(rec_mod, "get_trades_in_range", fake_get_trades_in_range)
    monkeypatch.setattr(rec_mod, "get_performance", fake_get_performance)
    monkeypatch.setattr(rec_mod, "compute_metrics", fake_compute_metrics)
    monkeypatch.setattr(rec_mod, "_call_openai", fake_call_openai)
    monkeypatch.setattr(rec_mod, "insert_recommendation", fake_insert_recommendation)

    bt_calls: list = []

    async def fake_enqueue(*a, **kw):
        bt_calls.append((a, kw))

    monkeypatch.setattr(rec_mod, "_enqueue_backtest_jobs", fake_enqueue)

    result = await rec_mod.generate_recommendations()

    assert len(result) == len(SIX_STRATEGIES)
    assert len(openai_calls) == len(SIX_STRATEGIES)
    assert len(insert_calls) == len(SIX_STRATEGIES)
    assert len(bt_calls) == 1, "주간 자문일인데 백테스트 enqueue 가 안 돌았다"


def test_t3_signature_still_zero_args():
    import inspect

    from src.engine.recommendation_engine import generate_recommendations

    sig = inspect.signature(generate_recommendations)
    assert len(sig.parameters) == 0
