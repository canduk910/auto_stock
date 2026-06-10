# 사이클 98 — KIS fluctuation `FID_RANK_SORT_CLS_CODE` 1줄 silent 결함 영구 시정 (Red)

**날짜**: 2026-06-10
**위험 등급**: HIGH (silent 결함 영구 차단 + KIS API 정본 영역 100% 인용 의무)
**선행 진단**: `_workspace/cycle98_phase1_diagnosis.md` (Supabase MCP 운영 실증 + KIS MCP 정본 매트릭스)
**선행 자문**: domain-expert 자문 생략 (단일 근본 원인 1줄 시정 + KIS MCP 정본 100% 인용 영역)
**채택**: Q55=A 1줄 시정 + AST 영구 가드 / Q56=A KIS MCP 정본 재검증 / Q57=A 진단 직후 push (NXT 애프터 시간 영속)

## 결함 배경 (운영 실증 + KIS MCP 정본 매트릭스)

### 운영 실증 (Supabase MCP READ-ONLY, 2026-06-10 16:36 KST 사이클 97 push 직후)

```
2026-06-10 16:36:49 KST  ERROR  [kis_rejection_quote] path=/uapi/domestic-stock/v1/ranking/fluctuation
                                tr_id=FHPST01700000 label=gold msg_cd=OPSQ2002
                                msg1=ERROR INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]
2026-06-10 16:36:49 KST  ERROR  [kis_rejection_quote] ... label=sub msg_cd=OPSQ2002
                                msg1=ERROR INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]
2026-06-10 16:36:50 KST  WARNING [fetch_fluctuation] KIS API 실패 market=kospi page=0
                                error=OPSQ2002 ... [FID_RANK_SORT_CLS_CODE] [4]
2026-06-10 16:36:50 KST  WARNING [fetch_fluctuation] KIS API 실패 market=kosdaq page=0
                                error=OPSQ2002 ... [FID_RANK_SORT_CLS_CODE] [4]
2026-06-10 16:36:50 KST  INFO    [stock_master_bulk_refresh] universe=0 kospi=0 kosdaq=0
                                unknown=0 securities=0 etf_excluded=0 elapsed_ms=233
```

**16:39:15 / 16:39:21 동일 패턴 반복** (KOSPI + KOSDAQ 양쪽 모두 page=0 첫 호출 즉시 거부 → 누적분 0건 graceful 반환).

### KIS API 거부 정확 의미

`OPSQ2002: ERROR INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]`
- 파라미터 영역 = `FID_RANK_SORT_CLS_CODE`
- value 길이 영역 4 (`"0000"`) **미허용** → KIS 거부

### KIS MCP 정본 매트릭스 (chk_fluctuation.py main 호출 영역 100% 인용)

KIS MCP 정본 인용 (`mcp__kis-code-assistant__read_source_code` 정본):

```python
# KIS 정본 = examples_llm/domestic_stock/fluctuation/chk_fluctuation.py::main()
result = fluctuation(
    fid_cond_mrkt_div_code="J",
    fid_cond_scr_div_code="20170",
    fid_input_iscd="0000",
    fid_rank_sort_cls_code="0",      # ← 1자리 ✓ (KIS 정본)
    fid_input_cnt_1="0",
    ...
)
```

vs

```python
# KIS fluctuation.py docstring 영역 (거짓 안내)
fid_rank_sort_cls_code (str): 순위 정렬 구분 코드 (0000: 등락률순)  # ← 4자리 ✗
```

| 파라미터 | KIS 정본 (chk main 호출) | 사이클 97 (scanner.py L1529) | 정합 |
|---------|--------------------------|------------------------------|------|
| FID_COND_MRKT_DIV_CODE | `"J"` | `"J"` | OK |
| FID_COND_SCR_DIV_CODE | `"20170"` | `"20170"` | OK |
| FID_INPUT_ISCD | `"0000"` | `"0001"`/`"0002"` | OK (영역 적응) |
| **FID_RANK_SORT_CLS_CODE** | **`"0"`** (1자리) | **`"0000"`** (4자리) | **NG ✗ 결함** |
| FID_INPUT_CNT_1 | `"0"` | `str(top_n)` | OK (사용자 제어) |
| 기타 11개 | 동일 | 동일 | OK |

**유일 결함 = `FID_RANK_SORT_CLS_CODE` 1줄** (사이클 97 영역 backend-dev Green 단계 docstring 영역 인용 silent 결함).

### Root Cause 영역 분석 (사이클 65 H1 답습)

사이클 97 backend-dev Green 단계 silent 결함:
1. KIS fluctuation.py docstring `(0000: 등락률순)` 거짓 안내 영역 인용 (1차 영역 거짓)
2. KIS chk_fluctuation.py main 호출 영역 `fid_rank_sort_cls_code="0"` 1자리 실측 영역 미인용

