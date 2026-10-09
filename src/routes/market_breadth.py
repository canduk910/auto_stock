"""시장 등락 통계 라우트 — `GET /api/market/breadth` (cycle416).

명세: `_workspace/red/cycle416/breadth_spec.md` §2 · §5.2~§5.5 · §7.3
계약: `_workspace/red/cycle416/breadth_contract.md` 「2. 라우트」

관찰 전용 화면(매크로)이다 — 매매 엔진·전략은 이 라우트도 leaf(`market_breadth`)도 import
하지 않는다. KRX 호출은 **모듈 참조**로만 한다(`from src.api import krx`) — 테스트가
`src.api.krx.fetch_stk_bydd_trd`/`fetch_ksq_bydd_trd` 자체를 갈아끼우는 seam 이다.
`src/api/krx.py` 는 한 글자도 고치지 않는다.

캐시·동시성·하루 호출 상한은 **프로세스 메모리** 상태다(재시작·배포 때 비워진다) — 모듈
전역 몇 개로 표현하고 `reset_state()` 가 테스트 seam 으로 비운다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query

from src.api import krx
from src.db import system_config
from src.engine import market_breadth as leaf
from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["market-breadth"])

_KST = timezone(timedelta(hours=9))

SOURCE = "KRX 공개 API 일별 매매정보(유가증권·코스닥)"

MSG_DISABLED = "KRX 공개 API 가 꺼져 있어 시장 등락 통계를 만들 수 없습니다 — 설정 화면의 외부 연동에서 켤 수 있습니다"
MSG_NO_KEY = "KRX 공개 API 키가 등록돼 있지 않아 시장 등락 통계를 만들 수 없습니다"
MSG_CONFIG_ERR = "KRX 연동 설정을 읽지 못했습니다 — 서버 로그 [market_breadth_error] 확인"
MSG_ALL_FAILED = "KRX 에서 자료를 받지 못했습니다 — 잠시 후 다시 시도하세요"
MSG_BUDGET = "오늘 이 화면의 KRX 조회 한도를 다 썼습니다 — 내일 다시 볼 수 있습니다"
MSG_UNEXPECTED = "시장 등락 통계를 만들지 못했습니다 — 서버 로그 [market_breadth_error] 확인"

# ─────────────────────────────────────────────────────────────────────────────
# 모듈 상수 — 호출 시점에 모듈 전역을 읽는다(테스트가 monkeypatch 하는 seam, 계약 2.2)
# ─────────────────────────────────────────────────────────────────────────────

_KRX_CONCURRENCY = 4
_REQUEST_DEADLINE_SECS = 45.0
_RETRY_DELAY_SECS = 1.0
_EMPTY_TTL_SECS = 600
_EMPTY_PERMANENT_AFTER_DAYS = 7
_DAILY_CALL_BUDGET = 1_000
_CACHE_MAX_ENTRIES = 512


# ─────────────────────────────────────────────────────────────────────────────
# 프로세스 메모리 상태 (계약 2.3 · 명세 §5.3)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _CacheEntry:
    status: str  # "ok" | "empty"
    stats: Any  # leaf.DayStats
    cached_at: datetime | None
    permanent: bool


_cache: dict[tuple[str, str], _CacheEntry] = {}
_in_flight: dict[tuple[str, str], "asyncio.Task"] = {}
_call_counts: dict[str, int] = {}
_budget_warned_dates: set[str] = set()
_semaphore: "asyncio.Semaphore | None" = None
_semaphore_loop: "asyncio.AbstractEventLoop | None" = None

_TIMEOUT = object()  # 시한 안에 못 끝난 결과의 자리표시


class _BudgetExhausted(Exception):
    """이 KST 날짜의 KRX 호출 상한을 다 썼다 — 호출을 시도하지 않는다."""


def reset_state() -> None:
    """캐시·진행 중 표·하루 호출 카운터·예산 경고 래치·세마포어를 비운다(테스트 seam)."""
    _cache.clear()
    _in_flight.clear()
    _call_counts.clear()
    _budget_warned_dates.clear()
    global _semaphore, _semaphore_loop
    _semaphore = None
    _semaphore_loop = None


def _get_semaphore() -> "asyncio.Semaphore":
    """실행 중 이벤트 루프마다 하나 — TestClient 가 요청마다 새 루프를 쓴다(계약 2.3)."""
    global _semaphore, _semaphore_loop
    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore_loop is not loop:
        _semaphore = asyncio.Semaphore(_KRX_CONCURRENCY)
        _semaphore_loop = loop
    return _semaphore


def _dash(ymd: str) -> str:
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"


def _ymd_to_date(ymd: str) -> date:
    return date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:]))


# ─────────────────────────────────────────────────────────────────────────────
# 캐시 (명세 §5.3)
# ─────────────────────────────────────────────────────────────────────────────

def _get_valid_cache(market: str, ymd: str) -> "leaf.DayStats | None":
    entry = _cache.get((market, ymd))
    if entry is None:
        return None
    if entry.status == "ok" or entry.permanent:
        return entry.stats
    age = (datetime.now(_KST) - entry.cached_at).total_seconds()
    if age < _EMPTY_TTL_SECS:
        return entry.stats
    return None  # 만료 — 다시 부른다


def _store_cache(market: str, ymd: str, stats: "leaf.DayStats") -> None:
    now = datetime.now(_KST)
    if stats.rows > 0:
        _cache[(market, ymd)] = _CacheEntry(status="ok", stats=stats, cached_at=now, permanent=True)
    else:
        d = _ymd_to_date(ymd)
        permanent = (now.date() - d).days > _EMPTY_PERMANENT_AFTER_DAYS
        if permanent:
            # 검증 결함(LOW, 확정 아님) — KRX 가 호출 한도 초과도 OutBlock_1 없는 HTTP 200 으로
            # 줄 가능성이 있다면 이 로그가 그 날짜를 영구 "휴장"으로 가두기 전 유일한 흔적이다.
            # 재현되면 이 WARNING 의 market/date 로 실제 KRX 응답을 다시 받아 대조한다.
            logger.warning(
                "[market_breadth_permanent_empty] market=%s date=%s age_days=%s",
                market, _dash(ymd), (now.date() - d).days,
            )
        _cache[(market, ymd)] = _CacheEntry(status="empty", stats=stats, cached_at=now, permanent=permanent)
    if len(_cache) > _CACHE_MAX_ENTRIES:
        excess = len(_cache) - _CACHE_MAX_ENTRIES
        for key in sorted(_cache.keys(), key=lambda k: k[1])[:excess]:
            _cache.pop(key, None)


# ─────────────────────────────────────────────────────────────────────────────
# 하루 호출 상한 (명세 §5.3)
# ─────────────────────────────────────────────────────────────────────────────

def _try_consume_budget() -> bool:
    today_str = datetime.now(_KST).date().isoformat()
    count = _call_counts.get(today_str, 0)
    if count >= _DAILY_CALL_BUDGET:
        if today_str not in _budget_warned_dates:
            _budget_warned_dates.add(today_str)
            logger.warning(
                "[market_breadth_budget_exhausted] date=%s budget=%s", today_str, _DAILY_CALL_BUDGET,
            )
        return False
    _call_counts[today_str] = count + 1
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 호출 한 건 — 세마포어 + 재시도 1회 (명세 §5.3)
# ─────────────────────────────────────────────────────────────────────────────

def _log_row_warnings(market: str, ymd: str, rows: list, stats: "leaf.DayStats") -> None:
    if rows and stats.rows == 0:
        logger.warning("[market_breadth_all_unparsed] market=%s date=%s", market, _dash(ymd))
    if stats.sign_mismatch > 0:
        logger.warning(
            "[market_breadth_sign_mismatch] market=%s date=%s n=%s", market, _dash(ymd), stats.sign_mismatch,
        )


async def _call_with_retry(market: str, ymd: str) -> "leaf.DayStats":
    fn = krx.fetch_stk_bydd_trd if market == "kospi" else krx.fetch_ksq_bydd_trd
    last_exc: BaseException | None = None
    for attempt in range(2):
        if not _try_consume_budget():
            raise _BudgetExhausted()
        sem = _get_semaphore()
        try:
            async with sem:
                rows = await fn(ymd)
        except Exception as exc:  # noqa: BLE001 - 재시도 대상, 아래서 1회 더
            last_exc = exc
            if attempt == 0:
                if _RETRY_DELAY_SECS:
                    await asyncio.sleep(_RETRY_DELAY_SECS)
                continue
            break
        else:
            try:
                stats = leaf.aggregate_rows(rows)
            except Exception as exc:  # noqa: BLE001 - 집계 결함은 재시도하지 않는다(결정론적)
                logger.warning(
                    "[market_breadth_fetch_error] market=%s date=%s err=%s",
                    market, _dash(ymd), type(exc).__name__,
                )
                raise
            _log_row_warnings(market, ymd, rows, stats)
            return stats
    logger.warning(
        "[market_breadth_fetch_error] market=%s date=%s err=%s",
        market, _dash(ymd), type(last_exc).__name__,
    )
    raise last_exc  # type: ignore[misc]


async def _run_and_store(market: str, ymd: str) -> "leaf.DayStats":
    try:
        stats = await _call_with_retry(market, ymd)
    finally:
        _in_flight.pop((market, ymd), None)
    _store_cache(market, ymd, stats)
    return stats


def _ensure_task(market: str, ymd: str) -> "asyncio.Task":
    key = (market, ymd)
    task = _in_flight.get(key)
    if task is None:
        task = asyncio.ensure_future(_run_and_store(market, ymd))
        _in_flight[key] = task
    return task


# ─────────────────────────────────────────────────────────────────────────────
# 배치 — 캐시 적중은 즉시, 나머지는 공유 태스크 + 시한 (명세 §5.3)
# ─────────────────────────────────────────────────────────────────────────────

async def _collect_batch(batch: list[date], deadline: float) -> tuple[dict[date, list], int]:
    results: dict[date, list] = {d: [None, None] for d in batch}
    needed: dict[tuple[date, str], "asyncio.Task"] = {}

    for d in batch:
        ymd = d.strftime("%Y%m%d")
        km = _get_valid_cache("kospi", ymd)
        if km is not None:
            results[d][0] = km
        else:
            needed[(d, "kospi")] = _ensure_task("kospi", ymd)
        kd = _get_valid_cache("kosdaq", ymd)
        if kd is not None:
            results[d][1] = kd
        else:
            needed[(d, "kosdaq")] = _ensure_task("kosdaq", ymd)

    if needed:
        remaining = max(deadline - asyncio.get_running_loop().time(), 0.0)
        await asyncio.wait(set(needed.values()), timeout=remaining)

    for (d, market), task in needed.items():
        idx = 0 if market == "kospi" else 1
        if not task.done():
            results[d][idx] = _TIMEOUT
            continue
        try:
            results[d][idx] = task.result()
        except Exception as exc:  # noqa: BLE001 - 날짜 판정용으로 분류한다(classify_day 가 None 취급)
            results[d][idx] = exc
    return results, len(needed)


# ─────────────────────────────────────────────────────────────────────────────
# 날짜 창 채우기 (명세 §2.1 · §2.2 · §5.3)
# ─────────────────────────────────────────────────────────────────────────────

async def _build_window(days: int) -> dict:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _REQUEST_DEADLINE_SECS
    now = datetime.now(_KST)
    today = now.date()
    limit = leaf.lookback_calendar_days(days)
    candidates = leaf.candidate_weekdays(today, days)
    d1 = candidates[0] if candidates else None

    days_list: list[dict] = []
    missing_list: list[date] = []
    empty_list: list[date] = []
    pending_date: date | None = None
    consumed: list[date] = []
    kospi_days: list = []
    kosdaq_days: list = []
    total_days: list = []
    any_budget = False
    slots_filled = 0
    idx = 0
    calls_attempted = 0

    while slots_filled < days and idx < len(candidates):
        if loop.time() >= deadline:
            break
        remaining_slots = days - slots_filled
        batch = candidates[idx: idx + remaining_slots + 2]
        idx += len(batch)
        batch_results, needed_count = await _collect_batch(batch, deadline)
        calls_attempted += needed_count

        reached_target = False
        for d in batch:
            km_raw, kd_raw = batch_results[d]
            km_budget = isinstance(km_raw, _BudgetExhausted)
            kd_budget = isinstance(kd_raw, _BudgetExhausted)
            km_stats = km_raw if isinstance(km_raw, leaf.DayStats) else None
            kd_stats = kd_raw if isinstance(kd_raw, leaf.DayStats) else None
            status = leaf.classify_day(km_stats, kd_stats)

            if status == leaf.DayStatus.EMPTY:
                if d == d1 and leaf.is_publish_pending(d, d1, now):
                    pending_date = d
                else:
                    empty_list.append(d)
                continue

            slots_filled += 1
            consumed.append(d)
            if status == leaf.DayStatus.MISSING:
                missing_list.append(d)
                if km_budget or kd_budget:
                    any_budget = True
            else:
                total_stats = leaf.merge_stats(km_stats, kd_stats)
                days_list.append({
                    "date": d.isoformat(),
                    "kospi": leaf.stats_to_dict(km_stats),
                    "kosdaq": leaf.stats_to_dict(kd_stats),
                    "total": leaf.stats_to_dict(total_stats),
                })
                kospi_days.append(km_stats)
                kosdaq_days.append(kd_stats)
                total_days.append(total_stats)

            if slots_filled >= days:
                reached_target = True
                break
        if reached_target:
            break

    return {
        "now": now,
        "today": today,
        "limit": limit,
        "days_list": days_list,
        "missing_list": missing_list,
        "empty_list": empty_list,
        "pending_date": pending_date,
        "n_days": len(days_list),
        "complete": len(days_list) == days,
        "window_from": consumed[-1] if consumed else None,
        "window_to": consumed[0] if consumed else None,
        "lookback_from": today - timedelta(days=limit),
        "kospi_days": kospi_days,
        "kosdaq_days": kosdaq_days,
        "total_days": total_days,
        "any_budget": any_budget,
        "slots_filled": slots_filled,
        "calls_attempted": calls_attempted,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 라우트 본문 (계약 2.1 · 명세 §5.5)
# ─────────────────────────────────────────────────────────────────────────────

async def compute_breadth(days: int) -> ApiResponse:
    """라우트 본문 전체 — 설정 확인·창 채우기·캐시·집계·메시지. 실패도 HTTP 200(`success=false`)."""
    start = asyncio.get_running_loop().time()
    try:
        cfg = await system_config.get_krx_open_api_config()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[market_breadth_error] stage=config err=%s", type(exc).__name__)
        return ApiResponse(success=False, data=None, message=MSG_CONFIG_ERR)

    if not cfg.enabled:
        return ApiResponse(success=False, data=None, message=MSG_DISABLED)
    if not cfg.key:
        return ApiResponse(success=False, data=None, message=MSG_NO_KEY)

    try:
        result = await _build_window(days)
    except Exception as exc:  # noqa: BLE001 - 라우트 밖으로 예외를 새지 않게 한다(500 금지)
        logger.warning("[market_breadth_error] stage=unexpected err=%s", type(exc).__name__)
        return ApiResponse(success=False, data=None, message=MSG_UNEXPECTED)

    n_days = result["n_days"]
    missing_list = result["missing_list"]
    slots_filled = result["slots_filled"]
    elapsed_ms = (asyncio.get_running_loop().time() - start) * 1000
    pending_str = result["pending_date"].isoformat() if result["pending_date"] else "-"

    if n_days == 0:
        if missing_list:
            message = MSG_BUDGET if result["any_budget"] else MSG_ALL_FAILED
        else:
            message = f"최근 {result['limit']}일 안에 KRX 자료가 없습니다"
        logger.info(
            "[market_breadth_done] days=%s n_days=0 missing=%s pending=%s calls=%s elapsed_ms=%.0f",
            days, len(missing_list), pending_str, result["calls_attempted"], elapsed_ms,
        )
        return ApiResponse(success=False, data=None, message=message)

    window_from = result["window_from"]
    window_to = result["window_to"]
    n = slots_filled
    if missing_list:
        message = (
            f"최근 {n}영업일 ({window_from.isoformat()}~{window_to.isoformat()}) — "
            f"{len(missing_list)}일은 KRX 응답이 없어 비었습니다"
        )
    else:
        message = f"최근 {n}영업일 ({window_from.isoformat()}~{window_to.isoformat()})"

    data = {
        "asof_kst": result["now"].isoformat(),
        "window": {
            "from": window_from.isoformat(),
            "to": window_to.isoformat(),
            "n_days": n_days,
            "requested": days,
            "complete": result["complete"],
            "lookback_from": result["lookback_from"].isoformat(),
        },
        "days": result["days_list"],
        "summary": {
            "kospi": leaf.stats_to_dict(leaf.summarize(result["kospi_days"])),
            "kosdaq": leaf.stats_to_dict(leaf.summarize(result["kosdaq_days"])),
            "total": leaf.stats_to_dict(leaf.summarize(result["total_days"])),
        },
        "adr_reference": dict(leaf.ADR_REFERENCE),
        "source": SOURCE,
        "missing_dates": [d.isoformat() for d in missing_list],
        "empty_dates": [d.isoformat() for d in result["empty_list"]],
        "pending_date": result["pending_date"].isoformat() if result["pending_date"] else None,
    }
    logger.info(
        "[market_breadth_done] days=%s n_days=%s missing=%s pending=%s calls=%s elapsed_ms=%.0f",
        days, n_days, len(missing_list), pending_str, result["calls_attempted"], elapsed_ms,
    )
    return ApiResponse(success=True, data=data, message=message)


@router.get("/breadth", response_model=ApiResponse)
async def get_breadth(days: int = Query(20, ge=1, le=60)) -> ApiResponse:
    return await compute_breadth(days)
