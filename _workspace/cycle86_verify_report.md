# 사이클 86 tester verify 보고서 — stock_master UI 메뉴 통합 검증

작성일: 2026-06-09
작성자: tester
대상: 사이클 86 e2e 통합 검증 (Red `_workspace/red/cycle86_stock_master_e2e.md` + Green `e2e/stock-master.spec.ts`)
결과: **FAIL — 시정 의뢰 필요** (백엔드 AST 가드 1건 FAIL = silent 결함 검출)

---

## 총평 (Executive Summary)

사이클 86 e2e spec 8 케이스 매트릭스 자체는 의도와 부합하나, **사이클 65 hotfix #3 영구 가드 (`tests/unit/e2e_mocks/test_e2e_spec_timeout_required.py`) 위반** 으로 백엔드 전체 회귀 1 FAIL 발생. AST 가드가 정확히 본 silent 결함을 검출 — *영속 가드 매트릭스가 의도대로 작동* 한 셈이나, 사이클 86 산출물은 *현 상태 push 불가*. frontend-dev 에 timeout 명시 4 사이트 시정 의뢰 후 재검증 필요.

---

## V-1 (HIGH) 백엔드 + 프론트 전체 회귀 — **FAIL**

### 백엔드
- 실측: `1 failed, 2157 passed, 2 skipped, 2 xfailed in 51.33s`
- 기대: `2158 PASS + 2 XFAIL + 2 skip 영속`
- 차이: **`tests/unit/e2e_mocks/test_e2e_spec_timeout_required.py::test_e2e_spec_files_must_specify_timeout_for_tobevisible` 1 FAIL**

### 프론트
- 실측: `Test Files 41 passed (41) / Tests 223 passed (223)` (3.46s)
- 기대: `223 PASS 영속` — **PASS** (Array.isArray 가드 hotfix + spec 신규 모두 무영향)

### 합계
- 실측 합계 PASS: 2157 + 223 = 2380 (기대 2381 대비 -1)
- **회귀 발생 = FAIL**

---

## V-2 (HIGH) flakiness 3 회 반복 — 부분 검증

- 백엔드 e2e_mocks: 2 회 반복 모두 동일 FAIL (deterministic failure = flaky 아닌 진짜 결함 확정)
- 프론트: 2 회 반복 모두 223 PASS (deterministic = flakiness 0)
- 3 회째는 시정 후 진행 권고

---

## V-3 (HIGH) Playwright e2e 8 케이스 — 미실행 (로컬 환경)

