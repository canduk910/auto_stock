# 사이클 89 Red 명세 — stock_master 500+ universe 확장

**작성일**: 2026-06-09
**작성자**: tdd-engineer
**위급도**: HIGH (작전주 차단 + 가격필터 정확도 회복 + 사이클 31/32/65/81 영속 매트릭스 영향)
**카드**: 사이클 83 후속 심화 (5분 주기 후보 풀 → 500+ universe 확장)

**선행**:
- Phase 1 진단: `_workspace/cycle89_phase1_diagnosis.md` 영속
- domain-expert 자문: `_workspace/cycle89_domain_consult.md` 영속
- 사이클 83 `_scan_pool_eager_refresh_task` (candidates=12 영역) 영속
- 사이클 84 stock_master_history trigger + 90일 retention 영속
- 사이클 88 G-REJECT-1/2/3 (4중 안전망 + ticker_last_tick + 4 dict 분리) 영속

**사용자 결정 + 도메인 자문 채택 (영속)**:

| 의제 | 채택 |
|------|------|
| Q19 universe | **B** 거래대금/거래량 상위 500 |
| Q20 적재 시점 | **D** 개장 전 1회 + 사이클 83 5분 주기 결합 |
| Q21 source | **A** KIS `volume_rank` (FHPST01710000 거래량순위) |
| Q22 retention | **A** 90일 영속 (사이클 84 영속) |
| Q23 전략별 필터링 | **A** 각 전략 `prepare()` 독립 |
| A1 500 기준 | **거래대금 (전일) 단독 정렬 1순위 + 등락률 ±15%+ 2순위 dedupe** |
| A2 시장 분리 | **KOSPI 250 + KOSDAQ 250 분리 (`mrkt_div_cls_code=1/2` 2회 호출) + ETF/리츠/우선주/SPAC 자동 제외** |

---

## 1. Green 시정 영역 (backend-dev 사이클 90 인계)

### 1-1. `src/engine/scanner.py::fetch_top_500_universe()` 신규 (~50L)

```python
async def fetch_top_500_universe() -> list[str]:
    """KOSPI 250 + KOSDAQ 250 거래대금 상위 합집합 (ETF/리츠/SPAC 자동 제외).

    사용자 결정 영속 (사이클 89):
    - Q19=B 거래대금/거래량 상위 500
    - Q21=A KIS volume_rank API (FHPST01710000)
    - A1 거래대금 (전일) 단독 정렬 + 등락률 ±15%+ dedupe (2순위)
    - A2 mrkt_div_cls_code=1 (KOSPI) + 2 (KOSDAQ) 분리 호출
    - ETF/리츠/SPAC 자동 제외 (_universe_filter_securities_only)
    """
    kospi_raw = await _fetch_volume_rank(market="1", top_n=250)
    kosdaq_raw = await _fetch_volume_rank(market="2", top_n=250)
    # 거래대금 재정렬 (trade_amount = prdy_vol × (stck_prpr - prdy_vrss), 사이클 48 BFB 답습)
    kospi = sorted(kospi_raw, key=_trade_amount_key, reverse=True)[:250]
    kosdaq = sorted(kosdaq_raw, key=_trade_amount_key, reverse=True)[:250]
    universe_raw = kospi + kosdaq
    universe = _universe_filter_securities_only(universe_raw)  # ETF/리츠/SPAC 제외
    tickers = [row["mksc_shrn_iscd"] for row in universe]
    return tickers[:500]
```

부수 헬퍼:
- `_fetch_volume_rank(market: str, top_n: int) -> list[dict]` — KIS FHPST01710000 호출
- `_trade_amount_key(row: dict) -> float` — 재정렬 key
- `_universe_filter_securities_only(rows: list[dict]) -> list[dict]` — A2 ETF/리츠/SPAC 제외

### 1-2. `src/engine/scheduler.py::_universe_eager_refresh_loop()` 신규 (~60L)

- 개장 *전* 1회 (08:30~08:50 영역, `_boot()` 직후) 적재 (사이클 51 boot_manager 답습)
- lifecycle = task 시작 + cancel + 마지막 flush (사이클 78/79 답습)
- 24h TTL 영속 (사이클 83 Q3=B)
- 50ms sleep 영속 (사이클 83 Q3=B)
- 신규 task attribute: `_universe_eager_refresh_task`
- `stop()` task_attrs 튜플 + `run_daily.finally` 양쪽 동행 추가 의무

### 1-3. `src/engine/stock_master_metrics.py` 신규 (~50L)

