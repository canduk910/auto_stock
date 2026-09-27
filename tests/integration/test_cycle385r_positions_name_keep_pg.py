"""cycle385 부록 R-5 (d) — 실 Postgres: 빈 종목명 upsert 가 저장된 이름을 지키는가 (TR27 통합).

명세 = `_workspace/red/cycle385_b7_partial_sell_spec.md` 부록 R-5 (d)
단위 짝 = `tests/unit/db/test_cycle385r_positions_name_keep.py`

docker/`DATABASE_URL_TEST` 없으면 `pg_harness` fixture 가 `pytest.skip`.
"""
from __future__ import annotations

from datetime import date

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def _save(name: str, qty: int) -> None:
    from src.db import positions

    await positions.save_position(
        ticker="005930", ticker_name=name, buy_price=70_000, quantity=qty,
        order_no="BUY-1", strategy_id="kojiro", buy_date=date(2026, 9, 21),
        high_since_buy=71_000,
    )


async def _row() -> dict:
    from src.db import positions

    rows = await positions.load_all()
    assert len(rows) == 1
    return rows[0]


@pytest.mark.asyncio
async def test_tr27_pg_blank_name_keeps_stored_name(clean_positions):
    """🔴 TR27 — 「삼성전자」 행 → 빈 이름으로 upsert(수량 7) → 이름 유지 · 수량 갱신 →
    「X」 로 upsert → 「X」(빈 값이 아닌 새 이름은 그대로 이긴다)."""
    await _save("삼성전자", 10)
    await _save("", 7)
    r = await _row()
    assert r["ticker_name"] == "삼성전자", f"빈 이름 upsert 가 저장된 이름을 지웠다: {r['ticker_name']!r}"
    assert r["quantity"] == 7, "이름을 지키느라 다른 칸 갱신이 빠졌다"

    await _save("X", 5)
    r = await _row()
    assert r["ticker_name"] == "X"
    assert r["quantity"] == 5


@pytest.mark.asyncio
async def test_tr27b_pg_first_insert_with_blank_name_is_blank(clean_positions):
    """🔵 TR27b — 행이 없을 때의 INSERT 는 무변경(빈 이름이면 빈 이름으로 들어간다)."""
    await _save("", 3)
    r = await _row()
    assert r["ticker_name"] == ""
    assert r["quantity"] == 3
