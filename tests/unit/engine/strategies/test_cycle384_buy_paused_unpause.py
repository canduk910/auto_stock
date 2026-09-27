"""cycle384 Red — `buy_paused` 해제 첫 틱: 거짓 돌파·낡은 래치 매수 금지 (T14~T23).

명세 정본 = `_workspace/red/cycle384_buy_paused_spec.md` §4 · §9.3

멈춤은 공통 게이트 **안**이라 첫 문장 게이트 전략(LTV·donchian·BFB·VCP·kojiro)은 멈춘 동안 신호
함수 본문이 통째로 안 돈다 — 기준가·래치가 얼어붙는다. 발사 직전 전략(momentum·VB)은 돌파 순간에만
게이트에 닿는다(기준가는 계속 갱신).

| 전략 | 멈출 때 지우는 것 | 해제 뒤 첫 틱 |
|---|---|---|
| momentum | `_prev_prdy_rate[t]` (cycle369 헬퍼) | 기록만 → NONE |
| VB · LTV | 중첩 `_prev_price[t]` (cycle369 헬퍼) | `prev==0` → NONE |
| BFB | `_breakout_first_seen[t]` · `_vol_latch[t]` — 평평한 `_prev_price` 는 **안 건드림** | 새 edge-crossing 만 인정 |
| VCP | `_vol_latch[t]` — 평평한 `_prev_price` 는 **안 건드림** | 새 edge-crossing 만 인정 |
| donchian · kojiro | 없음(`_bought_today` 도 안 건드림) | 창 안이면 곧바로 정상 평가(재기동과 동치) |

🔴 평평한 `_prev_price` 를 지우면 없는 값이 `0` 으로 읽혀 `0 < level <= current` 가 참이 되는
**새** 거짓 교차가 생긴다(cycle369 `_clear_edge_baseline_on_block` docstring). T20 이 막는다.
T21 은 남는 위험(멈춘 사이 실제로 일어난 교차를 해제 뒤 늦게 보는 것)을 **특성화**로 못박는다 —
WS 공백·밤사이 갭과 같은 기존 의미론이다.
"""
from __future__ import annotations

import copy
from datetime import date, timedelta

import pytest

from src.engine import tick_volume
from src.engine.strategy_base import Signal
from tests.unit.engine._cycle384_support import (
    T,
    U,
    need_pause_surface,
    open_info,
    pause,
    ready,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, caplog):
    from src.engine import scanner

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


def _sig(r, px: int, ticker: str = T) -> Signal:
    return r.s.check_buy_signal(ticker, px, r.open)


# ===========================================================================
# T14 — LTV: 첫 문장 게이트라 기준가가 언다 → 멈춘 틱에서 비운다 (M13)
# ===========================================================================
def test_t14_ltv_unpause_first_tick_is_not_a_false_crossing(monkeypatch):
    r = ready("long_tail_volatility", monkeypatch)
    assert _sig(r, 10_400) == Signal.NONE                    # 기준 10,400 (목표가 10,500 아래)
    pause(r.s)
    assert _sig(r, 10_600) == Signal.NONE                    # 멈춤 — 목표가 위
    assert T not in r.s._prev_price, "멈춘 틱이 LTV 중첩 기준가를 비우지 않았다(M13)"
    assert _sig(r, 11_800) == Signal.NONE
    pause(r.s, False)
    assert _sig(r, 11_900) == Signal.NONE, (
        "해제 첫 틱이 얼어 있던 옛 기준가(10,400) 대비 거짓 돌파로 BUY(+13% 추격) — M13"
    )
    assert _sig(r, 10_400) == Signal.NONE
    assert _sig(r, 10_600) == Signal.BUY, "양성 대조 — 진짜 재교차는 산다"


# ===========================================================================
# T15 · T16 — 발사 직전 전략: 교차 틱에서 기준가를 비운다(cycle369 헬퍼 재사용)
# ===========================================================================
def test_t15_vb_paused_crossing_pops_nested_baseline(monkeypatch):
    r = ready("volatility_breakout", monkeypatch)
    assert _sig(r, 10_400) == Signal.NONE
    pause(r.s)
    assert _sig(r, 10_550) == Signal.NONE                    # 교차 — 멈춤
    assert T not in r.s._prev_price, "멈춘 교차 틱에서 VB 중첩 기준가를 비우지 않았다(M13)"
    pause(r.s, False)
    assert _sig(r, 10_600) == Signal.NONE, "해제 다음 틱(목표 위 그대로)이 BUY — 추격 상한 없는 매수"
    assert _sig(r, 10_400) == Signal.NONE
    assert _sig(r, 10_550) == Signal.BUY


