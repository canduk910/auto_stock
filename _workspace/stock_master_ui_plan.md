# stock_master 상태 + 변경기록 UI 메뉴 구축 계획서

작성일: 2026-06-09
작성자: team-leader (트레이더 관점)
배경 사이클: 81 (가격필터 키 시정) → 82 (진단) → 83 (eager refresh 시정) chain
코드 변경: **0** (구축 계획서 단독, 사용자 결정 의제 Q1~Q5 제시 + 사이클 분할 권고)

---

## 1. 배경 (현장 관점)

### 1-1. 사이클 81~83 chain 핵심 발견 (운영 실증)

- 사이클 81: `_apply_price_filter` 가 `bfdy_clpr` 키 (CTPF1002R 정본) 미사용 → **SK스퀘어 (402340) 1,122,340원** 이 사용자 설정 `price_filter_max=500,000원` 2배 초과해도 funnel "최종 prepared 12" 통과. 1줄 시정 (L166 `prdy_clpr` → `bfdy_clpr`).
- 사이클 82 진단: stock_master 운영 적재 = **14건 한정** (보유/익일청산 위주, `_boot()` eager refresh 영역). 후보 풀 ~150~500건 중 ~90% 가 `bfdy_clpr <= 0` (= stock_master 미적재) 시 graceful 통과 경로 진입 → 가격필터 우회.
- 사이클 83 시정: eager refresh 영역 확장 (scanner 후보 풀 합집합 + sequential cap + 24h fresh skip). 시정 후 stock_master 14 → **150+ 건 예상**.

### 1-2. 운영 가시화 의무 (트레이더 관점)

stock_master 는 **매수 진입/익일 청산 직전 거부 차단의 핵심 사전 판별 데이터** (NXT 거래가능 / `bfdy_clpr` / `acml_tr_pbmn` / `krx_halted` / `admin_item`). 14건 한정 영속 결함이 **30일+ 동안 silent** 으로 누적된 사실 (사이클 82 진단 영속) = **운영 가시화 부재가 silent 결함 영속 차단 실패의 직접 원인**.

신규 UI 메뉴 의의:
1. **사이클 83 시정 효과 운영 측정** (14 → 150+ count 추이 + 24h TTL refresh 빈도 + eager refresh trigger 빈도)
2. **미래 silent 결함 영구 진단 가시화** (적재 누락 / 키 분포 이상 / TTL 만료 폭주 / `nxt_tradable=False` 폭주)
3. **개별 ticker 검증** (운영자가 특정 종목 raw 67 키 전수 확인 — 사이클 81 SK스퀘어 케이스 진단 의무 답습)

---

## 2. Phase 1 — 현황 분석 (READ-ONLY 완료)

### 2-1. `src/db/stock_master.py` 모듈 명세 (현재)

**컬럼** (사이클 G2 + 사이클 68 KST 답습 영속):
- `ticker` PK (KRX 6자리 — `inquire_stock_basics::_normalize_ticker` + `upsert_one` 이중 안전망)
- `name` / `excg_dvsn_cd` / `nxt_tradable` (bool) / `krx_halted` (bool) / `admin_item` (bool)
- `raw` JSONB (CTPF1002R 응답 전수, 67 키 — 사이클 81 진단 영속: `bfdy_clpr` / `stck_prpr` / `acml_tr_pbmn` 등)
- `refreshed_at` TIMESTAMPTZ — 24h TTL `is_stale()` 기준 (KST aware 비교, 사이클 68 G-11)

**CRUD 함수 (현재 3종)**:
- `upsert_one(StockBasics)` — 정규화 + KST `refreshed_at` 자동 세팅
- `get(ticker) -> Optional[StockBasics]` — 단건 조회
- `is_stale(ticker, max_age_hours=24) -> bool` — 24h 초과 또는 미존재

**호출 사이트 8 모듈** (Bash grep 영속): `models/balance.py` / `api/condition.py` / `engine/scanner.py` / `engine/order_engine.py` / `engine/scheduler.py` / `engine/boot_manager.py` / `routes/balance.py`.

**누락 함수 (UI 구축용 신규 필요)**:
- `list_all(limit, offset)` — 페이징 list (현재 없음)
- `count_all()` / `count_fresh()` / `count_stale()` — 상태 통계
- `get_key_distribution()` — `raw.bfdy_clpr > 0` / `acml_tr_pbmn > 0` / `nxt_tradable=True` / `krx_halted=True` / `admin_item=True` 카운트
- `list_recent(limit=10)` — 최근 갱신 ticker top N

### 2-2. 변경기록 영역 후보 (Phase 1 진단)

