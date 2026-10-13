"""RS 1단계 Red — `src/db/invest_opinion.py` CRUD (invest_opinion_history · estimate_perform_snapshot).

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase1.md` §D.
패턴 = `test_cycle443_overseas_index.py` 답습(`patch.object(module, "pg", create=True)`).

명세 해석 가정(구현이 따를 계약):
- `upsert_opinions(ticker, rows) -> int` — rows = C 래퍼의 정규화 dict 목록.
  `pg.executemany` 1회, SQL 에 `ON CONFLICT (ticker, bsop_date, mbcr_name) DO UPDATE`.
  바인딩 순서 앞 3칸 = ticker · bsop_date(date) · mbcr_name. `raw` 는 dict 그대로 바인딩(JSONB codec).
  빈 rows → 0 · DB 호출 없음. DB 예외 → 0(graceful, 올리지 않는다). 성공 → 보낸 행 수.
- `upsert_estimate_snapshot(ticker, snapshot_month: date, data: dict) -> bool` —
  data = `inquire_estimate_perform` 반환. `pg.execute` 1회, `ON CONFLICT (ticker, snapshot_month) DO UPDATE`.
  바인딩 앞 2칸 = ticker · snapshot_month(그 달 1일 date). raw dict 가 인자에 들어간다.
  DB 예외 → False.
- `get_opinions(ticker, date_from, date_to) -> list[dict]` — `pg.fetch` 결과를 dict 목록으로.
  DB 예외 → [].
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from src.db import invest_opinion as dbio

pytestmark = pytest.mark.unit


def _row(d: date, broker: str, goal):
    return {
        "bsop_date": d, "mbcr_name": broker, "invt_opnn": "매수", "rgbf_invt_opnn": "매수",
        "hts_goal_prc": goal, "stck_prdy_clpr": 75900, "dprt": -26.1,
        "raw": {"stck_bsop_date": d.strftime("%Y%m%d"), "mbcr_name": broker},
    }


async def test_upsert_opinions_empty_is_noop():
    with patch.object(dbio, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        n = await dbio.upsert_opinions("005930", [])
    assert n == 0
    pg_mod.executemany.assert_not_called()


async def test_upsert_opinions_binds_pk_first_and_conflict_target():
    rows = [_row(date(2024, 5, 27), "SK", 105000), _row(date(2024, 5, 20), "하이투자", None)]
    with patch.object(dbio, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        n = await dbio.upsert_opinions("005930", rows)
    assert n == 2
    sql, args_list = pg_mod.executemany.await_args.args
    assert "INSERT INTO invest_opinion_history" in sql
    assert "ON CONFLICT (ticker, bsop_date, mbcr_name) DO UPDATE" in sql
    assert list(args_list[0][:3]) == ["005930", date(2024, 5, 27), "SK"]
    assert rows[0]["raw"] in list(args_list[0])  # raw dict 그대로(JSONB codec)
    assert None in list(args_list[1])            # 결측 목표가는 NULL 로


async def test_upsert_opinions_db_exception_is_graceful():
    with patch.object(dbio, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock(side_effect=RuntimeError("pg down"))
        n = await dbio.upsert_opinions("005930", [_row(date(2024, 5, 27), "SK", 1)])
    assert n == 0


async def test_upsert_estimate_snapshot_conflict_target_and_binding():
    data = {"ticker": "005930", "raw": {"rt_cd": "0", "output1": {"sht_cd": "A005930"}},
            "settle_months": ["202512"]}
    with patch.object(dbio, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        ok = await dbio.upsert_estimate_snapshot("005930", date(2026, 10, 1), data)
    assert ok is True
    sql, *args = pg_mod.execute.await_args.args
    assert "INSERT INTO estimate_perform_snapshot" in sql
    assert "ON CONFLICT (ticker, snapshot_month) DO UPDATE" in sql
    assert args[0] == "005930"
    assert args[1] == date(2026, 10, 1)
    assert data["raw"] in args


async def test_upsert_estimate_snapshot_db_exception_returns_false():
    with patch.object(dbio, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(side_effect=RuntimeError("pg down"))
        ok = await dbio.upsert_estimate_snapshot(
            "005930", date(2026, 10, 1), {"ticker": "005930", "raw": {}, "settle_months": []})
    assert ok is False


async def test_get_opinions_returns_dicts_and_binds_range():
    rec = {"ticker": "005930", "bsop_date": date(2024, 5, 27), "mbcr_name": "SK",
           "hts_goal_prc": 105000}
    with patch.object(dbio, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[rec])
        out = await dbio.get_opinions("005930", date(2024, 1, 1), date(2024, 5, 28))
    assert out == [rec]
    _, *args = pg_mod.fetch.await_args.args
    assert args == ["005930", date(2024, 1, 1), date(2024, 5, 28)]


async def test_get_opinions_db_exception_returns_empty():
    with patch.object(dbio, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=RuntimeError("pg down"))
        out = await dbio.get_opinions("005930", date(2024, 1, 1), date(2024, 5, 28))
    assert out == []
