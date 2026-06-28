"""사이클 181 (base-1, HIGH) — 토큰만료 분기 substring → msg_cd 화이트리스트 전환 (Red).

`src/api/base.py` 의 토큰만료 분기 (`_request` L560 / `_request_via_quote_pool` L866) 가
순수 substring (`"token" in msg1.lower() or "만료" in msg1`) 이라 KIS `EGW00120` (예수금부족
변형, msg1 "기간이 만료된 code") 등 비-토큰 "만료" 메시지를 토큰만료로 오분류 → 불필요
`issue()` 재발급 + 동일 매수 body 재전송 (중복 체결 race).

확정 시정 설계 (Green 목표):
- `_TOKEN_EXPIRED_MSG_CODES = frozenset({"EGW00121","EGW00122","EGW00123"})` (access token 3종)
- 배제 frozenset `{"EGW00120","APBK0919","APBK0918"}` (예수금/시간외 변형)
- `is_token_expired = (msg_cd.upper() in _TOKEN_EXPIRED_MSG_CODES
      or ("token" in msg1.lower() and msg_cd.upper() not in EXCLUDE and "부족" not in msg1))`
- `"만료" in msg1` 절 영구 폐기.

본 파일은 *행위* 가드 (issue mock call_count + HTTP route call_count) 로 검증한다 —
Green 의 frozenset *이름* 에 결합하지 않는다. 설계 정본:
`_workspace/domain_consult/cycle181_token_expiry_whitelist.md`.
Red 메모: `_workspace/red/cycle181_token_expiry_whitelist.md`.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock

import httpx
import pytest

from src.api import base
from src.api.base import (
    KisApiError,
    get_request_metrics,
    reset_quote_request_metrics,
    reset_request_metrics,
)
from src.auth import token as _token_module

pytestmark = pytest.mark.unit


_ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
_ORDER_TR_ID = "TTTC0012U"
_QUOTE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
_QUOTE_TR_ID = "FHKST01010100"


# ===========================================================================
# Fixtures
# ===========================================================================
@pytest.fixture
def stub_token(monkeypatch: pytest.MonkeyPatch):
    async def _get_token() -> str:
        return "dummy-access-token"

    def _build_headers(tr_id: str, hashkey: str = "") -> dict[str, str]:
        return {
            "authorization": "Bearer dummy",
            "appkey": "test-key",
            "appsecret": "test-secret",
            "tr_id": tr_id,
            "custtype": "P",
        }

    monkeypatch.setattr(_token_module.token_manager, "get_token", _get_token)
    monkeypatch.setattr(_token_module.token_manager, "build_headers", _build_headers)
    return None


@pytest.fixture
def mock_issue(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """`token_manager.issue` 모의 — 재발급 호출 횟수 검증용.

    메인 (`_request`) 과 시세 풀 메인 fallback (`_request_via_quote_pool`) 양쪽이
    동일 `token_manager` 객체의 `issue` 를 호출하므로 단일 패치로 양 사이트 커버.
    """
    m = AsyncMock(return_value=None)
    monkeypatch.setattr(_token_module.token_manager, "issue", m)
    return m


@pytest.fixture
def mock_write_log(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=None)
    import src.db.system_logs as _system_logs_mod

    monkeypatch.setattr(_system_logs_mod, "write_log", mock)
    return mock


@pytest.fixture
def no_backoff(monkeypatch: pytest.MonkeyPatch):
    async def _no_sleep(*_a, **_k) -> None:
        return None

    monkeypatch.setattr(base.asyncio, "sleep", _no_sleep)
    return None


@pytest.fixture
def no_secondary(monkeypatch: pytest.MonkeyPatch):
    """보조 시세 계좌 0개 → `_request_via_quote_pool` 메인 fallback (manager=token_manager)."""

    async def _empty(*_a, **_k):
        return []

    monkeypatch.setattr(
        "src.db.kis_quote_accounts.list_accounts", _empty, raising=False
    )
    if hasattr(base, "_quote_request_index"):
        monkeypatch.setattr(base, "_quote_request_index", 0, raising=False)
    return None


@pytest.fixture(autouse=True)
def reset_metrics_around():
    reset_request_metrics()
    reset_quote_request_metrics()
    yield
    reset_request_metrics()
    reset_quote_request_metrics()


def _join_call_args(call) -> str:
    parts: list[str] = [str(a) for a in call.args]
    parts += [str(v) for v in call.kwargs.values()]
    return " | ".join(parts)


def _kis_json(msg_cd: str, msg1: str, rt_cd: str = "1") -> dict:
    return {"rt_cd": rt_cd, "msg_cd": msg_cd, "msg1": msg1, "output": {}}


def _ok_json() -> dict:
    return {"rt_cd": "0", "msg_cd": "0000", "msg1": "정상", "output": {"ODNO": "1"}}


# ===========================================================================
# _request (메인) — FP (false-positive 차단)
# ===========================================================================
@pytest.mark.asyncio
async def test_fp1_egw00120_buy_rejection_does_not_enter_token_branch(
    mock_kis, stub_token, mock_issue, mock_write_log, no_backoff,
):
    """FP-1 (핵심): EGW00120 예수금부족 매수 거부 ("기간이 만료된 code") →
    토큰 분기 미진입 → issue 0회 + 단일 HTTP 호출 + KisApiError.

    현재 코드: "만료" substring 매칭 → 분기 진입 → issue 3회 + HTTP 3회 → FAIL.
    """
    route = mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$")).respond(
        json=_kis_json("EGW00120", "기간이 만료된 code 입니다"),
    )

    with pytest.raises(KisApiError):
        await base.kis_post(_ORDER_PATH, _ORDER_TR_ID, {"PDNO": "005930"})

    assert mock_issue.call_count == 0, (
        f"EGW00120 예수금부족 거부는 토큰 재발급을 트리거하면 안 됨 "
        f"(issue 호출={mock_issue.call_count})"
    )
    assert route.call_count == 1, (
        f"토큰 분기 미진입 → 재시도 없이 단일 전송이어야 함 "
        f"(동일 매수 body 재전송={route.call_count})"
    )
    # 부수 discriminator: EGW00120 은 token_expired exhaust 로그를 남기면 안 됨
    token_exhaust = [
        c for c in mock_write_log.await_args_list
        if "last_status=token_expired" in _join_call_args(c)
    ]
    assert token_exhaust == [], (
        "EGW00120 은 토큰만료가 아니므로 [api_retry_exhausted] token_expired 금지"
    )


@pytest.mark.asyncio
async def test_fp2_non_token_expiry_message_does_not_enter_token_branch(
    mock_kis, stub_token, mock_issue, mock_write_log, no_backoff,
):
    """FP-2 (핵심): 비-토큰 "만료" msg1 (청약기간 만료, 비-화이트/비-배제 msg_cd) →
    토큰 분기 미진입 → issue 0회.

    현재 코드: "만료" substring 매칭 → 분기 진입 → issue ≥1 → FAIL.
    "만료" 절 폐기 검증.
    """
    route = mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$")).respond(
        json=_kis_json("IGW00001", "청약기간이 만료되었습니다"),
    )

    with pytest.raises(KisApiError):
        await base.kis_post(_ORDER_PATH, _ORDER_TR_ID, {"PDNO": "005930"})

    assert mock_issue.call_count == 0, (
        f"비-토큰 '만료' 메시지는 토큰 재발급 금지 (issue={mock_issue.call_count})"
    )
    assert route.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "msg_cd, msg1",
    [
        ("APBK1943", "시장가호가불가 종목입니다"),
        ("APBK0918", "장운영시간 외 입니다"),
    ],
)
async def test_fp3_non_keyword_rejections_never_enter_token_branch(
    msg_cd, msg1, mock_kis, stub_token, mock_issue, mock_write_log, no_backoff,
):
    """FP-3 (회귀 PASS-PASS): 시장가불가 / 시간외 거부 (token/만료 미포함) →
    토큰 분기 미진입 → issue 0회.

    현재 코드에서도 키워드 미매칭이라 미진입 (이미 0). Green 후에도 미진입 보존.
    """
    mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$")).respond(
        json=_kis_json(msg_cd, msg1),
    )

    with pytest.raises(KisApiError):
        await base.kis_post(_ORDER_PATH, _ORDER_TR_ID, {"PDNO": "005930"})

    assert mock_issue.call_count == 0


# ===========================================================================
# _request (메인) — TP (진짜 토큰만료 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_tp1_real_token_expiry_enters_branch_and_self_heals(
    mock_kis, stub_token, mock_issue, mock_write_log, no_backoff,
):
    """TP-1 (회귀 PASS-PASS): EGW00123 "기간이 만료된 token" → 토큰 분기 진입 →
    issue() ≥1 + continue 재시도 → 재시도서 rt_cd=0 → 최종 성공 (self-heal 보존)."""
    route = mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$"))
    route.side_effect = [
        httpx.Response(200, json=_kis_json("EGW00123", "기간이 만료된 token")),
        httpx.Response(200, json=_ok_json()),
    ]

    data = await base.kis_post(_ORDER_PATH, _ORDER_TR_ID, {"PDNO": "005930"})

    assert data["rt_cd"] == "0", "재시도서 토큰 재발급 후 성공해야 함"
    assert mock_issue.call_count >= 1, "진짜 토큰만료는 issue() 재발급 트리거 보존"


@pytest.mark.asyncio
async def test_tp1b_whitelist_msg_cd_alone_enters_branch(
    mock_kis, stub_token, mock_issue, mock_write_log, no_backoff,
):
    """TP-1b (화이트리스트 load-bearing): EGW00121 (msg1 에 영문 token·만료 *없음*) →
    msg_cd 단독으로 토큰 분기 진입 → issue ≥1 → 재시도 성공.

    현재 코드: msg1 키워드 미매칭 → 미진입 → 즉시 raise (issue 0, 성공 없음) → FAIL.
    화이트리스트가 msg1 wording 과 독립적으로 load-bearing 임을 검증 (자문 정정 1).
    """
    route = mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$"))
    route.side_effect = [
        httpx.Response(200, json=_kis_json("EGW00121", "유효하지 않은 접근입니다")),
        httpx.Response(200, json=_ok_json()),
    ]

    data = await base.kis_post(_ORDER_PATH, _ORDER_TR_ID, {"PDNO": "005930"})

    assert mock_issue.call_count >= 1, (
        "EGW00121 은 msg_cd 단독으로 토큰 분기 진입 → issue 재발급해야 함"
    )
    assert data["rt_cd"] == "0", "화이트리스트 진입 → 재발급 후 self-heal 성공"


@pytest.mark.asyncio
async def test_tp2_token_in_msg_unknown_code_uses_fallback(
    mock_kis, stub_token, mock_issue, mock_write_log, no_backoff,
):
    """TP-2 (회귀 PASS-PASS): msg_cd="" + msg1 에 영문 "token" + 배제코드 아님 →
    "token" 보조 폴백 진입 → issue ≥1 → 재시도 성공 (hybrid 보험)."""
    route = mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$"))
    route.side_effect = [
        httpx.Response(200, json=_kis_json("", "invalid token detected")),
        httpx.Response(200, json=_ok_json()),
    ]

    data = await base.kis_post(_ORDER_PATH, _ORDER_TR_ID, {"PDNO": "005930"})

    assert mock_issue.call_count >= 1, "미등재 msg_cd + msg1 'token' → 폴백 진입 보존"
    assert data["rt_cd"] == "0"


@pytest.mark.asyncio
async def test_tp2_exclude_guard_egw00120_with_token_in_msg(
    mock_kis, stub_token, mock_issue, mock_write_log, no_backoff,
):
    """TP-2 배제 (핵심): EGW00120 + msg1 에 우연히 "token" 포함 → 배제코드이므로
    폴백 미진입 → issue 0회.

    현재 코드: "token" substring 매칭 → 진입 → issue 호출 → FAIL.
    배제 가드 (폴백 오발화 차단) 검증.
    """
    route = mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$")).respond(
        json=_kis_json("EGW00120", "token 기간이 만료된 code 입니다"),
    )

    with pytest.raises(KisApiError):
        await base.kis_post(_ORDER_PATH, _ORDER_TR_ID, {"PDNO": "005930"})

    assert mock_issue.call_count == 0, (
        f"EGW00120 은 배제코드 — msg1 에 'token' 이 우연히 있어도 폴백 미진입 "
        f"(issue={mock_issue.call_count})"
    )
    assert route.call_count == 1


# ===========================================================================
# _request (메인) — EXHAUST (사이클 76 R7 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_exhaust_real_token_expiry_persists_emits_exhausted(
    mock_kis, stub_token, mock_issue, mock_write_log, no_backoff,
):
    """EXHAUST (회귀 PASS-PASS): EGW00123 "기간이 만료된 token" 이 MAX_RETRIES 까지 지속 →
    `[api_retry_exhausted] last_status=token_expired` ERROR 1행 + retry_exhausted==1 + raise.

    사이클 76 R7 (chain 진단 의무) 영속 — 진짜 토큰만료의 최종 실패 로깅 보존.
    """
    mock_kis.post(re.compile(rf".*{re.escape(_ORDER_PATH)}$")).respond(
        json=_kis_json("EGW00123", "기간이 만료된 token"),
    )

    with pytest.raises(KisApiError):
        await base.kis_post(_ORDER_PATH, _ORDER_TR_ID, {"PDNO": "005930"})

    exhausted = [
        c for c in mock_write_log.await_args_list
        if "[api_retry_exhausted]" in _join_call_args(c)
        and "last_status=token_expired" in _join_call_args(c)
    ]
    assert len(exhausted) == 1, (
        f"토큰만료 지속 시 token_expired exhaust 로그 1행 의무: {mock_write_log.await_args_list}"
    )
    assert get_request_metrics()["retry_exhausted"] == 1
    assert mock_issue.call_count >= 1, "진짜 토큰만료는 재발급 시도 보존"


# ===========================================================================
# _request_via_quote_pool (시세 풀) — POOL 대칭 (메인 fallback 경로)
# ===========================================================================
@pytest.mark.asyncio
async def test_pool_fp1_egw00120_does_not_enter_token_branch(
    mock_kis, stub_token, mock_issue, mock_write_log, no_backoff, no_secondary,
):
    """POOL-FP-1 (핵심): 시세 풀 (보조 0개 → 메인 fallback) EGW00120 "기간이 만료된 code" →
    토큰 분기 미진입 → manager.issue 0회 + 단일 호출.

    현재 코드: L866 "만료" 매칭 → 분기 진입 → manager.issue 호출 → FAIL.
    """
    route = mock_kis.get(
        re.compile(rf".*{re.escape(_QUOTE_PATH)}(\?.*)?$")
    ).respond(json=_kis_json("EGW00120", "기간이 만료된 code 입니다"))

    with pytest.raises(KisApiError):
        await base.kis_get_quote(_QUOTE_PATH, _QUOTE_TR_ID, {"fid_input_iscd": "005930"})

    assert mock_issue.call_count == 0, (
        f"시세 풀 EGW00120 도 토큰 재발급 금지 (issue={mock_issue.call_count})"
    )
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_pool_tp1_real_token_expiry_enters_branch(
    mock_kis, stub_token, mock_issue, mock_write_log, no_backoff, no_secondary,
):
    """POOL-TP-1 (회귀 PASS-PASS): 시세 풀 EGW00123 "기간이 만료된 token" →
    토큰 분기 진입 → manager.issue ≥1 + 재시도 → rt_cd=0 성공 (self-heal 대칭 보존)."""
    route = mock_kis.get(re.compile(rf".*{re.escape(_QUOTE_PATH)}(\?.*)?$"))
    route.side_effect = [
        httpx.Response(200, json=_kis_json("EGW00123", "기간이 만료된 token")),
        httpx.Response(
            200,
            json={"rt_cd": "0", "msg_cd": "0000", "msg1": "정상", "output": {"stck_prpr": "1"}},
        ),
    ]

    data = await base.kis_get_quote(_QUOTE_PATH, _QUOTE_TR_ID, {"fid_input_iscd": "005930"})

    assert data["rt_cd"] == "0", "시세 풀도 진짜 토큰만료에서 self-heal 성공 보존"
    assert mock_issue.call_count >= 1


@pytest.mark.asyncio
async def test_pool_exclude_guard_egw00120_with_token_in_msg(
    mock_kis, stub_token, mock_issue, mock_write_log, no_backoff, no_secondary,
):
    """POOL-배제 (핵심): 시세 풀 EGW00120 + msg1 에 우연히 "token" 포함 →
    배제코드 → 폴백 미진입 → manager.issue 0회.

    현재 코드: "token" substring 매칭 → 진입 → manager.issue 호출 → FAIL.
    """
    route = mock_kis.get(
        re.compile(rf".*{re.escape(_QUOTE_PATH)}(\?.*)?$")
    ).respond(json=_kis_json("EGW00120", "token 기간이 만료된 code"))

    with pytest.raises(KisApiError):
        await base.kis_get_quote(_QUOTE_PATH, _QUOTE_TR_ID, {"fid_input_iscd": "005930"})

    assert mock_issue.call_count == 0, (
        f"시세 풀 EGW00120 배제코드는 'token' 우연 포함에도 폴백 미진입 "
        f"(issue={mock_issue.call_count})"
    )
    assert route.call_count == 1
