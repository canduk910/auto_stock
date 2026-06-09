# 사이클 85 Red — stock_master UI 메뉴 프론트 단독 단계

작성일: 2026-06-09
작성자: tdd-engineer
배경: 사이클 85 발주 = `_workspace/cycle85_phase1_diagnosis.md` 진단 + 사용자 결정 채택 (Q10=A 단일 페이지 4 카드 / Q11=B 카테고리 + 핵심 5 키 highlight / Q12=A `<pre>` collapsible / Q13=B 60s polling / Q14=C 사이클 85 push + 86 통합 검증 별개)
선행 인계: 사이클 84 백엔드 5 GET 라우트 운영 적용 완료 (verify report `_workspace/cycle84_verify_report.md` 영속)

## 선행 영속 패턴 (의무 답습)

- **사이클 41 `StrategyFunnel.tsx`** — 단일 페이지 4 카드 구조 답습 (Q10=A)
- **사이클 65 hotfix #1 / H3 `_ast_useQuery_retry_required.test.ts`** — useQuery `retry: 1` 명시 의무 영구 가드 답습
- **사이클 75 G-AST5 + G-RT1~RT3 `_ast_api_mocks_coverage.test.ts`** — api-mocks 누락 영구 가드 답습 (G-AST5 = Dashboard 영역 확장 패턴)
- **사이클 80 hotfix #3/#4 LIFO 정합** — `tests/unit/e2e_mocks/test_api_mocks_routes_registered.py` `after_wildcard` 함수명 의무 답습 (구체 라우트가 wildcard *후* 등록)
- **사이클 81 G-M1~M8 햄버거 메뉴** — 모바일 viewport 375px 침범 0 영속 + 7개 메뉴 압축 (사이클 81 6개 → 사이클 85 7개)
- **사이클 68 KST 일관성** — `Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul' })` 명시 의무
- **사이클 65 `TradeAmountFilterCard` testid 패턴** — `data-testid="…-card"` / `…-button` 네이밍

## 1. Green 시정 영역 (frontend-dev 인계)

### 1-1. `frontend/src/types/stock-master.ts` (신규)

```typescript
export interface StockMasterStats {
  count_all: number
  bfdy_clpr_present: number
  nxt_tradable_count: number
  top_10_recent: Array<{ ticker: string; name: string; refreshed_at: string }>
}

export interface StockMasterListItem {
  ticker: string
  name: string
  excg_dvsn_cd: string | null
  nxt_tradable: boolean
  krx_halted: boolean
  admin_item: boolean
  refreshed_at: string  // KST +09:00 ISO
  raw: Record<string, unknown>
}

export type StockMasterDetail = StockMasterListItem

export interface StockMasterHistoryItem {
  id: number
  ticker: string
  change_type: 'INSERT' | 'UPDATE' | 'DELETE' | 'TTL_REFRESH'
  before_raw: Record<string, unknown> | null
  after_raw: Record<string, unknown> | null
  changed_at: string  // KST +09:00 ISO
}

export interface ScanPoolSummary {
  eager_refresh_today: number
}
```

### 1-2. `frontend/src/api/stock-master.ts` (신규 5 함수)

각 함수 모두 `ApiResponse<T>` 래퍼 `data.data` 추출 패턴 (사이클 65 `trade-amount-filter.ts` 답습):

- `fetchStats() -> Promise<StockMasterStats>` — `GET /api/stock-master/stats`
- `fetchList(limit = 100, offset = 0) -> Promise<StockMasterListItem[]>` — `GET /api/stock-master/list?limit=&offset=`
- `fetchScanPoolSummary() -> Promise<ScanPoolSummary>` — `GET /api/stock-master/scan-pool/summary`
- `fetchDetail(ticker: string) -> Promise<StockMasterDetail>` — `GET /api/stock-master/{ticker}` (404 → `axios.isAxiosError` 분기)
- `fetchHistory(ticker: string, limit = 100) -> Promise<StockMasterHistoryItem[]>` — `GET /api/stock-master/{ticker}/history?limit=`

