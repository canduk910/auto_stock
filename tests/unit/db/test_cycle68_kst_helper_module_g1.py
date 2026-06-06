"""사이클 68 G-1 — `src/db/_kst.py` 공용 KST 헬퍼 모듈 존재 + export.

> **결정 2-B 채택**: 모듈별 `KST = timezone(timedelta(hours=9))` 중복 폐기 →
>   `src/db/_kst.py` 단일 공용 헬퍼. 향후 silent 결함 영구 차단 (헬퍼 미사용 = AST FAIL).
>
> **선례**: 사이클 65 H2/H2-bis 패턴 답습 (`datetime.now(KST).isoformat()`).
>
> Red 시점: `src/db/_kst.py` 미존재 → import 자체 FAIL.
> Green 후: `now_kst_iso()` 호출 시 `+09:00` suffix 포함 ISO 8601 문자열 반환 +
>   `KST` 가 UTC+9 동등 timezone 객체.

검증 항목:
- G-1a: `from src.db._kst import now_kst_iso, KST` import 성공.
- G-1b: `now_kst_iso()` 반환값이 `+09:00` 또는 `+0900` suffix 포함 ISO 문자열.
- G-1c: `KST` 가 UTC+9 동등 객체 (timedelta(hours=9) utcoffset).

위험 등급: 정책 일관성 (DB INSERT 영역, hot path 무관).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit


def test_g1a_helper_module_importable():
    """G-1a — `src.db._kst` 모듈 import 성공 + `now_kst_iso` / `KST` export."""
    try:
        from src.db._kst import KST, now_kst_iso
    except ImportError as e:
        pytest.fail(
            "`src/db/_kst.py` 공용 KST 헬퍼 모듈 미존재 — "
            "사이클 68 결정 2-B 시정 의무 (Green 단계 backend-dev 작성).\n"
            f"원인: {e!r}"
        )
    # call signature 점검
    assert callable(now_kst_iso), "now_kst_iso 는 callable 의무"


def test_g1b_now_kst_iso_returns_kst_offset_suffix():
    """G-1b — `now_kst_iso()` 반환값에 KST `+09:00` (또는 `+0900`) suffix 포함."""
    from src.db._kst import now_kst_iso

    iso = now_kst_iso()
    assert isinstance(iso, str), f"ISO 문자열 의무, 실제 {type(iso).__name__}"
    # +09:00 또는 +0900 두 가지 표기 모두 허용 (datetime.isoformat 표준)
    assert re.search(r"\+09:?00$", iso), (
        f"KST `+09:00` suffix 의무 — 실제 반환: {iso!r}. "
        "사이클 53 KST `+09:00` 패턴 + 사이클 65 H2 답습 의무."
    )

    # parse 가능 + tzinfo aware 검증
    parsed = datetime.fromisoformat(iso)
    assert parsed.tzinfo is not None, "timezone-aware datetime 의무"
    assert parsed.utcoffset() == timedelta(hours=9), (
        f"UTC+9 의무 — 실제 offset: {parsed.utcoffset()}"
    )


def test_g1c_kst_constant_equals_utc_plus_9():
    """G-1c — `KST` 상수가 UTC+9 동등 timezone 객체."""
    from src.db._kst import KST

    # `timezone(timedelta(hours=9))` 또는 `ZoneInfo("Asia/Seoul")` 모두 허용
    # utcoffset 으로 동등성 검증 (ZoneInfo 는 datetime 인자 필요)
    sample_dt = datetime(2026, 6, 6, 12, 0, 0)
    try:
        offset = KST.utcoffset(sample_dt)
    except TypeError:
        # timezone(timedelta) 는 인자 None 도 허용
        offset = KST.utcoffset(None)
    assert offset == timedelta(hours=9), (
        f"UTC+9 의무 — 실제 offset: {offset}. "
        "허용 표현: `timezone(timedelta(hours=9))` 또는 `ZoneInfo('Asia/Seoul')`."
    )
