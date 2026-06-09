# 사이클 85 Phase 1 진단 (READ-ONLY)

작성일: 2026-06-09
작성자: team-leader (트레이더 관점)
대상: stock_master UI 메뉴 구축 — 프론트 단독 단계 (사이클 83 3 단계 분할 2/3)
인계: 사이클 84 = 백엔드 5 GET 라우트 + migration 032 + trigger 완료 (verify report `_workspace/cycle84_verify_report.md` 영속)
코드 변경: **0** (Phase 1 진단 단독)

---

## 1. 사이클 84 백엔드 인계 명세 (영속 확정)

### 5 GET 라우트 (`/api/stock-master/*`, ApiResponse 래퍼)

| 라우트 | 응답 | 페이징 | 비고 |
|--------|------|--------|------|
| `GET /stats` | `{count_all, bfdy_clpr_present, nxt_tradable_count, top_10_recent}` | × | 상태 카드 (4 키 + recent ticker top 10) |
| `GET /list?limit=100&offset=0` | `list[StockMasterRow]` (refreshed_at DESC) | limit ∈ [1,1000], offset ≥ 0 | 422 검증 영속 (V-5 4 sub-case PASS) |
| `GET /scan-pool/summary` | `{eager_refresh_today: int}` | × | 사이클 83 emit 카운트 |
| `GET /{ticker}/history?limit=100` | `list[{id, ticker, change_type, before_raw, after_raw, changed_at}]` | limit ∈ [1,1000] | DB trigger 자동 적재 (migration 032) |
| `GET /{ticker}` | StockBasics dict | × | 404 미존재 (V-5 PASS) |

### 운영 측정 영속 (verify report V-4)

- `stock_master_history` 테이블 0건 (운영 시작 시점) + `stock_master` 29건 → 다음 eager refresh 발화 시 trigger INSERT 측정 가능
- trigger AFTER INSERT/UPDATE/DELETE 3 이벤트 활성 확정
- 인덱스 3종: pkey + idx_smh_ticker_changed_at + idx_smh_changed_at

---

## 2. Phase 1 현황 분석

### 2-1. `frontend/src/App.tsx` 현 메뉴 구조 (사이클 81 햄버거 메뉴)

`navItems` 6개 (L15-22):
1. `/` 대시보드
2. `/history` 거래 내역
3. `/recommendations` 전략수정 AI자문
4. `/strategy-funnel` 조건검색 추적
5. `/logs` 로그
6. `/settings` 설정

**PC (sm 이상, L74-94)**: 가로 메뉴 + `whitespace-nowrap` + `flex-wrap`
**모바일 (sm 미만, L97-118)**: 햄버거 SVG 버튼 + `mobileOpen` state + `MobileMenuLabel` (L50-60) 현재 경로 한글 레이블
**Drawer (L122-147)**: 모바일 메뉴 6개 세로 배치 + 클릭 시 자동 close

**7번째 메뉴 `종목마스터` 추가 위치** (Q2=A 사용자 결정 영속):
- `navItems` 배열 7번째 row 추가 (`/stock-master` 라우트)
- `<Route path="/stock-master" element={<StockMaster />} />` Suspense 내부 lazy import (L13 패턴 답습)
- 모바일 햄버거 7개 압축 검증 (375px viewport) — 사이클 81 M-1~M-8 회귀 가드 갱신 의무

### 2-2. 기존 패턴 답습 (신규 파일 의무)

**`frontend/src/types/stock-master.ts` 신규** (사이클 65 `trade-amount-filter.ts` 20L 답습):
```ts
export interface StockMasterStats {
  count_all: number
  bfdy_clpr_present: number
  nxt_tradable_count: number
  top_10_recent: Array<{ ticker: string; name: string; refreshed_at: string }>
}
export interface StockMasterRow {
  ticker: string; name: string; excg_dvsn_cd: string | null
  nxt_tradable: boolean; krx_halted: boolean; admin_item: boolean
  raw: Record<string, unknown>
  refreshed_at: string  // KST +09:00 ISO
}
export interface StockMasterHistoryRow {
  id: number; ticker: string; change_type: string
  before_raw: Record<string, unknown> | null
  after_raw: Record<string, unknown> | null
  changed_at: string  // KST +09:00 ISO
}
export interface ScanPoolSummary {
  eager_refresh_today: number
}
```

**`frontend/src/api/stock-master.ts` 신규 5 함수** (사이클 65 `trade-amount-filter.ts` 35L 답습):
- `fetchStats() -> Promise<StockMasterStats>` (data.data 추출)
- `fetchList(limit, offset) -> Promise<StockMasterRow[]>`
- `fetchScanPoolSummary() -> Promise<ScanPoolSummary>`
- `fetchDetail(ticker) -> Promise<StockMasterRow>` (404 시 axios.isAxiosError 분기)
- `fetchHistory(ticker, limit) -> Promise<StockMasterHistoryRow[]>`

**`frontend/src/pages/StockMaster.tsx` 신규** (사이클 41 `StrategyFunnel.tsx` 305L 답습):
- 4 영역 (Q10 결정 영속 의제)

