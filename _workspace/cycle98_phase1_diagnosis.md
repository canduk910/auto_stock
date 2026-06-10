# 사이클 98 Phase 1 진단 — KIS fluctuation API 0 ticker silent 결함 (HIGH 긴급)

## 사용자 보고 (2026-06-10)

> universe 0 ticker 즉시 적재 완료 (262ms)
> stats: 전체 종목 수 = 82 / 오늘 자동 갱신 횟수 = 77

## 결정적 silent 결함 영구 확정 (Supabase MCP 실증)

### 운영 실증 (2026-06-10 16:36 KST 사이클 97 push 직후)

| 시각 (KST) | log_level | 영역 |
|-----------|----------|------|
| 16:10~16:30 (사이클 97 *이전*) | INFO | `universe=60 kospi=30 kosdaq=30 ... elapsed_ms=203~211` (사이클 96 volume_rank 영속 영역) |
| **16:36:49** (사이클 97 *직후*) | **ERROR** | `[kis_rejection_quote] path=/uapi/domestic-stock/v1/ranking/fluctuation tr_id=FHPST01700000 label=gold msg_cd=OPSQ2002 msg1=ERROR INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]` |
| **16:36:49** | **ERROR** | `[kis_rejection_quote] ... label=sub msg_cd=OPSQ2002 msg1=ERROR INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]` |
| 16:36:50 | WARNING | `[fetch_fluctuation] KIS API 실패 market=kospi page=0 error=OPSQ2002 ... [FID_RANK_SORT_CLS_CODE] [4] (graceful 누적분 반환)` |
| 16:36:50 | WARNING | `[fetch_fluctuation] KIS API 실패 market=kosdaq page=0 error=OPSQ2002 ... [FID_RANK_SORT_CLS_CODE] [4]` |
| 16:36:50 | INFO | `[stock_master_bulk_refresh] universe=0 kospi=0 kosdaq=0 unknown=0 securities=0 etf_excluded=0 elapsed_ms=233` |
| 16:39:15 / 16:39:21 | 동일 패턴 반복 | KOSPI + KOSDAQ 양쪽 모두 OPSQ2002 거부 |

### Root Cause 확정

**KIS API 거부 정확 메시지**: `OPSQ2002: ERROR INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]`

**KIS API 거부 의미**: `FID_RANK_SORT_CLS_CODE` 파라미터 영역 **value 길이 4자리 미허용**. 사이클 97 영역 전달값 `"0000"` (4자리) = KIS 거부 영역.

### KIS 정본 vs 사이클 97 영역 차이점 매트릭스 (chk_fluctuation.py 직답 인용)

| 파라미터 | KIS 정본 (chk_fluctuation.py main 호출 영역) | 사이클 97 (Green 영역, scanner.py L1529) | 정합 |
|---------|---------------------------------------------|----------------------------------------|------|
| FID_COND_MRKT_DIV_CODE | `"J"` | `"J"` | OK |
| FID_COND_SCR_DIV_CODE | `"20170"` | `"20170"` | OK |
| FID_INPUT_ISCD | `"0000"` (전체) | `"0001"` (KOSPI) / `"0002"` (KOSDAQ) | OK (영역 적응) |
| **FID_RANK_SORT_CLS_CODE** | **`"0"`** (1자리) | **`"0000"`** (4자리) | **NG ✗ 결함** |
| FID_INPUT_CNT_1 | `"0"` | `str(top_n)` (e.g., `"250"`) | OK |
| FID_PRC_CLS_CODE | `"0"` | `"0"` | OK |
| FID_INPUT_PRICE_1/2 | `""` | `""` | OK |
| FID_VOL_CNT | `""` | `""` | OK |
| FID_TRGT_CLS_CODE | `"0"` | `"0"` | OK |
| FID_TRGT_EXLS_CLS_CODE | `"0"` | `"0"` | OK |
| FID_DIV_CLS_CODE | `"0"` | `"0"` | OK |
| FID_RSFL_RATE1/2 | `""` | `""` | OK |

**유일 차이 = `FID_RANK_SORT_CLS_CODE`**:
- KIS chk_fluctuation.py 영역 main 호출: `fid_rank_sort_cls_code="0"` (**1자리**)
- KIS fluctuation.py 영역 docstring: `(0000: 등락률순)` (**4자리, docstring 영역 거짓 안내**)
- 사이클 97 영역: docstring 영역 인용 → `"0000"` (4자리) → KIS 영역 거부

