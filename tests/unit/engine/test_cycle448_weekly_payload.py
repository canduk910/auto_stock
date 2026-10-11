"""cycle448 — 20:00 주간 자문 OpenAI payload 에 전략별 핵심값 분포를 얹는다.

사용자 결정(2026-10-11): 「주간자문에는 전략핵심값 분포가 필요할듯」. `generate_recommendations()`
가 `recommendation_engine._call_openai` 에 `core_metrics` 를 넘기고, `_call_openai` 는
`has_any_keys()` 가 참일 때만 `user_payload["core_metrics_distribution"]` 을 싣는다.

cycle445 D8 게이트(주간 자문일이 아니면 전체 스킵) 뒤에 이 계산이 자리하므로, 비-목요일에는
`strategy_core_metrics.collect_strategy_core_metrics` 가 **호출 0회**다 — 계산 자체를 하지
않는다(토큰·CPU 낭비 금지, 사용자 명시 요건).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def _fake_strategy(strategy_id: str, *, llm_ctx=None, scanned=()):
    llm_ctx = llm_ctx or {}

    def _llm_context(ticker):
        return dict(llm_ctx.get(ticker, {}))

    return SimpleNamespace(
        strategy_id=strategy_id,
        config=SimpleNamespace(
            name=strategy_id,
            weight=0.2,
            params={"buy_threshold": 29.0, "stop_loss_rate": -7.5},
        ),
        state=SimpleNamespace(positions={}),
        get_scanned_tickers=lambda: list(scanned),
        llm_context=_llm_context,
    )


def _wire_registry(monkeypatch, strategies):
    from src.engine.scheduler import trading_scheduler

    fake_registry = SimpleNamespace(enabled=lambda: list(strategies))
    monkeypatch.setattr(trading_scheduler, "registry", fake_registry)


def _wire_common(monkeypatch, rec_mod):
    async def fake_expire(target_date):
        return 0

    async def fake_get_trades_in_range(*a, **kw):
        return []

    async def fake_get_performance(*a, **kw):
        return []

    def fake_compute_metrics(*a, **kw):
        return {}

    async def fake_insert_recommendation(**kwargs):
        return {"id": f"rec-{kwargs['strategy_id']}"}

    async def fake_enqueue(*a, **kw):
        return None

    monkeypatch.setattr(rec_mod, "expire_pending_before", fake_expire)
    monkeypatch.setattr(rec_mod, "get_trades_in_range", fake_get_trades_in_range)
    monkeypatch.setattr(rec_mod, "get_performance", fake_get_performance)
    monkeypatch.setattr(rec_mod, "compute_metrics", fake_compute_metrics)
    monkeypatch.setattr(rec_mod, "insert_recommendation", fake_insert_recommendation)
    monkeypatch.setattr(rec_mod, "_enqueue_backtest_jobs", fake_enqueue)

    from src.config import settings
    monkeypatch.setattr(settings, "openai_api_key", "test-key", raising=False)


def _wire_weekly_gate(monkeypatch, *, run: bool):
    from src.engine import weekly_advisory as wa

    async def fake_should_run(now):
        return {"run": run, "weekday_code": "thu", "configured_valid": True}

    monkeypatch.setattr(wa, "should_run_weekly_advisory", fake_should_run)


async def test_weekly_day_includes_core_metrics_distribution_when_nonempty(monkeypatch):
    from src.engine import recommendation_engine as rec_mod

    strat = _fake_strategy("donchian_swing", scanned=["005930"], llm_ctx={"005930": {"atr": 150.0}})
    _wire_registry(monkeypatch, [strat])
    _wire_common(monkeypatch, rec_mod)
    _wire_weekly_gate(monkeypatch, run=True)

    captured_payloads: list[dict] = []

    class _FakeMessage:
        def __init__(self, content):
            self.content = content

    class _FakeChoice:
        def __init__(self, content):
            self.message = _FakeMessage(content)

    class _FakeResponse:
        def __init__(self, content):
            self.choices = [_FakeChoice(content)]

    class _FakeCompletions:
        async def create(self, *, model, messages, response_format):
            captured_payloads.append(messages[1]["content"])
            return _FakeResponse("{}")

    class _FakeChat:
        def __init__(self):
            self.completions = _FakeCompletions()

    class _FakeOpenAI:
        def __init__(self, api_key):
            self.chat = _FakeChat()

    import openai
    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeOpenAI)

    result = await rec_mod.generate_recommendations()

    assert len(result) == 1
    assert len(captured_payloads) == 1
    user_msg = captured_payloads[0]
    json_start = user_msg.index("{")
    payload = json.loads(user_msg[json_start:])
    assert "core_metrics_distribution" in payload
    dist = payload["core_metrics_distribution"]
    assert dist["candidates"]["keys"]["atr"]["n"] == 1


async def test_weekly_day_omits_core_metrics_key_when_strategy_has_no_data(monkeypatch):
    """momentum 류 — llm_context 가 항상 빈 dict → 분포 키 자체가 payload 에 없다."""
    from src.engine import recommendation_engine as rec_mod

    strat = _fake_strategy("momentum", scanned=["005930"], llm_ctx={})
    _wire_registry(monkeypatch, [strat])
    _wire_common(monkeypatch, rec_mod)
    _wire_weekly_gate(monkeypatch, run=True)

    captured_payloads: list[dict] = []

    async def fake_call_openai(**kwargs):
        captured_payloads.append(kwargs)
        return {}

    monkeypatch.setattr(rec_mod, "_call_openai", fake_call_openai)

    await rec_mod.generate_recommendations()

    assert len(captured_payloads) == 1
    assert captured_payloads[0]["core_metrics"] == {
        "candidates": {"n_tickers": 1, "n_with_context": 0, "keys": {}},
        "holdings": {"n_tickers": 0, "n_with_context": 0, "keys": {}},
    }


async def test_non_advisory_day_never_computes_core_metrics(monkeypatch):
    """비-목요일(주간 자문일 아님) — 게이트가 루프 자체를 막아 수집기 호출이 0회다."""
    from src.engine import recommendation_engine as rec_mod
    from src.engine import strategy_core_metrics as scm

    strat = _fake_strategy("donchian_swing", scanned=["005930"], llm_ctx={"005930": {"atr": 1.0}})
    _wire_registry(monkeypatch, [strat])
    _wire_common(monkeypatch, rec_mod)
    _wire_weekly_gate(monkeypatch, run=False)

    calls: list = []

    def _tracking_collect(strategy):
        calls.append(strategy)
        raise AssertionError("주간 자문일이 아닌데 core metrics 를 계산했다")

    monkeypatch.setattr(scm, "collect_strategy_core_metrics", _tracking_collect)
    monkeypatch.setattr(rec_mod.strategy_core_metrics, "collect_strategy_core_metrics", _tracking_collect)

    result = await rec_mod.generate_recommendations()

    assert result == []
    assert calls == [], "비-목요일에 core metrics 수집기가 호출됐다"
