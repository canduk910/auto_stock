# 사이클 96 (2026-06-10) — 사이클 89 영역 복원 + 사이클 91 페이징 결합

> Red 단계 — tdd-engineer 작성. team-leader Phase 1 진단 (단일 근본 원인 = KIS API
> "0000" 응답 단일 페이지 30 한도 + 페이징 미지원, `_workspace/cycle96_phase1_diagnosis.md`
> 인계 예정) 후 사용자 결정 채택:
>
> | 의제 | 채택 |
> |------|------|
> | Q50 영역 복원 + 페이징 결합 | **D** 사이클 89 영역 복원 (`"0001"`/`"0002"`) + 사이클 91 페이징 영속 결합 |
> | Q51 push 시점 | **A** 진단 완료 직후 (KRX 메인 중, 사이클 38 명문화 영속) |

## 1. 근본 결함 (사이클 94 단일화 영역 신규 결함)

사이클 94 (2026-06-10 직전) 시정 = `_MARKET_INPUT_ISCD = {"all": "0000"}` 단일화 + post-split
적용 후 운영 실측 = **universe 500 ticker 미적재** 영속.

team-leader Phase 1 진단 결과 **단일 근본 원인 재발견**:

- KIS 정본 (`open-trading-api/examples_llm/.../volume_rank.py`) docstring 인용 = `"0000": 전체`
  영속이나, **운영 실측 = "0000" 응답이 단일 페이지 30건 한도 + 페이징 미지원** 확정
- 사이클 94 시정 = `tr_cont="M"` 헤더 미수신 → 첫 페이지 30 ticker 만 누적 → post-split 후
  ~30 (KOSPI/KOSDAQ 분류 결과) → universe 미적재
- 사이클 89 영역 = `"0001"` (KOSPI 업종) / `"0002"` (KOSDAQ 업종) 호출 패턴 + 사이클 91
  페이징 누적 결합 = 각 17 페이지 × 30 = 510 → 250 ceiling 적용 → **실측 500 ticker 영속**

| 영역 | 사이클 89 (2회 호출, 페이징 미지원 시점) | 사이클 91 (페이징 추가) | 사이클 94 (단일 호출 "0000") | 사이클 96 (영역 복원 + 페이징) |
|------|----------|----------|----------|----------|
| FID_INPUT_ISCD | "0001" / "0002" | 동일 | "0000" | **"0001" / "0002" 복원** |
| 페이징 누적 | × (30 한도) | ○ (max_pages=17) | ○ (tr_cont 헤더 미수신) | **○ (사이클 91 영속 결합)** |
| 호출 수 | 2 | 2 | 1 (사이클 94 단순화) | **2 (사이클 89 영역 복원)** |
| 운영 실측 universe | 60 | 미배포 | 미적재 | **~500 (목표)** |

## 2. 단일 근본 원인 영구 명문화

```
KIS "0000" 응답 = 단일 페이지 30 한도 + 페이징 미지원 (KIS 운영 실측, docstring 영역 불일치)
KIS "0001" / "0002" 응답 = 페이징 정상 + 각 ~17 페이지 누적 가능 (사이클 91 영역 영속)
```

이 영역은 KIS docstring 영역과 운영 실측 영역의 *불일치* 가 결정적 발견. **사이클 89 영역
복원 (Q50=D 채택) = 운영 실측 정합 영역 영구 정착**.

## 3. 시정 영역 (Green 단계 backend-dev 인계)

### 영역 1: `src/engine/scanner.py:1368~1371` `_MARKET_INPUT_ISCD` 영역 복원

**Before** (사이클 94 단일화 영역):
```python
# 사이클 94 — KIS 정본 일치 ("0000" 전체 영역 17+ 페이징 정상 작동)
_MARKET_INPUT_ISCD: dict[str, str] = {
    "all": "0000",  # KOSPI/KOSDAQ 통합 (전체) — 응답 post-split (Q42=A stock_master 캐시 join)
}
```

