"""사이클 G Part B — VB RS/RSI 관찰-배제0 배선 회귀 가드 (Red).

명세: `_workspace/red/_behaviors_cycleG_vb_rr_20260802.md` Part B (G-B3~B6).
계획: `~/.claude/plans/luminous-drifting-widget.md` Part B.

사이클 C3 quant 훅(`_apply_quant_filter_in_prepare`)과 **동일한 관찰-배제0 패턴**으로
RS·RSI 스코어를 prepare 단계에서 계산·기록만(배제 0). 2주 관찰로 증거 축적 후
유의성 게이트 → 별도 사이클에서 실배제.

Red 가드 매트릭스:
- G-B3 (파라미터): DEFAULT_PARAMS `rs_filter_enabled=False`/`rsi_filter_enabled=False` +
  `rsi_extreme_max=85` (RSI 는 극단>85 관찰 — 단순>70 컷 금지). PARAM_RANGES 미편입(AST).
- G-B4 (관찰 훅): `_apply_rs_rsi_observe_in_prepare(tickers)` 신규 — prepare 말미 호출.
  일봉(get_recent_daily) + 지수(069500)로 rsi/rs 계산 → funnel step(8/9) 스코어 기록.
- G-B5 (배제 0, HIGH): 입력 tickers == 출력 (관찰만). enabled 무관 배제 0.
  보유 protected 스킵(사이클 32 R4) + 일봉 결측/예외 fail-open(사이클 88 G-REJECT).
- G-B6 (지수 일봉): KODEX200 069500 조회. 미수신 graceful (RS None, 배제 0).
- FUNNEL: VB_FUNNEL_STAGES 7→9 확장 (step 8 RS 관찰 / step 9 RSI 관찰).
- SAFETY (AST): 훅 영역 check_exit_signal 호출 0 + risk/order import 0. check_buy/exit diff 0.

매매 안전성: prepare = 매수 진입 전 (사이클 38). 배제 0 (사이클 C3/38).
freeze_time 미사용 — get_recent_daily mock (사이클 187 hang 교훈).
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[4]
_VB_SRC = _REPO_ROOT / "src" / "engine" / "strategies" / "volatility_breakout.py"
_RECO_SRC = _REPO_ROOT / "src" / "engine" / "recommendation_engine.py"

_INDEX_TICKER = "069500"  # KODEX200 (RS 벤치마크)


def _make_strategy(**param_overrides):
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    params = {
        "min_market_cap": 100_000_000_000,
        "min_trade_amount": 20_000_000_000,
        "max_scan_stocks": 100,
    }
    params.update(param_overrides)
    config = StrategyConfig(
        strategy_id="volatility_breakout",
        name="변동성돌파",
        params=params,
    )
    return VolatilityBreakoutStrategy(config)


def _daily(ticker: str, n: int = 30, start: float = 100.0, step: float = 1.0) -> list[dict]:
    """get_recent_daily 반환 (bas_dd DESC — 최신 먼저). close_price 필드 사용."""
    rows = []
    for i in range(n):
        # i=0 이 최신 → close 가장 큼 (상승 추세). DESC 정렬 모사.
        close = start + step * (n - 1 - i)
        rows.append({
            "ticker": ticker,
            "bas_dd": f"202406{(n - i):02d}"[:8],
            "open_price": close,
            "high_price": close,
            "low_price": close,
            "close_price": close,
            "volume": 1_000_000,
            "trade_value": 100_000_000,
            "change_rate": 1.0,
            "raw": {},
        })
    return rows


def _daily_side_effect(daily_map: dict[str, list[dict]], default_n: int = 30):
    """ticker → 일봉 매핑 side_effect. 미지정 ticker 는 기본 상승 일봉."""
    async def _inner(ticker, *args, **kwargs):
        if ticker in daily_map:
            return daily_map[ticker]
        return _daily(ticker, n=default_n)
    return _inner


def _method_source(name: str) -> str:
    src = _VB_SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    return ""


def _get_hook(strategy):
    hook = getattr(strategy, "_apply_rs_rsi_observe_in_prepare", None)
    assert hook is not None, (
        "VolatilityBreakoutStrategy._apply_rs_rsi_observe_in_prepare 미구현 — Part B G-B4 산출물."
    )
    return hook


# ---------------------------------------------------------------------------
# G-B3 — 파라미터 (DEFAULT_PARAMS + PARAM_RANGES 미편입)
# ---------------------------------------------------------------------------
class TestRsRsiParams:
    def test_default_params_rs_rsi_keys(self):
        from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

        dp = VolatilityBreakoutStrategy.DEFAULT_PARAMS
        assert dp.get("rs_filter_enabled") is False, (
            f"rs_filter_enabled != False (관찰 기본 OFF): {dp.get('rs_filter_enabled')}"
        )
        assert dp.get("rsi_filter_enabled") is False, (
            f"rsi_filter_enabled != False (관찰 기본 OFF): {dp.get('rsi_filter_enabled')}"
        )
        assert dp.get("rsi_extreme_max") == 85, (
            f"rsi_extreme_max != 85 (극단 관찰 임계 — 단순 >70 컷 금지): "
            f"{dp.get('rsi_extreme_max')}"
        )

    def test_params_not_in_param_ranges(self):
        reco_src = _RECO_SRC.read_text(encoding="utf-8")
        for token in ("rs_filter_enabled", "rsi_filter_enabled", "rsi_extreme_max"):
            assert token not in reco_src, (
                f"recommendation_engine.py 에 '{token}' 등장 — "
                "PARAM_RANGES AI 자동튜닝 편입 금지 위반 (관찰 전용, 진입 정체성)."
            )


# ---------------------------------------------------------------------------
# G-B5 — 배제 0 (HIGH): 입력 == 출력 (관찰만)
# ---------------------------------------------------------------------------
class TestObserveNoExclusion:
    @pytest.mark.asyncio
    async def test_observe_passes_all(self):
        strategy = _make_strategy(rs_filter_enabled=False, rsi_filter_enabled=False)
        hook = _get_hook(strategy)
        tickers = ["005930", "000660", "035720"]

        with patch("src.db.stock_master_daily.get_recent_daily",
                   new=AsyncMock(side_effect=_daily_side_effect({}))), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()):
            result = await hook(tickers)

        assert set(result) == set(tickers), (
            f"관찰 모드인데 배제 발생 — 입력 {tickers} != 출력 {result}. 배제 0 위반 (G-B5)."
        )
        assert len(result) == len(tickers)

    @pytest.mark.asyncio
    async def test_no_exclusion_even_when_enabled(self):
        """enabled=True 여도 Phase 1 은 실배제 미구현 → 배제 0 (관찰만)."""
        strategy = _make_strategy(rs_filter_enabled=True, rsi_filter_enabled=True)
        hook = _get_hook(strategy)
        tickers = ["005930", "000660"]

        with patch("src.db.stock_master_daily.get_recent_daily",
                   new=AsyncMock(side_effect=_daily_side_effect({}))), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()):
            result = await hook(tickers)

        assert set(result) == set(tickers), (
            "enabled=True 인데 배제 발생 — Phase 1 은 관찰만(실배제 별도 사이클), 배제 0 위반."
        )


# ---------------------------------------------------------------------------
# G-B5 — protected 스킵 + fail-open
# ---------------------------------------------------------------------------
class TestProtectedAndFailOpen:
    @pytest.mark.asyncio
    async def test_held_ticker_passes(self):
        """보유 종목 절대 보호 (사이클 32 R4) — 관찰 대상에서 스킵하되 출력 보존."""
        strategy = _make_strategy(rs_filter_enabled=False)
        hook = _get_hook(strategy)

        with patch("src.db.stock_master_daily.get_recent_daily",
                   new=AsyncMock(side_effect=_daily_side_effect({}))), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value={"005930"}):
            result = await hook(["005930", "000660"])

        assert set(result) == {"005930", "000660"}, (
            "보유 종목 protected 인데 출력에서 누락 — 배제 0 위반 (G-B5)."
        )

    @pytest.mark.asyncio
    async def test_missing_daily_fail_open(self):
        """종목 일봉 결측([]) → RS/RSI None → fail-open 통과."""
        strategy = _make_strategy(rs_filter_enabled=False)
        hook = _get_hook(strategy)

        daily_map = {"005930": [], "000660": []}  # 종목 일봉 결측
        with patch("src.db.stock_master_daily.get_recent_daily",
                   new=AsyncMock(side_effect=_daily_side_effect(daily_map))), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()):
            result = await hook(["005930", "000660"])

        assert set(result) == {"005930", "000660"}, (
            "일봉 결측인데 배제 발생 — fail-open 통과 위반 (사이클 88 G-REJECT)."
        )

    @pytest.mark.asyncio
    async def test_exception_fail_open(self):
        """get_recent_daily 예외 graceful → 입력 보존."""
        strategy = _make_strategy(rs_filter_enabled=False)
        hook = _get_hook(strategy)

        with patch("src.db.stock_master_daily.get_recent_daily",
                   new=AsyncMock(side_effect=RuntimeError("DB down"))), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()):
            result = await hook(["005930", "000660"])

        assert set(result) == {"005930", "000660"}, (
            "get_recent_daily 예외인데 배제 발생 — graceful 통과 위반 (사이클 88)."
        )


# ---------------------------------------------------------------------------
# G-B6 — 지수 일봉 (KODEX200 069500) 조회 + 미수신 graceful
# ---------------------------------------------------------------------------
class TestIndexBenchmark:
    @pytest.mark.asyncio
    async def test_index_daily_queried(self):
        """RS 벤치마크 = KODEX200 069500 일봉 조회."""
        strategy = _make_strategy(rs_filter_enabled=False)
        hook = _get_hook(strategy)

        gr_mock = AsyncMock(side_effect=_daily_side_effect({}))
        with patch("src.db.stock_master_daily.get_recent_daily", new=gr_mock), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()):
            await hook(["005930"])

        queried = [c.args[0] for c in gr_mock.call_args_list if c.args]
        assert _INDEX_TICKER in queried, (
            f"KODEX200 {_INDEX_TICKER} 지수 일봉 미조회 — RS 벤치마크 부재 (G-B6). "
            f"조회 목록: {queried}"
        )

    @pytest.mark.asyncio
    async def test_index_missing_graceful(self):
        """지수 일봉 미수신([]) → RS None, 관찰 skip, 배제 0."""
        strategy = _make_strategy(rs_filter_enabled=False)
        hook = _get_hook(strategy)

        daily_map = {_INDEX_TICKER: []}  # 지수 일봉 미수신
        with patch("src.db.stock_master_daily.get_recent_daily",
                   new=AsyncMock(side_effect=_daily_side_effect(daily_map))), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()):
            result = await hook(["005930", "000660"])

        assert set(result) == {"005930", "000660"}, (
            "지수 일봉 미수신인데 배제 발생 — graceful RS None + 배제 0 위반 (G-B6)."
        )


# ---------------------------------------------------------------------------
# G-B4 — funnel step (8/9) 스코어 기록
# ---------------------------------------------------------------------------
class TestFunnelRecorded:
    @pytest.mark.asyncio
    async def test_funnel_steps_recorded(self):
        strategy = _make_strategy(rs_filter_enabled=False)
        hook = _get_hook(strategy)

        rec_mock = MagicMock()
        with patch("src.db.stock_master_daily.get_recent_daily",
                   new=AsyncMock(side_effect=_daily_side_effect({}))), \
             patch("src.engine.scanner._collect_protected_tickers_for_scanner",
                   return_value=set()), \
             patch.object(strategy, "_record_funnel_pipeline_step", rec_mock):
            await hook(["005930"])

        assert rec_mock.call_count >= 1, (
            "_apply_rs_rsi_observe_in_prepare 가 funnel step(RS/RSI 관찰) 미기록 (G-B4)."
        )


class TestFunnelStagesExtended:
    def test_funnel_stages_has_9_steps(self):
        from src.engine.strategies.volatility_breakout import VB_FUNNEL_STAGES

        assert len(VB_FUNNEL_STAGES) == 9, (
            f"VB_FUNNEL_STAGES 단계 수 {len(VB_FUNNEL_STAGES)} != 9 "
            "(RS 관찰 step 8 + RSI 관찰 step 9 확장)."
        )
        step_nos = [s.step_no for s in VB_FUNNEL_STAGES]
        assert 8 in step_nos and 9 in step_nos, (
            f"step_no 8/9 (RS/RSI 관찰) 누락: {step_nos}"
        )
        names = " ".join(s.step_name for s in VB_FUNNEL_STAGES if s.step_no in (8, 9))
        assert ("RS" in names or "상대강도" in names), (
            f"step 8/9 이름에 RS(상대강도) 관찰 부재: {names!r}"
        )
        assert "RSI" in names, f"step 8/9 이름에 RSI 관찰 부재: {names!r}"


# ---------------------------------------------------------------------------
# G-B4 — prepare 말미 호출 (quant 훅 옆/뒤, AST)
# ---------------------------------------------------------------------------
class TestHookCalledInPrepare:
    def test_observe_hook_called_in_prepare(self):
        src = _VB_SRC.read_text(encoding="utf-8")
        assert "self._apply_rs_rsi_observe_in_prepare(" in src, (
            "prepare 내 self._apply_rs_rsi_observe_in_prepare(...) 호출부 미발견 (G-B4)."
        )
        # quant 훅과 동일 영역(말미) — quant 훅 호출 이후(또는 인접) 위치
        prepare_body = _method_source("prepare")
        assert "_apply_rs_rsi_observe_in_prepare" in prepare_body, (
            "prepare 본체에 RS/RSI 관찰 훅 호출 부재 — 말미 배선 위반 (G-B4)."
        )


# ---------------------------------------------------------------------------
# SAFETY (AST) — 훅 영역 check_exit 호출 0 + risk/order import 0 + check_buy/exit diff 0
# ---------------------------------------------------------------------------
class TestSafetyIsolation:
    def test_hook_no_exit_call(self):
        body = _method_source("_apply_rs_rsi_observe_in_prepare")
        assert body, "_apply_rs_rsi_observe_in_prepare 미발견 (Part B 산출물)."
        assert "check_exit_signal" not in body, (
            "관찰 훅 영역에 check_exit_signal 호출 — 매수 진입 전 영역 위반 (사이클 38)."
        )

    def test_hook_no_risk_order_import(self):
        body = _method_source("_apply_rs_rsi_observe_in_prepare")
        assert body, "_apply_rs_rsi_observe_in_prepare 미발견."
        for token in ("order_engine", "from src.engine.risk", "import risk"):
            assert token not in body, (
                f"관찰 훅 영역에 '{token}' import — 매매 hot path 결합 위반 (SAFETY)."
            )

    def test_check_buy_exit_no_rs_rsi_token(self):
        for method in ("check_buy_signal", "check_exit_signal"):
            body = _method_source(method)
            assert body, f"{method} 미발견."
            for token in (
                "_apply_rs_rsi_observe_in_prepare", "relative_strength",
                "rsi(", "rs_filter_enabled", "rsi_filter_enabled",
            ):
                assert token not in body, (
                    f"{method} 본체에 관찰 토큰 '{token}' 인젝션 — 매매 로직 diff 0 위반 (SAFETY)."
                )
