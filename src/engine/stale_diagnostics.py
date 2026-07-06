"""사이클 67 = stale_manager.py 1,099L sub-module 분해 (Q1=A facade) — 진단 read-only.

사이클 60 Phase 2-A1 (2026-06-04): scheduler.py 의 stale 진단 5 함수 + 4 상수 이전.
사이클 67 (2026-06-06): stale_manager.py 1,099L → 4 sub-module 분해 (카드 #14 MEDIUM).

절대 깨지 말 것:
- 함수 본체 변경 0 (라인 단위 동일, self.* → scheduler.* 치환만)
- 시그너처 변경 0 (emit_stale_session_detail(scheduler, ...) Q4=B 영속)
- 상수 값 변경 0 (SoT: 이 파일이 4 상수의 단일 정의처)
- Q1 옵션 A 단방향: 이 파일은 stale_watcher_core / stale_session_recovery / stale_universe_guard 를 import 금지

의존성 방향 (옵션 A 단방향, G-7 AST 가드 영속):
    stale_watcher_core → stale_diagnostics (단방향)
    stale_diagnostics  → 외부 모듈만 (scheduler / scanner / websocket_pool)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 영속 (caplog 호환)

# ── 상수 (SoT: 이 파일이 4 상수의 단일 정의처) ──────────────────────────────────
# 사이클 17 보강 (2026-05-19) — KIS 공식 답변 반영
MAX_STALE_RETRIES = 5                       # 연속 N회 초과 stale 시 skip (영구 stale 의심). 6회 이상 → 다음 _scan_loop 위임.

# 사이클 29 (2026-05-21) — 영구 stale 무한 skip → 시간 기반 강제 재시도 전환
# 사이클 102 (2026-06-11) Q73=B — 임계 상향 (LMS chain 안전 마진 증가)
STALE_FORCE_RETRY_AFTER_SECS = 600          # 영구 stale 의심 종목 최소 재시도 간격 (10분, 사이클 29 5분 → 사이클 102 10분)
STALE_FORCE_RETRY_HOURLY_CAP = 6            # 시간당 동일 종목 최대 재시도 횟수 (사이클 29 12회 → 사이클 102 6회, LMS / 앱키 정지 위험 차단)

# 사이클 61 Phase 2-A2 (2026-06-05) — STALE_FRESHNESS_SECS 이전
# 사이클 9 관련: STALE_FRESHNESS_SECS 는 scheduler 잔류 함수도 사용
STALE_FRESHNESS_SECS = 60                   # 이 시간 내 tick 없으면 stale 판정 (F1 의 VERIFY_FRESHNESS_SECS 동일)

# 사이클 135 (2026-06-15) — WebSocket 구독 ACK grace period 신규 상수.
# 사용자 결정 Q3=A 영구 영속 + domain-expert 자문 의제 1 채택 영구 영속:
#   _workspace/domain_consult/cycle135_websocket_grace_period.md
#   180s = 3.0 × STALE_FRESHNESS_SECS = P95 안전 마진 정합 영구 영속
#     (KOSPI 대형주 25s / 중형주 55s / KOSDAQ 중형주 75s / 소형주 150s / 10시 이후 480s)
# 자문 의제 5 영속: D+1 / 1주 / 2주 운영 실측 후 사이클 136+ 재조정 의제 영역.
#
# 적용 영역 영구 영속:
#   stale_watcher_core.check_and_resubscribe_stale + resubscribe_stale_priority
#   구독 ACK 후 grace 이내 + ticker_last_tick 부재 = stale 판정 skip
#   첫 시세 입수 후 (ticker_last_tick 존재) = 기존 60s 영속 (사이클 29 005935 보호, G-GRACE-7)
SUBSCRIBE_GRACE_SECS = 180                  # 구독 ACK 후 grace period (KIS LMS chain 안전 마진 영속)

# CCNL_CACHE_TTL_SECONDS 는 refresh_stale_ccnl_cache 내부 상수 (로컬 변수) — 별도 모듈 전역 상수 불필요
# stale_manager.py facade 에서 re-export 하지 않는 내부 상수


# ── A1 5 함수 (사이클 60 Phase 2-A1 이주) ────────────────────────────────────────
# 모두 scheduler 를 첫 인자. self.* → scheduler.* 치환만. 행위 변경 0건.

def build_session_subscription_view(scheduler: Any) -> list[dict]:
    """세션별 분포 dict 리스트 (label / subscribed_count / fresh / stale / capacity_used / stale_tickers).

    - ``stale_tickers`` 는 ``(ticker, retries, last_resub_hhmmss_or_'-')`` 튜플 리스트
      (입력 ``ticker_last_tick`` 기준 정렬, cap 적용은 호출자 책임)
    - 헬퍼 자체는 cap 적용 안 함 — caller (`_emit_stale_session_detail` / `_report_tick_coverage`)
      가 G3 cap 20 적용
    - 풀 헬퍼 ``get_subscriptions_by_session`` + ``_main._subscriptions`` 길이 활용

    L2810 본체를 그대로 이주. self.* → scheduler.* 치환만.
    """
    from datetime import datetime as _dt
    from src.engine.scanner import KST_TZ as _KST_TZ, ticker_last_tick
    from src.realtime.websocket import MAX_SUBSCRIPTIONS as _MAX_SUB
    from src.realtime.websocket_pool import kis_ws_pool

    # 시세 채널 TR_ID 집합 — H0UNCNT0(통합 deprecated) + H0STCNT0(KRX) + H0NXCNT0(NXT).
    # 사이클 26 시간대별 분리 이후 동적이므로 set 으로 한 번에 매칭.
    _TICK_TR_IDS = frozenset({"H0UNCNT0", "H0STCNT0", "H0NXCNT0"})

    groups = kis_ws_pool.get_subscriptions_by_session()
    if not groups:
        return []

    now = _dt.now(_KST_TZ)
    fresh_threshold = timedelta(seconds=STALE_FRESHNESS_SECS)

    # 세션별 capacity (시세 채널만 카운트, 체결통보/MKOP 제외). 보조 세션은 인덱스 → 객체 매핑.
    sessions_view: list[dict] = []
    label_order = ["main"]
    # unknown 라벨 (race 대응) 도 포함
    if "unknown" in groups and "unknown" not in label_order:
        label_order.append("unknown")
    # groups 에 있는데 label_order 누락 케이스 보강
    for lbl in groups:
        if lbl not in label_order:
            label_order.append(lbl)

    for label in label_order:
        tickers = groups.get(label, set())
        if not tickers and label not in groups:
            # detail 출력에서 빈 세션은 호출자가 필터링
            continue

        # capacity 계산
        ws_obj = None
        if label == "main":
            ws_obj = kis_ws_pool._main
        else:
            ws_obj = next(
                (q for q in kis_ws_pool._quotes if getattr(q, "_label", None) == label),
                None,
            )

        if ws_obj is not None:
            cap_used = sum(
                1 for tr_id, _tk in getattr(ws_obj, "_subscriptions", set())
                if tr_id in _TICK_TR_IDS
            )
        else:
            cap_used = len(tickers)

        # fresh / stale 분리
        stale_entries: list[tuple[str, int, str]] = []
        fresh_count = 0
        for t in sorted(tickers):
            last = ticker_last_tick.get(t)
            if last is not None and (now - last) <= fresh_threshold:
                fresh_count += 1
            else:
                # stale — 진단 행 출력 후보. getattr 폴백으로 사전 init 누락 인스턴스 보호.
                retry = getattr(scheduler, "_stale_retry_count", {}).get(t, 0)
                last_resub_dt = getattr(
                    scheduler, "_stale_last_resubscribe_at", {}
                ).get(t)
                if last_resub_dt is None:
                    last_resub_s = "-"
                else:
                    last_resub_s = last_resub_dt.strftime("%H:%M:%S")
                stale_entries.append((t, retry, last_resub_s))

        sub_count = len(tickers)
        stale_count = len(stale_entries)
        ratio = round(stale_count / sub_count, 2) if sub_count > 0 else 0.0

        sessions_view.append({
            "label": label,
            "subscribed_count": sub_count,
            "capacity_used": cap_used,
            "capacity_max": _MAX_SUB,
            "fresh": fresh_count,
            "stale": stale_count,
            "stale_ratio": ratio,
            "stale_tickers": stale_entries,
        })
    return sessions_view


def emit_stale_session_detail(
    scheduler: Any, stale_tickers: list[str], now: datetime
) -> None:
    """``[stale_watcher_detail]`` 세션별 분포 행 출력 (G1: 별도 prefix, G3: cap 적용).

    - stale_count==0 인 세션은 detail 행 생략 (로그 폭주 차단)
    - 종목 리스트는 ``_STALE_DETAIL_TICKER_CAP`` (=20) 까지, 초과는 ``...+N`` 표시
    - 본 함수 예외는 호출자(`_check_and_resubscribe_stale`) 흐름 보호 위해 흡수

    L2909 본체를 그대로 이주. self.* → scheduler.* 치환만.
    """
    from src.db.system_logs import write_log as _write_log

    try:
        view = build_session_subscription_view(scheduler)
    except Exception:
        logger.debug("[stale_watcher_detail] view 빌드 실패", exc_info=True)
        return

    cap = scheduler._STALE_DETAIL_TICKER_CAP
    for s in view:
        if s["stale"] == 0:
            continue
        entries = s["stale_tickers"]
        displayed = entries[:cap]
        overflow = max(0, len(entries) - cap)
        tickers_repr_parts = [
            f"({t},r={r},@{ts})" for (t, r, ts) in displayed
        ]
        if overflow > 0:
            tickers_repr_parts.append(f"...+{overflow}")
        tickers_repr = "[" + ", ".join(tickers_repr_parts) + "]"
        msg = (
            f"[stale_watcher_detail] session={s['label']} "
            f"sub={s['capacity_used']}/{s['capacity_max']} "
            f"fresh={s['fresh']} stale={s['stale']} "
            f"ratio={s['stale_ratio']:.2f} stale={tickers_repr}"
        )
        logger.info(msg)
        # 사이클 72 hotfix A6: asyncio.create_task(_write_log) 제거 — logger.info → _DbLogHandler 위임 단일 INSERT


async def refresh_stale_ccnl_cache(
    scheduler: Any, candidate_tickers: list[str], *, cap: int = 20,
) -> None:
    """사이클 37 (2026-05-21) — stale 종목의 KIS 실제 last_cntg_hour 갱신.

    UI 에서 `last_tick` (WS 수신) 과 `last_cntg_hour` (KIS 실제) 비교 → WS 구독 문제 진단 가능.

    조건:
    - `_stale_retry_count[ticker] >= 2` (1회 stale 은 일시적 — KIS 호출 과다 차단)
    - 캐시 TTL 5분 — 5분 이내 hit 시 재호출 skip
    - 사이클당 cap 20 (KIS Rate Limit 보호)
    - 보유 종목 우선순위 (cap 도달해도 보유는 반드시 처리)

    안전 가드:
    - KIS None / 예외 → 캐시 미저장 (다음 사이클 자연 재시도, graceful)
    - 종목 간 50ms sleep
    - 본체 예외는 호출자(`_scan_loop`) 가 흡수
    - R4 `_evaluate_universe_guard` 와 같은 사이클에서 동시 호출되어도 race 무해
      (캐시 + TTL 로 중복 호출 자동 차단)

    L3222 본체를 그대로 이주. self.* → scheduler.* 치환만.
    내부 `self._evict_expired_ccnl(now, ttl_secs=TTL_SECS)` 호출은
    `evict_expired_ccnl(scheduler, now, ttl_secs=TTL_SECS)` 모듈 함수 직접 호출로
    전환 (wrapper 우회 — 순환 import 차단).
    """
    from src.api.quotation import inquire_ccnl
    from src.engine.scanner import KST_TZ as _KST_TZ

    # 1차 필터 — stale r>=2 만 평가 + 캐시 TTL 5분 hit 차단
    TTL_SECS = 300
    now = datetime.now(_KST_TZ)

    # 사이클 45 (2026-05-22, refactor-review 카드 #5) — TTL 만료 항목 자동 evict.
    # 영업일 중 stale watcher 가 더 이상 평가 안 하는 종목 (회복/R4 제외) 의 캐시 영구
    # 잔존 메모리 누수 차단. `_reset_daily_state` 동행 clear 와 이중 안전망.
    try:
        evicted = evict_expired_ccnl(scheduler, now, ttl_secs=TTL_SECS)
        if evicted > 0:
            logger.debug("[ccnl_cache_evict] expired=%d remaining=%d",
                         evicted, len(scheduler._last_ccnl_cache))
    except Exception:
        logger.debug("[ccnl_cache_evict] 실패 — 다음 사이클 자연 재시도", exc_info=True)

    if not candidate_tickers:
        return
    eligible: list[str] = []
    for ticker in candidate_tickers:
        if scheduler._stale_retry_count.get(ticker, 0) < 2:
            continue
        cached = scheduler._last_ccnl_cache.get(ticker)
        if cached:
            age = (now - cached["fetched_at"]).total_seconds()
            if age < TTL_SECS:
                continue  # TTL 이내 hit
        eligible.append(ticker)

    if not eligible:
        return

    # 사이클 37 — 보유 종목 우선순위 (cap 도달해도 보유는 반드시 처리)
    try:
        held: set[str] = set()
        for s in scheduler.registry.all():
            try:
                held.update(s.state.positions.keys())
            except Exception:
                pass
    except Exception:
        held = set()

    # 보유 종목 먼저, 그 다음 후보 — cap 적용
    held_first = [t for t in eligible if t in held]
    others = [t for t in eligible if t not in held]
    targets = (held_first + others)[:cap]

    for ticker in targets:
        try:
            ccnl = await inquire_ccnl(ticker)
        except Exception:
            logger.debug(
                "[ccnl_cache] inquire_ccnl 예외 ticker=%s — 캐시 미스 (다음 사이클 재시도)",
                ticker, exc_info=True,
            )
            await asyncio.sleep(0.05)
            continue

        if ccnl is None:
            # 캐시 미저장 — 다음 사이클 자연 재시도
            await asyncio.sleep(0.05)
            continue

        scheduler._last_ccnl_cache[ticker] = {
            "fetched_at": datetime.now(_KST_TZ),
            "last_cntg_hour": str(ccnl.get("last_cntg_hour", "")),
            "today_volume": int(ccnl.get("today_volume", 0)),
        }
        await asyncio.sleep(0.05)


def evict_expired_ccnl(
    scheduler: Any, now: datetime, ttl_secs: float = 300
) -> int:
    """사이클 45 (2026-05-22, refactor-review 카드 #5) — `_last_ccnl_cache` TTL 만료 항목 자동 제거.

    사이클 37 `_refresh_stale_ccnl_cache` 의 TTL hit 판정만으로는 stale watcher 가
    더 이상 평가 안 하는 종목 (회복/R4 제외 등) 의 캐시가 영구 잔존 → 영업일 중 dict
    size 증가 메모리 누수. 본 헬퍼가 진입 시점에 일괄 evict.

    Args:
        scheduler: TradingScheduler 인스턴스.
        now: 현재 KST datetime (호출자가 단일 시각 보장 — race 차단).
        ttl_secs: TTL 만료 임계 (기본 300s = 5분, 사이클 37 정의 보존).

    Returns:
        제거된 항목 수.

    Note:
        본체 예외 graceful — `_refresh_stale_ccnl_cache` 호출자가 try/except 흡수.
        `_reset_daily_state` 동행 clear 와 이중 안전망.

    L3316 본체를 그대로 이주. self.* → scheduler.* 치환만.
    """
    cutoff = now - timedelta(seconds=ttl_secs)
    expired: list[str] = []
    for ticker, entry in list(scheduler._last_ccnl_cache.items()):
        fetched_at = entry.get("fetched_at")
        if fetched_at is None or fetched_at <= cutoff:
            expired.append(ticker)
    for ticker in expired:
        scheduler._last_ccnl_cache.pop(ticker, None)
    return len(expired)


def prune_force_retry_history(
    scheduler: Any, ticker: str, now: datetime, window_secs: float = 3600
) -> None:
    """사이클 45 (2026-05-22, refactor-review 카드 #5) — `_stale_force_retry_history` 빈 list 제거.

    사이클 29-R1 `_check_and_resubscribe_stale` 의 sliding window 60분 in-place evict
    는 정상 동작하나, 빈 list 가 dict 에 영구 잔존하는 메모리 누수가 있음. 본 헬퍼가
    해당 ticker history 를 sliding window 외 항목 제거 + 빈 list 시 dict 에서 자동 제거.

    Args:
        scheduler: TradingScheduler 인스턴스.
        ticker: 평가 대상 ticker.
        now: 현재 KST datetime.
        window_secs: sliding window 임계 (기본 3600s = 60분).

    Note:
        cap 비교 직전 호출 권장. 호출되지 않는 ticker 는 `_reset_daily_state` 가 일괄 clear.
        본체 예외 graceful — 호출자 분기 보호.

    L3345 본체를 그대로 이주. self.* → scheduler.* 치환만.
    """
    if ticker not in scheduler._stale_force_retry_history:
        return
    cutoff = now - timedelta(seconds=window_secs)
    history = scheduler._stale_force_retry_history[ticker]
    pruned = [ts for ts in history if ts > cutoff]
    if pruned:
        scheduler._stale_force_retry_history[ticker] = pruned
    else:
        # 빈 list — dict 에서 제거 (메모리 누수 차단)
        scheduler._stale_force_retry_history.pop(ticker, None)