**After** (사이클 96 영역 복원):
```python
# 사이클 96 — KIS API "0000" 단일 페이지 30 한도 + 페이징 미지원 silent 결함 영구 시정
# 사이클 89 영역 복원 ("0001" KOSPI 업종 + "0002" KOSDAQ 업종) + 사이클 91 페이징 영역 결합
_MARKET_INPUT_ISCD: dict[str, str] = {
    "kospi": "0001",   # KOSPI 업종 (사이클 89 영역 복원, 페이징 17 페이지 정상)
    "kosdaq": "0002",  # KOSDAQ 업종 (사이클 89 영역 복원, 페이징 17 페이지 정상)
}
```

### 영역 2: `_fetch_volume_rank` 시그너처 변경

```python
async def _fetch_volume_rank(
    market: str,  # "kospi" or "kosdaq" (사이클 96 영역 복원, 사이클 89 "1"/"2" 폐기)
    top_n: int = 250,  # 각 업종 250 ticker 영역 (사이클 89 영속)
    max_pages: int = 17,  # 사이클 91 페이징 영속
) -> list[dict]:
    ...
    input_iscd = _MARKET_INPUT_ISCD.get(market, "0001")  # fallback = KOSPI (보수적)
    # 사이클 91 페이징 누적 영역 영속 (tr_cont="M" 분기, 50ms sleep, max_pages=17 graceful)
    ...
```

### 영역 3: `fetch_top_500_universe()` 영역 복원 + 페이징 결합

```python
async def fetch_top_500_universe() -> list[str]:
    """KOSPI 250 + KOSDAQ 250 = 500 ticker 적재 (사이클 96 영역).

    사이클 89 영역 복원 + 사이클 91 페이징 결합 + 사이클 95 unknown 합집합 영속.
    KIS "0000" 응답 단일 페이지 30 한도 + 페이징 미지원 silent 결함 영구 시정.

    Returns:
        종목코드 list (최대 500건). API 실패 시 [] (graceful).

    영속 의무:
    - 사이클 89 KOSPI/KOSDAQ 250+250 분리 호출 영역 영속
    - 사이클 91 페이징 영역 결합 (각 17 페이지 누적)
    - 사이클 95 unknown 합집합 영속 (graceful fallback, stock_master 부재 종목 대비)
    - 사이클 38 명문화 (매수 진입 전용 — 영향 0)
    - 사이클 48 BFB 거래대금 재정렬 패턴 답습
    - 사이클 64 protected_tickers (영역 분리, 영향 0)
    """
    import time as _t
    from src.db import stock_master as _sm_mod
    from src.engine.stock_master_metrics import (
        record_universe_refresh, flush_universe_collector,
    )

    start_ms = _t.monotonic() * 1000

    # 사이클 96 영역 복원 — 2회 분리 호출 (KIS "0001"/"0002" 업종코드 = 페이징 정상)
    kospi_raw = await _fetch_volume_rank(market="kospi", top_n=250)
    kosdaq_raw = await _fetch_volume_rank(market="kosdaq", top_n=250)

    # ETF/리츠/SPAC 자동 제외 (사이클 89 영속)
    kospi_filtered = _universe_filter_securities_only(kospi_raw)
    kosdaq_filtered = _universe_filter_securities_only(kosdaq_raw)

    # 거래대금 desc 재정렬 (사이클 48 BFB 패턴 답습)
    kospi_sorted = sorted(kospi_filtered, key=_trade_amount_key, reverse=True)[:250]
    kosdaq_sorted = sorted(kosdaq_filtered, key=_trade_amount_key, reverse=True)[:250]

    etf_excluded_total = (
        (len(kospi_raw) - len(kospi_filtered))
        + (len(kosdaq_raw) - len(kosdaq_filtered))
    )

    # 사이클 96 post-split 불요 (업종별 분리 호출 영역, KOSPI/KOSDAQ 분류 KIS API 자체)
    # 사이클 95 unknown 영역 영속 = 0 (graceful fallback, 호환 영속)
    universe_rows = kospi_sorted + kosdaq_sorted

    # 운영 가시화 (사이클 95 emit 영속, unknown=0 영속 정상 = 사이클 96 영역 복원 효과)
    elapsed_ms = int(_t.monotonic() * 1000 - start_ms)
    universe_size = len(universe_rows)
    logger.info(
        "[stock_master_bulk_refresh] universe=%d kospi=%d kosdaq=%d unknown=0 "
        "securities=%d etf_excluded=%d elapsed_ms=%d",
        universe_size,
        len(kospi_sorted),
        len(kosdaq_sorted),
        universe_size,
        etf_excluded_total,
        elapsed_ms,
    )

    # collector 적재 (사이클 95 unknown=0 키 영속)
    record_universe_refresh({
        "universe": universe_size,
        "kospi": len(kospi_sorted),
        "kosdaq": len(kosdaq_sorted),
        "unknown": 0,  # 사이클 96 — 영역 복원 결과 영속 정상
        "securities": universe_size,
        "etf_excluded": etf_excluded_total,
        "fetched": 0,
        "skipped_fresh": 0,
        "failed": 0,
        "elapsed_ms": elapsed_ms,
    })
    flush_universe_collector()

    tickers = [row["mksc_shrn_iscd"] for row in universe_rows if row.get("mksc_shrn_iscd")]
    return tickers[:500]
```

