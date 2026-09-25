"""사이클 134 (2026-06-15) — scheduler 4 task loop 공통 lifecycle 헬퍼 (카드 #21 영속).

배경:
- 사이클 101/106 `_full_universe_load_task_loop` + 사이클 122 daily + 사이클 126 basics +
  사이클 129/133 master = 4 동일 lifecycle 패턴 (사이클 106 race 차단 + while + wait_until).
- 사이클 130 refactor-review 권고 카드 #21 MEDIUM (-193L 추정).
- 사이클 133 master metrics 일관성 통합 후 자연 발주 (record_fn/flush_fn 인자 영역 활용).

영속 의무 매트릭스:
- 사이클 67 facade re-export 패턴 답습 (4 task loop facade 영속).
- 사이클 79 G-AST2 영속 (task_attrs 4 위치 영속 — instance + 3 cancel 사이트).
- 사이클 88 G-REJECT graceful 영속 (CancelledError + Exception 분리).
- 사이클 106 lifecycle race 차단 패턴 영속 (start() 직후 즉시 1회 + while 루프).
- 사이클 122/126/129/133 task 패턴 영속.

매매 안전성 영향 0 (lifecycle hook 영역 한정 + scanner/risk/order/realtime/auth 변경 0).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time
from typing import Awaitable, Callable, Protocol

from src.db._kst import KST as _KST

logger = logging.getLogger("src.engine.scheduler")

# 사이클 193 — 재시작 immediate run 신선도 게이트 기본 시간 임계 (h).
# 16:10 저녁 basics 성공 → 익일 07:50 boot = ~15.7h < 20h → immediate skip.
# master·financial 이 계속 쓴다(cycle363 이후로도 시간 게이트 정본 — 값 불변).
IMMEDIATE_FRESH_SKIP_HOURS = 20.0


def _now_kst() -> datetime:
    """cycle363 — 슬롯 모드의 유일한 시각 seam(KST aware). 테스트가 이 이름을 패치한다."""
    return datetime.now(_KST)


class _SchedulerLike(Protocol):
    """헬퍼 영역 영속 scheduler protocol (TradingScheduler 호환)."""

    _running: bool

    async def _wait_until(
        self, target_time: time, *, advance_if_passed: bool = False
    ) -> None:  # type: ignore[empty-body]
        ...


async def _evaluate_slot_gate(
    task_label: str,
    wait_time: time,
    force_check: Callable[[], Awaitable[bool]] | None,
    skip_if_absent: bool,
    *,
    force_run_reason: str = "below_floor",
) -> tuple[bool, str, str | None, str | None]:
    """cycle363 — 영업일 슬롯 게이트 판정 (지시서 §2.2 순서 ①~⑦).

    반환 = (should_run, reason, marker_iso, slot_iso). never-raise — 각 조회 단계의
    예외는 「실행」쪽으로 fail-open 한다(사용자 지시: 휴장일 조회 실패 = 실행).
    naive 마커(파싱 뒤 `utcoffset() is None`)는 KST 로 가정하지 않고 파싱 실패와
    같은 등급(`marker_unparseable`)으로 흡수한다. leaf 가 계약을 어겨 tz-aware
    datetime 이 아닌 슬롯을 돌려줘도(naive datetime · date · str 등) `calendar_unknown`
    으로 흡수해 raise 하지 않는다.
    """
    # ① force check — True/예외면 마커가 fresh 여도 무조건 실행.
    # cycle363 F-4 — `force_run_reason` 은 호출부가 그 사유를 구분해 로그에 남길 수
    # 있게 하는 키워드 전용 확장이다(기본값 "below_floor" = full_universe 행 수
    # 하한과 완전히 같은 문자열·같은 관측 계약, 회귀 0). 예외 경로는 여전히
    # "force_check_error" 로 고정 — 그 값은 "판정 자체가 실패했다" 는 별개 사실이다.
    if force_check is not None:
        try:
            triggered = await force_check()
        except Exception:
            return True, "force_check_error", None, None
        if triggered:
            return True, force_run_reason, None, None

    # ② 마커 조회.
    try:
        from src.db.system_config import get_task_last_success as _get_marker  # noqa: PLC0415

        last_iso = await _get_marker(task_label)
    except Exception:
        return True, "marker_error", None, None

    # ③ 마커 None.
    if last_iso is None:
        if skip_if_absent:
            return False, "no_marker", None, None
        return True, "no_marker", None, None

    # ④ 마커 파싱 실패(naive 마커도 같은 등급 — cycle363 F-2). naive 를 KST 로 가정하지 않는다.
    try:
        last_dt = datetime.fromisoformat(last_iso)
        if last_dt.utcoffset() is None:
            raise ValueError("naive marker — aware 비교 불가")
    except Exception:
        return True, "marker_unparseable", last_iso, None

    # ⑤ 마커 > now (시계 이상 방어). never-raise — 비교 실패도 파싱 실패와 같은 등급으로 흡수.
    now = _now_kst()
    try:
        is_future = last_dt > now
    except Exception:
        return True, "marker_unparseable", last_iso, None
    if is_future:
        return True, "future_marker", last_iso, None

    # ⑥ 휴장일 leaf — 직전 영업일 슬롯. leaf 가 계약을 어겨도(비 tz-aware) 모름과 동급.
    try:
        from src.engine import trading_calendar as _tc_mod  # noqa: PLC0415

        slot_dt = await _tc_mod.latest_passed_trading_slot(now, wait_time)
    except Exception:
        slot_dt = None
    if not isinstance(slot_dt, datetime) or slot_dt.utcoffset() is None:
        return True, "calendar_unknown", last_iso, None

    # ⑦ 마커 ≥ 슬롯 → fresh(skip), 아니면 stale(run). never-raise.
    try:
        is_fresh = last_dt >= slot_dt
        slot_iso = slot_dt.isoformat()
    except Exception:
        return True, "calendar_unknown", last_iso, None
    if is_fresh:
        return False, "fresh", last_iso, slot_iso
    return True, "stale", last_iso, slot_iso


def _emit_immediate_gate_log(
    task_label: str, should_run: bool, reason: str, marker_iso: str | None, slot_iso: str | None
) -> None:
    """`[immediate_gate]` 판정 로그 1행 + SKIP 시 cycle193 호환 legacy 1행."""
    marker_field = marker_iso if marker_iso is not None else "None"
    slot_field = slot_iso if slot_iso is not None else "None"
    try:
        logger.info(
            "[immediate_gate] task=%s decision=%s reason=%s marker=%s slot=%s",
            task_label,
            "run" if should_run else "skip",
            reason,
            marker_field,
            slot_field,
        )
    except Exception:
        pass
    if not should_run:
        try:
            logger.info(
                "[%s] immediate run skip — %s last_success=%s",
                task_label,
                reason,
                marker_field,
            )
        except Exception:
            pass


async def run_periodic_task_loop(
    *,
    scheduler: _SchedulerLike,
    task_label: str,
    wait_time: time,
    once_callable: Callable[..., Awaitable[dict]],
    record_fn: Callable[[dict], None],
    flush_fn: Callable[[], None],
    summary_log_format: str,
    summary_keys: tuple[str, ...],
    immediate_first_run: bool = True,
    retry_delay_secs: int = 60,
    initial_delay_secs: int = 0,
    immediate_skip_if_fresh_hours: float | None = None,
    immediate_skip_if_fresh_since_trading_slot: bool = False,
    immediate_force_run_check: Callable[[], Awaitable[bool]] | None = None,
    immediate_skip_if_marker_absent: bool = False,
    immediate_force_run_reason: str = "below_floor",
) -> None:
    """4 task loop 공통 lifecycle 헬퍼 (사이클 134 카드 #21 영속).

    동작 영구 영속 (사이클 106 lifecycle race 차단 + 사이클 88 G-REJECT graceful):

    1. immediate_first_run=True 시 start() 직후 즉시 1회 실행
       (사이클 106 lifecycle race 차단 패턴 답습 — _wait_until 대기 전 즉시 실행).
       CancelledError → return / Exception → graceful log + 계속 진행.

    2. while 루프 — _wait_until(wait_time) → once_callable() → record_fn(summary) →
       flush_fn() → logger.info(summary).
       CancelledError → break / Exception → graceful log + asyncio.sleep(retry_delay_secs).

    Args:
        scheduler: TradingScheduler 인스턴스 (_running 플래그 + _wait_until 메서드 영속).
        task_label: 로그 prefix 영속 (예: "full_universe_load" / "stock_master_basics_refresh").
        wait_time: 매일 실행 시각 (예: time(20, 0, 5) / time(16, 30)).
        once_callable: 1회 실행 영역 (예: `_full_universe_load_once`). force 인자 미사용 영속.
        record_fn: metrics collector record 영역 (사이클 133 헬퍼 영속 답습).
        flush_fn: metrics collector flush 영역 (사이클 78 G-AST1 영속).
        summary_log_format: `logger.info(format, *args)` 영역 format string (예: "[X] total=%d ...").
        summary_keys: summary dict 키 영역 (format args 영속). 키 부재 시 0 디폴트.
        immediate_first_run: start() 직후 즉시 1회 실행 영역 (True 영속, 사이클 106 답습).
        retry_delay_secs: Exception 후 retry 영역 (60s 영속, 사이클 88 G-REJECT 답습).
        initial_delay_secs: 사이클 158 Q3 stagger 인자 (default 0 = 회귀 보존).
            > 0 시 immediate_first_run 진입 *전* asyncio.sleep(N) 발화 — 4 task 동시 발화
            race 차단 (Supabase HTTP/2 풀 ConnectionTerminated 폭주 영역 차단).
        immediate_skip_if_fresh_hours: 사이클 193 신선도 게이트 (default None = 기존 행위 완전 동일).
            지정 시 immediate 블록에서 `system_config.get_task_last_success(task_label)`
            마커가 N시간 이내면 immediate once() skip (정기 while 루프 발화는 무관 영속).
            once() 성공 직후 (immediate + while 양쪽) `set_task_last_success(task_label, KST iso)`
            기록 (try/except graceful). None = 마커 조회/기록 0건 (신규 DB 접근 0).
            음수 경과(미래 마커/시계 이상) 방어: `0 <= elapsed < hours * 3600` 조건.
        immediate_skip_if_fresh_since_trading_slot: cycle363 — 영업일 슬롯 게이트
            (default False = 기존 행위 완전 동일). True 면 슬롯 = `wait_time` 이고
            판정 순서는 `_evaluate_slot_gate` 문서 참조. `immediate_skip_if_fresh_hours`
            와 동시 지정하면 함수 진입 즉시 `ValueError`(프로그래밍 오류).
        immediate_force_run_check: cycle363 — True 반환/예외 시 마커가 fresh 여도
            무조건 실행(예: full_universe 행 수 하한). 슬롯 모드 전용, 판정 ①.
        immediate_skip_if_marker_absent: cycle363 — 마커가 없을 때(None) skip 할지
            (default False = 기존 「마커 없음 = 실행」 유지). full_universe 부트스트랩 전용.
        immediate_force_run_reason: cycle363 F-4 — `immediate_force_run_check` 가
            True 를 반환했을 때 남길 사유 문자열(default "below_floor" = full_universe
            행 수 하한과 동일 — 기존 호출부는 diff 0). basics 의 KIS 출처 키 결손
            강제 재실행은 `"kis_keys_missing"` 을 넘긴다. 슬롯 모드 전용, force_check
            자체가 예외를 던진 경우는 이 값과 무관하게 항상 `"force_check_error"`.

    영속 의무 매트릭스:
    - 사이클 88 G-REJECT graceful 영속 (CancelledError + Exception 분리).
    - 사이클 106 lifecycle race 차단 패턴 영속.
    - 사이클 78 G-AST1 영속 (record + flush 호출 사이트 영속).
    """
    if immediate_skip_if_fresh_hours is not None and immediate_skip_if_fresh_since_trading_slot:
        raise ValueError(
            "immediate_skip_if_fresh_hours 와 immediate_skip_if_fresh_since_trading_slot 은 "
            "동시에 지정할 수 없다 (cycle363 — 시간 게이트와 영업일 슬롯 게이트는 배타적)"
        )

    def _build_log_args(summary: dict) -> tuple:
        """summary 키 영역에서 format args 영역 영구 영속 생성 영역."""
        return tuple(summary.get(key, 0) for key in summary_keys)

    # 사이클 106 lifecycle race 차단 패턴 답습 — start() 직후 즉시 1회 실행
    if immediate_first_run:
        # 사이클 158 Q3 stagger — 4 task 동시 발화 race 차단
        if initial_delay_secs > 0:
            try:
                await asyncio.sleep(initial_delay_secs)
            except asyncio.CancelledError:
                return

        # 사이클 193 신선도 게이트 — N시간 이내 성공 마커 있으면 immediate skip
        _run_immediate = True
        if immediate_skip_if_fresh_hours is not None:
            try:
                from src.db.system_config import get_task_last_success as _get_marker  # noqa: PLC0415
                from src.db._kst import KST as _KST  # noqa: PLC0415
                _last_iso = await _get_marker(task_label)
                if _last_iso is not None:
                    _last_dt = datetime.fromisoformat(_last_iso)
                    _now_dt = datetime.now(_KST)
                    _elapsed_secs = (_now_dt - _last_dt).total_seconds()
                    if 0 <= _elapsed_secs < immediate_skip_if_fresh_hours * 3600:
                        logger.info(
                            "[%s] immediate run skip — fresh last_success=%s",
                            task_label,
                            _last_iso,
                        )
                        _run_immediate = False
            except Exception:
                pass  # graceful — 조회/파싱 예외 시 즉시 실행 (안전 방향)
        elif immediate_skip_if_fresh_since_trading_slot:
            # 사이클 363 — 영업일 슬롯 게이트(판정 = `_evaluate_slot_gate`).
            _should_run, _reason, _marker_iso, _slot_iso = await _evaluate_slot_gate(
                task_label,
                wait_time,
                immediate_force_run_check,
                immediate_skip_if_marker_absent,
                force_run_reason=immediate_force_run_reason,
            )
            _emit_immediate_gate_log(task_label, _should_run, _reason, _marker_iso, _slot_iso)
            if not _should_run:
                _run_immediate = False

        if _run_immediate:
            try:
                summary = await once_callable()
                record_fn(summary)
                flush_fn()
                logger.info(summary_log_format, *_build_log_args(summary))
                # 사이클 193 — immediate 성공 마커 기록 (graceful).
                # 사이클 363 — 슬롯 모드도 기록한다(다음 부팅 판정의 유일한 근거).
                if immediate_skip_if_fresh_hours is not None or immediate_skip_if_fresh_since_trading_slot:
                    try:
                        from src.db.system_config import set_task_last_success as _set_marker  # noqa: PLC0415
                        from src.db._kst import now_kst_iso as _now_kst_iso  # noqa: PLC0415
                        await _set_marker(task_label, _now_kst_iso())
                    except Exception:
                        logger.debug("[%s] 신선도 마커 기록 실패 graceful", task_label)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("[%s] 초기 실행 예외 graceful", task_label)

    # while 루프 — _wait_until → once → record + flush + logger
    # 사이클 160 hotfix — `advance_if_passed=True` 명시 (task_loop_helper 폭주 차단 의무).
    # `_wait_until` 본질 복원 (run_daily phase 전환은 즉시 break) + helper 영역만 내일 미루기.
    while scheduler._running:
        try:
            await scheduler._wait_until(wait_time, advance_if_passed=True)
            if not scheduler._running:
                break
            summary = await once_callable()
            record_fn(summary)
            flush_fn()
            logger.info(summary_log_format, *_build_log_args(summary))
            # 사이클 193 — while 루프 성공 마커 기록 (graceful).
            # 사이클 363 — 슬롯 모드도 기록한다(F-8: 정기 발화는 게이트와 무관 · 마커는 기록).
            if immediate_skip_if_fresh_hours is not None or immediate_skip_if_fresh_since_trading_slot:
                try:
                    from src.db.system_config import set_task_last_success as _set_marker  # noqa: PLC0415
                    from src.db._kst import now_kst_iso as _now_kst_iso  # noqa: PLC0415
                    await _set_marker(task_label, _now_kst_iso())
                except Exception:
                    logger.debug("[%s] 신선도 마커 기록 실패 graceful", task_label)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("[%s] task loop 예외 graceful", task_label)
            await asyncio.sleep(retry_delay_secs)
