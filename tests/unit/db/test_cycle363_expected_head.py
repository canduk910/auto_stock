"""cycle363 Red — ①′ 일봉 신선도를 「직전 영업일」 기준으로 (`expected_head`).

지시서(정본) = `_workspace/red/cycle363_business_day_freshness_spec.md` §2.4 · §3.1 (14)~(17).
설계 = `_workspace/domain_consult/cycle360_boot_reprepare_4a_proposal.md` §1.5 · §3 표 ①′.

결함(코드 계산): `DAILY_STALENESS_DAYS = 4` 는 **달력일**이다. 09-28(월)은 추석 연휴 뒤
첫 영업일이라 `(09-28 − 09-23).days = 5 > 4` → 부팅 준비·재준비에서 **모든 종목이 KIS
100봉 폴백**으로 간다. VCP `daily_fetch_depth_mode="full"`(250봉 설계)이 그날 100봉이 된다.

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 계약
────────────────────────────────────────────────────────────────────────────
- 시그니처 `get_recent_daily_normalized(ticker, days, *, min_required=None,
  expected_head: date | None = None)` — `expected_head` 는 **키워드 전용**, 기본 None.
- 2번 신선도 게이트만 바뀐다:
  · `expected_head is not None` → `latest < expected_head` 면 KIS 폴백 `reason="stale"`
    (어휘 유지). 달력 판정(`DAILY_STALENESS_DAYS`)은 보지 않는다.
  · `expected_head is None` → 현행 달력 판정 **바이트 동일**(하위 호환).
- 락 게이트(1) · min_required 게이트(3) · `_kis_fallback` · `DAILY_STALENESS_DAYS=4` 무변경.
- 알려진 부작용(고정): 하루치 결손도 폴백(`latest = expected_head − 1영업일` → 폴백).

`reason` 은 `_kis_fallback(..., reason=...)` 키워드로 잰다(모듈 전역 이름 — 패치 seam).
시각은 `freeze_time` 으로 고정한다 — 어댑터는 `await asyncio.sleep` 이 없어 cycle187 의
freezegun+asyncio hang 조건에 해당하지 않는다(cycle263 C 계열과 같은 사용).

Red 유효성: `expected_head` kw 미존재 → TypeError (D1~D5·D7~D9) · 시그니처 단언 KeyError(D0).
D6(kw 생략 = 현행)·D10(상수) 은 **불변식**(현재도 PASS, Green 이 깨면 안 된다).
"""

from __future__ import annotations

import inspect
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

_TUE_0922 = date(2026, 9, 22)
_WED_0923 = date(2026, 9, 23)
_MON_0928_MORNING = "2026-09-28T07:50:00+09:00"
_KIS_ROWS = [{"stck_bsop_date": "20260923", "stck_clpr": "71000", "src": "kis"}]


def _db_rows(n: int, *, head: date = _WED_0923, lock_at: int | None = None) -> list[dict]:
    """정상(락 없음) DB rows, DESC. `lock_at` 위치 1행만 락 표시."""
    rows = []
    for i in range(n):
        dd = head - timedelta(days=i)
        rows.append({
            "ticker": "005930",
            "bas_dd": dd.isoformat(),
            "close_price": 71000 - i,
            "flng_cls_code": "02" if i == lock_at else "00",
            "prtt_rate": "0.0000",
            "raw": {
                "stck_bsop_date": dd.strftime("%Y%m%d"),
                "stck_clpr": str(71000 - i),
                "src": "db",
            },
        })
    return rows


