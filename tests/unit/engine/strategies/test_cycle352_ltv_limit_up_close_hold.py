"""cycle352 — LTV 15:20 상한가 유지 확인 (`limit_up_close_hold_mode`).

정본 명세 = `_workspace/domain_consult/cycle352_ltv_limit_up_trailing.md` §5.
사용자 결정(2026-09-25) D5 F3① — B「15:20 상한가 유지 확인」채택.

행위 요약 — `check_force_clear()` 반환:
    [당일 모드 종목 전부]                                              # 현행 그대로
  + [상한가 모드 ∧ 당일 매수(not pos.is_next_day) ∧ 확인 모드 enforce
     ∧ 15:20 가격의 전일대비 등락률 < limit_up_threshold 인 종목]       # cycle352 신규

가격 출처는 모드 전환 판정과 같다 — `scanner.ticker_prices[t]["current_price"]` /
`scanner.ticker_prev_close[t]`. 판정 불가(가격 없음·0 이하·전일종가 없음·예외)는
전부 **보유**(hold_unknown)다. 새 판정 전체가 never-raise 다 — `check_force_clear`
가 실패해도 당일 모드 종목의 15:20 청산은 지켜져야 한다(`scheduler._force_clear_main_only`
가 try 없이 부른다).

T14(`test_long_tail_volatility.py::test_force_clear_excludes_limit_up_reached`)는
**이 파일에서 손대지 않는다** — 가격 미주입 → hold_unknown → 제외로 그대로 초록이어야
한다(별도로 그 파일을 실행해 확인한다).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.session import MarketBoard, session_tracker
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategy_base import Position, StrategyConfig

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_LTV_LOGGER = "src.engine.strategies.long_tail_volatility"
_CONFIG_MARKER = "[ltv_limit_up_close_config]"
_DECISION_MARKER = "[ltv_limit_up_close_decision]"

# 2026-09-25 15:00:00 KST 고정 — `is_next_day` 가 벽시계 날짜를 읽으므로 자정 경계
# flaky 를 없앤다. 시각 창 게이트는 이 사이클에 없다(15:20 호출 흐름에 얹을 뿐).
_FROZEN_UTC = "2026-09-25 06:00:00"


@pytest.fixture(autouse=True)
def _freeze():
    with freeze_time(_FROZEN_UTC):
        yield


@pytest.fixture
def ltv(monkeypatch):
    """VB/LTV 회귀 스위트와 격리된 독립 인스턴스 — `scanner` 전역 dict 를 통째로
    새 dict 로 치환한다(모듈 전역 누수 차단, `scheduler_env`/`order_env` 관례).
    """
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_names", {})
    monkeypatch.setattr(scanner, "ticker_prev_close", {})
    monkeypatch.setattr(scanner, "ticker_prices", {})
    monkeypatch.setattr(scanner, "ticker_last_tick", {})
    monkeypatch.setattr(session_tracker, "_active", frozenset())
    return LongTailVolatilityStrategy(
        StrategyConfig(strategy_id="long_tail_volatility", name="롱테일", weight=0.2)
    )


def _make_position(strategy, ticker="005930", buy_price=80000, *, next_day=False):
    today = datetime.now(_KST).date()
    pos = Position(
        ticker=ticker, buy_price=buy_price, quantity=1,
        order_no="O1", strategy_id=strategy.strategy_id,
        buy_date=(today - timedelta(days=1)) if next_day else today,
    )
    strategy.state.positions[ticker] = pos
    return pos


def _lines(caplog, marker: str) -> list[str]:
    """레벨(INFO 이상) + 로거 + prefix 3중 한정 (cycle286 `_marker_lines` 패턴)."""
    out = []
    for r in caplog.records:
        if r.name != _LTV_LOGGER or r.levelno < logging.INFO:
            continue
        msg = r.getMessage()
        if msg.startswith(marker) and "observer_failed" not in msg:
            out.append(msg)
    return out


def _field(line: str, name: str) -> str:
    import re

    m = re.search(rf"(?:^|\s){name}=(\S+)", line)
    assert m is not None, f"필드 `{name}=` 이 로그에 없다: {line!r}"
    return m.group(1)


# ---------------------------------------------------------------------------
# T1~T3 — 임계 판정 (가격 출처 · 경계)
# ---------------------------------------------------------------------------
def test_t1_exit_when_same_day_and_below_threshold(ltv, monkeypatch, caplog):
    """T1 — 당일 매수 · 상한가 모드 · 15:20 가격 전일대비 +24% → exit."""
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    monkeypatch.setitem(scanner.ticker_prices, "005930", {"current_price": 86800})  # +24%
    # buy_price 를 prev_close 와 다르게 둔다 — 구현이 실수로 매수가 기준으로 등락률을
    # 계산하면(M5) 이 값 때문에 판정이 달라져야 한다.
    _make_position(ltv, "005930", buy_price=59000)
    ltv._limit_up_reached.add("005930")

    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        result = ltv.check_force_clear()

    assert "005930" in result
    lines = _lines(caplog, _DECISION_MARKER)
    assert len(lines) == 1
    assert _field(lines[0], "decision") == "exit"
    assert _field(lines[0], "ticker") == "005930"


def test_t2_hold_when_price_still_at_limit_up(ltv, monkeypatch, caplog):
    """T2 — 같은 조건, 가격 = 상한가 근접(+29.9%) → hold(제외)."""
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    monkeypatch.setitem(scanner.ticker_prices, "005930", {"current_price": 90930})  # +29.9%
    _make_position(ltv, "005930", buy_price=59000)
    ltv._limit_up_reached.add("005930")

    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        result = ltv.check_force_clear()

    assert "005930" not in result
    lines = _lines(caplog, _DECISION_MARKER)
    assert len(lines) == 1
    assert _field(lines[0], "decision") == "hold"


def test_t3_boundary_ge_holds_lt_exits(ltv, monkeypatch):
    """T3 — 경계는 `>=` 면 보유, `<` 면 청산(전환 조건과 대칭, M1 가드).

    메모 §5.4 T3 그대로 — 임계는 리터럴 `29.0`, 경계는 정확히 +29.00% / +28.99%.
    "29.00%" 를 문자 그대로 재현하면 부동소수 표현 오차로 28.999999999999996 이
    나온다(`0.29` 는 이진수로 정확히 표현되지 않는다) — 그래서 구현이 `risk.on_tick`
    의 `prdy_ctrt` 와 같은 반올림(소수 둘째 자리)을 거친다. 이 테스트는 그 반올림
    덕에 **임계를 역산하지 않고** 문자 그대로의 29.0 로 검증한다.
    """
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    ltv.config.params["limit_up_threshold"] = 29.0
    _make_position(ltv, "005930", buy_price=59000)
    ltv._limit_up_reached.add("005930")

    # +29.00% 정확값 (70000 × 1.29) — 반올림 후 29.00, threshold(29.0) 이상 → 보유.
    monkeypatch.setitem(scanner.ticker_prices, "005930", {"current_price": 90300})
    assert "005930" not in ltv.check_force_clear(), "prdy == threshold(29.00%) 는 보유(>=)여야 한다"

    # +28.99% 정확값 (70000 × 1.2899) — 반올림 후 28.99, threshold(29.0) 미만 → 청산.
    monkeypatch.setitem(scanner.ticker_prices, "005930", {"current_price": 90293})
    assert "005930" in ltv.check_force_clear(), "prdy(28.99%) < threshold(29.00%) 는 청산이어야 한다"


# ---------------------------------------------------------------------------
# T4~T5 — 판정 불가 (가격·전일종가 결측)
# ---------------------------------------------------------------------------
def test_t4_hold_unknown_when_price_missing_or_zero(ltv, monkeypatch, caplog):
    """T4 — `ticker_prices` 에 종목 없음 / `current_price=0` → hold_unknown reason=no_price."""
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    monkeypatch.setitem(scanner.ticker_prev_close, "000660", 100000)
    # 005930: ticker_prices 자체에 없음
    _make_position(ltv, "005930", buy_price=59000)
    ltv._limit_up_reached.add("005930")
    # 000660: current_price=0 명시
    _make_position(ltv, "000660", buy_price=59000)
    ltv._limit_up_reached.add("000660")
    monkeypatch.setitem(scanner.ticker_prices, "000660", {"current_price": 0})

    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        result = ltv.check_force_clear()

    assert "005930" not in result
    assert "000660" not in result
    lines = {_field(ln, "ticker"): ln for ln in _lines(caplog, _DECISION_MARKER)}
    assert _field(lines["005930"], "decision") == "hold_unknown"
    assert _field(lines["005930"], "reason") == "no_price"
    assert _field(lines["000660"], "decision") == "hold_unknown"
    assert _field(lines["000660"], "reason") == "no_price"


def test_t5_hold_unknown_when_prev_close_missing(ltv, monkeypatch, caplog):
    """T5 — `ticker_prev_close` 없음 → hold_unknown reason=no_prev_close."""
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prices, "005930", {"current_price": 86800})
    _make_position(ltv, "005930", buy_price=59000)
    ltv._limit_up_reached.add("005930")

    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        result = ltv.check_force_clear()

    assert "005930" not in result
    lines = _lines(caplog, _DECISION_MARKER)
    assert len(lines) == 1
    assert _field(lines[0], "decision") == "hold_unknown"
    assert _field(lines[0], "reason") == "no_prev_close"


# ---------------------------------------------------------------------------
# T6~T7 — 대상 범위 (익일 제외 · 당일 모드 보존)
# ---------------------------------------------------------------------------
def test_t6_next_day_excluded_with_no_decision_marker(ltv, monkeypatch, caplog):
    """T6 — 상한가 모드 · `is_next_day` · 낮은 가격 → 제외(현행) · 판정 마커 없음."""
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    monkeypatch.setitem(scanner.ticker_prices, "005930", {"current_price": 71000})  # +1.4%
    _make_position(ltv, "005930", buy_price=59000, next_day=True)
    ltv._limit_up_reached.add("005930")

    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        result = ltv.check_force_clear()

    assert "005930" not in result
    assert _lines(caplog, _DECISION_MARKER) == [], "익일 보유 종목은 판정 마커가 없어야 한다"


def test_t7_day_mode_tickers_always_included_regardless_of_price(ltv, monkeypatch, caplog):
    """T7 — 당일 모드 종목(두 개) + 상한가 모드 종목 혼재 → 당일 모드는 가격 무관 전부 포함.

    day-mode 두 종목에는 일부러 "hold 판정이 나올" 가격(전일대비 임계 이상 상승)을
    심는다 — M8(당일 모드 종목도 가격으로 거르기) 이 `decision == "hold"` 인 종목을
    지우는 형태로 들어와도 이 값들이 그 실수를 드러내게 하려는 것이다(가격 데이터가
    아예 없어 hold_unknown 이 되는 것과는 다른 경로를 덮는다).
    """
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    monkeypatch.setitem(scanner.ticker_prices, "005930", {"current_price": 95000})  # +35.7% → hold
    _make_position(ltv, "005930", buy_price=80000)
    monkeypatch.setitem(scanner.ticker_prev_close, "000660", 100000)
    monkeypatch.setitem(scanner.ticker_prices, "000660", {"current_price": 140000})  # +40% → hold
    _make_position(ltv, "000660", buy_price=100000)
    # 상한가 모드 종목 — 가격 데이터 자체가 없다(hold_unknown 이어도 base 는 무관해야 함).
    _make_position(ltv, "123456", buy_price=50000)
    ltv._limit_up_reached.add("123456")

    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        result = ltv.check_force_clear()

    assert "005930" in result
    assert "000660" in result
    assert "123456" not in result


# ---------------------------------------------------------------------------
# T8~T9 — 모드 판독
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw_mode", ["off", " OFF "])
def test_t8_off_mode_excludes_all_limit_up_tickers(ltv, monkeypatch, raw_mode):
    """T8 — `limit_up_close_hold_mode="off"` / `" OFF "` → 상한가 모드 전부 제외
    = 현행(cycle352 이전)과 같은 목록."""
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    monkeypatch.setitem(scanner.ticker_prices, "005930", {"current_price": 86800})  # +24% (exit 조건)
    _make_position(ltv, "005930", buy_price=59000)
    ltv._limit_up_reached.add("005930")
    _make_position(ltv, "000660", buy_price=100000)  # 당일 모드
    ltv.config.params["limit_up_close_hold_mode"] = raw_mode

    result = ltv.check_force_clear()

    assert result == ["000660"], "off 모드는 현행 목록(당일 모드만)과 같아야 한다"


@pytest.mark.parametrize("raw_mode", ["enforce", "", None, 123])
def test_t9_unknown_or_non_off_values_fall_back_to_enforce(ltv, raw_mode):
    """T9 — 모드 값 `"enforce"`·`""`·`None`·`123` → 전부 enforce."""
    ltv.config.params["limit_up_close_hold_mode"] = raw_mode
    assert ltv._read_limit_up_close_hold_mode() == "enforce"


def test_t9b_key_deleted_falls_back_to_enforce(ltv):
    """T9 (연속) — 키 삭제 → enforce."""
    del ltv.config.params["limit_up_close_hold_mode"]
    assert ltv._read_limit_up_close_hold_mode() == "enforce"


# ---------------------------------------------------------------------------
# T10 — 임계는 파라미터에서 읽는다
# ---------------------------------------------------------------------------
def test_t10_threshold_is_read_from_params(ltv, monkeypatch):
    """T10 — `limit_up_threshold=25` 로 바꾸고 +26% → 제외(hold, 26 >= 25)."""
    from src.engine import scanner

    ltv.config.params["limit_up_threshold"] = 25.0
    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    monkeypatch.setitem(scanner.ticker_prices, "005930", {"current_price": 88200})  # +26%
    _make_position(ltv, "005930", buy_price=59000)
    ltv._limit_up_reached.add("005930")

    result = ltv.check_force_clear()

    assert "005930" not in result


# ---------------------------------------------------------------------------
# T11 — 가격 조회 예외 → never-raise
# ---------------------------------------------------------------------------
class _BoomMapping(dict):
    def get(self, *args, **kwargs):  # noqa: D401
        raise RuntimeError("boom — 가격 조회 실패 재현")


def test_t11_price_lookup_exception_is_absorbed(ltv, monkeypatch, caplog):
    """T11 — 가격 조회에서 예외가 나도 **예외 없이** 반환 + 당일 모드 종목은
    여전히 포함 + `reason=error`."""
    from src.engine import scanner

    monkeypatch.setattr(scanner, "ticker_prices", _BoomMapping())
    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    _make_position(ltv, "005930", buy_price=59000)
    ltv._limit_up_reached.add("005930")
    _make_position(ltv, "000660", buy_price=100000)  # 당일 모드 — 무관하게 보존돼야 함

    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        result = ltv.check_force_clear()  # 예외 없이 반환

    assert "000660" in result, "당일 모드 종목은 가격 조회 예외와 무관하게 청산 대상이어야 한다"
    assert "005930" not in result
    lines = _lines(caplog, _DECISION_MARKER)
    assert len(lines) == 1
    assert _field(lines[0], "decision") == "hold_unknown"
    assert _field(lines[0], "reason") == "error"


def test_t11b_emit_failure_does_not_change_behavior(ltv, monkeypatch, caplog):
    """M9 — 마커 emit 이 던져도(logger.info 자체가 예외) 행위는 그대로다."""
    import src.engine.strategies.long_tail_volatility as mod
    from src.engine import scanner

    monkeypatch.setitem(scanner.ticker_prev_close, "005930", 70000)
    monkeypatch.setitem(scanner.ticker_prices, "005930", {"current_price": 86800})  # +24%
    _make_position(ltv, "005930", buy_price=59000)
    ltv._limit_up_reached.add("005930")
    _make_position(ltv, "000660", buy_price=100000)

    def _boom_info(*args, **kwargs):
        raise RuntimeError("logger boom")

    monkeypatch.setattr(mod.logger, "info", _boom_info)

    with caplog.at_level(logging.DEBUG):
        result = ltv.check_force_clear()  # 예외 없이 반환

    assert "005930" in result  # emit 실패와 무관하게 exit 판정은 유지
    assert "000660" in result


class _RaisingIsNextDay:
    """`_evaluate_limit_up_close_hold` 의 per-ticker try **밖**에서 예외를 낸다.

    `_limit_up_close_hold_extra_clears` 가 `limit_up_same_day` 목록을 만드는
    list comprehension(`not self.state.positions[ticker].is_next_day`)이 유일하게
    자기 try 로 안 덮인 지점이다 — 그 실패는 `check_force_clear` 의 **바깥**
    try/except 만이 흡수해야 한다(M7 가드).
    """

    ticker = "999999"
    buy_price = 50000
    quantity = 1
    order_no = "O1"
    strategy_id = "long_tail_volatility"
    buy_date = None
    high_since_buy = 0

    @property
    def is_next_day(self):
        raise RuntimeError("boom — is_next_day 조회 실패")


def test_t11c_outer_guard_absorbs_extra_clears_exception(ltv):
    """M7 — `_limit_up_close_hold_extra_clears` 자체가 던져도(per-ticker try 밖)
    `check_force_clear` 의 바깥 try/except 가 흡수해 당일 모드 종목은 보존한다.

    이 시나리오는 `_evaluate_limit_up_close_hold` 의 자기 try 로는 못 막는다
    (그 함수 호출 전 단계에서 터진다) — `check_force_clear` 자체의 never-raise
    계약이 유일한 방어선임을 증명한다.
    """
    ltv.state.positions["999999"] = _RaisingIsNextDay()
    ltv._limit_up_reached.add("999999")
    _make_position(ltv, "005930", buy_price=59000)  # 당일 모드 — 무관하게 보존돼야 함

    result = ltv.check_force_clear()  # 예외 없이 반환

    assert "005930" in result, (
        "check_force_clear 의 바깥 try/except 가 없으면(또는 `return []` 로 좁혀지면) "
        "당일 모드 종목까지 사라진다"
    )


# ---------------------------------------------------------------------------
# T12 — 설정 카나리아
# ---------------------------------------------------------------------------
def test_t12_config_canary_emits_even_with_zero_holdings(ltv, caplog):
    """T12 — 보유 0 에서도 `[ltv_limit_up_close_config]` 1행."""
    with caplog.at_level(logging.INFO, logger=_LTV_LOGGER):
        result = ltv.check_force_clear()

    assert result == []
    lines = _lines(caplog, _CONFIG_MARKER)
    assert len(lines) == 1
    assert _field(lines[0], "mode") == "enforce"
    assert _field(lines[0], "limit_up_same_day") == "0"


# ---------------------------------------------------------------------------
# T13 — on_position_closed 와의 상호작용 (기존 계약 보존)
# ---------------------------------------------------------------------------
def test_t13_on_position_closed_skips_cooldown_for_limit_up_ticker(ltv):
    """T13 — B 로 청산된 종목의 `on_position_closed` → 쿨다운 미등록(`was_limit_up`)."""
    ticker = "005930"
    ltv._limit_up_reached.add(ticker)

    ltv.on_position_closed(ticker)

    assert ticker not in ltv._cooldown_until
    assert ticker not in ltv._limit_up_reached
