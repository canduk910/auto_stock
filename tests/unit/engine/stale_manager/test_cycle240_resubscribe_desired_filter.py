"""cycle240 Red — `resubscribe_stale_priority` LOW 후보를 **desired 집합과 교집합**.

> 정본 스펙: `_workspace/red/cycle240_resubscribe_desired_filter_spec.md`
> 시정 대상: `src/engine/stale_watcher_core.py::resubscribe_stale_priority` 단독.

## 결함 (08-31 포렌식 ⓑ, MEDIUM)

`resubscribe_stale_priority`(5분, `scheduler._scan_loop` 호출)의 stale 후보 소스는
`scanner.ticker_last_tick` **전수**(`stale_watcher_core.py:449-453`)다. 그 dict 는
per-ticker pop 이 src 전체 0건이고 유일 정리가 20:10 정산의 `clear()` 라, 09:00 에
한 번 tick 을 받은 종목은 **매도·후보 이탈 후에도 20:10 까지 후보 자격을 유지**한다.

결과 = 같은 `_scan_loop` 이터레이션 안에서 `delta_unsubscribe_dropped` 가 뺀 종목을
`resubscribe_stale_priority` 가 12초 뒤 되살리는 **핑퐁**. EC2 실측(09-02): 09:40 RESUB
9종목 → 09:45 DELTA 동일 9 → 10:00 RESUB … 1:1 무한 페어링. 034020 은 09:00:29 매도 후
19:59 까지 **35회** 재구독됐다. 우선순위 LOW 라 메인 41 하드리밋은 안 깨지지만
구독 슬롯·KIS SEND 낭비 + 로그 오염 + `_stale_last_resubscribe_at` 오염이다.

형제 경로 `check_and_resubscribe_stale`(120s)은 소스가 `get_subscribed_tickers()`
(=실제 구독 집합)라 같은 결함이 없다 — **비대칭이 뿌리**다.

## 시정 계약 (스펙 §2)

분리 대입(`:477-478`) **직후**, cycle216 A(동시호가) / B(throttle) / cap **앞** 에
`low_targets` 만 desired 집합과 교집합한다.

- `desired_low = breakout ∪ momentum`
  - breakout = `scheduler._collect_breakout_tickers()` (VB/LTV/BFB/VCP scanned
    ∖ `_universe_excluded_today`) — **scheduler 소유 소스 = 활성 게이트의 유일 근거**
  - momentum = `scanner._last_scan_result` — **가산 전용**(활성 판정 불참)
- 활성 게이트 = `bool(breakout) ∧ HIGH 수집 무예외`. 하나라도 거짓이면 필터 미적용
  (현행 byte 동일) — **fail-open 방향 고정**. desired 공집합에 필터를 적용해 LOW 를
  조용히 전멸시키는 구현은 계약 위반이다.
- HIGH(보유 ∪ 익일청산)는 `low_targets` 에 **애초에 들어가지 않으므로** 필터 경로를
  지나지 않는다(구조적 면제) + HIGH 수집 실패 시 게이트 off(이중 보호).
- 관측 = 기존 INFO 1행 확장:
  `[stale_priority_resubscribe] count=%d tickers=%s desired_low=%d
   filtered_not_desired=%d filtered_sample=%s` (`count=` 첫 필드 byte 보존, sample ≤10).
  신규 마커 0 · cap 0 (행 빈도 불변 = 5분 1행이라 cap 불필요).

## Red 시점 결과 (현행 코드 기준 기대)

| ID | 기대 |
|----|------|
| F-1 | **FAIL** — 현행은 desired 밖 유령 X/Y 도 재구독 + INFO 에 신규 필드 부재 |
| F-2 | **FAIL** — delta 가 뺀 종목을 곧바로 되살림(핑퐁 실증) |
| F-3 | **FAIL** — HIGH 는 통과하나 LOW 유령이 걸러지지 않음 |
| F-4 | PASS(회귀 가드) — 게이트 off 4경로에서 현행 행위 완전 보존 |
| F-5 | **FAIL** — momentum 가산분 구분 없이 전량 재구독 |
| F-6 | **FAIL** — `_universe_excluded_today` 축출분이 desired 에서 이탈해야 하는데 재구독 |
| F-7 | **FAIL** — 필터 부재 → cap 이 미필터 LOW 를 먼저 소비 |
| F-8 | **FAIL** — 동시호가 WARNING 의 `low=` 가 필터 통과분이 아님 + 신규 필드 부재 |
| F-9 | **FAIL** — INFO 에 `desired_low=`/`filtered_not_desired=`/`filtered_sample=` 부재 |
| F-10 | **FAIL** — `_collect_low_desired` 헬퍼 부재 |
| F-11 | **FAIL** — 걸러져야 할 유령이 `_stale_last_resubscribe_at` 를 오염시킴 |
| F-12 | **FAIL** — 미구독 유령에도 `_ticker_to_session.pop` 발화(cycle215/217 계약과 무관한 낭비) |
| F-13 | PASS(회귀 가드) — 레거시 `_EmptyRegistry` 픽스처 경로 무변경 |

fixture 는 cycle216 파일에서 import 재사용(중복 정의 금지). caplog 는
`logger="src.engine.scheduler"`(사이클 60 I1 바인딩).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

# cycle216 fixture 재사용 (스펙 §4.1 — 중복 정의 금지)
# cycle240-R1: `_capture_scheduler_warnings()` 는 미사용 — 그 컨텍스트가
# `src.engine.scheduler` 로거 레벨을 WARNING 으로 올려 같은 블록 안 INFO
# (`[stale_priority_resubscribe]`) 를 방출 단계에서 흡수한다(F-8 이 caplog 와
# 함께 쓰면 `_info_lines(caplog)` 가 항상 빈 리스트). F-8 은 caplog(INFO 레벨,
# WARNING 도 함께 포착) 하나로 WARNING/INFO 를 동시에 관측한다.
from tests.unit.engine.stale_manager.test_cycle216_priority_throttle_call_auction import (  # noqa: F401
    _make_scheduler_with_high_tickers,
    _make_spy_pool,
    _session_tracker_mock,
)

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_FROZEN = "2026-09-02 10:00:00"
_BASE = datetime(2026, 9, 2, 10, 0, 0, tzinfo=KST)
_STALE = _BASE - timedelta(seconds=120)

_INFO_PREFIX = "[stale_priority_resubscribe] "


# ===========================================================================
# 신규 헬퍼 (cycle216 에 없는 것만 — INFO 캡처 / 상태 있는 pool / desired 주입)
# ===========================================================================
def _info_lines(caplog) -> list[str]:
    """`[stale_priority_resubscribe] ` INFO 본문만 (cap_exceeded WARNING 과 분리)."""
    return [
        r.getMessage() for r in caplog.records
        if r.getMessage().startswith(_INFO_PREFIX)
    ]


def _make_stateful_pool(subscribed=None, ticker_to_session=None):
    """구독 상태를 **변이**하는 pool 대역 — delta ↔ resubscribe 페어링 재현용.

    cycle217 `_make_guard_spy_pool` 은 `get_subscribed_tickers` 가 고정 set 이라
    "delta 가 뺀 뒤 재구독이 되살린다" 는 시간 축을 재현할 수 없다. 여기서는
    `unsubscribe` / `unsubscribe_in_pool` / `subscribe` 가 같은 set 을 갱신한다.
    """
    state: set[str] = set(subscribed or set())
    call_log: list[tuple] = []

    async def _unsub(tr_id, tr_key):
        call_log.append(("unsub", tr_id, tr_key))
        state.discard(tr_key)

    async def _unsub_pool(tr_id, tr_key):
        call_log.append(("unsub_pool", tr_id, tr_key))
        state.discard(tr_key)

    async def _sub(tr_id, tr_key, *, priority="LOW", bypass_limit=False):
        call_log.append(("sub", tr_id, tr_key, priority, bypass_limit))
        state.add(tr_key)
        return "main"

    pool = MagicMock()
    pool.unsubscribe = AsyncMock(side_effect=_unsub)
    pool.unsubscribe_in_pool = AsyncMock(side_effect=_unsub_pool)
    pool.subscribe = AsyncMock(side_effect=_sub)
    pool.get_subscribed_tickers = MagicMock(side_effect=lambda: set(state))
    pool._ticker_to_session = dict(ticker_to_session or {})
    return pool, call_log, state


def _arm_breakout(sched, tickers):
    """breakout desired 주입 — 인스턴스 속성이 `_collect_breakout_tickers` 메서드를 가린다.

    (F-6 만 실제 `_collect_breakout_tickers` 본체를 경유해 `_universe_excluded_today`
     제거가 desired 에 반영되는지 검증한다.)
    """
    sched._collect_breakout_tickers = lambda: list(tickers)


def _subscribed_tickers(pool) -> list[str]:
    return [c.args[1] for c in pool.subscribe.await_args_list]


# ===========================================================================
# F-1 (HIGH, 현행 FAIL — 핵심) — desired 밖 유령은 재구독 대상에서 제외
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_1_ghost_tickers_outside_desired_are_filtered(caplog):
    """F-1: 매도 완료·후보 이탈 종목(=desired 밖)이 stale 이어도 재구독하지 않는다.

    시나리오: positions ∅ / breakout desired = ['000100','000200'] / momentum = []
              stale = 000100, 000200, 000300(유령), 000400(유령)

    현행: `ticker_last_tick` 전수가 소스라 4종목 전부 재구독 → FAIL.
    시정 후: desired 교집합으로 000300/000400 탈락 → result == ['000100','000200'],
             INFO 에 `desired_low=2 filtered_not_desired=2 filtered_sample=['000300', '000400']`.
    """
    from src.engine import stale_manager

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    sched = _make_scheduler_with_high_tickers()          # HIGH 0
    _arm_breakout(sched, ["000100", "000200"])           # 게이트 활성
    ticker_last_tick = {t: _STALE for t in ("000100", "000200", "000300", "000400")}
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["000100", "000200"], (
        "desired(breakout ∪ momentum) 밖 LOW 유령은 재구독 대상에서 제외 의무. "
        "현행은 `scanner.ticker_last_tick` 전수를 소스로 써서 매도·이탈 종목까지 "
        f"되살린다(핑퐁 결함 ⓑ) → FAIL. 실제: {result}"
    )
    for ghost in ("000300", "000400"):
        assert ghost not in _subscribed_tickers(pool), (
            f"유령 {ghost} 에 subscribe SEND 금지 (KIS SEND·구독 슬롯 낭비). "
            f"실제 subscribe: {_subscribed_tickers(pool)}"
        )

    lines = _info_lines(caplog)
    assert len(lines) == 1, f"[stale_priority_resubscribe] INFO 1행 의무. 실제: {lines}"
    msg = lines[0]
    assert "desired_low=2" in msg, (
        f"관측 필드 `desired_low` (활성 시 desired 크기) 노출 의무. 실제: {msg}"
    )
    assert "filtered_not_desired=2" in msg, (
        "관측 필드 `filtered_not_desired` (걸러진 유령 수 — D+1 판독의 분자) 의무. "
        f"실제: {msg}"
    )
    assert "filtered_sample=['000300', '000400']" in msg, (
        f"관측 필드 `filtered_sample` (≤10 샘플) 의무. 실제: {msg}"
    )


# ===========================================================================
# F-2 (HIGH, 현행 FAIL) — delta ↔ resubscribe 핑퐁 실증
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_2_delta_unsubscribe_then_resubscribe_pingpong_stopped():
    """F-2: 같은 `_scan_loop` 이터레이션 안에서 delta 가 해제한 종목을 되살리지 않는다.

    `_scan_loop` 실순서: `new_set` → `_delta_unsubscribe_dropped(new_set)`(빼기) →
    `subscribe_filtered_stocks` → … → `_resubscribe_stale_priority(cap=10)`.
    EC2 실측(09-02) = RESUB 9 → 5분 뒤 DELTA 동일 9 의 1:1 무한 페어링.

    현행: 000300 이 delta 로 빠진 직후 재구독 → FAIL.
    시정 후: 000300 ∉ desired → 재구독 0.
    """
    from src.engine import stale_manager, stale_session_recovery

    sched = _make_scheduler_with_high_tickers()
    _arm_breakout(sched, ["000100"])                     # new_set 과 동치인 desired
    pool, call_log, state = _make_stateful_pool(
        subscribed={"000100", "000300"},
        ticker_to_session={"000100": "main", "000300": "main"},
    )
    ticker_last_tick = {"000100": _STALE, "000300": _STALE}

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        dropped = await stale_session_recovery.delta_unsubscribe_dropped(sched, {"000100"})
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert dropped == ["000300"], f"delta 는 new_set 밖 000300 만 해제. 실제: {dropped}"
    assert "000300" not in result, (
        "delta 가 방금 해제한 종목을 12초 뒤 재구독하면 핑퐁이다 — desired 교집합으로 "
        f"차단 의무. 현행은 되살림 → FAIL. 실제 result: {result}"
    )
    assert "000300" not in state, (
        f"해제 상태 유지 의무(재구독 SEND 0). 실제 구독 집합: {sorted(state)}"
    )
    assert "000100" in result, (
        f"desired 안의 stale 종목은 종전대로 재구독(회귀 0). 실제: {result}"
    )


# ===========================================================================
# F-3 (HIGH, 현행 FAIL) — HIGH(보유 ∪ 익일청산)는 desired 무관 절대 통과
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_3_high_tickers_bypass_desired_filter(caplog):
    """F-3: 보유·익일청산 종목은 desired 에 없어도 재구독되고 집계 밖이다.

    필터는 `low_targets` 에만 걸리므로 HIGH 는 **구조적으로** 필터 경로를 지나지 않는다
    (스펙 §3-1). `filtered_not_desired` 는 LOW 유령만 센다.

    현행: HIGH 는 통과하나 LOW 유령 000300 도 함께 재구독 + 신규 필드 부재 → FAIL.
    """
    from src.engine import stale_manager

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    sched = _make_scheduler_with_high_tickers(
        positions=["005930"], ndc={("000660", "volatility_breakout")},
    )
    _arm_breakout(sched, ["000100"])                     # HIGH 2종목은 desired 밖
    ticker_last_tick = {
        t: _STALE for t in ("005930", "000660", "000100", "000300")
    }
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert {"005930", "000660"} <= set(result), (
        "HIGH(보유 ∪ `_pending_next_day_clear`) 재구독 보장은 **불변 계약**이다 — "
        f"desired 밖이어도 절대 잘리지 않는다. 실제: {result}"
    )
    high_calls = [
        c for c in pool.subscribe.await_args_list if c.args[1] in ("005930", "000660")
    ]
    assert len(high_calls) == 2
    for call in high_calls:
        assert call.kwargs.get("priority") == "HIGH"
        assert call.kwargs.get("bypass_limit") is True

    assert "000300" not in result, (
        f"LOW 유령만 걸러진다. 현행은 필터 부재 → FAIL. 실제: {result}"
    )
    assert "000100" in result

    msg = _info_lines(caplog)[0]
    assert "filtered_not_desired=1" in msg, (
        "HIGH 는 `filtered_not_desired` 집계 밖 — LOW 유령 1건만 계상 의무. "
        f"실제: {msg}"
    )


# ===========================================================================
# F-4 (회귀 가드) — fail-open 4경로: 게이트 off 시 현행 행위 완전 보존
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
@pytest.mark.parametrize(
    "case",
    ["a_breakout_empty_momentum_present", "b_breakout_raises",
     "c_high_collect_raises", "d_empty_registry_no_get"],
)
async def test_f240_4_fail_open_gate_off_preserves_current_behavior(case):
    """F-4 (회귀 가드): desired 판정 불가·소스 부재 시 **필터 미적용**(현행 byte 동일).

    - (a) breakout 공집합 + momentum 만 존재 → 게이트 off.
          **`momentum` 은 활성 판정에 참여하지 않는다**(스펙 §0②). `scanner._last_scan_result`
          는 모듈 전역이라 다른 테스트의 `scan_stocks()` 잔여값이 남을 수 있고, 그것이
          게이트를 켜면 기존 LOW 회귀가 **수집 순서 의존**으로 깨진다.
    - (b) `_collect_breakout_tickers` 예외 → 게이트 off.
    - (c) HIGH 수집(`registry.all()`) 예외 → 게이트 off (HIGH 가 LOW 로 오분류된 뒤
          필터에 잘리는 경로를 닫는 이중 보호).
    - (d) 레거시 `_EmptyRegistry`(`.get` 부재) → AttributeError → 게이트 off.

    조용히 LOW 를 전멸시키는 구현(desired 공집합에 필터 적용)은 이 4케이스가 잡는다.
    Red/Green 양쪽 PASS — 게이트 off 구간의 **차분 0** 을 고정한다.
    """
    from src.engine import stale_manager

    sched = _make_scheduler_with_high_tickers()
    momentum: list[str] = []

    if case == "a_breakout_empty_momentum_present":
        _arm_breakout(sched, [])
        momentum = ["000900"]                            # desired 에는 있으나 게이트 불참
    elif case == "b_breakout_raises":
        def _boom():
            raise RuntimeError("registry 미주입")
        sched._collect_breakout_tickers = _boom
    elif case == "c_high_collect_raises":
        _arm_breakout(sched, ["000100"])
        broken = MagicMock()
        broken.all = MagicMock(side_effect=RuntimeError("registry.all 실패"))
        sched.registry = broken
    else:  # d_empty_registry_no_get
        class _EmptyRegistry:                            # `.get` 부재 (레거시 픽스처)
            def all(self):
                return []
        sched.registry = _EmptyRegistry()

    ticker_last_tick = {"000100": _STALE, "000300": _STALE}
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", momentum), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["000100", "000300"], (
        f"[{case}] 게이트 off = 필터 미적용(현행 byte 동일) 의무. fail-open 방향은 "
        "'LOW 를 조용히 전멸' 이 아니라 '현행 유지' 다. 실제: {}".format(result)
    )


# ===========================================================================
# F-5 (현행 FAIL) — momentum 은 desired 에 **가산**된다
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_5_momentum_adds_to_desired(caplog):
    """F-5: `scanner._last_scan_result`(모멘텀 스캔 결과)도 desired 성분이다.

    게이트는 breakout 만 보지만(§0②), desired **내용**에는 momentum 이 합쳐진다 —
    모멘텀 후보가 필터에 잘리면 그 전략의 tick 이 끊긴다.

    현행: 필터 자체가 없어 000300 도 재구독 → FAIL.
    """
    from src.engine import stale_manager

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    sched = _make_scheduler_with_high_tickers()
    _arm_breakout(sched, ["000100"])
    ticker_last_tick = {t: _STALE for t in ("000100", "000500", "000300")}
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", ["000500"]), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["000100", "000500"], (
        "desired = breakout ∪ momentum — 모멘텀 후보(000500)는 통과, 유령(000300)만 "
        f"탈락 의무. 실제: {result}"
    )
    assert "desired_low=2" in _info_lines(caplog)[0]


# ===========================================================================
# F-6 (현행 FAIL) — universe 축출 종목은 desired 에서 자동 이탈
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
@pytest.mark.parametrize("excluded, expect_included", [({"000700"}, False), (set(), True)])
async def test_f240_6_universe_excluded_drops_out_of_desired(excluded, expect_included):
    """F-6: **실제 `_collect_breakout_tickers` 본체를 경유**해야 한다.

    그 메서드는 `_universe_excluded_today` 를 이미 제거하므로(`scheduler.py:1743-1746`),
    축출 종목은 desired 에서 자동 이탈한다 = "universe 가드가 뺀 종목을 우선 재구독이
    되살리는" 2차 핑퐁도 함께 닫힌다.

    전략 `get_scanned_tickers()` 를 직접 합산해 `_universe_excluded_today` 를 우회하는
    구현(뮤테이션 m9)은 이 테스트가 잡는다.

    현행: 필터 부재 → 000700 재구독 → 첫 파라미터에서 FAIL.
    """
    from src.engine import stale_manager

    sched = _make_scheduler_with_high_tickers()

    strat = MagicMock()
    strat.config.enabled = True
    strat.get_scanned_tickers = MagicMock(return_value=["000100", "000700"])
    sched.registry = MagicMock(
        all=lambda: [],
        get=lambda sid: strat if sid == "bull_flag_breakout" else None,
    )
    sched._universe_excluded_today = set(excluded)

    ticker_last_tick = {"000100": _STALE, "000700": _STALE}
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert "000100" in result, f"정상 breakout 후보는 재구독. 실제: {result}"
    assert ("000700" in result) is expect_included, (
        "desired 는 `_collect_breakout_tickers()` (축출 제거 내장) 경유 의무. "
        f"excluded={excluded} → 000700 포함 기대={expect_included}. 실제: {result}"
    )


# ===========================================================================
# F-7 (HIGH, 현행 FAIL) — 순서 계약: 분리 → 필터 → throttle → cap
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_7_filter_precedes_throttle_and_cap():
    """F-7 (cycle216 T7 확장): cap 은 **필터·throttle 통과분** LOW 에만 적용된다.

    시나리오: HIGH 3 + LOW 12(000001~000012), throttle seed 000001~000004,
              desired = LOW 12 ∖ {000005, 000006}
      필터 → LOW 10 (000001-4, 000007-12)
      throttle → LOW 6 (000007~000012)
      cap=10, HIGH 3 → slots 7 → LOW 6 전부 → result 9

    필터를 throttle/cap **뒤**로 옮기면(뮤테이션 m4) cap 이 유령 000005/000006 을 먼저
    소비해 result 가 10 이 된다 — 유령이 cap 10 을 잡아먹는 것이 이 결함의 실비용이다.

    현행: 필터 부재 → LOW = 000005~000012 → cap 7 → 000005 포함, len 10 → FAIL.
    """
    from src.engine import stale_manager

    high = ["005001", "005002", "005003"]
    low = [f"{i:06d}" for i in range(1, 13)]
    sched = _make_scheduler_with_high_tickers(positions=high)
    _arm_breakout(sched, [t for t in low if t not in ("000005", "000006")])

    for t in ("000001", "000002", "000003", "000004"):
        sched._stale_last_resubscribe_at[t] = _BASE - timedelta(seconds=100)

    ticker_last_tick = {t: _STALE for t in (high + low)}
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert set(high) <= set(result), f"HIGH 3 절대 보장 (cap 위반 허용). 실제: {result}"
    for ghost in ("000005", "000006"):
        assert ghost not in result, (
            f"desired 밖 {ghost} 는 cap 조립 *전* 제거 의무 (필터 → throttle → cap). "
            f"실제: {result}"
        )
    low_in_result = [t for t in result if t in low]
    assert low_in_result == [f"{i:06d}" for i in range(7, 13)], (
        "필터(desired) → throttle(180s) → cap 순서 계약. 기대 LOW ['000007'..'000012'], "
        f"실제: {low_in_result}"
    )
    assert len(result) == 9, f"HIGH 3 + LOW 6 = 9. 실제 {len(result)}: {result}"


@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_7b_control_group_all_low_desired_matches_cycle216_t7():
    """F-7 대조군: desired 가 LOW 전량이면 cycle216 T7 과 **동일한 10건**이 나온다.

    필터가 desired 안 종목을 잘라내지 않음을 고정 (과잉 절삭 방지).
    """
    from src.engine import stale_manager

    high = ["005001", "005002", "005003"]
    low = [f"{i:06d}" for i in range(1, 13)]
    sched = _make_scheduler_with_high_tickers(positions=high)
    _arm_breakout(sched, low)

    for t in ("000001", "000002", "000003", "000004"):
        sched._stale_last_resubscribe_at[t] = _BASE - timedelta(seconds=100)

    ticker_last_tick = {t: _STALE for t in (high + low)}
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert len(result) == 10, f"cycle216 T7 동일 (cap=10). 실제 {len(result)}: {result}"
    assert [t for t in result if t in low] == [f"{i:06d}" for i in range(5, 12)]


# ===========================================================================
# F-8 (현행 FAIL) — 동시호가(cycle216 A) 병존
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_8_call_auction_warning_counts_filtered_survivors(caplog):
    """F-8: 동시호가 WARNING 의 `low=` 는 **필터 통과분** 수여야 한다.

    순서가 필터 → A 이므로 `[stale_skip_call_auction_priority] low=N` 의 N 은 유령을
    뺀 실제 후보 수 = 더 정확한 관측이다. HIGH 는 A 면제라 그대로 재구독된다.

    현행: 필터 부재 → low=3 + 신규 INFO 필드 부재 → FAIL.

    cycle240-R1: WARNING(`[stale_skip_call_auction_priority]`) 과 종료 INFO
    (`[stale_priority_resubscribe]`) 를 **같은 caplog(INFO 레벨) 캡처 하나**로
    함께 관측한다 — `_capture_scheduler_warnings()` 는 컨텍스트 동안
    `src.engine.scheduler` 로거 레벨을 WARNING 으로 올려 그 블록 안의 INFO 를
    방출 단계에서 흡수하므로(caplog 핸들러 도달 전 로거가 버림) 여기서 함께
    쓰면 안 된다(구현 결함이 아니라 픽스처 병용 결함).
    """
    from src.engine import stale_manager

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    sched = _make_scheduler_with_high_tickers(positions=["005930"])
    _arm_breakout(sched, ["000100"])
    ticker_last_tick = {
        t: _STALE for t in ("005930", "000100", "000300", "000400")
    }
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(True)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["005930"], (
        f"동시호가: HIGH 만 재구독 (cycle216 A 불변). 실제: {result}"
    )
    warns = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.WARNING
        and "[stale_skip_call_auction_priority]" in r.getMessage()
    ]
    assert len(warns) == 1, f"동시호가 WARNING 1행. 실제: {warns}"
    assert "low=1" in warns[0], (
        "필터 → 동시호가 순서라 `low=` 는 desired 통과분(1) 이어야 한다. "
        f"현행은 유령 포함 low=3 → FAIL. 실제: {warns[0]}"
    )
    msg = _info_lines(caplog)[0]
    assert "filtered_not_desired=2" in msg, (
        f"동시호가 경로에서도 필터 집계는 그대로 관측된다. 실제: {msg}"
    )


# ===========================================================================
# F-9 (현행 FAIL) — INFO 서식: prefix·첫 필드 보존 + 신규 3필드 + sample cap 10
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_9_info_format_active_and_inactive(caplog):
    """F-9: `[stale_priority_resubscribe] count=` 로 **시작**(byte 보존) + 3필드 추가.

    - `count=` 첫 필드 보존이 계약이다 —
      `test_scan_loop_stale_priority` 가 `"count=10" in log_text` 를 substring 단언한다.
    - `filtered_sample` 은 **≤10** (유령 15 주입) — 무제한이면 로그가 다시 오염된다.
    - 게이트 **비활성** 시 `desired_low=0 filtered_not_desired=0` (조사 신호).
    """
    from src.engine import stale_manager

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    ghosts = [f"0009{i:02d}" for i in range(15)]         # 유령 15

    # --- (1) 게이트 활성 ---------------------------------------------------
    sched = _make_scheduler_with_high_tickers()
    _arm_breakout(sched, ["000100"])
    ticker_last_tick = {t: _STALE for t in (["000100"] + ghosts)}
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        await stale_manager.resubscribe_stale_priority(sched, cap=10)

    active = _info_lines(caplog)[0]
    assert active.startswith("[stale_priority_resubscribe] count="), (
        f"prefix + 첫 필드 `count=` byte 보존 의무. 실제: {active}"
    )
    for field in ("desired_low=", "filtered_not_desired=", "filtered_sample="):
        assert field in active, f"신규 관측 필드 `{field}` 누락. 실제: {active}"
    assert "filtered_not_desired=15" in active
    sample_part = active.split("filtered_sample=", 1)[1]
    assert sample_part.count("'") // 2 <= 10, (
        f"`filtered_sample` 은 최대 10종목 (로그 오염 재발 차단). 실제: {sample_part}"
    )

    # --- (2) 게이트 비활성 -------------------------------------------------
    caplog.clear()
    sched2 = _make_scheduler_with_high_tickers()
    _arm_breakout(sched2, [])                            # breakout 공집합 → off
    tlt2 = {"000100": _STALE, "000300": _STALE}
    pool2, _log2 = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool2), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", ["000900"]), \
         patch("src.engine.scanner.ticker_last_tick", new=tlt2):
        await stale_manager.resubscribe_stale_priority(sched2, cap=10)

    inactive = _info_lines(caplog)[0]
    assert "desired_low=0" in inactive and "filtered_not_desired=0" in inactive, (
        "게이트 off 는 `desired_low=0 filtered_not_desired=0` 로 표기 — 장중에 이 값이 "
        f"지속되면 조사 신호다. 실제: {inactive}"
    )


# ===========================================================================
# F-10 (현행 FAIL) — 관측/헬퍼 실패는 행위를 바꾸지 않는다
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_10_helper_exception_is_isolated(monkeypatch, caplog):
    """F-10: `_collect_low_desired` 가 던져도 예외 전파 0 + 게이트 off 로 LOW 정상 재구독.

    관측기의 자기 실패가 재구독 루프를 끊으면 관측 시정이 아니라 **결함 주입**이다
    (cycle237 교훈). 호출부는 try 로 감싸고 `set(), set()` 폴백 = 게이트 off.
    """
    from src.engine import stale_manager, stale_watcher_core

    caplog.set_level(logging.INFO, logger="src.engine.scheduler")

    assert hasattr(stale_watcher_core, "_collect_low_desired"), (
        "시정 의무: 모듈 레벨 private 헬퍼 `_collect_low_desired(scheduler)` 신설 "
        "(스펙 §2.1). 현행 부재 → FAIL."
    )

    def _boom(_scheduler):
        raise RuntimeError("desired 수집 실패")

    monkeypatch.setattr(stale_watcher_core, "_collect_low_desired", _boom, raising=False)

    sched = _make_scheduler_with_high_tickers()
    _arm_breakout(sched, ["000100"])
    ticker_last_tick = {"000100": _STALE, "000300": _STALE}
    pool, _log = _make_spy_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["000100", "000300"], (
        f"헬퍼 예외 = 게이트 off (현행 행위 유지). 실제: {result}"
    )
    assert _info_lines(caplog)[0].startswith("[stale_priority_resubscribe] count=")


# ===========================================================================
# F-11 (현행 FAIL) — 걸러진 종목은 부수 상태를 오염시키지 않는다
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_11_filtered_ticker_leaves_no_side_effects():
    """F-11: 필터된 종목은 루프에 **진입하지 않으므로** 타임스탬프·seam 이 전부 무발화.

    `_stale_last_resubscribe_at` 오염이 이 결함의 조용한 2차 피해다 —
    cycle216 throttle 과 cycle29 force_retry 게이트가 그 값을 읽는다(cycle218 참조).
    `_stale_retry_count` 는 이 함수가 읽지도 쓰지도 않는다(G218-6 봉인) → `{}` 유지.
    """
    from src.engine import stale_manager

    sched = _make_scheduler_with_high_tickers()
    _arm_breakout(sched, ["000100"])
    ticker_last_tick = {"000100": _STALE, "000300": _STALE}
    pool, call_log, _state = _make_stateful_pool(
        subscribed={"000100", "000300"},
        ticker_to_session={"000100": "main", "000300": "main"},
    )

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["000100"]
    assert "000300" not in sched._stale_last_resubscribe_at, (
        "필터된 종목은 `_stale_last_resubscribe_at` 를 갱신하지 않는다 (throttle/"
        f"force_retry 타임스탬프 오염 소멸). 실제: {dict(sched._stale_last_resubscribe_at)}"
    )
    assert "000100" in sched._stale_last_resubscribe_at
    assert dict(sched._stale_retry_count) == {}, (
        "이 함수는 `_stale_retry_count` 무접촉 (cycle218 G218-6). "
        f"실제: {dict(sched._stale_retry_count)}"
    )
    assert not [e for e in call_log if e[2] == "000300"], (
        f"필터된 종목에 대한 어떤 seam 도 발화 금지. 실제: {call_log}"
    )


# ===========================================================================
# F-12 (현행 FAIL) — cycle215/217 split-brain 계약 불변 (desired ≠ subscribed)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_12_split_brain_desired_low_still_recovered():
    """F-12: desired 는 **구독 집합이 아니다**.

    미구독이지만 desired 인 LOW(split-brain)는 cycle217 계약대로
    `_ticker_to_session.pop` + 재SEND 로 복구되어야 하고, 미구독 유령은 어느 seam 도
    타면 안 된다.

    desired 소스를 `kis_ws_pool.get_subscribed_tickers()` 로 바꾸는 구현(뮤테이션 m5)은
    cycle215/217 시정을 통째로 무력화한다 — 이 테스트가 그 대체를 막는다.

    현행: 유령 000300 도 pop + 재SEND → FAIL.
    """
    from src.engine import stale_manager

    sched = _make_scheduler_with_high_tickers()
    _arm_breakout(sched, ["035420"])
    pool, call_log, _state = _make_stateful_pool(
        subscribed=set(),                                # 둘 다 미구독
        ticker_to_session={"035420": "main", "000300": "sub1"},
    )
    ticker_last_tick = {"035420": _STALE, "000300": _STALE}

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
         patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
         patch("src.engine.scanner._last_scan_result", []), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == ["035420"], (
        f"미구독 desired LOW 는 여전히 복구 대상 (cycle215/217 불변). 실제: {result}"
    )
    assert "035420" not in pool._ticker_to_session, (
        "cycle217: 미구독 종목은 `_ticker_to_session.pop` 로 dedup 해제 후 재SEND. "
        f"실제: {pool._ticker_to_session}"
    )
    assert pool._ticker_to_session.get("000300") == "sub1", (
        "유령은 pop 도 재SEND 도 하지 않는다 (루프 미진입). "
        f"실제: {pool._ticker_to_session}"
    )
    assert pool.unsubscribe_in_pool.await_count == 0, (
        "미구독 종목에 unsubscribe SEND 금지 (OPSP0003 회피, cycle217). "
        f"실제 호출: {pool.unsubscribe_in_pool.await_args_list}"
    )
    assert [e[2] for e in call_log if e[0] == "sub"] == ["035420"], (
        f"desired LOW 1건만 재SEND (유령은 SEND 0). 실제 call_log: {call_log}"
    )


# ===========================================================================
# F-13 (회귀 가드) — 레거시 픽스처 경로 차분 0
# ===========================================================================
@pytest.mark.asyncio
@freeze_time(_FROZEN, tz_offset=-9)
async def test_f240_13_legacy_fixture_path_unchanged():
    """F-13 (회귀 가드): 기존 23개 표적 파일의 픽스처는 전부 게이트 off 경로를 탄다.

    - `_EmptyRegistry`(`.get` 부재) → `_collect_breakout_tickers` AttributeError → off
    - `MagicMock` registry → `get_scanned_tickers()` 가 빈 iter → breakout `[]` → off

    두 경로 모두 **현행과 동일한 결과**여야 기존 회귀가 유지된다. `scanner._last_scan_result`
    잔여값이 게이트를 켜면 수집 순서에 따라 기존 테스트가 깨지므로, 여기서 momentum 을
    비어 있지 않게 주입해 **게이트 불참**을 고정한다.
    """
    from src.engine import stale_manager

    stale = ["200001", "200002", "200003"]

    for label, make in (
        ("empty_registry", "empty"),
        ("magicmock_registry", "magic"),
    ):
        sched = _make_scheduler_with_high_tickers()
        if make == "empty":
            class _EmptyRegistry:
                def all(self):
                    return []
            sched.registry = _EmptyRegistry()
        # magic: `_make_scheduler_with_high_tickers` 기본값이 이미 MagicMock registry

        ticker_last_tick = {t: _STALE for t in stale}
        pool, _log = _make_spy_pool()

        with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
             patch("src.realtime.websocket_pool.kis_ws_pool", pool), \
             patch("src.engine.session.session_tracker", _session_tracker_mock(False)), \
             patch("src.engine.scanner._last_scan_result", ["999999"]), \
             patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
            result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

        assert result == stale, (
            f"[{label}] 레거시 픽스처는 게이트 off → 전량 재구독 (차분 0). 실제: {result}"
        )
