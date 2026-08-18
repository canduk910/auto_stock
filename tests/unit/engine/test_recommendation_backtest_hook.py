"""Phase 3 Red — recommendation_engine 의 백테스트 enqueue 훅.

요구 행위:

generate_recommendations() 마지막 단계에서 ``_enqueue_backtest_jobs(target_date, inserted)``
를 호출해야 한다. 동기 await — INSERT 끝난 직후 호출.

``_enqueue_backtest_jobs`` 자체 책임:
- (a) 외부 YAML 지원 전략(momentum, volatility_breakout, donchian_swing) 각 2 kind
       → backtest_runs INSERT (status=queued) → BacktestEngine.run_for_strategy 호출
       → mcp_job_id 부여 + status=running 전이.
- (b) 폴백 전략(long_tail_volatility, bull_flag_breakout, vcp_breakout) 은
       INSERT 직후 즉시 ``status='skipped'`` + ``error_message='YAML DSL 미지원 (Phase 4-bis 대기)'``.
- KIS_MCP_ENABLED=false 시 (a) 도 즉시 ``status='skipped'`` + ``error_message='MCP 비활성'``.
- BacktestEngine 호출 실패 시 자문 INSERT 보존(이미 끝난 상태), 해당 row 만 ``status='failed'``.
- ``asyncio.create_task`` 로 ``_backtest_poll_loop(target_date)`` 발화 (fire-and-forget) —
  단, MCP 비활성 또는 enqueue 결과 (a) 0건이면 발화 안 함.

테스트 더블:
- backtest_runs 와 BacktestEngine 둘 다 monkeypatch.
- recommendations 인자 ``inserted`` 는 ``[{"strategy_id": ..., "current_params": ..., "recommended_params": ...}, ...]`` 형식.
"""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼: enqueue 테스트용 fake registry + 6 전략 stub
# ---------------------------------------------------------------------------
def _fake_strategy(strategy_id: str, params: dict | None = None):
    return SimpleNamespace(
        strategy_id=strategy_id,
        config=SimpleNamespace(
            name=strategy_id,
            weight=0.2,
            params=dict(params or {}),
        ),
        state=SimpleNamespace(),
    )


SIX_STRATEGIES = [
    "momentum",
    "volatility_breakout",
    "donchian_swing",
    "long_tail_volatility",
    "bull_flag_breakout",
    "vcp_breakout",
]


def _make_inserted_rows(target_date: date) -> list[dict]:
    """generate_recommendations() 가 _enqueue_backtest_jobs 로 넘기는 페이로드."""
    rows = []
    for sid in SIX_STRATEGIES:
        rows.append({
            "id": f"rec-{sid}",
            "target_date": target_date.isoformat(),
            "strategy_id": sid,
            "current_params": {"buy_threshold": 29.0},
            "recommended_params": {"buy_threshold": 27.0},
        })
    return rows


