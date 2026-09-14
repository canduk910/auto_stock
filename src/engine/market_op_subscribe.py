"""종목별 H0UNMKO0(VI) 구독 leaf — cycle292 에서 `scheduler.py` 에서 이동.

`scheduler._subscribe_market_operation_tickers` 가 이 함수에 위임한다. 행위는
cycle221/230 계약 그대로이고 이동만 했다 — 본체는 라인 단위 동일(`self.` → `scheduler.`
치환 6곳 + dedent 뿐), 자세한 설계 근거는 함수 docstring.

순환 import 회피: 이 모듈은 scheduler 를 import 하지 않는다(`data_load_tasks` 배너 답습) —
scheduler 인스턴스는 첫 인자로만 받는다.
⚠️ 함수-로컬 import 5줄(`ConnectionClosedError`/`State`/`MARKET_OP_TR_ID`/
`MAX_SUBSCRIPTIONS`+`kis_ws`/`kis_ws_pool`)을 모듈 최상단으로 올리지 않는다 — 기존 테스트
4파일이 **정의 모듈의 속성**(`src.realtime.websocket.*` / `src.realtime.websocket_pool.*`)을
monkeypatch 하고, 함수-로컬 import 는 매 호출 재실행되므로 그 patch 가 걸린다. 최상단으로
올리면 이름이 import 시점에 바인딩돼 patch 가 무력화되고 `_ws is None` → `return 0` 조기
반환이 부정 단언 6케이스를 **조용히 초록**으로 통과시킨다(cycle292 §2.5). 두 줄 분리
(`kis_ws`←websocket / `kis_ws_pool`←websocket_pool)도 유지 — 합치면 2026-07-24 의
매 호출 ImportError(cycle214 배포 이래 완전 미작동, 하루 117건) 재발이다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

# 운영 로그 접두사([market_op_subscribe_*] 등) grep 이력 단절 방지 (사이클 60 I1).
# `_DbLogHandler` 가 `[{record.name}]` 로 적재하므로 이름이 갈리면 system_logs 접두가
# 바뀐다 = 판독 사슬 파괴 = 행위 변경. `__name__` 으로 바꾸지 않는다 (cycle292 §4).
logger = logging.getLogger("src.engine.scheduler")


async def subscribe_market_operation_tickers(
    scheduler: Any, candidate_tickers: set[str], *, cap: int = 60,
) -> int:
    """cycle149/214 → **cycle221** — 종목별 H0UNMKO0(VI) 구독을 보조 세션 전용으로.

    대상은 **보유 + 익일청산(HIGH) 뿐**이다(전략 후보 LOW 미구독). 메인 세션에는 한 건도
    붙이지 않고 보조 세션(`_quotes`)에 **직접**(풀 API 미경유) **델타**(신규만 SEND /
    이탈만 해제)로 배치한다.

    사고(2026-08-19): OPSP0008 117건 중 시세 7건이 섞였고 대상 4종목이 전부 매수 직후 보유
    종목이었다(~58분 tick blind = 손절 사각). 메인 45/41 로 **KIS 서버 한도** 초과 상태였고
    그중 ~25% 를 VI 가 선점했다(`bypass_limit=True` 는 로컬 가드만 우회, 서버 한도는 못 넘음).
    cycle 32 R4 "HIGH 절대 보장"의 보호 대상은 **시세(tick)** 이고 H0UNMKO0 는 VI/거래정지
    **관찰** 채널(소비처 = `is_ticker_stale_excluded` + 서킷브레이커 UI, 매매 게이트
    미연계)이라 cycle214 의 HIGH 승격은 오적용 판정.
    정정 F2 — **후보 VI 배치 삭제**. `_ticker_to_session` 이 `tr_key` 단일 키라 기존 LOW
    배치는 TICK 중복 분기에서 SEND 없이 반환됐다 = 실질 noop. 세션 직접 호출로 옮기면
    "이동" 이 아니라 죽은 경로의 **7배 활성화**(10→70건)이고, scanner 잔여 슬롯 계산이 VI 를
    합집합으로 세므로 tick 후보 슬롯이 48~60 줄어든다(tail = VB/LTV, REST 폴 비대상 =
    완전 사각). → 되살리지 않는다.
    정정 F1 — **예약 슬롯 제거, 41 하드리밋**. 예약선은 후보 VI 70건 대비용이라 후보가
    사라지면 존재 이유가 없다(HIGH 는 10건 안팎). 남겨두면 08-19 실측(보조 6세션 ≈40.8/41)
    에서 보유 VI 가 **전량 skip** 되어 퇴행한다. 전 세션 만석이면 요약 INFO 와 **별도
    WARNING 1행** — 결손은 `is_ticker_stale_excluded` 무력화 → LMS 압력이라 은닉 금지.

    메인 폴백은 보조 세션이 0개이거나 전부 만석이어도 **금지**한다. 우선순위는 tick > VI
    이고 VI 관찰 상실은 손절 상실이 아니다 — 이 교환이 명시적 결정이다. `cap` 은
    vestigial — cycle214 시그니처 가드 보존 목적 유지, 제거 금지.
    영속: 소켓 OPEN 가드 + `ConnectionClosedError` break+WARNING 1행(2026-08-07) /
    0.05s Rate Limit 스로틀(사이클 17) / 8영역 diff 0.
    """
    from websockets.exceptions import ConnectionClosedError
    from websockets.protocol import State

    from src.api.market_operation import MARKET_OP_TR_ID
    from src.realtime.websocket import MAX_SUBSCRIPTIONS, kis_ws
    from src.realtime.websocket_pool import kis_ws_pool

    # 소켓 상태 가드 (2026-08-07) — 기존 가드는 `_ws` None 여부만 봐서, 재연결
    # 레이스로 "존재하지만 닫힌"(state != OPEN) 소켓이 통과 → send() 에서
    # ConnectionClosedError 폭주(08-07 11:24:57 HIGH 7종목 버스트). open 아니면
    # 사이클 skip — H0UNMKO0 는 다음 5분 사이클에 자동 복구되는 VI 채널.
    _ws_obj = getattr(kis_ws, "_ws", None) if kis_ws is not None else None
    if _ws_obj is None:
        return 0
    if getattr(_ws_obj, "state", None) is not State.OPEN:
        logger.info("[market_op_subscribe_skip] 소켓 미개방 — 사이클 skip, 다음 재개")
        return 0

    # HIGH = 보유 + 익일청산. **유일한** VI 대상이다 (cycle221 F2 — 후보 제외).
    high_tickers: set[str] = set()
    try:
        for s in scheduler.registry.all():
            try:
                high_tickers.update(s.state.positions.keys())
            except Exception:
                pass
    except Exception:
        pass
    try:
        high_tickers.update(t for (t, _sid) in scheduler._pending_next_day_clear)
    except Exception:
        pass

    # 후보(비HIGH)는 배치하지 않는다 — 관측용 카운트만 남긴다.
    try:
        low_skipped = len(set(candidate_tickers) - high_tickers)
    except Exception:
        low_skipped = 0

    targets = sorted(high_tickers)
    target_set = set(targets)

    # 메인 점유 계측 (read-only) — `[priority_drop]` 은 포화 시에만 발화해 main 45/41
    # 초과가 묻혀 있었다(사고 사실 #4). VI 훅은 5분마다 무조건 찍는다.
    try:
        main_total = len(getattr(kis_ws, "_subscriptions", ()) or ())
    except Exception:
        main_total = 0
    try:
        main_tick = len(kis_ws.get_subscribed_tickers() or ())
    except Exception:
        main_tick = 0
    main_over = max(0, main_total - MAX_SUBSCRIPTIONS)

    quotes = list(getattr(kis_ws_pool, "_quotes", None) or [])
    if not quotes:
        # 메인 폴백 **명시 금지** — 관찰 채널이 쉬는 것보다 tick 슬롯 보존이 우선.
        logger.info(
            "[market_op_no_quote_session] 보조 세션 0 — 종목별 VI skip(메인 폴백 금지)"
        )
        return 0

    # --- 델타 해제 (슬롯 누수 차단, 사고 원인 3 = UNSUBSCRIBE 0곳).
    # `kis_ws_pool.unsubscribe` 절대 금지 — ticker 키 pop 이 TICK 라우팅 기록을 지운다.
    released = 0
    for ticker in sorted(set(scheduler._market_op_subs) - target_set):
        sess = scheduler._market_op_subs.pop(ticker, None)
        if sess is None:
            continue
        try:
            await sess.unsubscribe(MARKET_OP_TR_ID, ticker)
            released += 1
        except Exception:
            logger.warning(
                "[market_op_subscribe] VI 해제 실패 ticker=%s graceful", ticker,
            )

    # --- 보조 세션 직접 라운드로빈 배치. 예약 슬롯 없음(cycle221 F1) = 41 하드리밋
    # (HIGH 10건 안팎이라 tick 미위협 + 예약선은 만석 근처에서 보유 VI 를 전멸시킨다).
    limit = MAX_SUBSCRIPTIONS
    subscribed = 0
    skipped_no_slot = 0
    idx = 0
    for pos, ticker in enumerate(targets):
        live = scheduler._market_op_subs.get(ticker)
        if live is not None and live in quotes:
            continue  # 이미 살아있는 구독 — 재SEND 금지 (LMS chain 완화)

        placed = False
        for offset in range(len(quotes)):
            ws = quotes[(idx + offset) % len(quotes)]
            try:
                used = len(getattr(ws, "_subscriptions", ()) or ())
            except Exception:
                used = limit
            if used >= limit:
                continue
            try:
                await ws.subscribe(MARKET_OP_TR_ID, ticker, bypass_limit=False)
            except ConnectionClosedError:
                logger.warning(
                    "[market_op_subscribe] 소켓 재연결 중 — VI 잔여 %d종목 skip",
                    len(targets) - pos,
                )
                placed = None  # break sentinel
                break
            except Exception:
                logger.exception(
                    "[market_op_subscribe] VI 구독 실패 ticker=%s graceful", ticker,
                )
                placed = True  # 종목별 격리 — 다음 종목으로
                break
            scheduler._market_op_subs[ticker] = ws
            subscribed += 1
            idx = (idx + offset + 1) % len(quotes)
            placed = True
            await asyncio.sleep(0.05)  # Rate Limit 보호 (사이클 17 LMS chain)
            break

        if placed is None:
            break
        if not placed:
            skipped_no_slot += 1

    logger.info(
        "[market_op_subscribe_summary] high=%d low_skipped=%d placed=%d released=%d "
        "skipped_no_slot=%d main_direct=0 sessions=%d main_tick=%d main_total=%d main_over=%d cap=%d",
        len(high_tickers), low_skipped, subscribed, released,
        skipped_no_slot, len(quotes), main_tick, main_total, main_over, cap,
    )
    if main_over > 0:
        logger.warning(
            "[market_op_subscribe_summary] 메인 세션 서버 한도 초과 "
            "main_total=%d max=%d main_over=%d — tick 구독 거부(OPSP0008) 위험",
            main_total, MAX_SUBSCRIPTIONS, main_over,
        )
    if skipped_no_slot > 0:
        # cycle221 F1 — 관찰 상실은 허용된 교환(tick > VI)이지만 **은닉은 아니다**.
        logger.warning(
            "[market_op_subscribe_no_slot] 보조 세션 전 세션 만석 — 보유/익일청산 VI 관찰 "
            "%d종목 결손 (sessions=%d, 세션당 상한 %d). is_ticker_stale_excluded 가 VI/거래정지 "
            "종목을 stale 에서 제외하지 못해 강제 재구독 지속 → KIS LMS 압력 증가",
            skipped_no_slot, len(quotes), MAX_SUBSCRIPTIONS,
        )
    return subscribed
