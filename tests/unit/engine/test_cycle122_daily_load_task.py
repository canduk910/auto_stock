"""사이클 122 (2026-06-12) — _stock_master_daily_load_once + task lifecycle 회귀 가드.

회귀 가드 매트릭스:
- G-SCAN1 (HIGH) — _stock_master_daily_load_once stock_master 전체 ticker 적재
- G-SCAN2 (HIGH) — 점진 적재 idempotency (max_bas_dd >= today → skip)
- G-SCAN3 (HIGH) — 백필 vs 증분 자동 분기 (count < 50 백필 / >= 50 증분)
- G-SCAN4 (MEDIUM) — Rate Limit 50ms sleep (사이클 83/91/97/107 답습)
- G-SCAN5 (MEDIUM) — graceful (KIS fetch 실패 시 다음 ticker 진행)
- G-SCHED1 (HIGH) — TIME_STOCK_MASTER_DAILY_LOAD = 16:00 KST
- G-SCHED2 (HIGH) — task cancel 목록에 _stock_master_daily_load_task 포함

영속 의무:
- 사이클 14 fetch_daily_candles 재사용
- 사이클 38 명문화 (scanner 매수 진입 전 영역)
- 사이클 79 G-AST2 task cancel 영속
- 사이클 88 G-REJECT graceful
- 사이클 106 lifecycle race 차단
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import scanner, scheduler, data_load_tasks

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# G-SCAN1 (HIGH) — _stock_master_daily_load_once 영역 호출 + summary 정합
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_scan1_load_once_iterates_stock_master():
    """stock_master 전체 ticker → 각 ticker 별 fetch_daily_candles + upsert_batch."""
    stock_master_rows = [
        {"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},
        {"ticker": "000660", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},
        {"ticker": "035420", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},
    ]
    mock_candles = [
        {"stck_bsop_date": "20260612", "stck_clpr": "71000",
         "stck_oprc": "70000", "stck_hgpr": "71500", "stck_lwpr": "69500",
         "acml_vol": "12345678", "acml_tr_pbmn": "876543210000"},
    ]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),  # 신규 적재
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=0),  # 백필 모드
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=mock_candles),
    ) as mock_kis, patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ) as mock_upsert, patch(
        "asyncio.sleep", new=AsyncMock(),
    ):
        summary = await scanner._stock_master_daily_load_once()

    assert summary["total"] == 3
    assert summary["fetched"] == 3
    assert summary["upserted_rows"] == 3
    assert summary["failed"] == 0
    assert mock_kis.call_count == 3
    assert mock_upsert.call_count == 3


# ---------------------------------------------------------------------------
# G-SCAN2 (HIGH) — max_bas_dd >= today → skip (idempotency)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_scan2_skip_when_already_loaded_today():
    """오늘 이미 적재된 ticker 는 KIS 호출 skip (점진 적재 영구 영속)."""
    from src.db._kst import today_kst

    today = today_kst()
    stock_master_rows = [{"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=today),  # 이미 오늘 적재됨
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(),
    ) as mock_kis, patch(
        "asyncio.sleep", new=AsyncMock(),
    ):
        summary = await scanner._stock_master_daily_load_once()

    assert summary["skipped_fresh"] == 1
    assert summary["fetched"] == 0
    assert not mock_kis.called  # KIS 호출 0건 (idempotency)


# ---------------------------------------------------------------------------
# G-SCAN3 (HIGH) — 백필 vs 증분 자동 분기
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_scan3_backfill_when_count_below_threshold():
    """count < 50 → 백필 모드 (T-100일 호출)."""
    stock_master_rows = [{"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}]

    captured_days: list[int] = []

    async def capture_kis_call(ticker, days):
        captured_days.append(days)
        return [{"stck_bsop_date": "20260612", "stck_clpr": "71000"}]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=date(2026, 6, 1)),  # 11일 전
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=10),  # 10건 < 50 = 백필
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=capture_kis_call),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch(
        "asyncio.sleep", new=AsyncMock(),
    ):
        await scanner._stock_master_daily_load_once()

    assert captured_days == [100]  # 백필 = T-100일


@pytest.mark.asyncio
async def test_g_scan3_incremental_when_count_above_threshold():
    """count >= 50 → 증분 모드 (T-7일 호출)."""
    stock_master_rows = [{"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}]

    captured_days: list[int] = []

    async def capture_kis_call(ticker, days):
        captured_days.append(days)
        return [{"stck_bsop_date": "20260612", "stck_clpr": "71000"}]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=date(2026, 6, 10)),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=100),  # 100건 >= 50 = 증분
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=capture_kis_call),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch(
        "asyncio.sleep", new=AsyncMock(),
    ):
        await scanner._stock_master_daily_load_once()

    assert captured_days == [7]  # 증분 = T-7일


# ---------------------------------------------------------------------------
# G-SCAN4 (MEDIUM) — Rate Limit 50ms sleep (사이클 83/91/97/107 답습)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_scan4_rate_limit_50ms_per_ticker():
    """ticker 간 50ms sleep — KIS LMS chain 안전 마진."""
    stock_master_rows = [{"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}, {"ticker": "000660", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}]
    sleep_durations: list[float] = []

    async def capture_sleep(duration):
        sleep_durations.append(duration)

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=0),
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=[{"stck_bsop_date": "20260612", "stck_clpr": "71000"}]),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch(
        "asyncio.sleep", side_effect=capture_sleep,
    ):
        await scanner._stock_master_daily_load_once()

    # 2 ticker × 1 sleep/ticker = 2건 (모두 50ms)
    rate_limit_sleeps = [d for d in sleep_durations if d == 0.05]
    assert len(rate_limit_sleeps) == 2


# ---------------------------------------------------------------------------
# G-SCAN5 (MEDIUM) — KIS fetch 실패 시 graceful (다음 ticker 진행)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g_scan5_graceful_on_kis_failure():
    """KIS fetch_daily_candles 실패 시 다음 ticker 진행 — 사이클 88 G-REJECT."""
    stock_master_rows = [{"ticker": "005930", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}, {"ticker": "000660", "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}}]

    async def kis_side_effect(ticker, days):
        if ticker == "005930":
            raise RuntimeError("KIS rate limit")
        return [{"stck_bsop_date": "20260612", "stck_clpr": "71000"}]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=0),
    ), patch(
        "src.api.condition.fetch_daily_candles",
        side_effect=kis_side_effect,
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch(
        "asyncio.sleep", new=AsyncMock(),
    ):
        summary = await scanner._stock_master_daily_load_once()

    assert summary["failed"] == 1
    assert summary["fetched"] == 1  # 두 번째 ticker 는 성공


# ---------------------------------------------------------------------------
# G-SCHED1 (HIGH) — TIME_STOCK_MASTER_DAILY_LOAD = 16:00 KST
# ---------------------------------------------------------------------------
def test_g_sched1_time_constant_is_16_00():
    """TIME_STOCK_MASTER_DAILY_LOAD = time(16, 0) — KRX 메인 종료 30분 후 안전 마진."""
    assert scheduler.TIME_STOCK_MASTER_DAILY_LOAD == time(16, 0)


# ---------------------------------------------------------------------------
# G-SCHED2 (HIGH) — task cancel 목록 포함 (3 곳 모두)
# ---------------------------------------------------------------------------
def test_g_sched2_stock_master_daily_load_task_in_cancel_tuples():
    """stop() + run_daily.finally + start.finally 3 곳 모두 cancel 목록 포함."""
    src = inspect.getsource(scheduler)
    # _stock_master_daily_load_task 가 cancel 튜플 3 곳 모두 포함되었는지 정적 검증
    count = src.count('"_stock_master_daily_load_task"')
    assert count >= 3, (
        f"_stock_master_daily_load_task 가 cancel 튜플 3 곳 모두에 포함되어야 함. "
        f"실제 등장 횟수={count}"
    )


# ---------------------------------------------------------------------------
# G-SCHED3 (MEDIUM) — _stock_master_daily_load_task_loop 메서드 존재
# ---------------------------------------------------------------------------
def test_g_sched3_task_loop_method_exists():
    """_stock_master_daily_load_task_loop 메서드 존재 + start() 직후 즉시 1회 실행.

    사이클 134 의미 전환 (카드 #21 — refactor-review 권고 채택) — 사이클 66 K-2 패턴 답습:
    - Red 시점 (사이클 122) = facade 본체 `while self._running` + `초기 실행 완료` 인라인
    - Green 시점 (사이클 134) = `run_periodic_task_loop` 헬퍼 위임 + lifecycle 영역 헬퍼 흡수
    - 핵심 의도 보존: 메서드 영속 + _wait_until 정합 + 즉시 실행 + while 영속 (헬퍼 흡수).
    """
    sched = scheduler.TradingScheduler()
    assert hasattr(sched, "_stock_master_daily_load_task_loop")
    assert callable(sched._stock_master_daily_load_task_loop)

    # refactor-review B1 (2026-08-09) — 본체 data_load_tasks 위임 이관. wrapper(TIME_) + 본체(helper) 결합.
    src = inspect.getsource(sched._stock_master_daily_load_task_loop) + \
        inspect.getsource(data_load_tasks.stock_master_daily_load_task_loop)
    # _wait_until 인자 정합 영속 (facade 또는 헬퍼 인자 영역 영구 영속)
    assert "TIME_STOCK_MASTER_DAILY_LOAD" in src, (
        "TIME_STOCK_MASTER_DAILY_LOAD 인자 영속 부재 — facade 영속 의무 위반"
    )

    # 사이클 134 의미 전환 — 헬퍼 위임 OR 인라인 영역 영구 영속
    has_helper = "run_periodic_task_loop" in src
    has_inline = "while self._running" in src and ("초기 실행 완료" in src or "초기 실행 예외" in src)
    assert has_helper or has_inline, (
        "lifecycle race 차단 패턴 영속 부재 — "
        "Red 시점 (인라인) 또는 Green 시점 (헬퍼 위임) 영속 의무 위반"
    )

    if has_helper:
        # 헬퍼 영역 영구 영속에서 lifecycle 흡수 영속
        from pathlib import Path
        helper_src = Path("src/engine/task_loop_helper.py").read_text(encoding="utf-8")
        assert "while scheduler._running" in helper_src
        assert "초기 실행" in helper_src
