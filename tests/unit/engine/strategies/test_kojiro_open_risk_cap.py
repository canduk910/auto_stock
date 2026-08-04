"""kojiro Σ 오픈리스크 캡 — 회귀 가드.

## 왜 개수 캡만으로는 부족한가

터틀의 유닛 캡이 통제하려던 대상은 **Σ 오픈리스크**이고, 유닛 개수는 그 프록시일
뿐이다. 프록시는 "1유닛 = 상수 리스크" 일 때만 정확한데 우리 구현에선 셋이 깨뜨린다:

1. **수량 절삭** — 소액 계좌에서 1.4주 → 1주 (실측 08-04 002790, 목표의 29%)
2. **`hard_stop_pct` −8% 캡** — `atr_ratio > 4%` 면 2ATR(>8%)이 잘려 리스크가 감소
3. **사이징 혼재** — flip 이전 position_ratio 포지션이 함께 존재

실측(08-04, 예산 690,111): "6포지션 = 6유닛" 이라면 총리스크 41,407원(예산 6.0%)
이어야 하나 실제는 **22,390원(3.2%) = 3.2유닛**, 포지션별 편차 8.3배.
⇒ 개수를 세는 것으로는 총리스크가 통제되지 않는다.

## 규약

- **개수 캡(`max_positions`)은 유지**하고 리스크 캡을 **추가**한다. 리스크 캡만 두면
  저ATR 종목으로 포지션 수가 무한정 늘 수 있다(개별 리스크는 작아도 상관·운영 부담).
  터틀도 유닛 캡과 시장군 캡을 병행했다. 개수 + 명목(예산) + 리스크 삼중.
- 포지션 리스크 = `qty × (buy_price − 실효손절선)`,
  실효손절선 = `max(_stop_floor 또는 buy − stop_atr×ATR, buy × (1+hard_stop_pct/100))`.
  `_stop_floor` 는 tighten-only 라 보유가 길수록 리스크가 **감소**한다(실제 노출 반영).
- **매수 게이트 전용** — 청산/손절/트레일링은 절대 차단하지 않는다.
- **fail-open**: ATR 결측 → `hard_stop_pct` 기준 추정, 예외 → 통과, `0` → 비활성.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pytest
from freezegun import freeze_time

from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
BUDGET = 690_111


def _kojiro(*, budget: int = BUDGET, **extra):
    params = {"max_open_risk_pct": 4.5, **extra}
    s = KojiroStrategy(
        StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.6, params=params),
    )
    s.state.total_investment = budget
    return s


def _hold(s, ticker: str, buy: int, qty: int, atr: float | None = None):
    s.state.positions[ticker] = Position(
        ticker=ticker, buy_price=buy, quantity=qty, order_no="O", strategy_id="kojiro",
    )
    if atr is not None:
        s._candidates[ticker] = {"atr": atr, "stage": 1, "prev_close": buy}


def _make_candidate(s, ticker: str, prev_close: int, atr: float = 1000.0):
    s._candidates[ticker] = {"atr": atr, "stage": 1, "prev_close": prev_close,
                             "sector": None, "name": ticker}


# ---------------------------------------------------------------------------
# R-1 — 오픈리스크 계산: 실효손절선 = max(2ATR선, −8%선)
# ---------------------------------------------------------------------------
def test_open_risk_uses_tighter_of_atr_and_pct_stop():
    s = _kojiro()
    # atr_ratio 4.91% → 2ATR = 9.83% > 8% → −8% backstop 이 실효
    _hold(s, "002790", 25_150, 1, atr=1235.6)
    assert s._open_risk_won() == pytest.approx(25_150 - int(25_150 * 0.92), abs=1)

    s2 = _kojiro()
    # atr_ratio 2% → 2ATR = 4% < 8% → 2ATR 이 실효
    _hold(s2, "000001", 10_000, 1, atr=200.0)
    assert s2._open_risk_won() == pytest.approx(400, abs=1)


def test_open_risk_sums_all_positions_and_scales_with_qty():
    s = _kojiro()
    _hold(s, "000001", 10_000, 3, atr=200.0)     # 3 × 400 = 1,200
    _hold(s, "000002", 20_000, 1, atr=400.0)     # 1 × 800 =   800
    assert s._open_risk_won() == pytest.approx(2_000, abs=2)


def test_open_risk_zero_when_no_positions():
    assert _kojiro()._open_risk_won() == 0


# ---------------------------------------------------------------------------
# R-2 — `_stop_floor` 반영 (tighten-only → 실제 노출 감소)
# ---------------------------------------------------------------------------
def test_open_risk_reflects_tightened_stop_floor():
    s = _kojiro()
    _hold(s, "000001", 10_000, 1, atr=200.0)     # base 손절 9,600 → 리스크 400
    base = s._open_risk_won()
    s._stop_floor["000001"] = 9_800              # 트레일링으로 상향된 손절선
    assert s._open_risk_won() < base
    assert s._open_risk_won() == pytest.approx(200, abs=1)


def test_stop_floor_below_pct_line_does_not_loosen_risk():
    """floor 가 −8%선보다 낮아도 리스크가 −8% 초과로 커지지 않는다."""
    s = _kojiro()
    _hold(s, "000001", 10_000, 1, atr=200.0)
    s._stop_floor["000001"] = 1_000              # 비정상적으로 낮은 값
    assert s._open_risk_won() <= 10_000 - int(10_000 * 0.92) + 1


# ---------------------------------------------------------------------------
# R-3 — ATR 결측 fail-open: hard_stop_pct 기준 추정
# ---------------------------------------------------------------------------
def test_open_risk_falls_back_to_pct_when_atr_missing():
    s = _kojiro()
    s.state.positions["000001"] = Position(
        ticker="000001", buy_price=10_000, quantity=2, order_no="O", strategy_id="kojiro",
    )  # _candidates 미등록 = ATR 결측
    assert s._open_risk_won() == pytest.approx(2 * (10_000 - int(10_000 * 0.92)), abs=2)


# ---------------------------------------------------------------------------
# R-4 — 매수 게이트: 캡 도달 시 NONE, 미달 시 통과
# ---------------------------------------------------------------------------
def _buy_ready(s, ticker="005930", prev_close=10_000):
    """시간창·갭·붕괴 게이트를 전부 통과하는 상태로 세팅."""
    _make_candidate(s, ticker, prev_close)
    return ticker


@freeze_time("2026-08-04 00:10:00")  # UTC 00:10 = KST 09:10 (창 내)
def test_buy_blocked_when_open_risk_at_cap():
    s = _kojiro(max_open_risk_pct=1.0, max_positions=99)   # 캡 = 예산의 1.0% = 6,901원
    _hold(s, "000001", 100_000, 1, atr=20_000.0)           # 리스크 8,000 > 6,901
    t = _buy_ready(s)
    assert s.check_buy_signal(t, 10_100, 10_000) == Signal.NONE


@freeze_time("2026-08-04 00:10:00")
def test_buy_allowed_when_open_risk_below_cap():
    s = _kojiro(max_open_risk_pct=4.5, max_positions=99)   # 캡 = 31,055원
    _hold(s, "000001", 10_000, 1, atr=200.0)               # 리스크 400
    t = _buy_ready(s)
    assert s.check_buy_signal(t, 10_100, 10_000) == Signal.BUY


@freeze_time("2026-08-04 00:10:00")
def test_cap_zero_disables_gate():
    s = _kojiro(max_open_risk_pct=0, max_positions=99)
    _hold(s, "000001", 100_000, 1, atr=20_000.0)
    t = _buy_ready(s)
    assert s.check_buy_signal(t, 10_100, 10_000) == Signal.BUY


@freeze_time("2026-08-04 00:10:00")
def test_gate_inactive_when_budget_zero():
    """예산 0(미배분) 이면 캡 판정 불가 → fail-open."""
    s = _kojiro(budget=0, max_open_risk_pct=4.5, max_positions=99)
    t = _buy_ready(s)
    assert s.check_buy_signal(t, 10_100, 10_000) == Signal.BUY


# ---------------------------------------------------------------------------
# R-5 — 개수 캡과 독립 (둘 다 각각 차단)
# ---------------------------------------------------------------------------
@freeze_time("2026-08-04 00:10:00")
def test_position_count_cap_still_applies_independently():
    s = _kojiro(max_open_risk_pct=99.0, max_positions=1)   # 리스크 캡은 사실상 무제한
    _hold(s, "000001", 10_000, 1, atr=200.0)
    t = _buy_ready(s)
    assert s.check_buy_signal(t, 10_100, 10_000) == Signal.NONE, "개수 캡은 그대로 작동"


# ---------------------------------------------------------------------------
# R-6 — 청산 경로는 절대 차단하지 않는다 (매수 게이트 전용)
# ---------------------------------------------------------------------------
def test_exit_signal_never_gated_by_open_risk():
    s = _kojiro(max_open_risk_pct=0.01)                    # 캡 극단적으로 낮게
    _hold(s, "000001", 10_000, 1, atr=200.0)
    s.state.positions["000001"].high_since_buy = 10_000
    # −8% 관통 → 캡과 무관하게 손절이 나와야 한다
    assert s.check_exit_signal("000001", 9_100, 10_000) == Signal.STOP_LOSS


def test_check_exit_signal_source_has_no_open_risk_reference():
    import inspect
    src = inspect.getsource(KojiroStrategy.check_exit_signal)
    assert "_open_risk_won" not in src and "max_open_risk_pct" not in src, (
        "청산이 리스크 캡을 참조하면 안 된다 — 캡 도달 시 손절이 막히는 사고 경로"
    )


# ---------------------------------------------------------------------------
# R-7 — fail-open: 계산 예외 시 매수 통과
# ---------------------------------------------------------------------------
@freeze_time("2026-08-04 00:10:00")
def test_gate_fails_open_on_exception(monkeypatch):
    s = _kojiro(max_open_risk_pct=0.001, max_positions=99)
    _hold(s, "000001", 10_000, 1, atr=200.0)

    def boom(*a, **k):
        raise RuntimeError("계산 실패")

    monkeypatch.setattr(KojiroStrategy, "_open_risk_won", boom)
    t = _buy_ready(s)
    assert s.check_buy_signal(t, 10_100, 10_000) == Signal.BUY


# ---------------------------------------------------------------------------
# R-8 — 파라미터 규약
# ---------------------------------------------------------------------------
def test_max_open_risk_pct_default_present():
    assert KojiroStrategy.DEFAULT_PARAMS.get("max_open_risk_pct") == 4.5


def test_max_open_risk_pct_excluded_from_param_ranges():
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES
    assert "max_open_risk_pct" not in PARAM_RANGES, "리스크 정체성 상수 — AI 튜닝 금지"
    assert "max_open_risk_pct" not in INT_PARAMS


# ---------------------------------------------------------------------------
# R-9 — 08-04 실측 재현: 현 6포지션 Σ리스크 ≈ 예산의 3.2%
# ---------------------------------------------------------------------------
def test_reproduces_live_open_risk_2026_08_04():
    s = _kojiro()
    for tk, buy, qty, atr in (
        ("111770", 86_800, 1, 4865.8), ("236200", 48_200, 1, 2547.6),
        ("316140", 33_050, 2, 1549.6), ("002810", 23_400, 2, 863.0),
        ("079160", 5_230, 2, 244.7),   ("002790", 25_150, 1, 1235.6),
    ):
        _hold(s, tk, buy, qty, atr=atr)
    risk = s._open_risk_won()
    assert 22_000 <= risk <= 22_800, f"실측 22,390원 대비 이탈: {risk}"
    assert 3.0 <= risk / BUDGET * 100 <= 3.4
