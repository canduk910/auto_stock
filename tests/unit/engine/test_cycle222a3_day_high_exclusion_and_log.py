"""cycle222-a3 — F-B(앵커 소유자 제외) · F-C(채택 관측성) 회귀 가드.

## F-B — LTV 앵커 채택 제외 (근거는 cycle222-a3 G-4 에서 정정됨)

`scheduler._execute_next_day_clear` 는 갭업 LTV 종목에 대해
    pos.high_since_buy = today_open        # ← max() 가 아니라 **절대 대입**
을 한다(사이클 142). 목적은 **개장 즉시 매도 방지** — 전일 상한가의 stale 고점을
그대로 두면 D+1 시가에 `drop_rate` 가 이미 임계를 넘어 개장하자마자 매도가 난다
(후성 093370, 6/15 −5.91%). 실행 시각은 **08:00:30 근방**이다
(`TIME_PRE_NXT_OPEN`=08:00 + `NEXT_DAY_STABILIZE_SECS`=30).

### ⚠️ G-4 정정 — 앞선 근거 서술 두 개가 사실과 어긋났다

(1) "LTV 앵커는 러닝 max 가 아니라 익일 시가 기준점" → **거짓**.
    `strategies/long_tail_volatility.py` 익일 트레일링 분기는 매 틱
    `pos.high_since_buy = max(pos.high_since_buy, current_price)` 로 러닝 max 를
    돌린다. 08:00:30 대입은 그 러닝 max 의 **시작점을 리셋**할 뿐이다.
(2) 절대 대입 시각이 09:00:30 → **거짓**(위 08:00:30).

### 그래서 제외의 진짜 근거 = **귀인(attribution)**

제외 이유는 사이클 142 가 깨져서가 아니다. `day_high` 는 **오늘 스코프**라
사이클 142 가 버리려던 stale **멀티데이** 고점을 되살리지 않는다. 실제로 일어나는
일은 **LTV 가 blind 내성을 얻어 놓치던 (오늘의) 고점을 보게 되고 −2% 트레일링이
더 일찍 발화**하는 것이고 — 규칙대로면 오히려 정확하다.

그럼에도 제외하는 이유는 **귀인**이다. 이번 사이클의 동기는 kojiro/donchian 의
ATR 트레일링이고 LTV 는 아니다. 근거 없이 두 전략의 청산 타이밍을 동시에 바꾸면
D+1 관측에서 무엇이 무엇을 바꿨는지 가릴 수 없다(cycle223 이 파라미터 값을
건드리지 않은 것과 같은 논리). **재검토 조건 = kojiro/donchian 의
`[day_high_adopted]` 실측이 쌓인 뒤.**

멤버십 기준 자체는 기계적이다 — "앵커에 **외부 소유자의 절대 대입**이 있는 전략".
그 커플링은 `tests/unit/ast/test_cycle222a3_ast_anchor_owner_coupling.py`(G-5)가
강제한다. 판정은 **명시 상수**로만 — `tradable_boards` 게이팅 금지(매수 전용
독트린 커플링 차단).

## F-C — 채택 경로 관측성

`[day_high_adopted]` 1회/(strategy_id, ticker)/일 INFO. 이게 없으면 D+1 에 조기
청산이 나도 원인이 day_high 채택인지 정상 트레일링인지 구분할 수 없고,
롤백 스위치 `TICK_DAY_HIGH_ANCHOR` 를 켤지 끌지 판단할 근거가 없다.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine import risk as risk_mod
from src.engine.risk import RiskManager
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategy_base import Position, Signal, StrategyBase, StrategyConfig
from src.engine.strategy_registry import StrategyRegistry

pytestmark = pytest.mark.unit

TICKER = "005180"
BUY = 75_800
_LOGGER_NAME = "src.engine.risk"


class _SpyStrategy(StrategyBase):
    async def prepare(self):
        pass

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price, ticker=None):
        return 0


@pytest.fixture
def _active(monkeypatch):
    def _set(boards):
        monkeypatch.setattr(session_tracker, "_active", frozenset(boards))
    return _set


def _rig(strategy_id: str = "kojiro", *, buy_date=None, high_since_buy: int = BUY):
    reg = StrategyRegistry()
    strat = _SpyStrategy(
        StrategyConfig(strategy_id=strategy_id, name=strategy_id, weight=0.1),
    )
    reg.register(strat)
    pos = Position(
        ticker=TICKER, buy_price=BUY, quantity=1, order_no="O-1",
        strategy_id=strategy_id,
    )
    if buy_date is not None:
        pos.buy_date = buy_date
    pos.high_since_buy = high_since_buy
    strat.state.positions[TICKER] = pos
    oe = MagicMock()
    oe._selling = set()
    oe.execute_sell = AsyncMock()
    oe.execute_buy = AsyncMock()
    return RiskManager(reg, oe), strat, pos


def _adopted_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if "[day_high_adopted]" in r.getMessage()]


def _yesterday() -> date:
    return date.today() - timedelta(days=1)


# ===========================================================================
# F-B — 앵커 소유자 제외
# ===========================================================================

def test_fb_excluded_set_is_an_explicit_frozenset_constant():
    """`_PRE_MARKET_EXIT_EVAL_STRATEGIES` 선례와 동형 — 명시 상수."""
    excluded = risk_mod._DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES
    assert isinstance(excluded, frozenset)
    assert excluded == frozenset({"long_tail_volatility"}), (
        "제외 집합이 바뀌었다 — 앵커에 **절대 대입** 하는 외부 소유자가 새로 생겼거나 "
        "사라진 것이므로 근거를 상수 주석에 남겨라"
    )


def test_fb_rationale_is_factually_corrected_and_states_the_attribution_reason():
    """**의미 전환 (cycle222-a3 G-4)** — 근거 서술이 코드·타임라인 사실과 맞아야 한다.

    ## 구 계약

    "사이클 142 / 후성 093370 / 두 번째 writer 금지" 만 있으면 통과였다. 그런데 그
    서술에는 **거짓 두 개**가 섞여 있었다 — (a) LTV 앵커가 러닝 max 가 아니라는
    주장(`long_tail_volatility.py` 가 매 틱 `max(...)` 를 돌린다) (b) 절대 대입
    시각이 09:00:30 이라는 주장(실제 08:00:30). 근거가 틀리면 다음 사람이 그 근거를
    검증하다 "제외가 불필요하다" 는 **반대 결론**에 도달할 수 있다.

    ## 새 계약

    사실관계(08:00:30 / 러닝 max)를 못박고, 제외의 결정적 근거가 **귀인**임을
    명시하며, **재검토 조건**을 남긴다. 기계적 멤버십 기준("절대 대입")과
    `tradable_boards` 금지는 그대로 유지한다.
    """
    import inspect

    src = inspect.getsource(risk_mod)
    head = src.split("_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES = ")[0]
    assert "142" in head, "사이클 142 사실관계 부재"
    assert "093370" in head, "후성 093370 실측 근거 부재"
    assert "절대 대입" in head, "절대 대입(소유자) 멤버십 기준 부재"
    assert "tradable_boards" in head, (
        "`tradable_boards` 게이팅 금지 명문화 부재 — 매수 전용 독트린 커플링 차단"
    )
    # G-4 — 사실 정정
    assert "08:00:30" in head, (
        "절대 대입 시각(08:00:30 근방 = TIME_PRE_NXT_OPEN + NEXT_DAY_STABILIZE_SECS)이 "
        "없다. 09:00:30 서술은 거짓이었다"
    )
    assert "러닝 max" in head, (
        "LTV 가 매 틱 `max(pos.high_since_buy, current_price)` 로 러닝 max 를 돌린다는 "
        "사실이 없다 — '익일 시가 기준점이라 러닝 max 가 아니다' 는 거짓이었다"
    )
    assert "09:00:30 이 아니다" in head, (
        "구 서술(09:00:30)이 **거짓임을 명시**하지 않았다 — 정정 기록이 없으면 "
        "다음 사람이 같은 오류로 되돌리고, 그 때 이 가드는 침묵한다"
    )
    # G-4 — 제외의 진짜 근거 + 해제 조건
    assert "귀인" in head, (
        "제외의 결정적 근거(귀인 — 이번 사이클 동기는 kojiro/donchian)가 없다"
    )
    assert "재검토 조건" in head, (
        "제외 해제 조건이 없다 — 근거가 사라져도 제외가 영구화된다"
    )


@pytest.mark.asyncio
async def test_fb_ltv_multiday_anchor_is_not_raised_by_day_high(_active):
    """★ 핵심 — LTV 멀티데이 보유는 `buy_date < today` 여도 채택하지 않는다."""
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig("long_tail_volatility",
                      buy_date=_yesterday(), high_since_buy=10_000)

    await rm.on_tick(TICKER, 10_200, 10_000, 2.0, day_high=10_500)

    assert pos.high_since_buy == 10_200, (
        f"LTV 앵커가 day_high 로 올라갔다 (앵커={pos.high_since_buy}) — "
        "사이클 142 의 today_open 절대 대입이 무력화된다"
    )


@pytest.mark.asyncio
async def test_fb_ltv_running_max_still_works(_active):
    """제외는 `day_high` 축만 끈다 — 현재가 러닝 max 는 그대로다."""
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig("long_tail_volatility",
                      buy_date=_yesterday(), high_since_buy=10_000)

    await rm.on_tick(TICKER, 10_800, 10_000, 8.0, day_high=11_500)

    assert pos.high_since_buy == 10_800


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_id", ["kojiro", "donchian_swing",
                                         "vcp_breakout", "bull_flag_breakout"])
async def test_fb_non_excluded_strategies_still_adopt(strategy_id, _active):
    """제외는 LTV 한정 — 나머지 전략의 blind 복구는 살아 있어야 한다.

    거부만 검증하면 "day_high 를 통째로 무시" 하는 구현도 통과하는 공허한 가드가 된다.
    """
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig(strategy_id, buy_date=_yesterday(), high_since_buy=BUY)

    await rm.on_tick(TICKER, 80_000, 76_000, 5.0, day_high=86_500)

    assert pos.high_since_buy == 86_500


def test_fb_resolver_rejects_excluded_before_any_other_check():
    """리졸버 단위 — 제외 전략은 어떤 입력에도 0."""
    rm, _, pos = _rig("long_tail_volatility", buy_date=_yesterday())
    assert rm._day_high_since_entry(
        "long_tail_volatility", TICKER, pos, 99_999, date.today(),
    ) == 0
    # 대조군: 같은 입력으로 비제외 전략은 채택된다
    assert rm._day_high_since_entry(
        "kojiro", TICKER, pos, 99_999, date.today(),
    ) == 99_999


def test_fb_gate_is_not_wired_to_tradable_boards():
    """게이팅 소스가 `tradable_boards` 가 아님을 리졸버 소스로 확인 (AST 가드 보완)."""
    import inspect

    src = inspect.getsource(RiskManager._day_high_since_entry)
    assert "_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES" in src
    assert "tradable_boards" not in src, (
        "매수 전용 설정(`tradable_boards`)이 청산 앵커 규약을 게이팅한다 — 커플링 금지"
    )


# ===========================================================================
# F-C — `[day_high_adopted]` 1회/(strategy, ticker)/일
# ===========================================================================

@pytest.mark.asyncio
async def test_fc_adoption_emits_once_per_strategy_ticker_per_day(_active, caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig("kojiro", buy_date=_yesterday())

    await rm.on_tick(TICKER, 80_000, 76_000, 5.0, day_high=86_500)
    await rm.on_tick(TICKER, 80_500, 76_000, 5.0, day_high=88_000)  # 또 올라감

    assert pos.high_since_buy == 88_000
    lines = _adopted_lines(caplog)
    assert len(lines) == 1, f"1회/(전략,종목)/일 cap 위반: {lines}"


@pytest.mark.asyncio
async def test_fc_log_carries_diagnostic_fields(_active, caplog):
    """전략 / 종목 / 이전 앵커 / 새 앵커 / 관측 고가."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    _active({MarketBoard.MAIN})
    rm, _, _pos = _rig("kojiro", buy_date=_yesterday(), high_since_buy=BUY)

    await rm.on_tick(TICKER, 80_000, 76_000, 5.0, day_high=86_500)

    (line,) = _adopted_lines(caplog)
    assert "strategy=kojiro" in line
    assert f"ticker={TICKER}" in line
    assert f"prev_anchor={BUY}" in line
    assert "new_anchor=86500" in line
    assert "observed=86500" in line


