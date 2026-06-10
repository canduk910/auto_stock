"""사이클 96 L-2 — KST 영속 (LOW).

명세 (`_workspace/red/cycle96_resurrect_industry_code_with_pagination.md`):

- 사이클 68 KST 일관성 답습 (`_kst` 헬퍼 영역 변경 0)
- 사이클 96 영역 복원 시 KST 영역 무영향 확인

기대 동작 (Green, backend-dev 인계):
- scanner.py 의 KST_TZ 정의 영속 (사이클 68 KST 일관성)
- 사이클 96 영역 복원 시 KST 영역 변경 0

영속 의무:
- 사이클 68 KST 일관성 답습
- 사이클 96 영역 복원 시 무영향
"""
from __future__ import annotations

from datetime import timedelta, timezone

import pytest

pytestmark = pytest.mark.unit


def test_l2_scanner_kst_tz_persistence():
    """L-2.a: scanner.py KST_TZ 정의 영속.

    검증 매트릭스:
    - `KST_TZ` 모듈 전역 정의 존재
    - timezone(timedelta(hours=9)) 영속

    영속 의무: 사이클 68 KST 일관성 답습 (변경 0).
    """
    from src.engine import scanner

    assert hasattr(scanner, "KST_TZ"), (
        "\n사이클 96 L-2.a 위반 — scanner.KST_TZ 정의 부재:\n"
        "  사이클 68 KST 일관성 영속 의무"
    )

    kst_tz = scanner.KST_TZ
    expected = timezone(timedelta(hours=9))

    assert kst_tz == expected, (
        f"\n사이클 96 L-2.a 위반 — KST_TZ 값 영역 결함:\n"
        f"  기대: timezone(timedelta(hours=9))\n"
        f"  실제: {kst_tz}\n"
        f"  사이클 68 KST 일관성 영속 의무"
    )


def test_l2_scanner_kst_tz_offset_9h():
    """L-2.b: KST_TZ UTC 오프셋 = +9시간 영속.

    검증 매트릭스:
    - utcoffset().total_seconds() == 9 * 3600

    영속 의무: 사이클 68 KST 일관성 검증.
    """
    from datetime import datetime

    from src.engine.scanner import KST_TZ

    now_kst = datetime.now(KST_TZ)
    offset_seconds = now_kst.utcoffset().total_seconds()

    assert offset_seconds == 9 * 3600, (
        f"\n사이클 96 L-2.b 위반 — KST UTC 오프셋 결함:\n"
        f"  기대: 32400초 (+9시간)\n"
        f"  실제: {offset_seconds}초\n"
        f"  사이클 68 KST 일관성 영속 의무"
    )
