"""사이클 153 — donchian_swing _scan_universe 영역 KOSPI200/KOSDAQ150 호출 정합 회귀 가드.

G-153-DONCHIAN 3 케이스 (HIGH 1) + G-153-SAFETY 일부.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# G-153-DONCHIAN-1 (HIGH) — _scan_universe → list_by_filter 호출 정합
# ---------------------------------------------------------------------------


class TestG153Donchian1:
    @pytest.mark.asyncio
    async def test_donchian_1_scan_universe_passes_index_flags(self):
        """G-153-DONCHIAN-1 HIGH — _scan_universe 영역 list_by_filter 호출 시 is_kospi200=True + is_kosdaq150=True 인자 전달 의무."""
        from src.engine.strategies import donchian_swing

        cfg = donchian_swing.StrategyConfig(
            strategy_id="donchian_swing",
            name="도치안 스윙",
            weight=1.0,
            params={
                "min_market_cap": 50_000_000_000,
                "min_trade_amount": 1_000_000_000,
                "max_scan_stocks": 200,
            },
        )
        strat = donchian_swing.DonchianSwingStrategy(cfg)

        captured_kwargs: dict = {}

        async def fake_list_by_filter(**kwargs):
            captured_kwargs.update(kwargs)
            # 사이클 170 카드 A — donchian 이 return_stage_counts=True 전달 → tuple 반환
            if kwargs.get("return_stage_counts"):
                return [], {"union_tickers": [], "mcap_tickers": [], "trade_tickers": []}
            return []

        with patch("src.db.stock_master.list_by_filter", side_effect=fake_list_by_filter):
            await strat._scan_universe()

        assert captured_kwargs.get("is_kospi200") is True, (
            "G-153-DONCHIAN-1 HIGH — _scan_universe 영역 is_kospi200=True 인자 영구 영속 의무"
        )
        assert captured_kwargs.get("is_kosdaq150") is True, (
            "G-153-DONCHIAN-1 HIGH — _scan_universe 영역 is_kosdaq150=True 인자 영구 영속 의무"
        )


# ---------------------------------------------------------------------------
# G-153-DONCHIAN-2 — FUNNEL_STAGES[0] step_name 변경 0
# ---------------------------------------------------------------------------


class TestG153Donchian2:
    def test_donchian_2_funnel_stage_0_step_name_unchanged(self):
        """G-153-DONCHIAN-2 — FUNNEL_STAGES[0] step_name = "코스피200+코스닥150 합집합" 영구 영속 (사용자 결정 영역 D)."""
        from src.engine.strategies import donchian_swing

        stage0 = donchian_swing.FUNNEL_STAGES[0]
        assert stage0.step_no == 1, "FUNNEL_STAGES[0] step_no = 1 영구 영속"
        assert "코스피200" in stage0.step_name, (
            "G-153-DONCHIAN-2 — step_name 영역 '코스피200' 영구 영속 의무"
        )
        assert "코스닥150" in stage0.step_name, (
            "G-153-DONCHIAN-2 — step_name 영역 '코스닥150' 영구 영속 의무"
        )
        assert "합집합" in stage0.step_name


# ---------------------------------------------------------------------------
# G-153-DONCHIAN-3 — step_no=1 survived 정합 (사용자 보고 결함 영역 시정 확인)
# ---------------------------------------------------------------------------


class TestG153Donchian3:
    @pytest.mark.asyncio
    async def test_donchian_3_survived_with_index_flags(self):
        """G-153-DONCHIAN-3 — KOSPI200/KOSDAQ150 필터 통과 종목만 survived 영역 영구 영속."""
        from src.engine.strategies import donchian_swing

        cfg = donchian_swing.StrategyConfig(
            strategy_id="donchian_swing",
            name="도치안 스윙",
            weight=1.0,
            params={
                "min_market_cap": 0,
                "min_trade_amount": 0,
                "max_scan_stocks": 200,
            },
        )
        strat = donchian_swing.DonchianSwingStrategy(cfg)

        # 사용자 보고 영역 시정 확인 = KOSPI200 + KOSDAQ150 후보가 1 → ~350 영역 영구 영속
        fake_rows = [
            {"ticker": "005930", "name": "삼성전자", "raw": {}, "is_kospi200": True, "is_kosdaq150": False},
            {"ticker": "000660", "name": "SK하이닉스", "raw": {}, "is_kospi200": True, "is_kosdaq150": False},
            {"ticker": "247540", "name": "에코프로비엠", "raw": {}, "is_kospi200": False, "is_kosdaq150": True},
        ]

        async def fake_list_by_filter(**kwargs):
            # is_kospi200=True OR is_kosdaq150=True 영역 필터 통과 = 3 종목
            # 사이클 170 카드 A — donchian 이 return_stage_counts=True 전달 → tuple 반환
            if kwargs.get("return_stage_counts"):
                tks = [r["ticker"] for r in fake_rows]
                return fake_rows, {
                    "union_tickers": tks,
                    "mcap_tickers": tks,
                    "trade_tickers": tks,
                }
            return fake_rows

        with patch("src.db.stock_master.list_by_filter", side_effect=fake_list_by_filter):
            result = await strat._scan_universe()

        # 사용자 보고 영역 = survived=5 (사이클 121 결함) → 사이클 153 시정 후 ≥3 영구 영속
        assert len(result) >= 3, (
            "G-153-DONCHIAN-3 — 사용자 보고 결함 시정 (KOSPI200 + KOSDAQ150 필터 통과 종목 영구 영속)"
        )


# ---------------------------------------------------------------------------
# G-153-SAFETY-1 (HIGH) — risk.on_tick / order_engine / realtime / auth import 0건
# ---------------------------------------------------------------------------


class TestG153Safety1:
    def test_safety_1_no_hot_path_imports(self):
        """G-153-SAFETY-1 HIGH — donchian_swing.py 영역 매매 hot path 변경 0 (AST 정적 가드)."""
        donchian_path = Path("src/engine/strategies/donchian_swing.py")
        source = donchian_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        forbidden_modules = {
            "src.engine.order_engine",
            "src.engine.risk",
            "src.realtime.websocket",
            "src.realtime.websocket_pool",
            "src.auth.token",
        }
        forbidden_attrs = {"on_tick", "execute_buy", "execute_sell", "place_order"}

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module in forbidden_modules:
                    imports.append(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_modules:
                        imports.append(alias.name)

        assert not imports, (
            f"G-153-SAFETY-1 HIGH — 매매 hot path 모듈 import 영구 영속 0건 위반: {imports}"
        )

        # 함수명 0건 검증
        for fn_name in forbidden_attrs:
            assert re.search(rf"\b{fn_name}\s*\(", source) is None, (
                f"G-153-SAFETY-1 HIGH — 함수 {fn_name} 호출 영구 영속 0건 위반"
            )


# ---------------------------------------------------------------------------
# G-153-SAFETY-3 — vcp_breakout L726/L732 영역 영향 0 (hardcoded list 변경 0)
# ---------------------------------------------------------------------------


class TestG153Safety3:
    @pytest.mark.xfail(
        strict=False,
        reason=(
            "사이클 157 (2026-06-17) 의미 전환 영구 영속 — VCP hardcoded list 영역 폐기 영역 "
            "영구 영속 시정 (사이클 66 K-2 패턴 답습). vcp_breakout._scan_universe 영역이 "
            "stock_master.list_by_filter(is_kospi200=True, is_kosdaq150=True) 영역으로 전환 영구 영속. "
            "사이클 153 G-153-SAFETY-3 시점 = hardcoded 영역 영구 영속 가드 의도 보존."
        ),
    )
    def test_safety_3_vcp_breakout_unchanged(self):
        """G-153-SAFETY-3 — vcp_breakout.py 영역 KOSPI_200_TICKERS + KOSDAQ_150_TICKERS 합집합 영역 변경 0.

        사이클 157 — VCP hardcoded 영역 폐기 영구 영속 시정 → xfail 영속 전환 (사이클 66 K-2 패턴).
        """
        vcp_path = Path("src/engine/strategies/vcp_breakout.py")
        source = vcp_path.read_text(encoding="utf-8")

        # 사이클 153 범위 외 — vcp_breakout 영역 hardcoded list 영역 영구 영속
        assert "KOSPI_200_TICKERS" in source, (
            "G-153-SAFETY-3 — vcp_breakout 영역 KOSPI_200_TICKERS 영구 영속 (사이클 153 변경 0)"
        )
        assert "KOSDAQ_150_TICKERS" in source, (
            "G-153-SAFETY-3 — vcp_breakout 영역 KOSDAQ_150_TICKERS 영구 영속 (사이클 153 변경 0)"
        )
