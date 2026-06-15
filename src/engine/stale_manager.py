"""Facade — 사이클 67 분해 후 4 sub-module 의 통합 진입점 (re-export only).

사이클 60 A1 → 사이클 61 A2 → 사이클 63 A3 → 사이클 66 시정 → 사이클 67 분해.
scheduler.py 11 wrapper 가 `from src.engine import stale_manager` 형태이므로
facade re-export 가 wrapper 변경 0 의무 보장 (Q5=A 영속).

Q4=B 안전선 (G-16 AST 가드):
- `patch("src.engine.stale_manager.X")` 패턴 테스트에서 사용 금지
- 실측 0건 (자문 §5 실측 데이터) — facade 보존으로 호환
- 신규 추가 시 G-16 AST 가드 즉시 FAIL → silent 결함 영구 차단

절대 깨지 말 것:
- 11 함수 + 10 상수 re-export 전수 보존 (G-2 가드)
- __all__ 21 항목 영속 (scheduler.py L92 `from src.engine.stale_manager import (5 상수)` 호환)
- logger re-export 영속 (사이클 60 I1 — test_I1 `stale_manager.logger.name` 호환)
"""
from __future__ import annotations

import logging

# logger re-export — 사이클 60 I1 영속: `stale_manager.logger.name == "src.engine.scheduler"` 호환
# 4 sub-module 모두 동일 logger binding 이므로 stale_diagnostics 에서 re-export
from src.engine.stale_diagnostics import logger  # noqa: F401

# ── 상수 re-export (11 상수, 사이클 135 SUBSCRIBE_GRACE_SECS 추가) ─────────────────
# stale_diagnostics (5 상수)
from src.engine.stale_diagnostics import (
    MAX_STALE_RETRIES,
    STALE_FORCE_RETRY_AFTER_SECS,
    STALE_FORCE_RETRY_HOURLY_CAP,
    STALE_FRESHNESS_SECS,
    SUBSCRIBE_GRACE_SECS,  # 사이클 135 — 구독 ACK grace period (180s, Q3=A 영속)
)

# stale_session_recovery (5 상수)
from src.engine.stale_session_recovery import (
    SILENT_INACTIVE_FRESH_RATIO_THRESHOLD,
    SILENT_INACTIVE_MIN_SUBSCRIBED,
    SILENT_INACTIVE_PERSIST_SECS,
    SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR,
    SILENT_INACTIVE_RECOVERY_WINDOW_SECS,
)

# stale_universe_guard (1 상수)
from src.engine.stale_universe_guard import UNIVERSE_LOW_VOLUME_THRESHOLD

# ── 함수 re-export (11 함수) ─────────────────────────────────────────────────────
# stale_diagnostics (5 함수)
from src.engine.stale_diagnostics import (
    build_session_subscription_view,
    emit_stale_session_detail,
    refresh_stale_ccnl_cache,
    evict_expired_ccnl,
    prune_force_retry_history,
)

# stale_session_recovery (3 함수)
from src.engine.stale_session_recovery import (
    detect_silent_inactive_sessions,
    force_reconnect_session,
    delta_unsubscribe_dropped,
)

# stale_universe_guard (1 함수)
from src.engine.stale_universe_guard import evaluate_universe_guard

# stale_watcher_core (2 함수 — K stale watcher 본체 HIGH hot path)
from src.engine.stale_watcher_core import (
    check_and_resubscribe_stale,
    resubscribe_stale_priority,
)

__all__ = [
    # 상수 11 (사이클 135 SUBSCRIBE_GRACE_SECS 추가)
    "MAX_STALE_RETRIES",
    "STALE_FORCE_RETRY_AFTER_SECS",
    "STALE_FORCE_RETRY_HOURLY_CAP",
    "STALE_FRESHNESS_SECS",
    "SUBSCRIBE_GRACE_SECS",  # 사이클 135 — 구독 ACK grace period (180s)
    "UNIVERSE_LOW_VOLUME_THRESHOLD",
    "SILENT_INACTIVE_FRESH_RATIO_THRESHOLD",
    "SILENT_INACTIVE_MIN_SUBSCRIBED",
    "SILENT_INACTIVE_PERSIST_SECS",
    "SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR",
    "SILENT_INACTIVE_RECOVERY_WINDOW_SECS",
    # 함수 11
    "build_session_subscription_view",
    "emit_stale_session_detail",
    "refresh_stale_ccnl_cache",
    "evict_expired_ccnl",
    "prune_force_retry_history",
    "detect_silent_inactive_sessions",
    "force_reconnect_session",
    "delta_unsubscribe_dropped",
    "evaluate_universe_guard",
    "check_and_resubscribe_stale",
    "resubscribe_stale_priority",
]
