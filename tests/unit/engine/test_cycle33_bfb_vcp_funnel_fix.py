"""사이클 33 (2026-05-21) — 3 전략 funnel 결함 시정 (BFB + VCP).

Phase 2 진단 결과:
- H-2 (BFB): `_scan_universe` 가 `fetch_stock_detail` (FHKST01010100) 응답에서
  `prdy_vol` 필드 추출 — KIS 응답에 해당 필드 없음 (`acml_vol`, `prdy_vrss_vol_rate` 만 있음).
  → trade_amt 항상 0 → 30→0 단일 단계 탈락. 사용자 5/21 보고 사고 원인.
- H-3 (VCP): `prepare` 가 `fetch_days=285` 일봉 요청 (ema_long=200 + base_max=75 + 10).
  KIS `fetch_daily_candles` (FHKST03010100) **단일 호출 최대 100일** 한도 → 100일만 반환.
  `len(candles) <= prev_idx + ema_long + 5 = 205` 항상 True → 113→0 사고 원인.

본 사이클 (33) 변경:
- BFB: `prdy_vol` → `acml_vol` (당일 누적거래량, 응답 존재 필드). 5/21 정상 동작 검증.
- VCP: `ema_long=200` 유지하되 `fetch_days` 를 KIS 100일 한도 내로 축소 또는
  multi-call 분할 fetch. **100일 한도 + ema_long=200 양립 불가** 이므로 다음 옵션 평가:
  - 옵션 A: ema_long 을 70 으로 축소 (200 → 70). 미네르비니식 의도 (200EMA) 변경 → 매매 안전성 영향.
  - 옵션 B: `fetch_daily_candles` 가 multi-call 자동 분할 (예: 2회 호출 → 200일). 인프라 변경.
  - 옵션 C: `fetch_days=95` 로 한도 내 축소 + 가용 EMA 길이로 trend filter 동작.
  → **본 사이클 권고 옵션 C** (인프라 변경 0, 미네르비니식 의도는 일부 양보). 사용자 확인 후 옵션 B 로 전환 가능.

회귀 가드:
- 5/21 funnel 카운터 재현 후 시정 검증
- BFB acml_vol 으로 trade_amt 계산 + 정상 30→N (N≥5 예상)
- VCP fetch_days ≤ 100 + candles 길이 충분 → 추세필터 진입
- 다른 전략 (donchian/VB/LTV/momentum) prepare 회귀 0
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

_xfail_cycle108 = pytest.mark.xfail(
    strict=False,
    reason="사이클 108 stock_master 전환으로 BFB volume-rank 호출 패턴 폐기 — "
           "과거 계약 영속 보존 (사이클 97 K-2 패턴 답습)",
)


# ===========================================================================
# B-1 (H-2 → 사이클 48 갱신): BFB `_scan_universe` — prdy 기반 volume-rank 사용
#
# 사이클 33 은 acml_vol(당일 누적) 을 썼으나, 07:50 장 전 boot 에서 acml_vol=0 →
# 매일 "유니버스 0종목" 결함 (운영 DB 확정). 사이클 48 (2026-05-27) 에서 VB/LTV 와
# 동일하게 volume-rank(FHPST01710000) prdy_vol 기반으로 시간무관화. 본 테스트도 갱신.
# 사이클 108: stock_master 전환으로 volume-rank 패턴 폐기 → xfail 의미 전환.
# ===========================================================================
def _vrank_item(ticker, name, price, listed, prdy_vol, prdy_vrss=0):
    return {
        "mksc_shrn_iscd": ticker,
        "hts_kor_isnm": name,
        "stck_prpr": str(price),
        "lstn_stcn": str(listed),
        "prdy_vol": str(prdy_vol),
        "prdy_vrss": str(prdy_vrss),
    }


@_xfail_cycle108
@pytest.mark.asyncio
async def test_bfb_scan_universe_uses_prdy_volume_rank(monkeypatch):
    """BFB `_scan_universe` 가 prdy_vol 기반 volume-rank 사용 — 장 전에도 시간무관 동작."""
    from src.engine.strategies import bull_flag_breakout as bfb_mod
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy

    async def _fake_kis_get(path, tr_id, params):
        # 삼성전자: 65000 × 5M(전일거래량) ≈ 325억 거래대금 >> 20억 통과
        return {"output": [_vrank_item("005930", "삼성전자", 65000, 5_969_782_550,
                                        prdy_vol=5_000_000, prdy_vrss=0)]}

    monkeypatch.setattr(bfb_mod, "kis_get", _fake_kis_get, raising=False)
    from src.api import base as base_mod
    monkeypatch.setattr(base_mod, "kis_get", _fake_kis_get, raising=False)
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_names", {})

    strat = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목 돌파", weight=0.0)
    )
    result = await strat._scan_universe()

    assert "005930" in result, (
        f"prdy_vol 기반 거래대금 산출로 장 전에도 통과 필요. 실제={result}"
    )


@_xfail_cycle108
@pytest.mark.asyncio
async def test_bfb_scan_universe_filters_low_trade_amount(monkeypatch):
    """거래대금 미달 종목은 정상 탈락 (min_trade_amount_failed 카운트, prdy 기준)."""
    from src.engine.strategies import bull_flag_breakout as bfb_mod
    from src.engine.strategy_base import StrategyConfig
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy

    async def _fake_kis_get(path, tr_id, params):
        return {"output": [
            # 빈약: 1000 × 100(전일거래량) = 10만원 << 20억 → 탈락
            _vrank_item("100001", "빈약", 1000, 100_000_000, prdy_vol=100, prdy_vrss=0),
            # 정상: 65000 × 5M = 325억 > 20억 통과
            _vrank_item("100002", "정상", 65000, 5_000_000_000, prdy_vol=5_000_000, prdy_vrss=0),
        ]}

    monkeypatch.setattr(bfb_mod, "kis_get", _fake_kis_get, raising=False)
    from src.api import base as base_mod
    monkeypatch.setattr(base_mod, "kis_get", _fake_kis_get, raising=False)
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_names", {})

    strat = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목 돌파", weight=0.0)
    )
    result = await strat._scan_universe()

    assert "100001" not in result
    assert "100002" in result
    assert strat._scan_stats["min_trade_amount_failed"] >= 1


# ===========================================================================
# V-1 (H-3): VCP `prepare` — fetch_days 100일 한도 내 + len 가드 일관
# ===========================================================================
def test_vcp_fetch_days_within_kis_100_limit():
    """VCP `prepare` 의 `fetch_days` 가 KIS `fetch_daily_candles` 100일 한도 이내.

    KIS FHKST01010100 단일 호출 최대 100일 (src/api/CLAUDE.md 명시).
    `fetch_days = ema_long + base_max + 10 = 200 + 75 + 10 = 285` 시
    실제 응답 100일만 → len(candles) <= prev_idx + ema_long + 5 = 205 항상 True → 모두 탈락.

    시정: ema_long 을 KIS 한도 내로 조정하거나 fetch_days 축소.
    """
    import inspect
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    src = inspect.getsource(VcpBreakoutStrategy.prepare)
    # fetch_days 계산식이 KIS 100일 한도 인식 — 명시적 cap 또는 ema_long 축소
    # 실제 검증은 prepare 실행으로 (아래 테스트 참조)
    # 본 테스트는 코드에 KIS 한도 인식 가드 존재 여부만 검증
    assert ("min(" in src and "100" in src) or "kis_max" in src.lower(), (
        f"VCP prepare 가 KIS 100일 한도 인식 가드 부재. fetch_days 무한 증가 위험."
    )


@pytest.mark.asyncio
async def test_vcp_prepare_handles_kis_100_day_limit(monkeypatch):
    """VCP prepare 가 KIS 100일 한도 가정 mock 응답에서도 정상 동작 (113→N≥0).

    5/21 운영 시점 113→0 결함 재현 + 시정 검증.
    """
    from src.engine.strategies import vcp_breakout as vcp_mod
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    # universe scan mock — 1개 종목만
    async def _fake_scan():
        return ["005930"]

    # KIS fetch_daily_candles mock — 100일만 반환 (실제 한도 시뮬레이션)
    # 추세필터 통과하도록 EMA 정렬 + 우상향 합성
    from datetime import date, timedelta
    today = date.today()
    candles = []
    base_price = 60000
    for i in range(100):
        d = today - timedelta(days=i + 1)  # 오늘 제외, 어제부터 100일 (시뮬)
        # 가격 우상향 추세 — 100일 전 50000 → 어제 60000
        price = 50000 + (100 - i) * 100
        candles.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": str(price),
            "stck_hgpr": str(price + 500),
            "stck_lwpr": str(price - 500),
            "stck_oprc": str(price),
            "acml_vol": "1000000",
        })

    async def _fake_fetch(ticker, days):
        # 요청 days 가 100 초과 시에도 100 만 반환 (KIS 실제 동작)
        actual_days = min(days, 100)
        return candles[:actual_days]

    from src.api import condition as cond_mod
    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch)
    monkeypatch.setattr(vcp_mod, "fetch_daily_candles", _fake_fetch, raising=False)

    # config 더블
    fake_config = MagicMock()
    fake_config.strategy_id = "vcp_breakout"
    fake_config.params = {
        "ema_short": 50,
        "ema_mid": 150,
        "ema_long": 200,
        "long_ema_uptrend_days": 20,
        "base_min_days": 25,
        "base_max_days": 75,
        "base_max_depth": 0.25,
        "base_depth_pct": 0.30,  # 사이클 41 — VCP DEFAULT_PARAMS 정합
        "pullback_min": 2,
        "pullback_max": 4,
        "pullback_count_min": 2,  # 사이클 41 — VCP DEFAULT_PARAMS 정합
        "pullback_count_max": 4,
        "last_pullback_max": 0.08,
        "volume_contraction_ratio": 0.70,
        "breakout_volume_mult": 1.5,
        "min_market_cap": 100_000_000_000,
        "min_trade_amount": 1_000_000_000,  # 2026-08-08 확대 — step1 라벨 f-string 참조 (__new__ 우회라 DEFAULT 병합 없음)
        "atr_period": 14,
        "tradable_boards": ["main"],
        "exchange": "KRX",
    }
    fake_config.enabled = True
    fake_config.weight = 0.1

    strat = VcpBreakoutStrategy.__new__(VcpBreakoutStrategy)
    strat.config = fake_config
    strat._candidates = {}
    strat._scanned_tickers = []
    strat._bought_today = set()
    strat._cooldown_until = {}
    # _scan_universe 우회
    strat._scan_universe = _fake_scan

    # 결함 재현 검증 — 적용 *전* 에는 candle_fetch_ok=0 (모두 길이 부족)
    # 적용 *후* 에는 fetch_days ≤ 100 + len 가드 일관 → candle_fetch_ok >= 1
    await strat.prepare()

    # 핵심 검증: candle_fetch_ok 가 0 이 아님 (113→0 결함 해소)
    assert strat._scan_stats["candle_fetch_ok"] >= 1, (
        f"VCP prepare 100일 한도 가정 시 candle_fetch_ok=0 결함 재현. "
        f"_scan_stats={strat._scan_stats}. fetch_days 한도 내 조정 + len 가드 일관 필요."
    )
