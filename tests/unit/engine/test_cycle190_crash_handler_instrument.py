"""사이클 190 Red — `scheduler.start()` 크래시 핸들러 예외타입 계측.

결함 (2026-07-03 07:59 운영 실증):
- start() 외곽 except 의 크래시 핸들러(`logger.exception("매매 프로세스 오류")` +
  `write_log("ERROR", "매매 프로세스 비정상 종료")`) 가 예외 타입/메시지를 기록하지 않음.
- "매매 프로세스 오류"는 6/10~7/3 한 달간 8회 발생한 상습 크래시 클래스이나, 과거 건
  원인이 traceback 소실로 미확정 → DB 만으로 진단 불가.

Green 계약:
- `write_log("ERROR", "매매 프로세스 비정상 종료")` →
  `write_log("ERROR", f"매매 프로세스 비정상 종료: {type(exc).__name__}: {str(exc)[:150]}")`
  — 원인불명 재발 시 DB 만으로 즉시 진단.
- `logger.exception("매매 프로세스 오류")` 불변. KisApiError graceful 분기(사이클 146) /
  finally 흐름 변경 0.

케이스:
- H-1 (HIGH): 크래시 핸들러 write_log ERROR 메시지에 예외 타입명 + str(exc) 요약 포함
- H-2: KisApiError 분기(사이클 146) 행위 불변 — graceful return + 프로세스 보존
- H-3: 예외 요약 150자 절단 (초장문 예외 메시지 DB 부풀림 차단)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import find_function_def, read_module_source

pytestmark = pytest.mark.unit


_SCHEDULER_PY = Path(__file__).resolve().parents[3] / "src" / "engine" / "scheduler.py"


def _start_body_src() -> str:
    source = read_module_source(_SCHEDULER_PY)
    node = find_function_def(source, "start")
    assert node is not None, "scheduler.start() 함수 미존재"
    return ast.unparse(node)


class TestCrashHandlerInstrument:
    """start() 크래시 핸들러 영역 예외 타입 계측 회귀 가드."""

    def test_h1_crash_handler_includes_exception_type_and_message(self):
        """H-1 (HIGH): 크래시 핸들러 write_log ERROR 에 type(exc).__name__ + str(exc) 동반.

        시정 후 = `write_log("ERROR", f"매매 프로세스 비정상 종료: {type(exc).__name__}: ...")`.
        현재 코드 = `write_log("ERROR", "매매 프로세스 비정상 종료")` (예외 타입 부재) → FAIL.
        """
        body_src = _start_body_src()

        # 기존 크래시 메시지 접두는 보존
        assert "매매 프로세스 비정상 종료" in body_src, (
            "크래시 핸들러 메시지 접두 '매매 프로세스 비정상 종료' 보존 의무"
        )
        # 예외 타입명 계측 토큰
        assert "type(exc).__name__" in body_src, (
            "H-1: 크래시 핸들러 write_log ERROR 에 `type(exc).__name__` 계측 부재 — "
            "사이클 190 결함 진단성 확보 위반 (원인불명 8회 재발 → DB 진단 불가)"
        )
        # str(exc) 요약 계측 토큰
        assert "str(exc)" in body_src, (
            "H-1: 크래시 핸들러 write_log ERROR 에 `str(exc)` 예외 메시지 요약 부재"
        )

    def test_h2_kis_api_error_graceful_branch_preserved(self):
        """H-2: 사이클 146 KisApiError graceful 분기 불변 — return + 프로세스 보존.

        불변식 (현재 PASS 유지).
        """
        body_src = _start_body_src()

        assert "isinstance(exc, KisApiError)" in body_src, (
            "H-2: 사이클 146 KisApiError graceful 분기 보존 의무"
        )
        assert "일시 장애" in body_src or "graceful" in body_src.lower(), (
            "H-2: KisApiError graceful 로그 메시지 보존 의무"
        )
        # graceful 분기의 조기 return (finally 진입 후 프로세스 종료 경로 회피)
        assert "return" in body_src, "H-2: KisApiError graceful return 경로 보존 의무"
        # 기존 크래시 로그 exception 호출 보존
        assert "매매 프로세스 오류" in body_src, (
            "H-2: logger.exception('매매 프로세스 오류') 보존 의무"
        )

    def test_h3_exception_summary_truncated_to_150(self):
        """H-3: 예외 요약 150자 절단 — 초장문 예외 메시지 DB 부풀림 차단.

        시정 후 = `str(exc)[:150]`. 현재 코드 = 절단 부재 → FAIL.
        """
        body_src = _start_body_src()

        assert "str(exc)[:150]" in body_src, (
            "H-3: 크래시 핸들러 예외 메시지 요약이 `str(exc)[:150]` 로 절단되지 않음 — "
            "초장문 traceback/예외 메시지가 system_logs 부풀림 위험"
        )