def test_t16_momentum_paused_crossing_pops_rate_baseline(monkeypatch):
    r = ready("momentum", monkeypatch)
    assert _sig(r, 12_800) == Signal.NONE                    # 28.0%
    pause(r.s)
    assert _sig(r, 12_910) == Signal.NONE                    # 29.1% 교차 — 멈춤
    assert T not in r.s._prev_prdy_rate, "멈춘 교차 틱에서 momentum 기준을 비우지 않았다(M13)"
    pause(r.s, False)
    assert _sig(r, 12_930) == Signal.NONE, "해제 다음 틱(29.3%)이 BUY — 첫 틱은 기록만이어야 한다"
    assert _sig(r, 12_700) == Signal.NONE
    assert _sig(r, 12_950) == Signal.BUY


# ===========================================================================
# T17 · T19 — BFB/VCP 낡은 거래량 래치: 멈춘 사이 셋업이 죽었다 돌아와도 해제 첫 틱에 사지 않는다 (M15)
# ===========================================================================
@pytest.mark.parametrize("sid,dead_px", [("bull_flag_breakout", 9_400), ("vcp_breakout", 8_900)],
                         ids=["t17_bfb", "t19_vcp"])
def test_t17_t19_stale_volume_latch_is_dropped_on_pause(monkeypatch, sid, dead_px):
    r = ready(sid, monkeypatch)
    tick_volume.record_acml_vol(T, 1)                        # 거래량 부족 → 교차가 래치를 무장한다
    assert _sig(r, 9_900) == Signal.NONE
    assert _sig(r, 10_050) == Signal.NONE
    assert T in r.s._vol_latch, "전제 — 거래량 부족 교차가 래치를 무장해야 한다"

    pause(r.s)
    assert _sig(r, 10_020) == Signal.NONE
    assert T not in r.s._vol_latch, f"{sid}: 첫 멈춤 틱이 래치를 지우지 않았다(M15)"
    assert _sig(r, dead_px) == Signal.NONE                   # 멈춘 사이 베이스/플래그 하단 이탈(죽은 셋업)
    assert _sig(r, 10_050) == Signal.NONE

    tick_volume.record_acml_vol(T, 10_000_000)
    pause(r.s, False)
    assert _sig(r, 10_100) == Signal.NONE, (
        f"{sid}: 해제 첫 틱이 낡은 래치로 죽은 셋업을 샀다(001450 역선택 — M15)"
    )
    assert _sig(r, 9_900) == Signal.NONE
    assert _sig(r, 10_100) == Signal.BUY, "양성 대조 — 진짜 재교차는 산다"


# ===========================================================================
# T18 — BFB 낡은 유지 대기: 해제 첫 틱이 거래량 게이트로 직행하지 않는다 (M15)
# ===========================================================================
def test_t18_bfb_stale_retention_wait_is_dropped_on_pause(monkeypatch):
    r = ready("bull_flag_breakout", monkeypatch, breakout_retention_minutes=3)
    tick_volume.record_acml_vol(T, 10_000_000)
    r.s._prev_price[T] = 10_050                              # 1차 돌파 틱이 남긴 기준
    r.s._breakout_first_seen[T] = r.clock.now - timedelta(minutes=10)

    pause(r.s)
    assert _sig(r, 10_050) == Signal.NONE
    assert T not in r.s._breakout_first_seen, "첫 멈춤 틱이 유지 대기를 지우지 않았다(M15)"
    pause(r.s, False)
    assert _sig(r, 10_100) == Signal.NONE, "해제 첫 틱이 연속 유지 확인 없이 거래량 게이트로 직행 — 낡은 유지 완주"

    # 양성 대조 — 새 교차는 유지 대기부터 다시 시작한다
    assert _sig(r, 9_900) == Signal.NONE
    assert _sig(r, 10_100) == Signal.NONE
    assert T in r.s._breakout_first_seen
    r.clock.advance(4 * 60)
    assert _sig(r, 10_100) == Signal.BUY


# ===========================================================================
# T20 — 평평한 `_prev_price`(BFB·VCP)는 건드리지 않는다 (M14)
# ===========================================================================
@pytest.mark.parametrize("sid", ["bull_flag_breakout", "vcp_breakout"])
def test_t20_flat_prev_price_is_untouched_by_pause(monkeypatch, sid):
    r = ready(sid, monkeypatch)
    assert _sig(r, 9_900) == Signal.NONE
    pause(r.s)
    assert _sig(r, 10_300) == Signal.NONE
    assert _sig(r, 9_800) == Signal.NONE
    assert r.s._prev_price.get(T) == 9_900, (
        f"{sid}: 멈춤이 평평한 기준가를 바꾸거나 지웠다(M14) — {r.s._prev_price.get(T)!r}"
    )


@pytest.mark.parametrize("sid", ["bull_flag_breakout", "vcp_breakout"])
def test_t20_unpause_above_level_creates_no_new_crossing(monkeypatch, sid):
    """기준가가 이미 레벨 위였다면 해제 뒤 레벨 위 틱은 교차가 아니다 — 기준가를 0 으로 비우면 교차가 된다(M14)."""
    r = ready(sid, monkeypatch)
    calls: list = []

    def _spy(ticker, info, current_price, level, latch):
        calls.append(current_price)
        return Signal.NONE

    monkeypatch.setattr(r.s, "_evaluate_vol_gate", _spy)
    _sig(r, 9_900)
    _sig(r, 10_200)                                          # 진짜 교차 → 게이트 1회, 기준 10,200
    assert calls == [10_200]
    pause(r.s)
    _sig(r, 10_300)
    pause(r.s, False)
    _sig(r, 10_400)
    assert calls == [10_200], f"{sid}: 해제 첫 틱이 새 교차로 읽혔다 — 평평한 기준가를 비웠다(M14)"
    _sig(r, 9_900)
    _sig(r, 10_200)
    assert calls == [10_200, 10_200], "양성 대조 — 내려갔다 다시 넘으면 교차"


