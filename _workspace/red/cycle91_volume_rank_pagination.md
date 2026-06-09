# 사이클 91 (2026-06-09) — KIS volume_rank 페이징 누적 누락 silent 결함 시정

> Red 단계 — tdd-engineer 작성. 사용자 결정 **A 즉시 발주** 후 backend-dev 직접 발주 +
> tdd-engineer Red 선행 (영구 차단 가드 의무).

## 근본 결함 (사이클 89 silent)

사이클 89 (2026-06-09) 도입한 `src/engine/scanner.py::_fetch_volume_rank` 가 KIS
`volume_rank` (FHPST01710000) API 의 **페이징 응답 의무**를 누락. 단일 호출만 +
`output[:top_n]` slicing → 운영 실측 **첫 페이지 30 + 30 = 60 ticker** 적재
(사용자 보고 — KOSPI 30 + KOSDAQ 30 = 정확 일치).

기대 영역 = KOSPI 250 + KOSDAQ 250 = 500 ticker (사이클 89 명세).

## KIS 정본 페이징 패턴 (MCP 인용 — `search_domestic_stock_api` 2026-06-09)

KIS 공식 저장소 `examples_llm/domestic_stock/volume_rank/volume_rank.py` 인용 (정본):

```python
res = ka._url_fetch(API_URL, tr_id, tr_cont, params)

if res.isOK():
    # ... DataFrame 누적
    tr_cont = res.getHeader().tr_cont

    if tr_cont == "M":  # 다음 페이지 존재
        print("Call Next")
        ka.smart_sleep()  # 시스템 안정적 운영을 위한 지연
        return volume_rank(
            ...,  # 동일 파라미터
            "N",  # 연속 호출 표식
            dataframe  # 누적 데이터프레임 전달
        )
    else:
        print("The End")
        return dataframe
```

요약:
- **응답 헤더 `tr_cont == "M"` → 다음 페이지 존재** (Multi)
- **재호출 입력 `tr_cont = "N"` → 다음 페이지 누적** (Next)
- 종료 조건: `tr_cont == ""` / `"D"` (Done) / `"E"` (End) 또는 응답 미존재
- 첫 페이지 응답 한도 = **~30건** (KIS 표준, 운영 실측 일치)
- 페이지 간 `smart_sleep()` (Rate Limit 보호) 의무

## 운영 실측 (사용자 보고 + READ-ONLY 확정)

| 영역 | 기대 | 실측 | 결함 인과 |
|------|------|------|----------|
| `_fetch_volume_rank(market="1", top_n=250)` | KOSPI 250 | **30** | 페이징 누락 |
| `_fetch_volume_rank(market="2", top_n=250)` | KOSDAQ 250 | **30** | 페이징 누락 |
| `fetch_top_500_universe()` | 500 | **60** | KOSPI 30 + KOSDAQ 30 |

## 시정 영역 (Green 단계 backend-dev 인계)

### 영역 1 — `src/engine/scanner.py::_fetch_volume_rank` 페이징 누적

