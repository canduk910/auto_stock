"""사이클 149 (2026-06-16) — 영역 A 회귀 가드.

API 모듈 `src/api/market_operation.py` 정본 검증.
- MARKET_OP_TR_ID == "H0UNMKO0" + 10 컬럼 정확 파싱
- is_event_blocking truthy 매핑 (의제 1 자문 채택)

domain-expert 자문: `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md`
"""

from __future__ import annotations

import pytest

from src.api.market_operation import (
    MARKET_OP_TR_ID,
    MarketOpEvent,
    is_event_blocking,
    parse_market_op_payload,
)


def test_G_A1_market_op_tr_id_and_payload_parsing() -> None:
    """MARKET_OP_TR_ID == "H0UNMKO0" + 10 컬럼 정확 추출.

    KIS 공식 H0UNMKO0 응답 정본 (사이클 26 영속 + 사이클 149 종목별 영역 확장).
    """
    # 사이클 26 영속 + KIS MCP 정본 영구 영속
    assert MARKET_OP_TR_ID == "H0UNMKO0"

    # 10 컬럼 `^` 구분 payload 정본 (정상 거래 종목)
    payload = "N^^110^110^0^0^0^0^0^KRX"
    event = parse_market_op_payload("005930", payload)

    assert event.ticker == "005930"
    assert event.trht_yn == "N"
    assert event.tr_susp_reas_cntt == ""
    assert event.mkop_cls_code == "110"
    assert event.antc_mkop_cls_code == "110"
    assert event.mrkt_trtm_cls_code == "0"
    assert event.divi_app_cls_code == "0"
    assert event.iscd_stat_cls_code == "0"
    assert event.vi_cls_code == "0"
    assert event.ovtm_vi_cls_code == "0"
    assert event.exch_cls_code == "KRX"


@pytest.mark.parametrize(
    "trht_yn, vi_cls_code, ovtm_vi_cls_code, iscd_stat_cls_code, expected_blocking",
    [
        # 정상 거래 종목 (의제 1 자문 채택 — "0"/"" = 비활성 블랙리스트)
        ("N", "0", "0", "0", False),
        ("N", "", "", "", False),
        ("", "", "", "", False),
        # 거래정지 활성 (TRHT_YN == "Y")
        ("Y", "0", "0", "0", True),
        # VI 활성 (정적 = "1")
        ("N", "1", "0", "0", True),
        # 시간외 VI 활성
        ("N", "0", "1", "0", True),
        # 종목상태 이상 (의제 5 자문 채택)
        ("N", "0", "0", "1", True),
        # KIS 향후 확장 호환 (의제 1 truthy 매핑) — "2"/"3" 등 = 활성
        ("N", "2", "0", "0", True),
        ("N", "0", "3", "0", True),
    ],
)
def test_G_A2_is_event_blocking_truthy_mapping(
    trht_yn: str, vi_cls_code: str, ovtm_vi_cls_code: str,
    iscd_stat_cls_code: str, expected_blocking: bool,
) -> None:
    """is_event_blocking 의제 1 truthy 매핑 영속 (자문 채택).

    "0"/"" = 비활성 블랙리스트, 그 외 모두 = 활성.
    """
    from datetime import datetime, timezone, timedelta

    event = MarketOpEvent(
        ticker="005930", trht_yn=trht_yn,
        tr_susp_reas_cntt="",
        mkop_cls_code="110", antc_mkop_cls_code="110",
        mrkt_trtm_cls_code="0", divi_app_cls_code="0",
        iscd_stat_cls_code=iscd_stat_cls_code,
        vi_cls_code=vi_cls_code, ovtm_vi_cls_code=ovtm_vi_cls_code,
        exch_cls_code="KRX",
        received_at=datetime.now(timezone(timedelta(hours=9))),
    )
    assert is_event_blocking(event) is expected_blocking
