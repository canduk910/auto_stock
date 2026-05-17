"""사이클 9 (2026-05-18) — 보조 시세 세션 자동 비활성 contract 검증.

base.py 의 `_request_via_quote_pool` 가 응답 성공/실패에 따라 health_monitor 에
record_success/record_failure 를 호출하고, 임계 초과 시 풀에서 세션이 제거되는
end-to-end 경로를 확인한다.

검증 사양 (4 케이스):
- A: 보조 세션 5xx 5회 연속 → DB active=false + 풀에서 제거 + 영구 로그
- B: TFR 5분 window 60% 실패 (총 10 호출 중 6 실패) → 자동 비활성
- C: 메인 라벨 record_failure 호출해도 비활성 안 됨 (안전 가드)
- D: 비활성된 label 두 번째 호출 idempotent — DB update 1회만
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.contract


@pytest.fixture(autouse=True)
def _reset_health_monitor():
    from src.services import quote_session_health as qsh

    qsh.health_monitor.reset()
    yield
    qsh.health_monitor.reset()


# ---------------------------------------------------------------------------
# 사양 A — 5xx 5회 연속 → 자동 비활성 통합
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_five_consecutive_5xx_failures_trigger_full_auto_disable(monkeypatch):
    """보조 세션 5xx 5회 연속 → (1) DB active=false (2) 풀 제거 (3) 영구 로그 전부 발화."""
    from src.services import quote_session_health as qsh

    update_mock = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="u1")))
    monkeypatch.setattr(qsh, "_db_update_account", update_mock)
    pool_disable_mock = AsyncMock()
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", pool_disable_mock)
    log_mock = AsyncMock()
    monkeypatch.setattr(qsh, "_write_system_log", log_mock)

    for _ in range(5):
        await qsh.health_monitor.record_failure("quote-1", reason="http_503")

    update_mock.assert_awaited_once_with("u1", active=False)
    pool_disable_mock.assert_awaited_once_with("quote-1")
    log_mock.assert_awaited()
    args, _ = log_mock.await_args
    assert "[quote_session_disabled]" in args[1]


# ---------------------------------------------------------------------------
# 사양 B — 5분 60% 실패율
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_5min_window_60_percent_failure_rate_triggers_auto_disable(monkeypatch):
    """5분 window 총 10 호출 중 6 실패 (60%) → 자동 비활성. consecutive 임계는 미달."""
    from src.services import quote_session_health as qsh

    update_mock = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="u2")))
    monkeypatch.setattr(qsh, "_db_update_account", update_mock)
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", AsyncMock())
    monkeypatch.setattr(qsh, "_write_system_log", AsyncMock())

    # F F S F F S F F S F — F=6 S=4 total=10
    # consecutive 는 max 2 (사이사이 S) — 임계 5 미달
    # window rate = 6/10 = 0.6 > 0.5 + min_calls 10 충족 → 비활성
    pattern = ["F", "F", "S", "F", "F", "S", "F", "F", "S", "F"]
    for ev in pattern:
        if ev == "F":
            await qsh.health_monitor.record_failure("quote-2", reason="http_500")
        else:
            await qsh.health_monitor.record_success("quote-2")

    update_mock.assert_awaited_once_with("u2", active=False)


# ---------------------------------------------------------------------------
# 사양 C — 메인 라벨 안전 가드
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_main_label_failures_never_trigger_auto_disable(monkeypatch):
    """메인 라벨 'main' 은 record_failure 5회 누적해도 비활성 발화 0."""
    from src.services import quote_session_health as qsh

    update_mock = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="main-id")))
    monkeypatch.setattr(qsh, "_db_update_account", update_mock)
    pool_disable_mock = AsyncMock()
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", pool_disable_mock)
    monkeypatch.setattr(qsh, "_write_system_log", AsyncMock())

    for _ in range(10):
        await qsh.health_monitor.record_failure("main", reason="http_503")

    update_mock.assert_not_awaited()
    pool_disable_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# 사양 D — 비활성 idempotent
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_already_disabled_label_double_failure_is_idempotent(monkeypatch):
    """이미 비활성된 라벨에 추가 실패 → DB update 재호출 안 함 (`_disabled_labels` 가드)."""
    from src.services import quote_session_health as qsh

    update_mock = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="u3")))
    monkeypatch.setattr(qsh, "_db_update_account", update_mock)
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", AsyncMock())
    monkeypatch.setattr(qsh, "_write_system_log", AsyncMock())

    # 1차 5회 → 비활성
    for _ in range(5):
        await qsh.health_monitor.record_failure("quote-3", reason="http_503")
    assert update_mock.await_count == 1

    # 2차 추가 실패 5회 → idempotent (DB update 재호출 없음)
    for _ in range(5):
        await qsh.health_monitor.record_failure("quote-3", reason="http_503")
    assert update_mock.await_count == 1, "idempotent 위반 — `_disabled_labels` 가드 누락"
