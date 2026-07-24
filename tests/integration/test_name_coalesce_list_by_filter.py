"""Red (통합) — list_by_filter 종목명 COALESCE 폴백 실 Postgres 왕복.

배경 (스펙 `name_coalesce_fix_spec.md`):
전체상장 스캔(kojiro 등) funnel 후보가 종목명 없이 번호만 표시. 근본 원인 =
마스터파일 한글명이 `stock_master.master_raw["hts_kor_isnm"]` 에만 있고 `name`/`raw`
는 소형주에서 빈값이며 `list_by_filter` SELECT 가 master_raw 를 안 봄.

시정 = SELECT name 을
    COALESCE(NULLIF(name, ''), NULLIF(TRIM(master_raw->>'hts_kor_isnm'), ''), '') AS name
로 교체. mock 단위(T1)로 못 잡는 **실 SQL COALESCE/NULLIF/TRIM · JSONB text 추출
(master_raw->>) 왕복 · '' vs NULL 계약** 안전망.

패턴: test_cycleM2b_universe_daily_roundtrip.py 답습 (clean_stock_master 시드 +
list_by_filter 실 조회). docker/DATABASE_URL_TEST 없으면 pg_harness fixture skip
(로컬 DB 부재 시 skip 이 정상 — CI postgres:15 에서 실행).

필터 통과 위해 min_market_cap=0/min_trade_amount=0 (생성컬럼 gte 없이 전체 반환).

Red 유효성: production SELECT 미변경 → master_raw 폴백 부재 → name='' 인 행이
'' 그대로 반환 → T2-b/T2-c 단언(마스터 한글명/TRIM) FAIL.
"""

from __future__ import annotations

from datetime import datetime

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def _insert_master(pg, ticker, *, name, master_raw, excg="02", nxt=True):
    """stock_master INSERT — name 컬럼 + master_raw JSONB 명시 시드.

    raw 는 필터 무관하게 기본값 유지(생성컬럼은 min=0 이라 gte 미적용). master_raw 가
    종목명 폴백 원천(hts_kor_isnm)이므로 케이스별로 명시 주입.
    """
    await pg.execute(
        """
        INSERT INTO stock_master (ticker, name, excg_dvsn_cd, nxt_tradable,
                                  is_kospi200, is_kosdaq150, raw, master_raw, refreshed_at)
        VALUES ($1, $2, $3, $4, false, false, $5::jsonb, $6::jsonb, $7)
        ON CONFLICT (ticker) DO UPDATE
            SET name = EXCLUDED.name, master_raw = EXCLUDED.master_raw
        """,
        ticker, name, excg, nxt,
        {"hts_avls": "10000", "acml_tr_pbmn": "50000000000"},
        master_raw,
        datetime.fromisoformat("2026-07-16T16:00:00+09:00"),
    )


async def _name_of(ticker: str) -> str | None:
    from src.db import stock_master

    out = await stock_master.list_by_filter(min_market_cap=0, min_trade_amount=0)
    for r in out:
        if r["ticker"] == ticker:
            return r["name"]
    return None


# ===========================================================================
# T2-a — CTPF name 우선 (name 있으면 master_raw 무시)
# ===========================================================================
@pytest.mark.asyncio
async def test_t2a_ctpf_name_takes_priority(clean_stock_master):
    """name='삼성전자' + master_raw.hts_kor_isnm='X' → 반환 name=='삼성전자' (CTPF 우선)."""
    await _insert_master(
        clean_stock_master, "005930",
        name="삼성전자", master_raw={"hts_kor_isnm": "X"},
    )
    assert await _name_of("005930") == "삼성전자", (
        "name 컬럼(CTPF)이 비어있지 않으면 그대로 우선 (COALESCE 1순위)."
    )


# ===========================================================================
# T2-b — 마스터파일 폴백 (name 빈값 → master_raw 한글명)
# ===========================================================================
@pytest.mark.asyncio
async def test_t2b_master_raw_fallback_when_name_empty(clean_stock_master):
    """name='' + master_raw.hts_kor_isnm='SK하이닉스' → 반환 name=='SK하이닉스' (마스터 폴백)."""
    await _insert_master(
        clean_stock_master, "000660",
        name="", master_raw={"hts_kor_isnm": "SK하이닉스"},
    )
    assert await _name_of("000660") == "SK하이닉스", (
        "name 빈값 → master_raw->>'hts_kor_isnm' 폴백 (COALESCE 2순위). "
        "현행(폴백 부재)은 '' 반환 → FAIL (Red)."
    )


