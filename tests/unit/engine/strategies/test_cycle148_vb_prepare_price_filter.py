"""사이클 148 — VB prepare() 영역 가격 max 필터 추가 회귀 가드.

사용자 결정: Q1=B (VB 단독) + Q2=C (PriceFilter 단일 source) + Q3=A (scanner 유지) + Q4=B (MEDIUM).

운영 실증 (6/16 11:11:27~30 KST):
- 6 종목 (298040 / 000660 / 009150 / 402340 / 011070 / 012450) bfdy_clpr > max=500,000
- scanner `_apply_price_filter` 차단 발화 -> UI funnel snapshot에 차단 종목 노출 결함
- 근본 원인: VB `_scan_universe()` 가격 필터 부재 (시총+거래대금만)

회귀 가드 10개 (HIGH 4 = 40%):
- G-148-PRICE-1 HIGH: VB prepare 가격 max 차단 직접 검증
- G-148-PRICE-2 MEDIUM: 가격 min 동행
- G-148-PRICE-3 MEDIUM: PriceFilter 비활성 시 전수 통과 (회귀)
- G-148-PRICE-4 LOW: scanner `_apply_price_filter` 변경 0 (AST)
- G-148-PRICE-5 LOW: list_by_filter 시그너처 변경 0 (AST)
- G-148-FUNNEL-1 LOW: VB_FUNNEL_STAGES 변경 0
- G-AST-148 LOW: VB prepare PriceFilter 단일 source AST
- G-148-SAFETY-1 HIGH: VB prepare check_exit_signal 호출 0건
- G-148-SAFETY-2 HIGH: risk.on_tick / order_engine import 0
- G-148-SAFETY-3 HIGH: 보유 종목 가격 필터 차단 0건
"""

from __future__ import annotations

import ast
import asyncio
import pathlib
from datetime import timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

KST = timezone(timedelta(hours=9))

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_VB_SOURCE_PATH = _REPO_ROOT / "src" / "engine" / "strategies" / "volatility_breakout.py"
_SCANNER_SOURCE_PATH = _REPO_ROOT / "src" / "engine" / "scanner.py"
_LIST_BY_FILTER_PATH = _REPO_ROOT / "src" / "db" / "stock_master.py"


def _make_strategy(min_price: int = 0, max_price: int = 0):
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

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


def _make_sm_row(ticker: str, *, name: str = "테스트종목") -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": "02",
        "nxt_tradable": True,
        "raw": {
            "hts_avls": "1000000",
            "acml_tr_pbmn": "50000000000",
        },
    }


def _make_basics(ticker: str, bfdy_clpr: int):
    sm = MagicMock()
    sm.ticker = ticker
    sm.raw = {"bfdy_clpr": str(bfdy_clpr)}
    return sm


# ---------------------------------------------------------------------------
# G-148-PRICE-1 (HIGH) — VB prepare 가격 max 차단 직접 검증
# ---------------------------------------------------------------------------

class TestVbPrepareAboveMaxBlocked:
    """G-148-PRICE-1: 6 종목 운영 실증 시나리오 — max=500_000 초과 차단."""

    def test_above_max_tickers_excluded(self):
        from src.db.system_config import PriceFilter

        strategy = _make_strategy()
        # 운영 실증 6 종목 + 통과 종목 1개
        rows = [
            _make_sm_row("298040"),
            _make_sm_row("000660"),
            _make_sm_row("009150"),
            _make_sm_row("402340"),
            _make_sm_row("011070"),
            _make_sm_row("012450"),
            _make_sm_row("005930"),  # 통과 (450_000)
        ]
        basics_map = {
            "298040": _make_basics("298040", 600_000),
            "000660": _make_basics("000660", 650_000),
            "009150": _make_basics("009150", 700_000),
            "402340": _make_basics("402340", 800_000),
            "011070": _make_basics("011070", 550_000),
            "012450": _make_basics("012450", 750_000),
            "005930": _make_basics("005930", 450_000),
        }

        async def _get(ticker):
            return basics_map.get(ticker)

        pf = PriceFilter(min_price=0, max_price=500_000)

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)), \
             patch("src.db.stock_master.get", new=AsyncMock(side_effect=_get)), \
             patch("src.db.system_config.get_price_filter", new=AsyncMock(return_value=pf)):
            result = asyncio.run(strategy._scan_universe())

        # 6 종목 차단 + 005930 통과
        assert "005930" in result
        assert "298040" not in result
        assert "000660" not in result
        assert "009150" not in result
        assert "402340" not in result
        assert "011070" not in result
        assert "012450" not in result


# ---------------------------------------------------------------------------
# G-148-PRICE-2 (MEDIUM) — 가격 min 동행
# ---------------------------------------------------------------------------

