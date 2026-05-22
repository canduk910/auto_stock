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

import logging
from typing import Optional

from src.realtime.websocket import (
    MAX_SUBSCRIPTIONS,
    KisWebSocket,
    kis_ws,
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
        # 1) 체결통보 메인 강제 — priority 무시
        if tr_id in _EXECUTION_NOTICE_TR_IDS:
            await self._main.subscribe(tr_id, tr_key, bypass_limit=True)
            self._ticker_to_session[tr_key] = self._main
            return "main"

        # 2) 중복 ticker 처리
        existing = self._ticker_to_session.get(tr_key)
        if existing is not None:
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
                return "main"
            # 보조에 있는데 LOW 로 또 들어옴 → 그대로 유지 (noop)
            return self._session_label(existing)

        # 3) HIGH 우선순위 — 메인 절대 보장 + bypass_limit=True
        if priority == "HIGH":
            await self._main.subscribe(tr_id, tr_key, bypass_limit=True)
            self._ticker_to_session[tr_key] = self._main
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
        return self._session_label(chosen)

    async def unsubscribe(self, tr_id: str, tr_key: str) -> None:
        """분배 추적된 세션에서 unsubscribe. 기록 없으면 noop (다음 _scan_loop 자연 정리).

        체결통보(H0STCNI0/H0STCNI9) 는 항상 메인 — 명시적으로 메인에서 해제.
        """
        if tr_id in _EXECUTION_NOTICE_TR_IDS:
            await self._main.unsubscribe(tr_id, tr_key)
            self._ticker_to_session.pop(tr_key, None)
            return

        chosen = self._ticker_to_session.pop(tr_key, None)
        if chosen is None:
            return
        try:
            await chosen.unsubscribe(tr_id, tr_key)
        except Exception:
            logger.debug("[pool_unsubscribe] 세션 unsubscribe 실패", exc_info=True)

    async def unsubscribe_all(self) -> None:
        """모든 세션의 모든 구독 해제 + 분배 추적 dict clear."""
        # 분배 추적 기반 unsubscribe — 메인 + 보조 모두 커버
        for tr_key, ws in list(self._ticker_to_session.items()):
            try:
                # tr_id 는 TICK_TR_ID 가정 — 분배 추적에 들어간 ticker 는 TICK 만
                # (체결통보 / 장운영정보는 별도 처리). 안전을 위해 ws._subscriptions 에서
                # tr_key 매칭하는 (tr_id, tr_key) 찾아 unsubscribe.
                matches = [
                    (tid, tk) for tid, tk in ws._subscriptions if tk == tr_key
                ]
                for tid, tk in matches:
                    await ws.unsubscribe(tid, tk)
            except Exception:
                logger.debug("[pool_unsubscribe_all] %s 해제 실패", tr_key, exc_info=True)
        self._ticker_to_session.clear()

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
        if chosen is None:
            # 추적 없는 ticker — 메인에서 시도 (안전 디폴트)
            chosen = self._main
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
        """메인 + 보조 모든 세션의 TICK 구독 합집합 (Phase D 호환 인터페이스)."""
        # 지연 import — scanner 가 websocket_pool 참조 가능성 차단
        from src.engine.scanner import TICK_TR_ID

        result: set[str] = set()
        for ws in [self._main, *self._quotes]:
            for tr_id, tr_key in ws._subscriptions:
                if tr_id == TICK_TR_ID:
                    result.add(tr_key)
        return result

    def get_acked_tickers(self) -> set[str]:
        """메인 + 보조 모든 세션의 ACK 받은 TICK 구독 합집합."""
        from src.engine.scanner import TICK_TR_ID

        result: set[str] = set()
        for ws in [self._main, *self._quotes]:
            for tr_id, tr_key in ws._subscriptions_acked:
                if tr_id == TICK_TR_ID:
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
        from src.engine.scanner import TICK_TR_ID

        # 사이클 43 — 보조 세션 label = ws._label (DB 라벨). graceful 폴백 "unknown".
        sessions = []
        for ws, label in [(self._main, "main")] + [
            (q, getattr(q, "_label", "") or "unknown") for q in self._quotes
        ]:
            subscribed = {
                tr_key for tr_id, tr_key in ws._subscriptions if tr_id == TICK_TR_ID
            }
            acked = {
                tr_key for tr_id, tr_key in ws._subscriptions_acked if tr_id == TICK_TR_ID
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
