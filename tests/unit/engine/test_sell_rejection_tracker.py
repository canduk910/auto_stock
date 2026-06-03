"""사이클 55 R-1 Red — SellRejectionTracker 단일 정책 객체 단위 테스트.

배경 (refactor-expert 설계 카드 §1, 2026-06-03):
    사이클 52 (B-1) 단일 책임 진입 차단 → 사이클 55 (R-1) 4 분류 통합 정책 객체.
    선례 답습: 사이클 48 `src/engine/stale_tracker.py::StaleTrackerState` (82L).

설계 명세 (자문 Q1~Q5 사용자 전부 적용):
    - Q1: 2단계 TTL — KRX 메인(09:00~15:30) 거부 = 5분 TTL,
                     NXT 시간대(08:00~09:00 / 15:30~20:00) 거부 = 다음 KST 09:00.
    - Q2: market_order_disallowed = 30초 TTL + NXT 폴백 실패 시 익일 청산 전환.
    - Q3: insufficient_quantity = 차단 X, history 만 적재 (positions 자체 제거가 자연 차단).
    - Q5: ticker별 deque(maxlen=20) history 사전 도입 (V-1 알람 hook).

테스트 매트릭스 (16 케이스):
    Q1 — 2단계 TTL (4)
        A1-1: KRX 메인 거부 (11:00) → 5분 TTL (11:05)
        A1-2: NXT 시간대 거부 (08:30) → 다음 09:00 TTL
        A1-3: 경계 시각 — 08:59:59 = NXT / 09:00:00 = KRX 메인 / 15:29:59 = KRX / 15:30 = NXT
        A1-4: KRX 메인 5분 경과 → is_blocked=False + lazy clear

    Q2 — market_order_disallowed (4)
        A2-1: 폴백 성공 (KRX 메인) → 30초 TTL 등록 + next_day=False
        A2-2: 폴백 실패 (KRX 메인) → next_day=False (KRX 사이클 자연 재트리거)
        A2-3: 폴백 실패 (NXT) → next_day=True (Q2 핵심)
        A2-4: 30초 경과 → is_blocked=False

    Q3 — insufficient_quantity (3)
        A3-1: register_insufficient_quantity → history 등록 + 차단 X
        A3-2: history 적재 reason="insufficient_quantity"
        A3-3: 다른 ticker 호출 영향 없음

    Q5 — history deque (3)
        A5-1: maxlen=20 — 21번째 push 시 1번 evict
        A5-2: get_recent_rejections 리스트 사본 반환 (mutate 차단)
        A5-3: 다른 ticker history 격리

    호환 — 일반 (2)
        A-1: reset_daily() → 4 필드 일괄 clear
        A-2: is_blocked TTL 만료 후 lazy cleanup (메모리 누수 방지)

Red 상태 (Green 구현 전):
    - `src/engine/sell_rejection.py` 모듈 자체 부재 → 전 케이스 ImportError 또는 FAIL.

freezegun KST 처리:
    사이클 52/54 freezegun 함정 회피 — `@freeze_time("2026-06-03 11:00:00", tz_offset=-9)` 로
    KST 11:00 가정 + `datetime.now(KST_TZ)` 로 aware 시각 추출.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit


KST_TZ = timezone(timedelta(hours=9))


# ===========================================================================
# Q1 — 2단계 TTL (KRX 메인 5분 / NXT 다음 09:00)
# ===========================================================================
@freeze_time("2026-06-03 11:00:00", tz_offset=-9)
def test_a1_1_when_market_closed_in_krx_main_hours_then_expiry_is_5_minutes_later():
    """A1-1: KRX 메인 시간(11:00) 거부 → expiry = 11:05 (+5분 TTL)."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    expiry = tracker.register_market_closed(
        "064400", now_kst, in_krx_main_hours=True
    )

    expected_expiry = now_kst + timedelta(minutes=5)
    assert expiry == expected_expiry, (
        f"KRX 메인 거부 expiry 불일치: {expiry} != {expected_expiry} (+5분 기대)"
    )
    # 차단 게이트 즉시 활성
    assert tracker.is_blocked("064400", now_kst) is True
    # 4분 후에도 차단
    assert tracker.is_blocked("064400", now_kst + timedelta(minutes=4)) is True


