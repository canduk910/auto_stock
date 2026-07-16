"""사이클 M1-2 (Red) — 4 모듈 실 Postgres 왕복 통합 검증.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, 증분 2).

대상: log_reports / backtest_runs / market_regime_snapshots / pending_next_day_clear.
mock 단위 테스트로 못 잡는 **실 SQL · JSONB codec · 복합 PK · UNIQUE upsert** 안전망.
docker/DATABASE_URL_TEST 없으면 pg_harness fixture 가 pytest.skip.

⚠️ 핵심 = JSONB 컬럼(findings/metrics/params_snapshot/raw_response)이 **dict/list 로
반환**(str 아님)되는지 = 계획 3대 리스크 1순위(JSONB codec 누락 silent 폴백) 라이브 가드.

Red 유효성: production(4 모듈)이 아직 pg 미사용 → 실 PG 왕복 경로 없음(supabase 미연결)
→ 이 테스트 전부 FAIL/에러.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


# ===========================================================================
# log_reports — JSONB findings/metrics dict/list 왕복 + UNIQUE(target_date) upsert
# ===========================================================================
@pytest.mark.asyncio
async def test_log_reports_jsonb_roundtrip_returns_dict_list(clean_log_reports):
    """⚠️ insert → get 후 findings=list / metrics=dict = JSONB codec 실증."""
    from src.db import log_reports

    findings = [{"category": "api", "severity": "high", "title": "T", "detail": {"n": 1}}]
    metrics = {"info": 3, "warn": 1, "by_hour": {"09": 2}}
    inserted = await log_reports.insert_log_report(
        target_date=date(2026, 7, 16),
        summary="요약",
        findings=findings,
        metrics=metrics,
        model="gpt-4",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        latency_ms=1200,
        cost_estimate_usd=Decimal("0.001234"),
    )
    assert inserted is not None, "insert_log_report → 삽입 dict."

    got = await log_reports.get_log_report(date(2026, 7, 16))
    assert got is not None
    assert isinstance(got["findings"], list), (
        "findings 가 list 아님 → JSONB codec 미작동 (계획 최대 위험 실현)."
    )
    assert isinstance(got["metrics"], dict), "metrics 가 dict 아님 → JSONB codec 미작동."
    assert got["findings"] == findings, "findings JSONB 왕복 무손실."
    assert got["metrics"]["by_hour"]["09"] == 2, "중첩 dict 보존."
    assert got["target_date"] == date(2026, 7, 16), "target_date DATE → date 객체."


@pytest.mark.asyncio
async def test_log_reports_unique_target_date_returns_none(clean_log_reports):
    """동일 target_date 재INSERT → UNIQUE 충돌 → None (중복 방지)."""
    from src.db import log_reports

    first = await log_reports.insert_log_report(
        target_date=date(2026, 7, 16), summary="a", findings=[], metrics={}, model=None,
    )
    assert first is not None
    dup = await log_reports.insert_log_report(
        target_date=date(2026, 7, 16), summary="b", findings=[], metrics={}, model=None,
    )
    assert dup is None, "target_date UNIQUE 충돌 → None."

    rows = await log_reports.list_log_reports()
    assert len(rows) == 1, "UNIQUE → 1행."


@pytest.mark.asyncio
async def test_log_reports_list_order_desc(clean_log_reports):
    """list_log_reports → target_date DESC 정렬."""
    from src.db import log_reports

    for d in (date(2026, 7, 14), date(2026, 7, 16), date(2026, 7, 15)):
        await log_reports.insert_log_report(
            target_date=d, summary="x", findings=[], metrics={}, model=None,
        )
    rows = await log_reports.list_log_reports(days=30)

    dates = [r["target_date"] for r in rows]
    assert dates == sorted(dates, reverse=True), "target_date DESC 정렬 계약."


# ===========================================================================
# backtest_runs — JSONB params_snapshot/metrics + 복합 UNIQUE + update_status
# ===========================================================================
@pytest.mark.asyncio
async def test_backtest_runs_jsonb_roundtrip_and_composite_unique(clean_backtest_runs):
    """⚠️ insert → get 후 params_snapshot=dict = JSONB codec. 복합 UNIQUE 멱등."""
    from src.db import backtest_runs

    params = {"k_value": 1.3, "stop_loss_rate": -3.0, "nested": {"a": [1, 2]}}
    inserted = await backtest_runs.insert_run(
        date(2026, 7, 16), "momentum", "current", params
    )
    assert inserted is not None, "insert_run → 삽입 dict."
    run_id = inserted["id"]

    got = await backtest_runs.get_by_id(run_id)
    assert got is not None
    assert isinstance(got["params_snapshot"], dict), (
        "params_snapshot 가 dict 아님 → JSONB codec 미작동."
    )
    assert got["params_snapshot"] == params, "params_snapshot JSONB 왕복 무손실."
    assert got["status"] == "queued", "초기 status=queued."

    # 복합 UNIQUE (target_date, strategy_id, params_kind) 재INSERT → None
    dup = await backtest_runs.insert_run(
        date(2026, 7, 16), "momentum", "current", {"k_value": 9.9}
    )
    assert dup is None, "복합 UNIQUE 충돌 → None."

    rows = await backtest_runs.list_by_date(date(2026, 7, 16))
    assert len(rows) == 1, "복합 UNIQUE → 1행."


@pytest.mark.asyncio
async def test_backtest_runs_update_status_completed_metrics_jsonb(clean_backtest_runs):
    """update_status(completed, metrics=…) → metrics JSONB 왕복 + completed_at 기록."""
    from src.db import backtest_runs

    inserted = await backtest_runs.insert_run(
        date(2026, 7, 16), "volatility_breakout", "recommended", {"k": 1}
    )
    run_id = inserted["id"]

    metrics = {"sharpe_ratio": 1.2, "win_rate": 0.55, "trades": [1, 2, 3]}
    updated = await backtest_runs.update_status(run_id, "completed", metrics=metrics)

    assert updated["status"] == "completed"
    assert isinstance(updated["metrics"], dict), "metrics 가 dict 아님 → JSONB codec 미작동."
    assert updated["metrics"] == metrics, "metrics JSONB 왕복 무손실."
    assert updated.get("completed_at") is not None, "completed 시 completed_at 기록."


@pytest.mark.asyncio
async def test_backtest_runs_update_status_missing_returns_empty(clean_backtest_runs):
    """존재하지 않는 id update → 적용 0건 → {}."""
    from src.db import backtest_runs

    out = await backtest_runs.update_status(
        "00000000-0000-0000-0000-000000000000", "completed"
    )
    assert out == {}, "적용 row 0건 → {}."


# ===========================================================================
# market_regime_snapshots — JSONB raw_response + NUMERIC + UNIQUE(snapshot_date)
# ===========================================================================
@pytest.mark.asyncio
async def test_market_regime_jsonb_roundtrip_and_unique(clean_market_regime):
    """⚠️ insert → get 후 raw_response=dict = JSONB codec. UNIQUE(snapshot_date)."""
    from src.db import market_regime_snapshots as mrs

    raw = {"macro": {"regime": "neutral", "cycle": "expansion"}, "sentiment": {"fg": 55}}
    inserted = await mrs.insert_snapshot(
        snapshot_date=date(2026, 7, 16),
        regime="neutral",
        regime_desc="중립",
        cycle_phase="expansion",
        vix=18.5,
        fear_greed_score=55.0,
        buffett_ratio=140.0,
        raw_response=raw,
        computed_cash_usage_ratio=0.8,
        buy_blocked=False,
        block_reason=None,
    )
    assert inserted is not None, "insert_snapshot → 삽입 dict."

    got = await mrs.get_by_date(date(2026, 7, 16))
    assert got is not None
    assert isinstance(got["raw_response"], dict), (
        "raw_response 가 dict 아님 → JSONB codec 미작동."
    )
    assert got["raw_response"] == raw, "raw_response JSONB 왕복 무손실."
    assert got["regime"] == "neutral"
    assert got["buy_blocked"] is False, "buy_blocked BOOLEAN → bool."
    # NUMERIC 컬럼 값 정합 (float 또는 Decimal — 값 자체 검증)
    assert abs(float(got["vix"]) - 18.5) < 1e-6, "vix NUMERIC 왕복."

    # UNIQUE(snapshot_date) 재INSERT → None
    dup = await mrs.insert_snapshot(
        snapshot_date=date(2026, 7, 16),
        regime="aggressive",
        regime_desc="x",
        cycle_phase="x",
        vix=10.0,
        fear_greed_score=90.0,
        buffett_ratio=200.0,
        raw_response={},
        computed_cash_usage_ratio=1.0,
        buy_blocked=True,
        block_reason="dup",
    )
    assert dup is None, "snapshot_date UNIQUE 충돌 → None."


@pytest.mark.asyncio
async def test_market_regime_get_latest_and_list_recent(clean_market_regime):
    """get_latest = 최신 snapshot_date / list_recent DESC 정렬."""
    from src.db import market_regime_snapshots as mrs

    for d in (date(2026, 7, 14), date(2026, 7, 16), date(2026, 7, 15)):
        await mrs.insert_snapshot(
            snapshot_date=d,
            regime="neutral",
            regime_desc=None,
            cycle_phase=None,
            vix=15.0,
            fear_greed_score=50.0,
            buffett_ratio=130.0,
            raw_response={"d": d.isoformat()},
            computed_cash_usage_ratio=0.9,
            buy_blocked=False,
            block_reason=None,
        )

    latest = await mrs.get_latest()
    assert latest["snapshot_date"] == date(2026, 7, 16), "get_latest = 최신 날짜."

    rows = await mrs.list_recent(days=30)
    dates = [r["snapshot_date"] for r in rows]
    assert dates == sorted(dates, reverse=True), "list_recent DESC 정렬 계약."


# ===========================================================================
# pending_next_day_clear — ⚠️ 복합 PK upsert + set 반환 + purge (익일청산 큐)
# ===========================================================================
@pytest.mark.asyncio
async def test_pending_ndc_save_load_roundtrip_composite_pk(clean_pending_ndc):
    """save → load 왕복: set[(ticker, strategy_id)] 반환 + 복합 PK upsert 1행."""
    from src.db import pending_next_day_clear as pnd

    await pnd.save_pending_ndc(
        date(2026, 7, 16), "196170", "volatility_breakout", reason="nxt_not_tradable"
    )
    await pnd.save_pending_ndc(
        date(2026, 7, 16), "476830", "long_tail_volatility", reason="nxt_open_missing"
    )
    # 동일 복합 PK 재저장 → upsert (중복 없음)
    await pnd.save_pending_ndc(
        date(2026, 7, 16), "196170", "volatility_breakout", reason="market_order_disallowed_fallback"
    )

    loaded = await pnd.load_pending_ndc(date(2026, 7, 16))
    assert loaded == {
        ("196170", "volatility_breakout"),
        ("476830", "long_tail_volatility"),
    }, "load_pending_ndc → set[tuple] + 복합 PK upsert 중복 없음."


@pytest.mark.asyncio
async def test_pending_ndc_delete_idempotent(clean_pending_ndc):
    """delete → 해당 복합 키만 삭제 + 미존재 삭제 idempotent."""
    from src.db import pending_next_day_clear as pnd

    await pnd.save_pending_ndc(date(2026, 7, 16), "196170", "volatility_breakout")
    await pnd.save_pending_ndc(date(2026, 7, 16), "476830", "long_tail_volatility")

    await pnd.delete_pending_ndc(date(2026, 7, 16), "196170", "volatility_breakout")
    # 미존재 삭제 (idempotent, 예외 없음)
    await pnd.delete_pending_ndc(date(2026, 7, 16), "999999", "momentum")

    loaded = await pnd.load_pending_ndc(date(2026, 7, 16))
    assert loaded == {("476830", "long_tail_volatility")}, "해당 복합 키만 삭제."


@pytest.mark.asyncio
async def test_pending_ndc_purge_before(clean_pending_ndc):
    """purge_pending_ndc_before → cutoff 이전 행만 DELETE + 삭제 수 반환."""
    from src.db import pending_next_day_clear as pnd

    await pnd.save_pending_ndc(date(2026, 7, 14), "111111", "momentum")
    await pnd.save_pending_ndc(date(2026, 7, 15), "222222", "donchian_swing")
    await pnd.save_pending_ndc(date(2026, 7, 16), "333333", "volatility_breakout")

    deleted = await pnd.purge_pending_ndc_before(date(2026, 7, 16))
    assert deleted == 2, "target_date < cutoff = 2행 삭제."

    remaining = await pnd.load_pending_ndc(date(2026, 7, 16))
    assert remaining == {("333333", "volatility_breakout")}, "cutoff 당일 이후 보존."
