# Red 명세 — 사이클 105: AST 영구 가드 신설 (사이클 104 silent 결함 2 영구 차단)

**작성일**: 2026-06-11
**담당**: tdd-engineer
**상태**: Phase 2 명세 + Phase 3 Red 통합 (단순 영역)
**위급도**: HIGH (영구 차단 의무) — production 코드 변경 0

---

## 배경

사이클 104 silent 결함 2 영역 즉시 시정 완료 + 사용자 결정 사이클 105 = AST 영구 가드 신설 (미래 재발 영구 차단). 사이클 78 G-AST1 + 79 G-AST2 + 98 G-DOC1 + 102 G-DOC1 답습 패턴 영구 영속.

### 결함 영역 1 — Playwright glob 모듈 intercept silent 결함

- **결함 시나리오**: `e2e/fixtures/api-mocks.ts` 의 와일드카드 glob (`**/api/*` 등) 이 Vite dev server 의 모듈 요청 (`http://localhost:3000/src/api/*.ts`, `resourceType='script'`) 도 intercept → JSON 반환 → MIME 타입 불일치 → 동적 import 실패 → e2e 페이지 빈 화면
- **사이클 104 시정**: `**/api/logs*` 핸들러에 `route.request().resourceType() === "script"` guard 추가 + `return route.continue()`
- **AST 영구 가드 의무 (G-PG1)**: 미래 신규 와일드카드 glob 추가 시 동일 패턴 silent 결함 영구 차단
  - **검증 영역**: `e2e/fixtures/api-mocks.ts` 의 모든 `page.route("**/api/...", ...)` 호출 중 와일드카드 suffix (`*`) 있고, suffix가 path segment 일부와 충돌 가능한 패턴 (예: `**/api/logs*` 가 `/src/api/logs.ts` 와 충돌) — 핸들러 본체에 `resourceType()` guard 존재 의무

### 결함 영역 2 — `Strategies.tsx` 응답 형식 fallback silent 결함

- **결함 시나리오**: `/api/strategies` GET 응답 형식이 내포 (`{ strategies: {...} }`) + 플랫 (`{ momentum: {...}, ... }`) 양 형식 가능 → fallback 없으면 한쪽 형식에서 `name = undefined` → 카드 미렌더
- **사이클 104 시정**: `Strategies.tsx` L157 `const raw = data?.strategies ?? data` fallback 추가
- **AST 영구 가드 의무 (G-SF1)**: 미래 fallback 제거 회귀 영구 차단
  - **검증 영역**: `frontend/src/pages/Strategies.tsx` 본체 = `data?.strategies ?? data` 또는 `data.strategies ?? data` 패턴 등장 의무 (정규식 grep)

---

## 회귀 가드 케이스 매트릭스

### HIGH 2 (G-PG1 + G-SF1 = 영구 차단 가드)

| ID | 파일 | 케이스 | 검증 영역 |
|----|------|--------|----------|
| G-PG1 | `tests/unit/e2e_mocks/test_cycle105_ast_playwright_resourcetype_guard.py` | `**/api/logs*` 와일드카드 glob 핸들러 본체에 `resourceType()` guard 영속 의무 | `e2e/fixtures/api-mocks.ts` 정적 grep |
| G-SF1 | `tests/unit/e2e_mocks/test_cycle105_ast_strategies_response_fallback.py` | `Strategies.tsx` 본체에 `data?.strategies ?? data` fallback 영속 의무 | `frontend/src/pages/Strategies.tsx` 정적 grep |

### MEDIUM 1 (사이클 104 시정 영역 영속 확인)

| ID | 파일 | 케이스 | 검증 영역 |
|----|------|--------|----------|
| G-PG2 | `tests/unit/e2e_mocks/test_cycle105_ast_playwright_resourcetype_guard.py` | resourceType guard 가 `script` 분기 + `route.continue()` 호출 결합 의무 | regex grep |

---

## 구현 영역

### Phase 3 Red

**신규 파일 1**: `tests/unit/e2e_mocks/test_cycle105_ast_playwright_resourcetype_guard.py`
- 검증 1 (G-PG1): `e2e/fixtures/api-mocks.ts` 텍스트 grep — `**/api/logs*` 핸들러 본체 (page.route 호출 직후 다음 page.route 호출 또는 함수 끝까지의 영역) 에 `resourceType()` 호출 존재
- 검증 2 (G-PG2): 동일 영역에 `script` 문자열 + `route.continue()` 호출 결합 존재

**신규 파일 2**: `tests/unit/e2e_mocks/test_cycle105_ast_strategies_response_fallback.py`
- 검증 1 (G-SF1): `frontend/src/pages/Strategies.tsx` 텍스트 grep — `data?.strategies ?? data` 또는 `data.strategies ?? data` 또는 동등 변형 (raw 변수 등) 존재 의무

### Phase 4 Green

- production 코드 변경 0 (사이클 104 시정 영역 영구 영속 = PASS 영역 영구 영속)

### Phase 5 verify

- 사이클 105 신규 가드 2 케이스 모두 PASS
- 백엔드 전체 회귀 0
- 사이클 104 영구 영속 영역 영구 영속

---

## 영속 의무 매트릭스

- **사이클 78 G-AST1 + 79 G-AST2 영속**: 미래 silent 결함 영구 차단 AST 패턴 답습 (8 회 누적 검증 후속 사이클 105 = 9 회 누적)
- **사이클 75 pytest AST 가드 패턴 답습**: `tests/unit/e2e_mocks/test_cycle75_api_mocks_routes_registered.py` 의 `Path` + `read_text` + 정규식 grep 패턴 직접 답습
- **사이클 86 답습 패턴 영속**: Playwright e2e 영역 silent 결함 영구 차단
- **사이클 98 G-DOC1 + 102 G-DOC1 답습 패턴 영속**: docstring 정본 인용 의무 영구 가드 (사이클 105 = silent 결함 영역 + docstring 인용 영역 영구 영속)
- **사이클 104 silent 결함 2 영역 영구 차단 의무**: G-PG1 + G-SF1 영구 가드 = 미래 재발 영구 차단
- **CLAUDE.md "절대 깨지 말 것" 8 영역 영속**

---

## 산출물

1. `tests/unit/e2e_mocks/test_cycle105_ast_playwright_resourcetype_guard.py` (G-PG1 + G-PG2)
2. `tests/unit/e2e_mocks/test_cycle105_ast_strategies_response_fallback.py` (G-SF1)
3. (production 코드 변경 0)

---

## 매매 안전성 무영향 확인

- AST 가드 영역만 신설 (e2e + frontend 영역 한정)
- production 코드 변경 0
- 매매 hot path 무관 (e2e Playwright 환경 + UI fallback 영역)
- 사이클 104 시정 영역 영구 영속 (`e2e/fixtures/api-mocks.ts` L192~195 resourceType guard + `Strategies.tsx` L157 fallback)
