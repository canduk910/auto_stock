"""사이클 90 L-1 (LOW) — KST 영속 (사이클 68 답습).

Red 명세 (`_workspace/red/cycle90_manual_refresh_universe_api.md`):

POST refresh-universe 응답 영역에서 timestamp 영구 영속 영역 무영향 검증.
사이클 68 KST 일관성 영속 — refresh 트리거는 단순 응답 영역이므로
timestamp 자체 생성 0건 (elapsed_ms 외 시각 키 0건).

기대 동작 (Green, 사이클 90):
- 응답 data 에 elapsed_ms 외 시각 ISO string 0건
- 미래 timestamp 키 도입 시도 timezone=Asia/Seoul 의무 (영속 가드)

Red 상태: production 코드 0 → 404.

위험 등급 LOW (사이클 68 영속 영역 정합).

영속 의무:
- 사이클 68 KST 영속 영역 변경 0
- `src/db/_kst.py` 헬퍼 영속 영역 무영향
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


def test_l1_response_no_unexpected_timestamp_keys(monkeypatch):
    """L-1: 응답 data 영역에 elapsed_ms 외 시각 ISO string 키 0건.

    사이클 68 KST 영속 — refresh 트리거 응답은 단순 통계 영역 (universe + elapsed_ms)
    + 시각 키 도입 0건. 미래 timestamp 키 도입 시 timezone=Asia/Seoul 의무 (영속 가드).
    """
    from src.engine import scanner

    monkeypatch.setattr(
        scanner, "fetch_top_500_universe", AsyncMock(return_value=["005930"]), raising=False
    )

    from src.main import app
    client = TestClient(app)
    res = client.post("/api/stock-master/refresh-universe")
    assert res.status_code == 200, (
        f"POST 200 의무 (실제 {res.status_code}) — backend-dev Green 단계 미작성"
    )
    body = res.json()
    data = body["data"]
    assert isinstance(data, dict), f"data 가 dict 의무 (실제 {type(data).__name__})"

    # 사이클 68 영속: 시각 ISO 키 0건 (universe + elapsed_ms 만 의무)
    # 미래 timestamp 키 도입 시 timezone=Asia/Seoul 의무 영속 가드
    expected_keys = {"universe", "elapsed_ms"}
    actual_keys = set(data.keys())
    assert actual_keys == expected_keys, (
        f"응답 data 키 집합 미일치 (예상 {expected_keys}, 실제 {actual_keys}) — "
        "사이클 68 영속 영역 변경 (시각 키 도입 시 timezone=Asia/Seoul 의무)"
    )

    # ISO timestamp 패턴 사전 검출 (`+09:00` 시각 키 도입 차단)
    body_text = res.text
    iso_kst_count = body_text.count("+09:00")
    iso_utc_count = body_text.count("+00:00") + body_text.count("Z\"")  # ISO UTC
    assert iso_utc_count == 0, (
        f"UTC ISO timestamp 검출 ({iso_utc_count}건) — 사이클 68 KST 영속 위반"
    )
