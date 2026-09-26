"""실시간 시세 구독 진단 라우트 — /api/realtime/* (G2/J2, 2026-05-12).

KIS REST/WS 어디에도 슬롯 사용현황 조회 API 미존재 → 우리 측 도구로 가시화.

GET /api/realtime/subscriptions:
- `_subscriptions` (SEND 기준) vs `_subscriptions_acked` (KIS 응답 기준) 격차 노출
- 최근 60초 내 tick 수신 (`fresh_60s`) / 미수신 (`stale_60s`) 카운트
- `MAX_SUBSCRIPTIONS=41` 한도 + 누적 재연결 횟수 + WebSocket 활성 여부

POST /api/realtime/resubscribe (J2, 2026-05-12):
- 60초 미수신(stale) TICK 종목을 운영자가 즉시 일괄 재구독
- F1 자동 재구독(재연결 후 60s)과 별개의 수동 트리거
- `_subscriptions` set 은 보존 — `_send_subscribe(TICK_TR_ID, t, subscribe=True)` 만 호출
- 호출 간 50ms sleep (Rate Limit 안전)
- WebSocket 끊김 시 400 (재구독 메시지 발송 불가)

POST/GET/DELETE /api/realtime/channel-probe (cycle253, 2026-09-05):
- 포렌식 `_workspace/forensics/stale_candidates_0904.md` ⑥-1 의 열린 질문 —
  "KRX 단독 채널(H0STCNT0)이 `nxt_tradable=False` 종목의 체결 프레임을 실제로
  송출하는가" — 를 8영역 무접촉으로 답하는 다크런치 진단 도구.
- 허용 tr_id = {H0STCNT0, H0NXCNT0} 뿐 (라이브 통합 채널 H0UNCNT0 는 422 —
  `_ticker_to_session` 단일 키를 덮어써 라이브 시세 경로를 훔친다).
- 배제 조건(409) 6종 — already_probing / already_tick_subscribed / held_or_pending_clear
  / in_desired_universe(breakout ∪ swing ∪ momentum 후보) / probe_cap / subscribe_dropped
  — 은 편의가 아니라 안전 장치다: 프레임이 실제로 오면 `risk.on_tick` 이 그대로 돌기
  때문에, 이미 라이브 구독·보유·익일청산·매수 후보인 종목을 프로브하면 실매매를 건드릴
  수 있다. 스윙 후보(donchian/kojiro `_candidates`)는 첫 `_scan_loop` 뒤 TICK 집합 밖이라
  구독 검사만으로는 새고, 프레임이 오면 09:05~09:30 창에서 tick 경로 BUY 가 가능하므로
  desired 게이트에 포함한다.
- `bypass_limit` 은 항상 리터럴 False — 진단 도구가 HIGH(보유) 슬롯을 밀면 안 된다.
- 영구 기록은 `logger.info` 한 줄뿐이다. `src.` 로거의 INFO 이상은 `main._DbLogHandler`
  가 이미 system_logs 에 적재하므로 같은 내용을 `write_log` 로 또 쓰면 액션당 2행 —
  사이클 72 G-6 가 막는 이중 INSERT 그 자체다. 프로브 경로는 `write_log` 를 호출하지
  않는다(AST g253_1f 가 핸들러 + 모듈 헬퍼 폐쇄까지 추적).
- 격리의 한계 — 운영 절차가 메운다:
  (a) 120s K watcher·delta unsubscribe·F1 재검증·universe guard 는 `tr_id == H0UNCNT0`
      필터라 프로브를 보지 못하지만, **5분 `resubscribe_stale_priority` 는 소스가
      `ticker_last_tick` 전수**라 프로브 종목이 프레임을 받은 뒤 stale 이 되면 후보에
      든다. cycle240 desired 교집합 필터(breakout desired 비어 있음 ∨ HIGH 수집 예외면
      OFF)만이 그것을 막으므로, 운영 전 돌파 전략 1개 이상 enabled + 스캔 결과 비어
      있지 않음을 확인한다(평일 정상 = 활성).
  (b) 프로브 중 같은 종목이 desired 에 편입되면 `_ticker_to_session` 단일 키 때문에
      `_scan_loop` 의 라이브 LOW TICK 구독이 무음 억제되고, 매수(HIGH 승격)되면 프로브
      튜플이 보조 세션에 고아로 남아 20:00 `unsubscribe_all` 도 지우지 못한다. GET 행의
      `live_tick_subscribed` / `in_desired_now` 가 편입을 가시화하고, DELETE 는
      `unsubscribe_in_pool` 대신 **모든 세션을 순회**해 `(tr_id, ticker)` 튜플을 지운다
      (`unsubscribe_in_pool` 의 라우팅 pop 은 승격된 라이브 종목의 라우팅까지 지운다).
      라우팅은 그 세션에 그 종목의 튜플이 하나도 남지 않을 때만 pop 한다. 프로브 창은
      ≤15분, DELETE 필수.
- 상태는 프로세스 메모리(`_channel_probes`) — 재시작 시 소실. 20:00 `unsubscribe_all`
  은 **구독만** 지우고 등록부는 남기므로(익일 같은 종목 409 `already_probing` + cap
  잠식), POST 진입 시 전날(KST) 항목을 자동 축출한다(`action=evict`). 그래도 정본 종료
  경로는 DELETE 다.
- 상세 명세: `_workspace/forensics/krx_channel_probe_design.md` §2.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from src.db.system_logs import write_log
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/realtime", tags=["realtime"])

# 60s 임계는 scanner.get_scan_status / scheduler._report_tick_coverage 와 동일 (운영 일관성)
_KST_TZ = timezone(timedelta(hours=9))
_FRESHNESS_SECS = 60

# --- cycle253 — KRX/NXT 단독 채널 다크런치 프로브 ---------------------------
#: 허용 tr_id = KRX 단독(H0STCNT0) + NXT 단독(H0NXCNT0). 라이브 통합 채널
#: (H0UNCNT0, `scanner.TICK_TR_ID`) 은 절대 포함하지 않는다 — `_ticker_to_session`
#: 이 tr_key 단일 키라 통합 채널 프로브는 그 종목의 라이브 라우팅을 덮어쓴다.
_PROBE_ALLOWED_TR_IDS = {"H0STCNT0", "H0NXCNT0"}
#: 동시 프로브 상한 — 진단 도구가 슬롯 예산을 잠식하지 않게 (명세 §1).
_PROBE_CAP = 3
#: ticker → {tr_id, started_at(datetime KST), session_label, first_tick_at(datetime|None)}
#: 프로세스 메모리 — 재시작 시 소실(20:00 unsubscribe_all 과 동일 수명, 문서화 대상).
_channel_probes: dict[str, dict] = {}


class ChannelProbeIn(BaseModel):
    """`POST /api/realtime/channel-probe` 바디.

    ticker 는 진입 규약과 동일(6자리 숫자만 — ETF/신주인수권 차단). tr_id 는 허용
    집합 밖이면 422 — 특히 라이브 통합 채널(H0UNCNT0)과 체결통보 TR 은 시세 진단
    프로브의 대상이 아니다.
    """

    ticker: str
    tr_id: str = "H0STCNT0"

    @field_validator("ticker")
    @classmethod
    def _validate_ticker(cls, v: str) -> str:
        if not (isinstance(v, str) and len(v) == 6 and v.isdigit()):
            raise ValueError("ticker 는 6자리 숫자여야 한다 (진입 규약과 동일)")
        return v

    @field_validator("tr_id")
    @classmethod
    def _validate_tr_id(cls, v: str) -> str:
        if v not in _PROBE_ALLOWED_TR_IDS:
            raise ValueError(
                f"tr_id 는 {sorted(_PROBE_ALLOWED_TR_IDS)} 중 하나여야 한다 "
                "(라이브 통합 채널·체결통보 TR 프로브 금지)"
            )
        return v


def _pool_sessions(pool) -> list:
    """풀의 세션 목록 `[main, *quotes]` — 속성 부재 시 빈 목록(테스트 대역 호환)."""
    sessions: list = []
    main = getattr(pool, "_main", None)
    if main is not None:
        sessions.append(main)
    try:
        sessions.extend(list(getattr(pool, "_quotes", None) or []))
    except Exception:
        pass
    return sessions


def _session_tuples(ws) -> set[tuple[str, str]]:
    """세션의 `_subscriptions` 스냅샷(SEND 기준). 부재·예외는 빈 집합."""
    try:
        return set(getattr(ws, "_subscriptions", None) or set())
    except Exception:
        return set()


def _probe_tuple_present(pool, tr_id: str, ticker: str) -> bool:
    """어느 세션이든 `_subscriptions` 에 `(tr_id, ticker)` 튜플이 있는가."""
    return any((tr_id, ticker) in _session_tuples(ws) for ws in _pool_sessions(pool))


def _register_probe_exclusion(tr_id: str, ticker: str) -> None:
    """cycle293 — 이 튜플이 **프로브** 임을 TICK 집계 쪽에 알린다.

    프로브는 진단 도구이므로 라이브 TICK 뷰(K stale watcher 재등록 · universe guard
    축출 · 5분 delta 해제 · F1 재검증 · `[tick_coverage]` 분모)에 들어가면 안 된다.
    종전에는 그 격리를 "전용 채널은 집계에 없다" 는 **채널 동일성**이 대신했는데,
    cycle293 이 전용 채널을 실 구독에 쓰기 시작해 그 추론이 죽었다.

    등록·회수·판정은 전부 `websocket` 의 세 헬퍼를 경유한다 — 집합을 직접
    변형하면 수명 dict(`_PROBE_EXCLUSION_DAY`)와 갈려 전날 잔존 항목이 라이브
    구독을 은폐한다.

    ⚠️ 등록 실패 시 최악은 **종전과 같은 노출이 아니다** — cycle293 부터 프로브가
    라이브 TICK 집계에 섞여 5분 `_scan_loop` delta 가 `current - new_set` 으로
    프로브를 해제해 측정을 끊는다. 그래도 never-raise 로 둔다: 측정 도구의
    격리 실패가 프로브 시작을 막는 것보다는 낫고, 끊기면 `received=False` 로
    드러난다.
    """
    try:
        from src.realtime.websocket import register_probe_exclusion

        register_probe_exclusion(tr_id, ticker)
    except Exception:  # pragma: no cover — never-raise
        logger.debug("[krx_channel_probe] 프로브 제외 등록 실패", exc_info=True)


def _unregister_probe_exclusion(tr_id: str, ticker: str) -> None:
    """프로브 종료·드롭 시 제외 등록 회수 (남기면 그 종목이 영구 집계 밖이 된다)."""
    try:
        from src.realtime.websocket import unregister_probe_exclusion

        unregister_probe_exclusion(tr_id, ticker)
    except Exception:  # pragma: no cover — never-raise
        logger.debug("[krx_channel_probe] 프로브 제외 회수 실패", exc_info=True)


def _release_routing_if_orphaned(pool, ticker: str) -> bool:
    """`_ticker_to_session[ticker]` 가 가리키는 세션에 그 종목의 튜플이 **하나도** 없을
    때만 라우팅을 pop 한다.

    `WebsocketPool.subscribe` 는 `_ticker_to_session` 에 기록이 있으면 LOW 요청을
    구독 없이 label 만 돌려준다(noop). 프로브 튜플이 사라졌는데 라우팅만 남으면 그
    종목의 라이브 LOW TICK 구독이 20:00 까지 무음 억제된다 — 프로브가 끝난 뒤 그
    흔적을 남기지 않는 것이 이 함수의 역할이다. 반대로 그 세션에 같은 종목의 다른
    tr_id 튜플(라이브 H0UNCNT0)이 남아 있으면 절대 pop 하지 않는다 — 그 라우팅은
    라이브 경로의 것이다.

    cycle293 Green (적대 검증 F6) — 병행 dict `_ticker_to_tr_id` 도 **같은 자리에서**
    pop 한다. `_ticker_to_session` 만 비우면 유령 채널 항목이 남고,
    `stale_watcher_core._actual_or_desired_tick_tr_id` 는 `_ticker_to_session` 을
    보지 않고 그 dict 만 읽으므로 구독 0건인 종목에 "실제 채널" 을 보고한다.
    """
    routing = getattr(pool, "_ticker_to_session", None)
    if not isinstance(routing, dict):
        return False
    routed = routing.get(ticker)
    if routed is None:
        return False
    if any(tk == ticker for _tid, tk in _session_tuples(routed)):
        return False
    routing.pop(ticker, None)
    tr_map = getattr(pool, "_ticker_to_tr_id", None)
    if isinstance(tr_map, dict):
        tr_map.pop(ticker, None)
    return True


async def _unsubscribe_probe_everywhere(pool, tr_id: str, ticker: str) -> list[str]:
    """`(tr_id, ticker)` 튜플을 보유한 **모든** 세션에서 해제하고 라벨 목록을 돌려준다.

    `unsubscribe_in_pool(tr_id, ticker)` 를 쓰지 않는 이유 — 그 함수는
    `_ticker_to_session.pop(ticker)` 가 가리키는 **한 세션**에서만 해제한다. 프로브
    중 같은 종목이 매수돼 HIGH 로 승격되면 라우팅은 main 으로 바뀌고 프로브 튜플은
    보조 세션에 고아로 남는데, 그때 `unsubscribe_in_pool` 은 (1) 고아를 못 지우고
    (2) 승격된 라이브 종목의 라우팅을 pop 해 버린다. 세션 전수 순회는 두 결함을 모두
    피한다. 라우팅 정리는 `_release_routing_if_orphaned` 규칙을 따른다.
    """
    removed_from: list[str] = []
    for ws in _pool_sessions(pool):
        if (tr_id, ticker) not in _session_tuples(ws):
            continue
        try:
            await ws.unsubscribe(tr_id, ticker)
            removed_from.append(str(getattr(ws, "_label", None) or "?"))
        except Exception:
            logger.debug(
                "[krx_channel_probe] 세션 unsubscribe 실패 ticker=%s tr_id=%s",
                ticker, tr_id, exc_info=True,
            )
    _release_routing_if_orphaned(pool, ticker)
    # cycle293 — 프로브가 끝나면 제외 등록도 함께 회수한다. 이 함수가 stop·evict
    # 양쪽의 단일 choke point 라 여기 한 곳이면 누락이 없다.
    _unregister_probe_exclusion(tr_id, ticker)
    return removed_from


def _desired_tickers() -> set[str]:
    """라이브 TICK 구독 후보(desired) 합집합 = breakout ∪ swing ∪ momentum.

    breakout(`_collect_breakout_tickers`)·momentum(`scanner._last_scan_result`)은
    `_scan_loop` 의 desired 와 같고, swing(`_collect_swing_tickers` — donchian/kojiro
    `_candidates`)은 첫 `_scan_loop` 뒤 TICK 집합 밖이라 구독 검사로는 잡히지 않지만
    프레임이 오면 09:05~09:30 창에서 tick 경로 BUY 가 구조적으로 가능하다. 소스 하나가
    예외를 던져도 나머지는 살린다(빈 집합 = 그 소스만 판정 불가).
    """
    desired: set[str] = set()
    try:
        from src.engine.scheduler import trading_scheduler
    except Exception:
        trading_scheduler = None
    for name in ("_collect_breakout_tickers", "_collect_swing_tickers"):
        try:
            fn = getattr(trading_scheduler, name, None)
            if callable(fn):
                desired.update(str(t) for t in (fn() or []))
        except Exception:
            continue
    try:
        from src.engine.scanner import _last_scan_result
        desired.update(str(t) for t in (_last_scan_result or []))
    except Exception:
        pass
    return desired


def _probe_context(pool) -> tuple[set[str], set[str]]:
    """GET/DELETE 행 계산에 필요한 (라이브 TICK 구독 집합, desired 집합)."""
    try:
        live_tick = set(pool.get_subscribed_tickers())
    except Exception:
        live_tick = set()
    return live_tick, _desired_tickers()


async def _evict_stale_probes(pool, *, now: datetime) -> list[str]:
    """전날(KST) 이전에 시작된 등록부 항목을 축출한다 — POST 진입 시 1회.

    20:00 `unsubscribe_all` 은 구독 튜플만 지우고 `_channel_probes` 는 남긴다. 그대로
    두면 익일 같은 종목 POST 가 409 `already_probing` 이고 잔존 항목이 cap 을 잠식한다.
    구독이 남아 있을 가능성(20:00 이후 시작한 프로브)까지 고려해 축출 전에 세션 전수
    해제를 한 번 더 시도한다(튜플이 없으면 no-op).
    """
    today = now.date()
    stale: list[str] = []
    for ticker, state in list(_channel_probes.items()):
        started_at = state.get("started_at")
        try:
            if started_at.date() >= today:
                continue
        except Exception:
            continue
        stale.append(ticker)
    for ticker in stale:
        state = _channel_probes.pop(ticker, None)
        if state is None:
            continue
        removed_from = await _unsubscribe_probe_everywhere(pool, state.get("tr_id", ""), ticker)
        logger.info(
            "[krx_channel_probe] action=evict ticker=%s tr_id=%s started_at=%s "
            "removed_from=%s reason=stale_day",
            ticker, state.get("tr_id"), getattr(state.get("started_at"), "isoformat", lambda: None)(),
            removed_from,
        )
    return stale


def _build_probe_row(
    ticker: str,
    state: dict,
    *,
    now: datetime,
    live_tick: set[str] | None = None,
    desired: set[str] | None = None,
) -> dict:
    """GET/DELETE 공용 — 프로브 1건의 신선도·수신 판정 행을 만든다.

    `received` 는 **`started_at` 기준**(last_tick_at > started_at)이다. 구독
    이전의 잔존 `ticker_last_tick` 값을 수신으로 세면 프로브가 스스로 가설을
    확증해버려 이 도구가 답하려는 질문 자체가 무의미해진다. `first_tick_at` 은
    처음 `received=True` 를 관측한 시점의 last_tick 값으로 **한 번만** 고정한다
    (폴링 기반 근사 — 이후 last_tick 이 더 전진해도 불변).

    `subscribed`/`acked` 는 프로브 자신의 `(tr_id, ticker)` **튜플** 존재로
    판정한다(원시 `pool._subscriptions`/`_subscriptions_acked`) — 같은 종목의
    라이브 통합 채널(H0UNCNT0) 튜플은 다른 tr_id 라 판정에 섞이지 않는다.

    `price` 는 생산 키를 읽는다 — `risk.on_tick` 이 쓰는 `ticker_prices[ticker]` 는
    `{current_price, open_price, change_rate, prdy_ctrt}` 4키뿐이고 누적거래량은
    `tick_volume.record_acml_vol` 로만 흐른다(P0-1 확정 사실). `price`/`acml_vol`
    키를 읽으면 운영에서 항상 `{null, null}` 이다.

    **`open_price` (09-09 추가)** — 채널별 시가 비교(NXT 프리장 vs KRX 전용, cycle264/265
    조사)에 이 값이 필요해 세 번째 키로 노출한다. 원문 WebSocket 프레임(`auto_stock.log`
    DEBUG)은 필드가 중간에서 잘려 시가를 못 뽑는다는 게 09-09 실측으로 확인됐다(websockets
    라이브러리가 긴 TEXT 프레임을 repr 축약해서 기록) — 이 파싱된 값이 채널 비교의 유일한
    안전한 소스다. `ticker_prices` 는 채널 무관 단일 dict(마지막 tick 값)라 같은 종목을
    한 채널에서 다른 채널로 전환하며 폴링하면 전환 전후 값을 그대로 비교할 수 있다.

    `live_tick_subscribed`(= `get_subscribed_tickers()` 포함) / `in_desired_now`
    (= breakout ∪ swing ∪ momentum 후보 포함)는 프로브 **시작 후** 같은 종목이 라이브
    유니버스에 편입됐는지를 드러낸다 — `in_desired_now ∧ ¬live_tick_subscribed` 는
    `_ticker_to_session` 단일 키 때문에 라이브 LOW 구독이 억제되고 있다는 신호이고,
    어느 쪽이든 True 면 즉시 DELETE 가 운영 절차다.
    """
    # 지연 import — scanner/websocket_pool 순환 의존 회피 + 테스트 대역 호환
    try:
        from src.engine.scanner import ticker_last_tick, ticker_prices
    except Exception:
        ticker_last_tick, ticker_prices = {}, {}
    try:
        from src.realtime.websocket_pool import kis_ws_pool
    except Exception:
        kis_ws_pool = None
    try:
        from src.engine.tick_volume import get_observed_acml_vol
    except Exception:
        def get_observed_acml_vol(_t: str):  # type: ignore[misc]
            return None

    tr_id = state["tr_id"]
    started_at: datetime = state["started_at"]

    try:
        subscribed_pairs = getattr(kis_ws_pool, "_subscriptions", set()) or set()
    except Exception:
        subscribed_pairs = set()
    try:
        acked_pairs = getattr(kis_ws_pool, "_subscriptions_acked", set()) or set()
    except Exception:
        acked_pairs = set()

    subscribed = (tr_id, ticker) in subscribed_pairs
    acked = (tr_id, ticker) in acked_pairs

    last_tick_dt = ticker_last_tick.get(ticker)
    if last_tick_dt is not None:
        last_tick_at = last_tick_dt.isoformat()
        age_secs = int((now - last_tick_dt).total_seconds())
    else:
        last_tick_at = None
        age_secs = None

    received = last_tick_dt is not None and last_tick_dt > started_at
    if received and state.get("first_tick_at") is None:
        state["first_tick_at"] = last_tick_dt

    first_tick_dt = state.get("first_tick_at")
    first_tick_at = first_tick_dt.isoformat() if first_tick_dt is not None else None

    price_entry = ticker_prices.get(ticker) if hasattr(ticker_prices, "get") else None
    current_price = price_entry.get("current_price") if isinstance(price_entry, dict) else None
    open_price = price_entry.get("open_price") if isinstance(price_entry, dict) else None
    try:
        acml_vol = get_observed_acml_vol(ticker)
    except Exception:
        acml_vol = None
    if current_price is None and acml_vol is None and open_price is None:
        price: dict | None = None
    else:
        price = {"price": current_price, "acml_vol": acml_vol, "open_price": open_price}

    live_tick_subscribed = ticker in live_tick if live_tick is not None else None
    in_desired_now = ticker in desired if desired is not None else None

    return {
        "ticker": ticker,
        "tr_id": tr_id,
        "started_at": started_at.isoformat(),
        "session_label": state.get("session_label"),
        "subscribed": subscribed,
        "acked": acked,
        "last_tick_at": last_tick_at,
        "age_secs": age_secs,
        "first_tick_at": first_tick_at,
        "received": received,
        "price": price,
        "live_tick_subscribed": live_tick_subscribed,
        "in_desired_now": in_desired_now,
    }


@router.get("/subscriptions", response_model=ApiResponse)
async def get_subscriptions() -> ApiResponse:
    """현재 WebSocket 구독 슬롯 사용현황을 반환한다.

    사이클 7-B (2026-05-17) — 멀티 세션 풀 지원:
    - 메인 + 보조 세션 합집합으로 ``total/acked/fresh_60s/stale_60s`` 산출
    - ``sessions`` 배열로 세션별 ``label/subscribed/acked/fresh/stale/limit/ws_connected/reconnect_count`` 노출
    - ``limit`` 전체값 = ``MAX_SUBSCRIPTIONS × (1 + 보조 세션 수)``
    - 보조 0개 시 sessions 길이 1 (main only) — 기존 호환 보존

    응답 data 스키마:
        total            — 합집합 TICK 구독 (SEND 기준)
        acked            — 합집합 ACK (KIS 응답 기준)
        fresh_60s        — 최근 60s 내 tick 수신 카운트
        stale_60s        — 60s 미수신 카운트
        limit            — 41 × (1 + 보조 세션 수)
        tickers.subscribed / acked / fresh / stale — 합집합 sorted
        reconnect_count  — 메인 세션 재연결 횟수 (보조는 sessions[*] 에 별도 노출)
        ws_connected     — 메인 세션 활성 (보조는 sessions[*] 에 별도 노출)
        sessions         — [{label, subscribed, acked, fresh, stale, limit, ws_connected, reconnect_count}, ...]
    """
    # 지연 import — scanner 가 websocket 을 참조하므로 순환 의존 회피
    # cycle293 — `TICK_TR_ID` 는 이 함수에서 쓰이지 않는다(구독 집합은 풀이 세 채널
    # 합집합으로 준다). 남겨 두면 다음 사람이 "이 함수는 통합 채널만 본다" 고 오독한다.
    from src.engine.scanner import ticker_last_tick
    from src.realtime.websocket import MAX_SUBSCRIPTIONS
    from src.realtime.websocket_pool import kis_ws_pool

    pool = kis_ws_pool
    # 합집합 (메인 + 보조)
    subscribed_set = pool.get_subscribed_tickers()
    acked_set = pool.get_acked_tickers()

    now = datetime.now(_KST_TZ)
    threshold = timedelta(seconds=_FRESHNESS_SECS)
    _min_dt = datetime.min.replace(tzinfo=_KST_TZ)
    fresh_set = {
        t for t in subscribed_set
        if (now - ticker_last_tick.get(t, _min_dt)) <= threshold
    }
    stale_set = subscribed_set - fresh_set

    # 세션별 분해 + freshness 카운트 추가
    sessions = pool.get_session_status()

    # 사이클 35 (2026-05-21) — 세션별 종목 상세 정보 (UI 노출용).
    # scheduler._stale_retry_count / _stale_last_resubscribe_at 접근 — 부재 시 graceful.
    # ticker_names 매핑 + ticker cap 200 (응답 크기 보호).
    # 사이클 37 (2026-05-21) — KIS 실제 last_cntg_hour 캐시 매핑 (`_last_ccnl_cache`).
    from src.engine.scanner import ticker_names
    try:
        from src.engine.scheduler import trading_scheduler
        stale_retry_count = getattr(trading_scheduler, "_stale_retry_count", {}) or {}
        stale_last_resubscribe_at = getattr(trading_scheduler, "_stale_last_resubscribe_at", {}) or {}
        # 사이클 37 — KIS 체결시각 캐시 (UI last_cntg_hour / today_volume 노출)
        last_ccnl_cache = getattr(trading_scheduler, "_last_ccnl_cache", {}) or {}
    except Exception:
        stale_retry_count = {}
        stale_last_resubscribe_at = {}
        last_ccnl_cache = {}

    SESSION_TICKERS_DETAIL_CAP = 200

    for session in sessions:
        # session.tickers.subscribed 에 sorted ticker 리스트 보유 — freshness 계산
        ticker_list = session.get("tickers", {}).get("subscribed", [])
        ticker_set = set(ticker_list)
        s_fresh = {
            t for t in ticker_set
            if (now - ticker_last_tick.get(t, _min_dt)) <= threshold
        }
        session["fresh"] = len(s_fresh)
        session["stale"] = len(ticker_set) - len(s_fresh)

        # 사이클 35 — tickers_detail: 종목별 (ticker, ticker_name, stale, last_tick, retries, last_resub)
        # cap 200 적용 (세션당). stale 먼저 정렬 → fresh 순 (운영자 우선 노출 순서).
        sorted_tickers = sorted(
            ticker_list,
            key=lambda t: (t not in (ticker_set - s_fresh), t),  # stale 먼저
        )[:SESSION_TICKERS_DETAIL_CAP]

        details = []
        for ticker in sorted_tickers:
            last_dt = ticker_last_tick.get(ticker)
            last_tick_iso = last_dt.isoformat() if last_dt and last_dt != _min_dt else None
            last_resub_at = stale_last_resubscribe_at.get(ticker)
            last_resub_iso = last_resub_at.isoformat() if last_resub_at else None
            is_stale = ticker not in s_fresh
            # 사이클 37 — KIS 캐시 매핑 (TTL 5분 + cap 20). 미스 → null
            ccnl_entry = last_ccnl_cache.get(ticker)
            last_cntg_hour = ccnl_entry.get("last_cntg_hour") if ccnl_entry else None
            today_volume = ccnl_entry.get("today_volume") if ccnl_entry else None
            details.append({
                "ticker": ticker,
                "ticker_name": ticker_names.get(ticker, ""),
                "stale": is_stale,
                "last_tick": last_tick_iso,
                "retries": int(stale_retry_count.get(ticker, 0)),
                "last_resub": last_resub_iso,
                # 사이클 37 신규
                "last_cntg_hour": last_cntg_hour,
                "today_volume": today_volume,
            })
        session["tickers_detail"] = details

    # 사이클 18 (2026-05-19, B-1) — stale 종목별 마지막 tick 시각 노출.
    # 프론트 ScanMonitor 가 "끊김 N종목" 펼치기 시 종목별 마지막 수신 시각 표시.
    # KRX 메인 마감 (15:30) 전 = 결함 가능 / 마감 후 = 자연 휴면 톤 분기 근거.
    last_tick_map: dict[str, str | None] = {}
    for ticker in sorted(stale_set):
        last_dt = ticker_last_tick.get(ticker)
        if last_dt is None or last_dt == _min_dt:
            last_tick_map[ticker] = None
        else:
            last_tick_map[ticker] = last_dt.isoformat()  # KST tz 포함

    data = {
        "total": len(subscribed_set),
        "acked": len(acked_set),
        "fresh_60s": len(fresh_set),
        "stale_60s": len(stale_set),
        "limit": MAX_SUBSCRIPTIONS * len(sessions),
        "tickers": {
            "subscribed": sorted(subscribed_set),
            "acked": sorted(acked_set),
            "fresh": sorted(fresh_set),
            "stale": sorted(stale_set),
        },
        "last_tick_map": last_tick_map,
        "reconnect_count": pool._reconnect_count,
        "ws_connected": pool._ws is not None,
        "sessions": sessions,
    }
    return ApiResponse(success=True, data=data, message="")


@router.post("/resubscribe", response_model=ApiResponse)
async def resubscribe_stale() -> ApiResponse:
    """stale(60s 미수신) TICK 구독 종목을 즉시 일괄 재구독한다 (J2, 2026-05-12).

    운영자가 ScanMonitor 의 끊김 배지를 확인하고 인라인 버튼을 눌러 호출.
    F1 자동 재구독(재연결 후 60s)이 발화하지 않는 일반 운영 시간대(연결 유지 중)
    에 stale 이 누적된 경우 즉시 회복.

    안전 불변식:
    - `_subscriptions` set 직접 수정 금지 — `_send_subscribe` 만 호출
      (E2 거절 응답이 오면 자동으로 set 에서 discard 됨)
    - 호출 간 50ms sleep — KIS WS Rate Limit 보호 (F1 메서드와 동일 패턴)
    - WebSocket `_ws is None` 시 400 — 메시지 발송 불가하므로 조용히 200 반환 금지

    응답:
        data.resubscribed : 재구독 종목 수
        data.tickers      : sorted ticker 리스트
    """
    # 지연 import — scanner 가 websocket 을 참조하므로 순환 의존 회피
    from src.engine.scanner import TICK_TR_ID, TICK_TR_IDS, ticker_last_tick
    from src.realtime.websocket import VERIFY_FRESHNESS_SECS, kis_ws

    # WebSocket 끊김 → 메시지 발송 불가 → 400 (조용한 200 금지)
    if kis_ws._ws is None:
        raise HTTPException(
            status_code=400,
            detail="WebSocket 연결 끊김 — 재구독 메시지 발송 불가. 자동 재연결 대기 후 재시도.",
        )

    # 현재 TICK 구독 집합 (SEND 기준, Phase D `get_subscribed_tickers`)
    subscribed = kis_ws.get_subscribed_tickers()
    # cycle293 — 재전송은 그 종목이 **실제로 구독된 채널**로 나가야 한다. 구독
    # 사실이 정본이고(리졸버의 현재 판정이 아니다), 매핑에 없으면 현행 통합 채널.
    tick_channel_of = {
        tr_key: tr_id
        for tr_id, tr_key in kis_ws._subscriptions
        if tr_id in TICK_TR_IDS
    }

    now = datetime.now(_KST_TZ)
    threshold = timedelta(seconds=VERIFY_FRESHNESS_SECS)
    min_dt = datetime.min.replace(tzinfo=_KST_TZ)

    # stale 추출 — last_tick 없으면 stale 로 간주 (F1 동일 규약)
    stale = sorted(
        t for t in subscribed
        if (now - ticker_last_tick.get(t, min_dt)) > threshold
    )

    # 각 stale ticker 재구독 — `_send_subscribe` 만 사용
    for ticker in stale:
        await kis_ws._send_subscribe(
            tick_channel_of.get(ticker, TICK_TR_ID), ticker, subscribe=True,
        )
        await asyncio.sleep(0.05)  # Rate Limit 보호

    # 영구 로그 — count=0 도 기록 (운영자가 빈 stale 도 확인 가능)
    try:
        await write_log(
            "INFO",
            f"[ws_manual_resubscribe] count={len(stale)} tickers={stale}",
        )
    except Exception:
        # fire-and-forget — write_log 실패해도 재구독 응답은 유지
        logger.debug("[ws_manual_resubscribe] write_log 실패", exc_info=True)

    return ApiResponse(
        success=True,
        data={"resubscribed": len(stale), "tickers": stale},
        message="",
    )


@router.get("/market-operation", response_model=ApiResponse)
async def get_market_operation() -> ApiResponse:
    """장운영 상태 + 서킷브레이커 휴리스틱 조회 (사이클 186).

    응답 data 스키마:
        vi_active_count         — VI 활성 종목 수
        halt_active_count       — 거래정지 활성 종목 수
        last_event_count        — 마지막 이벤트 보유 종목 수
        vi_active_sample        — VI 활성 sample (최대 10)
        halt_active_sample      — 거래정지 활성 sample (최대 10)
        iscd_stat_active_count  — 종목상태 이상 종목 수
        circuit_breaker         — 서킷브레이커 휴리스틱 dict
            suspected / reasons / halt_ratio / halted / observed
            representative_mkop_cls_code / halt_reasons_sample
        details                 — VI ∪ 거래정지 ∪ 종목상태(표시집합) 종목 상세 (최대 200)
            ticker / vi_code / ovtm_vi_code / halt_yn / halt_reason
            iscd_stat / mkop_cls_code / exch_code / received_at

    cycle371 — `details` 는 VI ∪ 거래정지 에 `get_iscd_stat_active_tickers()`(표시 집합
    중 51/52/53/54/59 멤버십 — 58 은 이미 거래정지 TTL 로 관리돼 제외)를 합집합한다.
    헤더 `iscd_stat_active_count` 는 51~54·58·59 6종으로 세는데 종전 `details` 는 VI ∪
    거래정지만 훑어, 관리종목(51)·단기과열(59) 단독(VI 비활성 + 거래정지 아님) 종목은
    헤더 카운트엔 잡히고 상세 행이 없었다. **카운트(summary)는 무변경** — `details`
    원본 행만 늘린다.
    """
    # 지연 import — 순환 의존 회피
    from src.engine.market_operation_monitor import (
        get_circuit_breaker_state,
        get_halt_active_tickers,
        get_iscd_stat_active_tickers,
        get_last_event,
        get_market_op_state_summary,
        get_vi_active_tickers,
    )

    summary = get_market_op_state_summary()

    # details: VI ∪ halt ∪ 종목상태(표시집합) 종목 sorted, cap 200 (cycle371)
    active_tickers = sorted(
        get_vi_active_tickers() | get_halt_active_tickers() | get_iscd_stat_active_tickers()
    )[:200]
    details = []
    for ticker in active_tickers:
        event = get_last_event(ticker)
        if event is None:
            continue
        details.append({
            "ticker": ticker,
            "vi_code": event.vi_cls_code,
            "ovtm_vi_code": event.ovtm_vi_cls_code,
            "halt_yn": event.trht_yn,
            "halt_reason": event.tr_susp_reas_cntt,
            "iscd_stat": event.iscd_stat_cls_code,
            "mkop_cls_code": event.mkop_cls_code,
            "exch_code": event.exch_cls_code,
            "received_at": event.received_at.isoformat() if event.received_at else None,
        })

    data = {**summary, "details": details}
    return ApiResponse(success=True, data=data, message="")


# ===========================================================================
# cycle253 — KRX/NXT 단독 채널 다크런치 프로브
# ===========================================================================
@router.post("/channel-probe", response_model=ApiResponse)
async def start_channel_probe(req: ChannelProbeIn) -> ApiResponse:
    """KRX/NXT 단독 채널(H0STCNT0/H0NXCNT0) 프로브를 시작한다 (cycle253).

    포렌식 열린 질문(`_workspace/forensics/stale_candidates_0904.md` ⑥-1) —
    "H0STCNT0 가 nxt_tradable=False 종목의 체결 프레임을 실제로 송출하는가" —
    를 8영역 무접촉으로 답한다. 409 배제 조건 5종은 편의가 아니라 안전 장치다:
    프레임이 실제로 오면 `risk.on_tick` 이 그대로 돌기 때문에, 이미 라이브
    구독·보유·익일청산·매수 후보인 종목을 프로브하면 실매매를 건드릴 수 있다.
    """
    ticker = req.ticker
    tr_id = req.tr_id

    # 지연 import — scanner/scheduler 순환 의존 회피
    from src.realtime.websocket_pool import kis_ws_pool

    now = datetime.now(_KST_TZ)
    # 전날(KST) 잔존 등록부 축출 — 20:00 unsubscribe_all 은 등록부를 건드리지 않는다
    await _evict_stale_probes(kis_ws_pool, now=now)

    if ticker in _channel_probes:
        raise HTTPException(status_code=409, detail="already_probing")

    try:
        tick_subscribed = kis_ws_pool.get_subscribed_tickers()
    except Exception:
        tick_subscribed = set()
    if ticker in tick_subscribed:
        raise HTTPException(status_code=409, detail="already_tick_subscribed")

    try:
        from src.engine.scheduler import trading_scheduler
    except Exception:
        trading_scheduler = None

    held = False
    try:
        registry = getattr(trading_scheduler, "registry", None)
        for strategy in registry.all() if registry is not None else []:
            positions = getattr(getattr(strategy, "state", None), "positions", {}) or {}
            if ticker in positions:
                held = True
                break
    except Exception:
        held = False

    pending_clear = False
    try:
        pending_set = getattr(trading_scheduler, "_pending_next_day_clear", set()) or set()
        pending_clear = any(t == ticker for t, _sid in pending_set)
    except Exception:
        pending_clear = False

    if held or pending_clear:
        raise HTTPException(status_code=409, detail="held_or_pending_clear")

    # desired = breakout ∪ swing ∪ momentum — 프레임이 오면 실매수 신호가 날 수 있는 집합
    if ticker in _desired_tickers():
        raise HTTPException(status_code=409, detail="in_desired_universe")

    if len(_channel_probes) >= _PROBE_CAP:
        raise HTTPException(status_code=409, detail="probe_cap")

    if kis_ws_pool._ws is None:
        raise HTTPException(
            status_code=400,
            detail="WebSocket 연결 끊김 — 프로브 구독 메시지 발송 불가",
        )

    # cycle293 — 프로브 튜플을 **구독 발사 전에** 제외 집합에 등록한다. 종전에는
    # "전용 채널은 TICK 집계에 없다" 는 채널 동일성이 격리를 대신했지만, cycle293 이
    # 그 채널을 실 구독에 쓰기 시작하며 그 추론이 죽었다(`websocket.
    # PROBE_EXCLUDED_TUPLES` docstring). 등록이 늦으면 그 사이 5분 `_scan_loop` delta
    # 가 프로브를 `current - new_set` 으로 해제해 측정을 끊는다.
    _register_probe_exclusion(tr_id, ticker)

    session_label = await kis_ws_pool.subscribe(
        tr_id, ticker, priority="LOW", bypass_limit=False,
    )

    # 풀은 (a) 전 세션 만석이면 None 을, (b) `_ticker_to_session` 에 튜플 없는 잔존
    # 라우팅이 있으면 구독 없이 label 만 돌려준다. 어느 쪽도 실제 구독이 0 이므로
    # 200 + 상태 등록은 거짓 — 409 로 알리고 등록하지 않는다. (b) 의 고아 라우팅은
    # 그 종목의 라이브 LOW 구독까지 억제하므로 여기서 함께 정리한다.
    if session_label is None or not _probe_tuple_present(kis_ws_pool, tr_id, ticker):
        reason = "all_sessions_full" if session_label is None else "no_tuple_after_subscribe"
        released = _release_routing_if_orphaned(kis_ws_pool, ticker)
        _unregister_probe_exclusion(tr_id, ticker)   # 등록 실패분 즉시 회수
        logger.warning(
            "[krx_channel_probe] action=dropped ticker=%s tr_id=%s session=%s reason=%s "
            "routing_released=%s",
            ticker, tr_id, session_label, reason, released,
        )
        raise HTTPException(status_code=409, detail="subscribe_dropped")

    started_at = datetime.now(_KST_TZ)
    _channel_probes[ticker] = {
        "tr_id": tr_id,
        "started_at": started_at,
        "session_label": session_label,
        "first_tick_at": None,
    }

    # 영구 기록은 이 한 줄 — `src.` 로거 INFO 는 `_DbLogHandler` 가 system_logs 에 적재한다.
    logger.info(
        "[krx_channel_probe] action=start ticker=%s tr_id=%s session=%s",
        ticker, tr_id, session_label,
    )

    return ApiResponse(
        success=True,
        data={
            "ticker": ticker,
            "tr_id": tr_id,
            "started_at": started_at.isoformat(),
            "session_label": session_label,
            "first_tick_at": None,
        },
        message="",
    )


@router.get("/channel-probe", response_model=ApiResponse)
async def get_channel_probes() -> ApiResponse:
    """진행 중인 채널 프로브 상태를 폴링한다 (cycle253). 구독 변경 0 — 읽기 전용.

    응답 `data.probes[*]` 각 행: ticker/tr_id/started_at/session_label/
    subscribed/acked/last_tick_at/age_secs/first_tick_at/received/price/
    live_tick_subscribed/in_desired_now.
    """
    from src.realtime.websocket_pool import kis_ws_pool

    now = datetime.now(_KST_TZ)
    live_tick, desired = _probe_context(kis_ws_pool)
    rows = [
        _build_probe_row(ticker, state, now=now, live_tick=live_tick, desired=desired)
        for ticker, state in _channel_probes.items()
    ]
    return ApiResponse(success=True, data={"probes": rows, "count": len(rows)}, message="")


@router.delete("/channel-probe/{ticker}", response_model=ApiResponse)
async def stop_channel_probe(ticker: str) -> ApiResponse:
    """채널 프로브를 종료한다 (cycle253) — 구독 해제 + 상태 제거.

    프로브 없으면 404(조용한 200 금지 — 두 번째 DELETE 가 해제를 재발사하면 안 된다).

    해제는 `unsubscribe_in_pool` 이 아니라 **세션 전수 순회**다 — 프로브 중 같은
    종목이 매수돼 HIGH 승격되면 프로브 튜플이 보조 세션에 고아로 남고 라우팅은
    main 을 가리키는데, `unsubscribe_in_pool` 은 그 고아를 못 지우면서 라이브
    라우팅만 pop 한다. 응답 `removed_from` 이 실제로 해제된 세션 라벨 목록이다.
    """
    state = _channel_probes.get(ticker)
    if state is None:
        raise HTTPException(status_code=404, detail="probe_not_found")

    # 지연 import — 순환 의존 회피
    from src.realtime.websocket_pool import kis_ws_pool

    now = datetime.now(_KST_TZ)
    live_tick, desired = _probe_context(kis_ws_pool)
    row = _build_probe_row(ticker, state, now=now, live_tick=live_tick, desired=desired)

    tr_id = state["tr_id"]

    removed_from = await _unsubscribe_probe_everywhere(kis_ws_pool, tr_id, ticker)
    _channel_probes.pop(ticker, None)
    row["removed_from"] = removed_from

    # 영구 기록은 이 한 줄 — `src.` 로거 INFO 는 `_DbLogHandler` 가 system_logs 에 적재한다.
    logger.info(
        "[krx_channel_probe] action=stop ticker=%s tr_id=%s received=%s first_tick_at=%s "
        "removed_from=%s",
        ticker, tr_id, row["received"], row["first_tick_at"], removed_from,
    )

    return ApiResponse(success=True, data=row, message="")


# ---------------------------------------------------------------------------
# cycle293 — 시세 채널 리졸버 킬스위치 (§8-B)
#
# 🔴 cycle287 의 실패를 반복하지 않는다. 그 사이클은 킬스위치 2개를
#    `param_catalog` 미등재로 만들어 `PUT /api/strategies/{id}/params` 가
#    `unknown_key` 422 를 돌려줬다 = **장중에 끌 수 없었다**. 리졸버는 전략별
#    설정이 아니라 인프라 축이라 `system_config` 한 키가 정본이고, 그 키를
#    **재시작 없이** 바꾸는 경로를 같은 커밋에 넣는다:
#
#      curl -X PUT .../api/realtime/tick-channel-mode -d '{"mode":"off"}'
#
#    이 PUT 은 DB 에 쓰고 **같은 요청 안에서** 엔진 메모리 값까지 덮는다(즉시).
#    폴링 경로(`scanner.subscribe_filtered_stocks` 5분 · `stale_watcher_core`
#    120초)는 그 뒤의 정합 보장용이다.
#
# ⚠️ 롤백이 즉시가 아닌 지점 — §3-C/§6-D 의 "장중 전환 금지" 때문에 이미 전용
#    채널에 올라간 종목은 **다음 `_boot`/재구독 사이클까지** 그 채널에 남는다.
# ---------------------------------------------------------------------------
class TickChannelModeRequest(BaseModel):
    mode: str
    #: cycle294 §9-D — 전환 다이얼. **모드 enum 에 태우지 않는다**(결정 카드 D-5):
    #: 「채널이 문제」(`mode`)와 「전환이 문제」(`switch_enabled`)는 다른 결정이고,
    #: 사고 중에 쓸 카드가 `off` 하나뿐이면 운영자가 146종목 대량 전환을 장중에
    #: 실행하게 된다(§9-B — `off` 는 이미 올라간 구독을 되돌리지 않는다).
    #: `false` 면 종목이 첫 구독 채널에 머문다 — `nxt_true` 는 NXT 종일이고 NXT 는
    #: 정규장·애프터에 체결을 실으므로 **blind 가 아니다**. 이것이 §5 자동 원복의
    #: 수동 대응물이다. 생략(`None`)하면 현행 값을 건드리지 않는다.
    switch_enabled: bool | None = None
    # 🔴 cycle295 — `gap_hold_enabled` 필드는 여기 없다(다이얼 자체가 제거됐다,
    # `src/engine/tick_channel_clock.py` 모듈 docstring 참조). 옛 런북 payload의
    # 이 키는 `model_config` 기본 `extra="ignore"` 로 **조용히 무시**된다 —
    # 422 로 막지 않는다(같은 요청의 `mode` 킬스위치까지 막히기 때문). §6-1 대로
    # 그 런북 자체를 지운다.


def _switch_windows_repr():
    """그날 전환 허용 창 목록 — 운영자가 화면 없이 확인하는 유일한 채널."""
    try:
        from src.engine import tick_channel_clock, tick_channel_mode

        return [
            {"start": str(start), "end": str(end), "label": label}
            for start, end, label in tick_channel_clock.switch_windows(
                offset_secs=tick_channel_mode.switch_offset_secs(),
            )
        ]
    except Exception:  # pragma: no cover — never-raise
        return []


@router.get("/tick-channel-mode", response_model=ApiResponse)
async def get_tick_channel_mode():
    """현재 리졸버 모드 + DB 저장값 + 유효 어휘."""
    from src.db import system_config
    from src.engine import tick_channel_mode

    try:
        stored = await system_config.get_tick_channel_resolver_mode()
    except Exception:
        stored = None
    return ApiResponse(
        success=True,
        data={
            "mode": tick_channel_mode.current_mode(),
            "stored": stored,
            "default": tick_channel_mode.DEFAULT_MODE,
            "valid_modes": sorted(tick_channel_mode.VALID_MODES),
            "config_key": tick_channel_mode.CONFIG_KEY,
            # cycle294 §9-D — 전환 다이얼은 모드와 **별개 축**이다.
            "switch_enabled": tick_channel_mode.switch_enabled(),
            "switch_offset_secs": tick_channel_mode.switch_offset_secs(),
            "switch_config_key": tick_channel_mode.SWITCH_ENABLED_KEY,
            "switch_windows": _switch_windows_repr(),
        },
        message="",
    )


@router.put("/tick-channel-mode", response_model=ApiResponse)
async def put_tick_channel_mode(req: TickChannelModeRequest):
    """리졸버 모드 변경 — DB 저장 + 즉시 메모리 반영 (재시작 불요).

    어휘 밖 값은 **422**(조용히 기본값으로 흡수하면 운영자가 무엇이 적용됐는지
    모른다). DB 쓰기가 실패해도 메모리 반영은 시도한다 — 사고 중 `off` 는 이번
    프로세스에서 듣는 것이 먼저다(다음 재시작에 되살아나는 것은 그 다음 문제).
    """
    from src.db import system_config
    from src.engine import tick_channel_mode

    mode = (req.mode or "").strip()
    if mode not in tick_channel_mode.VALID_MODES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"mode must be one of {sorted(tick_channel_mode.VALID_MODES)}, "
                f"got {req.mode!r}"
            ),
        )

    persisted = True
    try:
        await system_config.set_tick_channel_resolver_mode(mode)
    except Exception:
        persisted = False
        logger.exception("[tick_channel_mode] DB 저장 실패 — 메모리만 반영 시도")

    applied = tick_channel_mode.apply_mode(mode)

    # cycle294 §9-D — 선택 필드. 생략하면 현행 값 무접촉(부분 갱신)이라 모드만
    # 바꾸는 기존 호출은 **byte 동일**하게 동작한다. 신규 엔드포인트 0 이 계약이다.
    switch_applied = tick_channel_mode.switch_enabled()
    switch_persisted: bool | None = None
    if req.switch_enabled is not None:
        switch_persisted = True
        try:
            await system_config.set_tick_channel_switch_enabled(bool(req.switch_enabled))
        except Exception:
            switch_persisted = False
            logger.exception("[tick_channel_mode] switch_enabled DB 저장 실패 — 메모리만 반영 시도")
        switch_applied = tick_channel_mode.apply_switch_enabled(bool(req.switch_enabled))

    logger.warning(
        "[tick_channel_mode] mode=%s persisted=%s switch_enabled=%s switch_persisted=%s"
        " — 운영자 변경 (즉시 반영)",
        applied, persisted, switch_applied, switch_persisted,
    )
    failed = [
        label for label, ok in (
            ("mode", persisted),
            ("switch_enabled", switch_persisted),
        )
        if ok is False
    ]
    return ApiResponse(
        success=True,
        data={
            "mode": applied,
            "persisted": persisted,
            "switch_enabled": switch_applied,
            "switch_persisted": switch_persisted,
        },
        message=(
            ""
            if not failed
            else f"DB 저장 실패({', '.join(failed)}) — 메모리만 반영됨(재시작 시 원복)"
        ),
    )
