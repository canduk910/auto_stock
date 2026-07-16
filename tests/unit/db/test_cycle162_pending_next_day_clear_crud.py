"""사이클 162 회귀 가드 — DB 영역 (의제 D).

대상: `src/db/pending_next_day_clear.py` CRUD 4 함수.
domain-expert 자문 산출물 `_workspace/domain_consult/cycle162_pending_persist_and_call_auction.md`.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db import pending_next_day_clear as ndc

pytestmark = pytest.mark.xfail(
    reason=(
        "사이클 M1-2 의미 전환 — pending_next_day_clear.py 가 supabase-py 체인에서 "
        "src.db.pg(asyncpg) 로 전환되어 `patch('src.db.pending_next_day_clear.supabase')` "
        "전제가 더 이상 성립하지 않는다(AttributeError). ⚠️ 익일청산큐 매매 안전성 계약"
        "(복합 PK upsert / load graceful 빈 set / purge graceful -1 / reason 기본값)은 "
        "`tests/unit/db/test_cycleM1_2_pending_ndc_pg.py` 가 pg mock 기반으로 전량 "
        "동등 대체(G-162 전체 케이스 커버). 회귀 아님 (사이클 M1-1 선례 답습)."
    ),
    strict=False,
)


def _make_supabase_chain(data=None):
    """Supabase chain mock — execute() 호출 시 data 반환."""
    fluent = MagicMock()
    fluent.execute.return_value = SimpleNamespace(data=data or [])
    fluent.upsert.return_value = fluent
    fluent.delete.return_value = fluent
    fluent.select.return_value = fluent
    fluent.eq.return_value = fluent
    fluent.lt.return_value = fluent
    return fluent


@pytest.mark.asyncio
async def test_G_162_D_1_save_pending_ndc_upsert_payload():
    """G-162-D-1 (HIGH): save 시 UPSERT payload 4 키 + on_conflict PK 정합."""
    chain = _make_supabase_chain()
    with patch("src.db.pending_next_day_clear.supabase") as sb:
        sb.table.return_value = chain
        await ndc.save_pending_ndc(
            date(2026, 6, 18), "196170", "volatility_breakout", "nxt_not_tradable",
        )
    sb.table.assert_called_once_with("pending_next_day_clear")
    upsert_args, upsert_kwargs = chain.upsert.call_args
    payload = upsert_args[0]
    assert payload["target_date"] == "2026-06-18"
    assert payload["ticker"] == "196170"
    assert payload["strategy_id"] == "volatility_breakout"
    assert payload["reason"] == "nxt_not_tradable"
    assert "created_at" in payload
    assert payload["created_at"].endswith("+09:00") or "+09" in payload["created_at"]
    assert upsert_kwargs["on_conflict"] == "target_date,ticker,strategy_id"


@pytest.mark.asyncio
async def test_G_162_D_2_delete_pending_ndc_pk_filter():
    """G-162-D-2: delete 시 3 PK 컬럼 eq filter."""
    chain = _make_supabase_chain()
    with patch("src.db.pending_next_day_clear.supabase") as sb:
        sb.table.return_value = chain
        await ndc.delete_pending_ndc(
            date(2026, 6, 18), "476830", "long_tail_volatility",
        )
    eq_calls = [call.args for call in chain.eq.call_args_list]
    assert ("target_date", "2026-06-18") in eq_calls
    assert ("ticker", "476830") in eq_calls
    assert ("strategy_id", "long_tail_volatility") in eq_calls


@pytest.mark.asyncio
async def test_G_162_D_3_load_pending_ndc_returns_set():
    """G-162-D-3 (HIGH): load 시 set[(ticker, strategy_id)] 반환."""
    chain = _make_supabase_chain(data=[
        {"ticker": "196170", "strategy_id": "volatility_breakout"},
        {"ticker": "476830", "strategy_id": "long_tail_volatility"},
    ])
    with patch("src.db.pending_next_day_clear.supabase") as sb:
        sb.table.return_value = chain
        result = await ndc.load_pending_ndc(date(2026, 6, 18))
    assert result == {
        ("196170", "volatility_breakout"),
        ("476830", "long_tail_volatility"),
    }


@pytest.mark.asyncio
async def test_G_162_D_4_load_pending_ndc_graceful_on_exception():
    """G-162-D-4 (HIGH): load 실패 시 빈 set 반환 (메모리 set 보존, 사이클 88 G-REJECT)."""
    with patch("src.db.pending_next_day_clear.supabase") as sb:
        sb.table.side_effect = RuntimeError("Supabase down")
        result = await ndc.load_pending_ndc(date(2026, 6, 18))
    assert result == set()


@pytest.mark.asyncio
async def test_G_162_D_5_purge_pending_ndc_before_lt_filter():
    """G-162-D-5: purge 시 target_date < cutoff lt filter."""
    chain = _make_supabase_chain(data=[{"target_date": "2026-06-17"}])
    with patch("src.db.pending_next_day_clear.supabase") as sb:
        sb.table.return_value = chain
        count = await ndc.purge_pending_ndc_before(date(2026, 6, 18))
    chain.lt.assert_called_once_with("target_date", "2026-06-18")
    assert count == 1


@pytest.mark.asyncio
async def test_G_162_D_6_purge_graceful_on_exception_returns_minus_one():
    """G-162-D-6: purge 실패 시 -1 반환 (호출자 흡수)."""
    with patch("src.db.pending_next_day_clear.supabase") as sb:
        sb.table.side_effect = RuntimeError("Supabase down")
        count = await ndc.purge_pending_ndc_before(date(2026, 6, 18))
    assert count == -1


@pytest.mark.asyncio
async def test_G_162_D_7_save_default_reason_is_unknown():
    """G-162-D-7: reason 미명시 시 default 'unknown'."""
    chain = _make_supabase_chain()
    with patch("src.db.pending_next_day_clear.supabase") as sb:
        sb.table.return_value = chain
        await ndc.save_pending_ndc(date(2026, 6, 18), "196170", "volatility_breakout")
    payload = chain.upsert.call_args.args[0]
    assert payload["reason"] == "unknown"
