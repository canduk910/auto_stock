"""사이클 153 — stock_master.list_by_filter is_kospi200/is_kosdaq150 회귀 가드.

사용자 결정 영속:
- Q1=A KIS 공식 마스터 source (kospi200_apnt_cls_code != "" AND ksq150_nmix_yn == "Y")
- Q2=A is_kospi200: bool | None = None + is_kosdaq150: bool | None = None 인자 (사이클 108 nxt_tradable 답습)
- Q3=A TDD 정공

G-153-FILTER 5 케이스 (HIGH 3) + G-153-SAFETY (사이클 38 명문화 보존).
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------


def _make_row(
    ticker: str,
    *,
    hts_avls: str = "1000000",
    acml_tr_pbmn: str = "50000000000",
    excg_dvsn_cd: str = "02",
    nxt_tradable: bool = True,
    is_kospi200: bool = False,
    is_kosdaq150: bool = False,
    name: str = "테스트종목",
) -> dict:
    """사이클 153 — is_kospi200/is_kosdaq150 컬럼 영구 영속 신규."""
    return {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": excg_dvsn_cd,
        "nxt_tradable": nxt_tradable,
        "is_kospi200": is_kospi200,
        "is_kosdaq150": is_kosdaq150,
        "raw": {
            "hts_avls": hts_avls,
            "acml_tr_pbmn": acml_tr_pbmn,
        },
    }


def _index_filter(rows, *, is_kospi200=None, is_kosdaq150=None):
    """DB-side WHERE (is_kospi200/is_kosdaq150) 를 mock 레벨에서 시뮬레이션.

    - 둘 다 True → OR 합집합 (is_kospi200 OR is_kosdaq150)
    - 한쪽만 True → 해당 컬럼 True 종목만
    - 둘 다 None → 무필터
    """
    if is_kospi200 is True and is_kosdaq150 is True:
        return [r for r in rows if r.get("is_kospi200") or r.get("is_kosdaq150")]
    if is_kospi200 is not None and is_kosdaq150 is None:
        return [r for r in rows if r.get("is_kospi200") == is_kospi200]
    if is_kosdaq150 is not None and is_kospi200 is None:
        return [r for r in rows if r.get("is_kosdaq150") == is_kosdaq150]
    return list(rows)


async def _run_filter(all_rows, **kwargs):
    """사이클 M2b — pg.fetch 경유. mock 은 DB-side 인덱스 필터링된 rows 를 반환
    (production 은 WHERE 절만 발화 → 결과 pass-through). (result, where_sql) 반환.

    where_sql = SQL 의 WHERE 절 이하만 (SELECT 컬럼 프로젝션에 is_kospi200/is_kosdaq150
    가 등장하므로 WHERE 절로 한정해야 필터 predicate 를 정확히 검증).
    """
    from src.db import stock_master

    filtered = _index_filter(
        all_rows,
        is_kospi200=kwargs.get("is_kospi200"),
        is_kosdaq150=kwargs.get("is_kosdaq150"),
    )
    with patch.object(stock_master, "pg", create=True) as pg_mod:
        pg_mod.fetch = AsyncMock(return_value=filtered)
        result = await stock_master.list_by_filter(**kwargs)
        full_sql = pg_mod.fetch.await_args.args[0].lower()
    where_sql = full_sql.split("where", 1)[1] if "where" in full_sql else ""
    return result, where_sql


# ---------------------------------------------------------------------------
# G-153-FILTER-1 (HIGH) — is_kospi200=True 단독 필터
# ---------------------------------------------------------------------------


class TestG153Filter1:
    @pytest.mark.asyncio
    async def test_filter_1_kospi200_only(self):
        """G-153-FILTER-1 HIGH — is_kospi200=True 인자 영역 KOSPI200 종목만 통과."""
        from src.db import stock_master

        rows = [
            _make_row("000001", is_kospi200=True, is_kosdaq150=False),
            _make_row("000002", is_kospi200=True, is_kosdaq150=False),
            _make_row("000003", is_kospi200=False, is_kosdaq150=False),
            _make_row("000004", is_kospi200=False, is_kosdaq150=True),
        ]

        result, sql = await _run_filter(
            rows, is_kospi200=True, min_market_cap=0, min_trade_amount=0, limit=10,
        )

        tickers = [r["ticker"] for r in result]
        assert "000001" in tickers
        assert "000002" in tickers
        assert "000003" not in tickers, "KOSPI200/KOSDAQ150 모두 False → 제외 의무"
        assert "000004" not in tickers, "KOSPI200 단독 필터 영역 = KOSDAQ150 단독 종목 제외"
        assert "is_kospi200" in sql.lower(), "SQL WHERE 에 is_kospi200 필터 누락"
        assert " or " not in sql.lower(), "단독 지정은 OR 합집합 아님 (AND 단일 필터)"


# ---------------------------------------------------------------------------
# G-153-FILTER-2 (HIGH) — is_kosdaq150=True 단독 필터
# ---------------------------------------------------------------------------


class TestG153Filter2:
    @pytest.mark.asyncio
    async def test_filter_2_kosdaq150_only(self):
        """G-153-FILTER-2 HIGH — is_kosdaq150=True 인자 영역 KOSDAQ150 종목만 통과."""
        from src.db import stock_master

        rows = [
            _make_row("000001", is_kospi200=True, is_kosdaq150=False),
            _make_row("000002", is_kospi200=False, is_kosdaq150=True),
            _make_row("000003", is_kospi200=False, is_kosdaq150=True),
            _make_row("000004", is_kospi200=False, is_kosdaq150=False),
        ]

        result, sql = await _run_filter(
            rows, is_kosdaq150=True, min_market_cap=0, min_trade_amount=0, limit=10,
        )

        tickers = [r["ticker"] for r in result]
        assert "000001" not in tickers, "KOSPI200 단독 종목 제외 의무 (KOSDAQ150 단독 필터)"
        assert "000002" in tickers
        assert "000003" in tickers
        assert "000004" not in tickers
        assert "is_kosdaq150" in sql.lower(), "SQL WHERE 에 is_kosdaq150 필터 누락"


# ---------------------------------------------------------------------------
# G-153-FILTER-3 (HIGH) — OR 합집합 (donchian 의무)
# ---------------------------------------------------------------------------


class TestG153Filter3:
    @pytest.mark.asyncio
    async def test_filter_3_kospi200_or_kosdaq150_union(self):
        """G-153-FILTER-3 HIGH — 둘 다 True 시 OR 합집합 영역 (donchian 의무)."""
        from src.db import stock_master

        rows = [
            _make_row("000001", is_kospi200=True, is_kosdaq150=False),
            _make_row("000002", is_kospi200=False, is_kosdaq150=True),
            _make_row("000003", is_kospi200=True, is_kosdaq150=True),
            _make_row("000004", is_kospi200=False, is_kosdaq150=False),
        ]

        result, sql = await _run_filter(
            rows, is_kospi200=True, is_kosdaq150=True,
            min_market_cap=0, min_trade_amount=0, limit=10,
        )

        tickers = [r["ticker"] for r in result]
        assert "000001" in tickers, "KOSPI200 단독 = OR 통과"
        assert "000002" in tickers, "KOSDAQ150 단독 = OR 통과"
        assert "000003" in tickers, "양쪽 모두 True = OR 통과"
        assert "000004" not in tickers, "양쪽 모두 False = OR 제외"
        s = sql.lower()
        assert "is_kospi200" in s and "is_kosdaq150" in s and " or " in s, (
            "둘 다 True → OR 합집합 SQL 누락 (donchian 의무)"
        )


# ---------------------------------------------------------------------------
# G-153-FILTER-4 — 회귀 보존 (None 시 무필터)
# ---------------------------------------------------------------------------


class TestG153Filter4:
    @pytest.mark.asyncio
    async def test_filter_4_none_passes_all(self):
        """G-153-FILTER-4 — is_kospi200=None + is_kosdaq150=None 영역 무필터 (회귀 보존)."""
        from src.db import stock_master

        rows = [
            _make_row("000001", is_kospi200=False, is_kosdaq150=False),
            _make_row("000002", is_kospi200=True, is_kosdaq150=False),
            _make_row("000003", is_kospi200=False, is_kosdaq150=True),
        ]

        result, sql = await _run_filter(rows, min_market_cap=0, min_trade_amount=0, limit=10)

        tickers = [r["ticker"] for r in result]
        assert len(tickers) == 3, "None 시 무필터 영구 영속 (회귀 보존 영구 영속)"
        assert "is_kospi200" not in sql.lower() and "is_kosdaq150" not in sql.lower(), (
            "None 시 인덱스 필터 WHERE 미발생 (무필터 보존)"
        )


# ---------------------------------------------------------------------------
# G-153-FILTER-5 — 시그너처 영역 사이클 108 패턴 답습
# ---------------------------------------------------------------------------


class TestG153Filter5:
    def test_filter_5_signature_persistence(self):
        """G-153-FILTER-5 — list_by_filter 시그너처 영역 is_kospi200 + is_kosdaq150 영구 영속 인자."""
        from src.db import stock_master

        sig = inspect.signature(stock_master.list_by_filter)
        params = sig.parameters

        assert "is_kospi200" in params, "G-153-FILTER-5 is_kospi200 인자 영구 영속 의무"
        assert "is_kosdaq150" in params, "G-153-FILTER-5 is_kosdaq150 인자 영구 영속 의무"

        # 디폴트 = None (회귀 보존)
        assert params["is_kospi200"].default is None
        assert params["is_kosdaq150"].default is None

        # 사이클 108 nxt_tradable 패턴 답습 = bool | None
        assert "nxt_tradable" in params, "사이클 108 nxt_tradable 영역 보존 의무"
