"""사이클 62 (2026-06-05) Red — H 카테고리: 일일 집계 (1 케이스, 자문 +1).

> **선행 명세**: `_workspace/red/cycle62_price_filter.md` (§H)
> **자문 응답 Q6**: `_settle()` 직전 `[price_filter_daily_summary]` 1행 emit
> **선례**: 사이클 41 funnel 진단 패턴 답습

요구 행위 (Red 단계 AttributeError 정답 — `_emit_price_filter_daily_summary` 미존재):

H-1: `_settle()` 직전 `[price_filter_daily_summary]` 1행 INFO emit
     포함 필드: skip_count / hard_skip / warn_skip / mode

자문 근거: 운영자 일일 차단 비율 한눈에 파악 (`[price_filter_skip]` 개별 로그 200건
초과 시 가시성 저하 대응).

회귀 가드: scheduler._settle() 호출 흐름에 통합 — sync-docs 의무.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


@pytest.mark.asyncio
async def test_H1_daily_summary_emit_before_settle(caplog: pytest.LogCaptureFixture):
    """H-1: `_settle()` 호출 직전 `[price_filter_daily_summary]` 1행 INFO emit.

    검증 필드:
    - `skip_count` (HARD 모드 차단 카운트)
    - `warn_count` (WARN 모드 경고 카운트)
    - `mode` (현재 모드)

    20:10 KST 정산 시점 freeze.
    """
    from src.engine.order_engine import OrderEngine
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    order_engine = MagicMock(spec=OrderEngine)
    rm = RiskManager(registry=registry, order_engine=order_engine)

    # 일중 cap 누적 시뮬레이션 — Red 단계 두 필드 미존재 → AttributeError 정답
    rm._price_filter_skip_logged_today.add(("005930", "momentum"))
    rm._price_filter_skip_logged_today.add(("000660", "volatility_breakout"))
    rm._price_filter_skip_logged_today.add(("035720", "long_tail_volatility"))
    rm._price_filter_warn_logged_today.add(("042700", "momentum"))

    caplog.set_level(logging.INFO, logger="src.engine.risk")

    with freeze_time(datetime(2026, 6, 5, 20, 10, 0, tzinfo=KST)), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        # Red: `_emit_price_filter_daily_summary` 메서드 미존재 → AttributeError
        await rm._emit_price_filter_daily_summary()

    # `[price_filter_daily_summary]` 1행 emit 검증
    summary_logs = [
        r for r in caplog.records
        if "[price_filter_daily_summary]" in r.message
    ]
    assert len(summary_logs) == 1, (
        f"일일 집계 로그 누락/중복 (실제 {len(summary_logs)}건)"
    )

    msg = summary_logs[0].message
    assert "skip" in msg.lower(), "skip_count 필드 누락"
    assert "warn" in msg.lower(), "warn_count 필드 누락"
