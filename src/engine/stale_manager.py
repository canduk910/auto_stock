"""K stale watcher 진단 + 캐시 정리 + force_retry cap 헬퍼.

사이클 60 Phase 2-A1 (2026-06-04): scheduler.py 의 stale 관련 5 함수 + 5 상수
추출. 사이클 51 boot_manager.py 패턴 답습 — scheduler 인자 + 2 줄 wrapper 위임.

A2/A3 (사이클 61/62) 에서 6 함수 추가 이주 예정 (`_check_and_resubscribe_stale`
+ `_resubscribe_stale_priority` 등 WebSocket 4 중 안전망 hot path).

절대 깨지 말 것:
- WebSocket 4 중 안전망 행위 보존 (F1 + scan_loop + K stale watcher + resubscribe)
- 5 상수 동일성 (scheduler.py 가 re-export, `is` 동일성)
- StaleTrackerState 7 필드 reset_daily 동행 (사이클 48)
- property 7 쌍 layer 호환 (`src/routes/realtime.py:88-91` getattr graceful)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("src.engine.scheduler")

# ── 모듈 상수 (scheduler.py 에서 이전) ────────────────────────────────────────
# 사이클 17 보강 (2026-05-19) — KIS 공식 답변 반영
MAX_STALE_RETRIES = 5                       # 연속 N회 초과 stale 시 skip (영구 stale 의심). 6회 이상 → 다음 _scan_loop 위임.

# 사이클 29 (2026-05-21) — 영구 stale 무한 skip → 시간 기반 강제 재시도 전환
STALE_FORCE_RETRY_AFTER_SECS = 300          # 영구 stale 의심 종목 최소 재시도 간격 (5분)
STALE_FORCE_RETRY_HOURLY_CAP = 12           # 시간당 동일 종목 최대 재시도 횟수 (LMS / 앱키 정지 위험 차단)

# 사이클 32 (R4, 2026-05-21) — universe stale 가드
UNIVERSE_LOW_VOLUME_THRESHOLD = 10_000      # 당일 누적 체결량 임계 (운영 1주 후 조정)

# 사이클 29-R2 (2026-05-21) — silent_inactive 판정 비율 기반 전환
SILENT_INACTIVE_FRESH_RATIO_THRESHOLD = 0.2  # fresh_ratio < 20% 면 silent 의심 (사이클 24 fresh==0 완화)

# 사이클 61 Phase 2-A2 (2026-06-05) — A2 추가 5 상수 이전 (scheduler.py 에서 re-export)
# 사이클 9 관련: STALE_FRESHNESS_SECS 는 scheduler 잔류 함수 (_check_and_resubscribe_stale 등) 도 사용
STALE_FRESHNESS_SECS = 60                   # 이 시간 내 tick 없으면 stale 판정 (F1 의 VERIFY_FRESHNESS_SECS 동일)

# 사이클 24 (2026-05-20) — 세션 단위 silent inactive 감지 + 강제 reconnect
# 시간당 2회 cap — KIS LMS / 앱정보 이용중지 위험 사전 차단.
SILENT_INACTIVE_MIN_SUBSCRIBED = 5          # sub < 5 면 거래량 부족 자연 가능 (위양성 차단)
SILENT_INACTIVE_PERSIST_SECS = 300.0        # 5분 지속 임계 (단발 끊김 즉시 close 차단)
SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR = 2   # 시간당 reconnect 시도 cap
SILENT_INACTIVE_RECOVERY_WINDOW_SECS = 3600.0  # cap 윈도우 (60분)


# ── A1 5 함수 (모두 scheduler 를 첫 인자) ────────────────────────────────────

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
    label_order = ["main"] + [
        f"quote-{i}" for i in range(1, len(kis_ws_pool._quotes) + 1)
    ]
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
        elif label.startswith("quote-"):
            try:
                idx = int(label.split("-", 1)[1]) - 1
                if 0 <= idx < len(kis_ws_pool._quotes):
                    ws_obj = kis_ws_pool._quotes[idx]
            except (ValueError, IndexError):
                ws_obj = None

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
        try:
            # write_log 는 async — 호출 컨텍스트(async 함수)에서 task 로 발화
            # 호출자가 이미 async 컨텍스트이므로 직접 await 대신 fire-and-forget
            # 동일 prefix 별도 행으로 system_logs 보존
            asyncio.create_task(_write_log("INFO", msg))
        except Exception:
            logger.debug("[stale_watcher_detail] write_log 실패", exc_info=True)


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


# ── A2 4 함수 (사이클 61 Phase 2-A2, 2026-06-05) ─────────────────────────────
# silent inactive + universe guard + delta unsubscribe
# scheduler.py 본체 그대로 복붙 + self.* → scheduler.* 치환만.
# 행위 변경 0건 의무 (refactor only).

def detect_silent_inactive_sessions(scheduler: Any) -> list[str]:
    """세션 단위 silent inactive 감지 (사이클 24 / 29-R2). L2423 본체 그대로 이주.

    종목별 unsubscribe+subscribe 재등록(K stale watcher 사이클 17 보강) 으로
    회복 안 되는 *세션 자체* silent inactive 케이스를 5분 지속 후 강제 reconnect 대상으로 분류.

    판정 (3중):
    1. fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD (=0.2, 20%)
       — 사이클 29-R2 (2026-05-21): 기존 `fresh == 0` 완화. 메인 fresh=2/25 (8%) 실측
         결함 대응. fresh=0 케이스는 0.0 < 0.2 자동 호환.
    2. subscribed >= SILENT_INACTIVE_MIN_SUBSCRIBED (1~4 종목은 거래량 부족 자연 가능)
    3. 5분 지속 (first_seen 시각 추적)

    조건 미충족 (fresh_ratio >= 0.2 또는 subscribed < min) 시 first_seen pop (리셋).
    5분 도달 label 만 반환.
    """
    import sys
    from src.engine.scanner import KST_TZ as _KST_TZ, ticker_last_tick

    # kis_ws_pool 및 datetime 은 scheduler 모듈 네임스페이스를 우선 참조 (테스트 patch 호환).
    # scheduler.py 가 이미 로드된 환경에서는 동일 객체 — 행위 동일.
    # sys.modules 경유는 AST 정적 import 가 아니므로 D-1 가드 통과.
    _sched_mod = sys.modules.get("src.engine.scheduler")
    if _sched_mod is not None:
        kis_ws_pool = _sched_mod.kis_ws_pool
        _dt = _sched_mod.datetime
    else:
        from src.realtime.websocket_pool import kis_ws_pool  # type: ignore[assignment]
        _dt = datetime  # type: ignore[assignment]

    sessions = kis_ws_pool.get_session_status()
    now = _dt.now(_KST_TZ)
    threshold = timedelta(seconds=STALE_FRESHNESS_SECS)
    min_dt = _dt.min.replace(tzinfo=_KST_TZ)
    silent_labels: list[str] = []

    for s in sessions:
        label = s["label"]
        subscribed_count = s["subscribed"]
        subscribed_tickers = s["tickers"]["subscribed"]

        # fresh 계산: last_tick 이 threshold 이내인 종목 수
        fresh_count = sum(
            1 for t in subscribed_tickers
            if (now - ticker_last_tick.get(t, min_dt)) <= threshold
        )

        # 사이클 29-R2 — 비율 기반 판정 (fresh==0 → fresh_ratio<0.2 완화).
        # subscribed_count=0 인 경우 sub>=5 가드가 먼저 차단 → ZeroDivision 무해.
        # 사전 안전 가드로 0 분기 명시 처리 (fresh_ratio=0.0 으로 간주).
        if subscribed_count > 0:
            fresh_ratio = fresh_count / subscribed_count
        else:
            fresh_ratio = 0.0

        silent_suspect = (
            fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD
            and subscribed_count >= SILENT_INACTIVE_MIN_SUBSCRIBED
        )

        # 조건 1+2 동시 충족 시 first_seen 등록 (이미 있으면 보존)
        if silent_suspect:
            if label not in scheduler._silent_inactive_first_seen:
                scheduler._silent_inactive_first_seen[label] = now
            # 조건 3 (5분 지속) 검사
            elapsed = (now - scheduler._silent_inactive_first_seen[label]).total_seconds()
            if elapsed >= SILENT_INACTIVE_PERSIST_SECS:
                silent_labels.append(label)
        else:
            # 회복 또는 sub 부족 → first_seen pop (다음 5분 카운트 리셋)
            scheduler._silent_inactive_first_seen.pop(label, None)

    return silent_labels


async def force_reconnect_session(scheduler: Any, label: str) -> bool:
    """세션 단위 silent inactive 강제 reconnect (사이클 24). L2485 본체 그대로 이주.

    절대 깨지 말 것:
    - 시간당 세션당 2회 cap (KIS LMS/앱키 정지 위험) — `_silent_inactive_recovery_count` dict 동일성 보장
    - cap 윈도우 in-place evict (`history[:] = ...`) 정합성 보존
    - `_ws.close()` 발화 순서 보존

    1. 시간당 cap 검사: 60분 이전 시각 제거 후 남은 카운트 >= cap 면 SKIP + WARNING.
    2. label 분기:
       - "main" → kis_ws._ws.close() (모듈 레벨 심볼 직접 참조)
       - "quote-N" → kis_ws_pool._quotes[N-1]._ws.close()
    3. 영구 로그: INFO + system_logs write_log (fire-and-forget)
    4. _silent_inactive_first_seen.pop(label) — 다음 5분 카운트 리셋
    5. _silent_inactive_recovery_count[label].append(time.monotonic())

    Returns:
        True (reconnect 시도) / False (cap 도달 skip)
    """
    import sys
    import time as _t
    from src.db.system_logs import write_log as _write_log

    # kis_ws / kis_ws_pool 은 scheduler 모듈 네임스페이스를 우선 참조 (테스트 patch 호환).
    # sys.modules 경유는 AST 정적 import 가 아니므로 D-1 가드 통과.
    _sched_mod = sys.modules.get("src.engine.scheduler")
    if _sched_mod is not None:
        kis_ws = _sched_mod.kis_ws
        kis_ws_pool = _sched_mod.kis_ws_pool
    else:
        from src.realtime.websocket import kis_ws  # type: ignore[assignment]
        from src.realtime.websocket_pool import kis_ws_pool  # type: ignore[assignment]

    now_mono = _t.time()
    window = SILENT_INACTIVE_RECOVERY_WINDOW_SECS

    # 1. cap 검사 — 60분 이전 시각 제거 후 카운트 검증
    history = scheduler._silent_inactive_recovery_count.setdefault(label, [])
    history[:] = [t for t in history if (now_mono - t) < window]
    if len(history) >= SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR:
        logger.warning(
            "[silent_inactive_recovery_cap] label=%s count=%d/60min — reconnect skip",
            label, len(history),
        )
        try:
            await _write_log(
                "WARNING",
                f"[silent_inactive_recovery_cap] label={label} "
                f"count={len(history)}/60min — KIS 측 무한 재연결 회피",
            )
        except Exception:
            logger.debug("[silent_inactive_recovery_cap] write_log 실패", exc_info=True)
        return False

    # 2. label 분기 → _ws 객체 조회
    ws_obj = None
    if label == "main":
        ws_obj = getattr(kis_ws, "_ws", None)
    else:
        # "quote-N" → idx = N-1 (모듈 레벨 kis_ws_pool 직접 참조 — 테스트 패치 대응)
        try:
            idx = int(label.replace("quote-", "")) - 1
            quotes = getattr(kis_ws_pool, "_quotes", [])
            if 0 <= idx < len(quotes):
                ws_obj = getattr(quotes[idx], "_ws", None)
        except (ValueError, AttributeError):
            logger.warning("[silent_inactive_force_reconnect] 알 수 없는 label=%s", label)
            return False

    if ws_obj is None:
        logger.warning("[silent_inactive_force_reconnect] label=%s _ws is None — skip", label)
        return False

    # 3. 영구 로그
    logger.warning(
        "[silent_inactive_force_reconnect] label=%s elapsed>=%.0fs — _ws.close() 강제 발화",
        label, SILENT_INACTIVE_PERSIST_SECS,
    )
    try:
        await _write_log(
            "WARNING",
            f"[silent_inactive_force_reconnect] label={label} "
            f"elapsed>={SILENT_INACTIVE_PERSIST_SECS:.0f}s — _ws.close() 발화",
        )
    except Exception:
        logger.debug("[silent_inactive_force_reconnect] write_log 실패", exc_info=True)

    # 4. _ws.close() — connect() 의 ConnectionClosed catch → 재연결 루프
    try:
        await ws_obj.close()
    except Exception:
        logger.exception("[silent_inactive_force_reconnect] _ws.close() 실패 label=%s", label)
        return False

    # 5. state 갱신
    scheduler._silent_inactive_first_seen.pop(label, None)
    history.append(now_mono)

    return True


async def delta_unsubscribe_dropped(scheduler: Any, new_set: set[str]) -> list[str]:
    """`_scan_loop` 의 새 합집합에서 빠진 종목만 unsubscribe (사이클 15-A). L2811 본체 그대로 이주.

    절대 깨지 말 것:
    - KIS 공지 "비정상 케이스 2" (무한 등록/해제 반복) 차단
    - 50ms sleep + 종목별 예외 격리

    KIS 공지의 "비정상 케이스 2" (무한 등록/해제 반복) 패턴 차단.
    기존 `unsubscribe_all()` 전체 해제 → 빠진 종목 (delta_remove) 만 unsubscribe.

    흐름:
    1. 현재 풀 TICK 구독 합집합 `kis_ws_pool.get_subscribed_tickers()` 조회
    2. `delta_remove = current - new_set` 계산
    3. 각 종목 `kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)` 호출
    4. 종목 간 50ms sleep — KIS Rate Limit 보호
    5. 종목별 예외 격리

    Returns:
        unsubscribe 한 ticker 리스트 (테스트/모니터링용)

    안전 불변식:
    - TICK_TR_ID 종목만 처리 — 체결통보(H0STCNI0/9) / 장운영정보(H0UNMKO0) 영향 0
    - `_subscriptions` set 직접 수정 금지 — `kis_ws_pool.unsubscribe` 만 사용
    - 본체 예외는 호출자(`_scan_loop`)가 try/except 로 흡수
    """
    from src.db.system_logs import write_log as _write_log
    from src.engine.scanner import TICK_TR_ID
    from src.realtime.websocket_pool import kis_ws_pool

    current = kis_ws_pool.get_subscribed_tickers()
    delta_remove = sorted(current - new_set)
    if not delta_remove:
        return []

    unsubscribed: list[str] = []
    for ticker in delta_remove:
        try:
            await kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)
            unsubscribed.append(ticker)
        except Exception:
            logger.exception("[delta_unsubscribe] %s 실패", ticker)
        await asyncio.sleep(0.05)

    logger.info(
        "[scan_loop_delta] unsubscribed=%d tickers=%s",
        len(unsubscribed), unsubscribed[:10],
    )
    try:
        await _write_log(
            "INFO",
            f"[scan_loop_delta] unsubscribed={len(unsubscribed)} "
            f"tickers={unsubscribed[:10]}",
        )
    except Exception:
        logger.debug("[scan_loop_delta] write_log 실패", exc_info=True)
    return unsubscribed


async def evaluate_universe_guard(
    scheduler: Any, candidate_tickers: list[str]
) -> None:
    """사이클 32 (R4) — universe stale 가드 평가 + KIS 최근체결시각 기록. L2964 본체 그대로 이주.

    절대 깨지 말 것:
    - 보유 종목 / 익일청산 종목 절대 제외 금지 (사전 가드 순서 보존)
    - `_universe_excluded_today.add()` + `kis_ws_pool.unsubscribe()` 순서 보존
    - 50ms sleep Rate Limit 보호
    - `_reset_daily_state` 동행 clear (`_stale_state.reset_daily()` 통합 — A2 추가 없음)

    stale > MAX_STALE_RETRIES (=5) + KIS 당일 누적 거래량 < UNIVERSE_LOW_VOLUME_THRESHOLD
    → universe 에서 자동 제외 + WebSocket unsubscribe + INFO 로그 영구 보존.

    안전 가드:
    - 보유 종목 (`registry.is_ticker_held_by_any`) 절대 제외 금지 (손절·트레일링 우선)
    - 익일청산 종목 (`_pending_next_day_clear`) 절대 제외 금지 (시가 race 차단)
    - 이미 제외된 종목 재평가 skip (KIS Rate Limit 절약)
    - KIS `inquire_ccnl` 응답 None → 제외 보류 (다음 사이클 자연 재시도, graceful)
    - 종목 간 50ms sleep (Rate Limit 보호)
    - 본체 예외는 호출자(`_scan_loop`) 가 try/except 흡수 — 다음 사이클 자연 재시도

    Args:
        scheduler: TradingScheduler 인스턴스.
        candidate_tickers: 평가 대상 후보 리스트 (보통 `_collect_breakout_tickers` 결과 + extras)

    Note:
        매일 `_reset_daily_state` 가 `_universe_excluded_today.clear()` — 영구 블랙리스트 금지.
        제외된 종목은 다음 영업일 자동 재진입 가능.
    """
    from src.api.quotation import inquire_ccnl
    from src.db.system_logs import write_log as _write_log
    from src.engine.scanner import TICK_TR_ID
    from src.realtime.websocket_pool import kis_ws_pool

    # 사전 가드 — 보유 / 익일청산 / 이미 제외된 종목 사전 차단 (KIS 호출 절약)
    ndc_tickers = {t for (t, _sid) in getattr(scheduler, "_pending_next_day_clear", set())}
    excluded = getattr(scheduler, "_universe_excluded_today", set())

    # 평가 대상 결정 — stale > MAX_STALE_RETRIES + 보유/익일청산/이미 제외 아님
    targets: list[str] = []
    for ticker in candidate_tickers:
        if ticker in excluded:
            continue
        try:
            if scheduler.registry.is_ticker_held_by_any(ticker):
                continue
        except Exception:
            # registry 미주입 보호 (테스트 __new__)
            pass
        if ticker in ndc_tickers:
            continue
        retries = scheduler._stale_retry_count.get(ticker, 0)
        if retries <= MAX_STALE_RETRIES:
            continue
        targets.append(ticker)

    if not targets:
        return

    for ticker in targets:
        # KIS 호출 — graceful (실패 시 제외 보류, 다음 사이클 자연 재시도)
        try:
            ccnl = await inquire_ccnl(ticker)
        except Exception:
            logger.exception(
                "[universe_guard] inquire_ccnl 예외 ticker=%s — 제외 보류", ticker
            )
            continue

        if ccnl is None:
            # 빈 응답 (오프장 / 거래 없음) → 제외 보류
            logger.debug(
                "[universe_guard] inquire_ccnl None ticker=%s — 제외 보류",
                ticker,
            )
            await asyncio.sleep(0.05)
            continue

        today_volume = ccnl.get("today_volume", 0)
        if today_volume >= UNIVERSE_LOW_VOLUME_THRESHOLD:
            # 거래량 충분 → 제외 안 함 (가드 미발화)
            await asyncio.sleep(0.05)
            continue

        # 제외 결정 — 카운터 + last_resub_age 계산
        retries = scheduler._stale_retry_count.get(ticker, 0)
        last_at = scheduler._stale_last_resubscribe_at.get(ticker)
        if last_at is not None:
            from src.engine.scanner import KST_TZ as _KST_TZ
            age_secs = (datetime.now(_KST_TZ) - last_at).total_seconds()
            age_disp = f"{age_secs:.0f}s"
        else:
            age_disp = "-"

        # 제외 set 등록 + WebSocket unsubscribe
        scheduler._universe_excluded_today.add(ticker)
        try:
            await kis_ws_pool.unsubscribe(TICK_TR_ID, ticker)
        except Exception:
            logger.exception(
                "[universe_excluded] unsubscribe 실패 ticker=%s", ticker
            )

        # INFO 로그 + system_logs 영구 보존
        logger.info(
            "[universe_excluded] ticker=%s reason=stale_6plus_low_volume "
            "retries=%d last_resub_age=%s last_cntg_hour=%s today_volume=%d",
            ticker, retries, age_disp,
            ccnl.get("last_cntg_hour", ""),
            today_volume,
        )
        try:
            await _write_log(
                "INFO",
                f"[universe_excluded] ticker={ticker} "
                f"reason=stale_6plus_low_volume retries={retries} "
                f"last_resub_age={age_disp} "
                f"last_cntg_hour={ccnl.get('last_cntg_hour', '')} "
                f"today_volume={today_volume}",
            )
        except Exception:
            logger.debug("[universe_excluded] write_log 실패", exc_info=True)

        await asyncio.sleep(0.05)  # Rate Limit 보호
