"""cycle387 Red — 종목 차트용 KIS 기간별시세 날짜 창 페이징 (`src/api/period_chart.py`).

명세: `_workspace/red/cycle387_stock_chart_spec.md` §1.3 · §1.4 · §1.5 · §3.1 (S1~S26)
사용자 요청(2026-09-28): 잔고·주문체결내역·매매손익에서 종목을 더블클릭하면 KLineChart 로
최근 5년 일봉/주봉/월봉을 보여 준다. 우리 `stock_master_daily` 는 390일만 보관하므로
KIS `FHKST03010100` 을 **시세 풀(`kis_get_quote`)** 로 직접 읽는다.

## 이 파일이 봉인하는 계약 (이름·형태가 다르면 FAIL)

`src/api/period_chart.py`
  * `fetch_candle_chart(ticker, period="D", years=5, *, now_kst=None) -> CandleChart`
  * `ChartBusyError(Exception)` · `_is_provisional(last_date: date, period, now_kst) -> bool`
  * `_reset_state_for_tests()` — 캐시·inflight·세마포어·잠금을 **새로 만든다**
  * seam: 모듈 속성 `kis_get_quote`(from-import) · `_monotonic` · `asyncio.sleep`(모듈 이름으로 참조)
  * 상수 `_MAX_CALLS_PER_FETCH`(dict, 호출 시점에 읽는다) · `_QUEUE_WAIT_SECS`(호출 시점에 읽는다)

KIS 가짜는 「(DATE_1, DATE_2) 구간 안 **최신 100봉을 최신순으로**」 주는 합성 달력이다
(평일 + 몇 개의 공휴일). 응답 모양은 정본 `docs/kis/domestic-stock-quote.md:5582-5596` 그대로 —
숫자가 전부 **문자열**, `mod_yn`·`flng_cls_code` 포함.

## 금기 (가드 설계 금기 2026-09-05)
* caplog 단언은 `levelno >= WARNING` ∧ 접두어로만 한정한다(CI 루트 로거는 DEBUG).
* 실제 KIS 에 닿지 않는다 — S26 도 respx 가 httpx 전송 계층을 가로챈다.
* 시계는 `_monotonic` 주입, 날짜는 `now_kst` 주입(벽시계 비의존).

RED: `src/api/period_chart.py` 부재 → `pc` 픽스처가 import 에서 실패해 전 케이스 ERROR.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
DAILY_PRICE_URL = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
TR_ID = "FHKST03010100"

#: 기준 시각 — 2026-09-28(월) 10:00 KST(장중). 5년 D 구간 = 2021-09-28 ~ 2026-09-28.
NOW_MON_1000 = datetime(2026, 9, 28, 10, 0, tzinfo=KST)
TODAY = NOW_MON_1000.date()

#: 합성 달력의 휴장일(평일) — 창 경계 근처에 구멍을 만들어 커서가 「그 날짜 − 1일」 이
#: 휴장일일 때도 겹침·구멍이 없는지 함께 잰다.
HOLIDAYS = frozenset({
    date(2026, 9, 24), date(2026, 9, 25), date(2026, 1, 1), date(2025, 12, 25),
    date(2025, 10, 3), date(2025, 10, 6), date(2025, 10, 7), date(2025, 10, 8),
    date(2024, 10, 1),
})

_REAL_SLEEP = asyncio.sleep
BAR_KEYS = {"date", "open", "high", "low", "close", "volume", "amount"}
CHART_KEYS = {
    "ticker", "name", "period", "years", "adjusted", "market", "start_date", "end_date",
    "bars", "complete", "incomplete_reason", "last_bar_provisional", "dropped_bars",
    "kis_calls", "cached", "fetched_at",
}


# ─────────────────────────────────────────────────────────────────────────────
# 합성 달력 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _parse(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _trading_days(lo: date, hi: date, holidays: frozenset = HOLIDAYS) -> list[date]:
    out: list[date] = []
    d = lo
    while d <= hi:
        if d.weekday() < 5 and d not in holidays:
            out.append(d)
        d += timedelta(days=1)
    return out


def _price_row(d: date, *, bump: int = 0) -> dict[str, str]:
    """KIS output2 한 행 — 정본 응답 예시처럼 숫자가 전부 문자열이다."""
    base = 50_000 + (d.toordinal() % 400) * 10 + bump
    vol = 100_000 + d.toordinal() % 1000
    return {
        "stck_bsop_date": _ymd(d),
        "stck_clpr": str(base),
        "stck_oprc": str(base - 100),
        "stck_hgpr": str(base + 300),
        "stck_lwpr": str(base - 300),
        "acml_vol": str(vol),
        "acml_tr_pbmn": str(vol * base),
        "flng_cls_code": "00",
        "prtt_rate": "0.00",
        "mod_yn": "N",
        "prdy_vrss_sign": "3",
        "prdy_vrss": "0",
        "revl_issu_reas": "",
    }


def _envelope(rows: list[dict], *, name: Optional[str] = "삼성전자", ticker: str = "005930") -> dict:
    out1: dict[str, str] = {"stck_shrn_iscd": ticker, "stck_prpr": "71800", "prdy_vrss": "0"}
    if name is not None:
        out1["hts_kor_isnm"] = name
    return {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "msg1": "정상처리 되었습니다.",
        "output1": out1,
        "output2": rows,
        # base._request_via_quote_pool 이 붙이는 키(실제 응답 모양 재현).
        "_response_headers": {"tr_cont": ""},
    }


@dataclass
class Clock:
    """`period_chart._monotonic` 대체 — 테스트가 시간을 직접 옮긴다."""

    t: float = 10_000.0

    def __call__(self) -> float:
        return self.t


@dataclass
class _KisBase:
    """`kis_get_quote(url, tr_id, params)` 가짜 공통부 — 호출 기록·동시성 계측·게이트·시계."""

    calls: list = field(default_factory=list)
    fail_on: dict = field(default_factory=dict)          # {호출 순번(1부터): 예외}
    gate: Optional[asyncio.Event] = None                   # 이 이벤트가 설 때까지 응답 보류
    gate_ticker: Optional[str] = None                      # 게이트를 걸 종목(None = 전부)
    entered: Optional[asyncio.Event] = None                # 게이트 대상 호출이 들어오면 set
    clock: Optional[Clock] = None
    clock_step: float = 0.0                                # 호출 1건마다 시계를 옮길 초
    events: Optional[list] = None
    yield_inside: bool = False                             # 호출 도중 제어권을 넘긴다(동시성 계측)
    inflight: int = 0
    max_inflight: int = 0
    call_times: list = field(default_factory=list)       # 호출이 들어온 순간의 시계(간격 계측)

    async def __call__(self, url: str, tr_id: str, params: Optional[dict] = None, **kwargs: Any) -> dict:
        params = dict(params or {})
        self.calls.append((url, tr_id, params))
        self.call_times.append(self.clock.t if self.clock is not None else None)
        n = len(self.calls)
        ticker = params.get("FID_INPUT_ISCD")
        if self.events is not None:
            self.events.append(("kis", ticker))
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            gated = self.gate is not None and (self.gate_ticker is None or ticker == self.gate_ticker)
            if gated:
                if self.entered is not None:
                    self.entered.set()
                await self.gate.wait()
            if self.yield_inside:
                for _ in range(3):
                    await _REAL_SLEEP(0)
            if self.clock is not None:
                self.clock.t += self.clock_step
            exc = self.fail_on.get(n)
            if exc is not None:
                raise exc
            return self.respond(n, params)
        finally:
            self.inflight -= 1

    def respond(self, n: int, params: dict) -> dict:  # pragma: no cover - 하위 클래스
        raise NotImplementedError

    def calls_for(self, ticker: str) -> list:
        return [c for c in self.calls if c[2].get("FID_INPUT_ISCD") == ticker]


@dataclass
class CalendarKis(_KisBase):
    """합성 달력 — 구간 안 최신 100 버킷을 최신순으로 준다."""

    today: date = TODAY
    listing: date = date(1990, 1, 2)
    last_day: Optional[date] = None      # 최신 봉 날짜(기본 today) — 새벽 시각의 잠정 판정용
    week_anchor: str = "mon"             # "mon" = ISO 주 월요일 · "last" = 그 주 마지막 거래일
    month_anchor: str = "first"          # "first" = 그 달 첫 거래일 · "last" = 마지막 거래일
    holidays: frozenset = HOLIDAYS
    name: Optional[str] = "삼성전자"
    stuck: bool = False                  # S14 — DATE_2 를 무시하고 매번 같은 100봉
    overlap: bool = False                # S9 — 둘째 창부터 앞 창의 가장 오래된 봉을 겹쳐(값을 바꿔) 준다

    def _latest(self) -> date:
        return self.last_day or self.today

    def respond(self, n: int, params: dict) -> dict:
        d1 = _parse(params["FID_INPUT_DATE_1"])
        d2 = _parse(params["FID_INPUT_DATE_2"])
        period = params["FID_PERIOD_DIV_CODE"]
        hi = min(d2, self._latest())
        if self.stuck:
            hi = self._latest()
        if self.overlap and n >= 2:
            later = _trading_days(d2 + timedelta(days=1), self._latest(), self.holidays)
            if later:
                hi = later[0]
        days = _trading_days(max(d1, self.listing), hi, self.holidays)
        buckets: dict[Any, list[date]] = {}
        for d in days:
            if period == "D":
                key: Any = d
            elif period == "W":
                key = d.isocalendar()[:2]
            elif period == "M":
                key = (d.year, d.month)
            else:  # pragma: no cover - 명세 밖 기간
                raise AssertionError(f"period {period!r}")
            buckets.setdefault(key, []).append(d)
        anchors: list[date] = []
        for key, ds in buckets.items():
            if period == "D":
                anchors.append(ds[0])
            elif period == "W":
                anchors.append(_monday(ds[0]) if self.week_anchor == "mon" else max(ds))
            else:
                anchors.append(min(ds) if self.month_anchor == "first" else max(ds))
        anchors.sort(reverse=True)
        anchors = anchors[:100]
        rows = []
        for a in anchors:
            bump = 7 if (self.overlap and n >= 2 and a > d2) else 0
            rows.append(_price_row(a, bump=bump))
        return _envelope(rows, name=self.name, ticker=params.get("FID_INPUT_ISCD", ""))


@dataclass
class ScriptedKis(_KisBase):
    """호출 순번별로 준비한 output2 행을 그대로 준다(정규화·경계 검증용)."""

    script: list = field(default_factory=list)
    name: Optional[str] = "삼성전자"

    def respond(self, n: int, params: dict) -> dict:
        rows = self.script[n - 1] if n - 1 < len(self.script) else []
        return _envelope(list(rows), name=self.name, ticker=params.get("FID_INPUT_ISCD", ""))


# ─────────────────────────────────────────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def pc():
    """`src.api.period_chart` — 테스트마다 캐시·inflight·세마포어를 새로 만든다."""
    try:
        mod = importlib.import_module("src.api.period_chart")
    except ModuleNotFoundError as exc:
        pytest.fail(f"src/api/period_chart.py 부재 (cycle387 Red) — {exc}")
    mod._reset_state_for_tests()
    yield mod
    mod._reset_state_for_tests()


@dataclass
class Rig:
    pc: Any
    monkeypatch: pytest.MonkeyPatch
    clock: Clock
    sleeps: list
    events: list

    def install(self, kis: _KisBase) -> _KisBase:
        if kis.clock is None:
            kis.clock = self.clock
        kis.events = self.events
        self.monkeypatch.setattr(self.pc, "kis_get_quote", kis)
        return kis

    async def fetch(self, ticker: str = "005930", period: str = "D", years: int = 5, now: datetime = NOW_MON_1000):
        return await self.pc.fetch_candle_chart(ticker, period, years, now_kst=now)


@pytest.fixture
def rig(pc, monkeypatch) -> Rig:
    clock = Clock()
    sleeps: list = []
    events: list = []

    async def fake_sleep(delay, *args, **kwargs):
        sleeps.append(delay)
        events.append(("sleep", delay))
        if delay and delay > 0:
            clock.t += delay       # 쉰 만큼 시계가 간다(간격 계측이 실제 시간 흐름과 같아진다)
        await _REAL_SLEEP(0)

    monkeypatch.setattr(pc, "_monotonic", clock)
    monkeypatch.setattr(pc.asyncio, "sleep", fake_sleep)
    return Rig(pc=pc, monkeypatch=monkeypatch, clock=clock, sleeps=sleeps, events=events)


def _j(chart) -> dict:
    """라우트가 싣는 것과 같은 JSON 모양(`model_dump(mode="json")`)으로 잰다."""
    return chart.model_dump(mode="json")


def _dates(j: dict) -> list[str]:
    return [b["date"] for b in j["bars"]]


def _warnings(caplog, prefix: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)
    ]


# ═════════════════════════════════════════════════════════════════════════════
# S1 — 첫 호출 인자
# ═════════════════════════════════════════════════════════════════════════════

async def test_s1_first_call_uses_quote_pool_krx_adjusted_params(rig):
    """S1 — (DAILY_PRICE_URL, "FHKST03010100", 정확한 6키) · 시장 J · 수정주가 0."""
    from src.api import condition

    kis = rig.install(CalendarKis())
    await rig.fetch("005930", "D", 5)

    url, tr_id, params = kis.calls[0]
    assert url == condition.DAILY_PRICE_URL == DAILY_PRICE_URL
    assert tr_id == TR_ID, "FH 접두사 TR 은 실전·모의 동일 — get_tr_id 를 거치면 VH 로 깨진다"
    assert params == {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": "005930",
        "FID_INPUT_DATE_1": "20210928",
        "FID_INPUT_DATE_2": "20260928",
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0",
    }


# ═════════════════════════════════════════════════════════════════════════════
# S2~S5 — 일봉 커서 페이징 · 멈춤 조건
# ═════════════════════════════════════════════════════════════════════════════

async def test_s2_daily_five_years_pages_backward_with_fixed_start(rig):
    """S2 — 호출 수 = ceil(N/100) · DATE_1 고정 · DATE_2 = 직전 oldest − 1일 · 오름차순·중복 0."""
    kis = rig.install(CalendarKis())
    expected = _trading_days(date(2021, 9, 28), TODAY)
    n = len(expected)
    assert n % 100 != 0, f"전제 — 합성 달력 봉수 {n} 이 100 의 배수면 이 케이스가 S4 와 섞인다"

    j = _j(await rig.fetch("005930", "D", 5))

    assert len(kis.calls) == math.ceil(n / 100)
    assert {c[2]["FID_INPUT_DATE_1"] for c in kis.calls} == {"20210928"}, "시작일은 모든 창에서 고정"
    assert kis.calls[0][2]["FID_INPUT_DATE_2"] == "20260928"
    for k in range(1, len(kis.calls)):
        prev_resp = kis.respond(k, kis.calls[k - 1][2])
        oldest_prev = min(_parse(r["stck_bsop_date"]) for r in prev_resp["output2"])
        assert kis.calls[k][2]["FID_INPUT_DATE_2"] == _ymd(oldest_prev - timedelta(days=1)), (
            f"{k + 1}번째 창의 종료일은 직전 창 oldest({oldest_prev}) − 1일이어야 한다"
        )

    dates = _dates(j)
    assert dates == sorted(dates), "오름차순(오래된 것 먼저)"
    assert len(dates) == len(set(dates)) == n
    assert dates[0] >= "2021-09-28"
    assert dates[-1] == "2026-09-28"
    assert dates == [d.isoformat() for d in expected]
    assert j["complete"] is True
    assert j["incomplete_reason"] is None
    assert j["kis_calls"] == len(kis.calls)
    assert j["cached"] is False
    assert j["start_date"] == "2021-09-28"
    assert j["end_date"] == "2026-09-28"
    assert j["period"] == "D" and j["years"] == 5
    assert j["adjusted"] is True and j["market"] == "J"
    assert set(j) == CHART_KEYS


async def test_s3_listed_under_five_years_stops_on_short_window_without_extra_call(rig):
    """S3 — 2025-03-10 상장: 마지막 창이 100 미만에서 멈춘다(빈 호출 추가 0)."""
    kis = rig.install(CalendarKis(listing=date(2025, 3, 10)))
    n = len(_trading_days(date(2025, 3, 10), TODAY))
    assert n % 100 != 0

    j = _j(await rig.fetch("005930", "D", 5))

    assert len(kis.calls) == math.ceil(n / 100), "100 미만 창 뒤에 빈 호출을 한 번 더 하면 안 된다"
    assert len(j["bars"]) == n
    assert j["bars"][0]["date"] == "2025-03-10"
    assert j["complete"] is True
    assert j["incomplete_reason"] is None


async def test_s4_exact_multiple_of_100_reaching_start_stops_without_extra_call(rig):
    """S4 — 봉수가 정확히 200 이고 oldest == start → 3번째 호출 없이 멈춤(멈춤 #5)."""
    now = datetime(2026, 9, 29, 10, 0, tzinfo=KST)   # 화 — 1년 전 2025-09-29(월) = 거래일
    start = date(2025, 9, 29)
    recent = _trading_days(start + timedelta(days=1), now.date())[-199:]
    keep = {start, *recent}
    holidays = frozenset(d for d in _trading_days(start, now.date(), frozenset()) if d not in keep)
    kis = rig.install(CalendarKis(today=now.date(), holidays=holidays))

    j = _j(await rig.fetch("005930", "D", 1, now=now))

    assert kis.calls[0][2]["FID_INPUT_DATE_1"] == "20250929"
    assert len(j["bars"]) == 200
    assert j["bars"][0]["date"] == "2025-09-29"
    assert len(kis.calls) == 2, f"시작일에 닿았는데 호출이 {len(kis.calls)}회 — 빈 창을 한 번 더 부르면 안 된다"
    assert j["complete"] is True


async def test_s5_first_window_empty_returns_empty_complete(rig):
    """S5 — 첫 응답 빈 목록 → bars=[], complete=True, 호출 1."""
    kis = rig.install(ScriptedKis(script=[[]]))
    j = _j(await rig.fetch("005930", "D", 5))
    assert j["bars"] == []
    assert j["complete"] is True
    assert len(kis.calls) == 1
    assert j["last_bar_provisional"] is False


# ═════════════════════════════════════════════════════════════════════════════
# S6~S8 — 주봉·월봉 버킷
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("anchor", ["mon", "last"], ids=["S6_monday_dated", "S7_period_end_dated"])
async def test_s6_s7_weekly_cursor_is_previous_sunday_whatever_the_bar_date(rig, anchor):
    """S6·S7 — 주봉: start=2021-09-27(월) · 호출 3 · 2번째 DATE_2 = 1번째 oldest 주의 전 주 **일요일**.

    KIS 가 주봉 날짜를 주의 첫날로 찍든(S6) 마지막 거래일로 찍든(S7) 같은 커서·같은 결과여야
    한다 — 버킷(ISO 주)으로 다루면 둘 다 맞는다. oldest − 1일(= 목요일)을 커서로 쓰면 같은 주를
    다시 받는다(S7 에서 잡힌다).
    """
    kis = rig.install(CalendarKis(week_anchor=anchor))

    j = _j(await rig.fetch("005930", "W", 5))

    assert kis.calls[0][2]["FID_INPUT_DATE_1"] == "20210927", "W 시작 = 그 주 월요일"
    assert kis.calls[0][2]["FID_PERIOD_DIV_CODE"] == "W"
    assert len(kis.calls) == 3
    first = kis.respond(1, kis.calls[0][2])
    oldest1 = min(_parse(r["stck_bsop_date"]) for r in first["output2"])
    second_end = _parse(kis.calls[1][2]["FID_INPUT_DATE_2"])
    assert second_end == _monday(oldest1) - timedelta(days=1)
    assert second_end.weekday() == 6, f"2번째 종료일 {second_end} 은 일요일이어야 한다"

    weeks = [date.fromisoformat(d).isocalendar()[:2] for d in _dates(j)]
    assert len(weeks) == len(set(weeks)), "ISO 주 중복 0"
    assert len(weeks) == 262
    assert _dates(j) == sorted(_dates(j))
    assert j["complete"] is True
    assert j["start_date"] == "2021-09-27"


async def test_s8_monthly_single_call_from_first_of_month(rig):
    """S8 — 월봉: start=2021-09-01 · 61봉 → 호출 1 · (년,월) 중복 0."""
    kis = rig.install(CalendarKis())

    j = _j(await rig.fetch("005930", "M", 5))

    assert len(kis.calls) == 1
    assert kis.calls[0][2]["FID_INPUT_DATE_1"] == "20210901"
    assert kis.calls[0][2]["FID_PERIOD_DIV_CODE"] == "M"
    months = [d[:7] for d in _dates(j)]
    assert len(months) == len(set(months)) == 61
    assert j["start_date"] == "2021-09-01"
    assert j["complete"] is True


# ═════════════════════════════════════════════════════════════════════════════
# S9·S10 — 병합·정규화
# ═════════════════════════════════════════════════════════════════════════════

async def test_s9_overlapping_windows_keep_newer_window_value(rig):
    """S9 — 창끼리 겹치는 봉은 버킷당 1개, **먼저 받은(더 최신) 창의 값**이 남는다."""
    kis = rig.install(CalendarKis(listing=date(2025, 3, 10), overlap=True))
    n = len(_trading_days(date(2025, 3, 10), TODAY))

    j = _j(await rig.fetch("005930", "D", 5))

    dates = _dates(j)
    assert len(dates) == len(set(dates)) == n
    assert len(kis.calls) >= 2
    for b in j["bars"]:
        want = int(_price_row(date.fromisoformat(b["date"]))["stck_clpr"])
        assert b["close"] == want, f"{b['date']} 은 겹친 뒤 창의 값({b['close']})이 이겼다 — 먼저 받은 값이 남아야 한다"


async def test_s10_normalization_ints_keys_dates_and_drops(rig):
    """S10 — 문자열→정수 · 키 정확히 7개 · YYYY-MM-DD · 가격 0 행·미래 행·시작 전 행 제거 + dropped_bars."""
    zero = _price_row(date(2026, 9, 25))
    zero.update({"stck_oprc": "0", "stck_hgpr": "0", "stck_lwpr": "0", "mod_yn": "Y"})
    empty_amount = _price_row(date(2026, 9, 23))
    empty_amount.update({"acml_vol": "", "acml_tr_pbmn": ""})
    placeholder = {k: "" for k in _price_row(date(2026, 9, 22))}
    rows = [
        _price_row(date(2026, 9, 29)),   # today(09-28) 이후 → 버림
        _price_row(date(2026, 9, 28)),
        zero,                            # 가격 0(mod_yn Y) → 버림
        _price_row(date(2026, 9, 24)),
        empty_amount,                    # 거래량·대금 빈 값 → 0 (봉은 남는다)
        placeholder,                     # 날짜 없는 placeholder → 세지 않는다
        _price_row(date(2021, 9, 27)),   # start(2021-09-28) 이전 → 버림
    ]
    kis = rig.install(ScriptedKis(script=[rows]))

    j = _j(await rig.fetch("005930", "D", 5))

    assert len(kis.calls) == 1
    assert _dates(j) == ["2026-09-23", "2026-09-24", "2026-09-28"]
    assert j["dropped_bars"] == 3, "가격 0 · 미래 · 시작 전 = 3 (날짜 없는 placeholder 는 봉이 아니다)"
    for b in j["bars"]:
        assert set(b) == BAR_KEYS
        for k in BAR_KEYS - {"date"}:
            assert type(b[k]) is int, f"{k}={b[k]!r} 는 JSON 정수여야 한다(문자열·float 금지)"
    src = _price_row(date(2026, 9, 28))
    last = j["bars"][-1]
    assert last == {
        "date": "2026-09-28",
        "open": int(src["stck_oprc"]),
        "high": int(src["stck_hgpr"]),
        "low": int(src["stck_lwpr"]),
        "close": int(src["stck_clpr"]),
        "volume": int(src["acml_vol"]),
        "amount": int(src["acml_tr_pbmn"]),
    }
    first = j["bars"][0]
    assert first["volume"] == 0 and first["amount"] == 0


async def test_s10b_placeholder_rows_do_not_count_toward_100(rig):
    """S10b — 날짜 있는 행 99 + placeholder 3 → 100 미만이므로 한 번에 멈춘다."""
    days = _trading_days(date(2026, 1, 1), TODAY)[-99:]
    rows = [_price_row(d) for d in reversed(days)] + [{"stck_bsop_date": ""}] * 3
    kis = rig.install(ScriptedKis(script=[rows, [_price_row(date(2025, 12, 1))]]))

    j = _j(await rig.fetch("005930", "D", 5))

    assert len(kis.calls) == 1
    assert len(j["bars"]) == 99
    assert j["complete"] is True


async def test_s10c_zero_price_row_still_counts_toward_100(rig):
    """S10c — 날짜 있는 100행 중 1행이 가격 0 → 「100행」 이므로 다음 창을 부른다."""
    days = _trading_days(date(2025, 12, 1), TODAY)[-100:]
    rows = [_price_row(d) for d in reversed(days)]
    rows[50].update({"stck_oprc": "0", "stck_hgpr": "0", "stck_lwpr": "0", "mod_yn": "Y"})
    older_days = _trading_days(date(2025, 11, 1), days[0] - timedelta(days=1))[-50:]
    older = [_price_row(d) for d in reversed(older_days)]   # 50행(< 100) → 둘째 창에서 멈춘다
    kis = rig.install(ScriptedKis(script=[rows, older]))

    j = _j(await rig.fetch("005930", "D", 5))

    assert len(kis.calls) == 2, "가격 0 행도 KIS 가 준 행이다 — 100 계산에 넣는다"
    assert j["dropped_bars"] == 1
    assert len(j["bars"]) == 99 + len(older)


@pytest.mark.parametrize(
    ("raw_name", "want"),
    [("  삼성전자 ", "삼성전자"), ("", None), (None, None)],
    ids=["strip", "blank_is_null", "missing_is_null"],
)
async def test_s10d_name_from_output1_stripped_or_null(rig, raw_name, want):
    """S10d — `name` = 첫 호출 output1.hts_kor_isnm(strip, 비면 null)."""
    rig.install(ScriptedKis(script=[[_price_row(date(2026, 9, 28))]], name=raw_name))
    j = _j(await rig.fetch("005930", "D", 5))
    assert j["name"] == want


# ═════════════════════════════════════════════════════════════════════════════
# S11·S12 — 잠정 봉 판정 (cycle386: 06:00 KST 경계, 값은 고치지 않는다)
# ═════════════════════════════════════════════════════════════════════════════

def _at(y, m, d, hh, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=KST)


@pytest.mark.parametrize(
    ("last_date", "period", "now", "want"),
    [
        # S11 — 일봉
        (date(2026, 9, 28), "D", _at(2026, 9, 28, 10), True),     # 월 10:00 오늘 봉(장중)
        (date(2026, 9, 28), "D", _at(2026, 9, 29, 3), True),      # 화 03:00 월요일 봉(아직 애프터 값)
        (date(2026, 9, 28), "D", _at(2026, 9, 29, 5, 59), True),  # 06:00 직전
        (date(2026, 9, 28), "D", _at(2026, 9, 29, 6, 0), False),  # 06:00 경계 = 확정
        (date(2026, 9, 28), "D", _at(2026, 9, 29, 7), False),     # 화 07:00
        (date(2026, 10, 2), "D", _at(2026, 10, 3, 3), True),      # 토 03:00 금요일 봉
        (date(2026, 10, 2), "D", _at(2026, 10, 3, 7), False),     # 토 07:00
        # S12 — 주봉(날짜가 주 첫날이든 마지막 거래일이든 같은 답)
        (date(2026, 9, 28), "W", _at(2026, 10, 4, 12), False),    # 일 12:00 지난주 주봉
        (date(2026, 10, 2), "W", _at(2026, 10, 4, 12), False),
        (date(2026, 9, 28), "W", _at(2026, 9, 30, 10), True),     # 수 10:00 이번 주 주봉
        (date(2026, 9, 30), "W", _at(2026, 9, 30, 10), True),
        # S12 — 월봉
        (date(2026, 9, 1), "M", _at(2026, 9, 30, 21), True),      # 9/30 21:00 9월 월봉
        (date(2026, 9, 30), "M", _at(2026, 9, 30, 21), True),
        (date(2026, 9, 1), "M", _at(2026, 10, 1, 7), False),      # 10/1 07:00 9월 월봉
        (date(2026, 9, 30), "M", _at(2026, 10, 1, 7), False),
    ],
)
def test_s11_s12_is_provisional_pure(pc, last_date, period, now, want):
    """S11·S12 — `_is_provisional(last_date, period, now_kst)`: 마지막 봉 버킷 안에
    「평일 d ≥ (now − 6시간).date()」 가 있으면 True."""
    assert pc._is_provisional(last_date, period, now) is want


async def test_s11b_fetch_flags_today_bar_provisional_but_keeps_kis_values(rig):
    """S11b — 장중 조회의 마지막 봉 = 잠정 True. 값은 KIS 가 준 그대로(고치거나 버리지 않는다)."""
    rig.install(CalendarKis(listing=date(2026, 6, 1)))
    j = _j(await rig.fetch("005930", "D", 5))
    assert j["last_bar_provisional"] is True
    last = j["bars"][-1]
    assert last["date"] == "2026-09-28"
    assert last["close"] == int(_price_row(date(2026, 9, 28))["stck_clpr"])


async def test_s11c_fetch_after_six_am_marks_previous_day_final(rig):
    """S11c — 화 07:00 조회, 최신 봉 = 월요일 → 잠정 False."""
    now = _at(2026, 9, 29, 7)
    rig.install(CalendarKis(today=now.date(), last_day=date(2026, 9, 28), listing=date(2026, 6, 1)))
    j = _j(await rig.fetch("005930", "D", 5, now=now))
    assert j["bars"][-1]["date"] == "2026-09-28"
    assert j["last_bar_provisional"] is False


async def test_s12b_fetch_weekly_this_week_is_provisional(rig):
    """S12b — 월 10:00 의 주봉 조회 → 이번 주 봉이 마지막 = 잠정 True."""
    rig.install(CalendarKis(listing=date(2026, 3, 2)))
    j = _j(await rig.fetch("005930", "W", 5))
    assert j["last_bar_provisional"] is True


# ═════════════════════════════════════════════════════════════════════════════
# S13~S15 — 불완전 멈춤(호출 상한 · 진전 없음 · 시간 예산)
# ═════════════════════════════════════════════════════════════════════════════

async def test_s13_call_cap_stops_incomplete(rig):
    """S13 — `_MAX_CALLS_PER_FETCH["D"]=3` → 3회에서 멈춤, complete=False, call_cap."""
    rig.monkeypatch.setitem(rig.pc._MAX_CALLS_PER_FETCH, "D", 3)
    kis = rig.install(CalendarKis())

    j = _j(await rig.fetch("005930", "D", 5))

    assert len(kis.calls) == 3
    assert len(j["bars"]) == 300
    assert j["complete"] is False
    assert j["incomplete_reason"] == "call_cap"
    assert j["kis_calls"] == 3


async def test_s14_no_progress_stops_and_warns(rig, caplog):
    """S14 — 가짜가 매번 같은 100봉 → 2회에서 멈춤 · no_progress · WARNING [stock_chart_partial]."""
    caplog.set_level(logging.WARNING)
    kis = rig.install(CalendarKis(stuck=True))

    j = _j(await rig.fetch("005930", "D", 5))

    assert len(kis.calls) == 2
    assert j["complete"] is False
    assert j["incomplete_reason"] == "no_progress"
    assert len(j["bars"]) == 100
    lines = _warnings(caplog, "[stock_chart_partial] ")
    assert len(lines) == 1, lines
    assert "reason=no_progress" in lines[0]
    assert "ticker=005930" in lines[0]


async def test_s15_time_budget_stops_before_next_call(rig):
    """S15 — 호출마다 13초 → 2회 뒤 26초 > 25초 → 3번째 호출 없이 time_budget."""
    kis = rig.install(CalendarKis(clock_step=13.0))

    j = _j(await rig.fetch("005930", "D", 5))

    assert len(kis.calls) == 2
    assert j["complete"] is False
    assert j["incomplete_reason"] == "time_budget"
    assert len(j["bars"]) == 200


# ═════════════════════════════════════════════════════════════════════════════
# S16·S17 — 호출 예외
# ═════════════════════════════════════════════════════════════════════════════

async def test_s16_first_window_kis_error_propagates_and_is_not_cached(rig):
    """S16 — 첫 창 `KisApiError` → 그대로 전파 · 캐시 안 됨(다시 부르면 KIS 를 다시 부른다)."""
    from src.api.base import KisApiError

    kis = rig.install(CalendarKis(
        listing=date(2026, 6, 1),
        fail_on={1: KisApiError("1", "EGW00201", "초당 거래건수를 초과하였습니다.")},
    ))
    with pytest.raises(KisApiError) as ei:
        await rig.fetch("005930", "D", 5)
    assert ei.value.msg_cd == "EGW00201"
    assert len(kis.calls) == 1

    j = _j(await rig.fetch("005930", "D", 5))
    assert len(kis.calls) == 2, "실패는 캐시하지 않는다 — 두 번째 요청은 KIS 로 다시 나가야 한다"
    assert j["cached"] is False
    assert j["complete"] is True


def _window_errors():
    import httpx

    from src.api.base import KisApiError

    return [
        KisApiError("1", "EGW00201", "초당 거래건수를 초과하였습니다."),
        httpx.ReadTimeout("read timeout"),
    ]


@pytest.mark.parametrize("exc_index", [0, 1], ids=["kis_error", "network_timeout"])
async def test_s17_later_window_error_returns_partial_and_caches_one_minute(rig, caplog, exc_index):
    """S17 — 3번째 창 예외 → 앞 두 창의 봉 + complete=False(window_error) · 60초 캐시 · 61초 뒤 새 조회."""
    caplog.set_level(logging.WARNING)
    exc = _window_errors()[exc_index]
    kis = rig.install(CalendarKis(fail_on={3: exc}))

    j = _j(await rig.fetch("005930", "D", 5))

    assert len(kis.calls) == 3
    assert len(j["bars"]) == 200
    assert j["complete"] is False
    assert j["incomplete_reason"] == "window_error"
    assert j["bars"][-1]["date"] == "2026-09-28"
    lines = _warnings(caplog, "[stock_chart_partial] ")
    assert any("reason=window_error" in ln for ln in lines), lines

    base_t = rig.clock.t
    rig.clock.t = base_t + 59.0
    again = _j(await rig.fetch("005930", "D", 5))
    assert len(kis.calls) == 3, "부분 결과도 60초는 캐시 — 같은 실패로 KIS 를 두드리지 않는다"
    assert again["cached"] is True
    assert again["complete"] is False

    rig.clock.t = base_t + 61.0
    kis.fail_on.clear()
    fresh = _j(await rig.fetch("005930", "D", 5))
    assert len(kis.calls) > 3, "61초 뒤에는 새로 받는다"
    assert fresh["cached"] is False
    assert fresh["complete"] is True


# ═════════════════════════════════════════════════════════════════════════════
# S18 — 차트 KIS 호출 사이 간격 (조회 경계를 넘어서도 0.25초)
# ═════════════════════════════════════════════════════════════════════════════

#: 가짜 KIS 한 건이 걸리는 시간 — 2진 소수로 정확히 떨어지는 값(창 경계 비교가 부동소수 오차에 흔들리지 않게).
_CALL_SECS = 0.0625


def _gaps(times: list) -> list:
    return [b - a for a, b in zip(times, times[1:])]


def _max_calls_in_any_second(times: list) -> int:
    """반열린 1초 창 [t, t+1) 안에 들어간 호출 수의 최댓값."""
    return max((sum(1 for u in times if t <= u < t + 1.0) for t in times), default=0)


async def test_s18_sleep_fills_remainder_before_every_call_after_the_first(rig):
    """S18 — 첫 호출 앞에는 쉬지 않고, 이후 **모든** KIS 호출 앞에서 직전 차트 호출로부터
    0.25초가 될 때까지만 쉰다(호출 자체가 걸린 시간은 빼고 남은 만큼). 마지막 호출 뒤에는 쉬지 않는다."""
    kis = rig.install(CalendarKis(listing=date(2025, 3, 10), clock_step=_CALL_SECS))

    await rig.fetch("005930", "D", 5)

    calls = len(kis.calls)
    assert calls >= 3
    seq = [kind if kind == "kis" else ("sleep" if val and val > 0 else "yield") for kind, val in rig.events]
    seq = [s for s in seq if s != "yield"]
    assert seq[0] == "kis", "첫 호출 앞에는 sleep 이 없다"
    assert seq[-1] == "kis", "마지막 호출 뒤에 sleep 하지 않는다"
    assert seq == ["kis", "sleep"] * (calls - 1) + ["kis"]
    window_sleeps = [s for s in rig.sleeps if s and s > 0]
    assert window_sleeps == [0.25 - _CALL_SECS] * (calls - 1), (
        "고정 0.25초가 아니라 「직전 호출로부터 0.25초」 가 될 때까지만 쉰다"
    )
    assert _gaps(kis.call_times) == [0.25] * (calls - 1)
    assert rig.pc._WINDOW_SLEEP_SECS == 0.25


async def test_s18b_back_to_back_monthly_fetches_are_spaced(rig):
    """S18b — 월봉(호출 1회) 두 조회를 잇달아 부르면 두 KIS 호출도 0.25초 이상 떨어진다.

    조회 하나 안의 창 사이에서만 쉬면 월봉은 한 번도 쉬지 않아 종목 수만큼 KIS 를 연달아 두드린다.
    """
    kis = rig.install(CalendarKis(clock_step=_CALL_SECS))

    await rig.fetch("005930", "M", 5)
    await rig.fetch("000660", "M", 5)

    assert len(kis.calls) == 2
    assert _gaps(kis.call_times)[0] >= 0.25, f"두 월봉 조회의 KIS 호출 간격 {_gaps(kis.call_times)}"


async def test_s18c_forty_queued_tickers_never_exceed_four_calls_per_second(rig):
    """S18c — 서로 다른 40종목(일·주·월봉 섞어)을 한꺼번에 부르면 세마포어 줄을 서는데,
    앞 조회가 세마포어를 놓은 뒤 다음 조회의 첫 호출도 간격을 지킨다 → 어느 1초 창에도 4건 이하.

    이 기능은 `base.py` 전역 초당 20건 한도를 주문·잔고 호출과 함께 쓴다 — 차트 몫을 초당 4건으로 묶는다.
    """
    kis = rig.install(CalendarKis(listing=date(2025, 3, 10), clock_step=_CALL_SECS))
    periods = ("D", "W", "M")
    tickers = [f"{100000 + i:06d}" for i in range(40)]

    results = await asyncio.gather(*(rig.fetch(t, periods[i % 3], 5) for i, t in enumerate(tickers)))

    assert all(_j(r)["complete"] is True for r in results)
    assert {c[2]["FID_INPUT_ISCD"] for c in kis.calls} == set(tickers)
    assert kis.max_inflight == 1
    assert min(_gaps(kis.call_times)) >= 0.25, f"가장 짧은 간격 {min(_gaps(kis.call_times))}"
    assert _max_calls_in_any_second(kis.call_times) <= 4


# ═════════════════════════════════════════════════════════════════════════════
# S19~S22 — 캐시 · single-flight · 직렬 · 대기 초과
# ═════════════════════════════════════════════════════════════════════════════

async def test_s19_cache_hit_expiry_and_lru(rig):
    """S19 — 같은 키 두 번 = 조회 1번(두 번째 cached=True) · 601초 뒤 새 조회 · 33번째 키가 LRU 퇴출."""
    kis = rig.install(CalendarKis())

    first = _j(await rig.fetch("005930", "M", 5))
    second = _j(await rig.fetch("005930", "M", 5))
    assert len(kis.calls) == 1
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["bars"] == first["bars"]

    rig.clock.t += 599.0
    assert _j(await rig.fetch("005930", "M", 5))["cached"] is True
    assert len(kis.calls) == 1
    rig.clock.t += 2.0      # 저장 시점 + 601초
    assert _j(await rig.fetch("005930", "M", 5))["cached"] is False
    assert len(kis.calls) == 2

    # LRU — 32개를 채우고 1번 키를 다시 쓴 뒤 33번째를 넣으면 2번 키가 나간다.
    rig.pc._reset_state_for_tests()
    kis.calls.clear()
    tickers = [f"{i:06d}" for i in range(1, 34)]
    for t in tickers[:32]:
        await rig.fetch(t, "M", 5)
    assert len(kis.calls) == 32
    assert _j(await rig.fetch(tickers[0], "M", 5))["cached"] is True     # 1번 = 최근 사용
    await rig.fetch(tickers[32], "M", 5)                                # 33번째 → 퇴출 발생
    assert len(kis.calls) == 33
    assert _j(await rig.fetch(tickers[0], "M", 5))["cached"] is True, "최근에 쓴 키는 남아야 한다"
    assert len(kis.calls) == 33
    assert _j(await rig.fetch(tickers[1], "M", 5))["cached"] is False, "가장 오래 안 쓴 키가 퇴출돼야 한다"
    assert len(kis.calls) == 34
    assert rig.pc._CACHE_MAX_ENTRIES == 32


async def test_s19b_cache_set_evicts_expired_entries(rig):
    """S19b — 저장할 때 이미 만료된 항목을 걷어낸다(같은 키를 다시 읽거나 32개가 넘칠 때까지
    만료된 차트를 들고 있지 않는다). 아직 살아 있는 항목은 남는다."""
    rig.install(CalendarKis())

    await rig.fetch("005930", "M", 5)                     # t0 저장 → t0+600 만료
    rig.clock.t += 601.0
    await rig.fetch("000660", "M", 5)                     # 저장 시 005930 은 이미 만료
    assert ("005930", "M", 5) not in rig.pc._cache, "만료된 항목이 저장 뒤에도 남았다"
    assert ("000660", "M", 5) in rig.pc._cache

    rig.clock.t += 300.0
    await rig.fetch("035720", "M", 5)                     # 000660 은 아직 300초 남았다
    assert set(rig.pc._cache) == {("000660", "M", 5), ("035720", "M", 5)}


async def test_s20_single_flight_same_key(rig):
    """S20 — 같은 키 동시 2요청 → KIS 호출은 한 조회분, 두 결과 동일."""
    kis = rig.install(CalendarKis(listing=date(2025, 3, 10), yield_inside=True))
    one_fetch = math.ceil(len(_trading_days(date(2025, 3, 10), TODAY)) / 100)

    a, b = await asyncio.gather(rig.fetch("005930", "D", 5), rig.fetch("005930", "D", 5))

    assert len(kis.calls) == one_fetch, f"single-flight 실패 — 호출 {len(kis.calls)} (기대 {one_fetch})"
    assert _j(a)["bars"] == _j(b)["bars"]


async def test_s21_global_serial_one_fetch_at_a_time(rig):
    """S21 — 다른 키 동시 2요청 → 동시 진행 KIS 호출 최대 1 · 한 조회가 페이징을 끝낼 때까지 쥔다."""
    kis = rig.install(CalendarKis(listing=date(2025, 3, 10), yield_inside=True))

    a, b = await asyncio.gather(rig.fetch("005930", "D", 5), rig.fetch("000660", "D", 5))

    assert kis.max_inflight == 1, f"동시 진행 KIS 호출 {kis.max_inflight} — 모듈 전역 1건이어야 한다"
    order = [c[2]["FID_INPUT_ISCD"] for c in kis.calls]
    switches = sum(1 for x, y in zip(order, order[1:]) if x != y)
    assert switches == 1, f"두 조회의 창이 섞였다: {order}"
    assert _j(a)["complete"] is True and _j(b)["complete"] is True


async def test_s22_queue_wait_timeout_raises_busy_without_kis_call(rig, caplog):
    """S22 — 다른 조회가 세마포어를 쥔 채 대기 상한 초과 → ChartBusyError, 그 요청의 KIS 0회."""
    caplog.set_level(logging.WARNING)
    rig.monkeypatch.setattr(rig.pc, "_QUEUE_WAIT_SECS", 0.05)
    gate, entered = asyncio.Event(), asyncio.Event()
    kis = rig.install(CalendarKis(gate=gate, gate_ticker="005930", entered=entered))

    holder = asyncio.create_task(rig.fetch("005930", "M", 5))
    await asyncio.wait_for(entered.wait(), 5)

    with pytest.raises(rig.pc.ChartBusyError):
        await rig.fetch("000660", "M", 5)
    assert kis.calls_for("000660") == []
    lines = _warnings(caplog, "[stock_chart_busy] ")
    assert lines and "ticker=000660" in lines[0]

    gate.set()
    done = _j(await asyncio.wait_for(holder, 5))
    assert done["complete"] is True

    # 대기 초과는 캐시하지 않는다 — 자리가 나면 바로 받는다.
    after = _j(await rig.fetch("000660", "M", 5))
    assert after["cached"] is False
    assert len(kis.calls_for("000660")) == 1


# ═════════════════════════════════════════════════════════════════════════════
# S23·S24 — 인자 검증 · 구간 계산
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    ("ticker", "period", "years"),
    [
        ("A12345", "D", 5), ("12345", "D", 5), ("0059300", "D", 5), (None, "D", 5),
        ("0080G0", "D", 5),
        ("\u0660\u0660\u0665\u0669\u0663\u0660", "D", 5),   # 아랍-인도 숫자 ٠٠٥٩٣٠ (str.isdigit 은 참)
        ("\uff10\uff10\uff15\uff19\uff13\uff10", "D", 5),   # 전각 숫자 ００５９３０ (str.isdigit 은 참)
        ("005930", "Y", 5), ("005930", "d", 5),
        ("005930", "D", 0), ("005930", "D", 6),
    ],
)
async def test_s23_invalid_arguments_raise_value_error_without_kis(rig, ticker, period, years):
    """S23 — 6자리 **ASCII** 숫자 · D/W/M 대문자 · years 1..5 밖 → ValueError, KIS 0회(방어선 2).

    `str.isdigit()` 은 아랍-인도·전각 숫자도 참이라 ASCII 검사를 함께 해야 한다."""
    kis = rig.install(CalendarKis())
    with pytest.raises(ValueError):
        await rig.pc.fetch_candle_chart(ticker, period, years, now_kst=NOW_MON_1000)
    assert kis.calls == []


