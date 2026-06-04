"""Sell 거부 4 분류 통합 정책 객체 (사이클 55 R-1, 2026-06-03).

배경:
    사이클 52 (B-1) 단일 책임 진입 차단 → 사이클 55 (R-1) 4 분류 통합:
    - is_market_closed_rejection (KRX 메인 5분 TTL / NXT 시간대 다음 09:00 TTL)
    - is_market_order_disallowed (30초 TTL + NXT 폴백 실패 시 익일 청산 전환)
    - is_insufficient_quantity (기록만 + reconciliation 트리거, 차단 X)
    - (정상/기타 거부 — tracker 통과)

선례 답습:
    사이클 48 `src/engine/stale_tracker.py::StaleTrackerState` (82L).

호환 layer:
    OrderEngine 의 2 property (_market_closed_blocked / _market_closed_blocked_logged_today)
    가 본 데이터클래스 필드 직접 노출.
    사이클 52 회귀 가드 8 시나리오 호환 보장.
    사이클 54 _nxt_downgrade_logged_today 는 R-1 범위 밖 — 사이클 56-C 마이그레이션 완료 예정.

안전 가드:
    reset_daily() 가 _blocked_until / _blocked_reason / _logged_today / _history /
    _alarm_last_emitted 일괄 clear (사이클 57 V-1 추가).
    record_rejection() 은 항상 history 적재 + V-1 알람 임계 자동 검사.

사이클 57 V-1 (2026-06-04):
    _append_history → _maybe_emit_burst_alarm 자동 발화.
    10분 윈도우 5건 초과 시 CRITICAL system_logs INSERT (fire-and-forget).
    30분 cooldown per-ticker (알람 폭주 차단).
    사이클 52 B-1 실측 (10분 500건) 기반 임계 결정.
"""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone
from typing import ClassVar, Literal

from src.db.system_logs import safe_write_log
from src.engine.daily_emit_cap import DailyEmitCap

_KST_TZ = timezone(timedelta(hours=9))

# 사이클 57 V-1 — 알람 상수
ALARM_WINDOW_SECONDS: int = 600    # 10분 윈도우
ALARM_THRESHOLD: int = 5           # 5건 초과 (6건째 발화)
ALARM_COOLDOWN_SECONDS: int = 1800  # 30분 cooldown per-ticker

RejectionReason = Literal[
    "market_closed",
    "market_order_disallowed",
    "insufficient_quantity",
]


@dataclass(frozen=True)
class RejectionEvent:
    """거부 이벤트 1건 (V-1 알람 hook 사전 준비, 사이클 56+)."""

    reason: RejectionReason
    msg_cd: str
    msg1: str
    occurred_at: datetime


@dataclass(frozen=True)
class RejectionResult:
    """register_market_order_disallowed() 응답.

    Attributes:
        next_day_clear_required: NXT 폴백 실패 → 익일 청산 전환 의무.
            execute_sell 호출자가 _pending_next_day_clear 에 등록.
        block_ttl_expires_at: 30 초 TTL 만료 시각 (재시도 진입 게이트).
    """

    next_day_clear_required: bool
    block_ttl_expires_at: datetime


