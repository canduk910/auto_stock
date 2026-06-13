# 사이클 128 — 종목마스터 필터 + 전체현황 시정

## 사용자 요청 (verbatim)
"종목마스터의 종목목록에 필터링 기능을 넣어줘. (시장/시가총액/거래대금/종목명일부 등) 그리고 전체현황을 산출하는 로직을 점검해봐. 전체종목수를 제외하고는 페이징처리 중에 엉망이 되는 것 같아."

## 진단 결과 (HIGH 결함 확정)
사이클 126 `count_all` 만 count="exact" 시정. 나머지 4 카운트 (`bfdy_clpr_present` / `nxt_tradable_count` / `with_hts_avls` / `with_acml_tr_pbmn`) 는 `.range(0, 9999)` Python-side sum → **PostgREST 1000행 silent cap** → 부분 집계. 운영자 의사결정 silent 결함 HIGH.

## 사용자 결정
- Q1=A: count="exact" + filter 별도 쿼리 (4 카운트 분리)
- Q2=A: 상단 인라인 4 컨트롤 (시장 select + 시총 min + 거래대금 min + 종목명 substr) + 400ms 디바운스 + URL 동기화
- Q3=A: team-leader 위임 + TDD 사이클

## 시정 영역 (5 영역 통합)

### P0-1 — `src/db/stock_master.py::get_stats()` 4 카운트 시정 (HIGH)
- 4 카운트 모두 count="exact" 별도 쿼리 (사이클 126 패턴 100% 답습)
- `.range(0, 9999)` Python-side sum 영역 영구 폐기
- `top_10_recent` 별도 작은 `limit(10)` fetch
- `_count_exact()` 헬퍼 캡슐화

### P0-5 — AST 회귀 가드 (HIGH 동행)
- `tests/unit/ast/test_cycle128_ast_no_range_9999_silent_cap.py` — `src/db/` 전체 `.range(0, 9999)` 잔존 0건 영구 가드 (2 케이스)
- `tests/unit/db/test_cycle128_get_stats_exact_count_per_key.py` 4 케이스

### P1-2 — `list_paged_by_filter()` 신규 + 라우트 (MEDIUM)
- 신규 함수 `src/db/stock_master.py::list_paged_by_filter()`
- 반환 schema = `{items, total, limit, offset}` (사이클 128 envelope)
- 정렬 `refreshed_at DESC` 영속
- 4 필터: market / min_market_cap (원) / min_trade_amount (원) / name_substr
- **JSONB numeric 비교 (사이클 128 Supabase MCP 검증 확정)**:
  - `raw->'hts_avls'` (jsonb operator) numeric gte → **정확** (332 vs text 비교 2696 silent 결함 영구 차단)
  - `raw->>'hts_avls'` text gte 자릿수 비교 결함 영구 폐기
  - KIS 응답 99.96% jsonb number 타입 영속
- 라우트 `GET /api/stock-master/list` query param 4 추가
- `_eok_to_won()` 헬퍼 (T-2 단위 변환 캡슐화)
- 회귀 가드 7+6=13 케이스

### P1-3 — 프론트 필터 UI (MEDIUM)
- `frontend/src/pages/StockMaster.tsx` 4 컨트롤 인라인
- 400ms 디바운스 + `useSearchParams` URL 동기화
- IME composition 가드 (T-3 영속 — 한글 자모 입력 중 trigger 차단)
- 필터 초기화 버튼 (T-1 영속 — 빈 필터 = 전체)
- 페이지네이션 = `total` 기준
- 회귀 가드 7 케이스 (`StockMaster.cycle128.test.tsx`)

### P2-4 — MSW + Playwright (MEDIUM)
- `frontend/src/test/handlers.ts` envelope 응답 + name_substr 필터 흡수
- `e2e/fixtures/api-mocks.ts` LIFO 정합 envelope 응답
- `frontend/src/api/stock-master.ts::fetchList` 시그너처 (params object) + 호환 layer (Array → envelope 정규화)

## 의미 전환 (사이클 66 K-2 패턴)
- 사이클 124 G-STATS1/2 (`with_hts_avls` / `with_acml_tr_pbmn` Python-side sum mock) — xfail
- 사이클 126 G-COUNT2 (raw len(rows) fallback) — xfail

## 회귀 가드 누적
- 백엔드: 19 케이스 (사이클 128 신규) + 사이클 124/126 2 의미 전환 xfail
- 프론트: 7 케이스 (StockMaster.cycle128.test.tsx)
- 합계 26 신규 + 기존 호환 layer 영속

## 매매 안전성 무영향 확정
- `src/db/stock_master.py` GET 영역만 변경 (UPSERT/스키마 변경 0)
- `src/routes/stock_master.py` GET 영역만 변경 (POST 변경 0)
- `src/engine/scanner.py` / `risk.py` / `order_engine.py` / `realtime/` / `auth/` 변경 0
- 매매 hot path 무관 (사이클 38 명문화 영속)

## 운영 실측 검증 (Supabase MCP READ-ONLY)

| 카운트 | 사이클 128 결과 | SQL 정답 | 정확도 |
|--------|----------------|---------|-------|
| count_all | 2,697 | 2,697 | ✓ |
| nxt_tradable_count | 0 | 0 | ✓ |
| bfdy_clpr_present | 2,696 | 2,696 | ✓ |
| with_hts_avls | 2,696 | 2,696 | ✓ |
| with_acml_tr_pbmn | 2,582 | 2,582 | ✓ |

| 필터 조합 | total | 정확도 |
|---------|-------|-------|
| 빈 필터 | 2,697 | ✓ |
| KOSPI | 922 | ✓ |
| 시총≥1조 | 332 | ✓ JSONB numeric gte |
| name=삼성 | 20 | ✓ ILIKE substring |

## 영속 의무 매트릭스
- 사이클 38 (scanner 단계 매수 진입 전용 무관, GET 영역만)
- 사이클 65/64 (TradeAmountFilterCard / PriceFilterCard UI 패턴)
- 사이클 66 K-2 (의미 전환 xfail)
- 사이클 68 (KST 영역 영속)
- 사이클 75 G-AST5 (api-mocks 정합)
- 사이클 80 hotfix #3 (Playwright LIFO)
- 사이클 84 L-2 (POST 화이트리스트 영속, 본 사이클 변경 0)
- 사이클 89 (한글 친숙 용어)
- 사이클 108 (list_by_filter scanner 전용 별개, UI list 분리 영속)
- 사이클 124 G-AST1 (영속, 본 사이클 변경 0)
- 사이클 126 count="exact" 패턴 100% 답습
- 사이클 127 (fire-and-forget 영속, 본 사이클 GET 영역만 무관)
- T-1 빈 필터 = 전체 영속
- T-2 단위 변환 헬퍼 (`_eok_to_won`) 캡슐화
- T-3 IME composition 가드
- T-4 종목명 컬럼 = `name` (Supabase MCP 검증 확정)
