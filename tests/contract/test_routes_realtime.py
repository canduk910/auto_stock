"""realtime 라우트 계약 테스트 — /api/realtime/subscriptions (G2, 2026-05-12).

KIS REST/WS 어디에도 슬롯 사용현황 조회 API 미존재. 우리 측 진단 endpoint 노출.

응답 스키마 (ApiResponse 래퍼):
{
  "success": true,
  "data": {
    "total": int,            # _subscriptions TICK 필터 size (SEND 기준)
    "acked": int,            # _subscriptions_acked TICK 필터 size (KIS 응답 기준)
    "fresh_60s": int,        # 최근 60초 내 tick 수신
    "stale_60s": int,        # 60초 미수신
    "limit": int,            # MAX_SUBSCRIPTIONS (41)
    "tickers": {
      "subscribed": [str],   # _subscriptions, sorted
      "acked":      [str],   # _subscriptions_acked, sorted
      "fresh":      [str],   # fresh tickers, sorted
      "stale":      [str],   # stale tickers, sorted
    },
    "reconnect_count": int,
    "ws_connected": bool,
  },
  "message": str,
}
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.contract


KST = timezone(timedelta(hours=9))


def _assert_envelope(body: dict) -> None:
    assert set(body.keys()) >= {"success", "data", "message"}
    assert isinstance(body["success"], bool)


@pytest.fixture
def patched_kis_ws(monkeypatch):
    """kis_ws 싱글톤 상태 초기화 — 테스트마다 독립."""
    from src.realtime.websocket import kis_ws

    # 사전 상태 백업
    orig_subs = set(kis_ws._subscriptions)
    orig_acked = set(getattr(kis_ws, "_subscriptions_acked", set()))
    orig_ws = kis_ws._ws
    orig_reconnect = kis_ws._reconnect_count

    kis_ws._subscriptions = set()
    # Green 구현이 _subscriptions_acked 를 추가하면 그 set 도 초기화
    if not hasattr(kis_ws, "_subscriptions_acked"):
        kis_ws._subscriptions_acked = set()
    else:
        kis_ws._subscriptions_acked.clear()
    kis_ws._ws = None
    kis_ws._reconnect_count = 0

    yield kis_ws

    # 복원
    kis_ws._subscriptions = orig_subs
    kis_ws._subscriptions_acked = orig_acked
    kis_ws._ws = orig_ws
    kis_ws._reconnect_count = orig_reconnect


@pytest.fixture(autouse=True)
def _reset_ticker_last_tick():
    from src.engine import scanner as scanner_module

    scanner_module.ticker_last_tick.clear()
    yield
    scanner_module.ticker_last_tick.clear()


# ---------------------------------------------------------------------------
# Case G — 응답 스키마 매칭 (8개 top-level 키 + 4개 tickers 하위 키)
# ---------------------------------------------------------------------------
def test_case_g_response_schema_matches(contract_env, patched_kis_ws):
    from src.engine.scanner import TICK_TR_ID

    now = datetime.now(KST)
    # 3종목 구독 + 2종목 acked + 1종목 fresh
    patched_kis_ws._subscriptions = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
        (TICK_TR_ID, "035720"),
    }
    patched_kis_ws._subscriptions_acked = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
    }
    from src.engine import scanner as scanner_module
    scanner_module.ticker_last_tick["005930"] = now - timedelta(seconds=10)  # fresh

    r = contract_env.client.get("/api/realtime/subscriptions")
    assert r.status_code == 200
    body = r.json()
    _assert_envelope(body)
    assert body["success"] is True

    data = body["data"]
    top_keys = {"total", "acked", "fresh_60s", "stale_60s", "limit",
                "tickers", "reconnect_count", "ws_connected"}
    assert set(data.keys()) >= top_keys, (
        f"top-level 키 누락. expected superset of {top_keys}, got {set(data.keys())}"
    )

    tickers = data["tickers"]
    assert isinstance(tickers, dict)
    assert {"subscribed", "acked", "fresh", "stale"} <= set(tickers.keys()), (
        f"tickers 하위 키 누락: {set(tickers.keys())}"
    )

    # 값 검증
    assert data["total"] == 3
    assert data["acked"] == 2
    assert data["fresh_60s"] == 1
    assert data["stale_60s"] == 2
    assert data["limit"] == 41  # MAX_SUBSCRIPTIONS
    assert isinstance(data["reconnect_count"], int)
    assert isinstance(data["ws_connected"], bool)


# ---------------------------------------------------------------------------
# Case H — tickers 리스트 정렬 검증
# ---------------------------------------------------------------------------
def test_case_h_tickers_lists_are_sorted(contract_env, patched_kis_ws):
    from src.engine.scanner import TICK_TR_ID

    now = datetime.now(KST)
    # 의도적으로 sorted 와 다른 set 순서로 등록
    patched_kis_ws._subscriptions = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
        (TICK_TR_ID, "035720"),
    }
    patched_kis_ws._subscriptions_acked = {
        (TICK_TR_ID, "035720"),
        (TICK_TR_ID, "005930"),
    }
    from src.engine import scanner as scanner_module
    scanner_module.ticker_last_tick["035720"] = now - timedelta(seconds=5)   # fresh
    scanner_module.ticker_last_tick["005930"] = now - timedelta(seconds=120)  # stale (>60s)

    r = contract_env.client.get("/api/realtime/subscriptions")
    assert r.status_code == 200
    data = r.json()["data"]

    assert data["tickers"]["subscribed"] == ["000660", "005930", "035720"], (
        "subscribed 리스트는 sorted 되어야 함"
    )
    assert data["tickers"]["acked"] == ["005930", "035720"]
    assert data["tickers"]["fresh"] == ["035720"]
    # 000660 (ticker_last_tick 없음 → stale) + 005930 (>60s)
    assert data["tickers"]["stale"] == ["000660", "005930"]


# ---------------------------------------------------------------------------
# Case I — ws_connected=False 도 200 + 카운트 정상
# ---------------------------------------------------------------------------
def test_case_i_ws_disconnected_still_returns_counts(contract_env, patched_kis_ws):
    from src.engine.scanner import TICK_TR_ID

    patched_kis_ws._ws = None  # 연결 끊김
    patched_kis_ws._reconnect_count = 3
    patched_kis_ws._subscriptions = {(TICK_TR_ID, "005930")}
    patched_kis_ws._subscriptions_acked = set()

    r = contract_env.client.get("/api/realtime/subscriptions")
    assert r.status_code == 200
    data = r.json()["data"]

    assert data["ws_connected"] is False
    assert data["reconnect_count"] == 3
    assert data["total"] == 1
    assert data["acked"] == 0
    assert data["fresh_60s"] == 0
    assert data["stale_60s"] == 1
    assert data["tickers"]["subscribed"] == ["005930"]
    assert data["tickers"]["acked"] == []
    assert data["tickers"]["stale"] == ["005930"]