@dataclass
class SellRejectionTracker:
    """Sell 거부 4 분류 통합 정책 객체.

    사이클 52 (B-1) 단일 TTL → 사이클 55 (R-1) 4 분류 통합.
    사이클 57 V-1: _append_history → 10분 5건 초과 CRITICAL 알람 자동 발화.
    설계 카드 §1.2 인터페이스 명세 준수.
    """

    # 통합 차단 게이트 (Q1+Q2 — 2단계 TTL + 30초 TTL 공용 저장)
    _blocked_until: dict[str, datetime] = field(default_factory=dict)
    _blocked_reason: dict[str, RejectionReason] = field(default_factory=dict)
    # emit cap — 사이클 56-B: DailyEmitCap[str] 위임 (set 호환 layer 보존)
    _logged_today: DailyEmitCap[str] = field(default_factory=DailyEmitCap)
    # V-1 알람 hook 사전 준비 (Q5, 사이클 56+)
    _history: dict[str, deque[RejectionEvent]] = field(default_factory=dict)
    # 사이클 57 V-1 — per-ticker 알람 cooldown 시각
    _alarm_last_emitted: dict[str, datetime] = field(default_factory=dict)

    # 사이클 57 V-1 — class-level 상수 (모듈 상수와 동기화)
    _ALARM_WINDOW_SECONDS: ClassVar[int] = ALARM_WINDOW_SECONDS
    _ALARM_THRESHOLD: ClassVar[int] = ALARM_THRESHOLD
    _ALARM_COOLDOWN_SECONDS: ClassVar[int] = ALARM_COOLDOWN_SECONDS

    # ──────────────────────────── public 게이트

    def is_blocked(self, ticker: str, now_kst: datetime) -> bool:
        """진입 차단 게이트. TTL 자연 만료면 lazy clear 후 False.

        execute_sell 진입 직후 (selling.add 다음) 호출 — 사이클 52 순서 보존.
        """
        expiry = self._blocked_until.get(ticker)
        if expiry is None:
            return False
        if now_kst >= expiry:
            self._blocked_until.pop(ticker, None)
            self._blocked_reason.pop(ticker, None)
            return False
        return True

    def should_emit_block_log(self, ticker: str) -> bool:
        """차단 게이트 발화 시 1회/ticker/일 emit cap 판단.

        return True 시 호출자가 즉시 mark_block_logged(ticker).
        """
        return ticker not in self._logged_today

    def mark_block_logged(self, ticker: str) -> None:
        """emit cap 등록 — 이후 should_emit_block_log(ticker) 가 False 반환."""
        self._logged_today.add(ticker)

    # ──────────────────────────── public 등록 (분류별)

    def register_market_closed(
        self,
        ticker: str,
        now_kst: datetime,
        *,
        in_krx_main_hours: bool,
    ) -> datetime:
        """Q1 — KRX 메인 5분 TTL / 그 외(NXT 시간대) 다음 KST 09:00.

        Args:
            in_krx_main_hours: True 면 09:00~15:30 KRX 메인 거부 (일시 장애 가정,
                과보수 차단). False 면 NXT 시간대 거부 (자연 만료 명확).

        Returns:
            등록된 expiry datetime (사이클 52 호환 — 호출자가 로그에 사용).
        """
        if in_krx_main_hours:
            expiry = now_kst + timedelta(minutes=5)
        else:
            expiry = _compute_next_market_open_kst(now_kst)
        self._blocked_until[ticker] = expiry
        self._blocked_reason[ticker] = "market_closed"
        # discard — 만료 후 재폭주 시 INFO 1줄 emit 보장 (사이클 52 호환)
        self._logged_today.discard(ticker)
        self._append_history(
            ticker,
            RejectionEvent("market_closed", "", "", now_kst),
        )
        return expiry

    def register_market_order_disallowed(
        self,
        ticker: str,
        now_kst: datetime,
        *,
        is_nxt_session: bool,
        fallback_succeeded: bool,
    ) -> RejectionResult:
        """Q2 — 30초 TTL (동일 tick 폭주 차단) + NXT 폴백 실패 시 익일 청산 전환.

        Args:
            is_nxt_session: 현재 NXT 시간대 (08:00~09:00 / 15:30~20:00).
            fallback_succeeded: step_down 5호가 LIMIT 폴백이 성공했는지.
                False 이고 is_nxt_session=True → next_day_clear_required=True
                (Q2 핵심 — NXT 야간 폴백 실패 시 익일 KRX 시장가로 전환).

        Returns:
            RejectionResult: next_day_clear_required + block_ttl_expires_at
        """
        expiry = now_kst + timedelta(seconds=30)
        self._blocked_until[ticker] = expiry
        self._blocked_reason[ticker] = "market_order_disallowed"
        self._append_history(
            ticker,
            RejectionEvent("market_order_disallowed", "", "", now_kst),
        )
        next_day_required = is_nxt_session and not fallback_succeeded
        return RejectionResult(
            next_day_clear_required=next_day_required,
            block_ttl_expires_at=expiry,
        )

    def register_insufficient_quantity(
        self,
        ticker: str,
        now_kst: datetime,
    ) -> None:
        """Q3 — 차단 X (positions 제거가 자연 차단). history 만 적재.

        호출자(execute_sell)가 별도로:
          1) state.positions / DB positions 제거 (현행 보존)
          2) inquire_balance() 1회 호출 + [positions_reconciliation] 로그
        """
        self._append_history(
            ticker,
            RejectionEvent("insufficient_quantity", "", "", now_kst),
        )

    def record_rejection(
        self,
        ticker: str,
        reason: RejectionReason,
        msg_cd: str,
        msg1: str,
        now_kst: datetime,
    ) -> None:
        """V-1 알람 hook 사전 준비 — 분류별 register_* 외 raw history 채널."""
        self._append_history(
            ticker,
            RejectionEvent(reason, msg_cd, msg1, now_kst),
        )

    def get_recent_rejections(self, ticker: str) -> list[RejectionEvent]:
        """V-1 알람 / 진단 readonly 조회. maxlen=20 캡.

        Returns:
            list 사본 (외부 mutate 차단 — 내부 deque 직접 노출 금지).
        """
        dq = self._history.get(ticker)
        return list(dq) if dq else []

    # ──────────────────────────── 일일 reset

    def reset_daily(self) -> None:
        """_reset_daily_state 동행. 5 필드 일괄 clear (사이클 57 V-1 추가).

        사이클 48 stale_tracker.reset_daily() 패턴 답습.
        """
        self._blocked_until.clear()
        self._blocked_reason.clear()
        self._logged_today.clear()
        self._history.clear()
        self._alarm_last_emitted.clear()  # 사이클 57 V-1

    # ──────────────────────────── internal

    def _append_history(self, ticker: str, event: RejectionEvent) -> None:
        """history deque 에 이벤트 적재 + V-1 알람 임계 자동 검사 (사이클 57).

        사이클 55 R-1 의 4 채널 (register_market_closed / register_market_order_disallowed /
        register_insufficient_quantity / record_rejection) 모두 이 메서드 경유.
        """
        dq = self._history.get(ticker)
        if dq is None:
            dq = deque(maxlen=20)
            self._history[ticker] = dq
        dq.append(event)
        # 사이클 57 V-1 — 10분 5건 초과 시 CRITICAL system_logs 발화
        self._maybe_emit_burst_alarm(ticker, event.occurred_at)

    def _maybe_emit_burst_alarm(self, ticker: str, now_kst: datetime) -> None:
        """10분 윈도우 거부 횟수 > ALARM_THRESHOLD 시 CRITICAL system_logs 발화.

        30분 cooldown per-ticker — 알람 폭주 차단.
        fire-and-forget (asyncio.create_task) — 매매 hot path 블로킹 없음.

        사이클 57 V-1 (2026-06-04).
        """
        # cooldown 검사 (lazy clear)
        last_emit = self._alarm_last_emitted.get(ticker)
        if last_emit is not None:
            if (now_kst - last_emit).total_seconds() < self._ALARM_COOLDOWN_SECONDS:
                return  # cooldown 중 — skip
            self._alarm_last_emitted.pop(ticker, None)

        # 10분 윈도우 거부 횟수
        dq = self._history.get(ticker)
        if not dq:
            return
        window_start = now_kst - timedelta(seconds=self._ALARM_WINDOW_SECONDS)
        recent_events = [e for e in dq if e.occurred_at >= window_start]
        if len(recent_events) <= self._ALARM_THRESHOLD:
            return

        # 임계 초과 — cooldown 등록 + CRITICAL 알람 발화
        self._alarm_last_emitted[ticker] = now_kst
        self._emit_burst_alarm(ticker, recent_events, now_kst)

    def _emit_burst_alarm(
        self,
        ticker: str,
        recent_events: list[RejectionEvent],
        now_kst: datetime,
    ) -> None:
        """알람 메시지 포맷 + safe_write_log CRITICAL fire-and-forget (사이클 57 V-1).

        reason 분포 집계 + 마지막 이벤트 정보 포함.
        safe_write_log 실패 시 graceful skip (매매 흐름 무영향).
        """
        # reason 분포 집계
        reason_counts: dict[str, int] = {}
        for e in recent_events:
            reason_counts[e.reason] = reason_counts.get(e.reason, 0) + 1
        reasons_str = ", ".join(f"{k}:{v}" for k, v in sorted(reason_counts.items()))
        last_event = recent_events[-1]
        message = (
            f"[매도거부폭주] ticker={ticker} window=10min "
            f"count={len(recent_events)} threshold={self._ALARM_THRESHOLD}\n"
            f"  reasons={reasons_str}\n"
            f"  last_msg_cd={last_event.msg_cd} last_msg1={last_event.msg1[:60]}\n"
            f"  occurred_at_kst={now_kst.isoformat()}"
        )
        # fire-and-forget — 매매 hot path 블로킹 없음.
        # asyncio.create_task 는 running event loop 필수 — 테스트/초기화 환경
        # (loop 없음) 에서는 graceful skip (coroutine 즉시 close).
        coro = safe_write_log(
            "CRITICAL",
            message,
            fallback_debug=f"[매도거부폭주] write_log 실패 ticker={ticker}",
        )
        try:
            asyncio.create_task(coro)
        except RuntimeError:
            # no running event loop — 코루틴 정리 후 graceful skip
            coro.close()


