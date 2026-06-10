"""사이클 92 M-1 — MAX_RECONNECT=5 영속 (MEDIUM).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A3 영속:
- Q30=A 단일 채택 (옵션 C MAX_RECONNECT=5 영속 + 자동 재기동 추가)
- 옵션 A (MAX_RECONNECT=10) 비채택 (17분 LMS 위험 직접 노출)
- 옵션 B (BACKOFF_BASE=0.5) 비채택 (LMS 위험 직접 ↑)
- 31초 한도 = KIS 강제 중단 지속 (5~30초 추정) 일치

기대 동작 (Green, 사이클 92):
- MAX_RECONNECT == 5 영속 (변경 0)
- BACKOFF_BASE == 1.0 영속 (변경 0)
- 5회 누적 = 1+2+4+8+16 = 31초 영속

Red 상태 (사이클 92, production 변경 0):
- 현재 영속 → PASS (영속 가드)

영속 의무:
- 사이클 88 G-REJECT-1 (4중 안전망 영속) — 시간 척도 영속
- 사이클 92 자동 재기동 = MAX_RECONNECT 한도 변경 X = 추가 영역
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_m1_max_reconnect_persists_at_5():
    """M-1-1: MAX_RECONNECT == 5 영속 (Q30=A 한도 영속).

    검증:
    - `src/realtime/websocket.py::MAX_RECONNECT` == 5
    - 자동 재기동 도입 후에도 한도 영속

    영속 의무 (domain-expert A3):
    - 옵션 C (영속) + 자동 재기동 (Q30=A) 단일 채택
    - 옵션 A (=10) 비채택 (17분 LMS 직접 노출)
    - 31초 한도 = KIS 강제 중단 지속 (5~30초 추정) 일치
    """
    from src.realtime import websocket as ws_module
    assert ws_module.MAX_RECONNECT == 5, (
        f"\n사이클 92 M-1-1 위반 — MAX_RECONNECT 한도 변경:\n"
        f"  현재값: {ws_module.MAX_RECONNECT}\n"
        f"  기대값: 5 (Q30=A 영속)\n"
        f"  근거: domain-expert A3 옵션 C 영속 + 자동 재기동 *추가*"
    )


def test_m1_backoff_base_persists_at_1():
    """M-1-2: BACKOFF_BASE == 1.0 영속 (Q30=A 시간 척도 영속).

    검증:
    - BACKOFF_BASE == 1.0 영속
    - 31초 누적 (1+2+4+8+16) 보장

    영속 의무: domain-expert 옵션 B (=0.5) 비채택 (LMS 위험 직접 ↑).
    """
    from src.realtime import websocket as ws_module
    assert ws_module.BACKOFF_BASE == 1.0, (
        f"\n사이클 92 M-1-2 위반 — BACKOFF_BASE 변경:\n"
        f"  현재값: {ws_module.BACKOFF_BASE}\n"
        f"  기대값: 1.0 (Q30=A 영속)\n"
        f"  근거: domain-expert 옵션 B 비채택 (LMS 위험 ↑)"
    )


def test_m1_total_backoff_accumulation_is_31_secs():
    """M-1-3: 5회 누적 backoff = 31초 (= 1+2+4+8+16) 정적 검증.

    검증:
    - sum(BACKOFF_BASE * 2^(n-1) for n in 1..MAX_RECONNECT) == 31.0
    - KIS 강제 중단 지속 (5~30초 추정) 흡수 가능 영역

    영속 의무: 31초 한도 = 사이클 92 자동 재기동 cooldown (60s) ≪ 1 시간 cap 윈도우.
    """
    from src.realtime import websocket as ws_module

    total = sum(
        ws_module.BACKOFF_BASE * (2 ** (n - 1))
        for n in range(1, ws_module.MAX_RECONNECT + 1)
    )

    assert total == 31.0, (
        f"\n사이클 92 M-1-3 위반 — 5회 누적 backoff != 31초:\n"
        f"  현재값: {total}\n"
        f"  기대값: 31.0 (1+2+4+8+16)\n"
        f"  근거: KIS 강제 중단 지속 흡수 영역 영속"
    )
