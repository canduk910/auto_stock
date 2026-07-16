"""사이클 M3b (Red) — 매매 안전성 8영역 diff 0 + main.py seam-only 불변식.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 3 — 분석·관찰 + main seam).

M3b = system_logs.py 를 pg.* 로 전환 + main.py seam 2곳(`_DbLogHandler` + lifespan auto_start).
system_logs 는 관찰성 척추 = 매매 안전성 8영역 밖(src/db/). main.py 도 8영역 밖이나 seam 2곳만 변경.

이 파일 = 불변식 가드:
- 매매 안전성 8영역 git diff 0 (system_logs / main.py 모두 8영역 밖).
- system_logs 함수 계약(시그니처) 보존 → 72곳 호출부 diff 0.
- main.py 는 seam 2곳만 변경 — 다른 lifespan/미들웨어/라우터 배선 불변.

Red 단계: 대부분 불변식 PASS (전환은 db 모듈 내부 + main seam 교체). M3b 가 8영역을 건드리면
즉시 FAIL. system_logs 함수 심볼이 사라지면 FAIL.
"""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]

# 매매 안전성 8영역 (CLAUDE.md 명문화)
_SAFETY_PATHS = (
    "src/engine/risk.py",
    "src/engine/order_engine.py",
    "src/realtime/",
    "src/auth/",
    "src/api/order.py",
    "src/engine/session.py",
    "src/engine/scanner.py",
    "src/engine/strategy_registry.py",
)


def _git_changed_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(_REPO), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path)
    return files


# ---------------------------------------------------------------------------
# 매매 안전성 8영역 diff 0 (불변식)
# ---------------------------------------------------------------------------
def test_safety_8_areas_unchanged():
    """M3b 는 system_logs.py + main.py seam 전환 → 8영역 git diff 0."""
    changed = _git_changed_files()
    violations = [
        f for f in changed
        if any(f == p or f.startswith(p) for p in _SAFETY_PATHS)
    ]
    assert not violations, (
        "M3b 는 매매 안전성 8영역 diff 0 이어야 함 (함수 계약 보존 → 호출부 무변경). 변경 감지:\n  "
        + "\n  ".join(violations)
    )


# ---------------------------------------------------------------------------
# system_logs 함수 계약 시그니처 보존 (72곳 호출 계약)
# ---------------------------------------------------------------------------
def test_system_logs_functions_exist():
    """system_logs 계약 함수 심볼 보존."""
    from src.db import system_logs as sl

    for fn in (
        "write_log",
        "safe_write_log",
        "get_logs",
        "search_logs",
        "purge_old_logs",
        "_purge_by_cutoff",
    ):
        assert hasattr(sl, fn), f"{fn} 심볼 삭제 금지 (관찰성 척추 계약)."


def test_write_log_signature_preserved():
    """write_log(log_level, message) → None 시그니처 불변 (72곳 호출)."""
    from src.db import system_logs as sl

    params = list(inspect.signature(sl.write_log).parameters)
    assert params == ["log_level", "message"], f"write_log 시그니처 변경 금지: {params}"


def test_system_logs_constants_preserved():
    """retention/purge 상수 보존 (사이클175)."""
    from src.db import system_logs as sl

    assert sl.INFO_RETENTION_DAYS == 2
    assert sl.HIGH_RETENTION_DAYS == 30
    assert sl.HIGH_LEVELS == ("WARNING", "ERROR", "CRITICAL")
    assert sl.MAX_PURGE_BATCH == 100_000
    assert sl.PURGE_SELECT_BATCH == 1000
    assert sl.PURGE_MAX_ITERATIONS == 2000


# ---------------------------------------------------------------------------
# main.py seam-only — 다른 lifespan/미들웨어/라우터 배선 불변
# ---------------------------------------------------------------------------
def test_main_routers_and_middleware_preserved():
    """main.py seam 2곳만 변경 — 라우터 배선/미들웨어/health 불변."""
    body = (_REPO / "src" / "main.py").read_text(encoding="utf-8")

    # 미들웨어 배선 불변
    assert "MetricsMiddleware" in body, "MetricsMiddleware 불변."
    assert "CORSMiddleware" in body, "CORSMiddleware 불변."
    # 대표 라우터 배선 불변 (전수 포함 여부 대신 대표 샘플)
    for router in ("trading.router", "logs.router", "stock_master_router"):
        assert router in body, f"{router} 배선 불변."
    # health 엔드포인트 불변
    assert '"/health"' in body or "'/health'" in body, "health 엔드포인트 불변."
    # 로깅 기반 인프라 불변 (파일 핸들러 등)
    assert "_KSTFormatter" in body, "_KSTFormatter 불변."
    assert "TimedRotatingFileHandler" in body, "파일 핸들러 불변."


def test_main_db_log_handler_and_lifespan_still_present():
    """seam 대상 심볼 자체는 존재 (제거가 아니라 전환)."""
    body = (_REPO / "src" / "main.py").read_text(encoding="utf-8")

    assert "_DbLogHandler" in body, "_DbLogHandler 는 전환(큐)이지 제거 아님."
    assert "async def lifespan" in body, "lifespan 은 seam 제거이지 함수 제거 아님."


# ---------------------------------------------------------------------------
# supabase.py 병존 유지 (롤백 경로) — M3b 는 마지막 db 모듈이나 supabase.py 삭제 금지
# ---------------------------------------------------------------------------
def test_supabase_module_still_present_for_rollback():
    """이게 마지막 db 모듈 전환이나 supabase.py 는 병존(롤백용) 유지 — 삭제 금지."""
    supa = _REPO / "src" / "db" / "supabase.py"
    assert supa.exists(), (
        "supabase.py 병존(롤백 경로) 유지 의무 — M3b 는 마지막 db 모듈이나 삭제 금지 "
        "(라이브 vts 검증 며칠 후 별도 사이클에서 제거)."
    )
