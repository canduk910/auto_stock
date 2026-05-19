"""실시간 메시지 파싱/디스패치.

- 실시간 체결가 (H0STCNT0/H0UNCNT0/H0NXCNT0): 현재가, 시가, 등락률 등 추출
  - H0STCNT0(KRX) / H0UNCNT0(KRX+NXT 통합) / H0NXCNT0(NXT) — 메시지 포맷 동일
- 체결통보 (H0STCNI0/H0STCNI9): AES-256-CBC 복호화 후 체결 정보 추출
- NXT 장운영정보 (H0NXMKO0): 보드 전환 이벤트 (Phase 3 SessionTracker에서 활용)
"""

from __future__ import annotations

import base64
import logging
from typing import Callable, Awaitable

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

from src.config import settings

logger = logging.getLogger(__name__)

# 콜백 타입
TickHandler = Callable[[str, int, int, float], Awaitable[None]]
# ticker, current_price, open_price, change_rate

ExecutionHandler = Callable[[str, str, str, int, int], Awaitable[None]]
# ticker, order_no, side, price, quantity

BoardHandler = Callable[[str, str, str], Awaitable[None]]
# tr_key, mkop_cls_code, raw_payload — Phase 3 SessionTracker가 소비

_on_tick: TickHandler | None = None
_on_execution: ExecutionHandler | None = None
_on_board: BoardHandler | None = None


def register_tick_handler(handler: TickHandler) -> None:
    global _on_tick
    _on_tick = handler


def register_execution_handler(handler: ExecutionHandler) -> None:
    global _on_execution
    _on_execution = handler


def register_board_handler(handler: BoardHandler) -> None:
    """NXT 장운영정보(H0NXMKO0) 보드 전환 콜백 등록."""
    global _on_board
    _on_board = handler


_aes_iv: str = ""
_aes_key: str = ""


def set_aes_keys(iv: str, key: str) -> None:
    """WebSocket 접속 시 수신한 AES 키를 저장한다."""
    global _aes_iv, _aes_key
    _aes_iv = iv
    _aes_key = key


async def dispatch_message(tr_id: str, tr_key: str, payload: str, encrypted: bool = False) -> None:
    """실시간 메시지를 TR_ID에 따라 적절한 핸들러로 전달한다."""
    # KRX(H0STCNT0) / KRX+NXT 통합(H0UNCNT0) / NXT 단독(H0NXCNT0) 모두 동일 메시지 포맷
    if tr_id in ("H0STCNT0", "H0UNCNT0", "H0NXCNT0"):
        await _handle_tick(payload)
    elif tr_id in ("H0STCNI0", "H0STCNI9"):
        await _handle_execution(payload, encrypted=encrypted)
    # 장운영정보 — 통합(H0UNMKO0) / KRX 단독(H0STMKO0) / NXT 단독(H0NXMKO0). 동일 메시지 포맷
    elif tr_id in ("H0UNMKO0", "H0STMKO0", "H0NXMKO0"):
        await _handle_market_op(tr_id, tr_key, payload)
    else:
        logger.debug("미처리 TR: %s", tr_id)


def _parse_tick_prices(fields: list[str]) -> tuple[int, int] | None:
    """실시간 체결가 payload fields 에서 현재가/시가를 안전 파싱.

    malformed payload 는 None 반환해 상위에서 조용히 스킵한다.
    """
    try:
        return int(fields[2]), int(fields[7])
    except (TypeError, ValueError):
        return None


async def _handle_tick(payload: str) -> None:
    """실시간 체결가 메시지를 파싱한다.

    payload 형식 (^ 구분):
    종목코드^체결시간^현재가^전일대비구분^전일대비^등락률^가중평균^시가^고가^저가^...
    """
    fields = payload.split("^")
    if len(fields) < 10:
        return

    ticker = fields[0]
    parsed = _parse_tick_prices(fields)
    if parsed is None:
        logger.debug("실시간 체결가 파싱 실패: payload=%s", payload[:140])
        return
    current_price, open_price = parsed

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
    # [0] HTS ID, [1] 계좌번호(8자리)+상품코드(2자리), [2] 주문번호, [3] 원주문번호
    # [4] 매도매수구분(02:매수,01:매도), [5] 정정구분, [6] 주문종류
    # [7] 주문조건, [8] 종목코드, [9] 주문수량, [10] 체결단가
    # [11] 체결시간, [12] 거부여부, [13] 체결구분(1:접수,2:체결)
    # [14] ?, [15] ?, [16] 체결수량, [17] 고객명, [18] 종목명

    # 실전 환경에서 동일 HTS ID에 묶인 다른 계좌의 체결통보가 함께 푸시됨 → 대상 계좌만 처리
    target_account = (settings.kis_account_no or "").strip()
    recv_account = fields[1].strip() if fields[1] else ""
    if target_account and recv_account and not recv_account.startswith(target_account):
        logger.debug("체결통보 계좌 불일치 - 무시: 수신=%s, 대상=%s", recv_account, target_account)
        return

    order_no = fields[2]
    side = "BUY" if fields[4] == "02" else "SELL"
    exec_type = fields[13]  # 1:접수, 2:체결
    ticker = fields[8]
    price = int(fields[10]) if fields[10] else 0       # 체결단가
    quantity = int(fields[16]) if len(fields) > 16 and fields[16] else 0  # 체결수량

    # 접수 통보(1)는 무시, 체결 통보(2)만 처리
    if exec_type != "2":
        logger.debug("체결통보 접수(미체결): order_no=%s, ticker=%s", order_no, ticker)
        return

    if not ticker or len(ticker) != 6 or not ticker.isalnum():
        logger.warning("체결통보 종목코드 이상(6자리 영숫자 아님): %s (fields=%s)", ticker, fields[:20])
        return

    if _on_execution:
        await _on_execution(ticker, order_no, side, price, quantity)


async def _handle_market_op(tr_id: str, tr_key: str, payload: str) -> None:
    """장운영정보(H0UNMKO0/H0STMKO0/H0NXMKO0) 메시지 — 보드 전환 이벤트.

    KIS 명세 기준 응답 필드(공통 — 통합/KRX/NXT 동일 구조):
      [0] TRHT_YN — 거래정지 여부
      [1] TR_SUSP_REAS_CNTT — 거래 정지 사유
      [2] MKOP_CLS_CODE — 장운영 구분 코드 (110/112/121/129...)
      [3] ANTC_MKOP_CLS_CODE — 예상 장운영 구분 코드
      [4] MRKT_TRTM_CLS_CODE — 임의연장구분코드
      [5] DIVI_APP_CLS_CODE — 동시호가배분처리구분코드
      [6] ISCD_STAT_CLS_CODE — 종목상태구분코드
      [7] VI_CLS_CODE — VI적용구분코드
      [8] OVTM_VI_CLS_CODE — 시간외단일가VI적용구분코드
      [9] EXCH_CLS_CODE — 거래소 구분코드 (KRX/NXT)

    SessionTracker가 _on_board 콜백을 통해 소비한다.
    """
    fields = payload.split("^")
    mkop_cls_code = fields[2] if len(fields) > 2 else ""
    logger.info(
        "[%s] tr_key=%s, mkop_cls_code=%s, payload=%s",
        tr_id, tr_key, mkop_cls_code, payload[:140],
    )
    if _on_board:
        await _on_board(tr_key, mkop_cls_code, payload)


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
