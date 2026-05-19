"""사이클 17 보강 (2026-05-19) — OPSP0002 ALREADY IN SUBSCRIBE backoff 가드 (300s).

배경: 2026-05-19 15:15 KST tick_coverage ratio=0.0% 운영 결함. KIS 측
``OPSP0002 ALREADY IN SUBSCRIBE`` 응답을 받아도 다음 `_scan_loop` 사이클이
같은 종목을 즉시 재구독 → 또 OPSP0002 → 무한 루프. KIS WS Rate Limit + 위양성
폭증. 단순 차단: ``(tr_id, tr_key)`` 별 backoff 등록 → ``subscribe`` 진입 시
``time.time() < until`` 이면 send skip.

사이클 17 본체: 60s backoff.
사이클 17 보강 (2026-05-19): KIS 공식 답변 ("기등록한 사항을 재등록하지 않도록") 반영
60s → 300s. `_scan_loop` 5분 주기 ≥ backoff 만료 보장 → 같은 사이클 내 재시도 차단.

배치:
- `__init__`: ``self._opsp_backoff_until: dict[tuple[str, str], float] = {}``
- `_handle_raw` OPSP0002 분기: ``self._opsp_backoff_until[(tr_id, tr_key)] = time.time() + 300.0``
- `subscribe(tr_id, tr_key)`: ``if not bypass_limit and time.time() < self._opsp_backoff_until.get(key, 0.0)`` 면 send skip + DEBUG `[ws_subscribe_backoff]`

bypass_limit=True (HIGH 우선순위 보유/익일청산) 는 backoff 검사 skip — 보유
종목 손절 우선 보장.

5 케이스:
(A) `_handle_raw` OPSP0002 → `_opsp_backoff_until` 등록 + 값 ≈ now + 300.0
(B) `subscribe()` 진입 시 backoff 유효 → send skip
(C) 300.001s 경과 후 정상 subscribe (send 호출)
(D) 다른 종목 backoff 영향 0 (key tuple 격리)
(E) 정상 SUBSCRIBE SUCCESS (rt_cd=0) → backoff 진입 안 함

안전 가드:
- `_subscriptions` set 직접 수정 금지 — backoff 검사 후 send 만 skip
- `bypass_limit=True` 는 backoff 검사 skip (HIGH 보유 보장)
- 300s 만료 후 자연 복귀 — manual reset 불필요
"""
from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock

import pytest

from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


def _make_opsp0002_raw(tr_id: str, tr_key: str) -> str:
    """OPSP0002 ALREADY IN SUBSCRIBE 응답 JSON."""
    return json.dumps({
        "header": {"tr_id": tr_id, "tr_key": tr_key},
        "body": {
            "rt_cd": "1",
            "msg_cd": "OPSP0002",
            "msg1": "ALREADY IN SUBSCRIBE",
        },
    })


def _make_subscribe_success_raw(tr_id: str, tr_key: str) -> str:
    """정상 SUBSCRIBE SUCCESS 응답 JSON."""
    return json.dumps({
        "header": {"tr_id": tr_id, "tr_key": tr_key},
        "body": {
            "rt_cd": "0",
            "msg_cd": "OPSP0000",
            "msg1": "SUBSCRIBE SUCCESS",
            "output": {"iv": "iv_x", "key": "key_x"},
        },
    })


# ===========================================================================
# Case A — _handle_raw OPSP0002 → _opsp_backoff_until 등록 + 값 ≈ now + 300.0
# ===========================================================================
@pytest.mark.asyncio
async def test_opsp0002_registers_backoff_300s():
    """OPSP0002 응답 수신 시 `(tr_id, tr_key)` 가 backoff 사전에 등록되고 값은 now + 300.0.

    사이클 17 보강 (2026-05-19) — KIS 공식 답변 반영 60s → 300s.
    `_scan_loop` 5분 주기 ≥ backoff 만료 보장.
    """
    ws = KisWebSocket()
    # backoff 사전이 init 시점 빈 dict
    assert ws._opsp_backoff_until == {}

    raw = _make_opsp0002_raw("H0UNCNT0", "005930")
    before = time.time()
    await ws._handle_raw(raw)
    after = time.time()

    key = ("H0UNCNT0", "005930")
    assert key in ws._opsp_backoff_until, (
        f"OPSP0002 후 _opsp_backoff_until 미등록: 실제={ws._opsp_backoff_until}"
    )
    until = ws._opsp_backoff_until[key]
    # 300s ± 약간 (테스트 환경 jitter 흡수)
    assert before + 300.0 - 1.0 <= until <= after + 300.0 + 1.0, (
        f"backoff 만료 시각 부정합 — before+300={before+300.0:.3f} "
        f"until={until:.3f} after+300={after+300.0:.3f}"
    )


