"""QuoteSessionHealthMonitor — 보조 시세 세션 헬스 추적 + 자동 비활성 (사이클 9, 2026-05-18).

배경:
- KIS Open API 공지(2026-05-18): 무한 연결/종료 반복, 검증 없는 무한 등록/해제
  반복 시 IP/앱키 일시 차단 예정.
- 보조 시세 세션 1개가 토큰 발급 실패 또는 5xx 응답을 지속 받으면 K stale watcher
  가 분당 800 unsubscribe/subscribe 요청을 KIS 에 던지는 위험. 자체 헬스 모니터로
  5회 연속 실패 또는 5분 50% 실패율 감지 시 해당 보조를 자동 비활성 → 트래픽 차단.

설계:
- 모듈 싱글톤 ``health_monitor`` (단일 워커 가정 — 멀티 워커 금지 `CLAUDE.md`)
- 메인 라벨 "main" 은 자동 비활성 대상 제외 (안전 가드)
- ``record_success(label)`` / ``record_failure(label, reason)`` 양대 API
- 임계 분기: (a) 5회 연속 실패 (b) 5분 sliding window total ≥ 10 + failure_rate ≥ 0.5
- 비활성 시: (1) `kis_quote_accounts.update_account(active=False)` (2) 풀에서 세션 제거
  (3) `system_logs` `[quote_session_disabled]` 영구 1행
- DB update 실패 graceful — 메모리는 비활성 그대로, WARNING 로그
- 두 번째 비활성 호출 idempotent (`_disabled_labels` set 가드)

호출자:
- ``src/api/base.py::_request_via_quote_pool`` 가 응답/실패 분기에서 호출:
  - 성공 (rt_cd=="0") + actual_label != "main" → ``record_success(label)``
  - 5xx HTTPStatusError → ``record_failure(label, reason=f"http_{status}")``
  - 보조 매니저 발급 실패 → ``record_failure(label, reason="token_issue_fail")``
  - KIS 비즈니스 거부(rt_cd!=0) → 기록 안 함 (헬스와 무관)

운영자 가이드:
- 자동 비활성된 보조 세션은 ``kis_quote_accounts.active=false`` 로 영속.
- Settings UI 보조 계좌 카드에서 active=true 토글하면 다음 ``_boot()`` (다음날 07:50)
  부터 풀에 재참여.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 임계값 상수
# ---------------------------------------------------------------------------
MAX_CONSECUTIVE_FAILURES = 5    # 연속 실패 N 회 초과 시 자동 비활성
WINDOW_SECS = 300               # 5분 sliding window
MAX_FAILURE_RATE = 0.5          # window 실패율 임계 (50%)
MIN_CALLS_FOR_RATE = 10         # 비율 평가 최소 호출 수

_KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 외부 의존 — monkeypatch 가능한 wrapper 함수 (테스트 격리)
# ---------------------------------------------------------------------------
async def _db_get_by_label(label: str):
    """DB ``kis_quote_accounts.get_by_label(label)`` wrapper (monkeypatch point)."""
    from src.db import kis_quote_accounts as kqa
    return await kqa.get_by_label(label)


async def _db_update_account(account_id: str, *, active: bool) -> Optional[dict]:
    """DB ``kis_quote_accounts.update_account(id, active=...)`` wrapper."""
    from src.db import kis_quote_accounts as kqa
    return await kqa.update_account(account_id, active=active)


async def _pool_disable_quote_session(label: str) -> None:
    """``kis_ws_pool.disable_quote_session(label)`` wrapper (lazy import — 순환 차단)."""
    from src.realtime.websocket_pool import kis_ws_pool
    await kis_ws_pool.disable_quote_session(label)


async def _write_system_log(level: str, message: str) -> None:
    """``system_logs.write_log(level, message)`` wrapper. 예외 swallow."""
    try:
        from src.db.system_logs import write_log
        await write_log(level, message)
    except Exception:
        logger.debug("[quote_session_health] system_logs.write_log 실패", exc_info=True)


# ---------------------------------------------------------------------------
# QuoteSessionHealthMonitor
# ---------------------------------------------------------------------------
class QuoteSessionHealthMonitor:
    """보조 시세 세션 헬스 모니터 — 자동 비활성 의사결정 + 트래픽 차단."""

    def __init__(self) -> None:
        # 라벨별 연속 실패 누적. 성공 1회로 0 reset.
        self._consecutive_failures: dict[str, int] = {}
        # 마지막 실패 시각 (운영 가시성 — 현재 미사용, 추후 모니터링 UI 노출 예정)
        self._last_failure_at: dict[str, datetime] = {}
        # 5분 sliding window 카운터
        self._window_total: dict[str, int] = {}
        self._window_failures: dict[str, int] = {}
        self._window_start: dict[str, datetime] = {}
        # 이미 비활성 처리된 라벨 — idempotent 가드
        self._disabled_labels: set[str] = set()
        # 동시 record 호출 보호 (싱글톤 + 단일 워커지만 record_failure 안에서
        # await DB 호출 도중 다른 record 가 들어오는 race 방지)
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        """전체 상태 초기화 — 테스트 격리용."""
        self._consecutive_failures.clear()
        self._last_failure_at.clear()
        self._window_total.clear()
        self._window_failures.clear()
        self._window_start.clear()
        self._disabled_labels.clear()

    async def record_success(self, label: str) -> None:
        """라벨의 호출 성공 1회 — consecutive 0 reset + window total +=1 + 비율 재평가.

        성공 호출에서도 sliding window 평가를 수행한다 — 성공이 누적되어 window
        총 호출 수가 ``MIN_CALLS_FOR_RATE`` 에 도달한 시점에 누적된 과거 실패율
        평가가 발화해야 정확한 임계 분기가 일어난다.
        """
        if label == "main":
            # 메인은 자동 비활성 대상 아님 — 추적 자체 skip (성능 + 가드)
            return
        async with self._lock:
            self._consecutive_failures[label] = 0
            self._bump_window(label, failure=False)
            # 비율 임계는 success 시점에도 평가 (consecutive 임계는 record_failure 전용)
            await self._evaluate_rate_only(label, reason="window_eval_on_success")

    async def record_failure(self, label: str, reason: str) -> None:
        """라벨의 호출 실패 1회 — consecutive +=1 + window total/failures +=1."""
        if label == "main":
            # 메인은 자동 비활성 절대 금지 — 추적 자체 skip
            return
        async with self._lock:
            now = datetime.now(_KST)
            self._consecutive_failures[label] = (
                self._consecutive_failures.get(label, 0) + 1
            )
            self._last_failure_at[label] = now
            self._bump_window(label, failure=True)
            await self._evaluate(label, reason)

    def _bump_window(self, label: str, *, failure: bool) -> None:
        """sliding window 카운터 갱신. window 만료 시 reset 후 1 부터 카운트."""
        now = datetime.now(_KST)
        start = self._window_start.get(label)
        if start is None or (now - start) > timedelta(seconds=WINDOW_SECS):
            # window 만료 또는 첫 호출 — reset
            self._window_start[label] = now
            self._window_total[label] = 1
            self._window_failures[label] = 1 if failure else 0
            return
        self._window_total[label] = self._window_total.get(label, 0) + 1
        if failure:
            self._window_failures[label] = self._window_failures.get(label, 0) + 1

    async def _evaluate(self, label: str, reason: str) -> None:
        """임계 평가 — consecutive ≥ MAX 또는 window rate 초과 시 자동 비활성."""
        if label in self._disabled_labels:
            # idempotent — 이미 비활성된 라벨은 재평가 안 함
            return

        consecutive = self._consecutive_failures.get(label, 0)
        total = self._window_total.get(label, 0)
        failures = self._window_failures.get(label, 0)
        rate = failures / total if total > 0 else 0.0

        trigger_reason: Optional[str] = None
        if consecutive >= MAX_CONSECUTIVE_FAILURES:
            trigger_reason = (
                f"consecutive_failures={consecutive} threshold={MAX_CONSECUTIVE_FAILURES} "
                f"last_reason={reason}"
            )
        elif total >= MIN_CALLS_FOR_RATE and rate >= MAX_FAILURE_RATE:
            trigger_reason = (
                f"window_failure_rate={rate:.2f} threshold={MAX_FAILURE_RATE} "
                f"window_total={total} window_failures={failures} last_reason={reason}"
            )

        if trigger_reason is None:
            return

        await self._auto_disable(label, trigger_reason)

    async def _evaluate_rate_only(self, label: str, reason: str) -> None:
        """비율 임계만 평가 — record_success 에서 호출.

        성공 호출에서는 consecutive 임계가 의미 없지만(직전 호출에서 0 reset 됨),
        sliding window 누적 실패율 평가는 진행해야 늦은 비활성 결정 race 차단.
        """
        if label in self._disabled_labels:
            return

        total = self._window_total.get(label, 0)
        failures = self._window_failures.get(label, 0)
        if total < MIN_CALLS_FOR_RATE:
            return

        rate = failures / total if total > 0 else 0.0
        if rate < MAX_FAILURE_RATE:
            return

        await self._auto_disable(
            label,
            f"window_failure_rate={rate:.2f} threshold={MAX_FAILURE_RATE} "
            f"window_total={total} window_failures={failures} last_reason={reason}",
        )

    async def _auto_disable(self, label: str, reason: str) -> None:
        """자동 비활성 — DB + 풀 + 영구 로그. DB 실패 graceful."""
        self._disabled_labels.add(label)

        # (1) 영구 로그 우선 — 이후 DB/풀 정리가 실패해도 trace 보존
        await _write_system_log(
            "ERROR",
            f"[quote_session_disabled] label={label} reason={reason}",
        )

        # (2) 풀에서 세션 제거 — DB 보다 먼저 (실시간 트래픽 차단 최우선)
        try:
            await _pool_disable_quote_session(label)
        except Exception:
            logger.exception("[quote_session_health] pool 제거 실패: label=%s", label)

        # (3) DB active=false — 실패 graceful
        try:
            account = await _db_get_by_label(label)
            if account is None:
                logger.warning(
                    "[quote_session_health] kis_quote_accounts 라벨 없음: %s", label,
                )
                await _write_system_log(
                    "WARNING",
                    f"[quote_session_health_db_miss] label={label}",
                )
                return
            await _db_update_account(account.id, active=False)
        except Exception as e:
            logger.exception(
                "[quote_session_health] DB update 실패 (메모리만 비활성): label=%s", label,
            )
            await _write_system_log(
                "WARNING",
                f"[quote_session_health_db_fail] label={label} error={type(e).__name__}",
            )


# ---------------------------------------------------------------------------
# 모듈 싱글톤
# ---------------------------------------------------------------------------
health_monitor = QuoteSessionHealthMonitor()
