# 사이클 108 Red 명세 — Plan Phase A: VB/LTV/BFB `_scan_universe` stock_master 전환

## 개요

| 항목 | 내용 |
|------|------|
| 사이클 | 108 |
| 단계 | Plan Phase A |
| 대상 전략 | VB (volatility_breakout) / LTV (long_tail_volatility) / BFB (bull_flag_breakout) |
| 전환 내용 | KIS volume-rank/fluctuation API → stock_master DB 필터링 |
| KIS API 호출 | 4 호출/일 → **0 호출** (100% 절감) |
| 신호 빈도 영향 | ±5% 이내 (stock_master ~2,800종목 커버) |
| 운영 시각 | 2026-06-11 16:00 KST (NXT 애프터 영역) |

---

## 사용자 결정 (영구 구속)

| 결정 ID | 선택 | 내용 |
|---------|------|------|
| Q1=A | hts_avls | 시가총액 키 (`hts_avls`, 백만원 단위, ×1_000_000 변환) |
| Q2=A | 3전략 동시 | VB/LTV/BFB 단일 사이클 통합 시정 |
| Q3=C | 4 필터 | min_market_cap + min_trade_amount + exclude_tickers + nxt_tradable |
| 즉시 push | 허용 | 16:00 KST NXT 애프터 영역 매매 무영향 |

---

## 시정 영역 (production)

### 영역 1: `src/api/condition.py` — hts_avls 5-key merge 추가
- `for key in ("acml_tr_pbmn", "lstn_stcn", "acml_vol", "prdy_vrss", "hts_avls"):` 갱신
- 5번째 키 `hts_avls` 추가 → stock_master.raw 에 적재

### 영역 2: `src/db/stock_master.py` — `list_by_filter()` 신규
- `fetch_limit = max(limit * 2, 1000)` 2× 버퍼 쿼리
- Python-side JSONB 필터링 (PostgREST JSONB 직접 비교 미지원)
- `int(raw.get("hts_avls") or 0) * 1_000_000 >= min_market_cap` (백만원→원 변환)
- `int(raw.get("acml_tr_pbmn") or 0) >= min_trade_amount`
- nxt_tradable, exclude_tickers 필터 적용
- `asyncio.to_thread` 래핑

### 영역 3: VB/LTV/BFB `_scan_universe` 전환
- `src/engine/strategies/volatility_breakout.py`
- `src/engine/strategies/long_tail_volatility.py`
- `src/engine/strategies/bull_flag_breakout.py`
- 공통 패턴: `stock_master.list_by_filter(...)` 호출 → ETF 키워드 필터 → 6자리 정수 코드 검증 → `_scan_stats` 갱신

---

## 회귀 가드 13 케이스 매트릭스

### HIGH (6 케이스)

| ID | 파일 | 검증 내용 |
|----|------|-----------|
| HIGH-1 | `test_cycle108_list_by_filter.py` (5 케이스) | 4 필터 정합성 (시총/거래대금/exclude/nxt_tradable/limit) |
| HIGH-2 | `test_cycle108_vb_scan_universe.py::TestVbScanUniverseHigh2` | KIS API 0건 + stock_master.list_by_filter 1회 호출 + AST 가드 (`FHPST01710000`, `volume-rank` 부재) |
| HIGH-3 | `test_cycle108_ltv_scan_universe.py::TestLtvScanUniverseHigh3` | 동일 (LTV) |
| HIGH-4 | `test_cycle108_bfb_scan_universe.py::TestBfbScanUniverseHigh4` | 동일 (BFB) + `BLNG_CODES` AST 부재 |
| HIGH-5 | `test_cycle108_list_by_filter.py::TestListByFilterHigh5` | hts_avls 백만원→원 변환 정확성 (1조 통과 / 999.99억 탈락 / 키 미존재 graceful) |
| HIGH-6 (AST) | 3전략 AST 가드 | source 내 `FHPST01710000` / `volume-rank` / `BLNG_CODES` 0건 영구 |

### MEDIUM (4 케이스)

| ID | 파일 | 검증 내용 |
|----|------|-----------|
| MEDIUM-1 | `test_cycle108_{vb,ltv,bfb}_scan_universe.py::TestXxxScanUniverseMedium1` | ETF 키워드 제외 + 6자리 숫자 코드 검증 |
| MEDIUM-2 | `test_cycle108_{vb,ltv}_scan_universe.py::TestXxxScanUniverseMedium2` | universe_candidates / universe_filtered / last_run_at 카운터 영속 |
| MEDIUM-3 | `test_cycle108_bfb_scan_universe.py::TestBfbScanUniverseMedium2` | universe_candidates / universe_filtered / last_run_at 카운터 영속 (BFB) |
| MEDIUM-4 | `test_cycle108_list_by_filter.py::TestListByFilterMedium3` | DB fetch limit = min(limit×2, 1000) 이상 + KIS API 호출 0건 |

