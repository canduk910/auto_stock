"""사이클 151 — 4 전략 (LTV/donchian/BFB/VCP) prepare() 가격 필터 확대 회귀 가드.

사용자 결정: 사이클 148 VB 패턴 4 전략 확대 (사이클 148 영구 영속 + Q2=C 단일 source + Q4=B MEDIUM).

각 전략 9 케이스 × 4 = 36 케이스 + 공통 4 케이스 (AST + INT) = 40 케이스.

회귀 가드 영역:
- G-151-*-PRICE-1 (HIGH): 가격 max 차단 (사이클 148 운영 실증 답습)
- G-151-*-PRICE-2: 가격 min 차단
- G-151-*-PRICE-3: PriceFilter 비활성 시 전수 통과 (회귀 보존)
- G-151-*-PRICE-4: raw.bfdy_clpr miss graceful 통과
- G-151-*-PRICE-5: stock_master.get() 예외 graceful 통과
- G-151-*-SAFETY-1 (HIGH): prepare 본체 check_exit_signal 호출 0건
- G-151-*-SAFETY-2 (HIGH): risk/order_engine import 0
- G-151-*-SAFETY-3 (HIGH): 보유 종목 가격 필터 차단 0건
- G-151-*-AST-1: get_price_filter import 의무
- G-151-COMMON-AST-1: 4 전략 DEFAULT_PARAMS 별도 가격 키 금지
- G-151-COMMON-INT-1: scanner _apply_price_filter 영속 (변경 0)
- G-151-COMMON-INT-2: protected_tickers keyword 영속
- G-151-COMMON-AST-2: 4 전략 _apply_price_filter_in_prepare 메서드 정의 의무
"""

from __future__ import annotations

import ast
import asyncio
import pathlib
from datetime import timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

KST = timezone(timedelta(hours=9))

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_LTV_SOURCE_PATH = _REPO_ROOT / "src" / "engine" / "strategies" / "long_tail_volatility.py"
_DC_SOURCE_PATH = _REPO_ROOT / "src" / "engine" / "strategies" / "donchian_swing.py"
_BFB_SOURCE_PATH = _REPO_ROOT / "src" / "engine" / "strategies" / "bull_flag_breakout.py"
_VCP_SOURCE_PATH = _REPO_ROOT / "src" / "engine" / "strategies" / "vcp_breakout.py"
_SCANNER_SOURCE_PATH = _REPO_ROOT / "src" / "engine" / "scanner.py"

_STRATEGY_PATHS = {
    "ltv": _LTV_SOURCE_PATH,
    "dc": _DC_SOURCE_PATH,
    "bfb": _BFB_SOURCE_PATH,
    "vcp": _VCP_SOURCE_PATH,
}


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def _make_sm_row(ticker: str, *, name: str = "테스트종목") -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": "02",
        "nxt_tradable": True,
        "raw": {
            "hts_avls": "5000000",  # 시총 5000억 (donchian/VCP 1000억 임계 통과)
            "acml_tr_pbmn": "50000000000",
        },
    }


def _make_basics(ticker: str, bfdy_clpr: int):
    sm = MagicMock()
    sm.ticker = ticker
    sm.raw = {"bfdy_clpr": str(bfdy_clpr)}
    return sm


def _make_ltv_strategy():
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
    from src.engine.strategy_base import StrategyConfig

    config = StrategyConfig(
        strategy_id="long_tail_volatility",
        name="롱테일변동성돌파",
        params={
            "min_market_cap": 100_000_000_000,
            "min_trade_amount": 20_000_000_000,
            "max_scan_stocks": 100,
        },
    )
    return LongTailVolatilityStrategy(config)


def _make_dc_strategy():
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy
    from src.engine.strategy_base import StrategyConfig

    config = StrategyConfig(
        strategy_id="donchian_swing",
        name="도치안스윙",
        params={
            "min_market_cap": 100_000_000_000,
            "min_trade_amount": 5_000_000_000,
            "max_scan_stocks": 100,
        },
    )
    return DonchianSwingStrategy(config)


