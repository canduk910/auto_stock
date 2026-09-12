"""cycle263 Red (2026-09-06) — 일봉 적재 껍데기 봉 시정 (라) = (가) + (다).

명세 = `_workspace/specs/cycle263_daily_load_stub_fix.md`
자문 = `_workspace/consult/2026-09-06_daily_load_stub_bar.md` (본문 §2·§3·§6 + 부록 A-1·A-6)

결함(실측): `_stock_master_daily_load_once` 의 멱등 규칙(`latest >= today` skip)이,
기동 직후 immediate run(07:56)이 장 전 KIS 로부터 받은 **오늘 날짜 껍데기 봉**
(O=H=L=C=전일종가, 거래량 0)을 먼저 쓰는 바람에 **그날 16:00 을 전 종목 skip** 시킨다.
오염 경로는 "오늘 스텁"이 아니라 **"어제 스텁"** — `_boot` 의 prepare 가 적재보다 4분
먼저 돌아, 그 시점 테이블 헤드(어제 날짜 껍데기)를 `prev_idx` 가드가 통과시킨다.

시정 두 축:
- **(가)** `data_load_tasks.stock_master_daily_load_task_loop` 의 `run_periodic_task_loop`
  호출에 `immediate_skip_if_fresh_hours=IMMEDIATE_FRESH_SKIP_HOURS`(20.0) 추가 — 8영역 밖.
- **(다)** `scanner._stock_master_daily_load_once` 가 `fetched += 1` **뒤** ·
  `upsert_batch` **앞**에서 **함수 진입 시각이 20:00 KST(cycle283) 이전이면 `bas_dd == today` 캔들을
  폐기** — 8영역(사용자 결정 09-06 카드 ④ 승인).

────────────────────────────────────────────────────────────────────────────
Green 이 맞춰야 하는 seam (이 파일이 정의하는 계약)
────────────────────────────────────────────────────────────────────────────
1) `scanner._DAILY_LOAD_TODAY_BAR_CUTOFF: datetime.time = time(20, 0)`  # cycle283 (구 15:40)
   — scanner.py **전용 상수**(매매 시각 상수 `TIME_POST_NXT_OPEN` 재사용 금지, C5).
2) `scanner._drop_today_bars(candles, *, now_kst, today) -> list[dict]`
   — 순수 함수(부작용·await 0). 입력 리스트 비파괴. 판정 규칙:
     * `now_kst.time() <  cutoff` → `bas_dd >= today` 인 캔들 폐기
     * `now_kst.time() >= cutoff` → `bas_dd >  today` 인 캔들만 폐기(시계 왜곡 방어)
     * `bas_dd` 파싱 불가/빈 문자열 → **보존**(fail-open 방향)
3) 호출부는 `now_kst = datetime.now(KST)` 를 **루프 밖에서 1회** 계산하고,
   필터 호출을 `try/except` 로 감싸 예외 시 **원본 전량 upsert**(C4 fail-open) +
   `[daily_load_today_filter_skipped]` WARNING **실행당 최대 1행**.
4) 관측 마커 `[daily_load_today_bar_filter]` — **실행당 정확히 1행** INFO
   (`mode=drop|keep cutoff=20:00 now=HH:MM today=YYYY-MM-DD dropped_rows=N
   tickers_affected=M`). 종목당 emit 금지(cycle237 로그 폭주 교훈).

Red 유효성(현재 소스):
- A 계열 — 게이트 인자 미전달 → 마커 조회 0건 → immediate 무조건 실행 → FAIL.
- B/D 계열 — `_drop_today_bars` / `_DAILY_LOAD_TODAY_BAR_CUTOFF` 부재 → AttributeError.
- C/F 계열 — 마커 미발화 · 오늘봉 그대로 upsert → FAIL.
- E3/G — **불변식**(현재도 PASS). Green 이 깨뜨리면 안 되는 구조 전제.

기존 테스트 무수정 원칙: `test_cycle122_daily_load_task.py`(적재 본체 회귀) ·
`test_cycle134_task_loop_helper.py`(헬퍼 lifecycle) · `test_cycle193_immediate_fresh_gate.py`
(게이트 *일반* 의미론)는 손대지 않는다. 이 파일은 **daily_load 로의 배선**과
**오늘봉 필터**라는 새 계약만 덮는다.

⚠️ 의미 반전(C8): 시정 후 16:00 의 `skipped_fresh` 가 ~1,000 → ~0 이 된다.
   배포 전후 로그를 같은 grep 으로 **합산 금지**.

────────────────────────────────────────────────────────────────────────────
🔁 cycle283 재기준선 (2026-09-11, 사용자 결정 D1) — 커트오프 15:40 → **20:00**
────────────────────────────────────────────────────────────────────────────
09-14(월)부터 KRX 애프터마켓(16:00~20:00 실시간 체결)이 신설돼 **그날 거래가 20:00 에
끝난다**. 15:40 컷오프는 그 뒤의 모든 실행(정기·재기동 immediate·`force=True`)이
**부분 거래량 봉**을 확정봉으로 받아들이게 한다 — 09-11(금) 사고의 직접 원인이다
(16:14 재기동 immediate 가 1,005종목의 부분봉을 박고 18:10 정기가 908종목을
`skipped_fresh` 로 건너뜀; 40종목 대조 중앙값 **+0.51%**, 최대 **+13.97%**).

이 파일이 재기준선한 것은 **커트오프 값과 그 값을 전제한 시각들**뿐이고, 각 단언의
*의도*(시각 단독 판정 · fail-open · 실행당 1행 관측 · 보정 창 존치)는 그대로다.
가장 중요한 변경은 §G 시뮬의 **시장 모델**이다 — 종전 `_sim_kis_response` 는
"15:40 이후면 KIS 가 오늘 **확정봉**을 준다" 고 모델링했는데, 그것이 바로 이 사이클이
반증하는 명제다. 그 모델을 두면 회귀 스위트가 09-11 결함을 **구조적으로 재현할 수
없다**. 이제 15:30~20:00 은 OHLC 동일 + **거래량 부분값**(`_sim_partial`)을 준다.

⚠️ 의미 반전 ②: `[daily_load_today_bar_filter] mode=` 이 **세 번째 세대**다
   (원본 / cycle263 / cycle283). 15:40~20:00 구간 실행의 `mode` 가 keep → **drop**
   으로 뒤집힌다. 3세대 로그 합산 금지.
"""

from __future__ import annotations

import ast
import inspect
import logging
import re
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.db._kst import KST
from src.engine import data_load_tasks, scanner
from src.engine.task_loop_helper import IMMEDIATE_FRESH_SKIP_HOURS

pytestmark = pytest.mark.unit

_SCANNER_LOGGER = "src.engine.scanner"
_SCHED_LOGGER = "src.engine.scheduler"
_FILTER_MARKER = "[daily_load_today_bar_filter]"
_SKIP_MARKER = "[daily_load_today_filter_skipped]"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCANNER_SRC = _REPO_ROOT / "src" / "engine" / "scanner.py"


# ══════════════════════════════════════════════════════════════════════
# 공용 헬퍼
# ══════════════════════════════════════════════════════════════════════
def _records(caplog, prefix: str, *, logger_name: str, min_level: int = logging.INFO):
    """로거명 + 레벨 + prefix 3중 한정 (CI 루트 로거 DEBUG 내성 — 메모리 교훈)."""
    return [
        r for r in caplog.records
        if r.name == logger_name
        and r.levelno >= min_level
        and r.getMessage().startswith(prefix)
    ]


def _field(line: str, key: str) -> str | None:
    m = re.search(rf"\b{re.escape(key)}=([^\s]+)", line)
    return m.group(1) if m else None


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _bar(d: date, *, close: int, vol: int, flat: bool = False) -> dict:
    """KIS FHKST03010100 output2 형태 캔들 1행."""
    if flat:
        o = h = low = close
    else:
        o, h, low = close - 20, close + 50, close - 50
    return {
        "stck_bsop_date": _ymd(d),
        "stck_oprc": str(o),
        "stck_hgpr": str(h),
        "stck_lwpr": str(low),
        "stck_clpr": str(close),
        "acml_vol": str(vol),
        "acml_tr_pbmn": str(close * max(vol, 1)),
    }


def _stub_bar(d: date, prev_close: int) -> dict:
    """장 전 KIS 가 주는 껍데기 봉 — O=H=L=C=전일종가, 거래량 0."""
    return _bar(d, close=prev_close, vol=0, flat=True)


_UNIVERSE_ROW = {
    "ticker": "005930",
    "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"},
}


def _universe(*tickers: str, index: bool = False) -> list[dict]:
    """`stock_master.list_all` 대역 행.

    `index=True` 면 `is_kospi200` 을 켜 VCP universe 로 만든다 —
    `_stock_master_daily_load_once` 의 **220일 backfill 분기**
    (`fetch_daily_candles_backfill`) 진입 조건이다(사이클 172).
    """
    return [
        {
            "ticker": t,
            "raw": {"hts_avls": "1000", "acml_tr_pbmn": "5000000000"},
            "is_kospi200": index,
            "is_kosdaq150": False,
        }
        for t in (tickers or ("005930",))
    ]


