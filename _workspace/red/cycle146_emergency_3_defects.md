# 사이클 146 — 긴급 3건 통합 시정

## Phase 1 진단 영구 영속 (Supabase MCP READ-ONLY)

### 결함 #1 — 매매 프로세스 자동 정지
- 운영 로그: TR_ID = TTTC8434R (실전 잔고 조회 정상 TR_ID, 사용자 보고 TTTCNR은 오기)
- KIS 일시 5xx 6회 retry exhausted (09:01~09:07)
- 시정 = start() except 영역에서 KisApiError 5xx 영역 graceful

### 결함 #2 — nxt_tradable NOT NULL 위반
- 신규 ticker 1,564건+ (900xxx ETN / 950xxx 외국기업)
- 메인 세션 hotfix (DEFAULT FALSE) 완료
- 코드 영역 이중 안전망 = upsert_master_raw 영역 nxt_tradable 키 부재 (DB DEFAULT 위임)

### 결함 #3 — raw 영역 일부 회복
- pbmn_positive=1,132 / 200억+ = 29 (donchian 100+ 필요)
- 운영자 의무 = UI "기본정보 새로고침" trigger

## Phase 2 시정 영역

### 결함 #1 — start() graceful recovery
- KisApiError + status 5xx → 보수적 graceful (매매 보존)
- 기타 Exception → 기존 동작 보존

### 결함 #2 — upsert_master_raw 영역
- payload 영역 nxt_tradable 키 부재 (DB DEFAULT 위임)
- 기존 ticker 영역 nxt_tradable 보존

## Red 가드 (G-146)
- G-146-DEFECT1-1: KisApiError 5xx 시 매매 보존
- G-146-DEFECT1-2: 기타 Exception 보존
- G-146-DEFECT2-1: payload 영역 nxt_tradable 키 부재
- G-146-DEFECT2-2: 기존 ticker upsert 시 nxt_tradable 보존

## 영속 의무
- 사이클 17/38/79/81/88/107 영속
- CLAUDE.md "절대 깨지 말 것" 8 영역