- 본 tester verify 환경에서 `npx playwright test e2e/stock-master.spec.ts` 미실행 (CI e2e job 위임)
- frontend-dev 보고 = 로컬 5.4s 8 케이스 PASS (참조)
- **시정 후 CI 6/6 job success 확인 의무** (사이클 80 hotfix #4 영속 매트릭스)

---

## V-4 (HIGH) 영속 의무 매트릭스 — **위반 1건**

| 영속 영역 | 사이클 | 검증 결과 |
|----------|-------|----------|
| 사이클 75 G-RT retry:1 | StockMaster.tsx | PASS (vitest AST 영속) |
| **사이클 65 hotfix #3 toBeVisible timeout 명시** | e2e/*.spec.ts | **FAIL** (stock-master.spec.ts 4 사이트 위반) |
| 사이클 80 hotfix #3 Playwright LIFO 정합 | api-mocks 5 stock-master 라우트 | PASS (실측 L300/305/315/318/321/324 wildcard 전 구체 라우트 LIFO 정합) |
| 사이클 81 M-1~M-8 햄버거 메뉴 7개 압축 | AppShell.test.tsx | PASS |
| 사이클 84 5 GET 라우트 ApiResponse | 백엔드 | PASS (회귀 0) |
| 사이클 85 G-AST-LIFO | api-mocks | PASS |

### 위반 상세 (사이클 65 hotfix #3)

`e2e/stock-master.spec.ts` 의 timeout 옵션 미명시 4 사이트:
- L84: `await expect(page.getByTestId("mobile-menu-drawer")).not.toBeVisible();` — drawer 부재 검증 (`not.toBeVisible()` 도 정규식 매칭)
- L96: `await expect(drawer.getByText("대시보드")).toBeVisible();`
- L97: `await expect(drawer.getByText("거래 내역")).toBeVisible();`
- L98: `await expect(drawer.getByText("설정")).toBeVisible();`

AST 가드 정규식 `\.toBeVisible\(\s*\)` 에 정확히 매칭. 사이클 64+65 카드 누적으로 페이지 어셈블 5s 초과 위험 영역.

---

## V-5 (HIGH) 매매 안전성 무영향 — **PASS**

- production 매매 코드 변경 0 확인 (`git status` 결과 `frontend/src/pages/StockMaster.tsx` Array.isArray 가드 단독)
- StockMaster.tsx Array.isArray 가드 = 방어 코드만 (배열 응답 시 행위 동일)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속 (체결통보/uvicorn/주문번호 매핑/race 가드/reset_daily_state/익일 청산/NXT 좀비 차단/WebSocket 4중 안전망)
- 사이클 17/18/29/38/55 R-1/66/67/68/72/73/74/75/76/77/78/79/80/81/82/83/84/85 모두 무영향

---

## V-6 (MEDIUM) testid 의존성 — **PASS**

- `stock-master-stats-card` / `stock-master-list-card` / `stock-master-stats-eager-refresh-today` / `stock-master-history-card-loading` / `mobile-menu-drawer` 모두 spec 내 참조 일관성 확인
- StockMaster.tsx 내 testid 정의 영속 (사이클 85 산출물)

---

## V-7 (MEDIUM) 사이클 86 부수 발견 종결 — **PASS**

1. Array.isArray 가드 (StockMaster.tsx L292-296) = 운영 무영향 (mock 환경 한정 결함) — **종결**
2. G-E2E-3 모바일 drawer 정밀 검출 (`drawer.getByText`) = 사이클 81 G-M5 보강 — **종결**
3. G-E2E-2 stats 숫자 → 레이블 우회 = 운영 환경 정확성 백엔드 보장 — **종결**

---

## V-8 (MEDIUM) 사이클 87 (D+1 운영 측정) 인계 — **유효**

- 시점: 2026-06-10 (수) 09:00~10:00 1h
- Supabase MCP READ-ONLY 3 쿼리 명세 영속 (Red §7 + Phase 1 진단 §7)

---

## 시정 의뢰 (frontend-dev 인계)

### 즉시 시정 (HIGH, push 차단)

`e2e/stock-master.spec.ts` 4 사이트에 timeout 옵션 명시 추가:

```diff
- await expect(page.getByTestId("mobile-menu-drawer")).not.toBeVisible();
+ await expect(page.getByTestId("mobile-menu-drawer")).not.toBeVisible({ timeout: 5000 });

- await expect(drawer.getByText("대시보드")).toBeVisible();
+ await expect(drawer.getByText("대시보드")).toBeVisible({ timeout: 20000 });

- await expect(drawer.getByText("거래 내역")).toBeVisible();
+ await expect(drawer.getByText("거래 내역")).toBeVisible({ timeout: 20000 });

- await expect(drawer.getByText("설정")).toBeVisible();
+ await expect(drawer.getByText("설정")).toBeVisible({ timeout: 20000 });
```

사이클 80 hotfix #2 + 사이클 65 hotfix #3 패턴 답습 (timeout 20s, drawer 내부 메뉴는 이미 open 후 상태이나 영속 정합).
`not.toBeVisible` 는 drawer 부재 즉시 검증이므로 짧은 timeout (5s) 도 무방.

### 재검증 시나리오

1. frontend-dev 4 사이트 timeout 추가
2. `python -m pytest tests/unit/e2e_mocks/test_e2e_spec_timeout_required.py` PASS 확인
3. `python -m pytest -q` 전체 2158 PASS + 2 XFAIL + 2 skip 영속 확인
4. 로컬 또는 CI `npx playwright test e2e/stock-master.spec.ts` 8 케이스 PASS 영속 확인
5. flakiness 3 회 반복

---

## silent 결함 영구 차단 누적

사이클 65 hotfix #3 AST 가드가 사이클 86 silent 결함 (timeout 미명시) 을 *프로덕션 결함화 직전* 검출 = AST 영구 가드 매트릭스 실효성 입증.
silent 결함 영구 차단 누적: 19 → **20 회** (시정 후 종결 시).

---

## 결론

사이클 86 = **현 상태 push 불가**. frontend-dev 시정 (4 사이트 timeout 추가, ~5 분 작업) 후 tester 재검증 1회 + CI 6/6 job success 확인 후 종결 가능. 시정 자체는 LOW 위급도 (e2e 영역 한정, 매매 안전성 무영향) 이나 push 차단 영역 (AST 가드 영속 의무).

D+1 운영 측정 (사이클 87, 2026-06-10 수 09:00~10:00) 명세는 영속 유효.
