"""RS·재무·목표가 리비전 2단계 — 16:40 재무 적재에 얹는 추가 적재 3갈래 (명세 `_workspace/design/2026-10-13_rs_fundamental_phase2.md` §A).

1. 분기 재무(`div_cls="1"`) 2. 투자의견(`FHKST663300C0`, 주 1회) 3. 추정실적 월 스냅샷(`HHKST668300C0`).
매매 행위 0 — 주문·전략 상태에 닿지 않는다. 각 갈래는 독립 `try`, 전체는 never-raise(`CancelledError` 만 전파).
외부 의존은 모듈 속성으로 부른다(테스트가 원 모듈 속성을 바꾼다).
킬스위치 `system_config.fundamental_extra_load_mode` — 키 없음 = on · `off` = 전부 skip · 그 밖 = on + WARNING.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import src.api.finance as fin_api
import src.api.invest_opinion as io_api
import src.db.invest_opinion as io_db
import src.db.stock_master as sm_db
import src.db.stock_master_financial as smf_db
import src.db.system_config as sc_db
from src.engine import fundamental_score as fs

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

EXTRA_LOAD_HARD_CAP_SECS = 3000  # 50분 — 넘으면 남은 종목은 다음 실행으로 미룬다
_MODE_KEY = "fundamental_extra_load_mode"
_OPINION_MARKER_KEY = "fundamental_opinion_load_last"
_OPINION_INTERVAL = timedelta(days=7)
_OPINION_BACKFILL_DAYS = 400
_OPINION_WINDOW_DAYS = 90
_OPINION_PAGE_SIZE = 100
_SLEEP_SECS = 0.05


def target_quarter(today: date) -> str:
    """오늘 기준 「알 수 있는」 가장 최근 분기말(YYYYMM) — 1단계 `available_from`(+45/+90일) 규칙."""
    cands = [f"{y}{m:02d}" for y in (today.year - 1, today.year) for m in (3, 6, 9, 12)]
    return max(q for q in cands if fs.available_from(q) <= today)


def _new_summary() -> dict[str, Any]:
    return {
        "quarterly_total": 0, "quarterly_fetched": 0, "quarterly_skipped": 0, "quarterly_failed": 0,
        "opinion_tickers": 0, "opinion_rows": 0, "opinion_skipped": 0, "opinion_failed": 0,
        "estimate_saved": 0, "estimate_skipped": 0, "estimate_failed": 0,
        "elapsed_ms": 0, "mode": "on", "truncated": 0,
    }


def _unwrap(raw: object) -> object:
    return raw.get("value") if isinstance(raw, dict) else raw


async def _read_mode() -> str:
    try:
        raw = await sc_db._select_value(_MODE_KEY)
    except Exception:
        logger.warning("[fundamental_extra_load_failed] %s 조회 실패 — on 으로 진행", _MODE_KEY, exc_info=True)
        return "on"
    if raw is sc_db._MISSING:
        return "on"
    val = str(_unwrap(raw)).strip().lower()
    if val == "off":
        return "off"
    if val != "on":
        logger.warning("[fundamental_extra_load_failed] %s=%r 인식 불가 — on 으로 진행", _MODE_KEY, raw)
    return "on"


async def _universe() -> list[str]:
    from src.engine.scanner import _DAILY_LOAD_MIN_MCAP_EOK, _DAILY_LOAD_MIN_TRADE_WON  # 읽기만

    try:
        rows = await sm_db.list_by_filter(
            min_market_cap=_DAILY_LOAD_MIN_MCAP_EOK * 100_000_000,
            min_trade_amount=_DAILY_LOAD_MIN_TRADE_WON,
            is_kospi200=True,
            is_kosdaq150=True,
            limit=1000,
        )
    except Exception:
        logger.exception("[fundamental_extra_load_failed] 유니버스 조회 실패 graceful")
        return []
    out = []
    for row in rows or []:
        t = row.get("ticker", "")
        if t and len(t) == 6 and t.isdigit():
            out.append(t)
    return out


def _over(deadline: float) -> bool:
    return time.monotonic() > deadline


async def _quarterly_branch(tickers: list[str], today: date, deadline: float, summary: dict) -> None:
    target = target_quarter(today)
    for ticker in tickers:
        if _over(deadline):
            summary["truncated"] = 1
            return
        try:
            latest = await smf_db.max_stac_yymm(ticker, div_cls="1")
        except Exception:
            latest = None
        if latest is not None and latest >= target:
            summary["quarterly_skipped"] += 1
            continue
        try:
            rows = await fin_api.fetch_all_financials(ticker, div_cls="1")
            if not rows:
                summary["quarterly_failed"] += 1
            else:
                await smf_db.upsert_financial_batch(ticker, rows)
                summary["quarterly_fetched"] += 1
        except Exception:
            logger.warning("[fundamental_extra_load_failed] quarterly ticker=%s 실패", ticker, exc_info=True)
            summary["quarterly_failed"] += 1
        await asyncio.sleep(_SLEEP_SECS)


def _windows(start: date, end: date) -> list[tuple[date, date]]:
    out, cur = [], start
    while cur <= end:
        stop = min(cur + timedelta(days=_OPINION_WINDOW_DAYS - 1), end)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


async def _fetch_window(ticker: str, a: date, b: date) -> list[dict]:
    rows = await io_api.inquire_invest_opinion(ticker, a, b)
    await asyncio.sleep(_SLEEP_SECS)
    if len(rows) >= _OPINION_PAGE_SIZE and (b - a).days >= 1:
        half = ((b - a).days + 1) // 2
        rows = []
        for x, y in ((a, a + timedelta(days=half - 1)), (a + timedelta(days=half), b)):
            rows += await io_api.inquire_invest_opinion(ticker, x, y)  # 1회만 나눈다
            await asyncio.sleep(_SLEEP_SECS)
    return rows


def _marker_fresh(raw: object, now: datetime) -> bool:
    if raw is sc_db._MISSING:
        return False
    try:
        dt = datetime.fromisoformat(str(_unwrap(raw)))
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return timedelta(0) <= now - dt < _OPINION_INTERVAL


async def _opinion_branch(tickers: list[str], now: datetime, deadline: float, summary: dict) -> None:
    today = now.date()
    if _marker_fresh(await sc_db._select_value(_OPINION_MARKER_KEY), now):
        summary["opinion_skipped"] += len(tickers)
        return
    latest = await io_db.latest_bsop_dates(tickers)
    clean = True
    for ticker in tickers:
        if _over(deadline):
            summary["truncated"] = 1
            clean = False
            break
        d = latest.get(ticker)
        start = today - timedelta(days=_OPINION_BACKFILL_DAYS) if d is None else d + timedelta(days=1)
        if start > today:
            summary["opinion_skipped"] += 1
            continue
        summary["opinion_tickers"] += 1
        collected: list[dict] = []
        try:
            for a, b in _windows(start, today):
                collected += await _fetch_window(ticker, a, b)
            if collected:
                summary["opinion_rows"] += await io_db.upsert_opinions(ticker, collected)
        except Exception:
            # 일부 창만 저장하면 「DB 최신일 다음날부터」 재개 규칙이 빈 창을 영구히 건너뛴다 — 이 종목은 통째로 버린다
            logger.warning("[fundamental_extra_load_failed] opinion ticker=%s 실패", ticker, exc_info=True)
            summary["opinion_failed"] += 1
            clean = False
    if clean:
        await sc_db._upsert_value(_OPINION_MARKER_KEY, {"value": now.isoformat()})


async def _estimate_branch(tickers: list[str], today: date, deadline: float, summary: dict) -> None:
    month = date(today.year, today.month, 1)
    have = await io_db.estimate_snapshot_tickers(month)
    for ticker in tickers:
        if ticker in have:
            summary["estimate_skipped"] += 1
            continue
        if _over(deadline):
            summary["truncated"] = 1
            return
        try:
            resp = await io_api.inquire_estimate_perform(ticker)
            if not resp or not resp.get("settle_months"):
                summary["estimate_skipped"] += 1  # 빈 응답은 저장하지 않는다(커버리지 약 160종목)
            elif await io_db.upsert_estimate_snapshot(ticker, month, resp):
                summary["estimate_saved"] += 1
            else:
                summary["estimate_failed"] += 1
        except Exception:
            logger.warning("[fundamental_extra_load_failed] estimate ticker=%s 실패", ticker, exc_info=True)
            summary["estimate_failed"] += 1
        await asyncio.sleep(_SLEEP_SECS)


async def run_extra_loads_once(*, now_kst: datetime | None = None) -> dict:
    """추가 적재 3갈래 1회 — never-raise(`CancelledError` 만 전파). 반환 = 요약 dict."""
    start = time.monotonic()
    summary = _new_summary()
    branch_errors = 0
    try:
        now = now_kst or datetime.now(KST)
        summary["mode"] = await _read_mode()
        if summary["mode"] == "on":
            deadline = start + EXTRA_LOAD_HARD_CAP_SECS
            tickers = await _universe()
            summary["quarterly_total"] = len(tickers)
            for name, coro_fn in (
                ("quarterly", lambda: _quarterly_branch(tickers, now.date(), deadline, summary)),
                ("opinion", lambda: _opinion_branch(tickers, now, deadline, summary)),
                ("estimate", lambda: _estimate_branch(tickers, now.date(), deadline, summary)),
            ):
                try:
                    await coro_fn()
                except Exception:
                    branch_errors += 1
                    logger.warning("[fundamental_extra_load_failed] %s 갈래 실패 graceful", name, exc_info=True)
    except Exception:
        branch_errors += 1
        logger.exception("[fundamental_extra_load_failed] 예기치 못한 실패 graceful")
    summary["elapsed_ms"] = int((time.monotonic() - start) * 1000)
    failed = (branch_errors + summary["quarterly_failed"] + summary["opinion_failed"]
              + summary["estimate_failed"])
    logger.log(
        logging.WARNING if failed else logging.INFO,
        "[fundamental_extra_load] quarterly_total=%d quarterly_fetched=%d quarterly_skipped=%d "
        "quarterly_failed=%d opinion_tickers=%d opinion_rows=%d opinion_skipped=%d estimate_saved=%d "
        "estimate_skipped=%d elapsed_ms=%d mode=%s truncated=%d opinion_failed=%d estimate_failed=%d "
        "branch_errors=%d",
        summary["quarterly_total"], summary["quarterly_fetched"], summary["quarterly_skipped"],
        summary["quarterly_failed"], summary["opinion_tickers"], summary["opinion_rows"],
        summary["opinion_skipped"], summary["estimate_saved"], summary["estimate_skipped"],
        summary["elapsed_ms"], summary["mode"], summary["truncated"], summary["opinion_failed"],
        summary["estimate_failed"], branch_errors,
    )
    return summary
