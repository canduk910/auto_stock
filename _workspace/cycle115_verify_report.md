# 사이클 115 verify 보고서 — KRX OPEN API endpoint 실제 통합

날짜: 2026-06-12 (금)
범위: 4 endpoint 실제 통합 (양쪽 통합 + Q3=C 폴백) + 사이클 112 추상 결함 3건 시정
사용자 결정: Q1=양쪽 endpoint (bydd_trd + isu_base_info) + Q3=C 폴백 영속

## Phase 1 진단 결과 (정본 영구 확정)

외부 검증 2건 독립 일치:
- `seobaeksol/krx-rs/docs/krx-api-reference/KRX_API_Spec.md` (응답 schema 28KB)
- `raccoonyy/pykrx-openapi/src/pykrx_openapi/client.py` (정본 코드 인용)

**결정적 발견 4건 (사이클 112 추상 결함 3건 시정 의무)**:

| 항목 | 사이클 112 가정 | 사이클 115 정본 영구 영속 |
|------|----------------|----------------------|
| HTTP method | POST | **GET** |
| 인증 위치 | HTTP header `AUTH_KEY:` | **query parameter `AUTH_KEY=`** |
| 파라미터 위치 | JSON body | **query string `params=`** |
| Base URL | `https://data-dbg.krx.co.kr/svc/apis` | 동일 |

## 시정 영역 (production 2 파일)

### 영역 1 — `src/api/krx.py` (+98L 순증, 사이클 112 추상 결함 시정 + 4 endpoint 함수 신규)

**1-A. `fetch_krx_open_api` 추상 시정**:
- `client.post(url, headers=headers, json=body)` → `client.get(url, params=merged_params)`
- AUTH_KEY header 영역 → AUTH_KEY query parameter 영역 (params dict 자동 병합)
- Content-Type header 제거 (GET 영역)
- 401 / 4xx / 5xx / httpx 예외 graceful 영속 (사이클 88 G-REJECT)

**1-B. 신규 함수 4종 + 상수 5개**:
- `_ENDPOINT_STK_BYDD_TRD` / `_ENDPOINT_KSQ_BYDD_TRD` / `_ENDPOINT_STK_ISU_BASE_INFO` / `_ENDPOINT_KSQ_ISU_BASE_INFO` / `_OUTBLOCK_KEY` (AST 영구 가드 영역)
- `fetch_stk_bydd_trd(date)` / `fetch_ksq_bydd_trd(date)` / `fetch_stk_isu_base_info(date)` / `fetch_ksq_isu_base_info(date)` 4 함수

### 영역 2 — `src/engine/scanner.py` (+~190L 순증, Q3=C 폴백 구조)

**2-A. `_full_universe_load_once()` Q3=C 폴백 시정**:
```python
try:
    summary = await _full_universe_load_krx_primary()
    summary["source"] = "krx"
except KrxApiError:
    summary = await _full_universe_load_kis_fallback()
    summary["source"] = "kis_fallback"
```

**2-B. `_full_universe_load_krx_primary()` 신규 함수**:
- 4 KRX 호출 (KOSPI/KOSDAQ × bydd_trd/isu_base_info) + 50ms sleep × 3건
- bydd_trd → isu_base_info 매핑 (ISU_SRT_CD 6자리 정합)
- raw JSONB merge: bydd_trd 11 키 + isu_base_info 7 키 추가
- 사이클 81 G-AST1 영속: KIS `bfdy_clpr` / `hts_avls` 덮어쓰기 0 (KRX 키 신규 영역)
- 24h TTL idempotency (사이클 83/101 영속)
- 사이클 88 G-REJECT 영속 (개별 ticker 실패 graceful continue)

**2-C. `_full_universe_load_kis_fallback()` 함수 본체 추출** (행위 변경 0):
- 사이클 101+109+110 영역 영구 영속 본체 추출 (Q3=C 폴백 영역)

## 회귀 가드 매트릭스 결과

### 사이클 115 신규 (18 케이스, 3 파일)

| 파일 | 케이스 | 결과 |
|------|--------|------|
| `tests/unit/api/test_cycle115_krx_endpoints.py` | HIGH-2 (6) | 6 PASS |
| `tests/unit/engine/scanner/test_cycle115_full_universe_load_krx_fallback.py` | HIGH-3 (3) + HIGH-4 (1) + MEDIUM-1 (1) | 5 PASS |
| `tests/unit/ast/test_cycle115_krx_endpoint_urls.py` | AST (4) | 4 PASS |
| `tests/unit/ast/test_cycle115_krx_no_plaintext_key.py` | SEC (3) | 3 PASS |

