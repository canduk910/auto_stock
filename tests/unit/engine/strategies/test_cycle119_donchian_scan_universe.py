"""사이클 119 — donchian_swing _scan_universe stock_master 전환 회귀 가드.

사이클 108 답습 패턴 (VB/LTV/BFB) 100% 영구 영속 + donchian 특수성 반영:
  - Q2=D 임시 완화 임계 (500억 / 10억) — 사이클 121+ 점진 복원 권고
  - Q5=A nxt_tradable=None — donchian MAIN 단독 (사이클 26 영속)
  - 멀티데이 보유 영역 (5~15 영업일) — 사이클 32 R4 universe guard 영속

HIGH-1: DEFAULT_PARAMS 4 필터 신규 키 영구 영속
HIGH-2: _scan_universe = stock_master.list_by_filter() 호출 영속
HIGH-3: funnel 카운터 (universe_candidates + universe_filtered + last_run_at) 영속
HIGH-4: graceful 영역 (raise 시 빈 list + scan_stats 0)
MEDIUM-1: ETF 제외 + 6자리 종목코드 영속 (사이클 89)
MEDIUM-2: KIS API 직접 호출 0건 영구 영속 (운영 효과)
AST G-AST1: KOSPI200/KOSDAQ150 + fetch_stock_detail import 영역 부재
"""

from __future__ import annotations

import asyncio
from datetime import timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

KST = timezone(timedelta(hours=9))


def _make_strategy():
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategy_base import StrategyConfig

    config = StrategyConfig(
        strategy_id="donchian_swing",
        name="도치안 스윙",
        params={},  # DEFAULT_PARAMS 영역 사용 영속
    )
    return DonchianSwingStrategy(config)


def _stage_aware_mock(rows):
    """사이클 170 카드 A — donchian 이 return_stage_counts=True 전달 시 tuple 반환.

    AsyncMock(return_value=rows) 대체 — kwargs 의 return_stage_counts 분기.
    미지정 호출 → list 그대로 (회귀 보존).
    """
    from unittest.mock import AsyncMock

    async def _impl(**kwargs):
        if kwargs.get("return_stage_counts"):
            tks = [r.get("ticker", "") for r in rows]
            return rows, {
                "union_tickers": tks,
                "mcap_tickers": tks,
                "trade_tickers": tks,
            }
        return rows

    return AsyncMock(side_effect=_impl)


