"""사이클 67 Red — `stale_manager.py` sub-module 분해 G-1~G-5 회귀 가드 (5 케이스).

> **설계 카드**: `_workspace/cycle67_stale_manager_decomposition_design_card.md`
> **자문 응답**: `_workspace/cycle67_stale_manager_decomposition_domain_response.md`
> **선행 의존**: 사이클 60 A1 / 61 A2 / 63 A3 / 66 시정 (11 함수 + 10 상수 + 78 회귀 가드 영속)
> **위험 등급**: MEDIUM (행위 보존 refactor, 단 78 케이스 영향 영역 + K stale watcher HIGH hot path)

G-1~G-5 = 기본 분해 검증 (sub-module 파일 존재 + 함수 export + facade 보존):
- G-1: `stale_diagnostics.py` 신규 + 5 함수 export
- G-2: `stale_session_recovery.py` 신규 + 3 함수 export
- G-3: `stale_universe_guard.py` 신규 + 1 함수 export
- G-4: `stale_watcher_core.py` 신규 + 2 함수 export
- G-5: `stale_manager.py` facade 영속 + 11 함수 re-export 보장

Red 시점 결과 (분해 전):
- G-1, G-2, G-3, G-4: FAIL (sub-module 파일 미존재)
- G-5: PASS (현재 stale_manager.py 가 11 함수 모두 보유 — 자연 통과)

Green 시점 결과 (분해 후):
- G-1~G-5: 전수 PASS
"""
from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# G-1 — `stale_diagnostics.py` 신규 + 5 함수 export
# ===========================================================================
def test_G1_stale_diagnostics_module_exports_5_functions():
    """G-1: `src/engine/stale_diagnostics.py` 모듈 존재 + 5 함수 export 의무.

    분해 청사진 (사이클 67 §2.2):
    - build_session_subscription_view (사이클 60)
    - emit_stale_session_detail (사이클 60)
    - refresh_stale_ccnl_cache (사이클 60)
    - evict_expired_ccnl (사이클 60)
    - prune_force_retry_history (사이클 60)

    Red 단계: ModuleNotFoundError = FAIL.
    Green 단계: import 후 5 함수 모두 callable = PASS.
    """
    try:
        mod = importlib.import_module("src.engine.stale_diagnostics")
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"`src/engine/stale_diagnostics.py` 신규 모듈 누락. "
            f"사이클 67 분해 청사진 §2.1 의무. exc={exc}"
        )

    required_funcs = [
        "build_session_subscription_view",
        "emit_stale_session_detail",
        "refresh_stale_ccnl_cache",
        "evict_expired_ccnl",
        "prune_force_retry_history",
    ]
    for name in required_funcs:
        assert hasattr(mod, name), (
            f"`stale_diagnostics.py` 에 `{name}` 함수 export 누락. "
            f"사이클 60 A1 이주 함수 분해 청사진 위반"
        )
        assert callable(getattr(mod, name)), f"`{name}` 가 callable 이 아님"


# ===========================================================================
# G-2 — `stale_session_recovery.py` 신규 + 3 함수 export
# ===========================================================================
def test_G2_stale_session_recovery_module_exports_3_functions():
    """G-2: `src/engine/stale_session_recovery.py` 모듈 존재 + 3 함수 export 의무.

    분해 청사진 (사이클 67 §2.2):
    - detect_silent_inactive_sessions (사이클 61)
    - force_reconnect_session (사이클 61 — **KIS LMS/앱키 정지 위험 직접 영역**)
    - delta_unsubscribe_dropped (사이클 61)

    Red 단계: ModuleNotFoundError = FAIL.
    Green 단계: import 후 3 함수 모두 callable = PASS.
    """
    try:
        mod = importlib.import_module("src.engine.stale_session_recovery")
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"`src/engine/stale_session_recovery.py` 신규 모듈 누락. "
            f"사이클 67 분해 청사진 §2.1 의무. exc={exc}"
        )

    required_funcs = [
        "detect_silent_inactive_sessions",
        "force_reconnect_session",
        "delta_unsubscribe_dropped",
    ]
    for name in required_funcs:
        assert hasattr(mod, name), (
            f"`stale_session_recovery.py` 에 `{name}` 함수 export 누락. "
            f"사이클 61 A2 이주 함수 분해 청사진 위반"
        )
        assert callable(getattr(mod, name)), f"`{name}` 가 callable 이 아님"


