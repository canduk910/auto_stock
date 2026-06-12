# 사이클 115 Red 명세 — KRX OPEN API endpoint 실제 통합 + 사이클 112 추상 결함 시정

날짜: 2026-06-12 (금)
범위: 사이클 112 인프라 위에 실제 endpoint 호출 통합 + 사이클 112 추상 결함 3건 (POST/JSON body/AUTH_KEY header) 동시 시정
사용자 결정 (확정): Q1=양쪽 endpoint 통합 + Q3=C 폴백 (KRX 1차 + KIS 자동 폴백)
외부 검증: `seobaeksol/krx-rs` KRX_API_Spec.md (응답 schema) + `raccoonyy/pykrx-openapi` client.py (HTTP method + 인증 형식)

## 시정 영역 (5 영역, production 2 파일)

### 영역 1 — `src/api/krx.py` 추상 결함 시정 + 4 endpoint 함수 신규

**1-A. `fetch_krx_open_api` 추상 시정 (사이클 112 silent 결함 영구 차단)**:

| 항목 | 사이클 112 (결함) | 사이클 115 (정본 영속) |
|------|------------------|---------------------|
| HTTP method | `client.post(url, headers=headers, json=body)` | `client.get(url, params=merged_params)` |
| 인증 위치 | `headers = {"AUTH_KEY": config.key, ...}` | `merged_params = {"AUTH_KEY": config.key, **params}` |
| 파라미터 위치 | `json=body` | `params=merged_params` |
| Content-Type header | 명시 `application/json` | 미명시 (GET 영역) |

**1-B. 신규 함수 4종**:

```python
async def fetch_stk_bydd_trd(date: str) -> list[dict]:
    """KOSPI 일별 매매정보 (FHKST01010100 영역 KRX 대안)."""
    data = await fetch_krx_open_api("/sto/stk_bydd_trd", {"basDd": date})
    return data.get("OutBlock_1", [])

async def fetch_ksq_bydd_trd(date: str) -> list[dict]:
    """KOSDAQ 일별 매매정보."""
    data = await fetch_krx_open_api("/sto/ksq_bydd_trd", {"basDd": date})
    return data.get("OutBlock_1", [])

async def fetch_stk_isu_base_info(date: str) -> list[dict]:
    """KOSPI 종목 기본정보 (CTPF1002R 영역 KRX 대안)."""
    data = await fetch_krx_open_api("/sto/stk_isu_base_info", {"basDd": date})
    return data.get("OutBlock_1", [])

async def fetch_ksq_isu_base_info(date: str) -> list[dict]:
    """KOSDAQ 종목 기본정보."""
    data = await fetch_krx_open_api("/sto/ksq_isu_base_info", {"basDd": date})
    return data.get("OutBlock_1", [])
```

graceful: 4 endpoint 모두 `KrxApiError` 전파 → 호출자 (사이클 115 영역 2) Q3=C 폴백 의무.

### 영역 2 — `src/engine/scanner.py` `_full_universe_load_once()` Q3=C 폴백 구조

**현재 (사이클 101+109+110 영역)**:
```python
async def _full_universe_load_once() -> dict:
    # Phase 1: KIS market_cap 페이징 누적
    kospi_rows = await _fetch_market_cap_page(market="kospi", max_pages=100)
    kosdaq_rows = await _fetch_market_cap_page(market="kosdaq", max_pages=100)
    # Phase 2: CTPF1002R + stock_master upsert
    ...
```

**사이클 115 (KRX 1차 + KIS 자동 폴백)**:
```python
async def _full_universe_load_once() -> dict:
    try:
        summary = await _full_universe_load_krx_primary()
        summary["source"] = "krx"
        return summary
    except KrxApiError as exc:
        logger.warning(
            "[krx_open_api_fallback] KRX 실패 → KIS 폴백 (graceful): %s",
            exc,
        )
        summary = await _full_universe_load_kis_fallback()
        summary["source"] = "kis_fallback"
        return summary


async def _full_universe_load_krx_primary() -> dict:
    """KRX 정식 OPEN API 1차 우선 영역.

    KOSPI/KOSDAQ × bydd_trd/isu_base_info = 4 호출 + 50ms sleep
    (KIS LMS chain 안전 마진 답습).
    """
    from src.api.krx import (
        fetch_stk_bydd_trd, fetch_ksq_bydd_trd,
        fetch_stk_isu_base_info, fetch_ksq_isu_base_info,
    )
    today = today_kst().strftime("%Y%m%d")
    # 4 호출 + 50ms sleep
    kospi_trd = await fetch_stk_bydd_trd(today)
    await _asyncio.sleep(0.05)
    kosdaq_trd = await fetch_ksq_bydd_trd(today)
    await _asyncio.sleep(0.05)
    kospi_info = await fetch_stk_isu_base_info(today)
    await _asyncio.sleep(0.05)
    kosdaq_info = await fetch_ksq_isu_base_info(today)
    # 응답 merge + stock_master upsert
    ...


async def _full_universe_load_kis_fallback() -> dict:
    """기존 사이클 101+109+110 영역 영속 — 함수 본체 추출만."""
    # 기존 _full_universe_load_once 본체 영역 영구 영속
    ...
```

**stock_master upsert 영역 영구 영속**:
- `bydd_trd` → ticker(`ISU_CD`) / name(`ISU_NM`) / market(`MKT_NM`) / 6자리 ticker 정합 가드 (사이클 30 답습)
- raw JSONB merge: `MKTCAP` (원 단위) + `ACC_TRDVAL` (원 단위) + `LIST_SHRS` 추가
- `isu_base_info` → 동일 ticker (`ISU_SRT_CD`) → `LIST_DD` + `SECUGRP_NM` + `KIND_STKCERT_TP_NM` 추가 보강
- 사이클 81 G-AST1 영속: KIS `bfdy_clpr` / `hts_avls` 덮어쓰기 0 (KRX 키 신규 추가만)