사이클 97 회귀 가드 영역 한계:
- 회귀 가드 = `params["FID_RANK_SORT_CLS_CODE"] == "0000"` 영역 영구 검증 (결함 영역 동일 검증)
- KIS 실제 응답 통합 테스트 0건 (mock 영속)
- → TDD 영역 PASS / 운영 영역 즉시 KIS 거부 silent 차단

### 영향 영역

- **universe = 0 ticker 영구 영역** (KOSPI + KOSDAQ 양쪽 page=0 첫 호출 즉시 거부 → 누적분 0건 graceful 반환)
- **stock_master 적재 0건** (사이클 89/91/94/96 60 ticker 영속 영역 *도* 미달, 사이클 97 = 완전 영구 영역 차단)
- **매매 hot path 영향 0** (사이클 38 명문화 영속, scanner 단계 매수 진입 전용 + 사이클 64 protected_tickers + 사이클 81 영속)
- **운영 영향 (HIGH 긴급)**: 다음 영업일 (2026-06-11 목요일) 09:00 *전* 영구 시정 의무 (07:50 `TIME_BOOT` 영역 `fetch_top_500_universe()` 호출 → universe=0 영구 → momentum/breakout 후보 풀 영구 0건 → 매매 영구 차단)

## 시정 영역 (Green 단계 backend-dev 인계, production 1줄 시정)

### `src/engine/scanner.py:1529` 1줄 시정 (Green 의무)

```python
# Before (사이클 97 영역, KIS docstring 거짓 안내 영역 인용 결함)
"FID_RANK_SORT_CLS_CODE": "0000",   # 등락률순

# After (사이클 98 영역, KIS chk_fluctuation.py main 호출 영역 정본 영속)
"FID_RANK_SORT_CLS_CODE": "0",   # 등락률순 (KIS chk_fluctuation.py main 영역 정본 1자리)
```

### `src/engine/scanner.py:1497` docstring 시정 (Green 의무, G-DOC1 가드 통과 의무)

```python
# Before
FID_RANK_SORT_CLS_CODE = "0000"  (등락률순)

# After
FID_RANK_SORT_CLS_CODE = "0"     (등락률순, KIS chk_fluctuation.py main 호출 영역 정본 영속)
                                  (KIS fluctuation.py docstring 영역 "0000" 거짓 안내 영역 무시)
```

## 회귀 가드 5 케이스 (HIGH 3 + MEDIUM 1 + LOW 1, 4 파일)

### HIGH 3

**G-FIX1** — `tests/unit/engine/scanner/test_cycle98_rank_sort_cls_code_fix.py`
- `_fetch_fluctuation` 호출 시 KIS 요청 params 영역 `FID_RANK_SORT_CLS_CODE == "0"` (1자리, KIS 정본 정합)
- Red 상태: 사이클 97 영역 `"0000"` 영속 → FAIL
- Green: `"0000"` → `"0"` 1줄 시정 → PASS
- KIS 정본 인용: chk_fluctuation.py main 호출 영역 `fid_rank_sort_cls_code="0"`

**G-AST1** — `tests/unit/ast/test_cycle98_ast_rank_sort_cls_code.py`
- AST 영구 가드 (사이클 81 `bfdy_clpr` / 사이클 97 H-5 답습 패턴)
- scanner.py source 영역 `"FID_RANK_SORT_CLS_CODE": "0"` (1자리) ≥1건 영속
- scanner.py source 영역 `"FID_RANK_SORT_CLS_CODE": "0000"` (4자리) 또는 다른 다자리 영역 영구 차단
- Red 상태: production `"0000"` 영속 → FAIL
- Green: `"0000"` → `"0"` 시정 → PASS

**G-DOC1** — `tests/unit/ast/test_cycle98_ast_chk_citation_required.py` (**미래 silent 결함 영구 차단 패턴 신설**)
- KIS 정본 영역 인용 의무 (`_fetch_fluctuation` docstring 영역)
- `# KIS chk_fluctuation.py` 또는 `chk_fluctuation.py main` 영역 인용 주석 영역 ≥1건 영속
- 미래 backend-dev 가 docstring 거짓 안내 영역 인용 영구 차단 패턴
- Red 상태: docstring `"0000"` 영역 + chk 인용 부재 → FAIL
- Green: docstring `"0"` + chk 인용 추가 → PASS

### MEDIUM 1

**G-INT1** — `tests/integration/test_cycle98_fluctuation_kis_api.py`
- `_fetch_fluctuation` mock 통합 시나리오
- 정상 응답 영역 정합 (output ≥1건 + rt_cd "0")
- OPSQ2002 거부 시나리오 영역 graceful 영속 (KisApiError → 누적분 반환)
- Red 상태: 통합 테스트 0건 (사이클 97 mock 한정) → 신규 → FAIL (시정 영역 정합 검증)
- Green: G-FIX1 시정 후 PASS

### LOW 1

