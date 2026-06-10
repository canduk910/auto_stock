# 사이클 97 Red 명세 — KIS fluctuation API 신규 도입 + 사이클 89/91/94/96 전수 폐기

**작성일**: 2026-06-10
**상태**: Red 단계 (production 코드 변경 0)
**의제**: Q52=A KIS fluctuation 영역 신규 + Q53=A 사이클 89/91/94/96 전수 폐기 + Q54=A 즉시 push
**선행 영역**: `_workspace/cycle97_phase1_diagnosis.md` (Phase 1 진단 영속)

---

## 1. KIS MCP 정본 재검증 (인용 영속)

### 1.1 fluctuation.py 정본 (KIS open-trading-api/examples_llm/domestic_stock/fluctuation/)

**URL**: `/uapi/domestic-stock/v1/ranking/fluctuation`
**TR_ID**: `FHPST01700000`
**카테고리**: 국내주식 > 순위분석 > 등락률 순위 (v1_국내주식-088)

**필수 파라미터 영역**:
```python
fid_cond_mrkt_div_code: str   # J:KRX, NX:NXT, W:ELW, Q:ETF (검증 J/W/Q 만)
fid_cond_scr_div_code: str    # 20170 (검증 == "20170" 강제)
fid_input_iscd: str           # 0000:전체 / 0001:KOSPI / 0002:KOSDAQ / 업종코드
fid_rank_sort_cls_code: str   # 0000:등락률순
fid_input_cnt_1: str          # 입력 수1 (조회할 종목 수 — 사용자 영구 제어 영역)
fid_prc_cls_code: str         # 0:전체
fid_input_price_1: str        # 하한가 (빈 문자열 = 전체)
fid_input_price_2: str        # 상한가 (빈 문자열 = 전체)
fid_vol_cnt: str              # 최소 거래량 (빈 문자열 = 전체)
fid_trgt_cls_code: str        # 9자리 "0"/"1" 영역 (대상 구분)
fid_trgt_exls_cls_code: str   # 10자리 "0"/"1" 영역 (대상 제외 — ETF/ETN/SPAC)
fid_div_cls_code: str         # 0:전체
fid_rsfl_rate1: str           # 하락률 하한 (빈 문자열 = 전체)
fid_rsfl_rate2: str           # 상승률 상한 (빈 문자열 = 전체)
tr_cont: str = ""             # 페이징 영역 ("" → "N")
```

**페이징 패턴** (정본 인용):
```python
tr_cont = res.getHeader().tr_cont
if tr_cont == "M":  # 다음 페이지 존재
    print("Call Next")
    ka.smart_sleep()
    return fluctuation(..., "N", dataframe)
else:
    print("The End")
    return dataframe
```

### 1.2 응답 영역 (chk_fluctuation.py COLUMN_MAPPING 정본)

**결정적 영구 발견**: 응답 ticker 키 = `stck_shrn_iscd` (주식 단축 종목코드).

| 응답 키 | 의미 |
|---------|------|
| **stck_shrn_iscd** | 주식 단축 종목코드 (Phase 1 진단의 `mksc_shrn_iscd` 와 영역 차별) |
| data_rank | 데이터 순위 |
| hts_kor_isnm | HTS 한글 종목명 |
| stck_prpr | 주식 현재가 |
| prdy_vrss | 전일 대비 |
| prdy_vrss_sign | 전일 대비 부호 |
| prdy_ctrt | 전일 대비율 |
| acml_vol | 누적 거래량 |
| stck_hgpr | 주식 최고가 |
| stck_lwpr | 주식 최저가 |
| oprc_vrss_prpr | 시가 대비 |
| oprc_vrss_prpr_rate | 시가 대비 현재가 비율 |
| prd_rsfl | 기간 등락 |
| prd_rsfl_rate | 기간 등락 비율 |

**volume_rank 응답 키 (`mksc_shrn_iscd`) 와 영역 차별** — 사이클 89 영속 응답 키 가정 영구 폐기.

### 1.3 검증 영역 (정본 검증 영구 영속)

```python
if fid_cond_mrkt_div_code not in ["J", "W", "Q"]:
    raise ValueError("조건 시장 분류 코드 확인요망!!!")

if fid_cond_scr_div_code != "20170":
    raise ValueError("조건 화면 분류 코드 확인요망!!!")
```

→ `fid_cond_scr_div_code = "20170"` 강제 + `fid_cond_mrkt_div_code = "J"` 사용 (KRX 메인).

---

## 2. Phase 1 진단 영역 재정합 (응답 키 영역)

