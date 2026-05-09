"""변경 파일 → 영향 테스트 출력기.

사용:
    python tools/test_impact/affected.py HEAD~1               # 모든 영향 테스트
    python tools/test_impact/affected.py HEAD --target=backend
    python tools/test_impact/affected.py HEAD --target=frontend

빈 출력일 수 있음(영향 없음). pytest/vitest에 그대로 파이프 가능.
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX_PATH = ROOT / "_workspace" / "test_index.yaml"
OVERRIDES_PATH = Path(__file__).resolve().parent / "manual_overrides.yaml"


def _changed_files(ref: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", ref], cwd=ROOT, text=True
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def _expand_glob(pattern: str, candidates: list[str]) -> list[str]:
    return [c for c in candidates if fnmatch.fnmatch(c, pattern)]


def _collect_all_tests(target: str) -> list[str]:
    if target in ("backend", "all"):
        backend = [
            p.relative_to(ROOT).as_posix()
            for p in (ROOT / "tests").rglob("test_*.py")
        ]
    else:
        backend = []
    if target in ("frontend", "all"):
        frontend = subprocess.check_output(
            ["git", "ls-files", "frontend/src"], cwd=ROOT, text=True
        ).splitlines()
        frontend = [
            f
            for f in frontend
            if f.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
            or "__tests__/" in f
        ]
    else:
        frontend = []
    return backend + frontend


def _resolve_overrides(changed: list[str], all_tests: list[str]) -> set[str]:
    if not OVERRIDES_PATH.exists():
        return set()
    overrides = yaml.safe_load(OVERRIDES_PATH.read_text(encoding="utf-8")) or {}
    result: set[str] = set()
    for pat, test_globs in overrides.items():
        if any(fnmatch.fnmatch(c, pat) or c == pat for c in changed):
            for g in test_globs:
                result.update(_expand_glob(g, all_tests))
    return result


def affected(ref: str, target: str = "all") -> list[str]:
    changed = _changed_files(ref)
    if not INDEX_PATH.exists():
        # 인덱스 없으면 안전망: 전체 실행
        return _collect_all_tests(target)
    index = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8")) or {}

    sections: list[dict] = []
    if target in ("backend", "all"):
        sections.append(index.get("backend") or {})
    if target in ("frontend", "all"):
        sections.append(index.get("frontend") or {})

    tests: set[str] = set()
    for section in sections:
        for ch in changed:
            entry = section.get(ch)
            if not entry:
                continue
            tests.update(entry.get("direct_tests", []))
            tests.update(entry.get("transitive_tests", []))

    all_tests = _collect_all_tests(target)
    tests.update(_resolve_overrides(changed, all_tests))

    # 필터: target에 맞는 것만
    if target == "backend":
        tests = {t for t in tests if t.startswith("tests/")}
    elif target == "frontend":
        tests = {t for t in tests if t.startswith("frontend/")}

    return sorted(tests)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ref", help="git ref to compare against (예: HEAD~1, origin/main)")
    parser.add_argument(
        "--target",
        choices=["backend", "frontend", "all"],
        default="all",
    )
    args = parser.parse_args()
    tests = affected(args.ref, args.target)
    if tests:
        print(" ".join(tests))
    return 0


if __name__ == "__main__":
    sys.exit(main())
