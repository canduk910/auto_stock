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
from unittest.mock import MagicMock, patch

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
        """G-146-DEFECT2-2: nxt_tradable 값 영역 영구 영속 = False (보수적 폴백)."""
        source = read_module_source(_STOCK_MASTER_PY)
        node = find_function_def(source, "upsert_master_raw")
        assert node is not None

        body_src = ast.unparse(node)
        # nxt_tradable=False 또는 'nxt_tradable': False 영역 영구 영속
        assert "'nxt_tradable': False" in body_src or "\"nxt_tradable\": False" in body_src, (
            "upsert_master_raw 영역 영구 영속 nxt_tradable=False 영역 부재 — "
            "보수적 폴백 영역 영구 영속 위반 (사이클 81 G-AST1 안전 영구 영속)"
        )

    @pytest.mark.asyncio
    async def test_g_146_defect2_3_payload_structure_with_supabase_mock(self):
        """G-146-DEFECT2-3: 실제 호출 시 payload 영역 영구 영속에 4 키 영속 (mock)."""
        from src.db import stock_master

        with patch("src.db.stock_master.supabase") as mock_supabase:
            mock_table = MagicMock()
            mock_supabase.table.return_value = mock_table
            mock_upsert = MagicMock()
            mock_table.upsert.return_value = mock_upsert
            mock_upsert.execute = MagicMock(return_value=MagicMock(data=[]))

            await stock_master.upsert_master_raw("900100", {"prdt_abrv_name": "TEST"})

            # upsert 호출 영역 영구 영속 payload 검증
            call_args = mock_table.upsert.call_args
            payload = call_args.args[0]
            assert "ticker" in payload
            assert "master_raw" in payload
            assert "master_raw_updated_at" in payload
            assert "nxt_tradable" in payload, (
                f"payload 영역 영구 영속에 nxt_tradable 키 부재 — got keys: {list(payload.keys())}"
            )
            assert payload["nxt_tradable"] is False, (
                f"nxt_tradable 영역 영구 영속 보수적 폴백 위반 — got: {payload.get('nxt_tradable')}"
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
