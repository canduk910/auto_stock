"""cycle363 Red — 휴장일 판정 공용 leaf `src/engine/trading_calendar.py`.

지시서(정본) = `_workspace/red/cycle363_business_day_freshness_spec.md` §2.1 · §3.1 (13).
설계 = `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §3 표 ① · §8.

2026-09 달력(이 파일의 고정 시나리오): 09-18(금) 개장 · 09-21(월)~09-23(수) 개장 ·
**09-24(목)·09-25(금) 휴장(추석)** · 09-26(토)·09-27(일) 주말 · 09-28(월) 개장.

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약 (이 파일이 고정한다)
────────────────────────────────────────────────────────────────────────────
1) 모듈 `src.engine.trading_calendar` — 8영역·`boot_manager` import 0
   (`boot_manager._previous_trading_day` 는 조회 실패를 「영업일」로 삼키는 fail-open 이라
   「실패 → 실행」을 표현할 수 없다 — 재사용 금지, 그 함수는 무접촉).
2) 조회 seam = 모듈 전역 `async def _lookup_open(d: date) -> bool | None`.
   호출 시점에 `src.api.condition.is_trading_day` 를 **모듈 속성으로** 찾는다(지연 import).
   이 파일은 `src.api.condition.is_trading_day` 를 패치해 seam 의 위임까지 검증한다.
   leaf 내부 함수는 `_lookup_open` 을 **모듈 전역 이름으로** 부른다 — 전역 중립화 픽스처
   (`tests/conftest.py::_neutralize_trading_calendar`)가 그 이름 하나를 바꾼다.
3) 메모 = True/False 만 캐시(날짜의 개장 여부는 바뀌지 않는다), None 은 캐시하지 않는다.
   주말(`weekday() >= 5`)은 조회 없이 휴장. 40일보다 오래된 키는 **삽입 시** 정리하되
   기준은 삽입되는 날짜다(벽시계가 아니다 — L20 이 2027 년 시각에서도 2026-09 메모가
   살아 있음을 요구한다).
4) API 전부 never-raise(예외 → None):
   - `async def is_open_day(d) -> bool | None`
   - `async def previous_trading_day(today) -> date | None` — today 보다 **엄격히** 이전,
     달력 10일까지 역산, 도중 None 이면 None.
   - `async def latest_passed_trading_slot(now_kst, slot) -> datetime | None` — now 이하인
     「개장일 D 의 slot 시각」 중 가장 최근(KST aware). `now.time() >= slot` 이면 오늘부터
     (오늘 None → None, 오늘 휴장 → 직전 영업일), 아니면 `previous_trading_day(today)` 의 slot.
   - `def _reset_cache_for_tests() -> None`

이 파일은 `real_trading_calendar` 로 전역 중립화를 옵트아웃한다 — seam 을 실제로 타야
`is_trading_day` 위임과 메모 동작을 잴 수 있다.

Red 유효성: leaf 모듈 부재 → `tc` 픽스처의 import 가 ModuleNotFoundError → 전건 ERROR.
"""

from __future__ import annotations

import importlib
from datetime import date, datetime, time, timedelta

import pytest
from freezegun import freeze_time

from src.db._kst import KST

pytestmark = [pytest.mark.unit, pytest.mark.real_trading_calendar]

_HOLIDAYS = frozenset({date(2026, 9, 24), date(2026, 9, 25)})


class _FakeKisHoliday:
    """`src.api.condition.is_trading_day` 대역 — 호출 날짜를 전부 기록한다."""

    def __init__(
        self,
        *,
        unknown: frozenset = frozenset(),
        raise_on: frozenset = frozenset(),
        all_closed: bool = False,
    ) -> None:
        self.unknown = unknown
        self.raise_on = raise_on
        self.all_closed = all_closed
        self.calls: list[date] = []

    async def __call__(self, d):
        self.calls.append(d)
        if d in self.raise_on:
            raise RuntimeError("KIS CTCA0903R down")
        if d in self.unknown:
            return None
        if self.all_closed:
            return False
        return d.weekday() < 5 and d not in _HOLIDAYS