class _CapturingUpsert:
    """upsert_batch 대역 — ticker 별로 넘어온 캔들 전량 수집."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict]]] = []

    async def __call__(self, ticker: str, candles: list[dict]) -> int:
        self.calls.append((ticker, list(candles)))
        return len(candles)

    @property
    def all_dates(self) -> list[str]:
        # fail-open 경로에서는 비정상 캔들(dict 아님)이 그대로 넘어올 수 있다 — 방어.
        return [
            str(c.get("stck_bsop_date"))
            for _, cs in self.calls
            for c in cs
            if isinstance(c, dict)
        ]


class FakeScheduler:
    """`_running` 토글 + `_wait_until` mock (cycle134/193 답습)."""

    def __init__(self, running: bool = False) -> None:
        self._running = running
        self.wait_calls = 0

    async def _wait_until(self, target_time, *, advance_if_passed: bool = False) -> None:
        self.wait_calls += 1
        return None


def _iso_hours_ago(hours: float) -> str:
    return (datetime.now(KST) - timedelta(hours=hours)).isoformat()


async def _run_daily_facade(
    *, scheduler: FakeScheduler, once_mock, get_mock, set_mock
) -> None:
    """`stock_master_daily_load_task_loop` 를 실 헬퍼로 구동 (게이트 배선 검증용)."""
    with patch(
        "src.engine.scanner._stock_master_daily_load_once", once_mock
    ), patch(
        "src.engine.stock_master_daily_metrics.record_stock_master_daily_load",
        MagicMock(),
    ), patch(
        "src.engine.stock_master_daily_metrics.flush_stock_master_daily_load_collector",
        MagicMock(),
    ), patch(
        "src.db.system_config.get_task_last_success", get_mock, create=True
    ), patch(
        "src.db.system_config.set_task_last_success", set_mock, create=True
    ), patch(
        "src.engine.task_loop_helper.asyncio.sleep", new_callable=AsyncMock
    ):
        await data_load_tasks.stock_master_daily_load_task_loop(
            scheduler, wait_time=dtime(16, 0)
        )


class _LoadHarness:
    """`_stock_master_daily_load_once` 통합 구동 대역 (KIS/DB 전량 격리)."""

    def __init__(self, *, tickers=("005930",), candles_fn=None, latest=None, count=100,
                 index_universe=False, backfill_fn=None, force=False):
        self.tickers = tuple(tickers)
        self.candles_fn = candles_fn
        self.latest = latest
        self.count = count
        # 사이클 263 검증(M29) — VCP 220일 backfill 분기(`fetch_daily_candles_backfill`)
        # 도 필터의 **합류점 아래**인지 재는 축. `backfill_fn` 을 주면 증분 분기
        # (`fetch_daily_candles`) 호출은 즉시 AssertionError = 분기 오인 검출.
        self.index_universe = index_universe
        self.backfill_fn = backfill_fn
        self.force = force
        self.upsert = _CapturingUpsert()
        self.fetch_calls: list[tuple[str, int]] = []
        self.backfill_calls: list[tuple[str, int]] = []

    async def _fetch(self, ticker, days):
        if self.backfill_fn is not None:
            raise AssertionError(
                f"backfill 분기를 기대했는데 증분 fetch_daily_candles 가 불렸다 "
                f"(ticker={ticker} days={days}) — 분기 조건 오인"
            )
        self.fetch_calls.append((ticker, days))
        return list(self.candles_fn(ticker))

    async def _fetch_backfill(self, ticker, total_days):
        self.backfill_calls.append((ticker, total_days))
        assert self.backfill_fn is not None, "backfill 분기 미기대 상황에서 호출됨"
        return list(self.backfill_fn(ticker))

    def patches(self):
        latest = self.latest
        return (
            patch("src.db.stock_master.list_all",
                  new=AsyncMock(return_value=_universe(*self.tickers,
                                                       index=self.index_universe))),
            patch("src.db.stock_master_daily.max_bas_dd",
                  new=AsyncMock(return_value=latest)),
            patch("src.db.stock_master_daily.count_by_ticker",
                  new=AsyncMock(return_value=self.count)),
            patch("src.api.condition.fetch_daily_candles",
                  new=AsyncMock(side_effect=self._fetch)),
            patch("src.api.condition.fetch_daily_candles_backfill",
                  new=AsyncMock(side_effect=self._fetch_backfill)),
            patch("src.db.stock_master_daily.upsert_batch", new=self.upsert),
            patch("asyncio.sleep", new=AsyncMock()),
        )

    async def run(self) -> dict:
        from contextlib import ExitStack

        with ExitStack() as stack:
            for p in self.patches():
                stack.enter_context(p)
            return await scanner._stock_master_daily_load_once(self.force)


# ══════════════════════════════════════════════════════════════════════
# A. (가) 신선도 게이트 배선 — C1 + 자문 §A-6 (1)(2)(3)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_A1_daily_facade_passes_freshness_gate_argument():
    """C1 — daily_load facade 가 `immediate_skip_if_fresh_hours=20.0` 을 넘긴다.

    basics/master/financial 3 task 는 이미 넘기고 프로덕션에서 skip 중이다
    (`system_config` 실측). daily_load 만 부재 = 이 결함의 (가) 축.
    """
    captured: dict = {}

    async def _capture(**kwargs):
        captured.update(kwargs)

    with patch("src.engine.task_loop_helper.run_periodic_task_loop", _capture):
        await data_load_tasks.stock_master_daily_load_task_loop(
            FakeScheduler(), wait_time=dtime(16, 0)
        )

    assert captured.get("task_label") == "stock_master_daily_load"
    assert "immediate_skip_if_fresh_hours" in captured, (
        "C1 위반 — daily_load task 가 신선도 게이트 인자를 전달하지 않는다 "
        f"(전달 인자={sorted(captured)})"
    )
    assert captured["immediate_skip_if_fresh_hours"] == IMMEDIATE_FRESH_SKIP_HOURS, (
        f"게이트 임계는 IMMEDIATE_FRESH_SKIP_HOURS(=20.0) 정본 재사용 의무 "
        f"(실측 {captured['immediate_skip_if_fresh_hours']!r})"
    )


def test_A2_stale_not_applied_comment_is_corrected():
    """C1 — `:110` 의 '신선도 게이트 미적용' 주석이 남아 있으면 안 된다."""
    src = inspect.getsource(data_load_tasks.stock_master_daily_load_task_loop)
    assert "미적용" not in src, (
        "C1 위반 — '신선도 게이트 미적용' 주석 잔존. 게이트를 넣었으면 주석도 정정한다 "
        "(주석이 코드와 반대면 다음 사람이 코드를 믿지 않는다)"
    )


@pytest.mark.asyncio
async def test_A3_marker_15h9_skips_immediate_run():
    """§A-6 (2) 경계 — 마커 15.9h(전일 16:00 성공) → 아침 immediate **skip**.

    이게 껍데기 봉 생성 주체를 없애는 축이다.
    """
    sched = FakeScheduler(running=False)
    once = AsyncMock(return_value={"total": 0})
    get_mock = AsyncMock(return_value=_iso_hours_ago(15.9))
    set_mock = AsyncMock(return_value=None)

    await _run_daily_facade(
        scheduler=sched, once_mock=once, get_mock=get_mock, set_mock=set_mock
    )

    assert get_mock.await_count == 1, "게이트 배선 시 마커 조회 1회 의무"
    assert once.await_count == 0, (
        "15.9h < 20h → immediate 실행 금지 (아침 껍데기 봉 생성 주체 소멸)"
    )


@pytest.mark.asyncio
async def test_A4_marker_39h9_runs_immediate_selfheal():
    """§A-6 (2) 경계 — 39.9h(전날 16:00 실패) → immediate 실행 = 자기 치유."""
    sched = FakeScheduler(running=False)
    once = AsyncMock(return_value={"total": 0})
    get_mock = AsyncMock(return_value=_iso_hours_ago(39.9))
    set_mock = AsyncMock(return_value=None)

    await _run_daily_facade(
        scheduler=sched, once_mock=once, get_mock=get_mock, set_mock=set_mock
    )

    assert once.await_count == 1, (
        "39.9h > 20h → immediate 실행 의무 (16:00 실패 다음날 D 봉 복구 = 사이클106 안전망)"
    )
    assert set_mock.await_count == 1, "immediate 성공 → 마커 기록 의무"


@pytest.mark.asyncio
async def test_A5_marker_63h9_weekend_runs_immediate():
    """§A-6 (2) 경계 — 63.9h(금 16:00 → 월 07:56) → immediate 실행 (주 1회 무결성 재fetch)."""
    sched = FakeScheduler(running=False)
    once = AsyncMock(return_value={"total": 0})
    get_mock = AsyncMock(return_value=_iso_hours_ago(63.9))
    set_mock = AsyncMock(return_value=None)

    await _run_daily_facade(
        scheduler=sched, once_mock=once, get_mock=get_mock, set_mock=set_mock
    )

    assert get_mock.await_count == 1, "게이트 배선 시 마커 조회 1회 의무"
    assert once.await_count == 1, "주말 경과(63.9h > 20h) → 월요일 immediate 실행 의무"


@pytest.mark.asyncio
async def test_A6_marker_query_exception_runs_immediate_fail_open():
    """§A-6 (3) — 마커 조회 예외 → immediate 실행(fail-open). (다)가 오늘봉을 버려 무해."""
    sched = FakeScheduler(running=False)
    once = AsyncMock(return_value={"total": 0})
    get_mock = AsyncMock(side_effect=RuntimeError("pg down"))
    set_mock = AsyncMock(return_value=None)

    await _run_daily_facade(
        scheduler=sched, once_mock=once, get_mock=get_mock, set_mock=set_mock
    )

    assert get_mock.await_count == 1, "게이트 배선 시 마커 조회 시도 의무"
    assert once.await_count == 1, "조회 예외 → fail-open 실행 의무 (fail-closed 금지)"


@pytest.mark.asyncio
async def test_A7_evening_success_records_marker_for_daily_label():
    """§A-6 (1) 앞단 — 16:00 정기 성공 → `set_task_last_success("stock_master_daily_load")`.

    fresh 마커라 immediate 는 skip 되고, 정기 while 루프만 발화해야 한다
    (사이클 188 정기 발화 복원을 게이트가 다시 막으면 안 된다).
    """
    sched = FakeScheduler(running=True)

    async def _once():
        sched._running = False
        return {"total": 7}

    once = AsyncMock(side_effect=_once)
    get_mock = AsyncMock(return_value=_iso_hours_ago(15.9))
    set_mock = AsyncMock(return_value=None)

    await _run_daily_facade(
        scheduler=sched, once_mock=once, get_mock=get_mock, set_mock=set_mock
    )

    assert once.await_count == 1, "fresh 마커여도 정기 while 루프는 발화 의무"
    assert set_mock.await_count == 1, "16:00 성공 → 마커 기록 의무 (다음 아침 skip 근거)"
    args = set_mock.await_args.args
    assert args[0] == "stock_master_daily_load", "task_label 정본 전달 의무"
    assert isinstance(args[1], str) and "+09:00" in args[1], (
        f"KST iso(+09:00) 기록 의무 (실측 {args[1]!r})"
    )


@pytest.mark.asyncio
async def test_A8_evening_raise_does_not_record_marker():
    """§A-6 (1) — once() 가 raise 하면 마커를 **쓰지 않는다** (안전망 부활 조건).

    마커가 안 써져야 다음 아침 immediate 가 자동 부활해 D 봉을 복구한다.
    """
    sched = FakeScheduler(running=True)

    async def _boom():
        # 정기 while 루프에 진입한 뒤(= `_wait_until` 1회 이상)의 호출만 루프를 끝낸다.
        # immediate 호출이 루프를 끝내면 게이트 미배선(Red)과 배선(Green)이 구분되지 않는다.
        if sched.wait_calls > 0:
            sched._running = False
        raise RuntimeError("KIS 장애")

    once = AsyncMock(side_effect=_boom)
    get_mock = AsyncMock(return_value=_iso_hours_ago(15.9))
    set_mock = AsyncMock(return_value=None)

    await _run_daily_facade(
        scheduler=sched, once_mock=once, get_mock=get_mock, set_mock=set_mock
    )

    assert once.await_count == 1, (
        "fresh 마커 → immediate skip, 정기 1회만 발화 (게이트 미배선이면 2회)"
    )
    assert set_mock.await_count == 0, (
        "once() 예외 → 마커 기록 금지 (기록하면 다음 아침 immediate 안전망이 죽는다)"
    )


# ══════════════════════════════════════════════════════════════════════
# B. (다) 오늘봉 시각 필터 — 순수 판정 규칙 (C2/C3)
# ══════════════════════════════════════════════════════════════════════
_TODAY = date(2026, 9, 8)
_D1 = date(2026, 9, 7)
_D2 = date(2026, 9, 4)


def _kst_at(d: date, hh: int, mm: int) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=KST)


def test_B1_before_cutoff_drops_only_today_bar():
    """C2 — 07:56 진입 → 오늘 캔들만 제외, 나머지는 순서·객체 동일."""
    today_bar = _stub_bar(_TODAY, 10000)
    rest = [_bar(_D1, close=10000, vol=5000), _bar(_D2, close=9900, vol=4200)]
    candles = [today_bar, *rest]

    kept = scanner._drop_today_bars(
        candles, now_kst=_kst_at(_TODAY, 7, 56), today=_TODAY
    )

    assert [c["stck_bsop_date"] for c in kept] == [_ymd(_D1), _ymd(_D2)]
    assert kept[0] is rest[0] and kept[1] is rest[1], "잔여 캔들은 원본 객체 그대로 보존"
    assert len(candles) == 3 and candles[0] is today_bar, "입력 리스트 비파괴 의무"


def test_B2_after_cutoff_keeps_flat_zero_volume_today_bar():
    """C3 반증 2 — 20:05 진입 + 거래량 0·OHLC 평탄 오늘봉 = **거래정지 종목의 진짜 확정봉**.

    데이터 기준(거래량 0 ∧ 평탄)으로 구현하면 이 행을 영영 못 갖는다 → 붉어져야 한다.
    """
    flat_today = _bar(_TODAY, close=10000, vol=0, flat=True)
    candles = [flat_today, _bar(_D1, close=10000, vol=5000)]

    kept = scanner._drop_today_bars(
        candles, now_kst=_kst_at(_TODAY, 20, 5), today=_TODAY
    )

    assert [c["stck_bsop_date"] for c in kept] == [_ymd(_TODAY), _ymd(_D1)], (
        "20:00 이후 = 확정봉 시각(cycle283) — 진짜 무거래봉(하루 1~8건) 100% 보존 의무"
    )


def test_B3_before_cutoff_drops_intraday_partial_bar():
    """C3 반증 1 — 13:04 진입 + 거래량>0·비평탄 오늘봉 = **장중 부분봉**.

    데이터 기준이면 '정상 봉'으로 통과시켜 확정봉인 척 박힌다(껍데기보다 나쁘다 —
    평탄하지 않아 눈에 안 띈다). 시각 기준이면 폐기된다.
    """
    partial = _bar(_TODAY, close=10250, vol=331_402)
    candles = [partial, _bar(_D1, close=10000, vol=5000)]

    kept = scanner._drop_today_bars(
        candles, now_kst=_kst_at(_TODAY, 13, 4), today=_TODAY
    )

    assert [c["stck_bsop_date"] for c in kept] == [_ymd(_D1)], (
        "장중 부분봉은 거래량>0·비평탄이어도 폐기 의무 (판정 기준 = 시각 단독, C3)"
    )


@pytest.mark.parametrize(
    "hh,mm,expect_dropped",
    [(19, 59, True), (20, 0, False), (20, 1, False), (0, 0, True), (15, 40, True)],
)
def test_B4_cutoff_boundary_is_20_00(hh, mm, expect_dropped):
    """C2/C5 — 커트오프 경계는 **20:00** KST (19:59 폐기 / 20:00 보존, cycle283).

    `(15, 40, True)` 가 재기준선의 심장이다 — 구 컷오프 시각이 이제 **폐기 쪽**이라는
    사실을 못 박는다. 이 항이 없으면 누가 값을 15:40 으로 되돌려도 나머지 세 항만으로는
    아무것도 붉어지지 않는다.
    """
    candles = [_bar(_TODAY, close=10100, vol=12), _bar(_D1, close=10000, vol=5000)]

    kept = scanner._drop_today_bars(
        candles, now_kst=_kst_at(_TODAY, hh, mm), today=_TODAY
    )

    dropped = _ymd(_TODAY) not in [c["stck_bsop_date"] for c in kept]
    assert dropped is expect_dropped, (
        f"{hh:02d}:{mm:02d} 진입 시 오늘봉 폐기 여부 계약 위반 (기대 {expect_dropped})"
    )


def test_B5_after_cutoff_still_drops_future_dated_bar():
    """C2 — 20:00 이후에도 `bas_dd > today` 는 폐기 (시계 왜곡 방어)."""
    future = _bar(_TODAY + timedelta(days=1), close=10500, vol=100)
    candles = [future, _bar(_TODAY, close=10100, vol=9000)]

    kept = scanner._drop_today_bars(
        candles, now_kst=_kst_at(_TODAY, 20, 5), today=_TODAY
    )

    assert [c["stck_bsop_date"] for c in kept] == [_ymd(_TODAY)], (
        "미래 날짜 캔들은 커트오프 이후에도 폐기 의무 (시계 왜곡 방어)"
    )


def test_B6_unparseable_bas_dd_is_kept_fail_open():
    """C4 — `bas_dd` 가 빈 문자열/이형이면 **보존**(fail-open 방향).

    폐기하면 판정 실패가 곧 데이터 유실이 된다 — P0-1 유령 키와 같은 방향이라 금지.
    (실제 저장 단계에서 `upsert_batch` 의 `_candle_to_row` 가 graceful skip 한다.)
    """
    weird = [
        {"stck_bsop_date": ""},
        {"stck_bsop_date": "20260"},
        {},
    ]
    candles = [_bar(_TODAY, close=10100, vol=0, flat=True), *weird]

    kept = scanner._drop_today_bars(
        candles, now_kst=_kst_at(_TODAY, 7, 56), today=_TODAY
    )

    assert kept == weird, (
        "오늘봉만 폐기하고 파싱 불가 캔들은 전부 보존 의무 (fail-open, C4)"
    )


def test_B7_empty_input_returns_empty():
    """빈 입력 → 빈 출력 (예외 전파 금지)."""
    assert scanner._drop_today_bars([], now_kst=_kst_at(_TODAY, 7, 56), today=_TODAY) == []


# ══════════════════════════════════════════════════════════════════════
# C. 배선 — 필터가 `fetched += 1` 뒤 · `upsert_batch` 앞에 있는가 (C2/C7)
# ══════════════════════════════════════════════════════════════════════
@freeze_time("2026-09-08T07:56:00+09:00")
@pytest.mark.asyncio
async def test_C1_morning_run_never_upserts_today_bar(caplog):
    """C2 — 아침 실행: upsert_batch 로 오늘 날짜 행이 **단 한 건도** 넘어가지 않는다."""
    def _candles(_t):
        return [_stub_bar(_TODAY, 10000), _bar(_D1, close=10000, vol=5000)]

    h = _LoadHarness(candles_fn=_candles, latest=_D1)
    with caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        summary = await h.run()

    assert _ymd(_TODAY) not in h.upsert.all_dates, (
        f"아침 실행이 오늘봉을 기록했다 — 그날 16:00 이 통째로 skip 된다 "
        f"(실측 {h.upsert.all_dates})"
    )
    assert _ymd(_D1) in h.upsert.all_dates, "전일 실봉은 그대로 기록 의무"
    assert summary["fetched"] == 1, "C7/§9-6 — `fetched` 는 'KIS 응답을 받았다' 의미 불변"
    assert summary["failed"] == 0, "필터로 비어도 KIS 실패가 아니다 (`failed` 의미 불변)"


@freeze_time("2026-09-08T07:56:00+09:00")
@pytest.mark.asyncio
async def test_C2_counters_unchanged_when_all_candles_dropped():
    """§9-6 — 필터가 전량 제거해도 `fetched`/`failed` 카운터는 안 움직인다."""
    def _candles(_t):
        return [_stub_bar(_TODAY, 10000)]

    h = _LoadHarness(candles_fn=_candles, latest=_D1)
    summary = await h.run()

    assert summary["fetched"] == 1
    assert summary["failed"] == 0
    assert h.upsert.all_dates == [], "오늘봉 단독 응답 → 기록 0행"


@freeze_time("2026-09-08T20:05:00+09:00")
@pytest.mark.asyncio
async def test_C3_evening_run_writes_today_real_bar():
    """C2 — 20:05 실행은 오늘 확정봉을 그대로 기록한다 (20:30 정기가 비로소 일을 한다)."""
    def _candles(_t):
        return [_bar(_TODAY, close=10250, vol=812_004), _bar(_D1, close=10000, vol=5000)]

    h = _LoadHarness(candles_fn=_candles, latest=_D1)
    await h.run()

    assert _ymd(_TODAY) in h.upsert.all_dates, "20:00 이후 = 확정봉 기록 의무(cycle283)"


@freeze_time("2026-09-07T22:56:00")
@pytest.mark.asyncio
async def test_C4_cutoff_judged_in_kst_not_naive_local(caplog):
    """C6 — 시각 판정은 **tz-aware KST**.

    frozen 시각 = 2026-09-07 22:56 **UTC** = 2026-09-08 07:56 KST.
    naive `datetime.now()` 를 쓰면 22:56 ≥ 15:40 이 되어 오늘봉을 통과시키고
    `today` 도 09-07 로 어긋난다 → 붉어진다.
    """
    def _candles(_t):
        return [_stub_bar(_TODAY, 10000), _bar(_D1, close=10000, vol=5000)]

    h = _LoadHarness(candles_fn=_candles, latest=_D1)
    with caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        await h.run()

    assert _ymd(_TODAY) not in h.upsert.all_dates, (
        "naive 로컬 시각 판정 금지 — KST 07:56 은 커트오프 이전이다 (C6)"
    )
    rows = _records(caplog, _FILTER_MARKER, logger_name=_SCANNER_LOGGER)
    assert rows, "관측 마커 부재"
    line = rows[0].getMessage()
    assert _field(line, "today") == _TODAY.isoformat(), (
        f"`today` 는 KST 기준 날짜 의무 (실측 {_field(line, 'today')!r})"
    )
    assert _field(line, "now") == "07:56", (
        f"`now` 는 KST HH:MM 의무 (실측 {_field(line, 'now')!r})"
    )


@pytest.mark.asyncio
async def test_C5_cutoff_decided_once_at_function_entry():
    """자문 §9-4 — 커트오프 판정은 **함수 진입 시 1회**.

    15:39 진입 → 첫 종목 처리 중 시계가 15:41 로 진행 → 두 종목 모두 같은 규칙(폐기).
    종목마다 재판정하면 두 번째 종목의 오늘봉이 남아 붉어진다.
    """
    def _candles(_t):
        return [_bar(_TODAY, close=10100, vol=17), _bar(_D1, close=10000, vol=5000)]

    with freeze_time("2026-09-08T15:39:00+09:00") as frozen:
        h = _LoadHarness(tickers=("005930", "000660"), candles_fn=_candles, latest=_D1)
        orig_fetch = h._fetch

        async def _ticking_fetch(ticker, days):
            out = await orig_fetch(ticker, days)
            frozen.tick(timedelta(minutes=2))  # 15:39 → 15:41 → 15:43
            return out

        h._fetch = _ticking_fetch
        await h.run()

    assert h.upsert.all_dates.count(_ymd(_TODAY)) == 0, (
        "루프 중 시계가 커트오프를 넘어도 진입 시 규칙 유지 의무 "
        f"(실측 {h.upsert.all_dates})"
    )


@pytest.mark.asyncio
async def test_C6_cutoff_read_before_universe_paging(caplog):
    """C2 계약 문구 = "**함수 진입 시각**" — `list_all` 페이징 지연이 판정을 뒤집으면 안 된다.

    `stock_master.list_all` 은 최대 여러 페이지 + 예외 graceful 이라 수 초~수 분이 걸릴 수
    있다. `load_now_kst` 를 그 **뒤** 에서 읽으면 15:39 에 시작한 실행이 15:41 기준으로
    판정해 `mode=keep` 으로 뒤집히고 **장중 잠정봉이 확정봉으로 기록**된다.
    (test_C5 는 fetch 단계만 tick 시키므로 이 구간은 잠기지 않는다.)
    """
    def _candles(_t):
        return [_bar(_TODAY, close=10100, vol=17), _bar(_D1, close=10000, vol=5000)]

    from contextlib import ExitStack

    up = _CapturingUpsert()
    with freeze_time("2026-09-08T15:39:00+09:00") as frozen:
        async def _slow_list_all(limit=1000, offset=0):
            frozen.tick(timedelta(minutes=2))  # 15:39 → 15:41 (커트오프 통과)
            return _universe("005930") if offset == 0 else []

        async def _fetch(_t, _days):
            return _candles(_t)

        with ExitStack() as stack:
            stack.enter_context(patch("src.db.stock_master.list_all",
                                      new=AsyncMock(side_effect=_slow_list_all)))
            stack.enter_context(patch("src.db.stock_master_daily.max_bas_dd",
                                      new=AsyncMock(return_value=_D1)))
            stack.enter_context(patch("src.db.stock_master_daily.count_by_ticker",
                                      new=AsyncMock(return_value=100)))
            stack.enter_context(patch("src.api.condition.fetch_daily_candles",
                                      new=AsyncMock(side_effect=_fetch)))
            stack.enter_context(patch("src.db.stock_master_daily.upsert_batch", new=up))
            stack.enter_context(patch("asyncio.sleep", new=AsyncMock()))
            with caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
                await scanner._stock_master_daily_load_once()

    assert up.all_dates.count(_ymd(_TODAY)) == 0, (
        "유니버스 페이징이 지연돼 시계가 커트오프를 넘어도 진입 시 규칙 유지 의무 "
        f"(실측 {up.all_dates})"
    )
    rows = _records(caplog, _FILTER_MARKER, logger_name=_SCANNER_LOGGER)
    assert _field(rows[0].getMessage(), "now") == "15:39", (
        "판정 시각은 함수 진입 시각(15:39)이어야 한다 — list_all 뒤에서 읽으면 15:41 이다 "
        f"(실측 {_field(rows[0].getMessage(), 'now')!r})"
    )


# ══════════════════════════════════════════════════════════════════════
# D. 관측 — C7 (실행당 1행, 종목당 로그 금지)
# ══════════════════════════════════════════════════════════════════════
@freeze_time("2026-09-08T07:56:00+09:00")
@pytest.mark.asyncio
async def test_D1_filter_marker_emitted_once_per_run_with_fields(caplog):
    """C7 — 50 종목 입력에도 `[daily_load_today_bar_filter]` 는 **정확히 1행**."""
    def _candles(_t):
        return [_stub_bar(_TODAY, 10000), _bar(_D1, close=10000, vol=5000)]

    tickers = tuple(f"{100000 + i:06d}" for i in range(50))
    h = _LoadHarness(tickers=tickers, candles_fn=_candles, latest=_D1)
    with caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        await h.run()

    rows = _records(caplog, _FILTER_MARKER, logger_name=_SCANNER_LOGGER)
    assert len(rows) == 1, (
        f"실행당 1행 의무 — 종목당 emit 은 하루 1,000행 폭주 (cycle237 교훈). 실측 {len(rows)}행"
    )
    line = rows[0].getMessage()
    assert _field(line, "mode") == "drop"
    assert _field(line, "cutoff") == "20:00"
    assert _field(line, "now") == "07:56"
    assert _field(line, "today") == _TODAY.isoformat()
    assert _field(line, "dropped_rows") == "50", (
        f"걸러진 행 수 = 50 (종목당 1행) (실측 {_field(line, 'dropped_rows')!r})"
    )
    assert _field(line, "tickers_affected") == "50", (
        f"걸러진 종목 수 = 50 (실측 {_field(line, 'tickers_affected')!r})"
    )
    assert _field(line, "filter_errors") == "0", "정상 경로는 판정 실패 0"


@freeze_time("2026-09-08T20:30:00+09:00")
@pytest.mark.asyncio
async def test_D2_filter_marker_emitted_in_keep_mode_too(caplog):
    """C7 — 20:30 정기 실행도 1행(`mode=keep dropped_rows=0`) — 관측 연속성."""
    def _candles(_t):
        return [_bar(_TODAY, close=10250, vol=812_004), _bar(_D1, close=10000, vol=5000)]

    h = _LoadHarness(candles_fn=_candles, latest=_D1)
    with caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        await h.run()

    rows = _records(caplog, _FILTER_MARKER, logger_name=_SCANNER_LOGGER)
    assert len(rows) == 1, f"실행당 1행 의무 (실측 {len(rows)}행)"
    line = rows[0].getMessage()
    assert _field(line, "mode") == "keep"
    assert _field(line, "dropped_rows") == "0"
    assert _field(line, "tickers_affected") == "0"
    assert _field(line, "filter_errors") == "0", "정상 경로는 판정 실패 0"


@freeze_time("2026-09-08T07:56:00+09:00")
@pytest.mark.asyncio
async def test_D3_dropped_rows_and_tickers_are_distinct_counters(caplog):
    """C7 — 두 필드는 **서로 다른 것**을 센다 (행 수 ≠ 종목 수).

    D1 은 50종목 × 각 1행이라 두 값이 항상 같아 서로를 구분하지 못한다(뮤테이션
    `filter_dropped_rows += 1` · `filter_dropped_tickers += len(...)` 이 둘 다 살아남았다).
    여기서는 한 종목이 **2행**(내일 날짜 봉 + 오늘 껍데기)을 잃고 다른 종목은 0행을 잃는다.
    """
    tomorrow = _TODAY + timedelta(days=1)

    def _candles(ticker):
        if ticker == "005930":
            return [
                _bar(tomorrow, close=10300, vol=0),   # 시계 왜곡 미래 봉
                _stub_bar(_TODAY, 10000),             # 오늘 껍데기
                _bar(_D1, close=10000, vol=5000),     # 전일 확정봉
            ]
        return [_bar(_D1, close=9900, vol=4000), _bar(_D2, close=9800, vol=3000)]

    h = _LoadHarness(tickers=("005930", "000660"), candles_fn=_candles, latest=_D1)
    with caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
        await h.run()

    rows = _records(caplog, _FILTER_MARKER, logger_name=_SCANNER_LOGGER)
    assert len(rows) == 1, f"실행당 1행 의무 (실측 {len(rows)}행)"
    line = rows[0].getMessage()
    assert _field(line, "dropped_rows") == "2", (
        f"폐기된 **행** 수 = 2 (실측 {_field(line, 'dropped_rows')!r})"
    )
    assert _field(line, "tickers_affected") == "1", (
        f"폐기가 발생한 **종목** 수 = 1 (실측 {_field(line, 'tickers_affected')!r})"
    )
    assert h.upsert.all_dates.count(_ymd(tomorrow)) == 0, "미래 날짜 봉도 폐기 의무"
    assert h.upsert.all_dates.count(_ymd(_TODAY)) == 0


# ══════════════════════════════════════════════════════════════════════
# E. fail-open — C4
# ══════════════════════════════════════════════════════════════════════
@freeze_time("2026-09-08T07:56:00+09:00")
@pytest.mark.asyncio
async def test_E1_filter_exception_keeps_all_candles_and_warns_once(caplog):
    """C4 — 필터 예외 → **전량 upsert 유지**(현행 행위) + WARNING 실행당 최대 1행.

    fail-closed 는 P0-1(유령 키가 두 전략을 전 기간 체결 0건으로 만든 방향)이라 금지.
    """
    def _candles(_t):
        return [_stub_bar(_TODAY, 10000), _bar(_D1, close=10000, vol=5000)]

    tickers = tuple(f"{200000 + i:06d}" for i in range(30))
    h = _LoadHarness(tickers=tickers, candles_fn=_candles, latest=_D1)

    with patch(
        "src.engine.scanner._drop_today_bars",
        side_effect=RuntimeError("판정 실패"),
    ):
        with caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
            summary = await h.run()

    assert h.upsert.all_dates.count(_ymd(_TODAY)) == 30, (
        "판정 예외 → 원본 전량 upsert 의무 (fail-open, C4)"
    )
    assert summary["failed"] == 0, "판정 예외는 KIS 실패가 아니다"
    warns = _records(
        caplog, _SKIP_MARKER, logger_name=_SCANNER_LOGGER, min_level=logging.WARNING
    )
    assert len(warns) == 1, (
        f"fail-open 흔적은 실행당 1행 WARNING (종목당 30행 폭주 금지). 실측 {len(warns)}행"
    )
    # 요약 마커가 fail-open **규모**를 노출해야 한다 — 없으면 `dropped_rows=0` 이
    # "버릴 오늘봉이 없었다" 와 "필터가 전량 죽어 시정 전 행위로 되돌아갔다" 를 구분 못 한다.
    rows = _records(caplog, _FILTER_MARKER, logger_name=_SCANNER_LOGGER)
    assert len(rows) == 1, f"요약 마커는 실행당 1행 (실측 {len(rows)}행)"
    line = rows[0].getMessage()
    assert _field(line, "filter_errors") == "30", (
        "판정 실패 종목 수가 요약 마커에 드러나야 한다 "
        f"(실측 {_field(line, 'filter_errors')!r}) — WARNING 1행만으로는 "
        "'몇 종목이 새어 들어갔는지' 를 D+1 에 알 수 없다"
    )
    assert _field(line, "dropped_rows") == "0", (
        "fail-open 이면 폐기 0 이다 (원본 전량 upsert)"
    )


@freeze_time("2026-09-08T07:56:00+09:00")
@pytest.mark.asyncio
async def test_E2_malformed_candle_does_not_break_ticker_loop():
    """C4 — 판정 실패는 **캔들 단위**이지 종목 단위가 아니다.

    비정상 원소(dict 아님)가 섞인 **바로 그 종목**의 응답에 오늘 껍데기 봉이 함께 있어도
    껍데기는 폐기돼야 한다. `isinstance(candle, dict)` 방어가 없으면 첫 원소에서
    `AttributeError` → 호출부 fail-open → **그 종목의 캔들 전량**(오늘 껍데기 포함)이
    그대로 upsert 되어 이 사이클이 고치려는 결함이 그 종목에 재현된다(M30).
    """
    def _candles(ticker):
        if ticker == "005930":
            # 비정상 원소 + 오늘 껍데기 + 전일 실봉 — 한 응답에 셋을 섞는다
            return ["not-a-dict", _stub_bar(_TODAY, 10000),
                    _bar(_D1, close=10000, vol=5000)]
        return [_stub_bar(_TODAY, 10000), _bar(_D1, close=9900, vol=4000)]

    h = _LoadHarness(tickers=("005930", "000660"), candles_fn=_candles, latest=_D1)
    summary = await h.run()

    assert summary["fetched"] == 2, "첫 종목 이상 응답이 다음 종목 진행을 막으면 안 된다"
    assert h.upsert.all_dates.count(_ymd(_TODAY)) == 0, (
        "비정상 원소가 섞인 종목의 오늘봉도 폐기 의무 — 판정 실패는 캔들 단위다 "
        f"(실측 {h.upsert.all_dates})"
    )
    # 비정상 원소 자체는 **보존**된다(fail-open — 판정 불가가 곧 데이터 유실이면 안 된다)
    first_call = [cs for t, cs in h.upsert.calls if t == "005930"]
    assert first_call and "not-a-dict" in first_call[0], (
        f"판정 불가 원소는 보존 의무 (실측 {first_call})"
    )
    assert len(h.upsert.calls) == 2, "두 종목 모두 upsert 도달 의무"


@freeze_time("2026-09-08T07:56:00+09:00")
@pytest.mark.asyncio
async def test_E3_vcp_backfill_branch_is_filtered_too():
    """C2 — 필터 자리가 **두 fetch 분기의 합류점**이다 (VCP 220일 backfill 도 덮는다).

    명세가 `fetched += 1` 뒤 · `upsert` 앞을 고른 유일한 근거가 "두 분기
    (`fetch_daily_candles` / `fetch_daily_candles_backfill`)의 합류점" 인데, 그 합류
    성질을 재는 케이스가 없으면 backfill 분기만 우회시키는 변경이 통과한다(M29).
    프로덕션에서 이 분기는 실재한다 — VCP universe(KOSPI200∪KOSDAQ150) ∩
    `count_by_ticker < 120` 이고, 그게 곧 donchian·VCP 가 읽는 종목들이다.
    """
    def _backfill(_t):
        return [_stub_bar(_TODAY, 10000),
                _bar(_D1, close=10000, vol=5000),
                _bar(_D2, close=9900, vol=4800)]

    h = _LoadHarness(
        tickers=("005930",),
        latest=_D1,
        count=10,                # < 120 → VCP backfill 분기
        index_universe=True,     # is_kospi200=True → VCP universe
        backfill_fn=_backfill,   # 증분 fetch 가 불리면 AssertionError (분기 오인 검출)
    )
    summary = await h.run()

    assert h.backfill_calls, "VCP backfill 분기 진입 의무 (분기 조건 오인)"
    assert h.fetch_calls == [], "증분 분기는 호출되면 안 된다"
    assert summary["mode"] == "full", f"backfill 우세 → mode=full (실측 {summary['mode']})"
    assert h.upsert.all_dates.count(_ymd(_TODAY)) == 0, (
        f"backfill 분기의 오늘 껍데기도 폐기 의무 (실측 {h.upsert.all_dates})"
    )
    assert h.upsert.all_dates.count(_ymd(_D1)) == 1, "전일 확정봉은 보존 의무"


# ══════════════════════════════════════════════════════════════════════
# I. 수동 보정(`force=True`) 경로 — `POST /api/stock-master/refresh-daily`
#    (`src/routes/stock_master.py::refresh_daily_now`, force 기본 True)
#
#    `force` 는 `latest >= today` **멱등 skip 만** 우회하고 필터는 무조건 통과한다.
#    운영자가 가장 자주 쓰는 유일한 수동 경로인데 회귀 가드가 0건이면, 다음 사이클이
#    필터를 `force` 앞으로 옮기거나 커트오프 판정을 바꿔도 주말 보정이 조용히 망가진다.
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_I1_weekend_manual_backfill_is_untouched_by_filter(caplog):
    """토요일 15:16 `force=True` 수동 보정(09-06 에 실제로 쓴 절차)은 필터 **무접촉**.

    `today` 가 토요일이라 KIS 는 오늘 날짜 봉을 주지 않는다 ⇒ 폐기 0.
    금요일·목요일 확정봉이 전량 기록된다.
    """
    friday, thursday = date(2026, 9, 4), date(2026, 9, 3)

    def _candles(_t):
        return [_bar(friday, close=10400, vol=910_000),
                _bar(thursday, close=10300, vol=880_000)]

    # 2026-09-05 는 토요일 (09-06 일요일 보정과 같은 장외 창)
    with freeze_time("2026-09-05T15:16:00+09:00"):
        h = _LoadHarness(candles_fn=_candles, latest=friday, force=True)
        with caplog.at_level(logging.INFO, logger=_SCANNER_LOGGER):
            summary = await h.run()

    assert summary["skipped_fresh"] == 0, "force=True 는 max_bas_dd 멱등을 우회한다"
    assert summary["fetched"] == 1
    assert sorted(h.upsert.all_dates) == sorted([_ymd(friday), _ymd(thursday)]), (
        f"주말 수동 보정은 확정봉 전량 기록 의무 (실측 {h.upsert.all_dates})"
    )
    line = _records(caplog, _FILTER_MARKER, logger_name=_SCANNER_LOGGER)[0].getMessage()
    assert _field(line, "dropped_rows") == "0", "주말은 오늘 날짜 봉 자체가 없다 = 폐기 0"


@freeze_time("2026-09-08T20:35:00+09:00")
@pytest.mark.asyncio
async def test_I2_after_cutoff_manual_force_records_today_confirmed_bar():
    """평일 20:35 `force=True`(20:30 실패 후 수동 복구) → 오늘 **확정봉** 기록.

    cycle283 재기준선 — 종전 17:00 은 이제 컷오프 **이전**이라 같은 의도를 재려면
    시각을 20:00 뒤로 옮겨야 한다. 의도("컷오프 이후 수동 복구는 확정봉을 기록")는 불변.
    """
    def _candles(_t):
        return [_bar(_TODAY, close=10250, vol=812_004), _bar(_D1, close=10000, vol=5000)]

    h = _LoadHarness(candles_fn=_candles, latest=_TODAY, force=True)
    summary = await h.run()

    assert summary["skipped_fresh"] == 0, "force 는 latest==today 여도 fetch 한다"
    assert h.upsert.all_dates.count(_ymd(_TODAY)) == 1, (
        f"20:00 이후 수동 복구는 오늘 확정봉을 기록해야 한다 (실측 {h.upsert.all_dates})"
    )


@freeze_time("2026-09-08T10:00:00+09:00")
@pytest.mark.asyncio
async def test_I3_before_cutoff_manual_force_still_drops_today_bar():
    """평일 10:00 `force=True` → 오늘 **잠정봉** 폐기(설계 의도) + 전일봉은 기록.

    `force` 는 멱등 skip 만 우회한다 — 필터를 우회시키면 수동 실행 한 번이
    그날 16:00 을 다시 skip 시키는 원래 결함을 되살린다.
    """
    def _candles(_t):
        return [_bar(_TODAY, close=10100, vol=17), _bar(_D1, close=10000, vol=5000)]

    h = _LoadHarness(candles_fn=_candles, latest=_TODAY, force=True)
    await h.run()

    assert h.upsert.all_dates.count(_ymd(_TODAY)) == 0, (
        f"장중 수동 실행도 잠정봉을 기록하면 안 된다 (실측 {h.upsert.all_dates})"
    )
    assert h.upsert.all_dates.count(_ymd(_D1)) == 1


@freeze_time("2026-09-08T10:00:00+09:00")
@pytest.mark.asyncio
async def test_I4_without_force_fresh_skip_is_unchanged():
    """`force=False` + `latest == today` → 종전대로 skip (멱등 규칙 무변경 회귀)."""
    def _candles(_t):  # pragma: no cover — 호출되면 안 된다
        raise AssertionError("fresh skip 이면 KIS 를 부르지 않는다")

    h = _LoadHarness(candles_fn=_candles, latest=_TODAY)
    summary = await h.run()

    assert summary["skipped_fresh"] == 1
    assert summary["fetched"] == 0
    assert h.upsert.calls == []


# ══════════════════════════════════════════════════════════════════════
# F. 상수/구조 가드 — C5/C6
# ══════════════════════════════════════════════════════════════════════
def test_F1_cutoff_constant_is_scanner_local_literal_20_00():
    """C5 — `_DAILY_LOAD_TODAY_BAR_CUTOFF = time(20, 0)` 이 scanner.py 모듈 레벨 리터럴.

    cycle283 재기준선: 값만 20:00 으로 옮긴다. **"scanner 지역 리터럴 의무" 는 유지**
    — scheduler 의 매매/보드 시각 상수를 import 해 쓰면 매수 보드 시각 변경이 적재
    규약을 딸려 바꾼다(C5 원칙 불변, `test_F2` 가 그 축을 따로 지킨다).
    """
    assert hasattr(scanner, "_DAILY_LOAD_TODAY_BAR_CUTOFF"), (
        "C5 위반 — scanner 전용 커트오프 상수 부재"
    )
    assert scanner._DAILY_LOAD_TODAY_BAR_CUTOFF == dtime(20, 0)

    tree = ast.parse(_SCANNER_SRC.read_text(encoding="utf-8"))
    found = []
    for node in tree.body:  # 모듈 레벨만
        targets = (
            node.targets if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        for t in targets:
            if isinstance(t, ast.Name) and t.id == "_DAILY_LOAD_TODAY_BAR_CUTOFF":
                found.append(node)
    assert len(found) == 1, (
        f"모듈 레벨 정의 1건 의무 (실측 {len(found)}건) — 함수 안 지역 상수 금지"
    )
    value = found[0].value
    assert isinstance(value, ast.Call), "리터럴 `time(20, 0)` 호출 의무"
    args = [a.value for a in value.args if isinstance(a, ast.Constant)]
    assert args[:2] == [20, 0], f"커트오프 20:00 리터럴 의무 (실측 {args[:2]})"


def test_F2_scanner_does_not_reuse_trading_time_constants():
    """C5 — 매매 시각 상수(`TIME_POST_NXT_OPEN` 등) 재사용 금지.

    매수 보드 시각을 바꾸면 적재 규약이 딸려 바뀌는 커플링 차단
    (`tradable_boards` ↔ 청산 규약 커플링을 끊어 둔 기존 원칙과 같은 이유).
    """
    src = _SCANNER_SRC.read_text(encoding="utf-8")
    for name in ("TIME_POST_NXT_OPEN", "TIME_MAIN_CLOSE", "TIME_STOCK_MASTER_DAILY_LOAD"):
        assert name not in src, f"C5 위반 — 매매/스케줄 시각 상수 `{name}` 재사용"

    tree = ast.parse(src)
    imported_time_consts = [
        a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        for a in n.names
        if a.name.startswith("TIME_")
    ]
    assert imported_time_consts == [], (
        f"C5 위반 — 외부 TIME_* 상수 import 금지 (실측 {imported_time_consts})"
    )


def test_F3_scanner_has_no_naive_datetime_now():
    """C6 (불변식) — scanner.py 에 인자 없는 `datetime.now()` 0건 (tz-aware 강제).

    현재도 5곳 전부 `datetime.now(KST_TZ)` 다. Green 이 naive 를 새로 들여오면 붉어진다.
    """
    tree = ast.parse(_SCANNER_SRC.read_text(encoding="utf-8"))
    naive = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "now"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "datetime"
        and not n.args
        and not n.keywords
    ]
    assert naive == [], f"naive datetime.now() 금지 (C6) — 라인 {naive}"


# ══════════════════════════════════════════════════════════════════════
# G. 시나리오 — 자문 §A-6 (4) 낮 재배포 구멍 · (5) 수렴 3일
# ══════════════════════════════════════════════════════════════════════
class _FakeDailyStore:
    """`stock_master_daily` 인메모리 대역 (ticker → {bas_dd: candle})."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, dict]] = {}
        self.upsert_log: list[tuple[str, str, tuple[str, ...]]] = []

    def seed(self, ticker: str, candles: list[dict]) -> None:
        for c in candles:
            self.rows.setdefault(ticker, {})[c["stck_bsop_date"]] = c

    async def max_bas_dd(self, ticker: str):
        keys = self.rows.get(ticker) or {}
        if not keys:
            return None
        newest = max(keys)
        return date(int(newest[:4]), int(newest[4:6]), int(newest[6:8]))

    async def count_by_ticker(self, ticker: str) -> int:
        return len(self.rows.get(ticker) or {})

    async def upsert_batch(self, ticker: str, candles: list[dict]) -> int:
        # 사이클 263 — 어느 실행이 어떤 날짜를 다시 썼는지 기록.
        # (가) 적용 후 "최종값 보정" 의 담지자가 *아침 재fetch* → *D+1 16:00 의 7일 증분 창*
        # 으로 바뀌었기 때문에, 그 창이 실제로 D-1 을 재기록하는지 잠근다.
        self.upsert_log.append((
            datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
            ticker,
            tuple(str(c["stck_bsop_date"]) for c in candles),
        ))
        for c in candles:
            self.rows.setdefault(ticker, {})[str(c["stck_bsop_date"])] = c
        return len(candles)

    def head(self, ticker: str) -> dict | None:
        keys = self.rows.get(ticker) or {}
        return keys[max(keys)] if keys else None


