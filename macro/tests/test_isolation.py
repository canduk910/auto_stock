"""macro_lite 패키지 격리 검증 — 이 프로젝트(stock/services/config/db) import 0건 +
events/cycle/regime 3개 파일 원본 바이트 동일 (DoD, 요건서 REQ-PKG-01).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_PKG_DIR = _BACKEND_DIR / "macro_lite"
_PROJECT_ROOT = _BACKEND_DIR.parent.parent.parent  # .../packaging/macro_lite/backend -> stock-manager

_FORBIDDEN_IMPORT_RE = re.compile(r"^\s*(from|import)\s+(stock|services|config|db)\b")


def _iter_pkg_py_files():
    assert _PKG_DIR.is_dir(), f"macro_lite 패키지 디렉토리가 없음: {_PKG_DIR}"
    return sorted(_PKG_DIR.rglob("*.py"))


def test_no_project_module_imports():
    """grep -rn "from stock\\|from services\\|from config\\|from db\\|import stock\\|..." 0건."""
    violations = []
    for f in _iter_pkg_py_files():
        text = f.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _FORBIDDEN_IMPORT_RE.match(line):
                violations.append(f"{f.relative_to(_BACKEND_DIR)}:{lineno}: {line.strip()}")
    assert violations == [], "프로젝트 모듈 import 발견:\n" + "\n".join(violations)


@pytest.mark.parametrize("pkg_filename,orig_rel_path", [
    ("events.py", "services/macro_events.py"),
    ("cycle.py", "services/macro_cycle.py"),
    ("regime.py", "services/macro_regime.py"),
])
def test_byte_identical_to_original(pkg_filename, orig_rel_path):
    """diff services/macro_*.py packaging/macro_lite/backend/macro_lite/*.py 결과가 공백."""
    pkg_file = _PKG_DIR / pkg_filename
    orig_file = _PROJECT_ROOT / orig_rel_path

    if not orig_file.exists():
        pytest.skip(f"원본 파일 없음(다른 위치로 이동됨?): {orig_file}")

    assert pkg_file.exists(), f"패키지 파일이 아직 없음: {pkg_file}"
    assert pkg_file.read_bytes() == orig_file.read_bytes(), (
        f"{pkg_file}가 원본 {orig_file}과 바이트 단위로 다름 (REQ-PKG-01 위반)"
    )
