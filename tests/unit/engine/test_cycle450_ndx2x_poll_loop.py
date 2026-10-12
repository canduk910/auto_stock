"""cycle450 — 나스닥2배 섀도 폴 루프 `_ndx2x_poll_loop` 가 첫 회전에서 죽는 결함.

결함(운영 실측 2026-10-12 21:30:03): `TradingScheduler._ndx2x_poll_loop` 가 `_datetime`·`_KST`
를 쓰는데 두 이름은 **다른 메서드**(`_swing_buy_poll_loop`)의 함수-로컬 import 다. 전략이
켜져 있으면 `sync_daily_decision()` 직후 `now_t = _datetime.now(_KST).time()` 에서
`NameError` 로 태스크가 죽는다(`Task exception was never retrieved`).

검증 행위:
  T1 집행창(09:30~10:30 KST, 양끝 포함) 안 한 회전 → REST 현재가·시가로 `check_buy_signal` 호출
  T2 집행창 밖 한 회전 → `check_buy_signal`·`fetch_stock_detail` 호출 0
  T3 실 BUY 반환 → 주문 미발사 + `[ndx2x_buy_blocked_no_limit_path]` CRITICAL (기존 계약 고정)
  G1 구조 가드 — `_ndx2x_poll_loop` 본문이 읽는 이름 중 어디에도 정의되지 않은 이름 = 0

시각 고정: `datetime` 모듈의 클래스와 `scheduler.datetime` 전역을 함께 갈아끼운다 — Green 이
함수-로컬 import 로 고치든 모듈 전역 `datetime` 으로 고치든 같은 시각을 본다. tz 없는
`now()` 는 UTC 벽시계(9시간 이른 시각)를 돌려준다 — KST 를 명시하지 않은 구현은 창 판정이
어긋나 T1 이 잡는다. sleep 은 가짜로 바꿔 한 회전 뒤 `_running` 을 내린다(실 대기 0).
"""
from __future__ import annotations

import ast
import asyncio
import builtins
import contextlib
import datetime as _dt
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine import scheduler as scheduler_mod
from src.engine.scheduler import TradingScheduler
from src.engine.strategies.ndx2x_riskoff import Ndx2xRiskoffStrategy
from src.engine.strategy_base import Signal, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

KST = _dt.timezone(_dt.timedelta(hours=9))
_SCHEDULER_PY = Path(scheduler_mod.__file__)
_DETAIL = {"stck_prpr": "60000", "stck_oprc": "59000"}


@contextlib.contextmanager
def _freeze_kst(hh: int, mm: int):
    base_kst = _dt.datetime(2026, 10, 13, hh, mm, tzinfo=KST)
    real = _dt.datetime

    class _Frozen(real):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                # UTC 호스트의 naive 벽시계 — KST 미지정 구현을 드러낸다
                return base_kst.astimezone(_dt.timezone.utc).replace(tzinfo=None)
            return base_kst.astimezone(tz)

    _dt.datetime = _Frozen
    with patch.object(scheduler_mod, "datetime", _Frozen):
        try:
            yield
        finally:
            _dt.datetime = real


def _make_scheduler(signal: Signal = Signal.NONE):
    sched = TradingScheduler.__new__(TradingScheduler)
    sched.registry = StrategyRegistry()
    sched._running = True
    sched.order_engine = MagicMock()
    sched.order_engine.execute_buy = AsyncMock()

    strategy = Ndx2xRiskoffStrategy(StrategyConfig(
        strategy_id="ndx2x_riskoff", name="나스닥2배-위험회피", enabled=True, weight=0.0, params={},
    ))
    strategy.sync_daily_decision = AsyncMock(return_value=None)
    strategy.check_buy_signal = MagicMock(return_value=signal)
    sched.registry.register(strategy)
    return sched, strategy


