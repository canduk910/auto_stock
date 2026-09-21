"""cycle341 — `pytestmark` 를 두 번 대입해 앞의 마크를 **조용히 지우는** 것을 막는다.

## 왜 이 덫이 필요한가

`pytestmark` 는 평범한 모듈 전역 변수다. 두 번 대입하면 파이썬이 아무 말 없이
**뒤엣것으로 덮는다** — 앞의 마크는 사라지는데 코드에는 그대로 보인다.

2026-09-22 실측 = `test_cycle318_impact_index_freshness.py` 에 타임아웃 마크를
`import pytest` 바로 아래 넣었는데, 그 파일 조금 아래에 이미
`pytestmark = pytest.mark.unit` 이 있어 **타임아웃 마크가 통째로 무효**였다.
돌연변이(`timeout(240)` → `timeout(2)`)를 돌렸더니 **그대로 통과**해서 드러났다 —
안 돌렸으면 「CI 타임아웃을 고쳤다」고 믿은 채 같은 실패를 다시 만났을 것이다.

🔴 이것은 이 저장소가 반복해 밟는 **「공허 통과」** 계열이다(가드는 초록인데 아무것도
안 지킨다). 마크가 하는 일이 `slow`/`unit` 분류든 타임아웃이든 옵트아웃이든,
사라진 사실이 **아무 신호도 내지 않는다**는 점이 같다.

## 고치는 법

마크가 여럿이면 **한 대입에 리스트로** 담는다.

    pytestmark = [pytest.mark.unit, pytest.mark.timeout(240)]
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_TESTS = _ROOT / "tests"


def _module_level_pytestmark_assignments(path: Path) -> list[int]:
    """그 파일의 **모듈 최상위** `pytestmark = ...` 대입 줄 번호들."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    lines: list[int] = []
    for node in tree.body:                      # 최상위만 — 함수 안 지역변수는 무관
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "pytestmark":
                    lines.append(node.lineno)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "pytestmark":
                lines.append(node.lineno)
    return lines


def test_g341_1_no_test_file_assigns_pytestmark_twice() -> None:
    """🔴 한 파일에 `pytestmark` 대입은 **최대 1회**다.

    두 번이면 앞의 마크가 조용히 사라진다 — 여럿이면 리스트로 담는다.
    """
    offenders: list[str] = []
    for path in sorted(_TESTS.rglob("test_*.py")):
        lines = _module_level_pytestmark_assignments(path)
        if len(lines) > 1:
            rel = path.relative_to(_ROOT)
            offenders.append(f"{rel} — {len(lines)}회 (줄 {lines})")
    assert not offenders, (
        "`pytestmark` 를 두 번 대입하면 **뒤엣것이 앞엣것을 덮어** 앞의 마크가 조용히 "
        "사라진다. 여럿이면 한 대입에 리스트로 담는다 "
        "— `pytestmark = [pytest.mark.unit, pytest.mark.timeout(240)]`:\n  "
        + "\n  ".join(offenders)
    )


def test_g341_2_the_guard_actually_detects_a_double_assignment(tmp_path: Path) -> None:
    """🔴 양성 대조군 — 덫이 진짜로 잡는지 확인한다.

    이게 없으면 `_module_level_pytestmark_assignments` 가 항상 `[]` 를 돌려줘도
    위 테스트가 초록이다(= 이 파일 자신이 공허 통과가 된다).
    """
    bad = tmp_path / "test_double.py"
    bad.write_text(
        "import pytest\n"
        "pytestmark = pytest.mark.timeout(240)\n"
        "pytestmark = pytest.mark.unit\n",
        encoding="utf-8",
    )
    assert _module_level_pytestmark_assignments(bad) == [2, 3]

    good = tmp_path / "test_single.py"
    good.write_text(
        "import pytest\n"
        "pytestmark = [pytest.mark.unit, pytest.mark.timeout(240)]\n",
        encoding="utf-8",
    )
    assert _module_level_pytestmark_assignments(good) == [2]

    none = tmp_path / "test_none.py"
    none.write_text("def test_x():\n    pass\n", encoding="utf-8")
    assert _module_level_pytestmark_assignments(none) == []


def test_g341_3_function_local_pytestmark_is_not_counted(tmp_path: Path) -> None:
    """함수 안의 같은 이름은 모듈 마크가 아니다 — 오탐을 만들지 않는다."""
    f = tmp_path / "test_local.py"
    f.write_text(
        "import pytest\n"
        "pytestmark = pytest.mark.unit\n"
        "\n"
        "def test_x():\n"
        "    pytestmark = 'not a mark'\n"
        "    assert pytestmark\n",
        encoding="utf-8",
    )
    assert _module_level_pytestmark_assignments(f) == [2]


def test_g341_4_the_file_that_prompted_this_guard_is_clean() -> None:
    """그 사건의 현장이 실제로 고쳐졌는지 이름으로 못 박는다."""
    target = _TESTS / "unit" / "deploy" / "test_cycle318_impact_index_freshness.py"
    assert target.exists(), f"{target} 가 없다 — 이름이 바뀌었으면 이 단언도 옮긴다"
    assert len(_module_level_pytestmark_assignments(target)) == 1
    src = target.read_text(encoding="utf-8")
    # 타임아웃 마크가 살아 있는지도 함께 본다(전역 60초로는 CI 에서 모자란다).
    assert "pytest.mark.timeout(" in src, (
        "인덱스 재생성 테스트는 subprocess 로 빌드 도구를 실제 실행해 느린 CI 에서 "
        "전역 60초를 넘는다 — 타임아웃 마크를 지우면 Deploy 가 다시 skip 된다"
    )
