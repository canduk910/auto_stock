"""cycle371 Red — `GET /api/realtime/market-operation` details 에 종목상태 단독 종목 포함.

배경 = `_workspace/00_URGENT_WORKLIST.md` 「남은 일」 C 절 cycle368 후속(b):
"51·59 만인 종목은 화면 행이 없다(백엔드 `details` = VI ∪ 거래정지, 표시만)". 헤더
`iscd_stat_active_count` 는 표시 집합(51/52/53/54/58/59) 멤버십으로 세는데(`_ISCD_STAT_
DISPLAY_CODES`), `details` 는 여전히 VI ∪ 거래정지 집합만 훑어서 **관리종목(51)·단기
과열(59) 단독**(VI 비활성 + `trht_yn != Y` + 종목상태가 58 이 아님) 종목은 헤더 카운트
에는 잡히는데 상세 행이 없다.

시정 = `market_operation_monitor.get_iscd_stat_active_tickers()`(cycle371 신규) 를
`details` 대상 집합에 합집합한다. **카운트(`vi_active_count`/`halt_active_count`/
`iscd_stat_active_count`)는 무변경** — summary dict 를 그대로 두고 `details` 원본 행만
늘린다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
async def test_status_only_ticker_51_gets_a_details_row() -> None:
    """관리종목(51) 단독(VI 비활성·거래정지 아님) 종목도 details 행이 있어야 한다."""
    from src.routes.realtime import get_market_operation

    mom.record_market_op_event(
        _make_event("900010", iscd_stat_cls_code="51", mkop_cls_code="112")
    )

    resp = await get_market_operation()
    details = resp.data["details"]
    by_ticker = {row["ticker"]: row for row in details}

    assert "900010" in by_ticker, (
        "관리종목(51) 단독 종목이 details 에 없음 — 헤더 iscd_stat_active_count 보다 "
        f"행이 적다. details={details!r}"
    )
    row = by_ticker["900010"]
    assert row["iscd_stat"] == "51"
    assert row["halt_yn"] == "N"
    # 기존 VI/halt 행과 같은 필드 모양이어야 한다
    for field in (
        "ticker", "vi_code", "ovtm_vi_code", "halt_yn", "halt_reason",
        "iscd_stat", "mkop_cls_code", "exch_code", "received_at",
    ):
        assert field in row, f"details 필드 누락 — {field}"


@pytest.mark.asyncio
async def test_status_only_ticker_59_gets_a_details_row() -> None:
    """단기과열(59) 단독 종목도 details 행이 있어야 한다."""
    from src.routes.realtime import get_market_operation

    mom.record_market_op_event(
        _make_event("900020", iscd_stat_cls_code="59")
    )

    resp = await get_market_operation()
    by_ticker = {row["ticker"]: row for row in resp.data["details"]}
    assert "900020" in by_ticker, f"단기과열(59) 단독 종목 details 누락. {resp.data['details']!r}"
    assert by_ticker["900020"]["iscd_stat"] == "59"


@pytest.mark.asyncio
async def test_counts_unchanged_when_status_only_rows_added() -> None:
    """details 확장은 카운트(summary)를 바꾸지 않는다."""
    from src.routes.realtime import get_market_operation

    mom.record_market_op_event(_make_event("005930", vi_cls_code="1"))  # VI
    mom.record_market_op_event(
        _make_event("000020", trht_yn="Y", iscd_stat_cls_code="51")
    )  # halt(trht_yn) + iscd 51
    mom.record_market_op_event(
        _make_event("900010", iscd_stat_cls_code="51")
    )  # status-only(51)
    mom.record_market_op_event(
        _make_event("900030", iscd_stat_cls_code="55")
    )  # 신용가능(55) — 표시 집합 밖, details 무관

    resp = await get_market_operation()
    data = resp.data

    assert data["vi_active_count"] == 1
    assert data["halt_active_count"] == 1
    # iscd_stat_active_count = 표시 집합(51~54,58,59) 멤버십 — 000020·900010 두 건(51)
    assert data["iscd_stat_active_count"] == 2

    by_ticker = {row["ticker"]: row for row in data["details"]}
    assert set(by_ticker.keys()) == {"005930", "000020", "900010"}, (
        f"details 는 VI ∪ 거래정지 ∪ 종목상태(표시집합) 합집합이어야 한다. 실제: {sorted(by_ticker)!r}"
    )
    assert "900030" not in by_ticker, "55(신용가능)는 표시 집합 밖 — details 대상 아님"


@pytest.mark.asyncio
async def test_status_only_ticker_missing_last_event_is_impossible_but_graceful() -> None:
    """합집합 확장 후에도 기존 VI/halt 단독 케이스는 회귀 0 (cycle186 원 시나리오)."""
    from src.routes.realtime import get_market_operation

    mom.record_market_op_event(_make_event("005930", vi_cls_code="1"))

    resp = await get_market_operation()
    by_ticker = {row["ticker"]: row for row in resp.data["details"]}
    assert "005930" in by_ticker
    assert by_ticker["005930"]["vi_code"] == "1"