@pytest.mark.asyncio
async def test_fc_no_log_when_day_high_does_not_raise_the_anchor(_active, caplog):
    """정상 트레일링(현재가 러닝 max)과 구분돼야 한다 — 안 그러면 신호가 소음이 된다."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig("kojiro", buy_date=_yesterday(), high_since_buy=90_000)

    await rm.on_tick(TICKER, 80_000, 76_000, 5.0, day_high=86_500)

    assert pos.high_since_buy == 90_000
    assert _adopted_lines(caplog) == []


@pytest.mark.asyncio
async def test_fc_no_log_for_excluded_strategy(_active, caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    _active({MarketBoard.MAIN})
    rm, _, _pos = _rig("long_tail_volatility", buy_date=_yesterday(),
                       high_since_buy=10_000)

    await rm.on_tick(TICKER, 10_200, 10_000, 2.0, day_high=10_500)

    assert _adopted_lines(caplog) == []


@pytest.mark.asyncio
async def test_fc_reset_daily_state_clears_the_cap(_active, caplog):
    """정산 후 잔류 금지 — 익일 첫 채택이 다시 1회 emit 된다."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig("kojiro", buy_date=_yesterday())

    await rm.on_tick(TICKER, 80_000, 76_000, 5.0, day_high=86_500)
    assert len(_adopted_lines(caplog)) == 1

    rm.reset_daily_state()
    assert len(rm._day_high_adopted_logged) == 0

    pos.high_since_buy = BUY
    await rm.on_tick(TICKER, 80_000, 76_000, 5.0, day_high=86_500)
    assert len(_adopted_lines(caplog)) == 2


