"""cycle221 (2026-08-20) — H0UNMKO0(VI 채널) 메인 세션 퇴출 회귀 가드.

## 사고 (2026-08-19)

OPSP0008 "MAX SUBSCRIBE OVER" 117건. 그중 **실시간 시세(H0UNCNT0) 7건**이 섞였고
대상 4종목이 전부 **매수 직후 보유 종목**이었다 → tick 미수신 = 손절 사각.
(095340/005180 각 ~58분 blind, 108490 은 `_SWING_POLL_STRATEGIES` 비대상이라 보강 경로 0.)

실측 계측:
    2026-08-19T09:30:02 [priority_drop] ... total_subscribed=45 max=41 high_count=9
                                          pool_sessions=7 pool_slots=287 pool_subscribed=290
메인 세션이 이미 45/41 로 **KIS 서버 한도**를 넘긴 상태였다. `[ws_action_summary]
label=main tr_id=H0UNMKO0 window=300s SUBSCRIBE=10~11` 반복 = main 41 중 ~25% 를
**VI 관찰 채널**이 선점하고 있었다. `UNSUBSCRIBE=0` → 청산 종목 VI 영구 잔존(슬롯 누수).

## 판정

`MAX_SUBSCRIPTIONS = 41`(websocket.py:30)은 **KIS 서버 측 한도**다. `bypass_limit=True`
는 로컬 가드만 건너뛸 뿐 서버 한도는 우회 못 하고 초과분이 OPSP0008 로 되돌아온다.
cycle 32 R4 "HIGH 절대 보장"의 원래 대상은 **시세(tick)** 이고, H0UNMKO0 는 VI/거래정지
**관찰** 채널(소비처 = `is_ticker_stale_excluded` + 서킷브레이커 UI, 매수/매도 게이트
미연계)이다. cycle214 가 "보유 종목이니까 HIGH" 라벨만 보고 tick 규칙을 기계적으로
미러한 결과 **관찰 채널이 생명선 채널과 같은 41 슬롯을 놓고 경쟁**하게 됐다.

→ VI 는 메인에 **한 건도** 붙이지 않는다. 보조 세션에 **직접**(풀 API 미경유) **델타**로
   붙이되, 대상은 **보유 + 익일청산(HIGH) 뿐**이다.

## 정정 (적대적 리뷰 HIGH 2건)

**F2 — 후보(LOW) VI 배치 삭제.** 아래 F-P 로 인해 기존 후보 VI 는 **실질 noop** 이었다.
이를 보조 세션 직접 호출로 옮기는 것은 "이동"이 아니라 죽어 있던 경로의 **7배 활성화**
(보유 10건 → 최대 70건)이고, `scanner` 의
`remaining = _pool_total_slots - len(kis_ws_pool._subscriptions)` 는 pool `_subscriptions`
가 `(tr_id, tr_key)` 합집합이라 **VI 를 포함해 센다** → tick 후보 슬롯 −48~60. breakout
순서가 BFB→VCP→VB→LTV 라 잘리는 건 tail 의 **VB/LTV** 이고 VB 는 `_SWING_POLL_STRATEGIES`
비대상 = REST 폴 보강 0 = **완전 사각** = 08-19 와 같은 클래스의 새 피해.
→ 후보 VI 는 **되살리지 않는다**(행위 보존).

**F1 — 예약 슬롯 제거, 41 하드리밋 + 만석 WARNING.** 예약선 8 은 후보 VI 70건이 tick 을
밀어낼까 봐 둔 것이다. 후보가 사라지면 예약할 이유가 없다. 반대로 남겨두면 08-19 실측
(`pool_slots=287 pool_subscribed=290` = 보조 6세션 ≈40.8/41)에서 **보유 VI 가 전량 skip**
되어 변경 전(`bypass_limit=True` 무조건 성공, 실측 SUBSCRIBE=10~11)보다 **퇴행**한다.
전 세션 만석이면 `skipped_no_slot>0` → 요약 INFO 와 **별도 WARNING 1행**으로 관측한다
(보유 VI 결손 → `is_ticker_stale_excluded` 무력 → stale 강제 재구독 지속 → LMS 압력).

## 왜 `kis_ws_pool.subscribe` 도 쓰면 안 되는가 (F-P)

`websocket_pool._ticker_to_session` 은 `(tr_id, tr_key)` 가 아니라 **`tr_key`(종목코드)
단일 키**다(`websocket_pool.py:96`). `_scan_loop` 는 TICK 구독을 먼저 돌리고 그 **뒤에**
VI 훅을 돌린다. 따라서 (a) 이미 TICK 이 붙은 종목은 step2 "중복 ticker" 분기에서 SEND
없이 label 만 반환 = VI 가 애초에 안 나가고, (b) TICK 이 drop 된 종목만 VI 가 보조에
붙으면서 `_ticker_to_session[t] = quote-N` 이 찍혀 **그 종목의 TICK 이 영구히 안 붙는다.**
→ VI 는 `pool.subscribe`/`pool.unsubscribe` 를 **호출하지 않는다**(세션 객체 직접 호출).

## 범위

변경은 `src/engine/scheduler.py` 단일 함수 + 필드 1개. **8영역 diff 0**
(`realtime/websocket.py`, `realtime/websocket_pool.py`, `engine/scanner.py` 무변경).

설계: 사이클 221 설계 §4 회귀 가드 목록 (a)~(d).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.protocol import State

from src.api.market_operation import MARKET_OP_TR_ID
from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit

_LOGGER = "src.engine.scheduler"


# ---------------------------------------------------------------------------
# 픽스처 — 메인 세션 / 보조 세션(_quotes) 격리
# ---------------------------------------------------------------------------

def _make_scheduler(*, positions: set[str], pending: set[str] = frozenset()):
    """subscribe 훅만 태우기 위한 최소 스케줄러 인스턴스.

    `_market_op_subs` 는 Green 구현에서 `__init__` 이 선언하는 필드 —
    `__new__` 경로에서는 직접 주입해 `__init__` 계약을 흉내낸다
    (선언 자체는 `test_init_declares_market_op_subs` 가 실인스턴스로 검증).
    """
    sched = TradingScheduler.__new__(TradingScheduler)
    strat = SimpleNamespace(
        state=SimpleNamespace(positions={t: object() for t in positions})
    )
    registry = MagicMock()
    registry.all.return_value = [strat]
    sched.registry = registry
    sched._pending_next_day_clear = {(t, "s") for t in pending}
    sched._market_op_subs = {}
    return sched


def _make_quote_session(label: str, *, filled: int = 0):
    """보조 세션 1개 mock — `_subscriptions`(로컬 41 가드 소스) + subscribe/unsubscribe."""
    ws = MagicMock()
    ws._label = label
    ws._subscriptions = {("H0UNCNT0", f"{9_000_00 + i:06d}") for i in range(filled)}

    async def _sub(tr_id, tr_key, *, bypass_limit=False):
        ws._subscriptions.add((tr_id, tr_key))

    async def _unsub(tr_id, tr_key):
        ws._subscriptions.discard((tr_id, tr_key))

    ws.subscribe = AsyncMock(side_effect=_sub)
    ws.unsubscribe = AsyncMock(side_effect=_unsub)
    return ws


def _patch_ws(
    monkeypatch,
    *,
    quotes: list | None = None,
    main_filled: int = 10,
    main_tick: int = 10,
):
    """메인 `kis_ws` + 풀 `kis_ws_pool` 격리.

    - `fake_main._subscriptions` / `get_subscribed_tickers()` = 메인 점유 계측 소스
      (요약 로그 `main_total` / `main_tick` / `main_over` read-only 산출).
    - `fake_pool._quotes` = 보조 세션 리스트. VI 는 여기에 **직접** 붙는다.
    """
    fake_main = MagicMock()
    fake_main._ws = SimpleNamespace(state=State.OPEN)
    fake_main.subscribe = AsyncMock(return_value=None)
    fake_main.unsubscribe = AsyncMock(return_value=None)
    fake_main._subscriptions = {
        ("H0UNCNT0", f"{100000 + i:06d}") for i in range(main_filled)
    }
    fake_main.get_subscribed_tickers = MagicMock(
        return_value={f"{100000 + i:06d}" for i in range(main_tick)}
    )

    fake_pool = MagicMock()
    fake_pool.subscribe = AsyncMock(return_value="quote-1")
    fake_pool.unsubscribe = AsyncMock(return_value=None)
    fake_pool._quotes = list(quotes) if quotes is not None else [
        _make_quote_session("quote-1"), _make_quote_session("quote-2"),
    ]

    monkeypatch.setattr("src.realtime.websocket.kis_ws", fake_main, raising=False)
    monkeypatch.setattr(
        "src.realtime.websocket_pool.kis_ws_pool", fake_pool, raising=False
    )
    return fake_main, fake_pool


def _all_session_subscribe_calls(fake_pool) -> list:
    calls = []
    for q in fake_pool._quotes:
        calls.extend(q.subscribe.await_args_list)
    return calls


# ---------------------------------------------------------------------------
# (a) main 슬롯이 tick 을 위해 확보되는가
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_high_vi_never_subscribes_on_main(monkeypatch) -> None:
    """(a-1) HIGH(보유+익일청산) VI 도 메인 세션에 **한 건도** 붙지 않는다.

    사고 원인 2 — `scheduler.py:3283` 이 HIGH 를 `kis_ws.subscribe(bypass_limit=True)`
    로 메인 직접 구독해 main 41 중 ~25% 를 VI 가 선점했다.
    """
    fake_main, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"095340", "005180"}, pending={"108490"})

    await sched._subscribe_market_operation_tickers({"111111"})

    assert fake_main.subscribe.await_count == 0, (
        "VI(H0UNMKO0) 는 메인 세션 구독 금지 — tick 슬롯을 빼앗아 OPSP0008 유발"
    )
    main_vi = [
        c for c in fake_main.subscribe.await_args_list
        if c.args and c.args[0] == MARKET_OP_TR_ID
    ]
    assert main_vi == []


@pytest.mark.asyncio
async def test_no_bypass_limit_true_in_any_vi_call(monkeypatch) -> None:
    """(a-2) 어떤 VI 구독도 `bypass_limit=True` 를 쓰지 않는다.

    `bypass_limit=True` 는 **로컬 가드만** 우회하고 KIS 서버 한도 41 은 못 넘는다
    (websocket.py:468). 관찰 채널이 그 계약을 빌려 쓰면 초과분이 OPSP0008 로 온다.
    """
    fake_main, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"095340"}, pending=set())

    await sched._subscribe_market_operation_tickers({"111111", "222222"})

    calls = list(fake_main.subscribe.await_args_list) + _all_session_subscribe_calls(fake_pool)
    assert calls, "VI 구독이 아예 발생하지 않았다 — 픽스처/라우팅 확인"
    for c in calls:
        assert c.kwargs.get("bypass_limit") is not True, (
            "VI 구독은 bypass_limit=True 금지 — 로컬 41 가드가 살아 있어야 한다"
        )


@pytest.mark.asyncio
async def test_summary_reports_main_occupancy(monkeypatch, caplog) -> None:
    """(a-3) 요약 로그가 메인 세션 점유를 매 사이클 노출한다.

    사고 사실 #4 — main 45/41 초과가 `[priority_drop]`(포화 시에만 발화) 안에 묻혀
    보이지 않았다. VI 훅은 5분마다 drop 유무와 무관하게 점유를 찍는다.
    """
    fake_main, fake_pool = _patch_ws(monkeypatch, main_filled=30, main_tick=28)
    sched = _make_scheduler(positions={"095340"}, pending=set())

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        await sched._subscribe_market_operation_tickers({"111111"})

    text = caplog.text
    assert "[market_op_subscribe_summary]" in text
    for key in ("main_direct=0", "main_tick=", "main_total=", "main_over="):
        assert key in text, f"요약 로그에 {key} 누락 — 메인 점유 은닉 재발"


@pytest.mark.asyncio
async def test_main_over_emits_warning(monkeypatch, caplog) -> None:
    """(a-4) 메인이 서버 한도 41 을 넘으면 포화 drop 이 없어도 WARNING 1행.

    08-19 실측 total_subscribed=45 max=41 재현.
    """
    fake_main, fake_pool = _patch_ws(monkeypatch, main_filled=45, main_tick=43)
    sched = _make_scheduler(positions={"095340"}, pending=set())

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        await sched._subscribe_market_operation_tickers({"111111"})

    assert "main_over=4" in caplog.text, "main_over = max(0, main_total - 41) 계측 의무"
    warns = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "market_op" in r.getMessage()
    ]
    assert len(warns) == 1, "메인 서버 한도 초과는 WARNING 1행으로 상시 노출 (5분 주기)"


# ---------------------------------------------------------------------------
# (b) 보유 종목 tick 이 VI 때문에 밀리지 않는가
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pool_subscribe_and_unsubscribe_never_called(monkeypatch) -> None:
    """(b-1) `kis_ws_pool.subscribe`/`unsubscribe` 미호출 = `_ticker_to_session` 무오염.

    F-P — 풀 맵은 `tr_key` 단일 키라 VI 가 경유하면 (a) 이미 TICK 이 붙은 종목은
    중복 분기로 SEND 자체가 안 되고 (b) TICK drop 종목은 VI 때문에 quote-N 으로
    기록돼 **TICK 이 영구히 안 붙는다**. 세션 객체를 직접 호출해 우회한다.
    """
    fake_main, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"095340"}, pending=set())

    await sched._subscribe_market_operation_tickers({"111111", "222222"})

    assert fake_pool.subscribe.await_count == 0, (
        "VI 는 pool.subscribe 미경유 — _ticker_to_session(tr_key 단일키) 오염 금지"
    )
    assert fake_pool.unsubscribe.await_count == 0, (
        "VI 해제도 pool.unsubscribe 금지 — ticker 키 pop 이 TICK 라우팅 기록을 지운다"
    )
    # cycle221 정정 — 후보 VI 는 실질 noop 이었으므로 배치하지 않는다(F2).
    # 배치는 보유 1종목(095340) 뿐이고 후보 2종목은 SEND 0건.
    placed = _all_session_subscribe_calls(fake_pool)
    assert [c.args[1] for c in placed] == ["095340"]


@pytest.mark.asyncio
async def test_holding_vi_placed_whenever_session_below_hard_limit(monkeypatch) -> None:
    """[의미 전환 b-2, F1] 예약 슬롯 **없음** — 보조 세션이 41 미만이면 보유 VI 는 반드시 배치.

    원래 계약: `len(ws._subscriptions) < MAX_SUBSCRIPTIONS - _MARKET_OP_QUOTE_RESERVE`(=33).
    이 예약선은 후보 VI 70건이 tick 을 밀어낼까 봐 둔 것인데, cycle221 정정으로 후보 VI 가
    사라져(F2) 예약할 이유가 없어졌다. 남겨두면 08-19 실측(보조 6세션 ≈40.8/41)에서
    **보유 VI 가 전량 skip** 되어 변경 전(`bypass_limit=True` 무조건 성공)보다 퇴행한다.

    경계 실증: 40/41(구 예약선 33 을 한참 넘김) 에서도 보유 VI 는 반드시 자리를 잡는다.
    """
    from src.realtime.websocket import MAX_SUBSCRIPTIONS

    near_full = _make_quote_session("quote-1", filled=MAX_SUBSCRIPTIONS - 1)
    fake_main, fake_pool = _patch_ws(monkeypatch, quotes=[near_full])
    sched = _make_scheduler(positions={"095340"}, pending=set())

    n = await sched._subscribe_market_operation_tickers({"111111"})

    assert [c.args[1] for c in near_full.subscribe.await_args_list] == ["095340"], (
        "41 미만이면 보유 VI 배치 의무 — 예약선(구 33) 재도입 금지"
    )
    assert fake_main.subscribe.await_count == 0, "메인 폴백은 여전히 금지"
    assert n == 1


@pytest.mark.asyncio
async def test_all_sessions_full_skips_and_warns(monkeypatch, caplog) -> None:
    """[신규 F1] 전 세션 만석 → 보유 VI skip + **WARNING 1행**(조용한 관찰 상실 금지).

    관찰 상실 자체는 허용된 교환(tick > VI)이지만 **은닉은 아니다**. 보유 VI 가 비면
    `is_ticker_stale_excluded` 가 VI/거래정지 종목을 stale 에서 못 빼 stale watcher 의
    강제 재구독이 지속되고 KIS LMS 압력이 올라간다 — 기각안 D(VI 전면 폐지)를 거부한
    바로 그 사유라, 같은 상태에 **조용히** 도달하면 안 된다.
    """
    from src.realtime.websocket import MAX_SUBSCRIPTIONS

    full = _make_quote_session("quote-1", filled=MAX_SUBSCRIPTIONS)
    fake_main, fake_pool = _patch_ws(monkeypatch, quotes=[full])
    sched = _make_scheduler(positions={"095340", "005180"}, pending=set())

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        n = await sched._subscribe_market_operation_tickers({"111111"})

    assert n == 0
    assert full.subscribe.await_count == 0, "만석 세션에는 배치 불가"
    assert fake_main.subscribe.await_count == 0, "만석이어도 메인 폴백 금지"
    assert "skipped_no_slot=2" in caplog.text, "요약 INFO 에 결손 수 계측"

    warns = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "[market_op_subscribe_no_slot]" in r.getMessage()
    ]
    assert len(warns) == 1, "전 세션 만석 = WARNING 1행 의무 (INFO 요약만으로는 비대칭)"
    msg = warns[0].getMessage()
    assert "is_ticker_stale_excluded" in msg, "결과 사슬(무력화 대상) 명시 의무"
    assert "LMS" in msg, "결과 사슬(LMS 압력) 명시 의무"


# 상수 부재(`_MARKET_OP_QUOTE_RESERVE` 재도입 차단) 봉인은 AST 정본에 있다:
#   tests/unit/ast/test_cycle221_ast_market_op_no_main.py::test_quote_reserve_constant_absent


@pytest.mark.asyncio
async def test_candidates_never_reach_session_subscribe(monkeypatch) -> None:
    """[신규 F2] 후보(비HIGH) 종목은 `ws.subscribe` 대상에 **포함되지 않는다**.

    기존 풀 경유 후보 VI 는 `_ticker_to_session`(tr_key 단일키) 중복 분기 때문에 SEND 가
    나간 적이 없다 = 실질 noop. 세션 직접 호출로 되살리면 최대 70건이 처음으로 진짜
    SEND 되고 pool `_subscriptions` 합집합을 통해 tick 후보 슬롯을 48~60 잠식한다.
    """
    fake_main, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"095340"}, pending={"005180"})

    candidates = {f"{i:06d}" for i in range(70)}
    n = await sched._subscribe_market_operation_tickers(candidates)

    placed = {c.args[1] for c in _all_session_subscribe_calls(fake_pool)}
    assert placed == {"095340", "005180"}, "HIGH 2종목만 — 후보 70건 SEND 0"
    assert placed.isdisjoint(candidates - {"095340", "005180"})
    assert n == 2
    assert sched._market_op_subs.keys() == {"095340", "005180"}


@pytest.mark.asyncio
async def test_no_quote_sessions_means_no_vi_and_no_main_fallback(
    monkeypatch, caplog
) -> None:
    """(b-3) 보조 세션 0개면 VI 는 전량 skip — **메인 폴백 명시 금지**.

    이 사이클의 핵심 규칙. 관찰 채널이 없어지는 것보다 tick 슬롯을 지키는 게 우선.
    """
    fake_main, fake_pool = _patch_ws(monkeypatch, quotes=[])
    sched = _make_scheduler(positions={"095340"}, pending={"005180"})

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        n = await sched._subscribe_market_operation_tickers({"111111"})

    assert n == 0
    assert fake_main.subscribe.await_count == 0, "보조 0 → 메인 폴백 절대 금지"
    assert "[market_op_no_quote_session]" in caplog.text, "skip 사유 INFO 1행 의무"


@pytest.mark.asyncio
async def test_vi_never_exceeds_session_limit(monkeypatch) -> None:
    """(b-4) 보조 세션 배치도 로컬 41 가드가 살아 있다 (bypass 미사용).

    로컬 가드를 남겨두면 보조 세션도 서버 한도를 넘길 수 없다.
    """
    fake_main, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"095340", "005180"}, pending=set())

    await sched._subscribe_market_operation_tickers({"111111"})

    calls = _all_session_subscribe_calls(fake_pool)
    assert calls
    for c in calls:
        assert c.args[0] == MARKET_OP_TR_ID
        assert c.kwargs.get("bypass_limit", False) is False


# ---------------------------------------------------------------------------
# (c) 슬롯 누수가 막히는가
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_released_when_ticker_leaves_target(monkeypatch) -> None:
    """(c-1) target 에서 빠진 종목의 VI 는 델타 해제된다.

    사고 원인 3 — `MARKET_OP_TR_ID` 참조는 subscribe 2곳뿐, unsubscribe 0곳.
    실측 `UNSUBSCRIBE=0` → 슬롯 영구 누수.
    """
    fake_main, fake_pool = _patch_ws(monkeypatch)
    # cycle221 정정 — 후보 VI 는 실질 noop 이었으므로 배치하지 않는다(F2).
    # 델타 해제 계약은 그대로이므로 target 소스를 후보 → **보유**로 옮겨 검증한다.
    sched = _make_scheduler(positions={"111111", "222222"}, pending=set())

    await sched._subscribe_market_operation_tickers(set())
    assert set(sched._market_op_subs) == {"111111", "222222"}

    sched.registry.all.return_value = [
        SimpleNamespace(state=SimpleNamespace(positions={"111111": object()}))
    ]
    await sched._subscribe_market_operation_tickers(set())

    released = [
        c for q in fake_pool._quotes for c in q.unsubscribe.await_args_list
        if c.args == (MARKET_OP_TR_ID, "222222")
    ]
    assert len(released) == 1, "target 이탈 종목은 세션 객체로 정확히 1회 해제"
    assert "222222" not in sched._market_op_subs


@pytest.mark.asyncio
async def test_position_closed_releases_vi(monkeypatch) -> None:
    """(c-2) 청산돼 후보에도 없는 보유 종목의 VI 가 해제된다 (사실 #3 재발 차단)."""
    fake_main, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"095340"}, pending=set())

    await sched._subscribe_market_operation_tickers(set())
    assert "095340" in sched._market_op_subs

    # 청산 — 보유 목록에서 사라지고 후보에도 없다.
    sched.registry.all.return_value = [
        SimpleNamespace(state=SimpleNamespace(positions={}))
    ]
    await sched._subscribe_market_operation_tickers(set())

    released = [
        c for q in fake_pool._quotes for c in q.unsubscribe.await_args_list
        if c.args == (MARKET_OP_TR_ID, "095340")
    ]
    assert len(released) == 1
    assert sched._market_op_subs == {}


