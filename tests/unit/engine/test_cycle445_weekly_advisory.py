"""cycle445 D8 — 주간 AI 자문 실행일 판정 leaf (`src/engine/weekly_advisory.py`).

20:00 AI 자문(+ 딸린 외부 백테스트 enqueue)을 매일이 아니라 주간 자문일(기본
목요일)에만 돌린다(사용자 결정 2026-10-11). 판정은 시각을 인자로 받는 순수
함수라 freezegun 없이도 창 안·밖·목요일·휴장 목요일을 고정 시각으로 테스트한다
(벽시계 게이트가 CI 를 깨지 않게 — `feedback_wall_clock_gate_breaks_ci` 교훈).

🔴 "휴장 목요일" — 이 leaf 는 공휴일을 모른다(모듈 docstring). `run_daily()` 가
이미 그날 전체를 건너뛰므로, 휴장 목요일에도 이 함수 자신은 여전히 `True` 를
돌려준다(코드 도달 여부는 상위가 가른다). 그 가정 자체를 아래 테스트가 고정한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _kst(y, m, d, hh=20, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=KST)


# ---------------------------------------------------------------------------
# normalize_weekday
# ---------------------------------------------------------------------------
def test_normalize_weekday_accepts_known_codes_case_insensitive():
    from src.engine.weekly_advisory import normalize_weekday

    assert normalize_weekday("thu") == ("thu", True)
    assert normalize_weekday("MON") == ("mon", True)
    assert normalize_weekday(" Fri ") == ("fri", True)


@pytest.mark.parametrize("raw", [None, "", "monday", 3, {"value": "thu"}, "__cycle369_malformed__"])
def test_normalize_weekday_falls_back_to_default_on_bad_input(raw):
    from src.engine.weekly_advisory import normalize_weekday, DEFAULT_WEEKDAY_CODE

    code, valid = normalize_weekday(raw)
    assert code == DEFAULT_WEEKDAY_CODE
    assert valid is False


def test_default_weekday_code_is_thursday():
    from src.engine.weekly_advisory import DEFAULT_WEEKDAY_CODE

    assert DEFAULT_WEEKDAY_CODE == "thu"


# ---------------------------------------------------------------------------
# is_weekly_advisory_day — 순수, 시각 주입
# ---------------------------------------------------------------------------
def test_is_weekly_advisory_day_true_on_thursday_default():
    from src.engine.weekly_advisory import is_weekly_advisory_day

    # 2026-10-08 은 목요일 (실제 주간 자문일 — weekly_advice_2026-10-08.md 와 교차)
    thu = _kst(2026, 10, 8)
    assert thu.weekday() == 3
    assert is_weekly_advisory_day(thu) is True


@pytest.mark.parametrize(
    "day, expect",
    [
        (5, False),  # 월(2026-10-05) 아님 — 실제로는 월요일(weekday 0)이 아니라 다음 파라미터로 보정
    ],
)
def test_is_weekly_advisory_day_false_on_other_weekdays(day, expect):
    from src.engine.weekly_advisory import is_weekly_advisory_day

    # 2026-10-05(월) ~ 2026-10-11(일) 한 주 전체를 스캔 — 목요일(10-08)만 True
    week = {
        5: 0,  # 월
        6: 1,  # 화
        7: 2,  # 수
        8: 3,  # 목
        9: 4,  # 금
        10: 5,  # 토
        11: 6,  # 일
    }
    for dom, wd in week.items():
        now = _kst(2026, 10, dom)
        assert now.weekday() == wd
        assert is_weekly_advisory_day(now) == (wd == 3), (
            f"10-{dom:02d}(weekday={wd}) 판정이 틀렸다"
        )


def test_is_weekly_advisory_day_respects_custom_weekday_code():
    from src.engine.weekly_advisory import is_weekly_advisory_day

    mon = _kst(2026, 10, 5)
    assert mon.weekday() == 0
    assert is_weekly_advisory_day(mon, weekday_code="mon") is True
    assert is_weekly_advisory_day(mon, weekday_code="thu") is False


def test_is_weekly_advisory_day_unknown_code_falls_back_to_default():
    from src.engine.weekly_advisory import is_weekly_advisory_day

    thu = _kst(2026, 10, 8)
    # 코드가 어휘 밖이면 내부적으로 DEFAULT_WEEKDAY_CODE(목)로 떨어진다
    assert is_weekly_advisory_day(thu, weekday_code="not-a-day") is True


def test_is_weekly_advisory_day_time_of_day_irrelevant():
    """요일 판정은 시각(시·분)과 무관 — 00:00 과 23:59 모두 같은 요일이면 같다."""
    from src.engine.weekly_advisory import is_weekly_advisory_day

    assert is_weekly_advisory_day(_kst(2026, 10, 8, 0, 0)) is True
    assert is_weekly_advisory_day(_kst(2026, 10, 8, 23, 59)) is True
    assert is_weekly_advisory_day(_kst(2026, 10, 9, 0, 0)) is False


def test_is_weekly_advisory_day_closed_thursday_still_true():
    """🔴 휴장 목요일도 이 함수 자신은 True — 공휴일 판정은 이 leaf 의 책임이 아니다.

    실제 그 날 자문이 도는지는 `scheduler.run_daily()` 의 기존 휴장일 스킵이
    가른다(이 leaf 호출 자체에 도달하지 못한다). 이 테스트는 그 분리를 고정한다.
    """
    from src.engine.weekly_advisory import is_weekly_advisory_day

    # 가상의 휴장 목요일 — 이 leaf 는 휴장 여부를 조회하지 않으므로 날짜값은
    # 실제 공휴일 여부와 무관하게 요일만 본다.
    holiday_thu = _kst(2026, 1, 1)  # 신정, 목요일이라고 가정한 고정 시각
    assert holiday_thu.weekday() == 3
    assert is_weekly_advisory_day(holiday_thu) is True


# ---------------------------------------------------------------------------
# should_run_weekly_advisory — async, DB 조회 + 판정 결합, never-raise
# ---------------------------------------------------------------------------
async def test_should_run_weekly_advisory_default_thursday_run(monkeypatch):
    from src.engine import weekly_advisory as wa

    async def fake_get(**kw):
        return None  # 키 없음

    monkeypatch.setattr(
        "src.db.system_config.get_weekly_advisory_weekday_raw", fake_get, raising=False
    )

    decision = await wa.should_run_weekly_advisory(_kst(2026, 10, 8))
    assert decision == {"run": True, "weekday_code": "thu", "configured_valid": False}


async def test_should_run_weekly_advisory_default_thursday_skip_on_monday(monkeypatch):
    from src.engine import weekly_advisory as wa

    async def fake_get(**kw):
        return None

    monkeypatch.setattr(
        "src.db.system_config.get_weekly_advisory_weekday_raw", fake_get, raising=False
    )

    decision = await wa.should_run_weekly_advisory(_kst(2026, 10, 5))
    assert decision["run"] is False
    assert decision["weekday_code"] == "thu"


async def test_should_run_weekly_advisory_honors_configured_weekday(monkeypatch):
    from src.engine import weekly_advisory as wa

    async def fake_get(**kw):
        return "mon"

    monkeypatch.setattr(
        "src.db.system_config.get_weekly_advisory_weekday_raw", fake_get, raising=False
    )

    mon_decision = await wa.should_run_weekly_advisory(_kst(2026, 10, 5))
    assert mon_decision == {"run": True, "weekday_code": "mon", "configured_valid": True}

    thu_decision = await wa.should_run_weekly_advisory(_kst(2026, 10, 8))
    assert thu_decision == {"run": False, "weekday_code": "mon", "configured_valid": True}


async def test_should_run_weekly_advisory_malformed_value_falls_back(monkeypatch):
    from src.engine import weekly_advisory as wa

    async def fake_get(**kw):
        return "__cycle369_malformed__"

    monkeypatch.setattr(
        "src.db.system_config.get_weekly_advisory_weekday_raw", fake_get, raising=False
    )

    decision = await wa.should_run_weekly_advisory(_kst(2026, 10, 8))
    assert decision == {"run": True, "weekday_code": "thu", "configured_valid": False}


async def test_should_run_weekly_advisory_db_exception_is_never_raise(monkeypatch):
    """DB 조회 예외는 「키 없음」과 같게 다룬다 — 기본값(목)이 실제 목요일과 같아서
    요일을 바꾼 적 없는 운영은 DB 장애가 있어도 그 주 자문이 그대로 돈다."""
    from src.engine import weekly_advisory as wa

    async def fake_get(**kw):
        raise RuntimeError("DB down")

    monkeypatch.setattr(
        "src.db.system_config.get_weekly_advisory_weekday_raw", fake_get, raising=False
    )

    decision = await wa.should_run_weekly_advisory(_kst(2026, 10, 8))
    assert decision == {"run": True, "weekday_code": "thu", "configured_valid": False}
