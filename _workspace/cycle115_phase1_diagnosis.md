# 사이클 115 Phase 1 진단 — KRX OPEN API endpoint 실제 통합

날짜: 2026-06-12 (금)
대상: openapi.krx.co.kr 정식 OPEN API 4개 endpoint 실제 통합 + 사이클 112 추상 결함 3건 동시 시정
사용자 결정 (확정): Q1=양쪽 endpoint (bydd_trd + isu_base_info) 통합 + Q2/Q3=C 폴백 영속 (KRX 1차 + KIS 자동 폴백)

## Phase 1 — 외부 명세 정밀 조사 결과 (정본 영구 확정)

### 출처 (2건 독립 검증)

| 출처 | 영역 |
|------|------|
| `seobaeksol/krx-rs/docs/krx-api-reference/KRX_API_Spec.md` (28KB) | 4 endpoint 응답 필드 완전 명세 |
| `raccoonyy/pykrx-openapi/src/pykrx_openapi/client.py` + `constants.py` | HTTP method + 인증 형식 + 파라미터 위치 결정적 검증 |

### 결정적 발견 4건 (정본 영구 확정)

| 항목 | 사이클 112 가정 (결함) | 사이클 115 정본 영구 영속 |
|------|----------------------|-------------------|
| HTTP method | POST | **GET** |
| 인증 위치 | HTTP header `AUTH_KEY:` | **query parameter `AUTH_KEY=`** |
| 파라미터 위치 | JSON body | **query string `params=`** |
| Base URL | `https://data-dbg.krx.co.kr/svc/apis` | 동일 (`https://...`) |

**pykrx-openapi 클라이언트 인용 (정본)**:
```python
# src/pykrx_openapi/client.py
response = self.session.get(url, params=params, timeout=self.timeout)
# params:
params = {
    "AUTH_KEY": self.api_key,
    "basDd": bas_dd,
}
```

**결론**: 사이클 112 `fetch_krx_open_api` 추상 = 3 영역 silent 결함 (POST + JSON body + AUTH_KEY header) → 사이클 115 = 신규 endpoint 통합 + 사이클 112 추상 결함 시정 동시 진행.

### 4 endpoint 응답 schema 완전 명세 (정본 영구 영속)

#### 1. `stk_bydd_trd` + `ksq_bydd_trd` (일별 매매정보) — 응답 동일

URL: `https://data-dbg.krx.co.kr/svc/apis/sto/{stk|ksq}_bydd_trd`
Method: GET
Params: `basDd=YYYYMMDD` + `AUTH_KEY=...`

15 필드:
| 필드 | 의미 |
|------|------|
| `BAS_DD` | 기준일자 (YYYY/MM/DD) |
| `ISU_CD` | 종목코드 (단축코드 6자리, KRX 종목코드 정합) |
| `ISU_NM` | 종목명 |
| `MKT_NM` | 시장구분 (KOSPI/KOSDAQ) |
| `SECT_TP_NM` | 소속부 |
| `TDD_CLSPRC` | 종가 |
| `CMPPREVDD_PRC` | 대비 (전일 대비) |
| `FLUC_RT` | 등락률 |
| `TDD_OPNPRC` | 시가 |
| `TDD_HGPRC` | 고가 |
| `TDD_LWPRC` | 저가 |
| `ACC_TRDVOL` | 거래량 |
| `ACC_TRDVAL` | 거래대금 (원 단위, 사이클 108 `min_trade_amount` 직접 정합) |
| `MKTCAP` | 시가총액 (원 단위, 사이클 108 `min_market_cap` 직접 정합 — KIS `hts_avls` 백만원 단위와 차이 영구 영속 주의) |
| `LIST_SHRS` | 상장주식수 |

#### 2. `stk_isu_base_info` + `ksq_isu_base_info` (종목 기본정보) — 응답 동일

URL: `https://data-dbg.krx.co.kr/svc/apis/sto/{stk|ksq}_isu_base_info`
Method: GET
Params: `basDd=YYYYMMDD` + `AUTH_KEY=...`

12 필드:
| 필드 | 의미 |
|------|------|
| `ISU_CD` | 표준코드 (12자리) |
| `ISU_SRT_CD` | **단축코드 6자리 (KRX 종목코드 정합 영구 영속)** |
| `ISU_NM` | 한글 종목명 |
| `ISU_ABBRV` | 한글 종목약명 |
| `ISU_ENG_NM` | 영문 종목명 |
| `LIST_DD` | 상장일 |
| `MKT_TP_NM` | 시장구분 (KOSPI/KOSDAQ) |
| `SECUGRP_NM` | 증권구분 |
| `SECT_TP_NM` | 소속부 |
| `KIND_STKCERT_TP_NM` | 주식종류 (보통주/우선주) |
| `PARVAL` | 액면가 |
| `LIST_SHRS` | 상장주식수 |

