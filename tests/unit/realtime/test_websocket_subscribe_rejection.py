"""WebSocket 구독 거절 응답 감지 (E2, 2026-05-12).

결함 배경: `src/realtime/websocket.py::_handle_raw()` JSON 응답 처리 분기가
`msg1` 의 `"ERROR"` 단일 키워드만 매칭. KIS 거절 응답 변형(예: "이미 등록된 종목",
"한도 초과", `rt_cd != "0"`)을 감지 못 해 `_subscriptions` set 에 거절된 구독이
잔류 → silently drop 사실 자체를 운영 가시화 못 함.

본 테스트는 다음 사양을 검증한다 (E2 범위만):

1. 거절 판정 조건 (하나라도 매칭):
   - `body.rt_cd` 가 `"0"` 외 값 (1순위, KIS REST 동일 규약). None 이면 skip
   - `msg1` 키워드(대소문자 무시): ERROR / FAIL / REJECT / NOT ALLOWED / LIMIT /
     EXCEED / DUPLICATE / 한도 / 초과 / 이미 / 중복 / 허용되지 / 권한

2. 거절 처리:
   - `self._subscriptions.discard((tr_id, tr_key))` (멱등)
   - ERROR 로그
   - `write_log("ERROR", "[ws_subscribe_reject] tr_id=... tr_key=... rt_cd=... msg_cd=... msg1=...")`
     fire-and-forget — 예외 발생해도 본래 흐름 보존
   - 거절 분기 후 조기 return — 정상 SUBSCRIBE SUCCESS AES iv/key 저장 흐름 분리

3. 정상 응답(SUBSCRIBE SUCCESS) 흐름 영향 없음 — output 의 iv/key 가 AES 저장

4. Heartbeat(PINGPONG) / 비-JSON 캐럿 구분 실시간 데이터 — 거절 분기 진입 안 함
"""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock

import pytest

from src.realtime import websocket as websocket_module
from src.realtime.websocket import KisWebSocket

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _make_reject_raw(tr_id: str, tr_key: str, rt_cd: str, msg_cd: str, msg1: str) -> str:
    """KIS 구독 응답 JSON raw 문자열을 만든다."""
    return json.dumps({
        "header": {"tr_id": tr_id, "tr_key": tr_key},
        "body": {"rt_cd": rt_cd, "msg_cd": msg_cd, "msg1": msg1},
    })


def _make_success_raw_with_aes(tr_id: str, tr_key: str, iv: str, key: str) -> str:
    """SUBSCRIBE SUCCESS + AES iv/key output 포함 raw."""
    return json.dumps({
        "header": {"tr_id": tr_id, "tr_key": tr_key},
        "body": {
            "rt_cd": "0",
            "msg_cd": "OPSP0000",
            "msg1": "SUBSCRIBE SUCCESS",
            "output": {"iv": iv, "key": key},
        },
    })


def _make_pingpong_raw() -> str:
    """Heartbeat PINGPONG raw — rt_cd 누락."""
    return json.dumps({
        "header": {"tr_id": "PINGPONG", "tr_key": ""},
        "body": {},
    })


@pytest.fixture
def patched_write_log(monkeypatch):
    """websocket 모듈에서 참조하는 write_log 를 AsyncMock 으로 대체.

    Green 구현은 `from src.db.system_logs import write_log` 를 모듈 내부에
    추가해야 함 (api/base.py 패턴 차용). 모듈 미존재 시 패치는 setattr 로 만들어
    Green 후 fixture 가 자동으로 hookable.
    """
    mock = AsyncMock(return_value=None)
    # websocket 모듈에 write_log 심볼이 없으면 setattr 로 주입 (Green 후 import 추가됨)
    monkeypatch.setattr(websocket_module, "write_log", mock, raising=False)
    return mock


@pytest.fixture
def ws_with_subscription():
    """`(tr_id, tr_key)` 가 등록된 KisWebSocket 인스턴스."""
    ws = KisWebSocket()
    ws._subscriptions.add(("H0UNCNT0", "005930"))
    return ws


# ---------------------------------------------------------------------------
# Case A — rt_cd != "0" + 한국어 msg1 ("이미 등록된 종목")
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_a_rt_cd_nonzero_already_registered_discards_and_logs(
    ws_with_subscription, patched_write_log, caplog
):
    raw = _make_reject_raw(
        "H0UNCNT0", "005930", rt_cd="1", msg_cd="OPSP0007",
        msg1="이미 등록된 종목입니다",
    )
    with caplog.at_level(logging.ERROR, logger="src.realtime.websocket"):
        await ws_with_subscription._handle_raw(raw)

    assert ("H0UNCNT0", "005930") not in ws_with_subscription._subscriptions, (
        "rt_cd!=0 거절 응답이면 _subscriptions 에서 discard 되어야 함"
    )
    # ERROR 로그
    reject_logs = [
        rec for rec in caplog.records
        if rec.levelno == logging.ERROR and "구독 거절" in rec.getMessage()
    ]
    assert reject_logs, "ERROR 로그 '구독 거절' 미발생"
    # write_log fire-and-forget — prefix [ws_subscribe_reject]
    assert patched_write_log.await_count == 1
    args, _kwargs = patched_write_log.await_args
    assert args[0] == "ERROR"
    log_msg = args[1]
    assert "[ws_subscribe_reject]" in log_msg
    assert "tr_id=H0UNCNT0" in log_msg
    assert "tr_key=005930" in log_msg
    assert "rt_cd=1" in log_msg
    assert "msg_cd=OPSP0007" in log_msg
    assert "이미 등록된 종목입니다" in log_msg


