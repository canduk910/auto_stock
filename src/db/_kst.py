"""사이클 68 = KST 공용 헬퍼 (결정 2-B).

사이클 65 hotfix H2/H2-bis 답습.
모든 DB INSERT/UPSERT 모듈은 본 헬퍼 경유 의무.

정책 원칙 (CLAUDE.md 절대 규칙):
- 모든 시각 데이터 KST 강제 — +09:00 suffix 포함 ISO 8601 문자열 의무.
- DB INSERT payload 에 UTC 명시 사용 금지.
- 향후 silent 결함 차단: 본 헬퍼 미사용 = G-10b AST 가드 FAIL.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

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


def to_date(x: date | datetime | str | None) -> date | None:
    """DATE 컬럼 바인딩 값을 `date` 객체로 강제 변환한다 (M6 라이브 핫픽스).

    배경: asyncpg 는 DATE 컬럼에 Python `date` 객체를 요구한다 — `str` 을 넘기면
    ``invalid input for query argument $N: '...' ('str' object has no attribute
    'toordinal')`` 로 즉시 실패한다. `src/db/strategy_funnel.py::insert_snapshot`
    이 (scanner.py 의 `datetime.now(KST_TZ).date().isoformat()` 호출부에서) 문자열을
    받아 이 실패를 겪었다 — try/except graceful 이 삼켜 조용히 저장 누락됐다.

    변환 규칙 (우선순위):
    - `date` (또는 `datetime`, `date` 의 서브클래스) — `datetime` 이면 `.date()`,
      순수 `date` 면 그대로 반환.
    - `str` — `YYYY-MM-DD` (`date.fromisoformat`) 우선 시도, 실패 시 앞 10자를
      슬라이스하여 재시도 (`"2026-07-17T09:30:00+09:00"` 같은 타임스탬프 ISO 문자열
      호환 — `bas_dd`/`target_date` 가 다른 ISO 포맷 문자열로 도달하는 경로 방어).
    - `None` — `None` 그대로 (호출자 graceful 분기 보존, 예: `max_bas_dd` 미존재).
    - 그 외 파싱 실패 — `None` 반환 + `logger.warning` (상위 try/except 가 이미
      graceful 이므로 raise 하지 않는다 — 이중 방어보다 단일 경고가 낫다).

    본 헬퍼는 값 하나만 변환한다. **바인딩 지점 전체를 감싸는 것은 호출자 책임**
    (각 DB 모듈이 `to_date(target_date)` 로 감싸 date/str 양쪽 입력을 수용).
    """
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    if isinstance(x, str):
        try:
            return date.fromisoformat(x)
        except ValueError:
            pass
        try:
            return date.fromisoformat(x[:10])
        except (ValueError, TypeError):
            pass
        logger.warning("[to_date] 파싱 실패 — 원본 문자열 형식 불일치: %r", x)
        return None
    logger.warning("[to_date] 지원하지 않는 타입 — %r (%s)", x, type(x).__name__)
    return None
