"""실시간 메시지 파싱/디스패치.

- 실시간 체결가 (H0STCNT0): 현재가, 시가, 등락률 등 추출
- 체결통보 (H0STCNI0): AES-256-CBC 복호화 후 체결 정보 추출
"""

import base64
import logging
from typing import Callable, Awaitable

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

logger = logging.getLogger(__name__)

# 콜백 타입
TickHandler = Callable[[str, int, int, float], Awaitable[None]]
# ticker, current_price, open_price, change_rate

ExecutionHandler = Callable[[str, str, str, int, int], Awaitable[None]]
# ticker, order_no, side, price, quantity

_on_tick: TickHandler | None = None
_on_execution: ExecutionHandler | None = None


def register_tick_handler(handler: TickHandler) -> None:
    global _on_tick
    _on_tick = handler


def register_execution_handler(handler: ExecutionHandler) -> None:
    global _on_execution
    _on_execution = handler


_aes_iv: str = ""
_aes_key: str = ""


def set_aes_keys(iv: str, key: str) -> None:
    """WebSocket 접속 시 수신한 AES 키를 저장한다."""
    global _aes_iv, _aes_key
    _aes_iv = iv
    _aes_key = key


async def dispatch_message(tr_id: str, tr_key: str, payload: str, encrypted: bool = False) -> None:
    """실시간 메시지를 TR_ID에 따라 적절한 핸들러로 전달한다."""
    if tr_id == "H0STCNT0":
        await _handle_tick(payload)
    elif tr_id in ("H0STCNI0", "H0STCNI9"):
        await _handle_execution(payload, encrypted=encrypted)
    else:
        logger.debug("미처리 TR: %s", tr_id)


async def _handle_tick(payload: str) -> None:
    """실시간 체결가 메시지를 파싱한다.

    payload 형식 (^ 구분):
    종목코드^체결시간^현재가^전일대비구분^전일대비^등락률^가중평균^시가^고가^저가^...
    """
    fields = payload.split("^")
    if len(fields) < 10:
        return

    ticker = fields[0]
    current_price = int(fields[2])
    open_price = int(fields[7])

    if open_price > 0:
        change_rate = (current_price - open_price) / open_price * 100
    else:
        change_rate = 0.0

    if _on_tick:
        await _on_tick(ticker, current_price, open_price, change_rate)


async def _handle_execution(payload: str, *, encrypted: bool = False) -> None:
    """체결통보 메시지를 파싱한다.

    payload가 암호화된 경우 AES-256-CBC로 복호화 후 ^ 구분 필드를 파싱한다.
    """
    if encrypted and _aes_key and _aes_iv:
        try:
            payload = decrypt_aes_cbc(payload, _aes_key, _aes_iv)
        except Exception:
            logger.exception("체결통보 AES 복호화 실패")
            return

    # 체결통보 필드 파싱 (^ 구분)
    fields = payload.split("^")
    if len(fields) < 15:
        return

    # 필드 매핑 (KIS 체결통보 output 기준)
    # [0] HTS ID, [1] 계좌번호, [2] 주문번호, [3] 원주문번호
    # [4] 매도매수구분(02:매수,01:매도), [5] 정정구분, [6] 주문종류
    # [7] 주문조건, [8] 주문단가, [9] 주문수량, [10] 체결금액
    # [11] 체결시간, [12] 거부여부, [13] 체결구분(1:접수,2:체결)
    # [14] ?, [15] 종목번호, [16] 체결수량, [17] 고객명, [18] 종목명
    order_no = fields[2]
    side = "BUY" if fields[4] == "02" else "SELL"
    exec_type = fields[13]  # 1:접수, 2:체결
    ticker = fields[15] if len(fields) > 15 else ""
    price = int(fields[10]) if fields[10] else 0       # 체결금액
    quantity = int(fields[16]) if len(fields) > 16 and fields[16] else 0  # 체결수량

    # 접수 통보(1)는 무시, 체결 통보(2)만 처리
    if exec_type != "2":
        logger.debug("체결통보 접수(미체결): order_no=%s, ticker=%s", order_no, ticker)
        return

    if not ticker or not ticker.isdigit():
        logger.warning("체결통보 종목코드 이상: %s (fields=%s)", ticker, fields[:20])
        return

    if _on_execution:
        await _on_execution(ticker, order_no, side, price, quantity)


def decrypt_aes_cbc(encrypted_text: str, key: str, iv: str) -> str:
    """AES-256-CBC 복호화."""
    cipher = Cipher(
        algorithms.AES(key.encode("utf-8")),
        modes.CBC(iv.encode("utf-8")),
    )
    decryptor = cipher.decryptor()
    decoded = base64.b64decode(encrypted_text)
    decrypted_padded = decryptor.update(decoded) + decryptor.finalize()

    unpadder = sym_padding.PKCS7(128).unpadder()
    decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
    return decrypted.decode("utf-8")
