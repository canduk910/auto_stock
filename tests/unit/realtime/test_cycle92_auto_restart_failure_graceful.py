"""사이클 92 M-2 — start() 실패 시 graceful False + ERROR (MEDIUM).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A2-Q4 영속:
- start() 실패 graceful False 반환 (계속 동작 차단 차단)
- ERROR `[ws_auto_restart_failed]` emit (운영 가시화 의무)
- 4중 안전망 영역 race 0 보장 (`self._ws is None` graceful skip)

기대 동작 (Green, 사이클 92):
- stop()/start() 호출 중 예외 발생 → False 반환
- ERROR `[ws_auto_restart_failed]` emit
- 후속 자동 재기동은 영향 0 (history 등록 영속, cooldown 영속)

Red 상태 (사이클 92, production 변경 0):
- AttributeError: _trigger_auto_restart 부재

영속 의무:
- 사이클 88 G-REJECT-1 (4중 안전망 영속)
- 사이클 92 자동 재기동 = lifecycle 영역 한정 (4중 안전망 영향 0)
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_m2_start_failure_returns_false(caplog):
    """M-2-1: start() 예외 발생 시 graceful False 반환 + ERROR emit.

    검증 매트릭스:
    - stop() 정상 호출
    - start() 예외 발생 → False 반환
    - ERROR `[ws_auto_restart_failed]` emit

    Red 상태: AttributeError → FAILED.
    Green: try/except + False 반환 정합 → PASS.

    영속 의무: 운영 가시화 의무 (start 실패 시 다음 cycle 대기 영속).
    """
    ws = KisWebSocket()
    ws.stop = AsyncMock(return_value=None)
    # start 가 예외 발생
    ws.start = AsyncMock(side_effect=RuntimeError("KIS API 503"))
    ws.disconnect = AsyncMock(return_value=None)

    with caplog.at_level(logging.ERROR, logger="src.realtime.websocket"):
        result = await ws._trigger_auto_restart()

    # graceful False 반환
    assert result is False, (
        f"\n사이클 92 M-2-1 위반 — start() 실패 시 graceful False 반환 의무:\n"
        f"  result={result}\n"
        f"  근거: domain-expert A2-Q4 graceful 영속"
    )

    # ERROR [ws_auto_restart_failed] emit 확인
    error_msgs = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.ERROR and "[ws_auto_restart_failed]" in r.getMessage()
    ]
    assert error_msgs, (
        f"\n사이클 92 M-2-1 위반 — [ws_auto_restart_failed] ERROR 누락:\n"
        f"  caplog={[r.getMessage() for r in caplog.records]}\n"
        f"  근거: 운영 가시화 의무"
    )


@pytest.mark.asyncio
async def test_m2_stop_failure_does_not_crash():
    """M-2-2: stop() 예외 발생도 graceful False (start 도달 X 가능).

    검증:
    - stop() 예외 → False 반환 (crash 차단)
    - start() 호출 안 됨 OR 호출 후 실패 (둘 다 허용)

    영속 의무: try/except 전체 감싸기 (graceful 영속).
    """
    ws = KisWebSocket()
    ws.stop = AsyncMock(side_effect=RuntimeError("disconnect 실패"))
    ws.start = AsyncMock(return_value=None)
    ws.disconnect = AsyncMock(return_value=None)

    # crash 차단 검증 (False 반환만 의무, start 호출 여부 무관)
    result = await ws._trigger_auto_restart()
    assert result is False, (
        f"\n사이클 92 M-2-2 위반 — stop() 실패 시 graceful False 의무:\n"
        f"  result={result}\n"
        f"  근거: try/except 전체 graceful"
    )
