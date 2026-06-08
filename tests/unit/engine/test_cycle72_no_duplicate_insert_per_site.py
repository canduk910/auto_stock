"""사이클 72 G-A1 ~ G-A11 — 11 사이트 이중 INSERT 차단 (Red 단계).

각 사이트에서 동일 메시지의 `logger.info/warning(...)` + `await write_log(...)`
이중 호출이 있으면 system_logs INSERT 2건/메시지 폭주.

옵션 A' (사용자 결정): `logger.*` 만 유지 + `write_log` 호출 제거 → `_DbLogHandler`
위임 경로 단일 INSERT 보장 + G-D 500ms dedupe 캐시 추가 안전망.

본 모듈은 각 사이트의 *소스 정적 분석* 으로 `write_log` 호출 0건을 검증한다.
Green 단계 이전에는 11/11 모두 FAIL (현재 운영 코드 그대로).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


def _src_root() -> Path:
    return Path(__file__).resolve().parents[3] / "src"


def _read(rel_path: str) -> str:
    return (_src_root() / rel_path).read_text(encoding="utf-8")


# `await write_log(` 또는 `await _write_log(` 또는 `asyncio.create_task(_write_log(`
# (앞 공백/들여쓰기 무시) — fire-and-forget 패턴까지 포함.
_WRITE_LOG_CALL_RE = re.compile(
    r"(?:await\s+_?write_log\s*\(|asyncio\.create_task\s*\(\s*_?write_log\s*\()"
)


def _count_write_log_calls_near_prefix(source: str, prefix: str) -> int:
    """source 중 prefix(`[X]`) 가 등장하는 라인 전후 ±20 줄 내에서
    write_log/asyncio.create_task 호출 수를 센다.

    동일 사이트의 logger.info(... prefix ...) 와 write_log(... prefix ...) 가
    함께 있는 패턴을 잡기 위해 ±20 줄 윈도우 사용.
    """
    lines = source.splitlines()
    prefix_line_idxs = [
        i for i, line in enumerate(lines) if prefix in line
    ]
    count = 0
    seen_call_lines: set[int] = set()
    for pidx in prefix_line_idxs:
        start = max(0, pidx - 20)
        end = min(len(lines), pidx + 21)
        for j in range(start, end):
            if j in seen_call_lines:
                continue
            if _WRITE_LOG_CALL_RE.search(lines[j]):
                # write_log 호출이 동일 prefix 텍스트를 메시지에 포함하는지 확인
                # — ±20 줄 내 어떤 write_log 든 (멀티라인 f-string) 인접 prefix 와 연관
                window_text = "\n".join(
                    lines[max(0, j - 6):min(len(lines), j + 8)]
                )
                if prefix in window_text:
                    seen_call_lines.add(j)
                    count += 1
    return count


# ── G-A1 ~ G-A11 — 사이트별 케이스 ──────────────────────────────────────────────


def test_g_a1_ws_heartbeat_no_duplicate_write_log() -> None:
    """G-A1: src/realtime/websocket.py `[ws_heartbeat]` write_log 호출 0건."""
    source = _read("realtime/websocket.py")
    count = _count_write_log_calls_near_prefix(source, "[ws_heartbeat]")
    assert count == 0, (
        f"[ws_heartbeat] 사이트에 write_log 호출 {count}건 잔존 — "
        f"logger.info 와 이중 INSERT 결함 (옵션 A' 시정 필요)"
    )


def test_g_a2_stale_force_retry_no_duplicate_write_log() -> None:
    """G-A2: src/engine/stale_watcher_core.py `[stale_force_retry]` write_log 0건."""
    source = _read("engine/stale_watcher_core.py")
    count = _count_write_log_calls_near_prefix(source, "[stale_force_retry]")
    assert count == 0, (
        f"[stale_force_retry] 사이트에 write_log 호출 {count}건 잔존 — "
        f"logger.info 와 이중 INSERT (사이클 71 23x dup root cause)"
    )


def test_g_a3_stale_watcher_no_duplicate_write_log() -> None:
    """G-A3: src/engine/stale_watcher_core.py `[stale_watcher]` write_log 0건."""
    source = _read("engine/stale_watcher_core.py")
    count = _count_write_log_calls_near_prefix(source, "[stale_watcher]")
    # `[stale_watcher_detail]` / `[stale_watcher]` 별도 — 부분 일치는 detail 도 포함되지만
    # detail 은 별도 모듈(diagnostics)에 있으므로 본 파일에는 순수 `[stale_watcher]` 만 잔존.
    # subscribed=... 본문 라인의 prefix 한정.
    assert count == 0, (
        f"[stale_watcher] 사이트에 write_log 호출 {count}건 잔존 — "
        f"logger.info 와 이중 INSERT (사이클 71 7.33x dup)"
    )


def test_g_a4_stale_force_retry_cap_no_duplicate_write_log() -> None:
    """G-A4: src/engine/stale_watcher_core.py `[stale_force_retry_cap]` write_log 0건."""
    source = _read("engine/stale_watcher_core.py")
    count = _count_write_log_calls_near_prefix(source, "[stale_force_retry_cap]")
    assert count == 0, (
        f"[stale_force_retry_cap] 사이트에 write_log 호출 {count}건 잔존 — "
        f"logger.warning 와 이중 INSERT (WARNING 도 INSERT 됨)"
    )


def test_g_a5_stale_priority_resubscribe_no_duplicate_write_log() -> None:
    """G-A5: src/engine/stale_watcher_core.py `[stale_priority_resubscribe]` write_log 0건."""
    source = _read("engine/stale_watcher_core.py")
    count = _count_write_log_calls_near_prefix(
        source, "[stale_priority_resubscribe]"
    )
    assert count == 0, (
        f"[stale_priority_resubscribe] 사이트에 write_log 호출 {count}건 잔존 — "
        f"5분 우선 재구독 핵심 hot path 이중 INSERT 결함"
    )


def test_g_a6_stale_watcher_detail_no_duplicate_write_log() -> None:
    """G-A6: src/engine/stale_diagnostics.py `[stale_watcher_detail]` write_log 0건."""
    source = _read("engine/stale_diagnostics.py")
    count = _count_write_log_calls_near_prefix(source, "[stale_watcher_detail]")
    assert count == 0, (
        f"[stale_watcher_detail] 사이트에 write_log 호출 {count}건 잔존 — "
        f"asyncio.create_task(_write_log) fire-and-forget 도 이중 INSERT "
        f"(사이클 71 확정적 2.00x dup root cause)"
    )


def test_g_a7_silent_inactive_recovery_cap_no_duplicate_write_log() -> None:
    """G-A7: src/engine/stale_session_recovery.py `[silent_inactive_recovery_cap]` write_log 0건."""
    source = _read("engine/stale_session_recovery.py")
    count = _count_write_log_calls_near_prefix(
        source, "[silent_inactive_recovery_cap]"
    )
    assert count == 0, (
        f"[silent_inactive_recovery_cap] 사이트에 write_log 호출 {count}건 잔존 — "
        f"logger.warning 와 이중 INSERT (KIS LMS chain WARNING 도 dup)"
    )


def test_g_a8_silent_inactive_force_reconnect_no_duplicate_write_log() -> None:
    """G-A8: src/engine/stale_session_recovery.py `[silent_inactive_force_reconnect]` write_log 0건."""
    source = _read("engine/stale_session_recovery.py")
    count = _count_write_log_calls_near_prefix(
        source, "[silent_inactive_force_reconnect]"
    )
    assert count == 0, (
        f"[silent_inactive_force_reconnect] 사이트에 write_log 호출 {count}건 잔존 — "
        f"세션 강제 reconnect WARNING 이중 INSERT 결함"
    )


def test_g_a9_scan_loop_delta_no_duplicate_write_log() -> None:
    """G-A9: src/engine/stale_session_recovery.py `[scan_loop_delta]` write_log 0건."""
    source = _read("engine/stale_session_recovery.py")
    count = _count_write_log_calls_near_prefix(source, "[scan_loop_delta]")
    assert count == 0, (
        f"[scan_loop_delta] 사이트에 write_log 호출 {count}건 잔존 — "
        f"logger.info 와 이중 INSERT (5분 주기 hot path 매번 2건)"
    )


def test_g_a10_universe_excluded_no_duplicate_write_log() -> None:
    """G-A10: src/engine/stale_universe_guard.py `[universe_excluded]` write_log 0건."""
    source = _read("engine/stale_universe_guard.py")
    count = _count_write_log_calls_near_prefix(source, "[universe_excluded]")
    assert count == 0, (
        f"[universe_excluded] 사이트에 write_log 호출 {count}건 잔존 — "
        f"보유/익일청산 절대 보호 universe guard INFO 이중 INSERT"
    )


def test_g_a11_priority_drop_no_duplicate_write_log() -> None:
    """G-A11: src/engine/scanner.py `[priority_drop]` write_log 0건."""
    source = _read("engine/scanner.py")
    count = _count_write_log_calls_near_prefix(source, "[priority_drop]")
    assert count == 0, (
        f"[priority_drop] 사이트에 write_log 호출 {count}건 잔존 — "
        f"slot drop WARNING 이중 INSERT (drop 발생 시 매번 2건)"
    )