class TestVbPrepareBelowMinBlocked:
    """G-148-PRICE-2: min=5_000 미만 차단."""

    def test_below_min_tickers_excluded(self):
        from src.db.system_config import PriceFilter

        strategy = _make_strategy()
        rows = [
            _make_sm_row("100001"),
            _make_sm_row("100002"),
            _make_sm_row("100003"),
        ]
        basics_map = {
            "100001": _make_basics("100001", 3_000),  # 차단
            "100002": _make_basics("100002", 4_000),  # 차단
            "100003": _make_basics("100003", 6_000),  # 통과
        }

        async def _get(ticker):
            return basics_map.get(ticker)

        pf = PriceFilter(min_price=5_000, max_price=0)

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)), \
             patch("src.db.stock_master.get", new=AsyncMock(side_effect=_get)), \
             patch("src.db.system_config.get_price_filter", new=AsyncMock(return_value=pf)):
            result = asyncio.run(strategy._scan_universe())

        assert "100001" not in result
        assert "100002" not in result
        assert "100003" in result


# ---------------------------------------------------------------------------
# G-148-PRICE-3 (MEDIUM) — PriceFilter 비활성 시 전수 통과 (회귀 보존)
# ---------------------------------------------------------------------------

class TestVbPrepareInactivePassthrough:
    """G-148-PRICE-3: PriceFilter min=0, max=0 시 모든 종목 통과."""

    def test_inactive_filter_all_pass(self):
        from src.db.system_config import PriceFilter

        strategy = _make_strategy()
        rows = [_make_sm_row("005930"), _make_sm_row("000660"), _make_sm_row("100001")]

        pf = PriceFilter(min_price=0, max_price=0)
        assert pf.is_active is False

        # get 호출 0건 가드 (필터 비활성 시 호출 자체 안 함)
        get_mock = AsyncMock()

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)), \
             patch("src.db.stock_master.get", new=get_mock), \
             patch("src.db.system_config.get_price_filter", new=AsyncMock(return_value=pf)):
            result = asyncio.run(strategy._scan_universe())

        assert set(result) == {"005930", "000660", "100001"}


# ---------------------------------------------------------------------------
# G-148-PRICE-4 (LOW) — scanner `_apply_price_filter` 변경 0 (AST)
# ---------------------------------------------------------------------------

class TestScannerApplyPriceFilterUnchanged:
    """G-148-PRICE-4: scanner `_apply_price_filter` 함수 영속 (이중 안전망)."""

    def test_scanner_apply_price_filter_function_exists(self):
        tree = ast.parse(_SCANNER_SOURCE_PATH.read_text())
        names = [
            n.name for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_apply_price_filter"
        ]
        assert "_apply_price_filter" in names, (
            "scanner._apply_price_filter 영역 폐기 금지 (사이클 64 이중 안전망 영속)"
        )

    def test_scanner_protected_tickers_keyword_persistent(self):
        """protected_tickers= keyword 의무 영속 (사이클 64 G-2 가드 답습)."""
        source = _SCANNER_SOURCE_PATH.read_text()
        assert "protected_tickers: set[str]" in source, (
            "scanner._apply_price_filter protected_tickers keyword-only 영속 의무"
        )


# ---------------------------------------------------------------------------
# G-148-PRICE-5 (LOW) — list_by_filter 시그너처 변경 0 (AST)
# ---------------------------------------------------------------------------

class TestListByFilterSignatureUnchanged:
    """G-148-PRICE-5: stock_master.list_by_filter 시그너처 변경 0."""

    def test_list_by_filter_signature_persistent(self):
        tree = ast.parse(_LIST_BY_FILTER_PATH.read_text())
        target = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "list_by_filter":
                target = node
                break
        assert target is not None, "list_by_filter 함수 존재 의무"

        kwonly_names = {a.arg for a in target.args.kwonlyargs}
        required = {"market", "min_market_cap", "min_trade_amount", "exclude_tickers", "nxt_tradable", "limit"}
        missing = required - kwonly_names
        assert not missing, f"list_by_filter 시그너처 변경 금지 — missing={missing}"


# ---------------------------------------------------------------------------
# G-148-FUNNEL-1 (LOW) — VB_FUNNEL_STAGES 5 단계 영속
# ---------------------------------------------------------------------------

class TestVbFunnelStagesUnchanged:
    """G-148-FUNNEL-1: VB_FUNNEL_STAGES 5 단계 영속 (사이클 143)."""

    def test_vb_funnel_stages_five_steps(self):
        from src.engine.strategies.volatility_breakout import VB_FUNNEL_STAGES

        assert len(VB_FUNNEL_STAGES) == 5, "VB 5 단계 funnel 영속 (사이클 143)"
        assert VB_FUNNEL_STAGES[0].step_no == 1
        assert VB_FUNNEL_STAGES[4].step_no == 5


# ---------------------------------------------------------------------------
# G-AST-148 (LOW) — VB prepare PriceFilter 단일 source AST 가드
# ---------------------------------------------------------------------------

