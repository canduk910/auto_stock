"""사이클 133 (2026-06-15) — stock_master master metrics facade (신규).

사이클 129 master_load_once 영역 metrics collector 일관성 결함 해소.
사이클 130 refactor-review 카드 #24 LOW 영속.

공통 헬퍼 `make_metrics_collector` 위임 facade (사이클 67 패턴 답습).

emit prefix:
- [stock_master_master_load_summary] kospi_count=N kosdaq_count=M total=K updated=L failed=J elapsed_ms=I

영속 의무:
- 사이클 74 collector 패턴 답습
- 사이클 76 Q2 빈 윈도우 skip
- 사이클 78 G-AST1 flush 호출 사이트 영속 (scheduler.py master task loop 영역)
- 사이클 88 G-REJECT graceful 영역 단위
- 매매 안전성 영향 0 (로깅 영역만)
"""

from __future__ import annotations

import logging

from src.db._kst import now_kst_iso, KST  # noqa: F401 (L-3 KST 영속 가드)
from src.engine.metrics_collector import make_metrics_collector

logger = logging.getLogger("src.engine.scheduler")

(
    record_stock_master_master_load,
    flush_stock_master_master_load_collector,
    _master_load_collector,
) = make_metrics_collector(
    prefix="stock_master_master_load_summary",
    summary_keys=(
        "kospi_count", "kosdaq_count", "total",
        "updated", "failed", "elapsed_ms",
    ),
    use_last=True,
)
