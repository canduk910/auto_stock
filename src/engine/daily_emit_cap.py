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

from datetime import datetime, timedelta, timezone
from typing import Generic, TypeVar

K = TypeVar("K")

# 사이클 258 — `KstDailyEmitCap` KST 날짜 판정 전용(기존 `DailyEmitCap` 는 미참조,
# 클래스 byte 불변 보존).
_KST = timezone(timedelta(hours=9))


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


class KstDailyEmitCap(DailyEmitCap[K]):
    """KST 날짜 자기 리셋 + peek→로그→mark 표준 진입점 (사이클 258, 카드 #4).

    `DailyEmitCap` 은 날짜 개념이 없어 22곳의 호출부가 손으로
    ``if self._x_day != today: self._x_day = today; cap.reset_daily()`` 블록을
    반복해 왔다(사이클 56 헤더가 "일일 정산 시 reset_daily()" 만 상정했으나,
    scheduler 3,999L 상한 + 파일별 무접촉 규약 탓에 정산 훅 배선이 불가능해
    자기 리셋을 강제당했다). 이 서브클래스가 그 블록을 흡수한다.

    ``now`` 는 전부 키워드 전용(``*, now=``) — 위치 인자로 넘기면 안 된다
    (기존 ``should_emit(key)`` 1-인자 호출과 시그니처 호환을 유지하기 위해).
    생략 시 ``datetime.now(KST)`` (테스트는 freezegun 또는 명시 주입으로 결정화).

    선점 계약(K-13) — ``mark_emitted`` 가 **한 번도 동기화된 적 없는** 인스턴스에서
    먼저 불리면(즉 어떤 ``should_emit``/``mark_emitted`` 도 거치지 않은 새 cap에
    picker 가 값을 먼저 심는 기존 테스트 픽스처 패턴), 그 선점은 이어지는 첫
    ``should_emit`` 의 날짜 프라이밍에 지워지지 않는다 — 프라이밍(최초 동기화)은
    ``reset_daily()`` 를 부르지 않는다(비울 것이 없는 새 인스턴스이므로). 날짜가
    실제로 바뀔 때만(=두 번째 이후 동기화에서 날짜 값이 달라질 때만) 리셋한다.
    """

    def __init__(self) -> None:
        super().__init__()
        self._day: str = ""

    @staticmethod
    def _today(now: "datetime | None" = None) -> str:
        """KST 날짜 문자열 산출 — 실패(예: `now` 가 datetime 이 아님)는 "" 로 흡수."""
        try:
            dt = now if now is not None else datetime.now(_KST)
            return dt.date().isoformat()
        except Exception:
            return ""

    def _sync_day(self, now: "datetime | None" = None) -> None:
        """KST 날짜가 바뀌었으면 자기 `reset_daily()`.

        최초 동기화(``self._day == ""``)는 프라이밍만 하고 리셋하지 않는다
        (K-13 — 아직 아무것도 갱신 안 한 새 인스턴스에 리셋할 대상이 없다 +
        `mark_emitted` 로 미리 심어둔 선점을 지우지 않는다).
        """
        today = self._today(now)
        if not today:
            return
        if self._day == "":
            self._day = today
            return
        if self._day != today:
            self._day = today
            self.reset_daily()

    def should_emit(self, key: K, *, now: "datetime | None" = None) -> bool:
        """key 가 오늘(KST) 아직 emit 안 됐으면 True. 호출마다 자기 날짜 동기화."""
        try:
            self._sync_day(now)
        except Exception:  # pragma: no cover — never-raise
            pass
        return super().should_emit(key)

    def mark_emitted(self, key: K, *, now: "datetime | None" = None) -> None:
        """key 를 오늘 emit 됨으로 등록.

        아직 한 번도 동기화된 적 없는 인스턴스(``self._day == ""``)에서 먼저
        불리면 날짜만 프라이밍한다(K-13 선점 계약 — 리셋 없음). 이미 동기화된
        뒤에는 이 메서드가 날짜를 건드리지 않는다 — 롤오버 판정은 `should_emit`
        (=`emit_once` 의 peek) 단일 지점에서만 한다(이중 판정에 의한 표류 방지).
        """
        if self._day == "":
            primed = self._today(now)
            if primed:
                self._day = primed
        super().mark_emitted(key)

    def emit_once(
        self, key: K, log_fn, msg: str, *args, now: "datetime | None" = None,
    ) -> bool:
        """peek → ``log_fn(msg, *args)`` → mark. 표준 관측 진입점 (카드 #4/#5).

        ``log_fn`` 이 던지면 mark 하지 않는다(peek→로그→mark, cycle226 D-3) —
        로그 자기실패가 그날의 관측을 지우면 안 된다. 이 메서드 자체는
        **never-raise** — 내부 어떤 실패(예: unhashable key)도 흡수하고
        `observer_trace.trace_observer_failure` 로 흔적(디버그 스택)을 남긴 뒤
        False 를 반환한다(무흔적 `pass` 금지, 카드 #5 정책).
        """
        try:
            if not self.should_emit(key, now=now):
                return False
            log_fn(msg, *args)
            self.mark_emitted(key, now=now)
            return True
        except Exception:
            try:
                from src.engine.observer_trace import trace_observer_failure
                trace_observer_failure("[emit_once]", str(key), None, now=now)
            except Exception:  # pragma: no cover — 2차 예외도 흡수
                pass
            return False