@freeze_time("2026-06-03 08:30:00", tz_offset=-9)
def test_a1_2_when_market_closed_in_nxt_hours_then_expiry_is_next_kst_9am():
    """A1-2: NXT 시간대(08:30) 거부 → expiry = 당일 09:00 (NXT pre-market 끝 시각)."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    expiry = tracker.register_market_closed(
        "064400", now_kst, in_krx_main_hours=False
    )

    # 다음 09:00 (사이클 52 보존: 08:30 → 당일 09:00)
    expected_expiry = datetime(2026, 6, 3, 9, 0, 0, tzinfo=KST_TZ)
    assert expiry == expected_expiry, (
        f"NXT 시간대 거부 expiry 불일치: {expiry} != {expected_expiry} (다음 09:00 기대)"
    )


def test_a1_3_when_boundary_times_then_is_krx_main_hours_classifies_correctly():
    """A1-3: 경계 시각 — is_krx_main_hours / is_nxt_session_hours 정확성."""
    from src.engine.sell_rejection import is_krx_main_hours, is_nxt_session_hours

    # 08:59:59 → NXT (KRX 메인 아님)
    t_0859 = datetime(2026, 6, 3, 8, 59, 59, tzinfo=KST_TZ)
    assert is_krx_main_hours(t_0859) is False
    assert is_nxt_session_hours(t_0859) is True

    # 09:00:00 → KRX 메인 진입
    t_0900 = datetime(2026, 6, 3, 9, 0, 0, tzinfo=KST_TZ)
    assert is_krx_main_hours(t_0900) is True
    assert is_nxt_session_hours(t_0900) is False

    # 15:29:59 → KRX 메인
    t_1529 = datetime(2026, 6, 3, 15, 29, 59, tzinfo=KST_TZ)
    assert is_krx_main_hours(t_1529) is True
    assert is_nxt_session_hours(t_1529) is False

    # 15:30:00 → NXT 진입
    t_1530 = datetime(2026, 6, 3, 15, 30, 0, tzinfo=KST_TZ)
    assert is_krx_main_hours(t_1530) is False
    assert is_nxt_session_hours(t_1530) is True

    # 20:00:00 → NXT 외 (장 마감)
    t_2000 = datetime(2026, 6, 3, 20, 0, 0, tzinfo=KST_TZ)
    assert is_krx_main_hours(t_2000) is False
    assert is_nxt_session_hours(t_2000) is False


@freeze_time("2026-06-03 11:00:00", tz_offset=-9)
def test_a1_4_when_krx_main_5min_elapsed_then_is_blocked_false_with_lazy_clear():
    """A1-4: KRX 메인 5분 TTL 만료 → is_blocked=False + 내부 dict 정리."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    tracker.register_market_closed("064400", now_kst, in_krx_main_hours=True)

    # 5분 + 1초 후 — 만료
    later = now_kst + timedelta(minutes=5, seconds=1)
    assert tracker.is_blocked("064400", later) is False, (
        "TTL 만료 후 is_blocked=False 보장 위반"
    )
    # lazy cleanup — 내부 dict 에서 제거
    assert "064400" not in tracker._blocked_until, (
        "TTL 만료 후 lazy clear 누락 (메모리 누수 위험)"
    )
    assert "064400" not in tracker._blocked_reason


# ===========================================================================
# Q2 — market_order_disallowed (30초 TTL + NXT 폴백 실패 → 익일 전환)
# ===========================================================================
@freeze_time("2026-06-03 10:00:00", tz_offset=-9)
def test_a2_1_when_market_order_fallback_succeeded_in_krx_main_then_30s_ttl():
    """A2-1: KRX 메인 폴백 성공 → 30초 TTL + next_day=False (폭주 차단만)."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    result = tracker.register_market_order_disallowed(
        "064400", now_kst,
        is_nxt_session=False,
        fallback_succeeded=True,
    )

    assert result.next_day_clear_required is False, (
        "KRX 메인 폴백 성공 시 익일 청산 전환 불필요"
    )
    expected_expiry = now_kst + timedelta(seconds=30)
    assert result.block_ttl_expires_at == expected_expiry, (
        f"30초 TTL 불일치: {result.block_ttl_expires_at} != {expected_expiry}"
    )
    # 차단 게이트 활성
    assert tracker.is_blocked("064400", now_kst) is True


@freeze_time("2026-06-03 10:00:00", tz_offset=-9)
def test_a2_2_when_market_order_fallback_failed_in_krx_main_then_next_day_false():
    """A2-2: KRX 메인 폴백 실패 → next_day=False (다음 사이클 자연 재트리거)."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    result = tracker.register_market_order_disallowed(
        "064400", now_kst,
        is_nxt_session=False,
        fallback_succeeded=False,
    )

    assert result.next_day_clear_required is False, (
        "KRX 메인은 폴백 실패해도 익일 청산 전환 안 함 (당일 재시도 의무)"
    )


