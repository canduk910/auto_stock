"""사이클 21 — VolatilityBreakout `_scan_stats` 회귀 가드.

donchian_swing 의 `_empty_scan_stats()` + `_scan_stats` 누적 + `get_scan_stats()`
패턴을 VB 에 동일 적용한다. 운영자가 ScanMonitor 깔때기로 "왜 신호 0건인지"
단계별 추적 가능.

Red 단계 (사이클 21):
- `_empty_scan_stats()` 함수 부재 → ImportError
- `VolatilityBreakoutStrategy._scan_stats` 속성 부재 → AttributeError
- `get_scan_stats()` 메서드 부재 → AttributeError
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit


@pytest.fixture
def vb(monkeypatch):
    """scanner 격리한 VB 인스턴스."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    return VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="변동성 돌파", weight=0.3)
    )


# ---------------------------------------------------------------------------
# 1. _empty_scan_stats() — 9 키 dict 반환 + 초기값
# ---------------------------------------------------------------------------
def test_empty_scan_stats_has_nine_keys_and_zero_defaults():
    """`_empty_scan_stats()` 가 9 키 (8 카운트 + last_run_at) dict 를 0/None 으로 초기화한다."""
    from src.engine.strategies.volatility_breakout import _empty_scan_stats

    stats = _empty_scan_stats()

    expected_keys = {
        "universe_candidates",
        "universe_filtered",
        "price_filtered",
        "mcap_pass",
        "trade_amount_pass",
        "candle_fetch_ok",
        "k_value_computed",
        "final_prepared",
        "last_run_at",
    }
    assert set(stats.keys()) == expected_keys
    # 카운트는 0, last_run_at 만 None
    for k, v in stats.items():
        if k == "last_run_at":
            assert v is None
        else:
            assert v == 0, f"키 {k} 초기값이 0이 아님: {v}"


