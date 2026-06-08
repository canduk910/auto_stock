"""KIS WebSocket 연결 관리.

- 접속키 발급 후 WebSocket 연결
- 종목 구독/해제 (최대 41건, KIS 공식 한도)
- Heartbeat 감시, 자동 재연결 (최대 5회 지수 백오프)
- 메시지 수신 → handler로 디스패치
- 보유 종목 시세 구독은 `bypass_limit=True` 로 한도 무시 (E1, 2026-05-12)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Awaitable

import websockets
from websockets.asyncio.client import ClientConnection

from src.auth.token import token_manager
from src.config import settings
from src.db.system_logs import write_log
from src.realtime.handler import set_aes_keys

logger = logging.getLogger(__name__)

MAX_SUBSCRIPTIONS = 41  # KIS 공식 한도 41건 (1 세션 당). 보유 종목은 한도 무시하고 우선 보장 (subscribe_filtered_stocks priority_groups)
MAX_RECONNECT = 5
HEARTBEAT_TIMEOUT = 30  # 초
# 사이클 42 (2026-05-22) — PINGPONG 가시성 + 5분 주기 [ws_heartbeat] 통계 emit 주기
HEARTBEAT_METRICS_INTERVAL_SECS = 300  # 5분
BACKOFF_BASE = 1.0
MIN_STABLE_SECONDS = 5  # 이 시간 이상 연결 유지해야 안정적 연결로 판단

# F1 (2026-05-12) — 재연결 후 자동 시세 검증
# KIS silent inactive(SUBSCRIBE 응답도 시세도 안 주는 케이스) 차단용.
# E2 의 거절 감지가 동작하려면 거절 응답이 와야 하므로 silent inactive 는 못 잡음.
VERIFY_AFTER_SECS = 60        # 재연결 후 검증까지 대기
VERIFY_FRESHNESS_SECS = 60    # 검증 기준 — 이 시간 내 tick 없으면 미수신으로 판정
_KST_TZ = timezone(timedelta(hours=9))

# 사이클 16 (2026-05-19) — AES 키 저장 가드용 체결통보 tr_id 화이트리스트.
# `_handle_raw` SUBSCRIBE SUCCESS 분기에서 메인 세션 + 이 tr_id 만 모듈 전역 AES 키 저장.
# 보조 세션 또는 시세 SUBSCRIBE SUCCESS 는 skip — 체결통보 키 덮어쓰기 race 차단.
_EXECUTION_NOTICE_TR_IDS = frozenset({"H0STCNI0", "H0STCNI9"})

# 구독 거절 감지 키워드 (E2, 2026-05-12) — msg1 대소문자 무시 substring 매칭.
# rt_cd != "0" 1순위, 키워드는 보조. 한국어/영문 변형 누적.
_REJECT_KEYWORDS_UPPER = (
    "ERROR", "FAIL", "REJECT", "NOT ALLOWED",
    "LIMIT", "EXCEED", "DUPLICATE",
    # 사이클 17 (2026-05-19) — KIS 공식 답변 인용 41건 한도 초과 시 "MAX SUBSCRIBE OVER" 메시지.
    # 기존 LIMIT/EXCEED/OVER 단독 키워드 모두 미매칭이라 명시 추가.
    "MAX SUBSCRIBE",
)
_REJECT_KEYWORDS_KO = (
    # N (2026-05-12) — "이미" 제거: ALREADY IN SUBSCRIBE / "이미 구독" / "이미 등록" 은
    # KIS 측 "이미 활성" 의미로 거절 분기 진입 *전* `_handle_raw` 의 ALREADY 가드가
    # 흡수한다. "이미" 는 다른 정상 메시지에도 광범위하게 출현하는 위양성 키워드.
    "한도", "초과", "중복", "허용되지", "권한",
)


def _is_rejection_response(rt_cd: str | None, msg1: str) -> bool:
    """구독 거절 응답 판정 (E2).

    - rt_cd 가 "0" 외 값이면 거절 (KIS REST 와 동일 규약)
    - rt_cd 가 None/빈문자열이면 (Heartbeat 등) msg1 키워드만 검사
    - msg1 키워드(대소문자 무시): ERROR/FAIL/REJECT/NOT ALLOWED/LIMIT/EXCEED/DUPLICATE,
      한도/초과/이미/중복/허용되지/권한
    """
    if rt_cd not in (None, "", "0"):
        return True
    upper = msg1.upper()
    if any(kw in upper for kw in _REJECT_KEYWORDS_UPPER):
        return True
    if any(kw in msg1 for kw in _REJECT_KEYWORDS_KO):
        return True
    return False


class KisWebSocket:
    """KIS WebSocket 연결 매니저.

    사이클 7-C — 보조 시세 세션 지원을 위해 선택적으로 `token_manager` 주입 가능.
    인자 미지정 시 메인 글로벌 `token_manager` 사용 (기존 동작 100% 보존).
    """

    def __init__(
        self,
        *,
        token_manager=None,
        is_main: bool = True,
        label: str | None = None,  # 사이클 42 (2026-05-22) — pool 주입 (메인=main / 보조=quote-N)
    ) -> None:
        # 사이클 7-C — 메인이면 None, 보조면 외부 매니저 주입
        # `connect()` / approval_key 발급 시 이 매니저 사용
        from src.auth.token import token_manager as _main_tm
        self._token_manager = token_manager if token_manager is not None else _main_tm
        # 사이클 16 (2026-05-19) — 메인/보조 세션 식별자. AES 키 저장 가드용.
        # 보조 세션은 시세 수신 only — 체결통보 구독 안 함 + AES 키 저장도 skip.
        # 메인 세션의 체결통보(H0STCNI0/H0STCNI9) AES 키만 모듈 전역 보존.
        self.is_main: bool = is_main
        # 사이클 42 (2026-05-22) — PINGPONG 가시성 + 5분 주기 [ws_heartbeat] 통계 label.
        # pool 주입 (메인=main / 보조=quote-1/quote-2/...). 미지정 시 is_main 기반 자동 결정.
        self._label: str = label if label is not None else ("main" if is_main else "quote-?")

        self._ws: ClientConnection | None = None
        self._approval_key: str = ""
        self._subscriptions: set[tuple[str, str]] = set()  # (tr_id, tr_key) — SEND 기준
        # G1 (2026-05-12) — KIS 정상 SUBSCRIBE SUCCESS 응답을 받은 구독만 add.
        # 운영자 가시성: `_subscriptions` 와 분리해 "SEND 후 무응답" 케이스 즉시 식별.
        self._subscriptions_acked: set[tuple[str, str]] = set()
        # 사이클 17 (2026-05-19) — OPSP0002 ALREADY IN SUBSCRIBE backoff 사전.
        # KIS 측 거부를 받으면 (tr_id, tr_key) 별 `now + 300.0` 등록 → subscribe 진입 시
        # 유효 시간 내면 send skip. 무한 재구독 → OPSP0002 → 무한 루프 차단.
        # bypass_limit=True (HIGH 우선순위) 는 검사 skip — 보유 종목 손절 우선 보장.
        # 사이클 17 보강 (2026-05-19) — 60s → 300s. `_scan_loop` 5분 주기 ≥ backoff 만료
        # 보장하여 같은 사이클 내 재시도 차단. KIS 답변 인용: "기등록한 사항을 재등록하지 않도록".
        self._opsp_backoff_until: dict[tuple[str, str], float] = {}
        self._running = False
        self._reconnect_count = 0
        self._on_message: Callable[[str, str, str, bool], Awaitable[None]] | None = None
        # 사이클 42 (2026-05-22) — PINGPONG 송수신 통계 (5분 주기 [ws_heartbeat] INFO emit)
        # ping-pong 메커니즘 자체는 정상 동작 (Layer 1/2/3 검증 완료) — 가시성 강화 도구.
        # 운영자가 5분 주기 INFO 로 송수신 빈도 + heartbeat timeout 누적 카운트 검증.
        self._pingpong_recv_count: int = 0
        self._pingpong_last_at: datetime | None = None
        from datetime import timezone, timedelta
        _KST_TZ_INIT = timezone(timedelta(hours=9))
        self._pingpong_window_start_at: datetime = datetime.now(_KST_TZ_INIT)
        self._heartbeat_timeout_count: int = 0
        # 사이클 46 (2026-05-22, refactor-review 카드 #6) — task lifecycle 제거.
        # scheduler `_session_health_loop` 가 5분마다 `_heartbeat_metrics_emit_once` 호출.
        # 좀비 task 방지 + 메인+보조 일관성 + 카운터 reset 동작 보존 (사이클 42 정책).
        # AES 복호화 키 (체결통보용)
        self.aes_iv: str = ""
        self.aes_key: str = ""
        # F1 (2026-05-12) — 재연결 후 자동 검증 task 중첩 방지 플래그
        self._reverify_in_progress: bool = False

    async def connect(
        self,
        on_message: Callable[[str, str, str, bool], Awaitable[None]],
    ) -> None:
        """WebSocket 연결 후 메시지 수신 루프를 시작한다.

        on_message(tr_id, tr_key, data, encrypted): 수신된 메시지 핸들러
        """
        self._on_message = on_message
        self._running = True
        self._reconnect_count = 0

        # 사이클 46 (2026-05-22, refactor-review 카드 #6) — heartbeat metrics task 폐기.
        # scheduler `_session_health_loop` 가 5분마다 모든 세션 `_heartbeat_metrics_emit_once` 호출.
        # 사이클 42 카운터 reset 정책 그대로 보존 (`_heartbeat_metrics_emit_once` 가 reset 책임).

        while self._running and self._reconnect_count <= MAX_RECONNECT:
            try:
                # 사이클 7-C — 메인이면 글로벌 매니저, 보조면 주입된 매니저
                self._approval_key = await self._token_manager.get_approval_key()
                async with websockets.connect(
                    settings.kis_ws_url,
                    ping_interval=None,
                ) as ws:
                    self._ws = ws
                    connected_at = time.monotonic()
                    logger.info("WebSocket 연결 성공")

                    # 기존 구독 복원 + ACK set 클리어 (G1, 2026-05-12)
                    # 재연결 시 KIS 측 슬롯도 초기화되므로 모든 구독은 다시 ACK 받아야 함.
                    await self._restore_subscriptions_after_reconnect()

                    # F1 (2026-05-12) — 재연결인 경우만 검증 task 발화
                    # 첫 연결(_reconnect_count == 0) 은 정상 흐름이므로 검증 불필요.
                    # KIS silent inactive(SUBSCRIBE 응답도 시세도 안 주는 케이스) 차단용.
                    if self._reconnect_count > 0:
                        asyncio.create_task(self._verify_subscriptions_after_reconnect())

                    await self._receive_loop()

                    # 안정적 연결(MIN_STABLE_SECONDS 이상 유지)이었으면 카운트 리셋
                    if time.monotonic() - connected_at >= MIN_STABLE_SECONDS:
                        self._reconnect_count = 0

            except (
                websockets.ConnectionClosed,
                websockets.InvalidURI,
                OSError,
            ) as e:
                self._reconnect_count += 1
                if self._reconnect_count > MAX_RECONNECT:
                    logger.error("최대 재연결 횟수 초과, 종료")
                    break
                wait = BACKOFF_BASE * (2 ** (self._reconnect_count - 1))
                logger.warning(
                    "WebSocket 끊김 (%s), %d/%d 재연결 대기 %.1fs",
                    e,
                    self._reconnect_count,
                    MAX_RECONNECT,
                    wait,
                )
                await asyncio.sleep(wait)

        self._ws = None

    async def disconnect(self) -> None:
        """연결을 종료한다."""
        self._running = False
        # 사이클 46 (2026-05-22) — heartbeat metrics task lifecycle 제거.
        # scheduler `_session_health_loop` 가 통합 호출 → 본 함수에서 cancel 불필요.
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("WebSocket 연결 종료")

    async def _heartbeat_metrics_emit_once(self) -> None:
        """사이클 46 (2026-05-22, refactor-review 카드 #6) — 단발 [ws_heartbeat] emit + 카운터 reset.

        사이클 42 `_heartbeat_metrics_loop` 의 emit 로직 추출. 5분 주기 호출은 scheduler
        `_session_health_loop` 가 메인 + 보조 일괄 담당 → 좀비 task 방지 + 메인+보조 일관성.

        출력 예:
            [ws_heartbeat] label=main window=300s pingpong_recv=10
              avg_interval=30.0s last_age=15s heartbeat_timeout=0

        운영자 분석:
        - pingpong_recv 가 5분 윈도우 내 0 → ping-pong 결함
        - avg_interval 이 비정상 (예: 60s+) → KIS 측 변경 또는 네트워크 지연
        - heartbeat_timeout 누적 → 5분 윈도우 내 timeout 발생 빈도

        본체 예외는 호출자 (`scheduler._emit_heartbeat_metrics_all_sessions`) 가 격리.
        """
        from datetime import timezone as _tz, timedelta as _td
        _KST = _tz(_td(hours=9))

        now = datetime.now(_KST)
        window_secs = (now - self._pingpong_window_start_at).total_seconds()
        recv = self._pingpong_recv_count
        timeouts = self._heartbeat_timeout_count
        avg_interval = window_secs / max(recv, 1) if recv else 0.0
        last_age = (
            (now - self._pingpong_last_at).total_seconds()
            if self._pingpong_last_at else None
        )
        last_age_disp = f"{last_age:.0f}s" if last_age is not None else "none"

        logger.info(
            "[ws_heartbeat] label=%s window=%.0fs pingpong_recv=%d "
            "avg_interval=%.1fs last_age=%s heartbeat_timeout=%d",
            self._label, window_secs, recv, avg_interval,
            last_age_disp, timeouts,
        )
        # 사이클 72 hotfix A1: write_log 직접 호출 제거 — logger.info → _DbLogHandler 위임 단일 INSERT
        # 카운터 + 윈도우 시작 reset (사이클 42 정책 보존)
        self._pingpong_recv_count = 0
        self._heartbeat_timeout_count = 0
        self._pingpong_window_start_at = now

    async def subscribe(self, tr_id: str, tr_key: str, *, bypass_limit: bool = False) -> None:
        """종목 구독을 등록한다.

        bypass_limit=True 면 MAX_SUBSCRIPTIONS 한도 검사를 skip 한다 (보유 종목·익일청산 등
        HIGH 우선순위 구독에 사용 — E1, 2026-05-12). 기본 False 는 기존 분기 유지.

        사이클 17 (2026-05-19) — OPSP0002 backoff 가드.
        ``bypass_limit=False`` 이고 ``_opsp_backoff_until`` 에 등록된 키의 만료 시각이
        아직 지나지 않았으면 send 발사 skip + DEBUG ``[ws_subscribe_backoff]``.
        ``_subscriptions`` set 도 add 안 함 → 다음 자연 재시도 시 일관 동작.
        ``bypass_limit=True`` (HIGH 보유/익일청산) 는 검사 skip — 손절 우선 보장.
        """
        if not bypass_limit:
            until = self._opsp_backoff_until.get((tr_id, tr_key), 0.0)
            now = time.time()
            if now < until:
                logger.debug(
                    "[ws_subscribe_backoff] tr_id=%s tr_key=%s remain=%.1fs",
                    tr_id, tr_key, until - now,
                )
                return
        if not bypass_limit and len(self._subscriptions) >= MAX_SUBSCRIPTIONS:
            logger.warning("최대 구독 수(%d) 도달, %s/%s 구독 건너뜀", MAX_SUBSCRIPTIONS, tr_id, tr_key)
            return
        self._subscriptions.add((tr_id, tr_key))
        # G1: 명시적 (재)구독 호출 시 기존 ACK 무효화 — 새 응답 대기
        self._subscriptions_acked.discard((tr_id, tr_key))
        if self._ws:
            await self._send_subscribe(tr_id, tr_key, subscribe=True)

    async def unsubscribe(self, tr_id: str, tr_key: str) -> None:
        """종목 구독을 해제한다."""
        self._subscriptions.discard((tr_id, tr_key))
        # G1: 해제 시 ACK set 에서도 동기 제거
        self._subscriptions_acked.discard((tr_id, tr_key))
        if self._ws:
            await self._send_subscribe(tr_id, tr_key, subscribe=False)

    def get_subscribed_tickers(self) -> set[str]:
        """현재 TICK(H0UNCNT0) 구독 종목 집합을 반환한다 (Phase D 가시성 보강).

        scheduler._report_tick_coverage 가 5분 주기로 호출해 미수신 종목 카운트 노출.
        체결통보(H0STCNI0/H0STCNI9)·장운영정보(H0UNMKO0) 등 비-시세 구독은 제외.
        """
        # 지연 import: scanner→websocket 순환 의존 회피 (scanner에서 kis_ws 사용)
        from src.engine.scanner import TICK_TR_ID
        return {tr_key for tr_id, tr_key in self._subscriptions if tr_id == TICK_TR_ID}

    def get_acked_tickers(self) -> set[str]:
        """KIS 정상 SUBSCRIBE SUCCESS 응답을 받은 TICK 구독만 반환 (G1, 2026-05-12).

        `get_subscribed_tickers()` 는 SEND 기준, 이 메서드는 KIS 응답 기준.
        둘의 차이가 "SEND 후 무응답" 카운트 — 운영자가 즉시 식별 가능.
        체결통보·장운영정보 등 비-TICK 구독은 동일하게 제외.
        """
        from src.engine.scanner import TICK_TR_ID
        return {tr_key for tr_id, tr_key in self._subscriptions_acked if tr_id == TICK_TR_ID}

    async def _restore_subscriptions_after_reconnect(self) -> None:
        """재연결 직후 기존 구독을 다시 보내고 ACK set 을 비운다 (G1, 2026-05-12).

        KIS 측 슬롯이 재연결로 초기화되므로 모든 구독은 다시 ACK 받아야 한다.
        `_subscriptions` set 은 보존 — 단지 ACK 만 클리어 후 send 재전송.
        """
        self._subscriptions_acked.clear()
        for tr_id, tr_key in list(self._subscriptions):
            await self._send_subscribe(tr_id, tr_key, subscribe=True)

    # -- private --------------------------------------------------------

    async def _verify_subscriptions_after_reconnect(self) -> None:
        """재연결 후 60초 시점에 미수신 TICK 종목 자동 재구독 (F1, 2026-05-12).

        KIS silent inactive(거절도 시세도 없음) 차단용. 1회만 시도하며,
        부족분은 다음 5분 `_scan_loop` 사이클의 unsubscribe_all + 재구독 자연 회복에 위임.

        가드:
        - `_reconnect_count == 0` (첫 연결) 이면 발화 안 함
        - `_reverify_in_progress` True 면 중첩 방지로 즉시 종료
        - 검증 도중 `_ws is None` / `_running is False` 면 조용히 종료
        - 검증 중 예외 발생 → ERROR 로그 + 플래그 해제 (다음 재연결 정상 발화)
        - `_subscriptions` set 직접 수정 금지 — `_send_subscribe` 만 호출
        """
        # 첫 연결은 검증 발화 안 함 (가드)
        if self._reconnect_count == 0:
            return
        if self._reverify_in_progress:
            return
        self._reverify_in_progress = True
        try:
            await asyncio.sleep(VERIFY_AFTER_SECS)
            if not self._running or not self._ws:
                return

            # 지연 import: scanner→websocket 순환 의존 회피
            from src.engine.scanner import TICK_TR_ID, ticker_last_tick

            now = datetime.now(_KST_TZ)
            threshold = timedelta(seconds=VERIFY_FRESHNESS_SECS)
            # TICK 구독만 검증 대상 — 체결통보(H0STCNI0/9), 장운영정보(H0UNMKO0) 등 제외.
            # sorted 로 결정론적 순서 — preview 로그 truncate 가 일관되게 동작.
            subscribed = sorted(
                tr_key for tr_id, tr_key in self._subscriptions
                if tr_id == TICK_TR_ID
            )
            min_dt = datetime.min.replace(tzinfo=_KST_TZ)
            stale = [
                t for t in subscribed
                if (now - ticker_last_tick.get(t, min_dt)) > threshold
            ]
            if not stale:
                logger.info(
                    "[ws_reverify] 재연결 후 %ds — 미수신 종목 없음 (subscribed=%d)",
                    VERIFY_AFTER_SECS, len(subscribed),
                )
                return
            # 로그 truncate — 처음 10개만 표시 + 전체 카운트 명시
            preview = stale[:10]
            logger.warning(
                "[ws_reverify] 재연결 후 %ds — 미수신 %d종목 자동 재구독 "
                "(reconnect_count=%d, preview=%s)",
                VERIFY_AFTER_SECS, len(stale), self._reconnect_count, preview,
            )
            try:
                await write_log(
                    "WARNING",
                    f"[ws_reverify] reconnect_count={self._reconnect_count} "
                    f"stale={len(stale)}/{len(subscribed)} preview={preview}",
                )
            except Exception:
                # fire-and-forget — write_log 실패해도 재구독 흐름 보존
                logger.debug("[ws_reverify] write_log 실패", exc_info=True)

            for ticker in stale:
                # SUBSCRIBE 메시지 1회 재전송 — _subscriptions set 은 이미 보유.
                # 거절 응답이 오면 E2 가 자동으로 _subscriptions.discard 처리.
                await self._send_subscribe(TICK_TR_ID, ticker, subscribe=True)
                # KIS Rate Limit 보호 — 짧은 sleep
                await asyncio.sleep(0.05)
        except Exception:
            logger.exception("[ws_reverify] 재연결 후 검증 실패")
        finally:
            self._reverify_in_progress = False

    async def _send_subscribe(
        self, tr_id: str, tr_key: str, *, subscribe: bool
    ) -> None:
        if not self._ws:
            return
        msg = {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": "1" if subscribe else "2",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": tr_key,
                },
            },
        }
        await self._ws.send(json.dumps(msg))
        action = "구독" if subscribe else "해제"
        logger.info("WebSocket %s: %s / %s", action, tr_id, tr_key)

    async def _receive_loop(self) -> None:
        """메시지 수신 루프. Heartbeat 타임아웃 감시 포함."""
        while self._running and self._ws:
            try:
                raw = await asyncio.wait_for(
                    self._ws.recv(), timeout=HEARTBEAT_TIMEOUT
                )
            except asyncio.TimeoutError:
                # 사이클 42 (2026-05-22) — heartbeat timeout 카운트 (5분 주기 통계용)
                self._heartbeat_timeout_count += 1
                logger.warning(
                    "Heartbeat 타임아웃 (%ds), 재연결 시도 — label=%s timeout_count=%d",
                    HEARTBEAT_TIMEOUT, self._label, self._heartbeat_timeout_count,
                )
                return
            except websockets.ConnectionClosed:
                logger.warning("WebSocket 연결 닫힘")
                return

            await self._handle_raw(str(raw))

    async def _handle_raw(self, raw: str) -> None:
        """수신 메시지를 파싱하여 핸들러로 전달한다."""
        # JSON 응답 (구독 확인, Heartbeat 등)
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
                header = data.get("header", {})
                body = data.get("body", {})

                # Heartbeat(PINGPONG) — 사이클 42 (2026-05-22) 가시성 강화
                tr_id = header.get("tr_id", "")
                if tr_id == "PINGPONG":
                    if self._ws:
                        # L1: PINGPONG echo 추적 (DEBUG — 운영 INFO 미노출, 폭주 방지)
                        logger.debug("[ws_pingpong_echo] label=%s", self._label)
                        await self._ws.send(raw)
                    # L2: 송수신 카운터 + 시각 갱신 (5분 주기 [ws_heartbeat] 통계용)
                    from datetime import timezone as _tz, timedelta as _td
                    _KST = _tz(_td(hours=9))
                    self._pingpong_recv_count += 1
                    self._pingpong_last_at = datetime.now(_KST)
                    return

                msg1 = body.get("msg1", "")
                rt_cd = body.get("rt_cd")
                msg_cd = body.get("msg_cd", "")
                tr_key = header.get("tr_key", "")

                # N (2026-05-12) — ALREADY IN SUBSCRIBE 가드 (거절 분기 *전*)
                # `OPSP0002 ALREADY IN SUBSCRIBE` 응답은 rt_cd=1 이지만 거절이 아니라
                # "KIS 측 이미 활성" 의미. 거절로 분류해 `_subscriptions.discard` 하면
                # 다음 `_scan_loop` 가 재구독 → 또 ALREADY → 무한 루프 + tick_coverage
                # stale 위양성 폭증 (2026-05-12 운영 사고). KIS 측 활성 의미로 받아
                # 우리 set 정합성을 회복한다.
                upper_msg1 = msg1.upper()
                already = (
                    msg_cd == "OPSP0002"
                    or "ALREADY" in upper_msg1
                    or "이미 구독" in msg1
                    or "이미 등록" in msg1
                )
                if already:
                    self._subscriptions.add((tr_id, tr_key))
                    self._subscriptions_acked.add((tr_id, tr_key))
                    # 사이클 17 (2026-05-19) — OPSP0002 backoff 등록.
                    # KIS 측 ALREADY IN SUBSCRIBE 후 다음 _scan_loop 사이클이 즉시
                    # 재구독 → 또 OPSP0002 → 무한 루프 차단 (2026-05-19 15:15 사고 대응).
                    # 사이클 17 보강 — 60s → 300s. `_scan_loop` 5분 주기 ≥ backoff 만료
                    # 보장 (KIS 공식 답변: "기등록한 사항을 재등록하지 않도록").
                    self._opsp_backoff_until[(tr_id, tr_key)] = time.time() + 300.0
                    logger.info(
                        "WebSocket 구독 이미 활성(KIS 측): tr_id=%s, tr_key=%s, msg_cd=%s, msg1=%s [ws_opsp_backoff until=+300s]",
                        tr_id, tr_key, msg_cd, msg1,
                    )
                    return

                # 구독 거절 응답 감지 → 해당 구독 제거 (E2, 2026-05-12)
                # rt_cd != "0" / msg1 키워드(영문 ERROR/FAIL/REJECT/NOT ALLOWED/LIMIT/
                # EXCEED/DUPLICATE, 한국어 한도/초과/중복/허용되지/권한) 매칭 시
                # _subscriptions 정합성 회복 + [ws_subscribe_reject] 영구 로그.
                # 다음 5분 _scan_loop 사이클에서 E1 우선순위 큐로 자연 재시도된다.
                if _is_rejection_response(rt_cd, msg1):
                    logger.error(
                        "WebSocket 구독 거절: tr_id=%s, tr_key=%s, rt_cd=%s, msg_cd=%s, msg=%s",
                        tr_id, tr_key, rt_cd, msg_cd, msg1,
                    )
                    # 거절 난 구독을 제거 (멱등) — 재연결 시 같은 에러 반복 방지
                    self._subscriptions.discard((tr_id, tr_key))
                    # G1: ACK set 에서도 동기 discard (이전에 ACK 됐다가 재구독 후 거절 케이스)
                    self._subscriptions_acked.discard((tr_id, tr_key))
                    # 운영 trace 영구 저장 — Phase A1 [kis_rejection] 패턴 차용.
                    # fire-and-forget: write_log 실패해도 본래 흐름 보존 (정합성 회복 우선).
                    try:
                        await write_log(
                            "ERROR",
                            f"[ws_subscribe_reject] tr_id={tr_id} tr_key={tr_key} "
                            f"rt_cd={rt_cd} msg_cd={msg_cd} msg1={msg1}",
                        )
                    except Exception:
                        pass
                    return

                # G1 (2026-05-12) — 정상 SUBSCRIBE SUCCESS 응답 카운트 별도 추적.
                # KIS REST/WS 어디에도 슬롯 사용현황 조회 API 미존재 → 우리 측 도구로 가시화.
                # rt_cd=="0" + msg1 에 "SUBSCRIBE SUCCESS" 포함 시 _subscriptions_acked add.
                #
                # 사이클 14-C (2026-05-18) — _subscriptions 정합성 가드.
                # in-flight ACK race 차단: unsubscribe 직후 도착한 SUBSCRIBE SUCCESS ACK 는
                # _subscriptions 에 없으면 acked 에도 add 안 함 → 격차(_subscribed=0/_acked=N) 차단.
                # 2026-05-18 KST ~15:01 운영 endpoint 응답의 _main acked=30/subscribed=0 격차 대응.
                if rt_cd == "0" and "SUBSCRIBE SUCCESS" in upper_msg1:
                    if (tr_id, tr_key) in self._subscriptions:
                        self._subscriptions_acked.add((tr_id, tr_key))
                        logger.info(
                            "WebSocket 구독 ACK: tr_id=%s, tr_key=%s", tr_id, tr_key,
                        )
                    else:
                        logger.debug(
                            "[ws_ack_orphan] tr_id=%s tr_key=%s — _subscriptions 부재 (in-flight race ACK 무시)",
                            tr_id, tr_key,
                        )

                # 구독 성공 응답 → AES 키 저장 (체결통보용)
                # 사이클 16 (2026-05-19) — 이중 가드 추가.
                # 1) 세션 가드: 메인 세션만 모듈 전역 키 저장 (보조 세션 skip)
                # 2) tr_id 가드: 체결통보(H0STCNI0/H0STCNI9) 만 저장 (시세 SUBSCRIBE SUCCESS 덮어쓰기 차단)
                # 자체 인스턴스 변수(self.aes_iv/aes_key) 는 보존 (세션별 추적 — 디버깅용)
                output = body.get("output", {})
                if "iv" in output and "key" in output:
                    self.aes_iv = output["iv"]
                    self.aes_key = output["key"]
                    if self.is_main and tr_id in _EXECUTION_NOTICE_TR_IDS:
                        set_aes_keys(self.aes_iv, self.aes_key)
                        logger.info("AES 키 수신: tr_id=%s", tr_id)
                    else:
                        logger.debug(
                            "[aes_key_skip] tr_id=%s is_main=%s — 체결통보 외 키 무시 (사이클 16)",
                            tr_id, self.is_main,
                        )
                return
            except json.JSONDecodeError:
                pass

        # 파이프(|) 구분 실시간 데이터
        # 형식: encrypt|tr_id|count|data
        parts = raw.split("|", 3)
        if len(parts) == 4:
            encrypt_flag, tr_id, _count, payload = parts
            encrypted = encrypt_flag == "1"
            # tr_key는 payload의 첫 필드 (^ 구분, 비암호화 시)
            tr_key = ""
            if not encrypted and "^" in payload:
                tr_key = payload.split("^")[0]
            if self._on_message:
                try:
                    await self._on_message(tr_id, tr_key, payload, encrypted)
                except Exception:
                    logger.exception(
                        "WebSocket 메시지 핸들러 예외: tr_id=%s tr_key=%s encrypted=%s",
                        tr_id,
                        tr_key,
                        encrypted,
                    )


kis_ws = KisWebSocket()