**ticker 정규화 주의 (사이클 30 답습)**: `bydd_trd` = `ISU_CD` 단축코드 6자리 직접 / `isu_base_info` = `ISU_SRT_CD` 단축코드 6자리 직접 (`ISU_CD` 표준코드 12자리 사용 금지).

### 공통 사항

- Content-Type: application/json (요청)
- 응답 형식: `{"OutBlock_1": [{...}, ...]}` JSON 배열
- 누락 시 graceful: `{"OutBlock_1": []}` 빈 배열 반환
- 모든 응답값 String 타입 (호출자가 int 변환 의무)
- Rate Limit: 키당 일일 10,000 호출 (4 endpoint × 1 호출/일 = 4 호출 = 0.04% 영역, 무관)

## Phase 2 — 사용자 결정 영역 (확정)

| 의제 | 사용자 결정 | 영역 영구 영속 |
|------|-----------|--------------|
| Q1 endpoint 선택 | A (양쪽 통합 bydd_trd + isu_base_info) | 4 호출 (KOSPI/KOSDAQ × 2 endpoint) |
| Q2 KIS 처리 | (Q3 영속) | (Q3 영속) |
| Q3 폴백 방식 | C (KRX 1차 + KIS 자동 폴백 영속) | KrxApiError 시 사이클 109 KIS market-cap 영역 영속 |

## Phase 2.5 — 영역 분해 (5 영역)

### 영역 1 (backend-dev) — `src/api/krx.py` 추상 결함 3건 시정 + 4 endpoint 함수

**1-A. `fetch_krx_open_api` 추상 시정** (사이클 112 silent 결함 영구 차단):
- POST → **GET** (`httpx.AsyncClient.get`)
- JSON body → **query parameter** (`params=`)
- AUTH_KEY header → **AUTH_KEY query parameter** (params dict 에 추가)
- 401 핸들링 영속 + httpx 예외 graceful → KrxApiError 영속

**1-B. 신규 함수 4종**:
- `fetch_stk_bydd_trd(date: str) -> list[dict]` — KOSPI 일별 매매정보 (`OutBlock_1` 배열 반환)
- `fetch_ksq_bydd_trd(date: str) -> list[dict]` — KOSDAQ 일별 매매정보
- `fetch_stk_isu_base_info(date: str) -> list[dict]` — KOSPI 종목 기본정보
- `fetch_ksq_isu_base_info(date: str) -> list[dict]` — KOSDAQ 종목 기본정보

graceful: `KrxApiError` raise (사이클 112 영속). 호출자 (사이클 115 영역 2) Q3=C 폴백 의무.

### 영역 2 (backend-dev) — `src/engine/scanner.py` `_full_universe_load_once()` 갱신 (Q3=C 폴백)

신규 함수 `_full_universe_load_krx_primary()` + 기존 함수 본체 `_full_universe_load_kis_fallback()` 으로 추출 + try/except 폴백 패턴:

```python
async def _full_universe_load_once() -> dict:
    try:
        summary = await _full_universe_load_krx_primary()
        summary["source"] = "krx"
        return summary
    except KrxApiError as exc:
        logger.warning(f"[krx_open_api_fallback] KRX 실패 → KIS market-cap 폴백 (graceful): {exc}")
        summary = await _full_universe_load_kis_fallback()  # 기존 사이클 101+109+110 영역 영속
        summary["source"] = "kis_fallback"
        return summary
```

stock_master upsert 영역 (KRX 응답 → raw JSONB merge):
- KRX `bydd_trd` 응답 → ticker(`ISU_CD`) / name(`ISU_NM`) / market(`MKT_NM`) / `MKTCAP` (원 단위, 사이클 108 `min_market_cap` 직접 정합) / `ACC_TRDVAL` (원 단위, 사이클 108 `min_trade_amount` 직접 정합) / `LIST_SHRS`
- KRX `isu_base_info` 응답 → `LIST_DD` (상장일) / `SECUGRP_NM` / `KIND_STKCERT_TP_NM` 추가 보강
- raw JSONB merge 패턴 (사이클 107/108 답습) — KRX 키는 신규 영역으로 추가 (사이클 81 G-AST1 영속 = `bfdy_clpr` / `hts_avls` 덮어쓰기 0)

Rate Limit: 4 호출 + 50ms sleep (KIS LMS chain 안전 마진 답습)

### 영역 3 (test) — 회귀 가드 매트릭스