# ---------------------------------------------------------------------------
# A: generate_recommendations 가 INSERT 후 enqueue 호출하는지
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_recommendations_calls_enqueue_after_insert(
    monkeypatch: pytest.MonkeyPatch,
):
    """A: 자문 INSERT 가 모두 끝난 후 _enqueue_backtest_jobs 호출."""
    from src.engine import recommendation_engine as rec_mod

    target = date(2026, 5, 16)

    # ---- registry 모킹: 6 전략 enabled ----
    from src.engine.scheduler import trading_scheduler
    fake_registry = SimpleNamespace(
        enabled=lambda: [_fake_strategy(s) for s in SIX_STRATEGIES],
    )
    monkeypatch.setattr(trading_scheduler, "registry", fake_registry)

    # ---- settings.openai_api_key 가 truthy 여야 본체 진입 ----
    from src.config import settings
    monkeypatch.setattr(settings, "openai_api_key", "test-key", raising=False)

    # ---- 의존 DB / OpenAI 호출 무력화 ----
    async def fake_expire(_target):
        return 0

    async def fake_get_trades_in_range(*args, **kwargs):
        return []

    async def fake_get_performance(*args, **kwargs):
        return []

    def fake_compute_metrics(*args, **kwargs):
        return {}

    async def fake_call_openai(*args, **kwargs):
        return {"recommended_params": {"buy_threshold": 27.0}, "reasoning": "x"}

    async def fake_insert_recommendation(**kwargs):
        return {
            "id": f"rec-{kwargs['strategy_id']}",
            "target_date": kwargs["target_date"].isoformat(),
            "strategy_id": kwargs["strategy_id"],
            "current_params": kwargs["current_params"],
            "recommended_params": kwargs["recommended_params"],
        }

    monkeypatch.setattr(rec_mod, "expire_pending_before", fake_expire)
    monkeypatch.setattr(rec_mod, "get_trades_in_range", fake_get_trades_in_range)
    monkeypatch.setattr(rec_mod, "get_performance", fake_get_performance)
    monkeypatch.setattr(rec_mod, "compute_metrics", fake_compute_metrics)
    monkeypatch.setattr(rec_mod, "_call_openai", fake_call_openai)
    monkeypatch.setattr(rec_mod, "insert_recommendation", fake_insert_recommendation)

    # ---- _enqueue_backtest_jobs 추적 ----
    calls: list[dict] = []

    async def fake_enqueue(td, recs):
        calls.append({"target_date": td, "recs": list(recs)})

    monkeypatch.setattr(rec_mod, "_enqueue_backtest_jobs", fake_enqueue)

    # freezegun 으로 target_date 고정 (KST 20:00 = UTC 11:00, KST date=2026-05-16)
    from freezegun import freeze_time
    with freeze_time("2026-05-16 11:00:00"):
        inserted = await rec_mod.generate_recommendations()

    assert len(inserted) == 6
    assert len(calls) == 1, "enqueue 가 정확히 1회 호출되어야 한다"
    assert calls[0]["target_date"] == target
    # 전달된 recs 는 inserted 리스트 (혹은 적어도 6개 strategy 가 포함)
    rec_sids = {r["strategy_id"] for r in calls[0]["recs"]}
    assert rec_sids == set(SIX_STRATEGIES)


# ---------------------------------------------------------------------------
# B: _enqueue_backtest_jobs 가 6 전략 × 2 kind = 12 row INSERT
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_inserts_twelve_rows(
    monkeypatch: pytest.MonkeyPatch,
):
    """B: 6 전략 × {current, recommended} = 12 row 가 backtest_runs 에 INSERT."""
    from src.engine import recommendation_engine as rec_mod
    from src.engine import backtest_orchestration as _bt

    target = date(2026, 5, 16)
    recs = _make_inserted_rows(target)

    inserted_rows: list[dict] = []

    async def fake_insert_run(target_date, strategy_id, params_kind, params_snapshot):
        row = {
            "id": f"run-{strategy_id}-{params_kind}",
            "target_date": target_date.isoformat(),
            "strategy_id": strategy_id,
            "params_kind": params_kind,
            "params_snapshot": dict(params_snapshot),
            "status": "queued",
        }
        inserted_rows.append(row)
        return row

    async def fake_update_status(run_id, status, **kwargs):
        return {"id": run_id, "status": status, **kwargs}

    monkeypatch.setattr(_bt, "_db_insert_run", fake_insert_run, raising=False)
    monkeypatch.setattr(_bt, "_db_update_status", fake_update_status, raising=False)

    # ---- BacktestEngine: (a) 3 전략은 정상 submit, (b) 3 전략은 BacktestNotSupportedError ----
    from src.services.exceptions import BacktestNotSupportedError

    submit_calls: list[dict] = []

    class FakeEngine:
        enabled = True

        async def is_enabled_async(self):
            return self.enabled

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            submit_calls.append({"strategy_id": strategy_id, "kind": kind, "params": dict(params)})
            if strategy_id in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout"):
                raise BacktestNotSupportedError(f"{strategy_id} unsupported")
            return f"job-{strategy_id}-{kind}"

    monkeypatch.setattr(_bt, "_get_backtest_engine", lambda: FakeEngine(), raising=False)

    # ---- poll loop 발화 차단(테스트는 enqueue 만 검증) ----
    monkeypatch.setattr(_bt, "_spawn_backtest_poll_task", lambda td: None, raising=False)

    await rec_mod._enqueue_backtest_jobs(target, recs)

    # 12 row INSERT
    assert len(inserted_rows) == 12
    kinds = {(r["strategy_id"], r["params_kind"]) for r in inserted_rows}
    assert kinds == {
        (s, k) for s in SIX_STRATEGIES for k in ("current", "recommended")
    }


