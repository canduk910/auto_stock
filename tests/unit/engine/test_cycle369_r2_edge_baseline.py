"""cycle369 round 2 Red — Q7. 공통 게이트가 막은 동안 edge 전략의 기준가가 얼면 안 된다.

## 무엇을 고치나

LTV 는 VB 와 같은 **edge 교차** 전략이다(`prev < target <= current`, 기준가 `_prev_price`).
그런데 공통 게이트(`_account_soft_gate_blocked`)가 LTV 에서는 `check_buy_signal` 의
**첫 문장**이라(cycle233 M6), 상태 차단이 걸린 동안 기준가 갱신이 통째로 건너뛰어진다.
같은 날 차단이 풀리면(운영 롤백 `PUT buy_block_mode=off`·`observe`, 장 전 차단의 장중 해제)
첫 틱이 **얼어 있던 옛 기준가** 대비 거짓 돌파가 되어 추격 상한 없이 산다
(round-1 리뷰 탐침: 목표가 10,500 · 기준가 10,400 · 해제 뒤 첫 틱 11,900 → BUY, +13%).

main-session 결정 Q7 = **공통 게이트가 한 전략의 한 종목을 막을 때 그 전략의 그 종목
기준가를 비운다**(순수 메모리, `await` 0). 전략 7파일은 무변경이다 — 배선은
`StrategyBase._status_buy_blocked` 쪽이다.

| 전략 | 기준가 | 「비어 있음」의 의미 | 이 파일의 기대 |
|---|---|---|---|
| momentum | `_prev_prdy_rate[t]` | 첫 틱 = 기록만 | 해제 뒤 첫 틱 NONE |
| VB | `_prev_price[t][board]` | `prev == 0` = 기록만 | 해제 뒤 첫 틱 NONE |
| LTV | `_prev_price[t][board]` | `prev == 0` = 기록만 | 해제 뒤 첫 틱 NONE (**현재 RED**) |
| BFB·VCP | `_prev_price[t]` | `0` = **교차로 읽힌다**(`0 < level <= cur`) | 비우면 오히려 거짓 교차 → **새 교차를 만들면 안 된다**(가드) |

🔴 BFB·VCP 는 「없는 기준가」가 0 으로 읽혀 `0 < level <= current` 가 **참**이 된다. 그래서
`strategy_base` 에서 `_prev_price` 를 전략 구분 없이 `pop` 하는 구현은 BFB·VCP 에 새 거짓
교차를 만든다. 마지막 두 테스트가 그것을 막는다(현재 코드에서는 초록 — 과잉 시정 가드).

## 시계

- leaf = `status_exit_watch._now_kst` seam(`clock` 픽스처)
- 전략 모듈 = 모듈의 `datetime` 이름을 같은 Clock 을 따르는 서브클래스로 교체(`pin_module_clock`)
"""
from __future__ import annotations

import pytest

from tests.unit.engine._cycle369_support import (
    LIVE,
    clock,  # noqa: F401 — pytest 픽스처
    db_modes,  # noqa: F401
    gate,
    kst,
    leaf,
    open_info,
    overheat,
    pin_module_clock,
    record,
)

pytestmark = [pytest.mark.unit, pytest.mark.real_status_watch]

_T = "005160"
_U = "294141"   # 막히지 않는 두 번째 종목


@pytest.fixture(autouse=True)
def _base(caplog, db_modes, monkeypatch):
    open_info(caplog)
    try:
        from src.engine import account_risk_watcher

        account_risk_watcher.reset_state_for_test()
    except Exception:
        pass
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    monkeypatch.setattr(scanner, "ticker_prices", {})


_STRATS = {
    "momentum": ("src.engine.strategies.momentum", "MomentumStrategy"),
    "volatility_breakout": ("src.engine.strategies.volatility_breakout", "VolatilityBreakoutStrategy"),
    "long_tail_volatility": ("src.engine.strategies.long_tail_volatility", "LongTailVolatilityStrategy"),
    "bull_flag_breakout": ("src.engine.strategies.bull_flag_breakout", "BullFlagBreakoutStrategy"),
    "vcp_breakout": ("src.engine.strategies.vcp_breakout", "VcpBreakoutStrategy"),
}


