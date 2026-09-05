"""cycle258 Red — `strategy_base` 11 emit 헬퍼: 로거 사망 시 (a) 매수 수량 불변 (b) 흔적.

명세: 스크래치패드 `spec_cycle258_emit_cap_observer_trace.md` §1 (카드 #5 "추가 필요")
근거: `_workspace/refactor/2026-09-05_review.md` 카드 #5 형태 A —
      `strategy_base.py:727,764,838,864,935,1121,1150,1206,1237,1278,1312` 이
      전부 무흔적 `except Exception: pass` 다(11 사이트).

## 왜 두 축인가

- **SB-1(수량 불변)** — cycle242 R1/R2 가 봉인한 계약("행위는 cap 밖")의 전개.
  관측기가 어떤 이유로 죽어도 `_apply_budget_limit` 의 산출은 흔들리지 않는다.
  카드 #4/#5 의 리팩토링이 이 성질을 깨지 않았음을 11 사이트 전부에서 잰다.
  ⇒ **HEAD 에서 이미 GREEN** (특성화 가드 — 리팩토링을 보호하는 쪽).
- **SB-2(흔적)** — 지금은 무흔적 `pass` 라 "관측기가 항구적으로 깨졌는데 아무도
  모르는" 사각이 11곳에 있다. cycle237 C237-L2-1 결론(debug 단독조차 DB 미도달)
  을 이 파일에도 적용한다. ⇒ **HEAD 에서 RED**.

## 측정 방식

각 헬퍼마다 `logger.info`·`logger.warning` 을 **동시에** 죽이고(`logger.debug` 는
살려 둔다 — 흔적 채널) 헬퍼를 직접 호출한 뒤,
같은 입력의 **살아있는 로거 인스턴스**와 `_apply_budget_limit` 산출을 대조한다.
"""

from __future__ import annotations

import logging

import pytest
from freezegun import freeze_time

from src.engine import account_risk_watcher as arw_mod
from src.engine import strategy_base as sb_mod
from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

pytestmark = pytest.mark.unit

BUDGET = 774_640          # 2026-09-03 실측 kojiro 예산 (cycle242 픽스처 답습)
RATIO = 0.166
RISK = 0.005
TICKER = "000815"
PRICE = 405_500
ATR = 13_300


# ---------------------------------------------------------------------------
# 픽스처 — cycle233/242 `_MiniStrategy` 패턴 (로컬 복제, 타 테스트 모듈 import 금지)
# ---------------------------------------------------------------------------
class _MiniStrategy(StrategyBase):
    async def prepare(self):  # pragma: no cover
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return self._apply_budget_limit(0, current_price, ticker)


def _mini() -> _MiniStrategy:
    s = _MiniStrategy(
        StrategyConfig(
            strategy_id="kojiro",
            name="kojiro",
            params={
                "exchange": "KRX",
                "position_ratio": RATIO,
                "sizing_mode": "turtle",
                "risk_pct": RISK,
            },
        )
    )
    s.state.total_investment = BUDGET
    s._candidates = {TICKER: {"atr": ATR}}
    return s


# (헬퍼 이름, 호출 인자) — 11 사이트 전수. args/kwargs 는 각 헬퍼의 조기탈출
# 가드를 모두 통과해 **실제로 logger 를 부르는** 값으로 고른다.
_EMIT_CALLS: tuple[tuple[str, tuple, dict], ...] = (
    ("_emit_fallback_notional_capped", (TICKER,), dict(
        via_fallback=True, price=PRICE, atr=float(ATR), k=2.0,
        req_qty=3, capped_qty=1, budget=BUDGET, risk_pct=RISK)),
    ("_emit_fallback_cap_skipped", (TICKER, "no_atr", 1, PRICE), {}),
    ("_emit_fallback_cap_config", ("turtle", 2.0, BUDGET, RISK), {}),
    ("_emit_fallback_cap_clamped", (0.5, 1.0), {}),
    ("_emit_oversized_fallback", (TICKER, 1, PRICE), {}),
    ("_emit_ratio_notional_blocked", (TICKER,), dict(
        via_fallback=True, price=PRICE, cap=128_590, cutoff=321_475, k=2.5,
        req_qty=1, capped_qty=0, budget=BUDGET, pos_ratio=RATIO)),
    ("_emit_ratio_cap_skipped", (TICKER, "no_ratio", 1, PRICE), {}),
    ("_emit_ratio_cap_config", ("turtle", 2.5, BUDGET, RATIO, 128_590, 321_475), {}),
    ("_emit_ratio_cap_clamped", (25.0, 20.0), {}),
    ("_account_soft_gate_blocked", (TICKER,), {}),
    ("_emit_budget_clamp", (TICKER, 5, 1, 405_500), {}),
)
_EMIT_IDS = tuple(name for name, _a, _k in _EMIT_CALLS)

