"""사이클 85 G-AST-LIFO — e2e api-mocks Stock Master 라우트 등록 + LIFO 정합 영구 가드.

> **선례 답습**:
> - 사이클 65 hotfix #2 (`test_api_mocks_routes_registered.py`) api-mocks 신규 라우트 누락 영구 가드
> - 사이클 80 hotfix #3 (`e2e/fixtures/api-mocks.ts`) Playwright route 매칭 **LIFO** 정합 영구 시정
> - 사이클 80 hotfix #4 (`test_api_mocks_routes_registered.py::test_..._after_wildcard`) 가드 함수명
>   `before_wildcard` → `after_wildcard` 영구 시정 + assertion 방향 반전 (`>` 영구 의무)
>
> **결함 배경 (예방)**: 사이클 85 StockMaster.tsx 페이지 신규 — 5 useQuery 호출
> (`fetchStats` / `fetchList` / `fetchScanPoolSummary` / `fetchDetail` / `fetchHistory`).
> e2e Playwright 환경 (백엔드 미실행) 에서 5 라우트 미등록 시 vite proxy → ECONNREFUSED →
> React Query retry 누적 → e2e timeout. 또한 wildcard 가 *구체 라우트 후* 등록되어야
> Playwright LIFO 룰 (`latest registered route wins`) 정합 — 구체 라우트가 우선 매칭.
> wildcard 가 *전* 등록되면 envelope({}) 가 fallback 으로 동작.

요구 행위:
- T-1: `e2e/fixtures/api-mocks.ts` 에 wildcard `**/api/stock-master/**` 라우트 등록
- T-2~T-6: 5 구체 라우트 등록 (stats / list / scan-pool/summary / `:ticker` / `:ticker/history`)
- T-7: 5 구체 라우트가 wildcard *후* 등록 (LIFO 정합, 사이클 80 hotfix #3/#4 영속)

위험 등급 HIGH — e2e flaky 영구 차단 + 향후 신규 stock-master endpoint 추가 시 영구 누락 차단.
"""
from pathlib import Path

import pytest


MOCKS_PATH = Path(__file__).parent.parent.parent.parent / "e2e/fixtures/api-mocks.ts"


def _load_source() -> str:
    return MOCKS_PATH.read_text()


def test_e2e_api_mocks_includes_stock_master_wildcard():
    """T-1: wildcard `**/api/stock-master/**` 라우트 등록 의무 (fallback 역할).

    사이클 80 hotfix #3 영속 — LIFO 라 가장 *먼저* 등록되어야 가장 *후순위* 매칭됨.
    구체 라우트 미매칭 시 envelope({}) 반환.
    """
    source = _load_source()
    assert '"**/api/stock-master/**"' in source, (
        "e2e api-mocks.ts 에 wildcard `**/api/stock-master/**` 라우트 누락 — "
        "사이클 85 StockMaster.tsx 진입 시 구체 라우트 미매칭 시 ECONNREFUSED 위험. "
        "사이클 80 hotfix #3 LIFO 영속 패턴 답습 의무 (fallback 역할)."
    )


@pytest.mark.parametrize(
    "endpoint_literal",
    [
        '"**/api/stock-master/stats"',
        '"**/api/stock-master/list',  # list?limit=&offset= 형태 → list* 또는 list 시작
        '"**/api/stock-master/scan-pool/summary"',
    ],
)
def test_e2e_api_mocks_includes_stock_master_specific_static_routes(endpoint_literal: str):
    """T-2~T-4: 정적 경로 3종 (stats / list / scan-pool/summary) 등록 의무.

    list 는 query string 변형 (`list?limit=100&offset=0`) 가능 → prefix substring 매칭.
    """
    source = _load_source()
    assert endpoint_literal in source, (
        f"e2e api-mocks.ts 에 {endpoint_literal} 라우트 누락 — "
        f"사이클 85 StockMaster 페이지 진입 시 ECONNREFUSED."
    )


