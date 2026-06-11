"""사이클 89 (2026-06-09) — stock_master universe 갱신 메트릭 collector/flush 모듈.

사이클 74/78 sampling/aggregation 패턴 직답습.

emit prefix 2종:
  - [stock_master_bulk_refresh] universe=500 kospi=250 kosdaq=250 securities=480
    etf_excluded=15 fetched=N elapsed_ms=M  (개장 전 1회 INFO)
  - [stock_master_universe_summary] total=500 fresh=N stale=M held=K next_day=L
    (5분 주기 통계)

영속 의무:
  - 사이클 74 collector 패턴 답습 (record/flush 페어링)
  - 사이클 78 G-AST1 flush 호출 사이트 영속 (scheduler.py 에서 flush 의무)
  - 사이클 68 KST 영속 — `src/db/_kst.py` 공용 헬퍼 (`now_kst_iso`, `KST`) 사용 의무
  - 매매 안전성 영향 0 (로깅 영역만)
"""
from __future__ import annotations

import logging

# 사이클 68 KST 영속 — `src/db/_kst.py` 공용 헬퍼 import
# (now_kst_iso, KST 직접 사용은 현재 없으나, 미래 시각 처리 시 헬퍼 경유 의무)
from src.db._kst import now_kst_iso, KST  # noqa: F401 (L-3 KST 영속 가드)

logger = logging.getLogger("src.engine.scheduler")

# ---------------------------------------------------------------------------
# 5분 윈도우 collector (사이클 74 패턴 답습)
# ---------------------------------------------------------------------------
_universe_collector: list[dict] = []
_UNIVERSE_REFRESH_WINDOW_SECS: float = 300.0  # 5분 (사이클 42/74/78 답습)


def record_universe_refresh(stats: dict) -> None:
    """5분 윈도우 universe refresh 통계 1건 collector 적재.

    사이클 74 `record_stale_watcher_check` 패턴 직답습.

    Args:
        stats: 통계 dict. 권장 키:
            - universe (int): 총 universe 크기
            - kospi (int): KOSPI 적재 건수
            - kosdaq (int): KOSDAQ 적재 건수
            - securities (int): ETF/리츠/SPAC 제외 후 순수 보통주 수
            - etf_excluded (int): ETF/리츠/SPAC 제외 건수
            - fetched (int): stock_master upsert 건수
            - elapsed_ms (int): 소요 시간 (ms)
    """
    _universe_collector.append(stats)


def flush_universe_collector() -> None:
    """5분 윈도우 통계 collector → 1행 emit + clear.

    사이클 74 `flush_stale_watcher_collector` + 사이클 78 G-AST1 패턴 직답습.
    빈 윈도우는 skip (사이클 76 Q2 답습).

    emit prefix:
      - [stock_master_universe_summary] total=N fresh=M stale=K held=L next_day=J
    """
    global _universe_collector
    if not _universe_collector:
        return  # 빈 윈도우 skip (사이클 76 Q2)

    total_universe = sum(s.get("universe", 0) for s in _universe_collector)
    total_fetched = sum(s.get("fetched", 0) for s in _universe_collector)
    total_skipped = sum(s.get("skipped_fresh", 0) for s in _universe_collector)
    total_failed = sum(s.get("failed", 0) for s in _universe_collector)
    # 마지막 stats 의 스냅샷 값 사용 (누적이 의미 없는 필드)
    last = _universe_collector[-1]
    kospi = last.get("kospi", 0)
    kosdaq = last.get("kosdaq", 0)
    securities = last.get("securities", 0)
    etf_excluded = last.get("etf_excluded", 0)

    logger.info(
        "[stock_master_universe_summary] window=300s universe=%d kospi=%d kosdaq=%d "
        "securities=%d etf_excluded=%d fetched=%d skipped_fresh=%d failed=%d",
        total_universe, kospi, kosdaq, securities, etf_excluded,
        total_fetched, total_skipped, total_failed,
    )

    _universe_collector.clear()


# ---------------------------------------------------------------------------
# 사이클 101 (2026-06-11) — 매일 20:00:05 전체 유니버스 적재 collector (사이클 74 패턴 답습)
# emit prefix: [full_universe_load_summary]
# 사이클 78 G-AST1 영속: record_* 에 대응 flush_* 호출 사이트 ≥1 의무
# ---------------------------------------------------------------------------
_full_universe_collector: list[dict] = []


def record_full_universe_load_summary(stats: dict) -> None:
    """사이클 101 — 전체 유니버스 적재 결과 1건 collector 적재.

    사이클 74 `record_stale_watcher_check` 패턴 직답습.

    Args:
        stats: summary dict. 권장 키:
            - total (int): 전체 ticker 수
            - kospi (int): KOSPI market_cap 페이징 누적 건수
            - kosdaq (int): KOSDAQ market_cap 페이징 누적 건수
            - securities (int): 보통주 필터 통과 건수
            - etf (int): ETF/리츠/SPAC 제외 건수
            - fetched (int): CTPF1002R upsert 건수
            - skipped_ttl (int): 24h TTL fresh skip 건수
            - failed (int): 실패 건수
            - elapsed_ms (int): 소요 시간 (ms)
    """
    _full_universe_collector.append(stats)


def flush_full_universe_load_collector() -> None:
    """사이클 101 — 전체 유니버스 적재 collector → 1행 emit + clear.

    사이클 74/78/89 패턴 직답습.
    빈 윈도우는 skip (사이클 76 Q2 답습).

    emit prefix:
      [full_universe_load_summary] total=N kospi=M kosdaq=K securities=L etf=J
      fetched=I skipped_ttl=H failed=G elapsed_ms=F
    """
    global _full_universe_collector
    if not _full_universe_collector:
        return  # 빈 윈도우 skip (사이클 76 Q2)

    # 마지막 stats 단일 행 (매일 1회 적재 = 1건이 정상)
    last = _full_universe_collector[-1]
    total = last.get("total", 0)
    kospi = last.get("kospi", 0)
    kosdaq = last.get("kosdaq", 0)
    securities = last.get("securities", 0)
    etf = last.get("etf", 0)
    fetched = last.get("fetched", 0)
    skipped_ttl = last.get("skipped_ttl", 0)
    failed = last.get("failed", 0)
    elapsed_ms = last.get("elapsed_ms", 0)

    logger.info(
        "[full_universe_load_summary] total=%d kospi=%d kosdaq=%d "
        "securities=%d etf=%d fetched=%d skipped_ttl=%d failed=%d elapsed_ms=%d",
        total, kospi, kosdaq, securities, etf, fetched, skipped_ttl, failed, elapsed_ms,
    )

    _full_universe_collector.clear()