현재 `stock_master` 변경 추적 영역:
- `updated_at` 영속 (단일 시점만, before/after 비교 불가)
- `system_logs` prefix 4종 영속 (`[stock_master_miss]` / `[stock_master_miss stale]` / `[stock_master_upsert]` 등 — 사이클 56-E `safe_write_log` 통합 영속). 사이클 72 hotfix 후 logger.info 직접 발화 → `_DbLogHandler` 위임 INSERT.
- **신규 테이블 부재** — before_raw / after_raw / change_type 영구 기록 영역 0건.

### 2-3. UI 메뉴 현황 (사이클 81 G-M5 영속)

`frontend/src/App.tsx::navItems` 6개 (사이클 81 햄버거 메뉴 답습):
1. 대시보드 (`/`)
2. 거래 내역 (`/history`)
3. 전략수정 AI자문 (`/recommendations`)
4. 조건검색 추적 (`/strategy-funnel`)
5. 로그 (`/logs`)
6. 설정 (`/settings`)

7번째 메뉴 추가 시 모바일 햄버거 메뉴 (Drawer) 영속 보장 의무 (사이클 81 M-1~M-8 회귀 가드 답습).

---

## 3. Phase 2 — 사용자 결정 의제

### Q1. 변경기록 저장 영역 (HIGH — 매매 안전성 영향 영역, domain-expert 자문 후보)

| 옵션 | 영속 정책 | 신규 테이블 | 운영 부담 | 가시화 |
|------|----------|------------|----------|--------|
| **A** | `stock_master.updated_at` + `system_logs` prefix 단독 | 0 | LOW (현행 영속) | 시점만 (before/after 불가) |
| **B** | 신규 `stock_master_history` 테이블 (change_type/before_raw/after_raw JSONB) | 1 | MEDIUM (INSERT 1건/upsert, INSERT volume = 사이클 83 시정 후 150+ ticker × 24h ~= 일 150건) | 영구 영속 + diff 비교 |
| **C** | `system_logs` prefix `[stock_master_update]` 확장 + JSONB diff 인라인 | 0 | LOW (단일 INSERT, 사이클 72 dedupe 흡수 가능) | 영속 2일 (INFO retention) — diff 비교 가능하나 단기 |

**team-leader 권고**: **옵션 B (영구 영속) 채택** — 사이클 82 진단 영속 (silent 30일+) 패턴 차단 의무. 운영 부담 일 150건 = `trade_history` 일 ~50건 + `system_logs` 일 ~3000건 대비 미미. Supabase 무료 tier 500MB 영향 0.1% 미만.

**domain-expert 자문 영역 (선택)**:
- raw JSONB 67 키 full diff vs 핵심 키 (`bfdy_clpr` / `acml_tr_pbmn` / `nxt_tradable` / `krx_halted` / `admin_item`) only diff 비교
- change_type ENUM (`INSERT` / `UPDATE_PRICE` / `UPDATE_NXT_TRADABLE` / `UPDATE_HALTED` / `UPDATE_OTHER`)
- retention (영구 vs 90일 vs 365일)

### Q2. UI 메뉴 위치 (frontend-dev 인계)

| 옵션 | 위치 | 햄버거 메뉴 변화 | 진입 동선 |
|------|------|----------------|----------|
| **A** | 신규 7번째 메뉴 `종목마스터` | 6 → 7개 (모바일 햄버거 압축 확인 의무) | 1-click |
| **B** | 기존 `조건검색 추적` sub 페이지 (`/strategy-funnel/stock-master`) | 6개 유지 | 2-click (탭 추가) |
| **C** | 기존 `설정` sub (`/settings#stock-master`) | 6개 유지 | 2-click (스크롤) |

**team-leader 권고**: **옵션 A (7번째 메뉴)** — 운영 진단 빈도 높음 (사이클 81~83 chain 영속 빈도). 사이클 81 햄버거 메뉴 패턴 답습 안정성 입증.

### Q3. UI 화면 구성 (frontend-dev 인계)

**4 영역 구성** (사이클 41 StrategyFunnel + 사이클 21 KisAccountPoolCard 답습):

1. **상태 영역** (`stock-master-stats-card`):
   - 적재 count (전체 / fresh 24h 내 / stale 24h 초과)
   - 키 분포: `bfdy_clpr > 0` / `acml_tr_pbmn > 0` / `nxt_tradable=True` / `krx_halted=True` / `admin_item=True` 카운트 + 비율 (사이클 82 진단 답습 의무)
   - 최근 갱신 ticker top 10 (timestamp KST + ticker + name)
   - 운영 측정 (사이클 83 효과): `[scan_pool_eager_refresh]` daily_summary (사이클 83 신규 emit 가정)