# ===========================================================================
# T2-c — 고정폭 패딩 TRIM
# ===========================================================================
@pytest.mark.asyncio
async def test_t2c_master_raw_trim_padding(clean_stock_master):
    """name='' + master_raw.hts_kor_isnm='  패딩  ' → 반환 name=='패딩' (TRIM)."""
    await _insert_master(
        clean_stock_master, "111111",
        name="", master_raw={"hts_kor_isnm": "  패딩  "},
    )
    assert await _name_of("111111") == "패딩", (
        "마스터 한글명은 고정폭 패딩 → TRIM(master_raw->>'hts_kor_isnm') 후 반환."
    )


# ===========================================================================
# T2-d — 둘 다 없으면 '' (NULL 반환 금지)
# ===========================================================================
@pytest.mark.asyncio
async def test_t2d_empty_string_when_both_missing(clean_stock_master):
    """name='' + master_raw 키 부재 → 반환 name=='' (None 아님, 소비자 '' 계약)."""
    await _insert_master(
        clean_stock_master, "222222",
        name="", master_raw={},
    )
    got = await _name_of("222222")
    assert got == "", (
        "name/master_raw 모두 없으면 '' 반환 (COALESCE 최종 인자 ''). "
        f"NULL/None 반환 금지 (row.get('name','') None 회귀 차단). 실제: {got!r}"
    )


# ===========================================================================
# T2-e (회귀) — mcap/trade 필터 + return_stage_counts 불변 (COALESCE 무영향)
# ===========================================================================
@pytest.mark.asyncio
async def test_t2e_mcap_filter_and_stage_counts_unchanged(clean_stock_master):
    """생성컬럼 gte 필터 + return_stage_counts 3단계 attrition 이 name COALESCE 후에도 불변.

    시총 gte(hts_avls_eok) 필터가 raw 로 계산되는데, master_raw 폴백 종목도 필터를
    정상 통과/탈락하고 stage attrition(union/mcap/trade)이 그대로여야 한다 (G-A-1).
    name 은 master_raw 폴백으로 해소되며 필터 결과 원소/순서는 불변.
    """
    from src.db import stock_master

    # A: 시총 통과 + CTPF name / B: 시총 통과 + master_raw 폴백 name /
    # C: 시총 미달(hts_avls 500억 < 1000억컷)
    await _insert_master_raw_avls(clean_stock_master, "005930", name="삼성전자",
                                  master_raw={"hts_kor_isnm": "X"}, hts_avls="10000")
    await _insert_master_raw_avls(clean_stock_master, "000660", name="",
                                  master_raw={"hts_kor_isnm": "SK하이닉스"}, hts_avls="10000")
    await _insert_master_raw_avls(clean_stock_master, "111111", name="",
                                  master_raw={"hts_kor_isnm": "소형주"}, hts_avls="500")

    filtered, stage = await stock_master.list_by_filter(
        min_market_cap=100_000_000_000,  # hts_avls_eok >= 1000
        return_stage_counts=True,
    )
    union = set(stage["union_tickers"])
    mcap = set(stage["mcap_tickers"])

    assert union == {"005930", "000660", "111111"}, "union = 시총 gte 전 (전체 3)."
    assert mcap == {"005930", "000660"}, "mcap = 시총 gte 후 (500억 111111 탈락)."
    assert {r["ticker"] for r in filtered} == {"005930", "000660"}, (
        "필터 결과 원소 불변 (COALESCE name 변경이 WHERE/attrition 무영향, G-A-1)."
    )
    # 폴백 name 이 필터 통과 종목에도 정상 적용
    by_ticker = {r["ticker"]: r["name"] for r in filtered}
    assert by_ticker["005930"] == "삼성전자", "CTPF 우선 유지."
    assert by_ticker["000660"] == "SK하이닉스", "폴백 name 이 필터 통과 종목에도 해소."


async def _insert_master_raw_avls(pg, ticker, *, name, master_raw, hts_avls, nxt=True):
    """T2-e 전용 — 시총 필터 검증 위해 raw.hts_avls 를 케이스별로 주입."""
    await pg.execute(
        """
        INSERT INTO stock_master (ticker, name, excg_dvsn_cd, nxt_tradable,
                                  is_kospi200, is_kosdaq150, raw, master_raw, refreshed_at)
        VALUES ($1, $2, '02', $3, false, false, $4::jsonb, $5::jsonb, $6)
        ON CONFLICT (ticker) DO UPDATE
            SET name = EXCLUDED.name, master_raw = EXCLUDED.master_raw, raw = EXCLUDED.raw
        """,
        ticker, name, nxt,
        {"hts_avls": hts_avls, "acml_tr_pbmn": "50000000000"},
        master_raw,
        datetime.fromisoformat("2026-07-16T16:00:00+09:00"),
    )
