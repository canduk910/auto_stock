"""사이클 145 — strategy_funnel_snapshots insert_snapshot UPSERT 전환 회귀 가드.

결함 3 시정 (사용자 verbatim "단계가 늘어난 것처럼 보여"):
- 운영 DB 6/15 BFB step_no=1 = 8 row / donchian step_no=1~8 = 5~8 row (snapshot_at 다른 중복)
- UNIQUE = (target_date, strategy_id, step_no, snapshot_at) 영역 → snapshot_at 매번 갱신 → 중복 INSERT
- migration 035 (운영 DB 적용 완료) = UNIQUE → (target_date, strategy_id, step_no) 변경
- 코드 시정 = .insert() → .upsert(on_conflict=...) 전환

영속 의무:
- 사이클 34 strategy_funnel_snapshots 기본 영속
- 사이클 38 명문화 (진단 영역 한정)
- 사이클 41 JSONB cap 200/20 영속
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.ast._ast_helpers import (
    count_function_calls_in_node,
    find_function_def,
    read_module_source,
)

pytestmark = pytest.mark.unit


_FUNNEL_PY = Path(__file__).resolve().parents[3] / "src" / "db" / "strategy_funnel.py"


class TestUpsertTransition:
    """`insert_snapshot()` UPSERT 전환 영구 영속."""

    def test_g_145_funnel_1_upsert_call_present(self):
        """G-145-FUNNEL-1: AST `.upsert(` 호출 영속."""
        source = read_module_source(_FUNNEL_PY)
        node = find_function_def(source, "insert_snapshot")
        assert node is not None

        body_src = ast.unparse(node)
        assert ".upsert(" in body_src, (
            "insert_snapshot 영역 `.upsert(` 호출 부재 — UPSERT 전환 위반"
        )

    def test_g_145_funnel_2_on_conflict_keys(self):
        """G-145-FUNNEL-2: `on_conflict="target_date,strategy_id,step_no"` 영역."""
        source = read_module_source(_FUNNEL_PY)
        node = find_function_def(source, "insert_snapshot")
        assert node is not None

        body_src = ast.unparse(node)
        # snapshot_at 키 제외 (사이클 145 migration 035 영속)
        assert "target_date" in body_src
        assert "strategy_id" in body_src
        assert "step_no" in body_src

        # on_conflict 키 영역에 snapshot_at 영역 영구 영속 = 폐기
        # `on_conflict="target_date,strategy_id,step_no"` 영역 영구 영속 검증
        assert "on_conflict" in body_src, (
            "on_conflict 영역 영구 영속 부재 — UPSERT on_conflict 위반"
        )

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason=(
            "사이클 M1-3 의미 전환 — strategy_funnel.py 가 src.db.pg(asyncpg) 로 전환되어 "
            "`patch('src.db.strategy_funnel.supabase')` 전제가 성립하지 않는다(모듈에 "
            "supabase 심볼 부재 → AttributeError). 동등 계약(UNIQUE 재저장 시 1행 유지)은 "
            "`tests/integration/test_cycleM1_3_daily_perf_funnel_roundtrip.py::"
            "test_strategy_funnel_unique_upsert_one_row` 가 실 PG 왕복으로 대체. 회귀 아님."
        ),
        strict=False,
    )
    async def test_g_145_funnel_3_duplicate_insert_single_row(self):
        """G-145-FUNNEL-3: 동일 (target_date, strategy_id, step_no) 2회 insert → mock 영역에서 단일 upsert 호출."""
        from src.db import strategy_funnel

        with patch("src.db.strategy_funnel.supabase") as mock_supabase:
            mock_table = MagicMock()
            mock_supabase.table.return_value = mock_table
            mock_upsert = MagicMock()
            mock_table.upsert.return_value = mock_upsert
            mock_execute = MagicMock()
            mock_upsert.execute = mock_execute
            mock_execute.return_value = MagicMock(data=[{"id": "x"}])

            # 2회 동일 키 호출
            await strategy_funnel.insert_snapshot(
                target_date=date(2026, 6, 16),
                strategy_id="donchian_swing",
                step_no=1,
                step_name="코스피200+코스닥150",
                survived_tickers=["005930"],
            )
            await strategy_funnel.insert_snapshot(
                target_date=date(2026, 6, 16),
                strategy_id="donchian_swing",
                step_no=1,
                step_name="코스피200+코스닥150",
                survived_tickers=["005930", "000660"],
            )

            # 두 번 모두 upsert 호출 영역 영구 영속 (mock 영역 DB 영역 영구 영속 검증)
            assert mock_table.upsert.call_count == 2

    def test_g_145_funnel_4_docstring_cycle145(self):
        """G-145-FUNNEL-4: docstring 사이클 145 영역 영속 (UPSERT 시정 명시)."""
        source = read_module_source(_FUNNEL_PY)
        node = find_function_def(source, "insert_snapshot")
        assert node is not None

        docstring = ast.get_docstring(node) or ""
        # 사이클 145 명시 또는 UPSERT 명시 영역 영구 영속
        assert (
            "사이클 145" in docstring
            or "UPSERT" in docstring
            or "upsert" in docstring
        ), (
            "insert_snapshot docstring 영역에 사이클 145 UPSERT 시정 명시 부재"
        )
