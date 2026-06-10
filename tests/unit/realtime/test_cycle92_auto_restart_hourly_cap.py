"""사이클 92 H-4 — 시간당 3회 cap freezegun (HIGH).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A2-Q2 영속:
- 시간당 3회 cap (KIS LMS chain 차단)
- 사이클 24 silent_inactive 2회 답습 보강
- 4회째 = False 반환 + ERROR `[ws_auto_restart_cap_exceeded]`

기대 동작 (Green, 사이클 92):
- 1차 발화 (t=0s) + cooldown 통과 → True
- 2차 발화 (t=61s) + cooldown 통과 → True
- 3차 발화 (t=122s) + cooldown 통과 → True
- 4차 발화 (t=183s) + cap 3 도달 → False + ERROR `[ws_auto_restart_cap_exceeded]`

Red 상태 (사이클 92, production 변경 0):
- AttributeError: '_AUTO_RESTART_HOURLY_CAP' 모듈 전역 부재
- AttributeError: '_auto_restart_history' 인스턴스 변수 부재

영속 의무:
- 사이클 88 G-REJECT-1 (4중 안전망 영속) — cap 은 자동 재기동 영역 한정
- 사이클 24 silent_inactive 2회 답습 (LMS chain 차단)
- domain-expert A2-Q3 토큰 24h 캐시 영속 의무 (cap 초과 시 LMS 위험)
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


def test_h4_cap_constant_is_3():
    """H-4-1: _AUTO_RESTART_HOURLY_CAP 모듈 전역 == 3 정합.

    Red 상태: AttributeError → FAILED.
    Green: backend-dev `_AUTO_RESTART_HOURLY_CAP = 3` 모듈 전역 → PASS.

    영속 의무: domain-expert A2-Q2 권고 (사이클 24 silent_inactive 2회 답습 보강).
    """
    from src.realtime import websocket as ws_module
    assert hasattr(ws_module, "_AUTO_RESTART_HOURLY_CAP"), (
        "\n사이클 92 H-4-1 위반 — _AUTO_RESTART_HOURLY_CAP 모듈 전역 부재:\n"
        "  근거: domain-expert A2-Q2 권고 (LMS chain 차단)"
    )
    assert ws_module._AUTO_RESTART_HOURLY_CAP == 3, (
        f"\n사이클 92 H-4-1 위반 — _AUTO_RESTART_HOURLY_CAP 값 불일치:\n"
        f"  현재값: {ws_module._AUTO_RESTART_HOURLY_CAP}\n"
        f"  기대값: 3 (사이클 24 답습)"
    )


def test_h4_window_constant_is_3600_secs():
    """H-4-2: _AUTO_RESTART_WINDOW_SECS 모듈 전역 == 3600.0 (1시간) 정합.

    Red 상태: AttributeError → FAILED.
    Green: `_AUTO_RESTART_WINDOW_SECS = 3600.0` → PASS.
    """
    from src.realtime import websocket as ws_module
    assert hasattr(ws_module, "_AUTO_RESTART_WINDOW_SECS"), (
        "\n사이클 92 H-4-2 위반 — _AUTO_RESTART_WINDOW_SECS 모듈 전역 부재"
    )
    assert ws_module._AUTO_RESTART_WINDOW_SECS == 3600.0, (
        f"\n사이클 92 H-4-2 위반 — _AUTO_RESTART_WINDOW_SECS 값 불일치:\n"
        f"  현재값: {ws_module._AUTO_RESTART_WINDOW_SECS}\n"
        f"  기대값: 3600.0 (1시간)"
    )


@pytest.mark.asyncio
async def test_h4_fourth_trigger_in_hour_blocked(caplog):
    """H-4-3: 4차 발화 (cap 3 도달) 시 False + ERROR `[ws_auto_restart_cap_exceeded]`.

    검증 매트릭스:
    - 1차/2차/3차 발화 (각 cooldown 통과) → True
    - 4차 발화 → cap 3 도달 → False
    - ERROR `[ws_auto_restart_cap_exceeded]` emit
    - stop/start 4차 호출 안 됨

    Red 상태: AttributeError → FAILED.
    Green: history 누적 + cap 가드 정합 → PASS.

    영속 의무: 사이클 24 silent_inactive LMS chain 차단 패턴 답습.
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
        assert r1 is True, f"1차: {r1}"

        # 2차 발화 (t=1061, +61s)
        fake_time[0] = 1061.0
        r2 = await ws._trigger_auto_restart()
        assert r2 is True, f"2차: {r2}"

        # 3차 발화 (t=1122, +61s)
        fake_time[0] = 1122.0
        r3 = await ws._trigger_auto_restart()
        assert r3 is True, f"3차: {r3}"

        # 4차 발화 (t=1183, +61s) — cap 3 도달
        fake_time[0] = 1183.0
        with caplog.at_level(logging.ERROR, logger="src.realtime.websocket"):
            r4 = await ws._trigger_auto_restart()

        assert r4 is False, (
            f"\n사이클 92 H-4-3 위반 — cap 3 도달 시 False 반환 의무:\n"
            f"  r4={r4}\n"
            f"  근거: 시간당 3회 cap (KIS LMS chain 차단)"
        )

        # stop/start 4차 호출 안 됨 (3회만)
        assert ws.stop.await_count == 3, (
            f"\n사이클 92 H-4-3 위반 — stop 4차 호출 (cap 우회):\n"
            f"  ws.stop.await_count={ws.stop.await_count}\n"
            f"  근거: cap 도달 시 stop()/start() 호출 차단 의무"
        )

        # ERROR [ws_auto_restart_cap_exceeded] emit 확인
        cap_msgs = [
            r.getMessage() for r in caplog.records
            if r.levelno == logging.ERROR and "[ws_auto_restart_cap_exceeded]" in r.getMessage()
        ]
        assert cap_msgs, (
            f"\n사이클 92 H-4-3 위반 — [ws_auto_restart_cap_exceeded] ERROR 누락:\n"
            f"  caplog={[r.getMessage() for r in caplog.records]}\n"
            f"  근거: 운영 가시화 의무 (KIS LMS chain)"
        )
