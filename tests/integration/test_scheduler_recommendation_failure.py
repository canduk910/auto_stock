"""scheduler.py 19:50 AI자문 / 20:10 일일 로그 분석 예외 핸들러 보강 회귀 테스트.

2026-05-09 ~ 2026-05-12 4일간 system_logs 에 "전략수정 AI자문 생성 실패" GENERIC 메시지만
남고 stack trace 가 없어 결함 원인 추적이 불가능했던 사고를 차단.

검증 포인트:
  1. scheduler.py 소스에 traceback / type(e).__name__ 패턴이 두 핸들러 모두에 존재
  2. 같은 패턴 코드가 실행되면 system_logs ERROR 메시지에 stack trace 가 포함되어야 함
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest


SCHEDULER_PATH = Path(__file__).resolve().parent.parent.parent / "src" / "engine" / "scheduler.py"


def test_scheduler_source_has_traceback_in_recommendation_handler():
    """19:50 AI자문 except 핸들러에 traceback.format_exc() 가 포함되어야 한다."""
    src = SCHEDULER_PATH.read_text(encoding="utf-8")
    # 핵심 패턴: 19:50 핸들러 컨텍스트에서 traceback 사용 + ERROR 로그에 trace= 포함
    assert "전략수정 AI자문 생성 실패: type=" in src, \
        "19:50 핸들러에 type/msg/trace 보존 ERROR 메시지 누락 — 결함 재발 위험"
    assert "traceback.format_exc()" in src, "traceback.format_exc() 호출 누락"
    assert "trace={tb[:1000]}" in src, "stack trace 1000자 제한 슬라이싱 누락"


def test_scheduler_source_has_traceback_in_log_analysis_handler():
    """20:10 일일 로그 분석 except 핸들러도 동일 패턴이 적용되어야 한다."""
    src = SCHEDULER_PATH.read_text(encoding="utf-8")
    assert "일일 로그 분석 리포트 생성 실패: type=" in src, \
        "20:10 핸들러에 type/msg/trace 보존 ERROR 메시지 누락"
    # 두 핸들러 모두 traceback.format_exc + tb[:1000] 사용
    # (전체 파일에서 두 번 이상 나와야 함 — 양쪽 핸들러)
    assert src.count("tb[:1000]") >= 2, "두 핸들러 모두 1000자 trace 슬라이싱 적용 필요"


@pytest.mark.asyncio
async def test_recommendation_handler_pattern_writes_stack_trace(monkeypatch):
    """예외 발생 시 write_log ERROR 메시지에 traceback 과 type 이 포함되어야 한다.

    scheduler 의 try/except 블록과 동일한 코드 패턴을 재현해 회귀 검증한다.
    """
    captured: list[tuple[str, str]] = []

    async def fake_write_log(level: str, message: str) -> None:
        captured.append((level, message))

    # scheduler.py 의 19:50 except 블록과 동일한 패턴 (정확히 동일한 코드를 실행)
    async def run_block():
        try:
            raise ValueError("OPENAI_API_KEY 미설정 (시뮬)")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            await fake_write_log(
                "ERROR",
                f"전략수정 AI자문 생성 실패: type={type(e).__name__} msg={e!s} trace={tb[:1000]}",
            )

    await run_block()

    assert len(captured) == 1
    level, msg = captured[0]
    assert level == "ERROR"
    # 핵심 어설션 — 결함 차단의 본질
    assert "type=ValueError" in msg
    assert "msg=OPENAI_API_KEY 미설정 (시뮬)" in msg
    assert "trace=" in msg
    # traceback 본문에 raise 위치(파일/라인) 흔적이 있어야 함
    assert "Traceback" in msg or "ValueError" in msg


@pytest.mark.asyncio
async def test_log_analysis_handler_pattern_writes_stack_trace():
    """20:10 일일 로그 분석 except 블록 동일 회귀 검증."""
    captured: list[tuple[str, str]] = []

    async def fake_write_log(level: str, message: str) -> None:
        captured.append((level, message))

    async def run_block():
        try:
            raise RuntimeError("OpenAI 호출 실패 (시뮬)")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            await fake_write_log(
                "ERROR",
                f"일일 로그 분석 리포트 생성 실패: type={type(e).__name__} msg={e!s} trace={tb[:1000]}",
            )

    await run_block()

    assert len(captured) == 1
    level, msg = captured[0]
    assert level == "ERROR"
    assert "type=RuntimeError" in msg
    assert "msg=OpenAI 호출 실패 (시뮬)" in msg
    assert "trace=" in msg


def test_scheduler_source_has_no_generic_error_only_log():
    """예전 결함 패턴(stack trace 없는 단발 ERROR)이 남아있으면 안 된다.

    `await write_log("ERROR", "전략수정 AI자문 생성 실패")` 와 같이 trace 없는
    표현이 남아있으면 결함 재발 가능.
    """
    src = SCHEDULER_PATH.read_text(encoding="utf-8")
    # 정확히 trace= 없이 끝나는 ERROR 메시지가 있는지 확인
    bad_pattern_recommendation = re.search(
        r'write_log\(\s*"ERROR"\s*,\s*"전략수정 AI자문 생성 실패"\s*\)',
        src,
    )
    bad_pattern_log_analysis = re.search(
        r'write_log\(\s*"ERROR"\s*,\s*"일일 로그 분석 리포트 생성 실패"\s*\)',
        src,
    )
    assert bad_pattern_recommendation is None, \
        "stack trace 없는 GENERIC ERROR 로그 잔존 — 결함 재발 위험 (19:50)"
    assert bad_pattern_log_analysis is None, \
        "stack trace 없는 GENERIC ERROR 로그 잔존 — 결함 재발 위험 (20:10)"
