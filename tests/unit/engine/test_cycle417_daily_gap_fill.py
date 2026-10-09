"""cycle417 (2026-10-09) — 일봉 증분 적재 구멍 메우기 (Red).

계약 = `_workspace/red/cycle417/gap_fill_contract.md`.

## 왜

`_stock_master_daily_load_once` 의 증분 분기(`existing_count >= 225`)는
`fetch_daily_candles(days=7)` 로 **최근 7봉만** 받는다. 깊이 판정은 행 수뿐이라,
7영업일 넘게 적재 대상 밖에 있다가 돌아온 종목은 그 사이가 **영영 빈다**
(메인 세션 운영 DB 실측 10-08: 대상 1,029종목 중 14종목·34일, 전부 09-21~09-28).
신선도 게이트(`DAILY_STALENESS_DAYS=4`)는 마지막 날짜만 봐서 못 잡는다 —
20일 고가·ATR·EMA 가 빈 날을 건너뛰고 계산된다.

## 무엇을

- 적재 실행마다 **한 번** `stock_master_daily.earliest_missing_bas_dd(all_tickers, before=today)`
  로 종목별 「첫 행 이후 시장 달력에서 빠진 가장 이른 날」을 받는다(쿼리 1~2회, 종목당 0).
- 증분 분기에서 구멍이 있는 종목만 `fetch_days = clamp(_gap_fill_need_days(빈 날, 오늘), 7, 100)`.
  `_gap_fill_need_days` = 빈 날부터 오늘까지 **평일 수(양 끝 포함, 휴일 미차감)** + 2.
- KIS 호출은 여전히 **종목당 1콜**(창만 넓힌다).
- 관측 = 실행당 1행 INFO `[daily_load_gap_fill] tickers= widened= max_fetch_days=
  beyond_horizon= errors=` + `summary["gap_fill"]`. 판정 예외 = fail-open(7봉) + WARNING
  `[daily_load_gap_fill_skipped]` 실행당 1행.

## 무변경 (이 파일이 함께 잠근다)

깊은 backfill 분기 · `skipped_fresh` · `force` · 보호 종목 포함 규약 · 구멍 없는 종목 = 7.

## 매매 안전성

20:30 일봉 적재 = 매수 진입 **전** 데이터 계층(사이클 38). 매매 행위 무변경 —
risk / order_engine / realtime / auth 무접촉.
"""

from __future__ import annotations

import ast
import inspect
import logging
import re
import textwrap
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from src.engine import scanner

pytestmark = pytest.mark.unit

_SCANNER_LOGGER = "src.engine.scanner"
_GAP_INFO = "[daily_load_gap_fill] "        # 뒤 공백까지가 접두 — `_skipped` 와 겹치지 않는다
_GAP_WARN = "[daily_load_gap_fill_skipped]"
_HELPER = "earliest_missing_bas_dd"

_TODAY = date(2026, 10, 12)                 # 월요일
_NIGHT = "2026-10-12T20:30:00+09:00"        # 정기 적재(커트오프 20:00 뒤)
_MORNING = "2026-10-12T07:50:00+09:00"      # 부팅 immediate(커트오프 앞)
_LAST_LOADED = date(2026, 10, 8)            # 직전 영업일 헤드(10-09 한글날 휴장)
_CONVERGED = 240                            # >= 225 → 증분 분기
_SHALLOW = 224                              # < 225 → 깊은 backfill 분기

_MCAP_EOK_OK = "600"                        # 억원 (>= 500)
_TRADE_WON_OK = "6000000000"                # 원 (>= 10억)


# ══════════════════════════════════════════════════════════════════════
# 대역
# ══════════════════════════════════════════════════════════════════════
def _candle(d: date) -> dict:
    ymd = d.strftime("%Y%m%d")
    return {
        "stck_bsop_date": ymd, "stck_clpr": "71000", "stck_oprc": "70500",
        "stck_hgpr": "71500", "stck_lwpr": "70000",
        "acml_vol": "12345678", "acml_tr_pbmn": "876543210000",
    }


def _qualifier(ticker: str) -> dict:
    """비지수 + 시총·거래대금 자격 통과 = 적재 대상."""
    return {"ticker": ticker, "is_kospi200": False, "is_kosdaq150": False,
            "raw": {"hts_avls": _MCAP_EOK_OK, "acml_tr_pbmn": _TRADE_WON_OK}}


