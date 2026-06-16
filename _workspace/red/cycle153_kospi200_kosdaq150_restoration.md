# 사이클 153 Red — KOSPI200/KOSDAQ150 영역 영구 영속 복원 + stock_master.raw 영역 is_kospi200/is_kosdaq150 키 신규

## 사용자 결정 영속
- Q1=A — KIS 공식 마스터 source (`kospi200_apnt_cls_code != ""` AND `ksq150_nmix_yn == "Y"`)
- Q2=A — `is_kospi200: bool | None = None` + `is_kosdaq150: bool | None = None` 인자 (사이클 108 nxt_tradable 답습)
- Q3=A — TDD 정공

## 사용자 보고 영속 + Phase 1 진단 결정적 사실

- 6/16 첨부 UI = donchian step_no=1 "코스피200+코스닥150 합집합" survived=5 (사용자 보고 시점) / Supabase MCP 09:35 영역 = survived=1
- 사용자 verbatim: "코스피200 코스닥150의 합집합이 5개라는게 말이 안되는 것 같아"
- 운영 DB 실측 (2026-06-16): KOSPI200 1796 종목 (master_raw `kospi200_apnt_cls_code != ""`) + KOSDAQ150 149 종목 (master_raw `ksq150_nmix_yn == "Y"`) = 합집합 ~1945 종목 가능
- 결론 = 사이클 121 (2026-06-12) Plan Phase B silent 결함 = donchian_swing.py::_scan_universe() 영역 KOSPI200/KOSDAQ150 필터 완전 누락

## Red 행위 분해 (검증 가능한 행위)

### 행위 1 — migration 037 영역 + 컬럼 디폴트
- DB 컬럼 `is_kospi200 BOOLEAN DEFAULT FALSE` + `is_kosdaq150 BOOLEAN DEFAULT FALSE`
- 인덱스 2 정합 (`idx_stock_master_is_kospi200 WHERE is_kospi200=TRUE` / `idx_stock_master_is_kosdaq150 WHERE is_kosdaq150=TRUE`)
- 기존 row 영역 디폴트 FALSE (사이클 146 nxt_tradable 답습)

### 행위 2 — `_stock_master_master_load_once()` KOSPI/KOSDAQ 분기
- KOSPI 분기: `record["kospi200_apnt_cls_code"].strip() != ""` → `is_kospi200=True`
- KOSDAQ 분기: `record["ksq150_nmix_yn"] == "Y"` → `is_kosdaq150=True`

### 행위 3 — `upsert_master_raw()` 2 컬럼 동시 upsert
- payload 영역에 `is_kospi200` / `is_kosdaq150` 명시 (사이클 146 nxt_tradable 답습)
- 기존 ticker = ON CONFLICT DO UPDATE SET 영역 = 신규 컬럼 영구 영속 갱신

### 행위 4 — `list_by_filter()` 시그너처 영역 확장
- 신규 인자 `is_kospi200: bool | None = None` + `is_kosdaq150: bool | None = None`
- 둘 다 True 시 OR 영역 (`is_kospi200=True OR is_kosdaq150=True` 합집합)
- 한쪽만 True 시 AND 영역 (`is_kospi200=True` 단독 또는 `is_kosdaq150=True` 단독)
- 둘 다 None 시 무필터 (회귀 보존, 사이클 108 답습)

### 행위 5 — donchian `_scan_universe()` 영역 시정
- `list_by_filter(..., is_kospi200=True, is_kosdaq150=True, ...)` 호출
- FUNNEL_STAGES[0] step_name = "코스피200+코스닥150 합집합" 변경 0 (사용자 결정 영역 D)

### 행위 6 — vcp_breakout 영향 0 영역
- `vcp_breakout.py:726, 732` hardcoded list 영역 변경 0 (사이클 153 범위 외)
- 사이클 154+ 영향 평가 인계

### 행위 7 — 매매 안전성 무영향
- risk.on_tick / order_engine / realtime / auth 변경 0
- 사이클 32 R4 보유 종목 절대 보호 영속

