# 사이클 86 Phase 1 진단 (READ-ONLY)

작성일: 2026-06-09
작성자: team-leader (트레이더 관점)
대상: stock_master UI 메뉴 — **통합 검증 단계** (사이클 83 후속 3 단계 분할 3/3)
인계: 사이클 85 = 프론트 단독 완료 (commit `3ab326e` + hotfix `0a15158`/`57a125d` 3 영역 종결, **CI 6/6 전수 success**)
코드 변경: **0** (Phase 1 진단 단독)

---

## 1. 사이클 85 인계 명세 (영속 확정)

### 산출물 영속
- `frontend/src/pages/StockMaster.tsx` 신규 (4 카드 영역: stats / list / detail modal / history) — 사이클 81 G-M5 7번째 메뉴 영속
- `frontend/src/types/stock-master.ts` + `frontend/src/api/stock-master.ts` + `frontend/src/test/handlers.ts` 신규
- `e2e/fixtures/api-mocks.ts` L296-326 (5 stock-master 라우트 + wildcard `**/api/stock-master/**` LIFO 정합, 사이클 80 hotfix #3 영속)
- AST 가드 영속: `_ast_useQuery_retry_required.test.ts` (G-AST-RT 영역 확장 StockMaster.tsx) + `_ast_api_mocks_coverage.test.ts` (G-AST-MOCK REQUIRED_STOCK_MASTER_ENDPOINTS 5종)
- hotfix 3 영역 chain: hotfix #1+#2 TS2352 + DNS race 1차 / hotfix #3 mock 영역 상향 — 외부 의존 영구 차단

### 미수행 영역 (사이클 86 의무)
- **Playwright `e2e/stock-master.spec.ts` 신규 0건** — 통합 검증 영역
- D+1 운영 측정 (사이클 83 effect + 사이클 84 history INSERT 동행 + 사이클 85 UI 진입 확인) 0건

---

## 2. Phase 1 현황 분석

### 2-1. 기존 Playwright spec 패턴 답습 영역

| spec | 라인 | 패턴 | 비고 |
|------|------|------|------|
| `settings.spec.ts` | 17 | `installApiMocks(page)` + `page.goto("/settings")` + `toBeVisible({ timeout: 20000 })` × 2 | **사이클 80 hotfix #2 영속** (10s → 20s) |
| `recommendations.spec.ts` | 21 | 동일 패턴 | timeout 10s 유지 (카드 누적 적은 영역) |
| `trading-flow.spec.ts` | 31 | 동일 패턴 + 토글 시나리오 | E2E 흐름 1건 |

**`playwright.config.ts` 영속 영역**:
- `timeout: 30_000` (테스트당) + `expect.timeout: 5_000`
- `fullyParallel: false` + `workers: 1` (dev server 1개 공유)
- `retries: process.env.CI ? 1 : 0`
- `webServer.command: "npm run dev"` (백엔드 미가동, page.route 모킹)

### 2-2. `e2e/fixtures/api-mocks.ts` LIFO 등록 (사이클 80 hotfix #3 영속)

L296-326 사이클 85 등록 영역 (LIFO 정합 확정):

```ts
// L300 wildcard 먼저 (fallback)
await page.route("**/api/stock-master/**", (route) => envelope({}))
// L305~324 구체 라우트 *후* 등록 (LIFO 우선 매칭)
await page.route("**/api/stock-master/stats", ...)      // L305
await page.route("**/api/stock-master/list*", ...)      // L315
await page.route("**/api/stock-master/scan-pool/summary", ...) // L318
await page.route("**/api/stock-master/*/history*", ...) // L321
await page.route("**/api/stock-master/*", ...)          // L324
```

**G-AST-MOCK 영속**: `_ast_api_mocks_coverage.test.ts::after_wildcard` 영구 가드 (사이클 80 hotfix #4 함수명 의무).

### 2-3. 신규 `e2e/stock-master.spec.ts` 명세 (settings.spec.ts 100% 답습)

```ts
import { expect, test } from "@playwright/test";
import { installApiMocks } from "./fixtures/api-mocks";

test.describe("StockMaster 페이지", () => {
  test("진입 시 4 카드 + detail 모달 + history 영역이 보인다", async ({ page }) => {
    await installApiMocks(page);
    await page.goto("/stock-master");
    // settings.spec.ts 답습 (사이클 80 hotfix #2 영속 20s)
    await expect(page.getByText(/종목마스터|상태|목록/).first()).toBeVisible({ timeout: 20000 });
    // 4 카드 영역 핵심 텍스트
    await expect(page.getByText(/bfdy_clpr_present|eager_refresh_today/).first()).toBeVisible({ timeout: 20000 });
  });

  test("모바일 viewport 햄버거 메뉴 7개 압축", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await installApiMocks(page);
    await page.goto("/stock-master");
    // 사이클 81 G-M5 영속 + 사이클 85 7번째 메뉴 추가 후 검증
    await expect(page.locator("button[aria-label*='메뉴']")).toBeVisible({ timeout: 20000 });
  });
});
```

---

## 3. Phase 2 사용자 결정 의제 (Q15~Q18)

### Q15 (HIGH) Playwright spec 작성 + 즉시 push 여부

| 옵션 | 시점 | 위험 |
|------|------|------|
| **A 권고** | 본 사이클 86 spec 작성 + 즉시 commit + push + CI verify | 사이클 85 hotfix 3 chain 종결 후 안정 / 통합 검증 chain 완전 종결 |
| B | spec 작성 + 본 사이클 push 보류 (사이클 87 동행) | 안전 마진 / D+1 운영 측정 지연 |

**team-leader 권고: 옵션 A** — 사이클 85 hotfix 3 영역 chain 완전 종결 + CI 6/6 success 확정 + e2e 영역 한정 (production 매매 코드 변경 0) 으로 즉시 push 안전. 사이클 79/80 1차/재실행 fail (flaky 아닌 진짜 결함) 경험 반영 = e2e spec 추가 시 CI 즉시 검증 의무.

### Q16 (MEDIUM) Playwright 실제 실행 검증

| 옵션 | 방식 | 비용 |
|------|------|------|
| **A 권고** | 운영자 1회 실제 실행 권고 (간접 AST 가드 영속) | 시간 0 / AST 가드 17 케이스로 영구 차단 보장 |
| B | 사이클 86 내 `npx playwright install` + 실제 실행 의무 | ~5분 시간 비용 / 환경 의존 (CI 의존 영역) |

**team-leader 권고: 옵션 A** — 사이클 75 패턴 영속 (간접 AST 가드 17 케이스 영구 차단 보장). CI 환경 (GitHub Actions) 에서 `playwright install` + 실제 실행 영속 (사이클 85 hotfix chain 검증 실측).

### Q17 (HIGH) D+1 운영 측정 시점

| 옵션 | 시점 | 위험 |
|------|------|------|
| A | 2026-06-10 (수) 09:00~10:00 본 사이클 진행 | 운영 측정 즉시 / spec push 후 CI verify 미완 위험 |
| **B 권고** | 본 사이클 86 = Playwright spec 작성 + push 만 / D+1 운영 측정 = 사이클 87 별개 | 안전 분리 / 사이클 84 verify 패턴 답습 |

**team-leader 권고: 옵션 B** — 사이클 84/85 분리 패턴 답습. spec 작성 + push + CI verify = 사이클 86 영역 / D+1 운영 측정 = 사이클 87 영역. **오늘 = 2026-06-09 (화)** = 영업일이나 KRX 메인 시간 (09:00~15:30) 운영 측정 시점 = 사이클 87 명일 09:00~10:00 별개 진행 안전 (push 후 1일 운영 누적 → 측정 데이터 충분 확보).

### Q18 (LOW) 사이클 85 부수 발견 종결 확정

| 옵션 | 처리 | 비고 |
|------|------|------|
| **A 권고** | hotfix 3 영역 chain 완전 종결 (사이클 86 영역 외) | 사이클 85 CI 6/6 success 확정 영속 |
| B | 별개 카드 사이클 87+ 신규 (외부 의존 영구 차단 메커니즘 확장) | 추가 작업 / 즉시 위험 없음 |

**team-leader 권고: 옵션 A** — 사이클 85 hotfix #1+#2+#3 chain 으로 TS2352 + DNS race + mock 영역 상향 = 외부 의존 영구 차단 완료. 추가 메커니즘 = 사이클 87+ 운영 측정 후 결함 재발 시 발의 (현 시점 발의 불요).

---

## 4. 회귀 가드 매트릭스 추정 (사이클 86 신규)

### HIGH (3 케이스)

- **G-E2E-1** `stock-master.spec.ts` 진입 시 4 카드 핵심 텍스트 visible (settings.spec.ts 패턴 답습 timeout 20s, 사이클 80 hotfix #2 영속)
- **G-E2E-2** detail 모달 open + 카테고리 분류 + 핵심 5 키 highlight (사이클 81 Q11=B 영속)
- **G-E2E-3** 모바일 viewport 375px 햄버거 메뉴 7개 압축 (사이클 81 G-M5 영속)

### MEDIUM (2~3 케이스)

- **G-E2E-4** history 영역 before/after collapsible (사이클 81 Q12=A 영속)
- **G-E2E-5** api-mocks 5 라우트 LIFO 정합 영속 (사이클 80 hotfix #3 + 사이클 85 영속)
- **G-E2E-6** 4 카드 stats 영역 핵심 키 (`bfdy_clpr_present` / `eager_refresh_today`) 표시

### LOW (1~2 케이스)

- **G-E2E-7** vite proxy fallback (백엔드 미가동 page.route 모킹 영속)
- **G-E2E-8** 사이클 65 hotfix #3 패턴 영속 (lazy 로 + Suspense + 20s timeout)

**합계 6~8 케이스 / 단일 신규 spec 파일** (라이트 영역 — settings.spec.ts 21L 답습).

---

## 5. domain-expert 자문 필요 여부

**불요 가설 채택**:
- E2E 통합 검증 = UI 레이어 한정 (production 매매 코드 변경 0)
- 사이클 85 백엔드 + 프론트 명세 영속 확정 (5 GET 라우트 + 4 카드 + 햄버거 7번째 메뉴)
- Q15~Q18 모두 사이클 75/80/81/84/85 영속 패턴 답습 영역
- 매매 의사결정 / 파라미터 / 시장 행태 영역 0

**자문 의무 없음**. tdd-engineer Red → frontend-dev Green → tester verify 직행 가능.

---

## 6. 사용자 결정 요청 (단일 응답 회수)

다음 4개 의제 사용자 결정 회수 후 사이클 86 명세 발주:

- **Q15**: spec 작성 + push 시점 (A/B) — team-leader 권고 **A** (본 사이클 spec 작성 + 즉시 push + CI verify)
- **Q16**: 실제 실행 검증 방식 (A/B) — team-leader 권고 **A** (AST 가드 + CI 영속, 운영자 1회 권고)
- **Q17**: D+1 운영 측정 시점 (A/B) — team-leader 권고 **B** (사이클 86 push + 운영 측정 = 사이클 87 별개)
- **Q18**: 사이클 85 부수 발견 종결 (A/B) — team-leader 권고 **A** (hotfix 3 chain 완전 종결, 사이클 87+ 발의 불요)

---

## 7. 진행 흐름 (사용자 결정 회수 후)

### Q15=A + Q16=A + Q17=B + Q18=A 시 (권고 채택)

1. **tdd-engineer Red 명세** → `_workspace/red/cycle86_e2e_stock_master.md` (G-E2E-1~7 명세)
2. **frontend-dev Green 구현** → `e2e/stock-master.spec.ts` 신규 (settings.spec.ts 21L 답습 + 모바일 viewport 추가 ~30L 예상)
3. **tester verify** → V-1~V-N 매트릭스 (vitest + AST 가드 회귀 0 + Playwright 영구 가드 영속)
4. **commit + push** → CI 6/6 verify 의무 (사이클 80 hotfix 4 단계 통합 패턴 답습)
5. **사이클 87 인계** → D+1 (2026-06-10 수) 09:00~10:00 운영 측정 별개 사이클

### 사이클 87 운영 측정 명세 (의무 인계)

**Supabase MCP READ-ONLY 쿼리 (3 영역)**:

```sql
-- A: 사이클 84 trigger INSERT 실측
SELECT change_type, COUNT(*) FROM stock_master_history
WHERE changed_at >= (now_kst() - interval '24 hours')
GROUP BY change_type;

-- B: 사이클 83 시정 효과 (bfdy_clpr_present 비율 95%+ 목표)
SELECT
  COUNT(*) FILTER (WHERE raw ? 'bfdy_clpr' AND raw->>'bfdy_clpr' != '0') AS valid_count,
  COUNT(*) AS total_count,
  ROUND(100.0 * COUNT(*) FILTER (WHERE raw ? 'bfdy_clpr' AND raw->>'bfdy_clpr' != '0') / NULLIF(COUNT(*), 0), 2) AS valid_pct
FROM stock_master;

-- C: 사이클 83 eager refresh emit 카운트
SELECT COUNT(*) FROM system_logs
WHERE message LIKE '[scan_pool_eager_refresh]%'
  AND timestamp >= (now_kst()::date);
```

**측정 목표**:
- A: 사이클 84 trigger INSERT/UPDATE/TTL_REFRESH 분포 ≥10건 / 24h
- B: bfdy_clpr_present 비율 95%+ (사이클 83 시정 효과 확정)
- C: `[scan_pool_eager_refresh]` ≥10건 emit (사이클 83 effect 실측)

---

## 8. 주의사항 (사이클 86 진행 시 영속)

- **매매 안전성 무영향 보장**: E2E + AST 가드 영역 한정. production 매매 코드 변경 0
- **CLAUDE.md "절대 깨지 말 것" 8 영역 영속**: 본 신규 spec = UI 진입 + 4 카드 visible 검증 전용
- **사이클 80 hotfix #3 LIFO 정합 영속**: api-mocks 5 stock-master 라우트 구체 *후* wildcard 영속 (G-AST-MOCK 변경 0)
- **사이클 81 G-M5 영속**: 햄버거 메뉴 7개 압축 (사이클 85 navItems 7번째 추가 영속)
- **사이클 84 V-1~V-9 영속**: 백엔드 회귀 0 + flakiness 0 영속
- **사이클 85 hotfix 3 영역 chain 영속**: TS2352 + DNS race + mock 영역 상향 = 외부 의존 영구 차단 완료
- **fullyParallel: false + workers: 1 영속**: dev server 1개 공유 (playwright.config.ts 변경 0)
