"""cycle397 — 잔고 화면의 매입일(최초 매입일) leaf 회귀.

사용자 요청(2026-10-02) = "잔고내역에 매입일을 표기하자. 혹시 여러날짜에 걸쳐
매수했다면(피라미딩으로 인해) 최초매입일로 표시."

🔴 이 그물은 **값**을 잰다. 「필드가 응답에 있다」만 보면 오늘 날짜로 채우거나,
여러 원천이 갈릴 때 더 늦은 날짜(최근)를 골라도 전부 초록이다.
"""
from __future__ import annotations

from datetime import date

from src.engine.position_buy_date import merge_buy_date, resolve_engine_buy_dates


class _Pos:
    def __init__(self, buy_date):
        self.buy_date = buy_date


class _State:
    def __init__(self, positions: dict):
        self.positions = positions


class _Strategy:
    def __init__(self, strategy_id: str, positions: dict):
        self.strategy_id = strategy_id
        self.state = _State(positions)


# ── resolve_engine_buy_dates ─────────────────────────────────────────────


def test_resolves_buy_date_from_single_strategy_position():
    s = _Strategy("kojiro", {"005930": _Pos(date(2026, 9, 20))})
    out = resolve_engine_buy_dates([s])
    assert out == {"005930": "2026-09-20"}


def test_multiple_tickers_across_strategies():
    s1 = _Strategy("kojiro", {"005930": _Pos(date(2026, 9, 20))})
    s2 = _Strategy("donchian_swing", {"000660": _Pos(date(2026, 9, 25))})
    out = resolve_engine_buy_dates([s1, s2])
    assert out == {"005930": "2026-09-20", "000660": "2026-09-25"}


def test_same_ticker_in_two_strategies_picks_earlier_date():
    """비정상 상태(두 전략이 같은 종목)라도 더 이른 날짜를 — 「최초」 규약."""
    s1 = _Strategy("kojiro", {"005930": _Pos(date(2026, 9, 25))})
    s2 = _Strategy("donchian_swing", {"005930": _Pos(date(2026, 9, 20))})
    out = resolve_engine_buy_dates([s1, s2])
    assert out == {"005930": "2026-09-20"}


def test_non_date_buy_date_is_skipped():
    s = _Strategy("kojiro", {"005930": _Pos("이상한값")})
    out = resolve_engine_buy_dates([s])
    assert out == {}


def test_strategy_without_positions_dict_is_skipped():
    class _Broken:
        strategy_id = "x"
        state = None

    out = resolve_engine_buy_dates([_Broken()])
    assert out == {}


def test_exception_during_iteration_absorbed():
    class _Boom:
        @property
        def state(self):
            raise RuntimeError("boom")

    out = resolve_engine_buy_dates([_Boom()])
    assert out == {}


def test_empty_strategies_returns_empty_map():
    assert resolve_engine_buy_dates([]) == {}


# ── merge_buy_date ───────────────────────────────────────────────────────


def test_merge_prefers_engine_when_db_missing():
    assert merge_buy_date("2026-09-20", None) == "2026-09-20"


def test_merge_falls_back_to_db_when_engine_missing():
    assert merge_buy_date(None, date(2026, 9, 18)) == "2026-09-18"


def test_merge_accepts_db_value_as_iso_string_too():
    assert merge_buy_date(None, "2026-09-18") == "2026-09-18"


def test_merge_picks_earlier_of_two_sources():
    """피라미딩 대비 「최초 매입일」 규약 — 엔진이 더 이르면 엔진 값."""
    assert merge_buy_date("2026-09-15", date(2026, 9, 20)) == "2026-09-15"
    # DB 가 더 이르면 DB 값
    assert merge_buy_date("2026-09-20", date(2026, 9, 15)) == "2026-09-15"


def test_merge_both_missing_returns_none_not_today():
    assert merge_buy_date(None, None) is None


def test_merge_rejects_malformed_values():
    assert merge_buy_date("", None) is None
    assert merge_buy_date(123, None) is None  # type: ignore[arg-type]
