"""파일 캐시 (raw SQLite) + KST 헬퍼 — macro_lite 패키지 내부 단일 출처.

원본:
- `stock/cache.py` — get_cached / set_cached / delete_cached / delete_prefix / _sanitize
- `db/utils.py` (stock/db_base.py re-export) — KST / now_kst / now_kst_iso
- `stock/macro_store.py` (DB 일일 캐시) — get_today / save_today / delete_today 를
  같은 파일 캐시로 대체 (키 `macro:daily:{category}:{YYYY-MM-DD KST}`, 만료 = 다음날 KST 00:00)

캐시 DB 경로: 환경변수 `MACRO_LITE_CACHE_DIR` (기본 `~/macro-lite/`) + `cache.db`.
환경변수는 **호출 시점**에 읽는다 (테스트 격리: conftest 가 tmp 경로를 setenv).
현재시각은 모두 모듈 전역 `now_kst()` 를 경유한다 (테스트가 monkeypatch).
"""

import json
import logging
import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── KST 타임존 (한국 표준시 UTC+9) ──────────────────────────────────────────
KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """현재 KST 시각 (timezone-aware datetime)."""
    return datetime.now(KST)


def now_kst_iso(timespec: str = "seconds") -> str:
    """현재 KST 시각 ISO 문자열."""
    return now_kst().isoformat(timespec=timespec)


# ── NaN 정제 ─────────────────────────────────────────────────────────────────

def _sanitize(obj):
    """재귀적으로 NaN/Inf를 None으로 변환 (JSON 직렬화 안전 보장)."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


# ── 경로 / 연결 ───────────────────────────────────────────────────────────────

def _cache_dir() -> Path:
    """캐시 디렉토리 — 호출 시점에 환경변수 평가 (모듈 상수 금지)."""
    env = os.getenv("MACRO_LITE_CACHE_DIR")
    return Path(env) if env else Path.home() / "macro-lite"


def _db_path() -> Path:
    return _cache_dir() / "cache.db"


def _conn() -> sqlite3.Connection:
    _cache_dir().mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_db_path(), timeout=10.0)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL,
            expires TEXT NOT NULL
        )
        """
    )
    con.commit()
    return con


# ── TTL 캐시 (stock/cache.py 원본 동일) ──────────────────────────────────────

def get_cached(key: str):
    """캐시 조회. 만료됐거나 없으면 None 반환. NaN 값은 None으로 정제."""
    try:
        with _conn() as con:
            row = con.execute(
                "SELECT value, expires FROM cache WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        value, expires = row
        now = now_kst().replace(tzinfo=None)
        exp = datetime.fromisoformat(expires).replace(tzinfo=None)
        if now > exp:
            return None
        return _sanitize(json.loads(value))
    except Exception as e:
        logger.warning("캐시 읽기 실패 (%s): %s", key, e)
        return None


def set_cached(key: str, value, ttl_hours: float = 24) -> None:
    """데이터를 캐시에 저장. NaN/Inf는 None으로 변환 후 저장."""
    expires = (now_kst() + timedelta(hours=ttl_hours)).isoformat()
    try:
        sanitized = _sanitize(value)
        with _conn() as con:
            con.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires) VALUES (?, ?, ?)",
                (key, json.dumps(sanitized, ensure_ascii=False), expires),
            )
    except Exception as e:
        logger.warning("캐시 쓰기 실패 (%s): %s", key, e)


def delete_cached(key: str) -> None:
    try:
        with _conn() as con:
            con.execute("DELETE FROM cache WHERE key = ?", (key,))
    except Exception as e:
        logger.warning("캐시 삭제 실패 (%s): %s", key, e)


def delete_prefix(prefix: str) -> None:
    """접두사로 시작하는 캐시 키 일괄 삭제."""
    try:
        with _conn() as con:
            con.execute("DELETE FROM cache WHERE key LIKE ?", (f"{prefix}%",))
    except Exception as e:
        logger.warning("캐시 접두사 삭제 실패 (%s): %s", prefix, e)


# ── 당일(KST) 1회 캐시 — 원본 stock/macro_store.get_today/save_today/delete_today 대체 ──
# 원본은 DB(macro_gpt_cache) 에 "당일(KST) 이미 결과가 있으면 재호출하지 않는다" 의미로
# 날짜 키 row 를 저장했다. 여기서는 키에 KST 날짜를 박고 만료를 다음날 KST 00:00 으로
# 계산해 넣어(고정 24h 금지) 같은 의미를 파일 캐시로 구현한다.

def _today_kst() -> str:
    return now_kst().strftime("%Y-%m-%d")


def _daily_key(category: str) -> str:
    return f"macro:daily:{category}:{_today_kst()}"


def _seconds_until_next_kst_midnight() -> float:
    """다음날 KST 00:00 까지 남은 초."""
    now = now_kst()
    next_midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (next_midnight - now).total_seconds()


def get_today(category: str) -> Optional[Any]:
    """당일(KST) 결과 조회. 없으면 None."""
    return get_cached(_daily_key(category))


def save_today(category: str, result) -> None:
    """당일(KST) 결과 저장 (upsert). 만료 = 다음날 KST 00:00."""
    ttl_hours = _seconds_until_next_kst_midnight() / 3600.0
    set_cached(_daily_key(category), result, ttl_hours=ttl_hours)


def delete_today(category: str) -> int:
    """오늘자 캐시 강제 삭제 (외부 키 갱신/장애 복구용). 삭제 건수 반환(0/1)."""
    key = _daily_key(category)
    try:
        with _conn() as con:
            cur = con.execute("DELETE FROM cache WHERE key = ?", (key,))
            return int(cur.rowcount or 0)
    except Exception as e:
        logger.warning("당일 캐시 삭제 실패 (%s): %s", key, e)
        return 0