@pytest.mark.asyncio
async def test_release_uses_session_not_pool(monkeypatch) -> None:
    """(c-3) 해제는 세션 객체 직접 호출 — `pool.unsubscribe` 금지(맵 pop 차단)."""
    fake_main, fake_pool = _patch_ws(monkeypatch)
    # cycle221 정정 — 후보 VI 는 실질 noop 이었으므로 배치하지 않는다(F2). target 은 보유.
    sched = _make_scheduler(positions={"111111"}, pending=set())

    await sched._subscribe_market_operation_tickers(set())
    sched.registry.all.return_value = [
        SimpleNamespace(state=SimpleNamespace(positions={}))
    ]
    await sched._subscribe_market_operation_tickers(set())

    session_unsubs = sum(len(q.unsubscribe.await_args_list) for q in fake_pool._quotes)
    assert session_unsubs == 1, "세션 객체 직접 해제 1회"
    assert fake_pool.unsubscribe.await_count == 0, (
        "pool.unsubscribe 는 _ticker_to_session[ticker] 를 pop 해 TICK 라우팅을 지운다"
    )


def test_init_declares_market_op_subs() -> None:
    """(c-4a) `__init__` 이 `_market_op_subs` 를 선언한다."""
    sched = TradingScheduler()
    assert sched._market_op_subs == {}


