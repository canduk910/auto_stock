"""cycle423 리팩토링 카드 #6(④ N-e) — Red.

정본 = `_workspace/refactor/2026-10-09_review.md` 「카드 #6」. `GET /api/strategies/monitor`
응답에 전략별 `bought_today`(엔진 `_bought_today` 집합 — 그 속성이 있는 전략만)와
`sold_today`(`state.sold_today`, 모든 전략)를 **읍기 전용 복사본**(정렬 리스트)으로 싣는다.
프론트는 이 값으로 「오늘 매수함」·「오늘 매도함(당일 재매수 막힘)」 배지를 보인다
(`registry.is_ticker_blocked_for_buy` 의 당일매도 차단과 같은 의미).

| # | 계약 |
|---|---|
| N1 | `_bought_today` 가 있는 전략은 정렬된 리스트, 없는 전략은 `None`(빈 리스트와 구별 — "추적
     안 함" ≠ "오늘 0건") |
| N2 | `state.sold_today` 는 모든 전략이 갖는 필드라 항상 정렬된 리스트(빈 보유도 `[]`) |
| N3 | 읍기 전용 — 반환값은 새 리스트라 원본 set 을 고치지 않는다(`.clear()`·`.pop()` 등 호출 없음) |
| N4 | `_monitor_strategy_entry` 응답에 두 키가 실제로 실린다 |
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


class _FakeStrategy:
    """`_monitor_strategy_entry` 가 최소한으로 요구하는 속성만 — 다른 `_monitor_*` 헬퍼는
    `getattr` 기본값으로 비켜 간다(sid 를 scale 대상 밖으로 둬 market_unit 분기도 건드리지 않는다)."""

    def __init__(self, strategy_id: str, sold_today: set | None = None, bought_today: set | None = None):
        self.strategy_id = strategy_id
        self.state = SimpleNamespace(
            positions={}, pending_buys=set(),
            sold_today=sold_today if sold_today is not None else set(),
        )
        # 시장 유닛 대상 전략(kojiro 등)이 `_monitor_market_unit` 안에서 읍기만 한다 — 결측 스냅샷
        # 분기로 떨어지게 `config.params` 만 둔다(그 밖은 건드리지 않는다).
        self.config = SimpleNamespace(params={})
        if bought_today is not None:
            self._bought_today = bought_today


def _entry(strategy):
    from src.routes.strategies import _monitor_strategy_entry

    return _monitor_strategy_entry(strategy, strategy_id_today(), strategy_id_today().isoformat(), {}, _NullTickVolume())


def strategy_id_today():
    from datetime import date

    return date(2026, 10, 9)


class _NullTickVolume:
    def get_observed_acml_vol(self, ticker):  # pragma: no cover — tickers 집합이 비어 호출되지 않는다
        raise AssertionError("빈 종목 집합에서 호출되면 안 된다")


def test_n1_bought_today_present_sorted_when_attr_exists():
    strat = _FakeStrategy("kojiro", bought_today={"005930", "000660"})
    entry = _entry(strat)
    assert entry["bought_today"] == ["000660", "005930"]


def test_n1_bought_today_none_when_attr_absent():
    strat = _FakeStrategy("momentum")  # momentum 은 _bought_today 를 갖지 않는다
    entry = _entry(strat)
    assert entry["bought_today"] is None


def test_n2_sold_today_always_sorted_list():
    strat = _FakeStrategy("momentum", sold_today={"003160", "006120"})
    entry = _entry(strat)
    assert entry["sold_today"] == ["003160", "006120"]


def test_n2_sold_today_empty_list_when_no_sales():
    strat = _FakeStrategy("momentum")
    entry = _entry(strat)
    assert entry["sold_today"] == []


def test_n3_read_only_does_not_mutate_source_sets():
    sold = {"003160"}
    bought = {"005930"}
    strat = _FakeStrategy("kojiro", sold_today=sold, bought_today=bought)
    _entry(strat)
    assert sold == {"003160"}, "sold_today 원본 set 이 바뀌면 안 된다"
    assert bought == {"005930"}, "_bought_today 원본 set 이 바뀌면 안 된다"


def test_n4_keys_present_in_entry():
    strat = _FakeStrategy("momentum")
    entry = _entry(strat)
    assert "bought_today" in entry
    assert "sold_today" in entry