# ===========================================================================
# T21 — 특성화: 멈춘 사이 실제로 일어난 교차는 해제 뒤 「늦게」 본다 (잔여 위험 문서화)
# ===========================================================================
def test_t21_vcp_late_crossing_after_unpause_buys_characterization(monkeypatch):
    r = ready("vcp_breakout", monkeypatch)
    assert _sig(r, 9_900) == Signal.NONE                     # 기준 9,900 < base_high 10,000
    pause(r.s)
    assert _sig(r, 10_200) == Signal.NONE                    # 멈춘 사이 실제 교차
    pause(r.s, False)
    assert _sig(r, 10_300) == Signal.BUY, (
        "특성화 — 해제 첫 틱(+3% < 추격 상한 7.5%)은 멈춘 사이의 교차를 늦게 본다(WS 공백과 같은 의미론)"
    )


def test_t21_bfb_late_crossing_after_unpause_starts_retention(monkeypatch):
    r = ready("bull_flag_breakout", monkeypatch, breakout_retention_minutes=3)
    assert _sig(r, 9_900) == Signal.NONE
    pause(r.s)
    assert _sig(r, 10_200) == Signal.NONE
    assert T not in r.s._breakout_first_seen
    pause(r.s, False)
    assert _sig(r, 10_300) == Signal.NONE, "BFB 는 해제 시점부터 유지 대기를 새로 시작한다"
    assert r.s._breakout_first_seen.get(T) == r.clock.now


# ===========================================================================
# T22 — donchian·kojiro: 창 중간 해제 = 창 중간 재기동과 동치 (M17)
# ===========================================================================
@pytest.mark.parametrize("sid", ["donchian_swing", "kojiro"])
def test_t22_mid_window_unpause_buys_like_a_restart(monkeypatch, sid):
    r = ready(sid, monkeypatch)
    pause(r.s)
    assert r.fire() == Signal.NONE
    r.clock.set(9, 20)
    assert r.fire() == Signal.NONE
    pause(r.s, False)
    assert r.fire() == Signal.BUY, f"{sid}: 09:20 해제 뒤 첫 평가가 BUY 가 아니다 — 멈춤이 _bought_today 에 넣었다(M17)"


# ===========================================================================
# T23 — 래치 정리는 두 속성의 그 종목만 (M16)
# ===========================================================================
_KEEP = ("_position_setup", "_entry_atr", "_breakout_watch", "_cooldown_until", "_breakeven_latched",
         "_bought_today", "_candidates", "_partial_exit")


def _snap(s) -> dict:
    return {n: copy.deepcopy(getattr(s, n)) for n in _KEEP if hasattr(s, n)}


@pytest.mark.parametrize("sid", ["bull_flag_breakout", "vcp_breakout"])
def test_t23_pause_clears_only_the_two_entry_latches_of_that_ticker(monkeypatch, sid):
    need_pause_surface()
    r = ready(sid, monkeypatch)
    now = r.clock.now
    s = r.s
    s._position_setup[T] = {"flag_low": 9_500, "base_low": 9_000, "atr14": 300}
    s._entry_atr[T] = 300.0
    s._breakeven_latched.add(T)
    s._cooldown_until[U] = date(2026, 9, 30)
    if hasattr(s, "_breakout_watch"):
        s._breakout_watch = {"date": now.date(), "tickers": {T: {"hi": 10_050}}}
    latch = {"armed_at": now, "armed_date": now.date(), "flag_high": 10_000, "flag_low": 9_500,
             "base_high": 10_000, "base_low": 9_000}
    s._vol_latch[T] = dict(latch)
    s._vol_latch[U] = dict(latch)
    if hasattr(s, "_breakout_first_seen"):
        s._breakout_first_seen[T] = now
        s._breakout_first_seen[U] = now
    before = _snap(s)

    pause(s)
    assert _sig(r, 10_050) == Signal.NONE
    assert T not in s._vol_latch and U in s._vol_latch, "멈춘 종목의 래치만 지워야 한다"
    if hasattr(s, "_breakout_first_seen"):
        assert T not in s._breakout_first_seen and U in s._breakout_first_seen
    assert _snap(s) == before, f"{sid}: 래치 정리가 청산·관측 상태를 건드렸다(M16)"
    got = s._clear_entry_latches_on_pause(U)
    assert tuple(got) == (("breakout_first_seen", "vol_latch") if hasattr(s, "_breakout_first_seen")
                          else ("vol_latch",)), got
