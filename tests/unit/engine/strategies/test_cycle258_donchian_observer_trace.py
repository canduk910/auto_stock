"""cycle258 tester 시정 — donchian 잔여 관측기 2곳의 자기 실패 흔적 (C258-T3).

근거: cycle258 적대 검증 C258-T3 — `_emit_days_held_fallback`(형태 A `pass`) ·
`_emit_days_held_observation`(형태 B 무가드 `logger.debug(exc_info=True)`) 이 카드 #5
표에서 누락된 채 남아 있었다. 후자는 **debug 로거 자신이 죽으면 2차 예외가
`check_exit_signal` 밖으로 전파**됐다(proof_don.py — 400/400 RAISED 실측).

## 봉인하는 것

- D-1 `logger.debug` 까지 죽은 환경에서 `check_exit_signal` 이 예외 없이 완주하고
      반환 시그널이 살아있는 로거 인스턴스와 **동일**(미발화 NONE · 시간청산 STOP_LOSS).
- D-2 `_emit_days_held_observation` 자기 실패(cap 앞 단계에서 반복 폭발) →
      `[days_held_observe_failed] observer_failed key=<ticker>` WARNING **1회/ticker/일**
      + exc_info debug 매회 + KST 익일 재발화 + 정상 관측 키 무접촉.
- D-3 `_emit_days_held_fallback` 자기 실패 → 같은 정책(WARNING 1 + debug) + 무전파.
- D-4 소스 AST: `DonchianSwingStrategy` 의 모든 `_emit_*` 메서드 except 핸들러는
      `trace_observer_failure(..., dest_logger=logger)` 를 부른다 — `pass` 단독·
      직접 `logger.debug` 핸들러 0(카드 #5 정책이 파일 전체에서 단일).
"""

from __future__ import annotations

import ast
import datetime as _dt
import logging
from pathlib import Path

import pytest
from freezegun import freeze_time

import src.engine.strategies.donchian_swing as _mod
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit

_LOGGER = "src.engine.strategies.donchian_swing"
_SRC = Path(__file__).resolve().parents[4] / "src" / "engine" / "strategies" / "donchian_swing.py"
_OBS = "[days_held_observe]"
_OBS_FAILED = "[days_held_observe_failed]"
_FB = "[days_held_fallback]"
_FB_FAILED = "[days_held_fallback_failed]"
D = _dt.date
_W_1721 = [D(2026, 8, 17), D(2026, 8, 18), D(2026, 8, 19), D(2026, 8, 20), D(2026, 8, 21)]


# ---------------------------------------------------------------------------
# rig (사이클 224 파일과 동형 — 구성만 복제, 모듈 import 결합 없음)
# ---------------------------------------------------------------------------
def _mk(n_days: int = 2, **params) -> DonchianSwingStrategy:
    cfg = StrategyConfig(
        strategy_id="donchian_swing", name="도치안", weight=0.2,
        params={"sizing_mode": "position_ratio", "breakout_fail_n_days": n_days, **params},
    )
    s = DonchianSwingStrategy(cfg)
    s.state.total_investment = 100_000_000
    return s


def _arm(s, ticker="005930", buy_date=None, buy_price=10_000, breakout_high=11_000):
    pos = Position(ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
                   strategy_id="donchian_swing", buy_date=buy_date)
    pos.high_since_buy = buy_price
    s.state.positions[ticker] = pos
    s._candidates[ticker] = {"prev_close": buy_price, "atr": 0, "ema60": 0,
                             "donchian_high": breakout_high}
    if breakout_high:
        s._breakout_high[ticker] = breakout_high
    return pos


def _cache(s, days: list) -> None:
    s._trading_days = set(days)


def _recs(caplog, marker: str, level: int | None = None):
    return [r for r in caplog.records
            if marker in r.getMessage() and (level is None or r.levelno == level)]


