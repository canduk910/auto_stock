"""사이클 101 G-EMIT1 — `[full_universe_load_summary]` 운영 가시화 영속 (MEDIUM).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**domain-expert A3 영속 (운영 가시화 prefix)**:
- `[full_universe_load_summary] total=N kospi=M kosdaq=K securities=L etf=J fetched=I skipped_ttl=H failed=G elapsed_ms=F`
- 매일 20:00:05 적재 후 1행 INFO emit

검증 매트릭스:
- G-EMIT1-A: `flush_full_universe_load_collector` 호출 시 `[full_universe_load_summary]` prefix INFO 로그 ≥1건
- G-EMIT1-B: emit 영역 9 키 (total / kospi / kosdaq / securities / etf / fetched / skipped_ttl / failed / elapsed_ms) 포함

Red 상태: collector 함수 부재 또는 emit 부재.
Green (backend-dev): logger.info("[full_universe_load_summary] ...") emit 영속.

영속 의무:
- 사이클 74 collector 패턴 답습 (record/flush 페어링)
- 사이클 89 emit 패턴 답습 (`[stock_master_bulk_refresh]`)
- 매매 안전성 영역 영향 0 (로깅 영역만)
"""
from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit


def test_g_emit1_a_flush_emits_summary_prefix(caplog: pytest.LogCaptureFixture) -> None:
    """G-EMIT1-A: flush 시 `[full_universe_load_summary]` prefix INFO emit 영속 (MEDIUM).

    Red 상태: collector 함수 부재 또는 emit 부재.
    Green (backend-dev): flush 함수 내부 logger.info emit 영속.
    """
    import src.engine.stock_master_metrics as metrics_mod

    if not hasattr(metrics_mod, "record_full_universe_load_summary"):
        pytest.fail(
            "사이클 101 G-EMIT1-A Red — `record_full_universe_load_summary` 부재 (G-AST1-A 영속).\n"
            "  Green: stock_master_metrics.py 함수 정의 의무"
        )
    if not hasattr(metrics_mod, "flush_full_universe_load_collector"):
        pytest.fail(
            "사이클 101 G-EMIT1-A Red — `flush_full_universe_load_collector` 부재 (G-AST1-B 영속).\n"
            "  Green: stock_master_metrics.py 함수 정의 의무"
        )

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    # 1건 적재 + flush
    stats = {
        "total": 2800,
        "kospi": 950,
        "kosdaq": 1650,
        "securities": 2600,
        "etf": 200,
        "fetched": 2800,
        "skipped_ttl": 0,
        "failed": 0,
        "elapsed_ms": 280000,
    }

    record_func = metrics_mod.record_full_universe_load_summary
    flush_func = metrics_mod.flush_full_universe_load_collector

    # async 또는 sync 양쪽 호환
    import asyncio
    import inspect

    async def _exec():
        if inspect.iscoroutinefunction(record_func):
            await record_func(stats)
        else:
            record_func(stats)
        if inspect.iscoroutinefunction(flush_func):
            await flush_func()
        else:
            flush_func()

    asyncio.run(_exec())

    summary_records = [
        rec for rec in caplog.records
        if "[full_universe_load_summary]" in rec.getMessage()
    ]
    assert len(summary_records) >= 1, (
        f"\n사이클 101 G-EMIT1-A 위반 — `[full_universe_load_summary]` emit 0건:\n"
        f"  기대: flush 호출 시 INFO emit ≥1건\n"
        f"  실제 emit: {len(summary_records)}건\n"
        f"  Red 결함 가설: flush 함수 내부 logger.info emit 부재\n"
        f"  Green (backend-dev): logger.info('[full_universe_load_summary] total=%d ...') 영속"
    )


def test_g_emit1_b_summary_contains_nine_keys(caplog: pytest.LogCaptureFixture) -> None:
    """G-EMIT1-B: emit 영역 9 키 포함 영속 (MEDIUM).

    검증 매트릭스 (운영 가시화 의무):
    - total / kospi / kosdaq / securities / etf / fetched / skipped_ttl / failed / elapsed_ms

    Red 상태: emit 부재 또는 키 누락.
    Green (backend-dev): 9 키 모두 emit 영속.
    """
    import src.engine.stock_master_metrics as metrics_mod

    if not hasattr(metrics_mod, "record_full_universe_load_summary"):
        pytest.fail("G-EMIT1-B Red — record 부재 (G-AST1-A 영속)")
    if not hasattr(metrics_mod, "flush_full_universe_load_collector"):
        pytest.fail("G-EMIT1-B Red — flush 부재 (G-AST1-B 영속)")

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    stats = {
        "total": 2800, "kospi": 950, "kosdaq": 1650,
        "securities": 2600, "etf": 200, "fetched": 2800,
        "skipped_ttl": 0, "failed": 0, "elapsed_ms": 280000,
    }

    import asyncio
    import inspect

    async def _exec():
        rec = metrics_mod.record_full_universe_load_summary
        fl = metrics_mod.flush_full_universe_load_collector
        if inspect.iscoroutinefunction(rec):
            await rec(stats)
        else:
            rec(stats)
        if inspect.iscoroutinefunction(fl):
            await fl()
        else:
            fl()

    asyncio.run(_exec())

    summary_msg = ""
    for rec in caplog.records:
        msg = rec.getMessage()
        if "[full_universe_load_summary]" in msg:
            summary_msg = msg
            break

    required_keys = [
        "total=", "kospi=", "kosdaq=", "securities=", "etf=",
        "fetched=", "skipped_ttl=", "failed=", "elapsed_ms=",
    ]
    missing = [k for k in required_keys if k not in summary_msg]
    assert not missing, (
        f"\n사이클 101 G-EMIT1-B 위반 — 9 키 누락:\n"
        f"  기대 키: {required_keys}\n"
        f"  누락 키: {missing}\n"
        f"  실제 msg: {summary_msg!r}\n"
        f"  Green (backend-dev): 9 키 모두 emit 영속 의무"
    )
