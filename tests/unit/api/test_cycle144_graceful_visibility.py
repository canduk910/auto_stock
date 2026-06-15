"""사이클 144 영역 B — 카드 #27 graceful 가시화 강화 회귀 가드 (LOW).

사용자 결정: Q1=A 사이클 143 commit + push + Q2 = D+1 운영 실측 (자동) + 영역 B 카드 #27.

배경 (카드 #27 영역 영구 영속):
- src/api/condition.py::inquire_stock_basics (사이클 107) FHKST01010100 호출 실패 영역 silent fail
- src/engine/scanner.py::_stock_master_basics_refresh_once summary 영역에 graceful_failed 부재
- 사이클 129 OPSQ1002 SESSION FULL 영역 graceful 처리 영역 영구 영속 가시화 결핍

시정 영역:
- src/api/condition.py 모듈 전역 graceful_failed 카운터 영역 영구 영속 신규
- FHKST01010100 except 분기에 _record_graceful_failed 호출 영속
- scanner.py summary 영역 graceful_failed 필드 + emit 영역 영구 영속 갱신

영속 의무:
- 사이클 38 명문화 (logging 영역 한정)
- 사이클 88 G-REJECT graceful 영속 (영역 강화)
- 사이클 107 inquire_stock_basics merge 패턴 영속
- 매매 안전성 무영향 영속
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.ast._ast_helpers import (
    count_function_calls_in_node,
    find_function_def,
    read_module_source,
)

pytestmark = pytest.mark.unit


_CONDITION_PY = Path(__file__).resolve().parents[3] / "src" / "api" / "condition.py"
_SCANNER_PY = Path(__file__).resolve().parents[3] / "src" / "engine" / "scanner.py"


# =============================================================================
# G-144-COUNTER — graceful_failed 카운터 영역 영구 영속 (4 케이스)
# =============================================================================


class TestGracefulFailedCounter:
    """graceful_failed 카운터 영역 영구 영속 (모듈 전역)."""

    def test_g_144_counter_1_module_dict_exists(self):
        """G-144-COUNTER-1: `_graceful_failed_counter` 모듈 전역 dict 영속."""
        source = read_module_source(_CONDITION_PY)

        # 모듈 전역 영역 영구 영속 변수 영역 영구 영속 검출 (Annotated assignment 영역 영구 영속 또는 단순 assignment)
        assert "_graceful_failed_counter" in source, (
            "_graceful_failed_counter 모듈 전역 dict 부재 (카드 #27 graceful 가시화 영역 영구 영속 위반)"
        )

    @pytest.mark.asyncio
    async def test_g_144_counter_2_record_increments(self):
        """G-144-COUNTER-2: `_record_graceful_failed("fhkst01010100_failed")` 호출 → 카운터 증가."""
        from src.api import condition

        # reset 후 시작값 0
        condition.reset_graceful_failed_counts()
        snapshot_before = condition.get_graceful_failed_counts()
        assert snapshot_before.get("fhkst01010100_failed", 0) == 0

        # _record_graceful_failed 호출 영역 영구 영속
        await condition._record_graceful_failed("fhkst01010100_failed")
        snapshot_after = condition.get_graceful_failed_counts()
        assert snapshot_after.get("fhkst01010100_failed", 0) == 1, (
            f"_record_graceful_failed 호출 후 카운터 영역 영구 영속 미증가 — got {snapshot_after}"
        )

    def test_g_144_counter_3_get_snapshot_function(self):
        """G-144-COUNTER-3: `get_graceful_failed_counts()` 스냅샷 반환 영역 영구 영속."""
        from src.api import condition

        # 함수 영역 영구 영속 존재 검증
        assert hasattr(condition, "get_graceful_failed_counts"), (
            "get_graceful_failed_counts 함수 영역 영구 영속 부재"
        )

        snapshot = condition.get_graceful_failed_counts()
        assert isinstance(snapshot, dict), "get_graceful_failed_counts 영역 영구 영속 반환값 dict 영속 의무"
        assert "fhkst01010100_failed" in snapshot, (
            f"snapshot 영역 영구 영속 'fhkst01010100_failed' 키 영역 영구 영속 부재 — got {snapshot}"
        )

    def test_g_144_counter_4_reset_function(self):
        """G-144-COUNTER-4: `reset_graceful_failed_counts()` 초기화 영역 영구 영속."""
        from src.api import condition

        assert hasattr(condition, "reset_graceful_failed_counts"), (
            "reset_graceful_failed_counts 함수 영역 영구 영속 부재"
        )

        # 임의로 값 증가 후 reset
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(condition._record_graceful_failed("fhkst01010100_failed"))
            loop.run_until_complete(condition._record_graceful_failed("fhkst01010100_failed"))
        finally:
            loop.close()

        condition.reset_graceful_failed_counts()
        snapshot = condition.get_graceful_failed_counts()
        assert snapshot.get("fhkst01010100_failed", 0) == 0, (
            f"reset 후 카운터 영역 영구 영속 미초기화 — got {snapshot}"
        )


# =============================================================================
# G-144-INTEGRATION — inquire_stock_basics 영역 영구 영속 (3 케이스)
# =============================================================================


class TestInquireStockBasicsIntegration:
    """inquire_stock_basics 영역 영구 영속 graceful_failed 카운터 동기화."""

    @pytest.mark.asyncio
    async def test_g_144_int_1_fhkst_failed_records_counter(self):
        """G-144-INT-1: FHKST01010100 호출 실패 → `_record_graceful_failed` 호출 영속.

        CTPF1002R 정상 + FHKST01010100 실패 (예외 raise) → 카운터 +1.
        """
        from src.api import condition

        condition.reset_graceful_failed_counts()

        # kis_get_quote mock — CTPF1002R 성공 + FHKST01010100 실패
        call_count = [0]

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            call_count[0] += 1
            if tr_id == "CTPF1002R":
                return {"output": {"pdno": "005930", "prdt_abrv_name": "삼성전자"}}
            elif tr_id == "FHKST01010100":
                raise RuntimeError("FHKST01010100 호출 실패")
            return {}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            result = await condition.inquire_stock_basics("005930")

        # CTPF 정상 → result 반환 영속
        assert result is not None
        # 카운터 영역 영구 영속 +1 영속
        snapshot = condition.get_graceful_failed_counts()
        assert snapshot.get("fhkst01010100_failed", 0) >= 1, (
            f"FHKST01010100 실패 후 _record_graceful_failed 호출 부재 — got {snapshot}"
        )

    @pytest.mark.asyncio
    async def test_g_144_int_2_both_succeed_no_counter_change(self):
        """G-144-INT-2: 양쪽 정상 → 카운터 변경 0."""
        from src.api import condition

        condition.reset_graceful_failed_counts()
        snapshot_before = condition.get_graceful_failed_counts()
        before_count = snapshot_before.get("fhkst01010100_failed", 0)

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                return {"output": {"pdno": "005930", "prdt_abrv_name": "삼성전자"}}
            elif tr_id == "FHKST01010100":
                return {"output": {"hts_avls": "100000"}}
            return {}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            await condition.inquire_stock_basics("005930")

        snapshot_after = condition.get_graceful_failed_counts()
        after_count = snapshot_after.get("fhkst01010100_failed", 0)
        assert after_count == before_count, (
            f"양쪽 정상 시 카운터 영역 영구 영속 변경 — before={before_count}, after={after_count}"
        )

    @pytest.mark.asyncio
    async def test_g_144_int_3_kis_error_records_counter(self):
        """G-144-INT-3: FHKST01010100 KisApiError → `_record_graceful_failed` 호출 영속."""
        from src.api import condition
        from src.api.base import KisApiError

        condition.reset_graceful_failed_counts()

        async def _mock_kis_get_quote(url, tr_id, params, **kwargs):
            if tr_id == "CTPF1002R":
                return {"output": {"pdno": "005930", "prdt_abrv_name": "삼성전자"}}
            elif tr_id == "FHKST01010100":
                raise KisApiError("OPSQ1002", "SESSION FULL")
            return {}

        with patch("src.api.condition.kis_get_quote", side_effect=_mock_kis_get_quote):
            result = await condition.inquire_stock_basics("005930")

        assert result is not None
        snapshot = condition.get_graceful_failed_counts()
        assert snapshot.get("fhkst01010100_failed", 0) >= 1, (
            f"KisApiError 영역 영구 영속 _record_graceful_failed 호출 부재 — got {snapshot}"
        )


# =============================================================================
# G-144-SUMMARY — scanner summary 영역 영구 영속 (2 케이스)
# =============================================================================


class TestScannerSummaryGracefulFailed:
    """scanner _stock_master_basics_refresh_once summary 영역 graceful_failed 필드 영속."""

    def test_g_144_summary_1_summary_includes_graceful_failed_key(self):
        """G-144-SUMMARY-1: summary 영역에 `graceful_failed` 키 영속."""
        source = read_module_source(_SCANNER_PY)
        node = find_function_def(source, "_stock_master_basics_refresh_once")
        assert node is not None

        body_src = ast.unparse(node)
        # summary["graceful_failed"] 영역 영구 영속 또는 graceful_failed 키 영역 영구 영속 영속
        assert "graceful_failed" in body_src, (
            "_stock_master_basics_refresh_once summary 영역에 graceful_failed 키 부재"
        )

    def test_g_144_summary_2_emit_includes_graceful_failed_field(self):
        """G-144-SUMMARY-2: summary emit 로그 영역 영구 영속 `graceful_failed` 필드 영속."""
        source = read_module_source(_SCANNER_PY)
        node = find_function_def(source, "_stock_master_basics_refresh_once")
        assert node is not None

        body_src = ast.unparse(node)
        # [stock_master_basics_refresh_summary] emit 영역 영구 영속 graceful_failed_fhkst 영역 영구 영속
        # 또는 graceful_failed_* prefix 영역 영구 영속
        assert (
            "graceful_failed_fhkst" in body_src
            or "graceful_failed=" in body_src
        ), (
            "summary emit 영역 영구 영속 graceful_failed 필드 부재 (운영 가시화 영역)"
        )


# =============================================================================
# G-144-AST — AST 영구 가드 (1 케이스)
# =============================================================================


class TestASTGuard:
    """`inquire_stock_basics` graceful 분기 `_record_graceful_failed` 호출 영속."""

    def test_g_144_ast_1_inquire_stock_basics_records_failed(self):
        """G-144-AST-1: `inquire_stock_basics` graceful 분기에 `_record_graceful_failed` 호출 영속."""
        source = read_module_source(_CONDITION_PY)
        node = find_function_def(source, "inquire_stock_basics")
        assert node is not None, "inquire_stock_basics 함수 정의 부재"

        # 함수 본체 영역 영구 영속 `_record_graceful_failed` 호출 ≥ 1건
        record_count = count_function_calls_in_node(node, "_record_graceful_failed")
        assert record_count >= 1, (
            f"inquire_stock_basics 영역 _record_graceful_failed 호출 {record_count}건, "
            f"≥ 1건 영속 의무 위반 (카드 #27 graceful 가시화 영역 영구 영속)"
        )
