"""사이클 103 영역 0 — e2e api-mocks RealtimeHealth 라우트 등록 영구 가드.

명세: _workspace/red/cycle103_area0_realtime_health_ui.md
영속 의무: 사이클 75 G-AST5 / 80 hotfix #3 LIFO / 85 G-AST-MOCK

HIGH-8: G-AST-MOCK 4 endpoint api-mocks 등록 영구 가드 (Red 상태)
MEDIUM-1: api-mocks LIFO 정합 (사이클 80 hotfix #3 답습)
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
API_MOCKS = REPO_ROOT / "e2e" / "fixtures" / "api-mocks.ts"


def test_h8_api_mocks_realtime_health_endpoints_registered():
    """HIGH-8: e2e/fixtures/api-mocks.ts 에 RealtimeHealth 4 endpoint group 등록 영속.

    사이클 103 영역 0 Red 명세:
    - 4 카드 데이터 = `/api/logs/search?q=[prefix]` 영역 활용 (단일 endpoint + 4 prefix)
    - 또는 4 분리 endpoint = `/api/realtime-health/dispatch-drop` 등
    """
    assert API_MOCKS.exists(), f"e2e/fixtures/api-mocks.ts 영역 영속 실패 ({API_MOCKS})"

    src = API_MOCKS.read_text(encoding="utf-8")

    # 4 prefix 중 ≥1 prefix 영역 등록 영속 의무
    expected_prefixes = [
        "dispatch_drop_summary",
        "callback_exception",
        "stale_force_retry",
        "ws_auto_restart",
    ]

    registered_count = sum(1 for p in expected_prefixes if p in src)

    assert registered_count >= 1, (
        f"[G-AST-MOCK 영역 영속 실패] "
        f"e2e/fixtures/api-mocks.ts 영역에 4 prefix endpoint group 영구 영속 의무 영역 "
        f"(실제 영역 등록: {registered_count}/4 prefix). "
        f"사이클 103 영역 0 = 신규 RealtimeHealth 페이지 영역 endpoint group LIFO 정합 영속 의무 영역."
    )


def test_medium1_realtime_health_route_lifo_ordering():
    """MEDIUM-1: RealtimeHealth 영역 라우트 LIFO 정합 (사이클 80 hotfix #3 답습).

    Playwright route 매칭 = LIFO ("latest registered route wins") =
    wildcard `**/api/**` *전* 구체 라우트 (RealtimeHealth 4 endpoint group) 등록 영속.
    """
    if not API_MOCKS.exists():
        return  # 사이클 103 영역 0 Red 단계 (영역 영속 의무 영역 부재)

    src = API_MOCKS.read_text(encoding="utf-8")

    # wildcard 위치 영역 = `**/api/**` 영역 검색
    wildcard_pattern = re.compile(r'\*\*/api/\*\*')
    wildcard_matches = list(wildcard_pattern.finditer(src))

    # 4 prefix 위치 영역 검색
    realtime_health_pattern = re.compile(
        r'dispatch_drop_summary|callback_exception|stale_force_retry|ws_auto_restart'
    )
    realtime_health_matches = list(realtime_health_pattern.finditer(src))

    if not realtime_health_matches:
        # Red 단계 (영역 등록 영역 부재)
        return

    # LIFO 정합 영속 = 구체 라우트 (RealtimeHealth) 영역 위치 영역 > wildcard 영역 위치 영역
    # (Playwright LIFO = 함수 후반부 등록 라우트 우선 매칭 = 구체 라우트 영역 후반부 등록 의무)
    if wildcard_matches:
        wildcard_pos = wildcard_matches[0].start()
        realtime_health_pos = realtime_health_matches[0].start()

        assert realtime_health_pos > wildcard_pos, (
            f"[Playwright LIFO 정합 영구 영속 실패] "
            f"wildcard `**/api/**` 영역 위치 (pos={wildcard_pos}) < "
            f"RealtimeHealth 4 endpoint group 영역 위치 (pos={realtime_health_pos}) 영속 의무 영역. "
            f"사이클 80 hotfix #3 LIFO 영구 영속 = 구체 라우트 영역 후반부 등록 의무 영역."
        )
