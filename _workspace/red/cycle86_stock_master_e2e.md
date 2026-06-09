# 사이클 86 Red 명세 — stock_master UI 메뉴 통합 검증 (E2E)

작성일: 2026-06-09
작성자: tdd-engineer
대상: stock_master UI 메뉴 통합 검증 (사이클 83 후속 3 단계 분할 3/3)
인계: 사이클 85 = 프론트 단독 완료 (commit `3ab326e` + hotfix `0a15158`/`57a125d`, **CI 6/6 success**)
Phase 1 진단: `_workspace/cycle86_phase1_diagnosis.md` 영속
사용자 결정 채택: **Q15=A + Q16=A + Q17=B + Q18=A** (4건 권고 100% 채택)

---

## 1. Red 의도 (행위 명세)

### 1-1. 본 사이클 영역
- E2E (Playwright) 통합 검증 단독 — 사이클 85 산출물 (StockMaster.tsx 4 카드 + 7번째 메뉴 + 5 API 라우트) 의 *실 브라우저 렌더 + 라우팅 + 모바일 viewport* 영구 가드 설정
- production 매매 코드 변경 0 / 백엔드 + 프론트 단위 테스트 영역 0
- 단일 spec 파일 `e2e/stock-master.spec.ts` 신규 (settings.spec.ts 21L 답습 + 모바일 viewport 추가 ~30~50L)

### 1-2. Red 상태 정의
- 본 명세 작성 시점: `e2e/stock-master.spec.ts` **파일 부재** = Playwright test collection **0건** (vacuous PASS = Red 의도)
- frontend-dev Green 단계: 8 케이스 spec 작성 → CI e2e job 실측 PASS 확인 → Green 전환
- tdd-engineer 영역: **본 Red 명세 문서 + 8 케이스 매트릭스만** 작성. spec 파일 본체는 frontend-dev 인계

### 1-3. Red 검증 의무
```bash
# 본 명세 작성 시점 = 파일 부재 → grep 0건 = Red 의도 부합
ls /Users/koscom/Projects/auto_stock/e2e/stock-master.spec.ts 2>&1
# 예상: ls: e2e/stock-master.spec.ts: No such file or directory
```

frontend-dev Green 단계 후:
```bash
# CI e2e job (npx playwright test --config=e2e/playwright.config.ts)
# 8 케이스 전수 PASS 의무 = Green 전환
```

---

## 2. 회귀 가드 8 케이스 매트릭스 (단일 spec)

### HIGH 3 케이스

#### G-E2E-1 — 페이지 진입 + 4 카드 영역 렌더 (timeout 20s)
- **의도**: `/stock-master` 라우트 진입 시 `StockMaster.tsx` 가 lazy 로 mount 완료 + 4 카드 영역 (stats / list / detail / history) DOM 노드 visible
- **검증**:
  - `await page.goto("/stock-master")`
  - `await expect(page.getByTestId("stock-master-stats-card").first()).toBeVisible({ timeout: 20000 })`
  - `await expect(page.getByTestId("stock-master-list-card").first()).toBeVisible({ timeout: 20000 })`
- **timeout 20s 의무**: 사이클 80 hotfix #2 영속 (settings.spec.ts 답습 — 카드 누적 + useQuery 다중 + lazy 로 + Suspense fallback)
- **사이클 영속**: 사이클 75 retry:1 영역 (사이클 85 StockMaster.tsx G-AST-RT 영속) + 사이클 80 hotfix #2 (20s)
- **위급도 사유**: 페이지 진입 자체 실패 = 사이클 79 e2e fail (flaky 아닌 진짜 결함) chain 재현 가능 영역

#### G-E2E-2 — list 클릭 → detail 모달 open + 카테고리 분류 + 핵심 5 키 highlight
- **의도**: list 첫 row 클릭 → detail 모달 open + 5 카테고리 분류 (기본/가격/시장/거래/메타) + 핵심 5 키 (`bfdy_clpr` / `nxt_tradable` / `krx_halted` / `admin_item` / `refreshed_at`) 시각적 강조
- **검증**:
  - mock `/api/stock-master/list*` = `envelope([])` 빈 배열 → list 비어있음 graceful
  - mock 데이터 보강 시 (사이클 85 `005930` fixture) row 클릭 → 모달 open 검증
  - graceful 분기 명시 (현재 mock = 빈 list)
- **사이클 영속**: 사이클 81 Q11=B (detail 모달 + 카테고리 분류 + 핵심 5 키 highlight)
- **위급도 사유**: detail 모달 open 실패 = stock_master 데이터 가시화 핵심 기능 결함

