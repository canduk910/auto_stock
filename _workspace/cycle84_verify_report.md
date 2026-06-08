# 사이클 84 verify 보고서 (tester)

작성일: 2026-06-09
작성자: tester
대상: 사이클 84 = stock_master UI 메뉴 백엔드 단독 단계
범위: V-1 ~ V-9 검증 (production 변경 0)

## 1. V-1 백엔드 전체 회귀 0 (HIGH)

- **2151 passed + 2 xfailed + 2 skipped** (회귀 0 확정)
- Green 단계 보고 (2151) 와 정합
- 사이클 66 K-2 의미 전환 XFAIL + 사이클 81 폴백 폐기 XFAIL = 2 XFAIL 영속
- 2 skip 영속 (Playwright 환경 의존)

## 2. V-2 flakiness 3 회 반복 (HIGH)

| 회차 | PASS | XFAIL | skip | time |
|------|------|-------|------|------|
| 1    | 2151 | 2     | 2    | 49.27s |
| 2    | 2151 | 2     | 2    | 49.56s |
| 3    | 2151 | 2     | 2    | 49.66s |

- 변동폭 0.39s (±0.4%) / **flakiness 0 확정**
- Green 단계 보고 (49.35~49.71s) 범위 내 정합

## 3. V-3 신규 17 케이스 카테고리 분리 (HIGH)

`pytest tests/unit/{db,routes,ast,engine}/test_cycle84_*.py -v` 결과:

| 카테고리 | 케이스 수 | 결과 |
|---------|----------|------|
| HIGH M-1~M-5 (5) | 미그레이션 + trigger 3종 + API envelope | **5/5 PASS** |
| MEDIUM H-1~H-7 (7) | 페이징/집계/history/eager_refresh + 404/422×2 | **7/7 PASS** (parametrize 포함 11 sub-case) |
| LOW L-1~L-5 (5) | KST + AST READ-ONLY + scan_pool emit + dedupe 무영향 + R4 무영향 | **5/5 PASS** |
| **합계** | **17 (31 sub-case)** | **31 passed in 0.34s** |

## 4. V-4 Supabase MCP READ-ONLY 운영 검증 (HIGH)

| 항목 | SQL | 결과 |
|------|-----|------|
| 테이블 존재 | `information_schema.tables` | `stock_master_history` ✅ |
| 컬럼 6종 | `information_schema.columns` | id bigint NOT NULL / ticker text NOT NULL / change_type text NOT NULL / before_raw jsonb NULL / after_raw jsonb NULL / changed_at timestamptz NOT NULL ✅ |
| 인덱스 3종 | `pg_indexes` | pkey + idx_smh_ticker_changed_at (ticker, changed_at DESC) + idx_smh_changed_at (changed_at DESC) ✅ |
| trigger 활성 | `information_schema.triggers` | stock_master_history_track AFTER INSERT/UPDATE/DELETE → stock_master_history_trigger() ✅ |
| 초기 history 카운트 | `SELECT COUNT(*) FROM stock_master_history` | **0건** (예상 일치) |
| 운영 stock_master | `SELECT COUNT(*) FROM stock_master` | 29건 (다음 eager refresh 시 history INSERT 발화 예상) |

## 5. V-5 API 라우트 정합 (HIGH)

- 5 라우트 전수 `@router.get` 만 (put/post/delete/patch 0건)
- M-5 ApiResponse 래퍼 5/5 parametrize PASS
- 라우트 순서: `/stats` → `/list` → `/scan-pool/summary` → `/{ticker}/history` → `/{ticker}` (정적 → 동적 LIFO 정합)
- limit 422: 0, -1, 1001, 5000 모두 422 (H-6 4 sub-case PASS)
- offset 422: -1, -100 모두 422 (H-7 2 sub-case PASS)
- 404: 미존재 ticker → 404 (H-5 PASS)

## 6. V-6 영속 의무 매트릭스 (HIGH)

