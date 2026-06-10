"""사이클 94 L-1 — KST 영속 (사이클 68 답습) (LOW).

명세 (`_workspace/red/cycle94_fid_input_iscd_fix.md` §4 L-1):

- 사이클 68 KST 일관성 영속 (`_kst` 헬퍼 영역 변경 0)
- 사이클 94 시정 시 timestamp 영역 영향 0
- `src/db/_kst.py` 모듈 영속 (KST 단일 진입점)

기대 동작 (Green, backend-dev 인계):
- `src.db._kst` 모듈에서 `KST`, `now_kst_iso`, `today_kst` export 영속
- scanner 시정 영역에서 `_kst` 헬퍼 변경 0

Red 상태 (사이클 94): 사이클 94 시정 중 `_kst` 영역 영향 위험 검출.

영속 의무:
- 사이클 68 KST 일관성 영역 영속
- 사이클 94 시정 = scanner 영역 한정 (KST 무관)
- 매매 안전성 영향 0
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_l1_kst_helper_module_exports_preserved():
    """L-1.a: `src.db._kst` 모듈에서 `KST` / `now_kst_iso` / `today_kst` export 영속.

    사이클 68 헬퍼 통일 영역 영속 의무.

    영속 의무: 사이클 94 시정 시 _kst 영역 변경 0.
    """
    from src.db import _kst as _kst_mod

    assert hasattr(_kst_mod, "KST"), (
        "\n사이클 94 L-1.a 위반 — `KST` export 부재:\n"
        "  사이클 68 영속 영역 의무"
    )
    assert hasattr(_kst_mod, "now_kst_iso"), (
        "\n사이클 94 L-1.a 위반 — `now_kst_iso` export 부재:\n"
        "  사이클 68 영속 영역 의무"
    )
    assert hasattr(_kst_mod, "today_kst"), (
        "\n사이클 94 L-1.a 위반 — `today_kst` export 부재:\n"
        "  사이클 68 영속 영역 의무"
    )


def test_l1_kst_timezone_value_is_korean_standard():
    """L-1.b: `KST` value 가 `timezone(timedelta(hours=9))` 영역 영속.

    KST 단일 진입점 영역 정합 검증.
    """
    from datetime import timedelta, timezone

    from src.db._kst import KST

    expected = timezone(timedelta(hours=9))
    assert KST == expected, (
        f"\n사이클 94 L-1.b 위반 — KST timezone 결함:\n"
        f"  기대: timezone(timedelta(hours=9))\n"
        f"  실제: {KST}"
    )


def test_l1_scanner_module_no_utc_now_misuse():
    """L-1.c: scanner.py 가 사이클 94 시정 후에도 `datetime.utcnow()` 호출 0건 (KST 영속).

    사이클 68 G-10 AST 가드 답습 영역.
    """
    import inspect

    from src.engine import scanner as scanner_mod

    source = inspect.getsource(scanner_mod)

    # `datetime.utcnow()` 호출 0건 (사이클 68 G-10 답습)
    assert "datetime.utcnow()" not in source, (
        "\n사이클 94 L-1.c 위반 — `datetime.utcnow()` 호출 영속 결함:\n"
        "  사이클 68 KST 일관성 영역 영속 의무\n"
        "  Green: `now_kst_iso()` 또는 `datetime.now(KST)` 영속"
    )
