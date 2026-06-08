"""사이클 73 G-RT3 — R-1/R-2 logger 단독 호출 영속 보장 (Red 단계, 시정 후 PASS 유지).

옵션 A' 시정 의도:
- `write_log` 호출 제거 = logger 단독 유지 (운영 가시화 stdout/file + DB 3중 보존).
- 시정 후에도 `logger.warning([ws_reverify])` + `logger.error([ws_subscribe_reject])` 영속.

본 가드 의도:
- 회귀 차단 = 시정 과정에서 실수로 logger.* 호출까지 제거하면 운영 가시화 무력화 위험.
- Red 단계 PASS = 현재 logger 호출 영속 (시정 전 상태 유지 의무).
- Green 단계 PASS = 시정 후에도 logger 호출 영속 (write_log 만 제거).

Red 단계 검증 = 본 가드 PASS (현재 logger 호출 존재 → 영속 의무).
Green 단계 검증 = 본 가드 PASS (시정 후 logger 호출 영속 + write_log 만 제거).
"""
from __future__ import annotations

import re
from pathlib import Path


_WEBSOCKET_PY = (
    Path(__file__).resolve().parents[3] / "src" / "realtime" / "websocket.py"
)


def test_g_rt3_a_ws_reverify_logger_warning_persistence() -> None:
    """G-RT3-A: `[ws_reverify]` 사이트 `logger.warning` 호출 영속.

    시정 후에도 운영 가시화 (stdout/file + DB 3중 보존) 의무. write_log 만 제거되고
    logger.warning 은 절대 제거 금지.
    """
    source = _WEBSOCKET_PY.read_text(encoding="utf-8")
    # logger.warning 호출 + 다음 4줄 이내 [ws_reverify] 등장 (multi-line 메시지 흡수)
    pattern = re.compile(
        r"logger\.warning\s*\([^)]*\[ws_reverify\]",
        re.DOTALL,
    )
    # 좀 더 너그러운 매칭 — 라인 기준 ±3 줄
    lines = source.splitlines()
    found = False
    for i, line in enumerate(lines):
        if "logger.warning" not in line:
            continue
        # 다음 4줄까지 [ws_reverify] 등장 여부 확인
        end = min(len(lines), i + 5)
        block = "\n".join(lines[i:end])
        if "[ws_reverify]" in block:
            found = True
            break

    assert found, (
        "\n사이클 73 G-RT3-A 위반 — `[ws_reverify]` 사이트 `logger.warning` 호출 누락. "
        "옵션 A' 시정은 write_log 만 제거 — logger.warning 은 운영 가시화 의무 영속."
    )


def test_g_rt3_b_ws_subscribe_reject_logger_error_persistence() -> None:
    """G-RT3-B: `[ws_subscribe_reject]` 사이트 `logger.error` 호출 영속.

    시정 후에도 운영 가시화 의무. write_log 만 제거되고 logger.error 는 절대 제거 금지.
    """
    source = _WEBSOCKET_PY.read_text(encoding="utf-8")
    lines = source.splitlines()
    found = False
    for i, line in enumerate(lines):
        if "logger.error" not in line:
            continue
        end = min(len(lines), i + 5)
        block = "\n".join(lines[i:end])
        if "[ws_subscribe_reject]" in block or "WebSocket 구독 거절" in block:
            found = True
            break

    assert found, (
        "\n사이클 73 G-RT3-B 위반 — `[ws_subscribe_reject]` 사이트 `logger.error` "
        "호출 누락. 옵션 A' 시정은 write_log 만 제거 — logger.error 는 운영 가시화 의무 영속."
    )
