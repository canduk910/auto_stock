"""사이클 190 Red — `src/db/system_logs.py::write_log` never-raise 전환.

결함 (2026-07-03 07:59 운영 실증):
- `scheduler.py::start()` 의 bare `await write_log("INFO", ...)` 가 Supabase HTTP/2
  `httpcore.RemoteProtocolError(ConnectionTerminated)` 로 raise → start() 외곽 except
  (KisApiError 아님 → 사이클 146 graceful 미해당) → finally task 7종 cancel + WS 종료
  → 매매 시스템 종료.
- 구조 원인 = write_log 가 INSERT 실패 시 그대로 raise. 호출부 72곳의 로컬 보호 여부가
  제각각 → 단일 지점(write_log 자체) never-raise 로 관찰성 INSERT 가 매매를 죽이는
  클래스를 영구 차단.

Green 계약:
- write_log 는 INSERT 실패 시 `logger.debug("[write_log_failed] ...")` 단독 발화 후 return.
  WARNING 이상 금지 (`_DbLogHandler` 재귀 위험 — safe_write_log 사이클 56-E 답습).
- 시그니처/반환(None)/정상 경로 payload 불변 (사이클 65 H2 KST timestamp 보존).

케이스:
- W-1 (HIGH): INSERT httpx.RemoteProtocolError raise → write_log 예외 미전파 (return None)
- W-2: httpcore RemoteProtocolError 계열 / 일반 Exception 도 미전파 (parametrize)
- W-3: 실패 시 logger.debug 1회 발화 + logger.warning 이상 미발화 (재귀 차단 계약)
- W-4: 정상 경로 INSERT 1회 호출 불변 (payload log_level/message/timestamp KST 보존)
- W-5: safe_write_log 통합 — write_log 본체가 raise 하는 supabase 를 태워도 graceful
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import httpcore
import httpx
import pytest

pytestmark = pytest.mark.unit


def _mock_supabase_raising(exc: Exception) -> MagicMock:
    """`supabase.table("system_logs").insert(data).execute()` 가 exc 를 raise 하는 mock."""
    mock = MagicMock()
    mock.table.return_value.insert.return_value.execute.side_effect = exc
    return mock


def _mock_supabase_ok() -> MagicMock:
    """정상 경로 mock — execute() 가 빈 응답 반환."""
    mock = MagicMock()
    mock.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])
    return mock


# ---------------------------------------------------------------------------
# W-1 (HIGH): INSERT httpx.RemoteProtocolError → 예외 미전파
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_w1_remote_protocol_error_not_propagated():
    """운영 크래시 재현 — INSERT 가 RemoteProtocolError raise 해도 write_log 는 미전파."""
    import src.db.system_logs as _mod

    mock_supabase = _mock_supabase_raising(
        httpx.RemoteProtocolError("Server disconnected without sending a response.")
    )

    with patch.object(_mod, "supabase", mock_supabase):
        # 예외가 전파되면 이 await 에서 raise → 테스트 실패
        result = await _mod.write_log("INFO", "스윙 유니버스 비어있어 prepare 재실행")

    assert result is None, "write_log 반환은 항상 None (시그니처 불변)"
    # INSERT 는 실제로 시도됐어야 함 (fire-and-forget 이 아닌 실제 호출)
    mock_supabase.table.assert_called_with("system_logs")


# ---------------------------------------------------------------------------
# W-2: 다양한 예외 계열 미전파 (parametrize)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        httpcore.RemoteProtocolError("<ConnectionTerminated error_code:0>"),
        httpx.ConnectError("connection failed"),
        ConnectionError("네트워크 오류"),
        RuntimeError("일반 런타임 오류"),
        ValueError("직렬화 오류"),
    ],
)
async def test_w2_any_exception_not_propagated(exc: Exception):
    """connection 계열이든 일반 Exception 이든 write_log 는 절대 전파하지 않는다."""
    import src.db.system_logs as _mod

    mock_supabase = _mock_supabase_raising(exc)

    with patch.object(_mod, "supabase", mock_supabase):
        result = await _mod.write_log("ERROR", "테스트 메시지")

    assert result is None


# ---------------------------------------------------------------------------
# W-3: 실패 시 logger.debug 발화 + WARNING 이상 미발화 (재귀 차단)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_w3_failure_logs_debug_only_no_warning(caplog):
    """실패 시 logger.debug 만 발화 — WARNING 이상 금지 (_DbLogHandler 재귀 차단)."""
    import src.db.system_logs as _mod

    mock_supabase = _mock_supabase_raising(
        httpcore.RemoteProtocolError("Server disconnected")
    )

    with patch.object(_mod, "supabase", mock_supabase):
        with caplog.at_level(logging.DEBUG, logger="src.db.system_logs"):
            await _mod.write_log("INFO", "실패 케이스 메시지")

    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    high_records = [r for r in caplog.records if r.levelno >= logging.WARNING]

    assert len(debug_records) >= 1, "실패 시 logger.debug 가 최소 1회 발화돼야 한다"
    assert not high_records, (
        f"WARNING 이상 발화 금지 (DbLogHandler 재귀/무한 INSERT 위험): "
        f"{[r.getMessage() for r in high_records]}"
    )


# ---------------------------------------------------------------------------
# W-4: 정상 경로 payload 불변 (사이클 65 H2 KST timestamp 보존)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_w4_success_path_payload_preserved():
    """정상 경로 = INSERT 1회 + payload 에 log_level/message/timestamp(KST) 보존."""
    import src.db.system_logs as _mod

    mock_supabase = _mock_supabase_ok()

    with patch.object(_mod, "supabase", mock_supabase):
        await _mod.write_log("WARNING", "정상 로그 메시지")

    mock_supabase.table.assert_called_with("system_logs")
    insert_call = mock_supabase.table.return_value.insert
    insert_call.assert_called_once()
    data = insert_call.call_args.args[0]
    assert data["log_level"] == "WARNING"
    assert data["message"] == "정상 로그 메시지"
    assert "timestamp" in data, "사이클 65 H2 — timestamp 키 보존 의무"
    assert data["timestamp"].endswith("+09:00"), (
        f"KST timestamp 명시 의무 (사이클 53 컨벤션): {data['timestamp']}"
    )


# ---------------------------------------------------------------------------
# W-5: safe_write_log 통합 — write_log 본체 raise 소스를 태워도 graceful
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_w5_safe_write_log_integration_still_graceful(caplog):
    """safe_write_log → write_log(본체) → supabase INSERT 실패 end-to-end graceful.

    기존 test_safe_write_log.py 는 write_log 를 통째 mock(raise) 하여 검증했으나,
    본 케이스는 write_log 본체를 *실제로 태우고* supabase 만 raise 시켜
    "never-raise 전환 후 safe_write_log 계약이 이중 보호로 여전히 graceful" 임을 검증.
    """
    import src.db.system_logs as _mod

    mock_supabase = _mock_supabase_raising(
        httpx.RemoteProtocolError("Server disconnected")
    )

    with patch.object(_mod, "supabase", mock_supabase):
        with caplog.at_level(logging.DEBUG, logger="src.db.system_logs"):
            # 예외 전파되면 여기서 raise → 실패
            await _mod.safe_write_log("INFO", "safe 통합 메시지")

    high_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not high_records, "safe_write_log 통합 경로도 WARNING 이상 발화 금지"
