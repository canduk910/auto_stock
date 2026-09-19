"""cycle323 — 테스트가 리포 파일을 더럽힌 채 끝나던 것.

## 무엇이 문제였나

`test_cycle316_frontend_impact_index.py::test_tool_runs_and_is_deterministic` 이
`node tools/test_impact/build_index_frontend.mjs` 를 **리포에 대고 그대로** 돌렸다.
그 도구는 추적 파일 `_workspace/test_index.yaml` 을 제자리에서 덮어쓴다.

내용은 같지만 `generated_at` 이 매번 바뀌므로, **테스트를 돌린 것만으로 작업 트리가 더러워진다.**

## 왜 이것이 위험한가

혼자서는 무해해 보인다. 위험은 그 다음이다 —

> 더러워진 트리에서 `git add -A` 를 하면 **내가 하지 않은 변경이 커밋에 실린다.**

2026-09-19 에 원본 PDF 5권(141MB)이 정확히 그 경로로 커밋될 뻔했다. 그때 살린 것은
가드가 아니라 **커밋 전에 `git status` 를 눈으로 읽는 절차**였다. 절차는 사람이 건너뛴다.

그리고 이 더러움은 **조용하다** — `git status` 에 한 줄 뜨는 것이 전부고, 매번 뜨면
사람은 그것을 배경 소음으로 학습한다. 그러면 진짜 이상한 변경이 섞여도 안 보인다.

## 왜 cycle318 가드가 못 잡았나

cycle318 은 **내용 구역만** 비교한다(생성 시각은 잡음 축이라 일부러 뺐다).
시각만 바뀐 더러움은 그 가드의 시야 밖이다 — 둘은 서로 다른 것을 지킨다.

## 이 파일이 지키는 계약

리포의 추적 파일을 덮어쓰는 도구를 부르는 테스트는 **되돌린다.**
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_TESTS = _ROOT / "tests"

#: 리포의 추적 파일을 **제자리에서 덮어쓰는** 도구들. 늘어나면 여기에 더한다.
#: 🔴 **파일명이 아니라 디렉터리까지** 적는다 — 실제 호출자는 전부
#: `ROOT / "tools/test_impact/build_index.py"` 처럼 **경로**로 참조하고,
#: 이 상수 자신은 그 경로를 통째로 담지 않아 **자기 탐지를 피한다**(아래 오탐 가드 참조).
_TOOL_DIR = "tools/test_impact"
_TOOL_NAMES = ("build_index.py", "build_index_frontend.mjs")
_MUTATING_TOOLS = tuple(f"{_TOOL_DIR}/{n}" for n in _TOOL_NAMES)

#: 복원을 뜻하는 흔적. 하나라도 있으면 통과로 본다(구현 방식을 강제하지 않는다).
_RESTORE_MARKS = ("copyfile", "write_text(before", "write_text(_before")


def _test_files() -> list[Path]:
    return sorted(p for p in _TESTS.rglob("test_*.py"))


def _calls_mutating_tool(body: str) -> list[str]:
    """**호출 노드 안**에 도구 이름이 있을 때만 「부른다」로 본다 (AST).

    🔴 텍스트로 재면 안 된다. 처음엔 「주석·docstring 을 걷어내고 이름 찾기」로 짰는데
    **이 파일이 스스로를 잡았다** — 도구 이름이 `_MUTATING_TOOLS` 상수에 들어 있으니
    당연히 코드에 있다. 「자식 프로세스를 띄우는가」를 더해도 같았다(그 이름들 역시
    상수였다). 예외 목록으로 막으면 그 목록이 곧 구멍이 된다.

    구조로 재면 이 모호함이 사라진다 — 모듈 최상단의 **튜플 대입은 `Call` 이 아니고**,
    `subprocess.run([... "build_index.py" ...])` 는 `Call` 이다.
    """
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return []

    spawns = any(
        isinstance(n, ast.Call)
        and "subprocess" in ast.dump(n.func)[:200]
        for n in ast.walk(tree)
    )
    if not spawns:
        return []

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for t in _MUTATING_TOOLS:
                if t in node.value:
                    found.add(t)
    return sorted(found)


def test_tests_that_run_index_tools_restore_the_file() -> None:
    """인덱스 도구를 돌리는 테스트는 **원본을 되돌리는가**.

    막는 회귀 = 백업·복원 없이 도구를 부르는 테스트가 다시 들어오는 것.
    그러면 스위트를 한 번 돌릴 때마다 작업 트리가 더러워지고,
    그 더러움이 `git add -A` 를 타고 커밋에 실린다.
    """
    offenders: list[str] = []
    checked = 0

    for p in _test_files():
        body = p.read_text(encoding="utf-8")
        tools = _calls_mutating_tool(body)
        if not tools:
            continue
        checked += 1
        if not any(m in body for m in _RESTORE_MARKS):
            offenders.append(f"{p.relative_to(_ROOT)} (부르는 도구: {', '.join(tools)})")

    assert checked >= 3, (
        f"인덱스 도구를 부르는 테스트가 {checked}개뿐이다 — 탐색이 헛돌고 있다. "
        "파일 이름이나 경로가 바뀌었는지 확인한다."
    )
    assert not offenders, (
        "인덱스 도구를 돌리면서 원본을 되돌리지 않는 테스트가 있다.\n  "
        + "\n  ".join(offenders)
        + "\n  → `before = path.read_text()` … `finally: path.write_text(before)` 로 감싼다."
    )


def test_guard_can_see_the_tools() -> None:
    """탐색이 공허하지 않은가 — 도구 파일이 실제로 있는가.

    경로가 틀리면 위 단언이 **항상 초록**이 된다.
    """
    for rel in _MUTATING_TOOLS:
        assert (_ROOT / rel).is_file(), f"도구가 없다: {rel}"


def test_docstring_mentions_do_not_trigger() -> None:
    """설명 문장 속 도구 이름은 **잡지 않는가** — 오탐 방지 계약.

    이 파일 자신이 산 증거다. 여기 docstring 에 두 도구 이름이 모두 나오지만
    실제 호출은 0건이라 위 검사에 걸리면 안 된다.
    """
    body = (_ROOT / "tests/unit/deploy/test_cycle323_tests_leave_repo_clean.py").read_text(
        encoding="utf-8"
    )
    assert "build_index_frontend.mjs" in body, "전제가 깨졌다 — 이 파일에 도구 이름이 없다"
    assert not _calls_mutating_tool(body), (
        "주석·docstring 걷어내기가 동작하지 않는다 — 이 파일이 스스로를 잡는다"
    )
