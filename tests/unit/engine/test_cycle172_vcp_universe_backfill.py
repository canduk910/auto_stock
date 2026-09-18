"""사이클 172 (2026-06-22) — _stock_master_daily_load_once VCP universe 220일 backfill 분기.
사이클 196 (2026-07-07) — 임계 220 → 120 수렴 (retention 154영업일 실측 기반).
cycle299 (2026-09-17) — 임계 120 → 225 확장 (retention 390cal ≈ 261영업일 동반 확장).

이 파일이 재는 것은 **분기의 존재와 방향**이지 임계값 자체가 아니다 (임계값 정본 가드 =
`test_cycle196_vcp_backfill_convergence.py::B-1` + `test_cycle299_backfill_target_expansion.py::G-299-2`).
아래 케이스들은 임계가 120 이든 225 든 같은 쪽으로 떨어지도록 골라져 있어 값 변경에
무접촉이다 (count 100/50 은 어느 임계에서도 미달, 230 은 어느 임계에서도 충족).

cycle302 (2026-09-18) — **backfill 대상이 지수에서 「적재 대상 전부」로 넓어졌다.**
DB 깊이 < 임계인 적재 대상(index ∪ 시총·거래대금 자격 ∪ 보유·익일청산 보호)은
지수 소속과 무관하게 분할 fetch backfill 을 탄다. 지수 종목의 행위는 불변이고
(SCAN-1/2/4), 바뀐 것은 **비지수 종목이 더는 100일에 묶이지 않는다**는 것이다
(SCAN-3/3b 의미 전환). 계약 정본 = `test_cycle302_backfill_scope_expansion.py`.

회귀 가드 매트릭스:
- SCAN-1 (HIGH): 지수(is_kospi200) DB < 임계 → fetch_daily_candles_backfill 분기
- SCAN-2 (HIGH): 지수(is_kosdaq150) 동일 분기
- SCAN-3 (HIGH): 비지수 자격 종목도 DB < 임계면 같은 분기 (cycle302 의미 전환)
- SCAN-4: DB >= 임계 → 증분 유지 (재 backfill 금지)
- SCAN-5: graceful (backfill 실패 → 다음 ticker 진행)
- SAFETY-1 (HIGH): 매매 무관 — risk/order_engine/realtime/auth import 0

영속 의무:
- 사이클 38 명문화 (scanner 매수 진입 전 영역 — 16:00 daily task 만)
- 사이클 88 G-REJECT graceful
- 사이클 122 백필/증분 분기 영속 (비 VCP universe)
- 사이클 153 is_kospi200/is_kosdaq150 컬럼 (list_all .select("*") 포함)
"""

from __future__ import annotations

import ast
import inspect
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.engine import scanner

pytestmark = pytest.mark.unit


# 문서용 상수 — 이 파일의 어떤 테스트도 참조하지 않는다(케이스가 임계 무접촉이라 그렇다,
# 위 모듈 docstring). cycle299 가 프로덕션 임계를 225 로 올려 값을 다시 맞췄다.
_VCP_BACKFILL_THRESHOLD = 225  # noqa: F841 — 의도적 문서 상수


def _vcp_candle(bas_dd: str = "20260620") -> dict:
    return {
        "stck_bsop_date": bas_dd, "stck_clpr": "71000",
        "stck_oprc": "70500", "stck_hgpr": "71500", "stck_lwpr": "70000",
        "acml_vol": "12345678", "acml_tr_pbmn": "876543210000",
    }


