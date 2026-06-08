# 사이클 84 Phase 1 진단 — stock_master UI 백엔드 단독 단계

작성일: 2026-06-09
작성자: team-leader (트레이더 관점)
배경: 사이클 84 발주 = 구축 계획서 `_workspace/stock_master_ui_plan.md` 의 백엔드 단독 단계 (3 단계 분할 옵션 1, 사용자 결정 채택).
선결정 영속: **Q1=B (신규 `stock_master_history` 테이블) / Q2=A (7번째 메뉴) / Q3 = 3 단계 분할 / Q4=B (사이클 83 push 우선 후 발주, push 완료 = commit `6dfe070`)**.
코드 변경: **0** (READ-ONLY 진단 단독, Supabase MCP 1회 사용).

---

## 1. Phase 1 진단 — 결함/구조 식별 (완료)

### 1-1. `src/db/stock_master.py` 현황 (126L)

**컬럼 8종** (Supabase `information_schema.columns` 실측 영속):
- `ticker` (text, NOT NULL, PK) — KRX 6자리 (`upsert_one` 정규화 이중 안전망 영속)
- `name` (text, NOT NULL)
- `excg_dvsn_cd` (text, NOT NULL)
- `nxt_tradable` (boolean, NOT NULL)
- `krx_halted` (boolean, NOT NULL)
- `admin_item` (boolean, NOT NULL)
- `raw` (jsonb, NOT NULL) — CTPF1002R 응답 67 키
- `refreshed_at` (timestamptz, NOT NULL) — 24h TTL 기준 (사이클 68 KST aware 영속)

**기존 함수 3종**:
- `upsert_one(StockBasics)` (L53~82) — 정규화 + KST `refreshed_at` 자동 세팅
- `get(ticker) -> Optional[StockBasics]` (L85~93) — 단건 조회
- `is_stale(ticker, max_age_hours=24) -> bool` (L96~126) — 24h 초과 또는 미존재 (사이클 68 G-11 KST aware)

**호출 사이트 8 모듈** (Bash grep 영속):
`src/models/balance.py` / `src/api/condition.py` / `src/engine/scanner.py` / `src/engine/order_engine.py` / `src/engine/scheduler.py` / `src/engine/boot_manager.py` / `src/routes/balance.py` / `src/db/stock_master.py` 자기 참조.

### 1-2. Supabase 실측 (2026-06-09, READ-ONLY)

`stock_master` 적재 현황:
- **total = 14건** (사이클 83 push 직후 영역, eager refresh 효과 측정은 다음 영업일 09:30 이후)
- **fresh_24h = 1건** (단일 종목만 24h 내 갱신)
- **bfdy_clpr > 0 = 13건** (사이클 81 시정 효과 영속 — 93%)
- **nxt_tradable=true = 9건** / **krx_halted = 0** / **admin_item = 0**

운영 가시화 의무 = 사이클 81~83 chain 영속 silent 결함 차단 패턴 신규 영역.

### 1-3. 기존 라우트 17 파일 (`src/routes/` 분석)

기존 라우트 패턴 (사이클 65/75 답습 영속):
- `ApiResponse<T>` 래퍼 의무 (`models/response.py`)
- 페이징 응답 `total` / `total_pages` 의무 (사이클 6 `get_logs` 답습)
- 신규 `src/routes/stock_master.py` 생성 영역 = 충돌 없음 (기존 파일 0건)

### 1-4. 신규 헬퍼 4종 + 라우트 5종 명세 (계획서 영속)

**헬퍼 4종 (`src/db/stock_master.py` 추가)**:
- `list_all(limit=100, offset=0, fresh_only=False) -> tuple[list[StockBasics], int]`
- `get_stats() -> dict` (count_all / count_fresh / count_stale / key_distribution / top_10_recent)
- `list_history(ticker, limit=50, offset=0) -> tuple[list[dict], int]` (Q1=B 영역)
- `count_eager_refresh_today() -> int` (사이클 83 emit 의존)

**라우트 5종 (`src/routes/stock_master.py` 신규)**:
- `GET /api/stock-master/stats`
- `GET /api/stock-master/list?limit=100&offset=0`
- `GET /api/stock-master/{ticker}`
- `GET /api/stock-master/{ticker}/history?limit=50&offset=0`
- `GET /api/stock-master/scan-pool/summary`

### 1-5. migration 032 명세 (신규)

신규 테이블 `stock_master_history`:
- `id` UUID PK
- `ticker` TEXT NOT NULL (FK 가능, Q8 결정 영역)
- `change_type` ENUM (Q5 결정 영역)
- `before_raw` JSONB NULL (INSERT 시 NULL)
- `after_raw` JSONB NOT NULL
- `changed_at` TIMESTAMPTZ NOT NULL (KST `+09:00` 명시, 사이클 68 G-10b 영속)

인덱스 2종: `(ticker, changed_at DESC)` (history 조회용) + `(changed_at DESC)` (운영 측정용).

---

## 2. Phase 2 — 사용자 결정 의제 Q5~Q9

### Q5 (HIGH) `change_type` ENUM 정의

