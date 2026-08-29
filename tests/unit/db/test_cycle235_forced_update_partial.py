"""cycle235 R6 (N1-b) — 강제 UPDATE 가 PARTIAL row 를 COMPLETED 로 올린다.

257720 실측: 전량 체결 보정 경로의 `_update_trade_status_by_order_no` 가
WHERE status='PENDING' 고정이라 이미 PARTIAL 로 기록된 row 를 못 잡아
affected=0 → trade 가 PARTIAL 영구 잔존. 진행 중 상태(PENDING·PARTIAL)만
포괄하고 COMPLETED/CANCELLED 는 계속 불변이어야 한다.
"""

from __future__ import annotations

import pytest

from src.db import trade_history as th
from src.models.trade import TradeStatus, TradeType

pytestmark = pytest.mark.unit


@pytest.fixture
def captured_sql(monkeypatch):
    calls: list[tuple[str, tuple]] = []

    async def _execute(sql, *args):
        calls.append((sql, args))
        return "UPDATE 1"

    monkeypatch.setattr(th.pg, "execute", _execute)
    return calls


class TestR6ForcedUpdateCoversPartial:
    @pytest.mark.asyncio
    async def test_where_covers_pending_and_partial(self, captured_sql):
        affected = await th._update_trade_status_by_order_no(
            "0000411400", TradeType.BUY, TradeStatus.COMPLETED, price=51_100,
        )
        assert affected == 1
        sql, args = captured_sql[0]
        flat = sql.upper() + " " + " ".join(str(a) for a in args)
        assert "PENDING" in flat and "PARTIAL" in flat, (
            "WHERE 가 PENDING 단독 — PARTIAL 전량 체결 보정이 영구 실패 (257720 N1-b)"
        )
        # 최소한 상태 제한이 존재해야 한다 (WHERE 무제한 금지)
        assert "STATUS" in sql.upper().split("WHERE")[1]
        # 종결 상태 편입 금지 — 바인딩된 status 리스트가 **정확히** 진행 중 2종
        # (적대 검증 C235-V1: 문자열 절단 + `or True` 검사는 공허했다 — 상태 목록은
        # SQL 텍스트가 아니라 바인드 인자로 전달되므로 인자를 직접 검사한다)
        status_lists = [a for a in args if isinstance(a, list)]
        assert len(status_lists) == 1, "status 바인드 리스트 인자 1개가 계약"
        assert sorted(status_lists[0]) == ["PARTIAL", "PENDING"], (
            f"진행 중 상태 2종 정확 일치 위반: {status_lists[0]} — "
            "COMPLETED/CANCELLED 편입은 종결 상태 불변 계약 파괴"
        )
