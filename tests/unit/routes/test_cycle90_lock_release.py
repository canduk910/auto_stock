"""사이클 90 M-3 (MEDIUM) — Lock release 정합 (예외 시도 release).

Red 명세 (`_workspace/red/cycle90_manual_refresh_universe_api.md`):

`async with _refresh_universe_lock:` 컨텍스트 매니저로 정상 release 보장.
fetch_top_500_universe() 가 예외 raise 시도 Lock release 의무 (다음 호출
영구 차단 방지).

기대 동작 (Green, 사이클 90):
- 첫 번째 호출 = 예외 발생 (500 또는 graceful)
- Lock 정상 release
- 두 번째 호출 = 정상 200 (Lock 영구 잠금 차단)

Red 상태: production 코드 0 → 모두 404.

위험 등급 MEDIUM (Lock 영구 잠금 silent 결함 차단).

영속 의무:
- Q25=A async with 컨텍스트 매니저 영속 (try/finally 우회 차단)
- 사이클 89 graceful 영속 (KIS 실패 시 [] 반환, 예외 raise 아님)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q69=B — `fetch_top_500_universe` 영구 폐기 "
        "(POST /refresh-universe 라우트 대상 함수). "
        "사이클 90 시점 Lock release 예외 시도 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_m3_lock_releases_after_exception_in_fetch(monkeypatch):
    """M-3: fetch_top_500_universe 가 예외 raise 시도 Lock release.

    `async with _refresh_universe_lock:` 컨텍스트 매니저 의무.
    두 번째 호출은 Lock 정상 release 후 200 가능.
    """
    from src.engine import scanner
    from src.routes import stock_master as sm_route

    # 첫 번째 호출 — 예외 raise
    call_count = {"n": 0}

    async def _fetch_raises_then_succeeds():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated KIS 5xx")
        return ["005930"]

    monkeypatch.setattr(
        scanner, "fetch_top_500_universe", _fetch_raises_then_succeeds, raising=False
    )

    from src.main import app
    client = TestClient(app)

    # 첫 번째 호출 — 예외 발생 (500 또는 graceful 처리)
    res1 = client.post("/api/stock-master/refresh-universe")
    # 500 (FastAPI default 예외 처리) 또는 graceful 200 (사이클 89 영속 패턴 답습 시) 둘 다 허용
    assert res1.status_code in (200, 500), (
        f"첫 번째 호출 200 또는 500 의무 (실제 {res1.status_code}, body={res1.text[:200]})"
    )

    # Lock release 영속 — 잠금 상태 0 의무
    assert not sm_route._refresh_universe_lock.locked(), (
        "예외 발생 후 Lock 잠금 잔존 — `async with` 컨텍스트 매니저 release 미작동. "
        "Lock 영구 잠금 silent 결함 (다음 호출 영구 409)"
    )

    # 두 번째 호출 — Lock release 후 정상 200
    res2 = client.post("/api/stock-master/refresh-universe")
    assert res2.status_code == 200, (
        f"Lock release 후 호출 200 의무 (실제 {res2.status_code}) — "
        "Lock 영구 잠금 silent 결함 가능"
    )
