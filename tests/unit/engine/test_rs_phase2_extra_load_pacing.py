"""추가 적재 속도 상한 — 시세 조회 한도(초당 20)는 주문·잔고와 같은 전역 한도라
16:00~20:00 애프터마켓 동안 추가 적재는 평균 초당 약 2.5회 이하로 간다(보고서 사실 대조 지적, 2026-10-14)."""
import asyncio

import pytest

from src.engine import fundamental_load_tasks as flt

_MAX_CALLS_PER_SEC = 2.5


def test_quarterly_pace_at_most_limit():
    # 종목당 5 TR(finance 내부 TR 사이 sleep 포함) 뒤 종목 sleep — 호출 시간을 0 으로 쳐도 상한 이하
    assert 5 / flt._QUARTERLY_TICKER_SLEEP_SECS <= _MAX_CALLS_PER_SEC


def test_single_call_pace_at_most_limit():
    assert 1 / flt._CALL_SLEEP_SECS <= _MAX_CALLS_PER_SEC


@pytest.mark.asyncio
async def test_fetch_window_sleeps_call_pace(monkeypatch):
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    async def fake_opinion(ticker, a, b):
        return []

    monkeypatch.setattr(flt.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(flt.io_api, "inquire_invest_opinion", fake_opinion)
    from datetime import date
    await flt._fetch_window("005930", date(2026, 1, 1), date(2026, 3, 1))
    assert slept == [flt._CALL_SLEEP_SECS]