@pytest.mark.parametrize(
    ("now", "period", "years", "date1", "start_iso"),
    [
        (_at(2028, 2, 29, 10), "D", 5, "20230228", "2023-02-28"),   # 윤일 → 2/28
        (_at(2028, 2, 29, 10), "D", 1, "20270228", "2027-02-28"),
        (_at(2028, 2, 29, 10), "W", 5, "20230227", "2023-02-27"),   # 2023-02-28(화) 의 주 월요일
        (_at(2028, 2, 29, 10), "M", 5, "20230201", "2023-02-01"),
        (NOW_MON_1000, "D", 1, "20250928", "2025-09-28"),
    ],
)
async def test_s24_range_start_by_years_and_leap_day(rig, now, period, years, date1, start_iso):
    """S24 — years 년 전 같은 월·일(2/29 → 2/28) · W=그 주 월요일 · M=그 달 1일."""
    kis = rig.install(CalendarKis(today=now.date()))
    j = _j(await rig.fetch("005930", period, years, now=now))
    assert kis.calls[0][2]["FID_INPUT_DATE_1"] == date1
    assert kis.calls[0][2]["FID_INPUT_DATE_2"] == _ymd(now.date())
    assert j["start_date"] == start_iso
    assert j["end_date"] == now.date().isoformat()
    assert j["years"] == years


