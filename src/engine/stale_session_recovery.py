"""사이클 67 = stale_manager.py 1,099L sub-module 분해 (Q1=A facade) — silent inactive 복구.

사이클 61 Phase 2-A2 (2026-06-05): scheduler.py 의 silent inactive + reconnect + delta 3 함수 + 5 상수 이전.
사이클 67 (2026-06-06): stale_manager.py 1,099L → 4 sub-module 분해 (카드 #14 MEDIUM).
사이클 241 (2026-09-02) — `detect_silent_inactive_sessions` 세션 상대 판정 도입 (08-31 포렌식
결함 ⓐ · 워크리스트 P1-4). 30일 522건 중 491건(94.1%)이 판정 가능 세션 전원 동시 침묵 = 시장
침묵(NXT 프리 마감 08:50~09:00 · 15:20 이후 장후 동시호가 + 15:30~15:40 마감 흡수)이고 재연결이
회복시킨 사례는 0건이었다. 상세: `_workspace/red/cycle241_silent_inactive_relative_spec.md`.

절대 깨지 말 것:
- 사이클 61/67 이주 당시 계약 = 함수 본체 변경 0 (라인 단위 동일, self.* → scheduler.* 치환만).
  **cycle241 예외 1건** — `detect_silent_inactive_sessions` 는 의도된 행위 변경(세션 상대 판정)을
  도입한다. `force_reconnect_session` · `delta_unsubscribe_dropped` 는 이 사이클도 diff 0.
- 시간당 세션당 2회 cap — `_silent_inactive_recovery_count` dict 동일성 (모듈 전역 인스턴스 영속)
- `sys.modules.get("src.engine.scheduler")` 패턴 영속 (D-1 AST 가드 + freezegun patch 호환)
- 상수 값 변경 0 (SoT: 이 파일이 5 상수의 단일 정의처). cycle241 신규 2 상수는 module-private
  추가(`_MARKET_WIDE_MIN_ELIGIBLE`/`_MARKET_WIDE_PERSIST_WARN_SECS`, SoT 5 상수 밖 — facade 미노출)
- Q1 옵션 A 단방향: 이 파일은 `stale_watcher_core` 를 import 금지. `stale_diagnostics` 의
  `STALE_FRESHNESS_SECS` 는 허용된 단방향 예외(`:35`, G-7 이 실제로 검사하는 대상)
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


# ── cycle241 세션 상대 판정 (private — facade 미노출, 5 상수 SoT 와 별개) ──────────
_MARKET_WIDE_MIN_ELIGIBLE = 2            # 비교 가능 최소 판정 가능 세션 수. 미만 = 현행 유지(fail-open)
_MARKET_WIDE_PERSIST_WARN_SECS = 1800.0  # 에피소드 지속 WARNING 첫 발화·재발화 간격 (정상 최장 15:20→15:40 1,200s × 1.5)

# 에피소드 관측 상태 — StaleTrackerState(7필드 정확 일치 가드)·scheduler(3,999L) 어느 쪽에도 못 두므로 모듈 전역.
# 날짜 키 자기 리셋(cycle237 선례). 행위(기각·pop)는 이 dict 를 읽지 않는다 — 관측 전용.
_MW_EPISODE: dict[str, Any] = {
    "day": "", "since": None, "cycles": 0, "last_warn_at": None, "fail_warned_day": "",
}


def reset_market_wide_episode_state() -> None:
    """테스트 전용 — 에피소드 관측 상태 초기화 (facade 미노출, 운영 호출처 0)."""
    _MW_EPISODE.update(day="", since=None, cycles=0, last_warn_at=None, fail_warned_day="")


def _count_connected(sessions: Any) -> int:
    """`ws_connected is True` 세션 수 — 진단 필드 전용. 키 부재·비 dict 는 0 (5min 픽스처 호환).

    ⚠️ **읽는 법**: `ws_connected` 는 "소켓이 지금 생존" 이 아니라 "`_ws` 객체를 보유" 를 뜻한다
    (`websocket_pool.py::get_session_status` — `getattr(ws, "_ws", None) is not None`).
    재연결 backoff 대기 중에도 이전 `_ws` 가 즉시 클리어되지 않는 코드 경로가 있어(닫힌 소켓
    객체가 남는 케이스), 08-31 형 재연결 폭풍 중에도 `connected=8` 이 찍힐 수 있다 — 그 값을
    "소켓 정상, 순수 시장 침묵" 의 확증으로 오독하지 말 것. ⚠️ **`reconnects=` 필드는 이 사각을
    메우지 못한다(cycle241 라운드 2 정정)** — `force_reconnect_session` 강제 재연결은 그
    카운터를 올리지 않으므로 08-31 형 폭풍 중에도 0 에 가깝게 남는다(`_count_reconnects`
    docstring 참조). 소켓 생존 판별은 `[ws_heartbeat]`(세션별 PINGPONG 기반, `websocket.py`) 와
    함께 읽는다."""
    try:
        return sum(1 for s in sessions if isinstance(s, dict) and s.get("ws_connected") is True)
    except Exception:
        return 0


def _count_reconnects(sessions: Any) -> int:
    """세션별 `reconnect_count` 합 — 진단 필드 전용. 키 부재·비 dict·비정상 값은 0 기여.

    ⚠️ **읽는 법 (cycle241 라운드 2 정정)**: `reconnect_count`(=`KisWebSocket._reconnect_count`)
    는 "핸드셰이크 단계 재시도 인덱스"(세션당 상한 `MAX_RECONNECT=5`, `websocket.py`)다 —
    `connect()` 의 `except (ConnectionClosed, InvalidURI, OSError)` 분기(연결 시도/수립 도중의
    예기치 못한 단절)에서만 증가하고, `MIN_STABLE_SECONDS=5초` 이상 유지된 연결은 while 루프
    복귀 시 곧바로 0 으로 리셋된다. **`force_reconnect_session` 의 `_ws.close()` 로 일으키는
    재연결은 이 카운터를 올리지 않는다** — `_receive_loop` 가 그 `ConnectionClosed` 를 삼켜
    정상 반환하므로 `connect()` 의 except 분기에 도달하지 않고, silent_inactive 는 정의상
    5분 이상 유지된 연결이라 복귀 즉시 0 으로 리셋된다. 즉 **08-31 형 강제 재연결이 회당
    `_ws.close()` 로 88회 반복돼도 이 합은 0 에 가깝게 머문다** — "재연결 폭풍이면 세션 수를
    크게 웃도는 값으로 뛴다" 는 서술은 사실이 아니었다(라운드 1 docstring 오류, 라운드 2 시정).
    `connected=` 의 사각(재연결 대기 중 stale `_ws` 객체 보유)도 이 필드로는 메우지 못한다 —
    소켓 생존 판별은 `[ws_heartbeat]`(세션별 PINGPONG 기반, `websocket.py`) 를 함께 읽는다."""
    try:
        total = 0
        for s in sessions:
            if not isinstance(s, dict):
                continue
            value = s.get("reconnect_count", 0)
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            total += value
        return total
    except Exception:
        return 0


def _observe_market_wide(now: datetime, *, sessions_n: int, eligible_n: int, silent_n: int,
                          connected_n: int, reset_n: int, reconnects_n: int = 0) -> None:
    """시장 침묵 기각 관측 — entered(INFO 1회) / persisting(WARNING, ≥1800s 후 1800s 마다). never-raise.

    peek→로그→mark: `since`(entered) · `last_warn_at`(persisting) 은 로그 성공 **뒤**에 기록.
    `cycles` 는 카운터라 cap 대상이 아니다. 날짜 키가 바뀌면 상태를 먼저 비운다.

    `connected=` 은 "`_ws` 객체 보유"(재연결 대기 stale 포함) 이지 소켓 생존 확증이 아니다.
    ⚠️ **`reconnects=`(세션별 `reconnect_count` 합) 는 그 사각을 메우지 못한다 (cycle241
    라운드 2 정정)** — `force_reconnect_session` 강제 재연결은 이 카운터를 올리지 않으므로
    (`_count_reconnects` docstring 참조) 08-31 형 재연결 폭풍 중에도 0 에 가깝게 남는다.
    소켓 생존 판별은 `[ws_heartbeat]`(세션별 PINGPONG 기반, `websocket.py`) 와 이 함수의
    `transition=persisting` 지속 시간으로 읽는다 — `reconnects=` 는 "현재 핸드셰이크 재시도
    인덱스 합" 이라는 보조 진단으로만 취급한다.
    """
    try:
        day = now.date().isoformat()
        if _MW_EPISODE["day"] != day:
            _MW_EPISODE.update(day=day, since=None, cycles=0, last_warn_at=None)
        if _MW_EPISODE["since"] is None:                       # peek
            logger.info(
                "[silent_inactive_market_wide_skip] transition=entered sessions=%d eligible=%d "
                "silent=%d/%d connected=%d reset=%d reconnects=%d",
                sessions_n, eligible_n, silent_n, eligible_n, connected_n, reset_n, reconnects_n,
            )                                                   # 로그
            _MW_EPISODE.update(since=now, cycles=1, last_warn_at=None)   # mark
            return
        _MW_EPISODE["cycles"] += 1
        elapsed = (now - _MW_EPISODE["since"]).total_seconds()
        ref = _MW_EPISODE["last_warn_at"] or _MW_EPISODE["since"]
        if (elapsed >= _MARKET_WIDE_PERSIST_WARN_SECS
                and (now - ref).total_seconds() >= _MARKET_WIDE_PERSIST_WARN_SECS):   # peek
            logger.warning(
                "[silent_inactive_market_wide_skip] transition=persisting elapsed_secs=%d cycles=%d "
                "sessions=%d eligible=%d silent=%d/%d connected=%d reconnects=%d",
                int(elapsed), _MW_EPISODE["cycles"], sessions_n, eligible_n, silent_n, eligible_n,
                connected_n, reconnects_n,
            )                                                   # 로그
            _MW_EPISODE["last_warn_at"] = now                   # mark
    except Exception:
        _trace_market_wide_failure(now)


def _close_market_wide_episode(now: datetime) -> None:
    """열린 에피소드가 있으면 exited(INFO 1회) 후 상태 해제. never-raise. 없으면 no-op."""
    try:
        if _MW_EPISODE["since"] is None:
            return
        elapsed = (now - _MW_EPISODE["since"]).total_seconds()
        logger.info(
            "[silent_inactive_market_wide_skip] transition=exited elapsed_secs=%d cycles=%d",
            int(elapsed), _MW_EPISODE["cycles"],
        )                                                       # 로그
        _MW_EPISODE.update(since=None, cycles=0, last_warn_at=None)   # mark
    except Exception:
        _trace_market_wide_failure(now)


def _trace_market_wide_failure(now: datetime) -> None:
    """관측기 자기 실패 흔적 — WARNING 1회/일 + debug 스택 (cycle225 J-3: debug 단독은 `_DbLogHandler` INFO 컷을 못 넘는다).
    가장 안쪽은 어떤 경우에도 조용히 통과."""
    try:
        logger.debug("[silent_inactive_market_wide_skip_failed]", exc_info=True)
        day = now.date().isoformat()
        if _MW_EPISODE.get("fail_warned_day") != day:
            logger.warning("[silent_inactive_market_wide_skip_failed] observer raised — 기각 행위는 수행됨")
            _MW_EPISODE["fail_warned_day"] = day
    except Exception:
        pass


# ── A2 3 함수 (사이클 61 Phase 2-A2 이주) ────────────────────────────────────────
# silent inactive + universe guard + delta unsubscribe
# scheduler.py 본체 그대로 복붙 + self.* → scheduler.* 치환만.
# 사이클 61 이주 시점 계약 — 행위 변경 0건 의무 (refactor only).
# cycle241 예외 1건 — detect_silent_inactive_sessions 세션 상대 판정 (아래 함수 docstring 참조).

def detect_silent_inactive_sessions(scheduler: Any) -> list[str]:
    """세션 단위 silent inactive 감지 (사이클 24 / 29-R2 / cycle241 세션 상대 판정).

    종목별 unsubscribe+subscribe 재등록(K stale watcher 사이클 17 보강) 으로
    회복 안 되는 *세션 자체* silent inactive 케이스를 5분 지속 후 강제 reconnect 대상으로 분류.

    판정 (4중):
    1. fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD (=0.2, 20%)
       — 사이클 29-R2 (2026-05-21): 기존 `fresh == 0` 완화. 메인 fresh=2/25 (8%) 실측
         결함 대응. fresh=0 케이스는 0.0 < 0.2 자동 호환.
    2. subscribed >= SILENT_INACTIVE_MIN_SUBSCRIBED (1~4 종목은 거래량 부족 자연 가능)
    3. 5분 지속 (first_seen 시각 추적)
    4. **세션 상대 판정 (cycle241)** — 판정 가능 세션(subscribed >= MIN, 1+2 를 곧바로 만족할
       필요는 없다 — 세션 자체가 "비교 가능"함을 뜻한다)이 `_MARKET_WIDE_MIN_ELIGIBLE(=2)`
       이상이고 **그 전부**가 1+2(silent_suspect)이면 "세션 N개 동시 고장"이 아니라
       **시장 침묵**(NXT 프리 마감 08:50~09:00 · 15:20 이후 장후 동시호가 + 15:30~15:40
       마감 흡수)으로 보고 그 사이클을 기각한다 — 30일 522건 중 491건(94.1%)이 이 형태였고
       재연결이 회복시킨 사례는 0건이었다.

    조건 1+2 미충족(fresh_ratio >= 0.2 또는 subscribed < min) 시 first_seen pop(리셋).
    5분 도달 label 만 반환 — 단 4의 게이트가 열리면(시장 침묵) **누적 자체를 하지 않고**
    판정 가능 세션 전 라벨의 first_seen 을 pop 한 뒤 빈 리스트를 즉시 반환한다. 값을 유지
    (hold)하지 않는 이유 = 침묵 구간 동안 first_seen 이 계속 자라면 시장이 재개돼 한 세션만
    늦게 깨어나는 순간 elapsed >= 300 이 이미 성립해 **즉발**한다 — 오판이 재개 경계로
    이동할 뿐이다. 재개 후에도 진짜 결함이면 그 시점부터 다시 5분을 세어 정상 발화한다.

    fail-open 경계 — 다음은 게이트가 열리지 않고(off) 현행(3중 판정) byte 동일:
    - 판정 가능 세션 < 2 (단일 세션 풀 VTS/개발, 20:00 unsubscribe_all 직후 등 비교 대상 부재)
    - 판정 가능 세션 >= 2 이나 하나라도 fresh(silent_suspect 가 전부는 아님) — 진짜 단독
      세션 결함일 가능성이 남아 있으므로 현행대로 판정·발화한다.

    시장 침묵 기각은 `_MW_EPISODE`(모듈 전역, 날짜 키 자기 리셋) 로 관측만 한다 — 행위(pop +
    빈 리스트 반환)를 바꾸지 않는다(관측 헬퍼는 never-raise, 예외 흡수). 로그 prefix
    `[silent_inactive_market_wide_skip]` 로 3전이(entered 진입 1회 / persisting 30분마다
    WARNING / exited 이탈 1회)를 emit — 08-31 형 4시간 두절도 몇 줄로 축약된다.
    **결과 집합 ⊆ 현행** — cycle241 은 새 발화 경로를 만들지 않는다(게이트는 발화를 만들지
    않고 pop 은 elapsed 를 줄이기만 한다).
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

    # ── pass 1 (cycle241): 세션별 판정 재료 — 상태 무변경. fresh/ratio/suspect 식은 사이클 29-R2 byte 동일.
    judged: list[tuple[str, int, bool]] = []          # (label, subscribed_count, silent_suspect)
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
        judged.append((label, subscribed_count, silent_suspect))

    # ── cycle241 세션 상대 판정: 판정 가능 세션(sub >= MIN) 이 2개 이상이고 전부 침묵이면 시장 침묵 → 기각.
    eligible_n = sum(1 for (_l, n, _s) in judged if n >= SILENT_INACTIVE_MIN_SUBSCRIBED)
    silent_n = sum(1 for (_l, _n, s) in judged if s)
    _market_wide = eligible_n >= _MARKET_WIDE_MIN_ELIGIBLE and silent_n == eligible_n
    if _market_wide:
        # 행위 (cap 밖): 전 라벨 first_seen pop — 누적 금지. 재개 시점부터 다시 5분을 센다.
        reset_n = sum(
            1 for (label, _n, _s) in judged
            if scheduler._silent_inactive_first_seen.pop(label, None) is not None
        )
        # 관측 (예외 흡수): 에피소드 entered/persisting
        _observe_market_wide(now, sessions_n=len(judged), eligible_n=eligible_n, silent_n=silent_n,
                              connected_n=_count_connected(sessions), reset_n=reset_n,
                              reconnects_n=_count_reconnects(sessions))
        return []
    _close_market_wide_episode(now)                    # 열린 에피소드 있으면 exited 1행

    # ── pass 2: 사이클 24/29-R2 누적 루프 — 입력만 judged 튜플, 분기·대입·pop 위치 byte 동일.
    for (label, _n, silent_suspect) in judged:
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
       - DB 라벨(gold/sub 등) → _quotes 리스트에서 _label 매칭 세션 close
         (사이클 194 — 사이클 43 라벨 통일 완결, disable_quote_session 패턴 정합)
    3. 영구 로그: INFO + system_logs write_log (fire-and-forget)
    4. _silent_inactive_first_seen.pop(label) — 다음 5분 카운트 리셋
    5. _silent_inactive_recovery_count[label].append(time.monotonic())

    Returns:
        True (reconnect 시도) / False (cap 도달 skip)
    """
    import sys
    import time as _t

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
        # 사이클 194 — DB 라벨 매칭 (gold/sub 등). 사이클 43 라벨 통일 완결
        # (disable_quote_session websocket_pool.py:455 정합). quote-N 인덱스 파싱 폐기.
        quotes = getattr(kis_ws_pool, "_quotes", [])
        matched = next((q for q in quotes if getattr(q, "_label", None) == label), None)
        if matched is None:
            logger.warning("[silent_inactive_force_reconnect] 알 수 없는 label=%s", label)
            return False
        ws_obj = getattr(matched, "_ws", None)

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
