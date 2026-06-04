"""사이클 57 V-1 — 매도 거부 폭주 실시간 알람 단위 테스트.

배경:
    사이클 52 B-1 의 10분 500건 매도 거부 폭주가 실시간 운영자 알람 없이 다음 날
    20:10 자동 리포트에서야 발견됨. 사이클 55 R-1 2단계 TTL 로 폭주 자체는 차단되지만
    "왜 폭주가 발생했는지" 의 즉시 가시성 부재 → V-1 에서 CRITICAL system_logs 알람 추가.

핵심 결정 (team-leader D-1 ~ D-7):
    - D-1: 10분 윈도우 / 5건 초과 (6건째 발화)
    - D-2: 30분 cooldown per-ticker
    - D-3: system_logs CRITICAL 만 (외부 채널 별 사이클)
    - D-4: tracker 독립 최소 메시지 (registry/positions 의존 X)
    - D-5: _append_history 내부 자동 발화 (4 채널 공통 진입점)

테스트 매트릭스 (12 케이스):
    V1-1:  임계 미만 (5건 이하) → 알람 없음
    V1-2:  임계 도달 (6건째) → CRITICAL 알람 1회 발화
    V1-3:  cooldown 중 (30분 내) → 알람 skip
    V1-4:  cooldown 만료 (30분+) → 재발화
    V1-5:  메시지 포맷 정확성 — [매도거부폭주] + ticker + count + threshold=5 + reasons + last_msg_cd + occurred_at_kst
    V1-6:  다른 ticker 격리 — A 임계 도달 후 B 영향 없음
    V1-7:  _history deque maxlen=20 보존
    V1-8:  10분 윈도우 밖 거부 제외 — 6건 중 1건이 11분 전이면 5건만 → 알람 없음
    V1-9:  reset_daily() 동행 — _alarm_last_emitted clear → 재발화
    V1-10: 4 register 메서드 각각 6회 호출 시 알람 1회
    V1-11: safe_write_log mock 호출 검증 (CRITICAL level + 메시지 포함)
    V1-12: 사이클 55 R-1 호환 — get_recent_rejections 정상 동작

Mock 전략:
    asyncio.create_task 와 safe_write_log 를 동시 patch.
    create_task: 호출 횟수 카운트 + 코루틴 즉시 close (unawaited 경고 방지).
    safe_write_log: noop async 함수 또는 캡처 async 함수.
    이 두 patch 조합으로 unawaited coroutine PytestWarning 완전 차단.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))


def _now(hour: int = 11, minute: int = 0, second: int = 0) -> datetime:
    """2026-06-04 KST aware datetime 헬퍼."""
    return datetime(2026, 6, 4, hour, minute, second, tzinfo=_KST)


def _make_tracker():
    """SellRejectionTracker 신규 인스턴스 생성."""
    from src.engine.sell_rejection import SellRejectionTracker
    return SellRejectionTracker()


@contextmanager
def _patch_alarm(*, capture: bool = False) -> Iterator[dict]:
    """asyncio.create_task + safe_write_log 동시 patch 컨텍스트.

    Returns:
        dict 키:
            task_count: int (create_task 호출 횟수)
            captured: list[(level, message)] (capture=True 시)
    """
    state: dict = {"task_count": 0, "captured": []}

    async def noop_write_log(level: str, message: str, *, fallback_debug=None):
        if capture:
            state["captured"].append((level, message))

    def fake_create_task(coro):
        state["task_count"] += 1
        # 동기 실행 — unawaited 경고 방지
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()
        return MagicMock()

    with patch("src.engine.sell_rejection.safe_write_log", noop_write_log):
        with patch("src.engine.sell_rejection.asyncio") as mock_asyncio:
            mock_asyncio.create_task = fake_create_task
            yield state


# ===========================================================================
# V1-1: 임계 미만 (5건 이하) → 알람 없음
# ===========================================================================

def test_v1_1_below_threshold_no_alarm():
    """5건 (임계 정확히 일치) → create_task 호출 없음."""
    tracker = _make_tracker()
    now = _now()

    with _patch_alarm() as s:
        for i in range(5):
            tracker.record_rejection(
                "005930", "market_closed", "APBK0918", "장운영시간외",
                now + timedelta(seconds=i),
            )

    assert s["task_count"] == 0, f"5건에서 알람 발화 금지: {s['task_count']}"


# ===========================================================================
# V1-2: 임계 도달 (6건째) → CRITICAL 알람 1회 발화
# ===========================================================================

def test_v1_2_threshold_exceeded_alarm_emitted():
    """6건째 record_rejection 시 CRITICAL 알람 정확히 1회 발화."""
    tracker = _make_tracker()
    now = _now()

    with _patch_alarm() as s:
        for i in range(6):
            tracker.record_rejection(
                "005930", "market_closed", "APBK0918", "장운영시간외",
                now + timedelta(seconds=i),
            )

    assert s["task_count"] == 1, f"6건째에서 create_task 1회 기대: {s['task_count']}"


# ===========================================================================
# V1-3: cooldown 중 → 알람 skip
# ===========================================================================

def test_v1_3_during_cooldown_alarm_skipped():
    """6건 알람 발화 후 30분 내 추가 임계 도달 시 알람 skip."""
    tracker = _make_tracker()
    base = _now()

    with _patch_alarm() as s:
        # 1차 알람: 6건
        for i in range(6):
            tracker.record_rejection(
                "005930", "market_closed", "APBK0918", "장운영시간외",
                base + timedelta(seconds=i),
            )

        assert s["task_count"] == 1, "1차 알람 1회 기대"

        # cooldown 중 (29분 후) 추가 6건
        cooldown_base = base + timedelta(minutes=29)
        for i in range(6):
            tracker.record_rejection(
                "005930", "market_closed", "APBK0918", "장운영시간외",
                cooldown_base + timedelta(seconds=i),
            )

    assert s["task_count"] == 1, f"cooldown 중 재발화 금지: {s['task_count']}"


# ===========================================================================
# V1-4: cooldown 만료 후 재발화
# ===========================================================================

def test_v1_4_after_cooldown_expiry_alarm_reemitted():
    """30분 cooldown 만료 후 임계 재도달 시 알람 재발화."""
    tracker = _make_tracker()
    base = _now()

    with _patch_alarm() as s:
        # 1차 알람
        for i in range(6):
            tracker.record_rejection(
                "005930", "market_closed", "APBK0918", "장운영시간외",
                base + timedelta(seconds=i),
            )
        assert s["task_count"] == 1, "1차 알람 1회"

        # cooldown 만료 후 (31분) 신규 6건 — 모두 31분 이후 시각이므로 10분 윈도우 내
        expired_base = base + timedelta(minutes=31)
        for i in range(6):
            tracker.record_rejection(
                "005930", "market_closed", "APBK0918", "장운영시간외",
                expired_base + timedelta(seconds=i),
            )

    assert s["task_count"] == 2, f"cooldown 만료 후 재발화 기대: {s['task_count']}"


# ===========================================================================
# V1-5: 메시지 포맷 정확성
# ===========================================================================

def test_v1_5_message_format_accuracy():
    """알람 메시지에 필수 필드 모두 포함 검증."""
    tracker = _make_tracker()
    now = _now(11, 30, 0)

    with _patch_alarm(capture=True) as s:
        for i in range(6):
            tracker.record_rejection(
                "000660", "market_closed", "APBK0918", "장운영시간외",
                now + timedelta(seconds=i),
            )

    assert len(s["captured"]) == 1, "알람 1회 발화 기대"
    level, msg = s["captured"][0]
    assert level == "CRITICAL", f"레벨 CRITICAL 기대: {level}"
    assert "[매도거부폭주]" in msg, f"[매도거부폭주] 미포함: {msg}"
    assert "ticker=000660" in msg, f"ticker= 미포함: {msg}"
    assert "count=6" in msg, f"count=6 미포함: {msg}"
    assert "threshold=5" in msg, f"threshold=5 미포함: {msg}"
    assert "reasons=" in msg, f"reasons= 미포함: {msg}"
    assert "last_msg_cd=" in msg, f"last_msg_cd= 미포함: {msg}"
    assert "occurred_at_kst=" in msg, f"occurred_at_kst= 미포함: {msg}"


# ===========================================================================
# V1-6: 다른 ticker 격리
# ===========================================================================

def test_v1_6_different_ticker_isolation():
    """ticker A 임계 도달 후 ticker B 는 독립 — 상호 영향 없음."""
    tracker = _make_tracker()
    now = _now()

    with _patch_alarm() as s:
        # ticker A: 6건 → 알람 발화
        for i in range(6):
            tracker.record_rejection(
                "005930", "market_closed", "APBK0918", "장운영시간외",
                now + timedelta(seconds=i),
            )
        assert s["task_count"] == 1, "ticker A 알람 1회 기대"

        # ticker B: 5건 → 알람 없음
        for i in range(5):
            tracker.record_rejection(
                "000660", "market_closed", "APBK0918", "장운영시간외",
                now + timedelta(seconds=i),
            )

    assert s["task_count"] == 1, f"ticker B 5건에서 알람 추가 발화 금지: {s['task_count']}"


# ===========================================================================
# V1-7: deque maxlen=20 보존
# ===========================================================================

def test_v1_7_deque_maxlen_preserved():
    """21번째 push 시 가장 오래된 이벤트 evict — deque 길이 항상 20 이하."""
    tracker = _make_tracker()
    now = _now()

    # 30건 적재 — 처음 6건에서 1차 알람 발화, 이후 cooldown 내
    with _patch_alarm() as _:
        for i in range(30):
            tracker.record_rejection(
                "035420", "market_closed", "APBK0918", "장운영시간외",
                now + timedelta(seconds=i),
            )

    events = tracker.get_recent_rejections("035420")
    assert len(events) == 20, f"maxlen=20 초과: {len(events)}"
    from src.engine.sell_rejection import RejectionEvent
    assert all(isinstance(e, RejectionEvent) for e in events)


# ===========================================================================
# V1-8: 10분 윈도우 밖 이벤트 제외
# ===========================================================================

def test_v1_8_events_outside_window_excluded():
    """11분 전 이벤트 5건 + 현재 이벤트 5건 → 윈도우 내 5건만 → 알람 없음."""
    tracker = _make_tracker()
    now = _now(11, 30, 0)

    with _patch_alarm() as s:
        # 11분 전 5건 (윈도우 밖)
        old_base = now - timedelta(minutes=11)
        for i in range(5):
            tracker.record_rejection(
                "068270", "market_closed", "APBK0918", "장운영시간외",
                old_base + timedelta(seconds=i),
            )

        # 현재 5건 (윈도우 내) — 마지막 record 의 now_kst=now+4s 기준 윈도우 평가
        for i in range(5):
            tracker.record_rejection(
                "068270", "market_closed", "APBK0918", "장운영시간외",
                now + timedelta(seconds=i),
            )

    assert s["task_count"] == 0, f"윈도우 내 5건으로 알람 발화 금지: {s['task_count']}"


# ===========================================================================
# V1-9: reset_daily() 동행 — _alarm_last_emitted clear
# ===========================================================================

def test_v1_9_reset_daily_clears_alarm_cooldown():
    """reset_daily() 후 cooldown 초기화 → 동일 ticker 즉시 재발화 가능."""
    tracker = _make_tracker()
    now = _now()

    with _patch_alarm() as s:
        # 1차 알람 (cooldown 등록)
        for i in range(6):
            tracker.record_rejection(
                "005930", "market_closed", "APBK0918", "장운영시간외",
                now + timedelta(seconds=i),
            )
        assert s["task_count"] == 1

        # reset_daily() → _alarm_last_emitted clear
        tracker.reset_daily()

        # history 도 clear 되었으므로 새 이벤트 6건 추가
        # cooldown 내 시각이지만 _alarm_last_emitted 가 clear 되어 재발화 가능
        new_now = now + timedelta(minutes=2)  # cooldown 중이지만 reset 후이므로 발화
        for i in range(6):
            tracker.record_rejection(
                "005930", "market_closed", "APBK0918", "장운영시간외",
                new_now + timedelta(seconds=i),
            )

    assert s["task_count"] == 2, f"reset_daily 후 재발화 기대: {s['task_count']}"


# ===========================================================================
# V1-10: 4 register 메서드 각각 6회 호출 시 알람 1회
# ===========================================================================

class TestV110FourChannelsAllTriggerAlarm:
    """4 채널 각각 독립 6회 → 알람 1회.

    register_market_closed / register_market_order_disallowed /
    register_insufficient_quantity / record_rejection 모두 _append_history 경유.
    """

    def _run_channel_test(self, register_fn, ticker: str) -> int:
        """register_fn 6회 호출 후 create_task 호출 횟수 반환."""
        with _patch_alarm() as s:
            now = _now()
            for i in range(6):
                register_fn(ticker, now + timedelta(seconds=i))
        return s["task_count"]

    def test_register_market_closed_triggers_alarm(self):
        """register_market_closed 6회 → 알람 1회."""
        tracker = _make_tracker()
        count = self._run_channel_test(
            lambda t, ts: tracker.register_market_closed(t, ts, in_krx_main_hours=True),
            "005930",
        )
        assert count == 1, f"register_market_closed 알람 1회 기대: {count}"

    def test_register_market_order_disallowed_triggers_alarm(self):
        """register_market_order_disallowed 6회 → 알람 1회."""
        tracker = _make_tracker()
        count = self._run_channel_test(
            lambda t, ts: tracker.register_market_order_disallowed(
                t, ts, is_nxt_session=False, fallback_succeeded=True
            ),
            "000660",
        )
        assert count == 1, f"register_market_order_disallowed 알람 1회 기대: {count}"

    def test_register_insufficient_quantity_triggers_alarm(self):
        """register_insufficient_quantity 6회 → 알람 1회."""
        tracker = _make_tracker()
        count = self._run_channel_test(
            lambda t, ts: tracker.register_insufficient_quantity(t, ts),
            "035420",
        )
        assert count == 1, f"register_insufficient_quantity 알람 1회 기대: {count}"

    def test_record_rejection_triggers_alarm(self):
        """record_rejection 6회 → 알람 1회."""
        tracker = _make_tracker()
        count = self._run_channel_test(
            lambda t, ts: tracker.record_rejection(
                t, "market_closed", "APBK0918", "장운영시간외", ts
            ),
            "068270",
        )
        assert count == 1, f"record_rejection 알람 1회 기대: {count}"


# ===========================================================================
# V1-11: safe_write_log CRITICAL 호출 검증
# ===========================================================================

def test_v1_11_safe_write_log_called_with_critical_level():
    """알람 발화 시 safe_write_log('CRITICAL', ...) — 메시지에 [매도거부폭주] 포함."""
    tracker = _make_tracker()
    now = _now(10, 0, 0)

    with _patch_alarm(capture=True) as s:
        for i in range(6):
            tracker.record_rejection(
                "009150", "market_closed", "APBK0918", "장운영시간외",
                now + timedelta(seconds=i),
            )

    assert len(s["captured"]) == 1, f"safe_write_log 1회 기대: {len(s['captured'])}"
    level, msg = s["captured"][0]
    assert level == "CRITICAL", f"CRITICAL 레벨 기대: {level}"
    assert "[매도거부폭주]" in msg, f"[매도거부폭주] 미포함: {msg}"


# ===========================================================================
# V1-12: 사이클 55 R-1 호환 — get_recent_rejections 정상 동작
# ===========================================================================

def test_v1_12_cycle55_r1_compatibility_get_recent_rejections():
    """사이클 55 R-1 get_recent_rejections — deque sliced 사본 정상 반환."""
    tracker = _make_tracker()
    now = _now()

    with _patch_alarm() as _:
        for i in range(3):
            tracker.record_rejection(
                "005930", "market_closed", "APBK0918", "장운영시간외",
                now + timedelta(seconds=i),
            )

    events = tracker.get_recent_rejections("005930")
    assert isinstance(events, list), f"list 타입 기대: {type(events)}"
    assert len(events) == 3, f"3건 기대: {len(events)}"

    # 사본 검증 — 외부 mutate 가 내부 deque 영향 없음
    events.clear()
    assert len(tracker.get_recent_rejections("005930")) == 3, (
        "사본 mutate 가 deque 영향 없어야 함"
    )

    # 존재하지 않는 ticker
    assert tracker.get_recent_rejections("999999") == []
