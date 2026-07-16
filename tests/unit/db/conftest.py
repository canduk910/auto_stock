"""사이클 M2b — stock_master pg.* 인메모리 fake (round-trip 테스트용).

stock_master.py 가 supabase-py → src.db.pg(asyncpg) 로 전환되며 기존
`fake_supabase`(테이블 체인 흉내) 로는 라우팅이 불가(모듈이 supabase 를 더 이상
import 하지 않음). upsert_one → get → is_stale round-trip 계약을 pg.fetch/fetchrow/
execute 인터페이스로 흉내내는 최소 stateful fake.

SQL 텍스트를 완전 파싱하지 않고, stock_master.py 가 실제로 발화하는 고정 패턴만
인식한다:
- `INSERT INTO stock_master (...) ... ON CONFLICT (ticker) DO UPDATE ...` → upsert row
- `SELECT * FROM stock_master WHERE ticker = $1` → fetchrow(get)
- `SELECT refreshed_at FROM stock_master WHERE ticker = $1` → fetch(is_stale)
"""

from __future__ import annotations

from typing import Any

import pytest


class FakePgStockMaster:
    """stock_master 전용 stateful pg.* fake (ticker → row dict)."""

    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}

    async def execute(self, sql: str, *args: Any) -> str:
        s = sql.strip()
        if "INSERT INTO stock_master" in s and "ON CONFLICT (ticker)" in s:
            # upsert_one 컬럼 순서:
            #   ticker, name, excg_dvsn_cd, nxt_tradable, krx_halted,
            #   admin_item, raw, refreshed_at
            (
                ticker,
                name,
                excg_dvsn_cd,
                nxt_tradable,
                krx_halted,
                admin_item,
                raw,
                refreshed_at,
            ) = args[:8]
            self.store[ticker] = {
                "ticker": ticker,
                "name": name,
                "excg_dvsn_cd": excg_dvsn_cd,
                "nxt_tradable": nxt_tradable,
                "krx_halted": krx_halted,
                "admin_item": admin_item,
                "raw": raw,
                # 소비처(is_stale)가 datetime/str 모두 흡수 → datetime 그대로 보관.
                "refreshed_at": refreshed_at,
            }
            return "INSERT 0 1"
        return "INSERT 0 1"

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        ticker = args[0] if args else None
        return self.store.get(ticker)

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        s = sql.strip()
        if "refreshed_at" in s and "WHERE ticker" in s:
            ticker = args[0]
            row = self.store.get(ticker)
            if row is None:
                return []
            return [{"refreshed_at": row.get("refreshed_at")}]
        # 그 외 SELECT — 전체 반환(테스트 미사용 경로 graceful)
        return list(self.store.values())

    async def fetchval(self, sql: str, *args: Any) -> Any:
        return len(self.store)

    async def _with_retry(self, coro_factory, *, op: str = ""):
        return await coro_factory()


@pytest.fixture
def fake_pg_stock_master() -> FakePgStockMaster:
    return FakePgStockMaster()
