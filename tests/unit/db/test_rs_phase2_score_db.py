"""RS 2단계 Red — 관찰 기록용 DB 함수 (pg monkeypatch 단위).

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase2.md` §A·§B.
패턴 = `test_invest_opinion_db.py` 답습(`patch.object(module, "pg", create=True)`).

명세 해석 가정(구현이 따를 계약):
- `src/db/score_inputs.py`
  - `recent_closes_bulk(before, n=200) -> dict[str, list[float]]` — `stock_master_daily` 에서 `bas_dd < before`
    최근 n봉 종가, **창 함수 1쿼리**(`row_number() OVER (PARTITION BY ticker ORDER BY bas_dd DESC)`).
    값 = 오래된→최신 float 목록. `before` 는 `_kst.to_date` 로 DATE 바인딩.
  - `master_raw_map(tickers) -> dict[str, dict]` — `stock_master.master_raw` 일괄 1쿼리(`ANY($1::text[])`).
  - `financial_rows_bulk(tickers) -> dict[str, list[dict]]` — `stock_master_financial` 분기·연간 행 일괄 1쿼리.
  - 빈 종목 목록 = 쿼리 없이 `{}`.
- `src/db/candidate_scores.py::upsert_scores(rows) -> int` — `pg.executemany` 1회,
  `ON CONFLICT (target_date, strategy_id, ticker) DO UPDATE`. 반환 = 보낸 행 수. 빈 목록 = 0·호출 없음.
  NULL 은 NULL 로 보낸다(0 으로 채우지 않는다). `target_date` = DATE, `computed_at` = aware datetime.
- `src/db/invest_opinion.py` 추가 2함수(추가 적재용, 일괄 1쿼리):
  `latest_bsop_dates(tickers) -> dict[str, date]` · `estimate_snapshot_tickers(snapshot_month) -> set[str]`.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

COLUMNS = (
    "target_date", "strategy_id", "ticker", "role",
    "rs_raw", "rs_pct", "sector_key", "vs_sector", "sector_pct", "in_sector_pct",
    "revision_breadth", "target_median_change", "opinion_brokers",
    "fin_quarter", "op_income_q", "op_income_q_yoy", "op_turnaround", "op_yoy_growth",
    "revenue_yoy_growth", "net_turnaround", "roe", "debt_ratio_latest", "debt_ratio_down_years",
    "ttm_op_to_max_ratio", "rs_population", "computed_at",
)


def _si():
    from src.db import score_inputs  # noqa: PLC0415
    return score_inputs


def _cs():
    from src.db import candidate_scores  # noqa: PLC0415
    return candidate_scores


# ---------------------------------------------------------------------------
# score_inputs.recent_closes_bulk
# ---------------------------------------------------------------------------
async def test_recent_closes_bulk_single_window_query_and_ascending_output():
    si = _si()
    d = date(2026, 10, 13)
    rows = [
        {"ticker": "005930", "bas_dd": d - timedelta(days=1), "close_price": 103},
        {"ticker": "000660", "bas_dd": d - timedelta(days=2), "close_price": 50},
        {"ticker": "005930", "bas_dd": d - timedelta(days=3), "close_price": 101},
        {"ticker": "005930", "bas_dd": d - timedelta(days=2), "close_price": 102},
        {"ticker": "000660", "bas_dd": d - timedelta(days=1), "close_price": 51},
    ]
    with patch.object(si, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await si.recent_closes_bulk(d, n=200)
    assert pg_mod.fetch.await_count == 1, "종목 수와 무관하게 1쿼리"
    sql = pg_mod.fetch.await_args.args[0]
    args = list(pg_mod.fetch.await_args.args[1:])
    assert re.search(r"row_number\s*\(\s*\)\s*over", sql, re.I), "창 함수 1쿼리"
    assert re.search(r"partition\s+by\s+ticker", sql, re.I)
    assert "stock_master_daily" in sql
    assert re.search(r"bas_dd\s*<\s*\$\d", sql), "오늘 봉 제외 = bas_dd < before"
    assert d in args and 200 in args
    assert out == {"005930": [101.0, 102.0, 103.0], "000660": [50.0, 51.0]}
    assert all(isinstance(v, float) for vs in out.values() for v in vs)


async def test_recent_closes_bulk_lower_bound_320_days():
    si = _si()
    d = date(2026, 10, 13)
    with patch.object(si, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await si.recent_closes_bulk(d, n=200)
    sql = pg_mod.fetch.await_args.args[0]
    args = list(pg_mod.fetch.await_args.args[1:])
    assert re.search(r"bas_dd\s*>=\s*\$\d", sql), "스캔 축소 = bas_dd 하한"
    assert d - timedelta(days=320) in args


async def test_recent_closes_bulk_binds_date_even_for_str():
    si = _si()
    with patch.object(si, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await si.recent_closes_bulk("2026-10-13", n=50)
    assert out == {}
    args = list(pg_mod.fetch.await_args.args[1:])
    assert date(2026, 10, 13) in args and 50 in args
    assert "2026-10-13" not in args, "DATE 는 date 로 바인딩"


async def test_recent_closes_bulk_default_n_is_200():
    si = _si()
    with patch.object(si, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await si.recent_closes_bulk(date(2026, 10, 13))
    assert 200 in list(pg_mod.fetch.await_args.args[1:])


# ---------------------------------------------------------------------------
# score_inputs.master_raw_map / financial_rows_bulk
# ---------------------------------------------------------------------------
async def test_master_raw_map_one_query_any_array():
    si = _si()
    with patch.object(si, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[
            {"ticker": "005930", "master_raw": {"krx_smcn_yn": "Y", "roe": "12.5"}},
            {"ticker": "000660", "master_raw": {}},
        ])
        out = await si.master_raw_map(["005930", "000660", "999990"])
    assert pg_mod.fetch.await_count == 1
    sql = pg_mod.fetch.await_args.args[0]
    assert re.search(r"ANY\s*\(\s*\$1::text\[\]\s*\)", sql)
    assert "master_raw" in sql and "stock_master" in sql
    assert out["005930"] == {"krx_smcn_yn": "Y", "roe": "12.5"}
    assert "999990" not in out


async def test_master_raw_map_empty_no_query():
    si = _si()
    with patch.object(si, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock()
        assert await si.master_raw_map([]) == {}
    pg_mod.fetch.assert_not_called()


async def test_financial_rows_bulk_groups_by_ticker_both_div_cls():
    si = _si()
    with patch.object(si, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[
            {"ticker": "005930", "stac_yymm": "202506", "div_cls": "1", "bsop_prti": 30},
            {"ticker": "005930", "stac_yymm": "202412", "div_cls": "0", "lblt_rate": 70},
            {"ticker": "000660", "stac_yymm": "202506", "div_cls": "1", "bsop_prti": 5},
        ])
        out = await si.financial_rows_bulk(["005930", "000660"])
    assert pg_mod.fetch.await_count == 1
    sql = pg_mod.fetch.await_args.args[0]
    assert "stock_master_financial" in sql
    assert re.search(r"ANY\s*\(\s*\$1::text\[\]\s*\)", sql)
    assert sorted(r["div_cls"] for r in out["005930"]) == ["0", "1"]
    assert len(out["000660"]) == 1


async def test_financial_rows_bulk_empty_no_query():
    si = _si()
    with patch.object(si, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock()
        assert await si.financial_rows_bulk([]) == {}
    pg_mod.fetch.assert_not_called()


# ---------------------------------------------------------------------------
# candidate_scores.upsert_scores
# ---------------------------------------------------------------------------
def _score_row(**over):
    row = {c: None for c in COLUMNS}
    row.update({
        "target_date": date(2026, 10, 13), "strategy_id": "donchian_swing", "ticker": "005930",
        "role": "candidate", "rs_raw": 0.42, "rs_pct": 88, "rs_population": 1500,
        "computed_at": datetime(2026, 10, 13, 8, 5, tzinfo=KST),
    })
    row.update(over)
    return row


def _insert_columns(sql: str) -> list[str]:
    m = re.search(r"INSERT\s+INTO\s+candidate_score_snapshots\s*\(([^)]*)\)", sql, re.I | re.S)
    assert m, f"INSERT INTO candidate_score_snapshots (...) 가 없다: {sql}"
    return [c.strip() for c in m.group(1).split(",")]


async def test_upsert_scores_executemany_once_with_conflict_overwrite():
    cs = _cs()
    rows = [_score_row(), _score_row(ticker="000660", role="held", rs_raw=None, rs_pct=None)]
    with patch.object(cs, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        n = await cs.upsert_scores(rows)
    assert n == 2
    assert pg_mod.executemany.await_count == 1
    sql, args_list = pg_mod.executemany.await_args.args
    assert re.search(r"ON\s+CONFLICT\s*\(\s*target_date\s*,\s*strategy_id\s*,\s*ticker\s*\)\s*DO\s+UPDATE", sql, re.I)
    cols = _insert_columns(sql)
    assert set(cols) == set(COLUMNS), f"칸 불일치: {set(cols) ^ set(COLUMNS)}"
    for row, args in zip(rows, args_list):
        bound = dict(zip(cols, args))
        for c in COLUMNS:
            assert bound[c] == row[c], f"{c}: {bound[c]!r} != {row[c]!r}"
    second = dict(zip(cols, args_list[1]))
    assert second["rs_raw"] is None and second["rs_pct"] is None, "결측은 NULL (0 금지)"


async def test_upsert_scores_update_set_covers_all_non_pk_columns():
    cs = _cs()
    with patch.object(cs, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        await cs.upsert_scores([_score_row()])
    sql = pg_mod.executemany.await_args.args[0]
    tail = re.split(r"DO\s+UPDATE\s+SET", sql, flags=re.I)[1]
    for c in COLUMNS:
        if c in ("target_date", "strategy_id", "ticker"):
            continue
        assert re.search(rf"\b{c}\s*=\s*EXCLUDED\.{c}\b", tail), f"덮기 SET 에 {c} 누락"


async def test_upsert_scores_binds_date_type():
    cs = _cs()
    with patch.object(cs, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        await cs.upsert_scores([_score_row(target_date="2026-10-13")])
    sql, args_list = pg_mod.executemany.await_args.args
    bound = dict(zip(_insert_columns(sql), args_list[0]))
    assert bound["target_date"] == date(2026, 10, 13) and not isinstance(bound["target_date"], str)
    assert isinstance(bound["computed_at"], datetime) and bound["computed_at"].tzinfo is not None


async def test_upsert_scores_empty_noop():
    cs = _cs()
    with patch.object(cs, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        assert await cs.upsert_scores([]) == 0
    pg_mod.executemany.assert_not_called()


# ---------------------------------------------------------------------------
# invest_opinion 추가 2함수 (추가 적재용)
# ---------------------------------------------------------------------------
async def test_latest_bsop_dates_one_query():
    from src.db import invest_opinion as dbio

    with patch.object(dbio, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"ticker": "005930", "latest": date(2026, 10, 1)}])
        out = await dbio.latest_bsop_dates(["005930", "000660"])
    assert pg_mod.fetch.await_count == 1
    sql = pg_mod.fetch.await_args.args[0]
    assert "invest_opinion_history" in sql and re.search(r"max\s*\(\s*bsop_date\s*\)", sql, re.I)
    assert re.search(r"ANY\s*\(\s*\$1::text\[\]\s*\)", sql)
    assert out == {"005930": date(2026, 10, 1)}


async def test_latest_bsop_dates_empty_no_query():
    from src.db import invest_opinion as dbio

    with patch.object(dbio, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock()
        assert await dbio.latest_bsop_dates([]) == {}
    pg_mod.fetch.assert_not_called()


async def test_estimate_snapshot_tickers_for_month():
    from src.db import invest_opinion as dbio

    with patch.object(dbio, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[{"ticker": "005930"}, {"ticker": "000660"}])
        out = await dbio.estimate_snapshot_tickers(date(2026, 10, 1))
    sql = pg_mod.fetch.await_args.args[0]
    assert "estimate_perform_snapshot" in sql and "snapshot_month" in sql
    assert date(2026, 10, 1) in list(pg_mod.fetch.await_args.args[1:])
    assert out == {"005930", "000660"}
