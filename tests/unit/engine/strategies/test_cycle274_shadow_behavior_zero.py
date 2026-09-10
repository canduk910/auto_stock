"""cycle274 Red — **행위 변경 0** (VB·LTV `check_buy_signal` ↔ `risk.on_tick` ↔ `execute_buy`).

정본 = `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md`
(§5.1 평가 자리 · §6.2 신규 4키 · §9 C2·C3·C9)

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 이 사이클의 정체성

LLM 점수는 **기록만** 한다. `check_buy_signal` 반환값·`execute_buy` 인자·수량·청산이
전부 byte 동일해야 한다. `enforce` 는 **구현하지 않는다** — 어떤 값이 들어와도 `off`
로 낙하한다(C9). 이 파일이 그 계약의 런타임 증거이고, AST 증거는
`tests/unit/ast/test_cycle274_ast_llm_gate.py` 가 든다.

## Green 이 지켜야 하는 호출부 계약

`return Signal.BUY` **직전**(계좌 SOFT 게이트 → cycle262 90초 보류 → 신호 로그 →
`state.buy_signals.append` **뒤**)에서 `llm_buy_gate.observe_signal(...)` 을
**키워드 인자만**으로 부른다. 인자는 전부 **값 복사** — 전략 객체·`_targets`·
`config.params` 자체를 넘기지 않는다(§3.3, C17).

⚠️ **C2 는 호출부에 흡수기를 요구한다.** `observe_signal` 이 스스로 never-raise 여도
호출부의 `try/except` 는 그 바깥의 사고(import 실패·monkeypatch·시그니처 불일치)까지
받는다 — cycle268 `kojiro_gap_observe.absorb_call_failure` 와 같은 자리다. 자문 §5.1 의
"직전 1줄" 스케치는 그 흡수기를 세지 않은 표현이다(결과의 `spec_disagreements` 참조).

## freezegun ↔ KST

freezegun 인자는 UTC 이고 KST = UTC + 9h (KST 09:00 == UTC 00:00).
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time

from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import Signal, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

_KST_1000 = "2026-09-11 01:00:00"     # KST 2026-09-11(금) 10:00:00 — 보류창 밖
_KST_090030 = "2026-09-11 00:00:30"   # KST 09:00:30 — cycle262 보류창 안

_TICKER = "005930"
_PRDY = 70000
_OPEN = 80000
_K = 0.5
_PREV_RANGE = 1000
_OFFSET = int(_PREV_RANGE * _K)        # 500
_TARGET = _OPEN + _OFFSET              # 80,500
_PRIME_PX = 80200

_KEYS = {
    "llm_gate_mode": "shadow",
    "llm_gate_min_score": 70,
    "llm_gate_daily_call_cap": 20,
    "llm_gate_timeout_secs": 20,
}

_KINDS = ("vb", "ltv")


# ---------------------------------------------------------------------------
# 리그 (cycle262 `test_cycle262_open_entry_hold.py` 픽스처 답습)
# ---------------------------------------------------------------------------
def _cls(kind: str):
    return VolatilityBreakoutStrategy if kind == "vb" else LongTailVolatilityStrategy


def _module(kind: str):
    from src.engine.strategies import long_tail_volatility as ltv_mod
    from src.engine.strategies import volatility_breakout as vb_mod
    return vb_mod if kind == "vb" else ltv_mod


def _gate_of(kind: str):
    """전략 모듈이 물고 있는 `llm_buy_gate` — 부재면 **실패**(Red)."""
    mod = _module(kind)
    assert hasattr(mod, "llm_buy_gate"), (
        f"{mod.__name__} 에 `llm_buy_gate` import 가 없다 — 자문 §5.1 diff (1) 미배선"
    )
    return mod.llm_buy_gate


def _seed_target(strategy, ticker: str) -> None:
    strategy._targets[ticker] = {
        "k": _K,
        "prev_range": _PREV_RANGE,
        "target_offset_base": _OFFSET,
        "target_offset": _OFFSET,
        "target_price": 0,
        "open_price": 0,
        "boards": {},
    }
    strategy._open_confirmed[ticker] = {}


def _armed(kind: str, monkeypatch, *, params: dict | None = None, ticker: str = _TICKER):
    """돌파 1틱이면 BUY 가 나오는 최소 rig."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {ticker: "삼성전자"})
    monkeypatch.setattr(scanner, "ticker_prev_close", {ticker: _PRDY})
    monkeypatch.setattr(scanner, "ticker_prices", {})

    s = _cls(kind)(StrategyConfig(
        strategy_id="volatility_breakout" if kind == "vb" else "long_tail_volatility",
        name="변동성 돌파" if kind == "vb" else "롱테일 변동성",
        weight=0.3,
    ))
    if params:
        s.config.params.update(params)
    s.state.total_investment = 100_000_000
    _seed_target(s, ticker)
    # cycle272 — `main` 확정은 `source="rest"` 없이는 거부된다(기본 enforce).
    s.on_open_price_confirmed(ticker, open_price=_OPEN, board="main", source="rest")
    session_tracker._active = frozenset({MarketBoard.MAIN})
    return s


