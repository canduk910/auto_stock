"""사이클 56-E Red — `src/db/system_logs.py::safe_write_log` 4 케이스.

G5-1: write_log 정상 작동 시 safe_write_log 동등 동작
G5-2: write_log 예외 발생 시 graceful skip + logger.debug 호출
G5-3: fallback_debug 인자 전달 시 그것이 logger.debug 메시지로 사용
G5-4: fallback_debug None 일 때 기본 메시지 (level + message 일부 포함)
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# G5-1: write_log 정상 작동 시 safe_write_log 동등 동작
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_g5_1_safe_write_log_delegates_to_write_log():
    """write_log 정상 시 safe_write_log 는 동일 인자로 write_log 를 호출한다."""
    mock_write_log = AsyncMock()

    import src.db.system_logs as _mod

    with patch.object(_mod, "write_log", mock_write_log):
        await _mod.safe_write_log("INFO", "테스트 메시지")

    mock_write_log.assert_awaited_once_with("INFO", "테스트 메시지")


# ---------------------------------------------------------------------------
# G5-2: write_log 예외 발생 시 graceful skip + logger.debug 호출
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_g5_2_graceful_skip_on_write_log_exception(caplog):
    """write_log 예외 시 safe_write_log 는 예외를 전파하지 않고 logger.debug 만 발화."""
    mock_write_log = AsyncMock(side_effect=RuntimeError("Supabase 연결 오류"))

    import src.db.system_logs as _mod

    with patch.object(_mod, "write_log", mock_write_log):
        with caplog.at_level(logging.DEBUG, logger="src.db.system_logs"):
            # 예외가 전파되지 않아야 한다
            await _mod.safe_write_log("WARNING", "장애 메시지")

    # write_log 는 호출됐어야 함
    mock_write_log.assert_awaited_once()
    # logger.debug 가 발화됐어야 함 (caplog 에서 DEBUG 이상 로그 존재)
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert len(debug_records) >= 1, "logger.debug 가 최소 1회 발화돼야 한다"


# ---------------------------------------------------------------------------
# G5-3: fallback_debug 인자 전달 시 그것이 logger.debug 메시지로 사용
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_g5_3_fallback_debug_used_as_debug_message(caplog):
    """fallback_debug 명시 시 logger.debug 는 그 문자열을 첫 번째 인자로 사용한다."""
    mock_write_log = AsyncMock(side_effect=ConnectionError("DB 오류"))

    import src.db.system_logs as _mod

    with patch.object(_mod, "write_log", mock_write_log):
        with caplog.at_level(logging.DEBUG, logger="src.db.system_logs"):
            await _mod.safe_write_log(
                "INFO",
                "어떤 메시지",
                fallback_debug="[my_tag] write_log 실패",
            )

    # logger.debug 가 발화됐고 fallback_debug 텍스트가 로그에 포함돼야 함
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert len(debug_records) >= 1, "logger.debug 가 최소 1회 발화돼야 한다"
    assert "[my_tag] write_log 실패" in debug_records[0].getMessage()


# ---------------------------------------------------------------------------
# G5-4: fallback_debug None 일 때 기본 메시지 (level + message 일부 포함)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_g5_4_default_debug_message_contains_level_and_message(caplog):
    """fallback_debug=None 시 기본 debug 메시지에 level 과 message[:80] 이 포함된다."""
    mock_write_log = AsyncMock(side_effect=OSError("타임아웃"))

    import src.db.system_logs as _mod

    with patch.object(_mod, "write_log", mock_write_log):
        with caplog.at_level(logging.DEBUG, logger="src.db.system_logs"):
            await _mod.safe_write_log("CRITICAL", "중요한 오류 메시지", fallback_debug=None)

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert len(debug_records) >= 1, "logger.debug 가 최소 1회 발화돼야 한다"
    # 기본 메시지: level="CRITICAL" + message[:80] 의 일부가 포함돼야 함
    log_text = debug_records[0].getMessage()
    assert "CRITICAL" in log_text or "중요한 오류 메시지" in log_text