Phase 1 진단 §5.1 `tickers = [row["mksc_shrn_iscd"] for row in universe_rows ...]` 는 fluctuation 응답 영역과 **불일치**. 사이클 97 시정 = `stck_shrn_iscd` 영역 사용 의무.

→ 사이클 97 신규 헬퍼 `_fetch_fluctuation` 의 응답 ticker 추출 = `row.get("stck_shrn_iscd")` 영구.

---

## 3. 사이클 97 시정 영역 (Green 단계 backend-dev 인계)

### 3.1 `src/engine/scanner.py` 신규 영역

```python
# 사이클 97 (2026-06-10) — KIS fluctuation API (FHPST01700000) 영역 신규 도입
# 사이클 89/91/94/96 영역 전수 폐기 (KIS volume_rank 단일 페이지 30 한도 + 페이징 미지원)
# fluctuation 영역 = fid_input_cnt_1 사용자 제어 + tr_cont 페이징 영속
_FLUCTUATION_URL = "/uapi/domestic-stock/v1/ranking/fluctuation"
_FLUCTUATION_TR_ID = "FHPST01700000"

# fid_input_iscd 매핑 (KIS 정본)
# "0001" = KOSPI, "0002" = KOSDAQ
_FLUCTUATION_MARKET_INPUT_ISCD: dict[str, str] = {
    "kospi": "0001",
    "kosdaq": "0002",
}


async def _fetch_fluctuation(
    market: str,           # "kospi" or "kosdaq"
    top_n: int = 250,
    max_pages: int = 17,
) -> list[dict]:
    """KIS fluctuation API (FHPST01700000) 페이징 누적 호출 (사이클 97 영역 신규).
    
    사이클 97 (2026-06-10) — KIS volume_rank (사이클 89/91/94/96) 영역 전수 폐기 영구 시정.
    
    Args:
        market: "kospi" or "kosdaq" (사이클 96 명명 영속)
        top_n: 각 업종 최대 ticker (기본 250, 사이클 89 영속)
        max_pages: 페이지 안전 마진 (기본 17, 사이클 91 영속)
    
    Returns:
        KIS output list (dict). API 실패 시 누적분 graceful 반환. 빈 경우 [].
    
    영속 의무:
    - 사이클 89 거래대금 정렬 (_trade_amount_key) + ETF 제외 (_universe_filter_securities_only) 영속
    - 사이클 91 페이징 누적 (tr_cont "" → "N") 영속
    - 사이클 95 unknown=0 graceful 영속 (KIS API 분류 자체)
    - KIS 정본 페이징 패턴 (`open-trading-api/examples_llm/.../fluctuation.py`)
    
    응답 키 (KIS chk_fluctuation.py COLUMN_MAPPING 정본):
        stck_shrn_iscd  # 주식 단축 종목코드 (volume_rank `mksc_shrn_iscd` 와 영역 차별)
        stck_prpr / prdy_vrss / prdy_ctrt / acml_vol / ...
    """
    from src.api.base import kis_get_quote, KisApiError
    import asyncio as _asyncio
    
    input_iscd = _FLUCTUATION_MARKET_INPUT_ISCD.get(market)
    if not input_iscd:
        logger.warning(
            "[_fetch_fluctuation] unknown market: %s, fallback to kospi", market
        )
        input_iscd = _FLUCTUATION_MARKET_INPUT_ISCD["kospi"]
    
    accumulated: list[dict] = []
    tr_cont = ""
    
    for page in range(max_pages):
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20170",  # KIS 정본 강제 검증 영역
            "FID_INPUT_ISCD": input_iscd,
            "FID_RANK_SORT_CLS_CODE": "0000",   # 등락률순
            "FID_INPUT_CNT_1": str(top_n),       # 사이클 97 핵심: 사용자 영구 제어
            "FID_PRC_CLS_CODE": "0",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_TRGT_CLS_CODE": "0",
            "FID_TRGT_EXLS_CLS_CODE": "0",
            "FID_DIV_CLS_CODE": "0",
            "FID_RSFL_RATE1": "",
            "FID_RSFL_RATE2": "",
        }
        try:
            data = await kis_get_quote(
                _FLUCTUATION_URL,
                _FLUCTUATION_TR_ID,
                params=params,
                tr_cont=tr_cont,
            )
            output = data.get("output", []) or []
            accumulated.extend(output)
            
            if len(accumulated) >= top_n:
                break
            
            next_tr_cont = data.get("_response_headers", {}).get("tr_cont", "")
            if next_tr_cont != "M":
                break
            
            tr_cont = "N"
            await _asyncio.sleep(0.05)  # 사이클 83 Rate Limit 영속
        except KisApiError as e:
            logger.warning(
                "[fetch_fluctuation] KIS API 실패 market=%s page=%d error=%s (graceful 누적분 반환)",
                market, page, e,
            )
            break
        except Exception as e:
            logger.warning(
                "[fetch_fluctuation] 예외 market=%s page=%d error=%s (graceful 누적분 반환)",
                market, page, e,
            )
            break
    
    return list(accumulated[:top_n])
```

