# 사이클 81 — SK스퀘어 가격필터 미작동 silent 결함 시정 (Red)

**날짜**: 2026-06-08
**위험 등급**: HIGH (silent 결함 영구 차단 + 거래대금 폴백 동일 결함 동시 시정)
**선행 자문**: domain-expert (사이클 64 Q2 가정 오류 confirm)
**채택**: C-1 + C-3 동시 시정 (옵션 A 패턴 20 사이클 연속)

## 결함 배경

### C-1 (HIGH) — 사이클 64 키 오타
- `src/engine/scanner.py:166` `_apply_price_filter`
- 현재: `basics.raw.get("prdy_clpr", 0)` ← **CTPF1002R 미존재 키**
- 정본: `basics.raw.get("bfdy_clpr", 0)` ← **Before day close price**
- 결과: prdy_clpr 영구 0 → graceful 통과 분기 진입 → **above_max 차단 영구 무력화**
- 운영 실측: `[price_filter_scanner_skip]` 0건/30일+ (SK스퀘어 1,122,000원 통과 결함)

### C-3 (MEDIUM) — 거래대금 필터 2순위 폴백 동일 결함
- `src/engine/scanner.py:336` `_get_acml_tr_pbmn`
- 2순위 폴백 `stock_master.raw.get("acml_tr_pbmn", 0)` ← **CTPF1002R 미존재 키**
- 1순위 (scanner ticker_market_info["trade_amount_raw"]) 는 정상 작동 중
- 시정: 2순위 폴백 폐기 → 1순위 단독 + miss=graceful 통과 (Q6-1 영속)

## 명세 (선행)

### A. 키 정정 검증 (HIGH, 3 케이스)
- A-1: `_apply_price_filter` 가 `basics.raw["bfdy_clpr"]` 키 조회
- A-2: `prdy_clpr` 키 무시 (mock raw={"prdy_clpr": 999, "bfdy_clpr": 1200000} → 1,200,000 평가)
- A-3: AST 정적 가드 — scanner.py `_apply_price_filter` 영역 `"prdy_clpr"` 문자열 0건

### B. above_max 차단 회귀 (HIGH, 3 케이스, SK스퀘어 시나리오)
- B-1: bfdy_clpr=1,122,000, max=500,000 → above_max 제외 (SK스퀘어 시나리오)
- B-2: bfdy_clpr=400,000, max=500,000 → 통과
- B-3: bfdy_clpr=2,000, min=3,000 → below_min 제외

### C. graceful 통과 영속 (Q1 옵션 A' 핵심, 2 케이스)
- C-1: bfdy_clpr 키 부재 → survivor 통과 (회귀 미파괴)
- C-2: bfdy_clpr=0 → survivor 통과

### D. 보유/익일청산 보호 영속 (사이클 64 Q1 옵션 D, 1 케이스)
- D-1: 보유 ticker 가 above_max 라도 early-return 통과

### E. funnel step_no=98 + DailyEmitCap 영속 (2 케이스)
- E-1: above_max 1회 ticker 만 `[price_filter_scanner_skip]` 1행
- E-2: 같은 ticker 두 번째 호출 시 emit 안 함 (DailyEmitCap)

### F. 거래대금 필터 동시 시정 C-3 (3 케이스)
- F-1: `_get_acml_tr_pbmn` 2순위 폴백 `acml_tr_pbmn` 폐기 검증 — scanner 1순위 단독
- F-2: AST 정적 가드 — `_get_acml_tr_pbmn` 2순위 `acml_tr_pbmn` 분기 제거
- F-3: scanner.ticker_market_info 1순위 단독 + miss=graceful 통과

### G. 운영 실데이터 회귀 (1 케이스)
- G-1: 005930 raw 67 키 fixture → `bfdy_clpr` 추출 PASS + `prdy_clpr` 미존재 검증

## Red 검증 의무

| 케이스 | 현재 (Green 전) 결과 | 비고 |
|-------|------|------|
| A-1, A-2 | FAIL | `prdy_clpr` 잔존 |
| A-3 | FAIL | AST `"prdy_clpr"` 잔존 |
| B-1 | FAIL | prdy_clpr=0 → graceful 통과 = above_max 미차단 (SK스퀘어 결함 직접 재현) |
| B-2, B-3 | 부분 PASS / FAIL | graceful 통과 분기 진입 |
| C-1, C-2 | PASS | 미확보 graceful 통과 영속 |
| D-1 | PASS | early-return 영속 |
| E-1, E-2 | FAIL | emit 0건 |
| F-1, F-2 | FAIL | 2순위 폴백 존재 |
| F-3 | PASS | 1순위 우선 |
| G-1 | PASS | raw fixture 영속 |

**flakiness 3 회 반복** = 모두 동일 결과.

## 산출물

- `tests/unit/engine/scanner/test_cycle81_price_filter_key_fix.py` (A 3 + B 3 + C 2 + D 1 + E 2 = 11 케이스)
- `tests/unit/engine/scanner/test_cycle81_trade_amount_filter_fallback_removal.py` (F 3 케이스)
- `tests/unit/ast/test_cycle81_ast_price_filter_key.py` (A-3 + F-2 AST 정적 가드)
- `tests/unit/engine/scanner/test_cycle81_real_data_regression.py` (G-1, 005930 fixture)

총 ~15 케이스 (4 파일).

## Green 의무 (backend-dev 후속)

1. `src/engine/scanner.py:166` — `"prdy_clpr"` → `"bfdy_clpr"` (1 줄)
2. `src/engine/scanner.py:330-345` — 2순위 폴백 분기 전체 폐기 (`stock_master` 분기 제거, 1순위 + miss=0 단독)

## 안전 규칙 영속 (CLAUDE.md)

- 사이클 31 R6 (`current_price > total_investment` 가시화) 무관
- 사이클 32 R4 (universe guard 보유/익일청산 보호) 영속 (D-1)
- 사이클 38 명문화 (매수 진입 전용) 영속
- 사이클 64 Q1 옵션 D 3중 안전망 (보유/익일청산 절대 보호) 영속 (D-1)
- 매도 안전성 영향 0 (scanner 단계 = 매수 진입 전용)
