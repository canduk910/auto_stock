"""저녁 데이터 적재 task 루프 모듈 (refactor-review B1, 2026-08-09).

scheduler.py 재비대(사이클 67 3,007L → 4,230L) 시정 — 16:00~20:00 데이터 계층 task
8종의 본체를 위임 분해(사이클 51 boot_manager / 67 stale_manager 패턴 답습).
scheduler 는 2줄 wrapper 만 유지하고 본체는 이 모듈로 이관. 신규 데이터 task 는 여기 추가
= scheduler 본체 재유입 구조 차단.

⚠️ 매수/매도/정산 hot path 무관 (사이클 38 명문화 — scanner 매수 진입 *전* 데이터 계층).
순환 import 회피: 이 모듈은 scheduler 를 import 하지 않는다. 모듈 전역 `TIME_*` 상수는
wrapper 가 `wait_time` 인자로 전달, 함수는 `scheduler` 인스턴스만 참조.
로그는 운영자 grep 이력 보존을 위해 `logging.getLogger("src.engine.scheduler")` 사용
(사이클 60 I1 명시 binding 답습).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

# 운영 로그 접두사([full_universe_load_summary] 등) grep 이력 단절 방지 (사이클 60 I1).
logger = logging.getLogger("src.engine.scheduler")

# cycle363 — full_universe 부트스트랩 행 수 하한(자가 치유 안전망). 운영 3,583행 ·
# 2026-08-08 degrade 사고 60행 — 정상 운영보다 한참 아래, degrade 보다 한참 위.
FULL_UNIVERSE_IMMEDIATE_MIN_ROWS = 2000


async def _full_universe_below_immediate_floor() -> bool:
    """cycle363 — `stock_master.count_active() < FULL_UNIVERSE_IMMEDIATE_MIN_ROWS`.

    `count_active` 는 호출 시점에 `src.db.stock_master` 모듈 속성으로 찾는다(지연 import).
    그 함수 자체가 예외 시 0 을 반환하므로(DB 장애 = 실행, fail-safe) 이 콜백은 별도
    방어를 두지 않는다 — `test_cycle106_full_universe_load_lifecycle` 이 이 동작에 기댄다.
    """
    from src.db import stock_master as _stock_master_mod  # noqa: PLC0415

    count = await _stock_master_mod.count_active()
    return count < FULL_UNIVERSE_IMMEDIATE_MIN_ROWS


# cycle363 F-4 — basics 강제 재실행 임계(결측 행 수). 운영 실측 결측 0행(정상) ·
# 월요일 KRX 전량 덮어쓰기 사고 규모 2,670~2,674행 — 그 사이 어디든 안전하게
# 걸리도록 넉넉히 잡는다.
STOCK_MASTER_BASICS_FORCE_RUN_MISSING_THRESHOLD = 100


async def _stock_master_basics_kis_keys_missing_above_threshold() -> bool:
    """cycle363 F-4 — full_universe 만 돈 월요일 아침의 자가 치유.

    full_universe(+0초)가 RUN 하고 basics(+480초)가 SKIP 하면, KRX 적재의
    하드코딩 False(`nxt_tradable`·`krx_halted`·`admin_item`)와 KIS 출처 키 부재가
    16:10 정기 실행까지 방치된다(독립 검증 finding #6). 판정은 full_universe
    실행 *뒤* 라 실제 손상(결측 행 수)을 보고 결정한다.

    `count_missing_kis_provenance_key()` 는 **의도적으로 예외를 삼키지 않는다** —
    쿼리 실패가 여기로 전파되면 `_evaluate_slot_gate` 의 force_check 예외 처리가
    `reason=force_check_error` 로 RUN 시킨다(사용자 결정: 쿼리 실패는 RUN 쪽).
    """
    from src.db import stock_master as _stock_master_mod  # noqa: PLC0415

    missing = await _stock_master_mod.count_missing_kis_provenance_key()
    return missing > STOCK_MASTER_BASICS_FORCE_RUN_MISSING_THRESHOLD


async def scan_pool_eager_refresh_loop(scheduler: Any) -> None:
    """사이클 83 — _scan_loop 후보 풀 ticker stock_master 5분 eager refresh task.

    24h TTL fresh skip + 50ms sleep (Rate Limit) + 마지막 1회 flush 보장 (사이클 78).
    """
    from src.engine.scanner import (
        _scan_pool_eager_refresh_loop as _scanner_eager_refresh,
        flush_scan_pool_eager_refresh_collector,
        _SCAN_POOL_EAGER_REFRESH_WINDOW_SECS,
    )

    while scheduler._running:
        await asyncio.sleep(_SCAN_POOL_EAGER_REFRESH_WINDOW_SECS)
        try:
            await _scanner_eager_refresh()
        except Exception:
            logger.exception("[scan_pool_eager_refresh] refresh 실패")
        try:
            flush_scan_pool_eager_refresh_collector()
        except Exception:
            logger.exception("[scan_pool_eager_refresh_collector] flush 실패")
        if not scheduler._running:
            break


async def full_universe_load_task_loop(scheduler: Any, *, wait_time) -> None:
    """사이클 101/106/134 — 매일 20:00:05 전체 유니버스 일괄 적재 task facade.

    run_periodic_task_loop 헬퍼 위임 (사이클 67 facade 답습). 24h TTL idempotency +
    lifecycle race 차단(사이클 106) 은 헬퍼 영역에서 흡수.

    cycle363 — 영업일 슬롯 게이트로 전환한다(TTL 멱등만으로는 월요일·연휴 뒤 아침에
    직전 영업일보다 더 오래된 KRX 값이 최신 값을 덮는 것을 못 막는다 — 09-21(월) 실측이
    09-18(목) 값을 09-22(화) 값 위에 썼다). 부트스트랩(마커 영구 결측)은 행 수 하한이
    충분하면 skip 한다 — 「마커 없음 = 실행」이면 09-28 에 같은 덮어쓰기가 재현된다.
    """
    from src.engine.scanner import _full_universe_load_once as _load_once
    from src.engine.stock_master_metrics import (
        record_full_universe_load_summary,
        flush_full_universe_load_collector,
    )
    from src.engine.task_loop_helper import run_periodic_task_loop

    await run_periodic_task_loop(
        scheduler=scheduler,
        task_label="full_universe_load",
        wait_time=wait_time,  # 20:00:05
        once_callable=_load_once,
        record_fn=record_full_universe_load_summary,
        flush_fn=flush_full_universe_load_collector,
        summary_log_format=(
            "[full_universe_load_summary] total=%d kospi=%d kosdaq=%d "
            "fetched=%d skipped_ttl=%d failed=%d elapsed_ms=%d"
        ),
        summary_keys=(
            "total", "kospi", "kosdaq",
            "fetched", "skipped_ttl", "failed", "elapsed_ms",
        ),
        # 사이클 158 Q3 stagger — 가장 무거운 task = 즉시 발화 (0초)
        initial_delay_secs=0,
        # cycle363 — 영업일 슬롯 게이트 + 행 수 하한 자가 치유 + 마커 없음(부트스트랩) skip.
        immediate_skip_if_fresh_since_trading_slot=True,
        immediate_force_run_check=_full_universe_below_immediate_floor,
        immediate_skip_if_marker_absent=True,
    )


async def stock_master_daily_load_task_loop(scheduler: Any, *, wait_time) -> None:
    """사이클 122/134 — 매일 저녁 고정 시각(cycle283, 종전 16시 정각 → cycle273f) KIS 일봉 적재 task facade.

    시각 정본은 `scheduler.TIME_STOCK_MASTER_DAILY_LOAD` 하나다 — 이 facade 는 값을
    주입받기만 한다(리터럴·주석 모두 정본 이원화 금지).
    """
    from src.engine.scanner import _stock_master_daily_load_once
    from src.engine.stock_master_daily_metrics import (
        record_stock_master_daily_load,
        flush_stock_master_daily_load_collector,
    )
    from src.engine.task_loop_helper import run_periodic_task_loop

    await run_periodic_task_loop(
        scheduler=scheduler,
        task_label="stock_master_daily_load",
        wait_time=wait_time,  # 정본 = scheduler.TIME_STOCK_MASTER_DAILY_LOAD
        once_callable=_stock_master_daily_load_once,
        record_fn=record_stock_master_daily_load,
        flush_fn=flush_stock_master_daily_load_collector,
        summary_log_format=(
            "[stock_master_daily_load_summary] total=%d fetched=%d upserted_rows=%d "
            "skipped_fresh=%d failed=%d elapsed_ms=%d mode=%s"
        ),
        summary_keys=(
            "total", "fetched", "upserted_rows",
            "skipped_fresh", "failed", "elapsed_ms", "mode",
        ),
        # 사이클 159 stagger = full_universe 처리 완료 직후 진입
        initial_delay_secs=240,
        # 사이클 263 신선도 게이트 투입 — 사이클 193 이 daily_load 만 게이트를 뺀 근거였던
        # "max_bas_dd 멱등" 이 실제로는 깨져 있었다: 아침 immediate(07:56)가 장 전 KIS 로부터
        # 오늘 날짜 껍데기 봉을 받아 먼저 써서 max_bas_dd == today 를 만들고, 그날 저녁 정기
        # 실행을 전 종목 skip 시킨다(09-03/09-04 실측). 게이트는 그 껍데기 생성 주체를 없애
        # 사이클 193 의 전제를 되살린다. 마커는 once() 성공 시에만 갱신되므로 저녁 실패·
        # 프로세스 다운이면 다음 아침 immediate 가 자동 부활한다(사이클 106 안전망 보존).
        # cycle363 — 시간(20h) 게이트를 영업일 슬롯 게이트로 바꿨다. 20h 시계는 주말·연휴를
        # 「낡았다」고 세어 월요일 아침마다 자기 치유를 발화시켰고, 그 실행이 실제로 쓴 값은
        # 목요일(또는 그 전) KRX 값이었다(09-21 실측). 슬롯 = `wait_time`(20:30) — 마커가
        # 직전 영업일 20:30 뒤면 fresh 로 skip 한다.
        immediate_skip_if_fresh_since_trading_slot=True,
    )


async def stock_master_basics_refresh_task_loop(scheduler: Any, *, wait_time) -> None:
    """사이클 126 — 매일 16:10 KST KIS CTPF1002R 매스 보강 task facade."""
    from src.engine.scanner import _stock_master_basics_refresh_once
    from src.engine.stock_master_basics_metrics import (
        record_stock_master_basics_refresh,
        flush_stock_master_basics_refresh_collector,
    )
    from src.engine.task_loop_helper import run_periodic_task_loop

    await run_periodic_task_loop(
        scheduler=scheduler,
        task_label="stock_master_basics_refresh",
        wait_time=wait_time,  # 16:10 KST
        once_callable=_stock_master_basics_refresh_once,
        record_fn=record_stock_master_basics_refresh,
        flush_fn=flush_stock_master_basics_refresh_collector,
        summary_log_format=(
            "[stock_master_basics_refresh_summary] total=%d updated=%d "
            "skipped=%d failed=%d elapsed_ms=%d"
        ),
        summary_keys=(
            "total", "updated", "skipped", "failed", "elapsed_ms",
        ),
        # 사이클 159 stagger = full_universe 처리 시간 정합
        initial_delay_secs=480,
        # basics 는 멱등 없이 매 run 전량 재작성 (17분 burst).
        # cycle363 — 시간(20h) 게이트를 영업일 슬롯 게이트로 바꿨다(daily_load 와 같은 이유
        # — 월요일·연휴 뒤 아침 자기 치유가 실제로는 목요일 이전 값을 덮어썼다).
        immediate_skip_if_fresh_since_trading_slot=True,
        # cycle363 F-4 — full_universe 만 도는 월요일 아침의 자가 치유(사용자 승인).
        immediate_force_run_check=_stock_master_basics_kis_keys_missing_above_threshold,
        immediate_force_run_reason="kis_keys_missing",
    )


async def stock_master_master_load_task_loop(scheduler: Any, *, wait_time) -> None:
    """사이클 129 — 매일 16:30 KST KIS 종목 마스터 파일 적재 task facade."""
    from src.engine.scanner import _stock_master_master_load_once
    from src.engine.stock_master_master_metrics import (
        record_stock_master_master_load,
        flush_stock_master_master_load_collector,
    )
    from src.engine.task_loop_helper import run_periodic_task_loop, IMMEDIATE_FRESH_SKIP_HOURS

    await run_periodic_task_loop(
        scheduler=scheduler,
        task_label="stock_master_master_load",
        wait_time=wait_time,  # 16:30 KST
        once_callable=_stock_master_master_load_once,
        record_fn=record_stock_master_master_load,
        flush_fn=flush_stock_master_master_load_collector,
        summary_log_format=(
            "[stock_master_master_load_summary] kospi=%d kosdaq=%d "
            "total=%d updated=%d failed=%d elapsed_ms=%d"
        ),
        summary_keys=(
            "kospi_count", "kosdaq_count", "total",
            "updated", "failed", "elapsed_ms",
        ),
        # 사이클 159 stagger = basics 완료 30초 후 진입 (HTTP/2 race 마진)
        initial_delay_secs=720,
        # 사이클 193 신선도 게이트 — master 는 멱등 없이 매 run 전량 재작성 (4분 burst).
        immediate_skip_if_fresh_hours=IMMEDIATE_FRESH_SKIP_HOURS,
    )


async def stock_master_financial_load_task_loop(scheduler: Any, *, wait_time) -> None:
    """사이클 C3 — 매일 16:40 KST 퀀트 재무 (마법공식/F-Score-7) 주1회 적재 task facade.

    관찰 전용 (Phase 1) — 매매 로직 diff 0. 주1회 신선도 게이트(168h) + master 후 stagger.
    """
    from src.engine.scanner import _stock_master_financial_load_once
    from src.engine.task_loop_helper import run_periodic_task_loop

    def _noop_record(_summary: dict) -> None:
        return None

    def _noop_flush() -> None:
        return None

    await run_periodic_task_loop(
        scheduler=scheduler,
        task_label="stock_master_financial_load",
        wait_time=wait_time,  # 16:40 KST
        once_callable=_stock_master_financial_load_once,
        record_fn=_noop_record,
        flush_fn=_noop_flush,
        summary_log_format=(
            "[stock_master_financial_load_task_summary] total=%d updated=%d "
            "skipped=%d failed=%d"
        ),
        summary_keys=("total", "updated", "skipped", "failed"),
        # master(720초 지연) 완료 후 stagger 마진 (사이클 159 패턴)
        initial_delay_secs=900,
        # 주1회 신선도 게이트 (7일 = 168시간, 사이클 193 답습)
        immediate_skip_if_fresh_hours=168,
    )


async def evening_funnel_capture_task_loop(scheduler: Any, *, wait_time) -> None:
    """사이클 171 — 매일 저녁 잠정 funnel 캡처 task facade.

    cycle364 S1 — `wait_time=TIME_EVENING_FUNNEL_CAPTURE`(21:00, 20:30 일봉 적재 뒤·
    21:30 정산 전). 본체는 leaf `funnel_capture.evening_capture_once`(다음 거래일
    미리보기 A1, `prepare(as_of=)`). `_evening_funnel_capture_once` 는 그 leaf 로 가는
    3줄 위임이다(§4.6). start() 직후 +600초 즉시 1회는 S1 임시 레거시 재준비를 탄다
    (`decision=legacy_reprepare`) — S2 가 이 분기를 없앤다.
    """
    from src.engine.task_loop_helper import run_periodic_task_loop

    # metrics collector 미사용 (funnel = DB 직접 영속) → no-op record/flush
    def _noop_record(_summary: dict) -> None:
        return None

    def _noop_flush() -> None:
        return None

    await run_periodic_task_loop(
        scheduler=scheduler,
        task_label="evening_funnel_capture",
        wait_time=wait_time,  # cycle364 — 21:00 KST(TIME_EVENING_FUNNEL_CAPTURE)
        once_callable=scheduler._evening_funnel_capture_once,
        record_fn=_noop_record,
        flush_fn=_noop_flush,
        summary_log_format=(
            "[evening_funnel_capture_summary] prepared=%d saved=%d"
        ),
        summary_keys=("prepared", "saved"),
        # basics(16:10) 완료 후 진입 = HTTP/2 race 차단 마진 (사이클 159 답습)
        initial_delay_secs=600,
    )


async def stock_master_daily_purge_task_loop(scheduler: Any, *, wait_time) -> None:
    """사이클 150 — 매일 16:15 KST stock_master_daily retention cron task facade.

    보유/익일청산 protected_tickers 절대 보호 (사이클 32 R4). 사이클 192 루프 배치 purge.
    """
    from datetime import timedelta as _timedelta
    from src.db._kst import today_kst
    from src.db.stock_master_daily import (
        DAILY_RETENTION_DAYS,
        purge_old_rows,
    )
    from src.engine.task_loop_helper import run_periodic_task_loop

    async def _purge_once() -> dict:
        """retention cutoff + 보유/익일청산 protected_tickers 합집합 (사이클 32 R4)."""
        protected: set[str] = set()
        try:
            for strategy in scheduler.registry.all():
                state = strategy.state
                for ticker in (state.positions or {}).keys():
                    if ticker:
                        protected.add(ticker)
        except Exception:
            logger.exception("[stock_master_daily_purge] protected tickers 영역 수집 실패 graceful")

        try:
            for entry in (scheduler._pending_next_day_clear or set()):
                # entry 는 (ticker, strategy_id) 튜플 영속
                if isinstance(entry, tuple) and entry:
                    ticker = entry[0]
                else:
                    ticker = entry
                if ticker:
                    protected.add(str(ticker))
        except Exception:
            logger.exception("[stock_master_daily_purge] pending_next_day_clear 영역 수집 실패 graceful")

        cutoff = today_kst() - _timedelta(days=DAILY_RETENTION_DAYS)
        summary = await purge_old_rows(cutoff, protected_tickers=protected or None)
        summary["cutoff"] = cutoff.isoformat()
        return summary

    def _noop_record(summary: dict) -> None:  # noqa: ARG001
        return None

    def _noop_flush() -> None:
        return None

    await run_periodic_task_loop(
        scheduler=scheduler,
        task_label="stock_master_daily_purge",
        wait_time=wait_time,  # 16:15 KST
        once_callable=_purge_once,
        record_fn=_noop_record,
        flush_fn=_noop_flush,
        summary_log_format=(
            "[stock_master_daily_purge_summary] deleted=%d protected=%d "
            "elapsed_ms=%d cutoff=%s"
        ),
        summary_keys=("deleted", "protected_count", "elapsed_ms", "cutoff"),
        # 사이클 193 신선도 게이트 미적용 — purge 는 사이클 192 후 저렴 (게이트 대상 = basics/master 만).
    )
