"""종목 차트용 KIS 기간별시세 날짜 창 페이징 (cycle387).

정본: `_workspace/red/cycle387_stock_chart_spec.md` §1.3 · §1.4 · §1.5.

`stock_master_daily`(390일 보관)로는 5년 차트를 채울 수 없어, KIS `FHKST03010100`
(국내주식기간별시세)을 시세 풀(`kis_get_quote`) 경유로 직접 페이징한다. `tr_cont` 로
다음 페이지를 받을 수 없으므로(정본 — `docs/kis/domestic-stock-quote.md:5448`), 시작일을
고정하고 종료일 커서를 과거로 당기는 날짜 창 페이징이 유일한 길이다(§1.3).

읽기 전용 KIS 시세 조회 하나다 — 매매 경로(`kis_get`/`kis_post`, 8영역)와 섞이지 않는다
(AST 가드 `tests/unit/ast/test_cycle387_ast_stock_chart_scope.py`).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from src.api.base import kis_get_quote
from src.api.condition import DAILY_PRICE_URL
from src.db._kst import now_kst_iso
from src.models.candle_chart import CandleChart

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# ─────────────────────────────────────────────────────────────────────────────
# 상수 (§1.4 — 값은 AST 가드 G4 가 잠근다)
# ─────────────────────────────────────────────────────────────────────────────

_KIS_MAX_ROWS = 100
_MAX_CALLS_PER_FETCH: dict[str, int] = {"D": 15, "W": 4, "M": 2}
#: 차트 KIS 호출 사이 최소 간격(초). 조회 하나 안의 창 사이만이 아니라 **조회 경계를 넘어서도**
#: 모든 호출 앞에서 지킨다 — 이 기능의 몫을 초당 4건 이하로 묶는다(`base.py` 전역 초당 20건을
#: 주문·잔고 호출과 함께 쓴다).
_WINDOW_SLEEP_SECS = 0.25
_FETCH_CONCURRENCY = 1
_QUEUE_WAIT_SECS = 20.0
_FETCH_TIME_BUDGET_SECS = 25.0
_CACHE_TTL_SECS = 600.0
_PARTIAL_CACHE_TTL_SECS = 60.0
_CACHE_MAX_ENTRIES = 32
_PROVISIONAL_CUTOFF = timedelta(hours=6)

_PERIOD_LABELS = {"D": "일봉", "W": "주봉", "M": "월봉"}

#: 시계 seam — 테스트가 `_monotonic` 자체를 갈아끼운다. 함수 안에서는 매번
#: 모듈 전역으로 다시 읽어야 한다(기본 인자·클로저에 묶지 않는다).
_monotonic = time.monotonic


class ChartBusyError(Exception):
    """다른 조회가 모듈 전역 세마포어를 쥔 채 대기 상한을 넘겼다."""


# ─────────────────────────────────────────────────────────────────────────────
# 모듈 상태 (테스트마다 `_reset_state_for_tests()` 로 새로 만든다)
# ─────────────────────────────────────────────────────────────────────────────

_Key = tuple[str, str, int]

_cache: "OrderedDict[_Key, tuple[CandleChart, float]]" = OrderedDict()
_inflight: dict[_Key, "asyncio.Task[CandleChart]"] = {}
_semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)
#: 마지막 차트 KIS 호출을 시작한 시각(`_monotonic` 기준). `None` = 아직 부른 적 없음.
#: 세마포어 안에서만 읽고 쓴다(동시 조회 1건이라 경합이 없다).
_last_call_at: Optional[float] = None


def _reset_state_for_tests() -> None:
    """캐시·inflight·세마포어·호출 간격 기록을 새로 만든다.

    asyncio 프리미티브는 처음 기다린 이벤트 루프에 묶인다 — 테스트마다 새 루프면
    재사용 시 `RuntimeError` 이므로 매 테스트 새로 만든다. `_monotonic` 은 여기서
    건드리지 않는다(테스트가 별도로 monkeypatch 한다).
    """
    global _cache, _inflight, _semaphore, _last_call_at
    _cache = OrderedDict()
    _inflight = {}
    _semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY)
    _last_call_at = None


def _drain_task_exception(task: "asyncio.Task[Any]") -> None:
    """inflight task 종료 시 예외 회수 — "Task exception was never retrieved" 차단.

    `src/api/condition.py::_drain_task_exception` 과 같은 역할의 로컬 헬퍼다
    (private 함수를 import 하지 않는다 — G1 허용 목록 밖).
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.debug("[stock_chart] inflight task exception (drained): %r", exc)