# ---------------------------------------------------------------------------
# 2. prepare() — 단계 카운트 누적 검증 (fixture mock)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prepare_accumulates_counts_through_pipeline(vb, monkeypatch):
    """`_scan_universe()` 와 `fetch_daily_candles` 를 mock 으로 주입해
    각 단계 카운트가 올바르게 누적되는지 검증한다.

    시나리오 (4 종목):
    - "111111": rank_items 통과 + price/mcap/trade_amount 통과 + 일봉 OK + K값 계산 성공 → final_prepared
    - "222222": rank_items 통과 + 시총 미달 → mcap_pass 미증가
    - "333333": rank_items 통과 + 시총 OK / 거래대금 미달 → trade_amount_pass 미증가
    - "444444": rank_items 통과 + 모두 OK / 일봉 None → candle_fetch_ok 미증가
    """
    from src.engine.strategies import volatility_breakout as vb_mod

    # 모듈 컨스턴츠는 너무 큼 → 작게 조정
    vb.config.params["min_market_cap"] = 100_000_000_000  # 1000억
    vb.config.params["min_trade_amount"] = 20_000_000_000  # 200억

    # _scan_universe 를 우회하여 직접 카운터 검증 — _scan_universe 가 단계 카운트의 주역
    # 본 테스트는 prepare() 가 _scan_universe 호출 + 일봉 fetch 분기 + final_prepared 갱신
    # 모두 정합한지 확인하므로 _scan_universe 는 실제 동작 → kis_get 만 mock
    fake_rank_items = [
        # 통과 종목 (시총 5000억, 거래대금 500억)
        {
            "mksc_shrn_iscd": "111111",
            "hts_kor_isnm": "통과종목",
            "stck_prpr": "50000",
            "lstn_stcn": "10000000",  # 5000억
            "prdy_vol": "1000000",  # 거래대금 = 1M × 49000 ≈ 490억
            "prdy_vrss": "1000",
        },
        # 시총 미달 (시총 500억)
        {
            "mksc_shrn_iscd": "222222",
            "hts_kor_isnm": "시총미달",
            "stck_prpr": "5000",
            "lstn_stcn": "10000000",
            "prdy_vol": "10000000",
            "prdy_vrss": "100",
        },
        # 거래대금 미달 (시총 5000억, 거래대금 10억)
        {
            "mksc_shrn_iscd": "333333",
            "hts_kor_isnm": "거래대금미달",
            "stck_prpr": "50000",
            "lstn_stcn": "10000000",
            "prdy_vol": "20000",  # 20K × 49000 ≈ 9.8억
            "prdy_vrss": "1000",
        },
        # 일봉 None (시총 OK + 거래대금 OK)
        {
            "mksc_shrn_iscd": "444444",
            "hts_kor_isnm": "일봉없음",
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
        if ticker == "444444":
            raise RuntimeError("daily fetch fail")
        # candles[0] = 오늘 부분봉, candles[1] = 전일, candles[2:] = 전일 이전
        # K값 계산 위해 noise > 0 + prev_range > 0 필요
        from datetime import date
        today = date.today().strftime("%Y%m%d")
        return [
            {"stck_bsop_date": today, "stck_hgpr": "51000", "stck_lwpr": "50000", "stck_oprc": "50500", "stck_clpr": "50800"},
            # 전일
            {"stck_bsop_date": "20260518", "stck_hgpr": "51000", "stck_lwpr": "49000", "stck_oprc": "50000", "stck_clpr": "50500"},
        ] + [
            {"stck_bsop_date": f"2026051{i:02d}", "stck_hgpr": "51000", "stck_lwpr": "49000", "stck_oprc": "50000", "stck_clpr": "50500"}
            for i in range(15, 25)
        ]

    async def fake_write_log(*args, **kwargs):
        return None

    # kis_get / fetch_daily_candles / write_log 모두 lazy import → patch.object 사용
    with patch("src.api.base.kis_get", side_effect=fake_kis_get), \
         patch("src.api.condition.fetch_daily_candles", side_effect=fake_fetch_daily_candles), \
         patch("src.db.system_logs.write_log", side_effect=fake_write_log):
        await vb.prepare()

    stats = vb.get_scan_stats()

    # 4 종목 모두 BLNG 응답 후보 + dedupe → universe_candidates
    # kis_get 가 3 BLNG_CODES 호출되지만 seen_tickers dedupe → 4
    assert stats["universe_candidates"] == 4
    # 가격/listed/prdy_vol/prdy_close 모두 > 0 → price_filtered 4 (모두 통과)
    assert stats["price_filtered"] == 4
    # 시총 1000억 통과: 111111(5000억) + 333333(5000억) + 444444(5000억) = 3
    # (222222 는 5000×10M=500억 → 탈락)
    assert stats["mcap_pass"] == 3
    # 거래대금 200억 통과:
    # 111111: 1M × (50000-1000) = 490억 → OK
    # 222222: 10M × (5000-100) = 490억 → OK
    # 333333: 20K × (50000-1000) = 9.8억 → 탈락
    # 444444: 1M × (50000-1000) = 490억 → OK
    # → 3 종목 통과
    assert stats["trade_amount_pass"] == 3
    # universe_filtered = mcap+trade 동시 통과 = 2 (111111, 444444) — 222222 는 시총 미달
    assert stats["universe_filtered"] == 2
    # candle_fetch_ok = 111111 만 (444444 는 RuntimeError)
    # 222222 와 333333 은 filtered 에 안 들어가서 fetch 호출 안 됨
    assert stats["candle_fetch_ok"] == 1
    # k_value_computed = 111111 (전일 range > 0 + noise > 0)
    assert stats["k_value_computed"] == 1
    # final_prepared = _scanned_tickers 길이 == k_value_computed
    assert stats["final_prepared"] == 1
    # last_run_at 갱신됨
    assert stats["last_run_at"] is not None


# ---------------------------------------------------------------------------
# 3. get_scan_stats() — 사본 반환 (외부 수정 격리)
# ---------------------------------------------------------------------------
def test_get_scan_stats_returns_isolated_copy(vb):
    """`get_scan_stats()` 가 `_scan_stats` 의 사본을 반환하여 외부 수정으로부터 격리한다."""
    # 직접 _scan_stats 시드
    vb._scan_stats = {
        "universe_candidates": 10,
        "universe_filtered": 5,
        "price_filtered": 8,
        "mcap_pass": 6,
        "trade_amount_pass": 5,
        "candle_fetch_ok": 4,
        "k_value_computed": 3,
        "final_prepared": 3,
        "last_run_at": "2026-05-20T08:00:00+09:00",
    }

    snapshot1 = vb.get_scan_stats()
    snapshot2 = vb.get_scan_stats()

    # 사본이므로 별도 객체
    assert snapshot1 is not snapshot2
    # 값은 동일
    assert snapshot1 == snapshot2

    # 외부에서 수정해도 원본 _scan_stats 영향 없음
    snapshot1["universe_candidates"] = 999
    assert vb._scan_stats["universe_candidates"] == 10
    # get_scan_stats() 새 호출은 여전히 원본
    assert vb.get_scan_stats()["universe_candidates"] == 10
