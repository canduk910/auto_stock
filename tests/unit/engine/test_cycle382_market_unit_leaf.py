"""cycle382 Red — 시장 유닛 leaf(`src/engine/market_unit.py`) 판정 · 로더 · 모드 정규화 (R01~R16).

명세 = `_workspace/red/cycle382_market_unit_spec.md` §1 · §2 · §3.1 · §11.1 · §11.2(leaf)

규칙 한 줄: KODEX 200(`069500`) 종가의 **마지막 80봉**(`bas_dd < as_of`)으로
``sum60 = sum(w[20:80])`` · ``sum60_prev = sum(w[0:60])`` ·
``above = w[-1]*60 > sum60`` · ``rising = sum60 > sum60_prev`` (둘 다 엄격 부등호, 동률은 약한 쪽).
위·상승 1 / 위·하락 ¾ / 아래·상승 ½ / 아래·하락 0. 결측·stale·예외 → m = 1 (fail-open).

Red 유효성: leaf 가 없으므로 모든 테스트가 `[Red] src/engine/market_unit.py 미존재` 로 실패한다.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from types import MappingProxyType

import pytest
from freezegun import freeze_time

from tests.unit.engine._cycle382_support import (
    D1, D2, D3, D4, DAY, F1, F2, F3, F4, HEAD, NEXT, T2, T3, TF,
    Seams, field, kst, lines, make, mu, need_base, open_info, rows_for,
)

pytestmark = pytest.mark.unit


def _cls(closes):
    c, reason = mu().classify(list(closes))
    return c, reason


def _state_m(closes) -> tuple[str, float]:
    c, reason = _cls(closes)
    assert reason == "ok", f"classify reason={reason!r} (기대 ok)"
    assert c is not None
    return c.state, float(c.m)


# ===========================================================================
# 상수 (명세 §1.3 · §3.1)
# ===========================================================================
def test_r00_constants_and_multiplier_table_are_the_spec_values():
    lf = mu()
    assert lf.SOURCE_TICKER == "069500"
    assert (lf.MA_WINDOW, lf.SLOPE_LOOKBACK, lf.MIN_ROWS, lf.FETCH_ROWS) == (60, 20, 80, 120)
    assert lf.MIN_ROWS == lf.MA_WINDOW + lf.SLOPE_LOOKBACK
    assert isinstance(lf.MULTIPLIERS, MappingProxyType), "배수표는 읽기 전용 매핑이어야 한다"
    assert dict(lf.MULTIPLIERS) == {
        "up_rising": 1.0, "up_falling": 0.75, "down_rising": 0.5, "down_falling": 0.0,
    }
    assert lf.MODE_KEY == "market_unit_mode"
    assert tuple(lf.MODES) == ("off", "shadow", "enforce")


def test_r00_stale_fallback_days_equals_market_regime_etf_constant():
    from src.engine import market_regime

    assert mu().STALE_FALLBACK_MAX_CALENDAR_DAYS == 10
    assert mu().STALE_FALLBACK_MAX_CALENDAR_DAYS == market_regime.ETF_STALE_MAX_CALENDAR_DAYS


# ===========================================================================
# R01~R04 — 네 상태 · 배수
# ===========================================================================
@pytest.mark.parametrize(
    "series,state,m",
    [
        (F1, "up_rising", 1.0),
        (F2, "up_falling", 0.75),
        (F3, "down_rising", 0.5),
        (F4, "down_falling", 0.0),
    ],
    ids=["R01_F1", "R02_F2", "R03_F3", "R04_F4"],
)
def test_r01_r04_classify_when_each_state_then_multiplier(series, state, m):
    got_state, got_m = _state_m(series)
    assert (got_state, got_m) == (state, m)


def test_r01_r04_classification_exposes_above_and_rising():
    c, _ = _cls(F2)
    assert (bool(c.above), bool(c.rising)) == (True, False)
    c, _ = _cls(F3)
    assert (bool(c.above), bool(c.rising)) == (False, True)


# ===========================================================================
# R05~R07 — 동률은 약한 쪽 (엄격 부등호)
# ===========================================================================
def test_r05_close_equals_sma60_then_not_above():
    c, _ = _cls(T2)
    assert bool(c.above) is False, "종가 == SMA60 인데 above=True — `>` 가 `>=` 로 바뀌었다(M01)"
    assert _state_m(T2) == ("down_rising", 0.5)


def test_r06_sma60_equals_20_bars_ago_then_not_rising():
    c, _ = _cls(T3)
    assert bool(c.rising) is False, "SMA60 == 20봉 전 SMA60 인데 rising=True — M02"
    assert _state_m(T3) == ("up_falling", 0.75)


def test_r07_double_tie_then_zero():
    assert _state_m(TF) == ("down_falling", 0.0)


def test_r05_r07_ties_hold_for_float_and_decimal_inputs():
    """종가가 float·Decimal 로 와도 같은 판정 — 합 비교는 입력 자료형에 흔들리지 않는다."""
    from decimal import Decimal

    for conv in (float, Decimal):
        assert _state_m([conv(x) for x in T2]) == ("down_rising", 0.5)
        assert _state_m([conv(x) for x in T3]) == ("up_falling", 0.75)
        assert _state_m([conv(x) for x in F2]) == ("up_falling", 0.75)


# ===========================================================================
# R08 · R09 · R10 — 창 정렬 (lookback 20 · MA 60 · 마지막 80개만)
# ===========================================================================
def test_r08_slope_window_alignment_d1_d3():
    assert _state_m(D1) == ("up_rising", 1.0), "D1 — 기울기 창이 한 칸 과거로 밀렸거나 lookback 21(M03)"
    assert _state_m(D3) == ("down_rising", 0.5), "D3 — lookback 19(M04)"


def test_r09_ma_window_is_sixty_d2_d4():
    assert _state_m(D2) == ("up_falling", 0.75), "D2 — MA 창 61(M05)"
    assert _state_m(D4) == ("down_rising", 0.5), "D4 — MA 창 59(M05)"


def test_r10_only_last_80_closes_are_read():
    assert len(D1) == 81 and D1[0] == 50000
    assert _state_m(D1) == _state_m(D1[1:]) == ("up_rising", 1.0)
    # 앞에 얼마를 붙여도 같다
    assert _state_m([1, 999_999, 3] + F3) == ("down_rising", 0.5)


# ===========================================================================
# R11 · R12 — 행 수 · 종가 품질
# ===========================================================================
def test_r11_rows_short_boundary():
    c, reason = _cls(F1[1:])                      # 79개
    assert (c, reason) == (None, "rows_short")
    c, reason = _cls(F1)                          # 80개 = 경계
    assert reason == "ok" and c is not None


@pytest.mark.parametrize(
    "bad", [0, -5, None, float("nan"), float("inf"), "abc"],
    ids=["zero", "negative", "none", "nan", "inf", "string"],
)
@pytest.mark.parametrize("pos", [-1, -80], ids=["head", "window_start"])
def test_r12_bad_close_inside_window_then_bad_close(bad, pos):
    closes = list(F1)
    closes[pos] = bad
    c, reason = _cls(closes)
    assert (c, reason) == (None, "bad_close")


def test_r12_bad_close_outside_window_is_ignored():
    closes = [None] + list(F1)                    # 81번째(창 밖)가 None
    assert _state_m(closes) == ("up_rising", 1.0)


# ===========================================================================
# R13 — 모드 정규화 (부재 = off, 오타 = off + invalid)
# ===========================================================================
@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, ("off", True)),
        ("off", ("off", True)),
        ("shadow", ("shadow", True)),
        (" Shadow ", ("shadow", True)),
        ("ENFORCE", ("enforce", True)),
        ("on", ("off", False)),
        ("", ("off", False)),
        (1, ("off", False)),
        (True, ("off", False)),
        (0.5, ("off", False)),
    ],
)
def test_r13_normalize_mode(raw, expected):
    assert tuple(mu().normalize_mode(raw)) == expected


# ===========================================================================
# R14 · R15 · R16 — 로더(compute_snapshot): 봉 선택 · 미리보기 · 신선도 · 예외
# ===========================================================================
async def _snap(monkeypatch, seams: Seams, as_of: date, *, preview: bool):
    seams.install(monkeypatch)
    return await mu().compute_snapshot(as_of, preview=preview)


@freeze_time("2026-09-28T07:50:00+09:00")
async def test_r14_live_as_of_excludes_today_bar(monkeypatch):
    """as_of=09-28 — `bas_dd == 09-28` 극단값 봉은 창에 들어오면 상태를 뒤집는다(F1+1000 → 0.5). 빠져야 1.0."""
    today_bar = {"ticker": "069500", "bas_dd": DAY, "close_price": 1000}
    seams = Seams(rows_for(F1, HEAD, extra_desc=[today_bar]), prev_day=HEAD)
    snap = await _snap(monkeypatch, seams, DAY, preview=False)
    assert snap.ok is True and snap.reason == "ok"
    assert (snap.state, snap.m) == ("up_rising", 1.0), "오늘 봉이 창에 들어왔다(`<` → `<=`, M08)"
    assert snap.bar_date == HEAD
    assert snap.expected_head == HEAD
    assert snap.preview is False and snap.as_of == DAY
    assert snap.rows >= 80


@freeze_time("2026-09-28T07:50:00+09:00")
async def test_r14_seam_arguments_and_bas_dd_type_tolerance(monkeypatch):
    rows = rows_for(F2, HEAD)
    mixed = []
    for i, r in enumerate(rows):
        r = dict(r)
        if i % 3 == 1:
            r["bas_dd"] = r["bas_dd"].isoformat()                         # ISO 문자열
        elif i % 3 == 2:
            r["bas_dd"] = datetime(r["bas_dd"].year, r["bas_dd"].month, r["bas_dd"].day, 15, 30)
        mixed.append(r)
    mixed.insert(5, {"ticker": "069500", "bas_dd": "garbage", "close_price": 1})   # 파싱 불가 → 버린다
    seams = Seams(mixed, prev_day=HEAD)
    snap = await _snap(monkeypatch, seams, DAY, preview=False)
    assert (snap.ok, snap.state, snap.m) == (True, "up_falling", 0.75)
    assert snap.bar_date == HEAD
    assert seams.daily_calls, "get_recent_daily seam 을 부르지 않았다(모듈 속성 조회 seam)"
    ticker, days = seams.daily_calls[0]
    assert ticker == "069500" and days >= 80
    assert seams.cal_calls == [DAY], "previous_trading_day(as_of) 로 기대 머리를 구해야 한다"


@freeze_time("2026-09-28T21:05:00+09:00")
async def test_r15_preview_as_of_reads_as_of_minus_one_bar(monkeypatch):
    seams = Seams(rows_for(F3, DAY), prev_day=DAY)          # 머리 = 09-28(오늘 봉 = as_of−1)
    snap = await _snap(monkeypatch, seams, NEXT, preview=True)
    assert snap.ok is True
    assert snap.preview is True and snap.as_of == NEXT
    assert snap.bar_date == DAY, "미리보기에서 머리 봉을 버렸다(M09)"
    assert snap.expected_head == DAY
    assert (snap.state, snap.m) == ("down_rising", 0.5)
    assert seams.cal_calls == [NEXT]


@freeze_time("2026-09-28T07:50:00+09:00")
async def test_r16_stale_head_then_unavailable_m1(monkeypatch):
    seams = Seams(rows_for(F4, date(2026, 9, 22)), prev_day=HEAD)   # 머리 09-22 < 기대 09-23
    snap = await _snap(monkeypatch, seams, DAY, preview=False)
    assert (snap.ok, snap.state, snap.m, snap.reason) == (False, "unavailable", 1.0, "stale_head"), (
        "머리가 기대보다 오래됐는데 판정했다(M10) — 또는 실패를 m=0 으로 닫았다(M07)"
    )


@freeze_time("2026-09-28T07:50:00+09:00")
async def test_r16_head_newer_than_calendar_is_fresh(monkeypatch):
    seams = Seams(rows_for(F2, HEAD), prev_day=date(2026, 9, 22))    # 달력 불일치여도 데이터가 더 새롭다
    snap = await _snap(monkeypatch, seams, DAY, preview=False)
    assert (snap.ok, snap.state) == (True, "up_falling")


@freeze_time("2026-09-28T07:50:00+09:00")
@pytest.mark.parametrize(
    "head,ok",
    [(HEAD, True), (date(2026, 9, 17), False)],
    ids=["5_calendar_days_ok", "11_calendar_days_stale"],
)
async def test_r16_calendar_unknown_falls_back_to_ten_calendar_days(monkeypatch, head, ok):
    seams = Seams(rows_for(F2, head), prev_day=None)
    snap = await _snap(monkeypatch, seams, DAY, preview=False)
    assert snap.ok is ok
    if ok:
        assert (snap.state, snap.m) == ("up_falling", 0.75)
    else:
        assert (snap.reason, snap.m) == ("stale_head", 1.0)


@freeze_time("2026-09-28T07:50:00+09:00")
async def test_r16_rows_short_then_m1(monkeypatch):
    seams = Seams(rows_for(F4[1:], HEAD), prev_day=HEAD)          # 79행
    snap = await _snap(monkeypatch, seams, DAY, preview=False)
    assert (snap.ok, snap.reason, snap.m, snap.state) == (False, "rows_short", 1.0, "unavailable")


@freeze_time("2026-09-28T07:50:00+09:00")
async def test_r16_empty_db_result_is_rows_short(monkeypatch):
    """`get_recent_daily` 는 DB 오류 때 `[]` 를 돌려준다 — 조회 실패도 rows_short 로 온다."""
    seams = Seams([], prev_day=HEAD)
    snap = await _snap(monkeypatch, seams, DAY, preview=False)
    assert (snap.ok, snap.reason, snap.m) == (False, "rows_short", 1.0)


@freeze_time("2026-09-28T07:50:00+09:00")
async def test_r16_bad_close_through_loader_then_m1(monkeypatch):
    rows = rows_for(F4, HEAD)
    rows[0] = dict(rows[0], close_price=None)
    seams = Seams(rows, prev_day=HEAD)
    snap = await _snap(monkeypatch, seams, DAY, preview=False)
    assert (snap.ok, snap.reason, snap.m) == (False, "bad_close", 1.0)


@freeze_time("2026-09-28T07:50:00+09:00")
@pytest.mark.parametrize("where", ["daily", "calendar"])
async def test_r16_seam_exception_never_escapes(monkeypatch, where):
    seams = Seams(rows_for(F4, HEAD), prev_day=HEAD)
    if where == "daily":
        seams.daily_exc = RuntimeError("db down")
    else:
        seams.cal_exc = RuntimeError("calendar down")
    snap = await _snap(monkeypatch, seams, DAY, preview=False)   # 예외가 밖으로 나오면 여기서 실패
    assert (snap.ok, snap.reason, snap.m, snap.state) == (False, "exception", 1.0, "unavailable")


@freeze_time("2026-09-28T07:50:00+09:00")
async def test_r16_refresh_emits_unavailable_warning_with_reason(monkeypatch, caplog):
    """WARNING 은 전략 쪽 refresh 가 낸다(`strategy=` 필드) — 로거 `src.engine.market_unit`."""
    need_base()
    open_info(caplog)
    Seams(rows_for(F4, date(2026, 9, 22)), prev_day=HEAD).install(monkeypatch)
    s = make("donchian_swing", mode="shadow")
    await s._refresh_market_unit(as_of_date=DAY, preview=False)
    warns = lines(caplog, "[market_unit_unavailable]", min_level=logging.WARNING)
    assert len(warns) == 1, warns
    assert field(warns[0], "strategy") == "donchian_swing"
    assert field(warns[0], "reason") == "stale_head"
    assert field(warns[0], "where") == "refresh"
    assert "m=1.00" in warns[0]
    view = s._market_unit_view()
    assert (view.mode, float(view.m)) == ("shadow", 1.0)