### 1-3. `frontend/src/pages/StockMaster.tsx` (신규 — Q10=A 단일 페이지 4 카드)

**4 영역 카드 구성** (사이클 41 `StrategyFunnel.tsx` 답습):

| 카드 | testid | API | 표시 | polling |
|------|--------|-----|------|---------|
| 상태 | `stock-master-stats-card` | `fetchStats` + `fetchScanPoolSummary` | count_all / bfdy_clpr_present (사이클 81 키 정합 가시화) / nxt_tradable_count / eager_refresh_today (사이클 83 emit 카운트) + top_10_recent 5개 | 60s |
| list 테이블 | `stock-master-list-card` | `fetchList(100, offset)` | ticker / name / excg_dvsn_cd / nxt_tradable / krx_halted / admin_item / refreshed_at (KST `+09:00`) | 60s |
| detail 모달 | `stock-master-detail-modal` | `fetchDetail(ticker)` (ticker 클릭 시 open) | 카테고리 분류 5종 (기본/가격/거래/플래그/메타) + **핵심 5 키 highlight** (`bfdy_clpr` / `acml_vol` / `nxt_tradable` / `krx_halted` / `admin_item`) | 수동 |
| history 테이블 | `stock-master-history-card` | `fetchHistory(ticker, 100)` (ticker 선택 시 표시) | changed_at DESC / change_type 배지 / before_raw + after_raw `<pre>` collapsible (Q12=A) | 60s |

