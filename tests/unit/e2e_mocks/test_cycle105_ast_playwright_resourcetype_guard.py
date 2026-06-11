"""사이클 105 — Playwright glob 모듈 intercept silent 결함 영구 차단 AST 가드.

> **선례 (사이클 78 G-AST1 + 79 G-AST2 + 75 pytest AST + 102 G-DOC1 답습)**:
> - 사이클 78/79: AST 영구 가드 패턴 (미래 silent 결함 영구 차단)
> - 사이클 75: `tests/unit/e2e_mocks/test_cycle75_api_mocks_routes_registered.py`
>   = `Path` + `read_text` + 정규식 grep 패턴 직접 답습
> - 사이클 102 G-DOC1: docstring 정본 인용 의무 영구 가드 패턴
>
> **결함 배경 (사이클 104 발견 + 시정)**:
>   `e2e/fixtures/api-mocks.ts` 의 `**/api/logs*` Playwright glob 이
>   `http://localhost:3000/src/api/logs.ts` (Vite dev server 모듈 요청,
>   `resourceType='script'`) 도 intercept → JSON 반환 → MIME 타입 불일치 →
>   `RealtimeHealth.tsx` 동적 import 실패 → realtime-health.spec.ts 7/8 FAIL.
>
>   사이클 104 시정: `if (route.request().resourceType() === "script")`
>   guard + `return route.continue()` 추가 (e2e/fixtures/api-mocks.ts L192~195).
>
> **영구 차단 의무**: 미래 동일 패턴 (와일드카드 glob 이 Vite 모듈 경로와 충돌)
>   재발 시 즉시 검출 영구 차단. 본 가드 = 사이클 104 시정 영속 영구 영속 +
>   미래 신규 와일드카드 glob 추가 시 동일 패턴 silent 결함 영구 차단.

검증 방법: `e2e/fixtures/api-mocks.ts` 텍스트 정적 grep.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent.parent
API_MOCKS_PATH = REPO_ROOT / "e2e" / "fixtures" / "api-mocks.ts"


def _extract_handler_body(source: str, route_pattern: str) -> str:
    """`page.route("<route_pattern>", ...)` 호출 직후 ~ 다음 `await page.route` 호출 또는
    함수 끝까지의 영역을 반환 (핸들러 본체 + 동행 주석 영역).

    Playwright LIFO 정합 + 사이클 80 hotfix #3/#4 영속 영역 정합.
    """
    # 후보 패턴 (single + double + backtick quote)
    candidates = [
        f'page.route("{route_pattern}"',
        f"page.route('{route_pattern}'",
        f"page.route(`{route_pattern}`",
    ]
    start_idx = -1
    for candidate in candidates:
        idx = source.find(candidate)
        if idx >= 0:
            start_idx = idx
            break
    if start_idx < 0:
        return ""
    # 다음 page.route 호출 위치 또는 함수 끝까지 영역
    remaining = source[start_idx:]
    next_route_idx = remaining.find("page.route(", len("page.route("))
    if next_route_idx < 0:
        return remaining
    return remaining[:next_route_idx]


def test_e2e_api_mocks_path_exists():
    """e2e api-mocks.ts 파일 존재 의무 (방어 가드, 사이클 75 답습)."""
    assert API_MOCKS_PATH.exists(), (
        f"e2e api-mocks.ts 파일 누락: {API_MOCKS_PATH}. "
        "본 가드의 검증 대상 파일이 사라짐 — 본 테스트 갱신 의무."
    )


def test_cycle105_g_pg1_logs_glob_resourcetype_guard_required():
    """사이클 105 G-PG1 (HIGH) — `**/api/logs*` 와일드카드 glob 핸들러 본체에
    `resourceType()` guard 영속 의무.

    사이클 104 silent 결함 1 (Playwright glob Vite 모듈 intercept) 영구 차단:
      - `e2e/fixtures/api-mocks.ts` 의 `**/api/logs*` page.route 호출 직후
        다음 page.route 호출 전까지의 영역에 `resourceType()` 호출 영속 의무
      - 미래 fallback 제거 회귀 시 즉시 PASS → FAIL 검출
    """
    source = API_MOCKS_PATH.read_text(encoding="utf-8")
    handler_body = _extract_handler_body(source, "**/api/logs*")

    assert handler_body, (
        "사이클 105 G-PG1: `e2e/fixtures/api-mocks.ts` 에 "
        "`page.route(\"**/api/logs*\", ...)` 호출 미발견. "
        "사이클 104 시정 영역 영구 영속 의무 — 핸들러 위치 변경 시 본 가드 갱신 의무."
    )

    assert "resourceType()" in handler_body, (
        "사이클 105 G-PG1: `**/api/logs*` 핸들러 본체에 `resourceType()` "
        "호출 미발견 — 사이클 104 silent 결함 1 (Vite 모듈 intercept) 회귀 위험. "
        "와일드카드 glob 이 Vite dev server `/src/api/*.ts` (resourceType='script') "
        "요청을 intercept 시 MIME 타입 불일치 → 동적 import 실패 → "
        "RealtimeHealth.tsx 빈 화면. "
        "사이클 104 시정 패턴: "
        '`if (route.request().resourceType() === "script") return route.continue();` 영구 영속 의무.'
    )


def test_cycle105_g_pg2_resourcetype_script_branch_with_continue():
    """사이클 105 G-PG2 (MEDIUM) — resourceType guard 가 `script` 분기 +
    `route.continue()` 호출 결합 의무.

    사이클 104 시정 영역 정합 영구 영속:
      - `script` 문자열 (또는 `'script'` / `"script"`) 존재 의무
      - `route.continue()` 호출 존재 의무 (Vite 모듈 요청은 통과)
    """
    source = API_MOCKS_PATH.read_text(encoding="utf-8")
    handler_body = _extract_handler_body(source, "**/api/logs*")

    assert handler_body, (
        "사이클 105 G-PG2: `**/api/logs*` 핸들러 미발견 — G-PG1 참조 의무."
    )

    # `script` 문자열 검증 (single/double quote 양 형식 호환)
    has_script_literal = (
        '"script"' in handler_body or "'script'" in handler_body
    )
    assert has_script_literal, (
        "사이클 105 G-PG2: `**/api/logs*` 핸들러 본체에 `'script'` 또는 `\"script\"` "
        "문자열 리터럴 미발견 — resourceType 분기 영역 결함. "
        "사이클 104 시정 패턴: "
        '`route.request().resourceType() === "script"` 영구 영속 의무.'
    )

    # `route.continue()` 호출 검증 (Vite 모듈 요청 통과 의무)
    assert "route.continue()" in handler_body, (
        "사이클 105 G-PG2: `**/api/logs*` 핸들러 본체에 `route.continue()` "
        "호출 미발견 — Vite 모듈 요청 통과 영역 결함. "
        "사이클 104 시정 패턴: "
        "`if (...) return route.continue();` 영구 영속 의무."
    )