assert len(_EMIT_CALLS) == 11, "카드 #5 형태 A 는 11 사이트다 — 표가 어긋났다"


def _kill_emit_levels(monkeypatch):
    """`logger.info`/`logger.warning` 만 죽인다 — `debug`(흔적 채널)는 살려 둔다."""
    def _boom(*a, **k):
        raise RuntimeError("logger down")

    monkeypatch.setattr(sb_mod.logger, "info", _boom)
    monkeypatch.setattr(sb_mod.logger, "warning", _boom)


def _arm_soft_gate(monkeypatch):
    monkeypatch.setattr(arw_mod, "is_soft_gated", lambda: True)


def _invoke(s, name, args, kwargs, monkeypatch):
    if name == "_account_soft_gate_blocked":
        _arm_soft_gate(monkeypatch)
    return getattr(s, name)(*args, **kwargs)


# ===========================================================================
# SB-1 — 로거 사망 시 매수 수량 불변 (HEAD 에서 GREEN — 특성화/보호 가드)
# ===========================================================================
@freeze_time("2026-09-05 10:00:00+09:00")
@pytest.mark.parametrize(("name", "args", "kwargs"), _EMIT_CALLS, ids=_EMIT_IDS)
def test_c258_sb1_logger_death_keeps_quantity(monkeypatch, name, args, kwargs):
    """관측기가 죽어도 `_apply_budget_limit` 산출은 살아있는 로거와 **동일**하다.

    cycle242 R1/R2 격리 재현의 11 사이트 전개 — 관측 실패가 매수 수량을 바꾸는
    경로가 생기면(예: `emit_once` 가 예외를 흘리거나 캡 산출 순서를 건드리면)
    여기서 잡힌다.
    """
    baseline = _mini()._apply_budget_limit(0, PRICE, TICKER)

    s = _mini()
    _kill_emit_levels(monkeypatch)
    try:
        _invoke(s, name, args, kwargs, monkeypatch)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"{name}: 관측기 자기실패가 호출부로 전파됐습니다 ({exc!r}) — "
            "'행위는 cap 밖' 계약 위반"
        )
    got = s._apply_budget_limit(0, PRICE, TICKER)
    assert got == baseline, (
        f"{name}: 로거 사망 후 매수 수량이 {baseline} → {got} 로 바뀌었습니다"
    )
    assert isinstance(got, int) and not isinstance(got, bool), (
        f"{name}: 관문 반환이 int 가 아닙니다({type(got).__name__}) — "
        "`api/order.py` 가 `ORD_QTY='2.0'` 을 KIS 로 보냅니다(G-245 계약)"
    )


# ===========================================================================
# SB-2 — 로거 사망 시 흔적 (HEAD 에서 RED — 무흔적 `pass` 11곳)
# ===========================================================================
@freeze_time("2026-09-05 10:00:00+09:00")
@pytest.mark.parametrize(("name", "args", "kwargs"), _EMIT_CALLS, ids=_EMIT_IDS)
def test_c258_sb2_logger_death_leaves_a_trace(monkeypatch, caplog, name, args, kwargs):
    """무흔적 `pass` 금지 — 관측기가 항구적으로 깨져도 아무도 모르는 사각을 닫는다.

    구현 수단(`trace_observer_failure` 경유 / `emit_once` 내부 흡수)은 핀하지
    않고 **관측 가능한 사실**만 본다: 스택트레이스가 실린 로그 레코드 1건 이상.
    """
    s = _mini()
    _kill_emit_levels(monkeypatch)
    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        _invoke(s, name, args, kwargs, monkeypatch)

    assert any(r.exc_info for r in caplog.records), (
        f"{name}: 관측기 자기실패가 무흔적으로 삼켜졌습니다(형태 A) — cycle237 "
        "C237-L2-1 '도입 이전 무음과 구별 불가'. 기록: "
        f"{[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )


# ===========================================================================
# SB-3 — 게이트 전체 경로에서 로거 전면 사망 (info/warning/debug 동시)
# ===========================================================================
@freeze_time("2026-09-05 10:00:00+09:00")
@pytest.mark.parametrize("price", [PRICE, 220_000, 1_000, 10_000_000])
def test_c258_sb3_total_logger_death_keeps_gate_quantity(monkeypatch, price):
    """흔적 채널까지 전부 죽어도 관문은 살아야 한다 (never-raise 의 최종 방어선)."""
    baseline = _mini()._apply_budget_limit(0, price, TICKER)

    def _boom(*a, **k):
        raise RuntimeError("logger fully down")

    s = _mini()
    for level in ("debug", "info", "warning", "error"):
        monkeypatch.setattr(sb_mod.logger, level, _boom)
    try:
        got = s._apply_budget_limit(0, price, TICKER)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"로거 전면 사망이 관문 밖으로 전파됐습니다: {exc!r}")
    assert got == baseline, f"price={price}: 수량 {baseline} → {got}"
