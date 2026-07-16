"""사이클 M2b (Red) — src/db/stock_master.py asyncpg 전환 계약 가드 (매수 유니버스 hot path).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 2 — 매매 hot path, HIGH).

현행 stock_master.py = supabase-py 체인 + `execute_with_retry`(사이클 189). 이 증분 = `pg.*` 전환.
**함수 계약(시그니처·반환형·graceful) 100% 보존** → 호출부(scanner/strategies) diff 0.

⚠️ 최대 위험 (매수 유니버스 hot path):
1. **list_by_filter 결과 원소·순서·limit 불변** — 생성컬럼 gte(사이클205) + is_kospi200∪is_kosdaq150
   OR 합집합(사이클153) + return_stage_counts 3쿼리(사이클170/205). trade == 최종 filtered (G-A-1).
2. **JSONB raw 왕복** — codec 이 raw dict 복원 → 반환 dict `raw` 키 dict.
3. **get_stats 4카운트** — jsonb 존재성 text path (raw->>'키' non-null AND <>'0' AND <>'').

Red 유효성: production 미변경 → pg mock 미발화(모듈이 supabase 호출) → 계약 단언 FAIL.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _row(
    ticker: str,
    *,
    name: str = "테스트종목",
    excg_dvsn_cd: str = "02",
    nxt_tradable: bool = True,
    is_kospi200: bool = False,
    is_kosdaq150: bool = False,
    raw: dict | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": excg_dvsn_cd,
        "nxt_tradable": nxt_tradable,
        "is_kospi200": is_kospi200,
        "is_kosdaq150": is_kosdaq150,
        "raw": raw if raw is not None else {"hts_avls": "10000", "acml_tr_pbmn": "50000000000"},
    }


# ===========================================================================
# list_by_filter — ⚠️ 매수 유니버스 hot path (생성컬럼 gte + 합집합 + 3쿼리)
# ===========================================================================
@pytest.mark.asyncio
async def test_list_by_filter_reads_via_pg_fetch():
    """list_by_filter → pg.fetch (읽기 경로). stock_master SELECT."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[_row("005930"), _row("000660")])
        out = await stock_master.list_by_filter(limit=500)

    assert isinstance(out, list), "return_stage_counts=False → list 계약."
    assert [r["ticker"] for r in out] == ["005930", "000660"], "필터 결과 원소·순서 보존."
    sql = pg_mod.fetch.await_args.args[0]
    assert "stock_master" in sql and "SELECT" in sql.upper(), "stock_master SELECT 누락."


@pytest.mark.asyncio
async def test_list_by_filter_generated_column_gte_thresholds():
    """⚠️ min_market_cap>0 → hts_avls_eok gte ceil(mc/1e8) / min_trade_amount → acml_tr_pbmn_won gte.

    사이클 205 DB-side 생성컬럼 필터. Python-side raw 파싱 폐지 → SQL 에 생성컬럼 gte 등장.
    """
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        # 1,000억 (원) → hts_avls_eok gte 1000 (억원), 거래대금 200억 (원)
        await stock_master.list_by_filter(min_market_cap=100_000_000_000, min_trade_amount=20_000_000_000)

    sql = pg_mod.fetch.await_args.args[0].lower()
    args = pg_mod.fetch.await_args.args[1:]
    assert "hts_avls_eok" in sql, "생성컬럼 hts_avls_eok gte 누락 (사이클 205 DB-side 필터)."
    assert "acml_tr_pbmn_won" in sql, "생성컬럼 acml_tr_pbmn_won gte 누락."
    # 임계값 바인딩: 1,000억 원 / 1e8 = 1000 억원, 거래대금 200억 원 그대로
    assert 1000 in args, "hts_avls_eok 임계 ceil(min_market_cap/1e8)=1000 바인딩 누락."
    assert 20_000_000_000 in args, "acml_tr_pbmn_won 임계=min_trade_amount 바인딩 누락."


