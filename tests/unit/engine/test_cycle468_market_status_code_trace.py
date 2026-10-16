"""cycle468 — 시장 대표 종목 장운영 코드 변화 관측 기록 (사용자 결정 2026-10-16 「(가)」).

업무정리 대조로 KIS 숫자 코드 182(「서킷브레이크 장중동시마감」)·175/185(해제)의 실제 뜻과
도착 순서가 확정되지 않았다. 판정 로직은 바꾸지 않고, 대표 종목의 코드가 바뀔 때마다
「시장·출처·코드·직전 코드·시각·바뀐 뒤 상태」 한 줄을 남겨 다음 CB·임시정지 때 순서를 확정한다.

- 정상 장운영 코드끼리의 변화 = INFO(보관 2일) · 한쪽이라도 정상 밖 코드 = WARNING(보관 30일).
- 같은 코드 반복은 기록하지 않는다. (시장, 출처)마다 하루 상한이 있다.
- 기록이 실패해도 상태 판정은 그대로 돈다.
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timedelta, timezone

import pytest

from src.api.market_operation import parse_market_op_payload
from src.engine import market_cb_state as mcb
from src.engine import market_operation_monitor as mon

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
_LOGGER = "src.engine.market_cb_state"
_MARK = "[market_status_code_trace]"


@pytest.fixture(autouse=True)
def _reset():
    mon.reset_market_op_state()
    mcb.reset_market_cb_state()
    yield
    mon.reset_market_op_state()
    mcb.reset_market_cb_state()


def _frame(ticker: str, code: str, at: datetime):
    ev = parse_market_op_payload(ticker, f"{ticker}^N^(null)^{code}^^^^55^N^N^")
    ev = dataclasses.replace(ev, received_at=at)
    mon.record_market_op_event(ev)


def _t(h, m, s=0, day=15):
    return datetime(2026, 10, day, h, m, s, tzinfo=KST)


def _traces(caplog):
    return [r for r in caplog.records if r.name == _LOGGER and r.getMessage().startswith(_MARK)]


def test_normal_code_change_is_info_once_per_change(caplog):
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        _frame("005930", "110", _t(8, 30))
        _frame("005930", "110", _t(8, 31))   # 같은 코드 반복 = 기록 없음
        _frame("005930", "112", _t(9, 0))
    tr = _traces(caplog)
    assert [r.levelno for r in tr] == [logging.INFO, logging.INFO]
    assert tr[0].getMessage() == (
        "[market_status_code_trace] market=KOSPI source=ST code=110 prev=- ts=08:30:00 state=NORMAL"
    )
    assert "code=112 prev=110 ts=09:00:00 state=NORMAL" in tr[1].getMessage()


def test_cb_code_change_is_warning_with_resulting_state(caplog):
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        _frame("196170", "112", _t(11, 0))
        _frame("196170", "174", _t(11, 5))
        _frame("196170", "182", _t(11, 25))
        _frame("196170", "112", _t(11, 40))   # 정상 코드로 돌아와도 직전이 정상 밖이라 WARNING
    tr = _traces(caplog)
    assert [r.levelno for r in tr] == [logging.INFO, logging.WARNING, logging.WARNING, logging.WARNING]
    assert "market=KOSDAQ source=ST code=174 prev=112 ts=11:05:00 state=CB_ACTIVE" in tr[1].getMessage()
    assert "code=182 prev=174" in tr[2].getMessage()


def test_markets_and_sources_are_tracked_separately(caplog):
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        _frame("196170", "AF8", _t(12, 23))
        _frame("196170", "174", _t(12, 23, 1))
        _frame("005930", "174", _t(12, 23, 2))
        _frame("196170", "AF8", _t(12, 24))   # UN 출처 직전 코드 그대로 = 기록 없음
    msgs = [r.getMessage() for r in _traces(caplog)]
    assert len(msgs) == 3
    assert "market=KOSDAQ source=UN code=AF8 prev=-" in msgs[0]
    assert "market=KOSDAQ source=ST code=174 prev=-" in msgs[1]
    assert "market=KOSPI source=ST code=174 prev=-" in msgs[2]


def test_non_rep_ticker_is_not_traced(caplog):
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        _frame("053450", "174", _t(11, 0))
    assert _traces(caplog) == []


def test_daily_cap_per_market_source_then_summary_once(caplog):
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        for i in range(mcb.TRACE_DAILY_MAX + 5):
            _frame("005930", "110" if i % 2 else "112", _t(9, 0, 0) + timedelta(seconds=i))
    msgs = [r.getMessage() for r in _traces(caplog)]
    assert len(msgs) == mcb.TRACE_DAILY_MAX + 1
    assert msgs[-1] == (
        f"[market_status_code_trace] market=KOSPI source=ST cap_reached=1 limit={mcb.TRACE_DAILY_MAX}"
    )


def test_new_day_resets_prev_and_cap(caplog):
    _frame("005930", "112", _t(15, 0))
    caplog.clear()  # 앞 테스트가 로거 레벨을 INFO 로 남긴 작업자에서는 위 줄도 잡힌다
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        _frame("005930", "112", _t(8, 30, day=16))
    tr = _traces(caplog)
    assert len(tr) == 1 and "prev=- " in tr[0].getMessage()


def test_trace_failure_does_not_change_state_handling(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("trace boom")

    monkeypatch.setattr(mcb, "_trace_code", _boom)
    _frame("196170", "174", _t(11, 0))
    assert mcb.get_market_cb_summary(_t(11, 1))["markets"]["KOSDAQ"]["state"] == "CB_ACTIVE"