class _PoisonInfo:
    """지정 마커의 `info` 만 폭발시키는 로거 래퍼 — 나머지는 실 로거로 위임."""

    def __init__(self, real, *markers: str):
        self._real = real
        self._markers = markers

    def __getattr__(self, name):
        return getattr(self._real, name)

    def info(self, msg, *args, **kwargs):
        rendered = str(msg)
        if any(m in rendered for m in self._markers):
            raise RuntimeError("관측 로그 폭발 (인위)")
        return self._real.info(msg, *args, **kwargs)


def _boom(*a, **k):
    raise RuntimeError("logger down (인위)")


# ===========================================================================
# D-1 — debug 로거까지 사망: check_exit_signal 무전파 + 시그널 동일
# ===========================================================================
@pytest.mark.parametrize(
    "cache, buy_date, expected",
    [
        (_W_1721, D(2026, 8, 21), Signal.NONE),           # 미발화 경로
        (_W_1721[:-1], D(2026, 8, 19), Signal.STOP_LOSS),  # 시간청산 발화 경로
    ],
    ids=["none_path", "time_exit_path"],
)
def test_d1_debug_logger_death_does_not_escape_check_exit_signal(
    monkeypatch, cache, buy_date, expected,
):
    live = _mk(n_days=2)
    _cache(live, cache)
    _arm(live, buy_date=buy_date)
    hostile = _mk(n_days=2)
    _cache(hostile, cache)
    _arm(hostile, buy_date=buy_date)

    real = _mod.logger
    with freeze_time("2026-08-24 10:30:00+09:00"):
        ref = live.check_exit_signal("005930", 9_800, 9_900)
        assert ref == expected, "탐지기 self-test — 살아있는 로거 기준 시그널"

        # 관측 info 폭발(1차) + debug 사망(2차 — 옛 B 형태가 새던 지점)
        monkeypatch.setattr(real, "debug", _boom)
        monkeypatch.setattr(_mod, "logger", _PoisonInfo(real, _OBS, "days_held_observe"))
        try:
            got = hostile.check_exit_signal("005930", 9_800, 9_900)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(
                f"관측기 2차 예외가 `check_exit_signal` 밖으로 샜다: {exc!r} — "
                "무가드 `logger.debug` 핸들러(B 형태)의 결함 재현"
            )
    assert got == ref, f"로거 사망이 청산 시그널을 바꿨다: {ref} → {got}"


# ===========================================================================
# D-2 — 관측기 자기 실패 흔적: WARNING 1회/ticker/일 + debug 매회 + 롤오버
# ===========================================================================
def test_d2_observe_failure_trace_is_capped_per_day_and_rolls_over(caplog):
    s = _mk(n_days=2)
    pos = _arm(s, buy_date=D(2026, 8, 21))
    _cache(s, _W_1721)
    # cap 판정(`should_emit`) **앞** 단계에서 폭발 → 매 호출 실패(반복 실패 시나리오).
    s._breakout_high["005930"] = "not-an-int"

    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        with freeze_time("2026-08-24 10:00:00+09:00"):
            for _ in range(5):
                s._emit_days_held_observation("005930", pos, 9_500)   # 예외가 새면 여기서 실패
        assert len(_recs(caplog, _OBS_FAILED, logging.WARNING)) == 1, (
            "실패 WARNING 이 1회/ticker/일 cap 을 벗어났다(또는 0 = 무흔적)"
        )
        dbg = _recs(caplog, _OBS_FAILED, logging.DEBUG)
        assert len(dbg) == 5 and all(r.exc_info for r in dbg), (
            "debug 스택은 매 실패마다 exc_info 와 함께 남아야 한다"
        )
        assert not _recs(caplog, _OBS), "실패했는데 정상 관측 로그가 남으면 안 된다"
        # 정상 관측 키(`ticker|armed`/`ticker|disarmed`) 무접촉 — 실패 흔적 키는 분리돼 있다
        assert s._days_held_observe_logged.should_emit("005930|armed") is True
        assert s._days_held_observe_logged.should_emit("005930|disarmed") is True

        with freeze_time("2026-08-25 10:00:00+09:00"):
            s._emit_days_held_observation("005930", pos, 9_500)
    assert len(_recs(caplog, _OBS_FAILED, logging.WARNING)) == 2, (
        "KST 익일에 실패 WARNING 이 재발화하지 않았다"
    )
    msg = _recs(caplog, _OBS_FAILED, logging.WARNING)[0].getMessage()
    assert "observer_failed" in msg and "key=005930" in msg, f"운영 grep 축 부재: {msg!r}"


