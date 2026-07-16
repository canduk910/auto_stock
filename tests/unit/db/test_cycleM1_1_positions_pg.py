"""사이클 M1-1 (Red) — src/db/positions.py asyncpg 전환 계약 가드.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 1, 증분 1).

현행 positions.py 는 supabase-py 체인(`supabase.table(...).upsert(...).execute()`)이다.
이 증분 = `pg.*`(fetch/execute) 로 전환. **함수 계약(시그니처·반환형) 100% 보존** →
호출부(order_engine 등) diff 0.

Red 유효성: production(positions.py) 미변경 상태에서
- 단위: `pg.fetch`/`pg.execute` 를 patch 했으나 positions.py 가 아직 supabase 를 호출
  → mock 미발화 → 계약 단언 FAIL.
- 통합: 실 PG 왕복은 pg 경유 코드가 없으니(supabase 미연결) FAIL/에러.

전환 대상 SQL (대표 키워드):
- save_position → `INSERT INTO positions ... ON CONFLICT (ticker) DO UPDATE`
- delete_position → `DELETE FROM positions WHERE ticker = $1`
- load_all → `SELECT ... FROM positions` (→ list[dict])
- update_high → `UPDATE positions SET high_since_buy = $1 WHERE ticker = $2`
- clear_all → `DELETE FROM positions`

계약 불변식:
- save_position/delete_position/update_high/clear_all → None
- load_all → list[dict] (dict 키 = 컬럼명, order_engine 이 그대로 소비)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 단위 (mock) — pg.fetch / pg.execute patch 로 SQL·args·반환형 계약 검증
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_position_uses_pg_upsert_sql():
    """save_position → pg.execute 로 INSERT ... ON CONFLICT (ticker) DO UPDATE."""
    from src.db import positions

    with patch.object(positions, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await positions.save_position(
            ticker="005930",
            ticker_name="삼성전자",
            buy_price=70000,
            quantity=10,
            order_no="BUY-000001",
            strategy_id="momentum",
            buy_date=date(2026, 7, 16),
            high_since_buy=71000,
        )

    assert out is None, "save_position 반환형 None 계약 보존."
    assert pg_mod.execute.await_count == 1, "save_position 이 pg.execute 1회 호출."
    sql = pg_mod.execute.await_args.args[0]
    assert "INSERT INTO positions" in sql, "INSERT INTO positions SQL 누락."
    assert "ON CONFLICT (ticker) DO UPDATE" in sql, (
        "upsert = ON CONFLICT (ticker) DO UPDATE 누락."
    )
    # 파라미터 순서 — ticker 가 인자에 포함 (positional $N)
    passed_args = pg_mod.execute.await_args.args[1:]
    assert "005930" in passed_args, "ticker 파라미터 바인딩 누락."
    assert 70000 in passed_args and 10 in passed_args, "buy_price/quantity 바인딩 누락."


@pytest.mark.asyncio
async def test_save_position_high_since_buy_defaults_to_buy_price():
    """high_since_buy 기본 0 → buy_price 로 보정 (기존 `high or buy_price` 계약)."""
    from src.db import positions

    with patch.object(positions, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await positions.save_position(
            ticker="000660",
            ticker_name="SK하이닉스",
            buy_price=100000,
            quantity=5,
            order_no="BUY-000002",
            strategy_id="volatility_breakout",
            buy_date=date(2026, 7, 16),
            # high_since_buy 미지정 → 기본 0 → buy_price(100000) 로 보정
        )

    passed_args = pg_mod.execute.await_args.args[1:]
    assert 100000 in passed_args, "high_since_buy=0 → buy_price 보정 계약 위반."


@pytest.mark.asyncio
async def test_delete_position_uses_pg_delete_sql():
    """delete_position → pg.execute 로 DELETE FROM positions WHERE ticker = $1."""
    from src.db import positions

    with patch.object(positions, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="DELETE 1")
        out = await positions.delete_position("005930")

    assert out is None, "delete_position 반환형 None 계약 보존."
    assert pg_mod.execute.await_count == 1
    sql = pg_mod.execute.await_args.args[0]
    assert "DELETE FROM positions" in sql
    assert "ticker" in sql, "DELETE 에 ticker WHERE 절 누락."
    assert pg_mod.execute.await_args.args[1] == "005930", "ticker 파라미터 바인딩 누락."


@pytest.mark.asyncio
async def test_load_all_returns_list_of_dict_via_pg_fetch():
    """load_all → pg.fetch(SELECT ... positions) → list[dict] (컬럼명 키 보존)."""
    from src.db import positions

    rows = [
        {
            "ticker": "005930", "ticker_name": "삼성전자", "buy_price": 70000,
            "quantity": 10, "order_no": "BUY-000001", "strategy_id": "momentum",
            "buy_date": date(2026, 7, 16), "high_since_buy": 71000,
        },
        {
            "ticker": "000660", "ticker_name": "SK하이닉스", "buy_price": 100000,
            "quantity": 5, "order_no": "BUY-000002", "strategy_id": "volatility_breakout",
            "buy_date": date(2026, 7, 16), "high_since_buy": 100000,
        },
    ]
    with patch.object(positions, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await positions.load_all()

    assert out == rows, "load_all → list[dict] 행 내용·키 보존 (order_engine 소비 계약)."
    assert isinstance(out, list) and all(isinstance(r, dict) for r in out)
    sql = pg_mod.fetch.await_args.args[0]
    assert "SELECT" in sql.upper() and "positions" in sql, (
        "load_all SELECT FROM positions SQL 누락."
    )


@pytest.mark.asyncio
async def test_load_all_empty_returns_empty_list():
    """load_all 0건 → [] (result.data 빈 배열 대응)."""
    from src.db import positions

    with patch.object(positions, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        out = await positions.load_all()

    assert out == [], "0건 → 빈 리스트."


@pytest.mark.asyncio
async def test_update_high_uses_pg_update_sql():
    """update_high → pg.execute 로 UPDATE positions SET high_since_buy = $1 WHERE ticker = $2."""
    from src.db import positions

    with patch.object(positions, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="UPDATE 1")
        out = await positions.update_high("005930", 72500)

    assert out is None, "update_high 반환형 None 계약 보존."
    sql = pg_mod.execute.await_args.args[0]
    assert "UPDATE positions SET high_since_buy" in sql, (
        "UPDATE positions SET high_since_buy SQL 누락."
    )
    passed_args = pg_mod.execute.await_args.args[1:]
    assert 72500 in passed_args and "005930" in passed_args, (
        "high/ticker 파라미터 바인딩 누락."
    )


@pytest.mark.asyncio
async def test_clear_all_uses_pg_delete_all_sql():
    """clear_all → pg.execute 로 DELETE FROM positions (전체 삭제)."""
    from src.db import positions

    with patch.object(positions, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="DELETE 3")
        out = await positions.clear_all()

    assert out is None, "clear_all 반환형 None 계약 보존."
    sql = pg_mod.execute.await_args.args[0]
    assert "DELETE FROM positions" in sql, "clear_all DELETE FROM positions SQL 누락."


# ---------------------------------------------------------------------------
# 계약 보존 불변식 — supabase 미참조 (전환 완료 증명)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_positions_no_supabase_reference_after_transition():
    """전환 후 positions.py 는 supabase 를 참조하지 않는다 (pg 단독).

    Red 단계: 현행 positions.py 가 여전히 `from src.db.supabase import supabase`
    → 모듈에 supabase 심볼 존재 → 이 단언 FAIL. Green 후 pg 로 교체되면 PASS.
    """
    from src.db import positions

    assert not hasattr(positions, "supabase"), (
        "전환 후 positions 모듈에 supabase 심볼이 남으면 안 됨 (pg 단독 전환)."
    )
    assert hasattr(positions, "pg"), "positions 모듈이 src.db.pg 를 import 해야 함."