# ===========================================================================
# Case B — subscribe() 진입 시 backoff 유효 → send skip
# ===========================================================================
@pytest.mark.asyncio
async def test_subscribe_within_backoff_skips_send():
    """backoff 유효 시간 내 `subscribe()` 호출 → `_send_subscribe` 호출 안 됨."""
    ws = KisWebSocket()
    # 가짜 _ws (truthy) — _send_subscribe 호출 분기 진입을 막지 않기 위해
    ws._ws = object()
    # 백오프 등록 — 30s 남음
    key = ("H0UNCNT0", "005930")
    ws._opsp_backoff_until[key] = time.time() + 30.0

    # _send_subscribe 모킹 — 호출 여부 검증
    ws._send_subscribe = AsyncMock()

    await ws.subscribe("H0UNCNT0", "005930")

    # send 미호출 — backoff 차단
    ws._send_subscribe.assert_not_awaited()
    # _subscriptions set 도 add 안 함 — 다음 자연 재시도 시 일관 동작
    assert ("H0UNCNT0", "005930") not in ws._subscriptions


# ===========================================================================
# Case C — backoff 만료 후 정상 subscribe (send 호출됨)
# ===========================================================================
@pytest.mark.asyncio
async def test_subscribe_after_backoff_expired_sends():
    """backoff 만료 시각 경과 후 `subscribe()` 정상 send 발사.

    사이클 17 보강 (2026-05-19) — 만료 시각 검증값을 60s → 300s 정책에 맞춰 갱신.
    본 테스트는 *만료 시각 경과 후* 동작만 검증하므로 과거 시각으로 mock 하면 충분.
    """
    ws = KisWebSocket()
    ws._ws = object()
    key = ("H0UNCNT0", "005930")
    # 이미 만료된 backoff (과거 시각 — 300.001s 경과 의미)
    ws._opsp_backoff_until[key] = time.time() - 300.001

    ws._send_subscribe = AsyncMock()

    await ws.subscribe("H0UNCNT0", "005930")

    # send 정상 호출 + _subscriptions add
    ws._send_subscribe.assert_awaited_once_with("H0UNCNT0", "005930", subscribe=True)
    assert ("H0UNCNT0", "005930") in ws._subscriptions


# ===========================================================================
# Case D — 다른 종목 backoff 영향 0 (key tuple 격리)
# ===========================================================================
@pytest.mark.asyncio
async def test_backoff_isolated_per_ticker():
    """A 종목 backoff 가 B 종목 subscribe 에 영향 없음."""
    ws = KisWebSocket()
    ws._ws = object()
    # A 종목 backoff 등록
    ws._opsp_backoff_until[("H0UNCNT0", "005930")] = time.time() + 30.0

    ws._send_subscribe = AsyncMock()

    # B 종목 subscribe — backoff 영향 없어야 함
    await ws.subscribe("H0UNCNT0", "000660")

    ws._send_subscribe.assert_awaited_once_with("H0UNCNT0", "000660", subscribe=True)
    assert ("H0UNCNT0", "000660") in ws._subscriptions


# ===========================================================================
# Case E — 정상 SUBSCRIBE SUCCESS (rt_cd=0) → backoff 진입 안 함
# ===========================================================================
@pytest.mark.asyncio
async def test_normal_subscribe_success_does_not_register_backoff():
    """정상 SUBSCRIBE SUCCESS 응답은 backoff 사전을 건드리지 않음."""
    ws = KisWebSocket()
    # _subscriptions 에 미리 add — SUBSCRIBE SUCCESS ACK 정합성 가드 통과
    ws._subscriptions.add(("H0UNCNT0", "005930"))

    raw = _make_subscribe_success_raw("H0UNCNT0", "005930")
    await ws._handle_raw(raw)

    # backoff 사전 그대로 비어있음
    assert ws._opsp_backoff_until == {}, (
        f"정상 SUBSCRIBE SUCCESS 후 backoff 등록 잘못됨: {ws._opsp_backoff_until}"
    )