def _non_qualifier(ticker: str) -> dict:
    """자격 미달 — 보호(보유/익일청산)로만 적재 대상에 든다."""
    return {"ticker": ticker, "is_kospi200": False, "is_kosdaq150": False,
            "raw": {"hts_avls": "100", "acml_tr_pbmn": "900000000"}}


class _Load:
    """`_stock_master_daily_load_once` 1회 실행의 대역 묶음.

    - `gaps`        : 헬퍼가 돌려줄 {ticker: 가장 이른 빈 날}
    - `gap_exc`     : 헬퍼가 던질 예외(fail-open 검증)
    - `counts`      : 종목별 행 수(기본 240 = 증분 분기)
    - `latest`      : 종목별 max_bas_dd(기본 10-08 = 신선하지 않음)
    - `patch_helper`: False 면 헬퍼를 대역하지 않는다(기존 15파일과 같은 상태)
    """

    def __init__(self, rows: list[dict], *, gaps: dict | None = None,
                 gap_exc: BaseException | None = None,
                 counts: dict[str, int] | None = None,
                 latest: dict[str, date] | None = None,
                 patch_helper: bool = True) -> None:
        self.rows = rows
        self.counts = counts or {}
        self.latest = latest or {}
        self.fetch_calls: list[tuple[str, int]] = []
        self.backfill_calls: list[tuple[str, int]] = []
        if gap_exc is not None:
            self.helper = AsyncMock(side_effect=gap_exc)
        else:
            self.helper = AsyncMock(return_value=dict(gaps or {}))
        self.patch_helper = patch_helper

    async def _max_bas_dd(self, ticker=None):
        return self.latest.get(ticker, _LAST_LOADED)

    async def _count(self, ticker):
        return self.counts.get(ticker, _CONVERGED)

    async def _fetch(self, ticker, days):
        # 호출부가 `days=` 키워드로 넘기는 것이 기존 계약이다(cycle302 `_capture_fetch_days`).
        self.fetch_calls.append((ticker, days))
        return [_candle(_LAST_LOADED)]

    async def _backfill(self, ticker, *, total_days):
        self.backfill_calls.append((ticker, total_days))
        return [_candle(_LAST_LOADED)]

    def days_of(self, ticker: str) -> list[int]:
        return [d for t, d in self.fetch_calls if t == ticker]

    async def run(self, *, force: bool = False) -> dict:
        daily_kwargs = dict(
            max_bas_dd=AsyncMock(side_effect=self._max_bas_dd),
            count_by_ticker=AsyncMock(side_effect=self._count),
            upsert_batch=AsyncMock(return_value=1),
        )
        if self.patch_helper:
            daily_kwargs[_HELPER] = self.helper
        with patch.multiple("src.db.stock_master",
                            list_all=AsyncMock(side_effect=[self.rows, []])), \
             patch.multiple("src.db.stock_master_daily", create=True, **daily_kwargs), \
             patch.multiple("src.api.condition",
                            fetch_daily_candles=AsyncMock(side_effect=self._fetch),
                            fetch_daily_candles_backfill=AsyncMock(side_effect=self._backfill)), \
             patch("asyncio.sleep", new=AsyncMock()):
            return await scanner._stock_master_daily_load_once(force=force)


def _records(caplog, prefix: str, *, min_level: int) -> list[logging.LogRecord]:
    """로거명 + 레벨 + 접두 3중 한정 (CI 루트 로거 DEBUG 내성)."""
    return [
        r for r in caplog.records
        if r.name == _SCANNER_LOGGER and r.levelno >= min_level
        and r.getMessage().startswith(prefix)
    ]


def _field(line: str, key: str) -> str | None:
    m = re.search(rf"\b{re.escape(key)}=([^\s]+)", line)
    return m.group(1) if m else None


@pytest.fixture
def held(monkeypatch):
    """보유 종목 주입 — `_collect_protected_tickers_for_scanner` 의 테스트 seam(cycle302 답습)."""
    def _apply(positions=()):
        reg = SimpleNamespace(all=lambda: [SimpleNamespace(
            state=SimpleNamespace(positions={t: {} for t in positions}))])
        monkeypatch.setattr(scanner, "registry", reg, raising=False)
        import src.engine.scheduler as sched
        monkeypatch.setattr(
            sched, "trading_scheduler",
            SimpleNamespace(_pending_next_day_clear=[], registry=reg),
            raising=False,
        )
    return _apply


