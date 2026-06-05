"""사이클 61 Phase 2-A2 Red — B 카테고리: 5 상수 `is` 동일성 (5 케이스).

> **선행 명세**: `_workspace/red/cycle61_phase2A2_stale_manager.md` (Q3-G1~G5)
> **선례**: 사이클 60 A1 `test_cycle60_phase2A1_stale_manager.py` 카테고리 B 패턴 답습.

A2 추가 5 상수 (scheduler.X is stale_manager.X) re-export 호환 보장:
- SILENT_INACTIVE_MIN_SUBSCRIBED (=5)
- SILENT_INACTIVE_PERSIST_SECS (=300.0)
- SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR (=2) — KIS LMS/앱키 정지 위험 차단
- SILENT_INACTIVE_RECOVERY_WINDOW_SECS (=3600.0)
- STALE_FRESHNESS_SECS (=60)

Red 단계: stale_manager 에 5 상수 미존재 → `ImportError` 정상.

회귀 가드: CLAUDE.md 절대 깨지 말 것 — silent inactive 시간당 세션당 2회 cap
(B-3 `SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR` 동일성 = KIS LMS/앱키 정지 위험 차단).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_B1_SILENT_INACTIVE_MIN_SUBSCRIBED_same_object_across_modules():
    """B-1: `SILENT_INACTIVE_MIN_SUBSCRIBED` scheduler import = stale_manager 정의 (`is` 동일성)."""
    from src.engine.scheduler import SILENT_INACTIVE_MIN_SUBSCRIBED as A
    from src.engine.stale_manager import SILENT_INACTIVE_MIN_SUBSCRIBED as B  # Red: ImportError

    assert A is B, "SILENT_INACTIVE_MIN_SUBSCRIBED 가 두 모듈에서 동일 객체여야 함 (re-export)"
    assert A == 5, "사이클 24 정의 (sub<5 면 위양성 차단) 유지"


def test_B2_SILENT_INACTIVE_PERSIST_SECS_same_object():
    """B-2: `SILENT_INACTIVE_PERSIST_SECS` 동일성 + 값 300.0."""
    from src.engine.scheduler import SILENT_INACTIVE_PERSIST_SECS as A
    from src.engine.stale_manager import SILENT_INACTIVE_PERSIST_SECS as B  # Red: ImportError

    assert A is B
    assert A == 300.0, "사이클 24 정의 (5분 지속 임계, 단발 끊김 즉시 close 차단) 유지"


def test_B3_SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR_same_object():
    """B-3: `SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR` 동일성 + 값 2.

    절대 깨지 말 것: 시간당 세션당 2회 cap — KIS LMS/앱키 정지 위험 차단.
    """
    from src.engine.scheduler import SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR as A
    from src.engine.stale_manager import SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR as B  # Red: ImportError

    assert A is B
    assert A == 2, "사이클 24 정의 (시간당 reconnect 시도 cap) 유지 — LMS/앱키 정지 위험 차단"


def test_B4_SILENT_INACTIVE_RECOVERY_WINDOW_SECS_same_object():
    """B-4: `SILENT_INACTIVE_RECOVERY_WINDOW_SECS` 동일성 + 값 3600.0."""
    from src.engine.scheduler import SILENT_INACTIVE_RECOVERY_WINDOW_SECS as A
    from src.engine.stale_manager import SILENT_INACTIVE_RECOVERY_WINDOW_SECS as B  # Red: ImportError

    assert A is B
    assert A == 3600.0, "사이클 24 정의 (cap 윈도우 60분) 유지"


def test_B5_STALE_FRESHNESS_SECS_same_object():
    """B-5: `STALE_FRESHNESS_SECS` 동일성 + 값 60.

    A2 시점 stale_manager 로 이전 의무 — A1 의 lazy import 패턴
    (`from src.engine import scheduler as _sched_mod; _sched_mod.STALE_FRESHNESS_SECS`) 자연 해소.
    """
    from src.engine.scheduler import STALE_FRESHNESS_SECS as A
    from src.engine.stale_manager import STALE_FRESHNESS_SECS as B  # Red: ImportError

    assert A is B
    assert A == 60, "사이클 9 정의 (60s tick 없으면 stale 판정) 유지"
