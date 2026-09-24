"""strategy_funnel_snapshots CRUD — 조건검색 단계별 후보 영구 추적 (사이클 34, 2026-05-21).

배경:
- 사용자 5/21 15:26 funnel 결함 (donchian 111→0 / BFB 30→0 / VCP 113→0) 시 단계별 살아남은
  종목 + 탈락 사유를 알 수 없어 디버깅 곤란.

본 모듈:
- `insert_snapshot(target_date, strategy_id, step_no, step_name, ...)` — 단일 단계 1행 UPSERT
  + JSONB cap 자동 적용 (survived 200 / excluded 20)
- `list_snapshots(target_date, strategy_id=None)` — 단일 영업일 모든 단계 조회 (step_no ASC)
- `list_recent_by_strategy(strategy_id, days=7)` — 추이 분석용 (target_date DESC)

자금 안전: 본 모듈은 진단/추적 전용. 매매 동작 영향 0.

사이클 M1-3 (Supabase→RDS 이전 단계1 증분3, M1 마무리): supabase-py → `src.db.pg`
(asyncpg) 전환. 함수 시그니처·반환형·graceful 100% 보존 → 호출부(scheduler
`capture_funnel_snapshots` / 라우트 `POST /api/strategy-funnel/snapshot`) diff 0.
JSONB(`survived_tickers`/`excluded_sample`) 는 `$N::jsonb` + `json.dumps` 바인딩.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import src.db.pg as pg
from src.db._kst import to_date

logger = logging.getLogger(__name__)

TABLE_NAME = "strategy_funnel_snapshots"

# JSONB cap (응답 크기 + 저장 크기 보호)
SURVIVED_TICKERS_CAP = 200
EXCLUDED_SAMPLE_CAP = 20

# KST 영업일 비교용
_KST_TZ = timezone(timedelta(hours=9))


async def insert_snapshot(
    *,
    target_date: date,
    strategy_id: str,
    step_no: int,
    step_name: str,
    survived_tickers: list | None = None,  # list[str | dict] 모두 허용 (사이클 41)
    excluded_sample: list[dict[str, Any]] | None = None,
    survived_count: int | None = None,
    excluded_count: int = 0,
    step_conditions: str | None = None,  # 사이클 41 — 단계 조건 (UI 툴팁)
    is_provisional: bool = False,  # 사이클 171 — 저녁 16:20 잠정 캡처 플래그
) -> dict | None:
    """1단계 snapshot UPSERT (사이클 145 — UPSERT 전환 영구 영속).

    Args:
        target_date: 영업일 (KST).
        strategy_id: 전략 ID (donchian_swing / bull_flag_breakout / vcp_breakout / momentum / ...).
        step_no: 단계 번호 (1, 2, 3, ...).
        step_name: 단계 이름 (UI 명세와 정확히 일치).
        survived_tickers: 단계 통과 종목 리스트.
            - 사이클 34: list[str] (`["005930", ...]`).
            - 사이클 41 (2026-05-22): list[dict] (`[{"ticker": "...", "name": "..."}]`) 도 허용.
            JSONB cap 200 자동 적용. 하위 호환 — DB 응답 시 호출자가 형식 분기 처리.
        excluded_sample: 탈락 종목 sample.
            - 사이클 34: `[{"ticker": str, "reason": str}, ...]`.
            - 사이클 41: `[{"ticker": str, "name": str, "reason": str}, ...]` 권장 (종목명 추가).
            cap 20 자동 적용.
        survived_count: 통과 카운트 (None 이면 len(survived_tickers) 사용).
        excluded_count: 탈락 카운트.
        step_conditions: 단계 필터 조건 (UI 툴팁용, 사이클 41). DB 저장 안 함 (API 응답만).
        is_provisional: 잠정 캡처 여부 (사이클 171, migration 040).
            - True = 16:20 저녁 잠정 캡처 (전일 마스터 + 16:10 basics 기준, 아침 델타 미반영).
            - False (기본) = 09:30 자동 / 수동 trigger (확정). 기존 호출자 회귀 0.

    Returns:
        upsert 된 row dict (id 포함) 또는 None (실패 시).

    Note:
        사이클 145 (2026-06-16) — UPSERT 전환 영구 영속 (결함 3 시정).
        - 사이클 34 시점 = `.insert(row)` + UNIQUE `(target_date, strategy_id, step_no, snapshot_at)`
          → snapshot_at 매번 갱신 → 중복 INSERT 가능 → 운영 DB 영역 영구 영속 6/15 BFB step_no=1 = 8 row 결함.
        - 사이클 145 시정 = `.upsert(on_conflict="target_date,strategy_id,step_no")` 전환
          + migration 035 영역 영구 영속 UNIQUE 변경 (snapshot_at 키 폐기).
        - 같은 (target_date, strategy_id, step_no) 영역 영구 영속 = 최신 값 영구 영속 1 row.
        - snapshot_at = 마지막 쓰기 시각(DB `now()`). 첫 INSERT 는 컬럼 기본값
          `now()`(migration 030), 이후 덮어쓸 때마다 `DO UPDATE SET` 이 같은 DB
          시계로 갱신한다.
        - 매매 안전성 무영향 (진단/추적 영역 한정).
    """
    if not strategy_id:
        raise ValueError("strategy_id 필수")

    survived = list(survived_tickers or [])[:SURVIVED_TICKERS_CAP]
    excluded = list(excluded_sample or [])[:EXCLUDED_SAMPLE_CAP]

    if survived_count is None:
        survived_count = len(survived)

    row_id = str(uuid.uuid4())

    # M6 — target_date DATE 컬럼 바인딩. 호출자가 str(예: `.isoformat()` 오적용)을
    # 넘겨도 asyncpg 가 요구하는 date 객체로 강제 변환 (str 그대로면 즉시 예외).
    bound_target_date = to_date(target_date)

    try:
        result = await pg.fetchrow(
            f"""
            INSERT INTO {TABLE_NAME} (
                id, target_date, strategy_id, step_no, step_name,
                survived_count, excluded_count, survived_tickers, excluded_sample,
                is_provisional
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10)
            ON CONFLICT (target_date, strategy_id, step_no) DO UPDATE SET
                step_name = EXCLUDED.step_name,
                survived_count = EXCLUDED.survived_count,
                excluded_count = EXCLUDED.excluded_count,
                survived_tickers = EXCLUDED.survived_tickers,
                excluded_sample = EXCLUDED.excluded_sample,
                is_provisional = EXCLUDED.is_provisional,
                snapshot_at = now()
            RETURNING *
            """,
            row_id,
            bound_target_date,
            strategy_id,
            int(step_no),
            step_name,
            int(survived_count),
            int(excluded_count),
            survived,
            excluded,
            bool(is_provisional),
        )
        return result
    except Exception as exc:
        logger.warning(
            "strategy_funnel upsert 실패 — target=%s strategy=%s step=%d err=%s",
            target_date, strategy_id, step_no, exc,
        )
        return None


async def list_snapshots(
    *,
    target_date: date,
    strategy_id: str | None = None,
) -> list[dict]:
    """단일 영업일 snapshot 조회 (step_no ASC).

    Args:
        target_date: 영업일.
        strategy_id: 단일 전략 필터 (None 이면 전체).

    Returns:
        snapshot row list. 응답 cap 없음 (전략당 단계 수 ≤ 10 가정).
    """
    bound_target_date = to_date(target_date)
    try:
        if strategy_id:
            rows = await pg.fetch(
                f"""
                SELECT * FROM {TABLE_NAME}
                WHERE target_date = $1 AND strategy_id = $2
                ORDER BY step_no
                """,
                bound_target_date,
                strategy_id,
            )
        else:
            rows = await pg.fetch(
                f"""
                SELECT * FROM {TABLE_NAME}
                WHERE target_date = $1
                ORDER BY step_no
                """,
                bound_target_date,
            )
        return rows or []
    except Exception as exc:
        logger.warning(
            "strategy_funnel list 실패 — target=%s strategy=%s err=%s",
            target_date, strategy_id, exc,
        )
        return []


async def list_recent_by_strategy(
    strategy_id: str,
    days: int = 7,
) -> list[dict]:
    """특정 전략의 최근 N일 snapshot 추이 조회 (target_date DESC).

    Args:
        strategy_id: 전략 ID.
        days: 최근 N일 (기본 7).

    Returns:
        snapshot row list — target_date DESC, step_no ASC.
    """
    if days <= 0:
        return []

    today_kst = datetime.now(_KST_TZ).date()
    from_date = today_kst - timedelta(days=days - 1)

    try:
        rows = await pg.fetch(
            f"""
            SELECT * FROM {TABLE_NAME}
            WHERE strategy_id = $1 AND target_date >= $2 AND target_date <= $3
            ORDER BY target_date DESC, step_no
            """,
            strategy_id,
            from_date,
            today_kst,
        )
        return rows or []
    except Exception as exc:
        logger.warning(
            "strategy_funnel recent 실패 — strategy=%s err=%s",
            strategy_id, exc,
        )
        return []
