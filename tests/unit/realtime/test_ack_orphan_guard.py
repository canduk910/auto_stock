"""사이클 14-C (2026-05-18) — `_subscriptions` 정합성 가드 (in-flight ACK race 차단).

배경 (운영 사고 2026-05-18 KST ~15:01):
- `GET /api/realtime/subscriptions` 응답에서 `sessions[main].subscribed=0 / acked=30` 격차 관찰.
- 원인 race: `_scan_loop` 5분 주기 `unsubscribe_all() → subscribe_filtered_stocks()` 흐름에서
  - T0: `subscribe(tr_id, tr_key)` → `_subscriptions.add` + `_send_subscribe(SEND)` (KIS 측 ACK in-flight)
  - T1: `unsubscribe(tr_id, tr_key)` → `_subscriptions.discard` + `_subscriptions_acked.discard` (정상)
  - T2: KIS 가 T0 SEND 에 대한 SUBSCRIBE SUCCESS ACK 응답 (지연 도착)
  - T3: `_handle_raw` → 기존 코드: 무조건 `_subscriptions_acked.add` → **격차 발생**
- 누적 race 가 `_subscriptions=0 / _acked=N` 격차로 노출. KIS 측은 unsubscribe 처리, 우리 측 ACK 만 stale.

fix: `_handle_raw` SUBSCRIBE SUCCESS 분기에서 `(tr_id, tr_key) in self._subscriptions` 가드 추가.
- in-flight ACK race → `_subscriptions` 부재 → acked.add 무시 (orphan ACK 차단)
- 정상 SUBSCRIBE 흐름 (먼저 subscribe → ACK) → `_subscriptions` 존재 → acked.add 보존

3 케이스:
1. orphan ACK 차단 — `_subscriptions` 에 없는 ACK 는 `_subscriptions_acked` 에 add 안 됨
2. 정상 ACK 보존 — `_subscriptions` 에 있는 ACK 는 정상 add
3. orphan ACK 도 AES iv/key 저장은 보존 — race 와 무관한 별도 분기
"""

from __future__ import annotations

import json

import pytest

from src.realtime import websocket as websocket_module
from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


def _make_subscribe_success_raw(tr_id: str, tr_key: str, iv: str = "", key: str = "") -> str:
    """SUBSCRIBE SUCCESS raw — 선택적 AES iv/key output 포함."""
    body = {
        "rt_cd": "0",
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS",
    }
    if iv and key:
        body["output"] = {"iv": iv, "key": key}
    return json.dumps({
        "header": {"tr_id": tr_id, "tr_key": tr_key},
        "body": body,
    })


# ===========================================================================
# Case 1 — orphan ACK 차단: _subscriptions 부재 → acked.add 무시
# ===========================================================================
@pytest.mark.asyncio
async def test_subscribe_success_orphan_ack_does_not_add_to_acked():
    """`_subscriptions` 에 없는 (tr_id, tr_key) 의 SUBSCRIBE SUCCESS 응답은
    `_subscriptions_acked` 에 add 되지 않아야 한다 (in-flight race 차단).
    """
    ws = KisWebSocket()
    # _subscriptions 에 등록 안 함 (unsubscribe 직후 또는 race 상태 재현)
    assert ("H0UNCNT0", "005930") not in ws._subscriptions

    raw = _make_subscribe_success_raw("H0UNCNT0", "005930")
    await ws._handle_raw(raw)

    assert ("H0UNCNT0", "005930") not in ws._subscriptions_acked, (
        "사이클 14-C: orphan ACK (subscriptions 부재) 는 acked 에 add 안 됨. "
        f"실제 acked={ws._subscriptions_acked}"
    )


# ===========================================================================
# Case 2 — 정상 ACK 보존: _subscriptions 존재 → acked.add 정상
# ===========================================================================
@pytest.mark.asyncio
async def test_subscribe_success_normal_flow_adds_acked():
    """정상 흐름 — `subscribe()` 호출 후 ACK 도착 → `_subscriptions_acked` 에 정상 add."""
    ws = KisWebSocket()
    # subscribe 가 add 한 것처럼 시뮬레이션
    ws._subscriptions.add(("H0UNCNT0", "000660"))
    assert ("H0UNCNT0", "000660") not in ws._subscriptions_acked

    raw = _make_subscribe_success_raw("H0UNCNT0", "000660")
    await ws._handle_raw(raw)

    assert ("H0UNCNT0", "000660") in ws._subscriptions_acked, (
        "정상 흐름 — _subscriptions 에 있으면 ACK 정상 add. "
        f"실제 acked={ws._subscriptions_acked}"
    )


# ===========================================================================
# Case 3 — orphan ACK 도 AES iv/key 저장은 보존 (별도 분기)
# ===========================================================================
@pytest.mark.asyncio
async def test_subscribe_success_orphan_preserves_aes_keys(monkeypatch):
    """orphan ACK 시 acked.add 는 차단되지만, AES iv/key 저장은 보존되어야 한다.

    체결통보 H0STCNI0 응답이 in-flight 로 도착하는 race 케이스도 AES 키 저장
    경로(line 417-423)는 정합성 가드와 무관 — 키는 단일 글로벌이라 정합성 영향 0.
    """
    set_aes_calls: list[tuple[str, str]] = []

    def _spy_set_aes_keys(iv: str, key: str) -> None:
        set_aes_calls.append((iv, key))

    monkeypatch.setattr(websocket_module, "set_aes_keys", _spy_set_aes_keys)

    ws = KisWebSocket()
    # H0STCNI0 체결통보 — _subscriptions 에 등록 안 한 상태 (orphan ACK 재현)
    assert ("H0STCNI0", "HTSID01") not in ws._subscriptions

    raw = _make_subscribe_success_raw(
        "H0STCNI0", "HTSID01",
        iv="0123456789abcdef",
        key="0123456789abcdef0123456789abcdef",
    )
    await ws._handle_raw(raw)

    # ACK 는 차단
    assert ("H0STCNI0", "HTSID01") not in ws._subscriptions_acked
    # AES 키는 저장 보존 (별도 분기)
    assert ws.aes_iv == "0123456789abcdef"
    assert ws.aes_key == "0123456789abcdef0123456789abcdef"
    assert set_aes_calls == [(
        "0123456789abcdef",
        "0123456789abcdef0123456789abcdef",
    )]
