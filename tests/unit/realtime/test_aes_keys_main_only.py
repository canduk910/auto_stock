"""사이클 16 (2026-05-19) — AES 키 저장 격리 가드.

배경: 사이클 7-C 풀 통합 (메인 + 보조 N 세션) 이후 모든 SUBSCRIBE SUCCESS
응답이 모듈 전역 `_aes_iv`/`_aes_key` 를 덮어씌움. 메인 세션의 체결통보(H0STCNI0)
키가 보조 세션 ISA 의 시세(H0UNCNT0) SUBSCRIBE SUCCESS 키로 덮어써져
체결통보 복호화 실패 (오늘 11:20:23~11:22:31 11건 발생).

KIS 명세 (docs/kis/domestic-stock-realtime.md):
- 모든 SUBSCRIBE SUCCESS 응답에 `output.iv` / `output.key` 포함
- 같은 connect 내 SUBSCRIBE SUCCESS = 같은 키 (메인 단일 환경 무해)
- 메인 vs 보조 = 별도 connect = 다른 키 (보조 키가 메인 체결통보 키 덮어쓰면 실패)

fix: `_handle_raw` SUBSCRIBE SUCCESS 분기에서 이중 가드:
1. **세션 가드**: `self.is_main=True` 인 경우만 저장 (보조 세션 skip)
2. **tr_id 가드**: `tr_id in {H0STCNI0, H0STCNI9}` 만 저장 (시세 SUBSCRIBE SUCCESS skip)

호환: `set_aes_keys` 시그니처 무변경. 호출자(websocket.py) 가 가드 적용.

6 케이스:
1. KisWebSocket default `is_main=True`
2. KisWebSocket `is_main=False` 명시 가능
3. 메인 + 체결통보 SUBSCRIBE SUCCESS → set_aes_keys 호출
4. 메인 + 시세(H0UNCNT0) SUBSCRIBE SUCCESS → set_aes_keys skip
5. 보조 + 시세 SUBSCRIBE SUCCESS → set_aes_keys skip
6. 보조 + 체결통보 (이론상 X — 사이클 7-B 차단) SUBSCRIBE SUCCESS → set_aes_keys skip (이중 안전망)
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.realtime import handler as handler_mod
from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


def _make_subscribe_success_raw(tr_id: str, tr_key: str, iv: str, key: str) -> str:
    return json.dumps({
        "header": {"tr_id": tr_id, "tr_key": tr_key},
        "body": {
            "rt_cd": "0",
            "msg_cd": "OPSP0000",
            "msg1": "SUBSCRIBE SUCCESS",
            "output": {"iv": iv, "key": key},
        },
    })


@pytest.fixture
def reset_aes_keys():
    """매 테스트 시작 전 모듈 전역 키 초기화."""
    handler_mod._aes_iv = ""
    handler_mod._aes_key = ""
    yield
    handler_mod._aes_iv = ""
    handler_mod._aes_key = ""


# ===========================================================================
# Case 1: KisWebSocket default is_main=True
# ===========================================================================
def test_kis_websocket_default_is_main():
    ws = KisWebSocket()
    assert ws.is_main is True


# ===========================================================================
# Case 2: KisWebSocket is_main=False 명시
# ===========================================================================
def test_kis_websocket_is_main_explicit_false():
    ws = KisWebSocket(is_main=False)
    assert ws.is_main is False


# ===========================================================================
# Case 3: 메인 + 체결통보 SUBSCRIBE SUCCESS → AES 키 저장
# ===========================================================================
@pytest.mark.asyncio
async def test_main_execution_notice_saves_aes_keys(reset_aes_keys):
    ws = KisWebSocket()  # is_main=True
    ws._subscriptions.add(("H0STCNI0", "HTSID01"))
    raw = _make_subscribe_success_raw(
        "H0STCNI0", "HTSID01",
        iv="exec_iv_main_aaaa",
        key="exec_key_main_aaaaaaaaaaaaaaaaaaaaa",
    )
    await ws._handle_raw(raw)

    assert handler_mod._aes_iv == "exec_iv_main_aaaa"
    assert handler_mod._aes_key == "exec_key_main_aaaaaaaaaaaaaaaaaaaaa"


# ===========================================================================
# Case 4: 메인 + 시세(H0UNCNT0) SUBSCRIBE SUCCESS → AES 키 저장 SKIP
# ===========================================================================
@pytest.mark.asyncio
async def test_main_tick_subscribe_success_skips_aes_keys(reset_aes_keys):
    """메인 세션이라도 체결통보 외 tr_id 의 AES 키는 저장 안 함 (덮어쓰기 race 차단)."""
    ws = KisWebSocket()  # is_main=True

    # 사전에 체결통보 키 저장 (보존되어야 함)
    handler_mod._aes_iv = "preserved_iv"
    handler_mod._aes_key = "preserved_key"

    ws._subscriptions.add(("H0UNCNT0", "005930"))
    raw = _make_subscribe_success_raw(
        "H0UNCNT0", "005930",
        iv="tick_iv_should_not_overwrite",
        key="tick_key_should_not_overwrite",
    )
    await ws._handle_raw(raw)

    # 체결통보 키 그대로 보존
    assert handler_mod._aes_iv == "preserved_iv"
    assert handler_mod._aes_key == "preserved_key"


# ===========================================================================
# Case 5: 보조 + 시세 SUBSCRIBE SUCCESS → AES 키 저장 SKIP
# ===========================================================================
@pytest.mark.asyncio
async def test_quote_session_skips_aes_keys(reset_aes_keys):
    """보조 세션(is_main=False)의 시세 SUBSCRIBE SUCCESS 는 AES 키 저장 skip."""
    ws = KisWebSocket(is_main=False)

    handler_mod._aes_iv = "main_iv_protected"
    handler_mod._aes_key = "main_key_protected"

    ws._subscriptions.add(("H0UNCNT0", "005930"))
    raw = _make_subscribe_success_raw(
        "H0UNCNT0", "005930",
        iv="quote_session_iv_X",
        key="quote_session_key_X",
    )
    await ws._handle_raw(raw)

    # 메인 키 보존
    assert handler_mod._aes_iv == "main_iv_protected"
    assert handler_mod._aes_key == "main_key_protected"


# ===========================================================================
# Case 6: 보조 + 체결통보(이론상 X) SUBSCRIBE SUCCESS → AES 키 저장 SKIP
# 이중 안전망 — 사이클 7-B 가 보조 구독 차단하지만 어쩌다 도착해도 키 보존
# ===========================================================================
@pytest.mark.asyncio
async def test_quote_session_execution_notice_still_skips(reset_aes_keys):
    """이중 안전망: 보조 세션에 체결통보 SUBSCRIBE SUCCESS 가 어쩌다 도착해도 키 저장 skip."""
    ws = KisWebSocket(is_main=False)

    handler_mod._aes_iv = "main_iv_protected"
    handler_mod._aes_key = "main_key_protected"

    ws._subscriptions.add(("H0STCNI0", "HTSID01"))
    raw = _make_subscribe_success_raw(
        "H0STCNI0", "HTSID01",
        iv="quote_exec_iv_X",
        key="quote_exec_key_X",
    )
    await ws._handle_raw(raw)

    # 메인 키 보존 (보조 세션은 무조건 skip)
    assert handler_mod._aes_iv == "main_iv_protected"
    assert handler_mod._aes_key == "main_key_protected"