def _module(sid):
    import importlib

    return importlib.import_module(_STRATS[sid][0])


def _make(sid, **params):
    from src.engine.strategy_base import StrategyConfig

    cls = getattr(_module(sid), _STRATS[sid][1])
    s = cls(StrategyConfig(strategy_id=sid, name=sid, params={"exchange": "KRX", **params}))
    s.state.total_investment = 10_000_000
    return s


def _edge_ready(monkeypatch, s, *tickers):
    """VB·LTV — `main` 보드 목표가 10,500 이 REST 로 확정된 상태."""
    for t in tickers:
        s._targets[t] = {
            "k": 0.5, "prev_range": 1000, "target_offset_base": 500, "target_offset": 500,
            "target_price": 10500, "open_price": 10000,
            "boards": {"main": {"open_price": 10000, "target_price": 10500, "target_offset": 500}},
        }
        s._open_confirmed[t] = {"main": True}
    monkeypatch.setattr(s, "_resolve_active_board", lambda: "main")


def _block_in_session(clock, t=_T, *, h=9, m=41):
    """장중 해당 기록 → 그날 고정 차단(phase=in)."""
    clock.set(h, m)
    record(t, overheat(t), kst(h, m), src="inc")
    assert gate(t) is True, "전제 — 차단이 걸려야 한다"


def _release(clock, h=10, m=30):
    """운영 롤백 경로 — `PUT buy_block_mode=off` 가 같은 요청에서 `apply_mode` 로 반영된다."""
    clock.set(h, m)
    leaf().apply_mode("buy", "off")
    assert gate(_T) is False, "전제 — 해제돼야 한다"


# ===========================================================================
# LTV — 게이트가 첫 문장이라 기준가가 언다 (현재 RED)
# ===========================================================================
def test_q7_ltv_release_after_block_does_not_fire_false_crossing(clock, monkeypatch):
    """Q7 · J11 확장 — 차단 전 기준가 틱 → 차단 → 해제 → **해제 뒤 첫 틱은 새 교차가 아니다**.

    현재 코드: 차단 중 LTV 는 첫 문장에서 돌아가 `_prev_price` 가 10,400 에 언다.
    해제 뒤 첫 틱 11,900 이 `10,400 < 10,500 <= 11,900` 으로 읽혀 BUY(+13% 추격).
    """
    from src.engine.strategy_base import Signal

    pin_module_clock(monkeypatch, clock, _module("long_tail_volatility"))
    s = _make("long_tail_volatility")
    _edge_ready(monkeypatch, s, _T)

    clock.set(9, 40)
    assert s.check_buy_signal(_T, 10400, 10000) == Signal.NONE      # 기준가 10,400 (목표가 아래)

    _block_in_session(clock)
    assert s.check_buy_signal(_T, 10600, 10000) == Signal.NONE      # 차단 중 — 목표가 위
    assert s.check_buy_signal(_T, 11800, 10000) == Signal.NONE

    _release(clock)
    assert s.check_buy_signal(_T, 11900, 10000) == Signal.NONE, (
        "LTV 기준가가 차단 동안 얼어 있었다 — 해제 뒤 첫 틱이 옛 기준가(10,400) 대비 거짓 돌파로 BUY"
    )
    # 양성 대조 — 목표가 아래로 내려갔다가 다시 넘으면 산다(기준가가 살아 있다)
    assert s.check_buy_signal(_T, 10400, 10000) == Signal.NONE
    assert s.check_buy_signal(_T, 10600, 10000) == Signal.BUY


def test_q7_ltv_baseline_clear_is_scoped_to_the_blocked_ticker(clock, monkeypatch):
    """막힌 종목의 기준가만 비운다 — 다른 종목의 기준가는 그대로(전 종목 clear 금지)."""
    from src.engine.strategy_base import Signal

    pin_module_clock(monkeypatch, clock, _module("long_tail_volatility"))
    s = _make("long_tail_volatility")
    _edge_ready(monkeypatch, s, _T, _U)

    clock.set(9, 40)
    assert s.check_buy_signal(_U, 10400, 10000) == Signal.NONE      # U 기준가 10,400
    assert s.check_buy_signal(_T, 10400, 10000) == Signal.NONE

    _block_in_session(clock, _T)
    assert s.check_buy_signal(_T, 10600, 10000) == Signal.NONE      # T 만 막힘
    assert s.check_buy_signal(_U, 10600, 10000) == Signal.BUY, (
        "막히지 않은 종목의 기준가까지 지웠다 — 정상 돌파를 놓쳤다"
    )