def _prime(s, ticker: str = _TICKER) -> Signal:
    return s.check_buy_signal(ticker, _PRIME_PX, _OPEN)


def _breakout(s, ticker: str = _TICKER, px: int = _TARGET) -> Signal:
    return s.check_buy_signal(ticker, px, _OPEN)


class _Spy:
    """`observe_signal` 스파이 — 호출 kwargs 를 그대로 보관."""

    def __init__(self, exc: BaseException | None = None) -> None:
        self.calls: list[dict] = []
        self.exc = exc

    def __call__(self, **kw):
        self.calls.append(kw)
        if self.exc is not None:
            raise self.exc
        return None


def _install(kind: str, monkeypatch, spy: _Spy) -> None:
    monkeypatch.setattr(_gate_of(kind), "observe_signal", spy)


# ===========================================================================
# 신규 4키 (§6.2)
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("key,value", sorted(_KEYS.items()))
def test_w1_1_default_params_has_four_keys(kind: str, key: str, value) -> None:
    """C9·C10 전제/§6.2 — 신규 4키가 VB·LTV `DEFAULT_PARAMS` 에 명시 기본값으로 존재한다.

    `_load_strategy_config`/`PUT /params` 는 **`if key in params` 오버레이**라
    `DEFAULT_PARAMS` 에 없는 키는 DB 에서 조용히 버려진다 = 배포 전 DB 선반영은
    무음 실패다(cycle245 실측 함정). 그래서 **소스가 키의 정본**이다.
    """
    params = _cls(kind).DEFAULT_PARAMS
    assert key in params, f"{_cls(kind).__name__}.DEFAULT_PARAMS 에 `{key}` 부재"
    assert params[key] == value, f"`{key}` 기본값 {params[key]!r} != {value!r}"


@pytest.mark.parametrize("kind", _KINDS)
def test_w1_2_keys_survive_merge(monkeypatch, kind: str) -> None:
    """C9 전제/§6.2 — `__init__` 머지(`{**DEFAULT_PARAMS, **config.params}`) 후에도 런타임 존재."""
    s = _armed(kind, monkeypatch)
    for key, value in _KEYS.items():
        assert s.config.params.get(key) == value


@pytest.mark.parametrize("kind", _KINDS)
def test_w1_3_mode_default_is_shadow_not_enforce(kind: str) -> None:
    """C9/§6.2 — 기본 모드는 `shadow` 다. `enforce` 가 기본이면 그 자체가 무허가 행위 변경이다."""
    assert _cls(kind).DEFAULT_PARAMS["llm_gate_mode"] == "shadow"