# ══════════════════════════════════════════════════════════════════════
# P — 순수 함수 `_gap_fill_need_days` + 상수
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    ("earliest", "today", "need"),
    [
        # 실측 결함 구간: 09-21(월) ~ 10-12(월) 평일 16일 + 여유 2
        (date(2026, 9, 21), date(2026, 10, 12), 18),
        # 다음 밤 — 평일 하나 더
        (date(2026, 9, 21), date(2026, 10, 13), 19),
        # 오늘 하루(평일 1) + 2
        (date(2026, 10, 12), date(2026, 10, 12), 3),
        # 주말에서 시작해도 평일만 센다(토·일 0 + 월 1)
        (date(2026, 10, 10), date(2026, 10, 12), 3),
        # 하한 경계 쪽 값(clamp 전) — 화요일부터 = 평일 5 + 2
        (date(2026, 10, 6), date(2026, 10, 12), 7),
        # 휴일은 빼지 않는다 — 10-09(금, 한글날)도 평일로 센다(목·금·월 = 3)
        (date(2026, 10, 8), date(2026, 10, 12), 5),
        # 상한 경계 — 정확히 100 / 101
        (date(2026, 5, 28), date(2026, 10, 12), 100),
        (date(2026, 5, 27), date(2026, 10, 12), 101),
    ],
    ids=["gap_0921", "gap_0921_next_night", "today_only", "weekend_start",
         "need_7", "holiday_counted", "need_100", "need_101"],
)
def test_p1_need_days_is_weekdays_inclusive_plus_margin(earliest, today, need):
    """평일 수(양 끝 포함, 휴일 미차감) + 2.

    휴일을 빼지 않는 것이 **안전 방향**이다 — `fetch_daily_candles` 는 최근 N봉
    (`output[:N]`)을 받으므로 N 이 실제 영업일 수보다 크면 구멍 날짜를 반드시 포함하고,
    작으면 구멍을 놓친다. KIS 휴장 API(`trading_calendar`)는 이 경로에서 부르지 않는다.
    """
    assert scanner._gap_fill_need_days(earliest, today) == need


def test_p2_constants():
    """하한 7(현행 증분 창) · 여유 2 · 상한 100(KIS 1회 한도) — 값과 관계를 핀한다."""
    assert scanner._DAILY_LOAD_INCREMENTAL_DAYS == 7
    assert scanner._DAILY_LOAD_GAP_MARGIN_DAYS == 2
    assert scanner._DAILY_LOAD_FETCH_DAYS == 100
    assert scanner._DAILY_LOAD_INCREMENTAL_DAYS < scanner._DAILY_LOAD_FETCH_DAYS


# ══════════════════════════════════════════════════════════════════════
# W — 구멍 종목의 창 확대 (핵심)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("clock", [_NIGHT, _MORNING], ids=["2030_after_cutoff", "0750_before_cutoff"])
async def test_w1_gap_ticker_widens_to_need_days(clock):
    """09-21 구멍 + 오늘 10-12 → fetch_days 18 (평일 16 + 2). 시각(커트오프 앞·뒤)과 무관.

    현행(Red) = 7 — 그 7봉(10-12 기준 달력 20일)은 09-21~09-28 을 닿지 못해 구멍이 영구화된다.
    """
    load = _Load([_qualifier("003200")], gaps={"003200": date(2026, 9, 21)})
    with freeze_time(clock):
        summary = await load.run()

    assert load.days_of("003200") == [18], (
        f"구멍 종목은 빈 날까지 닿는 창을 받아야 한다 — 실측 {load.fetch_calls}"
    )
    assert load.backfill_calls == [], "증분 분기 종목은 분할 backfill 을 겸하지 않는다"
    assert summary["fetched"] == 1


async def test_w2_no_gap_ticker_keeps_seven():
    """구멍 없는 종목은 현행 그대로 7 — 정상 운영(수렴 유니버스)의 호출 모양 불변."""
    load = _Load([_qualifier("005930"), _qualifier("000660")], gaps={})
    with freeze_time(_NIGHT):
        await load.run()
    assert sorted(load.fetch_calls) == [("000660", 7), ("005930", 7)], (
        f"실측 {load.fetch_calls}"
    )