# ──────────────────────────── module-level helpers


def _compute_next_market_open_kst(now: datetime) -> datetime:
    """다음 KST 09:00 만료 시각 (사이클 52 order_engine 헬퍼 재이주).

    now < 09:00 KST → 당일 09:00.
    now >= 09:00 KST → 다음 날 09:00 (주말 스킵은 여기서 하지 않음 — NXT TTL 단순화).

    Note:
        사이클 52 order_engine._compute_next_market_open_kst 는 주말 스킵 포함.
        NXT 시간대 TTL 는 "다음 개장일 09:00" 정확도보다 "야간 폭주 차단" 목적이므로
        단순 다음 날 09:00 로 처리 (주말 매매 불가 → 실질적 영향 없음).
    """
    t = now.time()
    if t < dtime(9, 0):
        # 당일 09:00 (ex. 08:30 → 09:00)
        next_day = now.date()
    else:
        # 당일 이미 09:00 경과 → 다음 날 09:00 (ex. 16:00 → 익일 09:00)
        next_day = now.date() + timedelta(days=1)
    return datetime.combine(next_day, dtime(9, 0), tzinfo=_KST_TZ)


def is_krx_main_hours(now_kst: datetime) -> bool:
    """KRX 메인 시간 (09:00 ≤ t < 15:30) 판정 (Q1 분기 helper).

    True → Q1 5분 TTL / False → NXT 시간대 다음 09:00 TTL.
    """
    t = now_kst.time()
    return dtime(9, 0) <= t < dtime(15, 30)


def is_nxt_session_hours(now_kst: datetime) -> bool:
    """NXT 시간대 (08:00~09:00 / 15:30~20:00) 판정 (Q2 분기 helper).

    True → Q2 NXT 폴백 실패 시 익일 청산 전환 대상.
    """
    t = now_kst.time()
    return (dtime(8, 0) <= t < dtime(9, 0)) or (dtime(15, 30) <= t < dtime(20, 0))