@pytest.fixture
def tc():
    mod = importlib.import_module("src.engine.trading_calendar")
    mod._reset_cache_for_tests()
    yield mod
    mod._reset_cache_for_tests()


def _install(monkeypatch, fake: _FakeKisHoliday) -> _FakeKisHoliday:
    monkeypatch.setattr("src.api.condition.is_trading_day", fake)
    return fake


def _kst(y, m, d, hh=0, mm=0, ss=0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, tzinfo=KST)


# ══════════════════════════════════════════════════════════════════════
# A. is_open_day — 주말 · 메모 · None 비캐시 · 예외
# ══════════════════════════════════════════════════════════════════════
async def test_L01_weekend_is_closed_without_lookup(tc, monkeypatch):
    """주말은 조회 없이 휴장 (M7 — 주말을 개장으로 취급하면 붉어진다)."""
    fake = _install(monkeypatch, _FakeKisHoliday())
    assert await tc.is_open_day(date(2026, 9, 26)) is False  # 토
    assert await tc.is_open_day(date(2026, 9, 27)) is False  # 일
    assert fake.calls == [], f"주말 조회 0회 의무 (실측 {fake.calls})"


async def test_L02_open_day_is_memoized(tc, monkeypatch):
    """같은 날짜 두 번째 조회는 seam 호출 0회 (CTCA0903R 「가급적 1일 1회」)."""
    fake = _install(monkeypatch, _FakeKisHoliday())
    assert await tc.is_open_day(date(2026, 9, 23)) is True
    assert await tc.is_open_day(date(2026, 9, 23)) is True
    assert fake.calls == [date(2026, 9, 23)], f"개장 True 메모 의무 (실측 {fake.calls})"


async def test_L03_holiday_false_is_memoized(tc, monkeypatch):
    """확정 휴장(False)도 메모한다 (추석 09-24)."""
    fake = _install(monkeypatch, _FakeKisHoliday())
    assert await tc.is_open_day(date(2026, 9, 24)) is False
    assert await tc.is_open_day(date(2026, 9, 24)) is False
    assert fake.calls == [date(2026, 9, 24)], f"휴장 False 메모 의무 (실측 {fake.calls})"


async def test_L04_unknown_none_is_negative_cached_within_ttl(tc, monkeypatch):
    """cycle363 F-2 — None(모름)은 영구 캐시되지 않지만 TTL(90초) 안엔 재사용한다.

    같은 지연(예: CTCA0903R 느림)을 반복해서 기다리지 않으려는 것이다. True/False
    는 여전히 영구 메모다 — None 만 짧게 재사용한다.
    """
    fake = _install(monkeypatch, _FakeKisHoliday(unknown=frozenset({date(2026, 9, 22)})))
    assert await tc.is_open_day(date(2026, 9, 22)) is None
    assert await tc.is_open_day(date(2026, 9, 22)) is None
    assert fake.calls == [date(2026, 9, 22)], (
        f"TTL 안의 두 번째 호출은 seam 을 다시 부르면 안 된다 (실측 {fake.calls})"
    )


async def test_L04b_unknown_none_negative_cache_expires_after_ttl(tc, monkeypatch):
    """cycle363 F-2 — TTL 경과 후에는 다시 조회한다(영구 캐시가 아니다)."""
    fake = _install(monkeypatch, _FakeKisHoliday(unknown=frozenset({date(2026, 9, 22)})))
    clock = {"t": 1_000.0}
    monkeypatch.setattr(tc, "_now_monotonic", lambda: clock["t"])
    assert await tc.is_open_day(date(2026, 9, 22)) is None
    clock["t"] += tc._NEGATIVE_CACHE_TTL_SECS + 0.01
    assert await tc.is_open_day(date(2026, 9, 22)) is None
    assert fake.calls == [date(2026, 9, 22), date(2026, 9, 22)], (
        f"TTL 경과 후에는 다시 조회 의무 (실측 {fake.calls})"
    )


