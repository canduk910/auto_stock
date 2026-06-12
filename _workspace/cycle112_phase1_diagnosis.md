# 사이클 112 Phase 1 진단 — openapi.krx.co.kr 정식 OPEN API 인프라 사전 구성

날짜: 2026-06-12 (금)
대상: KRX Data Marketplace (openapi.krx.co.kr) 정식 OPEN API 키 관리 인프라

## 사이클 111 처리 결과 (배경)

- 사이클 111 (data.krx.co.kr 비공식 endpoint) = 잘못된 endpoint 확정 (KRX anti-bot 정책 차단)
- 사이클 111 코드는 `git stash@{0}: cycle111-data.krx-wrong-endpoint-discarded` 보존
- 사이클 110 baseline 복귀 완료
- 사이클 112 = 신규 구현 (openapi.krx.co.kr 정식 키 관리 인프라만)

## Phase 1 — KIS MCP 정본 영역 적용 여부

KIS MCP 정본 = KIS OpenAPI 한정. KRX 공식 OPEN API 는 별개 시스템 (한국거래소 직접 운영) → kis-mcp-query 스킬 호출 불필요. 다만 KIS `kis_quote_accounts` 마스킹 패턴 (사이클 7-A) 답습은 코드 단계 정합 의무.

## Phase 1 — openapi.krx.co.kr 인증 형식 정밀 조사 결과

### 사이트 조사 (WebFetch + WebSearch 4건 병렬)

| 출처 | 발견 사실 |
|------|----------|
| https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp | 일반 이용 절차 (회원가입 → 인증키 신청 → 서비스 검색 → API 활용 신청 → 개발 적용). 기술 명세 부재. |
| https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd | 6 카테고리 25 API 서비스 (지수 5 + 주식 6 + 증권상품 3 + 채권 3 + 파생상품 5 + 일반상품 3 + ESG 3). |
| https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=...주식... | "Request 헤더에 인증키 값을 AUTH_KEY 필드에 추가" 명시. 개발 명세서 다운로드 링크 존재. |
| https://i-whale.com (블로그) | base URL `https://data-dbg.krx.co.kr/svc/apis/sto` + endpoint 예시 (`/stk_bydd_trd` / `/ksq_bydd_trd` / `/stk_isu_base_info`) + POST + JSON payload (`basDd: YYYYMMDD`) + 응답 `OutBlock_1` 배열 + Rate Limit 키당 일일 10,000 호출 + "API 이용신청" (서비스별 승인) 의무 |
| WebSearch 종합 | base URL `https://data-dbg.krx.co.kr/svc/apis/{category}` (sto 주식 / idx 지수 / etp 증권상품 / bon 채권 / drv 파생상품 / cmm 일반상품 / esg ESG) — 카테고리별 분리 |

### 결정적 발견

1. **인증 방식 = `AUTH_KEY` HTTP header** (KIS 의 `authorization: Bearer ${token}` 영역과 별개 — *Bearer token 모델 아님*)
   - WebSearch 에서 발견된 `Authorization: Bearer ...` 영역 = `ktrs.krx.co.kr` 별도 서비스 (KRX-TR 거래정보 보고). openapi.krx.co.kr 와 무관. 혼동 금지.
2. **base URL = `https://data-dbg.krx.co.kr/svc/apis/{category}`** (사용자 등록 키와 별개 host)
3. **호출 방식 = POST + JSON payload** (`basDd: YYYYMMDD` 형식 + `Content-Type: application/json`)
4. **응답 = `OutBlock_1` 배열** + 필드명 `BAS_DD / ISU_CD / ISU_NM / TDD_CLSPRC / ACC_TRDVOL / MKTCAP` 등 (스네이크 대문자)
5. **Rate Limit = 키당 일일 10,000 호출** (서비스별 승인 = "승인대기" 시 401 응답)
6. **데이터 영역 = 2010년 이후 일자별** (실시간 영역 부재 — KIS 의 실시간 영역과 보완 관계)

### Phase 1 결론

- 사이클 112 = **인프라 사전 구성만** (실제 endpoint 통합은 사이클 113+, 사용자가 endpoint URL + 명세서 제공 후 별도 사이클로 진행)
- 사이클 112 클라이언트 추상 = `AUTH_KEY` header + POST + Supabase 동적 키 로드 + graceful 오류 처리 = 미래 사이클 113+ 통합 영역 즉시 활용 가능

## Phase 2 — 사용자 결정 영역 (확정)

1. 키 출처: openapi.krx.co.kr (KRX Data Marketplace) 정식 OPEN API
2. 키 관리: Supabase 저장 + 설정 페이지 입력 UI
3. 사이클 112 범위: 인프라 사전 구성 (호출 0건, 실제 통합은 사이클 113+)
4. 인증 형식: `AUTH_KEY` header (Phase 1 진단 확정)
5. base URL 디폴트: `https://data-dbg.krx.co.kr/svc/apis` (사용자 수정 가능, DB 저장)
6. 보안: 평문 저장 + 응답 마스킹 (`****1234`, KIS quote-accounts 패턴 답습)

## Phase 2.5 — 영역 분해 (6 영역)

### 영역 1 — Supabase 키 관리 (backend-dev)

- `system_config` 신규 3 키:
  - `krx_open_api_key` (text, SECRET, 평문 저장 + 응답 마스킹)
  - `krx_open_api_base_url` (text, default `https://data-dbg.krx.co.kr/svc/apis`)
  - `krx_open_api_enabled` (bool, default false)
