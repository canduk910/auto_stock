"""사이클 67 = stale_manager.py 1,099L sub-module 분해 (Q1=A facade) — K stale watcher 본체.

사이클 63 Phase 2-A3 (2026-06-05): scheduler.py L2442~L2789 K stale watcher 핵심 2 함수 이주.
사이클 66 (2026-06-06): cap=10 결함 시정 영속 (Q3 옵션 A WARNING 로그).
사이클 67 (2026-06-06): sub-module 분해 후 stale_diagnostics 직접 import (Q2 옵션 P1).

절대 깨지 말 것:
- WebSocket 4 중 안전망 행위 보존 (F1 + scan_loop + K stale watcher + resubscribe)
- 사이클 29 005935 사고 패턴 영구 차단 (HIGH 종목 cap 밖 잘림 0건)
- Q4=B 영속 (사이클 60 답습하지 않는 유일 영역) — `emit_stale_session_detail` 직접 호출
- 사이클 66 시정 본체 영속 (priority 분리 *먼저* + cap 적용 *나중*)
- try/except 4중 가드 영속 (사이클 66 Q2)
- `sys.modules.get("src.engine.scheduler")` 패턴 영속 (D-1 AST 가드 + freezegun patch 호환)
- 함수 본체 변경 0 (라인 단위 동일, self.* → scheduler.* 치환만)

의존성 방향 (옵션 A 단방향, G-7 AST 가드 영속):
    stale_watcher_core → stale_diagnostics (단방향, Q2 옵션 P1 모듈-레벨 정적 import)
    stale_watcher_core → 외부 모듈 (scheduler / scanner / websocket_pool)
    역방향 (diagnostics/session_recovery/universe_guard → watcher_core) 금지
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

# 사이클 67 Q2 옵션 P1 — cross-module 모듈-레벨 정적 import
# (Q4=B 영속, hot path 360 회/일 — 가독성 + AST G-7 가드 검증 명시성)
from src.engine.stale_diagnostics import (
    MAX_STALE_RETRIES,
    STALE_FORCE_RETRY_AFTER_SECS,
    STALE_FORCE_RETRY_HOURLY_CAP,
    STALE_FRESHNESS_SECS,
    SUBSCRIBE_GRACE_SECS,  # 사이클 135 — 구독 ACK grace period (180s, Q3=A 영속)
    emit_stale_session_detail,
)

logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 영속 (caplog 호환)

# 사이클 216 — LOW-only 재구독 throttle (동일 종목 중복 재발사 차단).
# 반드시 < 300s(`resubscribe_stale_priority` 5분 주기 자체) — 자기막힘/cycle215 원복 방지.
RESUBSCRIBE_THROTTLE_SECS = 3 * STALE_FRESHNESS_SECS  # = 180


# ── 사이클 74 옵션 C 조건부 — [stale_watcher] 5분 aggregation collector ─────────────

_stale_watcher_collector: list[dict] = []


def record_stale_watcher_check(stats: dict) -> None:
    """5분 윈도우 누적 (사이클 74 옵션 C 조건부 aggregation).

    stats keys: subscribed / stale / force_reregistered / skipped_giveup /
                force_retried / cap_blocked
    stale_count > 0 인 경우 `emit_stale_session_detail` 를 통한 individual
    `[stale_watcher_detail]` 는 별도 보존 (사이클 73 영속, 변경 0).
    """
    _stale_watcher_collector.append(stats)


def flush_stale_watcher_collector() -> None:
    """5분 윈도우 종료 시 `[stale_watcher_summary]` 1행 emit + collector 초기화.

    scheduler disconnect / cancel 직전 마지막 flush 1회 호출 의무 (Q5 옵션 A).
    collector 비어 있으면 emit skip (no-op).
    """
    if not _stale_watcher_collector:
        return
    checks = len(_stale_watcher_collector)
    stale_total = sum(s.get("stale", 0) for s in _stale_watcher_collector)
    retried = sum(s.get("force_reregistered", 0) for s in _stale_watcher_collector)
    cap_blocked = sum(s.get("cap_blocked", 0) for s in _stale_watcher_collector)
    force_retried = sum(s.get("force_retried", 0) for s in _stale_watcher_collector)
    logger.info(
        "[stale_watcher_summary] checks=%d stale_total=%d retried=%d cap_blocked=%d force_retried=%d",
        checks, stale_total, retried, cap_blocked, force_retried,
    )
    _stale_watcher_collector.clear()


# ── A3 2 함수 — K stale watcher 핵심 (사이클 63 Phase 2-A3, 2026-06-05) ────────────

async def check_and_resubscribe_stale(scheduler: Any) -> None:
    """K stale watcher 본체 — 120s 주기 (사이클 17/28/29-R1/R3 영속).

    사이클 63 Phase 2-A3 (2026-06-05): scheduler.py L2442~L2663 그대로 이주.
    self.* → scheduler.* 치환만. 행위 변경 0건 (refactor).

    Q4=B (사이클 60 답습하지 않는 유일 영역):
    본체 마지막 `self._emit_stale_session_detail(stale_tickers, now)` 호출 →
    `emit_stale_session_detail(scheduler, stale_tickers, now)` 직접 호출 (1 hop 단축).
    scheduler.py L2678 wrapper 자체는 외부 호환 보존 (삭제 안 함).

    Q2 RECOMMEND — `try/except` 4 중 가드 그대로 보존:
    - `registry.all()` / `s.state.positions.keys()` / `_pending_next_day_clear` 4 중
    - `getattr(scheduler, "registry", None)` 폴백 도입 금지 (silent 실패 위험)

    사이클 29-R3 우선순위 분리 (메인 편중 73% → 5% 해소) 영속:
    - positions / _pending_next_day_clear → HIGH+bypass_limit=True (메인 절대 보장)
    - 그 외 후보 → LOW+bypass_limit=False (보조 라운드로빈 분산)

    사이클 29-R1 force_retry (영구 stale 무한 skip 결함 대응) 영속:
    - 1~5회: 즉시 unsubscribe + subscribe (KIS 정상 신규 등록 패턴)
    - 6회 초과: 5분 cooldown + 시간당 12회 cap (LMS / 앱키 정지 위험 차단)
    """
    import sys as _sys

    # 사이클 61 패턴 답습 — D-1 AST 가드 + D-2 sys.modules.get 출현 수 가드.
    # datetime 접근은 scheduler 모듈 네임스페이스 우선 참조 (freezegun patch 호환).
    # kis_ws_pool 은 src.realtime.websocket_pool 모듈 직접 참조 (테스트 patch 호환):
    #   `patch("src.realtime.websocket_pool.kis_ws_pool")` 패치 작동 보장.
    _sched_mod = _sys.modules.get("src.engine.scheduler")
    if _sched_mod is not None and hasattr(_sched_mod, "datetime"):
        _dt_mod = _sched_mod.datetime
    else:
        from datetime import datetime as _dt_mod  # type: ignore[assignment]

    # kis_ws_pool — websocket_pool 모듈에서 직접 접근 (테스트 patch 경로 호환)
    _wsp_mod = _sys.modules.get("src.realtime.websocket_pool")
    if _wsp_mod is not None:
        kis_ws_pool = _wsp_mod.kis_ws_pool
    else:
        from src.realtime.websocket_pool import kis_ws_pool  # type: ignore[assignment]

    from src.engine.scanner import KST_TZ as _KST_TZ, TICK_TR_ID, ticker_last_tick

    # 사이클 13-E (2026-05-18): 메인 단독 → 풀 전체로 확장
    subscribed = kis_ws_pool.get_subscribed_tickers()
    if not subscribed:
        return

    now = _dt_mod.now(_KST_TZ)
    threshold = timedelta(seconds=STALE_FRESHNESS_SECS)
    min_dt = _dt_mod.min.replace(tzinfo=_KST_TZ)

    # 사이클 135 (2026-06-15) — 구독 ACK grace period (180s).
    # 사용자 결정 Q1=A + Q2=180s + Q3=A 자문 정합 + Q4=A HIGH 일관 grace.
    # domain-expert 자문 산출물 _workspace/domain_consult/cycle135_websocket_grace_period.md
    #
    # 가드 동작:
    #   - 첫 시세 입수 후 (`ticker_last_tick[t]` 존재) → 기존 60s 영속 (사이클 29 005935 보호, G-GRACE-7)
    #   - 첫 시세 입수 *전* (`ticker_last_tick[t]` 부재) + ACK 시점 미확인 → 기존 60s 영속 (race 보호, G-GRACE-6)
    #   - 첫 시세 입수 *전* + ACK 시점 확인 + grace 이내 → stale 판정 skip
    #   - 첫 시세 입수 *전* + ACK 시점 확인 + grace 초과 → stale 판정 정상 발화
    grace = timedelta(seconds=SUBSCRIBE_GRACE_SECS)
    # 사이클 135 ack_map 영역 영구 영속 — dict 영역 영구 영속만 유효 영속 (MagicMock 등 spec 부재 안전 영속)
    _ack_map_raw = getattr(kis_ws_pool, "_subscribed_at", None)
    ack_map = _ack_map_raw if isinstance(_ack_map_raw, dict) else {}

    def _is_within_grace(t: str) -> bool:
        """grace 영역 영구 영속 판정 영구 영속.

        첫 시세 입수 후 영역 (`ticker_last_tick[t]` 존재) = False (grace 미적용, 기존 60s 영속).
        첫 시세 입수 *전* + ACK 미확인 = False (race 보호, 기존 60s 영속).
        첫 시세 입수 *전* + ACK 확인 + grace 이내 = True (stale 판정 skip).
        """
        if t in ticker_last_tick:
            return False  # 첫 시세 입수 후 = grace 미적용 (G-GRACE-7 영속)
        ack_at = ack_map.get((TICK_TR_ID, t))
        if not isinstance(ack_at, datetime):
            return False  # ACK 미확인 = race 보호, 기존 60s 영속 (G-GRACE-6)
        try:
            return (now - ack_at) <= grace  # grace 이내 = stale 판정 skip
        except (TypeError, ValueError):
            # mock/race 안전 폴백 영역 영구 영속 = 기존 60s 영속 (사이클 29 005935 보호 영속)
            return False

    # 사이클 149 (2026-06-16) — VI/거래정지 stale 회피 hook.
    # 의제 5 (자문 채택) = VI 활성 ∪ 거래정지 ∪ 종목상태 이상 ticker stale 판정 지연.
    # `_is_within_grace` 패턴 답습 (사이클 135) + try/except 안전 폴백.
    # domain-expert 자문 `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md`.
    try:
        from src.engine.market_operation_monitor import is_ticker_stale_excluded as _is_market_op_excluded
    except Exception:
        def _is_market_op_excluded(t: str) -> bool:  # type: ignore[no-redef]
            return False

    _excluded_for_log: list[str] = []

    def _market_op_skip(t: str) -> bool:
        """stale 회피 = True 시 stale 판정 지연 + 로그 emit."""
        try:
            if _is_market_op_excluded(t):
                _excluded_for_log.append(t)
                return True
        except Exception:
            return False
        return False

    # 사이클 162 (2026-06-17) — 동시호가 시간대 stale 회피 hook (의제 E).
    # 사용자 보고 사고: 6/17 15:21:48 KST stale_watcher = subscribed=10 fresh=0 stale=10
    # ratio=0% → 5분 주기 재구독 시도 반복 = KIS LMS chain 위험.
    # 근본 원인 = 동시호가 시간대 (15:20~15:30) 체결 부재 = 정상 → stale 오판.
    # domain-expert 자문 산출물 `_workspace/domain_consult/cycle162_pending_persist_and_call_auction.md`.
    # 사이클 135 grace + 사이클 149 VI 패턴 답습 = stale 종목 *전체* skip + WARNING 1행.
    try:
        from src.engine.session import session_tracker as _session_tracker
        _is_call_auction = _session_tracker.is_call_auction_now(now)
    except Exception:
        _is_call_auction = False

    if _is_call_auction:
        # 동시호가 시간대 → stale 판정 *전체* 지연 (사이클 38 명문화 영속 — stale 판정 지연만)
        logger.warning(
            "[stale_skip_call_auction] subscribed=%d — 동시호가 시간대 stale 회피 "
            "(체결 부재 정상 영역)",
            len(subscribed),
        )
        # 누적 retry 카운터 보존 (fresh 회복 케이스 분기 미진입 = 정상 영역 영구 영속)
        return

    stale_tickers = sorted(
        t for t in subscribed
        if (now - ticker_last_tick.get(t, min_dt)) > threshold
        and not _is_within_grace(t)
        and not _market_op_skip(t)
    )

    if _excluded_for_log:
        logger.info(
            "[stale_skip_market_op] count=%d tickers=%s — VI/거래정지 stale 회피",
            len(_excluded_for_log), _excluded_for_log[:20],
        )

    if not stale_tickers:
        # 모두 fresh — 누적 retry 카운터 리셋 (회복 케이스)
        scheduler._stale_retry_count.clear()
        # 사이클 28 — _stale_last_resubscribe_at 동행 clear (G5 cleanup 동행).
        # getattr 폴백으로 사전 init 누락 인스턴스(테스트 `__new__` 호출 등) 보호.
        if hasattr(scheduler, "_stale_last_resubscribe_at"):
            scheduler._stale_last_resubscribe_at.clear()
        return

    force_reregistered = 0
    skipped_giveup = 0
    force_retry_count = 0       # 사이클 29 — 영구 stale 시간 기반 강제 재시도 카운트
    force_retry_cap_blocked = 0  # 사이클 29 — 시간당 cap 초과 차단 카운트

    # 사이클 29-R3 (2026-05-21) — 우선순위 분리 (메인 편중 73% 해소)
    # 사이클 25-B `_resubscribe_stale_priority` 와 동일 패턴:
    #   - positions / _pending_next_day_clear → HIGH+bypass_limit=True (메인 절대 보장)
    #   - 그 외 후보 → LOW+bypass_limit=False (보조 라운드로빈 분산)
    # Q2 RECOMMEND — try/except 4 중 가드 그대로 보존
    high_tickers: set[str] = set()
    try:
        for s in scheduler.registry.all():
            try:
                high_tickers.update(s.state.positions.keys())
            except Exception:
                pass
    except Exception:
        # registry 미주입 인스턴스(테스트 __new__) 보호 — 모두 LOW 로 처리
        pass
    try:
        high_tickers.update(t for (t, _sid) in scheduler._pending_next_day_clear)
    except Exception:
        pass

    for ticker in stale_tickers:
        retry = scheduler._stale_retry_count.get(ticker, 0) + 1
        scheduler._stale_retry_count[ticker] = retry

        # 사이클 29-R3 — 종목별 priority 결정 (HIGH/LOW 분리)
        if ticker in high_tickers:
            sub_priority = "HIGH"
            sub_bypass = True
        else:
            sub_priority = "LOW"
            sub_bypass = False

        if retry > MAX_STALE_RETRIES:
            # 사이클 29 (2026-05-21) — 영구 stale 무한 skip 결함 대응.
            # 종목 단위 5분 cooldown + 시간당 12회 cap 으로 강제 재시도 발화.
            # 13:21:41 마지막 시도 후 8분 영구 잔류 결함 (보유 005935 손절 평가 지연) 차단.
            last_at = None
            if hasattr(scheduler, "_stale_last_resubscribe_at"):
                last_at = scheduler._stale_last_resubscribe_at.get(ticker)

            if last_at is not None:
                age_secs = (_dt_mod.now(_KST_TZ) - last_at).total_seconds()
                if age_secs < STALE_FORCE_RETRY_AFTER_SECS:
                    # cooldown 미경과 — 기존 skip 동작 보존 (LMS 위험 차단, 카운터는 누적)
                    skipped_giveup += 1
                    continue
            else:
                # `_stale_last_resubscribe_at` 부재 = 영구 stale 의심 첫 진입.
                # age=infinity 로 간주 → 즉시 1회 시도.
                age_secs = float("inf")

            # 시간당 cap 가드 — 60분 슬라이딩 윈도우
            if not hasattr(scheduler, "_stale_force_retry_history"):
                scheduler._stale_force_retry_history = {}
            history = scheduler._stale_force_retry_history.setdefault(ticker, [])
            hour_ago = _dt_mod.now(_KST_TZ) - timedelta(hours=1)
            # 만료 항목 evict (60분 이전)
            history[:] = [t for t in history if t > hour_ago]

            if len(history) >= STALE_FORCE_RETRY_HOURLY_CAP:
                # 시간당 cap 초과 — LMS / 앱키 정지 위험 차단
                force_retry_cap_blocked += 1
                logger.warning(
                    "[stale_force_retry_cap] ticker=%s attempts_in_hour=%d "
                    "— LMS 위험 차단 skip",
                    ticker, len(history),
                )
                # 사이클 72 hotfix A4: write_log 제거 — logger.warning → _DbLogHandler 위임 단일 INSERT
                skipped_giveup += 1
                continue

            # 강제 재시도 발화
            # 사이클 29-R3 — sub_priority/sub_bypass 분기 적용 (HIGH/LOW)
            age_disp = f"{age_secs:.0f}s" if age_secs != float("inf") else "inf"
            try:
                await kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)
                await asyncio.sleep(0.05)
                await kis_ws_pool.subscribe(
                    TICK_TR_ID, ticker,
                    priority=sub_priority, bypass_limit=sub_bypass,
                )
                # 핵심: 카운터 0 리셋 (영구 stale 의심 해제 → 신규 사이클 시작).
                # 다음 사이클부터 다시 1~5회 정상 분기로 자연 회복.
                scheduler._stale_retry_count[ticker] = 0
                # 시각 갱신 + history 등록
                if hasattr(scheduler, "_stale_last_resubscribe_at"):
                    scheduler._stale_last_resubscribe_at[ticker] = _dt_mod.now(_KST_TZ)
                history.append(_dt_mod.now(_KST_TZ))
                force_retry_count += 1

                logger.info(
                    "[stale_force_retry] ticker=%s retries=%d last_resub_age=%s "
                    "— 강제 재시도 + 카운터 리셋",
                    ticker, retry, age_disp,
                )
                # 사이클 72 hotfix A2: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT
            except Exception:
                logger.exception("[stale_force_retry] 강제 재시도 실패: %s", ticker)

            await asyncio.sleep(0.05)  # Rate Limit 보호
            continue

        # 1~5회 — 첫 stale 즉시 강제 재등록 (KIS 정상 "신규 등록" 패턴, 재SEND 0건)
        # KIS 공식 답변: "기등록한 사항을 재등록하지 않도록" (LMS + 앱정보 이용중지 위험)
        # 사이클 29-R3 — sub_priority/sub_bypass 분기 적용 (사이클 25-B 패턴 K stale watcher 확장)
        try:
            await kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)
            await asyncio.sleep(0.05)
            await kis_ws_pool.subscribe(
                TICK_TR_ID, ticker,
                priority=sub_priority, bypass_limit=sub_bypass,
            )
            force_reregistered += 1
            # 사이클 28 — 강제 재등록 직후 시각 갱신 (진단 로그 출처).
            # 사전 init 누락 인스턴스(테스트 `__new__` 호출 등) 보호.
            if hasattr(scheduler, "_stale_last_resubscribe_at"):
                scheduler._stale_last_resubscribe_at[ticker] = _dt_mod.now(_KST_TZ)
        except Exception:
            logger.exception("[stale_watcher] 강제 재등록 실패: %s", ticker)

        await asyncio.sleep(0.05)  # Rate Limit 보호

    # 사이클 74 옵션 C 조건부 aggregation: [stale_watcher] 정상 흐름 INFO → 5분 collector 흡수
    record_stale_watcher_check({
        "subscribed": len(subscribed),
        "stale": len(stale_tickers),
        "force_reregistered": force_reregistered,
        "skipped_giveup": skipped_giveup,
        "force_retried": force_retry_count,
        "cap_blocked": force_retry_cap_blocked,
    })
    # 사이클 72 hotfix A3: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT
    # 사이클 74: 직접 logger.info("[stale_watcher] subscribed=...") 제거 → collector 흡수
    # stale_count > 0 시 individual [stale_watcher_detail] 보존 (사이클 73 영속, 하단 분기)

    # 사이클 28 — [stale_watcher_detail] 세션별 분포 + 종목 cap 20 (별도 행, G1 호환)
    # Q4=B (사이클 60 답습하지 않는 유일 영역) — 직접 호출 (1 hop 단축, wrapper 우회)
    emit_stale_session_detail(scheduler, stale_tickers, now)


async def resubscribe_stale_priority(scheduler: Any, cap: int = 10) -> list[str]:
    """`_scan_loop` 5분 stale 우선순위 재구독 (사이클 25-B 우선순위 분리 영속).

    사이클 63 Phase 2-A3 (2026-06-05): scheduler.py L2690~L2789 그대로 이주.
    self.* → scheduler.* 치환만. 행위 변경 0건 (refactor).

    사이클 66 (2026-06-06) — cap=10 결함 시정 (카드 #5 HIGH):
    - 사이클 63 K-2 결함 confirm → 사이클 66 K-2 시정 confirm (Q6-4 의미 전환).
    - `targets = stale_tickers[: cap]` 결함 패턴 (priority 분리 *전* cap 적용) 영구 제거.
    - HIGH (positions ∪ next_day_clear) 절대 보장 + LOW 잔여 cap 채움.
    - HIGH > cap 시 cap 위반 허용 + WARNING 로그 (Q3 옵션 A 운영 가시화).
    - try/except 4중 가드 통일 — `_check_and_resubscribe_stale` L820-833 본체 패턴 답습 (Q2).
    - 사이클 29 005935 사고 패턴 (HIGH 종목 cap 밖 잘림 8분 영구 잔류 + LMS chain) 영구 차단.

    사이클 25-B (2026-05-20) — positions/next_day_clear 는 HIGH, 그 외 후보는 LOW:
    - 기존: 모든 stale 에 HIGH+bypass_limit=True → VB/LTV 후보 stale → 메인 승격
      → 2026-05-20 14:58 메인 sub=11 fresh=0 stale=11 silent inactive 사고
    - 변경: positions/next_day_clear = HIGH (보유·익일청산 보장 절대 유지)
            그 외 후보 = LOW (보조 분산, 사이클 24 자동 회복과 시너지)

    Returns:
        재구독한 ticker 리스트 (호출 카운트 + 회귀 검증용)
    """
    import sys as _sys

    # 사이클 61 패턴 답습 — D-1 AST 가드 + D-2 sys.modules.get 출현 수 가드.
    # datetime 접근은 scheduler 모듈 네임스페이스 우선 참조 (freezegun patch 호환).
    # kis_ws_pool 은 src.realtime.websocket_pool 모듈 직접 참조 (테스트 patch 호환):
    #   `patch("src.realtime.websocket_pool.kis_ws_pool")` 패치 작동 보장.
    _sched_mod = _sys.modules.get("src.engine.scheduler")
    if _sched_mod is not None and hasattr(_sched_mod, "datetime"):
        _dt_mod = _sched_mod.datetime
    else:
        from datetime import datetime as _dt_mod  # type: ignore[assignment]

    # kis_ws_pool — websocket_pool 모듈에서 직접 접근 (테스트 patch 경로 호환)
    _wsp_mod = _sys.modules.get("src.realtime.websocket_pool")
    if _wsp_mod is not None:
        kis_ws_pool = _wsp_mod.kis_ws_pool
    else:
        from src.realtime.websocket_pool import kis_ws_pool  # type: ignore[assignment]

    from src.engine.scanner import KST_TZ as _KST_TZ, TICK_TR_ID, ticker_last_tick

    now = _dt_mod.now(_KST_TZ)
    threshold = timedelta(seconds=STALE_FRESHNESS_SECS)
    min_dt = _dt_mod.min.replace(tzinfo=_KST_TZ)

    # 사이클 149 (2026-06-16) — VI/거래정지 stale 회피 hook (`check_and_resubscribe_stale` 답습).
    try:
        from src.engine.market_operation_monitor import is_ticker_stale_excluded as _is_market_op_excluded
    except Exception:
        def _is_market_op_excluded(t: str) -> bool:  # type: ignore[no-redef]
            return False

    def _market_op_skip(t: str) -> bool:
        try:
            return bool(_is_market_op_excluded(t))
        except Exception:
            return False

    # sorted 로 결정적 순서 보장 — cap 적용 시 동일 입력에 동일 출력
    stale_tickers = sorted(
        t for t, last in ticker_last_tick.items()
        if (now - last if isinstance(last, datetime) else now - min_dt) > threshold
        and not _market_op_skip(t)
    )

    if not stale_tickers:
        return []

    # 사이클 25-B + 사이클 66 (2026-06-06) — HIGH 보장 대상 집합 (try/except 4중 가드 통일 Q2)
    # Q6-4 의미 전환: 사이클 63 K-2 결함 confirm → 사이클 66 K-2 시정 confirm.
    # 사이클 29 005935 사고 패턴 (HIGH 종목 cap 밖 잘림 8분 영구 잔류 + LMS chain) 영구 차단.
    high_tickers: set[str] = set()
    try:
        for s in scheduler.registry.all():
            try:
                high_tickers.update(s.state.positions.keys())
            except Exception:
                pass
    except Exception:
        # registry 미주입 인스턴스(테스트 __new__) 보호 — 모두 LOW 로 처리
        pass
    try:
        high_tickers.update(t for (t, _sid) in scheduler._pending_next_day_clear)
    except Exception:
        pass

    # Q1 시정: priority 분리 *먼저*, cap 적용 *나중* (HIGH 절대 우선)
    high_targets = [t for t in stale_tickers if t in high_tickers]
    low_targets = [t for t in stale_tickers if t not in high_tickers]

    # 사이클 216 보강 A — 동시호가 LOW-scoped skip (HIGH 는 면제, cycle162 전체
    # early-return 과 달리 LOW 후보만 비운다. 09:00 갭개장 손절 대비 HIGH 유지).
    try:
        from src.engine.session import session_tracker as _session_tracker
        _is_call_auction = _session_tracker.is_call_auction_now(now)
    except Exception:
        _is_call_auction = False
    if _is_call_auction and low_targets:
        logger.warning(
            "[stale_skip_call_auction_priority] low=%d skip — 동시호가 LOW 재구독 회피 (HIGH 유지)",
            len(low_targets),
        )
        low_targets = []

    # 사이클 216 보강 B — LOW-only per-ticker throttle (HIGH 는 완전 면제,
    # 300s 케이던스 자체가 LMS-safe + 손절 직결). throttle → cap 순서 (계약).
    _last_resub = getattr(scheduler, "_stale_last_resubscribe_at", {}) or {}
    low_targets = [
        t for t in low_targets
        if not (
            isinstance(_last_resub.get(t), datetime)
            and (now - _last_resub[t]).total_seconds() < RESUBSCRIBE_THROTTLE_SECS
        )
    ]

    # Q3 시정: HIGH > cap 시 cap 위반 허용 + WARNING 로그 (운영 가시화)
    if len(high_targets) > cap:
        logger.warning(
            "[stale_priority_resubscribe_cap_exceeded] high_count=%d cap=%d "
            "tickers=%s — HIGH 종목 cap 위반 허용 (보유/익일청산 절대 보장)",
            len(high_targets), cap, high_targets,
        )

    targets = high_targets + low_targets[: max(0, cap - len(high_targets))]
    resubscribed: list[str] = []

    for ticker in targets:
        # positions/next_day_clear → HIGH (메인 절대 보장, bypass 한도 무시)
        # 그 외 후보 → LOW (보조 세션 분산 우선, 사이클 25-B)
        if ticker in high_tickers:
            sub_priority = "HIGH"
            sub_bypass = True
        else:
            sub_priority = "LOW"
            sub_bypass = False
        try:
            await kis_ws_pool.unsubscribe_in_pool(TICK_TR_ID, ticker)
            await asyncio.sleep(0.05)
            await kis_ws_pool.subscribe(
                TICK_TR_ID, ticker,
                priority=sub_priority, bypass_limit=sub_bypass,
            )
            resubscribed.append(ticker)
            # 사이클 28 — 강제 재구독 시각 갱신 (진단 로그 출처).
            # 사전 init 누락 인스턴스(테스트 `__new__` 호출 등) 보호.
            if hasattr(scheduler, "_stale_last_resubscribe_at"):
                scheduler._stale_last_resubscribe_at[ticker] = _dt_mod.now(_KST_TZ)
        except Exception:
            logger.exception("[stale_priority_resubscribe] 재구독 실패: %s", ticker)
            continue
        await asyncio.sleep(0.05)  # Rate Limit 보호

    logger.info(
        "[stale_priority_resubscribe] count=%d tickers=%s",
        len(resubscribed), resubscribed,
    )
    # 사이클 72 hotfix A5: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT

    return resubscribed
