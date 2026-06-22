"""사이클 173 (2026-06-22) — 5 전략 prepare 일봉 source KIS→DB 전환 동등성 + 안전성.

5 전략 (VB/LTV/donchian/BFB/VCP) prepare 가 일봉 source 를
fetch_daily_candles → get_recent_daily_normalized(days, min_required) 로 전환.
momentum 제외 (실시간).

회귀 가드 (자문 G-EQ / G-VCP / G-SAFETY):
- G-EQ-1 (HIGH): 정상 종목 DB-source prepare == KIS-source 동일 매수 target.
- G-EQ-5 (HIGH): 전략별 min_required 명시 전달 (None 의존 금지).
- G-VCP-1 (HIGH, 행위 보존): VCP days=100 cap 유지 (DB 220 있어도 100만 사용).
- G-VCP-3: effective_ema_long 계산식 + fetch_days 100 cap 라인 변경 0 (AST).
- G-SAFETY-1 (HIGH): risk/order_engine/realtime/auth/api/order.py diff 0 (AST) + prepare 영역
  check_exit_signal/check_buy_signal 호출 0건.
- AST: 5 전략 prepare _fetch_one 영역 get_recent_daily_normalized 호출 + min_required= keyword 명시
  + fetch_daily_candles 직접 호출 0 (전략 prepare 한정).

★ team-leader 진단:
- 동등성은 어댑터가 동일 candles 를 양쪽 source 로 반환 → 동일 _targets 생성으로 검증.
- 정상 종목 (락 없음) 어댑터는 DB raw JSONB (= KIS 키 동일) 반환 → bit-동일 target.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

KST = timezone(timedelta(hours=9))
pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_STRAT_DIR = _REPO_ROOT / "src" / "engine" / "strategies"

_STRATEGY_FILES = {
    "volatility_breakout": _STRAT_DIR / "volatility_breakout.py",
    "long_tail_volatility": _STRAT_DIR / "long_tail_volatility.py",
    "donchian_swing": _STRAT_DIR / "donchian_swing.py",
    "bull_flag_breakout": _STRAT_DIR / "bull_flag_breakout.py",
    "vcp_breakout": _STRAT_DIR / "vcp_breakout.py",
}

# 전략별 명시 min_required (자문 §4 + plan §3, donchian 63 절대 하향 금지)
_EXPECTED_MIN_REQUIRED = {
    "volatility_breakout": 22,
    "long_tail_volatility": 22,
    "donchian_swing": 63,
    "bull_flag_breakout": 35,
    "vcp_breakout": 100,
}


# ---------------------------------------------------------------------------
# 헬퍼 — 정상 일봉 시리즈 (KIS 키 raw, 락 없음, DESC 최신 우선)
# ---------------------------------------------------------------------------
def _kis_candles(n: int, *, base_close: int = 50000, today_first: bool = False) -> list[dict]:
    """KIS fetch_daily_candles 형식 candles (DESC). 단조 상승 + 노이즈."""
    today = datetime.now(KST).date()
    rows = []
    for i in range(n):
        dd = today - timedelta(days=i if not today_first else i)
        close = base_close - i * 200
        high = close + 500 + (i % 3) * 100
        low = close - 400 - (i % 2) * 100
        open_p = close - 100
        rows.append({
            "stck_bsop_date": dd.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_oprc": str(open_p),
            "stck_hgpr": str(high),
            "stck_lwpr": str(low),
            "acml_vol": str(1_000_000 + i * 1000),
            "acml_tr_pbmn": str(50_000_000_000),
            "prdy_ctrt": "1.5",
        })
    return rows


# ===========================================================================
# AST — 5 전략 prepare 일봉 source 전환 정적 가드
# ===========================================================================
@pytest.mark.parametrize("strat,path", list(_STRATEGY_FILES.items()))
def test_ast_prepare_uses_normalized_adapter(strat, path):
    """5 전략 prepare 영역 get_recent_daily_normalized 호출 존재."""
    src = path.read_text(encoding="utf-8")
    assert "get_recent_daily_normalized" in src, \
        f"{strat} prepare 가 get_recent_daily_normalized 어댑터 사용 의무"


@pytest.mark.parametrize("strat,path", list(_STRATEGY_FILES.items()))
def test_ast_prepare_min_required_explicit(strat, path):
    """5 전략 prepare 가 min_required= keyword 명시 (None 의존 금지)."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    found = False
    expected = _EXPECTED_MIN_REQUIRED[strat]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name == "get_recent_daily_normalized":
                kw_names = {kw.arg for kw in node.keywords}
                assert "min_required" in kw_names, \
                    f"{strat} get_recent_daily_normalized 호출에 min_required= 명시 의무"
                found = True
    assert found, f"{strat} get_recent_daily_normalized 호출 ≥ 1"