**G-REG1** — 사이클 97 기존 회귀 가드 영역 갱신 (`test_cycle97_fid_input_cnt_1_control.py` 영역 또는 등가 영역)
- `FID_RANK_SORT_CLS_CODE = "0"` 영속 검증 추가 (사이클 97 H-3.c 영역 보강)
- Red 상태: 사이클 97 영역 `"0000"` 검증 없음 → FAIL (검증 추가 후 production `"0000"` 잔존 시 FAIL)
- Green: G-FIX1 시정 후 PASS

## Red 검증 매트릭스 (production 변경 0 영역)

| 케이스 | 현재 (Green 전) 결과 | 비고 |
|-------|---------------------|------|
| G-FIX1 | FAIL | params `"0000"` 잔존 (KIS 영역 거부 시뮬레이션) |
| G-AST1 | FAIL | scanner.py source `"0000"` 잔존 AST 검출 |
| G-DOC1 | FAIL | docstring chk 인용 부재 AST 검출 |
| G-INT1 | FAIL | 통합 테스트 신규 + production 결함 영속 |
| G-REG1 | FAIL | 사이클 97 영역 검증 갱신 후 production 영역 거부 |

**flakiness 3 회 반복** = 모두 동일 결과 (production 영역 변경 0).

## 산출물

- `tests/unit/engine/scanner/test_cycle98_rank_sort_cls_code_fix.py` (G-FIX1, 1 케이스)
- `tests/unit/ast/test_cycle98_ast_rank_sort_cls_code.py` (G-AST1, 1 케이스)
- `tests/unit/ast/test_cycle98_ast_chk_citation_required.py` (G-DOC1, 1 케이스, **신규 패턴**)
- `tests/integration/test_cycle98_fluctuation_kis_api.py` (G-INT1, 1 케이스)
- `tests/unit/engine/scanner/test_cycle97_fid_input_cnt_1_control.py` (G-REG1 갱신, 1 케이스 추가)

총 5 케이스 (4 신규 파일 + 1 기존 갱신).

## Green 의무 (backend-dev 후속, 1줄 시정)

1. `src/engine/scanner.py:1529` — `"FID_RANK_SORT_CLS_CODE": "0000"` → `"FID_RANK_SORT_CLS_CODE": "0"` (1줄)
2. `src/engine/scanner.py:1497` docstring — `FID_RANK_SORT_CLS_CODE = "0000"` → `FID_RANK_SORT_CLS_CODE = "0"` + `KIS chk_fluctuation.py main 호출 영역 정본` 인용 주석 추가 (G-DOC1 통과 의무)

## 안전 규칙 영속 (CLAUDE.md "절대 깨지 말 것" 8 영역)

- 체결통보 H0STCNI0/H0STCNI9 구독 영속 (영역 무관)
- uvicorn 단일 워커 영속
- 주문번호 매핑 + race 가드 영속
- `_reset_daily_state` 영속
- 익일 청산 30s 안정화 영속
- NXT 좀비 차단 + SellRejectionTracker 영속
- WebSocket 4중 안전망 영속
- KIS 거부 응답 영속 (`[kis_rejection_quote]` 사이클 98 영역 정상 작동 확인 = OPSQ2002 ERROR 영구 기록)

## 사이클 영역 영속 매트릭스

- 사이클 38 명문화 (매수 진입 전용) 영속 — scanner 단계 영역 = 매도 hot path 영향 0
- 사이클 64 Q1 옵션 D 3중 안전망 영속 — 보유/익일청산 절대 보호 영역 무관
- 사이클 65 H1 영역 답습 (KIS 정본 100% 인용 의무 silent 결함 영역 답습)
- 사이클 81 `bfdy_clpr` 1줄 시정 패턴 답습 (단일 근본 원인 1줄 영구 시정 + AST 영구 가드)
- 사이클 89/91/94/96 volume_rank 영역 폐기 영속 (사이클 97 H-5 AST 영구 가드 영속)
- 사이클 97 영역 영속 (사이클 98 = 사이클 97 영역 1줄 시정만)

## silent 결함 영구 차단 영역 = 20 회 누적

사이클 60 / 64 / 65#1 / 65#2 / 65#3 / 66 / 67 / 68 / 72 / 73 / 77 / 77#2 / 78 / 79 / 80 / 80#2 / 80#3 / 80#4 / 81 / **98**.

**미래 영구 차단 패턴 신설 (G-DOC1)**: KIS 정본 영역 chk_*.py main 호출 영역 인용 의무 (docstring 영역 거짓 안내 영역 무시 의무, 사이클 98+ 영역 KIS API 통합 영역 영구 가드).

## 운영 영역 push 후 검증 영역 (Supabase MCP READ-ONLY)

- `[stock_master_bulk_refresh] universe=500 kospi=250 kosdaq=250 unknown=0 securities=500 etf_excluded=N` 영구 영역 (사이클 97 영역 의도 영속 달성)
- `[fetch_fluctuation]` ERROR 영역 0건 (OPSQ2002 영구 차단)
- `[kis_rejection_quote] path=/ranking/fluctuation` 영역 0건
- 다음 영업일 (2026-06-11 목요일) 09:30 momentum/breakout 후보 풀 ≥60 ticker 영속