| 등급 | 케이스 | 영역 |
|------|--------|------|
| HIGH-1 | `fetch_krx_open_api` GET method + query params + AUTH_KEY query (3 sub) | 사이클 112 silent 결함 영구 차단 |
| HIGH-2 | 4 endpoint 함수 정상 응답 (4 sub) | 신규 영역 |
| HIGH-3 | Q3=C 폴백 패턴 (KRX 성공 + KrxApiError → KIS 폴백 + KIS도 실패 시 raise) (3 sub) | 사이클 88 G-REJECT 영속 |
| HIGH-4 | Rate Limit 50ms sleep | KIS LMS chain 답습 |
| MEDIUM-1 | stock_master upsert 정합 (KRX raw JSONB merge, KIS 키 보존) | 사이클 107/108 답습 |
| MEDIUM-2 | T+1 갱신 정합 (basDd 형식) | 단위 가드 |
| AST-1 | KRX endpoint URL 정적 검증 (`/sto/stk_bydd_trd` 등) | 미래 결함 영구 차단 |
| AST-2 | 응답 키 정적 검증 (`OutBlock_1` 영역) | 미래 결함 영구 차단 |
| 보안 가드 | API 키 평문 로그/commit 0 | 사이클 112 영속 + 사이클 17 KIS 보안 패턴 |

### 영역 4 (영구 영속) — 매매 안전성 무영향 확정

- scanner 단계 = 매수 진입 전 후보 풀 영역 한정 (사이클 38 명문화 영속)
- 매도/익일청산/15:20 강제청산 hot path 무관
- KIS LMS chain 영향 0 (KRX 별개 외부 API + Q3=C 폴백 영속)
- `src/engine/order_engine.py` 변경 0
- `src/realtime/` 영역 변경 0
- `src/auth/` 영역 변경 0

### 영역 5 (산출물) — 영구 기록

- `_workspace/red/cycle115_krx_endpoint_integration.md` Red 명세 (명료한 한국어)
- `_workspace/cycle115_phase1_diagnosis.md` (본 문서)
- `_workspace/cycle115_verify_report.md` verify 보고서

## 영속 의무 매트릭스 (전수 영속)

| 영속 의무 | 적용 영역 |
|-----------|----------|
| 사이클 17 KIS 인증 보안 (API 키 평문 로그 0) | 영역 1 + 보안 가드 |
| 사이클 32 R4 universe guard | 영역 2 (`_full_universe_load_kis_fallback` 영역 영속) |
| 사이클 38 명문화 (scanner 매수 진입 전용) | 영역 2 |
| 사이클 81 G-AST1 (`bfdy_clpr` / `hts_avls` 덮어쓰기 0) | 영역 2 (KRX 키 신규 추가만, KIS 키 영구 보존) |
| 사이클 88 G-REJECT (graceful = 호출자 폴백 의무) | 영역 1 (KrxApiError) + 영역 2 (Q3=C 폴백) |
| 사이클 89 한글 친숙 용어 | 로그 메시지 |
| 사이클 101 영속 (`_full_universe_load_once` 24h TTL idempotency) | 영역 2 |
| 사이클 106 영속 (lifecycle race 차단) | 영역 2 |
| 사이클 107/108 영속 (raw 보강 의존성) | 영역 2 (KRX raw merge 영역 정합) |
| 사이클 109 영속 (KIS market-cap 화이트리스트 영역) | 영역 1 (KRX 별개 base URL 영구 확정 — 화이트리스트 영역 외) |
| 사이클 110 영속 (silent 결함 시정 패턴) | 영역 1 (사이클 112 추상 결함 동일 패턴 시정) |
| 사이클 112 영속 (KRX 인프라 + 마스킹 + graceful) | 영역 1 (추상 결함 시정 + 영역 영구 영속) |
| 사이클 113 영속 (CI fail 시정 패턴) | 영역 3 (회귀 가드 작성 시 mock 정합) |
| 사이클 114 영속 (Deploy workflow_run + push 후 CI 확인 의무) | push 결정 시 |
| CLAUDE.md "절대 깨지 말 것" 8 영역 | 매매 hot path 무관 보장 |

## 보안 의무 (HIGH)

1. API 키 평문 로그/commit 절대 0 (사이클 112 영속 + 사이클 17 KIS 인증 보안 패턴 답습)
2. 사이클 112 `key_masked` 응답 영속
3. KrxApiError 메시지에 평문 key 노출 금지 (사이클 112 영속)
4. AUTH_KEY query parameter URL 로그 노출 시 마스킹 의무 (URL `?AUTH_KEY=secret...` → endpoint_path 만 로그)

## Push 결정 (사용자 명시 commit 지시 의무)

memory `feedback_commit_policy` 영속 — 사용자 명시 commit 지시 시에만 push. 작업 완료 후 사용자에게 결과 보고 + push 결정 요청.
