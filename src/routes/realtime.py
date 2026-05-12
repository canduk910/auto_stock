"""실시간 시세 구독 진단 라우트 — /api/realtime/* (G2, 2026-05-12).

KIS REST/WS 어디에도 슬롯 사용현황 조회 API 미존재 → 우리 측 도구로 가시화.

GET /api/realtime/subscriptions:
- `_subscriptions` (SEND 기준) vs `_subscriptions_acked` (KIS 응답 기준) 격차 노출
- 최근 60초 내 tick 수신 (`fresh_60s`) / 미수신 (`stale_60s`) 카운트
- `MAX_SUBSCRIPTIONS=41` 한도 + 누적 재연결 횟수 + WebSocket 활성 여부

운영자가 단일 호출로 SEND→ACK→fresh 격차를 인지하고 한도 근접도 확인 가능.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/realtime", tags=["realtime"])

# 60s 임계는 scanner.get_scan_status / scheduler._report_tick_coverage 와 동일 (운영 일관성)
_KST_TZ = timezone(timedelta(hours=9))
_FRESHNESS_SECS = 60


@router.get("/subscriptions", response_model=ApiResponse)
async def get_subscriptions() -> ApiResponse:
    """현재 WebSocket 구독 슬롯 사용현황을 반환한다.

    응답 data 스키마:
        total            — _subscriptions TICK 필터 size (SEND 기준)
        acked            — _subscriptions_acked TICK 필터 size (KIS 응답 기준)
        fresh_60s        — 최근 60s 내 tick 수신 카운트
        stale_60s        — 60s 미수신 카운트 (= total - fresh_60s)
        limit            — MAX_SUBSCRIPTIONS (KIS 공식 한도 41)
        tickers.subscribed / acked / fresh / stale — 모두 sorted 리스트
        reconnect_count  — 누적 재연결 횟수 (오늘 _reset_daily_state 까지)
        ws_connected     — WebSocket 활성 여부 (`_ws is not None`)
    """
    # 지연 import — scanner 가 websocket 을 참조하므로 순환 의존 회피
    from src.engine.scanner import TICK_TR_ID, ticker_last_tick
    from src.realtime.websocket import MAX_SUBSCRIPTIONS, kis_ws

    subscribed_set = {
        tr_key for tr_id, tr_key in kis_ws._subscriptions if tr_id == TICK_TR_ID
    }
    acked_set = {
        tr_key for tr_id, tr_key in kis_ws._subscriptions_acked if tr_id == TICK_TR_ID
    }

    now = datetime.now(_KST_TZ)
    threshold = timedelta(seconds=_FRESHNESS_SECS)
    _min_dt = datetime.min.replace(tzinfo=_KST_TZ)
    fresh_set = {
        t for t in subscribed_set
        if (now - ticker_last_tick.get(t, _min_dt)) <= threshold
    }
    stale_set = subscribed_set - fresh_set

    data = {
        "total": len(subscribed_set),
        "acked": len(acked_set),
        "fresh_60s": len(fresh_set),
        "stale_60s": len(stale_set),
        "limit": MAX_SUBSCRIPTIONS,
        "tickers": {
            "subscribed": sorted(subscribed_set),
            "acked": sorted(acked_set),
            "fresh": sorted(fresh_set),
            "stale": sorted(stale_set),
        },
        "reconnect_count": kis_ws._reconnect_count,
        "ws_connected": kis_ws._ws is not None,
    }
    return ApiResponse(success=True, data=data, message="")
