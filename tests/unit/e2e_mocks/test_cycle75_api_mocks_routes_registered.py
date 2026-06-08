"""사이클 75 카드 #19' (HIGH) — e2e api-mocks.ts 7 endpoint group 영구 가드 (pytest).

> **선례**:
> - 사이클 65 hotfix #2 (`tests/unit/e2e_mocks/test_api_mocks_routes_registered.py`)
>   `/api/system/price-filter` + `/api/system/trade-amount-filter` 영역 가드 패턴 답습.
> - 사이클 65 hotfix #3 AST 영구 가드 패턴 답습.
>
> **결함 배경**: 사이클 73 1차 fail + 사이클 74 1차 fail = flaky 2회 누적 —
>   Settings 화면 진입 시 `IntegrationToggleCard` / `CashUsageRatioCard` /
>   `KisQuoteAccountsCard` 등 7 endpoint group 이 `e2e/fixtures/api-mocks.ts` 에
>   미등록 → vite proxy 호출 → 백엔드 미실행 환경 ECONNREFUSED →
>   React Query 기본 retry 누적 → settings.spec.ts timeout flakiness.

본 가드는 향후 신규 컴포넌트 추가 시 e2e mock 누락을 pytest 단계에서 영구 차단한다
(vitest AST 가드 `_ast_api_mocks_coverage.test.ts` 와 이중 안전망).

검증 방법: `e2e/fixtures/api-mocks.ts` 텍스트 정적 grep.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent
API_MOCKS_PATH = REPO_ROOT / "e2e" / "fixtures" / "api-mocks.ts"

# 사이클 75 카드 #19' 식별 7 endpoint group (Settings 화면 진입 시 호출).
# 각 항목 = (endpoint_path, 컴포넌트, 사이클 73/74 fail 로그 여부)
REQUIRED_ENDPOINTS = [
    ("/api/strategies/system/cash-usage-ratio", "CashUsageRatioCard", True),
    ("/api/integrations/dkstock-regime", "IntegrationToggleCard", True),
    ("/api/integrations/kis-mcp", "IntegrationToggleCard", True),
    ("/api/integrations/auto-regime-adjust", "IntegrationToggleCard", False),
    ("/api/integrations/auto-apply", "IntegrationToggleCard", False),
    ("/api/integrations/buy-block", "BuyBlockSection", False),
    ("/api/integrations/quote-accounts", "KisQuoteAccountsCard", False),
]


def _route_registered(source: str, endpoint_path: str) -> bool:
    """page.route("**${endpoint_path}...") 형태 등록 확인.

    Playwright 와일드카드 `**` prefix + endpoint substring 매칭.
    `quote-accounts*` 형태 (suffix 와일드카드) 도 함께 커버.
    """
    # 후보 패턴:
    #   page.route("**/api/integrations/dkstock-regime"
    #   page.route("**/api/integrations/dkstock-regime*"
    #   page.route(`**/api/integrations/quote-accounts/${id}` 등 backtick 도 호환
    candidates = [
        f'page.route("**{endpoint_path}"',
        f'page.route("**{endpoint_path}*"',
        f"page.route('**{endpoint_path}'",
        f"page.route('**{endpoint_path}*'",
        f"page.route(`**{endpoint_path}`",
        f"page.route(`**{endpoint_path}*`",
    ]
    return any(candidate in source for candidate in candidates)


def test_e2e_api_mocks_path_exists():
    """e2e api-mocks.ts 파일 존재 의무 (방어 가드)."""
    assert API_MOCKS_PATH.exists(), (
        f"e2e api-mocks.ts 파일 누락: {API_MOCKS_PATH}. "
        "본 가드의 검증 대상 파일이 사라짐 — 본 테스트 갱신 의무."
    )


def test_e2e_api_mocks_includes_cycle75_seven_endpoint_group():
    """사이클 75 카드 #19' — 7 endpoint group 라우트 등록 통합 의무.

    각 endpoint 단위로 등록 여부 grep + 누락 목록 한꺼번에 보고
    (개별 it.each 분기보다 누락 전체 가시화에 유리).
    """
    source = API_MOCKS_PATH.read_text(encoding="utf-8")
    missing: list[str] = []

    for endpoint, component, was_in_fail_log in REQUIRED_ENDPOINTS:
        if not _route_registered(source, endpoint):
            fail_tag = " [사이클 73 fail 로그 확인]" if was_in_fail_log else ""
            missing.append(f"  - {endpoint:60s} ({component}){fail_tag}")

    assert not missing, (
        "e2e api-mocks.ts 에 사이클 75 카드 #19' 7 endpoint group 라우트 누락 — "
        "사이클 73/74 flaky 결함 영속 (vite proxy → ECONNREFUSED → "
        "React Query retry 누적 → settings.spec.ts timeout). "
        "사이클 65 hotfix #2 패턴 답습 의무:\n" + "\n".join(missing)
    )
