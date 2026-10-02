"""cycle398 PR0 — 전략 배선 골든(특성 테스트). 리팩토링 카드 #2(등록 명부)·#3(원형 선언) 의 행위 동일 증명.

설계 = `_workspace/refactor/2026-10-02_cards_2_3_design.md` §5 · 자문 = `_workspace/domain_consult/cycle398_refactor_cards_2_3.md` §5.1(G1~G9).
사용자 결정(10-02): A 원형 선언 = 등록 명부 필수 칸 · B `risk.py:88` 리터럴 유지 + 교차 검사 · C 명부에 없는 전략 파일 = 테스트 실패 · D PR1·PR2 분리.

## 무엇을 얼리나

지금 코드(main `0b011f9`)의 배선을 `tests/fixtures/strategy_wiring_golden.json` 에 얼려 두고, 같은 값을 다시 만들어 비교한다.

| 묶음 | 내용 |
|---|---|
| G1 등록 표 | `TradingScheduler().registry.all()` 의 (id, 이름, 켜짐, 비중, 클래스명) 7행, 순서까지 |
| G2 상수 표 | `_SWING_POLL_STRATEGIES` · `risk._TICK_BUY_EVAL_SKIP_STRATEGIES`(=`risk.py:88`) 외 전략 id 상수 |
| G3 반복 대상 표 | `scheduler.py` 의 `for … in <식>` 중 식이 전략 id 묶음인 자리 전수(AST, 키 = 함수 이름 + 그 함수 안 순번 — 줄 번호를 쓰지 않는다) |
| G4 켜짐 조합 128가지 | 조합마다 구독 수집기 3종 · 구독 인자 빌더 2종 · `_scan_loop` 1회 구독 인자 · 재 prepare 호출 순서 · 시가 확정 재시도 순서 · 시가 확정 대상 순서 · 15:20 강제청산 `execute_sell` 순서 · 익일청산 보류 순서 · 보유 REST 폴 순서 · 스윙 매수 폴 1주기 순서 · 재시작 복구 훅 호출 |
| G7 틱 평가 행렬 | 7전략 전부 켠 상태에서 `risk.on_tick` 의 매수 평가·청산 평가 호출 순서 |
| G8 부팅 복구 훅 | `boot_manager.boot()` 전체 경로에서 복구 훅 호출 순서·횟수(돈키언 2훅 중 `recompute_held_atr` 만 1회) · 켜짐과 무관 · DB 포지션 복구 뒤 |
| C 파일 = 등록 | 전략 디렉터리 파일 집합 == 등록된 전략 id 집합(결정 C) |

## 골든을 다시 만드는 것은 행위 변경 사이클에서만 한다

PR1·PR2(행위 동일 리팩토링)는 이 파일과 골든을 고치지 않는다. 다시 만들기:

    python tools/test_fixtures/gen_strategy_wiring_golden.py

(이 테스트 모듈을 `STRATEGY_WIRING_GOLDEN_REGEN=1` 로 돌린다 — conftest autouse 가 같은 환경을 만든다.)

## 골든이 못 잡는 것

- 값이 우연히 같은 다른 사실을 합치는 것(`:2038` 15:20 청산 대상 = 시가 목표가 대상) — 리뷰 규약으로 지킨다.
- `run_daily` 본문 안의 07:55 사전 구독 재 prepare(`:782`)·09:30 구독은 실행하지 않는다. 반복 대상은 G3 가,
  구독 인자는 같은 빌더(G4 `presub_args`·`args_0930`)가 덮는다.
- 로그 문구는 익일청산 `write_log` 와 시가 재시도 로그의 전략 순서만 본다.
"""
from __future__ import annotations

import ast
import contextlib
import datetime as _dt_mod
import hashlib
import json
import os
import subprocess
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "tests" / "fixtures" / "strategy_wiring_golden.json"
SCHEDULER_PY = ROOT / "src" / "engine" / "scheduler.py"
REGEN = os.environ.get("STRATEGY_WIRING_GOLDEN_REGEN") == "1"

_KST = _dt_mod.timezone(_dt_mod.timedelta(hours=9))
_PAST = _dt_mod.date(2026, 1, 2)
_MOMENTUM_SCAN = ["900001", "900002"]
#: 켜짐 비트·가짜 종목 번호의 고정 배정(= 지금 등록 순서). 등록 순서와 따로 둔다 — 등록 순서가 바뀌면
#: 종목 번호가 따라 바뀌어 모든 묶음이 붉어지는 대신, 순서에 기대는 묶음만 붉어진다.
_SID_INDEX = {
    "momentum": 0, "volatility_breakout": 1, "long_tail_volatility": 2, "donchian_swing": 3,
    "bull_flag_breakout": 4, "vcp_breakout": 5, "kojiro": 6, "etf_trend": 7,
}

# 전략 id 판정용 — 등록 표와 별개로 고정(골든 대상을 고르는 체이므로 등록에서 뽑지 않는다).
_KNOWN_IDS = frozenset(_SID_INDEX)


