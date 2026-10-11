"""cycle446 — 청산 AI 섀도 기록(`llm_worker`)의 구조 가드. 설계 §8.1 「매매 경로 소비처는
구조적으로 0」 — `src/engine/` 과 8영역(+같은 승인 대상 `scheduler.py`)에 `exit_ai_` 접두
언급이 0 이어야 한다. `src/db/`·`src/routes/`·프론트의 읽기 경로는 이 가드 밖이다
(설계 §8.2 「매매에는 쓰지 않는다」 를 코드 규칙으로 박는다).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

# 8영역 + scheduler.py(cycle257 영구 라인 상한 — 같은 승인 대상). 이 가드는 "쓰지 않는다"
# 사실만 확인하므로 8영역 목록 자체를 import 하지 않고 여기 다시 적는다(다른 가드의
# `_APPROVED_CONTENT_SHA` 승인 메커니즘과 무관 — 이 테스트는 sha 핀이 아니다).
_SCAN_TARGETS = [
    "src/engine",  # strategy 7파일 포함 — scheduler.py 도 이 안에 있다
    "src/api/order.py",
    "src/realtime",
    "src/auth",
]

_NEEDLE = re.compile(r"exit_ai_")


def _iter_py_files():
    for rel in _SCAN_TARGETS:
        p = _ROOT / rel
        if p.is_file():
            yield p
        elif p.is_dir():
            yield from sorted(p.rglob("*.py"))


def test_exit_ai_prefix_absent_from_engine_and_eight_areas():
    hits = []
    for p in _iter_py_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        if _NEEDLE.search(text):
            hits.append(p.relative_to(_ROOT).as_posix())
    assert hits == [], f"매매 경로에 exit_ai_* 언급이 있다(설계 §8.1 위반): {hits}"


def test_exit_ai_tables_exist_only_in_allowed_areas():
    """반대 방향 — 가드 자체가 아무것도 안 걸리는 공허한 참이 아님을 확인한다(양성 대조군)."""
    allowed = [
        _ROOT / "supabase" / "migrations" / "050_exit_ai_evaluations.sql",
        _ROOT / "llm_worker" / "ops" / "role.sql",
    ]
    assert any("exit_ai_evaluations" in p.read_text(encoding="utf-8") for p in allowed if p.is_file())
