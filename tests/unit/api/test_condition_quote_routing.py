"""Cycle 7-C Red — condition.py 시세성 함수가 `kis_get_quote` 로 위임된다.

기존 `kis_get` 호출을 `kis_get_quote` 로 치환해 보조 계좌 풀 라우팅 가능하게 한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.api import condition as cond_mod

pytestmark = pytest.mark.unit


@pytest.fixture
def spy_quote_get(monkeypatch: pytest.MonkeyPatch):
    """`kis_get_quote` 를 AsyncMock 으로 교체해 호출 추적."""
    from src.api import base as base_mod

    spy = AsyncMock(
        return_value={"rt_cd": "0", "msg_cd": "OK", "msg1": "정상",
                      "output": {"stck_prpr": "65000", "lstn_stcn": "1000",
                                 "acml_tr_pbmn": "1000000", "stck_clpr": "60000",
                                 "prdt_abrv_name": "삼성전자",
                                 "cptt_trad_tr_psbl_yn": "Y",
                                 "nxt_tr_stop_yn": "N",
                                 "tr_stop_yn": "N",
                                 "admn_item_yn": "N",
                                 "excg_dvsn_cd": "01",
                                 "pdno": "005930",
                                 "opnd_yn": "Y",
                                 "bass_dt": "20260518"},
                      "output2": [{
                          "stck_bsop_date": "20260516",
                          "stck_oprc": "60000", "stck_hgpr": "65000",
                          "stck_lwpr": "59000", "stck_clpr": "63000",
                          "acml_vol": "1000000",
                      }]}
    )

    monkeypatch.setattr(base_mod, "kis_get_quote", spy, raising=False)
    monkeypatch.setattr(cond_mod, "kis_get_quote", spy, raising=False)
    return spy


@pytest.fixture
def spy_main_get(monkeypatch: pytest.MonkeyPatch):
    """`kis_get` (메인) 도 함께 spy 해서 시세 함수가 메인 경로로 새지 않는지 검증."""
    from src.api import base as base_mod
    spy = AsyncMock(return_value={"rt_cd": "0", "msg_cd": "OK", "msg1": "정상", "output": {}})
    monkeypatch.setattr(base_mod, "kis_get", spy, raising=False)
    monkeypatch.setattr(cond_mod, "kis_get", spy, raising=False)
    return spy


# ---------------------------------------------------------------------------
# B-1. fetch_stock_detail → kis_get_quote
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_stock_detail_routes_via_quote_pool(spy_quote_get, spy_main_get, monkeypatch):
    """`fetch_stock_detail` 호출 시 `kis_get_quote` 가 호출된다."""
    # 캐시 비우기 — 이전 테스트에서 적재된 캐시 미스 보장
    cond_mod.clear_caches()
    await cond_mod.fetch_stock_detail("005930")

    spy_quote_get.assert_called()
    # 메인 kis_get 은 호출되지 않음
    assert spy_main_get.call_count == 0, (
        f"시세 함수는 메인 kis_get 경로 호출 금지: {spy_main_get.call_args_list}"
    )


# ---------------------------------------------------------------------------
# B-2. fetch_daily_candles → kis_get_quote
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_daily_candles_routes_via_quote_pool(spy_quote_get, spy_main_get):
    """`fetch_daily_candles` 호출 시 `kis_get_quote` 가 호출된다."""
    cond_mod.clear_caches()
    await cond_mod.fetch_daily_candles("005930", days=21)

    spy_quote_get.assert_called()
    assert spy_main_get.call_count == 0


# ---------------------------------------------------------------------------
# B-3. _fetch_fluctuation_rank → kis_get_quote
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_fluctuation_rank_routes_via_quote_pool(spy_quote_get, spy_main_get):
    """등락률 순위 조회가 시세 풀 경로로 위임된다."""
    await cond_mod._fetch_fluctuation_rank()
    spy_quote_get.assert_called()
    assert spy_main_get.call_count == 0


# ---------------------------------------------------------------------------
# B-4. inquire_stock_basics → kis_get_quote
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inquire_stock_basics_routes_via_quote_pool(spy_quote_get, spy_main_get):
    """주식기본조회(CTPF1002R) 가 시세 풀 경로로 위임된다."""
    await cond_mod.inquire_stock_basics("005930")
    spy_quote_get.assert_called()
    assert spy_main_get.call_count == 0


# ---------------------------------------------------------------------------
# B-5. is_market_open / next_trading_day → kis_get_quote
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_holiday_check_routes_via_quote_pool(spy_quote_get, spy_main_get):
    """휴장일 / 다음 영업일 조회가 시세 풀 경로로 위임된다."""
    from datetime import date

    spy_quote_get.return_value = {
        "rt_cd": "0", "msg_cd": "OK", "msg1": "정상",
        "output": [{"bass_dt": "20260518", "opnd_yn": "Y"}],
    }

    await cond_mod.is_market_open(date(2026, 5, 18))
    assert spy_quote_get.call_count >= 1
    spy_quote_get.reset_mock()

    await cond_mod.next_trading_day(date(2026, 5, 18))
    assert spy_quote_get.call_count >= 1
    assert spy_main_get.call_count == 0


# ---------------------------------------------------------------------------
# B-6. 매매/잔고 함수는 kis_get_quote / kis_post_quote 절대 호출 안 함
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_order_module_never_imports_quote_pool():
    """`src/api/order.py` 모듈 소스에 `kis_get_quote` 또는 `kis_post_quote` 미존재."""
    from pathlib import Path

    order_src = (
        Path(__file__).resolve().parents[3]
        / "src" / "api" / "order.py"
    ).read_text(encoding="utf-8")
    assert "kis_get_quote" not in order_src, "order.py 는 시세 풀 함수 import 금지"
    assert "kis_post_quote" not in order_src, "order.py 는 시세 풀 함수 import 금지"


@pytest.mark.asyncio
async def test_balance_module_never_imports_quote_pool():
    """`src/api/balance.py` 모듈 소스에 `kis_get_quote` 또는 `kis_post_quote` 미존재."""
    from pathlib import Path

    balance_src = (
        Path(__file__).resolve().parents[3]
        / "src" / "api" / "balance.py"
    ).read_text(encoding="utf-8")
    assert "kis_get_quote" not in balance_src, "balance.py 는 시세 풀 함수 import 금지"
    assert "kis_post_quote" not in balance_src, "balance.py 는 시세 풀 함수 import 금지"
