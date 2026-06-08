"""사이클 74 의제 2-B — `[stale_watcher]` 5분 aggregation + 결함 시 individual (옵션 C 조건부).

Red 단계: aggregator helper 미존재로 G-SW1/G-SW2/G-SW5 FAIL.
영속 영역: G-SW3 (사이클 73 stale_diagnostics individual `[stale_watcher_detail]` 보존)
+ G-SW4 (사이클 66 K-10 `[stale_force_retry_cap]` WARNING individual 영속) — PASS.

Green 단계: backend-dev 가 `record_stale_watcher_check` +
`flush_stale_watcher_collector` + `[stale_watcher_summary]` prefix 헬퍼 도입.
단 stale_count > 0 시 individual `[stale_watcher_detail]` 보존 (사이클 73 영속).

영속 의무:
- 사이클 17 KIS LMS chain 차단 (재SEND 0건)
- 사이클 29-R1/R2/R3 (force_retry / silent inactive cap / priority 분리)
- 사이클 66 cap=10 priority + K-10 WARNING individual 보존
- 사이클 67 stale_manager facade + 4 sub-module
- 사이클 73 stale_diagnostics individual 보존
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# G-SW1: 5분 윈도우 30 check → `[stale_watcher_summary]` 1행 (30 → 1)
# ===========================================================================
def test_g_sw1_stale_watcher_5min_aggregation_emits_one_summary_row(caplog):
    """G-SW1: 120s × 30 check → `[stale_watcher_summary]` 1행 emit (97% 감소)."""
    import logging
    from src.engine import stale_watcher_core as core

    record = getattr(core, "record_stale_watcher_check", None)
    flush = getattr(core, "flush_stale_watcher_collector", None)
    assert record is not None, (
        "사이클 74 G-SW1: `record_stale_watcher_check` 헬퍼 미존재 — "
        "옵션 C 조건부 aggregator 도입 의무 (Green 발주 대상)"
    )
    assert flush is not None, (
        "사이클 74 G-SW1: `flush_stale_watcher_collector` 헬퍼 미존재"
    )

    # 정상 흐름 30 회 (stale 0) — aggregation 흡수만, individual 0
    for _ in range(30):
        record({
            "subscribed": 40, "stale": 0,
            "force_reregistered": 0, "skipped_giveup": 0,
            "force_retried": 0, "cap_blocked": 0,
        })

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    flush()

    summary_lines = [
        r.message for r in caplog.records
        if "[stale_watcher_summary]" in r.message
    ]
    assert len(summary_lines) == 1, (
        f"G-SW1: `[stale_watcher_summary]` 1행 emit 의무 — actual={len(summary_lines)}"
    )

    # 정상 흐름 = `[stale_watcher] subscribed=...` 개별 INFO 흡수 0건
    individual_lines = [
        r.message for r in caplog.records
        if r.message.startswith("[stale_watcher] ") and "summary" not in r.message
    ]
    assert len(individual_lines) == 0, (
        f"G-SW1: 정상 흐름 개별 `[stale_watcher]` INFO 흡수 의무 — actual={len(individual_lines)}"
    )


# ===========================================================================
# G-SW2: 윈도우 통계 정확 (checks/stale_total/retried/cap_blocked/force_retried)
# ===========================================================================
def test_g_sw2_stale_watcher_summary_stats_accurate(caplog):
    """G-SW2: stale 분포 누적 통계 키워드 정확."""
    import logging
    from src.engine import stale_watcher_core as core

    record = getattr(core, "record_stale_watcher_check", None)
    flush = getattr(core, "flush_stale_watcher_collector", None)
    assert record is not None and flush is not None, (
        "사이클 74 G-SW2: 헬퍼 미존재"
    )

    samples = [
        {"subscribed": 40, "stale": 3, "force_reregistered": 3,
         "skipped_giveup": 0, "force_retried": 0, "cap_blocked": 0},
        {"subscribed": 40, "stale": 5, "force_reregistered": 5,
         "skipped_giveup": 0, "force_retried": 1, "cap_blocked": 0},
        {"subscribed": 40, "stale": 2, "force_reregistered": 2,
         "skipped_giveup": 0, "force_retried": 0, "cap_blocked": 0},
    ]
    for s in samples:
        record(s)

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    flush()

    summary_lines = [
        r.message for r in caplog.records
        if "[stale_watcher_summary]" in r.message
    ]
    assert len(summary_lines) == 1
    msg = summary_lines[0]

    for keyword in ("checks=3", "stale_total=10", "retried=10",
                    "cap_blocked=0", "force_retried=1"):
        assert keyword in msg, (
            f"G-SW2: 키워드 `{keyword}` 누락\nactual: {msg}"
        )


# ===========================================================================
# G-SW3: stale 발견 시 (stale_count > 0) individual `[stale_watcher_detail]` 보존
# (사이클 73 stale_diagnostics 영속 영역 — 변경 0)
# ===========================================================================
def test_g_sw3_stale_watcher_detail_preserved_when_stale_present():
    """G-SW3: stale_diagnostics 모듈의 `emit_stale_session_detail` 가
    `[stale_watcher_detail]` prefix 를 individual 보존하는 영역 영속 (사이클 73 영속).

    사이클 74 aggregation 도입 시에도 individual `[stale_watcher_detail]` 영구 보존.
    LMS chain 진단 의무 (사이클 29 005935 사고 패턴 영역).
    """
    from pathlib import Path

    diagnostics_py = (
        Path(__file__).resolve().parents[3]
        / "src" / "engine" / "stale_diagnostics.py"
    )
    source = diagnostics_py.read_text(encoding="utf-8")

    # `[stale_watcher_detail]` prefix 영역 영속 (사이클 73 영속)
    assert "[stale_watcher_detail]" in source, (
        "G-SW3: stale_diagnostics.py 의 `[stale_watcher_detail]` prefix 누락 — "
        "사이클 73 영속 영역 위반 (KIS LMS chain 진단 의무)"
    )

    # individual emit 함수 영속 (`emit_stale_session_detail`)
    assert "emit_stale_session_detail" in source, (
        "G-SW3: `emit_stale_session_detail` 함수 미존재 — "
        "사이클 67 4 sub-module 분해 영속 위반"
    )


# ===========================================================================
# G-SW4: `[stale_force_retry_cap]` WARNING individual 영속 (사이클 66 K-10 영속)
# ===========================================================================
def test_g_sw4_stale_force_retry_cap_warning_preserved():
    """G-SW4: `_resubscribe_stale_priority` cap 초과 시
    `[stale_priority_resubscribe_cap_exceeded]` WARNING individual 영속.

    사이클 66 K-10 영속 영역 — HIGH > cap 시 모두 보장 + WARNING 운영 가시화.
    """
    from pathlib import Path

    core_py = (
        Path(__file__).resolve().parents[3]
        / "src" / "engine" / "stale_watcher_core.py"
    )
    source = core_py.read_text(encoding="utf-8")

    # 사이클 66 K-10 WARNING individual 영속 (cap_exceeded)
    assert "[stale_priority_resubscribe_cap_exceeded]" in source, (
        "G-SW4: `[stale_priority_resubscribe_cap_exceeded]` WARNING 누락 — "
        "사이클 66 K-10 영속 영역 위반 (HIGH > cap 운영 가시화)"
    )

    # 사이클 17 보강 영역 영속 — `[stale_force_retry_cap]` WARNING
    assert "[stale_force_retry_cap]" in source, (
        "G-SW4: `[stale_force_retry_cap]` WARNING 누락 — "
        "사이클 29-R1 영속 영역 위반 (force_retry 시간당 cap 차단)"
    )


# ===========================================================================
# G-SW5: 윈도우 종료 시 마지막 flush (Q5 옵션 A)
# ===========================================================================
def test_g_sw5_stale_watcher_shutdown_flushes_residual(caplog):
    """G-SW5: shutdown 시 잔존 collector 마지막 flush 1회 의무 (Q5 옵션 A)."""
    import logging
    from src.engine import stale_watcher_core as core

    record = getattr(core, "record_stale_watcher_check", None)
    flush = getattr(core, "flush_stale_watcher_collector", None)
    assert record is not None and flush is not None, (
        "사이클 74 G-SW5: 헬퍼 미존재"
    )

    # 잔존 2 건
    record({"subscribed": 40, "stale": 0, "force_reregistered": 0,
            "skipped_giveup": 0, "force_retried": 0, "cap_blocked": 0})
    record({"subscribed": 40, "stale": 0, "force_reregistered": 0,
            "skipped_giveup": 0, "force_retried": 0, "cap_blocked": 0})

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")
    flush()

    summary_lines = [
        r.message for r in caplog.records
        if "[stale_watcher_summary]" in r.message
    ]
    assert len(summary_lines) == 1, (
        f"G-SW5: shutdown 잔존 flush 1행 의무 — actual={len(summary_lines)} "
        f"(잔여 카운터 손실 = Q5 옵션 A 위반)"
    )
    assert "checks=2" in summary_lines[0], (
        f"G-SW5: 잔존 2 건 모두 흡수 — actual: {summary_lines[0]}"
    )