| 옵션 | 타입 | 운영 가시화 | trigger 복잡도 |
|------|------|------------|--------------|
| **A** | INSERT / UPDATE (2 타입) | LOW (basic) | LOW (간단) |
| **B** | INSERT / UPDATE / DELETE / TTL_REFRESH (4 타입) | MEDIUM (TTL 추적) | MEDIUM |
| **C** | INSERT / UPDATE / DELETE / TTL_REFRESH / NXT_TRADABLE_FLIP (5 타입) | HIGH (NXT 거부 사후 보강 가시화) | HIGH |

**team-leader 권고**: **옵션 B** — 사이클 83 24h TTL refresh 빈도 측정 의무 + DELETE 영역 (현재 stock_master DELETE 호출 0건 = 향후 silent 결함 대비 영역). 옵션 C `NXT_TRADABLE_FLIP` 은 옵션 B `UPDATE` 의 `before_raw.nxt_tradable != after_raw.nxt_tradable` 비교로 사후 추출 가능 = 별도 ENUM 불필요. trigger 복잡도 MEDIUM 적정.

### Q6 (HIGH) raw diff 영역

| 옵션 | 영역 | 저장 부담 | 진단 정밀도 |
|------|------|----------|----------|
| **A** | 전체 JSONB before/after (67 키 전수) | HIGH (1건당 ~5KB × 일 150건 = 750KB/일 = 270MB/년) | HIGH (완전 진단) |
| **B** | 핵심 5 키 only (bfdy_clpr / acml_vol / nxt_tradable / krx_halted / admin_item) | LOW (1건당 ~200B × 일 150건 = 30KB/일 = 11MB/년) | MEDIUM (핵심 추적) |
| **C** | 변경된 키만 (delta diff, jsonb minus) | MEDIUM (1건당 ~500B 평균 = 27MB/년) | HIGH (변경 영역만 정밀) |

**team-leader 권고**: **옵션 A** — Supabase 무료 tier 500MB 한도 대비 270MB/년 = 54% (Q7 retention 적용 시 90일 = 14% / 365일 = 54%). 사이클 81 silent 결함 진단 의무 = 67 키 전수 보존 가치 우선. 옵션 C delta jsonb minus 는 PG 표준 함수 부재 (`-` 연산자는 키 제거용, diff 용도 별도 함수 정의 필요 = trigger 복잡도 상승). 옵션 B 는 사이클 81 silent 결함 (`prdy_clpr` vs `bfdy_clpr` 키 명명 오류) 영역 추적 불가 위험 (`bfdy_clpr` 만 추적 시 다른 키 변경 silent).

### Q7 (MEDIUM) retention 정책

| 옵션 | 기간 | 저장 부담 (옵션 A 기준) | 운영 측정 영역 |
|------|------|---------------------|--------------|
| **A** | 영구 영속 | HIGH (270MB/년 무한 증가) | 영구 진단 |
| **B** | 90일 | LOW (67MB) | 단기 진단 + 분기 회고 |
| **C** | 365일 | MEDIUM (270MB) | 연간 회고 |

**team-leader 권고**: **옵션 C (365일)** — `system_logs` 패턴 (INFO 2일 / HIGH 30일, 사이클 6 영속) 와 차별화. stock_master = KIS 정본 캐시 = 연간 트렌드 (액면분할 / 종목 신규 상장 / 폐지) 영역 = 365일 적정. cron job 별도 사이클 87+ 인계 (사이클 6 `purge_old_logs` 답습).

### Q8 (MEDIUM) trigger vs Python upsert 전수 직접 INSERT

| 옵션 | 구현 영역 | 회귀 위험 | 코드 변경 |
|------|----------|----------|---------|
| **A** | PostgreSQL trigger (자동) | LOW (DB 레벨) | 0 (application 무영향) |
| **B** | Python `upsert_one` 직접 INSERT (명시적) | MEDIUM (호출 누락 risk) | MEDIUM (`upsert_one` +20L) |
| **C** | 둘 다 (trigger + Python 명시적 로그) | HIGH (이중 INSERT 영역, 사이클 72 dedupe 결함 답습 위험) | HIGH |

**team-leader 권고**: **옵션 A (PostgreSQL trigger)** — 사이클 72 dedupe 결함 (`_DbLogHandler` + `await write_log` 양쪽 호출 silent 이중 INSERT, 9 회 누적) 패턴 영구 차단. trigger 단일 진입점 = 향후 신규 stock_master upsert 사이트 추가 시 자동 history INSERT 보장. migration 032 trigger 함수 `_audit_stock_master_changes()` + `BEFORE INSERT OR UPDATE OR DELETE` trigger 1건. application code 변경 0 = 회귀 위험 LOW.

### Q9 (HIGH) domain-expert 자문 의무 여부

| 옵션 | 자문 영역 | 사이클 진행 속도 |
|------|---------|--------------|
| **A** | 의무 (변경기록 영속 정책 = 매매 안전성 영역 영향 평가) | 1~2 사이클 지연 |
| **B** | 생략 (READ-ONLY GET only, 매매 hot path 무영향 = 위급도 LOW) | 즉시 진행 |