async def test_L05_lookup_exception_returns_none_and_is_negative_cached_within_ttl(tc, monkeypatch):
    """조회 예외 → None (never-raise) + TTL 안엔 재사용."""
    fake = _install(monkeypatch, _FakeKisHoliday(raise_on=frozenset({date(2026, 9, 22)})))
    assert await tc.is_open_day(date(2026, 9, 22)) is None
    assert await tc.is_open_day(date(2026, 9, 22)) is None
    assert len(fake.calls) == 1, f"TTL 안의 재호출은 seam 을 다시 부르면 안 된다 (실측 {fake.calls})"


async def test_L05b_lookup_exception_negative_cache_expires_after_ttl(tc, monkeypatch):
    fake = _install(monkeypatch, _FakeKisHoliday(raise_on=frozenset({date(2026, 9, 22)})))
    clock = {"t": 1_000.0}
    monkeypatch.setattr(tc, "_now_monotonic", lambda: clock["t"])
    assert await tc.is_open_day(date(2026, 9, 22)) is None
    clock["t"] += tc._NEGATIVE_CACHE_TTL_SECS + 0.01
    assert await tc.is_open_day(date(2026, 9, 22)) is None
    assert len(fake.calls) == 2, f"TTL 경과 후 재조회 의무 (실측 {fake.calls})"


async def test_L05c_confirmed_result_after_negative_cache_clears_it_and_is_memoized(tc, monkeypatch):
    """TTL 경과 뒤 확정값(True/False)이 오면 음성 캐시를 지우고 영구 메모로 옮긴다."""
    fake = _install(monkeypatch, _FakeKisHoliday(unknown=frozenset({date(2026, 9, 22)})))
    clock = {"t": 1_000.0}
    monkeypatch.setattr(tc, "_now_monotonic", lambda: clock["t"])
    assert await tc.is_open_day(date(2026, 9, 22)) is None
    fake.unknown = frozenset()  # 다음 조회부터는 확정값을 준다
    clock["t"] += tc._NEGATIVE_CACHE_TTL_SECS + 0.01
    assert await tc.is_open_day(date(2026, 9, 22)) is True
    assert fake.calls == [date(2026, 9, 22), date(2026, 9, 22)]
    # 영구 메모로 옮겨졌으니 세 번째 호출은 seam 을 다시 부르지 않는다(TTL 무관).
    assert await tc.is_open_day(date(2026, 9, 22)) is True
    assert fake.calls == [date(2026, 9, 22), date(2026, 9, 22)], (
        "확정값 이후에는 영구 메모 — 세 번째 호출에서 seam 호출 금지"
    )


async def test_L26_lookup_timeout_is_absorbed_as_unknown_without_raising(tc, monkeypatch):
    """cycle363 F-2 — CTCA0903R 지연은 `_LOOKUP_TIMEOUT_SECS` 로 흡수 → None, 예외 없음."""
    import asyncio

    monkeypatch.setattr(tc, "_LOOKUP_TIMEOUT_SECS", 0.01)

    async def _hangs(_d):
        await asyncio.sleep(1.0)
        return True

    monkeypatch.setattr(tc, "_lookup_open", _hangs)
    got = await tc.is_open_day(date(2026, 9, 22))
    assert got is None, f"타임아웃은 모름(None)으로 흡수 의무 (실측 {got!r})"


async def test_L27_lookup_within_timeout_is_unaffected(tc, monkeypatch):
    """타임아웃보다 짧게 끝나는 정상 조회는 결과가 그대로 온다(회귀 0)."""
    fake = _install(monkeypatch, _FakeKisHoliday())
    got = await tc.is_open_day(date(2026, 9, 23))
    assert got is True
    assert fake.calls == [date(2026, 9, 23)]


