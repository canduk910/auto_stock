"""사이클 133 (2026-06-15) — 4 stock_master metrics 모듈 공통 collector 헬퍼 (카드 #24 영속).

배경:
- 사이클 89/101/122/126 4 collector 동일 패턴 (record/flush 페어 + 사이클 76 Q2 빈 윈도우 skip).
- 사이클 129 master_load_once 영역 metrics collector 부재 = 일관성 결함.
- 사이클 130 refactor-review 권고 카드 #24 LOW (-218L).

영속 의무 매트릭스:
- 사이클 67 facade re-export 패턴 답습 (기존 3 모듈은 본 헬퍼 위임 facade).
- 사이클 68 KST 영속 (`now_kst_iso` / `KST` import 영속 + L-3 가드).
- 사이클 74 collector 패턴 영속 (record/flush 페어).
- 사이클 76 Q2 빈 윈도우 skip 영속.
- 사이클 78 G-AST1 영속 (record_X 정의 모듈은 대응 flush_X 호출 사이트 ≥ 1 의무).
- 사이클 88 G-REJECT graceful 영역 단위.

매매 안전성 영향 0 (로깅 영역 한정).
"""

from __future__ import annotations

import logging
from typing import Callable

# 사이클 68 KST 영속 — `src/db/_kst.py` 공용 헬퍼 import (L-3 KST 영속 가드)
from src.db._kst import now_kst_iso, KST  # noqa: F401

logger = logging.getLogger("src.engine.scheduler")


def make_metrics_collector(
    *,
    prefix: str,
    summary_keys: tuple[str, ...],
    int_keys: tuple[str, ...] = (),
    str_keys: tuple[str, ...] = (),
    accumulate_keys: tuple[str, ...] = (),
    use_last: bool = True,
) -> tuple[Callable[[dict], None], Callable[[], None], list]:
    """공통 metrics collector 팩토리 (사이클 133 카드 #24 영속).

    동작 (사이클 74/76/89/122 답습):
    - 모듈 전역 collector list 반환 (3번째 반환값) — 호출자가 list 직접 보유 가능.
    - record_fn(stats: dict): collector 적재 (단순 append).
    - flush_fn(): 빈 윈도우 skip (사이클 76 Q2) + INFO emit + clear.

    Args:
        prefix: emit 로그 prefix (예: `stock_master_basics_refresh_flushed`).
        summary_keys: 출력 키 영역 (예: ("total", "updated", "skipped", "failed", "elapsed_ms")).
        int_keys: int 타입 키 (디폴트 = summary_keys 모두 int 처리).
        str_keys: 문자열 타입 키 (예: ("mode",)).
        accumulate_keys: 누적 합산 키 (사이클 89 universe collector 패턴 — 다중 record 합산).
        use_last: True 면 마지막 stats 의 스냅샷 키 사용 (사이클 101 패턴 = 단일 행).
                  False + accumulate_keys 활용 시 5분 윈도우 합산 (사이클 89 패턴).

    Returns:
        (record_fn, flush_fn, collector_list): 호출자가 collector list 직접 보유 가능.

    영속 의무:
    - 사이클 76 Q2 빈 윈도우 skip (`if not collector: return`).
    - 사이클 88 G-REJECT graceful (emit 영역 try/except 영역 외 — logger.info 자체는 raise 0).
    """
    collector: list[dict] = []
    _int_keys = set(int_keys) if int_keys else (set(summary_keys) - set(str_keys))
    _str_keys = set(str_keys)
    _accumulate_keys = set(accumulate_keys)

    def _record(stats: dict) -> None:
        collector.append(stats)

    def _flush() -> None:
        if not collector:
            return  # 빈 윈도우 skip (사이클 76 Q2 영속)

        # 합산 분기 (사이클 89 universe collector 답습)
        aggregated: dict = {}
        for key in summary_keys:
            if key in _accumulate_keys:
                aggregated[key] = sum(s.get(key, 0) for s in collector)
            elif use_last:
                aggregated[key] = collector[-1].get(key, 0 if key in _int_keys else "")
            else:
                aggregated[key] = sum(s.get(key, 0) for s in collector)

        # emit 영역 — format string 동적 생성 (% placeholder + 키 영역 영속)
        # 사이클 122/126 emit prefix 답습 영속 ([prefix] key1=v1 key2=v2 ...)
        parts = [f"[{prefix}]"]
        args = []
        for key in summary_keys:
            value = aggregated[key]
            if key in _str_keys:
                parts.append(f"{key}=%s")
            else:
                parts.append(f"{key}=%d")
            args.append(value)
        format_str = " ".join(parts)
        logger.info(format_str, *args)

        collector.clear()

    return _record, _flush, collector
