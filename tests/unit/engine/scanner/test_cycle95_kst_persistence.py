"""사이클 95 L-2 — KST 영속 (사이클 68 답습) (LOW).

명세 (`_workspace/red/cycle95_chicken_and_egg_fix_ui.md` §3 L-2):

- 사이클 68 KST 일관성 영속 (`_kst` 헬퍼 영역 변경 0)
- 사이클 95 시정 시 timestamp 영역 영향 0
- `src/db/_kst.py` 모듈 영속 (KST 단일 진입점)

영속 의무:
- 사이클 68 KST 일관성 영역 영속
- 사이클 95 시정 = scanner 영역 한정 (KST 무관)
- 매매 안전성 영향 0
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_l2_kst_helper_module_exports_preserved():
    """L-2.a: `src.db._kst` 모듈 `KST` / `now_kst_iso` / `today_kst` export 영속."""
    from src.db import _kst as _kst_mod

    assert hasattr(_kst_mod, "KST"), (
        "사이클 95 L-2.a 위반 — `KST` export 부재 (사이클 68 영속 의무)"
    )
    assert hasattr(_kst_mod, "now_kst_iso"), (
        "사이클 95 L-2.a 위반 — `now_kst_iso` export 부재"
    )
    assert hasattr(_kst_mod, "today_kst"), (
        "사이클 95 L-2.a 위반 — `today_kst` export 부재"
    )


def test_l2_kst_timezone_value_is_korean_standard():
    """L-2.b: `KST` value 가 `timezone(timedelta(hours=9))` 영역 영속."""
    from datetime import timedelta, timezone

    from src.db._kst import KST

    expected = timezone(timedelta(hours=9))
    assert KST == expected, (
        f"\n사이클 95 L-2.b 위반 — KST timezone 결함:\n"
        f"  기대: timezone(timedelta(hours=9))\n"
        f"  실제: {KST}"
    )


def test_l2_scanner_module_no_utc_now_misuse():
    """L-2.c: scanner.py 가 사이클 95 시정 후에도 `datetime.utcnow()` 호출 0건 (KST 영속).

    사이클 68 G-10 AST 가드 답습 영역.
    """
    import inspect

    from src.engine import scanner as scanner_mod

    source = inspect.getsource(scanner_mod)

    assert "datetime.utcnow()" not in source, (
        "\n사이클 95 L-2.c 위반 — `datetime.utcnow()` 호출 영속 결함:\n"
        "  사이클 68 KST 일관성 영역 영속 의무\n"
        "  Green: `now_kst_iso()` 또는 `datetime.now(KST)` 영속"
    )
