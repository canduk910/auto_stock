"""사이클 56-A — 일일 emit cap 제네릭 헬퍼.

3 곳 동형 패턴 (사이클 31 R6 RiskManager / 사이클 52→55 SellRejectionTracker /
사이클 54 OrderEngine NXT) 통합 추상화. key 는 str (ticker) 또는
tuple[str, str] ((ticker, strategy_id)) 등 hashable 모두 허용.

사용 패턴:
    cap = DailyEmitCap[str]()  # ticker 단위
    if cap.should_emit(ticker):
        await write_log(...)
        cap.mark_emitted(ticker)
    # 일일 정산 시
    cap.reset_daily()

마이그레이션 현황 (사이클 56-B/C/D):
    - 56-B  SellRejectionTracker._logged_today  (set[str])          ← 완료
    - 56-C  OrderEngine._nxt_downgrade_logged_today  (set[str])     ← 완료
    - 56-D  RiskManager._risk_silent_skip_logged_today  (set[tuple[str, str]])  ← 완료

선례:
    사이클 48  src/engine/stale_tracker.py::StaleTrackerState
    사이클 51  src/engine/boot_manager.py
    사이클 55  src/engine/sell_rejection.py::SellRejectionTracker
"""
from __future__ import annotations

from typing import Generic, TypeVar

K = TypeVar("K")


class DailyEmitCap(Generic[K]):
    """ticker별 또는 페어별 일일 1회 emit cap.

    사용 패턴:
        cap = DailyEmitCap[str]()  # ticker 단위
        if cap.should_emit(ticker):
            await write_log(...)
            cap.mark_emitted(ticker)
        # 일일 정산 시
        cap.reset_daily()
    """

    def __init__(self) -> None:
        self._emitted: set[K] = set()

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def should_emit(self, key: K) -> bool:
        """key 가 오늘 아직 emit 안 됐으면 True."""
        return key not in self._emitted

    def mark_emitted(self, key: K) -> None:
        """key 를 오늘 emit 됨으로 등록."""
        self._emitted.add(key)

    def reset_daily(self) -> None:
        """일일 정산 — 모든 emit 기록 clear."""
        self._emitted.clear()

    # ------------------------------------------------------------------
    # 호환 layer — 기존 set 직접 접근 패턴 호환 (사이클 56-B/C/D 마이그레이션 시)
    # ------------------------------------------------------------------

    def __contains__(self, key: object) -> bool:
        """기존 ``key in _emitted_set`` 패턴 호환."""
        return key in self._emitted

    def __len__(self) -> int:
        """기존 ``len(_emitted_set)`` 패턴 호환."""
        return len(self._emitted)

    def __eq__(self, other: object) -> bool:
        """기존 ``cap == set()`` 비교 호환.

        사이클 56-B/C/D 마이그레이션 시 회귀 테스트가 ``== set()`` / ``== {}`` 등
        set 직접 비교를 사용하는 경우 내부 _emitted set 과 비교.
        DailyEmitCap 끼리 비교 시에도 _emitted 내용 비교.
        """
        if isinstance(other, DailyEmitCap):
            return self._emitted == other._emitted
        if isinstance(other, set):
            return self._emitted == other
        return NotImplemented

    def __repr__(self) -> str:
        return f"DailyEmitCap({self._emitted!r})"

    def clear(self) -> None:
        """기존 set.clear() 호환 별칭."""
        self.reset_daily()

    def add(self, key: K) -> None:
        """기존 set.add() 호환 별칭."""
        self.mark_emitted(key)

    def discard(self, key: K) -> None:
        """기존 set.discard() 호환.

        사이클 54 ``_market_closed_blocked_logged_today.discard`` 패턴 대응.
        존재하지 않는 key 는 예외 없이 무시한다.
        """
        self._emitted.discard(key)