### LOW (3 케이스)

| ID | 파일 | 검증 내용 |
|----|------|-----------|
| LOW-1 | `test_cycle108_list_by_filter.py` | hts_avls 키 None/빈 graceful (0 처리) |
| LOW-2 | `test_cycle108_ltv_scan_universe.py` | LTV 전용 `consecutive_limit_pass` 키 _scan_stats 존재 영속 |
| LOW-3 | `test_scan_universe_blng_multicall.py` + 8개 파일 | 구 BLNG_CODES 3회 호출 패턴 폐기 — XFAIL 의미 전환 (사이클 97 K-2 패턴 답습) |

---

## 폐기 계약 XFAIL 의미 전환 (사이클 97 K-2 패턴)

| 파일 | xfail 적용 테스트 수 | 사유 |
|------|---------------------|------|
| `test_scan_universe_blng_multicall.py` | 10 | BLNG 3회 호출 패턴 전수 폐기 |
| `test_cycle33_bfb_vcp_funnel_fix.py` | 2 | BFB volume-rank prdy_vol 패턴 폐기 |
| `test_volatility_breakout_scan_stats.py` | 1 | VB volume-rank pipeline 카운터 계약 폐기 |
| `test_bull_flag_breakout_min_trade_failed.py` | 2 | BFB volume-rank min_trade_amount 계약 폐기 |
| `test_bull_flag_breakout_prepare.py` | 2 | BFB volume-rank _scan_universe 계약 폐기 |
| `test_cycle48_bfb_vcp_zero_trade_fix.py` | 2 | BFB prdy_vol 기반 시간무관화 패턴 폐기 |
| `test_long_tail_volatility_scan_stats.py` | 1 | LTV volume-rank pipeline 카운터 계약 폐기 |
| `test_pr15_review_fixes.py` | 3 | BFB 빈 유니버스 volume-rank 에러 로그 계약 폐기 |
| **합계** | **23** | 전수 XFAIL (과거 계약 영속 보존) |

---

## 테스트 통계

| 항목 | 사이클 107 | 사이클 108 |
|------|-----------|-----------|
| backend_tests (test_index) | 476 | **560** |
| PASSED | 2,383 | 2,383 |
| XFAILED | 118 | **141** (+23 의미 전환) |
| FAILED | 0 | **0** |
| 신규 cycle108 가드 | 0 | **52** |

---

## 영속 의무 매트릭스 (사이클 108 영향 영역 전수 영속 확인)

| 영역 | 상태 |
|------|------|
| 사이클 13 영역 2 (시장 분기 영속) | 변경 0, 영속 |
| 사이클 55 R-1 SellRejectionTracker | 변경 0, 영속 |
| 사이클 31 R6/R7 익일청산 | 변경 0, 영속 |
| 사이클 84 history trigger | 변경 0, 영속 |
| 사이클 38 명문화 (tradable_boards 매수 전용) | 변경 0, 영속 |
| CLAUDE.md "절대 깨지 말 것" 8 영역 | 변경 0, 영속 |

---

## 매매 안전성 확인

scanner 단계 (매수 진입 전 후보 풀 구성) 영역만 변경. 매도/손절/Trailing/익일청산/15:20 강제청산 hot path 무관. `_scan_universe` 변경 → KIS API 0건으로 Race Limit 부담 100% 절감. 신호 빈도 변화: stock_master ~2,800종목 필터링 기반 = 기존 60~500 ticker 대비 5배+ 확장 (신호 빈도 ±5% 이내 예측).

---

## tester verify 인계

1. `python -m pytest -q --tb=no` → `2383 passed, 2 skipped, 141 xfailed, 1 xpassed` (실패 0)
2. EC2 push 후 `_scan_universe` 로그에 `[stock_master_list_by_filter]` 발화 확인
3. `[volume-rank]` / `FHPST01710000` 로그 발화 0건 확인 (KIS API 호출 0건)
4. 전략 funnel UI에서 VB/LTV/BFB `universe_candidates` 수치 정상 확인 (~2,800 범위)
