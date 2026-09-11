"""cycle274 Red — **행위 변경 0** (VB·LTV `check_buy_signal` ↔ `risk.on_tick` ↔ `execute_buy`).

정본 = `_workspace/domain_consult/cycle274_llm_buy_gate_20260910.md`
(§5.1 평가 자리 · §6.2 신규 4키 · §9 C2·C3·C9)

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 이 사이클의 정체성

LLM 점수는 **기록만** 한다. `check_buy_signal` 반환값·`execute_buy` 인자·수량·청산이
전부 byte 동일해야 한다. `enforce` 는 **구현하지 않는다** — 어떤 값이 들어와도 `off`
로 낙하한다(C9). 이 파일이 그 계약의 런타임 증거이고, AST 증거는
`tests/unit/ast/test_cycle274_ast_llm_gate.py` 가 든다.

## 🔁 2026-09-11 cycle276 승계 — 전략에서 배선이 **사라졌다**

관측 훅이 `check_buy_signal` 에서 `order_engine.execute_buy`(주문 접수 직후)로 옮겨졌다.
그래서 이 파일의 "발사점 배선"(w1_4~w1_8)과 "호출부 흡수기"(c2_1~c2_4) 케이스는 **삭제**
했다 — 그 계약은 이제 `tests/unit/engine/test_cycle276_order_time_hook.py`(런타임)와
`tests/unit/ast/test_cycle276_ast_order_hook.py`(구조)가 든다. 고아 가드를 남기지 않는다
(cycle240 A11b · cycle252 G-252-5b).

**남긴 것**은 cycle276 이후에도 유효한 계약뿐이다:
- `DEFAULT_PARAMS` 4키 존재·기본값·머지 생존(w1_1~w1_3) — 이 4키는 여전히 VB·LTV 의
  설정 표면이자 킬스위치다(`order_engine` 이 `strategy.config.params` 로 읽는다).
- `llm_gate_mode` 값이 무엇이든 매매 행위가 동일하다(c9_1·c3_1~c3_5) — 이제 전략은 그
  키를 **읽지도 않으므로** 더 강한 형태로 참이며, 누군가 전략에 mode 분기를 되살리면
  이 케이스들이 잡는다.
- 전략 모듈이 leaf 를 참조하지 않는다(w0_1, 신설).

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


def _assert_no_leaf_reference(kind: str) -> None:
    """🔁 cycle276 — 전략 모듈은 leaf 를 **모른다**(배선이 order_engine 으로 옮겨졌다).

    이름이 남아 있으면 전략에 죽은 배선이 있다는 뜻이고, 그 죽은 배선은 언젠가 다시
    호출된다.
    """
    mod = _module(kind)
    assert not hasattr(mod, "llm_buy_gate"), (
        f"{mod.__name__} 에 `llm_buy_gate` 참조가 남아 있다 — cycle276 원상 복구 미완"
    )


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
# 🔁 cycle276 — 전략에는 배선이 없다
# ===========================================================================
@pytest.mark.parametrize("kind", _KINDS)
def test_w0_1_strategy_module_does_not_reference_the_leaf(kind: str) -> None:
    """C12 런타임 짝 — VB·LTV 모듈에 `llm_buy_gate` 이름이 없다.

    cycle274 는 `check_buy_signal` 의 `return Signal.BUY` 직전에서 leaf 를 불렀다.
    cycle276 이 그 훅을 `order_engine.execute_buy`(주문 접수 직후)로 옮겼으므로
    전략 쪽 참조는 **전부** 사라져야 한다 — 남으면 죽은 배선이다.
    """
    _assert_no_leaf_reference(kind)


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
    s = _armed(kind, monkeypatch, params={"llm_gate_mode": mode})
    assert _prime(s) == Signal.NONE
    assert _breakout(s) == Signal.BUY


# 🔁 cycle276 — `test_c9_2_observe_is_called_even_in_off_mode` 는 **삭제**했다.
#    "전략은 항상 부르고 mode 판정은 leaf 가 한다" 는 계약의 자리가 order_engine 으로
#    옮겨졌다. 그 계약(off 에서도 `[llm_gate_config]` 카나리아 1행)은 이제
#    `test_cycle276_order_time_hook.py::test_c19_2_mode_off_still_emits_config_canary` 가 든다.


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
async def test_c3_2_execute_buy_args_identical_across_repeat_runs(monkeypatch, kind: str) -> None:
    """C3 — 같은 입력을 두 번 태워도 `execute_buy` 인자가 동일하다(결정성 회귀).

    🔁 cycle276 — 종전에는 "관측기가 터져도 동일" 을 쟀다. 관측기가 전략에서
    사라졌으므로 그 계약은 `test_cycle276_order_time_hook.py::test_c3_2/_c3_4`
    (훅이 던져도 `execute_buy` 결과 동일)로 옮겨졌다.
    """
    seen = []
    for _ in range(2):
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
        s = _armed(kind, monkeypatch, params={"llm_gate_mode": mode})
        qtys.append(s.calc_buy_quantity(_TARGET, ticker=_TICKER))
    assert qtys[0] == qtys[1]


@pytest.mark.parametrize("kind", _KINDS)
@freeze_time(_KST_1000)
async def test_c3_5_no_buy_when_no_breakout_regardless_of_gate(monkeypatch, kind: str) -> None:
    """C3 — 돌파가 없으면 어느 모드에서도 매수 0건(게이트가 매수를 **만들지** 않는다)."""
    for mode in ("off", "shadow"):
        _s, oe, risk = _rig(kind, monkeypatch, mode=mode)
        await risk.on_tick(_TICKER, current_price=_PRIME_PX, open_price=_OPEN, change_rate=14.5)
        await risk.on_tick(_TICKER, current_price=_TARGET - 1, open_price=_OPEN, change_rate=14.9)
        assert oe.execute_buy.await_count == 0
