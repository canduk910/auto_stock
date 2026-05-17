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
BACKOFF_BASE = 1.0
MIN_STABLE_SECONDS = 5  # 이 시간 이상 연결 유지해야 안정적 연결로 판단

# F1 (2026-05-12) — 재연결 후 자동 시세 검증
# KIS silent inactive(SUBSCRIBE 응답도 시세도 안 주는 케이스) 차단용.
# E2 의 거절 감지가 동작하려면 거절 응답이 와야 하므로 silent inactive 는 못 잡음.
VERIFY_AFTER_SECS = 60        # 재연결 후 검증까지 대기
VERIFY_FRESHNESS_SECS = 60    # 검증 기준 — 이 시간 내 tick 없으면 미수신으로 판정
_KST_TZ = timezone(timedelta(hours=9))

# 구독 거절 감지 키워드 (E2, 2026-05-12) — msg1 대소문자 무시 substring 매칭.
# rt_cd != "0" 1순위, 키워드는 보조. 한국어/영문 변형 누적.
_REJECT_KEYWORDS_UPPER = (
    "ERROR", "FAIL", "REJECT", "NOT ALLOWED",
    "LIMIT", "EXCEED", "DUPLICATE",
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

    def __init__(self, *, token_manager=None) -> None:
        # 사이클 7-C — 메인이면 None, 보조면 외부 매니저 주입
        # `connect()` / approval_key 발급 시 이 매니저 사용
        from src.auth.token import token_manager as _main_tm
        self._token_manager = token_manager if token_manager is not None else _main_tm

        self._ws: ClientConnection | None = None
        self._approval_key: str = ""
        self._subscriptions: set[tuple[str, str]] = set()  # (tr_id, tr_key) — SEND 기준
        # G1 (2026-05-12) — KIS 정상 SUBSCRIBE SUCCESS 응답을 받은 구독만 add.
        # 운영자 가시성: `_subscriptions` 와 분리해 "SEND 후 무응답" 케이스 즉시 식별.
        self._subscriptions_acked: set[tuple[str, str]] = set()
        self._running = False
        self._reconnect_count = 0
        self._on_message: Callable[[str, str, str, bool], Awaitable[None]] | None = None
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
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("WebSocket 연결 종료")

    async def subscribe(self, tr_id: str, tr_key: str, *, bypass_limit: bool = False) -> None:
        """종목 구독을 등록한다.

        bypass_limit=True 면 MAX_SUBSCRIPTIONS 한도 검사를 skip 한다 (보유 종목·익일청산 등
        HIGH 우선순위 구독에 사용 — E1, 2026-05-12). 기본 False 는 기존 분기 유지.
        """
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
                logger.warning("Heartbeat 타임아웃 (%ds), 재연결 시도", HEARTBEAT_TIMEOUT)
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

                # Heartbeat(PINGPONG)
                tr_id = header.get("tr_id", "")
                if tr_id == "PINGPONG":
                    if self._ws:
                        await self._ws.send(raw)
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
                    logger.info(
                        "WebSocket 구독 이미 활성(KIS 측): tr_id=%s, tr_key=%s, msg_cd=%s, msg1=%s",
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
                if rt_cd == "0" and "SUBSCRIBE SUCCESS" in upper_msg1:
                    self._subscriptions_acked.add((tr_id, tr_key))
                    logger.info(
                        "WebSocket 구독 ACK: tr_id=%s, tr_key=%s", tr_id, tr_key,
                    )

                # 구독 성공 응답 → AES 키 저장 (체결통보용)
                output = body.get("output", {})
                if "iv" in output and "key" in output:
                    self.aes_iv = output["iv"]
                    self.aes_key = output["key"]
                    set_aes_keys(self.aes_iv, self.aes_key)
                    logger.info("AES 키 수신: tr_id=%s", tr_id)
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
                await self._on_message(tr_id, tr_key, payload, encrypted)


kis_ws = KisWebSocket()