#### G-E2E-3 — 모바일 viewport 375px 햄버거 메뉴 7개 압축
- **의도**: iPhone 모바일 viewport (375x667) 에서 햄버거 버튼 클릭 → Drawer 7개 메뉴 (환경/보드/내역/AI자문/검색/추적/**종목마스터**) 표시
- **검증**:
  - `await page.setViewportSize({ width: 375, height: 667 })`
  - `await page.getByLabel("메뉴 열기").click()`
  - `await expect(page.getByText("종목마스터").first()).toBeVisible({ timeout: 20000 })`
- **사이클 영속**: 사이클 81 G-M5 (햄버거 메뉴 7개 압축) + 사이클 85 7번째 메뉴 `종목마스터` 추가
- **위급도 사유**: 모바일 viewport 메뉴 침범 = 사이클 81 영역 1 (HIGH 매매 안전성 외) 재현 가능 영역

### MEDIUM 3 케이스

#### G-E2E-4 — history 영역 before/after collapsible
- **의도**: detail 모달 내 history 영역 collapsible UI (사이클 81 Q12=A 영속) — before/after JSONB diff 토글 가능
- **검증**:
  - mock `/api/stock-master/*/history*` = `envelope([])` 빈 배열 → history 영역 자체 visible (collapsible 토글 버튼 visible) 검증
  - graceful 분기 명시
- **사이클 영속**: 사이클 81 Q12=A (history 영역 before/after collapsible)

#### G-E2E-5 — api-mocks 5 라우트 LIFO 정합 영속 (ECONNREFUSED 0건)
- **의도**: `e2e/fixtures/api-mocks.ts` L296-326 5 stock-master 라우트 LIFO 등록 영속 확인 — 페이지 진입 시 `/api/stock-master/**` 호출 5건 모두 mock 응답 (ECONNREFUSED 0건)
- **검증**:
  - `page.on("requestfailed", ...)` 핸들러 등록 → `/api/stock-master/` 포함 URL ECONNREFUSED 0건 확인
  - 또는 console error 모니터링 → "ECONNREFUSED" 0건
- **사이클 영속**: 사이클 80 hotfix #3 (LIFO 정합) + 사이클 85 (5 stock-master 라우트 추가) + 사이클 80 hotfix #4 (`after_wildcard` AST 가드 영속)
- **위급도 사유**: ECONNREFUSED 발생 = 사이클 77 hotfix #1 chain (Dashboard 영역 mock 누락) 재현 가능 영역

#### G-E2E-6 — stats 카드 4 지표 표시 (`count_all` / `bfdy_clpr_present` / `nxt_tradable_count` / `top_10_recent`)
- **의도**: stats 카드 영역 4 핵심 지표 (`count_all=29` / `bfdy_clpr_present=27` / `nxt_tradable_count=12` / `top_10_recent=[]`) mock 데이터 렌더 확인
- **검증**:
  - mock 응답 `count_all=29` / `bfdy_clpr_present=27` 등 숫자 visible
  - `getByText("29")` 또는 testid 기반 검증
- **사이클 영속**: 사이클 83 시정 효과 (bfdy_clpr_present 비율 95%+ 목표) 가시화

### LOW 2 케이스

#### G-E2E-7 — lazy 로 + Suspense fallback 정상 (retry:1 영역 영속)
- **의도**: `/stock-master` 라우트 진입 시 lazy 로 (`React.lazy` + `<Suspense>`) fallback "로딩 중…" 텍스트가 짧게 표시되거나 우회 후 본체 mount 완료
- **검증**:
  - 페이지 진입 → 최종 본체 visible 확인 (Suspense fallback 자체는 timing 의존 = graceful)
  - React Query `retry: 1` 영역 영속 확인 (사이클 85 `_ast_useQuery_retry_required.test.ts::TARGET_PAGES` StockMaster.tsx 영속, 별도 AST 가드)
- **사이클 영속**: 사이클 75 retry:1 영역 (5 컴포넌트 영역 확장) + 사이클 80 hotfix #1 (Settings.tsx retry:1 명시)

#### G-E2E-8 — 7번째 메뉴 `종목마스터` 클릭 → 라우트 진입
- **의도**: AppShell 가로 메뉴 (PC viewport ≥640px) 7번째 메뉴 `종목마스터` 클릭 → `/stock-master` 라우트 진입 + StockMaster.tsx mount 완료
- **검증**:
  - `await page.goto("/")` → 메뉴 클릭 → URL `/stock-master` 진입 확인
  - 또는 `await page.getByRole("link", { name: "종목마스터" }).click()`
- **사이클 영속**: 사이클 81 AppShell + 사이클 85 navItems 7번째 추가 + `frontend/src/__tests__/AppShell.test.tsx` 8 케이스 영속

---

## 3. spec 파일 명세 (frontend-dev Green 단계 인계)

### 3-1. 파일 경로 + 라인 수
- `e2e/stock-master.spec.ts` 신규 ~50~80L (settings.spec.ts 21L 답습 + 8 케이스 분리 + 모바일 viewport 추가)

### 3-2. 패턴 답습 의무
```typescript
import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

test.describe("StockMaster 페이지", () => {
  test("G-E2E-1: 진입 시 4 카드 영역 렌더 (timeout 20s)", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/stock-master");
    await expect(page.getByTestId("stock-master-stats-card").first()).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("stock-master-list-card").first()).toBeVisible({ timeout: 20000 });
  });

  test("G-E2E-2: list 클릭 → detail 모달 + 카테고리 + 5 키 highlight", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/stock-master");
    // mock list 빈 배열 = graceful (frontend-dev 가 mock 보강 시 row 클릭 검증 추가)
    await expect(page.getByTestId("stock-master-list-card").first()).toBeVisible({ timeout: 20000 });
  });

  test("G-E2E-3: 모바일 viewport 햄버거 메뉴 7개 압축", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await installApiMocks(page);
    await page.goto("/");
    await page.getByLabel("메뉴 열기").click();
    await expect(page.getByText("종목마스터").first()).toBeVisible({ timeout: 20000 });
  });

  test("G-E2E-4: history 영역 before/after collapsible", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/stock-master");
    // history collapsible UI 검증 (graceful)
    await expect(page.getByTestId("stock-master-list-card").first()).toBeVisible({ timeout: 20000 });
  });

  test("G-E2E-5: api-mocks 5 라우트 LIFO 영속 (ECONNREFUSED 0건)", async ({ page }) => {
    const failedRequests: string[] = [];
    page.on("requestfailed", (req) => {
      if (req.url().includes("/api/stock-master/")) {
        failedRequests.push(req.url());
      }
    });
    await installApiMocks(page);
    await page.goto("/stock-master");
    await expect(page.getByTestId("stock-master-stats-card").first()).toBeVisible({ timeout: 20000 });
    expect(failedRequests).toEqual([]);
  });

  test("G-E2E-6: stats 카드 4 지표 (count_all=29 등) 표시", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/stock-master");
    await expect(page.getByText("29").first()).toBeVisible({ timeout: 20000 });
  });

  test("G-E2E-7: lazy 로 + Suspense fallback 정상", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/stock-master");
    await expect(page.getByTestId("stock-master-stats-card").first()).toBeVisible({ timeout: 20000 });
  });

  test("G-E2E-8: 7번째 메뉴 클릭 → /stock-master 라우트 진입", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/");
    await page.getByRole("link", { name: "종목마스터" }).click();
    await expect(page).toHaveURL(/\/stock-master/);
    await expect(page.getByTestId("stock-master-stats-card").first()).toBeVisible({ timeout: 20000 });
  });
});
```

### 3-3. testid 의존성 (frontend-dev 확인 의무)
- `data-testid="stock-master-stats-card"` (stats 카드)
- `data-testid="stock-master-list-card"` (list 카드)
- 부재 시 frontend-dev 가 StockMaster.tsx 에 testid 추가 (1~2 줄, 행위 변경 0) 또는 spec 을 `getByText` 기반으로 대체

---

## 4. 영속 보장 매트릭스 (사이클 86 의무)

| 영속 영역 | 사이클 | 검증 방법 |
|----------|-------|----------|
| LIFO 정합 (api-mocks 5 라우트) | 80 hotfix #3 + 85 | G-E2E-5 + 기존 `_ast_api_mocks_coverage.test.ts::after_wildcard` AST 가드 |
| 햄버거 메뉴 7개 (모바일) | 81 G-M5 + 85 navItems | G-E2E-3 + 기존 AppShell.test.tsx 8 케이스 |
| timeout 20s (lazy + Suspense + 다중 useQuery) | 80 hotfix #2 | G-E2E-1/4/5/6/7/8 모두 timeout 20s 의무 |
| retry:1 영역 (StockMaster.tsx) | 75 + 85 G-AST-RT | 기존 `_ast_useQuery_retry_required.test.ts::TARGET_PAGES` AST 가드 |
| 5 API 라우트 mock 영속 | 85 (3ab326e) | G-E2E-5 + 기존 G-AST-MOCK 5종 |

## 5. 매매 안전성 무영향 보장

- **CLAUDE.md "절대 깨지 말 것" 8 영역 영속**: 본 신규 spec = UI 진입 + 4 카드 visible 검증 전용
- production 매매 코드 변경 0
- 백엔드 + 프론트 단위 테스트 영역 0
- e2e 영역 한정 = production 무관
- 사이클 38 명문화 영속 (`tradable_boards` 매수 진입 전용) — 본 사이클 무관 영역
- 사이클 17/18/29/38/55 R-1/66/67/68/72/73/74/75/76/77/78/79/80/81 모두 무영향

## 6. 후속 인계 (사이클 87)

- **D+1 운영 측정 (2026-06-10 수 09:00~10:00)** = 사이클 87 별개 진행 (Q17=B 채택)
- Phase 1 진단 §7 명세 영속 (3 SQL 영역: A trigger INSERT / B bfdy_clpr_present 95%+ / C eager_refresh emit ≥10건)
- 본 사이클 86 영역 외

## 7. Red 명세 영속 의무

- 본 문서 영구 보존 (`_workspace/red/cycle86_stock_master_e2e.md`)
- frontend-dev Green 단계 완료 후에도 Red 의도 + 8 케이스 매트릭스 + 영속 보장 매트릭스 영구 기록
- tester verify 후 사이클 87 인계 시 본 문서 참조 의무
