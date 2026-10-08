"""과거분 1회 적재(cycle412 계약 3.10절, 사용자 결정 D3). 기동 경로는 이 모듈을 모른다."""
from __future__ import annotations

import gzip
import time
from pathlib import Path

from jw.config import BACKFILL_MAX_BYTES_PER_SEC
from jw.grammar import parse_line
from jw.pairing import Pairer

_RESTORE_SOURCE = "log_restore"


def _open_text(path):
    p = Path(path)
    if p.suffix == ".gz":
        return gzip.open(p, "rt", encoding="utf-8", errors="replace")
    return open(p, "r", encoding="utf-8", errors="replace")


def iter_log_lines(paths, *, max_bytes_per_sec: int = BACKFILL_MAX_BYTES_PER_SEC, sleep=time.sleep):
    budget = 0
    for path in paths:
        with _open_text(path) as f:
            for line in f:
                line = line.rstrip("\n")
                budget += len(line.encode("utf-8")) + 1
                yield line
                if budget >= max_bytes_per_sec:
                    sleep(1.0)
                    budget = 0


def restore_rows(lines) -> list:
    pairer = Pairer(source=_RESTORE_SOURCE)
    events = [e for e in (parse_line(ln) for ln in lines) if e is not None]
    pairer.feed_events(events)
    return pairer.drain(final=True)["orders"]