**team-leader 권고**: **옵션 B (생략)** — 본 영역 = READ-ONLY GET 5종 + history trigger INSERT 만 (매매 hot path 무관). domain-expert 자문 영역 = 매수/매도 결정 / 파라미터 / 시장 행태 / KIS 거부 해석 (사이클 64/65/66/67/72/73/74 답습). 본 영역 = UI 진단 가시화 + DB schema 영역 = backend-dev 직답 가능. 사이클 진행 속도 우선 (사이클 81~83 chain 영역 push 완료 = 운영 효과 측정 다음 영업일 09:30 영역).

---

## 3. 회귀 가드 매트릭스 추정

**HIGH 5 케이스** (35% = 14/40):
- G-1: migration 032 적용 검증 (테이블/인덱스/trigger 존재 + ENUM CHECK)
- G-2: trigger 동작 freezegun (INSERT → history 1건 + UPDATE → history 1건 + DELETE → history 1건)
- G-3: `change_type` ENUM 4 타입 정확성 (INSERT/UPDATE/DELETE/TTL_REFRESH, Q5=B 채택 시)
- G-4: raw diff 정확성 (before_raw NULL vs after_raw 전수 영속, Q6=A 채택 시)
- G-5: API 라우트 5종 `ApiResponse<T>` 래퍼 정합 (사이클 65 답습)

**MEDIUM 7 케이스** (25%):
- M-1: `list_all` 페이징 limit/offset (total count 정합)
- M-2: `get_stats` 집계 정확성 (count_all + key_distribution + top_10_recent)
- M-3: `list_history` ticker filter + 페이징
- M-4: `count_eager_refresh_today` 사이클 83 emit 의존성 (mock)
- M-5: 5 라우트 응답 schema 정합 (`bfdy_clpr` / `nxt_tradable` / `refreshed_at` KST)
- M-6: 라우트 404 처리 (`GET /api/stock-master/{invalid_ticker}` → 404)
- M-7: 페이징 응답 `total_pages` 계산 정확성 (사이클 6 답습)

**LOW 5 케이스** (40%):
- L-1: history INSERT KST `+09:00` 명시 (사이클 68 G-10b 영역 확장)
- L-2: AST 영구 가드 `stock_master_history` payload KST 명시 0건 비위반
- L-3: 사이클 83 `[scan_pool_eager_refresh]` emit 카운트 정합
- L-4: trigger 함수 영역 한정 (다른 테이블 영향 0)
- L-5: 사이클 72 dedupe 영속 영향 0 (`_DbLogHandler` 무관)

총 **17 케이스 추정** (5 파일 신규 예상).

---

## 4. domain-expert 자문 의무 여부 권고

**team-leader 권고**: **생략 (Q9=B)** — 본 영역 = READ-ONLY GET + history trigger INSERT = 매매 hot path 무관. 자문 의무 영역 (매수/매도 / 파라미터 / 시장 행태 / KIS 거부) 모두 비해당. 사이클 진행 속도 우선.

---

## 5. 사용자 결정 회수 요청

다음 5개 의제 결정 후 사이클 84 명세 발주:

- **Q5**: change_type ENUM (A/B/C) — team-leader 권고 **B** (4 타입)
- **Q6**: raw diff 영역 (A/B/C) — team-leader 권고 **A** (전체 67 키)
- **Q7**: retention 정책 (A/B/C) — team-leader 권고 **C** (365일)
- **Q8**: trigger vs Python (A/B/C) — team-leader 권고 **A** (PG trigger 단일 진입점)
- **Q9**: domain-expert 자문 (A/B) — team-leader 권고 **B** (생략)

권고 채택 시 사이클 84 명세:
- migration 032: `stock_master_history` + 4 ENUM + 2 인덱스 + trigger 함수 `_audit_stock_master_changes()` + BEFORE INSERT/UPDATE/DELETE trigger
- `src/db/stock_master.py` 헬퍼 4종 추가
- `src/routes/stock_master.py` 신규 5 라우트 + ApiResponse 래퍼
- 회귀 가드 17 케이스 (HIGH 5 / MEDIUM 7 / LOW 5)
- 매매 안전성 무영향 (READ-ONLY GET + trigger INSERT 단일 영역)
- 사이클 85 (프론트) + 사이클 86 (통합 검증) 후속 인계

---

## 6. 주의사항 영속

- **CLAUDE.md "절대 깨지 말 것" 8 영역 무영향** — UI 진단 영역 한정
- **사이클 68 KST 일관성 영속** — `stock_master_history.changed_at` KST `+09:00` 명시
- **사이클 72 dedupe 영속** — trigger 단일 진입점 = `_DbLogHandler` 무관
- **사이클 81 silent 결함 패턴 차단** — 변경기록 영속 = 미래 silent 결함 진단 가시화
- **Q7 retention cron job** 사이클 87+ 인계 (사이클 6 `purge_old_logs` 답습)

---

## 7. 산출물 파일 경로

- `/Users/koscom/Projects/auto_stock/_workspace/cycle84_phase1_diagnosis.md` (본 문서)
- `/Users/koscom/Projects/auto_stock/_workspace/stock_master_ui_plan.md` (구축 계획서 영속)
