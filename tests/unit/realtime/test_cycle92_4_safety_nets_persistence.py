"""사이클 92 M-5 — 4중 안전망 영역 영속 보장 (MEDIUM).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A2-Q4 영속:
- F1 (`_verify_subscriptions_after_reconnect`) — connect() 내부 task → _ws=None 영구 종료 후 발화 불가
- _scan_loop 5분 (scheduler) — _ws=None 시 graceful skip
- K stale watcher 120s (stale_watcher_core.check_and_resubscribe_stale) — 세션 dead 시 noop
- _resubscribe_stale_priority 5분 (stale_watcher_core) — 동일 한계

기대 동작 (Green, 사이클 92):
- 4중 안전망 함수 4종 영속 (변경 0)
- 사이클 92 자동 재기동 = 4중 안전망 *추가* 영역 (대체 X)
- _ws=None 상태에서 자동 재기동 후 4중 안전망 자연 재진입 정합

Red 상태 (사이클 92, production 변경 0):
- 4중 안전망 함수 4종 현재 영속 → PASS (영속 가드)
- 사이클 92 자동 재기동 도입 후에도 4종 영속 → Green PASS

영속 의무:
- 사이클 88 G-REJECT-1 (4중 안전망 영속 영구 영역)
- 사이클 29 005935 사고 패턴 영구 차단
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_m5_f1_verify_function_persists():
    """M-5-1: F1 (`_verify_subscriptions_after_reconnect`) 영속 (변경 0).

    검증:
    - `src/realtime/websocket.py` 내 `_verify_subscriptions_after_reconnect` 영속
    - 사이클 92 자동 재기동 도입 후에도 영역 무변경

    영속 의무: 사이클 88 G-REJECT-1 (4중 안전망 1번).
    """
    websocket_py = (_REPO_ROOT / "src/realtime/websocket.py").read_text(encoding="utf-8")
    assert "_verify_subscriptions_after_reconnect" in websocket_py, (
        "\n사이클 92 M-5-1 위반 — F1 함수 영속 의무.\n"
        "  사이클 92 자동 재기동 = 4중 안전망 *추가* (대체 X)."
    )


def test_m5_scan_loop_function_persists():
    """M-5-2: _scan_loop (scheduler 5분 주기) 영속.

    검증:
    - `src/engine/scheduler.py` 내 `_scan_loop` 영속

    영속 의무: 사이클 88 G-REJECT-1 (4중 안전망 2번).
    """
    scheduler_py = (_REPO_ROOT / "src/engine/scheduler.py").read_text(encoding="utf-8")
    assert "_scan_loop" in scheduler_py, (
        "\n사이클 92 M-5-2 위반 — _scan_loop 영속 의무.\n"
        "  사이클 92 자동 재기동 = 4중 안전망 *추가* (대체 X)."
    )


def test_m5_check_and_resubscribe_stale_function_persists():
    """M-5-3: K stale watcher 본체 (`check_and_resubscribe_stale`) 영속.

    검증:
    - `src/engine/stale_watcher_core.py` 내 `check_and_resubscribe_stale` 영속

    영속 의무:
    - 사이클 88 G-REJECT-1 (4중 안전망 3번)
    - 사이클 29 005935 사고 패턴 영구 차단
    """
    stale_core_py = (_REPO_ROOT / "src/engine/stale_watcher_core.py").read_text(encoding="utf-8")
    assert "def check_and_resubscribe_stale" in stale_core_py, (
        "\n사이클 92 M-5-3 위반 — K stale watcher 영속 의무.\n"
        "  사이클 29 005935 사고 재현 위험."
    )


def test_m5_resubscribe_stale_priority_function_persists():
    """M-5-4: priority resubscribe (`resubscribe_stale_priority`) 영속.

    검증:
    - `src/engine/stale_watcher_core.py` 내 `resubscribe_stale_priority` 영속

    영속 의무:
    - 사이클 88 G-REJECT-1 (4중 안전망 4번)
    - 사이클 66 priority 분리 *후* cap 영속
    """
    stale_core_py = (_REPO_ROOT / "src/engine/stale_watcher_core.py").read_text(encoding="utf-8")
    assert "def resubscribe_stale_priority" in stale_core_py, (
        "\n사이클 92 M-5-4 위반 — priority resubscribe 영속 의무.\n"
        "  사이클 66 priority 분리 영속."
    )
