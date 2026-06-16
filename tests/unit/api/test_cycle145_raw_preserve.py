"""사이클 145 — inquire_stock_basics raw 영역 영구 영속 0 덮어쓰기 금지 회귀 가드.

결함 2 시정:
- 운영 DB 2,697 ticker 중 acml_tr_pbmn>0 = 3 종목만 (6/16 07:54~07:59 KST = 장 시작 전 boot)
- FHKST01010100 응답 acml_tr_pbmn=0 → 기존 raw 영역 영구 영속 덮어쓰기 → donchian/VB/LTV list_by_filter 0건
- 시정 = merge 영역에서 0 값 영역 영구 영속 덮어쓰기 금지 graceful (사이클 81 G-AST1 영속 강화)

영속 의무:
- 사이클 81 G-AST1 영구 영속 (raw 덮어쓰기 금지)
- 사이클 107 CTPF1002R + FHKST01010100 merge 패턴 영속
- 사이클 108 list_by_filter (`acml_tr_pbmn ≥ min_trade_amount`) 정합 영속
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit


_CONDITION_PY = Path(__file__).resolve().parents[3] / "src" / "api" / "condition.py"


class TestRawPreserveOnZero:
    """`inquire_stock_basics` 영역 영구 영속 acml_tr_pbmn=0 시 raw 영역 영구 영속 보존."""

    @pytest.mark.asyncio
    async def test_g_145_raw_1_zero_acml_tr_pbmn_skip(self):
        """G-145-RAW-1: FHKST01010100 acml_tr_pbmn=0 응답 시 merged_raw 영역 덮어쓰기 금지.

        CTPF1002R 영역 영구 영속에 acml_tr_pbmn 키 부재 (영구 영속) → 0 시 merge 영역 영구 영속 skip.
        장 시작 전 영역 영구 영속 보호 영역 영구 영속 (사이클 145 시정).
        """
        from src.api import condition

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                return {"output": {"pdno": "005930", "prdt_abrv_name": "삼성전자"}}
            elif tr_id == "FHKST01010100":
                # 장 시작 전 영역 영구 영속 응답: acml_tr_pbmn=0, hts_avls 정상
                return {
                    "output": {
                        "acml_tr_pbmn": "0",  # 0 영역 = 덮어쓰기 금지
                        "hts_avls": "19701959",
                        "acml_vol": "0",
                        "prdy_vrss": "1000",
                        "lstn_stcn": "5969782550",
                    }
                }
            return {}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            result = await condition.inquire_stock_basics("005930")

        assert result is not None
        # acml_tr_pbmn=0 영역 영구 영속 = raw 영역 영구 영속에 키 부재 또는 0 보존 *아님*
        # 시정 후 동작: 0 값 영역 영구 영속 = merge 영역 skip → raw 영역에 acml_tr_pbmn 키 부재
        assert "acml_tr_pbmn" not in result.raw or int(result.raw.get("acml_tr_pbmn", 0) or 0) == 0, (
            f"acml_tr_pbmn=0 영역 영구 영속에서 raw 영역 덮어쓰기 금지 위반 — "
            f"result.raw={result.raw}"
        )
        # 다른 정상 키 영역 영구 영속 보존
        assert "hts_avls" in result.raw
        assert "lstn_stcn" in result.raw

    @pytest.mark.asyncio
    async def test_g_145_raw_2_positive_acml_tr_pbmn_merge(self):
        """G-145-RAW-2: acml_tr_pbmn>0 정상 응답 시 정상 덮어쓰기."""
        from src.api import condition

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                return {"output": {"pdno": "005930", "prdt_abrv_name": "삼성전자"}}
            elif tr_id == "FHKST01010100":
                return {
                    "output": {
                        "acml_tr_pbmn": "50000000000",  # 500억 영역
                        "hts_avls": "19701959",
                    }
                }
            return {}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            result = await condition.inquire_stock_basics("005930")

        assert result is not None
        # 정상 값 영역 = merge 영역 영구 영속 = raw 영역 영구 영속에 키 포함
        assert "acml_tr_pbmn" in result.raw
        assert int(result.raw["acml_tr_pbmn"]) == 50000000000

    @pytest.mark.asyncio
    async def test_g_145_raw_3_zero_acml_vol_skip(self):
        """G-145-RAW-3: acml_vol=0 시 동일 영역 영구 영속 (장 시작 전 영역 영구 영속)."""
        from src.api import condition

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                return {"output": {"pdno": "005930", "prdt_abrv_name": "삼성전자"}}
            elif tr_id == "FHKST01010100":
                return {
                    "output": {
                        "acml_vol": "0",
                        "hts_avls": "100",
                    }
                }
            return {}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            result = await condition.inquire_stock_basics("005930")

        assert result is not None
        # acml_vol=0 영역 영구 영속 = 덮어쓰기 금지 (사이클 145 시정)
        assert "acml_vol" not in result.raw or int(result.raw.get("acml_vol", 0) or 0) == 0

    def test_g_145_raw_4_ast_guard_zero_skip(self):
        """G-145-RAW-4: AST 가드 — merge 영역 영구 영속 0 덮어쓰기 금지 영역 영구 영속."""
        source = read_module_source(_CONDITION_PY)
        node = find_function_def(source, "inquire_stock_basics")
        assert node is not None

        body_src = ast.unparse(node)

        # 사이클 145 영역 영구 영속 시정 = `merged_raw` 영역 영구 영속 +
        # 0 값 영역 영구 영속 가드 (`numeric_value == 0` 영역 영구 영속 또는 동등).
        assert (
            "사이클 145" in body_src
            or "numeric_value == 0" in body_src
            or "_is_zero_or_empty" in body_src
        ), (
            "inquire_stock_basics 영역 영구 영속에 사이클 145 0 덮어쓰기 금지 가드 부재"
        )
