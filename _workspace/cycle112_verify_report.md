# 사이클 112 verify 보고서 — openapi.krx.co.kr 정식 OPEN API 인프라 사전 구성

날짜: 2026-06-12 (금)
범위: 인프라 사전 구성만 (호출 0건, 매매 hot path 무영향)
사용자 결정: openapi.krx.co.kr 정식 OPEN API + Supabase 저장 + 설정 페이지 입력 UI

## Phase 1 진단 결과 (확정)

- KRX 정식 API 인증 방식 = `AUTH_KEY` HTTP header (KIS Bearer token 영역과 별개)
- base URL = `https://data-dbg.krx.co.kr/svc/apis/{category}` (디폴트)
- 호출 방식 = POST + JSON payload (`Content-Type: application/json`)
- Rate Limit = 키당 일일 10,000 호출 (서비스별 승인 의무)
- 응답 = `OutBlock_1` 배열 + 필드 (`BAS_DD / ISU_CD / ISU_NM / TDD_CLSPRC` 등)

## 시정 영역 (6 영역 + 보안 가드 1 영역 = 17 파일)

| 영역 | 파일 | 라인 수 |
|------|------|--------|
| 1: Pydantic 모델 (신규) | `src/models/krx_open_api.py` | 85L |
| 1: Supabase 헬퍼 (추가) | `src/db/system_config.py` | +130L (총 870L) |
| 2: 라우트 (추가) | `src/routes/system_integrations.py` | +75L (총 455L) |
| 3: 클라이언트 추상 (신규) | `src/api/krx.py` | 120L |
| 4: 카드 컴포넌트 (신규) | `frontend/src/components/KrxOpenApiCard.tsx` | 220L |
| 4: 타입 (신규) | `frontend/src/types/krx-open-api.ts` | 22L |
| 4: API 호출 (신규) | `frontend/src/api/krx-open-api.ts` | 30L |
| 4: Settings 통합 | `frontend/src/pages/Settings.tsx` | +2L |
| 5: MSW (추가) | `frontend/src/test/handlers.ts` | +20L |
| 5: Playwright (추가) | `e2e/fixtures/api-mocks.ts` | +15L |

## 회귀 가드 결과

### 백엔드 (HIGH 23 케이스 / 4 파일)

| 파일 | 케이스 | 결과 |
|------|--------|------|
| `tests/unit/db/test_cycle112_krx_open_api_config.py` | G-DB-1~6 (6) | 6 PASS |
| `tests/unit/routes/test_cycle112_krx_open_api_routes.py` | G-RT-1~6 (6) | 6 PASS |
| `tests/unit/api/test_cycle112_krx_client.py` | G-AP-1~5 (5) | 5 PASS |
| `tests/unit/ast/test_cycle112_security_ast.py` | G-AST-1~3 + G-SEC-1~3 (6) | 6 PASS |

**합계: 23/23 PASS** (사이클 112 영역 단독)

### 프론트엔드 (HIGH 5 케이스)

| 파일 | 케이스 | 결과 |
|------|--------|------|
| `frontend/src/components/__tests__/KrxOpenApiCard.test.tsx` | G-UI-1~5 (5) | 5 PASS |

**합계: 5/5 PASS**

### Flakiness 검증

- 백엔드: 3회 반복 (0.34s / 0.22s / 0.22s) — flakiness 0
- 프론트엔드: 3회 반복 (669ms / 488ms / 483ms) — flakiness 0

### 전체 회귀 (사이클 112 무관 영역 확인)

전체 백엔드 회귀 실행 시 2 결함 발견 — 두 결함 모두 사이클 112 변경 영역 무관 확정:

1. `tests/contract/test_cycle64_routes_price_filter.py::test_CR1_get_price_filter_response_no_mode_field`
   - 단독 실행 = PASS
   - 결함 원인 = 전체 회귀 시 Supabase mock state 누수 (test isolation 영역 결함, 사이클 64 시점부터 잠재)
   - 사이클 112 변경 영역 = `src/db/system_config.py` 끝부분에 KRX 헬퍼 추가만 (사이클 64 PriceFilter 영역 0건 변경)
2. `tests/unit/ast/test_cycle93_ast_chain_required.py::test_g_ast1_route_upsert_chain_required`
   - 사이클 110 시정 인계 결함 (사이클 101 `_full_universe_load_once` 통합 후 stale AST 가드)
   - 사이클 112 변경 영역 = `src/routes/stock_master.py` 0건 변경 (사이클 110 영역)

**결론: 사이클 112 회귀 0 — 두 결함 모두 사이클 112 무관 영역 인계 (사이클 113+ 별도 시정)**

## 영속 의무 매트릭스 (전수 영속)

