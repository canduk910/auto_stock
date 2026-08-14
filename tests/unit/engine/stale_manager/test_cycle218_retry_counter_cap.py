"""사이클 218 Red — K stale watcher `_stale_retry_count` 무한 climb 관찰성 정리.

> **선행 실측 (배포 후 발견, 2026-08-13 EC2, 051905)**:
>   `check_and_resubscribe_stale`(120s) 의 force_retry skip 분기에서 보유 종목의
>   `_stale_retry_count[ticker]` 가 r=131 까지 무한 climb.
>   근본 원인: cycle215 로 실효화된 `resubscribe_stale_priority`(5분) 가
>   `_stale_last_resubscribe_at[ticker]` 를 갱신 → K watcher force_retry 의 600s 게이트
>   (`stale_watcher_core.py:282` `age_secs < STALE_FORCE_RETRY_AFTER_SECS`) 가 계속
>   미충족 → **skip(무SEND) + r 리셋 안 됨**(리셋은 force_retry FIRE 시점 line 323 에만)
>   → r 무한 누적. **실제 재SEND 는 감소(4340→411), r 은 표시용 오해 숫자.**

> **시정 방향 (backend-dev 구현 — 본 파일은 그 행위의 Red)**:
>   `stale_watcher_core.py` force_retry skip 분기(`if age_secs < STALE_FORCE_RETRY_AFTER_SECS:`)
>   안, `continue` 앞에 1줄:
>       `scheduler._stale_retry_count[ticker] = MAX_STALE_RETRIES + 1`
>   = r 을 6 으로 홀드(무한 climb 차단).
>   **행위 불변 근거**: `_stale_retry_count` 소비자 전수 = K watcher `r > MAX_STALE_RETRIES`
>   (stale_watcher_core.py:272) + universe_guard `r <= MAX_STALE_RETRIES`
>   (stale_universe_guard.py:85) + diagnostics `r < 2`(stale_diagnostics.py:243) —
>   전부 임계 비교라 6 이든 131 이든 동일 결과(6>5, 6>=2). 표시만 값 변경 = 목표.

> **8영역 무접촉**: stale_watcher_core.py 는 realtime/ 아님. 4중 안전망 AST(G-REJECT-1) 무충돌.

카테고리별 분포 (6 케이스):
- HIGH 3: skip 분기 캡(G218-1, 핵심 Red) / force_retry FIRE 리셋 보존(G218-2) /
          universe_guard 임계 불변(G218-3)
- MEDIUM 3: force_retry 경로 결정 불변(G218-4) / 1-5 즉시 재등록 무영향(G218-5) /
            sibling 함수 격리(G218-6)

Red 시점 결과 (현재 코드 = cycle215/216/217 배포 상태 기준 기대):
- G218-1: FAIL — 현재 코드는 skip 시 r 리셋 안 함 → 매 사이클 +1 (6→7→8...131 climb).
- G218-2: PASS(불변 가드) — force_retry FIRE 는 line 323 에서 r=0 리셋 (캡 미접촉 경로).
- G218-3: PASS(불변 가드) — r=6 은 여전히 >5 로 universe_guard target (r=0 이면 미평가 대비).
- G218-4: PASS(불변 가드) — r=6(retry=7) 은 force_retry 경로 진입(1-5 falling 안 함).
- G218-5: PASS(불변 가드) — r<=5 은 1-5 즉시 재등록 (캡은 force_retry skip 분기 한정).
- G218-6: PASS(불변 가드) — `resubscribe_stale_priority` 는 `_stale_retry_count` 무접촉.

즉 파일 전체는 현재 코드에서 **G218-1 로 인해 RED** 이며, backend-dev 캡 1줄 후 전량 GREEN.
freezegun 은 고정 base + `asyncio.sleep` patch (cycle63 force_retry 패턴, 동결 hang 무관 —
`check_and_resubscribe_stale` 는 wait 루프 부재 = 단조전진 불요).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ===========================================================================
# fixture helpers (cycle63 force_retry 패턴 답습)
# ===========================================================================
def _make_scheduler(positions: list[str] | None = None, ndc: set | None = None):
    """`TradingScheduler.__new__` + `_stale_state` 만 init (cycle63 답습).

    `_stale_retry_count` / `_stale_last_resubscribe_at` / `_stale_force_retry_history`
    는 property → `_stale_state`(StaleTrackerState) dict 로 노출.
    """
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    object.__setattr__(sched, "_pending_next_day_clear", ndc or set())

    if positions:
        strategy_state = MagicMock()
        strategy_state.positions = {t: MagicMock() for t in positions}
        strategy = MagicMock(state=strategy_state)
        sched.registry = MagicMock(all=lambda: [strategy])
    else:
        sched.registry = MagicMock(all=lambda: [])
    return sched


def _make_mock_pool(subscribed: set):
    mock_pool = MagicMock()
    mock_pool.get_subscribed_tickers = MagicMock(return_value=subscribed)
    mock_pool.unsubscribe_in_pool = AsyncMock(return_value=None)
    mock_pool.subscribe = AsyncMock(return_value=None)
    return mock_pool


# ===========================================================================
# G218-1 (HIGH, 핵심 Red) — skip 분기 캡: r 이 MAX_STALE_RETRIES+1 로 홀드 (무한 climb 차단)
# ===========================================================================
@pytest.mark.asyncio
async def test_G218_1_skip_branch_caps_retry_count_no_infinite_climb():
    """G218-1 (핵심 Red): force_retry 게이트 미경과(age<600s) + r>5 종목이 skip 될 때,
    사이클 후 `_stale_retry_count[ticker] == MAX_STALE_RETRIES + 1`(=6). 반복 사이클에도
    6 유지(131 climb 안 함).

    현재 코드: skip 분기(stale_watcher_core.py:282-285)가 `skipped_giveup += 1; continue`
    만 하고 r 리셋 없음 → 매 사이클 line 261-262 에서 +1 → 6→7→8...climb.
    시정 후: `continue` 앞 `scheduler._stale_retry_count[ticker] = MAX_STALE_RETRIES + 1`
    → 매 사이클 6 으로 되홀드.

    Red 단계 (현재 코드): 사이클 1 후 r=7 → assert `==6` FAIL.
    Green 단계 (시정 후): 매 사이클 r=6 유지 → PASS.
    """
    from src.engine.stale_manager import MAX_STALE_RETRIES, check_and_resubscribe_stale

    base = datetime(2026, 8, 14, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler()
    ticker = "051905"
    # r=6(>5) → force_retry 분기. retry 로컬 = 7 이 되지만 캡이 6 으로 되홀드해야 함.
    sched._stale_retry_count[ticker] = MAX_STALE_RETRIES + 1  # = 6
    # cycle215 실효 `resubscribe_stale_priority` 가 최근 갱신한 상태 재현 (age=100s < 600s)
    sched._stale_last_resubscribe_at[ticker] = base - timedelta(seconds=100)

    mock_pool = _make_mock_pool({ticker})

    observed: list[int] = []
    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        # 5 사이클 반복 — 무한 climb 재현/차단 검증
        for _ in range(5):
            await check_and_resubscribe_stale(sched)
            observed.append(sched._stale_retry_count[ticker])

    assert observed == [MAX_STALE_RETRIES + 1] * 5, (
        "skip 분기 캡 누락 — r 이 매 사이클 +1 climb (관찰성 오해 숫자). "
        f"기대 [6,6,6,6,6], 실제 {observed}. "
        "시정: skip 분기 continue 앞 `_stale_retry_count[ticker] = MAX_STALE_RETRIES + 1`"
    )
    # skip = 무SEND (실제 재SEND 없음) — 표시 숫자만 문제였음을 명시
    assert mock_pool.subscribe.await_count == 0, (
        "force_retry 게이트 미경과 skip 은 재SEND 0 (r 만 오해 climb 하던 상황)"
    )
    assert mock_pool.unsubscribe_in_pool.await_count == 0, (
        "skip 분기는 unsubscribe SEND 도 0"
    )


# ===========================================================================
# G218-2 (HIGH, 불변 가드) — force_retry FIRE 경로 무영향 (r=0 리셋 보존)
# ===========================================================================
@pytest.mark.asyncio
async def test_G218_2_force_retry_fire_path_still_resets_to_zero():
    """G218-2 (불변): `_stale_last_resubscribe_at` old(age>=600s) → force_retry 실제 발화
    → r=0 리셋(stale_watcher_core.py:323) 보존. 캡(skip 분기)이 이 경로 안 건드림.

    캡은 `age_secs < STALE_FORCE_RETRY_AFTER_SECS` skip 분기에만 삽입되므로 FIRE 경로
    (age>=600 또는 last_at 부재)는 영향 0.

    현재 코드/시정 후 모두 PASS (캡 삽입이 FIRE 리셋을 회귀시키지 않음을 봉인).
    """
    from src.engine.stale_manager import MAX_STALE_RETRIES, check_and_resubscribe_stale

    base = datetime(2026, 8, 14, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler()
    ticker = "051905"
    sched._stale_retry_count[ticker] = MAX_STALE_RETRIES + 1  # = 6 → retry=7
    # age=700s >= 600s → 쿨다운 경과 → FIRE 경로 (skip 아님)
    sched._stale_last_resubscribe_at[ticker] = base - timedelta(seconds=700)

    mock_pool = _make_mock_pool({ticker})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await check_and_resubscribe_stale(sched)

    assert sched._stale_retry_count[ticker] == 0, (
        "force_retry FIRE → r=0 리셋(line 323) 보존 의무 — 캡이 FIRE 경로 침범 금지"
    )
    assert mock_pool.subscribe.await_count == 1, (
        "FIRE 경로는 실제 강제 재등록 (subscribe 1회) — 실효 재SEND 보존"
    )
    # FIRE 근거: history 에 1건 append (skip 분기는 history 미접촉)
    assert len(sched._stale_force_retry_history.get(ticker, [])) == 1, (
        "force_retry FIRE 는 history 60분 윈도우에 1건 등록"
    )


# ===========================================================================
# G218-3 (HIGH, 불변 가드) — universe_guard: 캡된 r=6 은 여전히 target (r=0 대비)
# ===========================================================================
@pytest.mark.asyncio
async def test_G218_3_universe_guard_threshold_invariant_six_targeted_zero_not():
    """G218-3 (불변): 캡된 r=6 종목은 stale_universe_guard 에서 여전히
    `r > MAX_STALE_RETRIES`(>5)로 target(제외 후보). **reset-to-0 였다면 깨질 것**
    (r=0 <= 5 → line 85 continue → 미평가) — 이 대비를 한 호출에서 명시 검증.

    캡 값이 `MAX_STALE_RETRIES + 1`(=6) 여야 하고 0 이면 안 되는 근거를 봉인한다.
    (직접 `evaluate_universe_guard` 호출 — 임계 결정 순수 검증, KIS None 폴백으로 제외 보류)

    현재 코드/시정 후 모두 PASS (universe_guard 임계 불변 문서화).
    """
    from src.engine.stale_manager import MAX_STALE_RETRIES, evaluate_universe_guard

    sched = _make_scheduler()
    sched.registry.is_ticker_held_by_any = MagicMock(return_value=False)
    object.__setattr__(sched, "_universe_excluded_today", set())

    high = "111111"   # r=6 (캡 값) → target 되어야 함
    boundary = "222222"  # r=5 (경계) → 미target
    zero = "333333"   # r=0 (오설계 reset-to-0 가정) → 미target
    sched._stale_retry_count[high] = MAX_STALE_RETRIES + 1  # 6
    sched._stale_retry_count[boundary] = MAX_STALE_RETRIES  # 5
    sched._stale_retry_count[zero] = 0

    # inquire_ccnl 호출 = "target 판정" 관측 지표 (None 반환 → 제외 보류, unsubscribe 없음)
    mock_ccnl = AsyncMock(return_value=None)
    mock_pool = MagicMock()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.api.quotation.inquire_ccnl", new=mock_ccnl), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool):
        await evaluate_universe_guard(sched, [high, boundary, zero])

    targeted = {c.args[0] for c in mock_ccnl.await_args_list}
    assert high in targeted, (
        "캡된 r=6 은 r>MAX_STALE_RETRIES(>5) → universe_guard target 유지 의무"
    )
    assert boundary not in targeted, (
        "r=5(경계)는 `r<=MAX_STALE_RETRIES` → 미평가 (line 85 continue)"
    )
    assert zero not in targeted, (
        "r=0(오설계 reset-to-0 가정)은 미평가 — 캡 값이 6 이어야 하고 0 이면 안 되는 근거"
    )


# ===========================================================================
# G218-4 (MEDIUM, 불변 가드) — force_retry 경로 결정: r=6(retry=7)은 force_retry 진입 (1-5 아님)
# ===========================================================================
@pytest.mark.asyncio
async def test_G218_4_capped_six_enters_force_retry_branch_not_immediate():
    """G218-4 (불변): 캡된 r=6 도 `retry(=7) > MAX_STALE_RETRIES` True → force_retry 경로
    진입(즉시 재등록 1-5 경로로 falling 안 함). 즉 6 은 여전히 >5.

    구분 관측: force_retry FIRE 는 `_stale_force_retry_history` 에 append(1-5 경로는
    history 미접촉) → history 등록 = force_retry 경로 진입 증거.

    현재 코드/시정 후 모두 PASS (경로 결정 임계 불변 봉인).
    """
    from src.engine.stale_manager import MAX_STALE_RETRIES, check_and_resubscribe_stale

    base = datetime(2026, 8, 14, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler()
    ticker = "051905"
    sched._stale_retry_count[ticker] = MAX_STALE_RETRIES + 1  # = 6 → retry=7 (>5)
    # last_at 부재 → age=inf → force_retry FIRE 경로 (1-5 즉시 경로와 구분)
    mock_pool = _make_mock_pool({ticker})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await check_and_resubscribe_stale(sched)

    assert len(sched._stale_force_retry_history.get(ticker, [])) == 1, (
        "r=6(retry=7)은 force_retry 경로 진입 → history 1건 등록 (1-5 즉시 경로는 history 미접촉)"
    )


# ===========================================================================
# G218-5 (MEDIUM, 불변 가드) — 1-5 즉시 재등록 경로 무영향 (r<=5)
# ===========================================================================
@pytest.mark.asyncio
async def test_G218_5_one_to_five_immediate_path_unaffected():
    """G218-5 (불변): r<=5 종목은 캡 무관 기존대로 1-5 즉시 강제 재등록.

    r=2 → retry=3 (<=5) → unsubscribe + subscribe + 카운터 누적(리셋 안 함, history 미접촉).
    캡은 force_retry skip 분기 한정이라 이 경로 byte 불변.

    현재 코드/시정 후 모두 PASS.
    """
    from src.engine.stale_manager import check_and_resubscribe_stale

    base = datetime(2026, 8, 14, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler()
    ticker = "051905"
    sched._stale_retry_count[ticker] = 2  # → retry=3 (1-5 즉시 경로)

    mock_pool = _make_mock_pool({ticker})

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new={}):
        await check_and_resubscribe_stale(sched)

    assert mock_pool.unsubscribe_in_pool.await_count == 1, "1-5 경로 즉시 unsubscribe"
    assert mock_pool.subscribe.await_count == 1, "1-5 경로 즉시 subscribe"
    assert sched._stale_retry_count[ticker] == 3, (
        "1-5 경로는 카운터 누적(리셋 안 함) — 캡 미접촉"
    )
    assert sched._stale_force_retry_history.get(ticker, []) == [], (
        "1-5 경로는 force_retry history 미접촉"
    )


# ===========================================================================
# G218-6 (MEDIUM, 불변 가드) — sibling 함수 격리 (cycle215/216/217 회귀 0)
# ===========================================================================
@pytest.mark.asyncio
async def test_G218_6_resubscribe_stale_priority_does_not_touch_retry_count():
    """G218-6 (불변): 캡 삽입 대상이 아닌 `resubscribe_stale_priority`(5분, 다른 함수)는
    `_stale_retry_count` 를 읽지도 쓰지도 않는다 → cycle215/216/217 회귀 0 의 구조적 근거.

    backend-dev 가 캡 1줄을 엉뚱한 함수(sibling)에 넣지 못하도록 격리 봉인.

    현재 코드/시정 후 모두 PASS.
    """
    from src.engine.stale_manager import resubscribe_stale_priority

    base = datetime(2026, 8, 14, 10, 0, 0, tzinfo=KST)
    sched = _make_scheduler()
    ticker = "051905"
    # resubscribe_stale_priority 의 stale 소스 = scanner.ticker_last_tick (get_subscribed 아님)
    stale_last_tick = {ticker: base - timedelta(seconds=120)}  # 120s > 60s → stale

    mock_pool = MagicMock()
    mock_pool.get_subscribed_tickers = MagicMock(return_value={ticker})
    mock_pool.unsubscribe_in_pool = AsyncMock(return_value=None)
    mock_pool.subscribe = AsyncMock(return_value=None)
    mock_pool._ticker_to_session = {}

    with freeze_time(base), \
         patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=stale_last_tick):
        result = await resubscribe_stale_priority(sched, cap=10)

    assert ticker in result, "resubscribe_stale_priority 는 stale 종목 재구독 (행위 보존)"
    assert dict(sched._stale_retry_count) == {}, (
        "resubscribe_stale_priority 는 `_stale_retry_count` 무접촉 — "
        "캡 삽입은 check_and_resubscribe_stale 한정 (sibling 격리)"
    )
