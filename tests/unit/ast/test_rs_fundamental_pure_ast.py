"""RS 1단계 Red — `rs_score.py`·`fundamental_score.py` 는 순수 leaf (I/O·await 0).

명세 = `_workspace/design/2026-10-13_rs_fundamental_phase1.md` §A·§B 「순수 함수, I/O 0」.
AST 로만 센다(주석·docstring 무관). 금지 = `async def` · `await` · I/O 모듈 import
(asyncio · asyncpg · httpx · aiohttp · requests · src.db · src.api · src.realtime · src.engine.scheduler).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_FILES = [_ROOT / "src" / "engine" / "rs_score.py", _ROOT / "src" / "engine" / "fundamental_score.py"]
_FORBIDDEN_PREFIXES = (
    "asyncio", "asyncpg", "httpx", "aiohttp", "requests",
    "src.db", "src.api", "src.realtime", "src.engine.scheduler",
)


def _forbidden(mod: str) -> bool:
    return any(mod == p or mod.startswith(p + ".") for p in _FORBIDDEN_PREFIXES)


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_pure_module_has_no_io_import_and_no_async(path: Path):
    assert path.is_file(), f"{path.relative_to(_ROOT)} 가 없다"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names if _forbidden(a.name)]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if _forbidden(mod):
                bad.append(mod)
            elif mod == "src":
                bad += [f"src.{a.name}" for a in node.names if _forbidden(f"src.{a.name}")]
        elif isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)):
            bad.append(f"{type(node).__name__}@L{node.lineno}")
    assert bad == [], f"{path.name} 순수성 위반: {bad}"
