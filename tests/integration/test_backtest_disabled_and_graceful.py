"""Phase 5 회귀 가드 — graceful degrade 통합 시나리오.

Phase 3 본 흐름 테스트(`test_recommendation_backtest_flow.py`) 는 (a) 전략 정상 path
를 검증한다. 본 모듈은 **운영 활성화 전 graceful 경로** 를 통합 회귀로 영구화한다:

1. ``test_kis_mcp_disabled_marks_all_runs_skipped``
   - ``KIS_MCP_ENABLED=false`` 재시작 시나리오. 6 전략 자문 INSERT 는 그대로 발생하고,
     12 backtest_runs 모두 status=skipped, error_message 가 비활성 사유. 폴 루프 task
     발화 없음. ``BacktestComparisonCard`` 가 (b) 폴백 라벨로 자연 노출되는지 unit 가
     이미 보장 — 본 가드는 백엔드 데이터 계약만 검증.

2. ``test_external_server_down_marks_recommended_runs_failed_recommendation_preserved``
   - 외부 MCP 서버 다운(``ExternalAPIError``) 시나리오. (a) 전략 submit 단계에서
     ``ExternalAPIError`` raise → status=failed + error_message. 자문 INSERT 6 row 는 보존,
     폴 루프는 발화 후 즉시 종료(미완료 running 0). 운영자 가시성 확보용 영구 가드.

Phase 5b 사용자 검증은 ``docs/backtest-monitoring.md`` 의 단계별 진단 절차를 따른다.
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


def _common_recommendation_mocks(monkeypatch: pytest.MonkeyPatch):
    """recommendation_engine 공통 모킹 — DB / OpenAI / registry."""
    from src.engine import recommendation_engine as rec_mod
    from src.engine.scheduler import trading_scheduler
    from src.config import settings

    fake_registry = SimpleNamespace(
        enabled=lambda: [_fake_strategy(s) for s in SIX_STRATEGIES],
    )
    monkeypatch.setattr(trading_scheduler, "registry", fake_registry)
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
        return {"recommended_params": {"buy_threshold": 27.0}, "reasoning": "t"}

    monkeypatch.setattr(rec_mod, "expire_pending_before", fake_expire)
    monkeypatch.setattr(rec_mod, "get_trades_in_range", fake_get_trades_in_range)
    monkeypatch.setattr(rec_mod, "get_performance", fake_get_performance)
    monkeypatch.setattr(rec_mod, "compute_metrics", fake_compute_metrics)
    monkeypatch.setattr(rec_mod, "_call_openai", fake_call_openai)

    pr_store: dict[str, dict] = {}

    async def fake_insert_recommendation(**kwargs):
        rec_id = f"rec-{kwargs['strategy_id']}"
        row = {
            "id": rec_id,
            "target_date": kwargs["target_date"].isoformat(),
            "strategy_id": kwargs["strategy_id"],
            "current_params": kwargs.get("current_params") or {},
            "recommended_params": kwargs.get("recommended_params") or {},
            "backtest_summary": None,
        }
        pr_store[rec_id] = row
        return row

    monkeypatch.setattr(rec_mod, "insert_recommendation", fake_insert_recommendation)
    return pr_store


def _bind_backtest_runs_store(monkeypatch: pytest.MonkeyPatch):
    """backtest_runs CRUD 모킹 — in-memory store 반환."""
    from src.engine import recommendation_engine as rec_mod

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
        if run_id not in runs_store:
            return None
        row = runs_store[run_id]
        row["status"] = status
        for k in ("mcp_job_id", "metrics", "error_message"):
            if k in kwargs:
                row[k] = kwargs[k]
        return row

    async def fake_db_list_by_date(td):
        return [r for r in runs_store.values() if r["target_date"] == td.isoformat()]

    monkeypatch.setattr(rec_mod, "_db_insert_run", fake_db_insert_run, raising=False)
    monkeypatch.setattr(rec_mod, "_db_update_status", fake_db_update_status, raising=False)
    monkeypatch.setattr(rec_mod, "_db_list_by_date", fake_db_list_by_date, raising=False)
    return runs_store


@pytest.mark.asyncio
async def test_kis_mcp_disabled_marks_all_runs_skipped(
    monkeypatch: pytest.MonkeyPatch,
):
    """KIS_MCP_ENABLED=false 시나리오 — 6 자문 INSERT + 12 runs 모두 skipped.

    운영 활성화 전(2026-05-18 이전) 디폴트 상태 = enabled False.
    이 상태에서 20:00 자문 사이클이 발화해도:
    - parameter_recommendations: 6 row INSERT 성공
    - backtest_runs: 12 row INSERT 후 모두 status=skipped
    - (a) 전략(momentum/VB/donchian) 사유는 'MCP 비활성'
    - (b) 전략(LTV/bull_flag/vcp) 사유는 'YAML DSL 미지원'
    - 폴 루프 task 발화 0회 (submit_success=0)

    Phase 5b 후 사용자가 .env 토글 → 다음 영업일부터 자연 활성화.
    """
    from src.engine import recommendation_engine as rec_mod

    pr_store = _common_recommendation_mocks(monkeypatch)
    runs_store = _bind_backtest_runs_store(monkeypatch)

    # BacktestEngine.enabled=False — KIS_MCP_ENABLED=false 시뮬레이션
    class DisabledEngine:
        enabled = False

        async def is_enabled_async(self):
            return self.enabled

        async def run_for_strategy(self, *a, **kw):
            raise AssertionError("disabled engine 은 호출되면 안 됨")

        async def poll(self, *a, **kw):
            raise AssertionError("disabled engine poll 호출 금지")

    monkeypatch.setattr(rec_mod, "_get_backtest_engine", lambda: DisabledEngine(), raising=False)

    spawn_called = {"n": 0}
    monkeypatch.setattr(
        rec_mod, "_spawn_backtest_poll_task",
        lambda td: spawn_called.__setitem__("n", spawn_called["n"] + 1),
        raising=False,
    )

    with freeze_time("2026-05-18 11:00:00"):  # KST 20:00
        inserted = await rec_mod.generate_recommendations()

    # 자문 INSERT 6 row 보존 (운영 영향 0)
    assert len(inserted) == 6
    assert len(pr_store) == 6

    # backtest_runs 12 row 모두 skipped
    assert len(runs_store) == 12
    statuses = {r["status"] for r in runs_store.values()}
    assert statuses == {"skipped"}, f"모든 row skipped 기대, 실제: {statuses}"

    # 사유 분포 확인 — (a) 는 MCP 비활성 / (b) 는 YAML DSL 미지원
    a_strategies = {"momentum", "volatility_breakout", "donchian_swing"}
    b_strategies = {"long_tail_volatility", "bull_flag_breakout", "vcp_breakout"}

    a_msgs = [
        r["error_message"] for r in runs_store.values()
        if r["strategy_id"] in a_strategies
    ]
    b_msgs = [
        r["error_message"] for r in runs_store.values()
        if r["strategy_id"] in b_strategies
    ]

    assert len(a_msgs) == 6  # 3 strategies × 2 kind
    assert len(b_msgs) == 6
    assert all("MCP 비활성" in m for m in a_msgs), a_msgs
    assert all("YAML DSL 미지원" in m for m in b_msgs), b_msgs

    # 폴 루프 task 발화 0회 (submit_success=0 → spawn skip)
    assert spawn_called["n"] == 0, "submit 0건이면 폴 루프 발화 금지"


@pytest.mark.asyncio
async def test_external_server_down_marks_runs_failed_recommendation_preserved(
    monkeypatch: pytest.MonkeyPatch,
):
    """외부 MCP 서버 다운 시나리오 — (a) submit 실패 → failed, 자문 INSERT 보존.

    KIS_MCP_ENABLED=true 인데 외부 서버가 다운된 상황:
    - parameter_recommendations: 6 row INSERT 보존
    - backtest_runs (a) 전략: ExternalAPIError → status=failed, error_message 포함
    - backtest_runs (b) 전략: 기존 skipped
    - 자문 INSERT 와 백테스트 enqueue 는 try/except 로 분리 — 자문은 graceful

    운영자가 ``backtest_runs.status=failed`` 행을 SQL 로 확인해 외부 서버 문제 진단.
    """
    from src.engine import recommendation_engine as rec_mod
    from src.services.exceptions import ExternalAPIError, BacktestNotSupportedError

    pr_store = _common_recommendation_mocks(monkeypatch)
    runs_store = _bind_backtest_runs_store(monkeypatch)

    class DownEngine:
        """enabled=True 지만 모든 호출에 ExternalAPIError raise — 서버 다운."""
        enabled = True

        async def is_enabled_async(self):
            return self.enabled

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            if strategy_id in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout"):
                raise BacktestNotSupportedError(f"{strategy_id} unsupported")
            raise ExternalAPIError(
                f"MCP 서버 다운 (Connection refused) — strategy={strategy_id} kind={kind}"
            )

        async def poll(self, *a, **kw):
            raise ExternalAPIError("MCP 서버 다운")

    monkeypatch.setattr(rec_mod, "_get_backtest_engine", lambda: DownEngine(), raising=False)

    spawn_called = {"n": 0}
    monkeypatch.setattr(
        rec_mod, "_spawn_backtest_poll_task",
        lambda td: spawn_called.__setitem__("n", spawn_called["n"] + 1),
        raising=False,
    )

    with freeze_time("2026-05-18 11:00:00"):
        inserted = await rec_mod.generate_recommendations()

    # 자문 INSERT 보존 — graceful degrade 원칙
    assert len(inserted) == 6, "외부 서버 다운에도 자문 INSERT 는 그대로"
    assert len(pr_store) == 6

    # 12 backtest_runs INSERT 됨
    assert len(runs_store) == 12

    # (a) 전략 6 row 모두 failed
    a_rows = [
        r for r in runs_store.values()
        if r["strategy_id"] in ("momentum", "volatility_breakout", "donchian_swing")
    ]
    assert len(a_rows) == 6
    assert all(r["status"] == "failed" for r in a_rows), [
        (r["strategy_id"], r["params_kind"], r["status"]) for r in a_rows
    ]
    assert all("ExternalAPIError" in (r["error_message"] or "") for r in a_rows)

    # (b) 전략 6 row 는 기존대로 skipped (Phase 4-bis 대기)
    b_rows = [
        r for r in runs_store.values()
        if r["strategy_id"] in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout")
    ]
    assert len(b_rows) == 6
    assert all(r["status"] == "skipped" for r in b_rows)
    assert all("YAML DSL 미지원" in (r["error_message"] or "") for r in b_rows)

    # 폴 루프 발화 0회 — submit_success=0
    assert spawn_called["n"] == 0, "모든 submit 실패면 폴 루프 발화 skip"


@pytest.mark.asyncio
async def test_backtest_poll_timeout_marks_running_rows_failed(
    monkeypatch: pytest.MonkeyPatch,
):
    """24h timeout 통합 가드 — 끝없이 running 상태인 row 가 timeout 후 failed.

    Phase 3 unit D 가 timeout 로직 자체를 보장하지만, 통합 흐름에서:
    - 자문 INSERT → enqueue → submit 성공(running 전이) → 폴 루프가 영원히 None 반환
    - 24h 경과 timeout → status=failed (error_message "Timeout")
    - 자문 INSERT 6 row 는 영속 보존
    """
    from src.engine import recommendation_engine as rec_mod
    from src.services.exceptions import BacktestNotSupportedError
    from src.models.backtest import BacktestMetrics

    pr_store = _common_recommendation_mocks(monkeypatch)
    runs_store = _bind_backtest_runs_store(monkeypatch)

    pending_summary_calls = {"n": 0}

    async def fake_list_pending_backtest(td):
        return []

    async def fake_update_backtest_summary(rec_id, summary):
        pending_summary_calls["n"] += 1
        if rec_id in pr_store:
            pr_store[rec_id]["backtest_summary"] = summary
        return pr_store.get(rec_id, {})

    monkeypatch.setattr(
        rec_mod, "_db_list_pending_backtest", fake_list_pending_backtest, raising=False
    )
    monkeypatch.setattr(
        rec_mod, "_db_update_backtest_summary", fake_update_backtest_summary, raising=False
    )

    class HangingEngine:
        enabled = True

        async def is_enabled_async(self):
            return self.enabled

        async def run_for_strategy(self, strategy_id, params, days=90, kind="current", **kw):
            if strategy_id in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout"):
                raise BacktestNotSupportedError(f"{strategy_id} unsupported")
            return f"job-{strategy_id}-{kind}"

        async def poll(self, job_id):
            # 영원히 running 반환 — timeout 분기 진입까지 강제
            return None

    monkeypatch.setattr(rec_mod, "_get_backtest_engine", lambda: HangingEngine(), raising=False)
    # 폴 sleep 0초 — 빠른 iteration
    monkeypatch.setattr(rec_mod, "_BACKTEST_POLL_INTERVAL_SECS", 0, raising=False)
    # timeout 도 0시간 → 첫 iteration 직후 timeout 분기 진입
    monkeypatch.setattr(rec_mod, "_BACKTEST_POLL_TIMEOUT_HOURS", 0, raising=False)

    poll_tasks: list[asyncio.Task] = []

    def spawn_poll(td):
        loop = asyncio.get_event_loop()
        t = loop.create_task(rec_mod._backtest_poll_loop(td))
        poll_tasks.append(t)
        return t

    monkeypatch.setattr(rec_mod, "_spawn_backtest_poll_task", spawn_poll, raising=False)

    with freeze_time("2026-05-18 11:00:00"):
        inserted = await rec_mod.generate_recommendations()

    assert len(inserted) == 6
    if poll_tasks:
        await asyncio.gather(*poll_tasks)

    # (a) 6 row 모두 timeout 으로 failed
    a_rows = [
        r for r in runs_store.values()
        if r["strategy_id"] in ("momentum", "volatility_breakout", "donchian_swing")
    ]
    assert len(a_rows) == 6
    assert all(r["status"] == "failed" for r in a_rows), a_rows
    assert all("Timeout" in (r["error_message"] or "") for r in a_rows)

    # 자문 INSERT 6 row 보존
    assert len(pr_store) == 6
