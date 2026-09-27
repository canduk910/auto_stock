"""cycle380 Red — `list_by_filter(exclude_etf_like=...)` SQL 모양 (docker 없이 도는 짝).

명세 = `_workspace/red/cycle380_etf_group_code.md` §4. 행위 증명(LIMIT 전 제외 · 헬퍼와 행 단위
일치)은 실 PG 통합 `tests/integration/test_cycle380_list_by_filter_etf_pg.py` 가 맡는다.
이 파일은 docker 가 없는 환경에서도 도는 최소 짝이다.

계약:
- 시그너처: keyword-only `exclude_etf_like`, 기본 False.
- True: 발행되는 **모든** SQL(단일 쿼리, stage 3쿼리)의 WHERE 에 `scty_grp_id_cd` 판정이
  `ORDER BY`/`LIMIT` **앞**에 있다.
- False(기본): SQL 에 `scty_grp_id_cd` 가 나오지 않는다 — 기존 호출자 SQL 무변경.

## HEAD 기준

RED — 인자 부재(TypeError) · 시그너처 부재.
"""
from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _capture(**kwargs) -> list[str]:
    import src.db.stock_master as sm

    with patch.object(sm, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        asyncio.run(sm.list_by_filter(**kwargs))
        return [c.args[0] for c in pg_mod.fetch.await_args_list]


def test_signature_keyword_only_default_false():
    from src.db.stock_master import list_by_filter

    param = inspect.signature(list_by_filter).parameters.get("exclude_etf_like")
    assert param is not None, "list_by_filter 에 exclude_etf_like 인자가 없다"
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is False


@pytest.mark.parametrize("stage", [False, True])
def test_exclusion_in_where_before_order_and_limit(stage):
    sqls = _capture(
        min_market_cap=50_000_000_000, min_trade_amount=1_000_000_000,
        limit=100, return_stage_counts=stage, exclude_etf_like=True,
    )
    assert len(sqls) == (3 if stage else 1)
    for sql in sqls:
        pos = sql.find("scty_grp_id_cd")
        assert pos != -1, f"ETF 판정이 SQL 에 없다: {sql}"
        assert " WHERE " in sql[:pos], "판정은 WHERE 절 안에 있어야 한다"
        assert pos < sql.find("ORDER BY") < sql.find("LIMIT"), "판정이 ORDER BY/LIMIT 뒤에 있다"


@pytest.mark.parametrize("stage", [False, True])
def test_default_sql_does_not_mention_group_code(stage):
    sqls = _capture(
        min_market_cap=50_000_000_000, min_trade_amount=1_000_000_000,
        limit=100, return_stage_counts=stage,
    )
    for sql in sqls:
        assert "scty_grp_id_cd" not in sql, "기본 경로 SQL 이 바뀌었다(전략 밖 호출자 영향)"


def test_exclusion_composes_with_index_and_exclude_filters():
    """donchian 모양(지수 OR + exclude_tickers)과 같이 써도 판정이 붙는다."""
    sqls = _capture(
        is_kospi200=True, is_kosdaq150=True, exclude_tickers=["005930"],
        limit=400, exclude_etf_like=True,
    )
    (sql,) = sqls
    assert "(is_kospi200 = true OR is_kosdaq150 = true)" in sql
    assert "ticker <> ALL(" in sql
    assert "scty_grp_id_cd" in sql
