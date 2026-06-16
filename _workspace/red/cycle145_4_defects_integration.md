# 사이클 145 — 4건 통합 시정 (사용자 결정 Q1=C UPSERT + Q2=A 통합)

- **결함 1**: migration 034 운영 DB 미적용 silent (메인 세션 hotfix 완료, 사이클 145 = EC2 자동 적용 워크플로우 추가)
- **결함 2**: 6/16 거래대금 0건 silent (raw.acml_tr_pbmn=0 덮어쓰기 결함 추정)
- **결함 3**: strategy_funnel_snapshots 중복 row (migration 035 운영 DB 적용 완료, 코드 UPSERT 전환)
- **결함 4**: UI "신고가 후보 58" 운영자 오인 (사이클 21 swing 후보, 정상 영역 — UI 라벨 명확화)

## Phase 1 진단 결정적 발견

### 결함 2
- 운영 DB stock_master 2,697 ticker 중 acml_tr_pbmn > 0 = **3 종목만**
- 6/15 22:54~22:59 UTC = 6/16 07:54~07:59 KST = boot force=True 시점
- 장 시작 *전* → KIS FHKST01010100 acml_tr_pbmn=0 정상 응답 → upsert 시 raw 영역 덮어쓰기
- 시정: `inquire_stock_basics` merge 영역에서 `acml_tr_pbmn=0`이면 기존 raw 키 영역 영구 영속 *보존* (덮어쓰기 금지 graceful)

### 결함 3 — Supabase MCP 적용 완료
- migration 035 운영 DB 적용 완료 (중복 row DELETE + UNIQUE 변경)
- 코드 영역 시정 필요: `insert_snapshot()` UPSERT 전환

### 결함 4 — 운영 정합 (운영자 오인)
- `ScanMonitor.tsx` `summaryLabel = '신고가 후보'` 영역 영구 영속이 `isSwing` (donchian) 탭 전용
- `swingCount` = donchian 후보 카운트 (사이클 21 영역 영구 영속)
- 결함 아님. UI 라벨 명확화로 충분

## 시정 영역

### 1. migration 035 + Supabase MCP 적용 ✓
- `supabase/migrations/035_strategy_funnel_snapshots_upsert.sql` 작성 + 운영 DB 적용 완료

### 2. `src/db/strategy_funnel.py::insert_snapshot()` UPSERT 전환
- `.insert(row)` → `.upsert(row, on_conflict="target_date,strategy_id,step_no")` 영역
- snapshot_at = 매번 갱신 (PostgreSQL DEFAULT now() 자동)
- survived_count / excluded_count / survived_tickers / excluded_sample / step_name 영역 영구 영속 EXCLUDED 갱신

### 3. `src/api/condition.py::inquire_stock_basics` raw 보존 시정
- FHKST01010100 응답 acml_tr_pbmn=0 시 기존 raw 키 영역 영구 영속 *보존*
- merge 영역에서 0 값 덮어쓰기 금지 graceful (사이클 81 G-AST1 영속)

### 4. `.github/workflows/deploy.yml` migration 자동 적용
- Supabase CLI (`npx supabase db push`) 통합
- 매 push 후 자동 migration apply (silent 결함 영구 차단)

## Red 회귀 가드 (G-145 시리즈)

### G-145-FUNNEL — strategy_funnel insert_snapshot UPSERT (4 케이스)
- G-145-FUNNEL-1: AST `.upsert(` 호출 영속
- G-145-FUNNEL-2: AST `on_conflict="target_date,strategy_id,step_no"` 영역
- G-145-FUNNEL-3: 동일 (target_date, strategy_id, step_no) 2회 insert → 1 row 영구 영속 (mock)
- G-145-FUNNEL-4: docstring 사이클 145 영역 영속

### G-145-RAW — inquire_stock_basics raw 보존 (4 케이스)
- G-145-RAW-1: acml_tr_pbmn=0 응답 시 기존 raw 키 보존 (merge 영역 0 덮어쓰기 금지)
- G-145-RAW-2: acml_tr_pbmn>0 응답 시 정상 덮어쓰기
- G-145-RAW-3: lstn_stcn / acml_vol / prdy_vrss / hts_avls 영역 영속 동일 영역
- G-145-RAW-4: AST 가드 — merge 영역 영구 영속 0 가드 영속

### G-145-MIGRATION — deploy.yml 자동 migration (2 케이스)
- G-145-MIGRATION-1: deploy.yml 영역에 `supabase db push` 또는 동등 영역 영구 영속
- G-145-MIGRATION-2: SUPABASE_DB_URL secret 영역 영구 영속 (workflow 영역 환경 변수)

## 영속 의무 매트릭스

- 사이클 17 KIS LMS chain (변경 0)
- 사이클 38 명문화 (logging + 진단 영역 한정)
- 사이클 79 G-AST2 / 81 G-AST1 (영향 0, 영역 강화)
- 사이클 88 G-REJECT graceful 영속 (영역 강화 = silent → 가시화)
- 사이클 107 inquire_stock_basics CTPF1002R + FHKST01010100 merge 패턴 영속 (시정 영역)
- 사이클 122/126/127/128/129/131/132/133/134/135/136/137/138/139/140/142/143/144 영속 (영향 0)
- 사이클 81 G-AST1 영속 영구 강화 (raw 0 덮어쓰기 금지 영구 영속)
