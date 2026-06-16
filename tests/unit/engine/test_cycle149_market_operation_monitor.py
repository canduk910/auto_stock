"""사이클 149 (2026-06-16) — 영역 B 회귀 가드.

`src/engine/market_operation_monitor.py` 모듈 state + hook 검증.
- 3 dict (_vi_active_tickers + _halt_active_tickers + _market_op_last_event) 분리 영속
- record_market_op_event VI/거래정지 활성/해제 정합
- is_ticker_stale_excluded VI ∪ 거래정지 합집합 정합
- seed_vi_active_from_rest 부팅 폴백
- reset_market_op_state 일괄 clear

domain-expert 자문: `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md`
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from src.api.market_operation import MarketOpEvent
from src.engine import market_operation_monitor as mom


KST = timezone(timedelta(hours=9))


def _make_event(
    ticker: str = "005930",
    *,
    trht_yn: str = "N",
    vi_cls_code: str = "0",
    ovtm_vi_cls_code: str = "0",
    iscd_stat_cls_code: str = "0",
) -> MarketOpEvent:
    return MarketOpEvent(
        ticker=ticker, trht_yn=trht_yn,
        tr_susp_reas_cntt="",
        mkop_cls_code="110", antc_mkop_cls_code="110",
        mrkt_trtm_cls_code="0", divi_app_cls_code="0",
        iscd_stat_cls_code=iscd_stat_cls_code,
        vi_cls_code=vi_cls_code, ovtm_vi_cls_code=ovtm_vi_cls_code,
        exch_cls_code="KRX",
        received_at=datetime.now(KST),
    )


@pytest.fixture(autouse=True)
def _reset_state():
    mom.reset_market_op_state()
    yield
    mom.reset_market_op_state()


def test_G_B1_record_vi_active_adds_to_set() -> None:
    """HIGH — VI 활성 이벤트 수신 → `_vi_active_tickers` add."""
    event = _make_event("005930", vi_cls_code="1")
    mom.record_market_op_event(event)

    assert "005930" in mom.get_vi_active_tickers()


def test_G_B2_record_vi_release_discards_from_set() -> None:
    """HIGH — VI 해제 이벤트 수신 → discard."""
    mom.record_market_op_event(_make_event("005930", vi_cls_code="1"))
    assert "005930" in mom.get_vi_active_tickers()

    # VI 해제
    mom.record_market_op_event(_make_event("005930", vi_cls_code="0"))
    assert "005930" not in mom.get_vi_active_tickers()


def test_G_B3_record_halt_active_adds_to_set() -> None:
    """HIGH — 거래정지 활성 이벤트 → `_halt_active_tickers` add."""
    event = _make_event("000020", trht_yn="Y")
    mom.record_market_op_event(event)

    assert "000020" in mom.get_halt_active_tickers()


def test_G_B4_record_halt_release_discards_from_set() -> None:
    """HIGH — 거래정지 해제 이벤트 → discard."""
    mom.record_market_op_event(_make_event("000020", trht_yn="Y"))
    assert "000020" in mom.get_halt_active_tickers()

    mom.record_market_op_event(_make_event("000020", trht_yn="N"))
    assert "000020" not in mom.get_halt_active_tickers()


def test_G_B5_is_ticker_stale_excluded_vi_active_returns_true() -> None:
    """HIGH — VI 활성 ticker → True (stale 회피)."""
    mom.record_market_op_event(_make_event("005930", vi_cls_code="1"))

    assert mom.is_ticker_stale_excluded("005930") is True


def test_G_B6_is_ticker_stale_excluded_halt_active_returns_true() -> None:
    """HIGH — 거래정지 활성 ticker → True (stale 회피)."""
    mom.record_market_op_event(_make_event("000020", trht_yn="Y"))

    assert mom.is_ticker_stale_excluded("000020") is True


def test_G_B7_is_ticker_stale_excluded_normal_returns_false() -> None:
    """MEDIUM — 비활성 ticker → False (정상 stale 판정)."""
    mom.record_market_op_event(_make_event("005930", vi_cls_code="0", trht_yn="N"))

    assert mom.is_ticker_stale_excluded("005930") is False
    assert mom.is_ticker_stale_excluded("999999") is False  # 미수신 ticker


def test_G_B8_get_market_op_active_tickers_union() -> None:
    """MEDIUM — VI ∪ 거래정지 합집합 정확."""
    mom.record_market_op_event(_make_event("005930", vi_cls_code="1"))
    mom.record_market_op_event(_make_event("000020", trht_yn="Y"))
    mom.record_market_op_event(_make_event("000660", vi_cls_code="0", trht_yn="N"))

    active = mom.get_market_op_active_tickers()
    assert active == {"005930", "000020"}


def test_G_B9_seed_vi_active_from_rest_boot_fallback() -> None:
    """MEDIUM — 부팅 시점 REST 폴백 시드 (자문 의제 4)."""
    mom.seed_vi_active_from_rest({"005930", "000020"})

    assert mom.is_ticker_stale_excluded("005930") is True
    assert mom.is_ticker_stale_excluded("000020") is True


def test_G_B10_reset_market_op_state_clears_3_dicts() -> None:
    """MEDIUM — `_reset_daily_state` 동행 3 dict 일괄 clear."""
    mom.record_market_op_event(_make_event("005930", vi_cls_code="1"))
    mom.record_market_op_event(_make_event("000020", trht_yn="Y"))

    mom.reset_market_op_state()

    assert mom.get_vi_active_tickers() == set()
    assert mom.get_halt_active_tickers() == set()
    assert mom.get_last_event("005930") is None
    assert mom.get_last_event("000020") is None


def test_G_B11_last_event_dict_preserves_last_event() -> None:
    """MEDIUM — `_market_op_last_event` dict 마지막 이벤트 보존."""
    e1 = _make_event("005930", vi_cls_code="1")
    mom.record_market_op_event(e1)

    e2 = _make_event("005930", vi_cls_code="0")
    mom.record_market_op_event(e2)

    last = mom.get_last_event("005930")
    assert last is not None
    assert last.vi_cls_code == "0"  # 마지막 이벤트 영속
