"""ndx2x_riskoff 이력 적재 — KIS FHKST03030100 → `overseas_index_daily` (cycle443).

겹침 widening-fetch 로 「요청 시작일 근처 며칠이 빠진다」 실측 quirk 를 상쇄한다
(자문 `_workspace/domain_consult/2026-10-06_ndx2x_risk_off.md` §3 「신호 원천」) —
매 반복의 **종료일 커서를 이전 반복에서 받은 최저 날짜로 당겨** 다시 요청한다.
그 최저 날짜는 이전 응답에 실제로 존재했던 날이므로(그 응답의 "끝" 쪽), 이번 응답의
"시작 근처 누락"은 그 날짜 **보다 더 과거**에서 일어나고 다음 반복이 또 같은 방식으로
겹쳐 메운다 — 메우는 로직 자체는 순수 함수(`ndx2x_core.merge_batches`)에 있다.

호출자(ndx2x_riskoff 전략)가 **미국 종가 확정 뒤(KST 07:00 이후)** 에만 불러야 한다 —
이 모듈은 시각을 판단하지 않는다. KIS 접속 없이 이 모듈만 테스트하려면 `fetch_daily_chartprice`
를 모듈 네임스페이스에서 monkeypatch 한다(다른 `src/api/*` 소비 모듈과 같은 패턴).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from src.api.overseas_quote import NDX_ISCD, OverseasIndexEmptyResponseError, fetch_daily_chartprice
from src.db import overseas_index as db
from src.engine.ndx2x_core import MIN_HISTORY_DAYS, merge_batches, parse_kis_rows

logger = logging.getLogger(__name__)

#: `overseas_index_daily.index_code` — 지금은 나스닥100 하나.
NDX_INDEX_CODE = "NDX"
#: 한 창의 달력일 폭 — 주말·공휴일을 감안해 100거래일 캡을 넉넉히 담는 여유.
_WINDOW_CALENDAR_DAYS = 160
#: widening 반복 상한 — 무한루프 방지. 도달 실패는 WARNING + 있는 만큼 저장(fail-open 적재,
#: 판단은 `ndx2x_core.decide_daily` 의 `insufficient_history` fail-closed 가 맡는다).
_MAX_FETCH_ATTEMPTS = 6


def _to_date(bsop: str) -> date:
    return datetime.strptime(bsop, "%Y%m%d").date()


@dataclass(frozen=True)
class IngestResult:
    rows_upserted: int
    total_history_days: int
    latest_date: str | None
    reached_target: bool


async def ensure_history(
    *, target_days: int = MIN_HISTORY_DAYS + 50, today: date | None = None,
) -> IngestResult:
    """DB 이력을 `target_days` 영업일 이상 채우고(최초 1회 backfill) 오늘까지 증분한다.

    이미 최신(오늘 또는 전날까지 저장)이고 이력이 충분하면 KIS 호출 0회.
    """
    today = today or date.today()
    latest = await db.get_latest_date(NDX_INDEX_CODE)
    existing = await db.get_recent_closes(NDX_INDEX_CODE, limit=target_days + 50)
    if (
        latest is not None
        and latest >= today - timedelta(days=1)
        and len(existing) >= target_days
    ):
        return IngestResult(0, len(existing), latest.isoformat(), True)

    existing_batch = [(d.strftime("%Y%m%d"), c) for d, c in existing]
    fetched_batches: list[list[tuple[str, float]]] = []
    raw_by_date: dict[str, dict] = {}
    collected_dates: set[str] = {d for d, _ in existing_batch}
    cursor_end = today
    attempts = 0

    while attempts < _MAX_FETCH_ATTEMPTS and len(collected_dates) < target_days:
        attempts += 1
        cursor_start = cursor_end - timedelta(days=_WINDOW_CALENDAR_DAYS)
        try:
            rows = await fetch_daily_chartprice(cursor_start, cursor_end, iscd=NDX_ISCD)
        except OverseasIndexEmptyResponseError:
            logger.error(
                "[ndx2x_ingest_empty] start=%s end=%s — output2 0행(FID_INPUT_ISCD 재확인)",
                cursor_start, cursor_end,
            )
            break
        parsed = parse_kis_rows(rows)
        if not parsed:
            break
        for d, _ in parsed:
            raw_by_date.setdefault(d, next(r for r in rows if r.get("stck_bsop_date") == d))
        fetched_batches.append(parsed)
        collected_dates.update(d for d, _ in parsed)

        oldest = min(d for d, _ in parsed)
        next_cursor_end = _to_date(oldest)
        if next_cursor_end >= cursor_end:
            break  # 진전 없음(KIS 가 더 과거를 안 준다) — 안전 종료
        cursor_end = next_cursor_end

    # 병합 우선순위: 새로 받은 배치(최근 구간 먼저) > DB 기존값(mod_yn 수정 반영 — 자문 §3).
    merged = merge_batches([*fetched_batches, existing_batch])
    upserted = await db.upsert_many(NDX_INDEX_CODE, merged, raw_by_date=raw_by_date)
    reached = len(merged) >= target_days
    if not reached:
        logger.warning(
            "[ndx2x_ingest_short] target=%d got=%d attempts=%d — 이력 부족, "
            "decide_daily 가 fail-closed(매매 없음) 로 받는다",
            target_days, len(merged), attempts,
        )
    latest_str = merged[-1][0] if merged else (latest.strftime("%Y%m%d") if latest else None)
    return IngestResult(upserted, len(merged), latest_str, reached)