# ─────────────────────────────────────────────────────────────────────────────
# 인자 검증 · 구간 계산 (§1.3-1)
# ─────────────────────────────────────────────────────────────────────────────

def _validate_args(ticker: Any, period: Any, years: Any) -> None:
    # `str.isdigit()` 는 아랍-인도·전각 숫자도 참이다 — ASCII 검사를 함께 한다.
    if not (isinstance(ticker, str) and len(ticker) == 6 and ticker.isascii() and ticker.isdigit()):
        raise ValueError(f"ticker 는 6자리 숫자여야 합니다: {ticker!r}")
    if period not in ("D", "W", "M"):
        raise ValueError(f"period 는 D/W/M 이어야 합니다: {period!r}")
    if isinstance(years, bool) or not isinstance(years, int) or not (1 <= years <= 5):
        raise ValueError(f"years 는 1~5 사이 정수여야 합니다: {years!r}")


def _years_ago(d: date, years: int) -> date:
    """`years` 년 전 같은 월·일. 2/29 → 2/28(그 해가 윤년이 아니면)."""
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return date(d.year - years, 2, 28)


def _bucket_first_day(d: date, period: str) -> date:
    """봉이 대표하는 기간(버킷)의 첫날. D=그 날 · W=ISO 주 월요일 · M=그 달 1일."""
    if period == "D":
        return d
    if period == "W":
        return d - timedelta(days=d.weekday())
    return d.replace(day=1)


def _bucket_last_weekday(d: date, period: str) -> date:
    """버킷 안의 마지막 평일. D=그 날 · W=그 주 금요일 · M=그 달 마지막 평일."""
    if period == "D":
        return d
    if period == "W":
        return _bucket_first_day(d, "W") + timedelta(days=4)
    if d.month == 12:
        next_month_first = date(d.year + 1, 1, 1)
    else:
        next_month_first = date(d.year, d.month + 1, 1)
    last_day = next_month_first - timedelta(days=1)
    while last_day.weekday() >= 5:  # 토(5)·일(6) → 앞 평일로
        last_day -= timedelta(days=1)
    return last_day


def _bucket_key(d: date, period: str) -> Any:
    if period == "D":
        return d
    if period == "W":
        return d.isocalendar()[:2]
    return (d.year, d.month)


def _next_cursor_end(oldest: date, period: str) -> date:
    """다음 창의 `FID_INPUT_DATE_2`. D=oldest−1일 · W/M=버킷 첫날−1일."""
    if period == "D":
        return oldest - timedelta(days=1)
    return _bucket_first_day(oldest, period) - timedelta(days=1)


def _compute_range(today: date, period: str, years: int) -> tuple[date, date]:
    base = _years_ago(today, years)
    if period == "D":
        start = base
    elif period == "W":
        start = base - timedelta(days=base.weekday())
    else:
        start = base.replace(day=1)
    return start, today


def _is_provisional(last_date: date, period: str, now_kst: datetime) -> bool:
    """마지막 봉 버킷 안에 「평일 d ≥ (now−6시간).date()」 가 하나라도 있으면 True.

    cycle386 실측 — KIS `J` 일봉은 D일 20:00 뒤에도 애프터마켓 값을 싣고, 정규장
    값으로 바뀌는 것은 D+1일 05:28 전 ~ 23:12 뒤 사이다. 06:00 을 경계로 쓴다
    (`daily_bar_finalize` 의 06:00 경계와 같은 값). 값은 고치지 않는다 — 표시 문구만.
    """
    cutoff_date = (now_kst - _PROVISIONAL_CUTOFF).date()
    return _bucket_last_weekday(last_date, period) >= cutoff_date


def _safe_int(v: Any) -> int:
    if v is None:
        return 0
    s = str(v).strip()
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 0


