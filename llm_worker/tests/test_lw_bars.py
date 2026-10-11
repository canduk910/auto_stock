"""cycle446 — 확정 일봉 판정(`lw/bars.py`, 설계 §2.3)."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from lw import bars
from lw_testkit import kst

pytestmark = pytest.mark.unit


def test_determine_bar_date_picks_max_before_today():
    rows = [{"bas_dd": date(2026, 10, 12)}, {"bas_dd": date(2026, 10, 13)},
           {"bas_dd": date(2026, 10, 14)}]  # 오늘(10-14) 포함되면 제외돼야 한다
    got = bars.determine_bar_date(rows, today=date(2026, 10, 14))
    assert got == date(2026, 10, 13)


def test_determine_bar_date_no_rows_before_today_is_none():
    rows = [{"bas_dd": date(2026, 10, 14)}]
    assert bars.determine_bar_date(rows, today=date(2026, 10, 14)) is None


def test_determine_bar_date_ignores_malformed_rows():
    rows = [{"bas_dd": "not-a-date"}, {}, None, {"bas_dd": date(2026, 10, 12)}]
    assert bars.determine_bar_date(rows, today=date(2026, 10, 14)) == date(2026, 10, 12)


def test_is_row_confirmed_head_row_before_0600_today_is_provisional():
    now = kst(2026, 10, 14, 7, 45)
    confirmed = bars.is_row_confirmed(
        bas_dd=date(2026, 10, 13), updated_at=kst(2026, 10, 13, 20, 30),
        head_bas_dd=date(2026, 10, 13), now=now,
    )
    assert confirmed is False


def test_is_row_confirmed_head_row_after_0600_today_is_confirmed():
    now = kst(2026, 10, 14, 7, 45)
    confirmed = bars.is_row_confirmed(
        bas_dd=date(2026, 10, 13), updated_at=kst(2026, 10, 14, 7, 0),
        head_bas_dd=date(2026, 10, 13), now=now,
    )
    assert confirmed is True


def test_is_row_confirmed_older_row_uses_bas_dd_plus_one_day_boundary():
    now = kst(2026, 10, 14, 7, 45)
    # bas_dd=10-12 의 경계는 10-13 06:00 — 그 전 updated_at 은 미확정
    not_yet = bars.is_row_confirmed(
        bas_dd=date(2026, 10, 12), updated_at=kst(2026, 10, 13, 5, 59),
        head_bas_dd=date(2026, 10, 13), now=now,
    )
    assert not_yet is False
    ok = bars.is_row_confirmed(
        bas_dd=date(2026, 10, 12), updated_at=kst(2026, 10, 13, 6, 1),
        head_bas_dd=date(2026, 10, 13), now=now,
    )
    assert ok is True


def test_is_row_confirmed_bad_input_never_raises():
    assert bars.is_row_confirmed(bas_dd="x", updated_at="y", head_bas_dd=None, now=kst(2026, 10, 14)) is False
    assert bars.is_row_confirmed(bas_dd=date(2026, 10, 13), updated_at=None,
                                head_bas_dd=date(2026, 10, 13), now=kst(2026, 10, 14)) is False