- `_universe_collector: list[dict]` 5분 윈도우 누적
- `record_universe_refresh(stats: dict)` (사이클 74/78 답습)
- `flush_universe_collector()` (사이클 74/78 답습)
- emit prefix 2종:
  - `[stock_master_bulk_refresh] universe=500 kospi=250 kosdaq=250 securities=480 etf_excluded=15 fetched=N elapsed_ms=M` 1행 (개장 전 1회 INFO)
  - `[stock_master_universe_summary] total=500 fresh=N stale=M held=K next_day=L` 5분 통계

### 1-4. AST 영구 가드 2

- **G-AST1 (사이클 78 답습)**: `_universe_eager_refresh_loop` 본체 또는 `_api_recovered_collector_loop` 본체에 `flush_universe_collector()` 호출 사이트 ≥1건 정적 검증
- **G-AST2 (사이클 79 답습)**: `_universe_eager_refresh_task` 가 `stop()` task_attrs + `run_daily.finally` 양쪽 동행 추가 (미래 신규 task 누락 영구 차단)

---

## 2. 회귀 가드 매트릭스 (17 케이스, HIGH 5 + MEDIUM 7 + LOW 5)

### HIGH 5 (29%)

| ID | 파일 | 의도 |
|----|------|------|
| **H-1** | `tests/unit/engine/scanner/test_cycle89_fetch_top_500_universe.py` | `fetch_top_500_universe()` 정렬 검증 (거래대금 desc + KOSPI/KOSDAQ 분리 + dedupe) |
| **H-2** | `tests/unit/engine/scanner/test_cycle89_etf_exclusion.py` | ETF/리츠/SPAC 자동 제외 (mock fixture KODEX 200 + TIGER + 리츠 + SPAC) |
| **H-3** | `tests/unit/engine/scanner/test_cycle89_kospi_kosdaq_separation.py` | `mrkt_div_cls_code=1/2` 2회 호출 분리 |
| **H-4** | `tests/unit/engine/test_cycle89_rate_limit_50ms.py` | 500 ticker 적재 시 50ms sleep + 25s elapsed (사이클 83 답습) |
| **H-5** | `tests/unit/engine/test_cycle89_candidate_pool_protection.py` | 사이클 64 protected_tickers + 사이클 65 trade_amount + 사이클 81 bfdy_clpr 영속 정합 + R6 trigger 빈도 감소 회귀 |

### MEDIUM 7 (41%)

| ID | 파일 | 의도 |
|----|------|------|
| **M-1** | `tests/unit/engine/test_cycle89_lifecycle.py` | asyncio mock lifecycle (`stop()` 시점 `_universe_eager_refresh_task` cancel + setattr None, 사이클 79 답습) |
| **M-2** | `tests/unit/engine/test_cycle89_ttl_24h.py` | 24h TTL fresh skip (사이클 83 답습, `stock_master.is_stale()` 영속) |
| **M-3** | `tests/unit/engine/test_cycle89_r4_universe_guard_persistence.py` | 사이클 32 R4 universe guard 영속 (보유/익일청산 절대 보호) |
| **M-4** | `tests/unit/engine/test_cycle89_protected_tickers_integration.py` | `_collect_protected_tickers_for_scanner` 영속 정합 (보유 ticker 가격필터 graceful 통과 영속) |
| **M-5** | `tests/unit/engine/test_cycle89_trade_amount_filter_persistence.py` | 사이클 65 trade_amount_filter 영속 (500 universe 적재 후 trade_amount 임계 정확 작동) |
| **M-6** | `tests/unit/engine/test_cycle89_bfdy_clpr_persistence.py` | 사이클 81 키 시정 영속 (`bfdy_clpr` valid 보존) |
| **M-7** | `tests/unit/engine/test_cycle89_emit_visibility.py` | `[stock_master_bulk_refresh]` + `[stock_master_universe_summary]` 1행 emit (A6 권고) |

### LOW 5 (29%)

| ID | 파일 | 의도 |
|----|------|------|
| **L-1** | `tests/unit/ast/test_cycle89_ast_flush_required.py` | G-AST1 — 사이클 78 flush 호출 사이트 영속 가드 (`flush_universe_collector` 호출 사이트 ≥1건) |
| **L-2** | `tests/unit/ast/test_cycle89_ast_task_cancel_required.py` | G-AST2 — 사이클 79 task cancel 영속 가드 (`_universe_eager_refresh_task` 가 stop task_attrs 튜플 포함) |
| **L-3** | `tests/unit/engine/test_cycle89_kst_consistency.py` | KST 영속 (사이클 68 답습, `_kst.now_kst_iso()` 사용) |
| **L-4** | `tests/unit/db/test_cycle89_history_trigger_persistence.py` | 사이클 84 history trigger 영속 (500 ticker × 1회/일 = 일 500 INSERT, 90일 retention) |
| **L-5** | `tests/unit/ast/test_cycle89_g_reject_persistence.py` | 사이클 88 G-REJECT-1/2/3 영속 가드 (사이클 89 영역 무영향 확인) |

