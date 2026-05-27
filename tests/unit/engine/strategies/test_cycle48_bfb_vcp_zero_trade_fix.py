"""사이클 48 (2026-05-27) — BFB/VCP 0건 매매 결함 전면 시정 (운영 DB 확정).

운영 DB 사실: 6개 전략 중 bull_flag_breakout(BFB) / vcp_breakout(VCP) 가 배포(5/18)
이후 단 한 건도 매매하지 못함 (BUY 0/SELL 0, strategy_funnel 매일 signals:0).

결함 + 시정 (도메인 자문 결론):
- BFB-1 유니버스: `_fetch_fluctuation_rank` + `fetch_stock_detail`(acml_vol) → 07:50 장 전
  boot 에서 acml_vol=0 → 매일 "유니버스 0종목". 시정: VB/LTV 처럼 volume-rank
  (FHPST01710000) prdy_vol 기반으로 시간무관화.
- BFB-2 Pole: pole_min_return 20→15, pole_max_red_ratio 0.30→0.45.
- VCP 추세필터: ema_long 200→120 / ema_mid 150→60 (KIS 100일 한도 내 계산 가능),
  last_pullback_max 0.08→0.12.
- 보조: scheduler._reprepare_breakout_if_empty 에 BFB/VCP 추가.

회귀 가드:
- BFB/VCP 가 "신호 평가 단계까지 도달 가능" (실제 후보 산출 fixture).
- 매수 진입 임계만 완화. 매도/손절/청산 로직 무수정.
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ===========================================================================
# BFB-1: 유니버스 시간무관화 — volume-rank(prdy_vol) 기반
# ===========================================================================
def _volume_rank_item(ticker: str, name: str, price: int, listed: int,
                       prdy_vol: int, prdy_vrss: int = 0) -> dict:
    """KIS volume-rank(FHPST01710000) output 단일 항목 모사.

    VB `_scan_universe` 가 쓰는 정본 키: mksc_shrn_iscd / hts_kor_isnm /
    stck_prpr / lstn_stcn / prdy_vol / prdy_vrss.
    """
    return {
        "mksc_shrn_iscd": ticker,
        "hts_kor_isnm": name,
        "stck_prpr": str(price),
        "lstn_stcn": str(listed),
        "prdy_vol": str(prdy_vol),
        "prdy_vrss": str(prdy_vrss),
    }


@pytest.mark.asyncio
async def test_bfb_scan_universe_uses_prdy_volume_rank_api(monkeypatch):
    """BFB `_scan_universe` 가 volume-rank API + prdy_vol 기반으로 시간무관 동작.

    07:50 장 전 boot 에서도 acml_vol(당일 누적=0) 의존 없이 후보 산출.
    """
    from src.engine.strategies import bull_flag_breakout as bfb_mod
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    captured_tr_ids: list[str] = []

    async def _fake_kis_get(path, tr_id, params):
        captured_tr_ids.append(tr_id)
        # 삼성전자: 65000 × 5M(전일거래량) = 3,250억 거래대금 >> 20억 통과
        # prdy_vrss=1000 → prdy_close = 65000 - 1000 = 64000 → trade_amt = 5M × 64000 = 3,200억
        return {
            "output": [
                _volume_rank_item("005930", "삼성전자", 65000, 5_969_782_550,
                                  prdy_vol=5_000_000, prdy_vrss=1000),
            ]
        }

    monkeypatch.setattr(bfb_mod, "kis_get", _fake_kis_get, raising=False)
    # 백엔드 구현이 src.api.base.kis_get 을 import 하는 경우 대비
    from src.api import base as base_mod
    monkeypatch.setattr(base_mod, "kis_get", _fake_kis_get, raising=False)

    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_names", {})

    strat = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목 돌파", weight=0.0)
    )

    result = await strat._scan_universe()

    # 시간무관 — volume-rank(FHPST01710000) 사용
    assert "FHPST01710000" in captured_tr_ids, (
        f"BFB 가 volume-rank(FHPST01710000) 시간무관 API 사용 필요. 호출된 tr_id={captured_tr_ids}"
    )
    assert "005930" in result, (
        f"prdy_vol 기반 거래대금 산출로 장 전에도 후보 통과 필요. 실제={result}"
    )


@pytest.mark.asyncio
async def test_bfb_scan_universe_filters_low_prdy_trade_amount(monkeypatch):
    """전일 거래대금 미달 종목은 정상 탈락 (prdy 기준)."""
    from src.engine.strategies import bull_flag_breakout as bfb_mod
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    async def _fake_kis_get(path, tr_id, params):
        return {
            "output": [
                # 빈약: 1000 × 100(전일거래량) = 10만원 << 20억 → 탈락
                _volume_rank_item("100001", "빈약", 1000, 100_000_000,
                                  prdy_vol=100, prdy_vrss=0),
                # 정상: 65000 × 5M = 3,250억 → 통과
                _volume_rank_item("100002", "정상", 65000, 5_000_000_000,
                                  prdy_vol=5_000_000, prdy_vrss=0),
            ]
        }

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


# ===========================================================================
# BFB-2: Pole 임계 완화 (DEFAULT_PARAMS)
# ===========================================================================
def test_bfb_pole_thresholds_relaxed():
    """BFB Pole 임계 완화 — pole_min_return 15.0 / pole_max_red_ratio 0.45."""
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy

    p = BullFlagBreakoutStrategy.DEFAULT_PARAMS
    assert p["pole_min_return"] == 15.0, (
        f"Pole 누적 상승률 임계 20.0→15.0 완화 필요. 실제={p['pole_min_return']}"
    )
    assert p["pole_max_red_ratio"] == 0.45, (
        f"Pole 음봉 비율 임계 0.30→0.45 완화 필요. 실제={p['pole_max_red_ratio']}"
    )


def test_bfb_detect_pole_passes_realistic_korean_setup():
    """현실적 한국 깃대상승 셋업(+16%, 음봉 40%)이 Pole 검출 통과.

    기존 +20% / 음봉 30% 에선 0 이던 케이스가 완화 임계로 통과 → 신호 평가 도달.
    """
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    strat = BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목 돌파", weight=0.0)
    )

    # candles[0] = 최근(어제), 인덱스 클수록 과거.
    # 구성: flag 5일(횡보·완만 조정·거래량 수축) + pole 5일(+16% 상승, 음봉 2개=40%)
    # pole 구간(과거): 시작가 10000 → 고가 11600 (+16%)
    candles: list[dict] = []

    # flag 구간 (최신 5일, idx 0~4) — 얕은 조정(폴 폭의 38.2% 이내) + 거래량 수축.
    # pole_high=11600, pole_width=1600 → flag_low ≥ 11600 - 0.382×1600 ≈ 10989 필요.
    flag_prices = [11200, 11150, 11100, 11250, 11300]
    for i, px in enumerate(flag_prices):
        candles.append({
            "stck_clpr": str(px),
            "stck_hgpr": str(px + 50),
            "stck_lwpr": str(px - 50),
            "stck_oprc": str(px - 20),
            "acml_vol": "300000",  # 수축된 거래량
        })

    # pole 구간 (과거 5일, idx 5~9) — +16% 상승, 음봉 2개(40%)
    # 시간 흐름: idx9(가장 옛날) 10000 → idx5(폴 끝) 11500, 고가 11600
    # candles 는 최신순이므로 idx9=oldest. pole_start=pole_slice_closes[-1]=10000
    pole_data = [
        # (close, high, low, open)  idx5 ~ idx9 (최신→과거)
        (11500, 11600, 11400, 11300),  # idx5 양봉
        (11300, 11400, 11000, 11400),  # idx6 음봉 (close<open)
        (11100, 11200, 10800, 10800),  # idx7 양봉
        (10700, 10900, 10600, 10900),  # idx8 음봉 (close<open)
        (10000, 10100, 9900, 9800),    # idx9 양봉 (oldest, pole_start=10000)
    ]
    for close, high, low, opn in pole_data:
        candles.append({
            "stck_clpr": str(close),
            "stck_hgpr": str(high),
            "stck_lwpr": str(low),
            "stck_oprc": str(opn),
            "acml_vol": "1000000",  # 폴 구간 큰 거래량
        })

    result = strat._detect_pole_and_flag(candles)

    assert result is not None, (
        "완화 임계(+15% / 음봉 45%)로 현실적 한국 깃대상승 셋업이 Pole/Flag 검출 통과해야 함. "
        "기존 +20% / 음봉 30% 에선 음봉 40% > 30% 로 탈락."
    )
    # 폴 강도 확인
    pole_return = (result["pole_high"] - result["pole_start"]) / result["pole_start"] * 100
    assert pole_return >= 15.0


# ===========================================================================
# VCP: 추세필터 임계 (DEFAULT_PARAMS) + 신호 평가 도달
# ===========================================================================
def test_vcp_ema_thresholds_within_kis_limit():
    """VCP EMA 임계가 KIS 100일 한도 내 계산 가능 — ema_long 120 / ema_mid 60."""
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    p = VcpBreakoutStrategy.DEFAULT_PARAMS
    assert p["ema_long"] == 120, (
        f"ema_long 200→120 (KIS 100일 한도 계산 가능) 필요. 실제={p['ema_long']}"
    )
    assert p["ema_mid"] == 60, (
        f"ema_mid 150→60 필요. 실제={p['ema_mid']}"
    )
    assert p["last_pullback_max"] == 0.12, (
        f"last_pullback_max 0.08→0.12 완화 필요. 실제={p['last_pullback_max']}"
    )


@pytest.mark.asyncio
async def test_vcp_trend_filter_reaches_base_detection_within_100_days(monkeypatch):
    """VCP 추세필터가 100일 데이터 + 120/60 EMA 로 통과 → 베이스 검출 단계 도달.

    기존 200/150 EMA 는 100일 한도로 effective ~75 축소 + ema_mid 재축소 →
    추세필터 항상 0. 시정 후 trend_filter_pass >= 1 (신호 평가 도달 입증).
    """
    from src.engine.strategies import vcp_breakout as vcp_mod
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig

    async def _fake_scan():
        return ["005930"]

    # 100일 우상향 추세 일봉 (오늘 제외, 어제부터 과거). 완만한 우상향.
    today = date.today()
    candles: list[dict] = []
    for i in range(100):
        d = today - timedelta(days=i + 1)
        # i=0 어제(최신), i=99 가장 과거. 우상향: 과거 낮고 최근 높음.
        price = 50000 + (100 - i) * 80  # 어제 ≈ 57920, 과거 ≈ 50080
        candles.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": str(price),
            "stck_hgpr": str(price + 300),
            "stck_lwpr": str(price - 300),
            "stck_oprc": str(price),
            "acml_vol": "1000000",
        })

    async def _fake_fetch(ticker, days):
        return candles[: min(days, 100)]

    from src.api import condition as cond_mod
    monkeypatch.setattr(cond_mod, "fetch_daily_candles", _fake_fetch)
    monkeypatch.setattr(vcp_mod, "fetch_daily_candles", _fake_fetch, raising=False)

    strat = VcpBreakoutStrategy(
        StrategyConfig(strategy_id="vcp_breakout", name="VCP 변동성 수축", weight=0.0)
    )
    strat._scan_universe = _fake_scan  # type: ignore[assignment]

    await strat.prepare()

    assert strat._scan_stats["candle_fetch_ok"] >= 1, (
        f"100일 fetch 정상. _scan_stats={strat._scan_stats}"
    )
    assert strat._scan_stats["trend_filter_pass"] >= 1, (
        f"120/60 EMA 정렬 + 우상향으로 추세필터 통과해야 함 (기존 200/150 은 항상 0). "
        f"_scan_stats={strat._scan_stats}"
    )


# ===========================================================================
# 보조 안전망: scheduler 장중 재prepare 대상에 BFB/VCP 추가
# ===========================================================================
def test_reprepare_breakout_includes_bfb_vcp():
    """`_reprepare_breakout_if_empty` 가 BFB/VCP 도 장중 재prepare 대상에 포함.

    boot 실패/일시 API 오류 회복용 안전망 (주 메커니즘은 prdy 유니버스).
    """
    from src.engine import scheduler as sched_mod

    src = inspect.getsource(sched_mod.TradingScheduler._reprepare_breakout_if_empty)
    assert "bull_flag_breakout" in src, (
        "BFB 가 장중 재prepare 대상에 포함 필요"
    )
    assert "vcp_breakout" in src, (
        "VCP 가 장중 재prepare 대상에 포함 필요"
    )