def _make_sm_row(
    ticker: str,
    name: str = "테스트종목",
    *,
    hts_avls: str = "1000000",        # 1조 (백만원 단위)
    acml_tr_pbmn: str = "50000000000",  # 500억
    nxt_tradable: bool = True,
    excg_dvsn_cd: str = "02",
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


# ---------------------------------------------------------------------------
# HIGH-1: DEFAULT_PARAMS 4 필터 신규 키 영구 영속
# ---------------------------------------------------------------------------


class TestDonchianDefaultParamsHigh1:
    """HIGH-1: Q2=D 임시 완화 임계 + Q5=A nxt_tradable=None + exclude_tickers 영속."""

    def test_h1_min_market_cap_relaxed_500_billion(self):
        """min_market_cap = 500억 (Q2=D 임시 완화, 원본 3,000억)."""
        from src.engine.strategies.donchian_swing import DonchianSwingStrategy

        assert DonchianSwingStrategy.DEFAULT_PARAMS["min_market_cap"] == 50_000_000_000

    def test_h1_min_trade_amount_relaxed_10_billion(self):
        """min_trade_amount = 10억 (Q2=D 임시 완화, 원본 50억)."""
        from src.engine.strategies.donchian_swing import DonchianSwingStrategy

        assert DonchianSwingStrategy.DEFAULT_PARAMS["min_trade_amount"] == 1_000_000_000

    def test_h1_exclude_tickers_empty_list(self):
        """exclude_tickers = [] 빈 list 디폴트 (Plan Phase C UI 호환)."""
        from src.engine.strategies.donchian_swing import DonchianSwingStrategy

        assert DonchianSwingStrategy.DEFAULT_PARAMS["exclude_tickers"] == []

    def test_h1_nxt_tradable_none(self):
        """nxt_tradable = None (Q5=A donchian MAIN 단독)."""
        from src.engine.strategies.donchian_swing import DonchianSwingStrategy

        assert DonchianSwingStrategy.DEFAULT_PARAMS["nxt_tradable"] is None


# ---------------------------------------------------------------------------
# HIGH-2: _scan_universe = stock_master.list_by_filter() 호출 영속
# ---------------------------------------------------------------------------


class TestDonchianScanUniverseHigh2:
    """HIGH-2: list_by_filter() 호출 정합 + 4 필터 인자 영속."""

    def test_h2_calls_list_by_filter_with_4_filters(self):
        """_scan_universe 가 list_by_filter 를 4 필터 인자로 호출한다."""
        strategy = _make_strategy()
        rows = [_make_sm_row("005930")]

        with patch(
            "src.db.stock_master.list_by_filter",
            new=_stage_aware_mock(rows),
        ) as mock_lbf:
            asyncio.run(strategy._scan_universe())

        mock_lbf.assert_called_once()
        kwargs = mock_lbf.call_args.kwargs
        assert kwargs["min_market_cap"] == 50_000_000_000
        assert kwargs["min_trade_amount"] == 1_000_000_000
        assert kwargs["exclude_tickers"] == []
        assert kwargs["nxt_tradable"] is None
        assert kwargs["limit"] == 400  # max_scan_stocks 디폴트 (2026-07 200→400, index 348 커버)

    def test_h2_returns_filtered_ticker_list(self):
        """반환값 = list[str] ticker (6자리 + ETF 제외)."""
        strategy = _make_strategy()
        rows = [
            _make_sm_row("005930", name="삼성전자"),
            _make_sm_row("000660", name="SK하이닉스"),
        ]

        with patch(
            "src.db.stock_master.list_by_filter",
            new=_stage_aware_mock(rows),
        ):
            result = asyncio.run(strategy._scan_universe())

        assert result == ["005930", "000660"]


# ---------------------------------------------------------------------------
# HIGH-3: funnel 카운터 영속
# ---------------------------------------------------------------------------


class TestDonchianScanStatsHigh3:
    """HIGH-3: universe_candidates / universe_filtered / last_run_at 영속."""

    def test_h3_universe_candidates_set(self):
        """universe_candidates = DB 반환 행수."""
        strategy = _make_strategy()
        rows = [_make_sm_row(f"{i:06d}") for i in range(1, 11)]

        with patch(
            "src.db.stock_master.list_by_filter",
            new=_stage_aware_mock(rows),
        ):
            asyncio.run(strategy._scan_universe())

        assert strategy._scan_stats["universe_candidates"] == 10

    def test_h3_universe_filtered_set(self):
        """universe_filtered = ETF + 6자리 필터 통과 수."""
        strategy = _make_strategy()
        rows = [
            _make_sm_row("069500", name="KODEX 200"),  # ETF 제외
            _make_sm_row("005930", name="삼성전자"),
            _make_sm_row("000660", name="SK하이닉스"),
        ]

        with patch(
            "src.db.stock_master.list_by_filter",
            new=_stage_aware_mock(rows),
        ):
            asyncio.run(strategy._scan_universe())

        assert strategy._scan_stats["universe_candidates"] == 3
        assert strategy._scan_stats["universe_filtered"] == 2

    def test_h3_last_run_at_kst_iso(self):
        """last_run_at = KST ISO 8601 (+09:00 명시)."""
        strategy = _make_strategy()
        rows = [_make_sm_row("005930")]

        with patch(
            "src.db.stock_master.list_by_filter",
            new=_stage_aware_mock(rows),
        ):
            asyncio.run(strategy._scan_universe())

        last_run = strategy._scan_stats["last_run_at"]
        assert last_run is not None
        assert "+09:00" in last_run


# ---------------------------------------------------------------------------
# HIGH-4: graceful 영역 (raise 시 빈 list + scan_stats 0)
# ---------------------------------------------------------------------------


class TestDonchianScanUniverseHigh4:
    """HIGH-4: list_by_filter raise 시 graceful 빈 list 반환 + scan_stats reset."""

    def test_h4_graceful_empty_list_on_exception(self):
        """list_by_filter Exception → 빈 list `[]` 반환."""
        strategy = _make_strategy()

        with patch(
            "src.db.stock_master.list_by_filter",
            new=AsyncMock(side_effect=RuntimeError("Supabase 영역 실패")),
        ):
            result = asyncio.run(strategy._scan_universe())

        assert result == []

    def test_h4_graceful_scan_stats_zero_on_exception(self):
        """list_by_filter Exception → scan_stats universe_candidates/filtered = 0."""
        strategy = _make_strategy()

        with patch(
            "src.db.stock_master.list_by_filter",
            new=AsyncMock(side_effect=RuntimeError("Supabase 영역 실패")),
        ):
            asyncio.run(strategy._scan_universe())

        assert strategy._scan_stats["universe_candidates"] == 0
        assert strategy._scan_stats["universe_filtered"] == 0
        assert strategy._scan_stats["last_run_at"] is not None


# ---------------------------------------------------------------------------
# MEDIUM-1: ETF 제외 + 6자리 종목코드 영속 (사이클 89)
# ---------------------------------------------------------------------------


class TestDonchianScanUniverseMedium1:
    """MEDIUM-1: ETF 키워드 제외 + 6자리 종목코드 검증 영속."""

    def test_m1_etf_excluded_by_name_keyword(self):
        """ETF 키워드 (KODEX/TIGER 등) 포함 종목 제외."""
        strategy = _make_strategy()
        rows = [
            _make_sm_row("069500", name="KODEX 200"),
            _make_sm_row("102110", name="TIGER 200"),
            _make_sm_row("005930", name="삼성전자"),
        ]

        with patch(
            "src.db.stock_master.list_by_filter",
            new=_stage_aware_mock(rows),
        ):
            result = asyncio.run(strategy._scan_universe())

        assert "069500" not in result
        assert "102110" not in result
        assert "005930" in result

    def test_m1_non_6digit_ticker_excluded(self):
        """6자리 숫자가 아닌 ticker (ETN 등) 제외."""
        strategy = _make_strategy()
        rows = [
            _make_sm_row("Q52010", name="ETN종목"),
            _make_sm_row("005930", name="삼성전자"),
        ]

        with patch(
            "src.db.stock_master.list_by_filter",
            new=_stage_aware_mock(rows),
        ):
            result = asyncio.run(strategy._scan_universe())

        assert "Q52010" not in result
        assert "005930" in result


# ---------------------------------------------------------------------------
# MEDIUM-2: KIS API 직접 호출 0건 영구 영속 (운영 효과)
# ---------------------------------------------------------------------------


class TestDonchianScanUniverseMedium2:
    """MEDIUM-2: KIS API 직접 호출 0건 (사이클 17 OPSP0002 + LMS chain 안전 강화)."""

    def test_m2_no_fetch_stock_detail_call(self):
        """_scan_universe 실행 중 fetch_stock_detail (KIS FHKST01010100) 호출 0건."""
        strategy = _make_strategy()
        rows = [_make_sm_row("005930"), _make_sm_row("000660")]

        with patch(
            "src.db.stock_master.list_by_filter",
            new=_stage_aware_mock(rows),
        ), patch("src.api.condition.fetch_stock_detail") as mock_fsd:
            asyncio.run(strategy._scan_universe())

        mock_fsd.assert_not_called()


# ---------------------------------------------------------------------------
# AST G-AST1: KOSPI200/KOSDAQ150 + fetch_stock_detail import 영역 부재
# ---------------------------------------------------------------------------


class TestDonchianScanUniverseAst:
    """AST G-AST1: _scan_universe 본체 정적 검증 (사이클 108 답습 패턴)."""

    def test_g_ast1_no_fetch_stock_detail_import_in_scan_universe(self):
        """donchian_swing.py 의 _scan_universe 본체에서 fetch_stock_detail import 0건."""
        import ast
        import pathlib

        src_file = pathlib.Path("src/engine/strategies/donchian_swing.py")
        source = src_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        scan_universe_func = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.AsyncFunctionDef)
                and node.name == "_scan_universe"
            ):
                scan_universe_func = node
                break

        assert scan_universe_func is not None, "_scan_universe 메서드 부재"

        # _scan_universe 본체 영역에서 fetch_stock_detail import 0건 정적 검증
        for child in ast.walk(scan_universe_func):
            if isinstance(child, ast.ImportFrom):
                imported_names = [alias.name for alias in child.names]
                assert "fetch_stock_detail" not in imported_names, (
                    "_scan_universe 본체에 fetch_stock_detail import 잔존 — "
                    "사이클 119 stock_master 전환 후 완전 폐기 의무"
                )

    def test_g_ast1_no_kospi_200_kosdaq_150_import_in_scan_universe(self):
        """donchian_swing.py 의 _scan_universe 본체에서 KOSPI_200_TICKERS / KOSDAQ_150_TICKERS import 0건."""
        import ast
        import pathlib

        src_file = pathlib.Path("src/engine/strategies/donchian_swing.py")
        source = src_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        scan_universe_func = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.AsyncFunctionDef)
                and node.name == "_scan_universe"
            ):
                scan_universe_func = node
                break

        assert scan_universe_func is not None

        # _scan_universe 본체 영역에서 KOSPI_200_TICKERS / KOSDAQ_150_TICKERS import 0건
        for child in ast.walk(scan_universe_func):
            if isinstance(child, ast.ImportFrom):
                imported_names = [alias.name for alias in child.names]
                assert "KOSPI_200_TICKERS" not in imported_names, (
                    "_scan_universe 본체에 KOSPI_200_TICKERS import 잔존 — "
                    "사이클 119 stock_master 전환 후 완전 폐기 의무"
                )
                assert "KOSDAQ_150_TICKERS" not in imported_names, (
                    "_scan_universe 본체에 KOSDAQ_150_TICKERS import 잔존 — "
                    "사이클 119 stock_master 전환 후 완전 폐기 의무"
                )

    def test_g_ast1_list_by_filter_import_present_in_scan_universe(self):
        """donchian_swing.py 의 _scan_universe 본체에서 list_by_filter 사용 확인 (stock_master 영역)."""
        import pathlib

        src_file = pathlib.Path("src/engine/strategies/donchian_swing.py")
        source = src_file.read_text(encoding="utf-8")

        # stock_master 모듈 import + list_by_filter 호출 영역 검증
        assert "from src.db import stock_master" in source, (
            "_scan_universe 영역에 stock_master import 부재 — 사이클 119 시정 미적용"
        )
        assert "list_by_filter" in source, (
            "_scan_universe 영역에 list_by_filter 호출 부재 — 사이클 119 시정 미적용"
        )