def test_q7_ltv_observe_mode_keeps_normal_crossing(clock, monkeypatch):
    """observe 는 막지 않으므로 기준가도 비우지 않는다 — 정상 교차 그대로(양성 대조)."""
    from src.engine.strategy_base import Signal

    pin_module_clock(monkeypatch, clock, _module("long_tail_volatility"))
    s = _make("long_tail_volatility")
    _edge_ready(monkeypatch, s, _T)
    leaf().apply_mode("buy", "observe")

    clock.set(9, 40)
    assert s.check_buy_signal(_T, 10400, 10000) == Signal.NONE
    record(_T, LIVE["005160"], kst(9, 41), src="inc")
    clock.set(9, 41)
    assert s.check_buy_signal(_T, 10600, 10000) == Signal.BUY


# ===========================================================================
# momentum · VB — 발사 직전 게이트(현재도 초록 — 회귀 가드, round-1 생존 M36 을 죽인다)
# ===========================================================================
def test_q7_momentum_baseline_before_block_then_release_no_false_cross(clock, monkeypatch):
    """J11 확장 — **차단 전에** 기준가 틱을 하나 둔다(round-1 J11 은 차단 뒤부터라 M36 이 살았다).

    M36 = momentum 최상단에 상태 게이트를 하나 더 둔 돌연변이 — 차단 동안 `_prev_prdy_rate`
    가 28% 에 얼고, 해제 뒤 29.9% 첫 틱이 거짓 돌파로 BUY 가 된다.
    """
    from src.engine import scanner
    from src.engine.strategy_base import Signal

    pin_module_clock(monkeypatch, clock, _module("momentum"))
    monkeypatch.setattr(scanner, "ticker_prev_close", {_T: 10000})
    s = _make("momentum")

    clock.set(9, 40)
    assert s.check_buy_signal(_T, 12800, 12000) == Signal.NONE      # 기준 28.0%(임계 29% 아래)

    _block_in_session(clock)
    assert s.check_buy_signal(_T, 12950, 12000) == Signal.NONE      # 교차 — 차단
    assert s.check_buy_signal(_T, 12980, 12000) == Signal.NONE

    _release(clock)
    assert s.check_buy_signal(_T, 12990, 12000) == Signal.NONE, (
        "momentum 기준가가 차단 동안 얼었다 — 해제 뒤 첫 틱 29.9% 가 거짓 돌파"
    )
    assert s.check_buy_signal(_T, 12700, 12000) == Signal.NONE
    assert s.check_buy_signal(_T, 12950, 12000) == Signal.BUY


def test_q7g_momentum_baseline_clear_is_scoped_to_the_blocked_ticker(clock, monkeypatch):
    """🔁 cycle369 R3 F6(Q7g) — momentum 도 막힌 종목의 `_prev_prdy_rate` 만 비운다.

    전 종목을 비우면(`_prev_prdy_rate.clear()`) 막히지 않은 종목의 다음 틱이 「첫 틱 = 기록만」
    으로 떨어져 **진짜 돌파를 조용히 놓친다**(급등 목록 전체가 한 번씩 매수 기회를 잃는다).
    """
    from src.engine import scanner
    from src.engine.strategy_base import Signal

    pin_module_clock(monkeypatch, clock, _module("momentum"))
    monkeypatch.setattr(scanner, "ticker_prev_close", {_T: 10000, _U: 10000})
    s = _make("momentum")

    clock.set(9, 40)
    assert s.check_buy_signal(_U, 12800, 12000) == Signal.NONE      # U 기준 28.0%
    assert s.check_buy_signal(_T, 12800, 12000) == Signal.NONE      # T 기준 28.0%

    _block_in_session(clock, _T)
    assert s.check_buy_signal(_T, 12950, 12000) == Signal.NONE      # T 교차 — 차단(T 기준만 비운다)
    assert s.check_buy_signal(_U, 12950, 12000) == Signal.BUY, (
        "막히지 않은 종목의 momentum 기준가까지 지웠다 — 정상 돌파(28.0% → 29.5%)를 놓쳤다"
    )


