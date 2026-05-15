"""Phase 2 Red — `src/db/backtest_runs.py` CRUD.

backtest_runs 테이블은 (target_date, strategy_id, params_kind) UNIQUE.
status: queued → running → completed (or failed).

요구 행위:

1. `insert_run(target_date, strategy_id, params_kind, params_snapshot)` → row dict 반환.
   동일 키 재시도 시 `None` 반환 (UNIQUE 충돌 → graceful).
2. `get_by_id(run_id)` — 미존재 시 None.
3. `list_by_date(target_date)` — 6 전략 × 2 kind 까지 묶어서 반환. 날짜 desc 정렬은 호출자.
4. `update_status(run_id, status, mcp_job_id=None, error_message=None, metrics=None)`
   → completed/failed 시 completed_at 자동 기록.
5. supabase 동기 SDK 호출은 모두 `asyncio.to_thread` 위임 — `src/db/CLAUDE.md` 규약.

테스트 더블:
- `src.db.backtest_runs.supabase` 를 `FakeSupabase` 로 monkeypatch.
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_insert_run_returns_inserted_row(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """A: insert_run 정상 — row dict 반환 + store 에 기록."""
    from src.db import backtest_runs

    monkeypatch.setattr(backtest_runs, "supabase", fake_supabase)

    row = await backtest_runs.insert_run(
        target_date=date(2026, 5, 16),
        strategy_id="momentum",
        params_kind="current",
        params_snapshot={"buy_threshold": 29.0, "stop_loss_rate": -7.5},
    )

    assert row is not None
    assert row["strategy_id"] == "momentum"
    assert row["params_kind"] == "current"
    assert row["status"] == "queued"
    assert row["params_snapshot"]["buy_threshold"] == 29.0
    # store 에 1건 들어가 있어야 함
    assert len(fake_supabase.store["backtest_runs"]) == 1


@pytest.mark.asyncio
async def test_insert_run_duplicate_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """D: 동일 (target_date, strategy_id, params_kind) 재시도 시 None."""
    from src.db import backtest_runs

    monkeypatch.setattr(backtest_runs, "supabase", fake_supabase)

    args = dict(
        target_date=date(2026, 5, 16),
        strategy_id="momentum",
        params_kind="current",
        params_snapshot={"foo": 1},
    )
    first = await backtest_runs.insert_run(**args)
    second = await backtest_runs.insert_run(**args)

    assert first is not None
    assert second is None
    # 중복은 store 에 들어가지 않아야 한다
    assert len(fake_supabase.store["backtest_runs"]) == 1


@pytest.mark.asyncio
async def test_get_by_id_returns_row_or_none(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """B-1: get_by_id."""
    from src.db import backtest_runs

    monkeypatch.setattr(backtest_runs, "supabase", fake_supabase)

    row = await backtest_runs.insert_run(
        target_date=date(2026, 5, 16),
        strategy_id="volatility_breakout",
        params_kind="recommended",
        params_snapshot={"k_value_krx_main": 0.5},
    )
    assert row is not None
    rid = row["id"]

    loaded = await backtest_runs.get_by_id(rid)
    assert loaded is not None
    assert loaded["id"] == rid
    assert loaded["strategy_id"] == "volatility_breakout"

    missing = await backtest_runs.get_by_id("99999999-0000-0000-0000-000000000000")
    assert missing is None


@pytest.mark.asyncio
async def test_list_by_date_filters_by_target_date(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """B-2: list_by_date — 해당 날짜 모두 반환."""
    from src.db import backtest_runs

    monkeypatch.setattr(backtest_runs, "supabase", fake_supabase)

    await backtest_runs.insert_run(
        target_date=date(2026, 5, 16),
        strategy_id="momentum",
        params_kind="current",
        params_snapshot={},
    )
    await backtest_runs.insert_run(
        target_date=date(2026, 5, 16),
        strategy_id="momentum",
        params_kind="recommended",
        params_snapshot={},
    )
    await backtest_runs.insert_run(
        target_date=date(2026, 5, 15),
        strategy_id="momentum",
        params_kind="current",
        params_snapshot={},
    )

    rows = await backtest_runs.list_by_date(date(2026, 5, 16))
    assert len(rows) == 2
    assert {r["params_kind"] for r in rows} == {"current", "recommended"}


@pytest.mark.asyncio
async def test_update_status_transitions(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """C: update_status — queued → running → completed.

    완료 시 completed_at 자동 기록 + metrics 페이로드 함께 받음.
    """
    from src.db import backtest_runs

    monkeypatch.setattr(backtest_runs, "supabase", fake_supabase)

    row = await backtest_runs.insert_run(
        target_date=date(2026, 5, 16),
        strategy_id="donchian_swing",
        params_kind="current",
        params_snapshot={"donchian_period": 20},
    )
    assert row is not None
    rid = row["id"]

    # queued → running (mcp_job_id 부여)
    await backtest_runs.update_status(rid, "running", mcp_job_id="job-abc")
    after_running = await backtest_runs.get_by_id(rid)
    assert after_running["status"] == "running"
    assert after_running["mcp_job_id"] == "job-abc"
    assert after_running.get("completed_at") in (None, "")

    # running → completed (metrics 첨부)
    metrics = {
        "total_return_pct": 12.3,
        "sharpe_ratio": 1.4,
        "max_drawdown": -8.7,
        "win_rate": 0.62,
        "total_trades": 18,
    }
    await backtest_runs.update_status(rid, "completed", metrics=metrics)
    after_completed = await backtest_runs.get_by_id(rid)
    assert after_completed["status"] == "completed"
    assert after_completed["metrics"]["total_return_pct"] == 12.3
    assert after_completed["completed_at"] is not None


@pytest.mark.asyncio
async def test_update_status_failed_records_error(
    monkeypatch: pytest.MonkeyPatch,
    fake_supabase,
):
    """C': update_status failed — error_message 영속화 + completed_at 기록."""
    from src.db import backtest_runs

    monkeypatch.setattr(backtest_runs, "supabase", fake_supabase)

    row = await backtest_runs.insert_run(
        target_date=date(2026, 5, 16),
        strategy_id="vcp_breakout",
        params_kind="current",
        params_snapshot={"ema_short": 50},
    )
    rid = row["id"]

    await backtest_runs.update_status(
        rid, "failed", error_message="MCP timeout after 300s"
    )
    after = await backtest_runs.get_by_id(rid)
    assert after["status"] == "failed"
    assert after["error_message"] == "MCP timeout after 300s"
    assert after["completed_at"] is not None