@pytest.mark.asyncio
async def test_list_by_filter_kospi200_kosdaq150_union_or():
    """⚠️ is_kospi200=True + is_kosdaq150=True → OR 합집합 (사이클 153 donchian 의무)."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await stock_master.list_by_filter(is_kospi200=True, is_kosdaq150=True)

    sql = pg_mod.fetch.await_args.args[0].lower()
    assert "is_kospi200" in sql and "is_kosdaq150" in sql, "지수 플래그 필터 누락."
    assert " or " in sql, (
        "is_kospi200 ∪ is_kosdaq150 = OR 합집합 (사이클 153 FUNNEL_STAGES[0] '코스피200+코스닥150 합집합')."
    )


@pytest.mark.asyncio
async def test_list_by_filter_kospi200_single_and():
    """is_kospi200=True 단독 → AND (.eq 단일 필터, OR 아님)."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        await stock_master.list_by_filter(is_kospi200=True)

    sql = pg_mod.fetch.await_args.args[0].lower()
    assert "is_kospi200" in sql, "is_kospi200 단독 필터 누락."
    assert " or " not in sql, "단독 지정은 OR 합집합 아님 (AND 단일 필터)."


@pytest.mark.asyncio
async def test_list_by_filter_exclude_tickers_and_limit():
    """exclude_tickers 제외 + limit 절단 계약 보존."""
    from src.db import stock_master

    rows = [_row("005930"), _row("000660"), _row("035720")]
    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=rows)
        out = await stock_master.list_by_filter(exclude_tickers=["000660"], limit=2)

    tickers = [r["ticker"] for r in out]
    assert "000660" not in tickers, "exclude_tickers 제외 계약."
    assert len(out) <= 2, "limit 절단 계약."


@pytest.mark.asyncio
async def test_list_by_filter_return_stage_counts_three_queries():
    """⚠️ return_stage_counts=True → (filtered, stage 3키) 튜플. 3쿼리 union/mcap/trade (사이클 205)."""
    from src.db import stock_master

    union_rows = [_row("005930"), _row("000660"), _row("035720")]
    mcap_rows = [_row("005930"), _row("000660")]
    trade_rows = [_row("005930")]

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        # 3쿼리 순차 반환 (union → mcap → trade)
        pg_mod.fetch = AsyncMock(side_effect=[union_rows, mcap_rows, trade_rows])
        result = await stock_master.list_by_filter(
            min_market_cap=100_000_000_000,
            min_trade_amount=20_000_000_000,
            return_stage_counts=True,
        )

    assert isinstance(result, tuple) and len(result) == 2, "return_stage_counts=True → (filtered, stage) 튜플."
    filtered, stage = result
    assert pg_mod.fetch.await_count == 3, "사이클 205 = union/mcap/trade 3쿼리."
    assert stage["union_tickers"] == ["005930", "000660", "035720"], "union 단계 = 시총/거래대금 gte 전."
    assert stage["mcap_tickers"] == ["005930", "000660"], "mcap 단계 = 시총 gte 후."
    assert stage["trade_tickers"] == ["005930"], "trade 단계 = 거래대금 gte 후."
    # ⚠️ G-A-1 HIGH — 최종 filtered == trade 단계 (매수 풀 불변)
    assert [r["ticker"] for r in filtered] == ["005930"], (
        "return_stage_counts=True 의 filtered == trade 단계 (매수 풀 원소·순서 불변, G-A-1)."
    )


@pytest.mark.asyncio
async def test_list_by_filter_stage_counts_matches_plain_filtered():
    """⚠️ G-A-1: return_stage_counts=True filtered 와 False 결과가 동일 원소·순서 (매수 풀 불변)."""
    from src.db import stock_master

    final_rows = [_row("005930"), _row("000660")]

    # plain (False)
    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=final_rows)
        plain = await stock_master.list_by_filter(min_market_cap=100_000_000_000)

    # stage (True) — trade 쿼리가 동일 final_rows 반환
    with patch.object(stock_master, "pg", create=True) as pg_mod2:
        pg_mod2.fetch = AsyncMock(side_effect=[final_rows, final_rows, final_rows])
        stage_filtered, _ = await stock_master.list_by_filter(
            min_market_cap=100_000_000_000, return_stage_counts=True
        )

    assert [r["ticker"] for r in plain] == [r["ticker"] for r in stage_filtered], (
        "return_stage_counts 여부와 무관하게 매수 풀(최종 filtered) 원소·순서 동일 (G-A-1 HIGH)."
    )


