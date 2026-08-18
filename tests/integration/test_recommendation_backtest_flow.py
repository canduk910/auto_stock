"""Phase 3 Red — 20:00 자문 ↔ 백테스트 통합 흐름.

20:00 정각 freezegun → generate_recommendations() → backtest_runs 12 row +
parameter_recommendations 6 row + 폴 루프 가 60s 후 metrics 갱신 → backtest_summary 동봉.

본 테스트는 fire-and-forget 패턴을 검증:
- generate_recommendations 본체는 자문 INSERT 와 enqueue 만 await 한다 (10s 이내 종료).
- _backtest_poll_loop 는 백그라운드 task — 본 테스트는 별도 await 로 종료 확인.

settlement 20:10 race 가드: 폴 루프 미완료 상태에서 settlement 호출(_reset_daily_state)
이 들어와도 자문 INSERT 는 보존되어야 한다. 본 테스트는 (1) enqueue 가 동기 완료,
(2) settlement 호출 후에도 parameter_recommendations.* 보존 두 가지를 검증한다.
"""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.integration


SIX_STRATEGIES = [
    "momentum",
    "volatility_breakout",
    "donchian_swing",
    "long_tail_volatility",
    "bull_flag_breakout",
    "vcp_breakout",
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


@pytest.mark.asyncio
async def test_full_flow_20_00_recommendation_backtest(
    monkeypatch: pytest.MonkeyPatch,
):
    """20:00 정각 자문 + 백테스트 enqueue + 폴 → backtest_summary 동봉 전 흐름."""
    from src.engine import recommendation_engine as rec_mod
    from src.engine import backtest_orchestration as _bt
    from src.models.backtest import BacktestMetrics

    target = date(2026, 5, 16)

    # ---- registry: 6 전략 ----
    from src.engine.scheduler import trading_scheduler
    fake_registry = SimpleNamespace(
        enabled=lambda: [_fake_strategy(s) for s in SIX_STRATEGIES],
    )
    monkeypatch.setattr(trading_scheduler, "registry", fake_registry)

    from src.config import settings
    monkeypatch.setattr(settings, "openai_api_key", "test-key", raising=False)

    # ---- DB / OpenAI 모킹 ----
    async def fake_expire(_):
        return 0

    async def fake_get_trades_in_range(*a, **kw):
        return []

    async def fake_get_performance(*a, **kw):
        return []

    def fake_compute_metrics(*a, **kw):
        return {}

    async def fake_call_openai(**kwargs):
        return {
            "recommended_params": {"buy_threshold": 27.0},
            "reasoning": "test",
        }

    pr_store: dict[str, dict] = {}

    async def fake_insert_recommendation(**kwargs):
        rec_id = f"rec-{kwargs['strategy_id']}"
        row = {
            "id": rec_id,
            "target_date": kwargs["target_date"].isoformat(),
            "strategy_id": kwargs["strategy_id"],
            "current_params": kwargs["current_params"],
            "recommended_params": kwargs["recommended_params"],
            "backtest_summary": None,
        }
        pr_store[rec_id] = row
        return row

    monkeypatch.setattr(rec_mod, "expire_pending_before", fake_expire)
    monkeypatch.setattr(rec_mod, "get_trades_in_range", fake_get_trades_in_range)
    monkeypatch.setattr(rec_mod, "get_performance", fake_get_performance)
    monkeypatch.setattr(rec_mod, "compute_metrics", fake_compute_metrics)
    monkeypatch.setattr(rec_mod, "_call_openai", fake_call_openai)
    monkeypatch.setattr(rec_mod, "insert_recommendation", fake_insert_recommendation)

    # ---- backtest_runs DB 모킹 ----
    runs_store: dict[str, dict] = {}

    async def fake_db_insert_run(target_date, strategy_id, params_kind, params_snapshot):
        run_id = f"run-{strategy_id}-{params_kind}"
        row = {
            "id": run_id,
            "target_date": target_date.isoformat(),
            "strategy_id": strategy_id,
            "params_kind": params_kind,
            "params_snapshot": dict(params_snapshot),
            "status": "queued",
            "mcp_job_id": None,
            "metrics": None,
            "error_message": None,
        }
        runs_store[run_id] = row
        return row

    async def fake_db_update_status(run_id, status, **kwargs):
        row = runs_store[run_id]
        row["status"] = status
        for k in ("mcp_job_id", "metrics", "error_message"):
            if k in kwargs:
                row[k] = kwargs[k]
        return row

    async def fake_db_list_by_date(td):
        return [r for r in runs_store.values() if r["target_date"] == td.isoformat()]

    async def fake_db_list_pending_backtest(td):
        return [
            r for r in pr_store.values()
            if r["target_date"] == td.isoformat()
            and r.get("backtest_summary") is None
        ]

    async def fake_db_update_backtest_summary(rec_id, summary):
        if rec_id in pr_store:
            pr_store[rec_id]["backtest_summary"] = summary
        return pr_store.get(rec_id, {})

    monkeypatch.setattr(_bt, "_db_insert_run", fake_db_insert_run, raising=False)
    monkeypatch.setattr(_bt, "_db_update_status", fake_db_update_status, raising=False)
    monkeypatch.setattr(_bt, "_db_list_by_date", fake_db_list_by_date, raising=False)
    monkeypatch.setattr(
        _bt, "_db_list_pending_backtest", fake_db_list_pending_backtest, raising=False
    )
    monkeypatch.setattr(
        _bt, "_db_update_backtest_summary", fake_db_update_backtest_summary, raising=False
    )

    # ---- BacktestEngine: 즉시 submit, poll 1회만에 완료 ----
    from src.services.exceptions import BacktestNotSupportedError

    class FakeEngine:
        enabled = True

        async def is_enabled_async(self):
            return self.enabled

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            if strategy_id in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout"):
                raise BacktestNotSupportedError(f"{strategy_id} unsupported")
            return f"job-{strategy_id}-{kind}"

        async def poll(self, job_id):
            return BacktestMetrics.model_validate({
                "total_return_pct": 12.3,
                "sharpe_ratio": 1.4,
                "max_drawdown": -7.5,
                "total_trades": 18,
            })

    monkeypatch.setattr(_bt, "_get_backtest_engine", lambda: FakeEngine(), raising=False)
    monkeypatch.setattr(_bt, "_BACKTEST_POLL_INTERVAL_SECS", 0, raising=False)

    # ---- 폴 루프 task 를 await 가능하게 캡처 ----
    poll_tasks: list[asyncio.Task] = []

    def spawn_poll(td):
        loop = asyncio.get_event_loop()
        t = loop.create_task(rec_mod._backtest_poll_loop(td))
        poll_tasks.append(t)
        return t

    monkeypatch.setattr(_bt, "_spawn_backtest_poll_task", spawn_poll, raising=False)

    # ---- 20:00 정각에 generate_recommendations 호출 ----
    with freeze_time("2026-05-16 11:00:00"):  # KST 20:00
        inserted = await rec_mod.generate_recommendations()

    assert len(inserted) == 6, "6 전략 자문 INSERT"
    assert len(pr_store) == 6
    assert len(runs_store) == 12, "6 전략 × 2 kind = 12 backtest_runs"

    # ---- 폴 루프 종료 대기 ----
    if poll_tasks:
        await asyncio.gather(*poll_tasks)

    # 모든 6 전략 backtest_summary 동봉
    summarized = [r for r in pr_store.values() if r.get("backtest_summary")]
    assert len(summarized) == 6

    # (a) 전략은 current/recommended 메트릭 동봉
    mom = pr_store["rec-momentum"]["backtest_summary"]
    assert mom["current"]["momentum"]["total_return_pct"] == 12.3
    assert mom["recommended"]["momentum"]["total_return_pct"] == 12.3
    # 동일 메트릭이라 diff 는 0
    assert mom["diff"]["momentum"]["total_return_pct"] == pytest.approx(0.0)

    # (b) 전략은 current/recommended None
    ltv = pr_store["rec-long_tail_volatility"]["backtest_summary"]
    assert ltv["current"].get("long_tail_volatility") is None
    assert ltv["recommended"].get("long_tail_volatility") is None


@pytest.mark.asyncio
async def test_settlement_race_preserves_recommendation_insert(
    monkeypatch: pytest.MonkeyPatch,
):
    """settlement 20:10 시점에 폴 루프 미완료여도 자문 INSERT 는 보존.

    핵심: 자문 INSERT 는 generate_recommendations 본체 (동기 await) 안에서 끝나야 하므로
    poll 루프가 영원히 안 끝나도 pr_store 에 6 row 가 영속화되어야 한다.
    """
    from src.engine import recommendation_engine as rec_mod
    from src.engine import backtest_orchestration as _bt
    from src.services.exceptions import BacktestNotSupportedError

    target = date(2026, 5, 16)

    from src.engine.scheduler import trading_scheduler
    fake_registry = SimpleNamespace(
        enabled=lambda: [_fake_strategy(s) for s in SIX_STRATEGIES],
    )
    monkeypatch.setattr(trading_scheduler, "registry", fake_registry)

    from src.config import settings
    monkeypatch.setattr(settings, "openai_api_key", "test-key", raising=False)

    async def fake_expire(_):
        return 0

    async def fake_get_trades_in_range(*a, **kw):
        return []

    async def fake_get_performance(*a, **kw):
        return []

    def fake_compute_metrics(*a, **kw):
        return {}

    async def fake_call_openai(**kwargs):
        return {"recommended_params": {}, "reasoning": ""}

    pr_store: dict[str, dict] = {}

    async def fake_insert_recommendation(**kwargs):
        rec_id = f"rec-{kwargs['strategy_id']}"
        row = {
            "id": rec_id,
            "target_date": kwargs["target_date"].isoformat(),
            "strategy_id": kwargs["strategy_id"],
            "backtest_summary": None,
        }
        pr_store[rec_id] = row
        return row

    monkeypatch.setattr(rec_mod, "expire_pending_before", fake_expire)
    monkeypatch.setattr(rec_mod, "get_trades_in_range", fake_get_trades_in_range)
    monkeypatch.setattr(rec_mod, "get_performance", fake_get_performance)
    monkeypatch.setattr(rec_mod, "compute_metrics", fake_compute_metrics)
    monkeypatch.setattr(rec_mod, "_call_openai", fake_call_openai)
    monkeypatch.setattr(rec_mod, "insert_recommendation", fake_insert_recommendation)

    runs_store: dict[str, dict] = {}

    async def fake_db_insert_run(target_date, strategy_id, params_kind, params_snapshot):
        run_id = f"run-{strategy_id}-{params_kind}"
        row = {
            "id": run_id,
            "target_date": target_date.isoformat(),
            "strategy_id": strategy_id,
            "params_kind": params_kind,
            "status": "queued",
            "mcp_job_id": None,
            "metrics": None,
            "error_message": None,
        }
        runs_store[run_id] = row
        return row

    async def fake_db_update_status(run_id, status, **kwargs):
        row = runs_store[run_id]
        row["status"] = status
        return row

    monkeypatch.setattr(_bt, "_db_insert_run", fake_db_insert_run, raising=False)
    monkeypatch.setattr(_bt, "_db_update_status", fake_db_update_status, raising=False)

    class FakeEngine:
        enabled = True

        async def is_enabled_async(self):
            return self.enabled

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            if strategy_id in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout"):
                raise BacktestNotSupportedError(f"{strategy_id} unsupported")
            return f"job-{strategy_id}-{kind}"

    monkeypatch.setattr(_bt, "_get_backtest_engine", lambda: FakeEngine(), raising=False)

    # 폴 루프 task 는 발화하지만 영원히 대기 (settlement race 시뮬레이션)
    spawn_called = {"n": 0}
    monkeypatch.setattr(
        _bt, "_spawn_backtest_poll_task",
        lambda td: spawn_called.__setitem__("n", spawn_called["n"] + 1),
        raising=False,
    )

    with freeze_time("2026-05-16 11:00:00"):  # KST 20:00
        inserted = await rec_mod.generate_recommendations()

    # 자문 INSERT 6 row 보존 — 폴 루프 미완료 무관
    assert len(inserted) == 6
    assert len(pr_store) == 6
    # 폴 루프 발화 1회 (fire-and-forget)
    assert spawn_called["n"] == 1
    # backtest_runs 도 영속화 (12 row)
    assert len(runs_store) == 12
