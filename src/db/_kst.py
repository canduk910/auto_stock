"""사이클 68 = KST 공용 헬퍼 (결정 2-B).

사이클 65 hotfix H2/H2-bis 답습.
모든 DB INSERT/UPSERT 모듈은 본 헬퍼 경유 의무.

정책 원칙 (CLAUDE.md 절대 규칙):
- 모든 시각 데이터 KST 강제 — +09:00 suffix 포함 ISO 8601 문자열 의무.
- DB INSERT payload 에 UTC 명시 사용 금지.
- 향후 silent 결함 차단: 본 헬퍼 미사용 = G-10b AST 가드 FAIL.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def now_kst_iso() -> str:
    """현재 KST 시각 ISO 문자열 (+09:00 suffix 포함).

    DB INSERT/UPSERT payload 의 시각 컬럼 (`created_at` / `updated_at` /
    `refreshed_at` / `completed_at` / `timestamp` 등) 에 사용.

    사이클 65 H2 답습 — `datetime.now(KST).isoformat()` 인라인 반복 폐기.
    """
    return datetime.now(KST).isoformat()


def today_kst() -> date:
    """현재 KST 날짜 (서버 timezone 의존 회피, Q1 LOW).

    서버 timezone 의존 → KST 영업일 어긋남 위험 차단.
    G-12 AST 가드 준수.
    """
    return datetime.now(KST).date()
