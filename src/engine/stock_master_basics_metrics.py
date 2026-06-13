"""사이클 126 (2026-06-13) — stock_master basics 보강 메트릭 collector/flush.

사이클 122 stock_master_daily_metrics.py 패턴 직답습 + 사이클 74/78/89/101 동형:
- record/flush 페어링
- 빈 윈도우 skip (사이클 76 Q2)
- KIS 영속 헬퍼 import (사이클 68 KST)
- 사이클 78 G-AST1 flush 호출 사이트 영속 의무

emit prefix:
- [stock_master_basics_refresh_summary] total=N updated=K
  skipped=L failed=M elapsed_ms=J

영속 의무:
- 사이클 78 G-AST1 — `record_*` 정의 모듈은 대응 `flush_*` 호출 사이트 ≥1
- 사이클 88 G-REJECT graceful 영역 단위
- 매매 안전성 영향 0 (로깅 영역만)
"""

from __future__ import annotations

import logging

# 사이클 68 KST 영속 — `src/db/_kst.py` 공용 헬퍼 import
from src.db._kst import now_kst_iso, KST  # noqa: F401 (L-3 KST 영속 가드)

logger = logging.getLogger("src.engine.scheduler")

# 사이클 101/122 패턴 답습 — 단일 행 collector (매일 1회 적재)
_basics_refresh_collector: list[dict] = []


def record_stock_master_basics_refresh(stats: dict) -> None:
    """1회 보강 결과를 collector 적재.

    사이클 122 `record_stock_master_daily_load` 패턴 직답습.

    Args:
        stats: summary dict. 권장 키:
            - total (int): 전체 ticker 수 (stock_master 조회 결과)
            - updated (int): KIS CTPF1002R 보강 성공 건수
            - skipped (int): basics 빈 응답 등 skip 건수
            - failed (int): KIS 호출 실패 또는 DB upsert 실패 건수
            - elapsed_ms (int): 소요 시간 (ms)
    """
    _basics_refresh_collector.append(stats)


def flush_stock_master_basics_refresh_collector() -> None:
    """collector → 1행 emit + clear.

    사이클 74/78/89/101/122 패턴 직답습. 빈 윈도우 skip (사이클 76 Q2).

    emit prefix:
      [stock_master_basics_refresh_summary] total=N updated=K
      skipped=L failed=M elapsed_ms=J
    """
    global _basics_refresh_collector
    if not _basics_refresh_collector:
        return  # 빈 윈도우 skip

    last = _basics_refresh_collector[-1]
    total = last.get("total", 0)
    updated = last.get("updated", 0)
    skipped = last.get("skipped", 0)
    failed = last.get("failed", 0)
    elapsed_ms = last.get("elapsed_ms", 0)

    logger.info(
        "[stock_master_basics_refresh_flushed] total=%d updated=%d "
        "skipped=%d failed=%d elapsed_ms=%d",
        total, updated, skipped, failed, elapsed_ms,
    )

    _basics_refresh_collector.clear()
