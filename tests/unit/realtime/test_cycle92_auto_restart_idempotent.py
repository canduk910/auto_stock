"""사이클 92 H-5 — start() idempotent 보장 (HIGH).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A2-Q1 영속:
- idempotent 의무 명시 + 진입 게이트 영속 (scheduler.py:395-405 `self._running` 가드)
- self._running = False 강제 의무 → stop() 호출 → 60s cooldown → start() 재호출
- 사이클 79/80 task lifecycle 답습

기대 동작 (Green, 사이클 92):
- 자동 재기동 1차 발화 → stop() + start() 1회씩
- 자동 재기동 2차 발화 (cooldown 통과) → 기존 상태 정리 + 재시작
- 기존 _subscriptions / _opsp_backoff_until 등 영속 (옵션, stop() 정책 의존)
- start() 중복 호출 시 race 0

Red 상태 (사이클 92, production 변경 0):
- AttributeError: _trigger_auto_restart 부재

영속 의무:
- 사이클 88 G-REJECT-1 (4중 안전망 영속)
- 사이클 17 OPSP0002 backoff 영속 (`_opsp_backoff_until` dict)
- 사이클 79/80 task lifecycle 패턴 답습
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h5_trigger_calls_stop_before_start():
    """H-5-1: stop() → start() 순서 보장 (idempotent + 기존 상태 정리).

    검증 매트릭스:
    - stop() 이 start() 전 호출 (call order)
    - 기존 상태 정리 후 재시작 정합

    Red 상태: AttributeError → FAILED.
    Green: 순서 정합 → PASS.

    영속 의무 (domain-expert A2-Q1):
    - self._running = False 강제 의무 (진입 게이트 우회)
    - stop() 의 task cancel + lifecycle 정리 영속
    """
    ws = KisWebSocket()

    call_order: list[str] = []

    async def stop_spy():
        call_order.append("stop")

    async def start_spy():
        call_order.append("start")

    ws.stop = stop_spy
    ws.start = start_spy
    ws.disconnect = AsyncMock(return_value=None)

    await ws._trigger_auto_restart()

    # stop → start 순서 보장
    assert call_order == ["stop", "start"], (
        f"\n사이클 92 H-5-1 위반 — stop → start 순서 보장 의무:\n"
        f"  call_order={call_order}\n"
        f"  기대: ['stop', 'start']\n"
        f"  근거: domain-expert A2-Q1 (기존 상태 정리 후 재시작)"
    )


@pytest.mark.asyncio
async def test_h5_trigger_records_history_after_success():
    """H-5-2: 성공 발화 시 _auto_restart_history 1건 추가 (cap 카운팅 의무).

    검증:
    - 발화 *전* len(history) == 0
    - 발화 *후* len(history) == 1
    - history 마지막 == _auto_restart_last_at == monotonic 시각

    Red 상태: 인스턴스 변수 부재 → AttributeError.
    Green: history 추가 정합 → PASS.
    """
    ws = KisWebSocket()
    ws.stop = AsyncMock(return_value=None)
    ws.start = AsyncMock(return_value=None)
    ws.disconnect = AsyncMock(return_value=None)

    fake_time = [1234.5]

    def fake_monotonic():
        return fake_time[0]

    # 발화 *전* history 확인
    assert hasattr(ws, "_auto_restart_history"), (
        "\n사이클 92 H-5-2 위반 — _auto_restart_history 인스턴스 변수 부재"
    )
    assert len(ws._auto_restart_history) == 0, (
        f"발화 *전* history 빈 상태 의무: {ws._auto_restart_history}"
    )

    with patch("src.realtime.websocket._time.monotonic", side_effect=fake_monotonic):
        result = await ws._trigger_auto_restart()

    assert result is True
    assert len(ws._auto_restart_history) == 1, (
        f"\n사이클 92 H-5-2 위반 — 발화 *후* history 1건 추가 의무:\n"
        f"  len={len(ws._auto_restart_history)}\n"
        f"  근거: cap 카운팅 정합"
    )
    assert ws._auto_restart_history[-1] == 1234.5
    assert hasattr(ws, "_auto_restart_last_at"), (
        "\n사이클 92 H-5-2 위반 — _auto_restart_last_at 인스턴스 변수 부재"
    )
    assert ws._auto_restart_last_at == 1234.5, (
        f"_auto_restart_last_at 시각 일치 의무: {ws._auto_restart_last_at}"
    )


@pytest.mark.asyncio
async def test_h5_cooldown_blocked_does_not_record_history():
    """H-5-3: cooldown 미경과 (False 반환) 시 history 추가 안 함 (cap 정합).

    검증:
    - 1차 발화 → history 1건
    - 2차 발화 (cooldown 미경과) → False + history 1건 유지 (2건 X)
    - 근거: 실제 발화 안 한 시도는 cap 계산에 포함 안 함 (LMS 안전 마진)

    Red 상태: AttributeError → FAILED.
    Green: 정합 → PASS.
    """
    ws = KisWebSocket()
    ws.stop = AsyncMock(return_value=None)
    ws.start = AsyncMock(return_value=None)
    ws.disconnect = AsyncMock(return_value=None)

    fake_time = [1000.0]

    def fake_monotonic():
        return fake_time[0]

    with patch("src.realtime.websocket._time.monotonic", side_effect=fake_monotonic):
        # 1차 발화
        r1 = await ws._trigger_auto_restart()
        assert r1 is True
        assert len(ws._auto_restart_history) == 1

        # 2차 발화 (cooldown 미경과)
        fake_time[0] = 1010.0
        r2 = await ws._trigger_auto_restart()
        assert r2 is False
        assert len(ws._auto_restart_history) == 1, (
            f"\n사이클 92 H-5-3 위반 — cooldown blocked 시 history 추가 금지:\n"
            f"  len={len(ws._auto_restart_history)}\n"
            f"  기대: 1 (1차만 카운팅)\n"
            f"  근거: 실제 발화 안 한 시도는 cap 계산 제외"
        )
