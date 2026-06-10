"""사이클 92 L-1 — 1시간 슬라이딩 윈도우 prune (LOW).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A2-Q2 영속:
- 1시간 슬라이딩 윈도우 (3600s) prune (history 자동 제거)
- 60분 경과한 history 항목 자동 prune → 새 발화 cap 정합

기대 동작 (Green, 사이클 92):
- 1차 발화 (t=0s) → history 1건
- 2차 발화 (t=3700s, 1h+ 경과) → 1차 prune → history 1건 (2차만 유지)
- cap 3 영역 안 진입 가능 (1시간 슬라이딩 윈도우 정합)

Red 상태 (사이클 92, production 변경 0):
- AttributeError: _auto_restart_history 부재

영속 의무:
- 사이클 92 cap 3 영역 영속 (LMS chain 차단)
- 사이클 66 5분 우선 재구독 window prune 패턴 답습
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_l1_window_prune_after_hour():
    """L-1-1: 1시간 (+1초) 경과 후 history prune → 새 발화 가능 정합.

    검증 매트릭스:
    - 1차 발화 (t=1000) → history 1건
    - 2차 발화 (t=4700, +1h+100s 경과) → cooldown 통과 + history prune → True
    - prune 후 history 크기 == 1 (1차 제거, 2차 추가)

    Red 상태: AttributeError → FAILED.
    Green: window prune 정합 → PASS.
    """
    ws = KisWebSocket()
    ws.stop = AsyncMock(return_value=None)
    ws.start = AsyncMock(return_value=None)
    ws.disconnect = AsyncMock(return_value=None)

    fake_time = [1000.0]

    def fake_monotonic():
        return fake_time[0]

    with patch("src.realtime.websocket._time.monotonic", side_effect=fake_monotonic):
        # 1차 발화 (t=1000)
        r1 = await ws._trigger_auto_restart()
        assert r1 is True
        assert len(ws._auto_restart_history) == 1

        # 2차 발화 (t=4701, +3701s = 1h+101s, cooldown 통과 + window prune 영역)
        fake_time[0] = 4701.0
        r2 = await ws._trigger_auto_restart()
        assert r2 is True, (
            f"\n사이클 92 L-1-1 위반 — 1h 경과 시 새 발화 의무 (prune 후):\n"
            f"  r2={r2}\n"
            f"  근거: 1시간 슬라이딩 윈도우 prune 정합"
        )

        # 1차는 prune, 2차만 history 잔존
        assert len(ws._auto_restart_history) == 1, (
            f"\n사이클 92 L-1-1 위반 — window prune 후 history 크기 잘못:\n"
            f"  len={len(ws._auto_restart_history)}\n"
            f"  기대: 1 (2차만, 1차는 1h 경과 → prune)"
        )
        assert ws._auto_restart_history[-1] == 4701.0


@pytest.mark.asyncio
async def test_l1_window_within_hour_no_prune():
    """L-1-2: 1시간 미경과 시 prune 안 함 (history 누적).

    검증:
    - 1차/2차/3차 발화 (cooldown 통과, 1h 미경과) → history 3건 누적
    - prune 안 됨 (cap 정합 영속)
    """
    ws = KisWebSocket()
    ws.stop = AsyncMock(return_value=None)
    ws.start = AsyncMock(return_value=None)
    ws.disconnect = AsyncMock(return_value=None)

    fake_time = [1000.0]

    def fake_monotonic():
        return fake_time[0]

    with patch("src.realtime.websocket._time.monotonic", side_effect=fake_monotonic):
        r1 = await ws._trigger_auto_restart()
        assert r1 is True

        fake_time[0] = 1061.0  # +61s
        r2 = await ws._trigger_auto_restart()
        assert r2 is True

        fake_time[0] = 1122.0  # +61s (총 122s = 0.034h, 1h 미경과)
        r3 = await ws._trigger_auto_restart()
        assert r3 is True

        assert len(ws._auto_restart_history) == 3, (
            f"\n사이클 92 L-1-2 위반 — 1h 미경과 prune 의무 위반:\n"
            f"  len={len(ws._auto_restart_history)}\n"
            f"  기대: 3 (모두 1h 미경과)"
        )
