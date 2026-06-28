"""사이클 64 (2026-06-06) Red — C 카테고리: 보유/익일청산 절대 보호 (4 케이스, **HIGH**).

> **선행 명세**: `_workspace/red/cycle64_price_filter_scanner.md` (§C)
> **자문 응답**: `_workspace/cycle64_price_filter_scanner_domain_response.md` (Q1 옵션 D 3중 안전망)
> **선례**: 사이클 32 R4 `_evaluate_universe_guard` (보유/익일청산 보호 패턴 직답습 의무)
> **위험 등급**: **HIGH** — 시세 끊김 → 손절 발화 0 결함 직접 영역

요구 행위 (Red 단계 모두 ImportError / AttributeError 정답):

- C-1: 보유 종목 임계 외 가격이라도 필터 통과 (`_apply_price_filter` 최상단 early-return)
- C-2: `_pending_next_day_clear` 종목 임계 외라도 필터 통과
- C-3: 보유 + 익일청산 합집합 종목 통과 (둘 다 protected)
- C-4: **`_collect_protected_tickers_for_scanner()` 헬퍼 단독 검증** — `registry.all().positions` ∪ `_pending_next_day_clear` 정확 합집합

위험 매트릭스:
- C-1~C-3 = 옵션 D early-return 가드 정확성 (시세 끊김 결함 차단)
- C-4 = 헬퍼 정확성 (lazy import + try/except graceful + scheduler 미초기화 호환)

CLAUDE.md 절대 규칙 보호:
- "**WebSocket 시세 보유·익일청산 우선 보장**" — scanner 차단 = 구독 안 됨 → stale → 손절 0건. 5/19 005935 사고 패턴 차단 영속
- "**`tradable_boards` 매수 진입 전용 (사이클 38)**" — 매도/익일청산은 보호 종목 정상 보존
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 사이클 183 — 캐시 격리 (stale-4 전환 후 모듈 캐시 오염 차단, 의미 전환 0)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_price_filter_cache_c():
    """_apply_price_filter 캐시 격리 — 테스트 간 TTL 캐시 오염 차단."""
    from src.engine import scanner
    if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
        scanner.invalidate_price_filter_cache_scanner()
    yield
    if hasattr(scanner, "invalidate_price_filter_cache_scanner"):
        scanner.invalidate_price_filter_cache_scanner()


def _make_pf(min_price=10_000, max_price=100_000):
    """activate 활성 PriceFilter."""
    from src.db.system_config import PriceFilter
    return PriceFilter(min_price=min_price, max_price=max_price)


def _make_basics(ticker: str, prdy_clpr: int):
    """사이클 81 시정 — bfdy_clpr 정본 키 사용 (파라미터명 호환 보존)."""
    from src.models.stock import StockBasics
    return StockBasics(
        ticker=ticker, name="", excg_dvsn_cd="",
        nxt_tradable=True, krx_halted=False, admin_item=False,
        raw={"bfdy_clpr": str(prdy_clpr)},  # 사이클 81 시정 — CTPF1002R 정본 키
    )


# ===========================================================================
# C-1: 보유 종목 임계 외라도 필터 통과 (HIGH)
# ===========================================================================
@pytest.mark.asyncio
async def test_C1_held_ticker_passes_even_outside_range():
    """C-1 (HIGH): 보유 종목 005930 (prdy_clpr=3000, min=10000 미달) → 필터 통과.

    옵션 D 최상단 early-return — `if ticker in protected_tickers: continue` (필터 평가 skip).
    KIS 호출 비용 0 + stock_master 호출 0 (early-return 이전 단계).

    회귀 가드: 시세 끊김 → 손절 발화 0 결함 차단.
    """
    from src.engine import scanner

    candidates = ["005930"]
    pf = _make_pf(min_price=10_000, max_price=0)
    protected = {"005930"}  # 보유 종목

    # stock_master.get mock — 호출 0 검증 의무 (early-return 보호)
    sm_get = AsyncMock(return_value=_make_basics("005930", prdy_clpr=3000))

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", sm_get), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=protected)

    assert result == ["005930"], (
        f"보유 종목 보호 위반 — 임계 외라도 필터 통과 의무 (실제 {result})"
    )
    # early-return 최적화 검증 — stock_master 호출 0 (필터 평가 skip)
    sm_get.assert_not_called()


# ===========================================================================
# C-2: 익일청산 종목 임계 외라도 필터 통과 (HIGH)
# ===========================================================================
@pytest.mark.asyncio
async def test_C2_next_day_clear_ticker_passes_even_outside_range():
    """C-2 (HIGH): _pending_next_day_clear 종목 임계 외 → 필터 통과.

    옵션 D 헬퍼 `_collect_protected_tickers_for_scanner` 가 `_pending_next_day_clear`
    합집합 포함 의무. 익일 청산 직전 종목 시세 끊김 = 청산 실패 결함 차단.
    """
    from src.engine import scanner

    candidates = ["000660"]
    pf = _make_pf(min_price=10_000, max_price=0)
    protected = {"000660"}  # 익일청산 보류

    sm_get = AsyncMock(return_value=_make_basics("000660", prdy_clpr=500))

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", sm_get), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=protected)

    assert result == ["000660"], "익일청산 보호 위반"
    sm_get.assert_not_called()


# ===========================================================================
# C-3: 보유 + 익일청산 합집합 + 매수 후보 혼합 시 보호 정확성 (HIGH)
# ===========================================================================
@pytest.mark.asyncio
async def test_C3_protected_union_preserved_with_filtering(monkeypatch):
    """C-3 (HIGH): 5 종목 (보유 1 / 익일청산 1 / 매수 후보 3) 입력 →
    보유 + 익일청산 2 종목 보호 + 매수 후보 3 중 임계 통과 1 종목 = 총 3 종목.

    혼합 시나리오 — protected 분기 + 필터 평가 분기 정확성.
    """
    from src.engine import scanner

    # 005930 보유 (저가 차단 대상 prdy=3000)
    # 000660 익일청산 (저가 차단 대상 prdy=500)
    # 035720 매수 후보 (저가 차단 대상 prdy=2000) — 차단
    # 042700 매수 후보 (임계 통과 prdy=50_000) — 통과
    # 012450 매수 후보 (고가 차단 대상 prdy=2_000_000) — 차단
    candidates = ["005930", "000660", "035720", "042700", "012450"]
    pf = _make_pf(min_price=10_000, max_price=100_000)
    protected = {"005930", "000660"}

    async def fake_sm_get(ticker):
        return {
            "035720": _make_basics("035720", prdy_clpr=2000),
            "042700": _make_basics("042700", prdy_clpr=50_000),
            "012450": _make_basics("012450", prdy_clpr=2_000_000),
        }.get(ticker)

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(side_effect=fake_sm_get)), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=protected)

    # 보유 + 익일청산 + 임계 통과 1 = 3
    assert set(result) == {"005930", "000660", "042700"}, (
        f"보호 + 필터 혼합 시나리오 결함 (실제 {result})"
    )
    # 보유/익일청산 종목 순서 유지 (입력 순서)
    assert result.index("005930") < result.index("000660") < result.index("042700"), (
        f"순서 보존 결함: {result}"
    )


# ===========================================================================
# C-4: `_collect_protected_tickers_for_scanner` 헬퍼 단독 검증 (HIGH)
# ===========================================================================
def test_C4_collect_protected_tickers_for_scanner_helper(monkeypatch):
    """C-4 (HIGH, 옵션 D 신규): `_collect_protected_tickers_for_scanner()` 헬퍼 정확성.

    검증 3 영역:
    1. `registry.all().positions` 합집합 (모든 활성 전략)
    2. `_pending_next_day_clear` 합집합 (scheduler.trading_scheduler)
    3. scheduler 미초기화 graceful (단위 테스트 호환 — try/except)
    """
    from src.engine import scanner

    # === 1. registry mock — 2 전략, 각각 1 종목 보유 ===
    strat1 = MagicMock()
    strat1.state = MagicMock(positions={"005930": MagicMock()})
    strat2 = MagicMock()
    strat2.state = MagicMock(positions={"000660": MagicMock()})

    mock_registry = MagicMock()
    mock_registry.all = MagicMock(return_value=[strat1, strat2])

    # === 2. scheduler mock — _pending_next_day_clear 2 종목 ===
    mock_scheduler = MagicMock()
    mock_scheduler._pending_next_day_clear = {("042700", "momentum"), ("035720", "volatility_breakout")}

    mock_sched_module = MagicMock()
    mock_sched_module.trading_scheduler = mock_scheduler

    monkeypatch.setattr("src.engine.scanner.registry", mock_registry, raising=False)
    # scheduler 는 lazy import 패턴 — sys.modules 또는 import 시점 mock
    with patch.dict("sys.modules", {"src.engine.scheduler": mock_sched_module}):
        # Red: `_collect_protected_tickers_for_scanner` 미존재 → AttributeError 정답
        result = scanner._collect_protected_tickers_for_scanner()

    # 검증: 4 종목 합집합 = (보유 2) ∪ (익일청산 2)
    assert isinstance(result, set), f"set 반환 의무 (실제 {type(result)})"
    assert result == {"005930", "000660", "042700", "035720"}, (
        f"`_collect_protected_tickers_for_scanner` 합집합 결함: {result}"
    )

    # === 3. scheduler 미초기화 graceful (try/except) ===
    mock_sched_module_none = MagicMock()
    mock_sched_module_none.trading_scheduler = None  # _boot 전 미초기화 상태
    with patch.dict("sys.modules", {"src.engine.scheduler": mock_sched_module_none}):
        result_no_sched = scanner._collect_protected_tickers_for_scanner()

    # registry 만 반영 (보유 2 종목)
    assert result_no_sched == {"005930", "000660"}, (
        f"scheduler 미초기화 graceful 결함 — registry 만 반영 의무 (실제 {result_no_sched})"
    )
