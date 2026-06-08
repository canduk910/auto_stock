"""사이클 74 의제 2-C — WS 구독/ACK/해제 tr_id별 aggregation (옵션 E-1).

Red 단계: `_record_action` / `_ws_action_collector` / `_flush_ws_action_collector`
+ `[ws_action_summary]` prefix 헬퍼 미존재로 G-WS1/WS2/WS3/WS5/WS6 FAIL.
영속 영역: G-WS4 (사이클 73 R-2 `[ws_subscribe_reject]` logger.error individual 보존) — PASS.

Green 단계: backend-dev 가 `KisWebSocket._record_action(tr_id, tr_key, action)` +
`_flush_ws_action_collector()` + `_ws_action_collector` 인스턴스 변수 도입.
`_send_subscribe` + `_handle_raw` SUBSCRIBE SUCCESS + OPSP0002 ALREADY 분기 흡수.
`disconnect()` cancel *전* 마지막 flush 1회 의무.

영속 의무 (변경 0):
- 사이클 17 보강 (KIS LMS chain 차단, OPSP0002 backoff 300s)
- 사이클 24 silent inactive force_reconnect (logger.error 영속)
- 사이클 29-R1/R2/R3 (force_retry / silent inactive cap / priority 분리)
- 사이클 42 `[ws_heartbeat]` 5분 통계 영속
- 사이클 66 cap=10 priority 분리
- 사이클 67 stale_manager facade
- 사이클 72 `_DbLogHandler` dedupe + G-6
- 사이클 73 R-1/R-2/S-1 + G-6.R/G-6.S
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# G-WS1: 5분 윈도우 내 subscribe 6 + unsubscribe 6 → `[ws_action_summary]` 1행
# ===========================================================================
@pytest.mark.asyncio
async def test_g_ws1_subscribe_unsubscribe_5min_aggregation_one_row(caplog):
    """G-WS1: subscribe 6 + unsubscribe 6 → `[ws_action_summary] tr_id=H0UNCNT0 ...` 1행.

    `_send_subscribe` 호출 시 logger.info 직접 호출 0건 + collector 흡수만.
    """
    import logging
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._ws = MagicMock()
    ws._ws.send = AsyncMock()
    ws._running = True

    tickers_sub = [f"00592{i}" for i in range(6)]
    tickers_unsub = [f"00066{i}" for i in range(6)]

    caplog.set_level(logging.INFO, logger="src.realtime.websocket")

    for t in tickers_sub:
        await ws._send_subscribe("H0UNCNT0", t, subscribe=True)
    for t in tickers_unsub:
        await ws._send_subscribe("H0UNCNT0", t, subscribe=False)

    # 직접 `WebSocket 구독: ...` / `WebSocket 해제: ...` 라인 12 개 흡수 의무
    direct_lines = [
        r.message for r in caplog.records
        if r.message.startswith("WebSocket 구독: ") or r.message.startswith("WebSocket 해제: ")
    ]
    assert len(direct_lines) == 0, (
        f"G-WS1: `_send_subscribe` 직접 logger.info 호출 0건 의무 (옵션 E-1 aggregation 흡수) "
        f"— actual={len(direct_lines)}: {direct_lines[:3]}..."
    )

    # collector flush → `[ws_action_summary]` 1 행 (tr_id=H0UNCNT0)
    flush = getattr(ws, "_flush_ws_action_collector", None)
    assert flush is not None, (
        "사이클 74 G-WS1: `_flush_ws_action_collector` 헬퍼 미존재 — Green 발주 대상"
    )
    caplog.clear()
    flush()

    summary_lines = [
        r.message for r in caplog.records
        if "[ws_action_summary]" in r.message
    ]
    assert len(summary_lines) == 1, (
        f"G-WS1: `[ws_action_summary]` 1행 emit 의무 — actual={len(summary_lines)}"
    )
    msg = summary_lines[0]
    assert "tr_id=H0UNCNT0" in msg, f"G-WS1: tr_id=H0UNCNT0 누락 — actual: {msg}"
    assert "SUBSCRIBE=6" in msg, f"G-WS1: SUBSCRIBE=6 누락 — actual: {msg}"
    assert "UNSUBSCRIBE=6" in msg, f"G-WS1: UNSUBSCRIBE=6 누락 — actual: {msg}"


# ===========================================================================
# G-WS2: 다중 tr_id (H0UNCNT0 + H0STCNT0) 별도 aggregation (tr_id 별 1행)
# ===========================================================================
@pytest.mark.asyncio
async def test_g_ws2_multi_tr_id_separate_aggregation(caplog):
    """G-WS2: 다중 tr_id 별도 aggregation → tr_id 별 1행 emit (총 2 행)."""
    import logging
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._ws = MagicMock()
    ws._ws.send = AsyncMock()
    ws._running = True

    for t in ("005930", "000660", "035420"):
        await ws._send_subscribe("H0UNCNT0", t, subscribe=True)
    for t in ("005935", "207940"):
        await ws._send_subscribe("H0STCNT0", t, subscribe=True)

    flush = getattr(ws, "_flush_ws_action_collector", None)
    assert flush is not None, (
        "사이클 74 G-WS2: `_flush_ws_action_collector` 미존재"
    )

    caplog.set_level(logging.INFO, logger="src.realtime.websocket")
    flush()

    summary_lines = [
        r.message for r in caplog.records
        if "[ws_action_summary]" in r.message
    ]
    assert len(summary_lines) == 2, (
        f"G-WS2: tr_id 2 종 → 2 행 emit 의무 — actual={len(summary_lines)}"
    )
    tr_ids_emitted = set()
    for msg in summary_lines:
        if "tr_id=H0UNCNT0" in msg:
            tr_ids_emitted.add("H0UNCNT0")
        if "tr_id=H0STCNT0" in msg:
            tr_ids_emitted.add("H0STCNT0")
    assert tr_ids_emitted == {"H0UNCNT0", "H0STCNT0"}, (
        f"G-WS2: tr_id 별 분리 emit 의무 — actual: {tr_ids_emitted}"
    )


# ===========================================================================
# G-WS3: SUBSCRIBE SUCCESS ACK aggregation 흡수
# ===========================================================================
@pytest.mark.asyncio
async def test_g_ws3_subscribe_success_ack_absorbed_into_aggregation(caplog):
    """G-WS3: `_handle_raw` SUBSCRIBE SUCCESS 분기에서 logger.info 직접 호출 0건 +
    collector action=ACK 흡수만."""
    import logging
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._ws = MagicMock()
    ws._ws.send = AsyncMock()
    ws._running = True

    # _subscriptions 정합성 가드 (사이클 14-C 영속) — 미리 add 필요
    ws._subscriptions.add(("H0UNCNT0", "005930"))

    success_msg = json.dumps({
        "header": {"tr_id": "H0UNCNT0", "tr_key": "005930"},
        "body": {"rt_cd": "0", "msg_cd": "OPSP0000",
                 "msg1": "SUBSCRIBE SUCCESS"},
    })

    caplog.set_level(logging.INFO, logger="src.realtime.websocket")
    await ws._handle_raw(success_msg)

    direct_lines = [
        r.message for r in caplog.records
        if "WebSocket 구독 ACK:" in r.message
    ]
    assert len(direct_lines) == 0, (
        f"G-WS3: SUBSCRIBE SUCCESS 직접 logger.info 호출 0건 의무 (옵션 E-1 흡수) "
        f"— actual={len(direct_lines)}: {direct_lines}"
    )

    # collector 에 ACK action 흡수 검증
    collector = getattr(ws, "_ws_action_collector", None)
    assert collector is not None, (
        "사이클 74 G-WS3: `_ws_action_collector` 인스턴스 변수 미존재 — Green 발주 대상"
    )
    h0un = collector.get("H0UNCNT0", {})
    ack_tickers = h0un.get("ACK", [])
    assert "005930" in ack_tickers, (
        f"G-WS3: collector ACK 005930 흡수 의무 — actual ACK={ack_tickers}"
    )


# ===========================================================================
# G-WS4: `[ws_subscribe_reject]` ERROR individual 보존 (사이클 73 R-2 영속)
# ===========================================================================
@pytest.mark.asyncio
async def test_g_ws4_subscribe_reject_logger_error_individual_preserved(caplog):
    """G-WS4: 거절 응답 시 `[ws_subscribe_reject]` logger.error individual 보존.

    사이클 73 R-2 영속 영역 + 사이클 29 005935 LMS chain 진단 의무.
    aggregation 흡수 금지 — 결함 가시화 영속.
    """
    import logging
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._ws = MagicMock()
    ws._ws.send = AsyncMock()
    ws._running = True

    # 사이클 73 R-2 거절 분기 트리거 (rt_cd != "0" + msg1 키워드)
    reject_msg = json.dumps({
        "header": {"tr_id": "H0UNCNT0", "tr_key": "005930"},
        "body": {"rt_cd": "1", "msg_cd": "OPSP9999",
                 "msg1": "SUBSCRIBE LIMIT EXCEED"},
    })

    caplog.set_level(logging.ERROR, logger="src.realtime.websocket")
    await ws._handle_raw(reject_msg)

    error_lines = [
        r.message for r in caplog.records
        if "[ws_subscribe_reject]" in r.message
    ]
    assert len(error_lines) >= 1, (
        "G-WS4: `[ws_subscribe_reject]` logger.error individual 보존 의무 위반 — "
        "사이클 73 R-2 영속 영역 침범"
    )

    # collector 가 거절 사이트 흡수 0건 (logger.error 단독 emit 영속)
    collector = getattr(ws, "_ws_action_collector", {})
    if collector:
        h0un = collector.get("H0UNCNT0", {})
        reject_in_collector = "REJECT" in h0un or "ERROR" in h0un
        assert not reject_in_collector, (
            "G-WS4: 거절 응답 collector 흡수 금지 — logger.error individual 보존 영속"
        )


# ===========================================================================
# G-WS5: OPSP0002 ALREADY 흡수 (Q2-D 옵션 A) — opsp_already 카운트만
# ===========================================================================
@pytest.mark.asyncio
async def test_g_ws5_opsp0002_already_absorbed_with_count(caplog):
    """G-WS5: OPSP0002 ALREADY 응답 시 aggregation 흡수 (Q2-D 옵션 A).

    사이클 17 보강 (KIS LMS chain 차단) 영속 — backoff 300s 정책 유지.
    `WebSocket 구독 이미 활성(KIS 측): ...` 직접 INFO 0건 + collector action=OPSP_ALREADY 흡수.
    """
    import logging
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._ws = MagicMock()
    ws._ws.send = AsyncMock()
    ws._running = True

    opsp_msg = json.dumps({
        "header": {"tr_id": "H0UNCNT0", "tr_key": "005930"},
        "body": {"rt_cd": "1", "msg_cd": "OPSP0002",
                 "msg1": "ALREADY IN SUBSCRIBE"},
    })

    caplog.set_level(logging.INFO, logger="src.realtime.websocket")
    await ws._handle_raw(opsp_msg)

    direct_lines = [
        r.message for r in caplog.records
        if "WebSocket 구독 이미 활성" in r.message
    ]
    assert len(direct_lines) == 0, (
        f"G-WS5: OPSP0002 ALREADY 직접 logger.info 호출 0건 의무 (Q2-D 옵션 A 흡수) "
        f"— actual={len(direct_lines)}"
    )

    # backoff 등록 영속 (사이클 17 보강 영역)
    backoff_key = ("H0UNCNT0", "005930")
    assert backoff_key in ws._opsp_backoff_until, (
        "G-WS5: OPSP0002 backoff 등록 영속 의무 — 사이클 17 보강 영역 위반"
    )

    # collector OPSP_ALREADY 흡수
    collector = getattr(ws, "_ws_action_collector", None)
    assert collector is not None, (
        "사이클 74 G-WS5: `_ws_action_collector` 미존재"
    )
    h0un = collector.get("H0UNCNT0", {})
    opsp_tickers = h0un.get("OPSP_ALREADY", [])
    assert "005930" in opsp_tickers, (
        f"G-WS5: collector OPSP_ALREADY 흡수 의무 — actual: {opsp_tickers}"
    )


# ===========================================================================
# G-WS6: 윈도우 종료 시 마지막 flush + disconnect cancel *전* flush (Q5 옵션 A)
# ===========================================================================
@pytest.mark.asyncio
async def test_g_ws6_disconnect_flushes_residual_before_cancel(caplog):
    """G-WS6: disconnect() cancel *전* 마지막 flush 1회 의무 (Q5 옵션 A).

    잔여 카운터 손실 방지 — 운영 환경 매일 20:00 `unsubscribe_all()` 직후
    disconnect → flush 가 정산 *직전* 데이터 보존.
    """
    import logging
    from src.realtime.websocket import KisWebSocket

    ws = KisWebSocket()
    ws._ws = MagicMock()
    ws._ws.send = AsyncMock()
    ws._running = True

    # 잔여 2 종목
    await ws._send_subscribe("H0UNCNT0", "005930", subscribe=True)
    await ws._send_subscribe("H0UNCNT0", "000660", subscribe=True)

    # disconnect 시점 직전 마지막 flush 의무
    caplog.set_level(logging.INFO, logger="src.realtime.websocket")
    # Green 후 = disconnect 가 자동 flush 호출. Red 단계는 헬퍼 자체 검증.
    flush = getattr(ws, "_flush_ws_action_collector", None)
    assert flush is not None, (
        "사이클 74 G-WS6: `_flush_ws_action_collector` 미존재 — disconnect 마지막 flush 의무"
    )
    flush()

    summary_lines = [
        r.message for r in caplog.records
        if "[ws_action_summary]" in r.message
    ]
    assert len(summary_lines) == 1, (
        f"G-WS6: disconnect 잔존 flush 1행 의무 — actual={len(summary_lines)} "
        f"(잔여 카운터 손실 = Q5 옵션 A 위반)"
    )
    assert "SUBSCRIBE=2" in summary_lines[0], (
        f"G-WS6: 잔존 2 종목 모두 흡수 — actual: {summary_lines[0]}"
    )