@pytest.mark.parametrize(
    ("earliest", "expected", "widened", "beyond"),
    [
        (date(2026, 10, 8), 7, 0, 0),      # need 5 → 하한 7 (확대 아님)
        (date(2026, 10, 6), 7, 0, 0),      # need 7 → 7 (경계, 확대 아님)
        (date(2026, 10, 5), 8, 1, 0),      # need 8 → 8 (하한 바로 위)
        (date(2026, 5, 28), 100, 1, 0),    # need 100 → 100 (경계 — 잘리지 않았다)
        (date(2026, 5, 27), 100, 1, 1),    # need 101 → 상한 100 (잘림)
        (date(2026, 4, 1), 100, 1, 1),     # need 141 → 상한 100 (잘림)
    ],
    ids=["floor_need5", "floor_need7", "need8", "cap_need100", "cap_need101", "cap_need141"],
)
async def test_w3_fetch_days_clamped_between_7_and_100(earliest, expected, widened, beyond):
    """하한 7 = 현행 보정 창(직전 영업일 봉 재기록, cycle263 G2) 보존 · 상한 100 = KIS 1회 한도.

    `widened` = 7 보다 큰 창을 요청했는가 · `beyond_horizon` = 필요 창이 100 을 **넘어** 잘렸는가
    (정확히 100 은 잘린 것이 아니다).
    """
    load = _Load([_qualifier("001060")], gaps={"001060": earliest})
    with freeze_time(_NIGHT):
        summary = await load.run()
    assert load.days_of("001060") == [expected], f"실측 {load.fetch_calls}"
    assert load.backfill_calls == []
    assert summary["gap_fill"]["widened"] == widened
    assert summary["gap_fill"]["beyond_horizon"] == beyond
    assert summary["gap_fill"]["max_fetch_days"] == (expected if widened else 0)


# ══════════════════════════════════════════════════════════════════════
# K — KIS 호출 수 불변 (종목당 1콜)
# ══════════════════════════════════════════════════════════════════════
async def test_k1_one_kis_call_per_ticker_including_gap_tickers():
    """구멍·무구멍·상한 초과 섞여도 KIS 호출은 종목 수와 같다 — 창만 넓힌다."""
    rows = [_qualifier(t) for t in ("000010", "000020", "000030", "000040")]
    load = _Load(rows, gaps={
        "000010": date(2026, 9, 21),
        "000030": date(2026, 4, 1),
    })
    with freeze_time(_NIGHT):
        await load.run()

    per_ticker = {t: len(load.days_of(t)) for t in ("000010", "000020", "000030", "000040")}
    assert per_ticker == {"000010": 1, "000020": 1, "000030": 1, "000040": 1}, (
        f"종목당 정확히 1콜 — 실측 {load.fetch_calls}"
    )
    assert load.backfill_calls == [], "수렴 종목에 분할 backfill(3콜) 금지"


async def test_k2_halted_gap_persists_next_night_same_call_count():
    """거래정지 등으로 KIS 가 빈 날의 봉을 주지 않아 구멍이 남아도 — 다음 밤에도 1콜.

    밤마다 창이 평일 수만큼 커질 뿐 호출 수는 늘지 않고, 창은 100 에서 멈춘다(무한 증가 없음).
    """
    gap = {"003200": date(2026, 9, 21)}

    night1 = _Load([_qualifier("003200")], gaps=gap)
    with freeze_time("2026-10-12T20:30:00+09:00"):
        await night1.run()

    night2 = _Load([_qualifier("003200")], gaps=gap, latest={"003200": date(2026, 10, 12)})
    with freeze_time("2026-10-13T20:30:00+09:00"):
        await night2.run()

    far = _Load([_qualifier("003200")], gaps=gap, latest={"003200": date(2027, 3, 1)})
    with freeze_time("2027-03-02T20:30:00+09:00"):
        await far.run()

    assert night1.days_of("003200") == [18]
    assert night2.days_of("003200") == [19], (
        "다음 밤 = 평일 하나 더(19). 구멍이 남았다고 추가 호출·재시도를 하지 않는다 — "
        f"실측 {night2.fetch_calls}"
    )
    assert far.days_of("003200") == [100], f"창은 100 에서 멈춘다 — 실측 {far.fetch_calls}"
    for night in (night1, night2, far):
        assert len(night.fetch_calls) == 1 and night.backfill_calls == []