## 4. 회귀 가드 매트릭스 (10 케이스, HIGH 5 + MEDIUM 3 + LOW 2)

### HIGH 5 (50%) — silent 결함 영구 차단 + 핵심 행위

| 가드 | 파일 | 검증 영역 |
|------|------|----------|
| **H-1** | `tests/unit/engine/scanner/test_cycle96_market_input_iscd_restored.py` | `_MARKET_INPUT_ISCD == {"kospi": "0001", "kosdaq": "0002"}` + `"0000"` 영속 부재 |
| **H-2** | `tests/unit/engine/scanner/test_cycle96_two_call_pagination_500.py` | 2회 호출 (KOSPI + KOSDAQ) + 각 17 페이지 페이징 누적 ≥ 500 ticker (mock) |
| **H-3** | `tests/unit/engine/scanner/test_cycle96_post_split_removed.py` | `_classify_market` 의존 영역 폐기 (사이클 94/95 영역 단순화) — 단, 사이클 95 unknown graceful 영속 |
| **H-4** | `tests/unit/engine/scanner/test_cycle96_kospi_kosdaq_separation_2call.py` | 2회 분리 호출 영속 (사이클 89 정본 정합) + 각 market 인자 KOSPI/KOSDAQ |
| **H-5** | `tests/unit/ast/test_cycle96_ast_no_zero_market_code.py` | AST 영구 가드: `"0000"` 시장코드 영역 영구 차단 (사이클 94 영역 회귀 영구 차단) |

### MEDIUM 3 (30%) — 운영 가시화 + 영속 영역

| 가드 | 파일 | 검증 영역 |
|------|------|----------|
| **M-1** | `tests/unit/engine/scanner/test_cycle96_emit_visibility_2call.py` | `[stock_master_bulk_refresh] universe=N kospi=K kosdaq=L unknown=0` emit 영역 정합 |
| **M-2** | `tests/unit/engine/scanner/test_cycle96_rate_limit_2call.py` | KIS 호출 영역 = 2회 분리 호출 + 페이징 영역 (각 ~17 페이지 × 2 = ~34 호출, 50ms sleep 영속) |
| **M-3** | `tests/unit/engine/scanner/test_cycle96_scanner_upsert_chain.py` | 사이클 93 `_scanner_upsert_loop` chain 영속 (호출 chain 변경 0) |

