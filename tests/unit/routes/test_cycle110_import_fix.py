"""사이클 110 HIGH-1 (G-IMPORT1) — refresh_universe_now 가 _full_universe_load_once 호출.

Red 명세 (`_workspace/red/cycle110_silent_defect_fix.md`):

사이클 101 (Q68=A+Q69=B) `fetch_top_500_universe` + `_universe_eager_refresh_loop` 영구 폐기
시점에 `src/routes/stock_master.py:52-54` import 영역 영구 영속이 동행 시정 누락
silent 결함 영역 영구 영속이. 사이클 110 시정 영역 영구 영속이 = `_full_universe_load_once`
영역 영구 영속이 단일 호출 (사이클 101 영역 영구 영속이 정상 함수 영역).

위험 등급 HIGH (silent 결함 영구 영속이 + 운영자 100% 실패 영역).

영속 의무:
- 사이클 101 영속 (`_full_universe_load_once` 영역 영구 영속이 24h TTL idempotency)
- 사이클 38 명문화 영속 (scanner 단계 = 매수 진입 전용)
- 사이클 88 G-REJECT 영속 (재구독 영역 폐기 금지)
- 사이클 106 영속 (lifecycle race 차단 영역 영구 영속이)
- 사이클 107 영속 (raw 보강 의존성 해소 영역 영구 영속이)
- 사이클 109 영속 (market-cap 화이트리스트 영역 영구 영속이)
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_full_universe_load_once(monkeypatch):
    """`_full_universe_load_once` mock 영역 영구 영속이 — 사이클 101 영역 정상 함수 영역 격리."""
    from src.engine import scanner

    mock = AsyncMock(return_value={
        "total": 2800,
        "kospi": 1400,
        "kosdaq": 1400,
        "securities": 2700,
        "etf": 100,
        "fetched": 2750,
        "skipped_ttl": 50,
        "failed": 0,
        "elapsed_ms": 180_000,
    })
    monkeypatch.setattr(scanner, "_full_universe_load_once", mock, raising=False)
    return mock


def test_g_import1_post_refresh_universe_calls_full_universe_load_once(
    mock_full_universe_load_once,
):
    """G-IMPORT1: POST `/refresh-universe` 영역 영구 영속이 가 `_full_universe_load_once` 호출 영역.

    사이클 101 (Q68=A+Q69=B) 영역 영구 영속이 `fetch_top_500_universe` +
    `_universe_eager_refresh_loop` 영구 폐기 → 사이클 110 시정 영역 영구 영속이 =
    `_full_universe_load_once` 단일 호출 (사이클 101 영역 정상 함수 영역).
    """
    from src.main import app
    client = TestClient(app)

    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 200, (
        f"POST refresh-universe 200 의무 (실제 {res.status_code}, body={res.text[:200]}) — "
        "사이클 110 시정 영역 영구 영속이 미적용"
    )

    # `_full_universe_load_once` 정확히 1회 호출 의무 영역 영구 영속이
    assert mock_full_universe_load_once.call_count == 1, (
        f"_full_universe_load_once 1회 호출 의무, 실제 {mock_full_universe_load_once.call_count}회 — "
        "사이클 110 시정 영역 영구 영속이 라우트가 중복 호출하거나 미호출"
    )


@pytest.mark.xfail(
    strict=False,
    reason="사이클 127 fire-and-forget BackgroundTasks 전환 — 동기 응답 schema 의미 폐기 (사이클 66 K-2 패턴)",
)
def test_g_import1_response_universe_equals_total(mock_full_universe_load_once):
    """G-IMPORT1-bis: universe 응답 키 영역 영구 영속이 = `summary["total"]` (사이클 89 호환 영속).

    사이클 110 응답 영역 영구 영속이 = summary 9 키 중 운영자 관심 7 키 노출:
    - universe (≡ summary["total"], 사이클 89 영역 영속 호환)
    - elapsed_ms + fetched + skipped_ttl + failed + kospi + kosdaq
    """
    from src.main import app
    client = TestClient(app)

    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 200

    body = res.json()
    assert body["success"] is True
    assert body["data"]["universe"] == 2800, (
        f"universe = summary['total'] (2800) 의무, 실제 {body['data']['universe']}"
    )