- 헬퍼: `get_krx_open_api_config()` / `set_krx_open_api_config(key=None, base_url=None, enabled=None)`

### 영역 2 — 라우트 (backend-dev)

- `GET /api/integrations/krx-open-api` — 응답 `{enabled, base_url, key_masked: "****1234"}` (평문 절대 노출 금지)
- `PUT /api/integrations/krx-open-api` — body `{key?, base_url?, enabled?}` (key 는 평문 저장 + 응답 마스킹)
- 라우트 위치: `src/routes/system_integrations.py` 확장 (사이클 5 패턴 답습)

### 영역 3 — 클라이언트 추상 (backend-dev)

- `src/api/krx.py` 신규
  - `KrxApiError` 예외 클래스
  - `fetch_krx_open_api(endpoint_path, params)` — Supabase 동적 키 로드 + `AUTH_KEY` header + httpx POST + graceful
- 호출 0건 보장 (scanner.py 변경 0, 사이클 113+ 통합 시점 시작)

### 영역 4 — 설정 페이지 카드 (frontend-dev)

- `frontend/src/components/KrxOpenApiCard.tsx` 신규
- `frontend/src/api/krx-open-api.ts` 신규
- `frontend/src/types/krx-open-api.ts` 신규
- 입력: API key (type=password) + base URL (text) + enabled 토글
- 표시: 마스킹된 키 (`****1234`)
- `useQuery({retry: 1, refetchInterval: 60_000})` (사이클 65 H3 + 사이클 75 G-RT 답습)
- 한글 라벨 ("KRX 정식 OPEN API", 사이클 89 답습)
- `frontend/src/pages/Settings.tsx` 신규 카드 통합

### 영역 5 — MSW + Playwright (frontend-dev)

- `frontend/src/test/handlers.ts` MSW GET/PUT handler
- `e2e/fixtures/api-mocks.ts` Playwright LIFO 정합 (사이클 80 hotfix #3 답습)

### 영역 6 — 회귀 가드 (test)

- 백엔드: Supabase 조회 + 라우트 + 클라이언트 추상 + 마스킹 + graceful (HIGH 5~8 케이스)
- 프론트엔드: 카드 렌더 + 토글 + 마스킹 표시 + retry:1 (HIGH 3~5)
- AST 가드: 키 평문이 코드에 직접 사용되지 않음 + `key_masked` 응답에 평문 키 0건

### 영역 7 — 보안 가드 (test, 추가)

- 평문 키가 commit / log / write_log / system_logs 에 0건 (정적 검증)
- `_kis_rejection` body 자동 마스킹 패턴 KRX 키도 동일 적용

## 영속 의무 매트릭스 (전수 영속)

| 영속 의무 | 영역 적용 |
|-----------|----------|
| 사이클 5 system_integrations (토글 패턴) | 영역 2 |
| 사이클 7-A kis_quote_accounts (마스킹 패턴) | 영역 1 + 2 + 3 |
| 사이클 17 OPSP0002 backoff + KIS 인증 보안 | 영역 3 |
| 사이클 38 명문화 (scanner 매수 진입 전용) | 호출 0건 보장 |
| 사이클 65 H3 useQuery retry:1 | 영역 4 |
| 사이클 68 KST (`_kst.py` 헬퍼) | 영역 1 (system_config upsert) |
| 사이클 75 G-AST5 api-mocks 영역 확장 | 영역 5 |
| 사이클 80 hotfix #3 Playwright LIFO | 영역 5 |
| 사이클 88 G-REJECT 3 (graceful = 호출자 폴백) | 영역 3 |
| 사이클 89 한글 친숙 용어 | 영역 4 |
| 사이클 110 silent 결함 시정 영속 | 영역 3 (호출 0건) |
| CLAUDE.md "절대 깨지 말 것" 8 영역 | 매매 hot path 무관 보장 |

## 매매 안전성 영역

- 사이클 112 = 인프라 사전 구성만 (호출 0건)
- `src/engine/scanner.py` 변경 0
- 매매 hot path 무관

## 보안 의무 (HIGH)

1. API 키 평문은 코드 / 로그 / 커밋 / system_logs / write_log 에 절대 저장 금지 (KIS 인증 보안 패턴 답습)
2. 응답 시 마스킹 의무 (`****1234` 형식, KIS quote-accounts 패턴 답습)
3. Supabase 저장 = 평문 (KIS app_secret 영역 답습) + 응답 마스킹
4. `_kis_rejection` body 처럼 민감 키는 자동 마스킹

## Phase 4 — 검증 의무

- 백엔드 회귀 가드 PASS + flakiness 0
- 프론트엔드 회귀 가드 PASS
- AST 영구 가드 PASS (평문 키 노출 차단)
- 매매 안전성 무영향 확정 (scanner 변경 0)

## 후속 카드 (사이클 113+ 인계)

- 사이클 112 = 인프라 사전 구성 완료 후 사용자가 endpoint URL + 명세서 제공 → 사이클 113+ 별도 사이클로 실제 endpoint 통합 (`fetch_krx_open_api` 호출 사이트 추가)
- 카드 후보:
  - 종목 마스터 보강 (KRX `stk_isu_base_info` 영역 + KIS CTPF1002R 영역 보완)
  - 일자별 거래 데이터 (KRX `stk_bydd_trd` 영역, 사이클 110 silent 결함 영역 대안)
  - 백테스트 데이터 영역 보강 (사이클 113+)
