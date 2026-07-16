"""사이클 129 — `stock_master.master_raw` 컬럼 Red 회귀 가드.

배경:
- migration 034: ALTER TABLE stock_master ADD master_raw JSONB + master_raw_updated_at TIMESTAMPTZ
- 사용자 결정 Q6=C 별도 컬럼 → 사이클 81 G-AST1 (raw 덮어쓰기 금지) 영속 보호

회귀 가드 4 케이스:
- G-MC1: upsert_master_raw 정상 (JSONB + updated_at_kst KST timestamp)
- G-MC2: get_master_raw 조회 (NULL/{} 부재 회피)
- G-MC3: count_master_raw_today 진단
- G-MC4: 사이클 81 G-AST1 영속 = raw 영역 변경 0 (upsert_master_raw 호출 후 raw 동일)
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.db._kst import KST


@pytest.mark.asyncio
async def test_g_mc1_upsert_master_raw_jsonb_kst():
    """G-MC1: upsert_master_raw 정상 (master_raw JSONB dict + master_raw_updated_at KST).

    사이클 M2b — pg.execute(SQL, ticker, master_raw dict, datetime, ...). master_raw 는
    dict 직접 바인딩(codec 전담), master_raw_updated_at 는 KST aware datetime 바인딩
    (사이클 68 G-10b — 이전 supabase 는 `+09:00` ISO string, asyncpg 는 TIMESTAMPTZ datetime).
    """
    from src.db import stock_master

    sample_master = {
        "mksc_shrn_iscd": "005930",
        "hts_kor_isnm": "삼성전자",
        "trht_yn": "N",
        "mang_issu_yn": "N",
        "ssts_hot_yn": "N",
        "stange_runup_yn": "N",
        "mrkt_alrm_cls_code": "00",
        "prdy_avls_scal": "5000000",
        "lstn_stcn": "5969783",
        "roe": "12.5",
    }

    assert hasattr(stock_master, "upsert_master_raw"), "G-MC1: upsert_master_raw 함수 부재"

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await stock_master.upsert_master_raw("005930", sample_master)

    sql = pg_mod.execute.await_args.args[0]
    args = pg_mod.execute.await_args.args[1:]
    assert "master_raw" in sql, "G-MC1: master_raw 컬럼 SQL 부재"
    # master_raw JSONB dict 직접 바인딩
    assert any(isinstance(a, dict) and a == sample_master for a in args), (
        "G-MC1: master_raw dict 값 바인딩 불일치"
    )
    # master_raw_updated_at = KST aware datetime (사이클 68 G-10b)
    kst_dt = next((a for a in args if isinstance(a, datetime)), None)
    assert kst_dt is not None, "G-MC1: master_raw_updated_at datetime 바인딩 부재"
    assert kst_dt.utcoffset() == KST.utcoffset(None), (
        "G-MC1: KST +09:00 timezone 위반 (사이클 68 G-10b 답습)"
    )


@pytest.mark.asyncio
async def test_g_mc2_get_master_raw():
    """G-MC2: get_master_raw 조회 영역 (NULL/{} 부재 회피). 사이클 M2b — pg.fetchrow."""
    from src.db import stock_master

    sample_master = {"mksc_shrn_iscd": "000660", "trht_yn": "Y"}

    assert hasattr(stock_master, "get_master_raw"), "G-MC2: get_master_raw 함수 부재"

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"master_raw": sample_master})
        result = await stock_master.get_master_raw("000660")

    assert result == sample_master, f"G-MC2: master_raw 조회 결함 (result={result!r})"


@pytest.mark.asyncio
async def test_g_mc3_count_master_raw_today():
    """G-MC3: count_master_raw_today 오늘 영역 갱신 진단. 사이클 M2b — pg.fetchval."""
    from src.db import stock_master

    assert hasattr(stock_master, "count_master_raw_today"), (
        "G-MC3: count_master_raw_today 함수 부재"
    )

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=2697)
        result = await stock_master.count_master_raw_today()

    assert isinstance(result, int), "G-MC3: count_master_raw_today int 반환 영역 위반"
    assert result >= 0, "G-MC3: 음수 영역 위반"


@pytest.mark.asyncio
async def test_g_mc4_upsert_master_raw_preserves_raw_g_ast1():
    """G-MC4: 사이클 81 G-AST1 영속 = upsert_master_raw 가 raw 컬럼 변경 0.

    사이클 M2b — pg.execute SQL 이 raw/bfdy_clpr/hts_avls 컬럼을 SET 하지 않음
    (master_raw 별도 컬럼만 upsert — Q6=C).
    """
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await stock_master.upsert_master_raw("005930", {"trht_yn": "N"})

    sql = pg_mod.execute.await_args.args[0]
    # G-AST1 영속 (사이클 81): raw / bfdy_clpr / hts_avls 컬럼 write 부재 의무.
    # (master_raw 는 별도 컬럼이라 "master_raw" 는 허용 — "raw =" write 만 금지 대상)
    assert "raw = " not in sql.replace("master_raw = ", ""), (
        "G-MC4: 사이클 81 G-AST1 위반 — upsert_master_raw 가 raw 컬럼 write 시도"
    )
    assert "bfdy_clpr" not in sql, "G-MC4: bfdy_clpr write 시도"
    assert "hts_avls" not in sql, "G-MC4: hts_avls write 시도"
