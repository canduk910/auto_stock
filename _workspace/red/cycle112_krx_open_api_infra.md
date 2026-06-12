# 사이클 112 Red 명세 — openapi.krx.co.kr 정식 OPEN API 인프라 사전 구성

날짜: 2026-06-12 (금)
범위: 인프라 사전 구성 (호출 0건, 사이클 113+ 통합 의무)

## 요구사항

KRX Data Marketplace (openapi.krx.co.kr) 정식 OPEN API 키를 Supabase 에 안전하게 저장하고, Settings UI 에서 입력/조회/토글 가능한 인프라를 사전 구성한다. 평문 키는 응답/로그/커밋에 절대 노출되지 않으며, 마스킹된 키 (`****1234`) 만 노출한다. 클라이언트 추상 (`fetch_krx_open_api`) 은 미래 사이클 113+ 통합 영역 즉시 활용 가능한 형태로 준비한다.

## 영역 1 — Supabase 키 관리 (system_config 신규 3 키)

### 회귀 가드 (HIGH 6)

**G-DB-1** (HIGH): `get_krx_open_api_config()` 가 키 부재 시 디폴트 반환 (`enabled=False`, `base_url="https://data-dbg.krx.co.kr/svc/apis"`, `key=""`)

**G-DB-2** (HIGH): `get_krx_open_api_config()` 가 3 키 모두 DB 존재 시 정확 반환

**G-DB-3** (HIGH): `set_krx_open_api_config(key="abc1234")` 가 `system_config.krx_open_api_key` 평문 저장 + KST timestamp 사용 (`_kst.py::now_kst_iso()` 영속)

**G-DB-4** (HIGH): `set_krx_open_api_config(enabled=True)` 부분 갱신 (key 미지정 시 기존 key 보존)

**G-DB-5** (HIGH): `set_krx_open_api_config(base_url="https://custom.krx.co.kr")` 부분 갱신

**G-DB-6** (HIGH): `KrxOpenApiConfig` Pydantic 모델이 3 필드 명확 정의

## 영역 2 — 라우트 (`/api/integrations/krx-open-api`)

### 회귀 가드 (HIGH 6)

**G-RT-1** (HIGH): `GET /api/integrations/krx-open-api` 응답 = `{enabled: bool, base_url: str, key_masked: str}` 정확 형식

**G-RT-2** (HIGH): 응답 `key_masked` 가 평문 키 0건 노출 (8자 이상 → `****1234`, 8자 미만 → `****`)

**G-RT-3** (HIGH): `PUT /api/integrations/krx-open-api` body `{key: "secret_key_1234"}` → DB 평문 저장 + 응답은 마스킹 (`****1234`)

**G-RT-4** (HIGH): `PUT` body 가 enabled/base_url 만 포함 (key 부재) → 기존 key 보존

**G-RT-5** (HIGH): `PUT` 빈 body → 422 또는 기존 값 유지 (decision: 기존 값 유지 = graceful, KIS 자문 패턴 답습)

**G-RT-6** (HIGH): DB 갱신 실패 시 500 (사이클 5 패턴 답습)

## 영역 3 — 클라이언트 추상 (`src/api/krx.py`)

### 회귀 가드 (HIGH 5)

**G-AP-1** (HIGH): `KrxApiError` 예외 클래스 정의 + import 가능

**G-AP-2** (HIGH): `fetch_krx_open_api(endpoint_path, params)` 가 Supabase 에서 동적 키 로드 (호출 시점 캐시 없음, 미래 사이클 113+ 영역에서 캐싱 추가 가능)

**G-AP-3** (HIGH): `enabled=False` 또는 키 부재 시 `KrxApiError("KRX OPEN API 비활성 또는 키 부재")` raise (사이클 88 G-REJECT graceful 영속)

**G-AP-4** (HIGH): httpx POST + `AUTH_KEY` header + `Content-Type: application/json` body 전송 (Phase 1 진단 확정 형식)

**G-AP-5** (HIGH): httpx 예외 (네트워크/timeout) 시 `KrxApiError` 변환 raise (graceful)

## 영역 4 — 설정 페이지 카드 (`KrxOpenApiCard`)

### 회귀 가드 (HIGH 5)

**G-UI-1** (HIGH): `KrxOpenApiCard` 컴포넌트 렌더 시 GET 응답 표시 (`enabled` 토글 + `base_url` 입력 + `key_masked` 표시)

**G-UI-2** (HIGH): API key 입력 필드 = `type="password"` (평문 잔존 차단)

**G-UI-3** (HIGH): 저장 버튼 클릭 → `PUT /api/integrations/krx-open-api` 호출 + 입력값 평문 잔존 차단 (저장 후 key state clear)

**G-UI-4** (HIGH): `useQuery({retry: 1, refetchInterval: 60_000})` 명시 (사이클 65 H3 + 사이클 75 G-RT 영속)

