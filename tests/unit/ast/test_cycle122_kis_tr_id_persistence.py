"""사이클 122 (2026-06-12) — AST 영구 가드.

회귀 가드 매트릭스:
- G-AST1 — KIS TR_ID `FHKST03010100` 영속 (사이클 14 fetch_daily_candles 재사용)
- G-AST2 — DB schema 영속 (migration 033 + PK 복합 키 + 인덱스 2종)
- G-AST3 — lifecycle race 차단 패턴 영속 (start() 즉시 + while 루프)
- G-AST4 — stock_master_daily TABLE_NAME 영속

영속 의무:
- 사이클 78 G-AST1 — record_* 정의 모듈은 대응 flush_* 호출 사이트 ≥1
- 사이클 79 G-AST2 — task cancel 목록 영속
- 사이클 106 lifecycle race 차단 패턴
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from src.db import stock_master_daily
from src.engine import scheduler, stock_master_daily_metrics

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# G-AST1 — KIS TR_ID FHKST03010100 영속 (사이클 14 fetch_daily_candles 재사용)
# ---------------------------------------------------------------------------
def test_g_ast1_kis_tr_id_fhkst03010100_present():
    """fetch_daily_candles 영역에 FHKST03010100 영속 (silent 결함 영구 차단)."""
    from src.api import condition

    src = inspect.getsource(condition)
    assert "FHKST03010100" in src, (
        "KIS 일봉 TR_ID FHKST03010100 가 src/api/condition.py 에서 사라졌음. "
        "사이클 122 = 사이클 14 fetch_daily_candles 재사용 (신규 KIS API 도입 0건)"
    )


# ---------------------------------------------------------------------------
# G-AST2 — DB schema 영속 (migration 033)
# ---------------------------------------------------------------------------
def test_g_ast2_migration_033_exists():
    """migration 033_stock_master_daily.sql 영구 존재."""
    migration_path = (
        Path(__file__).parent.parent.parent.parent
        / "supabase" / "migrations" / "033_stock_master_daily.sql"
    )
    assert migration_path.exists(), (
        f"migration 033 영구 존재 의무: {migration_path}"
    )
    content = migration_path.read_text()
    # PK 복합 키 영속
    assert "PRIMARY KEY (ticker, bas_dd)" in content
    # 핵심 인덱스 2종 영속
    assert "idx_stock_master_daily_ticker_bas_dd" in content
    assert "idx_stock_master_daily_bas_dd" in content
    # CTPF1002R 정본 키 영속 (사이클 81 G-AST1 답습)
    assert "raw" in content and "JSONB" in content


def test_g_ast2_stock_master_daily_table_name_persistence():
    """stock_master_daily.TABLE_NAME 영속 (silent 결함 차단)."""
    assert stock_master_daily.TABLE_NAME == "stock_master_daily"


# ---------------------------------------------------------------------------
# G-AST3 — lifecycle race 차단 패턴 영속 (사이클 106 답습)
# ---------------------------------------------------------------------------
def test_g_ast3_lifecycle_race_pattern_persistence():
    """_stock_master_daily_load_task_loop 영역 = start() 직후 즉시 1회 + while 루프."""
    src = inspect.getsource(scheduler.TradingScheduler._stock_master_daily_load_task_loop)
    # while 루프 영속
    assert "while self._running" in src
    # _wait_until 정합
    assert "_wait_until(TIME_STOCK_MASTER_DAILY_LOAD)" in src
    # graceful (사이클 88 G-REJECT 영속)
    assert "asyncio.CancelledError" in src
    assert "logger.exception" in src
    # 사이클 106 lifecycle race 차단 — 즉시 실행 + while 루프 양쪽
    immediate_count = src.count("초기 실행")
    periodic_count = src.count("정기 실행")
    assert immediate_count >= 1, "사이클 106 답습 — 초기 실행 영역 영구 영속"
    assert periodic_count >= 1, "while 루프 정기 실행 영역 영구 영속"


# ---------------------------------------------------------------------------
# G-AST4 — record_/flush_ 페어링 영속 (사이클 78 G-AST1 답습)
# ---------------------------------------------------------------------------
def test_g_ast4_record_flush_pairing_persistence():
    """record_stock_master_daily_load + flush_stock_master_daily_load_collector 페어링."""
    assert hasattr(stock_master_daily_metrics, "record_stock_master_daily_load")
    assert hasattr(stock_master_daily_metrics, "flush_stock_master_daily_load_collector")

    # scheduler.py 가 flush 호출 의무 (사이클 78 G-AST1 답습)
    scheduler_src = inspect.getsource(scheduler)
    assert "flush_stock_master_daily_load_collector" in scheduler_src, (
        "사이클 78 G-AST1 영속: record_* 정의 모듈 = 대응 flush_* 호출 사이트 ≥1 의무"
    )
    assert "record_stock_master_daily_load" in scheduler_src