@pytest.mark.asyncio
async def test_list_by_filter_returns_raw_dict_jsonb_codec():
    """JSONB raw 왕복 — 반환 dict 의 raw 키가 dict (codec 복원). 미작동 시 str → 소비처 파싱 결함."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[_row("005930", raw={"hts_avls": "12345"})])
        out = await stock_master.list_by_filter()

    assert isinstance(out[0]["raw"], dict), "raw 는 dict (JSONB codec 복원). str 이면 codec 미작동."
    assert out[0]["raw"]["hts_avls"] == "12345"


# ===========================================================================
# get_stats — 4 카운트 (jsonb 존재성 text path) + top_10_recent
# ===========================================================================
@pytest.mark.asyncio
async def test_get_stats_four_counts_via_fetchval():
    """get_stats 4카운트 = 각 fetchval("SELECT count(*) ...") (사이클 128 silent cap 회피)."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        # count_all / nxt / bfdy / hts_avls / acml_tr_pbmn 순 (구현 자유도 — 5회 이상 count)
        pg_mod.fetchval = AsyncMock(side_effect=[3000, 400, 2500, 1734, 366])
        pg_mod.fetch = AsyncMock(return_value=[
            {"ticker": "005930", "name": "삼성전자", "refreshed_at": "2026-07-16T16:00:00+09:00"},
        ])
        # stock_master_daily 연동 (count_all/max_bas_dd) graceful
        with patch("src.db.stock_master_daily.count_all", new=AsyncMock(return_value=100)), \
                patch("src.db.stock_master_daily.max_bas_dd", new=AsyncMock(return_value=None)):
            stats = await stock_master.get_stats()

    assert stats["count_all"] == 3000, "count_all = count(*) fetchval."
    assert stats["nxt_tradable_count"] == 400, "nxt_tradable_count = eq 필터 count."
    assert pg_mod.fetchval.await_count >= 4, "4카운트 모두 count(*) 별도 SELECT (사이클 128)."
    # count SQL 은 count(*) 형태
    count_sqls = [c.args[0].lower() for c in pg_mod.fetchval.await_args_list]
    assert all("count(" in s for s in count_sqls), "카운트는 count(*) SELECT."


@pytest.mark.asyncio
async def test_get_stats_jsonb_presence_text_path():
    """bfdy_clpr_present/with_hts_avls/with_acml_tr_pbmn = raw->>'키' 존재성 (non-null AND <>'0' AND <>'')."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=0)
        pg_mod.fetch = AsyncMock(return_value=[])
        with patch("src.db.stock_master_daily.count_all", new=AsyncMock(return_value=0)), \
                patch("src.db.stock_master_daily.max_bas_dd", new=AsyncMock(return_value=None)):
            await stock_master.get_stats()

    joined = " ".join(c.args[0].lower() for c in pg_mod.fetchval.await_args_list)
    assert "raw->>'bfdy_clpr'" in joined or "raw->>bfdy_clpr" in joined, (
        "bfdy_clpr 존재성은 raw->>'키' text path (사이클 128 — jsonb text 존재성)."
    )
    assert "hts_avls" in joined and "acml_tr_pbmn" in joined, "hts_avls/acml_tr_pbmn 존재성 카운트 누락."


# ===========================================================================
# list_paged_by_filter — UI 페이징 (생성컬럼 gte + name ilike + count + range)
# ===========================================================================
@pytest.mark.asyncio
async def test_list_paged_by_filter_count_and_range():
    """list_paged_by_filter → items + total(count(*)) + limit/offset. range → LIMIT/OFFSET."""
    from src.db import stock_master

    items = [_row("005930"), _row("000660")]
    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=items)
        pg_mod.fetchval = AsyncMock(return_value=57)
        out = await stock_master.list_paged_by_filter(limit=50, offset=0)

    assert out["items"] == items and out["total"] == 57, "items + total 계약."
    assert out["limit"] == 50 and out["offset"] == 0
    count_sql = pg_mod.fetchval.await_args.args[0].lower()
    assert "count(" in count_sql, "total = count(*) 별도 SELECT."
    data_sql = pg_mod.fetch.await_args.args[0].upper()
    assert "LIMIT" in data_sql and "OFFSET" in data_sql, "range → LIMIT/OFFSET 누락."


@pytest.mark.asyncio
async def test_list_paged_by_filter_generated_col_and_name_ilike():
    """min_market_cap → hts_avls_eok gte / name_substr → ILIKE (사이클 168)."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.fetchval = AsyncMock(return_value=0)
        await stock_master.list_paged_by_filter(
            min_market_cap=100_000_000_000, name_substr="삼성",
        )

    sql = pg_mod.fetch.await_args.args[0].lower()
    args = pg_mod.fetch.await_args.args[1:]
    assert "hts_avls_eok" in sql, "생성컬럼 gte 누락."
    assert "ilike" in sql, "name_substr → ILIKE 누락."
    assert any(isinstance(a, str) and "삼성" in a for a in args), "name 패턴 %삼성% 바인딩 누락."


