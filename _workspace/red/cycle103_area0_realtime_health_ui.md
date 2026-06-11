# 사이클 103 영역 0 — 운영 가시화 UI (RealtimeHealth 신규 페이지)

**명세 출처**: 사용자 결정 사이클 103 (Q10'=B, 2026-06-11) — 4 영역 통합 시정
**행위**: `/realtime-health` 신규 페이지 = 4 카드 (`[dispatch_drop_summary]` / `[callback_exception]` / `[stale_force_retry]` / `[ws_auto_restart]`) 5분 주기 system_logs 직접 조회 가시화 + 24h/7일 시간 윈도우 토글 + 8번째 메뉴 + 모바일 햄버거 8개 메뉴 영구 영속

## 영속 의무 매트릭스 (HIGH)

- 사이클 41 StrategyFunnel 4 카드 패턴 영속
- 사이클 65 H3 useQuery retry:1 영속 + 사이클 80 hotfix #1 Settings.tsx retry:1 영역 확장 답습
- 사이클 68 KST 영속 (`Intl.DateTimeFormat(timeZone='Asia/Seoul')` 명시)
- 사이클 75 G-AST5 api-mocks 영속 (4 endpoint group 등록 영구 가드)
- 사이클 80 hotfix #3/#4 Playwright LIFO 영속 (wildcard *전* 등록)
- 사이클 85 G-AST-RT TARGET_PAGES 확장 패턴 답습 + G-AST-MOCK 영속
- 사이클 89 한글 친숙 용어 + 사이클 언급 0 영속
- 사이클 102 G-REJECT 영속 (양 agent 일치)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

## 영역 0 데이터 출처 (4 prefix system_logs 직접 조회)

| 카드 | system_logs prefix | 영속 사이클 | 데이터 영역 |
|------|---------------------|-------------|---------------|
| `[dispatch_drop_summary]` | 사이클 102 영역 2-B | 5분 주기 emit | level/count/per-5min |
| `[callback_exception]` | 사이클 102 영역 2-C | 3 콜백 예외 빈도 | count/level/per-hour |
| `[stale_force_retry]` | 사이클 29 R1 + 사이클 102 Q73=B | 50~70건/일 (임계 상향 후) | count/per-hour |
| `[ws_auto_restart]` | 사이클 92 자동 재기동 | 0건 영속 정상 | count/per-day |

## 회귀 가드 13 케이스 (HIGH 8 + MEDIUM 3 + LOW 2)

### HIGH-1 ~ HIGH-4: 4 카드 정합 (각 카드 emit 영역 영속 확인, 4 sub-case)

- **HIGH-1** (`frontend/src/pages/__tests__/RealtimeHealth.test.tsx`): `RealtimeHealth.tsx` 가 `[dispatch_drop_summary]` 카드를 `data-testid="realtime-health-card-dispatch-drop"` 영역 렌더 + count/level/per-5min 영구 영속 + searchLogs(`q: "[dispatch_drop_summary]"`) 호출 정합
- **HIGH-2**: `[callback_exception]` 카드 `data-testid="realtime-health-card-callback-exception"` + 3 콜백 예외 빈도 영속
- **HIGH-3**: `[stale_force_retry]` 카드 `data-testid="realtime-health-card-stale-force-retry"` + 50~70건/일 임계 상향 영역 영속
- **HIGH-4**: `[ws_auto_restart]` 카드 `data-testid="realtime-health-card-ws-auto-restart"` + 0건 영속 정상 영역

### HIGH-5: useQuery retry:1 영속 (사이클 65 H3 답습)

- `frontend/src/pages/__tests__/RealtimeHealth.test.tsx::H5_useQuery_retry_required`: `useQuery({ retry: 1, ... })` 4 sub-case (각 카드 분리 호출 영역)

### HIGH-6: 60s polling refetchInterval (사이클 85 답습)

- `RealtimeHealth.test.tsx::H6_refetchInterval_60s`: `refetchInterval: 60_000` 명시 + 4 useQuery 영역 영구 영속

### HIGH-7: G-AST-RT TARGET_PAGES 확장 (사이클 85 G-AST-RT 답습)

- `frontend/src/components/__tests__/_ast_useQuery_retry_required.test.ts`: `TARGET_PAGES` literal 영역에 `'RealtimeHealth.tsx'` 추가 영구 영속 + it.each describe 영역 영속 (`grep RealtimeHealth.tsx` 정적 검증 ≥1건)

### HIGH-8: G-AST-MOCK 4 endpoint api-mocks 등록 영구 가드 (사이클 75 G-AST5 답습)

- `frontend/src/components/__tests__/_ast_api_mocks_coverage.test.ts`: 신규 describe 영역 + `REQUIRED_REALTIME_HEALTH_ENDPOINTS = [4 prefix]` literal + isRouteRegistered 검증
- `tests/unit/e2e_mocks/test_cycle103_api_mocks_routes_registered.py`: pytest AST 영역 = 4 endpoint group (`logs/search` 영역 활용 + window 토글 영역) 정규식 grep 영구 영속

### MEDIUM-1: api-mocks LIFO 정합 (사이클 80 hotfix #3 영속)

- `e2e/fixtures/api-mocks.ts`: wildcard `**/api/**` *전* 4 endpoint group 구체 라우트 등록 영역 영구 영속 (Playwright LIFO 영역)
- AST 영역 `tests/unit/e2e_mocks/test_cycle103_lifo_ordering.py`: wildcard 위치 영역 vs 구체 라우트 위치 영역 정렬 검증

### MEDIUM-2: 시간 윈도우 토글 (24h / 7일)

- `RealtimeHealth.test.tsx::M2_window_toggle`: `data-testid="realtime-health-window-24h"` / `realtime-health-window-7d` 버튼 영역 + 클릭 시 useQuery 영역 갱신 정합

### MEDIUM-3: 모바일 햄버거 8개 메뉴 (사이클 85 M-9 답습)

- `frontend/src/__tests__/AppShell.test.tsx::M_10_realtime_health_menu`: 햄버거 Drawer 8개 메뉴 (기존 7개 + `종목마스터` 다음 `실시간 상태` 영역) + 모바일 viewport 375px 영역 영속

### LOW-1: KST 영속 (사이클 68 답습)

- `RealtimeHealth.test.tsx::L1_KST_persistence`: `Intl.DateTimeFormat('ko-KR', timeZone: 'Asia/Seoul', hour12: false)` 명시 + `getHours()` 0건 정적 검증

### LOW-2: 빈 데이터 graceful

- `RealtimeHealth.test.tsx::L2_empty_graceful`: 4 카드 모두 응답 0건 시 "데이터 없음" 영역 렌더 + 에러 미발화 영역 영속

## Red 단계 (production 코드 변경 0)

- `frontend/src/pages/RealtimeHealth.tsx` = **신규 페이지 미존재** → 18 신규 테스트 영역 (HIGH 8 + MEDIUM 3 + LOW 2 + AST 5)
- `frontend/src/App.tsx::navItems` = 7개 (RealtimeHealth 미등록) → M-10 영역 fail
- `e2e/fixtures/api-mocks.ts` = 4 endpoint group 미등록 → MEDIUM-1 LIFO 영역 fail
- 사이클 103 영역 0 = 모든 신규 테스트 영역 RED 영구 영속

## Green 단계 인계 (frontend-dev 영역)

1. `frontend/src/types/realtime-health.ts` 신규 (4 카드 응답 영역 + window 토글 영역)
2. `frontend/src/api/realtime-health.ts` 신규 (4 함수 = searchLogs 영역 활용)
3. `frontend/src/pages/RealtimeHealth.tsx` 신규 (~280L, 4 카드 + window 토글 + retry:1 + 60s polling)
4. `frontend/src/App.tsx` 갱신 (navItems 7→8 + lazy import + Route + MobileMenuLabel)
5. `frontend/src/test/handlers.ts` MSW 영역 4 라우트 추가
6. `e2e/fixtures/api-mocks.ts` 4 endpoint group LIFO 정합 추가

## 영속 의무 영속 검증 (Green 단계 후)

- 사이클 65 H3 retry:1 정확 grep 4건 (4 useQuery 영역)
- 사이클 68 KST `Intl.DateTimeFormat` 명시 + `getHours()` 0건
- 사이클 75 G-AST5 4 endpoint 등록 영역
- 사이클 80 hotfix #3 LIFO 정합 영역
- 사이클 85 G-AST-RT TARGET_PAGES 확장 영역
- 사이클 89 한글 라벨 (`실시간 상태`) + 사이클 언급 0
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속 (UI 레이어 한정, READ-ONLY system_logs 조회)