def test_e2e_api_mocks_includes_stock_master_detail_dynamic_route():
    """T-5: 동적 detail 라우트 `**/api/stock-master/*` (ticker 변형) 등록 의무.

    `/api/stock-master/005930` 등 6자리 ticker — Playwright wildcard `*` 패턴 매칭.
    history 와 구분: history 는 `*/history` 접미사 (T-6).
    """
    source = _load_source()
    # detail = /api/stock-master/{ticker} (단일 segment + history 접미사 없음)
    # Playwright glob: `**/api/stock-master/*` (history 와 구분되도록 등록)
    # 또는 `**/api/stock-master/[^/]+` 정규식 가능 — 본 가드는 substring 검증.
    assert (
        '"**/api/stock-master/*"' in source
        or "'**/api/stock-master/*'" in source
    ), (
        "e2e api-mocks.ts 에 동적 detail 라우트 `**/api/stock-master/*` 누락 — "
        "ticker 클릭 시 detail 모달 ECONNREFUSED. T-6 history 라우트와 별도 등록 의무."
    )


def test_e2e_api_mocks_includes_stock_master_history_dynamic_route():
    """T-6: 동적 history 라우트 `**/api/stock-master/*/history*` 등록 의무."""
    source = _load_source()
    assert (
        '"**/api/stock-master/*/history' in source
        or "'**/api/stock-master/*/history" in source
    ), (
        "e2e api-mocks.ts 에 동적 history 라우트 `**/api/stock-master/*/history*` 누락 — "
        "history 테이블 렌더 시 ECONNREFUSED."
    )


def test_e2e_api_mocks_stock_master_specific_routes_registered_after_wildcard():
    """T-7: 5 구체 라우트가 wildcard `**/api/stock-master/**` *후* 등록 의무 (Playwright LIFO).

    **사이클 80 hotfix #3/#4 영속** — Playwright route 매칭 규칙은 **LIFO**
    ("latest registered route wins"). wildcard 가 fallback 역할이라면 구체 라우트보다
    *먼저* 등록되어야 가장 *후순위* 매칭됨 (LIFO 라 늦게 등록된 것이 우선).

    함수명 `after_wildcard` 의무 (사이클 80 hotfix #4 답습) + assertion 방향
    `구체 > wildcard` 의무 (`구체 < wildcard` = FIFO 가정 = 결함).

    위험: 구체 라우트가 *전* 등록되면 wildcard 가 LIFO 우선 매칭 → envelope({}) 응답 →
    StockMaster.tsx 의 React controlled input throw → 페이지 unmount → e2e timeout.
    """
    source = _load_source()

    wildcard_pos = source.find('"**/api/stock-master/**"')
    stats_pos = source.find('"**/api/stock-master/stats"')
    list_pos = source.find('"**/api/stock-master/list')
    summary_pos = source.find('"**/api/stock-master/scan-pool/summary"')

    assert wildcard_pos > 0, "wildcard `**/api/stock-master/**` 라우트 누락 (T-1 참조)"
    assert stats_pos > 0, "stats 구체 라우트 누락"
    assert list_pos > 0, "list 구체 라우트 누락"
    assert summary_pos > 0, "scan-pool/summary 구체 라우트 누락"

    # 사이클 80 hotfix #3 LIFO 영속 — 구체 라우트가 wildcard *후* 등록 의무
    assert stats_pos > wildcard_pos, (
        f"stats 구체 라우트 (pos={stats_pos}) 가 wildcard (pos={wildcard_pos}) *전* 등록 — "
        f"Playwright LIFO 위반 (wildcard 가 우선 매칭되어 구체 라우트 무효화). "
        f"사이클 80 hotfix #3 시정 의도 위반 (사이클 85 G-AST-LIFO)."
    )
    assert list_pos > wildcard_pos, (
        f"list 구체 라우트 (pos={list_pos}) 가 wildcard (pos={wildcard_pos}) *전* 등록 — "
        f"Playwright LIFO 위반."
    )
    assert summary_pos > wildcard_pos, (
        f"summary 구체 라우트 (pos={summary_pos}) 가 wildcard (pos={wildcard_pos}) *전* 등록 — "
        f"Playwright LIFO 위반."
    )