async def test_L28_reset_cache_for_tests_clears_negative_memo_too(tc, monkeypatch):
    """cycle363 F-2 — `_reset_cache_for_tests` 는 음성 캐시도 함께 비운다."""
    fake = _install(monkeypatch, _FakeKisHoliday(unknown=frozenset({date(2026, 9, 22)})))
    assert await tc.is_open_day(date(2026, 9, 22)) is None
    tc._reset_cache_for_tests()
    assert await tc.is_open_day(date(2026, 9, 22)) is None
    assert fake.calls == [date(2026, 9, 22), date(2026, 9, 22)], (
        f"reset 뒤에는 음성 캐시가 비어 있어 다시 조회해야 한다 (실측 {fake.calls})"
    )


async def test_L06_seam_delegates_to_condition_is_trading_day(tc, monkeypatch):
    """`_lookup_open` 은 `src.api.condition.is_trading_day`(3상태)에 위임한다.

    `is_market_open`(실패 시 True)으로 바꾸면 「모름 → 실행」이 사라진다 — 위임 대상 고정.
    """
    fake = _install(monkeypatch, _FakeKisHoliday(unknown=frozenset({date(2026, 9, 22)})))
    assert await tc._lookup_open(date(2026, 9, 23)) is True
    assert await tc._lookup_open(date(2026, 9, 24)) is False
    assert await tc._lookup_open(date(2026, 9, 22)) is None
    assert fake.calls == [date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 22)]


async def test_L07_is_open_day_calls_seam_by_module_global_name(tc, monkeypatch):
    """leaf 는 `_lookup_open` 을 모듈 전역 이름으로 부른다 (전역 중립화 픽스처의 전제)."""
    seen: list[date] = []

    async def _seam(d):
        seen.append(d)
        return True

    monkeypatch.setattr(tc, "_lookup_open", _seam)
    assert await tc.is_open_day(date(2026, 9, 22)) is True
    assert seen == [date(2026, 9, 22)], "is_open_day 가 교체된 seam 을 부르지 않았다"


async def test_L08_reset_cache_for_tests_clears_memo(tc, monkeypatch):
    fake = _install(monkeypatch, _FakeKisHoliday())
    await tc.is_open_day(date(2026, 9, 23))
    tc._reset_cache_for_tests()
    await tc.is_open_day(date(2026, 9, 23))
    assert fake.calls == [date(2026, 9, 23), date(2026, 9, 23)]


# ══════════════════════════════════════════════════════════════════════
# B. 메모 수명 — 벽시계 독립 · 40일 정리
# ══════════════════════════════════════════════════════════════════════
async def test_L09_memo_does_not_depend_on_wall_clock(tc, monkeypatch):
    """메모 정리 기준은 벽시계가 아니다 — 2027 년에 돌려도 2026-09 메모가 산다.

    정리를 `today_kst()` 기준으로 하면 이 파일과 슬롯 게이트 테스트의 호출 수 단언이
    달력이 흐르는 것만으로 붉어진다(로컬/CI 시각 무관 결정론 요구).
    """
    fake = _install(monkeypatch, _FakeKisHoliday())
    with freeze_time("2027-06-01T12:00:00+09:00"):
        assert await tc.is_open_day(date(2026, 9, 23)) is True
        assert await tc.is_open_day(date(2026, 9, 23)) is True
    assert fake.calls == [date(2026, 9, 23)], f"벽시계 기준 정리 금지 (실측 {fake.calls})"


async def test_L10_memo_evicts_keys_older_than_40_days_on_insert(tc, monkeypatch):
    """40일보다 오래된 키는 삽입 시 정리 — 40일 이내 키는 유지."""
    fake = _install(monkeypatch, _FakeKisHoliday())
    await tc.is_open_day(date(2026, 9, 1))   # 09-23 기준 22일 전 → 유지
    await tc.is_open_day(date(2026, 8, 3))   # 09-23 기준 51일 전 → 정리 대상
    await tc.is_open_day(date(2026, 9, 23))  # 삽입 → 정리 발생
    before = len(fake.calls)
    await tc.is_open_day(date(2026, 9, 1))
    assert len(fake.calls) == before, "40일 이내 키는 정리하면 안 된다"
    await tc.is_open_day(date(2026, 8, 3))
    assert fake.calls[-1] == date(2026, 8, 3) and len(fake.calls) == before + 1, (
        f"40일 초과 키는 삽입 시 정리 의무 — 다시 조회돼야 한다 (실측 {fake.calls})"
    )


