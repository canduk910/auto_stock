"""Red (단위) — list_by_filter SELECT 종목명 COALESCE 폴백 계약 가드.

배경 (스펙 `name_coalesce_fix_spec.md`):
전체상장 스캔 전략(특히 kojiro)의 funnel 후보가 종목명 없이 종목번호만 표시되는 버그.
근본 원인 = KIS 일일 마스터파일 한글명이 `stock_master.master_raw["hts_kor_isnm"]` 에만
있고, CTPF1002R 로만 채워지는 `name` 컬럼/`raw` 는 소형주에서 대개 빈값이며,
`list_by_filter` 의 SELECT(라인 632)가 `name, raw` 만 반환(master_raw 미참조)한다.

시정 = SELECT 의 `name` 을
    COALESCE(NULLIF(name, ''), NULLIF(TRIM(master_raw->>'hts_kor_isnm'), ''), '') AS name
로 교체 — CTPF `name` 우선, 없으면 마스터파일 한글명(고정폭 패딩 TRIM), 둘 다 없으면
'' (NULL 반환 금지, `row.get("name","")` None 회귀 차단). G-AST1 준수(읽기 폴백만,
쓰기/name 컬럼 write 무변경). 매수 진입 *전* 조회 계층 — 매매 hot path 무관.

패턴: test_cycleM2b_stock_master_pg.py 의 `pg.fetch` AsyncMock + SQL 캡처
(`pg_mod.fetch.await_args.args[0]`) 답습 (DB 불요).

Red 유효성: production SELECT 미변경(`name` 단일 컬럼) → COALESCE/master_raw 폴백/
`AS name` 부재 → 캡처 SQL 단언 FAIL (import/문법 아님).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _row(ticker: str, *, name: str = "테스트종목") -> dict:
    """list_by_filter 반환 계약 형태 (M2b _row 답습)."""
    return {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": "02",
        "nxt_tradable": True,
        "is_kospi200": False,
        "is_kosdaq150": False,
        "raw": {"hts_avls": "10000", "acml_tr_pbmn": "50000000000"},
    }


def _captured_select_sql(sql: str) -> str:
    """공백 전부 제거 + 소문자화 — 포매팅 무관 부분 문자열 단언용."""
    return "".join(sql.lower().split())


# ===========================================================================
# T1-a — SELECT 종목명 COALESCE(master_raw->>'hts_kor_isnm') 폴백 도입
# ===========================================================================
@pytest.mark.asyncio
async def test_list_by_filter_select_coalesces_name_from_master_raw():
    """⚠️ SELECT name 절이 CTPF name → master_raw.hts_kor_isnm(TRIM) → '' COALESCE.

    현행: `SELECT ticker, name, ...` (name 단일 컬럼, master_raw 미참조).
    시정: `COALESCE(NULLIF(name, ''), NULLIF(TRIM(master_raw->>'hts_kor_isnm'), ''), '') AS name`.
    """
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[])
        # 기본 경로(return_stage_counts=False, mcap/trade gte 없음) → 단일 pg.fetch.
        await stock_master.list_by_filter()

    sql_ns = _captured_select_sql(pg_mod.fetch.await_args.args[0])

    assert "coalesce(nullif(name" in sql_ns, (
        "SELECT name 이 COALESCE(NULLIF(name, ''), ...) 로 CTPF name 우선 폴백 의무. "
        f"실제 SQL(공백제거): {sql_ns}"
    )
    assert "master_raw->>'hts_kor_isnm'" in sql_ns, (
        "종목명 2순위 폴백 = master_raw->>'hts_kor_isnm' (마스터파일 한글명) 참조 의무. "
        f"실제 SQL(공백제거): {sql_ns}"
    )
    assert "trim(master_raw->>'hts_kor_isnm')" in sql_ns, (
        "master_raw 한글명은 고정폭 패딩 → TRIM 적용 의무 (NULLIF 로 트림 후 빈값 skip). "
        f"실제 SQL(공백제거): {sql_ns}"
    )
    # 둘 다 없을 때 '' (NULL 반환 금지). COALESCE 세번째 인자 '' 존재.
    assert "),'')asname" in sql_ns or "'')asname" in sql_ns, (
        "COALESCE 최종 인자 '' (NULL 반환 금지, 기존 소비자 '' 기대) + AS name 별칭 의무. "
        f"실제 SQL(공백제거): {sql_ns}"
    )


# ===========================================================================
# T1-b (회귀) — 반환 컬럼 계약 불변 + AS name 로 name 키 보존
# ===========================================================================
@pytest.mark.asyncio
async def test_list_by_filter_select_preserves_column_contract():
    """SELECT 나머지 컬럼(ticker/excg_dvsn_cd/nxt_tradable/is_kospi200/is_kosdaq150/raw)
    여전히 존재 + `AS name` 로 반환 dict `name` 키 불변 (소비자 코드 변경 0).
    """
    from src.db import stock_master

    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=[_row("005930", name="삼성전자")])
        out = await stock_master.list_by_filter()

    sql_ns = _captured_select_sql(pg_mod.fetch.await_args.args[0])
    for col in ("ticker", "excg_dvsn_cd", "nxt_tradable",
                "is_kospi200", "is_kosdaq150", "raw"):
        assert col in sql_ns, f"SELECT 반환 컬럼 '{col}' 누락 (매수 후보 소비 계약 위반)."

    # `AS name` 별칭 → 반환 dict 키 name 불변.
    assert "asname" in sql_ns, (
        "COALESCE 표현식은 `AS name` 별칭으로 반환 dict 키 `name` 을 보존해야 함 "
        "(소비자 row.get('name') 계약)."
    )
    assert "name" in out[0], "반환 row 에 name 키 보존 (소비자 계약)."