# ---------------------------------------------------------------------------
# Case B — rt_cd != "0" + 한국어 msg1 ("구독 한도 초과")
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_b_rt_cd_nonzero_limit_exceeded_discards_and_logs(
    ws_with_subscription, patched_write_log, caplog
):
    raw = _make_reject_raw(
        "H0UNCNT0", "005930", rt_cd="1", msg_cd="OPSP9999",
        msg1="구독 한도 초과",
    )
    with caplog.at_level(logging.ERROR, logger="src.realtime.websocket"):
        await ws_with_subscription._handle_raw(raw)

    assert ("H0UNCNT0", "005930") not in ws_with_subscription._subscriptions
    assert patched_write_log.await_count == 1
    log_msg = patched_write_log.await_args.args[1]
    assert "[ws_subscribe_reject]" in log_msg
    assert "구독 한도 초과" in log_msg


# ---------------------------------------------------------------------------
# Case C — SUBSCRIBE SUCCESS + AES iv/key 정상 흐름 보존
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_c_subscribe_success_stores_aes_keys_and_does_not_discard(
    ws_with_subscription, patched_write_log, caplog, monkeypatch
):
    # set_aes_keys 호출 spy
    set_aes_calls: list[tuple[str, str]] = []

    def _spy_set_aes_keys(iv: str, key: str) -> None:
        set_aes_calls.append((iv, key))

    monkeypatch.setattr(websocket_module, "set_aes_keys", _spy_set_aes_keys)

    raw = _make_success_raw_with_aes(
        "H0STCNI0", "HTSID01",
        iv="0123456789abcdef",
        key="0123456789abcdef0123456789abcdef",
    )
    with caplog.at_level(logging.ERROR, logger="src.realtime.websocket"):
        await ws_with_subscription._handle_raw(raw)

    # 기존 구독 유지
    assert ("H0UNCNT0", "005930") in ws_with_subscription._subscriptions
    # AES 저장
    assert ws_with_subscription.aes_iv == "0123456789abcdef"
    assert ws_with_subscription.aes_key == "0123456789abcdef0123456789abcdef"
    assert set_aes_calls == [(
        "0123456789abcdef",
        "0123456789abcdef0123456789abcdef",
    )]
    # 거절 로그 없음
    assert not any(
        "구독 거절" in rec.getMessage() for rec in caplog.records
    ), "정상 응답은 거절 로그를 만들지 않아야 함"
    # write_log 호출 없음
    assert patched_write_log.await_count == 0


# ---------------------------------------------------------------------------
# Case D — 영문 ERROR 키워드 (기존 동작 회귀 보호)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_d_msg1_error_keyword_uppercase_regression(
    ws_with_subscription, patched_write_log, caplog
):
    # rt_cd 는 의도적으로 명시하지 않아 (또는 "0") msg1 키워드 단독 매칭 검증
    raw = json.dumps({
        "header": {"tr_id": "H0UNCNT0", "tr_key": "005930"},
        "body": {"rt_cd": "0", "msg_cd": "OPSP****", "msg1": "ERROR: subscribe failed"},
    })
    with caplog.at_level(logging.ERROR, logger="src.realtime.websocket"):
        await ws_with_subscription._handle_raw(raw)

    assert ("H0UNCNT0", "005930") not in ws_with_subscription._subscriptions, (
        "msg1 의 ERROR 키워드 단독 매칭으로도 거절 처리되어야 함 (회귀 보호)"
    )
    assert patched_write_log.await_count == 1


# ---------------------------------------------------------------------------
# Case E — 영문 "FAIL TO SUBSCRIBE"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_e_msg1_fail_keyword_discards(
    ws_with_subscription, patched_write_log
):
    raw = json.dumps({
        "header": {"tr_id": "H0UNCNT0", "tr_key": "005930"},
        "body": {"rt_cd": "0", "msg_cd": "OPSP****", "msg1": "FAIL TO SUBSCRIBE"},
    })
    await ws_with_subscription._handle_raw(raw)

    assert ("H0UNCNT0", "005930") not in ws_with_subscription._subscriptions
    assert patched_write_log.await_count == 1


