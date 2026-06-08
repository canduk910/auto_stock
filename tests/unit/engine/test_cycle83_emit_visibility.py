"""사이클 83 G-OP2 — `[scan_pool_eager_refresh]` 1행 emit 가시화 검증.

명세 (`_workspace/red/cycle83_scan_pool_eager_refresh.md`):

A1 자문 권고: 5분 윈도우 누적 통계 collector → flush 시 1행 emit:
  `[scan_pool_eager_refresh] window=300s candidates=N refreshed=M skipped=K
   failed=L elapsed_ms=E`

사이클 74 sampling 패턴 답습 (`[swing_rest_poll_summary]` / `[stale_watcher_summary]`).

기대 동작 (Green, 사이클 84):
- 5건 stats 누적 → flush 1회 → 1행 emit
- prefix `[scan_pool_eager_refresh]` 포함
- 키: window / candidates / refreshed / skipped / failed / elapsed_ms

Red 단계 (사이클 83):
- 신규 함수 미존재 → FAIL.

영속:
- 사이클 74 G-SP4 / G-SW1 패턴 답습
- 사이클 78 G-FL1~FL4 영속
- 운영 가시화 영구 가드 (silent 결함 영구 차단)
"""
from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.unit


def test_g_op2_eager_refresh_summary_emit_visibility(caplog):
    """G-OP2: `[scan_pool_eager_refresh]` 1행 emit 가시화 검증.

    검증 매트릭스:
    1. `record_scan_pool_eager_refresh()` 5회 호출 누적
    2. `flush_scan_pool_eager_refresh_collector()` 1회 호출
    3. caplog 에 `[scan_pool_eager_refresh]` prefix INFO 로그 ≥ 1건
    4. 로그 메시지에 candidates / refreshed / skipped / elapsed_ms 키 포함

    Red 상태 (사이클 83): 신규 함수 미존재 → FAIL.

    Green (사이클 84):
    - scanner.py 모듈 전역 record/flush 함수 도입
    - flush 시 logger.info("[scan_pool_eager_refresh] ...") 1행 emit

    영속 의무:
    - 사이클 74 G-SP4 패턴 답습 (`[swing_rest_poll_summary]`)
    - 사이클 78 G-FL1 영속
    - 운영 가시화 영구 가드
    """
    try:
        from src.engine import scanner as _scanner_mod
        record_fn = getattr(_scanner_mod, "record_scan_pool_eager_refresh", None)
        flush_fn = getattr(_scanner_mod, "flush_scan_pool_eager_refresh_collector", None)
    except ImportError:
        pytest.fail("\n사이클 83 G-OP2 Red — scanner 모듈 import 실패.")

    if record_fn is None or flush_fn is None:
        pytest.fail(
            f"\n사이클 83 G-OP2 Red 상태 — record/flush 함수 미도입:\n"
            f"  record_scan_pool_eager_refresh: {record_fn!r}\n"
            f"  flush_scan_pool_eager_refresh_collector: {flush_fn!r}\n\n"
            f"  Green (사이클 84): backend-dev 가 scanner.py 모듈 전역 +\n"
            f"  record/flush 함수 도입 의무 (사이클 74 패턴 답습)."
        )

    # collector 초기화
    collector = getattr(_scanner_mod, "_scan_pool_eager_refresh_collector", [])
    collector.clear()

    # 5건 누적
    for i in range(5):
        record_fn({
            "candidates": 30 + i,
            "refreshed": 10 + i,
            "skipped": 18,
            "failed": 0,
            "elapsed_ms": 1500 + i * 100,
        })

    # caplog 설정 + flush
    caplog.set_level(logging.INFO, logger="src.engine.scanner")
    flush_fn()

    # 본 가드 1: prefix 로그 ≥ 1건
    log_messages = [r.message for r in caplog.records]
    summary_logs = [
        msg for msg in log_messages if "[scan_pool_eager_refresh]" in msg
    ]
    assert summary_logs, (
        f"\n사이클 83 G-OP2 위반 — `[scan_pool_eager_refresh]` prefix 로그 발화 0건:\n"
        f"  전체 로그: {log_messages}\n\n"
        f"  Green: flush 시 logger.info(\"[scan_pool_eager_refresh] window=300s ...\") "
        f"1행 emit 의무 (사이클 74 패턴 답습)."
    )

    # 본 가드 2: 핵심 키 포함
    summary_msg = summary_logs[0]
    required_keys = ["candidates", "refreshed"]
    missing_keys = [k for k in required_keys if k not in summary_msg]
    assert not missing_keys, (
        f"\n사이클 83 G-OP2 위반 — emit 메시지 핵심 키 누락:\n"
        f"  메시지: {summary_msg}\n"
        f"  누락 키: {missing_keys}\n\n"
        f"  Green: `[scan_pool_eager_refresh] window=300s candidates=N refreshed=M "
        f"skipped=K failed=L elapsed_ms=E` 형식 의무."
    )
