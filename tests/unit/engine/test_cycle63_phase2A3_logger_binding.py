"""사이클 63 Phase 2-A3 Red — L 카테고리: logger 명시 binding (1 케이스).

> **선행 명세**: `_workspace/red/cycle63_phase2A3.md` §2 L
> **선례**: 사이클 60 A1 I-1 (logger binding hotfix) 영구 가드.

stale_manager.logger 가 "src.engine.scheduler" 로 binding 되어 운영 logging config
호환 + caplog 한정 캡처 호환 보장.

Red 단계: 사이클 60 영속 → PASS 가능 (회귀 가드).

회귀 가드: A3 이주 시 신규 호출자가 `logging.getLogger(__name__)` 추가 시 즉시 발견.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_L1_stale_manager_logger_is_scheduler_named():
    """L-1: `stale_manager.logger.name == "src.engine.scheduler"`.

    사이클 60 hotfix 영구 가드:
    - 사이클 60 A1 backend-dev Green 단계에서 `__name__` 사용 → 4 회귀 가드 FAIL → 즉시 hotfix
    - `caplog.set_level(logger="src.engine.scheduler")` 한정 캡처 → `__name__` 시
      `src.engine.stale_manager` 로거로 분기 → caplog 미캡처

    A3 이주 시점 영구 강제 — 신규 함수가 `logger = logging.getLogger(__name__)` 추가 시
    즉시 발견 + 운영 `[stale_watcher]` / `[stale_priority_resubscribe]` 로그 누락 차단.
    """
    from src.engine import stale_manager as sm

    assert sm.logger.name == "src.engine.scheduler", (
        f"stale_manager.logger.name 이 'src.engine.scheduler' 가 아님: {sm.logger.name}. "
        f"사이클 60 hotfix 패턴 (logger 명시 binding) 영속 위반."
    )