# ---------------------------------------------------------------------------
# 공통 도구
# ---------------------------------------------------------------------------
def _jsonable(v):
    """집합은 정렬 리스트, 튜플은 리스트, enum 은 value — 비교 가능한 JSON 모양."""
    import enum

    if isinstance(v, enum.Enum):
        return v.value if isinstance(v.value, (str, int)) else v.name
    if isinstance(v, (set, frozenset)):
        return sorted(_jsonable(x) for x in v)
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(_jsonable(k)): _jsonable(x) for k, x in v.items()}
    return v


class _InstantAsyncio:
    """scheduler 모듈의 `asyncio` 자리에 끼우는 대리 — `sleep` 만 즉시 반환, 나머지는 진짜."""

    def __init__(self, stopper=None, limit: int = 400):
        import asyncio as _real

        self._real = _real
        self._stopper = stopper
        self._limit = limit
        self.calls = 0

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def sleep(self, *_a, **_k):
        self.calls += 1
        if self._stopper is not None and self.calls > self._limit:
            self._stopper()
        await self._real.sleep(0)


@contextlib.contextmanager
def _freeze_kst(iso: str):
    """`datetime.now` 만 고정 — freezegun 은 monotonic 까지 얼려 asyncio 가 멈춘다(cycle273e R6 답습)."""
    base_naive = _dt_mod.datetime.fromisoformat(iso)
    base_kst = base_naive.replace(tzinfo=_KST)

    class _Frozen(_dt_mod.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return base_naive
            off = getattr(tz, "utcoffset", lambda _x: None)(None)
            if off == _KST.utcoffset(None):
                return base_kst
            return base_kst.astimezone(tz)

    from src.engine import scheduler as _sched

    real = _dt_mod.datetime
    _dt_mod.datetime = _Frozen
    sched_patched = getattr(_sched, "datetime", None) is real
    if sched_patched:
        _sched.datetime = _Frozen
    try:
        yield
    finally:
        _dt_mod.datetime = real
        if sched_patched:
            _sched.datetime = real


def _new_scheduler(mask: int):
    """켜짐 조합 `mask`(등록 순서 비트) + 전략별 가짜 후보·보유·주문중을 심은 새 스케줄러."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_base import Position

    ts = TradingScheduler()
    for s in ts.registry.all():
        sid = s.config.strategy_id
        i = _SID_INDEX[sid]  # 등록 순서가 아니라 고정 번호 — 순서가 바뀌면 그 차이만 보이게
        s.config.enabled = bool(mask >> i & 1)
        n = i + 1
        cands = [f"{n}00001", f"{n}00002"]
        if hasattr(s, "get_scanned_tickers"):
            s.get_scanned_tickers = (lambda c=cands: list(c))
            s._scanned_tickers = list(cands)
        held = f"{n}00009"
        s.state.positions[held] = Position(
            ticker=held, buy_price=1000, quantity=1, order_no=f"O{n}", strategy_id=sid, buy_date=_PAST,
        )
        s.state.pending_buys.add(f"{n}00003")
        s.state.total_investment = 100_000_000
    return ts


def _set_scanned(ts, sid: str, tickers: list[str]) -> None:
    s = ts.registry.get(sid)
    if s is not None and hasattr(s, "get_scanned_tickers"):
        s.get_scanned_tickers = (lambda c=list(tickers): list(c))
        s._scanned_tickers = list(tickers)


# ---------------------------------------------------------------------------
# G1 · G2 · G3 — 정적 표
# ---------------------------------------------------------------------------
def snap_registry() -> list:
    from src.engine.scheduler import TradingScheduler

    return [
        [s.config.strategy_id, s.config.name, s.config.enabled, s.config.weight, type(s).__name__]
        for s in TradingScheduler().registry.all()
    ]


def snap_constants() -> dict:
    from src.engine import (
        funnel_capture, open_price_rest, param_catalog, risk, scheduler, session, status_exit_watch,
        strategy_base,
    )

    return _jsonable({
        "scheduler._SWING_POLL_STRATEGIES": scheduler._SWING_POLL_STRATEGIES,
        "risk._TICK_BUY_EVAL_SKIP_STRATEGIES": risk._TICK_BUY_EVAL_SKIP_STRATEGIES,
        "risk._PRE_MARKET_EXIT_EVAL_STRATEGIES": risk._PRE_MARKET_EXIT_EVAL_STRATEGIES,
        "risk._DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES": risk._DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES,
        "strategy_base.Position._MULTIDAY_STRATEGIES": strategy_base.Position._MULTIDAY_STRATEGIES,
        "strategy_base._ALWAYS_STATUS_GATE_CANDIDATE_SIDS": strategy_base._ALWAYS_STATUS_GATE_CANDIDATE_SIDS,
        "status_exit_watch._GROUP": status_exit_watch._GROUP,
        "status_exit_watch._SWING_GROUP": status_exit_watch._SWING_GROUP,
        "session._DEFAULT_TRADABLE_BOARDS": session._DEFAULT_TRADABLE_BOARDS,
        "param_catalog.STRATEGY_IDS": param_catalog.STRATEGY_IDS,
        "param_catalog._TURTLE_SIZED": param_catalog._TURTLE_SIZED,
        "param_catalog._VBLTV": param_catalog._VBLTV,
        "funnel_capture._ORDER": funnel_capture._ORDER,
        "open_price_rest._BASIS_STRATEGIES": open_price_rest._BASIS_STRATEGIES,
    })


def snap_for_loops() -> dict:
    """`scheduler.py` 의 `for … in <식>` 중 식이 전략 id 묶음인 자리 전수.

    식은 호출 없는 모양(튜플·리스트 리터럴 · 이름 · 속성)만 모듈 이름공간에서 평가한다 — 리터럴이
    명부 파생 이름으로 바뀌어도 같은 값이면 같은 골든이다. 키 = `함수 qualname#순번`.
    """
    from src.engine import scheduler as sched_mod

    src = SCHEDULER_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    ns = vars(sched_mod)
    out: dict[str, list] = {}

    def visit(node, qual: list[str]):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = qual + [child.name]
                counter = {"n": 0}
                _scan_body(child, ".".join(q), counter)
                visit(child, q)
            else:
                visit(child, qual)

    def _scan_body(fn, qname: str, counter: dict):
        # 이 함수 본문(중첩 함수 제외)의 For/AsyncFor 를 소스 순서로
        stack = list(reversed(list(ast.iter_child_nodes(fn))))
        found = []
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(n, (ast.For, ast.AsyncFor)):
                found.append(n)
            stack.extend(reversed(list(ast.iter_child_nodes(n))))
        found.sort(key=lambda n: (n.lineno, n.col_offset))
        for n in found:
            it = n.iter
            if not isinstance(it, (ast.Tuple, ast.List, ast.Name, ast.Attribute)):
                continue
            try:
                val = eval(compile(ast.Expression(it), "<for-iter>", "eval"), dict(ns))  # noqa: S307
            except Exception:
                continue
            if isinstance(val, (tuple, list, frozenset, set)) and val and all(isinstance(x, str) for x in val) \
                    and any(x in _KNOWN_IDS for x in val):
                counter["n"] += 1
                key = f"{qname}#{counter['n']}"
                out[key] = sorted(val) if isinstance(val, (set, frozenset)) else list(val)

    visit(tree, [])
    return out


# ---------------------------------------------------------------------------
# G4 — 켜짐 조합별 행위 추적
# ---------------------------------------------------------------------------
def snap_collectors(mask: int) -> dict:
    ts = _new_scheduler(mask)
    breakout = ts._collect_breakout_tickers()
    swing = ts._collect_swing_tickers()
    return {
        "breakout": breakout,
        "swing": swing,
        "presub": sorted(ts._collect_presubscribe_tickers()),
        "enabled_order": [s.config.strategy_id for s in ts.registry.enabled()],
        "presub_args": {
            "source_counts": ts._build_subscription_source_counts(momentum_tickers=None),
            "priority_groups": ts._build_priority_groups(momentum_tickers=None),
        },
        "args_0930": {
            "extra": breakout + swing,
            "source_counts": ts._build_subscription_source_counts(momentum_tickers=list(_MOMENTUM_SCAN)),
            "priority_groups": ts._build_priority_groups(momentum_tickers=list(_MOMENTUM_SCAN)),
        },
    }


async def snap_scan_loop(mask: int) -> dict:
    from src.engine import scheduler as sched_mod

    ts = _new_scheduler(mask)
    ts._running = True
    calls: list = []

    async def _subscribe(tickers, *, extra_tickers=None, source_counts=None, priority_groups=None, **kw):
        calls.append({
            "tickers": list(tickers),
            "extra": sorted(extra_tickers or []),  # list(set(...)) 라 순서는 계약 아님
            "source_counts": dict(source_counts or {}),
            "priority_groups": {k: list(v) for k, v in (priority_groups or {}).items()},
        })
        ts._running = False

    stubs = [
        "_delta_unsubscribe_dropped", "_reprepare_breakout_if_empty", "_confirm_breakout_open_prices_if_pending",
        "_resubscribe_stale_priority", "_evaluate_universe_guard", "_subscribe_market_operation_tickers",
        "_refresh_stale_ccnl_cache", "_auto_capture_funnel_snapshots", "_report_tick_coverage",
        "_sync_positions_from_balance",
    ]
    with contextlib.ExitStack() as es:
        for name in stubs:
            es.enter_context(patch.object(ts, name, new=AsyncMock()))
        es.enter_context(patch.object(sched_mod, "scan_stocks", new=AsyncMock(return_value=list(_MOMENTUM_SCAN))))
        es.enter_context(patch.object(sched_mod, "subscribe_filtered_stocks", new=_subscribe))
        es.enter_context(patch.object(sched_mod, "asyncio", new=_InstantAsyncio(lambda: setattr(ts, "_running", False))))
        await ts._scan_loop(first_delay=0)
    return {"subscribe_calls": calls}


async def snap_reprepare(mask: int) -> list:
    from src.engine import funnel_capture
    from src.engine import scheduler as sched_mod

    ts = _new_scheduler(mask)
    for s in ts.registry.all():
        _set_scanned(ts, s.config.strategy_id, [])
    order: list = []

    async def _live(strategy, *, phase):
        order.append([strategy.config.strategy_id, phase])
        return True

    with patch.object(funnel_capture, "live_prepare_one", new=_live), \
            patch.object(sched_mod, "write_log", new=AsyncMock()):
        await ts._reprepare_breakout_if_empty()
    return order


async def snap_confirm_if_pending(mask: int) -> list:
    from src.engine import scheduler as sched_mod
    from src.engine.session import MarketBoard, session_tracker

    ts = _new_scheduler(mask)
    for s in ts.registry.all():
        if hasattr(s, "_targets"):
            s._targets = {t: {} for t in s.get_scanned_tickers()}
            s._open_confirmed = {}
    log = MagicMock()
    boards: list = []

    async def _confirm(*, board=None, **kw):
        boards.append(board)

    with patch.object(sched_mod, "logger", new=log), \
            patch.object(session_tracker, "_active", frozenset({MarketBoard.MAIN})), \
            patch.object(ts, "_confirm_breakout_open_prices", new=_confirm):
        await ts._confirm_breakout_open_prices_if_pending()
    retried = [
        c.args[1] for c in log.info.call_args_list
        if c.args and isinstance(c.args[0], str) and c.args[0].startswith("[open_confirm_retry]")
    ]
    return [retried, boards]


async def snap_confirm_open_prices(mask: int) -> list:
    from src.engine import open_price_observe, open_price_rest

    ts = _new_scheduler(mask)
    order: list = []
    for s in ts.registry.all():
        if hasattr(s, "_targets"):
            sid = s.config.strategy_id
            s._targets = {t: {} for t in s.get_scanned_tickers()}
            s._open_confirmed = {}
            s.on_open_price_confirmed = (
                lambda ticker, price, board=None, source=None, _sid=sid: order.append([_sid, ticker, board, source])
            )
    with patch("src.api.condition.fetch_stock_detail", new=AsyncMock(return_value={"stck_oprc": "1000"})), \
            patch.object(open_price_rest, "owns_board", new=lambda *_a, **_k: False), \
            patch.object(open_price_observe, "mark_confirmed_via_rest", new=lambda *_a, **_k: None), \
            patch.object(ts, "_emit_breakout_open_confirm", new=lambda *_a, **_k: None):
        await ts._confirm_breakout_open_prices(board="main", max_wait_s=0)
    return order


async def snap_force_clear(mask: int) -> list:
    from src.engine import scheduler as sched_mod

    ts = _new_scheduler(mask)
    for s in ts.registry.all():
        if hasattr(s, "check_force_clear"):
            s.check_force_clear = (lambda _s=s: list(_s.state.positions.keys()))
    sells: list = []

    async def _sell(ticker, signal, sid, *a, **k):
        sells.append([ticker, signal.name, sid])

    ts.order_engine.execute_sell = _sell
    with _freeze_kst("2026-01-05 15:20:30"), patch.object(sched_mod, "write_log", new=AsyncMock()):
        await ts._force_clear_main_only()
    return sells


async def snap_next_day_clear(mask: int) -> dict:
    from src.engine import scheduler as sched_mod

    ts = _new_scheduler(mask)
    saved: list = []
    subs: list = []
    logs: list = []

    async def _save(day, ticker, sid, *, reason=None):
        saved.append([ticker, sid, reason])

    async def _sub(tr_id, ticker, *a, **k):
        subs.append(ticker)

    async def _wl(level, msg, *a, **k):
        logs.append(msg)

    with patch("src.db.stock_master.get", new=AsyncMock(return_value=types.SimpleNamespace(nxt_tradable=False))), \
            patch("src.db.pending_next_day_clear.save_pending_ndc", new=_save), \
            patch.object(sched_mod.kis_ws, "subscribe", new=_sub), \
            patch.object(sched_mod, "write_log", new=_wl), \
            patch.object(sched_mod, "asyncio", new=_InstantAsyncio()):
        await ts._execute_next_day_clear()
    return {"saved": saved, "subscribed": subs, "logs": logs,
            "pending": sorted([list(x) for x in ts._pending_next_day_clear])}


async def snap_rest_poll(mask: int) -> dict:
    from src.engine import scanner
    from src.engine import scheduler as sched_mod

    ts = _new_scheduler(mask)
    ts._running = True
    fetched: list = []
    ticks: list = []

    async def _fetch(ticker):
        fetched.append(ticker)
        return {"stck_prpr": "1000", "stck_oprc": "990", "prdy_ctrt": "1.0", "stck_hgpr": "1010"}

    async def _on_tick(ticker, *a, **k):
        ticks.append(ticker)

    stats_box: list = []
    with patch.object(sched_mod, "fetch_stock_detail", new=_fetch), \
            patch.object(ts.risk_manager, "on_tick", new=_on_tick), \
            patch.object(sched_mod, "record_swing_rest_poll", new=lambda st: stats_box.append(dict(st))), \
            patch.object(sched_mod, "asyncio", new=_InstantAsyncio()), \
            patch.dict(scanner.ticker_prices, {}, clear=False), \
            patch.dict(scanner.ticker_last_tick, {}, clear=False), \
            patch.dict(scanner.ticker_names, {}, clear=False):
        stats = await ts._run_swing_rest_poll_once()
    stats = {k: v for k, v in stats.items() if k != "elapsed_ms"}
    return {"fetched": fetched, "on_tick": ticks, "stats": stats}


async def snap_swing_buy_poll(mask: int) -> dict:
    from src.engine import scheduler as sched_mod
    from src.engine.strategy_base import Signal

    ts = _new_scheduler(mask)
    ts._running = True
    fetched: list = []
    evals: list = []
    buys: list = []
    for s in ts.registry.all():
        sid = s.config.strategy_id

        def _cbs(ticker, cur, opn, _sid=sid):
            evals.append([_sid, ticker])
            return Signal.BUY

        s.check_buy_signal = _cbs

    async def _fetch(ticker):
        fetched.append(ticker)
        return {"stck_prpr": "1000", "stck_oprc": "990"}

    async def _buy(ticker, price, strategy, *a, **k):
        buys.append([ticker, strategy.config.strategy_id])

    ts.order_engine.execute_buy = _buy
    log = MagicMock()

    def _info(fmt, *args, **kw):
        if isinstance(fmt, str) and fmt.startswith("[swing_poll] candidates="):
            ts._running = False

    log.info.side_effect = _info
    with _freeze_kst("2026-01-05 09:10:00"), \
            patch("src.api.condition.fetch_stock_detail", new=_fetch), \
            patch.object(sched_mod, "logger", new=log), \
            patch.object(sched_mod, "asyncio", new=_InstantAsyncio(lambda: setattr(ts, "_running", False))):
        await ts._swing_buy_poll_loop()
    return {"fetched": fetched, "check_buy_signal": evals, "execute_buy": buys}


async def snap_eager_hooks(mask: int) -> list:
    ts = _new_scheduler(mask)
    calls: list = []
    for s in ts.registry.all():
        sid = s.config.strategy_id
        for hook in ("recompute_held_atr", "recompute_high_since_buy"):
            if hasattr(s, hook):
                async def _rec(_sid=sid, _hook=hook):
                    calls.append([_sid, _hook])
                setattr(s, hook, _rec)
    with patch("src.db.stock_master.is_stale", new=AsyncMock(return_value=False)):
        await ts._eager_refresh_stock_master_for_held_positions()
    return calls


COMBO_SECTIONS = (
    "collectors", "scan_loop", "reprepare", "confirm_if_pending", "confirm_open_prices_main",
    "force_clear_1520", "next_day_clear", "rest_poll", "swing_buy_poll", "eager_restore_hooks",
)


async def snap_section(section: str, mask: int):
    fn = {
        "collectors": lambda m: _as_coro(snap_collectors(m)),
        "scan_loop": snap_scan_loop,
        "reprepare": snap_reprepare,
        "confirm_if_pending": snap_confirm_if_pending,
        "confirm_open_prices_main": snap_confirm_open_prices,
        "force_clear_1520": snap_force_clear,
        "next_day_clear": snap_next_day_clear,
        "rest_poll": snap_rest_poll,
        "swing_buy_poll": snap_swing_buy_poll,
        "eager_restore_hooks": snap_eager_hooks,
    }[section]
    return _jsonable(await fn(mask))


async def _as_coro(v):
    return v


# ---------------------------------------------------------------------------
# G7 — 틱 평가 행렬 (7전략 전부 켜짐)
# ---------------------------------------------------------------------------
async def snap_tick_matrix() -> dict:
    from src.engine import risk as risk_mod
    from src.engine import scanner
    from src.engine.session import MarketBoard, session_tracker
    from src.engine.strategy_base import Position, Signal

    out = {}
    for case in ("nobody_holds", "all_hold"):
        ts = _new_scheduler(0b1111111)
        ticker = "555555"
        buy_calls: list = []
        exit_calls: list = []
        for s in ts.registry.all():
            sid = s.config.strategy_id
            s.check_buy_signal = (lambda t, c, o, _sid=sid: (buy_calls.append(_sid), Signal.NONE)[1])
            s.check_exit_signal = (lambda t, c, o, _sid=sid: (exit_calls.append(_sid), Signal.NONE)[1])
            if case == "all_hold":
                s.state.positions[ticker] = Position(
                    ticker=ticker, buy_price=1000, quantity=1, order_no=f"T-{sid}", strategy_id=sid, buy_date=_PAST,
                )
        ts.order_engine._selling = set()
        pinned = _dt_mod.datetime(2026, 1, 5, 10, 30, 0, tzinfo=_KST)
        with patch.object(session_tracker, "_active", frozenset({MarketBoard.MAIN})), \
                patch.object(risk_mod, "_now_kst", new=lambda: pinned, create=True), \
                patch.dict(scanner.ticker_prev_close, {ticker: 1000}, clear=False), \
                patch.dict(scanner.ticker_prices, {}, clear=False), \
                patch.object(ts.order_engine, "execute_buy", new=AsyncMock()), \
                patch.object(ts.order_engine, "execute_sell", new=AsyncMock()):
            await ts.risk_manager.on_tick(ticker, current_price=1050, open_price=1000, change_rate=5.0)
        out[case] = {"check_buy_signal": buy_calls, "check_exit_signal": exit_calls}
    return out


# ---------------------------------------------------------------------------
# G8 — 부팅 전체 경로의 복구 훅
# ---------------------------------------------------------------------------
async def snap_boot_hooks(mask: int) -> dict:
    from src.engine import boot_manager

    real = _new_scheduler(mask)
    rows = []
    holdings = []
    for s in real.registry.all():
        for t, p in list(s.state.positions.items()):
            rows.append({
                "ticker": t, "ticker_name": t, "buy_price": p.buy_price, "quantity": p.quantity,
                "order_no": p.order_no, "strategy_id": p.strategy_id, "buy_date": _PAST, "high_since_buy": p.buy_price,
            })
            holdings.append(MagicMock(ticker=t, quantity=p.quantity, avg_price=p.buy_price, name=t))
        s.state.positions.clear()
        s.state.pending_buys.clear()

    calls: list = []
    for s in real.registry.all():
        sid = s.config.strategy_id
        for hook in ("recompute_held_atr", "recompute_high_since_buy"):
            if hasattr(s, hook):
                async def _rec(_s=s, _sid=sid, _hook=hook):
                    # 호출 시점에 그 전략 보유가 DB 에서 복구돼 있었는가
                    calls.append([_sid, _hook, sorted(_s.state.positions.keys())])
                setattr(s, hook, _rec)

    sm = MagicMock()
    sm.registry = real.registry
    sm.order_engine = real.order_engine
    sm._pending_next_day_clear = set()
    sm._preissue_all_tokens = AsyncMock()
    sm._load_strategy_config = AsyncMock()
    sm._refresh_market_regime_and_persist = AsyncMock()
    sm._resolve_cash_usage_ratio = AsyncMock(return_value=1.0)
    sm._sync_orders_to_db = AsyncMock()
    sm._eager_refresh_stock_master_for_held_positions = real._eager_refresh_stock_master_for_held_positions
    real._pending_next_day_clear = set()

    with patch("src.engine.boot_manager.token_manager") as tm, \
            patch("src.engine.boot_manager.get_balance",
                  new=AsyncMock(return_value=(holdings, MagicMock(net_asset=1_000_000)))), \
            patch("src.engine.boot_manager.get_daily_orders", new=AsyncMock(return_value=[])), \
            patch("src.engine.boot_manager.write_log", new=AsyncMock()), \
            patch("src.engine.funnel_capture.live_prepare_one", new=AsyncMock(return_value=True)), \
            patch("src.db.stock_master.count_active", new=AsyncMock(return_value=2768)), \
            patch("src.db.stock_master.is_stale", new=AsyncMock(return_value=False)), \
            patch("src.db.positions.load_all", new=AsyncMock(return_value=rows)), \
            patch("src.db.positions.save_position", new=AsyncMock()), \
            patch("src.db.positions.delete_position", new=AsyncMock()), \
            patch("src.db.trade_history.get_recent_buy_strategy", new=AsyncMock(return_value=None)), \
            patch("src.db.trade_history.mark_pending_buys_completed", new=AsyncMock()), \
            patch("src.db.trade_history.get_today_buys_ticker_strategy", new=AsyncMock(return_value=[])):
        tm.get_token = AsyncMock()
        await boot_manager.boot(sm)
    return {"calls": calls,
            "restored": {s.config.strategy_id: sorted(s.state.positions.keys()) for s in real.registry.all()}}


BOOT_MASKS = (0, 2 ** len(_SID_INDEX) - 1, 1)


# ---------------------------------------------------------------------------
# 골든 생성 · 로드
# ---------------------------------------------------------------------------
async def build_golden() -> dict:
    head = "unknown"
    with contextlib.suppress(Exception):
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    combos = {}
    for mask in range(2 ** len(_SID_INDEX)):
        combos[str(mask)] = {sec: await snap_section(sec, mask) for sec in COMBO_SECTIONS}
    return {
        "_meta": {
            "note": "cycle398 PR0 — 지금 배선의 골든. 행위 변경 사이클에서만 다시 만든다 "
                    "(python tools/test_fixtures/gen_strategy_wiring_golden.py).",
            "generated_at_commit": head,
            "scheduler_py_sha256": hashlib.sha256(SCHEDULER_PY.read_bytes()).hexdigest(),
            "mask_bit_order": sorted(_SID_INDEX, key=_SID_INDEX.get),
        },
        "registry": snap_registry(),
        "constants": snap_constants(),
        "for_loops": snap_for_loops(),
        "combos": combos,
        "tick_matrix": _jsonable(await snap_tick_matrix()),
        "boot_hooks": {str(m): _jsonable(await snap_boot_hooks(m)) for m in BOOT_MASKS},
    }


def _golden() -> dict:
    if not GOLDEN.exists():
        pytest.fail(f"골든 파일이 없다: {GOLDEN} — python tools/test_fixtures/gen_strategy_wiring_golden.py")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _mask_name(mask: int) -> str:
    on = [sid for sid, i in _SID_INDEX.items() if mask >> i & 1]
    return f"mask={mask} 켜짐={on}"


@pytest.mark.skipif(not REGEN, reason="골든 재생성은 STRATEGY_WIRING_GOLDEN_REGEN=1 일 때만")
@pytest.mark.asyncio
async def test_regenerate_golden():
    data = await build_golden()
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 단언
# ---------------------------------------------------------------------------
def test_g0_golden_shape():
    g = _golden()
    assert len(g["combos"]) == 2 ** len(_SID_INDEX), "켜짐 조합 2**N가지가 다 있어야 한다"
    assert all(set(v) == set(COMBO_SECTIONS) for v in g["combos"].values())
    assert set(g["boot_hooks"]) == {str(m) for m in BOOT_MASKS}


def test_g1_registry_table_order_and_defaults():
    """G1 — 등록 7행(id·이름·켜짐·비중·클래스명) 순서까지. 순서 = `risk.on_tick` 평가 순서 = 같은 틱 매수 우선순위.

    🔴 기본값(momentum 만 켜짐·비중 1.0)은 장식이 아니다 — `_load_strategy_config` 가 DB 조회에 실패하면 이 값으로 돈다.
    """
    assert snap_registry() == _golden()["registry"], "등록 표(순서·이름·기본 켜짐/비중·클래스)가 바뀌었다"


def test_g1b_registry_literal():
    """G1 의 리터럴 사본 — 골든 파일을 다시 만들어 G1 을 덮어도 이 줄은 남는다."""
    assert [r[0] for r in snap_registry()] == [
        "momentum", "volatility_breakout", "long_tail_volatility", "donchian_swing",
        "bull_flag_breakout", "vcp_breakout", "kojiro", "etf_trend",
    ]
    assert [(r[2], r[3]) for r in snap_registry()] == [(True, 1.0)] + [(False, 0.0)] * 7


@pytest.mark.parametrize("name", sorted(json.loads(GOLDEN.read_text(encoding="utf-8"))["constants"])
                         if GOLDEN.exists() else ["<골든 없음>"])
def test_g2_wiring_constants(name):
    g = _golden()["constants"]
    assert name in g
    assert snap_constants()[name] == g[name], f"배선 상수 {name} 가 바뀌었다"


def test_g2b_risk_tick_buy_skip_set_is_donchian_kojiro_etf_trend():
    """결정 B — `risk.py:88` 리터럴은 유지한다. cycle403(R3 승인, 10-03) 으로 etf_trend 가
    합류해 지금 값은 {donchian_swing, kojiro, etf_trend} 이고 스윙 폴 대상과 같다."""
    from src.engine import risk, scheduler

    assert risk._TICK_BUY_EVAL_SKIP_STRATEGIES == frozenset({"donchian_swing", "kojiro", "etf_trend"})
    assert frozenset(scheduler._SWING_POLL_STRATEGIES) == risk._TICK_BUY_EVAL_SKIP_STRATEGIES, (
        "틱 매수 평가 제외(risk.py:88)와 스윙 폴 대상이 갈라졌다 — 폴형 전략을 더했으면 risk.py:88 도 함께"
    )


def test_g3_scheduler_for_loop_targets():
    """G3 — `scheduler.py` 의 전략 id 반복 대상 전수(AST). 줄이 밀려도 안정 — 키는 함수 이름 + 순번."""
    got = snap_for_loops()
    exp = _golden()["for_loops"]
    assert set(got) == set(exp), f"반복 자리 집합이 바뀌었다: 추가 {sorted(set(got) - set(exp))} · 빠짐 {sorted(set(exp) - set(got))}"
    diff = {k: (exp[k], got[k]) for k in exp if got[k] != exp[k]}
    assert not diff, f"반복 대상 값·순서가 바뀌었다: {diff}"


def test_g3b_for_loop_count_floor():
    """탐지기 무효화 방지 — 지금 12자리가 잡힌다(설계 §5.1-3)."""
    assert len(snap_for_loops()) >= 12


@pytest.mark.parametrize("section", COMBO_SECTIONS)
@pytest.mark.asyncio
async def test_g4_combo_behavior(section):
    """G4·G5·G6·G9 — 켜짐 조합 2**N가지(N=등록 전략 수) × 배선 함수의 결과·호출 순서가 골든과 같다."""
    combos = _golden()["combos"]
    bad = []
    total = 2 ** len(_SID_INDEX)
    for mask in range(total):
        got = await snap_section(section, mask)
        if got != combos[str(mask)][section]:
            bad.append((mask, combos[str(mask)][section], got))
    assert not bad, (
        f"[{section}] {len(bad)}/{total} 조합이 골든과 다르다. 첫 사례 {_mask_name(bad[0][0])}\n"
        f"  골든: {bad[0][1]}\n  지금: {bad[0][2]}"
    )


@pytest.mark.asyncio
async def test_g4b_key_orders_literal():
    """골든의 핵심 순서를 리터럴로 한 번 더 — 7전략 전부 켠 조합."""
    full = 0b1111111
    col = await snap_section("collectors", full)
    # 구독 우선순위 BFB→VCP→VB→LTV (2026-08-08 사용자 결정)
    assert col["breakout"] == ["500001", "500002", "600001", "600002", "200001", "200002", "300001", "300002"]
    assert col["swing"] == ["400001", "400002", "700001", "700002"]
    # 재 prepare 순서 = 등록 순서 VB→LTV→BFB→VCP (자문 X2 — 구독 순서와 다르다)
    assert [r[0] for r in await snap_section("reprepare", full)] == [
        "volatility_breakout", "long_tail_volatility", "bull_flag_breakout", "vcp_breakout"]
    # 15:20 강제청산 VB→LTV · 익일청산 momentum→LTV→VB (자문 X3 — 등록 순서와 다르다)
    assert [r[2] for r in await snap_section("force_clear_1520", full)] == ["volatility_breakout", "long_tail_volatility"]
    assert [r[1] for r in (await snap_section("next_day_clear", full))["saved"]] == [
        "momentum", "long_tail_volatility", "volatility_breakout"]
    # 스윙 폴 순서 donchian→kojiro
    assert [r[1] for r in (await snap_section("swing_buy_poll", full))["execute_buy"]] == [
        "donchian_swing", "donchian_swing", "kojiro", "kojiro"]


@pytest.mark.asyncio
async def test_g7_tick_evaluation_matrix():
    """G7 — 같은 틱에서 7전략의 매수·청산 평가 호출 순서. 틱 매수 제외 2전략(donchian·kojiro)은 청산만."""
    got = _jsonable(await snap_tick_matrix())
    assert got == _golden()["tick_matrix"]
    assert "donchian_swing" not in got["nobody_holds"]["check_buy_signal"]
    assert "kojiro" not in got["nobody_holds"]["check_buy_signal"]


@pytest.mark.parametrize("mask", BOOT_MASKS)
@pytest.mark.asyncio
async def test_g8_boot_restore_hooks(mask):
    """G8·G9 — 부팅 복구 훅: 돈키언은 `recompute_held_atr` 1회(`recompute_high_since_buy` 0회) ·
    kojiro `held_atr` 1 · VCP·BFB `high_since_buy` 1 · 켜짐과 무관 · DB 포지션 복구 뒤."""
    got = _jsonable(await snap_boot_hooks(mask))
    assert got == _golden()["boot_hooks"][str(mask)]
    pairs = [(c[0], c[1]) for c in got["calls"]]
    assert pairs == [
        ("donchian_swing", "recompute_held_atr"),
        ("kojiro", "recompute_held_atr"),
        ("etf_trend", "recompute_held_atr"),
        ("vcp_breakout", "recompute_high_since_buy"),
        ("bull_flag_breakout", "recompute_high_since_buy"),
    ], f"복구 훅 순서·횟수가 바뀌었다(mask={mask}): {pairs}"
    for sid, _hook, held in got["calls"]:
        assert held, f"{sid} 복구 훅이 DB 포지션 복구 전에 불렸다"


def test_c_strategy_files_equal_registered():
    """결정 C — 전략 디렉터리에 파일만 두고 등록하지 않은 전략(또는 그 반대)은 붉다."""
    from tests._strategy_census import STRATEGY_IDS

    registered = {r[0] for r in snap_registry()}
    assert set(STRATEGY_IDS) == registered, (
        f"파일 {sorted(set(STRATEGY_IDS) - registered)} 는 등록되지 않았고 "
        f"{sorted(registered - set(STRATEGY_IDS))} 는 파일이 없다 — 등록 명부에 행을 추가하라"
    )