### 사이클 112 갱신 (5 케이스, 1 파일)

| 파일 | 갱신 영역 | 결과 |
|------|----------|------|
| `tests/unit/api/test_cycle112_krx_client.py` | G-AP-2 (POST → GET) + G-AP-4 (header → query param 의미 전환) + G-AP-5 (POST → GET) | 5 PASS |

**합계: 23/23 PASS** (사이클 115 영역 단독)

### Flakiness 검증 (3회 반복 일관)

| 회차 | 시간 | 결과 |
|------|------|------|
| 1차 | 0.19s | 23 PASS |
| 2차 | 0.13s | 23 PASS |
| 3차 | 0.13s | 23 PASS |

**flakiness 0** — 3회 반복 동일 카운트.

### 전체 회귀 (사이클 115 무관 영역)

| 영역 | 결과 |
|------|------|
| 전체 백엔드 (contract 제외) | **2291 PASS + 143 XFAIL + 1 XPASS** |
| 회귀 발생 | **0** |
| 매매 안전성 영향 | **0** |

## 영속 의무 매트릭스 검증 결과

| 영속 의무 | 적용 영역 | 검증 결과 |
|-----------|----------|----------|
| 사이클 17 KIS 인증 보안 (API 키 평문 로그 0) | 영역 1 + SEC-1 | SEC-1 PASS |
| 사이클 32 R4 universe guard | 영역 2 (KIS 폴백 영역 영속) | 회귀 0 |
| 사이클 38 명문화 (scanner 매수 진입 전용) | 영역 2 | 매매 hot path 무영향 영구 확정 |
| 사이클 81 G-AST1 (bfdy_clpr / hts_avls 덮어쓰기 0) | 영역 2 (KRX 키 신규 추가만) | MEDIUM-1 PASS |
| 사이클 88 G-REJECT (graceful = 호출자 폴백) | 영역 1 (KrxApiError) + 영역 2 (Q3=C 폴백) | HIGH-2.6 + HIGH-3.b PASS |
| 사이클 89 한글 친숙 용어 | 로그 메시지 | 영속 |
| 사이클 101 영속 (24h TTL idempotency) | 영역 2 (KRX + KIS 양쪽) | 영속 |
| 사이클 106 영속 (lifecycle race 차단) | 영역 2 (호출자 영역 무관) | 영속 |
| 사이클 107/108 영속 (raw 보강 의존성) | 영역 2 (MEDIUM-1) | MEDIUM-1 PASS |
| 사이클 109 영속 (KIS market-cap 화이트리스트) | 영역 1 (KRX 별개 base URL 영구 확정) | 영속 |
| 사이클 110 영속 (silent 결함 시정 패턴) | 영역 1 (추상 결함 시정) | 영속 |
| 사이클 112 영속 (KRX 인프라 + 마스킹) | 영역 1 (추상 결함 시정 + 인프라 영속) | 사이클 112 회귀 가드 5 PASS |
| 사이클 113 영속 (CI fail 시정 패턴) | 영역 3 (회귀 가드) | 영속 |
| 사이클 114 영속 (Deploy workflow_run + 푸시 후 CI 확인) | push 결정 시 | 영속 |
| CLAUDE.md "절대 깨지 말 것" 8 영역 | 매매 hot path 무관 보장 | 전수 영속 |

## 매매 안전성 영역 영구 확정

- `src/engine/order_engine.py` 변경 0
- `src/engine/scheduler.py` 변경 0
- `src/realtime/` 영역 변경 0
- `src/auth/` 영역 변경 0
- scanner 단계 매수 진입 전 후보 풀 영역 한정 (사이클 38 명문화 영속)
- 매도/익일청산/15:20 강제청산 hot path 무관
- KIS LMS chain 영향 0 (KRX 별개 외부 API + Q3=C 폴백 영속)

## 보안 의무 영역 영구 확정

| 보안 의무 | 검증 결과 |
|-----------|----------|
| 1. API 키 평문 코드/로그/커밋/system_logs 절대 노출 금지 | SEC-1 PASS |
| 2. URL 전체 로그 금지 (AUTH_KEY query parameter 포함) | SEC-2 PASS |
| 3. endpoint_path 만 로그 (사이클 112 영속) | SEC-3 PASS |
| 4. AUTH_KEY query parameter 영역 영구 영속 | AST-4 PASS |
| 5. POST method 회귀 영구 차단 | AST-3 PASS |