# ══════════════════════════════════════════════════════════════════════
# C. previous_trading_day
# ══════════════════════════════════════════════════════════════════════
async def test_L11_previous_trading_day_after_chuseok_is_0923(tc, monkeypatch):
    """09-28 기준 직전 영업일 = 09-23 (추석 이틀 + 주말 역산). 주말 조회 0."""
    fake = _install(monkeypatch, _FakeKisHoliday())
    assert await tc.previous_trading_day(date(2026, 9, 28)) == date(2026, 9, 23)
    assert set(fake.calls) == {date(2026, 9, 25), date(2026, 9, 24), date(2026, 9, 23)}, (
        f"평일만 조회 (실측 {fake.calls})"
    )
    assert all(d.weekday() < 5 for d in fake.calls)


async def test_L12_previous_trading_day_monday_skips_weekend(tc, monkeypatch):
    fake = _install(monkeypatch, _FakeKisHoliday())
    assert await tc.previous_trading_day(date(2026, 9, 21)) == date(2026, 9, 18)
    assert fake.calls == [date(2026, 9, 18)], f"주말 조회 0 (실측 {fake.calls})"


async def test_L13_previous_trading_day_is_strictly_before_today(tc, monkeypatch):
    _install(monkeypatch, _FakeKisHoliday())
    assert await tc.previous_trading_day(date(2026, 9, 23)) == date(2026, 9, 22), (
        "today 가 개장일이어도 today 자신은 반환 금지 (엄격히 이전)"
    )


async def test_L14_previous_trading_day_unknown_midway_returns_none(tc, monkeypatch):
    """역산 도중 None(모름)을 만나면 None — 추측으로 건너뛰지 않는다."""
    _install(monkeypatch, _FakeKisHoliday(unknown=frozenset({date(2026, 9, 24)})))
    assert await tc.previous_trading_day(date(2026, 9, 28)) is None


async def test_L15_previous_trading_day_lookup_exception_returns_none(tc, monkeypatch):
    _install(monkeypatch, _FakeKisHoliday(raise_on=frozenset({date(2026, 9, 25)})))
    assert await tc.previous_trading_day(date(2026, 9, 28)) is None


async def test_L16_previous_trading_day_gives_up_within_10_calendar_days(tc, monkeypatch):
    """전부 휴장이면 달력 10일 역산 후 None. 10일 밖은 조회하지 않는다."""
    today = date(2026, 9, 28)
    fake = _install(monkeypatch, _FakeKisHoliday(all_closed=True))
    assert await tc.previous_trading_day(today) is None
    assert fake.calls, "평일은 조회해야 한다"
    assert all(today - timedelta(days=10) <= d < today for d in fake.calls), (
        f"달력 10일(today-10 ~ today-1) 밖 조회 금지 (실측 {sorted(fake.calls)})"
    )


# ══════════════════════════════════════════════════════════════════════
# D. latest_passed_trading_slot
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "slot",
    [time(20, 30), time(16, 10), time(20, 0, 5)],
    ids=["daily_20:30", "basics_16:10", "full_universe_20:00:05"],
)
async def test_L17_before_slot_uses_previous_trading_day(tc, monkeypatch, slot):
    """09-28 07:45 — 오늘 슬롯 전 → 직전 영업일(09-23)의 슬롯."""
    _install(monkeypatch, _FakeKisHoliday())
    got = await tc.latest_passed_trading_slot(_kst(2026, 9, 28, 7, 45), slot)
    assert got == datetime.combine(date(2026, 9, 23), slot, tzinfo=KST), f"실측 {got!r}"