**부차 발견 (사이클 97 영역 영구 차단 후 추가 검증 영역)**:
- KIS 정본 chk_fluctuation.py 호출 영역 = `fid_input_cnt_1="0"` 영역. 사이클 97 영역 = `str(top_n)` 영역. KIS docstring 영역 = "조회할 종목 수" 영역. 정본 영역 = `"0"` 영역 (영역 의미 미상, KIS 영역 응답 영역 = 전체 영역). 사이클 97 영역 = top_n 영역 사용자 제어 영속 의도 (정합 가능 영역).
- KIS 정본 영역 `fid_cond_mrkt_div_code` 영역 = `["J", "W", "Q"]` 검증. 사이클 97 영역 = `"J"` 영역 (정합).
- KIS 정본 영역 fluctuation.py 영역 = `fid_input_iscd="0000"` 영역 (전체). 사이클 97 영역 = `"0001"`/`"0002"` 분리 호출 (사이클 96 영역 답습, KIS 영역 거부 영역 별도 검증 필요).

### 사이클 97 영역 backend-dev Green 단계 영구 결함

**KIS 정본 영역 100% 인용 못함**:
1. KIS fluctuation.py docstring 영역 (`0000: 등락률순`) 영역 인용 (1차 영역 영구 거짓 안내)
2. KIS chk_fluctuation.py main 호출 영역 (`fid_rank_sort_cls_code="0"` 영역 1자리 실측) 영역 미인용

**TDD 영역 단계 silent 결함 영역 발견 못함 (회귀 가드 영역 한계)**:
- 사이클 97 영역 회귀 가드 = `params["FID_RANK_SORT_CLS_CODE"] == "0000"` 영역 영구 검증
- KIS 영역 실제 응답 영역 통합 테스트 영역 0건 (mock 영속)
- → TDD 영역 정합 OK / 운영 영역 즉시 KIS 거부 영역 silent 차단

### 영향 영역

- **universe = 0 ticker 영구 영역** (KOSPI + KOSDAQ 양쪽 모두 page=0 첫 호출 즉시 거부 → 누적분 0건 graceful 반환)
- **stock_master 적재 0건** (사이클 89/91/94/96 영역 60 ticker 영속 영역 *도* 미달, **사이클 97 영역 = 완전 영구 영역 차단**)
- **매매 hot path 영향 0** (사이클 38 명문화 영속, scanner 단계 매수 진입 전용 + 사이클 64 protected_tickers 영역 영속 + 사이클 81 영역 영속)
- **운영 영향 (HIGH 긴급)**: 다음 영업일 (2026-06-11 목요일) 09:00 영역 *전*에 영구 시정 의무 (07:50 `TIME_BOOT` 영역에서 `fetch_top_500_universe()` 호출 → universe=0 영구 영역 → momentum/breakout 후보 풀 영구 0건 영역 → 매매 영구 차단)

## Q55~Q57 사용자 결정 의제

### Q55 (HIGH) 시정 방향

**옵션 A (강력 권고)**: `FID_RANK_SORT_CLS_CODE` `"0000"` → `"0"` 1줄 시정 (사이클 81 패턴 답습, 단일 근본 원인 1줄 시정).
- 회귀 가드 갱신 (`params["FID_RANK_SORT_CLS_CODE"] == "0"` 영역) + AST 영구 가드 신설 (`"0000"` 잔존 0건 + `"0"` ≥1건 + KIS chk_fluctuation.py 영역 정본 인용 docstring 의무)
- 통합 테스트 신설 (KIS API 실제 응답 영역 mock 영역 = OPSQ2002 거부 시나리오 + 정상 응답 시나리오 양쪽)
- 사이클 97 영역 docstring 영역 갱신 (정본 영역 인용 + 1자리 영역 명문화)

**옵션 B**: 사이클 97 영역 영구 폐기 + 사이클 96 영역 (volume_rank "0001"/"0002" 영역 60 ticker 영속) 영역 복원.
- 사이클 97 영역 도입 의도 (60 → 500 ticker) 영구 폐기
- 사용자 보고 영역 영속 (사이클 89~96 영역 60 ticker 영구 영속)

**옵션 C**: 사이클 89 영역 복원 (volume_rank 영역 60 ticker 영구 영속 수용).
- 사이클 91/94/96/97 영역 전수 폐기
- TIME_BOOT 07:50 영역 fetch_top_500_universe → fetch_top_60_universe 영역 명명 변경

### Q56 (HIGH) 영역 검증

**옵션 A (강력 권고)**: KIS MCP 정본 재검증 (chk_fluctuation.py 영역 100% 인용 완료, 본 보고서 영역 매트릭스 영속).

**옵션 B**: 사용자 EC2 SSH 운영 로그 (Supabase MCP 영역 = `[fetch_fluctuation]` ERROR 영역 실증 완료, 본 보고서 영역 16:36/16:39 영역).

**옵션 C**: A + B 통합 (**완료 영역**).

### Q57 (HIGH) push 시점

