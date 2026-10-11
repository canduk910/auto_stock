"""cycle446 — `src/db/exit_ai.py` 읽기 모듈 단위 검증(pg 호출은 monkeypatch)."""
from __future__ import annotations

from datetime import date

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_get_latest_verdicts_empty_pairs_skips_query(monkeypatch):
    from src.db import exit_ai

    called = False

    async def fake_fetch(sql, *args):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("src.db.pg.fetch", fake_fetch)
    out = await exit_ai.get_latest_verdicts([])
    assert out == {}
    assert called is False


@pytest.mark.asyncio
async def test_get_latest_verdicts_keeps_first_row_per_pair_bar_date_desc(monkeypatch):
    from src.db import exit_ai

    rows = [
        {"strategy_id": "kojiro", "ticker": "005930", "buy_date": date(2026, 10, 10),
         "buy_order_no": "1", "bar_date": date(2026, 10, 13), "action": "hold", "exit_score": 40,
         "rationale": "r1", "evaluated_at_iso": "2026-10-14T08:16:00.000000+09:00"},
        {"strategy_id": "kojiro", "ticker": "005930", "buy_date": date(2026, 10, 10),
         "buy_order_no": "1", "bar_date": date(2026, 10, 12), "action": "hold", "exit_score": 30,
         "rationale": "r0", "evaluated_at_iso": "2026-10-13T08:16:00.000000+09:00"},
    ]

    async def fake_fetch(sql, *args):
        assert "result = 'ok'" in sql
        assert args == ("kojiro", "005930")
        return rows

    monkeypatch.setattr("src.db.pg.fetch", fake_fetch)
    out = await exit_ai.get_latest_verdicts([("kojiro", "005930")])
    assert out[("kojiro", "005930")]["exit_score"] == 40  # 더 최신 bar_date 행


@pytest.mark.asyncio
async def test_get_evaluations_for_position_passes_through(monkeypatch):
    from src.db import exit_ai

    async def fake_fetch(sql, *args):
        assert args[0] == "kojiro"
        assert args[1] == "005930"
        return [{"bar_date": date(2026, 10, 13), "action": "exit"}]

    monkeypatch.setattr("src.db.pg.fetch", fake_fetch)
    out = await exit_ai.get_evaluations_for_position(
        strategy_id="kojiro", ticker="005930", buy_date=date(2026, 10, 10), buy_order_no="1",
    )
    assert out == [{"bar_date": date(2026, 10, 13), "action": "exit"}]


@pytest.mark.asyncio
async def test_get_today_run_status_returns_none_when_missing(monkeypatch):
    from src.db import exit_ai

    async def fake_fetchrow(sql, *args):
        return None

    monkeypatch.setattr("src.db.pg.fetchrow", fake_fetchrow)
    out = await exit_ai.get_today_run_status(date(2026, 10, 14))
    assert out is None


def test_exit_ai_strategies_matches_design_five():
    from src.db.exit_ai import EXIT_AI_STRATEGIES

    assert EXIT_AI_STRATEGIES == frozenset({
        "donchian_swing", "kojiro", "vcp_breakout", "bull_flag_breakout", "etf_trend",
    })
