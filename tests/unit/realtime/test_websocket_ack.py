"""WebSocket SUBSCRIBE SUCCESS ACK 추적 (G1, 2026-05-12).

배경: KIS REST/WebSocket 어디에도 슬롯 사용현황 조회 API 미존재. 운영자가
"지금 몇 개 구독이 실제 ACK 됐는가"를 알 수 없음. 우리가 발송한
`_subscriptions`(SEND 기준) 과 KIS 정상 응답 카운트를 분리 추적해 운영 가시화.

본 테스트는 다음 사양을 검증한다:

1. `KisWebSocket._subscriptions_acked: set[tuple[str, str]]` 신규 — KIS 정상 응답
   (`rt_cd=="0"` + `msg1` 에 "SUBSCRIBE SUCCESS" 포함) 만 add
2. `subscribe(tr_id, tr_key)` 호출 직후엔 ACK 비어있음 (응답 도착 전)
3. `connect()` 재연결 시 `_subscriptions_acked.clear()` — 모든 구독이 다시 ACK 받아야 함
4. E2 거절(`_is_rejection_response` True) → ACK add 안 됨, 기존 add 였으면 discard
5. `unsubscribe(tr_id, tr_key)` → ACK 에서 discard
6. `get_acked_tickers() -> set[str]` — TICK_TR_ID 필터링 (H0STCNI0/H0UNMKO0 제외)

안전 불변식: 기존 E2 거절 흐름 / AES iv/key 저장 흐름 / `_subscriptions` set 영향 없음.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock

import pytest

from src.realtime import websocket as websocket_module
from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _make_success_raw(tr_id: str, tr_key: str, *, msg1: str = "SUBSCRIBE SUCCESS") -> str:
    """KIS 정상 SUBSCRIBE SUCCESS 응답 raw."""
    return json.dumps({
        "header": {"tr_id": tr_id, "tr_key": tr_key},
        "body": {
            "rt_cd": "0",
            "msg_cd": "OPSP0000",
            "msg1": msg1,
            "output": {
                "iv": "0123456789abcdef",
                "key": "0123456789abcdef0123456789abcdef",
            },
        },
    })


def _make_reject_raw(tr_id: str, tr_key: str, *, rt_cd: str = "1", msg1: str = "중복 등록") -> str:
    return json.dumps({
        "header": {"tr_id": tr_id, "tr_key": tr_key},
        "body": {"rt_cd": rt_cd, "msg_cd": "OPSP0007", "msg1": msg1},
    })


@pytest.fixture(autouse=True)
def _silence_write_log(monkeypatch):
    """write_log 는 거절 분기 fire-and-forget. 테스트마다 AsyncMock 으로 swallow."""
    monkeypatch.setattr(websocket_module, "write_log", AsyncMock(return_value=None), raising=False)


@pytest.fixture
def _silence_set_aes(monkeypatch):
    """set_aes_keys 는 외부 handler 모듈 변경 — 테스트에서 spy 차단."""
    monkeypatch.setattr(websocket_module, "set_aes_keys", lambda iv, key: None)


# ---------------------------------------------------------------------------
# Case A — 정상 SUBSCRIBE SUCCESS → _subscriptions_acked 에 add + INFO 로그
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_a_subscribe_success_adds_to_acked_and_logs_info(
    _silence_set_aes, caplog
):
    ws = KisWebSocket()
    ws._subscriptions.add(("H0UNCNT0", "005930"))  # SEND 등록 가정

    raw = _make_success_raw("H0UNCNT0", "005930")
    with caplog.at_level(logging.INFO, logger="src.realtime.websocket"):
        await ws._handle_raw(raw)

    assert ("H0UNCNT0", "005930") in ws._subscriptions_acked, (
        "rt_cd=0 + msg1 'SUBSCRIBE SUCCESS' 면 _subscriptions_acked 에 add 되어야 함"
    )
    # 사이클 74 옵션 E-1: 직접 logger.info("WebSocket 구독 ACK: ...") 제거 → _record_action ACK 흡수
    # 직접 INFO 로그 0건 검증 + collector ACK 흡수 검증
    direct_ack_logs = [
        rec for rec in caplog.records
        if "WebSocket 구독 ACK:" in rec.getMessage() and rec.levelno == logging.INFO
    ]
    assert not direct_ack_logs, (
        f"사이클 74 G-7: SUBSCRIBE SUCCESS 직접 logger.info 0건 의무 — actual={direct_ack_logs}"
    )
    # collector 에 ACK 흡수 확인
    collector = getattr(ws, "_ws_action_collector", {})
    h0un = collector.get("H0UNCNT0", {})
    assert "005930" in h0un.get("ACK", []), (
        "사이클 74: collector ACK 005930 흡수 의무"
    )


# ---------------------------------------------------------------------------
# Case B — subscribe() 호출 직후엔 ACK 비어있음 (응답 도착 전)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_b_subscribe_call_does_not_pre_ack():
    ws = KisWebSocket()
    # _ws 는 None → send 안 함, set 등록만 확인
    await ws.subscribe("H0UNCNT0", "005930")

    assert ("H0UNCNT0", "005930") in ws._subscriptions, "SEND set 엔 등록"
    assert ("H0UNCNT0", "005930") not in ws._subscriptions_acked, (
        "응답 도착 전엔 _subscriptions_acked 에 없어야 함"
    )


# ---------------------------------------------------------------------------
# Case C — 재연결 시 _subscriptions_acked.clear() 호출됨
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_c_reconnect_clears_acked_set(monkeypatch):
    """connect() 가 기존 구독 복원 직전 _subscriptions_acked.clear() 호출.

    실제 connect 전체 흐름은 websockets.connect 외부 의존이라 모킹 부담이 큼.
    여기서는 구독 복원 로직이 ack set 클리어를 발화시키는지 단위 검증을 위해,
    내부 헬퍼 `_restore_subscriptions_and_clear_acked()` 가 존재하고 호출 시
    ack set 을 비우는지 확인한다. 헬퍼가 없으면 별도 함수로 추출 권장.

    헬퍼 미존재 시 fallback: connect() 가 자체적으로 clear 한다고 가정해
    `_subscriptions_acked.clear()` 가 retry 직전에 호출되어야 함을 명세로 검증.
    """
    ws = KisWebSocket()
    ws._subscriptions = {("H0UNCNT0", "005930"), ("H0UNCNT0", "000660")}
    ws._subscriptions_acked = {("H0UNCNT0", "005930"), ("H0UNCNT0", "000660")}

    # ws 연결되었다 가정 — _send_subscribe 모킹
    sent: list[tuple[str, str, bool]] = []

    async def _spy_send(tr_id, tr_key, *, subscribe):
        sent.append((tr_id, tr_key, subscribe))

    monkeypatch.setattr(ws, "_send_subscribe", _spy_send)

    # Green 구현이 노출할 헬퍼명 — `_restore_subscriptions()` 가 ack 클리어를 포함하도록
    # 강제. 헬퍼 미존재 시 AttributeError 로 즉시 Red.
    assert hasattr(ws, "_restore_subscriptions_after_reconnect"), (
        "_restore_subscriptions_after_reconnect 헬퍼 필요 — "
        "connect() 가 기존 구독 복원 직전 호출. ack set clear + 재send 책임 분리"
    )
    await ws._restore_subscriptions_after_reconnect()

    assert ws._subscriptions_acked == set(), (
        "재연결 시 _subscriptions_acked 는 비워져야 함 (모든 구독 다시 ACK 필요)"
    )
    # 기존 구독은 그대로 복원 send
    assert len(sent) == 2
    assert {(t[0], t[1]) for t in sent} == ws._subscriptions
    assert all(t[2] is True for t in sent)


# ---------------------------------------------------------------------------
# Case D — E2 거절 응답 → ACK add 안 됨, 기존 add 였으면 discard
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_d_rejection_discards_from_acked():
    ws = KisWebSocket()
    ws._subscriptions = {("H0UNCNT0", "005930")}
    # 이전 ACK 가 있었다고 가정 (재구독 후 거절 케이스)
    ws._subscriptions_acked = {("H0UNCNT0", "005930")}

    # N (2026-05-12) — "이미 등록"은 ALREADY 가드(거절 분기 *전*)에 흡수되므로
    # 진짜 거절 키워드("중복")로 본 케이스 재구성.
    raw = _make_reject_raw("H0UNCNT0", "005930", rt_cd="1", msg1="중복 등록된 종목")
    await ws._handle_raw(raw)

    # E2 동작: _subscriptions 에서도 discard
    assert ("H0UNCNT0", "005930") not in ws._subscriptions
    # G1 동작: _subscriptions_acked 에서도 discard
    assert ("H0UNCNT0", "005930") not in ws._subscriptions_acked, (
        "E2 거절 응답 시 _subscriptions_acked 에서도 discard 되어야 함"
    )


# ---------------------------------------------------------------------------
# Case E — unsubscribe() → ACK 에서 discard
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_e_unsubscribe_discards_from_acked():
    ws = KisWebSocket()
    ws._subscriptions = {("H0UNCNT0", "005930")}
    ws._subscriptions_acked = {("H0UNCNT0", "005930")}

    # _ws 는 None → send 안 함, set 갱신만 확인
    await ws.unsubscribe("H0UNCNT0", "005930")

    assert ("H0UNCNT0", "005930") not in ws._subscriptions
    assert ("H0UNCNT0", "005930") not in ws._subscriptions_acked, (
        "unsubscribe 호출 시 _subscriptions_acked 에서도 discard 되어야 함"
    )


# ---------------------------------------------------------------------------
# Case F — get_acked_tickers() TICK_TR_ID 필터 (H0STCNI0/H0UNMKO0 제외)
# ---------------------------------------------------------------------------
def test_case_f_get_acked_tickers_filters_tick_only():
    from src.engine.scanner import TICK_TR_ID

    ws = KisWebSocket()
    ws._subscriptions_acked = {
        (TICK_TR_ID, "005930"),
        (TICK_TR_ID, "000660"),
        ("H0STCNI0", "MYHTSID"),    # 체결통보 — 제외
        ("H0UNMKO0", "005930"),     # 장운영정보 — 제외
        (TICK_TR_ID, "035720"),
    }

    result = ws.get_acked_tickers()
    assert result == {"005930", "000660", "035720"}, (
        f"TICK_TR_ID acked 만 반환되어야 하지만 실제: {result}"
    )


# ---------------------------------------------------------------------------
# 추가 안전성 — subscribe() 호출 시 기존 acked entry 제거
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_subscribe_call_discards_stale_acked_entry():
    """동일 (tr_id, tr_key) 가 이미 ACK 됐는데 다시 subscribe 호출되면
    새 응답을 기다려야 하므로 ack 에서 제거되어야 함 (예: 재연결 외 명시적 재구독)."""
    ws = KisWebSocket()
    ws._subscriptions_acked.add(("H0UNCNT0", "005930"))

    await ws.subscribe("H0UNCNT0", "005930")

    assert ("H0UNCNT0", "005930") in ws._subscriptions
    assert ("H0UNCNT0", "005930") not in ws._subscriptions_acked, (
        "subscribe 호출 시 ack 에 남아있던 entry 는 제거 — 새 응답 대기"
    )