**`frontend/src/test/handlers.ts` 신규 5 MSW handler 추가** (vitest 단위 테스트용)

**`e2e/fixtures/api-mocks.ts` 신규 5 라우트 추가** (사이클 80 hotfix #3 LIFO 정합 영속 — 구체 라우트 *후* wildcard 가 fallback)

---

## 3. Phase 2 사용자 결정 의제 (Q10~Q14)

### Q10 (MEDIUM) UI 화면 구성 디테일

| 옵션 | 구성 | 장단점 |
|------|------|--------|
| **A 권고** | 단일 페이지 4 카드 (stats + list 테이블 + detail 모달 + history 테이블) | 단순 + 사이클 41 StrategyFunnel 패턴 답습 안정성 입증 |
| B | tab 구분 (상태 / list / scan-pool 3 tab) | 디테일 / 페이지 마운트 시 1 tab만 fetch |
| C | 사이드바 list + 메인 detail/history (master-detail) | UX 풍부 / 모바일 viewport 좁음 결함 위험 |

**team-leader 권고: 옵션 A** — 사이클 41 StrategyFunnel 답습 + 사이클 81 모바일 햄버거 메뉴 안정성 영속. 운영 진단 빈도 (사이클 81~83 chain 영속) 대비 단순 구조가 최적.

### Q11 (MEDIUM) ticker detail 표시 영역

| 옵션 | 표시 | 장단점 |
|------|------|--------|
| A | 67 키 전수 표 (1 행/키) | 정밀 / 운영자 압도 |
| **B 권고** | 카테고리 분류 (기본 4 / 가격 8 / 거래 6 / 플래그 5 / 메타 N) + 핵심 5 키 highlight (`bfdy_clpr` / `acml_tr_pbmn` / `nxt_tradable` / `krx_halted` / `admin_item`) | 사용성 + 사이클 81 SK스퀘어 진단 의무 답습 |
| C | 핵심 5 키 only + "전체 보기" toggle | 가벼움 / 진단 불충분 |

**team-leader 권고: 옵션 B** — 사이클 81 silent 결함 진단 의무 답습 + 운영자 가시화 우선.

### Q12 (LOW) history diff 표시 방식

| 옵션 | 표시 | 비고 |
|------|------|------|
| **A 권고** | before/after JSONB 전체 표시 (`<pre>` collapsible) | 단순 + 라이브러리 의존 0 |
| B | jsondiffpatch 라이브러리 | 번들 +30kB + 시각화 |
| C | 핵심 5 키 변경 항목만 highlight | 작전주 차단 영역 정밀 / 구현 부담 MEDIUM |

**team-leader 권고: 옵션 A** — 사이클 86 운영 측정 후 옵션 C 발의 가능 (LOW 후속 카드).

### Q13 (MEDIUM) auto-refresh polling 빈도

| 옵션 | 빈도 | 비고 |
|------|------|------|
| A | 30s | 사이클 83 effect 실시간 측정 / 부담 MEDIUM |
| **B 권고** | 60s | 운영 부담 균형 + KisAccountPoolCard 30s 패턴 답습 |
| C | 수동 refresh button only | 가벼움 / 진단 효율 LOW |

**team-leader 권고: 옵션 B** — `refetchInterval: 60_000` + staleTime 30_000. eager refresh 빈도 (24h TTL ~150건/day = 약 ~6/h) 대비 60s 폴링 충분.

### Q14 (HIGH) 사이클 85 종결 시점 push

| 옵션 | 시점 | 위험 |
|------|------|------|
| **A 권고** | 본 사이클 내 push (D+1 운영 측정 동행) | 사이클 86 통합 검증 *전* 운영 측정 시작 가능 / Playwright e2e 회귀 가능 |
| B | 사이클 86 (통합 검증) 동행 push | 안전 마진 / 운영 측정 지연 |
| C | 사이클 85 push + 사이클 86 통합 검증 별개 | 위험 분산 / 사이클 84 패턴 (READ-ONLY + 매매 hot path 무영향) 답습 |

**team-leader 권고: 옵션 C** — 사이클 84 verify (V-1 회귀 0 + V-7 매매 안전성 무영향) 영속 + 사이클 85 UI 레이어 한정 (production 매매 코드 변경 0) 으로 push 후 사이클 86 통합 검증 별개 진행 안전.

---

## 4. 회귀 가드 매트릭스 추정 (사이클 85 신규)

### HIGH 영속 의무 (5~7 케이스)

- **G-AST-RT (사이클 65 H3 + 사이클 75 G-RT 영속)**: `_ast_useQuery_retry_required.test.ts` 영역 확장 → `StockMaster.tsx` 추가. 신규 5 useQuery (`fetchStats` / `fetchList` / `fetchScanPoolSummary` / `fetchDetail` / `fetchHistory`) 모두 `retry: 1` 명시
- **G-AST-MOCK (사이클 75 G-AST5 + 사이클 80 hotfix #3 LIFO 영속)**: `_ast_api_mocks_coverage.test.ts` 영역 확장 → `REQUIRED_STOCK_MASTER_ENDPOINTS` 5종 추가. 등록 순서 = 구체 라우트 *후* wildcard 영속 (사이클 80 hotfix #4 `after_wildcard` 함수명 의무)
- **G-MOBILE-7 (사이클 81 G-M5 영속)**: `AppShell.test.tsx` M-1~M-8 갱신 → navItems 7개 압축 + MobileMenuLabel 매핑 7개 + 햄버거 Drawer 7개 클릭 후 close
- **G-KST (사이클 68 영속)**: `refreshed_at` / `changed_at` 모두 `Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul' })` 표시 (`new Date().getHours()` 금지)
- **G-RETRY-CARD (사이클 65 hotfix #1 영속)**: StockMaster.tsx 페이지의 5 useQuery 모두 직접 `retry: 1` 명시 (global default 의존 금지)

### MEDIUM (6~8 케이스)

- 5 useQuery 단위 fetch + 렌더
- 4 영역 페이지 render (stats / list / detail modal / history)
- 모바일 viewport (375px) responsive
- 404 처리 (`axios.isAxiosError` + status 404 분기)
- 422 처리 (limit < 1 / limit > 1000 / offset < 0)
- history diff 표시 (Q12 옵션 A `<pre>` collapsible)
- detail 카테고리 분류 표시 (Q11 옵션 B 5 카테고리)

### LOW (3~5 케이스)

- 사이클 83 `[scan_pool_eager_refresh]` literal 영속 (StockMaster 페이지 scan-pool summary 표시)
- 사이클 81 햄버거 메뉴 영속 (사이클 84 verify report V-9 답습)
- e2e api-mocks 5 라우트 LIFO 정합 (사이클 80 hotfix #3 영속)
- detail 핵심 5 키 highlight 시각 (`bfdy_clpr` / `acml_tr_pbmn` / `nxt_tradable` / `krx_halted` / `admin_item`)
- top_10_recent 카드 KST 표시

---

## 5. domain-expert 자문 필요 여부

**불요 가설 채택**:
- UI 레이어 한정 (production 매매 코드 변경 0)
- 사이클 84 백엔드 인계 명세 영속 확정 (5 GET 라우트 + ApiResponse 래퍼 + 페이징 + 404/422)
- Q10~Q13 모두 사이클 41 / 65 / 75 / 80 / 81 영속 패턴 답습 영역
- Q14 = 사이클 84 verify 영속 (매매 안전성 무영향 확정)

자문 의무 없음. tdd-engineer Red → frontend-dev Green 직행 가능.

---

## 6. 사용자 결정 요청 (단일 응답 회수)

다음 5개 의제에 대해 사용자 결정 회수 후 사이클 85 명세 발주:

- **Q10**: UI 구성 (A/B/C) — team-leader 권고 **A** (단일 페이지 4 카드)
- **Q11**: detail 표시 (A/B/C) — team-leader 권고 **B** (카테고리 분류 + 핵심 5 키 highlight)
- **Q12**: history diff (A/B/C) — team-leader 권고 **A** (단순 `<pre>`)
- **Q13**: polling 빈도 (A/B/C) — team-leader 권고 **B** (60s)
- **Q14**: push 시점 (A/B/C) — team-leader 권고 **C** (사이클 85 push + 사이클 86 별개 통합 검증)

---

## 7. 진행 흐름 (사용자 결정 회수 후)

1. tdd-engineer Red 명세 작성 → `_workspace/red/cycle85_stock_master_ui.md`
2. frontend-dev Green 구현 (4 신규 파일 + AppShell.test.tsx 갱신 + AST 가드 2 영역 확장)
3. tester verify (V-1~V-N 매트릭스)
4. Q14 결정에 따라 push 시점 분기

## 8. 주의사항 (사이클 85 진행 시 영속)

- **매매 안전성 무영향 보장**: UI 레이어 한정. Read-only 5 GET 라우트 호출만 (PUT/POST/DELETE 0건)
- **CLAUDE.md "절대 깨지 말 것" 8 영역 영속**: 본 신규 UI = 진단 가시화 전용
- **사이클 65 hotfix #1/#2/#3 영속**: useQuery `retry: 1` 명시 의무 (G-AST-RT 영역 확장)
- **사이클 80 hotfix #3 LIFO 정합 영속**: e2e api-mocks 구체 라우트 *후* wildcard (G-AST-MOCK 영역 확장)
- **사이클 81 햄버거 메뉴 영속**: 7번째 메뉴 추가 시 모바일 viewport (375px) 침범 0 (G-MOBILE-7 갱신)
- **사이클 68 KST 일관성**: `Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul' })` 명시 의무
- **운영 효과 측정 (사이클 86 verify)**: 사이클 83 시정 효과 stock_master count 29 → 150+ + `bfdy_clpr_present` 비율 → 95%+ + history 적재 (trigger INSERT) 실측 PASS 의무