def _is_stub(candle: dict) -> bool:
    return (
        int(candle["acml_vol"]) == 0
        and candle["stck_hgpr"] == candle["stck_lwpr"] == candle["stck_clpr"]
    )


_SESSIONS = [
    date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4),
    date(2026, 9, 7), date(2026, 9, 8), date(2026, 9, 9),
]


def _sim_close(d: date) -> int:
    return 10_000 + 100 * _SESSIONS.index(d)


def _sim_final_vol(d: date) -> int:
    return 100_000 + _SESSIONS.index(d)


def _sim_real(d: date) -> dict:
    """**최종** 봉 — 애프터마켓(~20:00)까지 담은 확정 거래량."""
    return _bar(d, close=_sim_close(d), vol=_sim_final_vol(d))


#: 09-11 실측 최대 오염(현대차 +13.97%)을 시장 모델에 반영한 부분 거래량 비율.
#: 중앙값 +0.51% 가 아니라 **최대치**를 쓴다 — 시뮬이 재려는 것은 "평균적으로 얼마나
#: 틀리나" 가 아니라 "부분값이 확정값과 **다른 값**임을 필터가 알아보나" 이고,
#: 근소한 차이는 반올림·정수 절삭에 묻혀 단언을 공허하게 만든다.
_SIM_PARTIAL_VOL_RATIO = 0.87


