"""cycle402 — 청산 사유 표기 시정 (cycle367 카드 4-1 (나) · 카드 4-2 (가) · ETF 설계 R4 (b)).

명세 = `_workspace/domain_consult/cycle367_exit_rules_consult.md` §4 (4.1 전수 · 4.3 소비처 · 4.4 최소 설계)
      + `_workspace/design/2026-09-27_etf_trend_strategy.md` §4.2.3 항목 4 · §10.2 R4.
사용자 승인 = 카드 4-1·4-2 09-25 저녁 「P2 나머지 모두 권고대로」 · R4 (b) 10-02 (`scheduler.py` 수정 포함).

## 무엇을 고치나

가격 손절·트레일링이 아닌 청산이 그 이름을 쓰고 있었다(09-10~09-23 스윙 매도 16건 중 6건).
`Signal` 에 이름 셋을 **덧붙이고**(기존 값 불변) 다섯 분기의 반환만 바꾼다.

| 전략 | 분기 | 전 | 후 |
|---|---|---|---|
| BFB | §3 측정된 이동 도달 | `TRAILING_STOP` | `TAKE_PROFIT` |
| BFB | §5 `max_hold_days` 초과 | `TRAILING_STOP` | `TIME_EXIT` |
| donchian | §2.5 `breakout_fail_n_days` | `STOP_LOSS` | `TIME_EXIT` |
| kojiro | §3 스테이지3 진입 | `TRAILING_STOP` | `TREND_EXIT` |
| VCP | §4 50일 EMA 이탈 | `TRAILING_STOP` | `TREND_EXIT` |

분기 조건·순서·로그 문구는 그대로다. 바뀌는 관측값은 `order_engine` 「`<신호> 매도 주문 접수`」 줄의 첫 단어다.

R4 (b) — 15:20 `_force_clear_main_only` 가 `Signal.FORCE_CLEAR` 를 하드코딩하던 자리를 전략이 고른 사유로 바꾼다.
`check_force_clear()` 의 반환 모양(`list[str]`)은 그대로 두고, 같은 전략 객체의 `force_clear_signal(ticker)`
(기본 = `FORCE_CLEAR`)를 never-raise 해석기 `resolve_force_clear_signal` 로 읽는다. VB·LTV 는 덮어쓰지 않으므로
사유는 byte 동일하게 `FORCE_CLEAR` 다(cycle398 골든 `force_clear_1520` 무변경).

## 시대 경계

배포 전 로그의 BFB·kojiro·VCP `TRAILING_STOP` 과 donchian `STOP_LOSS` 에는 위 다섯 청산이 섞여 있다.
배포 전후 로그를 신호 이름으로 합산하지 않는다.
"""
from __future__ import annotations

import ast
import datetime as _dt_mod
import logging
from datetime import date, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_KST = timezone(timedelta(hours=9))


# ═══════════════════════════════════════════════════════════════════════════
# S — Signal 열거형: 가산형
# ═══════════════════════════════════════════════════════════════════════════

def test_signal_when_cycle402_then_existing_values_unchanged():
    """기존 이름의 값은 한 글자도 바뀌지 않는다(로그 grep 이력·`!= NONE` 판정 보존)."""
    assert {m.name: m.value for m in Signal if m.name in {
        "NONE", "BUY", "STOP_LOSS", "NEXT_DAY_CLEAR", "TRAILING_STOP", "FORCE_CLEAR", "STATUS_EXIT",
    }} == {
        "NONE": "NONE", "BUY": "BUY", "STOP_LOSS": "STOP_LOSS", "NEXT_DAY_CLEAR": "NEXT_DAY_CLEAR",
        "TRAILING_STOP": "TRAILING_STOP", "FORCE_CLEAR": "FORCE_CLEAR", "STATUS_EXIT": "STATUS_EXIT",
    }