2. **변경기록 영역** (`stock-master-history-card`):
   - ticker 검색 (`stock-master-history-search-input`) + 시간순 변경 이력 (timestamp + change_type + before_raw / after_raw diff)
   - 페이징 (1-base, size 50)

3. **ticker detail 영역** (`stock-master-detail-{ticker}`):
   - ticker 클릭 시 raw JSONB 67 키 전수 표시 + `bfdy_clpr` / `acml_tr_pbmn` highlight
   - KST timestamp + `nxt_tradable` 배지 + `krx_halted` 배지 + `admin_item` 배지

4. **list 영역** (`stock-master-list-grid`):
   - 페이징 그리드 (1-base, size 100, 사이클 ScanMonitor 답습)
   - 컬럼: ticker / name / `bfdy_clpr` / `nxt_tradable` 배지 / `refreshed_at` (KST) / stale 배지 / detail 링크

### Q4. 백엔드 API 라우트 (backend-dev 인계)

5 신규 라우트 (`src/routes/stock_master.py` 신규 파일):

- `GET /api/stock-master/stats` — Q3 영역 1 (상태 통계 + 키 분포 + top 10)
- `GET /api/stock-master/list?limit=100&offset=0` — Q3 영역 4 (페이징 list + total count)
- `GET /api/stock-master/{ticker}` — Q3 영역 3 (raw 전수 + 배지)
- `GET /api/stock-master/{ticker}/history?limit=50&offset=0` — Q3 영역 2 (Q1 결정 영역, 옵션 B 채택 시 `stock_master_history` 테이블 쿼리)
- `GET /api/stock-master/scan-pool/summary` — Q3 영역 1 운영 측정 (사이클 83 eager refresh trigger 빈도)

**응답 래퍼 의무**: `ApiResponse<T>` (`models/response.py`).

**Q4 사이드: stock_master.py 신규 헬퍼 함수 4종** (Phase 1 누락 분석 영속):
- `list_all(limit, offset, fresh_only=False) -> tuple[list[StockBasics], int]`
- `get_stats() -> dict` (count_all / count_fresh / count_stale / key_distribution / top_10_recent)
- `list_history(ticker, limit, offset) -> tuple[list[dict], int]` (Q1 옵션 B 채택 시)
- `count_eager_refresh_today() -> int` (Q3 영역 1, 사이클 83 신규 emit 의존)

### Q5. 검증 의무 (tester 인계)

1. **백엔드 라우트 정합성**:
   - `ApiResponse<T>` 래퍼 (사이클 64/65 답습 — `data.data` 프론트 추출 정합)
   - 페이징 응답 `total` / `total_pages` 필수 (frontend/CLAUDE.md "백엔드 연동" 영속)
2. **프론트 useQuery + retry:1**:
   - 사이클 65 H1 + 사이클 75 G-AST5 답습 — `useQuery({ retry: 1, ... })` 명시 의무
   - AST 영구 가드 `_ast_useQuery_retry_required.test.ts` 영역 확장 (`StockMaster.tsx` 추가)