def _parse_ymd(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def _normalize_and_filter(
    buckets: dict[Any, dict], start: date, end: date, period: str
) -> tuple[list[dict], int]:
    """병합된 버킷 → 정규화된 봉 목록(오름차순) + 버린 수(§1.3-5)."""
    kept: list[dict] = []
    dropped = 0
    for row in buckets.values():
        d = _parse_ymd(row["stck_bsop_date"])
        o = _safe_int(row.get("stck_oprc"))
        h = _safe_int(row.get("stck_hgpr"))
        low = _safe_int(row.get("stck_lwpr"))
        c = _safe_int(row.get("stck_clpr"))
        if d > end or _bucket_first_day(d, period) < start or min(o, h, low, c) <= 0:
            dropped += 1
            continue
        kept.append({
            "date": d.isoformat(),
            "open": o,
            "high": h,
            "low": low,
            "close": c,
            "volume": _safe_int(row.get("acml_vol")),
            "amount": _safe_int(row.get("acml_tr_pbmn")),
        })
    kept.sort(key=lambda b: b["date"])
    return kept, dropped


# ─────────────────────────────────────────────────────────────────────────────
# KIS 날짜 창 페이징 (§1.3-4)
# ─────────────────────────────────────────────────────────────────────────────

async def _pace_chart_call() -> None:
    """직전 차트 KIS 호출 시작으로부터 `_WINDOW_SLEEP_SECS` 가 지날 때까지 쉬고, 이번 시작을 기록한다.

    세마포어 안의 **모든** `kis_get_quote` 호출 바로 앞에서 부른다. 조회 하나 안의 창 사이에서만
    쉬면 앞 조회가 세마포어를 놓는 순간 줄 선 다음 조회가 곧바로 KIS 를 부르고, 월봉(1회 호출)은
    한 번도 쉬지 않는다 — 종목 수만큼 연달아 두드려 전역 초당 한도를 다 쓴다.
    """
    global _last_call_at
    if _last_call_at is not None:
        wait = _WINDOW_SLEEP_SECS - (_monotonic() - _last_call_at)
        if wait > 0:
            await asyncio.sleep(wait)
    _last_call_at = _monotonic()


async def _fetch_windowed(
    ticker: str, period: str, years: int, start: date, end: date, now: datetime
) -> CandleChart:
    max_calls = _MAX_CALLS_PER_FETCH[period]
    t_start = _monotonic()
    cursor_end = end
    calls_used = 0
    complete = True
    incomplete_reason: Optional[str] = None
    name: Optional[str] = None
    buckets: dict[Any, dict] = {}

    while True:
        is_first_window = calls_used == 0
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": cursor_end.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": period,
            "FID_ORG_ADJ_PRC": "0",
        }
        await _pace_chart_call()
        try:
            data = await kis_get_quote(DAILY_PRICE_URL, "FHKST03010100", params)
        except Exception:
            if is_first_window:
                raise
            complete = False
            incomplete_reason = "window_error"
            break

        calls_used += 1
        if is_first_window:
            raw_name = (data.get("output1") or {}).get("hts_kor_isnm")
            name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None

        rows = data.get("output2") or data.get("output") or []
        dated_rows = [r for r in rows if r.get("stck_bsop_date")]
        for r in dated_rows:
            key = _bucket_key(_parse_ymd(r["stck_bsop_date"]), period)
            buckets.setdefault(key, r)  # 먼저 받은(더 최신 창) 값이 남는다

        n = len(dated_rows)
        if n == 0:
            break
        if n < _KIS_MAX_ROWS:
            break

        oldest = min(_parse_ymd(r["stck_bsop_date"]) for r in dated_rows)
        if _bucket_first_day(oldest, period) <= start:
            break
        next_end = _next_cursor_end(oldest, period)
        if next_end < start:
            break
        if next_end >= cursor_end:
            complete = False
            incomplete_reason = "no_progress"
            break
        if calls_used >= max_calls:
            complete = False
            incomplete_reason = "call_cap"
            break
        if (_monotonic() - t_start) > _FETCH_TIME_BUDGET_SECS:
            complete = False
            incomplete_reason = "time_budget"
            break

        cursor_end = next_end

    bars, dropped = _normalize_and_filter(buckets, start, end, period)
    last_provisional = (
        _is_provisional(date.fromisoformat(bars[-1]["date"]), period, now) if bars else False
    )

    if not complete:
        oldest_str = bars[0]["date"] if bars else ""
        logger.warning(
            "[stock_chart_partial] ticker=%s period=%s reason=%s calls=%d bars=%d oldest=%s",
            ticker, period, incomplete_reason, calls_used, len(bars), oldest_str,
        )

    elapsed_ms = (_monotonic() - t_start) * 1000
    logger.info(
        "[stock_chart_fetch] ticker=%s period=%s years=%d calls=%d bars=%d dropped=%d "
        "complete=%s reason=%s elapsed_ms=%.1f",
        ticker, period, years, calls_used, len(bars), dropped, complete,
        incomplete_reason, elapsed_ms,
    )

    return CandleChart(
        ticker=ticker,
        name=name,
        period=period,
        years=years,
        adjusted=True,
        market="J",
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        bars=bars,
        complete=complete,
        incomplete_reason=incomplete_reason,
        last_bar_provisional=last_provisional,
        dropped_bars=dropped,
        kis_calls=calls_used,
        cached=False,
        fetched_at=now_kst_iso(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 캐시 (LRU, §1.4)
# ─────────────────────────────────────────────────────────────────────────────

def _cache_get(key: _Key) -> Optional[CandleChart]:
    entry = _cache.get(key)
    if entry is None:
        return None
    chart, expire_at = entry
    if _monotonic() >= expire_at:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return chart


def _cache_set(key: _Key, chart: CandleChart, ttl: float) -> None:
    """저장하면서 이미 만료된 항목을 걷어낸다 — 같은 키를 다시 읽거나 개수가 넘칠 때까지
    만료된 차트를 들고 있지 않는다. 그 뒤에도 넘치면 가장 오래 안 쓴 것부터 뺀다(LRU)."""
    now = _monotonic()
    for expired in [k for k, (_, expire_at) in _cache.items() if now >= expire_at]:
        del _cache[expired]
    _cache[key] = (chart, now + ttl)
    while len(_cache) > _CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)


# ─────────────────────────────────────────────────────────────────────────────
# 공개 진입점
# ─────────────────────────────────────────────────────────────────────────────

async def _run_fetch(
    key: _Key, ticker: str, period: str, years: int, start: date, end: date, now: datetime
) -> CandleChart:
    t0 = _monotonic()
    acquired = False
    try:
        try:
            await asyncio.wait_for(_semaphore.acquire(), _QUEUE_WAIT_SECS)
            acquired = True
        except asyncio.TimeoutError as exc:
            waited = _monotonic() - t0
            logger.warning(
                "[stock_chart_busy] ticker=%s period=%s waited_s=%.2f", ticker, period, waited
            )
            raise ChartBusyError(f"chart busy: ticker={ticker} period={period}") from exc

        chart = await _fetch_windowed(ticker, period, years, start, end, now)
    finally:
        if acquired:
            _semaphore.release()
        current = _inflight.get(key)
        if current is asyncio.current_task():
            _inflight.pop(key, None)

    ttl = _CACHE_TTL_SECS if chart.complete else _PARTIAL_CACHE_TTL_SECS
    _cache_set(key, chart, ttl)
    return chart


async def fetch_candle_chart(
    ticker: str, period: str = "D", years: int = 5, *, now_kst: Optional[datetime] = None
) -> CandleChart:
    """5년 이내 일/주/월봉 차트를 KIS 에서 조회한다(캐시 → single-flight → 직렬 세마포어).

    Raises:
        ValueError: 인자 위반(방어선 2 — 라우트 FastAPI 검증이 방어선 1).
        KisApiError: 첫 창이 실패했다(그대로 전파, 캐시하지 않는다).
        ChartBusyError: 다른 조회가 세마포어를 쥔 채 대기 상한을 넘었다.
    """
    _validate_args(ticker, period, years)
    now = now_kst if now_kst is not None else datetime.now(KST)
    start, end = _compute_range(now.date(), period, years)
    key: _Key = (ticker, period, years)

    cached = _cache_get(key)
    if cached is not None:
        return cached.model_copy(update={"cached": True})

    task = _inflight.get(key)
    if task is None or task.done():
        task = asyncio.create_task(_run_fetch(key, ticker, period, years, start, end, now))
        task.add_done_callback(_drain_task_exception)
        _inflight[key] = task

    return await asyncio.shield(task)
