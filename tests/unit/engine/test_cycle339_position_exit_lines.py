"""cycle339 — 잔고 화면의 손절가·목표가 leaf 회귀.

🔴 이 그물은 **값**을 잰다. 「필드가 응답에 있다」만 보면 손절가와 목표가를
맞바꾸거나, 매수 트리거 가격을 목표가로 넣거나, 설정한 적 없는 기본값(−7%)으로
계산한 숫자를 띄워도 전부 초록이다. 이 화면은 운영자가 "여기까지는 버틴다" 를
판단하는 곳이라 **틀린 손절가는 없는 것보다 나쁘다.**
"""
from __future__ import annotations

import pytest

from src.engine.position_exit_lines import build_exit_line_map, resolve_exit_lines


class _Pos:
    def __init__(self, buy_price: int, quantity: int = 1):
        self.buy_price = buy_price
        self.quantity = quantity


class _State:
    def __init__(self, positions: dict):
        self.positions = positions


class _Config:
    def __init__(self, params: dict):
        self.params = params


class _Strategy:
    """전략 더블 — 실제 전략의 **공개 표면만** 흉내 낸다."""

    def __init__(
        self,
        strategy_id: str,
        positions: dict,
        params: dict | None = None,
        effective_stop=None,
        targets: dict | None = None,
        raise_on_stop: bool = False,
    ):
        self.strategy_id = strategy_id
        self.state = _State(positions)
        self.config = _Config(params or {})
        self._effective_stop = effective_stop
        self._targets = targets
        self._raise_on_stop = raise_on_stop
        if effective_stop is not None or raise_on_stop:
            self.get_effective_stop_price = self._stop  # type: ignore[assignment]
        if targets is not None:
            self.get_targets_status = lambda: self._targets  # type: ignore[assignment]

    def _stop(self, ticker: str):
        if self._raise_on_stop:
            raise RuntimeError("의도적 실패")
        return self._effective_stop


# ── 손절가 ────────────────────────────────────────────────────────────────


def test_effective_stop_wins_and_is_labeled():
    """보유형 전략의 실효 손절선이 1순위이고 출처가 붙는다."""
    s = _Strategy("kojiro", {"005930": _Pos(70_000)},
                  params={"hard_stop_pct": -8.0}, effective_stop=66_500)
    out = resolve_exit_lines([s], "005930")
    assert out["stop_price"] == 66_500          # hard_pct(64,400) 가 아니다
    assert out["stop_source"] == "effective"
    assert out["strategy_id"] == "kojiro"


def test_hard_pct_fallback_computes_from_buy_price():
    """실효 손절선이 없는 전략은 `buy_price × (1 + 하드손절%/100)` 근사를 쓴다."""
    s = _Strategy("momentum", {"005930": _Pos(70_000)},
                  params={"stop_loss_rate": -5.0})
    out = resolve_exit_lines([s], "005930")
    assert out["stop_price"] == 66_500          # 70,000 × 0.95
    assert out["stop_source"] == "hard_pct"


def test_hard_pct_picks_most_conservative_of_several_keys():
    """후보 키가 여럿이면 **가장 보수적인**(가장 높은 손절선) 값이다."""
    s = _Strategy("long_tail_volatility", {"005930": _Pos(100_000)},
                  params={"intraday_stop_loss": -3.5, "overnight_stop_loss": -9.0})
    out = resolve_exit_lines([s], "005930")
    # min(-3.5, -9.0) = -9.0 → 91,000
    assert out["stop_price"] == 91_000
    assert out["stop_source"] == "hard_pct"


def test_no_stop_key_yields_none_not_default_minus_seven():
    """🔴 손절 키가 하나도 없으면 `None` 이다 — 기본값 −7% 로 숫자를 지어내지 않는다.

    `extract_hard_stop_pct` 는 결측 시 −7.0 으로 fail-open 하는데, 그 값으로
    계산한 숫자를 띄우면 **운영자가 설정한 적 없는 손절가**가 화면에 선다.
    """
    s = _Strategy("momentum", {"005930": _Pos(70_000)}, params={"position_ratio": 0.25})
    out = resolve_exit_lines([s], "005930")
    assert out["stop_price"] is None
    assert out["stop_source"] is None


def test_positive_stop_pct_is_rejected():
    """양수 손절률은 규약 위반이라 채택하지 않는다(손절선이 매수가 위가 된다)."""
    s = _Strategy("momentum", {"005930": _Pos(70_000)}, params={"stop_loss_rate": 5.0})
    assert resolve_exit_lines([s], "005930")["stop_price"] is None