```python
async def _fetch_volume_rank(
    market: str,
    top_n: int = 250,
    max_pages: int = 15,  # 사이클 91 신규 — 무한 루프 차단 (KIS 표준 한도 + 안전 마진)
) -> list[dict]:
    """KIS volume_rank 페이징 누적 호출.

    사이클 91 (2026-06-09) silent 결함 시정:
    - tr_cont == "M" → 다음 페이지 호출 (KIS Multi)
    - tr_cont == "" or "D" or "E" → 종료
    - max_pages=15 무한 루프 차단 (KIS 표준 한도 영역 + 안전 마진)
    - 페이지 간 50ms sleep (Rate Limit 보호 + 사이클 83 답습)

    사이클 89 silent 결함: 단일 호출 + slicing → 60 ticker 적재 (KOSPI 30 + KOSDAQ 30).
    KIS 정본 = 페이징 누적 의무.
    """
    from src.api.base import kis_get_quote, KisApiError
    import asyncio as _asyncio

    input_iscd = _MARKET_INPUT_ISCD.get(market, "0001")
    accumulated: list[dict] = []
    tr_cont = ""  # 초기 호출 (KIS 표준 — 빈 문자열 = 첫 페이지)

    for page in range(max_pages):
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": input_iscd,
            "FID_DIV_CLS_CODE": "1",       # 보통주만
            "FID_BLNG_CLS_CODE": "3",       # 거래금액순
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "0000001101",
            "FID_INPUT_PRICE_1": "0",
            "FID_INPUT_PRICE_2": "0",
            "FID_VOL_CNT": "0",
            "FID_INPUT_DATE_1": "",
        }
        try:
            data = await kis_get_quote(
                _VOLUME_RANK_URL,
                _VOLUME_RANK_TR_ID,
                params,
                tr_cont=tr_cont,  # 사이클 91 신규 — base.py 영역 시정 의무
            )
            output = data.get("output", []) or []
            accumulated.extend(output)

            # 누적 영역이 top_n 초과 시 조기 종료 (효율)
            if len(accumulated) >= top_n:
                break

            # 응답 헤더 tr_cont 추출 (다음 페이지 존재 여부)
            next_tr_cont = data.get("_response_headers", {}).get("tr_cont", "")
            if next_tr_cont != "M":
                break  # 마지막 페이지 (D / E / "" 또는 헤더 미존재)

            tr_cont = "N"  # 다음 페이지 호출 (KIS 표준 — "N" = Next)
            await _asyncio.sleep(0.05)  # Rate Limit 보호 (사이클 83 답습)
        except KisApiError as e:
            logger.warning(
                "[fetch_volume_rank] KIS API 실패 market=%s page=%d error=%s (graceful 누적분 반환)",
                market, page, e,
            )
            break
        except Exception as e:
            logger.warning(
                "[fetch_volume_rank] 예외 market=%s page=%d error=%s (graceful 누적분 반환)",
                market, page, e,
            )
            break

    return list(accumulated[:top_n])
```

### 영역 2 — `src/api/base.py::kis_get_quote` 시그너처 검증 의무

현재 `kis_get_quote` 시그너처 (`src/api/base.py:610-624`):

```python
async def kis_get_quote(
    path: str,
    tr_id: str,
    params: dict | None = None,
    *,
    hashkey: str = "",
) -> dict:
```

**Green 단계 시정 의무 (backend-dev 직접 발주 영역)**:
1. `tr_cont: str = ""` 키워드 인자 추가 (기존 호출자 호환 — 디폴트 `""`)
2. `_request_via_quote_pool` 도 동일 인자 추가 + `manager.build_headers(tr_id, tr_cont=tr_cont, hashkey=hashkey)` 전달
3. 응답 본문에 `_response_headers` 키 주입 (응답 헤더 `tr_cont` 추출 영역)
   - 위치: `_request_via_quote_pool` 의 `data = resp.json()` 직후
   - 패턴: `data["_response_headers"] = {"tr_cont": resp.headers.get("tr_cont", "")}`
   - 이름 충돌 방지: 키 이름 `_response_headers` (언더스코어 prefix, KIS 응답 영역 분리)

**대안 영역 (backend-dev 결정 위임)**:
- `data` 에 헤더 주입 대신 별도 반환 튜플 `(data, headers)` 도 가능하나 기존 호출자 (5 함수) 모두 영향 → **dict 키 주입 채택** (영향 0)

### 영역 3 — `src/auth/token_manager.py::build_headers` 검증

`tr_cont` 헤더 영역이 KIS 표준이므로 `build_headers` 가 이미 영역 영속이어야 함.
부재 시 Green 단계 시정 의무.

## 회귀 가드 매트릭스 (8 케이스)

### HIGH 4

**H-1 — `tests/unit/engine/scanner/test_cycle91_volume_rank_pagination.py`**
페이징 누적 검증. mock 3 페이지 (각 30건 = 90 누적) + top_n=250 미만 시 max_pages
도달 종료. KIS 정본 패턴 일치 (tr_cont 입력 `""` → `"N"` → `"N"`).

**H-2 — `tests/unit/engine/scanner/test_cycle91_volume_rank_top_n_early_break.py`**
top_n=250 초과 시 조기 종료 (효율 가드). mock 응답 5 페이지 × 100건 = 500 가용,
top_n=250 면 3 페이지째 250 누적 후 break (4/5 페이지 미호출).

**H-3 — `tests/unit/engine/scanner/test_cycle91_volume_rank_max_pages_guard.py`**
max_pages=15 무한 루프 차단. KIS 헤더 항상 `"M"` 시나리오 (mock 무한 페이징) →
15 회 호출 후 중단 (KIS LMS chain 차단 영구 가드).