def _make_bfb_strategy():
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    config = StrategyConfig(
        strategy_id="bull_flag_breakout",
        name="눌림목돌파",
        params={
            "min_market_cap": 50_000_000_000,
            "min_trade_amount": 2_000_000_000,
            "max_scan_stocks": 100,
        },
    )
    return BullFlagBreakoutStrategy(config)


def _make_vcp_strategy():
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    config = StrategyConfig(
        strategy_id="vcp_breakout",
        name="VCP돌파",
        params={
            "min_market_cap": 100_000_000_000,
            "max_scan_stocks": 100,
        },
    )
    return VcpBreakoutStrategy(config)


_STRATEGY_FACTORIES = {
    "ltv": _make_ltv_strategy,
    "dc": _make_dc_strategy,
    "bfb": _make_bfb_strategy,
    "vcp": _make_vcp_strategy,
}

_STRATEGY_PREFIXES = {
    "ltv": "ltv_price_filter_prepare",
    "dc": "dc_price_filter_prepare",
    "bfb": "bfb_price_filter_prepare",
    "vcp": "vcp_price_filter_prepare",
}


# ---------------------------------------------------------------------------
# 단일 전략 통합 테스트 헬퍼 — 4 전략 prepare() 가격 필터 확인
# ---------------------------------------------------------------------------

def _run_apply_price_filter(strategy, tickers, basics_map, pf, *, protected=None):
    """4 전략 _apply_price_filter_in_prepare 직접 호출 검증."""
    async def _get(ticker):
        return basics_map.get(ticker)

    protected_set = set(protected or [])

    with patch("src.db.stock_master.get", new=AsyncMock(side_effect=_get)), \
         patch("src.db.system_config.get_price_filter", new=AsyncMock(return_value=pf)), \
         patch(
             "src.engine.scanner._collect_protected_tickers_for_scanner",
             return_value=protected_set,
             create=True,
         ):
        return asyncio.run(strategy._apply_price_filter_in_prepare(tickers))


# ===========================================================================
# G-151-LTV — LongTailVolatility 전략
# ===========================================================================