@freeze_time("2026-06-03 16:00:00", tz_offset=-9)  # NXT 애프터 시간대
def test_a2_3_when_market_order_fallback_failed_in_nxt_then_next_day_true():
    """A2-3 (Q2 핵심): NXT 폴백 실패 → next_day=True (익일 09:00 KRX 시장가 전환)."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    result = tracker.register_market_order_disallowed(
        "064400", now_kst,
        is_nxt_session=True,
        fallback_succeeded=False,
    )

    assert result.next_day_clear_required is True, (
        "Q2 핵심 — NXT 폴백 실패 시 익일 청산 전환 의무 위반"
    )
    # 30초 TTL 동일 등록 (동일 tick 폭주 차단)
    assert tracker.is_blocked("064400", now_kst) is True


@freeze_time("2026-06-03 10:00:00", tz_offset=-9)
def test_a2_4_when_30s_elapsed_then_is_blocked_false():
    """A2-4: 30초 경과 → 재시도 가능 (is_blocked=False)."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    tracker.register_market_order_disallowed(
        "064400", now_kst,
        is_nxt_session=False,
        fallback_succeeded=True,
    )

    later = now_kst + timedelta(seconds=31)
    assert tracker.is_blocked("064400", later) is False, (
        "30초 TTL 만료 후 차단 해제 위반"
    )
    assert "064400" not in tracker._blocked_until


# ===========================================================================
# Q3 — insufficient_quantity (차단 X, history 만)
# ===========================================================================
@freeze_time("2026-06-03 10:00:00", tz_offset=-9)
def test_a3_1_when_register_insufficient_quantity_then_not_blocked_and_history_added():
    """A3-1: insufficient_quantity 등록 → 차단 set 무영향, history 만 적재."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    tracker.register_insufficient_quantity("064400", now_kst)

    # 차단 게이트 무영향 (positions 자체 제거가 자연 차단 — Q3 도메인 자문)
    assert tracker.is_blocked("064400", now_kst) is False, (
        "insufficient_quantity 차단 누설 — positions 제거가 자연 차단이므로 tracker 차단 금지"
    )
    assert "064400" not in tracker._blocked_until
    # history 적재 확인
    history = tracker.get_recent_rejections("064400")
    assert len(history) == 1
    assert history[0].reason == "insufficient_quantity"


@freeze_time("2026-06-03 10:00:00", tz_offset=-9)
def test_a3_2_history_event_has_correct_reason_and_timestamp():
    """A3-2: history event 의 reason / occurred_at 정확성."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    tracker.register_insufficient_quantity("064400", now_kst)

    event = tracker.get_recent_rejections("064400")[0]
    assert event.reason == "insufficient_quantity"
    assert event.occurred_at == now_kst


@freeze_time("2026-06-03 10:00:00", tz_offset=-9)
def test_a3_3_insufficient_quantity_isolated_per_ticker():
    """A3-3: 다른 ticker history 격리 — 064400 등록이 005930 영향 없음."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    tracker.register_insufficient_quantity("064400", now_kst)

    assert tracker.get_recent_rejections("005930") == [], (
        "다른 ticker 호출 시 빈 history 보장 위반"
    )


# ===========================================================================
# Q5 — history deque (maxlen=20)
# ===========================================================================
@freeze_time("2026-06-03 10:00:00", tz_offset=-9)
def test_a5_1_history_deque_maxlen_20_evicts_oldest():
    """A5-1: history maxlen=20 — 21번째 push 시 1번째 evict."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    # 21회 등록 (record_rejection 사용)
    for i in range(21):
        tracker.record_rejection(
            "064400",
            "market_closed",
            f"MSG_{i:02d}",
            f"reason {i:02d}",
            now_kst + timedelta(seconds=i),
        )

    history = tracker.get_recent_rejections("064400")
    assert len(history) == 20, f"deque maxlen=20 위반: {len(history)}"
    # 1번째(MSG_00) evict, 마지막은 MSG_20
    msg_cds = [e.msg_cd for e in history]
    assert "MSG_00" not in msg_cds, "가장 오래된 항목 evict 누락"
    assert "MSG_20" in msg_cds, "최근 항목 누락"


@freeze_time("2026-06-03 10:00:00", tz_offset=-9)
def test_a5_2_get_recent_rejections_returns_list_copy_not_internal_deque():
    """A5-2: get_recent_rejections 가 list 사본 반환 (외부 mutate 차단)."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    tracker.record_rejection("064400", "market_closed", "MC", "msg", now_kst)

    snapshot = tracker.get_recent_rejections("064400")
    assert isinstance(snapshot, list), "list 타입 반환 보장"
    # mutate — 내부 deque 가 영향받지 않아야 함
    snapshot.clear()
    refetched = tracker.get_recent_rejections("064400")
    assert len(refetched) == 1, (
        "get_recent_rejections 가 내부 deque 직접 노출 — 외부 mutate 누설"
    )


@freeze_time("2026-06-03 10:00:00", tz_offset=-9)
def test_a5_3_history_isolated_per_ticker():
    """A5-3: ticker 별 history 독립 deque."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    tracker.record_rejection("064400", "market_closed", "MC1", "msg", now_kst)
    tracker.record_rejection("005930", "market_closed", "MC2", "msg", now_kst)

    h_064400 = tracker.get_recent_rejections("064400")
    h_005930 = tracker.get_recent_rejections("005930")
    assert len(h_064400) == 1 and h_064400[0].msg_cd == "MC1"
    assert len(h_005930) == 1 and h_005930[0].msg_cd == "MC2"