# ===========================================================================
# upsert_one / get / is_stale
# ===========================================================================
@pytest.mark.asyncio
async def test_upsert_one_pg_execute_conflict_ticker():
    """upsert_one → pg.execute INSERT ON CONFLICT (ticker). raw dict + refreshed_at datetime 바인딩."""
    from src.db import stock_master
    from src.models.stock import StockBasics

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await stock_master.upsert_one(StockBasics(ticker="005930", name="삼성전자", raw={"hts_avls": "10000"}))

    sql = pg_mod.execute.await_args.args[0]
    assert "INSERT INTO stock_master" in sql, "INSERT INTO stock_master 누락."
    assert "ON CONFLICT (ticker) DO UPDATE" in sql, "ticker PK upsert 누락."
    args = pg_mod.execute.await_args.args[1:]
    assert "005930" in args, "ticker 바인딩 누락."
    assert any(isinstance(a, dict) and a.get("hts_avls") == "10000" for a in args), (
        "raw JSONB dict 직접 바인딩 (json.dumps 사전 적용 금지, codec 전담)."
    )
    assert any(isinstance(a, datetime) for a in args), "refreshed_at datetime 바인딩 (str 금지)."


@pytest.mark.asyncio
async def test_upsert_one_normalizes_non_6digit_ticker():
    """비6자리 ticker → _normalize_ticker 정규화 후 저장 (PK 정합, 사이클 G2)."""
    from src.db import stock_master
    from src.models.stock import StockBasics

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        with patch("src.api.condition._normalize_ticker", return_value="000100"):
            await stock_master.upsert_one(StockBasics(ticker="00000A000100", name="유한양행"))

    args = pg_mod.execute.await_args.args[1:]
    assert "000100" in args and "00000A000100" not in args, (
        "비6자리 → _normalize_ticker 정규화 저장 (positions.ticker 6자리 PK 정합)."
    )


@pytest.mark.asyncio
async def test_get_returns_stockbasics_or_none():
    """get(ticker) → fetchrow → StockBasics. 미존재 → None."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={
            "ticker": "005930", "name": "삼성전자", "excg_dvsn_cd": "02",
            "nxt_tradable": True, "krx_halted": False, "admin_item": False, "raw": {},
        })
        got = await stock_master.get("005930")

    assert got is not None and got.ticker == "005930" and got.name == "삼성전자"

    with patch.object(stock_master, "pg", create=True) as pg_mod2:
        pg_mod2.fetchrow = AsyncMock(return_value=None)
        assert await stock_master.get("999999") is None, "미존재 → None."


@pytest.mark.asyncio
async def test_is_stale_missing_or_old_returns_true():
    """is_stale — 미존재/refreshed_at 부재/24h 초과 → True."""
    from src.db import stock_master

    # 미존재
    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        assert await stock_master.is_stale("005930") is True, "미존재 → stale True."

    # 24h 초과 (오래된 refreshed_at)
    with patch.object(stock_master, "pg", create=True) as pg_mod2:
        pg_mod2.fetch = AsyncMock(return_value=[{"refreshed_at": "2020-01-01T00:00:00+09:00"}])
        assert await stock_master.is_stale("005930") is True, "24h 초과 → stale True."


# ===========================================================================
# count_active / count_master_raw_today / master_raw
# ===========================================================================
@pytest.mark.asyncio
async def test_count_active_via_fetchval_graceful():
    """count_active → count(*) fetchval. 예외 → 0 graceful (사이클 88/163)."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchval = AsyncMock(return_value=3000)
        assert await stock_master.count_active() == 3000

    with patch.object(stock_master, "pg", create=True) as pg_mod2:
        pg_mod2.fetchval = AsyncMock(side_effect=Exception("boom"))
        assert await stock_master.count_active() == 0, "예외 → 0 graceful."