def _sim_partial(d: date) -> dict:
    """**부분** 봉 — OHLC 는 15:30 확정값과 동일하고 **거래량만 모자란다**(09-11 실측).

    ⚠️ 이 함수가 cycle283 재기준선의 핵심이다. 종전 모델(`15:40` 이후면 곧바로
    `_sim_real`)은 "장 마감 40분 뒤면 KIS 가 확정봉을 준다" 는 **반증된 명제**를
    시장 대역에 박아 두고 있었다. 그 대역 위에서는 09-11 결함(부분봉을 확정봉으로
    박음)이 **구조적으로 재현 불가능**하다 — 필터를 15:40 으로 되돌려도 시뮬은
    초록이다. 부분값과 최종값이 **다른 값**이어야 비로소 스위트가 결함을 본다.
    """
    partial_vol = int(_sim_final_vol(d) * _SIM_PARTIAL_VOL_RATIO)
    assert partial_vol != _sim_final_vol(d), "부분값이 최종값과 같으면 시뮬이 공허하다"
    return _bar(d, close=_sim_close(d), vol=partial_vol)


def _sim_kis_response(days: int) -> list[dict]:
    """KIS 대역 (cycle283 모델) — 하루를 **세 구간**으로 나눈다.

    - 장 전(~09:00): 오늘 **껍데기** 봉 (O=H=L=C=전일종가, 거래량 0)
    - 09:00~20:00: 오늘 **부분** 봉 — OHLC 는 15:30 이후 확정이지만 거래량은 계속 는다
      (09-11 실측: 일봉 OHLC 6종목 전수 불변 / 거래량·거래대금은 시간외 동안 증가)
    - 20:00~: 오늘 **최종** 봉 (애프터마켓 종료 후)

    ⚠️ 20:00 확정 자체는 아직 **미실측 가설**이다(`_workspace/00_URGENT_WORKLIST.md` 09-14 실측 목록
    §2 마지막 행 = "KIS 일봉이 애프터마켓 물량을 언제 반영하는가 → 문서에 근거 없음").
    09-14 저녁 §4-1 실측(20:05/20:20/20:40/21:00 재조회)에서 어긋나면 여기 상수와
    `scanner._DAILY_LOAD_TODAY_BAR_CUTOFF` 를 함께 뒤로 민다.
    """
    now = datetime.now(KST)
    today = now.date()
    out: list[dict] = []
    prior = [d for d in _SESSIONS if d < today]
    if today in _SESSIONS:
        if now.time() < dtime(9, 0):
            out.append(_stub_bar(today, _sim_close(prior[-1])))
        elif now.time() < dtime(20, 0):
            out.append(_sim_partial(today))
        else:
            out.append(_sim_real(today))
    for d in reversed(prior):
        out.append(_sim_real(d))
    return out[:days]


