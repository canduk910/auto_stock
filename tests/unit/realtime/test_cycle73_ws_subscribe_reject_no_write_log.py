"""사이클 73 G-RT2 — `[ws_subscribe_reject]` 사이트 write_log 호출 0건 (Red 단계).

옵션 A' 시정 (사이클 72 답습 + 영역 확장):
- `src/realtime/websocket.py` 의 `[ws_subscribe_reject]` 사이트 (E2 거절 분기)
  에서 `logger.error` + `await write_log` 동시 호출이 system_logs 이중 INSERT 의 root cause.
- 시정 = `write_log` 직접 호출 제거 (`logger.error` 단독 유지 — `_DbLogHandler` 위임 단일 INSERT).

Red 단계 = `await write_log("ERROR", "[ws_subscribe_reject] ...")` 사이트 1건 잔존 → FAIL.
Green 단계 = 시정 후 0건 → PASS.
"""
from __future__ import annotations

import re
from pathlib import Path


_WEBSOCKET_PY = (
    Path(__file__).resolve().parents[3] / "src" / "realtime" / "websocket.py"
)


def test_g_rt2_ws_subscribe_reject_site_no_write_log_call() -> None:
    """G-RT2: `src/realtime/websocket.py` `[ws_subscribe_reject]` 사이트 write_log 호출 0건.

    사이클 72 옵션 A' 영역 확장 (R-2) — system_logs 이중 INSERT 영구 차단.
    `logger.error("WebSocket 구독 거절: ...")` 단독 유지 (운영 가시화 보존).
    `_subscriptions.discard` + `_subscriptions_acked.discard` 정합성 회복은 무관 (영속).
    """
    source = _WEBSOCKET_PY.read_text(encoding="utf-8")
    lines = source.splitlines()

    violations: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if "write_log" not in line:
            continue
        if not re.search(r"\bwrite_log\s*\(", line):
            continue
        # write_log 호출 주변 ±5 줄 윈도우에 [ws_subscribe_reject] 등장 여부 확인
        start = max(0, i - 5)
        end = min(len(lines), i + 6)
        window = "\n".join(lines[start:end])
        if "[ws_subscribe_reject]" in window:
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"'):
                continue
            if "logger." in stripped:
                continue
            violations.append((i + 1, stripped))

    assert len(violations) == 0, (
        f"\n사이클 73 G-RT2 위반 — `[ws_subscribe_reject]` 사이트 write_log 호출 잔존:\n"
        + "\n".join(f"  L{line_no}: {snippet}" for line_no, snippet in violations)
        + "\n\n시정: src/realtime/websocket.py L521-529 영역의 try/except + "
        f"await write_log 블록 제거. logger.error 단독 유지 = _DbLogHandler 위임 "
        f"단일 INSERT (사이클 72 옵션 A' 영역 확장)."
    )
