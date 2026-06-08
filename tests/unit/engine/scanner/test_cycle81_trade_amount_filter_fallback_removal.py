"""사이클 81 (2026-06-08) Red — F 카테고리: 거래대금 필터 2순위 폴백 폐기 (C-3, MEDIUM).

> **선행 명세**: `_workspace/red/cycle81_price_filter_key_fix.md` (§F)
> **자문 응답**: domain-expert (CTPF1002R `acml_tr_pbmn` 도 미존재 키 → 2순위 폴백 폐기)
> **선례**: 사이클 65 B-5 패턴 답습 (2순위 → 1순위 단독으로 축소)

결함:
- `src/engine/scanner.py:330-345` `_get_acml_tr_pbmn` 2순위 폴백
- `stock_master.raw.get("acml_tr_pbmn", 0)` ← CTPF1002R 미존재 키 (가격 필터 동일 결함)
- 1순위 (scanner `ticker_market_info["trade_amount_raw"]`) 는 정상 작동 중

시정 (backend-dev 후속):
- 2순위 폴백 전체 폐기 → 1순위 단독 + miss=0 (graceful 통과 위임)

요구 행위 (3 케이스):
- F-1: 2순위 폴백 분기 진입 X (scanner 1순위 단독)
- F-2: AST 정적 가드 — 별도 파일 (`tests/unit/ast/test_cycle81_ast_price_filter_key.py`)
- F-3: scanner.ticker_market_info 1순위 단독 + miss=graceful 통과 (Q6-1 영속)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_cycle81_scanner_state():
    """사이클 81 scanner 모듈 전역 reset."""
    from src.engine import scanner

    if hasattr(scanner, "_trade_amount_filter_cache"):
        scanner._trade_amount_filter_cache = None
    if hasattr(scanner, "_trade_amount_filter_cache_expires_at"):
        scanner._trade_amount_filter_cache_expires_at = 0.0
    yield
    if hasattr(scanner, "_trade_amount_filter_cache"):
        scanner._trade_amount_filter_cache = None
    if hasattr(scanner, "_trade_amount_filter_cache_expires_at"):
        scanner._trade_amount_filter_cache_expires_at = 0.0


# ---------------------------------------------------------------------------
# F-1: 2순위 폴백 폐기 검증 — scanner miss 시 stock_master 호출 X
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F1_no_stock_master_fallback_when_scanner_miss(monkeypatch):
    """F-1: scanner miss 시에도 stock_master 폴백 호출 0건 + 0 반환.

    사이클 65 B-5 패턴 답습 — 2순위 폴백 폐기 = stock_master 호출 0건 보장.

    Red 상태: 현재 2순위 분기 진입 → stock_master.get 호출 1건 = FAIL.
    Green 상태: 2순위 분기 폐기 → stock_master.get 호출 0건 + 0 반환 (graceful) = PASS.
    """
    from src.engine import scanner

    # scanner ticker_market_info miss
    monkeypatch.setattr(scanner, "ticker_market_info", {}, raising=False)

    # stock_master.get 호출 추적 — 폐기 후 호출 0 의무
    sm_get_mock = AsyncMock()
    with patch("src.db.stock_master.get", sm_get_mock):
        result = await scanner._get_acml_tr_pbmn("A001")

    assert result == 0, (
        f"F-1: scanner miss 시 0 반환 의무 (graceful 통과 위임). 실제 {result}"
    )
    assert sm_get_mock.call_count == 0, (
        f"F-1 (HIGH): 2순위 폴백 폐기 의무 — stock_master.get 호출 0건. "
        f"실제 {sm_get_mock.call_count}건 — CTPF1002R 미존재 키 `acml_tr_pbmn` 잔존 결함."
    )


# ---------------------------------------------------------------------------
# F-2: AST 정적 가드 (별도 파일)
# ---------------------------------------------------------------------------
# tests/unit/ast/test_cycle81_ast_price_filter_key.py 에서 `_get_acml_tr_pbmn` 영역
# 의 `"acml_tr_pbmn"` 문자열 0건 + stock_master.get 호출 0건 정적 검증.


# ---------------------------------------------------------------------------
# F-3: scanner 1순위 단독 + miss=graceful 통과 (Q6-1 영속)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_F3_scanner_first_hit_only_miss_returns_zero(monkeypatch):
    """F-3: scanner.ticker_market_info 1순위 hit → 값 반환 / miss → 0 반환 (graceful).

    사이클 65 Q6-1 09:00 race graceful 영속 — 시스템 매매 무용 차단.
    """
    from src.engine import scanner

    # 1순위 hit 검증
    monkeypatch.setattr(
        scanner, "ticker_market_info",
        {"A001": {"trade_amount_raw": 30_000_000_000}},  # 300억
        raising=False,
    )

    sm_get_mock = AsyncMock()
    with patch("src.db.stock_master.get", sm_get_mock):
        result = await scanner._get_acml_tr_pbmn("A001")

    assert result == 30_000_000_000, (
        f"F-3 1순위 hit: scanner ticker_market_info[trade_amount_raw] 반환 의무. 실제 {result}"
    )
    assert sm_get_mock.call_count == 0, (
        "F-3 1순위 hit 시 stock_master.get 호출 0건 의무 (사이클 65 B-5-1 패턴 답습)"
    )

    # miss 검증 — 동일 함수 호출 시 0 반환 (graceful 통과 위임)
    monkeypatch.setattr(scanner, "ticker_market_info", {}, raising=False)

    sm_get_mock2 = AsyncMock()
    with patch("src.db.stock_master.get", sm_get_mock2):
        result_miss = await scanner._get_acml_tr_pbmn("B999")

    assert result_miss == 0, (
        f"F-3 miss: scanner miss + 폴백 폐기 → 0 반환 의무 (graceful). 실제 {result_miss}"
    )
    assert sm_get_mock2.call_count == 0, (
        f"F-3 miss 시 stock_master.get 호출 0건 의무 (2순위 폴백 폐기). "
        f"실제 {sm_get_mock2.call_count}건"
    )