# ---------------------------------------------------------------------------
# Case F — 한국어 "한도 초과" (rt_cd="0" 인 경우에도 msg1 키워드만으로 거절)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_f_msg1_korean_limit_exceeded_discards(
    ws_with_subscription, patched_write_log
):
    raw = json.dumps({
        "header": {"tr_id": "H0UNCNT0", "tr_key": "005930"},
        "body": {"rt_cd": "0", "msg_cd": "OPSP9999", "msg1": "한도 초과로 구독을 거부합니다"},
    })
    await ws_with_subscription._handle_raw(raw)

    assert ("H0UNCNT0", "005930") not in ws_with_subscription._subscriptions
    assert patched_write_log.await_count == 1
    log_msg = patched_write_log.await_args.args[1]
    assert "한도 초과" in log_msg


# ---------------------------------------------------------------------------
# Case G — Heartbeat PINGPONG (rt_cd 누락) 영향 없음
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_g_pingpong_does_not_affect_subscriptions(
    ws_with_subscription, patched_write_log, caplog
):
    # PINGPONG 분기는 ws.send echo 를 호출하므로 _ws 를 mock
    ws_with_subscription._ws = AsyncMock()

    raw = _make_pingpong_raw()
    with caplog.at_level(logging.ERROR, logger="src.realtime.websocket"):
        await ws_with_subscription._handle_raw(raw)

    # 기존 구독 영향 없음
    assert ("H0UNCNT0", "005930") in ws_with_subscription._subscriptions
    # echo 호출 확인 (PINGPONG 정상 흐름)
    ws_with_subscription._ws.send.assert_awaited_once_with(raw)
    # 거절 처리 없음
    assert not any("구독 거절" in rec.getMessage() for rec in caplog.records)
    assert patched_write_log.await_count == 0


# ---------------------------------------------------------------------------
# Case H — 비-JSON 캐럿 구분 실시간 데이터
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_h_pipe_delimited_realtime_data_skips_json_branch(
    ws_with_subscription, patched_write_log, caplog, monkeypatch
):
    # on_message 콜백 spy — 비-JSON 분기로 정상 진입했는지 확인
    received: list[tuple[str, str, str, bool]] = []

    async def _on_msg(tr_id: str, tr_key: str, payload: str, encrypted: bool) -> None:
        received.append((tr_id, tr_key, payload, encrypted))

    ws_with_subscription._on_message = _on_msg

    raw = "0|H0UNCNT0|001|005930^090000^70000^5^100"
    with caplog.at_level(logging.ERROR, logger="src.realtime.websocket"):
        await ws_with_subscription._handle_raw(raw)

    # 기존 구독 영향 없음
    assert ("H0UNCNT0", "005930") in ws_with_subscription._subscriptions
    # 비-JSON 분기 진입 — on_message 호출됨
    assert len(received) == 1
    assert received[0][0] == "H0UNCNT0"
    assert received[0][1] == "005930"
    # 거절 처리 없음
    assert not any("구독 거절" in rec.getMessage() for rec in caplog.records)
    assert patched_write_log.await_count == 0


# ---------------------------------------------------------------------------
# Case I — 동일 (tr_id, tr_key) 거절 2회 멱등
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_case_i_duplicate_rejection_is_idempotent(
    ws_with_subscription, patched_write_log
):
    raw = _make_reject_raw(
        "H0UNCNT0", "005930", rt_cd="1", msg_cd="OPSP0007",
        msg1="이미 등록된 종목입니다",
    )
    await ws_with_subscription._handle_raw(raw)
    # 두 번째 호출 — 예외 없이 멱등
    await ws_with_subscription._handle_raw(raw)

    assert ("H0UNCNT0", "005930") not in ws_with_subscription._subscriptions
    # write_log 는 2회 모두 호출 (운영 trace 영구 보존 정책)
    assert patched_write_log.await_count == 2


# ---------------------------------------------------------------------------
# 추가 안전성 — write_log 가 예외를 던져도 _handle_raw 정상 종료 (fire-and-forget)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_write_log_failure_does_not_break_handle_raw(
    ws_with_subscription, monkeypatch, caplog
):
    failing = AsyncMock(side_effect=RuntimeError("supabase down"))
    monkeypatch.setattr(websocket_module, "write_log", failing, raising=False)

    raw = _make_reject_raw(
        "H0UNCNT0", "005930", rt_cd="1", msg_cd="OPSP0007",
        msg1="이미 등록",
    )
    with caplog.at_level(logging.ERROR, logger="src.realtime.websocket"):
        await ws_with_subscription._handle_raw(raw)  # 예외 전파 없어야 함

    # discard 는 여전히 수행됨 (정합성 회복 우선)
    assert ("H0UNCNT0", "005930") not in ws_with_subscription._subscriptions
    assert failing.await_count == 1
