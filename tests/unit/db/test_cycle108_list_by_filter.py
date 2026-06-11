"""사이클 108 — stock_master.list_by_filter 회귀 가드.

HIGH-1: 4 필터 (min_market_cap, min_trade_amount, nxt_tradable, exclude_tickers) 정합성
HIGH-5: hts_avls 백만원 → 원 단위 변환 (×1_000_000)
MEDIUM-3: stock_master 전체 활용 (~2,800종목, 사이클 106 영속)
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 공통 픽스처 헬퍼
# ---------------------------------------------------------------------------

def _make_row(
    ticker: str,
    hts_avls: str = "1000000",   # 1조 (백만원 단위)
    acml_tr_pbmn: str = "50000000000",  # 500억 (원 단위)
    excg_dvsn_cd: str = "02",
    nxt_tradable: bool = True,
    name: str = "테스트종목",
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": excg_dvsn_cd,
        "nxt_tradable": nxt_tradable,
        "raw": {
            "hts_avls": hts_avls,
            "acml_tr_pbmn": acml_tr_pbmn,
        },
    }


def _mock_supabase_result(rows: list[dict]):
    """Supabase execute() 동기 응답 모킹."""
    mock_result = MagicMock()
    mock_result.data = rows
    return mock_result


def _setup_chain(mock_sb, result_mock):
    """Supabase 체이닝 메서드 mock 설정."""
    chain = MagicMock()
    mock_sb.table.return_value = chain
    chain.select.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.eq.return_value = chain
    chain.execute.return_value = result_mock
    return chain


async def _fake_to_thread(fn, *args, **kwargs):
    """asyncio.to_thread 대신 동기 함수 즉시 실행."""
    return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# HIGH-1: 4 필터 정합성
# ---------------------------------------------------------------------------

class TestListByFilterHigh1:
    """HIGH-1: 4 필터 (시총/거래대금/nxt_tradable/exclude_tickers) 정확성."""

    def test_h1_min_market_cap_filters_correctly(self):
        """시총 1,000억 미만 종목이 제외된다 (hts_avls 백만원 단위)."""
        rows = [
            _make_row("000001", hts_avls="200000"),   # 2,000억 — 통과
            _make_row("000002", hts_avls="50000"),    # 500억 — 제외 (1,000억 미만)
        ]
        result_mock = _mock_supabase_result(rows)

        with patch("src.db.stock_master.supabase") as mock_sb, \
             patch("asyncio.to_thread", side_effect=_fake_to_thread):
            _setup_chain(mock_sb, result_mock)
            import src.db.stock_master as sm
            result = asyncio.run(sm.list_by_filter(min_market_cap=100_000_000_000))

        tickers = [r["ticker"] for r in result]
        assert "000001" in tickers
        assert "000002" not in tickers

    def test_h1_min_trade_amount_filters_correctly(self):
        """거래대금 200억 미만 종목이 제외된다."""
        rows = [
            _make_row("000010", acml_tr_pbmn="50000000000"),   # 500억 — 통과
            _make_row("000011", acml_tr_pbmn="5000000000"),    # 50억 — 제외
        ]
        result_mock = _mock_supabase_result(rows)

        with patch("src.db.stock_master.supabase") as mock_sb, \
             patch("asyncio.to_thread", side_effect=_fake_to_thread):
            _setup_chain(mock_sb, result_mock)
            import src.db.stock_master as sm
            result = asyncio.run(sm.list_by_filter(min_trade_amount=20_000_000_000))

        tickers = [r["ticker"] for r in result]
        assert "000010" in tickers
        assert "000011" not in tickers

    def test_h1_exclude_tickers_removes_specified(self):
        """exclude_tickers 에 지정된 종목이 결과에서 제외된다."""
        rows = [
            _make_row("005930"),  # 삼성전자
            _make_row("000660"),  # SK하이닉스
        ]
        result_mock = _mock_supabase_result(rows)

        with patch("src.db.stock_master.supabase") as mock_sb, \
             patch("asyncio.to_thread", side_effect=_fake_to_thread):
            _setup_chain(mock_sb, result_mock)
            import src.db.stock_master as sm
            result = asyncio.run(sm.list_by_filter(exclude_tickers=["005930"]))

        tickers = [r["ticker"] for r in result]
        assert "005930" not in tickers
        assert "000660" in tickers

    def test_h1_nxt_tradable_param_passed_to_query(self):
        """nxt_tradable=True 가 DB 쿼리에 전달된다 (eq 호출 검증)."""
        rows = [_make_row("000001")]
        result_mock = _mock_supabase_result(rows)

        with patch("src.db.stock_master.supabase") as mock_sb, \
             patch("asyncio.to_thread", side_effect=_fake_to_thread):
            chain = _setup_chain(mock_sb, result_mock)
            import src.db.stock_master as sm
            asyncio.run(sm.list_by_filter(nxt_tradable=True))

        # eq("nxt_tradable", True) 가 최소 1회 호출됐는지 확인
        eq_calls = [str(c) for c in chain.eq.call_args_list]
        assert any("nxt_tradable" in c for c in eq_calls), (
            "nxt_tradable=True 가 Supabase .eq() 호출에 누락됨"
        )

    def test_h1_limit_caps_result(self):
        """limit 파라미터가 결과 건수를 제한한다."""
        rows = [_make_row(f"{i:06d}") for i in range(1, 201)]
        result_mock = _mock_supabase_result(rows)

        with patch("src.db.stock_master.supabase") as mock_sb, \
             patch("asyncio.to_thread", side_effect=_fake_to_thread):
            _setup_chain(mock_sb, result_mock)
            import src.db.stock_master as sm
            result = asyncio.run(sm.list_by_filter(limit=50))

        assert len(result) <= 50


# ---------------------------------------------------------------------------
# HIGH-5: hts_avls 백만원 → 원 변환 (×1_000_000)
# ---------------------------------------------------------------------------

class TestListByFilterHigh5:
    """HIGH-5: hts_avls 단위 변환 정확성."""

    def test_h5_hts_avls_unit_conversion_1trillion(self):
        """hts_avls=1_000_000 (1조 백만원) → 1_000_000_000_000 원 = 1조 통과."""
        rows = [_make_row("000001", hts_avls="1000000")]  # 1조 백만원
        result_mock = _mock_supabase_result(rows)

        with patch("src.db.stock_master.supabase") as mock_sb, \
             patch("asyncio.to_thread", side_effect=_fake_to_thread):
            _setup_chain(mock_sb, result_mock)
            import src.db.stock_master as sm
            result = asyncio.run(sm.list_by_filter(min_market_cap=1_000_000_000_000))  # 1조

        assert any(r["ticker"] == "000001" for r in result)

    def test_h5_hts_avls_just_below_threshold_excluded(self):
        """hts_avls=99_999 (999.99억 백만원) → 1,000억 임계 미달 제외."""
        rows = [_make_row("000002", hts_avls="99999")]  # 999.99억 백만원
        result_mock = _mock_supabase_result(rows)

        with patch("src.db.stock_master.supabase") as mock_sb, \
             patch("asyncio.to_thread", side_effect=_fake_to_thread):
            _setup_chain(mock_sb, result_mock)
            import src.db.stock_master as sm
            result = asyncio.run(sm.list_by_filter(min_market_cap=100_000_000_000))  # 1,000억

        assert not any(r["ticker"] == "000002" for r in result)

    def test_h5_hts_avls_missing_graceful(self):
        """hts_avls 키 미존재(None/없음) 시 0 으로 처리 — 시총 필터 제외."""
        rows = [
            {"ticker": "000003", "name": "테스트", "excg_dvsn_cd": "02",
             "nxt_tradable": True, "raw": {}},  # hts_avls 없음
        ]
        result_mock = _mock_supabase_result(rows)

        with patch("src.db.stock_master.supabase") as mock_sb, \
             patch("asyncio.to_thread", side_effect=_fake_to_thread):
            _setup_chain(mock_sb, result_mock)
            import src.db.stock_master as sm
            result = asyncio.run(sm.list_by_filter(min_market_cap=1_000_000))  # 1억

        # hts_avls=0 이면 1억 임계도 통과 불가
        assert not any(r["ticker"] == "000003" for r in result)


# ---------------------------------------------------------------------------
# MEDIUM-3: limit×2 버퍼 패턴 (사이클 106 DB 활용 영속)
# ---------------------------------------------------------------------------

class TestListByFilterMedium3:
    """MEDIUM-3: 2× 버퍼 쿼리로 limit 충족 보장."""

    def test_m3_fetch_limit_is_double(self):
        """DB 조회 limit 은 min(limit*2, 1000) 이상이어야 한다."""
        rows = []
        result_mock = _mock_supabase_result(rows)

        with patch("src.db.stock_master.supabase") as mock_sb, \
             patch("asyncio.to_thread", side_effect=_fake_to_thread):
            chain = _setup_chain(mock_sb, result_mock)
            import src.db.stock_master as sm
            asyncio.run(sm.list_by_filter(limit=100))

        # .limit(N) 호출 시 N >= 200 (100*2)
        limit_calls = chain.limit.call_args_list
        assert limit_calls, "Supabase .limit() 가 호출되지 않음"
        actual_limit = limit_calls[0][0][0]
        assert actual_limit >= 200, (
            f"DB fetch limit {actual_limit} 이 요청 limit 100 의 2배(200) 미만"
        )

    def test_m3_no_kis_api_import_in_list_by_filter(self):
        """list_by_filter 실행 중 KIS API 모듈이 임포트되지 않는다."""
        rows = [_make_row("000001")]
        result_mock = _mock_supabase_result(rows)

        with patch("src.db.stock_master.supabase") as mock_sb, \
             patch("asyncio.to_thread", side_effect=_fake_to_thread):
            _setup_chain(mock_sb, result_mock)
            with patch("src.api.base.kis_get") as mock_kis:
                import src.db.stock_master as sm
                asyncio.run(sm.list_by_filter())
                mock_kis.assert_not_called()
