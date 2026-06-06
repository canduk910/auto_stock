"""사이클 65 (2026-06-06) Red — H 카테고리: scanner daily_summary (1 케이스).

> **선행 명세**: `_workspace/red/cycle65_trade_amount_filter.md` (§File 7)
> **자문 응답**: Q5 별도 prefix `[trade_amount_filter_scanner_daily_summary]`
> **선례**: 사이클 64 H-1 패턴 답습 (운영자 가시화)

요구 행위 (Red 단계 AttributeError 정답 — `emit_trade_amount_filter_scanner_daily_summary` 미존재):

- H-1 [LOW]: `_settle()` 직전 `[trade_amount_filter_scanner_daily_summary]` 1행 INFO emit.
       포함 필드: block_count

freezegun 20:10 KST 정산 시각 명시.

위험 등급 LOW (운영자 가시화).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


@pytest.fixture(autouse=True)
def _reset_cycle65_scanner_state():
    """사이클 65 scanner 모듈 전역 reset."""
    from src.engine import scanner

    if hasattr(scanner, "_trade_amount_filter_scanner_skip_logged_today"):
        scanner._trade_amount_filter_scanner_skip_logged_today.clear()
    if hasattr(scanner, "_trade_amount_filter_scanner_skip_count_today"):
        for k in list(scanner._trade_amount_filter_scanner_skip_count_today):
            scanner._trade_amount_filter_scanner_skip_count_today[k] = 0
    yield


@pytest.mark.asyncio
async def test_H1_daily_summary_writes_with_correct_prefix(caplog: pytest.LogCaptureFixture):
    """H-1: `emit_trade_amount_filter_scanner_daily_summary()` 호출 시
    `[trade_amount_filter_scanner_daily_summary]` 1행 INFO emit + system_logs INSERT.

    검증 필드:
    - prefix `[trade_amount_filter_scanner_daily_summary]`
    - `block_count=N` (Q5 자문 별도 prefix 확정)

    20:10 KST 정산 시점 freeze.
    """
    from src.engine import scanner  # Red: emit_trade_amount_filter_scanner_daily_summary 미존재

    # 일중 cap 누적 시뮬레이션 — Red 단계 필드 미존재 → AttributeError
    scanner._trade_amount_filter_scanner_skip_count_today["total"] = 42

    write_log_mock = AsyncMock()

    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    with freeze_time(datetime(2026, 6, 6, 20, 10, 0, tzinfo=KST)), \
         patch("src.db.system_logs.write_log", write_log_mock):
        # Red: `emit_trade_amount_filter_scanner_daily_summary` 미존재 → AttributeError 정답
        await scanner.emit_trade_amount_filter_scanner_daily_summary()

    # 1) logger INFO 1행 emit 검증
    summary_logs = [
        r for r in caplog.records
        if "[trade_amount_filter_scanner_daily_summary]" in r.message
    ]
    assert len(summary_logs) == 1, (
        f"일일 집계 로그 누락/중복 — `[trade_amount_filter_scanner_daily_summary]` "
        f"1행 의무 (실제 {len(summary_logs)}건)"
    )
    msg = summary_logs[0].message
    assert "block_count=42" in msg, (
        f"block_count 필드 누락 또는 값 결함: {msg}"
    )

    # 2) system_logs.write_log INSERT 검증
    write_log_mock.assert_called_once()
    call_args = write_log_mock.call_args
    # write_log("INFO", "...") 형태 (사이클 64 답습)
    assert call_args[0][0] == "INFO", (
        f"write_log 첫 인자 'INFO' 의무 (실제 {call_args[0][0]})"
    )
    assert "[trade_amount_filter_scanner_daily_summary]" in call_args[0][1], (
        f"system_logs prefix 누락: {call_args[0][1]}"
    )
    assert "block_count=42" in call_args[0][1], (
        f"system_logs block_count 누락: {call_args[0][1]}"
    )
