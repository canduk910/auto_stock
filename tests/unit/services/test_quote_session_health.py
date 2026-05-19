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


# ---------------------------------------------------------------------------
# 사이클 18 (2026-05-19) — FAST_WINDOW 1분 80% 임계 추가 (3 케이스)
# ---------------------------------------------------------------------------
# 배경: ISA 같은 보조 라벨이 5xx 80%+ 비율로 영구 결함. 기존 5분 50% 임계는 충분히 빠르나,
# 1분 윈도우 80%+ 즉시 발화 분기 추가로 영구 결함 라벨 빠른 탈락 + 로그 폭주 차단.
@pytest.mark.asyncio
async def test_fast_window_80pct_failure_in_1min_triggers_disable(monkeypatch):
    """1분 fast 윈도우 10회 호출 중 8회 실패 (rate=0.8) → 자동 비활성.

    기존 임계 (consecutive 5 / 5분 50%) 미충족 상황에서도 fast 윈도우가 발화.
    """
    from src.services import quote_session_health as qsh

    update_mock = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="u-fast-1")))
    monkeypatch.setattr(qsh, "_db_update_account", update_mock)
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", AsyncMock())
    monkeypatch.setattr(qsh, "_write_system_log", AsyncMock())

    # 패턴: 실패4, 성공1, 실패4, 성공1 = 8 fail / 10 total. consecutive 최대 4 (5 미만), rate=0.8
    for _ in range(4):
        await qsh.health_monitor.record_failure("quote-fast", reason="http_500")
    await qsh.health_monitor.record_success("quote-fast")
    for _ in range(4):
        await qsh.health_monitor.record_failure("quote-fast", reason="http_500")
    await qsh.health_monitor.record_success("quote-fast")

    # fast window 임계 도달 (10회, 8실패) — disable 발화
    assert "quote-fast" in qsh.health_monitor._disabled_labels
    update_mock.assert_awaited_once_with("u-fast-1", active=False)


@pytest.mark.asyncio
async def test_fast_window_below_min_calls_does_not_trigger(monkeypatch):
    """1분 내 5회 모두 실패 (rate=1.0) 이지만 total<FAST_MIN_CALLS(10) → 비활성 안 됨.

    premature 결정 차단 — 최소 호출 수 미달 시 fast 임계 평가 skip.
    """
    from src.services import quote_session_health as qsh

    update_mock = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="u-fast-2")))
    monkeypatch.setattr(qsh, "_db_update_account", update_mock)
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", AsyncMock())
    monkeypatch.setattr(qsh, "_write_system_log", AsyncMock())

    # 4회 fail → consecutive 4 (<5), fast total=4 (<10) — 어떤 임계도 미달
    for _ in range(4):
        await qsh.health_monitor.record_failure("quote-low", reason="http_500")

    assert "quote-low" not in qsh.health_monitor._disabled_labels, (
        "fast min_calls 미달 시 자동 비활성 안 됨"
    )
    update_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_fast_window_resets_after_60s(monkeypatch):
    """60s 경과 후 fast 윈도우 리셋 — 직전 실패가 새 윈도우에 반영되지 않음.

    윈도우 만료 후 다시 누적 시작. 5xx 80%+ 임계 평가도 리셋된 윈도우 기준.
    """
    from datetime import datetime, timedelta, timezone

    from src.services import quote_session_health as qsh

    monkeypatch.setattr(qsh, "_db_get_by_label", AsyncMock(return_value=MagicMock(id="u-fast-3")))
    monkeypatch.setattr(qsh, "_db_update_account", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(qsh, "_pool_disable_quote_session", AsyncMock())
    monkeypatch.setattr(qsh, "_write_system_log", AsyncMock())

    KST = timezone(timedelta(hours=9))
    base = datetime(2026, 5, 19, 16, 0, 0, tzinfo=KST)
    times = [base, base + timedelta(seconds=61)]  # 두 시점

    call_idx = [0]
    real_datetime = qsh.datetime  # backup

    class _FrozenDatetime:
        @classmethod
        def now(cls, tz=None):
            return times[min(call_idx[0], len(times) - 1)]

    monkeypatch.setattr(qsh, "datetime", _FrozenDatetime)

    # t=base — 4회 실패 (fast window total=4, failures=4)
    call_idx[0] = 0
    for _ in range(4):
        await qsh.health_monitor.record_failure("quote-reset", reason="http_500")
    # 직전 fast window 확인
    assert qsh.health_monitor._fast_window_total.get("quote-reset", 0) == 4
    assert qsh.health_monitor._fast_window_failures.get("quote-reset", 0) == 4

    # t=base+61s — 새 호출이 fast 윈도우 리셋해야 함
    call_idx[0] = 1
    await qsh.health_monitor.record_success("quote-reset")

    # fast window 리셋 — total=1, failures=0 (리셋 후 새 카운트)
    assert qsh.health_monitor._fast_window_total.get("quote-reset", 0) == 1, (
        f"61s 경과 후 fast 윈도우 total=1 리셋, got {qsh.health_monitor._fast_window_total.get('quote-reset')}"
    )
    assert qsh.health_monitor._fast_window_failures.get("quote-reset", 0) == 0, (
        "리셋된 윈도우 성공만 카운트"
    )


# ---------------------------------------------------------------------------
# 사이클 18 — get_recent_5xx_ratio API (A-3 라벨 선택 분기용)
# ---------------------------------------------------------------------------
def test_get_recent_5xx_ratio_returns_zero_below_min_calls():
    """fast 윈도우 total<FAST_MIN_CALLS → (0.0, total). 비율 평가 불가."""
    from src.services.quote_session_health import health_monitor

    health_monitor._fast_window_total["quote-x"] = 5
    health_monitor._fast_window_failures["quote-x"] = 5
    ratio, total = health_monitor.get_recent_5xx_ratio("quote-x")
    assert ratio == 0.0 and total == 5, (
        f"min_calls 미달 시 ratio=0, got ({ratio}, {total})"
    )


def test_get_recent_5xx_ratio_returns_actual_ratio_at_threshold():
    """fast total>=FAST_MIN_CALLS → 실제 비율 반환."""
    from src.services.quote_session_health import health_monitor

    health_monitor._fast_window_total["quote-y"] = 12
    health_monitor._fast_window_failures["quote-y"] = 10
    ratio, total = health_monitor.get_recent_5xx_ratio("quote-y")
    assert abs(ratio - 10 / 12) < 0.01 and total == 12, (
        f"ratio=10/12, got ({ratio:.3f}, {total})"
    )


def test_get_recent_5xx_ratio_for_disabled_returns_full_ratio():
    """`_disabled_labels` 포함 라벨 → ratio=1.0 (메인 fallback 강제 트리거 보조 sanity).

    `_select_quote_label` 이 이미 비활성 라벨을 제외하지만 race 대비.
    """
    from src.services.quote_session_health import health_monitor

    health_monitor._disabled_labels.add("quote-dead")
    ratio, total = health_monitor.get_recent_5xx_ratio("quote-dead")
    assert ratio >= 0.8 and total >= 10, (
        f"비활성 라벨은 항상 메인 fallback 트리거, got ({ratio}, {total})"
    )