# ===========================================================================
# 호환 / 일반
# ===========================================================================
@freeze_time("2026-06-03 11:00:00", tz_offset=-9)
def test_compat_1_reset_daily_clears_all_four_fields():
    """호환-1: reset_daily() 호출 시 4 내부 dict/set/deque 일괄 clear."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    tracker.register_market_closed("064400", now_kst, in_krx_main_hours=True)
    tracker.register_insufficient_quantity("005930", now_kst)
    tracker.mark_block_logged("064400")
    tracker.record_rejection("064400", "market_closed", "X", "msg", now_kst)

    # 사전 상태 확인 (가드)
    assert tracker._blocked_until, "사전 상태 누락 — 테스트 결함"
    assert tracker._logged_today, "사전 상태 누락 — 테스트 결함"
    assert tracker._history, "사전 상태 누락 — 테스트 결함"

    tracker.reset_daily()

    assert tracker._blocked_until == {}, "_blocked_until clear 위반"
    assert tracker._blocked_reason == {}, "_blocked_reason clear 위반"
    assert tracker._logged_today == set(), "_logged_today clear 위반"
    assert tracker._history == {}, "_history clear 위반"


@freeze_time("2026-06-03 11:00:00", tz_offset=-9)
def test_compat_2_is_blocked_false_when_no_registration():
    """호환-2: 등록 없으면 is_blocked=False (KeyError 차단)."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    assert tracker.is_blocked("UNKNOWN", now_kst) is False


@freeze_time("2026-06-03 11:00:00", tz_offset=-9)
def test_compat_3_should_emit_block_log_cap_per_ticker():
    """호환-3: should_emit_block_log / mark_block_logged 1회 cap 동작."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    # 첫 호출 — emit 허용
    assert tracker.should_emit_block_log("064400") is True
    tracker.mark_block_logged("064400")
    # 2번째 호출 — cap (emit 금지)
    assert tracker.should_emit_block_log("064400") is False
    # 다른 ticker 격리
    assert tracker.should_emit_block_log("005930") is True


@freeze_time("2026-06-03 11:00:00", tz_offset=-9)
def test_compat_4_register_market_closed_resets_logged_today_for_reemit():
    """호환-4: register_market_closed 가 _logged_today.discard 호출 — 만료 후 재폭주 시 emit 보장."""
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()
    now_kst = datetime.now(KST_TZ)
    tracker.mark_block_logged("064400")
    assert "064400" in tracker._logged_today

    tracker.register_market_closed("064400", now_kst, in_krx_main_hours=True)
    # discard 호출 — 만료 후 재폭주 시 INFO 1줄 emit 보장
    assert "064400" not in tracker._logged_today, (
        "register_market_closed 가 _logged_today.discard 누락 — 재폭주 시 emit 누락"
    )


# ===========================================================================
# 사이클 56-B — _logged_today DailyEmitCap 마이그레이션 회귀 가드 (G-2)
# ===========================================================================
def test_logged_today_is_daily_emit_cap_instance():
    """사이클 56-B 마이그레이션 회귀 가드 — _logged_today 가 DailyEmitCap[str] 인스턴스.

    set 동형 호환 layer 5 메서드 (__contains__ / add / discard / clear / __len__)
    가 정상 동작하는지 검증. 기존 사이클 55 9 가드 행위 보존 확인.
    """
    from src.engine.daily_emit_cap import DailyEmitCap
    from src.engine.sell_rejection import SellRejectionTracker

    tracker = SellRejectionTracker()

    # 인스턴스 타입 검증 (56-B 핵심)
    assert isinstance(tracker._logged_today, DailyEmitCap), (
        "_logged_today 가 DailyEmitCap 인스턴스가 아님 — 56-B 마이그레이션 미수행"
    )

    # set 동형 호환 layer 검증 (add / __contains__ / discard / clear)
    tracker._logged_today.add("064400")
    assert "064400" in tracker._logged_today, "add 후 __contains__ True 실패"

    tracker._logged_today.discard("064400")
    assert "064400" not in tracker._logged_today, "discard 후 __contains__ False 실패"

    # clear / __len__ 검증
    tracker._logged_today.add("005930")
    tracker._logged_today.add("000660")
    assert len(tracker._logged_today) == 2, "__len__ 불일치"
    tracker._logged_today.clear()
    assert len(tracker._logged_today) == 0, "clear 후 __len__ 0 보장 위반"
