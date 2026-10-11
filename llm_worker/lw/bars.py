"""cycle446 — 확정 일봉 판정(설계 §2.3). 순수 함수. `src`·I/O·`await` 0."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta


def determine_bar_date(proxy_rows, *, today: date) -> "date | None":
    """`069500` 봉 중 `bas_dd < today` 의 최댓값(KODEX 200 직전 영업일 — 휴장일 달력 대신)."""
    best = None
    for row in proxy_rows or []:
        try:
            d = row.get("bas_dd")
            if not isinstance(d, date):
                continue
            if d < today and (best is None or d > best):
                best = d
        except Exception:
            continue
    return best


def is_row_confirmed(*, bas_dd: date, updated_at, head_bas_dd: date, now: datetime) -> bool:
    """헤드 봉 = `updated_at >= 오늘 06:00 KST`. 그 전 봉 = `updated_at >= (bas_dd+1일) 06:00 KST`
    (`daily_bar_finalize` 와 같은 규칙, 설계 §2.3)."""
    try:
        if not isinstance(bas_dd, date) or not isinstance(updated_at, datetime):
            return False
        tzinfo = updated_at.tzinfo or now.tzinfo
        if bas_dd == head_bas_dd:
            boundary = datetime.combine(now.date(), time(6, 0), tzinfo=now.tzinfo)
        else:
            boundary = datetime.combine(bas_dd + timedelta(days=1), time(6, 0), tzinfo=tzinfo)
        return updated_at >= boundary
    except Exception:
        return False
