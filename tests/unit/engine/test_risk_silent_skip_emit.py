"""사이클 31 (R6, 2026-05-21) — `risk.py:152` 사전 가드 침묵 가시화.

배경 (2026-05-21 09:13 VB 미매수 사고):
- `src/engine/risk.py:152-153` 사전 가드 `current_price > state.total_investment` skip 이
  침묵 동작 → 사용자가 대시보드 "돌파" 보고 매수 안 되는 이유를 코드 추적 + DB 분석 +
  Explore 에이전트 2개 병렬 호출까지 거쳐야 디버깅 가능했던 곤란의 근본 원인.
- VB 비중 0.3 → 0.5 상향 후에도 순자산 1.17M 기준 VB total = 543K.
  삼성전기(1.18M) / 현대모비스(0.62M) / SK하이닉스(1.83M) 등 여전히 사전 가드 영향권
  → 본 결함은 운영 중 매일 발생 가능성 높음.

본 사이클 (31, R6) 변경:
- 사전 가드 skip 직전 `[risk_silent_skip] ticker={t} strategy={sid} reason=price_gt_total_investment
  price={p} total={tot}` INFO 1행 emit
- **1회/종목/일/전략 emit cap** — `(ticker, strategy_id)` 페어 기준 하루 1회만
- 매 틱 emit 폭주 차단 (1초 내 수 백 틱 가능)
- `_reset_daily_state()` 시 emit set 동행 clear

신규 필드:
- `RiskManager._risk_silent_skip_logged_today: set[tuple[str, str]]` (인스턴스)

사양 (S1~S6):
- S-1: 같은 (ticker, strategy) 일일 1회만 emit (cap)
- S-2: 같은 ticker 다른 strategy 는 각각 emit (페어 단위)
- S-3: emit 후 같은 사이클 재호출 시 silent skip 보존 (성능 가드)
- S-4: `_reset_daily_state` 후 재 emit 가능
- S-5: INFO 로그 포맷 검증 (`[risk_silent_skip]` prefix + ticker/strategy/reason/price/total)
- S-6: skip 동작 자체는 보존 (성능 가드 — check_buy_signal 호출 0건)
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — 시나리오 setup
# ---------------------------------------------------------------------------
def _make_risk_manager_and_strategy(
    monkeypatch,
    *,
    strategy_id: str = "volatility_breakout",
    total_investment: int = 543_000,
    ticker_blocked: bool = False,
):
    """`RiskManager` + 단일 전략 더블 생성.

    가드 통과 조건만 충족 + `total_investment < current_price` 분기 도달.
    """
    from src.engine.risk import RiskManager

    # 전략 더블
    state = MagicMock()
    state.positions = {}
    state.pending_buys = set()
    state.sold_today = set()
    state.has_position = MagicMock(return_value=False)
    state.is_buy_blocked = MagicMock(return_value=False)
    state.is_low_funds_blocked = MagicMock(return_value=False)
    state.buy_disabled = False
    state.total_investment = total_investment
    state.signal_count_today = 0
    state.buy_signals = set()

    strategy = MagicMock()
    strategy.strategy_id = strategy_id
    strategy.state = state
    strategy.is_daily_loss_exceeded = MagicMock(return_value=False)
    strategy.check_buy_signal = MagicMock()
    strategy.check_exit_signal = MagicMock()

    # registry 더블 — enabled() 가 strategy 1개 반환
    registry = MagicMock()
    registry.enabled = MagicMock(return_value=[strategy])
    registry.is_ticker_blocked_for_buy = MagicMock(return_value=ticker_blocked)

    # OrderEngine 더블 — _selling set + execute_buy mock
    order_engine = MagicMock()
    order_engine._selling = set()
    order_engine.execute_buy = AsyncMock()

    rm = RiskManager(registry, order_engine)

    # session_tracker 가드 우회: is_tradable=True 강제
    from src.engine import session as session_mod
    monkeypatch.setattr(
        session_mod.session_tracker, "is_tradable",
        lambda sid, params=None: True, raising=False,
    )

    # buy_block 가드 우회: get_buy_block_state OFF + blocked=False
    from src.engine import market_regime as mr_mod
    fake_regime = MagicMock()
    fake_state = MagicMock()
    fake_state.mode = "OFF"
    fake_state.blocked = False
    fake_state.reasons = []
    fake_state.soft_multiplier = 1.0
    fake_regime.get_buy_block_state = AsyncMock(return_value=fake_state)
    monkeypatch.setattr(mr_mod, "get_current_regime", lambda: fake_regime)

    # scanner ticker_prev_close mock — prdy_ctrt 계산용
    from src.engine import scanner as scanner_mod
    monkeypatch.setattr(scanner_mod, "ticker_prev_close", {}, raising=False)
    monkeypatch.setattr(scanner_mod, "ticker_prices", {}, raising=False)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {}, raising=False)

    return rm, strategy


# ===========================================================================
# S-1: 같은 (ticker, strategy) 일일 1회만 emit (cap)
# ===========================================================================
@pytest.mark.asyncio
async def test_emit_once_per_ticker_strategy_pair_per_day(monkeypatch, caplog):
    """삼성전기(009150) 가격 1.18M > VB total 543K — 첫 호출 INFO emit, 재호출 silent."""
    import logging
    rm, strategy = _make_risk_manager_and_strategy(monkeypatch)

    caplog.set_level(logging.INFO, logger="src.engine.risk")

    # 1회 — emit
    await rm.on_tick("009150", current_price=1_186_000, open_price=1_186_000, change_rate=0.0)

    emit_lines = [r for r in caplog.records if "[risk_silent_skip]" in r.message]
    assert len(emit_lines) == 1, (
        f"첫 호출 INFO emit 누락. records={[r.message for r in caplog.records]}"
    )

    # 2회 — silent (cap)
    caplog.clear()
    await rm.on_tick("009150", current_price=1_186_000, open_price=1_186_000, change_rate=0.0)
    emit_lines_2 = [r for r in caplog.records if "[risk_silent_skip]" in r.message]
    assert len(emit_lines_2) == 0, (
        f"같은 (ticker, strategy) 재호출 시 silent 보존. records={[r.message for r in caplog.records]}"
    )


# ===========================================================================
# S-2: 같은 ticker 다른 strategy 는 각각 emit
# ===========================================================================
@pytest.mark.asyncio
async def test_emit_per_strategy_for_same_ticker(monkeypatch, caplog):
    """같은 ticker(009150) 가 VB + LTV 둘 다 가드에 걸리면 각각 1회 emit."""
    import logging
    from src.engine.risk import RiskManager

    # 두 전략 (VB, LTV) 동시 등록
    def _make_strat(sid, total):
        state = MagicMock()
        state.positions = {}
        state.pending_buys = set()
        state.sold_today = set()
        state.has_position = MagicMock(return_value=False)
        state.is_buy_blocked = MagicMock(return_value=False)
        state.is_low_funds_blocked = MagicMock(return_value=False)
        state.buy_disabled = False
        state.total_investment = total
        state.signal_count_today = 0
        state.buy_signals = set()
        strat = MagicMock()
        strat.strategy_id = sid
        strat.state = state
        strat.is_daily_loss_exceeded = MagicMock(return_value=False)
        strat.check_buy_signal = MagicMock()
        strat.check_exit_signal = MagicMock()
        return strat

    vb = _make_strat("volatility_breakout", 543_000)
    ltv = _make_strat("long_tail_volatility", 350_000)

    registry = MagicMock()
    registry.enabled = MagicMock(return_value=[vb, ltv])
    registry.is_ticker_blocked_for_buy = MagicMock(return_value=False)

    order_engine = MagicMock()
    order_engine._selling = set()
    order_engine.execute_buy = AsyncMock()

    rm = RiskManager(registry, order_engine)

    # 가드 우회 — 헬퍼와 동일
    from src.engine import session as session_mod
    monkeypatch.setattr(
        session_mod.session_tracker, "is_tradable",
        lambda sid, params=None: True, raising=False,
    )
    from src.engine import market_regime as mr_mod
    fake_regime = MagicMock()
    fake_state = MagicMock()
    fake_state.mode = "OFF"
    fake_state.blocked = False
    fake_state.reasons = []
    fake_state.soft_multiplier = 1.0
    fake_regime.get_buy_block_state = AsyncMock(return_value=fake_state)
    monkeypatch.setattr(mr_mod, "get_current_regime", lambda: fake_regime)
    from src.engine import scanner as scanner_mod
    monkeypatch.setattr(scanner_mod, "ticker_prev_close", {}, raising=False)
    monkeypatch.setattr(scanner_mod, "ticker_prices", {}, raising=False)
    monkeypatch.setattr(scanner_mod, "ticker_last_tick", {}, raising=False)

    caplog.set_level(logging.INFO, logger="src.engine.risk")

    await rm.on_tick("009150", current_price=1_186_000, open_price=1_186_000, change_rate=0.0)

    emit_lines = [r.message for r in caplog.records if "[risk_silent_skip]" in r.message]
    assert len(emit_lines) == 2, (
        f"같은 ticker 다른 strategy 각각 emit. 실제={len(emit_lines)}. records={emit_lines}"
    )
    # strategy 명시 검증
    assert any("volatility_breakout" in line for line in emit_lines)
    assert any("long_tail_volatility" in line for line in emit_lines)


# ===========================================================================
# S-3: emit 후 같은 사이클 재호출 시 silent skip 보존 + check_buy_signal 호출 0건
# ===========================================================================
@pytest.mark.asyncio
async def test_skip_behavior_preserved_no_check_buy_signal_call(monkeypatch):
    """가드 skip 동작 자체 보존 — `check_buy_signal` 호출 0건 (성능 가드)."""
    rm, strategy = _make_risk_manager_and_strategy(monkeypatch)

    # 100회 호출
    for _ in range(100):
        await rm.on_tick("009150", current_price=1_186_000, open_price=1_186_000, change_rate=0.0)

    # check_buy_signal 한 번도 호출 안 됨 (사전 가드 skip 동작 보존)
    strategy.check_buy_signal.assert_not_called()


# ===========================================================================
# S-4: `_reset_daily_state` 후 재 emit 가능 (정산 후 익일 첫 호출)
# ===========================================================================
@pytest.mark.asyncio
async def test_emit_re_enabled_after_daily_reset(monkeypatch, caplog):
    """`_risk_silent_skip_logged_today` 가 scheduler `_reset_daily_state` 와 동행 clear."""
    import logging
    rm, strategy = _make_risk_manager_and_strategy(monkeypatch)

    caplog.set_level(logging.INFO, logger="src.engine.risk")

    # 1회 emit
    await rm.on_tick("009150", current_price=1_186_000, open_price=1_186_000, change_rate=0.0)
    assert len([r for r in caplog.records if "[risk_silent_skip]" in r.message]) == 1

    # 매뉴얼 clear (scheduler._reset_daily_state 가 호출하는 동작 시뮬레이션)
    rm._risk_silent_skip_logged_today.clear()
    caplog.clear()

    # 익일 동일 호출 — 재 emit
    await rm.on_tick("009150", current_price=1_186_000, open_price=1_186_000, change_rate=0.0)
    re_emit_lines = [r for r in caplog.records if "[risk_silent_skip]" in r.message]
    assert len(re_emit_lines) == 1, (
        f"_reset_daily_state 후 재 emit 가능. 실제={len(re_emit_lines)}건"
    )


# ===========================================================================
# S-5: INFO 로그 포맷 검증
# ===========================================================================
@pytest.mark.asyncio
async def test_log_format_includes_all_required_fields(monkeypatch, caplog):
    """`[risk_silent_skip] ticker={t} strategy={sid} reason=... price=... total=...` 포맷."""
    import logging
    rm, _ = _make_risk_manager_and_strategy(
        monkeypatch, strategy_id="volatility_breakout", total_investment=543_000
    )

    caplog.set_level(logging.INFO, logger="src.engine.risk")

    await rm.on_tick("009150", current_price=1_186_000, open_price=1_186_000, change_rate=0.0)

    emit_lines = [r.message for r in caplog.records if "[risk_silent_skip]" in r.message]
    assert len(emit_lines) == 1
    line = emit_lines[0]
    # 필수 필드 검증
    assert "[risk_silent_skip]" in line
    assert "ticker=009150" in line
    assert "strategy=volatility_breakout" in line
    assert "reason=price_gt_total_investment" in line
    assert "price=1186000" in line
    assert "total=543000" in line


# ===========================================================================
# S-6: 가드 통과 시 emit 안 함 (정상 매수 흐름)
# ===========================================================================
@pytest.mark.asyncio
async def test_no_emit_when_total_investment_sufficient(monkeypatch, caplog):
    """`total_investment >= current_price` 면 가드 skip 발화 안 함 → emit 0건."""
    import logging
    rm, _ = _make_risk_manager_and_strategy(
        monkeypatch, total_investment=2_000_000  # > 1.18M
    )

    caplog.set_level(logging.INFO, logger="src.engine.risk")

    await rm.on_tick("009150", current_price=1_186_000, open_price=1_186_000, change_rate=0.0)

    emit_lines = [r for r in caplog.records if "[risk_silent_skip]" in r.message]
    assert len(emit_lines) == 0


# ===========================================================================
# S-7: scheduler `_reset_daily_state` 가 `risk_manager.reset_daily_state()` 위임
# 사이클 56-D: 외부 직접 clear → 캡슐화 위임 (사이클 52 OrderEngine 패턴 답습)
# ===========================================================================
def test_scheduler_reset_daily_state_clears_silent_skip_log():
    """scheduler `_reset_daily_state` 가 `risk_manager.reset_daily_state()` 를 위임 호출.

    사이클 56-D 마이그레이션: scheduler 외부 직접 clear →
    RiskManager.reset_daily_state() 캡슐화 위임. scheduler 소스에서 위임 호출 확인.
    RiskManager.reset_daily_state 소스에서 _risk_silent_skip_logged_today.clear() 확인.
    """
    import inspect
    from src.engine.risk import RiskManager
    from src.engine.scheduler import TradingScheduler

    sched_src = inspect.getsource(TradingScheduler._reset_daily_state)
    assert "risk_manager.reset_daily_state()" in sched_src, (
        f"`_reset_daily_state` 가 risk_manager.reset_daily_state() 미 위임. "
        f"코드: {sched_src[:500]}"
    )
    risk_src = inspect.getsource(RiskManager.reset_daily_state)
    assert "_risk_silent_skip_logged_today" in risk_src and ".clear()" in risk_src, (
        f"RiskManager.reset_daily_state 가 _risk_silent_skip_logged_today 미 clear. "
        f"코드: {risk_src}"
    )


# ===========================================================================
# S-8: RiskManager __init__ 가 `_risk_silent_skip_logged_today` 초기화
# ===========================================================================
def test_risk_manager_init_creates_silent_skip_log_set():
    """`RiskManager.__init__` 가 `_risk_silent_skip_logged_today: set` 필드 생성."""
    import inspect
    from src.engine.risk import RiskManager

    src = inspect.getsource(RiskManager.__init__)
    assert "_risk_silent_skip_logged_today" in src, (
        f"RiskManager.__init__ 에 _risk_silent_skip_logged_today 누락"
    )


# ===========================================================================
# G-4 (사이클 56-D): DailyEmitCap[tuple] 마이그레이션 회귀 가드
# ===========================================================================

def test_risk_silent_skip_logged_today_is_daily_emit_cap_instance(monkeypatch):
    """사이클 56-D 마이그레이션 회귀 가드 — DailyEmitCap[tuple] 인스턴스 + tuple key 호환."""
    from src.engine.daily_emit_cap import DailyEmitCap
    from src.engine.risk import RiskManager
    from unittest.mock import MagicMock

    registry = MagicMock()
    registry.enabled = MagicMock(return_value=[])
    order_engine = MagicMock()
    order_engine._selling = set()

    risk = RiskManager(registry, order_engine)

    # DailyEmitCap 인스턴스 검증
    assert isinstance(risk._risk_silent_skip_logged_today, DailyEmitCap), (
        f"_risk_silent_skip_logged_today 가 DailyEmitCap 인스턴스 아님: "
        f"{type(risk._risk_silent_skip_logged_today)}"
    )

    # tuple key — __contains__ / add / clear 호환 검증
    key = ("064400", "momentum")
    risk._risk_silent_skip_logged_today.add(key)
    assert key in risk._risk_silent_skip_logged_today, "add 후 __contains__ 실패"

    risk._risk_silent_skip_logged_today.clear()
    assert key not in risk._risk_silent_skip_logged_today, "clear 후 __contains__ 실패"


def test_risk_manager_reset_daily_state_caps(monkeypatch):
    """사이클 56-D reset 캡슐화 회귀 가드 — reset_daily_state() 호출 시 emit cap clear."""
    from src.engine.risk import RiskManager
    from unittest.mock import MagicMock

    registry = MagicMock()
    registry.enabled = MagicMock(return_value=[])
    order_engine = MagicMock()
    order_engine._selling = set()

    risk = RiskManager(registry, order_engine)

    # emit cap 에 항목 등록
    risk._risk_silent_skip_logged_today.add(("064400", "momentum"))
    risk._risk_silent_skip_logged_today.add(("005930", "volatility_breakout"))
    assert len(risk._risk_silent_skip_logged_today) == 2

    # reset_daily_state() 호출 후 모두 clear 확인
    risk.reset_daily_state()
    assert len(risk._risk_silent_skip_logged_today) == 0, (
        "reset_daily_state() 후 _risk_silent_skip_logged_today 가 비어있지 않음"
    )