class TestLtvPriceFilterInPrepare:
    """G-151-LTV: LTV prepare 가격 필터 후처리 회귀 가드."""

    def test_ltv_above_max_blocked(self):
        """G-151-LTV-PRICE-1 (HIGH): max 초과 차단."""
        from src.db.system_config import PriceFilter

        strategy = _make_ltv_strategy()
        tickers = ["298040", "000660", "005930"]
        basics_map = {
            "298040": _make_basics("298040", 600_000),
            "000660": _make_basics("000660", 700_000),
            "005930": _make_basics("005930", 450_000),
        }
        pf = PriceFilter(min_price=0, max_price=500_000)

        result = _run_apply_price_filter(strategy, tickers, basics_map, pf)
        assert "005930" in result
        assert "298040" not in result
        assert "000660" not in result

    def test_ltv_below_min_blocked(self):
        """G-151-LTV-PRICE-2: min 미달 차단."""
        from src.db.system_config import PriceFilter

        strategy = _make_ltv_strategy()
        tickers = ["100001", "100002", "100003"]
        basics_map = {
            "100001": _make_basics("100001", 3_000),
            "100002": _make_basics("100002", 4_000),
            "100003": _make_basics("100003", 6_000),
        }
        pf = PriceFilter(min_price=5_000, max_price=0)

        result = _run_apply_price_filter(strategy, tickers, basics_map, pf)
        assert "100001" not in result
        assert "100002" not in result
        assert "100003" in result

    def test_ltv_inactive_passthrough(self):
        """G-151-LTV-PRICE-3: PriceFilter 비활성 시 전수 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_ltv_strategy()
        tickers = ["005930", "000660", "100001"]
        pf = PriceFilter(min_price=0, max_price=0)
        result = _run_apply_price_filter(strategy, tickers, {}, pf)
        assert set(result) == {"005930", "000660", "100001"}

    def test_ltv_bfdy_clpr_miss_graceful(self):
        """G-151-LTV-PRICE-4: raw.bfdy_clpr miss → graceful 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_ltv_strategy()
        tickers = ["100001"]
        # raw 에 bfdy_clpr 키 없음
        sm = MagicMock()
        sm.ticker = "100001"
        sm.raw = {"hts_avls": "1000000"}
        basics_map = {"100001": sm}
        pf = PriceFilter(min_price=5_000, max_price=500_000)

        result = _run_apply_price_filter(strategy, tickers, basics_map, pf)
        assert "100001" in result, "raw.bfdy_clpr miss graceful 통과 (사이클 64 답습)"

    def test_ltv_stock_master_exception_graceful(self):
        """G-151-LTV-PRICE-5: stock_master.get() 예외 → graceful 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_ltv_strategy()
        tickers = ["100001"]
        pf = PriceFilter(min_price=5_000, max_price=500_000)

        async def _get_raise(ticker):
            raise RuntimeError("DB 일시 결함")

        with patch("src.db.stock_master.get", new=AsyncMock(side_effect=_get_raise)), \
             patch("src.db.system_config.get_price_filter", new=AsyncMock(return_value=pf)), \
             patch(
                 "src.engine.scanner._collect_protected_tickers_for_scanner",
                 return_value=set(),
                 create=True,
             ):
            result = asyncio.run(strategy._apply_price_filter_in_prepare(tickers))

        assert "100001" in result, "stock_master 예외 graceful 통과 (사이클 88 G-REJECT 답습)"

    def test_ltv_held_ticker_protected(self):
        """G-151-LTV-SAFETY-3 (HIGH): 보유 종목 가격 필터 차단 0건."""
        from src.db.system_config import PriceFilter

        strategy = _make_ltv_strategy()
        tickers = ["005930"]
        basics_map = {"005930": _make_basics("005930", 700_000)}  # max=500_000 초과
        pf = PriceFilter(min_price=0, max_price=500_000)

        result = _run_apply_price_filter(
            strategy, tickers, basics_map, pf, protected={"005930"}
        )
        assert "005930" in result, "보유 종목 절대 보호 (사이클 32 R4 + 사이클 30 005935 영속)"


# ===========================================================================
# G-151-DC — DonchianSwing 전략
# ===========================================================================

class TestDcPriceFilterInPrepare:
    """G-151-DC: donchian_swing prepare 가격 필터 후처리 회귀 가드."""

    def test_dc_above_max_blocked(self):
        """G-151-DC-PRICE-1 (HIGH): max 초과 차단."""
        from src.db.system_config import PriceFilter

        strategy = _make_dc_strategy()
        tickers = ["298040", "000660", "005930"]
        basics_map = {
            "298040": _make_basics("298040", 600_000),
            "000660": _make_basics("000660", 700_000),
            "005930": _make_basics("005930", 450_000),
        }
        pf = PriceFilter(min_price=0, max_price=500_000)
        result = _run_apply_price_filter(strategy, tickers, basics_map, pf)
        assert "005930" in result
        assert "298040" not in result
        assert "000660" not in result

    def test_dc_below_min_blocked(self):
        """G-151-DC-PRICE-2: min 미달 차단."""
        from src.db.system_config import PriceFilter

        strategy = _make_dc_strategy()
        tickers = ["100001", "100002", "100003"]
        basics_map = {
            "100001": _make_basics("100001", 3_000),
            "100002": _make_basics("100002", 4_000),
            "100003": _make_basics("100003", 6_000),
        }
        pf = PriceFilter(min_price=5_000, max_price=0)
        result = _run_apply_price_filter(strategy, tickers, basics_map, pf)
        assert "100001" not in result
        assert "100002" not in result
        assert "100003" in result

    def test_dc_inactive_passthrough(self):
        """G-151-DC-PRICE-3: PriceFilter 비활성 시 전수 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_dc_strategy()
        tickers = ["005930", "000660", "100001"]
        pf = PriceFilter(min_price=0, max_price=0)
        result = _run_apply_price_filter(strategy, tickers, {}, pf)
        assert set(result) == {"005930", "000660", "100001"}

    def test_dc_bfdy_clpr_miss_graceful(self):
        """G-151-DC-PRICE-4: raw.bfdy_clpr miss → graceful 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_dc_strategy()
        tickers = ["100001"]
        sm = MagicMock()
        sm.ticker = "100001"
        sm.raw = {"hts_avls": "1000000"}
        basics_map = {"100001": sm}
        pf = PriceFilter(min_price=5_000, max_price=500_000)
        result = _run_apply_price_filter(strategy, tickers, basics_map, pf)
        assert "100001" in result

    def test_dc_stock_master_exception_graceful(self):
        """G-151-DC-PRICE-5: stock_master.get() 예외 → graceful 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_dc_strategy()
        pf = PriceFilter(min_price=5_000, max_price=500_000)

        async def _get_raise(ticker):
            raise RuntimeError("DB 일시 결함")

        with patch("src.db.stock_master.get", new=AsyncMock(side_effect=_get_raise)), \
             patch("src.db.system_config.get_price_filter", new=AsyncMock(return_value=pf)), \
             patch(
                 "src.engine.scanner._collect_protected_tickers_for_scanner",
                 return_value=set(),
                 create=True,
             ):
            result = asyncio.run(strategy._apply_price_filter_in_prepare(["100001"]))

        assert "100001" in result

    def test_dc_held_ticker_protected(self):
        """G-151-DC-SAFETY-3 (HIGH): 보유 종목 가격 필터 차단 0건."""
        from src.db.system_config import PriceFilter

        strategy = _make_dc_strategy()
        tickers = ["005930"]
        basics_map = {"005930": _make_basics("005930", 700_000)}
        pf = PriceFilter(min_price=0, max_price=500_000)
        result = _run_apply_price_filter(
            strategy, tickers, basics_map, pf, protected={"005930"}
        )
        assert "005930" in result