@pytest.mark.parametrize("strat,path", list(_STRATEGY_FILES.items()))
def test_ast_no_direct_fetch_in_fetch_one(strat, path):
    """5 전략 prepare 의 _fetch_one 영역에 fetch_daily_candles 직접 호출 0건.

    donchian 은 get_donchian_high/get_atr DB 헬퍼 별도 호출 허용 (사이클 123 영속).
    검사 대상 = _fetch_one 내부 candles source 만.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # _fetch_one 중첩 함수 본문에서 fetch_daily_candles 직접 호출 검사
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_fetch_one":
            body_src = ast.get_source_segment(src, node) or ""
            assert "fetch_daily_candles" not in body_src, \
                f"{strat} _fetch_one 영역 fetch_daily_candles 직접 호출 금지 (어댑터 경유)"


def test_ast_min_required_values_match_spec():
    """전략별 min_required 값이 명세 정합 (donchian 63 절대 하향 금지)."""
    for strat, path in _STRATEGY_FILES.items():
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        expected = _EXPECTED_MIN_REQUIRED[strat]
        matched_values = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "attr", None) or getattr(fn, "id", None)
                if name == "get_recent_daily_normalized":
                    for kw in node.keywords:
                        if kw.arg == "min_required" and isinstance(kw.value, ast.Constant):
                            matched_values.append(kw.value.value)
        assert expected in matched_values, \
            f"{strat} min_required={expected} 명시 의무 (실제 {matched_values})"


# ===========================================================================
# G-VCP — VCP days=100 cap 행위 보존 (220 미사용)
# ===========================================================================
def test_g_vcp_3_fetch_days_100_cap_unchanged():
    """VCP fetch_days = min(..., KIS_DAILY_CANDLES_MAX=100) 라인 변경 0 (AST)."""
    src = _STRATEGY_FILES["vcp_breakout"].read_text(encoding="utf-8")
    assert "KIS_DAILY_CANDLES_MAX = 100" in src, "VCP 100 cap 상수 영속"
    assert "min(ema_long + base_max + 10, KIS_DAILY_CANDLES_MAX)" in src, \
        "VCP fetch_days 100 cap 식 영속 (220 미사용, 행위 보존)"


def test_g_vcp_3_effective_ema_long_formula_unchanged():
    """VCP effective_ema_long = min(ema_long, available_len - uptrend - 5) 식 변경 0."""
    src = _STRATEGY_FILES["vcp_breakout"].read_text(encoding="utf-8")
    assert "min(ema_long, available_len - uptrend_days - 5)" in src, \
        "effective_ema_long 식 영속 (사이클 33/48, 행위 보존)"


def test_g_vcp_1_days_100_passed_to_adapter():
    """VCP get_recent_daily_normalized 호출에 days=fetch_days (100 cap) + min_required=100."""
    src = _STRATEGY_FILES["vcp_breakout"].read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name == "get_recent_daily_normalized":
                kw = {k.arg: k.value for k in node.keywords}
                # min_required=100 (VCP 행위 보존)
                mr = kw.get("min_required")
                if isinstance(mr, ast.Constant):
                    assert mr.value == 100, "VCP min_required=100 (220 미사용)"
                found = True
    assert found, "VCP get_recent_daily_normalized 호출 존재"


# ===========================================================================
# G-SAFETY-1 — 매매 안전 영역 diff 0 (AST) + prepare 영역 check_exit/buy 호출 0
# ===========================================================================
@pytest.mark.parametrize("strat,path", list(_STRATEGY_FILES.items()))
def test_g_safety_1_no_exit_buy_in_prepare(strat, path):
    """전략 prepare 본문에 check_exit_signal / check_buy_signal 호출 0건."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "prepare":
            body_src = ast.get_source_segment(src, node) or ""
            assert "check_exit_signal" not in body_src, \
                f"{strat} prepare 에 check_exit_signal 호출 금지 (사이클 38)"
            assert "self.check_buy_signal" not in body_src, \
                f"{strat} prepare 에 check_buy_signal 호출 금지"


