"""KIS WebSocket 연결 관리.

- 접속키 발급 후 WebSocket 연결
- 종목 구독/해제 (최대 41건, KIS 공식 한도)
- Heartbeat 감시, 자동 재연결 (최대 5회 지수 백오프)
- 메시지 수신 → handler로 디스패치
- 보유 종목 시세 구독은 `bypass_limit=True` 로 한도 무시 (E1, 2026-05-12)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Callable, Awaitable

import websockets
from websockets.asyncio.client import ClientConnection

from src.auth.token import token_manager
from src.config import settings
from src.db.system_logs import write_log
from src.engine.daily_emit_cap import DailyEmitCap, KstDailyEmitCap  # 사이클 197 — 41-cap WARNING 1회/키/일 (의존성 0, 순환 없음)
from src.realtime.handler import set_aes_keys

logger = logging.getLogger(__name__)

MAX_SUBSCRIPTIONS = 41  # KIS 공식 한도 41건 (1 세션 당). 보유 종목은 한도 무시하고 우선 보장 (subscribe_filtered_stocks priority_groups)
MAX_RECONNECT = 5
HEARTBEAT_TIMEOUT = 30  # 초
# 사이클 42 (2026-05-22) — PINGPONG 가시성 + 5분 주기 [ws_heartbeat] 통계 emit 주기
HEARTBEAT_METRICS_INTERVAL_SECS = 300  # 5분
BACKOFF_BASE = 1.0
MIN_STABLE_SECONDS = 5  # 이 시간 이상 연결 유지해야 안정적 연결로 판단

# F1 (2026-05-12) — 재연결 후 자동 시세 검증
# KIS silent inactive(SUBSCRIBE 응답도 시세도 안 주는 케이스) 차단용.
# E2 의 거절 감지가 동작하려면 거절 응답이 와야 하므로 silent inactive 는 못 잡음.
VERIFY_AFTER_SECS = 60        # 재연결 후 검증까지 대기
VERIFY_FRESHNESS_SECS = 60    # 검증 기준 — 이 시간 내 tick 없으면 미수신으로 판정
_KST_TZ = timezone(timedelta(hours=9))

# 사이클 92 (2026-06-10) — MAX_RECONNECT 도달 시 자동 재기동 (KIS 07:50 강제 중단 충돌 영구 시정)
# Q28=E (TIME_BOOT 07:55) + Q30=A (자동 재기동 idempotent) 동반 시정.
# 60s cooldown (사이클 13-E-2 답습) + 시간당 3회 cap (LMS chain 차단, 사이클 24 silent_inactive 답습)
# 4중 안전망 *추가* 영역 (G-REJECT-1 위반 0, 사이클 88 영속)
_AUTO_RESTART_COOLDOWN_SECS = 60.0   # idempotent 재호출 간 cooldown
_AUTO_RESTART_HOURLY_CAP = 3          # 시간당 cap (KIS LMS chain 차단)
_AUTO_RESTART_WINDOW_SECS = 3600.0    # 1시간 슬라이딩 윈도우

# 사이클 16 (2026-05-19) — AES 키 저장 가드용 체결통보 tr_id 화이트리스트.
# `_handle_raw` SUBSCRIBE SUCCESS 분기에서 메인 세션 + 이 tr_id 만 모듈 전역 AES 키 저장.
# 보조 세션 또는 시세 SUBSCRIBE SUCCESS 는 skip — 체결통보 키 덮어쓰기 race 차단.
_EXECUTION_NOTICE_TR_IDS = frozenset({"H0STCNI0", "H0STCNI9"})

# cycle293 (2026-09-14) — cycle253 운영자 진단 프로브 튜플 제외 집합.
#
# 🔴 격리 기준이 **채널 → 프로브 정체성**으로 옮겨졌다. cycle253 은 "TICK 집계는
# `H0UNCNT0` 만 센다" 는 **채널 동일성**에 프로브 격리를 얹었고, 그 덕분에 프로브가
# K stale watcher(재등록) · universe guard(축출) · `delta_unsubscribe_dropped`(5분
# delta 해제) · F1 재검증 어디에도 등장하지 않았다. cycle293 이 그 전용 채널을
# **실제 구독**에 쓰기 시작하면서 그 추론이 죽었다 — 채널만 보면 이제 프로브와 실
# 구독을 구분할 수 없고, 프로브를 그냥 노출하면 다음 `_scan_loop`(5분)이
# `current - new_set` 으로 프로브를 해제해 측정을 끊는다.
#
# 그래서 격리를 "어느 채널인가" 가 아니라 "그 튜플이 프로브인가" 로 판정한다.
# 집합은 `src/routes/realtime.py` 의 프로브 시작/종료가 유지한다(프로세스 메모리,
# 20:00 `unsubscribe_all` 과 같은 수명). 비어 있는 것이 정상 운영 상태다 —
# 프로브는 기본 OFF 이고 cap 3 이다.
PROBE_EXCLUDED_TUPLES: set[tuple[str, str]] = set()

#: 각 제외 항목이 등록된 KST 날짜. 🔴 **수명 관리가 이 dict 다.**
#:
#: 적대 검증(HIGH) — 종전 주석은 이 집합의 수명이 "20:00 `unsubscribe_all` 과
#: 같다" 고 적었지만 `unsubscribe_all` 은 이 집합을 **비우지 않았다**. 회수 지점은
#: `routes/realtime.py::_unsubscribe_probe_everywhere` 하나뿐이고 `_evict_stale_probes`
#: 는 **다음 프로브 POST 진입 시에만** 돈다. 프로브를 stop 없이 두고 다음 POST 가
#: 없으면 그 `(tr_id, ticker)` 가 프로세스 수명 내내 남고, cycle293 이 **같은
#: 채널을 실 구독에 쓰기 시작**했으므로 그 종목의 라이브 구독이
#: `get_subscribed_tickers()` 에서 조용히 사라진다 = K stale watcher 블라인드 ·
#: `delta_unsubscribe_dropped` 미해제(실제 슬롯 누수) · 매 5분 재SEND ·
#: `[tick_coverage]` 분모 감소 = 이 사이클이 없애려던 §5-B 피해 그대로다.
#:
#: 그래서 (a) `is_probe_excluded()` 가 **KST 날짜가 다르면 스스로 회수**하고
#: (b) `WebsocketPool.unsubscribe_all()`/`stop()` 이 `reset_probe_exclusions()` 를
#: 부른다. 어느 호출자도 남기지 못하는 구조가 정본이다.
_PROBE_EXCLUSION_DAY: dict[tuple[str, str], str] = {}


def _probe_exclusion_today() -> str:
    try:
        return datetime.now(_KST_TZ).date().isoformat()
    except Exception:  # pragma: no cover — never-raise
        return ""


def register_probe_exclusion(tr_id: str, tr_key: str) -> None:
    """이 튜플이 **프로브**임을 TICK 집계 쪽에 알린다 (cycle253 격리, cycle293 재기준).

    `routes/realtime.py` 의 프로브 시작 경로만 부른다. 집합을 **재바인딩하지
    않고 변형**한다 — `websocket_pool` 이 같은 객체를 import 로 들고 있다.
    """
    PROBE_EXCLUDED_TUPLES.add((tr_id, tr_key))
    _PROBE_EXCLUSION_DAY[(tr_id, tr_key)] = _probe_exclusion_today()


def unregister_probe_exclusion(tr_id: str, tr_key: str) -> None:
    """프로브 종료·드롭 시 회수."""
    PROBE_EXCLUDED_TUPLES.discard((tr_id, tr_key))
    _PROBE_EXCLUSION_DAY.pop((tr_id, tr_key), None)


def is_probe_excluded(tr_id: str, tr_key: str) -> bool:
    """이 튜플을 TICK 집계에서 제외해야 하는가 (날짜 경과분은 여기서 자기 회수)."""
    key = (tr_id, tr_key)
    if key not in PROBE_EXCLUDED_TUPLES:
        return False
    day = _PROBE_EXCLUSION_DAY.get(key)
    today = _probe_exclusion_today()
    if day and today and day != today:
        # 전날 잔존 — 라이브 구독을 은폐하기 전에 스스로 회수한다.
        PROBE_EXCLUDED_TUPLES.discard(key)
        _PROBE_EXCLUSION_DAY.pop(key, None)
        return False
    return True


def reset_probe_exclusions() -> None:
    """제외 등록 전부 회수 (20:00 `unsubscribe_all` · `stop` · 테스트 격리 seam)."""
    PROBE_EXCLUDED_TUPLES.clear()
    _PROBE_EXCLUSION_DAY.clear()

# 구독 거절 감지 키워드 (E2, 2026-05-12) — msg1 대소문자 무시 substring 매칭.
# rt_cd != "0" 1순위, 키워드는 보조. 한국어/영문 변형 누적.
_REJECT_KEYWORDS_UPPER = (
    "ERROR", "FAIL", "REJECT", "NOT ALLOWED",
    "LIMIT", "EXCEED", "DUPLICATE",
    # 사이클 17 (2026-05-19) — KIS 공식 답변 인용 41건 한도 초과 시 "MAX SUBSCRIBE OVER" 메시지.
    # 기존 LIMIT/EXCEED/OVER 단독 키워드 모두 미매칭이라 명시 추가.
    "MAX SUBSCRIBE",
)
_REJECT_KEYWORDS_KO = (
    # N (2026-05-12) — "이미" 제거: ALREADY IN SUBSCRIBE / "이미 구독" / "이미 등록" 은
    # KIS 측 "이미 활성" 의미로 거절 분기 진입 *전* `_handle_raw` 의 ALREADY 가드가
    # 흡수한다. "이미" 는 다른 정상 메시지에도 광범위하게 출현하는 위양성 키워드.
    "한도", "초과", "중복", "허용되지", "권한",
)


def _is_rejection_response(rt_cd: str | None, msg1: str) -> bool:
    """구독 거절 응답 판정 (E2).

    - rt_cd 가 "0" 외 값이면 거절 (KIS REST 와 동일 규약)
    - rt_cd 가 None/빈문자열이면 (Heartbeat 등) msg1 키워드만 검사
    - msg1 키워드(대소문자 무시): ERROR/FAIL/REJECT/NOT ALLOWED/LIMIT/EXCEED/DUPLICATE,
      한도/초과/이미/중복/허용되지/권한
    """
    if rt_cd not in (None, "", "0"):
        return True
    upper = msg1.upper()
    if any(kw in upper for kw in _REJECT_KEYWORDS_UPPER):
        return True
    if any(kw in msg1 for kw in _REJECT_KEYWORDS_KO):
        return True
    return False


#: cycle294 §7-B — 레거시 통합 요청 재라우팅 관측 cap (1회/ticker/일, KST 자기 리셋).
_legacy_reroute_cap: "KstDailyEmitCap[str]" = KstDailyEmitCap()


def _reroute_legacy_unified(tr_id: str, tr_key: str) -> str:
    """cycle294 §7-B — 통합 채널 요청을 전용 채널로 되돌린다(레거시 호출자 구제).

    `scheduler.py` 는 이 사이클의 무접촉 대상인데 그 안의 두 줄(익일청산 시가
    수신 · 스윙 매수 직후)이 풀을 **우회해** 통합 채널로 직접 구독한다. 그 둘을
    그대로 두면 「통합 구독 0」 이 성립하지 않는다 — `websocket.py` 가 그것을
    잡을 수 있는 유일한 자리다.

    🔴 재라우팅 조건은 **`tr_id` 가 정확히 통합일 때** 하나뿐이다. 3단계에서
    통합은 아무도 의도적으로 고르지 않는 값이므로, 통합 요청 = 「리졸버를 안
    거친 호출」 의 확실한 신호다. 체결통보(`H0STCNI0`/`H0STCNI9`)·장운영정보
    (`H0UNMKO0`)·전용 2채널 요청은 이 함수를 **byte 동일**로 통과한다 — 그 넷 중
    하나라도 재라우팅되면 포지션 등록·손절이 끊기거나 이중 채널이 생긴다.

    풀의 세션들도 이 메서드를 쓰지만, 풀은 이미 리졸버가 고른 전용 채널을
    넘기므로 첫 조건에서 빠져나간다(멱등).

    ⚠️ 이것은 **증상 차단**이다. 근본 시정(그 두 줄을 리졸버 경유로 바꾸는 것)은
    `scheduler.py` 2줄 치환이고 별도 승인 대상이다.
    """
    try:
        from src.engine import tick_channel_mode
        from src.engine.scanner import (
            DEDICATED_TICK_TR_IDS,
            TICK_TR_IDS,
            subscribed_tick_tr_id,
        )

        # 「시세 채널이면서 전용이 아닌 것」 = 통합. 등가 비교(`tr_id == TICK_TR_ID`)를
        # 쓰지 않는 이유는 cycle293 A3(`test_a3_no_equality_comparison_against_tick_tr_id`)
        # 다 — 그 가드는 채널 판정을 **집합 멤버십**으로만 하도록 잠갔다. 두 정본
        # 집합에서 파생하면 채널이 하나 더 생겨도 이 판정이 조용히 낡지 않는다.
        if tr_id not in TICK_TR_IDS or tr_id in DEDICATED_TICK_TR_IDS:
            return tr_id
        if tick_channel_mode.current_mode() in (
            tick_channel_mode.MODE_OFF,
            tick_channel_mode.MODE_OBSERVE,
            # 🔴 적대 검증 HIGH-1(부팅) 시정 — `enforce_low` 는 **HIGH(보유·
            #    익일청산)를 스코프 밖**에 두는 단계적 롤아웃이다. 그런데 이
            #    함수는 우선순위를 모르므로 그 단계에서 레거시 통합 요청을
            #    전용 채널로 되돌리면 S1 의 안전장치가 통째로 무력화된다 —
            #    실측: `tick_tr_id_for(HIGH)` 는 통합을 돌려주는데 세션은
            #    전용 채널을 구독해 병행 dict 가 갈리고, 이어지는 해제가
            #    없는 튜플을 겨눠 KIS `OPSP0003` + 영구 고아를 만든다.
            #    레거시 직접 호출자 둘(익일청산 시가·스윙 매수 직후)은 전부
            #    HIGH 성격이라 `enforce_low` 에서 통과시키는 것이 정합이다.
            tick_channel_mode.MODE_ENFORCE_LOW,
        ):
            return tr_id                     # 롤백·다크런치·S1 은 오늘과 byte 동일
        routed = subscribed_tick_tr_id(tr_key)     # 풀 `_ticker_to_tr_id` 우선
        if not isinstance(routed, str) or routed == tr_id:
            return tr_id
        _emit_legacy_reroute(tr_key, tr_id, routed)
        return routed
    except Exception:  # pragma: no cover — never-raise
        return tr_id                         # 재라우팅 실패가 구독을 막지 않는다


def _emit_legacy_reroute(tr_key: str, from_tr_id: str, to_tr_id: str) -> None:
    """`[tick_channel_legacy_reroute]` — 1회/(ticker)/일.

    `scheduler.py` 두 줄의 **실제 발화 빈도**를 처음으로 재는 유일한 마커다.
    """
    try:
        if not _legacy_reroute_cap.should_emit(tr_key):
            return
        logger.warning(
            "[tick_channel_legacy_reroute] ticker=%s from=%s to=%s caller=legacy_direct",
            tr_key, from_tr_id, to_tr_id,
        )
        _legacy_reroute_cap.mark_emitted(tr_key)
    except Exception:  # pragma: no cover — never-raise
        pass


class KisWebSocket:
    """KIS WebSocket 연결 매니저.

    사이클 7-C — 보조 시세 세션 지원을 위해 선택적으로 `token_manager` 주입 가능.
    인자 미지정 시 메인 글로벌 `token_manager` 사용 (기존 동작 100% 보존).
    """

    def __init__(
        self,
        *,
        token_manager=None,
        is_main: bool = True,
        label: str | None = None,  # 사이클 42 (2026-05-22) — pool 주입 (메인=main / 보조=quote-N)
    ) -> None:
        # 사이클 7-C — 메인이면 None, 보조면 외부 매니저 주입
        # `connect()` / approval_key 발급 시 이 매니저 사용
        from src.auth.token import token_manager as _main_tm
        self._token_manager = token_manager if token_manager is not None else _main_tm
        # 사이클 16 (2026-05-19) — 메인/보조 세션 식별자. AES 키 저장 가드용.
        # 보조 세션은 시세 수신 only — 체결통보 구독 안 함 + AES 키 저장도 skip.
        # 메인 세션의 체결통보(H0STCNI0/H0STCNI9) AES 키만 모듈 전역 보존.
        self.is_main: bool = is_main
        # 사이클 42 (2026-05-22) — PINGPONG 가시성 + 5분 주기 [ws_heartbeat] 통계 label.
        # pool 주입 (메인=main / 보조=quote-1/quote-2/...). 미지정 시 is_main 기반 자동 결정.
        self._label: str = label if label is not None else ("main" if is_main else "quote-?")

        self._ws: ClientConnection | None = None
        self._approval_key: str = ""
        self._subscriptions: set[tuple[str, str]] = set()  # (tr_id, tr_key) — SEND 기준
        # G1 (2026-05-12) — KIS 정상 SUBSCRIBE SUCCESS 응답을 받은 구독만 add.
        # 운영자 가시성: `_subscriptions` 와 분리해 "SEND 후 무응답" 케이스 즉시 식별.
        self._subscriptions_acked: set[tuple[str, str]] = set()
        # 사이클 17 (2026-05-19) — OPSP0002 ALREADY IN SUBSCRIBE backoff 사전.
        # KIS 측 거부를 받으면 (tr_id, tr_key) 별 `now + 300.0` 등록 → subscribe 진입 시
        # 유효 시간 내면 send skip. 무한 재구독 → OPSP0002 → 무한 루프 차단.
        # bypass_limit=True (HIGH 우선순위) 는 검사 skip — 보유 종목 손절 우선 보장.
        # 사이클 17 보강 (2026-05-19) — 60s → 300s. `_scan_loop` 5분 주기 ≥ backoff 만료
        # 보장하여 같은 사이클 내 재시도 차단. KIS 답변 인용: "기등록한 사항을 재등록하지 않도록".
        self._opsp_backoff_until: dict[tuple[str, str], float] = {}
        # 사이클 197 — 41-cap 도달 WARNING DailyEmitCap (1회/(tr_id,tr_key)/일, KST 자기리셋).
        # 5분 scan 재시도가 동일 LOW 키를 반복 emit 하던 스팸 억제 (드롭 행위 불변).
        self._max_sub_warn_cap: DailyEmitCap[tuple[str, str]] = DailyEmitCap()
        self._max_sub_warn_date: str = ""
        self._running = False
        self._reconnect_count = 0
        self._on_message: Callable[[str, str, str, bool], Awaitable[None]] | None = None
        # 사이클 42 (2026-05-22) — PINGPONG 송수신 통계 (5분 주기 [ws_heartbeat] INFO emit)
        # ping-pong 메커니즘 자체는 정상 동작 (Layer 1/2/3 검증 완료) — 가시성 강화 도구.
        # 운영자가 5분 주기 INFO 로 송수신 빈도 + heartbeat timeout 누적 카운트 검증.
        self._pingpong_recv_count: int = 0
        self._pingpong_last_at: datetime | None = None
        from datetime import timezone, timedelta
        _KST_TZ_INIT = timezone(timedelta(hours=9))
        self._pingpong_window_start_at: datetime = datetime.now(_KST_TZ_INIT)
        self._heartbeat_timeout_count: int = 0
        # 사이클 46 (2026-05-22, refactor-review 카드 #6) — task lifecycle 제거.
        # scheduler `_session_health_loop` 가 5분마다 `_heartbeat_metrics_emit_once` 호출.
        # 좀비 task 방지 + 메인+보조 일관성 + 카운터 reset 동작 보존 (사이클 42 정책).
        # AES 복호화 키 (체결통보용)
        self.aes_iv: str = ""
        self.aes_key: str = ""
        # F1 (2026-05-12) — 재연결 후 자동 검증 task 중첩 방지 플래그
        self._reverify_in_progress: bool = False
        # 사이클 74 (2026-06-08) 옵션 E-1 — WS 구독/ACK/해제 tr_id별 aggregation collector.
        # subscribe/unsubscribe/SUBSCRIBE SUCCESS ACK/OPSP0002 정상 흐름 INFO → 5분 1행 흡수.
        # 구조: tr_id → {"SUBSCRIBE": [tickers], "UNSUBSCRIBE": [tickers], "ACK": [tickers],
        #                "OPSP_ALREADY": [tickers]}
        # [ws_subscribe_reject] logger.error / [ws_reverify] WARNING 은 individual 보존 (변경 0).
        self._ws_action_collector: dict[str, dict[str, list[str]]] = {}
        # 5분 주기 flush task handle (사이클 42 _heartbeat_metrics_loop 패턴 답습)
        self._ws_action_flush_task: asyncio.Task | None = None
        # 사이클 92 (2026-06-10) — 자동 재기동 cooldown + 슬라이딩 윈도우 cap 추적
        self._auto_restart_last_at: float = 0.0
        self._auto_restart_history: list[float] = []
        # 사이클 102 (2026-06-11) — 세션별 마지막 메시지 수신 시각 (보조 가시화)
        # 책임 분리: 종목별 ticker_last_tick (사이클 88 G-REJECT-2 영속) ↔ 세션별 _last_ws_message_at
        # 사이클 16 _aes_iv 인스턴스 변수 패턴 답습 (__init__ + _handle_raw 양쪽 영역 분리)
        self._last_ws_message_at: dict[str, datetime] = {}

        # 사이클 135 (2026-06-15) — 구독 ACK grace period (SUBSCRIBE_GRACE_SECS = 180s).
        # 사용자 결정 Q1=A 의제 채택 + Q3=A 자문 정합 + Q4=A HIGH 일관 grace.
        # domain-expert 자문 산출물 _workspace/domain_consult/cycle135_websocket_grace_period.md
        # 책임 분리 영속 (사이클 88 G-REJECT-3 5 dict 분리):
        #   _subscriptions / _subscriptions_acked / _ticker_to_session / ticker_last_tick / _subscribed_at
        # 갱신 사이트 (사이클 17 OPSP0002 ALREADY + SUBSCRIBE SUCCESS 양쪽):
        #   - SUBSCRIBE SUCCESS 분기: _subscribed_at[(tr_id, tr_key)] = now()
        #   - OPSP0002 ALREADY 분기: _subscribed_at[(tr_id, tr_key)] = now()  (자문 의제 4 영속)
        # 정리 사이트:
        #   - unsubscribe() / E2 거절 / _restore_subscriptions_after_reconnect() = pop
        # 적용 영역 영구 영속:
        #   stale_watcher_core (check_and_resubscribe_stale + resubscribe_stale_priority)
        #   첫 시세 입수 *전* (ticker_last_tick 부재) + grace 이내 = stale 판정 skip
        #   첫 시세 입수 *후* (ticker_last_tick 존재) = 기존 60s 영속 (사이클 29 005935 보호)
        self._subscribed_at: dict[tuple[str, str], datetime] = {}

    async def connect(
        self,
        on_message: Callable[[str, str, str, bool], Awaitable[None]],
    ) -> None:
        """WebSocket 연결 후 메시지 수신 루프를 시작한다.

        on_message(tr_id, tr_key, data, encrypted): 수신된 메시지 핸들러
        """
        self._on_message = on_message
        self._running = True
        self._reconnect_count = 0

        # 사이클 74 — _ws_action_flush_loop task 시작 (사이클 42 _heartbeat_metrics_loop 패턴 답습)
        # 좀비 task 방지: 기존 task 잔존 시 cancel + 새 task 발화
        if self._ws_action_flush_task and not self._ws_action_flush_task.done():
            self._ws_action_flush_task.cancel()
        self._ws_action_flush_task = asyncio.create_task(self._ws_action_metrics_loop())

        # 사이클 46 (2026-05-22, refactor-review 카드 #6) — heartbeat metrics task 폐기.
        # scheduler `_session_health_loop` 가 5분마다 모든 세션 `_heartbeat_metrics_emit_once` 호출.
        # 사이클 42 카운터 reset 정책 그대로 보존 (`_heartbeat_metrics_emit_once` 가 reset 책임).

        while self._running and self._reconnect_count <= MAX_RECONNECT:
            try:
                # 사이클 7-C — 메인이면 글로벌 매니저, 보조면 주입된 매니저
                self._approval_key = await self._token_manager.get_approval_key()
                async with websockets.connect(
                    settings.kis_ws_url,
                    ping_interval=None,
                ) as ws:
                    self._ws = ws
                    connected_at = _time.monotonic()
                    logger.info("WebSocket 연결 성공")

                    # 기존 구독 복원 + ACK set 클리어 (G1, 2026-05-12)
                    # 재연결 시 KIS 측 슬롯도 초기화되므로 모든 구독은 다시 ACK 받아야 함.
                    await self._restore_subscriptions_after_reconnect()

                    # F1 (2026-05-12) — 재연결인 경우만 검증 task 발화
                    # 첫 연결(_reconnect_count == 0) 은 정상 흐름이므로 검증 불필요.
                    # KIS silent inactive(SUBSCRIBE 응답도 시세도 안 주는 케이스) 차단용.
                    if self._reconnect_count > 0:
                        asyncio.create_task(self._verify_subscriptions_after_reconnect())

                    await self._receive_loop()

                    # 안정적 연결(MIN_STABLE_SECONDS 이상 유지)이었으면 카운트 리셋
                    if _time.monotonic() - connected_at >= MIN_STABLE_SECONDS:
                        self._reconnect_count = 0

            except (
                websockets.ConnectionClosed,
                websockets.InvalidURI,
                OSError,
            ) as e:
                self._reconnect_count += 1
                if self._reconnect_count > MAX_RECONNECT:
                    logger.error("최대 재연결 횟수 초과, 종료")
                    # 사이클 92 (2026-06-10) — 자동 재기동 트리거 (KIS 07:50 강제 중단 충돌 영구 시정)
                    # 4중 안전망 *추가* 영역 (G-REJECT-1 위반 0, 사이클 88 영속)
                    await self._trigger_auto_restart()
                    break
                wait = BACKOFF_BASE * (2 ** (self._reconnect_count - 1))
                logger.warning(
                    "WebSocket 끊김 (%s), %d/%d 재연결 대기 %.1fs",
                    e,
                    self._reconnect_count,
                    MAX_RECONNECT,
                    wait,
                )
                await asyncio.sleep(wait)

        self._ws = None

    async def disconnect(self) -> None:
        """연결을 종료한다."""
        self._running = False
        # 사이클 74 — disconnect cancel *전* 마지막 flush 1회 (Q5 옵션 A — 잔여 카운터 손실 방지)
        # 운영 환경 매일 20:00 unsubscribe_all() 직후 disconnect → 정산 *직전* 데이터 보존.
        self._flush_ws_action_collector()
        # flush task cancel + await 정리 (좀비 task 방지, 사이클 42 heartbeat task 패턴 답습)
        if self._ws_action_flush_task and not self._ws_action_flush_task.done():
            self._ws_action_flush_task.cancel()
            try:
                await self._ws_action_flush_task
            except asyncio.CancelledError:
                pass
        self._ws_action_flush_task = None
        # 사이클 46 (2026-05-22) — heartbeat metrics task lifecycle 제거.
        # scheduler `_session_health_loop` 가 통합 호출 → 본 함수에서 cancel 불필요.
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("WebSocket 연결 종료")

    async def stop(self) -> None:
        """사이클 92 (2026-06-10) — disconnect() 래퍼. idempotent 재기동 진입점.

        _trigger_auto_restart 의 stop() → start() 시퀀스에서 사용.
        disconnect() 와 동일 행위 — 기존 상태 정리 (task cancel + _ws.close()).
        """
        await self.disconnect()

    async def start(self) -> None:
        """사이클 92 (2026-06-10) — idempotent 재기동 진입점.

        _trigger_auto_restart 의 stop() → start() 시퀀스에서 사용.
        _on_message 가 등록되어 있는 경우 백그라운드 task 로 connect() 재발화.
        외부 scheduler 에서 connect() 를 직접 호출하는 경우와 구분.
        """
        if self._on_message is not None:
            asyncio.create_task(self.connect(self._on_message))

    async def _trigger_auto_restart(self) -> bool:
        """사이클 92 (2026-06-10) — MAX_RECONNECT 도달 시 자동 재기동.

        KIS 07:50 강제 중단 충돌 영구 시정. 4중 안전망 *추가* 영역 (G-REJECT-1 위반 0, 사이클 88 영속).

        영속 의무:
        - 60s cooldown (사이클 13-E-2 답습)
        - 시간당 3회 cap (사이클 24 silent_inactive 답습 + LMS chain 차단)
        - idempotent (stop() → start() 순차, 기존 상태 정리 → 정상 재시작)
        - 사이클 88 G-REJECT-1 영속 (4중 안전망 대체 X, 추가만)

        Returns:
            True = 재기동 발화 / False = cooldown 또는 cap 도달
        """
        now = _time.monotonic()

        # 60s cooldown (사이클 13-E-2 답습)
        if self._auto_restart_last_at > 0 and now - self._auto_restart_last_at < _AUTO_RESTART_COOLDOWN_SECS:
            logger.warning(
                "[ws_auto_restart_cooldown] 60s cooldown 미경과 (last=%.1fs ago)",
                now - self._auto_restart_last_at,
            )
            return False

        # 1시간 슬라이딩 윈도우 prune (사이클 24 sliding window 패턴 답습)
        self._auto_restart_history = [
            t for t in self._auto_restart_history if now - t < _AUTO_RESTART_WINDOW_SECS
        ]

        # 시간당 cap (KIS LMS chain 차단)
        if len(self._auto_restart_history) >= _AUTO_RESTART_HOURLY_CAP:
            logger.error(
                "[ws_auto_restart_cap_exceeded] 시간당 %d회 cap 도달 (KIS LMS chain 차단)",
                _AUTO_RESTART_HOURLY_CAP,
            )
            return False

        # 발화 (idempotent: stop() → start() 순차)
        self._auto_restart_last_at = now
        self._auto_restart_history.append(now)
        logger.warning("[ws_auto_restart] MAX_RECONNECT 도달 → 자동 재기동 발화 (stop → start)")

        try:
            # idempotent: 기존 상태 정리 후 정상 재시작
            await self.stop()
            await self.start()
            return True
        except Exception as e:
            logger.exception("[ws_auto_restart_failed] error=%s", e)
            return False

    async def _heartbeat_metrics_emit_once(self) -> None:
        """사이클 46 (2026-05-22, refactor-review 카드 #6) — 단발 [ws_heartbeat] emit + 카운터 reset.

        사이클 42 `_heartbeat_metrics_loop` 의 emit 로직 추출. 5분 주기 호출은 scheduler
        `_session_health_loop` 가 메인 + 보조 일괄 담당 → 좀비 task 방지 + 메인+보조 일관성.

        출력 예:
            [ws_heartbeat] label=main window=300s pingpong_recv=10
              avg_interval=30.0s last_age=15s heartbeat_timeout=0

        운영자 분석:
        - pingpong_recv 가 5분 윈도우 내 0 → ping-pong 결함
        - avg_interval 이 비정상 (예: 60s+) → KIS 측 변경 또는 네트워크 지연
        - heartbeat_timeout 누적 → 5분 윈도우 내 timeout 발생 빈도

        본체 예외는 호출자 (`scheduler._emit_heartbeat_metrics_all_sessions`) 가 격리.
        """
        from datetime import timezone as _tz, timedelta as _td
        _KST = _tz(_td(hours=9))

        now = datetime.now(_KST)
        window_secs = (now - self._pingpong_window_start_at).total_seconds()
        recv = self._pingpong_recv_count
        timeouts = self._heartbeat_timeout_count
        avg_interval = window_secs / max(recv, 1) if recv else 0.0
        last_age = (
            (now - self._pingpong_last_at).total_seconds()
            if self._pingpong_last_at else None
        )
        last_age_disp = f"{last_age:.0f}s" if last_age is not None else "none"

        logger.info(
            "[ws_heartbeat] label=%s window=%.0fs pingpong_recv=%d "
            "avg_interval=%.1fs last_age=%s heartbeat_timeout=%d",
            self._label, window_secs, recv, avg_interval,
            last_age_disp, timeouts,
        )
        # 사이클 72 hotfix A1: write_log 직접 호출 제거 — logger.info → _DbLogHandler 위임 단일 INSERT
        # 카운터 + 윈도우 시작 reset (사이클 42 정책 보존)
        self._pingpong_recv_count = 0
        self._heartbeat_timeout_count = 0
        self._pingpong_window_start_at = now

    # -- 사이클 74 옵션 E-1 — WS action aggregation --------------------------------

    def _record_action(self, tr_id: str, tr_key: str, action: str) -> None:
        """tr_id 별 action aggregation 누적 (사이클 74 옵션 E-1).

        action: "SUBSCRIBE" / "UNSUBSCRIBE" / "ACK" / "OPSP_ALREADY"
        5분 윈도우 후 `_flush_ws_action_collector` 가 `[ws_action_summary]` 1행 emit.
        [ws_subscribe_reject] ERROR / [ws_reverify] WARNING 은 individual 보존 (변경 0).
        """
        bucket = self._ws_action_collector.setdefault(tr_id, {})
        lst = bucket.setdefault(action, [])
        lst.append(tr_key)

    def _flush_ws_action_collector(self) -> None:
        """5분 윈도우 종료 시 tr_id별 누적 통계 1행 emit + collector 초기화.

        collector 비어 있으면 emit skip (no-op).
        종목 cap 20 + overflow `...+N` (사이클 28 [stale_watcher_detail] 패턴 답습).
        """
        if not self._ws_action_collector:
            return
        for tr_id, actions in self._ws_action_collector.items():
            parts: list[str] = []
            for action_name in ("SUBSCRIBE", "UNSUBSCRIBE", "ACK", "OPSP_ALREADY"):
                tickers = actions.get(action_name, [])
                if not tickers:
                    continue
                count = len(tickers)
                preview = sorted(tickers)[:20]
                overflow = max(0, count - 20)
                suffix = f"...+{overflow}" if overflow > 0 else ""
                parts.append(f"{action_name}={count} {preview}{suffix}")
            if not parts:
                continue
            logger.info(
                "[ws_action_summary] label=%s tr_id=%s window=300s %s",
                self._label, tr_id, " ".join(parts),
            )
        self._ws_action_collector.clear()

    async def _ws_action_metrics_loop(self) -> None:
        """5분 주기 ws_action collector flush (사이클 74, 사이클 42 _heartbeat_metrics_loop 패턴 답습).

        connect() 진입 직후 1회 task 시작. disconnect() 에서 cancel + await 정리.
        disconnect cancel *전* `_flush_ws_action_collector()` 1회 마지막 flush 의무 (Q5 옵션 A).
        """
        while self._running:
            await asyncio.sleep(HEARTBEAT_METRICS_INTERVAL_SECS)  # 5분 (300s)
            self._flush_ws_action_collector()

    # -- subscribe / unsubscribe / restore / verify --------------------------------



    async def subscribe(self, tr_id: str, tr_key: str, *, bypass_limit: bool = False) -> None:
        """종목 구독을 등록한다.

        bypass_limit=True 면 MAX_SUBSCRIPTIONS 한도 검사를 skip 한다 (보유 종목·익일청산 등
        HIGH 우선순위 구독에 사용 — E1, 2026-05-12). 기본 False 는 기존 분기 유지.

        사이클 17 (2026-05-19) — OPSP0002 backoff 가드.
        ``bypass_limit=False`` 이고 ``_opsp_backoff_until`` 에 등록된 키의 만료 시각이
        아직 지나지 않았으면 send 발사 skip + DEBUG ``[ws_subscribe_backoff]``.
        ``_subscriptions`` set 도 add 안 함 → 다음 자연 재시도 시 일관 동작.
        ``bypass_limit=True`` (HIGH 보유/익일청산) 는 검사 skip — 손절 우선 보장.
        """
        tr_id = _reroute_legacy_unified(tr_id, tr_key)
        if not bypass_limit:
            until = self._opsp_backoff_until.get((tr_id, tr_key), 0.0)
            now = _time.time()
            if now < until:
                logger.debug(
                    "[ws_subscribe_backoff] tr_id=%s tr_key=%s remain=%.1fs",
                    tr_id, tr_key, until - now,
                )
                return
        if not bypass_limit and len(self._subscriptions) >= MAX_SUBSCRIPTIONS:
            # 사이클 197 — WARNING DailyEmitCap (1회/키/일, KST 자기리셋). 드롭 return 불변.
            _today = datetime.now(_KST_TZ).date().isoformat()
            if _today != self._max_sub_warn_date:
                self._max_sub_warn_date = _today
                self._max_sub_warn_cap.reset_daily()
            _warn_key = (tr_id, tr_key)
            if self._max_sub_warn_cap.should_emit(_warn_key):
                logger.warning("최대 구독 수(%d) 도달, %s/%s 구독 건너뜀", MAX_SUBSCRIPTIONS, tr_id, tr_key)
                self._max_sub_warn_cap.mark_emitted(_warn_key)
            return
        self._subscriptions.add((tr_id, tr_key))
        # G1: 명시적 (재)구독 호출 시 기존 ACK 무효화 — 새 응답 대기
        self._subscriptions_acked.discard((tr_id, tr_key))
        if self._ws:
            await self._send_subscribe(tr_id, tr_key, subscribe=True)

    async def unsubscribe(self, tr_id: str, tr_key: str) -> None:
        """종목 구독을 해제한다."""
        self._subscriptions.discard((tr_id, tr_key))
        # G1: 해제 시 ACK set 에서도 동기 제거
        self._subscriptions_acked.discard((tr_id, tr_key))
        # 사이클 135 (2026-06-15) — _subscribed_at 동행 pop (G-GRACE-3 영속)
        self._subscribed_at.pop((tr_id, tr_key), None)
        if self._ws:
            await self._send_subscribe(tr_id, tr_key, subscribe=False)

    def get_subscribed_tickers(self) -> set[str]:
        """현재 TICK 구독 종목 집합을 반환한다 (세 시세 채널 합집합).

        scheduler._report_tick_coverage 가 5분 주기로 호출해 미수신 종목 카운트 노출.
        체결통보(H0STCNI0/H0STCNI9)·장운영정보(H0UNMKO0) 등 비-시세 구독은 제외.

        cycle293 — 종전에는 `tr_id == TICK_TR_ID` 등가 비교라 전용 채널
        (`H0STCNT0`/`H0NXCNT0`)로 옮긴 종목이 이 집합에서 **조용히 사라졌다**.
        그 집합은 K stale watcher · `already_in_pool` · `delta_unsubscribe_dropped`
        · `[tick_coverage]` 분모의 공통 원천이라, 빠지면 그 종목이 영영 감시 밖에
        놓이고 숫자만 좋아진다(§5-B).
        """
        # 지연 import: scanner→websocket 순환 의존 회피 (scanner에서 kis_ws 사용)
        from src.engine.scanner import TICK_TR_IDS
        return {
            tr_key for tr_id, tr_key in self._subscriptions
            if tr_id in TICK_TR_IDS and not is_probe_excluded(tr_id, tr_key)
        }

    def get_acked_tickers(self) -> set[str]:
        """KIS 정상 SUBSCRIBE SUCCESS 응답을 받은 TICK 구독만 반환 (G1, 2026-05-12).

        `get_subscribed_tickers()` 는 SEND 기준, 이 메서드는 KIS 응답 기준.
        둘의 차이가 "SEND 후 무응답" 카운트 — 운영자가 즉시 식별 가능.
        체결통보·장운영정보 등 비-TICK 구독은 동일하게 제외.
        """
        from src.engine.scanner import TICK_TR_IDS
        return {
            tr_key for tr_id, tr_key in self._subscriptions_acked
            if tr_id in TICK_TR_IDS and not is_probe_excluded(tr_id, tr_key)
        }

    async def _restore_subscriptions_after_reconnect(self) -> None:
        """재연결 직후 기존 구독을 다시 보내고 ACK set 을 비운다 (G1, 2026-05-12).

        KIS 측 슬롯이 재연결로 초기화되므로 모든 구독은 다시 ACK 받아야 한다.
        `_subscriptions` set 은 보존 — 단지 ACK 만 클리어 후 send 재전송.

        사이클 135 (2026-06-15) — 재연결 영역 = _subscribed_at.clear() 동행 (G-GRACE-8 영속).
        새 ACK 영역 영구 영속 발화 영역 영구 영속 = grace 영역 재시작 영속.
        """
        self._subscriptions_acked.clear()
        # 사이클 135 — grace 시점 초기화 (재연결 후 새 ACK 영역 영구 영속 영속)
        self._subscribed_at.clear()
        for tr_id, tr_key in list(self._subscriptions):
            await self._send_subscribe(tr_id, tr_key, subscribe=True)

    # -- private --------------------------------------------------------

    async def _verify_subscriptions_after_reconnect(self) -> None:
        """재연결 후 60초 시점에 미수신 TICK 종목 자동 재구독 (F1, 2026-05-12).

        KIS silent inactive(거절도 시세도 없음) 차단용. 1회만 시도하며,
        부족분은 다음 5분 `_scan_loop` 사이클의 unsubscribe_all + 재구독 자연 회복에 위임.

        가드:
        - `_reconnect_count == 0` (첫 연결) 이면 발화 안 함
        - `_reverify_in_progress` True 면 중첩 방지로 즉시 종료
        - 검증 도중 `_ws is None` / `_running is False` 면 조용히 종료
        - 검증 중 예외 발생 → ERROR 로그 + 플래그 해제 (다음 재연결 정상 발화)
        - `_subscriptions` set 직접 수정 금지 — `_send_subscribe` 만 호출
        """
        # 첫 연결은 검증 발화 안 함 (가드)
        if self._reconnect_count == 0:
            return
        if self._reverify_in_progress:
            return
        self._reverify_in_progress = True
        try:
            await asyncio.sleep(VERIFY_AFTER_SECS)
            if not self._running or not self._ws:
                return

            # 지연 import: scanner→websocket 순환 의존 회피
            from src.engine.scanner import TICK_TR_IDS, ticker_last_tick

            now = datetime.now(_KST_TZ)
            threshold = timedelta(seconds=VERIFY_FRESHNESS_SECS)
            # TICK 구독만 검증 대상 — 체결통보(H0STCNI0/9), 장운영정보(H0UNMKO0) 등 제외.
            # sorted 로 결정론적 순서 — preview 로그 truncate 가 일관되게 동작.
            # cycle293 — 세 채널 합집합(등가 비교 금지). 재전송 tr_id 는 아래에서
            # **그 종목이 실제로 구독된 채널**을 그대로 쓴다(리졸버의 판정이 아니라
            # 구독 사실 — 틀린 채널로 재전송하면 KIS 가 OPSP0003 를 돌려준다).
            # cycle293 Green (적대 검증 F7) — `PROBE_EXCLUDED_TUPLES` docstring 이
            # 격리 대상으로 명시한 4곳 중 F1 재검증에만 필터가 빠져 있었다.
            # 프로브는 진단 도구이므로 재연결 후 자동 재전송 대상이 아니다
            # (프로브 상태는 `GET /api/realtime/channel-probe` 가 received=False
            # 로 정직하게 알린다).
            tick_channel_of = {
                tr_key: tr_id
                for tr_id, tr_key in self._subscriptions
                if tr_id in TICK_TR_IDS and not is_probe_excluded(tr_id, tr_key)
            }
            subscribed = sorted(tick_channel_of)
            min_dt = datetime.min.replace(tzinfo=_KST_TZ)
            stale = [
                t for t in subscribed
                if (now - ticker_last_tick.get(t, min_dt)) > threshold
            ]
            if not stale:
                logger.info(
                    "[ws_reverify] 재연결 후 %ds — 미수신 종목 없음 (subscribed=%d)",
                    VERIFY_AFTER_SECS, len(subscribed),
                )
                return
            # 로그 truncate — 처음 10개만 표시 + 전체 카운트 명시
            preview = stale[:10]
            logger.warning(
                "[ws_reverify] 재연결 후 %ds — 미수신 %d종목 자동 재구독 "
                "(reconnect_count=%d, preview=%s)",
                VERIFY_AFTER_SECS, len(stale), self._reconnect_count, preview,
            )
            for ticker in stale:
                # SUBSCRIBE 메시지 1회 재전송 — _subscriptions set 은 이미 보유.
                # 거절 응답이 오면 E2 가 자동으로 _subscriptions.discard 처리.
                await self._send_subscribe(
                    tick_channel_of[ticker], ticker, subscribe=True,
                )
                # KIS Rate Limit 보호 — 짧은 sleep
                await asyncio.sleep(0.05)
        except Exception:
            logger.exception("[ws_reverify] 재연결 후 검증 실패")
        finally:
            self._reverify_in_progress = False

    async def _send_subscribe(
        self, tr_id: str, tr_key: str, *, subscribe: bool
    ) -> None:
        if not self._ws:
            return
        msg = {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": "1" if subscribe else "2",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": tr_key,
                },
            },
        }
        await self._ws.send(json.dumps(msg))
        # 사이클 74 옵션 E-1: 직접 logger.info 제거 → _record_action aggregation 흡수
        action = "SUBSCRIBE" if subscribe else "UNSUBSCRIBE"
        self._record_action(tr_id, tr_key, action)

    async def _receive_loop(self) -> None:
        """메시지 수신 루프. Heartbeat 타임아웃 감시 포함."""
        while self._running and self._ws:
            try:
                raw = await asyncio.wait_for(
                    self._ws.recv(), timeout=HEARTBEAT_TIMEOUT
                )
            except asyncio.TimeoutError:
                # 사이클 42 (2026-05-22) — heartbeat timeout 카운트 (5분 주기 통계용)
                self._heartbeat_timeout_count += 1
                logger.warning(
                    "Heartbeat 타임아웃 (%ds), 재연결 시도 — label=%s timeout_count=%d",
                    HEARTBEAT_TIMEOUT, self._label, self._heartbeat_timeout_count,
                )
                return
            except websockets.ConnectionClosed:
                logger.warning("WebSocket 연결 닫힘")
                return

            await self._handle_raw(str(raw))

    async def _handle_raw(self, raw: str) -> None:
        """수신 메시지를 파싱하여 핸들러로 전달한다."""
        # 사이클 102 (2026-06-11) — 세션별 마지막 메시지 수신 시각 갱신 (보조 가시화)
        # 사이클 68 KST 일관성 영속 (datetime.now(KST_TZ) 사용)
        self._last_ws_message_at[self._label] = datetime.now(_KST_TZ)
        # JSON 응답 (구독 확인, Heartbeat 등)
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
                header = data.get("header", {})
                body = data.get("body", {})

                # Heartbeat(PINGPONG) — 사이클 42 (2026-05-22) 가시성 강화
                tr_id = header.get("tr_id", "")
                if tr_id == "PINGPONG":
                    if self._ws:
                        # L1: PINGPONG echo 추적 (DEBUG — 운영 INFO 미노출, 폭주 방지)
                        logger.debug("[ws_pingpong_echo] label=%s", self._label)
                        await self._ws.send(raw)
                    # L2: 송수신 카운터 + 시각 갱신 (5분 주기 [ws_heartbeat] 통계용)
                    from datetime import timezone as _tz, timedelta as _td
                    _KST = _tz(_td(hours=9))
                    self._pingpong_recv_count += 1
                    self._pingpong_last_at = datetime.now(_KST)
                    return

                msg1 = body.get("msg1", "")
                rt_cd = body.get("rt_cd")
                msg_cd = body.get("msg_cd", "")
                tr_key = header.get("tr_key", "")

                # N (2026-05-12) — ALREADY IN SUBSCRIBE 가드 (거절 분기 *전*)
                # `OPSP0002 ALREADY IN SUBSCRIBE` 응답은 rt_cd=1 이지만 거절이 아니라
                # "KIS 측 이미 활성" 의미. 거절로 분류해 `_subscriptions.discard` 하면
                # 다음 `_scan_loop` 가 재구독 → 또 ALREADY → 무한 루프 + tick_coverage
                # stale 위양성 폭증 (2026-05-12 운영 사고). KIS 측 활성 의미로 받아
                # 우리 set 정합성을 회복한다.
                upper_msg1 = msg1.upper()
                already = (
                    msg_cd == "OPSP0002"
                    or "ALREADY" in upper_msg1
                    or "이미 구독" in msg1
                    or "이미 등록" in msg1
                )
                if already:
                    self._subscriptions.add((tr_id, tr_key))
                    self._subscriptions_acked.add((tr_id, tr_key))
                    # 사이클 135 (2026-06-15) — OPSP0002 ALREADY = KIS 측 이미 활성
                    # → 우리 측 grace 시점 갱신 정합 영속 (자문 의제 4 영속, G-GRACE-2).
                    # ACK 동등 처리 = _subscribed_at[(tr_id, tr_key)] = now() 갱신.
                    from datetime import timezone as _tz_g, timedelta as _td_g
                    _KST_G = _tz_g(_td_g(hours=9))
                    self._subscribed_at[(tr_id, tr_key)] = datetime.now(_KST_G)
                    # 사이클 17 (2026-05-19) — OPSP0002 backoff 등록.
                    # KIS 측 ALREADY IN SUBSCRIBE 후 다음 _scan_loop 사이클이 즉시
                    # 재구독 → 또 OPSP0002 → 무한 루프 차단 (2026-05-19 15:15 사고 대응).
                    # 사이클 17 보강 — 60s → 300s. `_scan_loop` 5분 주기 ≥ backoff 만료
                    # 보장 (KIS 공식 답변: "기등록한 사항을 재등록하지 않도록").
                    self._opsp_backoff_until[(tr_id, tr_key)] = _time.time() + 300.0
                    # 사이클 74 Q2-D 옵션 A: OPSP0002 ALREADY aggregation 흡수 (사이클 17 backoff 정책 영속)
                    # 직접 logger.info 제거 → _record_action collector 흡수 + 5분 주기 1행 emit
                    self._record_action(tr_id, tr_key, "OPSP_ALREADY")
                    return

                # 구독 거절 응답 감지 → 해당 구독 제거 (E2, 2026-05-12)
                # rt_cd != "0" / msg1 키워드(영문 ERROR/FAIL/REJECT/NOT ALLOWED/LIMIT/
                # EXCEED/DUPLICATE, 한국어 한도/초과/중복/허용되지/권한) 매칭 시
                # _subscriptions 정합성 회복 + [ws_subscribe_reject] 영구 로그.
                # 다음 5분 _scan_loop 사이클에서 E1 우선순위 큐로 자연 재시도된다.
                if _is_rejection_response(rt_cd, msg1):
                    logger.error(
                        "[ws_subscribe_reject] tr_id=%s, tr_key=%s, rt_cd=%s, msg_cd=%s, msg=%s",
                        tr_id, tr_key, rt_cd, msg_cd, msg1,
                    )
                    # 거절 난 구독을 제거 (멱등) — 재연결 시 같은 에러 반복 방지
                    self._subscriptions.discard((tr_id, tr_key))
                    # G1: ACK set 에서도 동기 discard (이전에 ACK 됐다가 재구독 후 거절 케이스)
                    self._subscriptions_acked.discard((tr_id, tr_key))
                    # 사이클 135 — E2 거절 시 _subscribed_at 동행 pop (정합성 회복 영속)
                    self._subscribed_at.pop((tr_id, tr_key), None)
                    # _DbLogHandler 위임 단일 INSERT — write_log 직접 호출 제거 (사이클 73 R-2)
                    return

                # G1 (2026-05-12) — 정상 SUBSCRIBE SUCCESS 응답 카운트 별도 추적.
                # KIS REST/WS 어디에도 슬롯 사용현황 조회 API 미존재 → 우리 측 도구로 가시화.
                # rt_cd=="0" + msg1 에 "SUBSCRIBE SUCCESS" 포함 시 _subscriptions_acked add.
                #
                # 사이클 14-C (2026-05-18) — _subscriptions 정합성 가드.
                # in-flight ACK race 차단: unsubscribe 직후 도착한 SUBSCRIBE SUCCESS ACK 는
                # _subscriptions 에 없으면 acked 에도 add 안 함 → 격차(_subscribed=0/_acked=N) 차단.
                # 2026-05-18 KST ~15:01 운영 endpoint 응답의 _main acked=30/subscribed=0 격차 대응.
                if rt_cd == "0" and "SUBSCRIBE SUCCESS" in upper_msg1:
                    if (tr_id, tr_key) in self._subscriptions:
                        self._subscriptions_acked.add((tr_id, tr_key))
                        # 사이클 135 (2026-06-15) — SUBSCRIBE SUCCESS ACK 시점
                        # _subscribed_at 갱신 (G-GRACE-1 영속). grace 영역 영구 영속 기점.
                        from datetime import timezone as _tz_ack, timedelta as _td_ack
                        _KST_ACK = _tz_ack(_td_ack(hours=9))
                        self._subscribed_at[(tr_id, tr_key)] = datetime.now(_KST_ACK)
                        # 사이클 74 옵션 E-1: 직접 logger.info 제거 → _record_action ACK 흡수
                        # "WebSocket 구독 ACK: tr_id=... tr_key=..." 직접 emit 0건 (G-7 AST 가드)
                        self._record_action(tr_id, tr_key, "ACK")
                    else:
                        logger.debug(
                            "[ws_ack_orphan] tr_id=%s tr_key=%s — _subscriptions 부재 (in-flight race ACK 무시)",
                            tr_id, tr_key,
                        )

                # 구독 성공 응답 → AES 키 저장 (체결통보용)
                # 사이클 16 (2026-05-19) — 이중 가드 추가.
                # 1) 세션 가드: 메인 세션만 모듈 전역 키 저장 (보조 세션 skip)
                # 2) tr_id 가드: 체결통보(H0STCNI0/H0STCNI9) 만 저장 (시세 SUBSCRIBE SUCCESS 덮어쓰기 차단)
                # 자체 인스턴스 변수(self.aes_iv/aes_key) 는 보존 (세션별 추적 — 디버깅용)
                output = body.get("output", {})
                if "iv" in output and "key" in output:
                    self.aes_iv = output["iv"]
                    self.aes_key = output["key"]
                    if self.is_main and tr_id in _EXECUTION_NOTICE_TR_IDS:
                        set_aes_keys(self.aes_iv, self.aes_key)
                        logger.info("AES 키 수신: tr_id=%s", tr_id)
                    else:
                        logger.debug(
                            "[aes_key_skip] tr_id=%s is_main=%s — 체결통보 외 키 무시 (사이클 16)",
                            tr_id, self.is_main,
                        )
                return
            except json.JSONDecodeError:
                pass

        # 파이프(|) 구분 실시간 데이터
        # 형식: encrypt|tr_id|count|data
        parts = raw.split("|", 3)
        if len(parts) == 4:
            encrypt_flag, tr_id, _count, payload = parts
            encrypted = encrypt_flag == "1"
            # tr_key는 payload의 첫 필드 (^ 구분, 비암호화 시)
            tr_key = ""
            if not encrypted and "^" in payload:
                tr_key = payload.split("^")[0]
            if self._on_message:
                try:
                    await self._on_message(tr_id, tr_key, payload, encrypted)
                except Exception:
                    logger.exception(
                        "WebSocket 메시지 핸들러 예외: tr_id=%s tr_key=%s encrypted=%s",
                        tr_id,
                        tr_key,
                        encrypted,
                    )


kis_ws = KisWebSocket()
