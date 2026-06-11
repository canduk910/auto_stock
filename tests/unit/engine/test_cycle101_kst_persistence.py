"""사이클 101 G-PERSIST5 — KST 영속 (사이클 68) (LOW).

명세 (`_workspace/red/cycle101_market_cap_full_universe_load.md`):

**사이클 68 KST 영속 (영구 보장)**:
- 모든 시각 데이터 KST 강제
- `src/db/_kst.py` 공용 헬퍼 (`now_kst_iso`, `KST`) 사용 의무
- 사이클 101 신규 모듈 영역 KST 영속 의무

검증 매트릭스:
- G-PERSIST5-A: `src/db/_kst.py` 모듈 영속 + `KST` + `now_kst_iso` export
- G-PERSIST5-B: `stock_master_metrics.py` 영역에 `_kst` 헬퍼 import 영속 (사이클 89 답습)

Red 상태: KST 헬퍼 부재 또는 영역 누락.
Green (backend-dev): 영속 영구 보장.

영속 의무:
- 사이클 68 KST 일관성 영속 영구 보장
- 매매 안전성 영역 영향 0 (헬퍼 영역)
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_g_persist5_a_kst_helper_exists() -> None:
    """G-PERSIST5-A: `src/db/_kst.py` 헬퍼 영속 (LOW).

    검증 매트릭스 (사이클 68 영속):
    - `KST` timezone 객체 영속
    - `now_kst_iso` 함수 영속
    """
    from src.db import _kst

    assert hasattr(_kst, "KST"), (
        "\n사이클 101 G-PERSIST5-A Red — `_kst.KST` 부재.\n"
        "  사이클 68 KST 영속 의무 (`src/db/_kst.py`)"
    )
    assert hasattr(_kst, "now_kst_iso"), (
        "\n사이클 101 G-PERSIST5-A Red — `_kst.now_kst_iso` 부재.\n"
        "  사이클 68 KST 영속 의무"
    )


def test_g_persist5_b_stock_master_metrics_kst_persistence() -> None:
    """G-PERSIST5-B: `stock_master_metrics.py` 영역 _kst 헬퍼 import 영속 (LOW).

    검증 매트릭스 (사이클 89 답습 영속):
    - 사이클 89 시점 `stock_master_metrics.py` 가 `from src.db._kst import now_kst_iso, KST` 영속
    - 사이클 101 영역 = 동일 모듈 신규 함수 추가 시 KST 영속 보장

    Red 상태: 모듈 영역에 KST 헬퍼 import 부재.
    Green (backend-dev): import 영속 의무.
    """
    import src.engine.stock_master_metrics as metrics_mod
    source = Path(metrics_mod.__file__).read_text(encoding="utf-8")

    has_kst_import = (
        "from src.db._kst import" in source
        or "src.db._kst" in source
    )
    assert has_kst_import, (
        f"\n사이클 101 G-PERSIST5-B 위반 — stock_master_metrics.py 영역 KST 헬퍼 import 부재:\n"
        f"  기대: `from src.db._kst import now_kst_iso, KST` 영속\n"
        f"  Red 결함 가설: 사이클 68 영역 silent 삭제\n"
        f"  Green (backend-dev): import 영속 의무"
    )