def test_signal_when_cycle402_then_three_exit_names_added_with_self_values():
    assert Signal["TIME_EXIT"].value == "TIME_EXIT"
    assert Signal["TAKE_PROFIT"].value == "TAKE_PROFIT"
    assert Signal["TREND_EXIT"].value == "TREND_EXIT"
    # 세 이름 모두 청산이다 — `risk.on_tick` 은 `!= Signal.NONE` 하나로 매도한다.
    for name in ("TIME_EXIT", "TAKE_PROFIT", "TREND_EXIT"):
        assert Signal[name] != Signal.NONE
        assert Signal[name] != Signal.BUY


def test_signal_when_cycle402_then_member_order_appends_after_existing():
    """새 이름은 끝에 덧붙인다 — 기존 순서 위에 끼워 넣지 않는다."""
    names = [m.name for m in Signal]
    assert names[:7] == [
        "NONE", "BUY", "STOP_LOSS", "NEXT_DAY_CLEAR", "TRAILING_STOP", "FORCE_CLEAR", "STATUS_EXIT",
    ]
    assert set(names[7:]) == {"TIME_EXIT", "TAKE_PROFIT", "TREND_EXIT"}


# ═══════════════════════════════════════════════════════════════════════════
# B — BFB §3 측정된 이동 · §5 시간 청산
# ═══════════════════════════════════════════════════════════════════════════

def _bfb():
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy

    s = BullFlagBreakoutStrategy(StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목 돌파", weight=0.0))
    s.config.params["breakout_retention_minutes"] = 0
    s._candidates["005930"] = {
        "pole_start": 10_000, "pole_high": 12_500, "flag_high": 12_300, "flag_low": 11_800,
        "flag_avg_volume": 200_000, "atr14": 300, "prev_close": 12_100,
    }
    return s


def test_bfb_when_measured_move_reached_then_take_profit():
    s = _bfb()
    s.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_300, quantity=10, order_no="O1",
        strategy_id="bull_flag_breakout", high_since_buy=14_800,
    )
    # 타겟 = flag_high 12_300 + 폴 폭 2_500 = 14_800
    assert s.check_exit_signal("005930", 14_800, 12_300) == Signal.TAKE_PROFIT
    assert s._partial_exit.get("005930") is True, "마킹 부수효과 보존"


def test_bfb_when_held_over_max_hold_days_then_time_exit():
    s = _bfb()
    with freeze_time("2026-05-15 14:00:00"):
        s.state.positions["005930"] = Position(
            ticker="005930", buy_price=12_000, quantity=10, order_no="O1",
            strategy_id="bull_flag_breakout", buy_date=date(2026, 5, 6), high_since_buy=12_500,
        )
        # chandelier = 12_500 − 600 = 11_900 < 12_400 · flag_low 11_800 < 12_400 → §5 만 발화
        assert s.check_exit_signal("005930", 12_400, 12_000) == Signal.TIME_EXIT


def test_bfb_when_chandelier_hit_then_still_trailing_stop():
    """샹들리에는 그대로 `TRAILING_STOP` — 이름 정정은 다섯 분기에만."""
    s = _bfb()
    s._partial_exit["005930"] = True
    s.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_300, quantity=10, order_no="O1",
        strategy_id="bull_flag_breakout", high_since_buy=15_500,
    )
    assert s.check_exit_signal("005930", 14_800, 12_300) == Signal.TRAILING_STOP


# ═══════════════════════════════════════════════════════════════════════════
# D — donchian §2.5 시간 청산
# ═══════════════════════════════════════════════════════════════════════════

def _donchian(n_days: int = 2):
    from src.engine.strategies.donchian_swing import DonchianSwingStrategy

    s = DonchianSwingStrategy(StrategyConfig(
        strategy_id="donchian_swing", name="도치안", weight=0.2,
        params={"sizing_mode": "position_ratio", "breakout_fail_n_days": n_days},
    ))
    s.state.total_investment = 100_000_000
    return s


def _donchian_arm(s, *, buy_date, buy_price=10_000, breakout_high=11_000):
    pos = Position(ticker="005930", buy_price=buy_price, quantity=10, order_no="O",
                   strategy_id="donchian_swing", buy_date=buy_date)
    pos.high_since_buy = buy_price
    s.state.positions["005930"] = pos
    s._candidates["005930"] = {"prev_close": buy_price, "atr": 0, "ema60": 0, "donchian_high": breakout_high}
    s._breakout_high["005930"] = breakout_high


