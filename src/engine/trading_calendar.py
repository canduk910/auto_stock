"""cycle363 — 휴장일 판정 공용 leaf.

작업 지시서(정본) = `_workspace/red/cycle363_business_day_freshness_spec.md` §2.1.
설계 = `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §1.5·§3 표 ①·§8.

월요일·연휴 뒤 아침에 「몇 시간 지났나」·「달력 며칠 지났나」가 아니라 「**직전 영업일**
정기 실행/봉이 있나」를 판정하려는 두 시정(부팅 즉시 실행 슬롯 게이트 · 일봉 신선도)이
공유하는 휴장일 조회 leaf 다.

- 조회 seam = 모듈 전역 `_lookup_open(d)` — 호출 시점에 `src.api.condition.is_trading_day`
  (기존 3상태 함수: True=개장 / False=휴장 / None=모름)를 모듈 속성으로 찾는다(지연 import).
  `boot_manager._previous_trading_day` 는 조회 실패를 「영업일」로 삼키는 관측용 fail-open
  이라 재사용하지 않는다(그 함수는 무접촉) — `is_market_open`(실패 시 True)도 같은 이유로
  참조하지 않는다.
- 메모 = 모듈 전역 dict — True/False 만 **영구** 캐시(날짜의 개장 여부는 바뀌지 않는다).
  주말은 조회 없이 휴장. 40일보다 오래된 키는 **삽입되는 날짜** 기준으로 삽입 시
  정리한다(벽시계 무관 — 정리 기준이 벽시계면 이 leaf 를 쓰는 회귀 스위트가 달력이
  흐르는 것만으로 붉어진다).
- **cycle363 F-2** — None(모름)은 영구 캐시하지 않지만 `_NEGATIVE_CACHE_TTL_SECS`(90초)
  동안 별도 저장소(`_negative_memo`)에 짧게 재사용한다(같은 지연을 반복해서 기다리지
  않는다). 조회 자체는 `_LOOKUP_TIMEOUT_SECS`(5초)로 감싼다 — CTCA0903R 지연이 부팅
  prepare 를 분 단위로 늘리는 것을 막는다. 타임아웃도 never-raise 계약 안에서
  「모름」으로 흡수하고 「모르면 실행」 방향은 바뀌지 않는다.
- API 전부 never-raise(예외 → None). naive 벽시계 호출(`datetime.now()` 및 date 단독
  today 계열 인자 생략 호출) 금지 — KST 명시 강제.
- 8영역·`scheduler.py`·`boot_manager.py` import 0(leaf 경계).
"""

from __future__ import annotations

import asyncio
import time as _time_mod
from datetime import date, datetime, time, timedelta

from src.db._kst import KST

# 40일 초과 키는 삽입 시 정리(§2.1) — 프로세스 수명 메모의 상한.
_MEMO_MAX_AGE_DAYS = 40
# previous_trading_day 의 역산 상한(달력일) — 그 안에 전부 휴장이면 None.
_PREVIOUS_TRADING_DAY_LOOKBACK_DAYS = 10
# cycle363 F-2 — 조회 타임아웃(초). CTCA0903R 지연 시 부팅 prepare 가 분 단위로
# 늘어나는 것을 막는다(독립 검증 실측). 타임아웃도 never-raise 계약 안에서
# 「모름」(None) 으로 흡수한다 — 실행 쪽 fail-open 방향은 바뀌지 않는다.
_LOOKUP_TIMEOUT_SECS = 5.0
# cycle363 F-2 — None(모름) 음성 캐시 TTL(초). 같은 프로세스 수명 안에서 지연
# 응답을 반복해서 기다리지 않게 짧게 재사용한다(60~120초 권고 중간값). True/False
# 영구 메모(`_memo`)와는 별도 저장소 — "모름" 은 여전히 영구로 굳지 않는다.
_NEGATIVE_CACHE_TTL_SECS = 90.0

# 날짜 → 개장 여부(True/False 만). None(모름)은 여기 들어오지 않는다.
_memo: dict[date, bool] = {}
# cycle363 F-2 — 날짜 → 음성 캐시 만료 시각(monotonic). None(모름) 판정 전용.
_negative_memo: dict[date, float] = {}


def _now_monotonic() -> float:
    """cycle363 F-2 — 음성 캐시 TTL 의 유일한 시각 seam. 테스트가 이 이름을 패치한다."""
    return _time_mod.monotonic()


