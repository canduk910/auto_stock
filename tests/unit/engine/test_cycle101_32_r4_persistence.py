"""사이클 101 G-PERSIST2 — 사이클 32 R4 universe guard 영속 (LOW).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사이클 32 R4 영속 (영구 보장)**:
- `_evaluate_universe_guard`: stale>5 + `today_volume < 10_000` → 자동 unsubscribe
- **보유/익일청산 종목 절대 보호 영속**
- 사이클 101 = `_full_universe_load_once` 영역 = DB 영역 한정 = R4 평가 영향 0

검증 매트릭스:
- G-PERSIST2-A: `stale_manager.evaluate_universe_guard` 함수 영속 (사이클 67 분해 영속)
- G-PERSIST2-B: 사이클 101 영역 변경 0 → R4 영역 영구 영속

Red 상태: stale_manager R4 영역 변경 시 FAIL.
Green (backend-dev): 사이클 101 영역 영향 0 영속.

영속 의무:
- 사이클 32 R4 universe guard 영속 영구 보장 (보유/익일청산 절대 보호)
- 사이클 67 stale_manager 분해 영속
- 매매 안전성 영역 영향 0 (영역 분리)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_g_persist2_a_evaluate_universe_guard_exists() -> None:
    """G-PERSIST2-A: `stale_manager.evaluate_universe_guard` 함수 영속 (LOW).

    검증 매트릭스 (사이클 32 R4 영속 의무):
    - `src/engine/stale_manager.py` 또는 `src/engine/stale_universe_guard.py` 영역에
      `evaluate_universe_guard` 함수 영속

    Red 상태: 사이클 32 R4 영역 영속 함수 부재.
    Green: 사이클 67 stale_manager 분해 영속 영구 보장.
    """
    from src.engine import stale_manager

    assert hasattr(stale_manager, "evaluate_universe_guard"), (
        "\n사이클 101 G-PERSIST2-A 위반 — `evaluate_universe_guard` 부재:\n"
        "  사이클 32 R4 영속 의무: 보유/익일청산 절대 보호\n"
        "  사이클 67 stale_manager 분해 영속 (stale_universe_guard.py 영역)\n"
        "  Red 결함 가설: 사이클 101 영역에서 R4 영역 silent 삭제 영구 차단\n"
        "  Green (backend-dev): 사이클 32 R4 영역 영구 영속 의무"
    )


def test_g_persist2_b_universe_low_volume_threshold_persisted() -> None:
    """G-PERSIST2-B: `UNIVERSE_LOW_VOLUME_THRESHOLD == 10_000` 영속 (LOW)."""
    from src.engine import stale_manager

    assert hasattr(stale_manager, "UNIVERSE_LOW_VOLUME_THRESHOLD"), (
        "\n사이클 101 G-PERSIST2-B Red — `UNIVERSE_LOW_VOLUME_THRESHOLD` 부재:\n"
        "  사이클 32 R4 영속 의무"
    )
    assert stale_manager.UNIVERSE_LOW_VOLUME_THRESHOLD == 10_000, (
        f"\n사이클 101 G-PERSIST2-B 위반 — UNIVERSE_LOW_VOLUME_THRESHOLD 변경:\n"
        f"  기대: 10_000 (사이클 32 R4 영속)\n"
        f"  실제: {stale_manager.UNIVERSE_LOW_VOLUME_THRESHOLD}\n"
        f"  Green (backend-dev): 사이클 32 R4 영역 영속 의무"
    )