## 회귀 가드 ≥15 케이스 매트릭스

### G-153-MIGRATION (2 케이스, HIGH 1)

- **G-153-MIGRATION-1 (HIGH)**: migration 037 영역 `is_kospi200 BOOLEAN DEFAULT FALSE` + `is_kosdaq150 BOOLEAN DEFAULT FALSE` 컬럼 + 인덱스 2 정합
- **G-153-MIGRATION-2**: 기존 row 영역 디폴트 FALSE (DB DEFAULT 영역)

### G-153-MASTER (3 케이스, HIGH 2)

- **G-153-MASTER-1 (HIGH)**: `_stock_master_master_load_once()` 영역 KOSPI 분기 = `kospi200_apnt_cls_code.strip() != ""` → `is_kospi200=True`
- **G-153-MASTER-2 (HIGH)**: KOSDAQ 분기 = `ksq150_nmix_yn == "Y"` → `is_kosdaq150=True`
- **G-153-MASTER-3**: hardcoded list 영역 변경 0 (vcp_breakout 영역 영향 0)

### G-153-FILTER (5 케이스, HIGH 3)

- **G-153-FILTER-1 (HIGH)**: `list_by_filter(is_kospi200=True)` → 후보 ~200 종목 (KOSPI200 단독)
- **G-153-FILTER-2 (HIGH)**: `list_by_filter(is_kosdaq150=True)` → 후보 ~150 종목 (KOSDAQ150 단독)
- **G-153-FILTER-3 (HIGH)**: `list_by_filter(is_kospi200=True, is_kosdaq150=True)` → **OR 영역** ~350 종목 합집합 (donchian 의무)
- **G-153-FILTER-4**: `list_by_filter(is_kospi200=None, is_kosdaq150=None)` → 전체 (회귀 보존)
- **G-153-FILTER-5**: 시그너처 영역 = 사이클 108 nxt_tradable 패턴 답습 (cls Signature 정합 검증)

### G-153-DONCHIAN (3 케이스, HIGH 1)

- **G-153-DONCHIAN-1 (HIGH)**: `_scan_universe()` → `list_by_filter(is_kospi200=True, is_kosdaq150=True, ...)` 호출 정합
- **G-153-DONCHIAN-2**: FUNNEL_STAGES[0] step_name = "코스피200+코스닥150 합집합" 변경 0
- **G-153-DONCHIAN-3**: step_no=1 survived = list_by_filter 결과 정합 (시총/거래대금/KOSPI200/KOSDAQ150 통과)

### G-153-SAFETY (3 케이스, HIGH 1)

- **G-153-SAFETY-1 (HIGH)**: risk.on_tick / order_engine / realtime / auth import 0건 (AST 정적 가드)
- **G-153-SAFETY-2**: 사이클 32 R4 보유 종목 절대 보호 영속 (현재 코드 영역 변경 0 검증)
- **G-153-SAFETY-3**: vcp_breakout L726/L732 영역 영향 0 (hardcoded list 영역 변경 0)

## 합 16 케이스 (HIGH 8 = 50%)

## 영속 의무 매트릭스
- CLAUDE.md "절대 깨지 말 것" 8 영역
- 사이클 32 R4 보유/익일청산 절대 보호
- 사이클 38 명문화 (scanner 매수 진입 전 한정)
- 사이클 81 G-AST1 raw JSONB 보호 (신규 컬럼 = raw 영역 외부)
- 사이클 108 list_by_filter 패턴 답습 (nxt_tradable 영역 정합)
- 사이클 121 Q2=D 임계 완화 영속 (변경 0)
- 사이클 129 master_raw 영역 영속 (변경 0)
- 사이클 143 FUNNEL_STAGES 영속 (donchian step_name 영구 영속)
- 사이클 146 upsert_master_raw 영역 nxt_tradable 명시 영속 답습 (is_kospi200/is_kosdaq150 동행 명시)
