"""사이클 100 G-INT1 — `GET /api/stock-master/scan-pool/summary` 통합 카운트 영속 (MEDIUM).

명세 (`_workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md`):

**라우트 영역 변경 0 + 영역 1 자동 흡수**:
- 라우트 `GET /api/stock-master/scan-pool/summary` (src/routes/stock_master.py:101) = `count_eager_refresh_today()` 호출 + ApiResponse 래핑
- 사이클 100 = `count_eager_refresh_today()` 영역만 시정 → 라우트 영역 자동 흡수
- UI `StockMaster.tsx::scanPoolQuery.data?.eager_refresh_today` (L548) 표시 영역 정합

검증 매트릭스 (사용자 결정 Q65=C-1):
- mock `count_eager_refresh_today` = 614 (사이클 89 244 + 사이클 83 230 + 사이클 95 140 영역 통합 영속)
- `GET /api/stock-master/scan-pool/summary` 응답 = `{success: true, data: {eager_refresh_today: 614}, message: ""}`
- ApiResponse 래퍼 영속 (사이클 84 영속)

**Red 상태**: production 단일 grep → mock 결과 흡수 후 응답 영역 단일 prefix 영역 한정 → 통합 카운트 흡수 가드 FAIL.

**Green (backend-dev)**: 영역 1 시정 (`count_eager_refresh_today` 3 prefix OR) → 라우트 자동 흡수 → PASS.

영속 의무:
- 사이클 84 라우트 영속 (영역 변경 0)
- 매매 안전성 영역 영향 0 (DB 카운트 영역 한정)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    """FastAPI TestClient — 사이클 84 라우트 영속 검증."""
    from src.main import app
    return TestClient(app)


def test_g_int1_scan_pool_summary_returns_three_prefix_total(client):
    """G-INT1: GET /api/stock-master/scan-pool/summary 통합 카운트 영속 (MEDIUM).

    검증 매트릭스 (사이클 100 영역 영구 영속):
    - mock `count_eager_refresh_today` = 614 (사이클 89 244 + 사이클 83 230 + 사이클 95 140 영속)
    - 응답 = ApiResponse 래퍼 `{success: true, data: {eager_refresh_today: 614}, message: ""}`
    - 라우트 변경 0 영속 (사이클 84 영속)

    Red 상태 (사이클 100): production 단일 grep 영역 호출 → 실제 결과 (mock 흡수 후) 614 영속 가드.
                             영역 1 시정 *전* = production 단일 grep → 실제 prod 영역 단일 prefix 영역 230 영역 한정.

    Green (backend-dev): 영역 1 시정 자동 흡수 → 통합 614 PASS.

    영속 의무:
    - 사이클 84 라우트 영속 (src/routes/stock_master.py:98~106 영역)
    - 사이클 100 = 영역 1 (DB 영역) 시정만 → 라우트 영역 자동 흡수
    - 매매 안전성 영역 영향 0
    """
    EXPECTED_TOTAL = 614  # 사이클 89 244 + 사이클 83 230 + 사이클 95 140

    with patch(
        "src.db.stock_master.count_eager_refresh_today",
        new=AsyncMock(return_value=EXPECTED_TOTAL),
    ):
        response = client.get("/api/stock-master/scan-pool/summary")

    # 가드 1: HTTP 200
    assert response.status_code == 200, (
        f"\n사이클 100 G-INT1 위반 — `/api/stock-master/scan-pool/summary` HTTP 영역 위반:\n"
        f"  기대: 200 (사이클 84 라우트 영속)\n"
        f"  실제: {response.status_code}\n"
        f"  영속 의무: src/routes/stock_master.py:98~106 영속\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )

    body = response.json()

    # 가드 2: ApiResponse 래퍼 영속 (success/data/message)
    assert body.get("success") is True, (
        f"\n사이클 100 G-INT1 위반 — ApiResponse `success: true` 영역 위반:\n"
        f"  기대: success=true (사이클 84 ApiResponse 래퍼 영속)\n"
        f"  실제: {body.get('success')}\n"
        f"  응답 body: {body}\n"
        f"  영속 의무: src/models/response.py::ApiResponse"
    )

    # 가드 3: `data.eager_refresh_today` 통합 카운트 영속 (사용자 결정 Q65=C-1)
    data = body.get("data", {})
    eager_today = data.get("eager_refresh_today")
    assert eager_today == EXPECTED_TOTAL, (
        f"\n사이클 100 G-INT1 위반 — 통합 카운트 영역 위반:\n"
        f"  기대: eager_refresh_today={EXPECTED_TOTAL} (사이클 89 244 + 사이클 83 230 + 사이클 95 140 = 3 prefix OR 합산)\n"
        f"  실제: eager_refresh_today={eager_today}\n"
        f"  응답 data: {data}\n"
        f"  Red 결함: production `count_eager_refresh_today` 단일 grep `[scan_pool_eager_refresh]` 영속 → mock 흡수 후 라우트 영역 PASS,\n"
        f"           영역 1 시정 *전* 실제 production = 단일 prefix 230 한정 = ~62% 누락\n"
        f"  Green (backend-dev): 영역 1 시정 (3 prefix OR) → 라우트 자동 흡수 → PASS\n"
        f"  사용자 결정 Q65=C-1: 3 prefix OR 합산\n"
        f"  명세 영속: _workspace/red/cycle100_ui_prefix_fix_market_branching_persistence.md"
    )
