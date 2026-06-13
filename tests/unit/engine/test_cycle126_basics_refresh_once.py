"""사이클 126 영역 3 — _stock_master_basics_refresh_once 회귀 가드.

KIS CTPF1002R 매스 보강 task — KRX 1차 폴백의 NXT/정지/관리종목
하드코딩 False 결함 시정.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_g_basics1_calls_inquire_and_upsert():
    """G-BASICS1: 각 ticker 마다 inquire_stock_basics + upsert_one 호출."""
    from src.engine import scanner

    fake_basics_obj = type("Basics", (), {})()

    async def fake_list_all(limit=100, offset=0):
        if offset == 0:
            return [{"ticker": "005930"}, {"ticker": "000660"}]
        return []

    inquire_mock = AsyncMock(return_value=fake_basics_obj)
    upsert_mock = AsyncMock(return_value=None)

    with patch("src.db.stock_master.list_all", side_effect=fake_list_all), \
         patch("src.api.condition.inquire_stock_basics", inquire_mock), \
         patch("src.db.stock_master.upsert_one", upsert_mock):
        summary = await scanner._stock_master_basics_refresh_once()

    assert summary["total"] == 2
    assert summary["updated"] == 2
    assert inquire_mock.await_count == 2
    assert upsert_mock.await_count == 2


@pytest.mark.asyncio
async def test_g_basics2_rate_limit_sleep_between_tickers():
    """G-BASICS2: ticker 사이에 50ms Rate Limit sleep (사이클 17 KIS LMS chain 영속)."""
    from src.engine import scanner

    fake_basics_obj = type("Basics", (), {})()

    async def fake_list_all(limit=100, offset=0):
        if offset == 0:
            return [{"ticker": "005930"}, {"ticker": "000660"}, {"ticker": "035720"}]
        return []

    sleep_mock = AsyncMock(return_value=None)

    with patch("src.db.stock_master.list_all", side_effect=fake_list_all), \
         patch("src.api.condition.inquire_stock_basics", AsyncMock(return_value=fake_basics_obj)), \
         patch("src.db.stock_master.upsert_one", AsyncMock(return_value=None)), \
         patch.object(scanner._asyncio, "sleep", sleep_mock):
        await scanner._stock_master_basics_refresh_once()

    # 3 ticker 모두 50ms sleep
    sleep_calls = [c for c in sleep_mock.await_args_list if c.args and c.args[0] == 0.05]
    assert len(sleep_calls) >= 3, (
        f"50ms Rate Limit sleep 호출 부족: {len(sleep_calls)} (기대 ≥3)"
    )


@pytest.mark.asyncio
async def test_g_basics3_graceful_on_kis_rejection():
    """G-BASICS3: KIS 거부 시 graceful + failed 카운터 증가 + 다음 ticker 진행."""
    from src.engine import scanner

    fake_basics_obj = type("Basics", (), {})()

    async def fake_list_all(limit=100, offset=0):
        if offset == 0:
            return [{"ticker": "005930"}, {"ticker": "000660"}]
        return []

    call_count = {"n": 0}

    async def fake_inquire(ticker: str):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("KIS 거부 시뮬레이션")
        return fake_basics_obj

    with patch("src.db.stock_master.list_all", side_effect=fake_list_all), \
         patch("src.api.condition.inquire_stock_basics", fake_inquire), \
         patch("src.db.stock_master.upsert_one", AsyncMock(return_value=None)):
        summary = await scanner._stock_master_basics_refresh_once()

    # 첫 ticker 실패 + 두 번째 성공
    assert summary["failed"] == 1
    assert summary["updated"] == 1


@pytest.mark.asyncio
async def test_g_basics4_emit_summary(caplog):
    """G-BASICS4: [stock_master_basics_refresh_summary] 1행 INFO emit."""
    from src.engine import scanner
    import logging

    fake_basics_obj = type("Basics", (), {})()

    async def fake_list_all(limit=100, offset=0):
        if offset == 0:
            return [{"ticker": "005930"}]
        return []

    with caplog.at_level(logging.INFO, logger="src.engine.scanner"):
        with patch("src.db.stock_master.list_all", side_effect=fake_list_all), \
             patch("src.api.condition.inquire_stock_basics", AsyncMock(return_value=fake_basics_obj)), \
             patch("src.db.stock_master.upsert_one", AsyncMock(return_value=None)):
            await scanner._stock_master_basics_refresh_once()

    summaries = [r for r in caplog.records if "[stock_master_basics_refresh_summary]" in r.message]
    assert len(summaries) >= 1, "[stock_master_basics_refresh_summary] emit 누락"
    begins = [r for r in caplog.records if "[stock_master_basics_refresh_begin]" in r.message]
    assert len(begins) >= 1, "[stock_master_basics_refresh_begin] 진단 로그 누락"


@pytest.mark.asyncio
async def test_g_diag1_daily_load_emits_begin_log(caplog):
    """G-DIAG1: _stock_master_daily_load_once 함수 진입 시 [stock_master_daily_load_begin] emit."""
    from src.engine import scanner
    import logging

    async def fake_list_all(limit=100, offset=0):
        return []  # 빈 영역 시뮬레이션 (begin emit 후 즉시 return)

    with caplog.at_level(logging.INFO, logger="src.engine.scanner"):
        with patch("src.db.stock_master.list_all", side_effect=fake_list_all):
            summary = await scanner._stock_master_daily_load_once()

    begins = [r for r in caplog.records if "[stock_master_daily_load_begin]" in r.message]
    assert len(begins) >= 1, "[stock_master_daily_load_begin] 진단 로그 누락"
    assert "db_write_failures" in summary, (
        "사이클 126 db_write_failures 카운터 누락"
    )