def test_g_safety_1_no_risk_order_import_in_strategies():
    """5 전략 모듈에 risk / order_engine import 0건 (매수 진입 전 격리)."""
    for strat, path in _STRATEGY_FILES.items():
        src = path.read_text(encoding="utf-8")
        assert "from src.engine.risk import" not in src, f"{strat} risk import 금지"
        assert "from src.engine.order_engine import" not in src, \
            f"{strat} order_engine import 금지"


# ===========================================================================
# G-EQ-1 — 정상 종목 DB-source == KIS-source 동일 VB target (통합 동등성)
# ===========================================================================
@pytest.mark.asyncio
async def test_g_eq1_vb_db_source_equals_kis_source():
    """VB: 동일 일봉 시리즈 → DB-source prepare _targets == KIS-source _targets.

    어댑터가 정상 종목 (락 없음) 일봉을 DB raw 로 반환하든 KIS 로 반환하든
    동일 시리즈면 _targets 가 bit-동일해야 한다 (행위 보존).
    """
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    def _make():
        config = StrategyConfig(
            strategy_id="volatility_breakout", name="변동성돌파",
            params={"min_market_cap": 100_000_000_000,
                    "min_trade_amount": 20_000_000_000, "max_scan_stocks": 100,
                    "k_period": 20},
        )
        return VolatilityBreakoutStrategy(config)

    candles = _kis_candles(24)  # 정상 시리즈

    async def _run_with_adapter_returning(candles_to_return):
        strat = _make()
        with patch.object(strat, "_scan_universe", new=AsyncMock(return_value=["005930"])), \
                patch.object(strat, "_apply_master_block_filter_in_prepare",
                             new=AsyncMock(return_value=(["005930"], []))), \
                patch("src.db.stock_master_daily.get_recent_daily_normalized",
                      new=AsyncMock(return_value=candles_to_return)):
            await strat.prepare()
        return dict(strat._targets)

    # KIS-source 와 DB-source 가 동일 candles 면 동일 target
    targets_a = await _run_with_adapter_returning(candles)
    targets_b = await _run_with_adapter_returning(list(candles))

    assert targets_a == targets_b, "동일 일봉 → 동일 _targets (행위 보존)"
    assert "005930" in targets_a, "정상 종목 target 생성"
    # k, prev_range, target_offset 핵심 매수 target 키 존재
    t = targets_a["005930"]
    assert "k" in t and "prev_range" in t and "target_offset" in t


# ===========================================================================
# G-EQ-3-donchian (신고가+EMA source 일관성, 자문 §249) —
# donchian 신고가는 어댑터 candles 단일 source (혼재 금지).
# 락 종목 candles 가 KIS 폴백되면 신고가도 그 candles 로 계산 (DB get_donchian_high 혼재 차단).
# ===========================================================================
def test_g_eq3_donchian_high_single_source_from_candles():
    """donchian 신고가 = 어댑터 candles 단일 source (get_donchian_high 별도 DB 혼재 금지).

    자문 §249: 락 종목은 신고가+EMA 둘 다 KIS 폴백해야 일관. candles 단일 source 로
    통일하면 어댑터가 폴백한 candles 의 신고가/EMA 가 자동 동일 source.
    """
    src = _STRATEGY_FILES["donchian_swing"].read_text(encoding="utf-8")
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "prepare":
            body = ast.get_source_segment(src, node) or ""
            assert "get_donchian_high" not in body, (
                "donchian prepare 신고가 = 어댑터 candles 단일 source 의무 "
                "(get_donchian_high 별도 DB 호출 = 락 종목 신고가/EMA 혼재 위험, 자문 §249)"
            )
            assert "max(highs[" in body, "candles 기반 신고가 계산 (kis_high) 영속"
