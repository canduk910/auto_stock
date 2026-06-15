"""사이클 92 H-6 — 사이클 88 G-REJECT-1/2/3 영속 가드 (HIGH).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

domain-expert 자문 A2-Q5 + A6 영속:
- 사이클 92 자동 재기동 = 4중 안전망 *추가* 영역 (대체 X)
- G-REJECT-1 위반 0 — 4중 안전망 함수 4종 영속 검증
- G-REJECT-2 위반 0 — ticker_last_tick + STALE_FRESHNESS_SECS 종목별 stale 영속
- G-REJECT-3 위반 0 — 4 dict 분리 영속 (_subscriptions / _subscriptions_acked / _ticker_to_session / ticker_last_tick)

기대 동작 (Green, 사이클 92):
- 사이클 88 G-REJECT 파일 (`tests/unit/ast/test_external_llm_reject_patterns.py`) 영속
- 본문 G-REJECT-1/2/3 모두 등장 영속
- 사이클 92 자동 재기동 도입 영역 = G-REJECT 영역 무영향
- 4중 안전망 함수 4종 (`_verify_subscriptions_after_reconnect` / `_scan_loop` / `check_and_resubscribe_stale` / `resubscribe_stale_priority`) 영속

Red 상태 (사이클 92, production 변경 0):
- 사이클 88 G-REJECT 파일 영속 → PASS (현재 상태 영속)
- 사이클 92 자동 재기동 도입 후에도 영속 → Green 단계 PASS

영속 의무:
- 사이클 88 G-REJECT-1 (단일 restore 도입 영구 차단)
- 사이클 88 G-REJECT-2 (종목별 stale 영속)
- 사이클 88 G-REJECT-3 (4 dict 분리 영속)
- 매매 안전성 영속 영구 (사이클 29 005935 사고 패턴 영구 차단)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.ast._ast_helpers import read_module_source

pytestmark = pytest.mark.unit


_TESTS_ROOT = Path(__file__).resolve().parents[2]
_G_REJECT_PY = _TESTS_ROOT / "unit" / "ast" / "test_external_llm_reject_patterns.py"
_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"


def test_h6_cycle88_g_reject_file_persists():
    """H-6-1: 사이클 88 G-REJECT-1/2/3 AST 가드 파일 영속 (사이클 92 시정 후에도).

    검증 매트릭스:
    - `tests/unit/ast/test_external_llm_reject_patterns.py` 영속
    - 본문에 G-REJECT-1/2/3 모두 등장 (영속 의무)
    - 사이클 92 자동 재기동 도입해도 변경 0

    영속 의무:
    - 사이클 88 G-REJECT-1/2/3 영속 영구
    - 사이클 92 자동 재기동 = 4중 안전망 *추가* (대체 X)
    """
    assert _G_REJECT_PY.exists(), (
        f"\n사이클 92 H-6-1 위반 — 사이클 88 G-REJECT 가드 파일 부재:\n"
        f"  파일: {_G_REJECT_PY}\n"
        f"  영속 의무: 사이클 88 G-REJECT-1/2/3 영속 영구"
    )

    source = read_module_source(_G_REJECT_PY)

    # G-REJECT-1/2/3 모두 본문에 등장
    for reject_id in ("G-REJECT-1", "G-REJECT-2", "G-REJECT-3"):
        assert reject_id in source, (
            f"\n사이클 92 H-6-1 위반 — 사이클 88 {reject_id} 영역 누락:\n"
            f"  파일: {_G_REJECT_PY.name}\n"
            f"  영속 의무: 사이클 88 G-REJECT-1/2/3 모두 영속"
        )


def test_h6_g_reject_1_quadruple_safety_net_functions_persist():
    """H-6-2: G-REJECT-1 4중 안전망 함수 4종 영속 (사이클 92 자동 재기동 = 추가 영역 확인).

    검증 매트릭스 (사이클 88 G-REJECT-1 영속 정합):
    - `_verify_subscriptions_after_reconnect` ∈ src/realtime/websocket.py (F1)
    - `_scan_loop` ∈ src/engine/scheduler.py (5분 주기)
    - `check_and_resubscribe_stale` ∈ src/engine/stale_watcher_core.py (K stale watcher 120s)
    - `resubscribe_stale_priority` ∈ src/engine/stale_watcher_core.py (5분 우선)

    Red 상태: 4종 모두 현재 영속 → PASS.
    Green: 사이클 92 자동 재기동 도입해도 4종 영속 → PASS.

    위반 시 사고 시나리오:
    - 단일 restore 통합 시 KIS 거부 코드 분기별 복구 영역 마비
    - 사이클 29 005935 사고 패턴 재현 → KIS LMS chain 위험
    - 사이클 92 자동 재기동 도입 시 4중 안전망 *추가* 영역 의무
    """
    websocket_py = read_module_source(_SRC_ROOT / "realtime/websocket.py")
    stale_watcher_core_py = read_module_source(_SRC_ROOT / "engine/stale_watcher_core.py")
    scheduler_py = read_module_source(_SRC_ROOT / "engine/scheduler.py")

    # F1 재연결 verify
    assert "_verify_subscriptions_after_reconnect" in websocket_py, (
        "\n사이클 92 H-6-2 위반 — F1 재연결 후 verify 함수 영속 의무.\n"
        "  사이클 92 자동 재기동 = 4중 안전망 *추가* 영역 (대체 X)."
    )

    # K stale watcher
    assert "def check_and_resubscribe_stale" in stale_watcher_core_py, (
        "\n사이클 92 H-6-2 위반 — K stale watcher 영속 의무.\n"
        "  check_and_resubscribe_stale 누락 = 4중 안전망 3번 마비 + 사이클 29 005935 재현."
    )

    # priority resubscribe
    assert "def resubscribe_stale_priority" in stale_watcher_core_py, (
        "\n사이클 92 H-6-2 위반 — priority resubscribe 영속 의무.\n"
        "  resubscribe_stale_priority 누락 = 4중 안전망 4번 마비."
    )

    # _scan_loop 5분 주기
    assert "_scan_loop" in scheduler_py, (
        "\n사이클 92 H-6-2 위반 — _scan_loop 5분 주기 영속 의무.\n"
        "  _scan_loop 누락 = 4중 안전망 2번 마비."
    )


def test_h6_g_reject_2_per_ticker_stale_persists():
    """H-6-3: G-REJECT-2 종목별 stale 판정 영속 (사이클 92 시정 후 영향 0).

    검증 매트릭스:
    - `ticker_last_tick` ∈ src/engine/scanner.py
    - `STALE_FRESHNESS_SECS` ∈ src/engine/stale_watcher_core.py
    - 사이클 92 자동 재기동 = lifecycle 영역 → ticker_last_tick 영역과 분리 = 영향 0
    """
    scanner_py = read_module_source(_SRC_ROOT / "engine/scanner.py")
    stale_watcher_core_py = read_module_source(_SRC_ROOT / "engine/stale_watcher_core.py")

    assert "ticker_last_tick" in scanner_py, (
        "\n사이클 92 H-6-3 위반 — 사이클 88 ticker_last_tick 식별자 누락:\n"
        "  영속 의무: 사이클 88 G-REJECT-2 (종목별 stale 영속) 영구\n"
        "  - 사이클 92 = lifecycle 영역 = ticker_last_tick 영역과 분리 = 영향 0"
    )

    assert "STALE_FRESHNESS_SECS" in stale_watcher_core_py, (
        "\n사이클 92 H-6-3 위반 — STALE_FRESHNESS_SECS 종목 단위 임계 영속 의무.\n"
        "  누락 = 종목 단위 stale 판정 마비."
    )


def test_h6_g_reject_3_four_dict_separation_persists():
    """H-6-4: G-REJECT-3 4 dict 분리 영속 (사이클 92 시정 후 영향 0).

    검증 매트릭스 (사이클 88 G-REJECT-3 영속 정합):
    - `_subscriptions` ∈ src/realtime/websocket.py
    - `_subscriptions_acked` ∈ src/realtime/websocket.py
    - `_ticker_to_session` ∈ src/realtime/websocket_pool.py
    - `ticker_last_tick` ∈ src/engine/scanner.py
    - 사이클 92 자동 재기동 = lifecycle 영역 → 4 dict 영역과 분리 = 영향 0
    """
    websocket_py = read_module_source(_SRC_ROOT / "realtime/websocket.py")
    websocket_pool_py = read_module_source(_SRC_ROOT / "realtime/websocket_pool.py")
    scanner_py = read_module_source(_SRC_ROOT / "engine/scanner.py")

    combined = websocket_py + websocket_pool_py + scanner_py
    required_dicts = [
        "_subscriptions",
        "_subscriptions_acked",
        "_ticker_to_session",
        "ticker_last_tick",
    ]

    for d in required_dicts:
        assert d in combined, (
            f"\n사이클 92 H-6-4 위반 — {d} 영속 의무.\n"
            f"  단일 dict 통합 시 orphan ACK race / 41 한도 분산 / "
            f"종목별 tick 추적 영역 마비.\n"
            f"  사이클 92 자동 재기동 = lifecycle 영역 = 4 dict 영역과 분리."
        )
