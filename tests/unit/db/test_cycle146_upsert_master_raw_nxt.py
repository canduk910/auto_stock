"""사이클 146 — `upsert_master_raw` 영역 영구 영속 nxt_tradable NOT NULL 위반 영구 차단 회귀 가드.

결함 #2 시정:
- 운영 사례 = 2026-06-16 09:09:04~09:09:49 KST 45초간 623건 폭주
- 신규 ticker (900xxx ETN / 950xxx 외국기업 / 490xxx 신규 상장) 영역 영구 영속
- `null value in column "nxt_tradable" of relation "stock_master"` NOT NULL 위반
- 근본 원인 = `upsert_master_raw` 영역 payload 영역 영구 영속에 `nxt_tradable` 부재
- 메인 세션 hotfix (DEFAULT FALSE) + 사이클 146 코드 이중 안전망

영속 의무:
- 사이클 81 G-AST1 영구 강화 (보수적 폴백 = FALSE = NXT 매수 차단)
- 사이클 32 R4 universe guard 답습 (보수적 안전 영역 영구 영속)
- 사이클 144 영역 영구 영속 16:10 task `inquire_stock_basics` 영역 영구 영속 다음 발화 시 정확한 값 복구
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit


_STOCK_MASTER_PY = Path(__file__).resolve().parents[3] / "src" / "db" / "stock_master.py"


class TestUpsertMasterRawNxtTradable:
    """`upsert_master_raw` 영역 영구 영속 신규 ticker NOT NULL 위반 영구 차단."""

    def test_g_146_defect2_1_payload_includes_nxt_tradable(self):
        """G-146-DEFECT2-1: payload 영역 영구 영속에 `nxt_tradable` 키 영속.

        시정 후 = INSERT 시 명시적 False (DB DEFAULT 이중 안전망).
        """
        source = read_module_source(_STOCK_MASTER_PY)
        node = find_function_def(source, "upsert_master_raw")
        assert node is not None

        body_src = ast.unparse(node)
        # payload 영역 영구 영속에 nxt_tradable 키 영속
        assert "nxt_tradable" in body_src, (
            "upsert_master_raw 영역 영구 영속 payload 영역에 nxt_tradable 키 부재 — "
            "신규 ticker NOT NULL 위반 영구 차단 위반"
        )

    def test_g_146_defect2_2_nxt_tradable_value_false(self):
        """G-146-DEFECT2-2: nxt_tradable 값 = False (보수적 폴백).

        사이클 M2b — asyncpg 전환으로 dict 리터럴 payload → 위치 인자 바인딩.
        SQL INSERT 컬럼 목록에 nxt_tradable 포함 + 본문에 `False` 바인딩 상수 존속.
        """
        source = read_module_source(_STOCK_MASTER_PY)
        node = find_function_def(source, "upsert_master_raw")
        assert node is not None

        body_src = ast.unparse(node)
        # asyncpg SQL 컬럼 목록에 nxt_tradable + 위치 인자 False 상수 존속.
        assert "nxt_tradable" in body_src, (
            "upsert_master_raw SQL 에 nxt_tradable 컬럼 부재 — 신규 ticker NOT NULL 위반 차단 위반"
        )
        assert "False" in body_src, (
            "upsert_master_raw 에 nxt_tradable=False 보수적 폴백 상수 부재 (사이클 81 G-AST1 안전)"
        )

    @pytest.mark.asyncio
    async def test_g_146_defect2_3_payload_structure_with_supabase_mock(self):
        """G-146-DEFECT2-3: 실제 호출 시 SQL/바인딩에 4 키 영속 (사이클 M2b — pg.execute)."""
        from src.db import stock_master

        with patch.object(stock_master, "pg", create=True) as pg_mod:
            pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
            await stock_master.upsert_master_raw("900100", {"prdt_abrv_name": "TEST"})

        sql = pg_mod.execute.await_args.args[0]
        args = pg_mod.execute.await_args.args[1:]
        # INSERT 컬럼 목록에 4 키 영속
        for col in ("ticker", "master_raw", "master_raw_updated_at", "nxt_tradable"):
            assert col in sql, f"SQL INSERT 컬럼 목록에 {col} 부재"
        # ticker 바인딩 + nxt_tradable=False 보수적 폴백 바인딩
        assert "900100" in args, "ticker 바인딩 부재"
        assert False in args, (
            "nxt_tradable=False 보수적 폴백 바인딩 부재 (신규 ticker NOT NULL 위반 차단)"
        )

    def test_g_146_defect2_4_docstring_mentions_cycle146(self):
        """G-146-DEFECT2-4: docstring 영역 영구 영속 사이클 146 + 결함 #2 명시."""
        source = read_module_source(_STOCK_MASTER_PY)
        node = find_function_def(source, "upsert_master_raw")
        assert node is not None

        docstring = ast.get_docstring(node) or ""
        assert "사이클 146" in docstring, "docstring 영역 영구 영속 사이클 146 명시 부재"
        assert "결함" in docstring or "nxt_tradable" in docstring, (
            "docstring 영역 영구 영속 결함 #2 영역 또는 nxt_tradable 명시 부재"
        )