# ---------------------------------------------------------------------------
# C: (b) 폴백 전략 3종은 즉시 skipped 마킹
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_skips_fallback_strategies(
    monkeypatch: pytest.MonkeyPatch,
):
    """C: (b) 폴백 전략은 BacktestEngine 호출 없이 status='skipped' + 사유 영속화."""
    from src.engine import recommendation_engine as rec_mod
    from src.engine import backtest_orchestration as _bt
    from src.services.exceptions import BacktestNotSupportedError

    target = date(2026, 5, 16)
    recs = _make_inserted_rows(target)

    insert_records: list[dict] = []
    update_records: list[dict] = []

    async def fake_insert_run(target_date, strategy_id, params_kind, params_snapshot):
        row = {
            "id": f"run-{strategy_id}-{params_kind}",
            "strategy_id": strategy_id,
            "params_kind": params_kind,
            "status": "queued",
        }
        insert_records.append(row)
        return row

    async def fake_update_status(run_id, status, **kwargs):
        update_records.append({"run_id": run_id, "status": status, **kwargs})
        return {"id": run_id, "status": status}

    monkeypatch.setattr(_bt, "_db_insert_run", fake_insert_run, raising=False)
    monkeypatch.setattr(_bt, "_db_update_status", fake_update_status, raising=False)

    submit_calls: list[str] = []

    class FakeEngine:
        enabled = True

        async def is_enabled_async(self):
            return self.enabled

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            submit_calls.append(strategy_id)
            if strategy_id in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout"):
                raise BacktestNotSupportedError(f"{strategy_id} unsupported")
            return f"job-{strategy_id}-{kind}"

    monkeypatch.setattr(_bt, "_get_backtest_engine", lambda: FakeEngine(), raising=False)
    monkeypatch.setattr(_bt, "_spawn_backtest_poll_task", lambda td: None, raising=False)

    await rec_mod._enqueue_backtest_jobs(target, recs)

    # (b) 전략 3 × 2 kind = 6 row 가 skipped 로 갱신되어야 한다
    skipped = [u for u in update_records if u["status"] == "skipped"]
    skipped_sids = {u["run_id"] for u in skipped}
    expected = {
        f"run-{s}-{k}"
        for s in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout")
        for k in ("current", "recommended")
    }
    assert skipped_sids == expected

    # skipped 에 error_message 가 포함되어야 한다 (사후 진단용)
    for u in skipped:
        assert u.get("error_message"), f"skipped row 에 error_message 필수: {u}"
        assert "YAML" in u["error_message"] or "지원" in u["error_message"]


