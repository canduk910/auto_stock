"""사이클 83 G-OP1 — SK스퀘어 (402340) 실데이터 fixture 회귀 검증.

명세 (`_workspace/red/cycle83_scan_pool_eager_refresh.md`):

사용자 보고 케이스 = SK스퀘어 (402340) 현재가 1,122,340원 (사용자 설정
`price_filter_max=500,000원` 2배 초과) 이 funnel "최종 prepared 12" 통과.

근본 원인: stock_master 운영 적재 14건 한정 (보유/익일청산 위주) → SK스퀘어
미적재 → `stock_master.get(402340)` None → `_apply_price_filter` graceful
통과 경로 진입 → 가격필터 무용.

사이클 83 시정 효과: `_scan_pool_eager_refresh_*` 가 후보 풀 SK스퀘어
eager 갱신 → 다음 _scan_loop 사이클에서 `stock_master.get(402340).raw.bfdy_clpr
= 1122340` valid → `_apply_price_filter` skip 발화 (`above_max`) → funnel
"최종 prepared" 미포함 → R6 우회 영구 차단.

기대 동작 (Green, 사이클 84):
- SK스퀘어 후보 풀 유입 → eager refresh 호출 → stock_master upsert
- 직후 `_apply_price_filter` 호출 → `[price_filter_scanner_skip]` 발화
  (`bfdy_clpr=1122340 reason=above_max max=500000`)

Red 단계 (사이클 83):
- 신규 함수 미존재 → 회귀 시나리오 불가 → FAIL.

영속:
- 사이클 81 시정 효과 영속 강화 (키 오타 + stock_master 적재 양쪽 영역)
- 사이클 38 명문화 영속 (매수 진입 전용)
- 사이클 32 R4 영속 (SK스퀘어 보유 0 가정)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_g_op1_sk_square_eager_refresh_then_price_filter_block(caplog, monkeypatch, fake_pg_kv):
    """G-OP1: SK스퀘어 (402340) eager refresh 후 가격필터 정상 차단.

    검증 매트릭스:
    1. SK스퀘어 (402340) candidates 유입
    2. eager refresh 1 회 실행 → `inquire_stock_basics(402340)` 호출 + upsert
       (raw.bfdy_clpr = 1,122,340)
    3. 직후 `_apply_price_filter([402340])` 호출 → 반환 빈 리스트 (차단)
       + `[price_filter_scanner_skip]` 로그 발화 (`above_max max=500000`)

    Red 상태 (사이클 83): 신규 함수 미존재 → FAIL.

    Green (사이클 84):
    - eager refresh 후 `_apply_price_filter` 가 stock_master.get(402340).raw.
      bfdy_clpr = 1,122,340 valid 조회 → above_max (>500000) → skip 발화
    - 사이클 81 시정 효과 영속 강화

    영속 의무:
    - 사이클 81 G-1 (`bfdy_clpr` 키 정확성) 영속
    - 사이클 64 Q1 옵션 D 보유/익일청산 절대 보호 영속 (SK스퀘어 미보유 가정)
    """
    # Red 사전조건
    try:
        from src.engine.scanner import _scan_pool_eager_refresh_loop  # noqa: F401
    except ImportError:
        pytest.fail(
            "\n사이클 83 G-OP1 Red 상태 — `_scan_pool_eager_refresh_loop` 미존재.\n"
            "  Green (사이클 84): backend-dev 가 신규 함수 도입 의무."
        )

    from src.engine import scanner as _scanner_mod
    from src.db import system_config

    # 가격필터 max=500,000 (사용자 설정 가정)
    # 2026-09-26 C2 — 인메모리 KV 로 저장한다. DB 없이 진짜 pg 로 쓰면 모듈 전역 폴백
    # `_price_filter_memory_override` 에 500,000 이 남아 뒤따르는
    # `test_cycle64_…::test_A1`(기본값 0 기대)을 수집 순서에 따라 깨뜨렸다.
    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    await system_config.set_price_filter(min_price=0, max_price=500_000)

    candidates = ["402340"]

    # Step 1: eager refresh 시 stock_master 가 비어있다고 가정 (사용자 보고 케이스)
    refreshed_data: dict[str, MagicMock] = {}

    async def _fake_is_stale(ticker: str, max_age_hours: int = 24) -> bool:
        return ticker not in refreshed_data

    async def _fake_inquire(ticker: str):
        basics = MagicMock()
        basics.ticker = ticker
        basics.raw = {"bfdy_clpr": 1_122_340, "prdy_clpr": 1_122_340}
        basics.market = "KOSPI"
        basics.nxt_tradable = True
        return basics

    async def _fake_upsert(basics):
        refreshed_data[basics.ticker] = basics

    async def _fake_get(ticker: str):
        return refreshed_data.get(ticker)

    # `_collect_protected_tickers_for_scanner` 가 보유/익일청산 조회하므로 빈 set 보장
    async def _fake_protected():
        return set()

    with patch("src.db.stock_master.is_stale", new=AsyncMock(side_effect=_fake_is_stale)), \
         patch("src.api.condition.inquire_stock_basics", new=AsyncMock(side_effect=_fake_inquire)), \
         patch("src.db.stock_master.upsert_one", new=AsyncMock(side_effect=_fake_upsert)), \
         patch("src.db.stock_master.get", new=AsyncMock(side_effect=_fake_get)):
        # Step 1: eager refresh 실행
        try:
            await _scan_pool_eager_refresh_loop(candidates)
        except (ImportError, AttributeError, TypeError) as e:
            pytest.fail(
                f"\n사이클 83 G-OP1 — eager refresh 호출 실패: {type(e).__name__}: {e}\n"
                f"  Green: backend-dev 신규 함수 도입 의무."
            )

        # SK스퀘어 stock_master 적재 확인 (Green 사전조건)
        assert "402340" in refreshed_data, (
            "G-OP1 Green 사전조건 위반: SK스퀘어 (402340) stock_master upsert 누락.\n"
            "  Green 시점에 eager refresh hook 이 KIS 호출 + upsert 의무."
        )

        # Step 2: 가격필터 적용
        import logging
        caplog.set_level(logging.INFO, logger="src.engine.scanner")

        # 가격필터 캐시 invalidate (60s TTL)
        try:
            _scanner_mod.invalidate_price_filter_cache_scanner()
        except Exception:
            pass

        survived = await _scanner_mod._apply_price_filter(
            candidates, protected_tickers=set()
        )

    # 본 가드 1: SK스퀘어 차단 (survived 에서 제외)
    assert "402340" not in survived, (
        f"\n사이클 83 G-OP1 위반 — SK스퀘어 (402340) 가격필터 차단 실패:\n"
        f"  survived: {survived}\n"
        f"  현재가 bfdy_clpr=1,122,340 > max=500,000 → above_max 차단 의무\n"
        f"  사이클 81 G-1 (bfdy_clpr 키) + 사이클 83 eager refresh 결합 효과"
    )

    # 본 가드 2: `[price_filter_scanner_skip]` 로그 발화
    log_messages = [r.message for r in caplog.records]
    skip_logs = [
        msg for msg in log_messages
        if "[price_filter_scanner_skip]" in msg and "402340" in msg
    ]
    assert skip_logs, (
        f"\n사이클 83 G-OP1 위반 — `[price_filter_scanner_skip]` 402340 로그 발화 누락:\n"
        f"  전체 로그: {log_messages}\n"
        f"  Green: eager refresh + 가격필터 차단 결합 시 운영 가시화 의무"
    )