@pytest.mark.asyncio
async def test_fc_rollback_switch_off_silences_the_log(_active, caplog, monkeypatch):
    """`TICK_DAY_HIGH_ANCHOR=False` 면 채택도 로그도 0 — 롤백 확인 수단."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    monkeypatch.setattr(risk_mod, "TICK_DAY_HIGH_ANCHOR", False)
    _active({MarketBoard.MAIN})
    rm, _, pos = _rig("kojiro", buy_date=_yesterday())

    await rm.on_tick(TICKER, 80_000, 76_000, 5.0, day_high=86_500)

    assert pos.high_since_buy == 80_000
    assert _adopted_lines(caplog) == []


def test_fc_emit_helper_is_sync_and_db_free():
    """hot path — `logger` 만. `write_log`/DB/`await` 금지 (A-1/A-1b 동형)."""
    import ast
    import inspect

    import textwrap

    src = textwrap.dedent(inspect.getsource(RiskManager._maybe_emit_day_high_adopted))
    fn = ast.parse(src).body[0]
    assert not isinstance(fn, ast.AsyncFunctionDef)
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    # docstring 오탐 회피 — **코드 노드** 기준으로만 본다 (A-10b 선례).
    code = "\n".join(
        ast.unparse(n) for n in fn.body
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))
    )
    for banned in ("pg.fetch", "pg.execute", "write_log", "insert_", "update_high"):
        assert banned not in code, f"`{banned}` 유입 — hot path 계약 위반"