# ---------------------------------------------------------------------------
# D: (a) 전략 3종은 BacktestEngine.run_for_strategy 호출 → status=running 전이
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_submits_supported_strategies(
    monkeypatch: pytest.MonkeyPatch,
):
    """D: (a) 전략은 BacktestEngine submit → mcp_job_id 매핑 → status='running'."""
    from src.engine import recommendation_engine as rec_mod
    from src.engine import backtest_orchestration as _bt
    from src.services.exceptions import BacktestNotSupportedError

    target = date(2026, 5, 16)
    recs = _make_inserted_rows(target)

    async def fake_insert_run(target_date, strategy_id, params_kind, params_snapshot):
        return {
            "id": f"run-{strategy_id}-{params_kind}",
            "strategy_id": strategy_id,
            "params_kind": params_kind,
            "status": "queued",
        }

    update_records: list[dict] = []

    async def fake_update_status(run_id, status, **kwargs):
        update_records.append({"run_id": run_id, "status": status, **kwargs})
        return {"id": run_id, "status": status}

    monkeypatch.setattr(_bt, "_db_insert_run", fake_insert_run, raising=False)
    monkeypatch.setattr(_bt, "_db_update_status", fake_update_status, raising=False)

    class FakeEngine:
        enabled = True

        async def is_enabled_async(self):
            return self.enabled

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            if strategy_id in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout"):
                raise BacktestNotSupportedError(f"{strategy_id} unsupported")
            return f"job-{strategy_id}-{kind}"

    monkeypatch.setattr(_bt, "_get_backtest_engine", lambda: FakeEngine(), raising=False)
    monkeypatch.setattr(_bt, "_spawn_backtest_poll_task", lambda td: None, raising=False)

    await rec_mod._enqueue_backtest_jobs(target, recs)

    running = [u for u in update_records if u["status"] == "running"]
    running_ids = {u["run_id"] for u in running}
    expected = {
        f"run-{s}-{k}"
        for s in ("momentum", "volatility_breakout", "donchian_swing")
        for k in ("current", "recommended")
    }
    assert running_ids == expected
    # mcp_job_id 가 갱신 페이로드에 포함되어야 한다
    for u in running:
        assert u.get("mcp_job_id"), f"running row 에 mcp_job_id 필수: {u}"


# ---------------------------------------------------------------------------
# E: KIS_MCP_ENABLED=false 시 모든 row skipped, BacktestEngine 호출 0건
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_skips_when_mcp_disabled(
    monkeypatch: pytest.MonkeyPatch,
):
    """E: enabled=False 면 (a) 전략도 모두 skipped — 외부 호출 0."""
    from src.engine import recommendation_engine as rec_mod
    from src.engine import backtest_orchestration as _bt

    target = date(2026, 5, 16)
    recs = _make_inserted_rows(target)

    insert_count = {"n": 0}
    update_records: list[dict] = []

    async def fake_insert_run(target_date, strategy_id, params_kind, params_snapshot):
        insert_count["n"] += 1
        return {
            "id": f"run-{strategy_id}-{params_kind}",
            "strategy_id": strategy_id,
            "params_kind": params_kind,
            "status": "queued",
        }

    async def fake_update_status(run_id, status, **kwargs):
        update_records.append({"run_id": run_id, "status": status, **kwargs})
        return {"id": run_id, "status": status}

    monkeypatch.setattr(_bt, "_db_insert_run", fake_insert_run, raising=False)
    monkeypatch.setattr(_bt, "_db_update_status", fake_update_status, raising=False)

    submit_count = {"n": 0}

    class FakeEngine:
        enabled = False

        async def is_enabled_async(self):
            return self.enabled

        async def run_for_strategy(self, *args, **kwargs):
            submit_count["n"] += 1
            return "job-should-not-be-called"

    monkeypatch.setattr(_bt, "_get_backtest_engine", lambda: FakeEngine(), raising=False)

    poll_calls: list = []
    monkeypatch.setattr(
        _bt, "_spawn_backtest_poll_task", lambda td: poll_calls.append(td), raising=False
    )

    await rec_mod._enqueue_backtest_jobs(target, recs)

    # 12 row INSERT 는 그대로 (영속화 자체는 보존 — 차후 토글 시 history 조회 가능)
    assert insert_count["n"] == 12
    # 모두 skipped (그러나 사유는 서로 다름: (a) 는 'MCP 비활성', (b) 는 'YAML DSL 미지원')
    skipped = [u for u in update_records if u["status"] == "skipped"]
    assert len(skipped) == 12

    # (a) 전략 3 × 2 kind = 6 row 는 'MCP 비활성' 사유
    mcp_disabled_ids = {
        f"run-{s}-{k}"
        for s in ("momentum", "volatility_breakout", "donchian_swing")
        for k in ("current", "recommended")
    }
    mcp_disabled = [u for u in skipped if u["run_id"] in mcp_disabled_ids]
    assert len(mcp_disabled) == 6
    for u in mcp_disabled:
        assert "비활성" in u["error_message"], f"(a) 전략 skipped 사유: {u}"

    # (b) 전략 3 × 2 kind = 6 row 는 'YAML DSL 미지원' 사유
    fallback_ids = {
        f"run-{s}-{k}"
        for s in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout")
        for k in ("current", "recommended")
    }
    fallback = [u for u in skipped if u["run_id"] in fallback_ids]
    assert len(fallback) == 6
    for u in fallback:
        assert "YAML" in u["error_message"] or "지원" in u["error_message"]

    # BacktestEngine.run_for_strategy 호출 0건
    assert submit_count["n"] == 0
    # poll loop 발화 안 함 (skipped 만 있는 상황)
    assert poll_calls == []


