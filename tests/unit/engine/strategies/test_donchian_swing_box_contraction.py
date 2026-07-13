"""사이클 23 P2-4 → 사이클 208 의미 전환 — donchian 박스 수축 보조 필터 *제거*.

사이클 208 (2026-07-13, 사이클 66 K-2 패턴): 박스 수축 필터가 추세 상승 종목
(신고가 = 박스 넓음)을 상시 탈락시켜 최종 후보 상시 0 → domain 자문 채택하여
필터 완전 제거 (`_workspace/domain_consult/cycle_donchian_box_contraction.md`).

기존 "박스 변동성 3% 통과 / 7% skip / box_contraction_pass 증가" 계약을
"필터 제거됨 (넓은 박스도 통과 / box_contraction_pass 키 부재)" 로 갱신.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


def _make_strat(box_period: int = 10, max_box_vol: float = 5.0):
    strat = DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.0)
    )
    strat.config.params["box_contraction_period"] = box_period
    strat.config.params["max_box_volatility_pct"] = max_box_vol
    return strat


def _make_candles(n=70, base_price=10_000, vol_pct=0.03, high_breakout=True):
    """n일치 가짜 일봉 생성.

    vol_pct: (high - low) / close 비율 — 박스 변동성 제어.
    최신순(idx=0이 가장 최근).

    high_breakout=True: candles[0] (가장 최근일, 전일) 의 종가가
    candles[1:21] 최고가 max 를 초과하도록 설정 → donchian 필터 통과.
    """
    from datetime import date, timedelta as td
    today = datetime(2026, 5, 20).date()
    candles = []
    for i in range(n):
        d = today - td(days=i + 1)
        if high_breakout and i == 0:
            # 가장 최근일: donchian 돌파 신고가 (나머지보다 10% 높게)
            close = int(base_price * 1.10)
            high = int(close * (1 + vol_pct / 2))
            low = int(close * (1 - vol_pct / 2))
        else:
            close = base_price
            high = int(close * (1 + vol_pct / 2))
            low = int(close * (1 - vol_pct / 2))
        candles.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_hgpr": str(high),
            "stck_lwpr": str(low),
            "stck_oprc": str(close),
            "acml_vol": "1000000",
        })
    return candles


def test_empty_scan_stats_no_box_contraction_pass():
    """사이클 208 의미 전환 — _empty_scan_stats() 에 box_contraction_pass 키 부재.

    (기존: 키 기본 0 존재 단언 → 제거 후 부재 단언)
    """
    from src.engine.strategies.donchian_swing import _empty_scan_stats
    stats = _empty_scan_stats()
    assert "box_contraction_pass" not in stats


def _make_donchian_passing_candles(n=70, base_price=10_000, vol_pct=0.03):
    """donchian prepare() 의 1~4 필터를 모두 통과하는 일봉 데이터 생성.

    donchian prepare() 필터:
    1) donchian: closes[0] > max(highs[1:donchian_period+1])
    2) EMA 우상향: ema_today > ema_yesterday AND closes[0] > ema_today
    3) 거래량: today_turnover > avg_turnover × volume_mult(1.5)
    4) ATR: positive

    최신순(idx=0 = 가장 최근) 반환.
    """
    from datetime import date, timedelta as td

    today = datetime(2026, 5, 20).date()
    candles = []

    for i in range(n):
        d = today - td(days=i + 1)
        if i == 0:
            # 가장 최근일(전일): 20일 신고가 초과 → donchian 통과
            # 나머지(1~69)는 base_price, 이 날은 base_price × 1.25
            close = int(base_price * 1.25)
            # 거래량도 높게 → 거래량 필터 통과
            acml_vol = "3000000"
        else:
            # 오래된 날수록 약간 낮게 → EMA 우상향 보장
            close = int(base_price * (1 + 0.001 * (n - i)))
            acml_vol = "1000000"
        high = int(close * (1 + vol_pct / 2))
        low = int(close * (1 - vol_pct / 2))
        candles.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_hgpr": str(high),
            "stck_lwpr": str(low),
            "stck_oprc": str(close),
            "acml_vol": acml_vol,
        })
    return candles


async def _run_prepare(strat, candles, tickers):
    """사이클 173 이후 일봉 source = get_recent_daily_normalized (DB 우선 어댑터).

    _scan_universe / master_block / 어댑터 를 mock 하고 prepare 실행.
    """
    async def fake_scan_universe():
        strat._scan_stats["universe_candidates"] = len(tickers)
        strat._scan_stats["universe_filtered"] = len(tickers)
        strat._scan_stage_counts = {
            "union_tickers": list(tickers),
            "mcap_tickers": list(tickers),
            "trade_tickers": list(tickers),
        }
        return list(tickers)

    import src.engine.scanner as scanner_mod
    with patch.object(strat, "_scan_universe", new=fake_scan_universe), \
            patch.object(
                strat, "_apply_master_block_filter_in_prepare",
                new=AsyncMock(return_value=(list(tickers), [])),
            ), \
            patch(
                "src.db.stock_master_daily.get_recent_daily_normalized",
                new=AsyncMock(return_value=candles),
            ), \
            patch("src.db.system_logs.write_log", new=AsyncMock()), \
            patch.object(scanner_mod, "ticker_prev_close", {}):
        await strat.prepare()


@pytest.mark.asyncio
async def test_low_volatility_box_still_prepared():
    """사이클 208 의미 전환 — 박스 변동성 3% 종목은 여전히 최종 후보에 포함.

    (기존: box_contraction_pass 증가 단언 → 필터 제거로 그 카운터 자체 부재.
    저변동성 종목도 정상 확정됨을 재확인.)
    """
    strat = _make_strat(box_period=10, max_box_vol=5.0)
    candles_low_vol = _make_donchian_passing_candles(n=70, base_price=10_000, vol_pct=0.03)

    await _run_prepare(strat, candles_low_vol, ["005930"])

    assert "005930" in strat._candidates
    assert "box_contraction_pass" not in strat._scan_stats


@pytest.mark.asyncio
async def test_high_volatility_wide_box_now_prepared():
    """사이클 208 의미 전환 — 박스 변동성 7%(넓은 박스) 종목도 이제 최종 후보에 포함.

    (기존: box_contraction_pass=0 + final_prepared=0 skip 단언 →
    필터 제거로 넓은 박스 추세 상승 종목도 확정 = 추세추종 정합.)
    """
    strat = _make_strat(box_period=10, max_box_vol=5.0)
    candles_high_vol = _make_donchian_passing_candles(n=70, base_price=10_000, vol_pct=0.07)

    await _run_prepare(strat, candles_high_vol, ["005930"])

    assert "005930" in strat._candidates, (
        "넓은 박스 종목도 최종 후보 포함 (박스 수축 필터 제거 후)"
    )
    assert strat._scan_stats["final_prepared"] >= 1
    assert "box_contraction_pass" not in strat._scan_stats