async def _run_one_rotation(sched, hh: int, mm: int) -> AsyncMock:
    """고정 시각에서 루프를 한 회전 돌린다. 첫 sleep 에서 `_running` 을 내려 탈출."""
    real_sleep = asyncio.sleep
    fetch = AsyncMock(return_value=dict(_DETAIL))

    async def _fake_sleep(_secs, *args, **kwargs):
        sched._running = False
        await real_sleep(0)

    with _freeze_kst(hh, mm), \
         patch("src.api.condition.fetch_stock_detail", new=fetch), \
         patch.object(scheduler_mod, "fetch_stock_detail", new=fetch), \
         patch.object(scheduler_mod.asyncio, "sleep", new=_fake_sleep):
        await asyncio.wait_for(sched._ndx2x_poll_loop(), timeout=5.0)
    return fetch


# ── T1: 집행창 안 ──

@pytest.mark.parametrize("hh,mm", [(9, 30), (9, 45), (10, 30)])
async def test_buy_signal_evaluated_when_inside_execution_window_then_check_buy_called_with_rest_prices(hh, mm):
    sched, strategy = _make_scheduler()

    fetch = await _run_one_rotation(sched, hh, mm)

    strategy.sync_daily_decision.assert_awaited_once()
    fetch.assert_awaited_once_with(strategy.FIXED_TICKER)
    strategy.check_buy_signal.assert_called_once_with(strategy.FIXED_TICKER, 60000, 59000)
    sched.order_engine.execute_buy.assert_not_called()


# ── T2: 집행창 밖 ──

@pytest.mark.parametrize("hh,mm", [(9, 29), (10, 31), (21, 30)])
async def test_buy_signal_skipped_when_outside_execution_window_then_no_quote_and_no_check_buy(hh, mm):
    sched, strategy = _make_scheduler()

    fetch = await _run_one_rotation(sched, hh, mm)

    # 창 밖에서도 일일 신호 동기화까지는 돈다 — 운영에서 죽은 자리가 바로 그 다음 줄이다
    strategy.sync_daily_decision.assert_awaited_once()
    fetch.assert_not_called()
    strategy.check_buy_signal.assert_not_called()
    sched.order_engine.execute_buy.assert_not_called()


# ── T3: 실 BUY 는 주문 없이 CRITICAL ──

async def test_real_buy_signal_when_inside_window_then_no_order_and_critical_logged(caplog):
    sched, strategy = _make_scheduler(signal=Signal.BUY)

    with caplog.at_level(logging.CRITICAL, logger="src.engine.scheduler"):
        await _run_one_rotation(sched, 9, 45)

    sched.order_engine.execute_buy.assert_not_called()
    blocked = [
        r for r in caplog.records
        if r.levelno >= logging.CRITICAL
        and r.getMessage().startswith("[ndx2x_buy_blocked_no_limit_path] ")
    ]
    assert len(blocked) == 1
    assert strategy.FIXED_TICKER in blocked[0].getMessage()


# ── G1: 구조 가드 — 정의되지 않은 이름 0 (이 메서드 하나만) ──

def _bound_in(node: ast.AST) -> set[str]:
    """`node` 아래(중첩 함수 포함)에서 묶이는 이름 — 대입·import·인자·def·except as."""
    bound: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            bound.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            bound.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(n.name)
        elif isinstance(n, ast.arg):
            bound.add(n.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
    return bound


def _module_globals(tree: ast.Module) -> set[str]:
    """모듈 전역에서 묶이는 이름 — 함수·클래스 **본문 안**은 세지 않는다."""
    names: set[str] = set()
    stack: list[ast.AST] = list(tree.body)
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
            continue
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            names.add(n.id)
        stack.extend(ast.iter_child_nodes(n))
    return names


def test_ndx2x_poll_loop_reads_only_defined_names():
    tree = ast.parse(_SCHEDULER_PY.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TradingScheduler")
    fn = next(
        n for n in cls.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_ndx2x_poll_loop"
    )

    loaded = {
        n.id for n in ast.walk(fn)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    assert loaded, "가드 공허 방지 — 본문에서 읽는 이름이 하나도 안 잡혔다"

    undefined = loaded - _bound_in(fn) - _module_globals(tree) - set(dir(builtins))
    assert undefined == set(), (
        f"_ndx2x_poll_loop 가 정의되지 않은 이름을 읽는다: {sorted(undefined)} "
        "— 다른 메서드의 함수-로컬 import 는 이 메서드에서 보이지 않는다"
    )
