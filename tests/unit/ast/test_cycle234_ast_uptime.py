"""cycle234 R5 — tick blind 계측 구조 봉인 (cycle233 F2 교훈 반영: 구조 검사)."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"

EIGHT_AREAS = [
    SRC / "engine" / "risk.py",
    SRC / "engine" / "order_engine.py",
    SRC / "engine" / "session.py",
    SRC / "engine" / "scanner.py",
    SRC / "engine" / "strategy_registry.py",
    SRC / "api" / "order.py",
]
EIGHT_AREA_DIRS = [SRC / "realtime", SRC / "auth"]


class TestG1SchedulerUntouched:
    def test_scheduler_has_no_uptime_reference(self):
        """scheduler.py 무접촉 — 라인 상한 가드(<4,000L) 보호 설계 (cycle233 선례)."""
        assert "uptime" not in (SRC / "engine" / "scheduler.py").read_text(
            encoding="utf-8")


class TestG2EightAreasUntouched:
    def test_no_uptime_token_in_eight_areas(self):
        offenders = []
        files = list(EIGHT_AREAS)
        for d in EIGHT_AREA_DIRS:
            files.extend(d.rglob("*.py"))
        for f in files:
            if "uptime" in f.read_text(encoding="utf-8"):
                offenders.append(str(f))
        assert not offenders, f"8영역에 uptime 참조: {offenders}"


class TestG3BootWiring:
    def test_boot_manager_reports_and_spawns(self):
        text = (SRC / "engine" / "boot_manager.py").read_text(encoding="utf-8")
        assert "report_boot_blind_gap" in text, "부팅 blind gap 보고 부재"
        assert "ensure_heartbeat_loop" in text, "하트비트 루프 스폰 부재"


class TestG4LoopStructure:
    def test_heartbeat_loop_while_running(self):
        """구조 검사 — While.test 한정 (docstring 문자열 공허화 금지, cycle233 F2)."""
        tree = ast.parse(
            (SRC / "engine" / "uptime_monitor.py").read_text(encoding="utf-8"))
        loop_fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "heartbeat_loop":
                loop_fn = node
        assert loop_fn is not None
        top_while = next(
            (s for s in loop_fn.body if isinstance(s, ast.While)), None)
        assert top_while is not None, "while 부재 — 하트비트 반복 소멸"
        assert "_running" in ast.dump(top_while.test)
        assert any(
            isinstance(c, ast.Call) and "record_heartbeat" in ast.dump(c)
            for c in ast.walk(top_while)
        ), "루프 본문에 하트비트 기록 부재"


class TestG5LeafImports:
    def test_uptime_monitor_import_allowlist(self):
        """leaf 계약 — src 내부 import 는 db.system_config / db._kst 만."""
        tree = ast.parse(
            (SRC / "engine" / "uptime_monitor.py").read_text(encoding="utf-8"))
        allowed = {"src.db.system_config", "src.db._kst"}
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if not mod.startswith("src."):
                    continue
                # `from src.db import system_config` → src.db.system_config 로 정규화
                resolved = [f"{mod}.{a.name}" for a in node.names]
                if mod in allowed:
                    continue
                bad.extend(r for r in resolved if r not in allowed)
            elif isinstance(node, ast.Import):
                bad.extend(a.name for a in node.names if a.name.startswith("src."))
        assert not bad, f"leaf 허용 밖 import: {bad}"