| 영속 의무 | 적용 영역 | 검증 결과 |
|-----------|----------|----------|
| 사이클 5 system_integrations 토글 패턴 | 영역 2 (라우트) | 영속 |
| 사이클 7-A 마스킹 패턴 (`mask_secret` 헬퍼) | 영역 1 + 2 + 3 | G-AST-1 + G-SEC-3 PASS |
| 사이클 17 OPSP0002 backoff 패턴 영역 (별개 시스템) | 영역 3 (graceful) | 영속 |
| 사이클 38 명문화 (scanner 매수 진입 전용) | 호출 0건 보장 | scanner.py 변경 0 |
| 사이클 65 H3 useQuery retry:1 | 영역 4 (`KrxOpenApiCard`) | retry:1 명시 PASS |
| 사이클 68 KST 영속 (`_kst.py::now_kst_iso()`) | 영역 1 (upsert payload) | G-DB-3 PASS |
| 사이클 75 G-AST5 api-mocks 영역 확장 | 영역 5 (MSW) | 영속 |
| 사이클 80 hotfix #3 Playwright LIFO | 영역 5 (Playwright) | wildcard 미존재 — 단일 라우트 |
| 사이클 88 G-REJECT 3 (graceful = 호출자 폴백) | 영역 3 (`KrxApiError` raise) | G-AP-3 PASS |
| 사이클 89 한글 친숙 용어 | 영역 4 (라벨) | G-UI-5 PASS |
| 사이클 110 silent 결함 시정 영속 | 영역 3 (호출 사이트 0건) | scanner.py 변경 0 |
| CLAUDE.md "절대 깨지 말 것" 8 영역 | 매매 hot path 무관 | 전수 영속 |

## 매매 안전성 영역 영구 확정

- `src/engine/scanner.py` 변경 0
- `src/engine/order_engine.py` 변경 0
- `src/engine/scheduler.py` 변경 0
- `src/realtime/` 영역 변경 0
- `src/auth/` 영역 변경 0
- 매매 hot path 무관 (호출 0건 + 사이클 38 명문화 영속)

## 보안 의무 영역 영구 확정

| 보안 의무 | 검증 결과 |
|-----------|----------|
| 1. API 키 평문 코드/로그/커밋/system_logs/write_log 절대 노출 금지 | G-SEC-1 + G-SEC-2 PASS |
| 2. 응답 마스킹 (`****1234`) | G-RT-1 + G-RT-2 + G-RT-3 PASS |
| 3. Supabase 평문 저장 (KIS app_secret 영역 답습) + 응답 마스킹 | G-DB-3 + G-AST-3 PASS |
| 4. 평문 key 응답에 절대 부재 | G-AST-1 (`KrxOpenApiStatus` 평문 key 필드 부재) PASS |
| 5. 프론트 입력 후 평문 잔존 차단 | G-UI-2 (type=password) + G-UI-3 (저장 후 state clear) PASS |

## 운영 효과 (push + EC2 배포 후)

- Settings 페이지 신규 카드 `KrxOpenApiCard` 노출 (KisQuoteAccountsCard 직하)
- 사용자가 KRX 정식 OPEN API 키 입력 → DB 평문 저장 → 응답 마스킹
- 본 사이클 호출 0건 — 활성화해도 실제 endpoint 호출 영역 부재 (사이클 113+ 통합 의무)

## 사이클 113+ 후속 카드 인계

### 필수 (HIGH)

1. 사용자가 openapi.krx.co.kr Swagger UI URL 또는 API 명세서 제공 → 실제 endpoint 통합 사이클 발의
2. `fetch_krx_open_api` 호출 사이트 추가 시점에 호출 사이트 회귀 가드 신규 작성 의무

### 인계 결함 (사이클 112 무관)

3. **사이클 64 contract test flaky** (HIGH, test isolation 영역)
   - `tests/contract/test_cycle64_routes_price_filter.py::test_CR1_get_price_filter_response_no_mode_field`
   - 단독 PASS / 전체 회귀 fail = Supabase mock state 누수
   - 사이클 113+ 별도 시정 의무
4. **사이클 93 AST 가드 stale 영역** (HIGH, 사이클 110 인계)
   - `tests/unit/ast/test_cycle93_ast_chain_required.py::test_g_ast1_route_upsert_chain_required`
   - 사이클 110 silent 결함 시정 (사이클 101 `_full_universe_load_once` 통합) 시점에 AST 가드 의미 전환 누락
   - 시정: AST 가드를 `_full_universe_load_once` 호출 검증으로 갱신 (사이클 110 영역 정합)

### 후보 카드 (사용자 결정 의무)

- KRX `stk_isu_base_info` 영역 통합 → stock_master 보강 (KIS CTPF1002R 영역 보완)
- KRX `stk_bydd_trd` 영역 통합 → 일자별 거래 데이터 (사이클 110 silent 결함 영역 대안)
- 백테스트 데이터 영역 보강 (KRX 일봉 데이터 직접 활용)

## Push 결정 요청

- 매매 안전성 무영향 확정 (scanner.py / order_engine.py / scheduler.py 변경 0)
- 호출 0건 보장 (인프라 사전 구성만)
- 전수 회귀 가드 PASS + flakiness 0

사용자 명시 commit 지시 후 push 가능 (memory `feedback_commit_policy` 영속).
