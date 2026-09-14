"""WebsocketPool — KIS WebSocket 메인 + 보조 N 세션 풀 (사이클 7-B, 2026-05-17).

배경:
- 사이클 7-A 에서 ``kis_quote_accounts`` 테이블 + multi-account 토큰 매니저 인프라 완성.
- 본 사이클은 시세 수신 핵심 변경 — 단일 ``KisWebSocket`` 인스턴스 → 멀티 세션 풀.
- 외부 호출자(scanner/risk/scheduler) 인터페이스 100% 보존 — 내부 분배 로직 캡슐화.

자금 안전 절대 원칙 (코드 가드 + 문서):
- **체결통보(H0STCNI0/H0STCNI9) → 메인 세션 단일 강제** — ``_enforce_main_only_execution_notice``
  + ``subscribe()`` 분기가 무조건 메인으로 우회.
- **매매/잔고/체결조회** — 본 사이클 변경 0 (사이클 7-A 에서 가드 명시됨, ``src/auth/CLAUDE.md``).
- **보조 세션** — 시세 only (TICK + HOGA + 예상체결). 체결통보 시도 RuntimeError.

분배 정책:
- HIGH 우선순위(보유/익일청산) → 메인 세션 절대 보장 (``bypass_limit=True``)
- LOW 우선순위(스캐닝) → 보조 세션 라운드로빈, 가득 찬 세션 건너뜀
- 보조 세션 0개 또는 모두 가득 → 메인 fallback (LOW 는 ``bypass_limit=False`` 라 메인도 가득이면 drop)
- 중복 ticker → 메인 우선. 보조에 이미 있는데 HIGH 로 들어오면 메인 승격 + 보조 unsubscribe

운영 안전 진행 — 점진 활성화:
1. 코드 배포 단계: 풀 코드 + 보조 세션 0개 (DB 미등록) → 메인 only 동작 (회귀 0)
2. 첫 보조 등록 후: DB 1개 등록 → 1 보조 세션 활성 → 41 + 41 = 82 슬롯
3. 점진 추가: DB 2~5 등록 → 풀 점진 확장
4. ``scheduler._boot()`` 재시작 시점에 보조 세션 연결 (기존 메인 흐름 유지)
"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from typing import Optional

from src.realtime.websocket import (
    MAX_SUBSCRIPTIONS,
    KisWebSocket,
    _reroute_legacy_unified,
    is_probe_excluded,
    kis_ws,
    reset_probe_exclusions,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 사이클 13-H — pool.start() first-ready await 상수
# 테스트에서 monkeypatch.setattr("src.realtime.websocket_pool.POOL_START_READY_TIMEOUT_SECS", ...)
# 로 가속 검증 가능하도록 module-level 선언 필수.
# ---------------------------------------------------------------------------
POOL_START_READY_TIMEOUT_SECS: float = 7.0
POOL_START_READY_POLL_INTERVAL_SECS: float = 0.1


# ---------------------------------------------------------------------------
# 체결통보 메인 단일 가드
# ---------------------------------------------------------------------------
class QuoteSessionExecutionNoticeError(RuntimeError):
    """보조 세션에 체결통보(H0STCNI0/H0STCNI9) 구독 시도 시 발생.

    체결통보는 영원히 메인 세션 단일. 보조 세션은 시세 수신 전용.
    """


_EXECUTION_NOTICE_TR_IDS = frozenset({"H0STCNI0", "H0STCNI9"})

#: cycle293 §9-A — 마커 2종의 1회/(ticker)/일 cap. 값은 KST 날짜 문자열이라
#: 날짜가 바뀌면 스스로 다시 열린다(새 dict·새 테이블 0). 여기에
#: `KstDailyEmitCap` 을 쓰지 않는 이유 = `src/realtime` → `src/engine` 모듈-레벨
#: import 를 새로 만들지 않는다(의존 방향 보존).
#:
#: 🔴 두 마커를 **가른 이유**(적대 검증 MEDIUM-1) — 종전에는 `subscribe()` 중복
#: 분기의 "요청 채널 거부" 와 "같은 종목이 두 채널에 동시 구독됨" 이 같은 마커
#: `[tick_channel_dual_detected]` 를 썼다. 그런데 거부는 **정상 운영 경로**에서
#: 뜬다 — `enforce` 에서 보유 종목은 `scanner` HIGH always-call 이 5분마다
#: 통합을 요청하고 현행이 전용 채널이면 거부된다(채널은 올바르게 유지된다).
#: 그 양성 발화가 §8-A S1 진행 게이트 "`[tick_channel_dual_detected]` 0건" 을
#: 달성 불가로 만들고, 운영자가 진짜 이중 구독과 구별할 수 없게 한다.
_tick_channel_denied_logged: dict[str, str] = {}
_tick_channel_dual_logged: dict[str, str] = {}


def _cap_once(store: dict, key: str) -> bool:
    """`store` 기준 1회/(key)/일 cap. True 면 발화해도 된다.

    `_kst_today_str()` 이 `""` 를 돌려주는 예외 경로에서도 **cap 이 열리지
    않는다**(적대 검증 L4 — 종전 판정식 `... == today and today` 는 그 경우
    무제한 발화였다). 날짜를 모르면 "이미 찍었다" 로 본다 — 관측 1행을
    잃는 것이 폭주보다 싸다.
    """
    today = _kst_today_str()
    if not today:
        return False
    if store.get(key) == today:
        return False
    store[key] = today
    return True


def _kst_today_str() -> str:
    """KST 날짜 문자열. 실패는 "" 로 흡수(그 경우 cap 이 열린 채로 동작)."""
    try:
        from datetime import datetime, timedelta, timezone

        return datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    except Exception:  # pragma: no cover — never-raise
        return ""


def _enforce_main_only_execution_notice(
    pool: "WebsocketPool", tr_id: str, *, session_label: str
) -> None:
    """체결통보를 메인 외 세션이 시도하면 RuntimeError raise.

    풀의 ``subscribe()`` 분기는 자동으로 메인으로 우회하지만, 외부 호출자가
    보조 세션을 직접 잡아 시도하는 케이스를 차단하는 명시 가드.
    """
    if tr_id in _EXECUTION_NOTICE_TR_IDS and session_label != "main":
        raise QuoteSessionExecutionNoticeError(
            f"체결통보는 메인 세션만 가능: tr_id={tr_id} session={session_label}"
        )


# ---------------------------------------------------------------------------
# WebsocketPool
# ---------------------------------------------------------------------------
class WebsocketPool:
    """메인 + 보조 N개 KIS WebSocket 세션 풀.

    - 메인 세션: 기존 ``kis_ws`` 인스턴스 재사용. 체결통보 + 보유/익일청산 시세.
    - 보조 세션: DB ``kis_quote_accounts`` active=true 행마다 1개. 스캐닝 시세 only.
    - 외부 호출자 인터페이스는 기존 ``KisWebSocket`` 과 동일 — ``subscribe`` /
      ``unsubscribe`` / ``unsubscribe_all`` / ``get_subscribed_tickers`` / ``start`` / ``stop`` /
      ``connect``.
    """

    def __init__(self) -> None:
        # 메인 세션은 기존 싱글톤 ``kis_ws`` 재사용 — 인스턴스 교체 시 다른 모듈
        # (handler.py / scheduler.py 등) 이 보유한 참조와 분기되는 결함 차단.
        self._main: KisWebSocket = kis_ws
        self._quotes: list[KisWebSocket] = []
        # ticker → KisWebSocket 분배 추적. unsubscribe / stale 재구독에 활용.
        self._ticker_to_session: dict[str, KisWebSocket] = {}
        # cycle293 §5-C — tr_key → 그 종목이 실제로 구독된 TICK 채널 TR_ID.
        # `_ticker_to_session` **키는 바꾸지 않는다**(C-1) — 단일 키가 곧 「같은
        # 종목 이중 채널 금지」의 구조적 강제 장치다(`ticker_last_tick` ·
        # `ticker_prices` · `tick_volume` 이 전부 ticker 단일 키이고, 두 채널이
        # 같은 종목 프레임을 주면 `record_acml_vol` last-write-wins 가 BFB/VCP
        # 거래량 게이트를 프레임 도착 순서에 좌우시킨다). 이 병행 dict 는
        # "이 종목은 어느 채널인가" 만 알려 이중 요청을 드러낸다.
        # `_market_op_subs`(제2 라우팅 dict) 선례와 같은 구조다.
        self._ticker_to_tr_id: dict[str, str] = {}
        # 라운드로빈 인덱스 (보조 세션 회전용)
        self._round_robin_idx: int = 0
        # 사이클 7-C — 보조 세션 connect task (graceful per-session 보장)
        self._quote_connect_tasks: list = []
        self._started: bool = False

    # -- 라이프사이클 (사이클 7-C) -----------------------------------------

    async def start(self, dispatch_message=None) -> None:
        """DB 활성 보조 계좌 조회 → 각 보조 KisWebSocket 인스턴스 생성 + connect.

        - 보조 세션 0개 → ``_quotes`` 빈 리스트 (메인 only 동작, 회귀 0)
        - 보조 N개 → 각 라벨별로 ``KisWebSocket`` 인스턴스 생성 → ``connect()`` task 발화
        - 보조 토큰 매니저 발급 실패 (`ValueError` 등) → 해당 세션만 skip (graceful)
        - ``dispatch_message`` 가 주어지면 보조 세션의 ``connect()`` 에 전달 (메인과 동일)
        - 같은 풀에 두 번째 호출은 noop (멱등) — 재기동 시점에 호출자가 reset 책임
        """
        if self._started:
            logger.debug("[pool_start] already started — noop")
            return
        self._started = True

        try:
            from src.db import kis_quote_accounts as kqa
            accounts = await kqa.list_accounts(active_only=True)
        except Exception:
            logger.warning("[pool_start] kis_quote_accounts 조회 실패 — 메인 only", exc_info=True)
            return

        if not accounts:
            logger.info("[pool_start] 보조 시세 계좌 0개 — 메인 only 동작")
            return

        from src.auth.token import get_token_manager

        for acct in accounts:
            label = getattr(acct, "label", None)
            if not label:
                continue
            try:
                manager = await get_token_manager(label)
            except Exception:
                logger.warning(
                    "[pool_start] 보조 토큰 매니저 발급 실패: label=%s — skip",
                    label, exc_info=True,
                )
                continue
            try:
                # 보조 세션 KisWebSocket 인스턴스 생성. token_manager 주입.
                # 사이클 16 (2026-05-19) — `is_main=False` 명시. `_handle_raw` SUBSCRIBE SUCCESS
                # AES 키 저장 가드 (메인 + 체결통보 tr_id 만 저장 — 보조는 skip).
                # 사이클 42 (2026-05-22) — label 주입 (보조 세션 [ws_heartbeat] INFO 식별)
                ws = KisWebSocket(token_manager=manager, is_main=False, label=label)
                self._quotes.append(ws)
                if dispatch_message is not None:
                    # connect 는 별도 task — 메인 흐름 차단 안 함
                    import asyncio as _asyncio
                    task = _asyncio.create_task(ws.connect(dispatch_message))
                    self._quote_connect_tasks.append(task)
                logger.info("[pool_start] 보조 세션 등록: label=%s", label)
            except Exception:
                logger.warning(
                    "[pool_start] 보조 세션 생성 실패: label=%s — skip",
                    label, exc_info=True,
                )

        # 사이클 13-H — 보조 connect first-ready await
        # 적어도 1개 보조 세션이 _ws 준비될 때까지 POOL_START_READY_TIMEOUT_SECS 까지 대기.
        # - _ws 폴링 채택: KisWebSocket.connect() 가 무한 루프(재연결+heartbeat)라
        #   task 자체는 never-complete. _ws 속성 갱신 시점이 "ready" 의 정확한 시그널.
        # - asyncio.get_event_loop().time() 사용(monotonic): 13-F freezegun 영향 없음.
        # - 예외 raise 금지: graceful 흐름 보존 — 메인 fallback 유지.
        # - _started=True 는 위에서 이미 설정됨(line 108) — timeout 시에도 _started=True 유지.
        if self._quotes and dispatch_message is not None:
            import asyncio as _asyncio
            import src.realtime.websocket_pool as _self_mod
            _timeout = _self_mod.POOL_START_READY_TIMEOUT_SECS
            _poll = _self_mod.POOL_START_READY_POLL_INTERVAL_SECS
            _start_t = _asyncio.get_event_loop().time()
            while True:
                _elapsed = _asyncio.get_event_loop().time() - _start_t
                if _elapsed >= _timeout:
                    # timeout
                    _ready_count = sum(
                        1 for q in self._quotes
                        if getattr(q, "_ws", None) is not None
                    )
                    logger.warning(
                        "[pool_start_ready_timeout] ready=%d/%d timeout=%.1fs — 메인 fallback 활성",
                        _ready_count, len(self._quotes), _timeout,
                    )
                    break
                _ready_count = sum(
                    1 for q in self._quotes
                    if getattr(q, "_ws", None) is not None
                )
                if _ready_count >= 1:
                    logger.info(
                        "[pool_start_ready] ready=%d/%d elapsed=%.2fs",
                        _ready_count, len(self._quotes), _elapsed,
                    )
                    break
                await _asyncio.sleep(_poll)

        logger.info(
            "[pool_start] 완료: main=1 quotes=%d total_slots=%d",
            len(self._quotes), MAX_SUBSCRIPTIONS * (1 + len(self._quotes)),
        )

    async def stop(self) -> None:
        """모든 보조 세션 disconnect + connect task cancel.

        메인 세션은 호출자(scheduler) 책임으로 별도 disconnect — 본 메서드는
        보조만 정리. 풀의 ``_started`` flag 재설정해 다음 ``start()`` 호출 시 재초기화.
        """
        for task in self._quote_connect_tasks:
            try:
                task.cancel()
            except Exception:
                pass
        self._quote_connect_tasks.clear()

        for ws in self._quotes:
            try:
                await ws.disconnect()
            except Exception:
                logger.debug("[pool_stop] 보조 세션 disconnect 실패", exc_info=True)
        self._quotes.clear()
        self._ticker_to_session.clear()
        self._ticker_to_tr_id.clear()
        # cycle293 Green — 프로브 제외 등록도 함께 회수한다. 남기면 그 튜플이
        # 라이브 구독과 **같은 식별자**라 다음 사이클의 실 구독을 은폐한다.
        reset_probe_exclusions()
        self._started = False

    # -- 세션 분배 --------------------------------------------------------

    def _select_session(self, ticker: str, *, priority: str) -> KisWebSocket:
        """티커 → 세션 결정.

        - HIGH: 메인 세션 절대 보장.
        - LOW : 보조 세션 라운드로빈 (가득 / disconnect 세션 건너뜀). 가용 없으면 메인 fallback.
        """
        if priority == "HIGH":
            return self._main

        # 보조 세션 후보 — 가득 차지 않고 disconnect 아닌 세션
        candidates = self._available_quotes()
        if not candidates:
            return self._main

        # 라운드로빈: 후보 안에서 다음 세션
        chosen = candidates[self._round_robin_idx % len(candidates)]
        self._round_robin_idx += 1
        return chosen

    def _available_quotes(self) -> list[KisWebSocket]:
        """슬롯 잔여 + WebSocket 연결 살아있는 보조 세션 리스트.

        - ``_ws is None`` (disconnect / 첫 연결 전) 은 제외 — 다음 ``_scan_loop`` 자연 회복 위임.
          (`_ws` 가 None 이어도 ``subscribe`` 자체는 가능하지만, 즉시 전송이 안 되므로 안전 제외)
        - ``_subscriptions`` 가 ``MAX_SUBSCRIPTIONS`` 도달한 세션도 제외.
        """
        return [
            q for q in self._quotes
            if getattr(q, "_ws", None) is not None
            and len(q._subscriptions) < MAX_SUBSCRIPTIONS
        ]

    def _session_label(self, ws: KisWebSocket) -> str:
        """세션 → label ("main" / DB 라벨 — 사이클 43 통일).

        사이클 43 (2026-05-22): 1-based index ("quote-1"/"quote-2") → DB 라벨 (ISA/sub/gold).
        보조 세션은 생성 시 pool 이 `KisWebSocket(label=label)` 주입 (사이클 42).
        풀에 등록된 보조 세션 인스턴스가 맞으면 `ws._label` 반환, 아니면 "unknown".

        디버깅 / 로그용. 메인은 동일성 비교(``is``).
        호환: `[tick_coverage_session]` / `[stale_watcher_detail]` / `[priority_drop_pool]` /
        `/api/realtime/subscriptions` / `KisAccountPoolCard` 자동 동기.
        """
        if ws is self._main:
            return "main"
        for q in self._quotes:
            if ws is q:
                # 사이클 43 — `ws._label` 직접 반환 (DB 라벨)
                # graceful — `_label` 미설정 시 빈 문자열 폴백 차단 (legacy 호환)
                return getattr(q, "_label", "") or "unknown"
        return "unknown"

    # -- subscribe / unsubscribe ----------------------------------------

    async def subscribe(
        self,
        tr_id: str,
        tr_key: str,
        *,
        priority: str = "LOW",
        bypass_limit: bool = False,
    ) -> Optional[str]:
        """tr_key(ticker) 를 적절한 세션에 분배 후 구독.

        Args:
            tr_id: KIS TR_ID. ``H0STCNI0/H0STCNI9`` 면 priority 무시 메인 강제.
            tr_key: 구독 키 (ticker / HTS ID / 계좌번호).
            priority: ``"HIGH"`` (보유/익일청산) | ``"LOW"`` (스캐닝/기본).
            bypass_limit: 외부 호환용. HIGH 이면 무조건 True 로 격상 (보유 시세 절대 보장).

        Returns:
            사용된 세션 label (``"main"`` / ``"quote-N"``). drop 발생 시 ``None``.
        """
        # 🔴 cycle294 적대 검증 HIGH-1(부팅) 시정 — 세션의 `subscribe` 첫 문장이
        #    레거시 통합 요청을 전용 채널로 되돌리는데(`_reroute_legacy_unified`),
        #    그 재라우팅은 **세션 안에서** 일어나 호출자의 지역 변수를 못 바꾼다.
        #    그래서 풀은 재라우팅 **전** 값을 `_ticker_to_tr_id` 에 적어 왔고,
        #    이후 `unsubscribe`(자기 교정) · `switch_channel_same_session`(old_tr_id) ·
        #    `stale_watcher_core._actual_or_desired_tick_tr_id` 가 전부 틀린 채널을
        #    봤다 — 실측: 존재하지 않는 튜플에 UNSUBSCRIBE 를 보내 KIS `OPSP0003`
        #    을 받고 진짜 튜플은 영구 고아가 된다. 진입에서 한 번 적용하면 아래
        #    모든 기록이 **실제로 구독되는 채널**과 같아진다(재라우팅은 멱등이라
        #    세션 안 호출은 no-op 이 된다).
        tr_id = _reroute_legacy_unified(tr_id, tr_key)

        # 1) 체결통보 메인 강제 — priority 무시
        if tr_id in _EXECUTION_NOTICE_TR_IDS:
            await self._main.subscribe(tr_id, tr_key, bypass_limit=True)
            self._ticker_to_session[tr_key] = self._main
            self._ticker_to_tr_id[tr_key] = tr_id
            return "main"

        # 2) 중복 ticker 처리
        existing = self._ticker_to_session.get(tr_key)
        if existing is not None:
            # cycle293 §5-C — 같은 종목에 **다른 채널** 요청이 오면 무음 통과시키지
            # 않는다. 현행 중복 분기는 `tr_id` 를 보지 않아 SEND 없이 성공을
            # 반환했고(cycle221 이 종목별 VI 구독에서 정확히 이 함정을 밟아 "실질
            # noop" 이 됐다), 그래서 `scheduler.py` 의 풀 우회 직접 구독 2곳
            # (`:1382` 익일청산 시가 · `:2728` 매수 직후)이 만드는 이중 채널이
            # 아무 흔적도 남기지 않았다. **요청 채널을 버리고 현행 채널을
            # 유지**하되(전환 금지 — §3-C) 승격(promote)은 그대로 진행한다:
            # 채널을 거부하는 것이 HIGH 보장을 거부하는 것이 되면 안 된다.
            existing_tr_id = self._ticker_to_tr_id.get(tr_key)
            if existing_tr_id is not None and existing_tr_id != tr_id:
                self._emit_tick_channel_request_denied(tr_key, existing_tr_id, tr_id)
                if is_probe_excluded(existing_tr_id, tr_key):
                    # 기존 것이 **진단 프로브**(cycle253)면 라이브 구독을 그 채널로
                    # 끌고 가지 않는다 — ≤15분 살다 DELETE 되는 도구가 그 종목의
                    # 라이브 채널을 정하면 안 된다. 라우팅의 주인은 라이브다.
                    self._ticker_to_tr_id[tr_key] = tr_id
                else:
                    tr_id = existing_tr_id
            elif existing_tr_id is None:
                # 추적 공백(부팅 전 구독·구버전 상태) — 최선의 정보로 채운다.
                self._ticker_to_tr_id[tr_key] = tr_id
            # 메인에 이미 있는데 LOW 로 들어옴 → 그대로 메인 사용
            if existing is self._main:
                return "main"
            # 보조에 있는데 HIGH 로 승격 — 보조 unsubscribe 후 메인 등록
            if priority == "HIGH":
                logger.info(
                    "[pool_promote] ticker=%s old=%s new=main",
                    tr_key, self._session_label(existing),
                )
                try:
                    await existing.unsubscribe(tr_id, tr_key)
                except Exception:
                    # 보조 unsubscribe 실패해도 메인 승격은 계속 — graceful
                    logger.debug("[pool_promote] 보조 unsubscribe 실패", exc_info=True)
                await self._main.subscribe(tr_id, tr_key, bypass_limit=True)
                self._ticker_to_session[tr_key] = self._main
                self._ticker_to_tr_id[tr_key] = tr_id
                return "main"
            # 보조에 있는데 LOW 로 또 들어옴 → 그대로 유지 (noop)
            return self._session_label(existing)

        # 3) HIGH 우선순위 — 메인 절대 보장 + bypass_limit=True
        if priority == "HIGH":
            await self._main.subscribe(tr_id, tr_key, bypass_limit=True)
            self._ticker_to_session[tr_key] = self._main
            self._ticker_to_tr_id[tr_key] = tr_id
            return "main"

        # 4) LOW — 보조 라운드로빈, 가용 없으면 메인 fallback
        chosen = self._select_session(tr_key, priority="LOW")
        # 메인 fallback 이면서 메인이 가득이면 drop
        if chosen is self._main and len(self._main._subscriptions) >= MAX_SUBSCRIPTIONS:
            logger.info(
                "[priority_drop_pool] tr_key=%s priority=LOW reason=all_sessions_full "
                "main=%d/%d quotes=%d",
                tr_key, len(self._main._subscriptions), MAX_SUBSCRIPTIONS, len(self._quotes),
            )
            return None

        # 보조 세션 선택이지만 슬롯 가득 (라운드로빈이 모두 가득인 경우)
        if chosen is not self._main and len(chosen._subscriptions) >= MAX_SUBSCRIPTIONS:
            # 마지막 안전망 — 메인 fallback 시도
            if len(self._main._subscriptions) < MAX_SUBSCRIPTIONS:
                chosen = self._main
            else:
                logger.info(
                    "[priority_drop_pool] tr_key=%s priority=LOW reason=all_sessions_full",
                    tr_key,
                )
                return None

        await chosen.subscribe(tr_id, tr_key, bypass_limit=bypass_limit)
        self._ticker_to_session[tr_key] = chosen
        self._ticker_to_tr_id[tr_key] = tr_id
        return self._session_label(chosen)

    def _emit_tick_channel_request_denied(
        self, tr_key: str, existing_tr_id: str, requested_tr_id: str,
    ) -> None:
        """`[tick_channel_request_denied]` — 다른 채널 요청을 **거부**했다 (1회/ticker/일).

        이것은 이중 구독이 아니다 — 현행 채널을 유지했다는 기록이다(§3-C 장중 전환
        금지). 정상 운영에서도 뜬다: `enforce` 에서 보유 종목의 HIGH always-call 이
        5분마다 통합을 요청하고 현행이 전용 채널이면 여기로 온다. **진짜 이중
        구독은 `[tick_channel_dual_detected]` 가 따로 센다**(전 세션 전수 대조).
        """
        try:
            if not _cap_once(_tick_channel_denied_logged, tr_key):
                return
            caller = "unknown"
            try:
                import sys as _sys

                frame = _sys._getframe(2)
                fname = frame.f_code.co_filename.rsplit("/", 1)[-1]
                caller = f"{fname}:{frame.f_lineno}"
            except Exception:
                pass
            # cycle293 마커는 완성된 문자열로 남긴다(회귀 가드가 `record.args`
            # 가 빈 것을 전제로 `record.message` 를 직접 읽는다).
            logger.warning(
                f"[tick_channel_request_denied] ticker={tr_key} "
                f"existing={existing_tr_id} requested={requested_tr_id} caller={caller}"
            )
        except Exception:  # pragma: no cover — never-raise (관측이 구독을 막지 않는다)
            logger.debug("[tick_channel_request_denied] emit 실패", exc_info=True)

    def detect_dual_tick_channels(self) -> dict[str, list[str]]:
        """🔴 같은 종목이 **두 TICK 채널에 동시 구독**돼 있는지 전 세션에서 센다.

        ## 왜 `subscribe()` 중복 분기가 아니라 여기인가 (적대 검증 CRITICAL)

        §4-C 가 이 관측에 맡긴 임무는 **풀을 우회하는 직접 구독 2곳**
        (`scheduler.py:1382` 익일청산 시가 수신 · `:2728` 스윙 매수 직후 — 둘 다
        `kis_ws.subscribe(...)` 단일 세션 직접)을 드러내는 것이다. 그 두 줄은
        `_ticker_to_session` 을 **건드리지 않으므로** `subscribe()` 의 중복 분기에
        영원히 도달하지 못한다 — 종전 구현은 자기가 지킨다고 적은 것을 지키지
        못했다(실증: 풀 구독 뒤 `kis_ws.subscribe` 우회로 튜플 2개가 생겼는데
        WARNING 0행).

        그래서 판정 근거를 **구독 사실**로 옮긴다: 전 세션의 `_subscriptions` 를
        훑어 같은 `tr_key` 에 TICK tr_id 가 2개 이상이면 발화한다. 프로브 튜플은
        제외한다(진단 도구가 이중 채널로 잡히면 §7 측정이 못 돌아간다).

        Returns: `{ticker: [tr_id, ...]}` — 이중인 종목만. 정상 상태는 빈 dict.
        """
        found: dict[str, list[str]] = {}
        try:
            from src.engine.scanner import TICK_TR_IDS

            by_ticker: dict[str, set[str]] = {}
            for ws in [self._main, *self._quotes]:
                try:
                    subs = getattr(ws, "_subscriptions", None) or set()
                except Exception:
                    continue
                for tr_id, tr_key in set(subs):
                    if tr_id not in TICK_TR_IDS:
                        continue
                    if is_probe_excluded(tr_id, tr_key):
                        continue
                    by_ticker.setdefault(tr_key, set()).add(tr_id)
            for tr_key, channels in by_ticker.items():
                if len(channels) < 2:
                    continue
                found[tr_key] = sorted(channels)
                if not _cap_once(_tick_channel_dual_logged, tr_key):
                    continue
                tracked = self._ticker_to_tr_id.get(tr_key, "-")
                logger.warning(
                    f"[tick_channel_dual_detected] ticker={tr_key} "
                    f"channels={sorted(channels)} tracked={tracked} "
                    f"source=session_scan"
                )
        except Exception:  # pragma: no cover — never-raise (관측이 구독을 막지 않는다)
            logger.debug("[tick_channel_dual_detected] 전수 대조 실패", exc_info=True)
        return found

    def session_of(self, tr_key: str):
        """그 종목을 담당하는 세션 (없으면 `None`) — 읽기 전용 접근자.

        cycle294 §4-D — 전환은 **세션 안 채널 교체**다. 호출자가
        `_ticker_to_session` 을 직접 만지지 않게 한다.
        """
        return self._ticker_to_session.get(tr_key)

    async def switch_channel_same_session(
        self,
        tr_key: str,
        new_tr_id: str,
        *,
        make_before_break: bool = True,
        ack_timeout_secs: float = 5.0,
        poll_interval: float = 0.2,
    ) -> str:
        """cycle294 §4-C — 살아 있는 구독의 **채널만** 바꾼다. 세션은 그대로.

        Returns: ``"switched"`` / ``"switched_orphan"``(구 채널 해제 실패) /
        ``"ack_timeout"`` / ``"noop"`` / ``"no_route"`` / ``"low_drop"``.

        ## 🔴 HIGH 는 make-before-break (절대 규칙 2)

        S2 신 채널 등록 → S3 **ACK 확인**(`_subscriptions` ∧ `_subscriptions_acked`
        2집합) → S5 구 채널 해제 → S6 병행 dict 갱신. `_subscriptions` 만 보면
        SEND 직후 무응답을 성공으로 읽고 구 채널을 끊는다(cycle14-C 가
        `_subscribed=0/_acked=N` 격차로 잡은 그 계열). ACK 실패는 **신 채널만
        즉시 회수**하고 구 채널을 유지한다 — 그 종목의 blind 구간은 0 이다.

        LOW 는 break-before-make — 전환 창에 잃을 프레임이 없고, 슬롯·SEND 를
        아끼며 실패해도 다음 사이클이 재시도한다.

        ## 🔴 세션 재추첨 금지 (§4-D)

        `unsubscribe` 는 `_ticker_to_session` 이 가리키는 **한 세션**만 본다. 신규
        구독을 라운드로빈으로 다른 세션에 떨어뜨리면 그 dict 가 덮이고 구 채널
        해제가 새 세션에서 `(old, tr_key)` 를 찾다 실패해 **구 세션 튜플이 영구
        고아**로 41 슬롯을 잠식한다(cycle253 프로브가 밟은 그 함정). 그래서 이
        메서드는 세션을 고르지 않는다 — `_ticker_to_session` 은 **읽기만** 한다.
        """
        old_tr_id = self._ticker_to_tr_id.get(tr_key)
        if not old_tr_id or old_tr_id == new_tr_id:
            return "noop"
        session = self._ticker_to_session.get(tr_key)
        if session is None:
            return "no_route"
        if make_before_break:
            await session.subscribe(new_tr_id, tr_key, bypass_limit=True)
            acked = False
            deadline = _time.monotonic() + max(0.0, float(ack_timeout_secs))
            while True:
                subs = getattr(session, "_subscriptions", None) or set()
                acked_set = getattr(session, "_subscriptions_acked", None) or set()
                if (new_tr_id, tr_key) in subs and (new_tr_id, tr_key) in acked_set:
                    acked = True
                    break
                if _time.monotonic() >= deadline:
                    break
                await asyncio.sleep(poll_interval)
            if not acked:
                # S4 — 고아 튜플 즉시 회수. 구 채널은 **건드리지 않는다**.
                try:
                    await session.unsubscribe(new_tr_id, tr_key)
                except Exception:
                    logger.debug("[tick_channel_switch] 고아 회수 실패", exc_info=True)
                return "ack_timeout"
            try:
                await session.unsubscribe(old_tr_id, tr_key)
            except Exception:
                logger.debug("[tick_channel_switch] 구 채널 해제 실패", exc_info=True)
                # 🔴 적대 검증 MEDIUM-2 시정 — `KisWebSocket.unsubscribe` 는
                # `_subscriptions.discard` 를 **먼저** 하고 SEND 하므로, SEND 가
                # 실패하면 KIS 쪽 구독은 살아 있는데 로컬 집합에서는 사라진다.
                # 그러면 20:00 `unsubscribe_all()`(로컬 튜플 전수 순회)이 그것을
                # 회수하지 못해 **영구 고아**가 되고 41 슬롯을 잠식하며, 두 채널
                # 프레임이 동시에 들어와도 `detect_dual_tick_channels` 가 못 본다.
                # 튜플을 되돌려 놓아 회수 경로와 이중 채널 탐지를 모두 살린다.
                try:
                    subs = getattr(session, "_subscriptions", None)
                    if isinstance(subs, set):
                        subs.add((old_tr_id, tr_key))
                except Exception:
                    pass
                self._ticker_to_tr_id[tr_key] = new_tr_id
                return "switched_orphan"
            self._ticker_to_tr_id[tr_key] = new_tr_id
            return "switched"
        try:
            await session.unsubscribe(old_tr_id, tr_key)
        except Exception:
            logger.debug("[tick_channel_switch] LOW 구 채널 해제 실패", exc_info=True)
            self._release_switch_routing(tr_key, old_tr_id, stage="unsub")
            return "low_drop"
        await session.subscribe(new_tr_id, tr_key, bypass_limit=False)
        live = getattr(session, "_subscriptions", None) or set()
        if (new_tr_id, tr_key) not in live:
            self._release_switch_routing(tr_key, new_tr_id, stage="sub")
            return "low_drop"
        self._ticker_to_tr_id[tr_key] = new_tr_id
        return "switched"

    def _release_switch_routing(self, tr_key: str, tr_id: str, *, stage: str) -> None:
        """🔴 적대 검증 HIGH-1 시정 — LOW 전환 실패 시 **라우팅을 비운다**.

        종전에는 실패해도 `_ticker_to_session`/`_ticker_to_tr_id` 를 그대로 뒀다.
        그러면 그 종목은 세션에 튜플이 0개인데 풀은 "구독돼 있다" 고 믿는 상태가
        되어 (a) `get_subscribed_tickers()` 에서 빠져 K stale watcher 가 영원히
        못 보고 (b) `delta_unsubscribe_dropped` 의 정리 대상도 아니며 (c) 다음
        `subscribe_filtered_stocks` 가 중복 분기(`existing is not None`)에서 SEND
        없이 조기 반환한다 ⇒ 20:00 `unsubscribe_all()` 또는 프로세스 재시작까지
        **자가 치유 경로가 없다**. 기존 `unsubscribe_in_pool` 은 두 dict 를 모두
        pop 해 다음 사이클이 재분배하도록 해 왔다 — 신규 경로만 그 관례를 안
        따랐다. 라우팅을 비우면 다음 5분 사이클의 재구독이 되살린다.
        """
        try:
            self._ticker_to_session.pop(tr_key, None)
            self._ticker_to_tr_id.pop(tr_key, None)
            logger.warning(
                "[tick_channel_switch_failed] ticker=%s stage=low_%s tr_id=%s "
                "routing=released", tr_key, stage, tr_id,
            )
        except Exception:  # pragma: no cover — never-raise
            pass

    async def unsubscribe(self, tr_id: str, tr_key: str) -> None:
        """분배 추적된 세션에서 unsubscribe. 기록 없으면 noop (다음 _scan_loop 자연 정리).

        체결통보(H0STCNI0/H0STCNI9) 는 항상 메인 — 명시적으로 메인에서 해제.
        """
        if tr_id in _EXECUTION_NOTICE_TR_IDS:
            await self._main.unsubscribe(tr_id, tr_key)
            self._ticker_to_session.pop(tr_key, None)
            self._ticker_to_tr_id.pop(tr_key, None)
            return

        chosen = self._ticker_to_session.pop(tr_key, None)
        tracked_tr_id = self._ticker_to_tr_id.pop(tr_key, None)
        if chosen is None:
            return
        # cycle293 — 호출자가 리졸버의 **현재** 판정을 넘겼는데 그 종목이 실제로는
        # 다른 채널에 구독돼 있을 수 있다(모드를 장중에 바꾼 뒤 매도가 나가는 경우).
        # 틀린 채널로 UNSUBSCRIBE 를 보내면 KIS 가 `OPSP0003 not found!` 를 돌려주고
        # (cycle215~218 이 잡은 그 ERROR) 구 채널 튜플은 **영구 고아**로 41 슬롯을
        # 잠식한다. 실제 구독 사실이 요청보다 우선이다.
        if tracked_tr_id is not None and tracked_tr_id != tr_id:
            logger.debug(
                "[pool_unsubscribe] 채널 자기 교정 tr_key=%s requested=%s actual=%s",
                tr_key, tr_id, tracked_tr_id,
            )
            tr_id = tracked_tr_id
        try:
            await chosen.unsubscribe(tr_id, tr_key)
        except Exception:
            logger.debug("[pool_unsubscribe] 세션 unsubscribe 실패", exc_info=True)

    async def unsubscribe_all(self) -> None:
        """모든 세션의 모든 구독 해제 + 분배 추적 dict clear."""
        # 분배 추적 기반 unsubscribe — 메인 + 보조 모두 커버
        for tr_key, ws in list(self._ticker_to_session.items()):
            try:
                # tr_id 를 가정하지 않는다 — `ws._subscriptions` 에서 tr_key 로
                # 매칭되는 `(tr_id, tr_key)` 튜플을 **전수** 찾아 해제한다. 그래서
                # 세 시세 채널 어느 것이든, 그리고 체결통보·장운영정보가 섞여
                # 들어와도 실제 구독된 튜플만 정확히 해제된다(cycle293 — 종전
                # 주석의 "tr_id 는 TICK_TR_ID 가정" 은 코드 실제와 달랐다).
                matches = [
                    (tid, tk) for tid, tk in ws._subscriptions if tk == tr_key
                ]
                for tid, tk in matches:
                    await ws.unsubscribe(tid, tk)
            except Exception:
                logger.debug("[pool_unsubscribe_all] %s 해제 실패", tr_key, exc_info=True)
        self._ticker_to_session.clear()
        self._ticker_to_tr_id.clear()
        # 20:00 `TIME_NXT_POST_CLOSE` — 프로브 튜플도 여기서 죽으므로 제외
        # 등록을 함께 회수한다(cycle293 Green: 수명 주석과 코드를 일치시킨다).
        reset_probe_exclusions()

    async def resend_subscribe_for_ticker(self, tr_id: str, tr_key: str) -> None:
        """K stale watcher 헬퍼 — 분배 추적된 세션에서 ``_send_subscribe`` 재전송.

        ``_subscriptions`` set 은 보존 — KIS silent inactive 회복용.
        추적 없는 ticker 는 메인 fallback (안전 디폴트).
        """
        chosen = self._ticker_to_session.get(tr_key, self._main)
        try:
            await chosen._send_subscribe(tr_id, tr_key, subscribe=True)
        except Exception:
            logger.debug("[pool_resend_subscribe] 실패: %s", tr_key, exc_info=True)

    async def unsubscribe_in_pool(self, tr_id: str, tr_key: str) -> None:
        """K stale watcher 헬퍼 — 분배 추적된 세션에서 강제 unsubscribe (재등록 전 정리).

        ``_ticker_to_session`` 추적 dict 에서도 제거 — 이어지는 ``subscribe`` 가
        새로 분배할 수 있게 한다. ``unsubscribe`` 와 분리한 이유: 강제 재등록 시점에는
        ticker 가 다른 세션으로 라운드로빈 될 수 있음을 명시.
        """
        chosen = self._ticker_to_session.pop(tr_key, None)
        tracked_tr_id = self._ticker_to_tr_id.pop(tr_key, None)
        if chosen is None:
            # 추적 없는 ticker — 메인에서 시도 (안전 디폴트)
            chosen = self._main
        if tracked_tr_id is not None and tracked_tr_id != tr_id:
            tr_id = tracked_tr_id
        try:
            await chosen.unsubscribe(tr_id, tr_key)
        except Exception:
            logger.debug("[pool_unsubscribe_in_pool] 실패: %s", tr_key, exc_info=True)

    async def disable_quote_session(self, label: str) -> None:
        """보조 세션 1개를 풀에서 제거 — 사이클 9 (2026-05-18) 자동 비활성용.

        호출자: ``src.services.quote_session_health.QuoteSessionHealthMonitor``
        가 5회 연속 실패 / 5분 50% 실패율 감지 시 호출.

        흐름:
        1. label → ``_quotes`` 인덱스 매칭 (``quote-N`` 1-based)
        2. 해당 세션 ``disconnect()`` (예외 swallow)
        3. ``_quotes`` 에서 제거
        4. ``_ticker_to_session`` 에서 해당 세션 담당 ticker 모두 제거

        안전 가드:
        - 메인 라벨 (``"main"``) → noop. 메인 세션은 자동 비활성 절대 금지.
        - 없는 label → noop (idempotent — 두 번째 호출 안전)

        다음 ``subscribe`` 호출은 자동 라운드로빈으로 남은 보조 또는 메인 fallback.
        """
        if label == "main":
            # 메인 세션 자동 비활성 절대 금지 — 안전 가드
            logger.debug("[pool_disable] 메인 라벨 noop")
            return

        # 사이클 43 (2026-05-22) — 1-based index ("quote-N") → DB 라벨 매칭.
        # 보조 세션 생성 시 `_label` 주입 (사이클 42). label 일치 보조 세션 검색.
        target = None
        target_idx = -1
        for idx, q in enumerate(self._quotes):
            if getattr(q, "_label", None) == label:
                target = q
                target_idx = idx
                break

        if target is None:
            # 없는 라벨 — idempotent noop (두 번째 호출 안전)
            logger.debug("[pool_disable] %s 이미 제거됨 또는 미존재 (quotes=%d)",
                         label, len(self._quotes))
            return

        # 해당 세션 담당 ticker 정리
        for tr_key in list(self._ticker_to_session.keys()):
            if self._ticker_to_session[tr_key] is target:
                del self._ticker_to_session[tr_key]
                self._ticker_to_tr_id.pop(tr_key, None)

        # disconnect — 예외 swallow (정합성 유지)
        try:
            await target.disconnect()
        except Exception:
            logger.debug("[pool_disable] disconnect 실패: %s", label, exc_info=True)

        # _quotes 에서 제거 — 라운드로빈 idx 도 보수적 reset
        # 사이클 43 — target_idx (label 매칭 후 찾은 인덱스)
        del self._quotes[target_idx]
        self._round_robin_idx = 0

        logger.info("[pool_disable] %s 비활성 완료 — quotes=%d", label, len(self._quotes))

    # -- 통합 조회 / 진단 -----------------------------------------------

    def get_subscribed_tickers(self) -> set[str]:
        """메인 + 보조 모든 세션의 TICK 구독 합집합 (Phase D 호환 인터페이스).

        cycle293 — 세 채널 합집합(등가 비교 금지, §5-B). 진단 프로브 튜플은
        `PROBE_EXCLUDED_TUPLES`(프로브 정체성 기준)로만 빠진다 — 채널 기준 격리는
        전용 채널이 실 구독에 쓰이는 순간 성립하지 않는다.
        """
        # 지연 import — scanner 가 websocket_pool 참조 가능성 차단
        from src.engine.scanner import TICK_TR_IDS

        result: set[str] = set()
        for ws in [self._main, *self._quotes]:
            for tr_id, tr_key in ws._subscriptions:
                if tr_id in TICK_TR_IDS and not is_probe_excluded(tr_id, tr_key):
                    result.add(tr_key)
        return result

    def get_acked_tickers(self) -> set[str]:
        """메인 + 보조 모든 세션의 ACK 받은 TICK 구독 합집합."""
        from src.engine.scanner import TICK_TR_IDS

        result: set[str] = set()
        for ws in [self._main, *self._quotes]:
            for tr_id, tr_key in ws._subscriptions_acked:
                if tr_id in TICK_TR_IDS and not is_probe_excluded(tr_id, tr_key):
                    result.add(tr_key)
        return result

    def get_subscriptions_by_session(self) -> dict[str, set[str]]:
        """label → set[ticker] 역인덱싱 (사이클 28, 2026-05-21).

        ``_ticker_to_session`` 역방향 — 세션별 stale 분포 추적 / 진단 로그 강화 용.
        신규 영속 dict 추가 *없음* (호출 시 그때그때 계산).

        규칙:
        - 메인 세션은 항상 "main" 라벨
        - 보조 세션은 ``_quotes`` 인덱스 기반 "quote-N" (1-based)
        - 매핑된 세션 객체가 풀(``_main``/``_quotes``)에서 사라진 경우 "unknown" 라벨로 묶음
          (race / disable_quote_session 잔재 대응)
        - 매핑 0건 → 빈 dict
        """
        result: dict[str, set[str]] = {}
        for ticker, ws in self._ticker_to_session.items():
            label = self._session_label(ws)
            result.setdefault(label, set()).add(ticker)
        return result

    def get_session_status(self) -> list[dict]:
        """세션별 슬롯 상태 dict 리스트. ``/api/realtime/subscriptions`` 응답에 동봉.

        사이클 43 (2026-05-22) — 라벨 통일: 1-based index ("quote-N") → DB 라벨 (ISA/sub/gold).
        보조 세션 `KisWebSocket.__init__(label=...)` 주입값 직접 반환.
        """
        from src.engine.scanner import TICK_TR_IDS

        # 사이클 43 — 보조 세션 label = ws._label (DB 라벨). graceful 폴백 "unknown".
        sessions = []
        for ws, label in [(self._main, "main")] + [
            (q, getattr(q, "_label", "") or "unknown") for q in self._quotes
        ]:
            # cycle293 — 세 채널 합집합. 등가 비교를 남기면 전용 채널 20종목을
            # 가진 세션이 대시보드에 `sub=0/41` 로 보여 운영자가 슬롯을 못 읽는다.
            subscribed = {
                tr_key for tr_id, tr_key in ws._subscriptions
                if tr_id in TICK_TR_IDS and not is_probe_excluded(tr_id, tr_key)
            }
            acked = {
                tr_key for tr_id, tr_key in ws._subscriptions_acked
                if tr_id in TICK_TR_IDS and not is_probe_excluded(tr_id, tr_key)
            }
            sessions.append({
                "label": label,
                "subscribed": len(subscribed),
                "acked": len(acked),
                "limit": MAX_SUBSCRIPTIONS,
                "ws_connected": getattr(ws, "_ws", None) is not None,
                "reconnect_count": getattr(ws, "_reconnect_count", 0),
                # 진단용 sorted ticker 리스트 (라우트에서 사용)
                "tickers": {
                    "subscribed": sorted(subscribed),
                    "acked": sorted(acked),
                },
            })
        return sessions

    # -- 호환 인터페이스 (기존 kis_ws 호출자 보존) ----------------------

    @property
    def _subscriptions(self) -> set[tuple[str, str]]:
        """메인 + 보조 모든 세션 ``_subscriptions`` 합집합.

        호환성: 기존 호출자가 ``kis_ws._subscriptions`` 를 직접 참조하는 경우 동일 의미 제공.
        외부 호출자가 set 에 직접 add/discard 하는 패턴은 사이클 7-B 에서 권장 안 함 —
        새 코드는 ``subscribe/unsubscribe`` 사용.
        """
        result: set[tuple[str, str]] = set()
        for ws in [self._main, *self._quotes]:
            result.update(ws._subscriptions)
        return result

    @property
    def _subscriptions_acked(self) -> set[tuple[str, str]]:
        """메인 + 보조 모든 세션 ACK 합집합."""
        result: set[tuple[str, str]] = set()
        for ws in [self._main, *self._quotes]:
            result.update(ws._subscriptions_acked)
        return result

    @property
    def _subscribed_at(self):
        """사이클 135 (2026-06-15) — 메인 + 보조 모든 세션 _subscribed_at 합집합.

        호환성: 사이클 88 G-REJECT-3 5 dict 분리 영속 (4 → 5).
        stale_watcher_core 영역 영구 영속에서 `kis_ws_pool._subscribed_at` 직접 참조 영속.

        충돌 시점 (동일 (tr_id, tr_key) 키 영역 영구 영속) = 마지막 ACK 시각 채택 영속
        (실제 운영 영역 영구 영속 = 동일 ticker 영역 영구 영속 메인 + 보조 동시 등록 영역 영구 영속 부재 영속 = WebsocketPool _ticker_to_session 분배 정합).
        """
        result: dict = {}
        for ws in [self._main, *self._quotes]:
            sa = getattr(ws, "_subscribed_at", None)
            if sa:
                result.update(sa)
        return result

    @property
    def _ws(self):
        """메인 세션 WebSocket 객체 — 라우트 ``ws_connected`` 판정용 (메인 기준)."""
        return getattr(self._main, "_ws", None)

    @property
    def _reconnect_count(self) -> int:
        """메인 세션 재연결 횟수 (대시보드 기본 노출 — 보조는 sessions 배열로 분리)."""
        return getattr(self._main, "_reconnect_count", 0)


# ---------------------------------------------------------------------------
# 모듈 싱글톤 — 호출자가 직접 import
# ---------------------------------------------------------------------------
# 운영 환경에선 ``kis_ws_pool`` 을 직접 사용. 기존 호출자 (``scanner``, ``scheduler``,
# ``routes``) 는 ``kis_ws`` (메인 단일) 도 그대로 import 가능 — 풀이 메인을 재사용하므로
# 메인 인스턴스 동일성 유지.
kis_ws_pool = WebsocketPool()
