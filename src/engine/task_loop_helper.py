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

logger = logging.getLogger("src.engine.scheduler")

# 사이클 193 — 재시작 immediate run 신선도 게이트 기본 시간 임계 (h).
# 16:10 저녁 basics 성공 → 익일 07:50 boot = ~15.7h < 20h → immediate skip.
IMMEDIATE_FRESH_SKIP_HOURS = 20.0


class _SchedulerLike(Protocol):
    """헬퍼 영역 영속 scheduler protocol (TradingScheduler 호환)."""

    _running: bool

    async def _wait_until(
        self, target_time: time, *, advance_if_passed: bool = False
    ) -> None:  # type: ignore[empty-body]
        ...


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

    영속 의무 매트릭스:
    - 사이클 88 G-REJECT graceful 영속 (CancelledError + Exception 분리).
    - 사이클 106 lifecycle race 차단 패턴 영속.
    - 사이클 78 G-AST1 영속 (record + flush 호출 사이트 영속).
    """

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
                    _now_kst = datetime.now(_KST)
                    _elapsed_secs = (_now_kst - _last_dt).total_seconds()
                    if 0 <= _elapsed_secs < immediate_skip_if_fresh_hours * 3600:
                        logger.info(
                            "[%s] immediate run skip — fresh last_success=%s",
                            task_label,
                            _last_iso,
                        )
                        _run_immediate = False
            except Exception:
                pass  # graceful — 조회/파싱 예외 시 즉시 실행 (안전 방향)

        if _run_immediate:
            try:
                summary = await once_callable()
                record_fn(summary)
                flush_fn()
                logger.info(summary_log_format, *_build_log_args(summary))
                # 사이클 193 — immediate 성공 마커 기록 (graceful)
                if immediate_skip_if_fresh_hours is not None:
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
            # 사이클 193 — while 루프 성공 마커 기록 (graceful)
            if immediate_skip_if_fresh_hours is not None:
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
