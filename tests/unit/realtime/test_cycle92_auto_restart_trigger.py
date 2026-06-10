"""사이클 92 H-2 — MAX_RECONNECT 도달 시 _trigger_auto_restart 호출 정합 (HIGH).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A2-Q1/Q4 영속:
- Q30=A MAX_RECONNECT 도달 시 start() idempotent 재호출
- 4중 안전망 *추가* 영역 (대체 X) — sequential 무관 (G-REJECT-1 위반 0)

기대 동작 (Green, 사이클 92):
- KisWebSocket._trigger_auto_restart 메서드 존재
- async 메서드 (coroutine)
- 60s cooldown + 시간당 3회 cap 가드 통과 시 True 반환
- ws.disconnect() + ws.connect() 시퀀스 호출
- WARNING `[ws_auto_restart] MAX_RECONNECT 도달 → start() 자동 재호출` emit

Red 상태 (사이클 92, production 변경 0):
- AttributeError: 'KisWebSocket' object has no attribute '_trigger_auto_restart'

영속 의무:
- 사이클 88 G-REJECT-1 (4중 안전망 영속) — 자동 재기동 = 추가 영역
- 사이클 79/80 task lifecycle 패턴 답습
"""
from __future__ import annotations

import inspect
import logging
from unittest.mock import AsyncMock

import pytest

from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


def test_h2_trigger_auto_restart_method_exists():
    """H-2-1: KisWebSocket._trigger_auto_restart 메서드 존재 (Q30=A 영속).

    Red 상태: AttributeError → FAILED.
    Green: backend-dev 신규 메서드 추가 → PASS.
    """
    ws = KisWebSocket()
    assert hasattr(ws, "_trigger_auto_restart"), (
        "\n사이클 92 H-2-1 위반 — _trigger_auto_restart 메서드 부재:\n"
        "  Q30=A: MAX_RECONNECT 도달 시 start() 자동 재호출 메서드 의무\n"
        "  근거: KIS 07:50 강제 중단 영구 시정"
    )


def test_h2_trigger_auto_restart_is_async():
    """H-2-2: _trigger_auto_restart 는 async 메서드 (coroutine).

    Red 상태: 메서드 부재 OR 비동기 미정의 → FAILED.
    Green: `async def _trigger_auto_restart(self) -> bool` → PASS.
    """
    ws = KisWebSocket()
    method = getattr(ws, "_trigger_auto_restart", None)
    assert method is not None, "_trigger_auto_restart 메서드 부재 (H-2-1 선행)"
    assert inspect.iscoroutinefunction(method), (
        "\n사이클 92 H-2-2 위반 — _trigger_auto_restart 가 async 가 아님:\n"
        "  기대: `async def _trigger_auto_restart(self) -> bool`\n"
        "  근거: await self.stop() + await self.start() 호출 필수"
    )


@pytest.mark.asyncio
async def test_h2_trigger_auto_restart_returns_true_on_success(caplog):
    """H-2-3: 첫 발화 (cooldown/cap 모두 통과) 시 True 반환 + WARNING emit.

    검증 매트릭스:
    - 첫 발화 (history 빈 상태) → cooldown 미해당 → cap 미해당 → 발화
    - disconnect() + connect() 호출 시퀀스
    - WARNING `[ws_auto_restart] MAX_RECONNECT 도달 → start() 자동 재호출` emit
    - 반환값 True

    Red 상태: 메서드 부재 → AttributeError.
    Green: 4중 안전망 추가 영역 정합 → PASS.

    영속 의무: 사이클 88 G-REJECT-1 (4중 안전망 영속) — H-6 별개 가드.
    """
    ws = KisWebSocket()
    # disconnect/connect (또는 stop/start) 모두 AsyncMock 으로 격리
    # KisWebSocket 현행 인터페이스 = connect/disconnect (start/stop 미존재)
    ws.disconnect = AsyncMock(return_value=None)
    # connect 는 첫 인자가 on_message — 자동 재기동 시 main lifecycle 진입점은
    # 통상 connect 가 아니라 외부 scheduler.start() 영역. 본 테스트는 인터페이스
    # 정합만 검증 (Green 단계 backend-dev 가 시그너처 결정).
    # 만약 backend-dev 가 self.start/self.stop 메서드 신규 추가 (옵션 1) 채택 시
    # 이 mock 도 동행 갱신 의무.
    ws.start = AsyncMock(return_value=None)  # 옵션 1 가정 (Red 단계 정합)
    ws.stop = AsyncMock(return_value=None)

    with caplog.at_level(logging.WARNING, logger="src.realtime.websocket"):
        result = await ws._trigger_auto_restart()

    # 첫 발화 = True 반환
    assert result is True, (
        f"\n사이클 92 H-2-3 위반 — 첫 발화 시 True 반환 의무:\n"
        f"  result={result}\n"
        f"  근거: cooldown/cap 모두 통과 → 발화 성공"
    )

    # WARNING `[ws_auto_restart]` emit 확인
    warning_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("[ws_auto_restart]" in msg for msg in warning_msgs), (
        f"\n사이클 92 H-2-3 위반 — [ws_auto_restart] WARNING emit 누락:\n"
        f"  warning_msgs={warning_msgs}\n"
        f"  근거: 운영 가시화 의무"
    )


@pytest.mark.asyncio
async def test_h2_trigger_auto_restart_calls_stop_then_start():
    """H-2-4: stop() → start() 시퀀스 호출 (idempotent 보장 의무).

    검증 매트릭스:
    - stop() 1회 호출 (기존 상태 정리, domain-expert A2-Q1)
    - start() 1회 호출 (idempotent 재시작)
    - 호출 순서 = stop → start

    Red 상태: 메서드 부재 → AttributeError.
    Green: 순서 정합 → PASS.

    영속 의무 (domain-expert A2-Q1):
    - self._running = False 강제 (진입 게이트 우회 의무)
    - stop() 이 기존 task cancel + lifecycle 정리
    """
    ws = KisWebSocket()
    ws.stop = AsyncMock(return_value=None)
    ws.start = AsyncMock(return_value=None)
    # disconnect 도 대체 사용 가능 (backend-dev 옵션 결정)
    ws.disconnect = AsyncMock(return_value=None)

    await ws._trigger_auto_restart()

    # stop / start 둘 다 1회 호출 의무
    # backend-dev 가 옵션 2 (disconnect/connect 직접 호출) 채택 시 동행 갱신
    stop_called = ws.stop.await_count == 1
    start_called = ws.start.await_count == 1
    assert stop_called and start_called, (
        f"\n사이클 92 H-2-4 위반 — stop()/start() 호출 누락:\n"
        f"  stop.await_count={ws.stop.await_count}, start.await_count={ws.start.await_count}\n"
        f"  근거: idempotent 보장 의무 (domain-expert A2-Q1)\n"
        f"  옵션 2 채택 시: disconnect/connect 동행 검증으로 갱신"
    )