# ===========================================================================
# G-151-BFB — BullFlagBreakout 전략
# ===========================================================================

class TestBfbPriceFilterInPrepare:
    """G-151-BFB: bull_flag_breakout prepare 가격 필터 후처리 회귀 가드."""

    def test_bfb_above_max_blocked(self):
        """G-151-BFB-PRICE-1 (HIGH): max 초과 차단."""
        from src.db.system_config import PriceFilter

        strategy = _make_bfb_strategy()
        tickers = ["298040", "000660", "005930"]
        basics_map = {
            "298040": _make_basics("298040", 600_000),
            "000660": _make_basics("000660", 700_000),
            "005930": _make_basics("005930", 450_000),
        }
        pf = PriceFilter(min_price=0, max_price=500_000)
        result = _run_apply_price_filter(strategy, tickers, basics_map, pf)
        assert "005930" in result
        assert "298040" not in result
        assert "000660" not in result

    def test_bfb_below_min_blocked(self):
        """G-151-BFB-PRICE-2: min 미달 차단."""
        from src.db.system_config import PriceFilter

        strategy = _make_bfb_strategy()
        tickers = ["100001", "100002", "100003"]
        basics_map = {
            "100001": _make_basics("100001", 3_000),
            "100002": _make_basics("100002", 4_000),
            "100003": _make_basics("100003", 6_000),
        }
        pf = PriceFilter(min_price=5_000, max_price=0)
        result = _run_apply_price_filter(strategy, tickers, basics_map, pf)
        assert "100001" not in result
        assert "100002" not in result
        assert "100003" in result

    def test_bfb_inactive_passthrough(self):
        """G-151-BFB-PRICE-3: PriceFilter 비활성 시 전수 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_bfb_strategy()
        tickers = ["005930", "000660", "100001"]
        pf = PriceFilter(min_price=0, max_price=0)
        result = _run_apply_price_filter(strategy, tickers, {}, pf)
        assert set(result) == {"005930", "000660", "100001"}

    def test_bfb_bfdy_clpr_miss_graceful(self):
        """G-151-BFB-PRICE-4: raw.bfdy_clpr miss → graceful 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_bfb_strategy()
        sm = MagicMock()
        sm.ticker = "100001"
        sm.raw = {"hts_avls": "1000000"}
        basics_map = {"100001": sm}
        pf = PriceFilter(min_price=5_000, max_price=500_000)
        result = _run_apply_price_filter(strategy, ["100001"], basics_map, pf)
        assert "100001" in result

    def test_bfb_stock_master_exception_graceful(self):
        """G-151-BFB-PRICE-5: stock_master.get() 예외 → graceful 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_bfb_strategy()
        pf = PriceFilter(min_price=5_000, max_price=500_000)

        async def _get_raise(ticker):
            raise RuntimeError("DB 일시 결함")

        with patch("src.db.stock_master.get", new=AsyncMock(side_effect=_get_raise)), \
             patch("src.db.system_config.get_price_filter", new=AsyncMock(return_value=pf)), \
             patch(
                 "src.engine.scanner._collect_protected_tickers_for_scanner",
                 return_value=set(),
                 create=True,
             ):
            result = asyncio.run(strategy._apply_price_filter_in_prepare(["100001"]))

        assert "100001" in result

    def test_bfb_held_ticker_protected(self):
        """G-151-BFB-SAFETY-3 (HIGH): 보유 종목 가격 필터 차단 0건."""
        from src.db.system_config import PriceFilter

        strategy = _make_bfb_strategy()
        tickers = ["005930"]
        basics_map = {"005930": _make_basics("005930", 700_000)}
        pf = PriceFilter(min_price=0, max_price=500_000)
        result = _run_apply_price_filter(
            strategy, tickers, basics_map, pf, protected={"005930"}
        )
        assert "005930" in result


# ===========================================================================
# G-151-VCP — VcpBreakout 전략
# ===========================================================================

class TestVcpPriceFilterInPrepare:
    """G-151-VCP: vcp_breakout prepare 가격 필터 후처리 회귀 가드."""

    def test_vcp_above_max_blocked(self):
        """G-151-VCP-PRICE-1 (HIGH): max 초과 차단."""
        from src.db.system_config import PriceFilter

        strategy = _make_vcp_strategy()
        tickers = ["298040", "000660", "005930"]
        basics_map = {
            "298040": _make_basics("298040", 600_000),
            "000660": _make_basics("000660", 700_000),
            "005930": _make_basics("005930", 450_000),
        }
        pf = PriceFilter(min_price=0, max_price=500_000)
        result = _run_apply_price_filter(strategy, tickers, basics_map, pf)
        assert "005930" in result
        assert "298040" not in result
        assert "000660" not in result

    def test_vcp_below_min_blocked(self):
        """G-151-VCP-PRICE-2: min 미달 차단."""
        from src.db.system_config import PriceFilter

        strategy = _make_vcp_strategy()
        tickers = ["100001", "100002", "100003"]
        basics_map = {
            "100001": _make_basics("100001", 3_000),
            "100002": _make_basics("100002", 4_000),
            "100003": _make_basics("100003", 6_000),
        }
        pf = PriceFilter(min_price=5_000, max_price=0)
        result = _run_apply_price_filter(strategy, tickers, basics_map, pf)
        assert "100001" not in result
        assert "100002" not in result
        assert "100003" in result

    def test_vcp_inactive_passthrough(self):
        """G-151-VCP-PRICE-3: PriceFilter 비활성 시 전수 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_vcp_strategy()
        tickers = ["005930", "000660", "100001"]
        pf = PriceFilter(min_price=0, max_price=0)
        result = _run_apply_price_filter(strategy, tickers, {}, pf)
        assert set(result) == {"005930", "000660", "100001"}

    def test_vcp_bfdy_clpr_miss_graceful(self):
        """G-151-VCP-PRICE-4: raw.bfdy_clpr miss → graceful 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_vcp_strategy()
        sm = MagicMock()
        sm.ticker = "100001"
        sm.raw = {"hts_avls": "1000000"}
        basics_map = {"100001": sm}
        pf = PriceFilter(min_price=5_000, max_price=500_000)
        result = _run_apply_price_filter(strategy, ["100001"], basics_map, pf)
        assert "100001" in result

    def test_vcp_stock_master_exception_graceful(self):
        """G-151-VCP-PRICE-5: stock_master.get() 예외 → graceful 통과."""
        from src.db.system_config import PriceFilter

        strategy = _make_vcp_strategy()
        pf = PriceFilter(min_price=5_000, max_price=500_000)

        async def _get_raise(ticker):
            raise RuntimeError("DB 일시 결함")

        with patch("src.db.stock_master.get", new=AsyncMock(side_effect=_get_raise)), \
             patch("src.db.system_config.get_price_filter", new=AsyncMock(return_value=pf)), \
             patch(
                 "src.engine.scanner._collect_protected_tickers_for_scanner",
                 return_value=set(),
                 create=True,
             ):
            result = asyncio.run(strategy._apply_price_filter_in_prepare(["100001"]))

        assert "100001" in result

    def test_vcp_held_ticker_protected(self):
        """G-151-VCP-SAFETY-3 (HIGH): 보유 종목 가격 필터 차단 0건."""
        from src.db.system_config import PriceFilter

        strategy = _make_vcp_strategy()
        tickers = ["005930"]
        basics_map = {"005930": _make_basics("005930", 700_000)}
        pf = PriceFilter(min_price=0, max_price=500_000)
        result = _run_apply_price_filter(
            strategy, tickers, basics_map, pf, protected={"005930"}
        )
        assert "005930" in result


# ===========================================================================
# G-151-COMMON — 4 전략 공통 AST + INT 가드
# ===========================================================================

class TestCommonAstGuards:
    """G-151-COMMON: 4 전략 공통 AST + INT 가드."""

    def test_all_strategies_have_apply_price_filter_in_prepare_method(self):
        """G-151-COMMON-AST-2: 4 전략 _apply_price_filter_in_prepare 메서드 정의 의무."""
        missing = []
        for label, path in _STRATEGY_PATHS.items():
            tree = ast.parse(path.read_text())
            method_names = [
                n.name for n in ast.walk(tree)
                if isinstance(n, ast.AsyncFunctionDef)
                and n.name == "_apply_price_filter_in_prepare"
            ]
            if not method_names:
                missing.append(label)
        assert not missing, (
            f"4 전략 _apply_price_filter_in_prepare 메서드 정의 의무 — missing={missing}"
        )

    def test_all_strategies_import_get_price_filter(self):
        """G-151-COMMON-AST-1: 4 전략 get_price_filter 호출/import 영속."""
        missing = []
        for label, path in _STRATEGY_PATHS.items():
            source = path.read_text()
            if "get_price_filter" not in source:
                missing.append(label)
        assert not missing, (
            f"4 전략 get_price_filter 단일 source 영속 의무 — missing={missing}"
        )

    def test_all_strategies_no_separate_price_keys_in_default_params(self):
        """G-151-COMMON-AST-3: 4 전략 DEFAULT_PARAMS 별도 가격 키 금지."""
        from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
        from src.engine.strategies.donchian_swing import DonchianSwingStrategy
        from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
        from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

        forbidden = {"min_price", "max_price", "price_min", "price_max"}
        for label, cls in [
            ("ltv", LongTailVolatilityStrategy),
            ("dc", DonchianSwingStrategy),
            ("bfb", BullFlagBreakoutStrategy),
            ("vcp", VcpBreakoutStrategy),
        ]:
            params = cls.DEFAULT_PARAMS
            leaked = forbidden & set(params.keys())
            assert not leaked, (
                f"{label} DEFAULT_PARAMS 별도 가격 키 추가 금지 — leaked={leaked}"
            )

    def test_scanner_apply_price_filter_persistent(self):
        """G-151-COMMON-INT-1: scanner _apply_price_filter 영속 (이중 안전망)."""
        tree = ast.parse(_SCANNER_SOURCE_PATH.read_text())
        names = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_apply_price_filter"
        ]
        assert "_apply_price_filter" in names, (
            "scanner._apply_price_filter 영역 폐기 금지 (사이클 64 이중 안전망 영속)"
        )

    def test_scanner_protected_tickers_keyword_persistent(self):
        """G-151-COMMON-INT-2: scanner protected_tickers keyword 영속."""
        source = _SCANNER_SOURCE_PATH.read_text()
        assert "protected_tickers: set[str]" in source, (
            "scanner._apply_price_filter protected_tickers keyword-only 영속 의무"
        )


# ===========================================================================
# G-151-SAFETY-AST — 4 전략 매매 안전성 AST 가드
# ===========================================================================

class TestSafetyAstGuards:
    """G-151-SAFETY-AST: 4 전략 매매 안전성 영역 AST 가드."""

    def test_all_strategies_no_risk_order_import(self):
        """G-151-COMMON-SAFETY-2 (HIGH): risk / order_engine import 0."""
        forbidden_patterns = [
            "from src.engine.risk",
            "from src.engine.order_engine",
            "from src.engine import risk",
            "from src.engine import order_engine",
        ]
        for label, path in _STRATEGY_PATHS.items():
            source = path.read_text()
            for pattern in forbidden_patterns:
                assert pattern not in source, (
                    f"{label} 소스 매매 안전성 영역 import 금지 — found={pattern!r}"
                )

    def test_apply_price_filter_in_prepare_no_check_exit_signal(self):
        """G-151-COMMON-SAFETY-1 (HIGH): _apply_price_filter_in_prepare 본체 check_exit_signal 호출 0건."""
        for label, path in _STRATEGY_PATHS.items():
            tree = ast.parse(path.read_text())
            target = None
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "_apply_price_filter_in_prepare":
                    target = node
                    break
            assert target is not None, f"{label} _apply_price_filter_in_prepare 메서드 부재"
            forbidden_calls = []
            for sub in ast.walk(target):
                if isinstance(sub, ast.Call):
                    func = sub.func
                    name = None
                    if isinstance(func, ast.Attribute):
                        name = func.attr
                    elif isinstance(func, ast.Name):
                        name = func.id
                    if name == "check_exit_signal":
                        forbidden_calls.append(name)
            assert not forbidden_calls, (
                f"{label} _apply_price_filter_in_prepare 본체 check_exit_signal 호출 금지 (매매 안전성)"
            )

    def test_all_strategies_apply_price_filter_called_in_scan_universe(self):
        """G-151-COMMON-AST-4: 4 전략 _scan_universe 본체에서 _apply_price_filter_in_prepare 호출 영속."""
        missing = []
        for label, path in _STRATEGY_PATHS.items():
            tree = ast.parse(path.read_text())
            scan_node = None
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "_scan_universe":
                    scan_node = node
                    break
            if scan_node is None:
                missing.append(f"{label}:_scan_universe missing")
                continue
            found = False
            for sub in ast.walk(scan_node):
                if isinstance(sub, ast.Call):
                    func = sub.func
                    name = None
                    if isinstance(func, ast.Attribute):
                        name = func.attr
                    elif isinstance(func, ast.Name):
                        name = func.id
                    if name == "_apply_price_filter_in_prepare":
                        found = True
                        break
            if not found:
                missing.append(label)
        assert not missing, (
            f"4 전략 _scan_universe 본체 _apply_price_filter_in_prepare 호출 영속 의무 — missing={missing}"
        )
