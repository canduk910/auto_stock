"""사이클 153 — stock_master.list_by_filter is_kospi200/is_kosdaq150 회귀 가드.

사용자 결정 영속:
- Q1=A KIS 공식 마스터 source (kospi200_apnt_cls_code != "" AND ksq150_nmix_yn == "Y")
- Q2=A is_kospi200: bool | None = None + is_kosdaq150: bool | None = None 인자 (사이클 108 nxt_tradable 답습)
- Q3=A TDD 정공

G-153-FILTER 5 케이스 (HIGH 3) + G-153-SAFETY (사이클 38 명문화 보존).
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

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


def _mock_supabase_result(rows: list[dict]):
    mock_result = MagicMock()
    mock_result.data = rows
    return mock_result


def _setup_chain(mock_sb, result_mock):
    chain = MagicMock()
    mock_sb.table.return_value = chain
    chain.select.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.eq.return_value = chain
    chain.or_.return_value = chain
    chain.execute.return_value = result_mock
    return chain


async def _fake_to_thread(fn, *args, **kwargs):
    return fn(*args, **kwargs)


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

        with patch.object(stock_master, "supabase") as mock_sb, \
             patch("asyncio.to_thread", _fake_to_thread):
            _setup_chain(mock_sb, _mock_supabase_result(rows))
            result = await stock_master.list_by_filter(
                is_kospi200=True,
                min_market_cap=0,
                min_trade_amount=0,
                limit=10,
            )

        tickers = [r["ticker"] for r in result]
        assert "000001" in tickers
        assert "000002" in tickers
        assert "000003" not in tickers, "KOSPI200/KOSDAQ150 모두 False → 제외 의무"
        assert "000004" not in tickers, "KOSPI200 단독 필터 영역 = KOSDAQ150 단독 종목 제외"


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

        with patch.object(stock_master, "supabase") as mock_sb, \
             patch("asyncio.to_thread", _fake_to_thread):
            _setup_chain(mock_sb, _mock_supabase_result(rows))
            result = await stock_master.list_by_filter(
                is_kosdaq150=True,
                min_market_cap=0,
                min_trade_amount=0,
                limit=10,
            )

        tickers = [r["ticker"] for r in result]
        assert "000001" not in tickers, "KOSPI200 단독 종목 제외 의무 (KOSDAQ150 단독 필터)"
        assert "000002" in tickers
        assert "000003" in tickers
        assert "000004" not in tickers


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

        with patch.object(stock_master, "supabase") as mock_sb, \
             patch("asyncio.to_thread", _fake_to_thread):
            _setup_chain(mock_sb, _mock_supabase_result(rows))
            result = await stock_master.list_by_filter(
                is_kospi200=True,
                is_kosdaq150=True,
                min_market_cap=0,
                min_trade_amount=0,
                limit=10,
            )

        tickers = [r["ticker"] for r in result]
        assert "000001" in tickers, "KOSPI200 단독 = OR 통과"
        assert "000002" in tickers, "KOSDAQ150 단독 = OR 통과"
        assert "000003" in tickers, "양쪽 모두 True = OR 통과"
        assert "000004" not in tickers, "양쪽 모두 False = OR 제외"


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

        with patch.object(stock_master, "supabase") as mock_sb, \
             patch("asyncio.to_thread", _fake_to_thread):
            _setup_chain(mock_sb, _mock_supabase_result(rows))
            result = await stock_master.list_by_filter(
                min_market_cap=0,
                min_trade_amount=0,
                limit=10,
            )

        tickers = [r["ticker"] for r in result]
        assert len(tickers) == 3, "None 시 무필터 영구 영속 (회귀 보존 영구 영속)"


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
