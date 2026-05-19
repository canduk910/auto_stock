"""실시간 시세 구독 진단 라우트 — /api/realtime/* (G2/J2, 2026-05-12).

KIS REST/WS 어디에도 슬롯 사용현황 조회 API 미존재 → 우리 측 도구로 가시화.

GET /api/realtime/subscriptions:
- `_subscriptions` (SEND 기준) vs `_subscriptions_acked` (KIS 응답 기준) 격차 노출
- 최근 60초 내 tick 수신 (`fresh_60s`) / 미수신 (`stale_60s`) 카운트
- `MAX_SUBSCRIPTIONS=41` 한도 + 누적 재연결 횟수 + WebSocket 활성 여부

POST /api/realtime/resubscribe (J2, 2026-05-12):
- 60초 미수신(stale) TICK 종목을 운영자가 즉시 일괄 재구독
- F1 자동 재구독(재연결 후 60s)과 별개의 수동 트리거
- `_subscriptions` set 은 보존 — `_send_subscribe(TICK_TR_ID, t, subscribe=True)` 만 호출
- 호출 간 50ms sleep (Rate Limit 안전)
- WebSocket 끊김 시 400 (재구독 메시지 발송 불가)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from src.db.system_logs import write_log
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/realtime", tags=["realtime"])

# 60s 임계는 scanner.get_scan_status / scheduler._report_tick_coverage 와 동일 (운영 일관성)
_KST_TZ = timezone(timedelta(hours=9))
_FRESHNESS_SECS = 60


@router.get("/subscriptions", response_model=ApiResponse)
async def get_subscriptions() -> ApiResponse:
    """현재 WebSocket 구독 슬롯 사용현황을 반환한다.

    사이클 7-B (2026-05-17) — 멀티 세션 풀 지원:
    - 메인 + 보조 세션 합집합으로 ``total/acked/fresh_60s/stale_60s`` 산출
    - ``sessions`` 배열로 세션별 ``label/subscribed/acked/fresh/stale/limit/ws_connected/reconnect_count`` 노출
    - ``limit`` 전체값 = ``MAX_SUBSCRIPTIONS × (1 + 보조 세션 수)``
    - 보조 0개 시 sessions 길이 1 (main only) — 기존 호환 보존

    응답 data 스키마:
        total            — 합집합 TICK 구독 (SEND 기준)
        acked            — 합집합 ACK (KIS 응답 기준)
        fresh_60s        — 최근 60s 내 tick 수신 카운트
        stale_60s        — 60s 미수신 카운트
        limit            — 41 × (1 + 보조 세션 수)
        tickers.subscribed / acked / fresh / stale — 합집합 sorted
        reconnect_count  — 메인 세션 재연결 횟수 (보조는 sessions[*] 에 별도 노출)
        ws_connected     — 메인 세션 활성 (보조는 sessions[*] 에 별도 노출)
        sessions         — [{label, subscribed, acked, fresh, stale, limit, ws_connected, reconnect_count}, ...]
    """
    # 지연 import — scanner 가 websocket 을 참조하므로 순환 의존 회피
    from src.engine.scanner import TICK_TR_ID, ticker_last_tick
    from src.realtime.websocket import MAX_SUBSCRIPTIONS
    from src.realtime.websocket_pool import kis_ws_pool

    pool = kis_ws_pool
    # 합집합 (메인 + 보조)
    subscribed_set = pool.get_subscribed_tickers()
    acked_set = pool.get_acked_tickers()

    now = datetime.now(_KST_TZ)
    threshold = timedelta(seconds=_FRESHNESS_SECS)
    _min_dt = datetime.min.replace(tzinfo=_KST_TZ)
    fresh_set = {
        t for t in subscribed_set
        if (now - ticker_last_tick.get(t, _min_dt)) <= threshold
    }
    stale_set = subscribed_set - fresh_set

    # 세션별 분해 + freshness 카운트 추가
    sessions = pool.get_session_status()
    for session in sessions:
        # session.tickers.subscribed 에 sorted ticker 리스트 보유 — freshness 계산
        ticker_list = session.get("tickers", {}).get("subscribed", [])
        ticker_set = set(ticker_list)
        s_fresh = {
            t for t in ticker_set
            if (now - ticker_last_tick.get(t, _min_dt)) <= threshold
        }
        session["fresh"] = len(s_fresh)
        session["stale"] = len(ticker_set) - len(s_fresh)

    # 사이클 18 (2026-05-19, B-1) — stale 종목별 마지막 tick 시각 노출.
    # 프론트 ScanMonitor 가 "끊김 N종목" 펼치기 시 종목별 마지막 수신 시각 표시.
    # KRX 메인 마감 (15:30) 전 = 결함 가능 / 마감 후 = 자연 휴면 톤 분기 근거.
    last_tick_map: dict[str, str | None] = {}
    for ticker in sorted(stale_set):
        last_dt = ticker_last_tick.get(ticker)
        if last_dt is None or last_dt == _min_dt:
            last_tick_map[ticker] = None
        else:
            last_tick_map[ticker] = last_dt.isoformat()  # KST tz 포함

    data = {
        "total": len(subscribed_set),
        "acked": len(acked_set),
        "fresh_60s": len(fresh_set),
        "stale_60s": len(stale_set),
        "limit": MAX_SUBSCRIPTIONS * len(sessions),
        "tickers": {
            "subscribed": sorted(subscribed_set),
            "acked": sorted(acked_set),
            "fresh": sorted(fresh_set),
            "stale": sorted(stale_set),
        },
        "last_tick_map": last_tick_map,
        "reconnect_count": pool._reconnect_count,
        "ws_connected": pool._ws is not None,
        "sessions": sessions,
    }
    return ApiResponse(success=True, data=data, message="")


@router.post("/resubscribe", response_model=ApiResponse)
async def resubscribe_stale() -> ApiResponse:
    """stale(60s 미수신) TICK 구독 종목을 즉시 일괄 재구독한다 (J2, 2026-05-12).

    운영자가 ScanMonitor 의 끊김 배지를 확인하고 인라인 버튼을 눌러 호출.
    F1 자동 재구독(재연결 후 60s)이 발화하지 않는 일반 운영 시간대(연결 유지 중)
    에 stale 이 누적된 경우 즉시 회복.

    안전 불변식:
    - `_subscriptions` set 직접 수정 금지 — `_send_subscribe` 만 호출
      (E2 거절 응답이 오면 자동으로 set 에서 discard 됨)
    - 호출 간 50ms sleep — KIS WS Rate Limit 보호 (F1 메서드와 동일 패턴)
    - WebSocket `_ws is None` 시 400 — 메시지 발송 불가하므로 조용히 200 반환 금지

    응답:
        data.resubscribed : 재구독 종목 수
        data.tickers      : sorted ticker 리스트
    """
    # 지연 import — scanner 가 websocket 을 참조하므로 순환 의존 회피
    from src.engine.scanner import TICK_TR_ID, ticker_last_tick
    from src.realtime.websocket import VERIFY_FRESHNESS_SECS, kis_ws

    # WebSocket 끊김 → 메시지 발송 불가 → 400 (조용한 200 금지)
    if kis_ws._ws is None:
        raise HTTPException(
            status_code=400,
            detail="WebSocket 연결 끊김 — 재구독 메시지 발송 불가. 자동 재연결 대기 후 재시도.",
        )

    # 현재 TICK 구독 집합 (SEND 기준, Phase D `get_subscribed_tickers`)
    subscribed = kis_ws.get_subscribed_tickers()

    now = datetime.now(_KST_TZ)
    threshold = timedelta(seconds=VERIFY_FRESHNESS_SECS)
    min_dt = datetime.min.replace(tzinfo=_KST_TZ)

    # stale 추출 — last_tick 없으면 stale 로 간주 (F1 동일 규약)
    stale = sorted(
        t for t in subscribed
        if (now - ticker_last_tick.get(t, min_dt)) > threshold
    )

    # 각 stale ticker 재구독 — `_send_subscribe` 만 사용
    for ticker in stale:
        await kis_ws._send_subscribe(TICK_TR_ID, ticker, subscribe=True)
        await asyncio.sleep(0.05)  # Rate Limit 보호

    # 영구 로그 — count=0 도 기록 (운영자가 빈 stale 도 확인 가능)
    try:
        await write_log(
            "INFO",
            f"[ws_manual_resubscribe] count={len(stale)} tickers={stale}",
        )
    except Exception:
        # fire-and-forget — write_log 실패해도 재구독 응답은 유지
        logger.debug("[ws_manual_resubscribe] write_log 실패", exc_info=True)

    return ApiResponse(
        success=True,
        data={"resubscribed": len(stale), "tickers": stale},
        message="",
    )
