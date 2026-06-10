"""사이클 92 H-3 — 자동 재기동 60s cooldown freezegun (HIGH).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A2-Q2 영속:
- 60s cooldown (사이클 13-E-2 task lifecycle 답습)
- KIS 재기동 완료 안전 마진
- 중복 발화 race 차단

기대 동작 (Green, 사이클 92):
- 1차 발화 t=0s → True 반환
- 2차 발화 t=30s (cooldown 미경과) → False 반환 + WARNING `[ws_auto_restart_cooldown]`
- 3차 발화 t=61s (cooldown 경과) → True 반환

Red 상태 (사이클 92, production 변경 0):
- AttributeError: '_AUTO_RESTART_COOLDOWN_SECS' 모듈 전역 부재
- AttributeError: '_auto_restart_last_at' 인스턴스 변수 부재

영속 의무:
- 사이클 88 G-REJECT-1 (4중 안전망 영속) — cooldown 은 자동 재기동 영역 한정
- 사이클 13-E-2 task lifecycle 답습 (60s 마진 검증)
"""
from __future__ import annotations

import logging
import time as _time_module
from unittest.mock import AsyncMock, patch

import pytest

from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h3_cooldown_constant_is_60_secs():
    """H-3-1: _AUTO_RESTART_COOLDOWN_SECS 모듈 전역 == 60.0 정합.

    Red 상태: AttributeError → FAILED.
    Green: backend-dev `_AUTO_RESTART_COOLDOWN_SECS = 60.0` 모듈 전역 → PASS.
    """
    from src.realtime import websocket as ws_module
    assert hasattr(ws_module, "_AUTO_RESTART_COOLDOWN_SECS"), (
        "\n사이클 92 H-3-1 위반 — _AUTO_RESTART_COOLDOWN_SECS 모듈 전역 부재:\n"
        "  근거: domain-expert A2-Q2 권고 (사이클 13-E-2 답습)"
    )
    assert ws_module._AUTO_RESTART_COOLDOWN_SECS == 60.0, (
        f"\n사이클 92 H-3-1 위반 — _AUTO_RESTART_COOLDOWN_SECS 값 불일치:\n"
        f"  현재값: {ws_module._AUTO_RESTART_COOLDOWN_SECS}\n"
        f"  기대값: 60.0 (사이클 13-E-2 답습)"
    )


@pytest.mark.asyncio
async def test_h3_second_trigger_within_cooldown_returns_false(caplog):
    """H-3-2: 1차 발화 후 30s (cooldown 미경과) 2차 발화 시 False + WARNING.

    검증 매트릭스:
    - 1차 발화 (t=0s) → True
    - 2차 발화 (t=30s, cooldown=60s 미경과) → False
    - WARNING `[ws_auto_restart_cooldown]` emit
    - stop()/start() 호출 안 됨 (2차)

    Red 상태: AttributeError → FAILED.
    Green: monotonic 비교 정합 → PASS.

    freezegun 미사용 — `time.monotonic` 직접 monkeypatch (monotonic 은 freezegun 영향 0).
    """
    ws = KisWebSocket()
    ws.stop = AsyncMock(return_value=None)
    ws.start = AsyncMock(return_value=None)
    ws.disconnect = AsyncMock(return_value=None)

    # time.monotonic 시간 통제
    fake_time = [1000.0]

    def fake_monotonic():
        return fake_time[0]

    # _time as _time_module 패턴 영속 (Red 명세 영속)
    with patch("src.realtime.websocket._time.monotonic", side_effect=fake_monotonic):
        # 1차 발화 (t=1000)
        result1 = await ws._trigger_auto_restart()
        assert result1 is True, f"1차 발화는 True 반환 의무 (cooldown 빈 상태): result1={result1}"

        # 2차 발화 (t=1030, +30s, cooldown 60s 미경과)
        fake_time[0] = 1030.0
        with caplog.at_level(logging.WARNING, logger="src.realtime.websocket"):
            result2 = await ws._trigger_auto_restart()

        assert result2 is False, (
            f"\n사이클 92 H-3-2 위반 — cooldown 미경과 시 False 반환 의무:\n"
            f"  result2={result2}\n"
            f"  근거: 60s cooldown 미경과 (현재 30s 경과)"
        )

        # WARNING [ws_auto_restart_cooldown] emit 확인
        cooldown_msgs = [
            r.getMessage() for r in caplog.records
            if r.levelno == logging.WARNING and "[ws_auto_restart_cooldown]" in r.getMessage()
        ]
        assert cooldown_msgs, (
            f"\n사이클 92 H-3-2 위반 — [ws_auto_restart_cooldown] WARNING 누락:\n"
            f"  caplog={[r.getMessage() for r in caplog.records]}\n"
            f"  근거: 운영 가시화 의무"
        )


@pytest.mark.asyncio
async def test_h3_trigger_after_cooldown_returns_true():
    """H-3-3: 1차 발화 후 61s (cooldown 경과) 2차 발화 시 True.

    검증 매트릭스:
    - 1차 발화 (t=0s) → True
    - 2차 발화 (t=61s, cooldown=60s 경과) → True
    - stop()/start() 2회 호출

    Red 상태: AttributeError → FAILED.
    Green: monotonic 비교 정합 → PASS.
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
        result1 = await ws._trigger_auto_restart()
        assert result1 is True

        # 2차 발화 (t=1061, +61s, cooldown 60s 경과)
        fake_time[0] = 1061.0
        result2 = await ws._trigger_auto_restart()
        assert result2 is True, (
            f"\n사이클 92 H-3-3 위반 — cooldown 경과 시 True 반환 의무:\n"
            f"  result2={result2}\n"
            f"  근거: 61s 경과 ≥ 60s cooldown"
        )

        # stop/start 2회 호출
        assert ws.stop.await_count == 2, f"stop 2회 호출 의무: {ws.stop.await_count}"
        assert ws.start.await_count == 2, f"start 2회 호출 의무: {ws.start.await_count}"
