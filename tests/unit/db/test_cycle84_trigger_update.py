"""사이클 84 Red — M-3 (HIGH): trigger UPDATE 동작 검증 (raw 변경).

stock_master UPSERT 시 OLD.raw != NEW.raw → trigger `change_type='UPDATE'` + before/after 보존.

위험 등급 HIGH (변경기록 영속의 UPDATE 케이스 — Q6=A 전체 67 키 진단 가시화 영역).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_M3_trigger_update_records_before_and_after():
    """M-3: stock_master UPSERT (raw 변경) → history `change_type=UPDATE` + before/after 양쪽 보존.

    예: bfdy_clpr 70000 → 71000 변경 시 before_raw.bfdy_clpr=70000 + after_raw.bfdy_clpr=71000.
    """
    from src.db import stock_master

    list_history = getattr(stock_master, "list_history", None)
    assert list_history is not None, (
        "stock_master.list_history 헬퍼 미작성 — backend-dev Green 단계 의무"
    )

    fake_rows = [{
        "id": 2,
        "ticker": "005930",
        "change_type": "UPDATE",
        "before_raw": {"prdt_name": "삼성전자", "bfdy_clpr": "70000"},
        "after_raw": {"prdt_name": "삼성전자", "bfdy_clpr": "71000"},
        "changed_at": "2026-06-09T09:01:00+09:00",
    }]
    fake_result = MagicMock()
    fake_result.data = fake_rows

    with patch("src.db.stock_master.supabase") as mock_supabase:
        chain = mock_supabase.table.return_value
        chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = fake_result
        chain.select.return_value.eq.return_value.order.return_value.execute.return_value = fake_result

        rows = await list_history("005930", limit=100)

    assert rows, "UPDATE history row 0건"
    row = rows[0]
    assert row["change_type"] == "UPDATE", (
        f"UPDATE change_type 의무 (실제={row['change_type']})"
    )
    assert row["before_raw"] is not None and row["after_raw"] is not None, (
        "UPDATE 케이스 before/after 양쪽 보존 의무"
    )
    assert row["before_raw"].get("bfdy_clpr") != row["after_raw"].get("bfdy_clpr"), (
        "UPDATE 시 raw 변경 영역 (bfdy_clpr 등) before/after 차이 보존"
    )
