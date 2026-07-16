"""사이클 M0 (Red) — config.database_url + 매매 안전성 8영역 diff 0 + db 모듈 미변경.

이 단계 = 순수 추가 (pg.py 신규 + config/env/lifespan/requirements 배선). 어느 db 모듈도
pg 미사용 = 행위 변화 0. supabase.py 병존.

가드:
- config.database_url 존재 (Settings 필드) — asyncpg DSN. → Red FAIL (미존재).
- lifespan 배선 (init_pool/close_pool) — src/main.py 텍스트에 함수명 등장. → Red FAIL.
- requirements.txt 에 asyncpg. → Red FAIL.
- 매매 안전성 8영역 diff 0 (git working tree) — 불변식 PASS.
- 어느 db 모듈도(supabase.py 포함) 미변경 (git) — 불변식 PASS.

Red 유효성: config.database_url 미존재 + main.py 배선 미존재 + requirements asyncpg 미존재 → FAIL.
Green 후 PASS.
"""

from __future__ import annotations

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
    """working tree + staged 변경 파일 목록 (repo 상대 경로)."""
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
        # porcelain: XY <path> (또는 rename ' -> ')
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path)
    return files


# ---------------------------------------------------------------------------
# config.database_url 존재 (asyncpg DSN)
# ---------------------------------------------------------------------------
def test_config_has_database_url():
    """Settings 에 database_url 필드 (postgresql://... DSN). supabase_url/key 병존."""
    from src.config import settings

    assert hasattr(settings, "database_url"), (
        "settings.database_url 미존재 — asyncpg create_pool(dsn=...) 소스 (신규 의무)."
    )
    # 병존 검증 — supabase 설정 삭제 금지 (롤백 경로 보존)
    assert hasattr(settings, "supabase_url"), "supabase_url 삭제 금지 (병존, M0 롤백 경로)."
    assert hasattr(settings, "supabase_key"), "supabase_key 삭제 금지 (병존)."


# ---------------------------------------------------------------------------
# lifespan 배선 — init_pool / close_pool
# ---------------------------------------------------------------------------
def test_main_lifespan_wires_pool():
    """src/main.py 가 init_pool / close_pool 을 배선 (텍스트 등장 = 배선 존재)."""
    main_src = (_REPO / "src" / "main.py").read_text(encoding="utf-8")
    assert "init_pool" in main_src, (
        "src/main.py lifespan 에 init_pool 배선 미존재 (풀 시작)."
    )
    assert "close_pool" in main_src, (
        "src/main.py lifespan 에 close_pool 배선 미존재 (풀 종료)."
    )


# ---------------------------------------------------------------------------
# requirements.txt 에 asyncpg
# ---------------------------------------------------------------------------
def test_requirements_has_asyncpg():
    """requirements.txt 에 asyncpg 의존성 추가."""
    req = (_REPO / "requirements.txt").read_text(encoding="utf-8")
    assert "asyncpg" in req.lower(), "requirements.txt 에 asyncpg 미추가."


# ---------------------------------------------------------------------------
# .env.example 에 DATABASE_URL
# ---------------------------------------------------------------------------
def test_env_example_has_database_url():
    """.env.example 에 DATABASE_URL 항목 추가."""
    env = (_REPO / ".env.example").read_text(encoding="utf-8")
    assert "DATABASE_URL" in env, ".env.example 에 DATABASE_URL 미추가."


# ---------------------------------------------------------------------------
# 매매 안전성 8영역 diff 0 (불변식)
# ---------------------------------------------------------------------------
def test_safety_8_areas_unchanged():
    """M0 는 순수 추가 → 매매 안전성 8영역 git diff 0. 불변식 PASS."""
    changed = _git_changed_files()
    violations = [
        f for f in changed
        if any(f == p or f.startswith(p) for p in _SAFETY_PATHS)
    ]
    assert not violations, (
        "M0 는 매매 안전성 8영역 diff 0 이어야 함 (행위 변화 0). 변경 감지:\n  "
        + "\n  ".join(violations)
    )


# ---------------------------------------------------------------------------
# 어느 db 모듈도(supabase.py 포함) 미변경 (불변식)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    reason=(
        "사이클 M1-1 의미 전환 — 이 불변식은 'M0 단계(순수 추가)' 한정 스냅샷 가드다. "
        "M1-1 이 계획대로 positions.py/strategy_config.py 를 pg.* 로 전환하면서 "
        "working tree 에 db 모듈 변경이 발생 — 이는 M0 범위 밖의 정상 진행이며 회귀가 "
        "아니다(docstring: '이 단계 = 순수 추가'). git status 기반 실시간 스냅샷이라 "
        "M0 완료 이후에는 항상 FAIL 하도록 설계되어 있어 xfail 로 은퇴시킨다."
    ),
    strict=False,
)
def test_no_existing_db_module_changed():
    """M0 = pg.py 신규만. 기존 src/db/ 모듈(supabase.py 포함) diff 0.

    pg.py 는 신규 파일(untracked)이라 '변경' 아님 — 기존 tracked db 모듈이 변경되면 위반.
    """
    changed = _git_changed_files()
    db_changed = [
        f for f in changed
        if f.startswith("src/db/") and not f.endswith("/pg.py")
    ]
    # untracked 신규 파일(pg.py)은 '??' 상태라 porcelain 에 잡히나 basename 필터로 제외.
    # 기존 모듈 수정(' M src/db/xxx.py')만 위반.
    assert not db_changed, (
        "M0 는 기존 db 모듈(supabase.py 포함) 미변경 이어야 함 (순수 추가):\n  "
        + "\n  ".join(db_changed)
    )