# ---------------------------------------------------------------------------
# SCAN-1 (HIGH) — VCP universe (is_kospi200) DB < 225 → backfill 분기
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan1_kospi200_under_target_triggers_backfill():
    """is_kospi200=True + DB < 225 → fetch_daily_candles_backfill 호출."""
    stock_master_rows = [
        {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False},
    ]

    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    ranged_kis_mock = AsyncMock(return_value=[_vcp_candle()])

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=100),  # < 225 → VCP backfill
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=ranged_kis_mock,
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 1, \
        "VCP universe (is_kospi200) DB < 225 → fetch_daily_candles_backfill 분기"
    assert ranged_kis_mock.await_count == 0, "VCP universe 는 100일 fetch 미사용"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-2 (HIGH) — VCP universe (is_kosdaq150) 동일 분기
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan2_kosdaq150_under_target_triggers_backfill():
    """is_kosdaq150=True + DB < 225 → fetch_daily_candles_backfill 호출."""
    stock_master_rows = [
        {"ticker": "247540", "is_kospi200": False, "is_kosdaq150": True},
    ]

    backfill_mock = AsyncMock(return_value=[_vcp_candle()])
    ranged_kis_mock = AsyncMock(return_value=[_vcp_candle()])

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=50),  # < 225 → VCP backfill
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=backfill_mock,
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=ranged_kis_mock,
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    assert backfill_mock.await_count == 1, \
        "VCP universe (is_kosdaq150) DB < 225 → backfill 분기"
    assert ranged_kis_mock.await_count == 0
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-3 (HIGH) — 비지수 자격 종목도 같은 분기 (cycle302 의미 전환)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan3_non_index_qualifier_takes_backfill():
    """비지수(is_kospi200=False, is_kosdaq150=False) 자격 종목 → 같은 분할 backfill.

    ⚠️ cycle302 **의미 전환**. 종전 단언은 "비 VCP 는 현행 100일 유지" 였고, 그
    제한이 비지수 1,526 종목을 125행 안팎에 묶어 VCP 정배열 판정을 동전던지기로
    만들었다(2026-09-18 실측). 단언을 약화한 것이 아니라 **반대 방향으로 강하게**
    다시 걸었다 — 이제 100일 fetch 가 불리면 붉어진다.
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
        new=AsyncMock(return_value=10),  # < 50 백필 (사이클 122 현행)
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

    assert backfill_mock.await_count == 1, (
        "비지수 자격 종목도 DB < 임계면 분할 backfill 이다(cycle302). "
        f"실측 backfill={backfill_mock.await_count} fetch_days={captured_days}"
    )
    assert 100 not in captured_days, (
        "100일 단발 fetch 로 떨어지면 목표 깊이에 영영 못 닿는다. "
        f"실측 fetch_days={captured_days}"
    )
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-3b — 지수 플래그 키 부재 row 도 자격만 통과하면 같은 깊이 (cycle302)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan3b_missing_flag_keys_still_take_backfill():
    """is_kospi200/is_kosdaq150 키 부재 row → 비지수 취급이지만 깊이는 같다.

    플래그 부재가 여전히 **비지수 취급**(falsy)이라는 사실은 불변이고, cycle302 는
    그 사실이 backfill 깊이를 가르지 않게 만들었다. 적재 대상 판정은 자격
    (`_is_daily_load_universe`)이 여전히 담당한다.
    """
    stock_master_rows = [
        {"ticker": "005930",
         "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},  # 사이클 206 자격
    ]  # 사이클 122 mock 형식 (플래그 키 없음)

    backfill_mock = AsyncMock(return_value=[_vcp_candle()])

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=10),
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

    assert backfill_mock.await_count == 1, (
        "플래그 키 부재 row 도 적재 대상이면 목표 깊이를 받는다(cycle302). "
        f"실측 backfill={backfill_mock.await_count}"
    )
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-4 — VCP universe DB >= 225 → 증분 유지 (재 backfill 금지)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan4_vcp_over_target_incremental():
    """VCP universe DB >= 225 → 증분 모드 (재 backfill 금지)."""
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
        new=AsyncMock(return_value=date(2026, 6, 1)),  # 미래 아님 → 적재 진행
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(return_value=230),  # >= 225 → 증분
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

    assert backfill_mock.await_count == 0, "DB >= 225 → 재 backfill 금지"
    assert 7 in captured_days, "증분 모드 (T-7일) 유지"
    assert summary["fetched"] == 1


# ---------------------------------------------------------------------------
# SCAN-5 — graceful (backfill 실패 → 다음 ticker 진행)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan5_backfill_failure_graceful():
    """backfill 실패 → 사이클 88 G-REJECT graceful (다음 ticker 진행).

    ⚠️ cycle302 로 backfill 대상이 넓어져, 두 번째 종목을 **수렴 상태**(DB >= 임계)로
    둬야 증분 분기가 실제로 돈다. 그래야 이 테스트가 재려는 것("한 종목의 실패가
    루프를 끊지 않는다")이 공허해지지 않는다.
    """
    stock_master_rows = [
        {"ticker": "005930", "is_kospi200": True, "is_kosdaq150": False},
        {"ticker": "000660", "is_kospi200": False, "is_kosdaq150": False,
         "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"}},  # 사이클 206 자격
    ]

    async def backfill_fail(ticker, **kwargs):
        raise RuntimeError("KIS backfill 실패")

    with patch(
        "src.db.stock_master.list_all",
        new=AsyncMock(side_effect=[stock_master_rows, []]),
    ), patch(
        "src.db.stock_master_daily.max_bas_dd",
        new=AsyncMock(return_value=None),
    ), patch(
        "src.db.stock_master_daily.count_by_ticker",
        new=AsyncMock(side_effect=[100, 230]),  # 005930 backfill / 000660 증분
    ), patch(
        "src.api.condition.fetch_daily_candles_backfill",
        new=AsyncMock(side_effect=backfill_fail),
    ), patch(
        "src.api.condition.fetch_daily_candles",
        new=AsyncMock(return_value=[_vcp_candle()]),
    ), patch(
        "src.db.stock_master_daily.upsert_batch",
        new=AsyncMock(return_value=1),
    ), patch("asyncio.sleep", new=AsyncMock()):
        summary = await scanner._stock_master_daily_load_once()

    # 005930 backfill 실패 → failed++, 000660(수렴 상태) 증분으로 정상 진행
    assert summary["failed"] >= 1, "backfill 실패 → failed++ graceful"
    assert summary["fetched"] >= 1, "다음 ticker 정상 진행"


# ---------------------------------------------------------------------------
# SAFETY-1 (HIGH) — 매매 무관 (scanner _stock_master_daily_load_once import 0)
# ---------------------------------------------------------------------------
def test_safety1_no_trading_hot_path_import():
    """_stock_master_daily_load_once 본체 — risk/order_engine/realtime/auth 참조 0."""
    src = inspect.getsource(scanner._stock_master_daily_load_once)
    for forbidden in ("risk.on_tick", "order_engine", "execute_buy", "execute_sell",
                      "place_order", "check_exit_signal", "check_buy_signal"):
        assert forbidden not in src, \
            f"_stock_master_daily_load_once 매매 hot path 참조 0 의무: {forbidden}"
