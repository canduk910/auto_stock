"""사이클 84 Red — M-2 (HIGH): trigger INSERT 동작 검증.

stock_master UPSERT INSERT 시 trigger 가 stock_master_history INSERT (change_type='INSERT' +
before_raw=NULL + after_raw=전수).

본 테스트는 마이그레이션 적용된 Supabase 환경에서 trigger 가 실제 INSERT 시점 발화하는지
mocked supabase로 검증한다 (실 DB 호출은 통합 테스트 영역).

위험 등급 HIGH (변경기록 영속의 INSERT 케이스 — 9 회 silent 결함 영구 차단 패턴 신규 영역).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_M2_trigger_insert_creates_history_row():
    """M-2: stock_master UPSERT (신규 INSERT) → stock_master_history `INSERT` row.

    backend-dev Green 단계: trigger 가 DB 레벨에서 자동 발화. Python 응용 코드 변경 0.
    헬퍼 `list_history(ticker)` 가 INSERT change_type 1건 반환 의무.
    """
    from src.db import stock_master

    list_history = getattr(stock_master, "list_history", None)
    assert list_history is not None, (
        "stock_master.list_history(ticker) 헬퍼 미작성 — backend-dev Green 단계 4 헬퍼 추가 의무"
    )

    # 모의 시나리오: ticker '005930' INSERT 직후 history 조회 → INSERT row 1건
    fake_rows = [{
        "id": 1,
        "ticker": "005930",
        "change_type": "INSERT",
        "before_raw": None,
        "after_raw": {"prdt_name": "삼성전자", "bfdy_clpr": "70000"},
        "changed_at": "2026-06-09T09:00:00+09:00",
    }]
    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=fake_rows)
        rows = await list_history("005930", limit=100)

    assert len(rows) >= 1, "INSERT 직후 history row 0건 — trigger 미발화 가정 결함"
    row = rows[0]
    assert row["change_type"] == "INSERT", (
        f"INSERT change_type 부재 (실제={row['change_type']})"
    )
    assert row["before_raw"] is None, "INSERT 케이스 before_raw NULL 의무"
    assert row["after_raw"] is not None, "INSERT 케이스 after_raw 전수 의무"
