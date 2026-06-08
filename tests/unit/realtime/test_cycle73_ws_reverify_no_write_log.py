"""사이클 73 G-RT1 — `[ws_reverify]` 사이트 write_log 호출 0건 (Red 단계).

옵션 A' 시정 (사이클 72 답습 + 영역 확장):
- `src/realtime/websocket.py` 의 `[ws_reverify]` 사이트 (`_verify_subscriptions_after_reconnect`)
  에서 `logger.warning` + `await write_log` 동시 호출이 system_logs 이중 INSERT 의 root cause.
- 시정 = `write_log` 직접 호출 제거 (`logger.warning` 단독 유지 — `_DbLogHandler` 위임 단일 INSERT).

Red 단계 = `await write_log("WARNING", "[ws_reverify] ...")` 사이트 1건 잔존 → FAIL.
Green 단계 = 시정 후 0건 → PASS.

배경 (사이클 72 운영 실측):
- 사이클 72 hotfix 11 사이트 시정 후 dup_factor 3.72 → 1.34 (64% 감소).
- 잔존 1.34 = `[ws_reverify]` (R-1) + `[ws_subscribe_reject]` (R-2) + `[swing_rest_poll]` (S-1)
  3 사이트가 사이클 72 11 사이트 매트릭스에서 누락 → 사이클 73 시정 영역 확장.
"""
from __future__ import annotations

import re
from pathlib import Path


_WEBSOCKET_PY = (
    Path(__file__).resolve().parents[3] / "src" / "realtime" / "websocket.py"
)

# `[ws_reverify]` 사이트의 write_log 호출 — fire-and-forget 패턴 포괄
_WS_REVERIFY_WRITE_LOG_RE = re.compile(
    r"(?:await\s+write_log\s*\(|asyncio\.create_task\s*\(\s*write_log\s*\()"
    r".*?\[ws_reverify\]",
    re.DOTALL,
)


def test_g_rt1_ws_reverify_site_no_write_log_call() -> None:
    """G-RT1: `src/realtime/websocket.py` `[ws_reverify]` 사이트 write_log 호출 0건.

    사이클 72 옵션 A' 영역 확장 (R-1) — system_logs 이중 INSERT 영구 차단.
    `logger.warning("[ws_reverify] ...")` 단독 유지 (운영 가시화 stdout/file/DB 3중 보존).
    """
    source = _WEBSOCKET_PY.read_text(encoding="utf-8")
    lines = source.splitlines()

    # `[ws_reverify]` 문자열을 포함하는 write_log 호출 사이트 검출 (±5 줄 윈도우)
    violations: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if "write_log" not in line:
            continue
        # await write_log( 또는 write_log( 단독 호출 (fire-and-forget 포함)
        if not re.search(r"\bwrite_log\s*\(", line):
            continue
        # write_log 호출 주변 ±5 줄 윈도우에 [ws_reverify] 등장 여부 확인
        start = max(0, i - 5)
        end = min(len(lines), i + 6)
        window = "\n".join(lines[start:end])
        if "[ws_reverify]" in window:
            # logger.* 호출 또는 docstring 코멘트 라인 제외 (실 호출만)
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"'):
                continue
            if "logger." in stripped:
                continue
            # 진짜 write_log 호출 라인
            violations.append((i + 1, stripped))

    assert len(violations) == 0, (
        f"\n사이클 73 G-RT1 위반 — `[ws_reverify]` 사이트 write_log 호출 잔존:\n"
        + "\n".join(f"  L{line_no}: {snippet}" for line_no, snippet in violations)
        + "\n\n시정: src/realtime/websocket.py L385-393 영역의 try/except + "
        f"await write_log 블록 제거. logger.warning 단독 유지 = _DbLogHandler 위임 "
        f"단일 INSERT (사이클 72 옵션 A' 영역 확장)."
    )
