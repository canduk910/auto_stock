"""사이클 102 영역 1 — 사이클 78 silent 결함 영구 확인 (행위 가드).

G-78-VERIFY-1 + G-78-VERIFY-5 — `[stale_watcher_summary]` emit 5분 주기 발화 검증.

영역 1 = 코드 변경 0 의무 영역 (사이클 78 영속 영역 영구 확인).
사이클 78 시정 영역 영속 확인 + `[stale_watcher_summary]` 0건/7일 운영 실측 결함
원인 = 코드 영역 (1) 영구 차단 확정.

영속 의무:
- 사이클 78 G-AST1 영속 (flush 호출 사이트 ≥1건 영구 가드)
- 사이클 74 collector 패턴 영속 (5분 윈도우 emit + clear)
- 사이클 17 KIS LMS chain / 사이클 38 명문화 / 매매 안전성 영향 0
"""
from __future__ import annotations

import logging

import pytest

from src.engine import stale_watcher_core


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# G-78-VERIFY-1 — record + flush 시 [stale_watcher_summary] 1행 emit 영속
# ---------------------------------------------------------------------------
def test_g_78_verify_1_stale_watcher_summary_emit_after_record(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """G-78-VERIFY-1 (HIGH): `record_stale_watcher_check` 후 `flush_stale_watcher_collector`
    호출 시 `[stale_watcher_summary]` 1행 emit 영속 (사이클 74 옵션 E-1 영역 영속).

    Red: 사이클 78 영속이 정상이면 Red 단계에서 즉시 PASS — 영구 가드 신설 목적.
    회귀 차단: 사이클 78 영속 영역 (record + flush 함수 정의) 침범 시 FAIL.

    검증 매트릭스:
    - record 5건 누적 (`stale_total=15`, `force_reregistered=5`, `cap_blocked=2`, `force_retried=8`)
    - flush 호출 → 로그 prefix `[stale_watcher_summary]` 1행 emit 영속
    - emit 후 collector empty 영속
    """
    # Arrange — collector clear (테스트 격리)
    stale_watcher_core._stale_watcher_collector.clear()
    caplog.clear()
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    # Act — 5건 record (사이클 74 옵션 E-1 영역 답습)
    for _ in range(5):
        stale_watcher_core.record_stale_watcher_check({
            "stale": 3,
            "force_reregistered": 1,
            "cap_blocked": 0,
            "force_retried": 2,
        })
    # cap_blocked 1건은 별도 record (집계 검증)
    stale_watcher_core.record_stale_watcher_check({
        "stale": 1,
        "force_reregistered": 0,
        "cap_blocked": 2,
        "force_retried": 0,
    })

    # 사전 조건: collector 6건 누적 영속
    assert len(stale_watcher_core._stale_watcher_collector) == 6, (
        f"G-78-VERIFY-1 사전조건: record 6건 누적 영속 — 실측 "
        f"{len(stale_watcher_core._stale_watcher_collector)}건"
    )

    # Act — flush (사이클 78 영속 = `_api_recovered_collector_loop` 본체 호출)
    stale_watcher_core.flush_stale_watcher_collector()

    # Assert — `[stale_watcher_summary]` 1행 emit 영속 (사이클 74 옵션 E-1 prefix)
    matching = [
        rec for rec in caplog.records
        if "[stale_watcher_summary]" in rec.getMessage()
    ]
    assert len(matching) == 1, (
        f"G-78-VERIFY-1 위반 — `[stale_watcher_summary]` 1행 emit 영속 결함 "
        f"(실측 {len(matching)}행 / 6 record):\n"
        + "\n".join(f"  - {rec.getMessage()}" for rec in caplog.records)
        + "\n\n  사이클 78 영속 영역 침범:\n"
        f"  - `record_stale_watcher_check` (`src/engine/stale_watcher_core.py:46`) +\n"
        f"  - `flush_stale_watcher_collector` (`src/engine/stale_watcher_core.py:57`)\n"
        f"  - 5분 주기 task 호출 사이트 (`scheduler.py::_api_recovered_collector_loop` L2563)\n"
        f"  영역 1 결함 = 사이클 78 영역 silent 결함 재현 위험 (메모리 leak HIGH)."
    )
    # 집계 정확성 영속 (사이클 74 영속 6 record = checks=6 / stale_total=16 / retried=5 / cap_blocked=2 / force_retried=10)
    msg = matching[0].getMessage()
    assert "checks=6" in msg, f"G-78-VERIFY-1 집계 결함 checks: {msg}"
    assert "stale_total=16" in msg, f"G-78-VERIFY-1 집계 결함 stale_total: {msg}"
    assert "retried=5" in msg, f"G-78-VERIFY-1 집계 결함 retried: {msg}"
    assert "cap_blocked=2" in msg, f"G-78-VERIFY-1 집계 결함 cap_blocked: {msg}"
    assert "force_retried=10" in msg, f"G-78-VERIFY-1 집계 결함 force_retried: {msg}"

    # emit 후 collector empty 영속 (사이클 74 패턴)
    assert len(stale_watcher_core._stale_watcher_collector) == 0, (
        "G-78-VERIFY-1 위반 — flush 후 collector empty 영속 결함 (사이클 74 영속 영역 침범)"
    )


# ---------------------------------------------------------------------------
# G-78-VERIFY-5 — empty collector flush skip (no-op) 영속
# ---------------------------------------------------------------------------
def test_g_78_verify_5_empty_collector_flush_skip_noop(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """G-78-VERIFY-5 (MEDIUM): empty collector 상태에서 `flush_stale_watcher_collector`
    호출 시 emit 0 (no-op) 영속 — Q2 빈 윈도우 skip 영역 영속 (사이클 74 영역).

    Red: 사이클 78 영속이 정상이면 Red 단계에서 즉시 PASS — 영구 가드 신설 목적.
    회귀 차단: empty 시 emit 발화 silent 결함 (운영 dup_factor 1.0x 위반) 차단.
    """
    # Arrange — collector clear
    stale_watcher_core._stale_watcher_collector.clear()
    caplog.clear()
    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    # Act — empty 상태 flush
    stale_watcher_core.flush_stale_watcher_collector()

    # Assert — emit 0 영속 (Q2 빈 윈도우 skip 영역 영속)
    matching = [
        rec for rec in caplog.records
        if "[stale_watcher_summary]" in rec.getMessage()
    ]
    assert len(matching) == 0, (
        f"G-78-VERIFY-5 위반 — empty collector flush 시 emit 0 영속 결함:\n"
        f"  실측 {len(matching)}행 (≥ 1 발화 = 사이클 74 Q2 영역 침범):\n"
        + "\n".join(f"  - {rec.getMessage()}" for rec in matching)
    )