async def test_L18_after_slot_on_open_day_is_today(tc, monkeypatch):
    """화 09-22 17:00 — basics(16:10) 는 오늘 슬롯, daily(20:30) 는 어제(월) 슬롯."""
    _install(monkeypatch, _FakeKisHoliday())
    now = _kst(2026, 9, 22, 17, 0)
    assert await tc.latest_passed_trading_slot(now, time(16, 10)) == _kst(2026, 9, 22, 16, 10)
    assert await tc.latest_passed_trading_slot(now, time(20, 30)) == _kst(2026, 9, 21, 20, 30)


async def test_L19_exactly_at_slot_counts_as_passed(tc, monkeypatch):
    """`now.time() >= slot` — 경계 시각 포함."""
    _install(monkeypatch, _FakeKisHoliday())
    got = await tc.latest_passed_trading_slot(_kst(2026, 9, 22, 16, 10), time(16, 10))
    assert got == _kst(2026, 9, 22, 16, 10)


async def test_L20_after_slot_on_holiday_falls_back_to_previous(tc, monkeypatch):
    """휴장일(09-24) 17:00 — 오늘은 슬롯이 없다 → 09-23 16:10."""
    _install(monkeypatch, _FakeKisHoliday())
    got = await tc.latest_passed_trading_slot(_kst(2026, 9, 24, 17, 0), time(16, 10))
    assert got == _kst(2026, 9, 23, 16, 10)


async def test_L21_after_slot_today_unknown_returns_none(tc, monkeypatch):
    """오늘 개장 여부를 모르면 None — 어제 슬롯으로 추측하지 않는다."""
    _install(monkeypatch, _FakeKisHoliday(unknown=frozenset({date(2026, 9, 22)})))
    assert await tc.latest_passed_trading_slot(_kst(2026, 9, 22, 17, 0), time(16, 10)) is None


async def test_L22_before_slot_previous_unknown_returns_none(tc, monkeypatch):
    _install(monkeypatch, _FakeKisHoliday(unknown=frozenset({date(2026, 9, 24)})))
    assert await tc.latest_passed_trading_slot(_kst(2026, 9, 28, 7, 45), time(20, 30)) is None


async def test_L23_slot_result_is_kst_aware(tc, monkeypatch):
    _install(monkeypatch, _FakeKisHoliday())
    got = await tc.latest_passed_trading_slot(_kst(2026, 9, 21, 7, 45), time(20, 30))
    assert got is not None and got.tzinfo is not None
    assert got.utcoffset() == timedelta(hours=9), f"KST aware 의무 (실측 {got!r})"
    assert got == _kst(2026, 9, 18, 20, 30)


async def test_L24_slot_and_previous_share_the_memo(tc, monkeypatch):
    """같은 부팅의 세 게이트가 같은 날짜를 다시 묻지 않는다 (날짜당 프로세스 수명 1회)."""
    fake = _install(monkeypatch, _FakeKisHoliday())
    await tc.previous_trading_day(date(2026, 9, 28))
    first = len(fake.calls)
    for slot in (time(20, 30), time(16, 10), time(20, 0, 5)):
        await tc.latest_passed_trading_slot(_kst(2026, 9, 28, 7, 45), slot)
    assert len(fake.calls) == first, f"메모 공유 의무 (실측 {fake.calls})"


async def test_L25_latest_passed_slot_never_raises(tc, monkeypatch):
    """seam 이 무엇을 던져도 None (never-raise)."""
    async def _boom(_d):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(tc, "_lookup_open", _boom)
    assert await tc.latest_passed_trading_slot(_kst(2026, 9, 28, 7, 45), time(20, 30)) is None
    assert await tc.previous_trading_day(date(2026, 9, 28)) is None
    assert await tc.is_open_day(date(2026, 9, 28)) is None
