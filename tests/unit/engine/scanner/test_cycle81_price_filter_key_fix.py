"""사이클 81 (2026-06-08) Red — SK스퀘어 가격필터 미작동 silent 결함 시정 (C-1, HIGH).

> **선행 명세**: `_workspace/red/cycle81_price_filter_key_fix.md`
> **자문 응답**: domain-expert (사이클 64 Q2 가정 오류 confirm — CTPF1002R 정본 키 = `bfdy_clpr`)
> **선례**: 사이클 64 B 카테고리 + C 카테고리 + E 카테고리 패턴 100% 답습

결함:
- `src/engine/scanner.py:166` `basics.raw.get("prdy_clpr", 0)` — CTPF1002R 미존재 키
- 30일+ 운영 실측 `[price_filter_scanner_skip]` 0건 — SK스퀘어 1,122,000원 통과

시정 (backend-dev 후속):
- `"prdy_clpr"` → `"bfdy_clpr"` (1 줄)

요구 행위:
- A 키 정정 검증 (3 케이스, HIGH)
- B above_max 차단 회귀 (3 케이스, HIGH, SK스퀘어 시나리오 직접 재현)
- C graceful 통과 영속 (2 케이스)
- D 보유/익일청산 보호 영속 (1 케이스, 사이클 64 Q1 옵션 D)
- E funnel + DailyEmitCap 영속 (2 케이스)

= 11 케이스
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _make_pf(min_price=0, max_price=0):
    """PriceFilter 헬퍼 — mode 인자 폐기 (사이클 64)."""
    from src.db.system_config import PriceFilter
    return PriceFilter(min_price=min_price, max_price=max_price)


def _make_basics_bfdy(ticker: str, bfdy_clpr: int, *, also_prdy: int | None = None):
    """StockBasics mock — raw.bfdy_clpr (정본 키) + 선택적 prdy_clpr (오염 키).

    `also_prdy` 지정 시 raw 에 prdy_clpr 도 포함 → A-2 가 bfdy_clpr 만 사용함을 검증.
    """
    from src.models.stock import StockBasics

    raw: dict[str, str] = {"bfdy_clpr": str(bfdy_clpr)}
    if also_prdy is not None:
        raw["prdy_clpr"] = str(also_prdy)
    return StockBasics(
        ticker=ticker, name=f"종목{ticker}",
        excg_dvsn_cd="1", nxt_tradable=True,
        krx_halted=False, admin_item=False,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# autouse fixture — scanner 모듈 전역 reset (테스트 격리)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_cycle81_scanner_state():
    """사이클 81 scanner 모듈 전역 reset — DailyEmitCap + 카운터 격리."""
    from src.engine import scanner

    # 사전 reset
    if hasattr(scanner, "_price_filter_scanner_skip_logged_today"):
        scanner._price_filter_scanner_skip_logged_today.clear()
    if hasattr(scanner, "_price_filter_scanner_skip_count_today"):
        for k in list(scanner._price_filter_scanner_skip_count_today):
            scanner._price_filter_scanner_skip_count_today[k] = 0
    yield
    # 사후 reset
    if hasattr(scanner, "_price_filter_scanner_skip_logged_today"):
        scanner._price_filter_scanner_skip_logged_today.clear()
    if hasattr(scanner, "_price_filter_scanner_skip_count_today"):
        for k in list(scanner._price_filter_scanner_skip_count_today):
            scanner._price_filter_scanner_skip_count_today[k] = 0


# ===========================================================================
# A. 키 정정 검증 (HIGH, 3 케이스)
# ===========================================================================

# ---------------------------------------------------------------------------
# A-1 [HIGH]: bfdy_clpr 키 조회 검증
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A1_uses_bfdy_clpr_key_for_filter_evaluation(monkeypatch):
    """A-1 (HIGH): `_apply_price_filter` 가 `basics.raw["bfdy_clpr"]` 키를 조회해야 한다.

    raw 에 bfdy_clpr=1,200,000 만 존재 + max=500,000 → above_max 차단되어야 함.
    Red 상태: 현재 prdy_clpr 키만 조회 → 미확보 0 → graceful 통과 = FAIL.
    Green 상태: bfdy_clpr 추출 → above_max 차단 = PASS.
    """
    from src.engine import scanner

    candidates = ["005930"]
    pf = _make_pf(min_price=0, max_price=500_000)
    # raw 에 bfdy_clpr 만 (prdy_clpr 없음) — 정본 키 단독 추출 검증
    basics = _make_basics_bfdy("005930", bfdy_clpr=1_200_000)

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == [], (
        "A-1 (HIGH): bfdy_clpr=1,200,000 + max=500,000 → above_max 차단 의무. "
        f"실제 {result} — `prdy_clpr` 키 조회 잔존 (CTPF1002R 미존재 키) 결함."
    )


# ---------------------------------------------------------------------------
# A-2 [HIGH]: prdy_clpr 키 무시 + bfdy_clpr 만 사용
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_A2_ignores_prdy_clpr_when_bfdy_clpr_present(monkeypatch):
    """A-2 (HIGH): raw 에 두 키 모두 존재 시 bfdy_clpr 만 평가 — prdy_clpr 무시.

    mock raw={"prdy_clpr": 999, "bfdy_clpr": 1200000} + max=500,000
    → bfdy_clpr=1,200,000 평가 → above_max 차단.

    Red 상태: prdy_clpr=999 평가 → max=500,000 미만 → 통과 = FAIL.
    Green 상태: bfdy_clpr=1,200,000 평가 → above_max 차단 = PASS.
    """
    from src.engine import scanner

    candidates = ["005930"]
    pf = _make_pf(min_price=0, max_price=500_000)
    # raw 에 prdy_clpr=999 (오염) + bfdy_clpr=1,200,000 (정본)
    basics = _make_basics_bfdy("005930", bfdy_clpr=1_200_000, also_prdy=999)

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == [], (
        "A-2 (HIGH): bfdy_clpr=1,200,000 우선 평가 → above_max 차단 의무. "
        f"실제 {result} — `prdy_clpr=999` 오염 키 평가 결함 (CTPF1002R 정본 미사용)."
    )


# ---------------------------------------------------------------------------
# A-3: AST 정적 가드 — 별도 파일 (tests/unit/ast/test_cycle81_ast_price_filter_key.py)
# ---------------------------------------------------------------------------
# (이 파일은 _apply_price_filter 영역의 "prdy_clpr" 잔존 0건 정적 검증을 별도 파일에서 다룬다)


# ===========================================================================
# B. above_max 차단 회귀 (HIGH, 3 케이스 — SK스퀘어 시나리오 직접 재현)
# ===========================================================================

# ---------------------------------------------------------------------------
# B-1 [HIGH]: SK스퀘어 시나리오 (bfdy_clpr=1,122,000, max=500,000)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B1_sk_square_above_max_blocked(monkeypatch):
    """B-1 (HIGH): SK스퀘어 결함 재현 — bfdy_clpr=1,122,000 + max=500,000 → above_max 차단.

    운영 실측 30일+ `[price_filter_scanner_skip]` 0건 사고의 직접 재현.
    Red 상태: prdy_clpr 조회 → 미확보 0 → graceful 통과 = FAIL (SK스퀘어 결함 재현).
    Green 상태: bfdy_clpr=1,122,000 추출 → above_max 차단 = PASS.
    """
    from src.engine import scanner

    candidates = ["402340"]  # SK스퀘어 ticker
    pf = _make_pf(min_price=0, max_price=500_000)
    basics = _make_basics_bfdy("402340", bfdy_clpr=1_122_000)

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == [], (
        "B-1 (HIGH) SK스퀘어 시나리오: bfdy_clpr=1,122,000 + max=500,000 → above_max 차단 의무. "
        f"실제 {result} — 30일+ 운영 결함 영속 위험."
    )


# ---------------------------------------------------------------------------
# B-2 [HIGH]: max 임계 통과 (정상 매수 후보 보존)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B2_below_max_passes(monkeypatch):
    """B-2 (HIGH): bfdy_clpr=400,000 + max=500,000 → 통과.

    정상 매수 후보 영구 차단 위험 방지.
    """
    from src.engine import scanner

    candidates = ["A001"]
    pf = _make_pf(min_price=0, max_price=500_000)
    basics = _make_basics_bfdy("A001", bfdy_clpr=400_000)

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == ["A001"], (
        f"B-2: bfdy_clpr=400,000 < max=500,000 → 통과 의무. 실제 {result}"
    )


# ---------------------------------------------------------------------------
# B-3 [HIGH]: below_min 차단 (저가 작전주 회피)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_B3_below_min_blocked(monkeypatch):
    """B-3 (HIGH): bfdy_clpr=2,000 + min=3,000 → below_min 제외.

    저가 작전주 회피 (디폴트 1,000원 권장값 영역).
    """
    from src.engine import scanner

    candidates = ["A002"]
    pf = _make_pf(min_price=3_000, max_price=0)
    basics = _make_basics_bfdy("A002", bfdy_clpr=2_000)

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == [], (
        f"B-3 (HIGH): bfdy_clpr=2,000 < min=3,000 → below_min 차단 의무. 실제 {result}"
    )


# ===========================================================================
# C. graceful 통과 영속 (Q1 옵션 A' 핵심, 2 케이스)
# ===========================================================================

# ---------------------------------------------------------------------------
# C-1: bfdy_clpr 키 부재 → graceful 통과 (사이클 64 Q2/Q3 영속)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_C1_missing_bfdy_clpr_graceful_passes(monkeypatch):
    """C-1: raw 에 bfdy_clpr 키 부재 → survivor 통과 (회귀 미파괴).

    사이클 64 Q2 graceful 통과 영속 — 신규 상장 1일차 영구 차단 방지.
    """
    from src.engine import scanner
    from src.models.stock import StockBasics

    candidates = ["NEWIPO"]
    pf = _make_pf(min_price=3_000, max_price=500_000)

    # raw 에 bfdy_clpr 키 자체 없음 (신규 상장 시나리오)
    basics = StockBasics(
        ticker="NEWIPO", name="신규상장",
        excg_dvsn_cd="1", nxt_tradable=True,
        krx_halted=False, admin_item=False,
        raw={"other_key": "1"},  # bfdy_clpr 미존재
    )

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == ["NEWIPO"], (
        f"C-1: bfdy_clpr 키 부재 → graceful 통과 의무 (신규 상장 영구 차단 방지). 실제 {result}"
    )


# ---------------------------------------------------------------------------
# C-2: bfdy_clpr=0 → graceful 통과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_C2_bfdy_clpr_zero_graceful_passes(monkeypatch):
    """C-2: bfdy_clpr=0 → survivor 통과 (graceful)."""
    from src.engine import scanner

    candidates = ["ZEROCL"]
    pf = _make_pf(min_price=3_000, max_price=500_000)
    basics = _make_basics_bfdy("ZEROCL", bfdy_clpr=0)

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(candidates, protected_tickers=set())

    assert result == ["ZEROCL"], (
        f"C-2: bfdy_clpr=0 → graceful 통과 의무. 실제 {result}"
    )


# ===========================================================================
# D. 보유/익일청산 보호 영속 (사이클 64 Q1 옵션 D, 1 케이스)
# ===========================================================================

# ---------------------------------------------------------------------------
# D-1 [HIGH]: 보유 종목 above_max 라도 early-return 통과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_D1_protected_ticker_above_max_early_return(monkeypatch):
    """D-1 (HIGH): 보유 ticker 가 above_max (bfdy_clpr=2,000,000 > max=500,000) 이어도 통과.

    사이클 64 Q1 옵션 D 3중 안전망 영속 — 보유/익일청산 절대 보호.
    CLAUDE.md "WebSocket 시세 보유·익일청산 우선 보장" 절대 규칙.
    """
    from src.engine import scanner

    candidates = ["HELD01"]
    pf = _make_pf(min_price=0, max_price=500_000)
    # 보유 종목이고 above_max 인데 stock_master.get 호출이 일어나도 무방하지만
    # early-return 검증 — bfdy_clpr 값은 의미 없음 (조회 자체 skip)
    basics = _make_basics_bfdy("HELD01", bfdy_clpr=2_000_000)

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        result = await scanner._apply_price_filter(
            candidates, protected_tickers={"HELD01"},
        )

    assert result == ["HELD01"], (
        "D-1 (HIGH) 보유 종목 보호 위반 — bfdy_clpr=2,000,000 > max=500,000 이어도 "
        f"early-return 통과 의무 (사이클 64 Q1 옵션 D 영속). 실제 {result}"
    )


# ===========================================================================
# E. funnel step_no=98 + DailyEmitCap 영속 (2 케이스)
# ===========================================================================

# ---------------------------------------------------------------------------
# E-1: above_max 차단 시 [price_filter_scanner_skip] INFO 1행 emit
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_E1_above_max_emit_one_skip_log(monkeypatch, caplog: pytest.LogCaptureFixture):
    """E-1: above_max 1회 ticker 만 `[price_filter_scanner_skip]` 1행 emit.

    Red 상태: 현재 prdy_clpr 조회 → 미확보 0 → graceful 통과 → emit 0건 = FAIL.
    Green 상태: bfdy_clpr 추출 → above_max 차단 → emit 1행 = PASS.
    """
    from src.engine import scanner

    candidates = ["005930"]
    pf = _make_pf(min_price=0, max_price=500_000)
    basics = _make_basics_bfdy("005930", bfdy_clpr=1_122_000)

    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        await scanner._apply_price_filter(candidates, protected_tickers=set())

    skip_logs = [
        r for r in caplog.records
        if "[price_filter_scanner_skip]" in r.message
    ]
    assert len(skip_logs) == 1, (
        f"E-1: `[price_filter_scanner_skip]` 1행 emit 의무 (실제 {len(skip_logs)}건). "
        "Red 상태 = bfdy_clpr 미조회 → 차단 안 됨 → emit 0건 결함 재현."
    )
    assert "005930" in skip_logs[0].message
    assert "above_max" in skip_logs[0].message


# ---------------------------------------------------------------------------
# E-2: 같은 ticker 두 번째 호출 시 emit 안 함 (DailyEmitCap)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_E2_daily_emit_cap_second_call_no_emit(monkeypatch, caplog: pytest.LogCaptureFixture):
    """E-2: 같은 ticker 두 번째 호출 시 emit 안 함 (DailyEmitCap 1회/ticker/일).

    매 스캔 폭주 차단 의무 영속 (사이클 64 E 카테고리 답습).
    """
    from src.engine import scanner

    candidates = ["005930"]
    pf = _make_pf(min_price=0, max_price=500_000)
    basics = _make_basics_bfdy("005930", bfdy_clpr=1_122_000)

    caplog.set_level(logging.INFO, logger="src.engine.scanner")

    with patch("src.engine.scanner.get_price_filter", AsyncMock(return_value=pf)), \
         patch("src.db.stock_master.get", AsyncMock(return_value=basics)), \
         patch("src.db.system_logs.write_log", AsyncMock()), \
         patch("src.db.strategy_funnel.insert_snapshot", AsyncMock()):
        # 1회차
        await scanner._apply_price_filter(candidates, protected_tickers=set())
        # 2회차
        await scanner._apply_price_filter(candidates, protected_tickers=set())

    skip_logs = [
        r for r in caplog.records
        if "[price_filter_scanner_skip]" in r.message
    ]
    assert len(skip_logs) == 1, (
        f"E-2: DailyEmitCap 1회/ticker/일 의무 (실제 {len(skip_logs)}건). "
        "두 번째 호출 emit 발화 = 매 스캔 폭주 결함."
    )