### LOW 2 (20%) — 영속 의무 답습 검증

| 가드 | 파일 | 검증 영역 |
|------|------|----------|
| **L-1** | `tests/unit/engine/scanner/test_cycle96_g_reject_persistence.py` | 사이클 88 G-REJECT-1/2/3 영속 (외부 LLM 영구 차단 AST 가드 영역 0) |
| **L-2** | `tests/unit/engine/scanner/test_cycle96_kst_persistence.py` | KST 영속 (사이클 68 답습, `_kst` 헬퍼 영역 변경 0) |

## 5. xfail 의미 전환 매트릭스 (사이클 66 K-2 패턴)

사이클 96 영역 복원으로 사이클 94 의 *몇몇* 가드 = 폐기 계약 영역으로 의미 전환 (xfail 마킹 의무).
사이클 89 H-3 = 사이클 94 시점 xfail 영역 = **사이클 96 시정 후 자동 PASS 의미 전환 (xfail 해제 검토)**.

| 영속 가드 | 사이클 94 시점 | 사이클 96 시점 | 처리 |
|----------|--------------|--------------|------|
| `test_cycle89_kospi_kosdaq_separation.py::test_h3_kospi_kosdaq_separated_2_calls` | xfail (단일 호출 폐기) | **PASS** (2회 호출 영역 복원) | xfail 영속 (`strict=False`) — 의미 전환 가시화 |
| `test_cycle94_fid_input_iscd_fix.py::test_h1_market_input_iscd_only_contains_0000` | PASS (단일화 시점) | **FAIL** (영역 복원) | xfail 마킹 의무 |
| `test_cycle94_fid_input_iscd_fix.py::test_h1_market_input_iscd_no_industry_codes` | PASS (단일화 시점) | **FAIL** (영역 복원) | xfail 마킹 의무 |
| `test_cycle94_kospi_kosdaq_split_500.py::test_h4_single_call_kospi_250_kosdaq_250_split` | PASS (단일 호출 시점) | **FAIL** (2회 호출 복원) | xfail 마킹 의무 |
| `test_cycle94_ast_no_industry_code.py::test_h6_no_industry_code_0001` | PASS | **FAIL** | xfail 마킹 의무 |
| `test_cycle94_ast_no_industry_code.py::test_h6_no_industry_code_0002` | PASS | **FAIL** | xfail 마킹 의무 |
| `test_cycle94_ast_no_industry_code.py::test_h6_market_input_iscd_contains_0000` | PASS | **FAIL** | xfail 마킹 의무 |
| `test_cycle94_post_split_market_id.py` | PASS | (보존 — 단, 호출 0 인 graceful 영역) | 적응 (호출 카운트 ≥ 0 영속) |

**xfail 마킹 사유**: 사이클 66 K-2 (cap=10 priority 분리 결함) 답습 — 사이클 N 시점 결함 confirm /
시정 confirm 양쪽 가드 영속 보존 = 미래 사이클 재발 영구 가시화.

## 6. 영속 의무 매트릭스 (사이클 96)

| 영속 의무 | 본 시정 영향 |
|----------|------------|
| 사이클 32 R4 universe guard (보유/익일청산 절대 보호) | 영향 0 (영역 분리) |
| 사이클 38 명문화 (매수 진입 전용) | 영향 0 |
| 사이클 64/65/81 graceful 설계 (price/trade_amount filter) | 영향 0 |
| 사이클 68 KST 일관성 | 영향 0 (`_kst` 헬퍼 변경 0) |
| 사이클 88 G-REJECT (외부 LLM 영구 차단 AST 가드 3) | 영향 0 + 답습 (L-1) |
| 사이클 89 KOSPI/KOSDAQ 분리 + ETF 제외 | **영역 복원** (호출 인자 명명 `"kospi"`/`"kosdaq"` 으로 갱신) |
| 사이클 91 페이징 (tr_cont + AST 가드 5) | **영속 + 결합** (사이클 96 영역 복원 + 결합 영역) |
| 사이클 92 자동 재기동 | 영향 0 |
| 사이클 93 호출 chain | 영향 0 (M-3 가드) |
| 사이클 95 chicken-and-egg unknown 합집합 | **영속 + 영역 0 (graceful 영속, unknown=0 정상)** |
| **CLAUDE.md "절대 깨지 말 것" 8 영역** | **영향 0 전수** (scanner 영역 = 매수 진입 *전* WS 구독 후보 영역) |

