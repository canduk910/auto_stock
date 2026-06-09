"""사이클 90 H-2 (HIGH) — Q25=A asyncio.Lock + 409 Conflict 동시 호출 가드.

Red 명세 (`_workspace/red/cycle90_manual_refresh_universe_api.md`):

사용자 결정 Q25=A: 단일 in-flight 가드 (asyncio.Lock + 409 Conflict). 사용자
더블 클릭 / 다중 탭 시 KIS Rate Limit 폭주 차단 + 25초 작업 중복 차단.

기대 동작 (Green, 사이클 90):
- 첫 번째 호출 = 200 + 정상 응답
- in-flight 중 두번째 호출 = 즉시 409 Conflict
- Lock release 후 세 번째 호출 = 200 (정상 복귀)

Red 상태 (사이클 90): production 코드 0 (라우트 + Lock 미존재) → 모두 404.

위험 등급 HIGH (KIS Rate Limit 폭주 차단 + UX 명확).

영속 의무:
- 사이클 80 hotfix #3 LIFO 영속 (라우트 등록 영역 영향 0)
- 사이클 84 Q9=B 영속 (POST 1개 예외 허용)
- 사이클 89 [stock_master_bulk_refresh] emit 영속
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def slow_fetch_client(monkeypatch):
    """fetch_top_500_universe 가 0.5s 대기하는 mock — Lock 동시 호출 시나리오."""
    from src.engine import scanner

    async def _slow_fetch():
        await asyncio.sleep(0.5)
        return ["005930", "402340"]

    monkeypatch.setattr(
        scanner, "fetch_top_500_universe", _slow_fetch, raising=False
    )

    from src.main import app
    return TestClient(app)


def test_h2_concurrent_post_returns_409_when_locked(slow_fetch_client):
    """H-2: in-flight 중 두번째 POST 호출 시 409 Conflict.

    asyncio.Lock 영속 패턴 — first call 진행 중 second call 즉시 409.

    동시 호출 시뮬레이션:
    - TestClient sync 모드라 정확한 in-flight race 재현은 한계 (별도 thread 필요)
    - 본 케이스 = Lock 자체의 존재 + 응답 분기 정합성 검증
    """
    import threading

    from src.routes import stock_master as sm_route

    # 모듈 레벨 Lock 영속 의무 확인
    assert hasattr(sm_route, "_refresh_universe_lock"), (
        "`_refresh_universe_lock` 모듈 레벨 인스턴스 부재 — "
        "Q25=A in-flight 가드 미구현. backend-dev Green 단계 의무."
    )
    lock = sm_route._refresh_universe_lock
    assert isinstance(lock, asyncio.Lock), (
        f"_refresh_universe_lock = asyncio.Lock 의무 (실제 {type(lock).__name__})"
    )

    # 두 thread 로 동시 호출 — 첫 번째 = 200 / 두 번째 = 409 또는 200 (race 시점)
    results = []

    def _call():
        res = slow_fetch_client.post("/api/stock-master/refresh-universe")
        results.append(res.status_code)

    t1 = threading.Thread(target=_call)
    t2 = threading.Thread(target=_call)
    t1.start()
    # 1ms 차이로 두 번째 호출 — 첫 번째 가 Lock 잡은 후 진입
    import time as _time
    _time.sleep(0.05)
    t2.start()
    t1.join(timeout=2.0)
    t2.join(timeout=2.0)

    # 정합성: 두 호출 모두 응답 완료 + 적어도 하나는 200 + 하나는 409
    # (race 정확 재현은 production code 가 구현되면 결정적, Red 단계는 0건)
    assert len(results) == 2, f"두 호출 응답 누락 (실제 {len(results)}건 = {results})"
    success_count = sum(1 for s in results if s == 200)
    conflict_count = sum(1 for s in results if s == 409)
    assert success_count + conflict_count == 2, (
        f"각 호출은 200 또는 409 만 의무 (실제 {results}) — "
        "다른 status_code 검출 시 Lock + 409 분기 미구현"
    )
    # 동시 호출 시 정확히 한 호출은 409 Conflict 의무 (in-flight 중 차단)
    assert conflict_count >= 1, (
        f"동시 호출 시 적어도 한 호출은 409 Conflict 의무 (실제 {results}) — "
        "Q25=A in-flight 가드 미작동"
    )


def test_h2_post_after_release_returns_200(slow_fetch_client):
    """H-2-bis: Lock release 후 다음 호출은 정상 200.

    `async with _refresh_universe_lock:` 영속 컨텍스트 매니저로 정상 release 보장.
    예외 발생 시도 동일 (M-3 영역).
    """
    # 첫 번째 호출 (Lock 진입 → 0.5s 후 release)
    res1 = slow_fetch_client.post("/api/stock-master/refresh-universe")
    assert res1.status_code == 200, (
        f"첫 번째 호출 200 의무 (실제 {res1.status_code}, body={res1.text[:200]})"
    )

    # 두 번째 호출 (Lock 해제 후 진입 → 정상)
    res2 = slow_fetch_client.post("/api/stock-master/refresh-universe")
    assert res2.status_code == 200, (
        f"Lock release 후 호출 200 의무 (실제 {res2.status_code}, body={res2.text[:200]}) — "
        "`async with` 컨텍스트 매니저 release 미작동"
    )