**G-UI-5** (HIGH): 한글 라벨 ("KRX 정식 OPEN API", "키 입력", "활성화", "기본 URL", 사이클 89 영속)

## 영역 5 — MSW + Playwright

### 회귀 가드 (HIGH 2)

**G-MSW-1** (HIGH): MSW handler GET/PUT 등록 (`handlers.ts`)

**G-PW-1** (HIGH): Playwright api-mocks 등록 (`api-mocks.ts`) + LIFO 정합 (사이클 80 hotfix #3 영속, 구체 라우트 *후* 등록)

## 영역 6 — AST 영구 가드 (보안 의무)

### 회귀 가드 (HIGH 3)

**G-AST-1** (HIGH): 응답 모델 (`KrxOpenApiStatus`) 에 평문 key 필드 0건 = `key_masked` 단독 존재 (Pydantic 모델 정적 검증)

**G-AST-2** (HIGH): `src/routes/system_integrations.py` 에서 `key_masked` 응답 직접 작성 시 평문 key 0건 (AST 정규식 가드)

**G-AST-3** (HIGH): `src/db/system_config.py` 의 `get_krx_open_api_config` 반환에는 평문 key 가 포함되지만, `src/routes/system_integrations.py` 에서 응답 빌더는 `mask_secret(config.key)` 호출 의무 (AST 정적 검증)

## 영역 7 — 보안 가드 (전용 AST)

### 회귀 가드 (HIGH 2)

**G-SEC-1** (HIGH): `src/` 전체 rglob 에서 `krx_open_api_key` 평문 logger.* 호출 0건 (`grep` 정적 검증)

**G-SEC-2** (HIGH): `src/` 전체 rglob 에서 `write_log` / `system_logs` INSERT 에 평문 key 전달 0건 (정적 검증)

## 영속 의무 매트릭스

| 영속 의무 | 적용 영역 |
|-----------|----------|
| 사이클 5 system_integrations 토글 패턴 | 영역 2 (라우트) |
| 사이클 7-A kis_quote_accounts 마스킹 (`mask_secret` 헬퍼) | 영역 1 + 2 + 3 |
| 사이클 38 명문화 (scanner 매수 진입 전용) | 호출 0건 보장 (변경 0) |
| 사이클 65 H3 useQuery retry:1 | 영역 4 (`KrxOpenApiCard`) |
| 사이클 68 KST 영속 (`_kst.py::now_kst_iso()`) | 영역 1 (system_config upsert payload) |
| 사이클 75 G-AST5 api-mocks 영역 확장 | 영역 5 (MSW) |
| 사이클 80 hotfix #3 Playwright LIFO | 영역 5 (Playwright) |
| 사이클 88 G-REJECT 3 (graceful = 호출자 폴백) | 영역 3 (`KrxApiError` raise) |
| 사이클 89 한글 친숙 용어 | 영역 4 (라벨) |
| 사이클 110 silent 결함 시정 영속 | 영역 3 (호출 사이트 0건) |
| CLAUDE.md "절대 깨지 말 것" 8 영역 | 매매 hot path 무관 확정 |

## 매매 안전성 확정

- `src/engine/scanner.py` 변경 0
- `src/engine/order_engine.py` 변경 0
- `src/engine/scheduler.py` 변경 0
- 매매 hot path 무관 (호출 0건 + 사이클 38 명문화 영속)

## 합계 회귀 가드 영역

- 영역 1: HIGH 6
- 영역 2: HIGH 6
- 영역 3: HIGH 5
- 영역 4: HIGH 5
- 영역 5: HIGH 2
- 영역 6: HIGH 3
- 영역 7: HIGH 2
- **합계: HIGH 29 케이스** (보안 의무 영역 = 정적 가드 추가 가능)

## 산출물

- 백엔드 신규: `src/api/krx.py` (~80L) + `src/models/krx_open_api.py` (~50L) + `src/db/system_config.py` 추가 헬퍼 (~80L) + `src/routes/system_integrations.py` 라우트 추가 (~70L)
- 프론트 신규: `frontend/src/types/krx-open-api.ts` (~30L) + `frontend/src/api/krx-open-api.ts` (~70L) + `frontend/src/components/KrxOpenApiCard.tsx` (~200L)
- 갱신: `frontend/src/pages/Settings.tsx` (+5L) + `frontend/src/test/handlers.ts` (+30L) + `e2e/fixtures/api-mocks.ts` (+20L) + `src/main.py` (라우트 등록 필요 시)
- 테스트: 영역 1~7 회귀 가드 신규 (HIGH 29)
- 명세: `_workspace/red/cycle112_krx_open_api_infra.md` (본 문서)
- 진단: `_workspace/cycle112_phase1_diagnosis.md`
- 검증: `_workspace/cycle112_verify_report.md` (verify 후 작성)