### 3.2 `fetch_top_500_universe()` 시정

`_fetch_volume_rank` → `_fetch_fluctuation` 영역 전환. 응답 ticker 키 `mksc_shrn_iscd` → `stck_shrn_iscd` 영역 전환.

### 3.3 폐기 영역 (사이클 89/91/94/96 전수)

- `_VOLUME_RANK_URL` 상수 → **삭제**
- `_VOLUME_RANK_TR_ID` 상수 → **삭제**
- `_fetch_volume_rank` 함수 → **삭제**
- `_MARKET_INPUT_ISCD` dict → **삭제** (신규 `_FLUCTUATION_MARKET_INPUT_ISCD` 로 영역 분리)
- `fetch_top_500_universe` 내부 `mksc_shrn_iscd` 응답 키 추출 → `stck_shrn_iscd`

---

## 4. 회귀 가드 10 케이스 매트릭스 (HIGH 5 + MEDIUM 3 + LOW 2)

### HIGH 5 (영구 가드 핵심)

| ID | 파일 | 검증 영역 |
|----|------|---------|
| **H-1** | `tests/unit/engine/scanner/test_cycle97_fluctuation_url_tr_id.py` | `_FLUCTUATION_URL` + `_FLUCTUATION_TR_ID` AST 상수 정합 (KIS 정본 영구 정합) |
| **H-2** | `tests/unit/engine/scanner/test_cycle97_fluctuation_pagination_500.py` | 2회 분리 호출 (KOSPI + KOSDAQ) × 페이징 누적 ≥ 500 ticker (mock) |
| **H-3** | `tests/unit/engine/scanner/test_cycle97_fid_input_cnt_1_control.py` | `FID_INPUT_CNT_1` 파라미터 사용자 제어 영역 (top_n=250 → str("250")) |
| **H-4** | `tests/unit/engine/scanner/test_cycle97_volume_rank_deprecated.py` | `_VOLUME_RANK_URL` / `_VOLUME_RANK_TR_ID` / `_fetch_volume_rank` 영역 폐기 (모듈 attribute 부재) |
| **H-5** | `tests/unit/ast/test_cycle97_ast_no_volume_rank.py` | AST 영구 가드: scanner.py source 에 `volume-rank` URL + `FHPST01710000` TR_ID 부재 (사이클 89/91/94/96 회귀 영구 차단) |

### MEDIUM 3 (운영 가시화)

| ID | 파일 | 검증 영역 |
|----|------|---------|
| **M-1** | `tests/unit/engine/scanner/test_cycle97_emit_visibility_fluctuation.py` | `[stock_master_bulk_refresh] universe=N kospi=K kosdaq=L unknown=0` emit 영속 (caplog) |
| **M-2** | `tests/unit/engine/scanner/test_cycle97_rate_limit_2call.py` | 50ms sleep 영속 + 2회 분리 호출 (KOSPI + KOSDAQ, 합 6 페이지 = 5 sleep 호출) |
| **M-3** | `tests/unit/engine/scanner/test_cycle97_scanner_upsert_chain.py` | `_scanner_upsert_loop` chain 영속 (`fetch_top_500_universe()` → `_universe_eager_refresh_loop` 호출 chain 변경 0) |

### LOW 2 (영속 가드)

| ID | 파일 | 검증 영역 |
|----|------|---------|
| **L-1** | `tests/unit/engine/scanner/test_cycle97_g_reject_persistence.py` | 사이클 88 G-REJECT 영속 (외부 LLM 영구 차단 AST 가드 3 영속) |
| **L-2** | `tests/unit/engine/scanner/test_cycle97_kst_persistence.py` | KST 영속 (`KST_TZ` import + UTC naive 0건 AST) |

---

## 5. xfail 의미 전환 매트릭스 (사이클 66 K-2 패턴 영속)

