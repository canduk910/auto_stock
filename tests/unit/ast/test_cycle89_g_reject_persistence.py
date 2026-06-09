"""사이클 89 L-5 — 사이클 88 G-REJECT-1/2/3 영속 가드.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

domain-expert 자문 A5 권고 영속:
- G-REJECT-1 (4중 안전망 영속) — 영향 0
- G-REJECT-2 (종목별 stale 영속, `ticker_last_tick`) — 영향 0
- G-REJECT-3 (4 dict 분리 영속) — 영향 0
- 사이클 89 = stock_master 적재 영역 (DB CRUD) = WebSocket 구독 영역과 분리 = 영향 0

기대 동작 (Green, 사이클 90):
- 사이클 88 G-REJECT-1/2/3 AST 가드 영속 (변경 0)
- 사이클 89 시정 영역이 G-REJECT 영역 침범 0

Red 상태 (사이클 89): 사이클 88 G-REJECT 영역 침범 시 FAIL (영속 위반).

영속 의무:
- 사이클 88 G-REJECT-1 (단일 restore 도입 영구 차단, WebSocket 4중 안전망 영속)
- 사이클 88 G-REJECT-2 (stale 전체 WS 단독 판정 영구 차단, ticker_last_tick 종목 단위)
- 사이클 88 G-REJECT-3 (SubscriptionRegistry 단일 dict 통합 영구 차단, 4 dict 분리 영속)
- 매매 안전성 영속 영구 (사이클 29 005935 사고 패턴 영구 차단)
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_TESTS_ROOT = Path(__file__).resolve().parents[2]
_G_REJECT_PY = _TESTS_ROOT / "unit" / "ast" / "test_external_llm_reject_patterns.py"
_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"


def test_l5_cycle88_g_reject_test_file_persists():
    """L-5: 사이클 88 G-REJECT-1/2/3 AST 가드 파일 영속 확인.

    검증 매트릭스:
    - `tests/unit/ast/test_external_llm_reject_patterns.py` 영속 (사이클 88 영속)
    - 본문에 G-REJECT-1/2/3 모두 등장 (영속 의무)
    - 사이클 89 시정해도 변경 0

    Red 상태 (사이클 89): G-REJECT 파일 부재 또는 일부 누락 시 FAIL.

    Green (사이클 90): backend-dev 가 사이클 89 시정해도 G-REJECT 무변경 → PASS.

    영속 의무:
    - 사이클 88 G-REJECT-1/2/3 영속 영구
    - 사이클 29 005935 사고 패턴 영구 차단
    """
    assert _G_REJECT_PY.exists(), (
        f"\n사이클 89 L-5 위반 — 사이클 88 G-REJECT 가드 파일 부재:\n"
        f"  파일: {_G_REJECT_PY}\n"
        f"  영속 의무: 사이클 88 G-REJECT-1/2/3 영속 영구"
    )

    source = _G_REJECT_PY.read_text(encoding="utf-8")

    # G-REJECT-1/2/3 모두 본문에 등장
    for reject_id in ("G-REJECT-1", "G-REJECT-2", "G-REJECT-3"):
        assert reject_id in source, (
            f"\n사이클 89 L-5 위반 — 사이클 88 {reject_id} 영역 누락:\n"
            f"  파일: {_G_REJECT_PY.name}\n"
            f"  영속 의무: 사이클 88 G-REJECT-1/2/3 모두 영속"
        )


def test_l5_cycle88_ticker_last_tick_persists_in_scanner():
    """L-5: 사이클 88 G-REJECT-2 영역 (`ticker_last_tick` 영속) 검증.

    검증 매트릭스:
    - `src/engine/scanner.py` 내 `ticker_last_tick` 식별자 영속
    - 사이클 89 시정 영역에서 변경 0

    영속 의무:
    - 사이클 88 G-REJECT-2 (종목별 stale 영속) 영구
    - 사이클 29 005935 사고 패턴 영구 차단
    - 사이클 89 = stock_master 영역 (DB) = `ticker_last_tick` 영역과 분리 = 영향 0
    """
    scanner_py = _SRC_ROOT / "engine" / "scanner.py"
    assert scanner_py.exists(), (
        f"\n사이클 89 L-5 위반 — `src/engine/scanner.py` 부재 (영속 위반)"
    )

    source = scanner_py.read_text(encoding="utf-8")
    assert "ticker_last_tick" in source, (
        f"\n사이클 89 L-5 위반 — 사이클 88 `ticker_last_tick` 식별자 누락:\n"
        f"  영속 의무: 사이클 88 G-REJECT-2 (종목별 stale 영속) 영구\n"
        f"  - 사이클 89 = stock_master 영역 = ticker_last_tick 영역과 분리 = 영향 0"
    )


def test_l5_cycle88_4_dict_separation_persists_in_websocket():
    """L-5: 사이클 88 G-REJECT-3 영역 (4 dict 분리 영속) 검증.

    검증 매트릭스 (사이클 88 G-REJECT-3 영속 정합):
    - `src/realtime/websocket.py` 내 `_subscriptions` / `_subscriptions_acked` 등장
    - `src/realtime/websocket_pool.py` 내 `_ticker_to_session` 등장 (세션 분배 dict)
    - `src/engine/scanner.py` 내 `ticker_last_tick` 등장 (G-REJECT-2)
    - 사이클 89 시정 영역에서 변경 0

    영속 의무:
    - 사이클 88 G-REJECT-3 (4 dict 분리 영속) 영구
    - SubscriptionRegistry 단일 dict 통합 영구 차단
    - 사이클 89 = stock_master 영역 = 4 dict 영역과 분리 = 영향 0
    """
    websocket_py = _SRC_ROOT / "realtime" / "websocket.py"
    websocket_pool_py = _SRC_ROOT / "realtime" / "websocket_pool.py"
    assert websocket_py.exists(), (
        f"\n사이클 89 L-5 위반 — `src/realtime/websocket.py` 부재 (영속 위반)"
    )
    assert websocket_pool_py.exists(), (
        f"\n사이클 89 L-5 위반 — `src/realtime/websocket_pool.py` 부재 (영속 위반)"
    )

    ws_source = websocket_py.read_text(encoding="utf-8")
    pool_source = websocket_pool_py.read_text(encoding="utf-8")

    # `_subscriptions` / `_subscriptions_acked` 은 websocket.py 영속
    for dict_name in ("_subscriptions", "_subscriptions_acked"):
        assert dict_name in ws_source, (
            f"\n사이클 89 L-5 위반 — 사이클 88 G-REJECT-3 dict 누락 (websocket.py):\n"
            f"  누락 dict: `{dict_name}`\n"
            f"  영속 의무: 사이클 88 G-REJECT-3 (4 dict 분리 영속) 영구\n"
            f"  - SubscriptionRegistry 단일 dict 통합 영구 차단"
        )

    # `_ticker_to_session` 은 websocket_pool.py 영속 (세션 분배 dict)
    assert "_ticker_to_session" in pool_source, (
        f"\n사이클 89 L-5 위반 — 사이클 88 G-REJECT-3 `_ticker_to_session` 누락 (websocket_pool.py):\n"
        f"  영속 의무: 사이클 88 G-REJECT-3 (4 dict 분리 영속) 영구\n"
        f"  - SubscriptionRegistry 단일 dict 통합 영구 차단\n"
        f"  - `_ticker_to_session` = ticker → KisWebSocket 세션 분배 (메인/보조 라우팅)"
    )