def test_reset_daily_state_clears_market_op_subs() -> None:
    """(c-4b) `_reset_daily_state` 동행 clear + 기존 `reset_market_op_state()` 보존.

    CLAUDE.md 「`_reset_daily_state` 동행 reset 의무」.
    """
    sched = TradingScheduler()
    sched._market_op_subs["095340"] = object()

    with patch.object(sched.registry, "all", return_value=[]), \
         patch.object(sched, "order_engine", MagicMock(
             _selling=set(), _selling_since={}, _filled_qty={}, _order_qty={},
             _order_strategy={}, _order_ticker={}, _pending_buy_orders={},
             _pending_cancel_tasks={}, reset_daily_state=MagicMock(),
         )), \
         patch.object(sched, "risk_manager", MagicMock(reset_daily_state=MagicMock())), \
         patch("src.engine.market_operation_monitor.reset_market_op_state") as reset_mo:
        sched._reset_daily_state()

    assert sched._market_op_subs == {}, "VI 구독 추적 맵 일일 clear 누락"
    reset_mo.assert_called_once()


# ---------------------------------------------------------------------------
# (d) LMS chain 위험이 커지지 않는가
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_idempotent_second_cycle_sends_nothing(monkeypatch) -> None:
    """(d-1) 동일 target 2회 호출 → 2번째 SEND 0건.

    현행은 매 5분 동일 10~11건을 재SEND(`[ws_action_summary] SUBSCRIBE=10~11`).
    이번 변경은 SEND 총량을 **감소**시킨다 (LMS chain 완화).
    """
    fake_main, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"095340", "005180"}, pending=set())

    await sched._subscribe_market_operation_tickers({"111111"})
    first = sum(len(q.subscribe.await_args_list) for q in fake_pool._quotes)
    # cycle221 정정 — 후보 VI 는 실질 noop 이었으므로 배치하지 않는다(F2). 보유 2종목뿐.
    assert first == 2

    await sched._subscribe_market_operation_tickers({"111111"})
    second = sum(len(q.subscribe.await_args_list) for q in fake_pool._quotes) - first
    assert second == 0, "이미 살아있는 VI 구독 재SEND 금지"


