"""Phase 3 Red — `_backtest_poll_loop(target_date)` 백그라운드 폴 루프.

요구 행위:

1. ``_backtest_poll_loop(target_date)`` 는 60s 주기로 미완료 backtest_runs row 를 폴링.
2. 완료된 job → ``update_status('completed', metrics=...)`` + 비교 메트릭 누적.
3. 한 자문 row(strategy_id)의 ``current`` + ``recommended`` 두 row 가 모두 종료 상태에
   도달하면 ``parameter_recommendations.backtest_summary`` 갱신.
4. 모든 6 전략 backtest_summary 동봉 완료 시 task 종료.
5. 24h 경과(``_BACKTEST_POLL_TIMEOUT_HOURS``) → 미완료 row ``status='failed'`` 후 종료.
6. ``_backtest_poll_loop_running`` 가드 — 중복 task 차단.

테스트는 polling sleep 을 즉시 0초로 단축하고, get_backtest_engine().poll 을 모킹해
running → completed 시뮬레이션.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 헬퍼: rows store 구축 (current/recommended × 6 전략 = 12 row)
# ---------------------------------------------------------------------------
def _make_rows_store(target_date: date) -> dict[str, dict]:
    """run_id -> row dict store. UI 의 parameter_recommendations 매핑은 strategy_id 로 처리."""
    store: dict[str, dict] = {}
    for sid in ("momentum", "volatility_breakout", "donchian_swing"):
        for kind in ("current", "recommended"):
            run_id = f"run-{sid}-{kind}"
            store[run_id] = {
                "id": run_id,
                "target_date": target_date.isoformat(),
                "strategy_id": sid,
                "params_kind": kind,
                "status": "running",
                "mcp_job_id": f"job-{sid}-{kind}",
                "metrics": None,
                "error_message": None,
            }
    # (b) 폴백 3 전략은 이미 skipped 상태
    for sid in ("long_tail_volatility", "bull_flag_breakout", "vcp_breakout"):
        for kind in ("current", "recommended"):
            run_id = f"run-{sid}-{kind}"
            store[run_id] = {
                "id": run_id,
                "target_date": target_date.isoformat(),
                "strategy_id": sid,
                "params_kind": kind,
                "status": "skipped",
                "mcp_job_id": None,
                "metrics": None,
                "error_message": "YAML DSL 미지원",
            }
    return store


# ---------------------------------------------------------------------------
# A: poll loop 가 미완료 row 만 폴링 → completed 전이
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_loop_polls_running_rows(monkeypatch: pytest.MonkeyPatch):
    """A: poll 호출 후 completed 전이 → metrics 첨부."""
    from src.engine import recommendation_engine as rec_mod
    from src.models.backtest import BacktestMetrics

    target = date(2026, 5, 16)
    store = _make_rows_store(target)

    # ---- DB 헬퍼 모킹 ----
    async def fake_list_by_date(td):
        assert td == target
        return list(store.values())

    async def fake_update_status(run_id, status, **kwargs):
        row = store[run_id]
        row["status"] = status
        if "metrics" in kwargs:
            row["metrics"] = kwargs["metrics"]
        if "error_message" in kwargs:
            row["error_message"] = kwargs["error_message"]
        return row

    pr_updates: list[dict] = []

    async def fake_list_pending(td):
        # 모든 rec_id 가 아직 backtest_summary=null 이라고 가정
        return [
            {"id": f"rec-{s}", "strategy_id": s, "target_date": td.isoformat()}
            for s in ("momentum", "volatility_breakout", "donchian_swing",
                     "long_tail_volatility", "bull_flag_breakout", "vcp_breakout")
        ]

    async def fake_update_backtest_summary(rec_id, summary):
        pr_updates.append({"rec_id": rec_id, "summary": summary})
        return {"id": rec_id, "backtest_summary": summary}

    monkeypatch.setattr(rec_mod, "_db_list_by_date", fake_list_by_date, raising=False)
    monkeypatch.setattr(rec_mod, "_db_update_status", fake_update_status, raising=False)
    monkeypatch.setattr(
        rec_mod, "_db_list_pending_backtest", fake_list_pending, raising=False
    )
    monkeypatch.setattr(
        rec_mod, "_db_update_backtest_summary", fake_update_backtest_summary, raising=False
    )

    # ---- BacktestEngine.poll 모킹: 1차 호출에 모든 (a) job 완료 반환 ----
    poll_calls: list[str] = []

    completed_metrics = {
        "total_return_pct": 12.3,
        "cagr": 14.5,
        "sharpe_ratio": 1.4,
        "sortino_ratio": 1.8,
        "max_drawdown": -7.5,
        "win_rate": 0.62,
        "profit_factor": 1.9,
        "total_trades": 18,
    }

    class FakeEngine:
        enabled = True

        async def poll(self, job_id):
            poll_calls.append(job_id)
            # 모두 즉시 완료
            return BacktestMetrics.model_validate(completed_metrics)

    monkeypatch.setattr(rec_mod, "_get_backtest_engine", lambda: FakeEngine(), raising=False)
    # poll 주기 0초로 단축
    monkeypatch.setattr(rec_mod, "_BACKTEST_POLL_INTERVAL_SECS", 0, raising=False)
    # 24h timeout 그대로
    monkeypatch.setattr(rec_mod, "_BACKTEST_POLL_TIMEOUT_HOURS", 24, raising=False)

    await rec_mod._backtest_poll_loop(target)

    # (a) 6 row 모두 completed (current+recommended × 3 전략)
    completed = [r for r in store.values() if r["status"] == "completed"]
    assert len(completed) == 6
    for r in completed:
        assert r["metrics"]["total_return_pct"] == 12.3

    # (a) 3 전략 + (b) 3 전략 = 6 전략 backtest_summary 갱신
    summary_rec_ids = {u["rec_id"] for u in pr_updates}
    assert summary_rec_ids == {
        f"rec-{s}"
        for s in ("momentum", "volatility_breakout", "donchian_swing",
                  "long_tail_volatility", "bull_flag_breakout", "vcp_breakout")
    }

    # poll 호출 횟수 = 6 (a) job
    assert len(poll_calls) == 6


# ---------------------------------------------------------------------------
# B: completed 전이 후 summary diff 계산 검증
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_loop_computes_diff_in_summary(monkeypatch: pytest.MonkeyPatch):
    """B: backtest_summary.diff[strategy_id] 는 recommended - current 산술 차."""
    from src.engine import recommendation_engine as rec_mod
    from src.models.backtest import BacktestMetrics

    target = date(2026, 5, 16)
    store = _make_rows_store(target)

    # current vs recommended 메트릭을 분리
    cur_metrics = {
        "total_return_pct": 10.0,
        "sharpe_ratio": 1.0,
        "max_drawdown": -10.0,
        "win_rate": 0.5,
        "total_trades": 20,
        "cagr": None, "sortino_ratio": None, "profit_factor": None,
    }
    rec_metrics = {
        "total_return_pct": 15.0,
        "sharpe_ratio": 1.5,
        "max_drawdown": -7.0,
        "win_rate": 0.6,
        "total_trades": 22,
        "cagr": None, "sortino_ratio": None, "profit_factor": None,
    }

    async def fake_list_by_date(td):
        return list(store.values())

    async def fake_update_status(run_id, status, **kwargs):
        row = store[run_id]
        row["status"] = status
        if "metrics" in kwargs:
            row["metrics"] = kwargs["metrics"]
        return row

    pr_updates: dict[str, dict] = {}

    async def fake_list_pending(td):
        return [
            {"id": f"rec-{s}", "strategy_id": s, "target_date": td.isoformat()}
            for s in ("momentum", "volatility_breakout", "donchian_swing",
                     "long_tail_volatility", "bull_flag_breakout", "vcp_breakout")
        ]

    async def fake_update_backtest_summary(rec_id, summary):
        pr_updates[rec_id] = summary
        return {"id": rec_id, "backtest_summary": summary}

    monkeypatch.setattr(rec_mod, "_db_list_by_date", fake_list_by_date, raising=False)
    monkeypatch.setattr(rec_mod, "_db_update_status", fake_update_status, raising=False)
    monkeypatch.setattr(
        rec_mod, "_db_list_pending_backtest", fake_list_pending, raising=False
    )
    monkeypatch.setattr(
        rec_mod, "_db_update_backtest_summary", fake_update_backtest_summary, raising=False
    )

    class FakeEngine:
        enabled = True

        async def poll(self, job_id):
            # job_id = "job-<strategy_id>-<kind>"
            parts = job_id.rsplit("-", 1)
            kind = parts[1]
            return BacktestMetrics.model_validate(
                rec_metrics if kind == "recommended" else cur_metrics
            )

    monkeypatch.setattr(rec_mod, "_get_backtest_engine", lambda: FakeEngine(), raising=False)
    monkeypatch.setattr(rec_mod, "_BACKTEST_POLL_INTERVAL_SECS", 0, raising=False)

    await rec_mod._backtest_poll_loop(target)

    # (a) 전략 momentum diff
    mom_summary = pr_updates["rec-momentum"]
    diff = mom_summary["diff"]["momentum"]
    assert diff["total_return_pct"] == pytest.approx(5.0)
    assert diff["sharpe_ratio"] == pytest.approx(0.5)
    assert diff["max_drawdown"] == pytest.approx(3.0)
    assert diff["win_rate"] == pytest.approx(0.1)
    assert diff["total_trades"] == pytest.approx(2.0)

    # current/recommended 둘 다 메트릭 동봉
    assert mom_summary["current"]["momentum"]["total_return_pct"] == 10.0
    assert mom_summary["recommended"]["momentum"]["total_return_pct"] == 15.0

    # (b) skipped 전략은 current=None / recommended=None / diff 비어있어야 함
    ltv_summary = pr_updates["rec-long_tail_volatility"]
    assert ltv_summary["current"].get("long_tail_volatility") is None
    assert ltv_summary["recommended"].get("long_tail_volatility") is None
    assert ltv_summary["diff"].get("long_tail_volatility", {}) in ({}, None)


# ---------------------------------------------------------------------------
# C: 한쪽만 완료된 상황에서는 summary 갱신 보류 (next iteration 위임)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_loop_defers_summary_until_both_ready(
    monkeypatch: pytest.MonkeyPatch,
):
    """C: current 만 완료된 시점엔 summary 동봉 안 됨 (recommended 대기)."""
    from src.engine import recommendation_engine as rec_mod
    from src.models.backtest import BacktestMetrics

    target = date(2026, 5, 16)
    store = _make_rows_store(target)
    # 모든 (b) skipped 제거 — 본 케이스는 (a) 1 전략만 추적
    keep_ids = {"run-momentum-current", "run-momentum-recommended"}
    store = {k: v for k, v in store.items() if k in keep_ids}

    async def fake_list_by_date(td):
        return list(store.values())

    async def fake_update_status(run_id, status, **kwargs):
        row = store[run_id]
        row["status"] = status
        if "metrics" in kwargs:
            row["metrics"] = kwargs["metrics"]
        return row

    pr_updates: dict[str, dict] = {}

    async def fake_list_pending(td):
        return [{"id": "rec-momentum", "strategy_id": "momentum",
                 "target_date": td.isoformat()}]

    async def fake_update_backtest_summary(rec_id, summary):
        pr_updates[rec_id] = summary
        return {"id": rec_id}

    monkeypatch.setattr(rec_mod, "_db_list_by_date", fake_list_by_date, raising=False)
    monkeypatch.setattr(rec_mod, "_db_update_status", fake_update_status, raising=False)
    monkeypatch.setattr(
        rec_mod, "_db_list_pending_backtest", fake_list_pending, raising=False
    )
    monkeypatch.setattr(
        rec_mod, "_db_update_backtest_summary", fake_update_backtest_summary, raising=False
    )

    poll_counts = {"calls": 0}

    class FakeEngine:
        enabled = True

        async def poll(self, job_id):
            poll_counts["calls"] += 1
            # 첫 호출: current 만 완료 / recommended 는 None(running)
            if poll_counts["calls"] == 1:
                # current 완료
                if "current" in job_id:
                    return BacktestMetrics.model_validate({"total_return_pct": 10.0})
                return None  # running
            # 다음 호출들: recommended 도 완료
            if "recommended" in job_id:
                return BacktestMetrics.model_validate({"total_return_pct": 15.0})
            return BacktestMetrics.model_validate({"total_return_pct": 10.0})

    monkeypatch.setattr(rec_mod, "_get_backtest_engine", lambda: FakeEngine(), raising=False)
    monkeypatch.setattr(rec_mod, "_BACKTEST_POLL_INTERVAL_SECS", 0, raising=False)

    await rec_mod._backtest_poll_loop(target)

    # 최종적으로 momentum summary 가 한 번은 동봉되어야 한다
    assert "rec-momentum" in pr_updates
    summary = pr_updates["rec-momentum"]
    assert summary["current"]["momentum"]["total_return_pct"] == 10.0
    assert summary["recommended"]["momentum"]["total_return_pct"] == 15.0


# ---------------------------------------------------------------------------
# D: 24h timeout — 미완료 row 를 failed 로 마킹 후 종료
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_loop_times_out_after_24h(monkeypatch: pytest.MonkeyPatch):
    """D: 24h 경과 시 미완료 row 'failed' + 'Timeout' 에러메시지 + task 종료."""
    from src.engine import recommendation_engine as rec_mod

    target = date(2026, 5, 16)
    # 모든 row 가 running 인 상태 — poll 이 영원히 None 반환
    store = _make_rows_store(target)
    for r in store.values():
        if r["status"] == "skipped":
            continue
        r["status"] = "running"

    async def fake_list_by_date(td):
        return list(store.values())

    update_calls: list[dict] = []

    async def fake_update_status(run_id, status, **kwargs):
        update_calls.append({"run_id": run_id, "status": status, **kwargs})
        row = store[run_id]
        row["status"] = status
        if "error_message" in kwargs:
            row["error_message"] = kwargs["error_message"]
        return row

    async def fake_list_pending(td):
        return []

    async def fake_update_backtest_summary(rec_id, summary):
        return {}

    monkeypatch.setattr(rec_mod, "_db_list_by_date", fake_list_by_date, raising=False)
    monkeypatch.setattr(rec_mod, "_db_update_status", fake_update_status, raising=False)
    monkeypatch.setattr(
        rec_mod, "_db_list_pending_backtest", fake_list_pending, raising=False
    )
    monkeypatch.setattr(
        rec_mod, "_db_update_backtest_summary", fake_update_backtest_summary, raising=False
    )

    class FakeEngine:
        enabled = True

        async def poll(self, job_id):
            return None  # 영원히 running

    monkeypatch.setattr(rec_mod, "_get_backtest_engine", lambda: FakeEngine(), raising=False)
    monkeypatch.setattr(rec_mod, "_BACKTEST_POLL_INTERVAL_SECS", 0, raising=False)
    # 0시간 timeout 으로 즉시 종료 트리거
    monkeypatch.setattr(rec_mod, "_BACKTEST_POLL_TIMEOUT_HOURS", 0, raising=False)

    await rec_mod._backtest_poll_loop(target)

    # 모든 (a) running row 가 failed 로 마킹되어야 한다
    failed = [u for u in update_calls if u["status"] == "failed"]
    failed_ids = {u["run_id"] for u in failed}
    assert failed_ids == {
        f"run-{s}-{k}"
        for s in ("momentum", "volatility_breakout", "donchian_swing")
        for k in ("current", "recommended")
    }
    for u in failed:
        assert "Timeout" in u.get("error_message", "") or "timeout" in u.get("error_message", "")


# ---------------------------------------------------------------------------
# E: 중복 task 가드 — _backtest_poll_loop_running 이 set 이면 즉시 종료
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_loop_guards_against_duplicate(monkeypatch: pytest.MonkeyPatch):
    """E: 같은 target_date 에 대해 두 번 동시 진입 시 두 번째는 즉시 종료."""
    from src.engine import recommendation_engine as rec_mod

    target = date(2026, 5, 16)

    # 이미 실행 중이라고 시그널
    monkeypatch.setattr(
        rec_mod, "_backtest_poll_loop_running",
        {target},
        raising=False,
    )

    list_calls = {"n": 0}

    async def fake_list_by_date(td):
        list_calls["n"] += 1
        return []

    monkeypatch.setattr(rec_mod, "_db_list_by_date", fake_list_by_date, raising=False)

    await rec_mod._backtest_poll_loop(target)

    # _db_list_by_date 호출 0 — 가드에 의해 즉시 종료
    assert list_calls["n"] == 0
