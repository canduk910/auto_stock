"""VB / LTV `_scan_universe()` BLNG_CLS_CODE 0/1/3 다중 호출 합집합 검증.

후보 풀 확장(현재 25 → 60~90종목) + 부분 실패 회복 + ETF/중복 dedupe.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.api.base import KisApiError
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import StrategyConfig

_xfail_cycle108 = pytest.mark.xfail(
    strict=False,
    reason="사이클 108 stock_master 전환으로 BLNG_CODES 3회 호출 패턴 폐기 — "
           "과거 계약 영속 보존 (사이클 97 K-2 패턴 답습)",
)
pytestmark = [pytest.mark.unit, _xfail_cycle108]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _item(ticker: str, name: str = "샘플전자", price: int = 50_000,
          listed: int = 50_000_000, prdy_vol: int = 5_000_000,
          prdy_vrss: int = 100) -> dict[str, Any]:
    """volume-rank `output` 단일 항목 모사."""
    return {
        "mksc_shrn_iscd": ticker,
        "hts_kor_isnm": name,
        "stck_prpr": str(price),
        "lstn_stcn": str(listed),
        "prdy_vol": str(prdy_vol),
        "prdy_vrss": str(prdy_vrss),
    }


@pytest.fixture
def vb(monkeypatch):
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_names", {})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    return VolatilityBreakoutStrategy(
        StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.3)
    )


@pytest.fixture
def ltv(monkeypatch):
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_names", {})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    return LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="LTV", weight=0.3)
    )


# ---------------------------------------------------------------------------
# 1) BLNG 0 / 1 / 3 — 3회 호출 검증 (VB)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_universe_vb_calls_three_blng_codes(vb):
    mock_get = AsyncMock(return_value={"output": [_item("005930", "삼성전자")]})
    with patch("src.api.base.kis_get", mock_get), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        await vb._scan_universe()
    # 3회 호출 — BLNG=0, 1, 3
    assert mock_get.call_count == 3
    blng_codes = [
        call.args[2].get("FID_BLNG_CLS_CODE")
        for call in mock_get.call_args_list
    ]
    assert blng_codes == ["0", "1", "3"]


@pytest.mark.asyncio
async def test_scan_universe_ltv_calls_three_blng_codes(ltv):
    mock_get = AsyncMock(return_value={"output": [_item("005930", "삼성전자")]})
    with patch("src.api.base.kis_get", mock_get), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        await ltv._scan_universe()
    assert mock_get.call_count == 3
    blng_codes = [
        call.args[2].get("FID_BLNG_CLS_CODE")
        for call in mock_get.call_args_list
    ]
    assert blng_codes == ["0", "1", "3"]


# ---------------------------------------------------------------------------
# 2) 합집합 dedupe — 같은 ticker 가 BLNG 0/1/3 응답에 모두 있어도 1회
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_universe_vb_dedupes_across_blng(vb):
    # BLNG=0: A,B / BLNG=1: B,C / BLNG=3: C,D — 합집합 dedupe = {A,B,C,D}
    responses = [
        {"output": [_item("000001", "에이"), _item("000002", "비")]},
        {"output": [_item("000002", "비"), _item("000003", "씨")]},
        {"output": [_item("000003", "씨"), _item("000004", "디")]},
    ]
    mock_get = AsyncMock(side_effect=responses)
    with patch("src.api.base.kis_get", mock_get), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await vb._scan_universe()
    # 4종목 합집합 (중복 제거)
    assert set(result) == {"000001", "000002", "000003", "000004"}
    # 정렬은 첫 등장(BLNG=0 우선) 기반
    assert result.index("000001") < result.index("000004")


@pytest.mark.asyncio
async def test_scan_universe_ltv_dedupes_across_blng(ltv):
    responses = [
        {"output": [_item("000001", "에이"), _item("000002", "비")]},
        {"output": [_item("000002", "비"), _item("000003", "씨")]},
        {"output": [_item("000003", "씨"), _item("000004", "디")]},
    ]
    mock_get = AsyncMock(side_effect=responses)
    with patch("src.api.base.kis_get", mock_get), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await ltv._scan_universe()
    assert set(result) == {"000001", "000002", "000003", "000004"}


# ---------------------------------------------------------------------------
# 3) 부분 실패 회복 — BLNG=1 만 raise 해도 0/3 결과로 진행
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_universe_vb_handles_one_blng_failure(vb):
    responses = [
        {"output": [_item("000001", "에이")]},
        KisApiError("1", "FAIL01", "조회 실패"),  # BLNG=1 실패
        {"output": [_item("000003", "씨")]},
    ]
    mock_get = AsyncMock(side_effect=responses)
    with patch("src.api.base.kis_get", mock_get), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await vb._scan_universe()
    # BLNG=0 + BLNG=3 결과만 반영 (BLNG=1 실패해도 raise 안 되고 다음 호출 진행)
    assert set(result) == {"000001", "000003"}
    assert mock_get.call_count == 3


@pytest.mark.asyncio
async def test_scan_universe_ltv_handles_one_blng_failure(ltv):
    responses = [
        {"output": [_item("000001", "에이")]},
        KisApiError("1", "FAIL01", "조회 실패"),
        {"output": [_item("000003", "씨")]},
    ]
    mock_get = AsyncMock(side_effect=responses)
    with patch("src.api.base.kis_get", mock_get), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await ltv._scan_universe()
    assert set(result) == {"000001", "000003"}
    assert mock_get.call_count == 3


# ---------------------------------------------------------------------------
# 4) 3회 모두 실패 — 0종목 ERROR 로그 + 빈 결과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_universe_vb_all_three_fail_emits_error_log(vb, caplog):
    mock_get = AsyncMock(side_effect=KisApiError("1", "FAIL01", "조회 실패"))
    write_log_mock = AsyncMock()
    with patch("src.api.base.kis_get", mock_get), \
         patch("src.db.system_logs.write_log", write_log_mock):
        with caplog.at_level("ERROR"):
            result = await vb._scan_universe()
    assert result == []
    assert mock_get.call_count == 3
    # ERROR 로그 1회 (write_log 호출 확인)
    write_log_mock.assert_called_once()
    call_args = write_log_mock.call_args
    assert call_args.args[0] == "ERROR"
    assert "0종목" in call_args.args[1]


@pytest.mark.asyncio
async def test_scan_universe_ltv_all_three_fail_emits_error_log(ltv, caplog):
    mock_get = AsyncMock(side_effect=KisApiError("1", "FAIL01", "조회 실패"))
    write_log_mock = AsyncMock()
    with patch("src.api.base.kis_get", mock_get), \
         patch("src.db.system_logs.write_log", write_log_mock):
        with caplog.at_level("ERROR"):
            result = await ltv._scan_universe()
    assert result == []
    assert mock_get.call_count == 3
    write_log_mock.assert_called_once()


# ---------------------------------------------------------------------------
# 5) ETF 필터 — 모든 BLNG 응답에서 동일 키워드로 제외
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_universe_vb_etf_filtered_per_blng(vb):
    # 각 BLNG 마다 ETF 1건 + 일반 1건 → 일반만 합집합
    responses = [
        {"output": [_item("000001", "에이"), _item("100001", "KODEX 코스피")]},
        {"output": [_item("000002", "비"), _item("100002", "TIGER 코스닥")]},
        {"output": [_item("000003", "씨"), _item("100003", "KBSTAR 200")]},
    ]
    mock_get = AsyncMock(side_effect=responses)
    with patch("src.api.base.kis_get", mock_get), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await vb._scan_universe()
    # ETF 3종(KODEX/TIGER/KBSTAR) 모두 제외, 일반 3종만
    assert set(result) == {"000001", "000002", "000003"}
    assert "100001" not in result
    assert "100002" not in result
    assert "100003" not in result


@pytest.mark.asyncio
async def test_scan_universe_ltv_etf_filtered_per_blng(ltv):
    responses = [
        {"output": [_item("000001", "에이"), _item("100001", "KODEX 코스피")]},
        {"output": [_item("000002", "비"), _item("100002", "TIGER 코스닥")]},
        {"output": [_item("000003", "씨"), _item("100003", "KBSTAR 200")]},
    ]
    mock_get = AsyncMock(side_effect=responses)
    with patch("src.api.base.kis_get", mock_get), \
         patch("src.db.system_logs.write_log", AsyncMock()):
        result = await ltv._scan_universe()
    assert set(result) == {"000001", "000002", "000003"}
