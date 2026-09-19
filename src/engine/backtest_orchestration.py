"""20:00 AI 자문 직후 Phase 3 백테스트 오케스트레이션 (enqueue + 폴 루프).

refactor 카드 B3 (2026-08-18) — `recommendation_engine.py` 에서 행위 보존 이관.
`generate_recommendations()` 는 recommendation_engine.py 에 잔류하며, 본 모듈의
`_enqueue_backtest_jobs` 를 module-level 재export 를 통해 그대로 호출한다
(`src/engine/CLAUDE.md` "refactor B3" 참조).

leaf 모듈 — recommendation_engine 을 import 하지 않는다 (순환 방지).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone, timedelta
from typing import Any

from src.db.parameter_recommendations import (
    list_recommendations_pending_backtest as _db_list_pending_backtest,
    update_backtest_summary as _db_update_backtest_summary,
)
from src.db.backtest_runs import (
    insert_run as _db_insert_run,
    list_by_date as _db_list_by_date,
    update_status as _db_update_status,
)
from src.models.backtest import compute_metric_diff
from src.services.exceptions import (
    BacktestNotSupportedError,
    ConfigError,
    ExternalAPIError,
)

# 운영 grep `[backtest_poll]`/`[backtest_enqueue]` 연속성 — __name__ 사용 금지
# (사이클 60 stale_manager 선례: getLogger(__name__) 로 바꾸면 운영 로그 config 에서
# 해당 prefix 가 누락될 위험).
logger = logging.getLogger("src.engine.recommendation_engine")

KST = timezone(timedelta(hours=9))

# ---------------------------------------------------------------------------
# Phase 3 백테스트 통합 상수
# ---------------------------------------------------------------------------
# (a) 외부 MCP YAML DSL 지원 전략 — submit 대상
_SUPPORTED_STRATEGIES: frozenset[str] = frozenset(
    {"momentum", "volatility_breakout", "donchian_swing"}
)
# (b) 폴백 전략 — 즉시 skipped 마킹.
# 🔴 이 넷은 외부 MCP 의 YAML DSL 로 표현되지 않는다. 그런데 그 DSL 을 해석하던 서버가
# 2026-08-18 철거됐으므로 지금은 (a) 3 전략도 함께 돌지 않는다 — 차이는 사유뿐이다.
# 로컬 실행기를 붙인다면 **이 넷이 우선**이다(진입·청산이 일봉 기반이라 재현이 성립한다).
# momentum·volatility_breakout 은 유니버스와 청산이 장중 경로라 일봉으로는 재현이 아니라
# 다른 전략을 만드는 일이 된다 — 그 판단은 `src/engine/strategies/CLAUDE.md` 가 정본이다.
_FALLBACK_STRATEGIES: frozenset[str] = frozenset(
    {"long_tail_volatility", "bull_flag_breakout", "vcp_breakout", "kojiro"}
)

# 폴 루프 주기 (테스트는 monkeypatch 로 0 으로 단축)
_BACKTEST_POLL_INTERVAL_SECS: int = 60
# 폴 루프 timeout — 24h 경과 시 미완료 row failed
_BACKTEST_POLL_TIMEOUT_HOURS: int = 24

# 중복 task 가드 — 동일 target_date 에 대해 폴 루프 task 중첩 차단
_backtest_poll_loop_running: set[date] = set()


# ---------------------------------------------------------------------------
# Phase 3 백테스트 통합 — enqueue + 폴 루프
# ---------------------------------------------------------------------------
def _get_backtest_engine():
    """싱글톤 lazy import. 테스트는 monkeypatch 로 치환."""
    from src.engine.backtest_engine import get_backtest_engine

    return get_backtest_engine()


def _spawn_backtest_poll_task(target_date: date) -> None:
    """폴 루프를 백그라운드 task 로 발화 — fire-and-forget.

    `asyncio.create_task` 가 안전한 이벤트 루프 안에서 호출되어야 하므로 호출자는
    이미 async 컨텍스트에 있어야 한다 (`_enqueue_backtest_jobs` 가 await 되는 동안).
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        logger.error("백테스트 폴 루프 발화 실패 — 이벤트 루프 없음")
        return

    task = loop.create_task(_backtest_poll_loop(target_date))
    # 좀비 task 차단 — 완료 시 자동 로깅
    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            logger.warning("[backtest_poll] cancelled: target_date=%s", target_date)
            return
        exc = t.exception()
        if exc:
            logger.error("[backtest_poll] task failure: target_date=%s err=%r", target_date, exc)

    task.add_done_callback(_on_done)


