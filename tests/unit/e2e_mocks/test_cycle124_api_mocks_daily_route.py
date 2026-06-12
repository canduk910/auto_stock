"""사이클 124 G-AST-LIFO / G-AST-MOCK — e2e api-mocks 일봉 라우트 등록 + LIFO 정합 영구 가드.

> **선례 답습**:
> - 사이클 85 `test_cycle85_api_mocks_stock_master_lifo.py` — Stock Master 5 라우트 LIFO 가드
> - 사이클 80 hotfix #3/#4 — Playwright LIFO 정합 (wildcard 먼저 등록 = LIFO 라 후순위 매칭)
>
> **결함 배경 (예방)**:
> 사이클 124 Q1=A — DetailModal 일봉 탭 신규 (`GET /api/stock-master/{ticker}/daily?days=30`).
> `**/api/stock-master/*/history*` 와 패턴 유사 — Playwright LIFO 에서 등록 순서가
> 매칭 우선순위를 결정한다.
> - `*/daily*` 가 `*/history*` *전* 등록 → `*/history*` 가 LIFO 우선 → daily 호출이
>   history 응답을 받을 위험.
> - `*/daily*` 가 wildcard `**/api/stock-master/**` *전* 등록 → wildcard 가 LIFO 우선 →
>   envelope({}) 응답 → DailyTab 렌더 실패.
>
> **해법** (사이클 80 hotfix #3 패턴 영속):
> wildcard 가장 *먼저* 등록 → 구체 라우트들 *후* 등록 순서:
> 1. wildcard `**/api/stock-master/**`   (fallback, 먼저)
> 2. `**/api/stock-master/stats`         (구체, 후)
> 3. `**/api/stock-master/list*`         (구체, 후)
> 4. `**/api/stock-master/scan-pool/summary` (구체, 후)
> 5. `**/api/stock-master/*/history*`    (구체, 후)
> 6. `**/api/stock-master/*/daily*`      (구체, history 후 등록 → LIFO 라 우선)
> 7. `**/api/stock-master/*`             (구체 catch-all, 후)
> 8. `**/api/stock-master/refresh-universe` (구체, 후)

위험 등급 HIGH — 사이클 124 Q1=A DailyTab e2e 환경 정합성 영구 차단.
"""
from pathlib import Path

import pytest


MOCKS_PATH = Path(__file__).parent.parent.parent.parent / "e2e/fixtures/api-mocks.ts"


def _load_source() -> str:
    return MOCKS_PATH.read_text()


def test_g_ast_mock_daily_route_registered():
    """G-AST-MOCK: `**/api/stock-master/*/daily*` 라우트가 api-mocks.ts 에 등록되어 있는지 확인.

    사이클 124 Q1=A — DetailModal 일봉 탭 신규. Playwright 환경에서 해당 라우트 미등록 시
    `/api/stock-master/005930/daily?days=30` 요청이 백엔드로 전달 → ECONNREFUSED →
    React Query retry 누적 → e2e timeout.
    """
    source = _load_source()
    assert (
        '"**/api/stock-master/*/daily' in source
        or "'**/api/stock-master/*/daily" in source
    ), (
        "e2e api-mocks.ts 에 daily 라우트 `**/api/stock-master/*/daily*` 누락 — "
        "사이클 124 Q1=A DetailModal 일봉 탭 신규 시 ECONNREFUSED 위험. "
        "사이클 85 G-AST-MOCK 패턴 답습 의무."
    )


def test_g_ast_lifo_daily_registered_after_wildcard():
    """G-AST-LIFO (1/2): `*/daily*` 가 wildcard `**/api/stock-master/**` *후* 등록 의무.

    Playwright LIFO 규칙: 나중에 등록된 라우트가 우선 매칭.
    wildcard 가 fallback 역할이라면 구체 라우트보다 *먼저* 등록 (= 소스코드 상 앞 위치)
    되어야 LIFO 에서 *후순위* 매칭이 된다.

    사이클 80 hotfix #3/#4 영속 — assertion 방향: `daily_pos > wildcard_pos`.
    """
    source = _load_source()

    wildcard_pos = source.find('"**/api/stock-master/**"')
    daily_pos = source.find('"**/api/stock-master/*/daily')
    if daily_pos == -1:
        daily_pos = source.find("'**/api/stock-master/*/daily")

    assert wildcard_pos > 0, "wildcard `**/api/stock-master/**` 라우트 누락 (사이클 85 T-1 참조)"
    assert daily_pos > 0, "daily 라우트 `**/api/stock-master/*/daily*` 누락 (G-AST-MOCK 참조)"

    assert daily_pos > wildcard_pos, (
        f"daily 라우트 (pos={daily_pos}) 가 wildcard (pos={wildcard_pos}) *전* 등록 — "
        f"Playwright LIFO 위반: wildcard 가 daily 보다 우선 매칭 → envelope({{}}) 응답 → "
        f"DailyTab 렌더 실패. 사이클 80 hotfix #3 LIFO 정합 패턴 위반."
    )


def test_g_ast_lifo_daily_registered_after_history():
    """G-AST-LIFO (2/2): `*/daily*` 가 `*/history*` *후* 등록 의무.

    두 라우트 패턴이 유사 (`**/api/stock-master/*/daily*` vs `**/api/stock-master/*/history*`).
    Playwright LIFO 에서 daily 가 history *전* 등록 → history 가 우선 매칭 → 위험 없음.
    반대 순서 (daily 가 history *후* 등록) → daily 가 우선 → 의도대로 동작.

    하지만 안전을 위해 daily 가 history *후* 등록되어야 더 구체적인 daily 요청을
    확실히 캐치한다. 사이클 124 api-mocks.ts 설계 의도: history 후 daily 등록.
    """
    source = _load_source()

    history_pos = source.find('"**/api/stock-master/*/history')
    if history_pos == -1:
        history_pos = source.find("'**/api/stock-master/*/history")

    daily_pos = source.find('"**/api/stock-master/*/daily')
    if daily_pos == -1:
        daily_pos = source.find("'**/api/stock-master/*/daily")

    assert history_pos > 0, (
        "history 라우트 `**/api/stock-master/*/history*` 누락 — 사이클 85 T-6 참조."
    )
    assert daily_pos > 0, "daily 라우트 `**/api/stock-master/*/daily*` 누락 (G-AST-MOCK 참조)"

    assert daily_pos > history_pos, (
        f"daily 라우트 (pos={daily_pos}) 가 history (pos={history_pos}) *전* 등록 — "
        f"사이클 124 설계 의도 위반. daily 가 history 후 등록되어야 "
        f"Playwright LIFO 에서 daily 요청을 올바르게 캐치함."
    )