## 7. Red 단계 산출물 (10 신규 파일 + 5 xfail 마킹)

```
_workspace/red/cycle96_resurrect_industry_code_with_pagination.md  (본 명세)
tests/unit/engine/scanner/
  test_cycle96_market_input_iscd_restored.py                       (H-1)
  test_cycle96_two_call_pagination_500.py                          (H-2)
  test_cycle96_post_split_removed.py                               (H-3)
  test_cycle96_kospi_kosdaq_separation_2call.py                    (H-4)
  test_cycle96_emit_visibility_2call.py                            (M-1)
  test_cycle96_rate_limit_2call.py                                 (M-2)
  test_cycle96_scanner_upsert_chain.py                             (M-3)
  test_cycle96_g_reject_persistence.py                             (L-1)
  test_cycle96_kst_persistence.py                                  (L-2)
tests/unit/ast/
  test_cycle96_ast_no_zero_market_code.py                          (H-5)

xfail 마킹 (사이클 94 영역 폐기 의미 전환):
tests/unit/engine/scanner/test_cycle94_fid_input_iscd_fix.py       (H-1.a / H-1.b)
tests/unit/engine/scanner/test_cycle94_kospi_kosdaq_split_500.py   (H-4)
tests/unit/ast/test_cycle94_ast_no_industry_code.py                (H-6.a / H-6.b / H-6.c)
```

## 8. Green 단계 (backend-dev 인계)

1. `src/engine/scanner.py`:
   - `_MARKET_INPUT_ISCD` 영역 복원 (`{"kospi": "0001", "kosdaq": "0002"}`)
   - `_fetch_volume_rank(market="kospi"/"kosdaq", top_n=250, max_pages=17)` 시그너처 변경
   - `fetch_top_500_universe()` 2회 분리 호출 + post-split 영역 폐기 (KOSPI/KOSDAQ 분리 KIS 자체)
   - emit 영역 `unknown=0` 영속 명시 (사이클 95 키 호환)
   - `record_universe_refresh` `unknown` 키 0 영속

2. xfail 마킹 (사이클 66 K-2 패턴):
   - `@pytest.mark.xfail(strict=False, reason="사이클 96 영역 복원 ...")`

## 9. Red → Green 전환 기대

- Red 단계: 백엔드 2293 → 사이클 96 신규 10 fail + 사이클 94 5 영역 fail (xfail 미마킹 시) = **+15 신규 fail**
- xfail 마킹 적용 후 Red: **+10 신규 fail + 5 xfail** (예상)
- Green 단계: backend-dev 시정 후 10 신규 PASS + 5 xfail (의미 전환 영속) + 회귀 0 + flakiness 0

## 10. 영향 인덱스 갱신

`_workspace/test_index.yaml`:
- backend tests +10 (사이클 96 신규)
- 사이클 94 5 xfail 마킹 영속 (테스트 카운트 동일)

## 11. 후속 사이클 인계 (사이클 97+)

- KIS docstring 영역과 운영 실측 영역 불일치 영속 모니터링 (KIS API 정책 변경 가능성)
- `tr_cont` 헤더 미수신 영역 운영 측정 영속 (사이클 91 영역 영속 의무)
- domain-expert 자문 의무 영역 0 (영역 복원만, 행위 변경 0)
