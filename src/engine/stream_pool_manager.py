"""스트림 풀 매니저 (사이클 15-B-1, 2026-05-19).

REST 관찰 → 임박(near-signal) 종목 WS 승격 → 신호 소멸 시 REST 복귀.
KIS 공지 "정상 케이스" (연결 1회 → 구독 → 데이터수신 → 불필요종목 구독해제 → 연결종료)
패턴 강화. WS 슬롯 효율 + 임박 종목만 집중 감시.

상태 모델:
- `rest_watch`: REST 폴링 관찰 중 (WS 구독 X)
- `ws_active`: WS 풀에 구독 중 (활성 매수 후보)
- `cooldown`: 강등 후 재승격 제한 (ws_rejoin_cooldown_secs)

전이 규칙:
- rest_watch → ws_active: near-signal 만족 + cooldown 아님 + 배치 제한 미초과
- ws_active → rest_watch: near-signal 소멸 + min_ws_hold_secs 경과 + 보유/익일청산 아님
- ws_active → cooldown: 강등 시 cooldown_until 기록 → cooldown 만료 시 rest_watch

안정성 정책:
- `MIN_WS_HOLD_SECS=180.0` — 승격 후 최소 유지 시간
- `WS_REJOIN_COOLDOWN_SECS=300.0` — 강등 후 재승격 제한
- `MAX_PROMOTE_PER_CYCLE=5` — 사이클당 승격 상한
- `MAX_DEMOTE_PER_CYCLE=5` — 사이클당 강등 상한

우선순위 (배치 제한 적용 시 정렬 기준):
1. positions (보유 종목 — 절대 demote 불가)
2. next_day_clear (익일청산 대기)
3. donchian_swing (멀티데이 안정성)
4. momentum
5. volatility_breakout
6. long_tail_volatility
7. bull_flag_breakout
8. vcp_breakout

본 모듈은 단독 사용 가능 (scheduler 통합 X 단계). 사이클 15-B-2 에서 통합.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# 안정성 정책 (사용자 설계서 제5장)
MIN_WS_HOLD_SECS = 180.0
WS_REJOIN_COOLDOWN_SECS = 300.0
MAX_PROMOTE_PER_CYCLE = 5
MAX_DEMOTE_PER_CYCLE = 5

# 우선순위 (설계서 제4장)
STRATEGY_PRIORITY = {
    "positions": 1,
    "next_day_clear": 2,
    "donchian_swing": 3,
    "momentum": 4,
    "volatility_breakout": 5,
    "long_tail_volatility": 6,
    "bull_flag_breakout": 7,
    "vcp_breakout": 8,
}


@dataclass
class StreamSlot:
    """ticker 별 스트림 슬롯 상태."""
    ticker: str
    strategy_id: str
    state: str  # "rest_watch" / "ws_active" / "cooldown"
    reason: str = ""
    since: float = field(default_factory=time.monotonic)  # 상태 진입 시각 (monotonic)
    ws_hold_until: float = 0.0  # ws_active 최소 유지 시각
    cooldown_until: float = 0.0  # cooldown 종료 시각

    def is_protected_from_demote(self) -> bool:
        """positions / next_day_clear 는 demote 절대 불가."""
        return self.strategy_id in ("positions", "next_day_clear")


class StreamPoolManager:
    """REST/WS 등록·탈락 정책의 단일 책임자.

    호출자(near_signal_monitor / scheduler) 가 promote/demote 요청하면 정책 검증 후
    실제 WS 풀에 subscribe/unsubscribe 위임. 호출자가 시간을 직접 inject 가능
    (`time.monotonic()` 인터페이스 — 테스트 가능).
    """

    def __init__(
        self,
        *,
        min_ws_hold_secs: float = MIN_WS_HOLD_SECS,
        ws_rejoin_cooldown_secs: float = WS_REJOIN_COOLDOWN_SECS,
        max_promote_per_cycle: int = MAX_PROMOTE_PER_CYCLE,
        max_demote_per_cycle: int = MAX_DEMOTE_PER_CYCLE,
    ) -> None:
        self.min_ws_hold_secs = min_ws_hold_secs
        self.ws_rejoin_cooldown_secs = ws_rejoin_cooldown_secs
        self.max_promote_per_cycle = max_promote_per_cycle
        self.max_demote_per_cycle = max_demote_per_cycle

        self._slots: dict[str, StreamSlot] = {}
        # 사이클 단위 배치 카운터 (호출자가 cycle_reset 호출 시 0)
        self._promoted_this_cycle = 0
        self._demoted_this_cycle = 0

    # -- 사이클 관리 -----------------------------------------------------

    def reset_cycle(self) -> None:
        """매 폴링 사이클 시작 시 호출 — 배치 카운터 초기화."""
        self._promoted_this_cycle = 0
        self._demoted_this_cycle = 0

    # -- 조회 ----------------------------------------------------------

    def get_slot(self, ticker: str) -> Optional[StreamSlot]:
        return self._slots.get(ticker)

    def get_state(self, ticker: str) -> str:
        slot = self._slots.get(ticker)
        if slot is None:
            return "unknown"
        return slot.state

    def list_by_state(self, state: str) -> list[StreamSlot]:
        return [s for s in self._slots.values() if s.state == state]

    # -- 핵심 전이 ------------------------------------------------------

    def can_promote(self, ticker: str, *, now: Optional[float] = None) -> tuple[bool, str]:
        """승격 가능 여부 + 사유 반환.

        반환: (True, "") 또는 (False, "reason")
        """
        if now is None:
            now = time.monotonic()

        # 배치 제한
        if self._promoted_this_cycle >= self.max_promote_per_cycle:
            return False, "max_promote_per_cycle_reached"

        slot = self._slots.get(ticker)
        if slot is None:
            # rest_watch 진입 전 — 첫 승격 가능
            return True, ""

        if slot.state == "ws_active":
            return False, "already_ws_active"

        if slot.state == "cooldown":
            if now < slot.cooldown_until:
                return False, "cooldown_not_expired"
            # cooldown 만료 — 승격 가능
            return True, ""

        # rest_watch — 승격 가능
        return True, ""

    def mark_promoted(
        self, ticker: str, strategy_id: str, reason: str,
        *, now: Optional[float] = None,
    ) -> bool:
        """승격 기록. 호출자가 WS subscribe 성공 후 호출.

        반환: True (정상 기록) / False (배치 제한 등으로 거부)
        """
        if now is None:
            now = time.monotonic()

        ok, why = self.can_promote(ticker, now=now)
        if not ok:
            logger.debug("[stream_pool] promote 거부: %s %s", ticker, why)
            return False

        self._slots[ticker] = StreamSlot(
            ticker=ticker,
            strategy_id=strategy_id,
            state="ws_active",
            reason=reason,
            since=now,
            ws_hold_until=now + self.min_ws_hold_secs,
            cooldown_until=0.0,
        )
        self._promoted_this_cycle += 1
        logger.info("[stream_pool] promoted: %s strategy=%s reason=%s", ticker, strategy_id, reason)
        return True

    def can_demote(self, ticker: str, *, now: Optional[float] = None) -> tuple[bool, str]:
        if now is None:
            now = time.monotonic()

        slot = self._slots.get(ticker)
        if slot is None:
            return False, "no_slot"
        if slot.state != "ws_active":
            return False, "not_ws_active"
        if slot.is_protected_from_demote():
            return False, "protected_strategy"
        if now < slot.ws_hold_until:
            return False, "min_ws_hold_not_expired"
        if self._demoted_this_cycle >= self.max_demote_per_cycle:
            return False, "max_demote_per_cycle_reached"
        return True, ""

    def mark_demoted(
        self, ticker: str, reason: str = "signal_faded",
        *, now: Optional[float] = None,
    ) -> bool:
        """강등 기록. 호출자가 WS unsubscribe 성공 후 호출.

        cooldown_until = now + ws_rejoin_cooldown_secs.
        """
        if now is None:
            now = time.monotonic()

        ok, why = self.can_demote(ticker, now=now)
        if not ok:
            logger.debug("[stream_pool] demote 거부: %s %s", ticker, why)
            return False

        slot = self._slots[ticker]
        slot.state = "cooldown"
        slot.reason = reason
        slot.since = now
        slot.ws_hold_until = 0.0
        slot.cooldown_until = now + self.ws_rejoin_cooldown_secs
        self._demoted_this_cycle += 1
        logger.info(
            "[stream_pool] demoted: %s strategy=%s reason=%s cooldown_until=%.0f",
            ticker, slot.strategy_id, reason, slot.cooldown_until,
        )
        return True

    def mark_rest_watch(self, ticker: str, strategy_id: str) -> None:
        """REST 관찰 진입 (slot 신규 생성 또는 cooldown 후 복귀)."""
        existing = self._slots.get(ticker)
        if existing is not None and existing.state == "ws_active":
            # ws_active 인 종목은 그대로 — rest_watch 회귀 안 함
            return
        self._slots[ticker] = StreamSlot(
            ticker=ticker,
            strategy_id=strategy_id,
            state="rest_watch",
            reason="rest_observation",
            since=time.monotonic(),
        )

    def expire_cooldowns(self, *, now: Optional[float] = None) -> list[str]:
        """cooldown 만료 슬롯을 rest_watch 로 복귀. 만료된 ticker list 반환."""
        if now is None:
            now = time.monotonic()
        expired: list[str] = []
        for ticker, slot in list(self._slots.items()):
            if slot.state == "cooldown" and now >= slot.cooldown_until:
                slot.state = "rest_watch"
                slot.reason = "cooldown_expired"
                slot.since = now
                slot.cooldown_until = 0.0
                expired.append(ticker)
        if expired:
            logger.info("[stream_pool] cooldown 만료: %d 종목", len(expired))
        return expired

    # -- 가시화 / API 응답 --------------------------------------------

    def snapshot(self) -> dict:
        """`/api/realtime/stream-status` 응답용 (사이클 15-C 가 사용).

        반환: `{"rest": [...], "ws": [...], "dropped": [...]}`
        """
        rest_list, ws_list, dropped_list = [], [], []
        now = time.monotonic()
        for slot in self._slots.values():
            entry = {
                "ticker": slot.ticker,
                "strategy": slot.strategy_id,
                "reason": slot.reason,
                "since_secs": round(now - slot.since, 1),
            }
            if slot.state == "rest_watch":
                rest_list.append(entry)
            elif slot.state == "ws_active":
                entry["min_hold_remaining_secs"] = max(0.0, round(slot.ws_hold_until - now, 1))
                ws_list.append(entry)
            elif slot.state == "cooldown":
                entry["cooldown_remaining_secs"] = max(0.0, round(slot.cooldown_until - now, 1))
                dropped_list.append(entry)
        return {
            "rest": sorted(rest_list, key=lambda e: e["ticker"]),
            "ws": sorted(ws_list, key=lambda e: e["ticker"]),
            "dropped": sorted(dropped_list, key=lambda e: e["ticker"]),
        }


# 모듈 싱글톤 (scheduler 가 import 해서 사용)
stream_pool_manager = StreamPoolManager()
