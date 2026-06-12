"""사이클 122 (2026-06-12) — stock_master_daily 적재 메트릭 collector/flush.

사이클 74/78/89/101 패턴 직답습:
- record/flush 페어링
- 빈 윈도우 skip (사이클 76 Q2)
- KIS 영속 헬퍼 import (사이클 68 KST)
- 사이클 78 G-AST1 flush 호출 사이트 영속 의무

emit prefix:
- [stock_master_daily_load_summary] total=N fetched=M skipped_fresh=K
  failed=L elapsed_ms=J upserted_rows=I mode=full|incremental

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

# 사이클 101 패턴 답습 — 단일 행 collector (매일 1회 적재)
_daily_load_collector: list[dict] = []


def record_stock_master_daily_load(stats: dict) -> None:
    """1회 적재 결과를 collector 적재.

    사이클 101 `record_full_universe_load_summary` 패턴 직답습.

    Args:
        stats: summary dict. 권장 키:
            - total (int): 전체 ticker 수 (stock_master 조회 결과)
            - fetched (int): KIS fetch_daily_candles 성공 건수
            - upserted_rows (int): DB upsert 누적 행 수
            - skipped_fresh (int): 점진 적재 시 max_bas_dd 가 오늘인 ticker (skip)
            - failed (int): KIS 호출 실패 건수
            - elapsed_ms (int): 소요 시간 (ms)
            - mode (str): "full" (백필) 또는 "incremental" (증분)
    """
    _daily_load_collector.append(stats)


def flush_stock_master_daily_load_collector() -> None:
    """collector → 1행 emit + clear.

    사이클 74/78/89/101 패턴 직답습. 빈 윈도우 skip (사이클 76 Q2).

    emit prefix:
      [stock_master_daily_load_summary] total=N fetched=M skipped_fresh=K
      failed=L elapsed_ms=J upserted_rows=I mode=...
    """
    global _daily_load_collector
    if not _daily_load_collector:
        return  # 빈 윈도우 skip

    last = _daily_load_collector[-1]
    total = last.get("total", 0)
    fetched = last.get("fetched", 0)
    upserted_rows = last.get("upserted_rows", 0)
    skipped_fresh = last.get("skipped_fresh", 0)
    failed = last.get("failed", 0)
    elapsed_ms = last.get("elapsed_ms", 0)
    mode = last.get("mode", "incremental")

    logger.info(
        "[stock_master_daily_load_summary] total=%d fetched=%d upserted_rows=%d "
        "skipped_fresh=%d failed=%d elapsed_ms=%d mode=%s",
        total, fetched, upserted_rows, skipped_fresh, failed, elapsed_ms, mode,
    )

    _daily_load_collector.clear()