async def _enqueue_backtest_jobs(
    target_date: date,
    inserted_recs: list[dict],
) -> None:
    """활성 전략 × 2 kind 만큼 backtest_runs row INSERT + (a) 전략은 BacktestEngine submit.

    현재 활성 7 전략 × 2 = **14 row** 다(`_SUPPORTED_STRATEGIES` 3 + `_FALLBACK_STRATEGIES` 4).

    🔴 **외부 백테스트 서버는 2026-08-18 철거됐고 재구축하지 않기로 했다**(사용자 결정 2026-09-19).
    그래서 `KIS_MCP_ENABLED` 는 DB·env 둘 다 false 이고, 지금 14 row 는 전부 `skipped` 로 적재된다.
    적재를 걷어내지 않는 이유 = 외부 호출이 0건이라 비용이 사실상 없고, `params_snapshot` 이
    그날 어떤 파라미터로 돌고 있었는지의 기록이며, 나중에 로컬 실행기를 붙일 자리이기 때문이다.

    매 row 의 lifecycle:
        queued → (a) running (submit 성공) | (b) skipped (로컬 실행기 없음) | failed (외부 오류)

    호출 순서:
    1. 모든 row INSERT (status=queued, params_snapshot 영속화).
    2. (b) 폴백 전략은 status='skipped' + 사유 영속화.
    3. KIS_MCP_ENABLED=false 면 (a) 도 즉시 'skipped' + '비활성' 사유.
    4. (a) 전략은 BacktestEngine.run_for_strategy 호출 → mcp_job_id 받아 'running' 전이.
       - BacktestNotSupportedError → 'skipped' (방어적 — _SUPPORTED_STRATEGIES 갱신 누락 대비)
       - ExternalAPIError / 기타 → 'failed' + error_message
    5. (a) submit 성공이 1건 이상이면 폴 루프 task 발화 (fire-and-forget).

    자문 INSERT 와 race 무관 — 본 함수는 enqueue 만 책임.
    """
    engine = _get_backtest_engine()
    # 결함(d) 시정 (2026-07-24): 정적 engine.enabled(.env, 프로세스 시작 시 고정) 대신
    # is_enabled_async()(DB 우선 → .env fallback)로 Settings UI 토글을 재시작 없이 즉시 반영.
    enabled = await engine.is_enabled_async()

    pending_run_jobs: list[tuple[dict, str]] = []  # (run_row, kind) for (a) submit

    for rec in inserted_recs:
        strategy_id = rec.get("strategy_id")
        if not strategy_id:
            continue
        current_params = dict(rec.get("current_params") or {})
        recommended_params = dict(rec.get("recommended_params") or {})

        for kind, snapshot in (
            ("current", current_params),
            ("recommended", recommended_params),
        ):
            try:
                run_row = await _db_insert_run(
                    target_date=target_date,
                    strategy_id=strategy_id,
                    params_kind=kind,
                    params_snapshot=snapshot,
                )
            except Exception:
                logger.exception(
                    "backtest_runs INSERT 실패: strategy=%s kind=%s", strategy_id, kind,
                )
                continue
            if not run_row:
                # UNIQUE 충돌 — 동일 사이클 재진입. 기존 row 가 있으니 skip.
                logger.info(
                    "backtest_runs INSERT skip (중복): strategy=%s kind=%s",
                    strategy_id, kind,
                )
                continue

            run_id = run_row["id"]

            # (b) 폴백 전략 — 즉시 skipped
            if strategy_id in _FALLBACK_STRATEGIES:
                try:
                    await _db_update_status(
                        run_id, "skipped",
                        error_message="로컬 백테스트 실행기 없음 (외부 MCP 서버 철거 2026-08-18)",
                    )
                except Exception:
                    logger.exception(
                        "backtest_runs skipped 갱신 실패: run_id=%s", run_id,
                    )
                continue

            # KIS_MCP_ENABLED=false — (a) 도 즉시 skipped
            if not enabled:
                try:
                    await _db_update_status(
                        run_id, "skipped",
                        error_message="MCP 비활성 (KIS_MCP_ENABLED=false)",
                    )
                except Exception:
                    logger.exception(
                        "backtest_runs MCP 비활성 skipped 갱신 실패: run_id=%s", run_id,
                    )
                continue

            # (a) 전략 — submit 대기 큐에 push
            pending_run_jobs.append((run_row, kind))

    # (a) submit 단계
    submit_success = 0
    for run_row, kind in pending_run_jobs:
        strategy_id = run_row["strategy_id"]
        snapshot = dict(run_row.get("params_snapshot") or {})
        try:
            job_id = await engine.run_for_strategy(
                strategy_id, snapshot, days=90, kind=kind,
            )
        except BacktestNotSupportedError as e:
            try:
                await _db_update_status(
                    run_row["id"], "skipped",
                    error_message=f"BacktestNotSupportedError: {e!s}",
                )
            except Exception:
                logger.exception(
                    "backtest_runs NotSupported skipped 갱신 실패: run_id=%s",
                    run_row["id"],
                )
            continue
        except (ExternalAPIError, ConfigError) as e:
            try:
                await _db_update_status(
                    run_row["id"], "failed",
                    error_message=f"{type(e).__name__}: {e!s}",
                )
            except Exception:
                logger.exception(
                    "backtest_runs failed 갱신 실패: run_id=%s", run_row["id"],
                )
            continue
        except Exception as e:
            try:
                await _db_update_status(
                    run_row["id"], "failed",
                    error_message=f"{type(e).__name__}: {e!s}",
                )
            except Exception:
                logger.exception(
                    "backtest_runs unexpected failed 갱신 실패: run_id=%s",
                    run_row["id"],
                )
            continue

        # running 전이 + mcp_job_id 매핑
        try:
            await _db_update_status(
                run_row["id"], "running", mcp_job_id=job_id,
            )
            submit_success += 1
        except Exception:
            logger.exception(
                "backtest_runs running 갱신 실패: run_id=%s", run_row["id"],
            )

    if submit_success > 0:
        _spawn_backtest_poll_task(target_date)
        logger.info(
            "[backtest_enqueue] target=%s submitted=%d (a)전략=%d (b)전략=%d enabled=%s",
            target_date, submit_success,
            len([r for r in inserted_recs if r.get("strategy_id") in _SUPPORTED_STRATEGIES]),
            len([r for r in inserted_recs if r.get("strategy_id") in _FALLBACK_STRATEGIES]),
            enabled,
        )
    else:
        logger.info(
            "[backtest_enqueue] target=%s submit=0 — 폴 루프 발화 skip (enabled=%s)",
            target_date, enabled,
        )