# cycle405 — donchian 의 시간 청산은 틱 경로(`check_exit_signal` §2.5)에서 15:20 경로
# (`check_force_clear` + `force_clear_signal` = TIME_EXIT)로 옮겨졌다. §2.5 돌파 실패 청산은
# 없어졌다(명세 `_workspace/red/cycle405_donchian_kkangto_spec.md` §2·§3). 행위 계약은
# `tests/unit/engine/strategies/test_cycle405_donchian_kk_force_clear.py` 가 지킨다.
@freeze_time("2026-08-14 10:00:00+09:00")
def test_donchian_when_breakout_fail_n_days_then_no_tick_time_exit():
    s = _donchian(n_days=2)
    s._trading_days = {date(2026, 8, d) for d in (10, 11, 12, 13, 14)}
    _donchian_arm(s, buy_date=date(2026, 8, 10))
    # 손실 −2% · 돌파선 11_000 아래 · 보유 4영업일 ≥ 2 — 옛 §2.5 TIME_EXIT 자리. 이제 NONE
    assert s.check_exit_signal("005930", 9_800, 9_900) == Signal.NONE


def test_donchian_force_clear_signal_is_time_exit():
    assert _donchian().force_clear_signal("005930") == Signal.TIME_EXIT


@freeze_time("2026-08-14 10:00:00+09:00")
def test_donchian_when_hard_stop_then_still_stop_loss():
    s = _donchian(n_days=2)
    s._trading_days = {date(2026, 8, d) for d in (10, 11, 12, 13, 14)}
    _donchian_arm(s, buy_date=date(2026, 8, 10))
    # cycle405 — 스탬프 없음 → R = 8% → 손절선 9,200 (사유 STOP_LOSS 유지)
    assert s.check_exit_signal("005930", 9_200, 9_900) == Signal.STOP_LOSS
    assert s.check_exit_signal("005930", 9_201, 9_900) == Signal.NONE


# ═══════════════════════════════════════════════════════════════════════════
# K — kojiro §3 스테이지3 진입
# ═══════════════════════════════════════════════════════════════════════════

@freeze_time("2026-08-27 00:10:00")  # KST 08-27 09:10
def test_kojiro_when_stage3_judged_today_then_trend_exit(caplog):
    from src.engine.strategies.kojiro import KojiroStrategy

    s = KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.6, params={}))
    s.state.total_investment = 690_111
    pos = Position(ticker="111770", buy_price=86_800, quantity=1, order_no="O", strategy_id="kojiro")
    pos.high_since_buy = 86_800
    s.state.positions["111770"] = pos
    s._candidates["111770"] = {"atr": 4_736.0, "stage": 1, "prev_close": 86_800}
    s._held_stage3["111770"] = (date(2026, 8, 27), True)

    caplog.set_level(logging.INFO, logger="src.engine.strategies.kojiro")
    assert s.check_exit_signal("111770", 86_800, 86_800) == Signal.TREND_EXIT
    exits = [r.getMessage() for r in caplog.records if "[kojiro_stage3_exit]" in r.getMessage()]
    assert len(exits) == 1 and exits[0].startswith("[kojiro_stage3_exit] 111770 스테이지3 진입 (추세 종료)"), (
        "로그 문구는 그대로"
    )


# ═══════════════════════════════════════════════════════════════════════════
# V — VCP §4 50일 EMA 이탈
# ═══════════════════════════════════════════════════════════════════════════

def _vcp():
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    s = VcpBreakoutStrategy(StrategyConfig(strategy_id="vcp_breakout", name="변동성 수축 돌파", weight=0.0))
    s._candidates["005930"] = {
        "base_high": 12_000, "base_low": 10_500, "last_pullback_pct": 0.05, "atr14": 200,
        "ema50": 11_500, "ema150": 11_000, "ema200": 10_800, "prev_close": 11_900, "avg_volume_20": 300_000,
    }
    return s


