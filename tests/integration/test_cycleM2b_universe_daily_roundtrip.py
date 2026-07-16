"""사이클 M2b (Red) — stock_master / stock_master_daily 실 Postgres 왕복 (매수 유니버스 + 일봉).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 2 — 매매 hot path, HIGH).

mock 단위로 못 잡는 **실 SQL · 생성컬럼(migration 039) 계산 · JSONB raw 왕복 · 복합키 upsert ·
날짜슬라이스 purge protected 보존** 안전망. docker/DATABASE_URL_TEST 없으면 pg_harness fixture skip.

⚠️ 핵심:
1. **생성컬럼 필터** — raw.hts_avls 문자열 → DB 가 hts_avls_eok(억원) STORED 계산 → gte 임계 정확 반환.
2. **is_kospi200 ∪ is_kosdaq150 합집합** — 사이클 153 donchian 의무.
3. **return_stage_counts 3단계** — union/mcap/trade attrition (매수 풀 = trade 정합, G-A-1).
4. **purge 날짜슬라이스 protected 보존** — never-drain 방지 (P-3).

Red 유효성: production(2 모듈)이 아직 pg 미사용(supabase 호출) → 실 PG 왕복 경로 없음 → 전부 FAIL/에러.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def _insert_master(pg, ticker, *, name="종목", excg="02", nxt=True,
                         kospi200=False, kosdaq150=False, hts_avls="10000",
                         acml_tr_pbmn="50000000000"):
    """stock_master INSERT — raw 만 넣고 생성컬럼(hts_avls_eok/acml_tr_pbmn_won)은 DB 계산."""
    await pg.execute(
        """
        INSERT INTO stock_master (ticker, name, excg_dvsn_cd, nxt_tradable,
                                  is_kospi200, is_kosdaq150, raw, refreshed_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
        ON CONFLICT (ticker) DO UPDATE SET raw = EXCLUDED.raw
        """,
        ticker, name, excg, nxt, kospi200, kosdaq150,
        {"hts_avls": hts_avls, "acml_tr_pbmn": acml_tr_pbmn},
        datetime.fromisoformat("2026-07-16T16:00:00+09:00"),
    )


# ===========================================================================
# list_by_filter — ⚠️ 생성컬럼 필터 (raw 문자열 → DB STORED 계산 → gte)
# ===========================================================================
@pytest.mark.asyncio
async def test_list_by_filter_generated_column_threshold(clean_stock_master):
    """⚠️ 시총 임계 정확 반환 — raw.hts_avls 문자열 → hts_avls_eok(억원) STORED → gte 필터.

    codec/생성컬럼 미작동 시 필터 무력화 → 매수 유니버스 왜곡. 1,000억(=10000억원 이상만) 통과.
    """
    from src.db import stock_master

    # 5,000억(hts_avls=5000 억원) < 1조(=10000) → 시총컷 1,000억(hts_avls_eok>=1000) 통과
    await _insert_master(clean_stock_master, "005930", hts_avls="10000")  # 1조
    await _insert_master(clean_stock_master, "000660", hts_avls="5000")   # 5,000억
    await _insert_master(clean_stock_master, "111111", hts_avls="500")    # 500억 (컷 미달)

    # min_market_cap 1,000억 (원) → hts_avls_eok >= 1000
    out = await stock_master.list_by_filter(min_market_cap=100_000_000_000)
    tickers = {r["ticker"] for r in out}

    assert "005930" in tickers and "000660" in tickers, "시총 1,000억 이상 종목 반환 (생성컬럼 gte)."
    assert "111111" not in tickers, "500억 종목은 시총컷 제외 (생성컬럼 hts_avls_eok gte)."


@pytest.mark.asyncio
async def test_list_by_filter_trade_amount_threshold(clean_stock_master):
    """거래대금 임계 — acml_tr_pbmn_won gte 정확."""
    from src.db import stock_master

    await _insert_master(clean_stock_master, "005930", acml_tr_pbmn="50000000000")  # 500억
    await _insert_master(clean_stock_master, "222222", acml_tr_pbmn="1000000000")   # 10억 (컷 미달)

    out = await stock_master.list_by_filter(min_trade_amount=20_000_000_000)  # 200억
    tickers = {r["ticker"] for r in out}
    assert "005930" in tickers and "222222" not in tickers, "거래대금 200억 gte 정확 (생성컬럼)."


@pytest.mark.asyncio
async def test_list_by_filter_kospi200_kosdaq150_union(clean_stock_master):
    """⚠️ is_kospi200 ∪ is_kosdaq150 OR 합집합 (사이클 153 donchian 의무)."""
    from src.db import stock_master

    await _insert_master(clean_stock_master, "005930", kospi200=True, kosdaq150=False)
    await _insert_master(clean_stock_master, "035720", kospi200=False, kosdaq150=True)
    await _insert_master(clean_stock_master, "999999", kospi200=False, kosdaq150=False)

    out = await stock_master.list_by_filter(is_kospi200=True, is_kosdaq150=True)
    tickers = {r["ticker"] for r in out}
    assert tickers == {"005930", "035720"}, (
        "OR 합집합 = KOSPI200 ∪ KOSDAQ150 (999999 제외). AND 였다면 공집합 = donchian 유니버스 붕괴."
    )


@pytest.mark.asyncio
async def test_list_by_filter_return_stage_counts_attrition(clean_stock_master):
    """⚠️ return_stage_counts 3단계 attrition + 최종 filtered == trade (G-A-1 매수 풀 불변)."""
    from src.db import stock_master

    # union 3 (전부) / 시총컷 후 2 / 거래대금컷 후 1
    await _insert_master(clean_stock_master, "005930", hts_avls="10000", acml_tr_pbmn="50000000000")  # 통과
    await _insert_master(clean_stock_master, "000660", hts_avls="10000", acml_tr_pbmn="1000000000")   # 시총O 거래X
    await _insert_master(clean_stock_master, "111111", hts_avls="100", acml_tr_pbmn="1000000000")     # 둘 다 X

    filtered, stage = await stock_master.list_by_filter(
        min_market_cap=100_000_000_000,   # hts_avls_eok >= 1000
        min_trade_amount=20_000_000_000,  # acml_tr_pbmn_won >= 20e9
        return_stage_counts=True,
    )
    assert len(stage["union_tickers"]) == 3, "union = 시총/거래대금 gte 전 (전체 3)."
    assert set(stage["mcap_tickers"]) == {"005930", "000660"}, "mcap = 시총컷 후 (2)."
    assert stage["trade_tickers"] == ["005930"], "trade = 거래대금컷 후 (1)."
    # ⚠️ G-A-1 — 최종 filtered == trade 단계 (매수 풀 불변)
    assert [r["ticker"] for r in filtered] == ["005930"], "filtered == trade 단계 (매수 풀 원소 불변, G-A-1)."


@pytest.mark.asyncio
async def test_list_by_filter_raw_jsonb_roundtrip(clean_stock_master):
    """반환 dict raw 는 dict (JSONB codec 왕복). str 이면 codec 미작동 → 소비처 파싱 결함."""
    from src.db import stock_master

    await _insert_master(clean_stock_master, "005930", hts_avls="12345")
    out = await stock_master.list_by_filter()
    assert isinstance(out[0]["raw"], dict), "raw JSONB → dict codec 왕복."
    assert out[0]["raw"]["hts_avls"] == "12345"


# ===========================================================================
# get_stats — 4카운트 정확 (asyncpg count, PostgREST 1000 cap 무관)
# ===========================================================================
@pytest.mark.asyncio
async def test_get_stats_four_counts_accurate(clean_stock_master):
    """get_stats count_all / nxt_tradable_count / bfdy_clpr_present 정확 (count(*), cap 무관)."""
    from src.db import stock_master

    # bfdy_clpr 있는 종목 2 + nxt True 3
    for i in range(3):
        await clean_stock_master.execute(
            """
            INSERT INTO stock_master (ticker, name, excg_dvsn_cd, nxt_tradable, raw, refreshed_at)
            VALUES ($1, $2, '02', true, $3::jsonb, $4)
            """,
            f"00000{i}", f"종목{i}",
            {"bfdy_clpr": "70000"} if i < 2 else {"bfdy_clpr": "0"},
            datetime.fromisoformat("2026-07-16T16:00:00+09:00"),
        )

    stats = await stock_master.get_stats()
    assert stats["count_all"] == 3, "count_all = 3 (count(*) 정확)."
    assert stats["nxt_tradable_count"] == 3, "nxt_tradable_count = 3."
    assert stats["bfdy_clpr_present"] == 2, (
        "bfdy_clpr_present = 2 (raw->>'bfdy_clpr' non-null AND <>'0'). '0' 종목 제외."
    )


# ===========================================================================
# stock_master_daily — upsert_batch 100 chunk + get_atr/donchian + purge
# ===========================================================================
@pytest.mark.asyncio
async def test_upsert_batch_100_chunk_roundtrip(clean_stock_master_daily):
    """upsert_batch 250건 → 100 chunk 왕복 → count_by_ticker=250. 복합키 (ticker,bas_dd)."""
    from src.db import stock_master_daily as smd

    candles = [
        {"stck_bsop_date": (date(2025, 1, 1) + timedelta(days=i)).strftime("%Y%m%d"),
         "stck_oprc": str(70000 + i), "stck_hgpr": str(70500 + i),
         "stck_lwpr": str(69500 + i), "stck_clpr": str(70000 + i),
         "acml_vol": "1000000", "acml_tr_pbmn": "70000000000", "prdy_ctrt": "0.5"}
        for i in range(250)
    ]
    total = await smd.upsert_batch("005930", candles)
    assert total == 250, "250건 upsert (100 chunk 3회)."

    cnt = await smd.count_by_ticker("005930")
    assert cnt == 250, "복합키 (ticker,bas_dd) 왕복 250행."


@pytest.mark.asyncio
async def test_get_donchian_high_and_atr_roundtrip(clean_stock_master_daily):
    """upsert 후 get_donchian_high(max high) + get_atr(양수) 실 데이터 계산 정합."""
    from src.db import stock_master_daily as smd

    candles = [
        {"stck_bsop_date": "20260601", "stck_oprc": "70000", "stck_hgpr": "72000",
         "stck_lwpr": "69000", "stck_clpr": "71000", "acml_vol": "1", "acml_tr_pbmn": "1", "prdy_ctrt": "0"},
        {"stck_bsop_date": "20260602", "stck_oprc": "71000", "stck_hgpr": "73500",
         "stck_lwpr": "70000", "stck_clpr": "72500", "acml_vol": "1", "acml_tr_pbmn": "1", "prdy_ctrt": "0"},
        {"stck_bsop_date": "20260603", "stck_oprc": "72000", "stck_hgpr": "72800",
         "stck_lwpr": "71000", "stck_clpr": "72000", "acml_vol": "1", "acml_tr_pbmn": "1", "prdy_ctrt": "0"},
    ]
    await smd.upsert_batch("005930", candles)

    high = await smd.get_donchian_high("005930", 20)
    assert high == 73500, "신고가 = max(high_price) 실 데이터 계산."

    atr = await smd.get_atr("005930", 14)
    assert atr is not None and atr > 0, "ATR True Range 평균 (양수)."


@pytest.mark.asyncio
async def test_purge_date_slice_protected_preserved(clean_stock_master_daily):
    """⚠️ purge 날짜슬라이스 — protected ticker 는 cutoff 이전이어도 보존 (never-drain P-3 + 사이클 32 R4)."""
    from src.db import stock_master_daily as smd

    old_dd = "20200101"  # cutoff 훨씬 이전
    # 일반 종목 + 보유(protected) 종목 모두 old
    for tk in ("005930", "000660"):
        await smd.upsert_batch(tk, [{
            "stck_bsop_date": old_dd, "stck_oprc": "70000", "stck_hgpr": "70500",
            "stck_lwpr": "69500", "stck_clpr": "70000", "acml_vol": "1",
            "acml_tr_pbmn": "1", "prdy_ctrt": "0",
        }])

    # 000660 은 보유 → protected
    out = await smd.purge_old_rows(date(2025, 6, 1), protected_tickers={"000660"})
    assert out["deleted"] >= 1, "일반 종목(005930) old 행 삭제."

    # 005930 삭제됨 / 000660 보존
    remain_005930 = await smd.count_by_ticker("005930")
    remain_000660 = await smd.count_by_ticker("000660")
    assert remain_005930 == 0, "일반 종목 old 행 purge."
    assert remain_000660 == 1, (
        "protected(보유) 종목은 cutoff 이전이어도 보존 (never-drain P-3 + 사이클 32 R4)."
    )


@pytest.mark.asyncio
async def test_get_recent_daily_normalized_returns_raw_jsonb(clean_stock_master_daily):
    """정상 데이터 → get_recent_daily_normalized 가 raw JSONB(KIS 원본 키 stck_clpr) 반환.

    신선도 게이트 통과 위해 최근 날짜로 적재. 락 없음(flng="00").
    """
    from src.db import stock_master_daily as smd
    from src.db._kst import today_kst

    base = today_kst()
    candles = [{
        "stck_bsop_date": (base - timedelta(days=i)).strftime("%Y%m%d"),
        "stck_oprc": str(70000 - i * 10), "stck_hgpr": str(70500 - i * 10),
        "stck_lwpr": str(69500 - i * 10), "stck_clpr": str(70000 - i * 10),
        "acml_vol": "1", "acml_tr_pbmn": "1", "prdy_ctrt": "0",
        "flng_cls_code": "00", "prtt_rate": "0.0000",
    } for i in range(25)]
    await smd.upsert_batch("005930", candles)

    out = await smd.get_recent_daily_normalized("005930", 22, min_required=22)
    assert len(out) >= 22, "충분/신선/락없음 → DB raw 반환."
    assert all("stck_clpr" in r for r in out), "raw JSONB KIS 원본 키 보존 (사이클 81)."
