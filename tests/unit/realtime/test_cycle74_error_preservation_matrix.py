"""사이클 74 의제 #B — ERROR 보존 매트릭스 영속 (사이클 29 005935 LMS chain 진단 의무).

본 파일은 *영속 영역 회귀 가드*. Red 단계 = 모든 케이스 PASS (사이클 16/24/29/42/72/73 영속).
Green 단계 = 사이클 74 옵션 E-1 aggregator 도입 후에도 5 영역 ERROR/WARNING 사이트 영속 보존.

영속 의무 ERROR 사이트 매트릭스:
| 사이트 | 사이클 | 레벨 | prefix | aggregation 흡수 |
|--------|-------|------|--------|----------------|
| `_handle_raw` 거절 | 73 R-2 | ERROR | `[ws_subscribe_reject]` | ❌ individual 영속 |
| silent inactive force_reconnect | 24/29-R2 | WARNING | `[silent_inactive_force_reconnect]` | ❌ individual 영속 |
| heartbeat timeout | 42 | WARNING | `Heartbeat 타임아웃` | ❌ individual 영속 |
| AES key skip | 16 | DEBUG | `[aes_key_skip]` | ❌ individual 영속 (DEBUG) |
| `_verify_subscriptions_after_reconnect` 미수신 | 73 R-1 | WARNING | `[ws_reverify]` | ❌ individual 영속 |
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_REALTIME_ROOT = Path(__file__).resolve().parents[3] / "src" / "realtime"


# ===========================================================================
# G-ERR1: `[ws_subscribe_reject]` (logger.error, 사이클 73 R-2) individual 영속
# ===========================================================================
def test_g_err1_ws_subscribe_reject_logger_error_preserved():
    """G-ERR1: `src/realtime/websocket.py::_handle_raw` 거절 분기에
    `[ws_subscribe_reject]` logger.error 영속.

    사이클 73 R-2 시정 영속 + 사이클 29 005935 LMS chain 진단 핵심.
    """
    ws_py = _REALTIME_ROOT / "websocket.py"
    source = ws_py.read_text(encoding="utf-8")

    assert "[ws_subscribe_reject]" in source, (
        "G-ERR1: `[ws_subscribe_reject]` prefix 누락 — 사이클 73 R-2 영속 영역 위반"
    )
    # logger.error 호출 동반 (거절 분기 핵심)
    assert "logger.error(" in source, (
        "G-ERR1: logger.error 호출 부재 — 사이클 73 R-2 영속 영역 위반"
    )
    # 거절 응답 + 영속 키워드
    assert "_is_rejection_response" in source, (
        "G-ERR1: `_is_rejection_response` 가드 영속 의무"
    )


# ===========================================================================
# G-ERR2: silent inactive force_reconnect (사이클 24 / 29-R2) individual 영속
# ===========================================================================
def test_g_err2_silent_inactive_force_reconnect_preserved():
    """G-ERR2: `force_reconnect_session` 함수 + `[silent_inactive_*]` 영속.

    사이클 24 (세션 강제 reconnect) + 사이클 29-R2 (silent inactive 3중 가드)
    영속 — KIS LMS/앱키 정지 위험 직접 영역.
    """
    recovery_py = (
        Path(__file__).resolve().parents[3]
        / "src" / "engine" / "stale_session_recovery.py"
    )
    source = recovery_py.read_text(encoding="utf-8")

    # 사이클 24 force_reconnect 함수 영속
    assert "force_reconnect_session" in source, (
        "G-ERR2: `force_reconnect_session` 함수 누락 — 사이클 24 영속 위반"
    )
    # 사이클 29-R2 silent inactive 감지 영속
    assert "detect_silent_inactive_sessions" in source, (
        "G-ERR2: `detect_silent_inactive_sessions` 함수 누락 — 사이클 29-R2 영속 위반"
    )
    # silent inactive prefix 영속 (logger 운영 가시화)
    assert (
        "silent_inactive_force_reconnect" in source
        or "[silent_inactive" in source
    ), (
        "G-ERR2: `silent_inactive` 운영 가시화 prefix 누락 — KIS LMS 위험 영역"
    )


# ===========================================================================
# G-ERR3: heartbeat timeout (사이클 42) individual 영속
# ===========================================================================
def test_g_err3_heartbeat_timeout_warning_preserved():
    """G-ERR3: `_receive_loop` heartbeat timeout 분기에 logger.warning 영속.

    사이클 42 영속 — `_heartbeat_timeout_count += 1` + WARNING 5분 통계 통합.
    aggregation 흡수 금지 — 결함 가시화 영속.
    """
    ws_py = _REALTIME_ROOT / "websocket.py"
    source = ws_py.read_text(encoding="utf-8")

    # 사이클 42 카운트 영속
    assert "_heartbeat_timeout_count" in source, (
        "G-ERR3: `_heartbeat_timeout_count` 필드 누락 — 사이클 42 영속 위반"
    )
    # WARNING emit 영속
    assert "Heartbeat 타임아웃" in source, (
        "G-ERR3: Heartbeat 타임아웃 WARNING 누락 — 사이클 42 영속 위반"
    )
    # 5분 통계 통합 (사이클 42)
    assert "_heartbeat_metrics_emit_once" in source or "[ws_heartbeat]" in source, (
        "G-ERR3: `_heartbeat_metrics_emit_once` 헬퍼 + `[ws_heartbeat]` 5분 통계 영속 의무"
    )


# ===========================================================================
# G-ERR4: AES key skip / 수신 (사이클 16) individual 영속
# ===========================================================================
def test_g_err4_aes_key_handling_preserved():
    """G-ERR4: AES 키 수신 / skip 분기 영속 (사이클 16 영속).

    `[aes_key_skip]` DEBUG + `AES 키 수신: tr_id=...` INFO 메인+체결통보만.
    보조 세션 / 시세 SUBSCRIBE SUCCESS AES 키 격리 영속 — 체결통보 복호화 race 차단.
    """
    ws_py = _REALTIME_ROOT / "websocket.py"
    source = ws_py.read_text(encoding="utf-8")

    # 사이클 16 이중 가드 영속
    assert "_EXECUTION_NOTICE_TR_IDS" in source, (
        "G-ERR4: `_EXECUTION_NOTICE_TR_IDS` 모듈 상수 누락 — 사이클 16 영속 위반"
    )
    assert "[aes_key_skip]" in source, (
        "G-ERR4: `[aes_key_skip]` DEBUG prefix 누락 — 사이클 16 영속 위반"
    )
    # 메인 + 체결통보 가드 영속
    assert "self.is_main and tr_id in _EXECUTION_NOTICE_TR_IDS" in source, (
        "G-ERR4: 메인+체결통보 이중 가드 누락 — 사이클 16 영속 위반"
    )


# ===========================================================================
# G-ERR5: `[ws_reverify]` WARNING (사이클 73 R-1) individual 영속
# ===========================================================================
def test_g_err5_ws_reverify_warning_preserved():
    """G-ERR5: `_verify_subscriptions_after_reconnect` 의 `[ws_reverify]` WARNING 영속.

    사이클 73 R-1 시정 영속 — F1 재연결 후 silent inactive 진단.
    preview cap 10 (사이클 73 R-2 영속) + write_log 직접 호출 제거 (_DbLogHandler 위임).
    """
    ws_py = _REALTIME_ROOT / "websocket.py"
    source = ws_py.read_text(encoding="utf-8")

    # 사이클 73 R-1 영속
    assert "[ws_reverify]" in source, (
        "G-ERR5: `[ws_reverify]` prefix 누락 — 사이클 73 R-1 영속 위반"
    )
    # `_verify_subscriptions_after_reconnect` 함수 영속 (F1 재연결 자동 검증)
    assert "_verify_subscriptions_after_reconnect" in source, (
        "G-ERR5: `_verify_subscriptions_after_reconnect` 함수 누락 — F1 영속 위반"
    )
    # logger.warning 호출 영속 (미수신 시)
    assert "logger.warning" in source, (
        "G-ERR5: logger.warning 호출 누락 — 사이클 73 R-1 영속 위반"
    )