## 운영 효과 (push + EC2 배포 후 예상)

### KRX 1차 성공 시 (사용자 키 활성 + 서비스 승인 완료)

- `_full_universe_load_once` source="krx" / 4 KRX 호출 + 50ms sleep × 3건 = ~200ms 소요
- stock_master.raw 에 KRX 키 추가 (MKTCAP / ACC_TRDVAL / LIST_SHRS / LIST_DD 등)
- KIS market-cap API 호출 0건 (KIS LMS chain 부담 완전 차단)
- 사이클 108 `list_by_filter(min_market_cap=, min_trade_amount=)` 데이터 영역 정합 영속

### KRX 폴백 시 (사용자 키 비활성 / 401 / 4xx / 5xx)

- `_full_universe_load_once` source="kis_fallback" / 사이클 101+109+110 영역 영구 영속
- 운영 무영향 (기존 KIS market-cap 영역 그대로 작동)
- `[krx_open_api_fallback]` WARNING 1행 가시화

## 사이클 116+ 후속 카드 인계

### 필수 (HIGH)

1. **D+1 운영 실측 의무 (2026-06-13 토 또는 다음 영업일 09:00~10:00)**
   - 사용자 KRX 키 활성화 + 4 endpoint 서비스 승인 완료 후 첫 호출 실측
   - `_full_universe_load_once` source 가시화 (KRX 성공 시 "krx" / 폴백 시 "kis_fallback")
   - stock_master.raw 영역에 KRX 키 (MKTCAP / ACC_TRDVAL / LIST_SHRS 등) 정상 포함 영구 영속 확인
   - 사이클 108 `list_by_filter` 데이터 영역 정합 (KRX `MKTCAP` 원 단위 vs KIS `hts_avls` 백만원 단위 차이) 실측 확인

### 후속 카드 (사용자 결정 의무)

2. **KRX `MKTCAP` 단위 정합 시정 영역** (HIGH 우선)
   - 사이클 108 `list_by_filter` 영역 = KIS `hts_avls` 백만원 단위 가정 (`raw.hts_avls × 1_000_000`)
   - KRX 영역 = `MKTCAP` 원 단위 직접
   - 단위 환산 로직 시정 의무 (`list_by_filter` 영역 source="krx" vs "kis_fallback" 분기 영역)

3. **KRX `SECUGRP_NM` 활용 ETF 자동 분류 영역** (MEDIUM)
   - 현재 영역 = `_universe_filter_securities_only` (KIS `prdt_type_cd` 기반)
   - KRX 영역 = `SECUGRP_NM` 활용 (보통주/우선주/ETF/리츠/SPAC 분류)
   - 사이클 116+ 별도 사이클로 영역 확장

### 인계 결함 (사이클 112+ 무관)

4. **사이클 64 contract test flaky** (사이클 112 인계 영속)
   - `tests/contract/test_cycle64_routes_price_filter.py::test_CR1_get_price_filter_response_no_mode_field`
   - 단독 PASS / 전체 회귀 fail = Supabase mock state 누수 (test isolation 영역)

5. **사이클 93 AST 가드 stale 영역** (사이클 110 인계)
   - `tests/unit/ast/test_cycle93_ast_chain_required.py::test_g_ast1_route_upsert_chain_required`
   - 시정: AST 가드를 `_full_universe_load_once` 호출 검증으로 갱신 (사이클 110 영역 정합)

## Push 결정 요청 (사용자 명시 commit 지시 의무)

- 매매 안전성 무영향 확정 (`order_engine.py` / `scheduler.py` / `realtime/` / `auth/` 변경 0)
- 회귀 가드 23 PASS (사이클 115 격리) + 전체 백엔드 2291 PASS + 회귀 0 + flakiness 0
- 사이클 112 추상 결함 3건 동시 시정 (POST → GET / JSON body → query string / header → query param)
- 사용자 KRX 키 활성화 영역 의존 (호출 시 사용자 키 활성 의존, 사이클 113 +  사이클 114 영역 영속)

사용자 명시 commit 지시 시에만 push (memory `feedback_commit_policy` 영속). 작업 완료 후 사용자에게 결과 보고 + push 결정 요청.
