"""cycle349 ③ E4 — 일일 리포트 수집기에 `vcp_breakout_events` 키 + `[vcp_breakout_events]` WARNING (Red).

명세 = `_workspace/red/cycle349_vcp_observe_spec.md` E3·E4.

`collect_daily_log_metrics` 는 20:05 1차 스냅샷 · 20:20 번들 · 21:30 완전판이 **모두** 부른다. 그래서
- 키 `metrics["vcp_breakout_events"]` 는 **하나** 추가하고 기존 9키 순서 뒤(끝)에 둔다(dict 가 그대로
  OpenAI 프롬프트·`daily_log_reports.metrics` JSONB·루틴 번들이라 순서도 계약이다 — cycle249 C-1).
- WARNING 줄은 KST 하루 1회(`KstDailyEmitCap`)이고 `target_date == 오늘(KST)` ∧ VCP 매수 창
  (`entry_end`, 못 읽으면 14:30)이 **닫힌 뒤**에만 찍는다(평소 첫 호출 = 20:05). 창이 열린 동안의
  호출(낮의 번들 GET·수동 run)과 과거 날짜 호출은 키만 채우고 cap 을 소비하지 않는다 — 소비하면
  그 중간값이 그날의 결과 줄이 된다(verify 지적 3).
- 키 값에는 `final` 이 붙는다 — 1 = 창이 닫힌 뒤의 값(지난 날짜 포함), 0 = 중간값.
- 지난 날짜에 이 프로세스가 watch 를 갖고 있지 않으면 `status=not_retained`(전략이 판정 — 그날
  값의 정본은 그날 `daily_log_reports.metrics`, verify 지적 4).
- 전략 부재 = `None`. 수집 실패 = 그 키만 `None`, 나머지 metrics 무영향(never-raise).
- 추가 I/O 0 — 메모리 읽기뿐(레지스트리에서 `vcp_breakout` 을 찾아 `breakout_event_summary(target_date)`).

시계 = aware KST(수집기의 `datetime.now(KST)`). freezegun 에는 UTC 로 넣는다(`_utc_of`).

⚠️ 수집기의 일일 cap 은 모듈 전역이라 테스트 간에 공유된다. 격리 = autouse `_fresh_collector_caps` 가
모듈 전역의 `KstDailyEmitCap` 인스턴스를 **타입으로** 찾아(이름 비의존) 테스트마다 새 인스턴스로 바꾼다.
날짜 자기 리셋에만 기대면 앞 테스트가 남긴 cap 날짜가 「과거 날짜 호출의 선소비」(M8b)를 가려
파일 통째 실행에서 그 돌연변이가 산다(tester F2). 테스트마다 날짜를 달리하는 관례는 그대로 둔다.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from freezegun import freeze_time

import src.engine.log_metrics_collector as collector

pytestmark = pytest.mark.unit

MARKER = "[vcp_breakout_events]"

#: cycle249 C-1 / cycle259 가 잠근 기존 순서 — 새 키는 그 **뒤**에 하나.
BASE_KEYS = [
    "target_date", "logs", "trades", "api_metrics", "strategy_funnel",
    "strategy_funnel_stages", "next_day_clear", "portfolio_risk_snapshot", "tick_blind",
]


def _utc_of(kst: str) -> str:
    dt = datetime.strptime(kst, "%Y-%m-%d %H:%M:%S") - timedelta(hours=9)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture(autouse=True)
def _fresh_collector_caps(monkeypatch):
    """F2 — 수집기 모듈 전역 `KstDailyEmitCap` 을 테스트마다 새 인스턴스로(타입으로 찾는다).
    하나도 못 찾으면 격리가 조용히 사라진 것이므로 실패시킨다.
    클래스는 수집기 모듈이 쥔 참조로 얻는다 — 이 파일에 `daily_emit_cap` import 를 새로 두면
    영향 인덱스(`test_cycle318_impact_index_freshness`)가 낡는다."""
    cap_type = collector.KstDailyEmitCap
    names = [n for n, v in vars(collector).items() if isinstance(v, cap_type)]
    assert names, "log_metrics_collector 모듈 전역에 KstDailyEmitCap 이 없다 — 격리 대상 소실"
    for n in names:
        monkeypatch.setattr(collector, n, cap_type())


@pytest.fixture
def isolated(monkeypatch):
    """수집 하위 호출을 결정론적 대역으로(DB/KIS 무접촉) — cycle249 isolated 와 같은 목록."""

    async def _fetch(start, end, limit=None):
        return []

    async def _high(start, end, *a, **k):
        return []

    async def _count(start, end):
        return {"WARNING": 0, "ERROR": 0, "CRITICAL": 0}

    async def _trades(d1, d2):
        return []

    async def _funnel():
        return {"momentum": {"signals": 0, "orders": 0, "fills": 0}}

    async def _stages(target_date):
        return {}

    async def _snapshot(now=None):
        return None

    monkeypatch.setattr(collector, "_fetch_logs_in_range", _fetch)
    monkeypatch.setattr(collector, "_fetch_high_severity_logs", _high)
    monkeypatch.setattr(collector, "_count_logs_by_level", _count)
    monkeypatch.setattr(collector, "get_trades_in_range", _trades)
    monkeypatch.setattr(collector, "get_request_metrics", lambda: {"total": 0})
    monkeypatch.setattr(collector, "_collect_strategy_funnel", _funnel)
    monkeypatch.setattr(collector, "_collect_strategy_funnel_stages", _stages)
    monkeypatch.setattr(collector, "_build_portfolio_risk_snapshot", _snapshot)

    async def _no_pyramid_shadow(target_date):
        return None

    # cycle351 — 셰도 진입점 대역(DB·30초 상한 무접촉). Green 전에는 속성이 없어 raising=False.
    monkeypatch.setattr(collector, "_collect_pyramid_shadow", _no_pyramid_shadow, raising=False)


class _FakeVcp:
    strategy_id = "vcp_breakout"

    def __init__(self, summary=None, *, raises: bool = False):
        self._summary = summary
        self._raises = raises
        self.calls: list = []

    def breakout_event_summary(self, target_date):
        self.calls.append(target_date)
        if self._raises:
            raise RuntimeError("summary boom (cycle349 test)")
        if self._summary is not None:
            return dict(self._summary)
        return {"status": "no_watch", "date": target_date.isoformat()}


def _install_registry(monkeypatch, strategies: list):
    """`trading_scheduler.registry` 대역 — `get(sid)` 와 `all()` 둘 다 지원(구현이 어느 쪽을 써도)."""
    from src.engine import scheduler as sched_mod

    by_id = {s.strategy_id: s for s in strategies}
    reg = SimpleNamespace(get=lambda sid: by_id.get(sid), all=lambda: list(strategies))
    monkeypatch.setattr(sched_mod, "trading_scheduler", SimpleNamespace(registry=reg))


def _ok_summary(d: date, *, crossed_tickers: list[str] | None = None) -> dict:
    crossed = list(["900002"] if crossed_tickers is None else crossed_tickers)
    return {
        "status": "ok", "date": d.isoformat(), "run_at": "07:45:00", "window": "09:05-14:30",
        "partial": False, "candidates": 3, "observed": 2, "crossed": len(crossed),
        "crossed_tickers": crossed, "unobserved_tickers": ["900003"],
        "per_ticker": {},
    }


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING and r.getMessage().startswith(MARKER + " ")]


async def _collect(d: date, kst_now: str):
    with freeze_time(_utc_of(kst_now)):
        return await collector.collect_daily_log_metrics(d)


# ---------------------------------------------------------------------------
# 키 계약
# ---------------------------------------------------------------------------

async def test_e4_key_appended_last_after_existing_nine(isolated, monkeypatch):
    d = date(2026, 10, 5)
    _install_registry(monkeypatch, [_FakeVcp()])
    metrics = await _collect(d, "2026-10-05 20:05:00")
    # cycle351 — 그 뒤에 `pyramid_shadow` 가 하나 더 붙는다(새 키는 항상 끝).
    assert list(metrics) == BASE_KEYS + ["vcp_breakout_events", "pyramid_shadow"], list(metrics)


async def test_e4_value_is_strategy_summary_for_target_date(isolated, monkeypatch):
    d = date(2026, 10, 6)
    fake = _FakeVcp(_ok_summary(d))
    _install_registry(monkeypatch, [fake])
    metrics = await _collect(d, "2026-10-06 20:05:00")
    assert metrics["vcp_breakout_events"] == {**_ok_summary(d), "final": 1}
    assert fake.calls == [d]


async def test_e4_strategy_absent_is_none(isolated, monkeypatch, caplog):
    d = date(2026, 10, 7)
    _install_registry(monkeypatch, [])
    metrics = await _collect(d, "2026-10-07 20:05:00")
    assert "vcp_breakout_events" in metrics
    assert metrics["vcp_breakout_events"] is None


async def test_e4_collection_failure_only_nulls_its_key(isolated, monkeypatch):
    """요약이 터져도 그 키만 None — 나머지 metrics 는 그대로(never-raise)."""
    d = date(2026, 10, 8)
    _install_registry(monkeypatch, [_FakeVcp(raises=True)])
    metrics = await _collect(d, "2026-10-08 20:05:00")
    assert metrics["vcp_breakout_events"] is None
    assert list(metrics)[:9] == BASE_KEYS
    assert metrics["strategy_funnel"] == {"momentum": {"signals": 0, "orders": 0, "fills": 0}}
    assert metrics["api_metrics"] == {"total": 0}


# ---------------------------------------------------------------------------
# WARNING 줄 — 형식 · 하루 1회 · 오늘만
# ---------------------------------------------------------------------------

async def test_e4_ok_line_format(isolated, monkeypatch, caplog):
    d = date(2026, 10, 12)
    _install_registry(monkeypatch, [_FakeVcp(_ok_summary(d, crossed_tickers=["900001", "900002"]))])
    await _collect(d, "2026-10-12 20:05:00")
    assert _lines(caplog) == [
        "[vcp_breakout_events] date=2026-10-12 status=ok crossed=2/3 observed=2 unobserved=1 "
        "run_at=07:45:00 window=09:05-14:30 partial=0 crossed_tickers=900001,900002"
    ]


async def test_e4_ok_line_partial_and_empty_crossed(isolated, monkeypatch, caplog):
    d = date(2026, 10, 13)
    summary = {**_ok_summary(d, crossed_tickers=[]), "partial": True, "run_at": "10:12:00"}
    _install_registry(monkeypatch, [_FakeVcp(summary)])
    await _collect(d, "2026-10-13 20:05:00")
    assert _lines(caplog) == [
        "[vcp_breakout_events] date=2026-10-13 status=ok crossed=0/3 observed=2 unobserved=1 "
        "run_at=10:12:00 window=09:05-14:30 partial=1 crossed_tickers=-"
    ]


async def test_e4_no_watch_line_stops_after_status(isolated, monkeypatch, caplog):
    """no_watch 는 `status=no_watch` 까지만 — 「0」과 「모른다」를 가른다."""
    d = date(2026, 10, 14)
    _install_registry(monkeypatch, [_FakeVcp()])
    await _collect(d, "2026-10-14 20:05:00")
    assert _lines(caplog) == ["[vcp_breakout_events] date=2026-10-14 status=no_watch"]


async def test_e4_error_status_line_stops_after_status(isolated, monkeypatch, caplog):
    d = date(2026, 10, 15)
    _install_registry(monkeypatch, [_FakeVcp({"status": "error", "date": d.isoformat()})])
    await _collect(d, "2026-10-15 20:05:00")
    assert _lines(caplog) == ["[vcp_breakout_events] date=2026-10-15 status=error"]


async def test_e4_warning_once_per_kst_day(isolated, monkeypatch, caplog):
    """20:05 · 20:20 · 21:30 세 번 불려도 줄은 1개(M5). 다음 날은 다시 1개."""
    d = date(2026, 10, 19)
    _install_registry(monkeypatch, [_FakeVcp(_ok_summary(d))])
    await _collect(d, "2026-10-19 20:05:00")
    await _collect(d, "2026-10-19 20:20:00")
    await _collect(d, "2026-10-19 21:30:00")
    assert len(_lines(caplog)) == 1

    d2 = d + timedelta(days=1)
    _install_registry(monkeypatch, [_FakeVcp(_ok_summary(d2))])
    await _collect(d2, "2026-10-20 20:05:00")
    lines = _lines(caplog)
    assert len(lines) == 2 and lines[1].startswith("[vcp_breakout_events] date=2026-10-20 ")


async def test_e4_past_date_fills_key_without_line(isolated, monkeypatch, caplog):
    """과거 날짜 호출(수동 재생성 등)은 줄 0 · 키는 전략이 준 값 그대로 + `final=1`
    (지난 날은 창이 닫혔다). 과거 날짜 판정(`not_retained`)은 전략 몫이라 대역이 흉내 낸다."""
    today = date(2026, 10, 21)
    past = today - timedelta(days=1)
    fake = _FakeVcp({"status": "not_retained", "date": past.isoformat()})
    _install_registry(monkeypatch, [fake])
    metrics = await _collect(past, "2026-10-21 21:30:00")
    assert _lines(caplog) == []
    assert metrics["vcp_breakout_events"] == {
        "status": "not_retained", "date": past.isoformat(), "final": 1,
    }
    assert fake.calls == [past]


async def test_e4_past_date_call_does_not_consume_todays_line(isolated, monkeypatch, caplog):
    """과거 날짜 호출이 오늘 cap 을 먼저 소비하면 20:05 줄이 사라진다."""
    today = date(2026, 10, 22)
    _install_registry(monkeypatch, [_FakeVcp(_ok_summary(today))])
    await _collect(today - timedelta(days=1), "2026-10-22 19:00:00")
    await _collect(today, "2026-10-22 20:05:00")
    lines = _lines(caplog)
    assert len(lines) == 1 and lines[0].startswith("[vcp_breakout_events] date=2026-10-22 ")


# ---------------------------------------------------------------------------
# 실제 VCP 전략으로 끝까지 (prepare → 틱 → 20:05 수집)
# ---------------------------------------------------------------------------

async def test_e4_end_to_end_with_real_vcp_strategy(isolated, monkeypatch, caplog):
    from tests.unit.engine.strategies.test_cycle349_vcp_breakout_observe import (
        T_A, T_B, TRADE_DAY, _naive, make_strategy, prepare_env,
    )

    s = make_strategy()
    with prepare_env():
        with freeze_time(_naive("07:45:00")):
            await s.prepare()
    for hms, ticker, price in (("09:30:00", T_A, 10_250), ("10:00:00", T_B, 20_800)):
        with freeze_time(_naive(hms)):
            s.check_buy_signal(ticker, price, price)
    _install_registry(monkeypatch, [s])

    with freeze_time(_utc_of("2026-09-22 20:05:00")):
        metrics = await collector.collect_daily_log_metrics(TRADE_DAY)

    assert metrics["vcp_breakout_events"] == {**s.breakout_event_summary(TRADE_DAY), "final": 1}
    assert metrics["vcp_breakout_events"]["status"] == "ok"
    assert _lines(caplog) == [
        "[vcp_breakout_events] date=2026-09-22 status=ok crossed=1/3 observed=2 unobserved=1 "
        "run_at=07:45:00 window=09:05-14:30 partial=0 crossed_tickers=900002"
    ]


# ---------------------------------------------------------------------------
# 창이 닫히기 전 호출 — 키만(final=0), 줄·cap 은 창이 닫힌 뒤에 (verify 지적 3)
# ---------------------------------------------------------------------------

async def test_e4_midday_call_fills_key_final0_and_leaves_line_for_evening(
        isolated, monkeypatch, caplog):
    """11:00 번들 GET·수동 run 이 먼저 불러도 줄은 0 이고 cap 도 그대로다 — 20:05 호출이
    최종 줄 1개를 찍는다. 11:00 이 cap 을 소비하면 그날 결과가 오전 중간값이 된다."""
    d = date(2026, 10, 26)
    _install_registry(monkeypatch, [_FakeVcp(_ok_summary(d))])

    midday = await _collect(d, "2026-10-26 11:00:00")
    assert _lines(caplog) == []
    assert midday["vcp_breakout_events"] == {**_ok_summary(d), "final": 0}

    evening = await _collect(d, "2026-10-26 20:05:00")
    assert evening["vcp_breakout_events"]["final"] == 1
    assert _lines(caplog) == [
        "[vcp_breakout_events] date=2026-10-26 status=ok crossed=1/3 observed=2 unobserved=1 "
        "run_at=07:45:00 window=09:05-14:30 partial=0 crossed_tickers=900002"
    ]
    await _collect(d, "2026-10-26 21:30:00")
    assert len(_lines(caplog)) == 1


@pytest.mark.parametrize("kst_now,closed", [
    ("2026-10-27 14:30:00", False),   # 창 끝 포함(게이트 `now_t > entry_end` 와 같은 식)
    ("2026-10-27 14:30:01", True),
])
async def test_e4_window_end_boundary(isolated, monkeypatch, caplog, kst_now, closed):
    """창 끝 경계 — 14:30:00 은 아직 창 안(중간값), 14:30:01 부터 최종. 대역은 params 가 없어
    기본값 14:30 으로 떨어진다(읽기 실패 폴백 경로)."""
    d = date(2026, 10, 27)
    _install_registry(monkeypatch, [_FakeVcp(_ok_summary(d))])
    metrics = await _collect(d, kst_now)
    assert metrics["vcp_breakout_events"]["final"] == (1 if closed else 0)
    assert len(_lines(caplog)) == (1 if closed else 0)


async def test_e4_window_end_is_read_from_vcp_params(isolated, monkeypatch, caplog):
    """창 끝은 VCP params 의 `entry_end` 를 읽는다 — 리터럴 14:30 고정이 아니다."""
    d = date(2026, 10, 28)
    fake = _FakeVcp(_ok_summary(d))
    fake.config = SimpleNamespace(params={"entry_end": "10:00"})
    _install_registry(monkeypatch, [fake])
    metrics = await _collect(d, "2026-10-28 11:00:00")
    assert metrics["vcp_breakout_events"]["final"] == 1
    assert len(_lines(caplog)) == 1


async def test_e4_error_lines_do_not_reuse_data_marker(isolated, monkeypatch, caplog):
    """수집 실패 흔적(DEBUG)은 데이터 마커 `[vcp_breakout_events]` 를 쓰지 않는다 — 운영에서
    그 접두로 grep 하면 결과 줄만 나와야 한다. 실패 흔적 자체는 남는다(무음 금지)."""
    d = date(2026, 10, 29)
    _install_registry(monkeypatch, [_FakeVcp(raises=True)])
    caplog.set_level(logging.DEBUG, logger=collector.logger.name)
    await _collect(d, "2026-10-29 20:05:00")
    msgs = [r.getMessage() for r in caplog.records]
    assert not [m for m in msgs if m.startswith(MARKER + " ")]
    assert [m for m in msgs if m.startswith("[vcp_breakout_events_error] ")]


async def test_e4_real_strategy_past_date_is_not_retained(isolated, monkeypatch, caplog):
    """실제 VCP — 오늘 watch 를 가진 프로세스에 어제 날짜를 물으면 `not_retained`(그날 관측
    여부를 모른다), 줄 0. 「관측 대상이 없었다」(no_watch)와 다른 사실이다."""
    from tests.unit.engine.strategies.test_cycle349_vcp_breakout_observe import (
        TRADE_DAY, _naive, make_strategy, prepare_env,
    )

    s = make_strategy()
    with prepare_env():
        with freeze_time(_naive("07:45:00")):
            await s.prepare()
    _install_registry(monkeypatch, [s])
    yesterday = TRADE_DAY - timedelta(days=1)
    with freeze_time(_utc_of("2026-09-22 20:05:00")):
        metrics = await collector.collect_daily_log_metrics(yesterday)
    assert metrics["vcp_breakout_events"] == {
        "status": "not_retained", "date": yesterday.isoformat(), "final": 1,
    }
    assert _lines(caplog) == []