@pytest.mark.asyncio
async def test_total_sends_bounded_by_delta(monkeypatch) -> None:
    """(d-2) target 이 N→N+1 이면 SEND 1건 + 해제 0건.

    cycle221 정정 — 후보 VI 는 실질 noop 이었으므로 배치하지 않는다(F2).
    target 증가는 **신규 매수(보유 추가)** 로 재현한다.
    """
    fake_main, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"111111", "222222"}, pending=set())

    await sched._subscribe_market_operation_tickers(set())
    base = sum(len(q.subscribe.await_args_list) for q in fake_pool._quotes)
    assert base == 2

    sched.registry.all.return_value = [
        SimpleNamespace(
            state=SimpleNamespace(
                positions={t: object() for t in ("111111", "222222", "333333")}
            )
        )
    ]
    await sched._subscribe_market_operation_tickers(set())
    delta = sum(len(q.subscribe.await_args_list) for q in fake_pool._quotes) - base
    unsubs = sum(len(q.unsubscribe.await_args_list) for q in fake_pool._quotes)

    assert delta == 1
    assert unsubs == 0


@pytest.mark.asyncio
async def test_rate_limit_sleep_preserved(monkeypatch) -> None:
    """(d-3) 0.05s Rate Limit 스로틀 유지 — sleep 횟수 == 실제 SEND 횟수 (사이클 17)."""
    fake_main, fake_pool = _patch_ws(monkeypatch)
    sched = _make_scheduler(positions={"095340"}, pending=set())

    sleeps: list[float] = []

    async def _fake_sleep(secs, *a, **kw):
        sleeps.append(secs)

    with patch("asyncio.sleep", new=AsyncMock(side_effect=_fake_sleep)):
        await sched._subscribe_market_operation_tickers({"111111", "222222"})

    sends = sum(len(q.subscribe.await_args_list) for q in fake_pool._quotes)
    # cycle221 정정 — 후보 VI 는 실질 noop 이었으므로 배치하지 않는다(F2). 보유 1종목.
    assert sends == 1
    assert len(sleeps) == sends, "SEND 마다 0.05s 스로틀"
    assert all(s == pytest.approx(0.05) for s in sleeps)


@pytest.mark.asyncio
async def test_connection_closed_single_warning_no_error(monkeypatch, caplog) -> None:
    """(d-4) 루프 중 `ConnectionClosedError` → 즉시 break + WARNING 1행 (ERROR 0).

    2026-08-07 계약 이식 — 재연결 중 예상 상태라 종목별 ERROR/traceback 금지.
    """
    q1 = _make_quote_session("quote-1")
    calls = {"n": 0}

    async def _sub(tr_id, tr_key, *, bypass_limit=False):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise ConnectionClosedError(None, None)

    q1.subscribe = AsyncMock(side_effect=_sub)
    fake_main, fake_pool = _patch_ws(monkeypatch, quotes=[q1])
    sched = _make_scheduler(positions={"051905", "073240", "079160", "103140"})

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        await sched._subscribe_market_operation_tickers(set())

    assert calls["n"] == 2, "ConnectionClosedError 후 즉시 break"
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    warns = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "market_op" in r.getMessage()
    ]
    assert not errors, "재연결 중 예상 상태 — ERROR/traceback 금지"
    assert len(warns) == 1, "1행 WARNING 으로 집약"
