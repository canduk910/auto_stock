# Cycle 75 — e2e api-mocks flaky 영구 차단 (Red 명세)

## 배경

- **카드 #19'** (HIGH): e2e api-mocks.ts 라우트 누락 → vite proxy 호출 → 백엔드 미실행 환경 (CI / 로컬 e2e) ECONNREFUSED → React Query 기본 retry 누적 → settings.spec.ts timeout flakiness
- **사이클 73 1차 fail + 사이클 74 1차 fail** = flaky 2회 누적 확인
- **사이클 65 hotfix #2 패턴 답습** (api-mocks 라우트 누락 시정) + **사이클 65 hotfix #3 패턴 답습** (AST 영구 가드)

## 사용자 결정 (team-leader Phase 1 분석 후 확정)

- 결정 1 = **C** (api-mocks 7 endpoint 추가 + AST 영구 가드) — **14 사이클 연속 옵션 A 패턴 영속**
- 결정 2 = **X** (`frontend/src/api/*.ts` literal vs api-mocks 대조)
- **Q4 채택** — `retry: 1` 영역 확장 (IntegrationToggleCard / CashUsageRatioCard / KisQuoteAccountsCard)

## 식별 7 endpoint group

| 컴포넌트 | endpoint | 비고 |
|----------|----------|------|
| `CashUsageRatioCard` | `/api/strategies/system/cash-usage-ratio` | 사이클 73 fail 로그 확인 |
| `IntegrationToggleCard` (4 토글) | `/api/integrations/dkstock-regime` | 사이클 73 fail 로그 |
| | `/api/integrations/kis-mcp` | 사이클 73 fail 로그 |
| | `/api/integrations/auto-regime-adjust` | |
| | `/api/integrations/auto-apply` | |
| `BuyBlockSection` | `/api/integrations/buy-block` | |
| `KisQuoteAccountsCard` | `/api/integrations/quote-accounts*` | |

## Red 테스트 매트릭스 (총 ~8 케이스)

### G-AST 그룹 (vitest 정적 가드, 4 케이스)

신규 파일: `frontend/src/components/__tests__/_ast_api_mocks_coverage.test.ts`

- **G-AST1**: `frontend/src/api/integrations.ts` literal endpoint → `e2e/fixtures/api-mocks.ts` 등록 확인 (`/integrations/${key}` 패턴 + `/integrations/buy-block`)
- **G-AST2**: `frontend/src/api/trading.ts` `/strategies/system/cash-usage-ratio` 등록 확인
- **G-AST3**: `frontend/src/api/kis-quote-accounts.ts` `/integrations/quote-accounts*` 등록 확인
- **G-AST4**: 3 컴포넌트 (IntegrationToggleCard / CashUsageRatioCard / KisQuoteAccountsCard) useQuery 호출에 `retry:` 옵션 명시 확인

### G-RT 그룹 (vitest retry 명시, 3 케이스)

기존 파일 확장: `frontend/src/components/__tests__/_ast_useQuery_retry_required.test.ts`

- **G-RT1**: `IntegrationToggleCard.tsx` useQuery 호출에 `retry:` 옵션 명시 확인
- **G-RT2**: `CashUsageRatioCard.tsx` useQuery 호출에 `retry:` 옵션 명시 확인
- **G-RT3**: `KisQuoteAccountsCard.tsx` useQuery 호출에 `retry:` 옵션 명시 확인

### G-E2E 그룹 (pytest 정적 가드, 1 케이스)

신규 파일: `tests/unit/e2e_mocks/test_cycle75_api_mocks_routes_registered.py`

- **G-E2E1**: `e2e/fixtures/api-mocks.ts` 에 7 endpoint group 라우트 등록 확인 (정규식 grep)

## Red 검증 의무

1. 모든 케이스 FAIL (Green 전)
2. flakiness 3 회 반복 — 모두 동일 결과
3. Green 단계 = frontend-dev 가 api-mocks 라우트 7 endpoint 추가 + 3 컴포넌트 `retry: 1` 명시

## 영속 영향

- 매도 안전성 / WebSocket 4 중 안전망 / 사이클 38/55 R-1/66/67/68/72/73/74 모두 무영향
- 사이클 65 hotfix #1/#2/#3 패턴 영속 (변경 0)
- 운영 영향 0 (e2e + frontend retry 옵션 한정)
