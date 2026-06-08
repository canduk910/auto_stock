"""사이클 74 의제 2-A — `[swing_rest_poll]` 5분 aggregation (옵션 C).

Red 단계: aggregator helper 미존재로 G-SP1~SP4 모두 FAIL.
Green 단계: backend-dev 가 `_swing_rest_poll_collector` + `_flush_swing_rest_poll_collector`
+ `[swing_rest_poll_summary]` prefix 5분 주기 emit 헬퍼 도입 후 PASS.

영속 의무:
- 사이클 17 KIS LMS chain 차단 + 사이클 38 명문화 (tradable_boards 매수 진입 전용)
- 사이클 42 `[ws_heartbeat]` 5분 통계 답습 패턴 (HEARTBEAT_METRICS_INTERVAL_SECS=300)
- 사이클 73 S-1 (`_run_swing_rest_poll_once` write_log 직접 호출 제거 영속)
- donchian_swing 60s 주기 → 5분 윈도우 = 5 회 poll 1 행 = 80% 감소
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ===========================================================================
# 공통 — collector helper 진입점 (Green 후 backend-dev 가 import 가능하게 함)
# ===========================================================================
def _import_collector():
    """Green 후: src.engine.scheduler 또는 src.engine.swing_rest_poll_aggregator
    모듈에서 `_swing_rest_poll_collector` / `record_swing_rest_poll` /
    `flush_swing_rest_poll_collector` 등을 import 한다.

    Red 단계 = 미존재로 ImportError / AttributeError → 케이스 FAIL.
    """
    from src.engine import scheduler as _sched
    return _sched


# ===========================================================================
# G-SP1: 5분 윈도우 내 5회 poll → `[swing_rest_poll_summary]` 1행 (80% 감소)
# ===========================================================================
def test_g_sp1_swing_rest_poll_5min_aggregation_emits_one_summary_row(caplog):
    """G-SP1: 5분 윈도우 5 회 poll → `[swing_rest_poll_summary]` 1행 emit.

    개별 `[swing_rest_poll]` INFO 5 회 → `[swing_rest_poll_summary]` 1 행 = 80% 감소.
    """
    import logging
    sched = _import_collector()

    # Green 후 backend-dev 가 도입할 헬퍼:
    record = getattr(sched, "record_swing_rest_poll", None)
    flush = getattr(sched, "flush_swing_rest_poll_collector", None)
    assert record is not None, (
        "사이클 74 G-SP1: `record_swing_rest_poll` 헬퍼 미존재 — "
        "옵션 C aggregator 도입 의무 (Green 발주 대상)"
    )
    assert flush is not None, (
        "사이클 74 G-SP1: `flush_swing_rest_poll_collector` 헬퍼 미존재"
    )

    # 5 회 poll 통계 등록 (실제 운영 = 60s 주기)
    for i in range(5):
        record({
            "candidates": 10 + i,
            "held": 2,
            "pending": 1,
            "updated": 9 + i,
            "failed": 1,
            "elapsed_ms": 1200 + i * 100,
        })

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    flush()

    summary_lines = [
        r.message for r in caplog.records
        if "[swing_rest_poll_summary]" in r.message
    ]
    assert len(summary_lines) == 1, (
        f"G-SP1: `[swing_rest_poll_summary]` 1행 emit 의무 — actual={len(summary_lines)}"
    )

    # 개별 `[swing_rest_poll]` (summary 아닌) INFO 폭주 영역 0건
    individual_lines = [
        r.message for r in caplog.records
        if r.message.startswith("[swing_rest_poll] ")
    ]
    assert len(individual_lines) == 0, (
        f"G-SP1: 개별 `[swing_rest_poll]` INFO 폭주 0건 의무 — actual={len(individual_lines)}"
    )


# ===========================================================================
# G-SP2: 윈도우 통계 정확 (polls/candidates_avg/max/total_held/elapsed_ms_avg)
# ===========================================================================
def test_g_sp2_swing_rest_poll_summary_stats_accurate(caplog):
    """G-SP2: 5 회 poll 후 flush 시 통계 키워드 정확."""
    import logging
    sched = _import_collector()

    record = getattr(sched, "record_swing_rest_poll", None)
    flush = getattr(sched, "flush_swing_rest_poll_collector", None)
    assert record is not None and flush is not None, (
        "사이클 74 G-SP2: 헬퍼 미존재"
    )

    samples = [
        {"candidates": 10, "held": 2, "pending": 0, "updated": 10, "failed": 0, "elapsed_ms": 1000},
        {"candidates": 20, "held": 2, "pending": 1, "updated": 20, "failed": 0, "elapsed_ms": 2000},
        {"candidates": 30, "held": 2, "pending": 1, "updated": 28, "failed": 2, "elapsed_ms": 1500},
        {"candidates": 15, "held": 3, "pending": 0, "updated": 15, "failed": 0, "elapsed_ms": 1200},
        {"candidates": 25, "held": 3, "pending": 1, "updated": 24, "failed": 1, "elapsed_ms": 1800},
    ]
    for s in samples:
        record(s)

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    flush()

    summary_lines = [
        r.message for r in caplog.records
        if "[swing_rest_poll_summary]" in r.message
    ]
    assert len(summary_lines) == 1
    msg = summary_lines[0]

    for keyword in ("polls=5", "candidates_avg=", "max=", "total_held=",
                    "elapsed_ms_avg="):
        assert keyword in msg, (
            f"G-SP2: 키워드 `{keyword}` 누락\nactual: {msg}"
        )

    # max=30 (candidates 최대값)
    assert "max=30" in msg, f"G-SP2: max=30 매칭 실패 — actual: {msg}"


# ===========================================================================
# G-SP3: 윈도우 종료 직후 첫 poll 다시 5분 누적 (freezegun)
# ===========================================================================
def test_g_sp3_swing_rest_poll_window_resets_after_flush(caplog):
    """G-SP3: flush 후 collector 초기화 + 다음 poll 1 회 시 새 윈도우 1 행 누적."""
    import logging
    sched = _import_collector()

    record = getattr(sched, "record_swing_rest_poll", None)
    flush = getattr(sched, "flush_swing_rest_poll_collector", None)
    assert record is not None and flush is not None, (
        "사이클 74 G-SP3: 헬퍼 미존재"
    )

    for _ in range(5):
        record({"candidates": 10, "held": 1, "pending": 0, "updated": 10,
                "failed": 0, "elapsed_ms": 1000})
    flush()  # 첫 윈도우 flush

    caplog.clear()

    # 다음 윈도우 첫 poll 등록
    record({"candidates": 5, "held": 1, "pending": 0, "updated": 5,
            "failed": 0, "elapsed_ms": 500})

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    flush()

    summary_lines = [
        r.message for r in caplog.records
        if "[swing_rest_poll_summary]" in r.message
    ]
    assert len(summary_lines) == 1, (
        f"G-SP3: 두 번째 flush 후 1 행 emit 의무 — actual={len(summary_lines)}"
    )
    assert "polls=1" in summary_lines[0], (
        f"G-SP3: 두 번째 윈도우 polls=1 의무 — actual: {summary_lines[0]}"
    )


# ===========================================================================
# G-SP4: disconnect/cancel 시 잔존 윈도우 마지막 flush 1회 (Q5)
# ===========================================================================
def test_g_sp4_swing_rest_poll_shutdown_flushes_residual(caplog):
    """G-SP4: shutdown hook 호출 시 잔존 collector 마지막 flush 1회 (Q5 옵션 A).

    `disconnect()` / `unsubscribe_all()` / `_swing_rest_poll_loop` cancel 직전
    잔여 카운터 손실 방지 — 정산 데이터 보존 의무.
    """
    import logging
    sched = _import_collector()

    record = getattr(sched, "record_swing_rest_poll", None)
    flush = getattr(sched, "flush_swing_rest_poll_collector", None)
    assert record is not None and flush is not None, (
        "사이클 74 G-SP4: 헬퍼 미존재"
    )

    # 잔존 2 건 (5 미만 — flush 주기 도달 전)
    record({"candidates": 8, "held": 1, "pending": 0, "updated": 8,
            "failed": 0, "elapsed_ms": 900})
    record({"candidates": 12, "held": 1, "pending": 0, "updated": 12,
            "failed": 0, "elapsed_ms": 1100})

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    # shutdown hook 호출 시 마지막 flush 의무
    flush()

    summary_lines = [
        r.message for r in caplog.records
        if "[swing_rest_poll_summary]" in r.message
    ]
    assert len(summary_lines) == 1, (
        f"G-SP4: shutdown 시 잔존 flush 1행 의무 — actual={len(summary_lines)} "
        f"(잔존 카운터 손실 = Q5 옵션 A 위반)"
    )
    assert "polls=2" in summary_lines[0], (
        f"G-SP4: 잔존 2 건 모두 흡수 — actual: {summary_lines[0]}"
    )
