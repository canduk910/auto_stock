"""백엔드 test impact 인덱스 생성기.

- src/**/*.py 의 import 문을 AST로 분석해 src 모듈 의존성 그래프를 만든다
- tests/**/test_*.py 가 import하는 src 모듈을 역추적해 direct_tests 매핑
- 그래프 BFS로 transitive_tests 계산
- _workspace/test_index.yaml 의 backend: 섹션을 갱신한다 (frontend 섹션은 보존)

사용:
    python tools/test_impact/build_index.py
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
SRC_ROOT = ROOT / "src"
TEST_ROOT = ROOT / "tests"
INDEX_PATH = ROOT / "_workspace" / "test_index.yaml"
KST = timezone(timedelta(hours=9))


def _module_name_for(path: Path) -> str:
    """src/foo/bar.py → src.foo.bar"""
    rel = path.relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def _path_for_module(name: str) -> Path | None:
    """src.foo.bar → src/foo/bar.py 가능하면 반환."""
    candidate = ROOT / Path(*name.split(".")).with_suffix(".py")
    if candidate.exists():
        return candidate
    pkg_init = ROOT / Path(*name.split(".")) / "__init__.py"
    if pkg_init.exists():
        return pkg_init
    return None


def _parse_imports(path: Path) -> list[str]:
    """파일 내 from-import / import 문에서 모듈 이름 리스트 반환.

    ``from src.api import base`` 처럼 서브모듈을 가져오는 경우, 모듈 자체(``src.api``)와
    잠재 서브모듈(``src.api.base``)을 모두 후보로 내보낸다. 이후 _resolve_to_src 에서
    실제 파일이 존재하는 후보만 채택된다.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
            for alias in node.names:
                names.append(f"{node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def _resolve_to_src(module_names: list[str]) -> list[Path]:
    """import 이름들 중 src 트리 안에 존재하는 파일들만 추출."""
    out: list[Path] = []
    for name in module_names:
        # src.foo.bar 형태 또는 src.foo (패키지)
        parts = name.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            p = _path_for_module(cand)
            if p is not None and SRC_ROOT in p.parents:
                out.append(p)
                break
    return out


def _collect_files(root: Path, pattern: str) -> list[Path]:
    return [p for p in root.rglob(pattern) if "__pycache__" not in p.parts]


def build() -> dict:
    src_files = _collect_files(SRC_ROOT, "*.py")
    test_files = _collect_files(TEST_ROOT, "test_*.py")
    # tests/**/conftest.py 도 의존성 그래프에 포함한다.
    # conftest.py 가 import 한 src 모듈은 같은 디렉토리(트리) 의 모든 test 의 의존성으로 전파.
    conftest_files = _collect_files(TEST_ROOT, "conftest.py")

    src_imports: dict[Path, list[Path]] = {
        f: _resolve_to_src(_parse_imports(f)) for f in src_files
    }
    test_imports: dict[Path, list[Path]] = {
        f: _resolve_to_src(_parse_imports(f)) for f in test_files
    }
    conftest_imports: dict[Path, list[Path]] = {
        f: _resolve_to_src(_parse_imports(f)) for f in conftest_files
    }

    # 각 test 파일의 의존성에 그 test 가 속한 모든 상위 conftest 의 의존성을 합친다.
    # (pytest 가 같은 디렉토리 + 상위 디렉토리의 conftest 를 자동 적용하는 규칙)
    for t in test_files:
        merged = list(test_imports[t])
        for c in conftest_files:
            try:
                t.relative_to(c.parent)
            except ValueError:
                continue
            merged.extend(conftest_imports.get(c, []))
        test_imports[t] = merged

    # direct: src 모듈이 어떤 테스트의 import 에 직접 또는 conftest 경유로 등장하는지
    direct: dict[Path, set[Path]] = defaultdict(set)
    for t, deps in test_imports.items():
        for d in deps:
            direct[d].add(t)

    # 역방향 src 그래프: src 파일을 import하는 다른 src 파일들
    reverse_src: dict[Path, set[Path]] = defaultdict(set)
    for s, deps in src_imports.items():
        for d in deps:
            reverse_src[d].add(s)

    # transitive: BFS로 역방향 src 그래프를 타고 모은 모든 테스트
    transitive: dict[Path, set[Path]] = {}
    for s in src_files:
        seen: set[Path] = set()
        queue = deque([s])
        tests: set[Path] = set()
        while queue:
            cur = queue.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            for parent in reverse_src.get(cur, ()):
                if parent not in seen:
                    queue.append(parent)
            tests.update(direct.get(cur, ()))
        transitive[s] = tests - direct.get(s, set())

    backend: dict[str, dict] = {}
    unmapped: list[str] = []
    for s in sorted(src_files):
        rel = s.relative_to(ROOT).as_posix()
        d = sorted(p.relative_to(ROOT).as_posix() for p in direct.get(s, set()))
        t = sorted(p.relative_to(ROOT).as_posix() for p in transitive.get(s, set()))
        if not d and not t:
            unmapped.append(rel)
        backend[rel] = {
            "direct_tests": d,
            "transitive_tests": t,
        }

    # 기존 frontend 섹션 보존
    existing: dict = {}
    if INDEX_PATH.exists():
        existing = yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8")) or {}

    payload = {
        "version": 1,
        "generated_at": datetime.now(KST).isoformat(),
        "backend": backend,
        "frontend": existing.get("frontend", {}),
        "stats": {
            "backend_modules": len(src_files),
            "backend_tests": len(test_files),
            "frontend_modules": len(existing.get("frontend", {})),
            "frontend_tests": existing.get("stats", {}).get("frontend_tests", 0),
            "unmapped_modules": unmapped,
        },
    }
    return payload


def main() -> int:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = build()
    INDEX_PATH.write_text(
        yaml.safe_dump(payload, sort_keys=True, allow_unicode=True), encoding="utf-8"
    )
    print(f"[build_index] wrote {INDEX_PATH.relative_to(ROOT)}")
    print(f"  backend modules: {payload['stats']['backend_modules']}")
    print(f"  backend tests:   {payload['stats']['backend_tests']}")
    print(f"  unmapped:        {len(payload['stats']['unmapped_modules'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
