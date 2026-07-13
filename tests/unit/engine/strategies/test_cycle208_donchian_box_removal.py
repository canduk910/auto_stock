"""사이클 208 Red — donchian_swing 박스 수축 보조 필터 완전 제거.

> 자문: `_workspace/domain_consult/cycle_donchian_box_contraction.md`
> Red 작성 = tdd-engineer / Green(삭제 구현) = backend-dev.

donchian = "20일 신고가 돌파" 추세추종. ATR 통과 후 유일 게이트인 박스 수축 필터
(`max_box_volatility_pct` ≤3.2% DB / 5.0 코드 default)가 "돌파 전 초압축 횡보"를 요구
→ 추세 상승 종목(신고가 = 박스 넓음)을 상시 탈락 → 최종 후보 상시 0.
domain 결론 = 필터 완전 제거 (페이크 방어는 청산 규칙 담당, VCP/BFB 와 역할 중복).

Red 유효성 (production 미변경): 6 FAIL (G-208-1~6) / 4 PASS (INV-1~4 불변식).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 합성 candles — donchian 1~4 필터 (신고가/EMA/거래대금/ATR) 통과.
# vol_pct 로 박스 폭 제어 (넓은 박스 = 박스 수축 필터라면 탈락 대상).
# ---------------------------------------------------------------------------
def _make_donchian_passing_candles(
    n: int = 70, base_price: int = 10_000, vol_pct: float = 0.03
) -> list[dict]:
    """donchian prepare() 의 1~4 필터를 모두 통과하는 일봉 데이터.

    필터:
      1) donchian: closes[0] > max(highs[1:donchian_period+1])
      2) EMA 우상향: ema_today > ema_yesterday AND closes[0] > ema_today
      3) 거래대금: today_turnover > avg_turnover × volume_mult(1.5)
      4) ATR: positive

    vol_pct: (high - low) / close 비율 — 박스 폭 제어.
      0.07 = 박스 폭 ~7% (박스 수축 필터 임계 5% 초과 → 예전이면 탈락).
    최신순(idx=0 = 가장 최근 = 전일) 반환.
    """
    today = datetime(2026, 5, 20).date()
    candles: list[dict] = []
    for i in range(n):
        d = today - timedelta(days=i + 1)
        if i == 0:
            # 가장 최근일(전일): 20일 신고가 초과 + 거래량 급증
            close = int(base_price * 1.25)
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


def _make_strat() -> DonchianSwingStrategy:
    return DonchianSwingStrategy(
        StrategyConfig(strategy_id="donchian_swing", name="도치안", weight=0.0)
    )


async def _run_prepare_with_candles(
    strat: DonchianSwingStrategy, candles: list[dict], tickers: list[str] | None = None
) -> None:
    """_scan_universe / master_block / DB 어댑터를 mock 하고 prepare 실행.

    사이클 173 이후 일봉 source = get_recent_daily_normalized (DB 우선 어댑터).
    """
    tickers = tickers or ["005930"]

    async def fake_scan_universe():
        strat._scan_stats["universe_candidates"] = len(tickers)
        strat._scan_stats["universe_filtered"] = len(tickers)
        strat._scan_stage_counts = {
            "union_tickers": list(tickers),
            "mcap_tickers": list(tickers),
            "trade_tickers": list(tickers),
        }
        return list(tickers)

    with patch.object(strat, "_scan_universe", new=fake_scan_universe), \
            patch.object(
                strat, "_apply_master_block_filter_in_prepare",
                new=AsyncMock(return_value=(list(tickers), [])),
            ), \
            patch(
                "src.db.stock_master_daily.get_recent_daily_normalized",
                new=AsyncMock(return_value=candles),
            ), \
            patch("src.db.system_logs.write_log", new=AsyncMock()):
        import src.engine.scanner as scanner_mod
        with patch.object(scanner_mod, "ticker_prev_close", {}):
            await strat.prepare()


# ===========================================================================
# G-208-1 (HIGH, 핵심) — 넓은 박스 추세 상승 종목이 최종 후보에 포함
# ===========================================================================
@pytest.mark.asyncio
async def test_g208_1_wide_box_trend_stock_now_in_candidates():
    """ATR 통과 + 박스 폭이 넓은(예전 필터라면 탈락) 종목이 최종 후보에 포함.

    현재 코드: 박스 필터 `vol_pct > max_box_vol(5.0)` → continue → 탈락 → FAIL.
    제거 후: 박스 필터 없음 → _candidates 에 포함 → PASS.
    """
    strat = _make_strat()
    # vol_pct=0.07 → 박스 폭 ~7% > 임계 5% → 박스 수축 필터라면 탈락 대상
    wide_box = _make_donchian_passing_candles(n=70, base_price=10_000, vol_pct=0.07)

    await _run_prepare_with_candles(strat, wide_box, tickers=["005930"])

    assert "005930" in strat._candidates, (
        "넓은 박스 추세 상승 종목이 최종 후보에 포함되어야 함 "
        "(박스 수축 필터 제거 후) — 현재 코드는 vol_pct>5.0 continue 로 탈락(FAIL 예상)"
    )
    assert strat._scan_stats["final_prepared"] >= 1, (
        "final_prepared ≥ 1 (넓은 박스 종목 확정)"
    )


# ===========================================================================
# G-208-2 — DEFAULT_PARAMS 에 box 2 키 부재
# ===========================================================================
def test_g208_2_default_params_no_box_keys():
    """DonchianSwingStrategy.DEFAULT_PARAMS 에 box 수축 2 키 부재."""
    dp = DonchianSwingStrategy.DEFAULT_PARAMS
    assert "box_contraction_period" not in dp, (
        "DEFAULT_PARAMS 에 box_contraction_period 제거 의무"
    )
    assert "max_box_volatility_pct" not in dp, (
        "DEFAULT_PARAMS 에 max_box_volatility_pct 제거 의무"
    )


# ===========================================================================
# G-208-3 — scan_stats 에 box_contraction_pass 키 부재
# ===========================================================================
def test_g208_3_scan_stats_no_box_contraction_pass():
    """_empty_scan_stats() / get_scan_stats() 에 box_contraction_pass 키 부재."""
    from src.engine.strategies.donchian_swing import _empty_scan_stats

    stats = _empty_scan_stats()
    assert "box_contraction_pass" not in stats, (
        "_empty_scan_stats 에 box_contraction_pass 제거 의무"
    )

    strat = _make_strat()
    assert "box_contraction_pass" not in strat.get_scan_stats(), (
        "get_scan_stats 에 box_contraction_pass 노출 금지"
    )


# ===========================================================================
# G-208-4 — PARAM_RANGES 에 box 2 키 부재
# ===========================================================================
def test_g208_4_param_ranges_no_box_keys():
    """recommendation_engine.PARAM_RANGES 에 box 수축 2 키 부재."""
    from src.engine.recommendation_engine import PARAM_RANGES

    assert "box_contraction_period" not in PARAM_RANGES, (
        "PARAM_RANGES 에 box_contraction_period 제거 의무 (전략 정체성 상수 = AI 튜닝 제외)"
    )
    assert "max_box_volatility_pct" not in PARAM_RANGES, (
        "PARAM_RANGES 에 max_box_volatility_pct 제거 의무"
    )


# ===========================================================================
# G-208-5 — INT_PARAMS 에 box_contraction_period 부재
# ===========================================================================
def test_g208_5_int_params_no_box_contraction_period():
    """recommendation_engine.INT_PARAMS 에 box_contraction_period 부재."""
    from src.engine.recommendation_engine import INT_PARAMS

    assert "box_contraction_period" not in INT_PARAMS, (
        "INT_PARAMS 에 box_contraction_period 제거 의무"
    )


# ===========================================================================
# 불변식 INV-1~3 — 다른 필터는 제거 후에도 정상 탈락 (박스만 제거)
# ===========================================================================
@pytest.mark.asyncio
async def test_inv1_donchian_high_miss_still_rejected():
    """20일 신고가 미달 종목은 여전히 탈락 (donchian 필터 불변)."""
    strat = _make_strat()
    # 전일 종가가 신고가를 넘지 못하도록 — 전 구간 평탄 (i==0 도 base_price)
    today = datetime(2026, 5, 20).date()
    flat: list[dict] = []
    for i in range(70):
        d = today - timedelta(days=i + 1)
        close = 10_000
        flat.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_hgpr": str(int(close * 1.01)),
            "stck_lwpr": str(int(close * 0.99)),
            "stck_oprc": str(close),
            "acml_vol": "1000000",
        })
    await _run_prepare_with_candles(strat, flat, tickers=["005930"])

    assert "005930" not in strat._candidates, (
        "신고가 미달 종목은 여전히 탈락 (donchian 필터 불변)"
    )
    assert strat._scan_stats["donchian_pass"] == 0, "donchian_pass 미증가"


@pytest.mark.asyncio
async def test_inv2_close_below_ema_still_rejected():
    """전일 종가 < 60일 EMA (신고가는 돌파하되 EMA 아래) 종목은 여전히 탈락.

    최근 20일 저가 블록에서 신고가 돌파는 하되, 오래된 60일 블록이 고가라
    EMA60 > 전일 종가 → `prev_close <= ema_today` EMA 필터 탈락 (박스와 무관).
    """
    strat = _make_strat()
    today = datetime(2026, 5, 20).date()
    ema_reject: list[dict] = []
    for i in range(70):
        d = today - timedelta(days=i + 1)
        if i == 0:
            close = 11_000            # 최근 20일 저가 블록의 신고가 돌파
        elif i <= 20:
            close = 10_000            # 최근 20일 저가 블록
        else:
            close = 30_000            # 오래된 블록 고가 → EMA60 끌어올림
        ema_reject.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_hgpr": str(int(close * 1.01)),
            "stck_lwpr": str(int(close * 0.99)),
            "stck_oprc": str(close),
            "acml_vol": "3000000" if i == 0 else "1000000",
        })
    await _run_prepare_with_candles(strat, ema_reject, tickers=["005930"])

    assert "005930" not in strat._candidates, (
        "전일 종가 < 60일 EMA 종목은 여전히 탈락 (EMA 필터 불변)"
    )


@pytest.mark.asyncio
async def test_inv3_flat_series_zero_atr_still_rejected():
    """전 구간 완전 평탄(단일 가격, high==low==close) 종목은 여전히 탈락.

    돌파도 없고 ATR=0 (close-to-close 변동 0) → 박스 필터 제거해도 확정 안 됨.
    (박스만 제거, donchian/EMA/거래대금/ATR 필터는 불변 확인.)
    참고: 신고가 돌파와 ATR=0 은 수학적으로 상호 배타적 (돌파 = close[0]>prev high →
    TR>0) 이므로 ATR 을 단독 격리할 수 없음 — 완전 평탄 시리즈로 종합 불변 확인.
    """
    strat = _make_strat()
    today = datetime(2026, 5, 20).date()
    flat_atr: list[dict] = []
    for i in range(70):
        d = today - timedelta(days=i + 1)
        close = 10_000  # 전 구간 동일 → 돌파 0 + ATR 0
        flat_atr.append({
            "stck_bsop_date": d.strftime("%Y%m%d"),
            "stck_clpr": str(close),
            "stck_hgpr": str(close),
            "stck_lwpr": str(close),
            "stck_oprc": str(close),
            "acml_vol": "1000000",
        })
    await _run_prepare_with_candles(strat, flat_atr, tickers=["005930"])

    assert "005930" not in strat._candidates, (
        "완전 평탄 종목은 여전히 탈락 (박스 제거해도 다른 필터 불변)"
    )
    assert strat._scan_stats["atr_pass"] == 0, "atr_pass 미증가"