@pytest.mark.asyncio
async def test_G1_intraday_redeploy_hole_is_closed():
    """§A-6 (4) — 13:04 재배포 immediate 가 부분봉을 박지 않고, 같은 날 **20:30** 이 fetch 한다.

    (가) 단독이면 마커 만료(D 12:0x)로 immediate 가 다시 떠서 **부분봉**을 확정봉처럼
    박고 그날 정기 적재가 skip 된다. 실측 12:00~15:30 full 배포 = 최근 30일 5건(주 1회 이상).

    cycle283 재기준선 — 정기 적재 시각이 16:00 → 20:30 이고, 시장 대역이 16:05 에도
    **부분 거래량**을 주므로 "두 번째 실행" 을 20:30 으로 옮긴다. 의도(장중 재기동이
    구멍을 못 만든다)는 불변이며, 오히려 이제 **거래량 축까지** 검사한다.
    """
    store = _FakeDailyStore()
    store.seed("005930", [_sim_real(d) for d in _SESSIONS if d <= date(2026, 9, 7)])
    ticker = "005930"
    fetch_log: list[str] = []

    async def _fetch(t, days):
        fetch_log.append(datetime.now(KST).strftime("%H:%M"))
        return _sim_kis_response(days)

    from contextlib import ExitStack

    def _stack(stack):
        stack.enter_context(patch("src.db.stock_master.list_all",
                                  new=AsyncMock(return_value=_universe(ticker))))
        stack.enter_context(patch("src.db.stock_master_daily.max_bas_dd",
                                  new=AsyncMock(side_effect=store.max_bas_dd)))
        stack.enter_context(patch("src.db.stock_master_daily.count_by_ticker",
                                  new=AsyncMock(side_effect=store.count_by_ticker)))
        stack.enter_context(patch("src.api.condition.fetch_daily_candles",
                                  new=AsyncMock(side_effect=_fetch)))
        stack.enter_context(patch("src.db.stock_master_daily.upsert_batch",
                                  new=AsyncMock(side_effect=store.upsert_batch)))
        stack.enter_context(patch("asyncio.sleep", new=AsyncMock()))

    # 1) 13:04 재배포 immediate
    with freeze_time("2026-09-08T13:04:00+09:00"):
        with ExitStack() as stack:
            _stack(stack)
            await scanner._stock_master_daily_load_once()

    assert _ymd(date(2026, 9, 8)) not in (store.rows.get(ticker) or {}), (
        "장중 부분봉이 DB 에 기록됐다 — 그날 16:00 이 skip 되고 다음 아침 prepare 가 "
        "'13시까지만의 고가/저가/종가'를 전일봉으로 읽는다 (§A-1 낮 재배포 구멍)"
    )
    assert await store.max_bas_dd(ticker) == date(2026, 9, 7)

    # 2) 같은 날 20:30 정기 (cycle283)
    with freeze_time("2026-09-08T20:30:00+09:00"):
        with ExitStack() as stack:
            _stack(stack)
            summary = await scanner._stock_master_daily_load_once()

    assert summary["skipped_fresh"] == 0, "latest=D-1 < today → 20:30 이 fetch 해야 한다"
    head = store.head(ticker)
    assert head is not None and head["stck_bsop_date"] == _ymd(date(2026, 9, 8))
    assert not _is_stub(head), "20:30 기록은 확정 실봉 의무"
    assert int(head["acml_vol"]) == _sim_final_vol(date(2026, 9, 8)), (
        "20:30 기록은 **최종** 거래량이어야 한다 — 부분값이 박히면 09-11 사고의 재현이다 "
        f"(실측 {head['acml_vol']}, 최종 {_sim_final_vol(date(2026, 9, 8))}, "
        f"부분 {int(_sim_final_vol(date(2026, 9, 8)) * _SIM_PARTIAL_VOL_RATIO)})"
    )
    assert fetch_log == ["13:04", "20:30"], f"두 실행 모두 fetch 의무 (실측 {fetch_log})"