def test_q7_vb_baseline_before_block_then_release_no_false_cross(clock, monkeypatch):
    from src.engine.strategy_base import Signal

    pin_module_clock(monkeypatch, clock, _module("volatility_breakout"))
    s = _make("volatility_breakout")
    _edge_ready(monkeypatch, s, _T)

    clock.set(9, 40)
    assert s.check_buy_signal(_T, 10400, 10000) == Signal.NONE      # 첫 틱 기록 10,400

    _block_in_session(clock)
    assert s.check_buy_signal(_T, 10550, 10000) == Signal.NONE      # 교차 — 차단
    assert s.check_buy_signal(_T, 11800, 10000) == Signal.NONE

    _release(clock)
    assert s.check_buy_signal(_T, 11900, 10000) == Signal.NONE, "VB 기준가가 얼었다 — 거짓 돌파"
    assert s.check_buy_signal(_T, 10400, 10000) == Signal.NONE
    assert s.check_buy_signal(_T, 10550, 10000) == Signal.BUY


# ===========================================================================
# BFB · VCP — 과잉 시정 가드 (「없는 기준가 = 0」 이 교차로 읽힌다)
# ===========================================================================
def _spy_vol_gate(monkeypatch, s):
    from src.engine.strategy_base import Signal

    calls: list[tuple] = []

    def _spy(ticker, info, current_price, level, latch):
        calls.append((ticker, current_price, latch))
        return Signal.NONE

    monkeypatch.setattr(s, "_evaluate_vol_gate", _spy)
    return calls


@pytest.mark.parametrize("sid,level_key,extra", [
    ("vcp_breakout", "base_high", {"base_low": 9500}),
    ("bull_flag_breakout", "flag_high", {"flag_low": 9500}),
])
def test_q7_bfb_vcp_release_does_not_create_new_crossing(clock, monkeypatch, sid, level_key, extra):
    """BFB·VCP 는 기준가가 없으면 0 으로 읽어 `0 < level <= cur` 가 **참**이다.

    차단 전 기준가가 이미 레벨 **위**(10,600)였다면, 해제 뒤 첫 틱(10,800)은 새 교차가 아니다.
    `_prev_price` 를 전략 구분 없이 `pop` 하는 Q7 구현은 여기서 거짓 교차(거래량 게이트 진입)를
    새로 만든다 — 그것을 막는 가드(현재 코드에서는 초록).
    """
    params = {"breakout_retention_minutes": 0} if sid == "bull_flag_breakout" else {}
    pin_module_clock(monkeypatch, clock, _module(sid))
    s = _make(sid, **params)
    s._candidates[_T] = {level_key: 10500, **extra}
    calls = _spy_vol_gate(monkeypatch, s)

    clock.set(10, 0)
    s.check_buy_signal(_T, 10400, 10000)      # 기준 10,400 (레벨 아래, 첫 관측 — 교차 아님)
    s.check_buy_signal(_T, 10600, 10000)      # 진짜 교차 → 거래량 게이트 1회
    assert len(calls) == 1, f"전제 — 교차 1회 {calls}"

    _block_in_session(clock, h=10, m=1)
    s.check_buy_signal(_T, 10700, 10000)      # 차단 중

    _release(clock)
    s.check_buy_signal(_T, 10800, 10000)      # 해제 뒤 첫 틱 — 레벨 위에 머묾(새 교차 아님)
    assert len(calls) == 1, (
        f"{sid}: 해제 뒤 첫 틱이 새 교차로 읽혔다 — 기준가를 0 으로 비워 `0 < level <= cur` 가 참이 됐다"
    )
    # 양성 대조 — 내려갔다 다시 넘으면 교차
    s.check_buy_signal(_T, 10400, 10000)
    s.check_buy_signal(_T, 10600, 10000)
    assert len(calls) == 2
