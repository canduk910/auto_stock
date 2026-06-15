"""사이클 89 (2026-06-09) + 사이클 133 (2026-06-15) — stock_master universe metrics facade.

사이클 133 카드 #24 영속:
- 공통 헬퍼 `make_metrics_collector` 위임 facade (사이클 67 stale_manager.py 패턴 답습).
- 행위 보존 의무: emit prefix + summary 키 + 빈 윈도우 skip 영속.

emit prefix 2종:
  - [stock_master_universe_summary] (5분 윈도우 통계, 사이클 89)
  - [full_universe_load_summary] (매일 20:00:05 적재, 사이클 101)

영속 의무:
- 사이클 74 collector 패턴 답습 (record/flush 페어)
- 사이클 76 Q2 빈 윈도우 skip
- 사이클 78 G-AST1 flush 호출 사이트 영속
- 사이클 68 KST 영속 — `src/db/_kst.py` 공용 헬퍼 (`now_kst_iso`, `KST`)
- 매매 안전성 영향 0 (로깅 영역만)
"""
from __future__ import annotations

import logging

# 사이클 68 KST 영속 — `src/db/_kst.py` 공용 헬퍼 import (L-3 KST 영속 가드)
from src.db._kst import now_kst_iso, KST  # noqa: F401

from src.engine.metrics_collector import make_metrics_collector

logger = logging.getLogger("src.engine.scheduler")

# 5분 윈도우 collector (사이클 89 답습 — universe + fetched 누적 / kospi/kosdaq/securities/etf_excluded 마지막)
_UNIVERSE_REFRESH_WINDOW_SECS: float = 300.0  # 5분 영속 (사이클 42/74/78 답습)

record_universe_refresh, flush_universe_collector, _universe_collector = make_metrics_collector(
    prefix="stock_master_universe_summary] window=300s",
    summary_keys=(
        "universe", "kospi", "kosdaq", "securities", "etf_excluded",
        "fetched", "skipped_fresh", "failed",
    ),
    accumulate_keys=("universe", "fetched", "skipped_fresh", "failed"),
    use_last=True,
)


# 사이클 101 — 매일 20:00:05 전체 유니버스 적재 collector (단일 행 패턴)
(
    record_full_universe_load_summary,
    flush_full_universe_load_collector,
    _full_universe_collector,
) = make_metrics_collector(
    prefix="full_universe_load_summary",
    summary_keys=(
        "total", "kospi", "kosdaq", "securities", "etf",
        "fetched", "skipped_ttl", "failed", "elapsed_ms",
    ),
    use_last=True,
)