@pytest.mark.asyncio
async def test_upsert_master_raw_columns_and_kst():
    """upsert_master_raw → master_raw JSONB + is_kospi200/is_kosdaq150 컬럼 + master_raw_updated_at datetime + nxt_tradable=False."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.execute = AsyncMock(return_value="INSERT 0 1")
        await stock_master.upsert_master_raw(
            "005930", {"mksc_shrn_iscd": "005930"}, is_kospi200=True, is_kosdaq150=False,
        )

    sql = pg_mod.execute.await_args.args[0]
    assert "master_raw" in sql and "ON CONFLICT (ticker)" in sql, "master_raw upsert (ticker) 누락."
    args = pg_mod.execute.await_args.args[1:]
    assert any(isinstance(a, dict) and a.get("mksc_shrn_iscd") == "005930" for a in args), (
        "master_raw JSONB dict 직접 바인딩."
    )
    assert True in args, "is_kospi200=True 컬럼 바인딩 누락 (사이클 153)."
    assert any(isinstance(a, datetime) for a in args), "master_raw_updated_at datetime 바인딩 (사이클 68)."
    # 사이클 146 — 신규 ticker NOT NULL 이중 안전망 (nxt_tradable=False)
    assert False in args, "nxt_tradable=False 신규 INSERT 이중 안전망 보존 (사이클 146)."


@pytest.mark.asyncio
async def test_get_master_raw_returns_dict_jsonb():
    """get_master_raw → master_raw dict (JSONB codec). NULL/{} → None."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetchrow = AsyncMock(return_value={"master_raw": {"mksc_shrn_iscd": "005930"}})
        got = await stock_master.get_master_raw("005930")

    assert isinstance(got, dict) and got["mksc_shrn_iscd"] == "005930"

    with patch.object(stock_master, "pg", create=True) as pg_mod2:
        pg_mod2.fetchrow = AsyncMock(return_value=None)
        assert await stock_master.get_master_raw("999999") is None, "미존재 → None."


# ===========================================================================
# read _with_retry 경유 / 쓰기 미경유 (사이클 187/189 정책)
# ===========================================================================
@pytest.mark.asyncio
async def test_list_by_filter_read_uses_fetch():
    """list_by_filter read = pg.fetch 발화 (내부 _with_retry). 쓰기 미발화."""
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        pg_mod.execute = AsyncMock()
        await stock_master.list_by_filter()

    assert pg_mod.fetch.await_count >= 1, "read 경로 pg.fetch 발화 누락."
    assert pg_mod.execute.await_count == 0, "read 경로에서 execute(쓰기) 미발화."


# ===========================================================================
# 계약 보존 불변식 — supabase / execute_with_retry 미참조 (pg 단독)
# ===========================================================================
def test_stock_master_no_supabase_reference_after_transition():
    """전환 후 stock_master.py 는 supabase / execute_with_retry 미참조 (pg 단독)."""
    from src.db import stock_master

    assert not hasattr(stock_master, "supabase"), "전환 후 supabase 심볼 잔존 금지 (pg 단독)."
    assert not hasattr(stock_master, "execute_with_retry"), (
        "supabase execute_with_retry 심볼 잔존 금지 (pg._with_retry 로 대체)."
    )
    assert hasattr(stock_master, "pg"), "stock_master 가 src.db.pg 를 import 해야 함."