# ===========================================================================
# 배선 — 발사점에서 정확히 1회 호출 (§5.1)
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
def test_w1_4_observe_called_once_on_breakout(monkeypatch, kind: str) -> None:
    """C1 런타임 짝/§5.1 — 돌파 발사점에서 `observe_signal` 이 **정확히 1회** 불린다.

    이 자리(계좌 SOFT 게이트 → cycle262 보류 → 신호 로그 → `buy_signals` append 뒤,
    `return Signal.BUY` 앞)여야 **shadow 표본 = enforce 표본**이 된다 — 다른 게이트를
    전부 통과한 신호만 평가하므로 2주 뒤 판정이 그대로 enforce 예측이 된다.
    """
    spy = _Spy()
    _install(kind, monkeypatch, spy)
    s = _armed(kind, monkeypatch)
    assert _prime(s) == Signal.NONE
    assert len(spy.calls) == 0, "baseline 틱에서 평가가 나갔다(신호가 아닌데 돈을 쓴다)"
    assert _breakout(s) == Signal.BUY
    assert len(spy.calls) == 1


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
def test_w1_5_observe_not_called_without_breakout(monkeypatch, kind: str) -> None:
    """C1 런타임 짝/§5.1 — 돌파가 아니면 호출 0건(목표가 아래 틱은 신호가 아니다)."""
    spy = _Spy()
    _install(kind, monkeypatch, spy)
    s = _armed(kind, monkeypatch)
    _prime(s)
    assert s.check_buy_signal(_TICKER, _TARGET - 1, _OPEN) == Signal.NONE
    assert spy.calls == []


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_090030)
def test_w1_6_observe_not_called_while_open_entry_hold(monkeypatch, kind: str) -> None:
    """C1 런타임 짝/§5.1 — cycle262 보류(09:00~09:01:30)로 막힌 신호는 **평가하지 않는다**.

    보류된 신호는 매수가 아니므로 shadow 표본에 들어가면 안 된다(표본 오염 +
    쓸 데 없는 비용). cycle262 게이트가 `observe_signal` **앞**이라는 순서 계약.
    """
    spy = _Spy()
    _install(kind, monkeypatch, spy)
    s = _armed(kind, monkeypatch, params={"open_entry_hold_secs": 90})
    _prime(s)
    assert _breakout(s) == Signal.NONE
    assert spy.calls == []


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
def test_w1_7_observe_receives_value_copies_only(monkeypatch, kind: str) -> None:
    """C17/§3.3 — 넘기는 것은 **값 복사**다. 전략 객체·`_targets`·`config.params` 금지.

    `create_task` 에 전략 객체를 넘기면 task 실행 시점에 `_targets` 가 이미 바뀌어
    있을 수 있다(재-prepare). 그리고 `config.params` 를 그대로 넘기면 leaf 가
    (실수로라도) 전략 파라미터를 오염시킬 수 있는 경로가 열린다.
    """
    spy = _Spy()
    _install(kind, monkeypatch, spy)
    s = _armed(kind, monkeypatch)
    _prime(s)
    _breakout(s)

    kw = spy.calls[0]
    assert kw, "키워드 인자로 호출되지 않았다(위치 인자는 순서 결함에 취약하다)"
    for value in kw.values():
        assert value is not s, "전략 객체 자체를 넘겼다"
        assert value is not s._targets, "`_targets` 참조를 넘겼다"
        assert value is not s.config.params, "`config.params` 참조를 넘겼다(오염 경로)"
    snap = kw["params_snapshot"]
    assert isinstance(snap, dict) and snap is not s.config.params
    for key in _KEYS:
        assert key in snap, f"params_snapshot 에 `{key}` 누락 — 모드 판정 불가"


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
def test_w1_8_observe_payload_fields(monkeypatch, kind: str) -> None:
    """C17 전제/§3.3 B군 — 신호 시점 스냅샷의 핵심 필드가 실제 값으로 넘어간다."""
    spy = _Spy()
    _install(kind, monkeypatch, spy)
    s = _armed(kind, monkeypatch)
    _prime(s)
    _breakout(s)

    kw = spy.calls[0]
    assert kw["strategy_id"] == s.strategy_id
    assert kw["ticker"] == _TICKER
    assert kw["board"] == "main"
    assert kw["price_won"] == _TARGET
    assert kw["board_open_won"] == _OPEN
    assert kw["target_won"] == _TARGET
    assert kw["target_offset_won"] == _OFFSET
    assert kw["prev_price_won"] == _PRIME_PX
    assert kw["prdy_close_won"] == _PRDY
    assert float(kw["k"]) == pytest.approx(_K)
    assert kw["now_kst"].tzinfo is not None, "`now_kst` 는 tz-aware 여야 한다(KST 강제)"


