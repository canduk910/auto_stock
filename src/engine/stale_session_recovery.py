"""사이클 67 = stale_manager.py 1,099L sub-module 분해 (Q1=A facade) — silent inactive 복구.

사이클 61 Phase 2-A2 (2026-06-05): scheduler.py 의 silent inactive + reconnect + delta 3 함수 + 5 상수 이전.
사이클 67 (2026-06-06): stale_manager.py 1,099L → 4 sub-module 분해 (카드 #14 MEDIUM).

절대 깨지 말 것:
- 함수 본체 변경 0 (라인 단위 동일, self.* → scheduler.* 치환만)
- 시간당 세션당 2회 cap — `_silent_inactive_recovery_count` dict 동일성 (모듈 전역 인스턴스 영속)
- `sys.modules.get("src.engine.scheduler")` 패턴 영속 (D-1 AST 가드 + freezegun patch 호환)
- 상수 값 변경 0 (SoT: 이 파일이 5 상수의 단일 정의처)
- Q1 옵션 A 단방향: 이 파일은 stale_watcher_core / stale_diagnostics / stale_universe_guard 를 import 금지
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 영속 (caplog 호환)

# ── 상수 (SoT: 이 파일이 5 상수의 단일 정의처) ──────────────────────────────────
# 사이클 29-R2 (2026-05-21) — silent_inactive 판정 비율 기반 전환
SILENT_INACTIVE_FRESH_RATIO_THRESHOLD = 0.2  # fresh_ratio < 20% 면 silent 의심 (사이클 24 fresh==0 완화)

# 사이클 24 (2026-05-20) — 세션 단위 silent inactive 감지 + 강제 reconnect
# 시간당 2회 cap — KIS LMS / 앱정보 이용중지 위험 사전 차단.
SILENT_INACTIVE_MIN_SUBSCRIBED = 5          # sub < 5 면 거래량 부족 자연 가능 (위양성 차단)
SILENT_INACTIVE_PERSIST_SECS = 300.0        # 5분 지속 임계 (단발 끊김 즉시 close 차단)
SILENT_INACTIVE_RECOVERY_CAP_PER_HOUR = 2   # 시간당 reconnect 시도 cap
SILENT_INACTIVE_RECOVERY_WINDOW_SECS = 3600.0  # cap 윈도우 (60분)

# STALE_FRESHNESS_SECS 는 stale_diagnostics.py 가 SoT.
# detect_silent_inactive_sessions 에서 직접 사용하므로 여기서 import.
from src.engine.stale_diagnostics import STALE_FRESHNESS_SECS  # noqa: E402


# ── A2 3 함수 (사이클 61 Phase 2-A2 이주) ────────────────────────────────────────
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
        # 사이클 72 hotfix A7: write_log 제거 — logger.warning → _DbLogHandler 위임 단일 INSERT
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
    # 사이클 72 hotfix A8: write_log 제거 — logger.warning → _DbLogHandler 위임 단일 INSERT

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
    # 사이클 72 hotfix A9: write_log 제거 — logger.info → _DbLogHandler 위임 단일 INSERT
    return unsubscribed