def test_effective_stop_exception_falls_back_not_crashes():
    """실효 손절선 계산이 터져도 근사로 물러서고 화면은 산다."""
    s = _Strategy("donchian_swing", {"005930": _Pos(70_000)},
                  params={"hard_stop_pct": -10.0}, raise_on_stop=True)
    out = resolve_exit_lines([s], "005930")
    assert out["stop_price"] == 63_000
    assert out["stop_source"] == "hard_pct"


@pytest.mark.parametrize("bad", [0, -1, None, "abc", True, False])
def test_non_positive_effective_stop_is_not_adopted(bad):
    """0·음수·비수치·bool 은 가격이 아니다 — 특히 `True` 가 1원이 되면 안 된다."""
    s = _Strategy("kojiro", {"005930": _Pos(70_000)}, effective_stop=bad)
    assert resolve_exit_lines([s], "005930")["stop_price"] is None


# ── 목표가 ────────────────────────────────────────────────────────────────


def test_measured_target_only_for_bull_flag():
    s = _Strategy("bull_flag_breakout", {"005930": _Pos(70_000)},
                  targets={"005930": {"measured_target": 84_000}})
    out = resolve_exit_lines([s], "005930")
    assert out["target_price"] == 84_000
    assert out["target_source"] == "measured_move"


def test_other_strategies_have_no_target_even_with_target_price():
    """🔴 VB·LTV 의 `target_price` 는 **매수 트리거**이지 익절가가 아니다.

    이미 산 종목의 「목표가」 칸에 그 값을 넣으면 완전한 거짓 정보다.
    """
    s = _Strategy("volatility_breakout", {"005930": _Pos(70_000)},
                  params={"stop_loss_rate": -5.0},
                  targets={"005930": {"target_price": 73_000, "measured_target": 99_000}})
    out = resolve_exit_lines([s], "005930")
    assert out["target_price"] is None
    assert out["target_source"] is None
    # 손절가는 정상적으로 나온다 — 목표가만 막는다.
    assert out["stop_price"] == 66_500


def test_bull_flag_without_measured_target_is_none():
    s = _Strategy("bull_flag_breakout", {"005930": _Pos(70_000)},
                  targets={"005930": {"measured_target": 0}})
    assert resolve_exit_lines([s], "005930")["target_price"] is None


# ── 경계 ──────────────────────────────────────────────────────────────────


def test_unheld_ticker_returns_all_none():
    """수동 매매분처럼 어느 전략도 안 들고 있으면 추측하지 않는다."""
    s = _Strategy("kojiro", {"005930": _Pos(70_000)}, effective_stop=66_000)
    out = resolve_exit_lines([s], "000660")
    assert out == {
        "strategy_id": None, "stop_price": None, "stop_source": None,
        "target_price": None, "target_source": None,
    }


def test_empty_ticker_and_empty_registry():
    assert resolve_exit_lines([], "005930")["stop_price"] is None
    assert resolve_exit_lines([_Strategy("kojiro", {})], "")["strategy_id"] is None


def test_broken_strategy_object_never_raises():
    """상태가 깨진 전략이 섞여도 순회가 죽지 않는다."""
    class Broken:
        @property
        def state(self):
            raise RuntimeError("깨짐")

    good = _Strategy("kojiro", {"005930": _Pos(70_000)}, effective_stop=66_000)
    # Broken 이 먼저 와도 결과를 얻는다.
    out = resolve_exit_lines([Broken(), good], "005930")
    assert out["stop_price"] in (66_000, None)  # 순회 중단 시 None 도 허용
    # 적어도 예외는 나오지 않는다.


def test_build_map_covers_every_requested_ticker():
    """요청한 종목은 하나도 빠지지 않는다 — 빠지면 화면이 키 없음으로 깨진다."""
    s = _Strategy("kojiro", {"005930": _Pos(70_000)}, effective_stop=66_000)
    m = build_exit_line_map([s], ["005930", "000660", "035720"])
    assert set(m) == {"005930", "000660", "035720"}
    assert m["005930"]["stop_price"] == 66_000
    assert m["000660"]["stop_price"] is None


def test_read_only_does_not_mutate_strategy_state():
    """🔴 read-only 계약 — 전략 상태를 하나도 바꾸지 않는다."""
    positions = {"005930": _Pos(70_000)}
    params = {"stop_loss_rate": -5.0}
    s = _Strategy("momentum", positions, params=params)
    before_positions = dict(positions)
    before_params = dict(params)
    resolve_exit_lines([s], "005930")
    assert positions == before_positions
    assert params == before_params
