"""사이클 M2b (Red) — src/db/stock_master_daily.py asyncpg 전환 계약 가드 (일봉 hot path).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 2 — 매매 hot path, HIGH).

현행 stock_master_daily.py = supabase-py 체인 + `execute_with_retry`(사이클 187). 이 증분 = `pg.*` 전환.
**함수 계약(시그니처·반환형·graceful) 100% 보존** → 호출부(scanner/strategies) diff 0.

⚠️ 최대 위험 (일봉 hot path):
1. **get_recent_daily_normalized 폴백 우선순위** (사이클 172/173, prepare 일봉 소스):
   락 게이트 → 신선도 게이트 → min_required 게이트 순. `fetch_daily_candles`(KIS) 미변경 폴백.
   raw JSONB 그대로 반환(사이클 81). 어댑터 = 모듈 함수 조합이라 pg 전환과 무관하게 계약 보존.
2. **purge_old_rows never-drain (P-3)** — SELECT/DELETE 양쪽 protected 제외. SELECT 누락 = never-drain.
3. **get_atr/get_donchian_high Python 계산** — SQL 은 get_recent_daily fetch 만.

Red 유효성: production 미변경 → pg mock 미발화(모듈이 supabase 호출) → 계약 단언 FAIL.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _daily_row(dd: date, *, close: int, high: int, low: int, prev_close: int = 0,
               flng: str = "00", prtt: str = "0.0000") -> dict:
    return {
        "ticker": "005930",
        "bas_dd": dd.isoformat(),
        "open_price": low,
        "high_price": high,
        "low_price": low,
        "close_price": close,
        "volume": 1_000_000,
        "trade_value": 70_000_000_000,
        "change_rate": 0.0,
        "flng_cls_code": flng,
        "prtt_rate": prtt,
        "raw": {
            "stck_bsop_date": dd.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_hgpr": str(high),
            "stck_lwpr": str(low),
        },
    }


# ===========================================================================
# upsert_batch — 100 chunk + 복합키 ON CONFLICT (ticker, bas_dd)
# ===========================================================================
@pytest.mark.asyncio
async def test_upsert_batch_chunks_and_conflict_key():
    """upsert_batch → 100 chunk 배치, ON CONFLICT (ticker, bas_dd). 250건 → 3 chunk."""
    from src.db import stock_master_daily as smd

    candles = [
        {"stck_bsop_date": (date(2026, 1, 1) + timedelta(days=i)).strftime("%Y%m%d"),
         "stck_clpr": str(70000 + i), "stck_hgpr": str(70500 + i), "stck_lwpr": str(69500 + i)}
        for i in range(250)
    ]
    with patch.object(smd, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        pg_mod.execute = AsyncMock(return_value="INSERT 0 100")
        total = await smd.upsert_batch("005930", candles)

    assert total == 250, "upsert_batch 성공 건수 250 (graceful skip 없음)."
    # chunk 발화 (executemany 또는 execute) — 100단위 3회 이상
    write_calls = pg_mod.executemany.await_args_list or pg_mod.execute.await_args_list
    assert len(write_calls) >= 3, "250건 → 100 chunk 3회 이상 발화 (_BATCH_SIZE=100)."
    # 어느 쓰기든 SQL 에 복합키 ON CONFLICT
    sql = write_calls[0].args[0]
    assert "ON CONFLICT (ticker, bas_dd)" in sql.replace('"', ""), "복합키 ON CONFLICT (ticker, bas_dd) 누락."


@pytest.mark.asyncio
async def test_upsert_batch_writes_not_via_with_retry():
    """upsert_batch 쓰기는 _with_retry 미경유 (사이클 187 G-187-A2 멱등 보수)."""
    from src.db import stock_master_daily as smd

    candles = [{"stck_bsop_date": "20260101", "stck_clpr": "70000"}]
    with patch.object(smd, "pg", create=True) as pg_mod:
        pg_mod.executemany = AsyncMock()
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        pg_mod._with_retry = AsyncMock()
        await smd.upsert_batch("005930", candles)

    assert pg_mod._with_retry.await_count == 0, "쓰기(upsert_batch)는 _with_retry 미경유."


# ===========================================================================
# get_recent_daily — bas_dd DESC + limit + graceful
# ===========================================================================
@pytest.mark.asyncio
async def test_get_recent_daily_desc_limit_via_fetch():
    """get_recent_daily → pg.fetch, bas_dd DESC + limit. 읽기 경로."""
    from src.db import stock_master_daily as smd

    rows = [_daily_row(date(2026, 6, 20), close=71000, high=71500, low=70000)]
    with patch.object(smd, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await smd.get_recent_daily("005930", 20)

    assert out == rows, "get_recent_daily → fetch 결과 pass-through."
    sql = pg_mod.fetch.await_args.args[0].upper()
    assert "ORDER BY" in sql and "DESC" in sql, "bas_dd DESC 정렬 누락."
    assert "LIMIT" in sql, "limit 절 누락."
    assert "005930" in pg_mod.fetch.await_args.args[1:], "ticker 바인딩 누락."


@pytest.mark.asyncio
async def test_get_recent_daily_exception_graceful_empty():
    """get_recent_daily 예외 → 빈 list graceful (호출자 KIS fallback)."""
    from src.db import stock_master_daily as smd

    with patch.object(smd, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(side_effect=Exception("boom"))
        out = await smd.get_recent_daily("005930", 20)

    assert out == [], "예외 → 빈 list graceful."


# ===========================================================================
# get_donchian_high / get_atr — Python 계산 (SQL 은 get_recent_daily fetch 만)
# ===========================================================================
@pytest.mark.asyncio
async def test_get_donchian_high_python_max():
    """get_donchian_high → get_recent_daily rows 위 max(high_price) Python 계산."""
    from src.db import stock_master_daily as smd

    rows = [
        _daily_row(date(2026, 6, 20), close=71000, high=72000, low=70000),
        _daily_row(date(2026, 6, 19), close=70500, high=73500, low=70000),
        _daily_row(date(2026, 6, 18), close=70000, high=71000, low=69500),
    ]
    with patch.object(smd, "get_recent_daily", new=AsyncMock(return_value=rows)):
        high = await smd.get_donchian_high("005930", 20)

    assert high == 73500, "N일 신고가 = max(high_price) (Python 계산)."


@pytest.mark.asyncio
async def test_get_atr_wilder_baseline():
    """get_atr → True Range 평균 (Python 계산). 데이터 부족 시 None."""
    from src.db import stock_master_daily as smd

    # ASC 로 뒤집힐 예정 — DESC 로 전달 (최신 먼저)
    rows = [
        _daily_row(date(2026, 6, 20), close=71000, high=72000, low=70000),
        _daily_row(date(2026, 6, 19), close=70000, high=71000, low=69000),
        _daily_row(date(2026, 6, 18), close=69000, high=70000, low=68000),
    ]
    with patch.object(smd, "get_recent_daily", new=AsyncMock(return_value=rows)):
        atr = await smd.get_atr("005930", 14)

    assert atr is not None and atr > 0, "ATR = True Range 평균 (양수)."

    with patch.object(smd, "get_recent_daily", new=AsyncMock(return_value=[])):
        assert await smd.get_atr("005930", 14) is None, "데이터 부족 → None."


# ===========================================================================
# get_recent_daily_normalized — ⚠️ 락/신선도/부족 폴백 (prepare 일봉 소스)
#
# 어댑터 = get_recent_daily/max_bas_dd/fetch_daily_candles 조합 → pg 전환과 무관하게
# 계약 보존(사이클 173 선례 = 모듈 함수 patch). 폴백 우선순위 절대 보존.
# ===========================================================================
@pytest.mark.asyncio
async def test_normalized_normal_returns_raw_jsonb():
    """정상 (락 없음/신선/충분) → raw JSONB 그대로 반환 (KIS 원본 키 stck_clpr 보존, 사이클 81)."""
    from src.db import stock_master_daily as smd

    db_rows = [_daily_row(date(2026, 6, 20) - timedelta(days=i), close=71000 - i * 100,
                          high=71500, low=70000) for i in range(22)]
    fetch_kis = AsyncMock()
    with patch.object(smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(smd, "max_bas_dd", new=AsyncMock(return_value=date.today() - timedelta(days=1))), \
            patch("src.api.condition.fetch_daily_candles", new=fetch_kis):
        out = await smd.get_recent_daily_normalized("005930", 22, min_required=22)

    assert fetch_kis.await_count == 0, "정상 → KIS 폴백 미발화 (DB raw 사용)."
    assert all("stck_clpr" in r for r in out), "raw JSONB (KIS 원본 키) 그대로 반환 (사이클 81)."


@pytest.mark.asyncio
async def test_normalized_lock_forces_kis_fallback():
    """⚠️ 락 게이트 (최우선) — flng_cls_code 비기본 → KIS 폴백 (수정주가 divergence 방어, 사이클 173)."""
    from src.db import stock_master_daily as smd

    db_rows = [_daily_row(date(2026, 6, 20) - timedelta(days=i), close=71000, high=71500, low=70000)
               for i in range(22)]
    db_rows[5]["flng_cls_code"] = "01"  # 락 (액면분할 등)
    kis_rows = [{"stck_bsop_date": "20260620", "stck_clpr": "999"}]
    fetch_kis = AsyncMock(return_value=kis_rows)
    with patch.object(smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(smd, "max_bas_dd", new=AsyncMock(return_value=date.today() - timedelta(days=1))), \
            patch("src.api.condition.fetch_daily_candles", new=fetch_kis):
        out = await smd.get_recent_daily_normalized("005930", 22, min_required=22)

    assert fetch_kis.await_count == 1, "락 발생 → KIS 강제 폴백 (사이클 173 G-EQ-3 최우선)."
    assert out == kis_rows, "락 시 KIS 응답 반환."


@pytest.mark.asyncio
async def test_normalized_stale_forces_kis_fallback():
    """신선도 게이트 — max_bas_dd 가 today-4 보다 오래 → KIS 폴백 (사이클 173 G-EQ-4)."""
    from src.db import stock_master_daily as smd

    db_rows = [_daily_row(date(2026, 6, 20) - timedelta(days=i), close=71000, high=71500, low=70000)
               for i in range(22)]
    kis_rows = [{"stck_bsop_date": "x", "stck_clpr": "1"}]
    fetch_kis = AsyncMock(return_value=kis_rows)
    stale_dd = date.today() - timedelta(days=10)  # staleness > 4
    with patch.object(smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(smd, "max_bas_dd", new=AsyncMock(return_value=stale_dd)), \
            patch("src.api.condition.fetch_daily_candles", new=fetch_kis):
        out = await smd.get_recent_daily_normalized("005930", 22, min_required=22)

    assert fetch_kis.await_count == 1, "신선도 초과 → KIS 폴백."
    assert out == kis_rows


@pytest.mark.asyncio
async def test_normalized_insufficient_forces_kis_fallback():
    """min_required 게이트 — DB len < min_required → KIS 폴백 (사이클 172)."""
    from src.db import stock_master_daily as smd

    db_rows = [_daily_row(date(2026, 6, 20) - timedelta(days=i), close=71000, high=71500, low=70000)
               for i in range(5)]  # 부족
    kis_rows = [{"stck_bsop_date": "x", "stck_clpr": "1"} for _ in range(22)]
    fetch_kis = AsyncMock(return_value=kis_rows)
    with patch.object(smd, "get_recent_daily", new=AsyncMock(return_value=db_rows)), \
            patch.object(smd, "max_bas_dd", new=AsyncMock(return_value=date.today() - timedelta(days=1))), \
            patch("src.api.condition.fetch_daily_candles", new=fetch_kis):
        out = await smd.get_recent_daily_normalized("005930", 22, min_required=22)

    assert fetch_kis.await_count == 1, "DB 부족 → KIS 폴백."
    assert out == kis_rows


# ===========================================================================
# purge_old_rows — ⚠️ 날짜 슬라이스 루프 + SELECT/DELETE 양쪽 protected 제외 (never-drain P-3)
# ===========================================================================
@pytest.mark.asyncio
async def test_purge_date_slice_loop_deletes_and_drains():
    """purge_old_rows → SELECT oldest bas_dd → 날짜별 DELETE 루프 → drained break. deleted 누적."""
    from src.db import stock_master_daily as smd

    with patch.object(smd, "pg", create=True) as pg_mod:
        # SELECT: 2일치 oldest → 2회, 3회째 drained(빈 결과)
        pg_mod.fetchrow = AsyncMock(side_effect=[
            {"bas_dd": "2025-01-01"},
            {"bas_dd": "2025-01-02"},
            None,  # drained
        ])
        pg_mod.fetch = AsyncMock(side_effect=[
            [{"bas_dd": "2025-01-01"}],
            [{"bas_dd": "2025-01-02"}],
            [],  # drained
        ])
        # DELETE: 각 날짜 "DELETE N"
        pg_mod.execute = AsyncMock(side_effect=["DELETE 3000", "DELETE 3500"])
        out = await smd.purge_old_rows(date(2025, 6, 1))

    assert out["deleted"] == 6500, "날짜별 DELETE affected 누적 (3000+3500, 'DELETE N' 파싱)."
    # DELETE SQL 은 특정 날짜 eq
    del_sql = pg_mod.execute.await_args_list[0].args[0].lower()
    assert "delete" in del_sql and "bas_dd" in del_sql, "날짜별 DELETE (bas_dd eq) 누락."


@pytest.mark.asyncio
async def test_purge_select_and_delete_both_exclude_protected():
    """⚠️ never-drain P-3 — SELECT/DELETE 양쪽 protected ticker 제외 (SELECT 누락 = never-drain 회귀)."""
    from src.db import stock_master_daily as smd

    protected = {"005930", "000660"}
    with patch.object(smd, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(side_effect=[{"bas_dd": "2025-01-01"}, None])
        pg_mod.fetch = AsyncMock(side_effect=[[{"bas_dd": "2025-01-01"}], []])
        pg_mod.execute = AsyncMock(return_value="DELETE 100")
        await smd.purge_old_rows(date(2025, 6, 1), protected_tickers=protected)

    # SELECT (oldest bas_dd) — protected 제외 절대 필수 (누락 = never-drain)
    select_call = pg_mod.fetchrow.await_args_list[0] if pg_mod.fetchrow.await_args_list else pg_mod.fetch.await_args_list[0]
    select_sql = select_call.args[0].lower()
    select_args = select_call.args[1:]
    assert ("!= all" in select_sql or "not (" in select_sql or "any(" in select_sql
            or "ticker" in select_sql), "SELECT 쪽 protected 제외 절 누락 (never-drain P-3)."
    protected_in_select = any(
        isinstance(a, (list, tuple)) and set(protected).issubset(set(a)) for a in select_args
    )
    assert protected_in_select, (
        "SELECT oldest bas_dd 쿼리에 protected 배열 바인딩 누락 = never-drain 회귀 (P-3 HIGH)."
    )
    # DELETE 쪽도 protected 제외
    delete_args = pg_mod.execute.await_args.args[1:]
    protected_in_delete = any(
        isinstance(a, (list, tuple)) and set(protected).issubset(set(a)) for a in delete_args
    )
    assert protected_in_delete, "DELETE 쪽 protected 제외 배열 바인딩 누락 (사이클 32 R4)."


@pytest.mark.asyncio
async def test_purge_not_via_with_retry():
    """purge_old_rows 는 SELECT/DELETE 모두 _with_retry 미경유 (G-187-A2 쓰기 함수 멱등 보수)."""
    from src.db import stock_master_daily as smd

    with patch.object(smd, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value=None)
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.execute = AsyncMock(return_value="DELETE 0")
        pg_mod._with_retry = AsyncMock()
        await smd.purge_old_rows(date(2025, 6, 1))

    assert pg_mod._with_retry.await_count == 0, (
        "purge SELECT/DELETE 모두 _with_retry 미경유 (사이클 192 G-187-A2 불변식 계승)."
    )


@pytest.mark.asyncio
async def test_purge_retention_days_constant_unchanged():
    """DAILY_RETENTION_DAYS=230 불변 (사이클 172/196, purge 로직 상수만)."""
    from src.db import stock_master_daily as smd

    assert smd.DAILY_RETENTION_DAYS == 230, "retention 230 불변 (전환 무관)."


# ===========================================================================
# count_all / count_by_ticker / max_bas_dd — count(*) fetchval
# ===========================================================================
@pytest.mark.asyncio
async def test_count_all_via_fetchval():
    """count_all → count(*) fetchval, 예외 → 0 graceful."""
    from src.db import stock_master_daily as smd

    with patch.object(smd, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=430000)
        assert await smd.count_all() == 430000

    with patch.object(smd, "pg", create=True) as pg_mod2:
        pg_mod2.fetchval = AsyncMock(side_effect=Exception("boom"))
        assert await smd.count_all() == 0, "예외 → 0 graceful."


@pytest.mark.asyncio
async def test_max_bas_dd_ticker_none_and_specified():
    """max_bas_dd — ticker None(전체 MAX) / 지정 2분기. 미존재 → None."""
    from src.db import stock_master_daily as smd

    with patch.object(smd, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=date(2026, 7, 16))
        got_all = await smd.max_bas_dd(None)
        got_one = await smd.max_bas_dd("005930")

    assert got_all == date(2026, 7, 16) and got_one == date(2026, 7, 16), "MAX(bas_dd) date 반환."
    # ticker 지정 시 바인딩
    specified_call = pg_mod.fetchval.await_args_list[1]
    assert "005930" in specified_call.args[1:], "ticker 지정 분기 바인딩 누락."


# ===========================================================================
# 계약 보존 불변식 — supabase 미참조 (pg 단독)
# ===========================================================================
def test_stock_master_daily_no_supabase_reference_after_transition():
    """전환 후 stock_master_daily.py 는 supabase / execute_with_retry 미참조 (pg 단독)."""
    from src.db import stock_master_daily as smd

    assert not hasattr(smd, "supabase"), "전환 후 supabase 심볼 잔존 금지 (pg 단독)."
    assert not hasattr(smd, "execute_with_retry"), (
        "supabase execute_with_retry 심볼 잔존 금지 (pg._with_retry 로 대체)."
    )
    assert hasattr(smd, "pg"), "stock_master_daily 가 src.db.pg 를 import 해야 함."