**옵션 A (강력 권고)**: 진단 직후 (KRX 메인 시간 외 = 현재 16:39 KST + KRX 마감 15:30 영속 + NXT 애프터 15:30~20:00 영역 = 매수 차단 영역 영속 = push 안전 영역).
- 사이클 38 명문화 영속 (매수 진입 전용 영역, 매도 hot path 영향 0)
- 사이클 95 patrol 답습 (사이클 95 영역 = chicken-and-egg lock-in 영역 시정 push KRX 메인 시간 영역도 영속)

**옵션 B**: NXT 애프터 마감 *후* (20:00+) — 보수적 영역. 사이클 38 명문화 영역 영속 의무 영역에서 영역 적용 불요.

## 영역 시정 청사진 (옵션 A 채택 가정)

### Production 코드 영역 (1 파일 +0/-0 영역, 영구 1줄 영역 시정)

**`src/engine/scanner.py:1529`**:
```python
# Before (사이클 97, KIS docstring 영역 거짓 안내 인용)
"FID_RANK_SORT_CLS_CODE": "0000",   # 등락률순

# After (사이클 98, KIS chk_fluctuation.py main 호출 영역 정본 인용)
"FID_RANK_SORT_CLS_CODE": "0",   # 등락률순 (KIS chk_fluctuation.py main 영역 정본 1자리)
```

### Docstring 영역 시정 (영구 가드 영구 영역)

**`src/engine/scanner.py:1497` docstring**:
```python
# Before
FID_RANK_SORT_CLS_CODE = "0000"  (등락률순)

# After
FID_RANK_SORT_CLS_CODE = "0"     (등락률순, KIS chk_fluctuation.py main 호출 영역 정본 영속)
                                  (KIS fluctuation.py docstring 영역 "0000" 영역 거짓 안내 영역 무시)
```

### 회귀 가드 영역 신규 (4 영역 5 케이스)

1. **G-FIX1** (`tests/unit/engine/scanner/test_cycle98_rank_sort_cls_code_fix.py`):
   - `params["FID_RANK_SORT_CLS_CODE"] == "0"` 영역 강제 검증
2. **G-AST1** (`tests/unit/ast/test_cycle98_ast_rank_sort_cls_code.py`):
   - `src/engine/scanner.py` 영역 `"0000"` 잔존 0건 AST 정적 가드 (FID_RANK_SORT_CLS_CODE 영역 한정 grep)
   - `"FID_RANK_SORT_CLS_CODE": "0"` 영역 ≥1건 AST 영구 가드
3. **G-INT1** (`tests/integration/test_cycle98_fluctuation_kis_api.py`):
   - KIS API 응답 영역 mock (정상 응답 정확 영역 인용 — output 영역 stck_shrn_iscd 영역 30건)
   - KIS API 거부 영역 mock (OPSQ2002 영역 graceful 영역 영속 검증)
4. **G-REG1**: 사이클 97 영역 기존 회귀 가드 영역 갱신 (`"0000"` → `"0"`)
5. **G-DOC1** (`tests/unit/ast/test_cycle98_ast_docstring_kis_chk_citation.py`):
   - docstring 영역 `chk_fluctuation.py main 호출 영역 정본` 영역 인용 의무

### 운영 영역 push 후 검증 영역 (Supabase MCP READ-ONLY)

- `[stock_master_bulk_refresh] universe=500 kospi=250 kosdaq=250 unknown=0 securities=500 etf_excluded=N` 영구 영역 (사이클 97 영역 의도 영속 달성)
- `[fetch_fluctuation]` ERROR 영역 0건 (OPSQ2002 영구 차단)
- `[kis_rejection_quote] path=/ranking/fluctuation` 영역 0건

## 진단 영역 요약

**결정적 결함 = 1 영역 (`"0000"` → `"0"` 1줄)**:
- KIS 영역 정본 = `"0"` (chk_fluctuation.py main 호출 영역 실측, 1자리)
- 사이클 97 영역 = `"0000"` (KIS fluctuation.py docstring 영역 거짓 안내 영역 인용, 4자리)
- KIS 영역 거부 = `OPSQ2002 INVALID INPUT_FILED_SIZE [FID_RANK_SORT_CLS_CODE] [4]` (영역 정확 일치)

**silent 결함 영구 차단 영역 = 20 회 누적 영속** (사이클 60/64/65#1/65#2/65#3/66/67/68/72/73/77/77#2/78/79/80/80#2/80#3/80#4/81/**98**).

**사이클 97 영역 = silent 결함 영역 = 사이클 65 H1 영역 답습**: KIS 정본 영역 100% 인용 안 함 → 회귀 가드 영역도 결함 영역 동일 영구 검증 → 운영 영역 즉시 KIS 거부 영역 silent 차단.

**미래 영역 영구 차단 패턴 신설**: AST G-DOC1 = KIS 정본 영역 chk_*.py main 호출 영역 정본 인용 의무 (docstring 영역 거짓 안내 영역 무시 의무, 사이클 98+ 영역 KIS API 통합 영역 영구 가드).
