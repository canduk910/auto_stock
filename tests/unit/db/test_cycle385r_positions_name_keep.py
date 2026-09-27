"""cycle385 부록 R-5 (d) — `save_position` 은 **빈 종목명으로 저장된 이름을 덮지 않는다** (TR27 단위).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` 부록 R-5 (d)
실 Postgres 짝 = `tests/integration/test_cycle385r_positions_name_keep_pg.py`

## 결함

`save_position` 의 upsert 가 `ticker_name = EXCLUDED.ticker_name` 이다. B7 의 「보유 남음」 경로
(`_handle_sell_fill` 의 `ticker_names.get(ticker, "")`)와 #1.5 재대조(`t(ticker)` 파생 — 캐시
miss 면 `""`)가 이름 캐시를 못 찾으면 저장된 이름을 **빈 값으로** 지운다. 빈 이름은 정보가 아니다.

## 시정

`ticker_name = COALESCE(NULLIF(EXCLUDED.ticker_name, ''), positions.ticker_name)` — 호출부 인자는
그대로(이름을 따로 조회하느라 await 를 더하지 않는다). INSERT(행 없음)는 무변경.
"""
from __future__ import annotations

import re
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


async def _captured_sql(ticker_name: str) -> tuple[str, tuple]:
    from src.db import positions

    with patch.object(positions, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await positions.save_position(
            ticker="005930", ticker_name=ticker_name, buy_price=70_000, quantity=7,
            order_no="BUY-1", strategy_id="kojiro", buy_date=date(2026, 9, 21),
            high_since_buy=71_000,
        )
    return pg_mod.execute.await_args.args[0], pg_mod.execute.await_args.args[1:]


@pytest.mark.asyncio
async def test_tr27_upsert_does_not_blank_a_stored_name():
    """🔴 TR27 — ON CONFLICT 갱신이 빈 이름을 무시하고 저장된 이름을 지킨다."""
    sql, _ = await _captured_sql("")
    flat = re.sub(r"\s+", " ", sql)
    assert "COALESCE(NULLIF(EXCLUDED.ticker_name, ''), positions.ticker_name)" in flat, (
        "빈 종목명 upsert 가 저장된 이름을 덮는다 — 캐시 miss 한 번에 화면·DB 종목명이 사라진다"
    )
    assert "ticker_name = EXCLUDED.ticker_name," not in flat


@pytest.mark.asyncio
async def test_tr27b_caller_arguments_and_insert_values_unchanged():
    """🔵 TR27b — 인자 바인딩(8개, 이름은 $2 그대로)은 무변경 — INSERT 경로는 빈 이름도 그대로 적는다."""
    sql, args = await _captured_sql("")
    assert "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)" in re.sub(r"\s+", " ", sql)
    assert args[:2] == ("005930", "")
    assert len(args) == 8
