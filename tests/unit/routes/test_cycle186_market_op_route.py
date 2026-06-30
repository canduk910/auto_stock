"""사이클 186 (2026-06-29) — GET /api/realtime/market-operation 라우트 Red 가드.

`src/routes/realtime.py` 신규 `get_market_operation` (기존 subscriptions ApiResponse 패턴 답습).
ApiResponse data = summary 전체 + circuit_breaker + details(cap 200) =
종목별 {ticker, vi_code, ovtm_vi_code, halt_yn, halt_reason, iscd_stat,
mkop_cls_code, exch_code, received_at} (get_last_event 활용, VI∪halt 종목 sorted).

검증 패턴: 사이클 127 답습 — TestClient 회피 + 라우트 함수 직접 await 호출.
승인 계획: `~/.claude/plans/hazy-prancing-cookie.md`.

Red 가드:
- ROUTE-SCHEMA: ApiResponse success + data 에 summary 키 + circuit_breaker + details(list)
- ROUTE-DETAILS: VI/halt 종목 mock → details 에 해당 ticker + 필드
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from src.api.market_operation import MarketOpEvent
from src.engine import market_operation_monitor as mom
from src.models.response import ApiResponse


KST = timezone(timedelta(hours=9))


def _make_event(
    ticker: str,
    *,
    trht_yn: str = "N",
    tr_susp_reas_cntt: str = "",
    mkop_cls_code: str = "110",
    vi_cls_code: str = "0",
    ovtm_vi_cls_code: str = "0",
    iscd_stat_cls_code: str = "0",
    exch_cls_code: str = "KRX",
) -> MarketOpEvent:
    return MarketOpEvent(
        ticker=ticker,
        trht_yn=trht_yn,
        tr_susp_reas_cntt=tr_susp_reas_cntt,
        mkop_cls_code=mkop_cls_code,
        antc_mkop_cls_code="110",
        mrkt_trtm_cls_code="0",
        divi_app_cls_code="0",
        iscd_stat_cls_code=iscd_stat_cls_code,
        vi_cls_code=vi_cls_code,
        ovtm_vi_cls_code=ovtm_vi_cls_code,
        exch_cls_code=exch_cls_code,
        received_at=datetime.now(KST),
    )


@pytest.fixture(autouse=True)
def _reset_state():
    mom.reset_market_op_state()
    yield
    mom.reset_market_op_state()


@pytest.mark.asyncio
async def test_route_schema_apiresponse_summary_cb_details() -> None:
    """ROUTE-SCHEMA — ApiResponse success + summary 키 + circuit_breaker + details(list)."""
    from src.routes.realtime import get_market_operation

    mom.record_market_op_event(_make_event("005930", vi_cls_code="1"))

    resp = await get_market_operation()

    assert isinstance(resp, ApiResponse)
    assert resp.success is True

    data = resp.data
    # summary 전체 포함
    for key in (
        "vi_active_count",
        "halt_active_count",
        "last_event_count",
        "iscd_stat_active_count",
        "circuit_breaker",
    ):
        assert key in data, f"market-operation data 키 누락 — {key}"

    assert isinstance(data["circuit_breaker"], dict)
    assert "suspected" in data["circuit_breaker"]
    assert isinstance(data["details"], list), "details 는 list 여야 함"


@pytest.mark.asyncio
async def test_route_details_vi_and_halt_tickers() -> None:
    """ROUTE-DETAILS — VI/halt 종목 mock → details 에 ticker + 필드."""
    from src.routes.realtime import get_market_operation

    mom.record_market_op_event(
        _make_event("005930", vi_cls_code="1", ovtm_vi_cls_code="0", mkop_cls_code="110")
    )
    mom.record_market_op_event(
        _make_event(
            "000020",
            trht_yn="Y",
            tr_susp_reas_cntt="서킷브레이커 발동",
            iscd_stat_cls_code="51",
            mkop_cls_code="121",
        )
    )

    resp = await get_market_operation()
    details = resp.data["details"]
    by_ticker = {row["ticker"]: row for row in details}

    # VI ∪ halt 종목 모두 노출
    assert "005930" in by_ticker, "VI 활성 종목 details 누락"
    assert "000020" in by_ticker, "거래정지 종목 details 누락"

    # 종목별 필드 정합
    vi_row = by_ticker["005930"]
    for field in ("ticker", "vi_code", "ovtm_vi_code", "halt_yn", "mkop_cls_code"):
        assert field in vi_row, f"details 필드 누락 — {field}"
    assert vi_row["vi_code"] == "1"

    halt_row = by_ticker["000020"]
    assert halt_row["halt_yn"] == "Y"
    assert halt_row["halt_reason"] == "서킷브레이커 발동"
    assert halt_row["mkop_cls_code"] == "121"


@pytest.mark.asyncio
async def test_route_empty_state_graceful() -> None:
    """ROUTE-SCHEMA 보조 — VI/halt 0건 정상 시 빈 details + CB suspected=False."""
    from src.routes.realtime import get_market_operation

    resp = await get_market_operation()

    assert resp.success is True
    assert resp.data["details"] == []
    assert resp.data["circuit_breaker"]["suspected"] is False