### 영역 3 — 회귀 가드 매트릭스

#### HIGH (5 케이스)

**HIGH-1: `fetch_krx_open_api` GET method + query params + AUTH_KEY query (3 sub)**
- 파일: `tests/unit/api/test_cycle115_krx_get_method.py`
- 영역: 사이클 112 silent 결함 영구 차단 (POST → GET / JSON body → query params / AUTH_KEY header → AUTH_KEY query)
- mock: `httpx.AsyncClient.get` mock + `params=` 검증

**HIGH-2: 4 endpoint 함수 정상 응답 (4 sub)**
- 파일: `tests/unit/api/test_cycle115_krx_endpoints.py`
- 영역: `fetch_stk_bydd_trd` / `fetch_ksq_bydd_trd` / `fetch_stk_isu_base_info` / `fetch_ksq_isu_base_info` 정상 응답 (`OutBlock_1` 배열 반환)

**HIGH-3: Q3=C 폴백 패턴 (3 sub)**
- 파일: `tests/unit/engine/scanner/test_cycle115_full_universe_load_krx_fallback.py`
- 영역: (a) KRX 성공 시 source="krx" + KIS 호출 0건 / (b) KrxApiError 시 KIS 폴백 호출 + source="kis_fallback" / (c) KIS 도 실패 시 raise 전파 (사이클 110 graceful 영역 영구 영속)

**HIGH-4: Rate Limit 50ms sleep**
- 파일: `tests/unit/engine/scanner/test_cycle115_rate_limit.py`
- 영역: 4 KRX 호출 사이 50ms sleep × 3건 발화 정확

#### MEDIUM (2 케이스)

**MEDIUM-1: stock_master upsert 정합 (KRX raw JSONB merge, 사이클 81 G-AST1 영속)**
- 파일: `tests/unit/engine/scanner/test_cycle115_stock_master_upsert.py`
- 영역: KRX `MKTCAP` / `ACC_TRDVAL` / `LIST_SHRS` raw 추가 + KIS `bfdy_clpr` / `hts_avls` 덮어쓰기 0

**MEDIUM-2: T+1 갱신 정합 (basDd 형식)**
- 파일: `tests/unit/api/test_cycle115_krx_endpoints.py` (HIGH-2 통합)
- 영역: today_kst() → YYYYMMDD 형식 정합

#### AST 영구 가드 (2 케이스)

**AST-1: KRX endpoint URL 정적 검증**
- 파일: `tests/unit/ast/test_cycle115_krx_endpoint_urls.py`
- 영역: `src/api/krx.py` 영역에 `/sto/stk_bydd_trd` + `/sto/ksq_bydd_trd` + `/sto/stk_isu_base_info` + `/sto/ksq_isu_base_info` 4 문자열 존재 영구 영속

**AST-2: 응답 키 정적 검증 (`OutBlock_1`)**
- 파일: `tests/unit/ast/test_cycle115_krx_outblock1_key.py`
- 영역: `src/api/krx.py` 영역에 `"OutBlock_1"` 또는 `OutBlock_1` 문자열 존재 영구 영속

#### 보안 가드 (1 케이스)

**SEC-1: API 키 평문 로그 0건 (사이클 112 영속 + 사이클 17 KIS 보안 답습)**
- 파일: `tests/unit/ast/test_cycle115_krx_no_plaintext_key.py`
- 영역: `src/api/krx.py` 영역에 `config.key` 가 `logger.*` 함수 인자로 직접 전달 0건 (URL 로그도 endpoint_path 만 사용)

## 영속 의무 매트릭스 (전수 영속)

- 사이클 17 KIS 인증 보안 영속 (영역 1 + SEC-1)
- 사이클 32 R4 universe guard 영속 (영역 2)
- 사이클 38 명문화 영속 (scanner 매수 진입 전용)
- 사이클 81 G-AST1 영속 (KIS `bfdy_clpr` / `hts_avls` 덮어쓰기 0, MEDIUM-1)
- 사이클 88 G-REJECT 영속 (graceful = 호출자 폴백, 영역 1 + HIGH-3)
- 사이클 89 한글 친숙 용어 영속 (로그 메시지)
- 사이클 101 영속 (`_full_universe_load_once` 24h TTL idempotency, 영역 2)
- 사이클 106 영속 (lifecycle race 차단)
- 사이클 107/108 영속 (raw 보강 의존성, MEDIUM-1)
- 사이클 109 영속 (KIS market-cap 화이트리스트 — KRX 별개 base URL 영구 확정)
- 사이클 110 영속 (silent 결함 시정 패턴)
- 사이클 112 영속 (KRX 인프라 + 마스킹 + graceful)
- 사이클 113 영속 (CI fail 시정 패턴)
- 사이클 114 영속 (Deploy workflow_run + push 후 CI 확인 의무)
- CLAUDE.md "절대 깨지 말 것" 8 영역 영속

## 매매 안전성 무영향 확정

- scanner 단계 매수 진입 전 후보 풀 영역 한정 (사이클 38 명문화 영속)
- 매도/익일청산/15:20 강제청산 hot path 무관
- KIS LMS chain 영향 0 (KRX 별개 외부 API + Q3=C 폴백 영속)
- `src/engine/order_engine.py` / `src/engine/scheduler.py` / `src/realtime/` / `src/auth/` 변경 0
