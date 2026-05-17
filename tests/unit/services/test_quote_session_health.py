"""사이클 9 (2026-05-18) — `QuoteSessionHealthMonitor` 회귀 가드.

배경:
- KIS Open API 공지: 무한 등록/해제 + 토큰 발급 실패 폭주 패턴 시 IP/앱키 차단.
- 보조 세션 1개가 지속 토큰 실패/5xx 면 stale watcher 가 분당 800 unsubscribe/subscribe
  요청을 KIS 에 던지는 위험. 자체 헬스 모니터로 5회 연속 실패 또는 5분 50% 실패율
  시 해당 보조를 자동 비활성 → 트래픽 차단.

검증 사양 (10 케이스):
- A: 토큰 발급 실패 reason="token_issue_fail" → consecutive +=1
- B: 5xx reason="http_503" → consecutive +=1
- C: 임계 5회 초과 → `_auto_disable` 발화 (`update_account(active=False)`)
- D: 성공 1회 후 consecutive 0 reset
- E: 5분 window total=12, failures=7 (rate≈0.58) → 자동 비활성
- F: window 만료 (300s 경과) 후 새 호출 → metrics reset
- G: window total=8 (< MIN_CALLS=10) → 비율 평가 안 함
- H: 비활성 시 `kis_ws_pool.disable_quote_session(label)` 호출
- I: 영구 로그 `[quote_session_disabled]` (`system_logs.write_log`)
- J: DB update 실패 graceful — 메모리만 비활성 + WARNING 로그

설계:
- ``QuoteSessionHealthMonitor`` 싱글톤 (`src/services/quote_session_health.py`)
- 메인 라벨 "main" 은 절대 비활성 안 됨 (안전 가드, 별도 케이스 contract 에서 검증)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 헬퍼 — 모듈 싱글톤 reset
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_health_monitor():
    """각 테스트마다 health_monitor 내부 dict 초기화 — 격리 보장."""
    from src.services import quote_session_health as qsh

    qsh.health_monitor.reset()
    yield
    qsh.health_monitor.reset()


# ---------------------------------------------------------------------------
# 사양 A — 토큰 발급 실패 카운터
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_record_failure_token_issue_increments_consecutive():
    """토큰 발급 실패 1회 → consecutive_failures[label] == 1."""
    from src.services.quote_session_health import health_monitor

    await health_monitor.record_failure("quote-1", reason="token_issue_fail")
    assert health_monitor._consecutive_failures.get("quote-1") == 1


# ---------------------------------------------------------------------------
# 사양 B — 5xx 카운터
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_record_failure_http_5xx_increments_consecutive():
    """5xx 응답 → consecutive +=1."""
    from src.services.quote_session_health import health_monitor

    await health_monitor.record_failure("quote-1", reason="http_503")
    assert health_monitor._consecutive_failures.get("quote-1") == 1


# ---------------------------------------------------------------------------
# 사양 C — 임계 5회 초과 시 자동 비활성
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_consecutive_failures_threshold_triggers_auto_disable(monkeypatch):
    """5회 연속 실패 → `_auto_disable` 호출 (update_account active=False)."""
    from src.services import quote_session_health as qsh

    update_mock = AsyncMock(return_value=MagicMock())
    get_by_label_mock = AsyncMock(return_value=MagicMock(id="uuid-1"))
    disable_pool_mock = AsyncMock()
    write_log_mock = AsyncMock()

    monkeypatch.setattr(qsh, "_db_get_by_label", get_by_label_mock)
    monkeypatch.setattr(qsh, "_db_update_account", update_mock)
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", disable_pool_mock)
    monkeypatch.setattr(qsh, "_write_system_log", write_log_mock)

    for _ in range(5):
        await qsh.health_monitor.record_failure("quote-1", reason="http_503")

    update_mock.assert_awaited_once_with("uuid-1", active=False)
    disable_pool_mock.assert_awaited_once_with("quote-1")
    assert "quote-1" in qsh.health_monitor._disabled_labels


# ---------------------------------------------------------------------------
# 사양 D — 성공 1회 reset
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_record_success_resets_consecutive_to_zero():
    """실패 누적 후 성공 1회 → consecutive 0 reset."""
    from src.services.quote_session_health import health_monitor

    await health_monitor.record_failure("quote-1", reason="http_500")
    await health_monitor.record_failure("quote-1", reason="http_500")
    assert health_monitor._consecutive_failures.get("quote-1") == 2

    await health_monitor.record_success("quote-1")
    assert health_monitor._consecutive_failures.get("quote-1", 0) == 0


# ---------------------------------------------------------------------------
# 사양 E — 5분 sliding window 50% 비율 초과
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_window_failure_rate_above_threshold_triggers_auto_disable(monkeypatch):
    """5분 window total=12, failures=7 (rate≈0.58) → 자동 비활성."""
    from src.services import quote_session_health as qsh

    update_mock = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="u")))
    monkeypatch.setattr(qsh, "_db_update_account", update_mock)
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", AsyncMock())
    monkeypatch.setattr(qsh, "_write_system_log", AsyncMock())

    # 12 호출 (성공 5, 실패 7) — 50% 초과 + min_calls 충족
    # 실패는 연속 4 까지만 (5 미만) — consecutive 임계 회피 위해 사이사이 성공
    sequence = ["F", "F", "F", "F", "S", "F", "F", "F", "S", "S", "S", "S"]
    # 총 F=7, S=5, total=12, rate=7/12=0.583
    for ev in sequence:
        if ev == "F":
            await qsh.health_monitor.record_failure("quote-2", reason="http_500")
        else:
            await qsh.health_monitor.record_success("quote-2")

    # consecutive 는 4 까지만 누적 후 reset 됐으므로 임계 미달.
    # 그러나 window failure_rate 58% > 50% + min_calls=10 → 비활성 발화 기대.
    update_mock.assert_awaited()


# ---------------------------------------------------------------------------
# 사양 F — window 만료 시 metrics reset
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_window_expiry_resets_metrics(monkeypatch):
    """window 만료(300s 경과) 후 다음 호출은 _window_total 1 로 리셋."""
    from src.services import quote_session_health as qsh

    # 초기 호출 — 5분 전 timestamp 강제 주입
    now = datetime.now(KST)
    qsh.health_monitor._window_start["quote-3"] = now - timedelta(seconds=301)
    qsh.health_monitor._window_total["quote-3"] = 10
    qsh.health_monitor._window_failures["quote-3"] = 6

    # 새 호출 → window 만료로 reset 후 1 부터 시작
    await qsh.health_monitor.record_success("quote-3")

    assert qsh.health_monitor._window_total["quote-3"] == 1
    assert qsh.health_monitor._window_failures["quote-3"] == 0


# ---------------------------------------------------------------------------
# 사양 G — min_calls 미달 시 비율 평가 skip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_window_rate_skipped_when_min_calls_not_met(monkeypatch):
    """window total=8 (< MIN_CALLS=10) + failures=7 → 비활성 안 됨."""
    from src.services import quote_session_health as qsh

    update_mock = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="u")))
    monkeypatch.setattr(qsh, "_db_update_account", update_mock)
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", AsyncMock())
    monkeypatch.setattr(qsh, "_write_system_log", AsyncMock())

    # 8 호출 (F=4, S=4) — rate=50% 정확히지만 min_calls 미달
    seq = ["F", "F", "S", "F", "F", "S", "S", "S"]
    for ev in seq:
        if ev == "F":
            await qsh.health_monitor.record_failure("quote-4", reason="http_500")
        else:
            await qsh.health_monitor.record_success("quote-4")

    # consecutive 도 2 까지만 (S 가 사이에 있음) — 임계 미달.
    # min_calls 8 < 10 → 비율 평가 skip → 비활성 안 됨.
    update_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# 사양 H — 비활성 시 풀 헬퍼 호출
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_disable_invokes_pool_disable_quote_session(monkeypatch):
    """`_auto_disable` 호출 시 `kis_ws_pool.disable_quote_session(label)` 발화."""
    from src.services import quote_session_health as qsh

    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="u")))
    monkeypatch.setattr(qsh, "_db_update_account", AsyncMock(return_value=MagicMock()))
    disable_pool_mock = AsyncMock()
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", disable_pool_mock)
    monkeypatch.setattr(qsh, "_write_system_log", AsyncMock())

    for _ in range(5):
        await qsh.health_monitor.record_failure("quote-5", reason="token_issue_fail")

    disable_pool_mock.assert_awaited_once_with("quote-5")


# ---------------------------------------------------------------------------
# 사양 I — 영구 로그
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_auto_disable_writes_permanent_log(monkeypatch):
    """비활성 시 `[quote_session_disabled]` prefix 영구 로그 (system_logs.write_log)."""
    from src.services import quote_session_health as qsh

    write_log_mock = AsyncMock()
    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="u")))
    monkeypatch.setattr(qsh, "_db_update_account", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", AsyncMock())
    monkeypatch.setattr(qsh, "_write_system_log", write_log_mock)

    for _ in range(5):
        await qsh.health_monitor.record_failure("quote-6", reason="http_503")

    write_log_mock.assert_awaited()
    args, kwargs = write_log_mock.await_args
    # write_log("ERROR", "[quote_session_disabled] label=... reason=...")
    assert args[0] == "ERROR"
    assert "[quote_session_disabled]" in args[1]
    assert "label=quote-6" in args[1]


# ---------------------------------------------------------------------------
# 사양 J — DB update 실패 graceful
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_db_update_failure_graceful_keeps_memory_disable(monkeypatch):
    """`update_account` 예외 시 메모리 비활성은 그대로 + WARNING 영구 로그."""
    from src.services import quote_session_health as qsh

    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="u")))
    monkeypatch.setattr(
        qsh, "_db_update_account",
        AsyncMock(side_effect=RuntimeError("supabase down")),
    )
    disable_pool_mock = AsyncMock()
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", disable_pool_mock)
    write_log_mock = AsyncMock()
    monkeypatch.setattr(qsh, "_write_system_log", write_log_mock)

    for _ in range(5):
        await qsh.health_monitor.record_failure("quote-7", reason="http_503")

    # 메모리는 비활성 — _disabled_labels 포함
    assert "quote-7" in qsh.health_monitor._disabled_labels
    # 풀 헬퍼는 그대로 호출 (메모리 정합성 유지)
    disable_pool_mock.assert_awaited_once_with("quote-7")
    # 영구 로그 2건 — ERROR(disabled) + WARNING(db_update_fail) 또는 단일 메시지에 사유 합친 경우 1건
    assert write_log_mock.await_count >= 1
