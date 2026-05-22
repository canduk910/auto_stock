"""사이클 43 (2026-05-22) — 세션 라벨 통일 (DB 사용자 라벨 사용).

배경:
- 사이클 42 ws_heartbeat 로그가 DB 라벨 (ISA/sub/gold) 사용 — 정합.
- 그러나 [tick_coverage_session]/[stale_watcher_detail]/[priority_drop_pool]/UI 등은
  여전히 1-based index (quote-1/quote-2/quote-3) 사용 — 불일치.

본 사이클 (43) 변경:
- `WebsocketPool._session_label(ws)`: 1-based index → `ws._label` 직접 반환
- `WebsocketPool.get_session_status()`: `(q, f"quote-{i}")` → `(q, q._label)`
- `WebsocketPool.disable_quote_session(label)`: `quote-` startswith → `_quotes` 순회 후
  `_label` 매칭 (메인 라벨 noop 가드 절대 보존)

안전 가드 (절대 보존):
- 메인 라벨 = "main" (변경 0)
- `_quotes[idx]` 인덱스 자체 무변경 — label 반환 로직만 변경
- `disable_quote_session("main")` noop 가드 보존
- 사이클 28 `get_subscriptions_by_session` 의 label 반환 정합성 자동 동기

사양 (L-1 ~ L-7):
- L-1: `_session_label(main)` = "main"
- L-2: `_session_label(quote_ws)` = `ws._label` (DB 라벨, 예: "ISA")
- L-3: `get_session_status()` 응답에 DB 라벨 노출
- L-4: `disable_quote_session("ISA")` 가 정상 동작 (메인 noop / DB 라벨 매칭)
- L-5: `disable_quote_session("main")` noop (안전 가드 보존)
- L-6: `disable_quote_session("none-existent")` noop (idempotent)
- L-7: `get_subscriptions_by_session()` 응답에도 DB 라벨 노출 (사이클 28 정합)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


def _make_pool_with_labels(labels: list[str]):
    """Mock pool — 메인 + 라벨 N개 보조 세션."""
    from src.realtime.websocket_pool import WebsocketPool
    from src.realtime.websocket import KisWebSocket

    pool = WebsocketPool()
    # 메인은 그대로 (__init__ 이 self._main = KisWebSocket() 생성)
    pool._main._label = "main"
    pool._main._subscriptions = set()
    pool._main._subscriptions_acked = set()
    # 보조 세션 mock — label 별 KisWebSocket 인스턴스
    pool._quotes = []
    for lbl in labels:
        ws = KisWebSocket.__new__(KisWebSocket)
        ws._label = lbl
        ws.is_main = False
        ws._subscriptions = set()
        ws._subscriptions_acked = set()
        ws._ws = object()
        ws._reconnect_count = 0
        ws.disconnect = AsyncMock()
        pool._quotes.append(ws)
    return pool


# ===========================================================================
# L-1: _session_label(main) = "main"
# ===========================================================================
def test_session_label_main():
    """메인 세션 label = 'main' (절대 보존)."""
    pool = _make_pool_with_labels(["ISA"])
    label = pool._session_label(pool._main)
    assert label == "main", f"메인 라벨 'main' 절대 보존. 실제={label}"


# ===========================================================================
# L-2: _session_label(quote_ws) = ws._label (DB 라벨)
# ===========================================================================
def test_session_label_returns_db_label():
    """보조 세션 label = `ws._label` (DB kis_quote_accounts.label 값)."""
    pool = _make_pool_with_labels(["ISA", "sub", "gold"])
    assert pool._session_label(pool._quotes[0]) == "ISA"
    assert pool._session_label(pool._quotes[1]) == "sub"
    assert pool._session_label(pool._quotes[2]) == "gold"


def test_session_label_unknown_session_returns_unknown():
    """풀에 없는 세션 → 'unknown' (graceful, 기존 폴백 유지)."""
    pool = _make_pool_with_labels(["ISA"])
    from src.realtime.websocket import KisWebSocket
    orphan = KisWebSocket.__new__(KisWebSocket)
    orphan._label = "orphan"
    orphan.is_main = False
    # 풀에 없는 세션 — _quotes 순회에서 매칭 실패
    # 정책: ws._label 그대로 또는 "unknown" — graceful
    label = pool._session_label(orphan)
    # 본 케이스는 orphan._label 그대로 또는 "unknown" 둘 다 허용 (graceful)
    assert label in ("orphan", "unknown")


# ===========================================================================
# L-3: get_session_status() 응답에 DB 라벨 노출
# ===========================================================================
def test_get_session_status_uses_db_labels(monkeypatch):
    """`get_session_status()` 결과 sessions[*].label = main + DB 라벨."""
    from src.engine.scanner import TICK_TR_ID
    pool = _make_pool_with_labels(["ISA", "sub", "gold"])

    sessions = pool.get_session_status()
    labels = [s["label"] for s in sessions]
    assert labels == ["main", "ISA", "sub", "gold"], (
        f"세션 라벨 main + DB 라벨 순서. 실제={labels}"
    )


# ===========================================================================
# L-4: disable_quote_session(DB 라벨) 정상 동작
# ===========================================================================
@pytest.mark.asyncio
async def test_disable_quote_session_with_db_label():
    """disable_quote_session('ISA') 호출 → 해당 세션 제거."""
    pool = _make_pool_with_labels(["ISA", "sub", "gold"])
    initial_count = len(pool._quotes)

    await pool.disable_quote_session("ISA")

    # 세션 1개 제거
    assert len(pool._quotes) == initial_count - 1
    # 남은 세션은 sub, gold
    remaining_labels = [q._label for q in pool._quotes]
    assert "ISA" not in remaining_labels
    assert "sub" in remaining_labels
    assert "gold" in remaining_labels


@pytest.mark.asyncio
async def test_disable_quote_session_disconnects_target():
    """disable_quote_session 호출 시 disconnect 발화."""
    pool = _make_pool_with_labels(["ISA"])
    target_ws = pool._quotes[0]

    await pool.disable_quote_session("ISA")

    target_ws.disconnect.assert_awaited_once()


# ===========================================================================
# L-5: disable_quote_session('main') noop (안전 가드 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_disable_quote_session_main_is_noop():
    """메인 세션 'main' 호출 → noop (안전 가드 절대 보존)."""
    pool = _make_pool_with_labels(["ISA", "sub"])
    initial_count = len(pool._quotes)

    await pool.disable_quote_session("main")

    # _quotes 변경 0
    assert len(pool._quotes) == initial_count


# ===========================================================================
# L-6: disable_quote_session(없는 라벨) noop (idempotent)
# ===========================================================================
@pytest.mark.asyncio
async def test_disable_quote_session_unknown_label_noop():
    """없는 라벨 호출 → noop (idempotent — 두 번째 호출 안전)."""
    pool = _make_pool_with_labels(["ISA"])

    await pool.disable_quote_session("non-existent-label")

    # 변경 없음
    assert len(pool._quotes) == 1
    assert pool._quotes[0]._label == "ISA"


# ===========================================================================
# L-7: get_subscriptions_by_session() — DB 라벨 노출 (사이클 28 정합)
# ===========================================================================
def test_get_subscriptions_by_session_uses_db_labels():
    """사이클 28 헬퍼도 DB 라벨 자동 반영 (`_session_label` 재활용)."""
    pool = _make_pool_with_labels(["ISA", "sub"])
    # _ticker_to_session 매핑 (실제 운영 패턴)
    pool._ticker_to_session = {
        "005930": pool._main,
        "000660": pool._quotes[0],
        "035420": pool._quotes[1],
    }

    grouped = pool.get_subscriptions_by_session()
    assert "main" in grouped and "005930" in grouped["main"]
    assert "ISA" in grouped and "000660" in grouped["ISA"]
    assert "sub" in grouped and "035420" in grouped["sub"]