async def _backtest_poll_loop(target_date: date) -> None:
    """백그라운드 폴 루프 — `_BACKTEST_POLL_INTERVAL_SECS` 주기로 미완료 row 폴링.

    종료 조건:
    - 모든 target_date 의 backtest_runs row 가 종료 상태(completed/failed/skipped) + 모든
      6 전략 backtest_summary 동봉 완료.
    - 시작 후 `_BACKTEST_POLL_TIMEOUT_HOURS` 경과 — 미완료 row failed 마킹 후 종료.

    중복 task 가드: `_backtest_poll_loop_running` set 에 target_date 있으면 즉시 종료.
    """
    if target_date in _backtest_poll_loop_running:
        logger.info(
            "[backtest_poll] 이미 진행중 — skip duplicate: target=%s", target_date,
        )
        return

    _backtest_poll_loop_running.add(target_date)
    started_at = datetime.now(KST)
    summarized_rec_ids: set[str] = set()

    try:
        engine = _get_backtest_engine()

        while True:
            # 1) 미완료 backtest_runs row 폴링
            try:
                rows = await _db_list_by_date(target_date)
            except Exception:
                logger.exception("[backtest_poll] list_by_date 실패")
                rows = []

            running_rows = [r for r in rows if r.get("status") == "running"]
            for row in running_rows:
                job_id = row.get("mcp_job_id")
                if not job_id:
                    # mcp_job_id 누락 — 비정상. failed 처리.
                    try:
                        await _db_update_status(
                            row["id"], "failed", error_message="mcp_job_id 누락",
                        )
                    except Exception:
                        logger.exception(
                            "[backtest_poll] running mcp_job_id 누락 처리 실패: %s",
                            row["id"],
                        )
                    continue
                try:
                    metrics = await engine.poll(job_id)
                except (ExternalAPIError, ConfigError) as e:
                    try:
                        await _db_update_status(
                            row["id"], "failed",
                            error_message=f"{type(e).__name__}: {e!s}",
                        )
                    except Exception:
                        logger.exception(
                            "[backtest_poll] failed 갱신 실패: %s", row["id"],
                        )
                    continue
                except Exception as e:
                    try:
                        await _db_update_status(
                            row["id"], "failed",
                            error_message=f"{type(e).__name__}: {e!s}",
                        )
                    except Exception:
                        logger.exception(
                            "[backtest_poll] unexpected failed 갱신 실패: %s",
                            row["id"],
                        )
                    continue

                if metrics is None:
                    # 여전히 running — 다음 iteration 대기
                    continue
                # completed
                try:
                    await _db_update_status(
                        row["id"], "completed",
                        metrics=metrics.model_dump(exclude_none=False),
                    )
                except Exception:
                    logger.exception(
                        "[backtest_poll] completed 갱신 실패: %s", row["id"],
                    )

            # 2) 종료 상태 row 기반 backtest_summary 동봉
            await _emit_pending_summaries(target_date, summarized_rec_ids)

            # 3) 종료 조건 확인
            try:
                rows_after = await _db_list_by_date(target_date)
            except Exception:
                logger.exception("[backtest_poll] list_by_date 재조회 실패")
                rows_after = rows

            terminal_states = {"completed", "failed", "skipped"}
            all_terminal = rows_after and all(
                r.get("status") in terminal_states for r in rows_after
            )

            try:
                pending_recs = await _db_list_pending_backtest(target_date)
            except Exception:
                logger.exception("[backtest_poll] list_pending_backtest 실패")
                pending_recs = []

            # 이미 summary 동봉 완료된 rec_id 는 제외 (fake/실DB 동작 차이 둘 다 안전).
            active_pending = [
                r for r in pending_recs if r.get("id") not in summarized_rec_ids
            ]

            if all_terminal and not active_pending:
                logger.info(
                    "[backtest_poll] 모든 row 종료 + summary 동봉 완료 — exit: target=%s",
                    target_date,
                )
                return

            # 4) timeout 확인
            elapsed = datetime.now(KST) - started_at
            if elapsed >= timedelta(hours=_BACKTEST_POLL_TIMEOUT_HOURS):
                # 미완료 running/queued row 를 failed 로 마킹
                still_pending = [
                    r for r in rows_after
                    if r.get("status") in ("running", "queued")
                ]
                for row in still_pending:
                    try:
                        await _db_update_status(
                            row["id"], "failed",
                            error_message=(
                                f"Timeout (>{_BACKTEST_POLL_TIMEOUT_HOURS}h)"
                            ),
                        )
                    except Exception:
                        logger.exception(
                            "[backtest_poll] timeout failed 갱신 실패: %s",
                            row["id"],
                        )
                # 마지막 한 번 더 summary 동봉 시도
                await _emit_pending_summaries(target_date, summarized_rec_ids)
                logger.warning(
                    "[backtest_poll] timeout — exit: target=%s pending=%d",
                    target_date, len(still_pending),
                )
                return

            # 5) 대기 후 재폴링
            await asyncio.sleep(_BACKTEST_POLL_INTERVAL_SECS)

    finally:
        _backtest_poll_loop_running.discard(target_date)


