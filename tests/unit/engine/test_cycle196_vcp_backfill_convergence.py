"""사이클 196 (2026-07-07) — VCP daily backfill 수렴 회귀 가드 (churn 종결).

배경 (사이클 192 D+1 실측): `_stock_master_daily_load_once` 의 VCP universe backfill 이
수렴 못 해 매 load 마다 348종목 전량 재backfill (churn). 근본 = backfill 조건
`existing_count < _DAILY_LOAD_VCP_BACKFILL_DAYS(=220)` 인데 retention 230cal일이 보유
영업일을 154 로 캡 → 220 절대 미도달 → use_vcp_backfill 영구 True.

시정 (P1): `_DAILY_LOAD_VCP_BACKFILL_DAYS = 220 → 120` (retained 154 대비 34일 마진 +
VCP prepare 100일 위 20일 버퍼). 수렴: existing 120 도달 → incremental 전환 → churn 종료.

Group B 회귀 가드 (scanner.py `_stock_master_daily_load_once`):
- B-1: 상수 == 120
- B-2 (핵심 수렴): VCP + count=154 → backfill 미호출 + fetch_daily_candles(days=7) 증분
- B-3: VCP + count=119 (<120) → fetch_daily_candles_backfill(total_days=120) 호출
- B-4 (경계, 불변식): count == threshold → strict-< False → 재backfill 금지 (incremental)
- B-5 (regression, 불변식): 非VCP 불변 (154→증분 days=7 / 30→100일 backfill)

Group C:
- C-1 (SAFETY, AST, 불변식): scanner 변경 = 상수값만 — daily_load 본체 매매 hot path 참조 0
  + 구독/스캔 함수 심볼 존재 (사이클 172 SAFETY 패턴 답습)

Red 유효성 (production 미변경 = 상수 220):
- B-1/B-2/B-3 FAIL (220 기준 → 154/119 모두 backfill / total_days=220)
- B-4/B-5/C-1 PASS (불변식 — count vs threshold 동적 비교 / 非VCP 무관 / AST 심볼)

mock 구성: 사이클 172 test_cycle172_vcp_universe_backfill.py 100% 답습
(list_all side_effect + max_bas_dd/count_by_ticker/fetch_*/upsert_batch + asyncio.sleep).
max_bas_dd=None = "fresh 아님 → 적재 진행" (사이클 176/180 교훈 — 날짜 하드코딩 회피).
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner

pytestmark = pytest.mark.unit


def _vcp_candle(bas_dd: str = "20260620") -> dict:
    return {
        "stck_bsop_date": bas_dd, "stck_clpr": "71000",
        "stck_oprc": "70500", "stck_hgpr": "71500", "stck_lwpr": "70000",
        "acml_vol": "12345678", "acml_tr_pbmn": "876543210000",
    }


# ---------------------------------------------------------------------------
# B-1 — 상수 == 120
# ---------------------------------------------------------------------------
def test_b1_backfill_days_constant_120():
    """_DAILY_LOAD_VCP_BACKFILL_DAYS == 120 (retention 230cal=154영업일 내 수렴).

    Red (220): FAIL. Green (120): PASS.
    """
    assert scanner._DAILY_LOAD_VCP_BACKFILL_DAYS == 120, (
        "사이클 196 — retained 154 대비 34일 마진 + VCP prepare 100일 위 20일 버퍼"
    )


# ---------------------------------------------------------------------------
# B-2 (핵심 수렴) — VCP + count=154 → 재backfill 금지 + 증분 (days=7)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b2_vcp_154_converges_to_incremental():
    """VCP universe + count_by_ticker=154 → backfill 미호출 + fetch_daily_candles(days=7).

    Red (220): 154 < 220 → use_vcp_backfill=True → backfill 호출 → await_count==0 FAIL.
    Green (120): 154 >= 120 → 증분 (154>=50 → days=7) → backfill 0 + days=7 → PASS.
    이것이 churn 종결의 핵심 증명 (retained 154 도달 시 재backfill 금지 = incremental 수렴).
    """
    stock_master_rows = [
        {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False},
    ]
    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_vcp_candle()]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),  # fresh 아님 → 적재 진행
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=154),  # retained 영업일 실측
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=capture_fetch),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 0, (
        "VCP 154 >= 120 → 재backfill 금지 (수렴). Red(220): 154<220 → backfill 호출 = FAIL"
    )
    assert 7 in captured_days, "VCP 154 → 증분 모드 (fetch_daily_candles days=7)"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# B-3 — VCP + count=119 (<120) → fetch_daily_candles_backfill(total_days=120)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b3_vcp_119_triggers_backfill_total_120():
    """VCP + count_by_ticker=119 (<120) → backfill 호출 + total_days=120.

    Red (220): backfill 호출되나 total_days=220 → `== 120` 단언 FAIL.
    Green (120): backfill total_days=120 → PASS.
    """
    stock_master_rows = [
        {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False},
    ]
    backfill_mock = AsyncMock(return_value=[_vcp_candle()])

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=119),  # < 120 → VCP backfill
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=[_vcp_candle()]),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 1, "VCP count 119 < 120 → backfill 호출"
    # 하드코딩 120 (상수 참조 시 Red 에서도 PASS 되어 Red 무효) — 목표값 명시 단언
    assert backfill_mock.call_args.kwargs.get("total_days") == 120, (
        "backfill total_days=120 의무. Red(220): total_days=220 → FAIL"
    )
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# B-4 (경계, 불변식) — count == threshold → strict-< False → 재backfill 금지
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b4_boundary_count_equals_threshold_incremental():
    """count_by_ticker == _DAILY_LOAD_VCP_BACKFILL_DAYS → strict-< False → incremental.

    threshold 를 상수에서 동적 취득 → Red(220)/Green(120) 양쪽 불변식 PASS:
    - Red: count=220, 220 < 220 = False → 증분 (days=7). backfill 0.
    - Green: count=120, 120 < 120 = False → 증분. backfill 0.
    strict-`<` 경계 (== 는 backfill 아님) 를 상수값 무관 영구 고정.
    """
    threshold = scanner._DAILY_LOAD_VCP_BACKFILL_DAYS  # 220(Red) / 120(Green) 동적
    stock_master_rows = [
        {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False},
    ]
    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_vcp_candle()]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=threshold),  # 정확히 경계값
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=capture_fetch),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 0, (
        "existing == threshold → strict-< False → 재backfill 금지 (경계 불변식)"
    )
    assert 7 in captured_days, "경계값(>=50) → 증분 (days=7)"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# B-5a (regression, 불변식) — 非VCP + existing=154 → 증분 (days=7)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b5a_non_vcp_154_incremental_unchanged():
    """非VCP (is_kospi200=False, is_kosdaq150=False) + existing=154 → 증분 (days=7).

    VCP 분기 미진입 → threshold 무관 불변식 (Red/Green 모두 PASS).
    """
    stock_master_rows = [
        {"ticker": "999999", "is_kospi200": False, "is_kosdaq150": False,
         "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},  # 사이클 206 자격
    ]
    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_vcp_candle()]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=154),  # >= 50 → 증분
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=capture_fetch),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 0, "非VCP = VCP backfill 분기 미진입 (불변)"
    assert 7 in captured_days, "非VCP 154 >= 50 → 증분 (days=7) 불변"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# B-5b (regression, 불변식) — 非VCP + existing=30 → 100일 backfill (days=100)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_b5b_non_vcp_30_hundred_day_unchanged():
    """非VCP + existing=30 (<50) → 현행 100일 fetch_daily_candles(days=100) (VCP 분기 미진입).

    사이클 122 현행 유지 불변식 (Red/Green 모두 PASS).
    """
    stock_master_rows = [
        {"ticker": "999999", "is_kospi200": False, "is_kosdaq150": False,
         "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},  # 사이클 206 자격
    ]
    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    captured_days: list[int] = []

    async def capture_fetch(ticker, days):
        captured_days.append(days)
        return [_vcp_candle()]

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=30),  # < 50 → 백필 100일
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(side_effect=capture_fetch),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 0, "非VCP = VCP backfill 미사용 (불변)"
    assert 100 in captured_days, "非VCP 30 < 50 → 현행 100일 fetch_daily_candles(days=100) 불변"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# C-1 (SAFETY, AST, 불변식) — scanner 변경 = 상수값만 (매매 hot path 불변)
# ---------------------------------------------------------------------------
def test_c1_safety_daily_load_no_trading_hot_path():
    """_stock_master_daily_load_once 본체 매매 hot path 참조 0 + 구독/스캔 함수 심볼 존재.

    사이클 172 SAFETY 패턴 답습 — 사이클 196 변경이 `_DAILY_LOAD_VCP_BACKFILL_DAYS`
    상수 값에 국한 (구독/스캔/우선순위/매수 경로 불변) 임을 정적 검증.
    불변식 — Red/Green 모두 PASS.
    """
    src = inspect.getsource(scanner._stock_master_daily_load_once)
    forbidden = (
        "risk.on_tick", "order_engine", "execute_buy", "execute_sell",
        "place_order", "check_exit_signal", "check_buy_signal",
        "subscribe_filtered_stocks", "scan_stocks",
    )
    for token in forbidden:
        assert token not in src, (
            f"_stock_master_daily_load_once 매매/구독 hot path 참조 0 의무: {token}"
        )

    # 상수 정의 존재 (사이클 196 변경 = 값만)
    assert hasattr(scanner, "_DAILY_LOAD_VCP_BACKFILL_DAYS"), \
        "_DAILY_LOAD_VCP_BACKFILL_DAYS 상수 정의 존재 의무"

    # 구독/스캔 경로 함수 심볼 불변 (accidental 삭제 방지)
    assert callable(getattr(scanner, "subscribe_filtered_stocks", None)), \
        "subscribe_filtered_stocks 심볼 불변"
    assert callable(getattr(scanner, "scan_stocks", None)), \
        "scan_stocks 심볼 불변"
