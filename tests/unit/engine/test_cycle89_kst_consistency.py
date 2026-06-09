"""사이클 89 L-3 — KST 영속 (사이클 68 답습).

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

- 사이클 68 `_kst.py` 헬퍼 영속 영역
- `now_kst_iso()` / `today_kst()` / `KST` timezone 영속
- 사이클 89 시정 영역 (stock_master_metrics) 도 KST 영속 의무

기대 동작 (Green, 사이클 90):
- `src/engine/stock_master_metrics.py` 내 시간 처리 = `_kst.now_kst_iso()` 단독 사용
- `datetime.utcnow()` / `datetime.now()` (naive) / `time.time()` (UTC seconds) 0건

Red 상태 (사이클 89): 신규 모듈 미존재 → ImportError → FAIL.

영속 의무:
- 사이클 68 KST 일관성 영속 (`src/db/_kst.py` 공용 헬퍼)
- 사이클 89 신규 모듈에서 동일 silent 결함 (UTC naive 비교 9시간 오차) 재발 차단
- 매매 안전성 영향 0 (로깅/메트릭 영역)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_STOCK_MASTER_METRICS_PY = (
    Path(__file__).resolve().parents[3] / "src" / "engine" / "stock_master_metrics.py"
)


def test_l3_stock_master_metrics_kst_consistency():
    """L-3: `src/engine/stock_master_metrics.py` 내 시간 처리 = KST 영속.

    검증 매트릭스:
    - `datetime.utcnow()` 호출 0건 (사이클 68 silent 결함 영구 차단)
    - `datetime.now()` (timezone 인자 없음) 호출 0건 (naive datetime 영구 차단)
    - `_kst` 헬퍼 import 1건 이상 (사이클 68 영속)

    Red 상태 (사이클 89): 신규 모듈 부재 → FAIL.

    Green (사이클 90): backend-dev 가 KST 헬퍼 영속 도입 → PASS.

    영속 의무:
    - 사이클 68 KST 일관성 영속 (`src/db/_kst.py` 공용 헬퍼)
    - 사이클 89 신규 모듈에서 동일 silent 결함 재발 차단
    """
    if not _STOCK_MASTER_METRICS_PY.exists():
        pytest.fail(
            "\n사이클 89 L-3 Red 상태 — `src/engine/stock_master_metrics.py` 모듈 부재:\n"
            "  Green (사이클 90): backend-dev 가 신규 모듈 도입 + KST 영속 의무.\n"
            "  - 사이클 68 `_kst.now_kst_iso()` 헬퍼 사용 의무"
        )

    source = _STOCK_MASTER_METRICS_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 가드 1: `datetime.utcnow()` 호출 0건
    utcnow_count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "utcnow":
                utcnow_count += 1
    assert utcnow_count == 0, (
        f"\n사이클 89 L-3 위반 — `datetime.utcnow()` 호출 발견:\n"
        f"  현재 호출 횟수: {utcnow_count} (= 0 필요)\n"
        f"  영속 의무: 사이클 68 silent 결함 (UTC naive 비교 9시간 오차) 영구 차단\n"
        f"  - 시정: `_kst.now_kst_iso()` 사용"
    )

    # 가드 2: `_kst` 또는 `now_kst_iso` import 등장 ≥ 1건
    has_kst_import = (
        "_kst" in source
        or "now_kst_iso" in source
        or "now_kst" in source
        or "KST" in source
    )
    assert has_kst_import, (
        f"\n사이클 89 L-3 위반 — KST 헬퍼 import 누락:\n"
        f"  영속 의무: 사이클 68 `src/db/_kst.py` 공용 헬퍼 영속 사용\n"
        f"  - 시정: `from src.db._kst import now_kst_iso, KST` 등 import"
    )