class TestVbPriceFilterSingleSource:
    """G-AST-148: VB prepare 영역에서 system_config.get_price_filter 호출."""

    def test_vb_imports_get_price_filter(self):
        """VB 소스에 get_price_filter import 또는 사용 영속."""
        source = _VB_SOURCE_PATH.read_text()
        assert "get_price_filter" in source, (
            "VB prepare 영역 PriceFilter 단일 source 영속 의무 "
            "(system_config.get_price_filter 호출)"
        )

    def test_vb_no_separate_price_keys_in_default_params(self):
        """VB DEFAULT_PARAMS에 별도 가격 키 추가 금지 (단일 source 영속)."""
        from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

        params = VolatilityBreakoutStrategy.DEFAULT_PARAMS
        # 별도 키 추가 금지
        forbidden = {"vb_price_min", "vb_price_max", "price_min", "price_max"}
        leaked = forbidden & set(params.keys())
        assert not leaked, f"VB DEFAULT_PARAMS 별도 가격 키 추가 금지 — leaked={leaked}"


# ---------------------------------------------------------------------------
# G-148-SAFETY-1 (HIGH) — VB prepare check_exit_signal 호출 0건
# ---------------------------------------------------------------------------

class TestVbPrepareNoCheckExitSignal:
    """G-148-SAFETY-1: VB prepare 본체 check_exit_signal 호출 0건 (매매 안전성)."""

    def test_vb_prepare_no_check_exit_signal_call(self):
        tree = ast.parse(_VB_SOURCE_PATH.read_text())
        prepare_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "prepare":
                prepare_node = node
                break
        assert prepare_node is not None

        # check_exit_signal 호출 검출
        forbidden_calls = []
        for sub in ast.walk(prepare_node):
            if isinstance(sub, ast.Call):
                # foo.check_exit_signal(...) 또는 check_exit_signal(...)
                func = sub.func
                name = None
                if isinstance(func, ast.Attribute):
                    name = func.attr
                elif isinstance(func, ast.Name):
                    name = func.id
                if name == "check_exit_signal":
                    forbidden_calls.append(name)
        assert not forbidden_calls, (
            f"VB prepare 본체 check_exit_signal 호출 금지 (매매 안전성) — found={forbidden_calls}"
        )


# ---------------------------------------------------------------------------
# G-148-SAFETY-2 (HIGH) — risk.on_tick / order_engine import 0
# ---------------------------------------------------------------------------

class TestVbNoRiskOrderImport:
    """G-148-SAFETY-2: VB 소스 risk.on_tick / order_engine import 0."""

    def test_vb_no_risk_on_tick_import(self):
        source = _VB_SOURCE_PATH.read_text()
        # import 또는 from import 모두 0
        forbidden_patterns = [
            "from src.engine.risk",
            "from src.engine.order_engine",
            "from src.engine import risk",
            "from src.engine import order_engine",
        ]
        for pattern in forbidden_patterns:
            assert pattern not in source, (
                f"VB 소스 매매 안전성 영역 import 금지 — found={pattern!r}"
            )


# ---------------------------------------------------------------------------
# G-148-SAFETY-3 (HIGH) — 보유 종목 가격 필터 차단 0건
# ---------------------------------------------------------------------------

class TestVbPreparePositionsProtected:
    """G-148-SAFETY-3: 보유 종목 가격 필터 차단 0건 (사이클 32 R4 답습)."""

    def test_held_ticker_passes_even_above_max(self):
        from src.db.system_config import PriceFilter
        from src.engine.strategy_base import Position

        strategy = _make_strategy()
        # 보유 종목 등록 — bfdy_clpr 가 max 초과해도 통과 의무
        held_ticker = "005930"
        strategy.state.positions[held_ticker] = Position(
            ticker=held_ticker,
            buy_price=600_000,
            quantity=10,
            order_no="TEST_ORDER",
            strategy_id="volatility_breakout",
        )

        rows = [_make_sm_row(held_ticker)]
        basics_map = {held_ticker: _make_basics(held_ticker, 700_000)}  # max=500_000 초과

        async def _get(ticker):
            return basics_map.get(ticker)

        pf = PriceFilter(min_price=0, max_price=500_000)

        # registry 주입 — scanner _collect_protected_tickers_for_scanner 답습
        mock_registry = MagicMock()
        mock_strategy_wrapper = MagicMock()
        mock_strategy_wrapper.state = strategy.state
        mock_registry.all.return_value = [mock_strategy_wrapper]

        with patch("src.db.stock_master.list_by_filter", new=AsyncMock(return_value=rows)), \
             patch("src.db.stock_master.get", new=AsyncMock(side_effect=_get)), \
             patch("src.db.system_config.get_price_filter", new=AsyncMock(return_value=pf)), \
             patch("src.engine.scanner.registry", mock_registry, create=True):
            result = asyncio.run(strategy._scan_universe())

        assert held_ticker in result, (
            "보유 종목 가격 필터 차단 0건 의무 (사이클 32 R4 답습 + 사이클 30 005935 영속)"
        )