# ---------------------------------------------------------------------------
# F: 외부 서버 ExternalAPIError → 자문 INSERT 보존 + 해당 row 만 failed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_handles_external_api_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """F: BacktestEngine.run_for_strategy 가 ExternalAPIError 던지면 해당 row 만 failed."""
    from src.engine import recommendation_engine as rec_mod
    from src.engine import backtest_orchestration as _bt
    from src.services.exceptions import BacktestNotSupportedError, ExternalAPIError

    target = date(2026, 5, 16)
    recs = _make_inserted_rows(target)

    async def fake_insert_run(target_date, strategy_id, params_kind, params_snapshot):
        return {
            "id": f"run-{strategy_id}-{params_kind}",
            "strategy_id": strategy_id,
            "params_kind": params_kind,
            "status": "queued",
        }

    update_records: list[dict] = []

    async def fake_update_status(run_id, status, **kwargs):
        update_records.append({"run_id": run_id, "status": status, **kwargs})
        return {"id": run_id, "status": status}

    monkeypatch.setattr(_bt, "_db_insert_run", fake_insert_run, raising=False)
    monkeypatch.setattr(_bt, "_db_update_status", fake_update_status, raising=False)

    class FakeEngine:
        enabled = True

        async def is_enabled_async(self):
            return self.enabled

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            if strategy_id == "momentum":
                raise ExternalAPIError("MCP 통신 단절")
            if strategy_id in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout"):
                raise BacktestNotSupportedError(f"{strategy_id} unsupported")
            return f"job-{strategy_id}-{kind}"

    monkeypatch.setattr(_bt, "_get_backtest_engine", lambda: FakeEngine(), raising=False)
    monkeypatch.setattr(_bt, "_spawn_backtest_poll_task", lambda td: None, raising=False)

    await rec_mod._enqueue_backtest_jobs(target, recs)

    # momentum 2 row 만 failed
    failed = [u for u in update_records if u["status"] == "failed"]
    failed_ids = {u["run_id"] for u in failed}
    assert failed_ids == {"run-momentum-current", "run-momentum-recommended"}
    for u in failed:
        assert "단절" in u.get("error_message", "") or "MCP" in u.get("error_message", "")

    # volatility_breakout / donchian_swing 은 정상 running
    running = [u for u in update_records if u["status"] == "running"]
    running_ids = {u["run_id"] for u in running}
    assert running_ids == {
        "run-volatility_breakout-current",
        "run-volatility_breakout-recommended",
        "run-donchian_swing-current",
        "run-donchian_swing-recommended",
    }