async def _call(
    *,
    db_rows: list[dict],
    latest,
    days: int = 22,
    min_required: int | None = 22,
    pass_expected: bool = True,
    expected_head=None,
    max_bas_dd_side_effect=None,
):
    """어댑터 1회 호출. 반환 = (rows, kis_fallback_mock, max_bas_dd_mock)."""
    from src.db import stock_master_daily as _smd

    fb = AsyncMock(return_value=_KIS_ROWS)
    mbd = (
        AsyncMock(side_effect=max_bas_dd_side_effect)
        if max_bas_dd_side_effect is not None
        else AsyncMock(return_value=latest)
    )
    kwargs = {"min_required": min_required}
    if pass_expected:
        kwargs["expected_head"] = expected_head
    with patch.object(_smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(_smd, "max_bas_dd", new=mbd), \
            patch.object(_smd, "_kis_fallback", new=fb):
        rows = await _smd.get_recent_daily_normalized("005930", days, **kwargs)
    return rows, fb, mbd


def _reason(fb: AsyncMock) -> str | None:
    if fb.await_count == 0:
        return None
    return fb.await_args.kwargs.get("reason")


# ══════════════════════════════════════════════════════════════════════
def test_D0_signature_has_keyword_only_expected_head_default_none():
    from src.db.stock_master_daily import get_recent_daily_normalized

    params = inspect.signature(get_recent_daily_normalized).parameters
    assert "expected_head" in params, "①′ — `expected_head` 인자 부재"
    p = params["expected_head"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY, "키워드 전용 의무 (위치 인자 호출부 호환)"
    assert p.default is None, "기본 None = 현행 달력 판정 (하위 호환)"


@pytest.mark.parametrize(
    "frozen",
    [_MON_0928_MORNING, "2026-12-31T08:00:00+09:00"],
    ids=["0928_after_chuseok", "wall_clock_far_later"],
)
async def test_D1_after_chuseok_head_equals_expected_uses_db(frozen):
    """(14) 09-28 · latest=09-23 · expected_head=09-23 → **DB 경로(폴백 0)**.

    달력 판정이면 5일 > 4 → 전 종목 KIS 폴백. `expected_head` 가 있으면 벽시계를 보지 않는다.
    """
    with freeze_time(frozen):
        rows, fb, _ = await _call(
            db_rows=_db_rows(30), latest=_WED_0923, expected_head=_WED_0923,
        )
    assert fb.await_count == 0, f"직전 영업일 봉이 헤드 → 폴백 금지 (reason={_reason(fb)!r})"
    assert rows and rows[0]["src"] == "db" and rows[0]["stck_bsop_date"] == "20260923"


async def test_D2_vcp_full_depth_250_rows_preserved():
    """(14) `days=250` 요청이 DB 250행을 그대로 반환 — VCP full 모드 보존(KIS 100봉 절단 없음)."""
    with freeze_time(_MON_0928_MORNING):
        rows, fb, _ = await _call(
            db_rows=_db_rows(250), latest=_WED_0923, expected_head=_WED_0923,
            days=250, min_required=100,
        )
    assert fb.await_count == 0
    assert len(rows) == 250, f"DB 250행 그대로 (실측 {len(rows)})"
    assert all(r.get("src") == "db" for r in rows)


async def test_D3_one_day_gap_falls_back_as_stale():
    """(15) latest=09-22 · expected_head=09-23 → KIS 폴백 `reason=stale`.

    알려진 부작용 고정 — 하루치 결손도 폴백이다(저녁 적재 결손일엔 전 종목 폴백,
    값은 맞아지지만 prepare 가 느려진다; `[daily_head_stale]` 가 같은 날 알린다).
    """
    with freeze_time(_MON_0928_MORNING):
        rows, fb, _ = await _call(
            db_rows=_db_rows(30, head=_TUE_0922), latest=_TUE_0922, expected_head=_WED_0923,
        )
    assert fb.await_count == 1 and _reason(fb) == "stale", f"reason={_reason(fb)!r}"
    assert rows == _KIS_ROWS


async def test_D4_explicit_none_keeps_calendar_judgment():
    """(16) expected_head=None(명시) · 09-28 · latest=09-23 → 현행 달력 판정 = 폴백 `stale`."""
    with freeze_time(_MON_0928_MORNING):
        _rows, fb, _ = await _call(
            db_rows=_db_rows(30), latest=_WED_0923, expected_head=None,
        )
    assert fb.await_count == 1 and _reason(fb) == "stale", (
        f"None = 달력 4일 판정 바이트 동일 의무 (reason={_reason(fb)!r})"
    )


async def test_D5_explicit_none_calendar_boundary_4_days_uses_db():
    """(16) None 경로 경계 — (today − latest).days == 4 는 폴백 아님(현행 `> 4`)."""
    with freeze_time(_MON_0928_MORNING):
        _rows, fb, _ = await _call(
            db_rows=_db_rows(30, head=date(2026, 9, 24)), latest=date(2026, 9, 24),
            expected_head=None,
        )
    assert fb.await_count == 0, f"4일 = 경계 안 (reason={_reason(fb)!r})"


async def test_D6_kwarg_omitted_is_current_behavior():
    """(16) 인자 생략 호출부(kojiro recompute·llm_buy_gate)는 현행 그대로 (불변식, Red PASS)."""
    with freeze_time(_MON_0928_MORNING):
        _rows, fb, _ = await _call(
            db_rows=_db_rows(30), latest=_WED_0923, pass_expected=False,
        )
    assert fb.await_count == 1 and _reason(fb) == "stale"


async def test_D7_lock_gate_still_precedes_freshness():
    """(17) 락 게이트가 여전히 신선도보다 먼저 — 락이면 `reason=lock`, 헤드 조회 전."""
    with freeze_time(_MON_0928_MORNING):
        _rows, fb, mbd = await _call(
            db_rows=_db_rows(30, lock_at=7), latest=_WED_0923, expected_head=_WED_0923,
        )
    assert fb.await_count == 1 and _reason(fb) == "lock", f"reason={_reason(fb)!r}"
    assert mbd.await_count == 0, "락 판정이 신선도(max_bas_dd) 조회보다 먼저"


async def test_D8_head_newer_than_expected_is_not_stale():
    """latest > expected_head (저녁 캡처 as_of 등) → DB 경로. 폴백 조건은 `latest < expected_head` 뿐."""
    with freeze_time(_MON_0928_MORNING):
        _rows, fb, _ = await _call(
            db_rows=_db_rows(30, head=date(2026, 9, 28)), latest=date(2026, 9, 28),
            expected_head=_WED_0923,
        )
    assert fb.await_count == 0, f"reason={_reason(fb)!r}"


@pytest.mark.parametrize(
    "latest, side_effect",
    [(None, None), (None, RuntimeError("pg down"))],
    ids=["max_bas_dd_none", "max_bas_dd_raises"],
)
async def test_D9_head_unknown_is_graceful_pass(latest, side_effect):
    """헤드 판정 불가(None/예외) → 현행처럼 graceful 통과 → min_required 충분하면 DB."""
    with freeze_time(_MON_0928_MORNING):
        _rows, fb, _ = await _call(
            db_rows=_db_rows(30), latest=latest, expected_head=_WED_0923,
            max_bas_dd_side_effect=side_effect,
        )
    assert fb.await_count == 0, f"reason={_reason(fb)!r}"


async def test_D9b_min_required_gate_still_after_freshness():
    """신선해도 행 수 부족 → `reason=insufficient` (3번 게이트 무변경)."""
    with freeze_time(_MON_0928_MORNING):
        _rows, fb, _ = await _call(
            db_rows=_db_rows(10), latest=_WED_0923, expected_head=_WED_0923, min_required=22,
        )
    assert fb.await_count == 1 and _reason(fb) == "insufficient", f"reason={_reason(fb)!r}"


# ══════════════════════════════════════════════════════════════════════
# F-3 (독립 검증 finding #3, 사용자 결정 2) — 깊은 읽기(>100봉) + 1영업일 결손
# ══════════════════════════════════════════════════════════════════════
# 결함: VCP `daily_fetch_depth_mode="full"`(운영, ~250봉 요청)에서 헤드가 하루만
# 밀린 종목도 KIS 폴백으로 떨어지는데, KIS 는 1회 100봉만 준다 — 200 EMA 가
# 75 EMA 로 퇴화한다(평상시 요일에도 발생, 연휴와 무관). 시정 = `days > 100` 이고
# `latest` 가 `expected_head` 의 **정확히 1영업일 전**이면 폴백하지 않고 DB 를 쓴다.
# 2영업일 이상 결손·얕은 요청(≤100봉)은 이 예외에 걸리지 않고 현행대로 폴백한다.
async def _call_with_calendar(
    *, previous_trading_day_return=None, previous_trading_day_side_effect=None, **kwargs,
):
    from src.engine import trading_calendar as _tc

    mock = AsyncMock(
        side_effect=previous_trading_day_side_effect,
    ) if previous_trading_day_side_effect is not None else AsyncMock(
        return_value=previous_trading_day_return,
    )
    with patch.object(_tc, "previous_trading_day", new=mock):
        rows, fb, mbd = await _call(**kwargs)
    return rows, fb, mbd, mock


async def test_F3a_deep_read_one_business_day_behind_uses_db():
    """days=250(VCP full) · latest=09-22(정확히 1영업일 결손) → 폴백 금지, DB 250행 그대로."""
    with freeze_time(_MON_0928_MORNING):
        rows, fb, _, cal = await _call_with_calendar(
            previous_trading_day_return=_TUE_0922,
            db_rows=_db_rows(250, head=_TUE_0922), latest=_TUE_0922, expected_head=_WED_0923,
            days=250, min_required=100,
        )
    assert fb.await_count == 0, f"1영업일 결손 + 100봉 초과 요청 → 폴백 금지(reason={_reason(fb)!r})"
    assert len(rows) == 250, f"DB 250행 그대로 — 100봉 KIS 폴백으로 깎이면 안 된다(실측 {len(rows)})"
    cal.assert_awaited_once_with(_WED_0923)


async def test_F3b_deep_read_two_business_days_behind_still_falls_back():
    """days=250 · latest=09-18(2영업일 이상 결손, `previous_trading_day(09-23)=09-22 ≠ 09-18`).

    설계 결정 — 연휴 뒤 전 종목 폴백 방지가 목적이 아니라 "값을 바로잡는 것"이 목적이므로
    2영업일 이상은 이 예외에 걸리지 않고 현행대로 KIS 폴백한다.
    """
    with freeze_time(_MON_0928_MORNING):
        rows, fb, _, _cal = await _call_with_calendar(
            previous_trading_day_return=_TUE_0922,
            db_rows=_db_rows(250, head=date(2026, 9, 18)), latest=date(2026, 9, 18),
            expected_head=_WED_0923, days=250, min_required=100,
        )
    assert fb.await_count == 1 and _reason(fb) == "stale", f"reason={_reason(fb)!r}"
    assert rows == _KIS_ROWS


async def test_F3c_shallow_read_one_business_day_behind_still_falls_back():
    """days=22(≤100, VB/LTV 규모) · 1영업일 결손이어도 현행대로 폴백 — 얕은 요청은 예외 밖."""
    with freeze_time(_MON_0928_MORNING):
        rows, fb, _, cal = await _call_with_calendar(
            previous_trading_day_return=_TUE_0922,
            db_rows=_db_rows(30, head=_TUE_0922), latest=_TUE_0922, expected_head=_WED_0923,
            days=22,
        )
    assert fb.await_count == 1 and _reason(fb) == "stale", f"reason={_reason(fb)!r}"
    assert rows == _KIS_ROWS
    cal.assert_not_awaited(), "days<=100 이면 `and` 단락 평가로 휴장일 조회 자체가 없어야 한다"


async def test_F3d_boundary_days_exactly_100_still_falls_back():
    """`days=100`(경계, 100 초과 아님) → 1영업일 결손이어도 폴백. 조건은 엄격히 `>`."""
    with freeze_time(_MON_0928_MORNING):
        rows, fb, _, cal = await _call_with_calendar(
            previous_trading_day_return=_TUE_0922,
            db_rows=_db_rows(120, head=_TUE_0922), latest=_TUE_0922, expected_head=_WED_0923,
            days=100, min_required=50,
        )
    assert fb.await_count == 1 and _reason(fb) == "stale", f"reason={_reason(fb)!r}"
    cal.assert_not_awaited()


@pytest.mark.parametrize(
    "prev_return, prev_side_effect",
    [(None, None), (None, RuntimeError("KIS CTCA0903R down"))],
    ids=["previous_trading_day_none", "previous_trading_day_raises"],
)
async def test_F3e_calendar_unknown_falls_back_safe_direction(prev_return, prev_side_effect):
    """휴장일 조회 모름/예외 → 「정확히 1영업일」을 확신할 수 없으므로 안전 방향(폴백)."""
    with freeze_time(_MON_0928_MORNING):
        rows, fb, _, _cal = await _call_with_calendar(
            previous_trading_day_return=prev_return,
            previous_trading_day_side_effect=prev_side_effect,
            db_rows=_db_rows(250, head=_TUE_0922), latest=_TUE_0922, expected_head=_WED_0923,
            days=250, min_required=100,
        )
    assert fb.await_count == 1 and _reason(fb) == "stale", f"reason={_reason(fb)!r}"
    assert rows == _KIS_ROWS


async def test_F3f_exact_match_head_never_consults_calendar_even_with_deep_read():
    """latest == expected_head(신선) · days=250 → 애초에 신선도 게이트를 안 타 휴장일 조회 0."""
    with freeze_time(_MON_0928_MORNING):
        rows, fb, _, cal = await _call_with_calendar(
            previous_trading_day_return=_TUE_0922,
            db_rows=_db_rows(250), latest=_WED_0923, expected_head=_WED_0923,
            days=250, min_required=100,
        )
    assert fb.await_count == 0
    assert len(rows) == 250
    cal.assert_not_awaited(), "신선(latest >= expected_head)이면 F-3 분기 자체에 도달하지 않는다"


async def test_F3g_deep_read_weekday_two_business_days_behind_within_calendar_keeps_db():
    """사용자 결정 「깊은 읽기는 DB 유지(현행 행위 보존)」 — 평일 2영업일 결손이라도
    현행 달력 판정(4일 이내)으로 신선하면 DB 250행 그대로(100봉 KIS 폴백 금지).

    금 09-18 07:50 · expected_head=목 09-17 · latest=화 09-15(2영업일 결손, 달력 3일).
    현행 달력 판정이 먼저 참이라 휴장일 조회는 하지 않는다(`or` 단락 평가).
    """
    with freeze_time("2026-09-18 07:50:00+09:00"):
        rows, fb, _, cal = await _call_with_calendar(
            previous_trading_day_return=date(2026, 9, 16),
            db_rows=_db_rows(250, head=date(2026, 9, 15)), latest=date(2026, 9, 15),
            expected_head=date(2026, 9, 17), days=250, min_required=100,
        )
    assert fb.await_count == 0, f"깊은 읽기 + 달력 4일 이내 → 폴백 금지(reason={_reason(fb)!r})"
    assert len(rows) == 250
    cal.assert_not_awaited()


async def test_F3h_shallow_read_weekday_two_business_days_behind_still_falls_back():
    """얕은 요청(≤100봉)은 달력 4일 이내여도 expected_head 기준으로 폴백(①′ 본래 동작)."""
    with freeze_time("2026-09-18 07:50:00+09:00"):
        rows, fb, _, cal = await _call_with_calendar(
            previous_trading_day_return=date(2026, 9, 16),
            db_rows=_db_rows(30, head=date(2026, 9, 15)), latest=date(2026, 9, 15),
            expected_head=date(2026, 9, 17), days=22,
        )
    assert fb.await_count == 1 and _reason(fb) == "stale", f"reason={_reason(fb)!r}"
    cal.assert_not_awaited()


def test_D10_staleness_constant_unchanged():
    """`DAILY_STALENESS_DAYS = 4` 무변경 (None 경로·다른 호출부가 계속 쓴다)."""
    from src.db.stock_master_daily import DAILY_STALENESS_DAYS

    assert DAILY_STALENESS_DAYS == 4