def test_vcp_when_below_ema50_only_then_trend_exit():
    s = _vcp()
    s._candidates["005930"]["atr14"] = 400  # 샹들리에 = 12_000 − 800 = 11_200 < 11_450 → §3 미발화
    s.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10, order_no="O1",
        strategy_id="vcp_breakout", high_since_buy=12_000,
    )
    # 손실 −4.6% (손절 −7% 미발화) · base_low 10_500 위 · ema50 11_500 아래 → §4 만 발화
    assert s.check_exit_signal("005930", 11_450, 12_000) == Signal.TREND_EXIT


def test_vcp_when_chandelier_hit_then_still_trailing_stop():
    s = _vcp()
    s.state.positions["005930"] = Position(
        ticker="005930", buy_price=12_000, quantity=10, order_no="O1",
        strategy_id="vcp_breakout", high_since_buy=13_000,
    )
    assert s.check_exit_signal("005930", 12_550, 12_000) == Signal.TRAILING_STOP


# ═══════════════════════════════════════════════════════════════════════════
# R — 15:20 강제청산 사유 = 전략이 고른다 (R4 (b))
# ═══════════════════════════════════════════════════════════════════════════

def test_base_force_clear_signal_when_not_overridden_then_force_clear():
    from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy

    vb = VolatilityBreakoutStrategy(StrategyConfig(strategy_id="volatility_breakout", name="VB", weight=0.1))
    assert vb.force_clear_signal("005930") == Signal.FORCE_CLEAR


@pytest.mark.parametrize("sid", ["volatility_breakout", "long_tail_volatility"])
def test_current_1520_strategies_when_resolved_then_force_clear_byte_same(sid):
    """VB·LTV 는 덮어쓰지 않는다 — 사유가 `FORCE_CLEAR` 로 byte 동일."""
    from src.engine.scheduler import TradingScheduler
    from src.engine.strategy_base import resolve_force_clear_signal

    ts = TradingScheduler()
    s = ts.registry.get(sid)
    assert type(s).force_clear_signal is __import__(
        "src.engine.strategy_base", fromlist=["StrategyBase"]
    ).StrategyBase.force_clear_signal, f"{sid} 가 force_clear_signal 을 덮어쓰면 15:20 사유가 바뀐다"
    assert resolve_force_clear_signal(s, "005930") is Signal.FORCE_CLEAR


class _Stub:
    """`ret` 이 `"sig:<이름>"` 이면 호출 시점에 `Signal[<이름>]` 로 푼다(수집 단계에서 새 이름을 요구하지 않게)."""

    def __init__(self, ret=None, exc=None, missing=False):
        if not missing:
            def _f(_ticker):
                if exc is not None:
                    raise exc
                if isinstance(ret, str) and ret.startswith("sig:"):
                    return Signal[ret[4:]]
                return ret
            self.force_clear_signal = _f
        self.config = type("C", (), {"strategy_id": "stub"})()


@pytest.mark.parametrize("stub,expected", [
    (_Stub(ret="sig:TREND_EXIT"), "TREND_EXIT"),
    (_Stub(ret="sig:TIME_EXIT"), "TIME_EXIT"),
    (_Stub(ret="sig:FORCE_CLEAR"), "FORCE_CLEAR"),
])
def test_resolve_force_clear_signal_when_valid_exit_then_returned(stub, expected):
    from src.engine.strategy_base import resolve_force_clear_signal

    assert resolve_force_clear_signal(stub, "005930") is Signal[expected]