# ══════════════════════════════════════════════════════════════════════
# U — 기존 분기·규약 무변경
# ══════════════════════════════════════════════════════════════════════
async def test_u1_deep_backfill_branch_unchanged_even_with_gap():
    """행 수 < 225 는 구멍과 무관하게 현행 225일 분할 backfill — 단발 fetch 를 겸하지 않는다."""
    load = _Load([_qualifier("000050")], gaps={"000050": date(2026, 9, 21)},
                 counts={"000050": _SHALLOW})
    with freeze_time(_NIGHT):
        await load.run()
    assert load.backfill_calls == [("000050", scanner._DAILY_LOAD_VCP_BACKFILL_DAYS)]
    assert load.fetch_calls == []


async def test_u2_skipped_fresh_unchanged_even_with_gap(caplog):
    """오늘 봉이 이미 있으면(force=False) 구멍이 있어도 skip — 구멍은 다음 밤에 메운다."""
    load = _Load([_qualifier("000070")], gaps={"000070": date(2026, 9, 21)},
                 latest={"000070": _TODAY})
    with freeze_time(_NIGHT), caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        summary = await load.run()
    assert load.fetch_calls == [] and load.backfill_calls == []
    assert summary["skipped_fresh"] == 1
    assert summary["gap_fill"]["widened"] == 0


async def test_u3_force_bypasses_fresh_skip_and_widens():
    """force 는 멱등 skip 만 우회한다 — 분기 규칙(구멍 확대 포함)은 같다."""
    load = _Load([_qualifier("000070"), _qualifier("000080")],
                 gaps={"000070": date(2026, 9, 21)},
                 latest={"000070": _TODAY, "000080": _TODAY})
    with freeze_time(_NIGHT):
        await load.run(force=True)
    assert load.days_of("000070") == [18]
    assert load.days_of("000080") == [7]


async def test_u4_protected_ticker_follows_same_rule(held, caplog):
    """보호 종목(자격 미달·보유)은 포함 규약 그대로 적재 대상이고, 구멍 규칙도 같게 탄다."""
    held(positions=("004690",))
    load = _Load([_qualifier("005930"), _non_qualifier("004690")],
                 gaps={"004690": date(2026, 9, 21)})
    with freeze_time(_NIGHT), caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        await load.run()

    assert load.days_of("004690") == [18], f"실측 {load.fetch_calls}"
    assert load.days_of("005930") == [7]
    sent = load.helper.await_args
    sent_tickers = sent.kwargs.get("tickers", sent.args[0] if sent.args else None)
    assert "004690" in list(sent_tickers), "구멍 판정 대상 = 보호 종목 포함 적재 대상 전부"
    protected_lines = _records(caplog, "[daily_load_protected_forced]", min_level=logging.INFO)
    assert len(protected_lines) == 1, "보호 마커는 그대로 실행당 1행"


# ══════════════════════════════════════════════════════════════════════
# C — 판정 호출 계약 (실행당 1회, 쿼리 1~2회)
# ══════════════════════════════════════════════════════════════════════
async def test_c1_helper_called_once_per_run_with_all_targets_and_today():
    """판정은 실행당 **한 번** — 종목당 조회 금지. 인자 = 적재 대상 전부 + `before=오늘`."""
    tickers = ["000010", "000020", "000030", "000040", "000050"]
    load = _Load([_qualifier(t) for t in tickers], gaps={})
    with freeze_time(_NIGHT):
        await load.run()

    assert load.helper.await_count == 1, (
        f"구멍 판정은 실행당 1회 — 실측 {load.helper.await_count}회"
    )
    call = load.helper.await_args
    sent = call.kwargs.get("tickers", call.args[0] if call.args else None)
    assert sent is not None and sorted(sent) == tickers, f"실측 인자 {call}"
    assert call.kwargs.get("before") == _TODAY, (
        f"달력은 오늘 이전 날짜로만 만든다(`before=` 키워드) — 실측 {call.kwargs}"
    )


