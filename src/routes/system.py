"""시스템 진단 라우트: /api/system/*

- memory: 프로세스 RSS/VMS + (선택) tracemalloc top 20
- metrics: endpoint별 호출 횟수 + 응답시간 분포 (p50/p95/p99)
"""

from __future__ import annotations

import logging
import os
import sys
import tracemalloc

from fastapi import APIRouter

from src.models.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/memory", response_model=ApiResponse)
async def memory_status():
    """프로세스 메모리 사용량 조회.

    psutil로 RSS/VMS 측정. MEMORY_PROFILE=true 환경변수 시 tracemalloc top 20 함께 반환.
    """
    try:
        import psutil
    except ImportError:
        return ApiResponse(success=False, message="psutil 미설치 — requirements.txt 확인")

    proc = psutil.Process()
    info = proc.memory_info()
    data: dict = {
        "rss_mb": round(info.rss / 1024 / 1024, 2),
        "vms_mb": round(info.vms / 1024 / 1024, 2),
        "num_threads": proc.num_threads(),
        "open_files": len(proc.open_files()),
        "connections": len(proc.net_connections(kind="inet")),
    }

    if tracemalloc.is_tracing():
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics("lineno")[:20]
        data["tracemalloc_top20"] = [
            {
                "file": str(s.traceback[0].filename),
                "line": s.traceback[0].lineno,
                "size_kb": round(s.size / 1024, 2),
                "count": s.count,
            }
            for s in top_stats
        ]
    else:
        data["tracemalloc"] = "disabled (set MEMORY_PROFILE=true to enable)"

    data["python_version"] = sys.version.split()[0]
    return ApiResponse(success=True, data=data)


@router.get("/metrics", response_model=ApiResponse)
async def endpoint_metrics():
    """endpoint별 응답시간 분포 (p50/p95/p99) + 호출 횟수.

    `MetricsMiddleware`가 누적한 통계를 반환.
    """
    from src.main import _endpoint_metrics

    summary: dict[str, dict] = {}
    for path, samples in _endpoint_metrics.items():
        if not samples:
            continue
        sorted_ms = sorted(samples)
        n = len(sorted_ms)
        p50 = sorted_ms[int(n * 0.50)] if n else 0
        p95 = sorted_ms[int(n * 0.95)] if n else 0
        p99 = sorted_ms[min(int(n * 0.99), n - 1)] if n else 0
        summary[path] = {
            "count": n,
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
            "max_ms": round(max(sorted_ms), 2) if n else 0,
            "min_ms": round(min(sorted_ms), 2) if n else 0,
        }

    return ApiResponse(success=True, data={
        "endpoints": summary,
        "tracemalloc_active": tracemalloc.is_tracing(),
        "memory_profile_env": os.environ.get("MEMORY_PROFILE", "false"),
    })


@router.post("/metrics/reset", response_model=ApiResponse)
async def reset_metrics():
    """누적 metrics 초기화 (실험 시작 시 베이스라인 리셋용)."""
    from src.main import _endpoint_metrics

    cleared = sum(len(v) for v in _endpoint_metrics.values())
    _endpoint_metrics.clear()
    return ApiResponse(success=True, message=f"{cleared}개 샘플 초기화")
