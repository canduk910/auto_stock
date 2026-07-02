"""사이클 189 (2026-07-02) Red — kis_quote_accounts + system_config read retry 확장.

사이클 187 `src/db/supabase.py::execute_with_retry(build, *, retries=1, op="")` 를
2 모듈 read 로 확장하는 시정의 회귀 가드 (헬퍼 자체 변경 0):
- `src/db/kis_quote_accounts.py` read 4곳 (list_accounts / get_account /
  get_account_by_label / get_credentials_for_token_manager)
- `src/db/system_config.py` read 9곳 (get_cash_usage_ratio / get_auto_regime_adjust /
  _get_bool_or_none / get_buy_block_mode / _get_float_or_default / _get_bool_or_default /
  _get_int_or_default / _get_str_or_default_UNUSED / _get_string_or_none)

불변 계약 (187 답습):
- 기존 try/except graceful + 기본값 폴백 전부 불변 (retry 소진 시 마지막 예외가
  기존 except 로 떨어져 동일 폴백).
- 쓰기(_upsert/insert/update/delete/_set_*) 미경유 — 직접 to_thread 유지 (멱등 제외).

Red 유효성 (현재 코드 = read retry 미존재):
- R-1/R-3/R-4/R-5 retry-success 케이스: FAIL — 1회 실패 시 즉시 graceful 폴백.
- R-2 graceful (2회 실패): PASS (불변식, 현재도 동일 폴백).
- R-6 쓰기 미경유 (1회 실패 즉시 전파, 재시도 0): PASS (불변식).

설계 메모: `_workspace/red/cycle189_db_read_retry_expand_and_reprepare_cap.md` 영역 A.

테스트 격리 (사이클 187 daily_read_retry mock 패턴 답습):
- `patch.object(<module>, "supabase", mock)` — 체인 mock `.execute()` side_effect 로 구동.
- asyncio.sleep 전역 patch (autouse) — 재시도 backoff 실지연 0 (타이밍 비의존).
- kis_quote_accounts 60s TTL 캐시는 각 테스트 진입 시 invalidate (autouse) — 캐시 오염 차단.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import src.db.kis_quote_accounts as kqa
import src.db.system_config as sc

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def no_sleep():
    """asyncio.sleep 무력화 — 재시도 backoff 실지연 0 (전역 패치, Red 안전)."""
    with patch("asyncio.sleep", new_callable=AsyncMock):
        yield


@pytest.fixture(autouse=True)
def clear_list_cache():
    """kis_quote_accounts 60s TTL 캐시 오염 차단 (test 간 stale 반환 방지)."""
    kqa.invalidate_list_cache()
    yield
    kqa.invalidate_list_cache()


def _make_supabase(execute_side_effect):
    """모든 체인 링크가 자기 자신 반환 + `.execute()` side_effect 부착한 supabase mock.

    kis_quote_accounts / system_config 양 모듈의 체인 (table/select/eq/order/limit) 커버.

    Returns:
        (mock_supabase, chain) — chain.execute.call_count 로 재시도 횟수 검증.
    """
    chain = MagicMock(name="chain")
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.upsert.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.delete.return_value = chain
    chain.execute.side_effect = execute_side_effect

    mock_sb = MagicMock(name="supabase")
    mock_sb.table.return_value = chain
    return mock_sb, chain


def _result(data):
    """Supabase 응답 mock — data 명시 (MagicMock 자동 child 회피)."""
    r = MagicMock(name="result")
    r.data = data
    return r


def _account_row(label: str = "quote-1"):
    """KisQuoteAccount.from_row 파싱 가능한 완전한 row."""
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "label": label,
        "app_key": "APPKEY-XXXX",
        "app_secret": "secret1234567890",
        "kis_env": "real",
        "active": True,
        "created_at": "2026-06-30T09:00:00+09:00",
        "updated_at": "2026-06-30T09:00:00+09:00",
    }


# ---------------------------------------------------------------------------
# R-1 — list_accounts: 1차 RemoteProtocolError → 재시도 → 정상 rows. Red 핵심.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_R1_list_accounts_retry_then_rows():
    """1차 Server disconnected → execute_with_retry 재시도 → 2차 정상 rows.

    현행 (retry 미존재) = 1회 실패 → except graceful → 빈 캐시 → [] 반환 (Red FAIL).
    """
    mock_sb, chain = _make_supabase(
        [httpx.RemoteProtocolError("Server disconnected"), _result([_account_row()])]
    )

    with patch.object(kqa, "supabase", mock_sb):
        accounts = await kqa.list_accounts()

    assert len(accounts) == 1, "재시도 후 1건 반환 (현행 graceful [] = Red FAIL)"
    assert accounts[0].label == "quote-1"
    assert chain.execute.call_count == 2, "1차 실패 + 2차 성공 = execute 2회 (retry 경유)"


# ---------------------------------------------------------------------------
# R-2 — list_accounts: 2회 연속 실패 → 기존 graceful 폴백 [] (불변식). Red PASS.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_R2_list_accounts_two_failures_graceful():
    """재시도 소진 (2회 실패) → 기존 except 보존 → 빈 list 폴백 (캐시 없음).

    현행 (retry 미존재) 도 1회 실패 → 즉시 graceful [] → 동일 결과 (불변식, PASS).
    """
    mock_sb, _chain = _make_supabase(
        [
            httpx.RemoteProtocolError("disconnect 1"),
            httpx.RemoteProtocolError("disconnect 2"),
        ]
    )

    with patch.object(kqa, "supabase", mock_sb):
        accounts = await kqa.list_accounts()

    assert accounts == [], "재시도 소진 → 기존 graceful 폴백 [] 보존 (캐시 없음)"


# ---------------------------------------------------------------------------
# R-3 — _get_int_or_default: retry 후 성공 → int / 2회 실패 → default
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_R3_get_int_or_default_retry_and_graceful():
    """_get_int_or_default — 1차 실패 → 재시도 → int 반환 / 2회 실패 → default 폴백."""
    # (1) retry 후 성공 → 5000 (현행 retry 미존재 시 default 반환 = Red FAIL)
    mock_sb, chain = _make_supabase(
        [httpx.RemoteProtocolError("Server disconnected"), _result([{"value": {"value": 5000}}])]
    )
    with patch.object(sc, "supabase", mock_sb):
        val = await sc._get_int_or_default("price_filter_min", 999)
    assert val == 5000, "재시도 후 int 반환 (현행 graceful default = Red FAIL)"
    assert chain.execute.call_count == 2, "retry 경유 = execute 2회"

    # (2) 2회 실패 → default (기존 except 보존, 불변식)
    mock_sb2, _chain2 = _make_supabase(
        [httpx.RemoteProtocolError("d1"), httpx.RemoteProtocolError("d2")]
    )
    with patch.object(sc, "supabase", mock_sb2):
        val2 = await sc._get_int_or_default("price_filter_min", 999)
    assert val2 == 999, "재시도 소진 → graceful default 보존"


# ---------------------------------------------------------------------------
# R-4 — _get_bool_or_none: retry 후 성공 → bool (대표 1)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_R4_get_bool_or_none_retry_then_value():
    """_get_bool_or_none — 1차 실패 → 재시도 → True 반환 (현행 graceful None = Red FAIL)."""
    mock_sb, chain = _make_supabase(
        [httpx.RemoteProtocolError("disconnect"), _result([{"value": {"value": True}}])]
    )
    with patch.object(sc, "supabase", mock_sb):
        val = await sc._get_bool_or_none("kis_mcp_enabled")
    assert val is True, "재시도 후 bool 반환 (현행 graceful None = Red FAIL)"
    assert chain.execute.call_count == 2, "retry 경유 = execute 2회"


# ---------------------------------------------------------------------------
# R-5 — get_buy_block_mode: retry 후 성공 → mode / 소진 → HARD 폴백 (매수 가드 소비)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_R5_get_buy_block_mode_retry_and_graceful():
    """get_buy_block_mode — 매수 가드 소비 경로. retry-success → mode / 소진 → 보수적 HARD.

    폴백 보수성 (HARD) 불변 확인 — retry 소진 시에도 매수 차단 기본값 유지.
    """
    # (1) retry 후 성공 → SOFT (현행 retry 미존재 시 HARD 반환 = Red FAIL)
    mock_sb, chain = _make_supabase(
        [httpx.RemoteProtocolError("Server disconnected"), _result([{"value": {"value": "SOFT"}}])]
    )
    with patch.object(sc, "supabase", mock_sb):
        mode = await sc.get_buy_block_mode()
    assert mode == "SOFT", "재시도 후 저장된 mode 반환 (현행 graceful HARD = Red FAIL)"
    assert chain.execute.call_count == 2, "retry 경유 = execute 2회"

    # (2) 2회 실패 → HARD (기존 except 보존, 보수적 폴백 불변)
    mock_sb2, _chain2 = _make_supabase(
        [httpx.RemoteProtocolError("d1"), httpx.RemoteProtocolError("d2")]
    )
    with patch.object(sc, "supabase", mock_sb2):
        mode2 = await sc.get_buy_block_mode()
    assert mode2 == "HARD", "재시도 소진 → 보수적 HARD 폴백 보존 (매수 차단 안전)"


# ---------------------------------------------------------------------------
# R-6 — 쓰기 대표 (_set_int): execute_with_retry 미경유 (1회 실패 즉시 전파). 불변식.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_R6_write_set_int_not_routed_through_retry():
    """쓰기(_set_int) 는 execute_with_retry 미경유 = 직접 to_thread → 1회 실패 즉시 전파.

    retry 경유였다면 RemoteProtocolError 1회는 재시도 → execute 2회. 미경유이므로
    execute 1회 + 예외 즉시 raise (멱등 우려 = 쓰기 retry 금지, 187 결정 영속).
    현재도 PASS (불변식) — Green 후에도 쓰기 경로 불변 유지.
    """
    mock_sb, chain = _make_supabase([httpx.RemoteProtocolError("Server disconnected")])
    with patch.object(sc, "supabase", mock_sb):
        with pytest.raises(httpx.RemoteProtocolError):
            await sc._set_int("price_filter_min", 5000)
    assert chain.execute.call_count == 1, "쓰기 = 재시도 0 (execute 1회, 즉시 전파)"