# ══════════════════════════════════════════════════════════════════════
# O — 관측: 실행당 1행 INFO + summary["gap_fill"]
# ══════════════════════════════════════════════════════════════════════
async def test_o1_marker_once_per_run_with_exact_fields(caplog):
    """A(18 확대) · B(7 — 하한) · C(100 — 상한 초과) · D(무구멍) · E(얕음 → backfill) + 대상 밖 1.

    tickers = 판정이 구멍을 보고한 **적재 대상** 종목 수(A·B·C·E = 4, 대상 밖 999999 제외)
    widened = 증분 분기에서 7 보다 큰 창을 요청한 종목 수(A·C = 2)
    max_fetch_days = widened 종목 창의 최댓값(100) · beyond_horizon = 필요 창 > 100 이라 잘린 수(C = 1)
    """
    rows = [_qualifier(t) for t in ("000010", "000020", "000030", "000040", "000050")]
    load = _Load(rows, gaps={
        "000010": date(2026, 9, 21),
        "000020": date(2026, 10, 8),
        "000030": date(2026, 5, 27),
        "000050": date(2026, 9, 21),
        "999999": date(2026, 9, 21),
    }, counts={"000050": _SHALLOW})
    with freeze_time(_NIGHT), caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        summary = await load.run()

    lines = _records(caplog, _GAP_INFO, min_level=logging.INFO)
    assert len(lines) == 1, (
        f"`[daily_load_gap_fill]` 는 실행당 정확히 1행(종목당 금지) — 실측 {len(lines)}행"
    )
    msg = lines[0].getMessage()
    assert lines[0].levelno == logging.INFO
    want = {"tickers": "4", "widened": "2", "max_fetch_days": "100",
            "beyond_horizon": "1", "errors": "0"}
    got = {k: _field(msg, k) for k in want}
    assert got == want, f"실측 {msg!r}"
    assert summary["gap_fill"] == {
        "tickers": 4, "widened": 2, "max_fetch_days": 100,
        "beyond_horizon": 1, "errors": 0,
    }
    # 호출 모양: 증분 4콜(18·7·100·7) + backfill 1
    assert sorted(load.fetch_calls) == [
        ("000010", 18), ("000020", 7), ("000030", 100), ("000040", 7),
    ]
    assert load.backfill_calls == [("000050", scanner._DAILY_LOAD_VCP_BACKFILL_DAYS)]
    for k in ("total", "fetched", "upserted_rows", "skipped_fresh", "failed",
              "db_write_failures", "elapsed_ms", "mode"):
        assert k in summary, f"기존 summary 키 `{k}` 소실"


async def test_o2_marker_on_clean_run_is_all_zero(caplog):
    """구멍이 없어도 1행은 남긴다 — 「판정이 돌았고 구멍 0」 과 「판정이 안 돌았다」 를 가른다."""
    load = _Load([_qualifier("005930")], gaps={})
    with freeze_time(_NIGHT), caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        summary = await load.run()
    lines = _records(caplog, _GAP_INFO, min_level=logging.INFO)
    assert len(lines) == 1
    msg = lines[0].getMessage()
    assert {k: _field(msg, k) for k in
            ("tickers", "widened", "max_fetch_days", "beyond_horizon", "errors")} == {
        "tickers": "0", "widened": "0", "max_fetch_days": "0",
        "beyond_horizon": "0", "errors": "0",
    }, f"실측 {msg!r}"
    assert summary["gap_fill"]["tickers"] == 0
    assert _records(caplog, _GAP_WARN, min_level=logging.WARNING) == []


# ══════════════════════════════════════════════════════════════════════
# F — fail-open (판정 실패가 적재를 막지 않는다)
# ══════════════════════════════════════════════════════════════════════
async def test_f1_helper_exception_fails_open_to_seven_with_one_warning(caplog):
    """판정 예외 → 구멍 판정 없이 현행 7봉 + WARNING 실행당 1행 + errors=1."""
    rows = [_qualifier(t) for t in ("000010", "000020", "000030")]
    load = _Load(rows, gap_exc=RuntimeError("db down"))
    with freeze_time(_NIGHT), caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        summary = await load.run()

    assert sorted(load.fetch_calls) == [("000010", 7), ("000020", 7), ("000030", 7)]
    assert summary["fetched"] == 3 and summary["failed"] == 0, (
        "판정 실패를 KIS 실패(`failed`)로 세지 않는다"
    )
    warns = _records(caplog, _GAP_WARN, min_level=logging.WARNING)
    assert len(warns) == 1, f"fail-open 흔적은 실행당 1행 WARNING — 실측 {len(warns)}행"
    assert _field(warns[0].getMessage(), "reason") == "gap_scan_error"
    info = _records(caplog, _GAP_INFO, min_level=logging.INFO)
    assert len(info) == 1 and _field(info[0].getMessage(), "errors") == "1"
    assert summary["gap_fill"]["errors"] == 1
    assert summary["gap_fill"]["widened"] == 0


