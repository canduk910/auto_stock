"""사이클 84 Red — L-3 (LOW): 사이클 83 `[scan_pool_eager_refresh]` emit 영속 가드.

사이클 83 `_eager_refresh_stock_master_for_held_positions` 가 1행 emit (boot_manager 영역).
사이클 84 `count_eager_refresh_today` 헬퍼의 의존성 = 본 emit 영속.

본 가드는 `src/engine/boot_manager.py` (또는 scheduler 영역) 에 `[scan_pool_eager_refresh]`
literal 1건 이상 존재 정적 검증 — 미래 silent 결함 (사이클 83 emit 제거) 영구 차단.

위험 등급 LOW (사이클 83 영속 가드 영역 확장).
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ENGINE_DIR = Path(__file__).resolve().parents[3] / "src" / "engine"
SEARCH_LITERAL = "[scan_pool_eager_refresh]"


def test_L3_scan_pool_eager_refresh_literal_present():
    """L-3: src/engine/ 전체에 `[scan_pool_eager_refresh]` literal 1건 이상.

    사이클 84 `count_eager_refresh_today` 의 의존성 = emit 영속 의무.
    """
    hits = []
    for py in ENGINE_DIR.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if SEARCH_LITERAL in text:
            hits.append(str(py.relative_to(ENGINE_DIR.parents[1])))

    assert hits, (
        f"`{SEARCH_LITERAL}` literal 0건 — 사이클 83 emit 영속 파괴 위험. "
        f"src/engine/ 전수 검색 0건. 사이클 84 count_eager_refresh_today 헬퍼 의존성 결함."
    )
