"""사이클 21 — Momentum `_scan_stats` 회귀 가드.

Momentum 은 prepare() 가 비어 있고 09:30 실시간 `scanner.scan_stocks()` 기반.
→ `scanner.scan_filter_stats` 모듈 전역 dict (7 키) 를 도입하고
`MomentumStrategy.get_scan_stats()` 가 그 사본을 반환한다.

Red 단계:
- `scanner.scan_filter_stats` 부재 → AttributeError
- `MomentumStrategy.get_scan_stats()` 부재 → AttributeError
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def momentum(monkeypatch):
    """scanner 격리한 Momentum 인스턴스."""
    return MomentumStrategy(
        StrategyConfig(strategy_id="momentum", name="모멘텀", weight=0.25)
    )


# ---------------------------------------------------------------------------
# 1. scanner.scan_filter_stats — 7 키 dict 모듈 전역
# ---------------------------------------------------------------------------
def test_scan_filter_stats_initialized_with_seven_keys():
    """`scanner.scan_filter_stats` 가 7 키 dict 로 초기화된다."""
    from src.engine import scanner

    assert hasattr(scanner, "scan_filter_stats")
    expected_keys = {
        "universe_candidates",
        "rate_pass",
        "mcap_pass",
        "trade_amount_pass",
        "limit_up_excluded",
        "final_prepared",
        "last_run_at",
    }
    assert set(scanner.scan_filter_stats.keys()) == expected_keys


# ---------------------------------------------------------------------------
# 2. scan_stocks() — 카운터 누적 검증
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_stocks_accumulates_scan_filter_stats(monkeypatch):
    """`scan_stocks()` 가 `scan_filter_stats` 의 각 단계 카운터를 갱신한다.

    시나리오 (5 종목):
    - "111111": 등락률 20%, 시총 5000억, 거래대금 500억 → 통과
    - "222222": 등락률 10% → rate_pass 미통과
    - "333333": 등락률 20%, 시총 500억 → mcap_pass 미통과
    - "444444": 등락률 20%, 시총 5000억, 거래대금 10억 → trade_amount_pass 미통과
    - "555555": 등락률 30%(상한가) → limit_up_excluded
    """
    from src.engine import scanner

    fake_raw = [
        {  # 통과
            "stck_shrn_iscd": "111111",
            "hts_kor_isnm": "통과종목",
            "prdy_ctrt": "20.0",
            "stck_prpr": "50000",
            "lstn_stcn": "10000000",  # 5000억
            "acml_tr_pbmn": "50000000000",  # 500억
        },
        {  # 등락률 미달
            "stck_shrn_iscd": "222222",
            "hts_kor_isnm": "등락률미달",
            "prdy_ctrt": "10.0",
            "stck_prpr": "50000",
            "lstn_stcn": "10000000",
            "acml_tr_pbmn": "50000000000",
        },
        {  # 시총 미달
            "stck_shrn_iscd": "333333",
            "hts_kor_isnm": "시총미달",
            "prdy_ctrt": "20.0",
            "stck_prpr": "5000",
            "lstn_stcn": "10000000",  # 500억
            "acml_tr_pbmn": "50000000000",
        },
        {  # 거래대금 미달
            "stck_shrn_iscd": "444444",
            "hts_kor_isnm": "거래대금미달",
            "prdy_ctrt": "20.0",
            "stck_prpr": "50000",
            "lstn_stcn": "10000000",
            "acml_tr_pbmn": "1000000000",  # 10억
        },
        {  # 상한가
            "stck_shrn_iscd": "555555",
            "hts_kor_isnm": "상한가",
            "prdy_ctrt": "30.0",
            "stck_prpr": "50000",
            "lstn_stcn": "10000000",
            "acml_tr_pbmn": "50000000000",
        },
    ]

    async def fake_fetch_rising_stocks():
        return fake_raw

    # 초기화
    monkeypatch.setattr(scanner, "ticker_names", {})
    monkeypatch.setattr(scanner, "ticker_market_info", {})
    monkeypatch.setattr(scanner, "_last_scan_result", [])
    # scan_filter_stats 도 깨끗하게 초기화 (다른 테스트에서 누적 방지)
    scanner.scan_filter_stats.update({
        "universe_candidates": 0,
        "rate_pass": 0,
        "mcap_pass": 0,
        "trade_amount_pass": 0,
        "limit_up_excluded": 0,
        "final_prepared": 0,
        "last_run_at": None,
    })

    with patch("src.engine.scanner.fetch_rising_stocks", side_effect=fake_fetch_rising_stocks):
        result = await scanner.scan_stocks()

    stats = scanner.scan_filter_stats

    # 5 종목 모두 raw 응답
    assert stats["universe_candidates"] == 5
    # 등락률 15%+ 통과: 111111(20%) + 333333(20%) + 444444(20%) + 555555(30%) = 4
    assert stats["rate_pass"] == 4
    # 시총 1000억 통과: 111111(5000억) + 444444(5000억) + 555555(5000억) = 3 (333333 500억 탈락)
    assert stats["mcap_pass"] == 3
    # 거래대금 200억 통과: 111111(500억) + 333333(500억) + 555555(500억) = 3 (444444 10억 탈락)
    # — mcap_pass / trade_amount_pass 는 각각 단독 평가
    assert stats["trade_amount_pass"] == 3
    # 상한가 제외 = 1 (555555: rate+mcap+trade 모두 통과한 뒤 30%+ 분기에서 떼짐)
    assert stats["limit_up_excluded"] == 1
    # 최종: 111111 만 (등락률 OK + 시총 OK + 거래대금 OK + 상한가 미해당)
    assert stats["final_prepared"] == 1
    assert result == ["111111"]
    assert stats["last_run_at"] is not None


# ---------------------------------------------------------------------------
# 3. MomentumStrategy.get_scan_stats() — 모듈 dict 사본 반환
# ---------------------------------------------------------------------------
def test_get_scan_stats_returns_copy_of_module_dict(momentum):
    """`MomentumStrategy.get_scan_stats()` 가 `scanner.scan_filter_stats` 의 사본을 반환한다."""
    from src.engine import scanner

    # 모듈 dict 시드
    scanner.scan_filter_stats.update({
        "universe_candidates": 15,
        "rate_pass": 10,
        "mcap_pass": 8,
        "trade_amount_pass": 6,
        "limit_up_excluded": 1,
        "final_prepared": 5,
        "last_run_at": "2026-05-20T09:30:00+09:00",
    })

    snapshot = momentum.get_scan_stats()
    # 사본임을 검증 — 수정해도 모듈 dict 영향 없음
    snapshot["universe_candidates"] = 999
    assert scanner.scan_filter_stats["universe_candidates"] == 15
    # 새 호출은 여전히 원본
    assert momentum.get_scan_stats()["universe_candidates"] == 15
    assert momentum.get_scan_stats()["final_prepared"] == 5