3. **e2e api-mocks 등록 의무**:
   - 사이클 75 G-AST5 답습 — `e2e/fixtures/api-mocks.ts` 5 endpoint 신규 라우트 + LIFO 정합 (사이클 80 hotfix #3 영속)
   - `_ast_api_mocks_coverage.test.ts` 영역 확장 (`REQUIRED_STOCK_MASTER_ENDPOINTS` 5종)
4. **모바일 햄버거 메뉴 7번째 메뉴 영속**:
   - 사이클 81 G-M5 답습 — `MobileMenuLabel` 7개 매핑 + `M-1~M-8` 회귀 가드 갱신
5. **변경기록 영역 영구 가드** (Q1 옵션 B 채택 시):
   - `stock_master_history` migration 032 (신규) + `(ticker, changed_at)` 인덱스
   - upsert_one trigger 함수 — INSERT/UPDATE 자동 history INSERT (사이클 83 effect 영속 측정 가능)

---

## 4. 사이클 분할 권고

### 옵션 1 (권장): 3 단계 분할 (사이클 84/85/86)

**사이클 84 (백엔드 단독)**:
- `src/db/stock_master.py` 신규 헬퍼 4종
- `src/routes/stock_master.py` 신규 5 라우트
- `migration 032` (Q1 옵션 B 채택 시 `stock_master_history` + trigger)
- 단위 + 통합 테스트 + ApiResponse 가드
- 매매 hot path 영향 0 (READ-ONLY 라우트 + history INSERT trigger 비동기)

**사이클 85 (프론트 단독)**:
- `frontend/src/pages/StockMaster.tsx` 신규 (4 영역)
- `frontend/src/api/stock-master.ts` + `frontend/src/types/stock-master.ts` 신규
- `App.tsx` navItems 7번째 메뉴 추가 + `MobileMenuLabel` 매핑 갱신
- vitest 회귀 + AST 영구 가드 (G-RT4 retry:1 영역 확장 + G-AST6 api-mocks 영역 확장)
- e2e api-mocks 5 endpoint 신규 + LIFO 정합

**사이클 86 (통합 검증)**:
- tester E2E (Playwright settings.spec.ts 답습 패턴)
- 모바일 햄버거 메뉴 7번째 메뉴 verify (M-1~M-8 갱신)
- 운영 측정 영역 실증 (사이클 83 effect 14 → 150+ 측정 PASS 의무)
- 회귀 0 + flakiness 0 + 매매 안전성 verify

### 옵션 2 (사이클 65 통합 패턴): 단일 사이클 84

- 백 + 프 + 검증 통합 (사이클 64/65 패턴)
- 변경 영역 광범위 → 회귀 위험 MEDIUM (사이클 81 영역 분리 권고 답습 안 함)

**team-leader 권고**: **옵션 1 채택** — 사이클 81 영역 분리 패턴 답습 + Q1 결정 (옵션 B) 채택 시 migration + trigger 영역 = 백엔드 단독 사이클 안정성 우선. 사이클 85 프론트 단독 = 사이클 75 패턴 답습 안정성 입증.

---

## 5. 사용자 결정 요청 (단일 응답으로 회수)

다음 5개 의제에 대해 사용자 결정 회수 후 사이클 84 명세 발주:

- **Q1**: 변경기록 저장 영역 (A/B/C) — team-leader 권고 **B** (영구 영속)
- **Q2**: UI 메뉴 위치 (A/B/C) — team-leader 권고 **A** (7번째 메뉴)
- **Q3**: 4 영역 구성 — team-leader 권고 **전수 채택** (수정 의제 있으면 명시)
- **Q4**: 5 라우트 + 4 헬퍼 — team-leader 권고 **전수 채택**
- **Q5**: 검증 의무 5종 — team-leader 권고 **전수 채택** + Q1 옵션 B 채택 시 migration 032 + trigger 동행

**사이클 분할**: 옵션 1 (3 단계) vs 옵션 2 (단일) — team-leader 권고 **옵션 1**

---

## 6. 주의사항 (사이클 84~86 진행 시 영속)

- **매매 안전성 무영향 보장**: 신규 라우트 = READ-ONLY (`GET` 5종 only). UPDATE/DELETE 라우트 절대 추가 금지 — stock_master 는 KIS CTPF1002R 정본 캐시 (운영자 수동 수정 → 사이클 81 silent 결함 재발 위험)
- **CLAUDE.md "절대 깨지 말 것" 8 영역 영속**: 본 신규 UI 영역 = 진단 가시화 전용, hot path (체결통보 / uvicorn 단일 워커 / 주문번호 매핑 / `_reset_daily_state` / NXT 좀비 차단 / WebSocket 4중 안전망 / KIS 거부 + KST / 사이클 38 명문화) 모두 무관
- **사이클 68 KST 일관성 영속**: 신규 라우트 응답 timestamp 모두 `+09:00` ISO (사이클 68 G-10b AST 가드 영역 확장)
- **사이클 72 dedupe 영속**: `[stock_master_*]` prefix 신규 emit 시 `_DbLogHandler` 위임 단일 INSERT 패턴 영속 (사이클 72 G-6 AST 가드 회피)
- **사이클 81 햄버거 메뉴 영속**: 7번째 메뉴 추가 시 모바일 viewport (375px) 침범 0 (사이클 81 G-M1~M8 회귀 가드 갱신)
- **운영 효과 측정 의무 (사이클 86 verify)**: 사이클 83 시정 효과 = stock_master count 14 → 150+ + `bfdy_clpr > 0` 비율 14% → 95%+ + `[price_filter_scanner_skip]` 정상 발화 (영업일 ~10~50건/일) 측정 PASS 의무

---

## 7. 후속 카드 인계 (사이클 87+)

- (LOW) `stock_master_history` retention 정책 (영구 vs 90일 vs 365일) — Q1 옵션 B 채택 시 운영 부담 monitoring 후 결정
- (LOW) stock_master `raw` JSONB 67 키 schema 정합성 가드 — CTPF1002R 응답 키 변경 영구 차단 (사이클 81 silent 결함 재발 영구 차단 패턴)
- (LOW) 운영자 수동 invalidate 라우트 (`POST /api/stock-master/{ticker}/invalidate`) — 사용자 강력 요청 시 검토, 기본 비추 (silent 결함 재발 위험)
