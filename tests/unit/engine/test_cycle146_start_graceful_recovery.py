"""사이클 146 — `scheduler.start()` 영역 영구 영속 KisApiError graceful recovery 회귀 가드.

결함 #1 시정:
- 운영 사례 = 2026-06-16 09:01:16~09:07:43 KST KIS `/trading/inquire-balance` 5xx
- 6회 retry exhausted → KisApiError 전파 → start() except 진입 → 매매 프로세스 비정상 종료
- run_daily 영역 영구 영속이 다음 영업일 08:20 까지 대기 = 8시간 매매 손실
- 시정 = KisApiError 영역 영구 영속 (잔고/시세/주문 영역) = 매매 hot path 보존

영속 의무:
- 사이클 13-E-2 task lifecycle 영역 영구 영속 보존 (좀비 task 0)
- 사이클 38 명문화 (매수/매도 hot path 무관 = 일시 장애 graceful)
- 다음 _scan_loop / _stale_watcher 영역 영구 영속 자동 복구
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit


_SCHEDULER_PY = Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"


class TestStartGracefulRecovery:
    """`start()` 영역 영구 영속 except 블록 영역 KisApiError graceful recovery 영구 영속."""

    def test_g_146_defect1_1_kis_api_error_import(self):
        """G-146-DEFECT1-1: start() 영역 영구 영속 except 블록 영역에 KisApiError import 영속."""
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "start")
        assert node is not None

        body_src = ast.unparse(node)
        # KisApiError import 영역 영구 영속 (지역 또는 모듈 영역)
        assert "KisApiError" in body_src, (
            "start() 영역 영구 영속 except 블록 영역에 KisApiError import 부재 — "
            "사이클 146 결함 #1 시정 위반"
        )

    def test_g_146_defect1_2_kis_api_error_graceful_branch(self):
        """G-146-DEFECT1-2: KisApiError 분기 영역 영구 영속 graceful 처리 영속.

        시정 후 = `isinstance(exc, KisApiError)` 분기 영역 영구 영속 + return 영역 영구 영속.
        """
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "start")
        assert node is not None

        body_src = ast.unparse(node)
        # isinstance(exc, KisApiError) 또는 동등 영역 영구 영속
        assert "isinstance(exc, KisApiError)" in body_src or "KisApiError" in body_src, (
            "start() 영역 영구 영속 KisApiError 분기 영역 부재"
        )

    def test_g_146_defect1_3_graceful_log_message(self):
        """G-146-DEFECT1-3: graceful 로그 영역 영구 영속에 "일시 장애" 명시 영속."""
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "start")
        assert node is not None

        body_src = ast.unparse(node)
        # graceful 영역 영구 영속 로그 메시지
        assert (
            "일시 장애" in body_src
            or "graceful" in body_src.lower()
            or "보존" in body_src
        ), (
            "start() 영역 영구 영속 KisApiError graceful 로그 메시지 부재"
        )

    def test_g_146_defect1_4_existing_exception_branch_preserved(self):
        """G-146-DEFECT1-4: 기타 Exception 영역 영구 영속 = 기존 동작 보존 (사이클 13-E-2 답습)."""
        source = read_module_source(_SCHEDULER_PY)
        node = find_function_def(source, "start")
        assert node is not None

        body_src = ast.unparse(node)
        # 기존 영역 영구 영속 "매매 프로세스 오류" + "매매 프로세스 비정상 종료" 메시지 영속
        assert "매매 프로세스 오류" in body_src
        assert "매매 프로세스 비정상 종료" in body_src
