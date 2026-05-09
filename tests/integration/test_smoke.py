"""통합 테스트 인프라 동작 확인용 스모크.

Phase A 단계에서는 실제 모듈 결합 검증을 하지 않고,
fixture(fake_supabase, fake_ws, mock_kis, kst_clock)가 정상 부트되는지만 확인.
Phase C/D 사이클에서 실제 통합 시나리오로 대체된다.
"""

from __future__ import annotations

from datetime import datetime

import pytest


pytestmark = pytest.mark.integration


def test_fake_supabase_basic_crud(fake_supabase):
    fake_supabase.table("positions").insert({"ticker": "005930", "qty": 10}).execute()
    rows = fake_supabase.table("positions").select("*").eq("ticker", "005930").execute().data
    assert len(rows) == 1
    assert rows[0]["qty"] == 10


def test_fake_supabase_update_and_delete(fake_supabase):
    fake_supabase.table("positions").insert({"ticker": "005930", "qty": 10}).execute()
    fake_supabase.table("positions").update({"qty": 20}).eq("ticker", "005930").execute()
    rows = fake_supabase.table("positions").select("*").execute().data
    assert rows[0]["qty"] == 20

    fake_supabase.table("positions").delete().eq("ticker", "005930").execute()
    rows = fake_supabase.table("positions").select("*").execute().data
    assert rows == []


@pytest.mark.asyncio
async def test_fake_ws_push_recv(fake_ws):
    await fake_ws.push("H0UNCNT0", "005930^144000^72000")
    msg = await fake_ws.recv()
    assert "H0UNCNT0" in msg
    assert "005930" in msg


def test_kst_clock_freezes_time(kst_clock):
    with kst_clock("2026-05-08 15:19:55"):
        now = datetime.now()
        assert now.year == 2026
        assert now.month == 5
        assert now.day == 8