# ===========================================================================
# D-3 — 폴백 관측기 자기 실패: WARNING + debug, 무전파
# ===========================================================================
def test_d3_fallback_failure_leaves_trace_and_never_raises(caplog, monkeypatch):
    s = _mk(n_days=2)
    _cache(s, [])
    monkeypatch.setattr(_mod, "logger", _PoisonInfo(_mod.logger, _FB, "days_held_fallback"))

    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        with freeze_time("2026-08-24 10:00:00+09:00"):
            try:
                s._emit_days_held_fallback("005930", 3, 2, 11_000)
                s._emit_days_held_fallback("000660", 3, 2, 11_000)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"폴백 관측기 예외가 호출부로 샜다: {exc!r}")

    warns = _recs(caplog, _FB_FAILED, logging.WARNING)
    assert len(warns) == 2, (
        f"`{_FB_FAILED}` WARNING {len(warns)}행 — ticker 당 1행(무흔적 `pass` 면 0)"
    )
    assert {("key=005930" in r.getMessage(), "key=000660" in r.getMessage()) for r in warns} == {
        (True, False), (False, True),
    }
    dbg = _recs(caplog, _FB_FAILED, logging.DEBUG)
    assert len(dbg) == 2 and all(r.exc_info for r in dbg)
    assert not _recs(caplog, _FB), "실패했는데 폴백 관측 로그가 남으면 안 된다"


# ===========================================================================
# D-4 — 소스 AST: 모든 `_emit_*` except 핸들러 = trace_observer_failure(dest_logger=logger)
# ===========================================================================
def test_d4_every_emit_helper_except_handler_uses_trace_observer_failure():
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DonchianSwingStrategy")
    emitters = [n for n in cls.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("_emit_")]
    assert len(emitters) >= 8, f"`_emit_*` 관측기 {len(emitters)}개 — 대상 식별 실패"

    offenders: list[str] = []
    checked = 0
    for fn in emitters:
        for h in ast.walk(fn):
            if not isinstance(h, ast.ExceptHandler):
                continue
            checked += 1
            calls = [c for c in ast.walk(h) if isinstance(c, ast.Call)]
            trace_calls = [
                c for c in calls
                if (getattr(c.func, "id", None) == "trace_observer_failure"
                    or getattr(c.func, "attr", None) == "trace_observer_failure")
            ]
            if not trace_calls:
                offenders.append(f"{fn.name}:{h.lineno} (핸들러 본문 = "
                                 f"{[type(b).__name__ for b in h.body]}, 호출 = "
                                 f"{[ast.unparse(c.func) for c in calls][:2]})")
                continue
            for c in trace_calls:
                kw = {k.arg: k.value for k in c.keywords}
                dl = kw.get("dest_logger")
                if not (isinstance(dl, ast.Name) and dl.id == "logger"):
                    offenders.append(f"{fn.name}:{c.lineno} dest_logger=logger 누락 "
                                     "(로거 정체성 — caplog 스코프 회귀 호환)")
    assert checked >= 8, f"except 핸들러 {checked}개 — 검사 대상 부족"
    assert not offenders, (
        "관측기 자기 실패 정책(카드 #5)이 파일 안에서 갈라졌다 — 무흔적 `pass` 또는 "
        f"무가드 `logger.debug` 핸들러: {offenders}"
    )