@pytest.mark.asyncio
async def test_G2_three_day_convergence_simulation():
    """§A-6 (5) — D0 껍데기 → D1 전환 → D2 정상 (07:56 / **20:30** × 3일, cycle283).

    성공 서명: (i) 아침 immediate 는 **첫날만** 실행 (D1·D2 는 마커 15.9h 로 skip)
    (ii) DB 에 껍데기 행이 한 건도 남지 않는다 (iii) D1 부터 아침 prepare 가 읽는
    헤드가 **직전 거래일 확정 실봉**이다.
    """
    from contextlib import ExitStack

    ticker = "005930"
    store = _FakeDailyStore()
    # 과거 확정봉 55행 — `count_by_ticker >= _DAILY_LOAD_INCREMENTAL_THRESHOLD(50)` 을
    # 만족시켜 **증분 분기**(`fetch_days=7`)로 돌게 한다. 프로덕션의 평시 상태이고,
    # 아래 "보정 창 존치" 단언이 재려는 대상이 바로 그 7일 창이다.
    store.seed(ticker, [
        _bar(date(2026, 6, 1) + timedelta(days=i), close=9_000 + i, vol=500_000 + i)
        for i in range(55)
    ])
    # 배포 직전 상태 = 09-04 껍데기가 헤드 (09-04 아침 immediate 가 쓴 것)
    store.seed(ticker, [_sim_real(d) for d in (date(2026, 9, 2), date(2026, 9, 3))])
    store.seed(ticker, [_stub_bar(date(2026, 9, 4), _sim_close(date(2026, 9, 3)))])

    marker: dict[str, str] = {}
    once_calls: list[datetime] = []
    real_once = scanner._stock_master_daily_load_once

    async def _counting_once(force: bool = False):
        once_calls.append(datetime.now(KST))
        return await real_once(force)

    async def _fetch(_t, days):
        return _sim_kis_response(days)

    def _stack(stack):
        stack.enter_context(patch("src.db.stock_master.list_all",
                                  new=AsyncMock(return_value=_universe(ticker))))
        stack.enter_context(patch("src.db.stock_master_daily.max_bas_dd",
                                  new=AsyncMock(side_effect=store.max_bas_dd)))
        stack.enter_context(patch("src.db.stock_master_daily.count_by_ticker",
                                  new=AsyncMock(side_effect=store.count_by_ticker)))
        stack.enter_context(patch("src.api.condition.fetch_daily_candles",
                                  new=AsyncMock(side_effect=_fetch)))
        stack.enter_context(patch("src.db.stock_master_daily.upsert_batch",
                                  new=AsyncMock(side_effect=store.upsert_batch)))
        stack.enter_context(patch("asyncio.sleep", new=AsyncMock()))
        stack.enter_context(patch("src.engine.scanner._stock_master_daily_load_once",
                                  _counting_once))
        stack.enter_context(patch(
            "src.engine.stock_master_daily_metrics.record_stock_master_daily_load",
            MagicMock()))
        stack.enter_context(patch(
            "src.engine.stock_master_daily_metrics.flush_stock_master_daily_load_collector",
            MagicMock()))
        stack.enter_context(patch(
            "src.db.system_config.get_task_last_success",
            AsyncMock(side_effect=lambda label: marker.get(label)), create=True))
        stack.enter_context(patch(
            "src.db.system_config.set_task_last_success",
            AsyncMock(side_effect=lambda label, iso: marker.__setitem__(label, iso)),
            create=True))
        stack.enter_context(patch("src.engine.task_loop_helper.asyncio.sleep",
                                  new_callable=AsyncMock))

    heads_at_morning: dict[str, str] = {}
    sim_days = [date(2026, 9, 7), date(2026, 9, 8), date(2026, 9, 9)]

    for day in sim_days:
        # ── 07:56 아침 (부팅 immediate — 실 게이트 경유)
        with freeze_time(f"{day.isoformat()}T07:56:00+09:00"):
            head = store.head(ticker)
            heads_at_morning[day.isoformat()] = head["stck_bsop_date"] if head else ""
            with ExitStack() as stack:
                _stack(stack)
                await data_load_tasks.stock_master_daily_load_task_loop(
                    FakeScheduler(running=False), wait_time=dtime(20, 30)
                )
        # ── 20:30 정기 (while 루프 1회분 = once() + 마커 기록)
        with freeze_time(f"{day.isoformat()}T20:30:30+09:00"):
            with ExitStack() as stack:
                _stack(stack)
                await scanner._stock_master_daily_load_once()
            marker["stock_master_daily_load"] = datetime.now(KST).isoformat()

    morning_calls = [c for c in once_calls if c.hour == 7]
    assert len(morning_calls) == 1, (
        f"아침 immediate 는 D0(마커 부재) 1회뿐 의무 — D1/D2 는 15.9h fresh skip. "
        f"실측 {[c.isoformat() for c in morning_calls]}"
    )
    assert morning_calls[0].date() == date(2026, 9, 7)

    stubs = {
        bas_dd for bas_dd, c in store.rows[ticker].items() if _is_stub(c)
    }
    assert stubs == set(), f"수렴 후 껍데기 행 잔존 금지 (실측 {sorted(stubs)})"

    assert heads_at_morning["2026-09-08"] == _ymd(date(2026, 9, 7)), (
        "D1 아침 prepare 가 읽는 헤드는 D0 확정 실봉 의무 "
        f"(실측 {heads_at_morning['2026-09-08']})"
    )
    assert heads_at_morning["2026-09-09"] == _ymd(date(2026, 9, 8)), (
        "D2 아침 prepare 가 읽는 헤드는 D1 확정 실봉 의무 "
        f"(실측 {heads_at_morning['2026-09-09']})"
    )
    for iso in ("2026-09-08", "2026-09-09"):
        head_bar = store.rows[ticker][heads_at_morning[iso]]
        assert not _is_stub(head_bar), f"{iso} 아침 헤드가 껍데기다"

    # ── 보정 창 존치 (담지자 교체의 잠금)
    # (가) 적용 후 아침 immediate 가 정상일마다 skip 되므로, "D 봉의 최종값" 을 나중에
    # 바로잡는 담지자는 더 이상 *다음 날 아침 재fetch* 가 아니라 **D+1 20:30 정기 실행의
    # 7일 증분 창**(`fetch_days=7` → `ON CONFLICT DO UPDATE`)이다. 누가 그 창을 1~2일로
    # 줄이면 D 봉이 20:30 스냅샷에 영구 고정되므로 여기서 붉어져야 한다.
    evening_0908 = [
        dates for ts, _t, dates in store.upsert_log if ts == "2026-09-08 20:30"
    ]
    assert evening_0908, "D+1 20:30 정기 실행이 upsert 에 도달해야 한다"
    assert _ymd(date(2026, 9, 8)) in evening_0908[0], "20:30 은 당일 확정봉을 쓴다"
    assert _ymd(date(2026, 9, 7)) in evening_0908[0], (
        "20:30 증분 창이 **직전 거래일 봉도 다시 쓴다** = 최종값 보정 담지자. "
        f"창을 줄이면 이 단언이 붉어진다 (실측 {evening_0908[0]})"
    )


# ══════════════════════════════════════════════════════════════════════
# H. 영구 불변식 — 자문 §8-6 / §9-8 전제 보존
# ══════════════════════════════════════════════════════════════════════
def test_H1_daily_candle_strategies_keep_today_bar_guard():
    """자문 §9-8 (영구) — 일봉을 소비하는 전략은 `prev_idx` 오늘봉 가드를 갖는다.

    "08:02·16:20 prepare 는 시정 전후 byte 동일" 이라는 판단이 이 가드 위에 서 있다.
    새 전략이 이걸 빠뜨리면 그 전제가 깨진다 (불변식 — 현재 6파일 전부 보유).
    """
    strat_dir = _REPO_ROOT / "src" / "engine" / "strategies"
    missing = []
    for path in sorted(strat_dir.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "get_recent_daily" not in src and "fetch_daily_candles" not in src:
            continue  # 일봉 미소비 전략 (momentum)
        if 'candles[0].get("stck_bsop_date") == today_str' not in src:
            missing.append(path.name)
    assert missing == [], (
        f"일봉 소비 전략에 오늘봉 가드(prev_idx) 부재: {missing} — "
        "자문 §8-6 전제(08:02/16:20 무변화)가 깨진다"
    )
