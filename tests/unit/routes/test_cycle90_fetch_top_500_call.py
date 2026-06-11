"""사이클 90 H-4 (HIGH) — fetch_top_500_universe() 호출 정합 (사이클 89 영속).

Red 명세 (`_workspace/red/cycle90_manual_refresh_universe_api.md`):

POST `/refresh-universe` 가 사이클 89 영속 영역 `fetch_top_500_universe()` 를
정확히 호출 + 결과 ticker 수를 universe 응답 키에 반영.

기대 동작 (Green, 사이클 90):
- POST 호출 시 fetch_top_500_universe await 1회
- 반환된 ticker list 의 len() = universe 응답값
- 빈 list 결과 시 universe=0 (KIS 실패 graceful, 사이클 89 영속)

Red 상태 (사이클 90): production 코드 0 → POST 라우트 미존재 → 404.

위험 등급 HIGH (사이클 89 영속 영역 정합 + 운영 효과 보장).

영속 의무:
- 사이클 89 fetch_top_500_universe 영속 (KOSPI 250 + KOSDAQ 250 분리 호출)
- 사이클 89 graceful 영속 (KIS 실패 시 [] 반환)
- 사이클 38 명문화 영속 (영역 무관)
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q69=B — `fetch_top_500_universe` 영구 폐기 "
        "(POST /refresh-universe 라우트 대상 함수). "
        "사이클 90 시점 1회 호출 정합 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_h4_fetch_top_500_universe_called_once_with_count_reflected(monkeypatch):
    """H-4: POST 호출 시 fetch_top_500_universe 1회 await + universe = len(result).

    mock 결과 5 ticker → universe=5 응답 의무.
    """
    from src.engine import scanner

    mock = AsyncMock(return_value=["005930", "402340", "035720", "000660", "035420"])
    monkeypatch.setattr(scanner, "fetch_top_500_universe", mock, raising=False)

    from src.main import app
    client = TestClient(app)
    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 200, (
        f"POST 200 의무 (실제 {res.status_code}, body={res.text[:200]}) — "
        "backend-dev Green 단계 라우트 미작성"
    )
    body = res.json()
    assert body["success"] is True
    assert body["data"]["universe"] == 5, (
        f"universe = mock ticker 수 (5) 의무, 실제 {body['data']['universe']} — "
        "fetch_top_500_universe 호출 결과 미반영"
    )

    # 정확히 1회 호출 의무
    assert mock.call_count == 1, (
        f"fetch_top_500_universe 1회 호출 의무, 실제 {mock.call_count}회 — "
        "라우트가 중복 호출하거나 미호출"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "사이클 101 Q69=B — `fetch_top_500_universe` 영구 폐기 "
        "(POST /refresh-universe 라우트 대상 함수). "
        "사이클 90 시점 빈 universe graceful 검증 의도 영속 보존 (사이클 66 K-2 패턴 답습)."
    ),
)
def test_h4_empty_universe_graceful_returns_zero(monkeypatch):
    """H-4-bis: KIS 실패 시 [] graceful 영속 → universe=0 응답.

    사이클 89 graceful 영속 패턴: `fetch_top_500_universe` 가 [] 반환 시
    라우트는 200 + universe=0 응답 (사용자에게 명확한 0건 신호).
    """
    from src.engine import scanner

    monkeypatch.setattr(
        scanner, "fetch_top_500_universe", AsyncMock(return_value=[]), raising=False
    )

    from src.main import app
    client = TestClient(app)
    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 200, (
        f"빈 universe 시도 200 의무 (graceful) — 실제 {res.status_code}"
    )
    body = res.json()
    assert body["data"]["universe"] == 0, (
        f"빈 universe = 0 의무, 실제 {body['data']['universe']}"
    )