async def test_f2_unpatched_helper_without_pool_fails_open(monkeypatch, caplog):
    """기존 15파일의 상태 재현 — 헬퍼를 대역하지 않고 풀이 없으면 예외 → fail-open(7봉).

    이 경로가 기존 일봉 적재 테스트들이 `earliest_missing_bas_dd` 를 몰라도 초록인 이유다
    (중립화 픽스처를 두지 않는 근거 = 계약 §6).
    """
    import src.db.pg as pg
    monkeypatch.setattr(pg, "_pool", None)
    load = _Load([_qualifier("005930")], patch_helper=False)
    with freeze_time(_NIGHT), caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        summary = await load.run()
    assert load.fetch_calls == [("005930", 7)]
    assert len(_records(caplog, _GAP_WARN, min_level=logging.WARNING)) == 1
    assert summary["gap_fill"]["errors"] == 1


async def test_f3_non_date_value_is_ignored_and_counted(caplog):
    """헬퍼가 날짜가 아닌 값을 주면 그 종목만 7(구멍 없음 취급) + errors 증가 · 다른 종목은 정상."""
    rows = [_qualifier("000010"), _qualifier("000020")]
    load = _Load(rows, gaps={"000010": "2026-09-21", "000020": date(2026, 9, 21)})
    with freeze_time(_NIGHT), caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        summary = await load.run()
    assert load.days_of("000010") == [7]
    assert load.days_of("000020") == [18]
    assert summary["gap_fill"]["errors"] == 1
    assert summary["gap_fill"]["tickers"] == 1
    assert len(_records(caplog, _GAP_WARN, min_level=logging.WARNING)) == 1


# ══════════════════════════════════════════════════════════════════════
# A — 소스 구조 (행위 테스트가 못 보는 우회 구현 차단)
# ══════════════════════════════════════════════════════════════════════
def _load_once_tree() -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(scanner._stock_master_daily_load_once)))


def _calls_named(tree: ast.AST, name: str) -> list[ast.Call]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            fname = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if fname == name:
                out.append(node)
    return out


def _inside_loop(tree: ast.AST, target: ast.AST) -> bool:
    loops = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp,
             ast.DictComp, ast.GeneratorExp)
    for node in ast.walk(tree):
        if isinstance(node, loops) and node is not target:
            if any(child is target for child in ast.walk(node)):
                return True
    return False


def test_a1_gap_scan_called_once_outside_ticker_loop():
    """판정 호출은 함수 안에 정확히 1곳, 종목 루프 **밖** — 종목당 쿼리 금지."""
    tree = _load_once_tree()
    calls = _calls_named(tree, _HELPER)
    assert len(calls) == 1, f"`{_HELPER}` 호출 자리 {len(calls)}곳 (기대 1)"
    assert not _inside_loop(tree, calls[0]), "판정 호출이 루프 안에 있다 — 종목당 쿼리가 된다"


def test_a2_kis_call_sites_unchanged():
    """KIS 호출 자리는 그대로 두 곳 — 구멍 메우기는 창(`days=`)만 바꾼다."""
    tree = _load_once_tree()
    assert len(_calls_named(tree, "fetch_daily_candles")) == 1
    assert len(_calls_named(tree, "fetch_daily_candles_backfill")) == 1
    assert _calls_named(tree, "fetch_daily_candles_ranged") == []


def test_a3_no_kis_holiday_api_in_load_path():
    """영업일 수는 평일 산술로 센다 — KIS 휴장 API·직접 KIS 호출을 끌어들이지 않는다."""
    src = inspect.getsource(scanner._stock_master_daily_load_once)
    need_src = inspect.getsource(scanner._gap_fill_need_days)
    for banned in ("trading_calendar", "is_trading_day", "kis_get"):
        assert banned not in src, f"적재 함수에 `{banned}` — KIS 휴장/직접 호출 금지"
        assert banned not in need_src, f"`_gap_fill_need_days` 에 `{banned}`"
