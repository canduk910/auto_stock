r"""사이클 M5 (Red) — 전수 가드 (HIGH): src/ 전체 supabase 직접 접근 0건 (supabase.py 자신 제외).

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (Supabase→RDS 이전, 누락 사이트).

M0~M3 가 17 db 모듈을 pg(asyncpg) 로 전환했으나, src/db/ **밖** 4파일이 여전히
`from src.db.supabase import supabase` / `supabase.table()` 로 Supabase 를 직접 읽고/써서 RDS 와
split-brain. M5 전환 후:

**전수 불변식 (컷오버 완료 판정)**:
  grep -rE "from src\.db\.supabase import|supabase\.(table|rpc)\(" src/ | grep -v src/db/supabase.py
  = 0건

= 이전의 진짜 마지막. 완료 시 src/ 전체 supabase 참조 0 (supabase.py 자신 제외).

추가: 매매 안전성 8영역 diff 0 (이 4파일은 8영역 밖).

Red 유효성: production 미변경 → 4파일 13 사이트 잔존 → 위반 리스트 non-empty → FAIL.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_SRC = _REPO / "src"
_SUPABASE_SELF = "src/db/supabase.py"

# 계획 명세 전수 가드 정규식 (import + table()/rpc() 호출)
_IMPORT_RE = re.compile(r"from\s+src\.db\.supabase\s+import")
_CALL_RE = re.compile(r"supabase\.(table|rpc)\(")


def _rel(p: Path) -> str:
    return str(p.relative_to(_REPO)).replace("\\", "/")


def _scan_violations() -> list[str]:
    """src/ 전체 (supabase.py 제외) 에서 supabase import / table()/rpc() 호출 사이트 목록."""
    hits: list[str] = []
    for py in _SRC.rglob("*.py"):
        rel = _rel(py)
        if rel == _SUPABASE_SELF:
            continue
        try:
            body = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(body.splitlines(), start=1):
            if _IMPORT_RE.search(line) or _CALL_RE.search(line):
                hits.append(f"{rel}:{i}: {line.strip()}")
    return hits


# ---------------------------------------------------------------------------
# 전수 가드 (HIGH) — src/ 전체 supabase 직접 접근 0건
# ---------------------------------------------------------------------------
def test_no_supabase_import_or_call_outside_db_module():
    """src/ 전체 (supabase.py 자신 제외) supabase 직접 접근 0건 — 이전 완료 판정."""
    violations = _scan_violations()
    assert not violations, (
        "src/ 전체에서 supabase 직접 import / table()/rpc() 호출 0건이어야 함 "
        "(supabase.py 자신 제외). RDS 전환 미완료 잔존 사이트 (split-brain):\n  "
        + "\n  ".join(violations)
    )


def test_sweep_regex_self_test():
    """탐지기 self-test — 정규식이 대표 패턴을 실제로 잡는지 검증 (false-negative 차단)."""
    assert _IMPORT_RE.search("from src.db.supabase import supabase")
    assert _IMPORT_RE.search("from src.db.supabase import supabase as _sb")
    assert _CALL_RE.search('supabase.table("system_config").select("value")')
    assert _CALL_RE.search("supabase.rpc('recompute_daily_performance')")
    # 무관 패턴은 매칭 안 함
    assert not _IMPORT_RE.search("import src.db.pg as pg")
    assert not _CALL_RE.search("pg.fetch(sql)")


def test_supabase_self_still_present():
    """supabase.py 자신은 병존(롤백 경로) 유지 — 삭제 금지."""
    assert (_SRC / "db" / "supabase.py").exists(), (
        "supabase.py 병존(롤백 경로) 유지 — M5 는 마지막 전환이나 supabase.py 삭제 금지."
    )