| 기존 영구 가드 파일 | 사이클 97 시점 처리 |
|-------------------|-----------------|
| `test_cycle89_kospi_kosdaq_separation.py` | **xfail 영속** (이미 사이클 94 시점 xfail 마킹) — 사이클 97 추가 reason 명시 |
| `test_cycle89_etf_exclusion.py` | **xfail 신규** (응답 키 `mksc_shrn_iscd` → `stck_shrn_iscd` 영역 전환) |
| `test_cycle89_fetch_top_500_universe.py` | **xfail 신규** (`_fetch_volume_rank` mock 영역 폐기) |
| `test_cycle91_volume_rank_pagination.py` | **xfail 신규** (`_fetch_volume_rank` 영역 폐기) |
| `test_cycle91_volume_rank_top_n_early_break.py` | **xfail 신규** |
| `test_cycle91_volume_rank_max_pages_guard.py` | **xfail 신규** |
| `test_cycle91_no_pagination_legacy.py` | **xfail 신규** |
| `test_cycle91_graceful_kis_error.py` | **xfail 신규** |
| `test_cycle91_rate_limit_sleep.py` | **xfail 신규** |
| `test_cycle91_fetch_top_500_universe_full.py` | **xfail 신규** |
| `test_cycle94_*` (이미 xfail 영속) | xfail 영속 + 사이클 97 reason 보강 |
| `test_cycle96_market_input_iscd_restored.py` | **xfail 신규** (`_MARKET_INPUT_ISCD` → `_FLUCTUATION_MARKET_INPUT_ISCD` 영역 전환) |
| `test_cycle96_kospi_kosdaq_separation_2call.py` | **xfail 신규** |
| `test_cycle96_two_call_pagination_500.py` | **xfail 신규** |
| `test_cycle96_emit_visibility_2call.py` | **xfail 신규** (사이클 97 M-1 이 영역 흡수) |
| `test_cycle96_rate_limit_2call.py` | **xfail 신규** (사이클 97 M-2 이 영역 흡수) |
| `test_cycle96_scanner_upsert_chain.py` | **xfail 신규** (사이클 97 M-3 이 영역 흡수) |
| `test_cycle96_kst_persistence.py` | **xfail 신규** (사이클 97 L-2 이 영역 흡수) |
| `test_cycle96_g_reject_persistence.py` | **xfail 신규** (사이클 97 L-1 이 영역 흡수) |
| `test_cycle96_post_split_removed.py` | **xfail 신규** |
| `tests/unit/ast/test_cycle96_ast_no_zero_market_code.py` | **xfail 신규** (`_MARKET_INPUT_ISCD` AST 영역 폐기) |

**xfail 마킹 영역 영구 영속 = 사이클 66 K-2 패턴 답습 (시정 자동 확인 + 과거 결함 confirm 보존)**.

---

## 6. 영속 의무 영역 (CLAUDE.md 영구 가드)

| 영속 의무 | 사이클 97 영향 |
|---------|------------|
| 사이클 32 R4 universe guard (보유/익일청산 절대 보호) | **영향 0** (영역 분리) |
| 사이클 38 명문화 (매수 진입 전용) | **영향 0** (영구 정합) |
| 사이클 64 protected_tickers | **영향 0** (영역 분리) |
| 사이클 65 거래대금 동행 필터 | **영향 0** (영역 분리) |
| 사이클 81 `bfdy_clpr` 가격필터 키 | **영향 0** (영역 분리) |
| 사이클 83 `_scan_pool_eager_refresh_loop` | **영향 0** (영역 분리) |
| 사이클 88 G-REJECT 외부 LLM AST | **영속** (L-1 가드) |
| 사이클 95 chicken-and-egg unknown 합집합 | **영속** (unknown=0 정상, 2회 분리 호출 효과) |
| **CLAUDE.md "절대 깨지 말 것" 8 영역** | **영향 0 전수** |

---

## 7. Red → Green 사이클 영속

- Red (사이클 97, 본 명세): production 코드 변경 0 + 10 신규 가드 FAIL + xfail 마킹 갱신 + 영향 인덱스 갱신
- Green (사이클 97 backend-dev): scanner.py 신규 영역 도입 (`_fetch_fluctuation` + `_FLUCTUATION_*` 상수) + 폐기 영역 정리 (`_fetch_volume_rank` + `_VOLUME_RANK_*` + `_MARKET_INPUT_ISCD`) → 10 가드 PASS
- 영속 영역 (사이클 98+ 인계): KRX 메인 시간 운영 측정 의무 (universe=500 정상 적재 + unknown=0 정상 + elapsed_ms 영속) + xfail 누적 cleanup 검토 (사이클 100+ 의제)