**H-4 — `tests/unit/engine/scanner/test_cycle91_fetch_top_500_universe_full.py`**
`fetch_top_500_universe()` 통합 시나리오. KOSPI 페이징 9 페이지 × 30 = 270 →
top_n=250 cap + KOSDAQ 동일 → ETF 제외 통과 + 합집합 500 ticker 완전 달성.
사이클 89 운영 실측 60 ticker 결함 영구 차단.

### MEDIUM 3

**M-1 — `tests/unit/engine/scanner/test_cycle91_rate_limit_sleep.py`**
페이지 간 50ms sleep 보장 (KIS Rate Limit 보호). `asyncio.sleep` mock 호출
횟수 = (페이지 수 - 1) 검증 (마지막 페이지 후 sleep 없음).

**M-2 — `tests/unit/engine/scanner/test_cycle91_graceful_kis_error.py`**
중간 페이지 KIS 실패 시 graceful 누적분 반환. mock 페이지 1/2 성공 + 페이지 3
`KisApiError` raise → break + 누적 60건 반환 (페이지 1+2 데이터 보존).

**M-3 — `tests/unit/engine/scanner/test_cycle91_no_pagination_legacy.py`**
`tr_cont` 헤더 없는 mock 응답 = 단일 호출 + graceful 종료 (legacy 환경 호환).
mock 응답에 `_response_headers` 키 부재 → 첫 호출 결과만 반환.

### LOW 1

**L-1 — `tests/unit/ast/test_cycle91_ast_pagination_pattern.py`**
`_fetch_volume_rank` 본체 정적 AST 가드:
- `tr_cont` 키워드 ≥ 2 회 사용 (입력 + 추출)
- `max_pages` 변수 사용 (무한 루프 차단)
- `for page in range(` 패턴 사용 (페이지 루프)
- `asyncio.sleep` 호출 (Rate Limit)
- silent 결함 영구 차단 (사이클 89 단일 호출 패턴 재발 영구 차단).

## 영속 의무 (사이클 88 G-REJECT + 사이클 89 영역)

- **사이클 89 영역 영속**:
  - KOSPI/KOSDAQ 분리 호출 (`_MARKET_INPUT_ISCD={"1": "0001", "2": "0002"}`)
  - ETF 제외 (`_universe_filter_securities_only`, prdt_type_cd "300" 만 통과)
  - 거래대금 정렬 (`_trade_amount_key = prdy_vol × (stck_prpr - prdy_vrss)`)
  - 50ms sleep (사이클 83 답습)
- **사이클 88 G-REJECT 영속**: KIS 거부 응답 영구 저장 매트릭스 무영향 (rt_cd != "0" 분기 영속)
- **사이클 81 bfdy_clpr 영속**: scanner 영역 분리 영향 0
- **사이클 65 trade_amount_filter 영속**: scanner DB upsert 영역 분리
- **사이클 38 명문화 영속**: `tradable_boards` 매수 진입 전용 (매도 hot path 영향 0)
- **매매 안전성 영향 0**: scanner 단계 = 매수 진입 *전* 종목 풀 차단 (사이클 64 영속)

## 운영 효과 예상 (Green push 후)

- `fetch_top_500_universe()` 60 → **500** ticker (사용자 의도 100% 달성)
- KOSPI 단독 30 → **250** (사이클 89 명세 정확 달성)
- KOSDAQ 단독 30 → **250** (사이클 89 명세 정확 달성)
- 후보 풀 폭축 결함 영구 차단 (silent 결함 사이클 91 영구 가드)

## Green 단계 검증 의무 (backend-dev 인계)

1. `src/api/base.py::kis_get_quote` + `_request_via_quote_pool` 에 `tr_cont` 키워드 인자 추가
2. 응답 본문에 `_response_headers["tr_cont"]` 키 주입 (영역 부재 시)
3. `src/auth/token_manager.py::build_headers` 의 `tr_cont` 헤더 영역 검증
4. `src/engine/scanner.py::_fetch_volume_rank` 페이징 누적 로직 추가
5. 본 Red 8 케이스 PASS 확인
6. 기존 cycle89 테스트 (H-1 fetch_top_500_universe / kospi_kosdaq_separation / etf_exclusion) 회귀 0
7. 영향 인덱스 `_workspace/test_index.yaml` 갱신 (backend tests 394 → 402)
