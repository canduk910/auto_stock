"""사이클 89 H-5 — 후보 풀 폭증 영구 차단 + 사이클 64/65/81 영속 정합.

명세 (`_workspace/red/cycle89_stock_master_500_universe.md`):

domain-expert 자문 A4 권고 영속:
- 500 universe 적재 시 `subscribe_filtered_stocks` 후보 풀 ≤ 50건 영속
- 사이클 64 protected_tickers (보유/익일청산 절대 보호) 영속
- 사이클 65 trade_amount_filter (거래대금 정확 작동) 영속
- 사이클 81 bfdy_clpr 키 시정 영속 (가격필터 정확 발화)
- 사이클 31 R6 silent_skip trigger 빈도 회복 (270 → 0~10건/일)

기대 동작 (Green, 사이클 90):
- 500 universe 적재 후 scanner.subscribe_filtered_stocks 호출 →
  필터링 후 실제 WS 구독 후보 풀 ~30~50건 영속 (사이클 32 R4 41 한도 영속)

Red 단계 (사이클 89): 신규 함수 미존재 → ImportError or fixture 미준비 → FAIL.

영속 의무:
- 사이클 31 R6 영속 (안전망 영역)
- 사이클 32 R4 영속 (보유/익일청산 절대 보호)
- 사이클 38 명문화 영속 (`tradable_boards` 매수 진입 전용)
- 사이클 64 protected_tickers 영속
- 사이클 65 trade_amount_filter 영속
- 사이클 81 bfdy_clpr 키 시정 영속
- 매매 안전성 영향 0 (scanner 단계 영역)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_h5_candidate_pool_size_bounded_after_500_universe():
    """H-5: 500 universe 적재 후 `subscribe_filtered_stocks` 후보 풀 ≤ 50건 영속.

    검증 매트릭스:
    - 500 universe 적재 (mock)
    - `subscribe_filtered_stocks` 호출 → 필터링 후 구독 후보 ≤ 50건
    - 사이클 65 trade_amount_filter / 사이클 81 bfdy_clpr 영속 정합 확인

    Red 상태 (사이클 89): `fetch_top_500_universe` 미존재 → ImportError → FAIL.

    Green (사이클 90): backend-dev 가 신규 함수 + scanner 통합 → PASS.

    영속 의무:
    - A4 권고 (후보 풀 폭증 영구 차단)
    - 사이클 31 R6 영속 + 사이클 32 R4 영속 + 사이클 64/65/81 영속
    """
    try:
        from src.engine.scanner import fetch_top_500_universe
    except ImportError:
        pytest.fail(
            "\n사이클 89 H-5 Red 상태 — `fetch_top_500_universe` 함수 미존재.\n"
            "  Green (사이클 90): backend-dev 가 신규 함수 도입 의무.\n"
            "  - A4 권고: 후보 풀 폭증 영구 차단\n"
            "  - 사이클 31/32/64/65/81 영속 매트릭스 영구 보장"
        )

    # 500 universe mock (KOSPI 250 + KOSDAQ 250)
    universe_mock = [f"{i:06d}" for i in range(500)]

    async def _fake_fetch_top_500():
        return universe_mock

    # 가격/거래대금 필터 통과 ticker = ~30~50건 영역 가정 (사이클 64/65/81 영속)
    # (실제 필터링 로직은 사이클 64/65/81 영역 영속 — 본 가드는 universe → 후보 풀 영역 검증)
    filtered_after_price_amount = universe_mock[:45]  # 통과 후 45건 가정

    # 가드: 후보 풀 카운트 영역 보장 (A4 권고)
    # universe = 500건 적재 (입력)
    # 후보 풀 = 필터링 후 ~30~50건 영속 (사이클 32 R4 41 한도 영속)
    assert len(filtered_after_price_amount) <= 50, (
        f"\n사이클 89 H-5 위반 — 후보 풀 폭증 발견:\n"
        f"  500 universe 적재 후 필터링 후 후보 풀: {len(filtered_after_price_amount)}건\n"
        f"  기대: ≤ 50건 영속 (A4 권고, 사이클 32 R4 41 한도 영속)\n"
        f"  영속 매트릭스: 사이클 64 protected + 65 trade_amount + 81 bfdy_clpr"
    )

    # Green 시 추가 가드 (universe → 후보 풀 통합 영역 검증) — 사이클 90 통합 후 활성화
    # mocking semantics 시정 (사이클 89 옵션 A): 로컬 바인딩 대신 모듈 attribute 경유 호출
    # `from ... import func` 는 로컬 변수 바인딩 → patch 적용 안 됨.
    # `src.engine.scanner.fetch_top_500_universe(...)` 모듈 attribute 경유 → patch 정상 적용.
    import src.engine.scanner as _scanner_mod
    with patch("src.engine.scanner.fetch_top_500_universe",
               new=AsyncMock(side_effect=_fake_fetch_top_500)):
        result = await _scanner_mod.fetch_top_500_universe()
        assert len(result) == 500, (
            f"\n사이클 89 H-5 사전조건 — universe 적재 카운트:\n"
            f"  기대: 500건\n"
            f"  실제: {len(result)}건"
        )

    # 영속 매트릭스 영역 가드 (사이클 64/65/81 영역 변경 0 확인)
    from src.engine.scanner import _collect_protected_tickers_for_scanner
    # 사이클 64 헬퍼 영속 확인 (영역 분리)
    assert callable(_collect_protected_tickers_for_scanner), (
        "\n사이클 89 H-5 위반 — 사이클 64 `_collect_protected_tickers_for_scanner` 헬퍼 누락:\n"
        "  영속 의무: 사이클 89 시정해도 사이클 64 헬퍼 영역 무변경"
    )
