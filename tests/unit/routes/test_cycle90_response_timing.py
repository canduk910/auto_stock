"""사이클 90 M-2 (MEDIUM) — elapsed_ms 응답 timing 검증.

Red 명세 (`_workspace/red/cycle90_manual_refresh_universe_api.md`):

응답 data.elapsed_ms 가 fetch_top_500_universe() 의 실제 소요 시간 (ms 단위)
을 정확히 반영. 운영 환경 ~25초 작업 영역 정합.

기대 동작 (Green, 사이클 90):
- 100ms 대기 mock → elapsed_ms >= 100
- 정상 종료 시 elapsed_ms 양수
- 예외 발생 시 elapsed_ms 미응답 (M-3 영역)

Red 상태: production 코드 0 → 404.

위험 등급 MEDIUM (운영 가시화 + UX 정합).

영속 의무:
- 사이클 89 영속 영역 정합 (KIS 호출 timing 가시화)
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def test_m2_elapsed_ms_reflects_actual_timing(monkeypatch):
    """M-2: 100ms 대기 mock → elapsed_ms >= 100 응답 반영.

    `time.monotonic()` 기반 elapsed 측정 영속 의무.
    """
    from src.engine import scanner

    async def _slow_fetch():
        await asyncio.sleep(0.1)  # 100ms
        return ["005930"]

    monkeypatch.setattr(scanner, "fetch_top_500_universe", _slow_fetch, raising=False)

    from src.main import app
    client = TestClient(app)
    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 200, (
        f"200 의무 (실제 {res.status_code}) — backend-dev Green 단계 미작성"
    )
    body = res.json()
    elapsed_ms = body["data"]["elapsed_ms"]
    assert elapsed_ms >= 100, (
        f"elapsed_ms >= 100 의무 (100ms sleep mock), 실제 {elapsed_ms} — "
        "time.monotonic 기반 timing 측정 미작동 또는 0 반환"
    )
    # 상한도 확인 — 비정상 큰 값 (1초 이상) 시 timing 측정 결함 의심
    assert elapsed_ms < 5000, (
        f"elapsed_ms < 5000 의무 (100ms 작업), 실제 {elapsed_ms} — "
        "비정상 timing 측정 (정상 ~100~500ms 영역)"
    )
