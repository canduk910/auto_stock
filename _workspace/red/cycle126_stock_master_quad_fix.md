# 사이클 126 Red 명세 — 종목마스터 UI/데이터 결함 4건 통합 시정

## 진단 (Phase 1)

| 결함 | 위치 | 근본 원인 | 사용자 결정 |
|------|------|-----------|------------|
| 1. UI 1000 cap | `src/db/stock_master.py::get_stats()` L113~L185 | `.execute()` 시 `.limit()` 미명시 → PostgREST 디폴트 1000행 한도 | count="exact" 별도 쿼리 + .range(0,9999) raw 집계 |
| 2. 목록 데이터 부족 | `frontend/src/pages/StockMaster.tsx:776~787` | 리스트 8 컬럼, 모달의 핵심 키 미노출 | 현재가/전일대비/시가총액/거래대금 4 컬럼 추가 |
| 3. NXT/정지/관리 미입수 | `src/engine/scanner.py:1831~1833` | KRX 1차 폴백 하드코딩 False, KIS lazy 보강 미발화 | KIS CTPF1002R 매스 보강 자동 task + 수동 trigger |
| 4. 일봉 미적재 | `src/engine/scanner.py::_stock_master_daily_load_once` | 코드 완벽, EC2 미재기동 or silent 실패 | 진단 로그 강화 + 수동 trigger |

## 회귀 가드 (영역별)

### 영역 1 — get_stats() count 분리
- G-COUNT1: count="exact" 쿼리 결과 mock 2697 정확 반환 (count_all == 2697)
- G-COUNT2: raw 분석 쿼리 .range(0, 9999) 사용 검증
- G-COUNT3: count 쿼리 실패 시 raw len(rows) fallback graceful

### 영역 2 — 리스트 4 컬럼
- G-LIST-COL: stck_prpr / prdy_vrss / hts_avls / acml_tr_pbmn 4 컬럼 렌더
- G-LIST-FORMAT: formatMarketCap (백만원→억원) + formatTradeAmount (원→억원)
- G-LIST-GRACEFUL: 값 없음 → "—" 표시

### 영역 3 — basics refresh 자동 task + POST
- G-BASICS1: _stock_master_basics_refresh_once 호출 시 inquire_stock_basics + upsert_one 호출
- G-BASICS2: Rate Limit 50ms sleep
- G-BASICS3: KIS 거부 시 graceful + failed 카운터 증가
- G-BASICS4: [stock_master_basics_refresh_summary] emit
- G-TASK1: scheduler._stock_master_basics_refresh_task_loop start() 즉시 1회 + 16:10 정기
- G-TASK2: task_attrs 3곳 (line 762/884/913)에 _stock_master_basics_refresh_task 포함
- G-ROUTE1: POST /basics/refresh 200 + asyncio.Lock 409 Conflict
- G-AST1: task_attrs 3곳 모두 _stock_master_basics_refresh_task 포함 (AST 정적)
- G-AST2: _ALLOWED_POST_ROUTES 화이트리스트에 /basics/refresh + /daily/refresh

### 영역 4 — 일봉 진단 강화 + POST
- G-DIAG1: _stock_master_daily_load_once 함수 진입 시 [stock_master_daily_load_begin] emit
- G-DIAG2: db_write_failures 카운터 summary 포함
- G-ROUTE2: POST /daily/refresh 200 + asyncio.Lock 409 Conflict
- G-AST3: Playwright LIFO 정합 (api-mocks.ts wildcard 전, 2 구체 후)

## 매매 안전성 무영향 확정
- scanner 단계 매수 진입 전 영역만 변경
- risk.on_tick / order_engine / realtime/ / auth/ 변경 0
- 매도/익일청산/15:20 강제청산 hot path 무관
- 사이클 38 명문화 영속 + 사이클 88 G-REJECT graceful 단위 영속

## 답습 매트릭스
- 사이클 17 KIS LMS chain (50ms sleep)
- 사이클 79 G-AST2 task_attrs 3곳
- 사이클 84 L-2 POST 화이트리스트
- 사이클 88 G-REJECT graceful
- 사이클 90 _refresh_universe_lock 패턴 (asyncio.Lock + 409)
- 사이클 122 일봉 task 100% 답습
- 사이클 124 UI 동기화 의무 8단계 절차
