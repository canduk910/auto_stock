"""cycle364 S1 Red — CAL: `trading_calendar.next_trading_day(d)`.

설계 정본 = `_workspace/domain_consult/cycle364_a1_as_of_design.md` §2.2 · §6.2 CAL.

2026-09 달력: 09-18(금) 개장 · 09-21(월)~09-23(수) 개장 · 09-24(목)·09-25(금) 휴장(추석) ·
09-26(토)·09-27(일) 주말 · 09-28(월) 개장.

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약
────────────────────────────────────────────────────────────────────────────
- `async def next_trading_day(d: date) -> date | None` — `d` 보다 **엄격히** 뒤의 가장 가까운
  개장일. 앞으로 최대 14 달력일 순회, 도중 None(모름)이면 None(추측 금지), 주말은 조회하지
  않음(`is_open_day` 재사용 = 메모 재사용), never-raise.
- 추석 5일 연휴(09-24~09-28 앞) 형태도 한 번에 넘는다.

seam = `_lookup_open` 을 이 파일이 **직접** 갈아 끼운다(conftest 전역 중립화보다 뒤에 걸려
이긴다) — 호출 날짜를 기록해 「주말 조회 0」·「메모」를 잰다.

Red 유효성: 함수 부재 → AttributeError(assert 메시지로 고정).
"""

from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.unit

_HOLIDAYS = frozenset({date(2026, 9, 24), date(2026, 9, 25)})


class _Cal:
    def __init__(self, *, unknown=frozenset(), boom=frozenset(), holidays=_HOLIDAYS):
        self.calls: list[date] = []
        self.unknown = set(unknown)
        self.boom = set(boom)
        self.holidays = set(holidays)

    async def __call__(self, d: date):
        self.calls.append(d)
        if d in self.boom:
            raise RuntimeError("CTCA0903R 장애")
        if d in self.unknown:
            return None
        return d.weekday() < 5 and d not in self.holidays


def _fn():
    from src.engine import trading_calendar as tc

    fn = getattr(tc, "next_trading_day", None)
    assert callable(fn), "trading_calendar.next_trading_day 미구현 (Red — cycle364 §2.2)"
    return fn


@pytest.fixture
def cal(monkeypatch):
    c = _Cal()
    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", c)
    return c


async def test_cal_1_when_wednesday_before_chuseok_then_next_monday_0928(cal):
    got = await _fn()(date(2026, 9, 23))
    assert got == date(2026, 9, 28), f"09-23 다음 거래일 = 09-28 (추석·주말 건너뜀) — 실측 {got}"
    assert sorted(cal.calls) == [date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 28)], (
        f"조회 날짜 {cal.calls} — 주말(09-26·27)은 조회하지 않는다"
    )


async def test_cal_2_when_friday_then_monday_and_weekend_not_queried(cal):
    got = await _fn()(date(2026, 9, 18))
    assert got == date(2026, 9, 21)
    assert cal.calls == [date(2026, 9, 21)], f"금→월: 주말 조회 0 (실측 {cal.calls})"


async def test_cal_3_when_midweek_then_next_day_strictly_after(cal):
    assert await _fn()(date(2026, 9, 21)) == date(2026, 9, 22), "엄격히 뒤 — 자기 자신을 돌려주지 않는다"


async def test_cal_4_when_called_twice_then_second_uses_memo(cal):
    fn = _fn()
    await fn(date(2026, 9, 23))
    n = len(cal.calls)
    again = await fn(date(2026, 9, 23))
    assert again == date(2026, 9, 28)
    assert len(cal.calls) == n, f"두 번째 호출이 seam 을 다시 불렀다 ({len(cal.calls) - n}회) — 메모 재사용"


async def test_cal_5_when_intermediate_day_unknown_then_none_not_guess(monkeypatch):
    c = _Cal(unknown={date(2026, 9, 24)})
    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", c)
    got = await _fn()(date(2026, 9, 23))
    assert got is None, f"도중 모름 → None (추측한 날짜로 라벨을 붙이지 않는다 §2.2) — 실측 {got}"


async def test_cal_6_when_lookup_raises_then_none_never_raise(monkeypatch):
    c = _Cal(boom={date(2026, 9, 24)})
    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", c)
    assert await _fn()(date(2026, 9, 23)) is None


async def test_cal_7_when_no_open_day_within_14_days_then_none(monkeypatch):
    every_weekday = {date(2026, 10, 1).fromordinal(date(2026, 10, 1).toordinal() + i) for i in range(40)}
    c = _Cal(holidays=every_weekday)
    monkeypatch.setattr("src.engine.trading_calendar._lookup_open", c)
    got = await _fn()(date(2026, 9, 30))
    assert got is None, f"14 달력일 안에 개장일이 없으면 None (실측 {got})"
    assert all(d <= date(2026, 10, 14) for d in c.calls), (
        f"상한 14 달력일을 넘어 조회했다: {max(c.calls)}"
    )
