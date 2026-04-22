"""KIS WebSocket 연결 관리.

- 접속키 발급 후 WebSocket 연결
- 종목 구독/해제 (최대 40개)
- Heartbeat 감시, 자동 재연결 (최대 5회 지수 백오프)
- 메시지 수신 → handler로 디스패치
"""

import asyncio
import json
import logging
from typing import Callable, Awaitable

import websockets
from websockets.asyncio.client import ClientConnection

from src.auth.token import token_manager
from src.config import settings
from src.realtime.handler import set_aes_keys

logger = logging.getLogger(__name__)

MAX_SUBSCRIPTIONS = 40
MAX_RECONNECT = 5
HEARTBEAT_TIMEOUT = 30  # 초
BACKOFF_BASE = 1.0


class KisWebSocket:
    """KIS WebSocket 연결 매니저."""

    def __init__(self) -> None:
        self._ws: ClientConnection | None = None
        self._approval_key: str = ""
        self._subscriptions: set[tuple[str, str]] = set()  # (tr_id, tr_key)
        self._running = False
        self._reconnect_count = 0
        self._on_message: Callable[[str, str, str, bool], Awaitable[None]] | None = None
        # AES 복호화 키 (체결통보용)
        self.aes_iv: str = ""
        self.aes_key: str = ""

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
                self._approval_key = await token_manager.get_approval_key()
                async with websockets.connect(
                    settings.kis_ws_url,
                    ping_interval=None,
                ) as ws:
                    self._ws = ws
                    self._reconnect_count = 0
                    logger.info("WebSocket 연결 성공")

                    # 기존 구독 복원
                    for tr_id, tr_key in list(self._subscriptions):
                        await self._send_subscribe(tr_id, tr_key, subscribe=True)

                    await self._receive_loop()

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

    async def subscribe(self, tr_id: str, tr_key: str) -> None:
        """종목 구독을 등록한다."""
        if len(self._subscriptions) >= MAX_SUBSCRIPTIONS:
            raise RuntimeError(f"최대 구독 수({MAX_SUBSCRIPTIONS}) 초과")
        self._subscriptions.add((tr_id, tr_key))
        if self._ws:
            await self._send_subscribe(tr_id, tr_key, subscribe=True)

    async def unsubscribe(self, tr_id: str, tr_key: str) -> None:
        """종목 구독을 해제한다."""
        self._subscriptions.discard((tr_id, tr_key))
        if self._ws:
            await self._send_subscribe(tr_id, tr_key, subscribe=False)

    # -- private --------------------------------------------------------

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