| 영역 | 영속 가드 | 결과 |
|------|----------|------|
| 사이클 31 R6 silent_skip | 매매 hot path 무관 | ✅ 무영향 |
| 사이클 32 R4 universe guard | L-5 AST 가드 (stock_master 모듈 0 참조) | ✅ PASS |
| 사이클 38 명문화 tradable_boards | 라우트 0 참조 | ✅ 무영향 |
| 사이클 64 Q1 옵션 D 3중 안전망 | scanner.py 변경 0 | ✅ 무영향 |
| 사이클 72 dedupe `_DbLogHandler` | L-4 AST 가드 (write_log 직접 호출 0건) | ✅ PASS |
| 사이클 78 flush / 79 G-AST1 / 83 emit | L-3 [scan_pool_eager_refresh] literal 영속 | ✅ PASS |

## 7. V-7 "절대 깨지 말 것" 8 영역 (MEDIUM)

체결통보 H0STCNI0/H0STCNI9 / uvicorn 단일 워커 / 주문번호 매핑 + race 가드 / `_reset_daily_state` / 익일 청산 30s 안정화 / NXT 거부 좀비 + SellRejectionTracker / WebSocket 4중 안전망 / KIS 거부 + KST + 사이클 38 명문화 — **8/8 무영향 확정**. 사이클 84 변경 영역 = READ-ONLY GET 5 라우트 + DB trigger 단일 진입점, 매매 hot path 0 교차.

## 8. V-8 AST 영구 가드 (MEDIUM)

- `src/routes/stock_master.py` `@router.` decorator 5건 (전수 `.get`)
- PUT/POST/DELETE/PATCH 0건 = READ-ONLY 영구 차단 확정
- L-2 AST 케이스 PASS — 미래 신규 라우트 추가 시에도 동일 가드 작동

## 9. V-9 사이클 85 (프론트) 인계 명세 (LOW)

| 항목 | 명세 |
|------|------|
| 신규 메뉴 | 7번째 "종목마스터" (헤더 nav + 모바일 햄버거 드로어 양쪽, 사이클 81 패턴 답습) |
| API 5종 | GET `/api/stock-master/{stats,list,scan-pool/summary,{ticker}/history,{ticker}}` |
| 응답 래퍼 | `ApiResponse<T>` → `data.data` 추출 (V12 정합 패턴) |
| 페이징 | limit/offset (limit ∈ [1,1000], offset ≥ 0, 422 핸들링) |
| 404 처리 | 미존재 ticker → `axios.isAxiosError` + status 404 분기 |
| timestamp | `refreshed_at` / `changed_at` 모두 KST `+09:00` (`Intl.DateTimeFormat(timeZone='Asia/Seoul')` 의무) |
| 신규 타입 | `frontend/src/types/stock-master.ts` (StockMasterRow / StockMasterStats / StockMasterHistoryRow / ScanPoolSummary) |
| useQuery retry | 사이클 65 H3 / 사이클 75 G-RT1~RT3 영속 — `retry: 1` 명시 의무 (AST G-AST4 영구 가드 영역 확장) |
| E2E mock | `e2e/fixtures/api-mocks.ts` 5 라우트 추가 (사이클 75 G-AST1~AST3 패턴 답습, LIFO 등록 순서 의무 사이클 80 hotfix #3 영속) |

## 10. 결론

- **17 신규 PASS + 2151 백엔드 전체 회귀 0 + flakiness 0 (3 회 0.39s 변동폭)**
- **migration 032 운영 적용 확인** (테이블/인덱스 3종/trigger 3 이벤트 활성)
- 매매 안전성 무영향 확정
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속
- 사이클 85 (프론트) 인계 가능 상태

## 11. 후속 카드 인계

- **사이클 85 (프론트)**: 7번째 메뉴 "종목마스터" + 5 라우트 호출 컴포넌트 + 타입 + useQuery retry:1 + E2E mock 추가
- **사이클 86 (통합 검증)**: E2E (Playwright stock-master.spec.ts) + 운영 stock_master 29건 → 다음 eager refresh 시 history INSERT 실측 + V-4 SQL 재측정 (`history_count > 0` 확인 + `change_type` 분포)
- **사이클 87+ (LOW retention cron)**: Q7=B 90일 retention `purge_old_stock_master_history()` 헬퍼 (사이클 6 `purge_old_logs` 답습)
- **사이클 88+ (LOW 운영 가시화)**: `[stock_master_history_retention_run]` 1행 emit + Settings UI retention 카드
