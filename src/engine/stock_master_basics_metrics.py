"""사이클 126 (2026-06-13) + 사이클 133 (2026-06-15) — stock_master basics metrics facade.

사이클 133 카드 #24 영속:
- 공통 헬퍼 `make_metrics_collector` 위임 facade (사이클 67 패턴 답습).
- 행위 보존 의무: emit prefix `[stock_master_basics_refresh_flushed]` + summary 키 영속.

emit prefix:
- [stock_master_basics_refresh_flushed] total=N updated=K skipped=L failed=M elapsed_ms=J

영속 의무:
- 사이클 74 collector 패턴 답습
- 사이클 76 Q2 빈 윈도우 skip
- 사이클 78 G-AST1 flush 호출 사이트 영속
- 사이클 88 G-REJECT graceful 영역 단위
- 매매 안전성 영향 0 (로깅 영역만)
"""

from __future__ import annotations

import logging

from src.db._kst import now_kst_iso, KST  # noqa: F401 (L-3 KST 영속 가드)
from src.engine.metrics_collector import make_metrics_collector

logger = logging.getLogger("src.engine.scheduler")

# 사이클 101/122 패턴 답습 — 단일 행 collector (매일 1회 적재)
(
    record_stock_master_basics_refresh,
    flush_stock_master_basics_refresh_collector,
    _basics_refresh_collector,
) = make_metrics_collector(
    prefix="stock_master_basics_refresh_flushed",
    summary_keys=("total", "updated", "skipped", "failed", "elapsed_ms"),
    use_last=True,
)
