"""cycle446 — 워커 테스트 공용 도우미. `conftest.py` 가 sys.path 를 준비한다."""
from __future__ import annotations

import fnmatch
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parent
LW_DIR = WORKER_ROOT / "lw"
KST = timezone(timedelta(hours=9))


def kst(y, mo, d, h=0, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=KST)


def all_worker_files():
    assert WORKER_ROOT.is_dir()
    return [
        p for p in sorted(WORKER_ROOT.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc"}
    ]


def all_worker_py():
    return [p for p in all_worker_files() if p.suffix == ".py"]


def lw_sources() -> dict:
    out = {}
    for p in sorted(LW_DIR.glob("*.py")):
        out[f"lw/{p.name}"] = p.read_text(encoding="utf-8")
    return out


def ignored(path: str, patterns: list) -> bool:
    """docker 빌드 문맥 규칙을 줄인 판정(journal_worker 와 같은 헬퍼)."""
    verdict = False
    for raw in patterns:
        neg = raw.startswith("!")
        pat = raw[1:] if neg else raw
        pat = pat.strip().lstrip("/").rstrip("/")
        if not pat:
            continue
        parts = path.split("/")
        prefixes = ["/".join(parts[:k]) for k in range(1, len(parts) + 1)]
        hit = any(fnmatch.fnmatch(pre, pat) for pre in prefixes)
        if pat.startswith("**/"):
            sub = pat[3:]
            hit = hit or any(fnmatch.fnmatch(seg, sub) for seg in parts) or any(
                fnmatch.fnmatch("/".join(parts[k:]), sub) for k in range(len(parts)))
        if hit:
            verdict = not neg
    return verdict
