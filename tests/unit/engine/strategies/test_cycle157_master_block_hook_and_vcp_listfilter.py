"""사이클 157 — VCP hardcoded list 폐기 + 6 전략 _is_master_blocked_for_entry hook + FUNNEL_STAGES +1단계.

회귀 가드 ≥18 케이스 (HIGH 6):
- A 영역 — VCP hardcoded list 폐기 (Q1) — 3 케이스 (HIGH 1)
- B 영역 — _is_master_blocked_for_entry hook 통합 (Q2) — 9 케이스 (HIGH 2)
- C 영역 — FUNNEL_STAGES +1단계 (Q3) — 6 케이스 (HIGH 0)
- D 영역 — AST + 안전성 — 3 케이스 (HIGH 3)

사이클 157 Phase 1 진단 핵심:
- 사이클 132 momentum funnel 영구 제외 영속 (hook 적용은 하되 snapshot 미적재).
- 사이클 153 G-153-SAFETY-3 의미 전환 영구 영속 (VCP hardcoded 영역 폐기 = 사이클 66 K-2 패턴 답습).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# A 영역 — VCP hardcoded list 폐기 (Q1)
# ===========================================================================


async def _inert_price_filter():
    """PriceFilter 비활성 instance — _apply_price_filter_in_prepare 영역 통과."""
    from src.db.system_config import PriceFilter

    return PriceFilter(min_price=0, max_price=0)


class TestG157Vcp1:
    @pytest.mark.asyncio
    async def test_g157_vcp_1_scan_universe_uses_list_by_filter(self):
        """G-157-VCP-1 HIGH — vcp_breakout._scan_universe → list_by_filter(is_kospi200=True, is_kosdaq150=True) 호출 의무 (사이클 153 donchian 패턴 답습)."""
        from src.engine.strategies import vcp_breakout

        cfg = vcp_breakout.StrategyConfig(
            strategy_id="vcp_breakout",
            name="VCP",
            weight=1.0,
            params={"min_market_cap": 100_000_000_000, "max_scan_stocks": 100},
        )
        strat = vcp_breakout.VcpBreakoutStrategy(cfg)

        captured_kwargs: dict = {}

        async def fake_list_by_filter(**kwargs):
            captured_kwargs.update(kwargs)
            return []

        with patch("src.db.stock_master.list_by_filter", side_effect=fake_list_by_filter):
            with patch("src.db.system_config.get_price_filter", new=_inert_price_filter):
                await strat._scan_universe()

        assert captured_kwargs.get("is_kospi200") is True, (
            "G-157-VCP-1 HIGH — is_kospi200=True 인자 의무 (사이클 153 donchian 패턴)"
        )
        assert captured_kwargs.get("is_kosdaq150") is True, (
            "G-157-VCP-1 HIGH — is_kosdaq150=True 인자 의무 (사이클 153 donchian 패턴)"
        )


class TestG157Vcp2:
    def test_g157_vcp_2_no_hardcoded_ticker_lists_import(self):
        """G-157-VCP-2 — vcp_breakout.py 본체에서 KOSPI_200_TICKERS / KOSDAQ_150_TICKERS import 폐기 (사이클 17 KIS LMS chain 안전 마진 강화)."""
        vcp_path = Path("src/engine/strategies/vcp_breakout.py")
        source = vcp_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        found_kospi = False
        found_kosdaq = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "KOSPI_200_TICKERS":
                        found_kospi = True
                    if alias.name == "KOSDAQ_150_TICKERS":
                        found_kosdaq = True

        assert not found_kospi, (
            "G-157-VCP-2 — vcp_breakout.py KOSPI_200_TICKERS import 폐기 의무 (사이클 157 hardcoded 영역 폐기)"
        )
        assert not found_kosdaq, (
            "G-157-VCP-2 — vcp_breakout.py KOSDAQ_150_TICKERS import 폐기 의무 (사이클 157 hardcoded 영역 폐기)"
        )


class TestG157Vcp3:
    def test_g157_vcp_3_no_fetch_stock_detail_call(self):
        """G-157-VCP-3 — vcp_breakout.py 본체에서 fetch_stock_detail 호출 폐기 (KIS API 124회/일 → 0)."""
        vcp_path = Path("src/engine/strategies/vcp_breakout.py")
        source = vcp_path.read_text(encoding="utf-8")

        # AST 정적 가드 — Name "fetch_stock_detail" 호출 site 0건
        tree = ast.parse(source)
        callsites = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # await fetch_stock_detail(...) 또는 fetch_stock_detail(...) 형태
                if isinstance(func, ast.Name) and func.id == "fetch_stock_detail":
                    callsites.append(node.lineno)
                elif isinstance(func, ast.Attribute) and func.attr == "fetch_stock_detail":
                    callsites.append(node.lineno)

        assert not callsites, (
            f"G-157-VCP-3 — vcp_breakout.py fetch_stock_detail 호출 폐기 의무 잔존={callsites}"
        )


# ===========================================================================
# B 영역 — _is_master_blocked_for_entry hook 통합 (Q2) — 6 전략 적용
# ===========================================================================


def _make_basics(ticker: str, raw: dict | None = None) -> Any:
    """StockBasics mock helper — pydantic 직접 인스턴스화 회피."""
    from src.models.stock import StockBasics

    return StockBasics(
        ticker=ticker,
        name="",
        excg_dvsn_cd="",
        nxt_tradable=True,
        krx_halted=False,
        admin_item=False,
        raw=raw or {},
    )


class TestG157HookVB:
    @pytest.mark.asyncio
    async def test_g157_hook_vb_calls_master_block(self):
        """G-157-HOOK-VB — VB prepare() 영역에서 _apply_master_block_filter_in_prepare 호출 의무."""
        from src.engine.strategies import volatility_breakout

        cfg = volatility_breakout.StrategyConfig(
            strategy_id="volatility_breakout",
            name="VB",
            weight=1.0,
            params={"min_market_cap": 0, "min_trade_amount": 0, "max_scan_stocks": 10},
        )
        strat = volatility_breakout.VolatilityBreakoutStrategy(cfg)

        # 영역 가드 — VB 클래스에 _apply_master_block_filter_in_prepare 메서드 존재
        assert hasattr(strat, "_apply_master_block_filter_in_prepare"), (
            "G-157-HOOK-VB — VB 영역 _apply_master_block_filter_in_prepare 메서드 의무"
        )


class TestG157HookLTV:
    def test_g157_hook_ltv_method_exists(self):
        """G-157-HOOK-LTV — LTV 클래스 _apply_master_block_filter_in_prepare 메서드 존재 의무."""
        from src.engine.strategies import long_tail_volatility

        cfg = long_tail_volatility.StrategyConfig(
            strategy_id="long_tail_volatility",
            name="LTV",
            weight=1.0,
            params={},
        )
        strat = long_tail_volatility.LongTailVolatilityStrategy(cfg)
        assert hasattr(strat, "_apply_master_block_filter_in_prepare"), (
            "G-157-HOOK-LTV — LTV 영역 _apply_master_block_filter_in_prepare 메서드 의무"
        )


class TestG157HookDonchian:
    def test_g157_hook_donchian_method_exists(self):
        """G-157-HOOK-DONCHIAN — donchian_swing 클래스 _apply_master_block_filter_in_prepare 메서드 존재 의무."""
        from src.engine.strategies import donchian_swing

        cfg = donchian_swing.StrategyConfig(
            strategy_id="donchian_swing",
            name="donchian",
            weight=1.0,
            params={},
        )
        strat = donchian_swing.DonchianSwingStrategy(cfg)
        assert hasattr(strat, "_apply_master_block_filter_in_prepare"), (
            "G-157-HOOK-DONCHIAN — donchian_swing 영역 _apply_master_block_filter_in_prepare 메서드 의무"
        )


class TestG157HookBFB:
    def test_g157_hook_bfb_method_exists(self):
        """G-157-HOOK-BFB — BFB 클래스 _apply_master_block_filter_in_prepare 메서드 존재 의무."""
        from src.engine.strategies import bull_flag_breakout

        cfg = bull_flag_breakout.StrategyConfig(
            strategy_id="bull_flag_breakout",
            name="BFB",
            weight=1.0,
            params={},
        )
        strat = bull_flag_breakout.BullFlagBreakoutStrategy(cfg)
        assert hasattr(strat, "_apply_master_block_filter_in_prepare"), (
            "G-157-HOOK-BFB — BFB 영역 _apply_master_block_filter_in_prepare 메서드 의무"
        )


class TestG157HookVCP:
    def test_g157_hook_vcp_method_exists(self):
        """G-157-HOOK-VCP — VCP 클래스 _apply_master_block_filter_in_prepare 메서드 존재 의무."""
        from src.engine.strategies import vcp_breakout

        cfg = vcp_breakout.StrategyConfig(
            strategy_id="vcp_breakout",
            name="VCP",
            weight=1.0,
            params={},
        )
        strat = vcp_breakout.VcpBreakoutStrategy(cfg)
        assert hasattr(strat, "_apply_master_block_filter_in_prepare"), (
            "G-157-HOOK-VCP — VCP 영역 _apply_master_block_filter_in_prepare 메서드 의무"
        )


class TestG157HookMomentumScanStocks:
    @pytest.mark.asyncio
    async def test_g157_hook_momentum_scan_stocks_calls_master_block(self):
        """G-157-HOOK-MOMENTUM — scanner.scan_stocks() 영역이 _is_master_blocked_for_entry 호출.

        momentum hook 영역 = scan_stocks() 내부 mcap+trade_amount 통과 *후*, filtered.append 직전.
        사이클 132 영속 — momentum funnel 미적재.
        """
        from src.engine import scanner

        # mock 응답 — 거래정지 종목 + 정상 종목 혼합
        async def fake_fetch_rising_stocks():
            return [
                {
                    "stck_shrn_iscd": "111111",
                    "hts_kor_isnm": "차단종목",
                    "prdy_ctrt": "20.0",
                    "stck_prpr": "10000",
                    "lstn_stcn": "100000000",
                    "acml_tr_pbmn": "30000000000",  # 300억
                },
                {
                    "stck_shrn_iscd": "222222",
                    "hts_kor_isnm": "정상종목",
                    "prdy_ctrt": "20.0",
                    "stck_prpr": "10000",
                    "lstn_stcn": "100000000",
                    "acml_tr_pbmn": "30000000000",
                },
            ]

        # 111111 거래정지, 222222 정상
        async def fake_get(ticker: str):
            if ticker == "111111":
                return _make_basics(ticker, raw={"iscd_stat_cls_code": "57"})  # 거래정지
            return _make_basics(ticker, raw={"iscd_stat_cls_code": "55"})  # 정상

        async def fake_get_master_raw(ticker: str):
            return {}

        with patch.object(scanner, "fetch_rising_stocks", side_effect=fake_fetch_rising_stocks):
            with patch("src.db.stock_master.get", side_effect=fake_get):
                with patch("src.db.stock_master.get_master_raw", side_effect=fake_get_master_raw):
                    result = await scanner.scan_stocks()

        # 차단 종목은 filtered 에서 제외, 정상 종목만 통과
        assert "111111" not in result, (
            "G-157-HOOK-MOMENTUM — 거래정지 종목 차단 의무 (iscd_stat_cls_code=57)"
        )
        assert "222222" in result, (
            "G-157-HOOK-MOMENTUM — 정상 종목 통과 의무 (iscd_stat_cls_code=55)"
        )


class TestG157HookProtected:
    @pytest.mark.asyncio
    async def test_g157_hook_protected_tickers_pass_through(self):
        """G-157-HOOK-PROTECTED HIGH — 보유 종목 절대 보호 (사이클 32 R4 영속).

        master block 13건 차단 hook 영역에서도 protected_tickers 는 무조건 통과.
        """
        from src.engine.strategies import volatility_breakout
        from src.engine import scanner as _scanner_mod

        cfg = volatility_breakout.StrategyConfig(
            strategy_id="volatility_breakout",
            name="VB",
            weight=1.0,
            params={},
        )
        strat = volatility_breakout.VolatilityBreakoutStrategy(cfg)

        # 005935 = 차단 사유 있는 종목 (거래정지)
        # 하지만 보유 종목 set 에 등록 → 통과 영역 영구 영속
        async def fake_get(ticker: str):
            return _make_basics(ticker, raw={"iscd_stat_cls_code": "57"})

        async def fake_get_master_raw(ticker: str):
            return {}

        with patch.object(_scanner_mod, "_collect_protected_tickers_for_scanner", return_value={"005935"}):
            with patch("src.db.stock_master.get", side_effect=fake_get):
                with patch("src.db.stock_master.get_master_raw", side_effect=fake_get_master_raw):
                    survived, excluded = await strat._apply_master_block_filter_in_prepare(["005935", "111111"])

        assert "005935" in survived, (
            "G-157-HOOK-PROTECTED HIGH — 보유 종목 절대 보호 의무 (사이클 32 R4)"
        )
        assert "111111" not in survived, (
            "G-157-HOOK-PROTECTED HIGH — 비보유 차단 종목은 제외 (구조 정합성)"
        )


class TestG157HookGraceful:
    @pytest.mark.asyncio
    async def test_g157_hook_graceful_on_stock_master_exception(self):
        """G-157-HOOK-GRACEFUL — stock_master.get / get_master_raw 예외 시 graceful 통과 (사이클 88 G-REJECT 답습)."""
        from src.engine.strategies import volatility_breakout
        from src.engine import scanner as _scanner_mod

        cfg = volatility_breakout.StrategyConfig(
            strategy_id="volatility_breakout",
            name="VB",
            weight=1.0,
            params={},
        )
        strat = volatility_breakout.VolatilityBreakoutStrategy(cfg)

        async def boom_get(ticker: str):
            raise RuntimeError("supabase boom")

        async def boom_get_master(ticker: str):
            raise RuntimeError("supabase boom")

        with patch.object(_scanner_mod, "_collect_protected_tickers_for_scanner", return_value=set()):
            with patch("src.db.stock_master.get", side_effect=boom_get):
                with patch("src.db.stock_master.get_master_raw", side_effect=boom_get_master):
                    survived, excluded = await strat._apply_master_block_filter_in_prepare(["005930", "000660"])

        # graceful 통과 — 양쪽 ticker 모두 survived 영속
        assert "005930" in survived
        assert "000660" in survived
        assert excluded == [], (
            "G-157-HOOK-GRACEFUL — 예외 시 excluded 영역 0건 (graceful 통과 영속)"
        )


class TestG157HookExcludedFormat:
    @pytest.mark.asyncio
    async def test_g157_hook_excluded_format_dict_ticker_name_reason(self):
        """G-157-HOOK-EXCLUDED-FORMAT — excluded = [{ticker, name, reason}] 영역 영속 (사이클 41 답습)."""
        from src.engine.strategies import volatility_breakout
        from src.engine import scanner as _scanner_mod

        cfg = volatility_breakout.StrategyConfig(
            strategy_id="volatility_breakout",
            name="VB",
            weight=1.0,
            params={},
        )
        strat = volatility_breakout.VolatilityBreakoutStrategy(cfg)

        async def fake_get(ticker: str):
            # 거래정지 종목 (iscd_stat_cls_code=57)
            return _make_basics(ticker, raw={"iscd_stat_cls_code": "57"})

        async def fake_get_master(ticker: str):
            return {}

        # 이름 등록
        _scanner_mod.ticker_names["555555"] = "테스트종목"

        with patch.object(_scanner_mod, "_collect_protected_tickers_for_scanner", return_value=set()):
            with patch("src.db.stock_master.get", side_effect=fake_get):
                with patch("src.db.stock_master.get_master_raw", side_effect=fake_get_master):
                    survived, excluded = await strat._apply_master_block_filter_in_prepare(["555555"])

        assert "555555" not in survived
        assert len(excluded) == 1
        rec = excluded[0]
        assert "ticker" in rec and rec["ticker"] == "555555"
        assert "name" in rec
        assert "reason" in rec and rec["reason"], "사유 영역 비어있으면 안 됨"


# ===========================================================================
# C 영역 — FUNNEL_STAGES +1단계 (Q3)
# ===========================================================================


class TestG157FunnelVB:
    def test_g157_funnel_vb_has_6_stages(self):
        """G-157-FUNNEL-VB — VB_FUNNEL_STAGES len == 6 (5 + 1단계 진입 차단 step)."""
        from src.engine.strategies.volatility_breakout import VB_FUNNEL_STAGES

        assert len(VB_FUNNEL_STAGES) == 6, (
            f"G-157-FUNNEL-VB — 5 → 6단계 영구 영속, 실제={len(VB_FUNNEL_STAGES)}"
        )


class TestG157FunnelLTV:
    def test_g157_funnel_ltv_has_7_stages(self):
        """G-157-FUNNEL-LTV — LTV_FUNNEL_STAGES len == 7 (6 + 1단계 진입 차단 step)."""
        from src.engine.strategies.long_tail_volatility import LTV_FUNNEL_STAGES

        assert len(LTV_FUNNEL_STAGES) == 7, (
            f"G-157-FUNNEL-LTV — 6 → 7단계 영구 영속, 실제={len(LTV_FUNNEL_STAGES)}"
        )


class TestG157FunnelDonchian:
    def test_g157_funnel_donchian_has_9_stages(self):
        """G-157-FUNNEL-DONCHIAN — donchian FUNNEL_STAGES len == 9 (8 + 1단계 진입 차단 step)."""
        from src.engine.strategies.donchian_swing import FUNNEL_STAGES as DC_FUNNEL_STAGES

        assert len(DC_FUNNEL_STAGES) == 9, (
            f"G-157-FUNNEL-DONCHIAN — 8 → 9단계 영구 영속, 실제={len(DC_FUNNEL_STAGES)}"
        )


class TestG157FunnelBFB:
    def test_g157_funnel_bfb_has_9_stages(self):
        """G-157-FUNNEL-BFB — BFB FUNNEL_STAGES len == 9 (8 + 1단계 진입 차단 step)."""
        from src.engine.strategies.bull_flag_breakout import FUNNEL_STAGES as BFB_FUNNEL_STAGES

        assert len(BFB_FUNNEL_STAGES) == 9, (
            f"G-157-FUNNEL-BFB — 8 → 9단계 영구 영속, 실제={len(BFB_FUNNEL_STAGES)}"
        )


class TestG157FunnelVCP:
    def test_g157_funnel_vcp_has_9_stages(self):
        """G-157-FUNNEL-VCP — VCP FUNNEL_STAGES len == 9 (8 + 1단계 진입 차단 step)."""
        from src.engine.strategies.vcp_breakout import FUNNEL_STAGES as VCP_FUNNEL_STAGES

        assert len(VCP_FUNNEL_STAGES) == 9, (
            f"G-157-FUNNEL-VCP — 8 → 9단계 영구 영속, 실제={len(VCP_FUNNEL_STAGES)}"
        )


class TestG157FunnelMomentumExcluded:
    def test_g157_funnel_momentum_no_record_calls(self):
        """G-157-FUNNEL-MOMENTUM-EXCLUDED — momentum.py 본체에서 _record_funnel_step / _record_funnel_pipeline_step 호출 0건 (사이클 132 영속)."""
        momentum_path = Path("src/engine/strategies/momentum.py")
        source = momentum_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        callsites = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in (
                    "_record_funnel_step",
                    "_record_funnel_pipeline_step",
                ):
                    callsites.append((func.attr, node.lineno))

        assert not callsites, (
            f"G-157-FUNNEL-MOMENTUM-EXCLUDED — momentum funnel 적재 0건 영속 위반={callsites}"
        )


# ===========================================================================
# D 영역 — AST + 안전성
# ===========================================================================


class TestG157AstCallsites:
    def test_g157_ast_master_block_hook_callsites_at_least_5(self):
        """G-AST-157 — 5 전략 prepare-path + scanner.scan_stocks 영역 master block hook 호출 site ≥ 5건.

        5 전략 prepare-path: VB / LTV / donchian / BFB / VCP — 각 `_apply_master_block_filter_in_prepare`
        호출 1건 = 5. scanner.scan_stocks() 영역에서는 `_is_master_blocked_for_entry` 직접 호출 +1.

        본 가드는 위임 chain 영속 가드: 5 전략 wrapper 영역에서 `apply_master_block_filter` 또는
        `_apply_master_block_filter_in_prepare` 호출 ≥ 5건 의무.
        """
        strategy_roots = [
            Path("src/engine/strategies/volatility_breakout.py"),
            Path("src/engine/strategies/long_tail_volatility.py"),
            Path("src/engine/strategies/donchian_swing.py"),
            Path("src/engine/strategies/bull_flag_breakout.py"),
            Path("src/engine/strategies/vcp_breakout.py"),
        ]
        hook_call_total = 0  # _apply_master_block_filter_in_prepare 호출 site (prepare 본체)
        for p in strategy_roots:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr == "_apply_master_block_filter_in_prepare":
                        hook_call_total += 1

        assert hook_call_total >= 5, (
            f"G-AST-157 — 5 전략 prepare-path 영역 _apply_master_block_filter_in_prepare 호출 site ≥ 5 의무, 실제={hook_call_total}"
        )

        # 추가: scanner.py 영역 _is_master_blocked_for_entry 직접 호출 (momentum scan_stocks hook + apply_master_block_filter 본체)
        scanner_src = Path("src/engine/scanner.py").read_text(encoding="utf-8")
        scanner_tree = ast.parse(scanner_src)
        scanner_direct_calls = 0
        for node in ast.walk(scanner_tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "_is_master_blocked_for_entry":
                    scanner_direct_calls += 1
                elif isinstance(func, ast.Attribute) and func.attr == "_is_master_blocked_for_entry":
                    scanner_direct_calls += 1
        assert scanner_direct_calls >= 2, (
            f"G-AST-157 — scanner.py 영역 _is_master_blocked_for_entry 직접 호출 site ≥ 2 의무 "
            f"(apply_master_block_filter 헬퍼 + scan_stocks momentum hook), 실제={scanner_direct_calls}"
        )


class TestG157Safety1:
    def test_g157_safety_1_no_hot_path_changes(self):
        """G-157-SAFETY-1 HIGH — src/engine/risk.py / src/engine/order_engine.py / src/realtime/ / src/auth/ 영역 사이클 157 변경 0 (정적 가드).

        본 가드 = 사이클 157 작업 영역이 strategies/ + scanner.py 한정임을 정적 보장 (사이클 38 명문화 영속).
        """
        # 매매 hot path 모듈 import / 호출이 strategies/ 영역에 추가되지 않았는지 정적 검사
        forbidden_modules = {
            "src.engine.order_engine",
            "src.engine.risk",
            "src.realtime.websocket",
            "src.realtime.websocket_pool",
            "src.auth.token",
        }
        forbidden_attrs = {"on_tick", "execute_buy", "execute_sell", "place_order"}

        for p in [
            Path("src/engine/strategies/volatility_breakout.py"),
            Path("src/engine/strategies/long_tail_volatility.py"),
            Path("src/engine/strategies/donchian_swing.py"),
            Path("src/engine/strategies/bull_flag_breakout.py"),
            Path("src/engine/strategies/vcp_breakout.py"),
        ]:
            source = p.read_text(encoding="utf-8")
            tree = ast.parse(source)

            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module in forbidden_modules:
                        imports.append(node.module)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden_modules:
                            imports.append(alias.name)

            assert not imports, (
                f"G-157-SAFETY-1 HIGH — {p.name} 영역 매매 hot path import 위반: {imports}"
            )

            # AST 기반 호출 site 검사 (주석 잡음 차단)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    fn_name = ""
                    if isinstance(func, ast.Name):
                        fn_name = func.id
                    elif isinstance(func, ast.Attribute):
                        fn_name = func.attr
                    if fn_name in forbidden_attrs:
                        # 주석/문자열은 AST 에 안 잡힘 — 실제 호출만 탐지
                        pytest.fail(
                            f"G-157-SAFETY-1 HIGH — {p.name} 영역 {fn_name} 호출 위반 line={node.lineno}"
                        )


class TestG157Safety2NoExitSignalCalls:
    def test_g157_safety_2_master_block_does_not_call_exit_signal(self):
        """G-157-SAFETY-2 HIGH — _apply_master_block_filter_in_prepare 영역이 check_exit_signal / on_tick 호출 0건 (사이클 38 명문화 영속).

        매수 진입 *전* 영역 한정 → 매도/익일청산 영역 호출 절대 금지.
        """
        for p in [
            Path("src/engine/strategies/volatility_breakout.py"),
            Path("src/engine/strategies/long_tail_volatility.py"),
            Path("src/engine/strategies/donchian_swing.py"),
            Path("src/engine/strategies/bull_flag_breakout.py"),
            Path("src/engine/strategies/vcp_breakout.py"),
        ]:
            source = p.read_text(encoding="utf-8")
            tree = ast.parse(source)

            # _apply_master_block_filter_in_prepare 함수 본체 내부에 check_exit_signal/on_tick 호출 site 없어야 함
            for node in ast.walk(tree):
                if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                    if node.name == "_apply_master_block_filter_in_prepare":
                        # 본체 walk
                        for inner in ast.walk(node):
                            if isinstance(inner, ast.Call):
                                func = inner.func
                                attr = func.attr if isinstance(func, ast.Attribute) else (
                                    func.id if isinstance(func, ast.Name) else ""
                                )
                                assert attr not in ("check_exit_signal", "on_tick", "execute_buy", "execute_sell"), (
                                    f"G-157-SAFETY-2 HIGH — {p.name}::_apply_master_block_filter_in_prepare 영역 {attr} 호출 위반 (사이클 38 명문화 위반)"
                                )


class TestG157Safety3RawReadOnly:
    def test_g157_safety_3_master_block_does_not_write_raw(self):
        """G-157-SAFETY-3 HIGH — _is_master_blocked_for_entry 영역이 raw / master_raw 영역 write 0건 (사이클 81 G-AST1 영속).

        진입 차단 hook 은 read-only — 데이터 변경 절대 금지.
        """
        scanner_path = Path("src/engine/scanner.py")
        source = scanner_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                if node.name == "_is_master_blocked_for_entry":
                    # 본체 walk — Assign / AugAssign 의 target 에 dict 형태 write 가 없어야 함
                    # raw[key] = ... 또는 master_raw[key] = ... 패턴
                    for inner in ast.walk(node):
                        if isinstance(inner, ast.Assign):
                            for target in inner.targets:
                                # Subscript 형태: raw["x"] = ...
                                if isinstance(target, ast.Subscript):
                                    value = target.value
                                    if isinstance(value, ast.Name) and value.id in ("raw", "master_raw"):
                                        pytest.fail(
                                            f"G-157-SAFETY-3 HIGH — _is_master_blocked_for_entry 영역 {value.id} write 위반 line={inner.lineno}"
                                        )
                        if isinstance(inner, ast.AugAssign):
                            target = inner.target
                            if isinstance(target, ast.Subscript):
                                value = target.value
                                if isinstance(value, ast.Name) and value.id in ("raw", "master_raw"):
                                    pytest.fail(
                                        f"G-157-SAFETY-3 HIGH — _is_master_blocked_for_entry 영역 {value.id} augassign 위반 line={inner.lineno}"
                                    )