# ═════════════════════════════════════════════════════════════════════════════
# S25 — 호출자 취소(모달 닫힘)
# ═════════════════════════════════════════════════════════════════════════════

async def test_s25_caller_cancel_does_not_cancel_fetch_and_fills_cache(rig):
    """S25 — 기다리던 코루틴을 cancel 해도 조회 task 는 끝나고 캐시가 채워진다."""
    gate, entered = asyncio.Event(), asyncio.Event()
    kis = rig.install(CalendarKis(gate=gate, gate_ticker="005930", entered=entered))

    caller = asyncio.create_task(rig.fetch("005930", "M", 5))
    await asyncio.wait_for(entered.wait(), 5)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller

    gate.set()
    for _ in range(20):
        await _REAL_SLEEP(0.01)

    again = _j(await rig.fetch("005930", "M", 5))
    assert len(kis.calls) == 1, "취소된 호출자의 조회가 끝나 캐시를 채웠어야 한다"
    assert again["cached"] is True
    assert len(again["bars"]) == 61


# ═════════════════════════════════════════════════════════════════════════════
# S26 — respx 계약 (실제 kis_get_quote → httpx → respx)
# ═════════════════════════════════════════════════════════════════════════════

async def test_s26_respx_real_kis_json_flows_to_int_bars(pc, monkeypatch, mock_kis):
    """S26 — `kis_get_quote` 를 **대체하지 않고** 실제로 태운다. respx 가 httpx 응답으로
    정본 모양(문자열 숫자 · output1 · output2)을 돌려주면 끝까지 정수 봉으로 나와야 한다.

    선례 `test_cycleC1_finance_fetch.py` G-C1-FIN-8 보다 한 단계 아래(전송 계층)를 가로챈다.
    """
    import httpx

    from src.api import base

    monkeypatch.setattr(base, "_select_quote_label", AsyncMock(return_value=None))
    monkeypatch.setattr(base.token_manager, "get_token", AsyncMock(return_value="test-token"))
    payload = {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "msg1": "정상처리 되었습니다.",
        "output1": {
            "acml_tr_pbmn": "236062833000",
            "acml_vol": "2106409",
            "hts_kor_isnm": "SK하이닉스",
            "itewhol_loan_rmnd_ratem name": "0.32",
            "stck_prpr": "112000",
            "stck_shrn_iscd": "000660",
        },
        "output2": [
            {
                "acml_tr_pbmn": "237914727500", "acml_vol": "2203472", "flng_cls_code": "00",
                "mod_yn": "N", "prdy_vrss": "0", "prdy_vrss_sign": "3", "prtt_rate": "0.00",
                "revl_issu_reas": "", "stck_bsop_date": "20260928", "stck_clpr": "107500",
                "stck_hgpr": "109000", "stck_lwpr": "106500", "stck_oprc": "107000",
            },
            {
                "acml_tr_pbmn": "4758294550000", "acml_vol": "44067440", "flng_cls_code": "00",
                "mod_yn": "N", "prdy_vrss": "-1500", "prdy_vrss_sign": "5", "prtt_rate": "0.00",
                "revl_issu_reas": "", "stck_bsop_date": "20260831", "stck_clpr": "107500",
                "stck_hgpr": "115000", "stck_lwpr": "101000", "stck_oprc": "109000",
            },
            {"stck_bsop_date": "", "stck_clpr": "", "stck_oprc": "", "stck_hgpr": "",
             "stck_lwpr": "", "acml_vol": "", "acml_tr_pbmn": "", "mod_yn": ""},
        ],
    }
    route = mock_kis.route(method="GET", path=DAILY_PRICE_URL).mock(
        return_value=httpx.Response(200, json=payload)
    )

    chart = await pc.fetch_candle_chart("000660", "M", 5, now_kst=NOW_MON_1000)

    assert route.call_count == 1
    q = route.calls[0].request.url.params
    assert q["FID_COND_MRKT_DIV_CODE"] == "J"
    assert q["FID_INPUT_ISCD"] == "000660"
    assert q["FID_PERIOD_DIV_CODE"] == "M"
    assert q["FID_ORG_ADJ_PRC"] == "0"
    assert q["FID_INPUT_DATE_1"] == "20210901"
    assert q["FID_INPUT_DATE_2"] == "20260928"

    j = _j(chart)
    assert j["name"] == "SK하이닉스"
    assert j["ticker"] == "000660"
    assert _dates(j) == ["2026-08-31", "2026-09-28"]
    assert j["bars"][-1] == {
        "date": "2026-09-28", "open": 107000, "high": 109000, "low": 106500,
        "close": 107500, "volume": 2203472, "amount": 237914727500,
    }
    for b in j["bars"]:
        for k in BAR_KEYS - {"date"}:
            assert type(b[k]) is int
    assert j["fetched_at"].endswith("+09:00")
    assert j["complete"] is True
