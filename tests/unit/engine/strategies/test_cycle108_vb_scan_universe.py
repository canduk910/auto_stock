"""사이클 108 — VB (volatility_breakout) _scan_universe stock_master 전환 회귀 가드.

HIGH-2: VB _scan_universe KIS volume-rank API 호출 0건 (AST 영구 가드 포함)
MEDIUM-1: ETF 제외 + 6자리 종목코드 영속
MEDIUM-2: funnel 카운터 (universe_candidates + universe_filtered + last_run_at) 영속
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

KST = timezone(timedelta(hours=9))


def _make_strategy():
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    config = StrategyConfig(
        strategy_id="volatility_breakout",
        name="변동성돌파",
        params={
            "min_market_cap": 100_000_000_000,
            "min_trade_amount": 20_000_000_000,
            "max_scan_stocks": 100,
        },
    )
    return VolatilityBreakoutStrategy(config)


def _make_sm_row(ticker: str, name: str = "테스트종목", nxt_tradable: bool = True) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": "02",
        "nxt_tradable": nxt_tradable,
        "raw": {
            "hts_avls": "1000000",    # 1조
            "acml_tr_pbmn": "50000000000",
        },
    }


# ---------------------------------------------------------------------------
# HIGH-2: KIS volume-rank API 호출 0건
# ---------------------------------------------------------------------------

class TestVbScanUniverseHigh2:
    """HIGH-2: KIS volume-rank API 호출 0건."""

    def test_h2_no_kis_api_call_during_scan_universe(self):
        """_scan_universe 실행 중 KIS API (kis_get) 가 호출되지 않는다."""
        strategy = _make_strategy()
        rows = [_make_sm_row("005930"), _make_sm_row("000660")]

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)), \
             patch("src.api.base.kis_get") as mock_kis_get:
            asyncio.run(strategy._scan_universe())
            mock_kis_get.assert_not_called()

    def test_h2_uses_stock_master_list_by_filter(self):
        """_scan_universe 가 stock_master.list_by_filter 를 호출한다."""
        strategy = _make_strategy()
        rows = [_make_sm_row("005930")]

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)) as mock_lbf:
            result = asyncio.run(strategy._scan_universe())
            mock_lbf.assert_called_once()

        assert result == ["005930"]

    def test_h2_no_fhpst01710000_tr_id_in_source(self):
        """AST 영구 가드 — volatility_breakout.py 소스에 FHPST01710000 가 없다."""
        import ast
        import pathlib

        src_file = pathlib.Path(
            "src/engine/strategies/volatility_breakout.py"
        )
        source = src_file.read_text(encoding="utf-8")
        assert "FHPST01710000" not in source, (
            "VB _scan_universe 에 KIS volume-rank TR_ID (FHPST01710000) 가 잔존함 — "
            "사이클 108 stock_master 전환 이후 완전 폐기 의무"
        )

    def test_h2_no_volume_rank_url_in_source(self):
        """AST 영구 가드 — volatility_breakout.py 소스에 volume-rank URL 이 없다."""
        import pathlib

        src_file = pathlib.Path("src/engine/strategies/volatility_breakout.py")
        source = src_file.read_text(encoding="utf-8")
        assert "volume-rank" not in source, (
            "VB _scan_universe 에 KIS volume-rank URL 경로가 잔존함"
        )


# ---------------------------------------------------------------------------
# MEDIUM-1: ETF 제외 + 6자리 종목코드 영속
# ---------------------------------------------------------------------------

class TestVbScanUniverseMedium1:
    """MEDIUM-1: ETF 제외 + 6자리 종목코드 검증 영속."""

    def test_m1_etf_ticker_excluded_by_name(self):
        """ETF 키워드 포함 종목명(TIGER, KODEX 등)이 결과에서 제외된다."""
        strategy = _make_strategy()
        rows = [
            _make_sm_row("069500", name="KODEX 200"),    # ETF — 제외
            _make_sm_row("005930", name="삼성전자"),       # 일반주 — 통과
        ]

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)):
            result = asyncio.run(strategy._scan_universe())

        assert "069500" not in result
        assert "005930" in result

    def test_m1_non_6digit_ticker_excluded(self):
        """6자리 숫자가 아닌 종목코드(ETN 등)가 제외된다."""
        strategy = _make_strategy()
        rows = [
            _make_sm_row("Q52010", name="ETN종목"),   # 알파벳 포함 — 제외
            _make_sm_row("005930", name="삼성전자"),
        ]

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)):
            result = asyncio.run(strategy._scan_universe())

        assert "Q52010" not in result
        assert "005930" in result


# ---------------------------------------------------------------------------
# MEDIUM-2: funnel 카운터 영속
# ---------------------------------------------------------------------------

class TestVbScanUniverseMedium2:
    """MEDIUM-2: universe_candidates / universe_filtered / last_run_at 카운터 영속."""

    def test_m2_universe_candidates_set(self):
        """universe_candidates 가 DB 반환 행수로 설정된다."""
        strategy = _make_strategy()
        rows = [_make_sm_row(f"{i:06d}") for i in range(1, 11)]

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)):
            asyncio.run(strategy._scan_universe())

        assert strategy._scan_stats["universe_candidates"] == 10

    def test_m2_universe_filtered_reflects_etf_exclusion(self):
        """universe_filtered 가 ETF 제외 후 실제 통과 수로 설정된다."""
        strategy = _make_strategy()
        rows = [
            _make_sm_row("069500", name="KODEX 200"),  # 제외
            _make_sm_row("005930", name="삼성전자"),    # 통과
            _make_sm_row("000660", name="SK하이닉스"),  # 통과
        ]

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)):
            asyncio.run(strategy._scan_universe())

        assert strategy._scan_stats["universe_candidates"] == 3
        assert strategy._scan_stats["universe_filtered"] == 2

    def test_m2_last_run_at_set_to_kst_iso(self):
        """last_run_at 이 KST ISO 형식 문자열로 설정된다."""
        strategy = _make_strategy()
        rows = [_make_sm_row("005930")]

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)):
            asyncio.run(strategy._scan_universe())

        last_run_at = strategy._scan_stats["last_run_at"]
        assert last_run_at is not None
        assert "+09:00" in last_run_at or "09:00" in last_run_at