async def _emit_pending_summaries(
    target_date: date,
    summarized_rec_ids: set[str],
) -> None:
    """전략별 (current/recommended) 두 row 가 모두 종료 상태에 도달한 자문에 대해
    `parameter_recommendations.backtest_summary` 갱신.

    이미 갱신된 rec_id 는 ``summarized_rec_ids`` set 으로 중복 호출 차단.
    """
    try:
        rows = await _db_list_by_date(target_date)
    except Exception:
        logger.exception("[backtest_poll] emit_summaries list_by_date 실패")
        return
    try:
        pending_recs = await _db_list_pending_backtest(target_date)
    except Exception:
        logger.exception("[backtest_poll] emit_summaries list_pending 실패")
        return

    if not pending_recs:
        return

    # rows: run_id -> row dict
    # strategy_id -> {kind: row}
    by_strategy: dict[str, dict[str, dict]] = {}
    for row in rows:
        sid = row.get("strategy_id")
        kind = row.get("params_kind")
        if not sid or not kind:
            continue
        by_strategy.setdefault(sid, {})[kind] = row

    terminal_states = {"completed", "failed", "skipped"}

    for rec in pending_recs:
        rec_id = rec.get("id")
        if not rec_id or rec_id in summarized_rec_ids:
            continue
        rec_sid = rec.get("strategy_id")
        if not rec_sid:
            continue

        # 전체 6 전략 메트릭을 한꺼번에 동봉 — UI 가 자기 전략 + peer 비교 가능
        current_map: dict[str, Any] = {}
        recommended_map: dict[str, Any] = {}
        diff_map: dict[str, Any] = {}

        all_terminal_for_this_rec = True
        for sid, kinds in by_strategy.items():
            cur_row = kinds.get("current")
            rec_row = kinds.get("recommended")
            # 두 kind 가 모두 종료 상태여야 본 자문의 summary 진행
            if not cur_row or not rec_row:
                continue
            if (
                cur_row.get("status") not in terminal_states
                or rec_row.get("status") not in terminal_states
            ):
                # 자기 전략의 두 kind 가 아직 안 끝났으면 본 rec 의 summary 유예
                if sid == rec_sid:
                    all_terminal_for_this_rec = False
                continue
            # current
            if cur_row.get("status") == "completed" and cur_row.get("metrics"):
                current_map[sid] = dict(cur_row["metrics"])
            else:
                current_map[sid] = None
            # recommended
            if rec_row.get("status") == "completed" and rec_row.get("metrics"):
                recommended_map[sid] = dict(rec_row["metrics"])
            else:
                recommended_map[sid] = None
            # diff
            d = compute_metric_diff(current_map[sid], recommended_map[sid])
            diff_map[sid] = d if d else {}

        if not all_terminal_for_this_rec:
            continue

        # 자기 전략의 두 row 가 by_strategy 에 없으면 (예: INSERT 실패) skip
        own = by_strategy.get(rec_sid, {})
        if "current" not in own or "recommended" not in own:
            continue
        if (
            own["current"].get("status") not in terminal_states
            or own["recommended"].get("status") not in terminal_states
        ):
            continue

        summary = {
            "current": current_map,
            "recommended": recommended_map,
            "diff": diff_map,
        }
        try:
            await _db_update_backtest_summary(rec_id, summary)
            summarized_rec_ids.add(rec_id)
        except Exception:
            logger.exception(
                "[backtest_poll] backtest_summary 갱신 실패: rec_id=%s", rec_id,
            )
