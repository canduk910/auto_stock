"""사이클 171 — strategy_funnel_snapshots is_provisional 잠정 플래그 회귀 가드.

배경 (자문 cycle171_master_funnel_timing_redesign.md 의제 4 우선순위 2):
- 16:20 저녁 잠정 funnel 캡처 (전일 마스터 + 16:10 basics 기준) → 운영자 밤 후보 확인.
- is_provisional=True = 잠정 / False = 09:30 자동 + 수동 trigger (확정).
- migration 040 운영 DB 적용 완료 (is_provisional BOOLEAN NOT NULL DEFAULT FALSE).

회귀 가드:
- G-171-DB-1: insert_snapshot is_provisional 인자 존재 + default False (회귀 보존)
- G-171-DB-2: is_provisional=True payload 동행
- G-171-DB-3: 미지정 시 payload is_provisional=False (기존 호출자 회귀 0)
- G-171-DB-4: migration 040 파일 존재 + is_provisional 컬럼 정의
"""

from __future__ import annotations

import ast
import inspect
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit


_FUNNEL_PY = Path(__file__).resolve().parents[3] / "src" / "db" / "strategy_funnel.py"
_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase"
    / "migrations"
    / "040_funnel_provisional.sql"
)


def _capture_upsert_payload(mock_supabase) -> dict:
    """mock supabase.table().upsert(payload) 의 payload 추출."""
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_upsert = MagicMock()
    mock_table.upsert.return_value = mock_upsert
    mock_upsert.execute.return_value = MagicMock(data=[{"id": "x"}])
    return mock_table


class TestInsertSnapshotProvisional:
    """insert_snapshot is_provisional 인자 영속."""

    def test_g_171_db_1_param_exists_default_false(self):
        """G-171-DB-1: is_provisional 인자 존재 + default False."""
        from src.db.strategy_funnel import insert_snapshot

        sig = inspect.signature(insert_snapshot)
        assert "is_provisional" in sig.parameters, (
            "insert_snapshot is_provisional 인자 부재 (사이클 171)"
        )
        param = sig.parameters["is_provisional"]
        assert param.default is False, (
            f"is_provisional default = False 회귀 보존 의무 (실측 {param.default})"
        )

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason=(
            "사이클 M1-3 의미 전환 — strategy_funnel.py 가 src.db.pg(asyncpg) 로 전환되어 "
            "`patch('src.db.strategy_funnel.supabase')` 전제가 성립하지 않는다(모듈에 "
            "supabase 심볼 부재 → AttributeError). 동등 계약(is_provisional=True 바인딩)은 "
            "`tests/unit/db/test_cycleM1_3_strategy_funnel_pg.py::"
            "test_insert_snapshot_uses_pg_upsert_triple_conflict` 가 pg mock 기반으로 대체. "
            "회귀 아님."
        ),
        strict=False,
    )
    async def test_g_171_db_2_provisional_true_in_payload(self):
        """G-171-DB-2: is_provisional=True → upsert payload 동행."""
        from src.db import strategy_funnel

        with patch("src.db.strategy_funnel.supabase") as mock_supabase:
            mock_table = _capture_upsert_payload(mock_supabase)
            await strategy_funnel.insert_snapshot(
                target_date=date(2026, 6, 22),
                strategy_id="donchian_swing",
                step_no=1,
                step_name="코스피200+코스닥150",
                survived_tickers=["005930"],
                is_provisional=True,
            )
            payload = mock_table.upsert.call_args.args[0]
            assert payload.get("is_provisional") is True, (
                f"is_provisional=True payload 누락 (실측 {payload.get('is_provisional')})"
            )

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason=(
            "사이클 M1-3 의미 전환 — strategy_funnel.py 가 src.db.pg(asyncpg) 로 전환되어 "
            "`patch('src.db.strategy_funnel.supabase')` 전제가 성립하지 않는다(모듈에 "
            "supabase 심볼 부재 → AttributeError). 동등 계약(기본값 is_provisional=False)은 "
            "`tests/unit/db/test_cycleM1_3_strategy_funnel_pg.py` (G-171-DB-1 signature 검사는 "
            "본 파일 test_g_171_db_1 로 계속 유효) 가 대체. 회귀 아님."
        ),
        strict=False,
    )
    async def test_g_171_db_3_default_false_in_payload(self):
        """G-171-DB-3: 미지정 시 payload is_provisional=False (기존 호출자 회귀 0)."""
        from src.db import strategy_funnel

        with patch("src.db.strategy_funnel.supabase") as mock_supabase:
            mock_table = _capture_upsert_payload(mock_supabase)
            await strategy_funnel.insert_snapshot(
                target_date=date(2026, 6, 22),
                strategy_id="momentum",
                step_no=99,
                step_name="최종 prepared",
                survived_tickers=["000660"],
            )
            payload = mock_table.upsert.call_args.args[0]
            assert payload.get("is_provisional") is False, (
                f"미지정 시 is_provisional=False 의무 (실측 {payload.get('is_provisional')})"
            )

    def test_g_171_db_4_migration_file(self):
        """G-171-DB-4: migration 040 파일 + is_provisional 컬럼 정의."""
        assert _MIGRATION.exists(), "migration 040_funnel_provisional.sql 부재"
        sql = _MIGRATION.read_text(encoding="utf-8")
        low = sql.lower()
        assert "is_provisional" in low
        assert "boolean" in low
        assert "default false" in low
        assert "if not exists" in low, "additive ADD COLUMN IF NOT EXISTS 의무"
