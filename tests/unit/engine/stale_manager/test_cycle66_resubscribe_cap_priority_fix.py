"""사이클 66 Red — `_resubscribe_stale_priority` cap=10 결함 시정 회귀 가드 (11 케이스).

> **선행 명세**: `_workspace/red/cycle66_cap10_fix.md` (team-leader)
> **설계 카드 v2**: `_workspace/cycle66_cap10_fix_design_card.md`
> **자문 응답**: `_workspace/cycle66_cap10_fix_domain_response.md` (Q1~Q6-6 옵션 A 전부 채택)
> **위험 등급**: HIGH (KIS LMS/앱키 정지 chain 직접 영역 + 사이클 29 005935 사고 패턴)
> **시정 대상**: `src/engine/stale_manager.py::resubscribe_stale_priority` L1023-1034
>   현재: `targets = stale_tickers[:cap]` (priority 분리 *전* cap 적용 = 결함)
>   시정: `high_targets + low_targets[: max(0, cap - len(high_targets))]`

회귀 가드 매트릭스:
- CLAUDE.md 절대 규칙: WebSocket 시세 보유·익일청산 우선 보장 (`MAX_SUBSCRIPTIONS=41` + HIGH bypass_limit=True)
- 사이클 25-B HIGH/LOW 분리 정책 영속
- 사이클 29-R3 K stale watcher 우선순위 분리 일관 (본체 `_check_and_resubscribe_stale` 와 100% 정합)
- 사이클 29 005935 사고 패턴 (8분 영구 stale 잔류 + LMS chain) 차단
- 사이클 38 명문화 (매수 진입 전용 무관 — 본 시정은 시세 영역)

카테고리별 분포 (11 케이스):
- HIGH 4: K-2 (의미 전환), K-3 (HIGH > cap 경계), K-4 (HIGH+LOW 분리), K-8 (try/except 4중 가드)
- MEDIUM 2: K-10 (WARNING 로그 발화), AST (정적 가드)
- LOW 4: K-5 (HIGH 0 기존 동일), K-6 (HIGH 5+LOW 0), K-7 (stale 비어있음), K-9 (HIGH 0+LOW 0 edge)
- AST 1: priority 분리 *후* cap 적용 정적 검증

Red 시점 결과 (기대):
- K-2: PASS (결함 confirm 영속 — 사이클 63 의미 + 사이클 66 의미 전환 docstring 명시)
- K-3, K-4, K-8, K-10, AST: FAIL (시정 후 PASS 전환 의무)
- K-5, K-6, K-7, K-9: PASS (시정 무관 영속 행위)
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))


# ===========================================================================
# fixture helpers (사이클 63 K-2 답습)
# ===========================================================================
def _make_scheduler_with_high_tickers(positions: list[str] = None, ndc: set = None):
    """`TradingScheduler.__new__` + positions / _pending_next_day_clear 주입.

    사이클 63 K-2 답습 패턴 — registry mock + StaleTrackerState 주입.
    """
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    object.__setattr__(sched, "_pending_next_day_clear", ndc or set())

    strategy_state = MagicMock()
    strategy_state.positions = {t: MagicMock() for t in (positions or [])}
    strategy = MagicMock(state=strategy_state)
    sched.registry = MagicMock(all=lambda: [strategy] if positions else [])
    return sched


def _make_mock_pool() -> MagicMock:
    """KIS WebSocket 풀 mock — subscribe/unsubscribe_in_pool AsyncMock.

    사이클 215 — resubscribe_stale_priority 가 K watcher 패턴 (unsubscribe_in_pool
    선행)을 채택하며 unsubscribe_in_pool 도 AsyncMock 필요 (mock 적응).
    """
    mock_pool = MagicMock()
    mock_pool.subscribe = AsyncMock(return_value=None)
    mock_pool.unsubscribe_in_pool = AsyncMock(return_value=None)
    return mock_pool


# ===========================================================================
# K-2 (HIGH) — 사이클 63 결함 confirm → 사이클 66 시정 confirm 의미 전환
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-08 10:00:00", tz_offset=-9)
async def test_K2_high_at_last_with_low_overflow_high_preserved_after_fix():
    """K-2 (사이클 63 결함 confirm → 사이클 66 시정 confirm, Q6-4 자문 docstring 의무).

    사이클 63 의미 (이주 직후): HIGH 1 사전순 마지막 + LOW 12 + cap=10 →
                              `stale_tickers[:cap]` 적용 시 LOW 10 만 포함,
                              HIGH 1 (005935) cap 밖 잘림 = 결함 confirm PASS.
    사이클 66 의미 (시정 후): 동일 시나리오에서 priority 분리 *후* cap 적용 →
                            HIGH 1 (005935) 절대 보장 + LOW 9 = 시정 confirm PASS.

    동일 케이스가 사이클별로 의미가 *전환* — Green 단계 시정 후 assertion 갱신:
    - 사이클 63 K-2: `assert "005935" not in result` (결함 확인)
    - 사이클 66 K-2 (본 케이스): `assert "005935" in result` (시정 확인)

    사이클 29 (2026-05-21) 005935 사고 패턴 영구 차단:
    - 보유 005935 (삼성전자우) stale 13:21:41 마지막 시도 후 8분 영구 잔류
    - 시세 누락 → 손절 신호 평가 지연 → KIS LMS chain 위험
    - 사이클 66 시정 안 = HIGH 절대 보장으로 이 결함 완전 차단
    """
    from src.engine import stale_manager

    base = datetime(2026, 6, 8, 10, 0, 0, tzinfo=KST)
    # 005935 = positions 소속 → HIGH
    sched = _make_scheduler_with_high_tickers(positions=["005935"])

    # stale 13 종목: LOW 12 ("000020" ~ "000240" step 20) + HIGH 1 ("005935")
    # sorted 결과 → "005935" 는 사전순 마지막
    low_tickers = [f"{i:06d}" for i in range(20, 260, 20)]  # 12 LOW
    stale_all = low_tickers + ["005935"]  # 13 종목
    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {t: stale_dt for t in stale_all}

    mock_pool = _make_mock_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    # 시정 후 행위: HIGH "005935" 절대 보장
    assert "005935" in result, (
        "사이클 66 시정 confirm — HIGH 종목 005935 가 cap 밖으로 잘려선 안 됨. "
        "priority 분리 *후* cap 적용으로 HIGH 절대 보장. "
        "Red 단계: 결함 영속 시 FAIL (005935 cap 밖 잘림 = 사이클 63 결함 동일). "
        "Green 단계: PASS = 시정 confirm."
    )
    assert len(result) == 10, (
        f"cap=10 정확 적용 (HIGH 1 + LOW 9). 실제: {len(result)}"
    )
    # subscribe 호출 시 005935 는 HIGH priority + bypass_limit=True 의무
    high_calls = [
        c for c in mock_pool.subscribe.await_args_list
        if c.kwargs.get("priority") == "HIGH"
    ]
    assert any(c.args[1] == "005935" for c in high_calls), (
        "005935 는 HIGH priority + bypass_limit=True 로 호출되어야 함 (사이클 25-B 영속)"
    )


# ===========================================================================
# K-3 (HIGH) — HIGH > cap 경계: HIGH 12 + LOW 0 + cap=10 → HIGH 12 모두 통과
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-08 10:00:00", tz_offset=-9)
async def test_K3_high_12_low_0_cap_10_all_high_allowed():
    """K-3 (Q3 옵션 A 검증): HIGH > cap 경계 — HIGH 12 + LOW 0 + cap=10 → HIGH 12 모두 통과.

    자문 Q3 옵션 A: cap=10 은 부담 한도 권고이지 절대 한도 아님.
    HIGH 보유 종목 12 stale 시 cap=10 강제 = 2종목 시세 누락 = 사이클 29 사고 패턴 재현.
    HIGH 모두 보장 + cap 위반 허용.

    Red 단계: `stale_tickers[:cap]` 결함 코드 → HIGH 12 중 10 만 통과 = FAIL.
    Green 단계: priority 분리 *후* cap 적용 + HIGH > cap 모두 보장 → 12 PASS.
    """
    from src.engine import stale_manager

    base = datetime(2026, 6, 8, 10, 0, 0, tzinfo=KST)
    # 12 종목 모두 positions 소속 → HIGH
    high_tickers = [f"00{i:04d}" for i in range(1, 13)]  # 12 종목
    sched = _make_scheduler_with_high_tickers(positions=high_tickers)

    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {t: stale_dt for t in high_tickers}

    mock_pool = _make_mock_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert len(result) == 12, (
        f"HIGH 12 모두 cap 위반 허용 통과 의무 (Q3 옵션 A). 실제: {len(result)}"
    )
    assert mock_pool.subscribe.await_count == 12
    # 모든 호출이 HIGH + bypass_limit=True
    for call in mock_pool.subscribe.await_args_list:
        assert call.kwargs.get("priority") == "HIGH", (
            f"HIGH 종목 모두 priority='HIGH' 의무. 실제: {call.kwargs.get('priority')}"
        )
        assert call.kwargs.get("bypass_limit") is True, (
            f"HIGH 종목 모두 bypass_limit=True 의무. 실제: {call.kwargs.get('bypass_limit')}"
        )


# ===========================================================================
# K-4 (HIGH) — HIGH 5 + LOW 20 + cap=10 (HIGH 사전순 후반) → HIGH 5 + LOW 5
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-08 10:00:00", tz_offset=-9)
async def test_K4_high_5_low_20_cap_10_split_correctly():
    """K-4: HIGH 5 + LOW 20 + cap=10 (HIGH 사전순 후반) → HIGH 5 + LOW 5.

    시나리오: sorted 결과 LOW 20 ("000001"~"000020") + HIGH 5 ("050000"~"050004").
    결함 코드: stale_tickers[:10] = LOW 10 만 → HIGH 5 전부 누락.
    시정 코드: HIGH 5 절대 보장 + LOW 잔여 cap=5.

    Red 단계: FAIL (HIGH 5 모두 cap 밖 잘림).
    Green 단계: PASS (HIGH 5 + LOW 5 = 10).
    """
    from src.engine import stale_manager

    base = datetime(2026, 6, 8, 10, 0, 0, tzinfo=KST)
    low_tickers = [f"{i:06d}" for i in range(1, 21)]  # 000001~000020 (LOW)
    high_tickers = [f"{i:06d}" for i in range(50000, 50005)]  # 050000~050004 (HIGH 사전순 후반)
    sched = _make_scheduler_with_high_tickers(positions=high_tickers)

    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {t: stale_dt for t in (low_tickers + high_tickers)}

    mock_pool = _make_mock_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert len(result) == 10, f"cap=10 정확 적용. 실제: {len(result)}"
    high_in_result = [t for t in result if t in high_tickers]
    low_in_result = [t for t in result if t in low_tickers]
    assert len(high_in_result) == 5, (
        f"HIGH 5 모두 보장 의무 (사이클 25-B + 사이클 66 시정). "
        f"실제 HIGH: {len(high_in_result)} ({high_in_result})"
    )
    assert len(low_in_result) == 5, (
        f"LOW 잔여 cap=5 의무. 실제 LOW: {len(low_in_result)} ({low_in_result})"
    )


# ===========================================================================
# K-5 (LOW) — HIGH 0 + LOW 20 + cap=10 (기존 동일 행위 보존)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-08 10:00:00", tz_offset=-9)
async def test_K5_high_0_low_20_cap_10_existing_behavior_preserved():
    """K-5 (회귀 가드): HIGH 0 + LOW 20 + cap=10 → LOW[:10] 동일 행위 보존.

    HIGH 부재 시 기존 행위 (LOW 10건 sorted) 영속 의무.
    시정 후에도 high_targets=[] → low_targets[:10] = LOW 10건 (사전순 우선).

    Red 단계: PASS (기존 행위 = 결함 코드도 LOW 10 통과).
    Green 단계: PASS (회귀 가드 = 시정 코드도 LOW 10 통과).
    """
    from src.engine import stale_manager

    base = datetime(2026, 6, 8, 10, 0, 0, tzinfo=KST)
    low_tickers = [f"{i:06d}" for i in range(1, 21)]  # 000001~000020
    sched = _make_scheduler_with_high_tickers()  # HIGH 0

    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {t: stale_dt for t in low_tickers}

    mock_pool = _make_mock_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert len(result) == 10, f"cap=10 정확 적용. 실제: {len(result)}"
    # 모두 LOW priority
    for call in mock_pool.subscribe.await_args_list:
        assert call.kwargs.get("priority") == "LOW", (
            f"HIGH 부재 → 모두 LOW priority 의무. 실제: {call.kwargs.get('priority')}"
        )
        assert call.kwargs.get("bypass_limit") is False, (
            f"LOW → bypass_limit=False 의무. 실제: {call.kwargs.get('bypass_limit')}"
        )
    # sorted 결정성 → 사전순 우선 10건
    expected = [f"{i:06d}" for i in range(1, 11)]
    assert result == expected, f"sorted 결정성 보존. 기대: {expected}, 실제: {result}"


# ===========================================================================
# K-6 (LOW) — HIGH 5 + LOW 0 + cap=10 → targets = HIGH 5 만
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-08 10:00:00", tz_offset=-9)
async def test_K6_high_5_low_0_cap_10_high_only_no_padding():
    """K-6: HIGH 5 + LOW 0 + cap=10 → targets = HIGH 5 만 (LOW 0 padding 금지).

    `max(0, cap - len(high_targets))` = max(0, 10-5) = 5,
    `low_targets[:5]` = [] (LOW 부재) → targets = HIGH 5.

    Red 단계: PASS 또는 FAIL (구현 영향 — 결함 코드 stale_tickers[:cap] 도 5건 통과).
    Green 단계: PASS (HIGH 5 만 보장).
    """
    from src.engine import stale_manager

    base = datetime(2026, 6, 8, 10, 0, 0, tzinfo=KST)
    high_tickers = [f"00500{i}" for i in range(5)]  # 005000~005004
    sched = _make_scheduler_with_high_tickers(positions=high_tickers)

    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {t: stale_dt for t in high_tickers}

    mock_pool = _make_mock_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert len(result) == 5, f"HIGH 5 + LOW 0 = 5건. 실제: {len(result)}"
    assert set(result) == set(high_tickers)
    # 모두 HIGH priority
    for call in mock_pool.subscribe.await_args_list:
        assert call.kwargs.get("priority") == "HIGH"
        assert call.kwargs.get("bypass_limit") is True


# ===========================================================================
# K-7 (LOW) — stale_tickers 비어있음 → early return (시정 무관)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-08 10:00:00", tz_offset=-9)
async def test_K7_stale_tickers_empty_early_return():
    """K-7 (회귀 가드): stale_tickers 비어있음 → early return + subscribe 0회.

    `if not stale_tickers: return []` early return 영속 의무.
    시정 무관 — 결함 코드/시정 코드 모두 동일 행위.
    """
    from src.engine import stale_manager

    sched = _make_scheduler_with_high_tickers(positions=["005930"])
    ticker_last_tick = {}  # 모두 fresh (stale 없음)

    mock_pool = _make_mock_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == [], f"stale 비어있음 → 빈 리스트 반환 의무. 실제: {result}"
    assert mock_pool.subscribe.await_count == 0, (
        f"subscribe 0회 의무 (early return). 실제: {mock_pool.subscribe.await_count}"
    )


# ===========================================================================
# K-8 (HIGH) — `high_tickers` 구성 사이클 25-B 일관 (try/except 4중 가드 Q2)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-08 10:00:00", tz_offset=-9)
async def test_K8_high_tickers_composition_registry_exception_fallback():
    """K-8 (Q2 try/except 4중 가드 검증): registry.all() 예외 시 positions=set() 폴백.

    자문 Q2: 본체 `_check_and_resubscribe_stale` L820-833 try/except 4중 가드 답습.
    `scheduler.registry.all()` 예외 시 외부 try/except 가 흡수 → positions = set() 폴백.
    `_pending_next_day_clear` 만 high_tickers 구성 → 일부 종목 HIGH 보장 유지.

    Red 단계: 현 코드는 2중 가드 (`for s in scheduler.registry.all():` 의 outer 가드 없음)
              → registry.all() 예외 시 함수 전체 crash = FAIL.
    Green 단계: 외부 try/except 추가로 graceful 흡수 → "005935" HIGH 보장 PASS.
    """
    from src.engine import stale_manager
    from src.engine.scheduler import TradingScheduler
    from src.engine.stale_tracker import StaleTrackerState

    base = datetime(2026, 6, 8, 10, 0, 0, tzinfo=KST)
    sched = TradingScheduler.__new__(TradingScheduler)
    object.__setattr__(sched, "_stale_state", StaleTrackerState())
    # _pending_next_day_clear 에 005935 등록 → HIGH 보장 의무
    object.__setattr__(sched, "_pending_next_day_clear", {("005935", "VB")})
    # registry.all() 예외 발생 강제
    failing_registry = MagicMock()
    failing_registry.all.side_effect = RuntimeError("registry crash — try/except 4중 가드 검증")
    sched.registry = failing_registry

    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {"005935": stale_dt, "000010": stale_dt}

    mock_pool = _make_mock_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        # 결함 코드: outer try/except 부재 → RuntimeError propagate 가능 (FAIL)
        # 시정 코드: 외부 try/except 흡수 → graceful 통과 (PASS)
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    # 005935 는 _pending_next_day_clear 소속 → HIGH 보장 의무
    assert "005935" in result, (
        "Q2 try/except 4중 가드 시정: registry.all() 예외에도 _pending_next_day_clear "
        "기반 HIGH 005935 보장 의무"
    )
    # 005935 가 HIGH priority 로 호출되었는지 검증
    high_calls = [
        c for c in mock_pool.subscribe.await_args_list
        if c.kwargs.get("priority") == "HIGH"
    ]
    assert any(c.args[1] == "005935" for c in high_calls), (
        "005935 는 HIGH priority + bypass_limit=True 호출 의무 (사이클 25-B 영속)"
    )


# ===========================================================================
# K-9 (LOW) — HIGH 0 + LOW 0 edge (둘 다 비어있음)
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-08 10:00:00", tz_offset=-9)
async def test_K9_high_0_low_0_both_empty_edge_early_return():
    """K-9 (Q4 도메인 신규): HIGH 0 + LOW 0 (둘 다 비어있음) edge → early return.

    stale_tickers = [] (모두 fresh) + high_tickers = set() →
    `if not stale_tickers: return []` 진입 → 빈 리스트 반환.

    K-7 (stale_tickers 비어있음) 와 동일 동작 보장 (회귀 가드 중복 안전망).
    시정 무관 — 결함/시정 코드 모두 동일.
    """
    from src.engine import stale_manager

    sched = _make_scheduler_with_high_tickers()  # HIGH 0
    ticker_last_tick = {}  # LOW 0 (모두 fresh)

    mock_pool = _make_mock_pool()

    with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
         patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
         patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
        result = await stale_manager.resubscribe_stale_priority(sched, cap=10)

    assert result == [], f"HIGH 0 + LOW 0 → 빈 리스트 반환 의무. 실제: {result}"
    assert mock_pool.subscribe.await_count == 0


# ===========================================================================
# K-10 (MEDIUM) — Q3 옵션 A WARNING 로그 발화 검증
# ===========================================================================
@pytest.mark.asyncio
@freeze_time("2026-06-08 10:00:00", tz_offset=-9)
async def test_K10_high_exceeds_cap_emits_warning_log():
    """K-10 (Q4 자문 신규, Q3 의무): HIGH > cap 시 WARNING 로그 발화 검증.

    자문 Q3 옵션 A: HIGH > cap 모두 보장 + WARNING 로그 의무 (운영 가시화).
    예: HIGH 12 + cap=10 → HIGH 12 모두 보장 + `[stale_priority_resubscribe_cap_exceeded]`
                          WARNING 로그 1회 발화.

    Red 단계: 결함 코드는 WARNING 로그 자체가 없음 → FAIL.
    Green 단계: 시정 코드의 `logger.warning(...)` 발화 → PASS.

    검증 방법: caplog `set_level("WARNING", logger="src.engine.stale_manager")` 명시
              + `[stale_priority_resubscribe_cap_exceeded]` substring 확인.
    """
    import logging

    from src.engine import stale_manager

    base = datetime(2026, 6, 8, 10, 0, 0, tzinfo=KST)
    high_tickers = [f"00{i:04d}" for i in range(1, 13)]  # 12 HIGH
    sched = _make_scheduler_with_high_tickers(positions=high_tickers)

    stale_dt = base - timedelta(seconds=120)
    ticker_last_tick = {t: stale_dt for t in high_tickers}

    mock_pool = _make_mock_pool()

    # caplog 패턴 — pytest caplog fixture 대신 logger handler 직접 attach
    # stale_manager 의 logger 는 `src.engine.scheduler` binding (사이클 60 A1 명시 보존).
    # `src.engine.stale_manager` 로 attach 하면 WARNING 잡힘 0 — 올바른 이름 사용.
    records: list[logging.LogRecord] = []

    class _CapHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("src.engine.scheduler")
    handler = _CapHandler(level=logging.WARNING)
    logger.addHandler(handler)
    prev_level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        with patch("asyncio.sleep", new=AsyncMock(return_value=None)), \
             patch("src.realtime.websocket_pool.kis_ws_pool", mock_pool), \
             patch("src.engine.scanner.ticker_last_tick", new=ticker_last_tick):
            await stale_manager.resubscribe_stale_priority(sched, cap=10)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)

    # WARNING 로그 1회 발화 의무 (cap 초과 = HIGH 12 > cap 10)
    warning_records = [
        r for r in records
        if r.levelno == logging.WARNING
        and "[stale_priority_resubscribe_cap_exceeded]" in r.getMessage()
    ]
    assert len(warning_records) == 1, (
        f"Q3 옵션 A 의무: HIGH > cap 시 WARNING 로그 1회 발화. "
        f"실제 발화 수: {len(warning_records)}. 전체 records: {[r.getMessage() for r in records]}"
    )
    # 로그 메시지에 high_count + cap 노출 의무 (운영 가시화)
    msg = warning_records[0].getMessage()
    assert "12" in msg and "10" in msg, (
        f"WARNING 메시지에 high_count(12) + cap(10) 노출 의무. 실제: {msg}"
    )


# ===========================================================================
# AST (MEDIUM) — priority 분리 *후* cap 적용 정적 가드
# ===========================================================================
def test_AST_priority_split_before_cap_application_static_guard():
    """AST 정적 가드 — `resubscribe_stale_priority` priority 분리 *후* cap 적용 영구 의무.

    사이클 66 Q1 시정:
    - 결함: `targets = stale_tickers[:cap]` (priority 분리 *전* cap 적용)
    - 시정: `targets = high_targets + low_targets[: max(0, cap - len(high_targets))]`

    AST walk 로 함수 본체 source 내:
    1. 시정 패턴 (`low_targets[: max(0, cap - len(high_targets))]`) substring 존재 의무
    2. 결함 패턴 (`stale_tickers[:cap]`) substring 부재 의무 (결함 영속 차단)

    Red 단계: 시정 안 됨 → 결함 substring 잔존 → FAIL.
    Green 단계: 시정 안 적용 → 결함 substring 제거 + 시정 substring 존재 → PASS.

    사이클 67 보강: 분해 후 stale_watcher_core.py 가 진실의 원천 (fallback: stale_manager.py).
    G-17 (사이클 67 신규) 이 분해 후 위치 변경 대비 검증 담당 — 본 가드는 행위 보존 영속.
    """
    # 사이클 67 분해 후 stale_watcher_core.py 가 진실의 원천.
    # G-10/G-11/G-12/G-15 패턴 답습 — candidate_paths 으로 두 경로 모두 허용.
    engine_root = Path(__file__).parent.parent.parent.parent.parent / "src/engine"
    candidate_paths = [
        engine_root / "stale_watcher_core.py",
        engine_root / "stale_manager.py",
    ]
    source = None
    chosen_path = None
    for p in candidate_paths:
        if p.exists():
            source = p.read_text()
            chosen_path = p
            break

    assert source is not None, "stale_watcher_core.py / stale_manager.py 모두 미존재"

    tree = ast.parse(source)

    target_func = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "resubscribe_stale_priority":
            target_func = node
            break

    assert target_func is not None, (
        f"{chosen_path}: `resubscribe_stale_priority` async 함수 발견 의무 "
        "(사이클 63 Phase 2-A3 이주 + 사이클 67 분해 영속)"
    )

    func_source = ast.unparse(target_func)

    # 시정 안 substring 의무
    assert "low_targets[:max(0, cap - len(high_targets))]" in func_source or \
           "low_targets[: max(0, cap - len(high_targets))]" in func_source, (
        "사이클 66 시정 안 (`low_targets[: max(0, cap - len(high_targets))]`) 누락. "
        "priority 분리 *후* cap 적용 패턴 의무. 시정 함수 본체 (일부):\n" + func_source[:500]
    )

    # 결함 패턴 부재 의무 (결함 영속 차단)
    assert "stale_tickers[:cap]" not in func_source, (
        "사이클 63 K-2 결함 (`stale_tickers[:cap]` priority 분리 *전* cap 적용) 영속. "
        "사이클 66 시정 = 결함 substring 완전 제거 의무"
    )

    # HIGH/LOW 분리 substring 의무 (사이클 25-B + 사이클 29-R3 본체 패턴 일관)
    assert "high_targets" in func_source and "low_targets" in func_source, (
        "priority 분리 변수 (`high_targets` / `low_targets`) 누락 = 사이클 25-B 패턴 위반"
    )
