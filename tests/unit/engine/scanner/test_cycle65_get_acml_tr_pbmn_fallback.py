"""사이클 65 (2026-06-06) Red — B-5 카테고리: `_get_acml_tr_pbmn` Q2 옵션 C 통합 폴백 (3 함수).

> **선행 명세**: `_workspace/red/cycle65_trade_amount_filter.md` (§File 3)
> **설계 카드 v2**: `_workspace/cycle65_trade_amount_filter_design_card.md` §2.4
> **자문 응답**: Q2 옵션 C 통합 폴백 (HIGH 핵심) — KIS 호출 0건 추가

Q2 옵션 C 3 경로:
1. `ticker_market_info["trade_amount_raw"]` (scanner 1순위, 원 단위)
2. `stock_master.raw.acml_tr_pbmn` (2순위, 24h TTL 캐시)
3. 둘 다 miss → 0 반환 (graceful 통과 위임)

위험 등급 MEDIUM (옵션 C 통합 폴백 정합성).

요구 행위 (Red 단계 모두 AttributeError 정답 — `_get_acml_tr_pbmn` 미존재):

- test_scanner_first_hit: 1순위 hit → stock_master 호출 0
- test_scanner_miss_stock_master_hit: 2순위 hit → stock_master 호출 1, 정확한 값 반환
- test_both_miss_returns_zero: 양쪽 miss → 0 반환 (graceful 통과 위임)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_cycle65_scanner_state():
    """사이클 65 scanner 모듈 전역 reset — 테스트 격리."""
    from src.engine import scanner

    if hasattr(scanner, "_trade_amount_filter_cache"):
        scanner._trade_amount_filter_cache = None
    if hasattr(scanner, "_trade_amount_filter_cache_expires_at"):
        scanner._trade_amount_filter_cache_expires_at = 0.0
    yield


# ---------------------------------------------------------------------------
# B-5-1: 1순위 hit — scanner ticker_market_info["trade_amount_raw"]
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_acml_tr_pbmn_scanner_first_hit(monkeypatch):
    """1순위 — scanner ticker_market_info hit → stock_master 호출 0건 검증.

    scanner 가 이미 fetch_rising_stocks 호출 + acml_tr_pbmn 보강 중 (KIS 호출 0건 추가).
    """
    from src.engine import scanner  # Red: _get_acml_tr_pbmn 미존재 → AttributeError

    monkeypatch.setattr(
        scanner, "ticker_market_info",
        {"A001": {"trade_amount_raw": 30_000_000_000}},  # 300억
        raising=False,
    )

    # stock_master 호출 추적 — 호출 0 의무
    sm_get_mock = AsyncMock()
    with patch("src.db.stock_master.get", sm_get_mock):
        # Red: `_get_acml_tr_pbmn` 미존재 → AttributeError 정답
        result = await scanner._get_acml_tr_pbmn("A001")

    assert result == 30_000_000_000, (
        f"1순위 hit 결함 — scanner ticker_market_info[trade_amount_raw] 반환 의무 (실제 {result})"
    )
    sm_get_mock.assert_not_called()  # KIS 호출 0건 추가 보존 (Q2 옵션 C 핵심)


# ---------------------------------------------------------------------------
# B-5-2: scanner miss → stock_master.raw.acml_tr_pbmn 2순위 hit
# 사이클 81 시정 — 2순위 폴백 폐기 (CTPF1002R 응답에 acml_tr_pbmn 키 없음).
# @xfail(strict=False): 사이클 65 시점 2순위 폴백 존재 확인 영속 보존 (사이클 66 K-2 패턴 답습).
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 81 시정 — 2순위 stock_master.raw.acml_tr_pbmn 폴백 폐기 "
        "(CTPF1002R 응답에 acml_tr_pbmn 키 없음 domain-expert 확정). "
        "사이클 65 시점 결함 영속 보존 (사이클 66 K-2 xfail 패턴 답습). "
        "시정 완료로 자동 XFAIL 전환 확인."
    ),
)
@pytest.mark.asyncio
async def test_get_acml_tr_pbmn_scanner_miss_stock_master_hit(monkeypatch):
    """2순위 — scanner miss 후 stock_master.raw.acml_tr_pbmn hit.

    stock_master 는 24h TTL 캐시 (CTPF1002R 응답).
    문자열 "15000000000" → int 150억 변환 검증.

    [사이클 81 의미 전환] 2순위 폴백 폐기 → scanner miss 시 0 반환 (graceful).
    xfail(strict=False): 결함 영속 보존 + 시정 완료 자동 XFAIL 가시화.
    """
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_market_info", {}, raising=False)

    # stock_master mock — raw.acml_tr_pbmn = 150억 (문자열 형식)
    basics = MagicMock()
    basics.raw = {"acml_tr_pbmn": "15000000000"}

    with patch("src.db.stock_master.get", AsyncMock(return_value=basics)):
        result = await scanner._get_acml_tr_pbmn("A001")

    assert result == 15_000_000_000, (
        f"2순위 hit 결함 — stock_master.raw.acml_tr_pbmn 반환 의무 (실제 {result})"
    )


# ---------------------------------------------------------------------------
# B-5-3: 둘 다 miss → 0 반환 (graceful 통과 위임)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_acml_tr_pbmn_both_miss_returns_zero(monkeypatch):
    """양쪽 miss → 0 반환. `_apply_trade_amount_filter` 가 graceful 통과 처리 (Q6-1)."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_market_info", {}, raising=False)

    with patch("src.db.stock_master.get", AsyncMock(return_value=None)):
        result = await scanner._get_acml_tr_pbmn("A001")

    assert result == 0, (
        f"양쪽 miss 시 0 반환 의무 — graceful 통과 위임 (Q6-1 영속) (실제 {result})"
    )
