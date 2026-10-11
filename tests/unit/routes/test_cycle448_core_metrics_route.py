"""cycle448 — `GET /api/strategies/core-metrics` (전략별 핵심값 분포, 사용자 결정 2026-10-11).

목요일 20:30 주간 Claude 루틴이 이 GET 으로 자문 보강 재료를 읽는다. 등록 전략 전부
(`registry.all()`)에 대해 `engine/strategy_core_metrics.collect_strategy_core_metrics` 를
그 자리에서 계산해 돌려준다.

검증 패턴: TestClient 지양, 라우트 함수 직접 await(`test_cycleF_te_endpoint.py` 와 동일 —
anyio portal hang 회피).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def _fake_strategy(strategy_id: str, *, llm_ctx=None, scanned=(), positions=None):
    llm_ctx = llm_ctx or {}

    def _llm_context(ticker):
        return dict(llm_ctx.get(ticker, {}))

    return SimpleNamespace(
        strategy_id=strategy_id,
        get_scanned_tickers=lambda: list(scanned),
        llm_context=_llm_context,
        state=SimpleNamespace(positions=positions or {}),
    )


def _wire_registry(monkeypatch, strategies):
    from src.routes import strategies as st

    fake_registry = SimpleNamespace(all=lambda: list(strategies))
    monkeypatch.setattr(st.trading_scheduler, "registry", fake_registry)


async def test_returns_one_entry_per_registered_strategy(monkeypatch):
    from src.routes import strategies as st

    strat_a = _fake_strategy("donchian_swing", scanned=["005930"], llm_ctx={"005930": {"atr": 100.0}})
    strat_b = _fake_strategy("kojiro", scanned=["000660"], llm_ctx={"000660": {"stage": 3}})
    _wire_registry(monkeypatch, [strat_a, strat_b])

    resp = await st.get_strategies_core_metrics()

    assert resp.success is True
    assert set(resp.data["strategies"]) == {"donchian_swing", "kojiro"}
    assert "generated_at" in resp.data
    assert resp.data["generated_at"].endswith("+09:00")

    d = resp.data["strategies"]["donchian_swing"]
    assert d["candidates"]["keys"]["atr"]["n"] == 1
    k = resp.data["strategies"]["kojiro"]
    assert k["candidates"]["keys"]["stage"]["n"] == 1


async def test_isolates_per_strategy_failure(monkeypatch):
    from src.routes import strategies as st

    good = _fake_strategy("donchian_swing", scanned=["005930"], llm_ctx={"005930": {"atr": 1.0}})

    class _Broken:
        strategy_id = "broken_strategy"

        def __getattr__(self, name):
            raise RuntimeError("boom")

    _wire_registry(monkeypatch, [good, _Broken()])

    resp = await st.get_strategies_core_metrics()

    assert resp.success is True
    assert set(resp.data["strategies"]) == {"donchian_swing", "broken_strategy"}
    assert resp.data["strategies"]["broken_strategy"] == {
        "candidates": {"n_tickers": 0, "n_with_context": 0, "keys": {}},
        "holdings": {"n_tickers": 0, "n_with_context": 0, "keys": {}},
    }


async def test_empty_registry_returns_empty_strategies_dict(monkeypatch):
    from src.routes import strategies as st

    _wire_registry(monkeypatch, [])

    resp = await st.get_strategies_core_metrics()

    assert resp.success is True
    assert resp.data["strategies"] == {}


async def test_includes_disabled_strategies_too(monkeypatch):
    """`registry.all()` 을 쓴다 — 꺼진·섀도 전략도 빠지지 않는다(`/te` 와 같은 축)."""
    from src.routes import strategies as st

    shadow = _fake_strategy("ndx2x_riskoff", scanned=[], llm_ctx={})
    shadow.FIXED_TICKER = "418660"
    _wire_registry(monkeypatch, [shadow])

    resp = await st.get_strategies_core_metrics()

    assert "ndx2x_riskoff" in resp.data["strategies"]
    assert resp.data["strategies"]["ndx2x_riskoff"]["candidates"]["n_tickers"] == 1
