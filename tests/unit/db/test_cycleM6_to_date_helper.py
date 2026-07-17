"""사이클 M6 (라이브 핫픽스) — `src/db/_kst.py::to_date` 헬퍼 단위 테스트.

배경: `src/db/strategy_funnel.py::insert_snapshot` 가 `target_date`(DATE 컬럼)에
문자열을 바인딩해 asyncpg 가
``invalid input for query argument $2: '...' ('str' object has no attribute
'toordinal')`` 로 실패했다 (graceful try/except 가 삼켜 silent 데이터 손실).
근본 원인 = `src/engine/scanner.py` 의 `datetime.now(KST_TZ).date().isoformat()`
호출부가 `target_date=` 에 str 을 넘김.

본 파일은 `to_date()` 자체의 변환 규칙만 검증한다 (date/str/datetime/None/
비-표준 ISO 문자열 앞 10자 슬라이스 / 파싱 실패 graceful).
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

import pytest

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))


def test_to_date_passthrough_date_object():
    """date 객체 입력 → 그대로 반환 (identity, 회귀 0)."""
    from src.db._kst import to_date

    d = date(2026, 7, 17)
    assert to_date(d) is d, "date 객체는 identity 로 그대로 반환돼야 한다."


def test_to_date_datetime_extracts_date():
    """datetime 입력 → .date() 로 변환 (시각 부분 제거)."""
    from src.db._kst import to_date

    dt = datetime(2026, 7, 17, 9, 30, 0, tzinfo=_KST)
    out = to_date(dt)
    assert out == date(2026, 7, 17)
    assert type(out) is date, "datetime 이 아닌 순수 date 로 변환돼야 한다 (asyncpg DATE 바인딩)."


def test_to_date_iso_string_yyyy_mm_dd():
    """`'YYYY-MM-DD'` 문자열 → date 객체 (버그 재현 케이스 — scanner.py 오류 형식)."""
    from src.db._kst import to_date

    out = to_date("2026-07-17")
    assert out == date(2026, 7, 17)
    assert type(out) is date


def test_to_date_iso_timestamp_string_first_10_chars():
    """`'YYYY-MM-DDTHH:MM:SS+09:00'` 같은 ISO 타임스탬프 문자열 → 앞 10자 슬라이스로 파싱."""
    from src.db._kst import to_date

    out = to_date("2026-07-17T09:30:00+09:00")
    assert out == date(2026, 7, 17)


def test_to_date_none_passthrough():
    """None 입력 → None (호출자 graceful 분기 보존, 예: max_bas_dd 미존재)."""
    from src.db._kst import to_date

    assert to_date(None) is None


def test_to_date_invalid_string_returns_none_graceful():
    """파싱 불가 문자열 → None (raise 하지 않음, 상위 try/except 의존 없이 자체 방어)."""
    from src.db._kst import to_date

    assert to_date("not-a-date") is None
    assert to_date("") is None
    assert to_date("2026/07/17") is None  # 슬래시 구분자 미지원 (ISO 전용)


def test_to_date_invalid_string_logs_warning(caplog):
    """파싱 실패 시 WARNING 1행 emit (운영 진단 가시화)."""
    from src.db._kst import to_date

    with caplog.at_level("WARNING", logger="src.db._kst"):
        result = to_date("garbage")
    assert result is None
    assert any("to_date" in rec.message for rec in caplog.records), (
        "파싱 실패 시 [to_date] WARNING 로그가 emit 돼야 한다."
    )


def test_to_date_unsupported_type_returns_none():
    """지원하지 않는 타입(int 등) → None graceful (raise 금지)."""
    from src.db._kst import to_date

    assert to_date(20260717) is None  # type: ignore[arg-type]


def test_to_date_datetime_subclass_of_date_checked_first():
    """datetime 은 date 의 서브클래스 — isinstance 순서상 datetime 분기가 먼저 발동해야 한다.

    (구현 세부 검증 — datetime 분기를 date 분기보다 먼저 두지 않으면 `.date()` 변환이
    누락되고 datetime 원본이 그대로 반환돼 asyncpg DATE 바인딩에 datetime 이 전달될
    위험이 있다. asyncpg 는 datetime 도 수용하지만, 값 자체가 시각 정보를 포함해
    쿼리 결과가 예측과 달라질 수 있다.)
    """
    from src.db._kst import to_date

    dt = datetime(2026, 7, 17, 23, 59, 59, tzinfo=_KST)
    out = to_date(dt)
    assert out == date(2026, 7, 17)
    assert not isinstance(out, datetime), "datetime 입력도 순수 date 로 정규화돼야 한다."
