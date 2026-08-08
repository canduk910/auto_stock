"""VCP·BFB 확대 유니버스 (2026-08-08) 회귀 가드.

사용자 지시 = "VCP·BFB 도 kojiro 처럼 전체 상장 중 일부필터(kojiro 동일) 적용한 확대 유니버스".
kojiro 필터 = 전체 상장(지수 무제약) ∩ 시총≥500억 ∩ 거래대금≥10억.

결정 (사용자 + 도메인 자문 `_workspace/domain_consult/cycle_vcp_bfb_universe_expansion.md`):
- VCP = 지수 제거 + 시총 100억(사용자 결정 — kojiro 500억보다 낮게, 소형주 포함) + 거래대금 0→10억 신설.
- BFB = B2 (거래대금 15억) — 이미 지수 무제약. 시총 100억(사용자 결정) + 거래대금 20억→15억 (장중 돌파
  추격이라 kojiro 10억은 슬리피지 위험, 완만한 15억 하향). max_scan 100→4000.

핵심 사실:
- 구독 부하는 유니버스가 아니라 셋업 통과 후보(get_scanned_tickers)에 비례.
- 일봉 데이터는 이미 존재 (daily-load = 지수∪500억/10억 = 확대 상위집합, 비지수 자격
  641종목 중 95.8% ≥100일 적재 실측) → scanner 무변경.
- 진입 임계(추세필터/pullback/폴/플래그)는 전략 정체성 상수 = 이번엔 불변.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _lbf_capture():
    """list_by_filter 호출 kwargs 캡처 + return_stage_counts 튜플 반환 mock."""
    captured: dict = {}

    async def fake(**kwargs):
        captured.update(kwargs)
        if kwargs.get("return_stage_counts"):
            return [], {"union_tickers": [], "mcap_tickers": [], "trade_tickers": []}
        return []

    return captured, fake


async def _inert_price_filter():
    """PriceFilter 비활성 instance — _apply_price_filter_in_prepare 통과 (test_cycle157 답습)."""
    from src.db.system_config import PriceFilter

    return PriceFilter(min_price=0, max_price=0)


# ---------------------------------------------------------------------------
# VCP — 지수 제거 + 시총 100억(사용자 결정) + 거래대금 10억
# ---------------------------------------------------------------------------

class TestVcpUniverseExpansion:
    def test_vcp_default_params_expanded(self):
        """VCP DEFAULT_PARAMS = 시총 100억 + 거래대금 10억 + max_scan 4000 (사용자 결정)."""
        from src.engine.strategies import vcp_breakout

        p = vcp_breakout.VcpBreakoutStrategy.DEFAULT_PARAMS
        assert p["min_market_cap"] == 10_000_000_000, "시총 100억 (사용자 결정 — kojiro 500억보다 낮게, 소형주 포함)"
        assert p["min_trade_amount"] == 1_000_000_000, "거래대금 10억 (0 하드코딩→신설)"
        assert p["max_scan_stocks"] == 4000, "max_scan 4000 (200→확대, 전체 filtered 커버)"

    def test_vcp_scan_universe_removes_index_filter(self):
        """VCP _scan_universe → list_by_filter(is_kospi200=None, is_kosdaq150=None) — 지수 제거."""
        from src.engine.strategies import vcp_breakout

        cfg = vcp_breakout.StrategyConfig(
            strategy_id="vcp_breakout", name="VCP", weight=1.0, params={}
        )
        strat = vcp_breakout.VcpBreakoutStrategy(cfg)
        captured, fake = _lbf_capture()

        with patch("src.db.stock_master.list_by_filter", side_effect=fake), \
             patch("src.db.system_config.get_price_filter", new=_inert_price_filter):
            asyncio.run(strat._scan_universe())

        assert captured.get("is_kospi200") is None, "지수 제약 제거 (전체 상장)"
        assert captured.get("is_kosdaq150") is None, "지수 제약 제거 (전체 상장)"

    def test_vcp_scan_universe_passes_trade_amount_and_mcap(self):
        """VCP _scan_universe → 시총 100억 + 거래대금 10억 필터 실전달 (하드코딩 0 폐기)."""
        from src.engine.strategies import vcp_breakout

        cfg = vcp_breakout.StrategyConfig(
            strategy_id="vcp_breakout", name="VCP", weight=1.0, params={}
        )
        strat = vcp_breakout.VcpBreakoutStrategy(cfg)
        captured, fake = _lbf_capture()

        with patch("src.db.stock_master.list_by_filter", side_effect=fake), \
             patch("src.db.system_config.get_price_filter", new=_inert_price_filter):
            asyncio.run(strat._scan_universe())

        assert captured.get("min_market_cap") == 10_000_000_000
        assert captured.get("min_trade_amount") == 1_000_000_000, (
            "거래대금 10억 필터 실전달 — 이전 하드코딩 min_trade_amount=0 폐기"
        )
        assert captured.get("return_stage_counts") is True

    def test_vcp_funnel_stage_labels_expanded(self):
        """VCP FUNNEL_STAGES[0]/[1] step_name = 확대 유니버스 정합."""
        from src.engine.strategies import vcp_breakout

        assert vcp_breakout.FUNNEL_STAGES[0].step_name == "전체 상장 유니버스 (시총/거래대금 컷 전)"
        assert vcp_breakout.FUNNEL_STAGES[1].step_name == "시총·거래대금 컷 통과"


# ---------------------------------------------------------------------------
# BFB — 시총 100억 + 거래대금 15억(B2) + max_scan 4000
# ---------------------------------------------------------------------------

class TestBfbUniverseExpansion:
    def test_bfb_default_params_expanded(self):
        """BFB DEFAULT_PARAMS = 시총 100억 + 거래대금 15억(B2) + max_scan 4000 (사용자 결정)."""
        from src.engine.strategies import bull_flag_breakout

        p = bull_flag_breakout.BullFlagBreakoutStrategy.DEFAULT_PARAMS
        assert p["min_market_cap"] == 10_000_000_000, "시총 100억 (사용자 결정 — 소형주 포함)"
        assert p["min_trade_amount"] == 1_500_000_000, "거래대금 15억 (20억→15억, 도메인 B2)"
        assert p["max_scan_stocks"] == 4000, "max_scan 4000 (100→확대, refreshed_at 임의절단 소멸)"

    def test_bfb_scan_universe_return_stage_counts_and_trade(self):
        """BFB _scan_universe → return_stage_counts=True + 거래대금 15억 전달 (VCP/kojiro 정합)."""
        from src.engine.strategies import bull_flag_breakout

        cfg = bull_flag_breakout.StrategyConfig(
            strategy_id="bull_flag_breakout", name="BFB", weight=1.0, params={}
        )
        strat = bull_flag_breakout.BullFlagBreakoutStrategy(cfg)
        captured, fake = _lbf_capture()

        with patch("src.db.stock_master.list_by_filter", side_effect=fake), \
             patch("src.db.system_config.get_price_filter", new=_inert_price_filter):
            asyncio.run(strat._scan_universe())

        assert captured.get("return_stage_counts") is True, "합집합 노출 배선 (VCP/kojiro 정합)"
        assert captured.get("min_trade_amount") == 1_500_000_000, "거래대금 15억 (B2)"
        assert captured.get("min_market_cap") == 10_000_000_000

    def test_bfb_empty_scan_stats_has_universe_union(self):
        """BFB _empty_scan_stats 에 universe_union 키 신규 (VCP 정합)."""
        from src.engine.strategies import bull_flag_breakout

        stats = bull_flag_breakout._empty_scan_stats()
        assert "universe_union" in stats, "확대 — 합집합 카운트 키 (시총·거래대금 컷 전 원천)"

    def test_bfb_scan_universe_sets_universe_union(self):
        """BFB _scan_universe 후 _scan_stats['universe_union'] 이 stage union 으로 설정된다."""
        from src.engine.strategies import bull_flag_breakout

        cfg = bull_flag_breakout.StrategyConfig(
            strategy_id="bull_flag_breakout", name="BFB", weight=1.0, params={}
        )
        strat = bull_flag_breakout.BullFlagBreakoutStrategy(cfg)

        rows = [
            {"ticker": "005930", "name": "삼성전자", "raw": {}},
            {"ticker": "000660", "name": "SK하이닉스", "raw": {}},
        ]
        union = ["005930", "000660", "035720"]  # 컷 전 원천이 더 많음
        stage = {"union_tickers": union, "mcap_tickers": [r["ticker"] for r in rows], "trade_tickers": [r["ticker"] for r in rows]}

        async def fake(**kwargs):
            return rows, stage

        with patch("src.db.stock_master.list_by_filter", side_effect=fake), \
             patch("src.db.system_config.get_price_filter", new=_inert_price_filter):
            asyncio.run(strat._scan_universe())

        assert strat._scan_stats["universe_union"] == 3, "합집합(컷 전) = 3"
        assert strat._scan_stats["universe_candidates"] == 2, "컷 통과 후보 = 2"


# ---------------------------------------------------------------------------
# 정합성 — VCP/BFB/kojiro 3전략 동일 확대 유니버스 소스
# ---------------------------------------------------------------------------

class TestExpansionParity:
    def test_vcp_bfb_funnel_step0_uses_union_not_filtered(self):
        """F-A 시정 — VCP/BFB prepare step0/step1 이 union/trade_tickers 사용 (컷 후 tickers 아님).

        확대 후 step0 라벨이 "컷 전 전체상장"인데 survived=tickers(컷 후)면 카운트 collapse
        → 라벨과 모순. kojiro 패턴(union_tickers/trade_tickers)으로 배선 (적대적 검증 F-A).
        """
        import inspect
        from src.engine.strategies import vcp_breakout, bull_flag_breakout

        for mod in (vcp_breakout, bull_flag_breakout):
            src = inspect.getsource(mod)
            assert 'stage_counts.get("union_tickers"' in src, (
                f"{mod.__name__} prepare 가 step0 에 union_tickers 를 써야 한다 (컷 전 원천)"
            )
            assert 'stage_counts.get("trade_tickers"' in src, (
                f"{mod.__name__} prepare 가 step1 에 trade_tickers 를 써야 한다 (시총·거래대금 컷 통과)"
            )
            # _scan_universe 가 stage 를 인스턴스에 보관 (prepare 가 읽음)
            assert "self._scan_stage_counts = stage" in src, (
                f"{mod.__name__} _scan_universe 가 stage 를 보관해야 한다"
            )

    def test_three_strategies_share_expanded_universe_source(self):
        """VCP·BFB·kojiro 모두 지수 무제약 + 시총·거래대금 필터 (동일 확대 유니버스 계열)."""
        from src.engine.strategies import vcp_breakout, bull_flag_breakout, kojiro

        vcp_p = vcp_breakout.VcpBreakoutStrategy.DEFAULT_PARAMS
        bfb_p = bull_flag_breakout.BullFlagBreakoutStrategy.DEFAULT_PARAMS
        koj_p = kojiro.KojiroStrategy.DEFAULT_PARAMS

        # 시총 하한 = VCP/BFB 100억 (사용자 결정 — kojiro 500억보다 낮게, 소형주 포함).
        assert vcp_p["min_market_cap"] == bfb_p["min_market_cap"] == 10_000_000_000
        assert koj_p["min_market_cap"] == 50_000_000_000  # kojiro 는 500억 유지 (확대 대상 아님)
        # 거래대금 = VCP kojiro 완전 동일(10억) / BFB 차등(15억, 추격도 BFB>kojiro 반영)
        assert vcp_p["min_trade_amount"] == koj_p["min_trade_amount"] == 1_000_000_000
        assert bfb_p["min_trade_amount"] >= koj_p["min_trade_amount"], (
            "BFB 거래대금 하한 ≥ kojiro (장중 돌파 추격 슬리피지 방어, 도메인 권고)"
        )
