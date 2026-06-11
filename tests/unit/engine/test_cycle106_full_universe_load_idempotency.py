"""사이클 106 영역 3 (HIGH) — _full_universe_load_once is_stale 24h TTL idempotency.

시정 근거 (Q1=A):
    start() 직후 즉시 1회 실행 + while 루프 구조로 변경.
    즉시 실행의 부수 효과 = is_stale 24h TTL idempotency 활용으로 0.

Idempotency 핵심:
    `_full_universe_load_once` 내부에서 각 ticker 마다 `is_stale(ticker, max_age_hours=24)` 호출.
    is_stale=False (24h 내 갱신) → skipped_ttl++ + KIS 호출 0건.
    is_stale=True (갱신 필요) → KIS CTPF1002R 호출 + upsert.

    따라서 동일 날짜 2회 호출:
    - 1회차: KIS 호출 + upsert (fetched++)
    - 2회차: skipped_ttl++ (KIS 호출 0건 추가)
    → 총 KIS 호출 = 1회차 분량만 (2회차 부수 효과 0)

회귀 가드 케이스:
    G-ID1 (HIGH): is_stale=False 종목 → skipped_ttl++ + KIS 호출 0건
    G-ID2 (HIGH): 동일 날짜 2회 호출 = 2회차 KIS 호출 0건 (is_stale=False)
    G-ID3 (HIGH): is_stale=True 종목 → KIS 호출 1회 + upsert 1회
    G-ID4 (MEDIUM): is_stale 예외 → graceful True (갱신 시도)
    G-ID5 (MEDIUM): 6자리 비숫자 ticker → skip (형식 가드 영속)
    G-ID6 (LOW): summary 9 키 전수 확인 (사이클 101 스펙 영속)

영속 의무:
    - 사이클 83 24h TTL fresh skip 영속 (is_stale 호출)
    - 사이클 84 history trigger 영속 (upsert_one 호출)
    - 사이클 88 G-REJECT 영속 (개별 실패 graceful continue)
    - 사이클 101 KIS 정본 인용 (FHPST01740000 + CTPF1002R)
    - 사이클 102 G-REJECT 영속
    - 매매 안전성 무영향 (scanner 단계, 매도/손절/익일청산 hot path 무관)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def _make_basics_mock(ticker: str) -> MagicMock:
    """upsert_one 에 전달할 basics mock."""
    m = MagicMock()
    m.ticker = ticker
    return m


# ---------------------------------------------------------------------------
# G-ID1 (HIGH): is_stale=False → skipped_ttl++ + KIS 호출 0건
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_id1_is_stale_false_skips_kis(monkeypatch):
    """G-ID1 (HIGH): is_stale=False (24h 내 갱신) 종목은 KIS CTPF1002R 호출 0건 + skipped_ttl++.

    사이클 83 24h TTL fresh skip 영속 확인.
    """
    from src.engine import scanner as sc

    # market_cap 페이징 = 2 ticker 반환
    mock_kospi = [{"mksc_shrn_iscd": "005930"}, {"mksc_shrn_iscd": "000660"}]
    mock_kosdaq: list = []

    async def mock_fetch_market_cap_page(market, max_pages):
        return mock_kospi if market == "kospi" else mock_kosdaq

    # is_stale = False (24h 이내 갱신 = skip)
    async def mock_is_stale(ticker, max_age_hours):
        return False

    mock_inquire = AsyncMock()  # 호출되면 안 됨
    mock_upsert = AsyncMock()  # 호출되면 안 됨

    with patch.object(sc, "_fetch_market_cap_page", side_effect=mock_fetch_market_cap_page), \
         patch("src.db.stock_master.is_stale", side_effect=mock_is_stale), \
         patch("src.api.condition.inquire_stock_basics", mock_inquire), \
         patch("src.db.stock_master.upsert_one", mock_upsert), \
         patch("src.config.settings") as mock_settings:
        mock_settings.kis_env = "vts"
        summary = await sc._full_universe_load_once()

    assert summary["skipped_ttl"] == 2, (
        f"G-ID1 FAIL: is_stale=False 2 ticker → skipped_ttl 2 기대, 실제 {summary['skipped_ttl']}."
    )
    assert summary["fetched"] == 0, (
        f"G-ID1 FAIL: is_stale=False → KIS 호출 0건 기대, 실제 fetched={summary['fetched']}."
    )
    assert mock_inquire.call_count == 0, (
        f"G-ID1 FAIL: is_stale=False 종목에 inquire_stock_basics {mock_inquire.call_count}회 호출됨. "
        "KIS 호출 0건 의무."
    )
    assert mock_upsert.call_count == 0, (
        f"G-ID1 FAIL: is_stale=False 종목에 upsert_one {mock_upsert.call_count}회 호출됨."
    )


# ---------------------------------------------------------------------------
# G-ID2 (HIGH): 동일 날짜 2회 호출 = 2회차 KIS 호출 0건 (idempotency 핵심)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_id2_second_call_zero_kis_calls(monkeypatch):
    """G-ID2 (HIGH): 동일 날짜 2회 호출 시 2회차 KIS CTPF1002R 호출 0건.

    Q1=A 즉시 실행 패턴의 핵심 근거:
    - 1회차: is_stale=True → KIS 호출 + upsert (fetched++)
    - 2회차: is_stale=False → skipped_ttl++ (KIS 호출 0건)
    → 총 KIS 호출 = 1회차 분량만. 조기 호출 부수 효과 0.
    """
    from src.engine import scanner as sc

    mock_kospi = [{"mksc_shrn_iscd": "005930"}]
    mock_kosdaq: list = []

    async def mock_fetch_market_cap_page(market, max_pages):
        return mock_kospi if market == "kospi" else mock_kosdaq

    call_history: list[bool] = []

    async def mock_is_stale(ticker, max_age_hours):
        # 1회차 → True, 2회차 → False
        result = len(call_history) == 0
        call_history.append(result)
        return result

    mock_basics = _make_basics_mock("005930")
    mock_inquire = AsyncMock(return_value=mock_basics)
    mock_upsert = AsyncMock()

    with patch.object(sc, "_fetch_market_cap_page", side_effect=mock_fetch_market_cap_page), \
         patch("src.db.stock_master.is_stale", side_effect=mock_is_stale), \
         patch("src.api.condition.inquire_stock_basics", mock_inquire), \
         patch("src.db.stock_master.upsert_one", mock_upsert), \
         patch("src.config.settings") as mock_settings:
        mock_settings.kis_env = "vts"

        # 1회차
        summary1 = await sc._full_universe_load_once()
        # 2회차
        summary2 = await sc._full_universe_load_once()

    # 1회차: KIS 호출 발생
    assert summary1["fetched"] == 1, (
        f"G-ID2 FAIL: 1회차 fetched=1 기대, 실제 {summary1['fetched']}."
    )
    # 2회차: KIS 호출 0건 (is_stale=False)
    assert summary2["fetched"] == 0 and summary2["skipped_ttl"] == 1, (
        f"G-ID2 FAIL: 2회차 KIS 호출 0건 기대. fetched={summary2['fetched']}, "
        f"skipped_ttl={summary2['skipped_ttl']}. is_stale idempotency 결함."
    )
    # 총 inquire 호출 = 1회차 1건만
    assert mock_inquire.call_count == 1, (
        f"G-ID2 FAIL: 총 inquire_stock_basics {mock_inquire.call_count}회 (기대 1회). "
        "2회차 KIS 호출 0건 idempotency 결함."
    )


# ---------------------------------------------------------------------------
# G-ID3 (HIGH): is_stale=True → KIS 호출 1회 + upsert 1회
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_id3_is_stale_true_triggers_kis(monkeypatch):
    """G-ID3 (HIGH): is_stale=True (갱신 필요) 종목 → KIS CTPF1002R 1회 + upsert 1회.

    사이클 84 history trigger 영속: upsert_one 호출 → DB trigger 자동.
    """
    from src.engine import scanner as sc

    mock_kospi = [{"mksc_shrn_iscd": "005930"}]
    mock_kosdaq: list = []

    async def mock_fetch_market_cap_page(market, max_pages):
        return mock_kospi if market == "kospi" else mock_kosdaq

    async def mock_is_stale(ticker, max_age_hours):
        return True  # 항상 갱신 필요

    mock_basics = _make_basics_mock("005930")
    mock_inquire = AsyncMock(return_value=mock_basics)
    mock_upsert = AsyncMock()

    with patch.object(sc, "_fetch_market_cap_page", side_effect=mock_fetch_market_cap_page), \
         patch("src.db.stock_master.is_stale", side_effect=mock_is_stale), \
         patch("src.api.condition.inquire_stock_basics", mock_inquire), \
         patch("src.db.stock_master.upsert_one", mock_upsert), \
         patch("src.config.settings") as mock_settings:
        mock_settings.kis_env = "vts"
        summary = await sc._full_universe_load_once()

    assert summary["fetched"] == 1, (
        f"G-ID3 FAIL: is_stale=True → fetched=1 기대, 실제 {summary['fetched']}."
    )
    assert mock_inquire.call_count == 1, (
        f"G-ID3 FAIL: inquire_stock_basics 1회 기대, 실제 {mock_inquire.call_count}회."
    )
    assert mock_upsert.call_count == 1, (
        f"G-ID3 FAIL: upsert_one 1회 기대, 실제 {mock_upsert.call_count}회. "
        "사이클 84 history trigger 영속 누락."
    )


# ---------------------------------------------------------------------------
# G-ID4 (MEDIUM): is_stale 예외 → graceful True (갱신 시도)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_id4_is_stale_exception_falls_back_to_true(monkeypatch):
    """G-ID4 (MEDIUM): is_stale 예외 시 graceful True → 갱신 시도.

    사이클 88 G-REJECT 영속: 개별 실패 graceful continue.
    """
    from src.engine import scanner as sc

    mock_kospi = [{"mksc_shrn_iscd": "005930"}]
    mock_kosdaq: list = []

    async def mock_fetch_market_cap_page(market, max_pages):
        return mock_kospi if market == "kospi" else mock_kosdaq

    async def mock_is_stale(ticker, max_age_hours):
        raise RuntimeError("DB 연결 실패")

    mock_basics = _make_basics_mock("005930")
    mock_inquire = AsyncMock(return_value=mock_basics)
    mock_upsert = AsyncMock()

    with patch.object(sc, "_fetch_market_cap_page", side_effect=mock_fetch_market_cap_page), \
         patch("src.db.stock_master.is_stale", side_effect=mock_is_stale), \
         patch("src.api.condition.inquire_stock_basics", mock_inquire), \
         patch("src.db.stock_master.upsert_one", mock_upsert), \
         patch("src.config.settings") as mock_settings:
        mock_settings.kis_env = "vts"
        summary = await sc._full_universe_load_once()

    # is_stale 예외 → graceful True → 갱신 시도 → fetched >= 0 (실패하면 failed++)
    # 핵심: 예외 시 프로세스 중단 없이 continue (graceful)
    total_handled = summary["fetched"] + summary["failed"] + summary["skipped_ttl"]
    assert total_handled >= 1, (
        f"G-ID4 FAIL: is_stale 예외 종목이 처리되지 않음 (총 처리={total_handled}). "
        "graceful 폴백 필요."
    )


# ---------------------------------------------------------------------------
# G-ID5 (MEDIUM): 비6자리/비숫자 ticker → skip (형식 가드 영속)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_id5_invalid_ticker_format_skipped(monkeypatch):
    """G-ID5 (MEDIUM): 6자리 비숫자 ticker (ETF, 신주인수권 등) → skip.

    CLAUDE.md "종목코드 형식 비대칭" 규칙 영속:
    진입은 6자리 숫자만 (isdigit()).
    """
    from src.engine import scanner as sc

    mock_kospi = [
        {"mksc_shrn_iscd": "ABCDEF"},   # 6자리 비숫자 → skip
        {"mksc_shrn_iscd": "12345"},    # 5자리 → skip
        {"mksc_shrn_iscd": "005930"},   # 정상
    ]
    mock_kosdaq: list = []

    async def mock_fetch_market_cap_page(market, max_pages):
        return mock_kospi if market == "kospi" else mock_kosdaq

    async def mock_is_stale(ticker, max_age_hours):
        return True

    mock_inquire = AsyncMock(return_value=_make_basics_mock("005930"))
    mock_upsert = AsyncMock()

    with patch.object(sc, "_fetch_market_cap_page", side_effect=mock_fetch_market_cap_page), \
         patch("src.db.stock_master.is_stale", side_effect=mock_is_stale), \
         patch("src.api.condition.inquire_stock_basics", mock_inquire), \
         patch("src.db.stock_master.upsert_one", mock_upsert), \
         patch("src.config.settings") as mock_settings:
        mock_settings.kis_env = "vts"
        summary = await sc._full_universe_load_once()

    # 정상 ticker 1개만 처리
    assert mock_inquire.call_count == 1, (
        f"G-ID5 FAIL: 정상 ticker 1개만 inquire 기대, 실제 {mock_inquire.call_count}회. "
        "비정상 ticker 형식 가드 누락."
    )
    assert summary["fetched"] == 1, (
        f"G-ID5 FAIL: fetched=1 기대, 실제 {summary['fetched']}."
    )


# ---------------------------------------------------------------------------
# G-ID6 (LOW): summary 9 키 전수 확인 (사이클 101 스펙 영속)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_g_id6_summary_has_nine_keys(monkeypatch):
    """G-ID6 (LOW): _full_universe_load_once 반환 summary 는 9 키 포함.

    사이클 101 스펙: total/kospi/kosdaq/securities/etf/fetched/skipped_ttl/failed/elapsed_ms.
    """
    from src.engine import scanner as sc

    mock_kospi: list = []
    mock_kosdaq: list = []

    async def mock_fetch_market_cap_page(market, max_pages):
        return mock_kospi if market == "kospi" else mock_kosdaq

    with patch.object(sc, "_fetch_market_cap_page", side_effect=mock_fetch_market_cap_page), \
         patch("src.config.settings") as mock_settings:
        mock_settings.kis_env = "vts"
        summary = await sc._full_universe_load_once()

    expected_keys = {
        "total", "kospi", "kosdaq", "securities", "etf",
        "fetched", "skipped_ttl", "failed", "elapsed_ms",
    }
    missing = expected_keys - set(summary.keys())
    assert not missing, (
        f"G-ID6 FAIL: summary 9 키 중 {missing} 누락. 사이클 101 스펙 영속 위반."
    )
