"""사이클 129 AST 영구 가드 — refresh_progress TaskKey "master" 영구 영속.

배경:
- 사이클 127 refresh_progress.py L34 Literal + L37 tuple 2 위치 동행 영속 패턴 확장
- 미래 silent 결함 영구 차단 (예: L34 만 추가 + L37 누락 → KeyError 영구 영속)

회귀 가드 2 케이스:
- G-AST-TK1: refresh_progress.py Literal "master" 포함 영속
- G-AST-TK2: refresh_progress.py TASK_KEYS tuple "master" 포함 영속 (2 위치 동행)
"""
from __future__ import annotations

from pathlib import Path

_PROGRESS_SRC = (
    Path(__file__).resolve().parents[3] / "src/engine/refresh_progress.py"
)


# 사이클 136 (2026-06-15) — 카드 #25 AST DRY 헬퍼 모듈 영역 영구 영속 마이그레이션.
from tests.unit.ast._ast_helpers import read_module_source


def _read() -> str:
    return read_module_source(_PROGRESS_SRC)


def test_g_ast_tk1_literal_master_present():
    """G-AST-TK1: TaskKey Literal 영역 "master" 포함 영속.

    사이클 127 L34 패턴 답습 — Literal["universe", "basics", "daily", "master"].
    """
    src = _read()
    # Literal 영역에 "master" 포함 영속
    assert 'TaskKey = Literal[' in src, (
        "G-AST-TK1: TaskKey Literal 정의 영역 부재"
    )

    # TaskKey Literal 라인 추출 → "master" 포함 영속
    for line in src.splitlines():
        if line.strip().startswith("TaskKey = Literal["):
            assert '"master"' in line, (
                f"G-AST-TK1: TaskKey Literal 'master' 영역 부재 (line={line!r})"
            )
            break
    else:
        raise AssertionError("G-AST-TK1: TaskKey Literal 영역 파싱 실패")


def test_g_ast_tk2_task_keys_tuple_master_present():
    """G-AST-TK2: TASK_KEYS tuple 영역 "master" 포함 영속.

    사이클 127 L37 패턴 답습 — TASK_KEYS = ("universe", "basics", "daily", "master").
    Literal + tuple 2 위치 동행 의무 영구 영속.
    """
    src = _read()
    assert "TASK_KEYS:" in src or "TASK_KEYS =" in src, (
        "G-AST-TK2: TASK_KEYS 정의 영역 부재"
    )

    # TASK_KEYS = (...) 라인 추출 → "master" 포함 영속
    found = False
    for line in src.splitlines():
        if "TASK_KEYS" in line and "(" in line and ")" in line:
            if '"master"' in line:
                found = True
                break

    assert found, (
        "G-AST-TK2: TASK_KEYS tuple 'master' 영역 부재 "
        "(L34 Literal + L37 tuple 2 위치 동행 의무 영속)"
    )
