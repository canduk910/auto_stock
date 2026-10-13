"""RS 2단계 Red — `src/engine/fundamental_load_tasks.py` 추가 적재 3갈래.

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase2.md` §A.

명세 해석 가정(구현이 따를 계약 — 바뀌면 이 머리말과 픽스처만 고친다):
- 공개 = `target_quarter(today: date) -> str`(순수, "YYYYMM") · `async run_extra_loads_once(*, now_kst=None) -> dict`
  · 상수 `EXTRA_LOAD_HARD_CAP_SECS = 3000`.
- `target_quarter` 의 공시 지연은 1단계 `fundamental_score.available_from` 과 같은 규칙이다
  (03·06·09월 = +45일, 12월(4분기) = +90일). 팀장 지시의 경계 예(2026-02-14 → 202509)가
  이 규칙과만 맞는다 — 명세 본문 「분기말 + 45일」 을 12월에도 그대로 적용하면 202512 가 된다(보고함).
- 외부 의존은 **모듈 속성으로** 부른다(`from x import y` 금지) — 이 테스트는 원 모듈의 속성을 바꾼다:
  `src.db.stock_master.list_by_filter` · `src.db.stock_master_financial.max_stac_yymm`/`upsert_financial_batch`
  · `src.api.finance.fetch_all_financials` · `src.api.invest_opinion.inquire_invest_opinion`/`inquire_estimate_perform`
  · `src.db.invest_opinion.upsert_opinions`/`upsert_estimate_snapshot` · `src.db.system_config._select_value`/`_upsert_value`.
- 새 DB 함수 2개(`src/db/invest_opinion.py`, 일괄 1쿼리):
  `latest_bsop_dates(tickers) -> dict[str, date]`(그 종목 DB 최신 `bsop_date`, 행 없는 종목은 키 없음) ·
  `estimate_snapshot_tickers(snapshot_month: date) -> set[str]`(그 달 행이 있는 종목).
- 킬스위치 = `system_config` 키 `fundamental_extra_load_mode`(`{"value": str}`). 주1회 마커 = 키
  `fundamental_opinion_load_last`, 값 `{"value": KST ISO datetime}` — 갈래가 돈 뒤 `_upsert_value` 로 쓴다.
- 투자의견 창: `[시작, 오늘]` 을 끝점 포함 90일 이하 창으로 빈틈·겹침 없이 나눈다(창 수 = ceil(일수/90)).
  응답 100건 = 그 창을 반으로 나눠 **1회만** 재조회(반쪽이 또 100건이어도 더 나누지 않는다).
- 요약 dict 키 = 명세 로그 필드 전부 + `truncated`(0/1) + `mode`.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

import src.api.finance as fin_api
import src.api.invest_opinion as io_api
import src.db.invest_opinion as io_db
import src.db.stock_master as sm_db
import src.db.stock_master_financial as smf_db
import src.db.system_config as sc_db
from src.engine import fundamental_load_tasks as flt
from src.engine import fundamental_score as fs
from src.engine import scanner

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 13, 16, 40, tzinfo=KST)
TODAY = NOW.date()
MODE_KEY = "fundamental_extra_load_mode"
MARKER_KEY = "fundamental_opinion_load_last"

_SUMMARY_KEYS = (
    "quarterly_total", "quarterly_fetched", "quarterly_skipped", "quarterly_failed",
    "opinion_tickers", "opinion_rows", "opinion_skipped",
    "estimate_saved", "estimate_skipped", "elapsed_ms", "mode", "truncated",
)


# ---------------------------------------------------------------------------
# target_quarter — 순수 함수
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 5, 15), "202603"),   # 03-31 + 45 = 05-15 (경계 포함)
        (date(2026, 5, 14), "202512"),
        (date(2026, 3, 31), "202512"),   # 12-31 + 90 = 03-31
        (date(2026, 3, 30), "202509"),
        (date(2026, 2, 14), "202509"),   # 팀장 지시 경계
        (date(2026, 1, 10), "202509"),   # 연도 경계
        (date(2025, 11, 14), "202509"),  # 09-30 + 45 = 11-14
        (date(2025, 11, 13), "202506"),
        (date(2026, 8, 14), "202606"),   # 06-30 + 45 = 08-14
        (date(2026, 8, 13), "202603"),
        (date(2026, 10, 13), "202606"),
    ],
)
def test_target_quarter_boundaries(today, expected):
    assert flt.target_quarter(today) == expected


def test_target_quarter_matches_phase1_available_from_every_day():
    """2025-01-01~2027-12-31 매일 — 「available_from <= today 인 가장 최근 분기말」 과 같다."""
    quarters = [f"{y}{m:02d}" for y in range(2023, 2028) for m in (3, 6, 9, 12)]
    d = date(2025, 1, 1)
    while d <= date(2027, 12, 31):
        want = max(q for q in quarters if fs.available_from(q) <= d)
        got = flt.target_quarter(d)
        assert isinstance(got, str) and len(got) == 6, got
        assert got == want, f"{d}: {got} != {want}"
        d += timedelta(days=1)


def test_hard_cap_constant():
    assert flt.EXTRA_LOAD_HARD_CAP_SECS == 3000


# ---------------------------------------------------------------------------
# 가짜 환경
# ---------------------------------------------------------------------------
class _Store:
    """system_config 가짜 저장소 — `_select_value`/`_upsert_value` 를 대신한다."""

    def __init__(self, initial: dict | None = None):
        self.data = dict(initial or {})
        self.writes: list[tuple[str, object]] = []

    async def select(self, key):
        return self.data.get(key, sc_db._MISSING)

    async def upsert(self, key, value):
        self.writes.append((key, value))
        self.data[key] = value


class Env:
    def __init__(self, monkeypatch, tickers=("005930", "000660", "035420"), config=None):
        self.tickers = list(tickers)
        self.store = _Store(config)
        self.calls: list[str] = []
        self.list_by_filter = AsyncMock(return_value=[{"ticker": t} for t in self.tickers])
        self.max_q: dict[str, str | None] = {}
        self.max_stac = AsyncMock(side_effect=self._max_stac)
        self.fetch_fin = AsyncMock(side_effect=self._fetch_fin)
        self.upsert_fin = AsyncMock(return_value=2)
        self.latest_dates: dict[str, date] = {}
        self.latest_bsop = AsyncMock(side_effect=lambda tickers: {
            t: d for t, d in self.latest_dates.items() if t in list(tickers)})
        self.opinion_resp = lambda t, a, b: []
        self.inquire_op = AsyncMock(side_effect=self._inquire_op)
        self.upsert_op = AsyncMock(side_effect=lambda t, rows: len(rows))
        self.est_have: set[str] = set()
        self.est_tickers = AsyncMock(side_effect=lambda month: set(self.est_have))
        self.est_resp = lambda t: {"ticker": t, "raw": {"output1": [{"x": "1"}]}, "settle_months": ["202512"]}
        self.inquire_est = AsyncMock(side_effect=lambda t: self.est_resp(t))
        self.upsert_est = AsyncMock(return_value=True)

        mp = monkeypatch
        mp.setattr(sm_db, "list_by_filter", self.list_by_filter)
        mp.setattr(smf_db, "max_stac_yymm", self.max_stac)
        mp.setattr(smf_db, "upsert_financial_batch", self.upsert_fin)
        mp.setattr(fin_api, "fetch_all_financials", self.fetch_fin)
        mp.setattr(io_db, "latest_bsop_dates", self.latest_bsop, raising=False)
        mp.setattr(io_db, "estimate_snapshot_tickers", self.est_tickers, raising=False)
        mp.setattr(io_db, "upsert_opinions", self.upsert_op)
        mp.setattr(io_db, "upsert_estimate_snapshot", self.upsert_est)
        mp.setattr(io_api, "inquire_invest_opinion", self.inquire_op)
        mp.setattr(io_api, "inquire_estimate_perform", self.inquire_est)
        mp.setattr(sc_db, "_select_value", self.store.select)
        mp.setattr(sc_db, "_upsert_value", self.store.upsert)

    async def _max_stac(self, ticker, div_cls="0"):
        self.calls.append(f"max:{ticker}:{div_cls}")
        return self.max_q.get(ticker)

    async def _fetch_fin(self, ticker, div_cls="0"):
        self.calls.append(f"fetch:{ticker}:{div_cls}")
        return [{"ticker": ticker, "stac_yymm": "202606", "div_cls": div_cls, "raw": {}}]

    async def _inquire_op(self, ticker, date_from, date_to):
        self.calls.append(f"op:{ticker}")
        return self.opinion_resp(ticker, date_from, date_to)

    def op_windows(self, ticker):
        return [(c.args[1], c.args[2]) if len(c.args) >= 3 else (c.kwargs["date_from"], c.kwargs["date_to"])
                for c in self.inquire_op.await_args_list
                if (c.args[0] if c.args else c.kwargs.get("ticker")) == ticker]


def _marker(days_ago: float) -> dict:
    return {"value": (NOW - timedelta(days=days_ago)).isoformat()}


async def _run(**kw):
    return await flt.run_extra_loads_once(now_kst=NOW, **kw)


# ---------------------------------------------------------------------------
# 요약·유니버스
# ---------------------------------------------------------------------------
async def test_summary_has_all_keys_and_universe_matches_annual_load(monkeypatch):
    env = Env(monkeypatch)
    summary = await _run()
    for k in _SUMMARY_KEYS:
        assert k in summary, f"요약 키 {k} 누락: {summary}"
    assert summary["mode"] == "on"
    assert summary["truncated"] == 0
    kw = env.list_by_filter.await_args.kwargs
    assert kw.get("min_market_cap") == scanner._DAILY_LOAD_MIN_MCAP_EOK * 100_000_000
    assert kw.get("min_trade_amount") == scanner._DAILY_LOAD_MIN_TRADE_WON
    assert kw.get("is_kospi200") is True and kw.get("is_kosdaq150") is True
    assert summary["quarterly_total"] == 3


async def test_summary_log_line_info_when_no_failure(monkeypatch, caplog):
    Env(monkeypatch)
    with caplog.at_level(logging.DEBUG):
        await _run()
    lines = [r for r in caplog.records if r.getMessage().startswith("[fundamental_extra_load] ")]
    assert len(lines) == 1, [r.getMessage() for r in lines]
    msg = lines[0].getMessage()
    for field in ("quarterly_total=", "quarterly_fetched=", "quarterly_skipped=", "quarterly_failed=",
                  "opinion_tickers=", "opinion_rows=", "opinion_skipped=", "estimate_saved=",
                  "estimate_skipped=", "elapsed_ms=", "mode="):
        assert field in msg, f"{field} 누락: {msg}"
    assert lines[0].levelno == logging.INFO


async def test_summary_log_line_warning_when_any_failure(monkeypatch, caplog):
    env = Env(monkeypatch)
    env.fetch_fin.side_effect = RuntimeError("KIS 500")
    with caplog.at_level(logging.DEBUG):
        summary = await _run()
    assert summary["quarterly_failed"] == 3
    lines = [r for r in caplog.records if r.getMessage().startswith("[fundamental_extra_load] ")]
    assert len(lines) == 1 and lines[0].levelno == logging.WARNING


# ---------------------------------------------------------------------------
# 갈래 1 — 분기 재무
# ---------------------------------------------------------------------------
async def test_quarterly_skip_when_db_has_target_quarter_else_fetch(monkeypatch):
    env = Env(monkeypatch)
    env.max_q = {"005930": "202606", "000660": "202603", "035420": None}  # target = 202606
    summary = await _run()
    assert "max:005930:1" in env.calls, "분기 신선도는 div_cls='1' 로 본다"
    fetched = [c for c in env.calls if c.startswith("fetch:")]
    assert fetched == ["fetch:000660:1", "fetch:035420:1"], fetched
    assert env.upsert_fin.await_count == 2
    assert summary["quarterly_fetched"] == 2
    assert summary["quarterly_skipped"] == 1


async def test_quarterly_ticker_failure_continues(monkeypatch):
    env = Env(monkeypatch)

    async def _boom(ticker, div_cls="0"):
        env.calls.append(f"fetch:{ticker}:{div_cls}")
        if ticker == "000660":
            raise RuntimeError("KIS SESSION FULL")
        return [{"ticker": ticker, "stac_yymm": "202606", "div_cls": div_cls, "raw": {}}]

    env.fetch_fin.side_effect = _boom
    summary = await _run()
    assert len([c for c in env.calls if c.startswith("fetch:")]) == 3
    assert summary["quarterly_failed"] == 1
    assert summary["quarterly_fetched"] == 2


# ---------------------------------------------------------------------------
# 갈래 2 — 투자의견
# ---------------------------------------------------------------------------
def _assert_tiles(windows, start: date, end: date):
    ws = sorted(windows)
    assert ws, "창이 없다"
    assert ws[0][0] == start and ws[-1][1] == end, (ws[0], ws[-1], start, end)
    for (a, b), (c, _d) in zip(ws, ws[1:]):
        assert c == b + timedelta(days=1), f"창 사이 빈틈/겹침: {b} → {c}"
    for a, b in ws:
        assert a <= b and (b - a).days + 1 <= 90, (a, b)


async def test_opinion_no_db_rows_starts_400_days_back_in_90_day_windows(monkeypatch):
    env = Env(monkeypatch, tickers=("005930",))
    summary = await _run()
    start = TODAY - timedelta(days=400)
    wins = env.op_windows("005930")
    _assert_tiles(wins, start, TODAY)
    assert len(wins) == math.ceil(((TODAY - start).days + 1) / 90)
    assert summary["opinion_tickers"] == 1


async def test_opinion_resumes_day_after_latest_db_date(monkeypatch):
    env = Env(monkeypatch, tickers=("005930", "000660"))
    env.latest_dates = {"005930": TODAY - timedelta(days=10), "000660": TODAY}
    await _run()
    _assert_tiles(env.op_windows("005930"), TODAY - timedelta(days=9), TODAY)
    assert len(env.op_windows("005930")) == 1
    assert env.op_windows("000660") == [], "오늘까지 이미 있으면 조회하지 않는다"


async def test_opinion_rows_upserted_and_counted(monkeypatch):
    env = Env(monkeypatch, tickers=("005930",))
    env.latest_dates = {"005930": TODAY - timedelta(days=5)}
    rows = [{"bsop_date": TODAY - timedelta(days=1), "mbcr_name": "SK", "hts_goal_prc": 100000, "raw": {}},
            {"bsop_date": TODAY - timedelta(days=2), "mbcr_name": "KB", "hts_goal_prc": 90000, "raw": {}}]
    env.opinion_resp = lambda t, a, b: list(rows)
    summary = await _run()
    assert env.upsert_op.await_count == 1
    assert env.upsert_op.await_args.args[0] == "005930"
    assert summary["opinion_rows"] == 2


async def test_opinion_truncated_window_is_halved_once(monkeypatch):
    env = Env(monkeypatch, tickers=("005930",))
    env.latest_dates = {"005930": TODAY - timedelta(days=60)}  # 창 1개 = [today-59, today]
    full = [{"bsop_date": TODAY - timedelta(days=i % 50), "mbcr_name": f"B{i}", "hts_goal_prc": 1, "raw": {}}
            for i in range(100)]
    env.opinion_resp = lambda t, a, b: list(full)  # 반쪽도 100건 — 그래도 한 번만 나눈다
    await _run()
    wins = env.op_windows("005930")
    first = (TODAY - timedelta(days=59), TODAY)
    assert wins[0] == first, wins
    halves = wins[1:]
    assert len(halves) == 2, f"100건이면 반으로 나눠 1회 재조회(2창): {wins}"
    _assert_tiles(halves, first[0], first[1])


async def test_opinion_weekly_marker_fresh_skips_branch(monkeypatch):
    env = Env(monkeypatch, config={MARKER_KEY: _marker(3)})
    summary = await _run()
    assert env.inquire_op.await_count == 0
    assert summary["opinion_skipped"] >= 1 or summary["opinion_tickers"] == 0
    assert all(k != MARKER_KEY for k, _ in env.store.writes), "skip 한 날은 마커를 다시 쓰지 않는다"


async def test_opinion_weekly_marker_stale_runs_and_rewrites_marker(monkeypatch):
    env = Env(monkeypatch, config={MARKER_KEY: _marker(8)})
    await _run()
    assert env.inquire_op.await_count >= 3
    written = [v for k, v in env.store.writes if k == MARKER_KEY]
    assert written, "갈래가 돌면 마커를 쓴다"
    val = written[-1]["value"] if isinstance(written[-1], dict) else written[-1]
    assert datetime.fromisoformat(str(val)).date() == TODAY


async def test_opinion_marker_absent_runs(monkeypatch):
    env = Env(monkeypatch)
    await _run()
    assert env.inquire_op.await_count >= 3
    assert any(k == MARKER_KEY for k, _ in env.store.writes)


# ---------------------------------------------------------------------------
# 갈래 3 — 추정실적 월 스냅샷
# ---------------------------------------------------------------------------
async def test_estimate_skips_tickers_with_this_month_row(monkeypatch):
    env = Env(monkeypatch)
    env.est_have = {"005930"}
    summary = await _run()
    assert env.est_tickers.await_args.args[0] == date(2026, 10, 1)
    asked = [c.args[0] for c in env.inquire_est.await_args_list]
    assert sorted(asked) == ["000660", "035420"]
    saved = env.upsert_est.await_args_list
    assert sorted(c.args[0] for c in saved) == ["000660", "035420"]
    assert all(c.args[1] == date(2026, 10, 1) for c in saved), "snapshot_month = 그 달 1일"
    assert summary["estimate_saved"] == 2
    assert summary["estimate_skipped"] >= 1


@pytest.mark.parametrize("empty", [None, {"ticker": "x", "raw": {}, "settle_months": []}], ids=["none", "no_months"])
async def test_estimate_empty_response_not_saved(monkeypatch, empty):
    env = Env(monkeypatch, tickers=("005930",))
    env.est_resp = lambda t: empty
    summary = await _run()
    assert env.inquire_est.await_count == 1
    assert env.upsert_est.await_count == 0
    assert summary["estimate_saved"] == 0


# ---------------------------------------------------------------------------
# 킬스위치
# ---------------------------------------------------------------------------
async def test_killswitch_off_skips_all_branches(monkeypatch):
    env = Env(monkeypatch, config={MODE_KEY: {"value": "off"}})
    summary = await _run()
    assert summary["mode"] == "off"
    for m in (env.fetch_fin, env.inquire_op, env.inquire_est, env.upsert_fin, env.upsert_op, env.upsert_est):
        assert m.await_count == 0
    assert env.store.writes == []


async def test_killswitch_missing_key_means_on(monkeypatch):
    env = Env(monkeypatch)
    summary = await _run()
    assert summary["mode"] == "on"
    assert env.fetch_fin.await_count == 3


async def test_killswitch_typo_means_on_with_warning(monkeypatch, caplog):
    env = Env(monkeypatch, config={MODE_KEY: {"value": "of"}})
    with caplog.at_level(logging.DEBUG):
        summary = await _run()
    assert summary["mode"] == "on"
    assert env.fetch_fin.await_count == 3
    assert any(r.levelno == logging.WARNING and MODE_KEY in r.getMessage() for r in caplog.records)


async def test_killswitch_read_every_run(monkeypatch):
    env = Env(monkeypatch)
    await _run()
    env.store.data[MODE_KEY] = {"value": "off"}
    before = env.fetch_fin.await_count
    summary = await _run()
    assert summary["mode"] == "off" and env.fetch_fin.await_count == before


# ---------------------------------------------------------------------------
# 갈래 격리 · never-raise · 하드캡
# ---------------------------------------------------------------------------
async def test_branch_exception_isolated(monkeypatch):
    env = Env(monkeypatch)
    env.max_stac.side_effect = RuntimeError("pg down")
    env.upsert_fin.side_effect = RuntimeError("pg down")
    env.latest_bsop.side_effect = RuntimeError("pg down")
    summary = await _run()
    assert env.inquire_est.await_count == 3, "앞 갈래가 깨져도 추정실적 갈래는 돈다"
    assert isinstance(summary, dict)


async def test_never_raise_on_universe_failure(monkeypatch):
    env = Env(monkeypatch)
    env.list_by_filter.side_effect = RuntimeError("pg down")
    summary = await _run()
    assert isinstance(summary, dict)
    assert env.fetch_fin.await_count == 0


async def test_never_raise_on_config_read_failure(monkeypatch):
    env = Env(monkeypatch)

    async def _boom(key):
        raise RuntimeError("pg down")

    monkeypatch.setattr(sc_db, "_select_value", _boom)
    summary = await _run()
    assert isinstance(summary, dict)


async def test_cancelled_error_propagates(monkeypatch):
    env = Env(monkeypatch)
    env.fetch_fin.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await _run()


async def test_hard_cap_truncates(monkeypatch):
    env = Env(monkeypatch)
    monkeypatch.setattr(flt, "EXTRA_LOAD_HARD_CAP_SECS", -1)
    summary = await _run()
    assert summary["truncated"] == 1
    assert env.fetch_fin.await_count < 3, "상한을 넘으면 남은 종목은 다음 실행으로 미룬다"


async def test_now_kst_default_is_accepted(monkeypatch):
    Env(monkeypatch)
    summary = await flt.run_extra_loads_once()
    assert isinstance(summary, dict) and "mode" in summary