# ===========================================================================
# G-3 — `stale_universe_guard.py` 신규 + 1 함수 export
# ===========================================================================
def test_G3_stale_universe_guard_module_exports_1_function():
    """G-3: `src/engine/stale_universe_guard.py` 모듈 존재 + 1 함수 export 의무.

    분해 청사진 (사이클 67 §2.2):
    - evaluate_universe_guard (사이클 32 R4 + 사이클 61)
      — **보유/익일청산 절대 보호 영역**.

    Red 단계: ModuleNotFoundError = FAIL.
    Green 단계: import 후 함수 callable = PASS.
    """
    try:
        mod = importlib.import_module("src.engine.stale_universe_guard")
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"`src/engine/stale_universe_guard.py` 신규 모듈 누락. "
            f"사이클 67 분해 청사진 §2.1 의무. exc={exc}"
        )

    assert hasattr(mod, "evaluate_universe_guard"), (
        "`stale_universe_guard.py` 에 `evaluate_universe_guard` 함수 export 누락. "
        "사이클 32 R4 + 사이클 61 A2 이주 함수 분해 청사진 위반"
    )
    assert callable(mod.evaluate_universe_guard)


# ===========================================================================
# G-4 — `stale_watcher_core.py` 신규 + 2 함수 export (K stale watcher 본체 HIGH)
# ===========================================================================
def test_G4_stale_watcher_core_module_exports_2_functions():
    """G-4: `src/engine/stale_watcher_core.py` 모듈 존재 + 2 함수 export 의무.

    분해 청사진 (사이클 67 §2.2):
    - check_and_resubscribe_stale (사이클 63 — **K stale watcher 본체 HIGH hot path**)
    - resubscribe_stale_priority (사이클 63 + 66 시정 — **사이클 29 005935 사고 차단 영역**)

    K stale watcher = 영구 hot path 360 회/일 + KIS LMS/앱키 정지 chain 직접 영역.

    Red 단계: ModuleNotFoundError = FAIL.
    Green 단계: import 후 2 함수 모두 callable = PASS.
    """
    try:
        mod = importlib.import_module("src.engine.stale_watcher_core")
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"`src/engine/stale_watcher_core.py` 신규 모듈 누락. "
            f"사이클 67 분해 청사진 §2.1 의무 (K stale watcher 본체 HIGH). exc={exc}"
        )

    required_funcs = [
        "check_and_resubscribe_stale",
        "resubscribe_stale_priority",
    ]
    for name in required_funcs:
        assert hasattr(mod, name), (
            f"`stale_watcher_core.py` 에 `{name}` 함수 export 누락. "
            f"사이클 63 A3 이주 함수 분해 청사진 위반 (K stale watcher 본체 HIGH)"
        )
        assert callable(getattr(mod, name)), f"`{name}` 가 callable 이 아님"


# ===========================================================================
# G-5 — `stale_manager.py` facade 보존 + 11 함수 re-export 보장
# ===========================================================================
def test_G5_stale_manager_facade_re_exports_11_functions():
    """G-5: `src/engine/stale_manager.py` facade 영속 + 11 함수 + 10 상수 re-export 보장.

    Q1 옵션 A (facade 보존) + Q5 옵션 A (scheduler.py 11 wrapper 변경 0 의무):
    - scheduler.py 11 wrapper 가 `from src.engine import stale_manager` 형태 영속
    - facade re-export 21 항목 (11 함수 + 10 상수) 영속 = wrapper 변경 0 보장
    - 자문 응답 §2 Q1 답변 + §6 Q5 답변 채택

    Red 단계: PASS (현재 stale_manager.py 가 11 함수 모두 보유 — 자연 통과)
    Green 단계: PASS (4 sub-module 분해 후 facade re-export 영속)

    본 가드는 Red/Green 무관 *영속 의무* — 분해 과정 중 누락 발생 시 즉시 FAIL.
    """
    from src.engine import stale_manager

    # 11 함수 re-export 영속
    required_funcs = [
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
    for name in required_funcs:
        assert hasattr(stale_manager, name), (
            f"`stale_manager.py` facade 에 `{name}` re-export 누락. "
            f"사이클 67 Q1 옵션 A facade 보존 의무 위반 + scheduler.py 11 wrapper 영향"
        )
        assert callable(getattr(stale_manager, name)), (
            f"`{name}` 가 callable 이 아님 (facade re-export 형태 위반)"
        )

    # 10 상수 re-export 영속 (사이클 60 A1 5 + 사이클 61 A2 5)
    required_constants = [
        "MAX_STALE_RETRIES",
        "STALE_FORCE_RETRY_AFTER_SECS",
        "STALE_FORCE_RETRY_HOURLY_CAP",
        "STALE_FRESHNESS_SECS",
        "UNIVERSE_LOW_VOLUME_THRESHOLD",
        "SILENT_INACTIVE_FRESH_RATIO_THRESHOLD",
        "SILENT_INACTIVE_MIN_SUBSCRIBED",
        "SILENT_INACTIVE_PERSIST_SECS",
        "SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR",
        "SILENT_INACTIVE_RECOVERY_WINDOW_SECS",
    ]
    for name in required_constants:
        assert hasattr(stale_manager, name), (
            f"`stale_manager.py` facade 에 상수 `{name}` re-export 누락. "
            f"scheduler.py L92 re-export 호환 의무 (사이클 60 A1 영속) 위반"
        )
