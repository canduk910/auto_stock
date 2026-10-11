"""cycle448 — 전략별 핵심값 분포(`strategy_core_metrics.py`) 구조 가드.

사용자 결정(2026-10-11): 주간 자문에만 필요하고 일일 보고에는 필요 없다.

  G-448-1  leaf `src/engine/strategy_core_metrics.py` 는 순수하다 — `src.*` import 0 ·
           `await`/`async def` 0 · 로깅/시계/IO 모듈 import 0.
  G-448-2  8영역(`risk`·`order_engine`·`session`·`scanner`·`strategy_registry`·
           `api/order`·`realtime`·`auth`) + `scheduler.py` 는 이 leaf 를 import 하지 않는다
           (매매 경로 무접촉).
  G-448-3  일일 보고 경로(`log_metrics_collector.py` · `log_analysis_engine.py` ·
           `daily_metrics_snapshot.py` · `routes/log_reports.py`)는 이 leaf 를
           import 하지 않는다 — 일일 보고에 전략 핵심값 분포가 새지 않는다.
  G-448-4  소비처는 `recommendation_engine.py`(20:00 주간 자문)와
           `routes/strategies.py`(`GET /api/strategies/core-metrics`) 둘뿐이다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
LEAF = SRC / "engine" / "strategy_core_metrics.py"

_EIGHT_AREA_FILES = (
    SRC / "engine" / "risk.py",
    SRC / "engine" / "order_engine.py",
    SRC / "engine" / "session.py",
    SRC / "engine" / "scanner.py",
    SRC / "engine" / "strategy_registry.py",
    SRC / "api" / "order.py",
)
_EIGHT_AREA_DIRS = (SRC / "realtime", SRC / "auth")
_SCHEDULER_FILE = SRC / "engine" / "scheduler.py"

_DAILY_REPORT_FILES = (
    SRC / "engine" / "log_metrics_collector.py",
    SRC / "engine" / "log_analysis_engine.py",
    SRC / "engine" / "daily_metrics_snapshot.py",
    SRC / "routes" / "log_reports.py",
)

_FORBIDDEN_LEAF_PREFIXES = (
    "src", "asyncio", "logging", "socket", "http", "urllib", "ssl", "sqlite3",
    "subprocess", "threading", "concurrent", "multiprocessing", "time", "httpx", "asyncpg",
    "datetime",
)


def _parse(path: Path) -> tuple[str, ast.Module]:
    text = path.read_text(encoding="utf-8")
    return text, ast.parse(text)


def _imported_top_modules(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
    return out


def _mentions_module(text: str, module_name: str) -> bool:
    return module_name in text


# ═════════════════════════════════════════════════════════════════════════════
# G-448-1 — leaf 순수성
# ═════════════════════════════════════════════════════════════════════════════

def test_g448_1_leaf_imports_only_stdlib_math_and_typing():
    text, tree = _parse(LEAF)
    top_modules = _imported_top_modules(tree)
    forbidden_hit = top_modules & set(_FORBIDDEN_LEAF_PREFIXES)
    assert forbidden_hit == set(), f"leaf 가 금지된 모듈을 import 했다: {forbidden_hit}"
    assert top_modules <= {"math", "typing", "__future__"}, top_modules


def test_g448_1b_leaf_has_no_await_or_async_def():
    text, tree = _parse(LEAF)
    async_nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.Await, ast.AsyncFunctionDef))]
    assert async_nodes == [], "leaf 에 await/async def 가 있다 — never-raise 순수 계약 위반"


def test_g448_1c_leaf_has_no_wall_clock_calls():
    text, _ = _parse(LEAF)
    for token in ("datetime.now(", "time.time(", "time.monotonic(", "date.today("):
        assert token not in text, f"leaf 가 벽시계를 읽는다: {token}"


# ═════════════════════════════════════════════════════════════════════════════
# G-448-2 — 8영역·scheduler.py 무접촉
# ═════════════════════════════════════════════════════════════════════════════

def test_g448_2_eight_areas_do_not_import_leaf():
    hits = []
    for path in _EIGHT_AREA_FILES:
        text = path.read_text(encoding="utf-8")
        if _mentions_module(text, "strategy_core_metrics"):
            hits.append(str(path))
    for d in _EIGHT_AREA_DIRS:
        for path in d.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if _mentions_module(text, "strategy_core_metrics"):
                hits.append(str(path))
    assert hits == [], f"8영역이 strategy_core_metrics 를 참조한다: {hits}"


def test_g448_2b_scheduler_does_not_import_leaf():
    text = _SCHEDULER_FILE.read_text(encoding="utf-8")
    assert "strategy_core_metrics" not in text


# ═════════════════════════════════════════════════════════════════════════════
# G-448-3 — 일일 보고 경로 비누출
# ═════════════════════════════════════════════════════════════════════════════

def test_g448_3_daily_report_path_does_not_reference_leaf():
    hits = []
    for path in _DAILY_REPORT_FILES:
        text = path.read_text(encoding="utf-8")
        if _mentions_module(text, "strategy_core_metrics"):
            hits.append(str(path))
    assert hits == [], f"일일 보고 경로가 strategy_core_metrics 를 참조한다: {hits}"


# ═════════════════════════════════════════════════════════════════════════════
# G-448-4 — 소비처 = 둘뿐
# ═════════════════════════════════════════════════════════════════════════════

def test_g448_4_only_two_consumers_reference_leaf():
    hits = []
    for path in SRC.rglob("*.py"):
        if path == LEAF:
            continue
        text = path.read_text(encoding="utf-8")
        if _mentions_module(text, "strategy_core_metrics"):
            hits.append(path.relative_to(SRC).as_posix())
    assert set(hits) == {"engine/recommendation_engine.py", "routes/strategies.py"}, hits
