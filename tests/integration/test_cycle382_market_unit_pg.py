"""cycle382 Red (선택 P01) — 실 Postgres: `069500` 일봉 90행 → `market_unit.compute_snapshot` 손계산 일치.

명세 = `_workspace/red/cycle382_market_unit_spec.md` §1 · §2 · §11.2(P01)

잰 것:
- 실 `stock_master_daily.get_recent_daily`(DESC · asyncpg `date` · INTEGER 종가)를 그대로 읽어
  마지막 80봉(`bas_dd < as_of`)으로 판정한다 — mock 이 못 잡는 `bas_dd` 자료형 처리.
- as_of 당일 행(`bas_dd == as_of`)은 창에 들어오지 않는다(라이브 부팅 = D−1 판정).

🔴 벽시계 의존 금지 — as_of 를 명시한다. 달력은 conftest 가 「모름(None)」 으로 중립화하므로
신선도는 10 달력일 폴백 규칙을 탄다(머리 09-23 · as_of 09-28 = 5일 → 신선).
docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

_AS_OF = date(2026, 9, 28)
_HEAD = date(2026, 9, 23)
_HOLIDAYS = {date(2026, 9, 24), date(2026, 9, 25)}


def _weekdays_desc(head: date, n: int) -> list[date]:
    out, d = [], head
    while len(out) < n:
        if d.weekday() < 5 and d not in _HOLIDAYS:
            out.append(d)
        d -= timedelta(days=1)
    return out


async def test_c382_pg_compute_snapshot_matches_hand_calculation(clean_stock_master_daily):
    try:
        from src.engine import market_unit
    except ImportError as exc:  # pragma: no cover — Red 단계
        pytest.fail(f"[Red] src/engine/market_unit.py 미존재 — {exc}")
    pg = clean_stock_master_daily
    # 오름차순 90개: 앞 10개는 창 밖(판정에 영향 없어야 한다) + F2(위·하락 ¾)
    f2 = [12000 - 10 * i for i in range(79)] + [12500]
    closes_asc = [99_999] * 10 + f2
    dates_desc = _weekdays_desc(_HEAD, len(closes_asc))
    for d, c in zip(dates_desc, reversed(closes_asc)):
        await pg.execute(
            "INSERT INTO stock_master_daily (ticker, bas_dd, close_price) VALUES ($1, $2, $3)",
            "069500", d, c,
        )
    # as_of 당일 극단값 행 — 창에 들어오면 판정이 뒤집힌다
    await pg.execute(
        "INSERT INTO stock_master_daily (ticker, bas_dd, close_price) VALUES ($1, $2, $3)",
        "069500", _AS_OF, 1,
    )

    snap = await market_unit.compute_snapshot(_AS_OF, preview=False)

    assert snap.ok is True, snap
    assert (snap.state, float(snap.m)) == ("up_falling", 0.75)
    assert snap.bar_date == _HEAD and isinstance(snap.bar_date, date)
    assert abs(float(snap.sma60) - 11_526.5) < 0.006
    assert abs(float(snap.sma60_prev) - 11_705.0) < 0.006
    assert float(snap.close) == 12_500