@pytest.mark.parametrize("stub", [
    _Stub(ret=Signal.NONE),           # NONE 으로 내면 매도가 「신호 없음」 으로 기록된다
    _Stub(ret=Signal.BUY),            # 매수 신호로 매도하지 않는다
    _Stub(ret="TREND_EXIT"),          # 문자열 — Signal 이 아니다
    _Stub(ret=None),
    _Stub(exc=RuntimeError("boom")),  # 예외가 15:20 루프를 끊으면 뒤 전략 청산이 사라진다
    _Stub(missing=True),
])
def test_resolve_force_clear_signal_when_invalid_then_force_clear_and_warning(stub, caplog):
    """판정 불가 = `FORCE_CLEAR` 로 판다(15:20 청산은 그대로 나간다) + WARNING."""
    from src.engine.strategy_base import resolve_force_clear_signal

    caplog.set_level(logging.DEBUG)
    assert resolve_force_clear_signal(stub, "005930") is Signal.FORCE_CLEAR
    warns = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith("[force_clear_signal_invalid] ")
    ]
    if isinstance(stub, _Stub) and not hasattr(stub, "force_clear_signal"):
        assert warns == [], "훅이 없는 객체는 기본 사유 — 경고할 일이 아니다"
    else:
        assert len(warns) == 1


@pytest.fixture
def _frozen_1520(monkeypatch):
    from src.engine import scheduler as sched_mod

    base = _dt_mod.datetime(2026, 1, 5, 15, 20, 30)

    class _Frozen(_dt_mod.datetime):
        @classmethod
        def now(cls, tz=None):
            return base if tz is None else base.replace(tzinfo=_KST).astimezone(tz)

    monkeypatch.setattr(sched_mod, "datetime", _Frozen)
    monkeypatch.setattr(sched_mod, "write_log", AsyncMock())
    return sched_mod


async def _run_force_clear(sched_mod, *, override: dict[str, Signal] | None = None):
    ts = sched_mod.TradingScheduler()
    for s in ts.registry.all():
        s.config.enabled = True
        s.state.positions["005930"] = Position(
            ticker="005930", buy_price=1000, quantity=1, order_no="O", strategy_id=s.config.strategy_id,
        )
        if hasattr(s, "check_force_clear"):
            s.check_force_clear = (lambda _s=s: list(_s.state.positions.keys()))
        if override and s.config.strategy_id in override:
            s.force_clear_signal = (lambda _t, _v=override[s.config.strategy_id]: _v)
    sells: list = []

    async def _sell(ticker, signal, sid, *a, **k):
        sells.append((ticker, signal, sid))

    ts.order_engine.execute_sell = _sell
    await ts._force_clear_main_only()
    return sells


async def test_force_clear_main_only_when_default_then_force_clear_for_vb_ltv(_frozen_1520):
    sells = await _run_force_clear(_frozen_1520)
    # cycle403 — ETF 추세(etf_trend) 도 close_at_1520 대상이고 force_clear_signal 이
    # 항상 TREND_EXIT 를 돌려준다(§12).
    assert [(t, s.name, sid) for t, s, sid in sells] == [
        ("005930", "FORCE_CLEAR", "volatility_breakout"),
        ("005930", "FORCE_CLEAR", "long_tail_volatility"),
        ("005930", "TIME_EXIT", "donchian_swing"),   # cycle405 — 15:20 시간 청산 대상
        ("005930", "TREND_EXIT", "etf_trend"),
    ]


async def test_force_clear_main_only_when_strategy_picks_reason_then_that_reason(_frozen_1520):
    """ETF 가 `TREND_EXIT` 를 돌려주는 모양(§12 이미 구현) — 전략이 고른 사유로 매도한다."""
    sells = await _run_force_clear(_frozen_1520, override={"long_tail_volatility": Signal["TREND_EXIT"]})
    assert [(s.name, sid) for _t, s, sid in sells] == [
        ("FORCE_CLEAR", "volatility_breakout"),
        ("TREND_EXIT", "long_tail_volatility"),
        ("TIME_EXIT", "donchian_swing"),   # cycle405
        ("TREND_EXIT", "etf_trend"),
    ]


