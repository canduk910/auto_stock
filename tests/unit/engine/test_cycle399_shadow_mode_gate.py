"""cycle399 Red — 공통 섀도 모드 `shadow_mode`: 신호 단계 관문 · 마커 · 상태 무접촉 · 청산 무접촉 (t01~t11).

명세 정본 = `_workspace/red/cycle399_shadow_mode.md` §1 · §3
근거 = `_workspace/domain_consult/cycle398_refactor_cards_2_3.md` §3(c) — 섀도는 「실전과 똑같이 판단한 뒤
방아쇠만 뺀다」. 막는 자리는 **신호 계산 뒤**(앞에서 막으면 「사려 했던 것」 이 남지 않는다).

합성 입력은 cycle384 의 `Buyable`(「멈추지 않으면 이번 평가가 BUY」)을 그대로 쓴다 — 양성 대조가
같은 입력에서 BUY 를 보이므로 섀도 단언이 공허하지 않다.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.engine.strategy_base import Position, Signal
from tests import _strategy_census as census
from tests.unit.engine._cycle384_support import (
    ALL7,
    DAY,
    NEXT_DAY,
    SB_LOGGER,
    T,
    U,
    Clock,
    field,
    kst,
    lines,
    open_info,
    ready,
    strategy_class,
)

pytestmark = pytest.mark.unit

KEY = "shadow_mode"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, caplog):
    from src.engine import scanner, tick_volume

    tick_volume.reset_for_test()
    monkeypatch.setattr(scanner, "ticker_prev_close", {}, raising=False)
    monkeypatch.setattr(scanner, "ticker_prices", {}, raising=False)
    try:
        from src.engine import account_risk_watcher

        account_risk_watcher.reset_state_for_test()
    except Exception:
        pass
    open_info(caplog)
    yield
    tick_volume.reset_for_test()


def shadow(s, value=True) -> None:
    """PUT 과 같은 경로 — 같은 ``config.params`` dict 를 고친다."""
    s.config.params[KEY] = value


def _buy_lines(caplog, sid: str | None = None) -> list[str]:
    out = lines(caplog, "[shadow_buy]")
    return [ln for ln in out if sid is None or field(ln, "strategy") == sid]


def _cfg_lines(caplog, sid: str | None = None, *, min_level: int = logging.INFO) -> list[str]:
    out = lines(caplog, "[shadow_mode_config]", min_level=min_level)
    return [ln for ln in out if sid is None or field(ln, "strategy") == sid]


def test_t00_behaviour_matrix_covers_the_census():
    """행위 표본(ALL7)이 전략 명부와 같다 — 여덟째 전략이 생기면 여기서 붉고 `Buyable` 에 입력을 더한다."""
    assert set(ALL7) == set(census.STRATEGY_IDS), (
        f"전략 명부 {census.STRATEGY_IDS} ≠ 행위 표본 {ALL7} — tests/unit/engine/_cycle384_support.py "
        "Buyable 에 새 전략의 「사는 순간」 입력을 더하라"
    )


# ===========================================================================
# t01 — 기본값
# ===========================================================================
@pytest.mark.parametrize("sid", ALL7)
def test_t01_default_params_has_shadow_mode_false(sid):
    d = strategy_class(sid).DEFAULT_PARAMS
    assert KEY in d, f"[Red] {sid} DEFAULT_PARAMS 에 shadow_mode 없음 — PUT 이 unknown_key 422 가 된다"
    assert d[KEY] is False, f"{sid} 기본값이 False(bool) 가 아니다: {d[KEY]!r}"


# ===========================================================================
# t02 — 섀도면 BUY 대신 NONE (양성 대조 동반)
# ===========================================================================
@pytest.mark.parametrize("sid", ALL7)
def test_t02_positive_control_shadow_off_buys(sid, monkeypatch, caplog):
    r = ready(sid, monkeypatch)
    shadow(r.s, False)
    r.prime()
    assert r.fire() == Signal.BUY, f"{sid}: 합성 입력이 BUY 를 못 낸다 — 섀도 단언이 공허해진다"
    assert _buy_lines(caplog) == [], "섀도가 꺼졌는데 [shadow_buy] 가 찍혔다"
    assert _cfg_lines(caplog) == [], "꺼짐(False)은 무음이어야 한다"


@pytest.mark.parametrize("sid", ALL7)
def test_t02_shadow_on_turns_buy_into_none(sid, monkeypatch):
    r = ready(sid, monkeypatch)
    shadow(r.s)
    r.prime()
    assert r.fire() == Signal.NONE, f"[Red] {sid}: shadow_mode=True 인데 BUY — 주문이 나간다"


# ===========================================================================
# t03 · t04 — [shadow_buy] 마커: 종목당 하루 1회, 다음 날 다시
# ===========================================================================
@pytest.mark.parametrize("sid", ALL7)
def test_t03_shadow_buy_marker_once_per_ticker_per_day(sid, monkeypatch, caplog):
    r = ready(sid, monkeypatch)
    shadow(r.s)
    r.prime()
    assert r.fire() == Signal.NONE
    got = _buy_lines(caplog, sid)
    assert len(got) == 1, f"[Red] {sid}: [shadow_buy] {len(got)}줄 — 1줄이어야 한다: {got}"
    ln = got[0]
    assert field(ln, "ticker") == T
    assert field(ln, "price") == str(r.fire_px)
    # BFB·VCP 는 BUY 가 거래량 게이트 헬퍼(`_evaluate_vol_gate`) 안에서 나고 그 헬퍼는 시가를 받지 않는다 — '-'
    want_open = "-" if sid in ("bull_flag_breakout", "vcp_breakout") else str(r.open)
    assert field(ln, "open") == want_open
    if r.level is not None:
        assert field(ln, "level") == str(r.level), f"{sid}: 돌파선/목표가가 오프라인 재현에 필요하다"
    for k in ("atr", "m", "mu_state", "board"):
        field(ln, k)                                   # 칸 존재(값 없으면 '-')
    recs = [x for x in caplog.records if x.getMessage().startswith("[shadow_buy] ")]
    assert all(x.levelno == logging.INFO and x.name == SB_LOGGER for x in recs)
    # 같은 날 같은 종목 — 다시 BUY 판정에 닿아도 NONE, 마커는 더 없다
    for _ in range(5):
        r.prime()
        assert r.fire() == Signal.NONE
    assert len(_buy_lines(caplog, sid)) == 1, "같은 날 같은 종목 [shadow_buy] 가 반복됐다"


def test_t04_next_kst_day_records_again(monkeypatch, caplog):
    clock = Clock(kst(9, 10))
    r = ready("donchian_swing", monkeypatch, clock)
    shadow(r.s)
    assert r.fire() == Signal.NONE
    clock.set(9, 10, day=NEXT_DAY)
    assert r.fire() == Signal.NONE
    assert len(_buy_lines(caplog, "donchian_swing")) == 2, "다음 KST 날짜에 다시 기록돼야 한다"


def test_t04_other_ticker_same_day_is_recorded(monkeypatch, caplog):
    r = ready("donchian_swing", monkeypatch)
    shadow(r.s)
    r.s._candidates[U] = dict(r.s._candidates[T])
    assert r.fire() == Signal.NONE
    assert r.s.check_buy_signal(U, 10_600, 10_100) == Signal.NONE
    assert [field(x, "ticker") for x in _buy_lines(caplog)] == [T, U]


# ===========================================================================
# t05 — 섀도 BUY 는 전략 상태를 바꾸지 않는다(화면·진입 스탬프·래치·주문 축)
# ===========================================================================
_STAMPS = ("_breakout_high", "_position_setup", "_position_atr", "_position_sectors")


@pytest.mark.parametrize("sid", ALL7)
def test_t05_shadow_buy_leaves_no_buy_state(sid, monkeypatch):
    r = ready(sid, monkeypatch)
    shadow(r.s)
    r.prime()
    bought = set(getattr(r.s, "_bought_today", set()))
    latch = repr(getattr(r.s, "_vol_latch", None))
    sigs = list(r.s.state.buy_signals)
    assert r.fire() == Signal.NONE
    assert r.s.state.buy_signals == sigs, f"{sid}: 섀도 신호가 화면 buy_signals 에 실전처럼 올라갔다"
    assert set(getattr(r.s, "_bought_today", set())) == bought, f"{sid}: 섀도가 _bought_today 를 찍었다"
    for name in _STAMPS:
        d = getattr(r.s, name, None)
        if isinstance(d, dict):
            assert T not in d, f"{sid}: 섀도가 진입 스탬프 {name} 를 남겼다 — 보유가 없는데 청산 상태가 생긴다"
    assert repr(getattr(r.s, "_vol_latch", None)) == latch, f"{sid}: 섀도가 진입 래치를 건드렸다"
    assert not r.s.state.pending_buys and not r.s.state.pending_buy_amounts
    assert r.s.state.signal_count_today == 0
    assert r.s.state.buy_disabled is False


# ===========================================================================
# t06 — 앞 관문이 이기면 섀도 기록도 없다 (순서 = 상태 → 멈춤 → SOFT → 신호 → 시장 유닛 → 섀도)
# ===========================================================================
@pytest.mark.parametrize("sid", ALL7)
def test_t06_buy_paused_wins_no_shadow_record(sid, monkeypatch, caplog):
    r = ready(sid, monkeypatch)
    shadow(r.s)
    r.s.config.params["buy_paused"] = True
    r.prime()
    assert r.fire() == Signal.NONE
    assert _buy_lines(caplog) == [], f"{sid}: 멈춘 전략에서 [shadow_buy] — 멈춤이 섀도보다 앞이어야 한다"


@pytest.mark.parametrize("sid", ["donchian_swing", "kojiro", "bull_flag_breakout", "vcp_breakout"])
def test_t06_market_unit_filter_wins_no_shadow_record(sid, monkeypatch, caplog):
    r = ready(sid, monkeypatch)
    shadow(r.s)
    monkeypatch.setattr(r.s, "_market_unit_blocks_entry", lambda ticker, price: True)
    r.prime()
    assert r.fire() == Signal.NONE
    assert _buy_lines(caplog) == [], f"{sid}: 시장 유닛이 거른 종목이 [shadow_buy] 로 남았다(순서 위반)"


def test_t06_account_soft_gate_wins_no_shadow_record(monkeypatch, caplog):
    r = ready("momentum", monkeypatch)
    shadow(r.s)
    monkeypatch.setattr(r.s, "_account_soft_gate_blocked", lambda ticker=None: True)
    r.prime()
    assert r.fire() == Signal.NONE
    assert _buy_lines(caplog) == []


@pytest.mark.parametrize("sid", ["momentum", "volatility_breakout", "donchian_swing"])
def test_t06_signal_not_met_no_shadow_record(sid, monkeypatch, caplog):
    clock = Clock(kst(9, 40))
    r = ready(sid, monkeypatch, clock)
    shadow(r.s)
    r.prime()
    if sid == "donchian_swing":
        clock.set(9, 40)                                   # 09:05~09:30 진입창 밖
        assert r.fire() == Signal.NONE
    else:
        assert r.fire(r.prime_px) == Signal.NONE           # 기준선 교차 없음
    assert _buy_lines(caplog) == [], "신호가 안 난 평가가 섀도 기록이 됐다 — 관문이 신호 계산 앞에 있다"


# ===========================================================================
# t07 — 값 해석: `is True` 만 켜짐
# ===========================================================================
_ABSENT = object()


@pytest.mark.parametrize("value,warn", [
    pytest.param(False, False, id="false"),
    pytest.param(_ABSENT, False, id="absent"),
    pytest.param("true", True, id="str_true"),
    pytest.param(1, True, id="one"),
    pytest.param(None, True, id="null"),
    pytest.param("yes", True, id="str_yes"),
])
def test_t07_non_true_values_are_off(value, warn, monkeypatch, caplog):
    r = ready("donchian_swing", monkeypatch)
    if value is _ABSENT:
        r.s.config.params.pop(KEY, None)
    else:
        shadow(r.s, value)
    assert r.fire() == Signal.BUY, f"{value!r}: True 가 아닌 값은 실전 그대로 사야 한다"
    assert _buy_lines(caplog) == []
    warns = _cfg_lines(caplog, "donchian_swing", min_level=logging.WARNING)
    if warn:
        assert len(warns) == 1 and field(warns[0], "valid") == "0", warns
    else:
        assert warns == []


def test_t07_true_emits_warning_canary_once_per_day(monkeypatch, caplog):
    r = ready("donchian_swing", monkeypatch)
    shadow(r.s)
    r.s._candidates[U] = dict(r.s._candidates[T])
    r.fire()
    r.s.check_buy_signal(U, 10_600, 10_100)
    warns = _cfg_lines(caplog, "donchian_swing", min_level=logging.WARNING)
    assert len(warns) == 1, warns
    assert field(warns[0], "shadow") == "1" and field(warns[0], "valid") == "1"


# ===========================================================================
# t08 — PUT 경로(같은 dict) 즉시 반영
# ===========================================================================
def test_t08_toggle_takes_effect_on_next_call(monkeypatch):
    r = ready("donchian_swing", monkeypatch)
    r.s._candidates[U] = dict(r.s._candidates[T])
    shadow(r.s, True)
    assert r.fire() == Signal.NONE
    shadow(r.s, False)
    assert r.s.check_buy_signal(U, 10_600, 10_100) == Signal.BUY, "끈 직후 실전 BUY 가 아니다 — 값을 캐시했다"


@pytest.mark.parametrize("sid", ALL7)
def test_t08_turning_on_after_prime_takes_effect(sid, monkeypatch):
    r = ready(sid, monkeypatch)
    r.prime()
    shadow(r.s, True)
    assert r.fire() == Signal.NONE


# ===========================================================================
# t09 — 청산 무접촉 (cycle384 t11 과 같은 차분)
# ===========================================================================
_EXIT_PATH = (10_000, 10_700, 11_400, 11_000, 10_600, 10_150, 8_300)


def _exit_state(s) -> dict:
    out: dict = {}
    for name, v in vars(s).items():
        if name in ("config", "state") or not isinstance(v, (dict, set, list)):
            continue
        out[name] = repr(sorted(v, key=repr)) if isinstance(v, set) else repr(v)
    for t, p in s.state.positions.items():
        out[f"pos:{t}"] = (p.buy_price, p.quantity, p.high_since_buy)
    out["sold_today"] = sorted(s.state.sold_today)
    return out


def _run_exit_path(s) -> list:
    sigs = []
    pos = s.state.positions[T]
    for px in _EXIT_PATH:
        pos.high_since_buy = max(pos.high_since_buy, px)
        sigs.append(s.check_exit_signal(T, px, 10_000))
    return sigs


@pytest.mark.parametrize("sid", ALL7)
def test_t09_exit_signals_identical_when_shadow(sid, monkeypatch):
    clock = Clock(kst(10, 30))
    a = ready(sid, monkeypatch, clock)
    b = ready(sid, monkeypatch, clock)
    clock.set(10, 30)
    shadow(b.s, True)
    for x in (a, b):
        x.s.state.positions[T] = Position(
            ticker=T, buy_price=10_000, quantity=10, order_no="ORD-399",
            strategy_id=sid, buy_date=DAY, high_since_buy=10_000,
        )
    sa, sb = _run_exit_path(a.s), _run_exit_path(b.s)
    assert any(x != Signal.NONE for x in sa), f"{sid}: 청산 신호가 하나도 없다 — 비교가 공허하다 {sa}"
    assert sb == sa, f"{sid}: 섀도가 청산 신호를 바꿨다 — 끔={sa} 섀도={sb}"
    assert _exit_state(b.s) == _exit_state(a.s), f"{sid}: 섀도가 청산 상태를 바꿨다"


# ===========================================================================
# t10 — risk.on_tick: 섀도 전략 BUY 는 주문으로 가지 않고, 보유분 손절은 나간다
# ===========================================================================
def _rm(monkeypatch, *strategies):
    from src.engine import risk as risk_mod
    from src.engine import scanner
    from src.engine.risk import RiskManager
    from src.engine.strategy_registry import StrategyRegistry

    monkeypatch.setattr(risk_mod.session_tracker, "is_tradable", lambda sid, params: True)
    monkeypatch.setattr(scanner, "ticker_prices", {})
    monkeypatch.setattr(scanner, "ticker_last_tick", {})
    reg = StrategyRegistry()
    for s in strategies:
        reg.register(s)
    oe = MagicMock()
    oe.execute_buy = AsyncMock()
    oe.execute_sell = AsyncMock()
    oe._selling = set()
    return RiskManager(registry=reg, order_engine=oe), oe


@pytest.mark.parametrize("on,buys", [(True, 0), (False, 1)], ids=["shadow", "positive_control"])
async def test_t10_on_tick_shadow_does_not_buy_and_stop_still_fires(monkeypatch, caplog, on, buys):
    r = ready("long_tail_volatility", monkeypatch, ticker=U)
    shadow(r.s, on)
    r.s.state.positions[T] = Position(ticker=T, buy_price=10_000, quantity=10, order_no="ORD-T",
                                      strategy_id="long_tail_volatility", buy_date=DAY,
                                      high_since_buy=10_000)
    rm, oe = _rm(monkeypatch, r.s)
    await rm.on_tick(ticker=U, current_price=10_400, open_price=10_000, change_rate=4.0)
    await rm.on_tick(ticker=U, current_price=10_550, open_price=10_000, change_rate=5.5)
    assert oe.execute_buy.await_count == buys
    assert r.s.state.signal_count_today == buys, "섀도 BUY 가 실전 신호 수(퍼널)에 섞였다"
    assert len(_buy_lines(caplog)) == (1 if on else 0)
    await rm.on_tick(ticker=T, current_price=8_500, open_price=10_000, change_rate=-15.0)
    assert oe.execute_sell.await_count == 1, "섀도 전략 보유분 손절이 나가지 않았다"
    assert r.s.config.enabled is True


# ===========================================================================
# t11 — 수량 경로 무접촉
# ===========================================================================
@pytest.mark.parametrize("sid", ["donchian_swing", "kojiro", "momentum"])
def test_t11_calc_buy_quantity_is_independent_of_shadow(sid, monkeypatch):
    r = ready(sid, monkeypatch)
    q0 = r.s.calc_buy_quantity(r.fire_px, r.t)
    shadow(r.s)
    q1 = r.s.calc_buy_quantity(r.fire_px, r.t)
    assert q0 > 0
    assert q1 == q0, f"{sid}: 섀도가 수량을 바꿨다 — 섀도는 신호 단계에서만 끝나야 한다"


# ===========================================================================
# t12 — 관측 실패는 판정을 바꾸지 않는다
# ===========================================================================
def test_t12_logger_failure_still_returns_none_and_retries(monkeypatch, caplog):
    """`[shadow_` 줄만 터뜨린다 — 판정은 NONE 그대로, 복구 뒤 기록된다(peek → log → mark)."""
    from src.engine import strategy_base as sb

    caplog.set_level(logging.DEBUG)
    r = ready("donchian_swing", monkeypatch)
    shadow(r.s)
    st = {"armed": True, "fired": 0}

    def _bomb(orig):
        def _f(msg, *a, **k):
            rendered = str(msg)
            if a:
                try:
                    rendered = str(msg) % a
                except Exception:
                    pass
            if st["armed"] and rendered.startswith("[shadow_"):
                st["fired"] += 1
                raise RuntimeError("logger dead (cycle399 t12)")
            return orig(msg, *a, **k)
        return _f

    monkeypatch.setattr(sb.logger, "info", _bomb(sb.logger.info))
    monkeypatch.setattr(sb.logger, "warning", _bomb(sb.logger.warning))
    assert r.fire() == Signal.NONE, "관측 예외가 섀도 판정을 뚫었다 — 실전 주문이 나갈 수 있다"
    assert st["fired"] >= 2, "전제 — 카나리아·[shadow_buy] 둘 다 시도됐어야 한다"
    assert _buy_lines(caplog) == []
    st["armed"] = False
    assert r.fire() == Signal.NONE
    assert len(_buy_lines(caplog, "donchian_swing")) == 1, "복구 뒤 [shadow_buy] 가 없다 — mark 가 log 앞이다"
    assert len(_cfg_lines(caplog, "donchian_swing", min_level=logging.WARNING)) == 1


def test_t12_cap_exception_never_leaves_check_buy_signal(monkeypatch):
    r = ready("long_tail_volatility", monkeypatch)
    shadow(r.s)

    def _boom(*a, **k):
        raise RuntimeError("cap dead")

    monkeypatch.setattr(r.s._shadow_logged, "should_emit", _boom)
    r.prime()
    assert r.fire() == Signal.NONE