# ===========================================================================
# C2 — 관측이 터져도 반환값 동일 (HIGH)
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize(
    "exc",
    [RuntimeError("boom"), TypeError("signature"), ValueError("x"), OverflowError("inf")],
    ids=["runtime", "type", "value", "overflow"],
)
@freeze_time(_KST_1000)
def test_c2_1_observe_exception_does_not_change_signal(monkeypatch, kind: str, exc) -> None:
    """C2 (HIGH) — `observe_signal` 이 무엇을 던져도 반환은 `Signal.BUY` 다.

    관측 예외가 `check_buy_signal` 을 뚫으면 `risk.on_tick` 은 전략별 try 가 없어
    그 종목의 나머지 평가를 통째로 잃고, `handler.py` 가 re-raise 해 **WS 재연결
    루프**가 된다(cycle237 TE-2 · cycle262 C10 과 같은 계열).
    """
    _install(kind, monkeypatch, _Spy(exc=exc))
    s = _armed(kind, monkeypatch)
    assert _prime(s) == Signal.NONE
    assert _breakout(s) == Signal.BUY


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
def test_c2_2_observe_exception_preserves_buy_signals_entry(monkeypatch, kind: str) -> None:
    """C2 — 관측이 터져도 `state.buy_signals` 항목이 정상 형태로 남는다(대시보드 무영향)."""
    _install(kind, monkeypatch, _Spy(exc=RuntimeError("boom")))
    s = _armed(kind, monkeypatch)
    _prime(s)
    _breakout(s)
    assert len(s.state.buy_signals) == 1
    entry = s.state.buy_signals[0]
    assert entry["ticker"] == _TICKER
    assert entry["price"] == _TARGET
    assert entry["target_price"] == _TARGET
    assert entry["board"] == "main"


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
def test_c2_3_observe_exception_leaves_a_trace(monkeypatch, kind: str, caplog) -> None:
    """C2/cycle258 카드 #5 — 호출부 흡수기는 **무흔적 `pass` 가 아니다**.

    관측기가 죽어도 아무도 모르면 이 마커의 **결측이 '신호가 없었다' 로 오독된다**
    (cycle268 §1 판독 표가 막으려던 바로 그것).
    """
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger=_module(kind).__name__)
    caplog.set_level(logging.DEBUG, logger="src.engine.observer_trace")
    _install(kind, monkeypatch, _Spy(exc=RuntimeError("boom")))
    s = _armed(kind, monkeypatch)
    _prime(s)
    _breakout(s)
    assert any("observer_failed" in r.getMessage() for r in caplog.records), (
        "관측 호출 실패의 흔적이 남지 않았다(무흔적 pass 금지). 흔적 경로는 강제하지 "
        "않는다 — 호출부가 `trace_observer_failure(..., dest_logger=logger)` 를 쓰든 "
        "leaf 의 흡수기를 타든 어느 쪽이든 `observer_failed` 한 줄은 남아야 한다."
    )


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
def test_c2_4_observe_exception_does_not_block_next_ticks(monkeypatch, kind: str) -> None:
    """C2 — 한 번 터진 뒤에도 다음 틱 평가가 계속된다(관측 사망이 매매를 마비시키지 않는다)."""
    _install(kind, monkeypatch, _Spy(exc=RuntimeError("boom")))
    s = _armed(kind, monkeypatch)
    _prime(s)
    _breakout(s)
    assert s.check_buy_signal(_TICKER, _TARGET + 100, _OPEN) == Signal.NONE  # 이미 돌파 후


# ===========================================================================
# C9 (전략 측) — 모드가 무엇이든 반환값은 종전 그대로
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize(
    "mode", ["shadow", "off", "enforce", "ENFORCE", "", None, 123, "shadow "],
    ids=["shadow", "off", "enforce", "ENFORCE", "empty", "none", "int", "trailing-space"],
)
@freeze_time(_KST_1000)
def test_c9_1_signal_is_identical_for_every_mode(monkeypatch, kind: str, mode) -> None:
    """C9 (HIGH) — `llm_gate_mode` 가 무엇이든 `check_buy_signal` 은 `Signal.BUY` 다.

    `enforce` 는 이 사이클에 **구현되지 않았다.** 미구현 모드를 DB 에 넣었을 때
    반환값이 달라지면 그것이 곧 무허가 행위 변경이다.
    """
    _install(kind, monkeypatch, _Spy())
    s = _armed(kind, monkeypatch, params={"llm_gate_mode": mode})
    assert _prime(s) == Signal.NONE
    assert _breakout(s) == Signal.BUY


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
def test_c9_2_observe_is_called_even_in_off_mode(monkeypatch, kind: str) -> None:
    """C9 — 모드 판정은 **leaf 의 책임**이다(전략은 항상 부르고 leaf 가 즉시 return).

    전략 파일에 mode 분기를 두면 `check_buy_signal` 안에 새 `if` 가 생겨 C1 의
    "반환값이 점수와 무관" 기계 증명이 흐려지고, `[llm_gate_config]` 롤백 카나리아도
    off 에서 사라진다.
    """
    spy = _Spy()
    _install(kind, monkeypatch, spy)
    s = _armed(kind, monkeypatch, params={"llm_gate_mode": "off"})
    _prime(s)
    _breakout(s)
    assert len(spy.calls) == 1
    assert spy.calls[0]["params_snapshot"]["llm_gate_mode"] == "off"