**useQuery 옵션 영속 (사이클 65 H3 + 사이클 80 hotfix #1 영역 영속)**:
- 5 useQuery 모두 `retry: 1` 명시 (G-AST-RT 영구 가드 의무)
- `refetchInterval: 60_000` (Q13=B)
- `staleTime: 30_000`

**페이징** (사이클 84 H-1 정합):
- list `limit=100` 고정, `offset` state 관리 + 이전/다음 버튼 (`stock-master-list-prev` / `stock-master-list-next`)
- limit < 1 or > 1000 / offset < 0 → 422 처리 (H-422)

**404 처리** (사이클 84 H-5 정합):
- detail/history `fetchDetail` 호출 시 `axios.isAxiosError(err) && err.response?.status === 404` → `stock-master-detail-not-found` graceful 메시지

**KST 표시** (G-KST 영구 가드, 사이클 68 영속):
- `refreshed_at` / `changed_at` 모두 `Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', ... })` 명시
- `new Date(iso).getHours()` 금지

### 1-4. `frontend/src/App.tsx` 갱신 (7번째 메뉴 추가)

- `navItems` 6 → 7개 추가: `{ to: '/stock-master', label: '종목마스터' }`
- `<Route path="/stock-master" element={<StockMaster />} />` 추가 (lazy import)
- `MobileMenuLabel` 헬퍼 `navItems` 매핑이 7개로 자동 확장됨 (변경 0, 단 G-MOBILE-7 검증 의무)

### 1-5. `frontend/src/test/handlers.ts` (MSW handlers 5 추가)

5 라우트 mock handlers 추가 (각각 `wrap({...})` 응답):
- `GET /api/stock-master/stats`
- `GET /api/stock-master/list`
- `GET /api/stock-master/scan-pool/summary`
- `GET /api/stock-master/:ticker`
- `GET /api/stock-master/:ticker/history`

### 1-6. `e2e/fixtures/api-mocks.ts` 갱신 (Playwright LIFO 정합)

**사이클 80 hotfix #3 LIFO 영속** — 구체 라우트가 wildcard *후* 등록:

```typescript
// 사이클 85 — wildcard 가 *전* 등록 (fallback 역할, LIFO 라 가장 후순위 매칭)
await page.route("**/api/stock-master/**", (route) =>
  route.fulfill({ json: envelope({}) }),
);

// 5 구체 라우트가 wildcard *후* 등록 (LIFO 라 우선 매칭)
await page.route("**/api/stock-master/stats", (route) => ...);
await page.route("**/api/stock-master/list*", (route) => ...);
await page.route("**/api/stock-master/scan-pool/summary", (route) => ...);
await page.route("**/api/stock-master/*/history*", (route) => ...);
await page.route("**/api/stock-master/*", (route) => ...);
```

## 2. 회귀 가드 매트릭스 (16 케이스, HIGH 5 + MEDIUM 7 + LOW 4)

### HIGH 5 (31%)

| ID | 파일 | 의도 | 답습 패턴 |
|----|------|------|----------|
| **G-AST-RT** | `frontend/src/components/__tests__/_ast_useQuery_retry_required.test.ts` (TARGET_PAGES 영역 확장 — `StockMaster.tsx` 추가) | `pages/StockMaster.tsx` 의 모든 useQuery 호출에 `retry:` 옵션 명시 의무 (5 useQuery × `retry: 1`) | 사이클 65 H3 + 사이클 80 hotfix #1 영속 |
| **G-AST-MOCK** | `frontend/src/components/__tests__/_ast_api_mocks_coverage.test.ts` (G-AST6 신규 describe — Stock Master 영역) | `REQUIRED_STOCK_MASTER_ENDPOINTS` 5종 (`/api/stock-master/{stats,list,scan-pool/summary,:ticker,:ticker/history}`) 모두 api-mocks 등록 검증 | 사이클 75 G-AST5 답습 |
| **G-AST-LIFO** | `tests/unit/e2e_mocks/test_cycle85_api_mocks_stock_master_lifo.py` 신규 | (a) 5 구체 라우트 등록 누락 검증 + (b) wildcard `**/api/stock-master/**` 등록 검증 + (c) 5 구체 라우트가 wildcard *후* 등록 (`after_wildcard` Playwright LIFO 정합) | 사이클 80 hotfix #3/#4 답습 |
| **G-MOBILE-7** | `frontend/src/__tests__/AppShell.test.tsx` (M-5 7개 확장 + 신규 M-9 `종목마스터` 라벨) | (a) PC nav 7개 메뉴 렌더 (`종목마스터` 포함) + (b) 모바일 햄버거 Drawer 7개 메뉴 + (c) 드로어 7개 클릭 후 close + (d) MobileMenuLabel 매핑 7개 (`/stock-master` → `종목마스터`) | 사이클 81 M-1~M-8 답습 |
| **G-KST** | `frontend/src/pages/__tests__/StockMaster.test.tsx` 신규 (G-KST sub-case) | `refreshed_at` / `changed_at` 표시 시 `Intl.DateTimeFormat` 사용 + `Asia/Seoul` 명시 + `+09:00` ISO 입력 KST 표시 검증 (`new Date(iso).getHours()` 패턴 0건 AST 정적) | 사이클 68 답습 |

### MEDIUM 7 (44%)

| ID | 파일 | 의도 |
|----|------|------|
| **H-STATS** | `frontend/src/pages/__tests__/StockMaster.test.tsx` (H-STATS sub-case) | 상태 카드 렌더 — `stock-master-stats-card` testid + 4 키 값 표시 (count_all=29 / bfdy_clpr_present / nxt_tradable_count / eager_refresh_today) + top_10_recent 5개 ticker |
| **H-LIST** | `frontend/src/pages/__tests__/StockMaster.test.tsx` (H-LIST sub-case) | list 테이블 렌더 + 페이징 (limit=100, offset=0) + 이전/다음 버튼 + refreshed_at DESC 표시 |
| **H-DETAIL** | `frontend/src/pages/__tests__/StockMaster.test.tsx` (H-DETAIL sub-case) | ticker 클릭 → `stock-master-detail-modal` open + Q11=B 카테고리 분류 5종 (기본/가격/거래/플래그/메타) + 핵심 5 키 highlight (`bfdy_clpr` / `acml_vol` / `nxt_tradable` / `krx_halted` / `admin_item`) — testid `stock-master-detail-highlight-{key}` |
| **H-HISTORY** | `frontend/src/pages/__tests__/StockMaster.test.tsx` (H-HISTORY sub-case) | history 테이블 changed_at DESC + change_type 배지 (INSERT/UPDATE/DELETE/TTL_REFRESH) + before_raw + after_raw `<pre>` collapsible toggle |
| **H-404** | `frontend/src/api/__tests__/stock-master.test.ts` (H-404 sub-case) | `fetchDetail('999999')` 호출 시 백엔드 404 응답 → axios error throw (페이지 단에서 `stock-master-detail-not-found` graceful) |
| **H-422** | `frontend/src/api/__tests__/stock-master.test.ts` (H-422 sub-case) | `fetchList(0, 0)` / `fetchList(1001, 0)` / `fetchList(100, -1)` 호출 시 백엔드 422 → axios error throw |
| **H-POLLING** | `frontend/src/pages/__tests__/StockMaster.test.tsx` (H-POLLING sub-case) | 5 useQuery 모두 `refetchInterval: 60_000` 명시 (Q13=B) — AST 정적 grep (`refetchInterval:\s*60_?000`) |

### LOW 4 (25%)

| ID | 파일 | 의도 |
|----|------|------|
| **L-API** | `frontend/src/api/__tests__/stock-master.test.ts` (L-API sub-case) | 5 함수 단위 (`fetchStats` / `fetchList` / `fetchScanPoolSummary` / `fetchDetail` / `fetchHistory`) 모두 `ApiResponse<T>` 래퍼 `data.data` 추출 정합 검증 (사이클 65 `trade-amount-filter.test.ts` 패턴 답습) |
| **L-MENU** | `frontend/src/__tests__/AppShell.test.tsx` (L-MENU sub-case) | 7번째 메뉴 `/stock-master` → `종목마스터` 라우트 존재 + NavLink 렌더 + 라우팅 정합 |
| **L-CYCLE83-EMIT** | `frontend/src/pages/__tests__/StockMaster.test.tsx` (L-CYCLE83-EMIT sub-case) | 상태 카드가 `fetchScanPoolSummary` 호출 후 `eager_refresh_today` 값을 testid `stock-master-stats-eager-refresh-today` 로 노출 (사이클 83 `[scan_pool_eager_refresh]` emit 카운트 가시화 영속) |
| **L-CYCLE81-MOBILE** | `frontend/src/__tests__/AppShell.test.tsx` (L-CYCLE81-MOBILE sub-case) | 모바일 viewport (resize 375px) 시 햄버거 메뉴 7개 압축 정상 + `nav-sticky-wrapper` overlap 0 (사이클 81 M-8 답습) |

## 3. 신규 / 갱신 파일 매트릭스

| 파일 | 변경 | 라인 추정 | 비고 |
|------|------|-----------|------|
| `frontend/src/types/stock-master.ts` | 신규 | ~45L | 5 interface 정의 |
| `frontend/src/api/stock-master.ts` | 신규 | ~65L | 5 함수 + ApiResponse 래퍼 |
| `frontend/src/pages/StockMaster.tsx` | 신규 | ~300L | 4 카드 (사이클 41 StrategyFunnel 답습) |
| `frontend/src/App.tsx` | 갱신 | +3L | navItems 7번째 + Route + lazy import |
| `frontend/src/test/handlers.ts` | 갱신 | +35L | MSW 5 handler |
| `e2e/fixtures/api-mocks.ts` | 갱신 | +25L | wildcard 1 + 구체 5 (LIFO 정합) |
| `frontend/src/api/__tests__/stock-master.test.ts` | 신규 | ~120L | L-API + H-404 + H-422 |
| `frontend/src/pages/__tests__/StockMaster.test.tsx` | 신규 | ~280L | G-KST + H-STATS + H-LIST + H-DETAIL + H-HISTORY + H-POLLING + L-CYCLE83-EMIT |
| `frontend/src/__tests__/AppShell.test.tsx` | 갱신 | +35L | M-5 7개 + M-9 `종목마스터` + L-MENU + L-CYCLE81-MOBILE |
| `frontend/src/components/__tests__/_ast_useQuery_retry_required.test.ts` | 갱신 | +2L | TARGET_PAGES 에 `StockMaster.tsx` 추가 |
| `frontend/src/components/__tests__/_ast_api_mocks_coverage.test.ts` | 갱신 | +45L | G-AST6 신규 describe (5 endpoint × 1) |
| `tests/unit/e2e_mocks/test_cycle85_api_mocks_stock_master_lifo.py` | 신규 | ~80L | 7 sub-case (5 등록 검증 + 1 wildcard 검증 + 1 LIFO 정합) |

## 4. Red 실행 결과 (예상)

- 프론트 현재: 196 PASS
- 사이클 85 Red 추가 시:
  - vitest 신규 ~14 fail (production 코드 부재 — StockMaster.tsx / stock-master.ts / types/stock-master.ts 미존재)
  - AST 가드 일부 사전 PASS 가능 (TARGET_PAGES 확장 등)
- 백엔드 현재: 2151 PASS + 2 XFAIL + 2 skip (사이클 84 종결 시점)
- 백엔드 사이클 85 Red 추가: 1 신규 `test_cycle85_api_mocks_stock_master_lifo.py` 추가 → 2152 PASS 예상

## 5. 영향 인덱스 갱신

`_workspace/test_index.yaml`:
- backend_tests: 366 → 367 (+1 pytest AST 신규)
- frontend_modules: 58 → 61 (+3 = types/stock-master.ts + api/stock-master.ts + pages/StockMaster.tsx)
- frontend_tests: 34 → 36 (+2 = api/__tests__/stock-master.test.ts + pages/__tests__/StockMaster.test.tsx)
- generated_at: 2026-06-09 갱신 의무

## 6. 매매 안전성 영향 평가

- **무영향**: UI 레이어 한정 (READ-ONLY 5 GET 라우트만 호출, PUT/POST/DELETE 0건)
- 매매 hot path (`risk.on_tick` / `order_engine` / `scheduler._boot`) 변경 0
- 사이클 84 백엔드 READ-ONLY 영속 정합 (`L-2` AST 가드 — `src/routes/stock_master.py` PUT/POST/DELETE 0건)
- 사이클 81 silent 결함 차단 패턴 가시화 (`bfdy_clpr_present` 카드 노출)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속 — 본 사이클 변경 영역 (frontend pages/types/api/MSW/e2e fixtures) production 매매 코드 무관

## 7. 후속 사이클 인계

- **사이클 86** (통합 검증): Playwright E2E `e2e/stock-master.spec.ts` 신규 + 운영 측정 (history trigger INSERT 실측 + bfdy_clpr_present 비율 95%+ 검증)
- **사이클 87+** (Q7=B 90일 retention cron job, 사이클 84 인계 영속): `purge_old_stock_master_history()` 헬퍼

## 8. 영속 가드 명시 의무 (frontend-dev Green 단계)

- 사이클 65 H3 + 사이클 80 hotfix #1: 5 useQuery 모두 `retry: 1` *명시* (전역 default 의존 금지)
- 사이클 80 hotfix #3 LIFO: e2e api-mocks 등록 순서 = wildcard 1개 *먼저* + 5 구체 라우트 *후* (LIFO 우선 매칭)
- 사이클 80 hotfix #4: `tests/unit/e2e_mocks/test_cycle85_api_mocks_stock_master_lifo.py` 함수명 `after_wildcard` 의무 + assertion `구체 > wildcard` 의무
- 사이클 81 G-M5: 햄버거 Drawer 7개 메뉴 클릭 시 자동 close
- 사이클 68 KST: `Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul' })` 명시, `getHours()` 금지
- 사이클 41 StrategyFunnel: lazy import + Suspense skeleton
- 사이클 75 G-AST5: `_ast_api_mocks_coverage.test.ts` 영역 확장 시 `REQUIRED_STOCK_MASTER_ENDPOINTS` literal 의무