async def test_force_clear_main_only_when_reason_hook_raises_then_still_sells_force_clear(_frozen_1520):
    """사유 훅 예외가 15:20 청산을 막지 않는다 — 뒤 전략까지 판다."""
    ts_sells = []

    def _boom(_t):
        raise RuntimeError("boom")

    from src.engine import scheduler as sched_mod
    ts = sched_mod.TradingScheduler()
    for s in ts.registry.all():
        s.config.enabled = True
        s.state.positions["005930"] = Position(
            ticker="005930", buy_price=1000, quantity=1, order_no="O", strategy_id=s.config.strategy_id,
        )
        if hasattr(s, "check_force_clear"):
            s.check_force_clear = (lambda _s=s: list(_s.state.positions.keys()))
    ts.registry.get("volatility_breakout").force_clear_signal = _boom

    async def _sell(ticker, signal, sid, *a, **k):
        ts_sells.append((signal.name, sid))

    ts.order_engine.execute_sell = _sell
    await ts._force_clear_main_only()
    assert ts_sells == [
        ("FORCE_CLEAR", "volatility_breakout"),
        ("FORCE_CLEAR", "long_tail_volatility"),
        ("TIME_EXIT", "donchian_swing"),   # cycle405
        ("TREND_EXIT", "etf_trend"),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# A — 구조: 하드코딩 제거 · 8영역 무접촉
# ═══════════════════════════════════════════════════════════════════════════

def _fn(path: Path, name: str) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 없음")


def test_force_clear_main_only_when_parsed_then_no_hardcoded_force_clear_signal():
    fn = _fn(_REPO / "src/engine/scheduler.py", "_force_clear_main_only")
    hard = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Attribute) and n.attr == "FORCE_CLEAR"
        and isinstance(n.value, ast.Name) and n.value.id in {"Signal", "_Signal"}
    ]
    assert hard == [], "15:20 사유를 하드코딩하지 않는다 — resolve_force_clear_signal 경유"
    calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "resolve_force_clear_signal"
    ]
    assert len(calls) == 1


def test_risk_on_tick_when_parsed_then_sells_on_any_non_none_signal():
    """8영역 무접촉의 전제 — `risk.py` 는 신호 이름을 가리지 않고 `!= Signal.NONE` 이면 판다."""
    src = (_REPO / "src/engine/risk.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    exit_names = {"STOP_LOSS", "TRAILING_STOP", "TIME_EXIT", "TAKE_PROFIT", "TREND_EXIT", "FORCE_CLEAR"}
    named = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and n.attr in exit_names
        and isinstance(n.value, ast.Name) and n.value.id == "Signal"
    ]
    assert named == [], "risk.py 가 청산 신호 이름을 분기하면 새 이름이 그 분기를 비켜 간다"
    assert "if signal != Signal.NONE:" in src


def test_order_engine_when_parsed_then_no_exit_name_branch():
    """`order_engine.py`(8영역)도 청산 신호 이름으로 분기하지 않는다 — `signal.value` 는 로그에만 쓴다."""
    tree = ast.parse((_REPO / "src/engine/order_engine.py").read_text(encoding="utf-8"))
    exit_names = {"STOP_LOSS", "TRAILING_STOP", "TIME_EXIT", "TAKE_PROFIT", "TREND_EXIT", "FORCE_CLEAR",
                  "NEXT_DAY_CLEAR", "STATUS_EXIT"}
    named = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and n.attr in exit_names
        and isinstance(n.value, ast.Name) and n.value.id == "Signal"
    ]
    assert named == [], f"order_engine.py 가 청산 신호 이름을 본다(줄 {named}) — 새 이름이 그 분기를 비켜 간다"


def test_resolve_force_clear_signal_when_hook_lookup_raises_then_force_clear(caplog):
    """훅 조회 자체가 터져도(속성 예외) 15:20 청산은 `FORCE_CLEAR` 로 나간다."""
    from src.engine.strategy_base import resolve_force_clear_signal

    class _Prop:
        config = None

        @property
        def force_clear_signal(self):
            raise RuntimeError("lookup boom")

    caplog.set_level(logging.DEBUG)
    assert resolve_force_clear_signal(_Prop(), "005930") is Signal.FORCE_CLEAR
    assert [r for r in caplog.records
            if r.levelno >= logging.WARNING and r.getMessage().startswith("[force_clear_signal_invalid] ")]