# ===========================================================================
# C3 — `risk.on_tick` → `execute_buy` 인자 동일 튜플 (HIGH)
# ===========================================================================
def _rig(kind: str, monkeypatch, *, mode):
    registry = StrategyRegistry()
    s = _armed(kind, monkeypatch, params={"llm_gate_mode": mode})
    registry.register(s)

    order_engine = MagicMock()
    order_engine.execute_buy = AsyncMock()
    order_engine.execute_sell = AsyncMock()
    order_engine._selling = set()

    from src.engine.risk import RiskManager
    return s, order_engine, RiskManager(registry, order_engine)


async def _run_on_tick(risk) -> None:
    await risk.on_tick(_TICKER, current_price=_PRIME_PX, open_price=_OPEN, change_rate=14.5)
    await risk.on_tick(_TICKER, current_price=_TARGET, open_price=_OPEN, change_rate=15.0)


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
async def test_c3_1_execute_buy_args_identical_off_vs_shadow(monkeypatch, kind: str) -> None:
    """C3 (HIGH) — 게이트 off/shadow 에서 `execute_buy` 인자 튜플이 **동일**하다.

    `execute_buy(ticker, current_price, strategy)` — 종목·가격·전략 셋 다 같아야
    한다. 하나라도 다르면 shadow 가 매매를 건드린 것이다.
    """
    _install(kind, monkeypatch, _Spy())
    seen = []
    for mode in ("off", "shadow"):
        s, oe, risk = _rig(kind, monkeypatch, mode=mode)
        await _run_on_tick(risk)
        assert oe.execute_buy.await_count == 1, f"mode={mode} 에서 매수 호출 수가 1이 아니다"
        args, kwargs = oe.execute_buy.await_args
        seen.append((args[0], args[1], args[2].strategy_id, tuple(sorted(kwargs))))
    assert seen[0] == seen[1], f"게이트가 매수 인자를 바꿨다: {seen}"


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
async def test_c3_2_execute_buy_args_identical_when_observe_explodes(monkeypatch, kind: str) -> None:
    """C3 — 관측이 터지는 상황에서도 `execute_buy` 인자가 동일하다."""
    seen = []
    for spy in (_Spy(), _Spy(exc=RuntimeError("boom"))):
        _install(kind, monkeypatch, spy)
        s, oe, risk = _rig(kind, monkeypatch, mode="shadow")
        await _run_on_tick(risk)
        assert oe.execute_buy.await_count == 1
        args, _kw = oe.execute_buy.await_args
        seen.append((args[0], args[1], args[2].strategy_id))
    assert seen[0] == seen[1]


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
async def test_c3_3_signal_count_today_unchanged(monkeypatch, kind: str) -> None:
    """C3 — `state.signal_count_today` 증가도 동일하다(대시보드 카운터 무영향)."""
    counts = []
    for mode in ("off", "shadow"):
        _install(kind, monkeypatch, _Spy())
        s, _oe, risk = _rig(kind, monkeypatch, mode=mode)
        await _run_on_tick(risk)
        counts.append(s.state.signal_count_today)
    assert counts[0] == counts[1] == 1


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
async def test_c3_4_calc_buy_quantity_identical(monkeypatch, kind: str) -> None:
    """C3 — 수량 산출도 게이트 on/off 에서 동일하다(사이징 무접촉).

    `calc_buy_quantity` 는 sha 핀 4개 중 둘로도 동결되지만(C18), 런타임에서도
    같은 값을 내는지 한 번 더 본다 — 핀은 소스를, 이 테스트는 결과를 잰다.
    """
    qtys = []
    for mode in ("off", "shadow"):
        _install(kind, monkeypatch, _Spy())
        s = _armed(kind, monkeypatch, params={"llm_gate_mode": mode})
        qtys.append(s.calc_buy_quantity(_TARGET, ticker=_TICKER))
    assert qtys[0] == qtys[1]


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
async def test_c3_5_no_buy_when_no_breakout_regardless_of_gate(monkeypatch, kind: str) -> None:
    """C3 — 돌파가 없으면 어느 모드에서도 매수 0건(게이트가 매수를 **만들지** 않는다)."""
    for mode in ("off", "shadow"):
        _install(kind, monkeypatch, _Spy())
        _s, oe, risk = _rig(kind, monkeypatch, mode=mode)
        await risk.on_tick(_TICKER, current_price=_PRIME_PX, open_price=_OPEN, change_rate=14.5)
        await risk.on_tick(_TICKER, current_price=_TARGET - 1, open_price=_OPEN, change_rate=14.9)
        assert oe.execute_buy.await_count == 0
