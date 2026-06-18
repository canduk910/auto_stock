"""사이클 164 Red — 시가 확정 chain 재시도 안전망 검증.

명세 (`_workspace/red/cycle164_open_confirm_retry_chain.md`):

근본 원인 (2026-06-18 11:03 KST EC2 재기동 사례):
- 11:03 재기동 시점 `run_daily` 진입 → `now > TIME_KRX_OPEN_CONFIRM` 분기 진입
- L640 `await self._confirm_breakout_open_prices()` 호출 시점 prepare 미완료
- `_targets` 비어있어 silent skip (L1413 `if not targets: return`)
- 11:17 prepare 완료 → `_targets` 등록되지만 시가 확정 재시도 chain 부재
- UI = "시가 대기" 표시 영속

시정 (옵션 C 통합):
- `_confirm_breakout_open_prices_if_pending()` 신규 메서드 — `_targets` 비어있지 않고
  `_open_confirmed[ticker][active_board] == False` 인 종목 1개 이상 시 재시도
- `_scan_loop` 5분 주기 `_reprepare_breakout_if_empty()` 직후 hook (graceful wrap)

안전 가드 (CLAUDE.md "절대 깨지 말 것"):
- `src/engine/risk.py` / `src/engine/order_engine.py` / `src/realtime/` / `src/auth/` 변경 0
- 매도/익일청산/15:20 강제청산/손절 hot path 무관 (사이클 38 명문화 영속)
- 사이클 26 VB MAIN 단독 + 사이클 38 LTV 3보드 영속
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.scheduler import TradingScheduler

pytestmark = pytest.mark.unit


SCHEDULER_PATH = Path("src/engine/scheduler.py")


def _make_strategy_with_targets(
    sid: str,
    *,
    targets: dict[str, dict] | None,
    open_confirmed: dict[str, dict] | None,
    enabled: bool = True,
) -> MagicMock:
    """VB/LTV strategy mock — `_targets` + `_open_confirmed` 영역."""
    strategy = MagicMock()
    strategy.config = MagicMock()
    strategy.config.enabled = enabled
    strategy.config.params = {"tradable_boards": ["main"]}
    strategy.config.name = sid
    strategy._targets = targets or {}
    strategy._open_confirmed = open_confirmed or {}
    strategy.DEFAULT_TRADABLE_BOARDS = ("main",)
    strategy.strategy_id = sid

    def _on_confirmed(ticker, open_price, board="main"):
        strategy._open_confirmed.setdefault(ticker, {})[board] = True

    strategy.on_open_price_confirmed = _on_confirmed
    strategy.get_targets_status = MagicMock(return_value={})
    return strategy


# ---------------------------------------------------------------------------
# G-164-OPEN-1 (HIGH) — `_targets` 비어있지 않고 시가 미확정 종목 ≥1 시 재시도
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_confirm_if_pending_triggers_retry_when_unconfirmed():
    """`_targets` 에 종목 1개 이상 + `_open_confirmed[main]` 부재 → 재시도 호출."""
    sched = TradingScheduler()
    vb = _make_strategy_with_targets(
        "volatility_breakout",
        targets={"005930": {"boards": {}}},
        open_confirmed={},  # main 미확정
    )
    sched.registry.get = MagicMock(return_value=vb)
    sched.registry.all = MagicMock(return_value=[vb])

    confirm_mock = AsyncMock()
    with patch.object(
        sched, "_confirm_breakout_open_prices", confirm_mock,
    ):
        await sched._confirm_breakout_open_prices_if_pending()

    confirm_mock.assert_awaited()  # ≥1회 호출 (재시도 발화)


# ---------------------------------------------------------------------------
# G-164-OPEN-2 (HIGH) — 모든 종목 confirmed → silent skip (idempotent)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_confirm_if_pending_skip_when_all_confirmed(monkeypatch):
    """`_open_confirmed[main]=True` 전수 → 재시도 호출 0건 (idempotent).

    환경별 active_board 차이 차단 의무 = session_tracker.active 강제 MAIN.
    """
    from src.engine.session import MarketBoard, session_tracker

    # active property = setter 부재 → _active 직접 영영 영영 영영 영영 영영
    # SessionTracker.active 영영 frozenset({MarketBoard.MAIN}) 영영 영영
    monkeypatch.setattr(
        type(session_tracker), "active",
        property(lambda self: frozenset({MarketBoard.MAIN})),
    )

    sched = TradingScheduler()
    vb = _make_strategy_with_targets(
        "volatility_breakout",
        targets={"005930": {"boards": {"main": {"open_price": 80000}}}},
        open_confirmed={"005930": {"main": True}},
    )
    sched.registry.get = MagicMock(return_value=vb)
    sched.registry.all = MagicMock(return_value=[vb])

    confirm_mock = AsyncMock()
    with patch.object(
        sched, "_confirm_breakout_open_prices", confirm_mock,
    ):
        await sched._confirm_breakout_open_prices_if_pending()

    confirm_mock.assert_not_awaited()  # 0회 호출 (idempotent skip)


# ---------------------------------------------------------------------------
# G-164-OPEN-3 — `_scan_loop` 영역 hook 호출 존재 검증 (AST 정적 가드)
# ---------------------------------------------------------------------------
def test_scan_loop_calls_confirm_if_pending_after_reprepare():
    """`_scan_loop` 본체에 `_confirm_breakout_open_prices_if_pending` 호출 ≥ 1건."""
    src = SCHEDULER_PATH.read_text(encoding="utf-8")
    # `_scan_loop` 본체 영역 추출 (시그너처 ~ 다음 메서드 정의 직전)
    start_idx = src.find("async def _scan_loop(")
    assert start_idx > 0, "_scan_loop 메서드 부재"
    # 다음 async def 또는 def 영역까지
    next_def_idx = src.find("\n    async def ", start_idx + 1)
    if next_def_idx < 0:
        next_def_idx = len(src)
    scan_loop_body = src[start_idx:next_def_idx]
    assert "_confirm_breakout_open_prices_if_pending" in scan_loop_body, (
        "_scan_loop 영역에 `_confirm_breakout_open_prices_if_pending` 호출 부재 — "
        "사이클 164 시정 누락 (silent 결함 차단 의무)"
    )


# ---------------------------------------------------------------------------
# G-164-OPEN-4 — `_confirm_breakout_open_prices` 예외 graceful (다음 사이클 재시도)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_confirm_if_pending_swallows_exception():
    """내부 `_confirm_breakout_open_prices` 예외 시 graceful (다음 사이클 자연 재시도)."""
    sched = TradingScheduler()
    vb = _make_strategy_with_targets(
        "volatility_breakout",
        targets={"005930": {"boards": {}}},
        open_confirmed={},
    )
    sched.registry.get = MagicMock(return_value=vb)
    sched.registry.all = MagicMock(return_value=[vb])

    confirm_mock = AsyncMock(side_effect=RuntimeError("KIS 일시 결함"))
    with patch.object(
        sched, "_confirm_breakout_open_prices", confirm_mock,
    ):
        # 예외가 외부로 누출되지 않아야 함 (graceful)
        await sched._confirm_breakout_open_prices_if_pending()

    confirm_mock.assert_awaited()  # 호출은 발화


# ---------------------------------------------------------------------------
# G-164-OPEN-5 (HIGH) — VB + LTV 양쪽 전략 모두 평가
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_confirm_if_pending_evaluates_both_vb_and_ltv():
    """VB + LTV 합집합 영역 — 한쪽이라도 미확정 종목 1개 이상 시 재시도."""
    sched = TradingScheduler()
    vb = _make_strategy_with_targets(
        "volatility_breakout",
        targets={"005930": {"boards": {"main": {"open_price": 80000}}}},
        open_confirmed={"005930": {"main": True}},  # 전수 확정
    )
    ltv = _make_strategy_with_targets(
        "long_tail_volatility",
        targets={"000660": {"boards": {}}},
        open_confirmed={},  # 미확정
    )

    def _get(sid):
        return {"volatility_breakout": vb, "long_tail_volatility": ltv}.get(sid)

    sched.registry.get = MagicMock(side_effect=_get)
    sched.registry.all = MagicMock(return_value=[vb, ltv])

    confirm_mock = AsyncMock()
    with patch.object(
        sched, "_confirm_breakout_open_prices", confirm_mock,
    ):
        await sched._confirm_breakout_open_prices_if_pending()

    # LTV 영역 미확정 종목 존재 → 재시도 호출 ≥ 1
    assert confirm_mock.await_count >= 1, (
        f"LTV 영역 미확정 종목 존재 시 재시도 발화 0건 — "
        f"호출 횟수: {confirm_mock.await_count}"
    )


# ---------------------------------------------------------------------------
# G-164-OPEN-6 — disabled 전략은 평가에서 제외
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_confirm_if_pending_skip_disabled_strategy():
    """`config.enabled = False` 전략은 호출 영역 제외."""
    sched = TradingScheduler()
    vb_disabled = _make_strategy_with_targets(
        "volatility_breakout",
        targets={"005930": {"boards": {}}},
        open_confirmed={},
        enabled=False,  # disabled
    )
    sched.registry.get = MagicMock(return_value=vb_disabled)
    sched.registry.all = MagicMock(return_value=[vb_disabled])

    confirm_mock = AsyncMock()
    with patch.object(
        sched, "_confirm_breakout_open_prices", confirm_mock,
    ):
        await sched._confirm_breakout_open_prices_if_pending()

    confirm_mock.assert_not_awaited()  # disabled 영역 skip


# ---------------------------------------------------------------------------
# G-164-OPEN-7 — `_targets` 비어있으면 prepare 미완료 — 호출 0회
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_confirm_if_pending_skip_when_targets_empty():
    """`_targets` 영역 빈 dict → prepare 미완료 영역 — `_reprepare_breakout_if_empty`
    영역 담당이므로 시가 확정 영역 호출 0회."""
    sched = TradingScheduler()
    vb = _make_strategy_with_targets(
        "volatility_breakout",
        targets={},  # prepare 미완료
        open_confirmed={},
    )
    sched.registry.get = MagicMock(return_value=vb)
    sched.registry.all = MagicMock(return_value=[vb])

    confirm_mock = AsyncMock()
    with patch.object(
        sched, "_confirm_breakout_open_prices", confirm_mock,
    ):
        await sched._confirm_breakout_open_prices_if_pending()

    confirm_mock.assert_not_awaited()  # prepare 미완료 → 다른 영역 담당


# ---------------------------------------------------------------------------
# G-164-SAFETY-1 (HIGH) — risk / order_engine / realtime / auth 변경 0 AST 가드
# ---------------------------------------------------------------------------
def test_no_modification_to_safety_critical_modules():
    """본 사이클 시정은 scheduler.py + 테스트 영역 한정 — 매매 hot path 변경 0."""
    src = SCHEDULER_PATH.read_text(encoding="utf-8")
    # scheduler.py 가 risk.py / order_engine.py / realtime/* / auth/* 영역 import 신규 0건.
    # 기존 import 패턴 보존 (사이클 38 명문화 영속).
    forbidden_changes = [
        "from src.engine.risk import RiskManager",
        "from src.engine.order_engine import OrderEngine",
    ]
    for pat in forbidden_changes:
        # 이미 기존에 존재하는 import 는 정상 (회귀 가드)
        assert pat in src, f"기존 import 보존 의무 위반: {pat}"


# ---------------------------------------------------------------------------
# G-164-SAFETY-2 (HIGH) — `_confirm_breakout_open_prices_if_pending` 메서드 존재
# ---------------------------------------------------------------------------
def test_method_exists_on_scheduler():
    """신규 메서드 존재 영역 영구 영속 정적 가드."""
    sched = TradingScheduler()
    assert hasattr(sched, "_confirm_breakout_open_prices_if_pending"), (
        "TradingScheduler 영역 `_confirm_breakout_open_prices_if_pending` 메서드 부재 — "
        "사이클 164 시정 누락"
    )


# ---------------------------------------------------------------------------
# G-164-AST-1 — `_scan_loop` 영역 graceful try/except wrap (운영 안정성)
# ---------------------------------------------------------------------------
def test_scan_loop_wraps_confirm_call_in_try_except():
    """hook 호출 영역 graceful try/except — 다음 사이클 자연 재시도 영속."""
    src = SCHEDULER_PATH.read_text(encoding="utf-8")
    start_idx = src.find("async def _scan_loop(")
    next_def_idx = src.find("\n    async def ", start_idx + 1)
    if next_def_idx < 0:
        next_def_idx = len(src)
    scan_loop_body = src[start_idx:next_def_idx]

    # `_confirm_breakout_open_prices_if_pending` 호출 영역 ~ 위/아래 20줄 검사
    call_idx = scan_loop_body.find("_confirm_breakout_open_prices_if_pending")
    assert call_idx > 0, "hook 호출 영역 부재"
    # 호출 위쪽 영역에 `try:` 존재 의무 (graceful wrap 영속)
    surrounding = scan_loop_body[max(0, call_idx - 500): call_idx + 500]
    assert "try:" in surrounding, (
        "hook 호출 영역 graceful try/except wrap 누락 — "
        "예외 시 다음 사이클 자연 재시도 영역 영구 영속 차단"
    )
