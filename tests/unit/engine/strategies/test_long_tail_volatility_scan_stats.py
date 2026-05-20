"""사이클 21 — LongTailVolatility `_scan_stats` 회귀 가드.

VB 와 동일한 9 키 + `consecutive_limit_pass` 추가 (10 키).

Red 단계: `_empty_scan_stats()` / `_scan_stats` / `get_scan_stats()` 부재 → 실패.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def ltv(monkeypatch):
    """scanner 격리한 LTV 인스턴스."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    return LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="롱테일 변동성", weight=0.2)
    )


# ---------------------------------------------------------------------------
# 1. _empty_scan_stats() — 10 키 dict (consecutive_limit_pass 포함)
# ---------------------------------------------------------------------------
def test_empty_scan_stats_has_ten_keys_with_consecutive_limit_pass():
    """LTV 는 VB 의 9 키 + `consecutive_limit_pass` 추가 = 10 키."""
    from src.engine.strategies.long_tail_volatility import _empty_scan_stats

    stats = _empty_scan_stats()

    expected_keys = {
        "universe_candidates",
        "universe_filtered",
        "price_filtered",
        "mcap_pass",
        "trade_amount_pass",
        "candle_fetch_ok",
        "consecutive_limit_pass",  # LTV 전용
        "k_value_computed",
        "final_prepared",
        "last_run_at",
    }
    assert set(stats.keys()) == expected_keys
    for k, v in stats.items():
        if k == "last_run_at":
            assert v is None
        else:
            assert v == 0, f"키 {k} 초기값이 0이 아님: {v}"


# ---------------------------------------------------------------------------
# 2. prepare() — 연속상한가 종목 분기 카운트 검증
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prepare_excludes_consecutive_limit_up_from_pass_count(ltv, monkeypatch):
    """연속상한가 종목은 `candle_fetch_ok` 통과 후 `consecutive_limit_pass` 미증가.

    2 종목:
    - "111111": 정상 — 모든 단계 통과
    - "222222": 전일 종가가 시가 대비 +28% 연속 → 연속상한가 분기에서 탈락
    """
    from src.engine.strategies import long_tail_volatility as ltv_mod

    ltv.config.params["min_market_cap"] = 100_000_000_000
    ltv.config.params["min_trade_amount"] = 20_000_000_000
    ltv.config.params["exclude_consecutive_limit"] = 2

    fake_rank_items = [
        {
            "mksc_shrn_iscd": "111111",
            "hts_kor_isnm": "정상종목",
            "stck_prpr": "50000",
            "lstn_stcn": "10000000",
            "prdy_vol": "1000000",
            "prdy_vrss": "1000",
        },
        {
            "mksc_shrn_iscd": "222222",
            "hts_kor_isnm": "연속상한가",
            "stck_prpr": "50000",
            "lstn_stcn": "10000000",
            "prdy_vol": "1000000",
            "prdy_vrss": "1000",
        },
    ]

    async def fake_kis_get(path, tr_id, params):
        if "volume-rank" in path:
            return {"output": fake_rank_items}
        return {"output": []}

    async def fake_fetch_daily_candles(ticker, days):
        from datetime import date
        today = date.today().strftime("%Y%m%d")
        if ticker == "222222":
            # 연속상한가 — open 대비 close 가 +28% 이상 (>25%) 2일 연속
            return [
                {"stck_bsop_date": today, "stck_hgpr": "51000", "stck_lwpr": "50000", "stck_oprc": "50500", "stck_clpr": "50800"},
                {"stck_bsop_date": "20260518", "stck_hgpr": "65000", "stck_lwpr": "50000", "stck_oprc": "50000", "stck_clpr": "64000"},  # +28%
                {"stck_bsop_date": "20260517", "stck_hgpr": "52000", "stck_lwpr": "40000", "stck_oprc": "40000", "stck_clpr": "51000"},  # +27%
            ] + [
                {"stck_bsop_date": f"2026051{i:02d}", "stck_hgpr": "51000", "stck_lwpr": "49000", "stck_oprc": "50000", "stck_clpr": "50500"}
                for i in range(15, 25)
            ]
        # 정상 종목
        return [
            {"stck_bsop_date": today, "stck_hgpr": "51000", "stck_lwpr": "50000", "stck_oprc": "50500", "stck_clpr": "50800"},
            {"stck_bsop_date": "20260518", "stck_hgpr": "51000", "stck_lwpr": "49000", "stck_oprc": "50000", "stck_clpr": "50500"},
        ] + [
            {"stck_bsop_date": f"2026051{i:02d}", "stck_hgpr": "51000", "stck_lwpr": "49000", "stck_oprc": "50000", "stck_clpr": "50500"}
            for i in range(15, 25)
        ]

    async def fake_write_log(*args, **kwargs):
        return None

    with patch("src.api.base.kis_get", side_effect=fake_kis_get), \
         patch("src.api.condition.fetch_daily_candles", side_effect=fake_fetch_daily_candles), \
         patch("src.db.system_logs.write_log", side_effect=fake_write_log):
        await ltv.prepare()

    stats = ltv.get_scan_stats()

    assert stats["universe_candidates"] == 2
    assert stats["mcap_pass"] == 2
    assert stats["trade_amount_pass"] == 2
    assert stats["universe_filtered"] == 2
    # 일봉 fetch 는 둘 다 성공
    assert stats["candle_fetch_ok"] == 2
    # 연속상한가 통과는 111111 만 (= 1)
    assert stats["consecutive_limit_pass"] == 1
    # K값 계산 + 최종 prepared = 1
    assert stats["k_value_computed"] == 1
    assert stats["final_prepared"] == 1
    assert stats["last_run_at"] is not None


# ---------------------------------------------------------------------------
# 3. get_scan_stats() — 사본 반환
# ---------------------------------------------------------------------------
def test_get_scan_stats_returns_isolated_copy(ltv):
    """`get_scan_stats()` 가 사본 반환 (외부 수정 격리)."""
    ltv._scan_stats = {
        "universe_candidates": 8,
        "universe_filtered": 4,
        "price_filtered": 7,
        "mcap_pass": 6,
        "trade_amount_pass": 5,
        "candle_fetch_ok": 4,
        "consecutive_limit_pass": 3,
        "k_value_computed": 3,
        "final_prepared": 3,
        "last_run_at": "2026-05-20T08:00:00+09:00",
    }

    snapshot = ltv.get_scan_stats()
    snapshot["universe_candidates"] = 999
    assert ltv._scan_stats["universe_candidates"] == 8
    assert ltv.get_scan_stats()["universe_candidates"] == 8
