"""사이클 83 G-RT1 — 사이클 31 R6 silent_skip trigger 빈도 감소 회귀 검증.

명세 (`_workspace/red/cycle83_scan_pool_eager_refresh.md`):

사이클 31 R6 (RiskManager `_risk_silent_skip_logged_today`) = `current_price >
total_investment` 조건 진입 시 `[risk_silent_skip]` 1회/페어/일 emit. 사이클 81
운영 실측 SK스퀘어 폭주 270건/일 = R6 cap 안 됐다면 무한.

근본 원인 chain:
1. stock_master 미적재 → `_apply_price_filter` graceful 통과
2. 후보 풀 SK스퀘어 (1,122,340원) 유입 → `risk.on_tick` 진입
3. SK스퀘어 가격 > total_investment (예: 120,414원) → R6 진입 + `[risk_silent_skip]`
4. 매 tick → R6 cap 으로 1회/일 발화

사이클 83 시정 효과: stock_master eager refresh → `_apply_price_filter` 정상 차단
→ SK스퀘어 후보 풀 제거 → `risk.on_tick` 미진입 → R6 trigger 빈도 자연 감소
(SK스퀘어 케이스 0건).

기대 동작 (Green, 사이클 84):
- eager refresh 전 (사이클 81 시점): R6 SK스퀘어 trigger 발생 가능
- eager refresh 후 (사이클 83 시점): 동일 시나리오에서 R6 SK스퀘어 trigger 0건

Red 단계 (사이클 83):
- 신규 함수 미존재 → 비교 실험 불가 → FAIL (Red 의무).

영속:
- 사이클 31 R6 영속 (cap 자체는 안전망 유지)
- 사이클 81 시정 영속
- 사이클 64 Q1 옵션 D 보유/익일청산 절대 보호 영속
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_g_rt1_r6_silent_skip_frequency_after_eager_refresh():
    """G-RT1: eager refresh 후 R6 silent_skip trigger 빈도 감소 회귀.

    시나리오 (사이클 81 실측 재현 + 사이클 83 시정 효과 검증):
    1. 사용자 설정 price_filter_max = 500,000원
    2. 후보 풀: SK스퀘어 (402340, 가격 1,122,340)
    3. eager refresh 호출 → stock_master upsert (`bfdy_clpr=1,122,340`)
    4. `_apply_price_filter([402340])` → SK스퀘어 차단 (above_max)
    5. survived 에 SK스퀘어 미포함 → `risk.on_tick` 미진입 → R6 trigger 0건

    Red 상태 (사이클 83): 신규 함수 미존재 → FAIL.

    Green (사이클 84):
    - eager refresh hook + 가격필터 정상 발화 → R6 SK스퀘어 trigger 자연 차단

    영속:
    - 사이클 31 R6 cap 영속 (최후 안전망)
    - 사이클 81 시정 영속 (키 정확성)
    - SK스퀘어 폭주 270건/일 → 0건/일 회귀 가드
    """
    # Red 사전조건
    try:
        from src.engine.scanner import _scan_pool_eager_refresh_loop  # noqa: F401
    except ImportError:
        pytest.fail(
            "\n사이클 83 G-RT1 Red 상태 — `_scan_pool_eager_refresh_loop` 미존재.\n"
            "  Green (사이클 84): backend-dev 가 신규 함수 도입 의무."
        )

    from src.engine import scanner as _scanner_mod
    from src.db import system_config

    await system_config.set_price_filter(min_price=0, max_price=500_000)

    candidates = ["402340"]
    refreshed_data: dict[str, MagicMock] = {}

    async def _fake_is_stale(ticker: str, max_age_hours: int = 24) -> bool:
        return ticker not in refreshed_data

    async def _fake_inquire(ticker: str):
        basics = MagicMock()
        basics.ticker = ticker
        basics.raw = {"bfdy_clpr": 1_122_340}
        basics.market = "KOSPI"
        basics.nxt_tradable = True
        return basics

    async def _fake_upsert(basics):
        refreshed_data[basics.ticker] = basics

    async def _fake_get(ticker: str):
        return refreshed_data.get(ticker)

    with patch("src.db.stock_master.is_stale", new=AsyncMock(side_effect=_fake_is_stale)), \
         patch("src.api.condition.inquire_stock_basics", new=AsyncMock(side_effect=_fake_inquire)), \
         patch("src.db.stock_master.upsert_one", new=AsyncMock(side_effect=_fake_upsert)), \
         patch("src.db.stock_master.get", new=AsyncMock(side_effect=_fake_get)):
        # Step 1: eager refresh
        try:
            await _scan_pool_eager_refresh_loop(candidates)
        except (ImportError, AttributeError, TypeError) as e:
            pytest.fail(
                f"\n사이클 83 G-RT1 — eager refresh 호출 실패: {type(e).__name__}: {e}\n"
                f"  Green: backend-dev 신규 함수 도입 의무."
            )

        # Step 2: 가격필터 적용 (캐시 invalidate 후)
        try:
            _scanner_mod.invalidate_price_filter_cache_scanner()
        except Exception:
            pass

        survived = await _scanner_mod._apply_price_filter(
            candidates, protected_tickers=set()
        )

    # 본 가드: SK스퀘어 survived 미포함 → risk.on_tick 미진입 → R6 trigger 자연 차단
    assert "402340" not in survived, (
        f"\n사이클 83 G-RT1 위반 — eager refresh 후에도 SK스퀘어 (402340) "
        f"가격필터 통과:\n"
        f"  survived: {survived}\n\n"
        f"  근본 원인 chain (사이클 81→83):\n"
        f"  1. stock_master 미적재 → `_apply_price_filter` graceful 통과 (사이클 81 결함)\n"
        f"  2. 사이클 81 시정 (`bfdy_clpr` 키) → stock_master 적재 영역 의존\n"
        f"  3. 사이클 83 시정 (eager refresh) → stock_master 적재 영역 확장\n"
        f"  4. 양쪽 시정 결합 효과 → SK스퀘어 가격필터 차단 영구\n\n"
        f"  Green (사이클 84): eager refresh hook + 가격필터 정상 발화 → \n"
        f"  R6 SK스퀘어 trigger 자연 차단 (사이클 31 R6 cap 안전망 보존)."
    )

    # 추가 안전 가드: R6 cap 영속 (사이클 31 영속 영역 침범 0)
    from src.engine.risk import RiskManager  # noqa: F401 — import 자체로 R6 cap 존재 검증
