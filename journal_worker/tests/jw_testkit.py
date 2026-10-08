"""cycle412 — 워커 테스트 공용 도우미(테스트 모듈이 `from jw_testkit import …` 로 쓴다).

`conftest.py` 가 `journal_worker/` 와 이 디렉터리를 sys.path 앞에 넣는다.
계약 = `_workspace/red/cycle412/journal_contract.md` 3절.
"""
from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parent
JW_DIR = WORKER_ROOT / "jw"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN_LOG = FIXTURES / "golden_2026-09-17_10-07.log"
GOLDEN_EXPECTED = FIXTURES / "golden_expected.json"
KST = timezone(timedelta(hours=9))


def jw(module: str):
    """`jw.<module>` 을 테스트 안에서 늦게 import 한다 — 모듈이 없으면 그 테스트만 실패한다."""
    return importlib.import_module(f"jw.{module}")


def kst(y, mo, d, h=0, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=KST)


def golden_lines() -> list[str]:
    return GOLDEN_LOG.read_text(encoding="utf-8").splitlines()


def golden_expected() -> dict:
    return json.loads(GOLDEN_EXPECTED.read_text(encoding="utf-8"))


def log_line(ts: str, level: str, logger: str, msg: str) -> str:
    """운영 파일 로그 한 줄(`src/main.py` LOG_FORMAT) — 레벨 칸은 8자 왼쪽 정렬."""
    return f"{ts} [{level:<8}] {logger} — {msg}"


def parse_all(lines) -> list[dict]:
    g = jw("grammar")
    return [e for e in (g.parse_line(ln) for ln in lines) if e is not None]


def jw_sources() -> dict[str, str]:
    """`journal_worker/jw/**/*.py` 원문 {상대경로: 내용}. 없으면 빈 dict(호출 쪽이 단언)."""
    if not JW_DIR.is_dir():
        return {}
    return {
        p.relative_to(WORKER_ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(JW_DIR.rglob("*.py"))
        if "__pycache__" not in p.parts
    }