---

## 3. Red 실행 결과 (예상)

- 백엔드 현재: 2161 PASS + 2 XFAIL + 2 skip (사이클 88 기준)
- 사이클 89 Red 작성 시: **+17 신규 fail** (production 코드 0 / 신규 함수 미존재)
- Green 단계 (사이클 90 backend-dev): 신규 모듈 + 함수 + lifecycle 통합 → 2178 PASS

## 4. 영향 인덱스 갱신

`_workspace/test_index.yaml` backend tests 370 → 387 (+17).

## 5. 매매 안전성 영향 평가

- **무영향**: scanner 단계 영역 (사이클 38 명문화 영속, 매수 진입 전용)
- 매도/익일청산/15:20 강제청산/손절/Trailing 영향 0
- 사이클 32 R4 universe guard 무영향 (M-3 가드)
- 사이클 64 protected_tickers 영속 (M-4 가드)
- 사이클 65 trade_amount_filter 영속 (M-5 가드)
- 사이클 81 silent 결함 차단 영속 (M-6 가드)
- 사이클 83 candidates=12 영역 영속 (영역 분리)
- 사이클 84 history trigger 영속 (L-4 가드, 500 ticker × 1회/일 = 5% retention 부담)
- 사이클 88 G-REJECT-1/2/3 영속 (L-5 가드, 영향 0 영구 확인)

## 6. 영속 의무 (각 케이스 docstring 명시)

- **사이클 17 KIS LMS chain 영속**: eager refresh 가 unsubscribe 발화 0건 (DB upsert 영역만)
- **사이클 32 R4 universe guard 영속**: 보유/익일청산 절대 보호 (positives only)
- **사이클 38 명문화 영속**: `tradable_boards` 매수 진입 전용 영역 한정
- **사이클 64 protected_tickers 영속**: 보유 ticker 가격필터 graceful 통과
- **사이클 65 trade_amount_filter 영속**: 거래대금 임계 정확 작동
- **사이클 67 stale_manager 분해 영속**: 영역 분리 (영향 0)
- **사이클 68 KST 영속**: `_kst.now_kst_iso()` 헬퍼 사용
- **사이클 78 flush 호출 사이트 영속**: G-AST1 패턴 답습
- **사이클 79 task cancel 영속**: G-AST2 패턴 답습
- **사이클 81 bfdy_clpr 키 시정 영속**: `_apply_price_filter` 정상 발화
- **사이클 83 scan_pool eager refresh 영속**: candidates=12 영역 영속 (영역 분리)
- **사이클 84 history trigger 영속**: 90일 retention + 500 universe = 45,000 row (5% 안전)
- **사이클 88 G-REJECT-1/2/3 영속**: 영향 0 영구 확인 (영역 분리)

## 7. 후속 사이클 인계

- **사이클 90** (Green): backend-dev 가 신규 모듈/함수 도입 + lifecycle 통합 + AST 가드 PASS 의무
- **사이클 91+** (Q23 공용 헬퍼 옵션 B 검토, 3회 반복 후 추상화 규칙)
- **사이클 92+** (운영 1주 측정 + R6 trigger 빈도 회복 검증)
- **사이클 95+** (KOSPI/KOSDAQ 비율 동적 분할 정밀화, A2 권고 영속)

## 8. 운영 효과 예상 (사이클 90 Green push 후)

- stock_master 적재 52건 → 500+ 건 (개장 전 1회 적재 + 24h TTL 영속)
- `_apply_price_filter` 통과율 97% → 30~50% (정상 가격필터 발화)
- `[price_filter_scanner_skip]` 일일 0건 → 10~50건 (작전주/초고가 자동 차단, 사이클 64/81 의도 회복)
- `[risk_silent_skip]` SK스퀘어 폭주 270건/일 → 0~10건 (R6 우회 시나리오 자연 차단)
- `[stock_master_bulk_refresh]` 개장 전 1회 emit (universe=500 + securities=~480 + etf_excluded=~15)
- `[stock_master_universe_summary]` 5분 주기 emit (~144건/day)
- 일일 KIS 호출 추가 부담 = ~502건 (volume_rank 2 + CTPF1002R 500, 24h TTL 영속 = 2 사이클째부터 0건)