async def _lookup_open(d: date) -> bool | None:
    """조회 seam — 호출 시점에 `src.api.condition.is_trading_day` 를 모듈 속성으로 찾는다.

    3상태(True/False/None)를 그대로 위임한다. 그 함수 자체가 never-raise 계약이지만
    이 seam 은 대역(테스트)이 예외를 던질 수 있다는 전제를 깨지 않는다 — 예외 처리는
    호출자(`is_open_day`)의 몫이다.
    """
    import src.api.condition as _condition  # noqa: PLC0415 — 지연 import (순환 회피)

    return await _condition.is_trading_day(d)


def _evict_older_than(anchor: date) -> None:
    """`anchor` 기준 40일보다 오래된 메모 키를 정리한다(삽입 시점 기준, 벽시계 무관)."""
    cutoff = anchor - timedelta(days=_MEMO_MAX_AGE_DAYS)
    for key in [k for k in _memo if k < cutoff]:
        del _memo[key]


async def is_open_day(d: date) -> bool | None:
    """개장 여부 3상태. 주말은 조회 없이 휴장. True/False 만 캐시. never-raise.

    cycle363 F-2 — 조회는 `_LOOKUP_TIMEOUT_SECS`(5초) 로 감싸고, 타임아웃도
    모름(None)으로 흡수한다. None(모름) 결과는 `_NEGATIVE_CACHE_TTL_SECS`(90초)
    동안 음성 캐시한다 — 그 창 안의 재호출은 seam 을 다시 부르지 않는다(같은
    지연을 반복해서 기다리지 않는다). True/False 는 여전히 영구(프로세스 수명)
    메모다.
    """
    if d in _memo:
        return _memo[d]
    if d.weekday() >= 5:
        return False
    _neg_expires_at = _negative_memo.get(d)
    if _neg_expires_at is not None and _now_monotonic() < _neg_expires_at:
        return None
    try:
        result = await asyncio.wait_for(_lookup_open(d), timeout=_LOOKUP_TIMEOUT_SECS)
    except Exception:
        _negative_memo[d] = _now_monotonic() + _NEGATIVE_CACHE_TTL_SECS
        return None
    if result is None:
        _negative_memo[d] = _now_monotonic() + _NEGATIVE_CACHE_TTL_SECS
        return None
    _negative_memo.pop(d, None)
    _evict_older_than(d)
    _memo[d] = result
    return result


async def previous_trading_day(today: date) -> date | None:
    """`today` 보다 엄격히 이전의 가장 최근 개장일. 최대 10 달력일 역산.

    도중 None(모름)을 만나면 추측하지 않고 None 을 반환한다.
    """
    try:
        cursor = today
        for _ in range(_PREVIOUS_TRADING_DAY_LOOKBACK_DAYS):
            cursor = cursor - timedelta(days=1)
            opened = await is_open_day(cursor)
            if opened is None:
                return None
            if opened:
                return cursor
        return None
    except Exception:
        return None


_NEXT_TRADING_DAY_LOOKAHEAD_DAYS = 14


async def next_trading_day(d: date) -> date | None:
    """`d` 보다 엄격히 뒤의 가장 가까운 개장일. 최대 14 달력일, 도중 None 이면 None."""
    try:
        cursor = d
        for _ in range(_NEXT_TRADING_DAY_LOOKAHEAD_DAYS):
            cursor = cursor + timedelta(days=1)
            opened = await is_open_day(cursor)
            if opened is None:
                return None
            if opened:
                return cursor
        return None
    except Exception:
        return None


async def latest_passed_trading_slot(now_kst: datetime, slot: time) -> datetime | None:
    """`now` 이하인 「개장일 D 의 slot 시각」 중 가장 최근(KST aware).

    `now.time() >= slot` 이면 오늘부터 검사(오늘 개장 여부 조회, None → None,
    휴장이면 직전 영업일로 낙하), 아니면 `previous_trading_day(today)` 의 slot.
    """
    try:
        today = now_kst.date()
        if now_kst.time() >= slot:
            opened_today = await is_open_day(today)
            if opened_today is None:
                return None
            if opened_today:
                return datetime.combine(today, slot, tzinfo=KST)
            prev = await previous_trading_day(today)
            if prev is None:
                return None
            return datetime.combine(prev, slot, tzinfo=KST)
        prev = await previous_trading_day(today)
        if prev is None:
            return None
        return datetime.combine(prev, slot, tzinfo=KST)
    except Exception:
        return None


def _reset_cache_for_tests() -> None:
    """테스트 전용 — 프로세스 수명 메모(영구·음성 캐시 양쪽)를 비운다."""
    _memo.clear()
    _negative_memo.clear()
